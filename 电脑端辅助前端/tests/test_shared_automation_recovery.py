from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHARED_PYTHON = ROOT / "shared_core" / "python"
if str(SHARED_PYTHON) not in sys.path:
    sys.path.insert(0, str(SHARED_PYTHON))

from dwpm_core.automation import (  # noqa: E402
    brush_recovery_decision,
    mine_garrison_decision,
)


class SharedAutomationRecoveryTests(unittest.TestCase):
    def test_brush_requires_fresh_busy_to_idle_or_full_refresh_grace(self) -> None:
        pending = {
            "generalIds": [1, 2],
            "createdAtMillis": 1_000,
            "sendState": "accepted",
        }
        schedule = {
            "postDispatchPollMillis": 30_000,
            "settlementRecheckGraceMillis": 300_000,
        }
        idle = [
            {"id": 1, "status": 0, "statusText": "闲"},
            {"id": 2, "status": 0, "statusText": "闲"},
        ]
        early = brush_recovery_decision(
            pending, idle, now_millis=31_000, schedule=schedule
        )
        self.assertEqual(early["action"], "wait")
        self.assertIn("尚未观察", early["reason"])

        busy = brush_recovery_decision(
            early["pending"],
            [idle[0], {"id": 2, "status": 6, "statusText": "战"}],
            now_millis=61_000,
            schedule=schedule,
        )
        self.assertEqual(busy["action"], "wait")
        self.assertTrue(busy["pending"]["sawBusy"])
        returned = brush_recovery_decision(
            busy["pending"], idle, now_millis=91_000, schedule=schedule
        )
        self.assertEqual(returned["action"], "maintain")

        grace = brush_recovery_decision(
            pending, idle, now_millis=301_001, schedule=schedule
        )
        self.assertEqual(grace["action"], "maintain")

    def test_mine_only_recalls_exact_confirmed_garrison(self) -> None:
        pending = {
            "battleId": 99,
            "mineId": 7,
            "generalIds": [1],
            "x": 18,
            "y": 22,
            "dispatchAtMillis": 1_000,
            "withdrawDefense": True,
            "recallRequestedAtMillis": 0,
        }
        schedule = {
            "garrisonPollMillis": 10_000,
            "missingMilitaryGraceMillis": 120_000,
            "settlementTimeoutMillis": 14_400_000,
        }
        busy = [{"id": 1, "status": 6, "statusText": "战"}]
        absent = mine_garrison_decision(
            pending, {"actions": []}, busy,
            now_millis=20_000, schedule=schedule,
        )
        self.assertEqual(absent["action"], "wait")

        wrong = mine_garrison_decision(
            pending,
            {"actions": [{
                "battleId": 99,
                "state": "驻守",
                "x": 17,
                "y": 22,
                "generalIds": [1],
            }]},
            busy,
            now_millis=30_000,
            schedule=schedule,
        )
        self.assertEqual(wrong["action"], "stop")

        confirmed = mine_garrison_decision(
            pending,
            {"actions": [{
                "battleId": 99,
                "state": "驻守",
                "x": 18,
                "y": 22,
                "generalIds": [1],
            }]},
            busy,
            now_millis=30_000,
            schedule=schedule,
        )
        self.assertEqual(confirmed["action"], "recall")

    def test_mine_clears_after_recall_only_when_all_generals_idle(self) -> None:
        pending = {
            "battleId": 99,
            "mineId": 7,
            "generalIds": [1, 2],
            "dispatchAtMillis": 1_000,
            "recallRequestedAtMillis": 5_000,
        }
        schedule = {"garrisonPollMillis": 10_000}
        waiting = mine_garrison_decision(
            pending,
            {"actions": []},
            [
                {"id": 1, "status": 0, "statusText": "闲"},
                {"id": 2, "status": 4, "statusText": "返"},
            ],
            now_millis=20_000,
            schedule=schedule,
        )
        self.assertEqual(waiting["action"], "wait")
        complete = mine_garrison_decision(
            pending,
            {"actions": []},
            [
                {"id": 1, "status": 0, "statusText": "闲"},
                {"id": 2, "status": 0, "statusText": "闲"},
            ],
            now_millis=30_000,
            schedule=schedule,
        )
        self.assertEqual(complete["action"], "complete")
        self.assertEqual(complete["outcome"], "recalled")

    def test_mine_round_verdict_is_accumulated_not_guessed_at_the_end(
        self,
    ) -> None:
        """Won and lost rounds end identically: the generals are simply home.

        The difference is only visible while it passes - 驻守 once the point is
        held, 返回 once the troops turn around - so each observation is folded
        onto the record and the closing tick reads the verdict off it.  A round
        whose 军情 was never seen must stay ``unknown``: the operator is told
        about losses, so a guess here is a false alarm.
        """

        schedule = {
            "garrisonPollMillis": 10_000,
            "missingMilitaryGraceMillis": 120_000,
            "settlementTimeoutMillis": 14_400_000,
        }
        idle = [{"id": 1, "status": 0, "statusText": "闲"}]
        base = {
            "battleId": 99,
            "generalIds": [1],
            "x": 18,
            "y": 22,
            "dispatchAtMillis": 1_000,
            "withdrawDefense": True,
        }

        marching = mine_garrison_decision(
            base,
            {"actions": [{
                "battleId": 99, "state": "返回", "x": 18, "y": 22,
                "generalIds": [1],
            }]},
            [{"id": 1, "status": 4, "statusText": "返"}],
            now_millis=30_000,
            schedule=schedule,
        )
        self.assertEqual("wait", marching["action"])
        self.assertGreater(
            int(marching["pending"]["returnObservedAtMillis"]), 0
        )

        # 军情 has since dropped the finished battle; the generals are home.
        lost = mine_garrison_decision(
            marching["pending"],
            {"actions": []},
            idle,
            now_millis=200_000,
            schedule=schedule,
        )
        self.assertEqual("complete", lost["action"])
        self.assertEqual("failed", lost["outcome"])

        silent = mine_garrison_decision(
            base,
            {"actions": []},
            idle,
            now_millis=200_000,
            schedule=schedule,
        )
        self.assertEqual("complete", silent["action"])
        self.assertEqual(
            "unknown",
            silent["outcome"],
            "never having seen the round is not evidence that it was lost",
        )

        held = mine_garrison_decision(
            {**base, "withdrawDefense": False},
            {"actions": [{
                "battleId": 99, "state": "驻守", "x": 18, "y": 22,
                "generalIds": [1],
            }]},
            [{"id": 1, "status": 3, "statusText": "防"}],
            now_millis=30_000,
            schedule=schedule,
        )
        self.assertEqual("complete", held["action"])
        self.assertEqual("garrisoned", held["outcome"])


if __name__ == "__main__":
    unittest.main()
