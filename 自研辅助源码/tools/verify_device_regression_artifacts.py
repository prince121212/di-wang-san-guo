#!/usr/bin/env python3
"""Verify completeness and safety of device protocol regression artifacts.

Input may be either:
- the capture root produced by capture_device_protocol_regression.sh, containing regression/;
- the regression/ directory itself, containing device_regression_report.json.

This verifier is offline-only. It checks report files, readiness summaries and safety flags.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REGRESSION_REQUIRED = [
    "device_regression_report.json",
    "merged_channel_extra.json",
    "summary.md",
    "native_wrapper_calibration.md",
    "readonly_calibration.md",
    "action_response_calibration.md",
    "daily_response_calibration.md",
    "capture_scenario_coverage.json",
    "capture_scenario_coverage.md",
    "replay_contract.json",
    "replay_contract.md",
    "shuahuang_offline_replay.json",
    "shuahuang_offline_replay.md",
    "daily_offline_replay.json",
    "daily_offline_replay.md",
    "mine_offline_replay.json",
    "mine_offline_replay.md",
    "action_gate_readiness.json",
    "action_gate_readiness.md",
    "full_offline_replay.json",
    "full_offline_replay.md",
]
CAPTURE_ROOT_EXPECTED = [
    "preflight.json",
    "preflight.md",
    "capture_operator_guide.md",
    "frida.log",
    "logcat.txt",
    "device_combined.log",
    "capture_summary.md",
    "adb_devices.txt",
    "capture_scenario_check.json",
    "capture_scenario_check.md",
    "self_lifecycle_logcat_check.json",
    "self_lifecycle_logcat_check.md",
    "shuahuang_minimum_goal_check.json",
    "shuahuang_minimum_goal_check.md",
]
SAFETY_FALSE_SUMMARY_KEYS = [
    "realActionNetworkAllowed",
]
READINESS_KEYS = [
    "shuaHuangOfflineReplayReady",
    "shuaHuangOfflineClosedLoopReplayReady",
    "dailyOfflineReplayReady",
    "dailyOfflineClosedLoopReplayReady",
    "mineOfflineReplayReady",
    "mineOfflineClosedLoopReplayReady",
    "dryRunActionEvidenceReady",
    "fullOfflineReplayReady",
]


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return bool(value)


def locate_regression_dir(path: Path) -> tuple[Path, Path | None]:
    path = path.resolve()
    if (path / "device_regression_report.json").exists():
        return path, path.parent if path.name == "regression" else None
    if (path / "regression" / "device_regression_report.json").exists():
        return path / "regression", path
    raise FileNotFoundError(f"cannot find device_regression_report.json under {path}")


def nested_dict(data: dict[str, Any], *path: str) -> dict[str, Any]:
    value: Any = data
    for part in path:
        if not isinstance(value, dict):
            return {}
        value = value.get(part, {})
    return value if isinstance(value, dict) else {}


def verify(path: Path) -> dict[str, Any]:
    regression_dir, capture_root = locate_regression_dir(path)
    report = load_json(regression_dir / "device_regression_report.json")
    action_gate = load_json(regression_dir / "action_gate_readiness.json") if (regression_dir / "action_gate_readiness.json").exists() else {}
    replay_contract = load_json(regression_dir / "replay_contract.json") if (regression_dir / "replay_contract.json").exists() else {}
    capture_scenarios = load_json(capture_root / "capture_scenario_check.json") if capture_root and (capture_root / "capture_scenario_check.json").exists() else {}
    self_lifecycle = load_json(capture_root / "self_lifecycle_logcat_check.json") if capture_root and (capture_root / "self_lifecycle_logcat_check.json").exists() else {}
    shuahuang_minimum_goal = load_json(capture_root / "shuahuang_minimum_goal_check.json") if capture_root and (capture_root / "shuahuang_minimum_goal_check.json").exists() else {}
    preflight = load_json(capture_root / "preflight.json") if capture_root and (capture_root / "preflight.json").exists() else {}

    missing_regression = [name for name in REGRESSION_REQUIRED if not (regression_dir / name).exists()]
    missing_capture = [name for name in CAPTURE_ROOT_EXPECTED if capture_root and not (capture_root / name).exists()]
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    readiness = {key: bool_value(summary.get(key, False)) for key in READINESS_KEYS}
    safety_violations = []
    for key in SAFETY_FALSE_SUMMARY_KEYS:
        if bool_value(summary.get(key, False)):
            safety_violations.append(f"summary.{key}=true")
    gate_summary = action_gate.get("summary", {}) if isinstance(action_gate.get("summary"), dict) else {}
    action_gate_missing = action_gate.get("missing", []) if isinstance(action_gate.get("missing", []), list) else []
    native_wrapper_summary = nested_dict(report, "nativeWrapperCalibration", "summary")
    brush_yellow_wrapper_details = native_wrapper_summary.get("brushYellowWrapperDetails", {})
    if not isinstance(brush_yellow_wrapper_details, dict):
        brush_yellow_wrapper_details = {}
    brush_yellow_wrapper_coverage = native_wrapper_summary.get("brushYellowWrapperCoverage", {})
    if not isinstance(brush_yellow_wrapper_coverage, dict):
        brush_yellow_wrapper_coverage = {}
    gate_native_evidence = nested_dict(action_gate, "evidence", "nativeWrapper")
    if not brush_yellow_wrapper_details:
        brush_yellow_wrapper_details = gate_native_evidence.get("brushYellowWrapperDetails", {})
        if not isinstance(brush_yellow_wrapper_details, dict):
            brush_yellow_wrapper_details = {}
    if bool_value(gate_summary.get("realActionSendReady", False)):
        safety_violations.append("actionGateReadiness.realActionSendReady=true")
    unsafe_contract = replay_contract.get("evidence", {}).get("unsafeTrueFlags", []) if isinstance(replay_contract.get("evidence"), dict) else []
    scenario_summary = capture_scenarios.get("summary", {}) if isinstance(capture_scenarios.get("summary"), dict) else {}
    scenario_required_ready = bool_value(scenario_summary.get("captureScenarioRequiredReady", False))
    scenario_recommended_ready = bool_value(scenario_summary.get("captureScenarioRecommendedReady", False))
    missing_scenarios = capture_scenarios.get("missingRequired", []) if isinstance(capture_scenarios.get("missingRequired", []), list) else []
    self_lifecycle_summary = self_lifecycle.get("summary", {}) if isinstance(self_lifecycle.get("summary"), dict) else {}
    self_lifecycle_ready = bool_value(self_lifecycle_summary.get("selfLifecycleLogcatReady", False))
    self_lifecycle_missing = self_lifecycle.get("missing", []) if isinstance(self_lifecycle.get("missing", []), list) else []
    if bool_value(self_lifecycle_summary.get("realActionNetworkAllowed", False)):
        safety_violations.append("selfLifecycle.summary.realActionNetworkAllowed=true")
    shuahuang_minimum_goal_summary = shuahuang_minimum_goal.get("summary", {}) if isinstance(shuahuang_minimum_goal.get("summary"), dict) else {}
    shuahuang_minimum_live_ready = bool_value(shuahuang_minimum_goal_summary.get("shuaHuangMinimumLiveEvidenceReady", False))
    shuahuang_minimum_final_ready = bool_value(shuahuang_minimum_goal_summary.get("shuaHuangMinimumFinalReady", False))
    shuahuang_minimum_missing = shuahuang_minimum_goal.get("missing", []) if isinstance(shuahuang_minimum_goal.get("missing", []), list) else []
    preflight_summary = preflight.get("summary", {}) if isinstance(preflight.get("summary"), dict) else {}
    preflight_present = bool(preflight)
    preflight_ready = bool_value(preflight_summary.get("preflightReady", False))
    preflight_missing = preflight.get("missing", []) if isinstance(preflight.get("missing", []), list) else []
    if bool_value(preflight_summary.get("realActionNetworkAllowed", False)):
        safety_violations.append("preflight.summary.realActionNetworkAllowed=true")
    if unsafe_contract:
        safety_violations.extend([f"replayContract.unsafeTrueFlags:{flag}" for flag in unsafe_contract])

    hard_missing = []
    hard_missing.extend([f"missing regression file:{name}" for name in missing_regression])
    hard_missing.extend([f"missing capture file:{name}" for name in missing_capture])
    hard_missing.extend([f"safety violation:{item}" for item in safety_violations])
    if capture_root and (not preflight_present or not preflight_ready):
        hard_missing.append("preflight:not ready")
    hard_missing.extend([f"preflight missing:{item}" for item in preflight_missing])
    hard_missing.extend([f"missing capture scenario:{item}" for item in missing_scenarios])
    if capture_root and not self_lifecycle:
        hard_missing.append("self lifecycle logcat:missing report")
    if capture_root and not self_lifecycle_ready:
        hard_missing.append("self lifecycle logcat:not ready")
    hard_missing.extend([f"self lifecycle missing:{item}" for item in self_lifecycle_missing])
    if capture_root and not shuahuang_minimum_goal:
        hard_missing.append("shuahuang minimum goal:missing report")
    if capture_root and not shuahuang_minimum_live_ready:
        hard_missing.append("shuahuang minimum goal:not live-evidence ready")
    hard_missing.extend([f"shuahuang minimum goal missing:{item}" for item in shuahuang_minimum_missing])
    hard_missing.extend([f"action gate missing:{item}" for item in action_gate_missing])
    # A complete artifact set can still be only offline-ready; true live regression requires
    # capture_root files and explicit readiness keys from real logs/base data.
    offline_artifacts_complete = not missing_regression and not safety_violations
    capture_artifacts_present = capture_root is not None and not missing_capture
    true_device_regressionReady = bool(
        capture_artifacts_present and
        preflight_ready and
        scenario_required_ready and
        self_lifecycle_ready and
        shuahuang_minimum_live_ready and
        readiness.get("shuaHuangOfflineClosedLoopReplayReady") and
        readiness.get("dryRunActionEvidenceReady") and
        readiness.get("fullOfflineReplayReady") and
        not safety_violations and
        bool_value(gate_summary.get("realActionSendReady", False)) is False
    )
    return {
        "summary": {
            "offlineRegressionArtifactsComplete": offline_artifacts_complete,
            "captureArtifactsPresent": capture_artifacts_present,
            "preflightPresent": preflight_present,
            "preflightReady": preflight_ready,
            "captureScenarioRequiredReady": scenario_required_ready,
            "captureScenarioRecommendedReady": scenario_recommended_ready,
            "selfLifecycleLogcatReady": self_lifecycle_ready,
            "shuaHuangMinimumLiveEvidenceReady": shuahuang_minimum_live_ready,
            "shuaHuangMinimumFinalReady": shuahuang_minimum_final_ready,
            "trueDeviceRegressionEvidenceReady": true_device_regressionReady,
            "realActionNetworkAllowed": False,
            "blocker": "artifact verification only; true device/action regression still requires isolated device logs and disabled real action send",
        },
        "paths": {
            "regressionDir": str(regression_dir),
            "captureRoot": str(capture_root) if capture_root else "",
        },
        "missing": {
            "regressionFiles": missing_regression,
            "captureFiles": missing_capture,
            "hardMissing": hard_missing,
        },
        "captureScenarios": {
            "requiredReady": scenario_required_ready,
            "recommendedReady": scenario_recommended_ready,
            "missingRequired": missing_scenarios,
            "missingRecommended": capture_scenarios.get("missingRecommended", []) if isinstance(capture_scenarios.get("missingRecommended", []), list) else [],
        },
        "selfLifecycleLogcat": {
            "ready": self_lifecycle_ready,
            "missing": self_lifecycle_missing,
            "summary": self_lifecycle_summary,
        },
        "shuaHuangMinimumGoal": {
            "liveEvidenceReady": shuahuang_minimum_live_ready,
            "finalReady": shuahuang_minimum_final_ready,
            "missing": shuahuang_minimum_missing,
            "summary": shuahuang_minimum_goal_summary,
        },
        "preflight": {
            "present": preflight_present,
            "ready": preflight_ready,
            "missing": preflight_missing,
            "summary": preflight_summary,
        },
        "actionGateMissing": action_gate_missing,
        "brushYellowWrapper": {
            "coverage": brush_yellow_wrapper_coverage,
            "details": brush_yellow_wrapper_details,
            "splitProvenForBothStages": bool_value(
                brush_yellow_wrapper_details.get(
                    "splitProvenForBothStages",
                    gate_native_evidence.get("brushYellowWrapperSplitProvenForBothStages", False)
                )
            ),
        },
        "readiness": readiness,
        "safety": {
            "violations": safety_violations,
            "actionGateRealActionSendReady": bool_value(gate_summary.get("realActionSendReady", False)),
            "replayContractUnsafeTrueFlags": unsafe_contract,
        },
        "actionGate": action_gate.get("summary", {}),
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 设备回归产物验收报告",
        "",
        "## Summary",
        "",
        f"- offlineRegressionArtifactsComplete: {str(s['offlineRegressionArtifactsComplete']).lower()}",
        f"- captureArtifactsPresent: {str(s['captureArtifactsPresent']).lower()}",
        f"- preflightPresent: {str(s['preflightPresent']).lower()}",
        f"- preflightReady: {str(s['preflightReady']).lower()}",
        f"- captureScenarioRequiredReady: {str(s['captureScenarioRequiredReady']).lower()}",
        f"- captureScenarioRecommendedReady: {str(s['captureScenarioRecommendedReady']).lower()}",
        f"- selfLifecycleLogcatReady: {str(s['selfLifecycleLogcatReady']).lower()}",
        f"- shuaHuangMinimumLiveEvidenceReady: {str(s['shuaHuangMinimumLiveEvidenceReady']).lower()}",
        f"- shuaHuangMinimumFinalReady: {str(s['shuaHuangMinimumFinalReady']).lower()}",
        f"- trueDeviceRegressionEvidenceReady: {str(s['trueDeviceRegressionEvidenceReady']).lower()}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## Capture scenarios",
        "",
        "```json",
        json.dumps(report["captureScenarios"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Self lifecycle logcat",
        "",
        "```json",
        json.dumps(report["selfLifecycleLogcat"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## ShuaHuang minimum goal",
        "",
        "```json",
        json.dumps(report["shuaHuangMinimumGoal"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Preflight",
        "",
        "```json",
        json.dumps(report["preflight"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Readiness",
        "",
        "```json",
        json.dumps(report["readiness"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Action gate missing",
        "",
        "```json",
        json.dumps(report["actionGateMissing"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Brush yellow wrapper evidence",
        "",
        "```json",
        json.dumps(report["brushYellowWrapper"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Missing",
        "",
        "```json",
        json.dumps(report["missing"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Safety",
        "",
        "```json",
        json.dumps(report["safety"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Paths",
        "",
        "```json",
        json.dumps(report["paths"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="capture root or regression directory")
    ap.add_argument("--out", help="Write JSON report; defaults to stdout")
    ap.add_argument("--markdown-out", help="Write Markdown report")
    ns = ap.parse_args()
    report = verify(Path(ns.input))
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
