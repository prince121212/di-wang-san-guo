#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("configure_device_shuahuang_service_plan.py")
spec = importlib.util.spec_from_file_location("configure_device_shuahuang_service_plan", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["configure_device_shuahuang_service_plan"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class ConfigureDeviceShuaHuangServicePlanTest(unittest.TestCase):
    def test_minimal_config_renders_shared_prefs_xml(self):
        xml = mod.render_config_prefs(764, mod.minimal_shuahuang_config(enabled=True, daily_limit=1))
        self.assertIn("764::shua_huang", xml)
        self.assertIn("APKTOOL_RENAMED_0x7f070073", xml)
        self.assertIn("APKTOOL_RENAMED_0x7f070163", xml)

    def test_target_to_map_targets_json_preserves_raw_record(self):
        raw = mod.target_to_map_targets_json({
            "id": 16304,
            "idHex": "000000003fb0",
            "kind": "山贼",
            "rank": 6,
            "x": 0,
            "y": 3,
            "rawRecord": "000000003FB061000A36E7BAA7E5B1B1E8B4BC",
        })
        arr = json.loads(raw)
        self.assertEqual(1, len(arr))
        self.assertEqual("000000003fb0", arr[0]["targetIdHex"])
        self.assertEqual("000000003FB061000A36E7BAA7E5B1B1E8B4BC", arr[0]["rawRecord"])


if __name__ == "__main__":
    unittest.main()
