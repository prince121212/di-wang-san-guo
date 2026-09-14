"""0x8104 inventory and equipment parsing."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..protocol.wire import read_utf
from .item_names import ITEM_NAMES_BY_ID as DEFAULT_ITEM_NAMES


EQUIPMENT_QUALITY_NAMES = ("普通", "良好", "优秀", "卓越")

# Compact equipment metadata recovered from the original client. Template ids
# are contiguous (0..160), so the shared core can safely classify equipment on
# both hosts without a desktop-only CSV loader.
_EQUIPMENT_NAMES = (
    "短剑|板斧|铜锤|斩马刀|铁胎弓|亮银枪|精钢剑|赤金斧|混元锤|碧玉刀|流云弓|泼风枪|"
    "避水剑|开山斧|破天锤|鬼头刀|宝雕弓|霸王枪|倚天剑|青釭剑|青龙偃月刀|丈八蛇矛|"
    "雌雄双剑|诸葛扇|古锭刀|方天画戟|七星刀|玄铁双戟|龙胆枪|三尖刀|皮盔|青铜盔|"
    "精铁盔|白银盔|黄金盔|紫金盔|玄武盔|白虎盔|朱雀盔|青龙盔|皮铠|青铜铠|精铁铠|"
    "白银铠|黄金铠|紫金铠|玄武铠|白虎铠|朱雀铠|青龙铠|战马|红鬃马|黄骠马|大宛马|"
    "赤兔|绝影|爪黄飞电|的卢|金蛇剑|灵蟒剑|腾蛇宝剑|金蛇盔|灵蟒盔|腾蛇云盔|灵蟒战甲|"
    "金蛇铠|腾蛇晶甲|金蛇骝|灵蟒骊|腾蛇骏|秣马剑|骏马剑|天马宝剑|真·流云弓|真·霸王枪|"
    "秣马盔|骏马盔|天马云盔|秣马铠|骏马战甲|天马晶甲|秣马骝|骏马骊|天马骏|金羊骝|"
    "灵羊骊|牡羊骏|灵羊盔|牡羊云盔|金羊盔|金羊剑|牡羊宝剑|灵羊剑|金羊铠|灵羊战甲|"
    "牡羊晶甲|万石弓|天子剑|双股剑|金箍棒|冕冠|紧箍咒|龙袍|虎皮裙|龙椅|照夜玉狮子|"
    "里飞沙|筋斗云|宝马|龙泉剑|新亭侯刀|云长锦袍|乌云踏雪|虎头湛金枪|旺财|南蛮战象|"
    "神犬|帝王冕|帝王剑|帝王铠|帝王辇|九齿钉耙|金猪|玄冠|黑衣金甲|快航|乌骓|凤翔盔|"
    "钻金盔|金刚盔|天龙盔|战袍|明光铠|金刚甲|帅袍|天龙铠|皇袍|尊·龙椅|火焰驹|白龙马|"
    "白虎|五彩神牛|钢头盔|笠形盔|凤翅盔|铜弩机|汉剑|长柄刀|环首刀|玄甲|锁子甲|金甲|"
    "尊·皇冠|尊·龙剑|尊·龙袍|尊·天子剑|尊·帝王剑|尊·青龙偃月刀|尊·赤兔|尊·龙冠|尊·皇袍"
).split("|")
_EQUIPMENT_LEVELS = (
    1, 3, 6, 9, 12, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 85, 80,
    95, 95, 80, 90, 80, 95, 85, 90, 90, 85, 10, 22, 34, 46, 58, 70, 80, 85, 90, 95,
    8, 20, 32, 44, 56, 68, 80, 85, 90, 95, 15, 32, 49, 66, 95, 85, 80, 90, 1, 35,
    70, 1, 35, 70, 35, 1, 70, 1, 35, 70, 1, 35, 70, 40, 75, 1, 35, 70, 1, 35,
    70, 1, 35, 70, 1, 35, 70, 35, 70, 1, 1, 70, 35, 1, 35, 70, 99, 99, 95, 85,
    99, 85, 99, 85, 99, 99, 95, 85, 95, 66, 95, 95, 88, 95, 50, 95, 80, 99, 99, 99,
    99, 80, 80, 80, 80, 90, 90, 90, 90, 95, 95, 90, 90, 90, 95, 95, 99, 99, 49, 66,
    70, 70, 44, 56, 70, 60, 65, 70, 75, 46, 58, 70, 99, 99, 99, 99, 99, 99, 99, 99, 99,
)
_EQUIPMENT_TYPES = (
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
    2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 0, 0,
    0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 0, 0, 0, 0, 0, 1, 1, 1, 2, 2,
    2, 3, 3, 3, 3, 3, 3, 1, 1, 1, 0, 0, 0, 2, 2, 2, 0, 0, 0, 0,
    1, 1, 2, 2, 3, 3, 3, 3, 3, 0, 0, 2, 3, 0, 3, 3, 3, 1, 0, 2,
    3, 0, 3, 1, 2, 3, 3, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 3,
    3, 3, 1, 1, 1, 0, 0, 0, 0, 2, 2, 2, 1, 0, 2, 0, 0, 0, 3, 1, 2,
)
_FAMOUS_EQUIPMENT_IDS = frozenset({
    18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
    36, 37, 38, 39, 46, 47, 48, 49, 54, 55, 56, 57,
})
if not (
    len(_EQUIPMENT_NAMES)
    == len(_EQUIPMENT_LEVELS)
    == len(_EQUIPMENT_TYPES)
    == 161
):
    raise RuntimeError("共享装备模板表不完整")
DEFAULT_EQUIPMENT_TEMPLATES = {
    template_id: {
        "templateId": template_id,
        "name": name,
        "level": _EQUIPMENT_LEVELS[template_id],
        "typeCode": _EQUIPMENT_TYPES[template_id],
        "famous": template_id in _FAMOUS_EQUIPMENT_IDS,
        "description": "",
    }
    for template_id, name in enumerate(_EQUIPMENT_NAMES)
}

AUTO_OPEN_ITEM_NAMES = (
    "50两银票",
    "100两银票",
    "300两银票",
    "1000两银票",
    "惊喜宝箱",
    "实木宝箱",
    "青铜宝箱",
    "精铁宝箱",
    "铜钱辎重",
    "粮食辎重",
)

AUTO_OPEN_KEY_REQUIREMENTS = {
    "青铜宝箱": "青铜钥匙",
    "精铁宝箱": "精铁钥匙",
}


def plan_open_one_inventory(
    inventory: Mapping[str, Any],
    item_name: str,
) -> Dict[str, Any]:
    """Validate one manual open against a freshly parsed inventory snapshot."""

    name = str(item_name or "").strip()
    if not name:
        raise ValueError("缺少物品名称")
    if name not in AUTO_OPEN_ITEM_NAMES:
        raise ValueError("该物品不在自动开箱允许范围")
    rows = inventory.get("items")
    if not isinstance(rows, list):
        raise ValueError("背包快照缺少道具列表")
    by_name = {
        str(row.get("name") or "").strip(): row
        for row in rows
        if isinstance(row, Mapping)
        and str(row.get("name") or "").strip()
    }
    item = by_name.get(name)
    try:
        item_id = int((item or {}).get("itemId") or (item or {}).get("id") or 0)
        count = int((item or {}).get("count") or 0)
    except (TypeError, ValueError) as error:
        raise ValueError(f"背包中{name}的数量或 ID 无效") from error
    if item_id <= 0 or count <= 0:
        raise ValueError(f"背包中没有{name}")
    required_key = AUTO_OPEN_KEY_REQUIREMENTS.get(name)
    key_count = 0
    if required_key:
        try:
            key_count = int((by_name.get(required_key) or {}).get("count") or 0)
        except (TypeError, ValueError) as error:
            raise ValueError(f"背包中{required_key}数量无效") from error
        if key_count <= 0:
            raise ValueError(f"缺少{required_key}")
    return {
        "ready": True,
        "itemName": name,
        "itemId": item_id,
        "availableCount": count,
        "openCount": 1,
        "requiredKey": required_key or "",
        "requiredKeyCount": key_count,
    }


def inventory_reward_log_text(message: Any) -> str:
    """Normalize the server's HTML-ish reward text for logs and notifications."""

    text = re.sub(r"(?i)<br\s*/?>", "；", str(message or ""))
    text = re.sub(r"<[^>]+>", "", text)
    return "；".join(
        part.strip()
        for part in re.split(r"[；;]", text)
        if part.strip()
    )


