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

from desktop_adapter.shared_core_ports import (
    DesktopCloudSharedDataPort,
    DesktopRawHttpPort,
    create_desktop_platform_ports,
)
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
        self.cloud_requests = []

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

    def cloudSharedDataConfigured(self) -> bool:
        return True

    def executeCloudRequest(self, payload: str) -> str:
        request = json.loads(payload)
        self.cloud_requests.append(request)
        return json.dumps({
            "status": 200,
            "body": {"ok": True, "mode": "LOCAL_ONLY"},
        })


class SharedCorePlatformPortTests(unittest.TestCase):
    def test_desktop_authenticated_raw_http_uses_account_game_callback(self) -> None:
        observed = []

        def exchange(request):
            observed.append(dict(request))
            return {"status": 200, "body": b"game", "headers": {}}

        port = DesktopRawHttpPort(exchange)
        result = port.exchange({
            "method": "POST",
            "url": "http://game.test/kingWapServer/HttpClient",
            "body": b"packet",
            "accountRef": "176",
            "requireExecutionOwner": True,
        })

        self.assertEqual(result["status"], 200)
        self.assertEqual(result["body"], b"game")
        self.assertEqual(observed[0]["accountRef"], "176")

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
            cloud_result = ports.cloud_shared_data.exchange({
                "method": "POST",
                "path": "/v1/presence/heartbeat",
                "body": {"actorId": "a" * 64},
            })
            directory_result = ports.cloud_shared_data.exchange({
                "method": "POST",
                "path": "/v1/servers/directory/sync",
                "body": {
                    "platformKey": "sglm",
                    "areas": [{
                        "serverKey": "qzone_352",
                        "areaName": "周年服352区",
                    }],
                },
            })

            self.assertEqual(bridge.notifications[0]["message"], "通知")
            self.assertEqual(bridge.wakes, [("7", 1234), ("7", None)])
            self.assertEqual(bridge.logs[0]["message"], "日志")
            self.assertEqual(bridge.events[0]["type"], "event")
            self.assertTrue(ports.cloud_shared_data.configured())
            self.assertEqual(cloud_result["body"]["mode"], "LOCAL_ONLY")
            self.assertEqual(directory_result["status"], 200)
            self.assertEqual(
                bridge.cloud_requests[0]["path"],
                "/v1/presence/heartbeat",
            )
            self.assertEqual(
                bridge.cloud_requests[1]["path"],
                "/v1/servers/directory/sync",
            )

    def test_desktop_cloud_port_is_disabled_without_runtime_configuration(self) -> None:
        self.assertFalse(DesktopCloudSharedDataPort("", "").configured())
        self.assertFalse(
            DesktopCloudSharedDataPort(
                "http://public.example", "runtime-token"
            ).configured()
        )
        self.assertTrue(
            DesktopCloudSharedDataPort(
                "https://shared.example", "runtime-token"
            ).configured()
        )
        self.assertTrue(
            DesktopCloudSharedDataPort(
                "http://127.0.0.1:8787", "runtime-token"
            ).configured()
        )

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
