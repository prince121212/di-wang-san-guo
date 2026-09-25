from __future__ import annotations

import dataclasses
import json
import unittest
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import test_shared_resident_automation as resident
from dwpm_core.operations import OperationKnownFailureError
from dwpm_core.features.mine import build_recall_payload


class Gate:
    def __init__(self, allowed=False):
        self.allowed = allowed
        self.calls = []

    def check(self, force=False):
        self.calls.append(force)
        return {"allowed": self.allowed, "required": True, "code": "MEMBER_SESSION_REPLACED",
                "message": "会员账号已在其他手机登录，本机自动任务已暂停"}


class MembershipGateTests(unittest.TestCase):
    def setUp(self):
        self.facade, self.clock, self.directory = resident.SharedResidentAutomationTests()._facade()
        self.gate = Gate()
        self.facade._ports = dataclasses.replace(self.facade._ports, membership=self.gate)

    def tearDown(self):
        self.facade.close()
        self.directory.cleanup()

    def test_revoked_membership_never_dispatches_and_keeps_pending_game_ledgers(self):
        pending = {"dispatchSendState": "uncertain", "battleId": 0, "mineId": 88, "generalIds": [7]}
        self.facade._update_account_public_state("303", {"minePendingGarrisonJson": json.dumps(pending)})
        game = Mock(side_effect=AssertionError("new game action must not run"))
        self.facade._run_configured_resident_tick = game
        result = self.facade._run_automation_recovery_tick(resident.FakeExecution(), "303", {})
        self.assertEqual(result["state"], "membership-paused")
        self.assertEqual(result["errorCode"], "MEMBER_SESSION_REPLACED")
        self.assertEqual(self.facade._automation_pending_record("303", "minePendingGarrisonJson"), pending)
        game.assert_not_called()

    def test_raw_game_send_checks_membership_even_if_ui_is_bypassed(self):
        with self.assertRaises(OperationKnownFailureError) as caught:
            self.facade._execute_host_game_command("303", 0x1522, b"new-march", "test", {}, mutation_sent=True)
        self.assertEqual(caught.exception.code, "MEMBER_SESSION_REPLACED")

    def test_claiming_read_only_does_not_bypass_membership_outside_cleanup_scope(self):
        with self.assertRaises(OperationKnownFailureError):
            self.facade._require_game_membership("303", 0x1600, b"", {"readOnly": True})

    def test_cleanup_scope_only_permits_observation_and_exact_existing_mine_recall(self):
        self.facade._member_cleanup.mine = ("303", 991)
        self.facade._require_game_membership("303", 0x0004, b"", {"readOnly": True})
        self.facade._require_game_membership("303", 0x1526, build_recall_payload(991), {})
        for account, opcode, payload in [("303",0x1522,b""), ("303",0x1526,build_recall_payload(992)),
                                          ("304",0x1526,build_recall_payload(991))]:
            with self.assertRaises(OperationKnownFailureError):
                self.facade._require_game_membership(account,opcode,payload,{"readOnly":True})

    def test_known_accepted_mine_can_finish_under_revocation_without_new_work(self):
        pending = {"dispatchSendState": "accepted", "battleId": 991, "mineId": 88, "withdrawDefense": True}
        self.facade._update_account_public_state("303", {"minePendingGarrisonJson": json.dumps(pending)})
        def cleanup(*_a, **_k):
            self.facade._require_game_membership("303",0x1526,build_recall_payload(991),{})
            return {"state":"waiting-return"}
        self.facade._run_mine_garrison_game_workflow = cleanup
        result = self.facade._run_automation_recovery_tick(resident.FakeExecution(), "303", {})
        self.assertEqual(result["safeCleanup"]["state"],"waiting-return")
        self.assertIsNone(self.facade._member_cleanup.mine)

    def test_game_start_forces_check_but_background_relogin_cannot_reclaim_member_session(self):
        for source, force in [("android-webview",True),("shared-service-relogin",False)]:
            with self.assertRaises(OperationKnownFailureError):
                self.facade._run_account_login_workflow_locked({"accountRef":"303","mode":"start"},
                    {"source":source},resident.FakeExecution())
            self.assertEqual(self.gate.calls[-1], force)

    def test_two_active_game_account_limit_is_enforced_before_login(self):
        self.gate.allowed = True
        for ref in ("304","305"):
            self.facade.account_record_upsert({"accountRef":ref,"id":int(ref),"enabled":True})
        with self.assertRaises(OperationKnownFailureError) as caught:
            self.facade._run_account_login_workflow_locked({"accountRef":"303","mode":"start"},{},resident.FakeExecution())
        self.assertEqual(caught.exception.code,"MEMBER_GAME_ACCOUNT_LIMIT")

    def test_host_error_fails_closed_and_leaves_game_data_intact(self):
        self.gate.check = Mock(side_effect=OSError("offline"))
        with self.assertRaises(OperationKnownFailureError) as caught:
            self.facade._require_membership()
        self.assertEqual(caught.exception.code,"MEMBER_NETWORK_UNAVAILABLE")
        self.assertIsNotNone(self.facade._accounts.get("303"))

    def test_parallel_game_starts_cannot_both_take_the_last_slot(self):
        self.gate.allowed = True
        for ref in ("304", "305"):
            self.facade.account_record_upsert({"accountRef":ref,"id":int(ref),"enabled":False})
        barrier = threading.Barrier(2)
        def login(body, _context, _execution):
            enabled = sum(bool(a.get("enabled")) for a in self.facade._accounts.snapshot()["accounts"])
            if enabled >= 2:
                return "full"
            time.sleep(0.02)  # Deterministic overlap without the device-wide admission lock.
            ref = body["accountRef"]
            self.facade.account_record_upsert({"accountRef":ref,"id":int(ref),"enabled":True})
            return "started"
        self.facade._run_account_login_workflow_locked = login
        def start(ref):
            barrier.wait()
            return self.facade._run_account_login_workflow({"accountRef":ref,"mode":"start"},{},resident.FakeExecution())
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(start,["304","305"]))
        self.assertCountEqual(results,["started","full"])


if __name__ == "__main__":
    unittest.main()
