from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core import CoreFacade  # noqa: E402
from dwpm_core.facade import AMBIGUOUS_SEND_STATES, FORMAL_SEND_STATE_KEYS
from dwpm_core.ports import PlatformPorts  # noqa: E402

FACADE = ROOT / "shared_core" / "python" / "dwpm_core" / "facade.py"

SEND_STATE_KEYS = FORMAL_SEND_STATE_KEYS


def recoverable(record: Dict[str, Any]) -> bool:
    """The recovery policy, evaluated over the shipped constants.

    The facade's probe is a closure, so this re-applies it rather than calling
    it - but it reads the *same* two constants the probe reads, so the policy
    cannot drift out from under the test.  An earlier version copied the key
    list into the test, and the copy silently kept asserting a rule the probe
    no longer had.
    """

    return not any(
        str(record.get(key) or "") in AMBIGUOUS_SEND_STATES
        for key in SEND_STATE_KEYS
    )


class RecoveryPolicyTests(unittest.TestCase):
    """`requiresAttention` must never outrank the durable send-boundary facts.

    A preflight that sent no prepare, dispatch or chest request left a real
    account's 副本 isolated from *both* the pending path and the configured
    scheduling path for four days, while the generals it needed were idle and
    at full energy the whole time.  The cause was that recoverability was
    decided from a list of error codes, so any code not on the list isolated
    the feature permanently and silently.
    """

    def test_only_an_unknown_outcome_needs_a_human(self) -> None:
        self.assertEqual(AMBIGUOUS_SEND_STATES, frozenset({"sending", "uncertain"}))

    def test_a_mutation_in_flight_is_not_rechecked_underneath_itself(self) -> None:
        for key in SEND_STATE_KEYS:
            for state in sorted(AMBIGUOUS_SEND_STATES):
                with self.subTest(key=key, state=state):
                    self.assertFalse(recoverable({key: state}))

    def test_every_settled_outcome_stays_recoverable(self) -> None:
        # These are *known* results, so re-reading state is safe: nothing a
        # human could decide is still open.
        for state in ("not-sent", "rejected", "accepted", "", None):
            for key in SEND_STATE_KEYS:
                with self.subTest(key=key, state=state):
                    self.assertTrue(recoverable({key: state}))

    def test_recoverability_never_consults_the_error_code(self) -> None:
        """将领维护 stayed isolated on 宝库没有活血丹 long after the item was bought."""

        record = {
            "sendState": "not-sent",
            "lastErrorCode": "EXPEDITION_ENERGY_ITEM_UNAVAILABLE",
            "lastError": "宝库没有活血丹",
            "requiresAttention": True,
        }
        self.assertTrue(recoverable(record))

        source = FACADE.read_text(encoding="utf-8")
        probe = source[
            source.index("def safe_read_only_recovery_probe(") :
            source.index("def pending_ready(")
        ]
        # The old allowlist must be gone: enumerating recoverable codes makes
        # every unlisted code fail closed into permanent, invisible isolation.
        self.assertNotIn("EXPEDITION_ENERGY_ITEM_UNAVAILABLE", probe)
        self.assertNotIn("宝库没有活血丹", probe.split('"""')[-1])


class IsolationVisibilityTests(unittest.TestCase):
    def test_isolated_features_are_reported_on_every_tick(self) -> None:
        """Isolation used to surface only when *everything* was isolated.

        While any other feature keeps running the account looks healthy, so an
        isolated feature stays invisible exactly when it is easiest to miss.
        """

        text = FACADE.read_text(encoding="utf-8")
        tail = text[text.index('"decidedVia": selected_pending_feature') - 2000:]
        self.assertIn("isolatedPendingFeatures", tail)
        self.assertIn("if isolated_pending_features:", tail)


class StalledAccountRecordTests(unittest.TestCase):
    """Replays the exact durable records taken off two stalled devices."""

    def test_the_preflight_that_sent_nothing_recovers(self) -> None:
        self.assertTrue(
            recoverable({
                "preDispatchMutationState": "failed",
                "preDispatchErrorCode": "EXPEDITION_ENERGY_NOT_READY",
                "prepareSendState": "not-sent",
                "dispatchSendState": "not-sent",
                "chestSendState": "not-sent",
                "requiresAttention": True,
            })
        )

    def test_a_dispatch_the_server_confirmed_recovers(self) -> None:
        """The 8-minute pause that expired 副本's battle tracking.

        The dispatch was ``accepted`` - a known fact, not an open question -
        so the account can simply re-read the battle's outcome.
        """

        self.assertTrue(
            recoverable({
                "prepareSendState": "accepted",
                "dispatchSendState": "accepted",
                "chestSendState": "not-sent",
                "lastError": "副本战斗跟踪超过8分钟",
                "requiresAttention": True,
            })
        )

    def test_a_dispatch_with_an_unknown_outcome_stays_isolated(self) -> None:
        self.assertFalse(
            recoverable({
                "preDispatchMutationState": "failed",
                "prepareSendState": "accepted",
                "dispatchSendState": "uncertain",
                "chestSendState": "not-sent",
                "requiresAttention": True,
            })
        )

    def test_an_interrupted_preflight_reaches_the_workflow_that_settles_it(
        self,
    ) -> None:
        """A gate above a resolver can only ever block.

        An app update interrupted 副本's troop heal, leaving the mutation at
        ``sending``.  Isolating on that kept the account out of the very
        workflow that knows how to settle it by observation, so the feature
        stalled indefinitely while everything else kept running.  Reading state
        is safe; only *replaying* is not, and that call belongs inside the
        workflow, next to the evidence.
        """

        self.assertNotIn("preDispatchMutationState", FORMAL_SEND_STATE_KEYS)
        for state in sorted(AMBIGUOUS_SEND_STATES):
            with self.subTest(state=state):
                self.assertTrue(
                    recoverable({
                        "preDispatchMutationState": state,
                        "preDispatchMutationMetadata": {
                            "feature": "troop-heal"
                        },
                        "prepareSendState": "not-sent",
                        "dispatchSendState": "not-sent",
                        "chestSendState": "not-sent",
                        "requiresAttention": True,
                    })
                )


