"""Formation, refill and healing wire rules extracted from the desktop core."""

from __future__ import annotations

import struct
from typing import Any, Dict, List, Tuple

from ..protocol.wire import normalize_hex_id, printable, read_utf


SOLDIER_TYPE_CODES = {
    "民兵": 0,
    "弩兵": 1,
    "弓兵": 2,
    "轻骑兵": 3,
    "弩车": 4,
    "冲城车": 5,
    "轻步兵": 6,
    "近卫兵": 7,
    "重步兵": 8,
    "弩骑兵": 9,
    "重骑兵": 10,
    "铁骑兵": 11,
    "投石车": 12,
    "重弩车": 13,
    "强弩兵": 14,
    "骁骑兵": 15,
}
SOLDIER_CODE_NAMES = {value: key for key, value in SOLDIER_TYPE_CODES.items()}


def soldier_type_code(name_or_code: Any) -> int:
    if isinstance(name_or_code, int):
        return int(name_or_code)
    value = str(name_or_code or "").strip()
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return int(value)
    return SOLDIER_TYPE_CODES.get(value, 3)


def soldier_type_name(code: Any) -> str:
    try:
        normalized = int(code)
    except Exception:
        return str(code)
    if normalized == -1:
        return "无配兵"
    return SOLDIER_CODE_NAMES.get(normalized, f"兵种{normalized}")


def build_refill_payload(general_chunks: List[str]) -> bytes:
    if not general_chunks:
        raise RuntimeError("批量补兵至少需要一个将领")
    if len(general_chunks) > 0xFF:
        raise RuntimeError("批量补兵将领数量超过 255")
    payload = bytearray([len(general_chunks)])
    for chunk in general_chunks:
        payload += bytes.fromhex(normalize_hex_id(chunk))
    return bytes(payload)


def parse_refill_response(payload: bytes) -> Dict[str, Any]:
    position = 0
    output: Dict[str, Any] = {
        "rawHex": payload.hex()[:4096],
        "textPreview": printable(payload, 1200),
    }
    try:
        if len(payload) < 3:
            return {**output, "success": False, "message": "响应过短"}
        status = struct.unpack(">b", payload[position:position + 1])[0]
        position += 1
        message, position = read_utf(payload, position)
        output.update({"status": status, "message": message, "success": status == 0})
        if status != 0:
            return output
        if position < len(payload):
            role_count = payload[position]
            position += 1
            roles = []
            for _ in range(role_count):
                if position + 13 > len(payload):
                    break
                general_id = struct.unpack(">q", payload[position:position + 8])[0]
                position += 8
                army_type = payload[position]
                position += 1
                army_count = struct.unpack(">i", payload[position:position + 4])[0]
                position += 4
                roles.append(
                    {
                        "generalId": general_id,
                        "generalIdHex": f"{general_id:016x}",
                        "armyType": army_type,
                        "armyCount": army_count,
                    }
                )
            output["roleUpdates"] = roles
        if position + 9 <= len(payload):
            fief_id = struct.unpack(">q", payload[position:position + 8])[0]
            position += 8
            soldier_type_count = payload[position]
            position += 1
            inventory = []
            for _ in range(soldier_type_count):
                if position + 5 > len(payload):
                    break
                soldier_type = payload[position]
                position += 1
                amount = struct.unpack(">i", payload[position:position + 4])[0]
                position += 4
                inventory.append({"soldierType": soldier_type, "amount": amount})
            output["fiefId"] = fief_id
            output["soldierInventory"] = inventory
    except Exception as error:
        output.update({"success": False, "parseError": str(error)})
    return output


def build_assign_troops_payload(
    general_id_hex: str,
    soldier_type_name_or_code: Any,
    count: int,
    group: int = 0,
) -> bytes:
    general_id = int(normalize_hex_id(general_id_hex), 16)
    return struct.pack(
        ">qbhi",
        general_id,
        int(group),
        soldier_type_code(soldier_type_name_or_code),
        int(count),
    )


