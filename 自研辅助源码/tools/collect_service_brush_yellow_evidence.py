#!/usr/bin/env python3
"""Collect productized ForegroundService brush-yellow evidence from task logs."""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

PACKAGE = "com.example.dwpmclone"


def adb_run_as_cat(path: str, package: str = PACKAGE) -> str:
    return subprocess.check_output(["adb", "shell", "run-as", package, "cat", path], text=True, errors="ignore")


def parse_task_logs_xml(raw_xml: str) -> list[dict[str, Any]]:
    m = re.search(r'<string name="task_logs">(.*?)</string>', raw_xml, re.S)
    if not m:
        return []
    data = json.loads(html.unescape(m.group(1)))
    return data if isinstance(data, list) else []


def latest_service_run(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    start = 0
    for i, entry in enumerate(logs):
        if not isinstance(entry, dict):
            continue
        if entry.get("message") == "service created":
            start = i
    return logs[start:]


def collect(package: str = PACKAGE) -> dict[str, Any]:
    logs = parse_task_logs_xml(adb_run_as_cat("shared_prefs/dwpm_clone_task_logs.xml", package=package))
    run_logs = latest_service_run(logs)
    messages = [" ".join(str(x.get(k, "")) for k in ("tag", "message")) for x in run_logs if isinstance(x, dict)]
    joined = "\n".join(messages)
    markers = {
        "serviceStarted": "local scheduling started" in joined,
        "loadedRealPlan": "real-session-from-account-repo" in joined,
        "hasShuaHuangTask": "SHUA_HUANG" in joined or "brush-yellow" in joined,
        "selectedFormation": "selected formation=" in joined or "selectedFormations=" in joined,
        "realSenderPrepared": "真实刷黄二进制 sender 准备发送" in joined,
        "dispatchSuccess": "dispatch-success" in joined,
        "dispatchFailed": "dispatch-failed" in joined,
        "opcode8522OrBattleText": "0x8522" in joined or "消灭" in joined or "山贼" in joined,
        "terminalStopLogout": "terminal_decisions" in joined or "logout" in joined,
        "serviceStoppedAfterTerminal": "local scheduling stopped" in joined and "service destroyed" in joined,
    }
    return {
        "checkedAtMillis": int(time.time() * 1000),
        "package": package,
        "logCount": len(logs),
        "latestRunLogCount": len(run_logs),
        "markers": markers,
        "serviceBrushYellowEvidenceReady": (
            markers["serviceStarted"]
            and markers["loadedRealPlan"]
            and markers["hasShuaHuangTask"]
            and markers["selectedFormation"]
            and markers["realSenderPrepared"]
            and markers["dispatchSuccess"]
            and markers["terminalStopLogout"]
        ),
        "recentLogs": run_logs[-80:],
    }


def to_markdown(report: dict[str, Any]) -> str:
    return "\n".join([
        "# Service brush-yellow evidence",
        "",
        f"- checkedAtMillis: {report['checkedAtMillis']}",
        f"- package: {report['package']}",
        f"- logCount: {report['logCount']}",
        f"- latestRunLogCount: {report['latestRunLogCount']}",
        f"- serviceBrushYellowEvidenceReady: {str(report['serviceBrushYellowEvidenceReady']).lower()}",
        "",
        "## Markers",
        "",
        "```json",
        json.dumps(report["markers"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Recent logs",
        "",
        "```json",
        json.dumps(report["recentLogs"], ensure_ascii=False, indent=2)[-12000:],
        "```",
    ])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", default=PACKAGE)
    ap.add_argument("--out", default="reports/service_brush_yellow_evidence_current.json")
    ap.add_argument("--markdown-out", default="reports/service_brush_yellow_evidence_current.md")
    ns = ap.parse_args()
    report = collect(package=ns.package)
    Path(ns.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")
    print(json.dumps({
        "serviceBrushYellowEvidenceReady": report["serviceBrushYellowEvidenceReady"],
        "markers": report["markers"],
        "out": ns.out,
    }, ensure_ascii=False, indent=2))
    return 0 if report["serviceBrushYellowEvidenceReady"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
