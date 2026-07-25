from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_general_parser_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


def general_record(general_id: int, name: str, energy: int) -> bytes:
    body = bytearray(114)
    body[0x03] = 0  # 步将
    body[0x06:0x08] = (59).to_bytes(2, "big")
    body[0x08] = 42
    body[0x1B:0x1D] = energy.to_bytes(2, "big")
    body[0x1D:0x1F] = energy.to_bytes(2, "big")
    body[0x23:0x27] = (1154).to_bytes(4, "big")
    body[0x27] = 60
    body[0x28] = 100
    body[0x56] = 0
    body[0x58] = 0
    body[0x70:0x72] = b"\xff\xff"
    encoded_name = name.encode("utf-8")
    return (
        general_id.to_bytes(8, "big")
        + len(encoded_name).to_bytes(2, "big")
        + encoded_name
        + body
    )


class GeneralParserTests(unittest.TestCase):
    def test_renaming_a_general_keeps_the_same_stable_id(self) -> None:
        before = SERVER.recover_generals_from_8004(
            general_record(446074, "统弓1", 305).hex()
        )
        after = SERVER.recover_generals_from_8004(
            general_record(446074, "A-1 统弓", 305).hex()
        )

        self.assertEqual([(row["id"], row["name"]) for row in before], [(446074, "统弓1")])
        self.assertEqual([(row["id"], row["name"]) for row in after], [(446074, "A-1 统弓")])

    def test_name_format_is_not_used_as_general_identity_validation(self) -> None:
        payload = general_record(446076, "★弓·2★", 305)
        generals = SERVER.recover_generals_from_8004(payload.hex())

        self.assertEqual(len(generals), 1)
        self.assertEqual(generals[0]["id"], 446076)
        self.assertEqual(generals[0]["name"], "★弓·2★")

    def test_accepts_live_energy_limit_above_300(self) -> None:
        payload = general_record(528290, "步2", 305)
        generals = SERVER.recover_generals_from_8004(payload.hex())

        self.assertEqual(len(generals), 1)
        self.assertEqual(generals[0]["id"], 528290)
        self.assertEqual(generals[0]["name"], "步2")
        self.assertEqual(generals[0]["tili"], 305)
        self.assertEqual(generals[0]["tiliLimit"], 305)

    def test_accepts_the_full_unsigned_short_energy_range(self) -> None:
        payload = general_record(528291, "步3", 5000)
        generals = SERVER.recover_generals_from_8004(payload.hex())

        self.assertEqual(len(generals), 1)
        self.assertEqual(generals[0]["tili"], 5000)
        self.assertEqual(generals[0]["tiliLimit"], 5000)
