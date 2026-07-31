"""Raid target query payload and 0x8310 fief-list parsing."""

from __future__ import annotations

import struct
from typing import Any, Dict

from ..contracts import load_behavior_contract
from ..protocol.wire import encode_utf, printable, read_utf


RAID_CONTRACT = load_behavior_contract()["raid"]
RAID_TARGET_PAYLOAD_PREFIX = bytes.fromhex(
    str(RAID_CONTRACT["targetPayloadPrefixHex"])
)


def build_raid_fief_list_payload(player_name: str) -> bytes:
    name = str(player_name or "").strip()
    if not name:
        raise RuntimeError("请填写要掠夺的玩家名称")
    return RAID_TARGET_PAYLOAD_PREFIX + encode_utf(name)


def parse_raid_fief_list(payload: bytes) -> Dict[str, Any]:
    position = 0
    output: Dict[str, Any] = {
        "rawHex": payload.hex()[:4096],
        "fiefs": [],
    }
    try:
        if len(payload) < 6:
            raise RuntimeError("0x8310 响应过短")
        flag = struct.unpack(">H", payload[position:position + 2])[0]
        position += 2
        player_name, position = read_utf(payload, position)
        country, position = read_utf(payload, position)
        if position >= len(payload):
            raise RuntimeError("0x8310 缺少封地数量")
        count = payload[position]
        position += 1
        fiefs = []
        for index in range(int(count)):
            if position + 8 > len(payload):
                raise RuntimeError(f"第 {index + 1} 条封地缺少 targetId")
            target_id = struct.unpack(">q", payload[position:position + 8])[0]
            position += 8
            fief_name, position = read_utf(payload, position)
            serial_byte = payload[position] if position < len(payload) else None
            if position < len(payload):
                position += 1
            city_name, position = read_utf(payload, position)
            tail = payload[position:position + 5]
            position += min(5, max(0, len(payload) - position))
            map_flag = tail[0] if len(tail) >= 1 else None
            map_x = (
                struct.unpack(">H", tail[1:3])[0]
                if len(tail) >= 3
                else None
            )
            map_y = (
                struct.unpack(">H", tail[3:5])[0]
                if len(tail) >= 5
                else None
            )
            fiefs.append(
                {
                    "index": index + 1,
                    "targetId": target_id,
                    "targetIdHex": f"{target_id:016x}",
                    "targetHex": f"{target_id:016x}",
                    "fiefName": fief_name,
                    "name": fief_name,
                    "cityName": city_name,
                    "city": city_name,
                    "serialByte": serial_byte,
                    "tailHex": tail.hex(),
                    "mapFlag": map_flag,
                    "x": map_x,
                    "y": map_y,
                }
            )
        output.update(
            {
                "flag": flag,
                "playerName": player_name,
                "country": country,
                "count": count,
                "fiefs": fiefs,
                "parsedBytes": position,
            }
        )
    except Exception as error:
        output.update(
            {
                "parseError": str(error),
                "textPreview": printable(payload, 1200),
            }
        )
    return output
