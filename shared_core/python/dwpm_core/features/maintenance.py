"""General maintenance, resource exchange and inventory action protocols."""

from __future__ import annotations

import struct
from typing import Any, Mapping, Sequence

from ..protocol.wire import read_utf
from .inventory import EQUIPMENT_QUALITY_NAMES, parse_8104_inventory


def build_add_loyalty_payload(general_id: int, delta: int) -> bytes:
    amount = int(delta)
    if amount <= 0 or amount > 0xFFFF:
        raise RuntimeError(f"加忠数值无效：{amount}")
    return struct.pack(">qBHB", int(general_id), 0, amount, 0)


def parse_821f_loyalty_response(payload: bytes) -> dict[str, Any]:
    """Parse the add-loyalty reply, including its single and batch modes."""
    out: dict[str, Any] = {
        "rawHex": payload.hex()[:4096],
        "success": False,
        "generals": [],
    }
    if len(payload) < 42:
        return {**out, "message": f"加忠响应长度不足：{len(payload)}/42"}
    try:
        position = 0
        result = struct.unpack(">b", payload[position:position + 1])[0]
        position += 1
        mode = struct.unpack(">b", payload[position:position + 1])[0]
        position += 1
        general_id = struct.unpack(">q", payload[position:position + 8])[0]
        position += 8
        actual_cost = struct.unpack(">q", payload[position:position + 8])[0]
        position += 8
        copper = struct.unpack(">q", payload[position:position + 8])[0]
        position += 8
        gold = struct.unpack(">q", payload[position:position + 8])[0]
        position += 8
        resource_g = struct.unpack(">q", payload[position:position + 8])[0]
        position += 8
        generals: list[dict[str, Any]] = []
        if mode == 2:
            if position >= len(payload):
                raise ValueError("批量加忠响应缺少将领数量")
            count = payload[position]
            position += 1
            for _ in range(count):
                if position + 12 > len(payload):
                    raise ValueError("批量加忠响应中的将领记录不完整")
                row_id, loyalty, loyalty_limit = struct.unpack(
                    ">qHH",
                    payload[position:position + 12],
                )
                position += 12
                generals.append(
                    {
                        "generalId": row_id,
                        "loyalty": loyalty,
                        "loyaltyLimit": loyalty_limit,
                    }
                )
        else:
            if position + 4 > len(payload):
                raise ValueError("单将领加忠响应缺少忠诚度结果")
            loyalty, loyalty_limit = struct.unpack(
                ">HH",
                payload[position:position + 4],
            )
            position += 4
            generals.append(
                {
                    "generalId": general_id,
                    "loyalty": loyalty,
                    "loyaltyLimit": loyalty_limit,
                }
            )
        success = result == 0
        return {
            **out,
            "success": success,
            "result": result,
            "mode": mode,
            "generalId": general_id,
            "actualCost": actual_cost,
            "copper": copper,
            "gold": gold,
            "resourceG": resource_g,
            "generals": generals,
            "message": (
                "忠诚度增加成功"
                if success
                else f"忠诚度增加失败(result={result})"
            ),
            "trailingHex": payload[position:].hex(),
        }
    except Exception as error:
        return {
            **out,
            "parseError": str(error),
            "message": f"加忠响应解析失败：{error}",
        }


def parse_status_utf(payload: bytes) -> tuple[int | None, str, int]:
    if not payload:
        return None, "空响应", 0
    status = struct.unpack(">b", payload[:1])[0]
    if len(payload) < 3:
        return status, "", 1
    message, position = read_utf(payload, 1)
    return status, message, position


def build_use_general_item_payload(
    general_id: int | str,
    item_id: int,
    count: int = 1,
) -> bytes:
    gid = (
        int(str(general_id), 16)
        if isinstance(general_id, str)
        and any(character in "abcdefABCDEF" for character in general_id)
        else int(general_id)
    )
    if gid <= 0:
        raise RuntimeError("使用道具缺少有效将领 ID")
    if not 0 <= int(item_id) <= 0xFFFF:
        raise RuntimeError(f"道具 ID 超出范围：{item_id}")
    if not 1 <= int(count) <= 0xFFFF:
        raise RuntimeError(f"道具数量超出范围：{count}")
    return struct.pack(">qHH", gid, int(item_id), int(count))


def parse_use_general_item_response(
    payload: bytes,
    source_opcode: str = "live/0x1218/0x8218",
    *,
    item_names: Mapping[int, str] | None = None,
    equipment_templates: Mapping[int, Mapping[str, Any]] | None = None,
    quality_names: Sequence[str] = EQUIPMENT_QUALITY_NAMES,
) -> dict[str, Any]:
    status = struct.unpack(">b", payload[:1])[0] if payload else None
    message = ""
    inventory = None
    if status == 0:
        inventory = parse_8104_inventory(
            payload[1:],
            source_opcode,
            item_names=item_names,
            equipment_templates=equipment_templates,
            quality_names=quality_names,
        )
    elif payload:
        _status, message, _position = parse_status_utf(payload)
    return {
        "success": status == 0,
        "status": status,
        "message": message or (
            "活血丹使用成功"
            if status == 0
            else f"使用失败状态 {status}"
        ),
        "inventory": inventory,
    }


