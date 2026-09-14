from __future__ import annotations

import json
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "captives"

from dwpm_core import CoreFacade  # noqa: E402
from dwpm_core.automation import resident_due_decision  # noqa: E402
from dwpm_core.features.captives import (  # noqa: E402
    PERSUADE_COOLDOWN_MILLIS,
    build_persuade_payload,
    build_prisoner_info_payload,
    build_release_payload,
    normalize_captive_policy,
    parse_persuade_response,
    parse_prisoner_info_response,
    parse_release_response,
    plan_captive_actions,
    recover_captives_from_8004,
)
from dwpm_core.operations import OperationUncertainError  # noqa: E402
from dwpm_core.ports import PlatformPorts  # noqa: E402


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _packet(fixture: dict, opcode: int) -> bytes:
    for packet in fixture["response"]:
        if int(packet["opcode"]) == opcode:
            return bytes.fromhex(packet["payloadHex"])
    raise AssertionError(f"fixture 缺少 0x{opcode:04x} 响应包")


def _request_payload(fixture: dict, opcode: int) -> bytes:
    for command in fixture["request"]:
        if int(command["opcode"]) == opcode:
            return bytes.fromhex(command["payloadHex"])
    raise AssertionError(f"fixture 缺少 0x{opcode:04x} 请求")


class FixedClock:
    def __init__(self, value: int = 40_000_000) -> None:
        self.value = value

    def now_millis(self) -> int:
        return self.value


class RecordingLogPort:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def write(self, event) -> None:
        self.events.append(dict(event))

    def user_messages(self) -> list[str]:
        return [
            str(event.get("message"))
            for event in self.events
            if str(event.get("audience") or "") == "user"
        ]


class FakeExecution:
    operation_id = "op_captives_fixture"

    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def mark_request_sent(self, metadata=None) -> None:
        self.sent.append(dict(metadata or {}))

    def publish_progress(self, _progress: int, _details=None) -> None:
        return None

    def raise_if_cancelled(self) -> None:
        return None

    def wait(self, _seconds: float) -> None:
        return None


class CaptiveWireFixtureTests(unittest.TestCase):
    """The protocol layer reads today's capture exactly as the client did."""

    def test_persuade_success_receipt_carries_both_rebuilt_tables(self) -> None:
        receipt = parse_persuade_response(
            _packet(_fixture("persuade_success"), 0x8234)
        )
        self.assertTrue(receipt["success"])
        self.assertEqual(receipt["status"], 0)
        self.assertEqual(receipt["message"], "恭喜您劝降成功！")
        self.assertFalse(receipt["cooldown"])
        self.assertEqual(receipt["generalCount"], 15)
        self.assertEqual(len(receipt["captives"]), 19)

    def test_persuade_cooldown_receipt_is_a_confirmed_business_result(self) -> None:
        receipt = parse_persuade_response(
            _packet(_fixture("persuade_cooldown"), 0x8234)
        )
        self.assertFalse(receipt["success"])
        self.assertEqual(receipt["status"], 249)
        self.assertTrue(receipt["cooldown"])
        self.assertEqual(receipt["message"], "劝降失败，您需要等待下次劝降！")
        self.assertEqual(len(receipt["captives"]), 18)

    def test_release_receipt_lists_the_remaining_captives(self) -> None:
        receipt = parse_release_response(
            _packet(_fixture("release_success"), 0x8236)
        )
        self.assertTrue(receipt["success"])
        self.assertEqual(receipt["status"], 0)
        self.assertEqual(len(receipt["captives"]), 18)

    def test_prisoner_info_receipt_carries_copper_and_gold_prices(self) -> None:
        info = parse_prisoner_info_response(
            _packet(_fixture("prisoner_info"), 0x8233)
        )
        self.assertEqual(info["copperCost"], 125)
        self.assertEqual(info["goldCost"], 1)

    def test_role_state_8004_recovers_the_whole_captive_table(self) -> None:
        captives = recover_captives_from_8004(
            _fixture("role_state_8004")["payloadHex"]
        )
        self.assertEqual(len(captives), 21)
        for captive in captives:
            self.assertEqual(captive["status"], 3)
            self.assertEqual(captive["statusText"], "俘")
            self.assertEqual(captive["prisonFiefName"], "宿代苑基地")
            self.assertGreater(captive["prisonFiefId"], 0)
            self.assertGreaterEqual(captive["growth"], 1)

    def test_request_builders_reproduce_the_captured_bytes(self) -> None:
        for name, opcode, builder in (
            ("persuade_success", 0x1234, build_persuade_payload),
            ("release_success", 0x1236, build_release_payload),
        ):
            captured = _request_payload(_fixture(name), opcode)
            fief_id, captive_id, _pay = struct.unpack(">qqB", captured)
            self.assertEqual(builder(fief_id, captive_id), captured)
        info_request = _request_payload(_fixture("prisoner_info"), 0x1233)
        captive_id = int.from_bytes(info_request[1:], "big", signed=True)
        self.assertEqual(build_prisoner_info_payload(captive_id), info_request)

    def test_persuade_host_is_the_prison_fief_not_the_role(self) -> None:
        captured = _request_payload(_fixture("persuade_success"), 0x1234)
        fief_id, captive_id, pay_mode = struct.unpack(">qqB", captured)
        self.assertEqual(fief_id, 205)
        self.assertNotEqual(fief_id, captive_id)
        self.assertEqual(pay_mode, 0)


