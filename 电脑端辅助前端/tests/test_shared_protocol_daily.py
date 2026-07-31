from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = ROOT / "shared_core" / "python"
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
FIXTURE_PATH = ROOT / "shared_core" / "protocol_parity_fixtures.json"
if str(CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CORE_SOURCE))

from dwpm_core.features.daily import (
    build_general_visit_list_payload,
    build_general_visit_payload,
    build_national_city_list_payload,
    build_owned_city_list_payload,
    build_salary_payload,
    country_donation_limits,
    general_visit_already_visited,
    national_citizen_daily_skip_result,
    normalize_general_visit_ids,
    parse_arena_coin_claim_response,
    parse_daily_diamond_box_response,
    parse_daily_sign_in_packets,
    parse_e200_daily_activity,
    parse_general_visit_page,
    parse_general_visit_receipt,
    parse_national_city_page,
    parse_owned_city_list,
    parse_salary_receipt,
    role_is_national_citizen,
)


SPEC = importlib.util.spec_from_file_location(
    "dwpm_server_daily_shared_parity",
    SERVER_PATH,
)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class SharedDailyProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.fixtures = payload["fixtures"]

    def test_national_city_pages_run_in_shared_core(self) -> None:
        for fixture_name in (
            "dailyNationalCity8404State",
            "dailyNationalCity8404Commandery",
            "dailyNationalCity8404County",
            "dailyNationalCity8404Small",
        ):
            fixture = self.fixtures[fixture_name]
            payload = bytes.fromhex(fixture["responseHex"])
            page = parse_national_city_page(
                payload,
                fixture["requestedCategory"],
            )
            with self.subTest(fixture=fixture_name):
                self.assertEqual(
                    SERVER.parse_national_city_page(
                        payload,
                        fixture["requestedCategory"],
                    ),
                    page,
                )
                city = page["cities"][0]
                self.assertEqual(page["category"], fixture["expected"]["category"])
                for key in ("name", "kind", "x", "y"):
                    self.assertEqual(city[key], fixture["expected"][key])

    def test_owned_city_and_salary_run_in_shared_core(self) -> None:
        owned_fixture = self.fixtures["dailyOwnedCity8318Nanhua"]
        owned_payload = bytes.fromhex(owned_fixture["responseHex"])
        owned = parse_owned_city_list(owned_payload)

        self.assertEqual(SERVER.parse_owned_city_list(owned_payload), owned)
        self.assertEqual(
            build_owned_city_list_payload(owned_fixture["roleId"]).hex(),
            owned_fixture["requestHex"],
        )
        self.assertEqual(
            SERVER.build_owned_city_list_payload(owned_fixture["roleId"]),
            build_owned_city_list_payload(owned_fixture["roleId"]),
        )
        city = owned["cities"][0]
        expected_city = owned_fixture["expected"]
        self.assertEqual(city["cityId"], expected_city["id"])
        for key in ("kindCode", "name", "x", "y", "ownerName", "ownerLevel"):
            self.assertEqual(city[key], expected_city[key])

        salary_fixture = self.fixtures["dailySalaryA14bSuccess"]
        salary_payload = bytes.fromhex(salary_fixture["responseHex"])
        salary = parse_salary_receipt(salary_payload)
        self.assertEqual(SERVER.parse_salary_receipt(salary_payload), salary)
        self.assertEqual(build_salary_payload().hex(), salary_fixture["requestHex"])
        for key, value in salary_fixture["expected"].items():
            self.assertEqual(salary[key], value)

    def test_general_visit_receipts_run_in_shared_core(self) -> None:
        for fixture_name in (
            "dailyGeneralVisitA273Rejected",
            "dailyGeneralVisitA273AlreadyVisited",
        ):
            fixture = self.fixtures[fixture_name]
            payload = bytes.fromhex(fixture["responseHex"])
            result = parse_general_visit_receipt(payload)
            with self.subTest(fixture=fixture_name):
                self.assertEqual(
                    SERVER.parse_general_visit_receipt(payload),
                    result,
                )
                for key, value in fixture["expected"].items():
                    self.assertEqual(result[key], value)

        page_fixture = self.fixtures["dailyGeneralVisitA271AlreadyVisited"]
        page_payload = bytes.fromhex(page_fixture["responseHex"])
        page = parse_general_visit_page(page_payload)
        self.assertEqual(SERVER.parse_general_visit_page(page_payload), page)
        self.assertTrue(
            general_visit_already_visited(page["status"], page["message"])
        )
        self.assertEqual(
            SERVER.general_visit_already_visited(
                page["status"],
                page["message"],
            ),
            general_visit_already_visited(page["status"], page["message"]),
        )
        self.assertEqual(
            SERVER.build_general_visit_list_payload(2),
            build_general_visit_list_payload(2),
        )
        self.assertEqual(
            SERVER.build_general_visit_payload(123, 2),
            build_general_visit_payload(123, 2),
        )

    def test_activity_arena_sign_in_and_diamond_run_in_shared_core(self) -> None:
        activity_fixture = self.fixtures["dailyActivityE200"]
        activity_payload = bytes.fromhex(activity_fixture["responseHex"])
        activity = parse_e200_daily_activity(activity_payload)
        for key, value in activity_fixture["expected"].items():
            self.assertEqual(activity["treasureOccupied"][key], value)

        arena_fixture = self.fixtures["dailyArenaDuplicateE266"]
        arena_payload = bytes.fromhex(arena_fixture["responseHex"])
        arena = parse_arena_coin_claim_response(arena_payload)
        self.assertEqual(SERVER.parse_arena_coin_claim_response(arena_payload), arena)
        for key, value in arena_fixture["expected"].items():
            self.assertEqual(arena[key], value)

        sign_fixture = self.fixtures["dailySignIn8134Duplicate"]
        sign_packets = [
            {
                "opcode": int(sign_fixture["responseOpcode"], 0),
                "payload": bytes.fromhex(sign_fixture["responseHex"]),
            }
        ]
        sign = parse_daily_sign_in_packets(sign_packets)
        self.assertEqual(SERVER.parse_daily_sign_in_packets(sign_packets), sign)
        for key, value in sign_fixture["expected"].items():
            self.assertEqual(sign[key], value)

        diamond_fixture = self.fixtures["dailyDiamondExpired8134"]
        diamond_payload = bytes.fromhex(diamond_fixture["responseHex"])
        diamond = parse_daily_diamond_box_response(diamond_payload)
        self.assertEqual(
            SERVER.parse_daily_diamond_box_response(diamond_payload),
            diamond,
        )
        for key, value in diamond_fixture["expected"].items():
            self.assertEqual(diamond[key], value)

    def test_national_list_request_validation_is_shared(self) -> None:
        self.assertEqual(
            SERVER.build_national_city_list_payload(1, 2),
            build_national_city_list_payload(1, 2),
        )
        with self.assertRaises(ValueError):
            build_national_city_list_payload(4, 1)

    def test_daily_identity_and_donation_rules_are_shared(self) -> None:
        citizen = {"roleState": {"officeIdUnsigned": 0x0100, "level": 30}}
        non_citizen = {
            "roleState": {"officeName": "太守", "level": 30},
            "role": {"officeName": "国民", "level": 30},
        }
        self.assertTrue(role_is_national_citizen(citizen))
        self.assertFalse(role_is_national_citizen(non_citizen))
        self.assertEqual(
            SERVER.role_is_national_citizen(citizen),
            role_is_national_citizen(citizen),
        )
        self.assertEqual(
            SERVER.national_citizen_daily_skip_result(citizen),
            national_citizen_daily_skip_result(citizen),
        )
        self.assertEqual(
            SERVER.country_donation_limits(citizen),
            country_donation_limits(citizen),
        )
        value = ["123", "0x7b", "bad", "456", "789", "1000", "2000"]
        self.assertEqual(
            SERVER.normalize_general_visit_ids(value),
            normalize_general_visit_ids(value),
        )
        self.assertEqual(
            normalize_general_visit_ids(value),
            ["123", "456", "789", "1000"],
        )


if __name__ == "__main__":
    unittest.main()
