"""Host-neutral settings normalization and local write plans.

The shared core owns field semantics. Platform hosts persist the returned
feature-config objects atomically and may attach platform-only paths or runtime
facts after persistence; planning itself never performs game-network I/O.
"""

from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any, Dict

from .contracts import load_behavior_contract
from .features.daily import normalize_general_visit_ids, role_is_national_citizen
from .features.dungeon import (
    DUNGEON_CONTRACT,
    DUNGEON_MODE_CLEAR,
    DUNGEON_MODE_LOOP,
    dungeon_chapter_number,
    dungeon_chest_index,
    dungeon_stage_number,
    normalize_dungeon_mode,
)
from .features.formation import SOLDIER_TYPE_CODES
from .features.inventory import AUTO_OPEN_ITEM_NAMES
from .features.internal_affairs import TECHNOLOGY_NAMES
from .features.lossless import (
    LOSSLESS_CONTRACT,
    LOSSLESS_DAILY_LIMIT,
    LOSSLESS_GUARD_CONTRACT,
    LOSSLESS_MAX_LEVEL,
    lossless_level_number,
)
from .features.ministries import (
    ministry_courtesy_allowed,
    ministry_planting_allowed,
    normalize_ministry_settings,
    unconfirmed_ministry_actions,
)
from .features.targets import (
    MINE_BUSINESS_IDS,
    normalize_brush_levels,
    normalize_drop_keywords,
    parse_composition_code,
)


MILITARY_FUTURE_READINESS: Dict[str, Dict[str, Any]] = {
    "lossless": {
        "name": "无损",
        "status": "implemented",
        "message": (
            "已接入0x1900/02/04/06/08与0x1520/22；支持十级五阶段循环、"
            "10级卫兵阵容筛选和指挥中心优先级。"
        ),
        "evidence": (
            "ctf_out/passive_pcap_hotspot_20260710_185601/live_analyzed"
        ),
    },
    "dungeon": {
        "name": "副本",
        "status": "implemented",
        "message": (
            "已接入固定关卡循环与打通副本模式；打通模式按0x8930"
            "目录逐关推进，战败即暂停并提示。"
        ),
        "evidence": "ctf_out/dungeon_capture_20260706_023009/game_flows.json",
    },
    "escort": {
        "name": "押镖",
        "status": "capture_needed",
        "message": (
            "已确认 0x6273 为镖车列表/状态查询；仍缺选择镖车、"
            "派将发车、召回或结算写接口，当前只保存配置。"
        ),
        "evidence": (
            "ctf_out/passive_pcap_hotspot_20260711_150241/live_analyzed"
        ),
        "knownOpcodes": ["0x6273"],
        "neededCapture": [
            "选择一种镖车并派将出发",
            "发车成功后的状态查询",
            "如有撤军/被劫则保留完整返回",
        ],
    },
    "treasure": {
        "name": "寻宝",
        "status": "capture_needed",
        "message": (
            "已确认 0x627a 为寻宝信息查询，可读取“金山银山/"
            "镇国之宝”；仍缺刷新、选宝藏、派将和结算写接口，"
            "当前只保存配置。"
        ),
        "evidence": (
            "ctf_out/passive_pcap_hotspot_20260711_150241/live_analyzed"
        ),
        "knownOpcodes": ["0x627a"],
        "neededCapture": [
            "刷新藏宝图",
            "选择一个宝藏并派将出发",
            "寻宝结果/结算",
            "可选：加速或自动购买藏宝图",
        ],
    },
}

_MILITARY_FUTURE_FEATURE_CONFIG_IDS = {
    "lossless": "military_lossless",
    "dungeon": "dungeon",
    "escort": "military_future_escort",
    "treasure": "military_future_treasure",
}

_MINE_CONTRACT = load_behavior_contract()["mine"]
_MINE_RESOURCE_OPTIONS = frozenset(MINE_BUSINESS_IDS)
_MINE_MAX_GENERALS = int(_MINE_CONTRACT["maximumGeneralsPerFormation"])
_MINE_ALLOWED_SCOPES = frozenset(_MINE_CONTRACT["allowedSearchScopes"])
_MINE_DEFAULT_SCOPE = str(_MINE_CONTRACT["defaultSearchScope"])
_MINE_ALLOWED_MARCH_MINUTES = frozenset(
    int(value) for value in _MINE_CONTRACT["allowedMaxMarchMinutes"]
)
_MINE_DEFAULT_MARCH_MINUTES = int(_MINE_CONTRACT["defaultMaxMarchMinutes"])

_RAID_CONTRACT = load_behavior_contract()["raid"]
_RAID_MAX_GENERALS = int(_RAID_CONTRACT["maximumGeneralsPerFormation"])

_LOSSLESS_MAX_GENERALS = int(
    LOSSLESS_CONTRACT["maximumGeneralsPerFormation"]
)
_LOSSLESS_DEFAULT_MAX_REROLLS = int(
    LOSSLESS_GUARD_CONTRACT["defaultMaxRerolls"]
)
_LOSSLESS_MAX_REROLLS = int(
    LOSSLESS_GUARD_CONTRACT["maximumMaxRerolls"]
)

_DUNGEON_MAX_GENERALS = int(
    DUNGEON_CONTRACT["maximumGeneralsPerFormation"]
)
_DUNGEON_CHEST_NAMES = tuple(str(value) for value in DUNGEON_CONTRACT["chestNames"])

_BRUSH_CONTRACT = load_behavior_contract()["brushYellow"]
_BRUSH_MAX_GENERALS = int(_BRUSH_CONTRACT["maximumGeneralsPerFormation"])
_BRUSH_MIN_ROLE_LEVEL = int(_BRUSH_CONTRACT["minimumRoleLevel"])
_BRUSH_HIGH_TROOP_LEVELS = frozenset((9, 10))
_BRUSH_HIGH_LEVEL_MIN_TROOPS = 1000
_DEFAULT_RECONNECT_DELAY_MINUTES = 5
_DEFAULT_BRUSH_DROPS = ("宝物", "资源", "装备", "宝箱")
_EQUIPMENT_QUALITY_NAMES = ("普通", "良好", "优秀", "卓越")
_DAILY_TASK_NAMES = (
    "autoSignIn",
    "arenaCoins",
    "autoDonate",
    "salary",
    "nationalCollect",
    "cityLordCollect",
    "generalVisit",
)
_SETTINGS_SCOPE_FIELDS = {
    "common.frequent": {
        "dailyLimit",
        "healWounded",
        "autoEnergy",
        "energyThreshold",
        "foodToCopper",
        "copperFloorWan",
        "domestic",
    },
    "common.daily": {"dailyTasks", "generalVisitGeneralIds"},
    "common.items": {
        "cleanInventory",
        "discardItemNames",
        "discardEquipment",
        "maxEquipmentQuality",
        "discardEquipmentQualities",
        "maxEquipmentLevel",
        "autoOpenItemNames",
        "autoOpenEnabled",
    },
    "common.chain": {"chainInventory"},
    "common.alarm": {"alarm"},
    "brush": {
        "autoStart",
        "reconnectDelayMinutes",
        "startHour",
        "dailyLimit",
        "cycleDelaySec",
        "returnWaitSec",
        "replenishTroops",
        "foodToCopper",
        "copperFloorWan",
        "cleanMail",
        "brush",
    },
}
_SETTINGS_SCOPE_NESTED_FIELDS = {
    ("common.frequent", "domestic"): {
        "enabled",
        "emptyBuildingType",
        "upgradeBuildings",
        "upgradeLowestFirst",
        "buildingPriority",
        "upgradeTechnology",
        "technologyId",
        "technologyIds",
        "technologyTargetLevel",
    },
    ("common.daily", "dailyTasks"): set(_DAILY_TASK_NAMES),
    ("common.chain", "chainInventory"): {
        "enabled",
        "keepItemName",
        "keepCount",
        "autoOpenEnabled",
        "autoOpenItemNames",
    },
    ("common.alarm", "alarm"): {
        "incomingEnabled",
        "incomingMode",
        "incomingKeywords",
        "militaryEnabled",
        "militaryMode",
        "errorEnabled",
        "vibrateOnAlarm",
    },
}


