#!/usr/bin/env python3
"""Audit whether recovered action/native evidence is sufficient to discuss an action gate.

This is an offline safety/readiness auditor. It never enables real sends. Even if all
offline evidence is present, `realActionSendReady` remains false until a separate,
user-controlled live action gate is designed, reviewed, and explicitly enabled.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

UNSAFE_SUMMARY_TRUE_KEYS = [
    "realActionNetworkAllowed",
    "networkSendAllowed",
]


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def bool_at(data: dict[str, Any], path: str, default: bool = False) -> bool:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return bool(value)


def int_at(data: dict[str, Any], path: str, default: int = 0) -> int:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    try:
        return int(value)
    except Exception:
        return default


def list_at(data: dict[str, Any], path: str) -> list[Any]:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return []
        value = value[part]
    return value if isinstance(value, list) else []


def wrapper_evidence(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("nativeWrapperCalibration", {}).get("summary", {})
    split_statuses = summary.get("splitStatuses", []) if isinstance(summary, dict) else []
    if not isinstance(split_statuses, list):
        split_statuses = []
    prefix_len = summary.get("prefixLength", {}) if isinstance(summary, dict) else {}
    suffix_len = summary.get("suffixLength", {}) if isinstance(summary, dict) else {}
    prefix_hash = summary.get("prefixHash", {}) if isinstance(summary, dict) else {}
    suffix_hash = summary.get("suffixHash", {}) if isinstance(summary, dict) else {}
    brush_yellow_coverage = summary.get("brushYellowWrapperCoverage", {}) if isinstance(summary, dict) else {}
    brush_yellow_details = summary.get("brushYellowWrapperDetails", {}) if isinstance(summary, dict) else {}
    field_audit = summary.get("nativeWrapperFieldAudit", {}) if isinstance(summary, dict) else {}
    if not isinstance(field_audit, dict):
        field_audit = {}
    proven_split = (
        "prefix_equals_lx_plus_key" in split_statuses or
        {"prefix_starts_with_lx", "prefix_ends_with_key"}.issubset(set(split_statuses))
    ) and ("suffix_equals_lb" in split_statuses or "suffix_assumed_lb" in split_statuses) and "unsplit" not in split_statuses
    stable = bool(prefix_len.get("stable", False)) and bool(suffix_len.get("stable", False)) and bool(prefix_hash.get("stable", False)) and bool(suffix_hash.get("stable", False))
    return {
        "captureCount": int(summary.get("captureCount", 0)) if isinstance(summary, dict) else 0,
        "uniqueGameHexCount": int(summary.get("uniqueGameHexCount", 0)) if isinstance(summary, dict) else 0,
        "splitStatuses": split_statuses,
        "stableWrapper": stable,
        "splitProven": proven_split,
        "brushYellowWrapperCoverageComplete": bool(brush_yellow_coverage.get("complete", False)),
        "brushYellowWrapperSplitProvenForBothStages": bool(brush_yellow_details.get("splitProvenForBothStages", brush_yellow_coverage.get("complete", False))),
        "brushYellowWrapperDetails": brush_yellow_details,
        "nativeWrapperFieldAudit": field_audit,
        "nativeWrapperFieldAuditReady": bool(field_audit.get("readyForDryRunWrapperPlan", False)),
        "brushYellowPrepare1520030Count": int(brush_yellow_coverage.get("prepare1520030", 0) or 0),
        "brushYellowDispatch1522030Count": int(brush_yellow_coverage.get("dispatch1522030", 0) or 0),
        "networkSendAllowed": bool(summary.get("networkSendAllowed", False)) if isinstance(summary, dict) else False,
        "actionSendReadyFromWrapperTool": bool(summary.get("actionSendReady", False)) if isinstance(summary, dict) else False,
        "readinessLevelFromWrapperTool": summary.get("readinessLevel", "unknown") if isinstance(summary, dict) else "unknown",
    }


def unsafe_flags(report: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in UNSAFE_SUMMARY_TRUE_KEYS:
        if bool_at(report, f"summary.{key}"):
            out.append(f"summary.{key}")
    contract_flags = list_at(report, "replayContract.evidence.unsafeTrueFlags")
    out.extend([f"replayContract:{flag}" for flag in contract_flags])
    for section in ["nativeWrapperCalibration", "readOnlyResponseCalibration", "actionResponseCalibration", "dailyResponseCalibration"]:
        if bool_at(report, f"{section}.summary.networkSendAllowed"):
            out.append(f"{section}.summary.networkSendAllowed")
    return out


def audit(report: dict[str, Any]) -> dict[str, Any]:
    wrapper = wrapper_evidence(report)
    shua_ready = bool_at(report, "summary.shuaHuangOfflineClosedLoopReplayReady")
    daily_ready = bool_at(report, "summary.dailyOfflineClosedLoopReplayReady")
    mine_ready = bool_at(report, "summary.mineOfflineClosedLoopReplayReady")
    dispatch_count = int_at(report, "summary.dispatchResultCount")
    daily_count = int_at(report, "summary.dailyStepResultCount")
    target_count = int_at(report, "summary.targetParsedCount")
    mine_count = int_at(report, "summary.mineParsedCount")
    resource_point_action_payload_ready = bool_at(report, "summary.resourcePointActionPayloadEvidenceReady")
    withdraw_payload_ready = bool_at(report, "summary.withdrawPayloadEvidenceReady")
    remaining_action_ready = bool_at(report, "summary.remainingActionDryRunEvidenceReady")
    unsafe = unsafe_flags(report)

    missing: list[str] = []
    if wrapper["captureCount"] < 2:
        missing.append("nativeWrapper:captureCount>=2")
    if wrapper["uniqueGameHexCount"] < 2:
        missing.append("nativeWrapper:uniqueGameHexCount>=2")
    if not wrapper["stableWrapper"]:
        missing.append("nativeWrapper:stable prefix/suffix length+hash")
    if not wrapper["splitProven"]:
        missing.append("nativeWrapper:lx/key/lb split proven")
    if not wrapper["brushYellowWrapperCoverageComplete"]:
        missing.append("nativeWrapper:brush-yellow 1520030+1522030 wrapper captures")
    if not wrapper["brushYellowWrapperSplitProvenForBothStages"]:
        missing.append("nativeWrapper:brush-yellow 1520030+1522030 split proven")
    if target_count <= 0:
        missing.append("readonly:041540 target parsed")
    if dispatch_count <= 0:
        missing.append("action:1522030 dispatch result parsed")
    if not shua_ready:
        missing.append("replay:brush-yellow closed loop")
    # Daily/mine are not required to discuss brush-yellow action gate, but they are useful
    # evidence for broader action coverage. Keep them as advisory gaps.
    advisory: list[str] = []
    if daily_count <= 0 or not daily_ready:
        advisory.append("daily closed-loop replay not ready")
    if mine_count <= 0 or not mine_ready:
        advisory.append("mine closed-loop replay not ready")
    if not remaining_action_ready:
        advisory.append("remaining resource-point/withdraw action payload dry-run evidence not present")
    if unsafe:
        missing.append("unsafe network flag must be false")
    # Deliberate non-technical gates that still block real action sends.
    policy_blockers = [
        "real action sender not implemented in self-developed app",
        "explicit user-controlled live action gate not present",
        "isolated device/account live action regression not completed",
    ]
    dry_run_evidence_ready = not missing
    readiness_level = "dry_run_action_evidence_ready" if dry_run_evidence_ready else "dry_run_only_missing_evidence"
    return {
        "summary": {
            "dryRunActionEvidenceReady": dry_run_evidence_ready,
            "realActionSendReady": False,
            "readinessLevel": readiness_level,
            "shuaHuangOfflineClosedLoopReplayReady": shua_ready,
            "dailyOfflineClosedLoopReplayReady": daily_ready,
            "mineOfflineClosedLoopReplayReady": mine_ready,
            "wrapperSplitProven": wrapper["splitProven"],
            "wrapperStable": wrapper["stableWrapper"],
            "brushYellowWrapperCoverageComplete": wrapper["brushYellowWrapperCoverageComplete"],
            "brushYellowWrapperSplitProvenForBothStages": wrapper["brushYellowWrapperSplitProvenForBothStages"],
            "nativeWrapperFieldAuditReady": wrapper["nativeWrapperFieldAuditReady"],
            "resourcePointActionPayloadEvidenceReady": resource_point_action_payload_ready,
            "withdrawPayloadEvidenceReady": withdraw_payload_ready,
            "remainingActionDryRunEvidenceReady": remaining_action_ready,
            "realActionNetworkAllowed": False,
            "blocker": "action gate audit only; true game action send remains disabled",
        },
        "missing": missing,
        "advisory": advisory,
        "policyBlockers": policy_blockers,
        "evidence": {
            "nativeWrapper": wrapper,
            "counts": {
                "targetParsedCount": target_count,
                "dispatchResultCount": dispatch_count,
                "dailyStepResultCount": daily_count,
                "mineParsedCount": mine_count,
                "resourcePointActionPayloadEvidenceReady": resource_point_action_payload_ready,
                "withdrawPayloadEvidenceReady": withdraw_payload_ready,
                "remainingActionDryRunEvidenceReady": remaining_action_ready,
            },
            "unsafeFlags": unsafe,
        },
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 动作 Gate Readiness 审计",
        "",
        "## Summary",
        "",
        f"- dryRunActionEvidenceReady: {str(s['dryRunActionEvidenceReady']).lower()}",
        f"- realActionSendReady: {str(s['realActionSendReady']).lower()}",
        f"- readinessLevel: {s['readinessLevel']}",
        f"- shuaHuangOfflineClosedLoopReplayReady: {str(s['shuaHuangOfflineClosedLoopReplayReady']).lower()}",
        f"- dailyOfflineClosedLoopReplayReady: {str(s['dailyOfflineClosedLoopReplayReady']).lower()}",
        f"- mineOfflineClosedLoopReplayReady: {str(s['mineOfflineClosedLoopReplayReady']).lower()}",
        f"- wrapperSplitProven: {str(s['wrapperSplitProven']).lower()}",
        f"- wrapperStable: {str(s['wrapperStable']).lower()}",
        f"- brushYellowWrapperCoverageComplete: {str(s['brushYellowWrapperCoverageComplete']).lower()}",
        f"- brushYellowWrapperSplitProvenForBothStages: {str(s['brushYellowWrapperSplitProvenForBothStages']).lower()}",
        f"- nativeWrapperFieldAuditReady: {str(s['nativeWrapperFieldAuditReady']).lower()}",
        f"- resourcePointActionPayloadEvidenceReady: {str(s['resourcePointActionPayloadEvidenceReady']).lower()}",
        f"- withdrawPayloadEvidenceReady: {str(s['withdrawPayloadEvidenceReady']).lower()}",
        f"- remainingActionDryRunEvidenceReady: {str(s['remainingActionDryRunEvidenceReady']).lower()}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## Missing hard evidence",
        "",
        "```json",
        json.dumps(report["missing"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Advisory gaps",
        "",
        "```json",
        json.dumps(report["advisory"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Policy blockers",
        "",
    ]
    lines.extend(f"- {item}" for item in report["policyBlockers"])
    lines += [
        "",
        "## Evidence",
        "",
        "```json",
        json.dumps(report["evidence"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="device_regression_report.json")
    ap.add_argument("--out", help="Write JSON report; defaults to stdout")
    ap.add_argument("--markdown-out", help="Write Markdown report")
    ns = ap.parse_args()
    report = audit(load_json(Path(ns.input)))
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
