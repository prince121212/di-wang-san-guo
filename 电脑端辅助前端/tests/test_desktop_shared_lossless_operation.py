from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Mapping

from shared_raw_http_test_host import (
    _decode_request_commands,
    _encode_response,
)


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location(
    "dwpm_server_shared_lossless_test",
    SERVER_PATH,
)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)

CAPTURE_FLOWS = (
    ROOT
    / "电脑端辅助前端"
    / "tests"
    / "fixtures"
    / "game_packets"
    / "passive_pcap_hotspot_20260710_185601"
    / "live_analyzed"
)


def capture_payload(flow_index: int, opcode: int) -> bytes:
    packets = SERVER.parse_response(
        (CAPTURE_FLOWS / f"{flow_index:03d}" / "resp.bin").read_bytes()
    )
    return next(
        packet["payload"]
        for packet in packets
        if packet.get("opcode") == opcode
    )


class StaticSessionSecrets:
    def save(self, _account_ref: str, _values: Mapping[str, str]) -> None:
        return None

    def load(self, _account_ref: str) -> Mapping[str, str]:
        return {"dm": "202"}

    def delete(self, _account_ref: str) -> None:
        return None


class LosslessRawHttpFixture:
    def __init__(self) -> None:
        self.commands: list[tuple[int, bytes]] = []

    def exchange(self, request: Mapping[str, object]) -> Mapping[str, object]:
        commands = _decode_request_commands(bytes(request.get("body") or b""))
        self.commands.extend(commands)
        self.assert_single(commands)
        opcode, _payload = commands[0]
        responses = {
            0x1900: (0x8900, capture_payload(84, 0x8900)),
            0x1904: (0x8904, capture_payload(85, 0x8904)),
            0x1906: (0x8906, capture_payload(86, 0x8906)),
            0x1520: (0x8520, b""),
            0x1522: (0x8522, bytes.fromhex("00000000000000006c42d1")),
        }
        if opcode not in responses:
            raise AssertionError(f"unexpected shared lossless opcode {opcode:#x}")
        response_opcode, response_payload = responses[opcode]
        return {
            "status": 200,
            "body": _encode_response([{
                "opcode": response_opcode,
                "payloadHex": response_payload.hex(),
            }]),
            "headers": {},
        }

    @staticmethod
    def assert_single(commands: list[tuple[int, bytes]]) -> None:
        if len(commands) != 1:
            raise AssertionError(f"expected one command, got {len(commands)}")


class DesktopSharedLosslessOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.old_core = SERVER.SHARED_PYTHON_CORE
        self.old_sessions = SERVER.SESSIONS
        self.old_accounts = SERVER.ACCOUNTS
        self.old_habits_loader = SERVER.load_account_habits
        self.account_ref = "desktop-lossless-fixture"
        self.session = {
            "sessionId": self.account_ref,
            "username": "offline-lossless-fixture",
            "gameHttp": "https://fixture.invalid/kingWapServer/HttpClient",
            "dm": 202,
            "platform": "sglm",
            "platformKey": "sglm",
            "area": {"areaName": "离线测试区"},
            "role": {"roleId": 202, "roleName": "离线角色", "level": 87},
            "generals": [],
            "army": [],
            "inventory": {},
        }
        SERVER.SESSIONS = {self.account_ref: self.session}
        SERVER.ACCOUNTS = {
            self.account_ref: {
                "sessionId": self.account_ref,
                "started": True,
                "status": "online",
                "session": self.session,
            }
        }
        SERVER.load_account_habits = lambda _session: {
            "config": {"healWounded": False, "autoEnergy": False},
            "formations": [{
                "generalIds": ["7"],
                "soldierType": "轻骑兵",
                "soldierCount": 100,
            }],
        }
        self.raw_http = LosslessRawHttpFixture()
        SERVER.SHARED_PYTHON_CORE = SERVER.CoreFacade(
            ROOT / "shared_core",
            str(Path(self.directory.name) / "operations.json"),
            ports=SERVER.create_desktop_platform_ports(
                Path(self.directory.name),
                session_secrets=StaticSessionSecrets(),
                raw_http=self.raw_http,
            ),
        )
        SERVER.SHARED_PYTHON_CORE.register_lossless_action_runner()
        selected = [{
            "id": 7,
            "idHex": "0000000000000007",
            "name": "赵云",
            "status": 0,
            "statusText": "闲",
            "displayStatus": "闲",
            "energyReliable": True,
            "tili": 300,
            "soldierTypeCode": 3,
            "soldierCount": 100,
            "currentSoldierCount": 100,
        }]
        SERVER.SHARED_PYTHON_CORE._run_expedition_preflight = types.MethodType(
            lambda _self, *_args, **_kwargs: (
                [dict(row) for row in selected],
                {"generalIds": [7]},
            ),
            SERVER.SHARED_PYTHON_CORE,
        )

    def tearDown(self) -> None:
        SERVER.SHARED_PYTHON_CORE.close()
        SERVER.SHARED_PYTHON_CORE = self.old_core
        SERVER.SESSIONS = self.old_sessions
        SERVER.ACCOUNTS = self.old_accounts
        SERVER.load_account_habits = self.old_habits_loader
        SERVER._desktop_delete_shared_session_secrets(self.account_ref)
        self.directory.cleanup()

    def test_desktop_tick_uses_shared_raw_lossless_workflow(self) -> None:
        result = SERVER.execute_lossless_tick(
            self.session,
            {
                "generalIds": ["7"],
                "level": 10,
                "fullTroops": False,
                "maxLineupRerolls": 3,
            },
        )

        self.assertTrue(result["dispatchAccepted"])
        self.assertEqual(result["battleId"], 7094993)
        self.assertEqual(
            [opcode for opcode, _payload in self.raw_http.commands],
            [0x1900, 0x1904, 0x1906, 0x1520, 0x1522],
        )
        self.assertEqual(
            self.raw_http.commands[-2][1],
            SERVER.build_lossless_prepare_payload(
                ["0000000000000007"], 202
            ),
        )
        self.assertEqual(
            self.raw_http.commands[-1][1],
            SERVER.build_lossless_expedition_payload(
                ["0000000000000007"], 202
            ),
        )


if __name__ == "__main__":
    unittest.main()
