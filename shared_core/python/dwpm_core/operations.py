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

OperationRunner = Callable[["OperationExecutionContext", Dict[str, Any]], Dict[str, Any]]
OperationEventCallback = Callable[[Dict[str, Any]], None]


class OperationCancelledError(RuntimeError):
    """Raised before a request is sent when the operation was cancelled."""


class OperationUncertainError(RuntimeError):
    """Raised when a mutating request may have reached the game server."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})


class OperationExecutionContext:
    """Narrow runner API which makes send/cancel semantics explicit."""

    def __init__(self, store: "DurableOperationStore", operation_id: str) -> None:
        self._store = store
        self.operation_id = operation_id

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

    def register_runner(self, kind: str, runner: OperationRunner) -> None:
        normalized_kind = self._normalized_text(kind, "operation kind", 160)
        if not callable(runner):
            raise TypeError("operation runner must be callable")
        with self._condition:
            current = self._runners.get(normalized_kind)
            if current is not None and current is not runner:
                raise ValueError(f"operation runner already registered: {normalized_kind}")
            self._runners[normalized_kind] = runner
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
    ) -> Dict[str, Any]:
        account = self._normalized_text(account_ref, "account ref", 200)
        normalized_type = str(operation_type or "").strip().lower()
        if normalized_type not in OPERATION_TYPES:
            raise ValueError("operation type must be query or mutation")
        normalized_kind = self._normalized_text(kind, "operation kind", 160)
        key = self._normalized_text(idempotency_key, "idempotency key", 200)
        normalized_payload = self._json_object(payload or {}, "operation payload")
        with self._condition:
            if coalesce_active:
                active = self._find_active_equivalent_locked(
                    account,
                    normalized_type,
                    normalized_kind,
                    normalized_payload,
                )
                if active is not None:
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
            }
            self._records[operation_id] = record
            self._persist_locked()
            self._ensure_lane_locked(account)
            self._condition.notify_all()
            submission = self._submission_view(record, deduplicated=False)
        self._emit("operation.accepted", record)
        return submission

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

    def cancel(self, operation_id: str) -> Optional[Dict[str, Any]]:
        event_record: Optional[Dict[str, Any]] = None
        with self._condition:
            record = self._records.get(str(operation_id))
            if record is None:
                return None
            self._refresh_simulated_locked(record)
            if record.get("status") in (QUEUED, RUNNING):
                if record.get("requestSent"):
                    record["cancellationDenied"] = "request-already-sent"
                    record["updatedAtMillis"] = self._now_millis()
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
                self._persist_locked()
                self._condition.notify_all()
            public = self._public_record(record)
        if event_record is not None:
            self._emit("operation.cancelled", event_record)
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
            except Exception as error:
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
            self._persist_locked()
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

    def _persist_locked(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": OPERATION_STORE_SCHEMA,
            "operations": list(self._records.values()),
        }
        temporary = self._path.with_name(f"{self._path.name}.tmp")
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        with temporary.open("wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(self._path)

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
            "updatedAtMillis": record.get("updatedAtMillis"),
            "error": record.get("error"),
        }
        try:
            callback(self._public_record(event))
        except Exception:
            # A display/event adapter must never break business execution.
            return
