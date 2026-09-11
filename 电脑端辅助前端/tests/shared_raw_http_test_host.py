"""Test-only adapter which exercises the shared core's byte-only HTTP path.

Older workflow fixtures were written against the temporary JSON game-command
bridge.  The mixin decodes Python's real request envelope, delegates only the
fixture selection to those existing methods, and re-encodes a real byte
response for ``parse_response``.  Production code never imports this module.
"""

from __future__ import annotations

import json
import struct
from typing import Any, Mapping


FIXTURE_GAME_HTTP = "https://fixture.invalid/kingWapServer/HttpClient"


def _decode_request_commands(body: bytes) -> list[tuple[int, bytes]]:
    position = 0
    if len(body) < 2:
        raise AssertionError("shared raw request is truncated before header")
    header_length = int.from_bytes(body[position:position + 2], "big")
    position += 2 + header_length
    if position + 9 > len(body):
        raise AssertionError("shared raw request is truncated before command count")
    position += 8  # timestamp
    command_count = body[position]
    position += 1
    commands: list[tuple[int, bytes]] = []
    for _index in range(command_count):
        if position + 22 > len(body):
            raise AssertionError("shared raw request command header is truncated")
        position += 16  # dm and reserved long
        payload_length = int.from_bytes(body[position:position + 2], "big")
        position += 2
        opcode = int.from_bytes(body[position:position + 2], "big")
        position += 2
        name_length = int.from_bytes(body[position:position + 2], "big")
        position += 2 + name_length
        payload = body[position:position + payload_length]
        if len(payload) != payload_length:
            raise AssertionError("shared raw request payload is truncated")
        position += payload_length
        commands.append((opcode, payload))
    if position != len(body):
        raise AssertionError("shared raw request has trailing bytes")
    return commands


def _decode_single_request(body: bytes) -> tuple[int, bytes]:
    commands = _decode_request_commands(body)
    if len(commands) != 1:
        raise AssertionError(f"expected one shared command, got {len(commands)}")
    return commands[0]


def _encode_response(packets: list[Mapping[str, Any]]) -> bytes:
    if len(packets) > 255:
        raise AssertionError("fixture response contains too many packets")
    output = bytearray((1, len(packets)))
    for packet in packets:
        opcode = int(packet.get("opcode") or 0)
        payload = bytes.fromhex(str(packet.get("payloadHex") or ""))
        output += struct.pack(">qqbiHB", 0, 0, 0, len(payload), opcode, 0)
        output += payload
    return bytes(output)


class RawHttpGameCommandHostMixin:
    """Turns legacy fixture selection into a real raw-HTTP host capability."""

    def loadSessionSecrets(self, _account_ref: str) -> str:
        return json.dumps({"dm": "202"})

    def executeRawHttp(self, request_json: str) -> str:
        request = json.loads(request_json)
        opcode, payload = _decode_single_request(
            bytes.fromhex(str(request.get("bodyHex") or ""))
        )
        command = {
            "opcode": opcode,
            "payloadHex": payload.hex(),
            "phase": str(request.get("phase") or "shared-core/test"),
            "readOnly": bool(request.get("readOnly", False)),
        }
        context = {
            key: request[key]
            for key in ("operationId", "requestId")
            if request.get(key) not in (None, "")
        }
        legacy = json.loads(
            self.executeGameCommand(
                str(request.get("accountRef") or ""),
                json.dumps(command, ensure_ascii=False),
                json.dumps(context, ensure_ascii=False),
            )
        )
        body = legacy.get("body")
        body = body if isinstance(body, dict) else {}
        fact = body.get("gameCommandFact")
        fact = fact if isinstance(fact, dict) else {}
        http_status = int(fact.get("httpCode") or legacy.get("status") or 500)
        packets = fact.get("packets")
        packets = packets if isinstance(packets, list) else []
        return json.dumps({
            "status": http_status,
            "bodyHex": _encode_response(packets).hex(),
        })
