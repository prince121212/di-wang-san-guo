#!/usr/bin/env python3
"""Prepare base_channel_extra.json for offline device regression replay contracts.

Input can be one of:
- LocalAccountRepository export: {"schema_version":"0.2-real-protocol-accounts","accounts":[...]}
- a single exported account object with session.channelExtra
- a session object with channelExtra
- a raw channelExtra JSON object

The output intentionally contains channelExtra-style evidence only. It does not include
passwords or tokenCiphertext and does not enable network sends.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

TOOL_DIR = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("verify_replay_contract", TOOL_DIR / "verify_replay_contract.py")
verify_replay_contract = importlib.util.module_from_spec(spec)
sys.modules["verify_replay_contract"] = verify_replay_contract
spec.loader.exec_module(verify_replay_contract)  # type: ignore[union-attr]

SAFE_FALSE_FLAGS = {
    "networkSendAllowed": "false",
    "deviceRegressionNetworkSendAllowed": "false",
    "baseChannelExtraNetworkSendAllowed": "false",
}
SENSITIVE_KEYS = {
    "password", "plainPassword", "tokenCiphertext", "encryptedPassword", "session", "cookie", "authorization",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def stringify_map(data: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in data.items():
        if value is None:
            continue
        if key in SENSITIVE_KEYS:
            continue
        if isinstance(value, (dict, list)):
            out[str(key)] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            text = str(value)
            if text != "":
                out[str(key)] = text
    return out


def extract_accounts(root: Any) -> list[dict[str, Any]]:
    if isinstance(root, dict) and isinstance(root.get("accounts"), list):
        return [item for item in root["accounts"] if isinstance(item, dict)]
    if isinstance(root, dict) and isinstance(root.get("session"), dict):
        return [root]
    return []


def choose_account(accounts: list[dict[str, Any]], account_id: str | None = None, role_name: str | None = None) -> dict[str, Any] | None:
    enabled = [acc for acc in accounts if acc.get("enabled", True) is not False]
    candidates = enabled or accounts
    if account_id:
        for acc in candidates:
            if str(acc.get("id", "")) == str(account_id):
                return acc
    if role_name:
        for acc in candidates:
            names = [acc.get("monarchName"), acc.get("displayName")]
            session = acc.get("session") if isinstance(acc.get("session"), dict) else {}
            extra = session.get("channelExtra", {}) if isinstance(session, dict) and isinstance(session.get("channelExtra"), dict) else {}
            names.append(extra.get("roleName"))
            if any(str(name) == role_name for name in names if name is not None):
                return acc
    real = [acc for acc in candidates if acc.get("loginState") == "REAL_PROTOCOL_LOGIN_OK" or (isinstance(acc.get("session"), dict) and acc["session"].get("sourceMode") == 1)]
    return (real or candidates)[0] if (real or candidates) else None


def extract_base_extra(root: Any, account_id: str | None = None, role_name: str | None = None) -> tuple[dict[str, str], str]:
    if isinstance(root, dict):
        accounts = extract_accounts(root)
        if accounts:
            account = choose_account(accounts, account_id=account_id, role_name=role_name)
            if not account:
                raise ValueError("no matching account found")
            session = account.get("session")
            if not isinstance(session, dict):
                raise ValueError("selected account has no session object")
            extra = session.get("channelExtra")
            if not isinstance(extra, dict):
                raise ValueError("selected account session has no channelExtra object")
            out = stringify_map(extra)
            # Keep non-sensitive account/session selectors useful for replay verification.
            if "roleName" not in out and account.get("monarchName"):
                out["roleName"] = str(account["monarchName"])
            if "sourceMode" not in out and session.get("sourceMode") is not None:
                out["sourceMode"] = str(session["sourceMode"])
            if "accountId" not in out and session.get("accountId") is not None:
                out["accountId"] = str(session["accountId"])
            return out, f"account:{account.get('id', '')}"
        if isinstance(root.get("channelExtra"), dict):
            out = stringify_map(root["channelExtra"])
            if root.get("sourceMode") is not None:
                out.setdefault("sourceMode", str(root["sourceMode"]))
            if root.get("accountId") is not None:
                out.setdefault("accountId", str(root["accountId"]))
            return out, "session"
        # Treat as raw channelExtra only if it does not look like a schema wrapper.
        return stringify_map(root), "raw-channel-extra"
    raise ValueError("input must be a JSON object")


def merge_extra_files(base: dict[str, str], paths: list[str]) -> dict[str, str]:
    merged = dict(base)
    for item in paths:
        data = load_json(Path(item))
        if not isinstance(data, dict):
            raise ValueError(f"{item} must contain a JSON object")
        # Accept either raw extra or an exported account/session wrapper.
        extracted, _ = extract_base_extra(data)
        merged.update(extracted)
    return merged


def prepare(
    input_path: Path,
    account_id: str | None = None,
    role_name: str | None = None,
    merge_files: list[str] | None = None,
) -> dict[str, Any]:
    root = load_json(input_path)
    extra, source = extract_base_extra(root, account_id=account_id, role_name=role_name)
    extra = merge_extra_files(extra, merge_files or [])
    extra = verify_replay_contract.with_recovered_role_resource(extra)
    extra.update(SAFE_FALSE_FLAGS)
    extra["baseChannelExtraImporter"] = "tools/prepare_base_channel_extra.py"
    contract = verify_replay_contract.verify(extra)
    return {
        "summary": {
            "source": source,
            "fieldCount": len(extra),
            "shuaHuangOfflineReplayReady": contract["summary"]["shuaHuangOfflineReplayReady"],
            "dailyOfflineReplayReady": contract["summary"]["dailyOfflineReplayReady"],
            "mineOfflineReplayReady": contract["summary"]["mineOfflineReplayReady"],
            "realActionNetworkAllowed": False,
            "blocker": "base channelExtra preparation only; true action send remains disabled",
        },
        "baseChannelExtra": extra,
        "replayContract": contract,
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# Base ChannelExtra 准备报告",
        "",
        "## Summary",
        "",
        f"- source: {s['source']}",
        f"- fieldCount: {s['fieldCount']}",
        f"- shuaHuangOfflineReplayReady: {str(s['shuaHuangOfflineReplayReady']).lower()}",
        f"- dailyOfflineReplayReady: {str(s['dailyOfflineReplayReady']).lower()}",
        f"- mineOfflineReplayReady: {str(s['mineOfflineReplayReady']).lower()}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## Replay contract missing",
        "",
        "```json",
        json.dumps(report["replayContract"]["missing"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Base channelExtra preview",
        "",
        "```json",
        json.dumps(report["baseChannelExtra"], ensure_ascii=False, indent=2, sort_keys=True)[:4000],
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="LocalAccountRepository export, account JSON, session JSON, or raw channelExtra JSON")
    ap.add_argument("--account-id", help="Select account id when input contains accounts[]")
    ap.add_argument("--role-name", help="Select role/monarch name when input contains accounts[]")
    ap.add_argument("--merge-extra", action="append", default=[], help="Merge another channelExtra/session/account JSON after the base; can be repeated")
    ap.add_argument("--out", help="Write base_channel_extra.json; defaults to stdout report JSON")
    ap.add_argument("--report-out", help="Write full JSON report")
    ap.add_argument("--markdown-out", help="Write Markdown report")
    ns = ap.parse_args()
    report = prepare(Path(ns.input), account_id=ns.account_id, role_name=ns.role_name, merge_files=ns.merge_extra)
    if ns.out:
        Path(ns.out).write_text(json.dumps(report["baseChannelExtra"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if ns.report_out:
        Path(ns.report_out).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")
    if not ns.out and not ns.report_out and not ns.markdown_out:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
