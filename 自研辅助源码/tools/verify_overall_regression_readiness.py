#!/usr/bin/env python3
"""Unified readiness audit for the migration/device regression goal.

This is an offline dashboard. It consolidates current preflight, full offline replay,
action gate, safety invariants, migration status and APK artifact evidence. It never
contacts a device/server and it must not mark true device regression ready unless live
preflight/device evidence and dry-run action evidence are both present.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    if isinstance(value, (int, float)):
        return value != 0
    return False


def summary(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("summary", {})
    return value if isinstance(value, dict) else {}


def nested(data: dict[str, Any], *parts: str) -> Any:
    cur: Any = data
    for part in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def file_info(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists(), "size": path.stat().st_size if path.exists() else 0}


def audit(root: Path) -> dict[str, Any]:
    root = root.resolve()
    reports = root / "reports"
    preflight = load_json(reports / "device_regression_preflight.json")
    full = load_json(reports / "full_offline_replay_report.json")
    remaining_action = load_json(reports / "remaining_action_dryrun_payload_gate_evidence.json")
    safety = load_json(reports / "action_safety_invariants.json")
    migration = load_json(reports / "migration_goal_status.json")
    artifact_check = load_json(reports / "latest_device_regression_artifact_check.json")
    if not artifact_check:
        artifact_check = load_json(reports / "regression_artifact_check.json")
    shuahuang_minimum = load_json(reports / "device_shuahuang_minimum_goal_check.json")
    if not shuahuang_minimum:
        shuahuang_minimum = load_json(reports / "latest_device_shuahuang_minimum_goal_check.json")

    p = summary(preflight)
    f = summary(full)
    r = summary(remaining_action)
    s = summary(safety)
    m = summary(migration)
    action_gate = summary(nested(full, "actionGateAudit") or {})
    artifact_summary = summary(artifact_check)
    shuahuang_minimum_summary = summary(shuahuang_minimum)

    apk_debug = root / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
    xiaohuang_apk = root.parent / "小黄点辅助.apk"
    game_apk = root.parent / "三国·帝王联盟1.66.apk"
    frida_script = root.parent / "reverse_cases" / "apk" / "scripts" / "frida_native_session_trace_v2.js"

    preflight_ready = truthy(p.get("preflightReady"))
    authorized_devices = int(p.get("authorizedDeviceCount") or 0)
    full_ready = truthy(f.get("fullOfflineReplayReady"))
    shua_ready = truthy(f.get("shuaHuangOfflineClosedLoopReplayReady"))
    role_resource_parse_ready = truthy(f.get("roleResourceParseReady"))
    general_evidence_parse_ready = truthy(f.get("generalEvidenceParseReady"))
    daily_ready = truthy(f.get("dailyOfflineClosedLoopReplayReady"))
    daily_protocol_ready = truthy(f.get("dailyProtocolEvidenceReady"))
    daily_full_order_ready = truthy(f.get("dailyFullRecoveredOrderReady"))
    mine_ready = truthy(f.get("mineOfflineClosedLoopReplayReady"))
    mine_readonly_ready = truthy(f.get("mineReadOnlyEvidenceReady"))
    mine_selection_ready = truthy(f.get("mineSelectionEvidenceReady"))
    remaining_action_ready = (
        truthy(f.get("remainingActionDryRunEvidenceReady"))
        or truthy(action_gate.get("remainingActionDryRunEvidenceReady"))
        or truthy(r.get("remainingActionDryRunEvidenceReady"))
    )
    dry_run_action_ready = truthy(f.get("dryRunActionEvidenceReady")) or truthy(action_gate.get("dryRunActionEvidenceReady"))
    shuahuang_minimum_live_ready = (
        truthy(artifact_summary.get("shuaHuangMinimumLiveEvidenceReady"))
        or truthy(shuahuang_minimum_summary.get("shuaHuangMinimumLiveEvidenceReady"))
    )
    real_action_send_ready = truthy(f.get("realActionSendReady")) or truthy(action_gate.get("realActionSendReady"))
    safety_ready = truthy(s.get("actionSafetyInvariantReady"))
    migration_complete = truthy(m.get("objectiveComplete"))
    real_action_allowed = any(
        truthy(x) for x in [
            p.get("realActionNetworkAllowed"),
            f.get("realActionNetworkAllowed"),
            s.get("realActionNetworkAllowed"),
            m.get("realActionNetworkAllowed"),
        ]
    )

    required_files = {
        "selfDebugApk": file_info(apk_debug),
        "xiaohuangApk": file_info(xiaohuang_apk),
        "gameApk": file_info(game_apk),
        "fridaNativeSessionScript": file_info(frida_script),
        "preflightJson": file_info(reports / "device_regression_preflight.json"),
        "fullOfflineReplayJson": file_info(reports / "full_offline_replay_report.json"),
        "remainingActionDryRunJson": file_info(reports / "remaining_action_dryrun_payload_gate_evidence.json"),
        "actionSafetyJson": file_info(reports / "action_safety_invariants.json"),
        "migrationGoalStatusJson": file_info(reports / "migration_goal_status.json"),
    }

    missing: list[str] = []
    for name, info in required_files.items():
        if not info["exists"]:
            missing.append(f"file:{name}")
    if not full_ready:
        missing.append("fullOfflineReplayReady=false")
    if not shua_ready:
        missing.append("shuaHuangOfflineClosedLoopReplayReady=false")
    if not role_resource_parse_ready:
        missing.append("roleResourceParseReady=false")
    if not general_evidence_parse_ready:
        missing.append("generalEvidenceParseReady=false")
    if not daily_ready:
        missing.append("dailyOfflineClosedLoopReplayReady=false")
    if not daily_protocol_ready:
        missing.append("dailyProtocolEvidenceReady=false")
    if not daily_full_order_ready:
        missing.append("dailyFullRecoveredOrderReady=false")
    if not mine_ready:
        missing.append("mineOfflineClosedLoopReplayReady=false")
    if not mine_readonly_ready:
        missing.append("mineReadOnlyEvidenceReady=false")
    if not mine_selection_ready:
        missing.append("mineSelectionEvidenceReady=false")
    if not remaining_action_ready:
        missing.append("remainingActionDryRunEvidenceReady=false")
    if not safety_ready:
        missing.append("actionSafetyInvariantReady=false")
    if real_action_allowed:
        missing.append("unsafe:realActionNetworkAllowed=true")
    if real_action_send_ready:
        missing.append("unsafe:realActionSendReady=true")

    live_missing: list[str] = []
    if not preflight_ready:
        live_missing.append("preflightReady=false")
    if authorized_devices <= 0:
        live_missing.append("authorizedDeviceCount=0")
    if not dry_run_action_ready:
        live_missing.append("dryRunActionEvidenceReady=false/native wrapper capture evidence missing")
    if not shuahuang_minimum_live_ready:
        live_missing.append("shuaHuangMinimumLiveEvidenceReady=false")
    if not migration_complete:
        live_missing.append("migration objectiveComplete=false")

    offline_toolchain_ready = not missing
    true_device_regression_ready = bool(
        offline_toolchain_ready
        and preflight_ready
        and authorized_devices > 0
        and dry_run_action_ready
        and shuahuang_minimum_live_ready
        and not real_action_send_ready
        and not real_action_allowed
        and migration_complete
    )
    return {
        "summary": {
            "offlineToolchainReady": offline_toolchain_ready,
            "fullOfflineReplayReady": full_ready,
            "shuaHuangOfflineClosedLoopReplayReady": shua_ready,
            "roleResourceParseReady": role_resource_parse_ready,
            "generalEvidenceParseReady": general_evidence_parse_ready,
            "dailyOfflineClosedLoopReplayReady": daily_ready,
            "dailyProtocolEvidenceReady": daily_protocol_ready,
            "dailyFullRecoveredOrderReady": daily_full_order_ready,
            "mineOfflineClosedLoopReplayReady": mine_ready,
            "mineReadOnlyEvidenceReady": mine_readonly_ready,
            "mineSelectionEvidenceReady": mine_selection_ready,
            "remainingActionDryRunEvidenceReady": remaining_action_ready,
            "dryRunActionEvidenceReady": dry_run_action_ready,
            "shuaHuangMinimumLiveEvidenceReady": shuahuang_minimum_live_ready,
            "actionSafetyInvariantReady": safety_ready,
            "preflightReady": preflight_ready,
            "authorizedDeviceCount": authorized_devices,
            "migrationObjectiveComplete": migration_complete,
            "trueDeviceRegressionReady": true_device_regression_ready,
            "realActionNetworkAllowed": False,
            "realActionSendReady": False,
            "blocker": "overall readiness audit only; true completion requires authorized device, native wrapper capture evidence, and full migration objective completion",
        },
        "missingOffline": missing,
        "missingLive": live_missing,
        "requiredFiles": required_files,
        "preflightSummary": p,
        "fullOfflineSummary": f,
        "remainingActionSummary": r,
        "actionGateSummary": action_gate,
        "artifactVerificationSummary": artifact_summary,
        "shuaHuangMinimumGoalSummary": shuahuang_minimum_summary,
        "actionSafetySummary": s,
        "migrationSummary": m,
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 整体回归 Readiness 统一审计",
        "",
        "## Summary",
        "",
        f"- offlineToolchainReady: {str(s['offlineToolchainReady']).lower()}",
        f"- fullOfflineReplayReady: {str(s['fullOfflineReplayReady']).lower()}",
        f"- shuaHuangOfflineClosedLoopReplayReady: {str(s['shuaHuangOfflineClosedLoopReplayReady']).lower()}",
        f"- roleResourceParseReady: {str(s['roleResourceParseReady']).lower()}",
        f"- generalEvidenceParseReady: {str(s['generalEvidenceParseReady']).lower()}",
        f"- dailyOfflineClosedLoopReplayReady: {str(s['dailyOfflineClosedLoopReplayReady']).lower()}",
        f"- dailyProtocolEvidenceReady: {str(s['dailyProtocolEvidenceReady']).lower()}",
        f"- dailyFullRecoveredOrderReady: {str(s['dailyFullRecoveredOrderReady']).lower()}",
        f"- mineOfflineClosedLoopReplayReady: {str(s['mineOfflineClosedLoopReplayReady']).lower()}",
        f"- mineReadOnlyEvidenceReady: {str(s['mineReadOnlyEvidenceReady']).lower()}",
        f"- mineSelectionEvidenceReady: {str(s['mineSelectionEvidenceReady']).lower()}",
        f"- remainingActionDryRunEvidenceReady: {str(s['remainingActionDryRunEvidenceReady']).lower()}",
        f"- dryRunActionEvidenceReady: {str(s['dryRunActionEvidenceReady']).lower()}",
        f"- shuaHuangMinimumLiveEvidenceReady: {str(s['shuaHuangMinimumLiveEvidenceReady']).lower()}",
        f"- actionSafetyInvariantReady: {str(s['actionSafetyInvariantReady']).lower()}",
        f"- preflightReady: {str(s['preflightReady']).lower()}",
        f"- authorizedDeviceCount: {s['authorizedDeviceCount']}",
        f"- migrationObjectiveComplete: {str(s['migrationObjectiveComplete']).lower()}",
        f"- trueDeviceRegressionReady: {str(s['trueDeviceRegressionReady']).lower()}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- realActionSendReady: {str(s['realActionSendReady']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## Missing offline/toolchain evidence",
        "",
        "```json",
        json.dumps(report["missingOffline"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Missing live/device evidence",
        "",
        "```json",
        json.dumps(report["missingLive"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Required files",
        "",
        "```json",
        json.dumps(report["requiredFiles"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent), help="Self-developed source root")
    ap.add_argument("--out", help="Write JSON report; defaults to stdout")
    ap.add_argument("--markdown-out", help="Write Markdown report")
    ns = ap.parse_args()
    report = audit(Path(ns.root))
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
