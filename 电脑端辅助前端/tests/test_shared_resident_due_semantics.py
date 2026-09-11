from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core.automation import (
    BLOCKED_RETRY_MILLIS,
    pre_dispatch_outstanding,
    ambiguous_preflight_reconciliation,
    STALL_REPORT_MILLIS,
    UNRECOGNIZED_BLOCK_RETRY_MILLIS,
    STARVATION_THRESHOLD_MILLIS,
    overdue_candidates,
    resident_due_decision,
)


NOW = 1_800_000_000_000

# Matches the shipped contract order: 无损 > 打矿 > 副本 > 刷黄.
PRIORITIES = {
    "lossless": 400,
    "mine": 300,
    "dungeon": 200,
    "brushYellow": 150,
    "raid": 125,
}

ALL_KEYS = {"lossless", "mine", "dungeon", "brushYellow", "raid"}


def configs(*, brush: bool = False, dungeon: bool = False) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if brush:
        out["common"] = {
            "autoStart": True,
            "startHour": 0,
            "dailyLimit": 500,
            "brush": {"rules": [{"enabled": True}]},
        }
    if dungeon:
        out["dungeon"] = {"enabled": True, "rows": [{"enabled": True}]}
    return out


def decide(cfg: Dict[str, Any], state: Dict[str, Any], now: int = NOW):
    return resident_due_decision(
        cfg,
        state,
        now_millis=now,
        saved_tasks_started=True,
        active_keys=ALL_KEYS,
        priorities=PRIORITIES,
    )


