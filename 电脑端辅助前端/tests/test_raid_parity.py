from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Mapping

from shared_raw_http_test_host import _decode_single_request, _encode_response


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_raid_parity_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class StaticSessionSecretPort:
    def save(self, _account_ref: str, _values: Mapping[str, str]) -> None:
        return None

    def load(self, _account_ref: str) -> Mapping[str, str]:
        return {"dm": "7"}

    def delete(self, _account_ref: str) -> None:
        return None


class RaidRawHttpFixture:
    """Offline byte transport for the Python-owned raid workflow."""

    def __init__(self) -> None:
        self.mode = "confirmed"
        self.commands: list[tuple[int, bytes]] = []

    def exchange(self, request: Mapping[str, object]) -> Mapping[str, object]:
        opcode, payload = _decode_single_request(bytes(request.get("body") or b""))
        self.commands.append((opcode, payload))
        packets: list[dict[str, object]]
        if opcode == 0x1520:
            packets = [] if self.mode == "missing-prepare" else [{
                "opcode": 0x8520,
                "payloadHex": (
                    "0000003c000000000000000000000000000000006400120016"
                ),
            }]
        elif opcode == 0x1522:
            packets = [{
                "opcode": 0x8522,
                "payloadHex": "00000000000000006c42d1",
            }]
        else:
            raise AssertionError(f"unexpected raid opcode {opcode:#x}")
        return {
            "status": 200,
            "body": _encode_response(packets),
            "headers": {},
        }


class RaidPrepareParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.old_core = SERVER.SHARED_PYTHON_CORE
        self.old_sessions = SERVER.SESSIONS
        self.old_accounts = SERVER.ACCOUNTS
        self.session = {
            "sessionId": "raid-test",
            "username": "offline-raid-fixture",
            "gameHttp": "https://fixture.invalid/kingWapServer/HttpClient",
            "dm": 7,
            "role": {"roleId": 202, "roleName": "测试角色"},
            "area": {"areaName": "测试区"},
            "platform": "sglm",
            "platformKey": "sglm",
            "generals": [],
            "army": [],
            "inventory": {},
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
            "ok": True,
            "fiefs": [{
                "index": 1,
                "targetId": 101,
                "fiefName": "一号封地",
                "name": "一号封地",
                "x": 18,
                "y": 22,
            }],
        }
        self.generals = [{
            "id": 1,
            "idHex": "0000000000000001",
            "name": "测试将领",
            "status": 0,
            "statusText": "闲",
            "displayStatus": "闲",
            "energyReliable": True,
            "tili": 300,
            "loyalty": 100,
            "soldierTypeCode": 3,
            "soldierCount": 100,
            "currentSoldierCount": 100,
        }]
        SERVER.SESSIONS = {"raid-test": self.session}
        SERVER.ACCOUNTS = {}
        self.raw_http = RaidRawHttpFixture()
        SERVER.SHARED_PYTHON_CORE = SERVER.CoreFacade(
            ROOT / "shared_core",
            str(Path(self.directory.name) / "operations.json"),
            ports=SERVER.create_desktop_platform_ports(
                Path(self.directory.name),
                session_secrets=StaticSessionSecretPort(),
                raw_http=self.raw_http,
            ),
        )
        SERVER.SHARED_PYTHON_CORE.register_raid_action_runner()
        SERVER.SHARED_PYTHON_CORE._run_raid_fiefs_game_workflow = types.MethodType(
            lambda _self, *_args, **_kwargs: dict(self.fiefs),
            SERVER.SHARED_PYTHON_CORE,
        )
        SERVER.SHARED_PYTHON_CORE._run_expedition_preflight = types.MethodType(
            lambda _self, *_args, **_kwargs: (
                [dict(row) for row in self.generals],
                {"generalIds": [1]},
            ),
            SERVER.SHARED_PYTHON_CORE,
        )

    def tearDown(self) -> None:
        SERVER.SHARED_PYTHON_CORE.close()
        SERVER.SHARED_PYTHON_CORE = self.old_core
        SERVER.SESSIONS = self.old_sessions
        SERVER.ACCOUNTS = self.old_accounts
        SERVER._desktop_delete_shared_session_secrets("raid-test")
        self.directory.cleanup()

    def test_missing_8520_stops_before_1522(self) -> None:
        self.raw_http.mode = "missing-prepare"

        with self.assertRaisesRegex(RuntimeError, "已禁止发送正式出征"):
            SERVER.execute_raid(self.session, self.options)

        self.assertEqual(
            [opcode for opcode, _payload in self.raw_http.commands],
            [0x1520],
        )

    def test_confirmed_8520_allows_1522_and_requires_positive_battle_id(self) -> None:
        result = SERVER.execute_raid(self.session, self.options)

        self.assertEqual(
            [opcode for opcode, _payload in self.raw_http.commands],
            [0x1520, 0x1522],
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["successBattleId"], 7094993)


if __name__ == "__main__":
    unittest.main()
