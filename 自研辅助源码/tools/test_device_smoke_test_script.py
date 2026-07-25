#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("device_smoke_test.sh")


class DeviceSmokeTestScriptTest(unittest.TestCase):
    def test_shell_syntax_and_self_lifecycle_check_present(self):
        subprocess.check_call(["bash", "-n", str(SCRIPT)])
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("verify_self_lifecycle_logcat.py", text)
        self.assertIn("self_lifecycle_logcat_check.md", text)
        self.assertIn("logcat_after_stop.txt", text)
        self.assertIn("logcat_combined.txt", text)
        self.assertIn("tap_text_or_fallback", text)
        self.assertIn("启动后台托管", text)
        self.assertIn("停止后台托管", text)
        self.assertIn("uiautomator", text)
        self.assertIn("ADB_BIN", text)
        self.assertIn("start_service_tap.txt", text)
        self.assertIn("[self-lifecycle-json]", Path(__file__).with_name("verify_self_lifecycle_logcat.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
