#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("replay_shuahuang_offline.py")
spec = importlib.util.spec_from_file_location("replay_shuahuang_offline", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["replay_shuahuang_offline"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class ReplayShuaHuangOfflineTest(unittest.TestCase):
    def complete_extra(self):
        return {
            "userId": "u10001",
            "serverUrl": "http://game.example",
            "roleName": "测试君主",
            "level": "42",
            "copper": "123456",
            "food": "654321",
            "state8004TailUtf8Preview": "JiangLing{id=0000000000000007,name=赵云,status=0,tili=49,daiBingLimit=1999,isPeiBingFail=false}",
            "xiaohuangPrefsJson": json.dumps({
                "shuahuangChuzhengBiandui0": True,
                "bianduihao0": "0000000000000003",
                "bianduiDejiangling0": "0000000000000007",
                "bingli0": "1999",
            }, ensure_ascii=False),
            "mapTargetsHex": "000000000065030005000b0016E9BB84E5B7BE",
            "dispatchResultsJson": json.dumps([{
                "formationId": 3,
                "targetId": "101",
                "success": True,
                "responseText": "刷黄出征成功！继续搜索... usedAount=1",
            }], ensure_ascii=False),
            "networkSendAllowed": "false",
        }

    def test_replays_minimum_closed_loop(self):
        report = mod.replay(self.complete_extra(), target_type="HUANG_JIN", start_x=11, start_y=22)
        self.assertTrue(report["summary"]["shuaHuangOfflineClosedLoopReplayReady"])
        self.assertEqual(3, report["summary"]["selectedFormationId"])
        self.assertEqual(101, report["summary"]["selectedTargetId"])
        self.assertTrue(report["summary"]["dispatchMatched"])
        self.assertTrue(report["summary"]["targetSelectionEvidence"]["targetSelectionEvidenceReady"])
        self.assertTrue(report["summary"]["targetSelectionEvidence"]["strictTargetTypeMatch"])
        self.assertEqual("HUANG_JIN", report["summary"]["targetSelectionEvidence"]["targetTypeConfigured"])
        self.assertEqual(1, report["summary"]["targetSelectionEvidence"]["typeMatchedCount"])
        payload = report["summary"]["dispatchPayloadEvidence"]
        self.assertTrue(payload["dispatchPayloadEvidenceReady"])
        self.assertEqual(["0000000000000007"], payload["generalIdHexChunks"])
        self.assertEqual("0000000000000065", payload["targetIdHex"])
        self.assertEqual("12", payload["prepareLengthHex"])
        self.assertEqual("1d", payload["expeditionLengthHex"])
        self.assertEqual(
            "0000000000000000001215200301000000000000000700000000000000000065",
            payload["preparePayload"],
        )
        self.assertEqual(
            "0000000000000000001d15220301000000000000000700000000000000000065ffffffffffffffff000000",
            payload["expeditionPayload"],
        )
        self.assertEqual([], report["missingSteps"])

    def test_replays_role_resource_from_state8004_evidence_when_top_level_missing(self):
        extra = self.complete_extra()
        for key in ("roleName", "level", "copper", "food"):
            extra.pop(key, None)
        extra["state8004TailUtf8Preview"] = (
            "君主名=证据君主|君主等级=47|铜钱=321000|粮食=654000|"
            "JiangLing{id=0000000000000007,name=赵云,status=0,tili=49,daiBingLimit=1999,isPeiBingFail=false}"
        )

        report = mod.replay(extra, target_type="HUANG_JIN", start_x=11, start_y=22)

        self.assertTrue(report["summary"]["shuaHuangOfflineClosedLoopReplayReady"])
        role_step = next(step for step in report["steps"] if step["step"] == "role/resource")
        self.assertTrue(role_step["ok"])

    def test_missing_dispatch_match_blocks_closed_loop(self):
        extra = self.complete_extra()
        extra["dispatchResultsJson"] = '[{"formationId":9,"targetId":"999","success":true}]'
        report = mod.replay(extra, target_type="HUANG_JIN", start_x=11, start_y=22)
        self.assertFalse(report["summary"]["shuaHuangOfflineClosedLoopReplayReady"])
        self.assertIn("dispatchResult/1522030", report["missingSteps"])

    def test_target_filter_is_applied_before_dispatch_match(self):
        extra = self.complete_extra()
        extra["mapTargetsJson"] = json.dumps([
            {"id": 101, "x": 11, "y": 22, "type": "黄巾", "level": 9},
            {"id": 102, "x": 30, "y": 30, "type": "黄巾", "level": 1, "drop": "令牌"},
        ], ensure_ascii=False)
        extra["mapTargetsHex"] = ""
        extra["shuaHuangMaxTargetLevel"] = "1"
        extra["shuaHuangRequiredKeywords"] = "令牌"
        extra["dispatchResultsJson"] = json.dumps([{
            "formationId": 3,
            "targetId": "102",
            "success": True,
            "responseText": "刷黄出征成功！继续搜索... usedAount=1",
        }], ensure_ascii=False)

        report = mod.replay(extra, target_type="HUANG_JIN", start_x=11, start_y=22)

        self.assertTrue(report["summary"]["shuaHuangOfflineClosedLoopReplayReady"])
        self.assertEqual(102, report["summary"]["selectedTargetId"])
        self.assertEqual(1, report["summary"]["appliedTargetFilter"]["maxLevel"])
        self.assertEqual(["令牌"], report["summary"]["appliedTargetFilter"]["requiredKeywords"])
        self.assertTrue(report["summary"]["targetSelectionEvidence"]["filterActive"])
        self.assertEqual(1, report["summary"]["targetSelectionEvidence"]["filterMatchedCount"])
        self.assertEqual(1, report["summary"]["targetSelectionEvidence"]["typeMatchedCount"])

    def test_map_target_alias_fields_replay_as_huang_and_shan(self):
        extra = self.complete_extra()
        extra["mapTargetsHex"] = ""
        extra["mapTargetsJson"] = json.dumps([
            {
                "targetIdHex": "0000000000000065",
                "coordX": 11,
                "coordY": 22,
                "targetKind": "渠帅",
                "targetLevel": 11,
                "rawRecord": "041540-captured-target",
            },
            {
                "targetID": "102",
                "kv": 33,
                "kw": 44,
                "kind": "山贼",
                "level": 4,
            },
        ], ensure_ascii=False)

        huang = mod.replay(extra, target_type="HUANG_JIN", start_x=11, start_y=22)
        self.assertTrue(huang["summary"]["shuaHuangOfflineClosedLoopReplayReady"])
        self.assertEqual(101, huang["summary"]["selectedTargetId"])
        self.assertEqual("渠帅", huang["selected"]["target"]["type"])
        self.assertEqual(11, huang["selected"]["target"]["x"])
        self.assertEqual(22, huang["selected"]["target"]["y"])
        self.assertEqual("041540-captured-target", huang["selected"]["target"]["raw"]["rawRecord"])

        extra["dispatchResultsJson"] = json.dumps([{
            "formationId": 3,
            "targetId": "102",
            "success": True,
            "responseText": "刷黄出征成功！继续搜索... usedAount=1",
        }], ensure_ascii=False)
        shan = mod.replay(extra, target_type="SHAN_ZEI", start_x=33, start_y=44)
        self.assertTrue(shan["summary"]["shuaHuangOfflineClosedLoopReplayReady"])
        self.assertEqual(102, shan["summary"]["selectedTargetId"])
        self.assertEqual("山贼", shan["selected"]["target"]["type"])

    def test_huang_target_selection_does_not_fallback_to_shan_zei(self):
        extra = self.complete_extra()
        extra["mapTargetsHex"] = ""
        extra["mapTargetsJson"] = json.dumps([
            {"id": 102, "x": 33, "y": 44, "kind": "山贼", "level": 4}
        ], ensure_ascii=False)
        extra["dispatchResultsJson"] = json.dumps([{
            "formationId": 3,
            "targetId": "102",
            "success": True,
            "responseText": "刷黄出征成功！继续搜索... usedAount=1",
        }], ensure_ascii=False)

        report = mod.replay(extra, target_type="HUANG_JIN", start_x=33, start_y=44)

        self.assertFalse(report["summary"]["shuaHuangOfflineClosedLoopReplayReady"])
        self.assertIn("chooseTarget", report["missingSteps"])
        self.assertIn("dispatchResult/1522030", report["missingSteps"])
        self.assertIsNone(report["summary"]["selectedTargetId"])
        self.assertFalse(report["summary"]["targetSelectionEvidence"]["targetSelectionEvidenceReady"])
        self.assertEqual(0, report["summary"]["targetSelectionEvidence"]["typeMatchedCount"])

    def test_dispatch_match_accepts_alias_fields_and_response_body(self):
        extra = self.complete_extra()
        extra["dispatchResultsJson"] = json.dumps([{
            "bianduihao": "0000000000000003",
            "targetIdHex": "0000000000000065",
            "status": "成功",
            "usedCount": 2,
            "responseBody": "刷黄出征成功！继续搜索... usedCount=2",
        }], ensure_ascii=False)

        report = mod.replay(extra, target_type="HUANG_JIN", start_x=11, start_y=22)

        self.assertTrue(report["summary"]["shuaHuangOfflineClosedLoopReplayReady"])
        self.assertTrue(report["summary"]["dispatchMatched"])
        self.assertTrue(report["summary"]["dispatchSuccess"])
        self.assertEqual("0000000000000003", report["selected"]["dispatch"]["bianduihao"])
        self.assertEqual("0000000000000065", report["selected"]["dispatch"]["targetIdHex"])

    def test_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "extra.json"
            out = Path(td) / "replay.json"
            md = Path(td) / "replay.md"
            src.write_text(json.dumps(self.complete_extra(), ensure_ascii=False), encoding="utf-8")
            subprocess.check_call([
                sys.executable, str(SCRIPT), str(src),
                "--start-x", "11", "--start-y", "22",
                "--out", str(out), "--markdown-out", str(md),
            ])
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(report["summary"]["shuaHuangOfflineClosedLoopReplayReady"])
            md_text = md.read_text(encoding="utf-8")
            self.assertIn("刷黄离线闭环回放报告", md_text)
            self.assertIn("Target selection evidence", md_text)
            self.assertIn("Dispatch payload evidence", md_text)


if __name__ == "__main__":
    unittest.main()
