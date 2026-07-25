from __future__ import annotations

import importlib.util
import struct
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_daily_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


def packet(opcode: int, payload: bytes) -> dict:
    return {"opcode": opcode, "payload": payload, "len": len(payload), "frag": 0}


class DailyInventoryProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sess = {
            "sessionId": "test-session",
            "gameHttp": "http://game",
            "dm": 123,
            "role": {"roleId": 1},
            "area": {"areaId": 351},
            "username": "1608601",
        }

    def test_use_item_matches_captured_3144_shape(self) -> None:
        calls = []

        def fake_post(_url, commands, _dm, account_id=None):
            calls.append((commands, account_id))
            return 200, b"", [packet(0xA144, b"\x00" + SERVER.utf("开启成功"))]

        with patch.object(SERVER, "post_game", side_effect=fake_post):
            result = SERVER.use_inventory_item(self.sess, 0x63, 1, item_name="惊喜宝箱")

        self.assertTrue(result["success"])
        self.assertEqual(calls[0][0], [(0x3144, struct.pack(">HH", 0x63, 1))])
        self.assertEqual(calls[0][1], "test-session")

    def test_use_item_supports_captured_batch_count(self) -> None:
        calls = []

        def fake_post(_url, commands, _dm, account_id=None):
            calls.append((commands, account_id))
            return 200, b"", [packet(
                0xA144,
                b"\x00" + SERVER.utf("铜钱辎重+1;兵书+1;青铜钥匙+1;"),
            )]

        with patch.object(SERVER, "post_game", side_effect=fake_post):
            result = SERVER.use_inventory_item(
                self.sess,
                0x63,
                3,
                item_name="惊喜宝箱",
            )

        self.assertTrue(result["success"])
        self.assertEqual(calls[0][0], [
            (0x3144, struct.pack(">HH", 0x63, 3)),
        ])
        self.assertEqual(result["count"], 3)

    def test_auto_open_batches_up_to_fifty_items_in_one_request(self) -> None:
        before = {
            "items": [
                {"itemId": 53, "name": "实木宝箱", "count": 99},
            ],
        }
        after = {
            "items": [
                {"itemId": 53, "name": "实木宝箱", "count": 49},
            ],
        }
        with (
            patch.object(
                SERVER,
                "refresh_inventory",
                side_effect=[before, after],
            ),
            patch.object(
                SERVER,
                "use_inventory_item",
                return_value={
                    "success": True,
                    "itemId": 53,
                    "itemName": "实木宝箱",
                    "count": 50,
                    "message": "铜钱+50000",
                },
            ) as use_item,
            patch.object(SERVER, "account_log") as account_log,
            patch.object(SERVER.time, "sleep"),
        ):
            result = SERVER.auto_open_inventory_items(
                self.sess,
                ["实木宝箱"],
            )

        use_item.assert_called_once_with(
            self.sess,
            53,
            50,
            item_name="实木宝箱",
        )
        self.assertEqual(result["opened"], 50)
        self.assertEqual(result["attempted"], 50)
        self.assertTrue(result["limited"])
        self.assertIn("实木宝箱 ×50", account_log.call_args.args[1])

    def test_auto_open_counts_partial_batch_from_inventory_delta(self) -> None:
        before = {
            "items": [
                {"itemId": 99, "name": "惊喜宝箱", "count": 7},
            ],
        }
        after = {
            "items": [
                {"itemId": 99, "name": "惊喜宝箱", "count": 5},
            ],
        }
        with (
            patch.object(
                SERVER,
                "refresh_inventory",
                side_effect=[before, after],
            ),
            patch.object(
                SERVER,
                "use_inventory_item",
                return_value={
                    "success": True,
                    "itemId": 99,
                    "itemName": "惊喜宝箱",
                    "count": 7,
                    "message": (
                        "传音符+1;粮食辎重+1;"
                        "宝库空间不足3，无法开启该宝箱！开启失败！"
                    ),
                },
            ),
            patch.object(SERVER, "account_log") as account_log,
            patch.object(SERVER.time, "sleep"),
        ):
            result = SERVER.auto_open_inventory_items(
                self.sess,
                ["惊喜宝箱"],
            )

        self.assertEqual(result["opened"], 2)
        self.assertEqual(result["attempted"], 7)
        self.assertEqual(result["actions"][0]["openedCount"], 2)
        self.assertTrue(result["actions"][0]["partial"])
        self.assertEqual(
            result["actions"][0]["message"],
            "传音符+1；粮食辎重+1",
        )
        self.assertIn(
            "自动开箱成功：惊喜宝箱 ×2",
            account_log.call_args_list[0].args[1],
        )
        self.assertEqual(
            account_log.call_args_list[1].kwargs["level"],
            "warning",
        )

    def test_auto_open_sums_duplicate_inventory_stacks(self) -> None:
        before = {
            "items": [
                {"itemId": 53, "name": "实木宝箱", "count": 99},
                {"itemId": 53, "name": "实木宝箱", "count": 2},
            ],
        }
        after = {
            "items": [
                {"itemId": 53, "name": "实木宝箱", "count": 51},
            ],
        }
        with (
            patch.object(
                SERVER,
                "refresh_inventory",
                side_effect=[before, after],
            ),
            patch.object(
                SERVER,
                "use_inventory_item",
                return_value={
                    "success": True,
                    "itemId": 53,
                    "itemName": "实木宝箱",
                    "count": 50,
                    "message": "鲁公手册+50",
                },
            ) as use_item,
            patch.object(SERVER, "account_log"),
            patch.object(SERVER.time, "sleep"),
        ):
            result = SERVER.auto_open_inventory_items(
                self.sess,
                ["实木宝箱"],
            )

        use_item.assert_called_once_with(
            self.sess,
            53,
            50,
            item_name="实木宝箱",
        )
        self.assertEqual(result["opened"], 50)

    def test_auto_open_skips_locked_chest_without_key(self) -> None:
        inventory = {
            "items": [
                {"itemId": 58, "name": "青铜宝箱", "count": 3},
            ]
        }
        with patch.object(SERVER, "refresh_inventory", return_value=inventory), \
             patch.object(SERVER, "use_inventory_item") as use_item, \
             patch.object(SERVER, "account_log"):
            result = SERVER.auto_open_inventory_items(self.sess, ["青铜宝箱"])

        use_item.assert_not_called()
        self.assertEqual(result["opened"], 0)
        self.assertIn("缺少青铜钥匙", result["skipped"][0]["reason"])

    def test_auto_open_supports_copper_supply_cart(self) -> None:
        before = {
            "items": [
                {"itemId": 91, "name": "铜钱辎重", "count": 2},
            ],
        }
        after = {"items": []}
        with (
            patch.object(
                SERVER,
                "refresh_inventory",
                side_effect=[before, after],
            ),
            patch.object(
                SERVER,
                "use_inventory_item",
                return_value={
                    "success": True,
                    "itemId": 91,
                    "itemName": "铜钱辎重",
                    "count": 2,
                    "message": "获得铜钱:6000;获得铜钱:6000",
                },
            ) as use_item,
            patch.object(SERVER, "account_log"),
            patch.object(SERVER.time, "sleep"),
        ):
            result = SERVER.auto_open_inventory_items(
                self.sess,
                ["铜钱辎重"],
            )

        self.assertIn("铜钱辎重", SERVER.AUTO_OPEN_ITEM_NAMES)
        use_item.assert_called_once_with(
            self.sess,
            91,
            2,
            item_name="铜钱辎重",
        )
        self.assertEqual(result["opened"], 2)

    def test_inventory_reward_log_text(self) -> None:
        self.assertEqual(
            SERVER.inventory_reward_log_text("<br/>传音符+3;<br/>"),
            "传音符+3",
        )

    def test_inventory_success_logs_are_politics_records(self) -> None:
        self.assertEqual(
            SERVER.success_action_from_log(
                "自动开箱成功：实木宝箱 → 铜钱+1000"
            ),
            ("开箱", "实木宝箱 → 铜钱+1000"),
        )

    def test_clean_inventory_records_each_successful_discard(self) -> None:
        inventory = {
            "items": [
                {"itemId": 4, "name": "山贼头巾", "count": 50},
            ],
            "equipment": [{
                "instanceId": 0xC95F8,
                "name": "短剑",
                "level": 1,
                "quality": 1,
                "qualityName": "良好",
                "famous": False,
                "strengthen": 0,
                "extraText": "",
            }],
        }
        policy = {
            "discardItemNames": "山贼头巾",
            "discardEquipment": True,
            "maxEquipmentQuality": "良好",
            "maxEquipmentLevel": 20,
        }
        with (
            patch.object(SERVER, "refresh_inventory", return_value=inventory),
            patch.object(
                SERVER,
                "execute_discard_inventory",
                return_value={"success": True, "message": "丢弃成功"},
            ),
            patch.object(SERVER, "record_success_action") as record_success,
        ):
            result = SERVER.clean_inventory_by_policy(self.sess, policy)

        self.assertEqual(result["itemCount"], 1)
        self.assertEqual(result["equipmentCount"], 1)
        self.assertEqual(
            [call.args[:3] for call in record_success.call_args_list],
            [
                ("test-session", "丢弃物品", "山贼头巾 x50"),
                ("test-session", "丢弃装备", "良好1级短剑"),
            ],
        )

    def test_clean_inventory_does_not_record_when_nothing_is_discarded(self) -> None:
        with (
            patch.object(
                SERVER,
                "refresh_inventory",
                return_value={"items": [], "equipment": []},
            ),
            patch.object(SERVER, "record_success_action") as record_success,
        ):
            result = SERVER.clean_inventory_by_policy(
                self.sess,
                {
                    "discardItemNames": "山贼头巾",
                    "discardEquipment": True,
                },
            )

        self.assertEqual(result["actionCount"], 0)
        record_success.assert_not_called()

    def test_daily_tasks_only_request_unfinished_enabled_items(self) -> None:
        calls = []

        def fake_post(_url, commands, _dm, account_id=None):
            calls.append(commands[0][0])
            if commands[0][0] == 0x6260:
                return 200, b"", [packet(0xE260, b"")]
            return 200, b"", [packet(0xE266, b"\x00" + SERVER.utf("领取成功"))]

        states = [
            {"key": "autoSignIn", "completed": True},
            {"key": "arenaCoins", "completed": False},
            {"key": "autoDonate", "completed": False},
            {"key": "salary", "completed": False},
        ]
        with patch.object(SERVER, "current_daily_task_completions", return_value=states), \
             patch.object(SERVER, "post_game", side_effect=fake_post), \
             patch.object(SERVER, "record_daily_task_completion") as record:
            result = SERVER.execute_daily_once_tasks(
                self.sess,
                {"autoSignIn": True, "arenaCoins": True},
            )

        self.assertNotIn("autoSignIn", result)
        self.assertTrue(result["arenaCoins"]["success"])
        self.assertEqual(calls, [0x6260, 0x6266])
        record.assert_called_once_with(self.sess, "arenaCoins")

    def test_auto_sign_in_then_claims_daily_diamond_box(self) -> None:
        calls = []

        def fake_post(_url, commands, _dm, account_id=None):
            calls.append((commands, account_id))
            opcode = commands[0][0]
            if opcode == 0x6202:
                return 200, b"", [packet(
                    0x8134,
                    b"\x00\x00\x0bactivity-list"
                    + SERVER.utf("铜钱:10000获得成功。粮食:30000获得成功。"),
                )]
            if opcode == 0x1134:
                return 200, b"", [packet(
                    0x8134,
                    b"\x00\x00\x0bactivity-list"
                    + SERVER.utf("惊喜宝箱+1获得成功。"),
                )]
            raise AssertionError(f"unexpected opcode {opcode:#x}")

        states = [
            {"key": "autoSignIn", "completed": False},
            {"key": "arenaCoins", "completed": False},
            {"key": "autoDonate", "completed": False},
            {"key": "salary", "completed": False},
        ]
        with patch.object(SERVER, "current_daily_task_completions", return_value=states), \
             patch.object(SERVER, "post_game", side_effect=fake_post), \
             patch.object(SERVER, "record_daily_task_completion") as record, \
             patch.object(SERVER, "account_log"):
            result = SERVER.execute_daily_once_tasks(self.sess, {"autoSignIn": True})

        self.assertEqual(calls, [
            ([(0x6202, b"")], "test-session"),
            ([(0x1134, struct.pack(">qB", 0x0DE2B1, 0))], "test-session"),
        ])
        self.assertTrue(result["autoSignIn"]["success"])
        self.assertTrue(result["autoSignIn"]["dailyDiamondBox"]["success"])
        self.assertEqual(
            result["autoSignIn"]["message"],
            "铜钱:10000获得成功；粮食:30000获得成功；每日金钻宝箱：惊喜宝箱+1获得成功",
        )
        record.assert_called_once_with(self.sess, "autoSignIn")

    def test_activity_list_daily_box_success_uses_trailing_reward(self) -> None:
        payload = (
            b"\x00\x00\x0bactivity-list-data"
            + SERVER.utf("惊喜宝箱+1获得成功。")
        )

        parsed = SERVER.parse_daily_diamond_box_response(payload)

        self.assertTrue(parsed["success"])
        self.assertFalse(parsed["alreadyClaimed"])
        self.assertEqual(parsed["message"], "惊喜宝箱+1获得成功")
        self.assertEqual(parsed["serverMessage"], "惊喜宝箱+1获得成功。")

    def test_expired_daily_diamond_activity_means_already_claimed(self) -> None:
        payload = (
            b"\xfe\x01\x01\x00\x00\x00\x00"
            + SERVER.utf("周年活动")
            + SERVER.utf("操作失败，活动已过期。")
        )

        parsed = SERVER.parse_daily_diamond_box_response(payload)

        self.assertTrue(parsed["success"])
        self.assertTrue(parsed["alreadyClaimed"])
        self.assertEqual(parsed["message"], "每日金钻宝箱已经领取过了！")
        self.assertEqual(parsed["serverMessage"], "操作失败，活动已过期。")

    def test_explicit_already_claimed_daily_diamond_reply_is_success(self) -> None:
        parsed = SERVER.parse_daily_diamond_box_response(
            b"\x01" + SERVER.utf("今日已经领取")
        )

        self.assertTrue(parsed["success"])
        self.assertTrue(parsed["alreadyClaimed"])
        self.assertEqual(parsed["message"], "每日金钻宝箱已经领取过了！")

    def test_country_donation_limits_follow_current_role_level(self) -> None:
        self.sess["role"]["level"] = 44

        limits = SERVER.country_donation_limits(self.sess)

        self.assertEqual(limits, {"level": 44, "copper": 44000, "food": 132000})

    def test_arena_coins_empty_failure_explains_time_or_already_claimed(self) -> None:
        def fake_post(_url, commands, _dm, account_id=None):
            if commands[0][0] == 0x6260:
                return 200, b"", [packet(0xE260, b"")]
            return 200, b"", [packet(0xE266, b"\x01\x00\x00")]

        states = [
            {"key": "autoSignIn", "completed": False},
            {"key": "arenaCoins", "completed": False},
            {"key": "autoDonate", "completed": False},
            {"key": "salary", "completed": False},
        ]
        with patch.object(SERVER, "current_daily_task_completions", return_value=states), \
             patch.object(SERVER, "post_game", side_effect=fake_post), \
             patch.object(SERVER, "record_daily_task_completion") as record:
            result = SERVER.execute_daily_once_tasks(self.sess, {"arenaCoins": True})

        self.assertFalse(result["arenaCoins"]["success"])
        self.assertIn("22点后", result["arenaCoins"]["message"])
        record.assert_not_called()

    def test_daily_activity_only_refreshes_once_per_local_day(self) -> None:
        self.sess["dailyActivityDate"] = time.strftime("%Y-%m-%d", time.localtime())
        with patch.object(SERVER, "refresh_daily_activity") as refresh:
            self.assertFalse(SERVER.refresh_daily_activity_after_midnight(self.sess))
            refresh.assert_not_called()

    def test_failed_daily_activity_attempt_is_not_repeated_by_heartbeat(self) -> None:
        self.sess.pop("dailyActivityDate", None)
        with patch.object(SERVER, "post_game", side_effect=RuntimeError("temporary timeout")), \
             patch.object(SERVER, "persist_runtime_state"):
            result = SERVER.refresh_daily_activity(self.sess)

        self.assertIn("temporary timeout", result["parseError"])
        self.assertEqual(
            time.strftime("%Y-%m-%d", time.localtime()),
            self.sess["dailyActivityDate"],
        )
        with patch.object(SERVER, "refresh_daily_activity") as refresh:
            self.assertFalse(SERVER.refresh_daily_activity_after_midnight(self.sess))
            refresh.assert_not_called()

    def test_scheduled_daily_automation_only_runs_once_per_day(self) -> None:
        with patch.object(SERVER, "execute_daily_once_tasks", return_value={"arenaCoins": {}}) as execute, \
             patch.object(SERVER, "persist_runtime_state"):
            first = SERVER.execute_scheduled_daily_tasks_once(self.sess, {"arenaCoins": True})
            second = SERVER.execute_scheduled_daily_tasks_once(self.sess, {"arenaCoins": True})

        self.assertEqual(first, {"arenaCoins": {}})
        self.assertEqual(second, {})
        execute.assert_called_once_with(self.sess, {"arenaCoins": True})

    def test_arena_coin_completion_uses_22_o_clock_cycle(self) -> None:
        before = time.mktime((2026, 7, 12, 21, 59, 59, 0, 0, -1))
        after = time.mktime((2026, 7, 12, 22, 0, 0, 0, 0, -1))
        self.assertEqual(SERVER.arena_coins_cycle_date(before), "20260711")
        self.assertEqual(SERVER.arena_coins_cycle_date(after), "20260712")

        old = SERVER.DAILY_TASK_COMPLETIONS
        try:
            account_key = SERVER.daily_account_key(self.sess, "20260711")
            SERVER.DAILY_TASK_COMPLETIONS = {
                account_key: {"arenaCoins": {"completed": True, "completedAt": 123}},
            }
            with patch.object(SERVER, "arena_coins_cycle_date", return_value="20260711"):
                states = {
                    item["key"]: item
                    for item in SERVER.current_daily_task_completions(self.sess)
                }
            self.assertTrue(states["arenaCoins"]["completed"])
            self.assertEqual(states["arenaCoins"]["completedAt"], 123)
        finally:
            SERVER.DAILY_TASK_COMPLETIONS = old

    def test_settings_save_does_not_need_daily_execution_retry(self) -> None:
        self.sess["dailyAutomationAttemptDate"] = time.strftime("%Y-%m-%d", time.localtime())
        with patch.object(SERVER, "execute_daily_once_tasks") as execute:
            result = SERVER.execute_scheduled_daily_tasks_once(self.sess, {"arenaCoins": True})

        self.assertEqual(result, {})
        execute.assert_not_called()

    def test_newly_enabled_daily_tasks_only_include_off_to_on_keys(self) -> None:
        old_config = {
            "dailyTasks": {
                "autoSignIn": True,
                "arenaCoins": True,
                "autoDonate": True,
                "salary": False,
                "nationalCollect": False,
                "generalVisit": False,
            },
            "generalVisitGeneralIds": [],
        }
        new_config = {
            "dailyTasks": {
                "autoSignIn": True,
                "arenaCoins": True,
                "autoDonate": True,
                "salary": True,
                "nationalCollect": False,
                "generalVisit": True,
            },
            "generalVisitGeneralIds": ["1001", "1002"],
        }

        enabled = SERVER.newly_enabled_daily_task_settings(old_config, new_config)

        self.assertEqual(enabled.get("salary"), True)
        self.assertEqual(enabled.get("generalVisit"), True)
        self.assertNotIn("autoSignIn", enabled)
        self.assertNotIn("arenaCoins", enabled)
        self.assertNotIn("autoDonate", enabled)
        self.assertEqual(enabled.get("generalVisitGeneralIds"), ["1001", "1002"])

    def test_save_only_runs_newly_enabled_daily_tasks(self) -> None:
        old_config = {
            "dailyTasks": {
                "autoSignIn": True,
                "salary": False,
            },
        }
        new_config = {
            "dailyTasks": {
                "autoSignIn": True,
                "salary": True,
            },
        }
        with patch.object(SERVER, "account_state_block_reason", return_value=None), \
             patch.object(SERVER, "account_log"), \
             patch.object(
                 SERVER,
                 "execute_daily_once_tasks",
                 return_value={"salary": {"success": True, "completed": True}},
             ) as execute:
            result = SERVER.execute_newly_enabled_daily_tasks_on_save(
                self.sess,
                old_config,
                new_config,
            )

        execute.assert_called_once_with(self.sess, {"salary": True})
        self.assertEqual(result["salary"]["success"], True)
        # 不改动“今日已尝试”标记，避免影响登录/跨日的一日一次语义。
        self.assertNotEqual(
            self.sess.get("dailyAutomationAttemptDate"),
            "force-cleared",
        )

    def test_save_skips_newly_enabled_daily_tasks_when_account_offline(self) -> None:
        old_config = {"dailyTasks": {"salary": False}}
        new_config = {"dailyTasks": {"salary": True}}
        with patch.object(SERVER, "account_state_block_reason", return_value="账号未启动"), \
             patch.object(SERVER, "account_log") as log, \
             patch.object(SERVER, "execute_daily_once_tasks") as execute:
            result = SERVER.execute_newly_enabled_daily_tasks_on_save(
                self.sess,
                old_config,
                new_config,
            )

        execute.assert_not_called()
        self.assertTrue(result.get("skipped"))
        self.assertEqual(result.get("enabledKeys"), ["salary"])
        self.assertTrue(log.called)

    def test_country_donation_payloads_match_latest_capture(self) -> None:
        copper = SERVER.build_country_donation_payload(copper=44000)
        food = SERVER.build_country_donation_payload(food=132000)

        self.assertEqual(
            copper.hex(),
            "000000000000abe000000000000000000000000000000000",
        )
        self.assertEqual(
            food.hex(),
            "000000000000000000000000000203a00000000000000000",
        )

    def test_max_donation_stops_before_sending_when_resource_is_short(self) -> None:
        self.sess["role"]["level"] = 38
        self.sess["roleState"] = {"copper": 37999, "food": 999999}
        with patch.object(SERVER, "refresh_generals"), \
             patch.object(SERVER, "execute_country_donation") as donate:
            result = SERVER.execute_max_country_donations(self.sess)

        self.assertFalse(result["success"])
        self.assertIn("铜钱不足最高捐献额", result["message"])
        donate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
