"""Local map sharing and admission must work with a completely dead cloud."""
from __future__ import annotations

import json
import struct
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

from test_shared_resident_automation import CoreFacade, FakeExecution, FixedClock, PlatformPorts, ROOT
from dwpm_core.operations import OperationKnownFailureError, OperationUncertainError
from dwpm_core.automation import resident_due_decision


class LocalMineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "operations.json")
        self.clock = FixedClock()
        self.facade = self.new_facade()
        for ref, platform, server in [("202", "sglm", "s1"), ("176", "sglm", "s1"),
                                      ("999", "sglm", "s2"), ("888", "kuaiwan", "s1")]:
            self.facade.account_record_upsert({"accountRef": ref, "id": int(ref),
                "platformKey": platform, "serverId": server, "enabled": ref == "202",
                "session": {"publicState": {"serverKey": server}}})
        self.target = {"id": 88, "idHex": "0000000000000058", "x": 10, "y": 10,
                       "kind": "银矿", "mineType": "SILVER", "level": 1,
                       "playerOccupied": False, "defenderCount": 0}
        self.body = {"accountRef": "202", "startX": 10, "startY": 10, "scope": "定点",
                     "resourceTypes": ["SILVER"], "levels": [1], "scanLimit": 1}
        self.sent = []
        self.facade._run_expedition_preflight = Mock(return_value=([
            {"id": 7, "idHex": "0000000000000007"}], {}))
        self.facade._daily_command_fact = self.command

    def new_facade(self):
        facade = CoreFacade(shared_root=ROOT / "shared_core", operation_store_path=self.path,
                            ports=PlatformPorts(clock=self.clock))
        facade._cloud_presence_mode = Mock(side_effect=AssertionError("mine used cloud presence"))
        facade._cloud_map_exchange = Mock(side_effect=AssertionError("mine used cloud map"))
        return facade

    def tearDown(self):
        self.facade.close()
        self.directory.cleanup()

    def observe(self, ref="176", **changes):
        self.facade._observe_local_map(ref, "mine", (10, 10), [{**self.target, **changes}])

    def command(self, _execution, ref, opcode, _payload, *_args, **_kw):
        self.sent.append((ref, opcode))
        payload = (struct.pack(">iqqBHH", 20, 0, 0, 100, 10, 10) if opcode == 0x1520
                   else b"\0\0\0" + struct.pack(">q", 12345))
        return {"packets": [{"opcode": opcode + 0x7000, "payload": payload}]}

    def execute(self, ref="202"):
        return self.facade._run_cloud_coordinated_mine_execute_game_workflow(
            FakeExecution(), {"accountRef": ref, "target": dict(self.target),
                              "generalIds": [7], "fullLoyalty": True}, {})

    def claim(self, ref="202", target=None):
        target = target or self.target
        return self.facade._begin_mine_recovery_record(ref, {
            "mineId": target["id"], "target": deepcopy(target), "generalIds": [7],
            "dispatchSendState": "sending"})

    def test_shared_map_reuses_stopped_same_server_account_without_cloud_or_scan(self):
        self.observe()
        self.facade._run_mine_search_game_workflow = Mock(side_effect=AssertionError("unnecessary scan"))
        result = self.facade._run_cloud_coordinated_mine_search_game_workflow(FakeExecution(), self.body, {})
        self.assertEqual(result["targets"][0]["id"], 88)
        self.assertIs(result["targets"][0]["playerOccupied"], False)
        self.assertEqual(result["mapMode"], "LOCAL_ONLY")

    def test_different_platform_and_server_never_share(self):
        self.observe()
        for ref in ("999", "888"):
            self.assertEqual(self.facade._local_map_store(ref, "mine").targets(self.clock.value, 10000), [])

    def test_fresh_occupied_observation_supersedes_empty_view_for_both_accounts(self):
        self.observe()
        self.clock.value += 1
        self.observe("202", playerOccupied=True)
        self.facade._run_mine_search_game_workflow = Mock(return_value={"targets": []})
        self.assertEqual(self.facade._run_local_mine_search(FakeExecution(), self.body, {})["targets"], [])

    def test_map_preserves_other_cells_and_expires_each_observation_independently(self):
        self.observe()
        self.clock.value += self.facade._local_map_ttl("mine") + 1
        self.facade._observe_local_map("202", "mine", (30, 30), [{**self.target, "id": 89, "idHex": "0000000000000059"}])
        self.assertEqual([t["id"] for t in self.facade._local_map_store("176", "mine").targets(
            self.clock.value, self.facade._local_map_ttl("mine"))], [89])

    def test_empty_cell_observation_removes_old_target_but_not_other_cell(self):
        self.observe()
        self.facade._observe_local_map("202", "mine", (30, 30), [{**self.target, "id": 89, "idHex": "0000000000000059"}])
        self.facade._observe_local_map("176", "mine", (10, 10), [])
        self.assertEqual([t["id"] for t in self.facade._local_map_store("202", "mine").targets(
            self.clock.value, 1000)], [89])

    def test_search_filters_are_account_specific_not_a_shared_write_filter(self):
        self.observe(level=2)
        body = {**self.body, "levels": [2]}
        self.assertEqual(self.facade._run_local_mine_search(FakeExecution(), body, {})["count"], 1)
        self.facade._run_mine_search_game_workflow = Mock(return_value={"targets": []})
        self.assertEqual(self.facade._run_local_mine_search(FakeExecution(), self.body, {})["count"], 0)

    def test_nearby_scan_is_bounded_and_continues_after_restart(self):
        scanned = []
        self.facade._run_mine_search_game_workflow = lambda _e, body, _c: (
            scanned.append(body["_scanCoordinatesOverride"]) or {"targets": []})
        body = {**self.body, "scope": "附近", "scanLimit": 80}
        self.facade._run_local_mine_search(FakeExecution(), body, {})
        self.facade.close()
        self.facade = self.new_facade()
        self.facade._run_mine_search_game_workflow = lambda _e, body, _c: (
            scanned.append(body["_scanCoordinatesOverride"]) or {"targets": []})
        self.facade._run_local_mine_search(FakeExecution(), body, {})
        self.assertLessEqual(len(scanned[0]), 5)
        self.assertFalse(set(map(tuple, scanned[0])) & set(map(tuple, scanned[1])))

    def test_two_accounts_atomic_admission_has_only_one_winner(self):
        barrier = threading.Barrier(2)
        def enter(ref):
            barrier.wait()
            try:
                self.claim(ref)
                return "accepted"
            except OperationKnownFailureError as error:
                return error.code
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(enter, ["202", "176"]))
        self.assertCountEqual(results, ["accepted", "MINE_TARGET_ALREADY_PENDING"])

    def test_real_dispatch_is_local_and_peer_cannot_send_even_when_stopped(self):
        self.assertEqual(self.execute()["result"]["successBattleId"], 12345)
        with self.assertRaises(OperationKnownFailureError) as caught:
            self.execute("176")
        self.assertEqual(caught.exception.code, "MINE_TARGET_ALREADY_PENDING")
        self.assertEqual(self.sent, [("202", 0x1520), ("202", 0x1522)])

    def test_map_and_uncertain_claim_survive_restart(self):
        self.observe()
        self.claim()
        self.facade.close()
        self.facade = self.new_facade()
        self.assertEqual(len(self.facade._local_map_store("176", "mine").targets(self.clock.value, 1000)), 1)
        with self.assertRaises(OperationKnownFailureError):
            self.claim("176")

    def test_existing_own_ledger_cannot_be_overwritten_with_another_target(self):
        self.claim()
        with self.assertRaises(OperationKnownFailureError) as caught:
            self.claim(target={**self.target, "id": 89})
        self.assertEqual(caught.exception.code, "MINE_ALREADY_PENDING")
        self.assertEqual(self.facade._automation_pending_record("202", "minePendingGarrisonJson")["mineId"], 88)

    def test_different_server_can_dispatch_same_numeric_target(self):
        self.claim()
        self.claim("999")

    def test_known_preflight_failure_releases_target_but_unknown_keeps_it(self):
        self.facade._run_expedition_preflight.side_effect = OperationKnownFailureError("体力不足", code="EXPEDITION_ENERGY_NOT_READY")
        with self.assertRaises(OperationKnownFailureError):
            self.execute()
        self.assertTrue(self.facade._mine_target_available("176", self.target))
        def uncertain(execution, *_a, **_kw):
            execution.mark_request_sent({})
            raise OperationUncertainError("配兵未知")
        self.facade._run_expedition_preflight = uncertain
        with self.assertRaises(OperationUncertainError):
            self.execute()
        self.assertFalse(self.facade._mine_target_available("176", self.target))

    def test_accepted_target_cannot_be_reused_from_old_map_after_ledger_closes(self):
        self.observe()
        self.execute()
        self.facade._update_account_public_state("202", {"minePendingGarrisonJson": "{}"})
        self.assertFalse(self.facade._mine_target_available("176", self.target))
        self.clock.value += 1
        self.observe(playerOccupied=True)
        self.assertFalse(self.facade._mine_target_available("176", self.target))
        self.clock.value += 1
        self.observe(playerOccupied=False)
        self.assertTrue(self.facade._mine_target_available("176", self.target))

    def test_old_cloud_wait_cleared_without_touching_other_feature_or_resource_wait(self):
        wait = {"dependency": "cloud-map", "retryAtMillis": self.clock.value + 999999}
        state = {"mine": {"dependencyWait": wait, "lastState": "waiting-dependency",
                          "nextWakeAtMillis": self.clock.value + 999999},
                 "brush": {"dependencyWait": wait, "lastState": "waiting-dependency"}}
        result = resident_due_decision({"mine": {"enabled": True, "rows": [{"enabled": True}]}},
            state, now_millis=self.clock.value, saved_tasks_started=True, active_keys={"mine"}, priorities={})
        self.assertEqual(result["feature"], "mine")
        self.assertNotIn("dependencyWait", result["state"]["mine"])
        self.assertEqual(result["state"]["brush"]["dependencyWait"], wait)
        self.assertIn("dependencyWait", state["mine"], "pure reducer must not mutate input")

    def test_brush_pool_shared_across_filters_and_scoped_by_server(self):
        target = {"id": 42, "kind": "山贼", "x": 10, "y": 10, "level": 7,
                  "composition": {"foot": 1}, "dropCategories": ["宝物"]}
        self.facade._observe_local_map("176", "bandit", (10, 10), [target])
        args = {"kind": "BANDIT", "fingerprint": "different-filter", "ttl_millis": 1000}
        self.assertEqual(self.facade._local_brush_targets(account_ref="202", **args)[0]["id"], 42)
        self.assertEqual(self.facade._local_brush_targets(account_ref="999", **args), [])

    def test_real_mine_wire_scan_saves_unfiltered_typed_observations_for_peer(self):
        fixture = json.loads((ROOT / "shared_core/protocol_parity_fixtures.json").read_text())["fixtures"]["mineSearch8542Structured"]
        command = Mock(return_value={"packets": [{"opcode": 0x8542,
                                                  "payload": bytes.fromhex(fixture["responseHex"])}]})
        self.facade._execute_host_game_command = command
        # First account's SILVER filter matches neither returned mine.
        body = {**self.body, "accountRef": "176", "startX": 60, "startY": 24,
                "scope": "附近", "scanLimit": 1}
        result = self.facade._run_local_mine_search(FakeExecution(), body, {})
        self.assertEqual(result["count"], 0)
        rows = self.facade._local_map_store("202", "mine").targets(self.clock.value, 1000)
        self.assertEqual(len(rows), 2, "ownership and unmatched types must be shared too")
        self.assertIs(next(t for t in rows if t["id"] == 257)["playerOccupied"], True)
        # Peer's different filter reuses exactly that game observation.
        body.update(accountRef="202", resourceTypes=["PASTURE_LV2"], levels=[2])
        result = self.facade._run_local_mine_search(FakeExecution(), body, {})
        self.assertEqual([t["id"] for t in result["targets"]], [258])
        self.assertEqual(command.call_count, 1)

    def test_corrupt_peer_ledger_blocks_instead_of_assuming_target_is_free(self):
        self.facade._update_account_public_state("176", {"minePendingGarrisonJson": "{bad json"})
        with self.assertRaises(OperationKnownFailureError) as caught:
            self.execute()
        self.assertEqual(caught.exception.code, "MINE_LOCAL_LEDGER_INVALID")
        self.assertEqual(self.sent, [])

    def test_latest_occupied_map_blocks_stale_manual_target_even_without_consumption_history(self):
        self.observe(playerOccupied=True)
        with self.assertRaises(OperationKnownFailureError):
            self.execute()
        self.assertEqual(self.sent, [])

    def test_shared_map_invalidation_works_without_legacy_host_port(self):
        self.observe()
        self.assertTrue(self.facade._invalidate_map_snapshot_target("202", "mine", self.target, "gone"))
        self.assertEqual(self.facade._local_map_store("176", "mine").targets(self.clock.value, 1000), [])

    def test_mine_only_recovery_tick_retires_quota_wait_and_sends_no_cloud_calls(self):
        self.observe("202")
        configs = {"mine": {"enabled": True, "settings": {"centerX": 10, "centerY": 10},
                           "rows": [{"enabled": True, "resourceType": "SILVER", "level": 1,
                                     "scope": "定点", "x": 10, "y": 10, "generalIds": [7]}]}}
        self.facade._update_account_public_state("202", {
            "savedTasksStarted": "true", "activeResidentTaskKeys": "mine",
            "residentAutomationConfigJson": json.dumps(configs),
            "residentAutomationStateJson": json.dumps({"mine": {
                "lastState": "waiting-dependency", "nextWakeAtMillis": self.clock.value + 999999,
                "dependencyWait": {"dependency": "cloud-map", "retryAtMillis": self.clock.value + 999999}}})})
        result = self.facade._run_automation_recovery_tick(FakeExecution(), "202", {"allowedFeatures": ["mine"]})
        self.assertEqual(result["state"], "dispatched")
        state = json.loads(self.facade._account_public_state("202")["residentAutomationStateJson"])
        self.assertNotIn("dependencyWait", state["mine"])
        self.facade._cloud_presence_mode.assert_not_called()
        self.facade._cloud_map_exchange.assert_not_called()


if __name__ == "__main__":
    unittest.main()
