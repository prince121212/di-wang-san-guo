#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("run_device_regression_pipeline.sh")


class RunDeviceRegressionPipelineTest(unittest.TestCase):
    def test_shell_syntax_and_help(self) -> None:
        subprocess.check_call(["bash", "-n", str(SCRIPT)])
        out = subprocess.check_output(["bash", str(SCRIPT), "--help"], text=True)
        self.assertIn("One-command device regression pipeline", out)
        self.assertIn("--account-export", out)
        self.assertIn("--promote-canonical", out)
        self.assertIn("--run-self-smoke-first", out)
        self.assertIn("--dry-run", out)
        self.assertIn("never enables real action sends", out)

    def test_requires_package(self) -> None:
        proc = subprocess.run(["bash", str(SCRIPT), "--dry-run"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(64, proc.returncode)
        self.assertIn("--package is required", proc.stderr)

    def test_dry_run_writes_plan_without_device(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "capture"
            proc = subprocess.run([
                "bash", str(SCRIPT),
                "--package", "com.ifengwoo.dwpm",
                "--duration", "5",
                "--out-dir", str(out_dir),
                "--dry-run",
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(0, proc.returncode, proc.stderr)
            summary = out_dir / "pipeline_summary.md"
            data_path = out_dir / "pipeline_summary.json"
            self.assertTrue(summary.exists())
            self.assertTrue(data_path.exists())
            text = summary.read_text(encoding="utf-8")
            self.assertIn("设备回归一键管线", text)
            self.assertIn("capture_device_protocol_regression.sh", text)
            self.assertIn("promote_device_regression_capture.py", text)
            self.assertIn("selfSmoke: <skipped>", text)
            self.assertIn("shuahuang_minimum_goal_check.md", text)
            self.assertIn("shuaHuangMinimumLiveEvidenceReady", text)
            data = json.loads(data_path.read_text(encoding="utf-8"))
            self.assertEqual("planned", data["summary"]["status"])
            self.assertTrue(data["summary"]["dryRun"])
            self.assertFalse(data["summary"]["realActionNetworkAllowed"])
            self.assertFalse(data["summary"]["realActionSendReady"])
            self.assertFalse(data["summary"]["runSelfSmokeFirst"])
            self.assertFalse(data["summary"]["shuaHuangMinimumLiveEvidenceReady"])
            self.assertIn("shuahuang_minimum_goal_check.md", data["summary"]["shuahuangMinimumGoalCheckMarkdown"])

    def test_dry_run_with_account_export_builds_prepare_command(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            account = root / "accounts.json"
            merge = root / "merge.json"
            account.write_text(json.dumps({"accounts": [{"id": 7, "session": {"channelExtra": {"userId": "u"}}}]}, ensure_ascii=False), encoding="utf-8")
            merge.write_text("{}", encoding="utf-8")
            out_dir = root / "capture"
            proc = subprocess.run([
                "bash", str(SCRIPT),
                "--package", "com.ifengwoo.dwpm",
                "--duration", "5",
                "--out-dir", str(out_dir),
                "--account-export", str(account),
                "--account-id", "7",
                "--merge-extra", str(merge),
                "--promote-canonical",
                "--run-self-smoke-first",
                "--dry-run",
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(0, proc.returncode, proc.stderr)
            text = (out_dir / "pipeline_summary.md").read_text(encoding="utf-8")
            self.assertIn("prepare_base_channel_extra.py", text)
            self.assertIn("--account-id", text)
            self.assertIn("--merge-extra", text)
            self.assertIn("--promote-canonical", text)
            self.assertIn("device_smoke_test.sh", text)
            data = json.loads((out_dir / "pipeline_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(str(out_dir / "base_channel_extra.json"), data["summary"]["baseChannelExtra"])
            self.assertTrue(data["summary"]["promoteCanonical"])
            self.assertTrue(data["summary"]["runSelfSmokeFirst"])


if __name__ == "__main__":
    unittest.main()