def project_account_settings(
    *,
    account: Any,
    config_dir: Any,
    file_name: Any,
    file_path: Any,
    settings: Any,
    exists: bool = True,
) -> Dict[str, Any]:
    """Build the one frontend settings-file view used by both hosts."""

    if not isinstance(account, dict):
        raise ValueError("设置读取缺少公开账号卡")
    if settings is not None and not isinstance(settings, dict):
        raise ValueError("设置快照必须是对象")
    normalized_exists = bool(exists)
    normalized_settings = deepcopy(settings) if isinstance(settings, dict) else {}
    content = (
        json.dumps(
            normalized_settings,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        if normalized_exists
        else ""
    )
    return {
        "ok": True,
        "account": deepcopy(account),
        "configDir": str(config_dir or ""),
        "files": [
            {
                "name": str(file_name or "account_settings.json"),
                "path": str(file_path or config_dir or ""),
                "exists": normalized_exists,
                "content": content,
            }
        ],
    }


def normalize_military_future_settings(
    feature: str,
    settings: Any,
) -> Dict[str, Any]:
    """Normalize one future-military form without enabling unverified I/O."""

    key = str(feature or "").strip()
    if key not in MILITARY_FUTURE_READINESS:
        raise ValueError(f"未知军事功能：{feature}")
    normalized = deepcopy(settings) if isinstance(settings, dict) else {}
    rows = normalized.get("rows")
    if isinstance(rows, list):
        next_rows = []
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                continue
            row = deepcopy(raw_row)
            raw_ids = row.get("generalIds")
            if isinstance(raw_ids, list):
                general_ids = [
                    str(value)
                    for value in raw_ids
                    if str(value or "").strip()
                ]
            elif row.get("generalId"):
                general_ids = [str(row.get("generalId"))]
            else:
                general_ids = []
            if key in {"dungeon", "lossless"}:
                row["enabled"] = row.get("enabled") is True
            row["generalIds"] = list(dict.fromkeys(general_ids))
            row["generalId"] = general_ids[0] if general_ids else ""
            next_rows.append(row)
        normalized["rows"] = next_rows
    if key == "dungeon":
        mode_value = normalized.get("mode")
        if mode_value in (None, "") and "clearStages" in normalized:
            mode_value = normalized.get("clearStages")
        normalized["mode"] = normalize_dungeon_mode(mode_value)
    return normalized


def settings_write_plan(route: str, body: Any) -> Dict[str, Any]:
    """Return normalized local writes plus host-neutral response fields."""

    normalized_route = str(route or "").split("?", 1)[0]
    request = deepcopy(body) if isinstance(body, dict) else {}
    if normalized_route == "/api/military/future/save":
        return _future_military_write_plan(normalized_route, request)
    if normalized_route == "/api/liubu/save":
        return _ministry_write_plan(normalized_route, request)
    if normalized_route == "/api/formations/save":
        return _formation_write_plan(normalized_route, request)
    if normalized_route == "/api/mine/save":
        return _mine_write_plan(normalized_route, request)
    if normalized_route == "/api/settings/save":
        return _scoped_settings_write_plan(normalized_route, request)
    if normalized_route == "/api/raid/execute":
        return _raid_write_plan(normalized_route, request)
    if normalized_route == "/api/lossless/execute":
        return _lossless_write_plan(normalized_route, request)
    if normalized_route == "/api/dungeon/execute":
        return _dungeon_write_plan(normalized_route, request)
    raise ValueError(f"共享设置核心尚未迁移该接口：{normalized_route}")


def _future_military_write_plan(
    route: str,
    request: Dict[str, Any],
) -> Dict[str, Any]:
    feature = str(request.get("feature") or "").strip()
    settings = normalize_military_future_settings(
        feature,
        request.get("settings") or {},
    )
    readiness = deepcopy(MILITARY_FUTURE_READINESS[feature])
    executable = readiness.get("status") == "implemented"
    enabled = any(
        isinstance(row, dict) and row.get("enabled") is True
        for row in settings.get("rows") or []
    )
    return {
        "route": route,
        "configs": {
            _MILITARY_FUTURE_FEATURE_CONFIG_IDS[feature]: settings,
        },
        "disabled": not (executable and enabled),
        "activationAllowed": executable and enabled,
        "networkRequired": False,
        "response": {
            "feature": feature,
            "settings": settings,
            "readiness": readiness,
        },
    }


def _ministry_write_plan(
    route: str,
    request: Dict[str, Any],
) -> Dict[str, Any]:
    raw_settings = request.get("settings")
    if not isinstance(raw_settings, dict):
        raise ValueError("六部保存缺少 settings")
    settings = normalize_ministry_settings({"settings": raw_settings})
    planting_supported = ministry_planting_allowed(settings)
    courtesy_supported = ministry_courtesy_allowed(settings)
    supported = planting_supported or courtesy_supported
    requested = any(
        settings.get(key)
        for key in (
            "cropEnabled",
            "stealEnabled",
            "courtesyEnabled",
            "salaryRefresh",
        )
    )
    config = {
        **settings,
        "enabled": supported,
        "supportedEnabled": supported,
        "requested": requested,
    }
    verified = []
    if planting_supported:
        verified.append("稻谷种植采摘")
    if courtesy_supported:
        verified.append("礼部任务委派")
    if not requested:
        reason = "六部任务已关闭"
    elif supported:
        reason = f"六部设置已保存，由账号任务队列执行{'、'.join(verified)}"
    elif settings.get("cropEnabled"):
        reason = f"{settings.get('crop')}协议尚未确认；配置已保存但不会发送"
    else:
        reason = "种菜收菜和礼部未开启；偷菜和俸禄刷新协议尚未完整确认，当前不发送"
    return {
        "route": route,
        "configs": {"six_ministries": config},
        "disabled": not requested,
        "activationAllowed": supported,
        "networkRequired": False,
        "response": {
            "settings": config,
            "requested": requested,
            "supportedEnabled": supported,
            "unconfirmedActions": unconfirmed_ministry_actions(settings),
            "reason": reason,
        },
    }


def _formation_write_plan(
    route: str,
    request: Dict[str, Any],
) -> Dict[str, Any]:
    raw_rows = request.get("formations")
    if not isinstance(raw_rows, list):
        raise ValueError("配兵保存缺少 formations")
    known_generals = request.get("knownGenerals")
    known_generals = known_generals if isinstance(known_generals, list) else []
    known_ids: set[str] = set()
    known_names: Dict[str, str] = {}
    for raw_general in known_generals:
        if not isinstance(raw_general, dict):
            continue
        name = str(raw_general.get("name") or "").strip()
        for value in (raw_general.get("id"), raw_general.get("idHex")):
            identity = str(value or "").strip()
            if not identity:
                continue
            known_ids.add(identity)
            if name:
                known_names[identity] = name

    ui_rows = []
    normalized_rows = []
    unresolved_ids = []
    unresolved_seen: set[str] = set()
    configured_ids: set[str] = set()
    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, dict):
            continue
        row = deepcopy(raw_row)
        enabled = row.get("enabled", True) is True
        raw_ids = row.get("generalIds")
        if isinstance(raw_ids, list):
            ids = [
                str(value).strip()
                for value in raw_ids
                if str(value or "").strip()
            ]
        else:
            fallback = str(row.get("generalId") or "").strip()
            ids = [fallback] if fallback else []
        ids = list(dict.fromkeys(ids))
        if len(ids) > 5:
            raise ValueError(f"第 {index + 1} 条配兵规则一次最多选择5名将领")
        if enabled and not ids:
            raise ValueError(f"第 {index + 1} 条启用的配兵规则未选择将领")
        soldier_type = str(row.get("soldierType") or "轻骑兵").strip()
        soldier_code = None
        try:
            soldier_code = int(soldier_type)
        except (TypeError, ValueError):
            pass
        if enabled and not (
            soldier_type in SOLDIER_TYPE_CODES
            or soldier_code in SOLDIER_TYPE_CODES.values()
        ):
            raise ValueError(f"第 {index + 1} 条配兵规则兵种无效：{soldier_type}")
        try:
            soldier_count = int(row.get("soldierCount") or 0)
        except (TypeError, ValueError) as error:
            raise ValueError(f"第 {index + 1} 条配兵规则兵力数量无效") from error
        if enabled and soldier_count <= 0:
            raise ValueError(f"第 {index + 1} 条配兵规则兵力数量必须大于 0")
        snapshots = (
            deepcopy(row.get("generalNameSnapshots"))
            if isinstance(row.get("generalNameSnapshots"), dict)
            else {}
        )
        for general_id in ids:
            if known_names.get(general_id):
                snapshots[general_id] = known_names[general_id]
        row.update(
            enabled=enabled,
            generalIds=ids,
            generalId=ids[0] if ids else "",
            soldierType=soldier_type,
            soldierCount=max(0, soldier_count),
        )
        if snapshots:
            row["generalNameSnapshots"] = snapshots
        ui_rows.append(row)

        if not enabled:
            continue
        for general_id in ids:
            if general_id in configured_ids:
                raise ValueError(f"将领 {general_id} 被重复配置，请只在一个配兵规则里选择它")
            configured_ids.add(general_id)
            if known_ids and general_id not in known_ids and general_id not in unresolved_seen:
                unresolved_seen.add(general_id)
                unresolved_ids.append(general_id)
            normalized = {
                "enabled": True,
                "generalId": general_id,
                "generalIds": [general_id],
                "soldierType": soldier_type,
                "soldierCount": soldier_count,
                "sourceRowIndex": index,
            }
            if snapshots:
                normalized["generalNameSnapshots"] = deepcopy(snapshots)
            normalized_rows.append(normalized)

    raw_options = request.get("formationOptions")
    raw_options = raw_options if isinstance(raw_options, dict) else {}
    options = {
        "clearOtherGenerals": bool(
            raw_options.get("clearOtherGenerals")
            or request.get("clearOtherGenerals")
        )
    }
    enabled = bool(normalized_rows)
    activation_allowed = enabled and not unresolved_ids
    if not enabled:
        apply_reason = "没有启用的配兵规则"
    elif unresolved_ids:
        apply_reason = (
            f"当前同步未找到将领 ID：{','.join(unresolved_ids)}；"
            "配置已保留，刷新角色状态后再执行"
        )
    else:
        apply_reason = "设置已保存，配兵应用是独立的账号网络任务"
    return {
        "route": route,
        "configs": {
            "formation_troop": {
                "enabled": enabled,
                "clearOtherGenerals": options["clearOtherGenerals"],
                "rows": ui_rows,
            }
        },
        "disabled": not enabled,
        "activationAllowed": activation_allowed,
        "networkRequired": False,
        "followUpOperation": {
            "kind": "apply-formations",
            "required": activation_allowed,
        },
        "response": {
            "formations": ui_rows,
            "normalizedFormations": normalized_rows,
            "formationOptions": options,
            "unresolvedGeneralIds": unresolved_ids,
            "applyReason": apply_reason,
        },
    }