class ResidentDueSemanticsTests(unittest.TestCase):
    """`nextWakeAtMillis = None` used to mean two contradictory things.

    The shared workflows return it from a blocked branch to mean "stop, a human
    must look".  The scheduler read the same value as "due right now", so a
    blocked feature competed every tick, lost on priority, and was never
    selected again - silently.  A real account had 副本 stuck like this for 70
    hours while its general had long since become available.
    """

    def test_never_run_feature_is_still_due_immediately(self) -> None:
        result = decide(configs(dungeon=True), {})

        self.assertEqual(result["feature"], "dungeon")
        self.assertEqual(result["reason"], "configured-feature-due")

    def test_recoverable_block_waits_out_a_backoff_from_when_it_blocked(self) -> None:
        state = {
            "dungeon": {
                "lastState": "blocked",
                "lastErrorCode": "EXPEDITION_ENERGY_NOT_READY",
                "blockedAtMillis": NOW - 60_000,
                "nextWakeAtMillis": None,
            }
        }

        result = decide(configs(dungeon=True), state)

        self.assertIsNone(result["feature"])
        self.assertEqual(result["reason"], "configured-features-waiting")
        self.assertEqual(
            result["nextWakeAtMillis"], NOW - 60_000 + BLOCKED_RETRY_MILLIS
        )

    def test_retry_deadline_is_a_fixed_instant_not_a_receding_target(self) -> None:
        """Anchored on the block, not on the read.

        The previous attempt derived the deadline from ``now`` and stored it,
        which made correctness depend on the caller persisting state.  One
        caller does not, so the deadline was recomputed from a later ``now``
        every tick and receded exactly as fast as the clock.
        """

        blocked_at = NOW - 60_000
        state: Dict[str, Any] = {
            "dungeon": {
                "lastState": "blocked",
                "lastErrorCode": "EXPEDITION_ENERGY_NOT_READY",
                "blockedAtMillis": blocked_at,
                "nextWakeAtMillis": None,
            }
        }
        expected = blocked_at + BLOCKED_RETRY_MILLIS

        for offset in (0, 60_000, 120_000):
            result = decide(configs(dungeon=True), state, now=NOW + offset)
            self.assertEqual(result["nextWakeAtMillis"], expected)

        arrived = decide(configs(dungeon=True), state, now=expected + 1)
        self.assertEqual(arrived["feature"], "dungeon")

    def test_deciding_never_mutates_the_state_it_was_given(self) -> None:
        """The module contract is that these reducers perform no I/O.

        A reducer that writes is only correct if every caller persists, and one
        of the two callers does not.
        """

        feature_state = {
            "lastState": "blocked",
            "lastErrorCode": "EXPEDITION_ENERGY_NOT_READY",
            "blockedAtMillis": NOW - 60_000,
            "nextWakeAtMillis": None,
        }
        before = dict(feature_state)

        decide(configs(dungeon=True), {"dungeon": feature_state})

        self.assertEqual(feature_state, before)

    def test_a_long_stuck_legacy_block_retries_immediately(self) -> None:
        """State written before blockedAtMillis existed must self-heal.

        A real account sat blocked for 70 hours on a cause that had resolved
        within minutes; making it wait out one more fresh backoff would be the
        wrong answer.
        """

        state = {
            "dungeon": {
                "lastState": "blocked",
                "lastErrorCode": "EXPEDITION_ENERGY_NOT_READY",
                "nextWakeAtMillis": None,
            }
        }

        result = decide(configs(dungeon=True), state)

        self.assertEqual(result["feature"], "dungeon")

    def test_an_unrecognized_block_waits_long_but_not_forever(self) -> None:
        """It used to wait forever, invisibly.

        An error code absent from the allowlist removed the feature from the
        candidate set permanently, with no expiry and nothing to re-evaluate
        it: 副本 sat out four days on a preflight that had sent nothing.
        Failing closed here was also redundant - a mutation whose outcome is
        unknown is caught by the send-boundary probe, which removes the feature
        from the pending path *and* from the configured path.  So an
        unrecognized code waits six times longer than a known-safe one, and is
        reported on every tick, but it can no longer become invisible.
        """

        def state(blocked_at: int) -> Dict[str, Any]:
            return {
                "dungeon": {
                    "lastState": "blocked",
                    "lastErrorCode": "DUNGEON_DISPATCH_UNCERTAIN",
                    "lastMessage": "回执未确认",
                    "blockedAtMillis": blocked_at,
                    "nextWakeAtMillis": None,
                }
            }

        waiting = decide(
            configs(dungeon=True),
            state(NOW - UNRECOGNIZED_BLOCK_RETRY_MILLIS + 1),
        )
        self.assertIsNone(waiting["feature"])
        entry = waiting["blocked"][0]
        self.assertEqual(entry["feature"], "dungeon")
        self.assertEqual(entry["errorCode"], "DUNGEON_DISPATCH_UNCERTAIN")
        self.assertEqual(entry["reason"], "requires-attention")

        due = decide(
            configs(dungeon=True),
            state(NOW - UNRECOGNIZED_BLOCK_RETRY_MILLIS),
        )
        self.assertEqual(due["feature"], "dungeon")
        # Still named, so one retry never hides that it is in trouble.
        self.assertEqual(due["blocked"][0]["feature"], "dungeon")

    def test_the_unrecognized_backoff_is_anchored_not_recomputed(self) -> None:
        """Deriving it from "now" would produce a target that never arrives."""

        blocked_state = {
            "dungeon": {
                "lastState": "blocked",
                "lastErrorCode": "DUNGEON_DISPATCH_UNCERTAIN",
                "blockedAtMillis": NOW,
                "nextWakeAtMillis": None,
            }
        }
        expected = NOW + UNRECOGNIZED_BLOCK_RETRY_MILLIS
        for observed_at in (NOW, NOW + 60_000, NOW + 10 * 60_000):
            self.assertEqual(
                decide(configs(dungeon=True), blocked_state, now=observed_at)[
                    "nextWakeAtMillis"
                ],
                expected,
            )

    def test_a_known_safe_block_keeps_the_short_backoff(self) -> None:
        blocked_state = {
            "dungeon": {
                "lastState": "blocked",
                "lastErrorCode": "EXPEDITION_ENERGY_NOT_READY",
                "blockedAtMillis": NOW - BLOCKED_RETRY_MILLIS,
                "nextWakeAtMillis": None,
            }
        }

        result = decide(configs(dungeon=True), blocked_state)

        self.assertEqual(result["feature"], "dungeon")
        self.assertEqual(result["blocked"][0]["reason"], "self-recoverable")

    def test_defeat_paused_waits_for_acknowledgement(self) -> None:
        state = {
            "dungeon": {
                "lastState": "defeat-paused",
                "lastErrorCode": "",
                "nextWakeAtMillis": None,
            }
        }

        result = decide(configs(dungeon=True), state)

        self.assertIsNone(result["feature"])
        self.assertEqual(result["blocked"][0]["state"], "defeat-paused")


