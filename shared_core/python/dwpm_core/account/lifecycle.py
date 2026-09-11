"""Account lifecycle, failure evidence and reconnect decisions.

These rules used to be split between the desktop reconnect worker and Android
Kotlin.  Hosts may keep their own process/service mechanics, but must ask this
module whether a session is usable, when it needs probing, and how a failure is
classified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


ONLINE = "online"
CHECKING = "checking"
NETWORK_PAUSED = "network_paused"
NEED_RELOGIN = "need_relogin"
OFFLINE = "offline"
STOPPED = "stopped"

FAILURE_NETWORK = "network"
FAILURE_SERVER = "server"
FAILURE_THROTTLE = "throttle"
FAILURE_UNKNOWN = "unknown"
FAILURE_KINDS = frozenset(
    (FAILURE_NETWORK, FAILURE_SERVER, FAILURE_THROTTLE, FAILURE_UNKNOWN)
)

DEFAULT_STATUS_TEXT = {
    ONLINE: "开启",
    CHECKING: "检测中",
    OFFLINE: "掉线",
    STOPPED: "未开启",
}

SESSION_INVALID_MARKERS = (
    "0x8016",
    "没有角色信息",
    "沒有角色信息",
    "明确拒绝登录态",
    "已确认会话失效",
    "登录态已失效",
    "登录/心跳拒绝帧",
    "captured-compact-0xfffc-login-heartbeat",
    "response-opcode-0x8016",
)

NETWORK_FAILURE_MARKERS = (
    "timed out",
    "timeout",
    "超时",
    "connection reset",
    "connection refused",
    "remote end closed",
    "network is unreachable",
    "no route to host",
    "temporary failure",
    "name or service not known",
    "连接失败",
    "无法连接",
    "http=0",
    "http 0",
    "http=502",
    "http=503",
    "http=504",
    "http 502",
    "http 503",
    "http 504",
    "bytes=0",
    "响应0字节",
    "socks连接游戏服失败",
    "broken pipe",
)

NETWORK_FAILURE_NEGATIONS = (
    "不是网络",
    "并非网络",
    "非网络",
    "未归因为网络",
    "没有网络故障",
    "没有明确网络",
    "非网络故障",
)

NETWORK_FAILURE_PHRASES = (
    "网络连接中断",
    "网络请求暂时失败",
    "网络请求失败",
    "网络问题失败",
    "网络不可达",
    "网络超时",
    "断网",
)

SERVER_FAILURE_MARKERS = (
    "游戏服登录失败",
    "登录态已失效",
    "明确拒绝登录态",
    "拒绝登录",
    "封禁",
    "封号",
    "认证失败",
    "鉴权失败",
    "未授权",
    "forbidden",
    "unauthorized",
    "http=401",
    "http=403",
    "http 401",
    "http 403",
    "0x8016",
    "没有角色信息",
    "沒有角色信息",
    "captured-compact-0xfffc-login-heartbeat",
    "response-opcode-0x8016",
)

RECONNECT_BACKOFF_MINUTES = {
    FAILURE_NETWORK: (3, 5, 10),
    FAILURE_SERVER: (10, 20, 30),
    FAILURE_THROTTLE: (3, 5, 10),
    FAILURE_UNKNOWN: (3, 5, 10),
}

FAILURE_KIND_LABELS = {
    FAILURE_SERVER: "服务器明确登录态拒绝",
    FAILURE_NETWORK: "网络连接故障",
    FAILURE_THROTTLE: "服务器限流",
    FAILURE_UNKNOWN: "响应未确认/协议异常",
}


@dataclass(frozen=True)
class AccountLifecyclePolicy:
    """Immutable policy loaded from the shared behavior contract."""

    started_requires_execution_owner: bool = True
    heartbeat_interval_millis: int = 20_000
    session_validation_interval_millis: int = 60_000
    session_probe_read_timeout_millis: int = 8_000
    session_state_fallback_read_timeout_millis: int = 20_000
    probe_failure_pause_threshold: int = 3
    probe_failure_relogin_threshold: int = 4
    degraded_probe_retry_millis: int = 5_000
    successful_response_refresh_min_interval_millis: int = 5_000
    status_texts: Mapping[str, str] = field(
        default_factory=lambda: dict(DEFAULT_STATUS_TEXT)
    )

    def __post_init__(self) -> None:
        texts = dict(self.status_texts or DEFAULT_STATUS_TEXT)
        missing = set(DEFAULT_STATUS_TEXT) - set(texts)
        if missing:
            raise ValueError(
                "account lifecycle status text is missing: "
                + ", ".join(sorted(missing))
            )
        if int(self.heartbeat_interval_millis) <= 0:
            raise ValueError("account lifecycle heartbeat interval must be positive")
        if int(self.session_validation_interval_millis) <= 0:
            raise ValueError(
                "account lifecycle session validation interval must be positive"
            )
        if int(self.session_probe_read_timeout_millis) <= 0:
            raise ValueError("account lifecycle probe timeout must be positive")
        if int(self.session_state_fallback_read_timeout_millis) <= 0:
            raise ValueError(
                "account lifecycle state fallback timeout must be positive"
            )
        if int(self.probe_failure_pause_threshold) < 2:
            raise ValueError(
                "account lifecycle probe pause threshold must be at least two"
            )
        if int(self.probe_failure_relogin_threshold) <= int(
            self.probe_failure_pause_threshold
        ):
            raise ValueError(
                "account lifecycle probe relogin threshold must exceed pause threshold"
            )
        if int(self.degraded_probe_retry_millis) <= 0:
            raise ValueError(
                "account lifecycle degraded probe retry must be positive"
            )
        if int(self.successful_response_refresh_min_interval_millis) <= 0:
            raise ValueError(
                "account lifecycle response refresh interval must be positive"
            )
        object.__setattr__(self, "status_texts", texts)

    @classmethod
    def from_behavior_contract(
        cls,
        contract: Mapping[str, Any],
    ) -> "AccountLifecyclePolicy":
        lifecycle = contract.get("accountLifecycle")
        if not isinstance(lifecycle, Mapping):
            raise ValueError("account lifecycle behavior contract is missing")
        texts = lifecycle.get("statusText")
        if not isinstance(texts, Mapping):
            raise ValueError("account lifecycle status text is missing")
        return cls(
            started_requires_execution_owner=bool(
                lifecycle.get("startedRequiresExecutionOwner", True)
            ),
            heartbeat_interval_millis=int(
                lifecycle.get("heartbeatIntervalMillis") or 0
            ),
            session_validation_interval_millis=int(
                lifecycle.get("sessionValidationIntervalMillis")
                or lifecycle.get("heartbeatIntervalMillis")
                or 0
            ),
            session_probe_read_timeout_millis=int(
                lifecycle.get("sessionProbeReadTimeoutMillis") or 0
            ),
            session_state_fallback_read_timeout_millis=int(
                lifecycle.get("sessionStateFallbackReadTimeoutMillis") or 0
            ),
            probe_failure_pause_threshold=int(
                lifecycle.get("probeFailurePauseThreshold") or 0
            ),
            probe_failure_relogin_threshold=int(
                lifecycle.get("probeFailureReloginThreshold") or 0
            ),
            degraded_probe_retry_millis=int(
                lifecycle.get("degradedProbeRetryMillis") or 0
            ),
            successful_response_refresh_min_interval_millis=int(
                lifecycle.get("successfulResponseRefreshMinIntervalMillis")
                or 0
            ),
            status_texts={str(key): str(value) for key, value in texts.items()},
        )

    def presentation(
        self,
        *,
        account_enabled: bool,
        execution_owner_active: bool,
        login_state: Any,
    ) -> dict[str, Any]:
        state = normalize_login_state(login_state)
        owner_missing = (
            bool(account_enabled)
            and self.started_requires_execution_owner
            and not bool(execution_owner_active)
        )
        started = bool(account_enabled) and (
            not self.started_requires_execution_owner
            or bool(execution_owner_active)
        )
        if owner_missing:
            status = STOPPED
        elif state == CHECKING:
            status = CHECKING
        elif state in (OFFLINE, NEED_RELOGIN, NETWORK_PAUSED):
            status = OFFLINE
        elif not account_enabled or state == STOPPED:
            status = STOPPED
        else:
            status = ONLINE
        return {
            "status": status,
            "statusText": self.status_texts[status],
            "started": started,
        }

    def should_probe(
        self,
        *,
        login_state: Any,
        force_validation: bool,
        last_validated_at_millis: Optional[int],
        now_millis: int,
    ) -> bool:
        state = normalize_login_state(login_state)
        if force_validation or state in (NETWORK_PAUSED, CHECKING):
            return True
        if state != ONLINE:
            return False
        if last_validated_at_millis is None:
            return True
        return (
            int(now_millis) - int(last_validated_at_millis)
            >= int(self.session_validation_interval_millis)
        )

    def snapshot(
        self,
        *,
        account_enabled: bool,
        execution_owner_active: bool,
        login_state: Any,
        source_mode: int,
        force_validation: bool = False,
        last_validated_at_millis: Optional[int] = None,
        now_millis: int = 0,
    ) -> dict[str, Any]:
        presentation = self.presentation(
            account_enabled=account_enabled,
            execution_owner_active=execution_owner_active,
            login_state=login_state,
        )
        usable = (
            int(source_mode) == 1
            and presentation["started"]
            and presentation["status"] == ONLINE
        )
        return {
            **presentation,
            "canonicalLoginState": normalize_login_state(login_state),
            "requiresRelogin": requires_relogin(login_state),
            "shouldProbe": self.should_probe(
                login_state=login_state,
                force_validation=force_validation,
                last_validated_at_millis=last_validated_at_millis,
                now_millis=now_millis,
            ),
            "mayUseLiveSession": usable,
            "runnable": usable,
            "heartbeatIntervalMillis": int(self.heartbeat_interval_millis),
            "sessionValidationIntervalMillis": int(
                self.session_validation_interval_millis
            ),
        }


def normalize_login_state(value: Any) -> str:
    state = str(value or "").strip().upper()
    if "CHECK" in state:
        return CHECKING
    if "NEED_RELOGIN" in state:
        return NEED_RELOGIN
    if "NETWORK_PAUSED" in state:
        return NETWORK_PAUSED
    if "OFFLINE" in state or "DISCONNECT" in state:
        return OFFLINE
    if "STOP" in state or not state:
        return STOPPED
    if "ONLINE" in state:
        return ONLINE
    # Unknown persisted states are never proof of a usable live Session.
    return OFFLINE


def requires_relogin(login_state: Any) -> bool:
    return normalize_login_state(login_state) in (NEED_RELOGIN, OFFLINE)


def is_session_invalid_message(message: Any) -> bool:
    text = str(message or "").lower()
    return any(marker in text for marker in SESSION_INVALID_MARKERS)


def is_network_failure_message(message: Any) -> bool:
    text = str(message or "").lower()
    if any(marker in text for marker in NETWORK_FAILURE_MARKERS):
        return True
    if any(marker in text for marker in NETWORK_FAILURE_NEGATIONS):
        return False
    return any(marker in text for marker in NETWORK_FAILURE_PHRASES)


def classify_reconnect_failure(
    message: Any,
    *,
    session_invalid: bool = False,
) -> str:
    if session_invalid:
        return FAILURE_SERVER
    text = str(message or "").lower()
    if any(marker in text for marker in SERVER_FAILURE_MARKERS):
        return FAILURE_SERVER
    if "http 429" in text or "http=429" in text or "服务器限流" in text:
        return FAILURE_THROTTLE
    if is_network_failure_message(text):
        return FAILURE_NETWORK
    return FAILURE_UNKNOWN


def reconnect_kind_label(kind: Any) -> str:
    return FAILURE_KIND_LABELS.get(
        str(kind or "").strip().lower(),
        FAILURE_KIND_LABELS[FAILURE_UNKNOWN],
    )


def reconnect_delay_millis(kind: Any, failure_count: int) -> int:
    normalized = str(kind or "").strip().lower()
    delays = RECONNECT_BACKOFF_MINUTES.get(
        normalized,
        RECONNECT_BACKOFF_MINUTES[FAILURE_UNKNOWN],
    )
    index = max(0, min(int(failure_count) - 1, len(delays) - 1))
    return int(delays[index]) * 60 * 1000
