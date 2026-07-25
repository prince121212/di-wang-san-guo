from __future__ import annotations

import importlib.util
import struct
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
CAPTURE_FLOWS = ROOT / "ctf_out" / "passive_pcap_hotspot_20260710_185601" / "live_analyzed"

SPEC = importlib.util.spec_from_file_location("dwpm_server_lossless_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


def response_payload(flow_index: int, opcode: int) -> bytes:
    response_file = CAPTURE_FLOWS / f"{flow_index:03d}" / "resp.bin"
    packets = SERVER.parse_response(response_file.read_bytes())
    return next(packet["payload"] for packet in packets if packet.get("opcode") == opcode)


class LosslessProtocolTests(unittest.TestCase):
    def test_status_fields_match_captured_level10_guard(self) -> None:
        status = SERVER.parse_lossless_status(response_payload(84, 0x8900))
        self.assertEqual(status["state"], 1)
        self.assertEqual(status["mode"], 1)
        self.assertEqual(status["stateName"], "可出征")
        self.assertEqual(status["phase"], "ready")
        self.assertTrue(status["dispatchable"])
        self.assertFalse(status["settlementPending"])
        self.assertEqual(status["remainingAttempts"], 4)
        self.assertEqual(status["usedAttempts"], 1)
        self.assertEqual(status["selectedLevel"], 10)
        self.assertEqual(status["stageId"], 0x3011)

    def test_pending_settlement_takes_priority_over_ready_mode(self) -> None:
        status = SERVER.parse_lossless_status(response_payload(15, 0x8900))
        self.assertEqual(status["mode"], 1)
        self.assertTrue(status["settlementPending"])
        self.assertEqual(status["phase"], "settlement")
        self.assertEqual(status["stateName"], "待结算")
        self.assertFalse(status["dispatchable"])

    def test_cooldown_layout_uses_tail_long_not_action_timer(self) -> None:
        payload = bytes.fromhex("00000000000529a90002030001000000000068af5b00000008")
        pending = SERVER.parse_lossless_status(payload)
        self.assertEqual(pending["mode"], 0)
        self.assertEqual(pending["actionTimerMs"], 338345)
        self.assertEqual(pending["cooldownMs"], 0x68AF5B)
        self.assertEqual(pending["reopenCost"], 8)
        self.assertEqual(pending["phase"], "settlement")

        settled_payload = bytearray(payload)
        settled_payload[12] = 0
        cooldown = SERVER.parse_lossless_status(bytes(settled_payload))
        self.assertEqual(cooldown["phase"], "cooldown")
        self.assertEqual(cooldown["stateName"], "冷却中")
        self.assertFalse(cooldown["dispatchable"])

    def test_catalog_contains_ten_levels_and_five_stages(self) -> None:
        catalog = SERVER.parse_lossless_catalog(response_payload(85, 0x8904))
        self.assertNotIn("parseError", catalog)
        self.assertEqual(catalog["levelCount"], 10)
        for level_number, level in enumerate(catalog["levels"], start=1):
            self.assertEqual(level["level"], level_number)
            self.assertEqual(
                [stage["name"] for stage in level["stages"]],
                ["卫兵", "小队长", "大队长", "头目", "首领"],
            )

    def test_level10_guard_screen_accepts_captured_target(self) -> None:
        lineup = SERVER.parse_lossless_lineup(response_payload(86, 0x8906))
        verdict = SERVER.evaluate_level10_guard_lineup(lineup)
        self.assertTrue(verdict["qualified"])
        self.assertEqual(verdict["chariotPositions"], [3, 4, 5])
        self.assertEqual(verdict["catapultPositions"], [5])
        self.assertEqual(
            verdict["formation"],
            ["1640近卫兵", "1581铁骑兵", "715重弩车", "743重弩车", "251投石车"],
        )

    def test_level10_guard_screen_rejects_catapult_before_other_chariot(self) -> None:
        lineup = SERVER.parse_lossless_lineup(response_payload(48, 0x8906))
        verdict = SERVER.evaluate_level10_guard_lineup(lineup)
        self.assertFalse(verdict["qualified"])
        self.assertIn("最后一个不是投石车", verdict["reason"])

    def test_level10_guard_accepts_earlier_catapult_when_last_chariot_is_catapult(self) -> None:
        lineup = {
            "enemies": [
                {"soldierCount": 1663, "soldierType": "近卫兵"},
                {"soldierCount": 1591, "soldierType": "铁骑兵"},
                {"soldierCount": 254, "soldierType": "投石车"},
                {"soldierCount": 718, "soldierType": "重弩车"},
                {"soldierCount": 254, "soldierType": "投石车"},
            ],
        }
        verdict = SERVER.evaluate_level10_guard_lineup(lineup)
        self.assertTrue(verdict["qualified"])
        self.assertEqual(verdict["chariotPositions"], [3, 4, 5])
        self.assertEqual(verdict["catapultPositions"], [3, 5])

    def test_failed_battle_is_a_valid_settlement(self) -> None:
        payload = response_payload(17, 0x8902)
        settlement = SERVER.parse_lossless_settlement(payload)
        self.assertTrue(settlement["success"])
        self.assertTrue(settlement["battleFailed"])
        self.assertFalse(settlement["battleWon"])
        self.assertIn("失败", settlement["message"])
        self.assertEqual(settlement["modeAfterSettlement"], 1)
        self.assertEqual(settlement["battleId"], int.from_bytes(payload[2:10], "big"))
        self.assertIn("声望", settlement["generalText"])
        self.assertIn("经验", settlement["extraText"])

    def test_level_selection_response_uses_one_based_ui_level(self) -> None:
        selected = SERVER.parse_lossless_select_response(response_payload(30, 0x8908))
        self.assertTrue(selected["success"])
        self.assertEqual(selected["selectedLevelIndex"], 9)
        self.assertEqual(selected["selectedLevel"], 10)
        self.assertEqual(selected["stageId"], 0x3011)

    def test_dispatch_payload_matches_capture(self) -> None:
        general_ids = [
            "0000000000c4a332",
            "0000000000f4f86b",
            "0000000000facf09",
            "0000000000c4a333",
            "0000000000c4a331",
        ]
        expected_prepare = (
            "0b05"
            "0000000000c4a332"
            "0000000000f4f86b"
            "0000000000facf09"
            "0000000000c4a333"
            "0000000000c4a331"
            "0000000000000398"
        )
        self.assertEqual(
            SERVER.build_lossless_prepare_payload(general_ids, 920).hex(),
            expected_prepare,
        )
        self.assertEqual(
            SERVER.build_lossless_expedition_payload(general_ids, 920).hex(),
            expected_prepare + "ffffffffffffffff000000",
        )

    def test_only_explicitly_enabled_rows_execute(self) -> None:
        session = {
            "generals": [
                {"id": 1, "idHex": "0000000000000001"},
                {"id": 2, "idHex": "0000000000000002"},
            ]
        }
        rows = SERVER.normalize_lossless_rows(session, {
            "fullTroops": True,
            "rows": [
                {"generalIds": ["1"], "level": "10级"},
                {"enabled": False, "generalIds": ["1"], "level": "10级"},
                {"enabled": True, "generalIds": ["2"], "level": "9级"},
            ],
        })
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["generalIds"], ["2"])
        self.assertEqual(rows[0]["level"], 9)


class DungeonConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = {
            "generals": [
                {"id": 1, "idHex": "0000000000000001"},
                {"id": 2, "idHex": "0000000000000002"},
            ]
        }

    def test_no_enabled_row_means_dungeon_is_disabled(self) -> None:
        settings = SERVER.normalize_military_future_settings("dungeon", {
            "rows": [
                {"enabled": False, "generalIds": ["1"], "chapter": "第一章", "stage": "3"},
                {"generalIds": ["2"], "chapter": "第二章", "stage": "1"},
            ],
        })
        self.assertFalse(settings["rows"][0]["enabled"])
        self.assertFalse(settings["rows"][1]["enabled"])
        self.assertEqual(SERVER.normalize_dungeon_rows(self.session, settings), [])

    def test_only_one_dungeon_row_can_be_enabled(self) -> None:
        settings = SERVER.normalize_military_future_settings("dungeon", {
            "rows": [
                {"enabled": True, "generalIds": ["1"], "chapter": "第一章", "stage": "3"},
                {"enabled": True, "generalIds": ["2"], "chapter": "第二章", "stage": "1"},
            ],
        })
        with self.assertRaisesRegex(RuntimeError, "同一时间只能启用一条"):
            SERVER.normalize_dungeon_rows(self.session, settings)

    def test_disabled_incomplete_rows_do_not_block_enabled_row(self) -> None:
        settings = SERVER.normalize_military_future_settings("dungeon", {
            "rows": [
                {"enabled": False, "generalIds": [], "chapter": "", "stage": ""},
                {"enabled": True, "generalIds": ["2"], "chapter": "第一章", "stage": "3", "chest": "右"},
            ],
        })
        rows = SERVER.normalize_dungeon_rows(self.session, settings)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["generalIds"], ["2"])
        self.assertEqual(rows[0]["stage"], 3)


class CommandCenterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.saved_tasks = SERVER.AUTO_TASKS
        self.saved_claims = SERVER.COMMAND_CENTER_CLAIMS
        self.saved_task_log = SERVER.task_log
        SERVER.AUTO_TASKS = {}
        SERVER.COMMAND_CENTER_CLAIMS = {}
        SERVER.task_log = lambda task, message: None

    def tearDown(self) -> None:
        SERVER.AUTO_TASKS = self.saved_tasks
        SERVER.COMMAND_CENTER_CLAIMS = self.saved_claims
        SERVER.task_log = self.saved_task_log

    def task(self, task_id: str, task_type: str, state: str, runnable: bool, ids: list[str]):
        task = {
            "taskId": task_id,
            "type": task_type,
            "sessionId": "session-1",
            "status": "running",
            "config": {"sessionId": "session-1"},
            "schedulerState": state,
            "schedulerRunnable": runnable,
            "schedulerGeneralIds": ids,
            "stopEvent": threading.Event(),
        }
        SERVER.AUTO_TASKS[task_id] = task
        return task

    def test_lossless_ready_blocks_brush_with_shared_general(self) -> None:
        self.task("lossless", "lossless", "ready", True, ["g1"])
        brush = self.task("brush", "auto-brush-yellow", "ready", True, ["g1"])
        blockers = SERVER._command_center_blockers(brush, ["g1"])
        self.assertEqual([blocker["taskKey"] for blocker in blockers], ["lossless"])

    def test_mine_ready_blocks_lossless_with_shared_general(self) -> None:
        self.task("mine", "auto-mine", "ready", True, ["g1"])
        lossless = self.task("lossless", "lossless", "ready", True, ["g1"])
        blockers = SERVER._command_center_blockers(lossless, ["g1"])
        self.assertEqual([blocker["taskKey"] for blocker in blockers], ["mine"])

    def test_mine_without_target_yields_to_lossless(self) -> None:
        self.task("mine", "auto-mine", "waiting_target", False, ["g1"])
        lossless = self.task("lossless", "lossless", "ready", True, ["g1"])
        self.assertEqual(SERVER._command_center_blockers(lossless, ["g1"]), [])

    def test_waiting_high_priority_task_with_busy_formation_yields_shared_idle_general(self) -> None:
        self.task(
            "mine",
            "auto-mine",
            "waiting_generals",
            False,
            ["g1", "g2"],
        )
        brush = self.task(
            "brush",
            "auto-brush-yellow",
            "ready",
            True,
            ["g1"],
        )
        with patch.dict(
            SERVER.SESSIONS,
            {
                "session-1": {
                    "generals": [
                        {"id": "g1", "displayStatus": "闲"},
                        {"id": "g2", "displayStatus": "防"},
                    ],
                },
            },
            clear=True,
        ):
            self.assertEqual(SERVER._command_center_blockers(brush, ["g1"]), [])

    def test_lossless_cooldown_yields_to_brush(self) -> None:
        self.task("lossless", "lossless", "cooldown", False, ["g1"])
        brush = self.task("brush", "auto-brush-yellow", "ready", True, ["g1"])
        self.assertEqual(SERVER._command_center_blockers(brush, ["g1"]), [])

    def test_brush_ready_blocks_dungeon(self) -> None:
        self.task("brush", "auto-brush-yellow", "checking", True, ["g1"])
        dungeon = self.task("dungeon", "dungeon", "ready", True, ["g1"])
        blockers = SERVER._command_center_blockers(dungeon, ["g1"])
        self.assertEqual([blocker["taskKey"] for blocker in blockers], ["brushYellow"])

    def test_brush_without_target_yields_to_dungeon(self) -> None:
        self.task("brush", "auto-brush-yellow", "waiting_target", False, ["g1"])
        dungeon = self.task("dungeon", "dungeon", "ready", True, ["g1"])
        self.assertEqual(SERVER._command_center_blockers(dungeon, ["g1"]), [])

    def test_disjoint_generals_do_not_block(self) -> None:
        self.task("lossless", "lossless", "ready", True, ["g1"])
        brush = self.task("brush", "auto-brush-yellow", "ready", True, ["g2"])
        self.assertEqual(SERVER._command_center_blockers(brush, ["g2"]), [])

    def test_brush_uses_disjoint_idle_formation_while_mine_is_running(self) -> None:
        self.task("mine", "auto-mine", "fighting", False, ["g1", "g2"])
        brush = self.task("brush", "auto-brush-yellow", "checking", True, ["g1"])
        sess = {
            "generals": [
                {"id": "g1", "name": "共享1", "displayStatus": "征"},
                {"id": "g2", "name": "共享2", "displayStatus": "征"},
                {"id": "g3", "name": "独立1", "displayStatus": "闲"},
                {"id": "g4", "name": "独立2", "displayStatus": "闲"},
            ],
        }
        rules = [
            {"generalIds": ["g1", "g2"]},
            {"generalIds": ["g3", "g4"]},
        ]

        selected = SERVER.select_dispatchable_brush_rule_index(
            brush,
            sess,
            rules,
            0,
        )

        self.assertEqual(selected, 1)

    def test_active_claim_blocks_same_general(self) -> None:
        brush = self.task("brush", "auto-brush-yellow", "ready", True, ["g1"])
        SERVER.COMMAND_CENTER_CLAIMS["session-1"] = {
            "lossless": {
                "taskId": "lossless",
                "taskKey": "lossless",
                "priority": 300,
                "generalIds": ["g1"],
            }
        }
        blockers = SERVER._command_center_blockers(brush, ["g1"])
        self.assertEqual(blockers[0]["state"], "dispatch-claim")

    def test_waiting_brush_is_released_when_lossless_enters_cooldown(self) -> None:
        lossless = self.task("lossless", "lossless", "ready", True, ["g1"])
        brush = self.task("brush", "auto-brush-yellow", "ready", True, ["g1"])
        acquired = threading.Event()

        def acquire() -> None:
            if SERVER.command_center_acquire(brush, ["g1"]):
                acquired.set()

        thread = threading.Thread(target=acquire)
        thread.start()
        time.sleep(0.05)
        self.assertFalse(acquired.is_set())
        SERVER.command_center_set_state(
            lossless,
            "cooldown",
            general_ids=["g1"],
            runnable=False,
            message="test cooldown",
        )
        self.assertTrue(acquired.wait(1.0))
        SERVER.command_center_release(brush)
        thread.join(timeout=1.0)
        self.assertFalse(thread.is_alive())

    def test_user_task_stack_puts_current_instruction_before_cooldown(self) -> None:
        lossless = self.task("lossless", "lossless", "cooldown", False, ["g1"])
        lossless.update({
            "schedulerNextCheckAt": 123456789,
            "losslessRemainingAttempts": 2,
            "lastLosslessStatus": {"remainingAttempts": 2},
        })
        brush = self.task("brush", "auto-brush-yellow", "fighting", False, ["g2"])
        stack = SERVER.task_stack_for_session("session-1", [lossless, brush])
        self.assertEqual([item["name"] for item in stack], ["刷黄", "无损闯关"])
        self.assertTrue(stack[0]["current"])
        self.assertEqual(stack[1]["state"], "cooldown")
        self.assertEqual(stack[1]["cooldownUntil"], 123456789)
        self.assertEqual(stack[1]["remainingAttempts"], 2)

    def test_user_task_stack_includes_non_resident_backend_instruction(self) -> None:
        formations = self.task("formations", "apply-formations", "running", True, [])
        stack = SERVER.task_stack_for_session("session-1", [formations])
        self.assertEqual(stack[0]["name"], "配兵")
        self.assertEqual(stack[0]["category"], "military")
        self.assertEqual(stack[0]["position"], 1)

    def test_user_task_stack_hides_command_center_wording(self) -> None:
        dungeon = self.task("dungeon", "dungeon", "ready", True, ["g1"])
        dungeon["schedulerMessage"] = "已满足本任务条件，等待指挥中心下发出征权"
        stack = SERVER.task_stack_for_session("session-1", [dungeon])
        self.assertEqual(stack[0]["message"], "条件已满足，等待执行")
        self.assertNotIn("指挥中心", stack[0]["message"])


