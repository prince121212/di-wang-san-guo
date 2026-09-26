"""Idle map preparation shares the resident lane and the unfiltered local pool."""
import json
import types
import unittest
from unittest.mock import patch

import test_shared_resident_automation as fixtures
from dwpm_core.facade import CoreFacade
from dwpm_core.features.targets import brush_scan_coordinates, resident_brush_scan_limit
from dwpm_core.operations import OperationCancelledError
from dwpm_core.ports import PlatformPorts


class IdleBanditPrefetchTests(unittest.TestCase):
    def setUp(self):
        self.core, self.clock, self.directory = fixtures.SharedResidentAutomationTests()._facade()
        account = json.loads(self.core.account_record_json("303"))["account"]
        account["platformKey"] = "sglm"
        account["session"]["publicState"].update(level="99", serverKey="qzone_352")
        self.core.account_record_upsert(account)
        habits = fixtures.SharedResidentAutomationTests._habits()
        habits["config"]["brush"].update(startX=91, startY=26, scanLimit=80)
        self.core.configure_resident_automation_from_habits("303", habits)
        self.execution = fixtures.FakeExecution()
        self.calls = []
        self.core._execute_host_game_command = types.MethodType(self.command, self.core)

    def tearDown(self):
        self.core.close()
        self.directory.cleanup()

    def command(self, _core, _ref, opcode, payload, phase, context, **kwargs):
        self.calls.append((opcode, payload, context, kwargs))
        self.assertEqual(opcode, 0x1540)
        self.assertTrue(context["readOnly"])
        self.assertFalse(kwargs["mutation_sent"])
        return {"packets": [{"opcode": 0x8540, "payload": bytes.fromhex("00bb003800")}]}

    def idle(self, **values):
        return {"feature": None, "state": "idle", "success": True,
                "nextWakeAtMillis": self.clock.value + 30000, **values}

    def run_idle(self, result=None, context=None):
        return self.core._idle_bandit_prefetch(self.execution, "303", context or {}, result or self.idle())

    def state(self):
        return json.loads(self.core._account_public_state("303")["residentAutomationStateJson"])

    def test_one_read_per_idle_tick_and_persisted_cursor(self):
        first = self.run_idle()
        self.assertEqual(first["feature"], "banditPrefetch")
        self.assertEqual(first["scannedCount"], 1)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][2]["readTimeoutMillis"], 2000)
        self.assertEqual(self.calls[0][2]["transportMaxAttempts"], 1)
        self.assertEqual(self.state()["banditPrefetch"]["scanLimit"], 160)
        self.assertEqual(self.state()["banditPrefetch"]["cursor"], 1)
        self.run_idle()
        self.assertEqual(len(self.calls), 1)  # rate limited
        self.clock.value += 3000
        self.run_idle()
        self.assertEqual(self.state()["banditPrefetch"]["cursor"], 2)

    def test_normal_work_and_imminent_return_poll_always_win(self):
        for incoming in [self.idle(feature="brush", state="dispatched"),
                         self.idle(feature="general", state="completed"),
                         self.idle(nextWakeAtMillis=self.clock.value + 1000),
                         self.idle(nextWakeAtMillis=self.clock.value),
                         self.idle(requiresAttention=True)]:
            actual = self.run_idle(incoming)
            self.assertEqual(actual["feature"], incoming["feature"])
            self.assertLessEqual(actual["nextWakeAtMillis"], incoming["nextWakeAtMillis"])
        self.assertEqual(self.calls, [])

    def test_prefetch_can_wake_during_march_without_touching_ledger(self):
        ledger = {"targetId": 123, "generalIds": [7], "sendState": "accepted",
                  "nextPollAtMillis": self.clock.value + 30000}
        self.core._update_account_public_state("303", {"brushPendingRecoveryJson": json.dumps(ledger)})
        self.run_idle()
        self.assertEqual(json.loads(self.core._account_public_state("303")["brushPendingRecoveryJson"]), ledger)
        self.assertEqual(self.execution.sent, [])

    def test_skips_fresh_cells_including_empty_and_fills_outer_half(self):
        coords = brush_scan_coordinates(91, 26, 160)
        store = self.core._local_map_store("303", "bandit")
        for coord in coords[:80]:
            store.observe(coord, [], self.clock.value, 1800000)
        self.run_idle()
        self.assertEqual(self.state()["banditPrefetch"]["lastCoordinate"], list(coords[80]))
        self.assertEqual(self.state()["banditPrefetch"]["cursor"], 81)

    def test_fully_fresh_map_sleeps_then_refreshes(self):
        store = self.core._local_map_store("303", "bandit")
        for coord in brush_scan_coordinates(91, 26, 160):
            store.observe(coord, [], self.clock.value, 1800000)
        self.run_idle()
        self.assertFalse(self.calls)
        self.clock.value += 120000
        self.run_idle()
        self.assertEqual(len(self.calls), 1)

    def test_scan_retains_all_levels_for_later_filtered_cache_reuse(self):
        targets = [{"id": 100 + level, "idHex": f"{100 + level:016x}", "x": 90,
                    "y": 24, "kind": "山贼", "level": level, "resource": "宝物",
                    "composition": {"foot": 0, "bow": 2, "cavalry": 0,
                                    "chariot": 0, "source": "8540-units"}}
                   for level in [1, 7, 10]]
        with patch("dwpm_core.facade.parse_bandit_targets", return_value=targets):
            self.run_idle()
        cached = self.core._local_brush_targets(account_ref="303", kind="BANDIT",
                    fingerprint="91,26|SHAN_ZEI", ttl_millis=1800000,
                    coordinates=brush_scan_coordinates(91, 26, 160))
        self.assertEqual({t["level"] for t in cached}, {1, 7, 10})
        # A returning formation goes straight through the existing cache path;
        # it must not issue a second map read to rediscover the prepared target.
        public = self.core._account_public_state("303")
        config = json.loads(public["residentAutomationConfigJson"])
        with patch.object(self.core, "_run_brush_search_game_workflow", side_effect=AssertionError("unexpected rescan")), \
             patch.object(self.core, "_run_brush_execute_game_workflow", return_value={
                 "result": {"success": True, "successBattleId": 777}}) as dispatch:
            result = self.core._run_configured_brush_tick(
                self.execution, "303", config, self.state(), {})
        self.assertEqual(result["state"], "dispatched")
        self.assertEqual(dispatch.call_args.args[1]["target"]["level"], 1)

    def test_stop_membership_cleanup_cloud_and_feature_restrictions_skip_scan(self):
        self.run_idle(context={"configuredExecutionAllowed": False})
        self.run_idle(context={"allowedFeatures": ["mine"]})
        self.core._update_account_public_state("303", {"savedTasksStarted": "false"})
        self.run_idle()
        self.core._update_account_public_state("303", {"savedTasksStarted": "true", "cloudRuntimeConfigJson": json.dumps({"cloudBrushMapEnabled": True})})
        self.run_idle()
        self.assertEqual(self.calls, [])

    def test_failure_retries_same_coordinate_and_cancellation_propagates(self):
        def fail(*args, **kwargs):
            raise OSError("fixture unavailable")
        self.core._execute_host_game_command = fail
        self.run_idle()
        self.assertEqual(self.state()["banditPrefetch"]["cursor"], 0)
        self.assertEqual(self.state()["banditPrefetch"]["nextWakeAtMillis"], self.clock.value + 10000)
        self.clock.value += 10000
        self.core._execute_host_game_command = lambda *a, **kw: (_ for _ in ()).throw(OperationCancelledError())
        with self.assertRaises(OperationCancelledError):
            self.run_idle()

    def test_restart_keeps_unfiltered_cache_and_cursor(self):
        self.run_idle()
        self.core.close()
        self.clock.value += 3000
        self.core = CoreFacade(shared_root=fixtures.ROOT / "shared_core",
                operation_store_path=str(fixtures.Path(self.directory.name) / "operations.json"),
                ports=PlatformPorts(clock=self.clock))
        self.core._execute_host_game_command = types.MethodType(self.command, self.core)
        self.run_idle()
        self.assertEqual(self.state()["banditPrefetch"]["cursor"], 2)

    def test_range_upgrade_preserves_custom_values(self):
        self.assertEqual(resident_brush_scan_limit(80), 160)
        self.assertEqual(resident_brush_scan_limit(), 160)
        self.assertEqual(resident_brush_scan_limit(384), 384)
        self.assertEqual(resident_brush_scan_limit(20), 20)
        old, new = brush_scan_coordinates(91, 26, 80), brush_scan_coordinates(91, 26, 160)
        self.assertEqual(new[:80], old)
        self.assertLess(min(x for x, y in new), min(x for x, y in old))
        self.assertGreater(max(x for x, y in new), max(x for x, y in old))

    def test_actual_resident_tick_uses_idle_gap_and_yields_at_business_deadline(self):
        self.core._save_resident_automation_state("303", {"brush": {
            "lastState": "waiting", "nextWakeAtMillis": self.clock.value + 30000}})
        context = {"allowedFeatures": ["brush"]}
        first = self.core._run_automation_recovery_tick(self.execution, "303", context)
        self.assertEqual(first["feature"], "banditPrefetch")
        self.assertEqual(len(self.calls), 1)
        self.clock.value += 30000
        with patch.object(self.core, "_run_configured_brush_tick", return_value={
                "feature": "brush", "state": "dispatched", "success": True,
                "nextWakeAtMillis": self.clock.value + 1000}) as dispatch:
            second = self.core._run_automation_recovery_tick(self.execution, "303", context)
        dispatch.assert_called_once()
        self.assertEqual(second["feature"], "brush")
        self.assertEqual(len(self.calls), 1)

    def test_actual_tick_scans_while_all_generals_have_future_recovery_polls(self):
        self.core._update_account_public_state("303", {"brushPendingRecoveryJson": json.dumps({
            "recoveryKey": "brush:test", "targetId": 123, "generalIds": [7],
            "sendState": "accepted", "nextPollAtMillis": self.clock.value + 30000,
            "formationNumber": 1, "sourceRowIndex": 0,
        })})
        first = self.core._run_automation_recovery_tick(
            self.execution, "303", {"allowedFeatures": ["brush"]})
        self.assertEqual(first["feature"], "banditPrefetch")
        self.assertEqual(len(self.calls), 1)
        self.assertLess(first["nextWakeAtMillis"], self.clock.value + 30000)


if __name__ == "__main__":
    unittest.main()
