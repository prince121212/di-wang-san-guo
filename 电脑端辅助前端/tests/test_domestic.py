import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("desktop_server_domestic", ROOT / "server.py")
SERVER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)
CAPTURE = ROOT.parent / "ctf_out/passive_pcap_hotspot_20260711_150241/live_analyzed"


class DomesticProtocolTests(unittest.TestCase):
    def test_food_to_copper_rounds_up_to_3000_copper_units(self) -> None:
        sess = {
            "sessionId": "s1",
            "roleState": {"copper": 93500, "food": 50000},
        }
        task = {"config": {"foodToCopper": True, "copperFloorWan": 10}, "logs": []}
        original = SERVER.execute_food_to_copper
        try:
            SERVER.execute_food_to_copper = lambda _sess, food_amount, confirm="": {
                "success": True,
                "copper": 102500,
                "food": 20000,
                "foodAmount": food_amount,
            }
            result = SERVER.ensure_account_copper_floor(sess, task=task, context="测试")
        finally:
            SERVER.execute_food_to_copper = original
        self.assertTrue(result["ok"])
        self.assertTrue(result["exchanged"])
        self.assertEqual(result["copperAmount"], 9000)
        self.assertEqual(result["foodAmount"], 30000)

    def response_payload(self, flow: int, opcode: int) -> bytes:
        packets = SERVER.parse_response((CAPTURE / f"{flow:03d}" / "resp.bin").read_bytes())
        return next(packet["payload"] for packet in packets if packet["opcode"] == opcode)

    def test_request_payloads_match_captures(self) -> None:
        self.assertEqual(
            SERVER.build_building_action_payload(0x0A79, 10, 1).hex(),
            "000000000000000a79000a0001",
        )
        self.assertEqual(
            SERVER.build_fief_query_payload(0x0A79).hex(),
            "000000000000000a79",
        )
        self.assertEqual(
            SERVER.build_technology_upgrade_payload(0x09AF, 3, 5, 2).hex(),
            "00000000000009af030005020000",
        )

    def test_parse_8200_building_sync(self) -> None:
        parsed = SERVER.parse_8200_building_result(self.response_payload(12, 0x8200))
        self.assertTrue(parsed["success"])
        self.assertEqual(parsed["fiefId"], 0x0A79)
        self.assertEqual(len(parsed["buildings"]), 4)
        self.assertEqual(parsed["buildings"][-1]["name"], "房屋")
        self.assertEqual(parsed["buildings"][-1]["slot"], 10)

    def test_building_action_confirmation_uses_level_or_busy_state(self) -> None:
        upgraded = [{"slot": 1, "type": 1, "level": 4, "busy": False}]
        queued = [{"slot": 1, "type": 1, "level": 3, "busy": True}]
        unchanged = [{"slot": 1, "type": 1, "level": 3, "busy": False}]
        self.assertTrue(SERVER.building_action_was_applied(upgraded, 1, 1, 3))
        self.assertTrue(SERVER.building_action_was_applied(queued, 1, 1, 3))
        self.assertFalse(SERVER.building_action_was_applied(unchanged, 1, 1, 3))
        self.assertTrue(SERVER.building_action_was_applied(upgraded, 1, 1, None))

    def test_parse_8246_base_and_secondary_fief(self) -> None:
        secondary = SERVER.parse_8246_fief_result(self.response_payload(15, 0x8246), 0x0A79)
        base = SERVER.parse_8246_fief_result(self.response_payload(119, 0x8246), 0x09AF)
        self.assertEqual(secondary["fiefName"], "九业封地")
        self.assertEqual(secondary["buildQueueCapacity"], 2)
        self.assertEqual(base["fiefName"], "宫玉迎基地")
        self.assertEqual(len(secondary["buildings"]), 4)
        self.assertEqual(len(base["buildings"]), 13)
        academy = next(item for item in base["buildings"] if item["type"] == 3)
        self.assertEqual((academy["slot"], academy["level"]), (3, 5))

    def test_domestic_hall_level_caps_and_queue_rules(self) -> None:
        state = {
            "fiefName": "测试基地",
            "buildQueueCapacity": 5,
            "buildings": [
                {"slot": 0, "type": 0, "level": 4, "busy": False},
                {"slot": 1, "type": 1, "level": 4, "busy": False},
                {"slot": 2, "type": 4, "level": 9, "busy": False},
            ],
        }
        self.assertTrue(SERVER.hall_must_upgrade_first(state))
        self.assertFalse(SERVER.building_can_follow_hall(state, state["buildings"][1]))
        state["buildings"][0]["level"] = 5
        self.assertTrue(SERVER.building_can_follow_hall(state, state["buildings"][1]))
        self.assertEqual(SERVER.building_level_limit(state, 1), 15)
        self.assertEqual(SERVER.building_level_limit(state, 4), 10)
        state["fiefName"] = "普通封地"
        self.assertEqual(SERVER.building_level_limit(state, 1), 10)
        state["buildings"][0]["busy"] = True
        self.assertTrue(SERVER.building_can_follow_hall(state, state["buildings"][1]))
        state["buildings"][1]["level"] = 5
        self.assertFalse(SERVER.building_can_follow_hall(state, state["buildings"][1]))
        state["buildings"][1]["busy"] = True
        self.assertEqual(SERVER.fief_build_queue_state(state), (2, 5))

    def test_role_queue_summary_combines_all_fiefs_and_academies(self) -> None:
        fiefs = [
            {
                "buildQueueCapacity": 5,
                "buildings": [
                    {"type": 0, "busy": True},
                    {"type": 3, "busy": False},
                    {"type": 3, "busy": True},
                ],
            },
            {
                "buildQueueCapacity": 2,
                "buildings": [
                    {"type": 3, "busy": False},
                    {"type": 1, "busy": True},
                ],
            },
        ]
        technologies = [
            {"technologyId": 1, "researching": True},
            {"technologyId": 2, "researching": False},
        ]
        summary = SERVER.summarize_role_queues(fiefs, technologies)
        self.assertEqual(summary["buildingQueue"], {"current": 3, "capacity": 7})
        self.assertEqual(summary["researchQueue"], {"current": 1, "capacity": 3})
        self.assertEqual(summary["fiefCount"], 2)

    def test_domestic_schedule_uses_lowest_hall_level(self) -> None:
        def state(level: int) -> dict:
            return {"buildings": [{"slot": 0, "type": 0, "level": level, "busy": False}]}

        self.assertEqual(SERVER.auto_domestic_interval_seconds([state(7), state(12)]), 3600)
        self.assertEqual(SERVER.auto_domestic_interval_seconds([state(7), state(6)]), 600)
        self.assertEqual(SERVER.auto_domestic_interval_seconds([]), 600)
        short_job = state(6)
        short_job["buildings"].append({
            "slot": 1, "type": 1, "level": 1, "busy": True, "timerMs": 5200,
        })
        self.assertEqual(SERVER.auto_domestic_interval_seconds([short_job]), 8)
        self.assertEqual(SERVER.auto_domestic_interval_text(8), "8秒")
        self.assertEqual(SERVER.auto_domestic_interval_text(600), "10分钟")
        self.assertEqual(SERVER.auto_domestic_interval_text(3600), "1小时")

    def test_successful_build_action_immediately_continues_queue_filling(self) -> None:
        self.assertTrue(SERVER.should_continue_filling_build_queues(True, False))
        self.assertFalse(SERVER.should_continue_filling_build_queues(False, False))
        self.assertFalse(SERVER.should_continue_filling_build_queues(True, True))
        state = {"buildings": [{"slot": 1, "busy": False}]}
        synced = [{"slot": 1, "busy": True}]
        self.assertTrue(SERVER.apply_building_sync_to_fief(state, {"buildings": synced}))
        self.assertEqual(state["buildings"], synced)
        self.assertFalse(SERVER.apply_building_sync_to_fief(state, {}))

    def test_owned_fiefs_include_places_without_generals(self) -> None:
        sess = {
            "roleState": {"roleName": "测试角色"},
            "generals": [{"fiefId": 1001}],
        }
        with patch.object(SERVER, "query_raid_fiefs", return_value={
            "fiefs": [
                {"targetId": 1001, "fiefName": "都城"},
                {"targetId": 1002, "fiefName": "永原封地"},
            ],
        }):
            self.assertEqual(SERVER.query_all_owned_fief_ids(sess), [1001, 1002])
        self.assertEqual(SERVER.fief_display_name(sess, 1002), "永原封地（ID 1002）")
        self.assertEqual(SERVER.fief_display_name(sess, 9999), "封地ID 9999")

    def test_brush_center_uses_login_coordinate_cache_without_game_request(self) -> None:
        sess = {
            "generals": [
                {"id": 11, "name": "甲", "fiefId": 1001},
                {"id": 12, "name": "乙", "fiefId": 1001},
                {"id": 13, "name": "丙", "fiefId": 1002},
            ],
            "ownedFiefLocations": {
                "1001": {
                    "targetId": 1001,
                    "fiefName": "都城",
                    "cityName": "洛阳",
                    "x": 91,
                    "y": 26,
                },
                "1002": {
                    "targetId": 1002,
                    "fiefName": "边城",
                    "cityName": "长安",
                    "x": 30,
                    "y": 40,
                },
            },
        }
        with patch.object(
            SERVER,
            "query_raid_fiefs",
            side_effect=AssertionError("保存设置时不应请求游戏服务器"),
        ):
            result = SERVER.recommend_brush_center(sess, ["11", "12", "13"])
        self.assertEqual((result["x"], result["y"]), (91, 26))
        self.assertEqual(result["fiefId"], 1001)
        self.assertEqual(result["fiefCounts"], {"1001": 2, "1002": 1})

    def test_brush_center_missing_login_cache_does_not_fallback_to_live_query(self) -> None:
        sess = {
            "generals": [{"id": 11, "name": "甲", "fiefId": 1001}],
        }
        with patch.object(
            SERVER,
            "query_raid_fiefs",
            side_effect=AssertionError("不允许实时查询"),
        ):
            with self.assertRaisesRegex(RuntimeError, "请重新启动该账号"):
                SERVER.recommend_brush_center(sess, ["11"])

    def test_parse_technology_table_and_research_state(self) -> None:
        prefix = b"\xaa" * 19
        records = bytearray()
        for tech_id in range(22):
            if tech_id == 5:
                records += bytes([tech_id, 2, 0])
                records += (2438).to_bytes(8, "big", signed=True)
                records += (21586).to_bytes(8, "big", signed=True)
                records += (123456789).to_bytes(8, "big", signed=True)
            else:
                records += bytes([tech_id, 1 if tech_id == 0 else 0, 2])
                records += (-1).to_bytes(8, "big", signed=True) * 2
                records += (0).to_bytes(8, "big", signed=True)
        states = SERVER.parse_technology_states_from_8004(prefix + records + b"\xbb")
        self.assertEqual(states[0]["level"], 1)
        self.assertEqual(states[5]["level"], 2)
        self.assertTrue(states[5]["researching"])
        self.assertEqual(states[5]["fiefId"], 2438)


if __name__ == "__main__":
    unittest.main()
