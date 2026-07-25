#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("verify_action_safety_invariants.py")
spec = importlib.util.spec_from_file_location("verify_action_safety_invariants", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["verify_action_safety_invariants"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class VerifyActionSafetyInvariantsTest(unittest.TestCase):
    def test_current_worktree_has_no_unsafe_action_gate_true(self):
        report = mod.verify(SCRIPT.parent.parent)
        self.assertTrue(report["summary"]["actionSafetyInvariantReady"])
        self.assertEqual([], report["sourceViolations"])
        self.assertEqual([], report["jsonViolations"])

    def test_detects_source_true_assignment(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "tools"
            src.mkdir()
            (src / "unsafe.py").write_text("networkSendAllowed = True\n", encoding="utf-8")
            report = mod.verify(root, source_dirs=["tools"], json_dirs=[])
            self.assertFalse(report["summary"]["actionSafetyInvariantReady"])
            self.assertEqual("networkSendAllowed", report["sourceViolations"][0]["key"])

    def test_detects_json_true_claim(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reports = root / "reports"
            reports.mkdir()
            (reports / "unsafe.json").write_text(json.dumps({"summary": {"realActionSendReady": True}}), encoding="utf-8")
            report = mod.verify(root, source_dirs=[], json_dirs=["reports"])
            self.assertFalse(report["summary"]["actionSafetyInvariantReady"])
            self.assertEqual("realActionSendReady", report["jsonViolations"][0]["key"])

    def test_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "safety.json"
            md = Path(td) / "safety.md"
            subprocess.check_call([
                sys.executable, str(SCRIPT),
                "--root", str(SCRIPT.parent.parent),
                "--out", str(out),
                "--markdown-out", str(md),
            ])
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(report["summary"]["actionSafetyInvariantReady"])
            self.assertIn("Action Safety Invariants", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
