from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_PATH = (
    ROOT
    / "电脑端辅助前端"
    / "windows_portable"
    / "portable_launcher.py"
)
START_SCRIPT_PATH = (
    ROOT
    / "电脑端辅助前端"
    / "windows_portable"
    / "启动辅助.bat"
)
SPEC = importlib.util.spec_from_file_location(
    "dwpm_windows_portable_test",
    LAUNCHER_PATH,
)
LAUNCHER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(LAUNCHER)


class WindowsPortableTests(unittest.TestCase):
    @staticmethod
    def create_state_database(data_dir: Path, marker: str) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(data_dir / "assistant_state.sqlite3") as connection:
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
                VALUES (?, ?, '', '{}', 1)
                """,
                (marker, marker),
            )

    def test_first_upgrade_copies_legacy_data_to_stable_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            legacy = root / "old-portable" / "data"
            stable = root / "local-app-data" / "DWPMDesktop" / "data"
            self.create_state_database(legacy, "old")
            (legacy / "shared_maps").mkdir()
            (legacy / "shared_maps" / "shared_maps.sqlite3").write_bytes(
                b"old-maps"
            )

            migrated = LAUNCHER.migrate_legacy_data_directory(stable, legacy)

            self.assertTrue(migrated)
            with sqlite3.connect(
                stable / "assistant_state.sqlite3"
            ) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT username FROM account_records"
                    ).fetchone()[0],
                    "old",
                )
            self.assertEqual(
                (stable / "shared_maps" / "shared_maps.sqlite3").read_bytes(),
                b"old-maps",
            )
            self.assertTrue((legacy / "assistant_state.sqlite3").exists())

    def test_existing_stable_database_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            legacy = root / "old" / "data"
            stable = root / "stable" / "data"
            self.create_state_database(legacy, "old")
            self.create_state_database(stable, "current")

            migrated = LAUNCHER.migrate_legacy_data_directory(stable, legacy)

            self.assertFalse(migrated)
            with sqlite3.connect(
                stable / "assistant_state.sqlite3"
            ) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT username FROM account_records"
                    ).fetchone()[0],
                    "current",
                )

    def test_first_upgrade_discovers_sibling_old_version(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            current = root / "new-version"
            preferred = current / "data"
            old_data = root / "old-version" / "data"
            stable = root / "local-app-data" / "DWPMDesktop" / "data"
            current.mkdir()
            self.create_state_database(old_data, "old")

            found = LAUNCHER.find_legacy_data_directory(
                stable,
                preferred,
                root,
            )

            self.assertEqual(found, old_data.resolve())

    def test_start_script_uses_stable_local_app_data(self) -> None:
        source = START_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn(r"%LOCALAPPDATA%\DWPMDesktop", source)
        self.assertIn('set "DWPM_DATA_DIR=%DWPM_USER_HOME%\\data"', source)
        self.assertIn('set "DWPM_LEGACY_DATA_DIR=%CD%\\data"', source)


if __name__ == "__main__":
    unittest.main()
