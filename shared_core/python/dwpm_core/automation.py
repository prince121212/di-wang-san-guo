"""Pure resident-task recovery reducers shared by desktop and Android.

The reducers never perform I/O. They consume durable pending facts plus a fresh
Python-parsed state snapshot and return the only permitted next action. Keeping
these decisions separate makes deadline/tick scheduling deterministic and keeps
Android from rebuilding task semantics in Kotlin.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable


_DAY_MILLIS = 86_400_000
_CHINA_OFFSET_MILLIS = 8 * 60 * 60 * 1000

#: How long a self-recoverable block waits before the scheduler retries it.
BLOCKED_RETRY_MILLIS = 5 * 60 * 1000

#: A due candidate unselected for this long jumps the priority queue once.
STARVATION_THRESHOLD_MILLIS = 10 * 60 * 1000
# A bounded slice of an unfinished sweep is not a new periodic job.  Giving it
# the normal ten-minute aging interval made five swords take fifty minutes.
# It still yields between slices; military work keeps its normal priority.
CONTINUATION_STARVATION_MILLIS = 10_000

#: How far past its own deadline a candidate must fall before the scheduler
#: reports it as stalled.  This is a health signal, never a scheduling input:
#: it exists so a feature that loses every tick says so itself, rather than
#: being inferred hours later from records that never appeared.
STALL_REPORT_MILLIS = 15 * 60 * 1000

#: States in which a feature asked to stop rather than to be rescheduled.
BLOCKED_STATES = frozenset({"blocked", "defeat-paused"})

#: How many coordinates 刷黄 must scan without a single filter match before
#: the operator is told the filter itself is the problem.
#:
#: "暂时没有目标" and "筛选条件在这个区里几乎选不出目标" are two different
#: facts that both surface as a no-targets tick; only accumulated evidence
#: tells them apart.  The scan space defaults to 80 coordinates scanned in
#: batches of 5, so 75 is fifteen batches - just under one full round - which
#: is the point where "nobody happened to match yet" stops being plausible.
#: The count resets when the filter fingerprint changes (the operator already
#: adjusted) and when any target matches (the filter demonstrably produces).
BRUSH_FILTER_ADVICE_MIN_SCANNED_COORDS = 75

#: Resident states worth announcing, and how each reads to the operator.
#:
#: The panel has one job: answer "它在做什么，卡住了吗".  A success record answers
#: the first half.  This table answers the second, and only for states where the
#: honest answer is "nothing, and here is why" -- ``running``/``fighting`` need no
#: announcement because the success record that follows is the real news.
#:
#: ``{reason}`` is filled from the feature's own last message when it has one.
NARRATED_STATES = {
    "blocked": "{label}已暂停：{reason}",
    "defeat-paused": "{label}因战败暂停：{reason}",
    "no-targets": "{label}暂时没有可打的目标，稍后自动重试",
    # A request whose outcome is unknown stops its own feature until the next
    # cycle rather than risk repeating it.  That is a decision the operator
    # lives with for hours, so it is the clearest case of "nothing is
    # happening, and here is why".
    "uncertain": "{label}已暂停：{reason}",
    # The account holds as many resource points as the server allows.  Like a
    # block this is a conclusion held until the count falls, not a sample, so
    # it is announced at once; leaving it says "已恢复运行" like any other.
    "capacity-full": "{label}已暂停：{reason}",
    # A general cannot march for want of a resource the game replenishes or
    # the account holder supplies - stamina with no 活血丹, or fewer idle
    # troops than the saved formation asks for.  The feature holds until a
    # named deadline and then tries again by itself.  It used to surface only
    # as "存在未确认操作，已隔离并禁止自动重发，请人工核对" when the failing
    # preflight happened to follow a sent heal; the honest line names the
    # general, the shortfall and what would end the pause.
    "formation-paused": "{label}已暂停：{reason}",
    "waiting-resources": "{label}等待资源：{reason}",
    "waiting-dependency": "{label}等待共享地图：{reason}",
    # Crossing BRUSH_FILTER_ADVICE_MIN_SCANNED_COORDS without a match is a
    # conclusion drawn from accumulated evidence, not one scan's sample, so it
    # is announced at once and is not in SAMPLED_STATES.  The reason carries
    # the 【建议】 marker both hosts use to raise a dismissible notice.
    # Leaving the state (a target matched) says "已恢复运行" like any other.
    "filter-strict": "{label}{reason}",
}

#: Narrated states that are a *sample* rather than a *decision*.
#:
#: A stop is a conclusion the feature reached and will hold until something
#: changes, so it is announced the moment it happens -- waiting to confirm it
#: risks never announcing it at all, since a stopped feature may not be ticked
#: again.  "No targets" is the opposite: it is what one scan happened to see,
#: and re-scanning flips it back and forth.  Those are announced only once the
#: condition has actually persisted, so a flap produces no line at all.
SAMPLED_STATES = frozenset({"no-targets"})

#: What is said when a feature leaves any state in :data:`NARRATED_STATES`.
RESUMED_TEMPLATE = "{label}已恢复运行"

#: How long a sampled state must persist before it is worth announcing.
#:
#: 刷黄 re-samples "有没有目标" every few seconds, so it flipped between
#: no-targets and running six times in four minutes one morning.  Each flip is a
#: real state change and would make a truthful line; all six together tell the
#: operator nothing, because the condition never changed - it was looked at
#: again.  Requiring a minute of persistence drops that burst entirely and keeps
#: the genuine quiet spells.
NARRATION_MIN_HOLD_MILLIS = 60 * 1000

#: Names for the resident features as the operator knows them.
#:
#: Kept beside the feature vocabulary itself so that anything narrated to a user
#: is named from one table.  A feature absent here is simply never narrated,
#: which is why this is a lookup with no fallback: a fallback would leak the
#: internal key ("domestic") into the panel the moment someone adds a feature.
FEATURE_LABELS = {
    "mine": "打矿",
    "brush": "刷黄",
    "raid": "掠夺",
    "lossless": "无损",
    "dungeon": "副本",
    "general": "将领维护",
    "ministry": "六部",
    "domestic": "内政",
    "inventory": "背包整理",
    "alarm": "军情警报",
    "captives": "俘虏",
}

#: Names for the daily tasks, which schedule themselves independently.
#:
#: 日常 is absent from :data:`FEATURE_LABELS` on purpose: it is not one feature
#: with one state but seven, each with its own cycle and its own stop reason,
#: so "日常已暂停" would name none of them.  A daily task that blocks itself
#: for a whole cycle used to be narrated as nothing at all.
DAILY_FEATURE_LABELS = {
    "autoSignIn": "签到",
    "arenaCoins": "领币",
    "autoDonate": "捐献",
    "salary": "俸禄",
    "nationalCollect": "国征",
    "cityLordCollect": "城征",
    "generalVisit": "拜访",
}

#: How long a block with an unrecognized error code waits before one retry.
#:
#: Such a block used to remove the feature from the candidate set *forever*,
#: with no expiry and nothing to re-evaluate it: 副本 sat out four days on a
#: preflight that had sent nothing at all.  Failing closed here was also
#: redundant, because replay safety does not live in this reducer.  A mutation
#: whose outcome is unknown is caught by the send-boundary probe, which
#: isolates the feature from the pending path *and* from the configured path
#: (``configured_allowed`` subtracts the isolated set).  So an unrecognized
#: code waits six times longer than a known-safe one and is reported on every
#: tick - but it can no longer become permanently invisible.
UNRECOGNIZED_BLOCK_RETRY_MILLIS = 30 * 60 * 1000

#: 撤防 send states that crossed the wire without confirming themselves.
#:
#: These are not ambiguous *mutations* - the request named one exact battle, so
#: it can only ever have withdrawn that one - they are requests whose answer
#: has to be read off the generals instead of the receipt.
_RECALL_UNSETTLED_STATES = frozenset(
    ("sending", "uncertain", "rejected", "sent-unconfirmed")
)

#: Blocked outcomes whose failing check provably sent no expedition packet, so
#: retrying them is known-safe and uses the short backoff.
AUTO_RETRY_BLOCK_CODES = frozenset({
    "EXPEDITION_ENERGY_NOT_READY",
    "EXPEDITION_GENERAL_BUSY",
    "EXPEDITION_TROOPS_NOT_READY",
    "EXPEDITION_POST_PREFLIGHT_MISSING",
    "EXPEDITION_FORMATION_RULE_MISSING",
})


def _add_resident_candidate(
    candidates: list[Dict[str, Any]],
    blocked: list[Dict[str, Any]],
    state: Dict[str, Any],
    *,
    feature: str,
    priority: Any,
    now: int,
    earliest: int | None = None,
) -> None:
    """Turn one feature's stored state into a candidate, a block, or neither.

    ``nextWakeAtMillis`` is nullable and was carrying three meanings in one
    slot: *when* to look again, *whether* to look automatically at all, and "I
    have no opinion".  The shared workflows return ``None`` from a blocked
    branch to mean "stop, a human must look", while this scheduler read the
    very same ``None`` as "due right now".  A blocked feature therefore
    competed on every tick, lost on priority, and was never selected again -
    silently, because it never ran and so never logged.  Those are separate
    questions and they get separate answers here.

    This function is pure, and that is load-bearing rather than stylistic.  An
    earlier fix disambiguated ``None`` by writing a deadline back into
    ``state``, which made correctness depend on the caller persisting it - and
    one of the two callers does not.  Anchoring the retry on
    ``blockedAtMillis`` instead makes the deadline a fixed instant that is
    identical however many times it is computed, so nothing has to be stored.
    Deriving it from ``now`` would instead anchor it to *the moment someone
    looked*, producing a target that recedes exactly as fast as the clock.

    "A human must look" is read from ``requiresAttention``, not from the state
    being spelled "blocked".  Recognising a stop by its name meant every new
    name reopened the same hole: 副本 stops as ``clear-unconfirmed`` after
    three unconfirmed clears, which is not in :data:`BLOCKED_STATES`, so it
    fell through to "due now" and competed on every single tick.  One feature
    coming to a halt must never cost the others their lane, and that has to
    hold for halts nobody has named yet.
    """
    explicit = state.get("nextWakeAtMillis")
    if explicit is None:
        last_state = str(state.get("lastState") or "").strip()
        if last_state in BLOCKED_STATES or bool(
            state.get("requiresAttention")
        ):
            code = str(state.get("lastErrorCode") or "").strip()
            if last_state == "defeat-paused":
                # Not a fault whose cause expires: the user asked to stop after
                # a defeat and there is an explicit acknowledgement path.
                # Resuming on a timer would restart the losing loop they paused.
                blocked.append({
                    "feature": feature,
                    "reason": "awaiting-acknowledgement",
                    "errorCode": code,
                    "state": last_state,
                    "message": str(state.get("lastMessage") or ""),
                })
                return
            recognized = code in AUTO_RETRY_BLOCK_CODES
            blocked.append({
                "feature": feature,
                "reason": (
                    "self-recoverable" if recognized else "requires-attention"
                ),
                "errorCode": code,
                "state": last_state,
                "message": str(state.get("lastMessage") or ""),
            })
            blocked_at = int(state.get("blockedAtMillis") or 0)
            # No recorded block instant means state written before this field
            # existed.  Such a feature has been stuck for an unknown, possibly
            # very long time on a cause that has probably resolved, so the
            # useful answer is "retry now", not "wait out a fresh backoff".
            if blocked_at <= 0:
                explicit = int(now)
            else:
                explicit = blocked_at + (
                    BLOCKED_RETRY_MILLIS
                    if recognized
                    else UNRECOGNIZED_BLOCK_RETRY_MILLIS
                )
        else:
            # Never ran, or finished without asking for a deadline: due now.
            explicit = int(now)
    due = int(explicit)
    if earliest is not None:
        due = max(due, int(earliest))
    candidates.append({
        "feature": feature,
        "dueAtMillis": due,
        "priority": int(priority or 0),
        "lastServedAtMillis": int(state.get("lastServedAtMillis") or 0),
        "continuationPending": bool(state.get(
            "continuationPending",
            # V99 persisted the unfinished cycle but not a continuation flag.
            # Upgrading must not leave that existing backlog waiting ten minutes.
            feature == "inventory"
            and str(state.get("lastState") or "") == "completed"
            and int(state.get("cycleActionCount") or 0) > 0,
        ))
        and str(state.get("lastState") or "") in {"completed", "retry", "waiting"}
        and not bool(state.get("requiresAttention")),
    })


def _positive_ids(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []
    output = []
    for value in values:
        try:
            item = int(value)
        except (TypeError, ValueError):
            continue
        if item > 0 and item not in output:
            output.append(item)
    return output


def _general_id(value: Dict[str, Any]) -> int:
    try:
        return int(value.get("id") or 0)
    except (TypeError, ValueError):
        return 0


def general_is_idle(value: Dict[str, Any]) -> bool:
    """Accept only explicit idle evidence; unknown never means idle."""

    for key in ("statusText", "displayStatus", "state"):
        text = str(value.get(key) or "").strip()
        if text:
            return text == "闲"
    try:
        return int(value.get("status")) == 0
    except (TypeError, ValueError):
        return False


def general_is_garrisoned(value: Dict[str, Any]) -> bool:
    """Accept only explicit garrison evidence; unknown never means garrisoned.

    Mirrors :func:`general_is_idle`, and is the fact a 撤防 is judged by: the
    request names one exact battle, so the only open question afterwards is
    whether the troops are still holding the point.  A general that has left
    "防" has left it because the withdrawal took effect - nothing else moves a
    garrison - which makes this a stronger answer than the receipt, and one
    that does not depend on any offset inside a response packet.
    """

    for key in ("statusText", "displayStatus", "state"):
        text = str(value.get(key) or "").strip()
        if text:
            return text in {"防", "驻守"}
    try:
        return int(value.get("status")) == 2
    except (TypeError, ValueError):
        return False


def china_day_key(now_millis: int) -> int:
    """Return a stable UTC+8 day key without relying on host timezone data."""

    return (int(now_millis) + _CHINA_OFFSET_MILLIS) // _DAY_MILLIS


def china_start_millis(day_key: int, hour: int) -> int:
    normalized_hour = max(0, min(23, int(hour)))
    return (
        int(day_key) * _DAY_MILLIS
        - _CHINA_OFFSET_MILLIS
        + normalized_hour * 60 * 60 * 1000
    )


def china_clock_text(now_millis: int) -> str:
    """Return ``HH:MM`` in UTC+8 for user-facing "暂停至" style messages."""

    minute_of_day = (
        (int(now_millis) + _CHINA_OFFSET_MILLIS) % _DAY_MILLIS
    ) // 60_000
    return f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


#: Pre-dispatch states that prove no mutation is waiting to be adjudicated.
#:
#: ``pending`` is the *initial* state: the mutation never began.  ``failed``
#: means it was attempted and did not take effect.  Both are settled facts.
SETTLED_PRE_DISPATCH_STATES = frozenset({"", "pending", "failed"})


def pre_dispatch_outstanding(record: Dict[str, Any]) -> bool:
    """True only when a preflight mutation may still have taken effect.

    This question was never named, so five workflows each answered it with
    their own hand-written set of state strings - and every one of those sets
    listed ``pending``, the state that means *nothing has happened yet*.  A
    real account's 副本 sat blocked with ``preDispatchMutationState=pending``
    and ``preDispatchMutationCount=0``, holding the pending lane while 刷黄
    starved twenty minutes and 将领维护 sixteen.  Fixing one site left four.

    The answer follows from evidence, not from which label the record happens
    to carry: a mutation is outstanding when the record says one is in flight
    (``sending``/``uncertain``), or landed and may not have been recorded
    (``accepted``), or when a send was counted despite a settled label.  An
    unrecognised label fails closed.
    """

    state = str(record.get("preDispatchMutationState") or "").strip()
    try:
        sends = int(record.get("preDispatchMutationCount") or 0)
    except (TypeError, ValueError):
        sends = 0
    if state in {"sending", "uncertain", "accepted"}:
        return True
    if state in SETTLED_PRE_DISPATCH_STATES:
        # A counted send contradicts the settled label; trust the count.
        return sends > 0 and state != "failed"
    return True


def overdue_candidates(
    candidates: Iterable[Dict[str, Any]],
    *,
    now_millis: int,
    threshold_millis: int = STALL_REPORT_MILLIS,
) -> list[Dict[str, Any]]:
    """Name the features that are due but keep losing, worst first.

    Every stall so far had the same signature - a feature whose own deadline
    passed long ago while some other lane kept winning the tick - and every one
    of them was found by a person noticing missing records hours or days later.
    The due-set is already computed on each tick, so the scheduler can state
    this itself for free.
    """

    now = int(now_millis)
    threshold = max(0, int(threshold_millis))
    overdue = []
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        try:
            due_at = int(candidate.get("dueAtMillis"))
        except (TypeError, ValueError):
            continue
        late = now - due_at
        if late < threshold:
            continue
        overdue.append({
            "feature": str(candidate.get("feature") or ""),
            "dueAtMillis": due_at,
            "overdueMillis": late,
        })
    overdue.sort(key=lambda row: -int(row["overdueMillis"]))
    return overdue


def ambiguous_preflight_reconciliation(
    pending: Dict[str, Any],
    generals: Iterable[Dict[str, Any]],
    *,
    formal_send_states: Iterable[str],
    now_millis: int,
    poll_millis: int,
    retry_millis: int,
) -> Dict[str, Any]:
    """Resolve a preflight whose mutation outcome is unknown, by observation.

    A process killed mid-send leaves ``preDispatchMutationState`` at
    ``sending``: the heal, top-up or troop assignment may or may not have
    landed.  Treating that as "a human must decide" is a conclusion, and it is
    one the game itself can settle - every preflight mutation is preceded by a
    fresh read, so once the selected generals are back to idle the world is in
    a known state again and the next attempt re-derives what it needs from it.

    The rule is only safe while *nothing formal* was sent.  A prepare, a
    dispatch, a chest or a settlement that crossed the boundary changes the
    world in a way no observation here can undo, so those still stop.

    刷黄 has carried this reconciliation for a while; 副本 never got one, so a
    single interrupted heal left it isolated indefinitely while every other
    feature kept running.  Stating it once, feature-neutrally, is what stops
    the next expedition workflow from having the same hole.
    """

    for key in formal_send_states:
        if str(pending.get(key) or "") not in {"", "not-sent"}:
            return {
                "action": "isolate",
                "reason": f"{key} 已越过发送边界，禁止自动结清",
            }
    selected = _positive_ids(pending.get("generalIds"))
    if not selected:
        return {"action": "isolate", "reason": "账本没有记录出征将领"}
    by_id = {
        _general_id(row): dict(row)
        for row in generals
        if isinstance(row, dict) and _general_id(row) > 0
    }
    missing = [value for value in selected if value not in by_id]
    if missing:
        return {
            "action": "wait",
            "reason": "最新状态未找到出征将领："
            + ",".join(str(value) for value in missing),
            "nextWakeAtMillis": int(now_millis) + max(1_000, int(poll_millis)),
        }
    busy = [value for value in selected if not general_is_idle(by_id[value])]
    if busy:
        return {
            "action": "wait",
            "reason": "出征将领尚未全部回闲："
            + ",".join(str(value) for value in busy),
            "nextWakeAtMillis": int(now_millis) + max(1_000, int(poll_millis)),
        }
    return {
        "action": "reconcile",
        "reason": (
            "最新只读状态确认将领全部回闲，且预出征/正式出征/开箱均未发送；"
            "旧的不确定前置账本已归档，下一轮跳过一次治疗"
        ),
        "skipHealOnce": True,
        "nextWakeAtMillis": int(now_millis) + max(1_000, int(retry_millis)),
    }


def resident_due_decision(
    configs: Dict[str, Any],
    state: Dict[str, Any],
    *,
    now_millis: int,
    saved_tasks_started: bool,
    active_keys: set[str],
    priorities: Dict[str, Any],
) -> Dict[str, Any]:
    """Choose the only configured resident task which may run this tick."""

    now = int(now_millis)
    updated = dict(state or {})
    day_key = china_day_key(now)
    brush_state = dict(updated.get("brush") or {})
    if int(
        brush_state.get("dayKey")
        if brush_state.get("dayKey") is not None
        else -1
    ) != day_key:
        brush_state.update({"dayKey": day_key, "usedCount": 0})
    updated["brush"] = brush_state
    updated["mine"] = dict(updated.get("mine") or {})
    # Mine coordination is now device-local. Retire only the obsolete cloud
    # dependency, never an uncertain expedition or resource/formation wait.
    mine_wait = updated["mine"].get("dependencyWait") or {}
    if mine_wait.get("dependency") == "cloud-map":
        updated["mine"].pop("dependencyWait", None)
        if updated["mine"].get("lastState") == "waiting-dependency":
            updated["mine"].update({"lastState": "ready", "nextWakeAtMillis": now,
                                    "lastErrorCode": "", "lastMessage": "打矿使用本机共享地图"})
    updated["mine"]["mapMode"] = "LOCAL_ONLY"
    updated["raid"] = dict(updated.get("raid") or {})
    updated["lossless"] = dict(updated.get("lossless") or {})
    dungeon_state = dict(updated.get("dungeon") or {})
    if int(
        dungeon_state.get("dayKey")
        if dungeon_state.get("dayKey") is not None
        else -1
    ) != day_key:
        dungeon_state.update({"dayKey": day_key, "usedCount": 0})
    updated["dungeon"] = dungeon_state
    updated["general"] = dict(updated.get("general") or {})
    updated["ministry"] = dict(updated.get("ministry") or {})
    updated["domestic"] = dict(updated.get("domestic") or {})
    updated["inventory"] = dict(updated.get("inventory") or {})
    updated["alarm"] = dict(updated.get("alarm") or {})
    updated["captives"] = dict(updated.get("captives") or {})
    if not saved_tasks_started:
        return {
            "feature": None,
            "reason": "saved-tasks-not-started",
            "nextWakeAtMillis": None,
            "state": updated,
        }

    candidates: list[Dict[str, Any]] = []
    blocked: list[Dict[str, Any]] = []
    mine = dict(configs.get("mine") or {})
    mine_rows = [
        dict(row)
        for row in mine.get("rows") or []
        if isinstance(row, dict) and row.get("enabled") is True
    ]
    if bool(mine.get("enabled")) and mine_rows and "mine" in active_keys:
        _add_resident_candidate(
            candidates,
            blocked,
            updated["mine"],
            feature="mine",
            priority=priorities.get("mine"),
            now=now,
        )

    common = dict(configs.get("common") or {})
    brush = dict(common.get("brush") or {})
    brush_rules = [
        dict(row)
        for row in brush.get("rules") or []
        if isinstance(row, dict) and row.get("enabled") is True
    ]
    if (
        bool(common.get("autoStart"))
        and brush_rules
        and "brushYellow" in active_keys
    ):
        start_hour = max(0, min(23, int(common.get("startHour") or 0)))
        daily_limit = max(1, int(common.get("dailyLimit") or 500))
        today_start = china_start_millis(day_key, start_hour)
        earliest = today_start if now < today_start else None
        if int(brush_state.get("usedCount") or 0) >= daily_limit:
            tomorrow_start = china_start_millis(day_key + 1, start_hour)
            earliest = max(earliest or 0, tomorrow_start)
        _add_resident_candidate(
            candidates,
            blocked,
            brush_state,
            feature="brush",
            priority=priorities.get("brushYellow"),
            now=now,
            earliest=earliest,
        )

    raid = dict(configs.get("raid") or {})
    raid_rows = [
        dict(row)
        for row in raid.get("rows") or []
        if isinstance(row, dict) and row.get("enabled") is True
    ]
    if bool(raid.get("enabled")) and raid_rows and "raid" in active_keys:
        _add_resident_candidate(
            candidates,
            blocked,
            updated["raid"],
            feature="raid",
            priority=priorities.get("raid"),
            now=now,
        )

    lossless = dict(configs.get("lossless") or {})
    lossless_rows = [
        dict(row)
        for row in lossless.get("rows") or []
        if isinstance(row, dict) and row.get("enabled") is True
    ]
    if (
        bool(lossless.get("enabled"))
        and lossless_rows
        and "lossless" in active_keys
    ):
        _add_resident_candidate(
            candidates,
            blocked,
            updated["lossless"],
            feature="lossless",
            priority=priorities.get("lossless"),
            now=now,
        )

    dungeon = dict(configs.get("dungeon") or {})
    dungeon_rows = [
        dict(row)
        for row in dungeon.get("rows") or []
        if isinstance(row, dict) and row.get("enabled") is True
    ]
    if (
        bool(dungeon.get("enabled"))
        and dungeon_rows
        and "dungeon" in active_keys
    ):
        dungeon_settings = dict(dungeon.get("settings") or {})
        daily_times = max(1, int(dungeon_settings.get("dailyTimes") or 999))
        earliest = None
        if int(dungeon_state.get("usedCount") or 0) >= daily_times:
            earliest = china_start_millis(day_key + 1, 0)
        _add_resident_candidate(
            candidates,
            blocked,
            dungeon_state,
            feature="dungeon",
            priority=priorities.get("dungeon"),
            now=now,
            earliest=earliest,
        )

    general = dict(configs.get("general") or {})
    if bool(general.get("enabled")) and "general" in active_keys:
        _add_resident_candidate(
            candidates,
            blocked,
            updated["general"],
            feature="general",
            priority=priorities.get("general"),
            now=now,
        )

    ministry = dict(configs.get("ministry") or {})
    if bool(ministry.get("enabled")) and "ministry" in active_keys:
        _add_resident_candidate(
            candidates,
            blocked,
            updated["ministry"],
            feature="ministry",
            priority=priorities.get("ministry"),
            now=now,
        )

    domestic = dict(configs.get("domestic") or {})
    if bool(domestic.get("active")) and "domestic" in active_keys:
        _add_resident_candidate(
            candidates,
            blocked,
            updated["domestic"],
            feature="domestic",
            priority=priorities.get("domestic"),
            now=now,
        )

    inventory = dict(configs.get("inventory") or {})
    if bool(inventory.get("enabled")) and "inventory" in active_keys:
        _add_resident_candidate(
            candidates,
            blocked,
            updated["inventory"],
            feature="inventory",
            priority=priorities.get("inventory"),
            now=now,
        )

    alarm = dict(configs.get("alarm") or {})
    if bool(alarm.get("enabled")) and "alarm" in active_keys:
        _add_resident_candidate(
            candidates,
            blocked,
            updated["alarm"],
            feature="alarm",
            priority=priorities.get("alarm"),
            now=now,
        )

    captives = dict(configs.get("captives") or {})
    if bool(captives.get("enabled")) and "captives" in active_keys:
        _add_resident_candidate(
            candidates,
            blocked,
            updated["captives"],
            feature="captives",
            priority=priorities.get("captives"),
            now=now,
        )

    if not candidates:
        return {
            "feature": None,
            "reason": (
                "shared-resident-requires-attention"
                if blocked
                else "no-active-shared-resident"
            ),
            "nextWakeAtMillis": None,
            "blocked": blocked,
            "candidates": [],
            "stalled": [],
            "state": updated,
        }
    due = [row for row in candidates if int(row["dueAtMillis"]) <= now]
    if due:
        # Strict priority alone lets a perpetually-due high-priority feature
        # starve every lower one forever.  Aging bounds the worst-case wait
        # without reordering anything that is not actually being starved:
        # priority still decides among equally starved candidates.
        for row in due:
            served = int(row["lastServedAtMillis"] or 0)
            # A feature that has never run is the most starved one there is.
            # Requiring served > 0 here excluded exactly the features that
            # needed the boost most: 将领维护 had never been selected once, so
            # it could never qualify, and 副本 waited on it indefinitely.
            # Treating 0 as "starved" is also safe on a fresh install, where
            # every candidate is starved and plain priority decides again.
            row["starved"] = (
                served <= 0 or now - served >= (
                    CONTINUATION_STARVATION_MILLIS
                    if row.get("continuationPending")
                    else STARVATION_THRESHOLD_MILLIS
                )
            )
        selected = max(
            due,
            key=lambda row: (
                1 if row["starved"] else 0,
                int(row["priority"]),
                -int(row["dueAtMillis"]),
            ),
        )
        return {
            "feature": selected["feature"],
            "dueAtMillis": int(selected["dueAtMillis"]),
            "priority": int(selected["priority"]),
            "starved": bool(selected["starved"]),
            "reason": "configured-feature-due",
            "nextWakeAtMillis": now,
            "blocked": blocked,
            "candidates": [str(row["feature"]) for row in candidates],
            "stalled": overdue_candidates(candidates, now_millis=now),
            "state": updated,
        }
    next_wake = min(int(row["dueAtMillis"]) for row in candidates)
    return {
        "feature": None,
        "reason": "configured-features-waiting",
        "nextWakeAtMillis": next_wake,
        "blocked": blocked,
        "candidates": [str(row["feature"]) for row in candidates],
        "stalled": overdue_candidates(candidates, now_millis=now),
        "state": updated,
    }


def _selected_generals(
    pending: Dict[str, Any],
    generals: Iterable[Dict[str, Any]],
) -> tuple[list[int], list[Dict[str, Any]], list[int]]:
    ids = _positive_ids(pending.get("generalIds"))
    by_id = {
        _general_id(value): dict(value)
        for value in generals
        if isinstance(value, dict) and _general_id(value) > 0
    }
    selected = [by_id[item] for item in ids if item in by_id]
    missing = [item for item in ids if item not in by_id]
    return ids, selected, missing


def brush_recovery_decision(
    pending: Dict[str, Any],
    generals: list[Dict[str, Any]],
    *,
    now_millis: int,
    schedule: Dict[str, Any],
) -> Dict[str, Any]:
    """Reduce one post-dispatch brush recovery observation."""

    ids, selected, missing = _selected_generals(pending, generals)
    created_at = int(pending.get("createdAtMillis") or 0)
    age = max(0, int(now_millis) - created_at)
    poll = max(1_000, int(schedule.get("postDispatchPollMillis") or 30_000))
    grace = max(
        poll,
        int(schedule.get("settlementRecheckGraceMillis") or 300_000),
    )
    # The established desktop brush loop waits for the selected generals to
    # return instead of inventing a fixed battle-duration cutoff.  A deployment
    # may opt into a timeout through the shared contract later, but the absence
    # of that field must preserve the working desktop behavior.
    timeout = max(0, int(schedule.get("settlementTimeoutMillis") or 0))
    if not ids or created_at <= 0:
        return {
            "action": "stop",
            "reason": "刷黄恢复记录缺少将领或创建时间",
            "preservePending": True,
        }
    if timeout > 0 and age > timeout:
        return {
            "action": "stop",
            "reason": f"刷黄战后恢复超过{timeout // 60_000}分钟",
            "preservePending": True,
        }
    if missing:
        return {
            "action": "wait",
            "reason": "新鲜角色状态未找到刷黄将领："
            + ",".join(str(value) for value in missing),
            "nextWakeAtMillis": int(now_millis) + poll,
            "pending": dict(pending),
        }

    busy = [value for value in selected if not general_is_idle(value)]
    updated = dict(pending)
    updated["lastObservedAtMillis"] = int(now_millis)
    updated["lastGeneralStates"] = [
        {
            "id": _general_id(value),
            "status": value.get("status"),
            "statusText": str(
                value.get("statusText")
                or value.get("displayStatus")
                or value.get("state")
                or "未知"
            ),
        }
        for value in selected
    ]
    if busy:
        updated["sawBusy"] = True
        return {
            "action": "wait",
            "reason": "刷黄将领尚未全部回闲",
            "nextWakeAtMillis": int(now_millis) + poll,
            "pending": updated,
        }
    if not bool(updated.get("sawBusy")) and age < grace:
        return {
            "action": "wait",
            "reason": "尚未观察到刷黄忙碌→回闲转换，等待完整刷新宽限期",
            "nextWakeAtMillis": int(now_millis) + poll,
            "pending": updated,
        }
    return {
        "action": "maintain",
        "reason": (
            "刷黄将领已由忙碌转为回闲"
            if updated.get("sawBusy")
            else "完整刷新宽限期后确认将领空闲"
        ),
        "pending": updated,
        "generals": selected,
    }


def mine_garrison_decision(
    pending: Dict[str, Any],
    snapshot: Dict[str, Any],
    generals: list[Dict[str, Any]],
    *,
    now_millis: int,
    schedule: Dict[str, Any],
) -> Dict[str, Any]:
    """Reduce one exact-battle mine garrison/recall observation.

    Whether the expedition took the mine is not knowable from the tick that
    ends the round: by then the generals are simply home, and a lost battle
    looks exactly like a won one whose 撤防 already landed.  The answer only
    exists *while* it is passing by - 军情 says 驻守 once the point is held and
    返回 once the troops turn around - so each observation is accumulated onto
    the record as it happens, and the closing tick reads the verdict off the
    record instead of guessing from the end state.

    Absence of evidence stays absent: a round whose 军情 was never seen (a
    restart, a dropped refresh) closes as ``unknown`` rather than as a loss,
    because reporting a failure that did not happen is worse than saying
    nothing.
    """

    observed = dict(pending)
    try:
        battle_id = int(pending.get("battleId") or 0)
        dispatch_at = int(pending.get("dispatchAtMillis") or 0)
    except (TypeError, ValueError):
        battle_id = 0
        dispatch_at = 0
    ids, selected, missing = _selected_generals(pending, generals)
    poll = max(1_000, int(schedule.get("garrisonPollMillis") or 10_000))
    timeout = max(
        poll,
        int(schedule.get("settlementTimeoutMillis") or 14_400_000),
    )
    grace = max(
        poll,
        int(schedule.get("missingMilitaryGraceMillis") or 120_000),
    )
    age = max(0, int(now_millis) - dispatch_at)
    if battle_id <= 0 or dispatch_at <= 0 or not ids:
        return {
            "action": "stop",
            "reason": "打矿驻守记录缺少 battleId、将领或出征时间",
            "preservePending": True,
        }
    if age > timeout:
        return {
            "action": "stop",
            "reason": f"打矿 battleId={battle_id} 驻守闭环超时",
            "preservePending": True,
        }
    if missing:
        return {
            "action": "wait",
            "reason": "新鲜角色状态未找到打矿将领："
            + ",".join(str(value) for value in missing),
            "nextWakeAtMillis": int(now_millis) + poll,
        }
    all_idle = len(selected) == len(ids) and all(
        general_is_idle(value) for value in selected
    )
    recall_requested = int(pending.get("recallRequestedAtMillis") or 0) > 0
    if recall_requested:
        return {
            "action": "complete" if all_idle else "wait",
            "reason": (
                "撤防后将领已全部回闲"
                if all_idle
                else "撤防已受理，等待将领回闲"
            ),
            # A 撤防 is only ever sent from a confirmed 驻守, so reaching here
            # is itself proof the point was taken.
            "outcome": "recalled" if all_idle else None,
            "pending": observed,
            "nextWakeAtMillis": int(now_millis) + poll,
        }
    if str(pending.get("recallSendState") or "") in _RECALL_UNSETTLED_STATES:
        # A 撤防 whose receipt did not identify itself is not an unknown
        # mutation - it is a known request with an unread answer, and the
        # answer is written on the generals.  Nothing but a withdrawal takes a
        # general out of 防, and the request named one exact battle, so it
        # cannot have moved anyone else's.  Judging it here also removes the
        # reason this used to be unanswerable: the receipt carries a whole
        # 军情 snapshot, its 【返回】 event reports an id that is not the
        # dispatch's, and one real account stopped on that mismatch every
        # single round while the generals had in fact already come home.
        still_holding = [
            value for value in selected if general_is_garrisoned(value)
        ]
        if not still_holding:
            return {
                "action": "complete" if all_idle else "wait",
                "reason": (
                    "撤防已生效，将领已全部回闲"
                    if all_idle
                    else "撤防已生效，将领已离开驻防，等待回闲"
                ),
                "outcome": "recalled" if all_idle else None,
                "pending": {**observed, "recallRequestedAtMillis": int(now_millis)},
                "nextWakeAtMillis": int(now_millis) + poll,
            }
        sent_at = max(
            int(pending.get("recallSendingAtMillis") or 0),
            int(pending.get("recallPreparingAtMillis") or 0),
        )
        if sent_at > 0 and int(now_millis) - sent_at <= grace:
            return {
                "action": "wait",
                "reason": "撤防请求已发送，等待将领离开驻防状态",
                "pending": observed,
                "nextWakeAtMillis": int(now_millis) + poll,
            }
        return {
            "action": "stop",
            "reason": (
                "撤防请求已发送但将领仍在驻防；"
                "禁止自动重发，需先人工/只读状态核对"
            ),
            "preservePending": True,
            "pending": observed,
        }

    action = next(
        (
            dict(value)
            for value in snapshot.get("actions") or []
            if isinstance(value, dict)
            and int(value.get("battleId") or 0) == battle_id
        ),
        None,
    )
    if action is not None:
        expected_x = int(pending.get("x") or 0)
        expected_y = int(pending.get("y") or 0)
        actual_x = int(action.get("x") or 0)
        actual_y = int(action.get("y") or 0)
        if (
            expected_x
            and expected_y
            and (actual_x != expected_x or actual_y != expected_y)
        ):
            return {
                "action": "stop",
                "reason": (
                    f"打矿 battleId={battle_id} 军情坐标不匹配："
                    f"({actual_x},{actual_y}) ≠ ({expected_x},{expected_y})"
                ),
                "preservePending": True,
            }
        action_ids = set(_positive_ids(action.get("generalIds")))
        if action_ids and action_ids.isdisjoint(ids):
            return {
                "action": "stop",
                "reason": f"打矿 battleId={battle_id} 军情将领不匹配",
                "preservePending": True,
            }
        state = str(action.get("state") or "")
        if state == "驻守":
            observed.setdefault("garrisonObservedAtMillis", int(now_millis))
            if bool(pending.get("withdrawDefense")):
                return {
                    "action": "recall",
                    "reason": "已确认目标 battleId 驻守，允许发送撤防",
                    "battle": action,
                    "pending": observed,
                }
            return {
                "action": "complete",
                "reason": "已确认驻守；当前配置不自动撤防",
                "outcome": "garrisoned",
                "pending": observed,
            }
        if state == "返回":
            observed.setdefault("returnObservedAtMillis", int(now_millis))
            return {
                "action": "wait",
                "reason": "军情已显示返回，等待将领回闲",
                "pending": observed,
                "nextWakeAtMillis": int(now_millis) + poll,
            }
        return {
            "action": "wait",
            "reason": f"军情状态={state or '未知'}，继续等待驻守",
            "pending": observed,
            "nextWakeAtMillis": int(now_millis) + poll,
        }

    if all_idle and age >= grace:
        return {
            "action": "complete",
            "reason": "军情缺失超过宽限期，且新鲜状态确认将领全部空闲",
            "outcome": mine_occupation_outcome(observed),
            "pending": observed,
        }
    return {
        "action": "wait",
        "reason": "尚无目标 battleId 军情，继续等待且禁止猜测撤防目标",
        "pending": observed,
        "nextWakeAtMillis": int(now_millis) + poll,
    }


def mine_occupation_outcome(pending: Dict[str, Any]) -> str:
    """Read the verdict a finished mine round accumulated while it ran.

    ``failed`` requires the positive evidence of a 返回 with no 驻守 before it.
    Everything else with no 驻守 is ``unknown``: the troops being home proves
    only that the round is over, and the operator is told about a loss, so a
    guess here becomes a false alarm on the 提示 page.
    """

    if int(pending.get("garrisonObservedAtMillis") or 0) > 0:
        return "garrisoned"
    if int(pending.get("returnObservedAtMillis") or 0) > 0:
        return "failed"
    return "unknown"


def raid_return_decision(
    pending: Dict[str, Any],
    generals: list[Dict[str, Any]],
    *,
    now_millis: int,
    schedule: Dict[str, Any],
) -> Dict[str, Any]:
    """Wait for one confirmed raid's exact generals to return idle."""

    ids, selected, missing = _selected_generals(pending, generals)
    created_at = int(
        pending.get("dispatchAtMillis")
        or pending.get("createdAtMillis")
        or 0
    )
    poll = max(
        1_000,
        int(
            schedule.get("postDispatchPollMillis")
            or schedule.get("busyGeneralPollMillis")
            or 60_000
        ),
    )
    grace = max(
        poll,
        int(schedule.get("settlementRecheckGraceMillis") or 300_000),
    )
    age = max(0, int(now_millis) - created_at)
    if not ids or created_at <= 0:
        return {
            "action": "stop",
            "reason": "掠夺回闲记录缺少将领或出征时间",
            "preservePending": True,
        }
    if missing:
        return {
            "action": "wait",
            "reason": "新鲜角色状态未找到掠夺将领："
            + ",".join(str(value) for value in missing),
            "nextWakeAtMillis": int(now_millis) + poll,
            "pending": dict(pending),
        }
    updated = dict(pending)
    updated["lastObservedAtMillis"] = int(now_millis)
    busy = [value for value in selected if not general_is_idle(value)]
    if busy:
        updated["sawBusy"] = True
        return {
            "action": "wait",
            "reason": "掠夺将领尚未全部回闲",
            "nextWakeAtMillis": int(now_millis) + poll,
            "pending": updated,
        }
    if not bool(updated.get("sawBusy")) and age < grace:
        return {
            "action": "wait",
            "reason": "尚未观察到掠夺忙碌→回闲转换，等待完整刷新宽限期",
            "nextWakeAtMillis": int(now_millis) + poll,
            "pending": updated,
        }
    return {
        "action": "complete",
        "reason": (
            "掠夺将领已由忙碌转为回闲"
            if updated.get("sawBusy")
            else "完整刷新宽限期后确认掠夺将领空闲"
        ),
        "pending": updated,
    }


__all__ = [
    "brush_recovery_decision",
    "china_day_key",
    "china_start_millis",
    "general_is_idle",
    "mine_garrison_decision",
    "mine_occupation_outcome",
    "raid_return_decision",
    "resident_due_decision",
]
