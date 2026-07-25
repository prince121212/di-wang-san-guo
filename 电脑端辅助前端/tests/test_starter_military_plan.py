import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def general(gid, name, kind, troop_limit=500):
    return {
        "id": gid,
        "idHex": f"{gid:016x}",
        "name": name,
        "kind": kind,
        "displayStatus": "闲",
        "tili": 100,
        "troopLimit": troop_limit,
        "fangyu": 80,
        "gongji": 80,
        "growth": 60,
        "soldierCount": 0,
    }


class StarterMilitaryPlanTest(unittest.TestCase):
    def test_early_bandit_dispatch_explicitly_allows_under_30(self):
        plan = {
            "bandit": {
                "teams": [{
                    "targetLevel": 1,
                    "roles": [{
                        "general": {"id": "1"},
                        "soldierType": "轻骑兵",
                        "desiredCount": 200,
                    }],
                }],
            },
        }
        with (
            patch.object(server, "unassign_all_idle_generals", return_value=[]),
            patch.object(
                server, "execute_assign_troops",
                return_value={"success": True},
            ),
            patch.object(
                server, "recommend_brush_center",
                return_value={"x": 100, "y": 100},
            ),
            patch.object(
                server, "search_targets",
                return_value={"targets": [{"id": 7, "level": 1}]},
            ),
            patch.object(
                server, "execute_brush",
                return_value={"success": True},
            ) as execute_brush,
            patch.object(server, "persist_runtime_state"),
        ):
            result = server.execute_starter_early_bandit_action(
                {"sessionId": "starter-under-30"},
                {"job_id": "starter-job"},
                plan,
            )
        self.assertTrue(result["success"])
        self.assertTrue(execute_brush.call_args.kwargs["allow_under30"])

    def test_under_30_bootstraps_200_base_carts_then_dungeon_then_bandits(self):
        sess = {
            "roleState": {"level": 12},
            "inventory": {"items": [{"name": "新手礼包2", "count": 1}]},
            "army": [{"soldierType": "弩车", "idleCount": 200}],
            "generals": [general(1, "前期将", "骑将")],
        }
        plan = server.starter_military_plan(sess)
        self.assertEqual(plan["recommendedTask"], "recruit-and-build")
        self.assertTrue(plan["bandit"]["directUnder30"])
        sess["starterBaseVehicleBootstrap"] = {"completed": True}
        plan = server.starter_military_plan(sess)
        self.assertEqual(plan["recommendedTask"], "dungeon")
        self.assertEqual(
            plan["dungeon"]["roles"][0]["soldierType"], "弩车",
        )
        sess["starterEarlyDungeonCompletedStages"] = 3
        plan = server.starter_military_plan(sess)
        self.assertEqual(plan["recommendedTask"], "bandit")
        self.assertEqual(plan["bandit"]["teams"][0]["targetLevel"], 1)
        sess["starterEarlyBanditCompletedLevels"] = [1, 2]
        plan = server.starter_military_plan(sess)
        self.assertEqual(plan["bandit"]["teams"][0]["targetLevel"], 3)

    def test_early_dungeon_tries_other_chests_and_tracks_first_three_stages(self):
        sess = {"starterEarlyDungeonCompletedStages": 0}
        plan = {
            "dungeon": {
                "ready": True,
                "mode": "early",
                "roles": [{
                    "general": {"id": "1"},
                    "soldierType": "弩车",
                    "desiredCount": 200,
                }],
            },
        }
        battle = {
            "success": True,
            "chest": 2,
            "chestName": "右",
            "chestResult": {"success": False, "payloadHex": "ff"},
        }
        with (
            patch.object(server, "refresh_generals"),
            patch.object(server, "starter_refill_low_energy_generals"),
            patch.object(server, "heal_all_wounded_before_military_prepare"),
            patch.object(server, "starter_military_plan", return_value=plan),
            patch.object(server, "unassign_all_idle_generals", return_value={}),
            patch.object(
                server, "execute_assign_troops",
                return_value={"success": True},
            ),
            patch.object(
                server, "starter_next_dungeon_stage",
                return_value={
                    "chapter": 0, "chapterName": "第1章",
                    "stage": 1, "stageCode": 0, "catalog": {},
                },
            ),
            patch.object(server, "execute_dungeon", return_value=battle) as run,
            patch.object(
                server, "open_dungeon_chest",
                return_value={"success": True, "chestIndex": 0},
            ),
            patch.object(
                server, "query_dungeon_catalog",
                return_value={"chapters": []},
            ),
            patch.object(server, "persist_runtime_state"),
        ):
            result = server.execute_starter_dungeon_action(
                sess, {"job_id": "starter-job"},
            )
        self.assertTrue(result["success"])
        self.assertEqual(sess["starterEarlyDungeonCompletedStages"], 1)
        self.assertEqual(run.call_args.args[1]["chest"], "右")

    def test_stage_three_unlock_team_uses_cavalry_and_crossbow_vehicle(self):
        sess = {
            "roleState": {"level": 30},
            "army": [
                {"soldierType": "轻骑兵", "idleCount": 200},
                {"soldierType": "弩车", "idleCount": 200},
            ],
            "generals": [
                general(1, "前排", "骑将"),
                general(2, "后排", "弓将"),
            ],
        }
        plan = server.starter_military_plan(sess)
        self.assertEqual(plan["recommendedTask"], "dungeon")
        self.assertEqual(plan["dungeon"]["mode"], "unlock-heavy")
        self.assertEqual(
            [role["soldierType"] for role in plan["dungeon"]["roles"]],
            ["轻骑兵", "弩车"],
        )

    def test_150_heavy_infantry_is_split_into_three_level6_teams(self):
        sess = {
            "roleState": {
                "level": 35,
                "idleArmy": [
                    {"soldierType": "重步兵", "idleCount": 150},
                    {"soldierType": "弩车", "idleCount": 900},
                ],
            },
            "army": [
                {"soldierType": "重步兵", "idleCount": 150},
                {"soldierType": "弩车", "idleCount": 900},
            ],
            "generals": [
                general(1, "步一", "步将"),
                general(2, "步二", "勇士"),
                general(3, "步三", "步将"),
                general(4, "车一", "骑将"),
                general(5, "车二", "弓将"),
                general(6, "车三", "骑将"),
            ],
        }
        plan = server.starter_military_plan(sess)
        teams = plan["bandit"]["teams"]
        self.assertEqual(len(teams), 3)
        self.assertTrue(all(row["targetLevel"] == 6 for row in teams))
        self.assertTrue(all(row["formationCode"] == "0500" for row in teams))
        self.assertTrue(all(row["front"]["desiredCount"] == 50 for row in teams))
        self.assertTrue(all(row["rear"]["desiredCount"] == 300 for row in teams))

    def test_199_heavy_infantry_switches_to_level7(self):
        sess = {
            "roleState": {"level": 40},
            "army": [
                {"soldierType": "重步兵", "idleCount": 398},
                {"soldierType": "弩车", "idleCount": 800},
            ],
            "generals": [
                general(1, "步一", "步将"),
                general(2, "步二", "勇士"),
                general(3, "车一", "骑将"),
                general(4, "车二", "弓将"),
            ],
        }
        teams = server.starter_military_plan(sess)["bandit"]["teams"]
        self.assertEqual(len(teams), 2)
        self.assertTrue(all(row["targetLevel"] == 7 for row in teams))
        self.assertTrue(all(row["front"]["desiredCount"] == 199 for row in teams))

    def test_dungeon_is_selected_until_first_defeat(self):
        sess = {
            "roleState": {"level": 33},
            "army": [
                {"soldierType": "重步兵", "idleCount": 150},
                {"soldierType": "弩兵", "idleCount": 150},
                {"soldierType": "弩车", "idleCount": 200},
            ],
            "generals": [
                general(1, "步将", "步将"),
                general(2, "弓将", "弓将"),
                general(3, "车将", "骑将"),
            ],
        }
        self.assertEqual(server.starter_military_plan(sess)["recommendedTask"], "dungeon")
        sess["starterDungeonDefeatConfirmed"] = True
        self.assertNotEqual(server.starter_military_plan(sess)["recommendedTask"], "dungeon")

    def test_legacy_generic_dungeon_stop_marker_does_not_disable_dungeon(self):
        sess = {
            "roleState": {"level": 33},
            "army": [
                {"soldierType": "重步兵", "idleCount": 150},
                {"soldierType": "弩兵", "idleCount": 150},
                {"soldierType": "弩车", "idleCount": 200},
            ],
            "generals": [
                general(1, "步将", "步将"),
                general(2, "弓将", "弓将"),
                general(3, "车将", "骑将"),
            ],
            "starterDungeonStoppedAfterDefeat": True,
        }
        self.assertEqual(
            server.starter_military_plan(sess)["recommendedTask"], "dungeon"
        )

    def test_only_explicit_battle_result_confirms_dungeon_defeat(self):
        self.assertFalse(server.starter_dungeon_defeat_confirmed({
            "success": False,
            "reason": "等待将领回闲超时",
        }))
        self.assertFalse(server.starter_dungeon_defeat_confirmed({
            "success": True,
            "textPreview": "本场战斗的100%伤兵自愈了 声望奖励400",
        }))
        self.assertTrue(server.starter_dungeon_defeat_confirmed({
            "success": True,
            "textPreview": "本场战斗战败，挑战失败",
        }))

    def test_dungeon_catalog_is_rechecked_after_level_increases(self):
        sess = {
            "roleState": {"level": 40},
            "army": [
                {"soldierType": "重步兵", "idleCount": 150},
                {"soldierType": "弩兵", "idleCount": 150},
                {"soldierType": "弩车", "idleCount": 200},
            ],
            "generals": [
                general(1, "步将", "步将"),
                general(2, "弓将", "弓将"),
                general(3, "车将", "骑将"),
            ],
            "starterDungeonNoAvailableStage": True,
            "starterDungeonNoAvailableAtLevel": 40,
        }
        self.assertNotEqual(
            server.starter_military_plan(sess)["recommendedTask"], "dungeon"
        )
        sess["roleState"]["level"] = 41
        self.assertEqual(
            server.starter_military_plan(sess)["recommendedTask"], "dungeon"
        )

    def test_exact_0500_requires_five_crossbow_units(self):
        target = {
            "compositionCode": "0300",
            "composition": {"foot": 0, "bow": 3, "cavalry": 0, "chariot": 0},
            "units": [{"soldierTypeCode": 1} for _ in range(3)],
        }
        self.assertTrue(server.starter_is_exact_all_crossbow_bandit(target))
        target["units"][0]["soldierTypeCode"] = 14
        self.assertFalse(server.starter_is_exact_all_crossbow_bandit(target))

    def test_busy_general_troops_are_not_counted_as_reassignable(self):
        idle_general = general(1, "空闲车将", "弓将")
        idle_general.update({
            "soldierType": "弩车",
            "soldierTypeCode": 4,
            "soldierCount": 90,
        })
        busy_general = general(2, "出征车将", "弓将")
        busy_general.update({
            "displayStatus": "出",
            "soldierType": "弩车",
            "soldierTypeCode": 4,
            "soldierCount": 90,
        })
        totals = server.starter_total_soldiers({
            "army": [],
            "generals": [idle_general, busy_general],
        })
        self.assertEqual(totals["弩车"], 90)
        owned = server.starter_inventory_soldiers({
            "army": [],
            "generals": [idle_general, busy_general],
        })
        self.assertEqual(owned["弩车"], 180)

    def test_temporary_fief_troops_are_not_counted_before_transfer(self):
        totals = server.starter_total_soldiers({
            "army": [
                {"soldierType": "弩车", "idleCount": 2, "fiefName": "测试基地"},
                {"soldierType": "弩车", "idleCount": 41, "fiefName": "临时封地"},
            ],
            "generals": [],
        })
        self.assertEqual(totals["弩车"], 2)

    def test_wounded_total_uses_idle_army_wounded_fields(self):
        self.assertEqual(server.starter_wounded_total({
            "army": [
                {"soldierType": "重步兵", "woundedCount": 50},
                {"soldierType": "弩车", "hurtSoldierCount": 12},
                {"soldierType": "弩兵", "woundedCount": 0},
            ],
        }), 62)

    def test_hidden_fief_wounded_troops_schedule_healing_recovery(self):
        sess = {
            "roleState": {"level": 46},
            "army": [{"soldierType": "重步兵", "idleCount": 50}],
            "generals": [
                general(1, "将一", "步将"),
                general(2, "将二", "弓将"),
            ],
            "starterFiefBuildings": {
                "fiefs": [{
                    "list1": [{"type": 8, "value": 50}],
                    "list2": [
                        {"type": 8, "value": 100},
                        {"type": 4, "value": 180},
                    ],
                }],
            },
        }
        self.assertEqual(server.starter_wounded_total(sess), 280)
        self.assertEqual(
            server.starter_military_plan(sess)["recommendedTask"], "heal"
        )

    def test_starter_force_heal_ignores_normal_mode_checkbox(self):
        sess = {
            "sessionId": "starter-force-heal",
            "generals": [{"fiefId": 100, "fiefName": "基地"}],
        }
        server.SAVED_CONFIGS[sess["sessionId"]] = {"healWounded": False}
        try:
            with patch.object(server, "refresh_generals"), patch.object(
                server,
                "execute_heal_wounded",
                return_value={"success": True},
            ) as heal:
                server.heal_all_wounded_before_military_prepare(
                    sess, "起号测试", force=True,
                )
            heal.assert_called_once()
        finally:
            server.SAVED_CONFIGS.pop(sess["sessionId"], None)

    def test_starter_resource_shortage_is_deferred_without_hot_retry(self):
        result = server.starter_heal_resource_deferred(
            RuntimeError(
                "治疗伤兵铜钱不足；固定粮食转铜失败：资源转换失败状态 -3"
            ),
            action_name="起号刷黄",
        )
        self.assertIsNotNone(result)
        self.assertTrue(result["deferred"])
        self.assertTrue(result["resourceBlocked"])
        self.assertEqual(result["retryAfterSec"], 600)


if __name__ == "__main__":
    unittest.main()