class NestedGeneralIsolationTests(unittest.TestCase):
    """A nested general step must not monopolize the account scheduler."""

    class _Clock:
        value = 100_000_000

        def now_millis(self) -> int:
            return self.value

    class _Execution:
        operation_id = "nested-general-isolation"

        def mark_request_sent(self, _metadata=None) -> None:
            return None

        def publish_progress(self, _progress: int, _details=None) -> None:
            return None

        def raise_if_cancelled(self) -> None:
            return None

        def wait(self, _seconds: float) -> None:
            return None

    def test_uncertain_nested_heal_isolated_while_brush_remains_schedulable(
        self,
    ) -> None:
        clock = self._Clock()
        directory = tempfile.TemporaryDirectory()
        facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(Path(directory.name) / "operations.json"),
            ports=PlatformPorts(clock=clock),
        )
        try:
            config = {
                "common": {
                    "autoStart": True,
                    "dailyLimit": 500,
                    "brush": {
                        "rules": [{"enabled": True, "generalIds": ["1"]}]
                    },
                },
                "dungeon": {
                    "enabled": True,
                    "settings": {"dailyTimes": 999},
                    "rows": [{"enabled": True, "generalIds": ["1"]}],
                },
                "general": {"enabled": True},
            }
            pending = {
                "schemaVersion": 1,
                "requiresAttention": True,
                "maintenanceProgress": {
                    "healByFief": {
                        "539": {
                            "state": "uncertain",
                            "message": "治疗请求回执未确认",
                        }
                    }
                },
            }
            facade.account_record_upsert({
                "accountRef": "176",
                "id": 176,
                "enabled": True,
                "loginState": "ONLINE",
                "session": {
                    "accountId": 176,
                    "publicState": {
                        "roleId": "176",
                        "savedTasksStarted": "true",
                        "activeResidentTaskKeys": (
                            "brushYellow,dungeon,general"
                        ),
                        "residentAutomationConfigJson": json.dumps(config),
                        "residentAutomationStateJson": json.dumps({
                            "brush": {},
                            "dungeon": {},
                            "general": {},
                        }),
                        "generalMaintenancePendingJson": json.dumps(pending),
                    },
                },
            })
            configured_contexts: list[dict[str, Any]] = []

            def configured(self, _execution, _account_ref, context):
                configured_contexts.append(dict(context))
                return {
                    "feature": "brush",
                    "state": "completed",
                    "success": True,
                    "message": "刷黄已执行",
                    "nextWakeAtMillis": clock.value + 1_000,
                }

            def general_must_not_run(self, *_args, **_kwargs):
                raise AssertionError(
                    "nested uncertain general maintenance monopolized the lane"
                )

            facade._run_configured_resident_tick = types.MethodType(  # noqa: SLF001
                configured,
                facade,
            )
            facade._run_configured_general_tick = types.MethodType(  # noqa: SLF001
                general_must_not_run,
                facade,
            )

            result = facade._run_automation_recovery_tick(  # noqa: SLF001
                self._Execution(),
                "176",
                {
                    "allowedFeatures": ["brush", "dungeon", "general"],
                    "configuredExecutionAllowed": True,
                },
            )

            self.assertEqual(result["feature"], "brush")
            self.assertEqual(result["state"], "completed")
            self.assertIn("general", result["isolatedPendingFeatures"])
            self.assertIn("general", result["isolatedAttentionFeatures"])
            self.assertNotIn("general", configured_contexts[0]["allowedFeatures"])
            stored = json.loads(facade.account_record_json("176"))["account"]
            still_pending = json.loads(
                stored["session"]["publicState"][
                    "generalMaintenancePendingJson"
                ]
            )
            self.assertEqual(
                still_pending["maintenanceProgress"]["healByFief"]["539"][
                    "state"
                ],
                "uncertain",
            )
        finally:
            facade.close()
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
