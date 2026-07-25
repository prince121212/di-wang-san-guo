#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("replay_full_offline.py")
GEN = Path(__file__).with_name("generate_shuahuang_channel_extra_sample.py")

spec = importlib.util.spec_from_file_location("replay_full_offline", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["replay_full_offline"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]

gen_spec = importlib.util.spec_from_file_location("generate_shuahuang_channel_extra_sample", GEN)
gen = importlib.util.module_from_spec(gen_spec)
sys.modules["generate_shuahuang_channel_extra_sample"] = gen
gen_spec.loader.exec_module(gen)  # type: ignore[union-attr]


class ReplayFullOfflineTest(unittest.TestCase):
    def full_extra(self):
        return gen.build_sample(target_type="HUANG_JIN", include_daily=True, include_mine=True)

    def test_full_sample_passes_all_offline_suites_but_not_action_gate(self):
        report = mod.replay(self.full_extra(), target_type="HUANG_JIN", start_x=11, start_y=22)

        self.assertTrue(report["summary"]["fullOfflineReplayReady"])
        self.assertTrue(report["summary"]["shuaHuangOfflineClosedLoopReplayReady"])
        self.assertTrue(report["summary"]["roleResourceParseReady"])
        self.assertTrue(report["summary"]["generalEvidenceParseReady"])
        self.assertTrue(report["summary"]["state8004GeneralEvidenceReady"])
        self.assertTrue(report["summary"]["dailyOfflineClosedLoopReplayReady"])
        self.assertTrue(report["summary"]["dailyProtocolEvidenceReady"])
        self.assertTrue(report["summary"]["dailyFullRecoveredOrderReady"])
        self.assertTrue(report["summary"]["mineOfflineClosedLoopReplayReady"])
        self.assertTrue(report["summary"]["mineReadOnlyEvidenceReady"])
        self.assertTrue(report["summary"]["mineSelectionEvidenceReady"])
        self.assertEqual([], report["missingSuites"])
        self.assertEqual(2, report["summary"]["targetParsedCount"])
        self.assertEqual(1, report["summary"]["dispatchResultCount"])
        self.assertGreaterEqual(report["summary"]["dailyStepResultCount"], 11)
        self.assertEqual(2, report["summary"]["mineParsedCount"])
        self.assertFalse(report["summary"]["dryRunActionEvidenceReady"])
        self.assertFalse(report["summary"]["realActionSendReady"])
        self.assertIn("nativeWrapper:captureCount>=2", report["actionGateAudit"]["missing"])

    def test_missing_daily_blocks_full_when_required(self):
        extra = gen.build_sample(target_type="HUANG_JIN", include_daily=False, include_mine=True)
        report = mod.replay(extra, target_type="HUANG_JIN", require_daily=True, require_mine=True)

        self.assertFalse(report["summary"]["fullOfflineReplayReady"])
        self.assertIn("daily", report["missingSuites"])

        relaxed = mod.replay(extra, target_type="HUANG_JIN", require_daily=False, require_mine=True)
        self.assertTrue(relaxed["summary"]["fullOfflineReplayReady"])
        self.assertFalse(relaxed["summary"]["dailyOfflineClosedLoopReplayReady"])

    def test_cli_accepts_channel_extra_and_report_wrappers(self):
        with tempfile.TemporaryDirectory() as td:
            extra_path = Path(td) / "extra.json"
            wrapper_path = Path(td) / "wrapper.json"
            out = Path(td) / "full.json"
            md = Path(td) / "full.md"
            extra = self.full_extra()
            extra_path.write_text(json.dumps(extra, ensure_ascii=False), encoding="utf-8")
            wrapper_path.write_text(json.dumps({"channelExtra": extra}, ensure_ascii=False), encoding="utf-8")

            subprocess.check_call([
                sys.executable, str(SCRIPT), str(wrapper_path),
                "--out", str(out),
                "--markdown-out", str(md),
            ])
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(report["summary"]["fullOfflineReplayReady"])
            self.assertIn("Full Offline Replay 统一验收报告", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
