from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = ROOT / "shared_core" / "python"
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
FIXTURE_PATH = ROOT / "shared_core" / "protocol_parity_fixtures.json"
if str(CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CORE_SOURCE))

from dwpm_core.hashing import source_manifest
from dwpm_core.protocol import (
    action_gamehex_to_cmd,
    encode_utf,
    encode_xy,
    make_packet,
    normalize_hex_id,
    packet_opcode,
    packet_payload_bytes,
    parse_response,
    read_only_gamehex_to_cmd,
    read_utf,
)


SPEC = importlib.util.spec_from_file_location("dwpm_server_wire_parity", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class SharedProtocolWireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.fixture = payload["fixtures"]["wireEnvelopeV1"]

    def test_utf_and_coordinate_bytes_match_the_frozen_fixture(self) -> None:
        fixture = self.fixture
        encoded = encode_utf(fixture["utfText"])

        self.assertEqual(encoded.hex(), fixture["utfHex"])
        self.assertEqual(SERVER.utf(fixture["utfText"]), encoded)
        self.assertEqual(read_utf(encoded, 0), (fixture["utfText"], len(encoded)))
        self.assertEqual(SERVER.read_utf(encoded, 0), read_utf(encoded, 0))
        self.assertEqual(
            encode_xy(fixture["xy"]["x"], fixture["xy"]["y"]),
            fixture["xy"]["hex"],
        )
        self.assertEqual(
            SERVER.encode_xy(fixture["xy"]["x"], fixture["xy"]["y"]),
            fixture["xy"]["hex"],
        )

    def test_request_envelope_is_byte_for_byte_identical(self) -> None:
        request = self.fixture["request"]
        commands = [
            (int(row["opcode"], 0), bytes.fromhex(row["payloadHex"]))
            for row in request["commands"]
        ]
        shared = make_packet(
            commands,
            request["dm"],
            header=request["header"],
            timestamp_millis=request["timestampMillis"],
        )
        original_now = SERVER.now_ms
        SERVER.now_ms = lambda: request["timestampMillis"]
        try:
            desktop = SERVER.make_packet(
                commands,
                request["dm"],
                header=request["header"],
            )
        finally:
            SERVER.now_ms = original_now

        self.assertEqual(shared.hex(), request["expectedHex"])
        self.assertEqual(desktop, shared)

    def test_plain_and_obfuscated_responses_have_identical_semantics(self) -> None:
        expected_opcode = int(self.fixture["expectedOpcode"], 0)
        for response_key, payload_key in (
            ("plainResponseHex", "plainResponsePayloadHex"),
            ("obfuscatedResponseHex", "obfuscatedResponsePayloadHex"),
        ):
            raw = bytes.fromhex(self.fixture[response_key])
            shared = parse_response(raw)
            desktop = SERVER.parse_response(raw)

            self.assertEqual(desktop, shared)
            self.assertEqual(len(shared), 1)
            self.assertEqual(shared[0]["opcode"], expected_opcode)
            self.assertEqual(shared[0]["payload"].hex(), self.fixture[payload_key])
            self.assertEqual(packet_opcode(shared[0]), expected_opcode)
            self.assertEqual(packet_payload_bytes(shared[0]), shared[0]["payload"])

    def test_gamehex_and_identifier_helpers_are_shared(self) -> None:
        read_only = "0" * 18 + "00" + "1016"
        action = "0" * 18 + "02" + "1522" + "aabb"

        self.assertEqual(read_only_gamehex_to_cmd(read_only), (0x1016, b""))
        self.assertEqual(SERVER.read_only_gamehex_to_cmd(read_only), (0x1016, b""))
        self.assertEqual(action_gamehex_to_cmd(action), (2, 0x1522, b"\xaa\xbb"))
        self.assertEqual(SERVER.action_gamehex_to_cmd(action), (2, 0x1522, b"\xaa\xbb"))
        self.assertEqual(normalize_hex_id("0x7b"), "000000000000007b")
        self.assertEqual(SERVER.normalize_hex_id("0x7b"), "000000000000007b")

    def test_desktop_definitions_are_thin_delegates_and_hash_covers_wire(self) -> None:
        source = SERVER_PATH.read_text(encoding="utf-8")
        manifest = source_manifest(ROOT / "shared_core")

        self.assertIn("return shared_encode_utf(s)", source)
        self.assertIn("return shared_parse_response(data, RESPONSE_OBFUSCATION_KEY)", source)
        self.assertIn("return shared_normalize_hex_id(id_value)", source)
        self.assertIn("python/dwpm_core/protocol/wire.py", manifest["files"])
        self.assertIn("python/dwpm_core/protocol/__init__.py", manifest["files"])


if __name__ == "__main__":
    unittest.main()
