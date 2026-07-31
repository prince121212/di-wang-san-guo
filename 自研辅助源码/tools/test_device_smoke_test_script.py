#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("device_smoke_test.sh")


class DeviceSmokeTestScriptTest(unittest.TestCase):
    def test_shell_syntax_and_safe_local_launch_contract(self):
        subprocess.check_call(["bash", "-n", str(SCRIPT)])
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('ACTIVITY="${PKG}/.AssistantWebActivity"', text)
        self.assertIn('install -r "$APK"', text)
        self.assertNotIn("install -r -d", text)
        self.assertNotIn("force-stop", text)
        self.assertNotIn("input tap", text)
        self.assertNotIn("startservice", text.lower())
        self.assertIn("hostingStarted: false", text)
        self.assertIn("gameActionSent: false", text)
        self.assertIn("uiautomator", text)
        self.assertIn("ADB_BIN", text)


if __name__ == "__main__":
    unittest.main()
