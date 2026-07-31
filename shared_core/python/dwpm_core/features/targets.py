"""Bandit/mine target parsing, normalization and deterministic filtering."""

from __future__ import annotations

import re
import struct
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from ..contracts import load_behavior_contract
from ..protocol.wire import encode_utf, read_utf


RESOURCE_POINT_NAMES = {
    0x01: "镔铁矿",
    0x02: "水晶矿",
    0x03: "玄铁矿",
    0x05: "牧场",
    0x06: "浆果园",
    0x07: "灵草园",
    0x08: "玉露园",
    0x0A: "银矿",
}
MINE_BUSINESS_IDS = {
    "镔铁矿": 1,
    "水晶矿": 2,
    "玄铁矿": 3,
    "浆果园": 6,
    "灵草园": 7,
    "玉露园": 8,
    "银矿": 10,
    "一级牧场": 11,
    "二级牧场": 12,
    "三级牧场": 13,
}
KIND_MARKERS = {
    "E5B1B1E8B38A": "山贼",
    "E5B1B1E8B4BC": "山贼",
    "E9BB83E5B7BE": "黄巾",
    "E9BB84E5B7BE": "黄巾",
    "E6B8A0E5B885": "渠帅",
    "E6B8A0E5B8A5": "渠帅",
    "E4B8BBE5B086": "主将",
    "E4B8BBE5B087": "主将",
    "E4B8BBE5B885": "主帅",
    "E4B8BBE5B8A5": "主帅",
}

MAP_SEARCH_CONTRACT = load_behavior_contract()["mapSearch"]
WORLD_CONTRACT = MAP_SEARCH_CONTRACT["world"]
WORLD_X_MIN = int(WORLD_CONTRACT["xMin"])
WORLD_X_MAX = int(WORLD_CONTRACT["xMax"])
WORLD_Y_MIN = int(WORLD_CONTRACT["yMin"])
WORLD_Y_MAX = int(WORLD_CONTRACT["yMax"])
WORLD_STEP = int(WORLD_CONTRACT["step"])
FULL_SCAN_LIMIT = int(MAP_SEARCH_CONTRACT["fullRequestLimit"])


def action_target_hex(target: Dict[str, Any]) -> str:
    raw = "".join(
        character
        for character in str(target.get("rawRecord") or "")
        if character in "0123456789abcdefABCDEF"
    ).lower()
    if target.get("source") == "8540-structured" and len(raw) >= 16:
        return raw[:16]
    if len(raw) >= 18:
        return raw[:18][-16:]
    return str(
        target.get("idHex") or format(int(target["id"]), "x")
    ).removeprefix("0x").rjust(16, "0")


def action_target_hex_candidates(target: Dict[str, Any]) -> List[Dict[str, str]]:
    raw = "".join(
        character
        for character in str(target.get("rawRecord") or "")
        if character in "0123456789abcdefABCDEF"
    ).lower()
    candidates: List[Dict[str, str]] = []

    def add(label: str, value: str) -> None:
        clean = "".join(
            character
            for character in str(value or "")
            if character in "0123456789abcdefABCDEF"
        ).lower()
        if len(clean) < 16:
            return
        clean = clean[-16:]
        if not any(row["targetHex"] == clean for row in candidates):
            candidates.append({"label": label, "targetHex": clean})

    if len(raw) >= 20:
        add("raw10_tail8_id_plus_utf_len", raw[:20][-16:])
    if target.get("source") == "8540-structured" and len(raw) >= 16:
        add("structured_record_first8_id", raw[:16])
    if len(raw) >= 18:
        add("legacy_first10_tail8", raw[:18][-16:])
    add(
        "id_hex",
        str(target.get("idHex") or format(int(target["id"]), "x"))
        .removeprefix("0x")
        .rjust(16, "0"),
    )
    return candidates


def composition_code(target: Dict[str, Any]) -> str:
    composition = target.get("composition")
    if (
        not isinstance(composition, dict)
        or composition.get("source") != "8540-units"
    ):
        return ""
    return "".join(
        str(int(composition.get(key, 0)))
        for key in ("foot", "bow", "cavalry", "chariot")
    )


def bandit_drop_categories(description: Any) -> List[str]:
    text = str(description or "")
    return [
        category
        for category in ("资源", "宝箱", "装备", "宝物")
        if category in text
    ]