def equipment_quality_codes(
    names: Any,
    quality_names: Sequence[str] = EQUIPMENT_QUALITY_NAMES,
) -> list[int]:
    """Map a user's chosen quality names to codes, in canonical order.

    Unknown names are dropped rather than guessed: a typo must not widen what
    gets thrown away.
    """

    if isinstance(names, str):
        raw = re.split(r"[,，;；|]+", names)
    elif isinstance(names, (list, tuple, set)):
        raw = list(names)
    else:
        raw = []
    wanted = {str(name or "").strip() for name in raw}
    return [
        index
        for index, name in enumerate(quality_names)
        if name in wanted
    ]


def equipment_is_safe_to_discard(
    equipment: Mapping[str, Any],
    *,
    max_quality: int,
    max_level: int,
    allowed_qualities: Optional[Iterable[int]] = None,
    quality_names: Sequence[str] = EQUIPMENT_QUALITY_NAMES,
) -> tuple[bool, str]:
    """Decide whether one treasury equipment row may be discarded.

    Only rows from the treasury reach here, so "未穿戴" holds by construction;
    the remaining guards are 未强化, 未炼魂, not a named general's piece, below
    the level ceiling and of a quality the user actually selected.  When the
    caller passes ``allowed_qualities`` that set is authoritative; the older
    ``max_quality`` ceiling stays for callers that never learned about sets.
    """

    if not bool(equipment.get("equipmentMetadataComplete")):
        return False, "装备元数据不完整"
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
    if quality < 0:
        return False, "品质未知"
    if allowed_qualities is not None:
        allowed = {int(value) for value in allowed_qualities}
        if quality not in allowed:
            label = (
                quality_names[quality]
                if quality < len(quality_names)
                else str(quality)
            )
            return False, f"品质{label}不在丢弃范围"
        return True, ""
    if quality > int(max_quality):
        label = (
            quality_names[int(max_quality)]
            if 0 <= int(max_quality) < len(quality_names)
            else str(max_quality)
        )
        return False, f"品质高于{label}"
    return True, ""


