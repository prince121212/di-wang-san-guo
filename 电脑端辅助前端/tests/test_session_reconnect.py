from __future__ import annotations

import importlib.util
import json
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
        SERVER.SHARED_RESIDENT_WAKE_OWNERS.clear()
        SERVER.ACCOUNT_RESIDENT_RECOVERY_LOCKS.clear()
        SERVER.ACCOUNT_RESIDENT_RECOVERY_GENERATIONS.clear()

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

    def test_restart_reconciles_live_session_with_stale_reconnect_countdown(self) -> None:
        stale_stop = threading.Event()
        stale_stop.set()
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "online",
            "reconnectState": "countdown",
            "reconnectAt": 123456,
            "reconnectReason": "旧倒计时",
            "reconnectGeneration": "old-generation",
            "reconnectFailureKind": "unknown",
            "reconnectFailureCount": 4,
            "heartbeatNetworkFailureCount": 3,
            "heartbeatUnconfirmedFailureCount": 99,
            "networkDegraded": True,
            "responseUnconfirmed": True,
            "lastError": "旧错误",
            "stopEvent": stale_stop,
        }
        SERVER.SESSIONS["s1"] = {"sessionId": "s1"}

        with patch.object(SERVER, "now_ms", return_value=987654), \
             patch.object(SERVER, "account_log") as account_log:
            reconciled = SERVER.reconcile_restored_live_session_reconnect_states()

        acc = SERVER.ACCOUNTS["s1"]
        self.assertEqual(reconciled, ["s1"])
        self.assertEqual(acc["status"], "checking")
        self.assertEqual(acc["reconnectState"], "")
        self.assertIsNone(acc["reconnectAt"])
        self.assertEqual(acc["reconnectGeneration"], "")
        self.assertEqual(acc["heartbeatNetworkFailureCount"], 0)
        self.assertEqual(acc["heartbeatUnconfirmedFailureCount"], 0)
        self.assertFalse(acc["networkDegraded"])
        self.assertFalse(acc["responseUnconfirmed"])
        self.assertFalse(acc["stopEvent"].is_set())
        self.assertEqual(acc["lastHeartbeat"]["checkedAt"], 987654)
        account_log.assert_called_once()

    def test_restart_keeps_reconnect_countdown_without_live_session(self) -> None:
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "offline",
            "reconnectState": "countdown",
            "reconnectAt": 123456,
            "stopEvent": threading.Event(),
        }

        with patch.object(SERVER, "account_log") as account_log:
            reconciled = SERVER.reconcile_restored_live_session_reconnect_states()

        self.assertEqual(reconciled, [])
        self.assertEqual(SERVER.ACCOUNTS["s1"]["reconnectState"], "countdown")
        self.assertEqual(SERVER.ACCOUNTS["s1"]["reconnectAt"], 123456)
        account_log.assert_not_called()

    def test_startup_sync_restores_shared_record_before_relogin(self) -> None:
        self.assertNotEqual(SERVER.REPORT_DIR, ROOT / "reports")
        SERVER.SHARED_PYTHON_CORE.account_records_replace_json("[]")
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "username": "u1",
            "password": "secret",
            "serverQuery": "周年服352区",
            "platform": "热血三国联盟",
            "platformKey": "sglm",
            "serial": "0",
            "displayName": "测试账号",
            "area": {"areaName": "周年服352区"},
            "role": {"roleId": 7, "roleName": "测试角色"},
            "started": True,
            "status": "offline",
            "lastError": "等待重连",
            "stopEvent": threading.Event(),
        }

        count = SERVER.sync_restored_accounts_to_shared_core()

        record = json.loads(
            SERVER.SHARED_PYTHON_CORE.account_record_json("s1")
        )["account"]
        self.assertEqual(count, 1)
        self.assertEqual(record["accountRef"], "s1")
        self.assertEqual(record["username"], "u1")
        self.assertEqual(record["loginState"], "REAL_PROTOCOL_OFFLINE")
        self.assertEqual(SERVER._desktop_load_shared_password("s1"), "secret")

    def test_shared_login_commit_replaces_stale_stop_and_reconnect_state(
        self,
    ) -> None:
        old_stop = threading.Event()
        old_stop.set()
        reconnect_cancel = threading.Event()

        class OldHeartbeat:
            @staticmethod
            def is_alive() -> bool:
                return True

        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "username": "u1",
            "password": "secret",
            "started": True,
            "status": "offline",
            "stopEvent": old_stop,
            "thread": OldHeartbeat(),
            "reconnectState": "countdown",
            "reconnectAt": 123456,
            "reconnectGeneration": "old",
            "reconnectFailureKind": "server",
            "reconnectFailureCount": 2,
            "resumeResidentTasksAfterReconnect": True,
        }
        SERVER.ACCOUNT_RECONNECT_JOBS["s1"] = {
            "generation": "old",
            "cancelEvent": reconnect_cancel,
        }

        with patch.object(SERVER, "persist_runtime_state"):
            SERVER._desktop_commit_shared_login_runtime(
                "s1",
                "s1",
                {
                    "sessionId": "s1",
                    "username": "u1",
                    "platform": "热血三国联盟",
                    "role": {"roleId": 7, "roleName": "测试角色"},
                    "area": {"areaName": "周年服352区"},
                },
                "start",
            )

        account = SERVER.ACCOUNTS["s1"]
        self.assertEqual(account["status"], "online")
        self.assertTrue(account["started"])
        self.assertFalse(account["stopEvent"].is_set())
        self.assertNotIn("thread", account)
        self.assertEqual(account["reconnectState"], "")
        self.assertIsNone(account["reconnectAt"])
        self.assertEqual(account["reconnectGeneration"], "")
        self.assertNotIn("s1", SERVER.ACCOUNT_RECONNECT_JOBS)
        self.assertTrue(reconnect_cancel.is_set())
        self.assertIn("s1", SERVER.SESSIONS)
        self.assertTrue(account["resumeResidentTasksAfterReconnect"])
        self.assertTrue(
            account["resumeResidentTasksAfterNetworkRecovery"]
        )
        self.assertFalse(SERVER.SESSIONS["s1"]["savedTasksStarted"])

    def test_heartbeat_local_lifecycle_stop_is_not_counted_as_unconfirmed(self) -> None:
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "online",
            "stopEvent": threading.Event(),
        }
        SERVER.SESSIONS["s1"] = {"sessionId": "s1"}

        with patch.object(
            SERVER,
            "execute_heartbeat",
            side_effect=SERVER.AccountRequestStopped("本地门禁已关闭"),
        ), patch.object(
            SERVER,
            "record_heartbeat_unconfirmed_failure",
        ) as record_unconfirmed:
            SERVER.heartbeat_worker("s1")

        record_unconfirmed.assert_not_called()

    def test_unconfirmed_heartbeat_counter_is_bounded_by_threshold(self) -> None:
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "online",
            "heartbeatUnconfirmedFailureCount": 99,
            "stopEvent": threading.Event(),
        }

        with patch.object(SERVER, "pause_tasks_for_transient_network_failure"), \
             patch.object(SERVER, "account_log"), \
             patch.object(SERVER, "mark_account_offline_for_unconfirmed_failure"), \
             patch.object(SERVER, "persist_runtime_state"):
            count = SERVER.record_heartbeat_unconfirmed_failure(
                "s1",
                "协议结果未确认",
            )

        self.assertEqual(count, SERVER.HEARTBEAT_UNCONFIRMED_FAILURE_LIMIT)
        self.assertEqual(
            SERVER.ACCOUNTS["s1"]["heartbeatUnconfirmedFailureCount"],
            SERVER.HEARTBEAT_UNCONFIRMED_FAILURE_LIMIT,
        )

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

    def test_shared_raw_game_exchange_uses_prebuilt_account_transport(self) -> None:
        SERVER.SESSIONS["s1"] = {
            "sessionId": "s1",
            "gameHttp": "http://game.example/kingWapServer/HttpClient",
            "platformKey": "sglm",
        }
        with patch.object(
            SERVER,
            "post_game_prebuilt",
            return_value=(200, b"response", []),
        ) as post:
            result = SERVER._desktop_shared_raw_game_exchange({
                "accountRef": "s1",
                "url": "http://game.example/kingWapServer/HttpClient",
                "body": b"prebuilt-packet",
                "readOnly": True,
                "gameCommands": [{
                    "opcode": 0x3110,
                    "payloadHex": "0100",
                }],
            })

        self.assertEqual(result["status"], 200)
        self.assertEqual(result["body"], b"response")
        post.assert_called_once_with(
            "http://game.example/kingWapServer/HttpClient",
            [(0x3110, b"\x01\x00")],
            b"prebuilt-packet",
            account_id="s1",
            noncritical=True,
            platform="sglm",
        )

    def test_shared_resident_wake_owner_is_unique_and_transfers(self) -> None:
        first_stop = threading.Event()
        second_stop = threading.Event()
        SERVER.AUTO_TASKS.update({
            "t1": {
                "taskId": "t1",
                "sessionId": "s1",
                "status": "running",
                "stopEvent": first_stop,
            },
            "t2": {
                "taskId": "t2",
                "sessionId": "s1",
                "status": "running",
                "stopEvent": second_stop,
            },
        })

        self.assertTrue(SERVER.claim_shared_resident_wake_owner("s1", "t1"))
        self.assertFalse(SERVER.claim_shared_resident_wake_owner("s1", "t2"))
        first_stop.set()
        # A stopped owner may still be draining an already-sent pending
        # operation.  Status/stopEvent cannot revoke the lease; hand-off is
        # explicit so another worker never runs the same recovery tick.
        self.assertFalse(SERVER.claim_shared_resident_wake_owner("s1", "t2"))
        SERVER.release_shared_resident_wake_owner("s1", "t1")
        self.assertTrue(SERVER.claim_shared_resident_wake_owner("s1", "t2"))
        self.assertEqual(SERVER.SHARED_RESIDENT_WAKE_OWNERS["s1"], "t2")

        SERVER.release_shared_resident_wake_owner("s1", "t1")
        self.assertEqual(SERVER.SHARED_RESIDENT_WAKE_OWNERS["s1"], "t2")
        SERVER.release_shared_resident_wake_owner("s1", "t2")
        self.assertNotIn("s1", SERVER.SHARED_RESIDENT_WAKE_OWNERS)

    def test_shared_resident_allow_list_contains_only_active_rows(self) -> None:
        self.assertEqual(
            SERVER.desktop_shared_allowed_features([
                "inventory", "brushYellow", "alarm", "inventory",
            ]),
            ["inventory", "brush", "alarm", "daily"],
        )

    def test_shared_result_never_falls_back_to_unrelated_wake_owner(self) -> None:
        owner_stop = threading.Event()
        owner_stop.set()
        owner = {
            "taskId": "owner",
            "type": "auto-brush-yellow",
            "sessionId": "s1",
            "status": "stopped",
            "stopEvent": owner_stop,
            "error": "旧任务错误不应被覆盖",
        }
        SERVER.AUTO_TASKS["owner"] = owner

        resolved = SERVER.shared_resident_result_task(
            "s1",
            "dungeon",
            owner,
        )

        self.assertIsNone(resolved)
        self.assertEqual(owner["type"], "auto-brush-yellow")
        self.assertEqual(owner["error"], "旧任务错误不应被覆盖")
        self.assertNotIn("lastSharedResidentResult", owner)

    def test_general_attention_does_not_stop_inventory_or_alarm(self) -> None:
        owner_stop = threading.Event()
        general_stop = threading.Event()
        alarm_stop = threading.Event()
        owner = {
            "taskId": "inventory-owner",
            "type": "auto-inventory",
            "sessionId": "s1",
            "status": "starting",
            "config": {"sessionId": "s1"},
            "stopEvent": owner_stop,
            "logs": [],
        }
        general = {
            "taskId": "general",
            "type": "auto-general",
            "sessionId": "s1",
            "status": "running",
            "config": {"sessionId": "s1"},
            "stopEvent": general_stop,
            "logs": [],
        }
        alarm = {
            "taskId": "alarm",
            "type": "auto-alarm",
            "sessionId": "s1",
            "status": "running",
            "config": {"sessionId": "s1"},
            "stopEvent": alarm_stop,
            "logs": [],
        }
        SERVER.AUTO_TASKS.update({
            "inventory-owner": owner,
            "general": general,
            "alarm": alarm,
        })
        SERVER.SESSIONS["s1"] = {"sessionId": "s1"}

        calls: list[list[str]] = []
        entered_second_tick = threading.Event()
        release_second_tick = threading.Event()

        def execute_tick(
            _sess,
            *,
            task=None,
            configured_execution_allowed=True,
            allowed_features=None,
        ):
            del task, configured_execution_allowed
            calls.append(list(allowed_features or []))
            if len(calls) == 1:
                return {
                    "feature": "general",
                    "state": "blocked",
                    "success": False,
                    "requiresAttention": True,
                    "message": (
                        "将领维护检查到统弓1体力=38，低于自动加体阈值40，"
                        "但宝库没有活血丹"
                    ),
                    "nextWakeAtMillis": SERVER.now_ms(),
                }
            entered_second_tick.set()
            release_second_tick.wait(3)
            return {
                "feature": None,
                "state": "idle",
                "success": True,
                "requiresAttention": False,
                "message": "测试结束",
                "nextWakeAtMillis": None,
            }

        with patch.object(SERVER, "sync_shared_resident_automation"), \
             patch.object(SERVER, "try_sync_shared_resident_automation"), \
             patch.object(SERVER, "persist_runtime_state"), \
             patch.object(SERVER, "account_log"), \
             patch.object(SERVER, "claim_shared_resident_wake_owner", return_value=True), \
             patch.object(SERVER, "release_shared_resident_wake_owner"), \
             patch.object(SERVER, "_shared_resident_pending", return_value=False), \
             patch.object(SERVER, "wait_for_task_account_online", return_value=True), \
             patch.object(
                 SERVER,
                 "execute_shared_resident_automation_tick",
                 side_effect=execute_tick,
             ):
            worker = threading.Thread(
                target=SERVER.auto_brush_worker,
                args=("inventory-owner",),
            )
            worker.start()
            self.assertTrue(entered_second_tick.wait(3))

            self.assertEqual(general["status"], "error")
            self.assertTrue(general_stop.is_set())
            self.assertEqual(owner["status"], "running")
            self.assertFalse(owner_stop.is_set())
            self.assertEqual(alarm["status"], "running")
            self.assertFalse(alarm_stop.is_set())
            self.assertIn("inventory", calls[1])
            self.assertIn("alarm", calls[1])
            self.assertNotIn("general", calls[1])

            owner_stop.set()
            release_second_tick.set()
            worker.join(3)
            self.assertFalse(worker.is_alive())

    def test_transient_network_pause_is_account_scoped(self) -> None:
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "online",
            "stopEvent": threading.Event(),
        }
        SERVER.SESSIONS["s1"] = {"sessionId": "s1"}
        for task_id, task_type in (("brush", "auto-brush-yellow"), ("dungeon", "dungeon")):
            SERVER.AUTO_TASKS[task_id] = {
                "taskId": task_id,
                "type": task_type,
                "sessionId": "s1",
                "status": "running",
                "config": {"sessionId": "s1"},
                "stopEvent": threading.Event(),
                "logs": [],
            }

        with patch.object(SERVER, "account_log"), \
             patch.object(SERVER, "system_log"), \
             patch.object(SERVER, "persist_runtime_state"):
            SERVER.pause_tasks_for_transient_network_failure(
                "s1",
                "手动选择的IP 节点A 无法连接游戏服",
            )

        self.assertTrue(SERVER.ACCOUNTS["s1"]["networkDegraded"])
        self.assertTrue(all(
            task["status"] == "stopped"
            for task in SERVER.AUTO_TASKS.values()
        ))
        self.assertTrue(all(
            task["stopEvent"].is_set()
            for task in SERVER.AUTO_TASKS.values()
        ))
        notices = SERVER.current_important_notices(SERVER.SESSIONS["s1"])
        self.assertTrue(any(
            item["key"] == "account:network"
            for item in notices
        ))
        self.assertFalse(any(
            str(item["key"]).startswith("task:")
            for item in notices
        ))

    def test_noncritical_shared_tick_timeout_does_not_error_wake_owner(self) -> None:
        class StopAfterFirstWait:
            def __init__(self) -> None:
                self.stopped = False

            def is_set(self) -> bool:
                return self.stopped

            def set(self) -> None:
                self.stopped = True

            def wait(self, _timeout=None) -> bool:
                self.stopped = True
                return True

        stop_event = StopAfterFirstWait()
        task = {
            "taskId": "owner",
            "type": "auto-brush-yellow",
            "sessionId": "s1",
            "status": "starting",
            "config": {"sessionId": "s1"},
            "stopEvent": stop_event,
            "logs": [],
        }
        SERVER.AUTO_TASKS["owner"] = task
        SERVER.SESSIONS["s1"] = {"sessionId": "s1"}

        network_error = (
            "手动选择的IP SUB 阿里·上海01 无法连接游戏服，"
            "非关键准备请求稍后重试，任务保持运行；timed out"
        )
        with patch.object(SERVER, "sync_shared_resident_automation"), \
             patch.object(SERVER, "try_sync_shared_resident_automation"), \
             patch.object(SERVER, "task_log"), \
             patch.object(SERVER, "persist_runtime_state"), \
             patch.object(SERVER, "claim_shared_resident_wake_owner", return_value=True), \
             patch.object(SERVER, "release_shared_resident_wake_owner"), \
             patch.object(SERVER, "_shared_resident_pending", return_value=False), \
             patch.object(SERVER, "_desktop_active_shared_resident_keys", return_value=["brushYellow"]), \
             patch.object(SERVER, "wait_for_task_account_online", return_value=True), \
             patch.object(
                 SERVER,
                 "execute_shared_resident_automation_tick",
                 side_effect=RuntimeError(network_error),
             ) as execute, \
             patch.object(
                 SERVER,
                 "mark_account_network_degraded_without_pause",
             ) as degraded:
            SERVER.auto_brush_worker("owner")

        execute.assert_called_once()
        degraded.assert_called_once_with("s1", network_error)
        self.assertEqual(task["status"], "stopped")
        self.assertNotIn("error", task)

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
            "lastHeartbeat": {"online": True, "checkedAt": 100},
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
        self.assertTrue(SERVER.ACCOUNTS["s1"]["networkDegraded"])
        self.assertTrue(SERVER.ACCOUNTS["s1"]["lastHeartbeat"]["online"])
        self.assertIn("timed out", SERVER.ACCOUNTS["s1"]["lastNetworkFailure"]["message"])

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
            "lastNetworkFailure": {
                "message": "timed out",
                "checkedAt": 123,
            },
            "resumeResidentTasksAfterNetworkRecovery": False,
            "stopEvent": threading.Event(),
        }
        sess = {"sessionId": "s1"}
        with patch.object(SERVER, "account_log"), \
             patch.object(SERVER, "persist_runtime_state"):
            attempted = SERVER.clear_heartbeat_network_failures("s1", sess)
        self.assertFalse(attempted)
        self.assertEqual(SERVER.ACCOUNTS["s1"]["heartbeatNetworkFailureCount"], 0)
        self.assertEqual(SERVER.ACCOUNTS["s1"]["heartbeatNetworkSwitchCount"], 0)
        self.assertEqual(SERVER.ACCOUNTS["s1"]["heartbeatNetworkSwitchAttemptCount"], 0)
        self.assertEqual(SERVER.ACCOUNTS["s1"]["heartbeatNetworkTriedProxyNodes"], [])
        self.assertFalse(SERVER.ACCOUNTS["s1"]["networkDegraded"])
        self.assertIsNone(SERVER.ACCOUNTS["s1"]["lastNetworkFailure"])

    def test_heartbeat_recovery_calls_coordinator_and_clears_intent_on_success(
        self,
    ) -> None:
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "online",
            "heartbeatNetworkFailureCount": 1,
            "networkDegraded": True,
            "resumeResidentTasksAfterNetworkRecovery": True,
            "stopEvent": threading.Event(),
        }
        sess = {"sessionId": "s1"}

        def completed(session, *, trigger, force=False):
            self.assertIs(session, sess)
            self.assertEqual(trigger, "heartbeat-recovered")
            SERVER._set_resident_recovery_intent("s1", False)
            return {"ok": True, "complete": True}

        with patch.object(
            SERVER,
            "coordinate_resident_recovery",
            side_effect=completed,
        ) as coordinate, patch.object(SERVER, "account_log"), patch.object(
            SERVER,
            "persist_runtime_state",
        ):
            attempted = SERVER.clear_heartbeat_network_failures("s1", sess)

        coordinate.assert_called_once()
        self.assertTrue(attempted)
        self.assertFalse(
            SERVER.ACCOUNTS["s1"][
                "resumeResidentTasksAfterNetworkRecovery"
            ]
        )
        self.assertFalse(
            SERVER.ACCOUNTS["s1"]["resumeResidentTasksAfterReconnect"]
        )

    def test_heartbeat_recovery_keeps_intent_when_coordinator_is_incomplete(
        self,
    ) -> None:
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "online",
            "networkDegraded": True,
            "resumeResidentTasksAfterNetworkRecovery": True,
            "stopEvent": threading.Event(),
        }
        sess = {"sessionId": "s1"}
        with patch.object(
            SERVER,
            "coordinate_resident_recovery",
            return_value={
                "ok": False,
                "complete": False,
                "errors": {"network": "timed out"},
            },
        ), patch.object(SERVER, "account_log"), patch.object(
            SERVER,
            "persist_runtime_state",
        ):
            attempted = SERVER.clear_heartbeat_network_failures("s1", sess)

        self.assertTrue(attempted)
        self.assertTrue(
            SERVER.ACCOUNTS["s1"][
                "resumeResidentTasksAfterNetworkRecovery"
            ]
        )

    def test_recovery_coordinator_reconciles_before_restarting_saved_tasks(
        self,
    ) -> None:
        sess = {"sessionId": "s1", "savedTasksStarted": True}
        SERVER.SESSIONS["s1"] = sess
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "online",
            "resumeResidentTasksAfterNetworkRecovery": True,
            "stopEvent": threading.Event(),
        }
        calls = []
        core = SERVER.SHARED_PYTHON_CORE
        with patch.object(SERVER, "require_account_online"), patch.object(
            SERVER,
            "_desktop_sync_shared_account",
        ), patch.object(
            core,
            "configure_resident_automation_from_habits",
            side_effect=lambda *_args, **_kwargs: calls.append("configure"),
        ), patch.object(
            core,
            "set_resident_automation_activation",
            side_effect=lambda *_args, **_kwargs: calls.append("deactivate"),
        ), patch.object(
            SERVER,
            "_reconcile_resident_ledgers_for_recovery",
            side_effect=lambda _sess: (
                calls.append("reconcile")
                or {
                    "pendingBefore": ["brush"],
                    "pendingAfter": [],
                    "results": {"brush": {"state": "completed"}},
                    "errors": {},
                }
            ),
        ), patch.object(
            SERVER,
            "resume_saved_resident_tasks",
            side_effect=lambda _sess: (
                calls.append("resume")
                or {"resumed": {"brushYellow": {}}, "errors": {}}
            ),
        ), patch.object(
            SERVER,
            "load_account_habits",
            return_value={},
        ), patch.object(SERVER, "account_log"), patch.object(
            SERVER,
            "persist_runtime_state",
        ):
            result = SERVER.coordinate_resident_recovery(
                sess,
                trigger="fixture",
            )

        self.assertTrue(result["complete"])
        self.assertEqual(
            calls,
            ["configure", "deactivate", "reconcile", "resume"],
        )
        self.assertFalse(
            SERVER.ACCOUNTS["s1"][
                "resumeResidentTasksAfterNetworkRecovery"
            ]
        )

    def test_recovery_coordinator_keeps_intent_when_resume_fails(self) -> None:
        sess = {"sessionId": "s1", "savedTasksStarted": True}
        SERVER.SESSIONS["s1"] = sess
        SERVER.ACCOUNTS["s1"] = {
            "sessionId": "s1",
            "started": True,
            "status": "online",
            "resumeResidentTasksAfterNetworkRecovery": True,
            "stopEvent": threading.Event(),
        }
        core = SERVER.SHARED_PYTHON_CORE
        with patch.object(SERVER, "require_account_online"), patch.object(
            SERVER,
            "_desktop_sync_shared_account",
        ), patch.object(
            core,
            "configure_resident_automation_from_habits",
            return_value={},
        ), patch.object(
            core,
            "set_resident_automation_activation",
            return_value={},
        ), patch.object(
            SERVER,
            "_reconcile_resident_ledgers_for_recovery",
            return_value={
                "pendingBefore": [],
                "pendingAfter": [],
                "results": {},
                "errors": {},
            },
        ), patch.object(
            SERVER,
            "resume_saved_resident_tasks",
            return_value={
                "resumed": {},
                "errors": {"brushYellow": "fixture"},
            },
        ), patch.object(
            SERVER,
            "load_account_habits",
            return_value={},
        ), patch.object(SERVER, "account_log"), patch.object(
            SERVER,
            "persist_runtime_state",
        ):
            result = SERVER.coordinate_resident_recovery(
                sess,
                trigger="fixture",
            )

        self.assertFalse(result["complete"])
        self.assertTrue(
            SERVER.ACCOUNTS["s1"][
                "resumeResidentTasksAfterNetworkRecovery"
            ]
        )

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
