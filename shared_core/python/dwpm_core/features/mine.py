"""Mine preview, recall and march-speed protocol rules."""

from __future__ import annotations

import struct
from typing import Any, Dict, List, Optional, Tuple

from ..contracts import load_behavior_contract
from ..protocol.wire import extract_utf_strings


MINE_CONTRACT = load_behavior_contract()["mine"]
MINE_PREVIEW_MINIMUM_BYTES = int(MINE_CONTRACT["preview"]["minimumPayloadBytes"])
MINE_SPEED_STOP_BELOW_SECONDS = int(MINE_CONTRACT["speed"]["stopBelowSeconds"])
MARCH_SPEED_SECONDS = {
    int(item_id): int(seconds)
    for item_id, seconds in MINE_CONTRACT["speed"]["itemSeconds"].items()
}
MARCH_SPEED_STATUS_MESSAGES = {
    0: "行军加速成功",
    -1: "行军加速失败",
    -2: "行军已经结束",
    -3: "自动VIP状态下无法使用行军符",
}


def parse_mine_preview(payload: bytes) -> Dict[str, Any]:
    output: Dict[str, Any] = {"rawHex": payload.hex(), "valid": False}
    if len(payload) < MINE_PREVIEW_MINIMUM_BYTES:
        return {
            **output,
            "error": (
                f"出征预览长度不足：{len(payload)}/"
                f"{MINE_PREVIEW_MINIMUM_BYTES}"
            ),
        }
    try:
        march_seconds, arrival_at, second_time, win_rate, x, y = struct.unpack(
            ">iqqBHH", payload[:MINE_PREVIEW_MINIMUM_BYTES]
        )
        output.update(
            {
                "valid": march_seconds >= 0,
                "marchSeconds": march_seconds,
                "arrivalAt": arrival_at,
                "secondTime": second_time,
                "winRate": win_rate,
                "x": x,
                "y": y,
                "trailingHex": payload[MINE_PREVIEW_MINIMUM_BYTES:].hex(),
            }
        )
    except Exception as error:
        output["error"] = str(error)
    return output


def parse_recall_response(
    payload: bytes,
    battle_id: Optional[int] = None,
) -> Dict[str, Any]:
    output: Dict[str, Any] = {
        "rawHex": payload.hex()[:4096],
        "success": False,
    }
    if len(payload) < 8:
        return {**output, "message": f"召回响应长度不足：{len(payload)}"}
    legacy_battle_id = struct.unpack(">q", payload[:8])[0]
    response_battle_id = legacy_battle_id
    source = "prefix"
    for field in extract_utf_strings(payload, max_len=600):
        if "【返回】" not in str(field.get("text") or ""):
            continue
        position = int(field["offset"]) + 2 + int(field["length"])
        if position + 14 > len(payload):
            continue
        event_battle_id = int.from_bytes(payload[position + 6:position + 14], "big")
        if event_battle_id <= 0:
            continue
        response_battle_id = event_battle_id
        source = "returnEvent"
        if battle_id is None or event_battle_id == int(battle_id):
            break
    success = response_battle_id > 0 and (
        battle_id is None or response_battle_id == int(battle_id)
    )
    return {
        **output,
        "success": success,
        "battleId": response_battle_id,
        "battleIdHex": f"{response_battle_id & 0xffffffffffffffff:016x}",
        "battleIdSource": source,
        "message": (
            "召回请求已受理" if success else "召回响应 battleId 不匹配"
        ),
        "militaryPayloadBytes": max(0, len(payload) - 8),
    }


def build_march_speed_payload(battle_id: int, item_id: int) -> bytes:
    if int(item_id) not in MARCH_SPEED_SECONDS:
        raise RuntimeError(f"未知行军符：{item_id}")
    return struct.pack(">qH", int(battle_id), int(item_id))


def parse_march_speed_response(payload: bytes) -> Dict[str, Any]:
    if not payload:
        return {
            "success": False,
            "status": None,
            "message": "行军加速响应为空",
            "rawHex": "",
        }
    status = struct.unpack(">b", payload[:1])[0]
    return {
        "success": status == 0,
        "status": status,
        "finished": status == -2,
        "message": MARCH_SPEED_STATUS_MESSAGES.get(
            status,
            f"行军加速未知状态 {status}",
        ),
        "militaryPayloadBytes": max(0, len(payload) - 1),
        "rawHex": payload.hex()[:4096],
    }


def inventory_march_speed_counts(inventory: Dict[str, Any]) -> Dict[int, int]:
    counts = {item_id: 0 for item_id in MARCH_SPEED_SECONDS}
    for row in inventory.get("items") or []:
        try:
            item_id = int(row.get("itemId"))
            count = max(0, int(row.get("count") or 0))
        except (TypeError, ValueError, AttributeError):
            continue
        if item_id in counts:
            counts[item_id] += count
    return counts


def choose_march_speed_items(
    remaining_seconds: int,
    inventory_items: List[Dict[str, Any]],
) -> List[int]:
    required_seconds = max(
        0,
        int(remaining_seconds) - MINE_SPEED_STOP_BELOW_SECONDS,
    )
    if required_seconds <= 0:
        return []
    counts = inventory_march_speed_counts({"items": inventory_items})
    available_seconds = sum(
        counts[item_id] * MARCH_SPEED_SECONDS[item_id]
        for item_id in MARCH_SPEED_SECONDS
    )
    if available_seconds < required_seconds:
        return [
            item_id
            for item_id in sorted(MARCH_SPEED_SECONDS, reverse=True)
            for _ in range(counts[item_id])
        ]

    target_units = (required_seconds + 899) // 900
    max_units = target_units + 11
    item_units = {
        item_id: seconds // 900
        for item_id, seconds in MARCH_SPEED_SECONDS.items()
    }
    states: Dict[int, Tuple[int, int, int, int]] = {0: (0, 0, 0, 0)}
    item_ids = sorted(MARCH_SPEED_SECONDS)

    def preference(combo: Tuple[int, int, int, int]) -> Tuple[Any, ...]:
        return (
            sum(combo),
            -combo[3],
            -combo[2],
            -combo[1],
            -combo[0],
        )

    for index, item_id in enumerate(item_ids):
        usable = min(counts[item_id], max_units // item_units[item_id] + 1)
        for _ in range(usable):
            previous = list(states.items())
            for total, combo in previous:
                next_total = total + item_units[item_id]
                if next_total > max_units:
                    continue
                next_combo = list(combo)
                next_combo[index] += 1
                candidate = tuple(next_combo)
                current = states.get(next_total)
                if current is None or preference(candidate) < preference(current):
                    states[next_total] = candidate
    winning_total = min(total for total in states if total >= target_units)
    winning = states[winning_total]
    return [
        item_id
        for item_id in sorted(item_ids, reverse=True)
        for _ in range(winning[item_ids.index(item_id)])
    ]


def build_recall_payload(battle_id: int) -> bytes:
    withdraw = MINE_CONTRACT["withdraw"]
    return (
        bytes.fromhex(str(withdraw["payloadPrefixHex"]))
        + struct.pack(">q", int(battle_id))
        + bytes.fromhex(str(withdraw["payloadSuffixHex"]))
    )
