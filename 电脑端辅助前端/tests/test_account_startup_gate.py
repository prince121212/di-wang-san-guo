import importlib.util
import pathlib
import threading
import time
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("desktop_server_startup_gate", ROOT / "server.py")
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SERVER)


class AccountStartupGateTests(unittest.TestCase):
    def test_same_platform_account_cannot_run_two_servers(self) -> None:
        target_id = "account-1012"
        running_id = "account-1013"
        SERVER.ACCOUNTS[target_id] = {
            "sessionId": target_id,
            "username": "1608601",
            "password": "secret",
            "platform": "热血三国联盟",
            "serverQuery": "双线1012区",
            "status": "stopped",
            "started": False,
        }
        SERVER.ACCOUNTS[running_id] = {
            "sessionId": running_id,
            "username": "1608601",
            "password": "secret",
            "platform": "热血三国联盟",
            "serverQuery": "双线1013区",
            "status": "online",
            "started": True,
        }
        SERVER.SESSIONS[running_id] = {"sessionId": running_id}
        try:
            with patch.object(
                SERVER, "clear_recent_game_requests",
            ), patch.object(
                SERVER, "cancel_account_reconnect",
            ):
                with self.assertRaisesRegex(
                    SERVER.AccountStartError, "跨区服同时登录",
                ):
                    SERVER.start_account(target_id)
        finally:
            SERVER.ACCOUNTS.pop(target_id, None)
            SERVER.ACCOUNTS.pop(running_id, None)
            SERVER.SESSIONS.pop(running_id, None)

    def test_waiting_task_continues_when_first_heartbeat_marks_account_online(self) -> None:
        session_id = "startup-account"
        task = {
            "taskId": "domestic-task",
            "sessionId": session_id,
            "stopEvent": threading.Event(),
            "logs": [],
        }
        SERVER.ACCOUNTS[session_id] = {
            "started": True,
            "status": "checking",
            "lastError": "",
        }
        SERVER.SESSIONS[session_id] = {"sessionId": session_id}

        def mark_online() -> None:
            time.sleep(0.03)
            with SERVER.ACCOUNT_LOCK:
                SERVER.ACCOUNTS[session_id]["status"] = "online"

        thread = threading.Thread(target=mark_online)
        thread.start()
        try:
            with patch.object(SERVER, "task_log"), patch.object(SERVER, "command_center_release"):
                self.assertTrue(
                    SERVER.wait_for_task_account_online(
                        task, session_id, "自动内政", timeout_sec=1, poll_sec=0.01,
                    )
                )
        finally:
            thread.join()
            SERVER.ACCOUNTS.pop(session_id, None)
            SERVER.SESSIONS.pop(session_id, None)


if __name__ == "__main__":
    unittest.main()
