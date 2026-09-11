from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHARED_PYTHON = ROOT / "shared_core" / "python"
if str(SHARED_PYTHON) not in sys.path:
    sys.path.insert(0, str(SHARED_PYTHON))

from dwpm_core import create_hosted_core  # noqa: E402
from dwpm_core.facade import CoreFacade  # noqa: E402


class AccountLifecycleHost:
    def __init__(self, data_directory: str) -> None:
        self.root = data_directory
        self.calls: list[dict] = []
        self.locked = False

    def dataDirectory(self) -> str:
        return self.root

    def executeNetworkOperation(
        self,
        method: str,
        path: str,
        body_json: str,
        context_json: str,
    ) -> str:
        body = json.loads(body_json)
        self.calls.append({"method": method, "path": path, "body": body})
        return json.dumps({
            "status": 200,
            "body": {
                "ok": True,
                "accountLifecycleFact": {
                    "accountRef": "9988",
                    "replacedAccountRef": body["accountRef"],
                    "status": "stopped" if path.endswith("/add") else "online",
                    "message": "host login complete",
                },
            },
        })

    def executionOwnerActive(self) -> bool:
        return False

    def tryAcquireNetworkOperation(self, account_ref: str) -> bool:
        if self.locked:
            return False
        self.locked = True
        return True

    def releaseNetworkOperation(self, account_ref: str) -> None:
        self.locked = False

    def savePassword(self, account_ref: str, password: str) -> None:
        return None

    def loadPassword(self, account_ref: str):
        return None

    def deleteCredential(self, account_ref: str) -> None:
        return None

    def saveSessionSecrets(self, account_ref: str, values_json: str) -> None:
        return None

    def loadSessionSecrets(self, account_ref: str) -> str:
        return "{}"

    def deleteSessionSecrets(self, account_ref: str) -> None:
        return None

    def networkAvailable(self) -> bool:
        return True

    def notifyEvent(self, event_json: str) -> None:
        return None

    def scheduleWake(self, account_ref: str, wake_at_millis: int) -> None:
        return None

    def cancelWake(self, account_ref: str) -> None:
        return None

    def writeLog(self, event_json: str) -> None:
        return None

    def publishEvent(self, event_json: str) -> None:
        return None