class CaptivePolicyTests(unittest.TestCase):
    """Table-driven growth-threshold decisions, the operator's own rule."""

    @staticmethod
    def _captive(
        captive_id: int,
        growth: int,
        *,
        available_at: int = 0,
    ) -> dict[str, object]:
        return {
            "id": captive_id,
            "name": f"俘虏{captive_id}",
            "growth": growth,
            "level": 14,
            "kind": "弓将",
            "prisonFiefId": 205,
            "persuadeAvailableAtMillis": available_at,
        }

    def test_normalize_defaults_to_fully_disabled(self) -> None:
        policy = normalize_captive_policy({})
        self.assertFalse(policy["releaseEnabled"])
        self.assertFalse(policy["persuadeEnabled"])
        self.assertEqual(policy["payMode"], 0)

    def test_normalize_clamps_thresholds_to_the_wire_range(self) -> None:
        policy = normalize_captive_policy({
            "captiveRelease": True,
            "captiveReleaseBelowGrowth": 999,
            "captivePersuade": True,
            "captivePersuadeGrowth": -3,
        })
        self.assertEqual(policy["releaseBelowGrowth"], 200)
        self.assertEqual(policy["persuadeAtOrAboveGrowth"], 1)

    def test_plan_decision_table(self) -> None:
        policy = {
            "releaseEnabled": True,
            "releaseBelowGrowth": 60,
            "persuadeEnabled": True,
            "persuadeAtOrAboveGrowth": 80,
            "payMode": 0,
        }
        cases = [
            # (captive, expected action)
            (self._captive(1, 59), "release"),
            (self._captive(2, 80), "persuade"),
            (self._captive(3, 70), "keep"),
            (self._captive(4, 95, available_at=2_000), "wait"),
        ]
        planned = plan_captive_actions([c for c, _ in cases], policy, now_millis=1_000)
        for row, (_captive, expected) in zip(planned, cases):
            with self.subTest(captive=row["name"], expected=expected):
                self.assertEqual(row["action"], expected)
        waiting = next(row for row in planned if row["action"] == "wait")
        self.assertEqual(waiting["availableAtMillis"], 2_000)

    def test_plan_respects_the_round_action_limit(self) -> None:
        policy = {
            "releaseEnabled": True,
            "releaseBelowGrowth": 100,
            "persuadeEnabled": False,
            "persuadeAtOrAboveGrowth": 100,
            "payMode": 0,
        }
        captives = [self._captive(index, 50) for index in range(1, 5)]
        planned = plan_captive_actions(
            captives, policy, now_millis=1_000, limit=2
        )
        self.assertEqual(
            [row["action"] for row in planned],
            ["release", "release", "defer", "defer"],
        )

    def test_plan_with_only_persuade_never_releases(self) -> None:
        policy = {
            "releaseEnabled": False,
            "releaseBelowGrowth": 60,
            "persuadeEnabled": True,
            "persuadeAtOrAboveGrowth": 80,
            "payMode": 0,
        }
        planned = plan_captive_actions(
            [self._captive(1, 50), self._captive(2, 90)],
            policy,
            now_millis=1_000,
        )
        self.assertEqual(
            [row["action"] for row in planned], ["keep", "persuade"]
        )

    def test_real_captives_all_release_below_the_operators_threshold(self) -> None:
        captives = recover_captives_from_8004(
            _fixture("role_state_8004")["payloadHex"]
        )
        policy = normalize_captive_policy({
            "captiveRelease": True,
            "captiveReleaseBelowGrowth": 70,
            "captivePersuade": True,
            "captivePersuadeGrowth": 70,
        })
        planned = plan_captive_actions(captives, policy, now_millis=1_000)
        self.assertEqual(len(planned), 21)
        self.assertTrue(
            all(row["growth"] < 70 for row in planned),
            "fixture 里 21 名俘虏成长均低于 70",
        )
        self.assertEqual(
            {row["action"] for row in planned}, {"release", "defer"}
        )
        self.assertEqual(
            sum(1 for row in planned if row["action"] == "release"), 10
        )


