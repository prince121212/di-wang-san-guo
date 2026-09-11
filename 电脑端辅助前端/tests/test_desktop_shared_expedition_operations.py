from __future__ import annotations

import importlib.util
import json
import struct
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location(
    "dwpm_server_shared_expedition_test",
    SERVER_PATH,
)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class DesktopSharedExpeditionOperationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixtures = json.loads(
            (ROOT / "shared_core" / "protocol_parity_fixtures.json").read_text(
                encoding="utf-8"
            )
        )["fixtures"]

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.old_core = SERVER.SHARED_PYTHON_CORE
        self.old_sessions = SERVER.SESSIONS
        self.old_accounts = SERVER.ACCOUNTS
        self.old_post_game = SERVER.post_game
        self.old_habits_loader = SERVER.load_account_habits
        self.old_auto_tasks = SERVER.AUTO_TASKS
        self.commands: list[dict[str, object]] = []
        self.mode = "brush-success"
        self.account_ref = "desktop-expedition-fixture"
        SERVER.SESSIONS = {
            self.account_ref: {
                "sessionId": self.account_ref,
                "username": "offline-fixture",
                "gameHttp": "http://offline-fixture.invalid/game",
                "dm": 202,
                "platform": "fixture",
                "platformKey": "fixture",
                "area": {"areaName": "离线测试区"},
                "role": {"roleId": 202, "roleName": "离线角色", "level": 87},
                "roleState": {"resourcePointCurrent": 0, "resourcePointCap": 2},
                "generals": [],
                "army": [],
                "inventory": {},
            }
        }
        SERVER.ACCOUNTS = {
            self.account_ref: {
                "sessionId": self.account_ref,
                "started": True,
                "status": "online",
                "session": SERVER.SESSIONS[self.account_ref],
            }
        }
        SERVER.AUTO_TASKS = {}
        SERVER.load_account_habits = lambda _session: {
            "config": {
                "healWounded": False,
                "autoEnergy": False,
                "energyThreshold": 20,
            },
            "formations": [
                {
                    "generalIds": ["1", "2"],
                    "soldierType": "轻骑兵",
                    "soldierCount": 120,
                }
            ],
        }
        SERVER.post_game = self._fake_post_game
        operation_path = Path(self.directory.name) / "operations.json"
        SERVER.SHARED_PYTHON_CORE = SERVER.CoreFacade(
            ROOT / "shared_core",
            str(operation_path),
            ports=SERVER.create_desktop_platform_ports(
                Path(self.directory.name),
                game_commands=SERVER.DesktopGameCommandPort(
                    SERVER._desktop_shared_game_command
                ),
            ),
        )
        SERVER._register_desktop_shared_expedition_routes()
        self._install_formation_state((1, 2))

    def tearDown(self) -> None:
        SERVER.SHARED_PYTHON_CORE.close()
        SERVER.SHARED_PYTHON_CORE = self.old_core
        SERVER.SESSIONS = self.old_sessions
        SERVER.ACCOUNTS = self.old_accounts
        SERVER.post_game = self.old_post_game
        SERVER.load_account_habits = self.old_habits_loader
        SERVER.AUTO_TASKS = self.old_auto_tasks
        self.directory.cleanup()

    def _fake_post_game(
        self,
        game_http,
        commands,
        dm,
        *,
        account_id,
        noncritical,
        platform,
    ):
        self.assertEqual(game_http, "http://offline-fixture.invalid/game")
        self.assertEqual(dm, 202)
        self.assertEqual(account_id, self.account_ref)
        self.assertEqual(platform, "fixture")
        self.assertEqual(len(commands), 1)
        opcode, payload = commands[0]
        self.commands.append({
            "opcode": int(opcode),
            "payload": bytes(payload),
            "noncritical": bool(noncritical),
        })
        if self.mode == "brush-success":
            if int(opcode) == 0x1522:
                packets = [{
                    "opcode": 0x8522,
                    "payload": bytes.fromhex(
                        self.fixtures["brushYellowDispatchReceipts"][
                            "successResponseHex"
                        ]
                    ),
                }]
            else:
                packets = [{"opcode": 0x8520, "payload": b""}]
        elif self.mode == "inventory-success":
            if int(opcode) == 0x1104:
                inventory_payload = (
                    b"\x00" * 14
                    + struct.pack(">HH", 40, 2)
                    + struct.pack(">HH", 58, 3) + b"\x00" * 8
                    + struct.pack(">HH", 59, 1) + b"\x00" * 8
                    + b"\x00\x00"
                )
                packets = [{"opcode": 0x8104, "payload": inventory_payload}]
            elif int(opcode) == 0x3144:
                message = "<br/>铜钱+1000;".encode("utf-8")
                packets = [{
                    "opcode": 0xA144,
                    "payload": struct.pack(">bH", 0, len(message)) + message,
                }]
            else:
                raise AssertionError(f"unexpected inventory opcode {int(opcode):#x}")
        elif self.mode == "hubu-query":
            self.assertEqual(int(opcode), 0x6320)
            packets = [{
                "opcode": 0xE320,
                "payload": bytes.fromhex(
                    self.fixtures["ministryHubuVerifiedPlant"][
                        "emptyGardenResponseHex"
                    ]
                ),
            }]
        elif self.mode == "formation-apply":
            self.assertEqual(int(opcode), 0x1226)
            general_id, _group, soldier_code, target_count = struct.unpack(
                ">qbhi", bytes(payload)
            )
            response = struct.pack(
                ">bqhhhh",
                1,
                general_id,
                soldier_code,
                120,
                soldier_code,
                target_count,
            )
            packets = [{"opcode": 0x8226, "payload": response}]
        elif int(opcode) == 0x1520:
            packets = [{
                "opcode": 0x8520,
                "payload": bytes.fromhex(
                    self.fixtures["minePreview8520"]["responseHex"]
                ),
            }]
        else:
            packets = [{"opcode": 0x8004, "payload": b"\x00"}]
        return 200, b"", packets

    def _install_formation_state(self, general_ids: tuple[int, ...]) -> None:
        state_hex = (
            self.fixtures["roleHead8004"]["responseHex"]
            + self.fixtures["generalRecord8004"]["responseHex"]
            + self.fixtures["idleArmy8004"]["responseHex"]
        )
        rows = [
            {
                "id": general_id,
                "idHex": f"{general_id:016x}",
                "name": f"将领{general_id}",
                "status": 0,
                "statusText": "闲",
                "displayStatus": "闲",
                "energyReliable": True,
                "tili": 305,
                "tiliLimit": 305,
                "loyalty": 100,
                "loyaltyLimit": 100,
                "troopLimit": 1200,
                "soldierTypeCode": 3,
                "soldierCount": 120,
                "currentSoldierCount": 120,
            }
            for general_id in general_ids
        ]
        army = [{"soldierTypeCode": 3, "idleCount": 120}]
        SERVER.SHARED_PYTHON_CORE._fresh_formation_state = types.MethodType(
            lambda _self, _account_ref, _context, read_only=False: (
                state_hex,
                [dict(row) for row in rows],
                [dict(row) for row in army],
            ),
            SERVER.SHARED_PYTHON_CORE,
        )

    @staticmethod
    def _wait(facade, operation_id: str) -> dict[str, object]:
        for _ in range(400):
            operation = facade.operation_status(operation_id)["operation"]
            if operation["status"] not in {"QUEUED", "RUNNING"}:
                return operation
            time.sleep(0.005)
        raise AssertionError(f"operation did not finish: {operation_id}")

    def test_desktop_brush_route_uses_shared_workflow_and_exact_fixture_bytes(
        self,
    ) -> None:
        target = {"id": 101, "x": 18, "y": 22, "type": "山贼", "kind": "山贼"}
        accepted = SERVER.SHARED_PYTHON_CORE.dispatch(
            "POST",
            "/api/brush/execute",
            {
                "sessionId": self.account_ref,
                "confirm": "brush-yellow",
                "generalIds": ["1", "2"],
                "target": target,
            },
            {"requestId": "desktop-brush-fixture", "platform": "desktop"},
        )

        self.assertEqual(accepted.status, 202)
        operation = self._wait(
            SERVER.SHARED_PYTHON_CORE,
            str(accepted.body["operationId"]),
        )
        self.assertEqual(operation["status"], "SUCCEEDED", operation)
        result = operation["result"]["result"]
        self.assertEqual(
            result["successBattleId"],
            self.fixtures["brushYellowDispatchReceipts"]["expectedBattleId"],
        )
        variant = SERVER.shared_build_brush_payloads_variant(
            [f"{value:016x}" for value in (1, 2)],
            "0000000000000065",
            variant=0,
        )
        self.assertEqual(
            [row["opcode"] for row in self.commands],
            [0x1520, 0x1522],
        )
        self.assertEqual(
            [row["payload"].hex() for row in self.commands],
            [
                SERVER.shared_action_gamehex_to_cmd(variant["prepare"])[2].hex(),
                SERVER.shared_action_gamehex_to_cmd(variant["expedition"])[2].hex(),
            ],
        )

    def test_desktop_mine_route_uses_same_uncertain_boundary_as_android(self) -> None:
        self.mode = "mine-missing-dispatch-receipt"
        self.commands.clear()
        self._install_formation_state((1,))
        accepted = SERVER.SHARED_PYTHON_CORE.dispatch(
            "POST",
            "/api/mine/execute",
            {
                "sessionId": self.account_ref,
                "confirm": "mine",
                "generalIds": ["1"],
                "target": {
                    "id": 101,
                    "x": 18,
                    "y": 22,
                    "type": "牧场",
                    "kind": "牧场",
                    "playerOccupied": False,
                },
                "maxMarchMinutes": 45,
                "fullLoyalty": False,
            },
            {"requestId": "desktop-mine-fixture", "platform": "desktop"},
        )

        self.assertEqual(accepted.status, 202)
        operation = self._wait(
            SERVER.SHARED_PYTHON_CORE,
            str(accepted.body["operationId"]),
        )
        self.assertEqual(operation["status"], "UNCERTAIN", operation)
        self.assertTrue(operation["requestSent"])
        self.assertEqual(operation["error"]["code"], "UNCERTAIN")
        self.assertEqual(
            [row["opcode"] for row in self.commands],
            [0x1520, 0x1522],
        )

    def test_desktop_inventory_route_uses_shared_preflight_and_receipt_parser(
        self,
    ) -> None:
        self.mode = "inventory-success"
        self.commands.clear()
        accepted = SERVER.SHARED_PYTHON_CORE.dispatch(
            "POST",
            "/api/inventory/open-one",
            {
                "sessionId": self.account_ref,
                "confirm": "open-one",
                "itemName": "青铜宝箱",
            },
            {"requestId": "desktop-inventory-fixture", "platform": "desktop"},
        )

        self.assertEqual(accepted.status, 202)
        operation = self._wait(
            SERVER.SHARED_PYTHON_CORE,
            str(accepted.body["operationId"]),
        )
        self.assertEqual(operation["status"], "SUCCEEDED", operation)
        self.assertTrue(operation["requestSent"])
        self.assertTrue(operation["result"]["result"]["success"])
        self.assertEqual(
            [row["opcode"] for row in self.commands],
            [0x1104, 0x3144, 0x1104],
        )
        self.assertEqual(self.commands[1]["payload"].hex(), "003a0001")

    def test_desktop_task_stop_removes_only_its_shared_activation_key(self) -> None:
        brush_stop = threading.Event()
        mine_stop = threading.Event()
        SERVER.AUTO_TASKS = {
            "brush": {
                "taskId": "brush",
                "type": "auto-brush-yellow",
                "sessionId": self.account_ref,
                "status": "running",
                "stopEvent": brush_stop,
            },
            "mine": {
                "taskId": "mine",
                "type": "auto-mine",
                "sessionId": self.account_ref,
                "status": "running",
                "stopEvent": mine_stop,
            },
        }

        self.assertEqual(
            SERVER._desktop_active_shared_resident_keys(self.account_ref),
            ["brushYellow", "mine"],
        )
        brush_stop.set()
        self.assertEqual(
            SERVER._desktop_active_shared_resident_keys(self.account_ref),
            ["mine"],
        )
        mine_stop.set()
        self.assertEqual(
            SERVER._desktop_active_shared_resident_keys(self.account_ref),
            [],
        )

    def test_desktop_additional_resident_tasks_share_the_same_activation_keys(
        self,
    ) -> None:
        stops = {
            feature: threading.Event()
            for feature in (
                "raid", "lossless", "dungeon", "general", "ministry",
                "domestic", "technology",
            )
        }
        task_types = {
            "general": "auto-general",
            "ministry": "auto-ministry",
            "domestic": "auto-domestic",
            "technology": "auto-technology",
        }
        SERVER.AUTO_TASKS = {
            feature: {
                "taskId": feature,
                "type": task_types.get(feature, feature),
                "sessionId": self.account_ref,
                "status": "running",
                "stopEvent": stops[feature],
            }
            for feature in stops
        }
        self.assertEqual(
            SERVER._desktop_active_shared_resident_keys(self.account_ref),
            ["domestic", "dungeon", "general", "lossless", "ministry", "raid"],
        )
        stops["lossless"].set()
        self.assertEqual(
            SERVER._desktop_active_shared_resident_keys(self.account_ref),
            ["domestic", "dungeon", "general", "ministry", "raid"],
        )

    def test_desktop_hubu_query_uses_shared_payload_and_parser(self) -> None:
        self.mode = "hubu-query"
        self.commands.clear()
        accepted = SERVER.SHARED_PYTHON_CORE.dispatch(
            "POST",
            "/api/liubu/hubu/query",
            {"sessionId": self.account_ref},
            {"requestId": "desktop-hubu-fixture", "platform": "desktop"},
        )

        self.assertEqual(accepted.status, 202)
        operation = self._wait(
            SERVER.SHARED_PYTHON_CORE,
            str(accepted.body["operationId"]),
        )
        self.assertEqual(operation["status"], "SUCCEEDED", operation)
        self.assertFalse(operation["requestSent"])
        self.assertEqual(operation["result"]["garden"]["emptyCount"], 10)
        self.assertEqual(
            [(row["opcode"], row["payload"].hex()) for row in self.commands],
            [(0x6320, "")],
        )

    def test_desktop_formation_apply_uses_shared_raw_1226_workflow(self) -> None:
        self.mode = "formation-apply"
        self.commands.clear()
        self._install_formation_state((1,))
        accepted = SERVER.SHARED_PYTHON_CORE.dispatch(
            "POST",
            "/api/formations/apply",
            {
                "sessionId": self.account_ref,
                "confirm": "apply-formations",
                "formations": [{
                    "enabled": True,
                    "generalIds": ["1"],
                    "soldierType": "轻骑兵",
                    "soldierCount": 100,
                }],
                "formationOptions": {"clearOtherGenerals": False},
            },
            {"requestId": "desktop-formations-fixture", "platform": "desktop"},
        )

        self.assertEqual(accepted.status, 202)
        operation = self._wait(
            SERVER.SHARED_PYTHON_CORE,
            str(accepted.body["operationId"]),
        )
        self.assertEqual(operation["status"], "SUCCEEDED", operation)
        self.assertEqual(operation["result"]["appliedCount"], 1)
        self.assertEqual(
            [(row["opcode"], row["payload"].hex()) for row in self.commands],
            [(0x1226, "000000000000000100000300000064")],
        )


if __name__ == "__main__":
    unittest.main()
