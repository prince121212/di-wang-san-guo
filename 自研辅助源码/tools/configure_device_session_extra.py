#!/usr/bin/env python3
"""Safely update the installed self-app saved session channelExtra.

This is a focused device helper for live regression setup.  It mutates only the
first saved account's ``session.channelExtra`` in ``dwpm_clone_accounts.xml`` and
prints a redacted summary so credentials are not echoed.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

PACKAGE = "com.example.dwpmclone"
PREF_PATH = "shared_prefs/dwpm_clone_accounts.xml"

SENSITIVE_KEY_RE = re.compile(r"(pass|pwd|token|cipher|secret|sign)", re.I)


def adb(*args: str, input_text: str | None = None) -> str:
    return subprocess.check_output(["adb", *args], input=input_text, text=True, errors="ignore")


def read_prefs(package: str = PACKAGE) -> str:
    return adb("shell", "run-as", package, "cat", PREF_PATH)


def write_prefs(raw_xml: str, package: str = PACKAGE) -> None:
    remote = f"/data/local/tmp/dwpm_clone_accounts_{int(time.time() * 1000)}.xml"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fp:
        fp.write(raw_xml)
        local = fp.name
    try:
        subprocess.run(["adb", "push", local, remote], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["adb", "shell", "chmod", "0644", remote], check=True)
        subprocess.run(["adb", "shell", "run-as", package, "cp", remote, PREF_PATH], check=True)
    finally:
        subprocess.run(["adb", "shell", "rm", "-f", remote], check=False)
        Path(local).unlink(missing_ok=True)


def split_accounts_xml(raw_xml: str) -> tuple[str, dict[str, Any], str]:
    m = re.search(r'(<string name="accounts_json">)(.*?)(</string>)', raw_xml, re.S)
    if not m:
        raise ValueError("accounts_json not found")
    root = json.loads(html.unescape(m.group(2)))
    if not isinstance(root, dict):
        raise ValueError("accounts_json root is not an object")
    return raw_xml[:m.start(2)], root, raw_xml[m.end(2):]


def render_accounts_xml(prefix: str, root: dict[str, Any], suffix: str) -> str:
    body = json.dumps(root, ensure_ascii=False, separators=(",", ":"))
    return prefix + html.escape(body, quote=False) + suffix


def parse_set(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"--set expects KEY=VALUE, got {item!r}")
        k, v = item.split("=", 1)
        k = k.strip()
        if not k:
            raise ValueError(f"--set key is empty in {item!r}")
        out[k] = v.strip()
    return out


def mutate_first_account_channel_extra(root: dict[str, Any], updates: dict[str, str], remove: list[str] | None = None) -> dict[str, Any]:
    accounts = root.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("no accounts")
    account = accounts[0]
    if not isinstance(account, dict):
        raise ValueError("first account is not an object")
    session = account.setdefault("session", {})
    if not isinstance(session, dict):
        raise ValueError("first account session is not an object")
    extra = session.setdefault("channelExtra", {})
    if not isinstance(extra, dict):
        raise ValueError("first account session.channelExtra is not an object")
    for key in remove or []:
        extra.pop(key, None)
    for key, value in updates.items():
        extra[str(key)] = str(value)
    return account


def redacted_account_summary(account: dict[str, Any], changed_keys: list[str]) -> dict[str, Any]:
    session = account.get("session") if isinstance(account.get("session"), dict) else {}
    extra = session.get("channelExtra") if isinstance(session.get("channelExtra"), dict) else {}
    gates = {
        key: ("***" if SENSITIVE_KEY_RE.search(key) else extra.get(key))
        for key in changed_keys
    }
    return {
        "accountId": account.get("id"),
        "username": account.get("username"),
        "serverName": account.get("serverName"),
        "displayName": account.get("displayName"),
        "changedKeys": changed_keys,
        "changedValuesRedacted": gates,
    }


def default_brush_yellow_updates(enable_fallback: bool = True) -> dict[str, str]:
    updates = {
        "realActionNetworkAllowed": "true",
        "realActionSendReady": "true",
        "realActionScope": "brush-yellow",
    }
    if enable_fallback:
        updates["allowRecoveredGeneralFallbackFormation"] = "true"
    return updates


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", default=PACKAGE)
    ap.add_argument("--set", dest="sets", action="append", default=[], help="channelExtra KEY=VALUE; may be repeated")
    ap.add_argument("--remove", action="append", default=[], help="channelExtra key to remove; may be repeated")
    ap.add_argument("--enable-brush-yellow-gates", action="store_true", help="set realActionNetworkAllowed/sendReady/scope for brush-yellow")
    ap.add_argument("--no-fallback-formation", action="store_true", help="do not set allowRecoveredGeneralFallbackFormation with --enable-brush-yellow-gates")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-stop-first", action="store_true", help="force-stop package before reading/writing prefs to avoid stale overwrites")
    ap.add_argument("--restart", action="store_true", help="start package with monkey after writing")
    ap.add_argument("--backup-out", default="reports/device_session_extra_backup_accounts.xml")
    ns = ap.parse_args()

    if ns.force_stop_first:
        subprocess.run(["adb", "shell", "am", "force-stop", ns.package], check=False)

    raw = read_prefs(package=ns.package)
    Path(ns.backup_out).write_text(raw, encoding="utf-8")
    prefix, root, suffix = split_accounts_xml(raw)
    updates = parse_set(ns.sets)
    if ns.enable_brush_yellow_gates:
        updates = {**default_brush_yellow_updates(enable_fallback=not ns.no_fallback_formation), **updates}
    changed_keys = sorted(set(updates) | set(ns.remove))
    account = mutate_first_account_channel_extra(root, updates, ns.remove)
    new_xml = render_accounts_xml(prefix, root, suffix)

    if not ns.dry_run:
        write_prefs(new_xml, package=ns.package)
        if ns.restart:
            subprocess.run(["adb", "shell", "monkey", "-p", ns.package, "-c", "android.intent.category.LAUNCHER", "1"], check=False)

    print(json.dumps({
        "package": ns.package,
        "dryRun": ns.dry_run,
        "backupOut": ns.backup_out,
        **redacted_account_summary(account, changed_keys),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
