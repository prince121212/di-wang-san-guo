#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("package_device_regression_evidence.py")
spec = importlib.util.spec_from_file_location("package_device_regression_evidence", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["package_device_regression_evidence"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


def write_reports_shell(root: Path) -> Path:
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (root / "app" / "build" / "outputs" / "apk" / "debug").mkdir(parents=True, exist_ok=True)
    (root / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk").write_bytes(b"apk")
    (root.parent / "小黄点辅助.apk").write_bytes(b"xh")
    (root.parent / "三国·帝王联盟1.66.apk").write_bytes(b"game")
    frida = root.parent / "reverse_cases" / "apk" / "scripts"
    frida.mkdir(parents=True, exist_ok=True)
    (frida / "frida_native_session_trace_v2.js").write_text("// frida\n", encoding="utf-8")
    for name in mod.CURRENT_REPORTS:
        (reports / name).write_text("{}\n" if name.endswith(".json") else "# report\n", encoding="utf-8")
    (reports / "overall_regression_readiness.json").write_text(json.dumps({"summary": {"trueDeviceRegressionReady": False, "realActionNetworkAllowed": False}}, ensure_ascii=False), encoding="utf-8")
    return reports


def write_capture(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name in ["frida.log", "logcat.txt", "device_combined.log", "capture_summary.md", "adb_devices.txt"]:
        (root / name).write_text("sample\n", encoding="utf-8")
    (root / "preflight.json").write_text(json.dumps({"summary": {"preflightReady": True, "authorizedDeviceCount": 1, "realActionNetworkAllowed": False}, "missing": []}, ensure_ascii=False), encoding="utf-8")
    (root / "preflight.md").write_text("# preflight\n", encoding="utf-8")
    (root / "capture_operator_guide.md").write_text("# guide\n", encoding="utf-8")
    (root / "capture_scenario_check.json").write_text(json.dumps({"summary": {"captureScenarioRequiredReady": True, "captureScenarioRecommendedReady": True}, "missingRequired": [], "missingRecommended": []}, ensure_ascii=False), encoding="utf-8")
    (root / "capture_scenario_check.md").write_text("# scenarios\n", encoding="utf-8")
    (root / "self_lifecycle_logcat_check.json").write_text(json.dumps({"summary": {"selfLifecycleLogcatReady": True, "taskStopCount": 1, "sessionLogoutCount": 1, "realActionNetworkAllowed": False}, "missing": []}, ensure_ascii=False), encoding="utf-8")
    (root / "self_lifecycle_logcat_check.md").write_text("# self lifecycle\n", encoding="utf-8")
    (root / "shuahuang_minimum_goal_check.json").write_text(json.dumps({"summary": {"shuaHuangMinimumLiveEvidenceReady": True, "shuaHuangMinimumFinalReady": False}}, ensure_ascii=False), encoding="utf-8")
    (root / "shuahuang_minimum_goal_check.md").write_text("# shuahuang minimum\n", encoding="utf-8")
    reg = root / "regression"
    reg.mkdir(parents=True, exist_ok=True)
    summary = {
        "shuaHuangOfflineReplayReady": True,
        "shuaHuangOfflineClosedLoopReplayReady": True,
        "dailyOfflineReplayReady": True,
        "dailyOfflineClosedLoopReplayReady": True,
        "mineOfflineReplayReady": True,
        "mineOfflineClosedLoopReplayReady": True,
        "fullOfflineReplayReady": True,
        "dryRunActionEvidenceReady": True,
        "realActionNetworkAllowed": False,
    }
    native_wrapper = {"summary": {"brushYellowWrapperCoverage": {"prepare1520030": 1, "dispatch1522030": 1, "complete": True}, "brushYellowWrapperDetails": {"complete": True, "splitProvenForBothStages": True}}}
    (reg / "device_regression_report.json").write_text(json.dumps({
        "summary": summary,
        "nativeWrapperCalibration": native_wrapper,
        "mergedChannelExtra": {
            "nativeWrapperKey": "SECRET_NATIVE_KEY",
            "nativeWrapperLx": "SECRET_LX",
            "nativeWrapperLb": "SECRET_LB",
        }
    }, ensure_ascii=False), encoding="utf-8")
    (reg / "merged_channel_extra.json").write_text(json.dumps({
        "nativeWrapperKey": "SECRET_NATIVE_KEY",
        "nativeWrapperLx": "SECRET_LX",
        "nativeWrapperLb": "SECRET_LB",
        "tokenCiphertext": "SECRET_TOKEN",
    }, ensure_ascii=False), encoding="utf-8")
    (reg / "replay_contract.json").write_text(json.dumps({"evidence": {"unsafeTrueFlags": []}}, ensure_ascii=False), encoding="utf-8")
    (reg / "action_gate_readiness.json").write_text(json.dumps({"summary": {"realActionSendReady": False}, "missing": [], "evidence": {"nativeWrapper": {"brushYellowWrapperDetails": native_wrapper["summary"]["brushYellowWrapperDetails"]}}}, ensure_ascii=False), encoding="utf-8")
    for name in mod.artifact_verifier.REGRESSION_REQUIRED:
        path = reg / name
        if not path.exists():
            path.write_text("{}\n" if name.endswith(".json") else "# report\n", encoding="utf-8")
    return root


class PackageDeviceRegressionEvidenceTest(unittest.TestCase):
    def test_packages_current_reports_without_capture(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "自研辅助源码"
            reports = write_reports_shell(project)
            out = Path(td) / "evidence.zip"
            report = mod.package(None, out, reports)
            self.assertTrue(out.exists())
            self.assertFalse(report["summary"]["includeRawLogs"])
            with zipfile.ZipFile(out) as zf:
                names = set(zf.namelist())
                self.assertIn("manifest.json", names)
                self.assertIn("SUMMARY.md", names)
                self.assertIn("current_reports/migration_goal_status.md", names)
                self.assertIn("current_reports/device_capture_operator_guide_latest.md", names)
                self.assertIn("current_reports/device_capture_operator_guide_unified_evidence.md", names)
                self.assertIn("current_reports/replay_contract_report.md", names)
                self.assertIn("current_reports/role_resource_general_parse_gate_evidence.md", names)
                self.assertIn("current_reports/configured_target_selection_gate_evidence.md", names)
                self.assertIn("current_reports/brush_yellow_dispatch_payload_gate_evidence.md", names)
                self.assertIn("current_reports/daily_offline_replay_report.md", names)
                self.assertIn("current_reports/daily_protocol_gate_evidence.md", names)
                self.assertIn("current_reports/mine_offline_replay_report.md", names)
                self.assertIn("current_reports/mine_readonly_selection_gate_evidence.md", names)
                self.assertIn("current_reports/remaining_action_dryrun_payload_gate_evidence.md", names)
                self.assertIn("current_reports/shuahuang_minimum_closed_loop_acceptance.md", names)
                self.assertIn("current_reports/shuahuang_capture_gate_tightening_evidence.md", names)
                self.assertIn("current_reports/shuahuang_minimum_goal_gate_evidence.md", names)
                self.assertIn("current_reports/shuahuang_minimum_goal_artifact_gate_evidence.md", names)
                self.assertIn("current_reports/device_pipeline_shuahuang_gate_summary_evidence.md", names)
                self.assertIn("current_reports/shuahuang_stop_logout_live_gate_evidence.md", names)
                self.assertIn("current_reports/self_lifecycle_logcat_marker_evidence.md", names)
                self.assertIn("current_reports/self_lifecycle_artifact_gate_evidence.md", names)
                self.assertIn("current_reports/preflight_self_game_package_gate_evidence.md", names)
                self.assertIn("current_reports/preflight_self_apk_freshness_gate_evidence.md", names)
                self.assertIn("current_reports/preflight_self_apk_marker_gate_evidence.md", names)
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                self.assertFalse(manifest["realActionNetworkAllowed"])

    def test_capture_package_excludes_raw_logs_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "自研辅助源码"
            reports = write_reports_shell(project)
            capture = write_capture(Path(td) / "capture")
            out = Path(td) / "evidence.zip"
            report = mod.package(capture, out, reports)
            self.assertTrue(report["summary"]["artifactTrueDeviceRegressionEvidenceReady"])
            with zipfile.ZipFile(out) as zf:
                names = set(zf.namelist())
                self.assertIn("generated/artifact_verification.json", names)
                self.assertIn("capture/regression/device_regression_report.json", names)
                self.assertIn("capture/shuahuang_minimum_goal_check.md", names)
                self.assertIn("capture/self_lifecycle_logcat_check.md", names)
                self.assertNotIn("capture/frida.log", names)
                self.assertNotIn("capture/logcat.txt", names)
                report_json = zf.read("capture/regression/device_regression_report.json").decode("utf-8")
                merged_json = zf.read("capture/regression/merged_channel_extra.json").decode("utf-8")
                self.assertNotIn("SECRET_NATIVE_KEY", report_json)
                self.assertNotIn("SECRET_NATIVE_KEY", merged_json)
                self.assertIn("<redacted>", report_json)
                self.assertIn("<redacted>", merged_json)
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                self.assertFalse(manifest["includeRawLogs"])
                self.assertFalse(manifest["includeSensitiveValues"])
                self.assertTrue(all("sha256" in item for item in manifest["entries"]))

    def test_capture_package_can_include_raw_logs_explicitly_and_cli_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "自研辅助源码"
            reports = write_reports_shell(project)
            capture = write_capture(Path(td) / "capture")
            out = Path(td) / "evidence.zip"
            summary = Path(td) / "summary.json"
            subprocess.check_call([
                sys.executable, str(SCRIPT), str(capture),
                "--reports-dir", str(reports),
                "--out", str(out),
                "--summary-out", str(summary),
                "--include-raw-logs",
            ])
            data = json.loads(summary.read_text(encoding="utf-8"))
            self.assertTrue(data["summary"]["includeRawLogs"])
            self.assertFalse(data["summary"]["includeSensitiveValues"])
            with zipfile.ZipFile(out) as zf:
                names = set(zf.namelist())
                self.assertIn("capture/frida.log", names)
                self.assertIn("capture/device_combined.log", names)

    def test_sensitive_values_can_be_included_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "自研辅助源码"
            reports = write_reports_shell(project)
            capture = write_capture(Path(td) / "capture")
            out = Path(td) / "evidence.zip"
            report = mod.package(capture, out, reports, include_sensitive_values=True)
            self.assertTrue(report["summary"]["includeSensitiveValues"])
            with zipfile.ZipFile(out) as zf:
                merged_json = zf.read("capture/regression/merged_channel_extra.json").decode("utf-8")
                self.assertIn("SECRET_NATIVE_KEY", merged_json)
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                self.assertTrue(manifest["includeSensitiveValues"])


if __name__ == "__main__":
    unittest.main()
