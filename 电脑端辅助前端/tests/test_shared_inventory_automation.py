from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHARED_PYTHON = ROOT / "shared_core" / "python"
if str(SHARED_PYTHON) not in sys.path:
    sys.path.insert(0, str(SHARED_PYTHON))

from dwpm_core import CoreFacade  # noqa: E402
from dwpm_core.automation import resident_due_decision  # noqa: E402
from dwpm_core.features.inventory import (  # noqa: E402
    equipment_is_safe_to_discard,
    observe_automatic_inventory_action,
    plan_next_automatic_inventory_action,
)
from dwpm_core.operations import OperationKnownFailureError  # noqa: E402
from dwpm_core.ports import PlatformPorts  # noqa: E402


class FixedClock:
    def __init__(self, value: int = 80_000_000) -> None:
        self.value = value

    def now_millis(self) -> int:
        return self.value


class FakeExecution:
    operation_id = "op_inventory_fixture"

    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def mark_request_sent(self, metadata=None) -> None:
        self.sent.append(dict(metadata or {}))

    def publish_progress(self, _progress: int, _details=None) -> None:
        return None

    def raise_if_cancelled(self) -> None:
        return None

    def wait(self, _seconds: float) -> None:
        return None


def utf(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return len(encoded).to_bytes(2, "big") + encoded


def item(item_id: int, name: str, count: int) -> dict[str, object]:
    return {"itemId": item_id, "id": item_id, "name": name, "count": count}


def inventory(*items: dict[str, object], equipment=None) -> dict[str, object]:
    return {
        "items": [dict(value) for value in items],
        "equipment": [dict(value) for value in equipment or []],
        "capacity": 100,
        "sourceOpcode": "fixture/0x8104",
    }


class SharedInventoryPlanningTests(unittest.TestCase):
    def test_auto_open_honors_whitelist_key_and_fifty_item_limit(self) -> None:
        planned = plan_next_automatic_inventory_action(
            inventory(
                item(58, "青铜宝箱", 70),
                item(59, "青铜钥匙", 1),
                item(777, "非白名单礼包", 99),
            ),
            {
                "autoOpenEnabled": True,
                "autoOpenItemNames": ["非白名单礼包", "青铜宝箱"],
                "maxOpenPerCycle": 50,
                "maxActionsPerCycle": 50,
            },
        )

        self.assertEqual(planned["action"]["kind"], "open")
        self.assertEqual(planned["action"]["itemName"], "青铜宝箱")
        self.assertEqual(planned["action"]["requestedCount"], 1)

        without_key = plan_next_automatic_inventory_action(
            inventory(item(58, "青铜宝箱", 70)),
            {
                "autoOpenEnabled": True,
                "autoOpenItemNames": ["青铜宝箱"],
                "cleanInventory": True,
                "discardItemNames": ["青铜宝箱"],
                "maxOpenPerCycle": 50,
            },
        )
        self.assertIsNone(without_key["action"])

        batch = plan_next_automatic_inventory_action(
            inventory(item(53, "实木宝箱", 70)),
            {
                "autoOpenEnabled": True,
                "autoOpenItemNames": ["实木宝箱"],
                "maxOpenPerCycle": 50,
            },
        )
        self.assertEqual(batch["action"]["requestedCount"], 50)

    def test_opening_precedes_discard_and_planner_returns_one_action(self) -> None:
        planned = plan_next_automatic_inventory_action(
            inventory(
                item(700, "废弃材料", 8),
                item(95, "50两银票", 3),
            ),
            {
                "autoOpenEnabled": True,
                "autoOpenItemNames": ["50两银票"],
                "cleanInventory": True,
                "discardItemNames": ["废弃材料"],
            },
        )
        self.assertEqual(planned["action"]["kind"], "open")
        self.assertEqual(planned["action"]["itemId"], 95)
        self.assertNotIn("actions", planned)

        discard = plan_next_automatic_inventory_action(
            inventory(item(700, "废弃材料", 8)),
            {
                "cleanInventory": True,
                "discardItemNames": ["废弃材料"],
            },
        )
        self.assertEqual(discard["action"]["kind"], "discard-item")
        self.assertEqual(discard["action"]["requestedCount"], 8)

    def test_equipment_protection_and_incomplete_metadata_fail_closed(self) -> None:
        safe = {
            "instanceId": 901,
            "name": "短剑",
            "equipmentMetadataComplete": True,
            "famous": False,
            "strengthen": 0,
            "extraText": "",
            "level": 10,
            "quality": 0,
        }
        allowed, reason = equipment_is_safe_to_discard(
            safe, max_quality=1, max_level=20
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "")
        for patch, marker in (
            ({"famous": True}, "名将"),
            ({"strengthen": 1}, "强化"),
            ({"extraText": "炼魂"}, "炼魂"),
            ({"level": 80}, "80级"),
            ({"level": 20}, "等级"),
            ({"quality": 2}, "品质"),
        ):
            with self.subTest(patch=patch):
                protected, protected_reason = equipment_is_safe_to_discard(
                    {**safe, **patch}, max_quality=1, max_level=20
                )
                self.assertFalse(protected)
                self.assertIn(marker, protected_reason)

        with self.assertRaisesRegex(ValueError, "元数据不完整"):
            plan_next_automatic_inventory_action(
                inventory(
                    equipment=[{
                        **safe,
                        "instanceId": 902,
                        "equipmentMetadataComplete": False,
                    }]
                ),
                {
                    "cleanInventory": True,
                    "discardEquipment": True,
                    "maxEquipmentQualityCode": 1,
                    "maxEquipmentLevel": 20,
                },
            )

    def test_selected_qualities_are_a_set_not_a_ceiling(self) -> None:
        """普通+良好 both go; 优秀 stays; a gap in the set is honoured."""

        def piece(instance_id: int, quality: int) -> dict[str, object]:
            return {
                "instanceId": instance_id,
                "name": f"装备{instance_id}",
                "equipmentMetadataComplete": True,
                "famous": False,
                "strengthen": 0,
                "extraText": "",
                "level": 10,
                "quality": quality,
                "qualityName": ["普通", "良好", "优秀", "卓越"][quality],
            }

        rows = [piece(901, 2), piece(902, 1), piece(903, 0)]
        policy = {
            "cleanInventory": True,
            "discardEquipment": True,
            "maxEquipmentQualityCode": 1,
            "discardEquipmentQualityCodes": [0, 1],
            "maxEquipmentLevel": 20,
        }
        first = plan_next_automatic_inventory_action(inventory(equipment=rows), policy)
        self.assertEqual(first["action"]["kind"], "discard-equipment")
        self.assertEqual(first["action"]["instanceId"], 902)
        second = plan_next_automatic_inventory_action(
            inventory(equipment=[rows[0], rows[2]]), policy
        )
        self.assertEqual(second["action"]["instanceId"], 903)
        third = plan_next_automatic_inventory_action(
            inventory(equipment=[rows[0]]), policy
        )
        self.assertIsNone(third["action"])

        gapped = {**policy, "discardEquipmentQualityCodes": [0, 2]}
        allowed, _reason = equipment_is_safe_to_discard(
            piece(904, 1), max_quality=2, max_level=20, allowed_qualities=[0, 2]
        )
        self.assertFalse(allowed)
        picked = plan_next_automatic_inventory_action(
            inventory(equipment=[piece(905, 1), piece(906, 2)]), gapped
        )
        self.assertEqual(picked["action"]["instanceId"], 906)

        # An explicitly empty selection discards nothing, even with the switch on.
        nothing = plan_next_automatic_inventory_action(
            inventory(equipment=rows),
            {**policy, "discardEquipmentQualityCodes": []},
        )
        self.assertIsNone(nothing["action"])

        # Callers that never learned about sets keep the ceiling semantics.
        legacy = {k: v for k, v in policy.items() if k != "discardEquipmentQualityCodes"}
        self.assertEqual(
            plan_next_automatic_inventory_action(inventory(equipment=rows), legacy)["action"]["instanceId"],
            902,
        )

    def test_observation_accepts_partial_consumption_and_exact_equipment_loss(self) -> None:
        partial = observe_automatic_inventory_action(
            {
                "kind": "open",
                "itemId": 95,
                "requestedCount": 5,
                "beforeItemCount": 5,
            },
            inventory(item(95, "50两银票", 3)),
        )
        self.assertTrue(partial["applied"])
        self.assertEqual(partial["consumedCount"], 2)

        equipment_loss = observe_automatic_inventory_action(
            {"kind": "discard-equipment", "instanceId": 901},
            inventory(equipment=[]),
        )
        self.assertTrue(equipment_loss["applied"])
        self.assertEqual(equipment_loss["consumedCount"], 1)


class SharedInventoryFacadeTests(unittest.TestCase):
    def _facade(self):
        directory = tempfile.TemporaryDirectory()
        clock = FixedClock()
        facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(Path(directory.name) / "operations.json"),
            ports=PlatformPorts(clock=clock),
        )
        facade.account_record_upsert({
            "accountRef": "404",
            "id": 404,
            "enabled": True,
            "loginState": "ONLINE",
            "session": {
                "accountId": 404,
                "sourceMode": 1,
                "publicState": {
                    "roleId": "404",
                    "gameHttp": "https://fixture.invalid/game",
                    "lastValidatedAt": str(clock.value),
                    "savedTasksStarted": "true",
                    "activeResidentTaskKeys": "inventory",
                },
            },
        })
        facade.configure_resident_automation_from_habits(
            "404",
            {
                "config": {
                    "autoStart": False,
                    "healWounded": False,
                    "autoEnergy": False,
                    "foodToCopper": False,
                    "autoOpenEnabled": True,
                    "autoOpenItemNames": ["50两银票", "非白名单礼包"],
                    "cleanInventory": False,
                    "dailyTasks": {},
                }
            },
        )
        facade.set_resident_automation_activation(
            "404", True, ["inventory"]
        )
        return facade, clock, directory

    @staticmethod
    def _public(facade: CoreFacade) -> dict[str, object]:
        account = json.loads(facade.account_record_json("404"))["account"]
        return account["session"]["publicState"]

    def _inventory_policy(self, facade: CoreFacade, config: dict[str, object]) -> dict[str, object]:
        facade.configure_resident_automation_from_habits("404", {"config": config})
        stored = json.loads(str(self._public(facade)["residentAutomationConfigJson"]))
        return dict(stored["inventory"])

    def test_policy_projection_derives_the_set_from_a_legacy_ceiling(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            base = {
                "cleanInventory": True,
                "discardEquipment": True,
                "maxEquipmentLevel": 20,
                "dailyTasks": {},
            }
            legacy = self._inventory_policy(
                facade, {**base, "maxEquipmentQuality": "良好"}
            )
            self.assertEqual(legacy["discardEquipmentQualities"], ["普通", "良好"])
            self.assertEqual(legacy["discardEquipmentQualityCodes"], [0, 1])
            self.assertEqual(legacy["maxEquipmentQuality"], "良好")

            explicit = self._inventory_policy(
                facade,
                {
                    **base,
                    "maxEquipmentQuality": "良好",
                    "discardEquipmentQualities": ["优秀", "普通", "不存在的品质"],
                },
            )
            self.assertEqual(explicit["discardEquipmentQualities"], ["普通", "优秀"])
            self.assertEqual(explicit["discardEquipmentQualityCodes"], [0, 2])
            # The ceiling follows the highest selected quality for old readers.
            self.assertEqual(explicit["maxEquipmentQuality"], "优秀")

            empty = self._inventory_policy(
                facade, {**base, "discardEquipmentQualities": []}
            )
            self.assertEqual(empty["discardEquipmentQualityCodes"], [])
        finally:
            facade.close()
            directory.cleanup()

    def test_config_normalization_activation_and_priority_include_inventory(self) -> None:
        facade, clock, directory = self._facade()
        try:
            public = self._public(facade)
            config = json.loads(public["residentAutomationConfigJson"])
            self.assertTrue(config["inventory"]["enabled"])
            self.assertEqual(
                config["inventory"]["autoOpenItemNames"], ["50两银票"]
            )
            activation = facade.set_resident_automation_activation(
                "404", True, None
            )
            self.assertIn("inventory", activation["activeKeys"])

            decision = resident_due_decision(
                {
                    "domestic": {"active": True},
                    "inventory": {"enabled": True},
                },
                {},
                now_millis=clock.value,
                saved_tasks_started=True,
                active_keys={"domestic", "inventory"},
                priorities={"domestic": 40, "inventory": 25},
            )
            self.assertEqual(decision["feature"], "domestic")
            decision["state"]["domestic"]["nextWakeAtMillis"] = (
                clock.value + 60_000
            )
            inventory_due = resident_due_decision(
                {
                    "domestic": {"active": True},
                    "inventory": {"enabled": True},
                },
                decision["state"],
                now_millis=clock.value,
                saved_tasks_started=True,
                active_keys={"domestic", "inventory"},
                priorities={"domestic": 40, "inventory": 25},
            )
            self.assertEqual(inventory_due["feature"], "inventory")
        finally:
            facade.close()
            directory.cleanup()

    def test_tick_persists_sending_ledger_before_only_mutation_and_verifies(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            snapshots = iter([
                inventory(item(95, "50两银票", 3)),
                inventory(item(95, "50两银票", 1)),
            ])
            facade._fresh_inventory_state = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: next(snapshots),
                facade,
            )
            commands: list[tuple[int, bytes]] = []

            def command(
                self,
                _account,
                opcode,
                payload,
                _phase,
                _context,
                *,
                mutation_sent,
            ):
                pending = json.loads(
                    SharedInventoryFacadeTests._public(self)[
                        "inventoryPendingActionJson"
                    ]
                )
                if pending.get("actionState") != "sending":
                    raise AssertionError("inventory send boundary was not durable")
                if not mutation_sent:
                    raise AssertionError("inventory mutation flag must be true")
                commands.append((int(opcode), bytes(payload)))
                return {
                    "httpCode": 200,
                    "httpOk": True,
                    "packets": [{
                        "opcode": 0xA144,
                        "payload": b"\x00" + utf("开启成功"),
                    }],
                }

            facade._execute_host_game_command = types.MethodType(  # noqa: SLF001
                command, facade
            )
            execution = FakeExecution()
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                execution, "404", {"allowedFeatures": ["inventory"]}
            )

            self.assertEqual(result["feature"], "inventory")
            self.assertEqual(result["state"], "completed")
            self.assertEqual(result["consumedCount"], 2)
            self.assertEqual(commands, [(0x3144, bytes.fromhex("005f0003"))])
            self.assertEqual(len(execution.sent), 1)
            public = self._public(facade)
            self.assertEqual(public["inventoryPendingActionJson"], "{}")
            last = json.loads(public["inventoryLastActionJson"])
            self.assertEqual(last["observation"]["consumedCount"], 2)
        finally:
            facade.close()
            directory.cleanup()

    def test_sent_states_recover_by_read_only_refresh_without_replay(self) -> None:
        for action_state in ("sending", "uncertain", "accepted"):
            with self.subTest(action_state=action_state):
                facade, clock, directory = self._facade()
                try:
                    pending = {
                        "schemaVersion": 1,
                        "cycleId": "inventory:fixture",
                        "cycleActionCount": 0,
                        "cycleOpenedCount": 0,
                        "configHash": "fixture",
                        "actionState": action_state,
                        "verificationDeadlineMillis": clock.value + 60_000,
                        "action": {
                            "kind": "open",
                            "itemId": 95,
                            "itemName": "50两银票",
                            "requestedCount": 3,
                            "beforeItemCount": 3,
                        },
                    }
                    facade._update_account_public_state(  # noqa: SLF001
                        "404",
                        {"inventoryPendingActionJson": json.dumps(pending)},
                    )
                    facade._fresh_inventory_state = types.MethodType(  # noqa: SLF001
                        lambda _self, *_args, **_kwargs: inventory(
                            item(95, "50两银票", 2)
                        ),
                        facade,
                    )
                    facade._execute_host_game_command = types.MethodType(  # noqa: SLF001
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError("recovery must not replay mutation")
                        ),
                        facade,
                    )
                    execution = FakeExecution()
                    result = facade._run_automation_recovery_tick(  # noqa: SLF001
                        execution,
                        "404",
                        {"allowedFeatures": ["inventory"]},
                    )
                    self.assertEqual(result["state"], "completed")
                    self.assertEqual(result["consumedCount"], 1)
                    self.assertEqual(execution.sent, [])
                    self.assertEqual(
                        self._public(facade)["inventoryPendingActionJson"],
                        "{}",
                    )
                finally:
                    facade.close()
                    directory.cleanup()

    def test_pre_send_is_released_rejected_is_blocked_and_uncertain_times_out(self) -> None:
        facade, clock, directory = self._facade()
        try:
            base = {
                "schemaVersion": 1,
                "cycleId": "inventory:fixture",
                "cycleActionCount": 0,
                "cycleOpenedCount": 0,
                "configHash": "fixture",
                "verificationDeadlineMillis": clock.value + 60_000,
                "action": {
                    "kind": "open",
                    "itemId": 95,
                    "itemName": "50两银票",
                    "requestedCount": 3,
                    "beforeItemCount": 3,
                },
            }
            facade._update_account_public_state(  # noqa: SLF001
                "404",
                {"inventoryPendingActionJson": json.dumps({
                    **base, "actionState": "preparing",
                })},
            )
            released = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "404", {"allowedFeatures": ["inventory"]}
            )
            self.assertEqual(released["state"], "retry")
            self.assertEqual(
                self._public(facade)["inventoryPendingActionJson"], "{}"
            )

            facade._update_account_public_state(  # noqa: SLF001
                "404",
                {"inventoryPendingActionJson": json.dumps({
                    **base,
                    "actionState": "rejected",
                    "error": "服务器拒绝 fixture",
                })},
            )
            rejected = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "404", {"allowedFeatures": ["inventory"]}
            )
            self.assertEqual(rejected["state"], "retry")
            self.assertFalse(rejected["requiresAttention"])
            self.assertEqual(
                self._public(facade)["inventoryPendingActionJson"], "{}"
            )
            self.assertIn(
                "inventoryLastRejectedActionJson",
                self._public(facade),
            )

            facade._update_account_public_state(  # noqa: SLF001
                "404",
                {"inventoryPendingActionJson": json.dumps({
                    **base, "actionState": "uncertain",
                })},
            )
            facade._fresh_inventory_state = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: inventory(
                    item(95, "50两银票", 3)
                ),
                facade,
            )
            verifying = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "404", {"allowedFeatures": ["inventory"]}
            )
            self.assertEqual(verifying["state"], "verifying")
            self.assertFalse(verifying.get("requiresAttention", False))

            clock.value += 60_001
            timed_out = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "404", {"allowedFeatures": ["inventory"]}
            )
            self.assertEqual(timed_out["state"], "blocked")
            self.assertTrue(timed_out["requiresAttention"])
            self.assertNotEqual(
                self._public(facade)["inventoryPendingActionJson"], "{}"
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_expired_uncertain_inventory_yields_lane_to_other_residents(self) -> None:
        """An unresolved inventory read must not starve brush or dungeon.

        The discard request crossed the send boundary, so replaying it is
        forbidden.  That safety fact is feature-scoped, however: a read-only
        verification can be retried on its own cadence while unrelated
        resident work continues to use the account lane.
        """

        facade, clock, directory = self._facade()
        try:
            now = clock.value
            facade._update_account_public_state(  # noqa: SLF001
                "404",
                {
                    "savedTasksStarted": "true",
                    "activeResidentTaskKeys": "brushYellow,dungeon,inventory",
                    "residentAutomationConfigJson": json.dumps({
                        "schemaVersion": 2,
                        "common": {
                            "autoStart": True,
                            "startHour": 0,
                            "dailyLimit": 500,
                            "brush": {
                                "rules": [{"enabled": True}],
                            },
                        },
                        "dungeon": {
                            "enabled": True,
                            "rows": [{"enabled": True}],
                            "settings": {"dailyTimes": 999},
                        },
                        "inventory": {"enabled": True},
                    }),
                    "residentAutomationStateJson": json.dumps({
                        "brush": {"nextWakeAtMillis": now},
                        "dungeon": {"nextWakeAtMillis": now},
                        "inventory": {"nextWakeAtMillis": now},
                    }),
                    "inventoryPendingActionJson": json.dumps({
                        "schemaVersion": 1,
                        "actionState": "uncertain",
                        "verificationDeadlineMillis": now - 1,
                        "action": {
                            "kind": "discard-item",
                            "itemName": "山贼头巾",
                            "beforeItemCount": 210,
                        },
                    }),
                },
            )

            def offline(_self, *_args, **_kwargs):
                raise OperationKnownFailureError(
                    "网络超时",
                    code="GAME_TIMEOUT",
                )

            facade._fresh_inventory_state = types.MethodType(  # noqa: SLF001
                offline,
                facade,
            )
            selected: list[tuple[str, set[str]]] = []

            def resident_tick(
                _self,
                _execution,
                _account_ref,
                _configs,
                _state,
                context,
                *,
                feature,
            ):
                selected.append((feature, set(context.get("allowedFeatures") or [])))
                return {
                    "feature": feature,
                    "state": "waiting",
                    "success": True,
                    "message": f"{feature} fixture",
                    "nextWakeAtMillis": now + 60_000,
                }

            for feature in ("brush", "dungeon"):
                facade_method = types.MethodType(
                    lambda self, *args, _feature=feature, **kwargs: resident_tick(
                        self,
                        *args,
                        **kwargs,
                        feature=_feature,
                    ),
                    facade,
                )
                setattr(facade, f"_run_configured_{feature}_tick", facade_method)

            first = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "404",
                {"allowedFeatures": ["brush", "dungeon", "inventory"]},
            )
            self.assertEqual(first["feature"], "inventory")
            self.assertEqual(first["state"], "blocked")
            # The account remains immediately wakeable for due residents even
            # though the inventory result itself needs attention.
            self.assertEqual(first["nextWakeAtMillis"], now)

            second = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "404",
                {"allowedFeatures": ["brush", "dungeon", "inventory"]},
            )
            self.assertIn(second["feature"], {"brush", "dungeon"})
            self.assertIn("inventory", second["isolatedPendingFeatures"])
            self.assertIn("inventory", second["isolatedAttentionFeatures"])
            self.assertTrue(selected)
            self.assertNotIn("inventory", selected[-1][1])
            pending = json.loads(
                self._public(facade)["inventoryPendingActionJson"]
            )
            self.assertGreater(pending["nextPollAtMillis"], now)
        finally:
            facade.close()
            directory.cleanup()


class DesktopInventoryCutoverSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (
            ROOT / "电脑端辅助前端" / "server.py"
        ).read_text(encoding="utf-8")

    def test_desktop_inventory_task_is_only_a_shared_tick_wake_owner(self) -> None:
        start = self.source.split("def start_auto_inventory(", 1)[1].split(
            "def start_auto_ministry(", 1
        )[0]
        worker = self.source.split("def auto_inventory_worker(", 1)[1].split(
            "def start_auto_inventory(", 1
        )[0]
        self.assertIn("auto_brush_worker(task_id)", worker)
        self.assertIn('"type": "auto-inventory"', start)
        self.assertIn('RESIDENT_TASK_PRIORITIES["inventory"]', start)
        self.assertNotIn("post_game(", start)
        self.assertNotIn("execute_discard_inventory(", start)

    def test_desktop_default_tick_activation_and_pending_include_inventory(self) -> None:
        active = self.source.split(
            "def _desktop_active_shared_resident_keys(", 1
        )[1].split("def try_sync_shared_resident_automation(", 1)[0]
        pending = self.source.split("def _shared_resident_pending(", 1)[1].split(
            "def _shared_brush_mine_pending(", 1
        )[0]
        tick = self.source.split(
            "def execute_shared_resident_automation_tick(", 1
        )[1].split("def execute_shared_daily_automation_tick(", 1)[0]
        self.assertIn('task_type == "auto-inventory"', active)
        self.assertIn('keys.add("inventory")', active)
        self.assertIn('"inventoryPendingActionJson"', pending)
        self.assertIn('"domestic", "inventory", "alarm", "daily"', tick)

    def test_old_desktop_auto_open_function_has_no_production_caller(self) -> None:
        self.assertEqual(self.source.count("auto_open_inventory_items("), 1)
        settings_route = self.source.split(
            'if self.path == "/api/settings/save":', 1
        )[1].split("class ", 1)[0]
        self.assertIn("start_auto_inventory(sess, cfg)", settings_route)
        self.assertNotIn("target=auto_open_inventory_items", settings_route)


if __name__ == "__main__":
    unittest.main()
