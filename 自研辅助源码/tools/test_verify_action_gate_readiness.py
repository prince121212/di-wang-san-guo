#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("verify_action_gate_readiness.py")
spec = importlib.util.spec_from_file_location("verify_action_gate_readiness", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["verify_action_gate_readiness"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class VerifyActionGateReadinessTest(unittest.TestCase):
    def report(self):
        stable = {"stable": True, "uniqueCount": 1, "values": [5]}
        return {
            "summary": {
                "targetParsedCount": 1,
                "dispatchResultCount": 1,
                "dailyStepResultCount": 1,
                "mineParsedCount": 1,
                "shuaHuangOfflineClosedLoopReplayReady": True,
                "dailyOfflineClosedLoopReplayReady": True,
                "mineOfflineClosedLoopReplayReady": True,
                "resourcePointActionPayloadEvidenceReady": True,
                "withdrawPayloadEvidenceReady": True,
                "remainingActionDryRunEvidenceReady": True,
                "realActionNetworkAllowed": False,
            },
            "nativeWrapperCalibration": {
                "summary": {
                    "captureCount": 2,
                    "uniqueGameHexCount": 2,
                    "prefixLength": stable,
                    "suffixLength": stable,
                    "prefixHash": stable,
                    "suffixHash": stable,
                    "splitStatuses": ["prefix_equals_lx_plus_key", "suffix_equals_lb"],
                    "brushYellowWrapperCoverage": {
                        "prepare1520030": 1,
                        "dispatch1522030": 1,
                        "complete": True,
                    },
                    "brushYellowWrapperDetails": {
                        "complete": True,
                        "splitProvenForBothStages": True,
                        "prepare1520030": {"count": 1, "splitProven": True},
                        "dispatch1522030": {"count": 1, "splitProven": True},
                    },
                    "nativeWrapperFieldAudit": {
                        "readyForDryRunWrapperPlan": True,
                        "selectedLxSource": "nativeWrapperLx",
                        "selectedKeySource": "nativeWrapperKey",
                        "selectedLbSource": "nativeWrapperLb",
                        "networkSendAllowed": False,
                    },
                    "networkSendAllowed": False,
                    "actionSendReady": False,
                    "readinessLevel": "dry_run_only",
                }
            },
            "readOnlyResponseCalibration": {"summary": {"networkSendAllowed": False}},
            "actionResponseCalibration": {"summary": {"networkSendAllowed": False}},
            "dailyResponseCalibration": {"summary": {"networkSendAllowed": False}},
            "replayContract": {"evidence": {"unsafeTrueFlags": []}},
        }

    def test_full_offline_evidence_is_dry_run_ready_but_real_send_false(self):
        audit = mod.audit(self.report())
        self.assertTrue(audit["summary"]["dryRunActionEvidenceReady"])
        self.assertTrue(audit["summary"]["nativeWrapperFieldAuditReady"])
        self.assertTrue(audit["summary"]["remainingActionDryRunEvidenceReady"])
        self.assertFalse(audit["summary"]["realActionSendReady"])
        self.assertEqual("dry_run_action_evidence_ready", audit["summary"]["readinessLevel"])
        self.assertIn("explicit user-controlled live action gate not present", audit["policyBlockers"])

    def test_missing_wrapper_and_closed_loop_blocks_dry_run_evidence(self):
        report = self.report()
        report["nativeWrapperCalibration"]["summary"]["captureCount"] = 1
        report["nativeWrapperCalibration"]["summary"]["splitStatuses"] = ["unsplit"]
        report["summary"]["shuaHuangOfflineClosedLoopReplayReady"] = False
        audit = mod.audit(report)
        self.assertFalse(audit["summary"]["dryRunActionEvidenceReady"])
        self.assertIn("nativeWrapper:captureCount>=2", audit["missing"])
        self.assertIn("nativeWrapper:lx/key/lb split proven", audit["missing"])
        self.assertIn("replay:brush-yellow closed loop", audit["missing"])

    def test_missing_brush_yellow_wrapper_opcode_coverage_blocks(self):
        report = self.report()
        report["nativeWrapperCalibration"]["summary"]["brushYellowWrapperCoverage"] = {
            "prepare1520030": 0,
            "dispatch1522030": 0,
            "complete": False,
        }
        report["nativeWrapperCalibration"]["summary"]["brushYellowWrapperDetails"] = {
            "complete": False,
            "splitProvenForBothStages": False,
        }
        audit = mod.audit(report)
        self.assertFalse(audit["summary"]["dryRunActionEvidenceReady"])
        self.assertIn("nativeWrapper:brush-yellow 1520030+1522030 wrapper captures", audit["missing"])

    def test_missing_brush_yellow_per_stage_split_proof_blocks(self):
        report = self.report()
        report["nativeWrapperCalibration"]["summary"]["brushYellowWrapperDetails"]["splitProvenForBothStages"] = False

        audit = mod.audit(report)

        self.assertFalse(audit["summary"]["dryRunActionEvidenceReady"])
        self.assertIn("nativeWrapper:brush-yellow 1520030+1522030 split proven", audit["missing"])

    def test_unsafe_flag_blocks(self):
        report = self.report()
        report["summary"]["realActionNetworkAllowed"] = True
        audit = mod.audit(report)
        self.assertFalse(audit["summary"]["dryRunActionEvidenceReady"])
        self.assertIn("unsafe network flag must be false", audit["missing"])

    def test_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "device_regression_report.json"
            out = Path(td) / "gate.json"
            md = Path(td) / "gate.md"
            src.write_text(json.dumps(self.report(), ensure_ascii=False), encoding="utf-8")
            subprocess.check_call([sys.executable, str(SCRIPT), str(src), "--out", str(out), "--markdown-out", str(md)])
            audit = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(audit["summary"]["dryRunActionEvidenceReady"])
            self.assertIn("动作 Gate Readiness 审计", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