class ResidentPriorityStarvationTests(unittest.TestCase):
    def test_higher_priority_still_wins_a_normal_contest(self) -> None:
        state = {
            "brush": {"nextWakeAtMillis": NOW, "lastServedAtMillis": NOW},
            "dungeon": {"nextWakeAtMillis": NOW, "lastServedAtMillis": NOW},
        }

        result = decide(configs(brush=True, dungeon=True), state)

        self.assertEqual(result["feature"], "dungeon")
        self.assertFalse(result["starved"])

    def test_a_starved_candidate_jumps_the_queue_once(self) -> None:
        """Priority must order work, never exclude it forever."""

        state = {
            "brush": {
                "nextWakeAtMillis": NOW,
                "lastServedAtMillis": NOW - STARVATION_THRESHOLD_MILLIS - 1,
            },
            "dungeon": {"nextWakeAtMillis": NOW, "lastServedAtMillis": NOW},
        }

        result = decide(configs(brush=True, dungeon=True), state)

        self.assertEqual(result["feature"], "brush")
        self.assertTrue(result["starved"])

    def test_when_every_candidate_is_new_plain_priority_decides(self) -> None:
        state = {
            "brush": {"nextWakeAtMillis": NOW},
            "dungeon": {"nextWakeAtMillis": NOW},
        }

        result = decide(configs(brush=True, dungeon=True), state)

        self.assertEqual(result["feature"], "dungeon")

    def test_a_never_served_feature_outranks_a_recently_served_one(self) -> None:
        """The case that stalled a real account.

        将领维护 (priority 75) had never been selected, so it could never age
        into the boost, while 刷黄 (150) was due on every tick.  副本 (200) was
        blocked waiting on the energy top-up that 将领维护 performs.
        """

        state = {
            "brush": {"nextWakeAtMillis": NOW, "lastServedAtMillis": NOW - 1_000},
            "dungeon": {"nextWakeAtMillis": NOW},
        }

        result = decide(configs(brush=True, dungeon=True), state)

        self.assertEqual(result["feature"], "dungeon")
        self.assertTrue(result["starved"])


class StallReportingTests(unittest.TestCase):
    """The scheduler has to say what it is failing to run.

    Every stall so far was found by a person noticing that records had stopped
    appearing - after 70 hours, after 4 days, after 3 hours.  The due-set is
    already computed on every tick, so naming the features that keep losing
    costs nothing and turns hours of investigation into one log line.
    """

    def test_a_feature_late_past_the_threshold_is_named_with_its_lateness(self):
        rows = overdue_candidates(
            [
                {"feature": "dungeon", "dueAtMillis": NOW - STALL_REPORT_MILLIS},
                {"feature": "brushYellow", "dueAtMillis": NOW - 1_000},
            ],
            now_millis=NOW,
        )

        self.assertEqual(
            rows,
            [{
                "feature": "dungeon",
                "dueAtMillis": NOW - STALL_REPORT_MILLIS,
                "overdueMillis": STALL_REPORT_MILLIS,
            }],
        )

    def test_the_worst_offender_comes_first(self):
        rows = overdue_candidates(
            [
                {"feature": "brushYellow", "dueAtMillis": NOW - 20 * 60_000},
                {"feature": "dungeon", "dueAtMillis": NOW - 70 * 60 * 60_000},
            ],
            now_millis=NOW,
        )

        self.assertEqual(
            [row["feature"] for row in rows], ["dungeon", "brushYellow"]
        )

    def test_a_healthy_schedule_reports_nothing(self):
        self.assertEqual(
            overdue_candidates(
                [{"feature": "dungeon", "dueAtMillis": NOW + 60_000}],
                now_millis=NOW,
            ),
            [],
        )
        self.assertEqual(overdue_candidates([], now_millis=NOW), [])

    def test_malformed_rows_never_break_the_tick(self):
        self.assertEqual(
            overdue_candidates(
                ["dungeon", None, {"feature": "brush"}, {"dueAtMillis": "x"}],
                now_millis=NOW,
            ),
            [],
        )

    def test_the_decision_carries_the_report_on_every_outcome(self):
        stalled_state = {
            "brush": {"nextWakeAtMillis": NOW - 60 * 60_000},
            "dungeon": {"nextWakeAtMillis": NOW - 90 * 60_000},
        }
        selected = decide(configs(brush=True, dungeon=True), stalled_state)
        self.assertEqual(
            [row["feature"] for row in selected["stalled"]],
            ["dungeon", "brush"],
        )

        waiting = decide(
            configs(brush=True),
            {"brush": {"nextWakeAtMillis": NOW + 60_000}},
        )
        self.assertEqual(waiting["feature"], None)
        self.assertEqual(waiting["stalled"], [])


