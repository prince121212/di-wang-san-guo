from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHARED_PYTHON = ROOT / "shared_core" / "python"
if str(SHARED_PYTHON) not in sys.path:
    sys.path.insert(0, str(SHARED_PYTHON))

from dwpm_core.facade import CoreFacade  # noqa: E402


class SharedAutomationPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.facade = CoreFacade(ROOT / "shared_core")

    def tearDown(self) -> None:
        self.facade.close()

    def test_start_saved_is_immediate_and_defers_when_account_is_stopped(self) -> None:
        response = self.facade.dispatch(
            "POST",
            "/api/automation/start-saved",
            {
                "accountRef": "202",
                "accountEnabled": False,
                "loginState": "REAL_PROTOCOL_STOPPED",
                "hasLiveSession": False,
                "savedTasksStarted": False,
                "executionOwnerActive": False,
            },
            {"requestId": "start-saved-stopped"},
        )

        self.assertEqual(response.status, 200)
        plan = response.body["plan"]
        self.assertFalse(plan["networkRequired"])
        self.assertTrue(plan["write"]["savedTasksStarted"])
        self.assertFalse(plan["write"]["activateNow"])
        self.assertEqual(plan["write"]["serviceAction"], "defer-until-account-start")
        self.assertTrue(plan["response"]["waitingForAccountStart"])

    def test_start_saved_activates_live_account_and_reports_idempotence(self) -> None:
        response = self.facade.dispatch(
            "POST",
            "/api/automation/start-saved",
            {
                "accountRef": "202",
                "accountEnabled": True,
                "loginState": "REAL_PROTOCOL_ONLINE",
                "hasLiveSession": True,
                "savedTasksStarted": True,
                "executionOwnerActive": True,
            },
            {"requestId": "start-saved-online"},
        )

        plan = response.body["plan"]
        self.assertTrue(plan["write"]["activateNow"])
        self.assertTrue(plan["response"]["alreadyStarted"])
        self.assertFalse(plan["response"]["waitingForAccountStart"])

    def test_stop_account_tasks_does_not_stop_or_logout_account(self) -> None:
        response = self.facade.dispatch(
            "POST",
            "/api/automation/stop",
            {"accountRef": "202"},
            {"requestId": "stop-automation-account"},
        )

        self.assertEqual(response.status, 200)
        write = response.body["plan"]["write"]
        self.assertEqual(write["scope"], "account")
        self.assertFalse(write["savedTasksStarted"])
        self.assertNotIn("enabled", write)
        self.assertNotIn("loginState", write)

    def test_stop_one_task_preserves_account_wide_saved_intent(self) -> None:
        response = self.facade.dispatch(
            "POST",
            "/api/automation/stop",
            {"taskId": "task-1"},
            {"requestId": "stop-automation-task"},
        )

        write = response.body["plan"]["write"]
        self.assertEqual(write["scope"], "task")
        self.assertEqual(write["taskId"], "task-1")
        self.assertNotIn("savedTasksStarted", write)


if __name__ == "__main__":
    unittest.main()
