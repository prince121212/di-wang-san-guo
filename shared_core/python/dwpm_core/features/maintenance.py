"""General maintenance, resource exchange and inventory action protocols."""

from __future__ import annotations

import struct
from typing import Any, Mapping, Sequence

from ..protocol.wire import read_utf
from .inventory import (
    EQUIPMENT_QUALITY_NAMES,
    equipment_is_safe_to_discard,
    parse_8104_inventory,
)


ENERGY_ITEM_ID = 12
ENERGY_ITEM_NAME = "活血丹"
ENERGY_ITEM_GAIN = 50
# The dispatch gate every expedition preflight applies after maintenance: a
# general at or below this reading cannot be sent out.  It is distinct from the
# user's auto-top-up threshold (``minEnergy``/``energyThreshold``), which only
# says when a 活血丹 *should* be spent.  A missing item therefore blocks nothing
# while the reading is still above this line - the general can march as is.
EXPEDITION_MIN_ENERGY = 20


def plan_general_energy_use(
    general: Mapping[str, Any],
    inventory: Mapping[str, Any],
    *,
    enabled: bool,
    threshold: int,
    action_name: str,
) -> dict[str, Any]:
    """Plan at most one confirmed energy-item mutation for one general."""

    normalized_threshold = max(20, min(int(threshold), 100))
    name = str(
        general.get("name")
        or general.get("id")
        or general.get("idHex")
        or "未知将领"
    )
    current_raw = (
        general.get("tili")
        if general.get("tili") is not None
        else general.get("energy")
    )
    if not bool(general.get("energyReliable")) or current_raw is None:
        return {
            "ready": False,
            "actionRequired": False,
            "reason": "energy-unreliable",
            "message": f"{action_name}无法确认{name}体力，未使用{ENERGY_ITEM_NAME}",
            "threshold": normalized_threshold,
        }
    try:
        current = int(current_raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{action_name}将领{name}体力无效：{current_raw}") from error
    if current >= normalized_threshold:
        return {
            "ready": True,
            "actionRequired": False,
            "reason": "energy-sufficient",
            "generalName": name,
            "before": current,
            "after": current,
            "threshold": normalized_threshold,
        }
    if not bool(enabled):
        return {
            "ready": True,
            "actionRequired": False,
            "reason": "auto-energy-disabled",
            "generalName": name,
            "before": current,
            "after": current,
            "threshold": normalized_threshold,
        }
    raw_general_id = general.get("id") or general.get("idHex")
    try:
        general_id = (
            int(general["id"])
            if general.get("id") not in (None, "")
            else int(str(raw_general_id).removeprefix("0x").removeprefix("0X"), 16)
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{action_name}检查到{name}体力={current}，"
            f"低于自动加体阈值{normalized_threshold}，但将领 ID 无效"
        ) from error
    if general_id <= 0:
        raise ValueError(
            f"{action_name}检查到{name}体力={current}，"
            f"低于自动加体阈值{normalized_threshold}，但缺少有效将领 ID"
        )
    rows = inventory.get("items")
    if not isinstance(rows, list):
        raise ValueError(f"{action_name}使用{ENERGY_ITEM_NAME}前背包快照无效")
    available = sum(
        max(0, int(row.get("count") or 0))
        for row in rows
        if isinstance(row, Mapping)
        and (
            int(row.get("itemId") or row.get("id") or -1) == ENERGY_ITEM_ID
            or str(row.get("name") or "") == ENERGY_ITEM_NAME
        )
    )
    if available < 1:
        raise ValueError(
            f"{action_name}检查到{name}体力={current}，"
            f"低于自动加体阈值{normalized_threshold}，"
            f"但宝库没有{ENERGY_ITEM_NAME}"
        )
    payload = build_use_general_item_payload(
        general_id,
        ENERGY_ITEM_ID,
        1,
    )
    return {
        "ready": True,
        "actionRequired": True,
        "generalId": general_id,
        "generalName": name,
        "itemId": ENERGY_ITEM_ID,
        "itemName": ENERGY_ITEM_NAME,
        "itemCount": 1,
        "availableItemCount": available,
        "before": current,
        "expectedAfter": current + ENERGY_ITEM_GAIN,
        "threshold": normalized_threshold,
        "payloadHex": payload.hex(),
    }


def apply_general_energy_receipt(
    plan: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    action_name: str,
) -> dict[str, Any]:
    if not bool(plan.get("actionRequired")):
        return dict(plan)
    if not bool(receipt.get("success")):
        raise ValueError(
            f"{action_name}活血丹使用失败："
            f"{receipt.get('message') or '无提示'}"
        )
    before = int(plan["before"])
    after = int(plan.get("expectedAfter") or before + ENERGY_ITEM_GAIN)
    name = str(plan.get("generalName") or plan.get("generalId") or "未知将领")
    threshold = int(plan["threshold"])
    return {
        **dict(plan),
        "success": True,
        "after": after,
        # The caller that asked for the top-up is part of the fact: the same
        # item is spent by 将领维护 and by every expedition preflight, and the
        # record page has to be able to say which one spent it.
        "actionName": str(action_name),
        "message": (
            f"自动加体完成：{name} 使用{ENERGY_ITEM_NAME}1个，"
            f"体力+{ENERGY_ITEM_GAIN}，由{before}更新为{after}；"
            f"检查来源={action_name}，设定阈值={threshold}"
        ),
        "receipt": dict(receipt),
    }


def plan_generals_full_loyalty(
    generals: Sequence[Mapping[str, Any]],
    *,
    action_name: str,
) -> list[dict[str, Any]]:
    """Build deterministic per-general top-up plans without sending packets."""

    plans = []
    seen = set()
    for index, general in enumerate(generals):
        try:
            general_id = int(general.get("id") or 0)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{action_name}满忠失败：第{index + 1}名将领 ID 无效") from error
        if general_id <= 0 or general_id in seen:
            raise ValueError(f"{action_name}满忠失败：将领 ID 无效或重复")
        seen.add(general_id)
        name = str(general.get("name") or general_id)
        if general.get("loyalty") is None or general.get("loyaltyLimit") is None:
            raise ValueError(
                f"{action_name}满忠失败：{name} 的忠诚度状态不可用，"
                "本轮暂不出征"
            )
        try:
            loyalty = int(general["loyalty"])
            loyalty_limit = int(general["loyaltyLimit"])
        except (TypeError, ValueError) as error:
            raise ValueError(f"{action_name}满忠失败：{name} 的忠诚度无效") from error
        if loyalty_limit <= 0 or loyalty < 0 or loyalty > loyalty_limit:
            raise ValueError(
                f"{action_name}满忠失败：{name} 的忠诚度"
                f"{loyalty}/{loyalty_limit}无效"
            )
        delta = loyalty_limit - loyalty
        row = {
            "sourceIndex": index,
            "generalId": general_id,
            "name": name,
            "loyalty": loyalty,
            "loyaltyLimit": loyalty_limit,
            "delta": delta,
            "skipped": delta == 0,
        }
        if delta:
            row["payloadHex"] = build_add_loyalty_payload(
                general_id,
                delta,
            ).hex()
        plans.append(row)
    return plans


def apply_full_loyalty_receipt(
    plan: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    action_name: str,
) -> dict[str, Any]:
    name = str(plan.get("name") or plan.get("generalId") or "未知将领")
    if bool(plan.get("skipped")):
        return {**dict(plan), "success": True}
    if not bool(receipt.get("success")):
        raise ValueError(
            f"{action_name}满忠失败：{name}；"
            f"{receipt.get('message') or '未收到 0x821f 加忠成功响应'}，"
            "本轮暂不出征"
        )
    general_id = int(plan["generalId"])
    updated = next(
        (
            row for row in receipt.get("generals") or []
            if isinstance(row, Mapping)
            and int(row.get("generalId") or 0) == general_id
        ),
        None,
    )
    if updated is None:
        raise ValueError(
            f"{action_name}满忠失败：{name}；响应未包含该将领，"
            "本轮暂不出征"
        )
    new_loyalty = int(updated.get("loyalty") or 0)
    new_limit = int(updated.get("loyaltyLimit") or plan["loyaltyLimit"])
    if new_loyalty < new_limit:
        raise ValueError(
            f"{action_name}满忠失败：{name} 加忠后仍为 "
            f"{new_loyalty}/{new_limit}，本轮暂不出征"
        )
    return {
        **dict(plan),
        **dict(receipt),
        "success": True,
        "loyalty": new_loyalty,
        "loyaltyLimit": new_limit,
        "name": name,
    }


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
