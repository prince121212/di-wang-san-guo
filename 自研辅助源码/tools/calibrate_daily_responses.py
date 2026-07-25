#!/usr/bin/env python3
"""Calibrate one-click daily response captures into dailyStepResultsJson.

Offline-only. It parses copied Frida/logcat/device text for recovered daily payloads or
explicit DailyStep names, normalizes success/failure text, and emits channelExtraCandidate
with dailyStepResultsJson consumable by SessionAwareGameProtocolClient.runDailyStep(...).
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
KV_FIELD = re.compile(r"\b(?P<key>dailyStep|step|gameHex|payload|payloadHex|responseText|responseHex|bodyText|bodyHex)\s*=\s*(?P<value>\"[^\"]*\"|'[^']*'|[^\s]+)", re.I)
DAILY_STEPS = {
    "SIGN_IN", "SURPRISE_BOX", "SALARY", "ARENA_REWARD", "COLLECT_TAX", "DONATE_TECH",
    "DONATE_COPPER", "DONATE_FOOD", "ADD_LOYALTY", "DELETE_MAIL", "ACHIEVEMENT_REWARD",
    "TASK_REWARD", "LEVEL_GIFT", "CONVERT_HALF_FOOD_TO_COPPER",
}
SUCCESS_LOGS = {
    "SIGN_IN": "已完成签到！",
    "SURPRISE_BOX": "已领取惊喜宝箱！",
    "ADD_LOYALTY": "已一键加忠！",
    "COLLECT_TAX": "已一键征收！",
    "ARENA_REWARD": "已领取竞技奖励！",
    "SALARY": "已领取俸禄！",
    "DELETE_MAIL": "已删除邮件！",
    "DONATE_COPPER": "已捐献铜钱！",
    "DONATE_FOOD": "已捐献粮食！",
    "DONATE_TECH": "已捐献科技！",
    "CONVERT_HALF_FOOD_TO_COPPER": "已转换一半粮食到铜钱！",
}
SUCCESS_MARKERS = list(SUCCESS_LOGS.values()) + ["成功", "完成", "领取", "已捐献", "success"]
FAILURE_MARKERS = ["error", "失败", "不足", "异常", "不能", "无法", "fail", "failed"]


@dataclass
class DailyCapture:
    step: str
    sourceLine: int
    responseText: str
    responseHex: str
    responseSha256: str
    success: bool | None
    message: str | None
    evidence: str
    payloadHex: str = ""


def clean(value: Any) -> str:
    return str(value).strip().strip('"\'')


def clean_hex(value: str) -> str:
    return "".join(ch for ch in value if ch in "0123456789abcdefABCDEF").lower()


def decode_hex_text(value: str) -> str:
    hex_value = clean_hex(value)
    if len(hex_value) < 2 or len(hex_value) % 2 != 0:
        return ""
    try:
        return bytes.fromhex(hex_value).decode("utf-8", errors="replace").strip("\x00 \r\n\t")
    except Exception:
        return ""


def normalize_step(value: Any = "", payload: Any = "") -> str | None:
    step = str(value or "").strip().upper()
    if step in DAILY_STEPS:
        return step
    payload_hex = clean_hex(str(payload or ""))
    if not payload_hex:
        return None
    if any(token in payload_hex for token in ("006200", "006202", "01620603", "01620607", "0162060e", "0162061c")):
        return "SIGN_IN"
    if "091134" in payload_hex:
        return "SURPRISE_BOX"
    if "0c121f" in payload_hex:
        return "ADD_LOYALTY"
    if "041330" in payload_hex:
        return "COLLECT_TAX"
    if "006266" in payload_hex:
        return "ARENA_REWARD"
    if "01314b" in payload_hex:
        return "SALARY"
    if "0a1116" in payload_hex:
        return "DELETE_MAIL"
    if "05140a" in payload_hex:
        return "DONATE_TECH"
    if "18140c" in payload_hex:
        tail = payload_hex.split("18140c", 1)[1]
        # donate food has a zero block before the amount; donate copper starts with amount.
        return "DONATE_FOOD" if tail.startswith("0000000000000000") else "DONATE_COPPER"
    return None


def explicit_success(text: str) -> bool | None:
    for pattern in (r"[\"']success[\"']\s*:\s*(true|false|1|0)", r"success\s*=\s*(true|false|1|0)"):
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).lower() in {"true", "1"}
    return None


def parse_response(step: str, response_text: str = "", response_hex: str = "") -> dict[str, Any]:
    text = response_text.strip() or decode_hex_text(response_hex)
    normalized = text.lower()
    explicit = explicit_success(text)
    marker_failure = next((m for m in FAILURE_MARKERS if m.lower() in normalized or m in text), None)
    step_success_log = SUCCESS_LOGS.get(step)
    marker_success = step_success_log if step_success_log and step_success_log in text else next((m for m in SUCCESS_MARKERS if m.lower() in normalized or m in text), None)
    failure = marker_failure or ("success=false" if explicit is False else None)
    success = None if failure else (marker_success or ("success=true" if explicit is True else None))
    result = False if failure else True if success else None
    message = extract_message(text) or (step_success_log if result is True and step_success_log else f"daily step failed: {step}" if result is False else text[:120] if text else None)
    evidence = f"failure-marker:{failure}" if failure else f"success-marker:{success}" if success else "no-known-marker"
    return {
        "success": result,
        "message": message,
        "evidence": ("hex->" + evidence) if not response_text.strip() and response_hex.strip() and text else evidence,
        "rawText": text,
    }


def extract_message(text: str) -> str | None:
    for pattern in (r"[\"'](?:message|msg|error)[\"']\s*:\s*[\"']([^\"']+)[\"']", r"(?:message|msg|error)\s*=\s*([^&|;\r\n]+)"):
        m = re.search(pattern, text, re.I)
        if m and m.group(1).strip():
            return m.group(1).strip()
    for line in (ln.strip() for ln in text.splitlines()):
        if any(token in line for token in ("已", "成功", "失败", "日常", "捐献", "领取")) or "error" in line.lower():
            return line
    return None


def parse_log(text: str) -> list[DailyCapture]:
    captures: list[DailyCapture] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        obj = parse_json_line(line) or parse_kv_line(line)
        if not obj:
            continue
        payload = obj.get("payload") or obj.get("payloadHex") or obj.get("gameHex") or ""
        step = normalize_step(obj.get("dailyStep") or obj.get("step"), payload)
        if not step:
            continue
        response_text = clean(obj.get("responseText") or obj.get("bodyText") or obj.get("response") or "")
        response_hex = clean_hex(str(obj.get("responseHex") or obj.get("bodyHex") or obj.get("responsePayloadHex") or ""))
        if not response_text and not response_hex:
            continue
        parsed = parse_response(step, response_text, response_hex)
        raw_for_hash = response_text or response_hex
        captures.append(DailyCapture(
            step=step,
            sourceLine=line_no,
            responseText=response_text or parsed["rawText"],
            responseHex=response_hex,
            responseSha256=hashlib.sha256(raw_for_hash.encode("utf-8", errors="replace")).hexdigest(),
            success=parsed["success"],
            message=parsed["message"],
            evidence=parsed["evidence"],
            payloadHex=clean_hex(str(payload)),
        ))
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
        out[m.group("key")] = clean(m.group("value"))
    return out or None


def daily_results(captures: list[DailyCapture]) -> list[dict[str, Any]]:
    # Keep the last capture for each step: multi-request steps such as SIGN_IN can produce
    # several low-level responses but dailyStepResultsJson is step-level metadata.
    by_step: dict[str, DailyCapture] = {}
    for cap in captures:
        by_step[cap.step] = cap
    out = []
    for step, cap in by_step.items():
        out.append({
            "step": step,
            "success": cap.success if cap.success is not None else False,
            "message": cap.message or "",
            "responseText": cap.responseText,
            "responseHex": cap.responseHex,
            "raw": {
                "source": "tools/calibrate_daily_responses.py",
                "payloadHex": cap.payloadHex,
                "evidence": cap.evidence,
                "responseSha256": cap.responseSha256,
            },
        })
    return out


def calibrate(text: str) -> dict[str, Any]:
    captures = parse_log(text)
    results = daily_results(captures)
    summary = {
        "captureCount": len(captures),
        "dailyStepResultCount": len(results),
        "successCount": sum(1 for c in captures if c.success is True),
        "failureCount": sum(1 for c in captures if c.success is False),
        "unknownCount": sum(1 for c in captures if c.success is None),
        "networkSendAllowed": False,
        "blocker": "daily response calibration only; true state-changing network send remains disabled",
    }
    extra = {
        "dailyResponseCalibrationImporter": "tools/calibrate_daily_responses.py",
        "dailyResponseCalibrationNetworkSendAllowed": "false",
    }
    if results:
        extra["dailyStepResultsJson"] = json.dumps(results, ensure_ascii=False, separators=(",", ":"))
    return {
        "summary": summary,
        "channelExtraCandidate": extra,
        "captures": [asdict(c) for c in captures],
        "dailyStepResults": results,
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# Daily Response 校准报告",
        "",
        "## Summary",
        "",
        f"- captureCount: {s['captureCount']}",
        f"- dailyStepResultCount: {s['dailyStepResultCount']}",
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
        "## Daily Step Results",
        "",
        "```json",
        json.dumps(report["dailyStepResults"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Captures",
        "",
    ]
    for cap in report["captures"]:
        lines += [
            f"### line {cap['sourceLine']} {cap['step']}",
            "",
            f"- success: {cap['success']}",
            f"- evidence: {cap['evidence']}",
            f"- responseSha256: `{cap['responseSha256']}`",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="Log/text containing daily response captures")
    ap.add_argument("--out", help="Output calibration JSON; defaults to stdout")
    ap.add_argument("--markdown-out", help="Optional Markdown report path")
    ns = ap.parse_args()
    text = Path(ns.input).read_text(encoding="utf-8", errors="replace")
    report = calibrate(text)
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
