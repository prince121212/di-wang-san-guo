from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core.operations import (  # noqa: E402
    MAX_RETAINED_CLOSED_OPERATIONS,
    MAX_RETAINED_RESULT_FIELD_BYTES,
    UNCOMPACTED_CLOSED_OPERATIONS,
    PRUNABLE_STATES,
    SUCCEEDED,
    TERMINAL_STATES,
    UNCERTAIN,
    DurableOperationStore,
)


class OperationRetentionTests(unittest.TestCase):
    """The ledger must not grow without bound.

    It had no retention at all.  A resident tick creates one durable operation
    every few seconds and every one was kept forever, so a real device reached
    11,744 records in a 52 MB file - 11,610 of them completed scheduler ticks.
    The whole file is re-serialised and rewritten on every state transition, so
    that became tens of megabytes of JSON encoding and flash writes per tick and
    about 400 MB of native heap.  MIUI killed the process with
    ``ScreenOffCPUCheckKill`` and both accounts lost seven hours overnight.
    """

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "operations.json"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _store(self) -> DurableOperationStore:
        return DurableOperationStore(self.path)

    def _seed(self, store, count: int, status: str, *, first_id: int = 0):
        for index in range(count):
            operation_id = f"op-{status}-{first_id + index}"
            store._records[operation_id] = {  # noqa: SLF001
                "operationId": operation_id,
                "status": status,
                "updatedAtMillis": first_id + index,
                "kind": "automation:recovery-tick:v1",
            }

    def test_closed_operations_are_capped(self) -> None:
        store = self._store()
        try:
            self._seed(store, MAX_RETAINED_CLOSED_OPERATIONS + 500, SUCCEEDED)
            store._persist_locked()  # noqa: SLF001

            self.assertEqual(
                len(store._records),  # noqa: SLF001
                MAX_RETAINED_CLOSED_OPERATIONS,
            )
        finally:
            store.close()

    def test_the_newest_closed_operations_are_the_ones_kept(self) -> None:
        store = self._store()
        try:
            self._seed(store, MAX_RETAINED_CLOSED_OPERATIONS + 10, SUCCEEDED)
            store._persist_locked()  # noqa: SLF001

            kept = sorted(
                int(record["updatedAtMillis"])
                for record in store._records.values()  # noqa: SLF001
            )
            self.assertEqual(kept[0], 10)
            self.assertEqual(kept[-1], MAX_RETAINED_CLOSED_OPERATIONS + 9)
        finally:
            store.close()

    def test_an_unresolved_send_boundary_is_never_pruned(self) -> None:
        """UNCERTAIN is the one thing the ledger exists to remember."""

        store = self._store()
        try:
            self._seed(store, MAX_RETAINED_CLOSED_OPERATIONS + 500, SUCCEEDED)
            store._records["op-uncertain"] = {  # noqa: SLF001
                "operationId": "op-uncertain",
                "status": UNCERTAIN,
                "updatedAtMillis": 0,
                "requestSent": True,
            }
            store._persist_locked()  # noqa: SLF001

            self.assertIn("op-uncertain", store._records)  # noqa: SLF001
        finally:
            store.close()

    def test_open_operations_are_never_pruned(self) -> None:
        store = self._store()
        try:
            self._seed(store, MAX_RETAINED_CLOSED_OPERATIONS + 500, SUCCEEDED)
            for status in ("QUEUED", "RUNNING", "FAILED"):
                store._records[f"op-{status}"] = {  # noqa: SLF001
                    "operationId": f"op-{status}",
                    "status": status,
                    "updatedAtMillis": 0,
                }
            store._persist_locked()  # noqa: SLF001

            for status in ("QUEUED", "RUNNING", "FAILED"):
                self.assertIn(f"op-{status}", store._records)  # noqa: SLF001
        finally:
            store.close()

    def test_only_definitively_closed_states_are_prunable(self) -> None:
        self.assertTrue(PRUNABLE_STATES < TERMINAL_STATES)
        self.assertNotIn(UNCERTAIN, PRUNABLE_STATES)

    def test_the_persisted_file_stays_small(self) -> None:
        """52 MB rewritten per tick is what the vendor killed us for."""

        store = self._store()
        try:
            self._seed(store, 12_000, SUCCEEDED)
            store._persist_locked()  # noqa: SLF001
        finally:
            store.close()

        self.assertLess(self.path.stat().st_size, 1_000_000)
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(
            len(stored["operations"]), MAX_RETAINED_CLOSED_OPERATIONS
        )


