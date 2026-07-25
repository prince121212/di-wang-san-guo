#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("generate_native_wrapper_positive_fixture.py")
spec = importlib.util.spec_from_file_location("generate_native_wrapper_positive_fixture", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["generate_native_wrapper_positive_fixture"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]
ROOT = SCRIPT.parent.parent


class GenerateNativeWrapperPositiveFixtureTest(unittest.TestCase):
    def test_builds_positive_dry_run_fixture_without_true_device_ready(self) -> None:
        report = mod.build_evidence(ROOT / "reports" / "full_offline_replay_report.json")
        summary = report["summary"]
        self.assertTrue(summary["positiveActionGateDryRunReady"])
        self.assertTrue(summary["positiveOverallDryRunReady"])
        self.assertTrue(summary["positiveOverallOfflineToolchainReady"])
        self.assertFalse(summary["positiveOverallTrueDeviceRegressionReady"])
        self.assertFalse(summary["positiveOverallRealActionNetworkAllowed"])
        self.assertFalse(summary["positiveOverallRealActionSendReady"])
        wrapper = report["nativeWrapperCalibration"]["summary"]
        self.assertTrue(wrapper["brushYellowWrapperCoverage"]["complete"])
        self.assertTrue(wrapper["brushYellowWrapperDetails"]["splitProvenForBothStages"])
        self.assertFalse(wrapper["networkSendAllowed"])
        self.assertIn("preflightReady=false", report["positiveOverallReadiness"]["missingLive"])
        self.assertIn("authorizedDeviceCount=0", report["positiveOverallReadiness"]["missingLive"])
        self.assertIn("migration objectiveComplete=false", report["positiveOverallReadiness"]["missingLive"])

    def test_cli_writes_evidence_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "fixture.json"
            md = Path(td) / "fixture.md"
            log = Path(td) / "fixture.log"
            subprocess.check_call([
                sys.executable, str(SCRIPT),
                "--base-full-report", str(ROOT / "reports" / "full_offline_replay_report.json"),
                "--out", str(out),
                "--markdown-out", str(md),
                "--fixture-log-out", str(log),
            ])
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(data["summary"]["positiveActionGateDryRunReady"])
            self.assertFalse(data["summary"]["positiveOverallTrueDeviceRegressionReady"])
            self.assertIn("Native Wrapper 阳性 Fixture", md.read_text(encoding="utf-8"))
            self.assertIn("1520030", log.read_text(encoding="utf-8"))
            self.assertIn("1522030", log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