def plan_next_automatic_inventory_action(
    inventory: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    opened_count: int = 0,
    action_count: int = 0,
) -> Dict[str, Any]:
    """Select at most one deterministic, fail-closed inventory mutation."""

    if inventory.get("parseError"):
        raise ValueError(f"背包解析失败：{inventory['parseError']}")
    items = [
        dict(row)
        for row in inventory.get("items") or []
        if isinstance(row, Mapping)
    ]
    equipment_rows = [
        dict(row)
        for row in inventory.get("equipment") or []
        if isinstance(row, Mapping)
    ]
    max_actions = max(
        1,
        min(int(policy.get("maxActionsPerCycle") or 50), 200),
    )
    max_open = max(
        1,
        min(int(policy.get("maxOpenPerCycle") or 50), 200),
    )
    if int(action_count) >= max_actions:
        return {
            "action": None,
            "reason": "action-limit",
            "message": f"本轮已达到{max_actions}项背包动作上限",
        }

    def normalized_names(value: Any) -> list[str]:
        raw = value if isinstance(value, list) else re.split(
            r"[,，;；|]+", str(value or "")
        )
        return list(dict.fromkeys(
            str(name or "").strip()
            for name in raw
            if str(name or "").strip()
        ))

    def item_count(item_id: int) -> int:
        return sum(
            max(0, int(row.get("count") or 0))
            for row in items
            if int(row.get("itemId") or row.get("id") or -1) == item_id
        )

    def name_count(name: str) -> int:
        return sum(
            max(0, int(row.get("count") or 0))
            for row in items
            if str(row.get("name") or "") == name
        )

    auto_names = [
        name
        for name in normalized_names(policy.get("autoOpenItemNames"))
        if name in AUTO_OPEN_ITEM_NAMES
    ] if bool(policy.get("autoOpenEnabled")) else []
    remaining_open = max(0, max_open - max(0, int(opened_count)))
    if remaining_open > 0:
        for name in auto_names:
            row = next((
                current
                for current in items
                if str(current.get("name") or "") == name
                and int(current.get("count") or 0) > 0
                and int(current.get("itemId") or current.get("id") or 0) > 0
            ), None)
            if row is None:
                continue
            item_id = int(row.get("itemId") or row.get("id") or 0)
            available = item_count(item_id)
            required_key = AUTO_OPEN_KEY_REQUIREMENTS.get(name)
            key_count = name_count(required_key) if required_key else available
            requested = min(available, key_count, remaining_open, 0xFFFF)
            if requested <= 0:
                continue
            return {
                "action": {
                    "kind": "open",
                    "itemId": item_id,
                    "itemName": name,
                    "requestedCount": requested,
                    "beforeItemCount": available,
                    "requiredKey": required_key or "",
                    "beforeKeyCount": key_count,
                },
                "reason": "auto-open",
                "message": f"自动开启{name} x{requested}",
            }

    discard_names = set(normalized_names(policy.get("discardItemNames")))
    if bool(policy.get("cleanInventory")) and discard_names:
        for row in items:
            name = str(row.get("name") or "")
            # Opening takes precedence. A selected box without its key is
            # preserved instead of falling through to discard.
            if name not in discard_names or name in auto_names:
                continue
            item_id = int(row.get("itemId") or row.get("id") or 0)
            available = item_count(item_id)
            if item_id <= 0 or available <= 0:
                continue
            return {
                "action": {
                    "kind": "discard-item",
                    "itemId": item_id,
                    "itemName": name,
                    "requestedCount": min(available, 0x7FFFFFFF),
                    "beforeItemCount": available,
                },
                "reason": "discard-item",
                "message": f"丢弃{name} x{available}",
            }

    if bool(policy.get("cleanInventory")) and bool(
        policy.get("discardEquipment")
    ):
        max_quality = int(policy.get("maxEquipmentQualityCode") or 0)
        # A policy that names its qualities is authoritative; the ceiling is
        # only the legacy shape.  An explicitly empty set discards nothing.
        raw_allowed = policy.get("discardEquipmentQualityCodes")
        allowed_qualities: Optional[set[int]] = None
        if isinstance(raw_allowed, (list, tuple, set)):
            allowed_qualities = set()
            for value in raw_allowed:
                try:
                    allowed_qualities.add(int(value))
                except (TypeError, ValueError):
                    continue
        max_level = max(
            1,
            min(int(policy.get("maxEquipmentLevel") or 20), 100),
        )
        incomplete = [
            row
            for row in equipment_rows
            if not bool(row.get("equipmentMetadataComplete"))
        ]
        if incomplete:
            identifiers = ",".join(
                str(
                    row.get("instanceId")
                    or row.get("id")
                    or row.get("templateId")
                    or "unknown"
                )
                for row in incomplete[:5]
            )
            raise ValueError(
                "装备元数据不完整，已禁止自动丢弃"
                + (f"：{identifiers}" if identifiers else "")
            )
        for row in equipment_rows:
            allowed, _reason = equipment_is_safe_to_discard(
                row,
                max_quality=max_quality,
                max_level=max_level,
                allowed_qualities=allowed_qualities,
            )
            if not allowed:
                continue
            instance_id = int(row.get("instanceId") or row.get("id") or 0)
            return {
                "action": {
                    "kind": "discard-equipment",
                    "instanceId": instance_id,
                    "itemName": str(row.get("name") or instance_id),
                    "requestedCount": 1,
                    "beforeItemCount": 1,
                    "level": int(row.get("level") or 0),
                    "quality": int(row.get("quality") or 0),
                    "qualityName": str(row.get("qualityName") or ""),
                },
                "reason": "discard-equipment",
                "message": f"丢弃装备{row.get('name') or instance_id}",
            }
    return {
        "action": None,
        "reason": "no-action",
        "message": "背包当前没有需要处理的物品",
    }


