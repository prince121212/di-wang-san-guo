#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("wait_for_device_and_run_pipeline.sh")


class WaitForDeviceAndRunPipelineTest(unittest.TestCase):
    def test_shell_syntax_and_help(self) -> None:
        subprocess.check_call(["bash", "-n", str(SCRIPT)])
        out = subprocess.check_output(["bash", str(SCRIPT), "--help"], text=True)
        self.assertIn("Wait until device regression preflight is ready", out)
        self.assertIn("--timeout", out)
        self.assertIn("--promote-canonical", out)
        self.assertIn("--run-self-smoke-first", out)
        self.assertIn("never enables real action sends", out)

    def test_requires_package(self) -> None:
        proc = subprocess.run(["bash", str(SCRIPT), "--dry-run"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(64, proc.returncode)
        self.assertIn("--package is required", proc.stderr)

    def test_dry_run_writes_wait_plan_without_device(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "wait"
            proc = subprocess.run([
                "bash", str(SCRIPT),
                "--package", "com.ifengwoo.dwpm",
                "--timeout", "2",
                "--interval", "1",
                "--duration", "5",
                "--out-dir", str(out_dir),
                "--promote-canonical",
                "--run-self-smoke-first",
                "--dry-run",
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(0, proc.returncode, proc.stderr)
            md = out_dir / "wait_for_device_summary.md"
            js = out_dir / "wait_for_device_summary.json"
            self.assertTrue(md.exists())
            self.assertTrue(js.exists())
            text = md.read_text(encoding="utf-8")
            self.assertIn("等待设备并运行回归管线", text)
            self.assertIn("run_device_regression_pipeline.sh", text)
            self.assertIn("--run-self-smoke-first", text)
            self.assertIn("shuahuang_minimum_goal_check.md", text)
            self.assertIn("shuaHuangMinimumLiveEvidenceReady", text)
            data = json.loads(js.read_text(encoding="utf-8"))
            self.assertEqual("planned", data["summary"]["status"])
            self.assertFalse(data["summary"]["realActionNetworkAllowed"])
            self.assertFalse(data["summary"]["realActionSendReady"])
            self.assertTrue(data["summary"]["runSelfSmokeFirst"])
            self.assertFalse(data["summary"]["shuaHuangMinimumLiveEvidenceReady"])
            self.assertIn("shuahuang_minimum_goal_check.md", data["summary"]["shuahuangMinimumGoalCheckMarkdown"])

    def test_timeout_writes_latest_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            adb = root / "adb"
            adb.write_text("#!/usr/bin/env bash\nif [[ $1 == devices ]]; then echo 'List of devices attached'; echo; else exit 1; fi\n", encoding="utf-8")
            adb.chmod(0o755)
            frida = root / "frida"
            frida.write_text("#!/usr/bin/env bash\necho frida\n", encoding="utf-8")
            frida.chmod(0o755)
            frida_ps = root / "frida-ps"
            frida_ps.write_text("#!/usr/bin/env bash\necho should-not-run\n", encoding="utf-8")
            frida_ps.chmod(0o755)
            files = []
            for name in ["self.apk", "xh.apk", "game.apk", "trace.js"]:
                path = root / name
                path.write_text("x", encoding="utf-8")
                files.append(path)
            out_dir = root / "wait"
            env = dict(**{k: v for k, v in __import__('os').environ.items()})
            env.update({"ADB_BIN": str(adb), "FRIDA_BIN": str(frida), "FRIDA_PS_BIN": str(frida_ps)})
            proc = subprocess.run([
                "bash", str(SCRIPT),
                "--package", "com.ifengwoo.dwpm",
                "--timeout", "1",
                "--interval", "1",
                "--duration", "5",
                "--out-dir", str(out_dir),
                "--frida-script", str(files[3]),
                "--self-apk", str(files[0]),
                "--xiaohuang-apk", str(files[1]),
                "--game-apk", str(files[2]),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            self.assertEqual(69, proc.returncode)
            self.assertTrue((out_dir / "wait_preflight_latest.json").exists())
            self.assertTrue((out_dir / "wait_preflight_latest.md").exists())
            self.assertTrue((out_dir / "wait_for_device_summary.json").exists())
            data = json.loads((out_dir / "wait_for_device_summary.json").read_text(encoding="utf-8"))
            self.assertEqual("timeout", data["summary"]["status"])
            self.assertIn("authorized adb device", (out_dir / "wait_preflight_latest.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
