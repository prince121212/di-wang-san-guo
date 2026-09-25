"""Pure recovery policy: resource waits are feature-scoped, not account stops."""

from __future__ import annotations

from typing import Any, Dict, Optional


RESOURCE_RETRY_MIN_MILLIS = 60_000
RESOURCE_RETRY_MAX_MILLIS = 15 * 60_000
HEAL_RESOURCE_FAILURE_CODES = frozenset({
    "TROOP_HEAL_COPPER_FLOOR_FOOD_SHORTAGE",
    "TROOP_HEAL_RECOVERY_FOOD_SHORTAGE",
    "TROOP_HEAL_COPPER_SHORTAGE",
    "TROOP_HEAL_RESOURCE_EXCHANGE_REJECTED",
    "TROOP_HEAL_RESOURCE_STATE_UNAVAILABLE",
})


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def copper_recovery_food_amount(current_copper: int, required_copper: int) -> int:
    """Cover the quoted deficit at 10,000 food -> 3,000 copper.

    A refusal can contradict a stale/unspecified quote. In that case allow one
    bounded legacy recovery amount, never an in-tick conversion loop.
    """

    deficit = max(0, int(required_copper) - int(current_copper))
    return ((deficit + 2999) // 3000) * 10_000 if deficit else 100_000


def is_heal_resource_failure(code: str, message: str) -> bool:
    return code in HEAL_RESOURCE_FAILURE_CODES or (
        code == "TROOP_HEAL_REJECTED" and "铜钱不足" in message
    )


def resource_wait_result(
    feature: str,
    code: str,
    message: str,
    *,
    now_millis: int,
    previous: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """A confirmed resource failure gets a bounded retry and a durable notice.

    No uncertain outcome belongs here. Older ledgers called an explicit
    insufficient-copper receipt TROOP_HEAL_REJECTED; accept that known shape
    without treating every rejected action as a resource shortage.
    """

    if not is_heal_resource_failure(code, message):
        return None
    previous = previous if isinstance(previous, dict) else {}
    wait = previous.get("resourceWait")
    wait = wait if isinstance(wait, dict) else {}
    attempts = min(1000, max(0, _integer(wait.get("attempts"))) + 1)
    delay = min(
        RESOURCE_RETRY_MAX_MILLIS,
        RESOURCE_RETRY_MIN_MILLIS * (2 ** min(attempts - 1, 4)),
    )
    retry_at = int(now_millis) + delay
    since = _integer(wait.get("sinceMillis"), int(now_millis))
    summary = (
        f"{message}；本功能将在{delay // 60_000}分钟后重新检查，"
        "其他任务继续运行"
    )
    return {
        "feature": "brushYellow" if feature == "brush" else feature,
        "state": "waiting-resources",
        "success": False,
        "requiresAttention": False,
        "errorCode": code,
        "message": summary,
        "nextWakeAtMillis": retry_at,
        "taskNextWakeAtMillis": retry_at,
        "resourceWait": {
            "sinceMillis": since,
            "updatedAtMillis": int(now_millis),
            "retryAtMillis": retry_at,
            "attempts": attempts,
            "errorCode": code,
            "message": summary,
        },
    }


def resource_wait_notices(
    state: Dict[str, Any], labels: Dict[str, str]
) -> list[Dict[str, Any]]:
    """Project current resource waits; log retention cannot hide a live issue."""

    notices = []
    for feature, value in state.items():
        if not isinstance(value, dict):
            continue
        wait = value.get("resourceWait")
        if (
            value.get("lastState") != "waiting-resources"
            or not isinstance(wait, dict)
            or not wait.get("message")
        ):
            continue
        public_feature = "brushYellow" if feature == "brush" else feature
        label = labels.get(feature, feature)
        since = _integer(wait.get("sinceMillis"))
        notices.append({
            "key": f"resource:{public_feature}:{since}",
            "feature": public_feature,
            "title": f"{label}等待资源",
            "summary": str(wait["message"]),
            "message": str(wait["message"]),
            "severity": "warning",
            "advice": "检查铜钱和粮食储备；后台会按退避时间重试，不影响其他任务。",
            "createdAt": since,
            "updatedAt": _integer(wait.get("updatedAtMillis"), since),
            "nextRetryAt": _integer(wait.get("retryAtMillis")),
        })
    return sorted(notices, key=lambda item: item["createdAt"], reverse=True)


def pending_business_progress(value: Any) -> Any:
    """Discard observations and retry bookkeeping, retaining actual step state.

    A new receipt, settled step, cursor or battle is progress. Updating a
    timestamp, error message or retry counter is not, including inside nested
    per-general/per-fief step journals.
    """

    observational_keys = {
        "lastError", "lastErrorCode", "requiresAttention",
        "nextPollAtMillis", "isolatedUntilMillis", "resourceWait",
    }
    if isinstance(value, dict):
        return {
            key: pending_business_progress(child)
            for key, child in value.items()
            if key not in observational_keys and not key.endswith("AtMillis")
        }
    if isinstance(value, list):
        return [pending_business_progress(child) for child in value]
    return value
