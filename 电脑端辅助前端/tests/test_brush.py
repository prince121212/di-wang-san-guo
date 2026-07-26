from __future__ import annotations

import importlib.util
import json
import struct
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
CAPTURE_FLOWS = ROOT / "ctf_out" / "passive_pcap_hotspot_20260710_215812" / "live_analyzed"

SPEC = importlib.util.spec_from_file_location("dwpm_server_brush_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


def response_payload(flow_index: int, opcode: int) -> bytes:
    response_file = CAPTURE_FLOWS / f"{flow_index:03d}" / "resp.bin"
    packets = SERVER.parse_response(response_file.read_bytes())
    return next(packet["payload"] for packet in packets if packet.get("opcode") == opcode)


class BrushProtocolTests(unittest.TestCase):
    def test_brush_level_gate_requires_level_30(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "请30级之后再开启刷黄"):
            SERVER.require_brush_level({"role": {"level": 29}})
        SERVER.require_brush_level({"role": {"level": 30}})
        SERVER.require_brush_level({
            "role": {"level": 29},
            "roleState": {"level": 30},
        })

    def test_low_level_brush_save_is_rejected_but_disabling_is_allowed(self) -> None:
        sess = {"role": {"level": 29}}
        with self.assertRaisesRegex(RuntimeError, "请30级之后再开启刷黄"):
            SERVER.require_brush_save_level(
                sess,
                {"autoStart": True},
                brush_scope_saved=True,
            )
        SERVER.require_brush_save_level(
            sess,
            {"autoStart": False},
            brush_scope_saved=True,
        )
        SERVER.require_brush_save_level(
            sess,
            {"autoStart": True},
            brush_scope_saved=False,
        )

    def test_low_level_account_cannot_search_execute_or_start_brush(self) -> None:
        sess = {
            "sessionId": "level-29-brush",
            "role": {"level": 29},
        }
        saved_sessions = SERVER.SESSIONS
        SERVER.SESSIONS = {sess["sessionId"]: sess}
        try:
            with patch.object(SERVER, "post_game") as post_game:
                with self.assertRaisesRegex(RuntimeError, "请30级之后再开启刷黄"):
                    SERVER.search_targets(sess, {})
                with self.assertRaisesRegex(RuntimeError, "请30级之后再开启刷黄"):
                    SERVER.execute_brush(
                        sess,
                        {"confirm": "brush-yellow"},
                    )
                with self.assertRaisesRegex(RuntimeError, "请30级之后再开启刷黄"):
                    SERVER.start_auto_brush({
                        "sessionId": sess["sessionId"],
                        "brush": {"rules": []},
                    })
                post_game.assert_not_called()
        finally:
            SERVER.SESSIONS = saved_sessions

    def test_low_level_account_does_not_start_idle_bandit_thread(self) -> None:
        sid = "level-29-idle-bandit"
        sess = {
            "sessionId": sid,
            "role": {"level": 29},
        }
        SERVER.SESSIONS[sid] = sess
        SERVER.ACCOUNTS[sid] = {
            "started": True,
            "status": "online",
            "stopEvent": threading.Event(),
        }
        try:
            with patch.object(SERVER, "search_targets") as search_targets:
                SERVER.start_idle_bandit_map_thread(sid)
                self.assertNotIn(sid, SERVER.IDLE_BANDIT_THREADS)
                self.assertEqual(
                    sess["idleBanditMap"]["state"],
                    "disabled_level",
                )
                search_targets.assert_not_called()
        finally:
            SERVER.SESSIONS.pop(sid, None)
            SERVER.ACCOUNTS.pop(sid, None)
            SERVER.IDLE_BANDIT_THREADS.pop(sid, None)

    def test_account_idle_bandit_worker_runs_without_a_brush_task(self) -> None:
        stop_event = threading.Event()
        sess = {
            "sessionId": "idle-map-account",
            "role": {"level": 30},
        }
        captured = {}
        saved_sessions = SERVER.SESSIONS
        SERVER.SESSIONS = {sess["sessionId"]: sess}

        def fake_search(_sess, opts, **kwargs):
            captured.update(opts)
            captured["scanState"] = kwargs.get("scan_state")
            stop_event.set()
            return {
                "requestCount": 1,
                "cacheSkipCount": 0,
                "scanLeaseSkipCount": 0,
                "nextCursor": 1,
            }

        try:
            with patch.object(
                SERVER,
                "shared_map_server_key",
                return_value="351",
            ), patch.object(
                SERVER,
                "account_ready_for_idle_bandit_scan",
                return_value=True,
            ), patch.object(
                SERVER,
                "idle_bandit_scan_centers",
                return_value=([(91, 26)], 80),
            ), patch.object(
                SERVER,
                "search_targets",
                side_effect=fake_search,
            ), patch.object(SERVER, "account_log"):
                SERVER.idle_bandit_map_worker(
                    sess["sessionId"],
                    sess,
                    stop_event,
                )
        finally:
            SERVER.SESSIONS = saved_sessions

        self.assertEqual(captured["startX"], 91)
        self.assertEqual(captured["startY"], 26)
        self.assertEqual(captured["batchSize"], 1)
        self.assertTrue(captured["noncritical"])
        self.assertTrue(captured["refreshSharedMap"])
        self.assertEqual(sess["idleBanditMap"]["state"], "updated")

    def test_idle_bandit_scan_yields_to_requests_but_not_long_lived_claims(self) -> None:
        sid = "idle-priority-account"
        SERVER.ACCOUNTS[sid] = {
            "started": True,
            "status": "online",
        }
        try:
            SERVER.ACCOUNT_GAME_REQUEST_ACTIVITY[sid] = {
                "critical": 1,
                "noncritical": 0,
                "lastCriticalFinishedAt": 0.0,
            }
            self.assertFalse(SERVER.account_ready_for_idle_bandit_scan(sid))

            SERVER.ACCOUNT_GAME_REQUEST_ACTIVITY[sid] = {
                "critical": 0,
                "noncritical": 0,
                "lastCriticalFinishedAt": (
                    time.monotonic()
                    - SERVER.IDLE_BANDIT_BUSINESS_QUIET_SEC
                    - 0.1
                ),
            }
            self.assertTrue(SERVER.account_ready_for_idle_bandit_scan(sid))

            SERVER.COMMAND_CENTER_CLAIMS[sid] = {
                "task": {"taskId": "task"},
            }
            self.assertTrue(SERVER.account_ready_for_idle_bandit_scan(sid))
        finally:
            SERVER.ACCOUNTS.pop(sid, None)
            SERVER.ACCOUNT_GAME_REQUEST_ACTIVITY.pop(sid, None)
            SERVER.COMMAND_CENTER_CLAIMS.pop(sid, None)

    def test_brush_preparation_scans_small_batch_while_generals_are_busy(self) -> None:
        stop_event = threading.Event()
        task = {
            "taskId": "brush-preparation",
            "type": "auto-brush-yellow",
            "sessionId": "brush-preparation-session",
            "config": {
                "brush": {
                    "startX": 91,
                    "startY": 26,
                    "scanLimit": 80,
                    "targetKind": "山贼",
                },
            },
            "stopEvent": stop_event,
        }
        sess = {
            "sessionId": "brush-preparation-session",
            "role": {"level": 30},
            "generals": [
                {"id": "g1", "name": "步1", "displayStatus": "征"},
                {"id": "g2", "name": "车1", "displayStatus": "返"},
            ],
        }
        rules = [{
            "generalIds": ["g1", "g2"],
            "level": 7,
            "drops": ["资源"],
            "compositionCode": "0500",
            "compositionFilter": {"maxBow": 5},
        }]
        target = {"id": 1, "name": "7级山贼", "x": 92, "y": 27}
        captured = {}
        saved_sessions = SERVER.SESSIONS
        SERVER.SESSIONS = {sess["sessionId"]: sess}

        def fake_search(_sess, opts, **_kwargs):
            captured.update(opts)
            stop_event.set()
            return {
                "targets": [target],
                "requestCount": 3,
                "cacheHitCount": 1,
                "nextCursor": 3,
            }

        try:
            with patch.object(SERVER, "search_targets", side_effect=fake_search), patch.object(
                SERVER,
                "task_log",
            ):
                SERVER.brush_map_preparation_worker(task, sess, rules)
        finally:
            SERVER.SESSIONS = saved_sessions

        self.assertEqual(captured["batchSize"], SERVER.MAP_PREPARATION_BATCH_SIZE)
        self.assertTrue(captured["noncritical"])
        self.assertEqual(task["mapPreparation"]["state"], "ready")
        self.assertEqual(task["mapPreparation"]["candidateCount"], 1)

    def test_brush_preparation_keeps_scanning_while_a_formation_is_idle(self) -> None:
        stop_event = threading.Event()
        task = {
            "taskId": "brush-preparation-idle",
            "type": "auto-brush-yellow",
            "sessionId": "brush-preparation-idle-session",
            "config": {"brush": {"startX": 91, "startY": 26, "scanLimit": 80}},
            "stopEvent": stop_event,
        }
        sess = {
            "sessionId": "brush-preparation-idle-session",
            "role": {"level": 30},
            "generals": [
                {"id": "g1", "displayStatus": "闲"},
                {"id": "g2", "displayStatus": "闲"},
            ],
        }
        rules = [{
            "generalIds": ["g1", "g2"],
            "level": 7,
            "drops": ["资源"],
            "compositionFilter": {"maxBow": 5},
        }]
        saved_sessions = SERVER.SESSIONS
        SERVER.SESSIONS = {sess["sessionId"]: sess}

        def fake_search(_sess, _opts, **_kwargs):
            stop_event.set()
            return {
                "targets": [],
                "requestCount": 2,
                "cacheHitCount": 0,
                "nextCursor": 2,
            }

        try:
            with patch.object(
                SERVER,
                "search_targets",
                side_effect=fake_search,
            ) as search_targets:
                SERVER.brush_map_preparation_worker(task, sess, rules)
        finally:
            SERVER.SESSIONS = saved_sessions

        search_targets.assert_called_once()
        self.assertEqual(task["mapPreparation"]["state"], "scanning")
        self.assertEqual(task["mapPreparation"]["requestCount"], 2)

    def test_formation_match_requires_exact_type_and_count(self) -> None:
        formation = {"soldierType": "轻骑兵", "soldierCount": 100}
        light_cavalry = SERVER.soldier_type_code("轻骑兵")
        other_type = SERVER.soldier_type_code("近卫兵")

        self.assertIsNone(SERVER.formation_match_reason(
            {"soldierTypeCode": light_cavalry, "soldierCount": 100},
            formation,
        ))
        self.assertIsNotNone(SERVER.formation_match_reason(
            {"soldierTypeCode": light_cavalry, "soldierCount": 101},
            formation,
        ))
        self.assertIsNotNone(SERVER.formation_match_reason(
            {"soldierTypeCode": light_cavalry, "soldierCount": 99},
            formation,
        ))
        self.assertIsNotNone(SERVER.formation_match_reason(
            {"soldierTypeCode": other_type, "soldierCount": 100},
            formation,
        ))
        self.assertTrue(SERVER.is_troop_shortage_message(
            "配兵未达到目标：请求599，服务器实际返回546；当前可用闲兵不足"
        ))
        self.assertFalse(SERVER.is_troop_shortage_message(
            "未收到0x8226配兵响应"
        ))

    def test_pre_dispatch_reassigns_when_current_count_exceeds_saved_count(self) -> None:
        formation = {
            "generalId": "101",
            "soldierType": "轻骑兵",
            "soldierCount": 100,
        }
        light_cavalry = SERVER.soldier_type_code("轻骑兵")
        current_general = {
            "id": 101,
            "name": "骑1",
            "soldierTypeCode": light_cavalry,
            "soldierCount": 101,
        }
        assigned = {
            "success": True,
            "message": "配兵成功",
            "parsed": {
                "assignedSoldierTypeCode": light_cavalry,
                "assignedSoldierCount": 100,
            },
        }
        task = {"taskId": "exact-formation", "config": {}}

        with patch.object(
            SERVER,
            "execute_assign_troops",
            return_value=assigned,
        ) as assign_troops, patch.object(SERVER, "task_log"):
            self.assertTrue(SERVER.perform_pre_dispatch_troops(
                task,
                {},
                formation,
                current_general=current_general,
            ))

        assign_troops.assert_called_once_with(
            {},
            "101",
            "轻骑兵",
            100,
            confirm="assign-troops",
        )

    def test_brush_energy_uses_one_item_and_adds_fifty(self) -> None:
        task = {
            "taskId": "energy-one",
            "config": {"energyThreshold": 20, "autoEnergy": True},
        }
        sess = {"generals": []}
        general = {
            "id": 101,
            "name": "步1",
            "tili": 5,
            "energyReliable": True,
        }
        with patch.object(
            SERVER,
            "refresh_inventory",
            return_value={"items": [{"itemId": 12, "count": 1}]},
        ), patch.object(
            SERVER,
            "execute_use_energy_item",
            return_value={"success": True},
        ) as use_item, patch.object(SERVER, "task_log") as task_log:
            self.assertTrue(SERVER.ensure_brush_energy(task, sess, general))

        use_item.assert_called_once_with(
            sess,
            "101",
            confirm="use-energy-item",
        )
        self.assertEqual(general["tili"], 55)
        self.assertIn("使用活血丹1个", task_log.call_args.args[1])
        self.assertIn("体力+50", task_log.call_args.args[1])

    def test_brush_energy_equal_to_threshold_does_not_use_item(self) -> None:
        task = {
            "taskId": "energy-threshold",
            "config": {"energyThreshold": 20, "autoEnergy": True},
        }
        general = {
            "id": 101,
            "name": "步1",
            "tili": 20,
            "energyReliable": True,
        }
        with patch.object(SERVER, "refresh_inventory") as inventory, \
             patch.object(SERVER, "execute_use_energy_item") as use_item:
            self.assertTrue(SERVER.ensure_brush_energy(task, {}, general))

        inventory.assert_not_called()
        use_item.assert_not_called()
        self.assertEqual(general["tili"], 20)

    def test_two_low_energy_generals_consume_only_two_items_total(self) -> None:
        task = {
            "taskId": "energy-two",
            "config": {"energyThreshold": 20, "autoEnergy": True},
        }
        sess = {"generals": []}
        generals = [
            {"id": 101, "name": "步1", "tili": 5, "energyReliable": True},
            {"id": 102, "name": "车1", "tili": 10, "energyReliable": True},
        ]
        with patch.object(
            SERVER,
            "refresh_inventory",
            side_effect=[
                {"items": [{"itemId": 12, "count": 2}]},
                {"items": [{"itemId": 12, "count": 1}]},
            ],
        ), patch.object(
            SERVER,
            "execute_use_energy_item",
            return_value={"success": True},
        ) as use_item, patch.object(SERVER, "task_log"):
            results = [
                SERVER.ensure_brush_energy(task, sess, general)
                for general in generals
            ]

        self.assertEqual(results, [True, True])
        self.assertEqual(use_item.call_count, 2)
        self.assertEqual([general["tili"] for general in generals], [55, 60])

    def test_settings_change_summary_describes_added_brush_row_and_domestic_toggle(self) -> None:
        sess = {
            "generals": [
                {"id": 1, "name": "步1"},
                {"id": 2, "name": "弓1"},
                {"id": 3, "name": "骑1"},
            ],
        }
        base_rules = [
            {"enabled": True, "sourceRowIndex": index, "generalIds": [str(index + 1)],
             "level": 6, "compositionCode": "0500", "drops": ["装备"]}
            for index in range(2)
        ]
        old = {"brush": {"rules": base_rules}, "domestic": {"enabled": True}}
        added = {
            "enabled": True, "sourceRowIndex": 2, "generalIds": ["1", "2", "3"],
            "level": 6, "compositionCode": "0500", "drops": ["装备", "资源"],
        }
        new = {"brush": {"rules": base_rules + [added]}, "domestic": {"enabled": False}}
        summary = SERVER.settings_change_summary(sess, old, new)
        self.assertIn(
            "开启刷黄-第3编队-将领步1、将领弓1、将领骑1｜目标6级山贼0500掉落装备、资源皆可",
            summary,
        )
        self.assertIn("关闭自动内政", summary)
        self.assertEqual(SERVER.settings_change_summary(sess, new, new), "保存设置：配置无变化")

    def test_drop_filter_is_or_and_selecting_all_means_unrestricted(self) -> None:
        equipment_target = {"resource": "很多资源,有装备,"}
        treasure_target = {"resource": "很多资源,一些宝物,"}
        unknown_target = {"resource": "特殊奖励"}

        self.assertTrue(SERVER.match_drop(equipment_target, ["装备"]))
        self.assertFalse(SERVER.match_drop(treasure_target, ["装备"]))
        self.assertTrue(SERVER.match_drop(
            treasure_target,
            ["装备", "宝物"],
        ))
        self.assertTrue(SERVER.match_drop(
            unknown_target,
            ["宝物", "资源", "装备", "宝箱"],
        ))

    def test_8540_uses_real_guard_composition_for_0500_filter(self) -> None:
        payload = bytearray(struct.pack(">HHB", 200, 200, 1))
        payload += struct.pack(">q", 2457451) + SERVER.utf("5级山贼")
        payload += struct.pack(">HBHH", 0, 5, 98, 33)
        payload += SERVER.utf("很多资源,") + struct.pack(">ii", 295, 731)
        payload += b"\x01" + struct.pack(">I", 1054) + b"\x02"
        for index, name in enumerate(("慎逸齐", "蔺尚")):
            payload += SERVER.utf(name)
            payload += struct.pack(">HHBBBi", 10, 733 + index, 4, 1, 6, 739 + index * 120)

        targets = SERVER.parse_8540_targets(bytes(payload))

        self.assertEqual(len(targets), 1)
        self.assertEqual((targets[0]["x"], targets[0]["y"]), (98, 33))
        self.assertEqual(targets[0]["compositionCode"], "0200")
        self.assertEqual(targets[0]["lootIds"], [1054])
        self.assertEqual(targets[0]["dropCategories"], ["资源"])
        self.assertTrue(SERVER.match_composition(targets[0], {
            "maxFoot": 0, "maxBow": 5, "maxCavalry": 0, "maxChariot": 0,
        }))
        self.assertFalse(SERVER.match_composition(targets[0], {
            "maxFoot": 0, "maxBow": 1, "maxCavalry": 0, "maxChariot": 0,
        }))
        self.assertFalse(SERVER.match_composition(
            {"composition": None},
            {"maxFoot": 0, "maxBow": 5, "maxCavalry": 0, "maxChariot": 0},
        ))

    def test_parse_8542_resource_points_keeps_structured_fields(self) -> None:
        payload = bytearray(struct.pack(">HHB", 60, 24, 2))
        payload += struct.pack(">qBBHHB", 0x101, 0x01, 3, 61, 25, 0)
        payload += SERVER.utf("玩家甲")
        payload += SERVER.utf("魏")
        payload += struct.pack(">ii", 50000, 1200)
        payload += SERVER.utf("每小时产出")
        payload += struct.pack(">ii", 7, 8)
        payload += b"\x01" + struct.pack(">BHB", 7, 90, 2)
        payload += b"\x01" + SERVER.utf("守将甲")
        payload += struct.pack(">HHBBBi", 11, 12, 1, 7, 35, 90)
        payload += struct.pack(">qBBHHB", 0x102, 0x05, 2, 64, 30, 1)
        payload += struct.pack(">ii", 18000, 600)
        payload += SERVER.utf("二级牧场")
        payload += struct.pack(">ii", 9, 10)
        payload += b"\x00\x00"

        resources = SERVER.parse_8542_resources(bytes(payload))

        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]["kind"], "镔铁矿")
        self.assertEqual(resources[0]["level"], 3)
        self.assertEqual((resources[0]["x"], resources[0]["y"]), (61, 25))
        self.assertEqual(resources[0]["storage"], 50000)
        self.assertEqual(resources[0]["productionPerHour"], 1200)
        self.assertEqual(resources[0]["defenderCount"], 1)
        self.assertFalse(resources[0]["isEmpty"])
        self.assertEqual(resources[0]["defenders"][0]["generalName"], "守将甲")
        self.assertEqual(resources[0]["ownerName"], "玩家甲")
        self.assertTrue(resources[0]["playerOccupied"])
        self.assertEqual(resources[1]["kind"], "二级牧场")
        self.assertEqual(resources[1]["amountA"], 18000)
        self.assertFalse(resources[1]["playerOccupied"])
        self.assertTrue(resources[1]["isEmpty"])
        self.assertEqual(resources[1]["idHex"], "0000000000000102")

    def test_build_mine_payloads_use_action_type_two(self) -> None:
        prepare, expedition = SERVER.build_mine_payloads(
            ["0000000000e09278", "0000000000f7f0bf"],
            0x101,
        )

        expected_head = (
            b"\x02\x02"
            + struct.pack(">q", 0xE09278)
            + struct.pack(">q", 0xF7F0BF)
            + struct.pack(">q", 0x101)
        )
        self.assertEqual(prepare, expected_head)
        self.assertEqual(
            expedition,
            expected_head + struct.pack(">q", -1) + b"\x00\x00\x00",
        )

    def test_shared_mine_map_filters_and_reserves_targets(self) -> None:
        original_dir = SERVER.SHARED_MAP_DIR
        original_maps = SERVER.SHARED_MAPS
        sess = {
            "sessionId": "mine-a",
            "username": "1608601",
            "area": {"areaId": 351, "areaName": "351区"},
        }
        target = {
            "id": 0x101,
            "idHex": "0000000000000101",
            "kind": "镔铁矿",
            "protocolKind": "镔铁矿",
            "typeCode": 1,
            "businessId": 1,
            "level": 3,
            "x": 61,
            "y": 25,
            "isEmpty": True,
            "defenderCount": 0,
        }
        try:
            with tempfile.TemporaryDirectory() as tmp:
                SERVER.SHARED_MAP_DIR = Path(tmp)
                SERVER.SHARED_MAPS = {}
                SERVER.record_shared_map_region(
                    sess,
                    "mine",
                    x=60,
                    y=24,
                    http_code=200,
                    opcodes=["0x8542"],
                    response_data=b"response",
                    response_payloads=[b"payload"],
                    targets=[target],
                )
                matches = SERVER.shared_map_available_mine_targets(
                    sess,
                    resource_types=["镔铁矿"],
                    levels=[3],
                    only_empty=True,
                )
                self.assertEqual(len(matches), 1)
                self.assertTrue(SERVER.reserve_shared_map_target(
                    sess,
                    "mine",
                    matches[0],
                    owner="mine-a",
                    task_id="task-a",
                ))
                self.assertEqual(
                    SERVER.shared_map_available_mine_targets(
                        sess,
                        resource_types=["镔铁矿"],
                    ),
                    [],
                )
        finally:
            SERVER.SHARED_MAP_DIR = original_dir
            SERVER.SHARED_MAPS = original_maps

    def test_inventory_parser_recovers_items_and_equipment(self) -> None:
        inventory = SERVER.parse_8104_inventory(response_payload(30, 0x8104))
        self.assertNotIn("parseError", inventory)
        self.assertEqual(inventory["itemCount"], 26)
        self.assertEqual(inventory["equipmentCount"], 7)
        items = {item["name"]: item["count"] for item in inventory["items"]}
        self.assertEqual(items["山贼头巾"], 50)
        self.assertEqual(items["活血丹"], 2)
        equipment = {item["instanceId"]: item for item in inventory["equipment"]}
        self.assertEqual(equipment[0xC95F8]["name"], "短剑")
        self.assertEqual(equipment[0xC95F8]["level"], 1)
        self.assertEqual(equipment[0xC95F8]["qualityName"], "良好")
        self.assertEqual(equipment[0xC9349]["name"], "赤金斧")
        self.assertEqual(equipment[0xC9349]["qualityName"], "优秀")
        self.assertEqual(equipment[0xCA4AE]["name"], "混元锤")

    def test_energy_payload_and_response_use_no_success_utf(self) -> None:
        payload = SERVER.build_use_general_item_payload(0xF7F0BF, 12, 1)
        self.assertEqual(payload.hex(), "0000000000f7f0bf000c0001")
        response = response_payload(60, 0x8218)
        self.assertEqual(response[0], 0)
        inventory = SERVER.parse_8104_inventory(response[1:])
        items = {item["name"]: item["count"] for item in inventory["items"]}
        self.assertEqual(items["活血丹"], 1)

    def test_food_to_copper_payload_and_response(self) -> None:
        payload = SERVER.build_resource_exchange_payload(1, 10000)
        self.assertEqual(payload.hex(), "010000000000002710")
        result = SERVER.parse_resource_exchange_response(response_payload(67, 0x8152))
        self.assertTrue(result["success"])
        self.assertEqual(result["copper"], 235201)
        self.assertEqual(result["food"], 287290)

    def test_delete_all_mail_payload_and_response(self) -> None:
        self.assertEqual(
            SERVER.build_delete_all_mail_payload().hex(),
            "0001ffffffffffffffff",
        )
        result = SERVER.parse_delete_mail_response(response_payload(52, 0x8116))
        self.assertTrue(result["success"])
        self.assertEqual(result["remaining"], 0)

    def test_discard_item_and_equipment_payloads(self) -> None:
        self.assertEqual(
            SERVER.build_discard_inventory_payload(0, 4, 50).hex(),
            "00000000000000000400000032ffffffffffffffff",
        )
        self.assertEqual(
            SERVER.build_discard_inventory_payload(1, 0xC95F8, 1).hex(),
            "0100000000000c95f800000001ffffffffffffffff",
        )

    def test_brush_payload_matches_captured_action_type_three(self) -> None:
        generals = [
            "0000000000e09278",
            "0000000000f7f0bf",
            "0000000000df3781",
        ]
        prepare, expedition = SERVER.build_brush_payloads(generals, "00000000005e3656")
        self.assertEqual(
            prepare,
            "00000000000000000022152003030000000000e092780000000000f7f0bf"
            "0000000000df378100000000005e3656",
        )
        self.assertEqual(
            expedition,
            "0000000000000000002d152203030000000000e092780000000000f7f0bf"
            "0000000000df378100000000005e3656ffffffffffffffff000000",
        )

    def test_dispatch_requires_positive_battle_id(self) -> None:
        captured = SERVER.parse_8522_dispatch_response(response_payload(75, 0x8522))
        self.assertTrue(captured["statusOk"])
        self.assertTrue(captured["success"])
        self.assertEqual(captured["battleId"], 0x6C42D1)

        no_battle = SERVER.parse_8522_dispatch_response(b"\x00\x00\x00" + struct.pack(">q", 0))
        self.assertTrue(no_battle["statusOk"])
        self.assertFalse(no_battle["success"])
        self.assertIn("battleId", no_battle["message"])

    def test_execute_brush_sends_only_canonical_action_type_three(self) -> None:
        calls = []
        original_post_game = SERVER.post_game
        original_report_dir = SERVER.REPORT_DIR
        original_sleep = SERVER.time.sleep

        def fake_post_game(_url, commands, _dm, account_id=None):
            opcode, payload = commands[0]
            calls.append((opcode, payload))
            if opcode == 0x1522:
                response = b"\x00\x00\x00" + struct.pack(">q", 0x6C42D1)
                return 200, response, [{
                    "opcode": 0x8522,
                    "len": len(response),
                    "frag": 0,
                    "payload": response,
                }]
            return 200, b"", []

        try:
            with tempfile.TemporaryDirectory() as tmp:
                SERVER.post_game = fake_post_game
                SERVER.REPORT_DIR = Path(tmp)
                SERVER.time.sleep = lambda _seconds: None
                result = SERVER.execute_brush(
                    {
                        "sessionId": "test",
                        "gameHttp": "http://example.invalid",
                        "dm": 1,
                        "role": {"roleId": 1, "level": 30},
                        "area": {"areaId": 351},
                        "generals": [{
                            "id": 0xE09278,
                            "idHex": "0000000000e09278",
                            "name": "步手1号",
                        }],
                    },
                    {
                        "confirm": "brush-yellow",
                        "generalId": str(0xE09278),
                        "target": {
                            "id": 0x5E3656,
                            "idHex": "00000000005e3656",
                            "x": 150,
                            "y": 44,
                            "name": "5级山贼",
                        },
                    },
                )
        finally:
            SERVER.post_game = original_post_game
            SERVER.REPORT_DIR = original_report_dir
            SERVER.time.sleep = original_sleep
        self.assertTrue(result["success"])
        self.assertEqual(result["successVariant"], 0)
        self.assertEqual([opcode for opcode, _payload in calls], [0x1520, 0x1522])
        self.assertEqual(calls[0][1][0], 3)
        self.assertEqual(calls[1][1][0], 3)

    def test_execute_brush_encodes_all_generals_in_one_formation(self) -> None:
        calls = []
        original_post_game = SERVER.post_game
        original_report_dir = SERVER.REPORT_DIR
        original_sleep = SERVER.time.sleep

        def fake_post_game(_url, commands, _dm, account_id=None):
            opcode, payload = commands[0]
            calls.append((opcode, payload))
            if opcode == 0x1522:
                response = b"\x00\x00\x00" + struct.pack(">q", 0x6C42D1)
                return 200, response, [{
                    "opcode": 0x8522,
                    "len": len(response),
                    "frag": 0,
                    "payload": response,
                }]
            return 200, b"", []

        general_ids = [0xE09278, 0xF7F0BF]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                SERVER.post_game = fake_post_game
                SERVER.REPORT_DIR = Path(tmp)
                SERVER.time.sleep = lambda _seconds: None
                result = SERVER.execute_brush(
                    {
                        "sessionId": "test",
                        "gameHttp": "http://example.invalid",
                        "dm": 1,
                        "role": {"roleId": 1, "level": 30},
                        "area": {"areaId": 351},
                        "generals": [
                            {
                                "id": general_id,
                                "idHex": f"{general_id:016x}",
                                "name": f"将领{index}",
                            }
                            for index, general_id in enumerate(general_ids, 1)
                        ],
                    },
                    {
                        "confirm": "brush-yellow",
                        "generalIds": [str(general_id) for general_id in general_ids],
                        "target": {
                            "id": 0x5E3656,
                            "idHex": "00000000005e3656",
                            "x": 150,
                            "y": 44,
                            "name": "5级山贼",
                        },
                    },
                )
        finally:
            SERVER.post_game = original_post_game
            SERVER.REPORT_DIR = original_report_dir
            SERVER.time.sleep = original_sleep
        self.assertTrue(result["success"])
        self.assertEqual([general["id"] for general in result["generals"]], general_ids)
        self.assertEqual([opcode for opcode, _payload in calls], [0x1520, 0x1522])
        for _opcode, payload in calls:
            self.assertEqual(payload[0], 3)
            self.assertEqual(payload[1], 2)
            self.assertEqual(
                payload[2:18],
                b"".join(struct.pack(">q", general_id) for general_id in general_ids),
            )

    def test_settlement_matches_current_target_and_ignores_baseline(self) -> None:
        old = "剿灭5级山贼(150,44)胜利！旧战报"
        current = "剿灭5级山贼(150,44)胜利！铜钱+277、粮食+649"
        sess = {
            "militaryIntel": {
                "updatedAt": 123,
                "events": [{"text": old}, {"text": current}],
            }
        }
        result = SERVER.brush_settlement_from_events(
            sess,
            {"x": 150, "y": 44},
            baseline_texts={old},
        )
        self.assertTrue(result["confirmed"])
        self.assertTrue(result["won"])
        self.assertEqual(result["text"], current)

        mismatch = SERVER.brush_settlement_from_events(
            sess,
            {"x": 149, "y": 44},
            baseline_texts=set(),
        )
        self.assertFalse(mismatch["confirmed"])

    def test_settlement_requires_fresh_busy_then_idle_transition(self) -> None:
        sess = {
            "militaryIntel": {"updatedAt": 100},
            "generals": [
                {
                    "id": "g1",
                    "displayStatus": "闲",
                    "a110StatusKnown": True,
                },
                {
                    "id": "g2",
                    "displayStatus": "闲",
                    "a110StatusKnown": True,
                },
            ],
        }
        observation = {
            "generalIds": ["g1", "g2"],
            "lastIntelUpdatedAt": 100,
            "sawBusy": False,
        }

        stale = SERVER.observe_brush_settlement(sess, observation)
        self.assertFalse(stale["fresh"])
        self.assertFalse(stale["confirmed"])

        sess["militaryIntel"]["updatedAt"] = 101
        still_idle = SERVER.observe_brush_settlement(sess, observation)
        self.assertTrue(still_idle["fresh"])
        self.assertFalse(still_idle["sawBusy"])
        self.assertFalse(still_idle["confirmed"])

        sess["militaryIntel"]["updatedAt"] = 102
        for general in sess["generals"]:
            general["displayStatus"] = "征"
        busy = SERVER.observe_brush_settlement(sess, observation)
        self.assertTrue(busy["sawBusy"])
        self.assertFalse(busy["confirmed"])

        sess["militaryIntel"]["updatedAt"] = 103
        for general in sess["generals"]:
            general["displayStatus"] = "闲"
            general["a110StatusKnown"] = False
        returned = SERVER.observe_brush_settlement(sess, observation)
        self.assertTrue(returned["confirmed"])
        self.assertEqual(returned["completedBy"], "将领均已经历出征状态并重新回闲")

    def test_dispatch_selection_skips_generals_already_in_flight(self) -> None:
        task = {
            "taskId": "brush-inflight-select",
            "sessionId": "session-1",
            "brushInFlight": {
                "0": {"generalIds": ["g1"]},
            },
        }
        sess = {
            "generals": [
                {"id": "g1", "displayStatus": "闲"},
                {"id": "g2", "displayStatus": "闲"},
            ],
        }
        rules = [
            {"generalIds": ["g1"]},
            {"generalIds": ["g2"]},
        ]
        with patch.object(SERVER, "_command_center_blockers", return_value=[]):
            selected = SERVER.select_dispatchable_brush_rule_index(
                task,
                sess,
                rules,
                0,
            )
        self.assertEqual(selected, 1)

    def test_dispatch_selection_allows_unprepared_rule_before_target_exists(self) -> None:
        task = {
            "taskId": "brush-candidate-select",
            "sessionId": "session-1",
        }
        sess = {
            "generals": [
                {"id": "g1", "displayStatus": "闲"},
                {"id": "g2", "displayStatus": "闲"},
            ],
        }
        rules = [
            {"generalIds": ["g1"]},
            {"generalIds": ["g2"]},
        ]
        with patch.object(
            SERVER,
            "_command_center_blockers",
            return_value=[],
        ), patch.object(
            SERVER,
            "brush_rule_has_prepared_target",
            return_value=False,
        ) as has_target:
            selected = SERVER.select_dispatchable_brush_rule_index(
                task,
                sess,
                rules,
                0,
            )
        self.assertEqual(selected, 0)
        self.assertEqual(has_target.call_count, 0)

    def test_wait_state_detects_stale_busy_generals_after_network_recovery(self) -> None:
        sess = {
            "generals": [
                {"id": "g1", "name": "步1", "displayStatus": "战"},
                {"id": "g2", "name": "车1", "displayStatus": "闲"},
            ],
        }
        waiting, general_ids, summary = SERVER.brush_cached_general_wait_state(
            sess,
            [{"generalIds": ["g1", "g2"]}],
        )

        self.assertTrue(waiting)
        self.assertEqual(general_ids, ["g1", "g2"])
        self.assertEqual(summary, "步1=战，车1=闲")

        sess["generals"][0]["displayStatus"] = "闲"
        waiting, _, summary = SERVER.brush_cached_general_wait_state(
            sess,
            [{"generalIds": ["g1", "g2"]}],
        )
        self.assertFalse(waiting)
        self.assertEqual(summary, "步1=闲，车1=闲")

    def test_inflight_maintenance_completes_without_blocking_other_flights(self) -> None:
        stop_event = threading.Event()
        task = {
            "taskId": "brush-inflight-maintenance",
            "type": "auto-brush-yellow",
            "sessionId": "session-1",
            "status": "running",
            "cycle": 0,
            "config": {"sessionId": "session-1", "dailyLimit": 500},
            "stopEvent": stop_event,
            "brushInFlight": {
                "0": {
                    "cycleNo": 1,
                    "ruleIndex": 0,
                    "generalIds": ["g1"],
                    "formations": [{"generalId": "g1"}],
                    "lastIntelUpdatedAt": 100,
                    "sawBusy": True,
                    "deadlineAt": SERVER.now_ms() + 60_000,
                },
                "1": {
                    "cycleNo": 2,
                    "ruleIndex": 1,
                    "generalIds": ["g2"],
                    "formations": [{"generalId": "g2"}],
                    "lastIntelUpdatedAt": 101,
                    "sawBusy": True,
                    "deadlineAt": SERVER.now_ms() + 60_000,
                },
            },
        }
        sess = {
            "militaryIntel": {"updatedAt": 101},
            "generals": [
                {"id": "g1", "displayStatus": "闲", "a110StatusKnown": False},
                {"id": "g2", "displayStatus": "征", "a110StatusKnown": True},
            ],
        }
        with patch.object(
            SERVER,
            "_command_center_blockers",
            return_value=[],
        ), patch.object(
            SERVER,
            "command_center_acquire",
            return_value=True,
        ) as acquire, patch.object(
            SERVER,
            "command_center_release",
        ) as release, patch.object(
            SERVER,
            "perform_brush_group_maintenance",
            return_value=True,
        ) as maintenance, patch.object(
            SERVER,
            "get_daily_brush_count",
            return_value=2,
        ), patch.object(SERVER, "task_log"):
            self.assertTrue(SERVER.process_brush_inflight(task, sess))

        self.assertNotIn("0", task["brushInFlight"])
        self.assertIn("1", task["brushInFlight"])
        self.assertEqual(task["cycle"], 1)
        acquire.assert_called_once_with(task, ["g1"])
        maintenance.assert_called_once_with(
            task,
            sess,
            [{"generalId": "g1"}],
        )
        release.assert_called_once()

    def test_heal_all_success_record_does_not_expose_protocol_sentinels(self) -> None:
        self.assertEqual(
            SERVER.success_action_from_log(
                "治疗伤兵完成：封地=利萍丰基地(205) 范围=全部伤兵；治疗成功"
            ),
            ("治疗", "利萍丰基地(205) 全部伤兵"),
        )
        self.assertEqual(
            SERVER.success_action_from_log(
                "治疗伤兵完成：fief=205 兵种=0 数量=-1；治疗成功"
            ),
            ("治疗", "封地205 全部伤兵"),
        )

    def test_group_maintenance_heals_same_fief_only_once(self) -> None:
        task = {
            "taskId": "same-fief-heal",
            "status": "running",
            "config": {
                "sessionId": "same-fief-session",
                "healWounded": True,
                "healAllIfCountUnknown": True,
            },
        }
        sess = {
            "sessionId": "same-fief-session",
            "generals": [
                {"id": "g1", "fiefId": 205, "fiefName": "利萍丰基地"},
                {"id": "g2", "fiefId": 205, "fiefName": "利萍丰基地"},
                {"id": "g3", "fiefId": 205, "fiefName": "利萍丰基地"},
            ],
        }
        formations = [
            {"generalId": "g1", "soldierCount": 0},
            {"generalId": "g2", "soldierCount": 0},
            {"generalId": "g3", "soldierCount": 0},
        ]
        heal_result = {
            "success": True,
            "message": "治疗成功",
            "plan": {
                "fiefId": 205,
                "healAll": True,
                "soldierTypeCode": 0,
                "woundedCount": -1,
            },
        }

        with patch.object(
            SERVER,
            "account_state_block_reason",
            return_value=None,
        ), patch.object(
            SERVER,
            "execute_heal_wounded",
            return_value=heal_result,
        ) as heal, patch.object(SERVER, "task_log") as task_log:
            self.assertTrue(SERVER.perform_brush_group_maintenance(
                task,
                sess,
                formations,
            ))

        self.assertEqual(heal.call_count, 1)
        success_messages = [
            call.args[1]
            for call in task_log.call_args_list
            if "治疗伤兵完成" in call.args[1]
        ]
        self.assertEqual(
            success_messages,
            ["治疗伤兵完成：封地=利萍丰基地(205) 范围=全部伤兵；治疗成功"],
        )

    def test_brush_scan_starts_at_center_and_expands_by_distance(self) -> None:
        coords = SERVER.brush_scan_coordinates(100, 30, 80)
        self.assertEqual(len(coords), 80)
        self.assertEqual(coords[0], (102, 30))
        distances = [(x - 100) ** 2 + (y - 30) ** 2 for x, y in coords]
        self.assertEqual(distances, sorted(distances))
        self.assertTrue(all(0 <= x <= 186 and 0 <= y <= 66 for x, y in coords))
        self.assertTrue(all(x % 6 == 0 and y % 6 == 0 for x, y in coords))

    def test_different_centers_share_one_canonical_scan_lattice(self) -> None:
        first = set(SERVER.brush_scan_coordinates(91, 26, 384))
        second = set(SERVER.brush_scan_coordinates(148, 44, 384))
        third = set(SERVER.brush_scan_coordinates(171, 8, 384))
        self.assertEqual(len(first), 384)
        self.assertEqual(first, second)
        self.assertEqual(first, third)

    def test_target_search_scans_configured_batch_before_cooldown(self) -> None:
        calls = []
        waits = []
        original_post_game = SERVER.post_game
        original_last_request_at = SERVER.BRUSH_SCAN_LAST_REQUEST_AT

        class FakeStopEvent:
            def is_set(self):
                return False

            def wait(self, seconds):
                waits.append(seconds)
                return False

        def fake_post_game(_url, commands, _dm, account_id=None):
            calls.append((commands[0][0], account_id))
            return 200, b"", []

        sess = {
            "sessionId": "incremental-search",
            "gameHttp": "http://example.invalid",
            "dm": 1,
            "role": {"roleId": 1, "level": 30},
        }
        opts = {
            "startX": 100,
            "startY": 30,
            "scanLimit": 80,
            "targetKind": "山贼",
            "level": 1,
        }
        state = {}
        stop_event = FakeStopEvent()
        try:
            SERVER.post_game = fake_post_game
            SERVER.BRUSH_SCAN_LAST_REQUEST_AT = 0.0
            result = SERVER.search_targets(
                sess,
                opts,
                scan_state=state,
                stop_event=stop_event,
            )
            self.assertEqual(
                result["requestCount"],
                SERVER.BRUSH_SCAN_BATCH_SIZE,
            )
            self.assertEqual(result["matchedCount"], 0)
            cached_result = SERVER.search_targets(
                sess,
                opts,
                scan_state=state,
                stop_event=stop_event,
            )
        finally:
            SERVER.post_game = original_post_game
            SERVER.BRUSH_SCAN_LAST_REQUEST_AT = original_last_request_at

        self.assertEqual(result["nextCursor"], 0)
        self.assertEqual(len(calls), 80)
        self.assertEqual(waits, [])
        self.assertEqual(cached_result["requestCount"], 0)
        self.assertEqual(cached_result["cacheSkipCount"], 80)
        self.assertEqual(len(calls), 80)

    def test_target_search_reuses_and_invalidates_cached_target(self) -> None:
        calls = []
        original_post_game = SERVER.post_game
        original_parser = SERVER.parse_8540_targets
        original_last_request_at = SERVER.BRUSH_SCAN_LAST_REQUEST_AT

        class FakeStopEvent:
            def wait(self, _seconds):
                return False

        def fake_post_game(_url, _commands, _dm, account_id=None):
            calls.append(account_id)
            return 200, b"", [{
                "opcode": 0x8540,
                "payload": b"cached-target",
            }]

        try:
            SERVER.post_game = fake_post_game
            SERVER.BRUSH_SCAN_LAST_REQUEST_AT = 0.0
            SERVER.parse_8540_targets = lambda _payload: [{
                "id": 99,
                "idHex": "0000000000000063",
                "x": 100,
                "y": 30,
                "kind": "山贼",
                "level": 1,
                "name": "1级山贼",
            }]
            sess = {
                "sessionId": "cached-search",
                "gameHttp": "http://example.invalid",
                "dm": 1,
                "role": {"roleId": 1, "level": 30},
            }
            opts = {
                "startX": 100,
                "startY": 30,
                "scanLimit": 80,
                "targetKind": "山贼",
                "level": 1,
            }
            state = {}
            stop_event = FakeStopEvent()
            first = SERVER.search_targets(
                sess,
                opts,
                scan_state=state,
                stop_event=stop_event,
            )
            second = SERVER.search_targets(
                sess,
                opts,
                scan_state=state,
                stop_event=stop_event,
            )
            removed = SERVER.invalidate_brush_scan_cache(state, second["targets"])
            third = SERVER.search_targets(
                sess,
                opts,
                scan_state=state,
                stop_event=stop_event,
            )
        finally:
            SERVER.post_game = original_post_game
            SERVER.parse_8540_targets = original_parser
            SERVER.BRUSH_SCAN_LAST_REQUEST_AT = original_last_request_at

        self.assertEqual(first["requestCount"], 1)
        self.assertEqual(second["requestCount"], 0)
        self.assertEqual(second["cacheHitCount"], 1)
        self.assertTrue(second["targets"][0]["fromCache"])
        self.assertEqual(removed, 1)
        self.assertEqual(third["requestCount"], 1)
        self.assertEqual(len(calls), 2)

    def test_shared_target_key_normalizes_live_and_sqlite_id_width(self) -> None:
        live_target = {
            "id": int("86b560", 16),
            "idHex": "00000086b560",
        }
        sqlite_target = {
            "id": int("86b560", 16),
            "idHex": "000000000086b560",
        }

        self.assertEqual(
            SERVER.shared_map_target_key(live_target),
            SERVER.shared_map_target_key(sqlite_target),
        )
        self.assertEqual(
            SERVER.shared_map_target_key(live_target),
            "id:000000000086b560",
        )

    def test_revalidation_matches_live_12_digit_id_to_sqlite_16_digit_id(self) -> None:
        cached_target = {
            "id": int("86b560", 16),
            "idHex": "000000000086b560",
            "sharedTargetKey": "id:000000000086b560",
            "scanCoord": [132, 42],
            "x": 136,
            "y": 45,
        }
        live_target = {
            "id": int("86b560", 16),
            "idHex": "00000086b560",
            "x": 136,
            "y": 45,
        }
        sess = {
            "sessionId": "revalidation-id-width",
            "gameHttp": "http://example.invalid",
            "dm": 1,
            "role": {"level": 30},
        }

        with patch.object(
            SERVER,
            "shared_map_server_key",
            return_value="区351",
        ), patch.object(
            SERVER,
            "claim_shared_map_scan",
            return_value=True,
        ), patch.object(
            SERVER,
            "wait_for_brush_scan_slot",
            return_value=True,
        ), patch.object(
            SERVER,
            "post_game",
            return_value=(
                200,
                b"",
                [{"opcode": 0x8540, "payload": b"live-target"}],
            ),
        ), patch.object(
            SERVER,
            "parse_8540_targets",
            return_value=[live_target],
        ), patch.object(
            SERVER,
            "record_shared_map_region",
            return_value={"diff": {"retainedCount": 1}},
        ), patch.object(
            SERVER,
            "release_shared_map_scan",
        ):
            result = SERVER.revalidate_shared_bandit_target(
                sess,
                cached_target,
                owner="brush-task",
            )

        self.assertTrue(result["available"])
        self.assertTrue(result["target"]["revalidated"])
        self.assertEqual(
            result["target"]["sharedTargetKey"],
            "id:000000000086b560",
        )

    def test_brush_search_miss_has_no_fixed_cooldown(self) -> None:
        waits = []
        logs = []
        original_task_log = SERVER.task_log

        class FakeStopEvent:
            def wait(self, seconds):
                waits.append(seconds)
                return False

            def is_set(self):
                return False

        task = {
            "taskId": "brush-yield-test",
            "type": "auto-brush-yellow",
            "sessionId": "session-1",
            "stopEvent": FakeStopEvent(),
        }
        try:
            SERVER.task_log = lambda _task, message: logs.append(message)
            stopped = SERVER.pause_brush_after_search_miss(
                task,
                ["general-1"],
                3,
                {
                    "requestCount": 20,
                    "cacheSkipCount": 4,
                    "nextCursor": 40,
                },
                rule_index=2,
            )
        finally:
            SERVER.task_log = original_task_log

        self.assertFalse(stopped)
        self.assertEqual(waits, [])
        self.assertEqual(task["schedulerState"], "waiting_target")
        self.assertFalse(task["schedulerRunnable"])
        self.assertEqual(task["schedulerGeneralIds"], ["general-1"])
        self.assertIn("本批 20 次找黄请求均未命中", task["schedulerMessage"])
        self.assertNotIn("schedulerNextCheckAt", task)
        self.assertNotIn("brushRuleRetryAt", task)
        self.assertIn("不设置找黄冷却", logs[0])
        self.assertIn("其他刷黄编队、副本和无损可继续", logs[0])

    def test_daily_start_schedule_uses_selected_local_hour(self) -> None:
        now = SERVER.time.mktime((2026, 7, 10, 2, 0, 0, 0, 0, -1))
        wait_today, today_ms = SERVER.local_daily_start_schedule(8, now_ts=now)
        wait_next, next_ms = SERVER.local_daily_start_schedule(8, next_day=True, now_ts=now)
        self.assertEqual(wait_today, 6 * 60 * 60)
        self.assertEqual(wait_next, 30 * 60 * 60)
        self.assertEqual(SERVER.time.localtime(today_ms / 1000).tm_hour, 8)
        self.assertEqual(SERVER.time.localtime(next_ms / 1000).tm_mday, 11)
        after_start = SERVER.time.mktime((2026, 7, 10, 9, 0, 0, 0, 0, -1))
        self.assertEqual(SERVER.local_daily_start_schedule(8, now_ts=after_start)[0], 0)

    def test_food_to_copper_floor_only_accepts_single_select_values(self) -> None:
        sess = {"sessionId": "copper-floor-config", "generals": []}
        for amount in (1, 10, 20, 50):
            config = SERVER.normalize_auto_config(
                sess,
                {"autoStart": False, "copperFloorWan": amount},
            )
            self.assertEqual(config["copperFloorWan"], amount)
        config = SERVER.normalize_auto_config(
            sess,
            {"autoStart": False, "copperFloorWan": 99},
        )
        self.assertEqual(config["copperFloorWan"], 1)

    def test_common_defaults_enable_healing_and_disable_technology_upgrade(self) -> None:
        sess = {"sessionId": "common-defaults", "generals": []}

        config = SERVER.normalize_auto_config(sess, {"autoStart": False})

        self.assertTrue(config["healWounded"])
        self.assertFalse(config["domestic"]["upgradeTechnology"])

    def test_explicit_common_toggle_values_are_preserved(self) -> None:
        sess = {"sessionId": "explicit-common-toggles", "generals": []}

        config = SERVER.normalize_auto_config(sess, {
            "autoStart": False,
            "healWounded": False,
            "domestic": {"upgradeTechnology": True},
        })

        self.assertFalse(config["healWounded"])
        self.assertTrue(config["domestic"]["upgradeTechnology"])

    def test_military_prepare_defaults_to_healing_when_old_config_lacks_field(self) -> None:
        sess = {
            "sessionId": "legacy-healing-default",
            "generals": [{"fiefId": 1001}],
        }
        with (
            patch.object(SERVER, "load_account_habits", return_value={"config": {}}),
            patch.object(SERVER, "refresh_generals"),
            patch.object(
                SERVER,
                "execute_heal_wounded",
                return_value={"success": True},
            ) as execute_heal,
        ):
            SERVER.heal_all_wounded_before_military_prepare(sess, "刷黄")

        execute_heal.assert_called_once()

    def test_common_frequent_patch_does_not_save_unsaved_daily_page(self) -> None:
        sess = {"sessionId": "atomic-common-settings", "generals": []}
        old_config = SERVER.normalize_auto_config(sess, {
            "autoStart": False,
            "healWounded": False,
            "autoEnergy": False,
            "dailyTasks": {
                "autoSignIn": False,
                "arenaCoins": True,
                "autoDonate": False,
                "salary": False,
            },
        })

        merged = SERVER.merge_settings_scope_patch(old_config, "common.frequent", {
            "healWounded": True,
            "autoEnergy": True,
            # Simulate a stale frontend accidentally including another page.
            "dailyTasks": {"autoSignIn": True},
        })
        config = SERVER.normalize_auto_config(sess, {"config": merged})

        self.assertTrue(config["healWounded"])
        self.assertTrue(config["autoEnergy"])
        self.assertFalse(config["dailyTasks"]["autoSignIn"])
        self.assertTrue(config["dailyTasks"]["arenaCoins"])

    def test_daily_scope_updates_only_daily_task_whitelist(self) -> None:
        old_config = {
            "autoStart": False,
            "healWounded": False,
            "dailyTasks": {
                "autoSignIn": False,
                "arenaCoins": True,
                "autoDonate": False,
                "salary": False,
            },
        }
        merged = SERVER.merge_settings_scope_patch(old_config, "common.daily", {
            "healWounded": True,
            "dailyTasks": {
                "autoSignIn": True,
                "arenaCoins": False,
                "notARealTask": True,
            },
        })

        self.assertFalse(merged["healWounded"])
        self.assertEqual(merged["dailyTasks"], {
            "autoSignIn": True,
            "arenaCoins": False,
            "autoDonate": False,
            "salary": False,
        })

    def test_daily_scope_missing_visit_selection_disables_only_general_visit(self) -> None:
        sess = {"sessionId": "independent-daily-settings", "generals": []}
        old_config = SERVER.normalize_auto_config(sess, {
            "autoStart": False,
            "dailyTasks": {
                "autoSignIn": False,
                "autoDonate": False,
                "salary": False,
                "nationalCollect": False,
                "cityLordCollect": False,
                "generalVisit": False,
            },
        })

        config = SERVER.normalize_settings_scope_patch(
            sess,
            old_config,
            "common.daily",
            {
                "dailyTasks": {
                    "autoDonate": True,
                    "salary": True,
                    "nationalCollect": True,
                    "cityLordCollect": True,
                    "generalVisit": True,
                },
                "generalVisitGeneralIds": [],
            },
        )

        self.assertTrue(config["dailyTasks"]["autoDonate"])
        self.assertTrue(config["dailyTasks"]["salary"])
        self.assertTrue(config["dailyTasks"]["nationalCollect"])
        self.assertTrue(config["dailyTasks"]["cityLordCollect"])
        self.assertFalse(config["dailyTasks"]["generalVisit"])
        self.assertEqual(config["generalVisitGeneralIds"], [])

    def test_national_citizen_can_save_visit_task_without_candidates(self) -> None:
        sess = {
            "sessionId": "citizen-daily-settings",
            "generals": [],
            "roleState": {"officeName": "国民", "officeId": 0x0100},
        }
        old_config = SERVER.normalize_auto_config(sess, {
            "autoStart": False,
            "dailyTasks": {"generalVisit": False},
        })

        config = SERVER.normalize_settings_scope_patch(
            sess,
            old_config,
            "common.daily",
            {
                "dailyTasks": {"generalVisit": True},
                "generalVisitGeneralIds": [],
            },
        )

        self.assertTrue(config["dailyTasks"]["generalVisit"])
        self.assertEqual(config["generalVisitGeneralIds"], [])

    def test_items_scope_cannot_overwrite_brush_or_common_fields(self) -> None:
        old_config = {
            "autoStart": True,
            "healWounded": True,
            "dailyTasks": {"autoSignIn": False},
            "brush": {"startX": 88, "startY": 22},
            "autoOpenEnabled": False,
        }
        merged = SERVER.merge_settings_scope_patch(old_config, "common.items", {
            "autoOpenEnabled": True,
            "healWounded": False,
            "dailyTasks": {"autoSignIn": True},
            "brush": {"startX": 1, "startY": 1},
        })

        self.assertTrue(merged["autoOpenEnabled"])
        self.assertTrue(merged["healWounded"])
        self.assertFalse(merged["dailyTasks"]["autoSignIn"])
        self.assertEqual(merged["brush"], {"startX": 88, "startY": 22})

    def test_items_scope_save_ignores_stale_brush_generals(self) -> None:
        sess = {
            "sessionId": "items-with-stale-brush",
            "generals": [{"id": 528290}],
        }
        old_brush = {
            "rows": [{
                "enabled": True,
                "generalIds": ["446074"],
                "generalId": "446074",
                "level": 7,
            }],
            "rules": [{"enabled": True, "generalIds": ["446074"]}],
            "generalId": "446074",
            "legacyMarker": "keep-exactly",
        }
        old_formations = [{
            "enabled": True,
            "generalId": "446074",
            "soldierType": "强弩兵",
            "soldierCount": 1299,
        }]
        old_config = {
            "sessionId": sess["sessionId"],
            "autoStart": True,
            "healWounded": True,
            "formations": old_formations,
            "brush": old_brush,
            "autoOpenEnabled": False,
            "autoOpenItemNames": [],
        }

        with patch.object(SERVER, "heal_saved_formation_rules") as heal_rules:
            config = SERVER.normalize_settings_scope_patch(
                sess,
                old_config,
                "common.items",
                {
                    "autoOpenEnabled": True,
                    "autoOpenItemNames": ["惊喜宝箱", "不存在的物品"],
                    "maxEquipmentLevel": 999,
                },
            )

        heal_rules.assert_not_called()
        self.assertTrue(config["autoOpenEnabled"])
        self.assertEqual(config["autoOpenItemNames"], ["惊喜宝箱"])
        self.assertEqual(config["maxEquipmentLevel"], 100)
        self.assertEqual(config["brush"], old_brush)
        self.assertEqual(config["formations"], old_formations)
        self.assertTrue(config["healWounded"])
        self.assertTrue(config["autoStart"])

    def test_brush_scope_save_still_rejects_stale_general(self) -> None:
        sess = {
            "sessionId": "brush-with-stale-general",
            "generals": [{"id": 528290}],
        }
        old_config = {
            "autoStart": True,
            "brush": {
                "rows": [{
                    "enabled": True,
                    "generalIds": ["446074"],
                    "generalId": "446074",
                    "level": 7,
                }],
            },
        }
        with (
            patch.object(
                SERVER,
                "heal_saved_formation_rules",
                return_value=[{
                    "enabled": True,
                    "generalId": "446074",
                    "soldierType": "强弩兵",
                    "soldierCount": 1299,
                }],
            ),
            self.assertRaisesRegex(
                RuntimeError,
                "刷黄规则的将领不在当前账号将领列表中：446074",
            ),
        ):
            SERVER.normalize_settings_scope_patch(
                sess,
                old_config,
                "brush",
                {
                    "autoStart": True,
                    "brush": old_config["brush"],
                },
            )

    def test_brush_scope_ignores_common_daily_and_item_fields(self) -> None:
        old_config = {
            "autoStart": False,
            "autoEnergy": False,
            "dailyTasks": {"autoSignIn": False},
            "autoOpenEnabled": False,
            "brush": {"startX": 88, "startY": 22},
        }
        merged = SERVER.merge_settings_scope_patch(old_config, "brush", {
            "autoStart": True,
            "autoEnergy": True,
            "dailyTasks": {"autoSignIn": True},
            "autoOpenEnabled": True,
            "brush": {"startX": 66, "startY": 11},
        })

        self.assertTrue(merged["autoStart"])
        self.assertFalse(merged["autoEnergy"])
        self.assertFalse(merged["dailyTasks"]["autoSignIn"])
        self.assertFalse(merged["autoOpenEnabled"])
        self.assertEqual(merged["brush"], {"startX": 66, "startY": 11})

    def test_all_disabled_brush_rows_save_without_formation(self) -> None:
        config = SERVER.normalize_auto_config(
            {
                "sessionId": "disabled-brush-config",
                "generals": [],
            },
            {
                "autoStart": True,
                "startHour": 9,
                "brush": {
                    "rows": [{
                        "enabled": False,
                        "generalIds": [],
                        "level": 1,
                        "compositionCode": "0000",
                    }],
                },
            },
        )
        self.assertFalse(config["autoStart"])
        self.assertEqual(config["startHour"], 9)
        self.assertEqual(config["formations"], [])

    def test_stale_formation_general_is_preserved_without_blocking_stop(self) -> None:
        sess = {
            "sessionId": "stale-formation-config",
            "generals": [{"id": 1, "name": "当前将领"}],
        }
        stale_rows = [
            {
                "enabled": True,
                "generalIds": ["1"],
                "generalId": "1",
                "soldierType": "轻骑兵",
                "soldierCount": 100,
            },
            {
                "enabled": True,
                "generalIds": ["12886835"],
                "generalId": "12886835",
                "soldierType": "投石车",
                "soldierCount": 200,
            },
        ]
        original_load = SERVER.load_account_habits
        original_save = SERVER.save_account_habits
        saved = {}
        SERVER.SAVED_FORMATION_RULES[sess["sessionId"]] = list(stale_rows)
        try:
            SERVER.load_account_habits = lambda _sess: {
                "formations": list(stale_rows),
                "formationOptions": {"clearOtherGenerals": False},
            }
            SERVER.save_account_habits = (
                lambda _sess, **kwargs: saved.update(kwargs) or {}
            )
            config = SERVER.normalize_auto_config(sess, {
                "autoStart": False,
                "brush": {"rows": [{"enabled": False}]},
            })
            normalized = list(SERVER.SAVED_FORMATION_RULES[sess["sessionId"]])
        finally:
            SERVER.load_account_habits = original_load
            SERVER.save_account_habits = original_save
            SERVER.SAVED_FORMATION_RULES.pop(sess["sessionId"], None)

        self.assertFalse(config["autoStart"])
        self.assertEqual(
            [row["generalId"] for row in normalized],
            ["1", "12886835"],
        )
        self.assertEqual(saved, {})
        self.assertEqual(
            SERVER.unresolved_formation_general_ids(sess, stale_rows),
            ["12886835"],
        )

    def test_default_brush_filter_is_0500_with_all_drops(self) -> None:
        config = SERVER.normalize_auto_config(
            {"sessionId": "default-brush-config", "generals": []},
            {
                "autoStart": False,
                "brush": {
                    "rows": [{
                        "enabled": False,
                        "generalIds": [],
                        "level": 1,
                    }],
                },
            },
        )
        self.assertEqual(config["brush"]["compositionCode"], "0500")
        self.assertEqual(config["brush"]["drop"], "宝物")
        self.assertEqual(config["brush"]["drops"], ["宝物", "资源", "装备", "宝箱"])

    def test_enabled_brush_rows_become_distinct_execution_rules(self) -> None:
        sess = {
            "sessionId": "multi-brush-config",
            "generals": [{"id": 1, "name": "步1"}, {"id": 2, "name": "骑1"}],
        }
        SERVER.SAVED_FORMATION_RULES[sess["sessionId"]] = [
            {"enabled": True, "generalIds": ["1"], "soldierType": "重步兵", "soldierCount": 49},
            {"enabled": True, "generalIds": ["2"], "soldierType": "轻骑兵", "soldierCount": 80},
        ]
        try:
            config = SERVER.normalize_auto_config(sess, {
                "autoStart": True,
                "startHour": 7,
                "brush": {
                    "startX": 100,
                    "startY": 30,
                    "rows": [
                        {"enabled": True, "generalIds": ["1"], "levels": [5, 6, 7], "level": 5, "compositionCode": "5000"},
                        {"enabled": True, "generalIds": ["2"], "level": 3, "compositionCode": "0050"},
                    ],
                },
            })
        finally:
            SERVER.SAVED_FORMATION_RULES.pop(sess["sessionId"], None)
        self.assertTrue(config["autoStart"])
        self.assertEqual(config["startHour"], 7)
        self.assertEqual([rule["generalIds"] for rule in config["brush"]["rules"]], [["1"], ["2"]])
        self.assertEqual([rule["levels"] for rule in config["brush"]["rules"]], [[5, 6, 7], [3]])
        self.assertEqual([rule["level"] for rule in config["brush"]["rules"]], [5, 3])
        self.assertEqual([rule["compositionCode"] for rule in config["brush"]["rules"]], ["5000", "0050"])
        self.assertEqual([formation["generalId"] for formation in config["formations"]], ["1", "2"])

    def test_multi_brush_levels_match_any_selected_level_but_keep_other_filters(self) -> None:
        composition_filter = {
            "maxFoot": 0,
            "maxBow": 5,
            "maxCavalry": 2,
            "maxChariot": 5,
        }

        def target(level: int, *, reward: str = "宝物", cavalry: int = 2) -> dict:
            return {
                "kind": "山贼",
                "level": level,
                "name": f"{level}级山贼",
                "reward": reward,
                "composition": {
                    "source": "8540-units",
                    "foot": 0,
                    "bow": 5,
                    "cavalry": cavalry,
                    "chariot": 5,
                },
            }

        for level in (5, 6, 7):
            self.assertTrue(SERVER.target_matches_search_filter(
                target(level),
                "山贼",
                [5, 6, 7],
                ["宝物"],
                composition_filter,
            ))
        for level in (4, 8):
            self.assertFalse(SERVER.target_matches_search_filter(
                target(level),
                "山贼",
                [5, 6, 7],
                ["宝物"],
                composition_filter,
            ))
        self.assertFalse(SERVER.target_matches_search_filter(
            target(6, reward="资源"),
            "山贼",
            [5, 6, 7],
            ["宝物"],
            composition_filter,
        ))
        self.assertFalse(SERVER.target_matches_search_filter(
            target(6, cavalry=3),
            "山贼",
            [5, 6, 7],
            ["宝物"],
            composition_filter,
        ))

    def test_brush_search_options_carry_multi_levels_and_legacy_level(self) -> None:
        opts = SERVER.brush_search_options(
            {"brush": {"targetKind": "山贼"}},
            {"levels": [7, 5, 6], "level": 7},
            {"sessionId": "multi-level-options"},
        )
        self.assertEqual(opts["levels"], [5, 6, 7])
        self.assertEqual(opts["level"], 5)
        self.assertEqual(SERVER.normalize_brush_levels(None, 6), [6])

    def test_stopping_brush_config_does_not_stop_other_resident_tasks(self) -> None:
        original_tasks = SERVER.AUTO_TASKS
        original_task_log = SERVER.task_log
        original_persist = SERVER.persist_runtime_state
        brush_stop = SERVER.threading.Event()
        dungeon_stop = SERVER.threading.Event()
        try:
            SERVER.AUTO_TASKS = {
                "brush": {
                    "taskId": "brush",
                    "type": "auto-brush-yellow",
                    "sessionId": "session-1",
                    "status": "running",
                    "stopEvent": brush_stop,
                },
                "dungeon": {
                    "taskId": "dungeon",
                    "type": "dungeon",
                    "sessionId": "session-1",
                    "status": "running",
                    "stopEvent": dungeon_stop,
                },
            }
            SERVER.task_log = lambda *_args, **_kwargs: None
            SERVER.persist_runtime_state = lambda: None
            stopped = SERVER.request_stop_tasks_for_session_type(
                "session-1",
                "auto-brush-yellow",
                "关闭刷黄",
            )
        finally:
            SERVER.AUTO_TASKS = original_tasks
            SERVER.task_log = original_task_log
            SERVER.persist_runtime_state = original_persist
        self.assertEqual(stopped, ["brush"])
        self.assertTrue(brush_stop.is_set())
        self.assertFalse(dungeon_stop.is_set())

    def test_auto_config_preserves_maintenance_settings(self) -> None:
        sess = {
            "sessionId": "brush-config-test",
            "generals": [{"id": 123, "name": "测试将领"}],
        }
        SERVER.SAVED_FORMATION_RULES[sess["sessionId"]] = [{
            "enabled": True,
            "generalId": "123",
            "generalIds": ["123"],
            "soldierType": "轻骑兵",
            "soldierCount": 10,
        }]
        try:
            config = SERVER.normalize_auto_config(sess, {
                "autoStart": False,
                "autoEnergy": True,
                "energyThreshold": 25,
                "foodToCopper": False,
                "copperFloorWan": 0,
                "cleanMail": True,
                "cleanInventory": True,
                "discardItemNames": "山贼头巾，兵书",
                "keepItemCount": 2,
                "discardEquipment": True,
                "maxEquipmentQuality": "优秀",
                "maxEquipmentLevel": 31,
                "autoOpenItemNames": ["50两银票", "青铜宝箱", "不存在的箱子"],
                "brush": {
                    "generalId": "123",
                    "level": 5,
                    "compositionCode": "0525",
                },
            })
        finally:
            SERVER.SAVED_FORMATION_RULES.pop(sess["sessionId"], None)
        self.assertTrue(config["autoEnergy"])
        self.assertEqual(config["energyThreshold"], 25)
        self.assertFalse(config["foodToCopper"])
        self.assertEqual(config["copperFloorWan"], 1)
        self.assertTrue(config["cleanMail"])
        self.assertTrue(config["cleanInventory"])
        self.assertEqual(config["discardItemNames"], "山贼头巾，兵书")
        self.assertEqual(config["keepItemCount"], 0)
        self.assertTrue(config["discardEquipment"])
        self.assertEqual(config["maxEquipmentQuality"], "优秀")
        self.assertEqual(config["maxEquipmentLevel"], 31)
        self.assertEqual(config["autoOpenItemNames"], ["50两银票", "青铜宝箱"])

    def test_shared_map_is_reused_by_accounts_on_same_server_only(self) -> None:
        original_dir = SERVER.SHARED_MAP_DIR
        original_maps = SERVER.SHARED_MAPS
        original_post_game = SERVER.post_game
        original_parser = SERVER.parse_8540_targets
        original_last_request_at = SERVER.BRUSH_SCAN_LAST_REQUEST_AT
        calls = []
        target = {
            "id": 99,
            "idHex": "0000000000000063",
            "x": 100,
            "y": 30,
            "kind": "山贼",
            "level": 1,
            "name": "1级山贼",
        }

        def fake_post_game(_url, _commands, _dm, account_id=None):
            calls.append(account_id)
            return 200, b"\xaa\xbb", [{
                "opcode": 0x8540,
                "payload": b"\x01\x02\x03",
            }]

        try:
            with tempfile.TemporaryDirectory() as tmp:
                SERVER.SHARED_MAP_DIR = Path(tmp)
                SERVER.SHARED_MAPS = {}
                SERVER.post_game = fake_post_game
                SERVER.parse_8540_targets = lambda _payload: [dict(target)]
                SERVER.BRUSH_SCAN_LAST_REQUEST_AT = 0.0
                sess1 = {
                    "sessionId": "same-server-a",
                    "username": "1001",
                    "gameHttp": "http://example.invalid",
                    "dm": 1,
                    "role": {"roleId": 1, "level": 30},
                    "area": {"serverKey": "qzone_351", "areaName": "351区"},
                }
                sess2 = {
                    **sess1,
                    "sessionId": "same-server-b",
                    "username": "1002",
                }
                other_server = {
                    **sess1,
                    "sessionId": "other-server",
                    "area": {"serverKey": "qzone_352", "areaName": "352区"},
                }
                opts = {
                    "startX": 100,
                    "startY": 30,
                    "scanLimit": 1,
                    "targetKind": "山贼",
                    "level": 1,
                }
                first = SERVER.search_targets(sess1, opts, scan_state={})
                second = SERVER.search_targets(sess2, opts, scan_state={})
                third = SERVER.search_targets(other_server, opts, scan_state={})
                scan_x, scan_y = SERVER.brush_scan_coordinates(100, 30, 1)[0]
                database_file = SERVER.bandit_db_path()
                with SERVER._bandit_db_connect() as connection:
                    persisted_region = connection.execute(
                        """
                        SELECT scanned_at FROM bandit_regions
                        WHERE server_key='区351' AND scan_x=? AND scan_y=?
                        """,
                        (scan_x, scan_y),
                    ).fetchone()
                database_exists = database_file.exists()
                legacy_map_files = list(database_file.parent.glob("*_bandit.json"))
                raw_response_files = list(database_file.parent.glob("*_bandit_responses.jsonl"))
        finally:
            SERVER.SHARED_MAP_DIR = original_dir
            SERVER.SHARED_MAPS = original_maps
            SERVER.post_game = original_post_game
            SERVER.parse_8540_targets = original_parser
            SERVER.BRUSH_SCAN_LAST_REQUEST_AT = original_last_request_at

        self.assertEqual(first["requestCount"], 1)
        self.assertEqual(second["requestCount"], 0)
        self.assertEqual(second["cacheHitCount"], 1)
        self.assertTrue(second["targets"][0]["fromSharedMap"])
        self.assertEqual(third["requestCount"], 1)
        self.assertEqual(calls, ["same-server-a", "other-server"])
        self.assertTrue(database_exists)
        self.assertIsNotNone(persisted_region)
        self.assertFalse(legacy_map_files)
        self.assertFalse(raw_response_files)

    def test_shared_target_reservation_prevents_cross_account_collision(self) -> None:
        original_dir = SERVER.SHARED_MAP_DIR
        original_maps = SERVER.SHARED_MAPS
        try:
            with tempfile.TemporaryDirectory() as tmp:
                SERVER.SHARED_MAP_DIR = Path(tmp)
                SERVER.SHARED_MAPS = {}
                sess1 = {
                    "sessionId": "owner-a",
                    "username": "1001",
                    "area": {"serverKey": "qzone_351"},
                }
                sess2 = {
                    "sessionId": "owner-b",
                    "username": "1002",
                    "area": {"serverKey": "qzone_351"},
                }
                target = {
                    "id": 99,
                    "idHex": "0000000000000063",
                    "x": 100,
                    "y": 30,
                    "kind": "山贼",
                    "level": 1,
                    "name": "1级山贼",
                }
                SERVER.record_shared_map_region(
                    sess1,
                    "bandit",
                    x=100,
                    y=30,
                    http_code=200,
                    opcodes=["0x8540"],
                    response_data=b"\x00",
                    response_payloads=[b"\x01"],
                    targets=[target],
                )
                available = SERVER.shared_map_available_targets(
                    sess1,
                    "bandit",
                    target_kind="山贼",
                    level=1,
                    drops=[],
                    composition_filter={},
                )
                claimed = SERVER.reserve_shared_map_target(
                    sess1,
                    "bandit",
                    available[0],
                    owner="owner-a",
                    task_id="task-a",
                )
                hidden_from_second = SERVER.shared_map_available_targets(
                    sess2,
                    "bandit",
                    target_kind="山贼",
                    level=1,
                    drops=[],
                    composition_filter={},
                )
                second_claim = SERVER.reserve_shared_map_target(
                    sess2,
                    "bandit",
                    available[0],
                    owner="owner-b",
                    task_id="task-b",
                )
                with SERVER._bandit_db_connect() as connection:
                    connection.execute(
                        """
                        UPDATE bandit_targets
                        SET lease_until=0
                        WHERE server_key='区351' AND target_id_hex=?
                        """,
                        (SERVER.normalize_bandit_target_id(available[0]),),
                    )
                reusable = SERVER.shared_map_available_targets(
                    sess2,
                    "bandit",
                    target_kind="山贼",
                    level=1,
                    drops=[],
                    composition_filter={},
                )
        finally:
            SERVER.SHARED_MAP_DIR = original_dir
            SERVER.SHARED_MAPS = original_maps

        self.assertTrue(claimed)
        self.assertEqual(hidden_from_second, [])
        self.assertFalse(second_claim)
        self.assertEqual(len(reusable), 1)

    def test_shared_map_diff_marks_removed_and_added_targets(self) -> None:
        original_dir = SERVER.SHARED_MAP_DIR
        original_maps = SERVER.SHARED_MAPS
        try:
            with tempfile.TemporaryDirectory() as tmp:
                SERVER.SHARED_MAP_DIR = Path(tmp)
                SERVER.SHARED_MAPS = {}
                sess = {
                    "sessionId": "diff-owner",
                    "username": "1001",
                    "area": {"areaName": "周年服351区"},
                }

                def target(target_id):
                    return {
                        "id": target_id,
                        "idHex": f"{target_id:016x}",
                        "x": 100 + target_id,
                        "y": 30,
                        "kind": "山贼",
                        "level": 1,
                        "name": "1级山贼",
                    }

                SERVER.record_shared_map_region(
                    sess,
                    "bandit",
                    x=100,
                    y=30,
                    http_code=200,
                    opcodes=["0x8540"],
                    response_data=b"first",
                    response_payloads=[b"first-payload"],
                    targets=[target(1), target(2)],
                )
                latest = SERVER.record_shared_map_region(
                    sess,
                    "bandit",
                    x=100,
                    y=30,
                    http_code=200,
                    opcodes=["0x8540"],
                    response_data=b"second",
                    response_payloads=[b"second-payload"],
                    targets=[target(2), target(3)],
                )
                with SERVER._bandit_db_connect() as connection:
                    statuses = {
                        f"id:{row['target_id_hex']}": row["status"]
                        for row in connection.execute(
                            """
                            SELECT target_id_hex, status FROM bandit_targets
                            WHERE server_key='区351'
                            """
                        ).fetchall()
                    }
        finally:
            SERVER.SHARED_MAP_DIR = original_dir
            SERVER.SHARED_MAPS = original_maps

        self.assertEqual(latest["diff"]["added"], ["id:0000000000000003"])
        self.assertEqual(latest["diff"]["removed"], ["id:0000000000000001"])
        self.assertEqual(latest["diff"]["retainedCount"], 1)
        self.assertNotIn("id:0000000000000001", statuses)
        self.assertEqual(statuses["id:0000000000000002"], "available")
        self.assertEqual(statuses["id:0000000000000003"], "available")

    def test_shared_scan_lease_avoids_duplicate_region_requests(self) -> None:
        original_dir = SERVER.SHARED_MAP_DIR
        original_maps = SERVER.SHARED_MAPS
        try:
            with tempfile.TemporaryDirectory() as tmp:
                SERVER.SHARED_MAP_DIR = Path(tmp)
                SERVER.SHARED_MAPS = {}
                sess1 = {
                    "sessionId": "scan-a",
                    "area": {"serverKey": "qzone_351"},
                }
                sess2 = {
                    "sessionId": "scan-b",
                    "area": {"serverKey": "qzone_351"},
                }
                first = SERVER.claim_shared_map_scan(
                    sess1, "bandit", "100,30", "scan-a"
                )
                duplicate = SERVER.claim_shared_map_scan(
                    sess2, "bandit", "100,30", "scan-b"
                )
                SERVER.release_shared_map_scan(
                    sess1, "bandit", "100,30", "scan-a"
                )
                after_release = SERVER.claim_shared_map_scan(
                    sess2, "bandit", "100,30", "scan-b"
                )
        finally:
            SERVER.SHARED_MAP_DIR = original_dir
            SERVER.SHARED_MAPS = original_maps

        self.assertTrue(first)
        self.assertFalse(duplicate)
        self.assertTrue(after_release)

    def test_unified_bandit_coordinator_scales_by_server_water_level(self) -> None:
        original_tasks = SERVER.AUTO_TASKS
        original_sessions = SERVER.SESSIONS
        try:
            sessions = [
                {
                    "sessionId": f"sid-{index}",
                    "area": {"serverKey": "qzone_351"},
                    "role": {"level": 60},
                }
                for index in range(20)
            ]
            SERVER.SESSIONS = {
                str(sess["sessionId"]): sess for sess in sessions
            }
            SERVER.AUTO_TASKS = {}
            maintenance = SERVER.bandit_coordinator_water_level(
                "区351", sessions,
            )
            self.assertEqual("maintenance", maintenance["level"])
            self.assertEqual(20.0, maintenance["intervalSec"])

            SERVER.AUTO_TASKS = {
                "brush": {
                    "taskId": "brush",
                    "type": "auto-brush-yellow",
                    "status": "running",
                    "sessionId": "sid-0",
                    "config": {
                        "sessionId": "sid-0",
                        "brush": {
                            "rules": [{
                                "enabled": True,
                                "targetKind": "山贼",
                                "levels": [7],
                                "startX": 90,
                                "startY": 30,
                            }],
                        },
                    },
                },
            }
            with patch.object(SERVER, "shared_map_available_targets", return_value=[]):
                low = SERVER.bandit_coordinator_water_level("区351", sessions)
            self.assertEqual("low", low["level"])
            self.assertEqual(1.5, low["intervalSec"])

            with patch.object(
                SERVER,
                "shared_map_available_targets",
                return_value=[{"id": 1}],
            ):
                one_account = SERVER.bandit_coordinator_water_level(
                    "区351", sessions[:1],
                )
                many_accounts = SERVER.bandit_coordinator_water_level(
                    "区351", sessions,
                )
            self.assertEqual(2.0, one_account["intervalSec"])
            self.assertEqual(6.0, many_accounts["intervalSec"])
        finally:
            SERVER.AUTO_TASKS = original_tasks
            SERVER.SESSIONS = original_sessions

    def test_coordinator_route_key_groups_accounts_by_outbound_ip(self) -> None:
        original_accounts = SERVER.ACCOUNTS
        try:
            SERVER.ACCOUNTS = {
                "a": {"proxyIp": "1.2.3.4", "proxyNode": "node-a"},
                "b": {"proxyIp": "1.2.3.4", "proxyNode": "node-b"},
                "c": {"proxyIp": "5.6.7.8", "proxyNode": "node-a"},
            }
            self.assertEqual(
                SERVER.bandit_coordinator_route_key("a"),
                SERVER.bandit_coordinator_route_key("b"),
            )
            self.assertNotEqual(
                SERVER.bandit_coordinator_route_key("a"),
                SERVER.bandit_coordinator_route_key("c"),
            )
        finally:
            SERVER.ACCOUNTS = original_accounts

    def test_heal_copper_shortage_exchanges_fixed_amount_once_then_retries(self) -> None:
        sess = {"sessionId": "heal-copper", "roleState": {}}
        formation = {"fiefId": 251}
        with patch.object(
            SERVER,
            "execute_food_to_copper",
            return_value={"success": True, "copper": 30_000, "food": 900_000},
        ) as exchange, patch.object(
            SERVER,
            "execute_heal_wounded",
            return_value={"success": True, "message": "治疗成功"},
        ) as retry, patch.object(SERVER, "account_log"):
            result = SERVER.retry_heal_after_fixed_copper_exchange(
                sess,
                formation,
                confirm="heal-wounded",
                allow_all_if_count_unknown=True,
                original_message="铜钱不足",
            )
        exchange.assert_called_once_with(
            sess,
            100_000,
            confirm="food-to-copper",
        )
        retry.assert_called_once_with(
            sess,
            formation,
            confirm="heal-wounded",
            allow_all_if_count_unknown=True,
            _copper_shortage_retry=False,
        )
        self.assertTrue(result["success"])
        self.assertEqual(100_000, result["copperRecovery"]["foodAmount"])
        self.assertEqual(30_000, result["copperRecovery"]["copperAmount"])


if __name__ == "__main__":
    unittest.main()
