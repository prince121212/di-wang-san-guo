from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_sign_in_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


def packet(opcode: int, payload: bytes) -> dict:
    return {"opcode": opcode, "payload": payload, "len": len(payload), "frag": 0}


class AutoSignInTests(unittest.TestCase):
    def test_live_fresh_activity_reply_is_success(self) -> None:
        reward = "铜钱:10000获得成功。粮食:30000获得成功。"
        payload = b"\x00\x00\x0bactivity-list-data" + SERVER.utf(reward)

        parsed = SERVER.parse_daily_sign_in_packets([packet(0x8134, payload)])

        self.assertTrue(parsed["success"])
        self.assertFalse(parsed["alreadyClaimed"])
        self.assertFalse(parsed["duplicateClaim"])
        self.assertEqual(parsed["status"], 0)
        self.assertEqual(parsed["responseOpcode"], "0x8134")
        self.assertEqual(
            parsed["message"],
            "铜钱:10000获得成功；粮食:30000获得成功",
        )
        self.assertEqual(parsed["serverMessage"], reward)

    def test_live_already_signed_activity_reply_is_idempotent_success(self) -> None:
        payload = b"\x0a\x00\x01" + SERVER.utf("本日已签到")

        parsed = SERVER.parse_daily_sign_in_packets([packet(0x8134, payload)])

        self.assertTrue(parsed["success"])
        self.assertTrue(parsed["alreadyClaimed"])
        self.assertTrue(parsed["duplicateClaim"])
        self.assertEqual(parsed["serverMessage"], "本日已签到")
        self.assertEqual(parsed["message"], "自动签到重复，本日已签到，明日再签到！")
        self.assertEqual(parsed["responseOpcode"], "0x8134")

    def test_empty_e202_is_fresh_sign_in_success(self) -> None:
        parsed = SERVER.parse_daily_sign_in_packets([packet(0xE202, b"")])

        self.assertTrue(parsed["success"])
        self.assertFalse(parsed.get("duplicateClaim", False))
        self.assertEqual(parsed["responseOpcode"], "0xe202")

    def test_duplicate_sign_in_marks_role_daily_task_done(self) -> None:
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
            SERVER.record_daily_task_completion(
                sess,
                "autoSignIn",
                source="automation-duplicate",
            )
            sign_in = next(
                item
                for item in SERVER.current_daily_task_completions(sess)
                if item["key"] == "autoSignIn"
            )
        finally:
            SERVER.DAILY_TASK_COMPLETIONS = original_completions
            SERVER.persist_runtime_state = original_persist

        self.assertTrue(sign_in["completed"])
        self.assertEqual(sign_in["source"], "automation-duplicate")


if __name__ == "__main__":
    unittest.main()
