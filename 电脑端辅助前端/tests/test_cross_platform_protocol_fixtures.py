from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
FIXTURE_PATH = ROOT / "shared_core" / "protocol_parity_fixtures.json"
SPEC = importlib.util.spec_from_file_location(
    "dwpm_server_cross_platform_protocol_test", SERVER_PATH
)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class CrossPlatformProtocolFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))[
            "fixtures"
        ]

    def test_target_search_8540_matches_shared_fixture(self) -> None:
        fixture = self.fixtures["targetSearch8540Complete"]
        expected = fixture["expected"]

        target = SERVER.parse_8540_targets(
            bytes.fromhex(fixture["responseHex"])
        )[0]

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
            target["composition"]["source"], expected["compositionSource"]
        )
        self.assertEqual(
            [unit["soldierTypeCode"] for unit in target["units"]],
            expected["unitSoldierTypeCodes"],
        )
        self.assertEqual(
            [unit["soldierCount"] for unit in target["units"]],
            expected["unitSoldierCounts"],
        )
        self.assertEqual(
            SERVER.action_target_hex(target),
            f"{expected['id']:016x}",
        )

    def test_brush_yellow_action_type_three_matches_shared_fixture(self) -> None:
        fixture = self.fixtures["brushYellowActionType3"]
        expected = fixture["expected"]

        prepare, dispatch = SERVER.build_brush_payloads(
            fixture["generalIdHexChunks"],
            fixture["targetIdHex"],
        )

        self.assertEqual(SERVER.BRUSH_ACTION_TYPE, expected["actionType"])
        self.assertEqual(prepare, expected["prepareGameHex"])
        self.assertEqual(dispatch, expected["dispatchGameHex"])

    def test_brush_yellow_grid_order_matches_shared_fixture(self) -> None:
        fixture = self.fixtures["brushYellowCanonicalGridCenter100x30"]
        center = fixture["center"]

        coordinates = SERVER.brush_scan_coordinates(
            center["x"], center["y"], fixture["limit"]
        )

        self.assertEqual(
            coordinates,
            [tuple(value) for value in fixture["expectedCoordinates"]],
        )
        self.assertTrue(all(x % 6 == 0 and y % 6 == 0 for x, y in coordinates))

    def test_brush_yellow_dispatch_receipts_match_shared_fixture(self) -> None:
        fixture = self.fixtures["brushYellowDispatchReceipts"]

        success = SERVER.parse_8522_dispatch_response(
            bytes.fromhex(fixture["successResponseHex"])
        )
        rejected = SERVER.parse_8522_dispatch_response(
            bytes.fromhex(fixture["softRejectResponseHex"])
        )

        self.assertTrue(success["success"])
        self.assertEqual(success["battleId"], fixture["expectedBattleId"])
        self.assertFalse(rejected["success"])

    def test_brush_yellow_exact_levels_match_shared_fixture(self) -> None:
        fixture = self.fixtures["brushYellowExactLevels"]
        for target in fixture["targets"]:
            with self.subTest(target=target["id"]):
                self.assertEqual(
                    SERVER.target_matches_search_filter(
                        target,
                        "山贼",
                        fixture["selectedLevels"],
                        [],
                        {},
                    ),
                    target["matches"],
                )

    def test_formation_assignment_and_refill_match_shared_fixtures(self) -> None:
        assignment = self.fixtures["formationAssign1226"]
        expected = assignment["expected"]
        payload = SERVER.build_assign_troops_payload(
            f"{assignment['generalId']:016x}",
            assignment["soldierTypeCode"],
            assignment["soldierCount"],
        )
        receipt = SERVER.parse_assign_troops_response(
            bytes.fromhex(assignment["successResponseHex"])
        )

        self.assertEqual(payload.hex(), assignment["requestPayloadHex"])
        self.assertEqual(receipt["success"], expected["success"])
        self.assertEqual(receipt["oldSoldierTypeCode"], expected["previousType"])
        self.assertEqual(receipt["oldSoldierCount"], expected["previousCount"])
        self.assertEqual(receipt["assignedSoldierTypeCode"], expected["assignedType"])
        self.assertEqual(receipt["assignedSoldierCount"], expected["assignedCount"])

        refill = self.fixtures["formationRefill1229"]
        refill_expected = refill["expected"]
        refill_payload = SERVER.build_refill_payload(
            [f"{value:016x}" for value in refill["generalIds"]]
        )
        refill_receipt = SERVER.parse_refill_response(
            bytes.fromhex(refill["successResponseHex"])
        )
        self.assertEqual(refill_payload.hex(), refill["requestPayloadHex"])
        self.assertEqual(refill_receipt["success"], refill_expected["success"])
        self.assertEqual(refill_receipt["message"], refill_expected["message"])
        self.assertEqual(len(refill_receipt["roleUpdates"]), refill_expected["entryCount"])
        self.assertEqual(refill_receipt["roleUpdates"][0]["armyType"], refill_expected["firstSoldierType"])
        self.assertEqual(refill_receipt["roleUpdates"][0]["armyCount"], refill_expected["firstSoldierCount"])

    def test_mine_action_type_and_payloads_match_shared_fixture(self) -> None:
        fixture = self.fixtures["mineActionType2"]
        expected = fixture["expected"]

        prepare, dispatch = SERVER.build_mine_payloads(
            [f"{value:016x}" for value in fixture["generalIds"]],
            fixture["targetId"],
        )

        self.assertEqual(SERVER.MINE_ACTION_TYPE, expected["actionType"])
        self.assertEqual(prepare.hex(), expected["preparePayloadHex"])
        self.assertEqual(dispatch.hex(), expected["dispatchPayloadHex"])
        prepare_length, prepare_opcode, prepare_from_game_hex = (
            SERVER.action_gamehex_to_cmd(expected["prepareGameHex"])
        )
        dispatch_length, dispatch_opcode, dispatch_from_game_hex = (
            SERVER.action_gamehex_to_cmd(expected["dispatchGameHex"])
        )
        self.assertEqual((prepare_length, prepare_opcode, prepare_from_game_hex), (
            len(prepare), SERVER.MINE_PREPARE_OPCODE, prepare
        ))
        self.assertEqual((dispatch_length, dispatch_opcode, dispatch_from_game_hex), (
            len(dispatch), SERVER.MINE_DISPATCH_OPCODE, dispatch
        ))

    def test_mine_search_8542_ownership_matches_shared_fixture(self) -> None:
        fixture = self.fixtures["mineSearch8542Structured"]
        expected = fixture["expected"]
        resources = SERVER.parse_8542_resources(
            bytes.fromhex(fixture["responseHex"])
        )

        self.assertEqual(len(resources), expected["count"])
        occupied, empty = resources
        for actual, wanted in ((occupied, expected["occupied"]), (empty, expected["empty"])):
            for key in (
                "id", "kind", "level", "x", "y", "ownerName", "ownerCountry",
                "playerOccupied", "isEmpty", "defenderCount",
            ):
                self.assertEqual(actual[key], wanted[key])
            self.assertEqual(actual["storage"], wanted["reserve"])
            self.assertEqual(
                actual["productionPerHour"], wanted["productionPerHour"]
            )
        self.assertEqual(
            occupied["defenders"][0]["generalName"],
            expected["occupied"]["firstDefenderName"],
        )
        self.assertEqual(occupied["meta"]["centerX"], expected["centerX"])
        self.assertEqual(occupied["meta"]["centerY"], expected["centerY"])

    def test_mine_preview_and_withdraw_match_shared_fixtures(self) -> None:
        preview_fixture = self.fixtures["minePreview8520"]
        preview = SERVER.parse_8520_mine_preview(
            bytes.fromhex(preview_fixture["responseHex"])
        )
        self.assertTrue(preview["valid"])
        for key in ("marchSeconds", "winRate", "x", "y"):
            self.assertEqual(preview[key], preview_fixture["expected"][key])

        withdraw_fixture = self.fixtures["mineWithdraw8526"]
        battle_id = withdraw_fixture["battleId"]
        self.assertEqual(
            SERVER.build_mine_recall_payload(battle_id).hex(),
            withdraw_fixture["requestPayloadHex"],
        )
        accepted = SERVER.parse_8526_recall_response(
            bytes.fromhex(withdraw_fixture["successResponseHex"]), battle_id
        )
        mismatched = SERVER.parse_8526_recall_response(
            bytes.fromhex(withdraw_fixture["mismatchedResponseHex"]), battle_id
        )
        self.assertTrue(accepted["success"])
        self.assertEqual(accepted["battleId"], battle_id)
        self.assertFalse(mismatched["success"])

    def test_mine_exact_level_ownership_and_speed_match_shared_fixtures(self) -> None:
        filter_fixture = self.fixtures["mineExactLevelAndOwnership"]
        for target in filter_fixture["targets"]:
            with self.subTest(target=target["id"]):
                self.assertEqual(
                    SERVER.mine_target_matches(
                        {
                            "id": target["id"],
                            "kind": target["mineType"],
                            "level": target["level"],
                            "isEmpty": target["isEmpty"],
                            "playerOccupied": target["playerOccupied"],
                        },
                        resource_types=filter_fixture["selectedMineTypes"],
                        levels=filter_fixture["selectedLevels"],
                        only_empty=filter_fixture["onlyEmpty"],
                    ),
                    target["matches"],
                )

        speed_fixture = self.fixtures["mineSmartSpeed"]
        self.assertEqual(
            SERVER.choose_march_speed_items(
                speed_fixture["remainingSeconds"], speed_fixture["inventory"]
            ),
            speed_fixture["expectedItemIds"],
        )

    def test_raid_action_type_and_payloads_match_shared_fixture(self) -> None:
        fixture = self.fixtures["raidActionType1"]
        expected = fixture["expected"]
        ids = [f"{value:016x}" for value in fixture["generalIds"]]
        prepare = SERVER.build_raid_prepare_payload(ids, fixture["targetId"])
        dispatch = SERVER.build_raid_expedition_payload(ids, fixture["targetId"])

        self.assertEqual(SERVER.RAID_ACTION_TYPE, expected["actionType"])
        self.assertEqual(prepare.hex(), expected["preparePayloadHex"])
        self.assertEqual(dispatch.hex(), expected["dispatchPayloadHex"])
        prepare_length, prepare_opcode, prepare_from_game_hex = (
            SERVER.action_gamehex_to_cmd(expected["prepareGameHex"])
        )
        dispatch_length, dispatch_opcode, dispatch_from_game_hex = (
            SERVER.action_gamehex_to_cmd(expected["dispatchGameHex"])
        )
        self.assertEqual((prepare_length, prepare_opcode, prepare_from_game_hex), (
            len(prepare), SERVER.RAID_PREPARE_OPCODE, prepare
        ))
        self.assertEqual((dispatch_length, dispatch_opcode, dispatch_from_game_hex), (
            len(dispatch), SERVER.RAID_DISPATCH_OPCODE, dispatch
        ))

    def test_raid_fief_and_dispatch_receipts_match_shared_fixtures(self) -> None:
        fief_fixture = self.fixtures["raidFief8310"]
        expected = fief_fixture["expected"]
        parsed = SERVER.parse_raid_fief_list(
            bytes.fromhex(fief_fixture["responseHex"])
        )
        first = parsed["fiefs"][0]

        self.assertEqual(
            SERVER.build_raid_fief_list_payload(fief_fixture["playerName"]).hex(),
            fief_fixture["requestPayloadHex"],
        )
        self.assertEqual(parsed["playerName"], expected["playerName"])
        self.assertEqual(parsed["country"], expected["country"])
        self.assertEqual(parsed["count"], expected["count"])
        self.assertEqual(first["targetId"], expected["firstTargetId"])
        self.assertEqual(first["name"], expected["firstName"])
        self.assertEqual(first["cityName"], expected["firstCityName"])
        self.assertEqual(first["x"], expected["firstX"])
        self.assertEqual(first["y"], expected["firstY"])

        receipt_fixture = self.fixtures["raidDispatchReceipts"]
        success = SERVER.parse_8522_dispatch_response(
            bytes.fromhex(receipt_fixture["successResponseHex"])
        )
        missing = SERVER.parse_8522_dispatch_response(
            bytes.fromhex(receipt_fixture["missingBattleIdResponseHex"])
        )
        rejected = SERVER.parse_8522_dispatch_response(
            bytes.fromhex(receipt_fixture["softRejectResponseHex"])
        )
        self.assertTrue(success["success"])
        self.assertEqual(success["battleId"], receipt_fixture["expectedBattleId"])
        self.assertFalse(missing["success"])
        self.assertFalse(rejected["success"])

    def test_lossless_status_settlement_and_payloads_match_shared_fixtures(self) -> None:
        status_fixture = self.fixtures["losslessCooldown8900"]
        status_expected = status_fixture["expected"]
        status = SERVER.parse_lossless_status(
            bytes.fromhex(status_fixture["responseHex"])
        )
        self.assertEqual(status["phase"], status_expected["phase"])
        self.assertEqual(status["mode"], status_expected["mode"])
        self.assertEqual(
            status["remainingAttempts"], status_expected["remainingAttempts"]
        )
        self.assertEqual(status["actionTimerMs"], status_expected["actionTimerMillis"])
        self.assertEqual(status["cooldownMs"], status_expected["cooldownMillis"])
        self.assertEqual(status["reopenCost"], status_expected["reopenCost"])

        settlement_fixture = self.fixtures["losslessSettlement8902Failed"]
        settlement_expected = settlement_fixture["expected"]
        settlement = SERVER.parse_lossless_settlement(
            bytes.fromhex(settlement_fixture["responseHex"])
        )
        for key in (
            "success", "battleFailed", "battleId", "resultText", "generalText"
        ):
            self.assertEqual(settlement[key], settlement_expected[key])

        action_fixture = self.fixtures["losslessActionType11"]
        action_expected = action_fixture["expected"]
        ids = [f"{value:016x}" for value in action_fixture["generalIds"]]
        prepare = SERVER.build_lossless_prepare_payload(ids, action_fixture["roleId"])
        dispatch = SERVER.build_lossless_expedition_payload(ids, action_fixture["roleId"])
        self.assertEqual(SERVER.LOSSLESS_ACTION_TYPE, action_expected["actionType"])
        self.assertEqual(prepare.hex(), action_expected["preparePayloadHex"])
        self.assertEqual(dispatch.hex(), action_expected["dispatchPayloadHex"])

    def test_lossless_level10_guard_matches_shared_fixture(self) -> None:
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
        verdict = SERVER.evaluate_level10_guard_lineup(lineup)
        expected = fixture["expected"]
        self.assertEqual(verdict["qualified"], expected["qualified"])
        self.assertEqual(verdict["chariotPositions"], expected["chariotPositions"])
        self.assertEqual(verdict["catapultPositions"], expected["catapultPositions"])

    def test_dungeon_payload_catalog_clear_selection_and_poll_match_shared_fixtures(self) -> None:
        action_fixture = self.fixtures["dungeonActionType14"]
        action_expected = action_fixture["expected"]
        ids = [f"{value:016x}" for value in action_fixture["generalIds"]]
        prepare = SERVER.build_dungeon_prepare_payload(ids, action_fixture["stageCode"])
        dispatch = SERVER.build_dungeon_expedition_payload(ids, action_fixture["stageCode"])
        self.assertEqual(SERVER.DUNGEON_ACTION_TYPE, action_expected["actionType"])
        self.assertEqual(prepare.hex(), action_expected["preparePayloadHex"])
        self.assertEqual(dispatch.hex(), action_expected["dispatchPayloadHex"])
        self.assertEqual(
            bytes([SERVER.dungeon_chest_index("右")]).hex(),
            action_expected["chestRightPayloadHex"],
        )

        catalog_fixture = self.fixtures["dungeonCatalog8930"]
        catalog_expected = catalog_fixture["expected"]
        catalog = SERVER.parse_dungeon_catalog(
            bytes.fromhex(catalog_fixture["responseHex"])
        )
        first = catalog["chapters"][0]
        self.assertEqual(len(catalog["chapters"]), catalog_expected["chapterCount"])
        self.assertEqual(first["name"], catalog_expected["firstChapterName"])
        self.assertEqual(
            len(first["stages"]), catalog_expected["firstChapterStageCount"]
        )
        self.assertEqual(first["stages"][2]["stageCode"], catalog_expected["displayStage3Code"])
        self.assertEqual(first["stages"][3]["stageCode"], catalog_expected["displayStage4Code"])
        selection = SERVER.first_uncompleted_dungeon_stage(catalog)
        self.assertIsNotNone(selection)
        self.assertEqual(selection["chapter"], catalog_expected["firstUncompletedChapter"])
        self.assertEqual(selection["stage"], catalog_expected["firstUncompletedDisplayStage"])
        self.assertEqual(selection["stageCode"], catalog_expected["firstUncompletedStageCode"])
        self.assertEqual(selection["available"], catalog_expected["firstUncompletedAvailable"])
        self.assertEqual(
            SERVER.resolve_dungeon_stage_code(catalog, 6, 11),
            catalog_expected["chapter7DisplayStage11Code"],
        )

        state_fixture = self.fixtures["dungeonStateAndPoll"]
        expected = state_fixture["expected"]
        self.assertFalse(
            SERVER.parse_dungeon_state(bytes.fromhex(state_fixture["idleResponseHex"]))["active"]
        )
        active = SERVER.parse_dungeon_state(
            bytes.fromhex(state_fixture["fightingResponseHex"])
        )
        reward_payload = bytes.fromhex(state_fixture["rewardResponseHex"])
        self.assertEqual(active["battleId"], expected["battleId"])
        self.assertEqual(reward_payload[1:9].hex(), f"{expected['battleId']:016x}")
        self.assertEqual(
            (bytes([2]) + expected["battleId"].to_bytes(8, "big")).hex(),
            expected["firstPollPayloadHex"],
        )
        self.assertEqual(
            (bytes([1]) + expected["battleId"].to_bytes(8, "big")).hex(),
            expected["nextPollPayloadHex"],
        )

    def test_daily_national_city_8404_samples_match_shared_fixtures(self) -> None:
        fixture_names = (
            "dailyNationalCity8404State",
            "dailyNationalCity8404Commandery",
            "dailyNationalCity8404County",
            "dailyNationalCity8404Small",
        )
        for fixture_name in fixture_names:
            with self.subTest(fixture=fixture_name):
                fixture = self.fixtures[fixture_name]
                expected = fixture["expected"]
                page = SERVER.parse_national_city_page(
                    bytes.fromhex(fixture["responseHex"]),
                    fixture["requestedCategory"],
                )
                city = page["cities"][0]
                self.assertEqual(page["category"], expected["category"])
                for key in ("name", "kind", "x", "y"):
                    self.assertEqual(city[key], expected[key])

    def test_daily_owned_city_8318_sample_matches_shared_fixture(self) -> None:
        fixture = self.fixtures["dailyOwnedCity8318Nanhua"]
        expected = fixture["expected"]
        parsed = SERVER.parse_owned_city_list(bytes.fromhex(fixture["responseHex"]))
        city = parsed["cities"][0]

        self.assertEqual(
            SERVER.build_owned_city_list_payload(fixture["roleId"]).hex(),
            fixture["requestHex"],
        )
        self.assertEqual(city["cityId"], expected["id"])
        for key in ("kindCode", "name", "x", "y", "ownerName", "ownerLevel"):
            self.assertEqual(city[key], expected[key])

    def test_daily_salary_a14b_sample_matches_shared_fixture(self) -> None:
        fixture = self.fixtures["dailySalaryA14bSuccess"]
        expected = fixture["expected"]
        parsed = SERVER.parse_salary_receipt(bytes.fromhex(fixture["responseHex"]))

        self.assertEqual(SERVER.build_salary_payload().hex(), fixture["requestHex"])
        for key in ("status", "extra", "success", "completed", "copper", "food"):
            self.assertEqual(parsed[key], expected[key])

    def test_daily_general_visit_a273_samples_match_shared_fixtures(self) -> None:
        for fixture_name in (
            "dailyGeneralVisitA273Rejected",
            "dailyGeneralVisitA273AlreadyVisited",
        ):
            with self.subTest(fixture=fixture_name):
                fixture = self.fixtures[fixture_name]
                expected = fixture["expected"]
                parsed = SERVER.parse_general_visit_receipt(
                    bytes.fromhex(fixture["responseHex"])
                )
                for key in (
                    "status",
                    "message",
                    "success",
                    "completed",
                    "recruited",
                    "alreadyVisited",
                    "invitationResolved",
                    "invitationRejected",
                ):
                    self.assertEqual(parsed[key], expected[key])

    def test_daily_general_visit_a271_duplicate_matches_shared_fixture(self) -> None:
        fixture = self.fixtures["dailyGeneralVisitA271AlreadyVisited"]
        expected = fixture["expected"]
        parsed = SERVER.parse_general_visit_page(bytes.fromhex(fixture["responseHex"]))

        self.assertEqual(parsed["status"], expected["status"])
        self.assertEqual(parsed["message"], expected["message"])
        self.assertEqual(len(parsed["candidates"]), expected["candidateCount"])
        self.assertEqual(
            SERVER.general_visit_already_visited(parsed["status"], parsed["message"]),
            expected["alreadyVisited"],
        )


if __name__ == "__main__":
    unittest.main()
