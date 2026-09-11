"""Shared account-card projection from host facts and canonical account state."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Mapping, Optional

from .lifecycle import AccountLifecyclePolicy


def project_account_cards(
    records: Iterable[Mapping[str, Any]],
    runtime_by_account: Mapping[str, Mapping[str, Any]],
    lifecycle: AccountLifecyclePolicy,
    *,
    execution_owner_active: bool,
    now_millis: int,
    account_refs: Optional[Iterable[str]] = None,
) -> list[Dict[str, Any]]:
    """Build the one public account-card shape used by both hosts."""

    requested = (
        {str(value).strip() for value in account_refs if str(value).strip()}
        if account_refs is not None
        else None
    )
    runtime = {
        str(key): _mapping(value)
        for key, value in _mapping(runtime_by_account).items()
    }
    output = []
    for raw_record in records:
        record = _mapping(raw_record)
        account_ref = str(
            record.get("accountRef") or record.get("id") or ""
        ).strip()
        if not account_ref or (requested is not None and account_ref not in requested):
            continue
        output.append(
            _project_account_card(
                record,
                runtime.get(account_ref, {}),
                lifecycle,
                execution_owner_active=execution_owner_active,
                now_millis=now_millis,
            )
        )
    return output


def _project_account_card(
    record: Dict[str, Any],
    runtime: Dict[str, Any],
    lifecycle: AccountLifecyclePolicy,
    *,
    execution_owner_active: bool,
    now_millis: int,
) -> Dict[str, Any]:
    account_ref = str(record.get("accountRef") or record.get("id"))
    session = _mapping(record.get("session"))
    public_state = _mapping(session.get("publicState"))
    reconnect = _mapping(runtime.get("reconnect"))
    last_validated = _optional_int(public_state.get("lastValidatedAt"))
    state = lifecycle.snapshot(
        account_enabled=bool(record.get("enabled")),
        execution_owner_active=bool(execution_owner_active),
        login_state=str(record.get("loginState") or ""),
        source_mode=_int(session.get("sourceMode"), 0),
        force_validation=False,
        last_validated_at_millis=last_validated,
        now_millis=int(now_millis),
    )
    retry_value = _optional_int(reconnect.get("nextAttemptAtMillis"))
    retry_at = retry_value if retry_value is not None and retry_value > 0 else None
    checked_at = _first_int(
        public_state.get("lastHeartbeatAt"),
        public_state.get("lastValidatedAt"),
    )
    last_error = _first_text(
        public_state.get("lastReloginError"),
        public_state.get("lastOfflineReason"),
        public_state.get("lastNetworkPauseReason"),
        reconnect.get("reason"),
    )
    task_overview = _mapping(runtime.get("taskOverview"))
    username = str(record.get("username") or "")
    server_name = str(record.get("serverName") or "")
    display_name = record.get("displayName")
    if display_name is None:
        display_name = f"{username}@{server_name}"
    has_live_session = bool(state["mayUseLiveSession"])
    card = {
        "sessionId": account_ref,
        "username": username,
        "displayName": display_name,
        "serverQuery": server_name,
        "areaName": server_name,
        "roleName": (
            record.get("monarchName")
            if record.get("monarchName") is not None
            else record.get("displayName")
        ),
        "level": _optional_int(public_state.get("level")),
        "status": state["status"],
        "statusText": state["statusText"],
        "started": bool(state["started"]),
        "desiredStarted": bool(record.get("enabled")),
        "hasLiveSession": has_live_session,
        "lastHeartbeat": (
            {
                "online": state["status"] == "online",
                "message": "在线" if state["status"] == "online" else last_error,
                "checkedAt": checked_at,
            }
            if checked_at is not None
            else None
        ),
        "lastError": last_error,
        "reconnectState": (
            "countdown"
            if retry_at is not None and retry_at > int(now_millis)
            else ""
        ),
        "reconnectAt": retry_at,
        "reconnectRemainingSec": (
            max(0, retry_at - int(now_millis) + 999) // 1000
            if retry_at is not None
            else 0
        ),
        "accountHabits": _json_copy(runtime.get("accountHabits") or {}),
        # The nested session shape is reserved for a currently usable live
        # session.  Cached account fields remain available on the card itself,
        # but must not make a stopped/offline account look actionable to either
        # host UI.
        "session": (
            _json_copy(runtime.get("session"))
            if has_live_session and isinstance(runtime.get("session"), Mapping)
            else None
        ),
        "recentGameRequests": _list(runtime.get("recentGameRequests")),
        "dailyStats": _json_copy(runtime.get("dailyStats") or {}),
        "taskStack": _list(task_overview.get("taskStack")),
        "notices": _list(task_overview.get("notices")),
    }
    host_presentation = _mapping(runtime.get("presentation"))
    for key in (
        "platform",
        "platformKey",
        "serial",
        "createdAt",
        "startedAt",
        "localOnly",
        "hasStoredPassword",
        "proxyGroup",
        "proxyNode",
        "proxyMode",
        "proxyIp",
        "proxyStatus",
        "proxyError",
        "proxyCheckedAt",
        "networkDegraded",
        "responseUnconfirmed",
        "heartbeatNetworkFailureCount",
        "heartbeatUnconfirmedFailureCount",
    ):
        if key in record:
            card[key] = _json_copy(record[key])
        elif key in host_presentation:
            card[key] = _json_copy(host_presentation[key])
    return card


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return _json_copy(value) if isinstance(value, list) else []


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_int(*values: Any) -> Optional[int]:
    for value in values:
        parsed = _optional_int(value)
        if parsed is not None:
            return parsed
    return None


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "")
        if text:
            return text
    return ""


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))
