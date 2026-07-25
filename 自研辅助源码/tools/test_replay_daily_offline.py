#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("replay_daily_offline.py")
spec = importlib.util.spec_from_file_location("replay_daily_offline", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["replay_daily_offline"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class ReplayDailyOfflineTest(unittest.TestCase):
    def complete_extra(self):
        return {
            "userId": "u1",
            "serverUrl": "http://game.example",
            "dailyEnabledSteps": "DONATE_TECH,SURPRISE_BOX,SIGN_IN,DONATE_COPPER,ADD_LOYALTY",
            "dailyDonationFactorFz": "2",
            "dailyStepResultsJson": json.dumps([
                {"step": "SIGN_IN", "success": True, "message": "已完成签到！"},
                {"step": "SURPRISE_BOX", "success": True, "message": "已领取惊喜宝箱！"},
                {"step": "ADD_LOYALTY", "success": True, "message": "已一键加忠！"},
                {"step": "DONATE_COPPER", "success": True, "message": "已捐献铜钱！"},
                {"step": "DONATE_TECH", "success": True, "message": "已捐献科技！"},
            ], ensure_ascii=False),
            "networkSendAllowed": "false",
        }

    def test_replays_recovered_daily_order(self):
        report = mod.replay(self.complete_extra())
        self.assertTrue(report["summary"]["dailyOfflineClosedLoopReplayReady"])
        self.assertTrue(report["summary"]["dailyProtocolEvidenceReady"])
        self.assertFalse(report["summary"]["fullRecoveredOrder"])
        self.assertTrue(report["summary"]["orderMatchesRecoveredSequence"])
        self.assertEqual(5, report["summary"]["protocolEvidenceStepCount"])
        self.assertEqual([
            "SIGN_IN", "SURPRISE_BOX", "ADD_LOYALTY", "DONATE_COPPER", "DONATE_TECH"
        ], report["requestedSteps"])
        donate = next(step for step in report["steps"] if step["step"] == "DONATE_COPPER")
        self.assertIn("00000000000007d0", donate["payloads"][0])
        self.assertTrue(donate["protocolEvidence"]["protocolEvidenceReady"])

    def test_missing_step_blocks_replay_and_stop_on_failure_marks_stopped_step(self):
        extra = self.complete_extra()
        extra["dailyStepResultsJson"] = json.dumps([
            {"step": "SIGN_IN", "success": True, "message": "已完成签到！"},
            {"step": "SURPRISE_BOX", "success": False, "message": "领取失败"},
        ], ensure_ascii=False)
        report = mod.replay(extra, stop_on_failure=True)
        self.assertFalse(report["summary"]["dailyOfflineClosedLoopReplayReady"])
        self.assertEqual("SURPRISE_BOX", report["summary"]["stoppedAt"])
        self.assertIn("dailyStep:SURPRISE_BOX", report["missingSteps"])

    def test_unrecovered_requested_step_blocks_replay(self):
        extra = self.complete_extra()
        extra["dailyEnabledSteps"] = "SIGN_IN,LEVEL_GIFT"
        extra["dailyStepResultsJson"] = json.dumps([
            {"step": "SIGN_IN", "success": True, "message": "已完成签到！"},
            {"step": "LEVEL_GIFT", "success": True, "message": "领取成功"},
        ], ensure_ascii=False)
        report = mod.replay(extra)
        self.assertFalse(report["summary"]["dailyOfflineClosedLoopReplayReady"])
        self.assertIn("unrecoveredSteps:LEVEL_GIFT", report["missingSteps"])

    def test_convert_half_food_to_copper_replays_as_recovered_delegated_step(self):
        extra = self.complete_extra()
        extra["dailyEnabledSteps"] = "SIGN_IN,CONVERT_HALF_FOOD_TO_COPPER"
        extra["dailyStepResultsJson"] = json.dumps([
            {"step": "SIGN_IN", "success": True, "message": "已完成签到！"},
            {"step": "CONVERT_HALF_FOOD_TO_COPPER", "success": True, "message": "已转换一半粮食到铜钱！"},
        ], ensure_ascii=False)

        report = mod.replay(extra)

        self.assertTrue(report["summary"]["dailyOfflineClosedLoopReplayReady"])
        self.assertEqual(["SIGN_IN", "CONVERT_HALF_FOOD_TO_COPPER"], report["requestedSteps"])
        convert = next(step for step in report["steps"] if step["step"] == "CONVERT_HALF_FOOD_TO_COPPER")
        self.assertEqual([], convert["payloads"])
        self.assertTrue(convert["recovered"])
        self.assertTrue(convert["protocolEvidence"]["delegatedStep"])
        self.assertTrue(convert["protocolEvidence"]["protocolEvidenceReady"])

    def test_captured_payload_mismatch_blocks_protocol_evidence(self):
        extra = self.complete_extra()
        extra["dailyEnabledSteps"] = "SURPRISE_BOX"
        extra["dailyStepResultsJson"] = json.dumps([
            {
                "step": "SURPRISE_BOX",
                "success": True,
                "message": "已领取惊喜宝箱！",
                "payloadHex": "000000000000000000deadbeef",
            }
        ], ensure_ascii=False)

        report = mod.replay(extra)

        self.assertFalse(report["summary"]["dailyOfflineClosedLoopReplayReady"])
        self.assertFalse(report["summary"]["dailyProtocolEvidenceReady"])
        self.assertIn("SURPRISE_BOX", report["protocolMissingSteps"])
        step = report["steps"][0]
        self.assertFalse(step["protocolEvidence"]["capturedPayloadMatchesExpected"])

    def test_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "extra.json"
            out = Path(td) / "daily.json"
            md = Path(td) / "daily.md"
            src.write_text(json.dumps(self.complete_extra(), ensure_ascii=False), encoding="utf-8")
            subprocess.check_call([sys.executable, str(SCRIPT), str(src), "--out", str(out), "--markdown-out", str(md)])
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(report["summary"]["dailyOfflineClosedLoopReplayReady"])
            md_text = md.read_text(encoding="utf-8")
            self.assertIn("一键日常离线回放报告", md_text)
            self.assertIn("dailyProtocolEvidenceReady", md_text)
            self.assertIn("Protocol missing steps", md_text)


if __name__ == "__main__":
    unittest.main()
