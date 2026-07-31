"""General-record recovery and shared status labels."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .formation import soldier_type_name


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
