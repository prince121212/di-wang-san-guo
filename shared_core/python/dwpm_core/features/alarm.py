"""Pure military-alarm classification and durable deduplication rules."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Mapping, Sequence


DEFAULT_INCOMING_KEYWORDS = ("掠夺", "夺取", "攻城", "敌军", "来袭")
INCOMING_MODES = frozenset(("声音+日志", "仅日志", "关闭"))
MILITARY_MODES = frozenset(("出征/返回", "仅来袭", "全部"))


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _names(value: Any, default: Sequence[str] = ()) -> list[str]:
    raw = value if isinstance(value, (list, tuple, set)) else re.split(
        r"[,，;；|\s]+", str(value or "")
    )
    result = list(dict.fromkeys(
        str(item or "").strip()
        for item in raw
        if str(item or "").strip()
    ))
    return result or list(default)


def normalize_alarm_policy(value: Mapping[str, Any] | None) -> Dict[str, Any]:
    raw = dict(value or {})
    incoming_mode = str(raw.get("incomingMode") or "声音+日志")
    if incoming_mode not in INCOMING_MODES:
        incoming_mode = "声音+日志"
    military_mode = str(raw.get("militaryMode") or "出征/返回")
    if military_mode not in MILITARY_MODES:
        military_mode = "出征/返回"
    incoming_enabled = _truthy(
        raw.get("incomingEnabled"), True
    ) and incoming_mode != "关闭"
    military_enabled = _truthy(raw.get("militaryEnabled"), True)
    error_enabled = _truthy(raw.get("errorEnabled"), True)
    return {
        "enabled": bool(incoming_enabled or military_enabled),
        "incomingEnabled": incoming_enabled,
        "incomingMode": incoming_mode,
        "incomingKeywords": _names(
            raw.get("incomingKeywords")
            or raw.get("keywords")
            or raw.get("alarm_keywords"),
            DEFAULT_INCOMING_KEYWORDS,
        ),
        "militaryEnabled": military_enabled,
        "militaryMode": military_mode,
        "errorEnabled": error_enabled,
        "vibrateOnAlarm": _truthy(
            raw.get("vibrateOnAlarm", raw.get("alarm_vibrate")), True
        ),
    }


def alarm_policy_hash(policy: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        normalize_alarm_policy(policy),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def alarm_event_fingerprint(action: Mapping[str, Any]) -> str:
    incoming = bool(action.get("incoming")) or str(
        action.get("state") or ""
    ) == "来袭"
    if incoming and int(action.get("recordId") or 0) > 0:
        identity = {
            "kind": "incoming",
            "recordId": int(action.get("recordId") or 0),
            "eventTimeMs": int(action.get("eventTimeMs") or 0),
            "attackerName": str(action.get("attackerName") or ""),
            "targetId": int(action.get("targetId") or 0),
            "actionType": int(action.get("actionType") or 0),
        }
    elif int(action.get("battleId") or 0) > 0:
        identity = {
            "kind": "military",
            "battleId": int(action.get("battleId") or 0),
            "state": str(action.get("state") or ""),
            "direction": str(action.get("direction") or ""),
            "targetId": int(action.get("targetId") or 0),
            "generalIds": sorted(
                int(value)
                for value in action.get("generalIds") or []
                if str(value).lstrip("-").isdigit()
            ),
        }
    else:
        identity = {
            "kind": "incoming" if incoming else "military",
            "time": str(
                action.get("eventTimeMs")
                or action.get("timeText")
                or action.get("time")
                or ""
            ),
            "state": str(action.get("state") or ""),
            "text": str(action.get("text") or ""),
        }
    return _canonical_hash(identity)


def _military_mode_matches(
    mode: str,
    state: str,
    text: str,
    direction: str,
) -> bool:
    if mode == "仅来袭":
        return False
    if mode == "全部":
        return True
    combined = "|".join((state, text, direction))
    return any(marker in combined for marker in (
        "出征", "返回", "行军", "征", "返", "outgoing", "return",
    ))


def detect_alarm_events(
    snapshot: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    now_millis: int,
) -> list[Dict[str, Any]]:
    normalized = normalize_alarm_policy(policy)
    if not normalized["enabled"]:
        return []
    rows = snapshot.get("actions")
    if not isinstance(rows, list):
        rows = snapshot.get("events")
    rows = rows if isinstance(rows, list) else []
    output: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for value in rows:
        if not isinstance(value, Mapping):
            continue
        action = dict(value)
        text = str(action.get("text") or "").strip()
        if not text:
            continue
        state = str(action.get("state") or "").strip()
        direction = str(action.get("direction") or "").strip()
        structured_incoming = bool(action.get("incoming")) or state == "来袭"
        keyword_incoming = any(
            keyword in text for keyword in normalized["incomingKeywords"]
        )
        incoming = bool(normalized["incomingEnabled"]) and (
            structured_incoming or keyword_incoming
        )
        military = bool(normalized["militaryEnabled"]) and (
            _military_mode_matches(
                str(normalized["militaryMode"]), state, text, direction
            )
        )
        kind = "incoming" if incoming else "military" if military else ""
        if not kind:
            continue
        fingerprint = alarm_event_fingerprint(action)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        show_notification = not (
            kind == "incoming"
            and normalized["incomingMode"] in {"仅日志", "关闭"}
        )
        vibrate = bool(
            show_notification and normalized["vibrateOnAlarm"]
        )
        output.append({
            "schemaVersion": 1,
            "type": "military-alarm",
            "kind": kind,
            "title": "来袭警报" if kind == "incoming" else "军情提醒",
            "message": text,
            "text": text,
            "fingerprint": fingerprint,
            "showNotification": show_notification,
            "vibrate": vibrate,
            "createdAtMillis": int(now_millis),
            "source": "shared-military-snapshot",
            "action": action,
        })
    return output


def plan_alarm_observation(
    snapshot: Mapping[str, Any],
    policy: Mapping[str, Any],
    state: Mapping[str, Any] | None,
    *,
    now_millis: int,
    fingerprint_limit: int = 200,
) -> Dict[str, Any]:
    normalized = normalize_alarm_policy(policy)
    current_events = detect_alarm_events(
        snapshot, normalized, now_millis=now_millis
    )
    limit = max(1, min(int(fingerprint_limit), 2_000))
    current_fingerprints = [
        str(event["fingerprint"]) for event in current_events[:limit]
    ]
    current_hash = alarm_policy_hash(normalized)
    previous = dict(state or {})
    baseline_required = (
        not bool(previous.get("baselineInitialized"))
        or str(previous.get("configHash") or "") != current_hash
    )
    previous_fingerprints = {
        str(value)
        for value in (
            previous.get("seenFingerprints")
            or previous.get("currentFingerprints")
            or []
        )
        if str(value or "").strip()
    }
    new_events = [] if baseline_required else [
        event
        for event in current_events
        if str(event["fingerprint"]) not in previous_fingerprints
    ]
    if baseline_required:
        seen_fingerprints = current_fingerprints
    else:
        seen_fingerprints = list(dict.fromkeys([
            *[
                str(value)
                for value in (
                    previous.get("seenFingerprints")
                    or previous.get("currentFingerprints")
                    or []
                )
                if str(value or "").strip()
            ],
            *current_fingerprints,
        ]))[-limit:]
    updated = dict(previous)
    updated.update({
        "configHash": current_hash,
        "baselineInitialized": True,
        "currentFingerprints": current_fingerprints,
        "seenFingerprints": seen_fingerprints,
        "lastObservedAtMillis": int(now_millis),
        "lastObservedCount": len(current_events),
        "lastNewEventCount": len(new_events),
        "lastState": "baseline" if baseline_required else (
            "completed" if new_events else "waiting"
        ),
    })
    return {
        "baselineEstablished": baseline_required,
        "events": new_events,
        "currentEvents": current_events,
        "detectedCount": len(current_events),
        "state": updated,
    }


def plan_error_alarm(
    policy: Mapping[str, Any],
    state: Mapping[str, Any] | None,
    message: str,
    *,
    source: str,
    now_millis: int,
    dedupe_millis: int = 300_000,
    fingerprint_limit: int = 50,
) -> Dict[str, Any]:
    normalized = normalize_alarm_policy(policy)
    updated = dict(state or {})
    text = str(message or "").strip()
    if not text or not bool(normalized["errorEnabled"]):
        return {"event": None, "state": updated, "reason": "disabled"}
    fingerprint = _canonical_hash({
        "kind": "error",
        "source": str(source or "host"),
        "message": text,
    })
    threshold = int(now_millis) - max(1_000, int(dedupe_millis))
    recent = [
        dict(value)
        for value in updated.get("recentErrors") or []
        if isinstance(value, Mapping)
        and int(value.get("atMillis") or 0) >= threshold
    ]
    if any(str(value.get("fingerprint") or "") == fingerprint for value in recent):
        updated["recentErrors"] = recent[-max(1, int(fingerprint_limit)):]
        return {"event": None, "state": updated, "reason": "deduplicated"}
    recent.append({"fingerprint": fingerprint, "atMillis": int(now_millis)})
    updated["recentErrors"] = recent[-max(1, int(fingerprint_limit)):]
    event = {
        "schemaVersion": 1,
        "type": "task-error-alarm",
        "kind": "error",
        "title": "任务异常",
        "message": text,
        "text": text,
        "fingerprint": fingerprint,
        "showNotification": True,
        "vibrate": bool(normalized["vibrateOnAlarm"]),
        "createdAtMillis": int(now_millis),
        "source": str(source or "host"),
    }
    return {"event": event, "state": updated, "reason": "new-error"}
