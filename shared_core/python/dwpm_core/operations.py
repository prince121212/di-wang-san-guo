"""Durable, per-account asynchronous operation lanes for the shared core.

Submitting an operation performs only validation and durable ledger creation. Real
game I/O is always executed on the account's background lane, so WebView, local
settings, logs and snapshots never wait for the game server.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


OPERATION_STORE_SCHEMA = 2
LEGACY_OPERATION_STORE_SCHEMA = 1
SIMULATED_OPERATION_KIND = "simulated-network"

QUERY = "query"
MUTATION = "mutation"
OPERATION_TYPES = frozenset((QUERY, MUTATION))

QUEUED = "QUEUED"
RUNNING = "RUNNING"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
UNCERTAIN = "UNCERTAIN"
TERMINAL_STATES = frozenset((SUCCEEDED, FAILED, CANCELLED, UNCERTAIN))

#: Outcomes that are definitively closed: nothing is left to adjudicate and no
#: recovery decision can ever depend on them again.  Only these may be pruned.
#: ``UNCERTAIN`` is terminal but deliberately excluded - it is the record of a
#: send boundary nobody resolved, which is the one thing this ledger exists for.
#: ``FAILED`` is excluded too: it is rare, and it is what a person reads when
#: asking why something stopped.
PRUNABLE_STATES = frozenset((SUCCEEDED, CANCELLED))

#: How many definitively-closed operations to keep.
#:
#: The ledger had no retention at all.  A resident tick creates one durable
#: operation every few seconds and every one was kept forever: a real device
#: reached 11,744 records in a 52 MB file, 11,610 of them completed scheduler
#: ticks.  The whole file is re-serialised and rewritten on *every* state
#: transition, so that became tens of megabytes of JSON encoding and flash
#: writes per tick, and about 400 MB of native heap.  MIUI killed the process
#: with ``ScreenOffCPUCheckKill`` and both accounts lost seven hours overnight.
#: Unbounded retention was not caution - it is what made the process look
#: exactly like the runaway it had become.
#:
#: This bounds historical, unretained results. A suspended consumer can miss
#: any fixed-size window while another account runs, so resident results are
#: separately retained until consumption, not merely until completion.
MAX_RETAINED_CLOSED_OPERATIONS = 300

#: Largest result field kept once an operation is definitively closed.
#:
#: ``result`` was 96% of the ledger, and one closed tick carried 109 KB of raw
#: per-coordinate ``scanResults`` - the working notes of how the outcome was
#: computed, which nothing reads once the outcome exists.  Measured against the
#: device: every field any consumer reads back from a closed operation is at
#: most 550 bytes (``successRecord``), while the bulky ones nobody reads run
#: from 5 KB to 109 KB.
#:
#: The bound is on *size* rather than on a list of field names, deliberately.
#: A keep-list silently loses data the day someone adds a field; a drop-list
#: silently leaks the day someone adds a bulky one.  Size is the property that
#: actually matters, and it needs no maintenance.
MAX_RETAINED_RESULT_FIELD_BYTES = 4096

#: Most recent closed operations kept whole, before compaction may touch them.
#:
#: A result is working notes only *after* everyone has had a chance to read it.
#: Compacting at the moment of closing is too early: the caller reads the
#: outcome immediately afterwards, and the desktop 副本/无损 ticks failed with
#: "未返回业务结果" the first time this ran. Retained resident results are
#: excluded from compaction altogether until the host consumes them.
UNCOMPACTED_CLOSED_OPERATIONS = 50

OperationRunner = Callable[["OperationExecutionContext", Dict[str, Any]], Dict[str, Any]]
OperationEventCallback = Callable[[Dict[str, Any]], None]
OperationRunGate = Callable[[], bool]


def _compact_closed_result(record: Dict[str, Any]) -> None:
    """Drop oversized result fields once nothing can read them again.

    Runs once per record: an operation that is definitively closed has already
    handed its outcome to whoever asked, so what remains of the bulk is working
    notes.  What was dropped is recorded rather than silently removed.
    """

    if record.get("resultCompacted"):
        return
    result = record.get("result")
    if not isinstance(result, dict):
        record["resultCompacted"] = True
        return
    dropped: Dict[str, int] = {}
    for key in list(result.keys()):
        try:
            size = len(
                json.dumps(result[key], ensure_ascii=False, default=str)
            )
        except (TypeError, ValueError):
            size = MAX_RETAINED_RESULT_FIELD_BYTES + 1
        if size > MAX_RETAINED_RESULT_FIELD_BYTES:
            dropped[key] = size
            result.pop(key, None)
    record["resultCompacted"] = True
    if dropped:
        record["resultDroppedFieldBytes"] = dropped


class OperationCancelledError(RuntimeError):
    """Raised before a request is sent when the operation was cancelled."""


class OperationUncertainError(RuntimeError):
    """Raised when a mutating request may have reached the game server."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})


