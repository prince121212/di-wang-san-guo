from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_account_persistence_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class AccountPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.originals = {
            "ACCOUNT_STATE_DB_FILE": SERVER.ACCOUNT_STATE_DB_FILE,
            "ACCOUNT_STATE_DB_READY": SERVER.ACCOUNT_STATE_DB_READY,
            "REPORT_DIR": SERVER.REPORT_DIR,
            "ACCOUNT_RECORDS_FILE": SERVER.ACCOUNT_RECORDS_FILE,
            "ACCOUNT_RECORD_BACKUP_DIR": SERVER.ACCOUNT_RECORD_BACKUP_DIR,
            "ACCOUNT_CONFIG_DIR": SERVER.ACCOUNT_CONFIG_DIR,
            "LOG_DIR": SERVER.LOG_DIR,
            "ACCOUNT_LOG_DIR": SERVER.ACCOUNT_LOG_DIR,
            "SYSTEM_LOG_FILE": SERVER.SYSTEM_LOG_FILE,
            "AREA_CATALOG_FILE": SERVER.AREA_CATALOG_FILE,
            "RUNTIME_STATE_FILE": SERVER.RUNTIME_STATE_FILE,
        }
        SERVER.ACCOUNT_STATE_DB_FILE = root / "assistant_state.sqlite3"
        SERVER.ACCOUNT_STATE_DB_READY = False
        SERVER.REPORT_DIR = root
        SERVER.ACCOUNT_RECORDS_FILE = root / "account_records.json"
        SERVER.ACCOUNT_RECORD_BACKUP_DIR = root / "backups"
        SERVER.ACCOUNT_CONFIG_DIR = root / "account_configs"
        SERVER.LOG_DIR = root / "logs"
        SERVER.ACCOUNT_LOG_DIR = SERVER.LOG_DIR / "accounts"
        SERVER.SYSTEM_LOG_FILE = SERVER.LOG_DIR / "system_recent.jsonl"
        SERVER.AREA_CATALOG_FILE = root / "area_catalog.json"
        SERVER.RUNTIME_STATE_FILE = root / "runtime_state.json"
        SERVER.initialize_account_state_database()

    def tearDown(self) -> None:
        for name, value in self.originals.items():
            setattr(SERVER, name, value)
        self.tempdir.cleanup()

    def records(self) -> list[dict]:
        return SERVER.database_account_records()

    def test_runtime_subset_cannot_erase_existing_accounts_or_passwords(self) -> None:
        SERVER.write_account_records_file([
            {
                "sessionId": "a",
                "username": "1001",
                "password": "secret-a",
                "serverQuery": "351区",
            },
            {
                "sessionId": "b",
                "username": "1002",
                "password": "secret-b",
                "serverQuery": "351区",
            },
        ])
        SERVER.write_account_records_file([
            {
                "sessionId": "a-new",
                "username": "1001",
                "serverQuery": "351区",
            },
        ])
        records = {
            SERVER.account_identity(record): record
            for record in self.records()
        }
        self.assertEqual(len(records), 2)
        self.assertEqual(records[("1001", "351区")]["password"], "secret-a")
        self.assertEqual(records[("1002", "351区")]["password"], "secret-b")

    def test_explicit_remove_deletes_only_selected_identity(self) -> None:
        first = {
            "sessionId": "a",
            "username": "1001",
            "password": "secret-a",
            "serverQuery": "351区",
        }
        second = {
            "sessionId": "b",
            "username": "1002",
            "password": "secret-b",
            "serverQuery": "351区",
        }
        SERVER.write_account_records_file([first, second])
        SERVER.remove_account_record(first)
        self.assertEqual(
            [SERVER.account_identity(record) for record in self.records()],
            [("1002", "351区")],
        )
        self.assertFalse(SERVER.ACCOUNT_RECORDS_FILE.exists())
        self.assertFalse(SERVER.ACCOUNT_RECORD_BACKUP_DIR.exists())


if __name__ == "__main__":
    unittest.main()
