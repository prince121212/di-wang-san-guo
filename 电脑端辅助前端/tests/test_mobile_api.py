from __future__ import annotations

import importlib.util
import json
import re
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_mobile_api_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class MobileApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_token = SERVER.MOBILE_API_TOKEN
        self.old_secret = SERVER.MOBILE_API_SECRET
        SERVER.MOBILE_API_TOKEN = "test-mobile-token"
        SERVER.MOBILE_API_SECRET = "stable-test-secret"
        SERVER.MOBILE_API_IDEMPOTENCY_RESULTS.clear()

    def tearDown(self) -> None:
        SERVER.MOBILE_API_TOKEN = self.old_token
        SERVER.MOBILE_API_SECRET = self.old_secret
        SERVER.MOBILE_API_IDEMPOTENCY_RESULTS.clear()

    def test_account_reference_is_stable_and_does_not_expose_session_id(self) -> None:
        first = SERVER.mobile_account_ref("raw-session-id")
        second = SERVER.mobile_account_ref("raw-session-id")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 32)
        self.assertNotIn("raw-session-id", first)

    def test_mobile_json_redacts_game_credentials_and_rewrites_session_ids(self) -> None:
        safe = SERVER.mobile_safe_json({
            "sessionId": "raw-session-id",
            "password": "secret",
            "tokenCiphertext": "game-token",
            "gameHttp": "http://game",
            "serverUrl": "http://game-server",
            "configDir": "/Users/alice/private",
            "nested": {"session_id": "raw-session-id", "value": 7},
        })

        self.assertNotIn("password", safe)
        self.assertNotIn("tokenCiphertext", safe)
        self.assertNotIn("gameHttp", safe)
        self.assertNotIn("serverUrl", safe)
        self.assertEqual(safe["configDir"], "电脑端统一核心存储")
        self.assertEqual(safe["sessionId"], SERVER.mobile_account_ref("raw-session-id"))
        self.assertEqual(safe["nested"]["session_id"], SERVER.mobile_account_ref("raw-session-id"))

    def test_mobile_json_sanitizes_embedded_settings_json(self) -> None:
        raw = json.dumps({
            "sessionId": "raw-session-id",
            "gameHttp": "http://secret",
            "configDir": "/Users/alice/private",
            "dailyTasks": {"salary": True},
        }, ensure_ascii=False)
        safe = SERVER.mobile_safe_json({"content": raw})
        parsed = json.loads(safe["content"])

        self.assertEqual(parsed["sessionId"], SERVER.mobile_account_ref("raw-session-id"))
        self.assertNotIn("gameHttp", parsed)
        self.assertEqual(parsed["configDir"], "电脑端统一核心存储")
        self.assertTrue(parsed["dailyTasks"]["salary"])

    def test_capabilities_cover_independent_daily_features_and_legacy_bridge(self) -> None:
        payload = SERVER.mobile_capabilities_payload()
        daily = next(item for item in payload["features"] if item["key"] == "daily")

        self.assertTrue(daily["independent"])
        self.assertEqual(
            daily["actions"],
            ["signIn", "arenaCoins", "donate", "salary", "nationalCollect", "cityLordCollect", "generalVisit"],
        )
        self.assertIn("/api/daily/general-visit/claim", payload["legacyBridge"]["postRoutes"])
        self.assertNotIn("/api/server/shutdown", payload["legacyBridge"]["postRoutes"])

    def test_shared_web_console_api_paths_are_all_in_mobile_bridge(self) -> None:
        app_text = (ROOT / "电脑端辅助前端" / "app.js").read_text(encoding="utf-8")
        referenced = {
            match.split("?")[0]
            for match in re.findall(r"/api/[A-Za-z0-9_./-]+", app_text)
        }
        allowed = set(SERVER.MOBILE_LEGACY_GET_PATHS) | set(SERVER.MOBILE_LEGACY_POST_PATHS)
        self.assertTrue(referenced - allowed <= {"/api/health"})

    def test_settings_revision_conflict_returns_current_snapshot_without_writing(self) -> None:
        account = {"sessionId": "sid", "username": "1608600", "area": {"areaName": "352区"}}
        with SERVER.ACCOUNT_LOCK:
            old_accounts = dict(SERVER.ACCOUNTS)
            SERVER.ACCOUNTS.clear()
            SERVER.ACCOUNTS["sid"] = account
        try:
            with patch.object(SERVER, "mobile_settings_revision", return_value="new-revision"), \
                 patch.object(SERVER, "mobile_settings_payload", return_value={"revision": "new-revision"}), \
                 patch.object(SERVER, "save_account_habits") as save:
                with self.assertRaises(SERVER.MobileApiConflict) as raised:
                    SERVER.mobile_patch_settings(
                        "sid",
                        scope="common.daily",
                        patch={"dailyTasks": {"salary": True}},
                        expected_revision="old-revision",
                    )

            self.assertEqual(raised.exception.current["revision"], "new-revision")
            save.assert_not_called()
        finally:
            with SERVER.ACCOUNT_LOCK:
                SERVER.ACCOUNTS.clear()
                SERVER.ACCOUNTS.update(old_accounts)

    def test_authenticated_health_and_idempotent_legacy_replay(self) -> None:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), SERVER.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            with self.assertRaises(urllib.error.HTTPError) as unauthorized:
                urllib.request.urlopen(base + "/api/v1/mobile/health", timeout=5)
            self.assertEqual(unauthorized.exception.code, 401)

            health_request = urllib.request.Request(
                base + "/api/v1/mobile/health",
                headers={"Authorization": "Bearer test-mobile-token", "X-Device-Id": "test-device"},
            )
            with urllib.request.urlopen(health_request, timeout=5) as response:
                health = json.loads(response.read())
            self.assertTrue(health["ok"])
            self.assertEqual(health["apiVersion"], "v1")

            body = json.dumps({
                "method": "GET",
                "path": "/api/health",
                "idempotencyKey": "health-once",
            }).encode()
            headers = {
                "Authorization": "Bearer test-mobile-token",
                "X-Device-Id": "test-device",
                "Content-Type": "application/json",
            }
            first_request = urllib.request.Request(
                base + "/api/v1/mobile/legacy", data=body, headers=headers, method="POST",
            )
            with urllib.request.urlopen(first_request, timeout=10) as response:
                first = json.loads(response.read())
            second_request = urllib.request.Request(
                base + "/api/v1/mobile/legacy", data=body, headers=headers, method="POST",
            )
            with urllib.request.urlopen(second_request, timeout=10) as response:
                second = json.loads(response.read())

            self.assertTrue(first["ok"])
            self.assertNotIn("idempotentReplay", first)
            self.assertTrue(second["idempotentReplay"])
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

    def test_paired_webview_legacy_surface_uses_opaque_refs_both_ways(self) -> None:
        sid = "raw-webview-session"
        account = {
            "sessionId": sid,
            "username": "1608600",
            "area": {"areaName": "352区"},
            "status": "stopped",
            "started": False,
            "createdAt": 1,
        }
        session = {
            "sessionId": sid,
            "username": "1608600",
            "role": {"roleName": "测试君主", "level": 38},
            "roleState": {"copper": 123, "food": 456},
            "area": {"areaName": "352区"},
            "createdAt": 1,
            "gameHttp": "http://secret-game-endpoint",
            "dm": 987,
            "channelExtra": {"gameHttp": "http://secret-game-endpoint", "dm": "987"},
        }
        with SERVER.ACCOUNT_LOCK:
            old_accounts = dict(SERVER.ACCOUNTS)
            old_sessions = dict(SERVER.SESSIONS)
            SERVER.ACCOUNTS.clear()
            SERVER.SESSIONS.clear()
            SERVER.ACCOUNTS[sid] = account
            SERVER.SESSIONS[sid] = session
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), SERVER.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            cookie = f"{SERVER.MOBILE_API_COOKIE}=test-mobile-token"
            try:
                request = urllib.request.Request(
                    base + "/api/accounts",
                    headers={"Cookie": cookie},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read())
                public = payload["accounts"][0]
                opaque = SERVER.mobile_account_ref(sid)
                self.assertEqual(opaque, public["session"]["sessionId"])
                self.assertNotIn(sid, json.dumps(payload, ensure_ascii=False))
                self.assertNotIn("gameHttp", json.dumps(payload, ensure_ascii=False))

                seen: list[str] = []
                with patch.object(SERVER, "account_log", side_effect=lambda actual, *args, **kwargs: seen.append(actual)):
                    body = json.dumps({
                        "sessionId": opaque,
                        "message": "来自配对 WebView",
                    }).encode()
                    log_request = urllib.request.Request(
                        base + "/api/logs/account",
                        data=body,
                        headers={
                            "Cookie": cookie,
                            "Content-Type": "application/json",
                        },
                        method="POST",
                    )
                    with urllib.request.urlopen(log_request, timeout=5) as response:
                        self.assertTrue(json.loads(response.read())["ok"])
                self.assertEqual([sid], seen)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)
        finally:
            with SERVER.ACCOUNT_LOCK:
                SERVER.ACCOUNTS.clear()
                SERVER.ACCOUNTS.update(old_accounts)
                SERVER.SESSIONS.clear()
                SERVER.SESSIONS.update(old_sessions)

    def test_remote_paired_webview_can_only_read_console_static_assets(self) -> None:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), SERVER.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        cookie = f"{SERVER.MOBILE_API_COOKIE}=test-mobile-token"
        try:
            # The test server is necessarily reached through loopback.  Patch
            # only the handler's network classification so this exercises the
            # exact LAN-phone branch without opening another interface.
            with patch.object(SERVER.Handler, "_client_is_loopback", return_value=False):
                for path in ("/index.html?mobile=1", "/app.js", "/styles.css"):
                    request = urllib.request.Request(base + path, headers={"Cookie": cookie})
                    with urllib.request.urlopen(request, timeout=5) as response:
                        self.assertEqual(200, response.status)
                        self.assertTrue(response.read())

                for path in ("/server.py", "/reports/assistant_state.sqlite3"):
                    request = urllib.request.Request(base + path, headers={"Cookie": cookie})
                    with self.assertRaises(urllib.error.HTTPError) as blocked:
                        urllib.request.urlopen(request, timeout=5)
                    self.assertEqual(404, blocked.exception.code)
                    payload = json.loads(blocked.exception.read())
                    self.assertEqual("MOBILE_STATIC_NOT_ALLOWED", payload["code"])

                    head = urllib.request.Request(
                        base + path,
                        headers={"Cookie": cookie},
                        method="HEAD",
                    )
                    with self.assertRaises(urllib.error.HTTPError) as blocked_head:
                        urllib.request.urlopen(head, timeout=5)
                    self.assertEqual(404, blocked_head.exception.code)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
