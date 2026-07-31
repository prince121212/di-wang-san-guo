"""0x8104 inventory and equipment parsing."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..protocol.wire import read_utf


DEFAULT_ITEM_NAMES = {
    0: "徭役令",
    1: "屯田令",
    2: "高级屯田令",
    3: "镔铁",
    4: "山贼头巾",
    5: "旌旗",
    6: "迁封令",
    9: "传音符",
    12: "活血丹",
    16: "兵书",
    20: "招贤令",
    22: "鲁公手册",
    36: "新手礼包",
    37: "新手礼包2",
    38: "新手礼包3",
    40: "新手礼包4",
    41: "新手礼包5",
    42: "新手礼包6",
    43: "新手礼包7",
    44: "新手礼包8",
    45: "新手礼包9",
    46: "新手礼包10",
    64: "战鼓",
    66: "八阵图",
    76: "初级行军符",
    77: "中级行军符",
    78: "高级行军符",
    79: "特级行军符",
    199: "水晶大材料包",
}
EQUIPMENT_QUALITY_NAMES = ("普通", "良好", "优秀", "卓越")


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
    templates = equipment_templates or {}
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
                    "offset": record_offset,
                    "rawHex": payload[record_offset:position].hex(),
                }
            )
        return equipment, position, ""
    except Exception as error:
        return equipment, position, str(error)


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
    capacity = int.from_bytes(payload[14:16], "big", signed=False)
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
    ) -> None:
        if item_id not in names or count <= 0 or count > 500000:
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
            reserved = payload[offset + 4:offset + 12]
            if (
                item_id not in names
                or count <= 0
                or count > 500000
                or reserved != b"\x00" * 8
            ):
                fixed_valid = False
                break
            fixed_rows.append((offset, item_id, count))
        if fixed_valid and (fixed_rows or item_count == 0):
            for offset, item_id, count in fixed_rows:
                add_item(
                    item_id,
                    count,
                    offset,
                    "u16-id-u16-count-reserved8",
                    12,
                )
            equipment, v5_end, equipment_error = (
                parse_8104_equipment_records(
                    payload,
                    table_offset + table_length,
                    equipment_templates,
                    quality_names,
                )
            )
            parsed: Dict[str, Any] = {
                "sourceOpcode": source_opcode,
                "capacity": capacity,
                "itemCount": item_count,
                "items": items,
                "equipmentCount": len(equipment),
                "equipment": equipment,
                "payloadByteCount": len(payload),
                "parsedItemCount": len(items),
                "dictionarySize": len(names),
                "layout": "u16-id-u16-count-reserved8-table",
                "v5EndOffset": v5_end,
            }
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
        if item_id not in names or count <= 0:
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
            )
        if len(items) >= item_count:
            break
    return {
        "sourceOpcode": source_opcode,
        "capacity": capacity,
        "itemCount": item_count,
        "items": items,
        "payloadByteCount": len(payload),
        "parsedItemCount": len(items),
        "dictionarySize": len(names),
    }
