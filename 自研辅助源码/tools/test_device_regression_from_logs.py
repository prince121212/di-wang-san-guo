#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("device_regression_from_logs.py")
spec = importlib.util.spec_from_file_location("device_regression_from_logs", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["device_regression_from_logs"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class DeviceRegressionFromLogsTest(unittest.TestCase):
    def sample_log(self) -> str:
        return "\n".join([
            '[readonly-response-json] {"opcode":"0x8004","roleName":"日志君主","level":42,"copper":123456,"food":654321,"state8004TailUtf8Preview":"JiangLing{id=0000000000000007,name=赵云,status=0,tili=49}"}',
            "[java-native-ret] com.ifengwoo.dwpm.tuoji.DWSG.HelpClass.getKey => KEY",
            '[native-wrapper-json] {"source":"body","threadId":"1","gameHex":"0000000000000000000a1520030010000000000000007","rawBody":"LXKEY0000000000000000000a1520030010000000000000007LB","lx":"LX","lb":"LB"}',
            '[native-wrapper-json] {"source":"body","threadId":"1","gameHex":"000000000000000000151522030010000000000000007","rawBody":"LXKEY000000000000000000151522030010000000000000007LB","lx":"LX","lb":"LB"}',
            '[base-channel-extra-json] {"generalsJson":[{"id":7,"name":"赵云","status":0,"tili":49}],"formationsJson":[{"formationId":3,"generalIds":[7],"canDispatch":true}],"selectedFormationIds":"3"}',
            '[readonly-response-json] {"opcode":"041540","responseHex":"000000000065030005000b0016E9BB84E5B7BE"}',
            '[readonly-response-json] {"opcode":"041542","responseHex":"0000000001010105000B00160100"}',
            '[action-response-json] {"opcode":"1522030","formationId":3,"targetId":"101","responseText":"刷黄出征成功！继续搜索... usedAount=1"}',
            '[self-lifecycle-json] {"event":"task_stop","sourceMode":1,"message":"停止任务"}',
            '[self-lifecycle-json] {"event":"session_logout","sourceMode":1,"message":"退出登录 logout exactly once"}',
            '[daily-response-json] {"dailyStep":"SIGN_IN","responseText":"已完成签到！"}',
        ])

    def base_extra(self) -> dict[str, str]:
        return {
            "userId": "u1",
            "serverUrl": "http://game.example",
            "roleName": "测试君主",
            "level": "42",
            "copper": "123456",
            "food": "654321",
            "state8004TailUtf8Preview": "JiangLing{id=0000000000000007,name=赵云,status=0,tili=49}",
            "xiaohuangPrefsJson": "{\"shuahuangChuzhengBiandui0\":true,\"bianduihao0\":\"0000000000000003\",\"bianduiDejiangling0\":\"0000000000000007\"}",
        }

    def test_aggregates_all_calibrations_and_merges_channel_extra(self) -> None:
        report = mod.calibrate_all(self.sample_log())

        self.assertTrue(report["summary"]["nativeTraceHasMethods"])
        self.assertEqual(2, report["summary"]["nativeWrapperCaptureCount"])
        self.assertTrue(report["summary"]["nativeWrapperFieldAuditReady"])
        self.assertFalse(report["summary"]["resourcePointWrapperCoverageComplete"])
        self.assertFalse(report["summary"]["withdrawDefenseWrapperCoverageComplete"])
        self.assertEqual(1, report["summary"]["targetParsedCount"])
        self.assertEqual(1, report["summary"]["mineParsedCount"])
        self.assertEqual(1, report["summary"]["dispatchResultCount"])
        self.assertEqual(1, report["summary"]["dailyStepResultCount"])
        self.assertTrue(report["summary"]["captureScenarioRequiredReady"])
        self.assertTrue(report["summary"]["loginState8004RequiredOk"])
        self.assertTrue(report["summary"]["loginState8004RoleResourceRecovered"])
        self.assertTrue(report["summary"]["offlineReplayReady"])
        self.assertFalse(report["summary"]["shuaHuangOfflineReplayReady"])
        self.assertFalse(report["summary"]["shuaHuangOfflineClosedLoopReplayReady"])
        self.assertFalse(report["summary"]["dailyOfflineClosedLoopReplayReady"])
        self.assertFalse(report["summary"]["mineOfflineClosedLoopReplayReady"])
        self.assertFalse(report["summary"]["fullOfflineReplayReady"])
        self.assertFalse(report["summary"]["dryRunActionEvidenceReady"])
        self.assertFalse(report["summary"]["realActionNetworkAllowed"])
        extra = report["mergedChannelExtra"]
        self.assertEqual("日志君主", extra["roleName"])
        self.assertEqual("123456", extra["copper"])
        self.assertIn("mapTargetsHex", extra)
        self.assertIn("mineTargetsHex", extra)
        self.assertIn("dispatchResultsJson", extra)
        self.assertIn("dailyStepResultsJson", extra)
        self.assertIn("replayContract", report)
        self.assertIn("shuaHuangOfflineReplay", report)
        self.assertIn("dailyOfflineReplay", report)
        self.assertIn("mineOfflineReplay", report)
        self.assertIn("fullOfflineReplay", report)
        self.assertIn("actionGateReadiness", report)
        self.assertIn("captureScenarioCoverage", report)
        self.assertIn("identity:userId/serverUrl", report["replayContract"]["missing"]["shuaHuang"])

    def test_reports_resource_point_and_withdraw_wrapper_coverage(self) -> None:
        extra_log = "\n".join([
            self.sample_log(),
            '[native-wrapper-json] {"source":"body","threadId":"1","gameHex":"000000000000000000121520010100000000000000070000000000000101","rawBody":"LXKEY000000000000000000121520010100000000000000070000000000000101LB","lx":"LX","lb":"LB"}',
            '[native-wrapper-json] {"source":"body","threadId":"1","gameHex":"0000000000000000001d1522010100000000000000070000000000000101ffffffffffffffff000000","rawBody":"LXKEY0000000000000000001d1522010100000000000000070000000000000101ffffffffffffffff000000LB","lx":"LX","lb":"LB"}',
            '[native-wrapper-json] {"source":"body","threadId":"1","gameHex":"0000000000000000000a152601010000000000000007","rawBody":"LXKEY0000000000000000000a152601010000000000000007LB","lx":"LX","lb":"LB"}',
        ])

        report = mod.calibrate_all(extra_log, base_extra=self.base_extra())

        self.assertTrue(report["summary"]["resourcePointWrapperCoverageComplete"])
        self.assertTrue(report["summary"]["withdrawDefenseWrapperCoverageComplete"])
        remaining = report["nativeWrapperCalibration"]["summary"]["remainingActionWrapperDetails"]
        self.assertTrue(remaining["resourcePoint"]["splitProvenForBothStages"])
        self.assertTrue(remaining["withdrawDefense"]["splitProven"])

    def test_base_extra_drives_strict_replay_contract_readiness(self) -> None:
        report = mod.calibrate_all(self.sample_log(), base_extra=self.base_extra())

        self.assertTrue(report["summary"]["offlineReplayReady"])
        self.assertTrue(report["summary"]["shuaHuangOfflineReplayReady"])
        self.assertTrue(report["summary"]["shuaHuangOfflineClosedLoopReplayReady"])
        self.assertTrue(report["summary"]["dailyOfflineReplayReady"])
        self.assertTrue(report["summary"]["dailyOfflineClosedLoopReplayReady"])
        self.assertTrue(report["summary"]["mineOfflineReplayReady"])
        self.assertTrue(report["summary"]["mineOfflineClosedLoopReplayReady"])
        self.assertTrue(report["summary"]["mineReadOnlyEvidenceReady"])
        self.assertTrue(report["summary"]["mineSelectionEvidenceReady"])
        self.assertTrue(report["summary"]["fullOfflineReplayReady"])
        self.assertTrue(report["summary"]["dryRunActionEvidenceReady"])
        self.assertFalse(report["actionGateReadiness"]["summary"]["realActionSendReady"])
        self.assertEqual([], report["replayContract"]["missing"]["shuaHuang"])
        self.assertEqual([], report["shuaHuangOfflineReplay"]["missingSteps"])
        self.assertEqual([], report["fullOfflineReplay"]["missingSuites"])

    def test_cli_writes_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "device.log"
            base = Path(td) / "base_channel_extra.json"
            out_dir = Path(td) / "out"
            src.write_text(self.sample_log() + "\n", encoding="utf-8")
            base.write_text(json.dumps(self.base_extra(), ensure_ascii=False), encoding="utf-8")
            subprocess.check_call([
                sys.executable, str(SCRIPT), str(src),
                "--base-channel-extra", str(base),
                "--out-dir", str(out_dir),
            ])
            data = json.loads((out_dir / "device_regression_report.json").read_text(encoding="utf-8"))
            self.assertTrue(data["summary"]["offlineReplayReady"])
            self.assertTrue(data["summary"]["shuaHuangOfflineReplayReady"])
            self.assertTrue((out_dir / "summary.md").exists())
            self.assertTrue((out_dir / "merged_channel_extra.json").exists())
            self.assertTrue((out_dir / "replay_contract.json").exists())
            self.assertTrue((out_dir / "replay_contract.md").exists())
            self.assertTrue((out_dir / "shuahuang_offline_replay.json").exists())
            self.assertTrue((out_dir / "shuahuang_offline_replay.md").exists())
            self.assertTrue((out_dir / "daily_offline_replay.json").exists())
            self.assertTrue((out_dir / "daily_offline_replay.md").exists())
            self.assertTrue((out_dir / "mine_offline_replay.json").exists())
            self.assertTrue((out_dir / "mine_offline_replay.md").exists())
            self.assertTrue((out_dir / "full_offline_replay.json").exists())
            self.assertTrue((out_dir / "full_offline_replay.md").exists())
            self.assertTrue((out_dir / "capture_scenario_coverage.json").exists())
            self.assertTrue((out_dir / "capture_scenario_coverage.md").exists())
            self.assertTrue((out_dir / "action_gate_readiness.json").exists())
            self.assertTrue((out_dir / "action_gate_readiness.md").exists())
            self.assertIn("设备日志离线回归汇总", (out_dir / "summary.md").read_text(encoding="utf-8"))
            self.assertIn("Replay contract missing", (out_dir / "summary.md").read_text(encoding="utf-8"))
            self.assertIn("Capture scenario missing required", (out_dir / "summary.md").read_text(encoding="utf-8"))
            self.assertIn("ShuaHuang offline replay missing steps", (out_dir / "summary.md").read_text(encoding="utf-8"))
            self.assertIn("Daily offline replay missing steps", (out_dir / "summary.md").read_text(encoding="utf-8"))
            self.assertIn("Mine offline replay missing steps", (out_dir / "summary.md").read_text(encoding="utf-8"))
            self.assertIn("fullOfflineReplayReady", (out_dir / "summary.md").read_text(encoding="utf-8"))
            self.assertIn("Action gate readiness missing hard evidence", (out_dir / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
