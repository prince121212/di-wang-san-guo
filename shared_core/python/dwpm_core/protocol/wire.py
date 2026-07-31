"""Host-neutral byte primitives and game request/response envelopes."""

from __future__ import annotations

import struct
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple


# Recovered from the original APK asset script/1590000.k (Lo/a.o()).
DEFAULT_RESPONSE_OBFUSCATION_KEY = bytes.fromhex(
    "f331e74bd85a8e2ab96791bb02bd32d2"
    "40494b00351014efe75f2b0e62b2abba"
)


def encode_utf(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack(">H", len(encoded)) + encoded


def read_utf(payload: bytes, position: int) -> Tuple[str, int]:
    length = int.from_bytes(payload[position:position + 2], "big")
    position += 2
    return (
        payload[position:position + length].decode("utf-8", errors="ignore"),
        position + length,
    )


def make_packet(
    commands: Sequence[Tuple[int, bytes]],
    dm: int,
    *,
    header: str,
    timestamp_millis: int,
) -> bytes:
    output = bytearray()
    output += encode_utf(header)
    output += struct.pack(">q", int(timestamp_millis))
    output += struct.pack(">B", len(commands))
    for opcode, payload in commands:
        body = bytes(payload)
        output += struct.pack(">q", int(dm))
        output += struct.pack(">q", 0)
        output += struct.pack(">H", len(body))
        output += struct.pack(">H", int(opcode))
        output += encode_utf("")
        output += body
    return bytes(output)


def deobfuscate_response_payload(
    payload: bytes,
    key: bytes = DEFAULT_RESPONSE_OBFUSCATION_KEY,
) -> bytes:
    if not key:
        raise RuntimeError("游戏响应混淆密钥为空")
    return bytes(
        (value - key[index % len(key)]) & 0xFF
        for index, value in enumerate(payload)
    )


def parse_response(
    data: bytes,
    response_obfuscation_key: bytes = DEFAULT_RESPONSE_OBFUSCATION_KEY,
) -> List[Dict[str, Any]]:
    position = 0
    packets: List[Dict[str, Any]] = []

    def need(size: int) -> None:
        if position + size > len(data):
            raise ValueError(
                f"parse overflow pos={position} need={size} size={len(data)}"
            )

    def u8() -> int:
        nonlocal position
        need(1)
        value = data[position]
        position += 1
        return value

    def i64() -> int:
        nonlocal position
        need(8)
        value = struct.unpack(">q", data[position:position + 8])[0]
        position += 8
        return value

    def i32() -> int:
        nonlocal position
        need(4)
        value = struct.unpack(">i", data[position:position + 4])[0]
        position += 4
        return value

    def u16() -> int:
        nonlocal position
        need(2)
        value = struct.unpack(">H", data[position:position + 2])[0]
        position += 2
        return value

    try:
        outer_count = u8()
        for outer_index in range(outer_count):
            inner_count = u8()
            for inner_index in range(inner_count):
                long0 = i64()
                long1 = i64()
                obfuscated = u8()
                length = i32()
                opcode = u16()
                fragment = u8()
                need(length)
                payload = data[position:position + length]
                position += length
                if obfuscated:
                    payload = deobfuscate_response_payload(
                        payload,
                        response_obfuscation_key,
                    )
                packets.append(
                    {
                        "outer": outer_index,
                        "inner": inner_index,
                        "long0": long0,
                        "long1": long1,
                        "obf": obfuscated,
                        "len": length,
                        "opcode": opcode,
                        "frag": fragment,
                        "payload": payload,
                    }
                )
    except Exception as error:
        packets.append({"parseError": str(error), "rawHex": data.hex()[:4096]})
    return packets


def packet_opcode(packet: Dict[str, Any]) -> Optional[int]:
    value = packet.get("opcode")
    try:
        if isinstance(value, str):
            return int(value, 16) if value.lower().startswith("0x") else int(value)
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def packet_payload_bytes(packet: Dict[str, Any]) -> bytes:
    payload = packet.get("payload")
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    payload_hex = str(packet.get("payloadHex") or "").strip()
    try:
        return bytes.fromhex(payload_hex) if payload_hex else b""
    except ValueError:
        return b""


def printable(payload: bytes, limit: int = 512) -> str:
    text = payload.decode("utf-8", errors="ignore")
    text = "".join(
        character
        if (
            0x20 <= ord(character) <= 0x7E
            or "\u4e00" <= character <= "\u9fff"
        )
        else " "
        for character in text
    )
    return re.sub(r"\s+", " ", text).strip()[:limit]


def extract_utf_strings(
    payload: bytes,
    *,
    min_len: int = 2,
    max_len: int = 180,
) -> List[Dict[str, Any]]:
    strings: List[Dict[str, Any]] = []
    for position in range(0, max(0, len(payload) - 2)):
        length = int.from_bytes(payload[position:position + 2], "big")
        if (
            not min_len <= length <= max_len
            or position + 2 + length > len(payload)
        ):
            continue
        raw = payload[position + 2:position + 2 + length]
        try:
            text = raw.decode("utf-8")
        except Exception:
            continue
        if not any("\u4e00" <= character <= "\u9fff" for character in text):
            continue
        if any(
            ord(character) < 0x20 and character not in "\r\n\t"
            for character in text
        ):
            continue
        strings.append({"offset": position, "length": length, "text": text})
    return strings


def encode_xy(x: int, y: int) -> str:
    return f"{int(x):04x}{int(y):04x}"


def read_only_gamehex_to_cmd(gamehex: str) -> Tuple[int, bytes]:
    body = str(gamehex)[18:]
    declared = int(body[:2], 16)
    opcode = int(body[2:6], 16)
    payload = bytes.fromhex(body[6:])
    if len(payload) != declared:
        raise ValueError(
            f"bad readonly gamehex declared={declared} actual={len(payload)}"
        )
    return opcode, payload


def action_gamehex_to_cmd(gamehex: str) -> Tuple[int, int, bytes]:
    body = str(gamehex)[18:]
    declared = int(body[:2], 16)
    opcode = int(body[2:6], 16)
    payload = bytes.fromhex(body[6:])
    return declared, opcode, payload


def normalize_hex_id(id_value: Any) -> str:
    clean = "".join(
        character
        for character in str(id_value or "")
        if character in "0123456789abcdefABCDEF"
    ).lower()
    if not clean:
        raise RuntimeError("缺少将领 ID")
    significant = clean.lstrip("0") or "0"
    if len(significant) > 16:
        raise RuntimeError(f"将领 ID 超过 8 字节：{id_value}")
    return significant.rjust(16, "0")