def _mine_write_plan(
    route: str,
    request: Dict[str, Any],
) -> Dict[str, Any]:
    raw_settings = request.get("settings")
    if not isinstance(raw_settings, dict):
        raise ValueError("打矿保存缺少 settings")
    settings = deepcopy(raw_settings)
    raw_rows = settings.get("rows")
    raw_rows = raw_rows if isinstance(raw_rows, list) else []

    known_generals = request.get("knownGenerals")
    known_generals = known_generals if isinstance(known_generals, list) else []
    known_ids = {
        str(value).strip()
        for general in known_generals
        if isinstance(general, dict)
        for value in (general.get("id"), general.get("idHex"))
        if str(value or "").strip()
    }

    ui_rows = []
    execution_rows = []
    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, dict):
            raise ValueError(f"第 {index + 1} 条打矿规则不是对象")
        ui_row = deepcopy(raw_row)
        ui_rows.append(ui_row)
        if not bool(ui_row.get("enabled", False)):
            continue
        raw_ids = ui_row.get("generalIds")
        if isinstance(raw_ids, list):
            general_ids = [
                str(value).strip()
                for value in raw_ids
                if str(value or "").strip()
            ]
        else:
            fallback = str(ui_row.get("generalId") or "").strip()
            general_ids = [fallback] if fallback else []
        general_ids = list(dict.fromkeys(general_ids))
        if not general_ids:
            raise ValueError(f"第 {index + 1} 条打矿规则未选择出征将领")
        if len(general_ids) > _MINE_MAX_GENERALS:
            raise ValueError(
                f"第 {index + 1} 条打矿规则最多选择"
                f"{_MINE_MAX_GENERALS}名出征将领"
            )
        missing = [
            general_id
            for general_id in general_ids
            if known_ids and general_id not in known_ids
        ]
        if missing:
            raise ValueError(
                f"第 {index + 1} 条打矿规则存在不属于当前账号的将领："
                + ",".join(missing)
            )
        resource_type = str(ui_row.get("resourceType") or "").strip()
        if resource_type not in _MINE_RESOURCE_OPTIONS:
            raise ValueError(f"第 {index + 1} 条打矿规则未选择有效资源类型")
        scope = str(ui_row.get("scope") or _MINE_DEFAULT_SCOPE)
        if scope not in _MINE_ALLOWED_SCOPES:
            scope = _MINE_DEFAULT_SCOPE
        try:
            x = max(0, min(int(ui_row.get("x") or 0), 186))
            y = max(0, min(int(ui_row.get("y") or 0), 66))
            level = int(ui_row.get("level") or 0) or None
        except (TypeError, ValueError) as error:
            raise ValueError(f"第 {index + 1} 条打矿规则坐标或等级无效") from error
        execution_rows.append(
            {
                "enabled": True,
                "sourceRowIndex": index,
                "generalIds": general_ids,
                "generalId": general_ids[0],
                "resourceType": resource_type,
                "level": level,
                "x": x,
                "y": y,
                "scope": scope,
                "onlyEmpty": bool(ui_row.get("onlyEmpty", False)),
                "onlyDefended": bool(ui_row.get("onlyDefended", False)),
            }
        )

    try:
        max_march_minutes = int(
            settings.get("maxMarchMinutes") or _MINE_DEFAULT_MARCH_MINUTES
        )
        center_x = max(0, min(int(settings.get("centerX") or 0), 186))
        center_y = max(0, min(int(settings.get("centerY") or 0), 66))
    except (TypeError, ValueError) as error:
        raise ValueError("打矿中心坐标或最大行军时间无效") from error
    if max_march_minutes not in _MINE_ALLOWED_MARCH_MINUTES:
        max_march_minutes = _MINE_DEFAULT_MARCH_MINUTES
    speed_value = settings.get("speed")
    speed = (
        speed_value
        if isinstance(speed_value, bool)
        else str(speed_value or "不加速").strip()
        not in {"", "不加速", "false", "False", "0"}
    )
    enabled = bool(execution_rows)
    persisted = {
        "enabled": enabled,
        "speed": speed,
        "fullLoyalty": bool(settings.get("fullLoyalty", True)),
        "replenishTroops": bool(settings.get("replenishTroops", True)),
        "maxMarchMinutes": max_march_minutes,
        "centerX": center_x,
        "centerY": center_y,
        # 自动打矿只允许未被玩家占领的资源点，旧字段不得重新启用。
        "targetPlayerName": "",
        "rows": ui_rows,
    }
    reason = (
        "打矿设置已保存，由账号任务队列异步执行"
        if enabled
        else "未启用任何打矿编队"
    )
    return {
        "route": route,
        "configs": {"auto_mining": persisted},
        "disabled": not enabled,
        "activationAllowed": enabled,
        "networkRequired": False,
        "followUpOperation": {
            "kind": "auto-mine",
            "required": enabled,
        },
        "response": {
            "settings": persisted,
            "executionRows": execution_rows,
            "reason": reason,
        },
    }


