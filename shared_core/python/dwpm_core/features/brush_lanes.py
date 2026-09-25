"""Durable brush lanes: one executing request, many independent expeditions.

The legacy field is the *selected execution slot*, not an account-wide battle
lock. Waiting records live beside it. Moving a record into/out of that slot is
one atomic public-state update, so all existing per-step send journals remain
scoped to exactly one expedition, including after a process dies mid-request.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Dict

BRUSH_ACTIVE_FIELD = "brushPendingRecoveryJson"
BRUSH_WAITING_FIELD = "brushWaitingRecoveriesJson"
BRUSH_CONSUMED_FIELD = "brushConsumedTargetsJson"
# At least the longest bandit-cache lifetime. Fresh game scans may rediscover
# survivors, but an old available cache row is never a new target.
BRUSH_CONSUMED_TTL_MILLIS = 6 * 60 * 60 * 1000


def _object(value: Any, *, field: str) -> Dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError(f"{field} 不是有效的刷黄账本对象")
    return deepcopy(value)


def brush_record_key(record: Dict[str, Any]) -> str:
    existing = str(record.get("recoveryKey") or "").strip()
    if existing:
        return existing
    # Stable identity for an old single-record ledger. Never use its changing
    # poll time, observed state or newly arrived battleId as the identity.
    identity = {
        key: record.get(key)
        for key in ("createdAtMillis", "generalIds", "formationId", "targetId")
    }
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return "legacy:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def brush_consumed_targets(public: Dict[str, Any], now: int) -> Dict[str, int]:
    raw = _object(public.get(BRUSH_CONSUMED_FIELD), field=BRUSH_CONSUMED_FIELD)
    return {
        str(key): int(value) for key, value in raw.items()
        if int(value) + BRUSH_CONSUMED_TTL_MILLIS >= now
    }


def brush_consumed_target_update(
    public: Dict[str, Any], record: Dict[str, Any], now: int,
) -> Dict[str, str]:
    """Commit with a receipt, and migrate old/uncertain ledgers before release."""
    if record.get("sendState") not in {"accepted", "uncertain", "sending", "target-missing"}:
        return {}
    target_id = int(record.get("targetId") or (record.get("target") or {}).get("id") or 0)
    if target_id <= 0:
        return {}
    targets = brush_consumed_targets(public, now)
    seen_at = int(
        record.get("acceptedAtMillis") or record.get("sendingAtMillis")
        or record.get("createdAtMillis") or now
    )
    targets[str(target_id)] = max(int(targets.get(str(target_id)) or 0), seen_at)
    return {BRUSH_CONSUMED_FIELD: json.dumps(targets, ensure_ascii=False)}


def brush_record_general_ids(record: Dict[str, Any]) -> set[int]:
    """Unknown ownership must block dispatch, never mean 'owns nobody'."""
    raw = record.get("generalIds")
    if not isinstance(raw, list) or not raw:
        return set()
    try:
        ids = {int(value) for value in raw}
    except (ValueError, TypeError, OverflowError):
        return set()
    return ids if all(value > 0 for value in ids) else set()


def brush_recovery_records(public: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    waiting = _object(public.get(BRUSH_WAITING_FIELD), field=BRUSH_WAITING_FIELD)
    records: Dict[str, Dict[str, Any]] = {}
    for key, value in waiting.items():
        if not isinstance(value, dict) or not value or not str(key).strip():
            raise ValueError("刷黄等待账本包含无法识别的记录")
        record = deepcopy(value)
        if record.get("recoveryKey") not in (None, "", key):
            raise ValueError("刷黄等待账本的记录身份不一致")
        record["recoveryKey"] = key
        records[key] = record
    active = _object(public.get(BRUSH_ACTIVE_FIELD), field=BRUSH_ACTIVE_FIELD)
    if active:
        key = brush_record_key(active)
        active["recoveryKey"] = key
        if key in records and records[key] != active:
            raise ValueError("刷黄执行槽与等待账本存在冲突，禁止覆盖")
        records[key] = active
    return records


def brush_lane_storage_updates(
    records: Dict[str, Dict[str, Any]], active_key: str
) -> Dict[str, str]:
    if active_key not in records:
        raise ValueError("要接管的刷黄账本不存在")
    return {
        BRUSH_ACTIVE_FIELD: json.dumps(records[active_key], ensure_ascii=False),
        BRUSH_WAITING_FIELD: json.dumps(
            {key: value for key, value in records.items() if key != active_key},
            ensure_ascii=False,
        ),
    }


def brush_skip_heal_update(
    state: Dict[str, Any], pending: Dict[str, Any], reason: str
) -> Dict[str, Any]:
    """An adjudicated heal must not be consumed by a different idle team."""
    scoped = dict(state.get("skipHealForGenerals") or {})
    scoped.update({str(general_id): reason for general_id in brush_record_general_ids(pending)})
    return {
        "skipHealOnce": True,  # Compatibility summary for older host views.
        "skipHealReason": reason,
        "skipHealForGenerals": scoped,
    }


def brush_lane_notices(public: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Keep a blocked formation visible while its siblings keep running."""
    try:
        records = brush_recovery_records(public)
    except (ValueError, TypeError):
        return [{
            "key": "brush-lane:invalid", "feature": "brushYellow",
            "title": "刷黄账本需检查", "summary": "刷黄分编队账本不可读，禁止新出征",
            "message": "刷黄分编队账本不可读，禁止新出征", "severity": "error",
        }]
    notices = []
    for key, record in records.items():
        wait = record.get("resourceWait") or {}
        if not wait and not record.get("requiresAttention"):
            continue
        label = (
            f"编队{record['formationNumber']}" if record.get("formationNumber")
            else "将领" + ",".join(map(str, sorted(brush_record_general_ids(record))))
        )
        message = str(
            wait.get("message") or record.get("lastError")
            or record.get("dispatchError") or record.get("preDispatchError")
            or record.get("lastDecisionReason") or "出征结果尚未结清，禁止重复派遣"
        )
        notices.append({
            "key": f"brush-lane:{key}", "feature": "brushYellow",
            "title": f"刷黄{label}等待资源" if wait else f"刷黄{label}需核对",
            "summary": message, "message": message,
            "severity": "warning" if wait else "error",
            "advice": "只保留该编队的将领占用；不影响其他独立编队。",
            "createdAt": int(wait.get("sinceMillis") or record.get("createdAtMillis") or 0),
            "updatedAt": int(record.get("updatedAtMillis") or record.get("createdAtMillis") or 0),
            "nextRetryAt": int(
                wait.get("retryAtMillis") or record.get("nextPollAtMillis") or 0
            ),
        })
    return notices
