"""Shared expedition payloads for brush, mine, raid, lossless and dungeon."""

from __future__ import annotations

import struct
from typing import Any, Dict, List, Tuple

from ..contracts import load_behavior_contract
from ..protocol.wire import normalize_hex_id, printable, read_utf


BEHAVIOR_CONTRACT = load_behavior_contract()
BRUSH_CONTRACT = BEHAVIOR_CONTRACT["brushYellow"]
MINE_CONTRACT = BEHAVIOR_CONTRACT["mine"]
RAID_CONTRACT = BEHAVIOR_CONTRACT["raid"]
LOSSLESS_CONTRACT = BEHAVIOR_CONTRACT["lossless"]
DUNGEON_CONTRACT = BEHAVIOR_CONTRACT["dungeon"]


def build_brush_payloads(
    general_chunks: List[str],
    target_hex: str,
) -> Tuple[str, str]:
    payloads = build_brush_payloads_variant(general_chunks, target_hex, variant=0)
    return payloads["prepare"], payloads["expedition"]


def build_brush_payloads_variant(
    general_chunks: List[str],
    target_hex: str,
    variant: int = 0,
) -> Dict[str, Any]:
    count = len(general_chunks)
    identifiers = "".join(general_chunks)
    prefix = "0" * 18
    canonical_action_hex = f"{int(BRUSH_CONTRACT['actionType']):02x}"
    variants = {
        0: {
            "prepareOp": f"1520{canonical_action_hex}0",
            "prepareTrailer": target_hex,
            "prepareExtra": 0x0A,
            "expeditionOp": f"1522{canonical_action_hex}0",
            "expeditionTrailer": target_hex + "ffffffffffffffff000000",
            "expeditionExtra": 0x15,
            "actionType": int(BRUSH_CONTRACT["actionType"]),
        },
        10: {
            "prepareOp": "15200a0",
            "prepareTrailer": target_hex,
            "prepareExtra": 0x0A,
            "expeditionOp": "15220a0",
            "expeditionTrailer": target_hex + "ffffffffffffffff000000",
            "expeditionExtra": 0x15,
        },
        1: {
            "prepareOp": "1520020",
            "prepareTrailer": "0000" + target_hex,
            "prepareExtra": 0x0A,
            "expeditionOp": "1522020",
            "expeditionTrailer": "0000" + target_hex + "ffffffffffffffff000000",
            "expeditionExtra": 0x15,
        },
        2: {
            "prepareOp": "15200e0",
            "prepareTrailer": "ffffffff0004" + target_hex,
            "prepareExtra": 0x0E,
            "expeditionOp": "15220e0",
            "expeditionTrailer": (
                "ffffffff0004" + target_hex + "ffffffffffffffff000000"
            ),
            "expeditionExtra": 0x19,
        },
        3: {
            "prepareOp": "1520010",
            "prepareTrailer": target_hex,
            "prepareExtra": 0x08,
            "expeditionOp": "1522010",
            "expeditionTrailer": target_hex + "ffffffffffffffff000000",
            "expeditionExtra": 0x13,
        },
        4: {
            "prepareOp": "15200b0",
            "prepareTrailer": target_hex,
            "prepareExtra": 0x08,
            "expeditionOp": "15220b0",
            "expeditionTrailer": target_hex + "ffffffffffffffff000000",
            "expeditionExtra": 0x13,
        },
    }
    normalized_variant = int(variant)
    spec = variants.get(normalized_variant)
    if spec is None:
        raise RuntimeError(f"未知刷黄出征 payload 变体：{variant}")
    prepare = (
        prefix
        + f"{count * 8 + spec['prepareExtra']:x}"
        + spec["prepareOp"]
        + str(count)
        + identifiers
        + spec["prepareTrailer"]
    )
    expedition = (
        prefix
        + f"{count * 8 + spec['expeditionExtra']:x}"
        + spec["expeditionOp"]
        + str(count)
        + identifiers
        + spec["expeditionTrailer"]
    )
    return {
        "variant": normalized_variant,
        "prepare": prepare,
        "expedition": expedition,
        **spec,
    }


def _standard_prepare(
    general_id_hexes: List[str],
    target_bytes: bytes,
    *,
    action_type: int,
    maximum_generals: int,
    empty_error: str,
    too_many_error: str,
) -> bytes:
    if not general_id_hexes:
        raise RuntimeError(empty_error)
    if len(general_id_hexes) > maximum_generals:
        raise RuntimeError(too_many_error)
    output = bytearray([action_type, len(general_id_hexes)])
    for general_id in general_id_hexes:
        output += bytes.fromhex(normalize_hex_id(general_id))
    output += target_bytes
    return bytes(output)