def _normalized_enabled_general_ids(
    row: Dict[str, Any],
    *,
    row_index: int,
    feature_name: str,
    maximum: int,
    known_ids: set[str],
) -> list[str]:
    raw_ids = row.get("generalIds")
    if isinstance(raw_ids, list):
        general_ids = [
            str(value).strip()
            for value in raw_ids
            if str(value or "").strip()
        ]
    else:
        fallback = str(row.get("generalId") or "").strip()
        general_ids = [fallback] if fallback else []
    general_ids = list(dict.fromkeys(general_ids))
    if not general_ids:
        raise ValueError(
            f"第 {row_index + 1} 条{feature_name}规则未选择出征将领"
        )
    if len(general_ids) > maximum:
        raise ValueError(
            f"第 {row_index + 1} 条{feature_name}规则最多选择"
            f"{maximum}名出征将领"
        )
    missing = [
        general_id
        for general_id in general_ids
        if known_ids and general_id not in known_ids
    ]
    if missing:
        raise ValueError(
            f"第 {row_index + 1} 条{feature_name}规则存在不属于当前账号的将领："
            + ",".join(missing)
        )
    return general_ids


def _raid_write_plan(
    route: str,
    request: Dict[str, Any],
) -> Dict[str, Any]:
    if str(request.get("confirm") or "") != "raid":
        raise ValueError("真实掠夺需要 confirm=raid")
    raw_rows = request.get("rows")
    if not isinstance(raw_rows, list):
        raw_rows = [request]
    known_ids = _known_general_ids(request.get("knownGenerals"))
    ui_rows = []
    execution_rows = []
    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, dict):
            raise ValueError(f"第 {index + 1} 条掠夺规则不是对象")
        row = deepcopy(raw_row)
        enabled = row.get("enabled", True) is not False
        raw_ids = row.get("generalIds")
        if isinstance(raw_ids, list):
            general_ids = [
                str(value).strip()
                for value in raw_ids
                if str(value or "").strip()
            ]
        else:
            fallback = str(row.get("generalId") or "").strip()
            general_ids = [fallback] if fallback else []
        general_ids = list(dict.fromkeys(general_ids))
        player_name = str(
            row.get("playerName") or row.get("targetPlayer") or ""
        ).strip()
        try:
            fief_index = int(row.get("fiefIndex") or row.get("fiefNo") or 0)
        except (TypeError, ValueError) as error:
            if enabled:
                raise ValueError(
                    f"第 {index + 1} 条掠夺规则封地序号无效"
                ) from error
            fief_index = 0
        full_troops = bool(
            row.get("fullTroops", _RAID_CONTRACT["fullTroopsDefault"])
        )
        full_loyalty = bool(
            row.get("fullLoyalty", _RAID_CONTRACT["fullLoyaltyDefault"])
        )
        duration = str(row.get("duration") or request.get("duration") or "立即出征")
        row.update(
            enabled=enabled,
            generalIds=general_ids,
            generalId=general_ids[0] if general_ids else "",
            playerName=player_name,
            fiefIndex=fief_index,
            fullTroops=full_troops,
            fullLoyalty=full_loyalty,
            duration=duration,
        )
        ui_rows.append(row)
        if not enabled:
            continue
        general_ids = _normalized_enabled_general_ids(
            row,
            row_index=index,
            feature_name="掠夺",
            maximum=_RAID_MAX_GENERALS,
            known_ids=known_ids,
        )
        if not player_name:
            raise ValueError(f"第 {index + 1} 条掠夺规则未填写玩家名称")
        if fief_index <= 0:
            raise ValueError(
                f"第 {index + 1} 条掠夺规则封地序号必须大于 0"
            )
        execution_rows.append(
            {
                "enabled": True,
                "sourceRowIndex": index,
                "generalIds": general_ids,
                "generalId": general_ids[0],
                "playerName": player_name,
                "fiefIndex": fief_index,
                "fullTroops": full_troops,
                "fullLoyalty": full_loyalty,
                "duration": duration,
            }
        )
    if not execution_rows:
        raise ValueError("至少需要勾选一条掠夺规则")
    first = execution_rows[0]
    persisted = {
        "enabled": True,
        "auto_loot_enabled": True,
        "selectedGeneralIds": list(first["generalIds"]),
        "fullTroops": bool(first["fullTroops"]),
        "fullLoyalty": bool(first["fullLoyalty"]),
        "duration": str(first["duration"]),
        "rows": ui_rows,
    }
    return {
        "route": route,
        "configs": {"auto_loot": persisted},
        "disabled": False,
        "activationAllowed": True,
        "networkRequired": False,
        "followUpOperation": {"kind": "raid", "required": True},
        "response": {
            "settings": persisted,
            "rows": ui_rows,
            "executionRows": execution_rows,
            "reason": "掠夺设置已保存，由账号任务队列异步执行",
        },
    }


def _lossless_write_plan(
    route: str,
    request: Dict[str, Any],
) -> Dict[str, Any]:
    if str(request.get("confirm") or "") != "lossless":
        raise ValueError("真实无损需要confirm=lossless")
    raw_settings = request.get("settings")
    if not isinstance(raw_settings, dict):
        raise ValueError("无损保存缺少 settings")
    settings = normalize_military_future_settings("lossless", raw_settings)
    known_ids = _known_general_ids(request.get("knownGenerals"))
    ui_rows = []
    execution_rows = []
    top_full_troops = bool(
        settings.get("fullTroops", LOSSLESS_CONTRACT["fullTroopsDefault"])
    )
    for index, raw_row in enumerate(settings.get("rows") or []):
        if not isinstance(raw_row, dict):
            raise ValueError(f"第 {index + 1} 条无损规则不是对象")
        row = deepcopy(raw_row)
        enabled = row.get("enabled") is True
        try:
            level = lossless_level_number(
                row.get("level")
                if row.get("level") is not None
                else LOSSLESS_MAX_LEVEL
            )
        except RuntimeError as error:
            if enabled:
                raise ValueError(str(error)) from error
            level = LOSSLESS_MAX_LEVEL
        max_rerolls = _int_setting(
            row.get("maxLineupRerolls"),
            _LOSSLESS_DEFAULT_MAX_REROLLS,
            1,
            _LOSSLESS_MAX_REROLLS,
        )
        full_troops = bool(row.get("fullTroops", top_full_troops))
        row.update(
            enabled=enabled,
            level=f"{level}级",
            levelName=f"{level}级",
            fullTroops=full_troops,
            maxLineupRerolls=max_rerolls,
        )
        ui_rows.append(row)
        if not enabled:
            continue
        general_ids = _normalized_enabled_general_ids(
            row,
            row_index=index,
            feature_name="无损",
            maximum=_LOSSLESS_MAX_GENERALS,
            known_ids=known_ids,
        )
        execution_rows.append(
            {
                "enabled": True,
                "sourceRowIndex": index,
                "generalIds": general_ids,
                "generalId": general_ids[0],
                "level": level,
                "levelName": f"{level}级",
                "fullTroops": full_troops,
                "maxLineupRerolls": max_rerolls,
            }
        )
    enabled = bool(execution_rows)
    persisted = {
        **settings,
        "enabled": enabled,
        "fullTroops": top_full_troops,
        "dailyLimit": _int_setting(
            settings.get("dailyLimit"),
            LOSSLESS_DAILY_LIMIT,
            1,
            LOSSLESS_DAILY_LIMIT,
        ),
        "rows": ui_rows,
    }
    reason = (
        "无损设置已保存，由账号任务队列异步执行"
        if enabled
        else "未启用任何无损编队，无损常驻任务已关闭"
    )
    return {
        "route": route,
        "configs": {"military_lossless": persisted},
        "disabled": not enabled,
        "activationAllowed": enabled,
        "networkRequired": False,
        "followUpOperation": {"kind": "lossless", "required": enabled},
        "response": {
            "settings": persisted,
            "rows": ui_rows,
            "executionRows": execution_rows,
            "reason": reason,
        },
    }


