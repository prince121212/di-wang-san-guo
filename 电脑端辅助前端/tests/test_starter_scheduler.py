from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server


class StarterSchedulerTest(unittest.TestCase):
    def test_successful_combat_dispatch_gets_one_second_follow_up(self):
        wait_sec = server.starter_scheduler_wait_seconds({
            "action": {"action_type": "five-stage-growth"},
            "result": {
                "success": True,
                "deploymentSuccess": True,
            },
        })
        self.assertEqual(wait_sec, 1)

    def test_long_combat_backoff_is_polled_at_bounded_cadence(self):
        wait_sec = server.starter_scheduler_wait_seconds({
            "action": {"action_type": "five-stage-growth"},
            "result": {
                "success": False,
                "deferred": True,
                "retryAfterSec": 600,
            },
        })
        self.assertEqual(wait_sec, 5)

    def test_fresh_job_starts_with_ordered_onboarding_and_sign_in(self):
        with tempfile.TemporaryDirectory() as tempdir:
            database = Path(tempdir) / "assistant_state.sqlite3"
            with patch.object(server, "ACCOUNT_STATE_DB_FILE", database):
                with sqlite3.connect(database) as connection:
                    server._account_state_schema_v1(connection)
                    at = server.now_ms()
                    connection.execute(
                        """
                        INSERT INTO starter_jobs(
                            job_id,account_id,platform,target_server,target_level,
                            status,current_stage,current_step,progress,control_state,
                            snapshot_json,created_at,updated_at
                        ) VALUES(?,?,?,?,?,'running','automatic_growth','test',45,
                                 'running','{}',?,?)
                        """,
                        (
                            "starter-fresh", "account-fresh", "downjoy",
                            "双线1016区", 66, at, at,
                        ),
                    )
                    connection.commit()
                actions = server.sync_starter_planned_actions(
                    "starter-fresh",
                    {
                        "roleState": {"level": 7},
                        "army": [{"soldierType": "轻骑兵", "idleCount": 200}],
                        "generals": [{
                            "id": 1,
                            "name": "测试将领",
                            "displayStatus": "闲",
                            "tili": 100,
                            "troopLimit": 200,
                        }],
                    },
                )
                self.assertEqual(
                    {action["action_type"] for action in actions},
                    {"five-stage-onboarding"},
                )


if __name__ == "__main__":
    unittest.main()
