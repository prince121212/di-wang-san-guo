#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("verify_self_lifecycle_logcat.py")
spec = importlib.util.spec_from_file_location("verify_self_lifecycle_logcat", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["verify_self_lifecycle_logcat"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class VerifySelfLifecycleLogcatTest(unittest.TestCase):
    def full_log(self) -> str:
        return "\n".join([
            'I/self-lifecycle: [self-lifecycle-json] {"event":"task_stop","accountId":7,"sourceMode":1,"logoutRequested":true,"logoutSucceeded":true,"realActionNetworkAllowed":false}',
            'I/self-lifecycle: [self-lifecycle-json] {"event":"session_logout","accountId":7,"sourceMode":1,"logoutOnce":true,"realActionNetworkAllowed":false}',
        ])

    def test_ready_when_task_stop_and_logout_markers_exist(self):
        report = mod.verify_text(self.full_log())
        self.assertTrue(report["summary"]["selfLifecycleLogcatReady"])
        self.assertEqual(1, report["summary"]["taskStopCount"])
        self.assertEqual(1, report["summary"]["sessionLogoutCount"])
        self.assertEqual([], report["missing"])
        self.assertFalse(report["summary"]["realActionNetworkAllowed"])

    def test_missing_logout_is_reported(self):
        report = mod.verify_text('I/self-lifecycle: [self-lifecycle-json] {"event":"task_stop","realActionNetworkAllowed":false}')
        self.assertFalse(report["summary"]["selfLifecycleLogcatReady"])
        self.assertIn("self-lifecycle-json:event=session_logout", report["missing"])
        self.assertTrue(any("session_logout" in item for item in report["nextActions"]))

    def test_unsafe_true_flag_blocks_ready(self):
        text = "\n".join([
            'I/self-lifecycle: [self-lifecycle-json] {"event":"task_stop","realActionNetworkAllowed":true}',
            'I/self-lifecycle: [self-lifecycle-json] {"event":"session_logout","realActionNetworkAllowed":false}',
        ])
        report = mod.verify_text(text)
        self.assertFalse(report["summary"]["selfLifecycleLogcatReady"])
        self.assertIn("unsafe:self lifecycle realActionNetworkAllowed=true", report["missing"])

    def test_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "logcat.txt"
            out = Path(td) / "out.json"
            md = Path(td) / "out.md"
            src.write_text(self.full_log(), encoding="utf-8")
            subprocess.check_call([sys.executable, str(SCRIPT), str(src), "--out", str(out), "--markdown-out", str(md)])
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(data["summary"]["selfLifecycleLogcatReady"])
            self.assertIn("自研 self-lifecycle logcat smoke", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