def _dungeon_write_plan(
    route: str,
    request: Dict[str, Any],
) -> Dict[str, Any]:
    if str(request.get("confirm") or "") != "dungeon":
        raise ValueError("真实副本需要 confirm=dungeon")
    raw_rows = request.get("rows")
    if not isinstance(raw_rows, list):
        raw_rows = [request]
    settings = normalize_military_future_settings(
        "dungeon",
        {
            "rows": raw_rows,
            "mode": request.get("mode"),
            "clearStages": request.get("clearStages"),
        },
    )
    mode = normalize_dungeon_mode(settings.get("mode"))
    enabled_count = sum(
        1
        for row in settings.get("rows") or []
        if isinstance(row, dict) and row.get("enabled") is True
    )
    if enabled_count > 1:
        raise ValueError("副本编队同一时间只能启用一条")
    known_ids = _known_general_ids(request.get("knownGenerals"))
    ui_rows = []
    execution_rows = []
    for index, raw_row in enumerate(settings.get("rows") or []):
        if not isinstance(raw_row, dict):
            raise ValueError(f"第 {index + 1} 条副本规则不是对象")
        row = deepcopy(raw_row)
        enabled = row.get("enabled") is True
        ui_rows.append(row)
        if not enabled:
            continue
        general_ids = _normalized_enabled_general_ids(
            row,
            row_index=index,
            feature_name="副本",
            maximum=_DUNGEON_MAX_GENERALS,
            known_ids=known_ids,
        )
        chapter_label = row.get("chapterName")
        if chapter_label in (None, ""):
            chapter_label = row.get("chapter")
        stage_value = row.get("stage")
        if stage_value is None:
            stage_value = row.get("level")
        if mode == DUNGEON_MODE_CLEAR:
            try:
                chapter = dungeon_chapter_number(
                    chapter_label if chapter_label is not None else "第一章"
                )
            except RuntimeError:
                chapter = 0
            try:
                stage = dungeon_stage_number(
                    stage_value if stage_value is not None else 1,
                    chapter,
                )
            except RuntimeError:
                stage = 1
        else:
            try:
                chapter = dungeon_chapter_number(
                    chapter_label if chapter_label is not None else "第一章"
                )
                stage = dungeon_stage_number(
                    stage_value if stage_value is not None else 1,
                    chapter,
                )
            except RuntimeError as error:
                raise ValueError(str(error)) from error
        chest_value = row.get("chest")
        if chest_value is None:
            chest_value = row.get("chestName")
        try:
            chest = dungeon_chest_index(
                chest_value if chest_value is not None else "右"
            )
        except RuntimeError as error:
            raise ValueError(str(error)) from error
        chapter_name = str(
            row.get("chapterName")
            or row.get("chapter")
            or f"第{chapter + 1}章"
        )
        row.update(
            enabled=True,
            generalIds=general_ids,
            generalId=general_ids[0],
            chapterName=chapter_name,
            chest=_DUNGEON_CHEST_NAMES[chest],
            chestName=_DUNGEON_CHEST_NAMES[chest],
        )
        execution_rows.append(
            {
                "enabled": True,
                "sourceRowIndex": index,
                "generalIds": general_ids,
                "generalId": general_ids[0],
                "chapter": chapter,
                "chapterName": chapter_name,
                "stage": stage,
                "chest": chest,
                "chestName": _DUNGEON_CHEST_NAMES[chest],
                "fullTroops": bool(row.get("fullTroops", False)),
                "waitForGeneralsIdle": True,
                "openChest": True,
            }
        )
    enabled = bool(execution_rows)
    persisted = {
        "enabled": enabled,
        "mode": mode,
        "autoUnlockUntilTarget": mode == DUNGEON_MODE_CLEAR,
        "dailyTimes": _int_setting(request.get("dailyTimes"), 999, 1),
        "rows": ui_rows,
    }
    if execution_rows:
        first = execution_rows[0]
        persisted.update(
            selectedGeneralIds=list(first["generalIds"]),
            chapter=int(first["chapter"]),
            stage=int(first["stage"]),
            boxPosition=int(first["chest"]),
        )
    reason = (
        "副本设置已保存，由账号任务队列异步执行"
        if enabled
        else "未启用任何副本编队，副本常驻任务已关闭"
    )
    return {
        "route": route,
        "configs": {"dungeon": persisted},
        "disabled": not enabled,
        "activationAllowed": enabled,
        "networkRequired": False,
        # The host performs this fast local action only after the settings
        # write succeeds. Python still decides whether the retained ledger is
        # an acknowledged defeat which is safe to archive.
        "acknowledgeDefeatOnSave": enabled,
        "followUpOperation": {"kind": "dungeon", "required": enabled},
        "response": {
            "settings": persisted,
            "rows": ui_rows,
            "mode": mode,
            "executionRows": execution_rows,
            "reason": reason,
        },
    }


def _merge_settings_scope_patch(
    old_config: Dict[str, Any],
    scope: str,
    patch: Dict[str, Any],
) -> Dict[str, Any]:
    if scope not in _SETTINGS_SCOPE_FIELDS:
        raise ValueError(f"未知设置保存范围：{scope}")
    if not isinstance(patch, dict):
        raise ValueError("设置 patch 必须是对象")
    merged = deepcopy(old_config) if isinstance(old_config, dict) else {}
    if not merged and scope.startswith("common."):
        merged["autoStart"] = False
    for key in _SETTINGS_SCOPE_FIELDS[scope]:
        if key not in patch:
            continue
        value = deepcopy(patch[key])
        nested_fields = _SETTINGS_SCOPE_NESTED_FIELDS.get((scope, key))
        if nested_fields is None:
            merged[key] = value
            continue
        source = value if isinstance(value, dict) else {}
        current = merged.get(key) if isinstance(merged.get(key), dict) else {}
        next_value = deepcopy(current)
        for nested_key in nested_fields:
            if nested_key in source:
                next_value[nested_key] = deepcopy(source[nested_key])
        merged[key] = next_value
    return merged