def build_mine_payloads(
    general_id_hexes: List[str],
    resource_id: int,
) -> Tuple[bytes, bytes]:
    maximum = int(MINE_CONTRACT["maximumGeneralsPerFormation"])
    prepare = _standard_prepare(
        general_id_hexes,
        struct.pack(">q", int(resource_id)),
        action_type=int(MINE_CONTRACT["actionType"]),
        maximum_generals=maximum,
        empty_error="打矿至少需要选择 1 个出征将领",
        too_many_error=f"打矿编队最多选择{maximum}名出征将领",
    )
    return prepare, prepare + struct.pack(">q", -1) + b"\x00\x00\x00"


def build_raid_prepare_payload(
    general_id_hexes: List[str],
    target_id: int,
) -> bytes:
    maximum = int(RAID_CONTRACT["maximumGeneralsPerFormation"])
    return _standard_prepare(
        general_id_hexes,
        struct.pack(">q", int(target_id)),
        action_type=int(RAID_CONTRACT["actionType"]),
        maximum_generals=maximum,
        empty_error="掠夺至少需要选择 1 个出征将领",
        too_many_error=f"掠夺编队最多选择{maximum}名出征将领",
    )


def build_raid_expedition_payload(
    general_id_hexes: List[str],
    target_id: int,
) -> bytes:
    return (
        build_raid_prepare_payload(general_id_hexes, target_id)
        + struct.pack(">q", int(RAID_CONTRACT["immediateRelatedLong"]))
        + bytes.fromhex(str(RAID_CONTRACT["immediateFlagsHex"]))
    )


def build_lossless_prepare_payload(
    general_id_hexes: List[str],
    role_id: int,
) -> bytes:
    maximum = int(LOSSLESS_CONTRACT["maximumGeneralsPerFormation"])
    return _standard_prepare(
        general_id_hexes,
        struct.pack(">q", int(role_id)),
        action_type=int(LOSSLESS_CONTRACT["actionType"]),
        maximum_generals=maximum,
        empty_error="无损至少需要选择1个出征将领",
        too_many_error=f"无损编队最多选择{maximum}名出征将领",
    )


def build_lossless_expedition_payload(
    general_id_hexes: List[str],
    role_id: int,
) -> bytes:
    return (
        build_lossless_prepare_payload(general_id_hexes, role_id)
        + struct.pack(">q", int(LOSSLESS_CONTRACT["immediateRelatedLong"]))
        + bytes.fromhex(str(LOSSLESS_CONTRACT["immediateFlagsHex"]))
    )


def build_dungeon_prepare_payload(
    general_id_hexes: List[str],
    stage_code: int,
) -> bytes:
    maximum = int(DUNGEON_CONTRACT["maximumGeneralsPerFormation"])
    return _standard_prepare(
        general_id_hexes,
        struct.pack(">i", -1)
        + struct.pack(">H", int(DUNGEON_CONTRACT["singlePlayerType"]))
        + struct.pack(">H", int(stage_code)),
        action_type=int(DUNGEON_CONTRACT["actionType"]),
        maximum_generals=maximum,
        empty_error="副本至少需要选择 1 个出征将领",
        too_many_error=f"副本编队最多选择{maximum}名出征将领",
    )


def build_dungeon_expedition_payload(
    general_id_hexes: List[str],
    stage_code: int,
) -> bytes:
    return (
        build_dungeon_prepare_payload(general_id_hexes, stage_code)
        + struct.pack(">q", int(DUNGEON_CONTRACT["immediateRelatedLong"]))
        + bytes.fromhex(str(DUNGEON_CONTRACT["immediateFlagsHex"]))
    )


def parse_dispatch_response(payload: bytes) -> Dict[str, Any]:
    """Parse the shared 0x8522 expedition response shape."""

    output: Dict[str, Any] = {"rawHex": payload.hex(), "success": False}
    if not payload:
        return {**output, "status": None, "message": "空响应"}
    try:
        status = struct.unpack(">b", payload[:1])[0]
        position = 1
        message = ""
        if position + 2 <= len(payload):
            message, position = read_utf(payload, position)
        output.update(
            {
                "status": status,
                "statusOk": status == 0,
                "message": message,
            }
        )
        if status == 0 and position + 8 <= len(payload):
            battle_id = struct.unpack(">q", payload[position:position + 8])[0]
            output["battleId"] = battle_id
            output["battleIdHex"] = f"{battle_id:016x}"
        output["success"] = status == 0 and int(output.get("battleId") or 0) > 0
        if status == 0 and not output["success"] and not message:
            output["message"] = "出征响应缺少有效 battleId"
        if status != 0 and not message:
            output["message"] = (
                "目标封地的君主等级不足，或使用了免战牌，处于保护状态"
                if status == -14
                else ("操作失败" if status == -1 else f"失败状态 {status}")
            )
        return output
    except Exception as error:
        return {
            **output,
            "parseError": str(error),
            "textPreview": printable(payload, 512),
        }
