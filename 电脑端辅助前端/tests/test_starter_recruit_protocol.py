import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


class StarterRecruitProtocolTest(unittest.TestCase):
    def test_base_vehicle_bootstrap_submits_exact_200_cart_order(self):
        sess = {
            "roleState": {"level": 7},
            "starterFirstPackOpened": True,
        }
        plan = {
            "fiefs": [{
                "fiefId": 100,
                "isBase": True,
                "buildings": [{
                    "instanceId": 7001,
                    "slot": 6,
                    "type": 6,
                    "level": 1,
                    "busy": False,
                }],
                "list1": [],
            }],
        }
        with patch.object(
            server,
            "execute_soldier_recruit",
            return_value={
                "success": True,
                "count": 200,
                "estimatedDurationSec": 7200,
            },
        ) as recruit, patch.object(server, "persist_runtime_state"):
            result = server.starter_base_vehicle_bootstrap_step(sess, plan)
        self.assertTrue(result["success"])
        self.assertEqual(
            recruit.call_args.args,
            (sess, 100, server.SOLDIER_TYPE_CODES["弩车"], 200),
        )
        self.assertEqual(
            recruit.call_args.kwargs,
            {"confirm_delay_sec": 8.0},
        )
        state = sess["starterBaseVehicleBootstrap"]
        self.assertEqual(state["targetBaseIdle"], 200)
        self.assertEqual(state["pending"]["count"], 200)

    def test_parse_captured_candidate_row(self):
        payload = bytes.fromhex(
            "000000000226b55d"
            "0006e580aae696b9"
            "00000148"
            "02d2"
            "01"
            "0032"
            "0045"
            "0033"
            "0029"
        )
        rows = server.parse_starter_recruit_candidates(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "倪方")
        self.assertEqual(rows[0]["kind"], "步将")
        self.assertEqual(rows[0]["growth"], 50)
        self.assertEqual(rows[0]["attack"], 69)
        self.assertEqual(rows[0]["intelligence"], 51)
        self.assertEqual(rows[0]["command"], 41)

    def test_recruit_list_query_sends_captured_mode_byte(self):
        payload = bytes.fromhex(
            "00000000003c1d90"
            "0009e5b089e8bf9fe4b9be"
            "0000014a"
            "02d4"
            "01"
            "0029"
            "0046"
            "003b"
            "0033"
        )
        sess = {
            "sessionId": "starter-1",
            "gameHttp": "http://game/kingWapServer/HttpClient",
            "dm": 1,
            "generals": [],
            "roleState": {"generalLimit": 11},
        }
        with patch.object(
            server,
            "post_game",
            return_value=(
                200,
                b"response",
                [{
                    "opcode": 0x821B,
                    "len": len(payload),
                    "frag": 0,
                    "payload": payload,
                }],
            ),
        ) as post, patch.object(server, "persist_runtime_state"):
            result = server.query_starter_recruit_list(sess)
        self.assertEqual(post.call_args.args[1], [(0x121B, b"\x00")])
        self.assertTrue(result["success"])
        self.assertEqual(result["candidates"][0]["name"], "尉迟乾")

    def test_front_line_general_is_prioritized(self):
        step = {"kind": "步将", "growth": 50, "command": 41, "attack": 69}
        cavalry = {"kind": "骑将", "growth": 70, "command": 47, "attack": 48}
        self.assertGreater(
            server.starter_recruit_score(step, []),
            server.starter_recruit_score(cavalry, []),
        )

    def test_crossbow_recruit_preview_matches_capture(self):
        payload = server.build_soldier_recruit_preview_payload(0x0FA5, 4, 204)
        self.assertEqual(
            payload.hex(),
            "0000000000000fa500000004000000cc0000000000000000",
        )

    def test_normal_crossbow_recruit_matches_capture_and_never_uses_urgent(self):
        payload = server.build_soldier_recruit_payload(
            0x0FA5, 4, 204, urgent=False,
        )
        self.assertEqual(
            payload.hex(),
            "0000000000000fa5fe0004000000cc00",
        )

    def test_recruit_duration_is_parsed_from_server_preview(self):
        self.assertEqual(
            server.parse_recruit_duration_seconds(
                "当前封地共有12个战车营可以有征兵队列 招募时间 0:52:00"
            ),
            52 * 60,
        )

    def test_recruit_status_four_is_timeout_not_success(self):
        sess = {"sessionId": "s1", "gameHttp": "http://game", "dm": 1}
        with patch.object(
            server,
            "query_soldier_recruit_preview",
            return_value={"success": True, "message": "招募时间 0:52:00"},
        ), patch.object(
            server,
            "post_game",
            return_value=(
                200,
                b"",
                [{
                    "opcode": 0x823D,
                    "len": 29,
                    "frag": 0,
                    "payload": bytes.fromhex(
                        "04000000000000151800000000000000000000d6cd000000000001891b"
                    ),
                }],
            ),
        ), patch.object(server.time, "sleep"):
            result = server.execute_soldier_recruit(sess, 5400, 4, 200)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], 4)
        self.assertIn("超时", result["message"])

    def test_recruit_confirmation_submits_total_and_trusts_queue_sync(self):
        import struct

        sess = {"sessionId": "s1", "gameHttp": "http://game", "dm": 1}
        previews = [{
            "success": True,
            "message": "共有12个战车营 平均每个战车营可以招募16个 招募时间 0:52:00",
            "campCount": 12,
            "averagePerCamp": 16,
            "estimatedCapacity": 192,
        }]
        response_payload = (
            struct.pack(">bqi", 0, 5469, 1)
            + struct.pack(">bqB", 1, 57349, 1)
            + struct.pack(">qbhiiqbi", 43296, 0, 4, 200, 200, 195000, 0, 195000)
            + bytes(16)
        )
        with patch.object(
            server, "query_soldier_recruit_preview", side_effect=previews,
        ) as preview, patch.object(
            server,
            "post_game",
            return_value=(
                200,
                b"",
                [{
                    "opcode": 0x823D,
                    "len": len(response_payload),
                    "frag": 0,
                    "payload": response_payload,
                }],
            ),
        ) as post, patch.object(server.time, "sleep") as sleep:
            result = server.execute_soldier_recruit(sess, 5469, 4, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["requestedCount"], 200)
        self.assertEqual(result["count"], 200)
        self.assertEqual(result["submittedCount"], 200)
        self.assertEqual(preview.call_count, 1)
        self.assertEqual(result["campCount"], 12)
        self.assertEqual(result["perCampCount"], 200)
        self.assertEqual(result["confirmDelaySec"], 0.35)
        sleep.assert_called_once_with(0.35)
        sent_payload = post.call_args.args[1][0][1]
        self.assertEqual(sent_payload.hex(), "000000000000155dfe0004000000c800")

    def test_multi_camp_recruit_can_submit_preview_average(self):
        import struct

        sess = {"sessionId": "s1", "gameHttp": "http://game", "dm": 1}
        response_payload = struct.pack(">bqi", 0, 5469, 12)
        for index in range(12):
            queue_count = 5 if index == 11 else 1
            response_payload += struct.pack(
                ">bqB", 1, 57349 + index, 1,
            )
            response_payload += struct.pack(
                ">qbhiiqbi",
                43296 + index,
                0,
                4,
                queue_count,
                queue_count,
                queue_count * 195000,
                0,
                195000,
            )
        response_payload += bytes(16)
        with patch.object(
            server,
            "query_soldier_recruit_preview",
            return_value={
                "success": True,
                "message": "共有12个战车营 平均每个战车营可以招募16个",
                "campCount": 12,
                "averagePerCamp": 16,
                "estimatedCapacity": 192,
            },
        ), patch.object(
            server,
            "post_game",
            return_value=(
                200,
                b"",
                [{
                    "opcode": 0x823D,
                    "len": len(response_payload),
                    "frag": 0,
                    "payload": response_payload,
                }],
            ),
        ) as post, patch.object(server.time, "sleep"):
            result = server.execute_soldier_recruit(
                sess,
                5469,
                4,
                200,
                submit_preview_average=True,
            )
        self.assertTrue(result["success"])
        self.assertEqual(result["requestedCount"], 200)
        self.assertEqual(result["submittedCount"], 16)
        self.assertEqual(result["count"], 16)
        self.assertTrue(result["submittedPreviewAverage"])
        sent_payload = post.call_args.args[1][0][1]
        self.assertEqual(sent_payload.hex(), "000000000000155dfe00040000001000")

    def test_recruit_confirmation_supports_captured_single_camp_wait(self):
        import struct

        sess = {"sessionId": "s1", "gameHttp": "http://game", "dm": 1}
        response_payload = (
            struct.pack(">bqi", 0, 16544, 1)
            + struct.pack(">bqB", 1, 57349, 1)
            + struct.pack(
                ">qbhiiqbi",
                43296, 0, 4, 200, 200, 36_792_000, 0, 183_960,
            )
            + bytes(16)
        )
        with patch.object(
            server,
            "query_soldier_recruit_preview",
            return_value={
                "success": True,
                "message": "共有1个战车营 平均每个战车营可以招募200个",
                "campCount": 1,
                "averagePerCamp": 200,
            },
        ), patch.object(
            server,
            "post_game",
            return_value=(
                200,
                b"",
                [{
                    "opcode": 0x823D,
                    "len": len(response_payload),
                    "frag": 0,
                    "payload": response_payload,
                }],
            ),
        ), patch.object(server.time, "sleep") as sleep:
            result = server.execute_soldier_recruit(
                sess, 16544, 4, 200, confirm_delay_sec=8.0,
            )
        self.assertTrue(result["success"])
        self.assertEqual(result["confirmDelaySec"], 8.0)
        sleep.assert_called_once_with(8.0)

    def test_parse_real_multi_camp_sync_detects_distributed_total(self):
        import struct

        raw = struct.pack(">bqi", 0, 5469, 12)
        for index in range(12):
            count = 5 if index == 11 else 1
            raw += struct.pack(">bqB", 1, 57349 + index, 1)
            raw += struct.pack(
                ">qbhiiqbi",
                43296 + index, 0, 4, count, count,
                count * 195000, 0, 195000,
            )
        raw += bytes(16)
        parsed = server.parse_recruit_success_823d(raw)
        self.assertEqual(parsed["blockCount"], 12)
        self.assertEqual(len(parsed["queues"]), 12)
        self.assertEqual(parsed["totalCount"], 16)

    def test_recruit_speed_item_matches_captured_emergency_order(self):
        import struct

        payload = struct.pack(">qHqH", 0x0FA5, 29, 0xA727, 1)
        self.assertEqual(
            payload.hex(),
            "0000000000000fa5001d000000000000a7270001",
        )

    def test_recruit_speed_uses_smallest_sufficient_order(self):
        inventory = {
            "items": [
                {"itemId": 27, "count": 1},
                {"itemId": 28, "count": 2},
                {"itemId": 29, "count": 1},
            ],
        }
        self.assertEqual(
            server.starter_select_recruit_speed_item(inventory, 369), 27
        )
        self.assertEqual(
            server.starter_select_recruit_speed_item(inventory, 7200), 28
        )
        self.assertEqual(
            server.starter_select_recruit_speed_item(inventory, 25000), 29
        )

    def test_low_resource_batch_applies_to_carts_and_heavy_infantry(self):
        sess = {"roleState": {"food": 8_000}}
        self.assertEqual(
            server.starter_affordable_recruit_batch(sess, 184, 4), 10
        )
        self.assertEqual(
            server.starter_affordable_recruit_batch(sess, 200, 2), 10
        )
        sess["roleState"]["food"] = 30_000
        self.assertEqual(
            server.starter_affordable_recruit_batch(sess, 184, 4), 50
        )
        self.assertEqual(
            server.starter_affordable_recruit_batch(sess, 20, 4), 20
        )
        sess["roleState"]["food"] = 500_000
        self.assertEqual(
            server.starter_affordable_recruit_batch(sess, 200, 4), 50
        )
        self.assertEqual(
            server.starter_affordable_recruit_batch(sess, 200, 8), 200
        )

    def test_open_fief_payload_matches_capture(self):
        self.assertEqual(
            server.build_starter_open_fief_payload(0x212).hex(),
            "000000000000000002120000",
        )

    def test_temporary_fief_does_not_recruit_before_all_vehicle_slots_exist(self):
        plan = {
            "baseFiefId": 100,
            "fiefs": [
                {"fiefId": 100, "isBase": True, "buildings": []},
                {
                    "fiefId": 200,
                    "isBase": False,
                    "buildings": [
                        {
                            "slot": 1, "type": 6, "level": 1,
                            "busy": False, "instanceId": 9001,
                        },
                    ],
                },
            ],
        }
        result = server.starter_recruitment_step({}, plan)
        self.assertTrue(result["skipped"])

    def test_filled_temporary_fief_starts_normal_crossbow_recruitment(self):
        plan = {
            "baseFiefId": 100,
            "fiefs": [
                {"fiefId": 100, "isBase": True, "buildings": []},
                {
                    "fiefId": 200,
                    "isBase": False,
                    "buildings": [
                        {
                            "slot": slot, "type": 6, "level": 1,
                            "busy": False, "instanceId": 9000 + slot,
                        }
                        for slot in range(1, 13)
                    ],
                },
            ],
        }
        sess = {}
        with patch.object(
            server,
            "execute_soldier_recruit",
            return_value={
                "success": True,
                "message": "ok",
                "estimatedDurationSec": 3120,
            },
        ) as recruit, patch.object(server, "persist_runtime_state"):
            result = server.starter_recruitment_step(sess, plan)
        self.assertTrue(result["success"])
        recruit.assert_called_once_with(
            sess, 200, server.SOLDIER_TYPE_CODES["弩车"], 50,
        )
        self.assertEqual(sess["starterTemporaryFiefRecruitSubmitted"]["200"], 50)
        self.assertGreater(
            sess["starterRecruitmentStates"]["200:4"]["readyAt"],
            sess["starterRecruitmentStates"]["200:4"]["submittedAt"],
        )

    def test_pending_temporary_recruitment_is_not_abandoned_early(self):
        plan = {
            "baseFiefId": 100,
            "fiefs": [
                {"fiefId": 100, "isBase": True, "buildings": []},
                {
                    "fiefId": 200,
                    "isBase": False,
                    "buildings": [
                        {
                            "slot": slot, "type": 6, "level": 1,
                            "busy": False, "instanceId": 9000 + slot,
                        }
                        for slot in range(1, 13)
                    ],
                },
            ],
        }
        sess = {
            "starterRecruitmentStates": {
                "200:4": {
                    "fiefId": 200,
                    "soldierTypeCode": 4,
                    "count": 200,
                    "readyAt": server.now_ms() + 120_000,
                },
            },
        }
        with patch.object(
            server, "execute_starter_abandon_temporary_fief",
        ) as abandon:
            result = server.starter_recruitment_step(sess, plan)
        self.assertTrue(result["skipped"])
        self.assertTrue(result["recruiting"])

    def test_elapsed_timer_does_not_abandon_until_server_lists_completed_troops(self):
        plan = {
            "baseFiefId": 100,
            "fiefs": [
                {"fiefId": 100, "isBase": True, "buildings": []},
                {
                    "fiefId": 200,
                    "isBase": False,
                    "buildings": [
                        {
                            "slot": slot, "type": 6, "level": 1,
                            "busy": False, "instanceId": 9000 + slot,
                        }
                        for slot in range(1, 13)
                    ],
                },
            ],
        }
        sess = {
            "starterRecruitmentStates": {
                "200:4": {
                    "fiefId": 200,
                    "soldierTypeCode": 4,
                    "count": 192,
                    "readyAt": server.now_ms() - 1,
                },
            },
        }
        with patch.object(
            server,
            "query_fief_buildings",
            return_value={"fiefId": 200, "list1": [{"type": 4, "value": 180}]},
        ), patch.object(
            server, "execute_starter_abandon_temporary_fief",
        ) as abandon:
            result = server.starter_recruitment_step(sess, plan)
        self.assertTrue(result["skipped"])
        self.assertFalse(result["serverCompletionConfirmed"])
        self.assertEqual(result["serverCompletedCount"], 180)
        abandon.assert_not_called()

    def test_server_completed_troops_allow_temporary_fief_abandon(self):
        plan = {
            "baseFiefId": 100,
            "fiefs": [
                {"fiefId": 100, "isBase": True, "buildings": []},
                {
                    "fiefId": 200,
                    "isBase": False,
                    "buildings": [
                        {
                            "slot": slot, "type": 6, "level": 1,
                            "busy": False, "instanceId": 9000 + slot,
                        }
                        for slot in range(1, 13)
                    ],
                },
            ],
        }
        sess = {
            "starterRecruitmentStates": {
                "200:4": {
                    "fiefId": 200,
                    "soldierTypeCode": 4,
                    "count": 192,
                    "readyAt": server.now_ms() - 1,
                },
            },
        }
        with patch.object(
            server,
            "query_fief_buildings",
            return_value={"fiefId": 200, "list1": [{"type": 4, "value": 192}]},
        ), patch.object(
            server,
            "execute_starter_abandon_temporary_fief",
            return_value={"success": True, "message": "已放弃"},
        ) as abandon:
            result = server.starter_recruitment_step(sess, plan)
        self.assertTrue(result["success"])
        abandon.assert_called_once_with(sess, 200, base_fief_id=100)

    def test_accidental_small_recruit_is_topped_up_before_abandon(self):
        plan = {
            "baseFiefId": 100,
            "fiefs": [
                {"fiefId": 100, "isBase": True, "buildings": []},
                {
                    "fiefId": 200,
                    "isBase": False,
                    "buildings": [
                        {
                            "slot": slot, "type": 6, "level": 1,
                            "busy": False, "instanceId": 9000 + slot,
                        }
                        for slot in range(1, 13)
                    ],
                },
            ],
        }
        sess = {
            "starterRecruitmentStates": {
                "200:4": {
                    "fiefId": 200,
                    "soldierTypeCode": 4,
                    "count": 12,
                    "targetCount": 200,
                    "readyAt": server.now_ms() - 1,
                },
            },
        }
        with patch.object(
            server,
            "query_fief_buildings",
            return_value={"fiefId": 200, "list1": [{"type": 4, "value": 12}]},
        ), patch.object(
            server,
            "execute_soldier_recruit",
            return_value={"success": False, "message": "测试停止"},
        ) as recruit, patch.object(
            server, "persist_runtime_state",
        ), patch.object(
            server, "execute_starter_abandon_temporary_fief",
        ) as abandon:
            server.starter_recruitment_step(sess, plan)
        recruit.assert_called_once_with(sess, 200, 4, 50)
        abandon.assert_not_called()

    def test_temporary_cart_queue_does_not_block_base_heavy_recruit(self):
        plan = {
            "baseFiefId": 100,
            "fiefs": [
                {
                    "fiefId": 100,
                    "isBase": True,
                    "buildings": [{
                        "slot": 10, "type": 4, "level": 7,
                        "busy": False, "instanceId": 7001,
                    }],
                },
                {
                    "fiefId": 200,
                    "isBase": False,
                    "buildings": [
                        {
                            "slot": slot, "type": 6, "level": 1,
                            "busy": False, "instanceId": 9000 + slot,
                        }
                        for slot in range(1, 13)
                    ],
                },
            ],
        }
        sess = {
            "starterRecruitmentStates": {
                "200:4": {
                    "fiefId": 200,
                    "soldierTypeCode": 4,
                    "count": 192,
                    "readyAt": server.now_ms() + 60_000,
                },
            },
            "army": [],
            "generals": [],
        }
        with patch.object(
            server,
            "execute_soldier_recruit",
            return_value={
                "success": True,
                "message": "已招募重步兵",
                "count": 200,
                "estimatedDurationSec": 3600,
            },
        ) as recruit, patch.object(server, "persist_runtime_state"):
            result = server.starter_recruitment_step(sess, plan)
        self.assertTrue(result["success"])
        recruit.assert_called_once_with(sess, 100, 8, 200)
        self.assertIn("100:8", sess["starterRecruitmentStates"])

    def test_pending_transfer_blocks_next_fief_until_total_is_confirmed(self):
        sess = {
            "army": [{"soldierType": "弩车", "idleCount": 300}],
            "generals": [],
            "starterPendingTransferChecks": {
                "200": {
                    "fiefId": 200,
                    "expectedMinimumTotal": 372,
                },
            },
        }
        with patch.object(server, "refresh_generals"), patch.object(
            server, "persist_runtime_state",
        ):
            waiting = server.starter_verify_pending_transfers(sess)
            self.assertFalse(waiting["confirmed"])
            self.assertEqual(waiting["observedOwnedTotal"], 300)
            sess["army"][0]["idleCount"] = 372
            confirmed = server.starter_verify_pending_transfers(sess)
        self.assertTrue(confirmed["confirmed"])
        self.assertFalse(sess["starterPendingTransferChecks"])

    def test_plan_owned_soldiers_include_idle_and_assigned_fief_lists(self):
        plan = {
            "fiefs": [{
                "list1": [{"type": 4, "value": 90}],
                "list2": [{"type": 4, "value": 90}, {"type": 8, "value": 100}],
            }],
        }
        self.assertEqual(
            server.starter_plan_owned_soldier_count(plan, 4), 180
        )


if __name__ == "__main__":
    unittest.main()