def scan_targets(response_hex: str) -> List[Dict[str, Any]]:
    normalized = "".join(
        character
        for character in response_hex.upper()
        if character in "0123456789ABCDEF"
    )
    output: List[Dict[str, Any]] = []
    for marker, kind in KIND_MARKERS.items():
        start = 0
        while True:
            index = normalized.find(marker, start)
            if index < 0:
                break
            for prefix in (26, 24, 22, 20, 18):
                record_start = index - prefix
                if record_start < 0:
                    continue
                record = normalized[record_start:index + len(marker)]
                if len(record) < 20:
                    continue
                try:
                    id_hex = record[:12]
                    target_id = int(id_hex, 16)
                    match = re.search(r"000A([0-9A-F]{2})" + marker + r"$", record)
                    level = 0
                    if match:
                        value = int(match.group(1), 16)
                        if 48 <= value <= 57:
                            level = value - 48
                    rank = {"渠帅": 11, "主将": 12, "主帅": 13}.get(kind, level)
                    if target_id > 0:
                        output.append(
                            {
                                "id": target_id,
                                "idHex": id_hex.lower(),
                                "kind": kind,
                                "name": f"{level}级{kind}" if level else kind,
                                "rank": rank,
                                "level": level,
                                "x": 0,
                                "y": 0,
                                "rawRecord": record,
                                "composition": None,
                                "compositionCode": "",
                                "source": "marker-scan",
                            }
                        )
                        break
                except Exception:
                    pass
            start = index + len(marker)
    seen = set()
    result = []
    for target in output:
        key = (
            target["id"],
            target["kind"],
            target.get("level"),
            target.get("rawRecord"),
        )
        if key not in seen:
            seen.add(key)
            result.append(target)
    return result


def parse_bandit_targets(payload: bytes) -> List[Dict[str, Any]]:
    targets: List[Dict[str, Any]] = []
    try:
        if len(payload) < 5:
            return []
        map_width = int.from_bytes(payload[0:2], "big")
        map_height = int.from_bytes(payload[2:4], "big")
        count = payload[4]
        position = 5
        for _ in range(count):
            target_id = int.from_bytes(payload[position:position + 8], "big")
            position += 8
            name, position = read_utf(payload, position)
            meta_a = payload[position]
            meta_b = payload[position + 1]
            level_byte = payload[position + 2]
            position += 3
            meta_d = int.from_bytes(payload[position:position + 2], "big")
            position += 2
            meta_e = int.from_bytes(payload[position:position + 2], "big")
            position += 2
            resource, position = read_utf(payload, position)
            resource_1 = int.from_bytes(
                payload[position:position + 4], "big", signed=True
            )
            position += 4
            resource_2 = int.from_bytes(
                payload[position:position + 4], "big", signed=True
            )
            position += 4
            loot_count = payload[position]
            position += 1
            loot_ids = []
            for _loot_index in range(loot_count):
                loot_ids.append(
                    int.from_bytes(payload[position:position + 4], "big")
                )
                position += 4
            unit_count = payload[position]
            position += 1
            composition = {
                "foot": 0,
                "bow": 0,
                "cavalry": 0,
                "chariot": 0,
                "source": "8540-units",
            }
            units = []
            major_keys = {0: "foot", 1: "bow", 2: "cavalry", 4: "chariot"}
            for _unit_index in range(unit_count):
                general_name, position = read_utf(payload, position)
                unit_a = int.from_bytes(payload[position:position + 2], "big")
                position += 2
                unit_uid = int.from_bytes(payload[position:position + 2], "big")
                position += 2
                unit_b = payload[position]
                major_code = payload[position + 1]
                soldier_code = payload[position + 2]
                position += 3
                soldier_count = int.from_bytes(
                    payload[position:position + 4], "big", signed=True
                )
                position += 4
                major_key = major_keys.get(major_code)
                if major_key is None:
                    raise ValueError(f"未知山贼兵种大类码 {major_code}")
                composition[major_key] += 1
                units.append(
                    {
                        "generalName": general_name,
                        "a": unit_a,
                        "uid": unit_uid,
                        "b": unit_b,
                        "majorCode": major_code,
                        "soldierTypeCode": soldier_code,
                        "soldierCount": soldier_count,
                    }
                )
            match = re.search(r"(\d+)级", name)
            level = int(match.group(1)) if match else int(level_byte)
            kind = (
                "山贼"
                if "山贼" in name or "山賊" in name
                else ("黄巾" if "黄巾" in name or "黃巾" in name else name)
            )
            raw_record = f"{target_id:016X}" + encode_utf(name).hex().upper()
            targets.append(
                {
                    "id": target_id,
                    "idHex": f"{target_id:012x}",
                    "kind": kind,
                    "name": name,
                    "level": level,
                    "x": meta_d,
                    "y": meta_e,
                    "rank": level,
                    "resource": resource,
                    "resource1": resource_1,
                    "resource2": resource_2,
                    "rawRecord": raw_record,
                    "lootIds": loot_ids,
                    "dropCategories": bandit_drop_categories(resource),
                    "units": units,
                    "meta": {
                        "mapWidth": map_width,
                        "mapHeight": map_height,
                        "a": meta_a,
                        "b": meta_b,
                        "levelByte": level_byte,
                        "d": meta_d,
                        "e": meta_e,
                    },
                    "composition": composition,
                    "compositionCode": "".join(
                        str(composition[key])
                        for key in ("foot", "bow", "cavalry", "chariot")
                    ),
                    "source": "8540-structured",
                }
            )
            if position >= len(payload):
                break
    except Exception:
        targets = []
    return targets or scan_targets(payload.hex())


