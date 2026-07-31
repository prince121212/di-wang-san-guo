"""Durable asynchronous-operation primitives owned by the shared core.

The phase-3 implementation deliberately simulates network latency and never opens a
socket.  It proves the contract needed by real game operations later: submission is
immediate, an idempotency key deduplicates retries, and status/result survive a host
or page recreation.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


OPERATION_STORE_SCHEMA = 1
SIMULATED_OPERATION_KIND = "simulated-network"
RUNNING = "RUNNING"
SUCCEEDED = "SUCCEEDED"
CANCELLED = "CANCELLED"
TERMINAL_STATES = frozenset((SUCCEEDED, CANCELLED))


class DurableOperationStore:
    """Thread-safe operation ledger with optional atomic JSON persistence."""

    def __init__(
        self,
        path: Optional[Path] = None,
        now_millis: Optional[Callable[[], int]] = None,
    ) -> None:
        self._path = path
        self._now_millis = now_millis or (lambda: int(time.time() * 1000))
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._closed = threading.Event()
        self._records: Dict[str, Dict[str, Any]] = {}
        self._load()
        self._resume_running_operations()
        self._worker = threading.Thread(
            target=self._run_scheduler,
            name="dwpm-operation-scheduler",
            daemon=True,
        )
        self._worker.start()

    @property
    def persistent(self) -> bool:
        return self._path is not None

    def submit_simulated(
        self,
        duration_millis: int,
        idempotency_key: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        duration = int(duration_millis)
        if duration < 0 or duration > 10 * 60 * 1000:
            raise ValueError("simulated operation duration must be between 0 and 600000 ms")
        key = str(idempotency_key).strip()
        if not key or len(key) > 160:
            raise ValueError("idempotency key must contain between 1 and 160 characters")
        normalized_payload = dict(payload or {})
        with self._lock:
            existing = next(
                (
                    record
                    for record in self._records.values()
                    if record.get("idempotencyKey") == key
                ),
                None,
            )
            if existing is not None:
                if (
                    existing.get("durationMillis") != duration
                    or existing.get("payload") != normalized_payload
                ):
                    raise ValueError("idempotency key was already used with different input")
                if self._refresh_locked(existing):
                    self._persist_locked()
                return self._submission_view(existing, deduplicated=True)

            submitted_at = self._now_millis()
            operation_id = f"op_{uuid.uuid4().hex}"
            record: Dict[str, Any] = {
                "operationId": operation_id,
                "kind": SIMULATED_OPERATION_KIND,
                "idempotencyKey": key,
                "status": RUNNING,
                "submittedAtMillis": submitted_at,
                "updatedAtMillis": submitted_at,
                "completeAtMillis": submitted_at + duration,
                "durationMillis": duration,
                "payload": normalized_payload,
                "progress": 0,
                "result": None,
                "error": None,
            }
            self._records[operation_id] = record
            self._refresh_locked(record)
            self._persist_locked()
            self._condition.notify_all()
            return self._submission_view(record, deduplicated=False)

    def status(self, operation_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            record = self._records.get(str(operation_id))
            if record is None:
                return None
            changed = self._refresh_locked(record)
            if changed:
                self._persist_locked()
            return self._public_record(record)

    def list_operations(self) -> List[Dict[str, Any]]:
        with self._lock:
            changed = False
            for record in self._records.values():
                changed = self._refresh_locked(record) or changed
            if changed:
                self._persist_locked()
            return [
                self._public_record(record)
                for record in sorted(
                    self._records.values(),
                    key=lambda item: (item["submittedAtMillis"], item["operationId"]),
                    reverse=True,
                )
            ]

    def cancel(self, operation_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            record = self._records.get(str(operation_id))
            if record is None:
                return None
            self._refresh_locked(record)
            if record["status"] == RUNNING:
                now = self._now_millis()
                record.update(
                    status=CANCELLED,
                    progress=0,
                    updatedAtMillis=now,
                    result={"cancelled": True, "cancelledAtMillis": now},
                )
                self._persist_locked()
                self._condition.notify_all()
            return self._public_record(record)

    def close(self) -> None:
        self._closed.set()
        with self._condition:
            self._condition.notify_all()

    def _load(self) -> None:
        if self._path is None or not self._path.is_file():
            return
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if payload.get("schemaVersion") != OPERATION_STORE_SCHEMA:
            raise ValueError("unsupported operation-store schema")
        records = payload.get("operations")
        if not isinstance(records, list):
            raise ValueError("operation-store records must be a list")
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("operation-store record must be an object")
            operation_id = str(record.get("operationId", ""))
            if not operation_id or operation_id in self._records:
                raise ValueError("operation-store contains an invalid or duplicate ID")
            self._records[operation_id] = record

    def _resume_running_operations(self) -> None:
        with self._lock:
            changed = False
            for record in self._records.values():
                changed = self._refresh_locked(record) or changed
            if changed:
                self._persist_locked()

    def _run_scheduler(self) -> None:
        while not self._closed.is_set():
            with self._condition:
                running = [
                    record
                    for record in self._records.values()
                    if record.get("status") == RUNNING
                ]
                if not running:
                    self._condition.wait()
                    continue
                next_deadline = min(int(record["completeAtMillis"]) for record in running)
                remaining = next_deadline - self._now_millis()
                if remaining > 0:
                    self._condition.wait(remaining / 1000.0)
                    continue
                changed = False
                for record in running:
                    changed = self._refresh_locked(record) or changed
                if changed:
                    self._persist_locked()

    def _refresh_locked(self, record: Dict[str, Any]) -> bool:
        if record.get("status") != RUNNING:
            return False
        now = self._now_millis()
        submitted = int(record["submittedAtMillis"])
        complete_at = int(record["completeAtMillis"])
        duration = max(1, complete_at - submitted)
        if now < complete_at:
            progress = max(0, min(99, int((now - submitted) * 100 / duration)))
            if progress != record.get("progress"):
                record["progress"] = progress
                record["updatedAtMillis"] = now
                return True
            return False
        record.update(
            status=SUCCEEDED,
            progress=100,
            updatedAtMillis=now,
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
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self._path)

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
            "completeAtMillis": record["completeAtMillis"],
        }

    @staticmethod
    def _public_record(record: Dict[str, Any]) -> Dict[str, Any]:
        return json.loads(json.dumps(record, ensure_ascii=False))
