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
