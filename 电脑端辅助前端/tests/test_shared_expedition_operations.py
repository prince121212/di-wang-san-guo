from __future__ import annotations

import json
import tempfile
import time
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core import create_hosted_core
from dwpm_core.features.expedition import build_brush_payloads_variant
from shared_raw_http_test_host import (
    FIXTURE_GAME_HTTP,
    RawHttpGameCommandHostMixin,
)


class SharedExpeditionOperationTests(unittest.TestCase):
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
            "username": "expedition-fixture",
            "serverName": "fixture",
            "enabled": True,
            "loginState": "REAL_PROTOCOL_ONLINE",
            "session": {
                "accountId": 202,
                "sourceMode": 1,
                "publicState": {
                    "roleId": 202,
                    "gameHttp": FIXTURE_GAME_HTTP,
                    "level": 87,
                    "resourcePointCurrent": 0,
                    "resourcePointCap": 2,
                    "lastValidatedAt": "1000",
                },
            },
        })

    @staticmethod
    def _wait(facade, operation_id: str):
        for _ in range(400):
            operation = facade.operation_status(operation_id)["operation"]
            if operation["status"] not in {"QUEUED", "RUNNING"}:
                return operation
            time.sleep(0.005)
        raise AssertionError(f"operation did not finish: {operation_id}")

    def _install_formation_state(self, facade, *, general_ids=(1, 2)) -> None:
        fixtures = self.fixtures
        state_hex = (
            fixtures["roleHead8004"]["responseHex"]
            + fixtures["generalRecord8004"]["responseHex"]
            + fixtures["idleArmy8004"]["responseHex"]
        )
        rows = []
        for index, general_id in enumerate(general_ids):
            rows.append({
                "id": int(general_id),
                "idHex": f"{int(general_id):016x}",
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
            })
        army = [{"soldierTypeCode": 3, "idleCount": 120}]
        facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
            lambda self, account_ref, context, read_only=False: (
                state_hex,
                [dict(row) for row in rows],
                [dict(row) for row in army],
            ),
            facade,
        )

    def test_brush_execute_uses_python_workflow_and_fixture_payloads(self) -> None:
        fixtures = self.fixtures

        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self) -> None:
                self.commands = []
                self.sent_request_records = []

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                return None

            def executeNetworkOperation(self, *_args):
                raise AssertionError("brush execute must use the raw command port")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode == 0x1522:
                    payload_hex = fixtures["brushYellowDispatchReceipts"][
                        "successResponseHex"
                    ]
                    response_opcode = 0x8522
                else:
                    payload_hex = ""
                    response_opcode = 0x8520
                return json.dumps({
                    "status": 200,
                    "body": {
                        "ok": True,
                        "gameCommandFact": {
                            "requestOpcode": opcode,
                            "httpCode": 200,
                            "httpOk": True,
                            "packets": [{
                                "opcode": response_opcode,
                                "payloadHex": payload_hex,
                            }],
                        },
                    },
                })

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(str(Path(directory) / "brush.json"), bridge)
            try:
                self._live_account(facade)
                self._install_formation_state(facade)
                target = {
                    "id": 101,
                    "x": 18,
                    "y": 22,
                    "type": "山贼",
                    "kind": "山贼",
                }
                accepted = facade.dispatch(
                    "POST",
                    "/api/brush/execute",
                    {
                        "accountRef": "202",
                        "confirm": "brush-yellow",
                        "generalIds": ["1", "2"],
                        "target": target,
                        "hostSettings": {
                            "formations": [
                                {"generalIds": ["1", "2"], "soldierType": "轻骑兵", "soldierCount": 120}
                            ],
                            "config": {"healWounded": False, "autoEnergy": False},
                            "healWounded": False,
                            "autoEnergy": False,
                        },
                    },
                    {"requestId": "brush-fixture", "platform": "android"},
                )
                self.assertEqual(accepted.status, 202)
                operation = self._wait(facade, accepted.body["operationId"])
                self.assertEqual(operation["status"], "SUCCEEDED", operation)
                self.assertTrue(operation["requestSent"])
                result = operation["result"]["result"]
                self.assertEqual(result["successBattleId"], fixtures["brushYellowDispatchReceipts"]["expectedBattleId"])
                self.assertEqual(
                    [int(row["opcode"], 16) for row in result["actionResults"]],
                    [0x1520, 0x1522],
                )
                variant = build_brush_payloads_variant(
                    [f"{value:016x}" for value in (1, 2)],
                    "0000000000000065",
                    variant=0,
                )
                self.assertEqual(result["payloads"]["prepareGameHex"], variant["prepare"])
                self.assertEqual(result["payloads"]["dispatchGameHex"], variant["expedition"])
                self.assertEqual([int(row["opcode"]) for row in bridge.commands], [0x1520, 0x1522])
                stored = json.loads(facade.account_record_json("202"))["account"]
                pending = json.loads(
                    stored["session"]["publicState"]["brushPendingRecoveryJson"]
                )
                self.assertEqual(pending["sendState"], "accepted")
                self.assertEqual(pending["generalIds"], [1, 2])
                self.assertEqual(
                    pending["battleId"],
                    fixtures["brushYellowDispatchReceipts"]["expectedBattleId"],
                )
            finally:
                facade.close()

    def test_mine_execute_marks_uncertain_when_dispatch_receipt_is_missing(self) -> None:
        fixtures = self.fixtures

        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self) -> None:
                self.commands = []

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                return None

            def executeNetworkOperation(self, *_args):
                raise AssertionError("mine execute must use the raw command port")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode == 0x1520:
                    packets = [{
                        "opcode": 0x8520,
                        "payloadHex": fixtures["minePreview8520"]["responseHex"],
                    }]
                else:
                    # A transport response without 0x8522 is not proof of failure.
                    packets = [{"opcode": 0x8004, "payloadHex": "00"}]
                return json.dumps({
                    "status": 200,
                    "body": {
                        "ok": True,
                        "gameCommandFact": {
                            "requestOpcode": opcode,
                            "httpCode": 200,
                            "httpOk": True,
                            "packets": packets,
                        },
                    },
                })

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(str(Path(directory) / "mine.json"), bridge)
            try:
                self._live_account(facade)
                self._install_formation_state(facade, general_ids=(1,))
                accepted = facade.dispatch(
                    "POST",
                    "/api/mine/execute",
                    {
                        "accountRef": "202",
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
                        "hostSettings": {
                            "formations": [
                                {"generalIds": ["1"], "soldierType": "轻骑兵", "soldierCount": 120}
                            ],
                            "config": {"healWounded": False, "autoEnergy": False},
                            "healWounded": False,
                            "autoEnergy": False,
                        },
                    },
                    {"requestId": "mine-fixture", "platform": "android"},
                )
                self.assertEqual(accepted.status, 202)
                operation = self._wait(facade, accepted.body["operationId"])
                self.assertEqual(operation["status"], "UNCERTAIN", operation)
                self.assertTrue(operation["requestSent"])
                self.assertEqual(operation["error"]["code"], "UNCERTAIN", operation)
                self.assertEqual([int(row["opcode"]) for row in bridge.commands], [0x1520, 0x1522])
            finally:
                facade.close()


if __name__ == "__main__":
    unittest.main()
