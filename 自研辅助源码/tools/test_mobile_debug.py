#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("mobile_debug.py")
SPEC = importlib.util.spec_from_file_location("mobile_debug", SCRIPT)
mobile_debug = importlib.util.module_from_spec(SPEC)
sys.modules["mobile_debug"] = mobile_debug
assert SPEC.loader is not None
SPEC.loader.exec_module(mobile_debug)


def provider_output(value: dict) -> str:
    encoded = mobile_debug.encode_base64url(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    )
    return (
        "Result: Bundle[{debug_protocol=1, debug_encoding=base64url, "
        f"debug_result={encoded}}}]\n"
    )


class MobileDebugTest(unittest.TestCase):
    def test_encodes_the_same_versioned_generic_api_message_as_the_webview(self):
        request = mobile_debug.make_api_request(
            "get",
            "/api/health",
            {"label": "手机调试"},
            request_id="debug-test-1",
        )

        decoded = json.loads(
            mobile_debug.decode_base64url(mobile_debug.encode_api_request(request))
        )

        self.assertEqual("v1", decoded["apiVersion"])
        self.assertEqual("debug-test-1", decoded["id"])
        self.assertEqual("GET", decoded["method"])
        self.assertEqual("/api/health", decoded["path"])
        self.assertEqual("手机调试", decoded["body"]["label"])

    def test_content_call_uses_provider_uri_and_android_extra_bindings(self):
        response = {"apiVersion": "v1", "id": "x", "status": 200, "body": {"ok": True}}
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=provider_output(response), stderr=""
        )
        with mock.patch.object(subprocess, "run", return_value=completed) as run:
            client = mobile_debug.AdbClient("fake-adb", "device-1", 5)
            actual = client.content_call(
                "com.example.dwpmclone.debug",
                "api",
                "encoded-request",
                ["allow_post:b:true", "post_confirmation:s:ALLOW_REAL_POST"],
            )

        self.assertEqual(response, actual)
        command = run.call_args.args[0]
        self.assertEqual(["fake-adb", "-s", "device-1"], command[:3])
        self.assertIn("content://com.example.dwpmclone.debug", command)
        self.assertIn("encoded-request", command)
        self.assertIn("allow_post:b:true", command)
        self.assertIn("post_confirmation:s:ALLOW_REAL_POST", command)

    def test_unconfirmed_post_is_rejected_before_adb_is_started(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = mobile_debug.main(
                [
                    "--adb-bin",
                    "/definitely/not/an/adb",
                    "call",
                    "POST",
                    "/api/automation/stop",
                    "--body",
                    '{"sessionId":"1608600"}',
                ]
            )

        self.assertEqual(2, code)
        self.assertIn("--allow-post", stderr.getvalue())
        self.assertNotIn("找不到 adb", stderr.getvalue())

    def test_confirmed_post_still_sends_both_provider_guards(self):
        response = {"apiVersion": "v1", "id": "x", "status": 200, "body": {"ok": True}}
        adb = mock.Mock()
        adb.content_call.return_value = response
        connection = mobile_debug.DebugConnection(
            adb=adb,
            package="com.example.dwpmclone",
            authority="com.example.dwpmclone.debug",
            apk=Path("missing.apk"),
        )

        actual = connection.call_api(
            "POST",
            "/api/automation/stop",
            {"sessionId": "1608600"},
            allow_post=True,
            request_id="post-1",
        )

        self.assertEqual(response, actual)
        call = adb.content_call.call_args.args
        self.assertEqual("api", call[1])
        decoded = json.loads(mobile_debug.decode_base64url(call[2]))
        self.assertEqual("POST", decoded["method"])
        self.assertEqual(
            ["allow_post:b:true", "post_confirmation:s:ALLOW_REAL_POST"],
            call[3],
        )

    def test_fake_adb_identity_and_api_response_are_verified_end_to_end(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            apk = root / "app-debug.apk"
            apk.write_bytes(b"debug-apk-for-test")
            apk_sha = hashlib.sha256(apk.read_bytes()).hexdigest()
            version_name, version_code = mobile_debug.expected_source_version()
            identity = {
                "ok": True,
                "debugProtocol": 1,
                "packageName": "com.example.dwpmclone",
                "versionName": version_name,
                "versionCode": version_code,
                "debuggable": True,
                "pid": 12345,
                "uid": 10123,
                "callingUid": 2000,
                "apkSha256": apk_sha,
                "sourceDir": "/data/app/base.apk",
                "sourceDirLastModified": 1,
                "packageLastUpdateTime": 2,
            }
            response = {
                "apiVersion": "v1",
                "id": "fake-api",
                "status": 200,
                "body": {"core": "android-local"},
            }
            log = root / "argv.jsonl"
            adb = root / "adb"
            adb.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                f"log = {str(log)!r}\n"
                "with open(log, 'a', encoding='utf-8') as stream:\n"
                "    stream.write(json.dumps(sys.argv[1:], ensure_ascii=False) + '\\n')\n"
                f"identity = {provider_output(identity)!r}\n"
                f"response = {provider_output(response)!r}\n"
                "print(identity if 'identity' in sys.argv else response, end='')\n",
                encoding="utf-8",
            )
            adb.chmod(0o755)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = mobile_debug.main(
                    [
                        "--adb-bin",
                        str(adb),
                        "--apk",
                        str(apk),
                        "call",
                        "GET",
                        "/api/health",
                        "--request-id",
                        "fake-api",
                    ]
                )

            self.assertEqual(0, code)
            self.assertEqual("android-local", json.loads(stdout.getvalue())["body"]["core"])
            calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(2, len(calls))
            self.assertIn("identity", calls[0])
            self.assertIn("api", calls[1])
            encoded_request = calls[1][calls[1].index("--arg") + 1]
            request = json.loads(mobile_debug.decode_base64url(encoded_request))
            self.assertEqual("/api/health", request["path"])

    def test_identity_rejects_a_stale_installed_apk_sha(self):
        with tempfile.TemporaryDirectory() as temporary:
            apk = Path(temporary) / "app-debug.apk"
            apk.write_bytes(b"local")
            version_name, version_code = mobile_debug.expected_source_version()
            identity = {
                "debugProtocol": 1,
                "packageName": "com.example.dwpmclone",
                "versionName": version_name,
                "versionCode": version_code,
                "debuggable": True,
                "pid": 1,
                "uid": 10001,
                "apkSha256": "0" * 64,
            }

            _, hard_errors, installed_errors = mobile_debug.verify_identity(
                identity,
                expected_package="com.example.dwpmclone",
                apk=apk,
            )

        self.assertEqual([], hard_errors)
        self.assertTrue(any("SHA-256" in item for item in installed_errors))

    def test_snapshot_diff_is_generic_and_can_ignore_volatile_keys(self):
        before = {"capturedAt": 1, "responses": {"/api/x": {"status": 200, "body": {"state": "queued"}}}}
        after = {"capturedAt": 2, "responses": {"/api/x": {"status": 200, "body": {"state": "running"}}}}

        changes = mobile_debug.recursive_diff(
            before,
            after,
            ignored_keys={"capturedAt"},
        )

        self.assertEqual(1, len(changes))
        self.assertEqual("$.responses./api/x.body.state", changes[0]["path"])
        self.assertEqual("queued", changes[0]["before"])
        self.assertEqual("running", changes[0]["after"])

    def test_default_snapshot_uses_read_only_local_diagnostics(self):
        paths = mobile_debug.default_snapshot_paths("1608600")

        self.assertTrue(all(path.startswith("/api/") for path in paths))
        self.assertTrue(any(path.startswith("/api/automation/status?") for path in paths))
        self.assertTrue(any(path.startswith("/api/logs/account?") for path in paths))
        self.assertFalse(any(path.startswith("/api/state/refresh?") for path in paths))

    def test_fast_installs_and_verifies_without_opening_the_activity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            apk = root / "app-debug.apk"
            apk.write_bytes(b"fast-debug-apk")
            apk_sha = hashlib.sha256(apk.read_bytes()).hexdigest()
            version_name, version_code = mobile_debug.expected_source_version()
            identity = {
                "ok": True,
                "debugProtocol": 1,
                "packageName": "com.example.dwpmclone",
                "versionName": version_name,
                "versionCode": version_code,
                "debuggable": True,
                "pid": 24680,
                "uid": 10123,
                "callingUid": 2000,
                "apkSha256": apk_sha,
                "sourceDir": "/data/app/base.apk",
                "sourceDirLastModified": 1,
                "packageLastUpdateTime": 2,
            }
            gradlew = root / "gradlew"
            gradlew.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
            gradlew.chmod(0o755)
            log = root / "adb-argv.jsonl"
            adb = root / "adb"
            adb.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                f"log = {str(log)!r}\n"
                "with open(log, 'a', encoding='utf-8') as stream:\n"
                "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                f"identity = {provider_output(identity)!r}\n"
                "print(identity if 'identity' in sys.argv else 'Success')\n",
                encoding="utf-8",
            )
            adb.chmod(0o755)

            with contextlib.redirect_stdout(io.StringIO()):
                code = mobile_debug.main(
                    [
                        "--adb-bin",
                        str(adb),
                        "--apk",
                        str(apk),
                        "--gradlew",
                        str(gradlew),
                        "fast",
                    ]
                )

            calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            flattened = [item for call in calls for item in call]
            self.assertEqual(0, code)
            self.assertIn("install", flattened)
            self.assertIn("-r", flattened)
            self.assertIn("identity", flattened)
            self.assertNotIn("am", flattened)
            self.assertNotIn("start", flattened)

    def test_help_lists_only_generic_debugging_capabilities(self):
        help_text = mobile_debug.build_parser().format_help()

        for command in ["call", "status", "logs", "snapshot", "diff", "watch", "fast", "open-ui"]:
            self.assertIn(command, help_text)
        self.assertNotIn("副本修复", help_text)
        self.assertNotIn("军情修复", help_text)


if __name__ == "__main__":
    unittest.main()
