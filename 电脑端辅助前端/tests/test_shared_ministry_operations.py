from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core import create_hosted_core
from shared_raw_http_test_host import (
    FIXTURE_GAME_HTTP,
    RawHttpGameCommandHostMixin,
)


def _occupied_garden_hex(fixture: dict) -> str:
    """Flow-062 empty garden with plot 0 replaced by one occupied record.

    The 0xe320 layout swaps a plot's 7B empty entry for a 32B occupied
    record, so the frame grows by 25 bytes per occupied plot.
    """
    garden = bytes.fromhex(fixture["emptyGardenResponseHex"])
    record = (
        b"\x00"                    # plotIndex 0
        b"\x00\x01"                # cropId 1 (稻谷)
        + (36000).to_bytes(4, "big")   # totalSeconds
        + (0).to_bytes(4, "big")       # remainingSeconds
        + b"\x64"                  # percent
        + (100).to_bytes(2, "big")     # plantCount
        + b"\x00" * 18
    )
    assert len(record) == 32
    header, entries, tail = garden[:26], garden[26:96], garden[96:]
    return (header + record + entries[7:] + tail).hex()


class SharedMinistryOperationTests(unittest.TestCase):
    def test_hubu_query_and_verified_plant_use_shared_raw_workflows(self) -> None:
        fixture = json.loads(
            (ROOT / "shared_core" / "protocol_parity_fixtures.json").read_text(
                encoding="utf-8"
            )
        )["fixtures"]["ministryHubuVerifiedPlant"]

        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self, ledger: Path) -> None:
                self.ledger = ledger
                self.status_calls = 0
                self.commands = []

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                return None

            def executeNetworkOperation(self, *_args):
                raise AssertionError("Hubu routes must use the shared raw command port")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode == 0x6320:
                    self.status_calls += 1
                    payload = fixture["emptyGardenResponseHex"]
                    if self.status_calls > 1:
                        payload = _occupied_garden_hex(fixture)
                    response_opcode = 0xE320
                else:
                    payload = fixture["plantResponseHex"]
                    response_opcode = 0xE328
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
                                "payloadHex": payload,
                            }],
                        },
                    },
                })

        def wait(facade, operation_id: str):
            for _ in range(200):
                operation = facade.operation_status(operation_id)["operation"]
                if operation["status"] not in {"QUEUED", "RUNNING"}:
                    return operation
                time.sleep(0.005)
            self.fail("operation did not finish")

        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "operations.json"
            bridge = HostBridge(ledger)
            facade = create_hosted_core(str(ledger), bridge)
            try:
                facade.account_record_upsert({
                    "accountRef": "202",
                    "id": 202,
                    "enabled": True,
                    "loginState": "REAL_PROTOCOL_ONLINE",
                    "session": {
                        "accountId": 202,
                        "sourceMode": 1,
                        "publicState": {
                            "gameHttp": FIXTURE_GAME_HTTP,
                            "lastValidatedAt": "1000",
                        },
                    },
                })
                query = facade.dispatch(
                    "POST",
                    "/api/liubu/hubu/query",
                    {"accountRef": "202"},
                    {"requestId": "hubu-query"},
                )
                self.assertEqual(query.status, 202)
                query_result = wait(facade, query.body["operationId"])
                self.assertEqual(query_result["status"], "SUCCEEDED")
                self.assertEqual(query_result["result"]["garden"]["emptyCount"], 5)
                self.assertEqual(
                    query_result["result"]["garden"]["unlockedCount"], 5
                )
                self.assertFalse(query_result["requestSent"])

                # Each operation receives its own before/after garden snapshot.
                bridge.status_calls = 0

                plant = facade.dispatch(
                    "POST",
                    "/api/liubu/hubu/plant",
                    {
                        "accountRef": "202",
                        "confirm": "hubu-batch-plant",
                        "crop": "稻谷",
                    },
                    {"requestId": "hubu-plant"},
                )
                self.assertEqual(plant.status, 202)
                plant_result = wait(facade, plant.body["operationId"])
                self.assertEqual(plant_result["status"], "SUCCEEDED")
                self.assertTrue(plant_result["requestSent"])
                self.assertEqual(plant_result["result"]["result"]["success"], True)
                self.assertEqual(
                    [row["opcode"] for row in bridge.commands],
                    [0x6320, 0x6320, 0x6328, 0x6320],
                )
                self.assertEqual(bridge.commands[2]["payloadHex"], "0100000001")
            finally:
                facade.close()

    def test_uncertain_plant_is_reconciled_by_status_without_replay(self) -> None:
        fixture = json.loads(
            (ROOT / "shared_core" / "protocol_parity_fixtures.json").read_text(
                encoding="utf-8"
            )
        )["fixtures"]["ministryHubuVerifiedPlant"]

        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self, ledger: Path) -> None:
                self.ledger = ledger
                self.status_calls = 0
                self.commands: list[int] = []

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                return account_ref == "202"

            def releaseNetworkOperation(self, _account_ref):
                return None

            def executeGameCommand(self, _account_ref, command_json, _context_json):
                command = json.loads(command_json)
                opcode = int(command["opcode"])
                self.commands.append(opcode)
                if opcode == 0x6320:
                    self.status_calls += 1
                    payload = fixture["emptyGardenResponseHex"]
                    if self.status_calls > 1:
                        payload = _occupied_garden_hex(fixture)
                    packets = [{"opcode": 0xE320, "payloadHex": payload}]
                else:
                    # The first mutation crosses the send boundary but loses
                    # its receipt. Recovery must only query status.
                    packets = []
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

        def wait(facade, operation_id: str):
            for _ in range(200):
                operation = facade.operation_status(operation_id)["operation"]
                if operation["status"] not in {"QUEUED", "RUNNING"}:
                    return operation
                time.sleep(0.005)
            self.fail("operation did not finish")

        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "operations.json"
            bridge = HostBridge(ledger)
            facade = create_hosted_core(str(ledger), bridge)
            try:
                facade.account_record_upsert({
                    "accountRef": "202",
                    "id": 202,
                    "enabled": True,
                    "loginState": "REAL_PROTOCOL_ONLINE",
                    "session": {
                        "accountId": 202,
                        "sourceMode": 1,
                        "publicState": {
                            "gameHttp": FIXTURE_GAME_HTTP,
                            "lastValidatedAt": "1000",
                        },
                    },
                })
                body = {
                    "accountRef": "202",
                    "confirm": "hubu-batch-plant",
                    "crop": "稻谷",
                }
                first = facade.dispatch(
                    "POST", "/api/liubu/hubu/plant", body,
                    {"requestId": "hubu-uncertain"},
                )
                uncertain = wait(facade, first.body["operationId"])
                self.assertEqual(uncertain["status"], "UNCERTAIN")
                record = json.loads(facade.account_record_json("202"))["account"]
                pending = json.loads(
                    record["session"]["publicState"]["ministryPendingPlantJson"]
                )
                self.assertEqual(pending["sendState"], "uncertain")

                recovered_call = facade.dispatch(
                    "POST", "/api/liubu/hubu/plant", body,
                    {"requestId": "hubu-recovery"},
                )
                recovered = wait(facade, recovered_call.body["operationId"])
                self.assertEqual(recovered["status"], "SUCCEEDED")
                self.assertFalse(recovered["requestSent"])
                self.assertEqual(
                    recovered["result"]["result"]["raw"]["phase"],
                    "plant-recovered",
                )
                self.assertEqual(bridge.commands, [0x6320, 0x6328, 0x6320])
                record = json.loads(facade.account_record_json("202"))["account"]
                self.assertEqual(
                    record["session"]["publicState"]["ministryPendingPlantJson"],
                    "{}",
                )
            finally:
                facade.close()


if __name__ == "__main__":
    unittest.main()
