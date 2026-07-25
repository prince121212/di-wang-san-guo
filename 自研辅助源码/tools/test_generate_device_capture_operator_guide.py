#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("generate_device_capture_operator_guide.py")
spec = importlib.util.spec_from_file_location("generate_device_capture_operator_guide", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["generate_device_capture_operator_guide"] = mod
sys.path.insert(0, str(SCRIPT.parent))
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class GenerateDeviceCaptureOperatorGuideTest(unittest.TestCase):
    def test_render_guide_contains_all_required_scenarios_and_safety_gate(self):
        text = mod.render_guide("com.ifengwoo.dwpm", "spawn", "120")
        for name in [
            "loginState8004",
            "nativeWrapper",
            "generalFormationBaseline",
            "brushYellowSearch041540",
            "brushYellowNativeWrapper1520",
            "brushYellowDispatch1522030",
            "selfStopLogout",
            "daily",
            "mineSearch041542",
        ]:
            self.assertIn(name, text)
        self.assertIn("1520030", text)
        self.assertIn("1522030", text)
        self.assertIn("041540", text)
        self.assertIn("041542", text)
        self.assertIn("将领/编队基线", text)
        self.assertIn("formationsJson", text)
        self.assertIn("停止任务", text)
        self.assertIn("退出登录", text)
        self.assertIn("preflightReady=true", text)
        self.assertIn("prepare_base_channel_extra.py", text)
        self.assertIn("generate_shuahuang_channel_extra_sample.py --profile full", text)
        self.assertIn("wait_for_device_and_run_pipeline.sh", text)
        self.assertIn("--run-self-smoke-first", text)
        self.assertIn("--promote-canonical", text)
        self.assertIn("端到端验收链路映射", text)
        self.assertIn("采集泳道顺序", text)
        self.assertIn("登录 | loginState8004", text)
        self.assertIn("出征刷黄 | brushYellowNativeWrapper1520", text)
        self.assertIn("停止任务 | selfStopLogout", text)
        self.assertIn("退出登录 | selfStopLogout", text)
        self.assertIn("self_lifecycle_logcat_check.md", text)
        self.assertIn("selfLifecycleLogcatReady=true", text)
        self.assertIn("fullOfflineReplayReady=true", text)
        self.assertIn("regression/full_offline_replay.md", text)
        self.assertIn("shuahuang_minimum_goal_check.md", text)
        self.assertIn("shuaHuangMinimumLiveEvidenceReady=true", text)
        self.assertIn("shuaHuangMinimumFinalReady=false", text)
        self.assertIn("不要把样本当作真实完成证据", text)
        self.assertIn("realActionNetworkAllowed=false", text)
        self.assertIn("自研辅助真实动作发送仍必须保持关闭", text)

    def test_cli_writes_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "capture_operator_guide.md"
            subprocess.check_call([
                sys.executable,
                str(SCRIPT),
                "--package",
                "com.ifengwoo.dwpm",
                "--mode",
                "spawn",
                "--duration",
                "120",
                "--out",
                str(out),
            ])
            text = out.read_text(encoding="utf-8")
            self.assertIn("设备协议采集操作指南", text)
            self.assertIn("com.ifengwoo.dwpm", text)
            self.assertIn("必需场景顺序", text)


if __name__ == "__main__":
    unittest.main()
