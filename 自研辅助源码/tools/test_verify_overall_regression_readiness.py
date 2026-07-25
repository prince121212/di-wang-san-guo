#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("verify_overall_regression_readiness.py")
spec = importlib.util.spec_from_file_location("verify_overall_regression_readiness", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["verify_overall_regression_readiness"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]
FIXTURE_SCRIPT = Path(__file__).with_name("generate_native_wrapper_positive_fixture.py")
fixture_spec = importlib.util.spec_from_file_location("generate_native_wrapper_positive_fixture", FIXTURE_SCRIPT)
fixture_mod = importlib.util.module_from_spec(fixture_spec)
sys.modules["generate_native_wrapper_positive_fixture"] = fixture_mod
fixture_spec.loader.exec_module(fixture_mod)  # type: ignore[union-attr]
ROOT = SCRIPT.parent.parent


class VerifyOverallRegressionReadinessTest(unittest.TestCase):
    def test_current_worktree_is_offline_ready_but_not_true_device_ready(self):
        report = mod.audit(ROOT)
        self.assertTrue(report["summary"]["fullOfflineReplayReady"])
        self.assertTrue(report["summary"]["roleResourceParseReady"])
        self.assertTrue(report["summary"]["generalEvidenceParseReady"])
        self.assertTrue(report["summary"]["dailyProtocolEvidenceReady"])
        self.assertTrue(report["summary"]["dailyFullRecoveredOrderReady"])
        self.assertTrue(report["summary"]["mineReadOnlyEvidenceReady"])
        self.assertTrue(report["summary"]["mineSelectionEvidenceReady"])
        self.assertTrue(report["summary"]["remainingActionDryRunEvidenceReady"])
        self.assertTrue(report["summary"]["actionSafetyInvariantReady"])
        self.assertFalse(report["summary"]["trueDeviceRegressionReady"])
        self.assertFalse(report["summary"]["realActionNetworkAllowed"])
        self.assertIn("authorizedDeviceCount=0", report["missingLive"])


    def test_positive_native_wrapper_fixture_sets_dry_run_but_not_true_device_ready(self):
        with tempfile.TemporaryDirectory() as td:
            base_full = json.loads((ROOT / "reports" / "full_offline_replay_report.json").read_text(encoding="utf-8"))
            positive_full = fixture_mod.build_positive_full_report(base_full)
            fixture_root = fixture_mod.write_fixture_overall_root(Path(td), positive_full)

            report = mod.audit(fixture_root)

            self.assertTrue(report["summary"]["offlineToolchainReady"])
            self.assertTrue(report["summary"]["remainingActionDryRunEvidenceReady"])
            self.assertTrue(report["summary"]["dryRunActionEvidenceReady"])
            self.assertFalse(report["summary"]["trueDeviceRegressionReady"])
            self.assertFalse(report["summary"]["realActionNetworkAllowed"])
            self.assertFalse(report["summary"]["realActionSendReady"])
            self.assertIn("preflightReady=false", report["missingLive"])
            self.assertIn("authorizedDeviceCount=0", report["missingLive"])
            self.assertIn("migration objectiveComplete=false", report["missingLive"])
            self.assertNotIn("dryRunActionEvidenceReady=false/native wrapper capture evidence missing", report["missingLive"])

    def test_markdown_contains_live_and_offline_sections(self):
        md = mod.to_markdown(mod.audit(ROOT))
        self.assertIn("整体回归 Readiness 统一审计", md)
        self.assertIn("Missing live/device evidence", md)
        self.assertIn("offlineToolchainReady", md)

    def test_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "overall.json"
            md = Path(td) / "overall.md"
            subprocess.check_call([sys.executable, str(SCRIPT), "--root", str(ROOT), "--out", str(out), "--markdown-out", str(md)])
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(data["summary"]["trueDeviceRegressionReady"])
            self.assertIn("整体回归 Readiness", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
