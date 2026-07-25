from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_account_state_db_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class AccountStateDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.originals = {
            "ACCOUNT_STATE_DB_FILE": SERVER.ACCOUNT_STATE_DB_FILE,
            "REPORT_DIR": SERVER.REPORT_DIR,
            "ACCOUNT_RECORDS_FILE": SERVER.ACCOUNT_RECORDS_FILE,
            "RUNTIME_STATE_FILE": SERVER.RUNTIME_STATE_FILE,
            "ACCOUNT_CONFIG_DIR": SERVER.ACCOUNT_CONFIG_DIR,
            "ACCOUNT_RECORD_BACKUP_DIR": SERVER.ACCOUNT_RECORD_BACKUP_DIR,
            "LOG_DIR": SERVER.LOG_DIR,
            "ACCOUNT_LOG_DIR": SERVER.ACCOUNT_LOG_DIR,
            "SYSTEM_LOG_FILE": SERVER.SYSTEM_LOG_FILE,
            "AREA_CATALOG_FILE": SERVER.AREA_CATALOG_FILE,
            "ACCOUNT_STATE_DB_READY": SERVER.ACCOUNT_STATE_DB_READY,
            "DAILY_BRUSH_COUNTS": SERVER.DAILY_BRUSH_COUNTS,
            "DAILY_DUNGEON_COUNTS": SERVER.DAILY_DUNGEON_COUNTS,
            "DAILY_TASK_COMPLETIONS": SERVER.DAILY_TASK_COMPLETIONS,
        }
        SERVER.ACCOUNT_STATE_DB_FILE = root / "assistant_state.sqlite3"
        SERVER.REPORT_DIR = root
        SERVER.ACCOUNT_RECORDS_FILE = root / "account_records.json"
        SERVER.RUNTIME_STATE_FILE = root / "runtime_state.json"
        SERVER.ACCOUNT_CONFIG_DIR = root / "account_configs"
        SERVER.ACCOUNT_CONFIG_DIR.mkdir()
        SERVER.ACCOUNT_RECORD_BACKUP_DIR = root / "account_record_backups"
        SERVER.LOG_DIR = root / "logs"
        SERVER.ACCOUNT_LOG_DIR = SERVER.LOG_DIR / "accounts"
        SERVER.SYSTEM_LOG_FILE = SERVER.LOG_DIR / "system_recent.jsonl"
        SERVER.AREA_CATALOG_FILE = root / "area_catalog.json"
        SERVER.ACCOUNT_STATE_DB_READY = False
        SERVER.DAILY_BRUSH_COUNTS = {}
        SERVER.DAILY_DUNGEON_COUNTS = {}
        SERVER.DAILY_TASK_COMPLETIONS = {}

    def tearDown(self) -> None:
        for name, value in self.originals.items():
            setattr(SERVER, name, value)
        self.tempdir.cleanup()

    def test_legacy_state_migrates_and_survives_cache_restart(self) -> None:
        storage_key = "20260713|1608602|area351|928"
        SERVER.ACCOUNT_RECORDS_FILE.write_text(
            json.dumps({
                "accounts": [{
                    "sessionId": "session-1",
                    "username": "1608602",
                    "password": "secret",
                    "serverQuery": "周年服351区",
                }],
            }),
            encoding="utf-8",
        )
        SERVER.RUNTIME_STATE_FILE.write_text(
            json.dumps({
                "dailyBrushCounts": {storage_key: 7},
                "dailyDungeonCounts": {storage_key: 2},
                "dailyTaskCompletions": {
                    storage_key: {
                        "autoSignIn": {
                            "completed": True,
                            "completedAt": 123456,
                            "source": "automation",
                        },
                    },
                },
            }),
            encoding="utf-8",
        )
        habit_dir = SERVER.ACCOUNT_CONFIG_DIR / "1608602_区351"
        habit_dir.mkdir()
        (habit_dir / SERVER.ACCOUNT_SETTINGS_FILENAME).write_text(
            json.dumps({
                "accountKey": "1608602_区351",
                "config": {"dailyLimit": 500},
                "formations": [{"enabled": True}],
            }),
            encoding="utf-8",
        )

        SERVER.initialize_account_state_database()

        self.assertEqual(
            SERVER.database_get_daily_counter(storage_key, "brushYellow"),
            7,
        )
        self.assertEqual(
            SERVER.database_get_daily_counter(storage_key, "dungeon"),
            2,
        )
        self.assertEqual(SERVER.database_account_records()[0]["username"], "1608602")
        self.assertEqual(
            SERVER.database_load_account_habits("1608602_区351")["config"]["dailyLimit"],
            500,
        )
        self.assertTrue(
            SERVER.DAILY_TASK_COMPLETIONS[storage_key]["autoSignIn"]["completed"]
        )
        with sqlite3.connect(SERVER.ACCOUNT_STATE_DB_FILE) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SERVER.ACCOUNT_STATE_SCHEMA_VERSION,
            )

        self.assertEqual(
            SERVER.database_increment_daily_counter(storage_key, "brushYellow"),
            8,
        )
        SERVER.DAILY_BRUSH_COUNTS.clear()
        SERVER.DAILY_TASK_COMPLETIONS.clear()
        SERVER.load_daily_state_cache_from_database()

        self.assertEqual(SERVER.DAILY_BRUSH_COUNTS[storage_key], 8)
        self.assertTrue(
            SERVER.DAILY_TASK_COMPLETIONS[storage_key]["autoSignIn"]["completed"]
        )

    def test_logs_area_catalog_and_runtime_snapshot_move_to_sqlite(self) -> None:
        SERVER.LOG_DIR.mkdir(parents=True)
        SERVER.ACCOUNT_LOG_DIR.mkdir(parents=True)
        SERVER.SYSTEM_LOG_FILE.write_text(
            json.dumps({
                "time": 100,
                "timeText": "legacy-system",
                "level": "info",
                "source": "legacy",
                "sessionId": "",
                "accountKey": "",
                "message": "旧系统日志",
            }) + "\n",
            encoding="utf-8",
        )
        (SERVER.ACCOUNT_LOG_DIR / "1001_区351.jsonl").write_text(
            json.dumps({
                "time": 101,
                "timeText": "legacy-account",
                "level": "info",
                "source": "legacy",
                "sessionId": "s1",
                "accountKey": "1001_区351",
                "message": "旧账号日志",
            }) + "\n",
            encoding="utf-8",
        )
        SERVER.AREA_CATALOG_FILE.write_text(
            json.dumps({
                "updatedAt": 102,
                "areas": [{
                    "target": "1",
                    "areaId": "351",
                    "areaName": "周年服351区",
                    "serverUrl": "https://example.invalid",
                    "serverKey": "qzone_351",
                }],
            }),
            encoding="utf-8",
        )
        SERVER.RUNTIME_STATE_FILE.write_text(
            json.dumps({"time": 103, "accounts": [], "sessions": []}),
            encoding="utf-8",
        )

        SERVER.initialize_account_state_database()

        self.assertEqual(
            SERVER.database_read_system_logs(10)[0]["message"],
            "旧系统日志",
        )
        self.assertEqual(
            SERVER.database_read_account_logs("1001_区351", 10)[0]["message"],
            "旧账号日志",
        )
        self.assertEqual(SERVER.read_area_catalog()["areas"][0]["areaId"], "351")
        self.assertEqual(SERVER.database_load_runtime_snapshot()["time"], 103)
        self.assertFalse(SERVER.LOG_DIR.exists())
        self.assertFalse(SERVER.AREA_CATALOG_FILE.exists())
        self.assertFalse(SERVER.RUNTIME_STATE_FILE.exists())

        SERVER.system_log("新系统日志", source="test")
        self.assertEqual(
            SERVER.database_read_system_logs(1)[0]["message"],
            "新系统日志",
        )

    def test_legacy_heal_all_record_is_displayed_as_plain_language(self) -> None:
        SERVER.initialize_account_state_database()
        with sqlite3.connect(SERVER.ACCOUNT_STATE_DB_FILE) as connection:
            connection.execute(
                """
                INSERT INTO success_records
                    (time, time_text, session_id, account_key,
                     category, message, detail_json)
                VALUES (1, 'legacy', 's1', '1001_区352',
                        '治疗', '兵种0 -1', NULL)
                """
            )

        records = SERVER.database_read_success_records("1001_区352")

        self.assertEqual(records[0]["message"], "全部伤兵")

    def test_starter_deployments_are_projected_into_success_records(self) -> None:
        SERVER.initialize_account_state_database()
        with sqlite3.connect(SERVER.ACCOUNT_STATE_DB_FILE) as connection:
            connection.execute(
                """
                INSERT INTO starter_jobs(
                    job_id, account_id, platform, target_server, target_level,
                    status, current_stage, current_step, progress,
                    control_state, snapshot_json, last_error,
                    created_at, updated_at
                ) VALUES(
                    'job-1', 'session-1', 'test', '1014', 66,
                    'running', 'five_stage_4', 'running', 50,
                    'running', '{}', '', 1, 200
                )
                """
            )
            bandit_result = {
                "success": True,
                "targetLevel": 2,
                "general": {"id": "1", "name": "百骑将", "troopLimit": 144},
                "target": {
                    "id": 7,
                    "name": "2级山贼",
                    "x": 65,
                    "y": 45,
                },
                "dispatch": {
                    "success": True,
                    "successBattleId": 12345,
                },
                "healing": {"success": True},
            }
            dungeon_result = {
                "success": True,
                "general": {"id": "2", "name": "副本将", "troopLimit": 300},
                "stage": {"chapter": 0, "stage": 2, "loop": True},
                "battle": {"success": True, "battleId": 67890},
                "healing": {"success": True},
            }
            for action_key, result, finished_at in (
                ("bandit", bandit_result, 100),
                ("dungeon", dungeon_result, 200),
            ):
                connection.execute(
                    """
                    INSERT INTO starter_action_queue(
                        job_id, action_key, action_type, priority, status,
                        payload_json, result_json, not_before, attempts,
                        created_at, updated_at, started_at, finished_at
                    ) VALUES(
                        'job-1', ?, 'five-stage-growth', 1000, 'success',
                        '{}', ?, 0, 1, ?, ?, ?, ?
                    )
                    """,
                    (
                        action_key,
                        json.dumps(result, ensure_ascii=False),
                        finished_at - 10,
                        finished_at,
                        finished_at - 5,
                        finished_at,
                    ),
                )
            connection.commit()

        _, brush_records = SERVER.read_success_records(
            "session-1", category="刷黄",
        )
        _, dungeon_records = SERVER.read_success_records(
            "session-1", category="副本",
        )

        self.assertEqual(len(brush_records), 1)
        self.assertEqual(brush_records[0]["message"], "百骑将 > 2级山贼(65，45)")
        self.assertEqual(
            brush_records[0]["detail"]["battleId"], 12345,
        )
        self.assertEqual(len(dungeon_records), 1)
        self.assertEqual(
            dungeon_records[0]["message"], "副本将 > 第1章第2关循环",
        )
        self.assertEqual(
            dungeon_records[0]["detail"]["battleId"], 67890,
        )

    def test_unversioned_database_is_backed_up_and_preserved(self) -> None:
        record = {
            "username": "1608602",
            "password": "secret",
            "serverQuery": "周年服351区",
            "platform": "热血三国联盟",
        }
        with sqlite3.connect(SERVER.ACCOUNT_STATE_DB_FILE) as connection:
            connection.execute(
                """
                CREATE TABLE account_records (
                    identity_key TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    server_query TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO account_records
                    (identity_key, username, server_query, payload_json, updated_at)
                VALUES (?, ?, ?, ?, 1)
                """,
                (
                    '["1608602","周年服351区"]',
                    "1608602",
                    "周年服351区",
                    json.dumps(record, ensure_ascii=False),
                ),
            )

        SERVER.initialize_account_state_database()

        self.assertEqual(SERVER.database_account_records(), [record])
        backups = list(
            (SERVER.ACCOUNT_STATE_DB_FILE.parent / "database_backups").glob(
                f"assistant_state.before_v{SERVER.ACCOUNT_STATE_SCHEMA_VERSION}"
                ".from_v0.*.sqlite3"
            )
        )
        self.assertEqual(len(backups), 1)
        with sqlite3.connect(backups[0]) as connection:
            payload = connection.execute(
                "SELECT payload_json FROM account_records"
            ).fetchone()[0]
            self.assertEqual(json.loads(payload)["password"], "secret")

    def test_failed_schema_migration_rolls_back(self) -> None:
        SERVER.initialize_account_state_database()
        original_version = SERVER.ACCOUNT_STATE_SCHEMA_VERSION
        original_migrations = dict(SERVER.ACCOUNT_STATE_SCHEMA_MIGRATIONS)

        def failing_migration(connection: sqlite3.Connection) -> None:
            connection.execute("CREATE TABLE should_rollback(value TEXT)")
            raise RuntimeError("intentional migration failure")

        try:
            failing_version = original_version + 1
            SERVER.ACCOUNT_STATE_SCHEMA_VERSION = failing_version
            SERVER.ACCOUNT_STATE_SCHEMA_MIGRATIONS[failing_version] = failing_migration
            SERVER.ACCOUNT_STATE_DB_READY = False

            with self.assertRaisesRegex(
                RuntimeError,
                "intentional migration failure",
            ):
                SERVER.initialize_account_state_database()
        finally:
            SERVER.ACCOUNT_STATE_SCHEMA_VERSION = original_version
            SERVER.ACCOUNT_STATE_SCHEMA_MIGRATIONS.clear()
            SERVER.ACCOUNT_STATE_SCHEMA_MIGRATIONS.update(original_migrations)

        with sqlite3.connect(SERVER.ACCOUNT_STATE_DB_FILE) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                original_version,
            )
            self.assertIsNone(
                connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='should_rollback'
                    """
                ).fetchone()
            )

    def test_newer_schema_is_rejected(self) -> None:
        with sqlite3.connect(SERVER.ACCOUNT_STATE_DB_FILE) as connection:
            connection.execute(
                f"PRAGMA user_version={SERVER.ACCOUNT_STATE_SCHEMA_VERSION + 1}"
            )

        with self.assertRaisesRegex(RuntimeError, "SQLite 数据版本过新"):
            SERVER.initialize_account_state_database()


if __name__ == "__main__":
    unittest.main()
