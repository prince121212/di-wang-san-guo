"""Deterministic account and Session lifecycle reducer.

The reducer performs no I/O.  Hosts report an observed event, persist the
returned public state, and execute only the requested next operation through
the shared per-account network lane.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from .lifecycle import (
    CHECKING,
    FAILURE_UNKNOWN,
    NEED_RELOGIN,
    NETWORK_PAUSED,
    OFFLINE,
    ONLINE,
    STOPPED,
    classify_reconnect_failure,
    normalize_login_state,
    reconnect_delay_millis,
)


EVENT_USER_START = "USER_START"
EVENT_USER_STOP = "USER_STOP"
EVENT_LOGIN_SUCCEEDED = "LOGIN_SUCCEEDED"
EVENT_LOGIN_FAILED = "LOGIN_FAILED"
EVENT_PROBE_VALID = "PROBE_VALID"
EVENT_SESSION_EXPIRED = "SESSION_EXPIRED"
EVENT_PROBE_UNAVAILABLE = "PROBE_UNAVAILABLE"
EVENT_NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"
EVENT_PROCESS_RECOVERED = "PROCESS_RECOVERED"

ACCOUNT_EVENTS = frozenset(
    (
        EVENT_USER_START,
        EVENT_USER_STOP,
        EVENT_LOGIN_SUCCEEDED,
        EVENT_LOGIN_FAILED,
        EVENT_PROBE_VALID,
        EVENT_SESSION_EXPIRED,
        EVENT_PROBE_UNAVAILABLE,
        EVENT_NETWORK_UNAVAILABLE,
        EVENT_PROCESS_RECOVERED,
    )
)

HOST_LOGIN_STATES = {
    ONLINE: "REAL_PROTOCOL_ONLINE",
    CHECKING: "REAL_PROTOCOL_CHECKING",
    NETWORK_PAUSED: "REAL_PROTOCOL_NETWORK_PAUSED",
    NEED_RELOGIN: "REAL_PROTOCOL_NEED_RELOGIN",
    OFFLINE: "REAL_PROTOCOL_OFFLINE",
    STOPPED: "REAL_PROTOCOL_STOPPED",
}

DEFAULT_PROBE_FAILURE_PAUSE_THRESHOLD = 3
DEFAULT_PROBE_FAILURE_RELOGIN_THRESHOLD = 4
DEFAULT_DEGRADED_PROBE_RETRY_MILLIS = 5_000


def reduce_account_event(
    state: Mapping[str, Any],
    event: str,
    *,
    now_millis: int,
    details: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the only allowed next account lifecycle state."""

    if not isinstance(state, Mapping):
        raise ValueError("account transition state must be an object")
    normalized_event = str(event or "").strip().upper()
    if normalized_event not in ACCOUNT_EVENTS:
        raise ValueError(f"unsupported account event: {normalized_event}")
    observed = dict(details or {})
    now = max(0, int(now_millis))
    desired_started = _bool(
        state.get(
            "desiredStarted",
            state.get("enabled", state.get("started", False)),
        )
    )
    session_present = _bool(
        state.get(
            "sessionCredentialPresent",
            state.get("sessionPresent", int(state.get("sourceMode") or 0) == 1),
        )
    )
    current_kind = str(state.get("failureKind") or "").strip().lower()
    current_count = max(0, int(state.get("failureCount") or 0))
    current_login = normalize_login_state(state.get("loginState"))
    output = {
        "desiredStarted": desired_started,
        "loginState": HOST_LOGIN_STATES[current_login],
        "sessionCredentialPresent": session_present,
        "liveSessionUsable": bool(
            desired_started and session_present and current_login == ONLINE
        ),
        "failureKind": current_kind,
        "failureCount": current_count,
        "nextRetryAtMillis": _optional_nonnegative_int(
            state.get("nextRetryAtMillis")
        ),
        "lastError": _safe_message(state.get("lastError")),
        "lastValidatedAtMillis": _optional_nonnegative_int(
            state.get("lastValidatedAtMillis")
        ),
        "nextOperation": "none",
        "sessionSecretAction": "retain",
        "event": normalized_event,
        "updatedAtMillis": now,
    }

    if normalized_event == EVENT_USER_START:
        output.update(
            desiredStarted=True,
            loginState=HOST_LOGIN_STATES[CHECKING],
            liveSessionUsable=False,
            nextRetryAtMillis=None,
            lastError="",
            nextOperation="login",
        )
        return output

    if normalized_event == EVENT_USER_STOP:
        output.update(
            desiredStarted=False,
            loginState=HOST_LOGIN_STATES[STOPPED],
            liveSessionUsable=False,
            nextRetryAtMillis=None,
            nextOperation="none",
        )
        return output

    if normalized_event in (EVENT_LOGIN_SUCCEEDED, EVENT_PROBE_VALID):
        output.update(
            desiredStarted=True,
            loginState=HOST_LOGIN_STATES[ONLINE],
            sessionCredentialPresent=True,
            liveSessionUsable=True,
            failureKind="",
            failureCount=0,
            nextRetryAtMillis=None,
            lastError="",
            lastValidatedAtMillis=_optional_nonnegative_int(
                observed.get("validatedAtMillis")
            ) or now,
            nextOperation="none",
        )
        return output

    if normalized_event == EVENT_NETWORK_UNAVAILABLE:
        output.update(
            loginState=HOST_LOGIN_STATES[NETWORK_PAUSED],
            liveSessionUsable=False,
            nextRetryAtMillis=None,
            lastError=_safe_message(
                observed.get("message") or "当前网络不可用"
            ),
            nextOperation="wait-network",
        )
        return output

    if normalized_event == EVENT_SESSION_EXPIRED:
        output.update(
            desiredStarted=True,
            loginState=HOST_LOGIN_STATES[NEED_RELOGIN],
            liveSessionUsable=False,
            nextRetryAtMillis=now,
            lastError=_safe_message(
                observed.get("message") or "Session 已失效"
            ),
            nextOperation="login",
            # Retain only as restart/relogin evidence; lifecycle gates make it
            # unusable for game actions.
            sessionSecretAction="retain",
        )
        return output

    message = _safe_message(observed.get("message") or "账号状态未确认")
    session_invalid = _bool(observed.get("sessionInvalid"))
    failure_kind = classify_reconnect_failure(
        message,
        session_invalid=session_invalid,
    )
    failure_count = (
        current_count + 1
        if current_kind == failure_kind
        else 1
    )
    retry_at = now + reconnect_delay_millis(failure_kind, failure_count)

    if normalized_event == EVENT_LOGIN_FAILED:
        output.update(
            desiredStarted=True,
            loginState=HOST_LOGIN_STATES[OFFLINE],
            sessionCredentialPresent=False,
            liveSessionUsable=False,
            failureKind=failure_kind,
            failureCount=failure_count,
            nextRetryAtMillis=retry_at,
            lastError=message,
            nextOperation="login",
            sessionSecretAction="delete",
        )
        return output

    if normalized_event == EVENT_PROBE_UNAVAILABLE:
        pause_threshold = max(
            2,
            int(
                observed.get("probeFailurePauseThreshold")
                or DEFAULT_PROBE_FAILURE_PAUSE_THRESHOLD
            ),
        )
        degraded_retry_millis = max(
            1,
            int(
                observed.get("degradedProbeRetryMillis")
                or DEFAULT_DEGRADED_PROBE_RETRY_MILLIS
            ),
        )
        relogin_threshold = max(
            pause_threshold + 1,
            int(
                observed.get("probeFailureReloginThreshold")
                or DEFAULT_PROBE_FAILURE_RELOGIN_THRESHOLD
            ),
        )
        if (
            current_login == ONLINE
            and session_present
            and failure_count < pause_threshold
        ):
            # A timeout is absence of liveness evidence, not evidence that a
            # previously valid Session has expired. Keep the account usable
            # while two short confirmation attempts run; explicit Android
            # connectivity loss still uses EVENT_NETWORK_UNAVAILABLE and
            # pauses immediately.
            output.update(
                desiredStarted=True,
                loginState=HOST_LOGIN_STATES[ONLINE],
                liveSessionUsable=True,
                failureKind=failure_kind,
                failureCount=failure_count,
                nextRetryAtMillis=now + degraded_retry_millis,
                lastError=message,
                nextOperation="probe-degraded",
            )
            return output
        if (
            session_present
            and failure_kind == "network"
            and failure_count >= relogin_threshold
        ):
            # Android connectivity and a reachable TCP port do not prove that
            # an authenticated game HTTP session is still capable of serving
            # requests. After one full paused retry also fails, probing the
            # same half-dead session cannot create new evidence. Scheduler
            # actions are already stopped, so a credential-backed fresh login
            # is the only progress-making and replay-safe recovery operation.
            output.update(
                desiredStarted=True,
                loginState=HOST_LOGIN_STATES[NEED_RELOGIN],
                sessionCredentialPresent=True,
                liveSessionUsable=False,
                failureKind=failure_kind,
                failureCount=failure_count,
                nextRetryAtMillis=now + degraded_retry_millis,
                lastError=message,
                nextOperation="login",
                sessionSecretAction="retain",
            )
            return output
        # The first failure which actually pauses the account starts at the
        # first network backoff step. The two degraded confirmation attempts
        # must not turn that first pause into the old ten-minute third step.
        pause_failure_count = max(
            1,
            failure_count - pause_threshold + 1,
        )
        output.update(
            desiredStarted=True,
            loginState=HOST_LOGIN_STATES[NETWORK_PAUSED],
            liveSessionUsable=False,
            failureKind=failure_kind,
            failureCount=failure_count,
            nextRetryAtMillis=(
                now
                + reconnect_delay_millis(
                    failure_kind,
                    pause_failure_count,
                )
            ),
            lastError=message,
            nextOperation="probe",
        )
        return output

    if normalized_event == EVENT_PROCESS_RECOVERED:
        persisted_retry_at = _optional_nonnegative_int(
            state.get("nextRetryAtMillis")
        )
        if not desired_started:
            output.update(
                loginState=HOST_LOGIN_STATES[STOPPED],
                liveSessionUsable=False,
                nextRetryAtMillis=None,
                nextOperation="none",
            )
        elif persisted_retry_at is not None and persisted_retry_at > now:
            output.update(
                loginState=HOST_LOGIN_STATES[
                    NETWORK_PAUSED if session_present else NEED_RELOGIN
                ],
                liveSessionUsable=False,
                nextRetryAtMillis=persisted_retry_at,
                nextOperation="wait-retry",
            )
        elif session_present:
            output.update(
                loginState=HOST_LOGIN_STATES[CHECKING],
                liveSessionUsable=False,
                nextRetryAtMillis=None,
                nextOperation="probe",
            )
        else:
            output.update(
                loginState=HOST_LOGIN_STATES[NEED_RELOGIN],
                liveSessionUsable=False,
                nextRetryAtMillis=now,
                nextOperation="login",
            )
        return output

    raise AssertionError(f"unhandled account event: {normalized_event}")


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _optional_nonnegative_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized >= 0 else None


def _safe_message(value: Any) -> str:
    return str(value or "").replace("\x00", "")[:500]