def parse_mine_resources(payload: bytes) -> List[Dict[str, Any]]:
    position = 0

    def need(size: int, field: str) -> None:
        if position + size > len(payload):
            raise ValueError(
                f"0x8542 truncated at {field}: pos={position} "
                f"need={size} size={len(payload)}"
            )

    def u8(field: str) -> int:
        nonlocal position
        need(1, field)
        value = payload[position]
        position += 1
        return value

    def u16(field: str) -> int:
        nonlocal position
        need(2, field)
        value = struct.unpack(">H", payload[position:position + 2])[0]
        position += 2
        return value

    def i32(field: str) -> int:
        nonlocal position
        need(4, field)
        value = struct.unpack(">i", payload[position:position + 4])[0]
        position += 4
        return value

    def i64(field: str) -> int:
        nonlocal position
        need(8, field)
        value = struct.unpack(">q", payload[position:position + 8])[0]
        position += 8
        return value

    def text(field: str) -> str:
        nonlocal position
        need(2, field)
        length = struct.unpack(">H", payload[position:position + 2])[0]
        position += 2
        need(length, field)
        value = payload[position:position + length].decode(
            "utf-8", errors="replace"
        )
        position += length
        return value

    if len(payload) < 5:
        raise ValueError(f"0x8542 response too short: {len(payload)}")
    center_x = u16("centerX")
    center_y = u16("centerY")
    count = u8("resourceCount")
    resources: List[Dict[str, Any]] = []
    for index in range(count):
        start = position
        resource_id = i64(f"resource[{index}].id")
        type_code = u8(f"resource[{index}].type")
        level = u8(f"resource[{index}].level")
        x = u16(f"resource[{index}].x")
        y = u16(f"resource[{index}].y")
        detail_flag = u8(f"resource[{index}].detailFlag")
        detail: Dict[str, Any] = {
            "flag": detail_flag,
            "ownerName": "",
            "ownerCountry": "",
            "text1": "",
            "text2": "",
            "amountA": None,
            "amountB": None,
            "description": "",
            "valueJ": None,
            "valueK": None,
        }
        if detail_flag == 0:
            owner_name = text(f"resource[{index}].ownerName")
            owner_country = text(f"resource[{index}].ownerCountry")
            detail.update(
                {
                    "ownerName": owner_name,
                    "ownerCountry": owner_country,
                    "text1": owner_name,
                    "text2": owner_country,
                }
            )
        detail.update(
            {
                "amountA": i32(f"resource[{index}].amountA"),
                "amountB": i32(f"resource[{index}].amountB"),
                "description": text(f"resource[{index}].description"),
                "valueJ": i32(f"resource[{index}].valueJ"),
                "valueK": i32(f"resource[{index}].valueK"),
            }
        )
        troop_groups = []
        for troop_index in range(u8(f"resource[{index}].troopGroupCount")):
            troop_groups.append(
                {
                    "typeCode": u8(
                        f"resource[{index}].troops[{troop_index}].type"
                    ),
                    "count": u16(
                        f"resource[{index}].troops[{troop_index}].count"
                    ),
                    "levelOrStatus": u8(
                        f"resource[{index}].troops[{troop_index}].levelOrStatus"
                    ),
                }
            )
        defenders = []
        for defender_index in range(u8(f"resource[{index}].defenderCount")):
            defenders.append(
                {
                    "generalName": text(
                        f"resource[{index}].defenders[{defender_index}].name"
                    ),
                    "fieldS": u16(
                        f"resource[{index}].defenders[{defender_index}].fieldS"
                    ),
                    "fieldR": u16(
                        f"resource[{index}].defenders[{defender_index}].fieldR"
                    ),
                    "fieldT": u8(
                        f"resource[{index}].defenders[{defender_index}].fieldT"
                    ),
                    "troopTypeCode": u8(
                        f"resource[{index}].defenders[{defender_index}].troopType"
                    ),
                    "generalLevelOrStatus": u8(
                        f"resource[{index}].defenders[{defender_index}].generalLevelOrStatus"
                    ),
                    "troopCount": i32(
                        f"resource[{index}].defenders[{defender_index}].troopCount"
                    ),
                }
            )
        protocol_name = RESOURCE_POINT_NAMES.get(type_code, f"资源点{type_code}")
        kind = (
            {1: "一级牧场", 2: "二级牧场", 3: "三级牧场"}.get(
                level, f"{level}级牧场"
            )
            if type_code == 0x05
            else protocol_name
        )
        owner_name = str(detail.get("ownerName") or "").strip()
        owner_country = str(detail.get("ownerCountry") or "").strip()
        player_occupied = bool(owner_name or owner_country)
        resources.append(
            {
                "id": resource_id,
                "idHex": f"{resource_id & 0xffffffffffffffff:016x}",
                "kind": kind,
                "protocolKind": protocol_name,
                "name": kind if type_code == 0x05 else f"{level}级{kind}",
                "typeCode": type_code,
                "businessId": MINE_BUSINESS_IDS.get(kind),
                "level": level,
                "rank": level,
                "x": x,
                "y": y,
                "detailFlag": detail_flag,
                "detail": detail,
                "ownerName": owner_name,
                "ownerCountry": owner_country,
                "playerOccupied": player_occupied,
                "unoccupiedByPlayer": not player_occupied,
                "troopGroups": troop_groups,
                "defenders": defenders,
                "defenderCount": len(defenders),
                "hasDefenders": bool(defenders),
                "isEmpty": not player_occupied,
                "occupied": player_occupied,
                "amountA": detail.get("amountA"),
                "amountB": detail.get("amountB"),
                "storage": detail.get("amountA"),
                "productionPerHour": detail.get("amountB"),
                "description": detail.get("description"),
                "valueJ": detail.get("valueJ"),
                "valueK": detail.get("valueK"),
                "rawRecord": payload[start:position].hex(),
                "source": "8542-structured",
                "meta": {
                    "centerX": center_x,
                    "centerY": center_y,
                    "recordIndex": index,
                },
            }
        )
    if position != len(payload):
        for resource in resources:
            resource.setdefault("meta", {})["trailingHex"] = payload[position:].hex()
    return resources