def observe_automatic_inventory_action(
    action: Mapping[str, Any],
    inventory: Mapping[str, Any],
) -> Dict[str, Any]:
    """Prove whether one ledgered inventory mutation changed fresh state."""

    kind = str(action.get("kind") or "")
    if kind == "discard-equipment":
        instance_id = int(action.get("instanceId") or 0)
        present = any(
            int(row.get("instanceId") or row.get("id") or 0) == instance_id
            for row in inventory.get("equipment") or []
            if isinstance(row, Mapping)
        )
        return {
            "applied": not present,
            "consumedCount": 1 if not present else 0,
            "currentCount": 0 if not present else 1,
        }
    item_id = int(action.get("itemId") or 0)
    before = max(0, int(action.get("beforeItemCount") or 0))
    current = sum(
        max(0, int(row.get("count") or 0))
        for row in inventory.get("items") or []
        if isinstance(row, Mapping)
        and int(row.get("itemId") or row.get("id") or -1) == item_id
    )
    consumed = max(0, before - current)
    return {
        "applied": consumed > 0,
        "consumedCount": min(
            consumed,
            max(0, int(action.get("requestedCount") or consumed)),
        ),
        "currentCount": current,
    }


def parse_8104_equipment_records(
    payload: bytes,
    offset: int,
    equipment_templates: Optional[Mapping[int, Mapping[str, Any]]] = None,
    quality_names: Sequence[str] = EQUIPMENT_QUALITY_NAMES,
) -> Tuple[List[Dict[str, Any]], int, str]:
    if offset + 2 > len(payload):
        return [], offset, "缺少装备数量"
    position = offset
    count = int.from_bytes(
        payload[position:position + 2],
        "big",
        signed=False,
    )
    position += 2
    if count > 1000:
        return [], offset, f"装备数量异常：{count}"
    templates = equipment_templates or DEFAULT_EQUIPMENT_TEMPLATES
    equipment = []
    try:
        for index in range(count):
            if position + 11 > len(payload):
                raise ValueError(f"第 {index + 1} 条装备记录不完整")
            record_offset = position
            instance_id = int.from_bytes(
                payload[position:position + 8],
                "big",
                signed=True,
            )
            position += 8
            template_id = int.from_bytes(
                payload[position:position + 2],
                "big",
                signed=False,
            )
            position += 2
            attribute_length = payload[position]
            position += 1
            if (
                attribute_length > 64
                or position + attribute_length + 10 > len(payload)
            ):
                raise ValueError(
                    f"第 {index + 1} 条装备属性长度异常："
                    f"{attribute_length}"
                )
            attributes = list(
                payload[position:position + attribute_length]
            )
            position += attribute_length
            strengthen_effect = int.from_bytes(
                payload[position:position + 2],
                "big",
                signed=False,
            )
            position += 2
            risk0 = payload[position]
            risk1 = payload[position + 1]
            position += 2
            protocol_j = int.from_bytes(
                payload[position:position + 2],
                "big",
                signed=False,
            )
            position += 2
            pity_current = int.from_bytes(
                payload[position:position + 2],
                "big",
                signed=False,
            )
            position += 2
            pity_target = int.from_bytes(
                payload[position:position + 2],
                "big",
                signed=False,
            )
            position += 2
            extra_text, position = read_utf(payload, position)
            template_known = template_id in templates
            template = templates.get(template_id) or {
                "templateId": template_id,
                "name": f"装备#{template_id}",
                "level": 0,
                "typeCode": -1,
                "famous": False,
                "description": "",
            }
            quality = attributes[0] if attributes else -1
            strengthen = attributes[1] if len(attributes) > 1 else 0
            equipment.append(
                {
                    "index": index,
                    "instanceId": instance_id,
                    "id": instance_id,
                    "instanceIdHex": (
                        f"{instance_id:016x}" if instance_id >= 0 else ""
                    ),
                    "templateId": template_id,
                    "name": template["name"],
                    "level": int(template["level"]),
                    "typeCode": int(template["typeCode"]),
                    "famous": bool(template["famous"]),
                    "quality": quality,
                    "qualityName": (
                        quality_names[quality]
                        if 0 <= quality < len(quality_names)
                        else f"品质{quality}"
                    ),
                    "strengthen": strengthen,
                    "attributes": attributes,
                    "strengthenEffect": strengthen_effect,
                    "risk": [risk0, risk1],
                    "protocolJ": protocol_j,
                    "pityCurrent": pity_current,
                    "pityTarget": pity_target,
                    "extraText": extra_text,
                    "templateDescription": template["description"],
                    "templateKnown": template_known,
                    # ``typeCode=0`` is a valid weapon type.  Do not use
                    # ``value or -1`` here: zero is falsy in Python and was
                    # incorrectly treated as missing metadata, which caused
                    # every known weapon to block automatic inventory cleanup.
                    "equipmentMetadataComplete": bool(
                        instance_id > 0
                        and template_known
                        and int(template.get("level") or 0) > 0
                        and template.get("typeCode") is not None
                        and int(template.get("typeCode")) >= 0
                        and 0 <= quality < len(quality_names)
                    ),
                    "offset": record_offset,
                    "rawHex": payload[record_offset:position].hex(),
                }
            )
        return equipment, position, ""
    except Exception as error:
        return equipment, position, str(error)


