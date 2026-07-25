#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("inspect_apk_manifest.py")
spec = importlib.util.spec_from_file_location("inspect_apk_manifest", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["inspect_apk_manifest"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]

SAMPLE = '''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.example.app" android:versionCode="7" android:versionName="1.2">
  <uses-sdk android:minSdkVersion="21" android:targetSdkVersion="33" />
  <uses-permission android:name="android.permission.INTERNET" />
  <application>
    <activity android:name=".MainActivity" android:exported="true">
      <intent-filter>
        <action android:name="android.intent.action.MAIN" />
        <category android:name="android.intent.category.LAUNCHER" />
      </intent-filter>
    </activity>
    <service android:name="SyncService" />
  </application>
</manifest>'''

class InspectApkManifestTest(unittest.TestCase):
    def test_parse_manifest_extracts_package_and_launcher(self):
        info = mod.parse_manifest(SAMPLE)
        self.assertEqual("com.example.app", info["package"])
        self.assertEqual("com.example.app.MainActivity", info["launchActivity"])
        self.assertEqual("1.2", info["versionName"])
        self.assertEqual(1, info["permissionCount"])
        self.assertEqual("com.example.app.SyncService", info["services"][0]["name"])

    def test_cli_with_fake_apkanalyzer(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "apkanalyzer"
            fake.write_text("#!/usr/bin/env bash\ncat <<'EOF'\n" + SAMPLE + "\nEOF\n", encoding="utf-8")
            fake.chmod(0o755)
            apk = root / "a.apk"
            apk.write_text("x", encoding="utf-8")
            out = root / "out.json"
            md = root / "out.md"
            subprocess.check_call([sys.executable, str(SCRIPT), str(apk), "--apkanalyzer", str(fake), "--out", str(out), "--markdown-out", str(md)])
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual("com.example.app", data["package"])
            self.assertIn("APK Manifest 检查", md.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
