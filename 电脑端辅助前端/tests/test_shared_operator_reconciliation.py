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
from dwpm_core.operations import OperationKnownFailureError  # noqa: E402
from dwpm_core.ports import PlatformPorts  # noqa: E402


class FixedClock:
    def __init__(self, value: int = 10_000_000) -> None:
        self.value = value

    def now_millis(self) -> int:
        return self.value


class FakeExecution:
    operation_id = "operator-reconcile-fixture"

    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def mark_request_sent(self, metadata=None) -> None:
        self.sent.append(dict(metadata or {}))

    def publish_progress(self, _progress, _details=None) -> None:
        return None

    def raise_if_cancelled(self) -> None:
        return None

    def wait(self, _seconds) -> None:
        return None


class SharedOperatorReconciliationTests(unittest.TestCase):
    def _facade(self):
        directory = tempfile.TemporaryDirectory()
        clock = FixedClock()
        facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(Path(directory.name) / "operations.json"),
            ports=PlatformPorts(clock=clock),
        )
        facade.account_record_upsert({
            "accountRef": "901",
            "id": 901,
            "enabled": True,
            "loginState": "ONLINE",
            "session": {
                "accountId": 901,
                "sourceMode": 1,
                "publicState": {
                    "roleId": "901",
                    "gameHttp": "https://fixture.invalid/game",
                    "lastValidatedAt": str(clock.value),
                    "residentAutomationConfigJson": json.dumps({
                        "updatedAtMillis": clock.value,
                        "formations": [{
                            "enabled": True,
                            "generalIds": ["7"],
                            "generalId": "7",
                            "soldierType": "轻骑兵",
                            "soldierCount": 100,
                        }],
                    }, ensure_ascii=False),
                    "residentAutomationStateJson": json.dumps({}),
                },
            },
        })
        general = {
            "id": 7,
            "name": "赵云",
            "status": 0,
            "statusText": "闲",
            "displayStatus": "闲",
            "energyReliable": True,
            "tili": 300,
            "soldierTypeCode": 3,
            "soldierCount": 100,
            "currentSoldierCount": 100,
        }
        facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
            lambda _self, *_args, **_kwargs: ("00", [dict(general)], []),
            facade,
        )
        return facade, clock, directory, general

    @staticmethod
    def _store(facade: CoreFacade) -> dict:
        return json.loads(facade.account_record_json("901"))["account"]

    def _put_pending(self, facade: CoreFacade, field: str, value: dict) -> None:
        facade._update_account_public_state(  # noqa: SLF001
            "901", {field: json.dumps(value, ensure_ascii=False)}
        )

    def test_lossless_operator_reconcile_archives_without_mutation(self) -> None:
        facade, clock, directory, _general = self._facade()
        try:
            facade._run_lossless_status_game_workflow = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: {
                    "mode": 1,
                    "remainingAttempts": 5,
                    "dispatchable": True,
                    "phase": "ready",
                },
                facade,
            )
            self._put_pending(facade, "losslessPendingBattleJson", {
                "generalIds": [7],
                "dispatchSendState": "not-sent",
                "prepareSendState": "not-sent",
                "preDispatchMutationState": "uncertain",
            })
            execution = FakeExecution()
            result = facade._run_lossless_recovery_game_workflow(  # noqa: SLF001
                execution,
                "901",
                json.loads(
                    self._store(facade)["session"]["publicState"][
                        "losslessPendingBattleJson"
                    ]
                ),
                {"operatorReconcileFeatures": ["lossless"]},
            )
            self.assertEqual(result["state"], "reconciled")
            self.assertEqual(execution.sent, [])
            public = self._store(facade)["session"]["publicState"]
            self.assertEqual(public["losslessPendingBattleJson"], "{}")
            audit = json.loads(public["losslessLastReconciliationJson"])
            self.assertEqual(audit["reconciledAtMillis"], clock.value)
        finally:
            facade.close()
            directory.cleanup()

    def test_dungeon_operator_reconcile_archives_without_mutation(self) -> None:
        facade, clock, directory, _general = self._facade()
        try:
            facade._run_dungeon_status_game_workflow = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: {
                    "phase": "idle",
                    "active": False,
                    "status": 0,
                },
                facade,
            )
            self._put_pending(facade, "dungeonPendingRunJson", {
                "generalIds": [7],
                "dispatchSendState": "not-sent",
                "prepareSendState": "not-sent",
                "chestSendState": "not-sent",
                "preDispatchMutationState": "uncertain",
            })
            execution = FakeExecution()
            result = facade._run_dungeon_recovery_game_workflow(  # noqa: SLF001
                execution,
                "901",
                json.loads(
                    self._store(facade)["session"]["publicState"][
                        "dungeonPendingRunJson"
                    ]
                ),
                {"operatorReconcileFeatures": ["dungeon"]},
            )
            self.assertEqual(result["state"], "reconciled")
            self.assertEqual(execution.sent, [])
            public = self._store(facade)["session"]["publicState"]
            self.assertEqual(public["dungeonPendingRunJson"], "{}")
            self.assertEqual(
                json.loads(public["dungeonLastReconciliationJson"])[
                    "reconciledAtMillis"
                ],
                clock.value,
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_brush_operator_reconcile_skips_one_heal_and_archives(self) -> None:
        facade, clock, directory, _general = self._facade()
        try:
            self._put_pending(facade, "brushPendingRecoveryJson", {
                "generalIds": [7],
                "sendState": "uncertain",
                "preDispatchMutationState": "accepted",
                "sendingAtMillis": clock.value - 600_000,
                "createdAtMillis": clock.value - 600_000,
                "dispatchRequestMetadata": {
                    "phase": "prepare",
                    "opcode": "0x1520",
                },
                "preDispatchRequestMetadata": {
                    "feature": "troop-heal",
                    "opcode": "0x1230",
                },
            })
            execution = FakeExecution()
            result = facade._run_brush_recovery_game_workflow(  # noqa: SLF001
                execution,
                "901",
                json.loads(
                    self._store(facade)["session"]["publicState"][
                        "brushPendingRecoveryJson"
                    ]
                ),
                {"operatorReconcileFeatures": ["brush"]},
            )
            self.assertEqual(result["state"], "reconciled")
            self.assertEqual(execution.sent, [])
            public = self._store(facade)["session"]["publicState"]
            self.assertEqual(public["brushPendingRecoveryJson"], "{}")
            state = json.loads(public["residentAutomationStateJson"])
            self.assertTrue(state["brush"]["skipHealOnce"])
            self.assertEqual(
                json.loads(public["brushLastReconciliationJson"])[
                    "reconciledAtMillis"
                ],
                clock.value,
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_operator_reconcile_rejects_busy_general_and_keeps_ledger(self) -> None:
        facade, _clock, directory, general = self._facade()
        try:
            self._put_pending(facade, "losslessPendingBattleJson", {
                "generalIds": [7],
                "dispatchSendState": "not-sent",
                "prepareSendState": "not-sent",
                "preDispatchMutationState": "uncertain",
            })
            busy = {**general, "status": 6, "statusText": "战"}
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: ("00", [busy], []),
                facade,
            )
            facade._run_lossless_status_game_workflow = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: {
                    "mode": 1,
                    "remainingAttempts": 5,
                    "dispatchable": True,
                    "phase": "ready",
                },
                facade,
            )
            with self.assertRaisesRegex(OperationKnownFailureError, "尚未回闲"):
                facade._run_lossless_recovery_game_workflow(  # noqa: SLF001
                    FakeExecution(),
                    "901",
                    json.loads(
                        self._store(facade)["session"]["publicState"][
                            "losslessPendingBattleJson"
                        ]
                    ),
                    {"operatorReconcileFeatures": ["lossless"]},
                )
            self.assertNotEqual(
                self._store(facade)["session"]["publicState"][
                    "losslessPendingBattleJson"
                ],
                "{}",
            )
        finally:
            facade.close()
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
