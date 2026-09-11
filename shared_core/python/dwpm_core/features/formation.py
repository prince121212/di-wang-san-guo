"""Formation, refill and healing wire rules extracted from the desktop core."""

from __future__ import annotations

import struct
from typing import Any, Dict, List, Mapping, Sequence, Tuple

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


def strict_soldier_type(value: Any) -> Tuple[int, str]:
    """Normalize an API soldier type without the legacy silent cavalry fallback."""

    if isinstance(value, bool):
        raise ValueError("兵种无效")
    if isinstance(value, int):
        code = int(value)
    else:
        text = str(value or "").strip()
        if text in SOLDIER_TYPE_CODES:
            code = SOLDIER_TYPE_CODES[text]
        else:
            try:
                code = int(text, 10)
            except (TypeError, ValueError) as error:
                raise ValueError(f"未知兵种：{text or '空'}") from error
    if code not in SOLDIER_CODE_NAMES:
        raise ValueError(f"未知兵种代码：{code}")
    return code, SOLDIER_CODE_NAMES[code]


def positive_game_id(value: Any, field: str = "ID") -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} 无效")
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"缺少{field}")
    try:
        if text.lower().startswith("0x"):
            result = int(text[2:], 16)
        elif any(character in "abcdefABCDEF" for character in text):
            result = int(text, 16)
        else:
            result = int(text, 10)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} 无效：{text}") from error
    if not 0 < result <= 0x7FFFFFFFFFFFFFFF:
        raise ValueError(f"{field} 超出范围：{text}")
    return result


