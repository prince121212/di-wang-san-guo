#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("calibrate_action_responses.py")
spec = importlib.util.spec_from_file_location("calibrate_action_responses", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["calibrate_action_responses"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class CalibrateActionResponsesTest(unittest.TestCase):
    def test_builds_dispatch_results_from_brush_yellow_expedition_json(self) -> None:
        text = '[action-response-json] {"opcode":"1522030","formationId":3,"targetId":"101","targetIdHex":"0000000000000065","generalIdHexChunks":["0000000000000007"],"responseText":"刷黄出征成功！继续搜索... usedAount=18"}'

        report = mod.calibrate(text)

        self.assertEqual(1, report["summary"]["captureCount"])
        self.assertEqual(1, report["summary"]["dispatchResultCount"])
        item = report["dispatchResults"][0]
        self.assertEqual(3, item["formationId"])
        self.assertEqual("101", item["targetId"])
        self.assertTrue(item["success"])
        self.assertEqual(18, item["consumedTimes"])
        self.assertIn("dispatchResultsJson", report["channelExtraCandidate"])
        dispatch_json = json.loads(report["channelExtraCandidate"]["dispatchResultsJson"])
        self.assertEqual("0000000000000007", dispatch_json[0]["generalIdHexChunks"][0])

    def test_parses_failure_and_hex_success(self) -> None:
        success_hex = "E588B7E9BB84E587BAE5BE81E68890E58A9F"
        text = "\n".join([
            '{"opcode":"1522030","formationId":3,"targetId":"101","responseHex":"%s"}' % success_hex,
            '{"opcode":"1522030","formationId":3,"targetId":"102","responseText":"{\\"success\\":false,\\"message\\":\\"体力不足，出征失败\\"}"}',
        ])

        report = mod.calibrate(text)

        self.assertEqual(2, report["summary"]["captureCount"])
        self.assertEqual(1, report["summary"]["successCount"])
        self.assertEqual(1, report["summary"]["failureCount"])
        self.assertEqual("hex->success-marker:刷黄出征成功", report["captures"][0]["evidence"])
        self.assertEqual("failure-marker:失败", report["captures"][1]["evidence"])


    def test_infers_dispatch_result_from_game_hex_and_base_prefs(self) -> None:
        game_hex = "00000000000000000015152203001000000000000000700000000000000000065ffffffffffffffff000000"
        text = '[action-response-json] {"opcode":"1522030","gameHex":"%s","responseText":"刷黄出征成功！继续搜索... usedAount=2"}' % game_hex
        base_extra = {
            "xiaohuangPrefsJson": "{\"shuahuangChuzhengBiandui0\":true,\"bianduihao0\":\"0000000000000003\",\"bianduiDejiangling0\":\"0000000000000007\"}"
        }

        report = mod.calibrate(text, base_extra=base_extra)

        self.assertEqual(1, report["summary"]["dispatchResultCount"])
        self.assertEqual(1, report["summary"]["dispatchResultInferredFormationCount"])
        item = report["dispatchResults"][0]
        self.assertEqual(3, item["formationId"])
        self.assertEqual("101", item["targetId"])
        self.assertEqual("0000000000000065", item["targetIdHex"])
        self.assertEqual(["0000000000000007"], item["generalIdHexChunks"])
        self.assertTrue(item["raw"]["formationIdInferred"])

    def test_ambiguous_base_prefs_do_not_infer_formation(self) -> None:
        game_hex = "00000000000000000015152203001000000000000000700000000000000000065ffffffffffffffff000000"
        text = '[action-response-json] {"opcode":"1522030","gameHex":"%s","responseText":"刷黄出征成功！"}' % game_hex
        base_extra = {
            "xiaohuangPrefsJson": "{\"shuahuangChuzhengBiandui0\":true,\"bianduihao0\":\"0000000000000003\",\"bianduiDejiangling0\":\"0000000000000008\",\"shuahuangChuzhengBiandui1\":true,\"bianduihao1\":\"0000000000000004\",\"bianduiDejiangling1\":\"0000000000000009\"}"
        }

        report = mod.calibrate(text, base_extra=base_extra)

        self.assertEqual(0, report["summary"]["dispatchResultCount"])

    def test_cli_writes_json_and_markdown(self) -> None:
        text = '[action-response-json] {"opcode":"1522030","formationId":3,"targetId":"101","responseText":"刷黄出征成功！"}'
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "action.log"
            out = Path(td) / "action.json"
            md = Path(td) / "action.md"
            src.write_text(text + "\n", encoding="utf-8")
            subprocess.check_call([sys.executable, str(SCRIPT), str(src), "--out", str(out), "--markdown-out", str(md)])
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(1, data["summary"]["dispatchResultCount"])
            self.assertIn("Action Response 校准报告", md.read_text(encoding="utf-8"))

    def test_cli_can_infer_formation_with_base_channel_extra(self) -> None:
        game_hex = "00000000000000000015152203001000000000000000700000000000000000065ffffffffffffffff000000"
        text = '[action-response-json] {"opcode":"1522030","gameHex":"%s","responseText":"刷黄出征成功！"}' % game_hex
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "action.log"
            base = Path(td) / "base_channel_extra.json"
            out = Path(td) / "action.json"
            src.write_text(text + "\n", encoding="utf-8")
            base.write_text(json.dumps({
                "baseChannelExtra": {
                    "xiaohuangPrefsJson": "{\"shuahuangChuzhengBiandui0\":true,\"bianduihao0\":\"0000000000000003\",\"bianduiDejiangling0\":\"0000000000000007\"}"
                }
            }, ensure_ascii=False), encoding="utf-8")

            subprocess.check_call([
                sys.executable, str(SCRIPT), str(src),
                "--base-channel-extra", str(base),
                "--out", str(out),
            ])

            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(1, data["summary"]["dispatchResultCount"])
            self.assertEqual(1, data["summary"]["dispatchResultInferredFormationCount"])
            self.assertEqual(3, data["dispatchResults"][0]["formationId"])
            self.assertTrue(data["dispatchResults"][0]["raw"]["formationIdInferred"])


if __name__ == "__main__":
    unittest.main()
