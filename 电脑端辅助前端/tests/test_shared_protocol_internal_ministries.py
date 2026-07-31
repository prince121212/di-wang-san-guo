from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = ROOT / "shared_core" / "python"
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
FIXTURE_PATH = ROOT / "shared_core" / "protocol_parity_fixtures.json"
if str(CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CORE_SOURCE))

from dwpm_core.features.internal_affairs import (
    apply_building_sync_to_fief,
    auto_domestic_interval_seconds,
    auto_domestic_interval_text,
    build_building_action_payload,
    build_country_donation_payload,
    build_fief_query_payload,
    build_technology_donation_payload,
    build_technology_upgrade_payload,
    building_action_was_applied,
    building_can_follow_hall,
    building_level_limit,
    fief_build_queue_state,
    hall_must_upgrade_first,
    parse_8200_building_result,
    parse_8246_fief_result,
    parse_technology_states_from_8004,
    should_continue_filling_build_queues,
)
from dwpm_core.features.ministries import (
    build_hubu_batch_plant_payload,
    build_hubu_status_query_payload,
    ministry_planting_allowed,
    normalize_ministry_settings,
    parse_hubu_garden_status,
    parse_hubu_plant_response,
    unconfirmed_ministry_actions,
)
from dwpm_core.hashing import source_manifest


