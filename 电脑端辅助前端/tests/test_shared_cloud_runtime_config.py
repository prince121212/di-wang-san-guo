"""Admin policy controls only cloud brush coordination, never game ledgers."""
from __future__ import annotations

import dataclasses
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import test_shared_brush_formation_lanes as lanes
from test_cloud_shared_map_core import FakeCloudPort
from dwpm_core.operations import OperationKnownFailureError


class ConfigCloud(FakeCloudPort):
    def __init__(self):
        super().__init__("CLOUD_SHARED")
        self.config_requests = []
        self.enabled = False
        self.revision = 1
        self.config_failure = False
        self.disable_path = ""

    def config(self):
        return {"schemaVersion": 1, "cloudBrushMapEnabled": self.enabled,
                "revision": self.revision, "updatedAtMillis": 123}

    def exchange(self, request):
        if request["path"] == "/v1/client/config":
            self.config_requests.append(deepcopy(request))
            if self.config_failure:
                raise OSError("offline")
            return {"status": 200, "body": {"ok": True, "config": self.config()}}
        if request["path"] == self.disable_path:
            self.calls.append(deepcopy(request))
            self.enabled = False
            self.revision += 1
            return {"status": 409, "body": {"ok": False, "code": "CLOUD_BRUSH_MAP_DISABLED",
                                             "config": self.config()}}
        return super().exchange(request)


