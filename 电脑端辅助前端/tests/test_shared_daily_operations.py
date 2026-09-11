from __future__ import annotations

import json
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core import CoreFacade, create_hosted_core
from dwpm_core.operations import OperationUncertainError
from dwpm_core.ports import PlatformPorts
from shared_raw_http_test_host import (
    FIXTURE_GAME_HTTP,
    RawHttpGameCommandHostMixin,
)


class SharedDailyOperationTests(unittest.TestCase):
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
            "username": "daily-fixture",
            "serverName": "fixture",
            "enabled": True,
            "loginState": "REAL_PROTOCOL_ONLINE",
            "session": {
                "accountId": 202,
                "sourceMode": 1,
                "publicState": {
                    "roleId": 202,
                    "gameHttp": FIXTURE_GAME_HTTP,
                    "level": 44,
                    "copper": 100000,
                    "food": 200000,
                    "officeName": "太守",
                    "lastValidatedAt": "1000",
                },
            },
        })

    def _wait(self, facade, operation_id: str):
        for _ in range(300):
            operation = facade.operation_status(operation_id)["operation"]
            if operation["status"] not in {"QUEUED", "RUNNING"}:
                return operation
            time.sleep(0.005)
        self.fail(f"operation did not finish: {operation_id}")

    def test_shared_daily_completion_decision_records_only_terminal_success(self) -> None:
        fixed_now = 1_785_515_999_000

        class Clock:
            def now_millis(self):
                return fixed_now

        class Completions:
            def __init__(self) -> None:
                self.counts: dict[tuple[str, str, int], int] = {}
                self.adds: list[tuple[str, str, int, int]] = []

            def count(self, account_ref, key, now_millis):
                return self.counts.get(
                    (str(account_ref), str(key), int(now_millis)),
                    0,
                )

            def add(self, account_ref, key, count, now_millis):
                storage_key = (
                    str(account_ref),
                    str(key),
                    int(now_millis),
                )
                self.adds.append((
                    str(account_ref),
                    str(key),
                    int(count),
                    int(now_millis),
                ))
                self.counts[storage_key] = (
                    self.counts.get(storage_key, 0) + int(count)
                )
                return self.counts[storage_key]

        completions = Completions()
        calls: list[str] = []

        def success(_execution, _body, _context):
            calls.append("success")
            return {
                "ok": True,
                "result": {
                    "success": True,
                    "completed": True,
                    "duplicateClaim": True,
                    "message": "服务器已确认今日完成",
                },
            }

        def partial(_execution, _body, _context):
            calls.append("partial")
            return {
                "ok": True,
                "result": {
                    "success": True,
                    "completed": False,
                    "partialSuccess": True,
                },
            }

        def uncertain(_execution, _body, _context):
            calls.append("uncertain")
            raise OperationUncertainError("发送后未收到回执")

        with tempfile.TemporaryDirectory() as directory:
            facade = CoreFacade(
                ROOT / "shared_core",
                str(Path(directory) / "completion-operations.json"),
                ports=PlatformPorts(
                    clock=Clock(),
                    daily_completions=completions,
                ),
            )
            try:
                wrapped = facade.daily_completion_workflow(
                    "autoSignIn", success
                )
                first = wrapped(None, {"accountRef": "202"}, {})
                second = wrapped(None, {"accountRef": "202"}, {})
                partial_result = facade.daily_completion_workflow(
                    "autoDonate", partial
                )(None, {"accountRef": "202"}, {})
                with self.assertRaises(OperationUncertainError):
                    facade.daily_completion_workflow(
                        "salary", uncertain
                    )(None, {"accountRef": "202"}, {})

                self.assertFalse(first["alreadyCompleted"])
                self.assertEqual(first["completionCount"], 1)
                self.assertTrue(second["alreadyCompleted"])
                self.assertEqual(calls.count("success"), 1)
                self.assertTrue(partial_result["result"]["partialSuccess"])
                self.assertEqual(
                    completions.adds,
                    [("202", "autoSignIn", 1, fixed_now)],
                )
                self.assertNotIn("salary", [row[1] for row in completions.adds])
                self.assertNotIn("autoDonate", [row[1] for row in completions.adds])
            finally:
                facade.close()

    def test_daily_claims_use_shared_raw_commands_and_fixture_semantics(self) -> None:
        fixtures = self.fixtures

        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self, ledger: Path) -> None:
                self.ledger = ledger
                self.commands: list[dict] = []
                self.acquired = 0
                self.released = 0
                self.completions: dict[tuple[str, str], int] = {}

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                self.acquired += 1
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                self.released += 1

            def dailyCompletionCount(self, account_ref, key, _now_millis):
                return self.completions.get((str(account_ref), str(key)), 0)

            def addDailyCompletion(
                self, account_ref, key, count, _now_millis
            ):
                storage_key = (str(account_ref), str(key))
                self.completions[storage_key] = (
                    self.completions.get(storage_key, 0) + int(count)
                )
                return self.completions[storage_key]

            def executeNetworkOperation(self, *_args):
                raise AssertionError("daily routes must use the shared raw command port")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                context = json.loads(context_json)
                opcode = int(command["opcode"])
                self.commands.append(command)

                ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
                record = next(
                    row for row in ledger["operations"]
                    if row["operationId"] == context["operationId"]
                )
                if opcode == 0x6260:
                    if record["requestSent"]:
                        raise AssertionError(
                            "arena preflight must remain cancellable before claim"
                        )
                elif not record["requestSent"]:
                    raise AssertionError(
                        "requestSent must be durable before daily mutation"
                    )

                if opcode == 0x6202:
                    packets = [{
                        "opcode": 0x8134,
                        "payloadHex": fixtures["dailySignIn8134Duplicate"][
                            "responseHex"
                        ],
                    }]
                elif opcode == 0x1134:
                    packets = [{
                        "opcode": 0x8134,
                        "payloadHex": fixtures["dailyDiamondExpired8134"][
                            "responseHex"
                        ],
                    }]
                elif opcode == 0x6260:
                    packets = [{"opcode": 0xE260, "payloadHex": "00"}]
                elif opcode == 0x6266:
                    packets = [{
                        "opcode": 0xE266,
                        "payloadHex": fixtures["dailyArenaDuplicateE266"][
                            "responseHex"
                        ],
                    }]
                elif opcode == 0x314B:
                    packets = [{
                        "opcode": 0xA14B,
                        "payloadHex": fixtures["dailySalaryA14bSuccess"][
                            "responseHex"
                        ],
                    }]
                else:
                    raise AssertionError(f"unexpected daily opcode: {opcode:#x}")

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
                }, ensure_ascii=False)

        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "daily-operations.json"
            bridge = HostBridge(ledger)
            facade = create_hosted_core(str(ledger), bridge)
            try:
                self._live_account(facade)
                results = {}
                for name, path in (
                    ("sign", "/api/daily/sign-in/claim"),
                    ("arena", "/api/daily/arena-coins/claim"),
                    ("salary", "/api/daily/salary/claim"),
                ):
                    accepted = facade.dispatch(
                        "POST",
                        path,
                        {"accountRef": "202", "ignoredSecret": "do-not-persist"},
                        {"requestId": f"daily-{name}", "platform": "android"},
                    )
                    self.assertEqual(accepted.status, 202)
                    operation = self._wait(facade, accepted.body["operationId"])
                    self.assertEqual(operation["status"], "SUCCEEDED")
                    self.assertTrue(operation["requestSent"])
                    self.assertNotIn(
                        "do-not-persist",
                        json.dumps(operation, ensure_ascii=False),
                    )
                    results[name] = operation["result"]["result"]

                self.assertTrue(
                    results["sign"]["raw"]["signIn"]["duplicateClaim"]
                )
                self.assertTrue(
                    results["sign"]["raw"]["diamondBox"]["alreadyClaimed"]
                )
                self.assertTrue(
                    results["arena"]["raw"]["receipt"]["duplicateClaim"]
                )
                self.assertEqual(
                    results["salary"]["raw"]["receipt"]["copper"],
                    642850,
                )
                self.assertEqual(
                    results["salary"]["raw"]["receipt"]["food"],
                    1190689,
                )
                self.assertEqual(
                    [command["opcode"] for command in bridge.commands],
                    [0x6202, 0x1134, 0x6260, 0x6266, 0x314B],
                )
                self.assertEqual(
                    [command["payloadHex"] for command in bridge.commands],
                    ["", "00000000000de2b100", "", "", "01"],
                )
                repeated = facade.dispatch(
                    "POST",
                    "/api/daily/sign-in/claim",
                    {"accountRef": "202"},
                    {"requestId": "daily-sign-repeat", "platform": "android"},
                )
                repeated_operation = self._wait(
                    facade, repeated.body["operationId"]
                )
                self.assertEqual(repeated_operation["status"], "SUCCEEDED")
                self.assertFalse(repeated_operation["requestSent"])
                self.assertTrue(
                    repeated_operation["result"]["alreadyCompleted"]
                )
                self.assertEqual(len(bridge.commands), 5)
                self.assertEqual(
                    bridge.completions,
                    {
                        ("202", "autoSignIn"): 1,
                        ("202", "arenaCoins"): 1,
                        ("202", "salary"): 1,
                    },
                )
                self.assertEqual(bridge.acquired, 4)
                self.assertEqual(bridge.released, 4)
            finally:
                facade.close()

    def test_daily_claim_failure_boundary_distinguishes_failed_and_uncertain(self) -> None:
        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self, ledger: Path, outcome: str) -> None:
                self.ledger = ledger
                self.outcome = outcome
                self.commands: list[int] = []

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                return None

            def executeNetworkOperation(self, *_args):
                raise AssertionError("daily routes must use the shared raw command port")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                opcode = int(command["opcode"])
                self.commands.append(opcode)
                if self.outcome == "arena-preflight-failure":
                    raise RuntimeError("arena read failed before claim")
                return json.dumps({
                    "status": 200,
                    "body": {
                        "ok": True,
                        "gameCommandFact": {
                            "requestOpcode": opcode,
                            "httpCode": 200,
                            "httpOk": True,
                            "packets": [{"opcode": 0x880D, "payloadHex": "00"}],
                        },
                    },
                })

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for outcome, path, expected, request_sent in (
                (
                    "arena-preflight-failure",
                    "/api/daily/arena-coins/claim",
                    "FAILED",
                    False,
                ),
                (
                    "salary-missing-receipt",
                    "/api/daily/salary/claim",
                    "UNCERTAIN",
                    True,
                ),
            ):
                ledger = root / f"{outcome}.json"
                bridge = HostBridge(ledger, outcome)
                facade = create_hosted_core(str(ledger), bridge)
                try:
                    self._live_account(facade)
                    accepted = facade.dispatch(
                        "POST",
                        path,
                        {"accountRef": "202"},
                        {"requestId": outcome, "platform": "android"},
                    )
                    self.assertEqual(accepted.status, 202)
                    operation = self._wait(facade, accepted.body["operationId"])
                    self.assertEqual(operation["status"], expected)
                    self.assertEqual(operation["requestSent"], request_sent)
                    if outcome == "arena-preflight-failure":
                        self.assertEqual(bridge.commands, [0x6260])
                    else:
                        self.assertEqual(bridge.commands, [0x314B])
                finally:
                    facade.close()

    def test_daily_auto_and_custom_donation_use_python_payloads_and_limits(self) -> None:
        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self, ledger: Path) -> None:
                self.ledger = ledger
                self.commands: list[dict] = []

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                return None

            def executeNetworkOperation(self, *_args):
                raise AssertionError("donation routes must use raw commands")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                context = json.loads(context_json)
                self.commands.append(command)
                ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
                record = next(
                    row for row in ledger["operations"]
                    if row["operationId"] == context["operationId"]
                )
                if not record["requestSent"]:
                    raise AssertionError(
                        "requestSent must be durable before donation mutation"
                    )
                opcode = int(command["opcode"])
                response_opcode = 0x840A if opcode == 0x140A else 0x840C
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
                                "payloadHex": "00",
                            }],
                        },
                    },
                })

        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "donation.json"
            bridge = HostBridge(ledger)
            facade = create_hosted_core(str(ledger), bridge)
            try:
                self._live_account(facade)
                automatic = facade.dispatch(
                    "POST",
                    "/api/daily/donate/claim",
                    {"accountRef": "202"},
                    {"requestId": "daily-donate", "platform": "android"},
                )
                self.assertEqual(automatic.status, 202)
                auto_operation = self._wait(
                    facade, automatic.body["operationId"]
                )
                self.assertEqual(auto_operation["status"], "SUCCEEDED")
                self.assertEqual(
                    auto_operation["result"]["result"]["successCount"],
                    3,
                )

                custom = facade.dispatch(
                    "POST",
                    "/api/daily/donate/custom",
                    {
                        "accountRef": "202",
                        "copper": 80000,
                        "food": 500000,
                        "ignored": "do-not-persist",
                    },
                    {"requestId": "daily-custom-donate", "platform": "android"},
                )
                self.assertEqual(custom.status, 202)
                custom_operation = self._wait(
                    facade, custom.body["operationId"]
                )
                self.assertEqual(custom_operation["status"], "SUCCEEDED")
                self.assertNotIn(
                    "do-not-persist",
                    json.dumps(custom_operation, ensure_ascii=False),
                )
                self.assertEqual(
                    [row["amount"] for row in custom_operation["result"]["result"]["actions"]],
                    [44000, 132000],
                )
                self.assertEqual(
                    [command["opcode"] for command in bridge.commands],
                    [0x140C, 0x140C, 0x140A, 0x140C, 0x140C],
                )
                self.assertEqual(
                    [command["payloadHex"] for command in bridge.commands],
                    [
                        "000000000000abe000000000000000000000000000000000",
                        "000000000000000000000000000203a00000000000000000",
                        "000000abe0",
                        "000000000000abe000000000000000000000000000000000",
                        "000000000000000000000000000203a00000000000000000",
                    ],
                )
            finally:
                facade.close()

    def test_daily_donation_missing_receipt_is_uncertain_and_citizen_salary_skips(self) -> None:
        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self, mode: str) -> None:
                self.mode = mode
                self.commands: list[int] = []

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                return None

            def executeNetworkOperation(self, *_args):
                raise AssertionError("daily routes must use raw commands")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                opcode = int(command["opcode"])
                self.commands.append(opcode)
                return json.dumps({
                    "status": 200,
                    "body": {
                        "ok": True,
                        "gameCommandFact": {
                            "requestOpcode": opcode,
                            "httpCode": 200,
                            "httpOk": True,
                            "packets": [{"opcode": 0x880D, "payloadHex": "00"}],
                        },
                    },
                })

        with tempfile.TemporaryDirectory() as directory:
            donation_bridge = HostBridge("missing-receipt")
            donation_facade = create_hosted_core(
                str(Path(directory) / "donation-missing.json"),
                donation_bridge,
            )
            try:
                self._live_account(donation_facade)
                accepted = donation_facade.dispatch(
                    "POST",
                    "/api/daily/donate/claim",
                    {"accountRef": "202"},
                    {"requestId": "donation-missing", "platform": "android"},
                )
                operation = self._wait(
                    donation_facade, accepted.body["operationId"]
                )
                self.assertEqual(operation["status"], "UNCERTAIN")
                self.assertTrue(operation["requestSent"])
                self.assertEqual(donation_bridge.commands, [0x140C])
            finally:
                donation_facade.close()

            citizen_bridge = HostBridge("citizen")
            citizen_facade = create_hosted_core(
                str(Path(directory) / "citizen-salary.json"),
                citizen_bridge,
            )
            try:
                self._live_account(citizen_facade)
                account = citizen_facade.account_records_snapshot()["accounts"][0]
                account["session"]["publicState"]["officeName"] = "国民"
                account["session"]["publicState"]["officeIdUnsigned"] = 0x0100
                citizen_facade.account_record_upsert(account)
                accepted = citizen_facade.dispatch(
                    "POST",
                    "/api/daily/salary/claim",
                    {"accountRef": "202"},
                    {"requestId": "citizen-salary", "platform": "android"},
                )
                operation = self._wait(
                    citizen_facade, accepted.body["operationId"]
                )
                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertFalse(operation["requestSent"])
                self.assertTrue(operation["result"]["result"]["skipped"])
                self.assertEqual(citizen_bridge.commands, [])
            finally:
                citizen_facade.close()

    def test_national_city_lord_and_general_visit_use_shared_raw_workflows(self) -> None:
        fixtures = self.fixtures

        def utf(value: str) -> bytes:
            encoded = value.encode("utf-8")
            return struct.pack(">H", len(encoded)) + encoded

        def status_receipt(status: int, message: str) -> str:
            return (struct.pack(">b", status) + utf(message)).hex()

        def general_page() -> str:
            payload = bytearray()
            payload += struct.pack(">b", 0)
            payload += utf("")
            payload += struct.pack(">HHB", 4, 1, 1)
            payload += struct.pack(">q", 88)
            payload += utf("蔡邕")
            payload += bytes((0, 0, 85, 0))
            payload += struct.pack(">h", 1)
            payload += utf("封地")
            payload += utf("洛阳")
            payload += b"\x00"
            payload += utf("君主")
            payload += struct.pack(">hBqq", 0, 50, 0, 100)
            payload += struct.pack(">hhhhhhhh", 0, 0, 90, 0, 10, 20, 30, 40)
            payload += struct.pack(">hh", 50, 1000)
            return bytes(payload).hex()

        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self, ledger: Path) -> None:
                self.ledger = ledger
                self.commands: list[dict] = []
                self.national_status_calls = 0

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                return None

            def executeNetworkOperation(self, *_args):
                raise AssertionError("daily workflows must use raw commands")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                context = json.loads(context_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
                record = next(
                    row for row in ledger["operations"]
                    if row["operationId"] == context["operationId"]
                )
                read_opcodes = {0x1404, 0x1332, 0x1318, 0x3271}
                if opcode in read_opcodes and record["requestSent"]:
                    raise AssertionError("daily preflight must remain cancellable")
                if opcode in read_opcodes and command.get("readOnly") is not True:
                    raise AssertionError("daily preflight must use read-only transport")
                if opcode not in read_opcodes and not record["requestSent"]:
                    raise AssertionError(
                        "requestSent must be durable before daily mutation"
                    )

                if opcode == 0x1404:
                    payload = bytes.fromhex(command["payloadHex"])
                    category = payload[8]
                    key = {
                        1: "dailyNationalCity8404State",
                        2: "dailyNationalCity8404Commandery",
                        3: "dailyNationalCity8404County",
                    }[category]
                    packets = [{
                        "opcode": 0x8404,
                        "payloadHex": fixtures[key]["responseHex"],
                    }]
                elif opcode == 0x1332:
                    copper = [100, 300, 200][self.national_status_calls]
                    self.national_status_calls += 1
                    packets = [{
                        "opcode": 0x8332,
                        "payloadHex": struct.pack(
                            ">BBBBqqqq", 0, 0, 0, 1,
                            copper, copper, 0, 0,
                        ).hex(),
                    }]
                elif opcode == 0x1334:
                    packets = [{
                        "opcode": 0x8334,
                        "payloadHex": status_receipt(1, "领取成功"),
                    }]
                elif opcode == 0x1318:
                    packets = [{
                        "opcode": 0x8318,
                        "payloadHex": fixtures["dailyOwnedCity8318Nanhua"][
                            "responseHex"
                        ],
                    }]
                elif opcode == 0x1330:
                    packets = [{
                        "opcode": 0x8330,
                        "payloadHex": status_receipt(1, "城主征收成功"),
                    }]
                elif opcode == 0x3271:
                    packets = [{"opcode": 0xA271, "payloadHex": general_page()}]
                elif opcode == 0x3273:
                    packets = [{
                        "opcode": 0xA273,
                        "payloadHex": fixtures["dailyGeneralVisitA273Rejected"][
                            "responseHex"
                        ],
                    }]
                else:
                    raise AssertionError(f"unexpected daily opcode {opcode:#x}")
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
                }, ensure_ascii=False)

        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "daily-country-workflows.json"
            bridge = HostBridge(ledger)
            facade = create_hosted_core(str(ledger), bridge)
            try:
                self._live_account(facade)
                candidates_accepted = facade.dispatch(
                    "POST",
                    "/api/daily/general-visit/candidates",
                    {"accountRef": "202"},
                    {"requestId": "general-candidates", "platform": "android"},
                )
                self.assertEqual(candidates_accepted.status, 202)
                candidates_operation = self._wait(
                    facade, candidates_accepted.body["operationId"]
                )
                self.assertEqual(candidates_operation["status"], "SUCCEEDED")
                self.assertFalse(candidates_operation["requestSent"])
                self.assertEqual(
                    candidates_operation["result"]["generals"][0]["id"], 88
                )
                routes = (
                    (
                        "national",
                        "/api/daily/national-collect/claim",
                        {"accountRef": "202"},
                    ),
                    (
                        "city-lord",
                        "/api/daily/city-lord-collect/claim",
                        {"accountRef": "202"},
                    ),
                    (
                        "general-visit",
                        "/api/daily/general-visit/claim",
                        {
                            "accountRef": "202",
                            "generalVisitGeneralIds": ["88"],
                        },
                    ),
                )
                operations = {}
                for name, route, body in routes:
                    accepted = facade.dispatch(
                        "POST",
                        route,
                        body,
                        {"requestId": name, "platform": "android"},
                    )
                    self.assertEqual(accepted.status, 202)
                    operation = self._wait(
                        facade, accepted.body["operationId"]
                    )
                    self.assertEqual(operation["status"], "SUCCEEDED")
                    self.assertTrue(operation["requestSent"])
                    operations[name] = operation["result"]["result"]

                self.assertEqual(
                    operations["national"]["ranking"][0]["city"],
                    "广成关",
                )
                self.assertEqual(
                    operations["national"]["successfulCopper"], 300
                )
                self.assertEqual(
                    operations["city-lord"]["ownedCities"][0]["cityName"],
                    "南化",
                )
                self.assertTrue(
                    operations["general-visit"]["invitationRejected"]
                )

                mutations = [
                    command for command in bridge.commands
                    if int(command["opcode"]) in {0x1334, 0x1330, 0x3273}
                ]
                self.assertEqual(
                    [command["opcode"] for command in mutations],
                    [0x1334, 0x1330, 0x3273],
                )
                self.assertEqual(
                    mutations[0]["payloadHex"],
                    (b"\x01" + utf("广成关")).hex(),
                )
                self.assertEqual(
                    mutations[1]["payloadHex"],
                    (b"\x01" + utf("南化") + b"\x00").hex(),
                )
                self.assertEqual(
                    mutations[2]["payloadHex"],
                    struct.pack(">qHH", 88, 1, 4).hex(),
                )
            finally:
                facade.close()

    def test_general_visit_duplicate_list_completes_without_mutation(self) -> None:
        fixture = self.fixtures["dailyGeneralVisitA271AlreadyVisited"]

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
                raise AssertionError("general visit must use raw commands")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                self.commands.append(int(command["opcode"]))
                return json.dumps({
                    "status": 200,
                    "body": {
                        "ok": True,
                        "gameCommandFact": {
                            "requestOpcode": int(command["opcode"]),
                            "httpCode": 200,
                            "httpOk": True,
                            "packets": [{
                                "opcode": 0xA271,
                                "payloadHex": fixture["responseHex"],
                            }],
                        },
                    },
                })

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(
                str(Path(directory) / "general-duplicate.json"), bridge
            )
            try:
                self._live_account(facade)
                accepted = facade.dispatch(
                    "POST",
                    "/api/daily/general-visit/claim",
                    {
                        "accountRef": "202",
                        "generalVisitGeneralIds": ["88"],
                    },
                    {"requestId": "general-duplicate", "platform": "android"},
                )
                operation = self._wait(facade, accepted.body["operationId"])
                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertFalse(operation["requestSent"])
                self.assertTrue(operation["result"]["result"]["duplicateVisit"])
                self.assertEqual(bridge.commands, [0x3271])
            finally:
                facade.close()

    def test_general_visit_no_generals_is_terminal_without_failure(self) -> None:
        def utf(value: str) -> bytes:
            encoded = value.encode("utf-8")
            return struct.pack(">H", len(encoded)) + encoded

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
                raise AssertionError("general visit must use raw commands")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                self.commands.append(int(command["opcode"]))
                if int(command["opcode"]) != 0x3271:
                    raise AssertionError("unexpected general visit opcode")
                payload = struct.pack(">b", -1) + utf("不可拜访，国王麾下无名将")
                return json.dumps({
                    "status": 200,
                    "body": {
                        "ok": True,
                        "gameCommandFact": {
                            "requestOpcode": 0x3271,
                            "httpCode": 200,
                            "httpOk": True,
                            "packets": [{
                                "opcode": 0xA271,
                                "payloadHex": payload.hex(),
                            }],
                        },
                    },
                }, ensure_ascii=False)

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(
                str(Path(directory) / "general-no-generals.json"), bridge
            )
            try:
                self._live_account(facade)
                query_accepted = facade.dispatch(
                    "POST",
                    "/api/daily/general-visit/candidates",
                    {"accountRef": "202"},
                    {"requestId": "general-no-generals-query", "platform": "android"},
                )
                query_operation = self._wait(
                    facade, query_accepted.body["operationId"]
                )
                self.assertEqual(query_operation["status"], "SUCCEEDED")
                self.assertTrue(query_operation["result"]["noTarget"])
                self.assertEqual(
                    query_operation["result"]["message"],
                    "不可拜访，国王麾下无名将",
                )
                accepted = facade.dispatch(
                    "POST",
                    "/api/daily/general-visit/claim",
                    {
                        "accountRef": "202",
                        "generalVisitGeneralIds": ["88"],
                    },
                    {"requestId": "general-no-generals", "platform": "android"},
                )
                operation = self._wait(facade, accepted.body["operationId"])
                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertFalse(operation["requestSent"])
                result = operation["result"]["result"]
                self.assertTrue(result["success"])
                self.assertTrue(result["completed"])
                self.assertTrue(result["noTarget"])
                self.assertTrue(result["skipped"])
                self.assertEqual(result["message"], "不可拜访，国王麾下无名将")
                self.assertEqual(bridge.commands, [0x3271, 0x3271])
            finally:
                facade.close()

    def test_domestic_query_and_actions_use_shared_raw_protocol_and_verify_building(self) -> None:
        fixtures = self.fixtures

        def utf(value: str) -> bytes:
            encoded = value.encode("utf-8")
            return struct.pack(">H", len(encoded)) + encoded

        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self, ledger: Path) -> None:
                self.ledger = ledger
                self.commands: list[dict] = []

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                return None

            def executeNetworkOperation(self, *_args):
                raise AssertionError("domestic routes must use raw commands")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                context = json.loads(context_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
                record = next(
                    row for row in ledger["operations"]
                    if row["operationId"] == context["operationId"]
                )
                read_only = opcode in {0x1016, 0x1246}
                if read_only and command.get("readOnly") is not True:
                    raise AssertionError("domestic reads must use read-only transport")
                if read_only and record["requestSent"]:
                    raise AssertionError("domestic preflight must precede mutation")
                if not read_only and not record["requestSent"]:
                    raise AssertionError("domestic mutation must persist requestSent")
                if opcode == 0x1016:
                    packets = [{
                        "opcode": 0x8004,
                        "payloadHex": fixtures["internalAffairsTechnology8004"][
                            "responseHex"
                        ],
                    }]
                elif opcode == 0x1246:
                    packets = [{
                        "opcode": 0x8246,
                        "payloadHex": fixtures["internalAffairsFief8246"][
                            "responseHex"
                        ],
                    }]
                elif opcode == 0x1200:
                    packets = [{
                        "opcode": 0x8200,
                        "payloadHex": fixtures["internalAffairsBuilding8200"][
                            "responseHex"
                        ],
                    }]
                elif opcode == 0x123F:
                    packets = [{
                        "opcode": 0x823F,
                        "payloadHex": (b"\x00" + utf("升级成功")).hex(),
                    }]
                else:
                    raise AssertionError(f"unexpected domestic opcode {opcode:#x}")
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
                }, ensure_ascii=False)

        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "domestic.json"
            bridge = HostBridge(ledger)
            facade = create_hosted_core(str(ledger), bridge)
            try:
                self._live_account(facade)
                account = facade.account_records_snapshot()["accounts"][0]
                account["session"]["publicState"]["ownedFiefLocationsJson"] = json.dumps([
                    {"targetId": 2681, "fiefName": "九业封地"},
                ], ensure_ascii=False)
                facade.account_record_upsert(account)

                query = facade.dispatch(
                    "POST",
                    "/api/domestic/query",
                    {"accountRef": "202"},
                    {"requestId": "domestic-query", "platform": "android"},
                )
                self.assertEqual(query.status, 202)
                query_operation = self._wait(
                    facade, query.body["operationId"]
                )
                self.assertEqual(query_operation["status"], "SUCCEEDED")
                self.assertFalse(query_operation["requestSent"])
                self.assertEqual(query_operation["result"]["fiefIds"], [2681])
                self.assertEqual(
                    query_operation["result"]["fiefs"][0]["fiefName"],
                    "九业封地",
                )

                building = facade.dispatch(
                    "POST",
                    "/api/domestic/action",
                    {
                        "accountRef": "202",
                        "confirm": "auto-domestic",
                        "action": "building",
                        "fiefId": 2681,
                        "slot": 10,
                        "buildingType": 1,
                    },
                    {"requestId": "domestic-building", "platform": "android"},
                )
                building_operation = self._wait(
                    facade, building.body["operationId"]
                )
                self.assertEqual(building_operation["status"], "SUCCEEDED")
                self.assertTrue(building_operation["requestSent"])
                self.assertTrue(building_operation["result"]["result"]["success"])
                self.assertEqual(
                    building_operation["result"]["result"]["confirmedBy"],
                    "0x8200建筑同步",
                )

                technology = facade.dispatch(
                    "POST",
                    "/api/domestic/action",
                    {
                        "accountRef": "202",
                        "confirm": "auto-domestic",
                        "action": "technology",
                        "fiefId": 2681,
                        "academySlot": 0,
                        "technologyId": 5,
                        "targetLevel": 3,
                    },
                    {"requestId": "domestic-technology", "platform": "android"},
                )
                technology_operation = self._wait(
                    facade, technology.body["operationId"]
                )
                self.assertEqual(technology_operation["status"], "SUCCEEDED")
                self.assertTrue(technology_operation["requestSent"])
                self.assertTrue(technology_operation["result"]["result"]["success"])
                self.assertEqual(
                    [int(command["opcode"]) for command in bridge.commands],
                    [0x1016, 0x1246, 0x1246, 0x1200, 0x123F],
                )
            finally:
                facade.close()


if __name__ == "__main__":
    unittest.main()