SPEC = importlib.util.spec_from_file_location(
    "dwpm_server_internal_ministries_shared_parity",
    SERVER_PATH,
)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class SharedInternalAffairsAndMinistriesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.fixtures = payload["fixtures"]

    def test_internal_affairs_request_builders_run_in_shared_core(self) -> None:
        fixture = self.fixtures["internalAffairsRequests"]
        expected = fixture["expected"]
        fief_query = build_fief_query_payload(fixture["fiefId"])
        building = build_building_action_payload(
            fixture["fiefId"],
            fixture["buildingSlot"],
            fixture["buildingType"],
        )
        technology = build_technology_upgrade_payload(
            fixture["academyFiefId"],
            fixture["academySlot"],
            fixture["technologyId"],
            fixture["technologyLevel"],
        )
        country_donation = build_country_donation_payload(
            copper=fixture["countryCopper"],
        )
        technology_donation = build_technology_donation_payload(
            fixture["technologyDonation"],
        )

        self.assertEqual(fief_query.hex(), expected["fiefQueryPayloadHex"])
        self.assertEqual(building.hex(), expected["buildingActionPayloadHex"])
        self.assertEqual(
            technology.hex(),
            expected["technologyUpgradePayloadHex"],
        )
        self.assertEqual(
            country_donation.hex(),
            expected["countryDonationPayloadHex"],
        )
        self.assertEqual(
            technology_donation.hex(),
            expected["technologyDonationPayloadHex"],
        )
        self.assertEqual(SERVER.build_fief_query_payload(fixture["fiefId"]), fief_query)
        self.assertEqual(
            SERVER.build_building_action_payload(
                fixture["fiefId"],
                fixture["buildingSlot"],
                fixture["buildingType"],
            ),
            building,
        )
        self.assertEqual(
            SERVER.build_technology_upgrade_payload(
                fixture["academyFiefId"],
                fixture["academySlot"],
                fixture["technologyId"],
                fixture["technologyLevel"],
            ),
            technology,
        )

    def test_building_and_fief_responses_run_in_shared_core(self) -> None:
        building_fixture = self.fixtures["internalAffairsBuilding8200"]
        building_payload = bytes.fromhex(building_fixture["responseHex"])
        building_result = parse_8200_building_result(building_payload)
        building_expected = building_fixture["expected"]
        self.assertEqual(
            SERVER.parse_8200_building_result(building_payload),
            building_result,
        )
        self.assertEqual(building_result["success"], building_expected["success"])
        self.assertEqual(building_result["fiefId"], building_expected["fiefId"])
        self.assertEqual(
            len(building_result["buildings"]),
            building_expected["buildingCount"],
        )
        for key, expected_key in (
            ("slot", "lastSlot"),
            ("type", "lastType"),
            ("name", "lastName"),
        ):
            self.assertEqual(
                building_result["buildings"][-1][key],
                building_expected[expected_key],
            )

        fief_fixture = self.fixtures["internalAffairsFief8246"]
        fief_payload = bytes.fromhex(fief_fixture["responseHex"])
        fief_result = parse_8246_fief_result(
            fief_payload,
            fief_fixture["expectedFiefId"],
        )
        self.assertEqual(
            SERVER.parse_8246_fief_result(
                fief_payload,
                fief_fixture["expectedFiefId"],
            ),
            fief_result,
        )
        fief_expected = fief_fixture["expected"]
        for key in ("success", "fiefId", "fiefName", "buildQueueCapacity"):
            self.assertEqual(fief_result[key], fief_expected[key])
        self.assertEqual(
            len(fief_result["buildings"]),
            fief_expected["buildingCount"],
        )

    def test_technology_table_runs_in_shared_core(self) -> None:
        fixture = self.fixtures["internalAffairsTechnology8004"]
        payload = bytes.fromhex(fixture["responseHex"])
        states = parse_technology_states_from_8004(payload)
        self.assertEqual(SERVER.parse_technology_states_from_8004(payload), states)
        expected = fixture["expected"]
        self.assertEqual(len(states), expected["technologyCount"])
        self.assertEqual(states[0]["level"], expected["firstLevel"])
        researching = next(row for row in states if row["researching"])
        for key in (
            "technologyId",
            "name",
            "level",
            "fiefId",
            "academyInstanceId",
            "deadlineMs",
        ):
            self.assertEqual(
                researching[key],
                expected[f"researching{key[0].upper()}{key[1:]}"],
            )

    def test_internal_affairs_queue_rules_run_in_shared_core(self) -> None:
        state = {
            "fiefName": "测试基地",
            "buildQueueCapacity": 5,
            "buildings": [
                {"slot": 0, "type": 0, "level": 4, "busy": False},
                {"slot": 1, "type": 1, "level": 4, "busy": False},
                {"slot": 2, "type": 4, "level": 9, "busy": True, "timerMs": 5200},
            ],
        }
        self.assertEqual(SERVER.hall_must_upgrade_first(state), hall_must_upgrade_first(state))
        self.assertEqual(SERVER.building_level_limit(state, 1), building_level_limit(state, 1))
        self.assertEqual(SERVER.fief_build_queue_state(state), fief_build_queue_state(state))
        self.assertEqual(
            SERVER.building_can_follow_hall(state, state["buildings"][1]),
            building_can_follow_hall(state, state["buildings"][1]),
        )
        self.assertEqual(
            SERVER.auto_domestic_interval_seconds([state]),
            auto_domestic_interval_seconds([state]),
        )
        self.assertEqual(SERVER.auto_domestic_interval_text(8), auto_domestic_interval_text(8))
        self.assertTrue(should_continue_filling_build_queues(True, False))
        buildings = [{"slot": 1, "type": 1, "level": 3, "busy": True}]
        self.assertTrue(building_action_was_applied(buildings, 1, 1, 3))
        shared_state = deepcopy(state)
        desktop_state = deepcopy(state)
        sync = {"buildings": buildings}
        self.assertEqual(
            SERVER.apply_building_sync_to_fief(desktop_state, sync),
            apply_building_sync_to_fief(shared_state, sync),
        )
        self.assertEqual(desktop_state, shared_state)

    def test_verified_ministry_settings_and_protocol_run_in_shared_core(self) -> None:
        safety_fixture = self.fixtures["ministrySettingsSafety"]
        settings = normalize_ministry_settings(safety_fixture["input"])
        expected = safety_fixture["expected"]
        self.assertEqual(SERVER.normalize_ministry_settings(safety_fixture["input"]), settings)
        for key in (
            "cropEnabled",
            "crop",
            "highPriority",
            "stealEnabled",
            "courtesyEnabled",
            "salaryRefresh",
        ):
            self.assertEqual(settings[key], expected[key])
        self.assertEqual(ministry_planting_allowed(settings), expected["plantingAllowed"])
        self.assertEqual(
            unconfirmed_ministry_actions(settings),
            expected["unconfirmedActions"],
        )

        fixture = self.fixtures["ministryHubuVerifiedPlant"]
        self.assertEqual(
            build_hubu_status_query_payload().hex(),
            fixture["statusQueryPayloadHex"],
        )
        self.assertEqual(
            build_hubu_batch_plant_payload(fixture["crop"]).hex(),
            fixture["plantPayloadHex"],
        )
        garden = parse_hubu_garden_status(
            bytes.fromhex(fixture["emptyGardenResponseHex"]),
        )
        receipt = parse_hubu_plant_response(
            bytes.fromhex(fixture["plantResponseHex"]),
        )
        self.assertEqual(garden, fixture["expected"]["garden"])
        for key, value in fixture["expected"]["receipt"].items():
            self.assertEqual(receipt[key], value)

    def test_unverified_ministry_writes_fail_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "协议尚未确认"):
            build_hubu_batch_plant_payload("草药")
        garden = bytes.fromhex(
            self.fixtures["ministryHubuVerifiedPlant"]["emptyGardenResponseHex"]
        )
        with self.assertRaisesRegex(RuntimeError, "尚未确认的记录结构"):
            parse_hubu_garden_status(garden + b"\x00")
        self.assertFalse(
            ministry_planting_allowed({"cropEnabled": True, "crop": "草药"})
        )

    def test_new_shared_sources_are_in_cross_platform_hash(self) -> None:
        manifest = source_manifest(ROOT / "shared_core")
        self.assertIn(
            "python/dwpm_core/features/internal_affairs.py",
            manifest["files"],
        )
        self.assertIn(
            "python/dwpm_core/features/ministries.py",
            manifest["files"],
        )


if __name__ == "__main__":
    unittest.main()
