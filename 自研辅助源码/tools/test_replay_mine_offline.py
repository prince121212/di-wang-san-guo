#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("replay_mine_offline.py")
spec = importlib.util.spec_from_file_location("replay_mine_offline", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["replay_mine_offline"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class ReplayMineOfflineTest(unittest.TestCase):
    def complete_extra(self):
        return {
            "userId": "u1",
            "serverUrl": "http://game.example",
            "mineTargetsHex": "0000000001010101000b0016010002D00101000000270F00000000010202020021002c000002D0020200000022B8",
            "selectedMineTypes": "GOLD,SILVER",
            "onlyEmptyMine": "true",
            "mineSelectedFormationIds": "3",
            "networkSendAllowed": "false",
        }

    def test_replays_mine_search_and_filter(self):
        report = mod.replay(self.complete_extra(), start_x=11, start_y=22)
        self.assertTrue(report["summary"]["mineOfflineClosedLoopReplayReady"])
        self.assertTrue(report["summary"]["mineReadOnlyEvidenceReady"])
        self.assertTrue(report["summary"]["mineSelectionEvidenceReady"])
        self.assertEqual(2, report["summary"]["mineCount"])
        self.assertEqual(1, report["summary"]["filteredMineCount"])
        self.assertEqual(0x101, report["summary"]["selectedMineId"])
        self.assertEqual("GOLD", report["summary"]["selectedMineType"])
        evidence = report["summary"]["mineSelectionEvidence"]
        self.assertEqual("041542", evidence["searchOpcode"])
        self.assertEqual("000000000000000000041542000b0016", evidence["searchPayload"])
        self.assertEqual(["GOLD", "SILVER"], evidence["filterConfig"]["selectedMineTypes"])
        self.assertTrue(evidence["selectedTypeMatchesConfig"])
        self.assertTrue(evidence["selectedEmptyMatchesConfig"])
        self.assertFalse(evidence["occupyRequired"])
        self.assertFalse(evidence["withdrawRequired"])
        self.assertFalse(report["summary"]["resourcePointActionPayloadEvidenceReady"])
        self.assertFalse(report["summary"]["withdrawPayloadEvidenceReady"])
        self.assertFalse(report["summary"]["remainingActionDryRunEvidenceReady"])

    def test_occupy_required_needs_matching_action_result(self):
        extra = self.complete_extra()
        extra["mineGeneralIds"] = "7"
        extra["occupyMineResultsJson"] = json.dumps([
            {"mineId": "257", "formationId": 3, "success": True, "message": "占矿出征成功"}
        ], ensure_ascii=False)
        report = mod.replay(extra, start_x=11, start_y=22, require_occupy=True)
        self.assertTrue(report["summary"]["mineOfflineClosedLoopReplayReady"])
        self.assertFalse(report["summary"]["mineReadOnlyEvidenceReady"])
        self.assertTrue(report["summary"]["occupyMatched"])
        self.assertTrue(report["summary"]["resourcePointActionPayloadEvidenceReady"])
        self.assertTrue(report["summary"]["remainingActionDryRunEvidenceReady"])
        evidence = report["resourcePointActionPayloadEvidence"]
        self.assertEqual("1520010", evidence["prepareOpcode"])
        self.assertEqual("1522010", evidence["dispatchOpcode"])
        self.assertEqual("0000000000000101", evidence["resourcePointIdHex"])
        self.assertIn("1520010", evidence["preparePayload"])
        self.assertIn("1522010", evidence["dispatchPayload"])

        extra["occupyMineResultsJson"] = json.dumps([
            {"mineId": "999", "formationId": 3, "success": True}
        ], ensure_ascii=False)
        blocked = mod.replay(extra, start_x=11, start_y=22, require_occupy=True)
        self.assertFalse(blocked["summary"]["mineOfflineClosedLoopReplayReady"])
        self.assertIn("occupyMineResult", blocked["missingSteps"])

    def test_withdraw_required_builds_payload_and_matches_result(self):
        extra = self.complete_extra()
        extra["withdrawDefenseRecordId"] = "257"
        extra["withdrawMineResultsJson"] = json.dumps([
            {"mineId": "257", "success": True, "message": "撤防完成"}
        ], ensure_ascii=False)
        report = mod.replay(extra, start_x=11, start_y=22, require_withdraw=True)
        self.assertTrue(report["summary"]["mineOfflineClosedLoopReplayReady"])
        self.assertFalse(report["summary"]["mineReadOnlyEvidenceReady"])
        self.assertTrue(report["summary"]["withdrawPayloadEvidenceReady"])
        self.assertTrue(report["summary"]["remainingActionDryRunEvidenceReady"])
        evidence = report["withdrawPayloadEvidence"]
        self.assertEqual("0a15260101", evidence["withdrawOpcode"])
        self.assertEqual("0000000000000101", evidence["defenseRecordIdHex"])
        self.assertIn("0a15260101", evidence["withdrawPayload"])

    def test_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "extra.json"
            out = Path(td) / "mine.json"
            md = Path(td) / "mine.md"
            src.write_text(json.dumps(self.complete_extra(), ensure_ascii=False), encoding="utf-8")
            subprocess.check_call([
                sys.executable, str(SCRIPT), str(src),
                "--start-x", "11", "--start-y", "22",
                "--out", str(out), "--markdown-out", str(md),
            ])
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(report["summary"]["mineOfflineClosedLoopReplayReady"])
            md_text = md.read_text(encoding="utf-8")
            self.assertIn("找矿离线回放报告", md_text)
            self.assertIn("mineReadOnlyEvidenceReady", md_text)
            self.assertIn("Mine selection evidence", md_text)
            self.assertIn("Resource-point action payload evidence", md_text)


if __name__ == "__main__":
    unittest.main()
