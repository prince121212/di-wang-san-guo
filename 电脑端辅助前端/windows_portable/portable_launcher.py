from __future__ import annotations

import os
import runpy
import shutil
import sqlite3
import threading
import urllib.request
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:17351/index.html"
HEALTH_URL = "http://127.0.0.1:17351/api/health"
STATE_DATABASE_NAME = "assistant_state.sqlite3"


def server_is_running() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=1) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def valid_state_database(data_dir: Path) -> bool:
    database_path = data_dir / STATE_DATABASE_NAME
    if not database_path.is_file():
        return False
    try:
        with sqlite3.connect(database_path) as connection:
            check = connection.execute("PRAGMA quick_check").fetchone()
            account_table = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='account_records'
                """
            ).fetchone()
        return bool(check and str(check[0]).lower() == "ok" and account_table)
    except sqlite3.Error:
        return False


def find_legacy_data_directory(
    data_dir: Path,
    preferred_dir: Path,
    search_root: Path,
) -> Path:
    candidates: list[Path] = []
    preferred_dir = preferred_dir.resolve()
    if preferred_dir != data_dir.resolve() and valid_state_database(preferred_dir):
        candidates.append(preferred_dir)
    try:
        for package_dir in search_root.resolve().iterdir():
            candidate = package_dir / "data"
            if (
                candidate.resolve() != data_dir.resolve()
                and candidate.resolve() != preferred_dir
                and valid_state_database(candidate)
            ):
                candidates.append(candidate)
    except OSError:
        pass
    if not candidates:
        return preferred_dir
    return max(
        candidates,
        key=lambda path: (path / STATE_DATABASE_NAME).stat().st_mtime,
    )


def migrate_legacy_data_directory(data_dir: Path, legacy_data_dir: Path) -> bool:
    """Copy a V0.0.1 portable data directory into the stable Windows location."""
    data_dir = data_dir.resolve()
    legacy_data_dir = legacy_data_dir.resolve()
    if data_dir == legacy_data_dir or valid_state_database(data_dir):
        data_dir.mkdir(parents=True, exist_ok=True)
        return False
    if not valid_state_database(legacy_data_dir):
        data_dir.mkdir(parents=True, exist_ok=True)
        return False

    data_dir.parent.mkdir(parents=True, exist_ok=True)
    if data_dir.exists():
        shutil.copytree(legacy_data_dir, data_dir, dirs_exist_ok=True)
    else:
        staging_dir = data_dir.with_name(data_dir.name + ".migrating")
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        shutil.copytree(legacy_data_dir, staging_dir)
        staging_dir.replace(data_dir)
    if not (data_dir / STATE_DATABASE_NAME).is_file():
        raise RuntimeError("旧版数据迁移失败：未找到 SQLite 数据库")
    print(f"已自动继承旧版数据：{legacy_data_dir} -> {data_dir}")
    return True


def prepare_data_directory() -> Path:
    data_dir = Path(
        os.environ.get("DWPM_DATA_DIR", str(ROOT / "data"))
    ).expanduser()
    legacy_data_dir = Path(
        os.environ.get("DWPM_LEGACY_DATA_DIR", str(ROOT / "data"))
    ).expanduser()
    legacy_data_dir = find_legacy_data_directory(
        data_dir,
        legacy_data_dir,
        ROOT.parent,
    )
    migrate_legacy_data_directory(data_dir, legacy_data_dir)
    return data_dir.resolve()


def main() -> None:
    if server_is_running():
        print("电脑版辅助已经在运行，正在打开页面...")
        webbrowser.open(URL)
        return
    data_dir = prepare_data_directory()
    print(f"用户数据目录：{data_dir}")
    timer = threading.Timer(1.5, webbrowser.open, args=(URL,))
    timer.daemon = True
    timer.start()
    runpy.run_path(str(ROOT / "app" / "server.py"), run_name="__main__")


if __name__ == "__main__":
    main()