def plan_troop_assignment(
    generals: Sequence[Mapping[str, Any]],
    army_rows: Sequence[Mapping[str, Any]],
    request: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> Dict[str, Any]:
    """Own the safety checks which previously diverged between Python and Kotlin."""

    general_id = positive_game_id(request.get("generalId"), "将领 ID")
    target_code, target_name = strict_soldier_type(
        request.get("soldierTypeCode", request.get("soldierType"))
    )
    try:
        requested_count = int(request.get("soldierCount"))
    except (TypeError, ValueError) as error:
        raise ValueError("配兵数量无效") from error
    if not 0 <= requested_count <= 0x7FFFFFFF:
        raise ValueError("配兵数量必须在 0..2147483647 之间")
    try:
        group = int(request.get("group") or 0)
    except (TypeError, ValueError) as error:
        raise ValueError("配兵分组无效") from error
    if not -128 <= group <= 127:
        raise ValueError("配兵分组必须在 -128..127 之间")

    general = next(
        (
            dict(row)
            for row in generals
            if positive_game_id(row.get("id"), "将领 ID") == general_id
        ),
        None,
    )
    if general is None:
        raise ValueError(f"未找到配兵将领：{general_id}")
    idle_status = int(contract.get("idleGeneralStatus") or 0)
    try:
        status = int(general.get("status"))
    except (TypeError, ValueError) as error:
        raise ValueError(f"无法确认将领{general.get('name') or general_id}状态") from error
    if status != idle_status:
        raise ValueError(
            f"将领{general.get('name') or general_id}当前不是空闲状态，未执行配兵"
        )
    try:
        troop_limit = max(0, int(general.get("troopLimit") or 0))
    except (TypeError, ValueError):
        troop_limit = 0
    effective_count = requested_count
    if bool(contract.get("clampCountToTroopLimit")) and troop_limit > 0:
        effective_count = min(requested_count, troop_limit)
    try:
        current_code = int(general.get("soldierTypeCode"))
    except (TypeError, ValueError):
        current_code = -1
    try:
        current_count = max(
            0,
            int(
                general.get(
                    "soldierCount",
                    general.get("currentSoldierCount", 0),
                )
                or 0
            ),
        )
    except (TypeError, ValueError):
        current_count = 0
    already_satisfied = (
        current_code == target_code and current_count == effective_count
    )

    idle_counts: Dict[int, int] = {}
    for raw in army_rows:
        try:
            code = int(raw.get("soldierTypeCode"))
            amount = int(
                raw.get("idleCount", raw.get("count", raw.get("amount", 0)))
                or 0
            )
        except (TypeError, ValueError):
            continue
        if code in SOLDIER_CODE_NAMES and amount > 0:
            idle_counts[code] = idle_counts.get(code, 0) + amount
    already_carrying_target = current_count if current_code == target_code else 0
    available = idle_counts.get(target_code, 0) + already_carrying_target
    if (
        bool(contract.get("precheckIdleSoldierInventory"))
        and not already_satisfied
        and effective_count > available
    ):
        raise ValueError(
            f"{general.get('name') or general_id}缺少"
            f"{effective_count - available}{target_name}；目标{effective_count}，"
            f"可用{available}，已保持原配兵不变"
        )
    return {
        "generalId": general_id,
        "generalIdHex": f"{general_id:016x}",
        "generalName": str(general.get("name") or general_id),
        "soldierType": target_name,
        "soldierTypeCode": target_code,
        "requestedCount": requested_count,
        "effectiveCount": effective_count,
        "troopLimit": troop_limit,
        "group": group,
        "currentSoldierTypeCode": current_code,
        "currentSoldierCount": current_count,
        "availableTargetCount": available,
        "alreadySatisfied": already_satisfied,
    }


def select_refill_generals(
    generals: Sequence[Mapping[str, Any]],
    requested_ids: Sequence[Any],
) -> List[Dict[str, Any]]:
    if not isinstance(requested_ids, (list, tuple)) or not requested_ids:
        raise ValueError("批量补兵至少需要一名将领")
    normalized: List[int] = []
    for value in requested_ids:
        general_id = positive_game_id(value, "将领 ID")
        if general_id not in normalized:
            normalized.append(general_id)
    if len(normalized) > 0xFF:
        raise ValueError("批量补兵将领数量超过 255")
    by_id = {
        positive_game_id(row.get("id"), "将领 ID"): dict(row)
        for row in generals
        if row.get("id") not in (None, "")
    }
    selected = []
    for general_id in normalized:
        row = by_id.get(general_id)
        if row is None:
            raise ValueError(f"未找到补兵将领：{general_id}")
        selected.append({
            "id": general_id,
            "idHex": f"{general_id:016x}",
            "name": str(row.get("name") or general_id),
        })
    return selected


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


def assignment_receipt_matches_plan(
    receipt: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    clearing: bool = False,
) -> bool:
    """Validate a 0x8226 receipt according to the requested operation.

    Normal assignment echoes the requested troop type and count.  Clearing is
    a different server operation even though it uses the same wire command:
    the server deliberately represents an unassigned general as
    ``assignedSoldierTypeCode=-1`` and ``assignedSoldierCount=0``.  Treating
    that sentinel as a normal assignment mismatch is what caused successful
    one-click clearing to be reported as a failure.
    """

    try:
        general_id = int(receipt.get("generalId") or 0)
        expected_general_id = int(plan.get("generalId") or 0)
        assigned_type = int(receipt.get("assignedSoldierTypeCode"))
        assigned_count = int(receipt.get("assignedSoldierCount"))
    except (TypeError, ValueError):
        return False
    if general_id != expected_general_id:
        return False
    if clearing:
        return assigned_type == -1 and assigned_count == 0
    try:
        expected_type = int(plan.get("soldierTypeCode"))
        expected_count = int(plan.get("effectiveCount"))
    except (TypeError, ValueError):
        return False
    return assigned_type == expected_type and assigned_count == expected_count


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


def plan_heal_wounded(
    generals: Sequence[Mapping[str, Any]],
    request: Mapping[str, Any],
    *,
    allow_all_if_count_unknown: bool = True,
) -> Dict[str, Any]:
    """Create the one canonical, auditable heal plan for both hosts."""

    raw_general_id = request.get("generalId")
    general_id = (
        positive_game_id(raw_general_id, "将领 ID")
        if raw_general_id not in (None, "")
        else None
    )
    general = next(
        (
            dict(row)
            for row in generals
            if general_id is not None
            and positive_game_id(row.get("id"), "将领 ID") == general_id
        ),
        {},
    )
    fief_id_value = (
        request.get("fiefId")
        or request.get("placeID")
        or request.get("placeId")
        or general.get("fiefId")
        or general.get("placeID")
        or general.get("placeId")
    )
    soldier_value = request.get("soldierTypeCode")
    if soldier_value in (None, ""):
        soldier_value = request.get("soldierType")
    if soldier_value in (None, ""):
        soldier_value = general.get("soldierTypeCode")
    if soldier_value in (None, ""):
        soldier_value = general.get("soldierType")
    if soldier_value in (None, ""):
        soldier_value = "轻骑兵"
    wounded_count = request.get("woundedCount")
    if wounded_count in (None, ""):
        wounded_count = general.get("woundedCount")
    if wounded_count in (None, ""):
        wounded_count = general.get("hurtSoldierCount")
    try:
        soldier_group = int(
            request.get("soldierGroup", request.get("healGroup", 2)) or 2
        )
    except (TypeError, ValueError) as error:
        raise ValueError("治疗兵组无效") from error
    if not -128 <= soldier_group <= 127:
        raise ValueError("治疗兵组必须在 -128..127 之间")
    # "Heal all" uses the protocol's fixed sentinel payload (soldier type 0,
    # count -1), so it does not require the representative general to carry a
    # concrete troop type. Fresh state legitimately reports -1 for an
    # unassigned general; validating it before this branch blocked maintenance
    # before any request was sent.
    if wounded_count in (None, "") and allow_all_if_count_unknown:
        if not fief_id_value:
            return {
                "ready": False,
                "reason": "缺少 fiefId/placeID，暂不发送治疗包",
                "opcode": "0x1230/0x1231",
                "generalId": general_id,
                "soldierType": soldier_type_name(0),
                "soldierTypeCode": 0,
            }
        fief_id = positive_game_id(fief_id_value, "封地 ID")
        pre_payload, heal_payload = build_heal_all_payloads(fief_id)
        return {
            "ready": True,
            "healAll": True,
            "reason": "未取得精确伤兵数量，使用客户端“治疗全部”语义",
            "opcode": "0x1230/0x1231",
            "generalId": general_id,
            "fiefId": fief_id,
            "soldierGroup": 2,
            "soldierType": soldier_type_name(0),
            "soldierTypeCode": 0,
            "woundedCount": -1,
            "preInfoPayloadHex": pre_payload.hex(),
            "healPayloadHex": heal_payload.hex(),
        }
    soldier_code, soldier_name = strict_soldier_type(soldier_value)
    if not fief_id_value:
        return {
            "ready": False,
            "reason": "缺少 fiefId/placeID，暂不发送治疗包",
            "opcode": "0x1230/0x1231",
            "generalId": general_id,
            "soldierType": soldier_name,
            "soldierTypeCode": soldier_code,
        }
    fief_id = positive_game_id(fief_id_value, "封地 ID")
    if wounded_count in (None, ""):
        return {
            "ready": False,
            "reason": "缺少当前伤兵数量，暂不发送治疗包",
            "opcode": "0x1230/0x1231",
            "generalId": general_id,
            "fiefId": fief_id,
            "soldierGroup": soldier_group,
            "soldierType": soldier_name,
            "soldierTypeCode": soldier_code,
            "preInfoPayloadHexIfCountKnown": build_heal_preinfo_payload(
                fief_id,
                soldier_code,
                0,
            ).hex(),
        }
    try:
        count = int(wounded_count)
    except (TypeError, ValueError) as error:
        raise ValueError("伤兵数量无效") from error
    if count <= 0:
        return {
            "ready": False,
            "noWounded": True,
            "reason": "当前无伤兵需要治疗",
            "generalId": general_id,
            "fiefId": fief_id,
            "soldierType": soldier_name,
            "soldierTypeCode": soldier_code,
            "woundedCount": count,
        }
    pre_payload = build_heal_preinfo_payload(fief_id, soldier_code, count)
    heal_payload = build_heal_payload(
        fief_id,
        soldier_group,
        soldier_code,
        count,
        use_gold=False,
    )
    return {
        "ready": True,
        "healAll": False,
        "generalId": general_id,
        "fiefId": fief_id,
        "soldierGroup": soldier_group,
        "soldierType": soldier_name,
        "soldierTypeCode": soldier_code,
        "woundedCount": count,
        "preInfoPayloadHex": pre_payload.hex(),
        "healPayloadHex": heal_payload.hex(),
    }


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
