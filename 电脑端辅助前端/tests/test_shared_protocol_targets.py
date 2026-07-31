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

from dwpm_core.features.targets import (
    brush_scan_coordinates,
    dedupe_targets,
    match_composition,
    match_drop,
    mine_target_matches,
    normalize_brush_levels,
    normalize_drop_keyword,
    normalize_drop_keywords,
    parse_bandit_targets,
    parse_composition_code,
    parse_mine_resources,
    scan_targets,
    target_distance_squared,
    target_matches_search_filter,
)


SPEC = importlib.util.spec_from_file_location("dwpm_server_target_parity", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class SharedTargetProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.fixtures = payload["fixtures"]

    def test_bandit_8540_parser_runs_in_shared_core(self) -> None:
        fixture = self.fixtures["targetSearch8540Complete"]
        expected = fixture["expected"]
        payload = bytes.fromhex(fixture["responseHex"])
        targets = parse_bandit_targets(payload)

        self.assertEqual(SERVER.parse_8540_targets(payload), targets)
        self.assertEqual(len(targets), 1)
        target = targets[0]
        for key in (
            "id",
            "kind",
            "level",
            "x",
            "y",
            "resource1",
            "resource2",
            "lootIds",
            "compositionCode",
            "source",
        ):
            self.assertEqual(target[key], expected[key])
        self.assertEqual(
            [unit["soldierTypeCode"] for unit in target["units"]],
            expected["unitSoldierTypeCodes"],
        )

    def test_mine_8542_parser_runs_in_shared_core(self) -> None:
        fixture = self.fixtures["mineSearch8542Structured"]
        expected = fixture["expected"]
        payload = bytes.fromhex(fixture["responseHex"])
        resources = parse_mine_resources(payload)

        self.assertEqual(SERVER.parse_8542_resources(payload), resources)
        self.assertEqual(len(resources), expected["count"])
        for actual, wanted in zip(
            resources,
            (expected["occupied"], expected["empty"]),
        ):
            for key in (
                "id",
                "kind",
                "level",
                "x",
                "y",
                "ownerName",
                "ownerCountry",
                "playerOccupied",
                "isEmpty",
                "defenderCount",
            ):
                self.assertEqual(actual[key], wanted[key])
            self.assertEqual(actual["storage"], wanted["reserve"])
            self.assertEqual(
                actual["productionPerHour"],
                wanted["productionPerHour"],
            )

    def test_canonical_grid_runs_in_shared_core(self) -> None:
        fixture = self.fixtures["brushYellowCanonicalGridCenter100x30"]
        center = fixture["center"]
        coordinates = brush_scan_coordinates(
            center["x"],
            center["y"],
            fixture["limit"],
        )

        self.assertEqual(
            SERVER.brush_scan_coordinates(
                center["x"],
                center["y"],
                fixture["limit"],
            ),
            coordinates,
        )
        self.assertEqual(
            coordinates,
            [tuple(point) for point in fixture["expectedCoordinates"]],
        )

    def test_exact_bandit_levels_run_in_shared_core(self) -> None:
        fixture = self.fixtures["brushYellowExactLevels"]
        for target in fixture["targets"]:
            with self.subTest(target=target["id"]):
                actual = target_matches_search_filter(
                    target,
                    "山贼",
                    fixture["selectedLevels"],
                    [],
                    {},
                )
                self.assertEqual(actual, target["matches"])
                self.assertEqual(
                    SERVER.target_matches_search_filter(
                        target,
                        "山贼",
                        fixture["selectedLevels"],
                        [],
                        {},
                    ),
                    actual,
                )

    def test_exact_mine_level_and_ownership_run_in_shared_core(self) -> None:
        fixture = self.fixtures["mineExactLevelAndOwnership"]
        for target in fixture["targets"]:
            candidate = {
                "id": target["id"],
                "kind": target["mineType"],
                "level": target["level"],
                "isEmpty": target["isEmpty"],
                "playerOccupied": target["playerOccupied"],
            }
            with self.subTest(target=target["id"]):
                actual = mine_target_matches(
                    candidate,
                    resource_types=fixture["selectedMineTypes"],
                    levels=fixture["selectedLevels"],
                    only_empty=fixture["onlyEmpty"],
                )
                self.assertEqual(actual, target["matches"])
                self.assertEqual(
                    SERVER.mine_target_matches(
                        candidate,
                        resource_types=fixture["selectedMineTypes"],
                        levels=fixture["selectedLevels"],
                        only_empty=fixture["onlyEmpty"],
                    ),
                    actual,
                )

    def test_desktop_target_helpers_are_thin_shared_delegates(self) -> None:
        target = {
            "id": 1,
            "kind": "山贼",
            "level": 7,
            "x": 102,
            "y": 30,
            "resource": "资源 宝箱",
            "composition": {
                "foot": 1,
                "bow": 1,
                "cavalry": 0,
                "chariot": 0,
                "source": "8540-units",
            },
        }
        composition_filter = {"maxFoot": 1, "maxBow": 1, "requireFoot": True}
        marker_hex = self.fixtures["targetSearch8540Complete"]["responseHex"]

        cases = (
            (SERVER.scan_targets(marker_hex), scan_targets(marker_hex)),
            (
                SERVER.match_composition(target, composition_filter),
                match_composition(target, composition_filter),
            ),
            (SERVER.normalize_drop_keyword("粮草"), normalize_drop_keyword("粮草")),
            (
                SERVER.normalize_drop_keywords("资源,宝箱"),
                normalize_drop_keywords("资源,宝箱"),
            ),
            (SERVER.match_drop(target, ["宝箱"]), match_drop(target, ["宝箱"])),
            (
                SERVER.normalize_brush_levels("8,7,7"),
                normalize_brush_levels("8,7,7"),
            ),
            (
                SERVER.parse_composition_code("1步2弓3骑4车"),
                parse_composition_code("1步2弓3骑4车"),
            ),
            (
                SERVER.target_distance_squared(target, 100, 30),
                target_distance_squared(target, 100, 30),
            ),
            (
                SERVER.dedupe_targets([target, dict(target)]),
                dedupe_targets([target, dict(target)]),
            ),
        )
        for desktop, shared in cases:
            self.assertEqual(desktop, shared)


if __name__ == "__main__":
    unittest.main()