class SharedAccountLifecycleOperationTests(unittest.TestCase):
    def test_public_account_projection_derives_only_compact_local_daily_counts(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        try:
            facade.account_record_upsert({
                "accountRef": "176",
                "id": 176,
                "username": "1608600",
                "serverName": "周年服352区",
                "session": {
                    "accountId": 176,
                    "sourceMode": 1,
                    "publicState": {
                        "residentAutomationConfigJson": json.dumps({
                            "schemaVersion": 2,
                        }),
                        "residentAutomationStateJson": json.dumps({
                            "updatedAtMillis": 123456,
                            "brush": {
                                "dayKey": 20678,
                                "usedCount": 8,
                                "largeDiagnostic": "x" * 10000,
                            },
                            "dungeon": {
                                "dayKey": 20678,
                                "usedCount": 3,
                            },
                            "inventory": {
                                "largeReceipt": "y" * 10000,
                            },
                        }),
                    },
                },
                "enabled": True,
            })

            projected = json.loads(
                facade.account_record_presentation_json("176")
            )["account"]
            public = projected["session"]["publicState"]
            counts = json.loads(public["residentDailyCountsJson"])
            self.assertEqual(counts["brush"], {
                "dayKey": 20678,
                "usedCount": 8,
            })
            self.assertEqual(counts["dungeon"], {
                "dayKey": 20678,
                "usedCount": 3,
            })
            self.assertEqual(counts["updatedAtMillis"], 123456)
            self.assertNotIn("residentAutomationStateJson", public)
            self.assertNotIn("largeDiagnostic", json.dumps(projected))
            self.assertLess(len(json.dumps(projected)), 2000)
        finally:
            facade.close()

    def test_add_prepare_is_deterministic_and_never_returns_password(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        try:
            request = {
                "username": "1608600",
                "serverQuery": "352区",
                "platform": "三国联盟",
                "serial": "7",
                "passwordPresent": True,
                "supportedPlatformKeys": ["sglm"],
            }
            first = facade.account_add_prepare(request)
            second = facade.account_add_prepare(request)
            self.assertEqual(
                first["plan"]["record"]["accountRef"],
                second["plan"]["record"]["accountRef"],
            )
            self.assertGreater(int(first["plan"]["record"]["accountRef"]), 0)
            self.assertFalse(first["plan"]["networkRequired"])
            self.assertNotIn("password", json.dumps(first).lower())
            self.assertEqual(first["plan"]["record"]["platformKey"], "sglm")
        finally:
            facade.close()

    def test_add_prepare_rejects_missing_password_and_unsupported_host_platform(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        try:
            with self.assertRaisesRegex(ValueError, "密码"):
                facade.account_add_prepare({
                    "username": "u",
                    "serverQuery": "1区",
                    "platform": "sglm",
                    "passwordPresent": False,
                })
            with self.assertRaisesRegex(ValueError, "尚未开放"):
                facade.account_add_prepare({
                    "username": "u",
                    "serverQuery": "1区",
                    "platform": "downjoy",
                    "passwordPresent": True,
                    "supportedPlatformKeys": ["sglm"],
                })
        finally:
            facade.close()

    def test_android_supported_platforms_keep_same_user_and_zone_distinct(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        try:
            common = {
                "username": "1608600",
                "serverQuery": "352区",
                "passwordPresent": True,
                "supportedPlatformKeys": ["sglm", "downjoy"],
            }
            alliance = facade.account_add_prepare({
                **common,
                "platform": "热血三国联盟",
            })["plan"]["record"]
            downjoy = facade.account_add_prepare({
                **common,
                "platform": "当乐帝王三国",
            })["plan"]["record"]

            self.assertNotEqual(alliance["accountRef"], downjoy["accountRef"])
            self.assertEqual(alliance["platformKey"], "sglm")
            self.assertEqual(alliance["channel"], "QQ")
            self.assertEqual(downjoy["platformKey"], "downjoy")
            self.assertEqual(downjoy["channel"], "DANGLE")
        finally:
            facade.close()

    def test_legacy_account_without_platform_is_not_reused_for_downjoy(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        try:
            facade.account_record_upsert({
                "accountRef": "123456",
                "id": 123456,
                "username": "1608600",
                "serverName": "352区",
                "enabled": False,
            })
            prepared = facade.account_add_prepare({
                "username": "1608600",
                "serverQuery": "352区",
                "platform": "downjoy",
                "passwordPresent": True,
                "supportedPlatformKeys": ["sglm", "downjoy"],
            })

            self.assertFalse(prepared["plan"]["existingAccount"])
            self.assertNotEqual(
                prepared["plan"]["record"]["accountRef"],
                "123456",
            )
        finally:
            facade.close()

    def test_hosted_add_and_start_do_not_require_an_active_execution_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            host = AccountLifecycleHost(directory)
            facade = create_hosted_core(
                str(Path(directory) / "operations.json"),
                host,
            )
            try:
                for path, request_id, expected_status in (
                    ("/api/accounts/add", "add-1", "stopped"),
                    ("/api/accounts/start", "start-1", "online"),
                ):
                    accepted = facade.dispatch(
                        "POST",
                        path,
                        {"accountRef": "1234"},
                        {"requestId": request_id, "platform": "test"},
                    )
                    self.assertEqual(accepted.status, 202)
                    operation_id = accepted.body["operationId"]
                    deadline = time.time() + 2
                    operation = None
                    while time.time() < deadline:
                        operation = facade.operation_status(operation_id)["operation"]
                        if operation["status"] in {"SUCCEEDED", "FAILED", "UNCERTAIN"}:
                            break
                        time.sleep(0.01)
                    self.assertEqual(operation["status"], "SUCCEEDED")
                    self.assertEqual(operation["result"]["status"], expected_status)
                    self.assertEqual(operation["payload"]["body"], {
                        "accountRef": "1234",
                        "mode": "add" if path.endswith("/add") else "start",
                    })
                self.assertEqual([call["path"] for call in host.calls], [
                    "/api/accounts/add",
                    "/api/accounts/start",
                ])
            finally:
                facade.close()


if __name__ == "__main__":
    unittest.main()
