#!/usr/bin/env python3
"""Calibrate recovered 041540/041542 read-only response captures.

The tool is offline-only. It consumes copied device/Frida/logcat text, extracts response
hex for the recovered read-only opcodes, parses known target/mine shapes, and emits:
- a JSON calibration report;
- optional Markdown summary;
- channelExtraCandidate keys that can be pasted into a real session for offline replay.

Accepted log shapes include:
  [readonly-response-json] {"opcode":"041540","responseHex":"..."}
  [readonly-response] opcode=041542 responseHex=...
  {"opcode":"0x1540","responsePayloadHex":"..."}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

JSON_OBJECT = re.compile(r"\{.*\}")
KV_EVENT = re.compile(
    r"(?:opcode|op)\s*[:=]\s*[\"']?(?P<opcode>0x?1?5?4[02]|04154[02]|154[02])[\"']?.*?"
    r"(?:responseHex|responsePayloadHex|payloadHex|bodyHex|hex)\s*[:=]\s*[\"']?(?P<hex>[0-9a-fA-F|\s]+)",
    re.I,
)
HEX_ONLY = re.compile(r"^[0-9a-fA-F|\s]{20,}$")

TARGET_KIND_MARKERS = [
    ("E5B1B1E8B38A", "山贼"),
    ("E5B1B1E8B4BC", "山贼"),
    ("E9BB83E5B7BE", "黄巾"),
    ("E9BB84E5B7BE", "黄巾"),
    ("E6B8A0E5B885", "渠帅"),
    ("E6B8A0E5B8A5", "渠帅"),
    ("E4B8BBE5B086", "主将"),
    ("E4B8BBE5B087", "主将"),
    ("E4B8BBE5B885", "主帅"),
    ("E4B8BBE5B8A5", "主帅"),
]
MINE_BASE_RECORD = re.compile(r"0000(?!00000000)[0-9A-F]{8}0[0-9AB]0[0-9A-F](?:00[0-9A-C][0-9A-F]){2}")
MINE_DETAIL = re.compile(r"02D[0-9A-F]{3}0[0-4]0[0-9A-F]0000[0-9A-F]{4}(?:00[0-9A-F]{2})?")
MINE_KIND = {
    "01": "金矿",
    "02": "银矿",
    "03": "冰玉矿",
    "04": "仙芝",
    "05": "玉露",
    "06": "玄铁矿",
    "07": "水晶矿",
    "08": "灵草",
    "09": "牧场",
    "0A": "镔铁矿",
    "0B": "浆果",
}


@dataclass
class Capture:
    opcode: str
    responseHex: str
    sourceLine: int
    sha256: str
    parsedCount: int
    parser: str
    parsed: list[dict[str, Any]]


def clean_hex(value: str) -> str:
    return "".join(ch for ch in value if ch in "0123456789abcdefABCDEF").upper()


def normalize_opcode(value: str) -> str | None:
    v = value.strip().lower().replace("0x", "")
    if v in {"041540", "1540", "1540"}:
        return "041540"
    if v in {"041542", "1542", "1542"}:
        return "041542"
    if v.endswith("1540"):
        return "041540"
    if v.endswith("1542"):
        return "041542"
    return None


def parse_log(text: str, default_opcode: str | None = None) -> list[Capture]:
    captures: list[Capture] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        event = parse_line_json(line) or parse_line_kv(line)
        if event is None and default_opcode and HEX_ONLY.match(line.strip()):
            event = {"opcode": default_opcode, "responseHex": line.strip()}
        if event is None:
            continue
        opcode = normalize_opcode(str(event.get("opcode") or event.get("op") or ""))
        if not opcode:
            continue
        response_hex = clean_hex(str(event.get("responseHex") or event.get("responsePayloadHex") or event.get("payloadHex") or event.get("bodyHex") or event.get("hex") or ""))
        if len(response_hex) < 12:
            continue
        parsed = parse_by_opcode(opcode, response_hex)
        captures.append(
            Capture(
                opcode=opcode,
                responseHex=response_hex,
                sourceLine=line_no,
                sha256=hashlib.sha256(response_hex.encode("ascii")).hexdigest(),
                parsedCount=len(parsed),
                parser="target-041540" if opcode == "041540" else "resource-041542",
                parsed=parsed,
            )
        )
    return captures


def parse_line_json(line: str) -> dict[str, Any] | None:
    m = JSON_OBJECT.search(line)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    if any(k in obj for k in ("responseHex", "responsePayloadHex", "payloadHex", "bodyHex", "hex")) and any(k in obj for k in ("opcode", "op")):
        return obj
    return None


def parse_line_kv(line: str) -> dict[str, str] | None:
    m = KV_EVENT.search(line)
    if not m:
        return None
    return {"opcode": m.group("opcode"), "responseHex": m.group("hex")}


def parse_by_opcode(opcode: str, response_hex: str) -> list[dict[str, Any]]:
    if opcode == "041540":
        return parse_targets(response_hex)
    if opcode == "041542":
        return parse_mines(response_hex)
    return []


def parse_targets(response_hex: str) -> list[dict[str, Any]]:
    candidates = [clean_hex(part) for part in re.split(r"[|\s]+", response_hex.replace("\\|", "|")) if len(clean_hex(part)) >= 20]
    out: list[dict[str, Any]] = []
    for record in candidates:
        parsed = parse_target_record(record)
        if parsed:
            out.append(parsed)
    out.extend(scan_concatenated_target_records(clean_hex(response_hex)))
    return dedupe_targets(out)


def scan_concatenated_target_records(normalized: str) -> list[dict[str, Any]]:
    """Recover adjacent 041540 records when captures have no pipe/space separator."""
    if len(normalized) < 20:
        return []
    out: list[dict[str, Any]] = []
    for marker_hex, _kind in TARGET_KIND_MARKERS:
        search_from = 0
        while True:
            marker_start = normalized.find(marker_hex, search_from)
            if marker_start < 0:
                break
            for prefix_len in (26, 24, 22, 20, 18):
                start = marker_start - prefix_len
                if start < 0:
                    continue
                candidate = normalized[start:marker_start + len(marker_hex)]
                parsed = parse_target_record(candidate)
                if parsed and parsed["id"] > 0 and 0 <= parsed["x"] <= 9999 and 0 <= parsed["y"] <= 9999:
                    out.append(parsed)
                    break
            search_from = marker_start + len(marker_hex)
    return out


def parse_target_record(record: str) -> dict[str, Any] | None:
    markers = [
        (record.find(hex_marker), hex_marker, kind)
        for hex_marker, kind in TARGET_KIND_MARKERS
        if record.find(hex_marker) >= 0
    ]
    marker = min(markers, key=lambda item: item[0]) if markers else None
    if not marker or len(record) < 26:
        return None
    marker_start, marker_hex, kind = marker
    if marker_start < 8:
        return None
    id_hex = record[:12]
    try:
        target_id = int(id_hex, 16)
    except ValueError:
        return None
    rank = rank_for_kind(kind) or int_or_none(record[12:14], 16) or 0
    x, y = parse_target_xy(record, marker_start)
    return {
        "id": target_id,
        "idHex": id_hex,
        "type": kind,
        "rank": rank,
        "x": x,
        "y": y,
        "kindHex": marker_hex,
        "rawRecord": record,
    }


def dedupe_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, Any, Any, Any]] = set()
    out: list[dict[str, Any]] = []
    for target in targets:
        key = (target.get("id"), target.get("type"), target.get("x"), target.get("y"))
        if key in seen:
            continue
        seen.add(key)
        out.append(target)
    return out


def rank_for_kind(kind: str) -> int | None:
    return {"渠帅": 11, "主将": 12, "主帅": 13}.get(kind)


def parse_target_xy(record: str, marker_start: int) -> tuple[int, int]:
    ranges = [(marker_start - 8, marker_start - 4), (marker_start - 4, marker_start), (18, 22), (22, 26), (12, 16), (16, 20)]
    for idx in range(0, len(ranges), 2):
        try:
            x = int(record[ranges[idx][0]:ranges[idx][1]], 16)
            y = int(record[ranges[idx + 1][0]:ranges[idx + 1][1]], 16)
        except Exception:
            continue
        if 0 <= x <= 9999 and 0 <= y <= 9999:
            return x, y
    return 0, 0


def parse_mines(response_hex: str) -> list[dict[str, Any]]:
    normalized = clean_hex(response_hex)
    matches = list(MINE_BASE_RECORD.finditer(normalized))
    out: list[dict[str, Any]] = []
    for idx, match in enumerate(matches):
        record = match.group(0)
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(normalized)
        tail = normalized[match.end():next_start]
        status_hex = tail[:4] if len(tail) >= 4 else ""
        detail = MINE_DETAIL.search(tail)
        kind_code = record[12:14].upper()
        out.append({
            "id": int(record[:12], 16),
            "idHex": record[:12],
            "kindCode": kind_code,
            "kind": MINE_KIND.get(kind_code, f"未知矿种{kind_code}"),
            "rank": int_or_none(record[14:16], 16) or 0,
            "x": int_or_none(record[16:20], 16) or 0,
            "y": int_or_none(record[20:24], 16) or 0,
            "isEmpty": status_hex.upper() == "0100" if status_hex else True,
            "statusHex": status_hex,
            "detail": detail.group(0) if detail else "",
            "rawRecord": record,
        })
    return out


def int_or_none(value: str, base: int = 10) -> int | None:
    try:
        return int(value, base)
    except Exception:
        return None


def channel_extra_candidate(captures: list[Capture]) -> dict[str, str]:
    extra: dict[str, str] = {
        "readOnlyCalibrationImporter": "tools/calibrate_readonly_responses.py",
        "readOnlyCalibrationNetworkSendAllowed": "false",
    }
    target_hex = next((c.responseHex for c in captures if c.opcode == "041540" and c.parsedCount > 0), None)
    mine_hex = next((c.responseHex for c in captures if c.opcode == "041542" and c.parsedCount > 0), None)
    if target_hex:
        extra["targetSearchResponseHex"] = target_hex
        extra["mapTargetsHex"] = target_hex
    if mine_hex:
        extra["resourcePointSearchResponseHex"] = mine_hex
        extra["mineTargetsHex"] = mine_hex
    return extra


def calibrate(text: str, default_opcode: str | None = None) -> dict[str, Any]:
    captures = parse_log(text, default_opcode=default_opcode)
    by_opcode: dict[str, list[Capture]] = {"041540": [], "041542": []}
    for capture in captures:
        by_opcode.setdefault(capture.opcode, []).append(capture)
    summary = {
        "captureCount": len(captures),
        "target041540CaptureCount": len(by_opcode.get("041540", [])),
        "resource041542CaptureCount": len(by_opcode.get("041542", [])),
        "targetParsedCount": sum(c.parsedCount for c in by_opcode.get("041540", [])),
        "mineParsedCount": sum(c.parsedCount for c in by_opcode.get("041542", [])),
        "networkSendAllowed": False,
        "blocker": "read-only response calibration only; no device/server request is sent by this tool",
    }
    return {
        "summary": summary,
        "channelExtraCandidate": channel_extra_candidate(captures),
        "captures": [asdict(c) for c in captures],
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 041540 / 041542 只读响应校准报告",
        "",
        "## Summary",
        "",
        f"- captureCount: {s['captureCount']}",
        f"- target041540CaptureCount: {s['target041540CaptureCount']}",
        f"- resource041542CaptureCount: {s['resource041542CaptureCount']}",
        f"- targetParsedCount: {s['targetParsedCount']}",
        f"- mineParsedCount: {s['mineParsedCount']}",
        f"- networkSendAllowed: {str(s['networkSendAllowed']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## ChannelExtra Candidate",
        "",
        "```json",
        json.dumps(report["channelExtraCandidate"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Captures",
        "",
    ]
    for capture in report["captures"]:
        lines += [
            f"### line {capture['sourceLine']} opcode {capture['opcode']}",
            "",
            f"- parser: {capture['parser']}",
            f"- parsedCount: {capture['parsedCount']}",
            f"- sha256: `{capture['sha256']}`",
            "",
            "```json",
            json.dumps(capture["parsed"], ensure_ascii=False, indent=2, sort_keys=True),
            "```",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="Log/text file containing 041540/041542 response hex captures")
    ap.add_argument("--out", help="Output calibration JSON; defaults to stdout")
    ap.add_argument("--markdown-out", help="Optional Markdown report path")
    ap.add_argument("--default-opcode", choices=["041540", "041542"], help="Treat bare hex lines as this opcode")
    ns = ap.parse_args()
    text = Path(ns.input).read_text(encoding="utf-8", errors="replace")
    report = calibrate(text, default_opcode=ns.default_opcode)
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