class OperationKnownFailureError(RuntimeError):
    """A sent request received a definitive failure and must not become uncertain."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "OPERATION_FAILED",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = str(code or "OPERATION_FAILED")
        self.details = dict(details or {})


class OperationDeferredError(RuntimeError):
    """Raised while a durable operation is waiting for a host capability.

    Losing foreground-service ownership or validated network access before a
    request is sent is not a business failure. The same operation must remain
    queued so a later Android service/process recovery can continue it without
    creating a second idempotency record.
    """


class OperationExecutionContext:
    """Narrow runner API which makes send/cancel semantics explicit."""

    def __init__(self, store: "DurableOperationStore", operation_id: str) -> None:
        self._store = store
        self.operation_id = operation_id

    @property
    def host_ready_observed(self) -> bool:
        """Whether the host execution gate was true when this run started."""

        return self._store._host_ready_observed(self.operation_id)

    def mark_request_sent(
        self,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist the point after which mutation retries may be unsafe."""

        self._store._mark_request_sent(self.operation_id, metadata)

    def publish_progress(
        self,
        progress: int,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._store._publish_progress(self.operation_id, progress, details)

    def raise_if_cancelled(self) -> None:
        self._store._raise_if_cancelled(self.operation_id)

    def wait(self, seconds: float) -> None:
        """Cancellation-aware wait for test runners and later retry backoff."""

        deadline = time.monotonic() + max(0.0, float(seconds))
        while True:
            self.raise_if_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            if self._store._closed.wait(min(remaining, 0.05)):
                raise OperationCancelledError("operation store is closing")


class DurableOperationStore:
    """Thread-safe operation ledger with one independent lane per account."""

    def __init__(
        self,
        path: Optional[Path] = None,
        now_millis: Optional[Callable[[], int]] = None,
        event_callback: Optional[OperationEventCallback] = None,
    ) -> None:
        self._path = path
        self._now_millis = now_millis or (lambda: int(time.time() * 1000))
        self._event_callback = event_callback
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._closed = threading.Event()
        self._records: Dict[str, Dict[str, Any]] = {}
        self._runners: Dict[str, OperationRunner] = {}
        self._runner_gates: Dict[str, OperationRunGate] = {}
        self._lane_threads: Dict[str, threading.Thread] = {}
        self._load()
        self._resume_operations_after_load()
        self._scheduler = threading.Thread(
            target=self._run_simulated_scheduler,
            name="dwpm-operation-scheduler",
            daemon=True,
        )
        self._scheduler.start()

    @property
    def persistent(self) -> bool:
        return self._path is not None

    def register_runner(
        self,
        kind: str,
        runner: OperationRunner,
        *,
        runnable_when: Optional[OperationRunGate] = None,
    ) -> None:
        normalized_kind = self._normalized_text(kind, "operation kind", 160)
        if not callable(runner):
            raise TypeError("operation runner must be callable")
        if runnable_when is not None and not callable(runnable_when):
            raise TypeError("operation run gate must be callable")
        with self._condition:
            current = self._runners.get(normalized_kind)
            if current is not None and current is not runner:
                raise ValueError(f"operation runner already registered: {normalized_kind}")
            self._runners[normalized_kind] = runner
            if runnable_when is None:
                self._runner_gates.pop(normalized_kind, None)
            else:
                self._runner_gates[normalized_kind] = runnable_when
            accounts = {
                str(record.get("accountRef") or "")
                for record in self._records.values()
                if record.get("kind") == normalized_kind
                and record.get("status") == QUEUED
            }
            for account_ref in accounts:
                if account_ref:
                    self._ensure_lane_locked(account_ref)
            self._condition.notify_all()

    def submit_network(
        self,
        *,
        account_ref: str,
        operation_type: str,
        kind: str,
        idempotency_key: str,
        payload: Optional[Dict[str, Any]] = None,
        coalesce_active: bool = False,
        defer_until_ready: bool = False,
        result_retention_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        account = self._normalized_text(account_ref, "account ref", 200)
        normalized_type = str(operation_type or "").strip().lower()
        if normalized_type not in OPERATION_TYPES:
            raise ValueError("operation type must be query or mutation")
        normalized_kind = self._normalized_text(kind, "operation kind", 160)
        key = self._normalized_text(idempotency_key, "idempotency key", 200)
        normalized_payload = self._json_object(payload or {}, "operation payload")
        retention_key = (
            self._normalized_text(result_retention_key, "result retention key", 200)
            if result_retention_key is not None else None
        )
        with self._condition:
            if coalesce_active:
                active = self._find_active_equivalent_locked(
                    account,
                    normalized_type,
                    normalized_kind,
                    normalized_payload,
                )
                if active is not None:
                    self._retain_result_locked(active, retention_key)
                    return self._submission_view(active, deduplicated=True)
            existing = self._find_idempotent_locked(
                account,
                normalized_kind,
                key,
            )
            if existing is not None:
                if (
                    existing.get("operationType") != normalized_type
                    or existing.get("payload") != normalized_payload
                ):
                    raise ValueError(
                        "idempotency key was already used with different input"
                    )
                self._retain_result_locked(existing, retention_key)
                return self._submission_view(existing, deduplicated=True)

            submitted_at = self._now_millis()
            operation_id = f"op_{uuid.uuid4().hex}"
            record: Dict[str, Any] = {
                "operationId": operation_id,
                "kind": normalized_kind,
                "operationType": normalized_type,
                "accountRef": account,
                "idempotencyKey": key,
                "status": QUEUED,
                "submittedAtMillis": submitted_at,
                "startedAtMillis": None,
                "updatedAtMillis": submitted_at,
                "completedAtMillis": None,
                "payload": normalized_payload,
                "progress": 0,
                "progressDetails": None,
                "requestSent": False,
                "requestSentAtMillis": None,
                "requestMetadata": None,
                "cancelRequested": False,
                "result": None,
                "error": None,
                # Background resident work opts into waiting for the host
                # execution lane.  Fresh foreground requests retain their
                # historical fail-fast behavior when no owner is present.
                "recoveryPending": bool(defer_until_ready),
                "hostReadyObserved": False,
            }
            if retention_key is not None:
                # A new operation from this same serial consumer supersedes
                # its closed results. This also repairs a crash between local
                # pointer removal and the best-effort acknowledgement.
                for previous in self._records.values():
                    if (
                        previous.get("accountRef") == account
                        and previous.get("resultRetentionKey") == retention_key
                        and previous.get("status") in TERMINAL_STATES
                    ):
                        previous["resultRetained"] = False
                record["resultRetentionKey"] = retention_key
                record["resultRetained"] = True
            self._records[operation_id] = record
            self._persist_locked()
            self._ensure_lane_locked(account)
            self._condition.notify_all()
            submission = self._submission_view(record, deduplicated=False)
        self._emit("operation.accepted", record)
        return submission

    def _retain_result_locked(
        self, record: Dict[str, Any], retention_key: Optional[str]
    ) -> None:
        if retention_key is None or (
            record.get("resultRetentionKey") == retention_key
            and record.get("resultRetained")
        ):
            return
        existing = record.get("resultRetentionKey")
        if existing is not None and existing != retention_key:
            raise ValueError("operation result already belongs to another consumer")
        record["resultRetentionKey"] = retention_key
        record["resultRetained"] = True
        self._persist_locked()

    def acknowledge_result(
        self, operation_id: str, *, account_ref: str, retention_key: str
    ) -> bool:
        """Release a closed result only after its consumer removed its pointer.

        This is not business reconciliation. UNCERTAIN/FAILED records remain
        protected by their existing retention policy even after acknowledgement.
        """

        with self._condition:
            record = self._records.get(str(operation_id))
            if (
                record is None
                or record.get("accountRef") != str(account_ref)
                or record.get("resultRetentionKey") != str(retention_key)
                or record.get("status") not in TERMINAL_STATES
            ):
                return False
            if record.get("resultRetained"):
                record["resultRetained"] = False
                self._persist_locked()
            return True

    def _find_active_equivalent_locked(
        self,
        account_ref: str,
        operation_type: str,
        kind: str,
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        signature = self._active_query_signature(payload)
        candidates = [
            record
            for record in self._records.values()
            if record.get("accountRef") == account_ref
            and record.get("operationType") == operation_type
            and record.get("kind") == kind
            and record.get("status") in (QUEUED, RUNNING)
            and self._active_query_signature(
                self._json_object(
                    record.get("payload") or {},
                    "operation payload",
                )
            ) == signature
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda record: (
                int(record.get("submittedAtMillis") or 0),
                str(record.get("operationId") or ""),
            ),
        )

    @staticmethod
    def _active_query_signature(payload: Dict[str, Any]) -> Dict[str, Any]:
        copied = json.loads(json.dumps(payload, ensure_ascii=False))
        context = copied.get("requestContext")
        if isinstance(context, dict):
            context.pop("requestId", None)
        return copied

    def submit_simulated(
        self,
        duration_millis: int,
        idempotency_key: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Backward-compatible offline delay used only by Debug verification."""

        duration = int(duration_millis)
        if duration < 0 or duration > 10 * 60 * 1000:
            raise ValueError(
                "simulated operation duration must be between 0 and 600000 ms"
            )
        key = self._normalized_text(idempotency_key, "idempotency key", 160)
        normalized_payload = self._json_object(payload or {}, "operation payload")
        with self._condition:
            existing = next(
                (
                    record
                    for record in self._records.values()
                    if record.get("kind") == SIMULATED_OPERATION_KIND
                    and record.get("idempotencyKey") == key
                ),
                None,
            )
            if existing is not None:
                if (
                    existing.get("durationMillis") != duration
                    or existing.get("payload") != normalized_payload
                ):
                    raise ValueError(
                        "idempotency key was already used with different input"
                    )
                if self._refresh_simulated_locked(existing):
                    self._persist_locked()
                return self._submission_view(existing, deduplicated=True)

            submitted_at = self._now_millis()
            operation_id = f"op_{uuid.uuid4().hex}"
            record = {
                "operationId": operation_id,
                "kind": SIMULATED_OPERATION_KIND,
                "operationType": QUERY,
                "accountRef": "__debug_simulation__",
                "idempotencyKey": key,
                "status": RUNNING,
                "submittedAtMillis": submitted_at,
                "startedAtMillis": submitted_at,
                "updatedAtMillis": submitted_at,
                "completedAtMillis": None,
                "completeAtMillis": submitted_at + duration,
                "durationMillis": duration,
                "payload": normalized_payload,
                "progress": 0,
                "progressDetails": None,
                "requestSent": False,
                "requestSentAtMillis": None,
                "requestMetadata": None,
                "cancelRequested": False,
                "result": None,
                "error": None,
            }
            self._records[operation_id] = record
            self._refresh_simulated_locked(record)
            self._persist_locked()
            self._condition.notify_all()
            submission = self._submission_view(record, deduplicated=False)
        self._emit("operation.accepted", record)
        return submission

    def status(self, operation_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            record = self._records.get(str(operation_id))
            if record is None:
                return None
            changed = self._refresh_simulated_locked(record)
            if changed:
                self._persist_locked()
            return self._public_record(record)

    def await_status(
        self,
        operation_id: str,
        timeout_millis: int,
    ) -> Optional[Dict[str, Any]]:
        """Read one operation, blocking until it settles or the budget ends.

        A screen-off Android host already holds a wake lock while the lane
        thread finishes, so waiting here is far cheaper than releasing the CPU
        and paying a whole alarm wakeup to read the same result moments later.
        Waiting on the shared condition also releases the GIL, so this never
        competes with the lane thread it is waiting for.  The budget is a
        latency optimisation only: a caller that times out still receives the
        current non-terminal record and keeps its existing polling path.
        """
        deadline = self._now_millis() + max(0, int(timeout_millis))
        with self._condition:
            while True:
                record = self._records.get(str(operation_id))
                if record is None:
                    return None
                if self._refresh_simulated_locked(record):
                    self._persist_locked()
                remaining = deadline - self._now_millis()
                if record.get("status") in TERMINAL_STATES or remaining <= 0:
                    return self._public_record(record)
                self._condition.wait(remaining / 1000.0)

    def list_operations(self) -> List[Dict[str, Any]]:
        with self._lock:
            changed = False
            for record in self._records.values():
                changed = self._refresh_simulated_locked(record) or changed
            if changed:
                self._persist_locked()
            return [
                self._public_record(record)
                for record in sorted(
                    self._records.values(),
                    key=lambda item: (
                        int(item.get("submittedAtMillis") or 0),
                        str(item.get("operationId") or ""),
                    ),
                    reverse=True,
                )
            ]

    def list_result_facts(
        self,
        account_ref: str,
        *,
        result_keys: List[str],
        required_truthy_key: str = "",
        limit: int = 1_000,
    ) -> List[Dict[str, Any]]:
        """Return a bounded, compact view of successful operation results.

        Some protocol results contain full catalogs and packet captures.  Local
        projections such as the success-record page need only a few fields and
        must not deep-copy the complete durable ledger on every refresh.
        """

        account = str(account_ref or "").strip()
        if not account:
            return []
        keys = list(dict.fromkeys(
            str(value or "").strip()
            for value in result_keys
            if str(value or "").strip()
        ))
        required = str(required_truthy_key or "").strip()
        bounded = max(1, min(int(limit), 10_000))
        with self._lock:
            records = sorted(
                self._records.values(),
                key=lambda item: (
                    int(item.get("completedAtMillis") or 0),
                    int(item.get("submittedAtMillis") or 0),
                    str(item.get("operationId") or ""),
                ),
                reverse=True,
            )
            facts = []
            for record in records:
                if str(record.get("accountRef") or "") != account:
                    continue
                if record.get("status") != SUCCEEDED:
                    continue
                result = record.get("result")
                if not isinstance(result, dict):
                    continue
                if required and not bool(result.get(required)):
                    continue
                facts.append(self._public_record({
                    "operationId": record.get("operationId"),
                    "kind": record.get("kind"),
                    "accountRef": account,
                    "status": SUCCEEDED,
                    "submittedAtMillis": record.get("submittedAtMillis"),
                    "updatedAtMillis": record.get("updatedAtMillis"),
                    "completedAtMillis": record.get("completedAtMillis"),
                    "result": {
                        key: result[key]
                        for key in keys
                        if key in result
                    },
                }))
                if len(facts) >= bounded:
                    break
            return facts

    def cancel(self, operation_id: str) -> Optional[Dict[str, Any]]:
        event_record: Optional[Dict[str, Any]] = None
        event_type: Optional[str] = None
        with self._condition:
            record = self._records.get(str(operation_id))
            if record is None:
                return None
            self._refresh_simulated_locked(record)
            if record.get("status") in (QUEUED, RUNNING):
                if record.get("requestSent"):
                    record["cancellationDenied"] = "request-already-sent"
                    record["updatedAtMillis"] = self._now_millis()
                    event_record = dict(record)
                    event_type = "operation.cancel-denied"
                else:
                    now = self._now_millis()
                    record.update(
                        status=CANCELLED,
                        cancelRequested=True,
                        progress=0,
                        updatedAtMillis=now,
                        completedAtMillis=now,
                        result={"cancelled": True, "cancelledAtMillis": now},
                        error=None,
                    )
                    event_record = dict(record)
                    event_type = "operation.cancelled"
                self._persist_locked()
                self._condition.notify_all()
            public = self._public_record(record)
        if event_record is not None and event_type is not None:
            self._emit(event_type, event_record)
        return public

    def close(self) -> None:
        self._closed.set()
        with self._condition:
            self._condition.notify_all()

    def _load(self) -> None:
        if self._path is None or not self._path.is_file():
            return
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        schema = int(payload.get("schemaVersion") or 0)
        if schema not in (LEGACY_OPERATION_STORE_SCHEMA, OPERATION_STORE_SCHEMA):
            raise ValueError("unsupported operation-store schema")
        records = payload.get("operations")
        if not isinstance(records, list):
            raise ValueError("operation-store records must be a list")
        for raw_record in records:
            if not isinstance(raw_record, dict):
                raise ValueError("operation-store record must be an object")
            record = dict(raw_record)
            operation_id = str(record.get("operationId", ""))
            if not operation_id or operation_id in self._records:
                raise ValueError(
                    "operation-store contains an invalid or duplicate ID"
                )
            if schema == LEGACY_OPERATION_STORE_SCHEMA:
                record.setdefault("operationType", QUERY)
                record.setdefault("accountRef", "__debug_simulation__")
                record.setdefault("startedAtMillis", record.get("submittedAtMillis"))
                record.setdefault("completedAtMillis", None)
                record.setdefault("progressDetails", None)
                record.setdefault("requestSent", False)
                record.setdefault("requestSentAtMillis", None)
                record.setdefault("requestMetadata", None)
                record.setdefault("cancelRequested", False)
            self._records[operation_id] = record

    def _resume_operations_after_load(self) -> None:
        with self._condition:
            changed = False
            for record in self._records.values():
                if record.get("kind") == SIMULATED_OPERATION_KIND:
                    changed = self._refresh_simulated_locked(record) or changed
                    continue
                # Any non-terminal operation loaded into a new process must
                # wait for the host execution lane to become ready.  This is
                # the durable hand-over marker that closes the Application /
                # ForegroundService startup race.
                if record.get("status") == QUEUED:
                    # Every queued record loaded from disk belongs to the
                    # previous process. Mark it as a hand-over record; fresh
                    # submissions made after this constructor returns do not
                    # receive this marker and retain fail-fast semantics.
                    if not record.get("recoveryPending"):
                        record["recoveryPending"] = True
                        record["hostReadyObserved"] = False
                        changed = True
                    continue
                if record.get("status") != RUNNING:
                    continue
                now = self._now_millis()
                if record.get("requestSent"):
                    record.update(
                        status=UNCERTAIN,
                        updatedAtMillis=now,
                        completedAtMillis=now,
                        error={
                            "code": "RECOVERED_AFTER_REQUEST_SENT",
                            "message": (
                                "进程恢复时请求已发送但回执未知；禁止自动重发"
                            ),
                        },
                    )
                else:
                    record.update(
                        status=QUEUED,
                        startedAtMillis=None,
                        updatedAtMillis=now,
                        recoveryPending=True,
                        hostReadyObserved=False,
                    )
                changed = True
            if changed:
                self._persist_locked()

    def _run_simulated_scheduler(self) -> None:
        while not self._closed.is_set():
            completed_events: List[Dict[str, Any]] = []
            with self._condition:
                running = [
                    record
                    for record in self._records.values()
                    if record.get("kind") == SIMULATED_OPERATION_KIND
                    and record.get("status") == RUNNING
                ]
                if not running:
                    self._condition.wait(timeout=0.5)
                    continue
                next_deadline = min(
                    int(record["completeAtMillis"]) for record in running
                )
                remaining = next_deadline - self._now_millis()
                if remaining > 0:
                    self._condition.wait(min(remaining / 1000.0, 0.5))
                    continue
                changed = False
                for record in running:
                    old_status = record.get("status")
                    changed = self._refresh_simulated_locked(record) or changed
                    if old_status != record.get("status") == SUCCEEDED:
                        completed_events.append(dict(record))
                if changed:
                    self._persist_locked()
            for record in completed_events:
                self._emit("operation.completed", record)

    def _ensure_lane_locked(self, account_ref: str) -> None:
        current = self._lane_threads.get(account_ref)
        if current is not None and current.is_alive():
            return
        thread = threading.Thread(
            target=self._run_account_lane,
            args=(account_ref,),
            name=f"dwpm-network-{self._safe_thread_label(account_ref)}",
            daemon=True,
        )
        self._lane_threads[account_ref] = thread
        thread.start()

    def _run_account_lane(self, account_ref: str) -> None:
        while not self._closed.is_set():
            with self._condition:
                record = self._next_runnable_locked(account_ref)
                if record is None:
                    has_pending = any(
                        row.get("accountRef") == account_ref
                        and row.get("status") == QUEUED
                        for row in self._records.values()
                    )
                    if not has_pending:
                        self._lane_threads.pop(account_ref, None)
                        return
                    self._condition.wait(timeout=0.5)
                    continue
                runner = self._runners[str(record["kind"])]
                now = self._now_millis()
                record.update(
                    status=RUNNING,
                    startedAtMillis=now,
                    updatedAtMillis=now,
                    progress=max(1, int(record.get("progress") or 0)),
                    hostReadyObserved=self._runner_gate_value_locked(
                        str(record.get("kind") or "")
                    ),
                    # Keep the recovery marker for the entire attempt. If the
                    # host owner disappears between gate selection and the
                    # first request, the operation can be re-queued safely.
                    recoveryPending=bool(record.get("recoveryPending")),
                )
                self._persist_locked()
                operation_id = str(record["operationId"])
                payload = self._public_record(record.get("payload") or {})
                started_record = dict(record)
            self._emit("operation.started", started_record)

            context = OperationExecutionContext(self, operation_id)
            try:
                context.raise_if_cancelled()
                result = runner(context, payload)
                if not isinstance(result, dict):
                    raise TypeError("operation runner result must be an object")
            except OperationCancelledError as error:
                self._finish_cancelled(operation_id, str(error))
            except OperationUncertainError as error:
                self._finish_uncertain(operation_id, str(error), error.details)
            except OperationKnownFailureError as error:
                self._finish_known_failure(
                    operation_id,
                    str(error),
                    error.code,
                    error.details,
                )
            except OperationDeferredError as error:
                self._defer_operation(operation_id, str(error))
            except Exception as error:
                if self._should_defer_after_exception(operation_id):
                    self._defer_operation(
                        operation_id,
                        str(error) or error.__class__.__name__,
                    )
                else:
                    self._finish_exception(operation_id, error)
            else:
                self._finish_success(operation_id, result)

    def _next_runnable_locked(
        self,
        account_ref: str,
    ) -> Optional[Dict[str, Any]]:
        candidates = [
            record
            for record in self._records.values()
            if record.get("accountRef") == account_ref
            and record.get("status") == QUEUED
            and str(record.get("kind") or "") in self._runners
            and self._runner_is_ready_locked(record)
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda record: (
                int(record.get("submittedAtMillis") or 0),
                str(record.get("operationId") or ""),
            ),
        )

    def _runner_gate_value_locked(self, kind: str) -> bool:
        gate = self._runner_gates.get(kind)
        if gate is None:
            return True
        try:
            return bool(gate())
        except Exception:
            return False

    def _runner_is_ready_locked(self, record: Dict[str, Any]) -> bool:
        kind = str(record.get("kind") or "")
        gate = self._runner_gates.get(kind)
        if gate is None:
            return True
        # Fresh submissions retain the historical fail-fast behaviour when the
        # owner is currently absent. Records explicitly marked as a process
        # hand-over wait for the foreground lane instead.
        if not bool(record.get("recoveryPending")):
            return True
        return self._runner_gate_value_locked(kind)

    def _host_ready_observed(self, operation_id: str) -> bool:
        with self._lock:
            record = self._records.get(str(operation_id))
            return bool(record and record.get("hostReadyObserved"))

    def _should_defer_after_exception(self, operation_id: str) -> bool:
        """Classify a host disappearing during I/O as a safe deferral.

        The gate is checked once before a lane starts, but Android can revoke
        the service/network between that check and a read-only transport call.
        If the mutation boundary has not been crossed, retrying the same
        durable operation is safe and preserves its idempotency key.
        """

        with self._lock:
            record = self._records.get(str(operation_id))
            if not record or record.get("status") != RUNNING:
                return False
            if record.get("requestSent") or not record.get("recoveryPending"):
                return False
            kind = str(record.get("kind") or "")
            if kind not in self._runner_gates:
                return False
            return not self._runner_gate_value_locked(kind)

    def _defer_operation(self, operation_id: str, message: str) -> None:
        with self._condition:
            record = self._records.get(operation_id)
            if record is None or record.get("status") == CANCELLED:
                return
            if record.get("operationType") == MUTATION and record.get("requestSent"):
                uncertain = True
                event_record = None
            elif bool(record.get("recoveryPending")) or bool(
                record.get("hostReadyObserved")
            ):
                uncertain = False
                now = self._now_millis()
                record.update(
                    status=QUEUED,
                    startedAtMillis=None,
                    updatedAtMillis=now,
                    completedAtMillis=None,
                    result=None,
                    error=None,
                    recoveryPending=True,
                    hostReadyObserved=False,
                    deferredAtMillis=now,
                    deferredReason=str(message or "host capability unavailable")[:500],
                    deferredCount=int(record.get("deferredCount") or 0) + 1,
                )
                self._persist_locked()
                self._condition.notify_all()
                event_record = dict(record)
            else:
                uncertain = False
                event_record = None
        if uncertain:
            self._finish_uncertain(
                operation_id,
                message or "host capability disappeared after request send",
                {"reason": "host-capability-deferred-after-request-sent"},
            )
            return
        if event_record is not None:
            self._emit("operation.deferred", event_record)
        else:
            self._finish_known_failure(
                operation_id,
                message or "host capability unavailable",
                "EXECUTION_OWNER_UNAVAILABLE",
                {"deferred": False},
            )

    def _finish_success(
        self,
        operation_id: str,
        result: Dict[str, Any],
    ) -> None:
        event_record: Optional[Dict[str, Any]] = None
        with self._condition:
            record = self._records.get(operation_id)
            if record is None or record.get("status") == CANCELLED:
                return
            now = self._now_millis()
            record.update(
                status=SUCCEEDED,
                progress=100,
                updatedAtMillis=now,
                completedAtMillis=now,
                result=self._json_object(result, "operation result"),
                error=None,
            )
            self._persist_locked()
            self._condition.notify_all()
            event_record = dict(record)
        self._emit("operation.completed", event_record)

    def _finish_cancelled(self, operation_id: str, message: str) -> None:
        event_record: Optional[Dict[str, Any]] = None
        with self._condition:
            record = self._records.get(operation_id)
            if record is None or record.get("status") == CANCELLED:
                return
            now = self._now_millis()
            record.update(
                status=CANCELLED,
                updatedAtMillis=now,
                completedAtMillis=now,
                result={"cancelled": True},
                error={"code": "CANCELLED", "message": message},
            )
            self._persist_locked()
            self._condition.notify_all()
            event_record = dict(record)
        self._emit("operation.cancelled", event_record)

    def _finish_uncertain(
        self,
        operation_id: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        event_record: Optional[Dict[str, Any]] = None
        with self._condition:
            record = self._records.get(operation_id)
            if record is None or record.get("status") == CANCELLED:
                return
            now = self._now_millis()
            record.update(
                status=UNCERTAIN,
                updatedAtMillis=now,
                completedAtMillis=now,
                error={
                    "code": "UNCERTAIN",
                    "message": message,
                    "details": self._json_object(
                        details or {},
                        "uncertain details",
                    ),
                },
            )
            self._persist_locked()
            self._condition.notify_all()
            event_record = dict(record)
        self._emit("operation.uncertain", event_record)

    def _finish_known_failure(
        self,
        operation_id: str,
        message: str,
        code: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        event_record: Optional[Dict[str, Any]] = None
        with self._condition:
            record = self._records.get(operation_id)
            if record is None or record.get("status") == CANCELLED:
                return
            now = self._now_millis()
            record.update(
                status=FAILED,
                updatedAtMillis=now,
                completedAtMillis=now,
                error={
                    "code": str(code or "OPERATION_FAILED"),
                    "message": str(message or "operation failed"),
                    "details": self._json_object(
                        details or {},
                        "failure details",
                    ),
                },
            )
            self._persist_locked()
            self._condition.notify_all()
            event_record = dict(record)
        self._emit("operation.failed", event_record)

    def _finish_exception(self, operation_id: str, error: Exception) -> None:
        with self._condition:
            record = self._records.get(operation_id)
            if record is None or record.get("status") == CANCELLED:
                return
            uncertain = bool(
                record.get("operationType") == MUTATION
                and record.get("requestSent")
            )
        if uncertain:
            self._finish_uncertain(
                operation_id,
                str(error) or error.__class__.__name__,
                {"exceptionType": error.__class__.__name__},
            )
            return
        event_record: Optional[Dict[str, Any]] = None
        with self._condition:
            record = self._records.get(operation_id)
            if record is None or record.get("status") == CANCELLED:
                return
            now = self._now_millis()
            record.update(
                status=FAILED,
                updatedAtMillis=now,
                completedAtMillis=now,
                error={
                    "code": "OPERATION_FAILED",
                    "message": str(error) or error.__class__.__name__,
                    "exceptionType": error.__class__.__name__,
                },
            )
            self._persist_locked()
            self._condition.notify_all()
            event_record = dict(record)
        self._emit("operation.failed", event_record)

    def _mark_request_sent(
        self,
        operation_id: str,
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        with self._condition:
            record = self._records.get(operation_id)
            if (
                record is None
                or record.get("status") != RUNNING
                or record.get("cancelRequested")
            ):
                raise OperationCancelledError(
                    "operation was cancelled before request send"
                )
            if record.get("requestSent"):
                return
            now = self._now_millis()
            record.update(
                requestSent=True,
                requestSentAtMillis=now,
                requestMetadata=self._json_object(
                    metadata or {},
                    "request metadata",
                ),
                updatedAtMillis=now,
            )
            self._persist_locked()
            event_record = dict(record)
        self._emit("operation.request-sent", event_record)

    def _publish_progress(
        self,
        operation_id: str,
        progress: int,
        details: Optional[Dict[str, Any]],
    ) -> None:
        value = max(0, min(int(progress), 99))
        with self._condition:
            record = self._records.get(operation_id)
            if record is None or record.get("status") != RUNNING:
                return
            record.update(
                progress=value,
                progressDetails=self._json_object(
                    details or {},
                    "progress details",
                ),
                updatedAtMillis=self._now_millis(),
            )
            # Deliberately not persisted.  Progress is a hint for the live UI,
            # not a fact anything recovers from: status, the send-boundary
            # markers and the result are what a restart reads, and those are
            # written on their own transitions.  This was the highest-frequency
            # write in the system - a workflow publishes progress many times per
            # tick and each call re-serialised the whole ledger - which is most
            # of why the process burned enough CPU with the screen off for MIUI
            # to kill it as a runaway.  The record stays current in memory, so
            # status reads and event subscribers are unaffected.
            event_record = dict(record)
        self._emit("operation.progress", event_record)

    def _raise_if_cancelled(self, operation_id: str) -> None:
        with self._lock:
            record = self._records.get(operation_id)
            if (
                record is None
                or record.get("status") == CANCELLED
                or record.get("cancelRequested")
            ):
                raise OperationCancelledError("operation was cancelled")

    def _refresh_simulated_locked(self, record: Dict[str, Any]) -> bool:
        if (
            record.get("kind") != SIMULATED_OPERATION_KIND
            or record.get("status") != RUNNING
        ):
            return False
        now = self._now_millis()
        submitted = int(record["submittedAtMillis"])
        complete_at = int(record["completeAtMillis"])
        duration = max(1, complete_at - submitted)
        if now < complete_at:
            progress = max(
                0,
                min(99, int((now - submitted) * 100 / duration)),
            )
            if progress != record.get("progress"):
                record["progress"] = progress
                record["updatedAtMillis"] = now
                return True
            return False
        record.update(
            status=SUCCEEDED,
            progress=100,
            updatedAtMillis=now,
            completedAtMillis=now,
            result={
                "ok": True,
                "simulated": True,
                "completedAtMillis": now,
                "echo": dict(record.get("payload") or {}),
            },
            error=None,
        )
        return True

    def _prune_locked(self) -> None:
        """Drop the oldest definitively-closed operations, newest kept.

        Called before every write, so the file cannot grow without bound no
        matter how long the process runs.  Anything still open, uncertain or
        failed is never touched: only records that can no longer inform a
        recovery decision are eligible.
        """

        closed = [
            (int(record.get("updatedAtMillis") or 0), operation_id)
            for operation_id, record in self._records.items()
            if str(record.get("status") or "") in PRUNABLE_STATES
            and not bool(record.get("resultRetained"))
        ]
        closed.sort()
        # Newest first are left whole; only what has aged past the read window
        # is compacted, and only what is past the retention bound is dropped.
        for _updated_at, operation_id in closed[:-UNCOMPACTED_CLOSED_OPERATIONS]:
            record = self._records.get(operation_id)
            if record is not None:
                _compact_closed_result(record)
        excess = len(closed) - MAX_RETAINED_CLOSED_OPERATIONS
        if excess <= 0:
            return
        for _updated_at, operation_id in closed[:excess]:
            self._records.pop(operation_id, None)

    def _persist_locked(self) -> None:
        if self._path is None:
            return
        self._prune_locked()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": OPERATION_STORE_SCHEMA,
            "operations": list(self._records.values()),
        }
        # A store can briefly have more than one writer during process handover
        # or while an integration test imports the desktop host.  A fixed
        # ``.tmp`` name lets one writer replace the other writer's temporary
        # file, making the loser fail with FileNotFoundError.  Keep the final
        # replace atomic, but give every write its own staging path.
        temporary = self._path.with_name(
            (
                f"{self._path.name}.tmp."
                f"{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}"
            )
        )
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            with temporary.open("wb") as output:
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(self._path)
        finally:
            # replace() removes the staging path on success.  On a failed
            # write/replace, remove only this writer's uniquely named file;
            # never touch another process's in-flight temporary file.
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _find_idempotent_locked(
        self,
        account_ref: str,
        kind: str,
        key: str,
    ) -> Optional[Dict[str, Any]]:
        return next(
            (
                record
                for record in self._records.values()
                if record.get("accountRef") == account_ref
                and record.get("kind") == kind
                and record.get("idempotencyKey") == key
            ),
            None,
        )

    @staticmethod
    def _normalized_text(value: Any, label: str, maximum: int) -> str:
        text = str(value or "").strip()
        if not text or len(text) > maximum:
            raise ValueError(
                f"{label} must contain between 1 and {maximum} characters"
            )
        return text

    @staticmethod
    def _json_object(value: Any, label: str) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError(f"{label} must be an object")
        return json.loads(json.dumps(value, ensure_ascii=False))

    @staticmethod
    def _safe_thread_label(account_ref: str) -> str:
        output = "".join(
            character if character.isalnum() else "_"
            for character in account_ref
        ).strip("_")
        return (output or "account")[:32]

    def _submission_view(
        self,
        record: Dict[str, Any],
        deduplicated: bool,
    ) -> Dict[str, Any]:
        return {
            "ok": True,
            "accepted": True,
            "deduplicated": deduplicated,
            "operationId": record["operationId"],
            "status": record["status"],
            "submittedAtMillis": record["submittedAtMillis"],
            "completeAtMillis": record.get("completeAtMillis"),
        }

    @staticmethod
    def _public_record(record: Dict[str, Any]) -> Dict[str, Any]:
        return json.loads(json.dumps(record, ensure_ascii=False))

    def _emit(self, event_type: str, record: Dict[str, Any]) -> None:
        callback = self._event_callback
        if callback is None:
            return
        event = {
            "type": event_type,
            "operationId": record.get("operationId"),
            "kind": record.get("kind"),
            "operationType": record.get("operationType"),
            "accountRef": record.get("accountRef"),
            "status": record.get("status"),
            "progress": record.get("progress"),
            "progressDetails": record.get("progressDetails"),
            "requestSent": bool(record.get("requestSent")),
            "cancellationDenied": record.get("cancellationDenied"),
            "updatedAtMillis": record.get("updatedAtMillis"),
            "error": record.get("error"),
        }
        try:
            callback(self._public_record(event))
        except Exception:
            # A display/event adapter must never break business execution.
            return
