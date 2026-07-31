"""Host-neutral settings normalization and local write plans.

The shared core owns field semantics. Platform hosts persist the returned
feature-config objects atomically and may attach platform-only paths or runtime
facts after persistence; planning itself never performs game-network I/O.
"""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Dict

from .features.dungeon import normalize_dungeon_mode
from .features.formation import SOLDIER_TYPE_CODES
from .features.ministries import (
    ministry_planting_allowed,
    normalize_ministry_settings,
    unconfirmed_ministry_actions,
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
    supported = ministry_planting_allowed(settings)
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
    if not requested:
        reason = "六部任务已关闭"
    elif supported:
        reason = "六部设置已保存，由账号任务队列执行金银花种植"
    elif settings.get("cropEnabled"):
        reason = f"{settings.get('crop')}协议尚未确认；配置已保存但不会发送"
    else:
        reason = "种菜收菜未开启；偷菜、礼部和俸禄刷新协议尚未完整确认，当前不发送"
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