class ResultCompactionTests(unittest.TestCase):
    """``result`` was 96% of the ledger; one closed tick carried 109 KB.

    Those were the working notes of how an outcome was computed - raw
    per-coordinate scan output - which nothing reads once the outcome exists.
    """

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "operations.json"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _record(self, index: int, *, status: str = SUCCEEDED):
        return {
            "operationId": f"op-{index}",
            "status": status,
            "updatedAtMillis": index,
            "result": {
                "feature": "brush",
                "state": "no-targets",
                "successRecord": {"category": "刷黄"},
                "scanResults": ["x" * 200 for _ in range(200)],
            },
        }

    def _store_with(self, count: int):
        store = DurableOperationStore(self.path)
        for index in range(count):
            store._records[f"op-{index}"] = self._record(index)  # noqa: SLF001
        return store

    def test_an_aged_result_loses_only_its_oversized_fields(self) -> None:
        store = self._store_with(UNCOMPACTED_CLOSED_OPERATIONS + 5)
        try:
            store._persist_locked()  # noqa: SLF001
            oldest = store._records["op-0"]["result"]  # noqa: SLF001

            self.assertNotIn("scanResults", oldest)
            # Everything a consumer reads is far under the bound and survives.
            self.assertEqual(oldest["feature"], "brush")
            self.assertEqual(oldest["state"], "no-targets")
            self.assertEqual(oldest["successRecord"], {"category": "刷黄"})
            # What went is recorded, not silently removed.
            self.assertIn(
                "scanResults",
                store._records["op-0"]["resultDroppedFieldBytes"],  # noqa: SLF001
            )
        finally:
            store.close()

    def test_a_just_closed_result_is_left_whole(self) -> None:
        """Compacting at close time is too early - the caller reads it next.

        The desktop 副本 and 无损 ticks failed with "未返回业务结果" the first
        time this ran without a read window.
        """

        store = self._store_with(UNCOMPACTED_CLOSED_OPERATIONS + 5)
        try:
            store._persist_locked()  # noqa: SLF001
            newest = store._records[  # noqa: SLF001
                f"op-{UNCOMPACTED_CLOSED_OPERATIONS + 4}"
            ]["result"]

            self.assertIn("scanResults", newest)
        finally:
            store.close()

    def test_an_unresolved_operation_keeps_everything(self) -> None:
        store = DurableOperationStore(self.path)
        try:
            for index in range(UNCOMPACTED_CLOSED_OPERATIONS + 5):
                store._records[f"op-{index}"] = self._record(index)  # noqa: SLF001
            store._records["op-0"]["status"] = UNCERTAIN  # noqa: SLF001
            store._persist_locked()  # noqa: SLF001

            self.assertIn(
                "scanResults",
                store._records["op-0"]["result"],  # noqa: SLF001
            )
        finally:
            store.close()

    def test_compaction_never_repeats_work(self) -> None:
        store = self._store_with(UNCOMPACTED_CLOSED_OPERATIONS + 5)
        try:
            store._persist_locked()  # noqa: SLF001
            store._records["op-0"]["result"]["late"] = "y" * 99_999  # noqa: SLF001
            store._persist_locked()  # noqa: SLF001

            # Already compacted once; a later addition is not re-scanned.
            self.assertIn("late", store._records["op-0"]["result"])  # noqa: SLF001
        finally:
            store.close()

    def test_the_bound_clears_every_field_a_consumer_reads(self) -> None:
        """Measured on the device: the largest was successRecord at 550 bytes."""

        self.assertGreaterEqual(MAX_RETAINED_RESULT_FIELD_BYTES, 550 * 4)


