from __future__ import annotations

import importlib.util
import json
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = ROOT / "shared_core" / "python"
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
FIXTURE_PATH = ROOT / "shared_core" / "protocol_parity_fixtures.json"
if str(CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CORE_SOURCE))

from dwpm_core.features.dungeon import (
    dungeon_battle_defeat_confirmed,
    dungeon_battle_texts,
    dungeon_chapter_number,
    dungeon_chest_index,
    dungeon_stage_completed_in_catalog,
    dungeon_stage_number,
    first_uncompleted_dungeon_stage,
    is_dungeon_pending_chest_error,
    normalize_dungeon_mode,
    parse_dungeon_catalog,
    parse_dungeon_state,
    resolve_dungeon_stage_code,
)
from dwpm_core.features.lossless import (
    evaluate_level10_guard_lineup,
    lossless_level_number,
    lossless_status_phase,
    parse_lossless_catalog,
    parse_lossless_lineup,
    parse_lossless_select_response,
    parse_lossless_settlement,
    parse_lossless_status,
)
from dwpm_core.features.raid import (
    build_raid_fief_list_payload,
    parse_raid_fief_list,
)
from dwpm_core.protocol.wire import encode_utf


SPEC = importlib.util.spec_from_file_location(
    "dwpm_server_battle_feature_parity",
    SERVER_PATH,
)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class SharedBattleFeatureProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.fixtures = payload["fixtures"]

    def test_raid_fief_query_runs_in_shared_core(self) -> None:
        fixture = self.fixtures["raidFief8310"]
        expected = fixture["expected"]
        payload = bytes.fromhex(fixture["responseHex"])
        parsed = parse_raid_fief_list(payload)

        self.assertEqual(
            build_raid_fief_list_payload(fixture["playerName"]).hex(),
            fixture["requestPayloadHex"],
        )
        self.assertEqual(
            SERVER.build_raid_fief_list_payload(fixture["playerName"]),
            build_raid_fief_list_payload(fixture["playerName"]),
        )
        self.assertEqual(SERVER.parse_raid_fief_list(payload), parsed)
        first = parsed["fiefs"][0]
        self.assertEqual(parsed["playerName"], expected["playerName"])
        self.assertEqual(parsed["country"], expected["country"])
        self.assertEqual(parsed["count"], expected["count"])
        self.assertEqual(first["targetId"], expected["firstTargetId"])
        self.assertEqual(first["name"], expected["firstName"])
        self.assertEqual(first["cityName"], expected["firstCityName"])
        self.assertEqual(first["x"], expected["firstX"])
        self.assertEqual(first["y"], expected["firstY"])

    def test_lossless_status_and_settlement_run_in_shared_core(self) -> None:
        status_fixture = self.fixtures["losslessCooldown8900"]
        status_payload = bytes.fromhex(status_fixture["responseHex"])
        status = parse_lossless_status(status_payload)
        expected = status_fixture["expected"]

        self.assertEqual(SERVER.parse_lossless_status(status_payload), status)
        self.assertEqual(status["phase"], expected["phase"])
        self.assertEqual(status["mode"], expected["mode"])
        self.assertEqual(
            status["remainingAttempts"],
            expected["remainingAttempts"],
        )
        self.assertEqual(status["actionTimerMs"], expected["actionTimerMillis"])
        self.assertEqual(status["cooldownMs"], expected["cooldownMillis"])
        self.assertEqual(status["reopenCost"], expected["reopenCost"])
        self.assertEqual(
            SERVER.lossless_status_phase(status),
            lossless_status_phase(status),
        )

        settlement_fixture = self.fixtures["losslessSettlement8902Failed"]
        settlement_payload = bytes.fromhex(settlement_fixture["responseHex"])
        settlement = parse_lossless_settlement(settlement_payload)
        self.assertEqual(
            SERVER.parse_lossless_settlement(settlement_payload),
            settlement,
        )
        for key, value in settlement_fixture["expected"].items():
            self.assertEqual(settlement[key], value)

    def test_lossless_catalog_lineup_and_selection_run_in_shared_core(self) -> None:
        catalog_payload = (
            struct.pack(">iqB", 1, 9, 10)
            + encode_utf("10级")
            + struct.pack(">iH", 1, 12305)
            + encode_utf("卫兵")
        )
        catalog = parse_lossless_catalog(catalog_payload)
        self.assertEqual(SERVER.parse_lossless_catalog(catalog_payload), catalog)
        self.assertEqual(catalog["levelCount"], 1)
        self.assertEqual(catalog["levels"][0]["level"], 10)
        self.assertEqual(catalog["levels"][0]["stages"][0]["stageId"], 12305)

        lineup_payload = (
            struct.pack(">BH", 0, 12305)
            + encode_utf("10级")
            + encode_utf("卫兵")
            + struct.pack(">i", 1)
            + encode_utf("守将甲")
            + struct.pack(">iHi", 7, 8, 9)
            + encode_utf("投石车")
            + struct.pack(">i", 1200)
        )
        lineup = parse_lossless_lineup(lineup_payload)
        self.assertEqual(SERVER.parse_lossless_lineup(lineup_payload), lineup)
        self.assertTrue(lineup["success"])
        self.assertEqual(lineup["enemies"][0]["soldierType"], "投石车")
        self.assertEqual(lineup["enemies"][0]["soldierCount"], 1200)

        select_payload = (
            struct.pack(">i", 1)
            + encode_utf("选择成功")
            + struct.pack(">qH", 9, 12305)
        )
        selection = parse_lossless_select_response(select_payload)
        self.assertEqual(
            SERVER.parse_lossless_select_response(select_payload),
            selection,
        )
        self.assertTrue(selection["success"])
        self.assertEqual(selection["selectedLevel"], 10)
        self.assertEqual(selection["stageId"], 12305)

    def test_lossless_guard_and_level_rules_run_in_shared_core(self) -> None:
        fixture = self.fixtures["losslessLevel10LastChariot"]
        lineup = {
            "stageId": fixture["stageId"],
            "stageName": fixture["stageName"],
            "enemies": [
                {
                    "position": index + 1,
                    "soldierType": soldier_type,
                    "soldierCount": 100,
                }
                for index, soldier_type in enumerate(fixture["soldierTypes"])
            ],
        }
        verdict = evaluate_level10_guard_lineup(lineup)

        self.assertEqual(SERVER.evaluate_level10_guard_lineup(lineup), verdict)
        for key, value in fixture["expected"].items():
            self.assertEqual(verdict[key], value)
        for value in (1, "10级"):
            self.assertEqual(
                SERVER.lossless_level_number(value),
                lossless_level_number(value),
            )

    def test_dungeon_catalog_progression_and_state_run_in_shared_core(self) -> None:
        catalog_fixture = self.fixtures["dungeonCatalog8930"]
        expected = catalog_fixture["expected"]
        payload = bytes.fromhex(catalog_fixture["responseHex"])
        catalog = parse_dungeon_catalog(payload)

        self.assertEqual(SERVER.parse_dungeon_catalog(payload), catalog)
        first = catalog["chapters"][0]
        self.assertEqual(len(catalog["chapters"]), expected["chapterCount"])
        self.assertEqual(first["name"], expected["firstChapterName"])
        self.assertEqual(len(first["stages"]), expected["firstChapterStageCount"])
        selection = first_uncompleted_dungeon_stage(catalog)
        self.assertEqual(
            SERVER.first_uncompleted_dungeon_stage(catalog),
            selection,
        )
        assert selection is not None
        self.assertEqual(selection["chapter"], expected["firstUncompletedChapter"])
        self.assertEqual(
            selection["stage"],
            expected["firstUncompletedDisplayStage"],
        )
        self.assertEqual(
            selection["stageCode"],
            expected["firstUncompletedStageCode"],
        )
        self.assertEqual(
            resolve_dungeon_stage_code(catalog, 6, 11),
            expected["chapter7DisplayStage11Code"],
        )
        self.assertEqual(
            SERVER.resolve_dungeon_stage_code(catalog, 6, 11),
            resolve_dungeon_stage_code(catalog, 6, 11),
        )
        self.assertFalse(
            dungeon_stage_completed_in_catalog(catalog, selection)
        )

        state_fixture = self.fixtures["dungeonStateAndPoll"]
        for response_name in ("idleResponseHex", "fightingResponseHex"):
            state_payload = bytes.fromhex(state_fixture[response_name])
            self.assertEqual(
                SERVER.parse_dungeon_state(state_payload),
                parse_dungeon_state(state_payload),
            )
        active = parse_dungeon_state(
            bytes.fromhex(state_fixture["fightingResponseHex"])
        )
        self.assertEqual(active["battleId"], state_fixture["expected"]["battleId"])

    def test_dungeon_input_and_terminal_rules_are_shared(self) -> None:
        cases = (
            (SERVER.normalize_dungeon_mode("打通"), normalize_dungeon_mode("打通")),
            (SERVER.dungeon_chapter_number("第三章"), dungeon_chapter_number("第三章")),
            (SERVER.dungeon_stage_number("11", 6), dungeon_stage_number("11", 6)),
            (SERVER.dungeon_chest_index("右"), dungeon_chest_index("右")),
            (
                SERVER.is_dungeon_pending_chest_error(
                    "副本个人状态异常：非空闲状态"
                ),
                is_dungeon_pending_chest_error(
                    "副本个人状态异常：非空闲状态"
                ),
            ),
            (
                SERVER.dungeon_battle_defeat_confirmed(
                    {"message": "本次挑战失败"}
                ),
                dungeon_battle_defeat_confirmed(
                    {"message": "本次挑战失败"}
                ),
            ),
            (
                SERVER._dungeon_battle_texts(
                    {"chestResult": {"textPreview": "本场战斗战败"}}
                ),
                dungeon_battle_texts(
                    {"chestResult": {"textPreview": "本场战斗战败"}}
                ),
            ),
        )
        for desktop, shared in cases:
            self.assertEqual(desktop, shared)


if __name__ == "__main__":
    unittest.main()
