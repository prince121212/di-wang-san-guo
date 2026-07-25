#!/usr/bin/env python3
"""Check the installed self-developed app's saved real session with a read-only 0x1016 request.

This tool reads only app-private shared_prefs via `adb shell run-as`, sends the game's
read-only role-state request (0x1016), and writes JSON/Markdown evidence. It never needs
or prints the account password.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import struct
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HEADER = "1660606`7054`0000480502"
PACKAGE = "com.example.dwpmclone"


def adb_run_as_cat(path: str, package: str = PACKAGE) -> str:
    return subprocess.check_output(
        ["adb", "shell", "run-as", package, "cat", path],
        text=True,
        errors="ignore",
    )


def load_saved_session(package: str = PACKAGE) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    raw = adb_run_as_cat("shared_prefs/dwpm_clone_accounts.xml", package=package)
    m = re.search(r'<string name="accounts_json">(.*?)</string>', raw, re.S)
    if not m:
        raise SystemExit("accounts_json not found; 请先在自研 App 完成真实协议登录/同步")
    root = json.loads(html.unescape(m.group(1)))
    accounts = root.get("accounts") or []
    if not accounts:
        raise SystemExit("accounts_json has no accounts; 请先在自研 App 完成真实协议登录/同步")
    account = accounts[0]
    session = account.get("session") or {}
    extra = session.get("channelExtra") or {}
    return account, session, {str(k): str(v) for k, v in extra.items()}


def utf(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack(">H", len(b)) + b


def make_packet(opcode: int, payload: bytes, dm: int) -> bytes:
    out = bytearray()
    out += utf(HEADER)
    out += struct.pack(">q", int(time.time() * 1000))
    out += struct.pack(">B", 1)
    out += struct.pack(">q", dm)
    out += struct.pack(">q", 0)
    out += struct.pack(">H", len(payload))
    out += struct.pack(">H", opcode)
    out += utf("")
    out += payload
    return bytes(out)


def parse_response(data: bytes) -> list[dict[str, Any]]:
    p = 0
    packets: list[dict[str, Any]] = []

    def need(n: int) -> None:
        if p + n > len(data):
            raise ValueError(f"parse overflow pos={p} need={n} size={len(data)}")

    def u8() -> int:
        nonlocal p
        need(1)
        v = data[p]
        p += 1
        return v

    def i64() -> int:
        nonlocal p
        need(8)
        v = struct.unpack(">q", data[p:p + 8])[0]
        p += 8
        return v

    def i32() -> int:
        nonlocal p
        need(4)
        v = struct.unpack(">i", data[p:p + 4])[0]
        p += 4
        return v

    def u16() -> int:
        nonlocal p
        need(2)
        v = struct.unpack(">H", data[p:p + 2])[0]
        p += 2
        return v

    try:
        # Game server response shape observed from the original direct probes:
        # u8 outerCount; each outer has u8 innerCount; then each packet is
        # i64 long0, i64 long1, u8 obf, i32 payloadLen, u16 opcode, u8 frag, payload.
        outer = u8()
        for outer_index in range(outer):
            inner = u8()
            for inner_index in range(inner):
                long0 = i64()
                long1 = i64()
                obf = u8()
                ln = i32()
                opcode = u16()
                frag = u8()
                need(ln)
                payload = data[p:p + ln]
                p += ln
                packets.append({
                    "outer": outer_index,
                    "inner": inner_index,
                    "opcode": opcode,
                    "opcodeHex": f"0x{opcode:04x}",
                    "long0": long0,
                    "long1": long1,
                    "obf": obf,
                    "frag": frag,
                    "len": ln,
                    "payloadHex": payload.hex(),
                    "textPreview": printable(payload),
                })
    except Exception as exc:
        packets.append({"parseError": str(exc), "rawHex": data.hex()[:4096]})
    return packets


def printable(b: bytes) -> str:
    text = b.decode("utf-8", errors="ignore")
    text = "".join(ch if ch.isprintable() else " " for ch in text)
    return re.sub(r"\s+", " ", text).strip()


def post_1016(game_http: str, dm: int, role_id: int) -> tuple[int, bytes, list[dict[str, Any]]]:
    body = make_packet(0x1016, struct.pack(">q", role_id), dm)
    req = urllib.request.Request(
        game_http,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/octet-stream",
            "User-Agent": "DWPMClone/1.0 live-1016-check",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read()
            code = r.status
    except urllib.error.HTTPError as e:
        data = e.read()
        code = e.code
    return code, data, parse_response(data)


def classify(packets: list[dict[str, Any]]) -> tuple[bool, bool, str]:
    opcodes = [p.get("opcodeHex") for p in packets]
    text = " ".join(str(p.get("message", "")) + " " + str(p.get("textPreview", "")) for p in packets)
    expired = "没有角色信息" in text or "沒有角色信息" in text or "0x8016" in opcodes
    fresh = "0x8004" in opcodes and not expired
    if fresh:
        reason = "0x1016 returned 0x8004 role state"
    elif expired:
        reason = "0x1016 returned expired-role evidence: 0x8016/没有角色信息"
    else:
        reason = f"0x1016 did not return 0x8004; opcodes={opcodes}"
    return fresh, expired, reason


def build_report(package: str = PACKAGE) -> dict[str, Any]:
    account, session, extra = load_saved_session(package=package)
    game_http = extra.get("gameHttp") or extra.get("gameHttpUrl")
    dm = int(extra.get("dm") or "0")
    role_id = int(extra.get("roleId") or account.get("id") or session.get("accountId") or "0")
    if not game_http or not dm or not role_id:
        raise SystemExit("saved session missing gameHttp/dm/roleId")
    http, data, packets = post_1016(game_http, dm, role_id)
    fresh, expired, reason = classify(packets)
    return {
        "checkedAtMillis": int(time.time() * 1000),
        "package": package,
        "accountId": account.get("id"),
        "username": account.get("username"),
        "roleName": extra.get("roleName") or account.get("displayName"),
        "roleId": role_id,
        "serverName": account.get("serverName"),
        "gameHttp": game_http,
        "http": http,
        "responseBytes": len(data),
        "opcodes": [p.get("opcodeHex") for p in packets],
        "sessionFresh": fresh,
        "sessionExpiredEvidence": expired,
        "reason": reason,
        "packets": packets,
    }


def to_markdown(report: dict[str, Any]) -> str:
    return "\n".join([
        "# Live 0x1016 session freshness check",
        "",
        f"- checkedAtMillis: {report['checkedAtMillis']}",
        f"- package: {report['package']}",
        f"- accountId: {report['accountId']}",
        f"- roleName: {report['roleName']}",
        f"- roleId: {report['roleId']}",
        f"- serverName: {report['serverName']}",
        f"- http: {report['http']}",
        f"- responseBytes: {report['responseBytes']}",
        f"- opcodes: {', '.join(map(str, report['opcodes']))}",
        f"- sessionFresh: {str(report['sessionFresh']).lower()}",
        f"- sessionExpiredEvidence: {str(report['sessionExpiredEvidence']).lower()}",
        f"- reason: {report['reason']}",
        "",
        "## Packets",
        "",
        "```json",
        json.dumps(report["packets"], ensure_ascii=False, indent=2)[:12000],
        "```",
    ])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", default=PACKAGE)
    ap.add_argument("--out", default="reports/live_1016_session_freshness_current.json")
    ap.add_argument("--markdown-out", default="reports/live_1016_session_freshness_current.md")
    ns = ap.parse_args()
    report = build_report(package=ns.package)
    Path(ns.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")
    print(json.dumps({
        "http": report["http"],
        "opcodes": report["opcodes"],
        "sessionFresh": report["sessionFresh"],
        "sessionExpiredEvidence": report["sessionExpiredEvidence"],
        "reason": report["reason"],
        "out": ns.out,
        "markdownOut": ns.markdown_out,
    }, ensure_ascii=False, indent=2))
    return 0 if report["sessionFresh"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
