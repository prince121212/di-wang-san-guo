from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_auto_energy_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class AutoEnergyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_saved_configs = dict(SERVER.SAVED_CONFIGS)
        SERVER.SAVED_CONFIGS.clear()
        with SERVER.GENERAL_ENERGY_ACTION_LOCKS_LOCK:
            SERVER.GENERAL_ENERGY_ACTION_LOCKS.clear()

    def tearDown(self) -> None:
        SERVER.SAVED_CONFIGS.clear()
        SERVER.SAVED_CONFIGS.update(self.old_saved_configs)
        with SERVER.GENERAL_ENERGY_ACTION_LOCKS_LOCK:
            SERVER.GENERAL_ENERGY_ACTION_LOCKS.clear()

    @staticmethod
    def general(energy: int = 5) -> dict:
        return {
            "id": 101,
            "idHex": "0000000000000065",
            "name": "统弓2",
            "displayStatus": "闲",
            "statusText": "闲",
            "tili": energy,
            "energyReliable": True,
            "soldierTypeCode": 14,
            "soldierCount": 1433,
        }

    @staticmethod
    def formation() -> dict:
        return {
            "generalId": "101",
            "soldierType": "强弩兵",
            "soldierCount": 1433,
        }

    def test_dungeon_preflight_uses_common_auto_energy_before_the_mandatory_gate(self) -> None:
        sid = "dungeon-auto-energy"
        general = self.general(5)
        sess = {"sessionId": sid, "generals": [general]}
        SERVER.SAVED_CONFIGS[sid] = {
            "autoEnergy": True,
            "energyThreshold": 40,
        }
        task = {"taskId": "dungeon-task", "config": {"sessionId": sid}, "logs": []}

        with patch.object(
            SERVER,
            "heal_all_wounded_before_military_prepare",
            return_value={"success": True},
        ), patch.object(
            SERVER,
            "refresh_general_with_a110_status",
            return_value=general,
        ), patch.object(
            SERVER,
            "saved_formation_for_general",
            return_value=self.formation(),
        ), patch.object(
            SERVER,
            "refresh_inventory",
            return_value={"items": [{"itemId": 12, "count": 3}]},
        ), patch.object(
            SERVER,
            "execute_use_energy_item",
            return_value={"success": True},
        ) as use_item, patch.object(SERVER, "task_log") as task_log:
            selected = SERVER.prepare_military_generals(
                sess,
                ["101"],
                "副本",
                task=task,
            )

        self.assertEqual(55, selected[0]["tili"])
        use_item.assert_called_once_with(sess, "101", confirm="use-energy-item")
        self.assertTrue(any("自动加体完成" in call.args[1] for call in task_log.call_args_list))

    def test_current_common_setting_overrides_a_stale_running_task_snapshot(self) -> None:
        sid = "dynamic-auto-energy"
        general = self.general(30)
        sess = {"sessionId": sid, "generals": [general]}
        SERVER.SAVED_CONFIGS[sid] = {
            "autoEnergy": True,
            "energyThreshold": 40,
        }
        stale_task = {
            "taskId": "stale-task",
            "config": {"sessionId": sid, "autoEnergy": False, "energyThreshold": 20},
            "logs": [],
        }

        with patch.object(
            SERVER,
            "refresh_inventory",
            return_value={"items": [{"itemId": 12, "count": 1}]},
        ), patch.object(
            SERVER,
            "execute_use_energy_item",
            return_value={"success": True},
        ) as use_item, patch.object(SERVER, "task_log"):
            SERVER.ensure_general_energy_for_check(
                sess,
                general,
                "无损",
                task=stale_task,
            )

        self.assertEqual(80, general["tili"])
        use_item.assert_called_once()

    def test_all_standard_military_preflight_names_share_the_same_energy_policy(self) -> None:
        for index, action_name in enumerate(("副本", "无损", "掠夺", "打矿", "刷黄"), start=1):
            with self.subTest(action_name=action_name):
                sid = f"standard-energy-{index}"
                general = self.general(10)
                sess = {"sessionId": sid, "generals": [general]}
                SERVER.SAVED_CONFIGS[sid] = {
                    "autoEnergy": True,
                    "energyThreshold": 40,
                }
                with patch.object(
                    SERVER,
                    "heal_all_wounded_before_military_prepare",
                    return_value={"success": True},
                ), patch.object(
                    SERVER,
                    "refresh_general_with_a110_status",
                    return_value=general,
                ), patch.object(
                    SERVER,
                    "saved_formation_for_general",
                    return_value=self.formation(),
                ), patch.object(
                    SERVER,
                    "refresh_inventory",
                    return_value={"items": [{"itemId": 12, "count": 1}]},
                ), patch.object(
                    SERVER,
                    "execute_use_energy_item",
                    return_value={"success": True},
                ) as use_item, patch.object(SERVER, "account_log"):
                    selected = SERVER.prepare_military_generals(
                        sess,
                        ["101"],
                        action_name,
                    )

                self.assertEqual(60, selected[0]["tili"])
                use_item.assert_called_once_with(sess, "101", confirm="use-energy-item")

    def test_disabled_common_setting_does_not_consume_an_item(self) -> None:
        sid = "disabled-auto-energy"
        general = self.general(5)
        sess = {"sessionId": sid, "generals": [general]}
        SERVER.SAVED_CONFIGS[sid] = {
            "autoEnergy": False,
            "energyThreshold": 40,
        }

        with patch.object(
            SERVER,
            "heal_all_wounded_before_military_prepare",
            return_value={"success": True},
        ), patch.object(
            SERVER,
            "refresh_general_with_a110_status",
            return_value=general,
        ), patch.object(SERVER, "execute_use_energy_item") as use_item:
            with self.assertRaisesRegex(RuntimeError, "将领体力不足"):
                SERVER.prepare_military_generals(sess, ["101"], "副本")

        use_item.assert_not_called()

    def test_enabled_policy_reports_missing_energy_items_before_dispatch(self) -> None:
        sid = "missing-energy-item"
        general = self.general(5)
        sess = {"sessionId": sid, "generals": [general]}
        SERVER.SAVED_CONFIGS[sid] = {
            "autoEnergy": True,
            "energyThreshold": 40,
        }

        with patch.object(
            SERVER,
            "heal_all_wounded_before_military_prepare",
            return_value={"success": True},
        ), patch.object(
            SERVER,
            "refresh_general_with_a110_status",
            return_value=general,
        ), patch.object(
            SERVER,
            "refresh_inventory",
            return_value={"items": []},
        ):
            with self.assertRaisesRegex(RuntimeError, "宝库没有活血丹"):
                SERVER.prepare_military_generals(sess, ["101"], "打矿")

    def test_two_checks_of_the_same_general_do_not_double_consume(self) -> None:
        sid = "deduplicated-auto-energy"
        cached_general = self.general(5)
        stale_copy = dict(cached_general)
        sess = {"sessionId": sid, "generals": [cached_general]}
        SERVER.SAVED_CONFIGS[sid] = {
            "autoEnergy": True,
            "energyThreshold": 40,
        }

        with patch.object(
            SERVER,
            "refresh_inventory",
            return_value={"items": [{"itemId": 12, "count": 2}]},
        ), patch.object(
            SERVER,
            "execute_use_energy_item",
            return_value={"success": True},
        ) as use_item, patch.object(SERVER, "account_log"):
            SERVER.ensure_general_energy_for_check(sess, cached_general, "副本")
            SERVER.ensure_general_energy_for_check(sess, stale_copy, "掠夺")

        self.assertEqual(55, cached_general["tili"])
        self.assertEqual(55, stale_copy["tili"])
        self.assertEqual(1, use_item.call_count)


if __name__ == "__main__":
    unittest.main()
