"""0x1600/0x8600 military-intelligence protocol parsing."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from ..contracts import load_behavior_contract
from ..protocol.wire import extract_utf_strings, read_utf
from .generals import general_status_text_from_code, recover_generals_from_8004


MILITARY_CONTRACT = load_behavior_contract()["militarySnapshot"]
MILITARY_INTEL_REQUEST_PAYLOAD = bytes.fromhex(
    str(MILITARY_CONTRACT["requestPayloadHex"])
)
MILITARY_ACTION_TARGET_TYPES = {
    0x01: "封地",
    0x02: "野外目标",
    0x03: "山贼",
    0x0E: "副本关卡",
}
MILITARY_ACTION_STATE_BY_TAG = {
    "攻占": "战斗",
    "夺取": "战斗",
    "掠夺": "战斗",
    "消灭": "战斗",
    "驻守": "驻守",
    "返回": "返回",
}
MILITARY_INCOMING_ACTION_TYPES = {0x01: ("掠夺", "夺取")}
MILITARY_8600_MAX_SECTION_ITEMS = 512
MILITARY_8600_JIANGLING_BODY_LEN = 114
MILITARY_8600_S5_ENTRY_LEN = 21
MILITARY_8600_ENERGY_OFFSET = 0x1B
MILITARY_8600_ENERGY_LIMIT_OFFSET = 0x1D
MILITARY_8600_TROOP_LIMIT_OFFSET = 0x23
MILITARY_8600_LOYALTY_OFFSET = 0x27
MILITARY_8600_PLACE_ID_OFFSET = 0x32
MILITARY_8600_STATUS_OFFSET = 0x56
MILITARY_MARCH_KINDS = {
    0x09: "去程",
    0x0B: "去程",
    0x0D: "回程",
    0x17: "副本",
}
MILITARY_OUTBOUND_MARCH_KINDS = {0x09, 0x0B}
MILITARY_BATTLE_IN_PROGRESS_MARKER = "战斗进行中"
MILITARY_TIMESTAMP_MIN_MS = 1_600_000_000_000
MILITARY_TIMESTAMP_MAX_MS = 2_000_000_000_000


def parse_8600_military_events(payload: bytes) -> List[Dict[str, Any]]:
    events = []
    for field in extract_utf_strings(payload, max_len=600):
        text = str(field.get("text") or "")
        if "【驻守】" not in text and "驻守在" not in text:
            continue
        position = int(field["offset"]) + 2 + int(field["length"])
        if position + 15 > len(payload):
            continue
        state16 = int.from_bytes(payload[position:position + 2], "big")
        position += 2
        state32 = int.from_bytes(payload[position:position + 4], "big")
        position += 4
        battle_id = int.from_bytes(payload[position:position + 8], "big")
        position += 8
        general_count = payload[position]
        position += 1
        if (
            not 1 <= general_count <= 32
            or position + general_count * 9 + 11 > len(payload)
        ):
            continue
        general_ids = []
        general_flags = []
        for _index in range(general_count):
            general_ids.append(
                int.from_bytes(payload[position:position + 8], "big")
            )
            position += 8
            general_flags.append(payload[position])
            position += 1
        target_id = int.from_bytes(payload[position:position + 8], "big")
        position += 8
        target_type = payload[position]
        position += 1
        try:
            target_name, position = read_utf(payload, position)
        except Exception:
            continue
        if position + 4 > len(payload):
            continue
        x = int.from_bytes(payload[position:position + 2], "big")
        y = int.from_bytes(payload[position + 2:position + 4], "big")
        if battle_id <= 0 or target_id <= 0 or not target_name:
            continue
        events.append(
            {
                "text": text,
                "offset": field["offset"],
                "state16": state16,
                "state32": state32,
                "battleId": battle_id,
                "generalIds": general_ids,
                "generalIdHexes": [
                    f"{general_id:016x}" for general_id in general_ids
                ],
                "generalFlags": general_flags,
                "targetId": target_id,
                "targetIdHex": f"{target_id:016x}",
                "targetType": target_type,
                "targetName": target_name,
                "x": x,
                "y": y,
            }
        )
    return events


def military_action_tag(text: str) -> str:
    if not text.startswith("【"):
        return ""
    end = text.find("】")
    if end <= 1:
        return ""
    return text[1:end]


def military_march_fields(
    march_kind: int,
    march_value: int,
    event_time_ms: int,
) -> Dict[str, Any]:
    if march_kind not in MILITARY_MARCH_KINDS:
        return {}
    if not MILITARY_TIMESTAMP_MIN_MS < event_time_ms < MILITARY_TIMESTAMP_MAX_MS:
        return {}
    return {
        "marchKind": march_kind,
        "marchKindText": MILITARY_MARCH_KINDS[march_kind],
        "marchValue": march_value,
        "eventTimeMs": event_time_ms,
    }


def parse_8600_military_march_tail(
    payload: bytes,
    position: int,
) -> Dict[str, Any]:
    if position + 13 > len(payload):
        return {}
    march_kind = payload[position]
    march_value = int.from_bytes(payload[position + 1:position + 5], "big")
    event_time_ms = int.from_bytes(
        payload[position + 5:position + 13],
        "big",
    )
    return military_march_fields(march_kind, march_value, event_time_ms)


def military_action_state(
    tag: str,
    text: str,
    march: Dict[str, Any],
) -> str:
    if tag == "副本":
        if MILITARY_BATTLE_IN_PROGRESS_MARKER in text:
            return "战斗"
        return "备战"
    base = MILITARY_ACTION_STATE_BY_TAG.get(tag, tag)
    if base == "战斗":
        march_kind = march.get("marchKind")
        if (
            march_kind in MILITARY_OUTBOUND_MARCH_KINDS
            and int(march.get("marchValue") or 0) > 0
        ):
            return "出征"
    return base


class _Military8600Cursor:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.offset = 0

    def take(self, size: int, field: str) -> bytes:
        if size < 0 or self.offset + size > len(self.payload):
            raise ValueError(
                f"0x8600 字段 {field} 越界：offset={self.offset}, "
                f"size={size}, payload={len(self.payload)}"
            )
        start = self.offset
        self.offset += size
        return self.payload[start:self.offset]

    def u8(self, field: str) -> int:
        return self.take(1, field)[0]

    def u16(self, field: str) -> int:
        return int.from_bytes(self.take(2, field), "big")

    def u32(self, field: str) -> int:
        return int.from_bytes(self.take(4, field), "big")

    def u64(self, field: str) -> int:
        return int.from_bytes(self.take(8, field), "big")

    def utf(self, field: str) -> Dict[str, Any]:
        start = self.offset
        length = self.u16(f"{field}.length")
        raw = self.take(length, field)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"0x8600 字段 {field} 不是合法 UTF-8") from error
        return {"text": text, "offset": start, "length": length}


def _military_8600_count(value: int, field: str) -> int:
    if not 0 <= value <= MILITARY_8600_MAX_SECTION_ITEMS:
        raise ValueError(f"0x8600 字段 {field} 数量异常：{value}")
    return value


def _parse_8600_descriptors(
    cursor: _Military8600Cursor,
    section_type: int,
) -> List[Dict[str, Any]]:
    count = _military_8600_count(
        cursor.u16(f"section{section_type}.descriptorCount"),
        f"section{section_type}.descriptorCount",
    )
    descriptors = []
    for index in range(count):
        descriptor = cursor.utf(
            f"section{section_type}.descriptors[{index}].text"
        )
        value_count = _military_8600_count(
            cursor.u16(
                f"section{section_type}.descriptors[{index}].valueCount"
            ),
            f"section{section_type}.descriptors[{index}].valueCount",
        )
        if section_type in {1, 3}:
            descriptor["recordIndexes"] = [
                cursor.u16(
                    f"section{section_type}.descriptors[{index}].values"
                    f"[{value_index}]"
                )
                for value_index in range(value_count)
            ]
        elif section_type == 2:
            descriptor["valueCount"] = value_count
            descriptor["objectId"] = cursor.u64(
                f"section2.descriptors[{index}].objectId"
            )
            descriptor["width"] = cursor.u16(
                f"section2.descriptors[{index}].width"
            )
            descriptor["height"] = cursor.u16(
                f"section2.descriptors[{index}].height"
            )
            update_count = _military_8600_count(
                cursor.u16(
                    f"section2.descriptors[{index}].updateCount"
                ),
                f"section2.descriptors[{index}].updateCount",
            )
            descriptor["updates"] = [
                cursor.u16(
                    f"section2.descriptors[{index}].updates[{update_index}]"
                )
                for update_index in range(update_count)
            ]
        else:
            raise ValueError(f"0x8600 未知分区类型：{section_type}")
        descriptors.append(descriptor)
    return descriptors


def _military_descriptor_for_record(
    descriptors: List[Dict[str, Any]],
    record_index: int,
) -> Dict[str, Any]:
    for descriptor in descriptors:
        if record_index in (descriptor.get("recordIndexes") or []):
            return descriptor
    if record_index < len(descriptors):
        return descriptors[record_index]
    return {"text": "", "offset": 0, "length": 0}


def _parse_8600_formation_records(
    cursor: _Military8600Cursor,
    section_type: int,
    descriptors: List[Dict[str, Any]],
    name_by_id: Dict[int, str],
) -> List[Dict[str, Any]]:
    count = _military_8600_count(
        cursor.u16(f"section{section_type}.recordCount"),
        f"section{section_type}.recordCount",
    )
    actions = []
    for index in range(count):
        record_offset = cursor.offset
        battle_id = cursor.u64(
            f"section{section_type}.records[{index}].battleId"
        )
        general_count = cursor.u8(
            f"section{section_type}.records[{index}].generalCount"
        )
        if not 1 <= general_count <= 32:
            raise ValueError(
                f"0x8600 section{section_type} 将领数异常：{general_count}"
            )
        general_ids = []
        general_flags = []
        for general_index in range(general_count):
            general_ids.append(
                cursor.u64(
                    f"section{section_type}.records[{index}].generals"
                    f"[{general_index}].id"
                )
            )
            general_flags.append(
                cursor.u8(
                    f"section{section_type}.records[{index}].generals"
                    f"[{general_index}].flag"
                )
            )
        target_id = cursor.u64(
            f"section{section_type}.records[{index}].targetId"
        )
        target_type = cursor.u8(
            f"section{section_type}.records[{index}].targetType"
        )
        target = cursor.utf(
            f"section{section_type}.records[{index}].targetName"
        )
        x = cursor.u16(f"section{section_type}.records[{index}].x")
        y = cursor.u16(f"section{section_type}.records[{index}].y")
        march: Dict[str, Any] = {}
        record_kind: Optional[int] = None
        if section_type == 1:
            record_kind = cursor.u8(f"section1.records[{index}].recordKind")
            march_value = cursor.u32(
                f"section1.records[{index}].marchValue"
            )
            event_time_ms = cursor.u64(
                f"section1.records[{index}].eventTimeMs"
            )
            march = military_march_fields(
                record_kind,
                march_value,
                event_time_ms,
            )
        else:
            cursor.u64(
                f"section3.records[{index}].serverTimeReference"
            )

        descriptor = _military_descriptor_for_record(descriptors, index)
        text = str(descriptor.get("text") or "")
        tag = military_action_tag(text)
        if (
            not tag
            or battle_id <= 0
            or target_id <= 0
            or not str(target.get("text") or "")
            or any(general_id <= 0 for general_id in general_ids)
        ):
            continue
        action: Dict[str, Any] = {
            "text": text,
            "tag": tag,
            "state": military_action_state(tag, text, march),
            "incoming": False,
            "direction": "outgoing",
            "sourceSection": section_type,
            "offset": int(descriptor.get("offset") or 0),
            "recordOffset": record_offset,
            "battleId": battle_id,
            "generalIds": general_ids,
            "generalIdHexes": [
                f"{general_id:016x}" for general_id in general_ids
            ],
            "generalFlags": general_flags,
            "generalNames": [
                name_by_id.get(general_id, "") for general_id in general_ids
            ],
            "targetId": target_id,
            "targetIdHex": f"{target_id:016x}",
            "targetType": target_type,
            "targetTypeText": MILITARY_ACTION_TARGET_TYPES.get(
                target_type,
                "",
            ),
            "targetName": str(target.get("text") or ""),
            "x": x,
            "y": y,
            "hasCoord": bool(x or y),
        }
        if record_kind is not None:
            action["recordKind"] = record_kind
        action.update(march)
        actions.append(action)
    return actions


def _parse_8600_incoming_records(
    cursor: _Military8600Cursor,
) -> List[Dict[str, Any]]:
    count = _military_8600_count(
        cursor.u16("section2.incomingCount"),
        "section2.incomingCount",
    )
    actions = []
    for index in range(count):
        record_offset = cursor.offset
        record_id = cursor.u64(f"section2.incoming[{index}].recordId")
        attacker = cursor.utf(f"section2.incoming[{index}].attackerName")
        action_type = cursor.u8(f"section2.incoming[{index}].actionType")
        target = cursor.utf(f"section2.incoming[{index}].targetName")
        target_id = cursor.u64(f"section2.incoming[{index}].targetId")
        remaining_ms = cursor.u32(
            f"section2.incoming[{index}].remainingMs"
        )
        event_time_ms = cursor.u64(
            f"section2.incoming[{index}].eventTimeMs"
        )
        attacker_name = str(attacker.get("text") or "")
        target_name = str(target.get("text") or "")
        if (
            record_id <= 0
            or target_id <= 0
            or not attacker_name
            or not target_name
        ):
            continue
        known_action = MILITARY_INCOMING_ACTION_TYPES.get(action_type)
        if known_action:
            tag, verb = known_action
            action_type_text = tag
            text = f"【{tag}】{attacker_name}{verb}{target_name}"
        else:
            tag = "来袭"
            action_type_text = f"未知类型 {action_type}"
            text = (
                f"【来袭】{attacker_name}对{target_name}"
                f"发起军事行动（类型 {action_type}）"
            )
        actions.append(
            {
                "text": text,
                "tag": tag,
                "state": "来袭",
                "incoming": True,
                "direction": "incoming",
                "sourceSection": 2,
                "offset": int(attacker.get("offset") or 0),
                "recordOffset": record_offset,
                "recordId": record_id,
                "recordIdHex": f"{record_id:016x}",
                "attackerName": attacker_name,
                "actionType": action_type,
                "actionTypeText": action_type_text,
                "generalIds": [],
                "generalIdHexes": [],
                "generalFlags": [],
                "generalNames": [],
                "targetId": target_id,
                "targetIdHex": f"{target_id:016x}",
                "targetTypeText": "我方封地",
                "targetName": target_name,
                "x": 0,
                "y": 0,
                "hasCoord": False,
                "marchKindText": "来袭",
                "marchValue": remaining_ms,
                "eventTimeMs": event_time_ms,
            }
        )
    return actions


def _parse_8600_trailing_evidence(
    cursor: _Military8600Cursor,
) -> Dict[str, Any]:
    payload = cursor.payload
    reference_count = _military_8600_count(
        cursor.u16("tail.activeBattleReferenceCount"),
        "tail.activeBattleReferenceCount",
    )
    active_references = [
        {
            "battleId": cursor.u64(
                f"tail.activeBattleReferences[{index}].battleId"
            ),
            "flag": cursor.u8(
                f"tail.activeBattleReferences[{index}].flag"
            ),
        }
        for index in range(reference_count)
    ]
    cursor.u8("tail.generalBlockFlag")

    owned_chunks = []
    owned_count = _military_8600_count(
        cursor.u16("tail.ownedGeneralCount"),
        "tail.ownedGeneralCount",
    )
    for index in range(owned_count):
        start = cursor.offset
        cursor.u64(f"tail.ownedGenerals[{index}].id")
        cursor.utf(f"tail.ownedGenerals[{index}].name")
        cursor.take(
            MILITARY_8600_JIANGLING_BODY_LEN,
            f"tail.ownedGenerals[{index}].body",
        )
        owned_chunks.append(payload[start:cursor.offset])

    captive_records = []
    captive_count = _military_8600_count(
        cursor.u8("tail.captiveGeneralCount"),
        "tail.captiveGeneralCount",
    )
    for index in range(captive_count):
        general_id = cursor.u64(f"tail.captiveGenerals[{index}].id")
        name = str(
            cursor.utf(f"tail.captiveGenerals[{index}].name").get("text")
            or ""
        )
        body = cursor.take(
            MILITARY_8600_JIANGLING_BODY_LEN,
            f"tail.captiveGenerals[{index}].body",
        )
        cursor.u64(f"tail.captiveGenerals[{index}].ownerId")
        fief_id = cursor.u16(f"tail.captiveGenerals[{index}].fiefId")
        fief_name = str(
            cursor.utf(f"tail.captiveGenerals[{index}].fiefName").get("text")
            or ""
        )
        cursor.u64(f"tail.captiveGenerals[{index}].reservedId")
        cursor.u16(f"tail.captiveGenerals[{index}].reservedFlag")
        status = body[MILITARY_8600_STATUS_OFFSET]
        captive_records.append(
            {
                "id": general_id,
                "idHex": f"{general_id:016x}",
                "name": name,
                "source": "0x8600-captive-general-tail",
                "militarySnapshotFresh": True,
                "status": status,
                "statusText": general_status_text_from_code(status),
                "tili": int.from_bytes(
                    body[
                        MILITARY_8600_ENERGY_OFFSET:
                        MILITARY_8600_ENERGY_OFFSET + 2
                    ],
                    "big",
                ),
                "tiliLimit": int.from_bytes(
                    body[
                        MILITARY_8600_ENERGY_LIMIT_OFFSET:
                        MILITARY_8600_ENERGY_LIMIT_OFFSET + 2
                    ],
                    "big",
                ),
                "loyalty": body[MILITARY_8600_LOYALTY_OFFSET],
                "troopLimit": int.from_bytes(
                    body[
                        MILITARY_8600_TROOP_LIMIT_OFFSET:
                        MILITARY_8600_TROOP_LIMIT_OFFSET + 4
                    ],
                    "big",
                ),
                "placeID": int.from_bytes(
                    body[
                        MILITARY_8600_PLACE_ID_OFFSET:
                        MILITARY_8600_PLACE_ID_OFFSET + 8
                    ],
                    "big",
                    signed=True,
                ),
                "captureFiefId": fief_id,
                "captureFiefName": fief_name,
            }
        )

    troop_start = cursor.offset
    troop_assignment_count = _military_8600_count(
        cursor.u8("tail.troopAssignmentCount"),
        "tail.troopAssignmentCount",
    )
    for index in range(troop_assignment_count):
        cursor.take(
            MILITARY_8600_S5_ENTRY_LEN,
            f"tail.troopAssignments[{index}]",
        )
    troop_blob = payload[troop_start:cursor.offset]
    owned_records = recover_generals_from_8004(
        (b"".join(owned_chunks) + troop_blob).hex()
    )
    for record in owned_records:
        record["source"] = "0x8600-owned-general-tail"
        record["militarySnapshotFresh"] = True
    return {
        "activeBattleReferences": active_references,
        "generalStatusRecords": owned_records,
        "captiveGeneralRecords": captive_records,
        "troopAssignmentCount": troop_assignment_count,
        "trailingEvidenceParsed": True,
        "unparsedTailByteCount": len(payload) - cursor.offset,
    }


def parse_8600_military_payload(
    payload: bytes,
    generals: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    name_by_id = {}
    for general in generals or []:
        try:
            general_id = int(general.get("id") or 0)
        except (TypeError, ValueError):
            continue
        name = str(general.get("name") or "")
        if general_id > 0 and name:
            name_by_id[general_id] = name

    cursor = _Military8600Cursor(payload)
    actions = []
    try:
        header_count = _military_8600_count(
            cursor.u16("headerPairCount"),
            "headerPairCount",
        )
        for index in range(header_count):
            cursor.u8(f"headerPairs[{index}].kind")
            cursor.u16(f"headerPairs[{index}].value")
        section_count = _military_8600_count(
            cursor.u8("sectionCount"),
            "sectionCount",
        )
        for section_index in range(section_count):
            section_type = cursor.u8(f"sections[{section_index}].type")
            if section_type not in {1, 2, 3}:
                raise ValueError(f"0x8600 未知分区类型：{section_type}")
            descriptors = _parse_8600_descriptors(cursor, section_type)
            if section_type in {1, 3}:
                actions.extend(
                    _parse_8600_formation_records(
                        cursor,
                        section_type,
                        descriptors,
                        name_by_id,
                    )
                )
            else:
                actions.extend(_parse_8600_incoming_records(cursor))
    except ValueError as error:
        return {
            "actions": [],
            "trailingEvidenceParsed": False,
            "unparsedTailByteCount": len(payload),
            "trailingParseError": str(error),
        }

    details: Dict[str, Any] = {
        "actions": actions,
        "activeBattleReferences": [],
        "generalStatusRecords": [],
        "captiveGeneralRecords": [],
        "troopAssignmentCount": 0,
        "trailingEvidenceParsed": False,
        "unparsedTailByteCount": 0,
    }
    if cursor.offset < len(payload):
        try:
            details.update(_parse_8600_trailing_evidence(cursor))
        except ValueError as error:
            details.update(
                {
                    "trailingEvidenceParsed": False,
                    "unparsedTailByteCount": len(payload) - cursor.offset,
                    "trailingParseError": str(error),
                }
            )
    return details


def parse_8600_military_actions(
    payload: bytes,
    generals: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    return list(
        parse_8600_military_payload(payload, generals).get("actions") or []
    )


def build_military_snapshot(
    payloads: List[bytes],
    generals: Optional[List[Dict[str, Any]]] = None,
    http_code: int = 200,
    updated_at: Optional[int] = None,
) -> Dict[str, Any]:
    """Aggregate parsed payloads without mutating either host's account state."""

    actions = []
    active_references: Dict[int, Dict[str, Any]] = {}
    general_records: Dict[int, Dict[str, Any]] = {}
    captive_records: Dict[int, Dict[str, Any]] = {}
    troop_assignment_count = 0
    trailing_evidence_parsed = False
    unparsed_tail_byte_count = 0
    trailing_errors = []
    seen: Set[Tuple[str, int]] = set()
    for payload in payloads:
        parsed = parse_8600_military_payload(payload, generals)
        for reference in parsed.get("activeBattleReferences") or []:
            battle_id = int(reference.get("battleId") or 0)
            if battle_id > 0:
                active_references[battle_id] = dict(reference)
        for record in parsed.get("generalStatusRecords") or []:
            general_id = int(record.get("id") or 0)
            if general_id > 0:
                general_records[general_id] = dict(record)
        for record in parsed.get("captiveGeneralRecords") or []:
            general_id = int(record.get("id") or 0)
            if general_id > 0:
                captive_records[general_id] = dict(record)
        troop_assignment_count += int(parsed.get("troopAssignmentCount") or 0)
        trailing_evidence_parsed = (
            trailing_evidence_parsed
            or bool(parsed.get("trailingEvidenceParsed"))
        )
        unparsed_tail_byte_count += int(
            parsed.get("unparsedTailByteCount") or 0
        )
        if parsed.get("trailingParseError"):
            trailing_errors.append(str(parsed["trailingParseError"]))
        for action in parsed.get("actions") or []:
            if action.get("incoming"):
                identity = ("incoming", int(action.get("recordId") or 0))
            else:
                identity = ("battle", int(action.get("battleId") or 0))
            if identity[1] <= 0 or identity in seen:
                continue
            seen.add(identity)
            actions.append(action)
    state_order = {
        "来袭": 0,
        "战斗": 1,
        "出征": 2,
        "驻守": 3,
        "返回": 4,
        "备战": 5,
    }
    actions.sort(
        key=lambda item: (
            state_order.get(str(item.get("state") or ""), 3),
            int(item.get("recordId") or item.get("battleId") or 0),
        )
    )
    snapshot: Dict[str, Any] = {
        "sourceOpcode": "0x1600/0x8600",
        "actions": actions,
        "actionCount": len(actions),
        "incomingCount": sum(1 for item in actions if item.get("incoming")),
        "activeBattleReferences": list(active_references.values()),
        "generalStatusRecords": list(general_records.values()),
        "generalStatusCount": len(general_records),
        "captiveGeneralRecords": list(captive_records.values()),
        "captiveGeneralCount": len(captive_records),
        "troopAssignmentCount": troop_assignment_count,
        "trailingEvidenceParsed": trailing_evidence_parsed,
        "unparsedTailByteCount": unparsed_tail_byte_count,
        "http": http_code,
        "responded": bool(payloads),
    }
    if updated_at is not None:
        snapshot["updatedAt"] = int(updated_at)
    if trailing_errors:
        snapshot["trailingParseError"] = "；".join(trailing_errors)
    return snapshot
