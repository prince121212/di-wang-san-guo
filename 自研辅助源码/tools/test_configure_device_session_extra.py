#!/usr/bin/env python3
from __future__ import annotations

import html
import importlib.util
import json
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("configure_device_session_extra.py")
spec = importlib.util.spec_from_file_location("configure_device_session_extra", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["configure_device_session_extra"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class ConfigureDeviceSessionExtraTest(unittest.TestCase):
    def make_xml(self) -> str:
        root = {
            "accounts": [
                {
                    "id": 1,
                    "username": "1608600",
                    "serverName": "周年服351区(新服)",
                    "session": {
                        "tokenCiphertext": "secret-token",
                        "channelExtra": {
                            "roleName": "东方美",
                            "dm": "123",
                        },
                    },
                }
            ]
        }
        return '<map><string name="accounts_json">' + html.escape(json.dumps(root, ensure_ascii=False), quote=False) + "</string></map>"

    def test_mutates_first_account_channel_extra_and_preserves_xml(self):
        prefix, root, suffix = mod.split_accounts_xml(self.make_xml())
        account = mod.mutate_first_account_channel_extra(root, {
            "realActionNetworkAllowed": "true",
            "realActionSendReady": "true",
            "realActionScope": "brush-yellow",
        })
        rendered = mod.render_accounts_xml(prefix, root, suffix)
        _, parsed, _ = mod.split_accounts_xml(rendered)
        extra = parsed["accounts"][0]["session"]["channelExtra"]
        self.assertEqual("东方美", extra["roleName"])
        self.assertEqual("true", extra["realActionNetworkAllowed"])
        self.assertEqual("true", extra["realActionSendReady"])
        self.assertEqual("brush-yellow", extra["realActionScope"])
        self.assertEqual(1, account["id"])

    def test_default_brush_yellow_updates_include_fallback_unless_disabled(self):
        self.assertEqual("true", mod.default_brush_yellow_updates()["allowRecoveredGeneralFallbackFormation"])
        self.assertNotIn("allowRecoveredGeneralFallbackFormation", mod.default_brush_yellow_updates(enable_fallback=False))

    def test_redacts_sensitive_changed_values(self):
        _, root, _ = mod.split_accounts_xml(self.make_xml())
        account = mod.mutate_first_account_channel_extra(root, {"tokenCiphertext": "abc", "realActionScope": "brush-yellow"})
        summary = mod.redacted_account_summary(account, ["tokenCiphertext", "realActionScope"])
        self.assertEqual("***", summary["changedValuesRedacted"]["tokenCiphertext"])
        self.assertEqual("brush-yellow", summary["changedValuesRedacted"]["realActionScope"])


if __name__ == "__main__":
    unittest.main()
