#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("verify_replay_contract.py")
spec = importlib.util.spec_from_file_location("verify_replay_contract", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["verify_replay_contract"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class VerifyReplayContractTest(unittest.TestCase):
    def complete_extra(self):
        return {
            "userId": "u1",
            "serverUrl": "http://game.example",
            "roleName": "测试君主",
            "level": "42",
            "copper": "123456",
            "food": "654321",
            "state8004TailUtf8Preview": "JiangLing{id=0000000000000007,name=赵云,status=0,tili=49}",
            "xiaohuangPrefsJson": "{\"shuahuangChuzhengBiandui0\":true,\"bianduihao0\":\"0000000000000003\",\"bianduiDejiangling0\":\"0000000000000007\"}",
            "mapTargetsHex": "000000000065030005000b0016E9BB84E5B7BE",
            "dispatchResultsJson": "[{\"formationId\":3,\"targetId\":\"101\",\"success\":true}]",
            "mineTargetsHex": "0000000001010105000B00160100",
            "dailyStepResultsJson": "[{\"step\":\"SIGN_IN\",\"success\":true}]",
            "deviceRegressionNetworkSendAllowed": "false",
        }

    def test_complete_extra_is_ready_for_offline_replay(self):
        report = mod.verify(self.complete_extra())
        self.assertTrue(report["summary"]["shuaHuangOfflineReplayReady"])
        self.assertTrue(report["summary"]["dailyOfflineReplayReady"])
        self.assertTrue(report["summary"]["mineOfflineReplayReady"])
        self.assertTrue(report["summary"]["roleResourceParseReady"])
        self.assertTrue(report["summary"]["generalEvidenceParseReady"])
        self.assertTrue(report["summary"]["state8004GeneralEvidenceReady"])
        self.assertEqual("state8004TailUtf8Preview", report["evidence"]["generalEvidence"]["generalEvidenceSource"])
        self.assertGreaterEqual(report["evidence"]["generalEvidence"]["generalEvidenceCount"], 1)
        self.assertFalse(report["summary"]["realActionNetworkAllowed"])

    def test_state8004_role_resource_evidence_can_satisfy_role_resource_contract(self):
        data = self.complete_extra()
        for key in ("roleName", "level", "copper", "food"):
            data.pop(key, None)
        data["state8004TailUtf8Preview"] = (
            "君主名=证据君主|君主等级=47|铜钱=321000|粮食=654000|"
            "JiangLing{id=0000000000000007,name=赵云,status=0,tili=49}"
        )

        report = mod.verify(data)

        self.assertTrue(report["summary"]["shuaHuangOfflineReplayReady"])
        self.assertEqual("state8004TailUtf8Preview", report["evidence"]["roleResourceEvidence"]["roleResourceEvidenceSource"])
        self.assertTrue(report["evidence"]["roleResourceParse"]["recoveredRoleResourceReady"])
        self.assertEqual("证据君主", report["evidence"]["roleResourceEvidence"]["roleName"])

    def test_dispatch_alias_fields_satisfy_shuahuang_contract(self):
        data = self.complete_extra()
        data["dispatchResultsJson"] = json.dumps([{
            "bianduihao": "0000000000000003",
            "targetIdHex": "0000000000000065",
            "status": "成功",
            "responseBody": "刷黄出征成功！继续搜索... usedCount=2",
        }], ensure_ascii=False)

        report = mod.verify(data)

        self.assertTrue(report["summary"]["shuaHuangOfflineReplayReady"])
        self.assertTrue(report["evidence"]["dispatchResultsUsable"])

    def test_missing_fields_and_unsafe_flag_block_readiness(self):
        report = mod.verify({"mapTargetsHex": "aa", "networkSendAllowed": "true"})
        self.assertFalse(report["summary"]["shuaHuangOfflineReplayReady"])
        self.assertIn("identity:userId/serverUrl", report["missing"]["shuaHuang"])
        self.assertIn("unsafe network flag must be false", report["missing"]["shuaHuang"])

    def test_present_but_unparseable_fields_do_not_satisfy_replay_contract(self):
        data = self.complete_extra()
        data.update({
            "state8004TailUtf8Preview": "not a general record",
            "xiaohuangPrefsJson": "{\"uiOnly\":true}",
            "mapTargetsHex": "zz",
            "dispatchResultsJson": "[{\"success\":true}]",
            "mineTargetsHex": "not-hex",
            "dailyStepResultsJson": "[{\"success\":true}]",
        })
        report = mod.verify(data)
        self.assertFalse(report["summary"]["shuaHuangOfflineReplayReady"])
        self.assertFalse(report["summary"]["dailyOfflineReplayReady"])
        self.assertFalse(report["summary"]["mineOfflineReplayReady"])
        self.assertIn("generals:parseable", report["missing"]["shuaHuang"])
        self.assertIn("formations:parseable", report["missing"]["shuaHuang"])
        self.assertIn("mapTargets/041540:parseable", report["missing"]["shuaHuang"])
        self.assertIn("dispatchResultsJson:usable", report["missing"]["shuaHuang"])
        self.assertIn("dailyStepResultsJson:usable", report["missing"]["daily"])
        self.assertIn("mineTargets/041542:parseable", report["missing"]["mine"])

    def test_cli_merges_base_and_writes_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "base.json"
            merged = Path(td) / "merged.json"
            out = Path(td) / "report.json"
            md = Path(td) / "report.md"
            data = self.complete_extra()
            base.write_text(json.dumps({k: data[k] for k in ["userId", "serverUrl", "roleName", "level", "copper", "food"]}, ensure_ascii=False), encoding="utf-8")
            merged.write_text(json.dumps({k: v for k, v in data.items() if k not in {"userId", "serverUrl", "roleName", "level", "copper", "food"}}, ensure_ascii=False), encoding="utf-8")
            subprocess.check_call([sys.executable, str(SCRIPT), str(merged), "--base", str(base), "--out", str(out), "--markdown-out", str(md)])
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(report["summary"]["shuaHuangOfflineReplayReady"])
            self.assertIn("ChannelExtra 离线回放契约校验", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
