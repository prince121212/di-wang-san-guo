from __future__ import annotations

import json
import struct
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core import create_hosted_core
from shared_raw_http_test_host import (
    FIXTURE_GAME_HTTP,
    RawHttpGameCommandHostMixin,
)


class SharedRawFormationOperationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixtures = json.loads(
            (ROOT / "shared_core" / "protocol_parity_fixtures.json").read_text(
                encoding="utf-8"
            )
        )["fixtures"]

    @staticmethod
    def _live_account(facade) -> None:
        facade.account_record_upsert({
            "accountRef": "202",
            "id": 202,
            "enabled": True,
            "loginState": "REAL_PROTOCOL_ONLINE",
            "session": {
                "accountId": 202,
                "sourceMode": 1,
                "publicState": {
                    "roleId": 202,
                    "gameHttp": FIXTURE_GAME_HTTP,
                    "lastValidatedAt": "1000",
                },
            },
        })

    @staticmethod
    def _wait(facade, operation_id: str):
        for _ in range(300):
            operation = facade.operation_status(operation_id)["operation"]
            if operation["status"] not in {"QUEUED", "RUNNING"}:
                return operation
            time.sleep(0.005)
        raise AssertionError(f"operation did not finish: {operation_id}")

    def _new_facade(self, directory: str, initial_count: int = 100):
        fixture = self.fixtures

        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self) -> None:
                self.current_count = initial_count
                self.current_type = 3 if initial_count > 0 else -1
                self.commands = []
                self.network_calls = 0
                self.acquired = 0
                self.released = 0

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                self.acquired += 1
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                self.released += 1

            def executeNetworkOperation(self, *_args):
                self.network_calls += 1
                raise AssertionError("formation routes must not use the Kotlin network adapter")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode != 0x1226:
                    raise AssertionError(f"unexpected formation opcode {opcode:#x}")
                payload = bytes.fromhex(str(command["payloadHex"]))
                general_id, group, soldier_code, target_count = struct.unpack(
                    ">qbhi", payload
                )
                self.assert_account = account_ref
                self.assert_context = json.loads(context_json)
                old_count = self.current_count
                old_type = self.current_type
                self.current_count = target_count
                self.current_type = -1 if target_count == 0 else soldier_code
                response = struct.pack(
                    ">bqhhhh",
                    1,
                    general_id,
                    old_type,
                    old_count,
                    self.current_type,
                    target_count,
                )
                return json.dumps({
                    "status": 200,
                    "body": {
                        "ok": True,
                        "gameCommandFact": {
                            "requestOpcode": opcode,
                            "httpCode": 200,
                            "httpOk": True,
                            "packets": [{
                                "opcode": 0x8226,
                                "payloadHex": response.hex(),
                            }],
                        },
                    },
                })

        bridge = HostBridge()
        ledger = Path(directory) / "operations.json"
        facade = create_hosted_core(str(ledger), bridge)
        self._live_account(facade)
        state_hex = (
            fixture["roleHead8004"]["responseHex"]
            + fixture["generalRecord8004"]["responseHex"]
            + fixture["idleArmy8004"]["responseHex"]
        )

        def fresh_state(_self, _account_ref, _context, read_only=False):
            general = {
                "id": 7,
                "idHex": "0000000000000007",
                "name": "测试将领",
                "status": 0,
                "statusText": "闲",
                "displayStatus": "闲",
                "troopLimit": 1800,
                "soldierTypeCode": bridge.current_type,
                "soldierCount": bridge.current_count,
                "currentSoldierCount": bridge.current_count,
            }
            return state_hex, [general], [{"soldierTypeCode": 3, "idleCount": 2000}]

        facade._fresh_formation_state = types.MethodType(fresh_state, facade)
        return facade, bridge

    def test_apply_formations_splits_rows_and_uses_raw_1226_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            facade, bridge = self._new_facade(directory)
            try:
                accepted = facade.dispatch(
                    "POST",
                    "/api/formations/apply",
                    {
                        "accountRef": "202",
                        "confirm": "apply-formations",
                        "formations": [{
                            "enabled": True,
                            "generalIds": [7],
                            "soldierType": "轻骑兵",
                            "soldierCount": 150,
                        }],
                        "formationOptions": {"clearOtherGenerals": False},
                    },
                    {"requestId": "raw-formation-apply", "platform": "android"},
                )
                self.assertEqual(accepted.status, 202)
                operation = self._wait(facade, accepted.body["operationId"])
                self.assertEqual(operation["status"], "SUCCEEDED", operation)
                self.assertTrue(operation["requestSent"])
                self.assertEqual(operation["result"]["appliedCount"], 1)
                self.assertEqual(bridge.network_calls, 0)
                self.assertEqual(bridge.acquired, 1)
                self.assertEqual(bridge.released, 1)
                self.assertEqual(
                    [(row["opcode"], row["payloadHex"]) for row in bridge.commands],
                    [(0x1226, "000000000000000700000300000096")],
                )
            finally:
                facade.close()

    def test_unassign_all_uses_raw_1226_zero_count_and_shared_receipt_parser(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            facade, bridge = self._new_facade(directory)
            try:
                accepted = facade.dispatch(
                    "POST",
                    "/api/formations/unassign-all",
                    {"accountRef": "202", "confirm": "unassign-all-troops"},
                    {"requestId": "raw-unassign-all", "platform": "android"},
                )
                self.assertEqual(accepted.status, 202)
                operation = self._wait(facade, accepted.body["operationId"])
                self.assertEqual(operation["status"], "SUCCEEDED", operation)
                self.assertTrue(operation["requestSent"])
                self.assertEqual(operation["result"]["clearedCount"], 1)
                self.assertEqual(operation["result"]["skippedCount"], 0)
                self.assertEqual(
                    operation["result"]["message"],
                    "服务器已确认一键卸兵成功：1名将领当前无配兵",
                )
                self.assertEqual(
                    operation["result"]["generals"][0]["soldierTypeCode"],
                    -1,
                )
                self.assertEqual(bridge.network_calls, 0)
                self.assertEqual(
                    [(row["opcode"], row["payloadHex"]) for row in bridge.commands],
                    [(0x1226, "000000000000000700000300000000")],
                )
            finally:
                facade.close()

    def test_busy_row_does_not_block_later_idle_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            facade, bridge = self._new_facade(directory)
            try:
                fixture = self.fixtures
                state_hex = (
                    fixture["roleHead8004"]["responseHex"]
                    + fixture["generalRecord8004"]["responseHex"]
                    + fixture["idleArmy8004"]["responseHex"]
                )

                def fresh_state(_self, _account_ref, _context, read_only=False):
                    def general(general_id: int, status: int) -> dict:
                        return {
                            "id": general_id,
                            "idHex": f"{general_id:016x}",
                            "name": f"将领{general_id}",
                            "status": status,
                            "statusText": "闲" if status == 0 else "战",
                            "displayStatus": "闲" if status == 0 else "战",
                            "troopLimit": 1800,
                            "soldierTypeCode": 3,
                            "soldierCount": 100,
                            "currentSoldierCount": 100,
                        }

                    return (
                        state_hex,
                        [general(7, 6), general(8, 0)],
                        [{"soldierTypeCode": 3, "idleCount": 2000}],
                    )

                facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                    fresh_state,
                    facade,
                )
                accepted = facade.dispatch(
                    "POST",
                    "/api/formations/apply",
                    {
                        "accountRef": "202",
                        "confirm": "apply-formations",
                        "formations": [
                            {
                                "enabled": True,
                                "generalIds": [7],
                                "soldierType": "轻骑兵",
                                "soldierCount": 150,
                            },
                            {
                                "enabled": True,
                                "generalIds": [8],
                                "soldierType": "轻骑兵",
                                "soldierCount": 150,
                            },
                        ],
                        "formationOptions": {"clearOtherGenerals": False},
                    },
                    {"requestId": "raw-formation-partial", "platform": "android"},
                )
                self.assertEqual(accepted.status, 202)
                operation = self._wait(facade, accepted.body["operationId"])
                self.assertEqual(operation["status"], "SUCCEEDED", operation)
                result = operation["result"]
                self.assertEqual(result["appliedCount"], 1)
                self.assertEqual(result["skippedCount"], 1)
                self.assertTrue(result["partial"])
                self.assertEqual([row["generalId"] for row in result["results"]], ["7", "8"])
                self.assertEqual(
                    [struct.unpack(">qbhi", bytes.fromhex(row["payloadHex"]))[0]
                     for row in bridge.commands],
                    [8],
                )
            finally:
                facade.close()


if __name__ == "__main__":
    unittest.main()
