from __future__ import annotations

import importlib.util
import pathlib
import sys
import threading
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("desktop_server_session_reconnect", ROOT / "server.py")
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class SessionReconnectTests(unittest.TestCase):
    CAPTURED_FFFC_RESPONSE = bytes.fromhex(
        "01010568568ff1a4498c00000000000000000000000001fffc0000"
    )

    @classmethod
    def captured_fffc_packets(cls) -> list[dict]:
        return SERVER.parse_response(cls.CAPTURED_FFFC_RESPONSE)

    def tearDown(self) -> None:
        for job in list(SERVER.ACCOUNT_RECONNECT_JOBS.values()):
            event = job.get("cancelEvent")
            if event:
                event.set()
        SERVER.ACCOUNT_RECONNECT_JOBS.clear()
        SERVER.ACCOUNTS.clear()
        SERVER.SESSIONS.clear()
        SERVER.AUTO_TASKS.clear()
        SERVER.SAVED_CONFIGS.clear()
        SERVER.COMMAND_CENTER_CLAIMS.clear()

    def test_offline_account_is_rejected_before_any_game_request(self) -> None:
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "offline",
            "stopEvent": threading.Event(),
        }
        with self.assertRaisesRegex(SERVER.AccountRequestStopped, "会话已失效"):
            SERVER.ensure_account_request_active("s1")

    def test_known_invalid_session_trips_one_account_wide_circuit_breaker(self) -> None:
        stop_event = threading.Event()
        task_event = threading.Event()
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "username": "u1",
            "area": {"areaName": "351区"},
            "started": True,
            "status": "online",
            "stopEvent": stop_event,
        }
        SERVER.SESSIONS["s1"] = {
            "sessionId": "s1",
            "savedTasksStarted": True,
        }
        SERVER.AUTO_TASKS["t1"] = {
            "taskId": "t1",
            "type": "auto-brush-yellow",
            "sessionId": "s1",
            "status": "running",
            "config": {"sessionId": "s1"},
            "stopEvent": task_event,
            "logs": [],
        }

        with patch.object(SERVER, "account_log"), \
             patch.object(SERVER, "system_log"), \
             patch.object(SERVER, "persist_runtime_state"), \
             patch.object(SERVER, "schedule_account_reconnect", return_value=123) as schedule:
            SERVER.mark_account_offline_if_session_invalid(
                "s1",
                "response-opcode-0x8016 明确拒绝登录态",
            )
            SERVER.mark_account_offline_if_session_invalid(
                "s1",
                "response-opcode-0x8016 明确拒绝登录态",
            )

        self.assertTrue(stop_event.is_set())
        self.assertTrue(task_event.is_set())
        self.assertNotIn("s1", SERVER.SESSIONS)
        self.assertEqual(SERVER.ACCOUNTS["s1"]["status"], "offline")
        self.assertTrue(SERVER.ACCOUNTS["s1"]["started"])
        self.assertEqual(SERVER.AUTO_TASKS["t1"]["status"], "stopped")
        schedule.assert_called_once_with(
            "s1",
            "response-opcode-0x8016 明确拒绝登录态",
            failure_kind="server",
        )

    def test_captured_heartbeat_rejection_does_not_rotate_proxy_or_return_to_caller(self) -> None:
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "username": "u1",
            "area": {"areaName": "351区"},
            "started": True,
            "status": "online",
            "proxyMode": "auto",
            "stopEvent": threading.Event(),
        }
        invalid = self.CAPTURED_FFFC_RESPONSE
        invalid_packets = self.captured_fffc_packets()
        calls = []

        def direct(_url, _body):
            calls.append("direct")
            return 200, invalid, invalid_packets

        with patch.object(SERVER, "assigned_proxy_node", return_value=""), \
             patch.object(SERVER, "resolve_outbound_ip", return_value="203.0.113.8"), \
             patch.object(SERVER, "wait_for_game_request_slot"), \
             patch.object(SERVER, "_post_game_direct", side_effect=direct), \
             patch.object(SERVER, "log_game_request_attempt"), \
             patch.object(SERVER, "mark_account_offline_for_server_rejection") as mark:
            with self.assertRaisesRegex(SERVER.GameServerRejected, "0xfffc"):
                SERVER.post_game(
                    "http://game.example/game",
                    [(0x3110, b"\x01\x00")],
                    1,
                    account_id="s1",
                )

        self.assertEqual(calls, ["direct"])
        mark.assert_called_once()

    def test_normal_large_role_response_with_fffc_bytes_is_not_session_rejected(self) -> None:
        payload = b"\x00" * 100 + b"\xff\xfc\x00\x00" + b"\x00" * 100
        packets = [
            {"opcode": 0x8001, "payload": b"\x00"},
            {"opcode": 0x8004, "payload": payload},
            {"opcode": 0xA129, "payload": b"\x00"},
        ]
        result = SERVER.classify_game_response(
            [(0x1016, b"\x00" * 8)],
            b"normal-prefix" + payload,
            packets,
        )
        self.assertEqual(result["kind"], "normal")
        self.assertFalse(result["sessionInvalid"])

    def test_normal_8152_business_payload_with_fffc_bytes_is_not_session_rejected(self) -> None:
        payload = b"\x00" + b"\x00" * 8 + b"\xff\xfc\x00\x00" + b"\x00" * 24
        result = SERVER.classify_game_response(
            [(0x1152, b"\x01" + b"\x00" * 8)],
            b"x" * 22 + payload,
            [{"opcode": 0x8152, "payload": payload}],
        )
        self.assertEqual(result["kind"], "normal")
        self.assertFalse(result["sessionInvalid"])

    def test_explicit_8016_without_8004_is_session_rejected_even_if_text_changes(self) -> None:
        packets = [{
            "opcode": 0x8016,
            "payload": b"\xff\x00\x0f" + "角色登录状态异常".encode(),
        }]
        result = SERVER.classify_game_response(
            [(0x1016, b"\x00" * 8)],
            b"response",
            packets,
        )
        self.assertEqual(result["kind"], "session_rejected")
        self.assertEqual(result["evidence"], "response-opcode-0x8016")

    def test_8004_success_wins_over_contradictory_8016_packet(self) -> None:
        result = SERVER.classify_game_response(
            [(0x1016, b"\x00" * 8)],
            b"response",
            [
                {"opcode": 0x8016, "payload": b"\x00"},
                {"opcode": 0x8004, "payload": b"\x00" * 32},
            ],
        )
        self.assertEqual(result["kind"], "normal")
        self.assertFalse(result["sessionInvalid"])

    def test_captured_fffc_is_session_evidence_only_for_login_or_heartbeat(self) -> None:
        packets = self.captured_fffc_packets()
        heartbeat = SERVER.classify_game_response(
            [(0x3110, b"\x01\x00")],
            self.CAPTURED_FFFC_RESPONSE,
            packets,
        )
        login = SERVER.classify_game_response(
            [(0x1004, b"\x00" * 8)],
            self.CAPTURED_FFFC_RESPONSE,
            packets,
        )
        business = SERVER.classify_game_response(
            [(0x1229, b"\x00")],
            self.CAPTURED_FFFC_RESPONSE,
            packets,
        )
        self.assertEqual(heartbeat["kind"], "session_rejected")
        self.assertEqual(login["kind"], "session_rejected")
        self.assertEqual(business["kind"], "business_rejected")
        self.assertFalse(business["sessionInvalid"])

    def test_reconnecting_gate_allows_only_explicit_login_handshake(self) -> None:
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "checking",
            "reconnectState": "reconnecting",
            "stopEvent": threading.Event(),
        }
        with self.assertRaisesRegex(SERVER.AccountRequestStopped, "停止后续"):
            SERVER.ensure_account_request_active("s1")
        SERVER.ensure_account_request_active("s1", allow_reconnecting=True)

    def test_post_game_reconnect_login_allowance_reaches_transport(self) -> None:
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "checking",
            "reconnectState": "reconnecting",
            "proxyMode": "auto",
            "stopEvent": threading.Event(),
        }
        calls = []

        def direct(_url, _body):
            calls.append("sent")
            return 200, b"\x01", [{"opcode": 0x8003, "payload": b"\x00"}]

        with patch.object(SERVER, "assigned_proxy_node", return_value=""), \
             patch.object(SERVER, "resolve_outbound_ip", return_value="203.0.113.8"), \
             patch.object(SERVER, "wait_for_game_request_slot"), \
             patch.object(SERVER, "_post_game_direct", side_effect=direct), \
             patch.object(SERVER, "log_game_request_attempt"):
            with self.assertRaises(SERVER.AccountRequestStopped):
                SERVER.post_game(
                    "http://game.example/game",
                    [(0x1003, b"\x00")],
                    0,
                    account_id="s1",
                )
            SERVER.post_game(
                "http://game.example/game",
                [(0x1003, b"\x00")],
                0,
                account_id="s1",
                allow_reconnecting=True,
            )

        self.assertEqual(calls, ["sent"])

    def test_first_heartbeat_during_reconnect_reaches_transport(self) -> None:
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "checking",
            "reconnectState": "reconnecting",
            "proxyMode": "auto",
            "stopEvent": threading.Event(),
        }
        sess = {
            "sessionId": "s1",
            "gameHttp": "http://game.example/game",
            "dm": 1,
        }
        calls = []

        def direct(_url, _body):
            calls.append("heartbeat")
            return 200, b"\x01", [{"opcode": 0xA110, "payload": b"\x00"}]

        with patch.object(SERVER, "assigned_proxy_node", return_value=""), \
             patch.object(SERVER, "resolve_outbound_ip", return_value="203.0.113.8"), \
             patch.object(SERVER, "wait_for_game_request_slot"), \
             patch.object(SERVER, "_post_game_direct", side_effect=direct), \
             patch.object(SERVER, "log_game_request_attempt"), \
             patch.object(SERVER, "update_military_intel_from_packets", return_value={}):
            hb = SERVER.execute_heartbeat(sess, allow_reconnecting=True)

        self.assertTrue(hb["online"])
        self.assertEqual(calls, ["heartbeat"])

    def test_saved_reconnect_minutes_are_used(self) -> None:
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "username": "u1",
            "area": {"areaName": "351区"},
        }
        SERVER.SAVED_CONFIGS["s1"] = {"reconnectDelayMinutes": 17}
        self.assertEqual(SERVER.account_reconnect_delay_minutes("s1"), 17)

    def test_network_failure_rotates_twice_then_goes_offline(self) -> None:
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "online",
            "stopEvent": threading.Event(),
        }
        SERVER.SESSIONS["s1"] = {"sessionId": "s1"}

        def rotate(session_id: str) -> dict:
            acc = SERVER.ACCOUNTS[session_id]
            switch_count = int(acc.get("heartbeatNetworkSwitchCount") or 0) + 1
            attempt = int(acc.get("heartbeatNetworkSwitchAttemptCount") or 0) + 1
            acc["heartbeatNetworkFailureCount"] = 0
            acc["heartbeatNetworkSwitchCount"] = switch_count
            acc["heartbeatNetworkSwitchAttemptCount"] = attempt
            return {
                "success": True,
                "attempt": attempt,
                "switchCount": switch_count,
            }

        with patch.object(SERVER, "pause_tasks_for_transient_network_failure"), \
             patch.object(SERVER, "account_log"), \
             patch.object(SERVER, "persist_runtime_state"), \
             patch.object(SERVER, "rotate_heartbeat_proxy", side_effect=rotate) as rotate_proxy, \
             patch.object(SERVER, "mark_account_offline_for_network_failure") as mark:
            observed = [
                SERVER.record_heartbeat_network_failure("s1", "HTTP=0 bytes=0")
                for _ in range(9)
            ]

        self.assertEqual(observed, [1, 2, 3, 1, 2, 3, 1, 2, 3])
        self.assertEqual(rotate_proxy.call_count, 2)
        mark.assert_called_once()

    def test_noncritical_preparation_failure_does_not_pause_tasks(self) -> None:
        task_stop = threading.Event()
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "online",
            "proxyMode": "local",
            "stopEvent": threading.Event(),
        }
        SERVER.AUTO_TASKS["t1"] = {
            "taskId": "t1",
            "type": "auto-brush-yellow",
            "sessionId": "s1",
            "status": "running",
            "config": {"sessionId": "s1"},
            "stopEvent": task_stop,
            "logs": [],
        }
        with patch.object(
            SERVER,
            "resolve_outbound_ip",
            return_value="203.0.113.8",
        ), patch.object(
            SERVER,
            "wait_for_game_request_slot",
        ), patch.object(
            SERVER,
            "_post_game_local",
            side_effect=TimeoutError("timed out"),
        ), patch.object(
            SERVER,
            "log_game_request_attempt",
        ), patch.object(
            SERVER,
            "account_log",
        ), patch.object(
            SERVER,
            "pause_tasks_for_transient_network_failure",
        ) as pause:
            with self.assertRaises(RuntimeError):
                SERVER.post_game(
                    "http://game.example/game",
                    [(0x1540, b"")],
                    1,
                    account_id="s1",
                    noncritical=True,
                )

        pause.assert_not_called()
        self.assertFalse(task_stop.is_set())
        self.assertEqual(SERVER.ACCOUNTS["s1"]["status"], "online")

    def test_successful_heartbeat_clears_network_failure_streak(self) -> None:
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "online",
            "heartbeatNetworkFailureCount": 3,
            "heartbeatNetworkSwitchCount": 2,
            "heartbeatNetworkSwitchAttemptCount": 2,
            "heartbeatNetworkTriedProxyNodes": ["节点A", "节点B"],
            "networkDegraded": True,
            "resumeResidentTasksAfterNetworkRecovery": False,
            "stopEvent": threading.Event(),
        }
        sess = {"sessionId": "s1"}
        with patch.object(SERVER, "account_log"), \
             patch.object(SERVER, "persist_runtime_state"):
            SERVER.clear_heartbeat_network_failures("s1", sess)
        self.assertEqual(SERVER.ACCOUNTS["s1"]["heartbeatNetworkFailureCount"], 0)
        self.assertEqual(SERVER.ACCOUNTS["s1"]["heartbeatNetworkSwitchCount"], 0)
        self.assertEqual(SERVER.ACCOUNTS["s1"]["heartbeatNetworkSwitchAttemptCount"], 0)
        self.assertEqual(SERVER.ACCOUNTS["s1"]["heartbeatNetworkTriedProxyNodes"], [])
        self.assertFalse(SERVER.ACCOUNTS["s1"]["networkDegraded"])

    def test_first_network_disconnect_reconnect_delay_is_three_minutes(self) -> None:
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "offline",
            "stopEvent": threading.Event(),
        }
        now = 1_000_000
        with patch.object(SERVER, "now_ms", return_value=now), \
             patch.object(SERVER, "account_log"), \
             patch.object(SERVER, "persist_runtime_state"), \
             patch.object(SERVER.threading, "Thread") as thread_class:
            reconnect_at = SERVER.schedule_account_reconnect(
                "s1",
                "两次自动换IP后心跳仍因网络问题失败",
                failure_kind="network",
            )

        self.assertEqual(reconnect_at, now + 3 * 60 * 1000)
        self.assertEqual(SERVER.ACCOUNTS["s1"]["reconnectDelayMinutes"], 3)
        thread_class.return_value.start.assert_called_once()

    def test_failure_evidence_distinguishes_network_from_server_rejection(self) -> None:
        self.assertTrue(SERVER.is_network_failure_message("HTTP=0 bytes=0"))
        self.assertTrue(SERVER.is_network_failure_message("timed out"))
        self.assertFalse(SERVER.is_network_failure_message("HTTP 403 forbidden"))
        self.assertFalse(SERVER.is_network_failure_message("fffc0000 会话失效"))
        self.assertFalse(
            SERVER.is_network_failure_message(
                "协议响应未确认（非网络故障、非登录态拒绝）"
            )
        )
        self.assertEqual(
            SERVER.classify_reconnect_failure("HTTP=0 bytes=0"),
            "network",
        )
        self.assertEqual(
            SERVER.classify_reconnect_failure("HTTP 403 forbidden"),
            "server",
        )
        self.assertEqual(
            SERVER.classify_reconnect_failure("0x8152业务失败状态 -1"),
            "unknown",
        )
        self.assertEqual(
            SERVER.classify_reconnect_failure("HTTP 429"),
            "throttle",
        )

    def test_http_status_classification_does_not_call_every_response_auth_rejection(self) -> None:
        self.assertEqual(SERVER.classify_http_response(401), "auth_rejected")
        self.assertEqual(SERVER.classify_http_response(403), "auth_rejected")
        self.assertEqual(SERVER.classify_http_response(429), "throttled")
        self.assertEqual(SERVER.classify_http_response(409), "application_rejected")
        self.assertEqual(SERVER.classify_http_response(404), "application_rejected")
        self.assertEqual(SERVER.classify_http_response(500), "server_error")
        self.assertEqual(SERVER.classify_http_response(503), "transport_failed")
        self.assertEqual(SERVER.classify_http_response(200), "normal")

    def test_empty_http_200_is_protocol_unknown_not_network_or_login_rejection(self) -> None:
        disposition = SERVER.classify_game_response(
            [(0x3110, b"\x01\x00")],
            b"",
            [],
        )
        self.assertEqual(disposition["kind"], "protocol_unconfirmed")
        self.assertFalse(disposition["sessionInvalid"])
        self.assertFalse(SERVER.transport_failed(200, b"", []))
        with self.assertRaises(SERVER.GameProtocolResponseError):
            SERVER.enforce_explicit_game_response(
                None,
                [(0x3110, b"\x01\x00")],
                200,
                b"",
                [],
            )


if __name__ == "__main__":
    unittest.main()
