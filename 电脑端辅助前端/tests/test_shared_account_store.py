from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHARED_PYTHON = ROOT / "shared_core" / "python"
if str(SHARED_PYTHON) not in sys.path:
    sys.path.insert(0, str(SHARED_PYTHON))

from dwpm_core.account.store import DurableAccountStore  # noqa: E402
from dwpm_core.facade import CoreFacade  # noqa: E402


def public_account(account_ref: str = "202") -> dict:
    return {
        "accountRef": account_ref,
        "id": int(account_ref),
        "username": "offline-user",
        "serverName": "测试区",
        "enabled": False,
        "loginState": "REAL_PROTOCOL_STOPPED",
        "gameAuthSignEvidence": "empty-signature-verified",
        "session": {
            "accountId": int(account_ref),
            "expiresAtMillis": None,
            "sourceMode": 1,
            "publicState": {
                "roleName": "离线角色",
                "level": "88",
                "serverKey": "qzone_352",
            },
        },
    }


class SharedAccountStoreTests(unittest.TestCase):
    def test_accounts_route_uses_shared_lifecycle_and_public_runtime_projection(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        try:
            facade.account_record_upsert(public_account())
            response = facade.dispatch(
                "GET",
                "/api/accounts",
                {
                    "runtimeByAccount": {
                        "202": {
                            "reconnect": {
                                "failures": 2,
                                "nextAttemptAtMillis": 61_000,
                                "reason": "network unavailable",
                                "failureKind": "network",
                            },
                            "accountHabits": {"config": {"autoStart": True}},
                            "session": {"role": {"roleName": "离线角色"}},
                            "recentGameRequests": [{"status": "success"}],
                            "dailyStats": {"brushYellowCount": 3},
                            "taskOverview": {
                                "taskStack": [{"key": "daily"}],
                                "notices": [{"key": "warning"}],
                            },
                        }
                    }
                },
                {
                    "executionOwnerActive": False,
                    "nowMillis": 1_000,
                },
            )

            self.assertEqual(response.status, 200)
            card = response.body["accounts"][0]
            self.assertEqual(card["sessionId"], "202")
            self.assertEqual(card["roleName"], None)
            self.assertEqual(card["level"], 88)
            self.assertEqual(card["status"], "stopped")
            self.assertFalse(card["started"])
            self.assertFalse(card["hasLiveSession"])
            self.assertIsNone(card["session"])
            self.assertEqual(card["reconnectState"], "countdown")
            self.assertEqual(card["reconnectRemainingSec"], 60)
            self.assertEqual(card["lastError"], "network unavailable")
            self.assertEqual(card["accountHabits"]["config"]["autoStart"], True)
            self.assertEqual(card["taskStack"][0]["key"], "daily")
            self.assertEqual(card["notices"][0]["key"], "warning")
        finally:
            facade.close()

    def test_accounts_route_does_not_publish_zero_as_a_retry_deadline(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        try:
            facade.account_record_upsert(public_account())
            response = facade.dispatch(
                "GET",
                "/api/accounts",
                {
                    "runtimeByAccount": {
                        "202": {
                            "reconnect": {"nextAttemptAtMillis": 0},
                        }
                    }
                },
                {"nowMillis": 1_000},
            )

            card = response.body["accounts"][0]
            self.assertIsNone(card["reconnectAt"])
            self.assertEqual(card["reconnectState"], "")
            self.assertEqual(card["reconnectRemainingSec"], 0)
        finally:
            facade.close()

    def test_round_trip_restart_and_atomic_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "accounts-v1.json"
            clock = iter((1000, 2000, 3000)).__next__
            store = DurableAccountStore(path, now_millis=clock)
            stored = store.upsert(public_account())

            self.assertEqual(stored["accountRef"], "202")
            self.assertEqual(store.snapshot()["count"], 1)
            self.assertTrue(path.is_file())
            self.assertFalse(path.with_name("accounts-v1.json.tmp").exists())

            restored = DurableAccountStore(path, now_millis=lambda: 4000)
            record = restored.get("202")
            self.assertIsNotNone(record)
            self.assertEqual(record["session"]["publicState"]["roleName"], "离线角色")
            self.assertTrue(restored.delete("202"))
            self.assertEqual(restored.snapshot()["count"], 0)

    def test_sensitive_fields_are_rejected_at_every_depth(self) -> None:
        sensitive = (
            ("password", "plaintext-password"),
            ("dm", "123456"),
            ("tokenCiphertext", "ciphertext-marker"),
            ("userId", "private-user-id"),
            ("sessionToken", "private-session"),
            ("gameAuthSign", "private-sign"),
        )
        for key, value in sensitive:
            record = public_account()
            record["session"]["publicState"][key] = value
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "sensitive field"):
                    DurableAccountStore().upsert(record)

    def test_presentation_projection_omits_large_runtime_evidence(self) -> None:
        record = public_account()
        record["session"]["publicState"].update(
            {
                "formationsJson": "x" * 1_000_000,
                "state8004PayloadHex": "aa" * 10_000,
                "generalsJson": "[{\"id\":1}]",
                "militarySnapshotJson": "{\"actions\":[]}",
            }
        )
        store = DurableAccountStore(now_millis=lambda: 1000)
        store.upsert(record)

        full = store.get("202")
        presentation = store.get_presentation("202")
        self.assertEqual(
            full["session"]["publicState"]["formationsJson"],
            "x" * 1_000_000,
        )
        visible = presentation["session"]["publicState"]
        self.assertNotIn("formationsJson", visible)
        self.assertNotIn("state8004PayloadHex", visible)
        self.assertEqual(visible["generalsJson"], "[{\"id\":1}]")
        self.assertEqual(visible["militarySnapshotJson"], "{\"actions\":[]}")

    def test_import_if_empty_never_overwrites_existing_state(self) -> None:
        store = DurableAccountStore(now_millis=lambda: 1000)
        first = store.import_if_empty([public_account("202")])
        second = store.import_if_empty([public_account("303")])

        self.assertTrue(first["imported"])
        self.assertFalse(second["imported"])
        self.assertIsNotNone(store.get("202"))
        self.assertIsNone(store.get("303"))

    def test_concurrent_accounts_do_not_lose_updates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = DurableAccountStore(
                Path(temporary) / "accounts-v1.json",
                now_millis=lambda: 1000,
            )
            threads = [
                threading.Thread(
                    target=store.upsert,
                    args=(public_account(str(200 + index)),),
                )
                for index in range(8)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(store.snapshot()["count"], 8)

    def test_facade_json_api_never_persists_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            account_path = root / "accounts-v1.json"
            facade = CoreFacade(
                ROOT / "shared_core",
                str(root / "operations-v2.json"),
                account_store_path=str(account_path),
            )
            try:
                accepted = json.loads(
                    facade.account_record_upsert_json(
                        json.dumps(public_account(), ensure_ascii=False)
                    )
                )
                rejected_record = public_account("303")
                rejected_record["session"]["publicState"]["dm"] = "9988"
                rejected = json.loads(
                    facade.account_record_upsert_json(
                        json.dumps(rejected_record, ensure_ascii=False)
                    )
                )

                self.assertTrue(accepted["ok"])
                self.assertFalse(rejected["ok"])
                raw = account_path.read_text(encoding="utf-8")
                self.assertNotIn("plaintext-password", raw)
                self.assertNotIn('"dm"', raw)
                self.assertNotIn("tokenCiphertext", raw)
                self.assertEqual(facade.account_records_snapshot()["count"], 1)
            finally:
                facade.close()


if __name__ == "__main__":
    unittest.main()
