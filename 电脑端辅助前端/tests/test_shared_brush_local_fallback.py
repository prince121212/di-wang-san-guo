"""Cloud coordination is optional; game send journals are not."""

from __future__ import annotations

import copy
import dataclasses
import json
import threading
import types
import unittest

import test_cloud_shared_map_core as cloud_tests
import test_shared_brush_formation_lanes as lanes
import test_shared_cloud_map_replica as maps
from test_shared_local_map_reuse import RecordingMapSnapshotPort
from dwpm_core import CoreFacade
from dwpm_core.operations import OperationKnownFailureError, OperationUncertainError


class FailingCloud(cloud_tests.FakeCloudPort):
    def __init__(self):
        super().__init__("CLOUD_SHARED")
        self.v2 = True
        self.failure_path = "/v1/maps/targets/reserve"
        self.failure_status = 503
        self.failure_code = "CLOUD_D1_DAILY_LIMIT"
        self.failure_target_status = None
        self.network_error = False

    def exchange(self, request):
        if request["path"] == self.failure_path and (
            self.failure_target_status is None
            or request["body"].get("status") == self.failure_target_status
        ):
            self.calls.append(copy.deepcopy(request))
            if self.network_error:
                raise OSError("fixture offline")
            return {"status": self.failure_status, "body": {
                "ok": False, "code": self.failure_code, "error": "fixture unavailable",
            }}
        return super().exchange(request)


