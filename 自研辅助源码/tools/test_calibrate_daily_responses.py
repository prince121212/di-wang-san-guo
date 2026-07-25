#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("calibrate_daily_responses.py")
spec = importlib.util.spec_from_file_location("calibrate_daily_responses", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["calibrate_daily_responses"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class CalibrateDailyResponsesTest(unittest.TestCase):
    def test_builds_daily_step_results_from_explicit_step(self) -> None:
        text = '[daily-response-json] {"dailyStep":"SIGN_IN","responseText":"已完成签到！"}'

        report = mod.calibrate(text)

        self.assertEqual(1, report["summary"]["captureCount"])
        self.assertEqual(1, report["summary"]["dailyStepResultCount"])
        item = report["dailyStepResults"][0]
        self.assertEqual("SIGN_IN", item["step"])
        self.assertTrue(item["success"])
        self.assertEqual("已完成签到！", item["message"])
        self.assertIn("dailyStepResultsJson", report["channelExtraCandidate"])

    def test_infers_step_from_payload_and_parses_failure(self) -> None:
        text = "\n".join([
            '{"payloadHex":"00000000000000000009113400000000000de2b100","responseText":"已领取惊喜宝箱！"}',
            '{"payloadHex":"0000000000000000000c121f000000000000000002000000","responseText":"{\\"success\\":false,\\"message\\":\\"资源不足，失败\\"}"}',
        ])

        report = mod.calibrate(text)

        self.assertEqual(2, report["summary"]["captureCount"])
        self.assertEqual(1, report["summary"]["successCount"])
        self.assertEqual(1, report["summary"]["failureCount"])
        steps = {item["step"]: item for item in report["dailyStepResults"]}
        self.assertTrue(steps["SURPRISE_BOX"]["success"])
        self.assertFalse(steps["ADD_LOYALTY"]["success"])

    def test_explicit_convert_half_food_step_uses_recovered_success_log(self) -> None:
        text = '[daily-response-json] {"dailyStep":"CONVERT_HALF_FOOD_TO_COPPER","responseText":"已转换一半粮食到铜钱！"}'

        report = mod.calibrate(text)

        self.assertEqual(1, report["summary"]["dailyStepResultCount"])
        item = report["dailyStepResults"][0]
        self.assertEqual("CONVERT_HALF_FOOD_TO_COPPER", item["step"])
        self.assertTrue(item["success"])
        self.assertEqual("已转换一半粮食到铜钱！", item["message"])

    def test_cli_writes_json_and_markdown(self) -> None:
        text = '[daily-response-json] {"dailyStep":"DONATE_TECH","responseText":"已捐献科技！"}'
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "daily.log"
            out = Path(td) / "daily.json"
            md = Path(td) / "daily.md"
            src.write_text(text + "\n", encoding="utf-8")
            subprocess.check_call([sys.executable, str(SCRIPT), str(src), "--out", str(out), "--markdown-out", str(md)])
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(1, data["summary"]["dailyStepResultCount"])
            self.assertIn("Daily Response 校准报告", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
