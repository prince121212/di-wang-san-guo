from __future__ import annotations

import importlib.util
import json
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = ROOT / "shared_core" / "python"
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
FIXTURE_PATH = ROOT / "shared_core" / "protocol_parity_fixtures.json"
if str(CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CORE_SOURCE))

from dwpm_core.features.formation import (
    build_assign_troops_payload,
    build_heal_all_payloads,
    build_refill_payload,
    parse_assign_troops_response,
    parse_heal_preinfo_response,
    parse_heal_response,
    parse_refill_response,
    soldier_type_code,
    soldier_type_name,
)
from dwpm_core.hashing import source_manifest


SPEC = importlib.util.spec_from_file_location("dwpm_server_formation_parity", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class SharedFormationProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.fixtures = payload["fixtures"]

    def test_assignment_fixture_runs_directly_in_the_shared_core(self) -> None:
        fixture = self.fixtures["formationAssign1226"]
        payload = build_assign_troops_payload(
            f"{fixture['generalId']:016x}",
            fixture["soldierTypeCode"],
            fixture["soldierCount"],
        )
        receipt_bytes = bytes.fromhex(fixture["successResponseHex"])
        shared = parse_assign_troops_response(receipt_bytes)

        self.assertEqual(payload.hex(), fixture["requestPayloadHex"])
        self.assertEqual(
            SERVER.build_assign_troops_payload(
                f"{fixture['generalId']:016x}",
                fixture["soldierTypeCode"],
                fixture["soldierCount"],
            ),
            payload,
        )
        self.assertEqual(SERVER.parse_assign_troops_response(receipt_bytes), shared)
        self.assertTrue(shared["success"])

    def test_refill_fixture_runs_directly_in_the_shared_core(self) -> None:
        fixture = self.fixtures["formationRefill1229"]
        general_ids = [f"{value:016x}" for value in fixture["generalIds"]]
        payload = build_refill_payload(general_ids)
        receipt_bytes = bytes.fromhex(fixture["successResponseHex"])
        shared = parse_refill_response(receipt_bytes)

        self.assertEqual(payload.hex(), fixture["requestPayloadHex"])
        self.assertEqual(SERVER.build_refill_payload(general_ids), payload)
        self.assertEqual(SERVER.parse_refill_response(receipt_bytes), shared)
        self.assertTrue(shared["success"])

    def test_healing_shapes_and_receipts_are_host_independent(self) -> None:
        preflight, action = build_heal_all_payloads(77)
        preflight_response = struct.pack(">qhqq", 77, -1, 12_000, 3)
        action_response = struct.pack(">bqqb", 0, 77, 99, 0)

        self.assertEqual(preflight, struct.pack(">qhi", 77, -1, -1))
        self.assertEqual(action, struct.pack(">qbhib", 77, 2, 0, -1, 0))
        self.assertEqual(SERVER.build_heal_all_payloads(77), (preflight, action))
        self.assertEqual(
            SERVER.parse_heal_preinfo_response(preflight_response),
            parse_heal_preinfo_response(preflight_response),
        )
        self.assertEqual(
            SERVER.parse_heal_response(action_response),
            parse_heal_response(action_response),
        )

    def test_soldier_dictionary_has_one_shared_owner(self) -> None:
        self.assertEqual(soldier_type_code("轻骑兵"), 3)
        self.assertEqual(soldier_type_name(3), "轻骑兵")
        self.assertIs(SERVER.SOLDIER_TYPE_CODES, SERVER.SHARED_SOLDIER_TYPE_CODES)
        self.assertIs(SERVER.SOLDIER_CODE_NAMES, SERVER.SHARED_SOLDIER_CODE_NAMES)
        manifest = source_manifest(ROOT / "shared_core")
        self.assertIn("python/dwpm_core/features/formation.py", manifest["files"])


if __name__ == "__main__":
    unittest.main()
