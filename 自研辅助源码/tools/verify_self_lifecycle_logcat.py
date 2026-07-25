#!/usr/bin/env python3
"""Verify self-developed app lifecycle markers in logcat text.

Looks for [self-lifecycle-json] task_stop and session_logout records emitted by
SelfLifecycleLogFormatter. Offline-only; it reads copied logcat text.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

MARKER_RE = re.compile(r"\[self-lifecycle-json\]\s*(\{.*?\})(?=\n|$)", re.S)
EVENT_TEXT = {
    "task_stop": re.compile(r"\[self-lifecycle-json\].*\"event\"\s*:\s*\"task_stop\"|task_stop|停止任务", re.I | re.S),
    "session_logout": re.compile(r"\[self-lifecycle-json\].*\"event\"\s*:\s*\"session_logout\"|session_logout|退出登录|logout", re.I | re.S),
}


def parse_records(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for match in MARKER_RE.finditer(text):
        raw = match.group(1)
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data["_raw"] = raw
                records.append(data)
        except Exception:
            records.append({"event": "<invalid-json>", "_raw": raw})
    return records


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return bool(value)


def verify_text(text: str) -> dict[str, Any]:
    records = parse_records(text)
    by_event: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_event.setdefault(str(record.get("event") or ""), []).append(record)
    task_stop = by_event.get("task_stop", [])
    session_logout = by_event.get("session_logout", [])
    unsafe_records = [r for r in records if truthy(r.get("realActionNetworkAllowed"))]
    source_mode_one = [r for r in records if str(r.get("sourceMode", "")).strip() == "1"]
    text_counts = {name: len(pattern.findall(text)) for name, pattern in EVENT_TEXT.items()}
    ready = bool(task_stop and session_logout and not unsafe_records)
    missing: list[str] = []
    if not task_stop:
        missing.append("self-lifecycle-json:event=task_stop")
    if not session_logout:
        missing.append("self-lifecycle-json:event=session_logout")
    if unsafe_records:
        missing.append("unsafe:self lifecycle realActionNetworkAllowed=true")
    return {
        "summary": {
            "selfLifecycleLogcatReady": ready,
            "markerRecordCount": len(records),
            "taskStopCount": len(task_stop),
            "sessionLogoutCount": len(session_logout),
            "sourceModeOneCount": len(source_mode_one),
            "unsafeRecordCount": len(unsafe_records),
            "realActionNetworkAllowed": False,
            "blocker": "self lifecycle logcat smoke only; true brush-yellow regression still requires full device capture",
        },
        "missing": missing,
        "textPatternCounts": text_counts,
        "records": records,
        "nextActions": next_actions(missing),
    }


def next_actions(missing: list[str]) -> list[str]:
    actions: list[str] = []
    if any("task_stop" in item for item in missing):
        actions.append("在自研辅助中启动本地调度后执行停止任务，确认 logcat 出现 [self-lifecycle-json] event=task_stop。")
    if any("session_logout" in item for item in missing):
        actions.append("确保自研辅助存在可停止的账号/任务计划，然后停止任务并退出登录，确认 logcat 出现 [self-lifecycle-json] event=session_logout。")
    if any("unsafe" in item for item in missing):
        actions.append("检查自研 App lifecycle marker：realActionNetworkAllowed 必须保持 false。")
    if not actions:
        actions.append("self-lifecycle-json smoke 通过；继续运行完整设备协议采集管线。")
    return actions


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 自研 self-lifecycle logcat smoke 检查",
        "",
        "## Summary",
        "",
        f"- selfLifecycleLogcatReady: {str(s['selfLifecycleLogcatReady']).lower()}",
        f"- markerRecordCount: {s['markerRecordCount']}",
        f"- taskStopCount: {s['taskStopCount']}",
        f"- sessionLogoutCount: {s['sessionLogoutCount']}",
        f"- sourceModeOneCount: {s['sourceModeOneCount']}",
        f"- unsafeRecordCount: {s['unsafeRecordCount']}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## Missing",
        "",
        "```json",
        json.dumps(report["missing"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Next actions",
        "",
    ]
    lines.extend(f"- {item}" for item in report.get("nextActions", []))
    lines += [
        "",
        "## Text pattern counts",
        "",
        "```json",
        json.dumps(report.get("textPatternCounts", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Records",
        "",
        "```json",
        json.dumps(report.get("records", []), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="logcat.txt or device_combined.log")
    ap.add_argument("--out", help="Write JSON report; defaults to stdout")
    ap.add_argument("--markdown-out", help="Write Markdown report")
    ns = ap.parse_args()
    text = Path(ns.input).read_text(encoding="utf-8", errors="replace")
    report = verify_text(text)
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
