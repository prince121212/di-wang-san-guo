#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("promote_device_regression_capture.py")
spec = importlib.util.spec_from_file_location("promote_device_regression_capture", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["promote_device_regression_capture"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


def write_project_shell(root: Path) -> None:
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (root / "app" / "build" / "outputs" / "apk" / "debug").mkdir(parents=True, exist_ok=True)
    (root / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk").write_bytes(b"apk")
    (root.parent / "小黄点辅助.apk").write_bytes(b"xh")
    (root.parent / "三国·帝王联盟1.66.apk").write_bytes(b"game")
    frida = root.parent / "reverse_cases" / "apk" / "scripts"
    frida.mkdir(parents=True, exist_ok=True)
    (frida / "frida_native_session_trace_v2.js").write_text("// frida\n", encoding="utf-8")
    (reports / "action_safety_invariants.json").write_text(json.dumps({"summary": {"actionSafetyInvariantReady": True, "realActionNetworkAllowed": False}}, ensure_ascii=False), encoding="utf-8")
    (reports / "migration_goal_status.json").write_text(json.dumps({"summary": {"objectiveComplete": False, "realActionNetworkAllowed": False}}, ensure_ascii=False), encoding="utf-8")


def write_capture(root: Path, complete: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if complete:
        for name in ["frida.log", "logcat.txt", "device_combined.log", "capture_summary.md", "adb_devices.txt"]:
            (root / name).write_text("sample\n", encoding="utf-8")
        (root / "preflight.json").write_text(json.dumps({
            "summary": {"preflightReady": True, "authorizedDeviceCount": 1, "realActionNetworkAllowed": False},
            "missing": [],
        }, ensure_ascii=False), encoding="utf-8")
        (root / "preflight.md").write_text("# preflight\n", encoding="utf-8")
        (root / "capture_operator_guide.md").write_text("# guide\n", encoding="utf-8")
        (root / "capture_scenario_check.json").write_text(json.dumps({
            "summary": {"captureScenarioRequiredReady": True, "captureScenarioRecommendedReady": True},
            "missingRequired": [],
            "missingRecommended": [],
        }, ensure_ascii=False), encoding="utf-8")
        (root / "capture_scenario_check.md").write_text("# scenarios\n", encoding="utf-8")
        (root / "self_lifecycle_logcat_check.json").write_text(json.dumps({
            "summary": {
                "selfLifecycleLogcatReady": True,
                "markerRecordCount": 2,
                "taskStopCount": 1,
                "sessionLogoutCount": 1,
                "unsafeRecordCount": 0,
                "realActionNetworkAllowed": False,
            },
            "missing": [],
        }, ensure_ascii=False), encoding="utf-8")
        (root / "self_lifecycle_logcat_check.md").write_text("# self lifecycle\n", encoding="utf-8")
        (root / "shuahuang_minimum_goal_check.json").write_text(json.dumps({
            "summary": {
                "shuaHuangMinimumLiveEvidenceReady": True,
                "shuaHuangMinimumFinalReady": False,
                "realActionNetworkAllowed": False,
                "realActionSendReady": False,
            },
            "missing": [],
        }, ensure_ascii=False), encoding="utf-8")
        (root / "shuahuang_minimum_goal_check.md").write_text("# shuahuang minimum\n", encoding="utf-8")
    reg = root / "regression"
    reg.mkdir(parents=True, exist_ok=True)
    full = {
        "summary": {
            "fullOfflineReplayReady": True,
            "shuaHuangOfflineClosedLoopReplayReady": True,
            "dailyOfflineClosedLoopReplayReady": True,
            "mineOfflineClosedLoopReplayReady": True,
            "dryRunActionEvidenceReady": True,
            "realActionNetworkAllowed": False,
            "realActionSendReady": False,
        },
        "actionGateAudit": {"summary": {"dryRunActionEvidenceReady": True, "realActionSendReady": False}},
    }
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
    native_wrapper = {
        "summary": {
            "brushYellowWrapperCoverage": {"prepare1520030": 1, "dispatch1522030": 1, "complete": True},
            "brushYellowWrapperDetails": {
                "complete": True,
                "splitProvenForBothStages": True,
                "prepare1520030": {"count": 1, "splitProven": True},
                "dispatch1522030": {"count": 1, "splitProven": True},
            },
        }
    }
    (reg / "device_regression_report.json").write_text(json.dumps({"summary": summary, "nativeWrapperCalibration": native_wrapper}, ensure_ascii=False), encoding="utf-8")
    (reg / "full_offline_replay.json").write_text(json.dumps(full, ensure_ascii=False), encoding="utf-8")
    (reg / "full_offline_replay.md").write_text("# full\n", encoding="utf-8")
    (reg / "action_gate_readiness.json").write_text(json.dumps({
        "summary": {"realActionSendReady": False, "dryRunActionEvidenceReady": True},
        "missing": [],
        "evidence": {"nativeWrapper": {"brushYellowWrapperDetails": native_wrapper["summary"]["brushYellowWrapperDetails"]}},
    }, ensure_ascii=False), encoding="utf-8")
    (reg / "replay_contract.json").write_text(json.dumps({"evidence": {"unsafeTrueFlags": []}}, ensure_ascii=False), encoding="utf-8")
    for name in mod.artifact_verifier.REGRESSION_REQUIRED:
        path = reg / name
        if not path.exists():
            path.write_text("{}\n" if name.endswith(".json") else "# report\n", encoding="utf-8")
    if not complete:
        (root / "preflight.json").write_text(json.dumps({"summary": {"preflightReady": False, "authorizedDeviceCount": 0, "realActionNetworkAllowed": False}, "missing": ["authorized adb device"]}, ensure_ascii=False), encoding="utf-8")
        (root / "preflight.md").write_text("# preflight false\n", encoding="utf-8")
    return root


class PromoteDeviceRegressionCaptureTest(unittest.TestCase):
    def test_latest_reports_written_without_canonical_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "自研辅助源码"
            write_project_shell(project)
            capture = write_capture(Path(td) / "capture")
            report = mod.promote(capture, project / "reports")

            self.assertTrue(report["summary"]["latestReportsWritten"])
            self.assertFalse(report["summary"]["canonicalPromoted"])
            self.assertTrue(report["summary"]["trueDeviceRegressionEvidenceReady"])
            self.assertTrue((project / "reports" / "latest_device_regression_artifact_check.json").exists())
            self.assertTrue((project / "reports" / "latest_device_full_offline_replay.json").exists())
            self.assertTrue((project / "reports" / "latest_device_shuahuang_minimum_goal_check.json").exists())
            self.assertTrue((project / "reports" / "latest_device_self_lifecycle_logcat_check.json").exists())
            self.assertFalse((project / "reports" / "full_offline_replay_report.json").exists())

    def test_canonical_promotion_requires_complete_artifact_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "自研辅助源码"
            write_project_shell(project)
            capture = write_capture(Path(td) / "capture", complete=False)
            report = mod.promote(capture, project / "reports", promote_canonical=True)

            self.assertFalse(report["summary"]["trueDeviceRegressionEvidenceReady"])
            self.assertFalse(report["summary"]["canonicalPromoted"])
            self.assertIn("canonical promotion refused", report["summary"]["canonicalBlocker"])
            self.assertFalse((project / "reports" / "full_offline_replay_report.json").exists())

    def test_complete_capture_can_promote_canonical_but_overall_goal_still_false(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "自研辅助源码"
            write_project_shell(project)
            capture = write_capture(Path(td) / "capture")
            report = mod.promote(capture, project / "reports", promote_canonical=True)

            self.assertTrue(report["summary"]["canonicalPromoted"])
            self.assertTrue((project / "reports" / "full_offline_replay_report.json").exists())
            self.assertTrue((project / "reports" / "device_regression_preflight.json").exists())
            self.assertTrue((project / "reports" / "device_shuahuang_minimum_goal_check.json").exists())
            self.assertTrue((project / "reports" / "device_self_lifecycle_logcat_check.json").exists())
            self.assertTrue(report["summary"]["overallDryRunActionEvidenceReadyAfterPromotion"])
            self.assertFalse(report["summary"]["overallTrueDeviceRegressionReadyAfterPromotion"])
            self.assertFalse(report["summary"]["realActionNetworkAllowed"])

    def test_cli_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "自研辅助源码"
            write_project_shell(project)
            capture = write_capture(Path(td) / "capture")
            out = Path(td) / "promotion.json"
            md = Path(td) / "promotion.md"
            subprocess.check_call([
                sys.executable, str(SCRIPT), str(capture),
                "--reports-dir", str(project / "reports"),
                "--out", str(out),
                "--markdown-out", str(md),
            ])
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(data["summary"]["trueDeviceRegressionEvidenceReady"])
            self.assertIn("设备回归采集产物导入报告", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
