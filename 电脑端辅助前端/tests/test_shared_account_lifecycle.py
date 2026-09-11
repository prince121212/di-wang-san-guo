from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHARED_PYTHON = ROOT / "shared_core" / "python"
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
if str(SHARED_PYTHON) not in sys.path:
    sys.path.insert(0, str(SHARED_PYTHON))

from dwpm_core.account.lifecycle import (  # noqa: E402
    AccountLifecyclePolicy,
    classify_reconnect_failure,
    is_network_failure_message,
    is_session_invalid_message,
    reconnect_delay_millis,
)
from dwpm_core.contracts import load_behavior_contract  # noqa: E402


SPEC = importlib.util.spec_from_file_location(
    "dwpm_server_shared_account_lifecycle_test",
    SERVER_PATH,
)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class SharedAccountLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = AccountLifecyclePolicy.from_behavior_contract(
            load_behavior_contract(ROOT / "shared_core")
        )

    def test_presentation_and_session_gate_match_shared_ui_contract(self) -> None:
        online = self.policy.snapshot(
            account_enabled=True,
            execution_owner_active=True,
            login_state="REAL_PROTOCOL_ONLINE",
            source_mode=1,
            now_millis=61_000,
            last_validated_at_millis=1_000,
        )
        orphaned = self.policy.snapshot(
            account_enabled=True,
            execution_owner_active=False,
            login_state="REAL_PROTOCOL_ONLINE",
            source_mode=1,
        )
        relogin = self.policy.snapshot(
            account_enabled=True,
            execution_owner_active=True,
            login_state="REAL_PROTOCOL_NEED_RELOGIN",
            source_mode=1,
        )

        self.assertEqual(online["status"], "online")
        self.assertEqual(online["statusText"], "开启")
        self.assertTrue(online["mayUseLiveSession"])
        self.assertTrue(online["shouldProbe"])
        self.assertEqual(orphaned["status"], "stopped")
        self.assertFalse(orphaned["mayUseLiveSession"])
        self.assertEqual(relogin["status"], "offline")
        self.assertTrue(relogin["requiresRelogin"])
        self.assertFalse(relogin["mayUseLiveSession"])

    def test_probe_uses_the_less_aggressive_session_validation_cadence(self) -> None:
        early = self.policy.snapshot(
            account_enabled=True,
            execution_owner_active=True,
            login_state="REAL_PROTOCOL_ONLINE",
            source_mode=1,
            now_millis=60_999,
            last_validated_at_millis=1_000,
        )
        due = self.policy.snapshot(
            account_enabled=True,
            execution_owner_active=True,
            login_state="REAL_PROTOCOL_ONLINE",
            source_mode=1,
            now_millis=61_000,
            last_validated_at_millis=1_000,
        )
        checking = self.policy.snapshot(
            account_enabled=True,
            execution_owner_active=True,
            login_state="REAL_PROTOCOL_CHECKING",
            source_mode=1,
        )

        self.assertFalse(early["shouldProbe"])
        self.assertTrue(due["shouldProbe"])
        self.assertTrue(checking["shouldProbe"])
        self.assertEqual(due["heartbeatIntervalMillis"], 20_000)
        self.assertEqual(due["sessionValidationIntervalMillis"], 60_000)
        self.assertEqual(self.policy.probe_failure_pause_threshold, 3)
        self.assertEqual(self.policy.probe_failure_relogin_threshold, 4)

    def test_unknown_persisted_state_fails_closed(self) -> None:
        unknown = self.policy.snapshot(
            account_enabled=True,
            execution_owner_active=True,
            login_state="LEGACY_UNRECOGNIZED_STATE",
            source_mode=1,
        )
        self.assertEqual(unknown["canonicalLoginState"], "offline")
        self.assertEqual(unknown["status"], "offline")
        self.assertTrue(unknown["requiresRelogin"])
        self.assertFalse(unknown["mayUseLiveSession"])

    def test_failure_evidence_stays_fail_closed(self) -> None:
        self.assertTrue(is_session_invalid_message("response-opcode-0x8016"))
        self.assertFalse(is_session_invalid_message("generic session error"))
        self.assertTrue(is_network_failure_message("HTTP=0 bytes=0"))
        self.assertFalse(is_network_failure_message("HTTP 403 forbidden"))
        self.assertFalse(
            is_network_failure_message("没有明确网络故障，响应未确认")
        )
        self.assertEqual(classify_reconnect_failure("HTTP=0 bytes=0"), "network")
        self.assertEqual(classify_reconnect_failure("HTTP 403 forbidden"), "server")
        self.assertEqual(classify_reconnect_failure("HTTP 429"), "throttle")
        self.assertEqual(classify_reconnect_failure("0x8152业务失败"), "unknown")

    def test_backoff_is_category_specific_and_bounded(self) -> None:
        self.assertEqual(reconnect_delay_millis("network", 1), 3 * 60_000)
        self.assertEqual(reconnect_delay_millis("network", 99), 10 * 60_000)
        self.assertEqual(reconnect_delay_millis("server", 1), 10 * 60_000)
        self.assertEqual(reconnect_delay_millis("server", 99), 30 * 60_000)

    def test_desktop_compatibility_functions_delegate_without_behavior_change(self) -> None:
        messages = (
            "HTTP=0 bytes=0",
            "HTTP 403 forbidden",
            "HTTP 429",
            "0x8152业务失败状态 -1",
        )
        for message in messages:
            self.assertEqual(
                SERVER.classify_reconnect_failure(message),
                classify_reconnect_failure(message),
            )
            self.assertEqual(
                SERVER.is_network_failure_message(message),
                is_network_failure_message(message),
            )
        self.assertIs(SERVER.shared_classify_reconnect_failure, classify_reconnect_failure)


if __name__ == "__main__":
    unittest.main()
