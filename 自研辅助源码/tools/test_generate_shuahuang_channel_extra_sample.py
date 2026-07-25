#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("generate_shuahuang_channel_extra_sample.py")
spec = importlib.util.spec_from_file_location("generate_shuahuang_channel_extra_sample", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["generate_shuahuang_channel_extra_sample"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class GenerateShuaHuangChannelExtraSampleTest(unittest.TestCase):
    def test_generated_huang_sample_is_replay_ready_and_safe(self):
        extra = mod.build_sample(role_name="测试样本", target_type="HUANG_JIN")
        report = mod.generate_report(extra, target_type="HUANG_JIN", start_x=11, start_y=22)

        self.assertTrue(report["summary"]["shuaHuangOfflineReplayReady"])
        self.assertTrue(report["summary"]["contractReady"])
        self.assertFalse(report["summary"]["dailyOfflineReplayReady"])
        self.assertFalse(report["summary"]["dailyProtocolEvidenceReady"])
        self.assertFalse(report["summary"]["dailyFullRecoveredOrderReady"])
        self.assertFalse(report["summary"]["mineOfflineReplayReady"])
        self.assertFalse(report["summary"]["mineReadOnlyEvidenceReady"])
        self.assertFalse(report["summary"]["mineSelectionEvidenceReady"])
        self.assertEqual(3, report["summary"]["selectedFormationId"])
        self.assertEqual(101, report["summary"]["selectedTargetId"])
        self.assertTrue(report["summary"]["targetSelectionEvidenceReady"])
        self.assertTrue(report["summary"]["strictTargetTypeMatch"])
        self.assertGreater(report["summary"]["filterMatchedCount"], 0)
        self.assertGreater(report["summary"]["typeMatchedCount"], 0)
        self.assertTrue(report["summary"]["dispatchPayloadEvidenceReady"])
        self.assertIn("1520030", report["summary"]["preparePayload"])
        self.assertIn("1522030", report["summary"]["expeditionPayload"])
        self.assertTrue(report["summary"]["dispatchMatched"])
        self.assertTrue(report["summary"]["dispatchSuccess"])
        for key in mod.SAFE_FALSE_FLAGS:
            self.assertEqual("false", extra[key])
        self.assertNotIn("tokenCiphertext", extra)
        self.assertNotIn("password", extra)

    def test_generated_shan_sample_selects_shan_target(self):
        extra = mod.build_sample(target_type="SHAN_ZEI", target_alias_style="captured")
        report = mod.generate_report(extra, target_type="SHAN_ZEI", start_x=33, start_y=44)

        self.assertTrue(report["summary"]["shuaHuangOfflineReplayReady"])
        self.assertEqual(102, report["summary"]["selectedTargetId"])
        self.assertEqual("SHAN_ZEI", report["summary"]["targetType"])

    def test_canonical_alias_style_is_also_replay_ready(self):
        extra = mod.build_sample(target_type="HUANG_JIN", target_alias_style="canonical")
        report = mod.generate_report(extra, target_type="HUANG_JIN", start_x=11, start_y=22)

        self.assertTrue(report["summary"]["shuaHuangOfflineReplayReady"])
        target = report["replay"]["selected"]["target"]
        self.assertEqual("黄巾", target["type"])

    def test_full_sample_includes_daily_and_mine_replay_contracts(self):
        extra = mod.build_sample(target_type="HUANG_JIN", include_daily=True, include_mine=True)
        report = mod.generate_report(extra, target_type="HUANG_JIN", start_x=11, start_y=22)

        self.assertTrue(report["summary"]["shuaHuangOfflineReplayReady"])
        self.assertTrue(report["summary"]["dailyOfflineReplayReady"])
        self.assertTrue(report["summary"]["dailyProtocolEvidenceReady"])
        self.assertTrue(report["summary"]["dailyFullRecoveredOrderReady"])
        self.assertTrue(report["summary"]["mineOfflineReplayReady"])
        self.assertTrue(report["summary"]["mineReadOnlyEvidenceReady"])
        self.assertTrue(report["summary"]["mineSelectionEvidenceReady"])
        self.assertTrue(report["summary"]["dailyContractReady"])
        self.assertTrue(report["summary"]["mineContractReady"])
        self.assertIn("dailyStepResultsJson", extra)
        self.assertIn("mineTargetsHex", extra)
        self.assertEqual([], report["dailyReplay"]["missingSteps"])
        self.assertEqual([], report["mineReplay"]["missingSteps"])

    def test_cli_writes_channel_extra_and_reports(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "shuahuang_channel_extra.json"
            report_out = Path(td) / "sample_report.json"
            md = Path(td) / "sample_report.md"
            subprocess.check_call([
                sys.executable, str(SCRIPT),
                "--role-name", "CLI样本",
                "--out", str(out),
                "--report-out", str(report_out),
                "--markdown-out", str(md),
            ])
            extra = json.loads(out.read_text(encoding="utf-8"))
            report = json.loads(report_out.read_text(encoding="utf-8"))
            self.assertEqual("CLI样本", extra["roleName"])
            self.assertEqual("false", extra["realActionNetworkAllowed"])
            self.assertTrue(report["summary"]["shuaHuangOfflineReplayReady"])
            self.assertTrue(report["summary"]["targetSelectionEvidenceReady"])
            self.assertIn("刷黄 ChannelExtra 样本生成报告", md.read_text(encoding="utf-8"))

    def test_cli_full_profile_writes_daily_and_mine_fields(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "full_channel_extra.json"
            report_out = Path(td) / "full_report.json"
            subprocess.check_call([
                sys.executable, str(SCRIPT),
                "--profile", "full",
                "--out", str(out),
                "--report-out", str(report_out),
            ])
            extra = json.loads(out.read_text(encoding="utf-8"))
            report = json.loads(report_out.read_text(encoding="utf-8"))
            self.assertIn("dailyStepResultsJson", extra)
            self.assertIn("mineTargetsHex", extra)
            self.assertTrue(report["summary"]["dailyOfflineReplayReady"])
            self.assertTrue(report["summary"]["dailyProtocolEvidenceReady"])
            self.assertTrue(report["summary"]["dailyFullRecoveredOrderReady"])
            self.assertTrue(report["summary"]["mineOfflineReplayReady"])
            self.assertTrue(report["summary"]["mineReadOnlyEvidenceReady"])
            self.assertTrue(report["summary"]["mineSelectionEvidenceReady"])


if __name__ == "__main__":
    unittest.main()
