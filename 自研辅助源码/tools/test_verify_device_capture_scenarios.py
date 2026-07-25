#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("verify_device_capture_scenarios.py")
spec = importlib.util.spec_from_file_location("verify_device_capture_scenarios", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["verify_device_capture_scenarios"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class VerifyDeviceCaptureScenariosTest(unittest.TestCase):
    def full_log(self) -> str:
        return "\n".join([
            '[readonly-response-json] {"opcode":"0x8004","roleName":"测试君主","level":42,"copper":123456,"food":654321,"state8004TailUtf8Preview":"JiangLing{id=0000000000000007,name=赵云,status=0,tili=49}"}',
            "[java-native-ret] com.ifengwoo.dwpm.tuoji.DWSG.HelpClass.getKey => KEY",
            '[game-wrapper-call] android.o gameHex=0000000000000000000a1520030010000000000000007',
            '[native-wrapper-json] {"gameHex":"0000000000000000000a1520030010000000000000007","rawBody":"LXKEY0000000000000000000a1520030010000000000000007LB","lx":"LX","lb":"LB"}',
            '[native-wrapper-json] {"gameHex":"000000000000000000151522030010000000000000007","rawBody":"LXKEY000000000000000000151522030010000000000000007LB","lx":"LX","lb":"LB"}',
            '[base-channel-extra-json] {"generalsJson":[{"id":7,"name":"赵云","status":0,"tili":49}],"formationsJson":[{"formationId":3,"generalIds":[7],"canDispatch":true}],"selectedFormationIds":"3"}',
            '[readonly-response-json] {"opcode":"041540","responseHex":"000000000065030005000b0016E9BB84E5B7BE"}',
            '[action-response-json] {"opcode":"1522030","formationId":3,"targetId":"101","responseText":"刷黄出征成功 usedAount=1"}',
            '[self-lifecycle-json] {"event":"task_stop","sourceMode":1,"message":"停止任务"}',
            '[self-lifecycle-json] {"event":"session_logout","sourceMode":1,"message":"退出登录 logout exactly once"}',
            '[daily-response-json] {"dailyStep":"SIGN_IN","responseText":"已完成签到！"}',
            '[readonly-response-json] {"opcode":"041542","responseHex":"0000000001010101000b0016010002D00101000000270F"}',
        ])

    def test_full_capture_satisfies_required_scenarios(self):
        report = mod.verify_text(self.full_log())
        self.assertTrue(report["summary"]["captureScenarioRequiredReady"])
        self.assertEqual([], report["missingRequired"])
        self.assertFalse(report["summary"]["realActionNetworkAllowed"])

    def test_missing_scenarios_report_next_actions(self):
        report = mod.verify_text('[readonly-response-json] {"opcode":"041540"}')
        self.assertFalse(report["summary"]["captureScenarioRequiredReady"])
        self.assertIn("loginState8004", report["missingRequired"])
        self.assertIn("nativeWrapper", report["missingRequired"])
        self.assertIn("generalFormationBaseline", report["missingRequired"])
        self.assertIn("brushYellowNativeWrapper1520", report["missingRequired"])
        self.assertIn("selfStopLogout", report["missingRequired"])
        self.assertTrue(any("小黄点" in item for item in report["nextManualActions"]))

    def test_self_stop_logout_requires_stop_and_logout_evidence(self):
        report = mod.verify_text('[self-lifecycle-json] {"event":"task_stop","sourceMode":1,"message":"停止任务"}')

        self.assertFalse(report["scenarios"]["selfStopLogout"]["requiredOk"])
        self.assertIn("selfStopLogout", report["missingRequired"])

    def test_general_formation_baseline_requires_both_sides(self):
        report = mod.verify_text("\n".join([
            '[readonly-response-json] {"opcode":"0x8004","roleName":"测试君主","copper":1,"food":2}',
            '[base-channel-extra-json] {"generalsJson":[{"id":7,"name":"赵云"}]}',
        ]))

        self.assertFalse(report["scenarios"]["generalFormationBaseline"]["requiredOk"])
        self.assertIn("generalFormationBaseline", report["missingRequired"])

    def test_login_8004_requires_role_or_resource_evidence(self):
        report = mod.verify_text('[readonly-response-json] {"opcode":"0x8004","state8004TailUtf8Preview":"JiangLing{id=7,name=赵云}"}')

        self.assertFalse(report["scenarios"]["loginState8004"]["requiredOk"])
        self.assertIn("loginState8004", report["missingRequired"])

    def test_generic_wrapper_without_brush_yellow_opcodes_is_not_enough(self):
        text = "\n".join([
            "[java-native-ret] com.ifengwoo.dwpm.tuoji.DWSG.HelpClass.getKey => KEY",
            '[native-wrapper-json] {"gameHex":"aa","rawBody":"LXKEYaaLB"}',
            '[readonly-response-json] {"opcode":"041540","responseHex":"000000000065030005000b0016E9BB84E5B7BE"}',
            '[action-response-json] {"opcode":"1522030","formationId":3,"targetId":"101","responseText":"刷黄出征成功 usedAount=1"}',
            '[daily-response-json] {"dailyStep":"SIGN_IN","responseText":"已完成签到！"}',
            '[readonly-response-json] {"opcode":"041542","responseHex":"0000000001010101000b0016010002D00101000000270F"}',
        ])
        report = mod.verify_text(text)
        self.assertFalse(report["summary"]["captureScenarioRequiredReady"])
        self.assertNotIn("nativeWrapper", report["missingRequired"])
        self.assertIn("brushYellowNativeWrapper1520", report["missingRequired"])

    def test_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "device_combined.log"
            out = Path(td) / "scenario.json"
            md = Path(td) / "scenario.md"
            src.write_text(self.full_log(), encoding="utf-8")
            subprocess.check_call([sys.executable, str(SCRIPT), str(src), "--out", str(out), "--markdown-out", str(md)])
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(report["summary"]["captureScenarioRequiredReady"])
            self.assertIn("设备采集场景覆盖检查", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
