from __future__ import annotations

import importlib.util
import sys
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_notice_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class ImportantNoticeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.originals = {
            "ACCOUNT_STATE_DB_FILE": SERVER.ACCOUNT_STATE_DB_FILE,
            "ACCOUNT_STATE_DB_READY": SERVER.ACCOUNT_STATE_DB_READY,
            "ACCOUNT_RECORDS_FILE": SERVER.ACCOUNT_RECORDS_FILE,
            "RUNTIME_STATE_FILE": SERVER.RUNTIME_STATE_FILE,
            "ACCOUNT_CONFIG_DIR": SERVER.ACCOUNT_CONFIG_DIR,
            "ACCOUNT_RECORD_BACKUP_DIR": SERVER.ACCOUNT_RECORD_BACKUP_DIR,
            "LOG_DIR": SERVER.LOG_DIR,
            "ACCOUNT_LOG_DIR": SERVER.ACCOUNT_LOG_DIR,
            "SYSTEM_LOG_FILE": SERVER.SYSTEM_LOG_FILE,
            "AREA_CATALOG_FILE": SERVER.AREA_CATALOG_FILE,
            "SESSIONS": SERVER.SESSIONS,
            "ACCOUNTS": SERVER.ACCOUNTS,
            "IMPORTANT_NOTICE_LOGS_MIGRATED_KEYS": SERVER.IMPORTANT_NOTICE_LOGS_MIGRATED_KEYS,
        }
        root = Path(self.tempdir.name)
        SERVER.ACCOUNT_STATE_DB_FILE = root / "assistant_state.sqlite3"
        SERVER.ACCOUNT_STATE_DB_READY = False
        SERVER.ACCOUNT_RECORDS_FILE = root / "account_records.json"
        SERVER.RUNTIME_STATE_FILE = root / "runtime_state.json"
        SERVER.ACCOUNT_CONFIG_DIR = root / "account_configs"
        SERVER.ACCOUNT_CONFIG_DIR.mkdir()
        SERVER.ACCOUNT_RECORD_BACKUP_DIR = root / "account_record_backups"
        SERVER.LOG_DIR = root / "logs"
        SERVER.ACCOUNT_LOG_DIR = SERVER.LOG_DIR / "accounts"
        SERVER.SYSTEM_LOG_FILE = SERVER.LOG_DIR / "system_recent.jsonl"
        SERVER.AREA_CATALOG_FILE = root / "area_catalog.json"
        SERVER.SESSIONS = {
            "s1": {
                "sessionId": "s1",
                "username": "1608602",
                "area": {"areaId": "351"},
                "role": {"roleId": 928},
            }
        }
        SERVER.ACCOUNTS = {
            "s1": {
                "sessionId": "s1",
                "username": "1608602",
                "area": {"areaId": "351"},
                "status": "online",
                "started": True,
            }
        }
        SERVER.IMPORTANT_NOTICE_LOGS_MIGRATED_KEYS = set()
        SERVER.initialize_account_state_database()

    def tearDown(self) -> None:
        for name, value in self.originals.items():
            setattr(SERVER, name, value)
        self.tempdir.cleanup()

    def test_brush_error_creates_notice_and_restart_resolves_it(self) -> None:
        task = {
            "taskId": "t1",
            "type": "auto-brush-yellow",
            "sessionId": "s1",
            "status": "error",
            "error": "状态机阻止刷黄：闲兵不足，已停止",
            "cycle": 0,
            "logs": [],
            "stopEvent": threading.Event(),
        }

        SERVER.task_log(task, task["error"])
        account_key = SERVER.account_storage_key(session_id="s1")
        notices = SERVER.database_read_active_important_notices(account_key)

        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]["key"], "task:brushYellow")
        self.assertEqual(notices[0]["title"], "刷黄已中止")
        self.assertIn("闲兵不足", notices[0]["message"])

        task["status"] = "running"
        task.pop("error")
        SERVER.task_log(task, "自动刷黄启动：重新检查编队")

        self.assertEqual(
            SERVER.database_read_active_important_notices(account_key),
            [],
        )

    def test_offline_account_is_returned_as_critical_notice(self) -> None:
        SERVER.ACCOUNTS["s1"].update({
            "status": "offline",
            "lastError": "当前节点无法连接游戏服",
        })

        notices = SERVER.current_important_notices(SERVER.SESSIONS["s1"])
        connection = next(item for item in notices if item["key"] == "account:connection")

        self.assertEqual(connection["severity"], "critical")
        self.assertIn("无法连接游戏服", connection["message"])
        self.assertEqual(
            connection["summary"],
            "账号连接异常：当前节点无法连接游戏服",
        )
        self.assertIn("检查当前IP", connection["advice"])

        self.assertTrue(
            SERVER.dismiss_important_notice(
                SERVER.SESSIONS["s1"],
                "account:connection",
            )
        )
        self.assertFalse(any(
            item["key"] == "account:connection"
            for item in SERVER.current_important_notices(SERVER.SESSIONS["s1"])
        ))

        SERVER.ACCOUNTS["s1"]["lastError"] = "新的连接失败原因"
        notices = SERVER.current_important_notices(SERVER.SESSIONS["s1"])
        self.assertTrue(any(
            item["key"] == "account:connection"
            for item in notices
        ))

    def test_long_brush_troop_error_has_short_summary(self) -> None:
        summary = SERVER.important_notice_summary({
            "title": "刷黄已中止",
            "message": (
                "状态机阻止刷黄：出征前配兵失败：将领 21765092；"
                "车2改 配兵中止：目标 259弩车，当前将领带兵=无配兵，"
                "可用弩车=0（闲兵0），不足以达到目标；当前闲兵：轻骑兵=4"
            ),
        })

        self.assertEqual(summary, "刷黄已中止：弩车闲兵不足（需要259，当前0）")

    def test_running_brush_troop_shortage_creates_notice_and_recovery_resolves_it(self) -> None:
        sess = SERVER.SESSIONS["s1"]
        reason = (
            "统弓2 配兵中止：目标 150弩兵，当前将领带兵=无配兵，"
            "可用弩兵=0（闲兵0），不足以达到目标；当前闲兵：强弩兵=285"
        )

        SERVER.upsert_brush_troop_shortage_notice(sess, 0, reason)
        notices = SERVER.current_important_notices(sess)
        notice = next(
            item for item in notices
            if item["key"] == "task:brushYellow:troopShortage:0"
        )

        self.assertEqual(notice["severity"], "warning")
        self.assertEqual(notice["title"], "刷黄配兵不足")
        self.assertEqual(
            notice["summary"],
            "刷黄配兵不足：弩兵闲兵不足（需要150，当前0）",
        )
        self.assertIn("军事-配兵", notice["advice"])

        SERVER.resolve_brush_troop_shortage_notice(sess, 0)
        self.assertFalse(any(
            item["key"] == "task:brushYellow:troopShortage:0"
            for item in SERVER.current_important_notices(sess)
        ))

    def test_click_delete_equivalent_hides_stored_task_notice(self) -> None:
        account_key = SERVER.account_storage_key(session_id="s1")
        SERVER.database_upsert_important_notice(
            account_key,
            "task:brushYellow",
            severity="error",
            title="刷黄已中止",
            message="状态机阻止刷黄：闲兵不足",
            source="task",
        )

        self.assertTrue(
            SERVER.dismiss_important_notice(
                SERVER.SESSIONS["s1"],
                "task:brushYellow",
            )
        )
        self.assertEqual(
            SERVER.database_read_active_important_notices(account_key),
            [],
        )


if __name__ == "__main__":
    unittest.main()