class ResidentResultHandoverTests(unittest.TestCase):
    """Closing an operation is not proof that its Android consumer read it."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "operations.json"
        self.store = self._open()

    def _open(self):
        store = DurableOperationStore(self.path)
        # Deliberately drive the lane transitions below. No network or timing
        # race is needed to exercise submit/dedup/ack/persist/prune.
        store._ensure_lane_locked = lambda _account: None
        return store

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def _submit(self, account="176", key="tick", *, consumer=None, coalesce=False):
        return self.store.submit_network(
            account_ref=account, operation_type="query",
            kind="automation:recovery-tick:v1", idempotency_key=key,
            payload={"accountRef": account}, coalesce_active=coalesce,
            result_retention_key=consumer or f"android-resident:{account}",
        )["operationId"]

    def _finish(self, operation_id, *, status=SUCCEEDED):
        with self.store._condition:
            self.store._records[operation_id].update(
                status=status, updatedAtMillis=1,
                result={"feature": "dungeon", "state": "fighting", "large": "x" * 20_000},
            )
            self.store._persist_locked()

    def _flood_other_account(self):
        with self.store._condition:
            for index in range(MAX_RETAINED_CLOSED_OPERATIONS + 50):
                self.store._records[f"flood-{index}"] = {
                    "operationId": f"flood-{index}", "accountRef": "202",
                    "status": SUCCEEDED, "updatedAtMillis": 100 + index,
                }
            self.store._persist_locked()

    def test_unconsumed_result_survives_other_account_flood_and_process_restart(self):
        operation_id = self._submit()
        self._finish(operation_id)
        self._flood_other_account()
        self.assertIn("large", self.store.status(operation_id)["result"])
        self.store.close()
        self.store = self._open()
        self.assertTrue(self.store.status(operation_id)["resultRetained"])
        self.assertIn("large", self.store.status(operation_id)["result"])
        self.assertEqual(len(self.store.list_operations()), MAX_RETAINED_CLOSED_OPERATIONS + 1)

    def test_only_correct_consumer_can_acknowledge_a_terminal_result(self):
        operation_id = self._submit()
        self.assertFalse(self.store.acknowledge_result(
            operation_id, account_ref="176", retention_key="android-resident:176",
        ))
        self._finish(operation_id)
        for account, consumer in (("202", "android-resident:176"), ("176", "other")):
            self.assertFalse(self.store.acknowledge_result(
                operation_id, account_ref=account, retention_key=consumer,
            ))
            self.assertTrue(self.store.status(operation_id)["resultRetained"])
        for _ in range(2):
            self.assertTrue(self.store.acknowledge_result(
                operation_id, account_ref="176", retention_key="android-resident:176",
            ))
        self.assertFalse(self.store.status(operation_id)["resultRetained"])
        self._flood_other_account()
        self.assertIsNone(self.store.status(operation_id))

    def test_acknowledgement_never_removes_unknown_send_evidence(self):
        operation_id = self._submit()
        self._finish(operation_id, status=UNCERTAIN)
        self.assertTrue(self.store.acknowledge_result(
            operation_id, account_ref="176", retention_key="android-resident:176",
        ))
        self._flood_other_account()
        self.assertEqual(self.store.status(operation_id)["status"], UNCERTAIN)
        self.assertIn("large", self.store.status(operation_id)["result"])

    def test_submission_after_lost_ack_releases_only_same_consumer_old_result(self):
        old = self._submit()
        other = self._submit("202", "other")
        self._finish(old)
        self._finish(other)
        new = self._submit("176", "new-tick")
        self.assertFalse(self.store.status(old)["resultRetained"])
        self.assertTrue(self.store.status(new)["resultRetained"])
        self.assertTrue(self.store.status(other)["resultRetained"])

    def test_response_loss_deduplicates_and_keeps_result_pinned(self):
        first = self._submit()
        self._finish(first)
        self.assertEqual(self._submit(), first)
        self.assertTrue(self.store.status(first)["resultRetained"])
        self._flood_other_account()
        self.assertIsNotNone(self.store.status(first))

    def test_coalesced_active_result_is_pinned_and_cannot_change_owner(self):
        first = self._submit(coalesce=True)
        self.assertEqual(self._submit(key="another-key", coalesce=True), first)
        with self.assertRaises(ValueError):
            self._submit(consumer="different-consumer")
        self.assertTrue(self.store.status(first)["resultRetained"])

    def test_lost_acks_cannot_accumulate_unbounded_pins(self):
        for index in range(30):
            operation_id = self._submit(key=f"tick-{index}")
            self._finish(operation_id)
        retained = [r for r in self.store.list_operations() if r.get("resultRetained")]
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0]["operationId"], operation_id)


if __name__ == "__main__":
    unittest.main()
