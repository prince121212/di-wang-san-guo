from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_office_parser_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


def utf(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return len(encoded).to_bytes(2, "big") + encoded


def role_state_head(*, office_id: int, avatar_id: int = 0x84) -> bytes:
    """Build the stable 0x8004 head through the office short field."""
    return b"".join([
        b"\x00\x00",                         # dispatcher/status bytes
        (1_700_000_000_000).to_bytes(8, "big", signed=True),
        (202).to_bytes(8, "big", signed=True),
        utf("利萍丰"),
        b"\x00",                              # flagB
        b"\x57",                              # level 87
        (0).to_bytes(8, "big", signed=True),  # copper
        (0).to_bytes(8, "big", signed=True),  # food
        (0).to_bytes(8, "big", signed=True),  # fieldF
        b"\x00",                              # flagG
        avatar_id.to_bytes(2, "big"),
        b"\x00",                              # flagX
        (0).to_bytes(8, "big", signed=True),  # prestige
        (0).to_bytes(8, "big", signed=True),  # prestige previous
        (0).to_bytes(8, "big", signed=True),  # prestige next
        (0).to_bytes(8, "big", signed=True),  # skipped long
        b"\x00",                              # flagL
        (0).to_bytes(4, "big", signed=True),  # copper/hour
        (0).to_bytes(4, "big", signed=True),  # food/hour
        (0).to_bytes(8, "big", signed=True),  # battle merit
        (0).to_bytes(8, "big", signed=True),  # fieldP
        (0).to_bytes(8, "big", signed=True),  # population current
        (0).to_bytes(8, "big", signed=True),  # population cap
        b"\x04\x08\x01\x02",                 # fief/general/resource limits
        b"\x00",                              # reserved byte before data.i.w
        office_id.to_bytes(2, "big"),
        b"\x99\x88",                          # unrelated tail
    ])


class OfficeParserTests(unittest.TestCase):
    def test_reads_office_after_the_existing_8004_head(self) -> None:
        state = SERVER.parse_8004_head(role_state_head(office_id=0x0383))

        self.assertEqual(state["avatarShortUnsigned"], 0x84)
        self.assertEqual(state["officeId"], 0x0383)
        self.assertEqual(state["officeIdUnsigned"], 0x0383)
        self.assertEqual(state["officeName"], "抚远将军")
        self.assertEqual(state["level"], 87)

    def test_maps_the_test_account_office_ranges(self) -> None:
        expected = {
            0x0100: "国民",
            0x0202: "侍郎",
            0x0203: "侍郎",
            0x0205: "侍郎",
            0x0382: "奋武将军",
            0x0500: "国王",
        }
        for office_id, name in expected.items():
            with self.subTest(office_id=hex(office_id)):
                self.assertEqual(SERVER.office_name_from_id(office_id), name)

    def test_keeps_legacy_avatar_alias_and_handles_missing_office_tail(self) -> None:
        payload = role_state_head(office_id=0x0100)
        state = SERVER.parse_8004_head(payload[:-4])

        self.assertEqual(state["officeIdRaw"], None)
        self.assertEqual(state["officeName"], "")
        self.assertEqual(state["officeShortUnsigned"], state["avatarShortUnsigned"])


if __name__ == "__main__":
    unittest.main()
