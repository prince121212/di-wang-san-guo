from __future__ import annotations

import json
import struct
import tempfile
import time
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core import CoreFacade  # noqa: E402
from dwpm_core.operations import (  # noqa: E402
    OperationKnownFailureError,
    OperationUncertainError,
)
from dwpm_core.ports import PlatformPorts  # noqa: E402
from dwpm_core.features.mine import build_recall_payload  # noqa: E402


class FixedClock:
    def __init__(self, value: int = 10_000_000) -> None:
        self.value = int(value)

    def now_millis(self) -> int:
        return self.value


class FakeExecution:
    operation_id = "op_automation_fixture"

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.progress: list[dict] = []

    def mark_request_sent(self, metadata=None) -> None:
        self.sent.append(dict(metadata or {}))

    def publish_progress(self, progress: int, details=None) -> None:
        self.progress.append({"progress": progress, **dict(details or {})})

    def raise_if_cancelled(self) -> None:
        return None

    def wait(self, _seconds: float) -> None:
        return None


def _live_account(facade: CoreFacade, account_ref: str = "202") -> None:
    facade.account_record_upsert({
        "accountRef": account_ref,
        "id": int(account_ref),
        "username": "automation-fixture",
        "serverName": "fixture",
        "enabled": True,
        "loginState": "ONLINE",
        "session": {
            "accountId": int(account_ref),
            "sourceMode": 1,
            "publicState": {
                "roleId": account_ref,
                "lastValidatedAt": "10000000",
                "generalsJson": "[]",
                "militarySnapshotJson": '{"actions":[]}',
            },
        },
    })


