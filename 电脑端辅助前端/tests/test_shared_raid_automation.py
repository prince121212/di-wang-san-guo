from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core import CoreFacade  # noqa: E402
from dwpm_core.features.expedition import (  # noqa: E402
    build_raid_expedition_payload,
    build_raid_prepare_payload,
)
from dwpm_core.operations import OperationUncertainError  # noqa: E402
from dwpm_core.ports import PlatformPorts  # noqa: E402


class FixedClock:
    def __init__(self, value: int = 20_000_000) -> None:
        self.value = value

    def now_millis(self) -> int:
        return self.value


class FakeExecution:
    operation_id = "op_raid_fixture"

    def __init__(self) -> None:
        self.sent = []

    def mark_request_sent(self, metadata=None) -> None:
        self.sent.append(dict(metadata or {}))

    def publish_progress(self, _progress: int, _details=None) -> None:
        return None

    def raise_if_cancelled(self) -> None:
        return None

    def wait(self, _seconds: float) -> None:
        return None


class SharedRaidAutomationTests(unittest.TestCase):
    def _facade(self):
        directory = tempfile.TemporaryDirectory()
        clock = FixedClock()
        facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(Path(directory.name) / "operations.json"),
            ports=PlatformPorts(clock=clock),
        )
        facade.account_record_upsert({
            "accountRef": "202",
            "id": 202,
            "username": "raid-fixture",
            "enabled": True,
            "loginState": "ONLINE",
            "session": {
                "accountId": 202,
                "sourceMode": 1,
                "publicState": {
                    "roleId": "202",
                    "lastValidatedAt": str(clock.value),
                    "generalsJson": "[]",
                },
            },
        })
        return facade, clock, directory

    @staticmethod
    def _general(status: int) -> dict:
        status_text = "闲" if status == 0 else "战"
        return {
            "id": 1,
            "idHex": "0000000000000001",
            "name": "将领1",
            "status": status,
            "statusText": status_text,
            "displayStatus": status_text,
            "energyReliable": True,
            "tili": 300,
            "soldierTypeCode": 3,
            "soldierCount": 100,
            "currentSoldierCount": 100,
        }

    def _install_preflight(self, facade: CoreFacade) -> None:
        selected = [self._general(0)]
        facade._run_raid_fiefs_game_workflow = types.MethodType(  # noqa: SLF001
            lambda self, *_args, **_kwargs: {
                "ok": True,
                "fiefs": [{
                    "index": 1,
                    "targetId": 101,
                    "fiefName": "一号封地",
                    "cityName": "洛阳",
                    "x": 91,
                    "y": 26,
                }],
            },
            facade,
        )
        facade._run_expedition_preflight = types.MethodType(  # noqa: SLF001
            lambda self, *_args, **_kwargs: (
                [dict(row) for row in selected],
                {"generalIds": [1]},
            ),
            facade,
        )

    def test_raid_dispatch_uses_shared_payload_then_waits_for_idle(self) -> None:
        facade, clock, directory = self._facade()
        try:
            self._install_preflight(facade)
            calls: list[tuple[int, bytes]] = []

            def command(self, _account, opcode, payload, _phase, _context, *, mutation_sent):
                stored = json.loads(self.account_record_json("202"))["account"]
                pending = json.loads(
                    stored["session"]["publicState"]["raidPendingReturnJson"]
                )
                if pending.get("sendState") != "sending":
                    raise AssertionError("raid send boundary was not persisted")
                calls.append((opcode, bytes(payload)))
                response_opcode = 0x8520 if opcode == 0x1520 else 0x8522
                response_payload = (
                    b""
                    if opcode == 0x1520
                    else bytes.fromhex("00000000000000006c42d1")
                )
                return {
                    "requestOpcode": opcode,
                    "httpCode": 200,
                    "httpOk": True,
                    "packets": [{
                        "opcode": response_opcode,
                        "payload": response_payload,
                    }],
                }

            facade._execute_host_game_command = types.MethodType(command, facade)  # noqa: SLF001
            body = facade.raid_action_operation_payload({
                "accountRef": "202",
                "confirm": "raid",
                "playerName": "目标玩家",
                "fiefIndex": 1,
                "generalIds": ["1"],
                "fullTroops": False,
                "fullLoyalty": False,
            }, {})
            execution = FakeExecution()
            response = facade._run_raid_execute_game_workflow(  # noqa: SLF001
                execution,
                body,
                {},
            )
            self.assertTrue(response["result"]["success"])
            self.assertEqual(response["result"]["successBattleId"], 7094993)
            self.assertEqual(calls, [
                (0x1520, build_raid_prepare_payload(["0000000000000001"], 101)),
                (0x1522, build_raid_expedition_payload(["0000000000000001"], 101)),
            ])
            stored = json.loads(facade.account_record_json("202"))["account"]
            pending = json.loads(
                stored["session"]["publicState"]["raidPendingReturnJson"]
            )
            self.assertEqual(pending["sendState"], "accepted")

            current = [self._general(6)]
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda self, *_args, **_kwargs: ("00", list(current), []),
                facade,
            )
            facade._persist_automation_general_snapshot = lambda *args, **kwargs: None  # noqa: SLF001
            waiting = facade._run_raid_return_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", pending, {}
            )
            self.assertEqual(waiting["state"], "waiting")
            stored = json.loads(facade.account_record_json("202"))["account"]
            pending = json.loads(
                stored["session"]["publicState"]["raidPendingReturnJson"]
            )
            self.assertTrue(pending["sawBusy"])
            clock.value += 60_000
            current[:] = [self._general(0)]
            completed = facade._run_raid_return_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", pending, {}
            )
            self.assertEqual(completed["state"], "completed")
            stored = json.loads(facade.account_record_json("202"))["account"]
            self.assertEqual(
                stored["session"]["publicState"]["raidPendingReturnJson"],
                "{}",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_raid_missing_dispatch_receipt_is_uncertain(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            self._install_preflight(facade)

            def command(self, _account, opcode, _payload, _phase, _context, *, mutation_sent):
                return {
                    "requestOpcode": opcode,
                    "httpCode": 200,
                    "httpOk": True,
                    "packets": ([{"opcode": 0x8520, "payload": b""}] if opcode == 0x1520 else []),
                }

            facade._execute_host_game_command = types.MethodType(command, facade)  # noqa: SLF001
            body = facade.raid_action_operation_payload({
                "accountRef": "202",
                "confirm": "raid",
                "playerName": "目标玩家",
                "fiefIndex": 1,
                "generalIds": ["1"],
                "fullTroops": False,
            }, {})
            with self.assertRaises(OperationUncertainError):
                facade._run_raid_execute_game_workflow(  # noqa: SLF001
                    FakeExecution(), body, {}
                )
            stored = json.loads(facade.account_record_json("202"))["account"]
            pending = json.loads(
                stored["session"]["publicState"]["raidPendingReturnJson"]
            )
            self.assertEqual(pending["sendState"], "uncertain")
            self.assertEqual(pending["generalIds"], [1])
        finally:
            facade.close()
            directory.cleanup()

    def test_raid_preflight_mutation_ambiguity_is_durable_and_never_replayed(
        self,
    ) -> None:
        facade, _clock, directory = self._facade()
        try:
            self._install_preflight(facade)

            def uncertain_preflight(
                _self, execution, *_args, **_kwargs
            ):
                execution.mark_request_sent({
                    "feature": "general-maintenance-energy",
                    "opcode": "0x1218",
                })
                raise OperationUncertainError("加体回执不明确")

            facade._run_expedition_preflight = types.MethodType(  # noqa: SLF001
                uncertain_preflight, facade
            )
            body = facade.raid_action_operation_payload({
                "accountRef": "202",
                "confirm": "raid",
                "playerName": "目标玩家",
                "fiefIndex": 1,
                "generalIds": ["1"],
                "fullTroops": False,
            }, {})
            with self.assertRaises(OperationUncertainError):
                facade._run_raid_execute_game_workflow(  # noqa: SLF001
                    FakeExecution(), body, {}
                )
            stored = json.loads(facade.account_record_json("202"))["account"]
            pending = json.loads(
                stored["session"]["publicState"]["raidPendingReturnJson"]
            )
            self.assertEqual(pending["preDispatchMutationState"], "uncertain")
            self.assertEqual(pending["sendState"], "not-started")

            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: (
                    "00", [self._general(0)], []
                ),
                facade,
            )
            facade._persist_automation_general_snapshot = (  # noqa: SLF001
                lambda *_args, **_kwargs: None
            )
            recovered = facade._run_raid_return_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", pending, {}
            )
            self.assertEqual(recovered["state"], "blocked")
            self.assertTrue(recovered["requiresAttention"])
            stored = json.loads(facade.account_record_json("202"))["account"]
            self.assertNotEqual(
                stored["session"]["publicState"]["raidPendingReturnJson"],
                "{}",
            )
        finally:
            facade.close()
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
