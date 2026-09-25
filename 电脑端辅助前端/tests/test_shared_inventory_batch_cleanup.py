from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core import CoreFacade
from dwpm_core.automation import CONTINUATION_STARVATION_MILLIS, resident_due_decision
from dwpm_core.features.inventory import (
    DEFAULT_EQUIPMENT_TEMPLATES,
    automatic_inventory_snapshot_is_complete,
    observe_automatic_inventory_action,
    parse_8104_inventory,
    plan_next_automatic_inventory_action,
)
from dwpm_core.local_views import project_success_records, resident_success_record
from dwpm_core.operations import OperationUncertainError
from dwpm_core.ports import PlatformPorts


class Clock:
    value = 80_000_000

    def now_millis(self):
        return self.value


class Execution:
    def __init__(self, number):
        self.operation_id = f"inventory-batch-{number}"
        self.sent = []

    def raise_if_cancelled(self):
        pass

    def mark_request_sent(self, metadata):
        self.sent.append(metadata)

    def publish_progress(self, *_args):
        pass


def utf(text):
    encoded = text.encode("utf-8")
    return struct.pack(">H", len(encoded)) + encoded


def equipment(instance_id, template_id=0, quality=0, **changes):
    template = DEFAULT_EQUIPMENT_TEMPLATES[template_id]
    return {
        **template,
        "instanceId": instance_id,
        "id": instance_id,
        "quality": quality,
        "qualityName": ["普通", "良好", "优秀", "卓越"][quality],
        "strengthen": 0,
        "extraText": "",
        "equipmentMetadataComplete": True,
        **changes,
    }


class BagServer:
    """Offline 0x1103/0x8103 server; no phone, HTTP or ADB access."""

    def __init__(self, owner):
        self.owner = owner
        self.equipment = []
        self.items = []
        self.commands = []
        self.reads = 0
        self.reject = set()
        self.uncertain = set()
        self.unchanged = set()
        self.bad_receipt = False
        self.bad_refresh = False
        self.command_millis = 100

    def payload(self):
        data = struct.pack(">qqH", 0, 0, len(self.items))
        for item in self.items:
            data += struct.pack(">HHq", item["itemId"], item["count"], 0)
        data += struct.pack(">H", len(self.equipment))
        for item in self.equipment:
            data += struct.pack(
                ">qHBBB HBBHHH",
                item["instanceId"], item["templateId"], 2,
                item["quality"], item["strengthen"], 10000, 0, 0, 0, 0, 20,
            ) + utf(item["extraText"])
        return data + struct.pack(">HHHB", 50, 500, 10, 5)

    def snapshot(self):
        return parse_8104_inventory(self.payload(), "fixture/0x8104")

    def refresh(self, *_args, **_kwargs):
        self.reads += 1
        snapshot = self.snapshot()
        if self.bad_refresh:
            snapshot.update(equipment=[], equipmentParseError="truncated")
        return snapshot

    def command(self, _account, opcode, payload, _phase, _context, *, mutation_sent):
        self.owner.assertTrue(mutation_sent)
        pending = self.owner.pending()
        self.owner.assertEqual(pending["actionState"], "sending")
        self.owner.assertTrue(pending["actionKey"])
        self.commands.append((opcode, payload, pending["actionKey"]))
        self.owner.clock.value += self.command_millis
        if opcode == 0x3144:
            item_id, count = struct.unpack(">HH", payload)
            row = next(row for row in self.items if row["itemId"] == item_id)
            row["count"] -= count
            self.items = [row for row in self.items if row["count"] > 0]
            return {"packets": [{"opcode": 0xA144, "payload": b"\x00" + utf("开启成功")}]}
        self.owner.assertEqual(opcode, 0x1103)
        kind, identifier, count, tail = struct.unpack(">Bqiq", payload)
        self.owner.assertEqual(tail, -1)
        if identifier in self.reject:
            return {"packets": [{"opcode": 0x8103, "payload": b"\x01" + utf("不能丢弃")}]}
        if identifier not in self.unchanged:
            if kind == 1:
                self.owner.assertEqual(count, 1)
                self.equipment = [row for row in self.equipment if row["instanceId"] != identifier]
            else:
                row = next(row for row in self.items if row["itemId"] == identifier)
                row["count"] -= count
                self.items = [row for row in self.items if row["count"] > 0]
        if identifier in self.uncertain:
            return {"packets": []}
        bag = self.payload() if not self.bad_receipt else b"\x00"
        return {"packets": [{"opcode": 0x8103, "payload": b"\x00" + utf("丢弃成功") + bag}]}


class InventoryBatchCleanupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.path = str(Path(self.directory.name) / "operations.json")
        self.facade = self.open_facade()
        self.facade.account_record_upsert({
            "accountRef": "404", "id": 404, "enabled": True, "loginState": "ONLINE",
            "session": {
                "accountId": 404, "sourceMode": 1,
                "publicState": {
                    "roleId": "404", "savedTasksStarted": "true",
                    "activeResidentTaskKeys": "inventory",
                },
            },
        })
        self.configure()
        self.server = BagServer(self)
        self.turn = 0

    def tearDown(self):
        self.facade.close()
        self.directory.cleanup()

    def open_facade(self):
        return CoreFacade(
            ROOT / "shared_core", self.path, ports=PlatformPorts(clock=self.clock)
        )

    def configure(self, **extra):
        self.facade.configure_resident_automation_from_habits("404", {
            "config": {
                "autoStart": False, "dailyTasks": {},
                "cleanInventory": True, "discardEquipment": True,
                "discardEquipmentQualities": ["普通", "良好", "优秀"],
                "maxEquipmentLevel": 36, "discardItemNames": ["山贼头巾"],
                **extra,
            },
        })
        self.facade.set_resident_automation_activation("404", True, ["inventory"])

    def public(self):
        return json.loads(self.facade.account_record_json("404"))["account"]["session"]["publicState"]

    def state(self):
        return json.loads(self.public()["residentAutomationStateJson"])["inventory"]

    def pending(self):
        return json.loads(self.public().get("inventoryPendingActionJson") or "{}")

    def records(self):
        return json.loads(self.public().get("successRecordsJson") or "[]")

    def tick(self, allowed=None):
        self.turn += 1
        with patch.object(self.facade, "_fresh_inventory_state", side_effect=self.server.refresh), \
                patch.object(self.facade, "_execute_host_game_command", side_effect=self.server.command):
            return self.facade._run_automation_recovery_tick(
                Execution(self.turn), "404", {"allowedFeatures": allowed or ["inventory"]}
            )

    def next_inventory_turn(self):
        self.clock.value = max(
            self.clock.value + 1000, int(self.state().get("nextWakeAtMillis") or 0)
        )
        return self.tick()

    def test_five_short_swords_drain_in_one_bounded_slice_and_group_honest_count(self):
        self.server.equipment = [equipment(900 + i) for i in range(5)]
        result = self.tick()
        self.assertEqual(len(self.server.commands), 5)
        self.assertEqual(len({row[2] for row in self.server.commands}), 5)
        self.assertEqual(self.server.reads, 1)  # Each complete discard receipt carries the next bag.
        self.assertEqual(self.server.equipment, [])
        self.assertEqual(self.pending(), {})
        self.assertEqual(self.public()["inventorySlotsUsed"], "0")
        self.assertEqual(self.public()["inventoryCapacity"], "50")
        presentation = json.loads(
            self.facade.account_record_presentation_json("404")
        )["account"]["session"]["publicState"]
        self.assertEqual(presentation["inventoryParserVersion"], "8104-trailer-v1")
        self.assertEqual(presentation["inventorySlotsUsed"], "0")
        self.assertIn("普通1级短剑 ×5", result["message"])
        self.assertEqual(len(self.records()), 5)  # Durable per-instance audit stays intact.
        page = self.facade.dispatch("GET", "/api/success-records", {"accountRef": "404"}).body
        self.assertEqual(len(page["entries"]), 1)
        entry = page["entries"][0]
        self.assertIn("普通1级短剑 已丢弃 ×5", entry["message"])
        self.assertEqual(entry["detail"]["actionCount"], 5)
        self.assertEqual(
            {row["action"]["instanceId"] for row in entry["detail"]["actions"]},
            set(range(900, 905)),
        )
        # Reading the grouped page must never compact the durable ledger.
        self.assertEqual(len(self.records()), 5)

    def test_live_case_shape_sixteen_eligible_and_one_protected_clears_in_slices(self):
        # 19:39 live evidence: 34 item stacks + 17 equipment = 51/50.
        templates = [42, 42, 40, 40, 40, 8, 32, 0, 0, 0, 0, 0, 9, 30, 30, 30]
        self.server.equipment = [
            equipment(900 + i, template_id, i % 3)
            for i, template_id in enumerate(templates)
        ] + [equipment(999, 13, 2)]  # Excellent Lv55 开山斧 must stay.
        self.server.items = [{"itemId": 1000 + i, "count": 1} for i in range(34)]
        self.assertEqual(self.server.snapshot()["slotsUsed"], 51)
        for _ in range(4):
            before = len(self.server.commands)
            self.tick()
            self.assertLessEqual(len(self.server.commands) - before, 5)
            self.clock.value += 10_000
        self.assertEqual([row["instanceId"] for row in self.server.equipment], [999])
        self.assertEqual(self.public()["inventorySlotsUsed"], "35")
        self.assertEqual(len(self.records()), 16)
        self.assertFalse(self.state()["continuationPending"])

    def test_time_budget_yields_before_second_command(self):
        self.server.equipment = [equipment(900 + i) for i in range(5)]
        self.server.command_millis = 5001
        self.tick()
        self.assertEqual(len(self.server.commands), 1)
        self.assertTrue(self.state()["continuationPending"])

    def test_known_rejection_skips_only_that_instance_and_keeps_audit(self):
        self.server.equipment = [equipment(900 + i) for i in range(4)]
        self.server.reject = {900}
        self.tick()
        self.assertEqual(len(self.server.commands), 4)
        self.assertEqual([row["instanceId"] for row in self.server.equipment], [900])
        self.assertEqual(len(self.records()), 3)
        self.assertEqual(self.pending(), {})
        rejected = json.loads(self.public()["inventoryLastRejectedActionJson"])
        self.assertEqual(rejected["action"]["instanceId"], 900)
        self.assertEqual(rejected["recoveryResolution"], "definitive-server-rejection")
        self.assertGreater(self.state()["nextWakeAtMillis"], self.clock.value + 60_000)

    def test_unknown_second_send_stops_batch_and_restart_observes_without_replay(self):
        self.server.equipment = [equipment(900 + i) for i in range(4)]
        self.server.uncertain = {901}
        with self.assertRaises(OperationUncertainError):
            self.tick()
        self.assertEqual(len(self.server.commands), 2)
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(self.pending()["action"]["instanceId"], 901)
        self.facade.close()
        self.facade = self.open_facade()
        self.clock.value += 60_001
        recovered = self.tick()
        self.assertTrue(recovered["recovered"])
        self.assertEqual(len(self.server.commands), 2)
        self.assertEqual(len(self.records()), 2)
        self.assertEqual(self.pending(), {})
        self.next_inventory_turn()
        self.assertEqual(len(self.server.commands), 4)
        self.assertEqual(self.server.equipment, [])
        self.assertEqual(len(self.records()), 4)

    def test_success_status_without_observed_removal_does_not_advance(self):
        self.server.equipment = [equipment(900), equipment(901)]
        self.server.unchanged = {900}
        result = self.tick()
        self.assertEqual(result["state"], "verifying")
        self.assertEqual(len(self.server.commands), 1)
        self.assertEqual(self.records(), [])
        self.assertEqual(self.pending()["action"]["instanceId"], 900)

    def test_contradicted_equipment_receipt_skips_that_piece_and_frees_the_rest(self):
        """成功 answered, instance still in the treasury after the window.

        An instance cannot be replenished, so the receipt is contradicted:
        no record, one send for that piece this sweep, and the next piece is
        reached in the same sweep instead of waiting on a human.
        """

        self.server.equipment = [equipment(900), equipment(901)]
        self.server.unchanged = {900}
        self.tick()
        self.clock.value += 60_001
        settled = self.tick()
        self.assertEqual(settled["state"], "retry")
        self.assertFalse(settled.get("requiresAttention", False))
        self.assertEqual(self.pending(), {})
        self.assertEqual(self.records(), [])
        unverified = json.loads(self.public()["inventoryLastUnverifiedActionJson"])
        self.assertEqual(unverified["recoveryResolution"], "receipt-contradicted")
        self.assertNotIn("requiresAttention", self.state())
        self.assertIn("discard-equipment:900", self.state()["cycleExcludedActions"])
        self.assertLessEqual(self.state()["nextWakeAtMillis"], self.clock.value + 1_000)
        # The sweep resumes on the feature's own next wake, not an hour later.
        self.next_inventory_turn()
        self.assertEqual([row["instanceId"] for row in self.server.equipment], [900])
        sent = [struct.unpack(">Bqiq", row[1])[1] for row in self.server.commands]
        self.assertEqual(sent, [900, 901])
        self.assertEqual([r["detail"]["action"]["instanceId"] for r in self.records()], [901])

    def test_replenishing_item_stack_settles_on_receipt_and_reaches_equipment(self):
        """The live shape: 山贼头巾 keeps dropping from 刷黄 while it is read.

        The server answers 成功 and the count never drops.  Before this fix
        the ledger froze 背包整理 for the account and no equipment behind the
        stack was ever discarded.  Now the window closes on the receipt, the
        stack sits out the sweep, and the equipment is cleared in the same
        sweep; the next sweep may try the stack once more.
        """

        self.server.items = [{"itemId": 4, "count": 45}]
        self.server.equipment = [equipment(900), equipment(901)]
        self.server.unchanged = {4}
        self.tick()
        self.assertEqual(self.pending()["action"]["kind"], "discard-item")
        self.server.items = [{"itemId": 4, "count": 90}]
        self.clock.value += 60_001
        settled = self.tick()
        self.assertEqual(settled["state"], "completed")
        self.assertFalse(settled["verified"])
        self.assertFalse(settled.get("requiresAttention", False))
        self.assertEqual(self.pending(), {})
        self.assertNotIn("requiresAttention", self.state())
        self.assertEqual(self.state()["cycleExcludedActions"], ["discard-item:4"])
        self.assertLessEqual(self.state()["nextWakeAtMillis"], self.clock.value + 1_000)
        self.next_inventory_turn()
        self.assertEqual(self.server.equipment, [])
        discards = [struct.unpack(">Bqiq", row[1])[:2] for row in self.server.commands]
        self.assertEqual(discards, [(0, 4), (1, 900), (1, 901)])
        records = self.records()
        by_kind = Counter(r["detail"]["action"]["kind"] for r in records)
        self.assertEqual(by_kind, {"discard-item": 1, "discard-equipment": 2})
        claimed = next(r for r in records if r["detail"]["action"]["kind"] == "discard-item")
        self.assertFalse(claimed["detail"]["verified"])
        self.assertEqual(claimed["detail"]["consumedCount"], 45)
        self.assertIn("背包数量未能核对", claimed["message"])
        self.assertTrue(all(
            r["detail"]["verified"] for r in records
            if r["detail"]["action"]["kind"] == "discard-equipment"
        ))
        # That sweep is over: the exclusion is forgotten with it, and the next
        # sweep - an hour on, not on a human - gives the stack one more send.
        self.assertTrue(self.state()["cycleFinished"])
        self.assertEqual(self.state()["cycleExcludedActions"], [])
        self.assertGreaterEqual(self.state()["nextWakeAtMillis"], self.clock.value + 3_600_000)
        self.next_inventory_turn()
        self.assertEqual(struct.unpack(">Bqiq", self.server.commands[-1][1])[:2], (0, 4))

    def test_malformed_inline_bag_falls_back_to_read_without_repeating_discard(self):
        self.server.equipment = [equipment(900)]
        self.server.bad_receipt = True
        self.tick()
        self.assertEqual(len(self.server.commands), 1)
        self.assertEqual(self.server.reads, 2)
        self.assertEqual(len(self.records()), 1)

    def test_incomplete_verification_cannot_prove_discard_or_send_next_piece(self):
        self.server.equipment = [equipment(900), equipment(901)]
        self.server.bad_receipt = True
        refresh_count = 0
        original = self.server.refresh

        def refresh(*args, **kwargs):
            nonlocal refresh_count
            refresh_count += 1
            self.server.bad_refresh = refresh_count > 1
            return original(*args, **kwargs)

        with patch.object(self.server, "refresh", side_effect=refresh):
            result = self.tick()
        self.assertEqual(result["state"], "verifying")
        self.assertEqual(len(self.server.commands), 1)
        self.assertEqual(self.records(), [])
        self.assertTrue(self.pending())

    def test_more_than_segment_limit_continues_without_resetting_open_budget(self):
        self.facade._behavior_contract["scheduler"]["inventoryMaxActionsPerCycle"] = 2
        self.facade._behavior_contract["scheduler"]["inventoryMaxOpenPerCycle"] = 3
        self.configure(
            autoOpenEnabled=True, autoOpenItemNames=["实木宝箱"],
            discardItemNames=["实木宝箱"],
        )
        self.server.items = [{"itemId": 53, "count": 10}]
        self.server.equipment = [equipment(900 + i) for i in range(6)]
        for _ in range(6):
            self.tick()
            self.clock.value += 10_000
            if self.state().get("cycleFinished"):
                break
        self.assertEqual(self.server.equipment, [])
        self.assertEqual(self.server.items, [{"itemId": 53, "count": 7}])
        opens = [row for row in self.server.commands if row[0] == 0x3144]
        self.assertEqual(len(opens), 1)
        self.assertEqual(struct.unpack(">HH", opens[0][1]), (53, 3))

    def test_replenished_item_stack_does_not_starve_equipment(self):
        self.server.items = [{"itemId": 4, "count": 10}]
        self.server.equipment = [equipment(900), equipment(901)]
        # Immediate replenishment is intentionally indistinguishable from
        # no consumption. Test the between-slice case, after verified clearing.
        self.facade._behavior_contract["scheduler"]["inventoryMaxActionsPerTick"] = 1
        self.tick()
        self.server.items = [{"itemId": 4, "count": 10}]
        self.next_inventory_turn()
        self.assertEqual(self.server.commands[-1][0], 0x1103)
        self.assertEqual(struct.unpack(">Bqiq", self.server.commands[-1][1])[0], 1)
        self.assertEqual(len(self.server.equipment), 1)

    def test_continuations_finish_while_high_priority_task_remains_due(self):
        self.server.equipment = [equipment(900 + i) for i in range(16)]
        public = self.public()
        configs = json.loads(public["residentAutomationConfigJson"])
        configs["common"].update({
            "autoStart": True, "dailyLimit": 500, "startHour": 0,
            "brush": {"rules": [{"enabled": True}]},
        })
        state = json.loads(public["residentAutomationStateJson"])
        state["brush"] = {
            "lastServedAtMillis": self.clock.value, "nextWakeAtMillis": self.clock.value
        }
        self.facade._update_account_public_state("404", {
            "residentAutomationConfigJson": json.dumps(configs),
            "residentAutomationStateJson": json.dumps(state),
            "activeResidentTaskKeys": "brushYellow,inventory",
        })
        selected = Counter()
        start = self.clock.value

        def brush(*_args, **_kwargs):
            return {
                "feature": "brush", "state": "waiting", "success": True,
                "nextWakeAtMillis": self.clock.value,
            }

        with patch.object(self.facade, "_run_configured_brush_tick", side_effect=brush):
            while self.clock.value - start < 60_000 and self.server.equipment:
                result = self.tick(["brush", "inventory"])
                selected[result["feature"]] += 1
                self.clock.value += 2000
        self.assertEqual(self.server.equipment, [])
        self.assertGreater(selected["brush"], 0)
        self.assertEqual(selected["inventory"], 4)

    def test_old_accepted_receipt_is_not_reused_after_restart(self):
        self.server.equipment = [equipment(900)]
        pending = {
            "actionKey": "old", "actionState": "accepted",
            "action": {"kind": "discard-equipment", "instanceId": 900},
            "verificationDeadlineMillis": self.clock.value + 60_000,
            "receipt": {"receipt": {"inventory": {"items": [], "equipment": []}}},
        }
        self.facade._update_account_public_state("404", {
            "inventoryPendingActionJson": json.dumps(pending),
        })
        result = self.tick()
        self.assertEqual(result["state"], "verifying")
        self.assertEqual(self.server.reads, 1)
        self.assertEqual(self.server.commands, [])
        self.assertEqual(self.records(), [])

    def test_confirmation_replayed_after_completion_does_not_increment_cycle_twice(self):
        self.server.equipment = [equipment(900)]
        self.facade._behavior_contract["scheduler"]["inventoryMaxActionsPerTick"] = 1
        self.tick()
        state = self.state()
        last = state["lastAction"]
        pending = {
            "actionKey": last["actionKey"], "action": last["action"],
            "cycleId": state["cycleId"], "configHash": state["configHash"],
            "cycleActionCount": 0, "cycleOpenedCount": 0,
        }
        self.facade._complete_automatic_inventory_action(
            "404", pending, self.server.snapshot(), last["observation"], recovered=True,
        )
        self.assertEqual(self.state()["cycleActionCount"], 1)
        self.assertEqual(len(self.records()), 1)


