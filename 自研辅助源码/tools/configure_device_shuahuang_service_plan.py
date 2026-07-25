#!/usr/bin/env python3
"""Configure the installed app so the ForegroundService creates a brush-yellow task.

Older installed builds only create ShuaHuangTask from LocalConfigRepository saved
screen config.  This helper writes the minimal `764::shua_huang` config and can
also pin `mapTargetsJson` to a known live-success target.  It does not start the
service by itself.
"""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


device_extra = load_module("configure_device_session_extra", ROOT / "configure_device_session_extra.py")

PACKAGE = "com.example.dwpmclone"
CONFIG_PREF_PATH = "shared_prefs/dwpm_clone_configs.xml"


def minimal_shuahuang_config(enabled: bool = True, daily_limit: int = 1, target_huang_jin: bool = False) -> dict[str, Any]:
    return {
        "values": {
            "APKTOOL_RENAMED_0x7f070073": enabled,
            "APKTOOL_RENAMED_0x7f070163": daily_limit,
            "APKTOOL_RENAMED_0x7f070165": 0,
            "APKTOOL_RENAMED_0x7f070166": 0,
            "APKTOOL_RENAMED_0x7f070164": 0,
            "APKTOOL_RENAMED_0x7f070188": target_huang_jin,
        }
    }


def render_config_prefs(account_id: int, config: dict[str, Any]) -> str:
    key = f"{account_id}::shua_huang"
    value = html.escape(json.dumps(config, ensure_ascii=False, separators=(",", ":")), quote=True)
    return "\n".join([
        "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>",
        "<map>",
        f'    <string name="{html.escape(key, quote=True)}">{value}</string>',
        "</map>",
        "",
    ])


def write_text_to_device(package: str, remote_path: str, text: str) -> None:
    import subprocess
    import tempfile

    tmp_remote = f"/data/local/tmp/dwpm_service_plan_{int(time.time() * 1000)}.xml"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fp:
        fp.write(text)
        local = fp.name
    try:
        subprocess.run(["adb", "push", local, tmp_remote], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["adb", "shell", "chmod", "0644", tmp_remote], check=True)
        subprocess.run(["adb", "shell", "run-as", package, "cp", tmp_remote, remote_path], check=True)
    finally:
        subprocess.run(["adb", "shell", "rm", "-f", tmp_remote], check=False)
        Path(local).unlink(missing_ok=True)


def load_success_target(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    target = data.get("chosenTarget")
    return target if isinstance(target, dict) else None


def target_to_map_targets_json(target: dict[str, Any]) -> str:
    raw = {
        "id": target.get("id"),
        "idHex": target.get("idHex"),
        "targetIdHex": target.get("idHex"),
        "coordX": target.get("x", 0),
        "coordY": target.get("y", 0),
        "kind": target.get("kind", "山贼"),
        "targetKind": target.get("kind", "山贼"),
        "level": target.get("rank", 0),
        "rank": target.get("rank", 0),
        "rawRecord": target.get("rawRecord", ""),
        "source": "live-success-target-pinned-for-service-regression",
    }
    return json.dumps([raw], ensure_ascii=False, separators=(",", ":"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", default=PACKAGE)
    ap.add_argument("--account-id", type=int, default=764)
    ap.add_argument("--daily-limit", type=int, default=1)
    ap.add_argument("--target-type", choices=["shanzei", "huangjin"], default="shanzei")
    ap.add_argument("--pin-success-target", action="store_true")
    ap.add_argument("--success-report", default="reports/live_brush_yellow_success_evidence_current.json")
    ap.add_argument("--dry-run", action="store_true")
    ns = ap.parse_args()

    config_xml = render_config_prefs(
        ns.account_id,
        minimal_shuahuang_config(
            enabled=True,
            daily_limit=ns.daily_limit,
            target_huang_jin=ns.target_type == "huangjin",
        ),
    )
    updates: dict[str, str] = {
        "shuaHuangDailyLimit": str(ns.daily_limit),
        "shuaHuangStartX": "0",
        "shuaHuangStartY": "0",
        "shuaHuangTargetType": "HUANG_JIN" if ns.target_type == "huangjin" else "SHAN_ZEI",
    }
    pinned_target = None
    if ns.pin_success_target:
        pinned_target = load_success_target(Path(ns.success_report))
        if pinned_target:
            updates["mapTargetsJson"] = target_to_map_targets_json(pinned_target)

    if not ns.dry_run:
        write_text_to_device(ns.package, CONFIG_PREF_PATH, config_xml)
        # Preserve existing gates/formations and only add task selection hints.
        argv = ["--package", ns.package]
        for k, v in updates.items():
            argv += ["--set", f"{k}={v}"]
        # Call module helpers directly to avoid spawning and to keep output redacted.
        raw = device_extra.read_prefs(package=ns.package)
        prefix, root, suffix = device_extra.split_accounts_xml(raw)
        device_extra.mutate_first_account_channel_extra(root, updates)
        device_extra.write_prefs(device_extra.render_accounts_xml(prefix, root, suffix), package=ns.package)

    print(json.dumps({
        "package": ns.package,
        "dryRun": ns.dry_run,
        "accountId": ns.account_id,
        "configPrefPath": CONFIG_PREF_PATH,
        "configWritten": not ns.dry_run,
        "changedExtraKeys": sorted(updates.keys()),
        "pinnedTarget": pinned_target,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
