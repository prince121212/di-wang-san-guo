from __future__ import annotations

import json
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = ROOT / "shared_core" / "python"
if str(CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CORE_SOURCE))

from dwpm_core import create_hosted_core  # noqa: E402
from shared_raw_http_test_host import (  # noqa: E402
    FIXTURE_GAME_HTTP,
    RawHttpGameCommandHostMixin,
)


class RawStateWorkflowHost(RawHttpGameCommandHostMixin):
    def __init__(self, fixtures) -> None:
        self.fixtures = fixtures
        self.commands = []
        self.locked = False
        self.state_payload = bytes.fromhex(
            fixtures["roleHead8004"]["responseHex"]
            + fixtures["generalRecord8004"]["responseHex"]
            + fixtures["idleArmy8004"]["responseHex"]
        )

    def executionOwnerActive(self):
        return True

    def tryAcquireNetworkOperation(self, account_ref):
        if self.locked or str(account_ref) != "202":
            return False
        self.locked = True
        return True

    def releaseNetworkOperation(self, account_ref):
        if str(account_ref) != "202" or not self.locked:
            raise AssertionError("invalid account-lane release")
        self.locked = False

    def executeGameCommand(self, account_ref, command_json, _context_json):
        command = json.loads(command_json)
        self.commands.append((str(account_ref), command))
        opcode = int(command["opcode"])
        if opcode == 0x1016:
            packets = [{"opcode": 0x8004, "payloadHex": self.state_payload.hex()}]
        elif opcode == 0x1104:
            packets = [{
                "opcode": 0x8104,
                "payloadHex": self.fixtures["inventory8104Compact"]["responseHex"],
            }]
        elif opcode == 0x1600:
            packets = [{
                "opcode": 0x8600,
                "payloadHex": self.fixtures["militaryIncoming8600"]["responseHex"],
            }]
        elif opcode == 0x1310:
            parsed_fief_payload = bytes.fromhex(
                self.fixtures["raidFief8310"]["responseHex"]
            )
            expected_fief_id = int(
                self.fixtures["internalAffairsFief8246"]["expectedFiefId"]
            )
            # Keep the verified header and first row, but expose exactly one
            # self-owned fief whose ID matches the 0x8246 fixture.
            count_offset = 2 + 2 + len("目标玩家".encode()) + 2 + len("魏".encode())
            first_id_offset = count_offset + 1
            first_row_end = first_id_offset + 8 + 2 + len("一号封地".encode()) + 1 + 2 + len("洛阳".encode()) + 5
            fief_payload = (
                parsed_fief_payload[:count_offset]
                + b"\x01"
                + expected_fief_id.to_bytes(8, "big")
                + parsed_fief_payload[first_id_offset + 8:first_row_end]
            )
            packets = [{
                "opcode": 0x8310,
                "payloadHex": fief_payload.hex(),
            }]
        elif opcode == 0x1246:
            packets = [{
                "opcode": 0x8246,
                "payloadHex": self.fixtures["internalAffairsFief8246"]["responseHex"],
            }]
        elif opcode == 0x3110:
            packets = [{
                "opcode": 0xA110,
                "payloadHex": self.fixtures["generalStatusA110"]["responseHex"],
            }]
        else:
            raise AssertionError(f"unexpected shared command {opcode:#x}")
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


class SharedStateNetworkWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixtures = json.loads(
            (ROOT / "shared_core" / "protocol_parity_fixtures.json").read_text(
                encoding="utf-8"
            )
        )["fixtures"]

    def _facade(self, directory: str, host: RawStateWorkflowHost):
        facade = create_hosted_core(
            str(Path(directory) / "operations.json"),
            host,
        )
        facade.account_record_upsert({
            "accountRef": "202",
            "id": 202,
            "username": "raw-state-fixture",
            "platformKey": "sglm",
            "enabled": True,
            "loginState": "REAL_PROTOCOL_ONLINE",
            "session": {
                "accountId": 202,
                "sourceMode": 1,
                "publicState": {
                    "roleId": "202",
                    "gameHttp": FIXTURE_GAME_HTTP,
                    "lastValidatedAt": "1000",
                },
            },
        })
        return facade

    @staticmethod
    def _wait(facade, operation_id: str):
        deadline = time.time() + 3
        while time.time() < deadline:
            operation = (
                facade.operation_status(operation_id).get("operation") or {}
            )
            if operation.get("status") in {
                "SUCCEEDED", "FAILED", "CANCELLED", "UNCERTAIN"
            }:
                return operation
            time.sleep(0.01)
        raise AssertionError("shared operation did not finish")

    def test_state_refresh_uses_only_python_packets_parsers_and_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            host = RawStateWorkflowHost(self.fixtures)
            facade = self._facade(directory, host)
            try:
                accepted = facade.dispatch(
                    "GET",
                    "/api/state/refresh",
                    {"accountRef": "202", "scope": "all"},
                    {"requestId": "raw-state-all", "platform": "android"},
                )
                operation = self._wait(facade, accepted.body["operationId"])
                stored = json.loads(facade.account_record_json("202"))["account"]
            finally:
                facade.close()

        self.assertEqual(operation["status"], "SUCCEEDED", operation)
        result = operation["result"]
        self.assertEqual(result["role"]["roleId"], 202)
        self.assertEqual(result["role"]["roleName"], "利萍丰")
        self.assertEqual(result["generals"][0]["id"], 528290)
        self.assertEqual(result["army"][0]["idleCount"], 120)
        self.assertEqual(result["inventory"]["items"][0]["itemId"], 76)
        self.assertEqual(result["militarySnapshot"]["incomingCount"], 1)
        self.assertEqual(
            [command[1]["opcode"] for command in host.commands],
            [0x1016, 0x1104, 0x1600],
        )
        self.assertEqual(
            host.commands[0][1]["payloadHex"],
            struct.pack(">q", 202).hex(),
        )
        self.assertEqual(
            host.commands[2][1]["payloadHex"],
            self.fixtures["militaryIncoming8600"]["requestPayloadHex"],
        )
        public = stored["session"]["publicState"]
        self.assertEqual(json.loads(public["generalsJson"])[0]["id"], 528290)
        self.assertEqual(
            json.loads(public["militarySnapshotJson"])["incomingCount"],
            1,
        )

    def test_heartbeat_and_military_routes_do_not_need_network_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            host = RawStateWorkflowHost(self.fixtures)
            facade = self._facade(directory, host)
            try:
                # Seed the real general list so 0xa110 status evidence can be joined.
                state = facade.dispatch(
                    "GET",
                    "/api/state/refresh",
                    {"accountRef": "202", "scope": "role"},
                    {"requestId": "raw-state-role"},
                )
                self.assertEqual(
                    self._wait(facade, state.body["operationId"])["status"],
                    "SUCCEEDED",
                )
                host.commands.clear()

                heartbeat = facade.dispatch(
                    "GET",
                    "/api/heartbeat",
                    {"accountRef": "202", "sessionId": "drop-me"},
                    {"requestId": "raw-heartbeat"},
                )
                heartbeat_operation = self._wait(
                    facade, heartbeat.body["operationId"]
                )
                military = facade.dispatch(
                    "GET",
                    "/api/military/intel",
                    {"accountRef": "202"},
                    {"requestId": "raw-military"},
                )
                military_operation = self._wait(
                    facade, military.body["operationId"]
                )
                stored = json.loads(facade.account_record_json("202"))["account"]
            finally:
                facade.close()

        self.assertEqual(heartbeat_operation["status"], "SUCCEEDED")
        self.assertTrue(heartbeat_operation["result"]["online"])
        self.assertEqual(
            heartbeat_operation["result"]["militaryIntel"]["statusByName"]["步2"],
            "战",
        )
        self.assertEqual(military_operation["status"], "SUCCEEDED")
        self.assertEqual(
            military_operation["result"]["militarySnapshot"]["incomingCount"],
            1,
        )
        self.assertEqual(
            [command[1]["opcode"] for command in host.commands],
            [0x3110, 0x1600],
        )
        operation_text = json.dumps(
            [heartbeat_operation, military_operation], ensure_ascii=False
        )
        self.assertNotIn("drop-me", operation_text)
        public = stored["session"]["publicState"]
        self.assertEqual(
            json.loads(public["militaryIntelJson"])["statusByName"]["步2"],
            "战",
        )

    def test_role_queue_scope_reads_all_queue_facts_and_persists_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            host = RawStateWorkflowHost(self.fixtures)
            # Queue parsing needs the verified technology table and the role name
            # used by the self-fief query. Keep the protocol facts in one 0x8004.
            technology_payload = bytes.fromhex(
                self.fixtures["internalAffairsTechnology8004"]["responseHex"]
            )
            host.state_payload += technology_payload[19:613]
            facade = self._facade(directory, host)
            try:
                account = facade.account_records_snapshot()["accounts"][0]
                account["session"]["publicState"]["roleName"] = "目标玩家"
                facade.account_record_upsert(account)
                accepted = facade.dispatch(
                    "GET",
                    "/api/state/refresh",
                    {"accountRef": "202", "scope": "role-queues"},
                    {"requestId": "raw-role-queues", "platform": "android"},
                )
                operation = self._wait(facade, accepted.body["operationId"])
                stored = json.loads(facade.account_record_json("202"))["account"]
            finally:
                facade.close()

        self.assertEqual(operation["status"], "SUCCEEDED", operation)
        summary = operation["result"]["roleQueueSummary"]
        self.assertEqual(summary["buildingQueue"], {"current": 0, "capacity": 2})
        self.assertEqual(summary["researchQueue"], {"current": 1, "capacity": 0})
        self.assertEqual(summary["fiefCount"], 1)
        self.assertEqual(
            [command[1]["opcode"] for command in host.commands],
            [0x1016, 0x1310, 0x1246],
        )
        public = stored["session"]["publicState"]
        self.assertEqual(
            json.loads(public["roleQueueSummaryJson"]),
            summary,
        )


if __name__ == "__main__":
    unittest.main()
