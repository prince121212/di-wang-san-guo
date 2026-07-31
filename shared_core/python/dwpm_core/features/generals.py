"""General-record recovery and shared status labels."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..protocol.wire import extract_utf_strings, printable, read_utf
from .formation import SOLDIER_CODE_NAMES, soldier_type_name


OFFICE_NAMES_BY_ID = {
    0x0000: "游民",
    0x0001: "细作",
    0x0100: "国民",
    0x0400: "丞相",
    0x0401: "丞相",
    0x0480: "大都督",
    0x0481: "大都督",
    0x0500: "国王",
}
OFFICE_NAMES_BY_ID.update(
    {0x0200 + index: "侍郎" for index in range(0x19)}
)
OFFICE_NAMES_BY_ID.update(
    {0x0280 + index: "都尉" for index in range(0x19)}
)
OFFICE_NAMES_BY_ID.update(
    {
        0x0300: "兵部尚书",
        0x0301: "吏部尚书",
        0x0302: "民部尚书",
        0x0303: "刑部尚书",
        0x0304: "工部尚书",
        0x0305: "户部尚书",
        0x0306: "礼部尚书",
        0x0307: "学部尚书",
        0x0380: "虎威将军",
        0x0381: "破虏将军",
        0x0382: "奋武将军",
        0x0383: "抚远将军",
        0x0384: "征东将军",
        0x0385: "平西将军",
        0x0386: "镇北将军",
        0x0387: "定南将军",
    }
)


def office_name_from_id(office_id: Any) -> str:
    try:
        normalized = int(office_id) & 0xFFFF
    except (TypeError, ValueError):
        return ""
    return OFFICE_NAMES_BY_ID.get(normalized, "")


def general_status_text_from_code(status_code: Any) -> str:
    if status_code is None or status_code == "":
        return "未知"
    try:
        code = int(status_code)
    except Exception:
        return str(status_code)
    return {
        0: "闲",
        1: "征",
        2: "防",
        3: "俘",
        4: "亡",
        5: "修",
        6: "战",
        7: "招",
        8: "返",
        9: "解雇",
    }.get(code, f"状态{code}")


def recover_generals_from_8004(hexstr: str) -> List[Dict[str, Any]]:
    payload = bytes.fromhex(hexstr)
    candidates: List[Dict[str, Any]] = []
    body_length = 114
    general_energy_wire_max = 0xFFFF
    repeated_id_offset = 0x3A
    profession_offset = 0x03
    growth_offset = 0x06
    level_offset = 0x08
    attack_offset = 0x17
    defense_offset = 0x19
    energy_offset = 0x1B
    energy_limit_offset = 0x1D
    troop_limit_offset = 0x23
    loyalty_offset = 0x27
    loyalty_limit_offset = 0x28
    place_id_offset = 0x32
    hero_status_offset = 0x56
    legacy_status58_offset = 0x58
    troop_entry_length = 21

    def u8(offset: int) -> Optional[int]:
        return payload[offset] if 0 <= offset < len(payload) else None

    def u16(offset: int) -> Optional[int]:
        return (
            int.from_bytes(payload[offset:offset + 2], "big")
            if 0 <= offset <= len(payload) - 2
            else None
        )

    def u32(offset: int) -> Optional[int]:
        return (
            int.from_bytes(payload[offset:offset + 4], "big")
            if 0 <= offset <= len(payload) - 4
            else None
        )

    def i64(offset: int) -> Optional[int]:
        return (
            int.from_bytes(
                payload[offset:offset + 8],
                "big",
                signed=True,
            )
            if 0 <= offset <= len(payload) - 8
            else None
        )

    def profession_label(code: Optional[int]) -> str:
        return {
            0: "步将",
            1: "弓将",
            2: "骑将",
            4: "勇士",
        }.get(code, "" if code is None else f"职业{code}")

    def looks_like_body(body_offset: int, general_id: int) -> bool:
        del general_id
        if body_offset + body_length > len(payload):
            return False
        if (
            payload[body_offset + 112] != 0xFF
            or payload[body_offset + 113] != 0xFF
        ):
            return False
        profession = u8(body_offset + profession_offset)
        growth = u16(body_offset + growth_offset)
        level = u8(body_offset + level_offset)
        energy = u16(body_offset + energy_offset)
        energy_limit = u16(body_offset + energy_limit_offset)
        troop_limit = u32(body_offset + troop_limit_offset)
        loyalty = u8(body_offset + loyalty_offset)
        loyalty_limit = u8(body_offset + loyalty_limit_offset)
        hero_status = u8(body_offset + hero_status_offset)
        legacy_status58 = u8(body_offset + legacy_status58_offset)
        return (
            profession is not None
            and 0 <= profession <= 8
            and growth is not None
            and 1 <= growth <= 200
            and level is not None
            and 1 <= level <= 200
            and energy is not None
            and 0 <= energy <= general_energy_wire_max
            and energy_limit is not None
            and 1 <= energy_limit <= general_energy_wire_max
            and troop_limit is not None
            and 0 <= troop_limit <= 50000
            and loyalty is not None
            and 0 <= loyalty <= 200
            and loyalty_limit is not None
            and 1 <= loyalty_limit <= 200
            and hero_status is not None
            and 0 <= hero_status <= 16
            and legacy_status58 is not None
            and 0 <= legacy_status58 <= 16
        )

    general_name_wire_max = 64
    for position in range(8, len(payload) - 2):
        length = int.from_bytes(payload[position:position + 2], "big")
        if (
            not 1 <= length <= general_name_wire_max
            or position + 2 + length > len(payload)
        ):
            continue
        raw_name = payload[position + 2:position + 2 + length]
        try:
            name = raw_name.decode("utf-8").strip()
        except UnicodeDecodeError:
            continue
        if not name:
            continue
        if any(
            ord(character) < 0x20 or ord(character) == 0x7F
            for character in name
        ):
            continue
        general_id = int.from_bytes(payload[position - 8:position], "big")
        if general_id <= 0:
            continue
        body_offset = position + 2 + length
        item: Dict[str, Any] = {
            "id": general_id,
            "idHex": f"{general_id:016x}",
            "name": name,
            "offset": position,
            "nameUtf8Offset": position,
        }
        if looks_like_body(body_offset, general_id):
            place_id = i64(body_offset + place_id_offset)
            profession = u8(body_offset + profession_offset)
            hero_status = u8(body_offset + hero_status_offset)
            status_text = general_status_text_from_code(hero_status)
            repeated_id = payload[
                body_offset + repeated_id_offset:
                body_offset + repeated_id_offset + 8
            ]
            item.update(
                {
                    "source": "state8004-binary-jiangling",
                    "layout": "i64_id_u16_name_114_body_b6_common_v20260708b",
                    "bodyOffset": body_offset,
                    "repeatedIdHex": repeated_id.hex(),
                    "repeatedIdMatches": repeated_id
                    == general_id.to_bytes(8, "big", signed=False),
                    "status": hero_status,
                    "heroStatusCode": hero_status,
                    "stateCode56": hero_status,
                    "statusText": status_text,
                    "displayStatus": status_text,
                    "busy": False if status_text == "闲" else True,
                    "rawStatus58": u8(body_offset + legacy_status58_offset),
                    "status58": u8(body_offset + legacy_status58_offset),
                    "energyReliable": True,
                    "tili": u16(body_offset + energy_offset),
                    "tiliLimit": u16(body_offset + energy_limit_offset),
                    "level": u8(body_offset + level_offset),
                    "growth": u16(body_offset + growth_offset),
                    "kind": profession_label(profession),
                    "professionCode": profession,
                    "gongji": u16(body_offset + attack_offset),
                    "fangyu": u16(body_offset + defense_offset),
                    "loyalty": u8(body_offset + loyalty_offset),
                    "loyaltyLimit": u8(body_offset + loyalty_limit_offset),
                    "troopLimit": u32(body_offset + troop_limit_offset),
                    "daiBingLimit": u32(body_offset + troop_limit_offset),
                }
            )
            if place_id and place_id > 0:
                item.update(
                    {
                        "placeID": place_id,
                        "fiefId": place_id,
                        "fiefIdHex": f"{place_id:016x}",
                    }
                )
        else:
            item.update(
                {
                    "source": "state8004-binary-name-candidate",
                    "status": (
                        payload[position + 2 + length]
                        if position + 2 + length < len(payload)
                        else None
                    ),
                    "tili": None,
                    "energyReliable": False,
                }
            )
        candidates.append(item)

    by_id: Dict[int, Dict[str, Any]] = {}
    for general in candidates:
        if not 0 < general["id"] <= 0x7FFFFFFFFFFFFFFF:
            continue
        previous = by_id.get(int(general["id"]))
        if previous is None or (
            general.get("source") == "state8004-binary-jiangling"
            and previous.get("source") != "state8004-binary-jiangling"
        ):
            by_id[int(general["id"])] = general
    recovered = list(by_id.values())
    final = [
        general
        for general in recovered
        if general.get("source") == "state8004-binary-jiangling"
    ]
    if not final:
        final = [
            general
            for general in candidates
            if general.get("source") == "state8004-binary-jiangling"
        ]

    ids = {int(general["id"]) for general in final}
    minimum_offset = max(
        (
            int(general.get("bodyOffset", 0)) + body_length
            for general in final
            if general.get("bodyOffset")
        ),
        default=0,
    )
    best: Optional[Tuple[int, List[Dict[str, Any]]]] = None
    for position in range(max(0, minimum_offset), len(payload)):
        count = payload[position]
        if (
            not 1 <= count <= 30
            or position + 1 + count * troop_entry_length > len(payload)
        ):
            continue
        assignments = []
        plausible = True
        for index in range(count):
            offset = position + 1 + index * troop_entry_length
            first_id = i64(offset)
            second_id = i64(offset + 8)
            soldier_type = u8(offset + 16)
            soldier_count = int.from_bytes(
                payload[offset + 17:offset + 21],
                "big",
                signed=True,
            )
            if (
                first_id is None
                or second_id is None
                or soldier_type is None
                or not 0 <= soldier_type <= 32
                or not 0 <= soldier_count <= 500000
            ):
                plausible = False
                break
            assignment_id = (
                second_id
                if second_id in ids
                else first_id
                if first_id in ids
                else None
            )
            if assignment_id is not None:
                assignments.append(
                    {
                        "generalId": assignment_id,
                        "soldierTypeCode": soldier_type,
                        "soldierCount": soldier_count,
                        "s5Offset": position,
                        "s5Count": count,
                    }
                )
        if plausible and assignments:
            score = (
                len(assignments),
                1 if count == len(assignments) else 0,
                -position,
            )
            previous_score = (
                (
                    len(best[1]),
                    1 if count == len(best[1]) else 0,
                    -best[0],
                )
                if best is not None
                else None
            )
            if best is None or score > previous_score:
                best = (position, assignments)
    if best:
        by_general_id = {
            assignment["generalId"]: assignment
            for assignment in best[1]
        }
        for general in final:
            assignment = by_general_id.get(int(general["id"]))
            if assignment:
                general.update(
                    {
                        "soldierTypeCode": assignment["soldierTypeCode"],
                        "soldierType": soldier_type_name(
                            assignment["soldierTypeCode"]
                        ),
                        "soldierCount": assignment["soldierCount"],
                        "currentSoldierCount": assignment["soldierCount"],
                        "s5Offset": assignment["s5Offset"],
                        "s5Count": assignment["s5Count"],
                    }
                )
            else:
                general.update(
                    {
                        "soldierTypeCode": -1,
                        "soldierType": "无配兵",
                        "soldierCount": 0,
                        "currentSoldierCount": 0,
                        "s5Offset": best[0],
                        "s5Count": len(best[1]),
                    }
                )
    return final


def parse_idle_army_from_8004(
    hexstr: str,
    generals: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    del generals
    if not hexstr:
        return []
    try:
        payload = bytes.fromhex(hexstr)
    except Exception:
        return []
    valid_codes = set(SOLDIER_CODE_NAMES.keys())

    def previous_fief_name(position: int) -> str:
        try:
            strings = extract_utf_strings(
                payload[max(0, position - 700):position],
                min_len=2,
                max_len=40,
            )
        except Exception:
            return ""
        for item in reversed(strings):
            text = str(item.get("text") or "")
            if any(token in text for token in ("基地", "封地", "城", "县", "郡")):
                return text
        return ""

    candidates = []
    for marker in range(0, max(0, len(payload) - 3)):
        if payload[marker] != 0x1D:
            continue
        position = marker + 1
        idle_type_count = payload[position]
        position += 1
        if not 0 <= idle_type_count <= 16:
            continue
        idle_rows = []
        valid = True
        for _ in range(idle_type_count):
            if position + 5 > len(payload):
                valid = False
                break
            soldier_type = payload[position]
            amount = int.from_bytes(
                payload[position + 1:position + 5],
                "big",
                signed=True,
            )
            position += 5
            if (
                soldier_type not in valid_codes
                or amount < 0
                or amount > 500000
            ):
                valid = False
                break
            idle_rows.append((soldier_type, amount))
        if not valid or position >= len(payload):
            continue
        wounded_type_count = payload[position]
        position += 1
        if not 0 <= wounded_type_count <= 16:
            continue
        wounded_rows = []
        for _ in range(wounded_type_count):
            if position + 5 > len(payload):
                valid = False
                break
            soldier_type = payload[position]
            amount = int.from_bytes(
                payload[position + 1:position + 5],
                "big",
                signed=True,
            )
            position += 5
            if (
                soldier_type not in valid_codes
                or amount < 0
                or amount > 500000
            ):
                valid = False
                break
            wounded_rows.append((soldier_type, amount))
        if not valid:
            continue
        if not any(value for _, value in idle_rows + wounded_rows):
            continue
        fief_name = previous_fief_name(marker)
        if not fief_name:
            continue
        merged: Dict[int, Dict[str, Any]] = {}
        order = []
        for soldier_type, amount in idle_rows:
            if soldier_type not in merged:
                merged[soldier_type] = {
                    "soldierTypeCode": soldier_type,
                    "soldierType": soldier_type_name(soldier_type),
                    "idleCount": 0,
                    "count": 0,
                    "amount": 0,
                    "woundedCount": 0,
                    "hurtSoldierCount": 0,
                    "fiefName": fief_name,
                    "offset": marker,
                }
                order.append(soldier_type)
            merged[soldier_type]["idleCount"] += amount
            merged[soldier_type]["count"] = merged[soldier_type]["idleCount"]
            merged[soldier_type]["amount"] = merged[soldier_type]["idleCount"]
        for soldier_type, amount in wounded_rows:
            if soldier_type not in merged:
                merged[soldier_type] = {
                    "soldierTypeCode": soldier_type,
                    "soldierType": soldier_type_name(soldier_type),
                    "idleCount": 0,
                    "count": 0,
                    "amount": 0,
                    "woundedCount": 0,
                    "hurtSoldierCount": 0,
                    "fiefName": fief_name,
                    "offset": marker,
                }
                order.append(soldier_type)
            merged[soldier_type]["woundedCount"] += amount
            merged[soldier_type]["hurtSoldierCount"] = merged[soldier_type][
                "woundedCount"
            ]
        rows = [merged[soldier_type] for soldier_type in order]
        score = (
            1 if "基地" in fief_name else 0,
            len(rows),
            sum(
                int(row["idleCount"]) + int(row["woundedCount"])
                for row in rows
            ),
            -marker,
        )
        candidates.append(
            {
                "marker": marker,
                "fiefName": fief_name,
                "rows": rows,
                "score": score,
            }
        )
    if not candidates:
        return []
    output = []
    merged_rows: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for candidate in sorted(
        candidates,
        key=lambda item: int(item.get("marker") or 0),
    ):
        for row in candidate.get("rows") or []:
            key = (
                str(row.get("fiefName") or ""),
                int(row.get("soldierTypeCode") or 0),
            )
            if key not in merged_rows:
                item = dict(row)
                merged_rows[key] = item
                output.append(item)
            else:
                item = merged_rows[key]
                item["idleCount"] = int(item.get("idleCount") or 0) + int(
                    row.get("idleCount") or 0
                )
                item["count"] = item["idleCount"]
                item["amount"] = item["idleCount"]
                item["woundedCount"] = int(
                    item.get("woundedCount") or 0
                ) + int(row.get("woundedCount") or 0)
                item["hurtSoldierCount"] = item["woundedCount"]
    return output


def parse_8004_head(
    payload: bytes,
    source_opcode: str = "0x1016/0x8004",
) -> Dict[str, Any]:
    position = 0

    def i8() -> int:
        nonlocal position
        value = payload[position]
        position += 1
        return value

    def i16() -> int:
        nonlocal position
        value = int.from_bytes(
            payload[position:position + 2],
            "big",
            signed=True,
        )
        position += 2
        return value

    def i32() -> int:
        nonlocal position
        value = int.from_bytes(
            payload[position:position + 4],
            "big",
            signed=True,
        )
        position += 4
        return value

    def i64() -> int:
        nonlocal position
        value = int.from_bytes(
            payload[position:position + 8],
            "big",
            signed=True,
        )
        position += 8
        return value

    def utf_at_cursor() -> str:
        nonlocal position
        value, next_position = read_utf(payload, position)
        position = next_position
        return value

    if len(payload) < 96:
        return {
            "sourceOpcode": source_opcode,
            "payloadByteCount": len(payload),
            "parseError": "0x8004 payload too short",
        }
    try:
        status1 = i8()
        status2 = i8()
        server_time = i64()
        role_id = i64()
        role_name = utf_at_cursor()
        flag_b = i8()
        level = i8()
        copper = i64()
        food = i64()
        field_f = i64()
        flag_g = i8()
        avatar_short_raw = i16()
        flag_x = i8()
        prestige = i64()
        prestige_previous = i64()
        prestige_next = i64()
        skip_long = i64()
        flag_l = i8()
        copper_per_hour = i32()
        food_per_hour = i32()
        battle_merit_candidate = i64()
        field_p = i64()
        population_current = i64()
        population_cap = i64()
        fief_limit = i8()
        general_limit = i8()
        resource_point_current = i8()
        resource_point_cap = i8()
        office_field_flag = None
        office_id_raw = None
        if len(payload) - position >= 3:
            office_field_flag = i8()
            office_id_raw = i16()
        parsed = position
        tail = payload[parsed:]
        return {
            "roleId": role_id,
            "roleName": role_name,
            "level": level,
            "copper": copper,
            "food": food,
            "prestige": prestige,
            "prestigePrevThreshold": prestige_previous,
            "prestigeNextThreshold": prestige_next,
            "copperPerHour": copper_per_hour,
            "foodPerHour": food_per_hour,
            "populationCurrent": population_current,
            "populationCap": population_cap,
            "fiefLimit": fief_limit,
            "generalLimit": general_limit,
            "resourcePointCurrent": resource_point_current,
            "resourcePointCap": resource_point_cap,
            "serverTimeMillis": server_time,
            "status1": status1,
            "status2": status2,
            "flagB": flag_b,
            "fieldF": field_f,
            "flagG": flag_g,
            "officeShortRaw": avatar_short_raw,
            "officeShortUnsigned": avatar_short_raw & 0xFFFF,
            "avatarShortRaw": avatar_short_raw,
            "avatarShortUnsigned": avatar_short_raw & 0xFFFF,
            "officeFieldFlag": office_field_flag,
            "officeId": office_id_raw,
            "officeIdRaw": office_id_raw,
            "officeIdUnsigned": (
                office_id_raw & 0xFFFF
                if office_id_raw is not None
                else None
            ),
            "officeName": office_name_from_id(office_id_raw),
            "flagX": flag_x,
            "skipLong": skip_long,
            "flagL": flag_l,
            "battleMeritCandidate": battle_merit_candidate,
            "fieldP": field_p,
            "sourceOpcode": source_opcode,
            "payloadByteCount": len(payload),
            "parsedHeadByteCount": parsed,
            "tailByteCount": len(tail),
            "tailUtf8Preview": printable(tail, 300),
        }
    except Exception as error:
        return {
            "sourceOpcode": source_opcode,
            "payloadByteCount": len(payload),
            "parseError": str(error),
        }


def parse_a110_general_statuses(
    payload: bytes,
    generals: List[Dict[str, Any]],
) -> Dict[str, Any]:
    body_length = 114
    repeated_id_offset = 0x3A
    hero_status_offset = 0x56
    legacy_status58_offset = 0x58
    status_by_name = {}
    status_by_id = {}
    records = []
    seen = set()

    for general in generals:
        try:
            general_id = int(general.get("id") or 0)
        except Exception:
            continue
        name = str(general.get("name") or "")
        if general_id <= 0 or not name:
            continue
        general_id_bytes = general_id.to_bytes(8, "big", signed=False)
        name_bytes = name.encode("utf-8")
        needle = (
            general_id_bytes
            + len(name_bytes).to_bytes(2, "big")
            + name_bytes
        )
        start = 0
        while True:
            position = payload.find(needle, start)
            if position < 0:
                break
            start = position + 1
            body_offset = position + len(needle)
            if body_offset + body_length > len(payload):
                continue
            body = payload[body_offset:body_offset + body_length]
            if (
                body[
                    repeated_id_offset:repeated_id_offset + 8
                ]
                != general_id_bytes
            ):
                continue
            if body[-2:] != b"\xff\xff":
                continue
            status_code = body[hero_status_offset]
            state = general_status_text_from_code(status_code)
            if general_id in seen:
                continue
            seen.add(general_id)
            status_by_name[name] = state
            status_by_id[str(general_id)] = state
            status_by_id[f"{general_id:016x}"] = state
            records.append(
                {
                    "id": general_id,
                    "idHex": f"{general_id:016x}",
                    "name": name,
                    "state": state,
                    "statusCode": status_code,
                    "heroStatusCode": status_code,
                    "stateCode56": status_code,
                    "rawStatus58": body[legacy_status58_offset],
                    "status58": body[legacy_status58_offset],
                    "busy": False if state == "闲" else True,
                    "recordOffset": position,
                    "bodyOffset": body_offset,
                    "source": "0x3110/0xa110-general-status-code56",
                }
            )
            break
    return {
        "statusByName": status_by_name,
        "statusById": status_by_id,
        "records": records,
    }


def parse_military_intel_from_a110(
    payload: bytes,
    generals: List[Dict[str, Any]],
    *,
    updated_at: Optional[int] = None,
) -> Dict[str, Any]:
    names = [
        str(general.get("name") or "")
        for general in generals
        if general.get("name")
    ]
    events = []
    for item in extract_utf_strings(payload):
        text = str(item["text"])
        if not any(
            token in text
            for token in (
                "【返回】",
                "返回",
                "出征",
                "战斗",
                "攻打",
                "行军",
                "剿灭",
                "胜利",
                "失败",
            )
        ):
            continue
        matched = [name for name in names if name and name in text]
        if not matched and not any(
            token in text for token in ("【返回】", "返回", "剿灭")
        ):
            continue
        state = ""
        if "返回" in text:
            state = "返回"
        elif any(
            token in text
            for token in ("出征", "战斗", "攻打", "行军", "剿灭")
        ):
            state = "征"
        events.append(
            {
                "text": text,
                "offset": item["offset"],
                "state": state,
                "generalNames": matched,
            }
        )
    status = parse_a110_general_statuses(payload, generals)
    output = {
        "sourceOpcode": "0x3110/0xa110",
        "events": events,
        "statusByName": status["statusByName"],
        "statusById": status["statusById"],
        "generalStatusRecords": status["records"],
    }
    if updated_at is not None:
        output["updatedAt"] = int(updated_at)
    return output
