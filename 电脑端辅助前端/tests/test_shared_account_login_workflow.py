from __future__ import annotations

import json
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHARED_PYTHON = ROOT / "shared_core" / "python"
if str(SHARED_PYTHON) not in sys.path:
    sys.path.insert(0, str(SHARED_PYTHON))

from dwpm_core.account.login import perform_shared_login  # noqa: E402
from dwpm_core.facade import CoreFacade  # noqa: E402
from dwpm_core.operations import (  # noqa: E402
    OperationKnownFailureError,
    OperationUncertainError,
)
from dwpm_core.ports import PlatformPorts  # noqa: E402
from dwpm_core.protocol.wire import encode_utf  # noqa: E402


FIXTURES = json.loads(
    (ROOT / "shared_core" / "protocol_parity_fixtures.json").read_text(
        encoding="utf-8"
    )
)["fixtures"]


def response(opcode: int, payload: bytes) -> bytes:
    return (
        b"\x01\x01"
        + struct.pack(">qqBiHB", 0, 0, 0, len(payload), opcode, 0)
        + payload
    )


def login_8003() -> bytes:
    return (
        b"\x00"
        + encode_utf("登录成功")
        + struct.pack(">q", 123456789)
        + struct.pack(">qii", 1700000000000, 0, 1)
        + struct.pack(">qh", 202, 351)
        + encode_utf("利萍丰")
        + struct.pack(">b", 87)
        + encode_utf("魏")
        + encode_utf("抚远将军")
    )


class FixtureRawHttpPort:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.game_index = 0

    def exchange(self, request):
        value = dict(request)
        self.requests.append(value)
        url = str(value.get("url") or "")
        if url.endswith("common/area/list.action"):
            return {
                "status": 200,
                "body": (
                    "session-token`user-1\n"
                    "target`351`351区`http://game.test`x4`x5`x6`x7`x8`x9`x10`qzone_351\n"
                ).encode(),
            }
        if url.endswith("system/user/validate.action"):
            return {"status": 200, "body": b"ok`account-suffix"}
        if url.endswith("common/area/enter.action"):
            return {"status": 200, "body": b"1"}
        self.game_index += 1
        if self.game_index == 1:
            body = response(0x8003, login_8003())
        elif self.game_index in {2, 3}:
            body = response(
                0x8004,
                bytes.fromhex(FIXTURES["roleHead8004"]["responseHex"]),
            )
        elif self.game_index == 4:
            body = response(
                0x8104,
                bytes.fromhex(FIXTURES["inventory8104Compact"]["responseHex"]),
            )
        elif self.game_index == 5:
            body = response(
                0xE200,
                bytes.fromhex(FIXTURES["dailyActivityE200"]["responseHex"]),
            )
        elif self.game_index == 6:
            body = response(
                0x8310,
                bytes.fromhex(FIXTURES["raidFief8310"]["responseHex"]),
            )
        else:
            raise AssertionError(f"unexpected game request {self.game_index}")
        return {"status": 200, "body": body}


class MemoryCredentials:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def save_password(self, account_ref: str, password: str) -> None:
        self.values[str(account_ref)] = str(password)

    def load_password(self, account_ref: str):
        return self.values.get(str(account_ref))

    def delete(self, account_ref: str) -> None:
        self.values.pop(str(account_ref), None)


class MemorySessionSecrets:
    def __init__(self) -> None:
        self.values: dict[str, dict[str, str]] = {}

    def save(self, account_ref: str, values) -> None:
        self.values[str(account_ref)] = dict(values)

    def load(self, account_ref: str):
        return dict(self.values.get(str(account_ref)) or {})

    def delete(self, account_ref: str) -> None:
        self.values.pop(str(account_ref), None)


class RuntimeFacts:
    def __init__(self) -> None:
        self.commits: list[dict] = []
        self.started: list[str] = []
        self.hosted: set[str] = set()

    def commit_login(self, previous_account_ref, account_ref, runtime, mode):
        self.commits.append({
            "previous": previous_account_ref,
            "accountRef": account_ref,
            "runtime": dict(runtime),
            "mode": mode,
        })

    def start_hosting(self, account_ref: str) -> None:
        normalized = str(account_ref)
        self.started.append(normalized)
        self.hosted.add(normalized)

    def is_hosting(self, account_ref: str) -> bool:
        return str(account_ref) in self.hosted


