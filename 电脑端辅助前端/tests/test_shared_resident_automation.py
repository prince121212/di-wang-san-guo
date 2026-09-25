from __future__ import annotations

import json
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core import CoreFacade  # noqa: E402
from dwpm_core.automation import (  # noqa: E402
    china_day_key,
    china_start_millis,
    resident_due_decision,
)
from dwpm_core.operations import (  # noqa: E402
    OperationKnownFailureError,
    OperationUncertainError,
)
from dwpm_core.ports import PlatformPorts  # noqa: E402


class FixedClock:
    def __init__(self, value: int = 40_000_000) -> None:
        self.value = value

    def now_millis(self) -> int:
        return self.value


class FakeExecution:
    operation_id = "op_resident_fixture"

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


class SharedResidentAutomationTests(unittest.TestCase):
    @staticmethod
    def _wait_operation(facade: CoreFacade, operation_id: str) -> dict:
        for _ in range(400):
            operation = facade.operation_status(operation_id)["operation"]
            if operation["status"] not in {"QUEUED", "RUNNING"}:
                return operation
            time.sleep(0.005)
        raise AssertionError("resident operation did not finish")

    def _facade(self):
        directory = tempfile.TemporaryDirectory()
        clock = FixedClock()
        facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(Path(directory.name) / "operations.json"),
            ports=PlatformPorts(clock=clock),
        )
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
                    "lastValidatedAt": str(clock.value),
                    "savedTasksStarted": "true",
                    "activeResidentTaskKeys": "brushYellow,mine",
                    "generalsJson": json.dumps([{
                        "id": 7,
                        "idHex": "0000000000000007",
                        "name": "赵云",
                    }]),
                },
            },
        })
        return facade, clock, directory

    @staticmethod
    def _habits() -> dict[str, object]:
        return {
            "formations": [{
                "enabled": True,
                "generalIds": ["7"],
                "soldierType": "轻骑兵",
                "soldierCount": 100,
            }],
            "config": {
                "autoStart": True,
                "startHour": 0,
                "dailyLimit": 3,
                "healWounded": True,
                "autoEnergy": True,
                "energyThreshold": 20,
                "dailyTasks": {
                    "autoSignIn": True,
                    "salary": True,
                },
                "generalVisitGeneralIds": ["7"],
                "brush": {
                    "startX": 10,
                    "startY": 10,
                    "scanLimit": 1,
                    "targetKind": "山贼",
                    "rows": [{
                        "enabled": True,
                        "generalIds": ["7"],
                        "level": 1,
                        "drop": "宝物",
                        "compositionCode": "0500",
                    }],
                },
            },
            "mine": {
                "enabled": True,
                "speed": False,
                "fullLoyalty": True,
                "maxMarchMinutes": 45,
                "centerX": 10,
                "centerY": 10,
                "rows": [{
                    "enabled": True,
                    "generalIds": ["7"],
                    "resourceType": "银矿",
                    "level": 1,
                    "x": 10,
                    "y": 10,
                    "scope": "定点",
                }],
            },
        }

    @classmethod
    def _all_resident_habits(cls) -> dict[str, object]:
        habits = cls._habits()
        habits["raid"] = {
            "enabled": True,
            "auto_loot_enabled": True,
            "rows": [{
                "enabled": True,
                "generalIds": ["7"],
                "playerName": "目标甲",
                "fiefIndex": 1,
                "fullTroops": True,
                "fullLoyalty": False,
            }],
        }
        habits["militaryFuture"] = {
            "lossless": {
                "enabled": True,
                "dailyLimit": 4,
                "rows": [
                    {
                        "enabled": True,
                        "generalIds": ["7"],
                        "level": "10级",
                    },
                    {
                        "enabled": True,
                        "generalIds": ["7"],
                        "level": "7级",
                    },
                ],
            },
            "dungeon": {
                "enabled": True,
                "mode": "loop",
                "dailyTimes": 2,
                "rows": [{
                    "enabled": True,
                    "generalIds": ["7"],
                    "chapter": "第一章",
                    "stage": 1,
                    "chest": "右",
                }],
            },
        }
        habits["ministry"] = {
            "cropEnabled": True,
            "crop": "稻谷",
            "highPriority": True,
            "stealEnabled": False,
            "courtesyEnabled": False,
            "salaryRefresh": False,
        }
        return habits

    def test_due_reducer_uses_priority_and_persists_daily_boundary(self) -> None:
        now = china_start_millis(500, 12)
        configs = {
            "common": {
                "autoStart": True,
                "startHour": 0,
                "dailyLimit": 2,
                "brush": {"rules": [{"enabled": True}]},
            },
            "mine": {"enabled": True, "rows": [{"enabled": True}]},
        }
        first = resident_due_decision(
            configs,
            {},
            now_millis=now,
            saved_tasks_started=True,
            active_keys={"brushYellow", "mine"},
            priorities={"mine": 400, "brushYellow": 200},
        )
        self.assertEqual(first["feature"], "mine")
        self.assertEqual(first["state"]["brush"]["dayKey"], china_day_key(now))

        state = first["state"]
        state["mine"]["nextWakeAtMillis"] = now + 60_000
        brush_due = resident_due_decision(
            configs,
            state,
            now_millis=now,
            saved_tasks_started=True,
            active_keys={"brushYellow", "mine"},
            priorities={"mine": 400, "brushYellow": 200},
        )
        self.assertEqual(brush_due["feature"], "brush")
        state["brush"]["usedCount"] = 2
        limited = resident_due_decision(
            configs,
            state,
            now_millis=now,
            saved_tasks_started=True,
            active_keys={"brushYellow", "mine"},
            priorities={"mine": 400, "brushYellow": 200},
        )
        self.assertIsNone(limited["feature"])
        self.assertEqual(limited["nextWakeAtMillis"], now + 60_000)

    def test_due_reducer_includes_raid_lossless_and_dungeon_daily_limit(self) -> None:
        now = china_start_millis(600, 12)
        configs = {
            "raid": {"enabled": True, "rows": [{"enabled": True}]},
            "lossless": {"enabled": True, "rows": [{"enabled": True}]},
            "dungeon": {
                "enabled": True,
                "settings": {"dailyTimes": 1},
                "rows": [{"enabled": True}],
            },
        }
        first = resident_due_decision(
            configs,
            {},
            now_millis=now,
            saved_tasks_started=True,
            active_keys={"raid", "lossless", "dungeon"},
            priorities={"lossless": 300, "raid": 125, "dungeon": 100},
        )
        self.assertEqual(first["feature"], "lossless")
        state = first["state"]
        state["lossless"]["nextWakeAtMillis"] = now + 60_000
        second = resident_due_decision(
            configs,
            state,
            now_millis=now,
            saved_tasks_started=True,
            active_keys={"raid", "lossless", "dungeon"},
            priorities={"lossless": 300, "raid": 125, "dungeon": 100},
        )
        self.assertEqual(second["feature"], "raid")
        state = second["state"]
        state["raid"]["nextWakeAtMillis"] = now + 60_000
        state["dungeon"]["usedCount"] = 1
        limited = resident_due_decision(
            configs,
            state,
            now_millis=now,
            saved_tasks_started=True,
            active_keys={"raid", "lossless", "dungeon"},
            priorities={"lossless": 300, "raid": 125, "dungeon": 100},
        )
        self.assertIsNone(limited["feature"])
        self.assertEqual(limited["nextWakeAtMillis"], now + 60_000)

    def test_due_reducer_includes_ministry_as_lowest_priority_resident(self) -> None:
        now = china_start_millis(601, 12)
        configs = {
            "dungeon": {
                "enabled": True,
                "settings": {"dailyTimes": 2},
                "rows": [{"enabled": True}],
            },
            "ministry": {"enabled": True, "settings": {"crop": "稻谷"}},
        }
        first = resident_due_decision(
            configs,
            {},
            now_millis=now,
            saved_tasks_started=True,
            active_keys={"dungeon", "ministry"},
            priorities={"dungeon": 100, "ministry": 50},
        )
        self.assertEqual(first["feature"], "dungeon")
        first["state"]["dungeon"]["nextWakeAtMillis"] = now + 60_000
        second = resident_due_decision(
            configs,
            first["state"],
            now_millis=now,
            saved_tasks_started=True,
            active_keys={"dungeon", "ministry"},
            priorities={"dungeon": 100, "ministry": 50},
        )
        self.assertEqual(second["feature"], "ministry")

    def test_python_daily_cycle_keeps_arena_boundary_at_china_twenty_two(self) -> None:
        before = china_start_millis(700, 22) - 1
        boundary = china_start_millis(700, 22)

        arena_before, next_before = CoreFacade._daily_periodic_cycle(  # noqa: SLF001
            "arenaCoins", before
        )
        arena_after, next_after = CoreFacade._daily_periodic_cycle(  # noqa: SLF001
            "arenaCoins", boundary
        )
        default_before, _ = CoreFacade._daily_periodic_cycle(  # noqa: SLF001
            "autoSignIn", before
        )
        default_after, _ = CoreFacade._daily_periodic_cycle(  # noqa: SLF001
            "autoSignIn", boundary
        )

        self.assertEqual(arena_after, arena_before + 1)
        self.assertEqual(next_before, boundary)
        self.assertGreater(next_after, boundary)
        self.assertEqual(default_before, default_after)

    def test_all_resident_habits_are_normalized_and_activated_by_python(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            configured = facade.configure_resident_automation_from_habits(
                "303", self._all_resident_habits()
            )
            self.assertTrue(configured["raidEnabled"])
            self.assertTrue(configured["losslessEnabled"])
            self.assertTrue(configured["dungeonEnabled"])
            self.assertTrue(configured["generalEnabled"])
            self.assertTrue(configured["ministryEnabled"])
            self.assertEqual(
                configured["dailyEnabledKeys"], ["autoSignIn", "salary"]
            )
            record = json.loads(facade.account_record_json("303"))["account"]
            config = json.loads(
                record["session"]["publicState"][
                    "residentAutomationConfigJson"
                ]
            )
            self.assertEqual(config["schemaVersion"], 2)
            self.assertEqual(config["raid"]["rows"][0]["playerName"], "目标甲")
            self.assertEqual(len(config["lossless"]["rows"]), 2)
            self.assertEqual(config["dungeon"]["settings"]["dailyTimes"], 2)
            self.assertEqual(config["ministry"]["settings"]["crop"], "稻谷")
            activation = facade.set_resident_automation_activation(
                "303", True, None
            )
            self.assertEqual(
                activation["activeKeys"],
                [
                    "brushYellow", "dungeon", "general", "lossless", "mine",
                    "ministry", "raid",
                ],
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_brush_rule_separates_brush_number_from_troop_source_row(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            habits = self._habits()
            habits["formations"] = [{
                "enabled": False,
                "generalIds": [],
            }, {
                "enabled": False,
                "generalIds": [],
            }, {
                "enabled": True,
                "generalIds": ["7"],
                "soldierType": "轻骑兵",
                "soldierCount": 100,
            }]
            facade.configure_resident_automation_from_habits("303", habits)
            record = json.loads(facade.account_record_json("303"))["account"]
            config = json.loads(
                record["session"]["publicState"][
                    "residentAutomationConfigJson"
                ]
            )
            rule = config["common"]["brush"]["rules"][0]
            self.assertEqual(rule["sourceRowIndex"], 0)
            self.assertEqual(rule["formationSourceRowIndex"], 2)
            self.assertEqual(rule["formationNumber"], 1)
        finally:
            facade.close()
            directory.cleanup()

    def test_brush_search_batch_stops_on_match_and_reports_scan_boundary(
        self,
    ) -> None:
        facade, _clock, directory = self._facade()
        try:
            fixture = json.loads(
                (
                    ROOT
                    / "shared_core"
                    / "protocol_parity_fixtures.json"
                ).read_text(encoding="utf-8")
            )["fixtures"]["targetSearch8540Complete"]
            target_payload = bytes.fromhex(fixture["responseHex"])
            empty_payload = bytes.fromhex("00bb003800")
            calls: list[bytes] = []
            contexts: list[dict] = []
            target_at: int | None = 3

            def command(
                _self,
                _account_ref,
                _opcode,
                payload,
                _phase,
                request_context,
                *,
                mutation_sent,
            ):
                self.assertFalse(mutation_sent)
                calls.append(bytes(payload))
                contexts.append(dict(request_context))
                response = (
                    target_payload
                    if target_at is not None and len(calls) == target_at
                    else empty_payload
                )
                return {
                    "packets": [{"opcode": 0x8540, "payload": response}],
                }

            facade._execute_host_game_command = types.MethodType(  # noqa: SLF001
                command,
                facade,
            )
            body = facade.brush_search_operation_payload(  # noqa: SLF001
                {
                    "accountRef": "303",
                    "startX": 10,
                    "startY": 10,
                    "targetKind": "山贼",
                    "levels": [1],
                    "drops": [],
                    "scanLimit": 80,
                },
                {},
            )
            body.update({
                "scanOffset": 10,
                "scanBatchSize": 10,
                "stopOnFirstMatch": True,
                "includeScanObservationTargets": True,
            })

            matched = facade._run_brush_search_game_workflow(  # noqa: SLF001
                FakeExecution(), body, {}
            )

            self.assertEqual(len(calls), 3)
            self.assertEqual(matched["scanOffset"], 10)
            self.assertEqual(matched["scanBatchSize"], 10)
            self.assertEqual(matched["scannedCount"], 3)
            self.assertEqual(matched["nextScanOffset"], 13)
            self.assertFalse(matched["scanWrapped"])
            self.assertEqual(len(matched["targets"]), 1)
            self.assertEqual(matched["scanResults"][0]["targetCount"], 0)
            self.assertEqual(matched["scanResults"][2]["matchedCount"], 1)
            self.assertEqual(len(matched["scanResults"][2]["targets"]), 1)
            self.assertEqual(contexts[0]["transportPaceBeforeMillis"], 0)
            self.assertEqual(contexts[1]["transportPaceBeforeMillis"], 200)
            self.assertEqual(contexts[1]["transportPaceJitterMillis"], 150)
            self.assertEqual(contexts[1]["readTimeoutMillis"], 12_000)
            self.assertEqual(contexts[1]["transportMaxAttempts"], 2)
            self.assertEqual(contexts[1]["transportRetryBaseDelayMillis"], 750)
            self.assertEqual(contexts[1]["transportRetryJitterMillis"], 500)

            calls.clear()
            contexts.clear()
            target_at = None
            body.update({"scanOffset": 75, "scanBatchSize": 10})
            wrapped = facade._run_brush_search_game_workflow(  # noqa: SLF001
                FakeExecution(), body, {}
            )
            self.assertEqual(len(calls), 5)
            self.assertEqual(wrapped["scannedCount"], 5)
            self.assertEqual(wrapped["nextScanOffset"], 0)
            self.assertTrue(wrapped["scanWrapped"])

            calls.clear()
            target_at = 1
            manual_body = facade.brush_search_operation_payload(  # noqa: SLF001
                {
                    "accountRef": "303",
                    "startX": 10,
                    "startY": 10,
                    "targetKind": "山贼",
                    "levels": [1],
                    "scanLimit": 2,
                },
                {},
            )
            manual = facade._run_brush_search_game_workflow(  # noqa: SLF001
                FakeExecution(), manual_body, {}
            )
            self.assertEqual(len(calls), 2)
            self.assertEqual(manual["scannedCount"], 2)
            self.assertTrue(manual["scanWrapped"])
        finally:
            facade.close()
            directory.cleanup()

    def test_brush_rules_keep_independent_persisted_scan_cursors(self) -> None:
        facade, clock, directory = self._facade()
        reopened = None
        operation_path = str(Path(directory.name) / "operations.json")
        try:
            habits = self._habits()
            habits["mine"] = {"enabled": False, "rows": []}
            brush = habits["config"]["brush"]
            brush["scanLimit"] = 80
            first_row = dict(brush["rows"][0])
            second_row = {**first_row, "level": 2}
            brush["rows"] = [first_row, second_row]
            facade.configure_resident_automation_from_habits("303", habits)
            captured: list[tuple[int, list[int]]] = []

            def empty_batch(_self, _execution, body, _context):
                offset = int(body["scanOffset"])
                count = min(
                    int(body["scanBatchSize"]),
                    int(body["scanLimit"]) - offset,
                )
                captured.append((offset, list(body["levels"])))
                next_offset = offset + count
                wrapped = next_offset >= int(body["scanLimit"])
                return {
                    "targets": [],
                    "scanOffset": offset,
                    "scanLimit": int(body["scanLimit"]),
                    "scanBatchSize": int(body["scanBatchSize"]),
                    "scannedCount": count,
                    "nextScanOffset": 0 if wrapped else next_offset,
                    "scanWrapped": wrapped,
                    "scannedCoordinates": [],
                    "scanResults": [],
                }

            facade._run_brush_search_game_workflow = types.MethodType(  # noqa: SLF001
                empty_batch,
                facade,
            )

            def config_and_state(target: CoreFacade) -> tuple[dict, dict]:
                record = json.loads(target.account_record_json("303"))["account"]
                public = record["session"]["publicState"]
                return (
                    json.loads(public["residentAutomationConfigJson"]),
                    json.loads(public["residentAutomationStateJson"]),
                )

            for _ in range(2):
                config, state = config_and_state(facade)
                result = facade._run_configured_brush_tick(  # noqa: SLF001
                    FakeExecution(), "303", config, state, {}
                )
                self.assertEqual(
                    result["nextWakeAtMillis"],
                    clock.value + 2_000,
                )

            self.assertEqual(captured, [(0, [1]), (0, [2])])
            _config, stored_state = config_and_state(facade)
            cursors = stored_state["brush"]["scanCursorsByRule"]
            self.assertEqual(len(cursors), 2)
            self.assertEqual(
                sorted(row["nextScanOffset"] for row in cursors.values()),
                [5, 5],
            )

            facade.close()
            facade = None
            reopened = CoreFacade(
                shared_root=ROOT / "shared_core",
                operation_store_path=operation_path,
                ports=PlatformPorts(clock=clock),
            )
            reopened._run_brush_search_game_workflow = types.MethodType(  # noqa: SLF001
                empty_batch,
                reopened,
            )
            config, state = config_and_state(reopened)
            reopened._run_configured_brush_tick(  # noqa: SLF001
                FakeExecution(), "303", config, state, {}
            )
            self.assertEqual(captured[-1], (5, [1]))
            _config, stored_state = config_and_state(reopened)
            offsets_by_key = {
                key: row["nextScanOffset"]
                for key, row in stored_state["brush"][
                    "scanCursorsByRule"
                ].items()
            }
            self.assertEqual(offsets_by_key["row:0|generals:7"], 10)
            self.assertEqual(offsets_by_key["row:1|generals:7"], 5)
        finally:
            if facade is not None:
                facade.close()
            if reopened is not None:
                reopened.close()
            directory.cleanup()

    def test_brush_stale_dispatch_keeps_advanced_scan_cursor(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            habits = self._habits()
            habits["mine"] = {"enabled": False, "rows": []}
            habits["config"]["brush"]["scanLimit"] = 80
            facade.configure_resident_automation_from_habits("303", habits)
            record = json.loads(facade.account_record_json("303"))["account"]
            public = record["session"]["publicState"]
            config = json.loads(public["residentAutomationConfigJson"])
            state = json.loads(public["residentAutomationStateJson"])

            def matched(_self, _execution, body, _context):
                offset = int(body["scanOffset"])
                return {
                    "targets": [{
                        "id": 90,
                        "x": 10,
                        "y": 10,
                        "kind": "山贼",
                        "level": 1,
                    }],
                    "scanOffset": offset,
                    "scanLimit": int(body["scanLimit"]),
                    "scanBatchSize": int(body["scanBatchSize"]),
                    "scannedCount": 1,
                    "nextScanOffset": offset + 1,
                    "scanWrapped": False,
                    "scannedCoordinates": [[10, 10]],
                    "scanResults": [{
                        "scanCoord": [10, 10],
                        "targetCount": 1,
                        "matchedCount": 1,
                    }],
                }

            def stale(*_args, **_kwargs):
                raise OperationKnownFailureError(
                    "目标不存在，不能到达。",
                    code="BRUSH_DISPATCH_REJECTED",
                )

            facade._run_brush_search_game_workflow = types.MethodType(  # noqa: SLF001
                matched,
                facade,
            )
            facade._run_brush_execute_game_workflow = types.MethodType(  # noqa: SLF001
                stale,
                facade,
            )
            with self.assertRaises(OperationKnownFailureError):
                facade._run_configured_brush_tick(  # noqa: SLF001
                    FakeExecution(), "303", config, state, {}
                )

            stored = json.loads(facade.account_record_json("303"))["account"]
            stored_state = json.loads(
                stored["session"]["publicState"][
                    "residentAutomationStateJson"
                ]
            )
            cursor = stored_state["brush"]["scanCursorsByRule"][
                "row:0|generals:7"
            ]
            self.assertEqual(cursor["lastScannedCount"], 1)
            self.assertEqual(cursor["nextScanOffset"], 1)
        finally:
            facade.close()
            directory.cleanup()

    def test_configured_daily_tick_runs_one_python_workflow_and_persists_deadline(
        self,
    ) -> None:
        facade, clock, directory = self._facade()
        try:
            facade.configure_resident_automation_from_habits(
                "303", self._all_resident_habits()
            )
            calls: list[str] = []

            def sign_in(_self, _execution, _body, _context):
                calls.append("autoSignIn")
                return {"ok": True, "result": {
                    "success": True,
                    "completed": True,
                    "message": "fixture sign in",
                }}

            facade._run_daily_sign_in_game_workflow = types.MethodType(  # noqa: SLF001
                sign_in, facade
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {
                    "allowedFeatures": ["daily"],
                    "dailyAllowedKeys": ["autoSignIn", "salary"],
                },
            )

            self.assertEqual(result["feature"], "daily")
            self.assertEqual(result["dailyKey"], "autoSignIn")
            self.assertEqual(result["state"], "completed")
            self.assertEqual(calls, ["autoSignIn"])
            record = json.loads(facade.account_record_json("303"))["account"]
            state = json.loads(
                record["session"]["publicState"]["residentAutomationStateJson"]
            )
            self.assertEqual(
                state["daily"]["autoSignIn"]["lastState"], "completed"
            )
            self.assertGreater(
                state["daily"]["autoSignIn"]["nextWakeAtMillis"],
                clock.value,
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_daily_completion_wakes_for_the_next_due_sibling(self) -> None:
        facade, clock, directory = self._facade()
        try:
            habits = self._habits()
            habits["mine"] = {"enabled": False, "rows": []}
            habits["config"]["dailyTasks"] = {
                "autoSignIn": True,
                "arenaCoins": True,
                "autoDonate": True,
            }
            facade.configure_resident_automation_from_habits("303", habits)
            facade.set_resident_automation_activation("303", True, ["daily"])
            calls: list[str] = []

            def completed(key: str):
                def workflow(_self, _execution, _body, _context):
                    calls.append(key)
                    return {"ok": True, "result": {
                        "success": True,
                        "completed": True,
                        "message": f"fixture {key}",
                    }}
                return workflow

            for key, method_name in (
                ("autoSignIn", "_run_daily_sign_in_game_workflow"),
                ("arenaCoins", "_run_daily_arena_coins_game_workflow"),
                ("autoDonate", "_run_daily_donate_game_workflow"),
            ):
                setattr(
                    facade,
                    method_name,
                    types.MethodType(completed(key), facade),
                )

            first = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["daily"]}
            )
            self.assertEqual("autoSignIn", first["dailyKey"])
            self.assertEqual(["autoSignIn"], calls)
            # The sign-in deadline is tomorrow, but the sibling arena/donation
            # keys are still due now.  The account lane must wake immediately.
            self.assertEqual(clock.value, first["nextWakeAtMillis"])

            second = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["daily"]}
            )
            self.assertEqual("autoDonate", second["dailyKey"])
            self.assertEqual(["autoSignIn", "autoDonate"], calls)

            # Arena coins are not due before the China 22:00 boundary.  Move
            # the fixed clock to that exact deadline and verify it becomes the
            # next executable sibling instead of having blocked donation.
            clock.value = int(second["nextWakeAtMillis"])
            third = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["daily"]}
            )
            self.assertEqual("arenaCoins", third["dailyKey"])
            self.assertEqual(
                ["autoSignIn", "autoDonate", "arenaCoins"], calls
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_daily_gate_precedes_due_resident_and_releases_lane_after_cycle(self) -> None:
        facade, clock, directory = self._facade()
        try:
            habits = self._habits()
            habits["config"]["dailyTasks"] = {
                "autoSignIn": True,
                "autoDonate": True,
            }
            facade.configure_resident_automation_from_habits("303", habits)
            facade.set_resident_automation_activation(
                "303", True, ["mine", "brushYellow", "daily"]
            )
            calls: list[str] = []

            def daily_success(key: str):
                def workflow(_self, _execution, _body, _context):
                    calls.append(key)
                    return {"ok": True, "result": {
                        "success": True,
                        "completed": True,
                        "message": f"fixture {key}",
                    }}
                return workflow

            facade._run_daily_sign_in_game_workflow = types.MethodType(  # noqa: SLF001
                daily_success("autoSignIn"), facade
            )
            facade._run_daily_donate_game_workflow = types.MethodType(  # noqa: SLF001
                daily_success("autoDonate"), facade
            )

            def mine(_self, _execution, _account_ref, _configs, _state, _context):
                calls.append("mine")
                return {
                    "feature": "mine",
                    "state": "dispatched",
                    "success": True,
                    "message": "fixture mine",
                    "nextWakeAtMillis": clock.value + 60_000,
                }

            facade._run_configured_mine_tick = types.MethodType(  # noqa: SLF001
                mine, facade
            )

            first = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {
                    "allowedFeatures": ["mine", "brush", "daily"],
                },
            )
            self.assertEqual(first["dailyKey"], "autoSignIn")
            self.assertEqual(calls, ["autoSignIn"])

            second = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {
                    "allowedFeatures": ["mine", "brush", "daily"],
                },
            )
            self.assertEqual(second["dailyKey"], "autoDonate")
            self.assertEqual(calls, ["autoSignIn", "autoDonate"])

            third = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {
                    "allowedFeatures": ["mine", "brush", "daily"],
                },
            )
            self.assertEqual(third["feature"], "mine")
            self.assertEqual(calls, ["autoSignIn", "autoDonate", "mine"])
        finally:
            facade.close()
            directory.cleanup()

    def test_daily_retry_deadline_does_not_starve_due_resident(self) -> None:
        facade, clock, directory = self._facade()
        try:
            habits = self._habits()
            habits["config"]["dailyTasks"] = {"autoSignIn": True}
            facade.configure_resident_automation_from_habits("303", habits)
            facade.set_resident_automation_activation(
                "303", True, ["mine", "daily"]
            )

            def fail_sign_in(_self, _execution, _body, _context):
                daily_calls.append("autoSignIn")
                raise OperationKnownFailureError(
                    "签到暂时失败",
                    code="DAILY_SIGN_IN_REJECTED",
                )

            facade._run_daily_sign_in_game_workflow = types.MethodType(  # noqa: SLF001
                fail_sign_in, facade
            )
            daily_calls: list[str] = []
            resident_calls = 0

            def mine(_self, _execution, _account_ref, _configs, _state, _context):
                nonlocal resident_calls
                resident_calls += 1
                return {
                    "feature": "mine",
                    "state": "waiting",
                    "success": True,
                    "message": "fixture mine waiting",
                    "nextWakeAtMillis": clock.value + 60_000,
                }

            facade._run_configured_mine_tick = types.MethodType(  # noqa: SLF001
                mine, facade
            )
            resumed = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {"allowedFeatures": ["mine", "daily"]},
            )
            self.assertEqual(resumed["feature"], "mine")
            self.assertEqual(daily_calls, ["autoSignIn"])
            self.assertEqual(resident_calls, 1)
            # The only daily key is persisted as retry with a future deadline;
            # it will regain priority when that deadline arrives.
            state = json.loads(
                json.loads(facade.account_record_json("303"))["account"]
                ["session"]["publicState"]["residentAutomationStateJson"]
            )
            self.assertEqual(state["daily"]["autoSignIn"]["lastState"], "retry")
            self.assertGreater(
                int(state["daily"]["autoSignIn"]["nextWakeAtMillis"]),
                clock.value,
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_daily_lane_never_returns_a_wake_before_a_slow_tick_finishes(
        self,
    ) -> None:
        facade, clock, directory = self._facade()
        try:
            habits = self._habits()
            habits["mine"] = {"enabled": False, "rows": []}
            habits["config"]["dailyTasks"] = {
                "autoSignIn": True,
                "autoDonate": True,
            }
            facade.configure_resident_automation_from_habits("303", habits)
            facade.set_resident_automation_activation("303", True, ["daily"])
            started_at = clock.value

            def slow_sign_in(_self, _execution, _body, _context):
                clock.value += 120_000
                return {"ok": True, "result": {
                    "success": True,
                    "completed": True,
                    "message": "fixture slow sign in",
                }}

            facade._run_daily_sign_in_game_workflow = types.MethodType(  # noqa: SLF001
                slow_sign_in, facade
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["daily"]}
            )

            self.assertEqual("autoSignIn", result["dailyKey"])
            self.assertGreater(clock.value, started_at)
            # Donation was due when this tick started.  Once sign-in finishes,
            # the lane should run it immediately, but must not publish the old
            # (already elapsed) timestamp as a future business deadline.
            self.assertEqual(clock.value, result["nextWakeAtMillis"])
            self.assertGreater(
                result["taskNextWakeAtMillis"], result["nextWakeAtMillis"]
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_known_daily_failure_does_not_block_due_sibling(self) -> None:
        facade, clock, directory = self._facade()
        try:
            habits = self._habits()
            habits["mine"] = {"enabled": False, "rows": []}
            habits["config"]["dailyTasks"] = {
                "autoSignIn": True,
                "autoDonate": True,
            }
            facade.configure_resident_automation_from_habits("303", habits)
            facade.set_resident_automation_activation("303", True, ["daily"])
            calls: list[str] = []

            def sign_in_failure(_self, _execution, _body, _context):
                calls.append("autoSignIn")
                raise OperationKnownFailureError(
                    "签到被服务器拒绝",
                    code="DAILY_SIGN_IN_REJECTED",
                )

            def donate_success(_self, _execution, _body, _context):
                calls.append("autoDonate")
                return {"ok": True, "result": {
                    "success": True,
                    "completed": True,
                    "message": "捐献成功",
                }}

            facade._run_daily_sign_in_game_workflow = types.MethodType(  # noqa: SLF001
                sign_in_failure, facade
            )
            facade._run_daily_donate_game_workflow = types.MethodType(  # noqa: SLF001
                donate_success, facade
            )

            failed = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["daily"]}
            )
            self.assertEqual("autoSignIn", failed["dailyKey"])
            self.assertEqual("retry", failed["state"])
            self.assertEqual(clock.value, failed["nextWakeAtMillis"])

            sibling = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["daily"]}
            )
            self.assertEqual("autoDonate", sibling["dailyKey"])
            self.assertEqual(["autoSignIn", "autoDonate"], calls)

            state = json.loads(
                json.loads(facade.account_record_json("303"))["account"]
                ["session"]["publicState"]["residentAutomationStateJson"]
            )
            self.assertGreaterEqual(
                int(state["daily"]["nextWakeAtMillis"]), clock.value
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_uncertain_pending_probe_backs_off_instead_of_spinning(self) -> None:
        """A stuck recovery probe must yield the lane between retries.

        账号 202 的真机事故：种菜待决账本的恢复探针持续命中 0xe320 布局
        变种，OperationUncertainError 每个 tick 都中断调度，账本又没有任何
        退避标记，于是六部每 ~11 秒独占一次车道，其余功能数小时颗粒无收。
        探针是只读的——退避 60 秒再试不影响安全，其他功能照常运行。
        """
        facade, clock, directory = self._facade()
        try:
            facade._update_account_public_state(  # noqa: SLF001
                "303",
                {
                    "ministryPendingPlantJson": json.dumps({
                        "createdAtMillis": clock.value - 5_000,
                        "sendState": "uncertain",
                        "crop": "稻谷",
                        "occupiedBefore": 3,
                    })
                },
            )
            calls: list[str] = []

            def uncertain_probe(_self, *_args, **_kwargs):
                calls.append("ministry")
                raise OperationUncertainError("户部菜地状态解析失败：fixture")

            facade._run_configured_ministry_tick = types.MethodType(  # noqa: SLF001
                uncertain_probe, facade
            )
            with self.assertRaises(OperationUncertainError):
                facade._run_automation_recovery_tick(  # noqa: SLF001
                    FakeExecution(), "303", {"allowedFeatures": ["ministry"]}
                )
            self.assertEqual(calls, ["ministry"])

            ledger = json.loads(
                json.loads(facade.account_record_json("303"))["account"]
                ["session"]["publicState"]["ministryPendingPlantJson"]
            )
            self.assertEqual(
                ledger["nextPollAtMillis"], clock.value + 60_000
            )
            # 退避期内再次 tick：待决探针不得再被选中，车道让给别的功能。
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["ministry"]}
            )
            self.assertEqual(calls, ["ministry"])
            self.assertNotEqual(result.get("feature"), "ministry")

            # 退避到期后探针恢复重试。
            clock.value += 60_001
            with self.assertRaises(OperationUncertainError):
                facade._run_automation_recovery_tick(  # noqa: SLF001
                    FakeExecution(), "303", {"allowedFeatures": ["ministry"]}
                )
            self.assertEqual(calls, ["ministry", "ministry"])
        finally:
            facade.close()
            directory.cleanup()

    def test_daily_structured_results_are_politics_success_records(self) -> None:
        facade, clock, directory = self._facade()
        try:
            sign_in = facade._append_resident_success_record(  # noqa: SLF001
                "303",
                {
                    "feature": "daily",
                    "dailyKey": "autoSignIn",
                    "cycleKey": 777,
                    "state": "completed",
                    "success": True,
                    "completed": True,
                    "message": "铜钱:10000获得成功",
                },
            )
            skipped = facade._append_resident_success_record(  # noqa: SLF001
                "303",
                {
                    "feature": "daily",
                    "dailyKey": "salary",
                    "cycleKey": 777,
                    "state": "completed",
                    "success": True,
                    "completed": True,
                    "skipped": True,
                    "skipReason": "national-citizen",
                    "statusText": "已做（国民跳过）",
                    "message": "国民跳过",
                },
            )
            self.assertEqual("签到", sign_in["category"])
            self.assertEqual("俸禄", skipped["category"])
            self.assertTrue(skipped["detail"]["skipped"])
            self.assertEqual(
                "daily:salary:777", skipped["dedupeKey"]
            )

            response = facade.dispatch(
                "GET",
                "/api/success-records",
                {"accountRef": "303", "category": "签到"},
            )
            self.assertEqual(200, response.status)
            self.assertEqual("签到", response.body["entries"][0]["category"])
            self.assertIn("铜钱", response.body["entries"][0]["message"])
        finally:
            facade.close()
            directory.cleanup()

    def test_daily_uncertain_result_blocks_same_cycle_without_replay(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            habits = self._habits()
            habits["config"]["dailyTasks"] = {"autoSignIn": True}
            facade.configure_resident_automation_from_habits("303", habits)
            calls = 0

            def uncertain(_self, _execution, _body, _context):
                nonlocal calls
                calls += 1
                raise OperationUncertainError("fixture daily receipt missing")

            facade._run_daily_sign_in_game_workflow = types.MethodType(  # noqa: SLF001
                uncertain, facade
            )
            with self.assertRaises(OperationUncertainError):
                facade._run_automation_recovery_tick(  # noqa: SLF001
                    FakeExecution(), "303", {"allowedFeatures": ["daily"]}
                )
            blocked = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["daily"]}
            )

            self.assertEqual(calls, 1)
            self.assertEqual(blocked["state"], "idle")
            self.assertIsNone(blocked["feature"])
        finally:
            facade.close()
            directory.cleanup()

    def test_missing_session_uses_long_retry_for_daily_and_resident(self) -> None:
        facade, clock, directory = self._facade()
        try:
            habits = self._habits()
            habits["mine"] = {"enabled": False, "rows": []}
            habits["config"]["dailyTasks"] = {"autoSignIn": True}
            facade.configure_resident_automation_from_habits("303", habits)
            facade.set_resident_automation_activation(
                "303", True, ["brushYellow"]
            )

            def missing_session(*_args, **_kwargs):
                raise OperationKnownFailureError(
                    "fixture missing session",
                    code="GAME_COMMAND_SESSION_MISSING",
                )

            facade._run_daily_sign_in_game_workflow = types.MethodType(  # noqa: SLF001
                missing_session, facade
            )
            daily = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {
                    "allowedFeatures": ["daily"],
                    "dailyAllowedKeys": ["autoSignIn"],
                },
            )
            self.assertEqual(daily["state"], "retry")
            self.assertEqual(
                daily["nextWakeAtMillis"], clock.value + 300_000
            )

            facade._run_configured_brush_tick = types.MethodType(  # noqa: SLF001
                missing_session, facade
            )
            resident = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["brush"]}
            )
            self.assertEqual(resident["state"], "retry")
            self.assertEqual(
                resident["nextWakeAtMillis"], clock.value + 300_000
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_configured_lossless_tick_advances_shared_cursor(self) -> None:
        facade, clock, directory = self._facade()
        try:
            facade.configure_resident_automation_from_habits(
                "303", self._all_resident_habits()
            )
            facade.set_resident_automation_activation(
                "303", True,
                ["brushYellow", "mine", "raid", "lossless", "dungeon"],
            )
            facade._update_account_public_state(  # noqa: SLF001
                "303",
                {"residentAutomationStateJson": json.dumps({
                    "brush": {"nextWakeAtMillis": clock.value + 60_000},
                    "mine": {"nextWakeAtMillis": clock.value + 60_000},
                    "raid": {"nextWakeAtMillis": clock.value + 60_000},
                    "lossless": {"cursor": 0, "nextWakeAtMillis": clock.value},
                    "dungeon": {"nextWakeAtMillis": clock.value + 60_000},
                })},
            )
            captured: dict[str, object] = {}

            def lossless(_self, _execution, body, _context):
                captured.update(body)
                return {"ok": True, "result": {
                    "feature": "lossless",
                    "state": "fighting",
                    "success": True,
                    "dispatchAccepted": True,
                    "battleId": 909,
                    "message": "fixture lossless accepted",
                    "nextWakeAtMillis": clock.value + 20_000,
                }}

            facade._run_lossless_action_game_workflow = types.MethodType(  # noqa: SLF001
                lossless, facade
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {"allowedFeatures": ["mine", "lossless", "brush", "raid", "dungeon"]},
            )
            self.assertEqual(result["feature"], "lossless")
            self.assertEqual(captured["dailyLimit"], 4)
            self.assertEqual(captured["level"], 10)
            record = json.loads(facade.account_record_json("303"))["account"]
            state = json.loads(
                record["session"]["publicState"][
                    "residentAutomationStateJson"
                ]
            )
            self.assertEqual(state["lossless"]["cursor"], 1)
            self.assertEqual(
                state["lossless"]["nextWakeAtMillis"], clock.value + 20_000
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_dungeon_resource_wait_releases_scheduler_for_other_tasks(self) -> None:
        facade, clock, directory = self._facade()
        try:
            facade.configure_resident_automation_from_habits(
                "303", self._all_resident_habits()
            )
            facade.set_resident_automation_activation(
                "303", True, ["dungeon", "ministry"]
            )
            pending = {
                "generalIds": [7],
                "preDispatchMutationState": "failed",
                "preDispatchMutationError": (
                    "副本检查到赵云体力=28，低于自动加体阈值40，"
                    "但宝库没有活血丹"
                ),
                "prepareSendState": "not-sent",
                "dispatchSendState": "not-sent",
                "chestSendState": "not-sent",
                "requiresAttention": True,
            }
            facade._save_automation_pending_record(  # noqa: SLF001
                "303", "dungeonPendingRunJson", pending
            )
            facade._run_dungeon_status_game_workflow = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: {
                    "phase": "idle",
                    "active": False,
                },
                facade,
            )

            first = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {"allowedFeatures": ["dungeon", "ministry"]},
            )
            self.assertEqual(first["state"], "waiting-resources")
            # The feature's own deadline remains five minutes away, while the
            # account wake is pulled forward for another due task.
            self.assertEqual(first["nextWakeAtMillis"], clock.value)
            record = json.loads(facade.account_record_json("303"))["account"]
            state = json.loads(
                record["session"]["publicState"][
                    "residentAutomationStateJson"
                ]
            )
            self.assertEqual(
                state["dungeon"]["nextWakeAtMillis"],
                clock.value + 300_000,
            )

            facade._run_configured_ministry_tick = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: {
                    "feature": "ministry",
                    "state": "completed",
                    "success": True,
                    "message": "六部任务已执行",
                    "nextWakeAtMillis": clock.value + 600_000,
                },
                facade,
            )
            second = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {"allowedFeatures": ["dungeon", "ministry"]},
            )
            self.assertEqual(second["feature"], "ministry")
            self.assertEqual(second["state"], "completed")
        finally:
            facade.close()
            directory.cleanup()

    def test_configured_ministry_tick_uses_existing_shared_plant_workflow(self) -> None:
        facade, clock, directory = self._facade()
        try:
            facade.configure_resident_automation_from_habits(
                "303", self._all_resident_habits()
            )
            facade.set_resident_automation_activation(
                "303", True, ["ministry"]
            )
            captured: dict[str, object] = {}

            def plant(_self, _execution, body, _context):
                captured.update(body)
                return {"ok": True, "result": {
                    "success": True,
                    "message": "fixture ministry planted",
                    "raw": {"phase": "planted"},
                }}

            facade._run_hubu_plant_game_workflow = types.MethodType(  # noqa: SLF001
                plant, facade
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["ministry"]}
            )

            self.assertEqual(result["feature"], "ministry")
            self.assertEqual(result["state"], "completed")
            self.assertEqual(captured["confirm"], "hubu-batch-plant")
            self.assertEqual(captured["crop"], "稻谷")
            self.assertEqual(
                result["nextWakeAtMillis"],
                clock.value + 10 * 60 * 1000,
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_dungeon_completion_count_is_idempotent_by_resident_token(self) -> None:
        facade, clock, directory = self._facade()
        try:
            context = facade._configured_resident_context(  # noqa: SLF001
                "dungeon", 0, 1
            )
            result = {
                "feature": "dungeon",
                "state": "chest-opened",
                "success": True,
                "battleId": 808,
                "message": "fixture dungeon completed",
                "nextWakeAtMillis": clock.value + 500,
            }
            facade._apply_resident_result_state(  # noqa: SLF001
                "303", result, context, from_pending=True
            )
            facade._apply_resident_result_state(  # noqa: SLF001
                "303", result, context, from_pending=True
            )
            record = json.loads(facade.account_record_json("303"))["account"]
            state = json.loads(
                record["session"]["publicState"][
                    "residentAutomationStateJson"
                ]
            )
            self.assertEqual(state["dungeon"]["usedCount"], 1)
            self.assertEqual(
                state["dungeon"]["lastCompletionToken"],
                context["completionToken"],
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_lossless_round_counts_on_guard_dispatch_even_without_clear(self) -> None:
        facade, clock, directory = self._facade()
        try:
            context = facade._configured_resident_context(  # noqa: SLF001
                "lossless", 0, 1
            )
            first_guard = {
                "feature": "lossless",
                "state": "fighting",
                "success": True,
                "dispatchAccepted": True,
                "battleId": 901,
                "stage": {
                    "level": 9,
                    "stageId": 0x2F11,
                    "stageName": "卫兵",
                },
                # This is the pre-dispatch status, so the new round is not in
                # the server counter yet.
                "status": {"usedAttempts": 0, "remainingAttempts": 5},
            }
            facade._apply_resident_result_state(  # noqa: SLF001
                "303", first_guard, context
            )
            # Re-applying one durable operation result must not count twice.
            facade._apply_resident_result_state(  # noqa: SLF001
                "303", first_guard, context
            )

            later_stage = {
                **first_guard,
                "battleId": 902,
                "stage": {
                    "level": 9,
                    "stageId": 0x2F12,
                    "stageName": "小队长",
                },
                "status": {"usedAttempts": 1, "remainingAttempts": 4},
            }
            facade._apply_resident_result_state(  # noqa: SLF001
                "303", later_stage, context
            )

            record = json.loads(facade.account_record_json("303"))["account"]
            state = json.loads(
                record["session"]["publicState"][
                    "residentAutomationStateJson"
                ]
            )["lossless"]
            self.assertEqual(state["dayKey"], china_day_key(clock.value))
            self.assertEqual(state["usedCount"], 1)
            self.assertEqual(state["lastRoundBattleId"], 901)

            # A later server status can safely backfill rounds that happened
            # before the local counter was introduced.
            facade._apply_resident_result_state(  # noqa: SLF001
                "303",
                {
                    "feature": "lossless",
                    "state": "cooldown",
                    "success": True,
                    "status": {"usedAttempts": 3, "remainingAttempts": 2},
                },
                context,
                from_pending=True,
            )
            record = json.loads(facade.account_record_json("303"))["account"]
            state = json.loads(
                record["session"]["publicState"][
                    "residentAutomationStateJson"
                ]
            )["lossless"]
            self.assertEqual(state["usedCount"], 3)
        finally:
            facade.close()
            directory.cleanup()

    def test_brush_dispatch_persists_one_shared_success_record(self) -> None:
        facade, clock, directory = self._facade()
        try:
            habits = self._habits()
            habits["mine"] = {"enabled": False, "rows": []}
            facade.configure_resident_automation_from_habits("303", habits)
            facade.set_resident_automation_activation(
                "303", True, ["brushYellow"]
            )

            def dispatched(*_args, **_kwargs):
                return {
                    "feature": "brush",
                    "state": "dispatched",
                    "success": True,
                    "dispatchAccepted": True,
                    "battleId": 303_701,
                    "formationNumber": 3,
                    "formationSourceRowIndex": 2,
                    "sourceRowIndex": 0,
                    "target": {"name": "7级山贼", "x": 9, "y": 8},
                    "message": "刷黄出征已确认：battleId=303701",
                    "nextWakeAtMillis": clock.value + 30_000,
                }

            facade._run_configured_brush_tick = types.MethodType(  # noqa: SLF001
                dispatched, facade
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["brush"]}
            )
            self.assertEqual("brush:battle:303701", result["successRecord"]["dedupeKey"])

            duplicate = facade._append_resident_success_record(  # noqa: SLF001
                "303", result
            )
            self.assertIsNone(duplicate)
            stored = json.loads(facade.account_record_json("303"))["account"]
            records = json.loads(
                stored["session"]["publicState"]["successRecordsJson"]
            )
            self.assertEqual(1, len(records))
            self.assertEqual("刷黄", records[0]["category"])
            self.assertEqual(
                records[0]["message"],
                "编队1 > 7级山贼(9，8)（battleId=303701）",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_reconciled_uncertain_heal_is_skipped_until_dispatch_succeeds(
        self,
    ) -> None:
        facade, _clock, directory = self._facade()
        try:
            habits = self._habits()
            habits["mine"] = {"enabled": False, "rows": []}
            habits["formations"] = [
                {"enabled": False, "generalIds": []},
                {"enabled": False, "generalIds": []},
                dict(habits["formations"][0]),
            ]
            facade.configure_resident_automation_from_habits("303", habits)
            record = json.loads(facade.account_record_json("303"))["account"]
            public = record["session"]["publicState"]
            configs = json.loads(public["residentAutomationConfigJson"])
            state = json.loads(public["residentAutomationStateJson"])
            state["brush"] = {
                **dict(state.get("brush") or {}),
                "skipHealOnce": True,
                "skipHealReason": "uncertain-pre-dispatch-heal",
            }
            captured: dict[str, object] = {}
            facade._run_brush_search_game_workflow = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: {
                    "targets": [{
                        "id": 9,
                        "x": 10,
                        "y": 10,
                        "name": "1级山贼",
                    }]
                },
                facade,
            )

            def execute(_self, _execution, body, _context):
                captured.update(body)
                return {"result": {
                    "success": True,
                    "successBattleId": 909,
                    "target": body["target"],
                    "message": "fixture brush accepted",
                }}

            facade._run_brush_execute_game_workflow = types.MethodType(  # noqa: SLF001
                execute, facade
            )
            result = facade._run_configured_brush_tick(  # noqa: SLF001
                FakeExecution(), "303", configs, state, {}
            )

            self.assertEqual(result["state"], "dispatched")
            self.assertEqual(result["formationSourceRowIndex"], 2)
            self.assertEqual(result["formationNumber"], 1)
            host_settings = dict(captured["hostSettings"])
            self.assertIs(host_settings["healWounded"], False)
            stored = json.loads(facade.account_record_json("303"))["account"]
            stored_state = json.loads(
                stored["session"]["publicState"][
                    "residentAutomationStateJson"
                ]
            )
            self.assertNotIn("skipHealOnce", stored_state["brush"])
            self.assertIn("lastSkippedHealAtMillis", stored_state["brush"])
        finally:
            facade.close()
            directory.cleanup()

    def test_habits_hydration_and_tick_choose_python_owned_mine(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            configured = facade.configure_resident_automation_from_habits(
                "303", self._habits()
            )
            self.assertTrue(configured["brushEnabled"])
            self.assertTrue(configured["mineEnabled"])
            captured: dict[str, object] = {}
            facade._run_mine_search_game_workflow = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: {
                    "targets": [{
                        "id": 88,
                        "x": 10,
                        "y": 10,
                        "mineType": "SILVER", "level": 1,
                        "playerOccupied": False,
                    }]
                },
                facade,
            )

            def execute(_self, _execution, body, _context):
                captured.update(body)
                return {"result": {
                    "success": True,
                    "dispatchAccepted": True,
                    "successBattleId": 991,
                    "target": body["target"],
                    "message": "fixture mine accepted",
                }}

            facade._run_mine_execute_game_workflow = types.MethodType(  # noqa: SLF001
                execute, facade
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["mine"]}
            )
            self.assertEqual(result["feature"], "mine")
            self.assertEqual(result["state"], "dispatched")
            self.assertEqual(captured["generalIds"], ["7"])
            self.assertTrue(captured["withdrawDefense"])
            self.assertEqual(
                captured["hostSettings"]["formations"][0]["generalId"],
                "7",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_mine_at_the_resource_point_cap_waits_without_scanning(self) -> None:
        """The cap is a fact about the account, so it is decided before any scan.

        Until now the only check sat at the send boundary, after the map scan
        and (in cloud mode) after reserving a shared target: a full account
        re-scanned every ten seconds only to be refused.  Now the tick stops at
        the cap, reports it as its own state so the panel can say why, and
        rechecks on the session probe's cadence - the count cannot change in
        our view any faster than that.  Below the cap the scan runs as before.
        """

        facade, clock, directory = self._facade()
        try:
            facade.configure_resident_automation_from_habits(
                "303", self._habits()
            )
            searches: list[dict[str, object]] = []
            facade._run_mine_search_game_workflow = types.MethodType(  # noqa: SLF001
                lambda _self, _execution, body, _context: (
                    searches.append(dict(body)) or {"targets": []}
                ),
                facade,
            )
            facade._update_account_public_state(  # noqa: SLF001
                "303",
                {"roleStateJson": json.dumps(
                    {"resourcePointCurrent": 5, "resourcePointCap": 5}
                )},
            )

            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["mine"]}
            )

            self.assertEqual(result["feature"], "mine")
            self.assertEqual(result["state"], "capacity-full")
            self.assertTrue(result["success"])
            self.assertIn("5/5", result["message"])
            self.assertEqual(
                result["nextWakeAtMillis"], clock.value + 60_000,
                "rechecked on the probe cadence, not the 10s target retry",
            )
            self.assertEqual(searches, [], "no map scan while the cap holds")
            stored = json.loads(facade.account_record_json("303"))["account"]
            mine_state = json.loads(
                stored["session"]["publicState"]["residentAutomationStateJson"]
            )["mine"]
            self.assertEqual(mine_state["lastState"], "capacity-full")

            facade._update_account_public_state(  # noqa: SLF001
                "303",
                {"roleStateJson": json.dumps(
                    {"resourcePointCurrent": 4, "resourcePointCap": 5}
                )},
            )
            clock.value += 60_000
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["mine"]}
            )

            self.assertEqual(result["feature"], "mine")
            self.assertEqual(result["state"], "no-targets")
            self.assertEqual(len(searches), 1, "one slot free: the scan runs")
        finally:
            facade.close()
            directory.cleanup()

    def test_brush_preflight_ambiguity_is_durable_and_never_replayed(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            def interrupted(_self, execution, *_args, **_kwargs):
                execution.mark_request_sent({"feature": "troop-heal"})
                raise OperationUncertainError("治疗回执不明")

            facade._run_expedition_preflight = types.MethodType(  # noqa: SLF001
                interrupted, facade
            )
            with self.assertRaises(OperationUncertainError):
                facade._run_brush_execute_game_workflow(  # noqa: SLF001
                    FakeExecution(),
                    {
                        "accountRef": "303",
                        "generalIds": ["7"],
                        "target": {"id": 9, "x": 10, "y": 10},
                        "hostSettings": {"formations": []},
                    },
                    {},
                )
            stored = json.loads(facade.account_record_json("303"))["account"]
            pending = json.loads(
                stored["session"]["publicState"]["brushPendingRecoveryJson"]
            )
            self.assertEqual(pending["preDispatchMutationState"], "uncertain")
            self.assertEqual(pending["sendState"], "not-started")
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: ("00", [], []),
                facade,
            )
            facade._persist_automation_general_snapshot = (  # noqa: SLF001
                lambda *_args, **_kwargs: None
            )
            recovery = facade._run_brush_recovery_game_workflow(  # noqa: SLF001
                FakeExecution(), "303", pending, {}
            )
            self.assertEqual(recovery["state"], "blocked")
            self.assertTrue(recovery["requiresAttention"])
            self.assertIn("禁止自动重做", recovery["message"])
        finally:
            facade.close()
            directory.cleanup()

    def test_brush_known_preflight_failure_is_archived_not_left_pending(
        self,
    ) -> None:
        facade, _clock, directory = self._facade()
        try:
            def rejected(_self, execution, *_args, **_kwargs):
                execution.mark_request_sent({
                    "feature": "troop-heal",
                    "opcode": "0x1230",
                })
                raise OperationKnownFailureError(
                    "刷黄出征前将领赵云体力不足或不可确认",
                    code="EXPEDITION_ENERGY_NOT_READY",
                )

            facade._run_expedition_preflight = types.MethodType(  # noqa: SLF001
                rejected, facade
            )
            with self.assertRaises(OperationKnownFailureError):
                facade._run_brush_execute_game_workflow(  # noqa: SLF001
                    FakeExecution(),
                    {
                        "accountRef": "303",
                        "generalIds": ["7"],
                        "target": {"id": 9, "x": 10, "y": 10},
                        "hostSettings": {"formations": []},
                    },
                    {},
                )
            stored = json.loads(facade.account_record_json("303"))["account"]
            public = stored["session"]["publicState"]
            self.assertEqual(public["brushPendingRecoveryJson"], "{}")
            archived = json.loads(
                public["brushLastPreDispatchFailureJson"]
            )
            self.assertEqual(
                archived["preDispatchMutationState"], "failed"
            )
            self.assertEqual(
                archived["preDispatchErrorCode"],
                "EXPEDITION_ENERGY_NOT_READY",
            )
            self.assertFalse(archived["requiresAttention"])
            self.assertEqual(archived["sendState"], "not-started")
        finally:
            facade.close()
            directory.cleanup()

    def test_mine_preflight_ambiguity_is_durable_and_never_replayed(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            def interrupted(_self, execution, *_args, **_kwargs):
                execution.mark_request_sent({"feature": "formation"})
                raise OperationUncertainError("配兵回执不明")

            facade._run_expedition_preflight = types.MethodType(  # noqa: SLF001
                interrupted, facade
            )
            with self.assertRaises(OperationUncertainError):
                facade._run_mine_execute_game_workflow(  # noqa: SLF001
                    FakeExecution(),
                    {
                        "accountRef": "303",
                        "generalIds": ["7"],
                        "target": {
                            "id": 88,
                            "x": 10,
                            "y": 10,
                            "mineType": "SILVER",
                            "playerOccupied": False,
                        },
                        "fullLoyalty": True,
                        "hostSettings": {"formations": []},
                    },
                    {},
                )
            stored = json.loads(facade.account_record_json("303"))["account"]
            pending = json.loads(
                stored["session"]["publicState"]["minePendingGarrisonJson"]
            )
            self.assertEqual(pending["preDispatchMutationState"], "uncertain")
            self.assertEqual(pending["dispatchSendState"], "not-started")
            self.assertEqual(pending["battleId"], 0)
        finally:
            facade.close()
            directory.cleanup()

    def test_waiting_mine_garrison_releases_the_lane_to_other_features(
        self,
    ) -> None:
        """打矿 watched a march and starved everything else for hours.

        The garrison loop is 675s of marching plus 驻守/撤防/回闲, and none of
        it holds anything in flight - the reducer just re-reads 军情 every ten
        seconds.  Yet the record kept its lane claim on every tick, so on the
        real account 副本 fell 41 minutes and 刷黄 104 minutes past their own
        deadlines while 打矿 occupied 112 of the ledger's ticks to 副本's 33.
        A waiting pending workflow has to hand the lane back, and it must also
        count as served so it does not win the next contest on priority alone.
        """

        facade, clock, directory = self._facade()
        try:
            facade.configure_resident_automation_from_habits(
                "303", self._habits()
            )
            facade._update_account_public_state(  # noqa: SLF001
                "303",
                {
                    "minePendingGarrisonJson": json.dumps({
                        "battleId": 41472667,
                        "generalIds": [7],
                        "createdAtMillis": clock.value - 300_000,
                        "dispatchAtMillis": clock.value - 300_000,
                        "dispatchSendState": "accepted",
                        "preDispatchMutationState": "accepted",
                    }),
                    "residentAutomationStateJson": json.dumps({
                        "brush": {"nextWakeAtMillis": clock.value},
                        "mine": {"nextWakeAtMillis": clock.value},
                    }),
                },
            )

            def garrison_waiting(_self, _execution, _account, _pending, _ctx):
                # What mine_garrison_decision returns while the generals march.
                return {
                    "feature": "mine",
                    "state": "waiting",
                    "message": "军情状态=出征，继续等待驻守",
                    "nextWakeAtMillis": clock.value + 10_000,
                }

            facade._run_mine_garrison_game_workflow = types.MethodType(  # noqa: SLF001
                garrison_waiting, facade
            )
            configured_calls: list[dict[str, object]] = []

            def configured(_self, _execution, _account, context):
                configured_calls.append(dict(context))
                return {
                    "feature": "brush",
                    "state": "no-targets",
                    "success": True,
                    "message": "本轮没有可打的目标",
                    "nextWakeAtMillis": clock.value + 10_000,
                }

            facade._run_configured_resident_tick = types.MethodType(  # noqa: SLF001
                configured, facade
            )

            first = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {"allowedFeatures": ["mine", "brush"]},
            )
            self.assertEqual("mine", first["decidedVia"])
            self.assertEqual("waiting", first["state"])
            self.assertEqual([], configured_calls)
            pending = facade._automation_pending_record(  # noqa: SLF001
                "303", "minePendingGarrisonJson"
            )
            self.assertEqual(clock.value + 10_000, pending["nextPollAtMillis"])
            state = json.loads(
                facade._account_public_state("303")[  # noqa: SLF001
                    "residentAutomationStateJson"
                ]
            )
            self.assertEqual(
                clock.value, state["mine"]["lastServedAtMillis"]
            )

            second = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {"allowedFeatures": ["mine", "brush"]},
            )
            self.assertEqual("configured", second["decidedVia"])
            self.assertEqual(1, len(configured_calls))
            # A yielded record must also leave the configured candidate set,
            # or the very same recovery is re-entered through the other door.
            self.assertNotIn(
                "mine", configured_calls[0]["allowedFeatures"]
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_a_stopped_pending_workflow_records_that_it_needs_a_human(
        self,
    ) -> None:
        """"Stop, a human must look" has to survive the tick that decided it.

        打矿's 撤防 came back without confirming its battle id, which no amount
        of reading can settle, so the reducer refused to act - correctly.  But
        the refusal lived only in the returned result, so the next tick found
        an ordinary-looking record, re-entered the same branch and refused
        again, twice a second, holding the lane while making no progress.  The
        isolation path already knows what to do with an unresolvable send; it
        was never told.
        """

        facade, clock, directory = self._facade()
        try:
            facade.configure_resident_automation_from_habits(
                "303", self._habits()
            )
            facade._update_account_public_state(  # noqa: SLF001
                "303",
                {
                    "minePendingGarrisonJson": json.dumps({
                        "battleId": 41511996,
                        "generalIds": [7],
                        "createdAtMillis": clock.value - 300_000,
                        "dispatchAtMillis": clock.value - 300_000,
                        "dispatchSendState": "accepted",
                        "preDispatchMutationState": "accepted",
                        # No reading settles this one.
                        "recallSendState": "uncertain",
                    }),
                    "residentAutomationStateJson": json.dumps({
                        "brush": {"nextWakeAtMillis": clock.value},
                        "mine": {"nextWakeAtMillis": clock.value},
                    }),
                },
            )
            calls: list[int] = []

            def refuses(_self, _execution, _account, _pending, _ctx):
                calls.append(1)
                return {
                    "feature": "mine",
                    "state": "blocked",
                    "requiresAttention": True,
                    "message": "撤防请求曾越过发送边界但回执未确认",
                    "nextWakeAtMillis": None,
                }

            facade._run_mine_garrison_game_workflow = types.MethodType(  # noqa: SLF001
                refuses, facade
            )
            facade._run_configured_resident_tick = types.MethodType(  # noqa: SLF001
                lambda _s, _e, _a, _c: {
                    "feature": "brush",
                    "state": "no-targets",
                    "success": True,
                    "message": "本轮没有可打的目标",
                    "nextWakeAtMillis": clock.value + 10_000,
                },
                facade,
            )

            first = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {"allowedFeatures": ["mine", "brush"]},
            )
            self.assertEqual("mine", first["decidedVia"])
            self.assertTrue(
                facade._automation_pending_record(  # noqa: SLF001
                    "303", "minePendingGarrisonJson"
                )["requiresAttention"]
            )

            second = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {"allowedFeatures": ["mine", "brush"]},
            )
            # Refused once, not once per tick, and named so the operator can
            # act instead of reading the same line forever.
            self.assertEqual(1, len(calls))
            self.assertEqual("configured", second["decidedVia"])
            self.assertIn("mine", second["isolatedAttentionFeatures"])
        finally:
            facade.close()
            directory.cleanup()

    def test_a_halted_task_costs_the_others_nothing_whatever_it_is_called(
        self,
    ) -> None:
        """One task stopping must never stop the rest.

        A halt was recognised by its name: only ``blocked`` and
        ``defeat-paused`` got a retry deadline, so any other stop fell through
        to "due now" and competed on every tick.  副本 halts as
        ``clear-unconfirmed`` after three unconfirmed clears, and its dispatch
        is a settled ``accepted``, so the send-boundary probe waved it through
        too - it recomputed the same refusal twice a second while holding the
        lane.  A spin is distinguished from a multi-step round that is still
        converging by whether the ledger moved, not by what the stop is called.
        """

        facade, clock, directory = self._facade()
        try:
            facade.configure_resident_automation_from_habits(
                "303", self._habits()
            )
            facade._update_account_public_state(  # noqa: SLF001
                "303",
                {
                    "dungeonPendingRunJson": json.dumps({
                        "battleId": 7,
                        "generalIds": [7],
                        "dispatchSendState": "accepted",
                        "createdAtMillis": clock.value - 60_000,
                    }),
                    "residentAutomationStateJson": json.dumps({
                        "brush": {"nextWakeAtMillis": clock.value},
                        "mine": {"nextWakeAtMillis": clock.value},
                    }),
                },
            )
            halts = 0

            def halted(_self, _execution, _account, _pending, _ctx):
                nonlocal halts
                halts += 1
                return {
                    "feature": "dungeon",
                    "state": "clear-unconfirmed",
                    "success": False,
                    "requiresAttention": True,
                    "message": "副本目录连续3次未确认本关通关，已暂停避免重复出征",
                    "nextWakeAtMillis": None,
                }

            facade._run_dungeon_recovery_game_workflow = types.MethodType(  # noqa: SLF001
                halted, facade
            )
            configured: list[dict[str, object]] = []
            facade._run_configured_resident_tick = types.MethodType(  # noqa: SLF001
                lambda _s, _e, _a, ctx: (
                    configured.append(dict(ctx))
                    or {
                        "feature": "brush",
                        "state": "no-targets",
                        "success": True,
                        "message": "本轮没有可打的目标",
                        "nextWakeAtMillis": clock.value + 10_000,
                    }
                ),
                facade,
            )

            for _ in range(6):
                facade._run_automation_recovery_tick(  # noqa: SLF001
                    FakeExecution(),
                    "303",
                    {"allowedFeatures": ["dungeon", "brush", "mine"]},
                )

            # It stopped; it must not keep asking.  One free attempt to let a
            # round advance, then it steps aside.
            self.assertLessEqual(
                halts, 2, "a halted task must not recompute itself every tick"
            )
            self.assertGreaterEqual(
                len(configured), 4, "the lane must go to whatever else is due"
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_relogin_keeps_every_conclusion_the_last_session_reached(
        self,
    ) -> None:
        """Surviving a reconnect must not depend on being on a list.

        The carry-over was a whitelist, so a durable conclusion had to be
        remembered to survive and forgetting one was silent.
        ``generalEnergyCooldownJson`` - "this general cannot march and the
        vault has no 活血丹, pause its formation for 30 minutes" - was
        forgotten, so every reconnect released the pause, every released
        formation hit the same shortage again, and the pause was rewritten.
        The test phone's Wi-Fi cycles nightly, which makes that a loop.

        Anything this login recomputes still wins; only what it says nothing
        about is inherited.
        """

        facade, _clock, directory = self._facade()
        try:
            previous = {
                "accountRef": "303",
                "id": 303,
                "session": {
                    "accountId": 303,
                    "publicState": {
                        "generalEnergyCooldownJson": '{"7":{"untilMillis":1}}',
                        "brushLastRecoveryJson": '{"battleId":99}',
                        "mineLastGarrisonJson": '{"battleId":77}',
                        "successRecordsJson": '[{"category":"打矿"}]',
                        # Recomputed by this login - must be replaced, not kept.
                        "generalsJson": '[{"id":1,"name":"旧的"}]',
                    },
                },
            }
            snapshot = {
                "accountRef": "303",
                "selectedRole": {"roleId": 303, "roleName": "新角色"},
                "roleState": {"roleId": 303, "roleName": "新角色"},
                "area": {"areaName": "周年服352区", "serverKey": "server-352"},
                "username": "u303",
                "generals": [{"id": 1, "name": "新的"}],
            }

            record, _runtime, _secrets = facade._shared_login_record(  # noqa: SLF001
                previous, snapshot, "start"
            )
            public = record["session"]["publicState"]

            for key in (
                "generalEnergyCooldownJson",
                "brushLastRecoveryJson",
                "mineLastGarrisonJson",
                "successRecordsJson",
            ):
                with self.subTest(key=key):
                    self.assertEqual(
                        previous["session"]["publicState"][key],
                        public.get(key),
                        "a conclusion must not need a whitelist entry",
                    )
            self.assertIn("新的", public["generalsJson"])
            self.assertNotIn("旧的", public["generalsJson"])
        finally:
            facade.close()
            directory.cleanup()

    def test_a_nested_send_boundary_isolates_whichever_feature_holds_it(
        self,
    ) -> None:
        """One fact, one answer - for every feature that stores it that way.

        将领维护/内政/背包整理 keep their durable send boundary one level below
        the top of the record, so a scan of the top-level keys sees a clean
        ledger.  That fact used to be answered in two places with two different
        answers: the isolation gate knew about 将领维护 only, because it was
        patched the day 将领维护 won every tick.  内政 stores its boundary in
        exactly the same shape, so it was still let through - the same defect
        one feature over, and the same symptom: the workflow returns blocked,
        the record still looks ordinary, and the pair repeats twice a second
        while holding the lane.

        背包整理 stores its boundary the same way and answers "never": a bag
        mutation is always safe to plan again from a fresh read, and its
        ledger settles itself once the verification window passes.  Holding
        it for a human froze one real account for a day over a 山贼头巾 stack
        that 刷黄 kept refilling, with every equipment discard queued behind.
        """

        for feature, field, record in (
            (
                "general",
                "generalMaintenancePendingJson",
                {"maintenanceProgress": {
                    "heal": {"healByFief/539": {"state": "uncertain"}}
                }},
            ),
            (
                "domestic",
                "domesticPendingActionJson",
                {"progress": {"building/12": {"state": "uncertain"}}},
            ),
        ):
            with self.subTest(feature=feature):
                facade, _clock, directory = self._facade()
                try:
                    self.assertTrue(
                        facade._pending_nested_send_unsettled(  # noqa: SLF001
                            feature, record
                        ),
                        f"{feature} hides its send boundary below the top level",
                    )
                    # A settled ledger of the same shape must stay runnable.
                    self.assertFalse(
                        facade._pending_nested_send_unsettled(  # noqa: SLF001
                            feature, {}
                        )
                    )
                finally:
                    facade.close()
                    directory.cleanup()

        facade, _clock, directory = self._facade()
        try:
            for action_state in ("sending", "uncertain", "accepted", "rejected"):
                with self.subTest(feature="inventory", action_state=action_state):
                    self.assertFalse(
                        facade._pending_nested_send_unsettled(  # noqa: SLF001
                            "inventory",
                            {"actionState": action_state, "requiresAttention": True},
                        ),
                        "a bag ledger never needs a human; it settles itself",
                    )
        finally:
            facade.close()
            directory.cleanup()

    def test_process_reopen_preserves_plan_cursor_and_stopped_task_never_starts(
        self,
    ) -> None:
        directory = tempfile.TemporaryDirectory()
        clock = FixedClock()
        operation_path = str(Path(directory.name) / "operations.json")
        first = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=operation_path,
            ports=PlatformPorts(clock=clock),
        )
        try:
            first.account_record_upsert({
                "accountRef": "303",
                "id": 303,
                "enabled": True,
                "loginState": "ONLINE",
                "session": {
                    "accountId": 303,
                    "sourceMode": 1,
                    "publicState": {
                        "roleId": "303",
                        "savedTasksStarted": "true",
                        "activeResidentTaskKeys": "brushYellow,mine",
                        "generalsJson": json.dumps([{
                            "id": 7,
                            "idHex": "0000000000000007",
                            "name": "赵云",
                        }]),
                    },
                },
            })
            first.configure_resident_automation_from_habits(
                "303", self._habits()
            )
            first._update_account_public_state(  # noqa: SLF001
                "303",
                {"residentAutomationStateJson": json.dumps({
                    "mine": {
                        "cursor": 1,
                        "nextWakeAtMillis": clock.value + 60_000,
                    },
                    "brush": {"cursor": 0, "usedCount": 1},
                })},
            )
        finally:
            first.close()

        reopened = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=operation_path,
            ports=PlatformPorts(clock=clock),
        )
        try:
            record = json.loads(reopened.account_record_json("303"))["account"]
            public = record["session"]["publicState"]
            config = json.loads(public["residentAutomationConfigJson"])
            state = json.loads(public["residentAutomationStateJson"])
            self.assertTrue(config["mine"]["enabled"])
            self.assertEqual(state["mine"]["cursor"], 1)

            reopened.set_resident_automation_activation("303", False, [])
            network_calls = 0

            def forbidden(*_args, **_kwargs):
                nonlocal network_calls
                network_calls += 1
                raise AssertionError("stopped task started network work")

            reopened._run_mine_search_game_workflow = forbidden  # noqa: SLF001
            reopened._run_brush_search_game_workflow = forbidden  # noqa: SLF001
            idle = reopened._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {"allowedFeatures": ["mine", "brush"]},
            )
            self.assertEqual(idle["state"], "idle")
            self.assertEqual(network_calls, 0)

            pending = {
                "generalIds": [7],
                "createdAtMillis": clock.value - 30_000,
                "sendState": "accepted",
            }
            reopened._update_account_public_state(  # noqa: SLF001
                "303",
                {"brushPendingRecoveryJson": json.dumps(pending)},
            )
            recovered = 0

            def recovery(_self, _execution, _account, _pending, _context):
                nonlocal recovered
                recovered += 1
                return {
                    "feature": "brushYellow",
                    "state": "completed",
                    "message": "accepted action safely recovered",
                    "nextWakeAtMillis": clock.value + 1_000,
                }

            reopened._run_brush_recovery_game_workflow = types.MethodType(  # noqa: SLF001
                recovery, reopened
            )
            result = reopened._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {"allowedFeatures": ["mine", "brush"]},
            )
            self.assertEqual(result["feature"], "brushYellow")
            self.assertEqual(recovered, 1)
            self.assertEqual(network_calls, 0)
        finally:
            reopened.close()
            directory.cleanup()

    def test_session_invalid_fails_before_any_resident_request(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            facade.configure_resident_automation_from_habits(
                "303", self._habits()
            )
            record = json.loads(facade.account_record_json("303"))["account"]
            record["enabled"] = False
            record["loginState"] = "REAL_PROTOCOL_STOPPED"
            facade.account_record_upsert(record)
            submitted = facade.submit_automation_recovery_tick(
                "303",
                tick_key="stopped-session",
                request_context={"allowedFeatures": ["mine", "brush"]},
            )
            operation = self._wait_operation(
                facade, submitted["operationId"]
            )
            self.assertEqual(operation["status"], "FAILED")
            self.assertFalse(operation["requestSent"])
            self.assertIn("没有可用于网络请求", operation["error"]["message"])
        finally:
            facade.close()
            directory.cleanup()

    def test_a_pending_owned_tick_still_reports_what_it_declined(self) -> None:
        """Reporting and the wake-merge decision were entangled.

        On a tick owned by a durable pending workflow the due-set was not
        published at all - and that is precisely the tick on which a starved
        feature is invisible.  A real account sat at zero 副本 runs for 70
        hours inside this blind spot.  What the scheduler declined has to be
        stated on every tick, independently of what it decided to do about it.
        """

        facade, clock, directory = self._facade()
        try:
            facade.configure_resident_automation_from_habits(
                "303", self._habits()
            )
            facade._update_account_public_state(  # noqa: SLF001
                "303",
                {
                    "brushPendingRecoveryJson": json.dumps({
                        "generalIds": [7],
                        "createdAtMillis": clock.value - 30_000,
                        "sendState": "accepted",
                    }),
                    "residentAutomationStateJson": json.dumps({
                        "brush": {"nextWakeAtMillis": clock.value},
                        # Due 90 minutes ago and losing every tick.
                        "mine": {
                            "nextWakeAtMillis": clock.value - 90 * 60_000
                        },
                    }),
                },
            )

            def waiting(_self, _execution, _account, _pending, _context):
                return {
                    "feature": "brushYellow",
                    "state": "waiting",
                    "message": "刷黄将领尚未全部回闲",
                    "nextWakeAtMillis": clock.value + 30_000,
                }

            facade._run_brush_recovery_game_workflow = types.MethodType(  # noqa: SLF001
                waiting, facade
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {"allowedFeatures": ["mine", "brush"]},
            )

            self.assertEqual(result["decidedVia"], "brush")
            self.assertIn("mine", result["candidateFeatures"])
            self.assertEqual(
                [row["feature"] for row in result["stalledFeatures"]], ["mine"]
            )
            # Declaring a future wake is a statement that the lane is not
            # needed until then, so the scheduler records it as the record's
            # own lane deadline and the 90-minute-overdue 打矿 gets the next
            # tick.  Holding the lane while merely watching the game world is
            # what starved 副本/刷黄 for hours on the real account.
            self.assertEqual(
                facade._automation_pending_record(  # noqa: SLF001
                    "303", "brushPendingRecoveryJson"
                )["nextPollAtMillis"],
                clock.value + 30_000,
            )
            self.assertEqual(result["nextWakeAtMillis"], clock.value)
        finally:
            facade.close()
            directory.cleanup()

    def test_a_finished_pending_does_not_park_the_account_on_its_own_cadence(
        self,
    ) -> None:
        """A lane that cleared its record holds nothing, so it must not gate.

        On a real account 将领维护 finished and reported its own ten-minute
        cadence.  The host wake gate is per *account*, so that one feature's
        deadline parked 副本 and 刷黄 for ten minutes even though both were
        already due.  Whether the tick came from a pending lane says nothing
        about when the account next has work; only the outstanding records do.
        """

        facade, clock, directory = self._facade()
        try:
            facade.configure_resident_automation_from_habits(
                "303", self._habits()
            )
            facade._update_account_public_state(  # noqa: SLF001
                "303",
                {
                    "brushPendingRecoveryJson": json.dumps({
                        "generalIds": [7],
                        "createdAtMillis": clock.value - 30_000,
                        "sendState": "accepted",
                    }),
                    "residentAutomationStateJson": json.dumps({
                        "brush": {"nextWakeAtMillis": clock.value},
                        "mine": {"nextWakeAtMillis": clock.value},
                    }),
                },
            )

            def finished(self, _execution, account_ref, _pending, _context):
                # Real workflows clear their record when they complete.
                self._update_account_public_state(  # noqa: SLF001
                    account_ref, {"brushPendingRecoveryJson": "{}"}
                )
                return {
                    "feature": "brushYellow",
                    "state": "completed",
                    "message": "刷黄战后步骤完成",
                    "nextWakeAtMillis": clock.value + 600_000,
                }

            facade._run_brush_recovery_game_workflow = types.MethodType(  # noqa: SLF001
                finished, facade
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {"allowedFeatures": ["mine", "brush"]},
            )

            self.assertEqual(result["feature"], "brushYellow")
            self.assertEqual(result["state"], "completed")
            self.assertLess(
                int(result["nextWakeAtMillis"]),
                clock.value + 600_000,
                "mine was already due; the account must not sleep 10 minutes",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_pending_recovery_hands_the_lane_to_due_work_while_waiting(
        self,
    ) -> None:
        """A waiting pending workflow cannot also keep the lane.

        This used to assert the opposite: the account slept until the pending
        record's own deadline, on the reasoning that an earlier wake would
        re-select the same workflow and spin.  That was true only because a
        waiting record kept its lane claim, which is the defect this asserts
        against - 打矿 held the lane through a 13-minute garrison loop and 副本/
        刷黄/将领维护 fell hours past their deadlines.  Publishing the declared
        deadline onto the record removes the spin, so the earlier wake is now
        both safe and necessary.
        """

        facade, clock, directory = self._facade()
        try:
            facade.configure_resident_automation_from_habits(
                "303", self._habits()
            )
            facade._update_account_public_state(  # noqa: SLF001
                "303",
                {
                    "brushPendingRecoveryJson": json.dumps({
                        "generalIds": [7],
                        "createdAtMillis": clock.value - 30_000,
                        "sendState": "accepted",
                    }),
                    "residentAutomationStateJson": json.dumps({
                        "brush": {"nextWakeAtMillis": clock.value},
                        "mine": {"nextWakeAtMillis": clock.value},
                    }),
                },
            )
            expected_wake = clock.value + 30_000

            def waiting(_self, _execution, _account, _pending, _context):
                return {
                    "feature": "brushYellow",
                    "state": "waiting",
                    "message": "刷黄将领尚未全部回闲",
                    "nextWakeAtMillis": expected_wake,
                }

            facade._run_brush_recovery_game_workflow = types.MethodType(  # noqa: SLF001
                waiting, facade
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {"allowedFeatures": ["mine", "brush"]},
            )

            self.assertEqual(result["feature"], "brushYellow")
            self.assertEqual(result["state"], "waiting")
            self.assertEqual(
                facade._automation_pending_record(  # noqa: SLF001
                    "303", "brushPendingRecoveryJson"
                )["nextPollAtMillis"],
                expected_wake,
            )
            self.assertEqual(result["nextWakeAtMillis"], clock.value)
        finally:
            facade.close()
            directory.cleanup()

    def test_yielded_pending_poll_deadline_wakes_account_before_idle_work(
        self,
    ) -> None:
        """A yielded pending record is still an account wake deadline.

        A real two-account host let one account start a brush expedition and a
        dungeon battle, then parked that account for forty minutes.  Both
        pending records had near-term ``nextPollAtMillis`` values, but once
        they yielded the lane only the much later configured deadline reached
        the Android account wake gate.  The other account kept running, which
        made this look like cross-account starvation rather than a lost timer.
        """

        facade, clock, directory = self._facade()
        try:
            facade.configure_resident_automation_from_habits(
                "303", self._habits()
            )
            facade.set_resident_automation_activation(
                "303", True, ["brushYellow", "mine"]
            )
            pending_poll = clock.value + 30_000
            facade._update_account_public_state(  # noqa: SLF001
                "303",
                {
                    "brushPendingRecoveryJson": json.dumps({
                        "generalIds": [7],
                        "createdAtMillis": clock.value - 30_000,
                        "sendState": "accepted",
                        "nextPollAtMillis": pending_poll,
                    }),
                    "residentAutomationStateJson": json.dumps({
                        "brush": {"nextWakeAtMillis": clock.value},
                        "mine": {
                            "nextWakeAtMillis": clock.value + 40 * 60_000
                        },
                    }),
                },
            )

            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {"allowedFeatures": ["mine", "brush"]},
            )

            self.assertIsNone(result["feature"])
            self.assertEqual(result["state"], "idle")
            self.assertIn("brush", result["isolatedPendingFeatures"])
            self.assertEqual(result["nextWakeAtMillis"], pending_poll)
        finally:
            facade.close()
            directory.cleanup()

    def test_read_only_network_failure_schedules_retry_without_pending_mutation(
        self,
    ) -> None:
        facade, clock, directory = self._facade()
        try:
            habits = self._habits()
            habits["mine"] = {"enabled": False, "rows": []}
            facade.configure_resident_automation_from_habits("303", habits)
            facade.set_resident_automation_activation(
                "303", True, ["brushYellow"]
            )

            def offline(_self, *_args, **_kwargs):
                raise OperationKnownFailureError(
                    "网络不可用",
                    code="BRUSH_SEARCH_RESPONSE_MISSING",
                )

            facade._run_brush_search_game_workflow = types.MethodType(  # noqa: SLF001
                offline, facade
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {"allowedFeatures": ["mine", "brush"]},
            )
            self.assertEqual(result["state"], "retry")
            self.assertFalse(result["requiresAttention"])
            self.assertEqual(
                result["nextWakeAtMillis"], clock.value + 10_000
            )
            stored = json.loads(facade.account_record_json("303"))["account"]
            self.assertEqual(
                stored["session"]["publicState"].get(
                    "brushPendingRecoveryJson", "{}"
                ),
                "{}",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_brush_retry_deadline_starts_after_long_scan_failure(self) -> None:
        facade, clock, directory = self._facade()
        try:
            habits = self._habits()
            habits["mine"] = {"enabled": False, "rows": []}
            facade.configure_resident_automation_from_habits("303", habits)
            facade.set_resident_automation_activation(
                "303", True, ["brushYellow"]
            )
            failure_at = clock.value + 120_000

            def stale_target(_self, *_args, **_kwargs):
                clock.value = failure_at
                raise OperationKnownFailureError(
                    "目标不存在，不能到达。",
                    code="BRUSH_DISPATCH_REJECTED",
                )

            facade._run_configured_brush_tick = types.MethodType(  # noqa: SLF001
                stale_target, facade
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {"allowedFeatures": ["brush"]},
            )

            self.assertEqual(result["state"], "retry")
            self.assertEqual(
                result["nextWakeAtMillis"], failure_at + 10_000
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_brush_high_level_troop_rejection_keeps_original_rule_index(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            habits = self._habits()
            habits["mine"] = {"enabled": False, "rows": []}
            brush_row = habits["config"]["brush"]["rows"][0]
            brush_row.update({"idx": 2, "levels": [8], "level": 8})
            facade.configure_resident_automation_from_habits("303", habits)
            facade.set_resident_automation_activation(
                "303", True, ["brushYellow"]
            )
            facade._run_brush_search_game_workflow = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: {
                    "targets": [{
                        "id": 90,
                        "x": 10,
                        "y": 10,
                        "kind": "山贼",
                        "level": 9,
                    }]
                },
                facade,
            )

            def rejected(_self, *_args, **_kwargs):
                raise OperationKnownFailureError(
                    "出征失败！攻打9级山贼、10级山贼，每个将领至少需配1000兵力。",
                    code="BRUSH_DISPATCH_REJECTED",
                )

            facade._run_brush_execute_game_workflow = types.MethodType(  # noqa: SLF001
                rejected, facade
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {"allowedFeatures": ["brush"]}
            )

            self.assertEqual(result["state"], "retry")
            self.assertFalse(result["requiresAttention"])
            self.assertEqual(result["errorCode"], "BRUSH_DISPATCH_REJECTED")
            self.assertEqual(result["sourceRowIndex"], 2)
            self.assertEqual(
                result["message"],
                "刷黄编队3未满足每个将领配兵达到1000",
            )
            self.assertIn("每个将领至少需配1000兵力", result["serverMessage"])
            self.assertEqual(result["generalTroops"][0]["generalId"], "7")
            self.assertEqual(result["generalTroops"][0]["soldierCount"], 100)
        finally:
            facade.close()
            directory.cleanup()

    def test_allowed_feature_gate_does_not_steal_other_legacy_owner(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            facade._update_account_public_state(  # noqa: SLF001
                "303",
                {"losslessPendingBattleJson": json.dumps({
                    "generalIds": [7],
                    "dispatchSendState": "accepted",
                })},
            )
            lossless_calls = 0

            def forbidden(_self, *_args, **_kwargs):
                nonlocal lossless_calls
                lossless_calls += 1
                raise AssertionError("brush/mine tick stole lossless ownership")

            facade._run_lossless_recovery_game_workflow = types.MethodType(  # noqa: SLF001
                forbidden, facade
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "303",
                {
                    "allowedFeatures": ["mine", "brush"],
                    "configuredExecutionAllowed": False,
                },
            )
            self.assertEqual(result["state"], "idle")
            self.assertEqual(lossless_calls, 0)
        finally:
            facade.close()
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
