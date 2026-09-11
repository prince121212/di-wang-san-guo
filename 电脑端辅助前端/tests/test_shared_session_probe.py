from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = ROOT / "shared_core" / "python"
if str(CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CORE_SOURCE))

from dwpm_core import CoreFacade
from dwpm_core.ports import PlatformPorts
from shared_raw_http_test_host import (
    FIXTURE_GAME_HTTP,
    _decode_single_request,
    _encode_response,
)


class FixedClock:
    def __init__(self, now_millis: int = 1_785_551_234_000) -> None:
        self.value = now_millis

    def now_millis(self) -> int:
        return self.value


class FixtureSecrets:
    def __init__(self, dm: int = 202) -> None:
        self.dm = dm

    def save(self, _account_ref, _values):
        return None

    def load(self, _account_ref):
        return {"dm": str(self.dm)}

    def delete(self, _account_ref):
        return None


class ScriptedRawHttp:
    def __init__(self, handler) -> None:
        self.handler = handler
        self.commands = []

    def exchange(self, request):
        opcode, payload = _decode_single_request(bytes(request["body"]))
        self.commands.append((opcode, payload, dict(request)))
        packets = self.handler(opcode, payload, len(self.commands))
        return {"status": 200, "body": _encode_response(packets)}


class SharedSessionProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixtures = json.loads(
            (ROOT / "shared_core" / "protocol_parity_fixtures.json").read_text(
                encoding="utf-8"
            )
        )["fixtures"]

    def _facade(self, directory: str, raw_http, *, dm: int = 202) -> CoreFacade:
        facade = CoreFacade(
            ROOT / "shared_core",
            str(Path(directory) / "operations.json"),
            ports=PlatformPorts(
                clock=FixedClock(),
                raw_http=raw_http,
                session_secrets=FixtureSecrets(dm),
            ),
        )
        facade.account_record_upsert({
            "accountRef": "202",
            "id": 202,
            "username": "probe-fixture",
            "platformKey": "sglm",
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
        return facade

    def test_negative_signed_dm_is_a_valid_opaque_session_value(self) -> None:
        raw_http = ScriptedRawHttp(
            lambda opcode, _payload, _call: [
                {"opcode": 0xA110, "payloadHex": "010203"}
            ] if opcode == 0x3110 else []
        )
        with tempfile.TemporaryDirectory() as directory:
            facade = self._facade(
                directory,
                raw_http,
                dm=-0x102030405060708,
            )
            try:
                result = facade.probe_account_session("202", False)
            finally:
                facade.close()

        self.assertEqual(result["status"], "valid")
        self.assertEqual(raw_http.commands[0][0], 0x3110)

    def test_zero_dm_still_means_session_missing(self) -> None:
        raw_http = ScriptedRawHttp(
            lambda _opcode, _payload, _call: []
        )
        with tempfile.TemporaryDirectory() as directory:
            facade = self._facade(directory, raw_http, dm=0)
            try:
                result = facade.probe_account_session("202", False)
            finally:
                facade.close()

        self.assertEqual(result["status"], "unavailable")
        self.assertIn("缺少已验证 Session", result["reason"])
        self.assertEqual(raw_http.commands, [])

    def test_heartbeat_probe_uses_python_packet_and_accepts_a110(self) -> None:
        raw_http = ScriptedRawHttp(
            lambda opcode, _payload, _call: [
                {"opcode": 0xA110, "payloadHex": "010203"}
            ] if opcode == 0x3110 else []
        )
        with tempfile.TemporaryDirectory() as directory:
            facade = self._facade(directory, raw_http)
            try:
                result = facade.probe_account_session("202", False)
                account = facade.account_records_snapshot()["accounts"][0]
            finally:
                facade.close()

        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["updates"]["militaryIntelPayloadHex"], "010203")
        self.assertEqual(result["updates"]["lastValidatedAt"], "1785551234000")
        self.assertEqual(raw_http.commands[0][0:2], (0x3110, b"\x01\x00"))
        self.assertTrue(raw_http.commands[0][2]["requireExecutionOwner"])
        self.assertEqual(raw_http.commands[0][2]["readTimeoutMillis"], 8_000)
        self.assertEqual(
            account["session"]["publicState"]["lastSuccessfulGameResponseAt"],
            "1785551234000",
        )

    def test_heartbeat_timeout_immediately_falls_back_to_role_state(self) -> None:
        state_payload = bytes.fromhex(
            self.fixtures["roleHead8004"]["responseHex"]
            + self.fixtures["generalRecord8004"]["responseHex"]
            + self.fixtures["idleArmy8004"]["responseHex"]
        )

        def handler(opcode, _payload, call):
            if opcode == 0x3110 and call == 1:
                raise TimeoutError("heartbeat timeout")
            if opcode == 0x1016:
                return [{"opcode": 0x8004, "payloadHex": state_payload.hex()}]
            if opcode == 0x3110:
                return [{"opcode": 0xA110, "payloadHex": "aabb"}]
            raise AssertionError(f"unexpected probe opcode {opcode:#x}")

        raw_http = ScriptedRawHttp(handler)
        with tempfile.TemporaryDirectory() as directory:
            facade = self._facade(directory, raw_http)
            try:
                result = facade.probe_account_session("202", False)
            finally:
                facade.close()

        self.assertEqual(result["status"], "valid")
        self.assertIn("即时兜底", result["reason"])
        self.assertEqual(
            [row[0] for row in raw_http.commands],
            [0x3110, 0x1016, 0x3110],
        )
        self.assertEqual(raw_http.commands[0][2]["readTimeoutMillis"], 8_000)
        self.assertEqual(raw_http.commands[1][2]["readTimeoutMillis"], 20_000)

    def test_full_probe_projects_8004_state_and_optional_heartbeat(self) -> None:
        state_payload = bytes.fromhex(
            self.fixtures["roleHead8004"]["responseHex"]
            + self.fixtures["generalRecord8004"]["responseHex"]
            + self.fixtures["idleArmy8004"]["responseHex"]
        )

        def handler(opcode, _payload, _call):
            if opcode == 0x1016:
                return [{"opcode": 0x8004, "payloadHex": state_payload.hex()}]
            if opcode == 0x3110:
                return [{"opcode": 0xA110, "payloadHex": "aabb"}]
            raise AssertionError(f"unexpected probe opcode {opcode:#x}")

        raw_http = ScriptedRawHttp(handler)
        with tempfile.TemporaryDirectory() as directory:
            facade = self._facade(directory, raw_http)
            try:
                result = facade.probe_account_session("202", True)
            finally:
                facade.close()

        self.assertEqual(result["status"], "valid")
        updates = result["updates"]
        self.assertEqual(updates["roleId"], "202")
        self.assertEqual(updates["roleName"], "利萍丰")
        self.assertEqual(json.loads(updates["generalsJson"])[0]["id"], 528290)
        self.assertEqual(json.loads(updates["armyJson"])[0]["idleCount"], 120)
        self.assertEqual(updates["militaryIntelPayloadHex"], "aabb")
        self.assertEqual([row[0] for row in raw_http.commands], [0x1016, 0x3110])

    def test_explicit_8016_and_compact_fffc_are_expired(self) -> None:
        for packets in (
            [{"opcode": 0x8016, "payloadHex": "000ce6b2a1e69c89e8a792e889b2"}],
            [{"opcode": 0xFFFC, "payloadHex": "00"}],
        ):
            with self.subTest(packets=packets):
                raw_http = ScriptedRawHttp(
                    lambda _opcode, _payload, _call, value=packets: value
                )
                with tempfile.TemporaryDirectory() as directory:
                    facade = self._facade(directory, raw_http)
                    try:
                        result = facade.probe_account_session("202", True)
                    finally:
                        facade.close()
                self.assertEqual(result["status"], "expired")

    def test_transport_failure_is_unavailable_not_expired(self) -> None:
        class FailingRawHttp:
            def exchange(self, _request):
                raise TimeoutError("network timeout")

        with tempfile.TemporaryDirectory() as directory:
            facade = self._facade(directory, FailingRawHttp())
            try:
                result = facade.probe_account_session("202", False)
            finally:
                facade.close()

        self.assertEqual(result["status"], "unavailable")
        self.assertIn("network timeout", result["reason"])


if __name__ == "__main__":
    unittest.main()
