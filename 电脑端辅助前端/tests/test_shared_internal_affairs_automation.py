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
from dwpm_core.local_views import (  # noqa: E402
    resident_success_records_from_operation_facts,
)
from dwpm_core.features.internal_affairs import (  # noqa: E402
    TECHNOLOGY_NAMES,
    plan_next_internal_affairs_action,
    technology_resource_cost,
)
from dwpm_core.operations import (  # noqa: E402
    OperationKnownFailureError,
    OperationUncertainError,
)
from dwpm_core.ports import PlatformPorts  # noqa: E402


class FixedClock:
    def __init__(self, value: int = 70_000_000) -> None:
        self.value = value

    def now_millis(self) -> int:
        return self.value


class FakeExecution:
    operation_id = "shared-domestic-fixture"

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


def building(
    slot: int,
    building_type: int,
    level: int,
    *,
    busy: bool = False,
    timer_ms: int = 0,
    instance_id: int | None = None,
) -> dict[str, object]:
    return {
        "slot": slot,
        "type": building_type,
        "level": level,
        "busy": busy,
        "timerMs": timer_ms,
        "instanceId": instance_id if instance_id is not None else slot + 100,
    }


def fief(
    fief_id: int = 1877,
    *,
    hall_level: int = 2,
    rows: list[dict[str, object]] | None = None,
    capacity: int = 2,
) -> dict[str, object]:
    return {
        "fiefId": fief_id,
        "fiefName": "基地",
        "buildQueueCapacity": capacity,
        "buildings": [building(0, 0, hall_level), *(rows or [])],
    }


class SharedInternalAffairsPlannerTests(unittest.TestCase):
    def test_hall_empty_and_lowest_upgrade_order_is_deterministic(self) -> None:
        config = {
            "enabled": True,
            "upgradeBuildings": True,
            "emptyBuildingType": 2,
        }
        hall = plan_next_internal_affairs_action(
            [
                fief(200, hall_level=3, rows=[building(1, 1, 3)]),
                fief(100, hall_level=2, rows=[building(1, 1, 2)]),
            ],
            [],
            config,
        )
        self.assertEqual((hall["action"], hall["fiefId"]), ("building", 100))
        self.assertEqual(hall["buildingType"], 0)

        empty = plan_next_internal_affairs_action(
            [fief(100, hall_level=5, rows=[building(1, 1, 1)])],
            [],
            config,
        )
        self.assertEqual(empty["slot"], 2)
        self.assertEqual(empty["buildingType"], 2)

        full_rows = [
            building(slot, 1 if slot != 3 else 3, 3 if slot == 2 else 4)
            for slot in range(1, 13)
        ]
        upgrade = plan_next_internal_affairs_action(
            [fief(100, hall_level=5, rows=full_rows)],
            [],
            config,
        )
        self.assertEqual(upgrade["slot"], 2)
        self.assertEqual(upgrade["previousLevel"], 3)

    def test_building_and_technology_take_alternating_turns(self) -> None:
        rows = [
            building(slot, 3 if slot == 3 else 1, 5 if slot == 3 else 2)
            for slot in range(1, 13)
        ]
        technologies = [{
            "technologyId": 5,
            "level": 1,
            "researching": False,
            "academyInstanceId": None,
        }]
        config = {
            "enabled": True,
            "upgradeBuildings": True,
            "upgradeTechnology": True,
            "technologyIds": [5],
        }

        first = plan_next_internal_affairs_action(
            [fief(rows=rows, hall_level=6)], technologies, config
        )
        second = plan_next_internal_affairs_action(
            [fief(rows=rows, hall_level=6)],
            technologies,
            config,
            prefer_technology=True,
        )

        self.assertEqual(first["action"], "building")
        self.assertTrue(first["nextPreferTechnology"])
        self.assertEqual(second["action"], "technology")
        self.assertFalse(second["nextPreferTechnology"])

    def test_previous_confirmed_domestic_operation_is_recovered_for_politics(self) -> None:
        recovered = resident_success_records_from_operation_facts(
            [{
                "accountRef": "303",
                "status": "SUCCEEDED",
                "completedAtMillis": 70_000_123,
                "result": {
                    "feature": "domestic",
                    "state": "completed",
                    "success": True,
                    "message": "升级房屋9→10已确认",
                    "action": {
                        "action": "building",
                        "fiefId": 1877,
                        "slot": 2,
                        "targetLevel": 10,
                    },
                },
            }],
            account_ref="303",
        )

        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["category"], "内政")
        self.assertEqual(recovered[0]["message"], "升级房屋9→10已确认")

        ignored = resident_success_records_from_operation_facts(
            [{
                "accountRef": "303",
                "status": "SUCCEEDED",
                "result": {
                    "feature": "domestic",
                    "state": "waiting-resources",
                    "success": True,
                    "action": {"action": "building"},
                },
            }],
            account_ref="303",
        )
        self.assertEqual(ignored, [])

    def test_unobservable_third_resource_fails_closed(self) -> None:
        self.assertEqual(technology_resource_cost(0, 11)["extra"], 800)
        rows = [building(slot, 3 if slot == 3 else 1, 15) for slot in range(1, 13)]
        plan = plan_next_internal_affairs_action(
            [fief(rows=rows, hall_level=15)],
            [{
                "technologyId": 0,
                "level": 10,
                "researching": False,
                "academyInstanceId": None,
            }],
            {
                "enabled": False,
                "upgradeTechnology": True,
                "technologyIds": [0],
            },
        )
        self.assertTrue(plan["blocked"])
        self.assertEqual(plan["requiredExtra"], 800)


class SharedInternalAffairsAutomationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.clock = FixedClock()
        self.operation_path = str(Path(self.directory.name) / "operations.json")
        self.facade = self._open_facade()
        self._seed_account(self.facade, "303")

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
    def _seed_account(facade: CoreFacade, account_ref: str) -> None:
        facade.account_record_upsert({
            "accountRef": account_ref,
            "id": int(account_ref),
            "enabled": True,
            "loginState": "ONLINE",
            "session": {
                "accountId": int(account_ref),
                "sourceMode": 1,
                "publicState": {
                    "roleId": account_ref,
                    "gameHttp": "https://fixture.invalid/game",
                    "savedTasksStarted": "true",
                    "activeResidentTaskKeys": "domestic",
                },
            },
        })

    @staticmethod
    def _habits(
        *,
        enabled: bool = True,
        upgrade_technology: bool = False,
        food_to_copper: bool = False,
    ) -> dict[str, object]:
        return {
            "general": {
                "autoHeal": False,
                "autoEnergy": False,
                "keepFullLoyalty": False,
                "foodToCopper": food_to_copper,
                "copperFloorWan": 10,
            },
            "config": {
                "domestic": {
                    "enabled": enabled,
                    "upgradeBuildings": True,
                    "upgradeLowestFirst": True,
                    "emptyBuildingType": 1,
                    "buildingPriority": [],
                    "upgradeTechnology": upgrade_technology,
                    "technologyIds": [5],
                },
            },
        }

    @staticmethod
    def _snapshot(
        *,
        copper: int = 1_000_000,
        food: int = 1_000_000,
        rows: list[dict[str, object]] | None = None,
        hall_level: int = 2,
        timer_ms: int = 0,
        technology_error: str = "",
    ) -> dict[str, object]:
        fief_rows = rows or [building(1, 1, hall_level)]
        if timer_ms:
            fief_rows = [building(1, 1, 1, busy=True, timer_ms=timer_ms)]
        return {
            "ok": True,
            "fiefs": [fief(hall_level=hall_level, rows=fief_rows)],
            "technologies": [],
            "technologyParseError": technology_error,
            "resources": {"copper": copper, "food": food},
            "resourceParseError": "",
        }

    def _configure(self, habits: dict[str, object]) -> None:
        configured = self.facade.configure_resident_automation_from_habits(
            "303", habits
        )
        self.assertTrue(configured["domesticEnabled"])
        self.facade.set_resident_automation_activation(
            "303", True, ["domestic"]
        )

    def _install_snapshot(self, snapshot: dict[str, object]) -> None:
        self.facade._run_domestic_query_game_workflow = types.MethodType(  # noqa: SLF001
            lambda _self, _execution, _body, _context: dict(snapshot),
            self.facade,
        )

    def _public(self) -> dict[str, object]:
        account = json.loads(self.facade.account_record_json("303"))["account"]
        return account["session"]["publicState"]

    def test_one_tick_submits_one_mutation_and_uses_one_second_deadline(self) -> None:
        self._configure(self._habits())
        self._install_snapshot(self._snapshot())
        actions: list[dict[str, object]] = []

        def action(_self, execution, body, _context):
            actions.append(dict(body))
            execution.mark_request_sent({"feature": "fixture-domestic"})
            return {"ok": True, "result": {"success": True, "message": "已确认"}}

        self.facade._run_domestic_action_game_workflow = types.MethodType(  # noqa: SLF001
            action, self.facade
        )
        result = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
        )

        self.assertEqual(result["state"], "completed")
        self.assertEqual(len(actions), 1)
        self.assertEqual(result["nextWakeAtMillis"], self.clock.value + 1_000)
        public = self._public()
        self.assertEqual(public["domesticPendingActionJson"], "{}")
        last = json.loads(public["domesticLastActionJson"])
        self.assertEqual(last["progress"]["action"]["state"], "completed")
        record = result["successRecord"]
        self.assertEqual(record["category"], "内政")
        self.assertEqual(record["dedupeKey"], "domestic:plan:domestic-303-70000000")
        records = json.loads(self._public()["successRecordsJson"])
        self.assertEqual([row["category"] for row in records], ["内政"])

        duplicate = self.facade._append_resident_success_record(  # noqa: SLF001
            "303", result
        )
        self.assertIsNone(duplicate)

    def test_completed_technology_record_names_the_technology(self) -> None:
        self._configure(self._habits(upgrade_technology=True))
        snapshot = self._snapshot()
        snapshot["technologies"] = [
            {"technologyId": 5, "level": 2, "researching": False}
        ]
        snapshot["fiefs"] = [
            fief(
                hall_level=5,
                rows=[
                    building(1, 1, 5, busy=True, timer_ms=60_000),
                    building(2, 3, 5),
                ],
                capacity=1,
            )
        ]
        self._install_snapshot(snapshot)

        def action(_self, execution, _body, _context):
            execution.mark_request_sent({"feature": "fixture-domestic"})
            return {
                "ok": True,
                "result": {"success": True, "message": "科技研究成功"},
            }

        self.facade._run_domestic_action_game_workflow = types.MethodType(  # noqa: SLF001
            action, self.facade
        )
        result = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
        )

        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["action"]["action"], "technology")
        expected = f"升级{TECHNOLOGY_NAMES[5]}2→3已确认"
        self.assertEqual(result["message"], expected)
        self.assertEqual(result["successRecord"]["message"], expected)
        self.assertEqual(result["successRecord"]["category"], "科技")

    def test_domestic_query_snapshot_updates_role_queue_projection(self) -> None:
        technologies = [{
            "technologyId": 5,
            "researching": True,
        }]
        queue = self.facade._project_account_public_state("303")[  # noqa: SLF001
            "roleQueueSummary"
        ]
        self.assertEqual(queue, {})

        summary = __import__(
            "dwpm_core.features.internal_affairs",
            fromlist=["summarize_role_queues"],
        ).summarize_role_queues(
            [fief(rows=[building(1, 3, 2)], capacity=2)],
            technologies,
            updated_at=self.clock.value,
        )
        self.facade._update_account_public_state(  # noqa: SLF001
            "303",
            {
                "technologyStatesJson": json.dumps(technologies),
                "roleQueueSummaryJson": json.dumps(summary),
            },
        )

        projected = self.facade._project_account_public_state("303")[  # noqa: SLF001
            "roleQueueSummary"
        ]
        self.assertEqual(projected["buildingQueue"], {"current": 0, "capacity": 2})
        self.assertEqual(projected["researchQueue"], {"current": 1, "capacity": 1})

    def test_no_available_action_uses_dynamic_build_completion_deadline(self) -> None:
        self._configure(self._habits())
        snapshot = self._snapshot(timer_ms=6_000, hall_level=15)
        snapshot["fiefs"] = [
            fief(
                hall_level=15,
                rows=[building(1, 1, 1, busy=True, timer_ms=6_000)],
                capacity=1,
            )
        ]
        self._install_snapshot(snapshot)
        result = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
        )

        self.assertEqual(result["state"], "waiting")
        self.assertEqual(result["nextWakeAtMillis"], self.clock.value + 8_000)

    def test_exchange_is_durable_and_process_reopen_never_repeats_it(self) -> None:
        self._configure(self._habits(food_to_copper=True))
        self._install_snapshot(self._snapshot(copper=0, food=1_000_000))
        exchanges = 0

        def exchange(_self, execution, _account_ref, food_amount, _context, **_kwargs):
            nonlocal exchanges
            exchanges += 1
            execution.mark_request_sent({
                "feature": "fixture-exchange",
                "foodAmount": food_amount,
            })
            return {"success": True, "message": "兑换成功"}

        def fail_before_send(*_args, **_kwargs):
            raise OperationKnownFailureError(
                "动作前读取失败", code="FIXTURE_BEFORE_SEND"
            )

        self.facade._run_heal_resource_exchange = types.MethodType(  # noqa: SLF001
            exchange, self.facade
        )
        self.facade._run_domestic_action_game_workflow = fail_before_send  # noqa: SLF001
        first = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
        )
        self.assertEqual(first["state"], "retry")
        self.assertEqual(exchanges, 1)

        self.facade.close()
        self.facade = self._open_facade()
        self._install_snapshot(self._snapshot(copper=100_000, food=600_000))

        def forbidden_exchange(*_args, **_kwargs):
            raise AssertionError("completed food-to-copper step was replayed")

        actions = 0

        def action(_self, execution, _body, _context):
            nonlocal actions
            actions += 1
            execution.mark_request_sent({"feature": "fixture-domestic"})
            return {"ok": True, "result": {"success": True}}

        self.facade._run_heal_resource_exchange = forbidden_exchange  # noqa: SLF001
        self.facade._run_domestic_action_game_workflow = types.MethodType(  # noqa: SLF001
            action, self.facade
        )
        resumed = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
        )

        self.assertEqual(resumed["state"], "completed")
        self.assertEqual(actions, 1)

    def test_completed_exchange_with_insufficient_observation_does_not_replay_or_act(self) -> None:
        self._configure(self._habits(food_to_copper=True))
        self._install_snapshot(self._snapshot(copper=0, food=1_000_000))

        def exchange(_self, execution, _account_ref, _food, _context, **_kwargs):
            execution.mark_request_sent({"feature": "fixture-exchange"})
            return {"success": True}

        def fail_before_send(*_args, **_kwargs):
            raise OperationKnownFailureError("读取失败", code="FIXTURE_READ_FAILED")

        self.facade._run_heal_resource_exchange = types.MethodType(  # noqa: SLF001
            exchange, self.facade
        )
        self.facade._run_domestic_action_game_workflow = fail_before_send  # noqa: SLF001
        self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
        )

        self._install_snapshot(self._snapshot(copper=0, food=600_000))
        self.facade._run_heal_resource_exchange = (  # noqa: SLF001
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("exchange was repeated")
            )
        )
        self.facade._run_domestic_action_game_workflow = (  # noqa: SLF001
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("action was sent without resources")
            )
        )
        result = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
        )

        self.assertEqual(result["state"], "waiting-resources")
        self.assertIn("未重复兑换或提交动作", result["message"])

    def test_uncertain_action_is_observed_and_never_replayed(self) -> None:
        self._configure(self._habits())
        self._install_snapshot(self._snapshot())
        sends = 0

        def uncertain(_self, execution, _body, _context):
            nonlocal sends
            sends += 1
            execution.mark_request_sent({"feature": "fixture-domestic"})
            raise OperationUncertainError("内政动作回执不明")

        self.facade._run_domestic_action_game_workflow = types.MethodType(  # noqa: SLF001
            uncertain, self.facade
        )
        with self.assertRaises(OperationUncertainError):
            self.facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
            )
        self.assertEqual(sends, 1)

        self.facade.close()
        self.facade = self._open_facade()
        self._install_snapshot(self._snapshot())
        self.facade._run_domestic_action_game_workflow = (  # noqa: SLF001
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("uncertain mutation was replayed")
            )
        )
        blocked = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
        )

        self.assertEqual(blocked["state"], "blocked")
        self.assertTrue(blocked["requiresAttention"])
        self.assertIn("禁止自动重发", blocked["message"])

    def test_uncertain_action_observed_as_applied_is_closed_without_replay(self) -> None:
        self._configure(self._habits())
        self._install_snapshot(self._snapshot())

        def uncertain(_self, execution, _body, _context):
            execution.mark_request_sent({"feature": "fixture-domestic"})
            raise OperationUncertainError("内政动作回执不明")

        self.facade._run_domestic_action_game_workflow = types.MethodType(  # noqa: SLF001
            uncertain, self.facade
        )
        with self.assertRaises(OperationUncertainError):
            self.facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
            )

        observed = self._snapshot()
        observed["fiefs"] = [fief(hall_level=3, rows=[building(1, 1, 2)])]
        self._install_snapshot(observed)
        self.facade._run_domestic_action_game_workflow = (  # noqa: SLF001
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("observed mutation was replayed")
            )
        )
        result = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
        )

        self.assertEqual(result["state"], "replanned")
        self.assertEqual(self._public()["domesticPendingActionJson"], "{}")

    def test_durable_accepted_receipt_finishes_without_replaying_action(self) -> None:
        self._configure(self._habits())
        self._install_snapshot(self._snapshot())

        def interrupted_after_send(_self, execution, _body, _context):
            execution.mark_request_sent({"feature": "fixture-domestic"})
            raise OperationUncertainError("fixture interruption")

        self.facade._run_domestic_action_game_workflow = types.MethodType(  # noqa: SLF001
            interrupted_after_send, self.facade
        )
        with self.assertRaises(OperationUncertainError):
            self.facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
            )
        pending = json.loads(self._public()["domesticPendingActionJson"])
        pending["progress"]["action"]["state"] = "accepted"
        self.facade._update_account_public_state(  # noqa: SLF001
            "303", {"domesticPendingActionJson": json.dumps(pending)}
        )
        self.facade._run_domestic_action_game_workflow = (  # noqa: SLF001
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("accepted action was replayed")
            )
        )

        result = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
        )

        self.assertEqual(result["state"], "completed")
        last = json.loads(self._public()["domesticLastActionJson"])
        self.assertEqual(
            last["progress"]["action"]["confirmedBy"],
            "durable-accepted-receipt",
        )

    def test_explicit_server_rejection_is_archived_before_delayed_retry(self) -> None:
        self._configure(self._habits())
        self._install_snapshot(self._snapshot())
        calls = 0

        def rejected(_self, execution, _body, _context):
            nonlocal calls
            calls += 1
            execution.mark_request_sent({"feature": "fixture-domestic"})
            raise OperationKnownFailureError(
                "服务器拒绝建筑操作",
                code="DOMESTIC_BUILDING_REJECTED",
            )

        self.facade._run_domestic_action_game_workflow = types.MethodType(  # noqa: SLF001
            rejected, self.facade
        )
        result = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
        )

        self.assertEqual(result["state"], "retry")
        self.assertFalse(result["success"])
        self.assertEqual(calls, 1)
        self.assertEqual(result["nextWakeAtMillis"], self.clock.value + 600_000)
        self.assertEqual(self._public()["domesticPendingActionJson"], "{}")

    def test_technology_only_parse_failure_uses_finite_retry(self) -> None:
        self._configure(self._habits(enabled=False, upgrade_technology=True))
        snapshot = self._snapshot(technology_error="fixture-invalid")
        snapshot["fiefs"] = [
            fief(hall_level=15, rows=[building(1, 1, 15)], capacity=1)
        ]
        self._install_snapshot(snapshot)
        result = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
        )

        self.assertEqual(result["state"], "retry")
        self.assertFalse(result["requiresAttention"])
        self.assertEqual(
            result["errorCode"], "SHARED_DOMESTIC_TECHNOLOGY_STATE_INVALID"
        )
        self.assertEqual(result["nextWakeAtMillis"], self.clock.value + 600_000)

    def test_candidate_change_after_safe_failure_replans_without_sending(self) -> None:
        self._configure(self._habits())
        self._install_snapshot(self._snapshot())
        self.facade._run_domestic_action_game_workflow = (  # noqa: SLF001
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                OperationKnownFailureError("读取失败", code="FIXTURE_READ_FAILED")
            )
        )
        first = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
        )
        self.assertEqual(first["state"], "retry")

        changed = self._snapshot()
        changed["fiefs"] = [
            fief(hall_level=3, rows=[building(1, 1, 2, busy=True, timer_ms=5000)])
        ]
        self._install_snapshot(changed)
        self.facade._run_domestic_action_game_workflow = (  # noqa: SLF001
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("stale candidate was sent")
            )
        )
        replanned = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
        )

        self.assertEqual(replanned["state"], "replanned")
        self.assertEqual(self._public()["domesticPendingActionJson"], "{}")

    def test_technology_parse_failure_retries_but_does_not_block_building(self) -> None:
        self._configure(self._habits(upgrade_technology=True))
        self._install_snapshot(self._snapshot(technology_error="fixture-invalid"))
        actions = 0

        def action(_self, execution, _body, _context):
            nonlocal actions
            actions += 1
            execution.mark_request_sent({"feature": "fixture-building"})
            return {"ok": True, "result": {"success": True}}

        self.facade._run_domestic_action_game_workflow = types.MethodType(  # noqa: SLF001
            action, self.facade
        )
        result = self.facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "303", {"allowedFeatures": ["domestic"]}
        )

        self.assertEqual(result["state"], "completed")
        self.assertEqual(actions, 1)

    def test_android_and_desktop_domestic_habits_normalize_identically(self) -> None:
        desktop = self._habits(enabled=True, upgrade_technology=True)
        self.facade.configure_resident_automation_from_habits("303", desktop)
        self._seed_account(self.facade, "304")
        self.facade.configure_resident_automation_from_habits(
            "304",
            {
                "general": desktop["general"],
                "config": {"domestic": desktop["config"]["domestic"]},
            },
        )
        first = json.loads(self._public()["residentAutomationConfigJson"])[
            "domestic"
        ]
        second_account = json.loads(
            self.facade.account_record_json("304")
        )["account"]
        second = json.loads(
            second_account["session"]["publicState"][
                "residentAutomationConfigJson"
            ]
        )["domestic"]

        self.assertEqual(first, second)

    def test_android_factory_has_no_legacy_internal_affairs_production_entry(self) -> None:
        factory = (
            ROOT
            / "自研辅助源码/app/src/main/java/com/example/dwpmclone/domain/scheduler/TaskFactory.kt"
        ).read_text(encoding="utf-8")
        self.assertNotIn("add(InternalAffairsTask(", factory)


if __name__ == "__main__":
    unittest.main()