def build_resource_exchange_payload(direction: int, amount: int) -> bytes:
    if direction not in (0, 1):
        raise RuntimeError(f"资源转换方向无效：{direction}")
    if amount <= 0:
        raise RuntimeError("资源转换数量必须大于 0")
    return struct.pack(">Bq", direction, int(amount))


def parse_resource_exchange_response(payload: bytes) -> dict[str, Any]:
    if not payload:
        return {
            "status": None,
            "success": False,
            "message": "资源转换响应为空",
            "rawHex": "",
        }
    status = struct.unpack(">b", payload[:1])[0]
    message = ""
    position = 1
    if status != 0 and len(payload) >= 3:
        _status, message, position = parse_status_utf(payload)
    out: dict[str, Any] = {
        "status": status,
        "success": status == 0,
        "message": message or (
            "资源转换成功"
            if status == 0
            else f"资源转换失败状态 {status}"
        ),
        "rawHex": payload.hex(),
    }
    if status == 0 and len(payload) >= 17:
        out["copper"] = struct.unpack(">q", payload[position:position + 8])[0]
        out["food"] = struct.unpack(">q", payload[position + 8:position + 16])[0]
    return out


def build_delete_all_mail_payload() -> bytes:
    return b"\x00\x01" + struct.pack(">q", -1)


def parse_delete_mail_response(payload: bytes) -> dict[str, Any]:
    if len(payload) < 4:
        return {
            "success": False,
            "message": "邮件删除响应过短",
            "rawHex": payload.hex(),
        }
    action = payload[0]
    box_type = payload[1]
    remaining = int.from_bytes(payload[2:4], "big", signed=False)
    success = action == 0 and box_type == 1
    return {
        "success": success,
        "action": action,
        "boxType": box_type,
        "remaining": remaining,
        "message": (
            "邮件清理完成"
            if success
            else f"邮件清理响应异常 action={action} box={box_type}"
        ),
        "rawHex": payload.hex(),
    }


def build_discard_inventory_payload(
    kind: int,
    object_id: int,
    count: int = 1,
) -> bytes:
    if kind not in (0, 1):
        raise RuntimeError(f"宝库丢弃类型无效：{kind}")
    if object_id < 0:
        raise RuntimeError("宝库丢弃对象 ID 无效")
    if count <= 0:
        raise RuntimeError("宝库丢弃数量必须大于 0")
    return (
        struct.pack(">Bqi", kind, int(object_id), int(count))
        + struct.pack(">q", -1)
    )


def parse_discard_inventory_response(
    payload: bytes,
    source_opcode: str = "live/0x1103/0x8103",
    *,
    item_names: Mapping[int, str] | None = None,
    equipment_templates: Mapping[int, Mapping[str, Any]] | None = None,
    quality_names: Sequence[str] = EQUIPMENT_QUALITY_NAMES,
) -> dict[str, Any]:
    status, message, position = parse_status_utf(payload)
    inventory = (
        parse_8104_inventory(
            payload[position:],
            source_opcode,
            item_names=item_names,
            equipment_templates=equipment_templates,
            quality_names=quality_names,
        )
        if status == 0 and position < len(payload)
        else None
    )
    return {
        "success": status == 0,
        "status": status,
        "message": message or (
            "丢弃成功"
            if status == 0
            else f"丢弃失败状态 {status}"
        ),
        "inventory": inventory,
        "rawHex": payload.hex(),
    }


def build_use_inventory_item_payload(item_id: int, count: int = 1) -> bytes:
    if not 0 <= int(item_id) <= 0xFFFF:
        raise RuntimeError(f"道具 ID 超出范围：{item_id}")
    if not 1 <= int(count) <= 0xFFFF:
        raise RuntimeError(f"道具数量超出范围：{count}")
    return struct.pack(">HH", int(item_id), int(count))


def equipment_is_safe_to_discard(
    equipment: dict[str, Any],
    *,
    max_quality: int,
    max_level: int,
    quality_names: Sequence[str] = EQUIPMENT_QUALITY_NAMES,
) -> tuple[bool, str]:
    if int(equipment.get("instanceId") or -1) <= 0:
        return False, "装备实例 ID 无效"
    if bool(equipment.get("famous")):
        return False, "名将装备"
    if int(equipment.get("strengthen") or 0) > 0:
        return False, "已经强化"
    if str(equipment.get("extraText") or "").strip():
        return False, "存在炼魂/额外描述"
    level = int(equipment.get("level") or 0)
    if level >= 80:
        return False, "80级以上保护"
    if level >= int(max_level):
        return False, f"等级不低于{max_level}"
    quality = int(
        equipment.get("quality")
        if equipment.get("quality") is not None
        else -1
    )
    if quality < 0 or quality > int(max_quality):
        return False, f"品质高于{quality_names[max_quality]}"
    return True, ""
