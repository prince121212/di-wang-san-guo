from __future__ import annotations

import copy
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core import CoreFacade
from dwpm_core.automation import FEATURE_LABELS
from dwpm_core.operations import OperationKnownFailureError, OperationUncertainError
from dwpm_core.ports import PlatformPorts
from dwpm_core.recovery_policy import (
    copper_recovery_food_amount,
    pending_business_progress,
    resource_wait_notices,
    resource_wait_result,
)
from test_shared_resident_automation import FixedClock, FakeExecution


class ResourceRecoveryPolicyTests(unittest.TestCase):
    def test_exchange_covers_the_quote_not_a_fixed_thirty_thousand(self):
        for copper, cost, food in (
            (0, 1, 10_000),
            (1_000, 10_000, 30_000),
            (1_000, 100_000, 330_000),
            (1_000, 100_001, 340_000),
            (10_000, 10_000, 100_000),  # explicit refusal contradicts quote
        ):
            with self.subTest(copper=copper, cost=cost):
                self.assertEqual(copper_recovery_food_amount(copper, cost), food)

    def test_resource_wait_is_bounded_and_keeps_one_notice_identity(self):
        previous = {}
        keys = set()
        now = 10_000_000
        for attempt, delay in enumerate((60, 120, 240, 480, 900, 900), 1):
            result = resource_wait_result(
                "brush", "TROOP_HEAL_COPPER_SHORTAGE", "铜钱不足",
                now_millis=now, previous=previous,
            )
            self.assertFalse(result["requiresAttention"])
            self.assertEqual(result["resourceWait"]["attempts"], attempt)
            self.assertEqual(result["taskNextWakeAtMillis"], now + delay * 1000)
            self.assertIn("其他任务继续运行", result["message"])
            previous = {"lastState": result["state"], "resourceWait": result["resourceWait"]}
            notices = resource_wait_notices({"brush": previous}, FEATURE_LABELS)
            self.assertEqual(notices[0]["severity"], "warning")
            self.assertEqual(notices[0]["feature"], "brushYellow")
            keys.add(notices[0]["key"])
            now = result["taskNextWakeAtMillis"]
        self.assertEqual(len(keys), 1)

    def test_only_a_confirmed_resource_failure_gets_resource_policy(self):
        self.assertIsNotNone(resource_wait_result(
            "brush", "TROOP_HEAL_REJECTED", "铜钱不足", now_millis=1000,
        ))
        for code, message in (
            ("TROOP_HEAL_REJECTED", "没有伤兵"),
            ("BRUSH_RECOVERY_STEP_REQUIRES_REVIEW", "铜钱不足后结果未知"),
            ("OPERATION_UNCERTAIN", "粮食转铜回执未确认"),
        ):
            self.assertIsNone(resource_wait_result(
                "brush", code, message, now_millis=1000,
            ))

    def test_stale_resource_metadata_cannot_hide_an_unknown_outcome(self):
        result = resource_wait_result(
            "brush", "TROOP_HEAL_COPPER_SHORTAGE", "铜钱不足", now_millis=1000,
        )
        self.assertEqual(resource_wait_notices({
            "brush": {"lastState": "uncertain", "resourceWait": result["resourceWait"]},
        }, FEATURE_LABELS), [])

    def test_observation_timestamps_are_not_business_progress_at_any_depth(self):
        before = {
            "sendState": "accepted",
            "isolatedAtMillis": 100,
            "recoveryProgress": {"healByFief": {"205": {
                "state": "rejected", "updatedAtMillis": 100,
                "reconciliation": {"observedAtMillis": 100},
            }}},
        }
        after = copy.deepcopy(before)
        after.update({
            "isolatedAtMillis": 200,
            "nextPollAtMillis": 500,
            "requiresAttention": True,
            "lastError": "same rejection",
            "resourceWait": {"attempts": 10},
        })
        after["recoveryProgress"]["healByFief"]["205"]["updatedAtMillis"] = 200
        after["recoveryProgress"]["healByFief"]["205"]["reconciliation"]["observedAtMillis"] = 200
        self.assertEqual(pending_business_progress(before), pending_business_progress(after))
        after["recoveryProgress"]["healByFief"]["205"]["state"] = "completed"
        self.assertNotEqual(pending_business_progress(before), pending_business_progress(after))


class SharedResourceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "operations.json"
        self.clock = FixedClock(1_789_600_000_000)
        self.facade = self._open()
        self.facade.account_record_upsert({
            "accountRef": "202", "id": 202, "enabled": True, "loginState": "ONLINE",
            "session": {"accountId": 202, "sourceMode": 1, "publicState": {
                "roleId": "202", "gameHttp": "https://fixture.invalid/game",
                "lastValidatedAt": str(self.clock.value),
                "savedTasksStarted": "true", "activeResidentTaskKeys": "brushYellow,mine",
            }},
        })
        configs = {
            "common": {"autoStart": True, "dailyLimit": 500, "brush": {"rules": [
                {"enabled": True, "generalIds": [7], "level": 1},
            ]}},
            "mine": {"enabled": True, "rows": [
                {"enabled": True, "generalIds": [7], "resourceType": "银矿", "level": 1},
            ]},
        }
        self.facade._update_account_public_state("202", {
            "residentAutomationConfigJson": json.dumps(configs),
        })
        self.copper = 1_000
        self.food = 1_000_000
        self.cost = 100_000
        self.heal_statuses = [-1, 0]
        self.exchange_status = 0
        self.exchange_missing = False
        self.exchange_balances = True
        self.pre_missing = False
        self.invalid_balances = False
        self.commands = []
        self._install_transport()

    def _open(self):
        return CoreFacade(
            shared_root=ROOT / "shared_core", operation_store_path=str(self.path),
            ports=PlatformPorts(clock=self.clock),
        )

    def tearDown(self):
        self.facade.close()
        self.directory.cleanup()

    def _state_hex(self):
        if self.invalid_balances:
            return "00"
        fixtures = json.loads((ROOT / "shared_core/protocol_parity_fixtures.json").read_text())["fixtures"]
        head = bytearray.fromhex(fixtures["roleHead8004"]["responseHex"])
        offset = 20 + int.from_bytes(head[18:20], "big") + 2
        struct.pack_into(">qq", head, offset, self.copper, self.food)
        return head.hex()

    def _install_transport(self):
        general = {
            "id": 7, "name": "将领7", "status": 0, "displayStatus": "闲",
            "statusText": "闲", "fiefId": 205, "placeID": 205,
            "energyReliable": True, "tili": 300, "tiliLimit": 300,
            "soldierTypeCode": 3, "soldierCount": 100, "currentSoldierCount": 100,
        }
        self.facade._fresh_formation_state = lambda *_a, **_k: (
            self._state_hex(), [dict(general)], [],
        )
        self.facade._persist_automation_general_snapshot = lambda *_a, **_k: None
        self.facade._cloud_presence_mode = lambda *_a, **_k: "local"
        self.facade._execute_host_game_command = self._command
        self.facade._run_configured_mine_tick = lambda *_a, **_k: {
            "feature": "mine", "state": "completed", "success": True,
            "message": "sibling ran", "nextWakeAtMillis": self.clock.value + 30_000,
        }

    def _command(self, _account, opcode, payload, _phase, _context, **_kwargs):
        self.commands.append((opcode, payload))
        if opcode == 0x1231:
            if self.pre_missing:
                return {"packets": []}
            response = struct.pack(">qhqq", 205, -1, self.cost, 0)
        elif opcode == 0x1230:
            status = self.heal_statuses.pop(0) if len(self.heal_statuses) > 1 else self.heal_statuses[0]
            response = struct.pack(">bqqB", status, 1, 2, 0)
        elif opcode == 0x1152:
            if self.exchange_missing:
                return {"packets": []}
            response = struct.pack(">b", self.exchange_status)
            if self.exchange_status == 0 and self.exchange_balances:
                amount = struct.unpack(">Bq", payload)[1]
                response += struct.pack(">qq", self.copper + amount * 3 // 10, self.food - amount)
        else:
            self.fail(f"Unexpected real command: {opcode:#x}")
        return {"packets": [{"opcode": opcode + 0x7000, "payload": response}]}

    def _heal(self, **body):
        return self.facade._run_troop_heal_game_workflow(FakeExecution(), {
            "accountRef": "202", "confirm": "heal-wounded", "generalId": 7,
            "fiefId": 205, "soldierType": "轻骑兵", "woundedCount": 7,
            "foodToCopper": False, **body,
        }, {})

    def _pending(self):
        return self.facade._automation_pending_record("202", "brushPendingRecoveryJson")

    def _seed_old_rejected_heal(self):
        self.facade._save_automation_pending_record("202", "brushPendingRecoveryJson", {
            "generalIds": [7], "generalFacts": [{"id": 7, "fiefId": 205}],
            "createdAtMillis": self.clock.value - 86_400_000,
            "sendState": "accepted", "preDispatchMutationState": "accepted",
            "battleId": 77, "sawBusy": True, "healWounded": True,
            "foodToCopper": False, "requiresAttention": True,
            "isolatedAtMillis": self.clock.value - 60_000,
            "formations": [{"generalId": "7", "soldierType": "轻骑兵", "soldierCount": 100}],
            "recoveryProgress": {
                "healByFief": {"205": {
                    "state": "rejected", "code": "TROOP_HEAL_REJECTED",
                    "message": "铜钱不足", "updatedAtMillis": self.clock.value - 86_400_000,
                }},
                "formationByGeneral": {"7": {"state": "completed"}},
            },
        })

    def _tick(self):
        return self.facade._run_automation_recovery_tick(
            FakeExecution(), "202", {"allowedFeatures": ["brush", "mine"]},
        )

    def test_copper_rejection_exchanges_the_quote_then_heals_only_once_more(self):
        result = self._heal()
        self.assertTrue(result["result"]["success"])
        self.assertEqual([x[0] for x in self.commands], [0x1231, 0x1230, 0x1152, 0x1231, 0x1230])
        self.assertEqual(struct.unpack(">Bq", self.commands[2][1]), (1, 330_000))

    def test_repeated_copper_rejection_never_loops_inside_one_tick(self):
        self.heal_statuses = [-1]
        with self.assertRaises(OperationKnownFailureError) as caught:
            self._heal()
        self.assertEqual(caught.exception.code, "TROOP_HEAL_COPPER_SHORTAGE")
        self.assertIn("已尝试粮食转铜", str(caught.exception))
        self.assertEqual([x[0] for x in self.commands].count(0x1152), 1)
        self.assertEqual([x[0] for x in self.commands].count(0x1230), 2)

    def test_failed_exchange_is_known_and_does_not_retry_healing(self):
        self.exchange_status = -1
        with self.assertRaises(OperationKnownFailureError) as caught:
            self._heal()
        self.assertEqual(caught.exception.code, "TROOP_HEAL_RESOURCE_EXCHANGE_REJECTED")
        self.assertIn("粮食转铜失败", str(caught.exception))
        self.assertEqual([x[0] for x in self.commands], [0x1231, 0x1230, 0x1152])

    def test_zero_and_unparseable_food_never_authorize_an_exchange(self):
        for invalid, code in (
            (False, "TROOP_HEAL_RECOVERY_FOOD_SHORTAGE"),
            (True, "TROOP_HEAL_RESOURCE_STATE_UNAVAILABLE"),
        ):
            with self.subTest(invalid=invalid):
                self.food = 0
                self.invalid_balances = invalid
                self.commands.clear()
                self.heal_statuses = [-1]
                with self.assertRaises(OperationKnownFailureError) as caught:
                    self._heal()
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn(0x1152, [x[0] for x in self.commands])

    def test_success_only_exchange_receipt_deducts_confirmed_food(self):
        self.copper, self.food, self.cost = 0, 40_000, 15_000
        self.exchange_balances = False
        with self.assertRaises(OperationKnownFailureError) as caught:
            self._heal(foodToCopper=True, copperFloorWan=1)
        self.assertEqual(caught.exception.code, "TROOP_HEAL_RECOVERY_FOOD_SHORTAGE")
        self.assertEqual(caught.exception.details["currentFood"], 0)
        self.assertEqual([x[0] for x in self.commands], [0x1152, 0x1231, 0x1230])

    def test_read_failure_after_confirmed_exchange_is_not_an_unknown_send(self):
        self.copper = 0
        self.pre_missing = True
        with self.assertRaises(OperationKnownFailureError) as caught:
            self._heal(foodToCopper=True, copperFloorWan=1)
        self.assertEqual(caught.exception.code, "TROOP_HEAL_PREINFO_MISSING")
        self.assertEqual([x[0] for x in self.commands], [0x1152, 0x1231])

    def test_phone_shaped_rejection_recovers_and_clears_its_pending(self):
        self._seed_old_rejected_heal()
        result = self._tick()
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["feature"], "brushYellow")
        self.assertEqual(self._pending(), {})
        self.assertIn(0x1152, [x[0] for x in self.commands])

    def test_failure_yields_both_scheduler_entries_and_survives_restart(self):
        self._seed_old_rejected_heal()
        self.exchange_status = -1
        first = self._tick()
        self.assertEqual(first["state"], "waiting-resources")
        self.assertEqual(first["taskNextWakeAtMillis"], self.clock.value + 60_000)
        self.assertLessEqual(first["nextWakeAtMillis"], self.clock.value)
        self.assertFalse(first["requiresAttention"])
        self.assertEqual(self._pending()["nextPollAtMillis"], first["taskNextWakeAtMillis"])
        self.assertNotIn("isolatedAtMillis", self._pending())
        notice = self.facade.resident_resource_notices("202")["notices"][0]
        self.assertIn("粮食转铜失败", notice["message"])

        self.facade.close()
        self.facade = self._open()
        self._install_transport()
        self.assertEqual(self.facade.resident_resource_notices("202")["notices"][0]["key"], notice["key"])
        commands_before = len(self.commands)
        sibling = self._tick()
        self.assertEqual(sibling["feature"], "mine")
        self.assertIn("brush", sibling["isolatedPendingFeatures"])
        self.assertNotIn("brush", sibling.get("isolatedAttentionFeatures", []))
        self.assertEqual(len(self.commands), commands_before)

        self.clock.value = first["taskNextWakeAtMillis"]
        self.heal_statuses = [-1]
        second = self._tick()
        self.assertEqual(second["taskNextWakeAtMillis"], self.clock.value + 120_000)
        self.assertEqual(self.facade.resident_resource_notices("202")["notices"][0]["key"], notice["key"])

        self.clock.value = second["taskNextWakeAtMillis"]
        self.exchange_status = 0
        self.heal_statuses = [-1, 0]
        self.assertEqual(self._tick()["state"], "completed")
        self.assertEqual(self.facade.resident_resource_notices("202")["notices"], [])

    def test_unknown_exchange_is_attributed_without_clearing_send_evidence(self):
        self._seed_old_rejected_heal()
        self.exchange_status = -1
        first = self._tick()
        self.clock.value = first["taskNextWakeAtMillis"]
        self.exchange_missing = True
        self.heal_statuses = [-1]
        with self.assertRaises(OperationUncertainError) as caught:
            self._tick()
        self.assertEqual(caught.exception.details["feature"], "brushYellow")
        pending = self._pending()
        self.assertEqual(pending["recoveryProgress"]["healByFief"]["205"]["state"], "uncertain")
        self.assertGreater(pending["nextPollAtMillis"], self.clock.value)
        self.assertEqual(self.facade.resident_resource_notices("202")["notices"], [])
        command_count = len(self.commands)
        self.assertEqual(self._tick()["feature"], "mine")
        self.assertEqual(len(self.commands), command_count)

    def test_configured_unknown_outcome_replaces_stale_resource_notice(self):
        previous = resource_wait_result(
            "mine", "TROOP_HEAL_COPPER_SHORTAGE", "铜钱不足",
            now_millis=self.clock.value - 60_000,
        )
        self.facade._apply_resident_result_state("202", previous)

        def unknown(*_args, **_kwargs):
            raise OperationUncertainError("粮食转铜请求已发送，回执丢失")

        self.facade._run_configured_mine_tick = unknown
        with self.assertRaises(OperationUncertainError) as caught:
            self.facade._run_configured_resident_tick(
                FakeExecution(), "202", {"allowedFeatures": ["mine"]},
            )
        self.assertEqual(caught.exception.details["feature"], "mine")
        self.assertEqual(self.facade.resident_resource_notices("202")["notices"], [])

    def test_repeated_known_block_without_business_progress_cannot_monopolize(self):
        self._seed_old_rejected_heal()
        calls = []

        def blocked(*_args, **_kwargs):
            calls.append(1)
            raise OperationKnownFailureError(
                "不能自动重放", code="BRUSH_RECOVERY_STEP_REQUIRES_REVIEW",
            )

        self.facade._run_brush_recovery_game_workflow = blocked
        features = []
        for _ in range(6):
            features.append(self._tick()["feature"])
            self.clock.value += 2000
        self.assertLessEqual(len(calls), 2)
        self.assertIn("mine", features)
        self.assertGreater(self._pending()["nextPollAtMillis"], self.clock.value)

    def test_unknown_durable_step_is_never_directly_replayed(self):
        for state in ("sending", "uncertain"):
            pending = {"recoveryProgress": {"healByFief": {"205": {"state": state}}}}
            with self.assertRaises(OperationKnownFailureError):
                self.facade._run_durable_brush_recovery_step(
                    FakeExecution(), "202", pending, "healByFief", "205",
                    lambda _execution: self.fail("unknown send replayed"),
                )

    def test_general_heal_resource_rejection_is_reassessed_not_reported_completed(self):
        pending = {"maintenanceProgress": {"healByFief": {"205": {
            "state": "rejected", "code": "TROOP_HEAL_REJECTED", "message": "铜钱不足",
        }}}}
        result = self.facade._run_durable_general_maintenance_step(
            FakeExecution(), "202", pending, "healByFief", "205",
            lambda execution: self.facade._run_troop_heal_game_workflow(execution, {
                "accountRef": "202", "generalId": 7, "fiefId": 205,
                "healAllIfCountUnknown": True, "foodToCopper": False,
            }, {}),
        )
        self.assertTrue(result["result"]["success"])
        self.assertIn(0x1152, [row[0] for row in self.commands])
        self.assertEqual(pending["maintenanceProgress"]["healByFief"]["205"]["state"], "completed")

    def test_rejected_reconciliation_attempt_can_retry_but_unknown_attempt_cannot(self):
        for state in ("rejected", "sending", "uncertain"):
            with self.subTest(state=state):
                self.commands.clear()
                pending = {"recoveryProgress": {"healByFief": {"205": {
                    "state": "archived-uncertain",
                    "reconciliation": {"maintenanceAttempt": {"state": state}},
                }}}}
                calls = []
                action = lambda _execution: (
                    calls.append(1) or {"success": True, "message": "fresh maintenance"}
                )
                if state == "rejected":
                    result = self.facade._reconcile_uncertain_brush_heal_step(
                        FakeExecution(), "202", pending, "205", 205, action, {},
                    )
                    self.assertTrue(result["success"])
                    self.assertEqual(len(calls), 1)
                    self.assertEqual([row[0] for row in self.commands], [0x1231])
                else:
                    with self.assertRaises(OperationKnownFailureError):
                        self.facade._reconcile_uncertain_brush_heal_step(
                            FakeExecution(), "202", pending, "205", 205, action, {},
                        )
                    self.assertEqual(calls, [])
                    self.assertEqual(self.commands, [])

    def test_resource_wait_is_narrated_on_edges_not_every_retry(self):
        lines = []
        self.facade._write_user_log = lambda _account, line: lines.append(line)
        first = resource_wait_result(
            "brush", "TROOP_HEAL_COPPER_SHORTAGE", "铜钱不足", now_millis=self.clock.value,
        )
        self.facade._apply_resident_result_state("202", first)
        self.clock.value = first["taskNextWakeAtMillis"]
        second = resource_wait_result(
            "brush", "TROOP_HEAL_COPPER_SHORTAGE", "铜钱仍不足",
            now_millis=self.clock.value, previous={"resourceWait": first["resourceWait"]},
        )
        self.facade._apply_resident_result_state("202", second)
        self.assertEqual(len(lines), 1)
        self.assertIn("等待资源", lines[0])
        self.facade._apply_resident_result_state("202", {
            "feature": "brush", "state": "completed", "success": True,
        })
        self.assertEqual(lines[-1], "刷黄已恢复运行")

    def test_android_submission_retains_result_until_acknowledged(self):
        submission = self.facade.submit_automation_recovery_tick(
            "202", tick_key="android-handover",
            request_context={"source": "android-resident-scheduler", "allowedFeatures": ["mine"]},
        )
        operation_id = submission["operationId"]
        operation = self.facade.operation_status(operation_id, wait_millis=2000)["operation"]
        self.assertEqual(operation["status"], "SUCCEEDED")
        self.assertTrue(operation["resultRetained"])
        self.assertEqual(operation["resultRetentionKey"], "android-resident:202")
        acknowledged = json.loads(self.facade.acknowledge_resident_operation_json("202", operation_id))
        self.assertTrue(acknowledged["acknowledged"])
        self.assertFalse(self.facade.operation_status(operation_id)["operation"]["resultRetained"])
        self.assertEqual(
            self.facade.operation_status("nonexistent")["errorCode"], "OPERATION_NOT_FOUND",
        )


if __name__ == "__main__":
    unittest.main()
