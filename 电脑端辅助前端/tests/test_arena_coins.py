from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_arena_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class ArenaCoinTests(unittest.TestCase):
    DUPLICATE_PAYLOAD = bytes.fromhex("fe00000100000000000325e40000012c")

    def test_live_duplicate_response_is_idempotent_success(self) -> None:
        parsed = SERVER.parse_arena_coin_claim_response(self.DUPLICATE_PAYLOAD)

        self.assertTrue(parsed["success"])
        self.assertTrue(parsed["alreadyClaimed"])
        self.assertTrue(parsed["duplicateClaim"])
        self.assertEqual(parsed["status"], -2)
        self.assertEqual(parsed["message"], "领竞技币重复，22点后再领取！")

    def test_other_negative_response_is_not_misclassified_as_duplicate(self) -> None:
        parsed = SERVER.parse_arena_coin_claim_response(bytes.fromhex("fe0000"))

        self.assertFalse(parsed["success"])
        self.assertNotIn("duplicateClaim", parsed)

    def test_duplicate_result_marks_role_daily_task_done(self) -> None:
        original_completions = SERVER.DAILY_TASK_COMPLETIONS
        original_persist = SERVER.persist_runtime_state
        SERVER.DAILY_TASK_COMPLETIONS = {}
        SERVER.persist_runtime_state = lambda: None
        sess = {
            "username": "1608602",
            "area": {"areaId": "351"},
            "role": {"roleId": 928},
        }
        try:
            parsed = SERVER.parse_arena_coin_claim_response(self.DUPLICATE_PAYLOAD)
            self.assertTrue(parsed["success"])
            SERVER.record_daily_task_completion(
                sess,
                "arenaCoins",
                source="automation-duplicate",
            )
            arena = next(
                item
                for item in SERVER.current_daily_task_completions(sess)
                if item["key"] == "arenaCoins"
            )
        finally:
            SERVER.DAILY_TASK_COMPLETIONS = original_completions
            SERVER.persist_runtime_state = original_persist

        self.assertTrue(arena["completed"])
        self.assertEqual(arena["source"], "automation-duplicate")


if __name__ == "__main__":
    unittest.main()