class SharedAutomationRecoveryWorkflowTests(unittest.TestCase):
    def _facade(self):
        clock = FixedClock()
        ports = PlatformPorts(clock=clock)
        directory = tempfile.TemporaryDirectory()
        facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(Path(directory.name) / "operations.json"),
            ports=ports,
        )
        _live_account(facade)
        return facade, clock, directory

    @staticmethod
    def _general(general_id: int, status: int, fief_id: int = 500) -> dict:
        status_text = "闲" if status == 0 else "战"
        return {
            "id": general_id,
            "name": f"将领{general_id}",
            "status": status,
            "statusText": status_text,
            "displayStatus": status_text,
            "fiefId": fief_id,
            "placeID": fief_id,
            "energyReliable": True,
            "tili": 300,
            "tiliLimit": 300,
            "soldierTypeCode": 3,
            "soldierCount": 100,
            "currentSoldierCount": 100,
        }

    def test_known_failed_brush_preflight_without_dispatch_is_reconciled(
        self,
    ) -> None:
        facade, clock, directory = self._facade()
        try:
            pending = {
                "generalIds": [1, 2],
                "formationId": 1,
                "targetId": 99,
                "targetX": 86,
                "targetY": 29,
                "createdAtMillis": clock.value - 60_000,
                "preDispatchMutationState": "failed",
                "preDispatchError": "刷黄出征前将领1体力不足或不可确认",
                "preDispatchRequestMetadata": {
                    "feature": "troop-heal",
                    "opcode": "0x1230",
                },
                "requiresAttention": True,
                "sendState": "not-started",
            }
            facade._update_account_public_state(  # noqa: SLF001
                "202",
                {
                    "brushPendingRecoveryJson": json.dumps(
                        pending, ensure_ascii=False
                    )
                },
            )

            def must_not_query_or_mutate(*_args, **_kwargs):
                raise AssertionError(
                    "definitive no-dispatch ledger must resolve locally"
                )

            facade._fresh_formation_state = must_not_query_or_mutate  # noqa: SLF001
            result = facade._run_brush_recovery_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", pending, {}
            )

            self.assertEqual(result["state"], "retry")
            self.assertFalse(result["requiresAttention"])
            self.assertEqual(
                result["nextWakeAtMillis"], clock.value + 10_000
            )
            self.assertIn("正式出征未成功发送", result["message"])
            stored = json.loads(facade.account_record_json("202"))["account"]
            public = stored["session"]["publicState"]
            self.assertEqual(public["brushPendingRecoveryJson"], "{}")
            archived = json.loads(
                public["brushLastPreDispatchFailureJson"]
            )
            self.assertEqual(
                archived["recoveryResolution"],
                "known-pre-dispatch-failure",
            )
            self.assertFalse(archived["requiresAttention"])
        finally:
            facade.close()
            directory.cleanup()

    def test_uncertain_brush_heal_is_not_replayed_and_next_attempt_skips_it(
        self,
    ) -> None:
        facade, clock, directory = self._facade()
        try:
            pending = {
                "generalIds": [1, 2],
                "createdAtMillis": clock.value - 60_000,
                "preDispatchMutationState": "uncertain",
                "preDispatchRequestMetadata": {
                    "feature": "troop-heal",
                    "opcode": "0x1230",
                },
                "sendState": "not-started",
                "requiresAttention": True,
            }
            facade._update_account_public_state(  # noqa: SLF001
                "202",
                {
                    "brushPendingRecoveryJson": json.dumps(
                        pending, ensure_ascii=False
                    )
                },
            )
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: (
                    "00",
                    [self._general(1, 0), self._general(2, 0)],
                    [],
                ),
                facade,
            )
            facade._persist_automation_general_snapshot = (  # noqa: SLF001
                lambda *_args, **_kwargs: None
            )

            result = facade._run_brush_recovery_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", pending, {}
            )

            self.assertEqual(result["state"], "retry")
            self.assertFalse(result["requiresAttention"])
            self.assertIn("禁止重发治疗", result["message"])
            stored = json.loads(facade.account_record_json("202"))["account"]
            public = stored["session"]["publicState"]
            self.assertEqual(public["brushPendingRecoveryJson"], "{}")
            archived = json.loads(
                public["brushLastPreDispatchFailureJson"]
            )
            self.assertEqual(
                archived["recoveryResolution"],
                "uncertain-heal-not-replayed-skip-next",
            )
            state = json.loads(public["residentAutomationStateJson"])
            self.assertTrue(state["brush"]["skipHealOnce"])
        finally:
            facade.close()
            directory.cleanup()

    def test_brush_recovery_maintains_then_clears_pending(self) -> None:
        facade, clock, directory = self._facade()
        try:
            pending = {
                "generalIds": [1, 2],
                "generalFacts": [
                    {"id": 1, "fiefId": 500},
                    {"id": 2, "fiefId": 500},
                ],
                "createdAtMillis": clock.value - 60_000,
                "sendState": "accepted",
                "battleId": 77,
                "healWounded": True,
                "foodToCopper": False,
                "copperFloorWan": 1,
                "deleteMailForSpeed": True,
                "formations": [
                    {
                        "generalId": "1",
                        "generalIds": ["1"],
                        "soldierType": "轻骑兵",
                        "soldierCount": 100,
                    },
                    {
                        "generalId": "2",
                        "generalIds": ["2"],
                        "soldierType": "轻骑兵",
                        "soldierCount": 100,
                    },
                ],
            }
            facade._update_account_public_state(
                "202",
                {"brushPendingRecoveryJson": json.dumps(pending, ensure_ascii=False)},
            )
            current = [
                self._general(1, 6),
                self._general(2, 6),
            ]
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda self, *_args, **_kwargs: ("00", list(current), []),
                facade,
            )
            facade._persist_automation_general_snapshot = lambda *args, **kwargs: None  # noqa: SLF001
            calls: list[tuple[str, int]] = []

            def heal(self, execution, body, _context):
                calls.append(("heal", int(body["fiefId"])))
                execution.mark_request_sent({"feature": "fixture-heal"})
                return {"ok": True, "result": {"success": True, "message": "治疗成功"}}

            def assign(self, execution, body, _context):
                calls.append(("assign", int(body["generalId"])))
                execution.mark_request_sent({"feature": "fixture-assign"})
                return {"ok": True, "result": {"success": True, "message": "配兵成功"}}

            def delete_mail(self, execution, _account_ref, _context):
                calls.append(("mail", 0))
                execution.mark_request_sent({"feature": "fixture-delete-mail"})
                return {"ok": True, "result": {"success": True, "message": "邮件清理完成"}}

            facade._run_troop_heal_game_workflow = types.MethodType(heal, facade)  # noqa: SLF001
            facade._run_troop_assign_game_workflow = types.MethodType(assign, facade)  # noqa: SLF001
            facade._run_brush_delete_mail_game_workflow = types.MethodType(delete_mail, facade)  # noqa: SLF001

            first = facade._run_brush_recovery_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", pending, {}
            )
            self.assertEqual(first["state"], "waiting")
            stored = json.loads(facade.account_record_json("202"))["account"]
            waiting = json.loads(
                stored["session"]["publicState"]["brushPendingRecoveryJson"]
            )
            self.assertTrue(waiting["sawBusy"])

            current[:] = [self._general(1, 0), self._general(2, 0)]
            second = facade._run_brush_recovery_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", waiting, {}
            )
            self.assertEqual(second["state"], "completed")
            self.assertEqual(
                calls,
                [("heal", 500), ("assign", 1), ("assign", 2), ("mail", 0)],
            )
            stored = json.loads(facade.account_record_json("202"))["account"]
            public = stored["session"]["publicState"]
            self.assertEqual(public["brushPendingRecoveryJson"], "{}")
            self.assertIn("brushLastRecoveryJson", public)
        finally:
            facade.close()
            directory.cleanup()

    def test_recovery_tick_submission_is_durable_and_immediate(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            submitted = facade.submit_automation_recovery_tick(
                "202",
                tick_key="fixture-idle",
            )
            self.assertTrue(submitted["accepted"])
            self.assertEqual(submitted["status"], "QUEUED")
            for _ in range(200):
                operation = facade.operation_status(
                    submitted["operationId"]
                )["operation"]
                if operation["status"] not in {"QUEUED", "RUNNING"}:
                    break
                time.sleep(0.005)
            else:
                self.fail("automation recovery operation did not complete")
            self.assertEqual(operation["status"], "SUCCEEDED", operation)
            self.assertFalse(operation["requestSent"])
            self.assertEqual(operation["result"]["state"], "idle")
        finally:
            facade.close()
            directory.cleanup()

    def test_blocked_brush_pending_is_isolated_from_other_configured_work(
        self,
    ) -> None:
        facade, clock, directory = self._facade()
        try:
            # Only a mutation whose outcome is genuinely unknown justifies
            # holding a feature back for a human.  "accepted" is a settled fact
            # and must stay recoverable; "uncertain" is the real ambiguity.
            pending = {
                "generalIds": [1],
                "sendState": "uncertain",
                "requiresAttention": True,
                "lastError": "刷黄出征回执未确认",
                "isolatedAtMillis": clock.value - 1_000,
            }
            facade._update_account_public_state(  # noqa: SLF001
                "202",
                {
                    "brushPendingRecoveryJson": json.dumps(
                        pending,
                        ensure_ascii=False,
                    )
                },
            )
            configured_calls = 0
            configured_allowed = []

            def configured(self, _execution, _account_ref, context):
                nonlocal configured_calls
                configured_calls += 1
                configured_allowed.extend(context.get("allowedFeatures") or [])
                return {
                    "feature": "inventory",
                    "state": "completed",
                    "success": True,
                    "message": "背包整理完成",
                    "nextWakeAtMillis": clock.value + 60_000,
                }

            facade._run_configured_resident_tick = types.MethodType(  # noqa: SLF001
                configured,
                facade,
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "202",
                {
                    "allowedFeatures": ["brush", "inventory"],
                    "configuredExecutionAllowed": True,
                },
            )

            self.assertEqual(result["feature"], "inventory")
            self.assertEqual(result["state"], "completed")
            self.assertEqual(configured_calls, 1)
            self.assertIn("inventory", configured_allowed)
            self.assertNotIn("brush", configured_allowed)
            stored = json.loads(facade.account_record_json("202"))["account"]
            still_pending = json.loads(
                stored["session"]["publicState"]["brushPendingRecoveryJson"]
            )
            self.assertTrue(still_pending["requiresAttention"])
        finally:
            facade.close()
            directory.cleanup()

    def test_a_settled_pending_recovers_despite_a_stale_attention_flag(
        self,
    ) -> None:
        """副本 sat isolated for days on an attention flag nothing re-evaluated.

        ``requiresAttention`` is a conclusion an earlier run drew, and
        conclusions expire.  Once the send boundary is a *known* result the
        workflow only needs to re-read state, so it must be allowed to run
        again and clear the flag itself.
        """

        facade, clock, directory = self._facade()
        try:
            pending = {
                "generalIds": [1],
                "sendState": "accepted",
                "requiresAttention": True,
                "lastError": "刷黄战后步骤需要处理",
                "isolatedAtMillis": clock.value - 1_000,
            }
            facade._update_account_public_state(  # noqa: SLF001
                "202",
                {
                    "brushPendingRecoveryJson": json.dumps(
                        pending,
                        ensure_ascii=False,
                    )
                },
            )
            attempted = []

            def recover(self, _execution, _account_ref, value, _context):
                attempted.append(dict(value))
                return {
                    "feature": "brush",
                    "state": "completed",
                    "success": True,
                    "message": "刷黄战后步骤完成",
                }

            facade._run_brush_recovery_game_workflow = types.MethodType(  # noqa: SLF001
                recover,
                facade,
            )

            def configured(self, *_args, **_kwargs):
                self.fail("configured work must not pre-empt a ready pending")

            facade._run_configured_resident_tick = types.MethodType(  # noqa: SLF001
                configured,
                facade,
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "202",
                {
                    "allowedFeatures": ["brush", "inventory"],
                    "configuredExecutionAllowed": True,
                },
            )

            self.assertEqual(result["feature"], "brush")
            self.assertEqual(result["state"], "completed")
            self.assertEqual(len(attempted), 1)
            self.assertTrue(attempted[0]["requiresAttention"])
        finally:
            facade.close()
            directory.cleanup()

    def test_isolated_uncertain_dispatch_reenters_and_settles_itself(self):
        """刷黄 01:31 的真实形状：sendState=sending + requiresAttention。

        The gate used to strand exactly this record forever - the probe saw
        an ambiguous formal send and refused re-entry, so the adjudicator
        added in this change could never run.  With an accepted preflight
        the workflow only reads state, so the pending must come back in and
        settle itself once the grace has passed.
        """

        facade, clock, directory = self._facade()
        try:
            pending = self._uncertain_dispatch_pending(
                clock,
                createdAtMillis=clock.value - 31 * 60_000,
                sendingAtMillis=clock.value - 31 * 60_000,
                blockedAtMillis=clock.value - 30 * 60_000,
                isolatedAtMillis=clock.value - 30 * 60_000,
            )
            facade._update_account_public_state(  # noqa: SLF001
                "202",
                {"brushPendingRecoveryJson": json.dumps(pending, ensure_ascii=False)},
            )
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: (
                    "00",
                    [self._general(1, 0), self._general(2, 0)],
                    [],
                ),
                facade,
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "202",
                {
                    "allowedFeatures": ["brush", "inventory"],
                    "configuredExecutionAllowed": True,
                },
            )
            self.assertEqual(result["feature"], "brushYellow", result)
            self.assertEqual(result["state"], "reconciled", result)
            stored = json.loads(facade.account_record_json("202"))["account"]
            public = stored["session"]["publicState"]
            self.assertEqual(public["brushPendingRecoveryJson"], "{}")
        finally:
            facade.close()
            directory.cleanup()

    def test_pending_known_failure_returns_feature_scoped_result(self) -> None:
        facade, clock, directory = self._facade()
        try:
            pending = {
                "generalIds": [1],
                "sendState": "accepted",
            }
            facade._update_account_public_state(  # noqa: SLF001
                "202",
                {"brushPendingRecoveryJson": json.dumps(pending)},
            )

            def fail_brush(self, *_args, **_kwargs):
                raise OperationKnownFailureError(
                    "刷黄战后步骤 healByFief/500 不可重放",
                    code="BRUSH_RECOVERY_STEP_REQUIRES_REVIEW",
                )

            facade._run_brush_recovery_game_workflow = types.MethodType(  # noqa: SLF001
                fail_brush,
                facade,
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "202",
                {
                    "allowedFeatures": ["brush"],
                    "configuredExecutionAllowed": False,
                },
            )

            self.assertEqual(result["feature"], "brushYellow")
            self.assertEqual(result["state"], "blocked")
            self.assertTrue(result["requiresAttention"])
            self.assertEqual(
                result["errorCode"],
                "BRUSH_RECOVERY_STEP_REQUIRES_REVIEW",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_pending_energy_item_shortage_yields_and_retries_later(self) -> None:
        facade, clock, directory = self._facade()
        try:
            pending = {
                "generalIds": [1],
                "maintenanceProgress": {},
            }
            facade._update_account_public_state(  # noqa: SLF001
                "202",
                {
                    "generalMaintenancePendingJson": json.dumps(
                        pending,
                        ensure_ascii=False,
                    )
                },
            )

            calls = 0

            def fail_general(self, *_args, **_kwargs):
                nonlocal calls
                calls += 1
                raise OperationKnownFailureError(
                    "将领维护检查到智步6体力不足，但宝库没有活血丹",
                    code="EXPEDITION_ENERGY_ITEM_UNAVAILABLE",
                )

            facade._run_configured_general_tick = types.MethodType(  # noqa: SLF001
                fail_general,
                facade,
            )
            configured_features = []

            def run_brush(self, _execution, _account_ref, context):
                configured_features.extend(context.get("allowedFeatures") or [])
                return {
                    "feature": "brush",
                    "state": "completed",
                    "success": True,
                    "message": "刷黄已让步运行",
                    "nextWakeAtMillis": clock.value + 60_000,
                }

            facade._run_configured_resident_tick = types.MethodType(  # noqa: SLF001
                run_brush,
                facade,
            )
            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "202",
                {
                    "allowedFeatures": ["general", "brush"],
                },
            )

            self.assertEqual(result["feature"], "general")
            self.assertEqual(result["state"], "retry")
            self.assertFalse(result["requiresAttention"])
            self.assertIsNotNone(result["nextWakeAtMillis"])
            self.assertEqual(calls, 1)

            stored = json.loads(facade.account_record_json("202"))["account"]
            saved = json.loads(
                stored["session"]["publicState"][
                    "generalMaintenancePendingJson"
                ]
            )
            self.assertFalse(saved["requiresAttention"])
            self.assertGreater(saved["isolatedUntilMillis"], clock.value)

            # The same pending record must not be re-entered before its retry
            # deadline, otherwise the fix would only change the log label.
            second = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(),
                "202",
                {
                    "allowedFeatures": ["general", "brush"],
                },
            )
            self.assertEqual(calls, 1)
            self.assertEqual(second["feature"], "brush")
            self.assertNotIn("general", configured_features)
        finally:
            facade.close()
            directory.cleanup()

    def test_process_reopen_preserves_brush_send_boundary(self) -> None:
        clock = FixedClock()
        directory = tempfile.TemporaryDirectory()
        operation_path = str(Path(directory.name) / "operations.json")
        first = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=operation_path,
            ports=PlatformPorts(clock=clock),
        )
        try:
            _live_account(first)
            first._update_account_public_state(  # noqa: SLF001
                "202",
                {
                    "brushPendingRecoveryJson": json.dumps({
                        "generalIds": [1],
                        "generalFacts": [{"id": 1, "fiefId": 500}],
                        "createdAtMillis": clock.value - 600_000,
                        "sendState": "accepted",
                        "sawBusy": True,
                        "healWounded": True,
                        "formations": [{
                            "generalId": "1",
                            "generalIds": ["1"],
                            "soldierType": "轻骑兵",
                            "soldierCount": 100,
                        }],
                        "recoveryProgress": {
                            "healByFief": {
                                "500": {
                                    "state": "sending",
                                    "sentAtMillis": clock.value - 1_000,
                                }
                            }
                        },
                    }, ensure_ascii=False)
                },
            )
        finally:
            first.close()

        reopened = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=operation_path,
            ports=PlatformPorts(clock=clock),
        )
        try:
            stored = json.loads(reopened.account_record_json("202"))["account"]
            pending = json.loads(
                stored["session"]["publicState"]["brushPendingRecoveryJson"]
            )
            rows = [self._general(1, 0)]
            reopened._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda self, *_args, **_kwargs: ("00", list(rows), []),
                reopened,
            )
            reopened._persist_automation_general_snapshot = lambda *args, **kwargs: None  # noqa: SLF001
            heal_calls = 0
            preinfo_calls = 0

            def should_not_repeat(self, *_args, **_kwargs):
                nonlocal heal_calls
                heal_calls += 1
                raise AssertionError("process recovery repeated an uncertain heal")

            def latest_no_wounded(self, *_args, **_kwargs):
                nonlocal preinfo_calls
                preinfo_calls += 1
                return {
                    "success": True,
                    "fiefId": 500,
                    "soldierType": -1,
                    "copperCost": 0,
                    "goldCost": 0,
                }

            reopened._run_troop_heal_game_workflow = types.MethodType(  # noqa: SLF001
                should_not_repeat,
                reopened,
            )
            reopened._read_brush_heal_preinfo = types.MethodType(  # noqa: SLF001
                latest_no_wounded,
                reopened,
            )
            reopened._run_troop_assign_game_workflow = types.MethodType(  # noqa: SLF001
                lambda self, execution, _body, _context: (
                    execution.mark_request_sent({"feature": "fixture-assign"})
                    or {
                        "ok": True,
                        "result": {"success": True, "message": "配兵成功"},
                    }
                ),
                reopened,
            )
            result = reopened._run_brush_recovery_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", pending, {}
            )
            self.assertEqual(result["state"], "completed")
            self.assertEqual(heal_calls, 0)
            self.assertEqual(preinfo_calls, 1)
            stored = json.loads(reopened.account_record_json("202"))["account"]
            public = stored["session"]["publicState"]
            self.assertEqual(public["brushPendingRecoveryJson"], "{}")
            archived = json.loads(public["brushLastRecoveryJson"])
            step = archived["recoveryProgress"]["healByFief"]["500"]
            self.assertEqual(step["state"], "archived-uncertain")
            self.assertFalse(step["reconciliation"]["oldRequestReplayed"])
            self.assertEqual(
                step["reconciliation"]["resolution"],
                "latest-estimate-no-wounded",
            )
        finally:
            reopened.close()
            directory.cleanup()

    def test_brush_recovery_does_not_repeat_uncertain_heal(self) -> None:
        facade, clock, directory = self._facade()
        try:
            pending = {
                "generalIds": [1],
                "generalFacts": [{"id": 1, "fiefId": 500}],
                "createdAtMillis": clock.value - 600_000,
                "sendState": "accepted",
                "sawBusy": True,
                "healWounded": True,
                "formations": [{
                    "generalId": "1",
                    "generalIds": ["1"],
                    "soldierType": "轻骑兵",
                    "soldierCount": 100,
                }],
            }
            facade._update_account_public_state(
                "202",
                {"brushPendingRecoveryJson": json.dumps(pending, ensure_ascii=False)},
            )
            rows = [self._general(1, 0)]
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda self, *_args, **_kwargs: ("00", list(rows), []),
                facade,
            )
            facade._persist_automation_general_snapshot = lambda *args, **kwargs: None  # noqa: SLF001
            call_count = 0

            def uncertain_heal(self, execution, _body, _context):
                nonlocal call_count
                call_count += 1
                execution.mark_request_sent({"feature": "fixture-heal"})
                raise OperationUncertainError("fixture socket closed after heal")

            facade._run_troop_heal_game_workflow = types.MethodType(uncertain_heal, facade)  # noqa: SLF001
            with self.assertRaises(OperationUncertainError):
                facade._run_brush_recovery_game_workflow(  # noqa: SLF001
                    FakeExecution(), "202", pending, {}
                )
            stored = json.loads(facade.account_record_json("202"))["account"]
            uncertain = json.loads(
                stored["session"]["publicState"]["brushPendingRecoveryJson"]
            )
            self.assertEqual(
                uncertain["recoveryProgress"]["healByFief"]["500"]["state"],
                "uncertain",
            )
            preinfo_calls = 0

            def latest_wounded(self, *_args, **_kwargs):
                nonlocal preinfo_calls
                preinfo_calls += 1
                return {
                    "success": True,
                    "fiefId": 500,
                    "soldierType": -1,
                    "copperCost": 1,
                    "goldCost": 80,
                }

            facade._read_brush_heal_preinfo = types.MethodType(  # noqa: SLF001
                latest_wounded,
                facade,
            )

            def fresh_maintenance(self, execution, _body, _context):
                nonlocal call_count
                call_count += 1
                execution.mark_request_sent({"feature": "fixture-fresh-heal"})
                return {
                    "ok": True,
                    "result": {"success": True, "message": "最新伤兵已治疗"},
                }

            facade._run_troop_heal_game_workflow = types.MethodType(  # noqa: SLF001
                fresh_maintenance,
                facade,
            )
            facade._run_troop_assign_game_workflow = types.MethodType(  # noqa: SLF001
                lambda self, execution, _body, _context: (
                    execution.mark_request_sent({"feature": "fixture-assign"})
                    or {
                        "ok": True,
                        "result": {"success": True, "message": "配兵成功"},
                    }
                ),
                facade,
            )
            completed = facade._run_brush_recovery_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", uncertain, {}
            )
            self.assertEqual(completed["state"], "completed")
            self.assertEqual(preinfo_calls, 1)
            # One old uncertain attempt plus one distinct latest-state repair.
            self.assertEqual(call_count, 2)
            stored = json.loads(facade.account_record_json("202"))["account"]
            archived = json.loads(
                stored["session"]["publicState"]["brushLastRecoveryJson"]
            )
            reconciliation = archived["recoveryProgress"]["healByFief"][
                "500"
            ]["reconciliation"]
            self.assertFalse(reconciliation["oldRequestReplayed"])
            self.assertEqual(
                reconciliation["maintenanceAttempt"]["state"],
                "completed",
            )
        finally:
            facade.close()
            directory.cleanup()

    def _uncertain_dispatch_pending(self, clock, **overrides):
        pending = {
            "generalIds": [1, 2],
            "formationId": 1,
            "targetId": 99,
            "targetX": 86,
            "targetY": 29,
            "createdAtMillis": clock.value - 60_000,
            "sendingAtMillis": clock.value - 60_000,
            "preDispatchMutationState": "accepted",
            "preDispatchRequestMetadata": {
                "feature": "troop-heal",
                "opcode": "0x1230",
            },
            "dispatchRequestMetadata": {
                "feature": "brush-execute",
                "opcode": "0x1520",
                "phase": "prepare",
            },
            "sendState": "sending",
            "requiresAttention": True,
        }
        pending.update(overrides)
        return pending

    def _run_recovery_with_generals(self, facade, pending, generals):
        facade._update_account_public_state(  # noqa: SLF001
            "202",
            {"brushPendingRecoveryJson": json.dumps(pending, ensure_ascii=False)},
        )
        facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
            lambda _self, *_args, **_kwargs: ("00", generals, []),
            facade,
        )
        return facade._run_brush_recovery_game_workflow(  # noqa: SLF001
            FakeExecution(), "202", pending, {}
        )

    def test_uncertain_dispatch_waits_out_the_grace_before_settling(self):
        facade, clock, directory = self._facade()
        try:
            pending = self._uncertain_dispatch_pending(clock)
            result = self._run_recovery_with_generals(
                facade,
                pending,
                [
                    self._general(1, 0),
                    self._general(2, 0),
                ],
            )
            self.assertEqual(result["state"], "waiting")
            self.assertFalse(result["requiresAttention"])
            # 宽限期 30 分钟，从发送时刻起算，而不是从观察时刻起算。
            self.assertEqual(
                result["nextWakeAtMillis"],
                pending["sendingAtMillis"] + 1_800_000,
            )
            self.assertIn("自动结清", result["message"])
            stored = json.loads(facade.account_record_json("202"))["account"]
            public = stored["session"]["publicState"]
            kept = json.loads(public["brushPendingRecoveryJson"])
            self.assertEqual(kept["lastDecision"], "wait-auto-settle-grace")
            self.assertFalse(kept["requiresAttention"])
        finally:
            facade.close()
            directory.cleanup()

    def test_aged_uncertain_dispatch_with_all_generals_idle_auto_settles(
        self,
    ):
        facade, clock, directory = self._facade()
        try:
            pending = self._uncertain_dispatch_pending(
                clock,
                createdAtMillis=clock.value - 31 * 60_000,
                sendingAtMillis=clock.value - 31 * 60_000,
            )
            result = self._run_recovery_with_generals(
                facade,
                pending,
                [
                    self._general(1, 0),
                    self._general(2, 0),
                ],
            )
            self.assertEqual(result["state"], "reconciled")
            self.assertTrue(result["success"])
            self.assertFalse(result["requiresAttention"])
            self.assertEqual(
                result["nextWakeAtMillis"], clock.value + 10_000
            )
            stored = json.loads(facade.account_record_json("202"))["account"]
            public = stored["session"]["publicState"]
            self.assertEqual(public["brushPendingRecoveryJson"], "{}")
            archived = json.loads(public["brushLastReconciliationJson"])
            self.assertEqual(
                archived["reconciliationReason"],
                "auto-aged-uncertain-dispatch-and-all-idle",
            )
            self.assertFalse(archived["requiresAttention"])
            self.assertEqual(
                archived["reconciliationEvidence"]["idleGeneralIds"], [1, 2]
            )
            state = json.loads(public["residentAutomationStateJson"])
            self.assertTrue(state["brush"]["skipHealOnce"])
            self.assertEqual(
                state["brush"]["skipHealReason"],
                "auto-reconciled-uncertain-dispatch",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_aged_uncertain_dispatch_with_busy_general_keeps_watching(self):
        facade, clock, directory = self._facade()
        try:
            pending = self._uncertain_dispatch_pending(
                clock,
                createdAtMillis=clock.value - 31 * 60_000,
                sendingAtMillis=clock.value - 31 * 60_000,
            )
            result = self._run_recovery_with_generals(
                facade,
                pending,
                [
                    self._general(1, 6),  # 仍在行军/战斗
                    self._general(2, 0),
                ],
            )
            self.assertEqual(result["state"], "waiting")
            self.assertFalse(result["requiresAttention"])
            self.assertIn("等待回闲后自动结清", result["message"])
            self.assertEqual(result["nextWakeAtMillis"], clock.value + 30_000)
            stored = json.loads(facade.account_record_json("202"))["account"]
            public = stored["session"]["publicState"]
            kept = json.loads(public["brushPendingRecoveryJson"])
            self.assertEqual(kept["lastDecision"], "wait-auto-settle-busy")
            self.assertFalse(kept["requiresAttention"])
        finally:
            facade.close()
            directory.cleanup()

    def test_uncertain_dispatch_with_missing_general_still_blocks(self):
        facade, clock, directory = self._facade()
        try:
            pending = self._uncertain_dispatch_pending(
                clock,
                createdAtMillis=clock.value - 31 * 60_000,
                sendingAtMillis=clock.value - 31 * 60_000,
            )
            result = self._run_recovery_with_generals(
                facade,
                pending,
                [self._general(1, 0)],  # 将领2不在最新状态里，无法裁决
            )
            self.assertEqual(result["state"], "blocked")
            self.assertTrue(result["requiresAttention"])
            self.assertIn("禁止自动重做", result["message"])
            stored = json.loads(facade.account_record_json("202"))["account"]
            public = stored["session"]["publicState"]
            self.assertNotEqual(public["brushPendingRecoveryJson"], "{}")
        finally:
            facade.close()
            directory.cleanup()

    def test_auto_settle_does_not_apply_to_uncertain_heal(self):
        facade, clock, directory = self._facade()
        try:
            pending = self._uncertain_dispatch_pending(
                clock,
                createdAtMillis=clock.value - 31 * 60_000,
                sendingAtMillis=clock.value - 31 * 60_000,
                preDispatchMutationState="sending",
            )
            result = self._run_recovery_with_generals(
                facade,
                pending,
                [
                    self._general(1, 0),
                    self._general(2, 0),
                ],
            )
            self.assertEqual(result["state"], "blocked")
            self.assertTrue(result["requiresAttention"])
        finally:
            facade.close()
            directory.cleanup()

    def test_legacy_brush_recovery_backfills_saved_formations_before_mutation(
        self,
    ) -> None:
        facade, clock, directory = self._facade()
        try:
            pending = {
                "generalIds": [1, 2],
                "generalFacts": [
                    {"id": 1, "fiefId": 500},
                    {"id": 2, "fiefId": 500},
                ],
                "createdAtMillis": clock.value - 600_000,
                "sendState": "accepted",
                "sawBusy": True,
                "healWounded": True,
                "recoveryProgress": {
                    "healByFief": {
                        "500": {
                            "state": "completed",
                            "message": "治疗已完成",
                        }
                    }
                },
            }
            facade._update_account_public_state(  # noqa: SLF001
                "202",
                {
                    "brushPendingRecoveryJson": json.dumps(
                        pending,
                        ensure_ascii=False,
                    ),
                    "residentAutomationConfigJson": json.dumps(
                        {
                            "updatedAtMillis": clock.value - 30_000,
                            "formations": [
                                {
                                    "generalId": "1",
                                    "generalIds": ["1"],
                                    "soldierType": "强弩兵",
                                    "soldierCount": 899,
                                },
                                {
                                    "generalId": "2",
                                    "generalIds": ["2"],
                                    "soldierType": "重步兵",
                                    "soldierCount": 599,
                                },
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            )
            rows = [self._general(1, 0), self._general(2, 0)]
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda self, *_args, **_kwargs: ("00", list(rows), []),
                facade,
            )
            facade._persist_automation_general_snapshot = (  # noqa: SLF001
                lambda *args, **kwargs: None
            )
            heal_calls = 0
            assignments: list[tuple[int, str, int]] = []
            test_case = self

            def heal(self, *_args, **_kwargs):
                nonlocal heal_calls
                heal_calls += 1
                raise AssertionError("已完成治疗不应重复执行")

            def assign(self, execution, body, _context):
                stored = json.loads(self.account_record_json("202"))["account"]
                frozen = json.loads(
                    stored["session"]["publicState"][
                        "brushPendingRecoveryJson"
                    ]
                )
                test_case.assertEqual(
                    frozen["formationRuleSource"],
                    "resident-config-legacy-backfill",
                )
                test_case.assertEqual(len(frozen["formations"]), 2)
                test_case.assertEqual(len(frozen["formationRuleHash"]), 64)
                execution.mark_request_sent({"feature": "fixture-assign"})
                assignments.append((
                    int(body["generalId"]),
                    str(body["soldierType"]),
                    int(body["soldierCount"]),
                ))
                return {
                    "ok": True,
                    "result": {"success": True, "message": "配兵成功"},
                }

            facade._run_troop_heal_game_workflow = types.MethodType(  # noqa: SLF001
                heal,
                facade,
            )
            facade._run_troop_assign_game_workflow = types.MethodType(  # noqa: SLF001
                assign,
                facade,
            )

            result = facade._run_brush_recovery_game_workflow(  # noqa: SLF001
                FakeExecution(),
                "202",
                pending,
                {},
            )

            self.assertEqual(result["state"], "completed")
            self.assertEqual(heal_calls, 0)
            self.assertEqual(
                assignments,
                [(1, "强弩兵", 899), (2, "重步兵", 599)],
            )
            stored = json.loads(facade.account_record_json("202"))["account"]
            self.assertEqual(
                stored["session"]["publicState"]["brushPendingRecoveryJson"],
                "{}",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_legacy_brush_recovery_fails_before_mutation_when_rule_is_missing(
        self,
    ) -> None:
        facade, clock, directory = self._facade()
        try:
            pending = {
                "generalIds": [1, 2],
                "generalFacts": [
                    {"id": 1, "fiefId": 500},
                    {"id": 2, "fiefId": 500},
                ],
                "createdAtMillis": clock.value - 600_000,
                "sendState": "accepted",
                "sawBusy": True,
                "healWounded": True,
            }
            facade._update_account_public_state(  # noqa: SLF001
                "202",
                {
                    "brushPendingRecoveryJson": json.dumps(pending),
                    "residentAutomationConfigJson": json.dumps({
                        "formations": [{
                            "generalId": "1",
                            "soldierType": "强弩兵",
                            "soldierCount": 899,
                        }]
                    }, ensure_ascii=False),
                },
            )
            rows = [self._general(1, 0), self._general(2, 0)]
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda self, *_args, **_kwargs: (
                    "00",
                    list(rows),
                    [],
                ),
                facade,
            )
            facade._persist_automation_general_snapshot = (  # noqa: SLF001
                lambda *args, **kwargs: None
            )
            mutation_calls = 0

            def should_not_mutate(self, *_args, **_kwargs):
                nonlocal mutation_calls
                mutation_calls += 1
                raise AssertionError("配兵规则未完整时不得发包")

            facade._run_troop_heal_game_workflow = types.MethodType(  # noqa: SLF001
                should_not_mutate,
                facade,
            )
            facade._run_troop_assign_game_workflow = types.MethodType(  # noqa: SLF001
                should_not_mutate,
                facade,
            )

            with self.assertRaises(OperationKnownFailureError) as raised:
                facade._run_brush_recovery_game_workflow(  # noqa: SLF001
                    FakeExecution(),
                    "202",
                    pending,
                    {},
                )

            self.assertEqual(
                raised.exception.code,
                "BRUSH_RECOVERY_FORMATION_MISSING",
            )
            self.assertEqual(mutation_calls, 0)
        finally:
            facade.close()
            directory.cleanup()

    def test_legacy_brush_recovery_rejects_ambiguous_or_invalid_rules(
        self,
    ) -> None:
        cases = {
            "duplicate": [
                {
                    "generalId": "1",
                    "soldierType": "强弩兵",
                    "soldierCount": 899,
                },
                {
                    "generalIds": ["1"],
                    "soldierType": "重步兵",
                    "soldierCount": 599,
                },
            ],
            "invalid-soldier": [{
                "generalId": "1",
                "soldierType": "不存在的兵种",
                "soldierCount": 899,
            }],
            "invalid-count": [{
                "generalId": "1",
                "soldierType": "强弩兵",
                "soldierCount": 0,
            }],
        }
        for name, formations in cases.items():
            with self.subTest(name=name):
                facade, clock, directory = self._facade()
                try:
                    pending = {
                        "generalIds": [1],
                        "generalFacts": [{"id": 1, "fiefId": 500}],
                        "createdAtMillis": clock.value - 600_000,
                        "sendState": "accepted",
                        "sawBusy": True,
                        "healWounded": True,
                    }
                    facade._update_account_public_state(  # noqa: SLF001
                        "202",
                        {
                            "brushPendingRecoveryJson": json.dumps(pending),
                            "residentAutomationConfigJson": json.dumps(
                                {"formations": formations},
                                ensure_ascii=False,
                            ),
                        },
                    )
                    rows = [self._general(1, 0)]
                    facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                        lambda self, *_args, **_kwargs: (
                            "00",
                            list(rows),
                            [],
                        ),
                        facade,
                    )
                    facade._persist_automation_general_snapshot = (  # noqa: SLF001
                        lambda *args, **kwargs: None
                    )
                    mutation_calls = 0

                    def should_not_mutate(self, *_args, **_kwargs):
                        nonlocal mutation_calls
                        mutation_calls += 1
                        raise AssertionError("无效配兵规则不得发包")

                    facade._run_troop_heal_game_workflow = types.MethodType(  # noqa: SLF001
                        should_not_mutate,
                        facade,
                    )
                    facade._run_troop_assign_game_workflow = types.MethodType(  # noqa: SLF001
                        should_not_mutate,
                        facade,
                    )

                    with self.assertRaises(OperationKnownFailureError):
                        facade._run_brush_recovery_game_workflow(  # noqa: SLF001
                            FakeExecution(),
                            "202",
                            pending,
                            {},
                        )
                    self.assertEqual(mutation_calls, 0)
                finally:
                    facade.close()
                    directory.cleanup()

    def test_mine_recall_then_idle_clears_exact_battle(self) -> None:
        facade, clock, directory = self._facade()
        try:
            pending = {
                "battleId": 123,
                "mineId": 7,
                "generalIds": [1],
                "x": 18,
                "y": 22,
                "dispatchAtMillis": clock.value - 20_000,
                "withdrawDefense": True,
                "recallRequestedAtMillis": 0,
            }
            busy_general = self._general(1, 6, 500)
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda self, *_args, **_kwargs: (
                    "00",
                    [dict(busy_general)],
                    [],
                ),
                facade,
            )
            facade._persist_automation_general_snapshot = lambda *args, **kwargs: None  # noqa: SLF001
            snapshot = {
                "actions": [{
                    "battleId": 123,
                    "state": "驻守",
                    "x": 18,
                    "y": 22,
                    "generalIds": [1],
                }]
            }
            facade._refresh_military_snapshot_game = types.MethodType(  # noqa: SLF001
                lambda self, *_args, **_kwargs: dict(snapshot),
                facade,
            )
            calls: list[tuple[int, bytes]] = []

            def command(self, _account, opcode, payload, _phase, _context, *, mutation_sent):
                stored_before_transport = json.loads(
                    self.account_record_json("202")
                )["account"]
                pending_before_transport = json.loads(
                    stored_before_transport["session"]["publicState"][
                        "minePendingGarrisonJson"
                    ]
                )
                if pending_before_transport.get("recallSendState") != "sending":
                    raise AssertionError("recall send boundary was not persisted")
                calls.append((opcode, bytes(payload)))
                return {
                    "requestOpcode": opcode,
                    "httpCode": 200,
                    "httpOk": True,
                    "packets": [{
                        "opcode": 0x8526,
                        "payload": bytes.fromhex("000000000000007b"),
                    }],
                }

            facade._execute_host_game_command = types.MethodType(command, facade)  # noqa: SLF001
            result = facade._run_mine_garrison_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", pending, {}
            )
            self.assertEqual(result["state"], "waiting-return")
            self.assertEqual(calls, [(0x1526, build_recall_payload(123))])
            stored = json.loads(facade.account_record_json("202"))["account"]
            accepted = json.loads(
                stored["session"]["publicState"]["minePendingGarrisonJson"]
            )
            self.assertEqual(accepted["recallSendState"], "accepted")
            self.assertGreater(accepted["recallRequestedAtMillis"], 0)

            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda self, *_args, **_kwargs: (
                    "00",
                    [{**busy_general, "status": 0, "statusText": "闲", "displayStatus": "闲"}],
                    [],
                ),
                facade,
            )
            snapshot["actions"] = []
            completed = facade._run_mine_garrison_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", accepted, {}
            )
            self.assertEqual(completed["state"], "completed")
            stored = json.loads(facade.account_record_json("202"))["account"]
            self.assertEqual(
                stored["session"]["publicState"]["minePendingGarrisonJson"],
                "{}",
            )
            # Getting the generals home is the half that frees them for the
            # next round, and it used to produce no record at all.
            self.assertTrue(completed["recallCompleted"])
            self.assertEqual("recalled", completed["occupationOutcome"])
            self.assertEqual(
                "占领成功，已撤回编队全部将领", completed["message"]
            )
            recorded = facade._append_resident_success_record(  # noqa: SLF001
                "202", completed
            )
            self.assertEqual("打矿", recorded["category"])
            self.assertEqual(
                "全部将领 已撤回（battleId=123）",
                recorded["message"],
                "the recall must reach the record page on its own key",
            )
            self.assertEqual("mine:recall:123", recorded["dedupeKey"])
        finally:
            facade.close()
            directory.cleanup()

    def test_a_lost_mine_round_is_reported_as_a_failure_not_a_success(
        self,
    ) -> None:
        """占领失败 is rare, and the only 打矿 outcome needing attention.

        A lost round looks like a won one at the end - the generals are home
        either way - so the verdict is taken from the 返回 seen while it ran.
        It is narrated as a failure rather than filed as a success, because
        that is what puts it on the 角色-提示 page.
        """

        facade, clock, directory = self._facade()
        try:
            general = self._general(1, 6, 500)
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda self, *_a, **_k: ("00", [dict(general)], []),
                facade,
            )
            facade._persist_automation_general_snapshot = (  # noqa: SLF001
                lambda *args, **kwargs: None
            )
            snapshot = {
                "actions": [{
                    "battleId": 321,
                    "state": "返回",
                    "x": 18,
                    "y": 22,
                    "generalIds": [1],
                }]
            }
            facade._refresh_military_snapshot_game = types.MethodType(  # noqa: SLF001
                lambda self, *_a, **_k: dict(snapshot),
                facade,
            )
            pending = {
                "battleId": 321,
                "generalIds": [1],
                "x": 18,
                "y": 22,
                "sourceRowIndex": 0,
                "target": {"name": "1级镔铁矿", "x": 18, "y": 22},
                "dispatchAtMillis": clock.value - 20_000,
                "dispatchSendState": "accepted",
                "preDispatchMutationState": "accepted",
                "withdrawDefense": True,
                "recallRequestedAtMillis": 0,
            }

            returning = facade._run_mine_garrison_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", pending, {}
            )
            self.assertEqual("waiting", returning["state"])
            stored = json.loads(facade.account_record_json("202"))["account"]
            observed = json.loads(
                stored["session"]["publicState"]["minePendingGarrisonJson"]
            )
            self.assertGreater(observed["returnObservedAtMillis"], 0)

            # The battle leaves 军情 and the general comes home.
            snapshot["actions"] = []
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda self, *_a, **_k: (
                    "00",
                    [{
                        **general,
                        "status": 0,
                        "statusText": "闲",
                        "displayStatus": "闲",
                    }],
                    [],
                ),
                facade,
            )
            clock.value += 200_000
            completed = facade._run_mine_garrison_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", observed, {}
            )

            self.assertEqual("completed", completed["state"])
            self.assertEqual("failed", completed["occupationOutcome"])
            self.assertFalse(completed["recallCompleted"])
            self.assertFalse(completed["success"])
            self.assertIsNone(
                facade._append_resident_success_record(  # noqa: SLF001
                    "202", completed
                ),
                "a lost round is not a success record",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_a_preview_target_gone_closes_the_ledger_and_rescans(self) -> None:
        """The server answering the preview with foreign coordinates is a
        known conclusion - the mine was taken or despawned - not an
        unconfirmed operation.  The formal dispatch is never sent, so the
        record closes and the scheduler looks for another target instead of
        isolating the feature for a human."""
        facade, clock, directory = self._facade()
        try:
            general = self._general(1, 0)
            facade._run_expedition_preflight = types.MethodType(  # noqa: SLF001
                lambda self, *_a, **_k: (
                    [{**general, "idHex": "0000000000000001"}],
                    {"sent": True},
                ),
                facade,
            )
            facade._persist_automation_general_snapshot = (  # noqa: SLF001
                lambda *args, **kwargs: None
            )
            gone_preview = struct.pack(">iqqBHH", 0, 0, 0, 0, 0xFFFF, 0xFFFF)

            def command_fact(
                self, _execution, _account, opcode, _payload, _phase, _context,
                *, mutation_sent,
            ):
                return {
                    "requestOpcode": opcode,
                    "httpCode": 200,
                    "httpOk": True,
                    "packets": [{
                        "opcode": 0x8520,
                        "payload": gone_preview,
                    }],
                }

            facade._daily_command_fact = types.MethodType(command_fact, facade)  # noqa: SLF001
            with self.assertRaises(OperationKnownFailureError) as raised:
                facade._run_mine_execute_game_workflow(  # noqa: SLF001
                    FakeExecution(),
                    {
                        "accountRef": "202",
                        "generalIds": [1],
                        "target": {
                            "id": 187324,
                            "mineType": "二级牧场",
                            "x": 71,
                            "y": 30,
                        },
                    },
                    {},
                )
            self.assertEqual(
                "MINE_PREVIEW_TARGET_MISMATCH", raised.exception.code
            )
            self.assertIn("已失效", str(raised.exception))
            self.assertIn("重新寻找目标", str(raised.exception))
            stored = json.loads(facade.account_record_json("202"))["account"]
            public = stored["session"]["publicState"]
            self.assertEqual("{}", public["minePendingGarrisonJson"])
            archived = json.loads(public["mineLastPreDispatchFailureJson"])
            self.assertFalse(archived["requiresAttention"])
            self.assertEqual(
                "rejected-before-dispatch", archived["dispatchSendState"]
            )
            self.assertEqual(
                "MINE_PREVIEW_TARGET_MISMATCH", archived["dispatchErrorCode"]
            )
            # The raw preview is the only evidence of what the server actually
            # said; the incident that motivated this change had to be diagnosed
            # without it because older builds never persisted it.
            self.assertEqual(gone_preview.hex(), archived["preview"]["rawHex"])
        finally:
            facade.close()
            directory.cleanup()

    def test_a_legacy_target_gone_ledger_settles_without_a_human(self) -> None:
        """Records written by older builds kept the mismatch active with
        requiresAttention and isolated 打矿 for hours.  Every outcome on such
        a record is known - the troop assignment was accepted, the preview
        answered, the formal dispatch was never sent - so recovery closes it
        and hands the feature back to the configured path."""
        facade, clock, directory = self._facade()
        try:
            pending = {
                # The exact shape account 1608601 carried on 2026-09-15.
                "battleId": 0,
                "mineId": 187324,
                "generalIds": [1],
                "x": 71,
                "y": 30,
                "targetName": "二级牧场",
                "target": {"id": 187324, "mineType": "二级牧场", "x": 71, "y": 30},
                "createdAtMillis": clock.value - 14_400_000,
                "preDispatchMutationState": "accepted",
                "preDispatchRequestMetadata": {
                    "feature": "troop-assign",
                    "opcode": "0x1226",
                },
                "dispatchSendState": "rejected-before-dispatch",
                "dispatchError": "预出征坐标与目标不一致",
                "requiresAttention": True,
            }
            facade._update_account_public_state(  # noqa: SLF001
                "202",
                {"minePendingGarrisonJson": json.dumps(pending, ensure_ascii=False)},
            )
            idle_general = self._general(1, 0)
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda self, *_a, **_k: ("00", [idle_general], []),
                facade,
            )
            facade._persist_automation_general_snapshot = (  # noqa: SLF001
                lambda *args, **kwargs: None
            )
            facade._refresh_military_snapshot_game = types.MethodType(  # noqa: SLF001
                lambda self, *_a, **_k: {"actions": []},
                facade,
            )

            result = facade._run_mine_garrison_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", pending, {}
            )

            self.assertEqual("retry", result["state"])
            self.assertFalse(result["requiresAttention"])
            self.assertEqual(
                "MINE_PREVIEW_TARGET_MISMATCH", result["errorCode"]
            )
            stored = json.loads(facade.account_record_json("202"))["account"]
            public = stored["session"]["publicState"]
            self.assertEqual("{}", public["minePendingGarrisonJson"])
            archived = json.loads(public["mineLastPreDispatchFailureJson"])
            self.assertFalse(archived["requiresAttention"])
            self.assertEqual(
                "target-gone-before-dispatch", archived["recoveryResolution"]
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_mine_recall_missing_receipt_is_uncertain_and_not_replayed(self) -> None:
        facade, clock, directory = self._facade()
        try:
            pending = {
                "battleId": 123,
                "generalIds": [1],
                "x": 18,
                "y": 22,
                "dispatchAtMillis": clock.value - 20_000,
                "withdrawDefense": True,
                "recallRequestedAtMillis": 0,
            }
            busy_general = {
                **self._general(1, 2),
                "statusText": "防",
                "displayStatus": "防",
            }
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda self, *_args, **_kwargs: ("00", [dict(busy_general)], []),
                facade,
            )
            facade._persist_automation_general_snapshot = lambda *args, **kwargs: None  # noqa: SLF001
            facade._refresh_military_snapshot_game = types.MethodType(  # noqa: SLF001
                lambda self, *_args, **_kwargs: {
                    "actions": [{
                        "battleId": 123,
                        "state": "驻守",
                        "x": 18,
                        "y": 22,
                        "generalIds": [1],
                    }]
                },
                facade,
            )
            calls = 0

            def command(self, _account, opcode, _payload, _phase, _context, *, mutation_sent):
                nonlocal calls
                calls += 1
                return {
                    "requestOpcode": opcode,
                    "httpCode": 200,
                    "httpOk": True,
                    "packets": [],
                }

            facade._execute_host_game_command = types.MethodType(command, facade)  # noqa: SLF001
            with self.assertRaises(OperationUncertainError):
                facade._run_mine_garrison_game_workflow(  # noqa: SLF001
                    FakeExecution(), "202", pending, {}
                )
            stored = json.loads(facade.account_record_json("202"))["account"]
            uncertain = json.loads(
                stored["session"]["publicState"]["minePendingGarrisonJson"]
            )
            self.assertEqual(uncertain["recallSendState"], "uncertain")

            # The generals are still holding the point, so the withdrawal
            # demonstrably has not landed yet - wait for them, never re-send.
            waiting = facade._run_mine_garrison_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", uncertain, {}
            )
            self.assertEqual(waiting["state"], "waiting")
            self.assertIn("等待将领离开驻防", waiting["message"])

            # Still garrisoned well past the grace period: now it is a human's
            # problem, and still not a re-send.
            clock.value += 10 * 60_000
            blocked = facade._run_mine_garrison_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", uncertain, {}
            )
            self.assertEqual(blocked["state"], "blocked")
            self.assertEqual(calls, 1)
        finally:
            facade.close()
            directory.cleanup()

    def test_a_recall_is_judged_by_the_generals_not_by_the_receipt(
        self,
    ) -> None:
        """The receipt to a 撤防 does not identify itself; the generals do.

        A real account sent 41604347 and got 41605271 back - the receipt
        carries a whole 军情 snapshot whose 【返回】 event reports a different
        id - so every single round stopped on the mismatch while the generals
        had already left the mine.  An exact match still confirms, but its
        absence proves nothing: the request named one exact battle, so nothing
        else can have been withdrawn, and a general only ever leaves 防 because
        a withdrawal landed.  The receipt is kept either way, so the next
        mismatch can be diagnosed instead of re-guessed.
        """

        facade, clock, directory = self._facade()
        try:
            pending = {
                "battleId": 123,
                "generalIds": [1],
                "x": 18,
                "y": 22,
                "dispatchAtMillis": clock.value - 20_000,
                "withdrawDefense": True,
                "recallRequestedAtMillis": 0,
            }
            holding = {
                **self._general(1, 2),
                "statusText": "防",
                "displayStatus": "防",
            }
            state = {"general": holding}
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda self, *_a, **_k: ("00", [dict(state["general"])], []),
                facade,
            )
            facade._persist_automation_general_snapshot = (  # noqa: SLF001
                lambda *args, **kwargs: None
            )
            facade._refresh_military_snapshot_game = types.MethodType(  # noqa: SLF001
                lambda self, *_a, **_k: {
                    "actions": [{
                        "battleId": 123, "state": "驻守", "x": 18, "y": 22,
                        "generalIds": [1],
                    }]
                },
                facade,
            )
            # The server answered about a different battle - on the real
            # account a 刷黄 formation was marching home at the same moment.
            other = struct.pack(">q", 999)

            facade._execute_host_game_command = types.MethodType(  # noqa: SLF001
                lambda self, _a, opcode, _p, _ph, _c, *, mutation_sent: {
                    "requestOpcode": opcode,
                    "httpCode": 200,
                    "httpOk": True,
                    "packets": [{"opcode": 0x8526, "payload": other}],
                },
                facade,
            )
            sent = facade._run_mine_garrison_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", pending, {}
            )
            self.assertEqual("waiting-return", sent["state"])

            stored = json.loads(facade.account_record_json("202"))["account"]
            held = json.loads(
                stored["session"]["publicState"]["minePendingGarrisonJson"]
            )
            self.assertEqual("sent-unconfirmed", held["recallSendState"])
            self.assertEqual(123, held["recallExpectedBattleId"])
            self.assertEqual(999, held["recallRejectedReceipt"]["battleId"])
            self.assertEqual(
                other.hex(),
                held["recallRejectedReceipt"]["rawHex"],
                "the next mismatch must be diagnosable from the ledger",
            )

            # The generals leave 防 - that, and only that, settles it.
            state["general"] = {
                **holding,
                "status": 0,
                "statusText": "闲",
                "displayStatus": "闲",
            }
            completed = facade._run_mine_garrison_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", held, {}
            )
            self.assertEqual("completed", completed["state"])
            self.assertEqual("recalled", completed["occupationOutcome"])
            self.assertTrue(completed["recallCompleted"])
        finally:
            facade.close()
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
