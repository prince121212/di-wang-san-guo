from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
CONTRACT_PATH = ROOT / "shared_core" / "assistant_behavior_contract.json"
SPEC = importlib.util.spec_from_file_location("dwpm_server_shared_contract_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


def packet(opcode: int, payload: bytes) -> dict:
    return {"opcode": opcode, "payload": payload, "len": len(payload), "frag": 0}


class SharedBehaviorContractTests(unittest.TestCase):
    def test_desktop_loads_repository_contract(self) -> None:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(SERVER.SHARED_BEHAVIOR_CONTRACT_SOURCE, str(CONTRACT_PATH))
        self.assertEqual(
            SERVER.DAILY_SIGN_IN_REQUEST_OPCODE,
            int(contract["daily"]["signIn"]["requestOpcode"], 0),
        )
        self.assertEqual(
            SERVER.DAILY_SIGN_IN_ACTIVITY_OPCODE,
            int(contract["daily"]["signIn"]["activityResponseOpcode"], 0),
        )
        self.assertEqual(
            SERVER.DAILY_FAILED_FEATURE_RETRY_MS,
            int(contract["daily"]["schedule"]["failedFeatureRetryMillis"]),
        )
        lifecycle = contract["accountLifecycle"]
        self.assertTrue(lifecycle["startedRequiresExecutionOwner"])
        self.assertTrue(lifecycle["startRunsFreshLogin"])
        self.assertEqual(
            SERVER.CLIENT_HEARTBEAT_INTERVAL_SEC,
            lifecycle["heartbeatIntervalMillis"] / 1000,
        )
        self.assertEqual(SERVER.ACCOUNT_STATUS_TEXT, lifecycle["statusText"])
        for status, text in lifecycle["statusText"].items():
            self.assertEqual(SERVER.account_status_text(status), text)
        scheduler = contract["scheduler"]
        self.assertEqual(
            SERVER.RESIDENT_TASK_PRIORITIES,
            scheduler["residentPriority"],
        )
        self.assertEqual(
            [key for key, _label in SERVER.RESIDENT_TASKS],
            ["mine", "lossless", "brushYellow", "raid", "dungeon", "ministry"],
        )
        self.assertTrue(scheduler["sameGeneralMutualExclusionRequired"])
        self.assertTrue(scheduler["onlyRunnableResidentBlocksLowerPriority"])
        self.assertFalse(scheduler["formationPrerequisiteRunsFirst"])
        self.assertFalse(scheduler["dailyFeaturesRunBeforeResidents"])
        self.assertTrue(scheduler["militaryLaneRunsBeforeIdleLane"])
        self.assertTrue(scheduler["expeditionPreparationIsTaskScoped"])
        self.assertTrue(scheduler["idleLaneMustYieldToDueMilitaryWork"])
        self.assertTrue(scheduler["observationRefreshMayRunBetweenLanes"])
        self.assertTrue(scheduler["waitStatePersistsAcrossProcess"])
        self.assertTrue(scheduler["dayBoundaryUsesContractTimezone"])
        actions = contract["daily"]["actions"]
        self.assertEqual(
            SERVER.DAILY_ARENA_READ_OPCODE,
            int(actions["arenaCoins"]["readRequestOpcode"], 0),
        )
        self.assertEqual(
            SERVER.DAILY_ARENA_CLAIM_OPCODE,
            int(actions["arenaCoins"]["claimRequestOpcode"], 0),
        )
        self.assertEqual(
            SERVER.DAILY_DONATE_RESOURCE_OPCODE,
            int(actions["donate"]["resourceRequestOpcode"], 0),
        )
        self.assertEqual(
            SERVER.DAILY_DONATE_TECH_OPCODE,
            int(actions["donate"]["technologyRequestOpcode"], 0),
        )
        self.assertEqual(
            SERVER.DAILY_SALARY_REQUEST_OPCODE,
            int(actions["salary"]["requestOpcode"], 0),
        )
        self.assertEqual(
            SERVER.DAILY_NATIONAL_LIST_RESPONSE_OPCODE,
            int(actions["nationalCollect"]["cityListResponseOpcode"], 0),
        )
        self.assertEqual(actions["nationalCollect"]["responseHeaderBytes"], 7)
        self.assertEqual(actions["nationalCollect"]["includedListCategories"], [1, 2, 3])
        self.assertEqual(
            SERVER.DAILY_OWNED_CITY_OPCODE,
            int(actions["cityLordCollect"]["ownedCityRequestOpcode"], 0),
        )
        self.assertEqual(
            SERVER.DAILY_OWNED_CITY_RESPONSE_OPCODE,
            int(actions["cityLordCollect"]["ownedCityResponseOpcode"], 0),
        )
        self.assertEqual(
            SERVER.DAILY_GENERAL_LIST_OPCODE,
            int(actions["generalVisit"]["listRequestOpcode"], 0),
        )
        self.assertEqual(
            SERVER.DAILY_GENERAL_VISIT_RESPONSE_OPCODE,
            int(actions["generalVisit"]["visitResponseOpcode"], 0),
        )
        self.assertEqual(actions["generalVisit"]["alreadyVisitedStatus"], -2)
        self.assertIn(
            "拒绝了阁下的邀请",
            actions["generalVisit"]["invitationResolvedMarkers"],
        )
        expedition = contract["expedition"]
        self.assertEqual(
            SERVER.BRUSH_PREPARE_OPCODE,
            int(expedition["prepareOpcode"], 0),
        )
        self.assertEqual(
            SERVER.BRUSH_DISPATCH_RESPONSE_OPCODE,
            int(expedition["dispatchResponseOpcode"], 0),
        )
        self.assertTrue(expedition["dispatchSuccessRequiresPositiveBattleId"])
        self.assertEqual(
            SERVER.BRUSH_SOFT_REJECT_PAYLOAD_HEX,
            expedition["softRejectPayloadHex"],
        )
        formation = contract["formation"]
        self.assertEqual(SERVER.FORMATION_ASSIGN_REQUEST_OPCODE, int(formation["assignRequestOpcode"], 0))
        self.assertEqual(SERVER.FORMATION_ASSIGN_RESPONSE_OPCODE, int(formation["assignResponseOpcode"], 0))
        self.assertEqual(SERVER.FORMATION_REFILL_REQUEST_OPCODE, int(formation["refillRequestOpcode"], 0))
        self.assertEqual(SERVER.FORMATION_REFILL_RESPONSE_OPCODE, int(formation["refillResponseOpcode"], 0))
        self.assertTrue(formation["precheckIdleSoldierInventory"])
        self.assertTrue(formation["assignmentDoesNotImplicitlyRefill"])
        self.assertGreater(formation["completedSleepMillis"], 0)
        map_search = contract["mapSearch"]
        self.assertEqual(SERVER.BRUSH_WORLD_X_MAX, map_search["world"]["xMax"])
        self.assertEqual(SERVER.BRUSH_WORLD_Y_MAX, map_search["world"]["yMax"])
        self.assertEqual(SERVER.BRUSH_WORLD_STEP, map_search["world"]["step"])
        self.assertEqual(SERVER.BRUSH_SCAN_BATCH_SIZE, map_search["nearbyRequestLimit"])
        self.assertEqual(SERVER.BRUSH_FULL_SCAN_LIMIT, map_search["fullRequestLimit"])
        self.assertEqual(
            SERVER.BRUSH_SCAN_CACHE_TTL_MS,
            map_search["scanCoordinateCacheTtlMillis"],
        )
        self.assertEqual(
            SERVER.SHARED_MAP_TARGET_TTL_MS,
            map_search["targetCacheTtlMillis"],
        )
        brush = contract["brushYellow"]
        self.assertEqual(SERVER.BRUSH_MIN_ROLE_LEVEL, brush["minimumRoleLevel"])
        self.assertEqual(
            SERVER.BRUSH_MAX_GENERALS_PER_FORMATION,
            brush["maximumGeneralsPerFormation"],
        )
        self.assertEqual(SERVER.BRUSH_ACTION_TYPE, brush["actionType"])
        self.assertTrue(brush["exactSelectedLevelsRequired"])
        self.assertEqual(
            SERVER.MINE_PREPARE_OPCODE,
            int(contract["mine"]["prepareOpcode"], 0),
        )
        self.assertEqual(
            SERVER.MINE_DISPATCH_RESPONSE_OPCODE,
            int(contract["mine"]["dispatchResponseOpcode"], 0),
        )
        self.assertEqual(
            SERVER.MINE_WITHDRAW_REQUEST_OPCODE,
            int(contract["mine"]["withdraw"]["requestOpcode"], 0),
        )
        self.assertEqual(
            SERVER.MINE_WITHDRAW_RESPONSE_OPCODE,
            int(contract["mine"]["withdraw"]["responseOpcode"], 0),
        )
        self.assertEqual(
            SERVER.RAID_FIEF_QUERY_OPCODE,
            int(contract["raid"]["fiefQueryOpcode"], 0),
        )
        self.assertEqual(
            SERVER.RAID_FIEF_QUERY_RESPONSE_OPCODE,
            int(contract["raid"]["fiefQueryResponseOpcode"], 0),
        )
        self.assertEqual(
            SERVER.MILITARY_SNAPSHOT_REQUEST_OPCODE,
            int(contract["militarySnapshot"]["requestOpcode"], 0),
        )
        self.assertEqual(
            SERVER.MILITARY_SNAPSHOT_RESPONSE_OPCODE,
            int(contract["militarySnapshot"]["responseOpcode"], 0),
        )
        lossless = contract["lossless"]
        self.assertEqual(SERVER.LOSSLESS_ACTION_TYPE, lossless["actionType"])
        self.assertEqual(SERVER.LOSSLESS_DAILY_LIMIT, lossless["serverDailyLimit"])
        self.assertEqual(
            SERVER.LOSSLESS_STATUS_REQUEST_OPCODE,
            int(lossless["statusRequestOpcode"], 0),
        )
        self.assertEqual(
            SERVER.LOSSLESS_PREPARE_RESPONSE_OPCODE,
            int(lossless["prepareResponseOpcode"], 0),
        )
        self.assertEqual(
            SERVER.LOSSLESS_DISPATCH_RESPONSE_OPCODE,
            int(lossless["dispatchResponseOpcode"], 0),
        )
        self.assertFalse(lossless["fullTroopsDefault"])
        self.assertTrue(lossless["level10Guard"]["lastChariotMustBeCatapult"])
        dungeon = contract["dungeon"]
        self.assertEqual(SERVER.DUNGEON_ACTION_TYPE, dungeon["actionType"])
        self.assertEqual(
            (SERVER.DUNGEON_MODE_LOOP, SERVER.DUNGEON_MODE_CLEAR),
            tuple(dungeon["allowedModes"]),
        )
        self.assertEqual(
            SERVER.DUNGEON_CATALOG_REQUEST_OPCODE,
            int(dungeon["catalogRequestOpcode"], 0),
        )
        self.assertEqual(
            SERVER.DUNGEON_CHEST_RESPONSE_OPCODE,
            int(dungeon["chestResponseOpcode"], 0),
        )
        self.assertTrue(dungeon["clearModeSkipsMultiplayerFinals"])
        self.assertTrue(dungeon["clearModeRequiresCatalogConfirmation"])
        self.assertTrue(dungeon["clearModePausesOnDefeat"])

    def test_mine_withdraw_payload_comes_from_shared_contract(self) -> None:
        battle_id = 0x123456789
        payload = SERVER.build_mine_recall_payload(battle_id)
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))["mine"]["withdraw"]
        self.assertEqual(payload[:2].hex(), contract["payloadPrefixHex"])
        self.assertEqual(payload[-1:].hex(), contract["payloadSuffixHex"])
        self.assertEqual(int.from_bytes(payload[2:10], "big"), battle_id)

    def test_desktop_and_contract_accept_live_8134_success_and_duplicate(self) -> None:
        reward = "铜钱:10000获得成功。粮食:30000获得成功。"
        fresh = SERVER.parse_daily_sign_in_packets([
            packet(0x8134, b"\x00\x00\x0bactivity-list-data" + SERVER.utf(reward))
        ])
        duplicate = SERVER.parse_daily_sign_in_packets([
            packet(0x8134, b"\x0a\x00\x01" + SERVER.utf("本日已签到"))
        ])
        self.assertTrue(fresh["success"])
        self.assertTrue(duplicate["success"])
        self.assertTrue(duplicate["duplicateClaim"])
        self.assertEqual(duplicate["message"], SERVER.DAILY_SIGN_IN_DUPLICATE_LOG)

    def test_legacy_e202_empty_reply_remains_idempotent_success(self) -> None:
        parsed = SERVER.parse_daily_sign_in_packets([packet(0xE202, b"")])
        self.assertTrue(parsed["success"])
        self.assertEqual(parsed["message"], "签到请求已由服务器确认")

    def test_expired_diamond_box_is_completed_not_failure(self) -> None:
        payload = b"\x00\x00\x01activity\x00\x00\x0a" + SERVER.utf("操作失败，活动已过期。")
        parsed = SERVER.parse_daily_diamond_box_response(payload)
        self.assertTrue(parsed["success"])
        self.assertTrue(parsed["alreadyClaimed"])

    def test_failed_daily_feature_is_retried_during_same_day(self) -> None:
        session: dict = {}
        settings = {"autoSignIn": True}
        failure = {"autoSignIn": {"success": False, "completed": False}}
        success = {"autoSignIn": {"success": True, "completed": True}}
        habits = {"config": {"dailyTasks": settings}}

        with (
            mock.patch.object(SERVER, "persist_runtime_state"),
            mock.patch.object(SERVER, "current_daily_task_completions", return_value=[]),
            mock.patch.object(SERVER, "load_account_habits", return_value=habits),
            mock.patch.object(
                SERVER,
                "execute_daily_once_tasks",
                side_effect=[failure, success],
            ) as execute,
        ):
            SERVER.execute_scheduled_daily_tasks_once(session, settings)
            self.assertEqual(session["dailyAutomationPendingKeys"], ["autoSignIn"])
            self.assertGreater(session["dailyAutomationRetryAt"], 0)

            session["dailyAutomationRetryAt"] = 0
            self.assertTrue(SERVER.execute_daily_automation_after_midnight(session))
            self.assertEqual(execute.call_count, 2)
            self.assertEqual(session["dailyAutomationPendingKeys"], [])
            self.assertEqual(session["dailyAutomationRetryAt"], 0)


if __name__ == "__main__":
    unittest.main()
