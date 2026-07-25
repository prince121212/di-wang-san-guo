#!/usr/bin/env python3
"""Offline device regression aggregator for the DWPM migration.

Consumes copied device/Frida/logcat text and runs all calibration parsers together:
- native/session trace importer
- native wrapper stability calibration
- 041540/041542 read-only response calibration
- 1520030/1522030 action response calibration
- one-click daily response calibration
- offline replay contract verification
- offline brush-yellow closed-loop replay
- offline one-click daily flow replay
- offline mine-search flow replay
- action gate readiness audit
- unified full offline replay suite
- raw capture scenario coverage audit

It never connects to a device or server. It is a repeatable report generator for later
真机回归 evidence.
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


native_importer = load_tool("import_native_session_trace")
native_wrapper = load_tool("calibrate_native_wrapper_trace")
readonly = load_tool("calibrate_readonly_responses")
action = load_tool("calibrate_action_responses")
daily = load_tool("calibrate_daily_responses")
replay_contract = load_tool("verify_replay_contract")
shuahuang_replay = load_tool("replay_shuahuang_offline")
daily_replay = load_tool("replay_daily_offline")
mine_replay = load_tool("replay_mine_offline")
action_gate = load_tool("verify_action_gate_readiness")
full_replay = load_tool("replay_full_offline")
capture_scenarios = load_tool("verify_device_capture_scenarios")


def merge_channel_extra(*candidates: dict[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for candidate in candidates:
        for key, value in candidate.items():
            if value is None:
                continue
            text = str(value)
            if text == "":
                continue
            merged[key] = text
    merged["deviceRegressionImporter"] = "tools/device_regression_from_logs.py"
    merged["deviceRegressionNetworkSendAllowed"] = "false"
    return merged


def normalize_extra(extra: dict[str, Any] | None) -> dict[str, str]:
    if not extra:
        return {}
    return {str(k): str(v) for k, v in extra.items() if v is not None and str(v) != ""}


def int_extra(extra: dict[str, str], *keys: str, default: int = 0) -> int:
    for key in keys:
        value = extra.get(key)
        if value is None or str(value).strip() == "":
            continue
        try:
            return int(str(value), 10)
        except Exception:
            continue
    return default


def calibrate_all(
    text: str,
    include_values: bool = False,
    base_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    native_extra = native_importer.parse(text, include_raw_body=include_values)
    wrapper_report = native_wrapper.calibrate(text, include_values=include_values)
    readonly_report = readonly.calibrate(text)
    action_report = action.calibrate(text, base_extra=normalize_extra(base_extra))
    daily_report = daily.calibrate(text)
    scenario_report = capture_scenarios.verify_text(text)
    role_resource_from_log = replay_contract.recover_role_resource_from_text(text)
    if role_resource_from_log:
        role_resource_from_log.setdefault("roleResourceEvidenceSource", "device_combined_log")
    merged_extra = merge_channel_extra(
        role_resource_from_log,
        native_extra,
        wrapper_report.get("channelExtraCandidate", {}),
        readonly_report.get("channelExtraCandidate", {}),
        action_report.get("channelExtraCandidate", {}),
        daily_report.get("channelExtraCandidate", {}),
    )
    replay_extra = normalize_extra(base_extra)
    replay_extra.update(merged_extra)
    replay_report = replay_contract.verify(replay_extra)
    shuahuang_replay_report = shuahuang_replay.replay(
        replay_extra,
        target_type=str(replay_extra.get("shuaHuangTargetType") or replay_extra.get("targetType") or "HUANG_JIN"),
        start_x=int_extra(replay_extra, "shuaHuangStartX", "startX"),
        start_y=int_extra(replay_extra, "shuaHuangStartY", "startY"),
    )
    daily_replay_report = daily_replay.replay(replay_extra)
    mine_replay_report = mine_replay.replay(
        replay_extra,
        start_x=int_extra(replay_extra, "mineStartX", "startX"),
        start_y=int_extra(replay_extra, "mineStartY", "startY"),
    )
    full_replay_report = full_replay.replay(
        replay_extra,
        target_type=str(replay_extra.get("shuaHuangTargetType") or replay_extra.get("targetType") or "HUANG_JIN"),
        start_x=int_extra(replay_extra, "shuaHuangStartX", "startX", default=11),
        start_y=int_extra(replay_extra, "shuaHuangStartY", "startY", default=22),
    )
    summary = {
        "nativeTraceHasMethods": bool(native_extra.get("nativeTraceMethods")),
        "nativeWrapperCaptureCount": wrapper_report["summary"]["captureCount"],
        "nativeWrapperUniqueGameHexCount": wrapper_report["summary"]["uniqueGameHexCount"],
        "nativeWrapperFieldAuditReady": wrapper_report["summary"].get("nativeWrapperFieldAudit", {}).get("readyForDryRunWrapperPlan", False),
        "brushYellowWrapperCoverageComplete": wrapper_report["summary"].get("brushYellowWrapperCoverage", {}).get("complete", False),
        "resourcePointWrapperCoverageComplete": wrapper_report["summary"].get("remainingActionWrapperDetails", {}).get("resourcePoint", {}).get("complete", False),
        "withdrawDefenseWrapperCoverageComplete": wrapper_report["summary"].get("remainingActionWrapperDetails", {}).get("withdrawDefense", {}).get("complete", False),
        "target041540CaptureCount": readonly_report["summary"]["target041540CaptureCount"],
        "targetParsedCount": readonly_report["summary"]["targetParsedCount"],
        "resource041542CaptureCount": readonly_report["summary"]["resource041542CaptureCount"],
        "mineParsedCount": readonly_report["summary"]["mineParsedCount"],
        "actionCaptureCount": action_report["summary"]["captureCount"],
        "dispatchResultCount": action_report["summary"]["dispatchResultCount"],
        "dispatchResultInferredFormationCount": action_report["summary"].get("dispatchResultInferredFormationCount", 0),
        "dailyCaptureCount": daily_report["summary"]["captureCount"],
        "dailyStepResultCount": daily_report["summary"]["dailyStepResultCount"],
        "captureScenarioRequiredReady": scenario_report["summary"]["captureScenarioRequiredReady"],
        "captureScenarioRecommendedReady": scenario_report["summary"]["captureScenarioRecommendedReady"],
        "loginState8004RequiredOk": scenario_report["scenarios"].get("loginState8004", {}).get("requiredOk", False),
        "loginState8004RecommendedOk": scenario_report["scenarios"].get("loginState8004", {}).get("recommendedOk", False),
        "loginState8004RoleResourceRecovered": bool(role_resource_from_log.get("roleName") or role_resource_from_log.get("copper")),
        "offlineReplayReady": bool(
            readonly_report["summary"]["targetParsedCount"] > 0 and
            action_report["summary"]["dispatchResultCount"] > 0
        ),
        "shuaHuangOfflineReplayReady": replay_report["summary"]["shuaHuangOfflineReplayReady"],
        "shuaHuangOfflineClosedLoopReplayReady": shuahuang_replay_report["summary"]["shuaHuangOfflineClosedLoopReplayReady"],
        "roleResourceParseReady": replay_report["summary"].get("roleResourceParseReady", False),
        "generalEvidenceParseReady": replay_report["summary"].get("generalEvidenceParseReady", False),
        "state8004GeneralEvidenceReady": replay_report["summary"].get("state8004GeneralEvidenceReady", False),
        "dailyOfflineReplayReady": replay_report["summary"]["dailyOfflineReplayReady"],
        "dailyOfflineClosedLoopReplayReady": daily_replay_report["summary"]["dailyOfflineClosedLoopReplayReady"],
        "dailyProtocolEvidenceReady": daily_replay_report["summary"].get("dailyProtocolEvidenceReady", False),
        "dailyFullRecoveredOrderReady": daily_replay_report["summary"].get("fullRecoveredOrder", False),
        "mineOfflineReplayReady": replay_report["summary"]["mineOfflineReplayReady"],
        "mineOfflineClosedLoopReplayReady": mine_replay_report["summary"]["mineOfflineClosedLoopReplayReady"],
        "mineReadOnlyEvidenceReady": mine_replay_report["summary"].get("mineReadOnlyEvidenceReady", False),
        "mineSelectionEvidenceReady": mine_replay_report["summary"].get("mineSelectionEvidenceReady", False),
        "fullOfflineReplayReady": full_replay_report["summary"]["fullOfflineReplayReady"],
        "dryRunActionEvidenceReady": False,
        "realActionNetworkAllowed": False,
        "blocker": "offline regression report only; true game action send and full device regression still require user-controlled live gate and isolated device validation",
    }
    report = {
        "summary": summary,
        "mergedChannelExtra": merged_extra,
        "nativeTrace": native_extra,
        "nativeWrapperCalibration": wrapper_report,
        "readOnlyResponseCalibration": readonly_report,
        "actionResponseCalibration": action_report,
        "dailyResponseCalibration": daily_report,
        "captureScenarioCoverage": scenario_report,
        "replayContract": replay_report,
        "shuaHuangOfflineReplay": shuahuang_replay_report,
        "dailyOfflineReplay": daily_replay_report,
        "mineOfflineReplay": mine_replay_report,
        "fullOfflineReplay": full_replay_report,
    }
    gate_report = action_gate.audit(report)
    report["actionGateReadiness"] = gate_report
    report["summary"]["dryRunActionEvidenceReady"] = gate_report["summary"]["dryRunActionEvidenceReady"]
    return report


def write_outputs(report: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "device_regression_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "merged_channel_extra.json").write_text(json.dumps(report["mergedChannelExtra"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "native_wrapper_calibration.md").write_text(native_wrapper.to_markdown(report["nativeWrapperCalibration"]) + "\n", encoding="utf-8")
    (out_dir / "readonly_calibration.md").write_text(readonly.to_markdown(report["readOnlyResponseCalibration"]) + "\n", encoding="utf-8")
    (out_dir / "action_response_calibration.md").write_text(action.to_markdown(report["actionResponseCalibration"]) + "\n", encoding="utf-8")
    (out_dir / "daily_response_calibration.md").write_text(daily.to_markdown(report["dailyResponseCalibration"]) + "\n", encoding="utf-8")
    (out_dir / "capture_scenario_coverage.json").write_text(json.dumps(report["captureScenarioCoverage"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "capture_scenario_coverage.md").write_text(capture_scenarios.to_markdown(report["captureScenarioCoverage"]) + "\n", encoding="utf-8")
    (out_dir / "replay_contract.json").write_text(json.dumps(report["replayContract"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "replay_contract.md").write_text(replay_contract.to_markdown(report["replayContract"]) + "\n", encoding="utf-8")
    (out_dir / "shuahuang_offline_replay.json").write_text(json.dumps(report["shuaHuangOfflineReplay"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "shuahuang_offline_replay.md").write_text(shuahuang_replay.to_markdown(report["shuaHuangOfflineReplay"]) + "\n", encoding="utf-8")
    (out_dir / "daily_offline_replay.json").write_text(json.dumps(report["dailyOfflineReplay"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "daily_offline_replay.md").write_text(daily_replay.to_markdown(report["dailyOfflineReplay"]) + "\n", encoding="utf-8")
    (out_dir / "mine_offline_replay.json").write_text(json.dumps(report["mineOfflineReplay"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "mine_offline_replay.md").write_text(mine_replay.to_markdown(report["mineOfflineReplay"]) + "\n", encoding="utf-8")
    (out_dir / "action_gate_readiness.json").write_text(json.dumps(report["actionGateReadiness"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "action_gate_readiness.md").write_text(action_gate.to_markdown(report["actionGateReadiness"]) + "\n", encoding="utf-8")
    (out_dir / "full_offline_replay.json").write_text(json.dumps(report["fullOfflineReplay"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "full_offline_replay.md").write_text(full_replay.to_markdown(report["fullOfflineReplay"]) + "\n", encoding="utf-8")
    (out_dir / "summary.md").write_text(to_markdown(report) + "\n", encoding="utf-8")


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 设备日志离线回归汇总",
        "",
        "## Summary",
        "",
        f"- nativeTraceHasMethods: {str(s['nativeTraceHasMethods']).lower()}",
        f"- nativeWrapperCaptureCount: {s['nativeWrapperCaptureCount']}",
        f"- nativeWrapperUniqueGameHexCount: {s['nativeWrapperUniqueGameHexCount']}",
        f"- nativeWrapperFieldAuditReady: {str(s['nativeWrapperFieldAuditReady']).lower()}",
        f"- brushYellowWrapperCoverageComplete: {str(s['brushYellowWrapperCoverageComplete']).lower()}",
        f"- resourcePointWrapperCoverageComplete: {str(s['resourcePointWrapperCoverageComplete']).lower()}",
        f"- withdrawDefenseWrapperCoverageComplete: {str(s['withdrawDefenseWrapperCoverageComplete']).lower()}",
        f"- target041540CaptureCount: {s['target041540CaptureCount']}",
        f"- targetParsedCount: {s['targetParsedCount']}",
        f"- resource041542CaptureCount: {s['resource041542CaptureCount']}",
        f"- mineParsedCount: {s['mineParsedCount']}",
        f"- actionCaptureCount: {s['actionCaptureCount']}",
        f"- dispatchResultCount: {s['dispatchResultCount']}",
        f"- dispatchResultInferredFormationCount: {s.get('dispatchResultInferredFormationCount', 0)}",
        f"- dailyCaptureCount: {s['dailyCaptureCount']}",
        f"- dailyStepResultCount: {s['dailyStepResultCount']}",
        f"- captureScenarioRequiredReady: {str(s['captureScenarioRequiredReady']).lower()}",
        f"- captureScenarioRecommendedReady: {str(s['captureScenarioRecommendedReady']).lower()}",
        f"- loginState8004RequiredOk: {str(s['loginState8004RequiredOk']).lower()}",
        f"- loginState8004RecommendedOk: {str(s['loginState8004RecommendedOk']).lower()}",
        f"- loginState8004RoleResourceRecovered: {str(s['loginState8004RoleResourceRecovered']).lower()}",
        f"- offlineReplayReady: {str(s['offlineReplayReady']).lower()}",
        f"- shuaHuangOfflineReplayReady: {str(s['shuaHuangOfflineReplayReady']).lower()}",
        f"- shuaHuangOfflineClosedLoopReplayReady: {str(s['shuaHuangOfflineClosedLoopReplayReady']).lower()}",
        f"- roleResourceParseReady: {str(s.get('roleResourceParseReady', False)).lower()}",
        f"- generalEvidenceParseReady: {str(s.get('generalEvidenceParseReady', False)).lower()}",
        f"- state8004GeneralEvidenceReady: {str(s.get('state8004GeneralEvidenceReady', False)).lower()}",
        f"- dailyOfflineReplayReady: {str(s['dailyOfflineReplayReady']).lower()}",
        f"- dailyOfflineClosedLoopReplayReady: {str(s['dailyOfflineClosedLoopReplayReady']).lower()}",
        f"- dailyProtocolEvidenceReady: {str(s.get('dailyProtocolEvidenceReady', False)).lower()}",
        f"- dailyFullRecoveredOrderReady: {str(s.get('dailyFullRecoveredOrderReady', False)).lower()}",
        f"- mineOfflineReplayReady: {str(s['mineOfflineReplayReady']).lower()}",
        f"- mineOfflineClosedLoopReplayReady: {str(s['mineOfflineClosedLoopReplayReady']).lower()}",
        f"- mineReadOnlyEvidenceReady: {str(s.get('mineReadOnlyEvidenceReady', False)).lower()}",
        f"- mineSelectionEvidenceReady: {str(s.get('mineSelectionEvidenceReady', False)).lower()}",
        f"- fullOfflineReplayReady: {str(s['fullOfflineReplayReady']).lower()}",
        f"- dryRunActionEvidenceReady: {str(s['dryRunActionEvidenceReady']).lower()}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "说明：`offlineReplayReady` 是旧的“日志中有找黄+动作响应样本”宽松指标；"
        "`*OfflineReplayReady` 是 `verify_replay_contract.py` 的严格契约指标，"
        "要求身份、角色/资源、将领、编队、响应样本与安全 flag 同时满足。",
        "",
        "## Outputs",
        "",
        "- device_regression_report.json",
        "- merged_channel_extra.json",
        "- native_wrapper_calibration.md",
        "- readonly_calibration.md",
        "- action_response_calibration.md",
        "- daily_response_calibration.md",
        "- capture_scenario_coverage.json",
        "- capture_scenario_coverage.md",
        "- replay_contract.json",
        "- replay_contract.md",
        "- shuahuang_offline_replay.json",
        "- shuahuang_offline_replay.md",
        "- daily_offline_replay.json",
        "- daily_offline_replay.md",
        "- mine_offline_replay.json",
        "- mine_offline_replay.md",
        "- action_gate_readiness.json",
        "- action_gate_readiness.md",
        "- full_offline_replay.json",
        "- full_offline_replay.md",
        "",
        "## Replay contract missing",
        "",
        "```json",
        json.dumps(report["replayContract"]["missing"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Capture scenario missing required",
        "",
        "```json",
        json.dumps(report["captureScenarioCoverage"]["missingRequired"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Capture scenario next manual actions",
        "",
    ]
    lines.extend(f"- {item}" for item in report["captureScenarioCoverage"]["nextManualActions"])
    lines += [
        "",
        "## ShuaHuang offline replay missing steps",
        "",
        "```json",
        json.dumps(report["shuaHuangOfflineReplay"]["missingSteps"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Daily offline replay missing steps",
        "",
        "```json",
        json.dumps(report["dailyOfflineReplay"]["missingSteps"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Mine offline replay missing steps",
        "",
        "```json",
        json.dumps(report["mineOfflineReplay"]["missingSteps"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Action gate readiness missing hard evidence",
        "",
        "```json",
        json.dumps(report["actionGateReadiness"]["missing"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Merged channelExtra preview",
        "",
        "```json",
        json.dumps(report["mergedChannelExtra"], ensure_ascii=False, indent=2, sort_keys=True)[:4000],
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="Combined device/Frida/logcat text")
    ap.add_argument("--out-dir", help="Output directory; defaults to stdout JSON only")
    ap.add_argument("--base-channel-extra", help="Optional base channelExtra/session JSON merged before captured log candidates for replay contract verification")
    ap.add_argument("--include-values", action="store_true", help="Include raw wrapper body/prefix/suffix values in native calibration outputs")
    ns = ap.parse_args()
    text = Path(ns.input).read_text(encoding="utf-8", errors="replace")
    base_extra = None
    if ns.base_channel_extra:
        base_extra = replay_contract.load_json(Path(ns.base_channel_extra))
    report = calibrate_all(text, include_values=ns.include_values, base_extra=base_extra)
    if ns.out_dir:
        write_outputs(report, Path(ns.out_dir))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
