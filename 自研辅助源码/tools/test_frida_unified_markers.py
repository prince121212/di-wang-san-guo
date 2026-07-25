#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRIDA = ROOT.parent / "reverse_cases" / "apk" / "scripts" / "frida_native_session_trace_v2.js"
DEVICE_REGRESSION = Path(__file__).with_name("device_regression_from_logs.py")
spec = importlib.util.spec_from_file_location("device_regression_from_logs", DEVICE_REGRESSION)
mod = importlib.util.module_from_spec(spec)
sys.modules["device_regression_from_logs"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class FridaUnifiedMarkersTest(unittest.TestCase):
    def test_frida_script_emits_unified_response_markers(self) -> None:
        text = FRIDA.read_text(encoding="utf-8")
        self.assertIn("emitUnifiedResponseMarkers", text)
        self.assertIn("[readonly-response-json]", text)
        self.assertIn("[action-response-json]", text)
        self.assertIn("[daily-response-json]", text)
        self.assertIn("extractBrushYellowDispatchFields", text)
        self.assertIn("detectDailyStep", text)

    def test_unified_markers_are_consumable_by_device_regression_tool(self) -> None:
        log = "\n".join([
            '[readonly-response-json] {"gameHex":"000000000000000000041540000b0016","opcode":"041540","responseText":"000000000065030005000b0016E9BB84E5B7BE","responseHex":"000000000065030005000b0016E9BB84E5B7BE"}',
            '[action-response-json] {"gameHex":"00000000000000000015152203001000000000000000700000000000000000065ffffffffffffffff000000","opcode":"1522030","responseText":"刷黄出征成功！继续搜索... usedAount=1"}',
            '[daily-response-json] {"gameHex":"000000000000000000006200","opcode":"daily-sign-in","dailyStep":"SIGN_IN","payloadHex":"000000000000000000006200","responseText":"已完成签到！"}',
        ])
        report = mod.calibrate_all(log, base_extra={
            "userId": "u1",
            "serverUrl": "http://game.example",
            "roleName": "测试君主",
            "level": "42",
            "copper": "123",
            "food": "456",
            "state8004TailUtf8Preview": "JiangLing{id=0000000000000007,name=赵云,status=0,tili=49}",
            "xiaohuangPrefsJson": "{\"shuahuangChuzhengBiandui0\":true,\"bianduihao0\":\"0000000000000003\",\"bianduiDejiangling0\":\"0000000000000007\"}",
        })
        self.assertEqual(1, report["summary"]["targetParsedCount"])
        self.assertEqual(1, report["summary"]["actionCaptureCount"])
        self.assertEqual(1, report["summary"]["dailyStepResultCount"])
        self.assertEqual(1, report["summary"]["dispatchResultCount"])
        self.assertIn("mapTargetsHex", report["mergedChannelExtra"])
        self.assertIn("dailyStepResultsJson", report["mergedChannelExtra"])
        self.assertIn("dispatchResultsJson", report["mergedChannelExtra"])


if __name__ == "__main__":
    unittest.main()
