#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("prepare_base_channel_extra.py")
spec = importlib.util.spec_from_file_location("prepare_base_channel_extra", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["prepare_base_channel_extra"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class PrepareBaseChannelExtraTest(unittest.TestCase):
    def account_export(self):
        return {
            "schema_version": "0.2-real-protocol-accounts",
            "accounts": [
                {
                    "id": 7,
                    "displayName": "测试君主",
                    "username": "u",
                    "encryptedPassword": "secret",
                    "serverName": "s1",
                    "session": {
                        "accountId": 7,
                        "tokenCiphertext": "token-secret",
                        "sourceMode": 1,
                        "channelExtra": {
                            "userId": "u1",
                            "serverUrl": "http://game.example",
                            "roleName": "测试君主",
                            "level": "42",
                            "copper": "123456",
                            "food": "654321",
                            "state8004TailUtf8Preview": "JiangLing{id=0000000000000007,name=赵云,status=0,tili=49}",
                            "xiaohuangPrefsJson": "{\"shuahuangChuzhengBiandui0\":true,\"bianduihao0\":\"0000000000000003\",\"bianduiDejiangling0\":\"0000000000000007\"}",
                        },
                    },
                    "enabled": True,
                    "loginState": "REAL_PROTOCOL_LOGIN_OK",
                }
            ],
        }

    def calibration_extra(self):
        return {
            "mapTargetsHex": "000000000065030005000b0016E9BB84E5B7BE",
            "dispatchResultsJson": "[{\"formationId\":3,\"targetId\":\"101\",\"success\":true}]",
            "mineTargetsHex": "0000000001010105000B00160100",
            "dailyStepResultsJson": "[{\"step\":\"SIGN_IN\",\"success\":true}]",
        }

    def test_extracts_safe_channel_extra_from_account_export(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "accounts.json"
            src.write_text(json.dumps(self.account_export(), ensure_ascii=False), encoding="utf-8")
            report = mod.prepare(src)
            extra = report["baseChannelExtra"]
            self.assertEqual("u1", extra["userId"])
            self.assertEqual("1", extra["sourceMode"])
            self.assertEqual("false", extra["networkSendAllowed"])
            self.assertNotIn("tokenCiphertext", extra)
            self.assertNotIn("encryptedPassword", extra)
            self.assertFalse(report["summary"]["shuaHuangOfflineReplayReady"])
            self.assertIn("mapTargets/041540:parseable", report["replayContract"]["missing"]["shuaHuang"])

    def test_merge_calibration_extra_can_satisfy_strict_contract(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "accounts.json"
            merge = Path(td) / "merged_channel_extra.json"
            src.write_text(json.dumps(self.account_export(), ensure_ascii=False), encoding="utf-8")
            merge.write_text(json.dumps(self.calibration_extra(), ensure_ascii=False), encoding="utf-8")
            report = mod.prepare(src, merge_files=[str(merge)])
            self.assertTrue(report["summary"]["shuaHuangOfflineReplayReady"])
            self.assertTrue(report["summary"]["dailyOfflineReplayReady"])
            self.assertTrue(report["summary"]["mineOfflineReplayReady"])

    def test_enriches_role_resource_from_state8004_evidence(self):
        export = self.account_export()
        extra = export["accounts"][0]["session"]["channelExtra"]
        for key in ("roleName", "level", "copper", "food"):
            extra.pop(key, None)
        extra["state8004TailUtf8Preview"] = (
            "君主名=证据君主|君主等级=47|铜钱=321000|粮食=654000|"
            "JiangLing{id=0000000000000007,name=赵云,status=0,tili=49}"
        )
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "accounts.json"
            src.write_text(json.dumps(export, ensure_ascii=False), encoding="utf-8")
            report = mod.prepare(src)
            extra = report["baseChannelExtra"]
            self.assertEqual("证据君主", extra["roleName"])
            self.assertEqual("47", extra["level"])
            self.assertEqual("321000", extra["copper"])
            self.assertEqual("654000", extra["food"])

    def test_cli_writes_base_and_reports(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "accounts.json"
            merge = Path(td) / "merged_channel_extra.json"
            out = Path(td) / "base_channel_extra.json"
            report_out = Path(td) / "base_report.json"
            md = Path(td) / "base_report.md"
            src.write_text(json.dumps(self.account_export(), ensure_ascii=False), encoding="utf-8")
            merge.write_text(json.dumps(self.calibration_extra(), ensure_ascii=False), encoding="utf-8")
            subprocess.check_call([
                sys.executable, str(SCRIPT), str(src),
                "--merge-extra", str(merge),
                "--out", str(out),
                "--report-out", str(report_out),
                "--markdown-out", str(md),
            ])
            extra = json.loads(out.read_text(encoding="utf-8"))
            report = json.loads(report_out.read_text(encoding="utf-8"))
            self.assertEqual("false", extra["baseChannelExtraNetworkSendAllowed"])
            self.assertTrue(report["summary"]["shuaHuangOfflineReplayReady"])
            self.assertIn("Base ChannelExtra 准备报告", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
