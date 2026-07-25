from __future__ import annotations

import importlib.util
import sqlite3
import struct
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_mine_sqlite_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class MineSqliteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_dir = SERVER.SHARED_MAP_DIR
        self.old_initialized = SERVER.BANDIT_DB_INITIALIZED_PATHS
        SERVER.SHARED_MAP_DIR = Path(self.tmp.name)
        SERVER.BANDIT_DB_INITIALIZED_PATHS = set()
        self.sess = {
            "sessionId": "mine-sqlite-a",
            "username": "1608601",
            "area": {"areaId": 351, "areaName": "351区"},
        }

    def tearDown(self) -> None:
        SERVER.SHARED_MAP_DIR = self.old_dir
        SERVER.BANDIT_DB_INITIALIZED_PATHS = self.old_initialized
        self.tmp.cleanup()

    def test_task_overview_exposes_resource_capacity_and_daily_dungeon_count(self) -> None:
        sess = {
            **self.sess,
            "roleState": {
                "resourcePointCurrent": 2,
                "resourcePointCap": 4,
            },
        }
        with patch.object(
            SERVER,
            "current_daily_task_completions",
            return_value=[],
        ), patch.object(
            SERVER,
            "current_important_notices",
            return_value=[],
        ), patch.object(
            SERVER,
            "get_daily_dungeon_count",
            return_value=7,
        ):
            overview = SERVER.current_task_overview(sess)

        mine = next(item for item in overview["resident"] if item["key"] == "mine")
        dungeon = next(item for item in overview["resident"] if item["key"] == "dungeon")
        self.assertEqual(mine["resourcePointCurrent"], 2)
        self.assertEqual(mine["resourcePointCap"], 4)
        self.assertEqual(dungeon["dailyDungeonCount"], 7)

    def test_mine_preparation_scans_small_batch_while_generals_are_busy(self) -> None:
        stop_event = threading.Event()
        task = {
            "taskId": "mine-preparation",
            "type": "auto-mine",
            "sessionId": "mine-preparation-session",
            "config": {"centerX": 91, "centerY": 26},
            "stopEvent": stop_event,
        }
        sess = {
            "sessionId": "mine-preparation-session",
            "roleState": {"resourcePointCurrent": 1, "resourcePointCap": 4},
            "generals": [
                {"id": "g1", "name": "步1", "displayStatus": "战"},
                {"id": "g2", "name": "车1", "displayStatus": "返"},
            ],
        }
        rows = [{
            "generalIds": ["g1", "g2"],
            "resourceType": "一级牧场",
            "scope": "附近",
        }]
        target = {"id": 2, "name": "一级牧场", "x": 93, "y": 28}
        captured = {}
        saved_sessions = SERVER.SESSIONS
        SERVER.SESSIONS = {sess["sessionId"]: sess}

        def fake_search(_sess, opts, **_kwargs):
            captured.update(opts)
            stop_event.set()
            return {
                "targets": [target],
                "requestCount": 2,
                "cacheHitCount": 1,
                "nextCursor": 2,
            }

        try:
            with patch.object(
                SERVER,
                "search_mine_targets",
                side_effect=fake_search,
            ), patch.object(SERVER, "task_log"):
                SERVER.mine_map_preparation_worker(task, sess, rows)
        finally:
            SERVER.SESSIONS = saved_sessions

        self.assertEqual(captured["batchSize"], SERVER.MAP_PREPARATION_BATCH_SIZE)
        self.assertTrue(captured["noncritical"])
        self.assertEqual(task["mapPreparation"]["state"], "ready")
        self.assertEqual(task["mapPreparation"]["candidateCount"], 1)

    @staticmethod
    def target(
        target_id: int = 0x101,
        *,
        kind: str = "二级牧场",
        occupied: bool = False,
    ) -> dict:
        return {
            "id": target_id,
            "idHex": f"{target_id:016x}",
            "typeCode": 5,
            "businessId": 12,
            "kind": kind,
            "protocolKind": "牧场",
            "level": 2,
            "x": 95,
            "y": 30,
            "detailFlag": 0 if occupied else 1,
            "ownerName": "玩家甲" if occupied else "",
            "ownerCountry": "魏" if occupied else "",
            "playerOccupied": occupied,
            "unoccupiedByPlayer": not occupied,
            "amountA": 18000,
            "amountB": 600,
            "description": "牧场资源",
            "valueJ": 7,
            "valueK": 8,
            "troopGroups": [{"typeCode": 7, "count": 90, "levelOrStatus": 2}],
            "defenderCount": 1,
            "defenders": [{"generalName": "守将", "troopCount": 90}],
        }

    def test_business_numbering_keeps_thirteen_slots_and_ten_live_types(self) -> None:
        self.assertEqual(len(SERVER.MINE_RESOURCE_OPTIONS), 10)
        self.assertEqual(
            SERVER.MINE_BUSINESS_IDS,
            {
                "镔铁矿": 1,
                "水晶矿": 2,
                "玄铁矿": 3,
                "浆果园": 6,
                "灵草园": 7,
                "玉露园": 8,
                "银矿": 10,
                "一级牧场": 11,
                "二级牧场": 12,
                "三级牧场": 13,
            },
        )
        self.assertEqual(SERVER.RESOURCE_POINT_NAMES[5], "牧场")

    def test_mine_tables_and_three_hour_ttl_are_used(self) -> None:
        now = 2_000_000_000_000
        with patch.object(SERVER, "now_ms", return_value=now):
            SERVER.record_shared_map_region(
                self.sess,
                "mine",
                x=94,
                y=29,
                http_code=200,
                opcodes=["0x8542"],
                response_data=b"",
                response_payloads=[],
                targets=[self.target()],
            )

        db = SERVER.bandit_db_path()
        with sqlite3.connect(db) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertTrue({
                "mine_targets",
                "mine_regions",
                "mine_target_regions",
                "mine_scan_leases",
            }.issubset(tables))
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM mine_targets").fetchone()[0],
                1,
            )

        with patch.object(
            SERVER,
            "now_ms",
            return_value=now + SERVER.MINE_MAP_TARGET_TTL_MS - 1,
        ):
            matches = SERVER.shared_map_available_mine_targets(
                self.sess,
                resource_types=["二级牧场"],
            )
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["businessId"], 12)

        with patch.object(
            SERVER,
            "now_ms",
            return_value=now + SERVER.MINE_MAP_TARGET_TTL_MS + 1,
        ):
            self.assertEqual(
                SERVER.shared_map_available_mine_targets(
                    self.sess,
                    resource_types=["二级牧场"],
                ),
                [],
            )

    def test_player_occupied_target_is_mapped_but_not_attackable(self) -> None:
        SERVER.record_shared_map_region(
            self.sess,
            "mine",
            x=95,
            y=30,
            http_code=200,
            opcodes=["0x8542"],
            response_data=b"",
            response_payloads=[],
            targets=[self.target(0x102, occupied=True)],
        )
        self.assertEqual(
            SERVER.shared_map_available_mine_targets(
                self.sess,
                resource_types=["二级牧场"],
            ),
            [],
        )
        public = SERVER.public_mine_map(self.sess)
        self.assertEqual(len(public["points"]), 1)
        self.assertTrue(public["points"][0]["playerOccupied"])
        self.assertEqual(public["ttlMs"], 3 * 60 * 60 * 1000)

    def test_recall_payload_matches_capture(self) -> None:
        self.assertEqual(
            SERVER.build_mine_recall_payload(0x8F2785).hex(),
            "010100000000008f278500",
        )
        parsed = SERVER.parse_8526_recall_response(
            bytes.fromhex("00000000008f2785") + b"military",
            0x8F2785,
        )
        self.assertTrue(parsed["success"])

    def test_recall_parser_accepts_current_return_event_response(self) -> None:
        battle_id = 10007604
        payload = bytearray(b"\xff\x00\x00\x00\x00\x00\x00\x00")
        payload += SERVER.utf("【返回】步1,步2返回东方美的封地(东方美基地)")
        payload += struct.pack(">HIQ", 1, 1, battle_id)
        parsed = SERVER.parse_8526_recall_response(bytes(payload), battle_id)
        self.assertTrue(parsed["success"])
        self.assertEqual(parsed["battleId"], battle_id)
        self.assertEqual(parsed["battleIdSource"], "returnEvent")

    def test_preview_parser_and_status_minus_14_message(self) -> None:
        preview = SERVER.parse_8520_mine_preview(
            struct.pack(">iqqBHH", 18, 1000, 2000, 38, 95, 30)
        )
        self.assertTrue(preview["valid"])
        self.assertEqual(preview["winRate"], 38)
        self.assertEqual((preview["x"], preview["y"]), (95, 30))

        rejected = SERVER.parse_8522_dispatch_response(bytes.fromhex("f20000"))
        self.assertEqual(rejected["status"], -14)
        self.assertIn("免战牌", rejected["message"])

    def test_full_loyalty_payload_and_response(self) -> None:
        general_id = 0x01531924
        self.assertEqual(
            SERVER.build_add_loyalty_payload(general_id, 41).hex(),
            "000000000153192400002900",
        )
        payload = struct.pack(
            ">bbqqqqqHHB",
            0,
            0,
            general_id,
            5125,
            998875,
            10,
            20,
            100,
            100,
            0,
        )
        parsed = SERVER.parse_821f_loyalty_response(payload)
        self.assertTrue(parsed["success"])
        self.assertEqual(parsed["actualCost"], 5125)
        self.assertEqual(parsed["copper"], 998875)
        self.assertEqual(parsed["generals"][0]["loyalty"], 100)
        self.assertEqual(parsed["generals"][0]["loyaltyLimit"], 100)

    def test_full_loyalty_only_tops_up_generals_below_limit(self) -> None:
        full = {
            "id": 1,
            "idHex": "0000000000000001",
            "name": "满忠将",
            "loyalty": 100,
            "loyaltyLimit": 100,
        }
        low = {
            "id": 2,
            "idHex": "0000000000000002",
            "name": "低忠将",
            "loyalty": 59,
            "loyaltyLimit": 100,
        }
        sess = {
            "sessionId": "",
            "gameHttp": "http://game",
            "dm": 1,
            "generals": [full, low],
            "roleState": {"copper": 100000},
        }
        response = struct.pack(
            ">bbqqqqqHHB",
            0,
            0,
            2,
            5125,
            94875,
            0,
            0,
            100,
            100,
            0,
        )
        packets = [{"opcode": 0x821F, "payload": response, "len": len(response), "frag": 0}]
        with patch.object(
            SERVER,
            "post_game",
            return_value=(200, response, packets),
        ) as post_game:
            result = SERVER.ensure_mine_generals_full_loyalty(sess, [full, low])
        self.assertTrue(result["success"])
        self.assertEqual(post_game.call_count, 1)
        self.assertEqual(post_game.call_args.args[1][0][0], 0x121F)
        self.assertEqual(post_game.call_args.args[1][0][1], SERVER.build_add_loyalty_payload(2, 41))
        self.assertEqual(low["loyalty"], 100)
        self.assertEqual(sess["roleState"]["copper"], 94875)

    def test_full_loyalty_failure_prevents_dispatch(self) -> None:
        general = {
            "id": 2,
            "idHex": "0000000000000002",
            "name": "低忠将",
            "loyalty": 59,
            "loyaltyLimit": 100,
        }
        sess = {
            "sessionId": "",
            "gameHttp": "http://game",
            "dm": 1,
            "militaryIntel": {"updatedAt": 1},
        }
        failure = struct.pack(
            ">bbqqqqqHHB",
            2,
            0,
            2,
            0,
            100000,
            0,
            0,
            59,
            100,
            0,
        )
        packets = [{"opcode": 0x821F, "payload": failure, "len": len(failure), "frag": 0}]
        with patch.object(
            SERVER,
            "prepare_military_generals",
            return_value=[general],
        ), patch.object(
            SERVER,
            "post_game",
            return_value=(200, failure, packets),
        ) as post_game:
            with self.assertRaisesRegex(RuntimeError, "打矿满忠失败"):
                SERVER.execute_mine(
                    sess,
                    {
                        "confirm": "mine",
                        "generalIds": ["2"],
                        "target": self.target(),
                        "fullLoyalty": True,
                    },
                )
        self.assertEqual(post_game.call_count, 1)
        self.assertEqual(post_game.call_args.args[1][0][0], 0x121F)

    def test_smart_march_speed_selection_and_protocol(self) -> None:
        inventory = [
            {"itemId": 76, "count": 3},
            {"itemId": 77, "count": 2},
            {"itemId": 78, "count": 1},
            {"itemId": 79, "count": 1},
        ]
        self.assertEqual(SERVER.choose_march_speed_items(40, inventory), [])
        self.assertEqual(SERVER.choose_march_speed_items(44 * 60, inventory), [77, 76])
        self.assertEqual(SERVER.choose_march_speed_items(59 * 60, inventory), [78])
        self.assertEqual(SERVER.choose_march_speed_items(179 * 60, inventory), [79])
        self.assertEqual(
            SERVER.build_mine_speed_payload(0x933D6B, 77).hex(),
            "0000000000933d6b004d",
        )
        self.assertTrue(SERVER.parse_8524_mine_speed_response(b"\x00data")["success"])
        self.assertTrue(SERVER.parse_8524_mine_speed_response(b"\xfe")["finished"])

    def test_smart_speed_uses_available_max_when_inventory_is_short(self) -> None:
        inventory = [
            {"itemId": 76, "count": 1},
            {"itemId": 77, "count": 1},
        ]
        self.assertEqual(
            SERVER.choose_march_speed_items(4 * 60 * 60, inventory),
            [77, 76],
        )

    def test_old_mine_speed_setting_is_normalized_to_checkbox_boolean(self) -> None:
        sess = {"generals": []}
        enabled = SERVER.normalize_mine_settings(
            sess,
            {"speed": "中级行军符", "rows": []},
        )
        disabled = SERVER.normalize_mine_settings(
            sess,
            {"speed": "不加速", "rows": []},
        )
        self.assertTrue(enabled["speed"])
        self.assertFalse(disabled["speed"])

    def test_mine_refill_defaults_on_and_can_be_disabled(self) -> None:
        sess = {"generals": []}
        defaulted = SERVER.normalize_mine_settings(sess, {"rows": []})
        disabled = SERVER.normalize_mine_settings(
            sess,
            {"replenishTroops": False, "rows": []},
        )
        self.assertTrue(defaulted["replenishTroops"])
        self.assertFalse(disabled["replenishTroops"])

    def test_mine_march_range_defaults_to_45_and_accepts_only_options(self) -> None:
        sess = {"generals": []}
        self.assertEqual(
            SERVER.normalize_mine_settings(sess, {"rows": []})["maxMarchMinutes"],
            45,
        )
        self.assertEqual(
            SERVER.normalize_mine_settings(
                sess, {"maxMarchMinutes": 90, "rows": []}
            )["maxMarchMinutes"],
            90,
        )
        self.assertEqual(
            SERVER.normalize_mine_settings(
                sess, {"maxMarchMinutes": 75, "rows": []}
            )["maxMarchMinutes"],
            45,
        )

    def test_busy_mine_preflight_is_retryable_but_configuration_errors_are_not(self) -> None:
        self.assertTrue(SERVER.retryable_mine_preflight_error(
            "打矿出征前检查未通过：步1；将领当前不是空闲状态(状态=返，必须=闲)"
        ))
        self.assertTrue(SERVER.retryable_mine_preflight_error(
            "打矿满忠失败：车1；铜钱不足，本轮暂不出征"
        ))
        self.assertTrue(SERVER.retryable_mine_preflight_error(
            "打矿出征前配兵失败：车1；配兵未达到目标：请求599，实际546"
        ))
        self.assertFalse(SERVER.retryable_mine_preflight_error(
            "打矿出征前检查未通过：步1 没有保存的配兵规则"
        ))
        self.assertTrue(SERVER.mine_capacity_full_error(
            "资源点数量已满(4/4)，无法继续打矿"
        ))
        self.assertFalse(SERVER.mine_capacity_full_error(
            "资源点数量不足"
        ))

    def test_execute_mine_requires_preview_before_formal_dispatch(self) -> None:
        sess = {
            "sessionId": "",
            "gameHttp": "http://game",
            "dm": 1,
            "militaryIntel": {"updatedAt": 1},
        }
        general = {
            "id": 0xE09278,
            "idHex": "0000000000e09278",
            "name": "步1",
            "displayStatus": "闲",
            "soldierTypeCode": 8,
            "soldierCount": 100,
        }
        target = self.target()
        empty_packets: list[dict] = []
        with patch.object(
            SERVER,
            "prepare_military_generals",
            return_value=[general],
        ), patch.object(
            SERVER,
            "post_game",
            return_value=(200, b"", empty_packets),
        ) as post_game:
            result = SERVER.execute_mine(
                sess,
                {
                    "confirm": "mine",
                    "generalIds": [str(general["id"])],
                    "target": target,
                },
            )
        self.assertFalse(result["success"])
        self.assertFalse(result["dispatchAccepted"])
        self.assertIn("禁止发送正式出征", result["failureReason"])
        self.assertEqual(post_game.call_count, 1)
        self.assertEqual(post_game.call_args.args[1][0][0], 0x1520)

    def test_execute_mine_rejects_preview_beyond_march_range(self) -> None:
        target = self.target()
        general = {
            "id": 1, "idHex": "0000000000000001", "name": "步1",
            "displayStatus": "闲", "soldierTypeCode": 8, "soldierCount": 100,
        }
        preview = struct.pack(
            ">iqqBHH",
            46 * 60, 0, 0, 100, int(target["x"]), int(target["y"]),
        )
        sess = {
            "sessionId": "", "gameHttp": "http://game", "dm": 1,
            "militaryIntel": {"updatedAt": 1},
        }
        with patch.object(
            SERVER, "prepare_military_generals", return_value=[general]
        ), patch.object(
            SERVER,
            "post_game",
            return_value=(200, b"", [{
                "opcode": 0x8520, "payload": preview, "len": len(preview),
                "payloadHex": preview.hex(), "frag": 0,
            }]),
        ) as post_game:
            result = SERVER.execute_mine(
                sess,
                {
                    "confirm": "mine", "generalIds": ["1"], "target": target,
                    "maxMarchMinutes": 45,
                },
            )
        self.assertFalse(result["success"])
        self.assertIn("超过设定的45分钟", result["failureReason"])
        self.assertEqual(post_game.call_count, 1)

    def test_execute_mine_reuses_generals_prepared_before_target_selection(self) -> None:
        sess = {
            "sessionId": "",
            "gameHttp": "http://game",
            "dm": 1,
            "militaryIntel": {"updatedAt": 1},
        }
        general = {
            "id": 0xE09278,
            "idHex": "0000000000e09278",
            "name": "步1",
            "displayStatus": "闲",
            "soldierTypeCode": 8,
            "soldierCount": 100,
        }
        with patch.object(
            SERVER,
            "prepare_military_generals",
        ) as prepare, patch.object(
            SERVER,
            "post_game",
            return_value=(200, b"", []),
        ):
            SERVER.execute_mine(
                sess,
                {
                    "confirm": "mine",
                    "generalIds": [str(general["id"])],
                    "target": self.target(),
                },
                prepared_generals=[general],
            )

        prepare.assert_not_called()

    def test_execute_mine_counts_success_only_after_garrison_recall_and_idle(self) -> None:
        sess = {
            "sessionId": "",
            "gameHttp": "http://game",
            "dm": 1,
            "militaryIntel": {"updatedAt": 1},
        }
        general = {
            "id": 0xE09278,
            "idHex": "0000000000e09278",
            "name": "步1",
            "displayStatus": "闲",
            "soldierTypeCode": 8,
            "soldierCount": 100,
        }
        target = self.target()
        battle_id = 0x8F2785
        preview_payload = struct.pack(">iqqBHH", 18, 1000, 2000, 38, 95, 30)
        dispatch_payload = b"\x00\x00\x00" + struct.pack(">q", battle_id)
        responses = [
            (
                200,
                b"preview",
                [{"opcode": 0x8520, "payload": preview_payload, "len": 25, "frag": 0}],
            ),
            (
                200,
                b"dispatch",
                [{"opcode": 0x8522, "payload": dispatch_payload, "len": 11, "frag": 0}],
            ),
        ]
        with patch.object(
            SERVER,
            "prepare_military_generals",
            return_value=[general],
        ), patch.object(
            SERVER,
            "post_game",
            side_effect=responses,
        ) as post_game, patch.object(
            SERVER.time,
            "sleep",
        ), patch.object(
            SERVER,
            "wait_for_mine_garrison",
            return_value={"confirmed": True},
        ) as wait_garrison, patch.object(
            SERVER,
            "recall_mine_garrison",
            return_value={"success": True},
        ) as recall, patch.object(
            SERVER,
            "wait_for_mine_generals_idle",
            return_value={"finished": True},
        ) as wait_idle, patch.object(
            SERVER,
            "accelerate_mine_march",
            return_value={"success": False, "message": "测试加速失败后自然行军"},
        ) as accelerate:
            result = SERVER.execute_mine(
                sess,
                {
                    "confirm": "mine",
                    "generalIds": [str(general["id"])],
                    "target": target,
                    "speed": True,
                },
            )
        self.assertTrue(result["dispatchAccepted"])
        self.assertTrue(result["success"])
        self.assertEqual(result["successBattleId"], battle_id)
        self.assertEqual(post_game.call_count, 2)
        accelerate.assert_called_once_with(
            sess,
            battle_id,
            18,
            task=None,
        )
        wait_garrison.assert_called_once()
        recall.assert_called_once_with(sess, battle_id, task=None)
        wait_idle.assert_called_once()

    def test_military_intel_must_confirm_garrison_kind_and_coordinate(self) -> None:
        sess = {"sessionId": "", "gameHttp": "http://game", "dm": 1}
        payload = SERVER.utf("【驻守】步、车驻守在牧场(91,28)")
        packets = [{"opcode": 0x8600, "payload": payload, "len": len(payload), "frag": 0}]
        with patch.object(
            SERVER,
            "post_game",
            return_value=(200, payload, packets),
        ):
            result = SERVER.query_mine_garrison_intel(
                sess,
                {
                    "kind": "一级牧场",
                    "protocolKind": "牧场",
                    "x": 91,
                    "y": 28,
                },
            )
        self.assertTrue(result["confirmed"])
        self.assertEqual(result["opcode"], "0x1600/0x8600")

    def test_parse_live_shaped_8600_garrison_event(self) -> None:
        general_ids = [7032218, 7032236, 7032238, 6843289]
        battle_id = 10007604
        payload = bytearray(SERVER.utf(
            "【驻守】步1,步2,车1,车2驻守在牧场(93,30)"
        ))
        payload += struct.pack(">HIQB", 1, 1, battle_id, len(general_ids))
        for general_id in general_ids:
            payload += struct.pack(">QB", general_id, 0)
        payload += struct.pack(">QB", 0xA51B, 2)
        payload += SERVER.utf("1级牧场")
        payload += struct.pack(">HH", 93, 30)

        events = SERVER.parse_8600_military_events(bytes(payload))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["battleId"], battle_id)
        self.assertEqual(events[0]["generalIds"], general_ids)
        self.assertEqual(events[0]["targetId"], 0xA51B)
        self.assertEqual(events[0]["targetName"], "1级牧场")
        self.assertEqual((events[0]["x"], events[0]["y"]), (93, 30))

    def test_binary_garrison_confirmation_requires_exact_formation(self) -> None:
        sess = {
            "sessionId": "",
            "gameHttp": "http://game",
            "dm": 1,
            "generals": [
                {"id": 11, "idHex": "000000000000000b"},
                {"id": 12, "idHex": "000000000000000c"},
            ],
        }
        payload = bytearray(SERVER.utf("【驻守】甲驻守在牧场(93,30)"))
        payload += struct.pack(">HIQBQBQB", 1, 1, 88, 1, 11, 0, 99, 2)
        payload += SERVER.utf("1级牧场") + struct.pack(">HH", 93, 30)
        packets = [{
            "opcode": 0x8600,
            "payload": bytes(payload),
            "len": len(payload),
            "frag": 0,
        }]
        with patch.object(
            SERVER,
            "post_game",
            return_value=(200, bytes(payload), packets),
        ):
            exact = SERVER.query_mine_garrison_intel(
                sess,
                {"protocolKind": "牧场", "x": 93, "y": 30},
                general_ids=["11"],
            )
            unrelated = SERVER.query_mine_garrison_intel(
                sess,
                {"protocolKind": "牧场", "x": 93, "y": 30},
                general_ids=["12"],
            )
        self.assertTrue(exact["confirmed"])
        self.assertFalse(unrelated["confirmed"])

    def test_known_battle_accepts_partial_survivor_garrison(self) -> None:
        sess = {
            "sessionId": "",
            "gameHttp": "http://game",
            "dm": 1,
            "generals": [
                {"id": gid, "idHex": f"{gid:016x}"}
                for gid in (11, 12, 13, 14)
            ],
        }
        payload = bytearray(SERVER.utf("【驻守】乙、丙、丁驻守在牧场(92,25)"))
        payload += struct.pack(">HIQB", 1, 1, 88, 3)
        for general_id in (12, 13, 14):
            payload += struct.pack(">QB", general_id, 0)
        payload += struct.pack(">QB", 99, 2)
        payload += SERVER.utf("1级牧场") + struct.pack(">HH", 92, 25)
        packets = [{
            "opcode": 0x8600,
            "payload": bytes(payload),
            "len": len(payload),
            "frag": 0,
        }]
        with patch.object(
            SERVER,
            "post_game",
            return_value=(200, bytes(payload), packets),
        ):
            confirmed = SERVER.query_mine_garrison_intel(
                sess,
                {"protocolKind": "牧场", "x": 92, "y": 25},
                general_ids=["11", "12", "13", "14"],
                battle_id=88,
            )
            wrong_battle = SERVER.query_mine_garrison_intel(
                sess,
                {"protocolKind": "牧场", "x": 92, "y": 25},
                general_ids=["11", "12", "13", "14"],
                battle_id=89,
            )

        self.assertTrue(confirmed["confirmed"])
        self.assertFalse(wrong_battle["confirmed"])

    def test_wait_for_garrison_accepts_idle_and_defending_survivors(self) -> None:
        sess = {
            "sessionId": "",
            "militaryIntel": {"updatedAt": 2},
            "generals": [
                {"id": 11, "name": "败退将领", "displayStatus": "闲"},
                {"id": 12, "name": "驻守将领", "displayStatus": "防"},
            ],
        }
        with patch.object(
            SERVER,
            "refresh_military_intel",
        ), patch.object(
            SERVER,
            "query_mine_garrison_intel",
            return_value={"confirmed": True},
        ) as query:
            result = SERVER.wait_for_mine_garrison(
                sess,
                ["11", "12"],
                battle_id=88,
                target={"protocolKind": "牧场", "x": 92, "y": 25},
                max_wait_sec=1,
                updated_after_ms=1,
            )

        self.assertTrue(result["confirmed"])
        self.assertTrue(result["partialGarrison"])
        self.assertEqual([row["id"] for row in result["defendingGenerals"]], [12])
        query.assert_called_once_with(
            sess,
            {"protocolKind": "牧场", "x": 92, "y": 25},
            general_ids=["11", "12"],
            battle_id=88,
        )

    def test_recall_accepts_defender_state_transition_when_payload_shape_varies(self) -> None:
        sess = {
            "sessionId": "",
            "gameHttp": "http://game",
            "dm": 1,
            "pendingMineGarrisons": [{
                "battleId": 88,
                "generalIds": [11, 12],
            }],
            "generals": [
                {"id": 11, "name": "败退将领", "displayStatus": "闲"},
                {"id": 12, "name": "驻守将领", "displayStatus": "防"},
            ],
        }
        mismatched_payload = struct.pack(">q", 99)

        def mark_returning(_sess):
            sess["generals"][1]["displayStatus"] = "返"

        with patch.object(
            SERVER,
            "post_game",
            return_value=(
                200,
                mismatched_payload,
                [{
                    "opcode": 0x8526,
                    "payload": mismatched_payload,
                    "len": len(mismatched_payload),
                    "frag": 0,
                }],
            ),
        ), patch.object(
            SERVER,
            "refresh_generals",
            side_effect=mark_returning,
        ):
            result = SERVER.recall_mine_garrison(sess, 88)

        self.assertTrue(result["success"])
        self.assertEqual(result["successEvidence"], "general-status-transition")
        self.assertIn("防转为返/闲", result["message"])

    def test_pending_mine_garrison_is_part_of_runtime_session_snapshot(self) -> None:
        sess = {"sessionId": "mine-persist", "generals": []}
        with patch.object(SERVER, "persist_runtime_state"):
            SERVER.remember_pending_mine_garrison(
                sess,
                battle_id=123,
                general_ids=[11, 12],
                target={"id": 99, "x": 93, "y": 30},
            )
        snapshot = SERVER.runtime_session_snapshot(sess)
        self.assertEqual(snapshot["pendingMineGarrisons"][0]["battleId"], 123)
        self.assertEqual(
            snapshot["pendingMineGarrisons"][0]["generalIds"],
            [11, 12],
        )

    def test_startup_recovery_adopts_only_exact_orphan_garrison(self) -> None:
        sess = {
            "sessionId": "",
            "generals": [
                {
                    "id": 11,
                    "idHex": "000000000000000b",
                    "name": "步1",
                    "displayStatus": "防",
                },
                {
                    "id": 12,
                    "idHex": "000000000000000c",
                    "name": "车1",
                    "displayStatus": "防",
                },
            ],
        }
        row = {"generalIds": ["11", "12"]}
        event = {
            "battleId": 88,
            "generalIds": [11, 12],
            "targetId": 99,
            "targetIdHex": "0000000000000063",
            "targetName": "1级牧场",
            "x": 93,
            "y": 30,
        }
        with patch.object(
            SERVER,
            "refresh_military_intel",
        ), patch.object(
            SERVER,
            "query_mine_garrison_intel",
            return_value={"confirmed": True, "matchingEvents": [event]},
        ), patch.object(
            SERVER,
            "wait_for_mine_garrison",
            return_value={"confirmed": True},
        ), patch.object(
            SERVER,
            "recall_mine_garrison",
            return_value={"success": True},
        ) as recall, patch.object(
            SERVER,
            "wait_for_mine_generals_idle",
            return_value={"finished": True},
        ):
            recovered = SERVER.recover_pending_mine_garrisons(sess, [row])

        self.assertTrue(recovered[0]["success"])
        recall.assert_called_once_with(sess, 88, task=None)
        self.assertNotIn("pendingMineGarrisons", sess)

    def test_startup_recovery_does_not_recall_unrelated_defenders(self) -> None:
        sess = {
            "sessionId": "",
            "generals": [{
                "id": 12,
                "idHex": "000000000000000c",
                "name": "守城将",
                "displayStatus": "防",
            }],
        }
        with patch.object(
            SERVER,
            "refresh_military_intel",
        ), patch.object(
            SERVER,
            "query_mine_garrison_intel",
            return_value={"confirmed": False, "matchingEvents": []},
        ), patch.object(
            SERVER,
            "recall_mine_garrison",
        ) as recall:
            recovered = SERVER.recover_pending_mine_garrisons(
                sess,
                [{"generalIds": ["12"]}],
            )
        self.assertEqual(recovered, [])
        recall.assert_not_called()

    def test_recovery_adopts_partial_surviving_garrison(self) -> None:
        sess = {
            "sessionId": "",
            "generals": [
                {"id": 11, "name": "灰1", "displayStatus": "闲"},
                {"id": 12, "name": "灰2", "displayStatus": "防"},
                {"id": 13, "name": "骑1", "displayStatus": "闲"},
                {"id": 14, "name": "骑2", "displayStatus": "防"},
                {"id": 15, "name": "骑3", "displayStatus": "闲"},
            ],
        }
        row = {"generalIds": ["11", "12", "13", "14", "15"]}
        event = {
            "battleId": 188,
            "generalIds": [12, 14],
            "targetId": 99,
            "targetIdHex": "0000000000000063",
            "targetName": "一级牧场",
            "x": 91,
            "y": 29,
        }
        with patch.object(
            SERVER, "refresh_military_intel",
        ), patch.object(
            SERVER,
            "query_mine_garrison_intel",
            return_value={"confirmed": True, "matchingEvents": [event]},
        ) as intel, patch.object(
            SERVER, "wait_for_mine_garrison",
            return_value={"confirmed": True},
        ), patch.object(
            SERVER, "recall_mine_garrison",
            return_value={"success": True},
        ) as recall, patch.object(
            SERVER, "wait_for_mine_generals_idle",
            return_value={"finished": True},
        ):
            recovered = SERVER.recover_pending_mine_garrisons(sess, [row])

        self.assertTrue(recovered[0]["success"])
        self.assertEqual({12, 14}, set(intel.call_args.kwargs["general_ids"]))
        recall.assert_called_once_with(sess, 188, task=None)


if __name__ == "__main__":
    unittest.main()
