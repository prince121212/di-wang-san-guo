#!/usr/bin/env python3
"""Gate-controlled live brush-yellow regression runner.

This is an orchestrator, not a bypass.  It always refreshes the read-only
0x1016 freshness evidence, rebuilds the brush-yellow prerequisite report, and
refuses to send any real action unless that report says
``readyForRealBrushYellow=true``.  A second explicit CLI confirmation is also
required for action send.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], allow_fail: bool = False) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if cp.returncode != 0 and not allow_fail:
        raise RuntimeError(f"command failed rc={cp.returncode}: {' '.join(cmd)}\n{cp.stdout}\n{cp.stderr}")
    return cp


def load_json(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def build_decision(prereq: dict[str, Any], do_action: bool, confirm: str | None) -> dict[str, Any]:
    ready = bool(prereq.get("readyForRealBrushYellow"))
    stage = str(prereq.get("readinessStage") or "UNKNOWN")
    blockers = list(prereq.get("blockers") or [])
    if not ready:
        return {
            "canSend": False,
            "willSend": False,
            "code": "PREREQ_NOT_READY",
            "message": f"刷黄前置未满足：stage={stage} blockers={blockers}",
        }
    if not do_action:
        return {
            "canSend": True,
            "willSend": False,
            "code": "READY_DRY_RUN",
            "message": "前置已满足；未传 --do-action，因此只生成准备就绪证据。",
        }
    if confirm != "brush-yellow":
        return {
            "canSend": True,
            "willSend": False,
            "code": "ACTION_CONFIRMATION_MISSING",
            "message": "真实动作需要同时传 --do-action --confirm brush-yellow。",
        }
    return {
        "canSend": True,
        "willSend": True,
        "code": "WILL_SEND_BRUSH_YELLOW",
        "message": "前置/gate/session 均满足，按显式确认执行一次真实刷黄回归。",
    }


def to_markdown(report: dict[str, Any]) -> str:
    decision = report["decision"]
    prereq = report["prereq"]
    lines = [
        "# Live brush-yellow regression runner",
        "",
        f"- checkedAtMillis: {report['checkedAtMillis']}",
        f"- package: {report['package']}",
        f"- decisionCode: {decision['code']}",
        f"- canSend: {str(decision['canSend']).lower()}",
        f"- willSend: {str(decision['willSend']).lower()}",
        f"- message: {decision['message']}",
        f"- readinessStage: {prereq.get('readinessStage')}",
        f"- readyForRealBrushYellow: {str(prereq.get('readyForRealBrushYellow')).lower()}",
        f"- blockers: {', '.join(prereq.get('blockers') or []) if prereq.get('blockers') else 'none'}",
        f"- liveSessionFresh: {str(prereq.get('liveSessionFresh')).lower()}",
        f"- formationCount: {prereq.get('formationCount')}",
        f"- generalCandidateCount: {prereq.get('generalCandidateCount')}",
        "",
        "## Evidence files",
        "",
        f"- live1016: `{report['liveReport']}`",
        f"- prereq: `{report['prereqReport']}`",
    ]
    if report.get("actionReport"):
        lines.append(f"- action: `{report['actionReport']}`")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", default="com.example.dwpmclone")
    ap.add_argument("--do-action", action="store_true")
    ap.add_argument("--confirm", default=None, help="must be 'brush-yellow' with --do-action")
    ap.add_argument("--target-kind", default="黄巾")
    ap.add_argument("--target-index", type=int, default=0)
    ap.add_argument("--general-index", type=int, default=0)
    ap.add_argument("--scan-limit", type=int, default=80)
    ap.add_argument("--out", default="reports/live_brush_yellow_regression_current.json")
    ap.add_argument("--markdown-out", default="reports/live_brush_yellow_regression_current.md")
    ns = ap.parse_args()

    live_json = "reports/live_1016_session_freshness_current.json"
    prereq_json = "reports/brush_yellow_live_prereq_current.json"
    run([sys.executable, "tools/check_live_1016_session.py", "--package", ns.package], allow_fail=True)
    run([sys.executable, "tools/check_brush_yellow_prereq.py", "--package", ns.package], allow_fail=True)
    prereq = load_json(ROOT / prereq_json)
    decision = build_decision(prereq, ns.do_action, ns.confirm)
    action_report = None
    action_cp_summary = None
    if decision["willSend"]:
        action_report = f"reports/live_brush_yellow_action_{int(time.time())}.json"
        cp = run([
            sys.executable,
            "tools/direct_binary_action_probe.py",
            "--do-action",
            "--target-kind",
            ns.target_kind,
            "--target-index",
            str(ns.target_index),
            "--general-index",
            str(ns.general_index),
            "--scan-limit",
            str(ns.scan_limit),
            "--out",
            action_report,
        ])
        action_cp_summary = {"returncode": cp.returncode, "stdoutTail": cp.stdout[-4000:], "stderrTail": cp.stderr[-4000:]}

    report = {
        "checkedAtMillis": int(time.time() * 1000),
        "package": ns.package,
        "liveReport": live_json,
        "prereqReport": prereq_json,
        "actionReport": action_report,
        "decision": decision,
        "prereq": {
            "readinessStage": prereq.get("readinessStage"),
            "readyForRealBrushYellow": prereq.get("readyForRealBrushYellow"),
            "blockers": prereq.get("blockers"),
            "liveSessionFresh": prereq.get("liveSessionFresh"),
            "configReadyExceptSession": prereq.get("configReadyExceptSession"),
            "formationCount": prereq.get("formationCount"),
            "generalCandidateCount": prereq.get("generalCandidateCount"),
            "gates": prereq.get("gates"),
        },
        "actionCommandSummary": action_cp_summary,
    }
    Path(ns.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")
    print(json.dumps({
        "decisionCode": decision["code"],
        "canSend": decision["canSend"],
        "willSend": decision["willSend"],
        "readinessStage": prereq.get("readinessStage"),
        "blockers": prereq.get("blockers"),
        "out": ns.out,
        "markdownOut": ns.markdown_out,
        "actionReport": action_report,
    }, ensure_ascii=False, indent=2))
    if decision["willSend"]:
        return 0
    if decision["code"] == "READY_DRY_RUN":
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
