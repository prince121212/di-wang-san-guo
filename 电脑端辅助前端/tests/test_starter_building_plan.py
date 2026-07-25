import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def building(slot, kind, level=0, busy=False):
    return {
        "slot": slot,
        "type": kind,
        "level": level,
        "busy": busy,
        "timerMs": 1000 if busy else 0,
    }


class StarterBuildingPlanTest(unittest.TestCase):
    def plan(self, states):
        sess = {
            "generals": [{"fiefId": 100, "fiefName": "基地"}],
            "ownedFiefNames": {"100": "基地", "200": "临时封地"},
        }
        by_id = {row["fiefId"]: row for row in states}
        with patch.object(
            server, "query_all_owned_fief_ids", return_value=list(by_id),
        ), patch.object(
            server, "query_fief_buildings",
            side_effect=lambda _sess, fief_id: by_id[fief_id],
        ):
            return server.starter_refresh_fief_buildings(sess)

    def test_never_returns_hall_upgrade_and_prioritizes_infantry_to_seven(self):
        plan = self.plan([
            {
                "fiefId": 100,
                "fiefName": "基地",
                "buildQueueCapacity": 2,
                "buildings": [
                    building(0, 0, 1),
                    building(1, 4, 6),
                    building(2, 5, 3),
                ],
            },
        ])
        action = plan["nextAction"]
        self.assertEqual(action["buildingType"], 4)
        self.assertEqual(action["previousLevel"], 6)
        self.assertNotEqual(action["buildingType"], 0)

    def test_after_first_pack_base_builds_exactly_one_vehicle_camp_first(self):
        sess = {
            "generals": [{"fiefId": 100, "fiefName": "基地"}],
            "ownedFiefNames": {"100": "基地"},
            "roleState": {"level": 7},
            "starterFirstPackOpened": True,
        }
        state = {
            "fiefId": 100,
            "fiefName": "基地",
            "buildQueueCapacity": 2,
            "buildings": [
                building(0, 0, 10),
                building(1, 4, 1),
            ],
        }
        with patch.object(
            server, "query_all_owned_fief_ids", return_value=[100],
        ), patch.object(
            server, "query_fief_buildings", return_value=state,
        ):
            plan = server.starter_refresh_fief_buildings(sess)
        action = plan["nextAction"]
        self.assertEqual(action["fiefId"], 100)
        self.assertEqual(action["buildingType"], 6)
        self.assertEqual(action["buildingName"], "战车营")
        self.assertIn("基地只先建1座", action["reason"])

    def test_after_level_seven_upgrades_the_lagging_production_camp(self):
        plan = self.plan([
            {
                "fiefId": 100,
                "fiefName": "基地",
                "buildQueueCapacity": 2,
                "buildings": [
                    building(0, 0, 1),
                    building(1, 4, 8),
                    building(2, 5, 3),
                ],
            },
        ])
        self.assertEqual(plan["nextAction"]["buildingType"], 5)

    def test_temporary_fief_only_builds_level_one_vehicle_camp(self):
        plan = self.plan([
            {
                "fiefId": 100,
                "fiefName": "基地",
                "buildQueueCapacity": 1,
                "buildings": [
                    building(0, 0, 1),
                    building(1, 4, 7, busy=True),
                    building(2, 5, 3, busy=True),
                ],
            },
            {
                "fiefId": 200,
                "fiefName": "临时封地",
                "buildQueueCapacity": 2,
                "buildings": [
                    building(0, 0, 1),
                    building(1, -1),
                ],
            },
        ])
        action = plan["nextAction"]
        self.assertEqual(action["fiefId"], 200)
        self.assertEqual(action["buildingType"], 6)
        self.assertIsNone(action["previousLevel"])

    def test_omitted_slots_from_8246_are_inferred_as_empty(self):
        plan = self.plan([
            {
                "fiefId": 100,
                "fiefName": "基地",
                "buildQueueCapacity": 1,
                "buildings": [
                    building(0, 0, 1),
                    building(1, 4, 7, busy=True),
                    building(2, 5, 3, busy=True),
                ],
            },
            {
                "fiefId": 200,
                "fiefName": "临时封地",
                "buildQueueCapacity": 2,
                # Real 0x8246 responses omit empty slots entirely.
                "buildings": [building(0, 0, 1)],
            },
        ])
        action = plan["nextAction"]
        self.assertEqual(action["fiefId"], 200)
        self.assertEqual(action["slot"], 1)
        self.assertEqual(action["buildingType"], 6)

    def test_level_seven_upgrade_is_cancelled_before_heavy_recruitment(self):
        plan = {
            "fiefs": [{
                "fiefId": 100,
                "isBase": True,
                "buildings": [{
                    "slot": 10,
                    "type": 4,
                    "level": 7,
                    "busy": True,
                    "nested": {"action": 0, "ownerId": 7001},
                }],
            }],
        }
        sess = {"army": [], "generals": []}
        with patch.object(
            server, "starter_refresh_fief_buildings", return_value=plan,
        ), patch.object(
            server,
            "execute_cancel_building_action",
            return_value={"success": True, "message": "已取消"},
        ) as cancel:
            result = server.execute_starter_development_action(
                sess, {"id": 1},
            )
        self.assertTrue(result["success"])
        self.assertTrue(result["recruitmentPriority"])
        cancel.assert_called_once_with(sess, 100, 10, 4)

    def test_population_shortage_prioritizes_lowest_idle_house(self):
        sess = {
            "generals": [{"fiefId": 100, "fiefName": "基地"}],
            "roleState": {
                "populationCurrent": 100,
                "populationCap": 820,
            },
        }
        state = {
            "fiefId": 100,
            "fiefName": "基地",
            "buildQueueCapacity": 5,
            "buildings": [
                building(0, 0, 10),
                building(1, 1, 10),
                building(4, 1, 3),
                building(9, 1, 1),
                building(10, 4, 7),
                building(11, 5, 3),
            ],
        }
        with patch.object(
            server, "query_all_owned_fief_ids", return_value=[100],
        ), patch.object(
            server, "query_fief_buildings", return_value=state,
        ):
            plan = server.starter_refresh_fief_buildings(sess)
        self.assertEqual(plan["nextAction"]["buildingType"], 1)
        self.assertEqual(plan["nextAction"]["slot"], 9)
        self.assertIn("人口不足", plan["nextAction"]["reason"])


if __name__ == "__main__":
    unittest.main()