class ResidentRestoreTests(unittest.TestCase):
    def test_enabled_resident_configs_resume_in_priority_order(self) -> None:
        saved = {
            "load_account_habits": SERVER.load_account_habits,
            "start_auto_mine": SERVER.start_auto_mine,
            "start_lossless_task": SERVER.start_lossless_task,
            "start_auto_brush": SERVER.start_auto_brush,
            "start_dungeon_task": SERVER.start_dungeon_task,
            "account_log": SERVER.account_log,
        }
        calls = []
        try:
            SERVER.load_account_habits = lambda sess: {
                "formations": [],
                "mine": {
                    "speed": False,
                    "fullLoyalty": True,
                    "centerX": 91,
                    "centerY": 26,
                    "rows": [{
                        "enabled": True,
                        "generalIds": ["1"],
                        "resourceType": "镔铁矿",
                        "scope": "附近",
                    }],
                },
                "config": {
                    "autoStart": True,
                    "sessionId": "session-1",
                    "brush": {"generalId": "1"},
                    "formations": [],
                },
                "militaryFuture": {
                    "lossless": {
                        "fullTroops": False,
                        "rows": [{"enabled": True, "generalIds": ["1"], "level": "10级"}],
                    },
                    "dungeon": {
                        "rows": [{
                            "enabled": True,
                            "generalIds": ["1"],
                            "chapter": "第一章",
                            "stage": "1",
                            "chest": "右",
                        }],
                    },
                },
            }
            SERVER.start_auto_mine = lambda sess, settings: calls.append("mine") or {"started": True}
            SERVER.start_lossless_task = lambda sess, rows: calls.append("lossless") or {"started": True}
            SERVER.start_auto_brush = lambda config: calls.append("brushYellow") or {"taskId": "brush"}
            SERVER.start_dungeon_task = lambda sess, rows: calls.append("dungeon") or {"started": True}
            SERVER.account_log = lambda *args, **kwargs: None
            session = {
                "sessionId": "session-1",
                "generals": [{"id": 1, "idHex": "0000000000000001"}],
            }
            result = SERVER.resume_saved_resident_tasks(session)
            self.assertEqual(calls, ["mine", "lossless", "brushYellow", "dungeon"])
            self.assertEqual(list(result["resumed"]), ["mine", "lossless", "brushYellow", "dungeon"])
            self.assertEqual(result["errors"], {})
        finally:
            for name, value in saved.items():
                setattr(SERVER, name, value)


class TaskAccountGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.saved_accounts = SERVER.ACCOUNTS
        self.saved_sessions = SERVER.SESSIONS
        self.saved_task_log = SERVER.task_log
        SERVER.ACCOUNTS = {}
        SERVER.SESSIONS = {}
        SERVER.task_log = lambda task, message: task.setdefault("testLogs", []).append(message)

    def tearDown(self) -> None:
        SERVER.ACCOUNTS = self.saved_accounts
        SERVER.SESSIONS = self.saved_sessions
        SERVER.task_log = self.saved_task_log

    def test_checking_account_waits_for_first_heartbeat_then_continues(self) -> None:
        sid = "session-checking"
        SERVER.SESSIONS[sid] = {"sessionId": sid}
        SERVER.ACCOUNTS[sid] = {
            "sessionId": sid,
            "started": True,
            "status": "checking",
        }
        task = {
            "taskId": "lossless-checking",
            "type": "lossless",
            "sessionId": sid,
            "config": {"sessionId": sid},
            "stopEvent": threading.Event(),
        }

        def confirm_online() -> None:
            time.sleep(0.03)
            with SERVER.ACCOUNT_LOCK:
                SERVER.ACCOUNTS[sid]["status"] = "online"

        thread = threading.Thread(target=confirm_online)
        thread.start()
        self.assertTrue(SERVER.wait_for_task_account_online(
            task,
            sid,
            "无损",
            timeout_sec=0.5,
            poll_sec=0.01,
        ))
        thread.join(timeout=1.0)
        self.assertEqual(task["schedulerState"], "checking")
        self.assertTrue(task["schedulerRunnable"])
        self.assertTrue(any("等待首次心跳" in line for line in task["testLogs"]))
        self.assertTrue(any("确认在线" in line for line in task["testLogs"]))

    def test_offline_account_still_fails_immediately(self) -> None:
        sid = "session-offline"
        SERVER.SESSIONS[sid] = {"sessionId": sid}
        SERVER.ACCOUNTS[sid] = {
            "sessionId": sid,
            "started": True,
            "status": "offline",
            "lastError": "测试掉线",
        }
        task = {
            "taskId": "lossless-offline",
            "type": "lossless",
            "sessionId": sid,
            "config": {"sessionId": sid},
            "stopEvent": threading.Event(),
        }
        with self.assertRaisesRegex(RuntimeError, "掉线.*测试掉线"):
            SERVER.wait_for_task_account_online(
                task,
                sid,
                "无损",
                timeout_sec=0.5,
                poll_sec=0.01,
            )


if __name__ == "__main__":
    unittest.main()