#: Largest bag the footer may plausibly declare; anything past it is a misread.
_MAX_PLAUSIBLE_BAG_CAPACITY = 4096


def parse_8104_footer(payload: bytes, offset: int) -> Dict[str, Any]:
    """Read the trailer the original client keeps after the equipment bank.

    The client's 0x8104 reader ends with ``readShort`` ×3 and ``readByte``;
    the first short is what its 宝物 screen shows as the bag limit (``ev``,
    "背包上限").  Two real captures from different accounts both end in
    ``0032 01f4 000a 05`` - 50, 500, 10, 5 - and 50 is exactly the limit the
    game displays for them.  The remaining values are kept raw and unnamed
    rather than guessed at.

    ``capacity`` is ``None`` when the trailer is missing or implausible, never
    a number read from somewhere else: an unknown limit is displayable as
    unknown, a wrong one is not.
    """

    tail = payload[offset:]
    values: List[int] = []
    position = 0
    for _ in range(3):
        if position + 2 > len(tail):
            break
        values.append(int.from_bytes(tail[position:position + 2], "big"))
        position += 2
    if position + 1 <= len(tail):
        values.append(tail[position])
    capacity = values[0] if values else None
    if capacity is not None and not 0 < capacity <= _MAX_PLAUSIBLE_BAG_CAPACITY:
        capacity = None
    return {
        "capacity": capacity,
        "values": values,
        "rawHex": tail.hex(),
        "offset": offset,
    }


