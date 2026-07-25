#!/usr/bin/env python3
"""Calibrate captured state-changing action responses for recovered gameHex actions.

Offline-only. This tool parses copied Frida/logcat/device text containing responses for
known action opcodes and emits a calibration report plus channelExtraCandidate. For the
刷黄 action pair it can generate dispatchResultsJson entries consumable by
SessionAwareGameProtocolClient.dispatchFormation(...).

Accepted examples:
  [action-response-json] {"opcode":"1522030","formationId":3,"targetId":"101","responseText":"刷黄出征成功！继续搜索... usedAount=1"}
  {"gameHex":"000...1522030...","responseHex":"E588B7E9BB84E587BAE5BE81E68890E58A9F"}

No network request is sent and real action send remains disabled.
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
KNOWN_ACTION_OPCODES = {
    "1520030": "brush-yellow-prepare",
    "1522030": "brush-yellow-expedition",
    "1520010": "resource-point-prepare",
    "1522010": "resource-point-expedition",
}
SUCCESS_MARKERS = ["刷黄出征成功", "出征成功", "继续搜索", "成功！继续搜索", "success"]
FAILURE_MARKERS = ["error", "失败", "不足", "不能出征", "无法出征", "不可出征", "已出征", "正在行军", "体力", "君主将", "没有找到", "异常", "fail", "failed"]
USED_PATTERNS = [
    re.compile(r"usedAount\s*[:=]\s*[\"']?(\d+)", re.I),
    re.compile(r"usedAmount\s*[:=]\s*[\"']?(\d+)", re.I),
    re.compile(r"usedCount\s*[:=]\s*[\"']?(\d+)", re.I),
    re.compile(r"已刷\s*(\d+)\s*次"),
    re.compile(r"第\s*(\d+)\s*次"),
]
KV_FIELD = re.compile(r"\b(?P<key>opcode|gameHex|formationId|targetId|targetIdHex|responseText|responseHex|bodyText|bodyHex|generalIdHexChunks)\s*=\s*(?P<value>\[[^\]]*\]|\"[^\"]*\"|'[^']*'|[^\s]+)", re.I)


@dataclass
class ActionCapture:
    opcode: str
    action: str
    sourceLine: int
    responseText: str
    responseHex: str
    responseSha256: str
    success: bool | None
    message: str | None
    usedAount: int | None
    consumedTimes: int
    evidence: str
    formationId: int | None = None
    targetId: str | None = None
    targetIdHex: str | None = None
    generalIdHexChunks: list[str] | None = None


def clean(value: Any) -> str:
    return str(value).strip().strip('"\'')


def clean_hex(value: str) -> str:
    return "".join(ch for ch in value if ch in "0123456789abcdefABCDEF").upper()


def normalize_opcode(value: Any = "", game_hex: Any = "") -> str | None:
    text = f"{value or ''} {game_hex or ''}".lower().replace("0x", "")
    for opcode in KNOWN_ACTION_OPCODES:
        if opcode.lower() in text:
            return opcode
    return None


def decode_hex_text(value: str) -> str:
    hex_value = clean_hex(value)
    if len(hex_value) < 2 or len(hex_value) % 2 != 0:
        return ""
    try:
        return bytes.fromhex(hex_value).decode("utf-8", errors="replace").strip("\x00 \r\n\t")
    except Exception:
        return ""


def explicit_success(text: str) -> bool | None:
    for pattern in (r"[\"']success[\"']\s*:\s*(true|false|1|0)", r"success\s*=\s*(true|false|1|0)"):
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).lower() in {"true", "1"}
    return None


def extract_message(text: str) -> str | None:
    for pattern in (r"[\"'](?:message|msg|error)[\"']\s*:\s*[\"']([^\"']+)[\"']", r"(?:message|msg|error)\s*=\s*([^&|;\r\n]+)"):
        m = re.search(pattern, text, re.I)
        if m and m.group(1).strip():
            return m.group(1).strip()
    for line in (ln.strip() for ln in text.splitlines()):
        if any(marker in line for marker in ("刷黄", "出征", "失败")) or "error" in line.lower():
            return line
    return text[:120] if text else None


def parse_response(response_text: str = "", response_hex: str = "") -> dict[str, Any]:
    text = response_text.strip() or decode_hex_text(response_hex)
    normalized = text.lower()
    explicit = explicit_success(text)
    marker_failure = next((m for m in FAILURE_MARKERS if m.lower() in normalized or m in text), None)
    marker_success = next((m for m in SUCCESS_MARKERS if m.lower() in normalized or m in text), None)
    failure = marker_failure or ("success=false" if explicit is False else None)
    success = None if failure else (marker_success or ("success=true" if explicit is True else None))
    result = False if failure else True if success else None
    used = None
    for pattern in USED_PATTERNS:
        m = pattern.search(text)
        if m:
            used = int(m.group(1))
            break
    evidence = f"failure-marker:{failure}" if failure else f"success-marker:{success}" if success else "usedAount-marker" if used is not None else "no-known-marker"
    return {
        "success": result,
        "message": extract_message(text),
        "usedAount": used,
        "consumedTimes": used if used is not None else 1 if result is True else 0,
        "evidence": ("hex->" + evidence) if not response_text.strip() and response_hex.strip() and text else evidence,
        "rawText": text,
    }


def parse_log(text: str) -> list[ActionCapture]:
    captures: list[ActionCapture] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        obj = parse_json_line(line) or parse_kv_line(line)
        if not obj:
            continue
        opcode = normalize_opcode(obj.get("opcode"), obj.get("gameHex"))
        if not opcode:
            continue
        response_text = clean(obj.get("responseText") or obj.get("bodyText") or obj.get("response") or "")
        response_hex = clean_hex(str(obj.get("responseHex") or obj.get("bodyHex") or obj.get("responsePayloadHex") or ""))
        if not response_text and not response_hex:
            continue
        parsed = parse_response(response_text, response_hex)
        raw_for_hash = response_text or response_hex
        cap = ActionCapture(
            opcode=opcode,
            action=KNOWN_ACTION_OPCODES[opcode],
            sourceLine=line_no,
            responseText=response_text or parsed["rawText"],
            responseHex=response_hex,
            responseSha256=hashlib.sha256(raw_for_hash.encode("utf-8", errors="replace")).hexdigest(),
            success=parsed["success"],
            message=parsed["message"],
            usedAount=parsed["usedAount"],
            consumedTimes=parsed["consumedTimes"],
            evidence=parsed["evidence"],
            formationId=parse_int(obj.get("formationId")),
            targetId=clean(obj.get("targetId")) if obj.get("targetId") is not None else None,
            targetIdHex=clean(obj.get("targetIdHex")) if obj.get("targetIdHex") is not None else None,
            generalIdHexChunks=parse_chunks(obj.get("generalIdHexChunks")),
        )
        captures.append(enrich_capture_from_game_hex(cap, obj))
    return captures


def parse_json_line(line: str) -> dict[str, Any] | None:
    m = JSON_OBJECT.search(line)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def parse_kv_line(line: str) -> dict[str, Any] | None:
    out: dict[str, Any] = {}
    for m in KV_FIELD.finditer(line):
        key = m.group("key")
        value = clean(m.group("value"))
        if key.lower() == "generalidhexchunks":
            out[key] = parse_chunks(value)
        else:
            out[key] = value
    return out or None


def parse_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value), 10)
    except Exception:
        return None


def parse_chunks(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [clean(v) for v in value if clean(v)]
    text = clean(value)
    if not text:
        return None
    text = text.strip("[]")
    chunks = [clean(part) for part in re.split(r"[,;|\s]+", text) if clean(part)]
    return chunks or None


def parse_target_id_from_hex(value: Any) -> str | None:
    text = clean_hex(str(value or ""))
    if not text:
        return None
    try:
        return str(int(text, 16))
    except Exception:
        return None


def parse_brush_yellow_dispatch_game_hex(game_hex: Any) -> dict[str, Any]:
    """Extract conservative 1522030 fields from recovered dispatch payload hex."""
    gh = clean_hex(str(game_hex or ""))
    idx = gh.find("1522030")
    if idx < 0:
        return {}
    after = gh[idx + len("1522030"):]
    if not after:
        return {}
    try:
        # Captures commonly encode count as one byte (01), while some recovered
        # summaries describe it as a decimal digit. Prefer the byte form when it
        # looks like 00..09; otherwise fall back to a single decimal char.
        count = int(after[:2], 16) if len(after) >= 2 and int(after[:2], 16) <= 9 else int(after[0], 10)
        count_width = 2 if len(after) >= 2 and int(after[:2], 16) <= 9 else 1
    except Exception:
        count = 0
        count_width = 1
    general_chunks: list[str] = []
    cursor = count_width
    for _ in range(max(0, count)):
        chunk = after[cursor:cursor + 16]
        if len(chunk) == 16:
            general_chunks.append(chunk)
        cursor += 16
    if after[cursor:cursor + 4] == "0000":
        cursor += 4
    target_hex = after[cursor:cursor + 16]
    out: dict[str, Any] = {}
    if general_chunks:
        out["generalIdHexChunks"] = general_chunks
    if len(target_hex) == 16:
        out["targetIdHex"] = target_hex
        target_id = parse_target_id_from_hex(target_hex)
        if target_id:
            out["targetId"] = target_id
    return out


def normalize_extra(extra: dict[str, Any] | None) -> dict[str, str]:
    if not extra:
        return {}
    out: dict[str, str] = {}
    for key, value in extra.items():
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            out[str(key)] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            text = str(value)
            if text != "":
                out[str(key)] = text
    return out


def load_base_extra(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    if isinstance(data.get("baseChannelExtra"), dict):
        data = data["baseChannelExtra"]
    elif isinstance(data.get("channelExtra"), dict):
        data = data["channelExtra"]
    elif isinstance(data.get("session"), dict) and isinstance(data["session"].get("channelExtra"), dict):
        data = data["session"]["channelExtra"]
    return normalize_extra(data)


def parse_json_value(raw: str) -> Any | None:
    try:
        return json.loads(raw)
    except Exception:
        return None


def parse_formation_id_value(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    text = clean(str(value))
    parsed = parse_int(text)
    if parsed is not None:
        return parsed
    hx = clean_hex(text)
    if hx:
        try:
            return int(hx, 16)
        except Exception:
            return None
    return None


def normalize_chunk(value: Any) -> str:
    return clean_hex(str(value or "")).lstrip("0") or ("0" if str(value or "").strip() else "")


def extract_formation_candidates(extra: dict[str, str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for key in ("formationsJson", "formationJson"):
        value = parse_json_value(extra.get(key, ""))
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue
                fid = parse_formation_id_value(item.get("formationId") or item.get("id") or item.get("formationNo") or item.get("bianduihao"))
                generals = item.get("generalIdHexChunks") or item.get("generalHexChunks") or item.get("generalIds") or item.get("generals")
                chunks = parse_chunks(generals) or []
                if fid is not None:
                    candidates.append({"formationId": fid, "generalIdHexChunks": chunks, "source": key})
    for key in ("xiaohuangPrefsJson", "sharedPrefsJson", "guajiPrefsJson", "recoveredPrefsJson"):
        value = parse_json_value(extra.get(key, ""))
        if not isinstance(value, dict):
            continue
        suffixes = set()
        for pref_key in value.keys():
            m = re.match(r"(?:shuahuangChuzhengBiandui|bianduihao|bianduiDejiangling)(\d+)$", str(pref_key), re.I)
            if m:
                suffixes.add(m.group(1))
        for suffix in sorted(suffixes, key=lambda x: int(x) if x.isdigit() else 999999):
            enabled = str(value.get(f"shuahuangChuzhengBiandui{suffix}", "true")).strip().lower() in {"true", "1", "yes", "on"}
            if not enabled:
                continue
            fid = parse_formation_id_value(value.get(f"bianduihao{suffix}"))
            chunks = parse_chunks(value.get(f"bianduiDejiangling{suffix}")) or []
            if fid is not None:
                candidates.append({"formationId": fid, "generalIdHexChunks": chunks, "source": f"{key}:{suffix}"})
    return candidates


def infer_formation_id(cap: ActionCapture, base_extra: dict[str, str]) -> int | None:
    if cap.formationId is not None:
        return cap.formationId
    candidates = extract_formation_candidates(base_extra)
    if not candidates:
        return None
    cap_chunks = {normalize_chunk(chunk) for chunk in (cap.generalIdHexChunks or []) if normalize_chunk(chunk)}
    if cap_chunks:
        matched = []
        for candidate in candidates:
            cand_chunks = {normalize_chunk(chunk) for chunk in (candidate.get("generalIdHexChunks") or []) if normalize_chunk(chunk)}
            if cand_chunks and cap_chunks.issubset(cand_chunks):
                matched.append(candidate)
        if len(matched) == 1:
            return int(matched[0]["formationId"])
    unique_ids = []
    for candidate in candidates:
        fid = int(candidate["formationId"])
        if fid not in unique_ids:
            unique_ids.append(fid)
    return unique_ids[0] if len(unique_ids) == 1 else None


def enrich_capture_from_game_hex(cap: ActionCapture, obj: dict[str, Any]) -> ActionCapture:
    if cap.opcode != "1522030":
        return cap
    fields = parse_brush_yellow_dispatch_game_hex(obj.get("gameHex"))
    if cap.targetIdHex is None and fields.get("targetIdHex"):
        cap.targetIdHex = str(fields["targetIdHex"])
    if cap.targetId is None and fields.get("targetId"):
        cap.targetId = str(fields["targetId"])
    if not cap.generalIdHexChunks and fields.get("generalIdHexChunks"):
        cap.generalIdHexChunks = list(fields["generalIdHexChunks"])
    if cap.targetId is None and cap.targetIdHex:
        cap.targetId = parse_target_id_from_hex(cap.targetIdHex)
    return cap


def dispatch_results(captures: list[ActionCapture], base_extra: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    normalized_base = normalize_extra(base_extra)
    for cap in captures:
        formation_id = infer_formation_id(cap, normalized_base)
        target_id = cap.targetId or parse_target_id_from_hex(cap.targetIdHex)
        if cap.opcode != "1522030" or formation_id is None or not target_id:
            continue
        item: dict[str, Any] = {
            "formationId": formation_id,
            "targetId": target_id,
            "success": cap.success if cap.success is not None else False,
            "consumedTimes": cap.consumedTimes,
            "message": cap.message or "",
            "responseText": cap.responseText,
            "responseHex": cap.responseHex,
            "raw": {
                "source": "tools/calibrate_action_responses.py",
                "opcode": cap.opcode,
                "action": cap.action,
                "evidence": cap.evidence,
                "responseSha256": cap.responseSha256,
                "formationIdInferred": cap.formationId is None,
            },
        }
        if cap.targetIdHex:
            item["targetIdHex"] = cap.targetIdHex
        if cap.generalIdHexChunks:
            item["generalIdHexChunks"] = cap.generalIdHexChunks
        out.append(item)
    return out


def calibrate(text: str, base_extra: dict[str, Any] | None = None) -> dict[str, Any]:
    captures = parse_log(text)
    dispatch = dispatch_results(captures, base_extra=base_extra)
    summary = {
        "captureCount": len(captures),
        "brushYellowPrepareCount": sum(1 for c in captures if c.opcode == "1520030"),
        "brushYellowExpeditionCount": sum(1 for c in captures if c.opcode == "1522030"),
        "dispatchResultCount": len(dispatch),
        "dispatchResultInferredFormationCount": sum(1 for item in dispatch if item.get("raw", {}).get("formationIdInferred")),
        "successCount": sum(1 for c in captures if c.success is True),
        "failureCount": sum(1 for c in captures if c.success is False),
        "unknownCount": sum(1 for c in captures if c.success is None),
        "networkSendAllowed": False,
        "blocker": "action response calibration only; true state-changing network send remains disabled",
    }
    extra = {
        "actionResponseCalibrationImporter": "tools/calibrate_action_responses.py",
        "actionResponseCalibrationNetworkSendAllowed": "false",
    }
    if dispatch:
        extra["dispatchResultsJson"] = json.dumps(dispatch, ensure_ascii=False, separators=(",", ":"))
    return {
        "summary": summary,
        "channelExtraCandidate": extra,
        "captures": [asdict(c) for c in captures],
        "dispatchResults": dispatch,
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# Action Response 校准报告",
        "",
        "## Summary",
        "",
        f"- captureCount: {s['captureCount']}",
        f"- brushYellowPrepareCount: {s['brushYellowPrepareCount']}",
        f"- brushYellowExpeditionCount: {s['brushYellowExpeditionCount']}",
        f"- dispatchResultCount: {s['dispatchResultCount']}",
        f"- dispatchResultInferredFormationCount: {s.get('dispatchResultInferredFormationCount', 0)}",
        f"- successCount: {s['successCount']}",
        f"- failureCount: {s['failureCount']}",
        f"- unknownCount: {s['unknownCount']}",
        f"- networkSendAllowed: {str(s['networkSendAllowed']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## ChannelExtra Candidate",
        "",
        "```json",
        json.dumps(report["channelExtraCandidate"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Dispatch Results",
        "",
        "```json",
        json.dumps(report["dispatchResults"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Captures",
        "",
    ]
    for cap in report["captures"]:
        lines += [
            f"### line {cap['sourceLine']} {cap['opcode']} {cap['action']}",
            "",
            f"- success: {cap['success']}",
            f"- consumedTimes: {cap['consumedTimes']}",
            f"- evidence: {cap['evidence']}",
            f"- responseSha256: `{cap['responseSha256']}`",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="Log/text containing action response captures")
    ap.add_argument("--base-channel-extra", "--base", dest="base_channel_extra", help="Optional base channelExtra/session/account JSON used to infer formationId from 1522030 gameHex")
    ap.add_argument("--out", help="Output calibration JSON; defaults to stdout")
    ap.add_argument("--markdown-out", help="Optional Markdown report path")
    ns = ap.parse_args()
    text = Path(ns.input).read_text(encoding="utf-8", errors="replace")
    base_extra = load_base_extra(Path(ns.base_channel_extra)) if ns.base_channel_extra else None
    report = calibrate(text, base_extra=base_extra)
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
