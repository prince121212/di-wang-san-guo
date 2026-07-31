from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_raid_parity_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class RaidPrepareParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = {
            "sessionId": "raid-test",
            "gameHttp": "https://game.invalid/",
            "dm": 7,
            "role": "测试角色",
            "area": "测试区",
        }
        self.options = {
            "confirm": "raid",
            "playerName": "目标玩家",
            "fiefIndex": 1,
            "generalIds": ["1"],
            "fullTroops": False,
            "fullLoyalty": False,
        }
        self.fiefs = {
            "fiefs": [{
                "index": 1,
                "targetId": 101,
                "fiefName": "一号封地",
                "name": "一号封地",
                "x": 18,
                "y": 22,
            }]
        }
        self.generals = [{
            "id": 1,
            "idHex": "0000000000000001",
            "name": "测试将领",
            "soldierTypeCode": 3,
            "soldierCount": 100,
        }]

    @staticmethod
    def packet(opcode: int, payload: bytes) -> dict:
        return {
            "opcode": opcode,
            "payload": payload,
            "len": len(payload),
            "frag": 0,
        }

    def test_missing_8520_stops_before_1522(self) -> None:
        sent_opcodes: list[int] = []

        def post_game(_url, commands, _dm, **_kwargs):
            sent_opcodes.extend(opcode for opcode, _payload in commands)
            return 200, b"", []

        with patch.object(SERVER, "query_raid_fiefs", return_value=self.fiefs), \
             patch.object(SERVER, "raid_preflight_generals", return_value=self.generals), \
             patch.object(SERVER, "post_game", side_effect=post_game), \
             patch.object(SERVER.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "已禁止发送正式出征"):
                SERVER.execute_raid(self.session, self.options)

        self.assertEqual(sent_opcodes, [SERVER.RAID_PREPARE_OPCODE])

    def test_confirmed_8520_allows_1522_and_requires_positive_battle_id(self) -> None:
        sent_opcodes: list[int] = []
        preview = bytes.fromhex(
            "0000003c000000000000000000000000000000006400120016"
        )
        receipt = bytes.fromhex("00000000000000006c42d1")

        def post_game(_url, commands, _dm, **_kwargs):
            opcode = commands[0][0]
            sent_opcodes.append(opcode)
            if opcode == SERVER.RAID_PREPARE_OPCODE:
                packet = self.packet(SERVER.RAID_PREPARE_RESPONSE_OPCODE, preview)
            else:
                packet = self.packet(SERVER.RAID_DISPATCH_RESPONSE_OPCODE, receipt)
            return 200, packet["payload"], [packet]

        with patch.object(SERVER, "query_raid_fiefs", return_value=self.fiefs), \
             patch.object(SERVER, "raid_preflight_generals", return_value=self.generals), \
             patch.object(SERVER, "post_game", side_effect=post_game), \
             patch.object(SERVER, "refresh_generals"), \
             patch.object(SERVER, "refresh_military_intel"), \
             patch.object(SERVER.time, "sleep"):
            result = SERVER.execute_raid(self.session, self.options)

        self.assertEqual(
            sent_opcodes,
            [SERVER.RAID_PREPARE_OPCODE, SERVER.RAID_DISPATCH_OPCODE],
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["successBattleId"], 7094993)


if __name__ == "__main__":
    unittest.main()
