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

from dwpm_core.account import (
    area_catalog_signature,
    find_login_area,
    parse_8003_login,
    parse_passport_area_list,
)
from dwpm_core.hashing import source_manifest


SPEC = importlib.util.spec_from_file_location(
    "dwpm_server_account_shared_parity",
    SERVER_PATH,
)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class SharedAccountProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.fixtures = payload["fixtures"]

    def test_8003_login_response_runs_in_shared_core(self) -> None:
        fixture = self.fixtures["accountLogin8003"]
        payload = bytes.fromhex(fixture["responseHex"])
        parsed = parse_8003_login(payload)
        self.assertEqual(SERVER.parse8003(payload), parsed)
        expected = fixture["expected"]
        for key in (
            "status",
            "message",
            "dm",
            "loginTime",
            "selected",
            "trailingBytes",
        ):
            self.assertEqual(parsed[key], expected[key])
        self.assertEqual(len(parsed["roles"]), expected["roleCount"])
        first = parsed["roles"][0]
        self.assertEqual(first["roleId"], expected["firstRoleId"])
        self.assertEqual(first["roleName"], expected["firstRoleName"])
        self.assertEqual(first["level"], expected["firstRoleLevel"])

    def test_passport_area_parsing_and_selection_run_in_shared_core(self) -> None:
        fixture = self.fixtures["accountPassportAreas"]
        parsed = parse_passport_area_list(fixture["responseText"])
        self.assertEqual(SERVER.parse_passport_area_list(fixture["responseText"]), parsed)
        session, user_id, areas = parsed
        expected = fixture["expected"]
        self.assertEqual(session, expected["session"])
        self.assertEqual(user_id, expected["userId"])
        self.assertEqual(len(areas), expected["areaCount"])
        self.assertEqual(areas[0]["areaId"], expected["firstAreaId"])
        self.assertEqual(areas[0]["areaName"], expected["firstAreaName"])
        for query in fixture["queries"]:
            selected = find_login_area(areas, query["query"])
            with self.subTest(query=query["query"]):
                self.assertIsNotNone(selected)
                self.assertEqual(
                    selected["serverKey"],
                    query["expectedServerKey"],
                )
                self.assertEqual(
                    SERVER.find_login_area(areas, query["query"]),
                    selected,
                )

    def test_area_signature_is_order_independent_and_shared(self) -> None:
        _, _, areas = parse_passport_area_list(
            self.fixtures["accountPassportAreas"]["responseText"]
        )
        signature = area_catalog_signature(areas)
        self.assertEqual(signature, area_catalog_signature(list(reversed(areas))))
        self.assertEqual(SERVER.area_catalog_signature(areas), signature)

    def test_malformed_login_and_passport_responses_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            parse_8003_login(b"\x00")
        with self.assertRaisesRegex(RuntimeError, "passport"):
            parse_passport_area_list("bad response")

    def test_account_sources_are_in_cross_platform_hash(self) -> None:
        manifest = source_manifest(ROOT / "shared_core")
        self.assertIn("python/dwpm_core/account/__init__.py", manifest["files"])
        self.assertIn("python/dwpm_core/account/protocol.py", manifest["files"])


if __name__ == "__main__":
    unittest.main()
