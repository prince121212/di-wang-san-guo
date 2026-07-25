#!/usr/bin/env python3
"""Verify the brush-yellow minimum goal from capture/regression artifacts.

This is a goal-level gate for the first real feature:

login -> role/resource -> generals/formations -> 041540 search -> configured target/
formation selection -> 1520030/1522030 wrapper evidence -> 1522030 dispatch response ->
stop/logout -> safety boundary.

It is offline-only: it reads reports produced by capture_device_protocol_regression.sh or
device_regression_from_logs.py. It does not connect to a device and does not enable real
action sends.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

TOOL_DIR = Path(__file__).resolve().parent


def load_tool(name: str):
    path = TOOL_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


artifact_verifier = load_tool("verify_device_regression_artifacts")


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


def nested(data: dict[str, Any], *path: str) -> Any:
    value: Any = data
    for part in path:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return load_json(path)


def locate(path: Path) -> tuple[Path, Path | None]:
    return artifact_verifier.locate_regression_dir(path)


def step_ok_from_replay(replay: dict[str, Any], name: str) -> bool:
    for item in list_or_empty(replay.get("steps")):
        if isinstance(item, dict) and item.get("step") == name:
            return bool_value(item.get("ok", False))
    return False


def scenario_ok(scenarios: dict[str, Any], name: str) -> bool:
    return bool_value(nested(scenarios, "scenarios", name, "requiredOk"))


def configured_target_selection_ok(replay: dict[str, Any]) -> bool:
    summary = dict_or_empty(replay.get("summary"))
    evidence = dict_or_empty(summary.get("targetSelectionEvidence"))
    return bool(
        step_ok_from_replay(replay, "chooseTarget")
        and bool_value(evidence.get("targetSelectionEvidenceReady"))
        and bool_value(evidence.get("strictTargetTypeMatch"))
        and evidence.get("targetTypeConfigured") in {"HUANG_JIN", "SHAN_ZEI"}
        and int(evidence.get("inputTargetCount") or 0) > 0
        and int(evidence.get("filterMatchedCount") or 0) > 0
        and int(evidence.get("typeMatchedCount") or 0) > 0
        and evidence.get("selectedTargetId") is not None
    )


def dispatch_payload_evidence_ok(replay: dict[str, Any]) -> bool:
    summary = dict_or_empty(replay.get("summary"))
    evidence = dict_or_empty(summary.get("dispatchPayloadEvidence"))
    return bool(
        step_ok_from_replay(replay, "buildDispatchPayloads/1520030+1522030")
        and bool_value(evidence.get("dispatchPayloadEvidenceReady"))
        and evidence.get("prepareOpcode") == "1520030"
        and evidence.get("expeditionOpcode") == "1522030"
        and int(evidence.get("generalCount") or 0) > 0
        and isinstance(evidence.get("targetIdHex"), str)
        and len(str(evidence.get("targetIdHex"))) >= 16
        and "1520030" in str(evidence.get("preparePayload") or "")
        and "1522030" in str(evidence.get("expeditionPayload") or "")
        and bool_value(evidence.get("prepareContainsTarget"))
        and bool_value(evidence.get("expeditionContainsTarget"))
        and bool_value(evidence.get("prepareContainsAllGenerals"))
        and bool_value(evidence.get("expeditionContainsAllGenerals"))
    )


def verify(path: Path) -> dict[str, Any]:
    regression_dir, capture_root = locate(path)
    device_report = load_json(regression_dir / "device_regression_report.json")
    device_summary = dict_or_empty(device_report.get("summary"))
    replay = read_optional_json(regression_dir / "shuahuang_offline_replay.json")
    action_gate = read_optional_json(regression_dir / "action_gate_readiness.json")
    action_gate_summary = dict_or_empty(action_gate.get("summary"))
    scenarios = (
        read_optional_json(capture_root / "capture_scenario_check.json")
        if capture_root and (capture_root / "capture_scenario_check.json").exists()
        else read_optional_json(regression_dir / "capture_scenario_coverage.json")
    )
    preflight = read_optional_json(capture_root / "preflight.json") if capture_root else {}
    preflight_summary = dict_or_empty(preflight.get("summary"))

    native_summary = dict_or_empty(nested(device_report, "nativeWrapperCalibration", "summary"))
    brush_wrapper_coverage = dict_or_empty(native_summary.get("brushYellowWrapperCoverage"))
    brush_wrapper_details = dict_or_empty(native_summary.get("brushYellowWrapperDetails"))
    if not brush_wrapper_details:
        brush_wrapper_details = dict_or_empty(nested(action_gate, "evidence", "nativeWrapper", "brushYellowWrapperDetails"))

    replay_summary = dict_or_empty(replay.get("summary"))
    replay_ready = bool_value(replay_summary.get("shuaHuangOfflineClosedLoopReplayReady"))
    scenario_required_ready = bool_value(nested(scenarios, "summary", "captureScenarioRequiredReady"))
    preflight_ready = bool_value(preflight_summary.get("preflightReady"))
    dry_run_action_evidence_ready = bool_value(device_summary.get("dryRunActionEvidenceReady")) or bool_value(action_gate_summary.get("dryRunActionEvidenceReady"))
    real_action_network_allowed = (
        bool_value(device_summary.get("realActionNetworkAllowed"))
        or bool_value(preflight_summary.get("realActionNetworkAllowed"))
        or bool_value(action_gate_summary.get("realActionNetworkAllowed"))
    )
    real_action_send_ready = bool_value(action_gate_summary.get("realActionSendReady"))

    steps = {
        "preflight": preflight_ready,
        "login": scenario_ok(scenarios, "loginState8004") and step_ok_from_replay(replay, "login/session"),
        "roleResource": scenario_ok(scenarios, "loginState8004") and step_ok_from_replay(replay, "role/resource"),
        "generalFormationBaseline": (
            scenario_ok(scenarios, "generalFormationBaseline")
            and step_ok_from_replay(replay, "generals")
            and step_ok_from_replay(replay, "formations")
            and step_ok_from_replay(replay, "chooseFormation")
        ),
        "findYellow041540": scenario_ok(scenarios, "brushYellowSearch041540") and step_ok_from_replay(replay, "findYellow/041540"),
        "configuredTargetSelection": configured_target_selection_ok(replay),
        "dispatchPayloadEvidence": dispatch_payload_evidence_ok(replay),
        "brushYellowWrapper1520030And1522030": (
            scenario_ok(scenarios, "brushYellowNativeWrapper1520")
            and bool_value(brush_wrapper_coverage.get("complete"))
            and bool_value(brush_wrapper_details.get("splitProvenForBothStages"))
        ),
        "dispatch1522030Response": scenario_ok(scenarios, "brushYellowDispatch1522030") and step_ok_from_replay(replay, "dispatchResult/1522030"),
        "stopLogout": scenario_ok(scenarios, "selfStopLogout") and step_ok_from_replay(replay, "stop/logout"),
        "dryRunActionEvidence": dry_run_action_evidence_ready,
        "safetyGate": (not real_action_network_allowed) and (not real_action_send_ready),
    }
    missing = [name for name, ok in steps.items() if not ok]
    live_evidence_ready = not missing and scenario_required_ready and replay_ready
    self_app_real_send_blockers = []
    if not real_action_send_ready:
        self_app_real_send_blockers.append("realActionSendReady=false")
    if not real_action_network_allowed:
        self_app_real_send_blockers.append("realActionNetworkAllowed=false")
    final_ready = live_evidence_ready and real_action_send_ready and real_action_network_allowed
    return {
        "summary": {
            "shuaHuangMinimumLiveEvidenceReady": live_evidence_ready,
            "shuaHuangMinimumFinalReady": final_ready,
            "offlineClosedLoopReplayReady": replay_ready,
            "captureScenarioRequiredReady": scenario_required_ready,
            "preflightReady": preflight_ready,
            "dryRunActionEvidenceReady": dry_run_action_evidence_ready,
            "realActionNetworkAllowed": real_action_network_allowed,
            "realActionSendReady": real_action_send_ready,
            "blocker": (
                "brush-yellow minimum goal gate; final self-app execution remains false while real action send/network gates are disabled"
                if not final_ready
                else ""
            ),
        },
        "steps": steps,
        "missing": missing,
        "selfAppRealSendBlockers": self_app_real_send_blockers,
        "evidence": {
            "selectedFormationId": replay_summary.get("selectedFormationId"),
            "selectedTargetId": replay_summary.get("selectedTargetId"),
            "appliedTargetFilter": replay_summary.get("appliedTargetFilter"),
            "targetSelectionEvidence": replay_summary.get("targetSelectionEvidence"),
            "dispatchPayloadEvidence": replay_summary.get("dispatchPayloadEvidence"),
            "dispatchMatched": replay_summary.get("dispatchMatched"),
            "dispatchSuccess": replay_summary.get("dispatchSuccess"),
            "brushYellowWrapperCoverage": brush_wrapper_coverage,
            "brushYellowWrapperDetails": brush_wrapper_details,
            "captureScenarioMissingRequired": scenarios.get("missingRequired", []),
            "replayMissingSteps": replay.get("missingSteps", []),
            "selfStopLogoutScenarioRequiredOk": scenario_ok(scenarios, "selfStopLogout"),
            "actionGateMissing": action_gate.get("missing", []),
        },
        "paths": {
            "regressionDir": str(regression_dir),
            "captureRoot": str(capture_root) if capture_root else "",
        },
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 刷黄最小目标验收报告",
        "",
        "## Summary",
        "",
        f"- shuaHuangMinimumLiveEvidenceReady: {str(s['shuaHuangMinimumLiveEvidenceReady']).lower()}",
        f"- shuaHuangMinimumFinalReady: {str(s['shuaHuangMinimumFinalReady']).lower()}",
        f"- offlineClosedLoopReplayReady: {str(s['offlineClosedLoopReplayReady']).lower()}",
        f"- captureScenarioRequiredReady: {str(s['captureScenarioRequiredReady']).lower()}",
        f"- preflightReady: {str(s['preflightReady']).lower()}",
        f"- dryRunActionEvidenceReady: {str(s['dryRunActionEvidenceReady']).lower()}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- realActionSendReady: {str(s['realActionSendReady']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## Steps",
        "",
        "```json",
        json.dumps(report["steps"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Missing",
        "",
        "```json",
        json.dumps(report["missing"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Self-app real send blockers",
        "",
        "```json",
        json.dumps(report["selfAppRealSendBlockers"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Evidence",
        "",
        "```json",
        json.dumps(report["evidence"], ensure_ascii=False, indent=2, sort_keys=True),
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
