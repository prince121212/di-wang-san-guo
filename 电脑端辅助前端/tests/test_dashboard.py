from __future__ import annotations

import importlib.util
import sys
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_dashboard_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class DashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.originals = {
            "ACCOUNTS": SERVER.ACCOUNTS,
            "SESSIONS": SERVER.SESSIONS,
            "AUTO_TASKS": SERVER.AUTO_TASKS,
            "ACCOUNT_STATE_DB_READY": SERVER.ACCOUNT_STATE_DB_READY,
            "DAILY_BRUSH_COUNTS": SERVER.DAILY_BRUSH_COUNTS,
            "DAILY_DUNGEON_COUNTS": SERVER.DAILY_DUNGEON_COUNTS,
            "DAILY_TASK_COMPLETIONS": SERVER.DAILY_TASK_COMPLETIONS,
        }
        sid = "dashboard-session"
        self.sess = {
            "sessionId": sid,
            "username": "1608600",
            "role": {
                "roleId": 100,
                "roleName": "测试角色",
                "level": 77,
                "country": "蜀汉",
                "title": "蜀",
            },
            "roleState": {
                "roleName": "测试角色",
                "level": 77,
                "copper": 123,
                "food": 456,
                "resourcePointCurrent": 1,
                "resourcePointCap": 4,
            },
            "area": {"areaId": 351, "areaName": "351区"},
            "generals": [
                {"id": 1, "name": "步1", "displayStatus": "闲"},
                {"id": 2, "name": "车1", "displayStatus": "战"},
                {"id": 3, "name": "车2", "displayStatus": "防"},
            ],
            "dailyActivity": {},
        }
        SERVER.ACCOUNTS = {
            sid: {
                "sessionId": sid,
                "username": "1608600",
                "status": "online",
                "started": True,
                "role": self.sess["role"],
                "area": self.sess["area"],
                "lastHeartbeat": {"online": True, "checkedAt": 1234},
            }
        }
        SERVER.SESSIONS = {sid: self.sess}
        SERVER.AUTO_TASKS = {}
        SERVER.ACCOUNT_STATE_DB_READY = False
        daily_key = SERVER.daily_account_key(self.sess)
        SERVER.DAILY_BRUSH_COUNTS = {daily_key: 9}
        SERVER.DAILY_DUNGEON_COUNTS = {daily_key: 2}
        SERVER.DAILY_TASK_COMPLETIONS = {}

    def tearDown(self) -> None:
        for name, value in self.originals.items():
            setattr(SERVER, name, value)

    def test_dashboard_uses_only_existing_local_state(self) -> None:
        forbidden = (
            "post_game",
            "execute_heartbeat",
            "refresh_generals",
            "refresh_military_intel",
            "refresh_inventory",
        )
        patches = [
            patch.object(
                SERVER,
                name,
                side_effect=AssertionError(f"dashboard called forbidden function {name}"),
            )
            for name in forbidden
        ]
        with patch.object(
            SERVER,
            "load_account_habits",
            return_value={"config": {"dailyLimit": 500}},
        ), patch.object(
            SERVER,
            "database_read_account_logs",
            return_value=[],
        ), patch.object(
            SERVER,
            "current_important_notices",
            return_value=[],
        ), patch.object(
            SERVER,
            "recent_game_requests",
            return_value=[],
        ):
            for item in patches:
                item.start()
            try:
                result = SERVER.current_dashboard_snapshot()
            finally:
                for item in reversed(patches):
                    item.stop()

        self.assertEqual(result["gameRequestsIssued"], 0)
        self.assertEqual(result["totals"]["accounts"], 1)
        self.assertEqual(result["totals"]["online"], 1)
        self.assertEqual(result["generalTotals"]["idle"], 1)
        self.assertEqual(result["generalTotals"]["active"], 1)
        self.assertEqual(result["generalTotals"]["defending"], 1)
        account = result["accounts"][0]
        self.assertEqual(account["countryShort"], "蜀")
        self.assertEqual(account["dailyProgress"]["brushYellow"]["current"], 9)
        self.assertEqual(account["dailyProgress"]["dungeon"]["current"], 2)
        self.assertEqual(account["resources"]["resourcePointCurrent"], 1)

    def test_dashboard_country_short_name_supports_all_countries(self) -> None:
        names = ("汉", "魏", "蜀", "吴", "楚", "胡", "赵", "秦", "羌", "鲁", "蛮", "燕", "晋", "陈")
        for name in names:
            self.assertEqual(
                SERVER.dashboard_country_short_name({"title": name}),
                name,
            )
        self.assertEqual(
            SERVER.dashboard_country_short_name({"country": "蜀汉"}),
            "蜀",
        )

    def test_account_summary_exposes_current_daily_stats(self) -> None:
        account = SERVER.ACCOUNTS[self.sess["sessionId"]]
        daily_key = SERVER.daily_account_key(self.sess)

        first = SERVER.public_account_summary(account)
        self.assertEqual(first["dailyStats"]["brushYellowCount"], 9)
        self.assertEqual(first["dailyStats"]["dungeonCount"], 2)

        SERVER.DAILY_BRUSH_COUNTS[daily_key] = 10
        updated = SERVER.public_account_summary(account)
        self.assertEqual(updated["dailyStats"]["brushYellowCount"], 10)

    def test_start_all_saved_tasks_only_targets_started_online_accounts(self) -> None:
        self.sess["savedTasksStarted"] = False
        already = {
            "sessionId": "already",
            "username": "1608601",
            "area": {"areaName": "352区"},
            "savedTasksStarted": True,
        }
        offline = {
            "sessionId": "offline",
            "username": "1608602",
            "area": {"areaName": "352区"},
            "savedTasksStarted": False,
        }
        SERVER.SESSIONS.update({"already": already, "offline": offline})
        SERVER.ACCOUNTS.update({
            "already": {
                "sessionId": "already",
                "username": "1608601",
                "status": "online",
                "started": True,
            },
            "offline": {
                "sessionId": "offline",
                "username": "1608602",
                "status": "offline",
                "started": True,
            },
        })

        with patch.object(
            SERVER,
            "require_account_online",
        ) as require_online, patch.object(
            SERVER,
            "resume_saved_resident_tasks",
            return_value={
                "resumed": {"brushYellow": {"started": True}},
                "errors": {},
            },
        ) as resume, patch.object(SERVER, "account_log"):
            result = SERVER.resume_saved_tasks_for_all_running_accounts()

        self.assertEqual(result["eligibleCount"], 2)
        self.assertEqual(result["startedCount"], 1)
        self.assertEqual(result["alreadyStartedCount"], 1)
        self.assertEqual(result["failedCount"], 0)
        require_online.assert_called_once_with(
            "dashboard-session",
            "一键开始全部账号任务",
        )
        resume.assert_called_once_with(self.sess)
        self.assertFalse(any(
            item["sessionId"] == "offline"
            for item in result["results"]
        ))
