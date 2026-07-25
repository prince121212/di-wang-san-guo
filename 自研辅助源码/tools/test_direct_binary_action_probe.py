#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("direct_binary_action_probe.py")
spec = importlib.util.spec_from_file_location("direct_binary_action_probe", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["direct_binary_action_probe"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class DirectBinaryActionProbeTest(unittest.TestCase):
    def test_action_target_hex_uses_live_calibrated_raw_record_prefix(self):
        target = {
            "id": 16064,
            "idHex": "000000003ec0",
            "rawRecord": "000000003EC063000A31E7BAA7E5B1B1E8B4BC",
        }
        self.assertEqual("0000003ec063000a", mod.action_target_hex(target))

    def test_action_target_hex_falls_back_to_padded_id_hex(self):
        self.assertEqual("0000000000003ec0", mod.action_target_hex({"id": 16064, "idHex": "3ec0"}))


if __name__ == "__main__":
    unittest.main()