class BrushLocalFallbackTests(unittest.TestCase):
    def setUp(self):
        self.h = lanes.BrushFormationLaneTests()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.cloud = FailingCloud()
        self.cloud.sync_targets = [maps.cloud_row(
            "000000000000abcd", level=7, last_seen=self.h.clock.value,
            data={
                "kind": "山贼", "resource": "宝物", "dropCategories": ["宝物"],
                "composition": {"foot": 1, "bow": 0, "cavalry": 0, "chariot": 0,
                                "source": "8540-units"},
                "unitTypes": [1],
            },
        )]
        self.install_port()
        account = json.loads(self.h.facade.account_record_json("303"))["account"]
        self.h.facade.account_record_upsert({
            **account, "platformKey": "sglm", "serverId": "server-352",
        })
        self.h.put(serverKey="server-352")
        self.before_config = self.h.public()["residentAutomationConfigJson"]

    def install_port(self):
        self.h.facade._ports = dataclasses.replace(
            self.h.facade._ports, cloud_shared_data=self.cloud,
        )

    def route(self):
        return json.loads(self.h.public().get("brushCloudFallbackJson") or "{}")

    def configured_tick(self):
        return self.h.facade._run_configured_brush_tick(
            cloud_tests.FakeExecution(), "303",
            json.loads(self.h.public()["residentAutomationConfigJson"]),
            json.loads(self.h.public()["residentAutomationStateJson"]), {},
        )

    def local_target(self, target_id=90001):
        return {
            "id": target_id, "idHex": f"{target_id:016x}", "x": 10, "y": 10,
            "kind": "山贼", "level": 7, "resource": "宝物", "dropCategories": ["宝物"],
            "composition": {"foot": 1, "bow": 0, "cavalry": 0, "chariot": 0,
                            "source": "8540-units"},
            "units": [{"soldierTypeCode": 1}],
            "fromCache": True, "fromLocalSnapshot": True,
        }

    def test_quota_uses_true_local_snapshot_and_preserves_old_battle(self):
        self.h.put(**{lanes.ACTIVE: json.dumps(self.h.old_pending(
            nextPollAtMillis=self.h.clock.value + 600_000
        ))})
        before = copy.deepcopy(self.h.pending()[0])
        snapshots = RecordingMapSnapshotPort()
        self.h.facade._ports = dataclasses.replace(self.h.facade._ports, map_snapshots=snapshots)
        target = {**self.local_target(), "compositionCode": "1000"}
        self.h.facade._save_map_snapshot(
            account_ref="303", kind="BANDIT", fingerprint="10,10|SHAN_ZEI",
            targets=[target], scanned_at_millis=self.h.clock.value,
        )
        self.h.facade._observe_local_map("303", "bandit", (12, 12), [target])
        result = self.h.tick()
        self.assertEqual(result["state"], "dispatched", result)
        self.assertEqual(result["mapMode"], "LOCAL_FALLBACK")
        self.assertEqual(result["target"]["id"], 90001)
        self.assertTrue(result["target"]["fromLocalSnapshot"])
        self.assertTrue(result["target"]["fromCache"])
        self.assertEqual(result["formationNumber"], 2)
        self.assertEqual(self.h.searched, 0)
        self.assertEqual(len(self.h.sent), 1)
        old = next(p for p in self.h.pending() if p["generalIds"] == [7])
        self.assertEqual({k: old[k] for k in before}, before)
        self.assertEqual(self.route()["failureCode"], "CLOUD_D1_DAILY_LIMIT")
        self.assertEqual(self.route()["nextProbeAtMillis"], self.h.clock.value + 300_000)
        self.assertEqual(self.h.public()["residentAutomationConfigJson"], self.before_config)

    def test_cooldown_limits_cloud_calls_not_four_formation_dispatches(self):
        first = self.h.tick()
        calls = copy.deepcopy(self.cloud.calls)
        results = [first]
        for _ in range(3):
            self.h.clock.value += 2_000
            results.append(self.h.tick())
        self.assertEqual([r["state"] for r in results], ["dispatched"] * 4, results)
        self.assertEqual({r["formationNumber"] for r in results}, {1, 2, 3, 4})
        self.assertEqual(self.cloud.calls, calls)
        self.assertEqual(len(self.h.pending()), 4)
        self.assertEqual(len(self.h.sent), 4)
        self.assertEqual(self.h.public()["residentAutomationConfigJson"], self.before_config)

    def test_restart_preserves_fallback_and_sends_only_an_idle_formation(self):
        self.h.tick()
        before = copy.deepcopy(self.h.pending())
        route = self.route()
        calls = copy.deepcopy(self.cloud.calls)
        self.h.facade.close()
        self.h.facade = self.h.new_facade()
        self.h.install_game_boundaries()
        self.install_port()
        self.h.clock.value += 2_000
        result = self.h.tick()
        self.assertEqual(result["mapMode"], "LOCAL_FALLBACK")
        self.assertEqual(result["formationNumber"], 3)
        self.assertEqual(self.route(), route)
        self.assertEqual(self.cloud.calls, calls)
        self.assertEqual(len(self.h.pending()), 2)
        self.assertEqual(next(p for p in self.h.pending() if p["battleId"] == before[0]["battleId"]), before[0])

    def test_healthy_heartbeat_is_not_recovery_but_two_write_receipts_are(self):
        self.h.tick()
        self.cloud.failure_path = ""
        self.h.facade.cloud_presence_heartbeat("303")
        self.assertTrue(self.route()["active"])
        self.h.clock.value = self.route()["nextProbeAtMillis"]
        result = self.configured_tick()
        self.assertEqual(result["mapMode"], "CLOUD_SHARED", result)
        self.assertEqual(result["target"]["id"], 0xabcd)
        self.assertFalse(self.route()["active"])
        self.assertEqual(self.route()["recoveryEvidence"], "reserve-and-dispatching")

    def test_successful_heartbeat_and_reserve_but_failed_dispatching_stay_local(self):
        self.h.tick()
        self.h.clock.value = self.route()["nextProbeAtMillis"]
        self.cloud.failure_path = "/v1/maps/targets/status"
        self.cloud.failure_target_status = "dispatching"
        result = self.configured_tick()
        self.assertEqual(result["mapMode"], "LOCAL_FALLBACK")
        self.assertEqual(len(self.h.sent), 2, "never send once for each route")
        self.assertTrue(self.route()["active"])

    def test_network_and_server_failure_each_fall_back_before_game_mutation(self):
        for status, code, network in (
            (500, "INTERNAL_ERROR", False), (503, "CLOUD_D1_DAILY_LIMIT", False),
            (401, "UNAUTHORIZED", False), (429, "RATE_LIMIT", False),
            (500, "", True),
        ):
            with self.subTest(status=status, network=network):
                self.h.put(brushCloudFallbackJson="{}")
                self.cloud.failure_status = status
                self.cloud.failure_code = code
                self.cloud.network_error = network
                # Direct routing also covers read-only manual search.
                calls = []
                result = self.h.facade._run_brush_with_map_route(
                    "303", lambda mode, _attempt: self.route_probe(mode, calls)
                )
                self.assertEqual(calls, ["CLOUD_SHARED", "LOCAL_FALLBACK"])
                self.assertEqual(result["mapMode"], "LOCAL_FALLBACK")
                self.assertEqual(self.h.sent, [])

    def route_probe(self, mode, calls):
        calls.append(mode)
        if mode == "CLOUD_SHARED":
            self.h.facade._cloud_map_exchange(
                "303", "/v1/maps/targets/reserve",
                {"mapKind": "bandit", "targetId": "000000000000abcd"},
            )
        return {"ok": True}

    def test_heartbeat_outage_falls_back_without_changing_the_presence_fact(self):
        self.h.facade.cloud_presence_heartbeat("303")
        self.h.clock.value += cloud_tests.CLOUD_PRESENCE_RENEW_MILLIS + 1
        self.cloud.failure_path = "/v1/presence/heartbeat"
        result = self.h.tick()
        self.assertEqual(result["mapMode"], "LOCAL_FALLBACK")
        presence = json.loads(self.h.public()["cloudMapPresenceJson"])
        self.assertEqual(presence["mode"], "CLOUD_UNAVAILABLE")
        self.assertTrue(presence["previouslyShared"])
        with self.assertRaises(OperationKnownFailureError):
            self.h.facade._cloud_map_action_mode("303", "找矿")

    def test_soft_subscription_failure_switches_to_local_not_old_cloud_rows(self):
        self.cloud.failure_path = ""
        replica = self.h.facade._cloud_map_replica("303", "bandit")
        self.assertTrue(replica.ensure_fresh())
        self.h.clock.value += 61_000
        self.cloud.failure_path = "/v1/maps/targets/changes"
        result = self.h.tick()
        self.assertEqual(result["mapMode"], "LOCAL_FALLBACK")
        self.assertNotEqual(result["target"]["id"], 0xabcd)
        self.assertFalse(any(c["path"].endswith("/reserve") for c in self.cloud.calls))

    def test_normal_competition_and_validation_error_never_trigger_fallback(self):
        self.cloud.failure_path = ""
        self.cloud.reserved = False
        self.cloud.reserve_reason = "unavailable"
        result = self.h.tick()
        self.assertEqual(result["state"], "no-targets")
        self.assertFalse(self.route().get("active"))
        self.assertEqual(self.h.sent, [])
        self.assertEqual(self.h.searched, 0)
        self.cloud.failure_path = "/v1/maps/targets/reserve"
        self.cloud.failure_status = 400
        self.cloud.failure_code = "INVALID_TARGET"
        with self.assertRaises(OperationKnownFailureError) as raised:
            self.h.facade._run_brush_with_map_route(
                "303", lambda mode, _attempt: self.route_probe(mode, [])
            )
        self.assertEqual(raised.exception.code, "INVALID_TARGET")
        self.assertFalse(self.route().get("active"))

    def test_post_dispatch_cloud_failure_never_replays_the_accepted_game_action(self):
        self.cloud.failure_path = "/v1/maps/targets/status"
        self.cloud.failure_target_status = "dispatched"
        result = self.h.tick()
        self.assertEqual(result["state"], "dispatched")
        self.assertEqual(len(self.h.sent), 1)
        self.assertEqual(self.h.pending()[0]["sendState"], "accepted")
        self.assertTrue(self.route()["active"])
        self.h.clock.value += 2_000
        self.assertEqual(self.h.tick()["mapMode"], "LOCAL_FALLBACK")
        self.assertEqual(len(self.h.sent), 2)

    def test_uncertain_game_receipt_is_not_a_reason_to_retry_locally(self):
        self.cloud.failure_path = ""
        command = self.h.facade._daily_command_fact

        def missing_receipt(*args, **kwargs):
            result = command(*args, **kwargs)
            return {} if args[2] == 0x1522 else result

        self.h.facade._daily_command_fact = missing_receipt
        with self.assertRaises(OperationUncertainError):
            self.h.tick()
        self.assertEqual(len(self.h.sent), 1)
        self.assertEqual(self.h.pending()[0]["sendState"], "uncertain")
        self.assertFalse(self.route().get("active"))

    def test_explicit_local_route_removes_old_dispatch_wait_not_old_battle(self):
        state = json.loads(self.h.public()["residentAutomationStateJson"])
        state["brush"]["dependencyWait"] = {
            "path": "/v1/maps/targets/reserve", "failureAtMillis": self.h.clock.value - 10_000,
            "retryAtMillis": self.h.clock.value, "message": "old wait", "errorCode": "INTERNAL_ERROR",
        }
        self.h.put(residentAutomationStateJson=json.dumps(state))
        result = self.h.tick()
        self.assertEqual(result["state"], "dispatched")
        saved = json.loads(self.h.public()["residentAutomationStateJson"])["brush"]
        self.assertNotIn("dependencyWait", saved)
        self.assertEqual(saved["mapMode"], "LOCAL_FALLBACK")
        self.assertIn("本地地图", saved["lastMessage"])
        self.assertEqual(len(self.h.pending()), 1)

    def test_real_local_scanner_remains_bounded_without_matches_and_does_not_change_filters(self):
        self.cloud.failure_path = "/v1/presence/heartbeat"
        self.h.facade._run_brush_search_game_workflow = types.MethodType(
            CoreFacade._run_brush_search_game_workflow, self.h.facade
        )
        self.h.put(gameHttp="https://game.example/HttpClient?dm=fixture")
        requests = maps.CloudMapReplicaFacadeTests()._record_map_requests(self.h.facade)
        first = self.h.tick()
        self.assertEqual(first["state"], "no-targets")
        self.assertEqual(first["mapMode"], "LOCAL_FALLBACK")
        self.assertEqual(first["scannedCount"], 5)
        self.assertEqual(len(requests), 5)
        cloud_calls = copy.deepcopy(self.cloud.calls)
        self.h.clock.value = first["nextWakeAtMillis"]
        second = self.h.tick()
        self.assertEqual(second["state"], "no-targets")
        self.assertEqual(len(requests), 10)
        self.assertEqual(self.cloud.calls, cloud_calls)
        self.assertEqual(self.h.sent, [])
        self.assertEqual(self.h.public()["residentAutomationConfigJson"], self.before_config)

    def test_offline_observations_queue_before_first_cloud_sync_without_network(self):
        self.cloud.failure_path = "/v1/presence/heartbeat"
        self.h.tick()
        calls = copy.deepcopy(self.cloud.calls)
        replica = self.h.facade._cloud_map_replica("303", "bandit")
        self.assertFalse(replica.full_sync_done)
        self.h.facade._cloud_publish_map_observations(
            "303", "bandit",
            [{"scanCoord": [10, 10], "targets": [self.local_target(90002)]}], {},
        )
        self.assertTrue(replica.upload_pending(f"{90002:016x}"))
        self.assertEqual(self.cloud.calls, calls)

    def test_known_peer_lease_is_not_bypassed_by_local_fallback(self):
        replica = self.h.facade._cloud_map_replica("303", "bandit")
        replica.defer_candidate(f"{90001:016x}", "unavailable",
                                retry_at_millis=self.h.clock.value + 180_000)
        self.h.facade._local_brush_targets = lambda **_kw: [self.local_target()]
        result = self.h.tick()
        self.assertEqual(result["mapMode"], "LOCAL_FALLBACK")
        self.assertNotEqual(result["target"]["id"], 90001)
        self.assertEqual(self.h.searched, 1)

    def test_manual_local_dispatch_falls_back_but_cloud_only_target_requires_local_reselection(self):
        body = self.h.facade.brush_execute_operation_payload({
            "accountRef": "303", "confirm": "brush-yellow", "generalIds": ["8"],
            "target": self.local_target(),
        }, {})
        result = self.h.facade._run_cloud_coordinated_brush_execute_game_workflow(
            cloud_tests.FakeExecution(), body, {},
        )
        self.assertEqual(result["mapMode"], "LOCAL_FALLBACK")
        self.assertEqual(len(self.h.sent), 1)
        self.assertEqual(self.h.pending()[0]["sendState"], "accepted")
        body = self.h.facade.brush_execute_operation_payload({
            "accountRef": "303", "confirm": "brush-yellow", "generalIds": ["9"],
            "target": {"id": 5555, "x": 10, "y": 10, "fromCloudSharedMap": True},
        }, {})
        with self.assertRaises(OperationKnownFailureError) as raised:
            self.h.facade._run_cloud_coordinated_brush_execute_game_workflow(
                cloud_tests.FakeExecution(), body, {},
            )
        self.assertEqual(raised.exception.code, "BRUSH_LOCAL_TARGET_REQUIRED")
        self.assertEqual(len(self.h.sent), 1)

    def peer(self, server="server-352", target_id=90001, send_state="uncertain"):
        self.h.facade.account_record_upsert({
            "accountRef": "404", "id": 404, "enabled": False, "platformKey": "sglm",
            "serverId": server,
            "session": {"publicState": {
                "serverKey": server, "savedTasksStarted": "false",
                lanes.ACTIVE: json.dumps({
                    "recoveryKey": "peer-battle", "generalIds": [77], "targetId": target_id,
                    "sendState": send_state,
                }),
            }},
        })

    def test_stopped_same_server_account_still_protects_its_uncertain_target(self):
        self.peer()
        self.h.facade._local_brush_targets = lambda **_kw: [self.local_target()]
        result = self.h.tick()
        self.assertEqual(result["state"], "dispatched")
        self.assertNotEqual(result["target"]["id"], 90001)
        self.assertEqual(self.h.searched, 1)
        account = self.h.facade._accounts.get("404")
        self.assertFalse(account["enabled"])
        self.assertEqual(account["session"]["publicState"]["savedTasksStarted"], "false")
        with self.assertRaises(OperationKnownFailureError) as raised:
            self.h.facade._begin_brush_recovery_record("303", {
                "recoveryKey": "new", "generalIds": [7], "targetId": 90001,
            })
        self.assertEqual(raised.exception.code, "BRUSH_TARGET_ALREADY_PENDING")

    def test_other_server_target_is_not_a_local_lock(self):
        self.peer(server="server-351")
        self.h.facade._local_brush_targets = lambda **_kw: [self.local_target()]
        result = self.h.tick()
        self.assertEqual(result["target"]["id"], 90001)
        self.assertEqual(self.h.searched, 0)

    def test_same_device_target_admission_is_atomic_across_accounts(self):
        self.peer(target_id=88, send_state="accepted")
        barrier = threading.Barrier(2)
        outcomes = []

        def begin(ref, general):
            barrier.wait()
            try:
                self.h.facade._begin_brush_recovery_record(ref, {
                    "recoveryKey": f"race-{ref}", "generalIds": [general], "targetId": 123456,
                })
                outcomes.append("ok")
            except OperationKnownFailureError as error:
                outcomes.append(error.code)

        threads = [threading.Thread(target=begin, args=args) for args in (("303", 8), ("404", 78))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
        self.assertCountEqual(outcomes, ["ok", "BRUSH_TARGET_ALREADY_PENDING"])


class LocalConsumedOutboxTests(unittest.TestCase):
    def test_held_upload_survives_restart_cloud_replay_and_only_fresh_game_fact_releases_it(self):
        import tempfile
        from pathlib import Path
        from dwpm_core.features.cloud_map_replica import CloudMapReplicaStore

        with tempfile.TemporaryDirectory() as directory:
            clock = maps.MutableClock()
            exchange = maps.FakeExchange()
            make = lambda: CloudMapReplicaStore(
                server_key="server", map_kind="bandit", data_directory=Path(directory),
                clock=clock.now_millis, exchange=exchange,
            )
            store = make()
            target = maps.observation("000000000000abcd")
            target_id = target["targetId"]
            store.apply_scan_observation(1, 1, [target])
            at = clock.value + 1
            clock.value = at
            store.record_consumed_targets({target_id: at})
            restored = make()
            self.assertTrue(restored.upload_pending(target_id))
            self.assertFalse(restored.flush_uploads())
            self.assertEqual(exchange.calls, [])
            clock.value += 1
            restored.apply_scan_observation(1, 1, [target], protected_target_ids={target_id})
            self.assertFalse(restored.flush_uploads())
            restored._apply_row(restored._targets, maps.cloud_row(target_id, changed=clock.value))
            self.assertFalse(restored.flush_uploads())
            clock.value += 1
            restored.apply_scan_observation(1, 1, [target])
            restored.record_consumed_targets({target_id: at})  # Same receipt is not a new dispatch.
            self.assertTrue(restored.flush_uploads())
            self.assertFalse(restored.upload_pending(target_id))
            self.assertEqual(len(exchange.calls), 1)


if __name__ == "__main__":
    unittest.main()
