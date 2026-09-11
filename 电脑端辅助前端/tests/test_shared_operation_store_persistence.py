from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core.operations import DurableOperationStore, QUERY, SUCCEEDED


class SharedOperationStorePersistenceTests(unittest.TestCase):
    def test_recovered_operation_waits_for_host_gate_and_resumes_same_id(self) -> None:
        """A process hand-over must defer, not fail or duplicate, a pending lane."""

        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "operations-v2.json"
            ledger.write_text(
                json.dumps({
                    "schemaVersion": 2,
                    "operations": [{
                        "operationId": "op_recovery_gate",
                        "kind": "fixture-query",
                        "operationType": QUERY,
                        "accountRef": "account-1",
                        "idempotencyKey": "recovery-gate-1",
                        "status": "RUNNING",
                        "submittedAtMillis": 1,
                        "startedAtMillis": 2,
                        "updatedAtMillis": 3,
                        "completedAtMillis": None,
                        "payload": {"value": 7},
                        "progress": 42,
                        "progressDetails": {"phase": "read-only-scan"},
                        "requestSent": False,
                        "requestSentAtMillis": None,
                        "requestMetadata": None,
                        "cancelRequested": False,
                        "result": None,
                        "error": None,
                    }],
                }),
                encoding="utf-8",
            )
            ready = False
            calls: list[str] = []
            store = DurableOperationStore(ledger)
            try:
                store.register_runner(
                    "fixture-query",
                    lambda _execution, payload: calls.append(str(payload["value"]))
                    or {"ok": True},
                    runnable_when=lambda: ready,
                )

                time.sleep(0.08)
                pending = store.status("op_recovery_gate")
                self.assertIsNotNone(pending)
                self.assertEqual(pending["status"], "QUEUED")
                self.assertTrue(pending["recoveryPending"])
                self.assertEqual(calls, [])

                ready = True
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    completed = store.status("op_recovery_gate")
                    if completed and completed["status"] == SUCCEEDED:
                        break
                    time.sleep(0.01)
                else:
                    self.fail("recovered operation did not resume")

                completed = store.status("op_recovery_gate")
                self.assertEqual(completed["operationId"], "op_recovery_gate")
                self.assertEqual(calls, ["7"])
                records = json.loads(ledger.read_text(encoding="utf-8"))["operations"]
                self.assertEqual(
                    [row["idempotencyKey"] for row in records],
                    ["recovery-gate-1"],
                )
            finally:
                store.close()

    def test_result_facts_filter_and_copy_only_requested_fields(self) -> None:
        store = DurableOperationStore()
        try:
            store.register_runner(
                "fixture-query",
                lambda _execution, _payload: {
                    "feature": "brush",
                    "dispatchAccepted": True,
                    "battleId": 701,
                    "target": {"name": "8级山贼"},
                    "catalog": {"large": ["unused"] * 1_000},
                },
            )
            submitted = store.submit_network(
                account_ref="account-1",
                operation_type=QUERY,
                kind="fixture-query",
                idempotency_key="request-1",
            )
            for _ in range(200):
                operation = store.status(submitted["operationId"])
                if operation and operation["status"] == SUCCEEDED:
                    break
                time.sleep(0.005)
            else:
                self.fail("fixture operation did not complete")

            facts = store.list_result_facts(
                "account-1",
                result_keys=["feature", "battleId", "target"],
                required_truthy_key="dispatchAccepted",
            )
            self.assertEqual(len(facts), 1)
            self.assertEqual(
                facts[0]["result"],
                {
                    "feature": "brush",
                    "battleId": 701,
                    "target": {"name": "8级山贼"},
                },
            )
        finally:
            store.close()

    def test_concurrent_stores_use_distinct_atomic_staging_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "operations-v2.json"
            stores = [DurableOperationStore(ledger), DurableOperationStore(ledger)]
            barrier = threading.Barrier(2)
            staging_paths: list[Path] = []
            failures: list[BaseException] = []
            original_replace = Path.replace

            def synchronized_replace(source: Path, target: Path) -> Path:
                staging_paths.append(source)
                barrier.wait(timeout=5)
                return original_replace(source, target)

            def submit(store: DurableOperationStore, suffix: str) -> None:
                try:
                    store.submit_network(
                        account_ref=f"account-{suffix}",
                        operation_type=QUERY,
                        kind="fixture-query",
                        idempotency_key=f"request-{suffix}",
                    )
                except BaseException as error:  # captured for the test thread
                    failures.append(error)

            try:
                with mock.patch.object(Path, "replace", synchronized_replace):
                    threads = [
                        threading.Thread(target=submit, args=(store, str(index)))
                        for index, store in enumerate(stores)
                    ]
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join(timeout=10)

                self.assertTrue(all(not thread.is_alive() for thread in threads))
                self.assertEqual(failures, [])
                self.assertEqual(len(staging_paths), 2)
                self.assertEqual(len(set(staging_paths)), 2)
                payload = json.loads(ledger.read_text(encoding="utf-8"))
                self.assertEqual(payload["schemaVersion"], 2)
                self.assertEqual(len(payload["operations"]), 1)
                self.assertEqual(list(ledger.parent.glob(f"{ledger.name}.tmp.*")), [])
            finally:
                for store in stores:
                    store.close()

    def test_failed_replace_removes_only_its_staging_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "operations-v2.json"
            store = DurableOperationStore(ledger)
            try:
                with mock.patch.object(Path, "replace", side_effect=OSError("fixture")):
                    with self.assertRaisesRegex(OSError, "fixture"):
                        store.submit_network(
                            account_ref="account-1",
                            operation_type=QUERY,
                            kind="fixture-query",
                            idempotency_key="request-1",
                        )
                self.assertEqual(list(ledger.parent.glob(f"{ledger.name}.tmp.*")), [])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
