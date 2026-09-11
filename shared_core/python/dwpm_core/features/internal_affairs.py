"""Internal-affairs protocol shapes and deterministic queue rules."""

from __future__ import annotations

import struct
from typing import Any

from ..contracts import load_behavior_contract
from ..protocol.wire import read_utf


INTERNAL_AFFAIRS_CONTRACT = load_behavior_contract()["internalAffairs"]

BUILDING_TYPE_NAMES = {
    -1: "空地",
    0: "大厅",
    1: "房屋",
    2: "农场",
    3: "书院",
    4: "步兵营",
    5: "弓兵营",
    6: "战车营",
    8: "骑兵营",
}
BUILDING_NAME_TYPES = {
    name: code for code, name in BUILDING_TYPE_NAMES.items() if code >= 0
}
TECHNOLOGY_NAMES = {
    0: "工程设计",
    1: "征召技巧",
    2: "种植技术",
    3: "行军技巧",
    4: "市场贸易",
    5: "建筑学",
    6: "铸铁技术",
    7: "甲胄制造",
    8: "药草研究",
    9: "阵法技巧",
    10: "抛射技巧",
    11: "驾驭技巧",
    12: "战车设计",
    13: "统帅能力",
    14: "信仰",
    15: "仓储",
    16: "安置",
    17: "格斗",
    18: "精准",
    19: "驯马",
    20: "精工",
    21: "悬赏",
}
BARRACK_BUILDING_TYPES = frozenset({4, 5, 6, 8})

# Recovered from the same game-rule tables previously embedded by the Android
# implementation.  They live here now so both hosts use one resource planner.
_BUILDING_COPPER_COSTS = {
    0: (0, 180, 540, 1080, 2160, 4320, 6480, 9720, 12636, 16425, 33728, 56192, 84753, 120425, 164300),
    1: (26, 78, 234, 468, 936, 1872, 2808, 4212, 5475, 7118, 11111, 16295, 22886, 31118, 41243),
    2: (20, 60, 180, 360, 720, 1440, 2160, 3240, 4212, 5475, 9468, 14652, 21243, 29475, 39600),
    3: (44, 132, 396, 792, 1584, 3168, 4752, 7128, 9266, 12045, 20829, 32234, 46734, 64845, 87120),
    4: (30, 90, 270, 540, 1080, 2160, 3240, 4860, 6318, 8212),
    5: (30, 90, 270, 540, 1080, 2160, 3240, 4860, 6318, 8212),
    6: (36, 108, 326, 653, 1306, 2613, 3920, 5880, 7643, 9936),
    8: (33, 99, 297, 594, 1188, 2376, 3564, 5346, 6949, 9033),
}
_BUILDING_FOOD_COSTS = {
    0: (0, 450, 1350, 2700, 5400, 10800, 16200, 24300, 31590, 41067, 77004, 123660, 182979, 257067, 348192),
    1: (65, 195, 585, 1170, 2340, 4680, 7020, 10530, 13689, 17796, 27113, 39209, 54588, 73796, 97421),
    2: (50, 150, 450, 900, 1800, 3600, 5400, 8100, 10530, 13689, 20344, 28984, 39969, 53689, 70564),
    3: (110, 330, 990, 1980, 3960, 7920, 11880, 17820, 23166, 30115, 44756, 63764, 87931, 118115, 155240),
    4: (75, 225, 675, 1350, 2700, 5400, 8100, 12150, 15795, 20533),
    5: (75, 225, 675, 1350, 2700, 5400, 8100, 12150, 15795, 20533),
    6: (90, 271, 742, 1633, 3267, 6534, 9801, 14701, 19111, 24838),
    8: (82, 247, 742, 1485, 2970, 5940, 8910, 13365, 17374, 22586),
}
_TECHNOLOGY_COPPER_BASE = (
    20000, 20000, 2400, 22000, 2400, 2400, 28000, 25000,
    25000, 20000, 20000, 20000, 20000, 30000, 4000,
)
_PLANTING_TECHNOLOGY_COPPER = (
    2400, 4320, 7776, 13997, 25194,
    45350, 81629, 146933, 264479, 476062,
)
_FOOD_TECHNOLOGY_COSTS = (1000, 3000, 8000, 20000, 50000)
_STORAGE_TECHNOLOGY_FOOD = (300, 900, 2400, 6000, 15000)
_EXTRA_TECHNOLOGY_COSTS = (800, 1600, 3200, 6400, 12800)


