from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core import CoreFacade
from dwpm_core.local_views import (
    SUCCESS_RECORD_MILITARY_CATEGORIES,
    food_to_copper_success_record,
    resident_success_record,
)
from dwpm_core.operations import OperationKnownFailureError, OperationUncertainError


class FakeExecution:
    operation_id = "politics-fixture"

    def raise_if_cancelled(self):
        pass

    def mark_request_sent(self, metadata):
        pass

    def publish_progress(self, progress, details=None):
        pass


class InventoryResourceRecordTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.operation_path = str(Path(self.directory.name) / "operations.json")
        self.facade = self._open_facade()
        self.facade.account_record_upsert({
            "accountRef": "404",
            "id": 404,
            "enabled": True,
            "loginState": "ONLINE",
            "session": {"accountId": 404, "publicState": {}},
        })

    def tearDown(self):
        self.facade.close()
        self.directory.cleanup()

    def _open_facade(self):
        return CoreFacade(ROOT / "shared_core", self.operation_path)

    def _records(self):
        public = json.loads(self.facade.account_record_json("404"))[
            "account"
        ]["session"]["publicState"]
        return json.loads(public.get("successRecordsJson") or "[]")

    def _exchange(self, reason="copper-floor", operation_id="politics-fixture"):
        execution = FakeExecution()
        execution.operation_id = operation_id
        return self.facade._run_heal_resource_exchange(
            execution, "404", 10_000, {}, reason=reason
        )

    def test_inventory_completion_records_all_three_kinds_in_politics(self):
        for kind, name, count, category, expected in (
            ("open", "实木宝箱", 2, "开箱", "实木宝箱 已开启 ×2"),
            ("discard-item", "山贼头巾", 50, "丢弃物品", "山贼头巾 已丢弃 ×50"),
            ("discard-equipment", "短剑", 1, "丢弃装备", "良好10级短剑 已丢弃 ×1"),
        ):
            with self.subTest(kind=kind):
                pending = {
                    "actionKey": kind,
                    "cycleId": "fixture",
                    "action": {
                        "kind": kind, "itemName": name,
                        "requestedCount": count + (1 if kind == "open" else 0),
                        "qualityName": "良好", "level": 10,
                    },
                }
                result = self.facade._complete_automatic_inventory_action(
                    "404", pending, {"items": [], "equipment": []},
                    {"applied": True, "consumedCount": count}, recovered=False,
                )
                record = result["successRecord"]
                self.assertEqual(record["category"], category)
                self.assertEqual(record["message"], expected)
                self.assertNotIn(category, SUCCESS_RECORD_MILITARY_CATEGORIES)
                self.assertIsNone(
                    self.facade._append_resident_success_record("404", result)
                )
                # Recovering the same durable action later must not duplicate
                # its receipt, even when the recovery wording differs.
                self.facade._complete_automatic_inventory_action(
                    "404", pending, {"items": [], "equipment": []},
                    {"applied": True, "consumedCount": count}, recovered=True,
                )
        self.assertEqual(len(self._records()), 3)
        page = self.facade.dispatch(
            "GET", "/api/success-records", {"accountRef": "404"}
        )
        self.assertEqual(page.status, 200)
        self.assertEqual(
            {row["category"] for row in page.body["entries"]},
            {"开箱", "丢弃物品", "丢弃装备"},
        )

    def test_inventory_does_not_record_unconfirmed_or_failed_results(self):
        base = {
            "feature": "inventory", "state": "completed", "success": True,
            "actionKey": "fixture", "consumedCount": 1,
            "action": {"kind": "open", "itemName": "实木宝箱"},
        }
        for changes in (
            {"state": "verifying"}, {"state": "waiting"},
            {"state": "blocked"}, {"success": False},
            {"consumedCount": 0}, {"consumedCount": -1},
            {"actionKey": ""}, {"action": {"kind": "unknown"}},
        ):
            with self.subTest(changes=changes):
                self.assertIsNone(resident_success_record(
                    {**base, **changes}, now_millis=1
                ))

    def test_inventory_record_survives_crash_before_pending_is_cleared(self):
        pending = {
            "actionKey": "interrupted-discard", "actionState": "accepted",
            "cycleId": "fixture", "cycleActionCount": 0,
            "action": {
                "kind": "discard-item", "itemId": 700, "itemName": "山贼头巾",
                "requestedCount": 3, "beforeItemCount": 3,
            },
        }
        self.facade._update_account_public_state(
            "404", {"inventoryPendingActionJson": json.dumps(pending)}
        )
        inventory = {"items": [], "equipment": []}
        update = self.facade._update_account_public_state

        def interrupted_update(account_ref, updates):
            if updates.get("inventoryPendingActionJson") == "{}":
                raise RuntimeError("fixture: interrupted before clearing pending")
            return update(account_ref, updates)

        with patch.object(self.facade, "_update_account_public_state", side_effect=interrupted_update):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                self.facade._complete_automatic_inventory_action(
                    "404", pending, inventory,
                    {"applied": True, "consumedCount": 3}, recovered=False,
                )
        self.assertEqual(len(self._records()), 1)
        self.facade.close()
        self.facade = self._open_facade()
        pending = self.facade._automation_pending_record("404", "inventoryPendingActionJson")
        with patch.object(self.facade, "_fresh_inventory_state", return_value=inventory):
            with patch.object(self.facade, "_execute_host_game_command", side_effect=AssertionError("must not replay")):
                result = self.facade._run_automatic_inventory_pending_recovery(
                    FakeExecution(), "404", pending, {}
                )
        self.assertEqual(result["state"], "completed")
        self.assertEqual(len(self._records()), 1)
        self.assertEqual(self._records()[0]["message"], "山贼头巾 已丢弃 ×3")

    def test_same_item_in_distinct_actions_is_not_deduplicated(self):
        base = {
            "feature": "inventory", "state": "completed", "success": True,
            "consumedCount": 1, "action": {"kind": "open", "itemName": "实木宝箱"},
        }
        for action_key in ("first", "second"):
            self.facade._append_resident_success_record(
                "404", {**base, "actionKey": action_key}
            )
        self.assertEqual(len(self._records()), 2)

    def test_exchange_records_every_caller_and_survives_restart(self):
        packet = {"opcode": 0x8152, "payload": b"\x00" + struct.pack(">qq", 3000, 90000)}
        with patch.object(self.facade, "_execute_host_game_command", return_value={"packets": [packet]}):
            for reason in ("domestic-resource-floor", "copper-floor", "heal-copper-recovery"):
                self.assertTrue(self._exchange(reason)["success"])
        records = self._records()
        self.assertEqual(len(records), 3)
        for record in records:
            self.assertEqual(record["category"], "转铜")
            self.assertEqual(record["message"], "10000粮换3000铜")
            self.assertNotIn(record["category"], SUCCESS_RECORD_MILITARY_CATEGORIES)
        self.facade.close()
        self.facade = self._open_facade()
        self.assertEqual(self._records(), records)
        page = self.facade.dispatch(
            "GET", "/api/success-records", {"accountRef": "404", "category": "转铜"}
        )
        self.assertEqual(len(page.body["entries"]), 3)
        # A repeated projection after a restart is a duplicate, not a new fact.
        duplicate = food_to_copper_success_record(
            {"success": True}, food_amount=10_000, operation_id="politics-fixture",
            exchange_key=records[1]["detail"]["exchangeKey"],
            reason="copper-floor", now_millis=1,
        )
        self.assertIsNone(self.facade._append_success_record("404", duplicate))
        with patch.object(self.facade, "_execute_host_game_command", return_value={"packets": [packet]}):
            self._exchange(operation_id="next-operation")
        self.assertEqual(len(self._records()), 4)

    def test_distinct_exchanges_with_same_reason_in_one_operation_are_all_recorded(self):
        packet = {"opcode": 0x8152, "payload": b"\x00"}
        with patch.object(self.facade, "_execute_host_game_command", return_value={"packets": [packet]}):
            first = self._exchange("heal-copper-recovery")
            second = self._exchange("heal-copper-recovery")
        self.assertNotEqual(first["exchangeKey"], second["exchangeKey"])
        self.assertEqual(len(self._records()), 2)

    def test_exchange_rejection_missing_and_empty_receipts_are_not_recorded(self):
        for packets, error in (
            ([], OperationUncertainError),
            ([{"opcode": 0x8152, "payload": b""}], OperationUncertainError),
            ([{"opcode": 0x8152, "payload": b"\xff"}], OperationKnownFailureError),
        ):
            with self.subTest(packets=packets):
                with patch.object(self.facade, "_execute_host_game_command", return_value={"packets": packets}):
                    with self.assertRaises(error):
                        self._exchange()
                self.assertEqual(self._records(), [])


if __name__ == "__main__":
    unittest.main()
