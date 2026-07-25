#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("capture_device_protocol_regression.sh")


class CaptureDeviceProtocolRegressionScriptTest(unittest.TestCase):
    def test_script_contains_safe_defaults_and_regression_call(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("--package <android.package>", text)
        self.assertIn("frida_native_session_trace_v2.js", text)
        self.assertIn("check_device_regression_preflight.py", text)
        self.assertIn("--frida-ps-bin", text)
        self.assertIn("FRIDA_PS_BIN", text)
        self.assertIn("preflight.json", text)
        self.assertIn("preflight.md", text)
        self.assertIn("generate_device_capture_operator_guide.py", text)
        self.assertIn("capture_operator_guide.md", text)
        self.assertIn("PREFLIGHT_READY", text)
        self.assertIn("--skip-preflight", text)
        self.assertIn("--self-apk", text)
        self.assertIn("--xiaohuang-apk", text)
        self.assertIn("--game-apk", text)
        self.assertIn("device_regression_from_logs.py", text)
        self.assertIn("verify_device_capture_scenarios.py", text)
        self.assertIn("verify_device_regression_artifacts.py", text)
        self.assertIn("verify_shuahuang_minimum_goal.py", text)
        self.assertIn("verify_self_lifecycle_logcat.py", text)
        self.assertIn("networkSendAllowed: false", text)
        self.assertIn("real action gate remains disabled", text)
        self.assertIn("--include-values", text)
        self.assertIn("--base-channel-extra", text)
        self.assertIn("replay_contract.md", text)
        self.assertIn("shuahuang_offline_replay.md", text)
        self.assertIn("daily_offline_replay.md", text)
        self.assertIn("mine_offline_replay.md", text)
        self.assertIn("action_gate_readiness.md", text)
        self.assertIn("capture_scenario_check.md", text)
        self.assertIn("capture_scenario_coverage.md", text)
        self.assertIn("regression_artifact_check.md", text)
        self.assertIn("shuahuang_minimum_goal_check.md", text)
        self.assertIn("self_lifecycle_logcat_check.md", text)
        self.assertIn("shuaHuangMinimumLiveEvidenceReady=true", text)
        self.assertIn("selfLifecycleLogcatReady=true", text)
        self.assertIn("login/0x8004 role-resource evidence", text)
        self.assertIn("generals/formations baseline evidence", text)
        self.assertIn("self-app stop/logout lifecycle evidence", text)
        self.assertIn("1520030 and 1522030", text)

    def test_shell_syntax_is_valid(self) -> None:
        subprocess.check_call(["bash", "-n", str(SCRIPT)])

    def test_help_works_without_device(self) -> None:
        out = subprocess.check_output(["bash", str(SCRIPT), "--help"], text=True)
        self.assertIn("Usage:", out)
        self.assertIn("--package", out)
        self.assertIn("spawn|attach", out)
        self.assertIn("--base-channel-extra", out)
        self.assertIn("--skip-preflight", out)
        self.assertIn("--frida-script", out)
        self.assertIn("--self-apk", out)

    def test_failed_preflight_writes_reports_before_capture(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            adb = root / "adb"
            adb.write_text("#!/usr/bin/env bash\nif [[ $1 == devices ]]; then echo 'List of devices attached'; echo; else exit 1; fi\n", encoding="utf-8")
            adb.chmod(0o755)
            frida = root / "frida"
            frida.write_text("#!/usr/bin/env bash\necho frida\n", encoding="utf-8")
            frida.chmod(0o755)
            frida_ps = root / "frida-ps"
            frida_ps.write_text("#!/usr/bin/env bash\necho should-not-run\n", encoding="utf-8")
            frida_ps.chmod(0o755)
            files = []
            for name in ["self.apk", "xh.apk", "game.apk", "trace.js"]:
                path = root / name
                path.write_text("x", encoding="utf-8")
                files.append(path)
            out_dir = root / "out"
            env = dict(os.environ)
            env.update({"ADB_BIN": str(adb), "FRIDA_BIN": str(frida), "FRIDA_PS_BIN": str(frida_ps)})
            proc = subprocess.run([
                "bash", str(SCRIPT),
                "--package", "com.ifengwoo.dwpm",
                "--duration", "5",
                "--out-dir", str(out_dir),
                "--frida-script", str(files[3]),
                "--self-apk", str(files[0]),
                "--xiaohuang-apk", str(files[1]),
                "--game-apk", str(files[2]),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            self.assertEqual(69, proc.returncode)
            self.assertTrue((out_dir / "preflight.json").exists())
            self.assertTrue((out_dir / "preflight.md").exists())
            self.assertIn("device regression preflight failed", proc.stderr)
            self.assertIn("authorized adb device", (out_dir / "preflight.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
