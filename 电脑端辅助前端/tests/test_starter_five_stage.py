import sys
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


class StarterFiveStageTest(unittest.TestCase):
    def test_under_thirty_policy_uses_no_bandit_map(self):
        policy = server.STARTER_LEVELING_POLICY["bandit"]
        self.assertEqual(policy["under30MapScope"], "none")
        self.assertEqual(
            policy["under30Strategy"],
            "search-and-dispatch",
        )
        snapshot = server.starter_snapshot({
            "roleState": {"level": 20},
            "role": {},
            "generals": [],
        })
        self.assertEqual(snapshot["mapScope"], "direct-search")

    def test_level_limits_follow_requested_steps(self):
        self.assertEqual(server.starter_allowed_extra_fief_count(9), 0)
        self.assertEqual(server.starter_allowed_extra_fief_count(10), 1)
        self.assertEqual(server.starter_allowed_extra_fief_count(20), 2)
        self.assertEqual(server.starter_allowed_extra_fief_count(40), 4)
        self.assertEqual(server.starter_target_general_count(9), 3)
        self.assertEqual(server.starter_target_general_count(10), 4)
        self.assertEqual(server.starter_target_general_count(15), 5)
        self.assertEqual(server.starter_target_general_count(20), 6)
        self.assertEqual(server.starter_target_general_count(25), 7)

    def test_stage_plan_cannot_skip_initial_combat(self):
        sess = {
            "roleState": {"level": 15},
            "generals": [{}, {}, {}, {}, {}],
            "starterDailySignInDate": server.time.strftime(
                "%Y-%m-%d", server.time.localtime(),
            ),
            "starterEarlyBanditCompletedLevels": [1, 2],
            "starterEarlyDungeonCompletedStages": 0,
        }
        with patch.object(
            server, "starter_last_action_finished_at",
            return_value=server.now_ms(),
        ):
            plan = server.starter_five_stage_plan("job", sess)
        self.assertEqual(plan["stage"], "five_stage_2")
        self.assertEqual(plan["actionType"], "five-stage-initial-combat")

    def test_reward_phase_has_priority_after_initial_combat(self):
        sess = {
            "roleState": {"level": 15},
            "generals": [{}, {}, {}, {}, {}],
            "starterDailySignInDate": server.time.strftime(
                "%Y-%m-%d", server.time.localtime(),
            ),
            "starterEarlyBanditCompletedLevels": [1, 2, 3],
            "starterEarlyDungeonCompletedStages": 2,
            "starterFiveStageDevelopmentLevel": 15,
            "starterFiveStageDevelopmentAuditedAt": server.now_ms(),
        }
        with patch.object(
            server, "starter_last_action_finished_at", return_value=0,
        ):
            plan = server.starter_five_stage_plan("job", sess)
        self.assertEqual(plan["stage"], "five_stage_5")
        self.assertEqual(plan["actionType"], "claim-rewards")

    def test_idle_combat_formation_runs_before_due_maintenance(self):
        sess = {
            "roleState": {"level": 20},
            "generals": [{
                "id": 1,
                "displayStatus": "闲",
                "troopLimit": 190,
                "soldierTypeCode": 3,
                "soldierCount": 190,
            }],
            "starterDailySignInDate": server.time.strftime(
                "%Y-%m-%d", server.time.localtime(),
            ),
            "starterEarlyBanditCompletedLevels": [1, 2, 3],
            "starterEarlyDungeonCompletedStages": 2,
            "starterFiveStageDevelopmentLevel": 19,
            "starterFiveStageDevelopmentAuditedAt": 0,
        }
        with patch.object(
            server, "starter_last_action_finished_at", return_value=0,
        ):
            plan = server.starter_five_stage_plan("", sess)
        self.assertTrue(plan["combatDue"])
        self.assertTrue(plan["rewardDue"])
        self.assertTrue(plan["developmentDue"])
        self.assertEqual(plan["actionType"], "five-stage-growth")

    def test_development_yields_one_turn_to_combat_after_each_success(self):
        sess = {
            "roleState": {"level": 20},
            "generals": [{}, {}, {}, {}, {}, {}],
            "starterDailySignInDate": server.time.strftime(
                "%Y-%m-%d", server.time.localtime(),
            ),
            "starterEarlyBanditCompletedLevels": [1, 2, 3],
            "starterEarlyDungeonCompletedStages": 2,
            "starterFiveStageDevelopmentLevel": 19,
            "starterFiveStageDevelopmentAuditedAt": 0,
        }
        with patch.object(
            server,
            "starter_last_action_finished_at",
            return_value=server.now_ms(),
        ), patch.object(
            server,
            "starter_last_successful_action_type",
            return_value="five-stage-development",
        ):
            combat_plan = server.starter_five_stage_plan("job", sess)
        self.assertTrue(combat_plan["developmentDue"])
        self.assertTrue(combat_plan["developmentYieldedToCombat"])
        self.assertEqual(combat_plan["actionType"], "five-stage-growth")

        with patch.object(
            server,
            "starter_last_action_finished_at",
            return_value=server.now_ms(),
        ), patch.object(
            server,
            "starter_last_successful_action_type",
            return_value="five-stage-growth",
        ):
            development_plan = server.starter_five_stage_plan("job", sess)
        self.assertTrue(development_plan["developmentDue"])
        self.assertFalse(development_plan["developmentYieldedToCombat"])
        self.assertEqual(
            development_plan["actionType"], "five-stage-development",
        )

    def test_first_extra_fief_only_builds_level_one_vehicle_camps(self):
        plan = {
            "fiefs": [{
                "fiefId": 200,
                "fiefName": "第一个封地",
                "fiveStageRole": "vehicle",
                "busyQueueCount": 0,
                "queueCapacity": 2,
                "buildings": [
                    {
                        "slot": slot,
                        "type": 6,
                        "name": "战车营",
                        "level": 1,
                        "busy": False,
                    }
                    for slot in range(1, 12)
                ],
            }],
        }
        action = server.starter_five_stage_required_fief_action(plan)
        self.assertEqual(action["kind"], "build-building")
        self.assertEqual(action["slot"], 12)
        self.assertEqual(action["buildingType"], 6)
        self.assertIsNone(action["previousLevel"])

    def test_other_fief_uses_academy_in_slot_three_and_houses_elsewhere(self):
        plan = {
            "fiefs": [{
                "fiefId": 300,
                "fiefName": "第二个封地",
                "fiveStageRole": "house",
                "busyQueueCount": 0,
                "queueCapacity": 2,
                "buildings": [],
            }],
        }
        action = server.starter_five_stage_required_fief_action(plan)
        self.assertEqual(action["kind"], "build-building")
        self.assertEqual(action["slot"], 1)
        self.assertEqual(action["buildingType"], 1)
        plan["fiefs"][0]["buildings"] = [
            {"slot": 1, "type": 1, "level": 1, "busy": False},
            {"slot": 2, "type": 1, "level": 1, "busy": False},
        ]
        action = server.starter_five_stage_required_fief_action(plan)
        self.assertEqual(action["slot"], 3)
        self.assertEqual(action["buildingType"], 3)

    def test_base_farm_is_demolished_before_fixed_layout(self):
        plan = {
            "fiefs": [{
                "fiefId": 100,
                "fiefName": "基地",
                "isBase": True,
                "busyQueueCount": 0,
                "queueCapacity": 2,
                "buildings": [
                    {"slot": 3, "type": 2, "name": "农场", "level": 1},
                    {"slot": 4, "type": 8, "name": "骑兵营", "level": 1},
                ],
            }],
        }
        action = server.starter_five_stage_base_building_action(plan)
        self.assertEqual(action["kind"], "demolish-building")
        self.assertEqual(action["slot"], 3)
        self.assertEqual(action["buildingType"], 2)

    def test_demolition_rechecks_until_the_slot_is_really_empty(self):
        sess = {
            "sessionId": "s1",
            "gameHttp": "http://game",
            "dm": 1,
        }
        with patch.object(
            server,
            "post_game",
            return_value=(200, b"", []),
        ), patch.object(
            server,
            "query_fief_buildings",
            side_effect=[
                {
                    "buildings": [{
                        "slot": 3,
                        "type": 2,
                        "name": "农场",
                    }],
                },
                {"buildings": []},
            ],
        ) as query, patch.object(server.time, "sleep"):
            result = server.execute_demolish_building_action(
                sess, 100, 3, 2,
            )
        self.assertTrue(result["success"])
        self.assertEqual(result["confirmedBy"], "提交后封地复查")
        self.assertEqual(query.call_count, 2)

    def test_base_optional_upgrade_never_selects_cavalry_camp(self):
        plan = {
            "fiefs": [{
                "fiefId": 100,
                "isBase": True,
                "busyQueueCount": 0,
                "queueCapacity": 2,
                "buildings": [
                    {"slot": 4, "type": 8, "level": 1, "busy": False},
                    {"slot": 11, "type": 5, "level": 1, "busy": False},
                    {"slot": 12, "type": 4, "level": 2, "busy": False},
                    {"slot": 1, "type": 1, "level": 1, "busy": False},
                ],
            }],
        }
        action = server.starter_five_stage_base_optional_upgrade(plan)
        self.assertIn(action["buildingType"], {4, 5})
        self.assertNotEqual(action["buildingType"], 8)

    def test_completed_base_cavalry_recruitment_stays_complete_after_losses(self):
        sess = {
            "starterFiveStageBaseCavalry": {
                "targetBaseIdle": 204,
                "speedOrdersUsed": 2,
                "completed": True,
                "observedBaseIdle": 211,
            },
        }
        plan = {
            "fiefs": [{
                "fiefId": 100,
                "isBase": True,
                "list1": [{"type": 3, "value": 202}],
                "buildings": [{
                    "slot": 4,
                    "type": 8,
                    "instanceId": 400,
                }],
            }],
        }
        result = server.starter_five_stage_base_cavalry_step(sess, plan)
        self.assertTrue(result["success"])
        self.assertTrue(result["completed"])
        self.assertIn("历史记录已确认完成", result["message"])

    def test_finished_cavalry_queue_completes_after_troops_are_assigned(self):
        sess = {
            "roleState": {"level": 20},
            "generals": [{
                "id": 1,
                "soldierTypeCode": 3,
                "soldierCount": 179,
            }],
            "starterFiveStageBaseCavalry": {
                "fiefId": 100,
                "buildingInstanceId": 400,
                "baselineBaseIdle": 14,
                "targetBaseIdle": 214,
                "targetCount": 200,
                "acceptedCount": 200,
                "submittedAt": 123,
                "speedOrdersUsed": 2,
            },
        }
        plan = {
            "fiefs": [{
                "fiefId": 100,
                "isBase": True,
                "list1": [{"type": 3, "value": 22}],
                "buildings": [{
                    "slot": 4,
                    "type": 8,
                    "instanceId": 400,
                    "nested": {"tasks": []},
                }],
            }],
        }
        with patch.object(
            server,
            "query_fief_buildings",
            return_value=plan["fiefs"][0],
        ), patch.object(server, "persist_runtime_state"):
            result = server.starter_five_stage_base_cavalry_step(
                sess, plan,
            )
        self.assertTrue(result["success"])
        self.assertTrue(result["completed"])
        self.assertIn("征兵队列已完成", result["message"])
        self.assertEqual(
            sess["starterFiveStageBaseCavalry"]["confirmedBy"],
            "accepted-order-and-empty-queue",
        )

    def test_only_190_light_cavalry_generals_are_dispatch_ready(self):
        sess = {
            "generals": [
                {
                    "id": 1, "displayStatus": "闲", "troopLimit": 300,
                    "soldierTypeCode": 3, "soldierCount": 190,
                },
                {
                    "id": 2, "displayStatus": "闲", "troopLimit": 300,
                    "soldierTypeCode": 3, "soldierCount": 189,
                },
                {
                    "id": 3, "displayStatus": "闲", "troopLimit": 180,
                    "soldierTypeCode": 3, "soldierCount": 180,
                },
            ],
        }
        ready = server.starter_five_stage_ready_cavalry_generals(
            sess, idle_only=True,
        )
        self.assertEqual([row["id"] for row in ready], [1])
        ready_100 = server.starter_five_stage_ready_cavalry_generals(
            sess, idle_only=True, minimum_count=100,
        )
        self.assertEqual([row["id"] for row in ready_100], [1, 2, 3])

    def test_assignment_bootstraps_low_capacity_general_with_100_cavalry(self):
        low = {
            "id": 2,
            "name": "低统兵将",
            "displayStatus": "闲",
            "troopLimit": 138,
            "soldierTypeCode": -1,
            "soldierCount": 0,
        }
        sess = {
            "generals": [low],
            "army": [{"soldierTypeCode": 3, "idleCount": 100}],
        }
        with patch.object(
            server, "refresh_generals", return_value=[low],
        ), patch.object(
            server,
            "execute_assign_troops",
            return_value={"success": True},
        ) as assign:
            result = server.starter_five_stage_assign_one_general(sess)
        self.assertTrue(result["success"])
        self.assertEqual(result["targetCavalryCount"], 100)
        assign.assert_called_once_with(
            sess, "2", "轻骑兵", 100, confirm="assign-troops",
        )

    def test_assignment_upgrades_100_to_190_after_capacity_increases(self):
        upgraded = {
            "id": 3,
            "name": "已升级统兵将",
            "displayStatus": "闲",
            "troopLimit": 220,
            "soldierTypeCode": 3,
            "soldierCount": 100,
        }
        sess = {
            "generals": [upgraded],
            "army": [{"soldierTypeCode": 3, "idleCount": 90}],
        }
        with patch.object(
            server, "refresh_generals", return_value=[upgraded],
        ), patch.object(
            server,
            "execute_assign_troops",
            return_value={"success": True},
        ) as assign:
            result = server.starter_five_stage_assign_one_general(sess)
        self.assertEqual(result["targetCavalryCount"], 190)
        assign.assert_called_once_with(
            sess, "3", "轻骑兵", 190, confirm="assign-troops",
        )

    def test_level_two_bandit_accepts_100_and_records_healing(self):
        general = {
            "id": 4,
            "name": "二级山贼将",
            "displayStatus": "闲",
            "troopLimit": 138,
            "soldierTypeCode": 3,
            "soldierCount": 100,
        }
        sess = {
            "roleState": {"level": 16},
            "generals": [general],
        }
        healing = {
            "success": True,
            "treatedFiefCount": 1,
            "message": "治疗完成",
        }
        target = {"id": "bandit-2", "level": 2, "x": 10, "y": 20}
        with patch.object(
            server,
            "starter_five_stage_heal_before_dispatch",
            return_value=healing,
        ), patch.object(
            server, "starter_cleanup_active_bandit_targets",
            return_value={},
        ) as cleanup_targets, patch.object(
            server, "recommend_brush_center", return_value={"x": 10, "y": 20},
        ), patch.object(
            server, "search_targets",
            return_value={"targets": [target], "requestCount": 1},
        ) as search, patch.object(
            server, "execute_brush", return_value={"success": True},
        ) as dispatch, patch.object(
            server, "reserve_shared_map_target",
        ) as reserve_target, patch.object(
            server, "update_shared_map_target_status",
        ) as update_target, patch.object(server, "persist_runtime_state"):
            result = server.execute_starter_five_stage_bandit_dispatch(
                sess, {"job_id": "job", "id": 1}, general,
                target_level=2,
            )
        self.assertTrue(result["success"])
        self.assertEqual(result["targetLevel"], 2)
        self.assertEqual(result["healing"], healing)
        dispatch.assert_called_once()
        self.assertTrue(search.call_args.kwargs["allow_under30"])
        self.assertTrue(result["directSearch"])
        self.assertFalse(result["sharedMap"])
        cleanup_targets.assert_not_called()
        reserve_target.assert_not_called()
        update_target.assert_not_called()
        self.assertEqual(
            sess["starterDirectBanditCursors"]["2"],
            0,
        )
        self.assertNotIn("starterFiveStageBanditScanStates", sess)

    def test_level_three_bandit_rejects_100_cavalry(self):
        general = {
            "id": 5,
            "name": "兵力未满将",
            "displayStatus": "闲",
            "troopLimit": 220,
            "soldierTypeCode": 3,
            "soldierCount": 100,
        }
        sess = {"roleState": {"level": 16}, "generals": [general]}
        with patch.object(
            server,
            "starter_five_stage_heal_before_dispatch",
            return_value={"success": True},
        ), patch.object(server, "search_targets") as search:
            result = server.execute_starter_five_stage_bandit_dispatch(
                sess, {"job_id": "job", "id": 1}, general,
                target_level=3,
            )
        self.assertTrue(result["deferred"])
        self.assertIn("未达到190", result["message"])
        search.assert_not_called()

    def test_healing_failure_prevents_bandit_dispatch(self):
        general = {
            "id": 6,
            "name": "待治疗将",
            "displayStatus": "闲",
            "troopLimit": 220,
            "soldierTypeCode": 3,
            "soldierCount": 190,
        }
        sess = {"roleState": {"level": 16}, "generals": [general]}
        with patch.object(
            server,
            "starter_five_stage_heal_before_dispatch",
            return_value={
                "success": False,
                "deferred": True,
                "message": "治疗未确认",
            },
        ), patch.object(server, "search_targets") as search, patch.object(
            server, "execute_brush",
        ) as dispatch:
            result = server.execute_starter_five_stage_bandit_dispatch(
                sess, {"job_id": "job", "id": 1}, general,
                target_level=3,
            )
        self.assertTrue(result["deferred"])
        self.assertEqual(result["healing"]["message"], "治疗未确认")
        search.assert_not_called()
        dispatch.assert_not_called()

    def test_growth_routes_100_cavalry_general_to_level_two_bandit(self):
        general = {
            "id": 7,
            "name": "百骑将",
            "displayStatus": "闲",
            "troopLimit": 144,
            "soldierTypeCode": 3,
            "soldierCount": 100,
        }
        sess = {"generals": [general]}
        with patch.object(
            server, "starter_restore_five_stage_state_from_actions",
        ), patch.object(
            server, "refresh_generals", return_value=[general],
        ), patch.object(
            server, "starter_five_stage_fief_states",
            return_value={"fiefs": []},
        ) as fief_states, patch.object(
            server, "starter_five_stage_base_building_action",
            return_value=None,
        ), patch.object(
            server, "starter_five_stage_base_cavalry_step",
            return_value={"completed": True},
        ), patch.object(
            server, "starter_five_stage_assign_one_general",
            return_value={"success": True, "skipped": True},
        ), patch.object(
            server,
            "execute_starter_five_stage_bandit_dispatch",
            return_value={"success": True},
        ) as dispatch, patch.object(server, "persist_runtime_state"):
            result = server.execute_starter_five_stage_growth(
                sess, {"job_id": "job"},
            )
        self.assertTrue(result["success"])
        dispatch.assert_called_once_with(
            sess, {"job_id": "job"}, general, target_level=2,
            yield_on_miss=True,
        )
        fief_states.assert_not_called()

    def test_growth_routes_non_reserved_190_general_to_level_three(self):
        reserved = {
            "id": 8,
            "name": "副本将",
            "displayStatus": "出",
            "troopLimit": 300,
            "soldierTypeCode": 3,
            "soldierCount": 190,
        }
        bandit = {
            "id": 9,
            "name": "三级山贼将",
            "displayStatus": "闲",
            "troopLimit": 220,
            "soldierTypeCode": 3,
            "soldierCount": 190,
        }
        sess = {
            "generals": [reserved, bandit],
            "starterFiveStageDungeonGeneralId": "8",
        }
        with patch.object(
            server, "starter_restore_five_stage_state_from_actions",
        ), patch.object(
            server, "refresh_generals", return_value=[reserved, bandit],
        ), patch.object(
            server, "starter_five_stage_fief_states",
            return_value={"fiefs": []},
        ), patch.object(
            server, "starter_five_stage_base_building_action",
            return_value=None,
        ), patch.object(
            server, "starter_five_stage_base_cavalry_step",
            return_value={"completed": True},
        ), patch.object(
            server, "starter_five_stage_assign_one_general",
            return_value={"success": True, "skipped": True},
        ), patch.object(
            server,
            "execute_starter_five_stage_bandit_dispatch",
            return_value={"success": True},
        ) as dispatch:
            result = server.execute_starter_five_stage_growth(
                sess, {"job_id": "job"},
            )
        self.assertTrue(result["success"])
        dispatch.assert_called_once_with(
            sess, {"job_id": "job"}, bandit, target_level=3,
            yield_on_miss=True,
        )

    def test_growth_dispatches_low_tier_bandit_before_reserved_dungeon(self):
        reserved = {
            "id": 10,
            "name": "副本保留将",
            "displayStatus": "闲",
            "troopLimit": 300,
            "soldierTypeCode": 3,
            "soldierCount": 190,
        }
        bandit = {
            "id": 11,
            "name": "百骑山贼将",
            "displayStatus": "闲",
            "troopLimit": 144,
            "soldierTypeCode": 3,
            "soldierCount": 100,
        }
        sess = {
            "generals": [reserved, bandit],
            "starterFiveStageDungeonGeneralId": "10",
        }
        with patch.object(
            server, "starter_restore_five_stage_state_from_actions",
        ), patch.object(
            server, "refresh_generals", return_value=[reserved, bandit],
        ), patch.object(
            server, "starter_five_stage_fief_states",
            return_value={"fiefs": []},
        ), patch.object(
            server, "starter_five_stage_base_building_action",
            return_value=None,
        ), patch.object(
            server, "starter_five_stage_base_cavalry_step",
            return_value={"completed": True},
        ), patch.object(
            server, "starter_five_stage_assign_one_general",
            return_value={"success": True, "skipped": True},
        ), patch.object(
            server,
            "execute_starter_five_stage_bandit_dispatch",
            return_value={"success": True},
        ) as dispatch, patch.object(
            server, "execute_starter_five_stage_dungeon_stage",
        ) as dungeon:
            result = server.execute_starter_five_stage_growth(
                sess, {"job_id": "job"},
            )
        self.assertTrue(result["success"])
        dispatch.assert_called_once_with(
            sess, {"job_id": "job"}, bandit, target_level=2,
            yield_on_miss=True,
        )
        dungeon.assert_not_called()

    def test_reserved_dungeon_general_below_190_is_never_routed_to_bandit(self):
        reserved = {
            "id": 15,
            "name": "副本保留将",
            "displayStatus": "闲",
            "troopLimit": 300,
            "soldierTypeCode": 3,
            "soldierCount": 181,
        }
        bandit = {
            "id": 16,
            "name": "山贼将",
            "displayStatus": "闲",
            "troopLimit": 180,
            "soldierTypeCode": 3,
            "soldierCount": 100,
        }
        sess = {
            "generals": [reserved, bandit],
            "starterFiveStageDungeonGeneralId": "15",
        }
        with patch.object(
            server,
            "execute_starter_five_stage_bandit_dispatch",
            return_value={"success": True},
        ) as dispatch:
            result = server.execute_starter_five_stage_ready_combat(
                sess, {"job_id": "job"},
            )
        self.assertTrue(result["success"])
        dispatch.assert_called_once_with(
            sess, {"job_id": "job"}, bandit, target_level=2,
            yield_on_miss=True,
        )

    def test_short_returned_formation_is_healed_and_refilled_before_planning(self):
        general = {
            "id": 17,
            "name": "归队将",
            "displayStatus": "闲",
            "troopLimit": 300,
            "soldierTypeCode": 3,
            "soldierCount": 96,
        }
        sess = {"generals": [general]}
        with patch.object(
            server, "starter_restore_five_stage_state_from_actions",
        ), patch.object(
            server, "refresh_generals", return_value=[general],
        ), patch.object(
            server, "starter_five_stage_heal_before_dispatch",
            return_value={"success": True},
        ) as heal, patch.object(
            server, "starter_five_stage_assign_one_general",
            return_value={
                "success": True,
                "skipped": False,
                "message": "已给归队将配置100轻骑兵",
            },
        ) as assign, patch.object(
            server, "starter_five_stage_fief_states",
        ) as fief_states:
            result = server.execute_starter_five_stage_growth(
                sess, {"job_id": "job"},
            )
        self.assertTrue(result["success"])
        self.assertIn("归队治疗后补兵", result["message"])
        heal.assert_called_once_with(sess, "起号编队归队")
        assign.assert_called_once_with(sess)
        fief_states.assert_not_called()

    def test_consecutive_dispatches_reuse_recent_all_fief_healing(self):
        cached = {
            "success": True,
            "checkedAt": server.now_ms(),
            "treatedFiefCount": 1,
        }
        sess = {"starterFiveStageRecentHealing": cached}
        with patch.object(
            server, "heal_all_wounded_before_military_prepare",
        ) as heal:
            result = server.starter_five_stage_heal_before_dispatch(
                sess, "起号2级山贼",
            )
        self.assertTrue(result["success"])
        self.assertTrue(result["reused"])
        heal.assert_not_called()

    def test_bandit_scan_miss_yields_without_blocking_dungeon(self):
        general = {
            "id": 12,
            "name": "扫描将",
            "displayStatus": "闲",
            "troopLimit": 144,
            "soldierTypeCode": 3,
            "soldierCount": 100,
        }
        sess = {
            "roleState": {"level": 20},
            "generals": [general],
        }
        with patch.object(
            server,
            "starter_five_stage_heal_before_dispatch",
            return_value={"success": True},
        ), patch.object(
            server, "starter_cleanup_active_bandit_targets",
            return_value={},
        ), patch.object(
            server, "recommend_brush_center", return_value={"x": 1, "y": 2},
        ), patch.object(
            server, "search_targets",
            return_value={"targets": [], "requestCount": 1},
        ), patch.object(server, "persist_runtime_state"):
            result = server.execute_starter_five_stage_bandit_dispatch(
                sess,
                {"job_id": "job", "id": 1},
                general,
                target_level=2,
                yield_on_miss=True,
            )
        self.assertTrue(result["success"])
        self.assertTrue(result["scanMiss"])
        self.assertFalse(result["deploymentSuccess"])
        self.assertFalse(result["deferred"])
        self.assertGreater(
            sess["starterFiveStageBanditRetryAt"]["12"],
            server.now_ms(),
        )

    def test_bandit_scan_cooldown_allows_reserved_dungeon_to_run(self):
        reserved = {
            "id": 13,
            "name": "副本将",
            "displayStatus": "闲",
            "troopLimit": 300,
            "soldierTypeCode": 3,
            "soldierCount": 190,
        }
        cooling = {
            "id": 14,
            "name": "冷却山贼将",
            "displayStatus": "闲",
            "troopLimit": 144,
            "soldierTypeCode": 3,
            "soldierCount": 100,
        }
        sess = {
            "generals": [reserved, cooling],
            "starterFiveStageDungeonGeneralId": "13",
            "starterFiveStageBanditRetryAt": {
                "14": server.now_ms() + 30_000,
            },
        }
        with patch.object(
            server, "starter_restore_five_stage_state_from_actions",
        ), patch.object(
            server, "refresh_generals", return_value=[reserved, cooling],
        ), patch.object(
            server, "starter_five_stage_fief_states",
            return_value={"fiefs": []},
        ), patch.object(
            server, "starter_five_stage_base_building_action",
            return_value=None,
        ), patch.object(
            server, "starter_five_stage_base_cavalry_step",
            return_value={"completed": True},
        ), patch.object(
            server, "starter_five_stage_assign_one_general",
            return_value={"success": True, "skipped": True},
        ), patch.object(
            server, "execute_starter_five_stage_bandit_dispatch",
        ) as bandit_dispatch, patch.object(
            server,
            "execute_starter_five_stage_dungeon_stage",
            return_value={"success": True},
        ) as dungeon:
            result = server.execute_starter_five_stage_growth(
                sess, {"job_id": "job"},
            )
        self.assertTrue(result["success"])
        bandit_dispatch.assert_not_called()
        dungeon.assert_called_once_with(
            sess, reserved, stage=2, loop=True,
        )

    def test_initial_dungeon_launches_without_waiting_for_settlement(self):
        general = {
            "id": 1,
            "name": "测试将领",
            "troopLimit": 300,
            "displayStatus": "闲",
            "soldierTypeCode": 3,
            "soldierCount": 190,
        }
        sess = {"generals": [general]}
        before = {
            "chapters": [{
                "chapterId": 0,
                "stages": [{"displayStage": 1, "resultCode": 255}],
            }],
        }
        with patch.object(
            server, "query_dungeon_catalog", return_value=before,
        ), patch.object(
            server,
            "execute_dungeon",
            return_value={
                "success": True,
                "launchConfirmedAt": server.now_ms(),
            },
        ) as execute, patch.object(
            server,
            "starter_five_stage_heal_before_dispatch",
            return_value={"success": True, "treatedFiefCount": 0},
        ), patch.object(
            server, "persist_runtime_state",
        ):
            result = server.execute_starter_five_stage_dungeon_stage(
                sess, general, stage=1, loop=False,
            )
        self.assertTrue(result["success"])
        self.assertTrue(result["deploymentSuccess"])
        self.assertTrue(result["dungeonLaunchedOnly"])
        self.assertNotIn("starterEarlyDungeonCompletedStages", sess)
        self.assertEqual(
            sess["starterFiveStageDungeonPending"]["stage"], 1,
        )
        self.assertTrue(execute.call_args.args[1]["launchOnly"])

    def test_reconnect_restores_legacy_chinese_bandit_milestone(self):
        with tempfile.TemporaryDirectory() as tempdir:
            database = Path(tempdir) / "assistant_state.sqlite3"
            with patch.object(server, "ACCOUNT_STATE_DB_FILE", database):
                with sqlite3.connect(database) as connection:
                    server._account_state_schema_v1(connection)
                    now = server.now_ms()
                    connection.execute(
                        """
                        INSERT INTO starter_action_queue(
                            job_id,action_key,action_type,priority,status,
                            payload_json,result_json,not_before,attempts,
                            created_at,updated_at,finished_at
                        ) VALUES(?,?,?,?,'success','{}',?,0,1,?,?,?)
                        """,
                        (
                            "job", "stage2", "five-stage-initial-combat", 1000,
                            json.dumps({
                                "success": True,
                                "message": "阶段2：已按顺序派出2级山贼",
                            }, ensure_ascii=False),
                            now, now, now,
                        ),
                    )
                    connection.commit()
                sess = {}
                server.starter_restore_five_stage_state_from_actions(
                    "job", sess,
                )
                self.assertEqual(
                    sess["starterEarlyBanditCompletedLevels"], [2],
                )

    def test_reconnect_restores_reserved_dungeon_general_from_launch(self):
        with tempfile.TemporaryDirectory() as tempdir:
            database = Path(tempdir) / "assistant_state.sqlite3"
            with patch.object(server, "ACCOUNT_STATE_DB_FILE", database):
                with sqlite3.connect(database) as connection:
                    server._account_state_schema_v1(connection)
                    now = server.now_ms()
                    connection.execute(
                        """
                        INSERT INTO starter_action_queue(
                            job_id,action_key,action_type,priority,status,
                            payload_json,result_json,not_before,attempts,
                            created_at,updated_at,finished_at
                        ) VALUES(?,?,?,?,'success','{}',?,0,1,?,?,?)
                        """,
                        (
                            "job", "dungeon-launch",
                            "five-stage-growth", 1000,
                            json.dumps({
                                "success": True,
                                "deploymentSuccess": True,
                                "dungeonLaunchedOnly": True,
                                "general": {
                                    "id": "151919647",
                                    "name": "蓟季",
                                },
                                "stage": {
                                    "chapter": 0,
                                    "stage": 2,
                                    "loop": True,
                                },
                                "battle": {"success": True},
                            }, ensure_ascii=False),
                            now, now, now,
                        ),
                    )
                    connection.commit()
                sess = {}
                server.starter_restore_five_stage_state_from_actions(
                    "job", sess,
                )
                self.assertEqual(
                    sess["starterFiveStageDungeonGeneralId"],
                    "151919647",
                )

    def test_dungeon_uses_prepare_then_expedition(self):
        sess = {
            "sessionId": "s1",
            "gameHttp": "http://game",
            "dm": 1,
            "role": {},
            "area": {},
        }
        general = {
            "id": 1,
            "idHex": "0000000000000001",
            "name": "测试将领",
            "displayStatus": "闲",
            "soldierTypeCode": 3,
            "soldierCount": 190,
        }
        prepare_payload = bytes.fromhex(
            "00000000000000000000000000000000000000000000ffffffff"
        )
        expedition_payload = server.utf("单人副本启动成功！")
        with patch.object(
            server, "dungeon_preflight_generals", return_value=[general],
        ), patch.object(
            server, "query_dungeon_catalog", return_value={},
        ), patch.object(
            server, "resolve_dungeon_stage_code", return_value=0,
        ), patch.object(
            server,
            "post_game",
            side_effect=[
                (
                    200,
                    b"",
                    [{
                        "opcode": 0x8520,
                        "len": len(prepare_payload),
                        "frag": 0,
                        "payload": prepare_payload,
                    }],
                ),
                (
                    200,
                    b"",
                    [{
                        "opcode": 0x8522,
                        "len": len(expedition_payload),
                        "frag": 0,
                        "payload": expedition_payload,
                    }],
                ),
            ],
        ) as post, patch.object(
            server,
            "wait_for_dungeon_generals_idle",
            return_value={"finished": True},
        ), patch.object(
            server,
            "query_dungeon_state",
            return_value={"active": False, "status": 0},
        ), patch.object(
            server,
            "query_dungeon_reward_state",
            return_value={},
        ), patch.object(
            server,
            "open_dungeon_chest",
            return_value={"success": True},
        ), patch.object(server.time, "sleep"):
            result = server.execute_dungeon(sess, {
                "confirm": "dungeon",
                "starterMode": True,
                "generalIds": ["1"],
                "chapter": "第一章",
                "stage": 1,
                "openChest": True,
            })
        self.assertTrue(result["success"])
        self.assertEqual(post.call_args_list[0].args[1][0][0], 0x1520)
        self.assertEqual(post.call_args_list[1].args[1][0][0], 0x1522)
        self.assertEqual(result["payloads"]["expeditionOpcode"], "0x1522")

    def test_dungeon_launch_only_returns_before_polling_or_opening_chest(self):
        sess = {
            "sessionId": "s1",
            "gameHttp": "http://game",
            "dm": 1,
            "role": {},
            "area": {},
        }
        general = {
            "id": 1,
            "idHex": "0000000000000001",
            "name": "测试将领",
            "displayStatus": "闲",
            "soldierTypeCode": 3,
            "soldierCount": 190,
        }
        prepare_payload = bytes.fromhex(
            "00000000000000000000000000000000000000000000ffffffff"
        )
        expedition_payload = server.utf("单人副本启动成功！")
        responses = [
            (200, b"", [{
                "opcode": 0x8520,
                "len": len(prepare_payload),
                "frag": 0,
                "payload": prepare_payload,
            }]),
            (200, b"", [{
                "opcode": 0x8522,
                "len": len(expedition_payload),
                "frag": 0,
                "payload": expedition_payload,
            }]),
        ]
        with patch.object(
            server, "dungeon_preflight_generals", return_value=[general],
        ), patch.object(
            server, "query_dungeon_catalog", return_value={},
        ), patch.object(
            server, "resolve_dungeon_stage_code", return_value=0,
        ), patch.object(
            server, "post_game", side_effect=responses,
        ), patch.object(
            server, "query_dungeon_state",
        ) as query_state, patch.object(
            server, "wait_for_dungeon_generals_idle",
        ) as wait_idle, patch.object(
            server, "open_dungeon_chest",
        ) as open_chest, patch.object(server.time, "sleep"):
            result = server.execute_dungeon(sess, {
                "confirm": "dungeon",
                "starterMode": True,
                "launchOnly": True,
                "generalIds": ["1"],
                "chapter": "第一章",
                "stage": 2,
                "openChest": False,
            })
        self.assertTrue(result["success"])
        self.assertTrue(result["launchOnly"])
        self.assertTrue(result["generalWaitSummary"]["launchOnly"])
        query_state.assert_not_called()
        wait_idle.assert_not_called()
        open_chest.assert_not_called()

    def test_pending_dungeon_advances_only_one_poll_per_scheduler_step(self):
        launched_at = server.now_ms() - 10_000
        general = {
            "id": 1,
            "idHex": "0000000000000001",
            "name": "副本将",
            "displayStatus": "战",
            "effectiveStatusUpdatedAt": server.now_ms(),
            "troopLimit": 200,
            "soldierTypeCode": 3,
            "soldierCount": 190,
        }
        pending = {
            "chapter": 0,
            "stage": 2,
            "loop": True,
            "generalId": "1",
            "generalIds": ["1"],
            "launchedAt": launched_at,
            "dispatchedAt": launched_at,
            "pollCount": 0,
            "nextPollAt": 0,
        }
        sess = {
            "sessionId": "s1",
            "gameHttp": "http://game",
            "dm": 1,
            "generals": [general],
            "starterFiveStageDungeonPending": pending,
        }
        with patch.object(
            server, "query_dungeon_state",
            return_value={"active": True, "status": 1, "battleId": 99},
        ), patch.object(
            server, "post_game", return_value=(200, b"", []),
        ) as post, patch.object(server, "persist_runtime_state"):
            result = server.execute_starter_five_stage_dungeon_pending(
                sess, general, pending,
            )
        self.assertTrue(result["deferred"])
        self.assertEqual(
            sess["starterFiveStageDungeonPending"]["pollCount"], 1,
        )
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[1][0][0], 0x1702)
        self.assertEqual(post.call_args.args[1][0][1][0], 2)

    def test_pending_dungeon_waits_without_relaunch(self):
        sess = {
            "starterFiveStageDungeonPending": {
                "chapter": 0,
                "stage": 2,
                "launchedAt": server.now_ms(),
            },
        }
        catalog = {
            "chapters": [{
                "chapterId": 0,
                "stages": [{"displayStage": 2, "resultCode": 255}],
            }],
        }
        with patch.object(
            server, "query_dungeon_catalog", return_value=catalog,
        ), patch.object(
            server,
            "query_dungeon_state",
            return_value={"active": False, "status": 0},
        ), patch.object(server, "execute_dungeon") as execute:
            result = server.execute_starter_five_stage_dungeon_stage(
                sess,
                {"id": 1, "name": "测试将领"},
                stage=2,
                loop=False,
            )
        self.assertTrue(result["deferred"])
        self.assertIn("等待战斗状态", result["message"])
        execute.assert_not_called()

    def test_pending_dungeon_status_four_opens_chest_and_completes(self):
        sess = {
            "starterFiveStageDungeonPending": {
                "chapter": 0,
                "stage": 2,
                "launchedAt": server.now_ms(),
            },
        }
        catalog = {
            "chapters": [{
                "chapterId": 0,
                "stages": [{"displayStage": 2, "resultCode": 255}],
            }],
        }
        with patch.object(
            server, "query_dungeon_catalog", return_value=catalog,
        ), patch.object(
            server,
            "query_dungeon_state",
            return_value={"active": False, "status": 4},
        ), patch.object(
            server,
            "query_dungeon_reward_state",
            return_value={"status": 4},
        ), patch.object(
            server,
            "open_dungeon_chest",
            return_value={"success": True},
        ) as open_chest, patch.object(
            server, "record_daily_dungeon_success", return_value=1,
        ), patch.object(
            server, "persist_runtime_state",
        ), patch.object(
            server, "execute_dungeon",
        ) as execute:
            result = server.execute_starter_five_stage_dungeon_stage(
                sess,
                {"id": 1, "name": "测试将领"},
                stage=2,
                loop=False,
            )
        self.assertTrue(result["success"])
        self.assertTrue(result["settledPendingBattle"])
        self.assertEqual(sess["starterEarlyDungeonCompletedStages"], 2)
        self.assertNotIn("starterFiveStageDungeonPending", sess)
        open_chest.assert_called_once_with(sess, 2)
        execute.assert_not_called()

    def test_vehicle_fief_uses_normal_recruit_confirmation_window(self):
        sess = {
            "roleState": {"level": 13},
            "role": {"level": 13},
            "generals": [{}, {}, {}, {}],
        }
        fief_plan = {
            "fiefCount": 2,
            "fiefs": [{
                "fiefId": 200,
                "fiveStageRole": "vehicle",
                "buildings": [
                    {
                        "slot": slot,
                        "type": 6,
                        "level": 1,
                        "busy": False,
                    }
                    for slot in range(1, 13)
                ],
            }],
        }
        with patch.object(
            server, "refresh_generals",
        ), patch.object(
            server,
            "starter_five_stage_fief_states",
            return_value=fief_plan,
        ), patch.object(
            server,
            "execute_soldier_recruit",
            return_value={"success": True, "count": 200},
        ) as recruit:
            result = server.execute_starter_five_stage_development(
                sess, {},
            )
        self.assertTrue(result["success"])
        recruit.assert_called_once_with(
            sess,
            200,
            server.SOLDIER_TYPE_CODES["弩车"],
            200,
            confirm_delay_sec=0.35,
            submit_preview_average=True,
        )

    def test_vehicle_recruit_timeout_is_recorded_without_blocking_combat(self):
        sess = {
            "roleState": {"level": 17},
            "role": {"level": 17},
            "generals": [{}, {}, {}, {}, {}],
        }
        fief_plan = {
            "fiefCount": 2,
            "fiefs": [{
                "fiefId": 200,
                "fiveStageRole": "vehicle",
                "buildings": [
                    {
                        "slot": slot,
                        "type": 6,
                        "level": 1,
                        "busy": slot != 12,
                    }
                    for slot in range(1, 13)
                ],
            }],
        }
        with patch.object(
            server, "refresh_generals",
        ), patch.object(
            server, "starter_five_stage_fief_states",
            return_value=fief_plan,
        ), patch.object(
            server, "starter_five_stage_required_fief_action",
            return_value=None,
        ), patch.object(
            server, "execute_soldier_recruit",
            return_value={
                "success": False,
                "message": "征兵确认超时或尚未就绪",
            },
        ), patch.object(server, "persist_runtime_state"):
            result = server.execute_starter_five_stage_development(
                sess, {},
            )
        self.assertTrue(result["success"])
        self.assertFalse(result["deferred"])
        self.assertFalse(result["recruitmentSuccess"])
        self.assertIn("已记录并继续战斗", result["message"])
        self.assertGreater(
            int(sess["starterFiveStageDevelopmentAuditedAt"]), 0,
        )

    def test_ready_general_can_depart_while_cavalry_recruits(self):
        general = {
            "id": 1,
            "name": "测试将领",
            "displayStatus": "闲",
            "troopLimit": 300,
            "soldierTypeCode": 3,
            "soldierCount": 196,
        }
        sess = {"generals": [general]}
        with patch.object(
            server, "starter_restore_five_stage_state_from_actions",
        ), patch.object(
            server, "refresh_generals",
        ), patch.object(
            server,
            "starter_five_stage_fief_states",
            return_value={"fiefs": []},
        ), patch.object(
            server,
            "starter_five_stage_base_building_action",
            return_value=None,
        ), patch.object(
            server,
            "starter_five_stage_base_cavalry_step",
            return_value={
                "completed": False,
                "recruiting": True,
                "state": {"speedOrdersUsed": 2},
            },
        ), patch.object(
            server,
            "starter_five_stage_assign_one_general",
            return_value={"skipped": True},
        ), patch.object(
            server,
            "starter_five_stage_ready_cavalry_generals",
            side_effect=[[general], [general], [general], [general]],
        ), patch.object(
            server,
            "execute_starter_five_stage_dungeon_stage",
            return_value={"success": True, "message": "副本已启动"},
        ) as dungeon, patch.object(
            server, "persist_runtime_state",
        ):
            result = server.execute_starter_five_stage_growth(
                sess, {"job_id": "job"},
            )
        self.assertTrue(result["success"])
        self.assertNotIn("baseCavalryRecruitingInBackground", result)
        dungeon.assert_called_once_with(
            sess, general, stage=2, loop=True,
        )


if __name__ == "__main__":
    unittest.main()