class AmbiguousPreflightReconciliationTests(unittest.TestCase):
    """Resolve an unknown preflight outcome by observation, never by replay."""

    FORMAL = ("prepareSendState", "dispatchSendState", "chestSendState")

    def reconcile(self, pending, generals):
        return ambiguous_preflight_reconciliation(
            pending,
            generals,
            formal_send_states=self.FORMAL,
            now_millis=NOW,
            poll_millis=30_000,
            retry_millis=10_000,
        )

    @staticmethod
    def idle(general_id: int) -> Dict[str, Any]:
        return {"id": general_id, "statusText": "闲"}

    def test_idle_generals_and_nothing_formal_sent_archives_the_ledger(self):
        decision = self.reconcile(
            {
                "generalIds": [7, 8],
                "preDispatchMutationState": "sending",
                "prepareSendState": "not-sent",
                "dispatchSendState": "not-sent",
                "chestSendState": "not-sent",
            },
            [self.idle(7), self.idle(8)],
        )

        self.assertEqual(decision["action"], "reconcile")
        self.assertEqual(decision["nextWakeAtMillis"], NOW + 10_000)

    def test_a_general_still_out_means_wait_not_archive(self):
        decision = self.reconcile(
            {"generalIds": [7, 8], "prepareSendState": "not-sent"},
            [self.idle(7), {"id": 8, "statusText": "征"}],
        )

        self.assertEqual(decision["action"], "wait")
        self.assertEqual(decision["nextWakeAtMillis"], NOW + 30_000)
        self.assertIn("8", decision["reason"])

    def test_a_general_missing_from_fresh_state_means_wait(self):
        decision = self.reconcile(
            {"generalIds": [7, 8], "prepareSendState": "not-sent"},
            [self.idle(7)],
        )

        self.assertEqual(decision["action"], "wait")

    def test_any_formal_send_still_stops_for_a_human(self):
        """The safety boundary must not move: this is the whole guarantee."""

        for key in self.FORMAL:
            for state in ("sending", "uncertain", "accepted", "rejected"):
                with self.subTest(key=key, state=state):
                    decision = self.reconcile(
                        {"generalIds": [7], key: state},
                        [self.idle(7)],
                    )
                    self.assertEqual(decision["action"], "isolate")

    def test_a_ledger_without_generals_cannot_be_reconciled(self):
        self.assertEqual(
            self.reconcile({"generalIds": []}, [self.idle(7)])["action"],
            "isolate",
        )


class PreDispatchOutstandingTests(unittest.TestCase):
    """One named question, answered from evidence, in one place.

    Five workflows each hand-wrote their own set of state strings for "might a
    preflight mutation have taken effect", and every one of those sets listed
    ``pending`` - the state that means *nothing has happened yet*.  A real
    account's 副本 sat blocked on exactly that, holding the pending lane while
    刷黄 starved twenty minutes and 将领维护 sixteen.  Fixing one site left the
    other four live.
    """

    def test_nothing_started_is_not_outstanding(self) -> None:
        for state in ("", "pending"):
            with self.subTest(state=state):
                self.assertFalse(pre_dispatch_outstanding({
                    "preDispatchMutationState": state,
                    "preDispatchMutationCount": 0,
                }))

    def test_the_exact_record_that_stalled_a_real_account(self) -> None:
        self.assertFalse(pre_dispatch_outstanding({
            "preDispatchMutationState": "pending",
            "preDispatchMutationCount": 0,
            "prepareSendState": "not-sent",
            "dispatchSendState": "not-sent",
            "chestSendState": "not-sent",
            "requiresAttention": True,
        }))

    def test_an_unknown_or_landed_outcome_is_outstanding(self) -> None:
        for state in ("sending", "uncertain", "accepted"):
            with self.subTest(state=state):
                self.assertTrue(pre_dispatch_outstanding({
                    "preDispatchMutationState": state,
                }))

    def test_a_failed_attempt_took_no_effect(self) -> None:
        self.assertFalse(pre_dispatch_outstanding({
            "preDispatchMutationState": "failed",
            "preDispatchMutationCount": 1,
        }))

    def test_a_counted_send_overrides_a_settled_label(self) -> None:
        """The count is evidence; the label is a claim.  Trust the evidence."""

        self.assertTrue(pre_dispatch_outstanding({
            "preDispatchMutationState": "pending",
            "preDispatchMutationCount": 1,
        }))

    def test_an_unrecognised_label_fails_closed(self) -> None:
        self.assertTrue(pre_dispatch_outstanding({
            "preDispatchMutationState": "some-future-state",
        }))

    def test_a_malformed_count_is_not_trusted_as_zero_evidence(self) -> None:
        self.assertFalse(pre_dispatch_outstanding({
            "preDispatchMutationState": "pending",
            "preDispatchMutationCount": "not-a-number",
        }))


class EveryExpeditionUsesTheOneAnswerTests(unittest.TestCase):
    def test_no_workflow_still_hand_writes_the_state_set(self) -> None:
        """Five copies is how fixing one site left four broken."""

        source = (
            ROOT / "shared_core" / "python" / "dwpm_core" / "facade.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn(
            '{"pending", "sending", "uncertain", "failed", "accepted"}',
            source,
        )
        self.assertGreaterEqual(source.count("pre_dispatch_outstanding("), 5)


if __name__ == "__main__":
    unittest.main()