def parse_assign_troops_response(payload: bytes) -> Dict[str, Any]:
    position = 0
    output: Dict[str, Any] = {
        "rawHex": payload.hex()[:4096],
        "textPreview": printable(payload, 1200),
    }
    try:
        if len(payload) < 17:
            return {**output, "success": False, "message": "0x8226 响应过短"}
        status = struct.unpack(">b", payload[position:position + 1])[0]
        position += 1
        general_id = struct.unpack(">q", payload[position:position + 8])[0]
        position += 8
        old_type = struct.unpack(">h", payload[position:position + 2])[0]
        position += 2
        old_count = struct.unpack(">h", payload[position:position + 2])[0]
        position += 2
        new_type = struct.unpack(">h", payload[position:position + 2])[0]
        position += 2
        new_count = struct.unpack(">h", payload[position:position + 2])[0]
        position += 2
        if status == 1:
            current = (
                "无配兵"
                if new_type == -1 and new_count == 0
                else f"{new_count} {soldier_type_name(new_type)}"
            )
            message = f"配兵成功：当前 {current}"
        else:
            message = (
                f"配兵失败(status={status}，通常表示兵种/数量不可用、"
                "库存不足或将领当前不可配兵)"
            )
        output.update(
            {
                "status": status,
                "success": status == 1,
                "message": message,
                "generalId": general_id,
                "generalIdHex": f"{general_id:016x}",
                "oldSoldierTypeCode": old_type,
                "oldSoldierType": soldier_type_name(old_type),
                "oldSoldierCount": old_count,
                "assignedSoldierTypeCode": new_type,
                "assignedSoldierType": soldier_type_name(new_type),
                "assignedSoldierCount": new_count,
                "echoSoldierTypeCode": new_type,
                "echoSoldierCount": new_count,
                "fieldA": old_type,
                "fieldB": old_count,
                "currentSoldierCount": new_count,
                "soldierLimit": new_count,
            }
        )
        if status == 1 and position < len(payload):
            count = payload[position]
            position += 1
            inventory = []
            for _ in range(count):
                if position + 5 > len(payload):
                    break
                code = struct.unpack(">b", payload[position:position + 1])[0]
                position += 1
                amount = struct.unpack(">i", payload[position:position + 4])[0]
                position += 4
                inventory.append({"soldierTypeCode": code, "amount": amount})
            output["soldierInventory"] = inventory
    except Exception as error:
        output.update(
            {
                "success": False,
                "parseError": str(error),
                "message": "配兵响应解析失败",
            }
        )
    return output


def build_heal_preinfo_payload(
    fief_id: Any,
    soldier_code: int,
    count: int,
) -> bytes:
    return struct.pack(">qhi", int(fief_id), int(soldier_code), int(count))


def build_heal_payload(
    fief_id: Any,
    soldier_group: int,
    soldier_code: int,
    count: int,
    use_gold: bool = False,
) -> bytes:
    return struct.pack(
        ">qbhib",
        int(fief_id),
        int(soldier_group),
        int(soldier_code),
        int(count),
        1 if use_gold else 0,
    )


def build_heal_all_payloads(fief_id: Any) -> Tuple[bytes, bytes]:
    return (
        build_heal_preinfo_payload(fief_id, -1, -1),
        build_heal_payload(fief_id, 2, 0, -1, use_gold=False),
    )


def parse_heal_preinfo_response(payload: bytes) -> Dict[str, Any]:
    output: Dict[str, Any] = {
        "rawHex": payload.hex()[:4096],
        "textPreview": printable(payload, 1200),
    }
    try:
        if len(payload) < 26:
            return {**output, "success": False, "message": "0x8231 响应过短"}
        output.update(
            {
                "success": True,
                "fiefId": struct.unpack(">q", payload[0:8])[0],
                "soldierType": struct.unpack(">h", payload[8:10])[0],
                "copperCost": struct.unpack(">q", payload[10:18])[0],
                "goldCost": struct.unpack(">q", payload[18:26])[0],
            }
        )
    except Exception as error:
        output.update({"success": False, "parseError": str(error)})
    return output


def parse_heal_response(payload: bytes) -> Dict[str, Any]:
    output: Dict[str, Any] = {
        "rawHex": payload.hex()[:4096],
        "textPreview": printable(payload, 1200),
    }
    try:
        if len(payload) < 18:
            return {**output, "success": False, "message": "0x8230 响应过短"}
        status = struct.unpack(">b", payload[0:1])[0]
        messages = {
            0: "治疗成功",
            -1: "铜钱不足",
            -2: "治疗失败",
            -3: "黄金不足",
        }
        output.update(
            {
                "status": status,
                "success": status == 0,
                "message": messages.get(status, f"未知治疗状态 {status}"),
                "firstLong": struct.unpack(">q", payload[1:9])[0],
                "secondLong": struct.unpack(">q", payload[9:17])[0],
                "hasExtraState": bool(payload[17]),
            }
        )
    except Exception as error:
        output.update({"success": False, "parseError": str(error)})
    return output
