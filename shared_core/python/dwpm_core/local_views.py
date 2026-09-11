"""Host-neutral projections for local logs, status and success facts.

Platform hosts only read or mutate their local stores.  Filtering, limits,
legacy success recognition and response JSON live here so the Web console sees
the same contract on desktop and Android without waiting for game-network I/O.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import re
from typing import Any, Dict, Iterable, Optional


SYSTEM_LOG_DEFAULT_LIMIT = 500
ACCOUNT_LOG_DEFAULT_LIMIT = 100
SUCCESS_RECORD_MAX_LINES = 50
ACCOUNT_LOG_MESSAGE_MAX_LENGTH = 2_000

#: Features whose user-visible fact *is* the confirmed dispatch, and the label
#: each is known by.
#:
#: A server-confirmed expedition is the same fact no matter which feature sent
#: it: the account committed generals to a battle and cannot take it back.  So
#: recognition is driven by that evidence (``dispatchAccepted`` plus a battle
#: id), and this table only decides what the line is called.  It used to be a
#: per-feature ``if`` chain instead, which meant a feature was recorded only if
#: someone remembered to write its branch - 打矿 was dispatching all day and
#: never appeared anywhere a user could see, because its branch was never
#: written.  Adding a feature here is now the whole change.
#:
#: 副本 is deliberately absent: it is recorded on *completion*, because an
#: opened chest, not the dispatch, is what the operator is waiting to hear.
_EXPEDITION_SUCCESS_LABELS = {
    "brush": "刷黄",
    "mine": "打矿",
    "raid": "掠夺",
    "lossless": "无损",
}
#: Internal aliases for one and the same resident feature.
_RESIDENT_FEATURE_ALIASES = {"brushYellow": "brush"}
_DAILY_SUCCESS_CATEGORIES = {
    "autoSignIn": "签到",
    "arenaCoins": "领币",
    "autoDonate": "捐献",
    "salary": "俸禄",
    "nationalCollect": "国征",
    "cityLordCollect": "城征",
    "generalVisit": "拜访",
}
_DUNGEON_COMPLETION_STATES = {"chest-opened", "settlement-recovered"}

_MINE_TYPE_LABELS = {
    "GOLD": "金矿",
    "SILVER": "银矿",
    "BING_YU": "冰玉矿",
    "XIAN_ZHI": "仙芝园",
    "XUAN_TIE": "玄铁矿",
    "YU_LU": "玉露园",
    "PASTURE_LV1": "一级牧场",
    "PASTURE_LV2": "二级牧场",
    "PASTURE_LV3": "三级牧场",
    "CRYSTAL": "水晶矿",
    "LING_CAO": "灵草园",
    "BIN_TIE": "镔铁矿",
    "JIANG_GUO": "浆果园",
}
_SELECTED_MAP_STATUSES = {"reserved", "dispatched"}

_ERROR_MARKERS = ("失败", "异常", "错误")
_EXACT_MESSAGES = {
    "wakelock acquired for scheduler window": "已获取调度执行窗口锁",
    "wakelock released": "已释放后台保活锁",
    "network validated; account sessions must be rechecked before scheduling": (
        "网络已确认可用，调度前将重新检查账号会话"
    ),
    "network monitor registered": "网络监听已启用",
    "local scheduling started": "手机本地调度已启动",
    "local scheduling stopped": "手机本地调度已停止",
}
_TASK_NAMES = {
    "DAILY_NATIONAL_COLLECT": "每日国家征收",
    "DAILY_CITY_LORD_COLLECT": "每日城主征收",
    "DAILY_GENERAL_VISIT": "每日名将拜访",
    "DAILY_ARENA_COINS": "每日领竞技币",
    "DAILY_SIGN_IN": "每日签到",
    "DAILY_DONATE": "每日捐献",
    "DAILY_SALARY": "每日领取俸禄",
    "BANDIT_PREFETCH": "闲时找山贼",
    "MINE_PREFETCH": "闲时找资源点",
    "FOOD_TO_COPPER": "粮食转铜",
    "STATE_REFRESH": "角色军情刷新",
    "SIX_MINISTRIES": "六部",
    "AUTO_MINING": "自动打矿",
    "MINE_SEARCH": "找矿",
    "SHUA_HUANG": "刷黄",
    "AUTO_LOOT": "自动掠夺",
    "FORMATION": "配兵",
    "INTERNAL": "自动内政",
    "INVENTORY": "背包整理",
    "LOSSLESS": "无损",
    "DUNGEON": "副本",
    "GENERAL": "将领维护",
    "ALARM": "军情警报",
    "DAILY": "日常任务",
}
_COMMON_REPLACEMENTS = (
    ("real-session+saved-screen-config:", "真实会话+已保存配置:"),
    ("real-session-from-account-repo", "账号本地真实会话"),
    ("session-metadata-aligned", "会话信息已对齐"),
    ("account plan(s) from LocalConfigRepository", "个账号任务方案（本地配置）"),
    ("task reports", "个任务报告"),
    ("session_recovery", "会话恢复"),
    ("city-lord/list", "城主城池列表"),
    ("formation_troop", "配兵"),
    ("daily_basic", "每日任务"),
    ("shua_huang", "刷黄"),
    ("dungeon", "副本"),
    ("lossless", "无损"),
    ("mine", "打矿"),
    ("RetryAfter(", "稍后重试("),
    ("NeedRelogin(", "需要重新登录("),
    ("Continue", "继续"),
    ("Sleep(", "等待("),
    ("Stop(", "停止("),
    ("LOGGED_OUT", "已退出"),
    ("RUNNING", "运行中"),
    ("WAITING_RELOGIN", "等待重新登录"),
    ("PAUSED_NETWORK", "网络暂停"),
    ("STOPPING", "正在停止"),
    ("STOPPED", "已停止"),
    (" loaded ", " 已加载 "),
    (" completed ", " 已完成 "),
    (" online=", " 在线="),
    (" paused=", " 暂停="),
    (" waiting=", " 等待="),
    (" relogged=", " 已重登="),
    ("tick=", "调度轮次="),
    ("account=", "账号="),
    ("source=", "来源="),
    ("tasks=", "任务数="),
    ("decisions=", "执行结果="),
    ("features=", "功能="),
    ("actions=", "军情数="),
    ("generals=", "将领数="),
    ("captives=", "被俘将领数="),
    ("unparsedTailBytes=", "未解析尾部字节="),
    ("responses=", "响应="),
    ("opcodes=", "响应指令="),
    ("opcode=", "指令="),
    ("keys=", "字段="),
    ("role=", "角色="),
    ("general=", "将领="),
    ("copper=", "铜钱="),
    ("food=", "粮食="),
    ("code=", "编号="),
    ("phase=", "阶段="),
    ("target=", "目标="),
    ("error=", "错误="),
    ("Lv.", "等级"),
    ("ms)", "毫秒)"),
)


def localize_user_text(value: Any) -> str:
    text = str(value or "")
    if not text:
        return text
    if text in _EXACT_MESSAGES:
        return _EXACT_MESSAGES[text]
    for source, replacement in sorted(
        _TASK_NAMES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        text = text.replace(source, replacement)
    for source, replacement in _COMMON_REPLACEMENTS:
        text = text.replace(source, replacement)
    return text


def project_system_logs(body: Any) -> Dict[str, Any]:
    request = _object(body, "系统日志投影")
    max_lines = _bounded_int(request.get("maxLines"), 10_000, 1, 100_000)
    limit = _bounded_int(
        request.get("limit"), SYSTEM_LOG_DEFAULT_LIMIT, 1, max_lines
    )
    after_id = _optional_nonnegative_int(request.get("afterId"))
    entries = [_log_entry(value, system=True) for value in _rows(request.get("entries"))]
    entries.sort(key=lambda row: (int(row["id"]), int(row["time"])))
    if after_id is not None:
        entries = [row for row in entries if int(row["id"]) > after_id]
        entries = entries[:limit]
    else:
        # Initial loads show the newest tail, while incremental loads return the
        # oldest unseen page so advancing cursorId cannot skip intermediate rows.
        entries = entries[-limit:]
    latest_id = max(
        _bounded_int(request.get("latestId"), 0, 0),
        max((int(row["id"]) for row in entries), default=0),
    )
    cursor_id = (
        int(entries[-1]["id"])
        if entries
        else int(after_id or 0)
    )
    return {
        "ok": True,
        "limit": limit,
        "entries": entries,
        "cursorId": cursor_id,
        "latestId": latest_id,
        "hasMore": cursor_id < latest_id,
        "storage": str(request.get("storage") or "local"),
        "maxLines": max_lines,
    }


def project_account_logs(body: Any) -> Dict[str, Any]:
    request = _object(body, "账号日志投影")
    account_ref = str(request.get("accountRef") or "").strip()
    if not account_ref:
        raise ValueError("账号日志缺少 accountRef")
    max_lines = _bounded_int(request.get("maxLines"), 100, 1, 10_000)
    limit = _bounded_int(
        request.get("limit"), ACCOUNT_LOG_DEFAULT_LIMIT, 1, max_lines
    )
    entries = [_log_entry(value, system=False) for value in _rows(request.get("entries"))]
    entries = [
        row for row in entries
        if str(row.get("sessionId") or "") == account_ref
    ]
    entries.sort(key=lambda row: (int(row["time"]), int(row["id"])))
    entries = entries[-limit:]
    return {
        "ok": True,
        "accountKey": str(request.get("accountKey") or account_ref),
        "limit": limit,
        "entries": entries,
        "maxLines": max_lines,
    }


def project_success_records(body: Any) -> Dict[str, Any]:
    request = _object(body, "成功记录投影")
    account_ref = str(request.get("accountRef") or "").strip()
    if not account_ref:
        raise ValueError("成功记录缺少 accountRef")
    limit = _bounded_int(
        request.get("limit"), SUCCESS_RECORD_MAX_LINES, 1,
        SUCCESS_RECORD_MAX_LINES,
    )
    category = str(request.get("category") or "").strip()
    records = []
    for raw in _rows(request.get("records")):
        record = _explicit_success_record(raw, account_ref)
        if record:
            _normalize_brush_success_record(record)
            records.append(record)
    for raw in _rows(request.get("logEntries")):
        entry = _log_entry(raw, system=False)
        if str(entry.get("sessionId") or "") != account_ref:
            continue
        resolved = resolve_success_record(raw)
        if not resolved:
            continue
        records.append(
            {
                "id": int(entry["id"]),
                "time": int(entry["time"]),
                "timeText": str(entry["timeText"]),
                "sessionId": account_ref,
                "accountKey": str(request.get("accountKey") or account_ref),
                "category": resolved["category"],
                "message": resolved["message"],
                "source": str(entry.get("source") or ""),
                **(
                    {"dedupeKey": resolved["dedupeKey"]}
                    if resolved.get("dedupeKey") else {}
                ),
            }
        )
    if category:
        records = [row for row in records if row["category"] == category]
    records.sort(
        key=lambda row: (int(row.get("time") or 0), int(row.get("id") or 0)),
        reverse=True,
    )
    unique_records = []
    keyed_indexes = {}
    for record in records:
        dedupe_key = _success_record_dedupe_key(record)
        previous_index = keyed_indexes.get(dedupe_key) if dedupe_key else None
        if previous_index is not None:
            if _success_record_quality(record) > _success_record_quality(
                unique_records[previous_index]
            ):
                detailed = deepcopy(record)
                previous = unique_records[previous_index]
                freshest = max(
                    (previous, record),
                    key=lambda row: (
                        int(row.get("time") or 0),
                        int(row.get("id") or 0),
                    ),
                )
                for key in ("id", "time", "timeText"):
                    if key in freshest:
                        detailed[key] = deepcopy(freshest[key])
                unique_records[previous_index] = detailed
            continue
        if dedupe_key:
            keyed_indexes[dedupe_key] = len(unique_records)
        unique_records.append(record)
    unique_records.sort(
        key=lambda row: (int(row.get("time") or 0), int(row.get("id") or 0)),
        reverse=True,
    )
    return {
        "ok": True,
        "accountKey": str(request.get("accountKey") or account_ref),
        "limit": limit,
        "category": category,
        "entries": unique_records[:limit],
        "maxLines": SUCCESS_RECORD_MAX_LINES,
    }


def resident_success_record(
    result: Any,
    *,
    now_millis: int,
) -> Optional[Dict[str, Any]]:
    """Convert one definitive shared-resident result into a host-neutral fact."""

    if not isinstance(result, dict) or result.get("success") is False:
        return None
    feature = str(result.get("feature") or "").strip()
    state = str(result.get("state") or "").strip()
    battle_id = _positive_int(
        result.get("battleId") or result.get("successBattleId")
    )
    timestamp = max(0, int(now_millis))

    if feature == "daily" and state == "completed":
        daily_key = str(result.get("dailyKey") or "").strip()
        nested = result.get("result")
        nested = nested if isinstance(nested, dict) else {}
        daily_key = daily_key or str(nested.get("dailyKey") or "").strip()
        category = _DAILY_SUCCESS_CATEGORIES.get(daily_key)
        if not category:
            return None
        cycle_value = result.get("cycleKey")
        if cycle_value in (None, ""):
            cycle_value = nested.get("cycleKey")
        try:
            cycle_key = int(cycle_value) if cycle_value not in (None, "") else None
        except (TypeError, ValueError):
            cycle_key = None
        skipped = bool(result.get("skipped") or nested.get("skipped"))
        skip_reason = str(
            result.get("skipReason") or nested.get("skipReason") or ""
        ).strip()
        message = str(
            result.get("message")
            or result.get("statusText")
            or nested.get("message")
            or nested.get("statusText")
            or category
        ).strip()
        # A skipped task is a definitive political result, not an absent record.
        # Keep the concise server-neutral text so the role page can show why it
        # was completed without pretending a network request was sent.
        if skipped and not message:
            message = "国民跳过"
        dedupe_key = (
            f"daily:{daily_key}:{cycle_key}"
            if cycle_key is not None
            else f"daily:{daily_key}:{timestamp}"
        )
        detail: Dict[str, Any] = {
            "feature": "daily",
            "state": state,
            "dailyKey": daily_key,
            "skipped": skipped,
        }
        if cycle_key is not None:
            detail["cycleKey"] = cycle_key
        if skip_reason:
            detail["skipReason"] = skip_reason
        for key in ("completionCount", "taskNextWakeAtMillis"):
            value = result.get(key)
            if value not in (None, ""):
                detail[key] = deepcopy(value)
        return _resident_success_record(
            timestamp=timestamp,
            category=category,
            message=message,
            dedupe_key=dedupe_key,
            detail=detail,
        )

    if feature == "domestic" and state == "completed":
        action = result.get("action")
        action = action if isinstance(action, dict) else {}
        action_kind = str(action.get("action") or "").strip()
        if action_kind not in {"building", "technology"}:
            return None
        plan_key = str(result.get("planKey") or "").strip()
        message = str(
            result.get("message")
            or action.get("description")
            or ("科技升级已确认" if action_kind == "technology" else "建筑操作已确认")
        ).strip()
        category = "科技" if action_kind == "technology" else "内政"
        dedupe_key = (
            f"domestic:plan:{plan_key}"
            if plan_key else
            "domestic:action:"
            f"{action_kind}:{int(action.get('fiefId') or 0)}:"
            f"{int(action.get('slot') or action.get('academySlot') or 0)}:"
            f"{int(action.get('targetLevel') or 0)}:{timestamp}"
        )
        return _resident_success_record(
            timestamp=timestamp,
            category=category,
            message=message,
            dedupe_key=dedupe_key,
            detail={
                "feature": "domestic",
                "state": state,
                "planKey": plan_key,
                "action": deepcopy(action),
            },
        )

    canonical = _canonical_resident_feature(feature)
    if (
        canonical in _EXPEDITION_SUCCESS_LABELS
        and bool(result.get("dispatchAccepted"))
        and battle_id is not None
    ):
        return _expedition_success_record(
            result,
            canonical=canonical,
            state=state,
            battle_id=battle_id,
            timestamp=timestamp,
        )

    # Getting the generals back is a separate fact from sending them out, and
    # the one that frees them for the next round.  It keys off the same battle
    # but must not share the expedition's dedupe key, or the round would show
    # only whichever half was written first.
    if (
        canonical == "mine"
        and bool(result.get("recallCompleted"))
        and battle_id is not None
    ):
        target = _safe_success_target(result.get("target"))
        destination = _target_destination(target)
        formation_number = _expedition_formation_number(result)
        action = (
            f"编队{formation_number}"
            if formation_number is not None else "全部将领"
        )
        return _resident_success_record(
            timestamp=timestamp,
            category=_EXPEDITION_SUCCESS_LABELS["mine"],
            message=(
                f"{action} 已撤回 > {destination}（battleId={battle_id}）"
                if destination
                else f"{action} 已撤回（battleId={battle_id}）"
            ),
            dedupe_key=f"mine:recall:{battle_id}",
            detail={
                "feature": "mine",
                "state": state,
                "battleId": battle_id,
                "target": target,
                "occupationOutcome": str(
                    result.get("occupationOutcome") or "recalled"
                ),
                **(
                    {"formationNumber": formation_number}
                    if formation_number is not None else {}
                ),
            },
        )

    if (
        feature == "dungeon"
        and state in _DUNGEON_COMPLETION_STATES
        and battle_id is not None
    ):
        stage = _safe_success_stage(result.get("stage"))
        stage_text = _dungeon_stage_text(stage)
        completion = str(result.get("message") or "副本完成并已确认结算")
        message = f"{stage_text} > {completion}" if stage_text else completion
        message += f"（battleId={battle_id}）"
        chest = result.get("chestResult")
        chest = chest if isinstance(chest, dict) else {}
        return _resident_success_record(
            timestamp=timestamp,
            category="副本",
            message=message,
            dedupe_key=f"dungeon:battle:{battle_id}",
            detail={
                "feature": "dungeon",
                "state": state,
                "battleId": battle_id,
                "stage": stage,
                "chest": {
                    key: deepcopy(chest[key])
                    for key in ("chestIndex", "chestName", "success")
                    if key in chest
                },
            },
        )
    return None


def general_energy_success_record(
    applied: Any,
    *,
    now_millis: int,
) -> Optional[Dict[str, Any]]:
    """Turn one accepted 活血丹 receipt into a record for the 政事 page.

    Every feature that tops a general up - 将领维护 and each expedition
    preflight - goes through the same shared step, so this reads that step's
    own result instead of re-deriving the fact from each caller's message.
    Spending a stock item is bookkeeping, not a military outcome, so the
    category deliberately sits outside the 军事 set the role page filters on.
    """

    if not isinstance(applied, dict):
        return None
    if not bool(applied.get("success")) or not bool(applied.get("actionRequired")):
        return None
    try:
        general_id = int(applied.get("generalId") or 0)
    except (TypeError, ValueError):
        general_id = 0
    name = str(
        applied.get("generalName") or general_id or "未知将领"
    ).strip() or "未知将领"
    item_name = str(applied.get("itemName") or "活血丹").strip() or "活血丹"
    count = _positive_int(applied.get("itemCount")) or 1
    # Zero is a real reading on both counters, and the most interesting one:
    # a general at 体力0 is exactly who needs the item, and 0 left in stock is
    # exactly what the user needs to see.
    before = _nonnegative_int(applied.get("before"))
    after = _nonnegative_int(applied.get("after"))
    action_name = str(applied.get("actionName") or "").strip()
    detail: Dict[str, Any] = {
        "feature": "general",
        "step": "energy",
        "generalId": general_id,
        "generalName": name,
        "itemName": item_name,
        "itemCount": count,
    }
    for key, value in (("before", before), ("after", after)):
        if value is not None:
            detail[key] = value
    if action_name:
        detail["actionName"] = action_name
    remaining = _nonnegative_int(applied.get("availableItemCount"))
    if remaining is not None:
        # What was in stock *before* this use; the page shows what is left.
        detail["remainingItemCount"] = max(0, remaining - count)
    parts = [f"{name} 使用{count}枚{item_name}"]
    if before is not None and after is not None:
        parts.append(f"体力{before}→{after}")
    if action_name:
        parts.append(f"来源{action_name}")
    timestamp = max(0, int(now_millis))
    return _resident_success_record(
        timestamp=timestamp,
        category=item_name,
        message="，".join(parts),
        # One general cannot be topped up twice inside a minute: the item adds
        # more energy than the lowest threshold that can trigger it.  A minute
        # bucket therefore folds the same event together no matter which path
        # reported it, without ever folding two real uses.
        dedupe_key=f"general:energy:{general_id}:{timestamp // 60_000}",
        detail=detail,
    )


def resident_success_records_from_public_state(
    public_state: Any,
    *,
    account_ref: str,
) -> list[Dict[str, Any]]:
    """Read durable history and recover the last pre-upgrade resident facts."""

    if not isinstance(public_state, dict):
        return []
    records = []
    for raw in _json_list_value(public_state.get("successRecordsJson")):
        if not isinstance(raw, dict):
            continue
        record = deepcopy(raw)
        record.setdefault("sessionId", str(account_ref))
        record.setdefault("accountKey", str(account_ref))
        records.append(record)

    last_brush = _json_object_value(
        public_state.get("brushLastRecoveryJson")
    )
    pending_brush = _json_object_value(
        public_state.get("brushPendingRecoveryJson")
    )
    brush_facts = [last_brush]
    if str(pending_brush.get("sendState") or "") == "accepted":
        brush_facts.append(pending_brush)
    for fact in brush_facts:
        battle_id = _positive_int(fact.get("battleId"))
        if battle_id is None:
            continue
        timestamp = _first_positive_int(
            fact,
            "acceptedAtMillis",
            "completedAtMillis",
            "updatedAtMillis",
            "createdAtMillis",
        )
        brush_result = {
            "feature": "brush",
            "state": "dispatched",
            "success": True,
            "dispatchAccepted": True,
            "battleId": battle_id,
            "target": fact.get("target") or {},
            "sourceRowIndex": fact.get("sourceRowIndex"),
            "formationNumber": fact.get("formationNumber"),
            "formationSourceRowIndex": fact.get(
                "formationSourceRowIndex"
            ),
        }
        formation_number = _brush_formation_number(
            brush_result, public_state=public_state
        )
        if formation_number is not None:
            brush_result["formationNumber"] = formation_number
        recovered = resident_success_record(
            brush_result,
            now_millis=timestamp,
        )
        if recovered:
            recovered.update({
                "sessionId": str(account_ref),
                "accountKey": str(account_ref),
                "source": "shared-resident-state-recovery",
            })
            records.append(recovered)

    pending_lossless = _json_object_value(
        public_state.get("losslessPendingBattleJson")
    )
    if str(pending_lossless.get("dispatchSendState") or "") == "accepted":
        recovered = resident_success_record(
            {
                "feature": "lossless",
                "state": "fighting",
                "success": True,
                "dispatchAccepted": True,
                "battleId": pending_lossless.get("battleId"),
                "stage": pending_lossless.get("stage") or {},
            },
            now_millis=_first_positive_int(
                pending_lossless,
                "acceptedAtMillis",
                "dispatchAtMillis",
                "dispatchAcceptedAtMillis",
                "updatedAtMillis",
                "createdAtMillis",
            ),
        )
        if recovered:
            recovered.update({
                "sessionId": str(account_ref),
                "accountKey": str(account_ref),
                "source": "shared-resident-state-recovery",
            })
            records.append(recovered)

    dungeon = _json_object_value(public_state.get("dungeonLastResultJson"))
    if str(dungeon.get("state") or "") in _DUNGEON_COMPLETION_STATES:
        recovered = resident_success_record(
            {
                "feature": "dungeon",
                "state": dungeon.get("state"),
                "success": True,
                "battleId": dungeon.get("battleId"),
                "stage": dungeon.get("stage") or {},
                "chestResult": dungeon.get("chestResult") or {},
                "message": (
                    "上一场副本待领取宝箱已补开"
                    if dungeon.get("state") == "settlement-recovered"
                    else "副本完成并已开启宝箱"
                ),
            },
            now_millis=_first_positive_int(
                dungeon, "completedAtMillis", "updatedAtMillis"
            ),
        )
        if recovered:
            recovered.update({
                "sessionId": str(account_ref),
                "accountKey": str(account_ref),
                "source": "shared-resident-state-recovery",
            })
            records.append(recovered)
    return records


def resident_success_records_from_operation_facts(
    operation_facts: Any,
    *,
    account_ref: str,
    public_state: Any = None,
) -> list[Dict[str, Any]]:
    """Recover compact expedition and domestic facts from the durable ledger.

    Old operation results retained the fields needed by the UI even though the
    old success-record formatter discarded them.  Hosts pass only a compact,
    pre-filtered projection here so opening the record page never copies the
    complete (and sometimes very large) protocol ledger.
    """

    records = []
    for operation in _rows(operation_facts):
        if not isinstance(operation, dict):
            continue
        operation_account = str(operation.get("accountRef") or "").strip()
        if operation_account and operation_account != str(account_ref):
            continue
        if operation.get("status") not in (None, "", "SUCCEEDED"):
            continue
        result = operation.get("result")
        if not isinstance(result, dict):
            continue
        result = deepcopy(result)
        feature = str(result.get("feature") or "").strip()
        canonical = _canonical_resident_feature(feature)
        is_expedition = canonical in _EXPEDITION_SUCCESS_LABELS
        if not is_expedition and feature not in {"domestic", "daily"}:
            continue
        # The ledger keeps the dispatch evidence, so a feature the projection
        # used to ignore is not lost history - it is unread history.  打矿 had
        # a full day of confirmed expeditions sitting here while the record
        # page showed none of them; widening this with the same table that
        # recognizes a live dispatch recovers them.
        if is_expedition and not bool(result.get("dispatchAccepted")):
            continue
        if feature == "domestic" and not (
            str(result.get("state") or "") == "completed"
            and result.get("success") is not False
            and isinstance(result.get("action"), dict)
        ):
            continue
        if feature == "daily" and not (
            str(result.get("state") or "") == "completed"
            and result.get("success") is not False
            and str(result.get("dailyKey") or "").strip()
        ):
            continue
        if feature in {"brush", "brushYellow"}:
            formation_number = _brush_formation_number(
                result, public_state=public_state
            )
            if formation_number is not None:
                result["formationNumber"] = formation_number
        embedded = result.get("successRecord")
        embedded = embedded if isinstance(embedded, dict) else {}
        timestamp = _first_positive_int(
            embedded, "time", "createdAtMillis", "updatedAtMillis"
        ) or _first_positive_int(
            result,
            "tickAtMillis",
            "acceptedAtMillis",
            "dispatchAtMillis",
            "completedAtMillis",
        ) or _first_positive_int(
            operation,
            "completedAtMillis",
            "updatedAtMillis",
            "submittedAtMillis",
        )
        recovered = resident_success_record(result, now_millis=timestamp)
        if recovered:
            recovered.update({
                "sessionId": str(account_ref),
                "accountKey": str(account_ref),
                "source": "shared-operation-history",
            })
            records.append(recovered)
    return records


def project_automation_status(body: Any) -> Dict[str, Any]:
    request = _object(body, "自动化状态投影")
    tasks = [deepcopy(row) for row in _rows(request.get("tasks"))]
    tasks.sort(
        key=lambda row: int(row.get("createdAt") or row.get("updatedAt") or 0),
        reverse=True,
    )
    operations = [
        deepcopy(row) for row in _rows(request.get("assistantOperations"))
    ]
    overview = request.get("taskOverview")
    if overview is not None and not isinstance(overview, dict):
        raise ValueError("任务概览必须是对象或 null")
    return {
        "ok": True,
        "tasks": tasks[:10],
        "assistantOperations": operations,
        "taskOverview": deepcopy(overview),
    }


def project_bandit_map(
    body: Any,
    *,
    now_millis: int,
    ttl_millis: int,
) -> Dict[str, Any]:
    request = _object(body, "山贼地图投影")
    server_key = str(request.get("serverKey") or "").strip()
    if not server_key:
        raise ValueError("当前账号没有可识别的区服，无法读取山贼地图")
    now = _bounded_int(now_millis, 0, 0)
    ttl = _bounded_int(ttl_millis, 1, 1)
    points = []
    for raw in _rows(request.get("records")):
        record = _map_record(raw)
        updated_at = _map_updated_at(record)
        if not _map_record_is_fresh(record, updated_at, now, ttl):
            continue
        level = _field_int(record, "level", "rank", "fz") or 0
        composition = _bandit_composition_code(record)
        identity = _map_target_identity(record)
        if identity is None or level <= 0 or not composition:
            continue
        target_id, target_hex = identity
        reward = _field_text(
            record,
            "rewardDescription",
            "resource",
            "reward",
            "drop",
            "description",
        )
        categories = _field_string_values(
            record,
            "dropCategories",
            "dropCategory",
        )
        if not categories:
            categories = [
                category
                for category in ("资源", "宝箱", "装备", "宝物")
                if category in reward
            ]
        status = _map_status(record)
        points.append({
            "key": f"id:{target_hex}",
            "id": target_id,
            "idHex": target_hex,
            "name": _field_text(record, "name", "kind", "type") or "山贼",
            "level": level,
            "x": _field_int(record, "x") or 0,
            "y": _field_int(record, "y") or 0,
            "compositionCode": composition,
            "rewardDescription": reward,
            "dropCategories": categories,
            "lootIds": _field_int_values(record, "lootIds", "lootId", "dropIds"),
            "firstDiscoveredAt": _field_int(
                record,
                "firstDiscoveredAt",
                "firstDiscoveredAtMillis",
            ) or updated_at,
            "updatedAt": updated_at,
            "selectedForAttack": status in _SELECTED_MAP_STATUSES,
            "status": status,
        })
    points.sort(key=lambda row: (row["y"], row["x"], row["level"]))
    return {
        "ok": True,
        "serverKey": server_key,
        "updatedAt": max(
            _bounded_int(request.get("updatedAt"), 0, 0),
            max((int(row["updatedAt"]) for row in points), default=0),
        ),
        "ttlMs": ttl,
        "points": points,
    }


def project_mine_map(
    body: Any,
    *,
    now_millis: int,
    ttl_millis: int,
) -> Dict[str, Any]:
    request = _object(body, "资源地图投影")
    server_key = str(request.get("serverKey") or "").strip()
    if not server_key:
        raise ValueError("当前账号没有可识别的区服，无法读取资源地图")
    now = _bounded_int(now_millis, 0, 0)
    ttl = _bounded_int(ttl_millis, 1, 1)
    points = []
    for raw in _rows(request.get("records")):
        record = _map_record(raw)
        updated_at = _map_updated_at(record)
        if not _map_record_is_fresh(record, updated_at, now, ttl):
            continue
        identity = _map_target_identity(record)
        if identity is None:
            continue
        target_id, target_hex = identity
        protocol_kind = _field_text(record, "protocolKind", "type", "mineType")
        kind = _field_text(record, "kind") or _MINE_TYPE_LABELS.get(
            protocol_kind.upper(),
            protocol_kind,
        )
        level = _field_int(record, "level", "rank", "fz") or 0
        type_code = _field_optional_int(record, "typeCode", "kindCode")
        name = _field_text(record, "name")
        if not name:
            name = (
                kind
                if type_code == 5 or level <= 0
                else f"{level}级{kind}"
            )
        owner_name = _field_text(
            record,
            "ownerName",
            "playerName",
            "owner",
            "lordName",
        )
        player_occupied = _field_bool(
            record,
            "playerOccupied",
            "occupiedByPlayer",
            "occupied",
        )
        if player_occupied is None:
            player_occupied = bool(owner_name)
        defender_count = _field_int(
            record,
            "defenderCount",
            "defenseCount",
            "defenders",
            "guardCount",
        ) or 0
        status = _map_status(record)
        expires_at = updated_at + ttl
        points.append({
            "key": f"id:{target_hex}",
            "id": target_id,
            "idHex": target_hex,
            "name": name or kind,
            "kind": kind,
            "protocolKind": protocol_kind,
            "businessId": _field_optional_int(record, "businessId", "resourceId"),
            "typeCode": type_code if type_code is not None else "",
            "level": level,
            "x": _field_int(record, "x") or 0,
            "y": _field_int(record, "y") or 0,
            "ownerName": owner_name,
            "ownerCountry": _field_text(record, "ownerCountry", "country"),
            "playerOccupied": player_occupied,
            "unoccupiedByPlayer": not player_occupied,
            "amountA": _field_optional_int(
                record,
                "amountA",
                "reserve",
                "amount",
                "storage",
            ),
            "amountB": _field_optional_int(
                record,
                "amountB",
                "productionPerHour",
            ),
            "description": _field_text(record, "description", "detail"),
            "defenderCount": defender_count,
            "hasDefenders": defender_count > 0,
            "firstDiscoveredAt": _field_int(
                record,
                "firstDiscoveredAt",
                "firstDiscoveredAtMillis",
            ) or updated_at,
            "updatedAt": updated_at,
            "expiresAt": expires_at,
            "remainingMs": max(0, expires_at - now),
            "selectedForAttack": status in _SELECTED_MAP_STATUSES,
            "status": status,
        })
    points.sort(
        key=lambda row: (
            row["y"],
            row["x"],
            row["businessId"] if row["businessId"] is not None else 999,
        )
    )
    return {
        "ok": True,
        "serverKey": server_key,
        "updatedAt": max(
            _bounded_int(request.get("updatedAt"), 0, 0),
            max((int(row["updatedAt"]) for row in points), default=0),
        ),
        "ttlMs": ttl,
        "points": points,
    }


def recommend_brush_center(body: Any) -> Dict[str, Any]:
    """Choose the cached fief containing most selected generals without I/O."""

    request = _object(body, "刷黄推荐中心")
    minimum_level = _bounded_int(request.get("minimumRoleLevel"), 0, 0, 10_000)
    role_level = _bounded_int(request.get("roleLevel"), 0, 0, 10_000)
    if minimum_level > 0 and role_level < minimum_level:
        raise ValueError(f"请{minimum_level}级之后再开启刷黄！")
    raw_ids = request.get("generalIds")
    if not isinstance(raw_ids, list):
        raise ValueError("刷黄推荐中心缺少 generalIds")
    ordered_ids = [
        str(value).strip()
        for value in raw_ids
        if str(value or "").strip()
    ]
    if not ordered_ids:
        raise ValueError("当前刷黄编队没有已选将领")

    generals = list(_rows(request.get("generals")))
    selected = []
    selected_generals = []
    for general_id in ordered_ids:
        general = next(
            (
                row for row in generals
                if _general_identity_matches(row, general_id)
            ),
            None,
        )
        if general is None:
            raise ValueError(f"无法读取将领 {general_id} 的所在封地")
        fief_id = _field_int(general, "fiefId", "placeID", "placeId") or 0
        if fief_id <= 0:
            name = _field_text(general, "name", "generalName") or general_id
            raise ValueError(f"将领 {name} 没有可识别的所在封地")
        selected.append((general_id, general, fief_id))
        selected_generals.append({
            "generalId": general_id,
            "generalName": (
                _field_text(general, "name", "generalName") or general_id
            ),
            "fiefId": fief_id,
        })

    locations: Dict[int, Dict[str, Any]] = {}
    for fief in _rows(request.get("fiefs")):
        fief_id = _field_int(fief, "targetId", "fiefId", "id") or 0
        if fief_id > 0 and fief_id not in locations:
            locations[fief_id] = fief
    for _general_id, general, fief_id in selected:
        if fief_id in locations:
            continue
        raw = general.get("raw")
        raw = raw if isinstance(raw, dict) else {}
        x = _field_int(general, "fiefX")
        y = _field_int(general, "fiefY")
        if x is None:
            x = _field_int(raw, "fiefX")
        if y is None:
            y = _field_int(raw, "fiefY")
        if x is None or y is None:
            continue
        locations[fief_id] = {
            "targetId": fief_id,
            "fiefName": (
                _field_text(general, "fiefName")
                or _field_text(raw, "fiefName")
            ),
            "cityName": (
                _field_text(general, "cityName")
                or _field_text(raw, "cityName")
            ),
            "x": x,
            "y": y,
        }

    counts: Dict[int, int] = {}
    for _general_id, _general, fief_id in selected:
        counts[fief_id] = counts.get(fief_id, 0) + 1
    highest = max(counts.values())
    tied = {fief_id for fief_id, count in counts.items() if count == highest}
    chosen_fief_id = next(
        fief_id for _general_id, _general, fief_id in selected
        if fief_id in tied
    )
    chosen = locations.get(chosen_fief_id)
    x = _field_int(chosen or {}, "x", "fiefX")
    y = _field_int(chosen or {}, "y", "fiefY")
    if chosen is None or x is None or y is None:
        raise ValueError(
            f"登录缓存中没有封地ID {chosen_fief_id} 的世界坐标，"
            "请重新启动该账号"
        )
    world_x = max(0, min(int(x), 186))
    world_y = max(0, int(y))
    return {
        "ok": True,
        "x": world_x,
        "y": min(world_y, 55),
        "worldX": world_x,
        "worldY": world_y,
        "fiefId": chosen_fief_id,
        "fiefName": _field_text(chosen, "fiefName", "name"),
        "cityName": _field_text(chosen, "cityName", "city"),
        "selectedGenerals": selected_generals,
        "fiefCounts": {str(key): value for key, value in counts.items()},
        "source": "login-owned-fief-cache",
    }


def account_log_write_plan(body: Any) -> Dict[str, Any]:
    request = _object(body, "账号日志写入")
    message = re.sub(r"\s+", " ", str(request.get("message") or "")).strip()
    if not message:
        raise ValueError("日志内容不能为空")
    level = str(request.get("level") or "info").strip().lower()
    if level not in {"debug", "info", "warn", "warning", "error"}:
        level = "info"
    if level == "warning":
        level = "warn"
    return {
        "route": "/api/logs/account",
        "networkRequired": False,
        "write": {
            "accountRef": str(
                request.get("accountRef") or request.get("sessionId") or ""
            ).strip(),
            "message": message[:ACCOUNT_LOG_MESSAGE_MAX_LENGTH],
            "level": level,
            "source": str(request.get("source") or "frontend").strip()[:80],
        },
    }


def system_log_clear_plan(body: Any) -> Dict[str, Any]:
    _object(body, "系统日志清空")
    return {
        "route": "/api/logs/system/clear",
        "networkRequired": False,
        "clearSystemLogs": True,
    }


def notice_dismiss_plan(body: Any) -> Dict[str, Any]:
    request = _object(body, "提示关闭")
    account_ref = str(
        request.get("accountRef") or request.get("sessionId") or ""
    ).strip()
    if not account_ref:
        raise ValueError("缺少账号")
    notice_key = str(request.get("noticeKey") or "").strip()
    if not notice_key:
        raise ValueError("缺少提示标识")
    return {
        "route": "/api/notices/dismiss",
        "networkRequired": False,
        "write": {
            "accountRef": account_ref,
            "noticeKey": notice_key[:240],
        },
    }


def resolve_success_record(entry: Any) -> Optional[Dict[str, str]]:
    if not isinstance(entry, dict):
        return None
    category = str(entry.get("successCategory") or "").strip()
    message = str(entry.get("successMessage") or "").strip()
    if category and message:
        resolved = {"category": category[:30], "message": message[:500]}
        dedupe_key = str(
            entry.get("successDedupeKey") or entry.get("dedupeKey") or ""
        ).strip()
        if dedupe_key:
            resolved["dedupeKey"] = dedupe_key[:200]
        return resolved
    return _legacy_success_record(str(entry.get("message") or ""))


def _legacy_success_record(raw_message: str) -> Optional[Dict[str, str]]:
    text = re.sub(r"\s+", " ", str(raw_message or "")).strip()
    match = re.search(
        r"共享常驻 .*?\bfeature=(?:brush|brushYellow)\b "
        r"state=dispatched\b.*?\bmessage=.*?battleId=(\d+)\b",
        text,
    )
    if match:
        battle_id = int(match.group(1))
        return _success(
            "刷黄",
            f"出征成功（battleId={battle_id}）",
            dedupe_key=f"brush:battle:{battle_id}",
        )
    match = re.search(r"副本第 \d+ 轮第 (\d+) 条完成：.+? → (.+?第\d+关)，", text)
    if match:
        return _success("副本", f"编队{match.group(1)} > {match.group(2)}")
    match = re.search(
        r"自动加体完成：(.+?) 使用活血丹1个"
        r"(?:.*?由(\d+)更新为(\d+))?",
        text,
    )
    if match:
        # 加体 and 活血丹使用 are the same event - the step has no other item -
        # so both paths report it under one category instead of splitting the
        # history across the 军事 and 政事 tabs.
        detail = f"{match.group(1)}使用1枚活血丹"
        if match.group(2) and match.group(3):
            detail += f"，体力{match.group(2)}→{match.group(3)}"
        return _success("活血丹", detail)
    match = re.search(r"粮食转铜完成：兑换(\d+)铜，消耗粮食(\d+)", text)
    if match:
        return _success("转铜", f"{match.group(2)}粮换{match.group(1)}铜")
    match = re.search(r"治疗伤兵完成：.*?封地=([^；]+?) 范围=全部伤兵(?:；|$)", text)
    if match:
        return _success("治疗", f"{match.group(1)} 全部伤兵")
    match = re.search(r"治疗伤兵完成：.*?fief=([^ ]+) 兵种=0 数量=-1(?:；|$)", text)
    if match:
        return _success("治疗", f"封地{match.group(1)} 全部伤兵")
    match = re.search(r"治疗伤兵完成：.*?兵种=([^ ]+) 数量=([^；]+)", text)
    if match:
        soldier = match.group(1)
        label = f"兵种{soldier}" if re.fullmatch(r"-?\d+", soldier) else soldier
        return _success("治疗", f"{label} {match.group(2)}")
    match = re.search(r"自动开箱成功：(.+)", text)
    if match:
        return _success("开箱", match.group(1))
    prefixes = (
        ("自动签到完成：", "签到", "今日签到成功"),
        ("领竞技币完成：", "领币", "领取竞技币成功"),
        ("领取俸禄完成：", "俸禄", "领取俸禄成功"),
        ("国家俸禄完成：", "俸禄", "领取俸禄成功"),
        ("国家征收完成：", "国征", "国家征收成功"),
        ("城主征收完成：", "城征", "城主征收成功"),
        ("名将拜访完成：", "拜访", "名将拜访成功"),
        ("名将拜访成功：", "拜访", "名将拜访成功"),
    )
    for prefix, category, fallback in prefixes:
        if text.startswith(prefix):
            return _success(category, text[len(prefix):].strip() or fallback)
    if text.startswith("自动捐献完成：") and "失败" not in text:
        detail = re.sub(
            r"^(?:自动捐献完成[:：]\s*)+", "",
            text[len("自动捐献完成："):],
        ).strip()
        return _success("捐献", detail or "捐献成功")
    return None


def _success(
    category: str,
    message: str,
    *,
    dedupe_key: str = "",
) -> Dict[str, str]:
    result = {"category": category[:30], "message": message.strip()[:500]}
    if dedupe_key:
        result["dedupeKey"] = dedupe_key[:200]
    return result


def _explicit_success_record(
    raw: Any,
    account_ref: str,
) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    raw_account_ref = str(raw.get("sessionId") or "").strip()
    if raw_account_ref and raw_account_ref != account_ref:
        return None
    category = str(raw.get("category") or "其他").strip()[:30] or "其他"
    message = re.sub(r"\s+", " ", str(raw.get("message") or "")).strip()[:500]
    if category == "治疗" and message == "兵种0 -1":
        message = "全部伤兵"
    if not message:
        return None
    timestamp = _bounded_int(raw.get("time"), 0, 0)
    record = {
        "id": _bounded_int(raw.get("id"), 0, -10**18, 10**18),
        "time": timestamp,
        "timeText": str(raw.get("timeText") or _time_text(timestamp)),
        "sessionId": str(raw.get("sessionId") or account_ref),
        "accountKey": str(raw.get("accountKey") or account_ref),
        "category": category,
        "message": message,
    }
    for key in ("source", "detail", "dedupeKey"):
        if key in raw:
            record[key] = deepcopy(raw[key])
    return record


def _normalize_brush_success_record(record: Dict[str, Any]) -> None:
    """Repair persisted brush labels without changing troop-source identity.

    Older desktop records stored the military troop-table row as
    ``formationNumber``.  Their detail already contains the brush-rule row, so
    the projection can correct both the visible message and visible number
    while retaining ``formationSourceRowIndex`` for internal diagnostics.
    """

    detail = record.get("detail")
    detail = detail if isinstance(detail, dict) else {}
    feature = str(detail.get("feature") or "").strip()
    if feature == "brushYellow":
        feature = "brush"
    if feature != "brush" and str(record.get("category") or "") != "刷黄":
        return
    rule_index = _nonnegative_int(detail.get("ruleSourceRowIndex"))
    if rule_index is None:
        rule_index = _nonnegative_int(detail.get("sourceRowIndex"))
    if rule_index is None:
        return
    formation_number = rule_index + 1
    detail["formationNumber"] = formation_number
    record["detail"] = detail
    record["message"] = re.sub(
        r"^编队\d+",
        f"编队{formation_number}",
        str(record.get("message") or ""),
        count=1,
    )


def _canonical_resident_feature(feature: Any) -> str:
    name = str(feature or "").strip()
    return _RESIDENT_FEATURE_ALIASES.get(name, name)


def _expedition_success_record(
    result: Dict[str, Any],
    *,
    canonical: str,
    state: str,
    battle_id: int,
    timestamp: int,
) -> Dict[str, Any]:
    """Render one server-confirmed expedition for the operator.

    Recognition already happened at the call site, on evidence alone.  What is
    left is naming, and features differ only in what they consider the
    interesting part of a dispatch: 无损 is clearing a numbered stage, while
    打矿/刷黄/掠夺 are going somewhere on the map.  Nothing else here is
    feature-specific, so a new expedition feature needs no code at all.
    """

    label = _EXPEDITION_SUCCESS_LABELS[canonical]
    detail: Dict[str, Any] = {
        "feature": canonical,
        "state": state,
        "battleId": battle_id,
    }
    if canonical == "lossless":
        stage = _safe_success_stage(result.get("stage"))
        detail["stage"] = stage
        return _resident_success_record(
            timestamp=timestamp,
            category=label,
            message=(
                _lossless_stage_text(stage)
                or f"无损出征（battleId={battle_id}）"
            ),
            dedupe_key=f"{canonical}:battle:{battle_id}",
            detail=detail,
        )

    target = _safe_success_target(result.get("target"))
    destination = _target_destination(target)
    formation_number = _expedition_formation_number(result)
    action = (
        f"编队{formation_number}"
        if formation_number is not None else "出征"
    )
    detail["target"] = target
    if formation_number is not None:
        detail["formationNumber"] = formation_number
    if _nonnegative_int(result.get("formationSourceRowIndex")) is not None:
        detail["formationSourceRowIndex"] = int(
            result["formationSourceRowIndex"]
        )
    if _nonnegative_int(result.get("sourceRowIndex")) is not None:
        detail["ruleSourceRowIndex"] = int(result["sourceRowIndex"])
    return _resident_success_record(
        timestamp=timestamp,
        category=label,
        message=(
            f"{action} > {destination}（battleId={battle_id}）"
            if destination else f"{action}成功（battleId={battle_id}）"
        ),
        dedupe_key=f"{canonical}:battle:{battle_id}",
        detail=detail,
    )


def _expedition_formation_number(result: Dict[str, Any]) -> Optional[int]:
    """The config row a dispatch came from, as the operator numbers it."""

    rule_index = _nonnegative_int(result.get("ruleSourceRowIndex"))
    if rule_index is None:
        rule_index = _nonnegative_int(result.get("sourceRowIndex"))
    if rule_index is not None:
        return rule_index + 1
    return _positive_int(result.get("formationNumber"))


def _resident_success_record(
    *,
    timestamp: int,
    category: str,
    message: str,
    dedupe_key: str,
    detail: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "id": int(timestamp),
        "time": int(timestamp),
        "timeText": _time_text(int(timestamp)),
        "category": str(category),
        "message": re.sub(r"\s+", " ", str(message)).strip()[:500],
        "source": "shared-resident",
        "dedupeKey": str(dedupe_key)[:200],
        "detail": deepcopy(detail),
    }


def _success_record_dedupe_key(record: Dict[str, Any]) -> str:
    direct = str(record.get("dedupeKey") or "").strip()
    if direct:
        return direct
    detail = record.get("detail")
    detail = detail if isinstance(detail, dict) else {}
    detail_key = str(detail.get("dedupeKey") or "").strip()
    if detail_key:
        return detail_key
    battle_id = _positive_int(detail.get("battleId"))
    if battle_id is None:
        match = re.search(
            r"\bbattleId\s*[=:]\s*(\d+)\b",
            str(record.get("message") or ""),
        )
        battle_id = int(match.group(1)) if match else None
    if battle_id is None:
        return ""
    feature = str(detail.get("feature") or "").strip()
    if feature == "brushYellow":
        feature = "brush"
    if not feature:
        feature = {
            "刷黄": "brush",
            "副本": "dungeon",
            "打矿": "mine",
            "掠夺": "raid",
            "无损": "lossless",
        }.get(str(record.get("category") or ""), "")
    return f"{feature}:battle:{battle_id}" if feature else ""


def _success_record_quality(record: Dict[str, Any]) -> int:
    detail = record.get("detail")
    detail = detail if isinstance(detail, dict) else {}
    score = 0
    if detail:
        score += 4
    if isinstance(detail.get("target"), dict) and detail["target"]:
        score += 2
    if isinstance(detail.get("stage"), dict) and detail["stage"]:
        score += 2
    if _positive_int(detail.get("formationNumber")) is not None:
        score += 3
    if str(record.get("dedupeKey") or "").strip():
        score += 1
    message = str(record.get("message") or "").strip()
    if re.match(r"^编队\d+\s*>", message):
        score += 2
    if message.endswith("> 目标") or " > 目标" in message:
        score -= 2
    return score


def _safe_success_target(value: Any) -> Dict[str, Any]:
    target = value if isinstance(value, dict) else {}
    return {
        key: deepcopy(target[key])
        for key in (
            "id", "targetId", "name", "kind", "type", "mineType",
            "level", "x", "y",
        )
        if key in target
    }


def _safe_success_stage(value: Any) -> Dict[str, Any]:
    stage = value if isinstance(value, dict) else {}
    return {
        key: deepcopy(stage[key])
        for key in (
            "chapter", "chapterName", "stage", "stageNumber", "stageId",
            "stageIdHex", "stageCode", "level", "levelName", "stageName",
        )
        if key in stage
    }


def _target_destination(target: Dict[str, Any]) -> str:
    name = str(
        target.get("name")
        or target.get("kind")
        or target.get("type")
        or target.get("mineType")
        or ""
    ).strip()
    x = target.get("x")
    y = target.get("y")
    if name and x is not None and y is not None:
        return f"{name}({x}，{y})"
    return name


def _dungeon_stage_text(stage: Dict[str, Any]) -> str:
    chapter = str(stage.get("chapterName") or "").strip()
    if not chapter and stage.get("chapter") not in (None, ""):
        chapter = f"第{stage.get('chapter')}章"
    stage_number = stage.get("stage")
    if stage_number in (None, ""):
        stage_number = stage.get("stageNumber")
    if chapter and stage_number not in (None, ""):
        return f"{chapter}第{stage_number}关"
    return str(
        stage.get("stageName") or stage.get("levelName") or chapter or ""
    ).strip()


def _lossless_stage_text(stage: Dict[str, Any]) -> str:
    level = _positive_int(stage.get("level"))
    if level is None:
        match = re.search(r"(\d+)\s*级", str(stage.get("levelName") or ""))
        level = int(match.group(1)) if match else None
    stage_name = str(stage.get("stageName") or "").strip()
    if level is not None and stage_name:
        return f"{level}级-{stage_name}"
    if stage_name:
        return stage_name
    return f"{level}级" if level is not None else ""


def _brush_formation_number(
    result: Dict[str, Any],
    *,
    public_state: Any = None,
) -> Optional[int]:
    # The brush rule row is the only authoritative user-facing identity.
    # ``formationSourceRowIndex`` belongs to the separate military troop table
    # and must never leak into brush labels.  Prefer the rule row even when an
    # older result also carries a now-known-wrong explicit formationNumber.
    numbered = _expedition_formation_number(result)
    if numbered is not None:
        return numbered

    rule_index = _nonnegative_int(result.get("ruleSourceRowIndex"))
    if rule_index is None:
        rule_index = _nonnegative_int(result.get("sourceRowIndex"))
    if not isinstance(public_state, dict):
        return None
    config = _json_object_value(public_state.get("residentAutomationConfigJson"))
    common = config.get("common")
    common = common if isinstance(common, dict) else {}
    brush = common.get("brush")
    brush = brush if isinstance(brush, dict) else {}
    rules = [row for row in brush.get("rules") or [] if isinstance(row, dict)]
    rule = next(
        (
            row for row in rules
            if _nonnegative_int(row.get("sourceRowIndex")) == rule_index
        ),
        None,
    )
    if rule is None and rule_index is not None and rule_index < len(rules):
        rule = rules[rule_index]
    if not isinstance(rule, dict):
        return None
    configured_rule_index = _nonnegative_int(rule.get("sourceRowIndex"))
    if configured_rule_index is not None:
        return configured_rule_index + 1
    # A very old configuration may not contain sourceRowIndex.  In that case
    # the rule's position in the brush list is still the brush-page identity.
    try:
        return rules.index(rule) + 1
    except ValueError:
        return None


def _json_object_value(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _json_list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return deepcopy(value)
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return []
        return decoded if isinstance(decoded, list) else []
    return []


def _positive_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _nonnegative_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _first_positive_int(source: Dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = _positive_int(source.get(key))
        if value is not None:
            return value
    return 0


def _log_entry(raw: Any, *, system: bool) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("日志条目必须是对象")
    timestamp = _bounded_int(
        raw.get("time", raw.get("timeMillis")), 0, 0
    )
    message = localize_user_text(raw.get("displayMessage", raw.get("message")))
    level = str(raw.get("level") or "").strip().lower()
    if level not in {"debug", "info", "warn", "warning", "error"}:
        level = "error" if any(marker in message for marker in _ERROR_MARKERS) else "info"
    if level == "warning":
        level = "warn"
    session_id = str(
        raw.get("sessionId")
        if raw.get("sessionId") is not None
        else raw.get("accountId") or ""
    )
    entry = {
        "id": _bounded_int(raw.get("id"), timestamp, 0),
        "time": timestamp,
        "timeText": str(raw.get("timeText") or _time_text(timestamp)),
        "level": level,
        "source": str(raw.get("source") or raw.get("tag") or ""),
        "sessionId": session_id,
        "accountKey": str(
            raw.get("accountKey")
            or (f"账号{session_id}" if system and session_id else "")
        ),
        "message": message,
    }
    if "detail" in raw:
        entry["detail"] = deepcopy(raw["detail"])
    return entry


def _map_record(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("地图记录必须是对象")
    fields = raw.get("filterFields")
    if fields is not None and not isinstance(fields, dict):
        raise ValueError("地图记录 filterFields 必须是对象")
    return raw


def _general_identity_matches(record: Dict[str, Any], requested: str) -> bool:
    expected_text = str(requested or "").strip()
    if not expected_text:
        return False
    direct_values = [
        _field_text(record, "id"),
        _field_text(record, "generalId"),
        _field_text(record, "jiangLingId"),
        _field_text(record, "idHex"),
    ]
    if expected_text in direct_values:
        return True
    expected_number = _identity_number(expected_text, hex_hint=False)
    if expected_number is None:
        return False
    for key in ("id", "generalId", "jiangLingId"):
        value = _field_text(record, key)
        if _identity_number(value, hex_hint=False) == expected_number:
            return True
    return _identity_number(
        _field_text(record, "idHex"),
        hex_hint=True,
    ) == expected_number


def _identity_number(value: Any, *, hex_hint: bool) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.removeprefix("0x").removeprefix("0X")
    base = 16 if hex_hint or any(char.lower() in "abcdef" for char in normalized) else 10
    try:
        parsed = int(normalized, base)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _map_updated_at(record: Dict[str, Any]) -> int:
    return _field_int(
        record,
        "updatedAt",
        "lastValidatedAtMillis",
        "lastSeenAt",
    ) or 0


def _map_record_is_fresh(
    record: Dict[str, Any],
    updated_at: int,
    now_millis: int,
    ttl_millis: int,
) -> bool:
    active = _field_bool(record, "active")
    if active is False:
        return False
    if record.get("invalidatedAtMillis") not in (None, "", 0, "0"):
        return False
    if _map_status(record) == "missing":
        return False
    age = int(now_millis) - int(updated_at)
    return updated_at > 0 and 0 <= age <= int(ttl_millis)


def _map_status(record: Dict[str, Any]) -> str:
    return _field_text(record, "status").strip().lower() or "available"


def _map_target_identity(
    record: Dict[str, Any],
) -> Optional[tuple[int, str]]:
    raw_hex = _field_text(
        record,
        "idHex",
        "targetIdHex",
        "resourcePointIdHex",
    ).lower().removeprefix("0x")
    clean_hex = re.sub(r"[^0-9a-f]", "", raw_hex)
    target_id = _field_optional_int(record, "targetId", "id")
    if clean_hex:
        try:
            from_hex = int(clean_hex, 16)
        except ValueError:
            from_hex = 0
        if from_hex > 0:
            target_id = from_hex
    if target_id is None or target_id <= 0:
        return None
    normalized_id = int(target_id) & ((1 << 64) - 1)
    if not clean_hex:
        clean_hex = format(normalized_id, "x")
    return normalized_id, clean_hex[-16:].rjust(16, "0")


def _bandit_composition_code(record: Dict[str, Any]) -> str:
    explicit = re.sub(
        r"\D",
        "",
        _field_text(record, "compositionCode"),
    )
    if explicit:
        return explicit
    composition = record.get("composition")
    values = []
    for key in ("foot", "bow", "cavalry", "chariot"):
        value = None
        if isinstance(composition, dict):
            value = _optional_int_value(composition.get(key))
        if value is None:
            value = _field_optional_int(record, key)
        if value is None:
            return ""
        values.append(value)
    return "".join(str(value) for value in values)


def _field_value(record: Dict[str, Any], *keys: str) -> Any:
    fields = record.get("filterFields")
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
        if (
            isinstance(fields, dict)
            and key in fields
            and fields[key] not in (None, "")
        ):
            return fields[key]
    return None


def _field_text(record: Dict[str, Any], *keys: str) -> str:
    value = _field_value(record, *keys)
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ""
    return str(value).strip()


def _optional_int_value(value: Any) -> Optional[int]:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _field_optional_int(record: Dict[str, Any], *keys: str) -> Optional[int]:
    for key in keys:
        value = _field_value(record, key)
        parsed = _optional_int_value(value)
        if parsed is not None:
            return parsed
    return None


def _field_int(record: Dict[str, Any], *keys: str) -> Optional[int]:
    return _field_optional_int(record, *keys)


def _field_bool(record: Dict[str, Any], *keys: str) -> Optional[bool]:
    for key in keys:
        value = _field_value(record, key)
        if isinstance(value, bool):
            return value
        normalized = str(value or "").strip().lower()
        if normalized in {"1", "true", "yes", "y"}:
            return True
        if normalized in {"0", "false", "no", "n"}:
            return False
    return None


def _field_string_values(record: Dict[str, Any], *keys: str) -> list[str]:
    value = _field_value(record, *keys)
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        text = str(value).strip()
        try:
            import json

            decoded = json.loads(text)
            values = decoded if isinstance(decoded, list) else []
        except (TypeError, ValueError):
            values = re.split(r"[,，、;；|/\s]+", text)
    output = []
    for item in values:
        text = str(item or "").strip()
        if text and text not in output:
            output.append(text)
    return output


def _field_int_values(record: Dict[str, Any], *keys: str) -> list[int]:
    output = []
    for value in _field_string_values(record, *keys):
        parsed = _optional_int_value(value)
        if parsed is not None and parsed not in output:
            output.append(parsed)
    return output


def _time_text(timestamp: int) -> str:
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp / 1000.0).strftime("%Y-%m-%d %H:%M:%S")


def _object(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label}必须是对象")
    return value


def _rows(value: Any) -> Iterable[Dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("投影条目必须是数组")
    return value


def _bounded_int(
    value: Any,
    default: int,
    minimum: int,
    maximum: Optional[int] = None,
) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    result = max(int(minimum), result)
    if maximum is not None:
        result = min(int(maximum), result)
    return result


def _optional_nonnegative_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None