class ExplodingGameCommandPort:
    def execute(self, *args, **kwargs):
        raise AssertionError("legacy host game command port must not be used")


class SingleGameRawHttpPort:
    def __init__(self) -> None:
        self.requests = []

    def exchange(self, request):
        self.requests.append(dict(request))
        return {"status": 200, "body": response(0xA110, b"heartbeat")}


class FailingGameRawHttpPort:
    def exchange(self, _request):
        return {"status": 502, "body": b""}


class SharedAccountLoginWorkflowTests(unittest.TestCase):
    def test_pure_workflow_owns_requests_parsers_and_normalized_facts(self) -> None:
        http = FixtureRawHttpPort()
        sent = []
        progress = []
        result = perform_shared_login(
            http,
            username="tester",
            password="secret",
            server_query="351区",
            platform="sglm",
            now_millis=lambda: 1700000000123,
            before_first_request=lambda: sent.append(True),
            progress=lambda value, detail: progress.append((value, dict(detail))),
        )
        self.assertEqual(result["accountRef"], "202")
        self.assertEqual(result["roleState"]["roleName"], "利萍丰")
        self.assertEqual(result["dm"], 123456789)
        self.assertEqual(result["area"]["serverKey"], "qzone_351")
        self.assertEqual(result["inventory"]["capacity"], 50)
        self.assertEqual(result["dailyActivity"]["treasureOccupied"]["current"], 1)
        self.assertEqual(result["ownedFiefs"][0]["targetId"], 101)
        self.assertEqual(sent, [True])
        self.assertEqual(http.game_index, 6)
        self.assertTrue(any(item[1]["phase"] == "game-login-base" for item in progress))
        self.assertNotIn("secret", json.dumps(result, ensure_ascii=False))

    def test_durable_add_and_start_commit_core_ledger_without_host_reentry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            credentials = MemoryCredentials()
            secrets = MemorySessionSecrets()
            runtime = RuntimeFacts()
            http = FixtureRawHttpPort()
            facade = CoreFacade(
                ROOT / "shared_core",
                str(Path(directory) / "operations.json"),
                ports=PlatformPorts(
                    credentials=credentials,
                    session_secrets=secrets,
                    raw_http=http,
                    account_runtime=runtime,
                ),
            )
            try:
                prepared = facade.account_add_prepare({
                    "username": "tester",
                    "serverQuery": "351区",
                    "platform": "sglm",
                    "passwordPresent": True,
                })
                draft = dict(prepared["plan"]["record"])
                draft_ref = draft["accountRef"]
                credentials.save_password(draft_ref, "secret")
                facade.account_record_upsert(draft)
                facade.register_account_login_routes()

                added = self._dispatch_and_wait(facade, "/api/accounts/add", draft_ref, "add")
                self.assertEqual(added["status"], "SUCCEEDED")
                self.assertEqual(added["result"]["accountRef"], "202")
                self.assertIsNone(
                    json.loads(facade.account_record_json(draft_ref))["account"]
                )
                stored = json.loads(facade.account_record_json("202"))["account"]
                self.assertFalse(stored["enabled"])
                self.assertEqual(stored["loginState"], "REAL_PROTOCOL_STOPPED")
                self.assertNotIn("dm", json.dumps(stored).lower())
                self.assertEqual(secrets.values["202"]["dm"], "123456789")
                self.assertEqual(runtime.started, [])

                http.game_index = 0
                started = self._dispatch_and_wait(facade, "/api/accounts/start", "202", "start")
                self.assertEqual(started["status"], "SUCCEEDED")
                self.assertEqual(
                    json.loads(facade.account_record_json("202"))["account"]["loginState"],
                    "ONLINE",
                )
                self.assertEqual(runtime.started, ["202"])
                operation_json = json.dumps(started, ensure_ascii=False).lower()
                self.assertNotIn("secret", operation_json)
                self.assertNotIn("123456789", operation_json)

                http.game_index = 0
                relogged = facade.relogin_account("202")
                self.assertTrue(relogged["ok"])
                self.assertEqual(relogged["accountRef"], "202")
                self.assertEqual(runtime.started, ["202", "202"])
            finally:
                facade.close()

    def test_json_prepare_maps_user_validation_to_structured_failure(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        try:
            result = json.loads(facade.account_add_prepare_json("{}"))
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"]["code"], "ACCOUNT_ADD_REJECTED")
            self.assertIn("账号", result["error"]["message"])
        finally:
            facade.close()

    def test_stale_enabled_area_without_runtime_evidence_is_superseded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            credentials = MemoryCredentials()
            secrets = MemorySessionSecrets()
            runtime = RuntimeFacts()
            http = FixtureRawHttpPort()
            facade = CoreFacade(
                ROOT / "shared_core",
                str(Path(directory) / "operations.json"),
                ports=PlatformPorts(
                    credentials=credentials,
                    session_secrets=secrets,
                    raw_http=http,
                    account_runtime=runtime,
                ),
            )
            try:
                credentials.save_password("202", "secret")
                facade.account_record_upsert({
                    "accountRef": "202",
                    "id": 202,
                    "username": "tester",
                    "serverName": "351区",
                    "serverQuery": "351区",
                    "platformKey": "sglm",
                    "enabled": False,
                    "loginState": "REAL_PROTOCOL_STOPPED",
                })
                facade.account_record_upsert({
                    "accountRef": "764",
                    "id": 764,
                    "username": "tester",
                    "serverName": "352区",
                    "enabled": True,
                    "loginState": "REAL_PROTOCOL_LOGIN_OK",
                })
                facade.register_account_login_routes()

                operation = self._dispatch_and_wait(
                    facade,
                    "/api/accounts/start",
                    "202",
                    "stale-duplicate",
                )

                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertEqual(
                    operation["result"]["supersededAccountRefs"],
                    ["764"],
                )
                stale = json.loads(
                    facade.account_record_json("764")
                )["account"]
                self.assertFalse(stale["enabled"])
                self.assertEqual(
                    stale["loginState"],
                    "REAL_PROTOCOL_STOPPED",
                )
                self.assertEqual(runtime.started, ["202"])
                self.assertGreater(len(http.requests), 0)
            finally:
                facade.close()

    def test_confirmed_live_area_still_blocks_duplicate_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            credentials = MemoryCredentials()
            secrets = MemorySessionSecrets()
            runtime = RuntimeFacts()
            runtime.hosted.add("764")
            http = FixtureRawHttpPort()
            facade = CoreFacade(
                ROOT / "shared_core",
                str(Path(directory) / "operations.json"),
                ports=PlatformPorts(
                    credentials=credentials,
                    session_secrets=secrets,
                    raw_http=http,
                    account_runtime=runtime,
                ),
            )
            try:
                credentials.save_password("202", "secret")
                facade.account_record_upsert({
                    "accountRef": "202",
                    "id": 202,
                    "username": "tester",
                    "serverName": "351区",
                    "serverQuery": "351区",
                    "platformKey": "sglm",
                    "enabled": False,
                    "loginState": "REAL_PROTOCOL_STOPPED",
                })
                facade.account_record_upsert({
                    "accountRef": "764",
                    "id": 764,
                    "username": "tester",
                    "serverName": "352区",
                    "platformKey": "sglm",
                    "enabled": True,
                    "loginState": "REAL_PROTOCOL_ONLINE",
                    "session": {
                        "accountId": 764,
                        "sourceMode": 1,
                        "publicState": {},
                    },
                })
                facade.register_account_login_routes()

                operation = self._dispatch_and_wait(
                    facade,
                    "/api/accounts/start",
                    "202",
                    "live-duplicate",
                )

                self.assertEqual(operation["status"], "FAILED")
                self.assertEqual(
                    operation["error"]["code"],
                    "ACCOUNT_DUPLICATE_RUNNING",
                )
                self.assertEqual(http.requests, [])
                self.assertTrue(
                    json.loads(facade.account_record_json("764"))[
                        "account"
                    ]["enabled"]
                )
            finally:
                facade.close()

    def test_authenticated_commands_use_python_packet_over_raw_http(self) -> None:
        raw_http = SingleGameRawHttpPort()
        session_secrets = MemorySessionSecrets()
        session_secrets.save("202", {"dm": "123456789", "userId": "u"})
        facade = CoreFacade(
            ROOT / "shared_core",
            ports=PlatformPorts(
                session_secrets=session_secrets,
                raw_http=raw_http,
                game_commands=ExplodingGameCommandPort(),
            ),
        )
        try:
            facade.account_record_upsert({
                "accountRef": "202",
                "id": 202,
                "username": "tester",
                "platformKey": "sglm",
                "enabled": True,
                "loginState": "ONLINE",
                "session": {
                    "accountId": 202,
                    "sourceMode": 1,
                    "publicState": {
                        "gameHttp": "http://game.test/kingWapServer/HttpClient",
                    },
                },
            })
            fact = facade._execute_host_game_command(
                "202",
                0x3110,
                b"\x01\x00",
                "test/heartbeat",
                {"readOnly": True},
                mutation_sent=False,
            )
            self.assertEqual(fact["requestOpcode"], 0x3110)
            self.assertEqual(fact["packets"][0]["opcode"], 0xA110)
            self.assertEqual(fact["packets"][0]["payload"], b"heartbeat")
            request = raw_http.requests[0]
            self.assertTrue(request["requireExecutionOwner"])
            self.assertEqual(request["requestOpcode"], 0x3110)
            self.assertEqual(
                request["headers"]["Content-Type"],
                "application/x-www-form-urlencoded",
            )
            self.assertIn("Dalvik/2.1.0", request["headers"]["User-Agent"])
            self.assertEqual(request["gameCommands"], [{
                "opcode": 0x3110,
                "payloadHex": "0100",
            }])
            self.assertIn(b"\x31\x10", request["body"])
        finally:
            facade.close()

    def test_sent_mutation_http_502_is_uncertain_and_read_is_retryable(self) -> None:
        secrets = MemorySessionSecrets()
        secrets.save("202", {"dm": "123456789"})
        facade = CoreFacade(
            ROOT / "shared_core",
            ports=PlatformPorts(
                session_secrets=secrets,
                raw_http=FailingGameRawHttpPort(),
            ),
        )
        try:
            facade.account_record_upsert({
                "accountRef": "202",
                "id": 202,
                "platformKey": "sglm",
                "enabled": True,
                "loginState": "ONLINE",
                "session": {
                    "accountId": 202,
                    "sourceMode": 1,
                    "publicState": {
                        "gameHttp": "http://game.test/kingWapServer/HttpClient",
                    },
                },
            })
            with self.assertRaisesRegex(
                OperationUncertainError,
                "禁止自动重做",
            ):
                facade._execute_host_game_command(
                    "202",
                    0x140C,
                    b"\x00" * 24,
                    "test/mutation",
                    {},
                    mutation_sent=True,
                )
            with self.assertRaises(OperationKnownFailureError):
                facade._execute_host_game_command(
                    "202",
                    0x1016,
                    b"",
                    "test/query",
                    {"readOnly": True},
                    mutation_sent=False,
                )
        finally:
            facade.close()

    def _dispatch_and_wait(self, facade, path: str, account_ref: str, suffix: str):
        accepted = facade.dispatch(
            "POST",
            path,
            {"accountRef": account_ref},
            {"requestId": f"login-{suffix}-{time.time_ns()}"},
        )
        self.assertEqual(accepted.status, 202)
        operation_id = accepted.body["operationId"]
        deadline = time.time() + 3
        operation = None
        while time.time() < deadline:
            operation = facade.operation_status(operation_id)["operation"]
            if operation["status"] in {"SUCCEEDED", "FAILED", "UNCERTAIN"}:
                return operation
            time.sleep(0.01)
        self.fail(f"operation did not finish: {operation}")


if __name__ == "__main__":
    unittest.main()