def _int_setting(
    value: Any,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = int(default)
    if minimum is not None:
        normalized = max(minimum, normalized)
    if maximum is not None:
        normalized = min(maximum, normalized)
    return normalized


def _known_general_ids(generals: Any) -> set[str]:
    if not isinstance(generals, list):
        return set()
    return {
        str(value).strip()
        for general in generals if isinstance(general, dict)
        for value in (general.get("id"), general.get("idHex"))
        if str(value or "").strip()
    }


def _known_general_names(generals: Any) -> Dict[str, str]:
    names: Dict[str, str] = {}
    if not isinstance(generals, list):
        return names
    for general in generals:
        if not isinstance(general, dict):
            continue
        name = str(general.get("name") or "").strip()
        if not name:
            continue
        for value in (general.get("id"), general.get("idHex")):
            identity = str(value or "").strip()
            if identity:
                names[identity] = name
    return names


def _formation_index(formations: Any) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    if not isinstance(formations, list):
        return indexed
    for raw in formations:
        if not isinstance(raw, dict) or raw.get("enabled", True) is not True:
            continue
        raw_ids = raw.get("generalIds")
        if isinstance(raw_ids, list):
            ids = [str(value).strip() for value in raw_ids if str(value or "").strip()]
        else:
            fallback = str(raw.get("generalId") or "").strip()
            ids = [fallback] if fallback else []
        for general_id in dict.fromkeys(ids):
            row = deepcopy(raw)
            row["generalId"] = general_id
            row["generalIds"] = [general_id]
            indexed[general_id] = row
    return indexed


def normalize_automation_config(
    config: Any,
    *,
    session_id: Any,
    known_generals: Any = None,
    saved_formations: Any = None,
    resolve_brush_formations: bool = True,
) -> Dict[str, Any]:
    """Normalize the shared settings model without reading host state or network."""

    cfg = deepcopy(config) if isinstance(config, dict) else {}
    brush = deepcopy(cfg.get("brush")) if isinstance(cfg.get("brush"), dict) else {}
    raw_rows = brush.get("rows") if isinstance(brush.get("rows"), list) else cfg.get("rows")
    brush_rows = deepcopy(raw_rows) if isinstance(raw_rows, list) else []
    auto_start = bool(cfg.get("autoStart", True))
    if brush_rows and not any(
        isinstance(row, dict) and bool(row.get("enabled")) for row in brush_rows
    ):
        auto_start = False

    formation_by_general = (
        _formation_index(saved_formations) if resolve_brush_formations else {}
    )
    if auto_start and not formation_by_general:
        raise ValueError(
            "请先到“军事-配兵”页保存配兵规则；"
            "刷黄页只保存刷黄规则，不会创建/修改配兵规则"
        )
    active_rows = [
        (source_index, deepcopy(row))
        for source_index, row in enumerate(brush_rows)
        if isinstance(row, dict) and bool(row.get("enabled"))
    ]
    if auto_start and not active_rows:
        active_rows = [(0, deepcopy(brush))]
    known_ids = _known_general_ids(known_generals or [])
    known_names = _known_general_names(known_generals or [])
    brush_rules = []
    selected_formations = []
    selected_ids: set[str] = set()
    for fallback_row_index, row in active_rows:
        source_row_index = _int_setting(
            row.get("idx"), fallback_row_index, minimum=0
        )
        display_row_number = source_row_index + 1
        raw_ids = row.get("generalIds")
        if isinstance(raw_ids, list):
            general_ids = [
                str(value).strip()
                for value in raw_ids
                if str(value or "").strip()
            ]
        else:
            fallback = row.get("generalId") or brush.get("generalId") or cfg.get("generalId")
            general_ids = [str(fallback).strip()] if str(fallback or "").strip() else []
        general_ids = list(dict.fromkeys(general_ids))
        if not general_ids:
            raise ValueError(
                f"第 {display_row_number} 条已勾选刷黄规则没有选择出征将领"
            )
        if len(general_ids) > _BRUSH_MAX_GENERALS:
            raise ValueError(
                f"第 {display_row_number} 条刷黄规则最多选择"
                f"{_BRUSH_MAX_GENERALS}名出征将领"
            )
        row_formations = []
        for general_id in general_ids:
            if known_ids and general_id not in known_ids:
                raise ValueError(
                    f"第 {display_row_number} 条刷黄规则的将领不在当前账号将领列表中："
                    f"{general_id}；原配置已保留，请先刷新角色状态/重新同步将领后再执行"
                )
            formation = formation_by_general.get(general_id)
            if not formation:
                raise ValueError(
                    f"刷黄将领 {general_id} 没有保存过配兵规则；"
                    "请先到“军事-配兵”页为该将领保存兵种和数量"
                )
            row_formations.append(deepcopy(formation))
            if general_id not in selected_ids:
                selected_ids.add(general_id)
                selected_formations.append(deepcopy(formation))
        composition = deepcopy(brush.get("compositionFilter")) \
            if isinstance(brush.get("compositionFilter"), dict) else {}
        if isinstance(row.get("compositionFilter"), dict):
            composition.update(deepcopy(row["compositionFilter"]))
        by_code = parse_composition_code(
            row.get("compositionCode")
            or brush.get("compositionCode")
            or cfg.get("compositionCode")
            or ""
        )
        if by_code:
            composition.update(by_code)
        for key, default in (
            ("maxFoot", 0),
            ("maxBow", 5),
            ("maxCavalry", 0),
            ("maxChariot", 0),
        ):
            composition[key] = _int_setting(composition.get(key), default)
        composition["requireFoot"] = bool(composition.get("requireFoot", False))
        drops = normalize_drop_keywords(
            row.get("drop") or brush.get("drop") or cfg.get("drop"),
            row.get("drops") or brush.get("drops") or cfg.get("drops"),
        ) or list(_DEFAULT_BRUSH_DROPS)
        levels = normalize_brush_levels(
            row.get("levels"),
            row.get("level", brush.get("level", 1)),
        ) or [1]
        if any(level in _BRUSH_HIGH_TROOP_LEVELS for level in levels):
            troop_shortages = []
            for formation in row_formations:
                general_id = str(formation.get("generalId") or "").strip()
                soldier_count = _int_setting(
                    formation.get("soldierCount"), 0, minimum=0
                )
                if soldier_count >= _BRUSH_HIGH_LEVEL_MIN_TROOPS:
                    continue
                snapshots = (
                    formation.get("generalNameSnapshots")
                    if isinstance(formation.get("generalNameSnapshots"), dict)
                    else {}
                )
                general_name = str(
                    known_names.get(general_id)
                    or snapshots.get(general_id)
                    or general_id
                    or "将领"
                ).strip()
                troop_shortages.append(f"{general_name}={soldier_count}")
            if troop_shortages:
                raise ValueError(
                    f"刷黄编队{display_row_number}未满足每个将领配兵达到"
                    f"{_BRUSH_HIGH_LEVEL_MIN_TROOPS}："
                    + "、".join(troop_shortages)
                )
        formation_source_row_index = _int_setting(
            row_formations[0].get("sourceRowIndex"),
            source_row_index,
            minimum=0,
        )
        brush_rules.append(
            {
                "enabled": True,
                "sourceRowIndex": source_row_index,
                "formationSourceRowIndex": formation_source_row_index,
                # 用户看到的编队号属于“刷黄规则”，必须按
                # 刷黄页面的行号连续编号。配兵表来源行号只用于
                # 内部查找配兵数据，不能替代刷黄编队号。
                "formationNumber": source_row_index + 1,
                "generalIds": general_ids,
                "generalId": general_ids[0],
                "levels": levels,
                "level": levels[0],
                "drops": drops,
                "drop": drops[0],
                "compositionCode": (
                    f"{composition['maxFoot']}{composition['maxBow']}"
                    f"{composition['maxCavalry']}{composition['maxChariot']}"
                ),
                "compositionFilter": composition,
                "formations": row_formations,
            }
        )

    general_id = str(brush_rules[0].get("generalId") or "") if brush_rules else ""
    composition = deepcopy(
        (brush_rules[0] if brush_rules else {}).get("compositionFilter") or {}
    )
    if not composition:
        composition = deepcopy(brush.get("compositionFilter")) \
            if isinstance(brush.get("compositionFilter"), dict) else {}
        by_code = parse_composition_code(
            brush.get("compositionCode") or cfg.get("compositionCode") or ""
        )
        if by_code:
            composition.update(by_code)
        for key, default in (
            ("maxFoot", 0),
            ("maxBow", 5),
            ("maxCavalry", 0),
            ("maxChariot", 0),
        ):
            composition[key] = _int_setting(composition.get(key), default)
        composition["requireFoot"] = bool(composition.get("requireFoot", False))

    daily_limit = _int_setting(
        cfg.get("dailyLimit") or brush.get("dailyLimit") or 500,
        500,
        1,
        500,
    )
    quality = str(
        cfg.get("maxEquipmentQuality")
        or brush.get("maxEquipmentQuality")
        or "良好"
    )
    if quality not in _EQUIPMENT_QUALITY_NAMES:
        quality = "良好"
    # The page selects qualities as a set; ``maxEquipmentQuality`` is kept as
    # the highest selected one so older readers keep the same ceiling.  A
    # record without the set gets the ceiling expanded to "that and below",
    # which is what the ceiling has always meant.
    raw_qualities = cfg.get(
        "discardEquipmentQualities",
        brush.get("discardEquipmentQualities"),
    )
    if isinstance(raw_qualities, (list, tuple, set)):
        wanted = {str(name or "").strip() for name in raw_qualities}
        discard_qualities = [
            name for name in _EQUIPMENT_QUALITY_NAMES if name in wanted
        ]
        if discard_qualities:
            quality = discard_qualities[-1]
    else:
        discard_qualities = list(
            _EQUIPMENT_QUALITY_NAMES[: _EQUIPMENT_QUALITY_NAMES.index(quality) + 1]
        )
    raw_open_names = cfg.get("autoOpenItemNames", brush.get("autoOpenItemNames", []))
    if isinstance(raw_open_names, list):
        open_names = [str(name or "").strip() for name in raw_open_names]
    else:
        open_names = [
            name.strip()
            for name in re.split(r"[,，;；|]+", str(raw_open_names or ""))
        ]
    open_names = list(dict.fromkeys(
        name for name in open_names if name in AUTO_OPEN_ITEM_NAMES
    ))
    copper_floor = _int_setting(
        cfg["copperFloorWan"] if "copperFloorWan" in cfg else brush.get("copperFloorWan", 1),
        1,
    )
    if copper_floor not in (1, 10, 20, 50):
        copper_floor = 1
    reconnect_delay = _int_setting(
        cfg.get("reconnectDelayMinutes", brush.get(
            "reconnectDelayMinutes", _DEFAULT_RECONNECT_DELAY_MINUTES
        )),
        _DEFAULT_RECONNECT_DELAY_MINUTES,
        1,
        24 * 60,
    )
    top_levels = normalize_brush_levels(brush.get("levels"), brush.get("level"))
    if not top_levels and brush_rules:
        top_levels = list(brush_rules[0].get("levels") or [])
    if not top_levels:
        top_levels = [1]
    top_drops = normalize_drop_keywords(
        brush.get("drop") or cfg.get("drop"),
        brush.get("drops") or cfg.get("drops"),
    ) or list(_DEFAULT_BRUSH_DROPS)

    raw_chain = deepcopy(cfg.get("chainInventory")) \
        if isinstance(cfg.get("chainInventory"), dict) else {}
    chain_keep_count = _int_setting(raw_chain.get("keepCount", 3), 3, 0, 9999)
    raw_alarm = deepcopy(cfg.get("alarm")) if isinstance(cfg.get("alarm"), dict) else {}
    incoming_mode = str(raw_alarm.get("incomingMode") or "声音+日志")
    if incoming_mode not in {"声音+日志", "仅日志", "关闭"}:
        incoming_mode = "声音+日志"
    military_mode = str(raw_alarm.get("militaryMode") or "出征/返回")
    if military_mode not in {"出征/返回", "仅来袭", "全部"}:
        military_mode = "出征/返回"
    domestic = deepcopy(cfg.get("domestic")) if isinstance(cfg.get("domestic"), dict) else {}
    technology_ids = [
        int(value)
        for value in domestic.get("technologyIds", [domestic.get("technologyId", 5)])
        if str(value).lstrip("-").isdigit() and int(value) in TECHNOLOGY_NAMES
    ]
    daily = deepcopy(cfg.get("dailyTasks")) if isinstance(cfg.get("dailyTasks"), dict) else {}
    return {
        "sessionId": str(session_id or cfg.get("sessionId") or ""),
        "autoStart": auto_start,
        "reconnectDelayMinutes": reconnect_delay,
        "startHour": _int_setting(cfg.get("startHour") or brush.get("startHour") or 0, 0, 0, 23),
        "dailyLimit": daily_limit,
        "cycleDelaySec": _int_setting(cfg.get("cycleDelaySec") or brush.get("cycleDelaySec") or 10, 10, 1, 3600),
        "returnWaitSec": _int_setting(cfg.get("returnWaitSec") or brush.get("returnWaitSec") or 0, 0, 0, 3600),
        "maxReturnWaitSec": _int_setting(cfg.get("maxReturnWaitSec") or brush.get("maxReturnWaitSec") or 300, 300, 30, 7200),
        "maxDispatchFailures": _int_setting(cfg.get("maxDispatchFailures") or brush.get("maxDispatchFailures") or 1, 1, 1, 10),
        "healWounded": bool(cfg.get("healWounded", True)),
        "healAllIfCountUnknown": bool(cfg.get("healAllIfCountUnknown", True)),
        "replenishTroops": bool(cfg.get("replenishTroops", False)),
        "autoEnergy": bool(cfg.get("autoEnergy", brush.get("autoEnergy", True))),
        "energyThreshold": _int_setting(cfg.get("energyThreshold") or brush.get("energyThreshold") or 20, 20, 20, 100),
        "foodToCopper": bool(cfg.get("foodToCopper", brush.get("foodToCopper", True))),
        "copperFloorWan": copper_floor,
        "cleanMail": bool(cfg.get("cleanMail", brush.get("cleanMail", False))),
        "cleanInventory": bool(cfg.get("cleanInventory", brush.get("cleanInventory", False))),
        "discardItemNames": str(cfg.get("discardItemNames") or brush.get("discardItemNames") or "").strip(),
        "keepItemCount": 0,
        "discardEquipment": bool(cfg.get("discardEquipment", brush.get("discardEquipment", False))),
        "maxEquipmentQuality": quality,
        "discardEquipmentQualities": discard_qualities,
        "maxEquipmentLevel": _int_setting(cfg.get("maxEquipmentLevel") or brush.get("maxEquipmentLevel") or 20, 20, 1, 100),
        "autoOpenItemNames": open_names,
        "autoOpenEnabled": bool(cfg.get("autoOpenEnabled", brush.get("autoOpenEnabled", False))),
        "chainInventory": {
            "enabled": bool(raw_chain.get("enabled", False)),
            "keepItemName": str(raw_chain.get("keepItemName", "青铜钥匙")).strip()[:80],
            "keepCount": chain_keep_count,
            "autoOpenEnabled": bool(raw_chain.get("autoOpenEnabled", False)),
            "autoOpenItemNames": str(raw_chain.get("autoOpenItemNames", "50两银票")).strip()[:300],
        },
        "alarm": {
            "incomingEnabled": bool(raw_alarm.get("incomingEnabled", True)) and incoming_mode != "关闭",
            "incomingMode": incoming_mode,
            "incomingKeywords": deepcopy(
                raw_alarm.get("incomingKeywords")
                or raw_alarm.get("keywords")
                or raw_alarm.get("alarm_keywords")
                or "掠夺,夺取,攻城,敌军,来袭"
            ),
            "militaryEnabled": bool(raw_alarm.get("militaryEnabled", True)),
            "militaryMode": military_mode,
            "errorEnabled": bool(raw_alarm.get("errorEnabled", True)),
            "vibrateOnAlarm": bool(
                raw_alarm.get(
                    "vibrateOnAlarm",
                    raw_alarm.get("alarm_vibrate", True),
                )
            ),
        },
        "domestic": {
            "enabled": bool(domestic.get("enabled", False)),
            "emptyBuildingType": _int_setting(domestic.get("emptyBuildingType", 1), 1),
            "upgradeBuildings": bool(domestic.get("upgradeBuildings", True)),
            "upgradeLowestFirst": bool(domestic.get("upgradeLowestFirst", True)),
            "buildingPriority": list(domestic.get("buildingPriority") or []),
            "upgradeTechnology": bool(domestic.get("upgradeTechnology", False)),
            "technologyId": _int_setting(domestic.get("technologyId", 5), 5),
            "technologyIds": technology_ids,
            "technologyTargetLevel": _int_setting(domestic.get("technologyTargetLevel", 2), 2, 1, 10),
            "acceleration": "none",
        },
        "dailyTasks": {key: bool(daily.get(key, False)) for key in _DAILY_TASK_NAMES},
        "generalVisitGeneralIds": normalize_general_visit_ids(cfg.get("generalVisitGeneralIds", [])),
        "formations": selected_formations,
        "brush": {
            "startX": _int_setting(brush.get("startX", 0), 0),
            "startY": _int_setting(brush.get("startY", 0), 0),
            "scanLimit": _int_setting(brush.get("scanLimit", 80), 80, 1, 384),
            "targetKind": str(brush.get("targetKind") or "山贼"),
            "levels": top_levels,
            "level": top_levels[0],
            "drops": top_drops,
            "drop": top_drops[0],
            "generalId": general_id,
            "rows": brush_rows,
            "rules": brush_rules,
            "compositionCode": (
                f"{composition['maxFoot']}{composition['maxBow']}"
                f"{composition['maxCavalry']}{composition['maxChariot']}"
            ),
            "compositionFilter": composition,
        },
    }


def _settings_feature_configs(
    scope: str,
    config: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    configs: Dict[str, Dict[str, Any]] = {}
    scopes = set(_SETTINGS_SCOPE_FIELDS) if scope == "legacy.full" else {scope}
    if "common.frequent" in scopes:
        configs["general"] = {
            "autoHeal": bool(config.get("healWounded", True)),
            "autoEnergy": bool(config.get("autoEnergy", True)),
            "minEnergy": _int_setting(config.get("energyThreshold"), 20, 20, 100),
            "foodToCopper": bool(config.get("foodToCopper", True)),
            "copperFloorWan": _int_setting(config.get("copperFloorWan"), 1),
            "dailyLimit": _int_setting(config.get("dailyLimit"), 500, 1, 500),
        }
        configs["internal_affairs"] = deepcopy(config.get("domestic") or {})
    if "common.daily" in scopes:
        configs["daily_basic"] = {
            "dailyTasks": deepcopy(config.get("dailyTasks") or {}),
            "generalVisitGeneralIds": list(config.get("generalVisitGeneralIds") or []),
        }
    if "common.items" in scopes:
        configs["inventory"] = {
            key: deepcopy(config.get(key))
            for key in (
                "cleanInventory",
                "discardItemNames",
                "discardEquipment",
                "maxEquipmentQuality",
                "discardEquipmentQualities",
                "maxEquipmentLevel",
                "autoOpenItemNames",
                "autoOpenEnabled",
            )
        }
    if "common.chain" in scopes:
        configs["chain_inventory"] = deepcopy(config.get("chainInventory") or {})
    if "common.alarm" in scopes:
        alarm = deepcopy(config.get("alarm") or {})
        alarm["alarm_withdraw_enabled"] = any(
            bool(alarm.get(key))
            for key in ("incomingEnabled", "militaryEnabled", "errorEnabled")
        )
        configs["alarm_withdraw"] = alarm
    if "brush" in scopes:
        brush = deepcopy(config.get("brush") or {})
        rules = brush.get("rules") if isinstance(brush.get("rules"), list) else []
        selected_ids = list(dict.fromkeys(
            str(general_id)
            for rule in rules if isinstance(rule, dict)
            for general_id in rule.get("generalIds") or []
            if str(general_id or "").strip()
        ))
        active = rules[0] if rules else {}
        composition = deepcopy(active.get("compositionFilter") or brush.get("compositionFilter") or {})
        configs["shua_huang"] = {
            "enabled": bool(config.get("autoStart", False)) and bool(selected_ids),
            "startHour": _int_setting(config.get("startHour"), 0, 0, 23),
            "dailyLimit": _int_setting(config.get("dailyLimit"), 500, 1, 500),
            "replenishTroops": bool(config.get("replenishTroops", False)),
            "foodToCopper": bool(config.get("foodToCopper", True)),
            "copperFloorWan": _int_setting(config.get("copperFloorWan"), 1),
            "cleanMail": bool(config.get("cleanMail", False)),
            "startX": _int_setting(brush.get("startX"), 0, 0, 186),
            "startY": _int_setting(brush.get("startY"), 0, 0, 66),
            "scanLimit": _int_setting(brush.get("scanLimit"), 80, 1, 384),
            "targetKind": str(brush.get("targetKind") or "山贼"),
            "selectedFormationIds": selected_ids,
            "selectedFormationId": selected_ids[0] if selected_ids else "",
            "rows": deepcopy(brush.get("rows") or []),
            "levels": deepcopy(active.get("levels") or brush.get("levels") or []),
            "drops": deepcopy(active.get("drops") or brush.get("drops") or []),
            "compositionCode": str(active.get("compositionCode") or brush.get("compositionCode") or ""),
            "compositionFilter": composition,
            "maxFoot": _int_setting(composition.get("maxFoot"), 0),
            "maxBow": _int_setting(composition.get("maxBow"), 5),
            "maxCavalry": _int_setting(composition.get("maxCavalry"), 0),
            "maxChariot": _int_setting(composition.get("maxChariot"), 0),
            "requireFoot": bool(composition.get("requireFoot", False)),
        }
    return configs


def _scoped_settings_write_plan(
    route: str,
    request: Dict[str, Any],
) -> Dict[str, Any]:
    scope = str(request.get("scope") or "").strip() or "legacy.full"
    old_config = request.get("oldConfig")
    old_config = deepcopy(old_config) if isinstance(old_config, dict) else {}
    session = request.get("session")
    session = deepcopy(session) if isinstance(session, dict) else {}
    session_id = request.get("sessionId") or session.get("sessionId")
    known_generals = request.get("knownGenerals")
    saved_formations = request.get("savedFormations")

    if scope == "legacy.full":
        source = request.get("config")
        source = source if isinstance(source, dict) else request
        config = normalize_automation_config(
            source,
            session_id=session_id,
            known_generals=known_generals,
            saved_formations=saved_formations,
        )
    else:
        patch = request.get("patch")
        if not isinstance(patch, dict):
            raise ValueError("设置保存缺少 patch")
        merged = _merge_settings_scope_patch(old_config, scope, patch)
        if scope == "brush":
            config = normalize_automation_config(
                merged,
                session_id=session_id,
                known_generals=known_generals,
                saved_formations=saved_formations,
            )
        else:
            safe_source = deepcopy(merged)
            safe_source["autoStart"] = False
            safe_brush = deepcopy(safe_source.get("brush")) \
                if isinstance(safe_source.get("brush"), dict) else {}
            for key in ("rows", "rules", "generalId"):
                safe_brush.pop(key, None)
            safe_source["brush"] = safe_brush
            safe_source.pop("rows", None)
            safe_source.pop("generalId", None)
            config = normalize_automation_config(
                safe_source,
                session_id=session_id,
                known_generals=known_generals,
                saved_formations=[],
                resolve_brush_formations=False,
            )
            scoped_fields = _SETTINGS_SCOPE_FIELDS[scope]
            for key, value in old_config.items():
                if key not in scoped_fields:
                    config[key] = deepcopy(value)

    warnings = []
    if scope in {"common.daily", "legacy.full"}:
        visit_ids = normalize_general_visit_ids(config.get("generalVisitGeneralIds"))
        config["generalVisitGeneralIds"] = visit_ids
        daily = deepcopy(config.get("dailyTasks")) if isinstance(config.get("dailyTasks"), dict) else {}
        if daily.get("generalVisit") and not visit_ids and not role_is_national_citizen(session):
            daily["generalVisit"] = False
            warnings.append("名将拜访未选择将领，本项未开启；其他日常设置已正常保存")
        config["dailyTasks"] = daily
    role_level = _int_setting(
        request.get("roleLevel")
        or (session.get("roleState") or {}).get("level")
        or (session.get("role") or {}).get("level"),
        0,
    )
    if scope in {"brush", "legacy.full"} and bool(config.get("autoStart", True)):
        if role_level < _BRUSH_MIN_ROLE_LEVEL:
            raise ValueError("请30级之后再开启刷黄！")

    configs = _settings_feature_configs(scope, config)
    if not configs:
        raise ValueError(f"共享设置核心没有生成写入内容：{scope}")
    brush_enabled = bool(config.get("autoStart", False)) and bool(
        (config.get("brush") or {}).get("rules")
    )
    alarm = config.get("alarm") if isinstance(config.get("alarm"), dict) else {}
    alarm_enabled = any(bool(alarm.get(key)) for key in (
        "incomingEnabled", "militaryEnabled", "errorEnabled"
    ))
    disabled = (
        not brush_enabled if scope == "brush"
        else True if scope == "common.chain"
        else not alarm_enabled if scope == "common.alarm"
        else False
    )
    follow_ups = []
    if scope in {"brush", "legacy.full"} and brush_enabled:
        follow_ups.append({"kind": "start-brush", "required": True})
    if scope in {"common.daily", "legacy.full"}:
        old_daily = old_config.get("dailyTasks") if isinstance(old_config.get("dailyTasks"), dict) else {}
        newly_enabled = [
            key for key in _DAILY_TASK_NAMES
            if bool((config.get("dailyTasks") or {}).get(key)) and not bool(old_daily.get(key))
        ]
        if newly_enabled:
            follow_ups.append({"kind": "run-new-daily", "required": True, "keys": newly_enabled})
    if scope in {"common.items", "legacy.full"} and config.get("autoOpenEnabled"):
        follow_ups.append({"kind": "auto-open-inventory", "required": True})
    if scope in {"common.frequent", "legacy.full"}:
        domestic = config.get("domestic") if isinstance(config.get("domestic"), dict) else {}
        if domestic.get("enabled"):
            follow_ups.append({"kind": "auto-domestic", "required": True})
        if domestic.get("upgradeTechnology"):
            follow_ups.append({"kind": "auto-technology", "required": True})
    return {
        "route": route,
        "configs": configs,
        "disabled": disabled,
        "activationAllowed": brush_enabled if scope == "brush" else False,
        "networkRequired": False,
        "followUpOperations": follow_ups,
        "response": {
            "scope": scope,
            "config": config,
            "settingsWarnings": warnings,
        },
    }
