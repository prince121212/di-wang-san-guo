from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core.operations import DurableOperationStore, QUERY, SUCCEEDED


class SharedOperationAwaitStatusTests(unittest.TestCase):
    """`await_status` exists so a battery-constrained host can stop polling.

    The Android foreground service holds a wake lock for the whole scheduler
    window, so blocking there is cheaper than releasing the CPU and spending an
    entire alarm wakeup to read a result that was ready moments later.
    """

    def test_await_returns_the_terminal_record_without_caller_polling(self) -> None:
        store = DurableOperationStore()
        try:
            store.register_runner(
                "fixture-query",
                lambda _execution, _payload: (
                    time.sleep(0.2) or {"feature": "brush", "settled": True}
                ),
            )
            submitted = store.submit_network(
                account_ref="account-1",
                operation_type=QUERY,
                kind="fixture-query",
                idempotency_key="await-1",
            )

            operation = store.await_status(submitted["operationId"], 5_000)

            self.assertIsNotNone(operation)
            self.assertEqual(operation["status"], SUCCEEDED)
            self.assertTrue(operation["result"]["settled"])
        finally:
            store.close()

    def test_await_gives_up_at_the_budget_and_returns_the_pending_record(self) -> None:
        """Timing out is a latency outcome, not an error: the lane keeps running."""

        release = threading.Event()
        store = DurableOperationStore()
        try:
            store.register_runner(
                "fixture-query",
                lambda _execution, _payload: (
                    release.wait(5.0) or {"feature": "brush"}
                ),
            )
            submitted = store.submit_network(
                account_ref="account-1",
                operation_type=QUERY,
                kind="fixture-query",
                idempotency_key="await-2",
            )

            started = time.monotonic()
            operation = store.await_status(submitted["operationId"], 150)
            elapsed = time.monotonic() - started

            self.assertIsNotNone(operation)
            self.assertNotEqual(operation["status"], SUCCEEDED)
            # Bounded: it must not wait for the lane, but must honour the budget.
            self.assertGreaterEqual(elapsed, 0.1)
            self.assertLess(elapsed, 2.0)
        finally:
            release.set()
            store.close()

    def test_await_reports_a_missing_operation_the_same_way_status_does(self) -> None:
        store = DurableOperationStore()
        try:
            self.assertIsNone(store.await_status("op_does_not_exist", 50))
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
