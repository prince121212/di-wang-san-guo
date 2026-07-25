#!/usr/bin/env python3
"""Generate an offline positive fixture for native wrapper readiness.

The current worktree intentionally keeps real action sends disabled and has no live
native-wrapper capture.  This helper builds a deterministic *fixture* that answers a
narrow regression question:

- if a future device capture contains split lx+key+gameHex+lb wrapper bodies for the
  brush-yellow 1520030 and 1522030 stages, will the recovered action gate flip to
  dryRunActionEvidenceReady=true?
- will the higher-level overall readiness still refuse to mark true device regression
  ready when preflight/device/migration evidence is absent?

It never contacts a device/server and never edits the canonical reports unless the
caller explicitly writes outputs under a separate directory.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

TOOL_DIR = Path(__file__).resolve().parent
ROOT = TOOL_DIR.parent


def load_tool(name: str):
    path = TOOL_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


native_wrapper = load_tool("calibrate_native_wrapper_trace")
action_gate = load_tool("verify_action_gate_readiness")
overall = load_tool("verify_overall_regression_readiness")


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def fixture_log() -> str:
    """Return minimal wrapper evidence for both brush-yellow action stages.

    The values are intentionally toy fixture values.  They prove parser/gate behavior,
    not live server validity.
    """
    return "\n".join([
        "[java-native-ret] com.ifengwoo.dwpm.tuoji.DWSG.HelpClass.getKey => KEY",
        '[native-wrapper-json] {"source":"fixture","threadId":"1","gameHex":"0000000000000000000a1520030010000000000000007","rawBody":"LXKEY0000000000000000000a1520030010000000000000007LB","lx":"LX","key":"KEY","lb":"LB"}',
        '[native-wrapper-json] {"source":"fixture","threadId":"1","gameHex":"000000000000000000151522030010000000000000007","rawBody":"LXKEY000000000000000000151522030010000000000000007LB","lx":"LX","key":"KEY","lb":"LB"}',
    ]) + "\n"


def build_positive_full_report(base_full: dict[str, Any]) -> dict[str, Any]:
    report = copy.deepcopy(base_full)
    report["nativeWrapperCalibration"] = native_wrapper.calibrate(fixture_log(), include_values=False)
    report.setdefault("readOnlyResponseCalibration", {"summary": {"networkSendAllowed": False}})
    report.setdefault("actionResponseCalibration", {"summary": {"networkSendAllowed": False}})
    report.setdefault("dailyResponseCalibration", {"summary": {"networkSendAllowed": False}})
    report.setdefault("replayContract", {}).setdefault("evidence", {}).setdefault("unsafeTrueFlags", [])
    report.setdefault("summary", {})["realActionNetworkAllowed"] = False
    report["summary"]["networkSendAllowed"] = False
    gate = action_gate.audit(report)
    report["actionGateAudit"] = gate
    report["summary"]["dryRunActionEvidenceReady"] = bool(gate["summary"].get("dryRunActionEvidenceReady"))
    report["summary"]["realActionSendReady"] = False
    report["summary"]["realActionNetworkAllowed"] = False
    return report


def write_fixture_overall_root(temp_parent: Path, positive_full: dict[str, Any]) -> Path:
    """Create a temporary root shaped like the source tree for overall.audit()."""
    root = temp_parent / "自研辅助源码"
    reports = root / "reports"
    reports.mkdir(parents=True)
    (root / "app" / "build" / "outputs" / "apk" / "debug").mkdir(parents=True)
    (root / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk").write_bytes(b"fixture-debug-apk")
    (temp_parent / "小黄点辅助.apk").write_bytes(b"fixture-xiaohuang-apk")
    (temp_parent / "三国·帝王联盟1.66.apk").write_bytes(b"fixture-game-apk")
    frida_dir = temp_parent / "reverse_cases" / "apk" / "scripts"
    frida_dir.mkdir(parents=True)
    (frida_dir / "frida_native_session_trace_v2.js").write_text("// fixture frida script\n", encoding="utf-8")
    (reports / "full_offline_replay_report.json").write_text(json.dumps(positive_full, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (reports / "remaining_action_dryrun_payload_gate_evidence.json").write_text(json.dumps({
        "summary": {
            "remainingActionDryRunEvidenceReady": True,
            "resourcePointActionPayloadEvidenceReady": True,
            "withdrawPayloadEvidenceReady": True,
            "realActionNetworkAllowed": False,
        }
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (reports / "device_regression_preflight.json").write_text(json.dumps({
        "summary": {
            "preflightReady": False,
            "authorizedDeviceCount": 0,
            "realActionNetworkAllowed": False,
        }
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (reports / "action_safety_invariants.json").write_text(json.dumps({
        "summary": {
            "actionSafetyInvariantReady": True,
            "realActionNetworkAllowed": False,
        }
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (reports / "migration_goal_status.json").write_text(json.dumps({
        "summary": {
            "objectiveComplete": False,
            "realActionNetworkAllowed": False,
        }
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return root


def build_evidence(base_full_report: Path) -> dict[str, Any]:
    base_full = load_json(base_full_report)
    positive_full = build_positive_full_report(base_full)
    with tempfile.TemporaryDirectory(prefix="dwpm_native_fixture_") as td:
        fixture_root = write_fixture_overall_root(Path(td), positive_full)
        overall_report = overall.audit(fixture_root)
    return {
        "summary": {
            "fixtureOnly": True,
            "positiveActionGateDryRunReady": bool(positive_full["actionGateAudit"]["summary"].get("dryRunActionEvidenceReady")),
            "positiveOverallDryRunReady": bool(overall_report["summary"].get("dryRunActionEvidenceReady")),
            "positiveOverallOfflineToolchainReady": bool(overall_report["summary"].get("offlineToolchainReady")),
            "positiveOverallTrueDeviceRegressionReady": bool(overall_report["summary"].get("trueDeviceRegressionReady")),
            "positiveOverallRealActionNetworkAllowed": bool(overall_report["summary"].get("realActionNetworkAllowed")),
            "positiveOverallRealActionSendReady": bool(overall_report["summary"].get("realActionSendReady")),
            "blocker": "fixture proves offline dry-run readiness path only; live ADB/native capture and migration completion remain required",
        },
        "fixtureLog": fixture_log(),
        "nativeWrapperCalibration": positive_full["nativeWrapperCalibration"],
        "positiveActionGateAudit": positive_full["actionGateAudit"],
        "positiveFullOfflineSummary": positive_full.get("summary", {}),
        "positiveOverallReadiness": overall_report,
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    gate = report["positiveActionGateAudit"]["summary"]
    overall_summary = report["positiveOverallReadiness"]["summary"]
    wrapper_summary = report["nativeWrapperCalibration"]["summary"]
    lines = [
        "# Native Wrapper 阳性 Fixture Readiness 证据",
        "",
        "## 结论",
        "",
        f"- fixtureOnly: {str(s['fixtureOnly']).lower()}",
        f"- positiveActionGateDryRunReady: {str(s['positiveActionGateDryRunReady']).lower()}",
        f"- positiveOverallDryRunReady: {str(s['positiveOverallDryRunReady']).lower()}",
        f"- positiveOverallOfflineToolchainReady: {str(s['positiveOverallOfflineToolchainReady']).lower()}",
        f"- positiveOverallTrueDeviceRegressionReady: {str(s['positiveOverallTrueDeviceRegressionReady']).lower()}",
        f"- positiveOverallRealActionNetworkAllowed: {str(s['positiveOverallRealActionNetworkAllowed']).lower()}",
        f"- positiveOverallRealActionSendReady: {str(s['positiveOverallRealActionSendReady']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## 证明范围",
        "",
        "这个报告只证明工具链的阳性路径：当未来真机采集补齐 1520030/1522030 native wrapper 且 lx/key/lb 分割可证时，动作 gate 能进入 dry-run evidence ready。",
        "它不证明真实刷黄已完成，也不会打开真实动作发送。",
        "",
        "## Native Wrapper Fixture Summary",
        "",
        f"- captureCount: {wrapper_summary['captureCount']}",
        f"- uniqueGameHexCount: {wrapper_summary['uniqueGameHexCount']}",
        f"- brushYellowWrapperCoverageComplete: {str(wrapper_summary['brushYellowWrapperCoverage']['complete']).lower()}",
        f"- brushYellowWrapperSplitProvenForBothStages: {str(wrapper_summary['brushYellowWrapperDetails']['splitProvenForBothStages']).lower()}",
        f"- nativeWrapperFieldAuditReady: {str(wrapper_summary.get('nativeWrapperFieldAudit', {}).get('readyForDryRunWrapperPlan', False)).lower()}",
        f"- networkSendAllowed: {str(wrapper_summary['networkSendAllowed']).lower()}",
        f"- actionSendReady: {str(wrapper_summary['actionSendReady']).lower()}",
        "",
        "## Action Gate Fixture Summary",
        "",
        f"- dryRunActionEvidenceReady: {str(gate['dryRunActionEvidenceReady']).lower()}",
        f"- realActionSendReady: {str(gate['realActionSendReady']).lower()}",
        f"- realActionNetworkAllowed: {str(gate['realActionNetworkAllowed']).lower()}",
        f"- readinessLevel: {gate['readinessLevel']}",
        "",
        "## Overall Fixture Summary",
        "",
        f"- offlineToolchainReady: {str(overall_summary['offlineToolchainReady']).lower()}",
        f"- dryRunActionEvidenceReady: {str(overall_summary['dryRunActionEvidenceReady']).lower()}",
        f"- preflightReady: {str(overall_summary['preflightReady']).lower()}",
        f"- authorizedDeviceCount: {overall_summary['authorizedDeviceCount']}",
        f"- migrationObjectiveComplete: {str(overall_summary['migrationObjectiveComplete']).lower()}",
        f"- trueDeviceRegressionReady: {str(overall_summary['trueDeviceRegressionReady']).lower()}",
        "",
        "## Overall fixture missing live/device evidence",
        "",
        "```json",
        json.dumps(report["positiveOverallReadiness"].get("missingLive", []), ensure_ascii=False, indent=2),
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-full-report", default=str(ROOT / "reports" / "full_offline_replay_report.json"))
    ap.add_argument("--out", help="Write JSON evidence")
    ap.add_argument("--markdown-out", help="Write Markdown evidence")
    ap.add_argument("--fixture-log-out", help="Write the deterministic fixture log")
    ns = ap.parse_args()
    report = build_evidence(Path(ns.base_full_report))
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")
    if ns.fixture_log_out:
        Path(ns.fixture_log_out).write_text(report["fixtureLog"], encoding="utf-8")


if __name__ == "__main__":
    main()
