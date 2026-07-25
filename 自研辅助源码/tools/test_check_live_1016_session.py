#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("check_live_1016_session.py")
spec = importlib.util.spec_from_file_location("check_live_1016_session", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["check_live_1016_session"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class CheckLive1016SessionTest(unittest.TestCase):
    def test_classifies_8004_as_fresh(self):
        fresh, expired, reason = mod.classify([{"opcodeHex": "0x8004", "textPreview": "东方美"}])
        self.assertTrue(fresh)
        self.assertFalse(expired)
        self.assertIn("0x8004", reason)

    def test_classifies_8016_without_role_as_expired(self):
        fresh, expired, reason = mod.classify([{"opcodeHex": "0x8016", "textPreview": "没有角色信息"}])
        self.assertFalse(fresh)
        self.assertTrue(expired)
        self.assertIn("没有角色信息", reason)

    def test_markdown_contains_session_flags(self):
        md = mod.to_markdown({
            "checkedAtMillis": 1,
            "package": "pkg",
            "accountId": 2,
            "roleName": "君主",
            "roleId": 3,
            "serverName": "区服",
            "http": 200,
            "responseBytes": 10,
            "opcodes": ["0x8016"],
            "sessionFresh": False,
            "sessionExpiredEvidence": True,
            "reason": "expired",
            "packets": [],
        })
        self.assertIn("sessionFresh: false", md)
        self.assertIn("sessionExpiredEvidence: true", md)


if __name__ == "__main__":
    unittest.main()
