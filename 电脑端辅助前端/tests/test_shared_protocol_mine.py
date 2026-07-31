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

from dwpm_core.features.expedition import parse_dispatch_response
from dwpm_core.features.mine import (
    build_march_speed_payload,
    build_recall_payload,
    choose_march_speed_items,
    parse_march_speed_response,
    parse_mine_preview,
    parse_recall_response,
)


SPEC = importlib.util.spec_from_file_location("dwpm_server_mine_parity", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class SharedMineProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.fixtures = payload["fixtures"]

    def test_preview_and_dispatch_receipts_run_in_shared_core(self) -> None:
        preview_fixture = self.fixtures["minePreview8520"]
        preview_bytes = bytes.fromhex(preview_fixture["responseHex"])
        shared_preview = parse_mine_preview(preview_bytes)

        self.assertEqual(SERVER.parse_8520_mine_preview(preview_bytes), shared_preview)
        for key in ("marchSeconds", "winRate", "x", "y"):
            self.assertEqual(shared_preview[key], preview_fixture["expected"][key])

        dispatch_fixture = self.fixtures["brushYellowDispatchReceipts"]
        success_bytes = bytes.fromhex(dispatch_fixture["successResponseHex"])
        reject_bytes = bytes.fromhex(dispatch_fixture["softRejectResponseHex"])
        self.assertEqual(SERVER.parse_8522_dispatch_response(success_bytes), parse_dispatch_response(success_bytes))
        self.assertEqual(SERVER.parse_8522_dispatch_response(reject_bytes), parse_dispatch_response(reject_bytes))
        self.assertTrue(parse_dispatch_response(success_bytes)["success"])
        self.assertFalse(parse_dispatch_response(reject_bytes)["success"])

    def test_recall_request_and_receipts_run_in_shared_core(self) -> None:
        fixture = self.fixtures["mineWithdraw8526"]
        battle_id = fixture["battleId"]

        self.assertEqual(build_recall_payload(battle_id).hex(), fixture["requestPayloadHex"])
        self.assertEqual(SERVER.build_mine_recall_payload(battle_id), build_recall_payload(battle_id))
        for response_name in ("successResponseHex", "mismatchedResponseHex"):
            response = bytes.fromhex(fixture[response_name])
            self.assertEqual(
                SERVER.parse_8526_recall_response(response, battle_id),
                parse_recall_response(response, battle_id),
            )
        self.assertTrue(parse_recall_response(bytes.fromhex(fixture["successResponseHex"]), battle_id)["success"])
        self.assertFalse(parse_recall_response(bytes.fromhex(fixture["mismatchedResponseHex"]), battle_id)["success"])

    def test_march_speed_request_receipts_and_selection_run_in_shared_core(self) -> None:
        protocol = self.fixtures["mineMarchSpeed8524"]
        smart = self.fixtures["mineSmartSpeed"]

        payload = build_march_speed_payload(protocol["battleId"], protocol["itemId"])
        self.assertEqual(payload.hex(), protocol["requestPayloadHex"])
        self.assertEqual(SERVER.build_mine_speed_payload(protocol["battleId"], protocol["itemId"]), payload)
        for response_name in ("successResponseHex", "finishedResponseHex"):
            response = bytes.fromhex(protocol[response_name])
            self.assertEqual(
                SERVER.parse_8524_mine_speed_response(response),
                parse_march_speed_response(response),
            )
        selected = choose_march_speed_items(
            smart["remainingSeconds"],
            smart["inventory"],
        )
        self.assertEqual(selected, smart["expectedItemIds"])
        self.assertEqual(
            SERVER.choose_march_speed_items(smart["remainingSeconds"], smart["inventory"]),
            selected,
        )


if __name__ == "__main__":
    unittest.main()
