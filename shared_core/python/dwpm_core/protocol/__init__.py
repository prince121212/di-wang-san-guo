"""Game-wire protocol shared by every host."""

from .wire import (
    DEFAULT_RESPONSE_OBFUSCATION_KEY,
    action_gamehex_to_cmd,
    deobfuscate_response_payload,
    encode_utf,
    encode_xy,
    extract_utf_strings,
    make_packet,
    normalize_hex_id,
    packet_opcode,
    packet_payload_bytes,
    parse_response,
    printable,
    read_only_gamehex_to_cmd,
    read_utf,
)

__all__ = [
    "DEFAULT_RESPONSE_OBFUSCATION_KEY",
    "action_gamehex_to_cmd",
    "deobfuscate_response_payload",
    "encode_utf",
    "encode_xy",
    "extract_utf_strings",
    "make_packet",
    "normalize_hex_id",
    "packet_opcode",
    "packet_payload_bytes",
    "parse_response",
    "printable",
    "read_only_gamehex_to_cmd",
    "read_utf",
]