def parse_8104_inventory(
    payload: bytes,
    source_opcode: str = "0x1104/0x8104",
    *,
    item_names: Optional[Mapping[int, str]] = None,
    equipment_templates: Optional[Mapping[int, Mapping[str, Any]]] = None,
    quality_names: Sequence[str] = EQUIPMENT_QUALITY_NAMES,
) -> Dict[str, Any]:
    if len(payload) < 18:
        return {
            "sourceOpcode": source_opcode,
            "items": [],
            "parseError": f"0x8104 payload too short: {len(payload)}",
        }
    # The original client opens this packet with readLong, readLong, readShort:
    # two account-wide asset counters and then the stack count.  Bytes 14..16
    # are therefore the low half of the second long, and reading them as the
    # bag limit gave 1863 / 1386 / 1150 on three live accounts whose limit is
    # 50.  The limit lives in the trailer; see :func:`parse_8104_footer`.
    header_long1 = int.from_bytes(payload[0:8], "big", signed=False)
    header_long2 = int.from_bytes(payload[8:16], "big", signed=False)
    item_count = int.from_bytes(payload[16:18], "big", signed=False)
    names = dict(item_names or DEFAULT_ITEM_NAMES)
    items = []
    seen = set()

    def add_item(
        item_id: int,
        count: int,
        offset: int,
        layout: str,
        raw_length: int = 16,
        *,
        require_known: bool = False,
        allow_zero: bool = True,
    ) -> None:
        if (
            item_id < 0
            or item_id > 0xFFFF
            or count <= 0
            or count > 500000
            or (require_known and item_id not in names)
            or (not allow_zero and item_id == 0)
        ):
            return
        key = (item_id, offset)
        if key in seen:
            return
        seen.add(key)
        items.append(
            {
                "index": len(items),
                "itemId": item_id,
                "id": item_id,
                "name": names.get(item_id, f"道具#{item_id}"),
                "count": count,
                "offset": offset,
                "layout": layout,
                "rawHex": payload[
                    offset:min(offset + raw_length, len(payload))
                ].hex(),
                "source": source_opcode,
            }
        )

    table_offset = 18
    table_length = item_count * 12
    if item_count > 0 and table_offset + table_length <= len(payload):
        fixed_rows = []
        fixed_valid = True
        # Each row is u16 id, u16 count, then a per-stack long the original
        # client reads as data (an expiry / unique id).  It is usually zero, so
        # an earlier version of this parser required it to be - and any account
        # holding one item that carried a value fell out of this branch into
        # the scan fallback, which reports no equipment and no bag limit at
        # all.  The row's own shape cannot prove the layout; what proves it is
        # that the equipment bank and its trailer line up immediately after
        # the table, so that is checked below instead.
        for index in range(item_count):
            offset = table_offset + index * 12
            item_id = int.from_bytes(
                payload[offset:offset + 2],
                "big",
                signed=False,
            )
            count = int.from_bytes(
                payload[offset + 2:offset + 4],
                "big",
                signed=False,
            )
            if count <= 0 or count > 500000:
                fixed_valid = False
                break
            fixed_rows.append((offset, item_id, count))
        equipment_table_offset = table_offset + table_length
        equipment, v5_end, equipment_error = (
            parse_8104_equipment_records(
                payload,
                equipment_table_offset,
                equipment_templates,
                quality_names,
            )
            if fixed_valid
            else ([], equipment_table_offset, "跳过：道具表未通过校验")
        )
        if fixed_valid and equipment_error:
            # The equipment bank did not line up.  Accept the table anyway
            # only when every per-stack long is zero, which is the corroborating
            # evidence the old check relied on; otherwise this is not the
            # layout we think it is and the scan fallback is the honest answer.
            fixed_valid = all(
                payload[offset + 4:offset + 12] == b"\x00" * 8
                for offset, _item_id, _count in fixed_rows
            )
        if fixed_valid and (fixed_rows or item_count == 0):
            for offset, item_id, count in fixed_rows:
                add_item(
                    item_id,
                    count,
                    offset,
                    "u16-id-u16-count-reserved8",
                    12,
                )
            # The server sends the two counts that make up bag occupancy - the
            # stack count in the header and the equipment count that opens the
            # equipment bank - but never their sum; the game client adds them
            # for its "49/50".  Sum the declared counts, not the rows we
            # happened to decode, so a template we cannot name still counts
            # as the slot it occupies.
            declared_equipment_count = (
                int.from_bytes(
                    payload[equipment_table_offset:equipment_table_offset + 2],
                    "big",
                    signed=False,
                )
                if equipment_table_offset + 2 <= len(payload)
                else len(equipment)
            )
            slots_used = item_count + declared_equipment_count
            # A trailer read from the wrong offset is worse than no trailer:
            # only trust it once every equipment record parsed cleanly.
            footer = (
                parse_8104_footer(payload, v5_end)
                if not equipment_error
                else {"capacity": None, "values": [], "rawHex": "", "offset": v5_end}
            )
            capacity = footer["capacity"]
            parsed: Dict[str, Any] = {
                "sourceOpcode": source_opcode,
                "capacity": capacity,
                "slotsUsed": slots_used,
                "slotsFree": (
                    max(0, int(capacity) - slots_used)
                    if capacity is not None
                    else None
                ),
                "headerLong1": header_long1,
                "headerLong2": header_long2,
                "itemCount": item_count,
                "items": items,
                "equipmentCount": len(equipment),
                "declaredEquipmentCount": declared_equipment_count,
                "equipment": equipment,
                "footer": footer,
                "payloadByteCount": len(payload),
                "parsedItemCount": len(items),
                "dictionarySize": len(names),
                "layout": "u16-id-u16-count-reserved8-table",
                "v5EndOffset": v5_end,
            }
            unknown_item_ids = sorted({
                item_id
                for _, item_id, _ in fixed_rows
                if item_id not in names
            })
            if unknown_item_ids:
                parsed["unknownItemIds"] = unknown_item_ids
            if equipment_error:
                parsed["equipmentParseError"] = equipment_error
            return parsed

    first_offset = 18
    if first_offset + 16 <= len(payload):
        item_id = int.from_bytes(
            payload[first_offset:first_offset + 4],
            "big",
            signed=False,
        )
        count_a = int.from_bytes(
            payload[first_offset + 12:first_offset + 14],
            "big",
            signed=False,
        )
        count_b = int.from_bytes(
            payload[first_offset + 14:first_offset + 16],
            "big",
            signed=False,
        )
        add_item(
            item_id,
            count_b or count_a,
            first_offset,
            "int-id-reserved-count-slot",
            16,
            require_known=True,
        )

    for offset in range(18, max(18, len(payload) - 3)):
        if first_offset <= offset < first_offset + 16:
            continue
        item_id = int.from_bytes(
            payload[offset:offset + 2],
            "big",
            signed=False,
        )
        count = int.from_bytes(
            payload[offset + 2:offset + 4],
            "big",
            signed=False,
        )
        if item_id == 0 or item_id not in names or count <= 0:
            continue
        prefix8 = payload[max(18, offset - 8):offset]
        prefix6 = payload[max(18, offset - 6):offset]
        if prefix8 == b"\x00" * 8 or prefix6 == b"\x00" * 6:
            if offset == first_offset + 2:
                continue
            add_item(
                item_id,
                count,
                offset,
                "zero-prefix-u16-id-u16-count",
                12,
                require_known=True,
                allow_zero=False,
            )
        if len(items) >= item_count:
            break
    # The scan fallback cannot locate the equipment bank, so it cannot reach
    # the trailer either; the limit and the occupancy are simply unknown here.
    parsed = {
        "sourceOpcode": source_opcode,
        "capacity": None,
        "slotsUsed": None,
        "slotsFree": None,
        "headerLong1": header_long1,
        "headerLong2": header_long2,
        "itemCount": item_count,
        "items": items,
        "equipmentCount": 0,
        "equipment": [],
        "payloadByteCount": len(payload),
        "parsedItemCount": len(items),
        "dictionarySize": len(names),
        "layout": "legacy-scan-fallback",
    }
    if len(items) != item_count:
        parsed["parseError"] = (
            f"0x8104 道具表结构不匹配：声明 {item_count} 条，"
            f"安全解析 {len(items)} 条"
        )
    return parsed