class CloudRuntimeConfigTests(unittest.TestCase):
    def setUp(self):
        self.h = lanes.BrushFormationLaneTests()
        self.h.setUp()
        self.cloud = ConfigCloud()
        self.install_port()
        a = self.h.facade._accounts.get("303")
        self.h.facade.account_record_upsert({**a, "platformKey": "sglm", "serverId": "s1"})
        self.h.put(serverKey="s1")

    def install_port(self):
        self.h.facade._ports = dataclasses.replace(self.h.facade._ports, cloud_shared_data=self.cloud)

    def tearDown(self):
        self.h.tearDown()

    def test_disabled_tick_dispatches_locally_without_any_map_or_presence_request(self):
        config_before = self.h.public()["residentAutomationConfigJson"]
        result = self.h.tick()
        self.assertEqual(result["state"], "dispatched")
        self.assertEqual(result["mapMode"], "LOCAL_ONLY")
        self.assertIs(result["cloudBrushMapEnabled"], False)
        self.assertEqual(len(self.cloud.config_requests), 1)
        self.assertEqual(self.cloud.calls, [])
        self.assertEqual(config_before, self.h.public()["residentAutomationConfigJson"])
        self.h.facade._cloud_presence_mode("303", force=True)
        self.h.facade._cloud_publish_map_observations("303", "bandit", [], {}, queue_only=True)
        self.assertEqual(self.cloud.calls, [])

    def test_each_account_and_each_explicit_start_gets_latest_config(self):
        f = self.h.facade
        self.assertFalse(f.refresh_cloud_runtime_config("303")["cloudBrushMapEnabled"])
        f.refresh_cloud_runtime_config("303")
        self.assertEqual(len(self.cloud.config_requests), 1)
        a = f._accounts.get("303")
        f.account_record_upsert({**a, "accountRef": "404", "id": 404})
        f.refresh_cloud_runtime_config("404")
        self.assertEqual(len(self.cloud.config_requests), 2)
        self.cloud.enabled = True
        self.cloud.revision += 1
        self.assertTrue(f.refresh_cloud_runtime_config("303", force=True)["cloudBrushMapEnabled"])
        self.assertEqual(len(self.cloud.config_requests), 3)

    def test_process_restart_reads_config_again_but_does_not_clear_inflight_battle(self):
        self.h.tick()
        pending = deepcopy(self.h.pending())
        self.h.facade.close()
        self.h.facade = self.h.new_facade()
        self.install_port()
        self.h.facade.refresh_cloud_runtime_config("303")
        self.assertEqual(len(self.cloud.config_requests), 2)
        self.assertEqual(self.h.pending(), pending)

    def test_failed_startup_fetch_keeps_disabled_cache_or_defaults_local(self):
        f = self.h.facade
        f.refresh_cloud_runtime_config("303")
        self.cloud.enabled = True
        self.cloud.config_failure = True
        result = f.refresh_cloud_runtime_config("303", force=True)
        self.assertIs(result["cloudBrushMapEnabled"], False)
        self.assertEqual(result["source"], "cached")
        self.h.put(cloudRuntimeConfigJson="{}")
        self.assertEqual(f.refresh_cloud_runtime_config("303", force=True)["source"], "local-default")
        self.assertEqual(self.cloud.calls, [])

    def test_failed_fetch_keeps_last_enabled_decision_and_existing_fallback(self):
        self.cloud.enabled = True
        self.h.facade.refresh_cloud_runtime_config("303")
        self.cloud.config_failure = True
        result = self.h.facade.refresh_cloud_runtime_config("303", force=True)
        self.assertIs(result["cloudBrushMapEnabled"], True)
        self.assertEqual(result["source"], "cached")

    def test_concurrent_first_use_fetches_once_for_that_account(self):
        barrier = threading.Barrier(2)
        def read(_i):
            barrier.wait()
            return self.h.facade.refresh_cloud_runtime_config("303")
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(read, range(2)))
        self.assertEqual(len(self.cloud.config_requests), 1)
        self.assertEqual(results[0], results[1])

    def test_off_policy_retires_old_dependency_wait_without_replaying_old_battle(self):
        now = self.h.clock.value
        self.h.put(brushPendingRecoveryJson=json.dumps(self.h.old_pending(nextPollAtMillis=now + 600000)),
                   residentAutomationStateJson=json.dumps({"brush": {
                       "lastState": "waiting-dependency", "nextWakeAtMillis": now + 999999,
                       "dependencyWait": {"dependency": "cloud-map", "retryAtMillis": now + 999999}}}))
        pending = deepcopy(self.h.pending()[0])
        self.h.tick()
        self.assertNotIn("dependencyWait", json.loads(self.h.public()["residentAutomationStateJson"])["brush"])
        restored = next(row for row in self.h.pending() if row.get("battleId") == pending["battleId"])
        self.assertEqual({key: restored[key] for key in pending}, pending)

    def test_reenable_resets_only_cloud_probe_cooldown(self):
        self.h.facade.refresh_cloud_runtime_config("303")
        self.h.put(brushCloudFallbackJson=json.dumps({"scope": ["sglm", "s1"], "active": True,
                                                     "nextProbeAtMillis": self.h.clock.value + 999999}))
        self.cloud.enabled = True
        self.cloud.revision += 1
        self.h.facade.refresh_cloud_runtime_config("303", force=True)
        fallback = json.loads(self.h.public()["brushCloudFallbackJson"])
        self.assertEqual(fallback["nextProbeAtMillis"], 0)
        self.assertTrue(fallback["active"], "only real write receipts may confirm cloud recovery")

    def test_server_disable_between_start_and_dispatch_switches_once_before_game_mutation(self):
        self.cloud.enabled = True
        f = self.h.facade
        f.refresh_cloud_runtime_config("303")
        self.cloud.disable_path = "/v1/maps/targets/reserve"
        routes = []
        def run(mode, _attempt):
            routes.append(mode)
            if mode == "CLOUD_SHARED":
                f._cloud_map_exchange("303", "/v1/maps/targets/reserve", {"mapKind": "bandit"})
            return {"ok": True}
        result = f._run_brush_with_map_route("303", run)
        self.assertEqual(routes, ["CLOUD_SHARED", "LOCAL_ONLY"])
        self.assertIs(result["cloudBrushMapEnabled"], False)
        self.assertFalse(json.loads(self.h.public().get("brushCloudFallbackJson") or "{}").get("active"))

    def test_admin_disabled_direct_map_exchange_cannot_leak_an_upload(self):
        with self.assertRaises(OperationKnownFailureError) as caught:
            self.h.facade._cloud_map_exchange("303", "/v1/maps/observations", {"mapKind": "bandit"})
        self.assertEqual(caught.exception.code, "CLOUD_BRUSH_MAP_DISABLED")
        self.assertEqual(self.cloud.calls, [])

    def test_rejects_rollback_config_and_preserves_disabled_decision(self):
        self.cloud.revision = 3
        self.h.facade.refresh_cloud_runtime_config("303")
        self.cloud.revision = 2
        self.cloud.enabled = True
        result = self.h.facade.refresh_cloud_runtime_config("303", force=True)
        self.assertIs(result["cloudBrushMapEnabled"], False)
        self.assertEqual(result["revision"], 3)


if __name__ == "__main__":
    unittest.main()
