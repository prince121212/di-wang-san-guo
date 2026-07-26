from __future__ import annotations

import threading
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def catalog_with_progress(*, next_available: bool = True) -> dict:
    return {
        "chapters": [{
            "chapterId": 0,
            "displayChapter": 1,
            "detailFlag": 1,
            "stages": [
                {"displayStage": 1, "stageCode": 10, "available": True, "resultCode": 1},
                {"displayStage": 2, "stageCode": 11, "available": True, "resultCode": 1},
                {"displayStage": 3, "stageCode": 12, "available": True, "resultCode": 1},
                {"displayStage": 4, "stageCode": 13, "available": next_available, "resultCode": 255},
            ],
        }],
    }


class DungeonClearTests(unittest.TestCase):
    def test_mode_normalization_keeps_legacy_loop_and_accepts_clear_alias(self) -> None:
        self.assertEqual(server.normalize_dungeon_mode(None), "loop")
        self.assertEqual(server.normalize_dungeon_mode("clear"), "clear")
        self.assertEqual(server.normalize_dungeon_mode("打通副本"), "clear")
        normalized = server.normalize_military_future_settings(
            "dungeon",
            {"clearStages": True, "rows": []},
        )
        self.assertEqual(normalized["mode"], "clear")

    def test_selects_first_uncompleted_stage_after_completed_stage_three(self) -> None:
        result = server.first_uncompleted_dungeon_stage(catalog_with_progress())

        self.assertIsNotNone(result)
        self.assertEqual(result["chapter"], 0)
        self.assertEqual(result["stage"], 4)
        self.assertEqual(result["stageCode"], 13)

    def test_locked_first_uncompleted_stage_is_not_skipped(self) -> None:
        result = server.first_uncompleted_dungeon_stage(
            catalog_with_progress(next_available=False),
        )

        self.assertEqual(result["stage"], 4)
        self.assertFalse(result["available"])

    def test_locked_chapter_without_stage_details_is_not_treated_as_all_clear(self) -> None:
        catalog = {
            "chapters": [
                {
                    "chapterId": 0,
                    "displayChapter": 1,
                    "detailFlag": 1,
                    "stages": [{
                        "displayStage": 12,
                        "stageCode": 12,
                        "available": True,
                        "resultCode": 1,
                    }],
                },
                {
                    "chapterId": 1,
                    "displayChapter": 2,
                    "name": "第二章",
                    "detailFlag": 0,
                    "stages": [],
                },
                {
                    "chapterId": 2,
                    "displayChapter": 3,
                    "detailFlag": 1,
                    "stages": [{
                        "displayStage": 1,
                        "stageCode": 24,
                        "available": True,
                        "resultCode": 255,
                    }],
                },
            ],
        }

        result = server.first_uncompleted_dungeon_stage(catalog)

        self.assertEqual(result["chapter"], 1)
        self.assertEqual(result["stage"], 1)
        self.assertFalse(result["available"])
        self.assertTrue(result["lockedChapter"])
        self.assertEqual(result["stageCode"], 3)

    def test_defeat_requires_explicit_battle_wording(self) -> None:
        self.assertTrue(server.dungeon_battle_defeat_confirmed({
            "chestResult": {"textPreview": "本场战斗战败，挑战失败"},
        }))
        self.assertFalse(server.dungeon_battle_defeat_confirmed({
            "failureReason": "副本启动未收到有效0x8522确认",
        }))

    def test_clear_preflight_forces_healing_before_reassignment(self) -> None:
        sess = {"sessionId": "force-heal"}
        with patch.object(server, "prepare_military_generals", return_value=[]) as prepare:
            server.dungeon_preflight_generals(
                sess,
                ["1"],
                force_heal=True,
            )

        prepare.assert_called_once_with(
            sess,
            ["1"],
            "副本",
            task=None,
            allow_existing_troops=False,
            force_heal=True,
        )

    def test_clear_mode_ignores_stale_chapter_and_stage_placeholders(self) -> None:
        sess = {
            "generals": [{"id": 1, "idHex": "0000000000000001"}],
        }

        rows = server.normalize_dungeon_rows(
            sess,
            {"rows": [{
                "enabled": True,
                "generalIds": ["1"],
                "chapter": "已删除章节",
                "stage": "999",
                "chest": "右",
            }]},
            mode="clear",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["chapter"], 0)
        self.assertEqual(rows[0]["stage"], 1)
        self.assertEqual(rows[0]["generalIds"], ["1"])

    def test_force_heal_reaches_military_prepare_before_saved_formation_check(self) -> None:
        sess = {"sessionId": "force-heal-prepare"}
        general = {
            "id": 1,
            "idHex": "0000000000000001",
            "name": "副本将领",
            "displayStatus": "闲",
            "energyReliable": True,
            "tili": 100,
            "soldierTypeCode": 8,
            "soldierCount": 100,
        }
        formation = {
            "generalId": "1",
            "soldierType": "重步兵",
            "soldierCount": 100,
        }
        with patch.object(
            server,
            "heal_all_wounded_before_military_prepare",
            return_value={"success": True},
        ) as heal, patch.object(
            server,
            "refresh_general_with_a110_status",
            return_value=general,
        ), patch.object(
            server,
            "saved_formation_for_general",
            return_value=formation,
        ):
            selected = server.prepare_military_generals(
                sess,
                ["1"],
                "副本",
                force_heal=True,
            )

        heal.assert_called_once_with(sess, "副本", task=None, force=True)
        self.assertEqual(selected, [general])

    def test_clear_worker_advances_one_stage_then_pauses_on_defeat(self) -> None:
        sid = "dungeon-clear-test"
        ref1 = {
            "chapter": 0,
            "chapterName": "第1章",
            "stage": 4,
            "stageCode": 13,
            "available": True,
        }
        ref2 = {
            "chapter": 0,
            "chapterName": "第1章",
            "stage": 5,
            "stageCode": 14,
            "available": True,
        }
        task = {
            "taskId": "dungeon-clear-task",
            "type": "dungeon",
            "sessionId": sid,
            "status": "starting",
            "cycle": 0,
            "config": {
                "sessionId": sid,
                "mode": "clear",
                "rows": [{
                    "generalIds": ["1"],
                    "generalId": "1",
                    "chest": 2,
                    "chestName": "右",
                }],
            },
            "stopEvent": threading.Event(),
            "logs": [],
            "schedulerState": "checking",
            "schedulerGeneralIds": ["1"],
        }
        sess = {
            "sessionId": sid,
            "role": {},
            "area": {},
            "generals": [{"id": "1", "idHex": "0000000000000001", "name": "编队1将领"}],
        }
        old_tasks = server.AUTO_TASKS
        old_sessions = server.SESSIONS
        server.AUTO_TASKS = {task["taskId"]: task}
        server.SESSIONS = {sid: sess}
        try:
            with patch.object(server, "wait_for_task_account_online", return_value=True), \
                 patch.object(server, "next_dungeon_clear_stage", side_effect=[ref1, ref2]) as select_stage, \
                 patch.object(server, "command_center_wait_generals_idle", return_value=True), \
                 patch.object(server, "command_center_acquire", return_value=True), \
                 patch.object(server, "command_center_release"), \
                 patch.object(server, "execute_dungeon", side_effect=[
                     {"success": True, "stageCompleted": True, "chestResult": {"success": True}},
                     {"success": True, "defeatConfirmed": True, "chestResult": {"success": True, "textPreview": "本场战斗战败"}},
                 ]) as execute, \
                 patch.object(server, "record_daily_dungeon_success", return_value=1) as record, \
                 patch.object(server, "persist_dungeon_clear_pause", return_value={"paused": True}) as save_pause, \
                 patch.object(server, "task_log"), \
                 patch.object(server, "persist_runtime_state"), \
                 patch.object(server, "mark_account_offline_if_session_invalid"):
                server.dungeon_worker(task["taskId"])
        finally:
            server.AUTO_TASKS = old_tasks
            server.SESSIONS = old_sessions

        self.assertEqual(execute.call_count, 2)
        self.assertEqual(
            [call.args[1]["stage"] for call in execute.call_args_list],
            [4, 5],
        )
        self.assertEqual(
            [call.args[1]["stageCode"] for call in execute.call_args_list],
            [13, 14],
        )
        self.assertTrue(all(
            call.args[1]["clearStage"]
            for call in execute.call_args_list
        ))
        self.assertEqual(select_stage.call_count, 2)
        record.assert_called_once_with(sess)
        save_pause.assert_called_once()
        self.assertEqual(task["status"], "stopped")
        self.assertTrue(task["defeatConfirmed"])
        self.assertIn("第1章第5关", task["stopReason"])
        self.assertIn("战败", task["stopReason"])

    def test_defeat_stop_is_projected_to_role_notice(self) -> None:
        task = {
            "type": "dungeon",
            "status": "stopped",
            "stopReason": "打通副本暂停：第1章第5关战败",
            "config": {"mode": "clear"},
        }
        with patch.object(server, "database_upsert_important_notice") as upsert:
            server.sync_task_important_notice(task, task["stopReason"], "notice-sid")

        upsert.assert_called_once()
        args, kwargs = upsert.call_args
        self.assertEqual(args[1], "task:dungeon")
        self.assertEqual(kwargs["severity"], "warning")
        self.assertEqual(kwargs["title"], "打通副本已停止")
        self.assertIn("战败", kwargs["message"])

    def test_saved_defeat_pause_does_not_auto_resume_after_reconnect(self) -> None:
        sess = {
            "sessionId": "paused-clear",
            "generals": [{"id": 1, "idHex": "0000000000000001"}],
        }
        habits = {
            "militaryFuture": {
                "dungeon": {
                    "mode": "clear",
                    "pausedAfterDefeat": {
                        "paused": True,
                        "reason": "第1章第5关战败",
                    },
                    "rows": [{
                        "enabled": True,
                        "generalIds": ["1"],
                        "chapter": "第一章",
                        "stage": "1",
                        "chest": "右",
                    }],
                },
            },
        }
        with patch.object(server, "load_account_habits", return_value=habits), \
             patch.object(server, "start_dungeon_task") as start, \
             patch.object(server, "account_log"), \
             patch.object(server, "persist_runtime_state"):
            result = server.resume_saved_resident_tasks(sess)

        start.assert_not_called()
        self.assertIn("dungeonPausedAfterDefeat", result["oneTime"])
        self.assertNotIn("dungeon", result["resumed"])

    def test_persist_defeat_pause_saves_stage_and_current_rows(self) -> None:
        sess = {"sessionId": "persist-clear-pause"}
        task = {
            "config": {
                "rows": [{
                    "enabled": True,
                    "generalIds": ["1"],
                    "chest": 2,
                }],
            },
        }
        stage = {
            "chapter": 0,
            "chapterName": "第1章",
            "stage": 5,
        }
        with patch.object(
            server,
            "load_account_habits",
            return_value={"militaryFuture": {}},
        ), patch.object(
            server,
            "save_account_habits",
        ) as save, patch.object(server, "now_ms", return_value=123456):
            pause = server.persist_dungeon_clear_pause(
                sess,
                task,
                stage,
                "第1章第5关战败",
            )

        saved = save.call_args.kwargs["military_future"]["dungeon"]
        self.assertEqual(saved["mode"], "clear")
        self.assertEqual(saved["rows"], task["config"]["rows"])
        self.assertEqual(saved["pausedAfterDefeat"], pause)
        self.assertEqual(pause, {
            "paused": True,
            "reason": "第1章第5关战败",
            "chapter": 0,
            "chapterName": "第1章",
            "stage": 5,
            "pausedAt": 123456,
        })

    def test_resaving_dungeon_replaces_and_clears_old_defeat_pause(self) -> None:
        sess = {
            "sessionId": "resave-clear-pause",
            "username": "test",
            "area": {},
        }
        replacement = {
            "mode": "clear",
            "rows": [{"enabled": True, "generalIds": ["1"]}],
        }
        old_payload = {
            "militaryFuture": {
                "dungeon": {
                    **replacement,
                    "pausedAfterDefeat": {
                        "paused": True,
                        "reason": "第1章第5关战败",
                    },
                },
            },
        }
        with patch.object(
            server,
            "load_account_settings_payload",
            return_value=old_payload,
        ), patch.object(
            server,
            "database_save_account_habits",
        ) as database_save, patch.object(
            server,
            "account_storage_key",
            return_value="test-account",
        ):
            server.save_account_habits(
                sess,
                military_future={"dungeon": replacement},
            )

        stored_payload = database_save.call_args.args[1]
        stored_dungeon = stored_payload["militaryFuture"]["dungeon"]
        self.assertEqual(stored_dungeon, replacement)
        self.assertNotIn("pausedAfterDefeat", stored_dungeon)


if __name__ == "__main__":
    unittest.main()
