from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Mapping

from shared_raw_http_test_host import _decode_request_commands, _encode_response


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location(
    "dwpm_server_shared_dungeon_test",
    SERVER_PATH,
)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)

FIXTURES = json.loads(
    (ROOT / "shared_core" / "protocol_parity_fixtures.json").read_text(
        encoding="utf-8"
    )
)["fixtures"]


def launch_marker_payload() -> bytes:
    encoded = "单人副本启动成功！".encode("utf-8")
    return len(encoded).to_bytes(2, "big") + encoded


class StaticSessionSecrets:
    def save(self, _account_ref: str, _values: Mapping[str, str]) -> None:
        return None

    def load(self, _account_ref: str) -> Mapping[str, str]:
        return {"dm": "303"}

    def delete(self, _account_ref: str) -> None:
        return None


class DungeonRawHttpFixture:
    def __init__(self) -> None:
        self.commands: list[tuple[int, bytes]] = []

    def exchange(self, request: Mapping[str, object]) -> Mapping[str, object]:
        commands = _decode_request_commands(bytes(request.get("body") or b""))
        if len(commands) != 1:
            raise AssertionError(f"expected one command, got {len(commands)}")
        self.commands.extend(commands)
        opcode, _payload = commands[0]
        responses = {
            0x1938: (0x8938, b"\x00"),
            0x1930: (
                0x8930,
                bytes.fromhex(
                    FIXTURES["dungeonCatalog8930"]["responseHex"]
                ),
            ),
            0x1520: (0x8520, b""),
            0x1522: (0x8522, launch_marker_payload()),
        }
        if opcode not in responses:
            raise AssertionError(f"unexpected shared dungeon opcode {opcode:#x}")
        response_opcode, response_payload = responses[opcode]
        return {
            "status": 200,
            "body": _encode_response([{
                "opcode": response_opcode,
                "payloadHex": response_payload.hex(),
            }]),
            "headers": {},
        }


class DesktopSharedDungeonOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.old_core = SERVER.SHARED_PYTHON_CORE
        self.old_sessions = SERVER.SESSIONS
        self.old_accounts = SERVER.ACCOUNTS
        self.old_habits_loader = SERVER.load_account_habits
        self.account_ref = "desktop-dungeon-fixture"
        self.session = {
            "sessionId": self.account_ref,
            "username": "offline-dungeon-fixture",
            "gameHttp": "https://fixture.invalid/kingWapServer/HttpClient",
            "dm": 303,
            "platform": "sglm",
            "platformKey": "sglm",
            "area": {"areaName": "离线测试区"},
            "role": {"roleId": 303, "roleName": "离线角色", "level": 87},
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
        self.raw_http = DungeonRawHttpFixture()
        SERVER.SHARED_PYTHON_CORE = SERVER.CoreFacade(
            ROOT / "shared_core",
            str(Path(self.directory.name) / "operations.json"),
            ports=SERVER.create_desktop_platform_ports(
                Path(self.directory.name),
                session_secrets=StaticSessionSecrets(),
                raw_http=self.raw_http,
            ),
        )
        SERVER.SHARED_PYTHON_CORE.register_dungeon_action_runner()
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

    def test_desktop_tick_uses_shared_raw_dungeon_workflow(self) -> None:
        result = SERVER.execute_dungeon_tick(
            self.session,
            {
                "generalIds": ["7"],
                "chapter": 0,
                "chapterName": "第一章",
                "stage": 3,
                "chest": 2,
                "fullTroops": False,
            },
            mode="loop",
        )

        self.assertTrue(result["dispatchAccepted"])
        self.assertEqual(result["stage"]["stageCode"], 2)
        self.assertEqual(
            [opcode for opcode, _payload in self.raw_http.commands],
            [0x1938, 0x1930, 0x1520, 0x1522],
        )
        self.assertEqual(
            self.raw_http.commands[-2][1],
            SERVER.build_dungeon_prepare_payload(
                ["0000000000000007"], 2
            ),
        )
        self.assertEqual(
            self.raw_http.commands[-1][1],
            SERVER.build_dungeon_expedition_payload(
                ["0000000000000007"], 2
            ),
        )


if __name__ == "__main__":
    unittest.main()