def building_resource_cost(
    building_type: int,
    target_level: int,
) -> dict[str, int] | None:
    index = int(target_level) - 1
    copper = _BUILDING_COPPER_COSTS.get(int(building_type))
    food = _BUILDING_FOOD_COSTS.get(int(building_type))
    if index < 0 or copper is None or food is None:
        return None
    if index >= len(copper) or index >= len(food):
        return None
    return {
        "copper": int(copper[index]),
        "food": int(food[index]),
        "extra": 0,
    }


def technology_resource_cost(
    technology_id: int,
    target_level: int,
) -> dict[str, int] | None:
    tech_id = int(technology_id)
    level = int(target_level)
    index = level - 1
    if tech_id not in TECHNOLOGY_NAMES or index < 0:
        return None
    if tech_id == 2:
        if index >= len(_PLANTING_TECHNOLOGY_COPPER):
            return None
        return {
            "copper": int(_PLANTING_TECHNOLOGY_COPPER[index]),
            "food": 0,
            "extra": 0,
        }
    if tech_id == 15:
        if index >= len(_STORAGE_TECHNOLOGY_FOOD):
            return None
        return {
            "copper": 0,
            "food": int(_STORAGE_TECHNOLOGY_FOOD[index]),
            "extra": 0,
        }
    if 16 <= tech_id <= 20:
        if tech_id == 16 and 5 <= index < 10:
            return {
                "copper": 0,
                "food": 0,
                "extra": int(_EXTRA_TECHNOLOGY_COSTS[index - 5]),
            }
        if index >= len(_FOOD_TECHNOLOGY_COSTS):
            return None
        return {
            "copper": 0,
            "food": int(_FOOD_TECHNOLOGY_COSTS[index]),
            "extra": 0,
        }
    if tech_id == 21:
        if index >= len(_EXTRA_TECHNOLOGY_COSTS):
            return None
        return {
            "copper": 0,
            "food": 0,
            "extra": int(_EXTRA_TECHNOLOGY_COSTS[index]),
        }
    if tech_id >= len(_TECHNOLOGY_COPPER_BASE):
        return None
    if tech_id == 0 and level > 10:
        extra_index = level - 11
        if extra_index >= len(_EXTRA_TECHNOLOGY_COSTS):
            return None
        return {
            "copper": 0,
            "food": 0,
            "extra": int(_EXTRA_TECHNOLOGY_COSTS[extra_index]),
        }
    if level > 10:
        return None
    copper = int(_TECHNOLOGY_COPPER_BASE[tech_id]) * (1 << index)
    return {"copper": copper, "food": 0, "extra": 0}


def build_fief_query_payload(fief_id: int, mode: int = 0) -> bytes:
    return struct.pack(">Bq", int(mode), int(fief_id))


def build_building_action_payload(
    fief_id: int,
    slot: int,
    building_type: int,
    action: int = 0,
) -> bytes:
    if not (
        0 <= int(slot) <= 0xFFFF
        and 0 <= int(building_type) <= 0xFFFF
    ):
        raise RuntimeError("建筑槽位或类型超出范围")
    return struct.pack(">BqHH", int(action), int(fief_id), int(slot), int(building_type))


def build_technology_upgrade_payload(
    fief_id: int,
    academy_slot: int,
    technology_id: int,
    target_level: int,
    mode: int = 0,
    use_gold: int = 0,
) -> bytes:
    return struct.pack(
        ">qBHBBB",
        int(fief_id),
        int(academy_slot),
        int(technology_id),
        int(target_level),
        int(mode),
        int(use_gold),
    )


