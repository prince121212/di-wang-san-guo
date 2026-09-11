from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core.facade import CoreFacade  # noqa: E402
from dwpm_core.operations import (  # noqa: E402
    OperationKnownFailureError,
    OperationUncertainError,
)
from dwpm_core.ports import PlatformPorts  # noqa: E402


class FixedClock:
    def __init__(self, value: int = 50_000_000) -> None:
        self.value = value

    def now_millis(self) -> int:
        return self.value


class FakeExecution:
    operation_id = "shared-general-resident-fixture"

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


class SharedGeneralMaintenanceAutomationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.clock = FixedClock()
        self.operation_path = str(
            Path(self.directory.name) / "operations.json"
        )
        self.facade = self._open_facade()
        self._seed_account(self.facade)

    def tearDown(self) -> None:
        self.facade.close()
        self.directory.cleanup()

    def _open_facade(self) -> CoreFacade:
        return CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=self.operation_path,
            ports=PlatformPorts(clock=self.clock),
        )

    @staticmethod
    def _seed_account(facade: CoreFacade) -> None:
        facade.account_record_upsert({
            "accountRef": "303",
            "id": 303,
            "enabled": True,
            "loginState": "ONLINE",
            "session": {
                "accountId": 303,
                "sourceMode": 1,
                "publicState": {
                    "roleId": "303",
                    "gameHttp": "https://fixture.invalid/game",
                    "savedTasksStarted": "true",
                    "activeResidentTaskKeys": "general",
                    "generalsJson": "[]",
                },
            },
        })

    @staticmethod
    def _habits(
        *,
        auto_heal: bool = True,
        auto_energy: bool = True,
        loyalty: bool = True,
    ) -> dict[str, object]:
        return {
            "general": {
                "autoHeal": auto_heal,
                "autoEnergy": auto_energy,
                "minEnergy": 35,
                "keepFullLoyalty": loyalty,
                "autoRescue": True,
                "foodToCopper": False,
                "copperFloorWan": 10,
            }
        }

    @staticmethod
    def _generals() -> list[dict[str, object]]:
        # Deliberately out of order: both hosts must get the same stable plan.
        return [
            {
                "id": 9,
                "name": "马超",
                "fiefId": 1878,
                "tili": 10,
                "energyReliable": True,
                "loyalty": 80,
                "loyaltyLimit": 100,
            },
            {
                "id": 8,
                "name": "关羽",
                "fiefId": 1877,
                "tili": 90,
                "energyReliable": True,
                "loyalty": 100,
                "loyaltyLimit": 100,
            },
            {
                "id": 7,
                "name": "赵云",
                "fiefId": 1877,
                "tili": 20,
                "energyReliable": True,
                "loyalty": 60,
                "loyaltyLimit": 100,
            },
        ]

    def _configure(self, facade: CoreFacade, habits: dict[str, object]) -> None:
        configured = facade.configure_resident_automation_from_habits(
            "303", habits
        )
        self.assertTrue(configured["generalEnabled"])
        facade.set_resident_automation_activation("303", True, ["general"])

    def _fresh_generals(self, facade: CoreFacade) -> None:
        facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
            lambda _self, _account_ref, _context, read_only=False: (
                "",
                [dict(row) for row in self._generals()],
                [],
            ),
            facade,
        )
        facade._persist_automation_general_snapshot = types.MethodType(  # noqa: SLF001
            lambda *_args, **_kwargs: None,
            facade,
        )

    @staticmethod
    def _public(facade: CoreFacade) -> dict[str, object]:
        account = json.loads(facade.account_record_json("303"))["account"]
        return account["session"]["publicState"]

    def test_multi_fief_and_multi_general_steps_use_one_stable_order(self) -> None:
        self._configure(self.facade, self._habits())
        self._fresh_generals(self.facade)
        actions: list[str] = []

        def heal(_self, execution, body, _context):
            actions.append(f"heal:{body.get('fiefId') or 'fallback'}")
            execution.mark_request_sent({"feature": "fixture-heal"})
            return {"ok": True, "result": {"message": "治疗成功"}}

        def energy(
            _self,
            execution,
            _account_ref,
            general,
            _context,
            **_options,
        ):
            actions.append(f"energy:{general['id']}")
            execution.mark_request_sent({"feature": "fixture-energy"})
            return {"success": True, "message": "加体成功"}

        def loyalty(
            _self,
            execution,
            _account_ref,
            general,
            _context,
            **_options,
        ):
            actions.append(f"loyalty:{general['id']}")
            execution.mark_request_sent({"feature": "fixture-loyalty"})
            return {"success": True, "message": "加忠成功"}

        self.facade._run_troop_heal_game_workflow = types.MethodType(  # noqa: SLF001
            heal, self.facade
        )
        self.facade._run_general_energy_maintenance_step = types.MethodType(  # noqa: SLF001
            energy, self.facade
        )
        self.facade._run_general_loyalty_maintenance_step = types.MethodType(  # noqa: SLF001
            loyalty, self.facade
        )

        result = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["general"]}
        )

        self.assertEqual(result["feature"], "general")
        self.assertEqual(result["state"], "completed")
        self.assertEqual(
            actions,
            [
                "heal:1877",
                "heal:1878",
                "energy:7",
                "energy:8",
                "energy:9",
                "loyalty:7",
                "loyalty:8",
                "loyalty:9",
            ],
        )
        self.assertEqual(
            result["nextWakeAtMillis"], self.clock.value + 600_000
        )
        public = self._public(self.facade)
        self.assertEqual(public["generalMaintenancePendingJson"], "{}")
        last = json.loads(public["generalMaintenanceLastRunJson"])
        self.assertEqual(last["orderedGeneralIds"], [7, 8, 9])
        config = json.loads(public["residentAutomationConfigJson"])
        self.assertFalse(config["general"]["autoRescue"])
        self.assertTrue(
            config["general"]["unsupportedAutoRescueRequested"]
        )
        state = json.loads(public["residentAutomationStateJson"])
        self.assertEqual(
            state["general"]["nextWakeAtMillis"],
            self.clock.value + 600_000,
        )

    def test_android_object_and_desktop_flat_habits_normalize_identically(
        self,
    ) -> None:
        self._configure(
            self.facade,
            {
                "general": {
                    "autoHeal": True,
                    "autoEnergy": True,
                    "minEnergy": 35,
                    "keepFullLoyalty": False,
                    "foodToCopper": True,
                    "copperFloorWan": 20,
                }
            },
        )
        self.facade.account_record_upsert({
            "accountRef": "304",
            "id": 304,
            "enabled": True,
            "loginState": "ONLINE",
            "session": {
                "accountId": 304,
                "sourceMode": 1,
                "publicState": {
                    "roleId": "304",
                    "savedTasksStarted": "true",
                    "activeResidentTaskKeys": "general",
                },
            },
        })
        self.facade.configure_resident_automation_from_habits(
            "304",
            {
                "config": {
                    "healWounded": True,
                    "autoEnergy": True,
                    "energyThreshold": 35,
                    "keepFullLoyalty": False,
                    "foodToCopper": True,
                    "copperFloorWan": 20,
                }
            },
        )
        android_config = json.loads(
            self._public(self.facade)["residentAutomationConfigJson"]
        )["general"]
        desktop_account = json.loads(
            self.facade.account_record_json("304")
        )["account"]
        desktop_config = json.loads(
            desktop_account["session"]["publicState"][
                "residentAutomationConfigJson"
            ]
        )["general"]

        self.assertEqual(android_config, desktop_config)

    def test_process_reopen_continues_after_completed_safe_steps(self) -> None:
        self._configure(
            self.facade,
            self._habits(auto_heal=True, auto_energy=True, loyalty=True),
        )
        self._fresh_generals(self.facade)
        first_actions: list[str] = []

        def heal(_self, execution, body, _context):
            first_actions.append(f"heal:{body.get('fiefId')}")
            execution.mark_request_sent({"feature": "fixture-heal"})
            return {"ok": True, "result": {"message": "治疗成功"}}

        def fail_before_send(_self, *_args, **_kwargs):
            first_actions.append("energy:failed-before-send")
            raise OperationKnownFailureError(
                "读取背包失败", code="FIXTURE_ENERGY_READ_FAILED"
            )

        self.facade._run_troop_heal_game_workflow = types.MethodType(  # noqa: SLF001
            heal, self.facade
        )
        self.facade._run_general_energy_maintenance_step = types.MethodType(  # noqa: SLF001
            fail_before_send, self.facade
        )
        first = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["general"]}
        )
        self.assertEqual(first["state"], "retry")
        self.assertFalse(first["requiresAttention"])
        self.assertEqual(
            first_actions,
            ["heal:1877", "heal:1878", "energy:failed-before-send"],
        )

        self.facade.close()
        self.facade = self._open_facade()
        self._fresh_generals(self.facade)
        resumed_actions: list[str] = []

        def heal_must_not_repeat(*_args, **_kwargs):
            raise AssertionError("completed healing step was replayed")

        def energy(
            _self,
            execution,
            _account_ref,
            general,
            _context,
            **_options,
        ):
            resumed_actions.append(f"energy:{general['id']}")
            execution.mark_request_sent({"feature": "fixture-energy"})
            return {"success": True, "message": "加体成功"}

        def loyalty(
            _self,
            execution,
            _account_ref,
            general,
            _context,
            **_options,
        ):
            resumed_actions.append(f"loyalty:{general['id']}")
            execution.mark_request_sent({"feature": "fixture-loyalty"})
            return {"success": True, "message": "加忠成功"}

        self.facade._run_troop_heal_game_workflow = heal_must_not_repeat  # noqa: SLF001
        self.facade._run_general_energy_maintenance_step = types.MethodType(  # noqa: SLF001
            energy, self.facade
        )
        self.facade._run_general_loyalty_maintenance_step = types.MethodType(  # noqa: SLF001
            loyalty, self.facade
        )
        resumed = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["general"]}
        )

        self.assertEqual(resumed["state"], "completed")
        self.assertEqual(
            resumed_actions,
            [
                "energy:7",
                "energy:8",
                "energy:9",
                "loyalty:7",
                "loyalty:8",
                "loyalty:9",
            ],
        )

    def test_uncertain_send_is_only_observed_and_never_replayed(self) -> None:
        self._configure(
            self.facade,
            self._habits(auto_heal=False, auto_energy=True, loyalty=False),
        )
        self._fresh_generals(self.facade)
        sends = 0

        def uncertain(
            _self,
            execution,
            _account_ref,
            _general,
            _context,
            **_options,
        ):
            nonlocal sends
            sends += 1
            execution.mark_request_sent({"feature": "fixture-energy"})
            raise OperationUncertainError("加体回执不明")

        self.facade._run_general_energy_maintenance_step = types.MethodType(  # noqa: SLF001
            uncertain, self.facade
        )
        with self.assertRaises(OperationUncertainError):
            self.facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["general"]}
            )
        self.assertEqual(sends, 1)

        self.facade.close()
        self.facade = self._open_facade()
        observations = 0

        def fresh(_self, _account_ref, _context, read_only=False):
            nonlocal observations
            observations += 1
            self.assertTrue(read_only)
            return "", [dict(row) for row in self._generals()], []

        self.facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
            fresh, self.facade
        )
        self.facade._persist_automation_general_snapshot = types.MethodType(  # noqa: SLF001
            lambda *_args, **_kwargs: None,
            self.facade,
        )

        def forbidden(*_args, **_kwargs):
            raise AssertionError("uncertain energy mutation was replayed")

        self.facade._run_general_energy_maintenance_step = forbidden  # noqa: SLF001
        blocked = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["general"]}
        )

        self.assertEqual(observations, 1)
        self.assertEqual(blocked["state"], "blocked")
        self.assertTrue(blocked["requiresAttention"])
        self.assertIn("禁止自动重发", blocked["message"])
        pending = json.loads(
            self._public(self.facade)["generalMaintenancePendingJson"]
        )
        self.assertEqual(
            pending["maintenanceProgress"]["energyByGeneral"]["7"]["state"],
            "uncertain",
        )

    def test_explicit_rejection_stops_before_later_mutations(self) -> None:
        self._configure(
            self.facade,
            self._habits(auto_heal=False, auto_energy=True, loyalty=True),
        )
        self._fresh_generals(self.facade)
        energy_calls = 0
        loyalty_calls = 0

        def rejected(
            _self,
            execution,
            _account_ref,
            _general,
            _context,
            **_options,
        ):
            nonlocal energy_calls
            energy_calls += 1
            execution.mark_request_sent({"feature": "fixture-energy"})
            raise OperationKnownFailureError(
                "服务器拒绝加体", code="FIXTURE_ENERGY_REJECTED"
            )

        def loyalty(*_args, **_kwargs):
            nonlocal loyalty_calls
            loyalty_calls += 1
            return {"success": True}

        self.facade._run_general_energy_maintenance_step = types.MethodType(  # noqa: SLF001
            rejected, self.facade
        )
        self.facade._run_general_loyalty_maintenance_step = loyalty  # noqa: SLF001

        states = [
            self.facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["general"]}
            )["state"]
            for _ in range(4)
        ]

        # A rejection is definitive, so it is never replayed: each of the three
        # generals is attempted exactly once.
        self.assertEqual(energy_calls, 3)
        # It is also not an open question, so the round converges instead of
        # blocking forever.  A run that can never complete keeps its pending
        # record, and that record outranks every configured feature on every
        # tick - one real account stopped scheduling 副本 and 刷黄 entirely.
        self.assertEqual(states[-1], "completed")
        self.assertEqual(loyalty_calls, 3)
        public = self._public(self.facade)
        self.assertEqual(public["generalMaintenancePendingJson"], "{}")

    def test_a_failing_round_keeps_the_send_markers_it_recorded(self) -> None:
        """The failure path must never roll back the send-boundary ledger.

        It rebuilt the record from the snapshot taken *before* the workflow
        ran, so every step the workflow durably recorded on its way to failing
        was erased.  That ledger is the only thing standing between a landed
        mutation and a second send of it.
        """

        self._configure(
            self.facade,
            self._habits(auto_heal=False, auto_energy=True, loyalty=False),
        )
        self._fresh_generals(self.facade)
        attempted: list[int] = []

        def reject_every_general(
            _self,
            execution,
            _account_ref,
            general,
            _context,
            **_options,
        ):
            attempted.append(int(general["id"]))
            execution.mark_request_sent({"feature": "fixture-energy"})
            raise OperationKnownFailureError(
                "服务器拒绝加体", code="FIXTURE_ENERGY_REJECTED"
            )

        self.facade._run_general_energy_maintenance_step = types.MethodType(  # noqa: SLF001
            reject_every_general, self.facade
        )

        self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["general"]}
        )
        self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["general"]}
        )

        pending = json.loads(
            self._public(self.facade)["generalMaintenancePendingJson"]
        )
        recorded = pending["maintenanceProgress"]["energyByGeneral"]
        # Both generals reached the server, so both outcomes must survive.
        self.assertEqual(sorted(recorded.keys()), ["7", "8"])
        self.assertEqual(
            {key: value["state"] for key, value in recorded.items()},
            {"7": "rejected", "8": "rejected"},
        )
        self.assertEqual(attempted, [7, 8])


if __name__ == "__main__":
    unittest.main()
