"""Durable non-sensitive account and public Session state.

Authentication material is deliberately outside this store.  Passwords and
Session secrets stay behind platform credential/secret ports, while both hosts
use this ledger as the canonical source for account metadata and public state.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional


ACCOUNT_STORE_SCHEMA = 1
MAX_ACCOUNT_REF_LENGTH = 200

_SENSITIVE_EXACT_KEYS = frozenset(
    (
        "dm",
        "userid",
        "accountwithsuffix",
        "gameauthsign",
        "sessiontoken",
        "accesstoken",
        "authtoken",
    )
)
_SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "cookie",
    "authorization",
    "tokenciphertext",
)
_SENSITIVE_KEY_SUFFIXES = ("token", "secret", "credential")
_PUBLIC_EVIDENCE_KEYS = frozenset(("gameauthsignevidence",))

PRESENTATION_PUBLIC_STATE_KEYS = frozenset(
    (
        "roleId",
        "roleName",
        "level",
        "nation",
        "title",
        "copper",
        "food",
        "prestige",
        "populationCurrent",
        "populationCap",
        "resourcePointCurrent",
        "resourcePointCap",
        "officeFieldFlag",
        "officeId",
        "officeIdRaw",
        "officeIdUnsigned",
        "officeName",
        "officialTitle",
        "serverKey",
        "lastValidatedAt",
        "lastHeartbeatAt",
        "lastSuccessfulGameResponseAt",
        "lastSuccessfulGameResponsePhase",
        "lastReloginAt",
        "lastReloginError",
        "lastOfflineAt",
        "lastOfflineReason",
        "lastNetworkPauseAt",
        "lastNetworkPauseReason",
        "nextReloginAt",
        "nextSessionProbeAt",
        "savedTasksStarted",
        "savedTasksStartedAt",
        "activeResidentTaskKeys",
        "roleStateJson",
        "resourceStateJson",
        "generalsJson",
        "generalsParserVersion",
        "ownedFiefLocationsJson",
        "armyJson",
        "armySource",
        "inventoryJson",
        "inventoryCapacity",
        "inventoryParserVersion",
        "inventorySlotsUsed",
        "inventoryItemCount",
        "inventoryEquipmentCount",
        "inventorySourceOpcode",
        "dailyActivityJson",
        "militaryIntelJson",
        "militarySnapshotJson",
        "residentDailyTaskStatusJson",
    )
)

RESIDENT_DAILY_COUNTS_SCHEMA = 1


class DurableAccountStore:
    """Thread-safe account ledger with atomic durable replacement."""

    def __init__(
        self,
        path: Optional[Path] = None,
        now_millis: Optional[Callable[[], int]] = None,
    ) -> None:
        self._path = path
        self._now_millis = now_millis or (lambda: 0)
        self._lock = threading.RLock()
        self._records: Dict[str, Dict[str, Any]] = {}
        self._revision = 0
        self._updated_at_millis = 0
        self._load()

    @property
    def persistent(self) -> bool:
        return self._path is not None

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            records = [
                _json_copy(self._records[key])
                for key in sorted(self._records)
            ]
            return {
                "ok": True,
                "schemaVersion": ACCOUNT_STORE_SCHEMA,
                "revision": self._revision,
                "updatedAtMillis": self._updated_at_millis,
                "accounts": records,
                "count": len(records),
                "secrets": "platform-ports-only",
            }

    def presentation_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            records = [
                _presentation_record(self._records[key])
                for key in sorted(self._records)
            ]
            return {
                "ok": True,
                "schemaVersion": ACCOUNT_STORE_SCHEMA,
                "revision": self._revision,
                "updatedAtMillis": self._updated_at_millis,
                "accounts": records,
                "count": len(records),
                "projection": "local-presentation",
                "secrets": "platform-ports-only",
            }

    def get(self, account_ref: Any) -> Optional[Dict[str, Any]]:
        key = _account_ref(account_ref)
        with self._lock:
            record = self._records.get(key)
            return _json_copy(record) if record is not None else None

    def get_presentation(self, account_ref: Any) -> Optional[Dict[str, Any]]:
        key = _account_ref(account_ref)
        with self._lock:
            record = self._records.get(key)
            return (
                _presentation_record(record)
                if record is not None
                else None
            )

    def upsert(self, record: Dict[str, Any]) -> Dict[str, Any]:
        normalized = _normalize_record(record)
        account_ref = normalized["accountRef"]
        with self._lock:
            current = self._records.get(account_ref)
            if current == normalized:
                return _json_copy(current)
            self._records[account_ref] = normalized
            self._changed_locked()
            return _json_copy(normalized)

    def import_if_empty(
        self,
        records: Iterable[Dict[str, Any]],
    ) -> Dict[str, Any]:
        normalized = _normalize_records(records)
        with self._lock:
            if self._records:
                return {
                    "ok": True,
                    "imported": False,
                    "reason": "account-store-not-empty",
                    "count": len(self._records),
                    "revision": self._revision,
                }
            self._records = normalized
            if normalized:
                self._changed_locked()
            return {
                "ok": True,
                "imported": bool(normalized),
                "reason": "imported" if normalized else "no-records",
                "count": len(self._records),
                "revision": self._revision,
            }

    def replace_all(
        self,
        records: Iterable[Dict[str, Any]],
    ) -> Dict[str, Any]:
        normalized = _normalize_records(records)
        with self._lock:
            if self._records != normalized:
                self._records = normalized
                self._changed_locked()
            return self.snapshot()

    def delete(self, account_ref: Any) -> bool:
        key = _account_ref(account_ref)
        with self._lock:
            if self._records.pop(key, None) is None:
                return False
            self._changed_locked()
            return True

    def clear(self) -> int:
        with self._lock:
            count = len(self._records)
            if count:
                self._records.clear()
                self._changed_locked()
            return count

    def _changed_locked(self) -> None:
        self._revision += 1
        self._updated_at_millis = int(self._now_millis())
        self._persist_locked()

    def _load(self) -> None:
        if self._path is None or not self._path.is_file():
            return
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if int(payload.get("schemaVersion") or 0) != ACCOUNT_STORE_SCHEMA:
            raise ValueError("unsupported account-store schema")
        records = payload.get("accounts")
        if not isinstance(records, list):
            raise ValueError("account-store accounts must be a list")
        self._records = _normalize_records(records)
        self._revision = max(0, int(payload.get("revision") or 0))
        self._updated_at_millis = max(
            0,
            int(payload.get("updatedAtMillis") or 0),
        )

    def _persist_locked(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": ACCOUNT_STORE_SCHEMA,
            "revision": self._revision,
            "updatedAtMillis": self._updated_at_millis,
            "accounts": [self._records[key] for key in sorted(self._records)],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        temporary = self._path.with_name(f"{self._path.name}.tmp")
        with temporary.open("wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(self._path)


def assert_public_account_record(record: Any) -> None:
    if not isinstance(record, dict):
        raise ValueError("account record must be an object")
    _assert_no_sensitive_fields(record)


def _normalize_records(
    records: Iterable[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    if isinstance(records, (str, bytes, dict)):
        raise ValueError("account records must be a list")
    normalized: Dict[str, Dict[str, Any]] = {}
    for record in records:
        item = _normalize_record(record)
        key = item["accountRef"]
        if key in normalized:
            raise ValueError(f"duplicate account ref: {key}")
        normalized[key] = item
    return normalized


def _normalize_record(record: Any) -> Dict[str, Any]:
    assert_public_account_record(record)
    copied = _json_copy(record)
    account_ref = _account_ref(copied.get("accountRef") or copied.get("id"))
    copied["accountRef"] = account_ref
    return copied


def _presentation_record(record: Dict[str, Any]) -> Dict[str, Any]:
    projected = {
        key: _json_copy(value)
        for key, value in record.items()
        if key != "session"
    }
    session = record.get("session")
    if not isinstance(session, dict):
        projected["session"] = None
        return projected
    public_state = session.get("publicState")
    visible_state = {
        key: value
        for key, value in (public_state or {}).items()
        if key in PRESENTATION_PUBLIC_STATE_KEYS
    } if isinstance(public_state, dict) else {}
    resident_daily_counts = _resident_daily_counts_projection(public_state)
    if resident_daily_counts is not None:
        # The durable resident state remains the only source of truth.  Expose
        # only the two tiny daily counters needed by the high-frequency UI;
        # never copy the full automation state (which may contain large
        # inventory receipts and scheduler diagnostics) into presentation.
        visible_state["residentDailyCountsJson"] = json.dumps(
            resident_daily_counts,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    resident_daily_status = _resident_daily_task_status_projection(public_state)
    if resident_daily_status is not None:
        # Keep the account-card projection small: task status is useful after an
        # Android process restart, while the full scheduler ledger can contain
        # protocol receipts and recovery diagnostics that do not belong in UI.
        visible_state["residentDailyTaskStatusJson"] = json.dumps(
            resident_daily_status,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    # Raw 0x8004 evidence is only needed by the UI's legacy recovery fallback
    # when normalized role/general state has not yet been persisted.
    if not visible_state.get("generalsJson"):
        for key in ("state8004PayloadHex", "state8004TailHex"):
            if isinstance(public_state, dict) and key in public_state:
                visible_state[key] = public_state[key]
    projected["session"] = {
        key: _json_copy(value)
        for key, value in session.items()
        if key != "publicState"
    }
    projected["session"]["publicState"] = _json_copy(visible_state)
    return projected


def _resident_daily_counts_projection(
    public_state: Any,
) -> Optional[Dict[str, Any]]:
    if not isinstance(public_state, dict):
        return None
    config = _json_object(public_state.get("residentAutomationConfigJson"))
    if _safe_int(config.get("schemaVersion"), 0) < 2:
        return None
    state = _json_object(public_state.get("residentAutomationStateJson"))
    projection: Dict[str, Any] = {
        "schemaVersion": RESIDENT_DAILY_COUNTS_SCHEMA,
        "updatedAtMillis": max(
            0,
            _safe_int(state.get("updatedAtMillis"), 0),
        ),
    }
    for feature in ("brush", "dungeon"):
        feature_state = state.get(feature)
        feature_state = (
            feature_state if isinstance(feature_state, dict) else {}
        )
        projection[feature] = {
            "dayKey": _safe_int(feature_state.get("dayKey"), -1),
            "usedCount": max(
                0,
                _safe_int(feature_state.get("usedCount"), 0),
            ),
        }
    return projection


def _resident_daily_task_status_projection(
    public_state: Any,
) -> Optional[Dict[str, Any]]:
    """Expose compact per-key daily terminal facts to local UI hosts."""

    if not isinstance(public_state, dict):
        return None
    config = _json_object(public_state.get("residentAutomationConfigJson"))
    if _safe_int(config.get("schemaVersion"), 0) < 2:
        return None
    state = _json_object(public_state.get("residentAutomationStateJson"))
    daily = state.get("daily")
    if not isinstance(daily, dict):
        return None
    output: Dict[str, Any] = {
        "schemaVersion": 1,
        "updatedAtMillis": max(0, _safe_int(state.get("updatedAtMillis"), 0)),
        "daily": {},
    }
    for key, raw in daily.items():
        if not isinstance(raw, dict):
            continue
        normalized_key = str(key or "").strip()
        if not normalized_key or len(normalized_key) > 80:
            continue
        item: Dict[str, Any] = {
            "lastState": str(raw.get("lastState") or "")[:40],
            "lastMessage": str(raw.get("lastMessage") or "")[:500],
            "skipped": bool(raw.get("skipped")),
            "skipReason": str(raw.get("skipReason") or "")[:120],
            "statusText": str(raw.get("statusText") or "")[:120],
        }
        for field in (
            "cycleKey",
            "nextWakeAtMillis",
            "completionCount",
        ):
            if raw.get(field) not in (None, ""):
                item[field] = _safe_int(raw.get(field), 0)
        output["daily"][normalized_key] = item
    return output


def _json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip().startswith("{"):
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _account_ref(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > MAX_ACCOUNT_REF_LENGTH:
        raise ValueError(
            "account ref must contain between 1 and "
            f"{MAX_ACCOUNT_REF_LENGTH} characters"
        )
    return text


def _assert_no_sensitive_fields(value: Any, prefix: str = "account") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = (
                str(key).replace("_", "").replace("-", "").lower()
            )
            sensitive = (
                normalized not in _PUBLIC_EVIDENCE_KEYS
                and (
                    normalized in _SENSITIVE_EXACT_KEYS
                    or any(
                        fragment in normalized
                        for fragment in _SENSITIVE_KEY_FRAGMENTS
                    )
                    or normalized.endswith(_SENSITIVE_KEY_SUFFIXES)
                )
            )
            if sensitive:
                raise ValueError(
                    "sensitive field cannot enter account store: "
                    f"{prefix}.{key}"
                )
            _assert_no_sensitive_fields(child, f"{prefix}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_sensitive_fields(child, f"{prefix}[{index}]")


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))
