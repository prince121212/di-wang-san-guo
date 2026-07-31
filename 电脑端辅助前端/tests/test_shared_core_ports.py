from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = ROOT / "shared_core" / "python"
DESKTOP_SOURCE = ROOT / "电脑端辅助前端"
for source in (CORE_SOURCE, DESKTOP_SOURCE):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from desktop_adapter.shared_core_ports import create_desktop_platform_ports
from dwpm_core import CoreFacade, create_hosted_core
from dwpm_core.host_ports import platform_ports_from_host_bridge


class FakeHostedBridge:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.deleted = []
        self.passwords = {}
        self.session_secrets = {}
        self.events = []
        self.logs = []
        self.notifications = []
        self.wakes = []

    def savePassword(self, account_ref: str, password: str) -> None:
        self.passwords[account_ref] = password

    def loadPassword(self, account_ref: str):
        return self.passwords.get(account_ref) or (
            "keystore-only" if account_ref == "7" else None
        )

    def deleteCredential(self, account_ref: str) -> None:
        self.deleted.append(account_ref)

    def saveSessionSecrets(self, account_ref: str, payload: str) -> None:
        self.session_secrets[account_ref] = json.loads(payload)

    def loadSessionSecrets(self, account_ref: str) -> str:
        return json.dumps(self.session_secrets.get(account_ref, {}))

    def deleteSessionSecrets(self, account_ref: str) -> None:
        self.session_secrets.pop(account_ref, None)

    def dataDirectory(self) -> str:
        return str(self.directory)

    def networkAvailable(self) -> bool:
        return True

    def notifyEvent(self, payload: str) -> None:
        self.notifications.append(json.loads(payload))

    def scheduleWake(self, account_ref: str, wake_at_millis: int) -> None:
        self.wakes.append((account_ref, wake_at_millis))

    def cancelWake(self, account_ref: str) -> None:
        self.wakes.append((account_ref, None))

    def writeLog(self, payload: str) -> None:
        self.logs.append(json.loads(payload))

    def publishEvent(self, payload: str) -> None:
        self.events.append(json.loads(payload))


class SharedCorePlatformPortTests(unittest.TestCase):
    def test_host_bridge_exposes_capabilities_without_business_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bridge = FakeHostedBridge(Path(directory))
            ports = platform_ports_from_host_bridge(bridge)

            ports.credentials.save_password("9", "memory-only-password")
            self.assertEqual(
                ports.credentials.load_password("9"),
                "memory-only-password",
            )
            self.assertEqual(ports.credentials.load_password("7"), "keystore-only")
            self.assertIsNone(ports.credentials.load_password("8"))
            ports.credentials.delete("7")
            self.assertEqual(bridge.deleted, ["7"])
            ports.session_secrets.save(
                "7",
                {"dm": "123", "sessionToken": "temporary"},
            )
            self.assertEqual(
                ports.session_secrets.load("7"),
                {"dm": "123", "sessionToken": "temporary"},
            )
            ports.session_secrets.delete("7")
            self.assertEqual(ports.session_secrets.load("7"), {})
            self.assertEqual(ports.data_directory.data_directory(), Path(directory))
            self.assertTrue(ports.network_state.is_available())
            ports.notifications.notify({"message": "通知"})
            ports.wake.schedule("7", 1234)
            ports.wake.cancel("7")
            ports.logs.write({"message": "日志"})
            ports.events.publish({"type": "event"})

            self.assertEqual(bridge.notifications[0]["message"], "通知")
            self.assertEqual(bridge.wakes, [("7", 1234), ("7", None)])
            self.assertEqual(bridge.logs[0]["message"], "日志")
            self.assertEqual(bridge.events[0]["type"], "event")

    def test_hosted_core_publishes_operation_events_through_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bridge = FakeHostedBridge(root)
            facade = create_hosted_core(
                str(root / "operations.json"),
                bridge,
            )
            facade.register_network_route(
                "GET",
                "/api/state/refresh",
                lambda body, context, execution: {"ok": True},
            )
            accepted = facade.dispatch(
                "GET",
                "/api/state/refresh",
                {"accountRef": "7"},
                {"requestId": "host-port-event-1"},
            )
            operation_id = accepted.body["operationId"]
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                operation = facade.operation_status(operation_id)["operation"]
                if operation["status"] == "SUCCEEDED":
                    break
                time.sleep(0.01)
            else:
                self.fail("hosted operation did not complete")

            event_types = {event["type"] for event in bridge.events}
            self.assertIn("operation.accepted", event_types)
            self.assertIn("operation.completed", event_types)
            self.assertTrue(bridge.logs)
            facade.close()

    def test_desktop_ports_use_host_files_not_core_business_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ports = create_desktop_platform_ports(root)
            ports.events.publish({"type": "operation.completed", "status": "SUCCEEDED"})
            ports.logs.write({"level": "info", "message": "测试"})

            event_file = root / "shared_core" / "events.jsonl"
            log_file = root / "shared_core" / "core.jsonl"
            self.assertEqual(
                json.loads(event_file.read_text(encoding="utf-8"))["status"],
                "SUCCEEDED",
            )
            self.assertEqual(
                json.loads(log_file.read_text(encoding="utf-8"))["message"],
                "测试",
            )

            facade = CoreFacade(ROOT / "shared_core", ports=ports)
            self.assertEqual(facade.dispatch("GET", "/api/health").status, 200)
            facade.close()


if __name__ == "__main__":
    unittest.main()
