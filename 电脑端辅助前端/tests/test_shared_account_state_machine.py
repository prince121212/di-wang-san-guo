from __future__ import annotations

import json
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHARED_PYTHON = ROOT / "shared_core" / "python"
if str(SHARED_PYTHON) not in sys.path:
    sys.path.insert(0, str(SHARED_PYTHON))

from dwpm_core.account.state_machine import (  # noqa: E402
    EVENT_LOGIN_FAILED,
    EVENT_LOGIN_SUCCEEDED,
    EVENT_NETWORK_UNAVAILABLE,
    EVENT_PROBE_UNAVAILABLE,
    EVENT_PROBE_VALID,
    EVENT_PROCESS_RECOVERED,
    EVENT_SESSION_EXPIRED,
    EVENT_USER_START,
    EVENT_USER_STOP,
    reduce_account_event,
)
from dwpm_core.facade import CoreFacade  # noqa: E402


SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location(
    "dwpm_server_shared_account_state_machine_test",
    SERVER_PATH,
)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class SharedAccountStateMachineTests(unittest.TestCase):
    def test_start_login_probe_and_stop_timeline(self) -> None:
        state = {
            "desiredStarted": False,
            "loginState": "REAL_PROTOCOL_STOPPED",
            "sessionCredentialPresent": False,
        }
        started = reduce_account_event(
            state,
            EVENT_USER_START,
            now_millis=1_000,
        )
        online = reduce_account_event(
            started,
            EVENT_LOGIN_SUCCEEDED,
            now_millis=2_000,
        )
        recovered = reduce_account_event(
            online,
            EVENT_PROCESS_RECOVERED,
            now_millis=3_000,
        )
        validated = reduce_account_event(
            recovered,
            EVENT_PROBE_VALID,
            now_millis=4_000,
        )
        stopped = reduce_account_event(
            validated,
            EVENT_USER_STOP,
            now_millis=5_000,
        )

        self.assertEqual(started["loginState"], "REAL_PROTOCOL_CHECKING")
        self.assertEqual(started["nextOperation"], "login")
        self.assertTrue(online["liveSessionUsable"])
        self.assertEqual(recovered["nextOperation"], "probe")
        self.assertFalse(recovered["liveSessionUsable"])
        self.assertTrue(validated["liveSessionUsable"])
        self.assertEqual(stopped["loginState"], "REAL_PROTOCOL_STOPPED")
        self.assertFalse(stopped["desiredStarted"])
        self.assertEqual(stopped["sessionSecretAction"], "retain")

    def test_failure_category_controls_persistent_backoff(self) -> None:
        base = {
            "desiredStarted": True,
            "loginState": "REAL_PROTOCOL_CHECKING",
            "sessionCredentialPresent": False,
        }
        network_first = reduce_account_event(
            base,
            EVENT_LOGIN_FAILED,
            now_millis=1_000,
            details={"message": "HTTP=0 bytes=0"},
        )
        network_second = reduce_account_event(
            network_first,
            EVENT_LOGIN_FAILED,
            now_millis=2_000,
            details={"message": "connection reset"},
        )
        server = reduce_account_event(
            network_second,
            EVENT_LOGIN_FAILED,
            now_millis=3_000,
            details={"message": "HTTP 403 forbidden"},
        )

        self.assertEqual(network_first["failureKind"], "network")
        self.assertEqual(network_first["failureCount"], 1)
        self.assertEqual(network_first["nextRetryAtMillis"], 181_000)
        self.assertEqual(network_second["failureCount"], 2)
        self.assertEqual(network_second["nextRetryAtMillis"], 302_000)
        self.assertEqual(server["failureKind"], "server")
        self.assertEqual(server["failureCount"], 1)
        self.assertEqual(server["nextRetryAtMillis"], 603_000)
        self.assertEqual(server["sessionSecretAction"], "delete")

    def test_network_pause_and_session_expiry_never_expose_live_session(self) -> None:
        online = {
            "desiredStarted": True,
            "loginState": "REAL_PROTOCOL_ONLINE",
            "sessionCredentialPresent": True,
        }
        disconnected = reduce_account_event(
            online,
            EVENT_NETWORK_UNAVAILABLE,
            now_millis=10_000,
        )
        unavailable = reduce_account_event(
            online,
            EVENT_PROBE_UNAVAILABLE,
            now_millis=20_000,
            details={"message": "timed out"},
        )
        expired = reduce_account_event(
            online,
            EVENT_SESSION_EXPIRED,
            now_millis=30_000,
            details={"message": "response-opcode-0x8016"},
        )

        self.assertEqual(disconnected["nextOperation"], "wait-network")
        self.assertFalse(disconnected["liveSessionUsable"])
        self.assertEqual(unavailable["failureKind"], "network")
        self.assertEqual(unavailable["nextOperation"], "probe")
        self.assertFalse(unavailable["liveSessionUsable"])
        self.assertEqual(expired["loginState"], "REAL_PROTOCOL_NEED_RELOGIN")
        self.assertEqual(expired["nextOperation"], "login")
        self.assertEqual(expired["sessionSecretAction"], "retain")
        self.assertFalse(expired["liveSessionUsable"])

    def test_process_recovery_selects_probe_or_login_without_sending(self) -> None:
        with_session = reduce_account_event(
            {
                "desiredStarted": True,
                "loginState": "REAL_PROTOCOL_ONLINE",
                "sessionCredentialPresent": True,
            },
            EVENT_PROCESS_RECOVERED,
            now_millis=1_000,
        )
        without_session = reduce_account_event(
            {
                "desiredStarted": True,
                "loginState": "REAL_PROTOCOL_OFFLINE",
                "sessionCredentialPresent": False,
            },
            EVENT_PROCESS_RECOVERED,
            now_millis=1_000,
        )

        self.assertEqual(with_session["nextOperation"], "probe")
        self.assertEqual(without_session["nextOperation"], "login")
        self.assertFalse(with_session["liveSessionUsable"])
        self.assertFalse(without_session["liveSessionUsable"])

    def test_facade_json_api_is_deterministic_and_rejects_unknown_events(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        try:
            first = facade.account_transition_json(
                json.dumps(
                    {
                        "desiredStarted": True,
                        "loginState": "REAL_PROTOCOL_ONLINE",
                        "sessionCredentialPresent": True,
                    }
                ),
                EVENT_PROCESS_RECOVERED,
                "{}",
                1234,
            )
            second = facade.account_transition_json(
                json.dumps(
                    {
                        "desiredStarted": True,
                        "loginState": "REAL_PROTOCOL_ONLINE",
                        "sessionCredentialPresent": True,
                    }
                ),
                EVENT_PROCESS_RECOVERED,
                "{}",
                1234,
            )
            rejected = json.loads(
                facade.account_transition_json("{}", "INVENTED_EVENT")
            )

            self.assertEqual(first, second)
            self.assertFalse(rejected["ok"])
            self.assertEqual(
                rejected["error"]["code"],
                "ACCOUNT_TRANSITION_REJECTED",
            )
        finally:
            facade.close()

    def test_desktop_runtime_projection_applies_the_same_happy_path(self) -> None:
        account = {
            "sessionId": "desktop-offline",
            "started": False,
            "status": "stopped",
            "lastError": "",
        }
        started = SERVER.apply_shared_account_transition(
            account,
            EVENT_USER_START,
            now_millis_value=1_000,
            session_credential_present=False,
        )
        self.assertEqual(started["loginState"], "REAL_PROTOCOL_CHECKING")
        self.assertEqual(account["status"], "checking")
        self.assertTrue(account["started"])

        online = SERVER.apply_shared_account_transition(
            account,
            EVENT_LOGIN_SUCCEEDED,
            now_millis_value=2_000,
            session_credential_present=True,
        )
        self.assertEqual(online["loginState"], "REAL_PROTOCOL_ONLINE")
        self.assertEqual(account["status"], "online")

        stopped = SERVER.apply_shared_account_transition(
            account,
            EVENT_USER_STOP,
            now_millis_value=3_000,
            session_credential_present=True,
        )
        self.assertEqual(stopped["loginState"], "REAL_PROTOCOL_STOPPED")
        self.assertEqual(account["status"], "stopped")
        self.assertFalse(account["started"])


if __name__ == "__main__":
    unittest.main()
