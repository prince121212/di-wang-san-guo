#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("check_device_regression_preflight.py")
spec = importlib.util.spec_from_file_location("check_device_regression_preflight", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["check_device_regression_preflight"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class CheckDeviceRegressionPreflightTest(unittest.TestCase):
    def make_bin(self, td: Path, name: str, content: str) -> Path:
        path = td / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)
        return path

    def make_fake_self_apk(self, path: Path, marker: bool = True) -> Path:
        with zipfile.ZipFile(path, "w") as zf:
            payload = b"classes" + (b" self-lifecycle-json " if marker else b"")
            zf.writestr("classes.dex", payload)
        return path

    def test_ready_with_fake_tools_device_and_files(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            adb = self.make_bin(td, "adb", "#!/usr/bin/env bash\nif [[ $1 == devices ]]; then echo 'List of devices attached'; echo 'emu device product:x'; elif [[ $1 == shell ]]; then echo 'package:/data/app/pkg/base.apk'; else echo ok; fi\n")
            frida = self.make_bin(td, "frida", "#!/usr/bin/env bash\necho frida\n")
            frida_ps = self.make_bin(td, "frida-ps", "#!/usr/bin/env bash\necho 'PID  Name'; echo '---- ----'; echo '123  com.ifengwoo.dwpm'; echo '456  system_server'\n")
            files = []
            for name in ["self.apk", "x.apk", "game.apk", "f.js", "base.json"]:
                p = td / name
                if name == "self.apk":
                    self.make_fake_self_apk(p)
                else:
                    p.write_text("x", encoding="utf-8")
                files.append(p)
            files[4].write_text("{}", encoding="utf-8")
            report = mod.preflight(str(adb), str(frida), str(frida_ps), package="pkg", base_channel_extra=str(files[4]), self_apk=files[0], xiaohuang_apk=files[1], game_apk=files[2], frida_script=files[3])
            self.assertTrue(report["summary"]["preflightReady"])
            self.assertEqual([], report["missing"])
            self.assertTrue(report["summary"]["packageInstalled"])
            self.assertTrue(report["summary"]["baseChannelExtraChecked"])
            self.assertTrue(report["summary"]["baseChannelExtraValid"])
            self.assertFalse(report["summary"]["baseChannelExtraBaselineReady"])
            self.assertIn("identity:userId/serverUrl", report["baseChannelExtraAudit"]["missingBaseline"])
            self.assertTrue(report["summary"]["fridaUsbChecked"])
            self.assertTrue(report["summary"]["fridaUsbOk"])
            self.assertEqual(2, report["summary"]["fridaUsbProcessCount"])
            self.assertTrue(any("Preflight 已就绪" in item for item in report["nextActions"]))
            self.assertIn("adb install -r", "\n".join(report["installCommands"]))
            self.assertTrue(any("登录/同步角色状态" in item for item in report["runbook"]))

    def test_missing_device_blocks_preflight(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            adb = self.make_bin(td, "adb", "#!/usr/bin/env bash\necho 'List of devices attached'\n")
            frida = self.make_bin(td, "frida", "#!/usr/bin/env bash\necho frida\n")
            frida_ps = self.make_bin(td, "frida-ps", "#!/usr/bin/env bash\necho should-not-run\n")
            f = td / "file"
            f.write_text("x", encoding="utf-8")
            report = mod.preflight(str(adb), str(frida), str(frida_ps), self_apk=f, xiaohuang_apk=f, game_apk=f, frida_script=f)
            self.assertFalse(report["summary"]["preflightReady"])
            self.assertIn("authorized adb device", report["missing"])
            self.assertFalse(report["summary"]["fridaUsbChecked"])
            self.assertTrue(any("USB 调试" in item for item in report["nextActions"]))
            self.assertTrue(any("adb devices" in item for item in report["runbook"]))

    def test_frida_usb_failure_blocks_when_device_is_authorized(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            adb = self.make_bin(td, "adb", "#!/usr/bin/env bash\nif [[ $1 == devices ]]; then echo 'List of devices attached'; echo 'emu device product:x'; elif [[ $1 == shell ]]; then echo 'package:/data/app/pkg/base.apk'; fi\n")
            frida = self.make_bin(td, "frida", "#!/usr/bin/env bash\necho frida\n")
            frida_ps = self.make_bin(td, "frida-ps", "#!/usr/bin/env bash\necho 'Failed to enumerate processes: unable to connect to remote frida-server' >&2\nexit 1\n")
            f = td / "file"
            f.write_text("x", encoding="utf-8")
            report = mod.preflight(str(adb), str(frida), str(frida_ps), package="pkg", self_apk=f, xiaohuang_apk=f, game_apk=f, frida_script=f)
            self.assertFalse(report["summary"]["preflightReady"])
            self.assertTrue(report["summary"]["fridaUsbChecked"])
            self.assertFalse(report["summary"]["fridaUsbOk"])
            self.assertIn("frida usb device/server", report["missing"])
            self.assertTrue(any("启动与本机 frida-tools 版本匹配" in item for item in report["nextActions"]))
            self.assertTrue(any("frida-ps -U" in item for item in report["nextActions"]))




    def test_self_apk_without_lifecycle_marker_blocks_preflight(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            adb = self.make_bin(td, "adb", "#!/usr/bin/env bash\necho 'List of devices attached'\n")
            frida = self.make_bin(td, "frida", "#!/usr/bin/env bash\necho frida\n")
            frida_ps = self.make_bin(td, "frida-ps", "#!/usr/bin/env bash\necho should-not-run\n")
            self_apk = self.make_fake_self_apk(td / "self.apk", marker=False)
            xh = td / "xh.apk"
            game = td / "game.apk"
            trace = td / "trace.js"
            for path in [xh, game, trace]:
                path.write_text("x", encoding="utf-8")

            report = mod.preflight(str(adb), str(frida), str(frida_ps), self_apk=self_apk, xiaohuang_apk=xh, game_apk=game, frida_script=trace)

            self.assertFalse(report["summary"]["preflightReady"])
            self.assertFalse(report["summary"]["selfApkLifecycleMarkerReady"])
            self.assertIn("selfApk:self-lifecycle-json marker", report["missing"])
            self.assertTrue(any("SelfLifecycleLogFormatter" in item for item in report["nextActions"]))

    def test_stale_self_apk_blocks_preflight_even_without_device(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            adb = self.make_bin(td, "adb", "#!/usr/bin/env bash\necho 'List of devices attached'\n")
            frida = self.make_bin(td, "frida", "#!/usr/bin/env bash\necho frida\n")
            frida_ps = self.make_bin(td, "frida-ps", "#!/usr/bin/env bash\necho should-not-run\n")
            self_apk = td / "self.apk"
            xh = td / "xh.apk"
            game = td / "game.apk"
            trace = td / "trace.js"
            for path in [self_apk, xh, game, trace]:
                path.write_text("x", encoding="utf-8")
            os.utime(self_apk, (1, 1))

            report = mod.preflight(str(adb), str(frida), str(frida_ps), self_apk=self_apk, xiaohuang_apk=xh, game_apk=game, frida_script=trace)

            self.assertFalse(report["summary"]["preflightReady"])
            self.assertFalse(report["summary"]["selfApkBuildFresh"])
            self.assertIn("selfApk:fresh debug build", report["missing"])
            self.assertTrue(any("assembleDebug" in item for item in report["nextActions"]))

    def test_self_package_missing_blocks_preflight_when_self_apk_manifest_has_package(self):
        original_infer = mod.infer_apk_package
        try:
            with tempfile.TemporaryDirectory() as t:
                td = Path(t)
                adb = self.make_bin(
                    td,
                    "adb",
                    "#!/usr/bin/env bash\n"
                    "if [[ $1 == devices ]]; then echo 'List of devices attached'; echo 'emu device product:x'; "
                    "elif [[ $1 == shell && $2 == pm && $3 == path && $4 == pkg ]]; then echo 'package:/data/app/pkg/base.apk'; "
                    "elif [[ $1 == shell && $2 == pm && $3 == path && $4 == com.example.dwpmclone ]]; then exit 1; "
                    "else echo ok; fi\n",
                )
                frida = self.make_bin(td, "frida", "#!/usr/bin/env bash\necho frida\n")
                frida_ps = self.make_bin(td, "frida-ps", "#!/usr/bin/env bash\necho 'PID  Name'; echo '123  com.ifengwoo.dwpm'\n")
                self_apk = td / "self.apk"
                xh_apk = td / "xh.apk"
                game_apk = td / "game.apk"
                frida_script = td / "trace.js"
                self.make_fake_self_apk(self_apk)
                for path in [xh_apk, game_apk, frida_script]:
                    path.write_text("x", encoding="utf-8")

                def fake_infer(path):
                    name = Path(path).name
                    if name == "self.apk":
                        return {"attempted": True, "package": "com.example.dwpmclone", "launchActivity": "MainActivity", "versionName": "1", "error": ""}
                    if name == "xh.apk":
                        return {"attempted": True, "package": "pkg", "launchActivity": "XhActivity", "versionName": "1", "error": ""}
                    if name == "game.apk":
                        return {"attempted": True, "package": "com.gamebox.king", "launchActivity": "KingActivity", "versionName": "1", "error": ""}
                    return {"attempted": True, "package": "", "launchActivity": "", "versionName": "", "error": ""}

                mod.infer_apk_package = fake_infer
                report = mod.preflight(str(adb), str(frida), str(frida_ps), package="pkg", self_apk=self_apk, xiaohuang_apk=xh_apk, game_apk=game_apk, frida_script=frida_script)

                self.assertFalse(report["summary"]["preflightReady"])
                self.assertFalse(report["summary"]["selfPackageInstalled"])
                self.assertEqual("com.example.dwpmclone", report["summary"]["selfPackage"])
                self.assertIn("self package installed:com.example.dwpmclone", report["missing"])
                self.assertIn("game package installed:com.gamebox.king", report["missing"])
                self.assertTrue(any("self-lifecycle-json" in item for item in report["nextActions"]))
                self.assertTrue(any("游戏本体" in item for item in report["nextActions"]))
        finally:
            mod.infer_apk_package = original_infer

    def test_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            adb = self.make_bin(td, "adb", "#!/usr/bin/env bash\necho 'List of devices attached'\n")
            frida = self.make_bin(td, "frida", "#!/usr/bin/env bash\necho frida\n")
            frida_ps = self.make_bin(td, "frida-ps", "#!/usr/bin/env bash\necho should-not-run\n")
            f = td / "file"
            f.write_text("x", encoding="utf-8")
            out = td / "preflight.json"
            md = td / "preflight.md"
            subprocess.check_call([sys.executable, str(SCRIPT), "--adb-bin", str(adb), "--frida-bin", str(frida), "--frida-ps-bin", str(frida_ps), "--self-apk", str(f), "--xiaohuang-apk", str(f), "--game-apk", str(f), "--frida-script", str(f), "--out", str(out), "--markdown-out", str(md)])
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(data["summary"]["preflightReady"])
            self.assertIn("fridaUsb", data)
            self.assertIn("设备回归 Preflight 检查", md.read_text(encoding="utf-8"))
            self.assertIn("Next actions", md.read_text(encoding="utf-8"))
            self.assertIn("Frida USB", md.read_text(encoding="utf-8"))
            self.assertIn("Base channelExtra audit", md.read_text(encoding="utf-8"))
            self.assertIn("Capture runbook", md.read_text(encoding="utf-8"))

    def test_base_channel_extra_safety_flag_blocks_preflight(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            adb = self.make_bin(td, "adb", "#!/usr/bin/env bash\nif [[ $1 == devices ]]; then echo 'List of devices attached'; echo 'emu device product:x'; elif [[ $1 == shell ]]; then echo 'package:/data/app/pkg/base.apk'; fi\n")
            frida = self.make_bin(td, "frida", "#!/usr/bin/env bash\necho frida\n")
            frida_ps = self.make_bin(td, "frida-ps", "#!/usr/bin/env bash\necho 'PID  Name'; echo '123  com.ifengwoo.dwpm'\n")
            f = td / "file"
            f.write_text("x", encoding="utf-8")
            base = td / "base.json"
            base.write_text(json.dumps({
                "userId": "u1",
                "serverUrl": "http://game.example",
                "roleName": "君主",
                "level": "42",
                "copper": "1",
                "food": "2",
                "state8004TailUtf8Preview": "JiangLing{id=0000000000000007,name=赵云,status=0,tili=49}",
                "xiaohuangPrefsJson": "{\"shuahuangChuzhengBiandui0\":true,\"bianduihao0\":\"0000000000000003\",\"bianduiDejiangling0\":\"0000000000000007\"}",
                "networkSendAllowed": "true",
            }, ensure_ascii=False), encoding="utf-8")
            report = mod.preflight(str(adb), str(frida), str(frida_ps), package="pkg", base_channel_extra=str(base), self_apk=f, xiaohuang_apk=f, game_apk=f, frida_script=f)

            self.assertFalse(report["summary"]["preflightReady"])
            self.assertTrue(report["summary"]["baseChannelExtraValid"])
            self.assertFalse(report["summary"]["baseChannelExtraSafetyOk"])
            self.assertIn("baseChannelExtra unsafe network flag must be false", report["missing"])
            self.assertIn("networkSendAllowed", report["baseChannelExtraAudit"]["unsafeTrueFlags"])

    def test_base_channel_extra_good_baseline_is_advisory_ready(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            base = td / "base.json"
            base.write_text(json.dumps({
                "userId": "u1",
                "serverUrl": "http://game.example",
                "roleName": "君主",
                "level": "42",
                "copper": "1",
                "food": "2",
                "state8004TailUtf8Preview": "JiangLing{id=0000000000000007,name=赵云,status=0,tili=49}",
                "xiaohuangPrefsJson": "{\"shuahuangChuzhengBiandui0\":true,\"bianduihao0\":\"0000000000000003\",\"bianduiDejiangling0\":\"0000000000000007\"}",
                "networkSendAllowed": "false",
            }, ensure_ascii=False), encoding="utf-8")

            audit = mod.base_channel_extra_audit(str(base))

            self.assertTrue(audit["validJsonObject"])
            self.assertTrue(audit["safetyOk"])
            self.assertTrue(audit["baselineReadyForCapture"])
            self.assertFalse(audit["strictReplayReadyBeforeCapture"])
            self.assertEqual([], audit["missingBaseline"])
            self.assertIn("mapTargets/041540:parseable", audit["contractMissing"]["shuaHuang"])

    def test_base_channel_extra_invalid_json_blocks_preflight(self):
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            adb = self.make_bin(td, "adb", "#!/usr/bin/env bash\nif [[ $1 == devices ]]; then echo 'List of devices attached'; echo 'emu device product:x'; elif [[ $1 == shell ]]; then echo 'package:/data/app/pkg/base.apk'; fi\n")
            frida = self.make_bin(td, "frida", "#!/usr/bin/env bash\necho frida\n")
            frida_ps = self.make_bin(td, "frida-ps", "#!/usr/bin/env bash\necho 'PID  Name'; echo '123  com.ifengwoo.dwpm'\n")
            f = td / "file"
            f.write_text("x", encoding="utf-8")
            base = td / "bad.json"
            base.write_text("not json", encoding="utf-8")
            report = mod.preflight(str(adb), str(frida), str(frida_ps), package="pkg", base_channel_extra=str(base), self_apk=f, xiaohuang_apk=f, game_apk=f, frida_script=f)

            self.assertFalse(report["summary"]["preflightReady"])
            self.assertFalse(report["summary"]["baseChannelExtraValid"])
            self.assertIn("baseChannelExtra:valid json object", report["missing"])
            self.assertTrue(report["baseChannelExtraAudit"]["error"])


if __name__ == "__main__":
    unittest.main()
