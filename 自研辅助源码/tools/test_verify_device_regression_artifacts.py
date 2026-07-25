#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("verify_device_regression_artifacts.py")
spec = importlib.util.spec_from_file_location("verify_device_regression_artifacts", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["verify_device_regression_artifacts"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class VerifyDeviceRegressionArtifactsTest(unittest.TestCase):
    def write_regression(self, root: Path, complete_capture: bool = True) -> Path:
        if complete_capture:
            for name in ["frida.log", "logcat.txt", "device_combined.log", "capture_summary.md", "adb_devices.txt"]:
                (root / name).write_text("sample\n", encoding="utf-8")
            (root / "preflight.json").write_text(json.dumps({
                "summary": {
                    "preflightReady": True,
                    "adbFound": True,
                    "fridaFound": True,
                    "fridaPsFound": True,
                    "fridaUsbChecked": True,
                    "fridaUsbOk": True,
                    "authorizedDeviceCount": 1,
                    "realActionNetworkAllowed": False,
                },
                "missing": [],
            }, ensure_ascii=False), encoding="utf-8")
            (root / "preflight.md").write_text("# preflight\n", encoding="utf-8")
            (root / "capture_operator_guide.md").write_text("# guide\n", encoding="utf-8")
            (root / "capture_scenario_check.json").write_text(json.dumps({"summary": {"captureScenarioRequiredReady": True, "captureScenarioRecommendedReady": True}, "missingRequired": [], "missingRecommended": []}, ensure_ascii=False), encoding="utf-8")
            (root / "capture_scenario_check.md").write_text("# scenario\n", encoding="utf-8")
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
        reg.mkdir(parents=True)
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
                "brushYellowWrapperCoverage": {
                    "prepare1520030": 1,
                    "dispatch1522030": 1,
                    "complete": True,
                },
                "brushYellowWrapperDetails": {
                    "complete": True,
                    "splitProvenForBothStages": True,
                    "prepare1520030": {
                        "count": 1,
                        "splitProven": True,
                        "prefixLength": {"stable": True, "uniqueCount": 1, "values": [5]},
                    },
                    "dispatch1522030": {
                        "count": 1,
                        "splitProven": True,
                        "prefixLength": {"stable": True, "uniqueCount": 1, "values": [5]},
                    },
                },
            }
        }
        (reg / "device_regression_report.json").write_text(json.dumps({"summary": summary, "nativeWrapperCalibration": native_wrapper}, ensure_ascii=False), encoding="utf-8")
        (reg / "replay_contract.json").write_text(json.dumps({"evidence": {"unsafeTrueFlags": []}}, ensure_ascii=False), encoding="utf-8")
        (reg / "action_gate_readiness.json").write_text(json.dumps({
            "summary": {
                "realActionSendReady": False,
                "brushYellowWrapperSplitProvenForBothStages": True,
            },
            "evidence": {"nativeWrapper": {"brushYellowWrapperDetails": native_wrapper["summary"]["brushYellowWrapperDetails"]}},
        }, ensure_ascii=False), encoding="utf-8")
        for name in mod.REGRESSION_REQUIRED:
            path = reg / name
            if not path.exists():
                path.write_text("{}\n" if name.endswith(".json") else "# report\n", encoding="utf-8")
        return reg

    def test_complete_artifacts_are_accepted_but_real_send_stays_false(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_regression(root)
            report = mod.verify(root)
            self.assertTrue(report["summary"]["offlineRegressionArtifactsComplete"])
            self.assertTrue(report["summary"]["captureArtifactsPresent"])
            self.assertTrue(report["summary"]["preflightPresent"])
            self.assertTrue(report["summary"]["preflightReady"])
            self.assertTrue(report["summary"]["captureScenarioRequiredReady"])
            self.assertTrue(report["summary"]["selfLifecycleLogcatReady"])
            self.assertTrue(report["summary"]["shuaHuangMinimumLiveEvidenceReady"])
            self.assertFalse(report["summary"]["shuaHuangMinimumFinalReady"])
            self.assertTrue(report["summary"]["trueDeviceRegressionEvidenceReady"])
            self.assertFalse(report["summary"]["realActionNetworkAllowed"])
            self.assertEqual([], report["safety"]["violations"])
            self.assertTrue(report["brushYellowWrapper"]["splitProvenForBothStages"])
            self.assertEqual(1, report["brushYellowWrapper"]["coverage"]["prepare1520030"])
            self.assertTrue(report["brushYellowWrapper"]["details"]["prepare1520030"]["splitProven"])

    def test_missing_files_and_safety_flags_are_reported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reg = self.write_regression(root, complete_capture=False)
            (reg / "mine_offline_replay.md").unlink()
            (reg / "device_regression_report.json").write_text(json.dumps({"summary": {"realActionNetworkAllowed": True}}, ensure_ascii=False), encoding="utf-8")
            report = mod.verify(reg)
            self.assertFalse(report["summary"]["offlineRegressionArtifactsComplete"])
            self.assertFalse(report["summary"]["captureArtifactsPresent"])
            self.assertIn("mine_offline_replay.md", report["missing"]["regressionFiles"])
            self.assertIn("capture_scenario_check.json", report["missing"]["captureFiles"])
            self.assertIn("self_lifecycle_logcat_check.json", report["missing"]["captureFiles"])
            self.assertIn("shuahuang_minimum_goal_check.json", report["missing"]["captureFiles"])
            self.assertIn("preflight.json", report["missing"]["captureFiles"])
            self.assertIn("summary.realActionNetworkAllowed=true", report["safety"]["violations"])

    def test_preflight_not_ready_blocks_true_device_regression_ready(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_regression(root)
            (root / "preflight.json").write_text(json.dumps({
                "summary": {
                    "preflightReady": False,
                    "authorizedDeviceCount": 0,
                    "realActionNetworkAllowed": False,
                },
                "missing": ["authorized adb device"],
            }, ensure_ascii=False), encoding="utf-8")
            report = mod.verify(root)
            self.assertTrue(report["summary"]["preflightPresent"])
            self.assertFalse(report["summary"]["preflightReady"])
            self.assertFalse(report["summary"]["trueDeviceRegressionEvidenceReady"])
            self.assertIn("preflight:not ready", report["missing"]["hardMissing"])
            self.assertIn("preflight missing:authorized adb device", report["missing"]["hardMissing"])

    def test_missing_capture_scenario_blocks_true_device_regression_ready(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_regression(root)
            (root / "capture_scenario_check.json").write_text(json.dumps({
                "summary": {"captureScenarioRequiredReady": False, "captureScenarioRecommendedReady": False},
                "missingRequired": ["brushYellowNativeWrapper1520"],
                "missingRecommended": []
            }, ensure_ascii=False), encoding="utf-8")
            report = mod.verify(root)
            self.assertFalse(report["summary"]["captureScenarioRequiredReady"])
            self.assertFalse(report["summary"]["trueDeviceRegressionEvidenceReady"])
            self.assertIn("missing capture scenario:brushYellowNativeWrapper1520", report["missing"]["hardMissing"])

    def test_missing_self_lifecycle_logcat_blocks_true_device_regression_ready(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_regression(root)
            (root / "self_lifecycle_logcat_check.json").write_text(json.dumps({
                "summary": {
                    "selfLifecycleLogcatReady": False,
                    "markerRecordCount": 1,
                    "taskStopCount": 1,
                    "sessionLogoutCount": 0,
                    "realActionNetworkAllowed": False,
                },
                "missing": ["self-lifecycle-json:event=session_logout"],
            }, ensure_ascii=False), encoding="utf-8")
            report = mod.verify(root)
            self.assertFalse(report["summary"]["selfLifecycleLogcatReady"])
            self.assertFalse(report["summary"]["trueDeviceRegressionEvidenceReady"])
            self.assertIn("self lifecycle logcat:not ready", report["missing"]["hardMissing"])
            self.assertIn("self lifecycle missing:self-lifecycle-json:event=session_logout", report["missing"]["hardMissing"])

    def test_missing_shuahuang_minimum_goal_blocks_true_device_regression_ready(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_regression(root)
            (root / "shuahuang_minimum_goal_check.json").write_text(json.dumps({
                "summary": {
                    "shuaHuangMinimumLiveEvidenceReady": False,
                    "shuaHuangMinimumFinalReady": False,
                },
                "missing": ["generalFormationBaseline"],
            }, ensure_ascii=False), encoding="utf-8")
            report = mod.verify(root)
            self.assertFalse(report["summary"]["shuaHuangMinimumLiveEvidenceReady"])
            self.assertFalse(report["summary"]["trueDeviceRegressionEvidenceReady"])
            self.assertIn("shuahuang minimum goal:not live-evidence ready", report["missing"]["hardMissing"])
            self.assertIn("shuahuang minimum goal missing:generalFormationBaseline", report["missing"]["hardMissing"])

    def test_action_gate_missing_items_are_hard_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reg = self.write_regression(root)
            (reg / "action_gate_readiness.json").write_text(json.dumps({
                "summary": {"realActionSendReady": False},
                "missing": ["nativeWrapper:brush-yellow 1520030+1522030 wrapper captures"]
            }, ensure_ascii=False), encoding="utf-8")
            report = mod.verify(root)
            self.assertIn(
                "action gate missing:nativeWrapper:brush-yellow 1520030+1522030 wrapper captures",
                report["missing"]["hardMissing"]
            )
            self.assertIn(
                "nativeWrapper:brush-yellow 1520030+1522030 wrapper captures",
                report["actionGateMissing"]
            )

    def test_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_regression(root)
            out = root / "artifact_check.json"
            md = root / "artifact_check.md"
            subprocess.check_call([sys.executable, str(SCRIPT), str(root), "--out", str(out), "--markdown-out", str(md)])
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(report["summary"]["offlineRegressionArtifactsComplete"])
            self.assertIn("brushYellowWrapper", report)
            self.assertIn("设备回归产物验收报告", md.read_text(encoding="utf-8"))
            self.assertIn("Brush yellow wrapper evidence", md.read_text(encoding="utf-8"))
            self.assertIn("ShuaHuang minimum goal", md.read_text(encoding="utf-8"))
            self.assertIn("Self lifecycle logcat", md.read_text(encoding="utf-8"))
            self.assertIn("Preflight", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