def match_composition(target: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    if not filters:
        return True
    composition = target.get("composition") or {}
    if composition.get("source") != "8540-units":
        return False
    foot = int(composition.get("foot", 0))
    bow = int(composition.get("bow", 0))
    cavalry = int(composition.get("cavalry", 0))
    chariot = int(composition.get("chariot", 0))
    max_foot = int(filters.get("maxFoot", 9))
    max_bow = int(filters.get("maxBow", 9))
    max_cavalry = int(filters.get("maxCavalry", 9))
    max_chariot = int(filters.get("maxChariot", 9))
    if bool(filters.get("requireFoot", False)) and foot <= 0:
        return False
    return (
        foot <= max_foot
        and bow <= max_bow
        and cavalry <= max_cavalry
        and chariot <= max_chariot
    )


def normalize_drop_keyword(drop: Any) -> str:
    text = str(drop or "").strip()
    if text in {"宝物", "资源", "装备", "宝箱"}:
        return text
    if text in {"铜钱", "粮食", "粮草", "资源类"}:
        return "资源"
    return ""


def normalize_drop_keywords(drop: Any, drops: Any = None) -> List[str]:
    raw_values: List[Any] = []
    if isinstance(drops, list):
        raw_values.extend(drops)
    elif drops not in (None, ""):
        raw_values.extend(re.split(r"[,，;；|\s]+", str(drops)))
    if isinstance(drop, list):
        raw_values.extend(drop)
    elif drop not in (None, ""):
        raw_values.extend(re.split(r"[,，;；|\s]+", str(drop)))
    if any(str(value).strip() == "不限" for value in raw_values):
        return ["宝物", "资源", "装备", "宝箱"]
    output = []
    for item in raw_values:
        keyword = normalize_drop_keyword(item)
        if keyword and keyword not in output:
            output.append(keyword)
    return output


def parse_composition_code(code: str) -> Dict[str, int] | None:
    digits = "".join(
        character for character in str(code or "") if character.isdigit()
    )
    if len(digits) != 4:
        return None
    return {
        "maxFoot": int(digits[0]),
        "maxBow": int(digits[1]),
        "maxCavalry": int(digits[2]),
        "maxChariot": int(digits[3]),
    }


def match_drop(target: Dict[str, Any], drop: Any) -> bool:
    keywords = normalize_drop_keywords(drop)
    if not keywords:
        return True
    if set(keywords) == {"宝物", "资源", "装备", "宝箱"}:
        return True
    haystack = " ".join(
        str(value or "")
        for value in [
            target.get("resource"),
            target.get("reward"),
            target.get("drop"),
            target.get("name"),
            target.get("rawRecord"),
        ]
    )
    return any(keyword in haystack for keyword in keywords)


def mine_target_matches(
    target: Dict[str, Any],
    *,
    resource_types: Optional[List[str]] = None,
    levels: Optional[List[int]] = None,
    only_empty: bool = False,
    only_defended: bool = False,
    allow_player_occupied: bool = False,
    exact_x: Optional[int] = None,
    exact_y: Optional[int] = None,
) -> bool:
    type_names = {
        str(value or "").strip()
        for value in resource_types or []
        if str(value or "").strip() and str(value or "").strip() != "请选择"
    }
    level_values = {int(value) for value in levels or []}
    if type_names and str(target.get("kind") or "") not in type_names:
        return False
    if level_values and int(target.get("level") or 0) not in level_values:
        return False
    player_occupied = bool(
        target.get("playerOccupied")
        if target.get("playerOccupied") is not None
        else target.get("occupied")
    )
    if player_occupied and not allow_player_occupied:
        return False
    if only_empty and player_occupied:
        return False
    if only_defended and int(target.get("defenderCount") or 0) <= 0:
        return False
    if exact_x is not None and int(target.get("x") or 0) != int(exact_x):
        return False
    if exact_y is not None and int(target.get("y") or 0) != int(exact_y):
        return False
    return True


def brush_scan_coordinates(
    center_x: int,
    center_y: int,
    limit: int,
) -> List[Tuple[int, int]]:
    normalized_x = max(WORLD_X_MIN, min(int(center_x), WORLD_X_MAX))
    normalized_y = max(WORLD_Y_MIN, min(int(center_y), WORLD_Y_MAX))
    max_count = max(1, min(int(limit), FULL_SCAN_LIMIT))
    coordinates = [
        (x, y)
        for x in range(WORLD_X_MIN, WORLD_X_MAX + 1, WORLD_STEP)
        for y in range(WORLD_Y_MIN, WORLD_Y_MAX + 1, WORLD_STEP)
    ]
    coordinates.sort(
        key=lambda point: (
            (point[0] - normalized_x) ** 2 + (point[1] - normalized_y) ** 2,
            abs(point[0] - normalized_x) + abs(point[1] - normalized_y),
            point[0],
            point[1],
        )
    )
    return coordinates[:max_count]


def target_distance_squared(
    target: Dict[str, Any],
    center_x: int,
    center_y: int,
) -> int:
    try:
        target_x = int(target.get("x"))
        target_y = int(target.get("y"))
    except (TypeError, ValueError):
        return 10 ** 9
    return (target_x - center_x) ** 2 + (target_y - center_y) ** 2


def normalize_brush_levels(levels: Any = None, level: Any = None) -> List[int]:
    if isinstance(levels, (list, tuple, set)):
        raw_values = list(levels)
    elif levels not in (None, ""):
        raw_values = re.split(r"[,，;；|\s]+", str(levels))
    else:
        raw_values = []
    if not raw_values and level not in (None, ""):
        raw_values = [level]
    normalized = []
    for value in raw_values:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= parsed <= 10 and parsed not in normalized:
            normalized.append(parsed)
    return sorted(normalized)


def target_matches_search_filter(
    target: Dict[str, Any],
    target_kind: str,
    level: Any,
    drops: List[str],
    composition_filter: Dict[str, Any],
) -> bool:
    levels = normalize_brush_levels(
        level if isinstance(level, (list, tuple, set)) else None,
        None if isinstance(level, (list, tuple, set)) else level,
    )
    try:
        target_level = int(target.get("level") or 0)
    except (TypeError, ValueError):
        target_level = 0
    return (
        target_kind in str(target.get("kind", ""))
        and (not levels or target_level in levels)
        and match_drop(target, drops)
        and match_composition(target, composition_filter)
    )


def dedupe_targets(targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique = []
    seen: Set[Tuple[Any, ...]] = set()
    for target in targets:
        target_id = str(target.get("id") or target.get("idHex") or "")
        key = (
            ("id", target_id)
            if target_id
            else (
                "coord",
                target.get("x"),
                target.get("y"),
                target.get("kind"),
                target.get("level"),
            )
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(target)
    return unique