def parse_building_list(
    payload: bytes,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    if offset < 0 or offset >= len(payload):
        raise RuntimeError("建筑列表偏移无效")
    count = payload[offset]
    if count > 32:
        raise RuntimeError(f"建筑数量异常：{count}")
    position = offset + 1
    buildings: list[dict[str, Any]] = []
    for index in range(count):
        if position + 28 > len(payload):
            raise RuntimeError(f"第 {index + 1} 条建筑记录不完整")
        slot = payload[position]
        instance_id = struct.unpack(">q", payload[position + 1:position + 9])[0]
        building_type = struct.unpack(">b", payload[position + 9:position + 10])[0]
        level = payload[position + 10]
        timer_ms = struct.unpack(">i", payload[position + 11:position + 15])[0]
        progress = struct.unpack(">i", payload[position + 15:position + 19])[0]
        state_sign = struct.unpack(">q", payload[position + 19:position + 27])[0]
        nested_action = payload[position + 27]
        position += 28
        nested: dict[str, Any] = {"action": nested_action}
        if nested_action == 0:
            if position + 8 > len(payload):
                raise RuntimeError("建筑嵌套清理块不完整")
            nested["ownerId"] = struct.unpack(">q", payload[position:position + 8])[0]
            position += 8
        elif nested_action == 1:
            if position + 9 > len(payload):
                raise RuntimeError("建筑嵌套任务头不完整")
            nested["ownerId"] = struct.unpack(">q", payload[position:position + 8])[0]
            task_count = payload[position + 8]
            position += 9
            nested["taskCount"] = task_count
            nested["tasks"] = []
            for _ in range(task_count):
                if position + 32 > len(payload):
                    raise RuntimeError("建筑嵌套任务记录不完整")
                nested["tasks"].append(
                    {
                        "taskId": struct.unpack(">q", payload[position:position + 8])[0],
                        "state": payload[position + 8],
                        "targetType": struct.unpack(">H", payload[position + 9:position + 11])[0],
                        "current": struct.unpack(">i", payload[position + 11:position + 15])[0],
                        "target": struct.unpack(">i", payload[position + 15:position + 19])[0],
                        "remainingMs": struct.unpack(">q", payload[position + 19:position + 27])[0],
                        "flag": payload[position + 27],
                        "tickMs": struct.unpack(">i", payload[position + 28:position + 32])[0],
                    }
                )
                position += 32
        else:
            raise RuntimeError(f"未知建筑嵌套动作：{nested_action}")
        buildings.append(
            {
                "slot": slot,
                "instanceId": instance_id,
                "type": building_type,
                "name": BUILDING_TYPE_NAMES.get(
                    building_type,
                    f"建筑{building_type}",
                ),
                "level": level,
                "timerMs": timer_ms,
                "busy": timer_ms > 0,
                "progress": progress,
                "stateSign": state_sign,
                "nested": nested,
            }
        )
    return buildings, position


def parse_fief_base_block(payload: bytes, offset: int, end: int) -> dict[str, Any]:
    position = offset

    def take(size: int) -> bytes:
        nonlocal position
        if position + size > end:
            raise RuntimeError("封地基础状态不完整")
        value = payload[position:position + size]
        position += size
        return value

    flag1 = take(1)[0]
    flag2 = take(1)[0]
    name, position = read_utf(payload, position)
    if position > end:
        raise RuntimeError("封地名称越界")
    base = {
        "flag1": flag1,
        "flag2": flag2,
        "fiefName": name,
        "longValue": struct.unpack(">q", take(8))[0],
        "intValue1": struct.unpack(">i", take(4))[0],
        "intValue2": struct.unpack(">i", take(4))[0],
        "shortValue1": struct.unpack(">h", take(2))[0],
        "shortValue2": struct.unpack(">h", take(2))[0],
        "baseBuildQueueCapacity": take(1)[0],
        "shortValue3": struct.unpack(">h", take(2))[0],
        "shortValue4": struct.unpack(">h", take(2))[0],
        "flag3": take(1)[0],
    }

    def parse_buff_group() -> list[dict[str, int]]:
        rows = []
        for _ in range(take(1)[0]):
            rows.append(
                {
                    "value": take(1)[0],
                    "remainingMs": struct.unpack(">q", take(8))[0],
                    "type": take(1)[0],
                }
            )
        return rows

    base["copperBoosts"] = parse_buff_group()
    base["grainBoosts"] = parse_buff_group()
    queue_boosts = parse_buff_group()
    base["buildQueueBoosts"] = queue_boosts

    def consume_byte_int_rows() -> list[dict[str, int]]:
        return [
            {"type": take(1)[0], "value": struct.unpack(">i", take(4))[0]}
            for _ in range(take(1)[0])
        ]

    base["list1"] = consume_byte_int_rows()
    base["list2"] = consume_byte_int_rows()
    if position != end:
        raise RuntimeError(f"封地基础状态有未解析尾部：{end - position}B")
    active_capacities = [
        int(row["value"])
        for row in queue_boosts
        if int(row.get("remainingMs") or 0) > 0
        and int(row.get("value") or 0) > 0
    ]
    base["buildQueueCapacity"] = (
        active_capacities[0]
        if active_capacities
        else max(1, int(base["baseBuildQueueCapacity"] or 2))
    )
    base["buildQueueRemainingMs"] = max(
        (int(row.get("remainingMs") or 0) for row in queue_boosts),
        default=0,
    )
    return base


def parse_8200_building_result(payload: bytes) -> dict[str, Any]:
    if len(payload) < 11:
        raise RuntimeError("0x8200 建筑响应过短")
    status = struct.unpack(">b", payload[:1])[0]
    substatus = struct.unpack(">b", payload[1:2])[0]
    fief_id = struct.unpack(">q", payload[2:10])[0]
    buildings, end = parse_building_list(payload, 10)
    if end != len(payload):
        raise RuntimeError(f"0x8200 建筑响应有未解析尾部：{len(payload) - end}B")
    return {
        "success": status == 0 and substatus == 0,
        "status": status,
        "substatus": substatus,
        "fiefId": fief_id,
        "buildings": buildings,
    }


def parse_8246_fief_result(
    payload: bytes,
    expected_fief_id: int | None = None,
) -> dict[str, Any]:
    if len(payload) < 12:
        raise RuntimeError("0x8246 封地响应过短")
    status = struct.unpack(">b", payload[:1])[0]
    fief_id = struct.unpack(">q", payload[1:9])[0]
    if expected_fief_id is not None and fief_id != int(expected_fief_id):
        raise RuntimeError(
            f"0x8246 封地不匹配：期望{expected_fief_id}，实际{fief_id}"
        )
    candidates = []
    for offset in range(9, len(payload)):
        if payload[offset] > 16:
            continue
        try:
            buildings, end = parse_building_list(payload, offset)
        except Exception:
            continue
        slots = [int(item["slot"]) for item in buildings]
        if (
            end == len(payload)
            and len(slots) == len(set(slots))
            and all(slot <= 31 for slot in slots)
            and all(
                int(item["type"]) in BUILDING_TYPE_NAMES
                for item in buildings
            )
        ):
            try:
                base = parse_fief_base_block(payload, 9, offset)
            except Exception:
                continue
            candidates.append((offset, buildings, base))
    if len(candidates) != 1:
        raise RuntimeError(f"0x8246 建筑列表定位不唯一：候选{len(candidates)}个")
    offset, buildings, base = candidates[0]
    return {
        "success": status == 0,
        "status": status,
        "fiefId": fief_id,
        "buildingOffset": offset,
        "buildings": buildings,
        **base,
    }


def parse_technology_states_from_8004(payload: bytes) -> list[dict[str, Any]]:
    """Locate the verified 22-entry technology table in a role-state payload."""
    candidates: list[list[dict[str, Any]]] = []
    count = 22
    record_size = 27
    for offset in range(0, max(0, len(payload) - count * record_size + 1)):
        if any(
            payload[offset + index * record_size] != index
            for index in range(count)
        ):
            continue
        rows = []
        plausible = True
        for index in range(count):
            position = offset + index * record_size
            level = payload[position + 1]
            state = payload[position + 2]
            fief_id = struct.unpack(">q", payload[position + 3:position + 11])[0]
            academy_id = struct.unpack(">q", payload[position + 11:position + 19])[0]
            deadline_ms = struct.unpack(">q", payload[position + 19:position + 27])[0]
            if level > 15 or state > 10:
                plausible = False
                break
            rows.append(
                {
                    "technologyId": index,
                    "name": TECHNOLOGY_NAMES.get(index, f"科技{index}"),
                    "level": level,
                    "state": state,
                    "researching": (
                        fief_id >= 0 and academy_id >= 0 and deadline_ms > 0
                    ),
                    "fiefId": None if fief_id < 0 else fief_id,
                    "academyInstanceId": None if academy_id < 0 else academy_id,
                    "deadlineMs": deadline_ms,
                    "offset": position,
                }
            )
        if plausible:
            candidates.append(rows)
    if len(candidates) != 1:
        raise RuntimeError(
            f"0x8004 科技状态表定位不唯一：候选{len(candidates)}个"
        )
    return candidates[0]


def building_action_was_applied(
    buildings: list[dict[str, Any]],
    slot: int,
    building_type: int,
    previous_level: int | None,
) -> bool:
    building = next(
        (
            item
            for item in buildings
            if int(item.get("slot", -1)) == int(slot)
        ),
        None,
    )
    if not building or int(building.get("type", -1)) != int(building_type):
        return False
    if previous_level is None:
        return True
    return (
        int(building.get("level", 0)) > int(previous_level)
        or bool(building.get("busy"))
    )


def build_country_donation_payload(
    *,
    copper: int = 0,
    food: int = 0,
    technology: int = 0,
) -> bytes:
    values = [int(copper), int(food), int(technology)]
    if sum(value > 0 for value in values) != 1:
        raise RuntimeError("每次国家捐献必须且只能指定一种资源")
    if any(value < 0 for value in values):
        raise RuntimeError("国家捐献数量不能为负数")
    return struct.pack(">qqq", *values)


def build_technology_donation_payload(amount: int) -> bytes:
    """0x140a payload: mode byte 0 + signed int amount."""
    value = int(amount)
    if value <= 0:
        raise RuntimeError("科技积分捐献数量必须大于0")
    return struct.pack(">Bi", 0, value)


def fief_is_base(state: dict[str, Any]) -> bool:
    return "基地" in str(state.get("fiefName") or "")


def building_level_limit(state: dict[str, Any], building_type: int) -> int:
    if int(building_type) in BARRACK_BUILDING_TYPES:
        return 10
    return 15 if fief_is_base(state) else 10


def fief_build_queue_state(state: dict[str, Any]) -> tuple[int, int]:
    capacity = max(1, int(state.get("buildQueueCapacity") or 2))
    busy = sum(bool(item.get("busy")) for item in state.get("buildings") or [])
    return busy, capacity


def summarize_role_queues(
    fief_states: list[dict[str, Any]],
    technology_states: list[dict[str, Any]],
    *,
    updated_at: int,
) -> dict[str, Any]:
    """Project one complete role-queue snapshot from authoritative game facts."""

    states = [dict(row) for row in fief_states if isinstance(row, dict)]
    technologies = [
        dict(row) for row in technology_states if isinstance(row, dict)
    ]
    building_current = 0
    building_capacity = 0
    research_capacity = 0
    for state in states:
        busy, capacity = fief_build_queue_state(state)
        building_current += busy
        building_capacity += capacity
        research_capacity += sum(
            1
            for building in state.get("buildings") or []
            if isinstance(building, dict)
            and int(building.get("type", -1)) == 3
        )
    research_current = sum(
        1 for technology in technologies if technology.get("researching")
    )
    return {
        "buildingQueue": {
            "current": building_current,
            "capacity": building_capacity,
        },
        "researchQueue": {
            "current": research_current,
            "capacity": research_capacity,
        },
        "fiefCount": len(states),
        "updatedAt": max(0, int(updated_at)),
        "source": "0x1310/0x8310+0x1246/0x8246+0x1016/0x8004",
    }


def fief_hall(state: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (
            building
            for building in state.get("buildings") or []
            if int(building.get("type", -1)) == 0
        ),
        None,
    )


def hall_must_upgrade_first(state: dict[str, Any]) -> bool:
    hall = fief_hall(state)
    if not hall or hall.get("busy"):
        return False
    hall_level = int(hall.get("level", 0))
    other_levels = [
        int(building.get("level", 0))
        for building in state.get("buildings") or []
        if int(building.get("type", -1)) > 0
    ]
    return (
        hall_level < building_level_limit(state, 0)
        and (not other_levels or max(other_levels) >= hall_level)
    )


def building_can_follow_hall(
    state: dict[str, Any],
    building: dict[str, Any],
) -> bool:
    hall = fief_hall(state)
    building_type = int(building.get("type", -1))
    level = int(building.get("level", 0))
    return bool(
        hall
        and building_type > 0
        and not building.get("busy")
        and level < int(hall.get("level", 0))
        and level < building_level_limit(state, building_type)
    )


def auto_domestic_interval_seconds(states: list[dict[str, Any]]) -> int:
    halls = [fief_hall(state) for state in states]
    all_halls_at_least_seven = bool(halls) and all(
        hall is not None and int(hall.get("level", 0)) >= 7
        for hall in halls
    )
    normal_interval = 3600 if all_halls_at_least_seven else 600
    remaining_ms = [
        int(building.get("timerMs") or 0)
        for state in states
        for building in state.get("buildings") or []
        if building.get("busy") and int(building.get("timerMs") or 0) > 0
    ]
    if not remaining_ms:
        return normal_interval
    next_completion_seconds = (min(remaining_ms) + 999) // 1000
    return max(5, min(normal_interval, next_completion_seconds + 2))


def auto_domestic_interval_text(interval_seconds: int) -> str:
    seconds = max(1, int(interval_seconds))
    if seconds % 3600 == 0:
        return f"{seconds // 3600}小时"
    if seconds % 60 == 0:
        return f"{seconds // 60}分钟"
    return f"{seconds}秒"


def should_continue_filling_build_queues(
    acted: bool,
    technology_only: bool,
) -> bool:
    """A successful building action should be followed by an immediate recheck."""
    return bool(
        INTERNAL_AFFAIRS_CONTRACT[
            "fillEveryAvailableBuildingAndTechnologyQueuePerRun"
        ]
        and acted
        and not technology_only
    )


def apply_building_sync_to_fief(
    state: dict[str, Any],
    action_result: dict[str, Any],
) -> bool:
    """Reuse the authoritative 0x8200 building list for the next batch action."""
    buildings = (
        action_result.get("buildings")
        or action_result.get("checkedBuildings")
        or []
    )
    if not buildings:
        return False
    state["buildings"] = list(buildings)
    return True


def plan_next_internal_affairs_action(
    fiefs: list[dict[str, Any]],
    technologies: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    prefer_technology: bool = False,
) -> dict[str, Any]:
    """Choose at most one deterministic building or technology submission."""

    states = sorted(
        [dict(value) for value in fiefs if isinstance(value, dict)],
        key=lambda value: int(value.get("fiefId") or 0),
    )
    interval_millis = auto_domestic_interval_seconds(states) * 1000
    enabled = bool(config.get("enabled"))
    upgrade_buildings = bool(config.get("upgradeBuildings", True))
    upgrade_technology = bool(config.get("upgradeTechnology"))
    try:
        empty_type = int(config.get("emptyBuildingType", 1))
    except (TypeError, ValueError):
        empty_type = 1
    if empty_type not in BUILDING_TYPE_NAMES or empty_type < 0:
        empty_type = 1

    technology_rows = [
        dict(value)
        for value in technologies
        if isinstance(value, dict)
        and int(value.get("technologyId", -1)) in TECHNOLOGY_NAMES
    ]
    occupied_academies = {
        int(value["academyInstanceId"])
        for value in technology_rows
        if bool(value.get("researching"))
        and value.get("academyInstanceId") is not None
    }

    building_plan: dict[str, Any] | None = None
    if enabled:
        hall_candidates: list[tuple[int, int, dict[str, Any], dict[str, Any]]] = []
        for state in states:
            busy, capacity = fief_build_queue_state(state)
            hall = fief_hall(state)
            if busy < capacity and hall and hall_must_upgrade_first(state):
                hall_candidates.append((
                    int(hall.get("level") or 0),
                    int(state.get("fiefId") or 0),
                    state,
                    hall,
                ))
        if hall_candidates:
            level, fief_id, _state, hall = min(hall_candidates)
            target_level = level + 1
            building_plan = {
                "action": "building",
                "description": f"优先升级大厅{level}→{target_level}",
                "fiefId": fief_id,
                "slot": int(hall.get("slot") or 0),
                "buildingType": 0,
                "previousLevel": level,
                "targetLevel": target_level,
            }

    if enabled and building_plan is None:
        for state in states:
            busy, capacity = fief_build_queue_state(state)
            if busy >= capacity:
                continue
            occupied = {
                int(value.get("slot") or 0)
                for value in state.get("buildings") or []
                if isinstance(value, dict)
            }
            empty_slots = [slot for slot in range(1, 13) if slot not in occupied]
            if not empty_slots:
                continue
            fief_id = int(state.get("fiefId") or 0)
            building_plan = {
                "action": "building",
                "description": (
                    "空地建造"
                    + str(BUILDING_TYPE_NAMES.get(empty_type, empty_type))
                ),
                "fiefId": fief_id,
                "slot": empty_slots[0],
                "buildingType": empty_type,
                "previousLevel": None,
                "targetLevel": 1,
            }
            break

    if enabled and upgrade_buildings and building_plan is None:
        raw_priority = config.get("buildingPriority")
        raw_priority = raw_priority if isinstance(raw_priority, list) else []
        priority_types: list[int] = []
        for value in raw_priority:
            try:
                item = int(value)
            except (TypeError, ValueError):
                item = BUILDING_NAME_TYPES.get(str(value), -1)
            if item >= 0 and item not in priority_types:
                priority_types.append(item)
        lowest_first = bool(config.get("upgradeLowestFirst", True))
        candidates: list[tuple[int, int, int, int, dict[str, Any]]] = []
        for state in states:
            busy, capacity = fief_build_queue_state(state)
            hall = fief_hall(state)
            if busy >= capacity or hall is None:
                continue
            fief_id = int(state.get("fiefId") or 0)
            for building in state.get("buildings") or []:
                if not isinstance(building, dict):
                    continue
                building_type = int(building.get("type", -1))
                if (
                    building_type == 3
                    and int(building.get("instanceId") or 0)
                    in occupied_academies
                ):
                    continue
                if not building_can_follow_hall(state, building):
                    continue
                priority = (
                    priority_types.index(building_type)
                    if building_type in priority_types
                    else len(priority_types)
                )
                level = int(building.get("level") or 0)
                candidates.append((
                    priority,
                    level if lowest_first else -level,
                    fief_id,
                    int(building.get("slot") or 0),
                    building,
                ))
        if candidates:
            _priority, _level_order, fief_id, slot, building = min(candidates)
            level = int(building.get("level") or 0)
            building_type = int(building.get("type") or 0)
            building_plan = {
                "action": "building",
                "description": (
                    f"升级{BUILDING_TYPE_NAMES.get(building_type, building_type)}"
                    f"{level}→{level + 1}"
                ),
                "fiefId": fief_id,
                "slot": slot,
                "buildingType": building_type,
                "previousLevel": level,
                "targetLevel": level + 1,
            }

    technology_plan: dict[str, Any] | None = None
    if upgrade_technology:
        selected_ids = []
        for value in config.get("technologyIds") or []:
            try:
                tech_id = int(value)
            except (TypeError, ValueError):
                continue
            if tech_id in TECHNOLOGY_NAMES and tech_id not in selected_ids:
                selected_ids.append(tech_id)
        researching_ids = {
            int(value.get("technologyId") or 0)
            for value in technology_rows
            if bool(value.get("researching"))
        }
        candidates: list[
            tuple[int, int, int, int, dict[str, Any], dict[str, Any]]
        ] = []
        for state in states:
            fief_id = int(state.get("fiefId") or 0)
            for academy in state.get("buildings") or []:
                if not isinstance(academy, dict):
                    continue
                if (
                    int(academy.get("type", -1)) != 3
                    or bool(academy.get("busy"))
                    or int(academy.get("instanceId") or 0)
                    in occupied_academies
                ):
                    continue
                academy_level = int(academy.get("level") or 0)
                for technology in technology_rows:
                    tech_id = int(technology.get("technologyId") or 0)
                    tech_level = int(technology.get("level") or 0)
                    if (
                        tech_id in selected_ids
                        and tech_id not in researching_ids
                        and tech_level < academy_level
                    ):
                        candidates.append((
                            tech_level,
                            selected_ids.index(tech_id),
                            fief_id,
                            int(academy.get("slot") or 0),
                            academy,
                            technology,
                        ))
        if candidates:
            level, _selected, fief_id, slot, _academy, technology = min(
                candidates
            )
            tech_id = int(technology.get("technologyId") or 0)
            technology_plan = {
                "action": "technology",
                "description": (
                    f"升级{TECHNOLOGY_NAMES.get(tech_id, tech_id)}"
                    f"{level}→{level + 1}"
                ),
                "fiefId": fief_id,
                "academySlot": slot,
                "technologyId": tech_id,
                "previousLevel": level,
                "targetLevel": level + 1,
            }

    if building_plan and technology_plan:
        selected = technology_plan if prefer_technology else building_plan
    else:
        selected = building_plan or technology_plan
    if selected is None:
        return {
            "action": None,
            "reason": "当前封地没有可提交的建筑或科技队列",
            "nextWakeDelayMillis": interval_millis,
            "nextPreferTechnology": bool(prefer_technology),
        }
    if selected["action"] == "building":
        cost = building_resource_cost(
            int(selected["buildingType"]),
            int(selected["targetLevel"]),
        )
    else:
        cost = technology_resource_cost(
            int(selected["technologyId"]),
            int(selected["targetLevel"]),
        )
    if cost is None:
        return {
            "action": None,
            "reason": f"{selected['description']}缺少共享成本表，已失败关闭",
            "blocked": True,
            "candidate": selected,
            "nextWakeDelayMillis": None,
            "nextPreferTechnology": bool(prefer_technology),
        }
    if int(cost.get("extra") or 0) > 0:
        return {
            "action": None,
            "reason": (
                f"{selected['description']}需要第三类资源"
                f"{int(cost['extra'])}，共享核心尚未接入其余额，已失败关闭"
            ),
            "blocked": True,
            "candidate": selected,
            "requiredExtra": int(cost["extra"]),
            "nextWakeDelayMillis": None,
            "nextPreferTechnology": bool(prefer_technology),
        }
    return {
        **selected,
        "requiredCopper": int(cost["copper"]),
        "requiredFood": int(cost["food"]),
        "requiredExtra": int(cost.get("extra") or 0),
        "nextWakeDelayMillis": (
            1_000
            if selected["action"] == "building" or enabled
            else interval_millis
        ),
        "nextPreferTechnology": selected["action"] == "building"
        if enabled and upgrade_technology else bool(prefer_technology),
    }
