from __future__ import annotations

import importlib.util
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_daily_country_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


def packet(opcode: int, payload: bytes) -> dict:
    return {"opcode": opcode, "payload": payload, "len": len(payload), "frag": 0}


def status_receipt(status: int, message: str = "") -> bytes:
    return bytes([status & 0xFF]) + SERVER.utf(message)


def visit_receipt(status: int, message: str = "") -> bytes:
    return struct.pack(">i", status) + SERVER.utf(message)


class DailyCountryFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sess = {
            "sessionId": "daily-country-test",
            "gameHttp": "http://game",
            "dm": 123,
            "role": {"roleId": 1, "level": 10, "roleName": "测试角色"},
            "roleState": {"copper": 9999999, "food": 99999999},
            "area": {"areaId": 351},
        }

    def test_donation_attempts_copper_food_and_technology_independently(self) -> None:
        calls: list[tuple[int, bytes]] = []

        def fake_donate(_sess, *, resource, amount):
            calls.append((resource, amount))
            return {"success": resource != "food", "resource": resource, "amount": amount}

        with patch.object(SERVER, "execute_country_donation", side_effect=fake_donate):
            result = SERVER.execute_daily_country_donations(self.sess)

        self.assertEqual([key for key, _ in calls], ["copper", "food", "technology"])
        self.assertFalse(result["success"])
        self.assertTrue(result["partialSuccess"])
        self.assertFalse(result["completed"])
        self.assertEqual(len(result["actions"]), 3)

    def test_technology_donation_payload_and_opcode(self) -> None:
        calls = []

        def fake_post(_url, commands, _dm, account_id=None):
            calls.append((commands, account_id))
            return 200, b"", [packet(0x840A, b"\x00")]

        with patch.object(SERVER, "post_game", side_effect=fake_post):
            result = SERVER.execute_country_donation(self.sess, resource="technology", amount=10000)

        self.assertTrue(result["success"])
        self.assertEqual(calls[0][0], [(0x140A, b"\x00\x00\x00\x27\x10")])

    def test_salary_payload_and_success_status(self) -> None:
        calls = []

        def fake_post(_url, commands, _dm, account_id=None):
            calls.append(commands)
            return 200, b"", [packet(0xA14B, status_receipt(1, "领取国家俸禄成功"))]

        with patch.object(SERVER, "post_game", side_effect=fake_post):
            result = SERVER.claim_national_salary(self.sess)

        self.assertTrue(result["success"])
        self.assertEqual(calls, [[(0x314B, b"\x01")]])

    def test_national_list_payload_categories_exclude_small_city(self) -> None:
        payloads = []

        def fake_post(_url, commands, _dm, account_id=None):
            payloads.append(commands[0][1])
            category = commands[0][1][8]
            # Real 0x8404 header is seven bytes:
            # status, category, totalPages, page, count.
            return 200, b"", [packet(0x8404, bytes([0, category, 0, 1, 0, 1, 0]))]

        with patch.object(SERVER, "post_game", side_effect=fake_post):
            SERVER.query_national_cities(self.sess)

        self.assertEqual([payload[8] for payload in payloads], [1, 2, 3])
        self.assertNotIn(4, [payload[8] for payload in payloads])

    def test_real_national_city_samples_use_seven_byte_header(self) -> None:
        samples = {
            "state": (
                "000100010001010006e6b49be998b300005b001a000ae78caee5b89d28383329"
                "00af1f40000003390000270f010100000006001e8480001e8480000186a0000186a0"
            ),
            "commandery": (
                "000200010001010009e5b9bfe68890e585b301005d001c000ae78caee5b89d28383329"
                "000013880000028e0000232801010000000b00186a0000186a000000132b000186a0"
            ),
            "county": (
                "000300010001010006e5a4b7e999b50200850026000ae59b9ee5bf8628393429"
                "00000bb800000000000003e8010300000015000927c000124f8000000001000186a0"
            ),
        }
        parsed = {
            kind: SERVER.parse_national_city_page(bytes.fromhex(payload_hex))
            for kind, payload_hex in samples.items()
        }

        self.assertEqual(parsed["state"]["cities"][0]["name"], "洛阳")
        self.assertEqual(parsed["state"]["cities"][0]["kind"], "state")
        self.assertEqual(parsed["commandery"]["cities"][0]["kind"], "commandery")
        self.assertEqual(parsed["county"]["cities"][0]["kind"], "county")
        self.assertEqual([parsed[key]["category"] for key in samples], [1, 2, 3])

    def test_real_small_city_sample_is_classified_but_never_a_target(self) -> None:
        payload = bytes.fromhex(
            "000400010001010006e68890e69e9703005f0024000ae59b9ee5bf8628393429"
            "000107d000000000000000c801020000001f00061a80000c350000000001000186a0"
        )
        parsed = SERVER.parse_national_city_page(payload)

        self.assertEqual(parsed["category"], 4)
        self.assertEqual(parsed["cities"][0]["name"], "成林")
        self.assertEqual(parsed["cities"][0]["kind"], "small")

    def test_real_national_collect_status_samples_parse_quota_and_copper(self) -> None:
        available = SERVER.parse_national_collect_status(bytes.fromhex(
            "0000000500000000000249f000000000000249f000000000000493e0"
            "00000000000493e0"
        ))
        exhausted = SERVER.parse_national_collect_status(bytes.fromhex(
            "00020505000000000000c350000000000000c35000000000000186a0"
            "00000000000186a0"
        ))

        self.assertEqual(available["usedCount"], 0)
        self.assertEqual(available["limit"], 5)
        self.assertEqual(available["currentCopper"], 150000)
        self.assertTrue(available["canCollect"])
        self.assertEqual(exhausted["usedCount"], 5)
        self.assertTrue(exhausted["quotaExhausted"])
        self.assertFalse(exhausted["canCollect"])

    def test_national_collect_ranks_by_copper_then_hierarchy(self) -> None:
        cities = [
            {"name": "县甲", "kind": "county"},
            {"name": "州甲", "kind": "state"},
            {"name": "郡甲", "kind": "commandery"},
        ]
        amounts = {"县甲": 100, "州甲": 500, "郡甲": 500}
        attempted = []

        with patch.object(SERVER, "query_national_cities", return_value=cities), \
             patch.object(SERVER, "query_national_collect_status", side_effect=lambda _s, city: {
                 "status": 0, "availability": 0, "usedCount": 0, "limit": 1,
                 "currentCopper": amounts[city["name"]], "copperCap": 0,
                 "currentFood": 0, "foodCap": 0,
             }), \
             patch.object(SERVER, "collect_national_city", side_effect=lambda _s, city: (
                 attempted.append(city["name"]) or {"success": True, "message": "ok"}
             )):
            result = SERVER.execute_national_collect(self.sess)

        self.assertEqual(attempted, ["州甲"])
        self.assertEqual(result["successfulCount"], 1)

    def test_national_collect_prefers_richer_county_over_poorer_state(self) -> None:
        cities = [
            {"name": "州甲", "kind": "state"},
            {"name": "县甲", "kind": "county"},
        ]
        amounts = {"州甲": 100, "县甲": 500}
        attempted = []

        with patch.object(SERVER, "query_national_cities", return_value=cities), \
             patch.object(SERVER, "query_national_collect_status", side_effect=lambda _s, city: {
                 "status": 0, "availability": 0, "usedCount": 0, "limit": 1,
                 "currentCopper": amounts[city["name"]], "copperCap": 0,
                 "currentFood": 0, "foodCap": 0,
             }), \
             patch.object(SERVER, "collect_national_city", side_effect=lambda _s, city: (
                 attempted.append(city["name"]) or {"success": True, "message": "ok"}
             )):
            result = SERVER.execute_national_collect(self.sess)

        self.assertEqual(attempted, ["县甲"])
        self.assertEqual(result["ranking"][0]["city"], "县甲")

    def test_national_collect_failure_moves_to_next_city(self) -> None:
        cities = [{"name": "州甲", "kind": "state"}, {"name": "郡甲", "kind": "commandery"}]
        attempted = []

        def collect(_sess, city):
            attempted.append(city["name"])
            return {"success": False, "message": "州城暂不可征收"} if city["name"] == "州甲" else {"success": True, "message": "ok"}

        with patch.object(SERVER, "query_national_cities", return_value=cities), \
             patch.object(SERVER, "query_national_collect_status", side_effect=lambda _s, city: {
                 "status": 0, "availability": 0, "usedCount": 0, "limit": 1,
                 "currentCopper": 100 if city["name"] == "州甲" else 50,
                 "copperCap": 0, "currentFood": 0, "foodCap": 0,
             }), \
             patch.object(SERVER, "collect_national_city", side_effect=collect):
            result = SERVER.execute_national_collect(self.sess)

        self.assertEqual(attempted, ["州甲", "郡甲"])
        self.assertEqual(result["successfulCount"], 1)
        self.assertTrue(result["completed"])
        self.assertFalse(result["success"])
        self.assertTrue(result["partialSuccess"])

    def test_national_collect_status_failure_is_not_queried_repeatedly(self) -> None:
        cities = [
            {"name": "州坏", "kind": "state"},
            {"name": "郡好", "kind": "commandery"},
            {"name": "县好", "kind": "county"},
        ]
        status_calls = []
        collect_calls = []

        def status(_sess, city):
            status_calls.append(city["name"])
            if city["name"] == "州坏":
                raise RuntimeError("状态超时")
            return {
                "status": 0, "availability": 0, "usedCount": 0, "limit": 2,
                "currentCopper": 200 if city["name"] == "郡好" else 100,
                "copperCap": 0, "currentFood": 0, "foodCap": 0,
                "canCollect": True, "quotaExhausted": False,
            }

        with patch.object(SERVER, "query_national_cities", return_value=cities), \
             patch.object(SERVER, "query_national_collect_status", side_effect=status), \
             patch.object(SERVER, "collect_national_city", side_effect=lambda _s, city: (
                 collect_calls.append(city["name"]) or {"success": True, "message": "ok"}
             )):
            result = SERVER.execute_national_collect(self.sess)

        self.assertEqual(status_calls, ["州坏", "郡好", "县好"])
        self.assertEqual(collect_calls, ["郡好", "县好"])
        self.assertEqual(result["statusFailureCount"], 1)
        self.assertTrue(result["partialSuccess"])

    def test_city_lord_collects_every_owned_city_after_one_failure(self) -> None:
        fiefs = {"fiefs": [{"cityName": "甲"}, {"cityName": "乙"}, {"cityName": "丙"}]}
        attempted = []

        with patch.object(SERVER, "query_own_fiefs", return_value=fiefs), \
             patch.object(SERVER, "collect_city_lord", side_effect=lambda _s, fief: (
                 attempted.append(fief["cityName"]) or {"success": fief["cityName"] != "乙"}
             )):
            result = SERVER.execute_city_lord_collect(self.sess)

        self.assertEqual(attempted, ["甲", "乙", "丙"])
        self.assertEqual(result["attemptedCount"], 3)
        self.assertFalse(result["completed"])

    def test_city_lord_uses_city_name_not_display_fief_name(self) -> None:
        fiefs = {
            "fiefs": [
                {"name": "利萍丰基地", "fiefName": "利萍丰基地", "cityName": "洛阳"},
                {"name": "广成关封地", "fiefName": "广成关封地", "cityName": "广成关"},
            ]
        }
        attempted = []

        with patch.object(SERVER, "query_own_fiefs", return_value=fiefs), \
             patch.object(SERVER, "collect_city_lord", side_effect=lambda _s, fief: (
                 attempted.append(SERVER._daily_city_name(fief)) or {"success": True}
             )):
            result = SERVER.execute_city_lord_collect(self.sess)

        self.assertTrue(result["success"])
        self.assertEqual(attempted, ["洛阳", "广成关"])

    def test_city_lord_no_owned_city_is_terminal_no_target(self) -> None:
        with patch.object(SERVER, "query_own_fiefs", return_value={"fiefs": []}):
            result = SERVER.execute_city_lord_collect(self.sess)

        self.assertTrue(result["success"])
        self.assertTrue(result["completed"])
        self.assertTrue(result["noTarget"])

    def test_general_visit_all_failures_remain_retryable(self) -> None:
        candidates = [
            {"id": "1", "name": "甲", "captiveState": 0},
            {"id": "2", "name": "乙", "captiveState": 0},
        ]
        with patch.object(SERVER, "query_general_visit_candidates", return_value={"generals": candidates}), \
             patch.object(SERVER, "visit_general", return_value={"success": False, "message": "暂不可拜访"}):
            result = SERVER.execute_general_visit(self.sess, ["1", "2"])

        self.assertFalse(result["success"])
        self.assertFalse(result["completed"])
        self.assertEqual(result["attemptedCount"], 2)

    def test_general_visit_uses_selected_order_and_stops_on_first_success(self) -> None:
        candidates = [
            {"id": "1", "name": "甲", "captiveState": 0},
            {"id": "2", "name": "乙", "captiveState": 0},
            {"id": "3", "name": "丙", "captiveState": 0},
        ]
        attempted = []

        with patch.object(SERVER, "query_general_visit_candidates", return_value={"generals": candidates}), \
             patch.object(SERVER, "visit_general", side_effect=lambda _s, general: (
                 attempted.append(general["id"]) or {"success": general["id"] == "2"}
             )):
            result = SERVER.execute_general_visit(self.sess, ["3", "2", "1"])

        self.assertEqual(attempted, ["3", "2"])
        self.assertTrue(result["success"])

    def test_general_visit_rejected_invitation_is_terminal_for_today(self) -> None:
        candidates = [
            {"id": "1", "name": "甲", "captiveState": 0},
            {"id": "2", "name": "乙", "captiveState": 0},
        ]
        attempted = []

        def visit(_sess, general):
            attempted.append(general["id"])
            return {
                "success": False,
                "completed": True,
                "invitationResolved": True,
                "status": 0,
                "message": "甲拒绝了阁下的邀请，请再接再厉",
            }

        with patch.object(SERVER, "query_general_visit_candidates", return_value={"generals": candidates}), \
             patch.object(SERVER, "visit_general", side_effect=visit):
            result = SERVER.execute_general_visit(self.sess, ["1", "2"])

        self.assertEqual(attempted, ["1"])
        self.assertFalse(result["success"])
        self.assertTrue(result["completed"])
        self.assertTrue(result["visitResolved"])

    def test_general_visit_receipt_marks_rejection_and_duplicate_as_completed(self) -> None:
        rejected = SERVER.parse_general_visit_receipt(
            visit_receipt(0, "蔡邕拒绝了阁下的邀请，请再接再厉")
        )
        duplicate = SERVER.parse_general_visit_receipt(
            visit_receipt(-2, "不可拜访，本日已拜访")
        )

        self.assertFalse(rejected["success"])
        self.assertTrue(rejected["completed"])
        self.assertTrue(rejected["invitationResolved"])
        self.assertTrue(duplicate["completed"])
        self.assertTrue(duplicate["alreadyVisited"])

    def test_general_visit_list_short_business_receipt_does_not_overread(self) -> None:
        payload = bytes([0xFE]) + SERVER.utf("不可拜访，本日已拜访")
        parsed = SERVER.parse_general_visit_page(payload)

        self.assertEqual(parsed["status"], -2)
        self.assertEqual(parsed["message"], "不可拜访，本日已拜访")
        self.assertTrue(parsed["shortReceipt"])
        self.assertEqual(parsed["candidates"], [])

    def test_general_visit_already_done_short_circuits_without_visit_request(self) -> None:
        with patch.object(SERVER, "query_general_visit_candidates", return_value={
            "success": True,
            "completed": True,
            "alreadyVisited": True,
            "message": "不可拜访，本日已拜访",
            "generals": [],
        }), patch.object(SERVER, "visit_general") as visit:
            result = SERVER.execute_general_visit(self.sess, ["1", "2"])

        visit.assert_not_called()
        self.assertTrue(result["success"])
        self.assertTrue(result["completed"])
        self.assertTrue(result["duplicateVisit"])

    def test_general_visit_candidate_query_normalizes_already_visited_receipt(self) -> None:
        def fake_post(_url, _commands, _dm, account_id=None):
            return 200, b"", [packet(0xA271, bytes([0xFE]) + SERVER.utf("不可拜访，本日已拜访"))]

        with patch.object(SERVER, "post_game", side_effect=fake_post):
            result = SERVER.query_general_visit_candidates(self.sess)

        self.assertTrue(result["success"])
        self.assertTrue(result["completed"])
        self.assertTrue(result["alreadyVisited"])
        self.assertEqual(result["generals"], [])

    def test_daily_task_exception_does_not_block_sibling_tasks(self) -> None:
        states = [{"key": key, "completed": False} for key in SERVER.DAILY_TASK_NAMES]
        with patch.object(SERVER, "current_daily_task_completions", return_value=states), \
             patch.object(SERVER, "execute_daily_country_donations", side_effect=RuntimeError("donate boom")), \
             patch.object(SERVER, "claim_national_salary", return_value={"success": True, "completed": True}), \
             patch.object(SERVER, "record_daily_task_completion"), \
             patch.object(SERVER, "account_log"), \
             patch.object(SERVER, "database_upsert_important_notice"), \
             patch.object(SERVER, "database_resolve_important_notice"):
            result = SERVER.execute_daily_once_tasks(
                self.sess,
                {"autoDonate": True, "salary": True},
            )

        self.assertIn("autoDonate", result)
        self.assertIn("salary", result)
        self.assertFalse(result["autoDonate"]["success"])
        self.assertTrue(result["salary"]["success"])

    def test_explicit_session_rejection_is_recorded_without_blocking_sibling_tasks(self) -> None:
        states = [{"key": key, "completed": False} for key in SERVER.DAILY_TASK_NAMES]
        with patch.object(SERVER, "current_daily_task_completions", return_value=states), \
             patch.object(SERVER, "execute_daily_country_donations", side_effect=SERVER.GameServerRejected("会话失效")), \
             patch.object(SERVER, "claim_national_salary", return_value={"success": True, "completed": True}), \
             patch.object(SERVER, "mark_account_offline_if_session_invalid"), \
             patch.object(SERVER, "record_daily_task_completion"), \
             patch.object(SERVER, "record_success_action"), \
             patch.object(SERVER, "account_log"), \
             patch.object(SERVER, "database_upsert_important_notice"), \
             patch.object(SERVER, "database_resolve_important_notice"):
            result = SERVER.execute_daily_once_tasks(
                self.sess,
                {"autoDonate": True, "salary": True},
            )

        self.assertIn("autoDonate", result)
        self.assertIn("salary", result)
        self.assertTrue(result["autoDonate"].get("sessionInvalid"))
        self.assertTrue(result["salary"]["success"])


if __name__ == "__main__":
    unittest.main()