class SharedCaptivesResidentTests(unittest.TestCase):
    """The feature wired end to end: settings, tick, send discipline, records."""

    def _facade(self):
        directory = tempfile.TemporaryDirectory()
        clock = FixedClock()
        logs = RecordingLogPort()
        facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(Path(directory.name) / "operations.json"),
            ports=PlatformPorts(clock=clock, logs=logs),
        )
        facade.account_record_upsert({
            "accountRef": "303",
            "id": 303,
            "enabled": True,
            "loginState": "ONLINE",
            "session": {
                "accountId": 303,
                "sourceMode": 1,
                "publicState": {"roleId": "303"},
            },
        })
        return facade, clock, logs, directory

    @staticmethod
    def _habits(**overrides: object) -> dict[str, object]:
        captives: dict[str, object] = {
            "captiveRelease": True,
            "captiveReleaseBelowGrowth": 70,
            "captivePersuade": True,
            "captivePersuadeGrowth": 70,
        }
        captives.update(overrides)
        return {"captives": captives}

    def _configure(self, facade: CoreFacade, **overrides: object) -> None:
        configured = facade.configure_resident_automation_from_habits(
            "303", self._habits(**overrides)
        )
        self.assertTrue(configured["captivesEnabled"])
        facade.set_resident_automation_activation("303", True, ["captives"])

    def _install_fake_transport(
        self,
        facade: CoreFacade,
        *,
        action_packets: dict[int, list[dict[str, object]]],
    ) -> list[int]:
        sent_opcodes: list[int] = []
        role_state = bytes.fromhex(_fixture("role_state_8004")["payloadHex"])

        def fake_execute(
            _self,
            account_ref: str,
            opcode: int,
            payload: bytes,
            phase: str,
            context: dict,
            *,
            mutation_sent: bool,
        ) -> dict[str, object]:
            sent_opcodes.append(int(opcode))
            if int(opcode) == 0x1016:
                packets = [{"opcode": 0x8004, "payload": role_state}]
            else:
                packets = list(action_packets.get(int(opcode), []))
            return {
                "requestOpcode": int(opcode),
                "httpCode": 200,
                "httpOk": True,
                "responseBytes": sum(len(p["payload"]) for p in packets),
                "packets": packets,
            }

        facade._execute_host_game_command = types.MethodType(  # noqa: SLF001
            fake_execute, facade
        )
        return sent_opcodes

    @staticmethod
    def _fixture_packets(fixture_name: str, *opcodes: int) -> list[dict[str, object]]:
        fixture = _fixture(fixture_name)
        return [
            {"opcode": int(packet["opcode"]), "payload": bytes.fromhex(packet["payloadHex"])}
            for packet in fixture["response"]
            if int(packet["opcode"]) in opcodes
        ]

    def _tick(self, facade: CoreFacade) -> dict[str, object]:
        return facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["captives"]}
        )

    def _public_state(self, facade: CoreFacade) -> dict[str, object]:
        record = json.loads(facade.account_record_json("303"))["account"]
        return record["session"]["publicState"]

    def test_habits_normalize_and_activate_captives(self) -> None:
        facade, _clock, _logs, directory = self._facade()
        try:
            configured = facade.configure_resident_automation_from_habits(
                "303", self._habits()
            )
            self.assertTrue(configured["captivesEnabled"])
            activation = facade.set_resident_automation_activation("303", True)
            record = json.loads(facade.account_record_json("303"))["account"]
            keys = str(
                record["session"]["publicState"]["activeResidentTaskKeys"]
            )
            self.assertIn("captives", keys.split(","))
            self.assertTrue(activation["ok"] if "ok" in activation else True)

            disabled = facade.configure_resident_automation_from_habits(
                "303", {"captives": {"captiveRelease": False}}
            )
            self.assertFalse(disabled["captivesEnabled"])
        finally:
            facade.close()
            directory.cleanup()

    def test_due_reducer_selects_configured_captives(self) -> None:
        decision = resident_due_decision(
            {"captives": {"enabled": True, "settings": {}}},
            {},
            now_millis=1_000,
            saved_tasks_started=True,
            active_keys={"captives"},
            priorities={"captives": 45},
        )
        self.assertEqual(decision["feature"], "captives")

    def test_tick_releases_one_captive_and_records_it(self) -> None:
        facade, clock, logs, directory = self._facade()
        try:
            self._configure(facade, captivePersuade=False)
            sent = self._install_fake_transport(
                facade,
                action_packets={
                    0x1236: self._fixture_packets("release_success", 0x8236),
                },
            )
            captives = recover_captives_from_8004(
                _fixture("role_state_8004")["payloadHex"]
            )
            first = sorted(captives, key=lambda row: int(row["id"]))[0]

            result = self._tick(facade)

            self.assertEqual(result["feature"], "captives")
            self.assertEqual(result["state"], "completed")
            self.assertTrue(result["success"])
            self.assertEqual(sent, [0x1016, 0x1236])
            expected = f"已释放 {first['name']}（成长{first['growth']}）"
            self.assertEqual(result["message"], expected)
            # More captives remain actionable, so the lane wakes quickly.
            self.assertEqual(result["nextWakeAtMillis"], clock.value + 1_000)
            self.assertIn(f"俘虏：{expected}", logs.user_messages())
            records = json.loads(
                self._public_state(facade)["successRecordsJson"]
            )
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["category"], "俘虏")
            self.assertEqual(records[0]["message"], expected)
            # The send boundary closed synchronously; nothing is left pending.
            self.assertEqual(
                self._public_state(facade)["captivesPendingActionJson"], "{}"
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_tick_persuades_one_captive_and_records_it(self) -> None:
        facade, clock, logs, directory = self._facade()
        try:
            self._configure(
                facade,
                captiveRelease=False,
                captivePersuadeGrowth=50,
            )
            sent = self._install_fake_transport(
                facade,
                action_packets={
                    0x1234: self._fixture_packets("persuade_success", 0x8234),
                },
            )
            captives = recover_captives_from_8004(
                _fixture("role_state_8004")["payloadHex"]
            )
            first = sorted(captives, key=lambda row: int(row["id"]))[0]

            result = self._tick(facade)

            self.assertEqual(result["state"], "completed")
            self.assertEqual(sent, [0x1016, 0x1234])
            expected = f"劝降成功 {first['name']}（成长{first['growth']}）"
            self.assertEqual(result["message"], expected)
            self.assertIn(f"俘虏：{expected}", logs.user_messages())
        finally:
            facade.close()
            directory.cleanup()

    def test_persuade_cooldown_is_recorded_not_raised(self) -> None:
        facade, clock, _logs, directory = self._facade()
        try:
            self._configure(
                facade,
                captiveRelease=False,
                captivePersuadeGrowth=50,
            )
            self._install_fake_transport(
                facade,
                action_packets={
                    0x1234: self._fixture_packets("persuade_cooldown", 0x8234),
                },
            )
            captives = recover_captives_from_8004(
                _fixture("role_state_8004")["payloadHex"]
            )
            first = sorted(captives, key=lambda row: int(row["id"]))[0]

            result = self._tick(facade)

            self.assertEqual(result["state"], "waiting")
            self.assertTrue(result["success"])
            self.assertIn("冷却1小时", str(result["message"]))
            # The boundary closed on a confirmed business result.
            public = self._public_state(facade)
            self.assertEqual(public["captivesPendingActionJson"], "{}")
            state = json.loads(public["residentAutomationStateJson"])
            cooldowns = state["captives"]["captiveCooldowns"]
            self.assertEqual(
                cooldowns[str(first["id"])],
                clock.value + PERSUADE_COOLDOWN_MILLIS,
            )
            # The next tick plans around the recorded lock: the same captive
            # now reports wait instead of persuade.
            policy = normalize_captive_policy({
                "captivePersuade": True,
                "captivePersuadeGrowth": 50,
            })
            first["persuadeAvailableAtMillis"] = cooldowns[str(first["id"])]
            planned = plan_captive_actions(
                [first], policy, now_millis=clock.value
            )
            self.assertEqual(planned[0]["action"], "wait")
        finally:
            facade.close()
            directory.cleanup()

    def test_a_missing_receipt_is_uncertain_and_never_resent(self) -> None:
        facade, _clock, _logs, directory = self._facade()
        try:
            self._configure(
                facade,
                captiveRelease=False,
                captivePersuadeGrowth=50,
            )
            sent = self._install_fake_transport(facade, action_packets={})

            with self.assertRaises(OperationUncertainError):
                self._tick(facade)
            self.assertEqual(sent, [0x1016, 0x1234])
            pending = json.loads(
                self._public_state(facade)["captivesPendingActionJson"]
            )
            self.assertEqual(pending["sendState"], "uncertain")

            # The next tick observes before anything else may send: the
            # captive is still there and unchanged, so the feature stops for a
            # human instead of replaying the mutation.
            result = self._tick(facade)
            self.assertEqual(result["feature"], "captives")
            self.assertEqual(result["state"], "blocked")
            self.assertTrue(result["requiresAttention"])
            self.assertIn("禁止自动重发", str(result["message"]))
            self.assertEqual(sent.count(0x1234), 1)
        finally:
            facade.close()
            directory.cleanup()

    def test_uncertain_persuade_recovers_when_the_captive_is_gone(self) -> None:
        facade, clock, _logs, directory = self._facade()
        try:
            self._configure(
                facade,
                captiveRelease=False,
                captivePersuadeGrowth=50,
            )
            self._install_fake_transport(facade, action_packets={})
            with self.assertRaises(OperationUncertainError):
                self._tick(facade)
            pending = json.loads(
                self._public_state(facade)["captivesPendingActionJson"]
            )

            # Observation: the captive left the table - the persuade landed.
            captives = recover_captives_from_8004(
                _fixture("role_state_8004")["payloadHex"]
            )
            action = dict(pending["action"])
            remaining = [
                row for row in captives if int(row["id"]) != int(action["captiveId"])
            ]
            result = facade._recover_captives_pending(  # noqa: SLF001
                "303", pending, remaining, now_millis=clock.value
            )
            self.assertEqual(result["state"], "completed")
            self.assertTrue(result["success"])
            self.assertEqual(
                result["captiveAction"]["captiveId"], action["captiveId"]
            )
            self.assertEqual(
                self._public_state(facade)["captivesPendingActionJson"], "{}"
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_uncertain_persuade_recovers_a_visible_failed_attempt(self) -> None:
        facade, clock, _logs, directory = self._facade()
        try:
            self._configure(
                facade,
                captiveRelease=False,
                captivePersuadeGrowth=50,
            )
            self._install_fake_transport(facade, action_packets={})
            with self.assertRaises(OperationUncertainError):
                self._tick(facade)
            pending = json.loads(
                self._public_state(facade)["captivesPendingActionJson"]
            )
            captives = recover_captives_from_8004(
                _fixture("role_state_8004")["payloadHex"]
            )
            action = dict(pending["action"])
            observed = []
            for row in captives:
                row = dict(row)
                if int(row["id"]) == int(action["captiveId"]):
                    # The attempt landed and failed: count +1, cooldown base set.
                    row["persuadeCount"] = int(row["persuadeCount"]) + 1
                    row["persuadeCooldownBaseMillis"] = clock.value
                    row["persuadeAvailableAtMillis"] = (
                        clock.value + PERSUADE_COOLDOWN_MILLIS
                    )
                observed.append(row)

            result = facade._recover_captives_pending(  # noqa: SLF001
                "303", pending, observed, now_millis=clock.value
            )
            self.assertEqual(result["state"], "waiting")
            self.assertTrue(result["success"])
            self.assertEqual(
                result["captiveCooldowns"][str(action["captiveId"])],
                clock.value + PERSUADE_COOLDOWN_MILLIS,
            )
            self.assertEqual(
                self._public_state(facade)["captivesPendingActionJson"], "{}"
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_an_empty_prison_waits_for_the_next_poll(self) -> None:
        facade, clock, _logs, directory = self._facade()
        try:
            self._configure(facade)
            sent: list[int] = []

            def fake_execute(
                _self,
                account_ref: str,
                opcode: int,
                payload: bytes,
                phase: str,
                context: dict,
                *,
                mutation_sent: bool,
            ) -> dict[str, object]:
                sent.append(int(opcode))
                return {
                    "requestOpcode": int(opcode),
                    "httpCode": 200,
                    "httpOk": True,
                    "responseBytes": 0,
                    "packets": [{"opcode": 0x8004, "payload": b"\x00" * 64}],
                }

            facade._execute_host_game_command = types.MethodType(  # noqa: SLF001
                fake_execute, facade
            )
            result = self._tick(facade)
            self.assertEqual(result["feature"], "captives")
            self.assertEqual(result["state"], "waiting")
            self.assertTrue(result["success"])
            self.assertEqual(result["message"], "俘虏营当前没有俘虏")
            self.assertEqual(result["nextWakeAtMillis"], clock.value + 600_000)
            self.assertEqual(sent, [0x1016])
        finally:
            facade.close()
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
