#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("verify_shuahuang_minimum_goal.py")
spec = importlib.util.spec_from_file_location("verify_shuahuang_minimum_goal", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["verify_shuahuang_minimum_goal"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


def write_capture(root: Path, *, general_formation: bool = True, dry_run: bool = True, stop_logout: bool = True, target_selection: bool = True, dispatch_payload: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "preflight.json").write_text(json.dumps({
        "summary": {
            "preflightReady": True,
            "authorizedDeviceCount": 1,
            "realActionNetworkAllowed": False,
        },
        "missing": [],
    }, ensure_ascii=False), encoding="utf-8")
    scenarios = {
        "summary": {
            "captureScenarioRequiredReady": general_formation and stop_logout,
            "captureScenarioRecommendedReady": general_formation and stop_logout,
            "realActionNetworkAllowed": False,
        },
        "missingRequired": [] if general_formation and stop_logout else (
            ([] if general_formation else ["generalFormationBaseline"]) + ([] if stop_logout else ["selfStopLogout"])
        ),
        "scenarios": {
            "loginState8004": {"requiredOk": True},
            "generalFormationBaseline": {"requiredOk": general_formation},
            "brushYellowSearch041540": {"requiredOk": True},
            "brushYellowNativeWrapper1520": {"requiredOk": True},
            "brushYellowDispatch1522030": {"requiredOk": True},
            "selfStopLogout": {"requiredOk": stop_logout},
        },
    }
    (root / "capture_scenario_check.json").write_text(json.dumps(scenarios, ensure_ascii=False), encoding="utf-8")
    reg = root / "regression"
    reg.mkdir()
    summary = {
        "shuaHuangOfflineClosedLoopReplayReady": True,
        "dryRunActionEvidenceReady": dry_run,
        "realActionNetworkAllowed": False,
    }
    native = {
        "summary": {
            "brushYellowWrapperCoverage": {"prepare1520030": 1, "dispatch1522030": 1, "complete": True},
            "brushYellowWrapperDetails": {"splitProvenForBothStages": True},
        }
    }
    (reg / "device_regression_report.json").write_text(json.dumps({
        "summary": summary,
        "nativeWrapperCalibration": native,
    }, ensure_ascii=False), encoding="utf-8")
    steps = [
        {"step": "login/session", "ok": True},
        {"step": "role/resource", "ok": True},
        {"step": "generals", "ok": True},
        {"step": "formations", "ok": True},
        {"step": "chooseFormation", "ok": True},
        {"step": "findYellow/041540", "ok": True},
        {"step": "chooseTarget", "ok": True},
        {"step": "buildDispatchPayloads/1520030+1522030", "ok": dispatch_payload},
        {"step": "dispatchResult/1522030", "ok": True},
        {"step": "stop/logout", "ok": True},
    ]
    (reg / "shuahuang_offline_replay.json").write_text(json.dumps({
        "summary": {
            "shuaHuangOfflineClosedLoopReplayReady": True,
            "selectedFormationId": 3,
            "selectedTargetId": 101,
            "appliedTargetFilter": {
                "minLevel": None,
                "maxLevel": None,
                "maxDistance": None,
                "requiredKeywords": [],
                "blockedKeywords": [],
            },
            "targetSelectionEvidence": {
                "targetSelectionEvidenceReady": target_selection,
                "targetTypeConfigured": "HUANG_JIN",
                "strictTargetTypeMatch": target_selection,
                "filterActive": False,
                "inputTargetCount": 2,
                "filterMatchedCount": 2 if target_selection else 0,
                "typeMatchedCount": 1 if target_selection else 0,
                "selectedTargetId": 101 if target_selection else None,
                "selectedTargetType": "渠帅" if target_selection else None,
            },
            "dispatchPayloadEvidence": {
                "dispatchPayloadEvidenceReady": dispatch_payload,
                "prepareOpcode": "1520030",
                "expeditionOpcode": "1522030",
                "generalIdHexChunks": ["0000000000000007"] if dispatch_payload else [],
                "generalCount": 1 if dispatch_payload else 0,
                "targetIdHex": "0000000000000065" if dispatch_payload else "",
                "prepareLengthHex": "12" if dispatch_payload else "",
                "expeditionLengthHex": "1d" if dispatch_payload else "",
                "preparePayload": "0000000000000000001215200301000000000000000700000000000000000065" if dispatch_payload else "",
                "expeditionPayload": "0000000000000000001d15220301000000000000000700000000000000000065ffffffffffffffff000000" if dispatch_payload else "",
                "prepareContainsTarget": dispatch_payload,
                "expeditionContainsTarget": dispatch_payload,
                "prepareContainsAllGenerals": dispatch_payload,
                "expeditionContainsAllGenerals": dispatch_payload,
            },
            "dispatchMatched": True,
            "dispatchSuccess": True,
        },
        "steps": steps,
        "missingSteps": [],
    }, ensure_ascii=False), encoding="utf-8")
    (reg / "action_gate_readiness.json").write_text(json.dumps({
        "summary": {
            "dryRunActionEvidenceReady": dry_run,
            "realActionSendReady": False,
            "realActionNetworkAllowed": False,
        },
        "missing": [] if dry_run else ["nativeWrapper:brush-yellow 1520030+1522030 wrapper captures"],
    }, ensure_ascii=False), encoding="utf-8")
    return root


class VerifyShuaHuangMinimumGoalTest(unittest.TestCase):
    def test_live_evidence_ready_but_final_send_remains_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = write_capture(Path(td) / "capture")
            report = mod.verify(root)

        self.assertTrue(report["summary"]["shuaHuangMinimumLiveEvidenceReady"])
        self.assertFalse(report["summary"]["shuaHuangMinimumFinalReady"])
        self.assertEqual([], report["missing"])
        self.assertEqual(["realActionSendReady=false", "realActionNetworkAllowed=false"], report["selfAppRealSendBlockers"])
        self.assertEqual(3, report["evidence"]["selectedFormationId"])
        self.assertEqual(101, report["evidence"]["selectedTargetId"])
        self.assertTrue(report["evidence"]["targetSelectionEvidence"]["targetSelectionEvidenceReady"])
        self.assertEqual("HUANG_JIN", report["evidence"]["targetSelectionEvidence"]["targetTypeConfigured"])
        self.assertTrue(report["evidence"]["dispatchPayloadEvidence"]["dispatchPayloadEvidenceReady"])
        self.assertIn("1520030", report["evidence"]["dispatchPayloadEvidence"]["preparePayload"])
        self.assertIn("1522030", report["evidence"]["dispatchPayloadEvidence"]["expeditionPayload"])

    def test_missing_general_formation_baseline_blocks_live_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = write_capture(Path(td) / "capture", general_formation=False)
            report = mod.verify(root)

        self.assertFalse(report["summary"]["shuaHuangMinimumLiveEvidenceReady"])
        self.assertIn("generalFormationBaseline", report["missing"])
        self.assertIn("generalFormationBaseline", report["evidence"]["captureScenarioMissingRequired"])

    def test_missing_dry_run_action_evidence_blocks_live_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = write_capture(Path(td) / "capture", dry_run=False)
            report = mod.verify(root)

        self.assertFalse(report["summary"]["shuaHuangMinimumLiveEvidenceReady"])
        self.assertIn("dryRunActionEvidence", report["missing"])

    def test_missing_stop_logout_blocks_live_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = write_capture(Path(td) / "capture", stop_logout=False)
            report = mod.verify(root)

        self.assertFalse(report["summary"]["shuaHuangMinimumLiveEvidenceReady"])
        self.assertIn("stopLogout", report["missing"])
        self.assertFalse(report["evidence"]["selfStopLogoutScenarioRequiredOk"])

    def test_missing_configured_target_selection_evidence_blocks_live_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = write_capture(Path(td) / "capture", target_selection=False)
            report = mod.verify(root)

        self.assertFalse(report["summary"]["shuaHuangMinimumLiveEvidenceReady"])
        self.assertIn("configuredTargetSelection", report["missing"])
        self.assertFalse(report["evidence"]["targetSelectionEvidence"]["targetSelectionEvidenceReady"])

    def test_missing_dispatch_payload_evidence_blocks_live_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = write_capture(Path(td) / "capture", dispatch_payload=False)
            report = mod.verify(root)

        self.assertFalse(report["summary"]["shuaHuangMinimumLiveEvidenceReady"])
        self.assertIn("dispatchPayloadEvidence", report["missing"])
        self.assertFalse(report["evidence"]["dispatchPayloadEvidence"]["dispatchPayloadEvidenceReady"])

    def test_cli_writes_reports(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = write_capture(Path(td) / "capture")
            out = Path(td) / "goal.json"
            md = Path(td) / "goal.md"
            subprocess.check_call([sys.executable, str(SCRIPT), str(root), "--out", str(out), "--markdown-out", str(md)])
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(data["summary"]["shuaHuangMinimumLiveEvidenceReady"])
            self.assertIn("刷黄最小目标验收报告", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