class InventoryBatchSafetyTests(unittest.TestCase):
    def test_record_grouping_never_merges_cycles_qualities_or_legacy_records(self):
        records = []
        for index, (cycle, quality) in enumerate(
            [("first", 0), ("first", 0), ("first", 1), ("next", 0), ("", 0)]
        ):
            record = resident_success_record({
                "feature": "inventory", "state": "completed", "success": True,
                "actionKey": f"action-{index}", "batchKey": f"batch-{index}",
                "cycleId": cycle, "consumedCount": 1,
                "action": {
                    "kind": "discard-equipment", "instanceId": 900 + index,
                    "itemName": "短剑", "level": 1, "quality": quality,
                    "qualityName": ["普通", "良好"][quality],
                },
            }, now_millis=index + 1)
            records.append(record)
        # Duplicate delivery from another projection source is not another piece.
        page = project_success_records({
            "accountRef": "404", "records": records + [records[0]], "limit": 50,
        })
        self.assertEqual(len(page["entries"]), 4)
        self.assertEqual(
            sum(row["detail"]["consumedCount"] for row in page["entries"]), 5
        )
        self.assertEqual(len(records[0]["detail"]["action"]), 6)
        self.assertNotIn("actions", records[0]["detail"])

    def test_zero_item_table_still_decodes_equipment_and_empty_capacity(self):
        # Zero stacks precede the equipment count; they are not a legacy layout.
        data = struct.pack(">qqHHHHHB", 0, 0, 0, 0, 50, 500, 10, 5)
        parsed = parse_8104_inventory(data)
        self.assertTrue(automatic_inventory_snapshot_is_complete(parsed))
        self.assertEqual(parsed["capacity"], 50)
        self.assertEqual(parsed["slotsUsed"], 0)

    def test_level_36_quality_and_protection_boundaries_remain_strict(self):
        safe = equipment(900)
        policy = {
            "cleanInventory": True, "discardEquipment": True,
            "discardEquipmentQualityCodes": [0, 1, 2], "maxEquipmentLevel": 36,
        }
        for quality in (0, 1, 2):
            bag = {"items": [], "equipment": [{**safe, "quality": quality, "level": 35}]}
            self.assertIsNotNone(plan_next_automatic_inventory_action(bag, policy)["action"])
        for change in (
            {"level": 36}, {"quality": 3}, {"famous": True},
            {"strengthen": 1}, {"extraText": "炼魂"},
        ):
            bag = {"items": [], "equipment": [{**safe, **change}]}
            self.assertIsNone(plan_next_automatic_inventory_action(bag, policy)["action"])

    def test_partial_snapshot_is_not_discard_confirmation(self):
        for bag in (
            {"items": [], "equipment": [], "equipmentParseError": "truncated"},
            {"items": [], "equipment": [], "declaredEquipmentCount": 1},
            {"items": [], "equipment": [], "itemCount": 1},
            {"items": [], "equipment": [], "layout": "legacy-scan-fallback"},
        ):
            self.assertFalse(automatic_inventory_snapshot_is_complete(bag))
            with self.assertRaises(ValueError):
                observe_automatic_inventory_action(
                    {"kind": "discard-equipment", "instanceId": 900}, bag
                )

    def test_continuation_priority_is_bounded_and_never_ignores_deadlines_or_attention(self):
        now = 80_000_000
        configs = {
            "domestic": {"active": True},
            "inventory": {"enabled": True},
        }
        state = {
            "domestic": {"lastServedAtMillis": now, "nextWakeAtMillis": now},
            "inventory": {
                "lastServedAtMillis": now - CONTINUATION_STARVATION_MILLIS,
                "nextWakeAtMillis": now, "lastState": "completed",
                "continuationPending": True,
            },
        }

        def decide():
            return resident_due_decision(
                configs, state, now_millis=now, saved_tasks_started=True,
                active_keys={"inventory", "domestic"},
                priorities={"domestic": 40, "inventory": 25},
            )["feature"]

        self.assertEqual(decide(), "inventory")
        state["inventory"]["lastServedAtMillis"] = now
        self.assertEqual(decide(), "domestic")
        state["inventory"]["lastServedAtMillis"] = now - CONTINUATION_STARVATION_MILLIS
        state["inventory"]["nextWakeAtMillis"] = now + 1
        self.assertEqual(decide(), "domestic")
        state["inventory"]["nextWakeAtMillis"] = now
        state["inventory"]["requiresAttention"] = True
        self.assertEqual(decide(), "domestic")
        # The old on-device in-progress cycle receives the same bounded
        # continuation treatment without an unsafe migration of its ledger.
        state["inventory"].pop("requiresAttention")
        state["inventory"].pop("continuationPending")
        state["inventory"]["cycleActionCount"] = 13
        self.assertEqual(decide(), "inventory")
        state["inventory"]["continuationPending"] = False
        self.assertEqual(decide(), "domestic")


if __name__ == "__main__":
    unittest.main()
