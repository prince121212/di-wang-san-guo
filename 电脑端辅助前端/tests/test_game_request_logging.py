from __future__ import annotations

import importlib.util
import struct
import sys
import threading
import tempfile
import unittest
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"

SPEC = importlib.util.spec_from_file_location("dwpm_server_game_log_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class GameRequestLoggingTests(unittest.TestCase):
    def test_request_slots_on_same_route_are_serialized(self) -> None:
        original_interval = SERVER.GAME_REQUEST_MIN_INTERVAL_SEC
        SERVER.GAME_REQUEST_MIN_INTERVAL_SEC = 0.05
        SERVER.GAME_REQUEST_ROUTE_LOCKS.clear()
        SERVER.GAME_REQUEST_ROUTE_LAST_STARTED_AT.clear()
        started = []
        barrier = threading.Barrier(2)

        def take_slot() -> None:
            barrier.wait()
            SERVER.wait_for_game_request_slot("direct:test")
            started.append(time.monotonic())

        try:
            threads = [threading.Thread(target=take_slot) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        finally:
            SERVER.GAME_REQUEST_MIN_INTERVAL_SEC = original_interval
            SERVER.GAME_REQUEST_ROUTE_LOCKS.clear()
            SERVER.GAME_REQUEST_ROUTE_LAST_STARTED_AT.clear()
        self.assertGreaterEqual(abs(started[1] - started[0]), 0.045)

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        temp_root = Path(self.tempdir.name)
        self.originals = {
            "assigned_proxy_node": SERVER.assigned_proxy_node,
            "_post_game_direct": SERVER._post_game_direct,
            "_post_game_via_socks": SERVER._post_game_via_socks,
            "clash_proxy_groups": SERVER.clash_proxy_groups,
            "switch_clash_node": SERVER.switch_clash_node,
            "system_log": SERVER.system_log,
            "resolve_outbound_ip": SERVER.resolve_outbound_ip,
            "stop_account": SERVER.stop_account,
            "ACCOUNTS": SERVER.ACCOUNTS,
            "SESSIONS": SERVER.SESSIONS,
            "OUTBOUND_IP_CACHE": SERVER.OUTBOUND_IP_CACHE,
            "RECENT_GAME_REQUEST_RESULTS": SERVER.RECENT_GAME_REQUEST_RESULTS,
            "RUNTIME_STATE_FILE": SERVER.RUNTIME_STATE_FILE,
            "ACCOUNT_RECORDS_FILE": SERVER.ACCOUNT_RECORDS_FILE,
            "ACCOUNT_RECORD_BACKUP_DIR": SERVER.ACCOUNT_RECORD_BACKUP_DIR,
        }
        self.logs = []
        SERVER.ACCOUNTS = {}
        SERVER.SESSIONS = {}
        SERVER.OUTBOUND_IP_CACHE = {}
        SERVER.RECENT_GAME_REQUEST_RESULTS = {}
        SERVER.RUNTIME_STATE_FILE = temp_root / "runtime_state.json"
        SERVER.ACCOUNT_RECORDS_FILE = temp_root / "account_records.json"
        SERVER.ACCOUNT_RECORD_BACKUP_DIR = temp_root / "account_record_backups"
        SERVER.ACCOUNT_RECORD_BACKUP_DIR.mkdir()
        SERVER.resolve_outbound_ip = lambda _key, *, via_proxy: (
            "103.62.49.130" if via_proxy else "203.0.113.8"
        )
        SERVER.system_log = lambda message, **kwargs: self.logs.append({
            "message": message,
            **kwargs,
        })

    def tearDown(self) -> None:
        for name, value in self.originals.items():
            setattr(SERVER, name, value)
        self.tempdir.cleanup()

    @staticmethod
    def packet(opcode: int) -> dict:
        return {
            "opcode": opcode,
            "payload": b"\x00",
            "len": 1,
            "frag": 0,
        }

    def test_heartbeat_request_is_visible_but_marked_as_heartbeat(self) -> None:
        SERVER.assigned_proxy_node = lambda _account_id: ""
        SERVER._post_game_direct = lambda _url, _body: (
            200,
            b"\x01",
            [self.packet(0xA110)],
        )

        code, _data, _packets = SERVER.post_game(
            "http://game.example/game",
            [(0x3110, b"\x01\x00")],
            1,
            account_id=None,
        )

        self.assertEqual(code, 200)
        self.assertEqual(len(self.logs), 1)
        entry = self.logs[0]
        self.assertEqual(entry["source"], "game:heartbeat")
        self.assertIn("原服请求未知账号", entry["message"])
        self.assertIn("IP是：直连 203.0.113.8", entry["message"])
        self.assertIn("｜心跳｜", entry["message"])
        self.assertNotIn("0x3110", entry["message"])
        self.assertEqual(entry["detail"]["requestOpcodes"], ["0x3110"])
        self.assertEqual(entry["detail"]["responseOpcodes"], ["0xa110"])
        self.assertEqual(entry["detail"]["purpose"], "心跳")

    def test_recent_request_window_keeps_only_latest_thirty_results(self) -> None:
        for index in range(32):
            failed = index % 3 == 0
            SERVER.log_game_request_attempt(
                "http://game.example/game",
                [(0x1104, b"\x00")],
                10,
                "test-session",
                "direct",
                time.monotonic(),
                code=503 if failed else 200,
                data=b"" if failed else b"\x01",
                packets=[] if failed else [self.packet(0x8104)],
                outbound_ip="203.0.113.8",
            )

        history = SERVER.recent_game_requests("test-session")
        self.assertEqual(len(history), 30)
        # Requests 0 and 1 have rolled out; request 2 is now the oldest.
        self.assertEqual(history[0]["status"], "success")
        self.assertEqual(history[-1]["status"], "success")
        self.assertEqual(
            [item["status"] for item in history],
            ["failure" if index % 3 == 0 else "success" for index in range(2, 32)],
        )

    def test_public_account_is_gray_until_logged_in(self) -> None:
        account = {
            "sessionId": "gray-session",
            "username": "1001",
            "area": {"areaName": "351区"},
            "started": False,
            "status": "stopped",
        }
        SERVER.ACCOUNTS["gray-session"] = account
        SERVER.record_recent_game_request(
            "gray-session",
            success=False,
            purpose="旧失败请求",
        )
        self.assertEqual(SERVER.public_account(account)["recentGameRequests"], [])

        account["started"] = True
        account["status"] = "online"
        SERVER.SESSIONS["gray-session"] = {
            "sessionId": "gray-session",
            "username": "1001",
            "area": {"areaName": "351区"},
            "role": {},
            "createdAt": 1,
        }
        self.assertEqual(
            SERVER.public_account(account)["recentGameRequests"][0]["status"],
            "failure",
        )
        SERVER.clear_recent_game_requests("gray-session")
        self.assertEqual(SERVER.public_account(account)["recentGameRequests"], [])

    def test_business_fffc_log_is_not_login_rejection(self) -> None:
        SERVER.log_game_request_attempt(
            "http://game.example/game",
            [(0x1229, b"\x00")],
            10,
            None,
            "direct",
            time.monotonic(),
            code=200,
            data=b"\x01",
            packets=[{"opcode": 0xFFFC, "payload": b"\x00"}],
            outbound_ip="203.0.113.8",
        )

        entry = self.logs[-1]
        self.assertIn("业务请求被拒绝", entry["message"])
        self.assertEqual(entry["detail"]["responseKind"], "business_rejected")
        self.assertEqual(entry["detail"]["failureKind"], "business_rejected")
        self.assertFalse(entry["detail"]["sessionInvalid"])
        self.assertFalse(entry["detail"]["loginRejected"])

    def test_embedded_fffc_bytes_in_normal_packet_log_as_normal(self) -> None:
        payload = b"\x00" * 12 + b"\xff\xfc\x00\x00" + b"\x00" * 12
        SERVER.log_game_request_attempt(
            "http://game.example/game",
            [(0x1152, b"\x00")],
            10,
            None,
            "direct",
            time.monotonic(),
            code=200,
            data=b"response",
            packets=[{"opcode": 0x8152, "payload": payload}],
            outbound_ip="203.0.113.8",
        )

        entry = self.logs[-1]
        self.assertEqual(entry["detail"]["responseKind"], "normal")
        self.assertEqual(entry["detail"]["failureKind"], "")
        self.assertFalse(entry["detail"]["sessionInvalid"])
        self.assertFalse(entry["detail"]["serverRejected"])

    def test_http_log_categories_remain_distinct(self) -> None:
        for code in (503, 403, 429, 500):
            SERVER.log_game_request_attempt(
                "http://game.example/game",
                [(0x1104, b"\x00")],
                10,
                None,
                "direct",
                time.monotonic(),
                code=code,
                data=b"response",
                packets=[self.packet(0x8104)],
                outbound_ip="203.0.113.8",
            )

        by_http = {entry["detail"]["http"]: entry for entry in self.logs}
        self.assertEqual(by_http[503]["detail"]["failureKind"], "network")
        self.assertEqual(by_http[503]["detail"]["httpKind"], "transport_failed")
        self.assertFalse(by_http[503]["detail"]["loginRejected"])
        self.assertEqual(by_http[403]["detail"]["failureKind"], "server_login_rejected")
        self.assertTrue(by_http[403]["detail"]["loginRejected"])
        self.assertEqual(by_http[429]["detail"]["failureKind"], "throttle")
        self.assertFalse(by_http[429]["detail"]["loginRejected"])
        self.assertEqual(by_http[500]["detail"]["failureKind"], "protocol_unknown")
        self.assertEqual(by_http[500]["detail"]["httpKind"], "server_error")
        self.assertFalse(by_http[500]["detail"]["loginRejected"])

    def test_direct_failure_and_proxy_retry_each_get_a_log_entry(self) -> None:
        SERVER.ACCOUNTS["test-session"] = {
            "username": "1608601",
            "area": {"areaName": "周年服351区(新服)"},
        }
        SERVER.assigned_proxy_node = lambda _account_id: ""
        SERVER._post_game_direct = lambda _url, _body: (502, b"", [])
        SERVER.clash_proxy_groups = lambda: ("自动选择", ["测试节点"])
        SERVER.switch_clash_node = lambda _group, _node: None
        SERVER._post_game_via_socks = lambda _url, _body, _node: (
            200,
            b"\x01",
            [self.packet(0x8104)],
        )

        code, _data, _packets = SERVER.post_game(
            "http://game.example/game",
            [(0x1104, b"\x00")],
            1,
            account_id="test-session",
        )

        self.assertEqual(code, 200)
        self.assertEqual(len(self.logs), 2)
        direct, proxy = self.logs
        self.assertEqual(direct["source"], "game:request")
        self.assertEqual(direct["level"], "warn")
        self.assertIn("原服请求1608601区351", direct["message"])
        self.assertIn("IP是：直连 203.0.113.8", direct["message"])
        self.assertIn("｜读取宝库｜", direct["message"])
        self.assertIn("失败：HTTP 502", direct["message"])
        self.assertEqual(direct["detail"]["http"], 502)
        self.assertTrue(direct["detail"]["transportFailed"])
        self.assertIn("IP是：代理 测试节点 103.62.49.130", proxy["message"])
        self.assertIn("｜读取宝库｜", proxy["message"])
        self.assertEqual(proxy["detail"]["http"], 200)
        self.assertEqual(proxy["detail"]["responseOpcodes"], ["0x8104"])
        self.assertEqual(proxy["detail"]["outboundIp"], "103.62.49.130")

    def test_proxy_failures_pause_tasks_but_keep_account_for_heartbeat(self) -> None:
        stop_calls = []
        switched_nodes = []
        SERVER.ACCOUNTS["test-session"] = {
            "username": "1608601",
            "area": {"areaName": "周年服351区(新服)"},
            "started": True,
            "stopEvent": threading.Event(),
        }
        SERVER.assigned_proxy_node = lambda _account_id: "节点1"
        SERVER.clash_proxy_groups = lambda: (
            "自动选择",
            [f"节点{index}" for index in range(1, 7)],
        )
        SERVER.switch_clash_node = lambda _group, node: switched_nodes.append(node)
        SERVER._post_game_via_socks = lambda _url, _body, _node: (502, b"", [])
        SERVER.stop_account = lambda session_id, *, reason="": stop_calls.append((session_id, reason))

        with self.assertRaisesRegex(RuntimeError, "连续尝试4个IP"):
            SERVER.post_game(
                "http://game.example/game",
                [(0x1104, b"\x00")],
                1,
                account_id="test-session",
            )

        self.assertEqual(switched_nodes, ["节点1", "节点2", "节点3", "节点4"])
        request_logs = [
            entry for entry in self.logs
            if entry.get("source") == "game:request"
        ]
        self.assertEqual(len(request_logs), 4)
        for entry in request_logs:
            self.assertIn("103.62.49.130", entry["message"])
        self.assertEqual(stop_calls, [])
        self.assertTrue(SERVER.ACCOUNTS["test-session"]["networkDegraded"])

    def test_manual_proxy_failure_does_not_rotate_nodes(self) -> None:
        stop_calls = []
        switched_nodes = []
        SERVER.ACCOUNTS["test-session"] = {
            "username": "1608601",
            "area": {"areaName": "周年服351区(新服)"},
            "started": True,
            "stopEvent": threading.Event(),
            "proxyMode": "manual",
            "proxyNode": "节点2",
        }
        SERVER.clash_proxy_groups = lambda: ("自动选择", ["节点1", "节点2", "节点3"])
        SERVER.switch_clash_node = lambda _group, node: switched_nodes.append(node)
        SERVER._post_game_via_socks = lambda _url, _body, _node: (502, b"", [])
        SERVER.stop_account = lambda session_id, *, reason="": stop_calls.append((session_id, reason))

        with self.assertRaisesRegex(RuntimeError, "手动选择的IP 节点2"):
            SERVER.post_game(
                "http://game.example/game",
                [(0x1003, b"\x00")],
                1,
                account_id="test-session",
            )

        self.assertEqual(switched_nodes, ["节点2"])
        self.assertEqual(stop_calls, [])
        self.assertTrue(SERVER.ACCOUNTS["test-session"]["networkDegraded"])

    def test_closing_account_cancels_remaining_proxy_switches(self) -> None:
        switched_nodes = []
        stop_event = threading.Event()
        SERVER.ACCOUNTS["test-session"] = {
            "username": "1608601",
            "area": {"areaName": "周年服351区(新服)"},
            "started": True,
            "stopEvent": stop_event,
        }
        SERVER.assigned_proxy_node = lambda _account_id: "节点1"
        SERVER.clash_proxy_groups = lambda: ("自动选择", ["节点1", "节点2", "节点3"])
        SERVER.switch_clash_node = lambda _group, node: switched_nodes.append(node)

        def fail_then_close(_url, _body, _node):
            stop_event.set()
            return 502, b"", []

        SERVER._post_game_via_socks = fail_then_close

        with self.assertRaisesRegex(SERVER.AccountRequestStopped, "账号已关闭"):
            SERVER.post_game(
                "http://game.example/game",
                [(0x1104, b"\x00")],
                1,
                account_id="test-session",
            )

        self.assertEqual(switched_nodes, ["节点1"])

    def test_request_purpose_uses_protocol_and_dynamic_general_name(self) -> None:
        SERVER.SESSIONS["session-1"] = {
            "generals": [{
                "id": 0xF7F0BF,
                "idHex": "0000000000f7f0bf",
                "name": "步1",
            }],
        }
        energy_payload = struct.pack(">qHH", 0xF7F0BF, 12, 1)

        self.assertEqual(
            SERVER.game_request_purpose([(0x1218, energy_payload)], "session-1"),
            "给将领步1加体",
        )
        self.assertEqual(
            SERVER.game_request_purpose([(0x1540, b"\x00\x64\x00\x1e")], "session-1"),
            "找黄",
        )
        self.assertEqual(
            SERVER.game_request_purpose([(0x1522, b"\x03\x01")], "session-1"),
            "刷黄出征",
        )
        self.assertEqual(
            SERVER.game_request_purpose([
                (0x3144, struct.pack(">HH", 53, 12)),
            ], "session-1"),
            "开启实木宝箱×12",
        )


if __name__ == "__main__":
    unittest.main()
