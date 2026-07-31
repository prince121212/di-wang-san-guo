"""军情（0x1600/0x8600）真实抓包回归。

真值来源是三份专门为军情做的抓包，每份都带 operator_timeline.md 里
玩家本人的口述记录（目标名称、坐标、参战将领、当时的状态），因此
下面断言的坐标和状态都能对回真实客户端界面，不是自证式断言：

- passive_pcap_hotspot_20260714_033644：牧场(91,28)，步2/步3/车2/车1
- passive_pcap_hotspot_20260714_044023：镔铁矿(95,30)，步2/车2
- passive_pcap_hotspot_20260714_125113：水晶矿(136,20)，步1/车1

同一次出征在军情里是同一个 battleId，随时间在
【攻占】战斗进行中 →【驻守】→【返回】之间流转。
"""
from __future__ import annotations

import importlib.util
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
CTF_OUT = ROOT / "ctf_out"

SPEC = importlib.util.spec_from_file_location("dwpm_server_military_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


def payload_8600(capture: str, flow_index: int) -> bytes:
    response_file = CTF_OUT / capture / "live_analyzed" / f"{flow_index:03d}" / "resp.bin"
    packets = SERVER.parse_response(response_file.read_bytes())
    return next(
        packet["payload"]
        for packet in packets
        if packet.get("opcode") == 0x8600
    )


def only_action(capture: str, flow_index: int, generals=None) -> dict:
    actions = SERVER.parse_8600_military_actions(
        payload_8600(capture, flow_index), generals or [],
    )
    assert len(actions) == 1, f"{capture}/{flow_index:03d} 解析出 {len(actions)} 条军情"
    return actions[0]


CAP_MU = "passive_pcap_hotspot_20260714_033644"   # 牧场 (91,28)
CAP_BIN = "passive_pcap_hotspot_20260714_044023"  # 镔铁矿 (95,30)
CAP_CRY = "passive_pcap_hotspot_20260714_125113"  # 水晶矿 (136,20)
# 2026-07-26 军情专项抓包：副本关卡记录、山贼去程尾部(0x0b)、
# 去程/回程 marchValue 连续递减；带口述时间线。
CAP_JQ = "passive_pcap_hotspot_20260726_173635"


def incoming_raid_payload() -> bytes:
    """Minimal 0x8600 payload preserving the live 2026-07-29 type=2 layout."""
    out = bytearray()
    out += struct.pack(">H", 3)
    for kind, value in ((1, 0), (1, 1), (2, 0)):
        out += struct.pack(">BH", kind, value)
    out += struct.pack(">B", 3)  # type=1, type=2, type=3

    # type=1: no outgoing actions.
    out += struct.pack(">BHH", 1, 0, 0)

    # type=2 descriptor table followed by the original client's C(0, stream)
    # incoming-record table.
    out += struct.pack(">BH", 2, 1)
    out += SERVER.utf("")
    out += struct.pack(">HQHHH", 1, 0x18DC27, 0, 50, 1)
    out += struct.pack(">H", 0)
    out += struct.pack(">H", 1)
    out += struct.pack(">Q", 10_564_231)
    out += SERVER.utf("全益溪")
    out += struct.pack(">B", 1)
    out += SERVER.utf("宿代苑基地")
    out += struct.pack(">QI", 176, 71_716_750)
    out += struct.pack(">Q", 1_785_337_200_415)

    # type=3: no garrison actions. Real packets append a structured general-state
    # block; this minimal fixture deliberately ends before that optional block.
    out += struct.pack(">BHH", 3, 0, 0)
    return bytes(out)


class MilitaryIntelParserTests(unittest.TestCase):
    def test_request_payload_matches_real_client(self) -> None:
        """军情刷新必须和真实客户端发一模一样的 0x1600 请求体。"""
        self.assertEqual(
            SERVER.MILITARY_INTEL_REQUEST_PAYLOAD.hex(),
            "07000000000000000000000014",
        )

    def test_battle_in_progress_is_parsed_with_real_target_and_coords(self) -> None:
        action = only_action(CAP_CRY, 41)
        self.assertEqual(action["tag"], "攻占")
        self.assertEqual(action["state"], "战斗")
        self.assertIn("战斗进行中", action["text"])
        self.assertEqual(action["targetName"], "水晶矿(1级)")
        # 口述真值：X=136，Y=20
        self.assertEqual((action["x"], action["y"]), (136, 20))
        self.assertEqual(action["targetType"], 2)
        self.assertEqual(action["targetTypeText"], "野外目标")
        self.assertEqual(action["battleId"], 9649515)
        self.assertEqual(action["generalIds"], [0xFACF09, 0x14C1BE6])

    def test_garrison_keeps_same_battle_id_and_target(self) -> None:
        fighting = only_action(CAP_CRY, 41)
        garrison = only_action(CAP_CRY, 62)
        self.assertEqual(garrison["tag"], "驻守")
        self.assertEqual(garrison["state"], "驻守")
        self.assertEqual((garrison["x"], garrison["y"]), (136, 20))
        # 同一次出征，battleId 与参战将领不变，只是状态推进
        self.assertEqual(garrison["battleId"], fighting["battleId"])
        self.assertEqual(garrison["generalIds"], fighting["generalIds"])
        # 驻守没有行军尾部，因此不应凭空出现时间戳
        self.assertNotIn("eventTimeMs", garrison)

    def test_returning_action_targets_home_fief_without_coords(self) -> None:
        returning = only_action(CAP_CRY, 70)
        self.assertEqual(returning["tag"], "返回")
        self.assertEqual(returning["state"], "返回")
        self.assertEqual(returning["targetName"], "董全基地")
        self.assertEqual(returning["targetType"], 1)
        self.assertEqual(returning["targetTypeText"], "封地")
        # 返回自己封地没有地图坐标，不能伪造成 (0,0) 的真实坐标
        self.assertEqual((returning["x"], returning["y"]), (0, 0))
        self.assertFalse(returning["hasCoord"])
        # 回程带预计到达时间戳
        self.assertEqual(returning["marchKindText"], "回程")
        self.assertGreater(returning["eventTimeMs"], 1_700_000_000_000)

    def test_march_value_is_remaining_march_time(self) -> None:
        """marchValue 是“剩余行军毫秒”，eventTimeMs 是固定的预计到达时刻。

        20260726_173635 同一 battleId 连续刷新证明 marchValue 逐次递减而
        eventTimeMs 恒定（见 MarchTailSemanticsTests）。因此
        eventTimeMs - marchValue = 本次刷新的时刻。旧抓包只在点击「召回全军」
        后立刻刷新过一次（operator_timeline：13:02:26 与 03:55:22），
        剩余≈全程，这两个数值断言依然成立。
        """
        # 水晶矿：13:02:26 点召回后立刻刷新，返回途中“30 多分钟”
        crystal = only_action(CAP_CRY, 70)
        self.assertAlmostEqual(crystal["marchValue"] / 60000, 32.75, places=1)
        crystal_refreshed = crystal["eventTimeMs"] - crystal["marchValue"]
        # 牧场：03:55:22 点召回
        pasture = only_action(CAP_MU, 111)
        self.assertAlmostEqual(pasture["marchValue"] / 60000, 6.07, places=1)
        pasture_refreshed = pasture["eventTimeMs"] - pasture["marchValue"]
        # 刷新时刻必须早于预计到达，且两者差就是当时的剩余行军时间
        for refreshed_at, action in (
            (crystal_refreshed, crystal), (pasture_refreshed, pasture),
        ):
            self.assertLess(refreshed_at, action["eventTimeMs"])
            self.assertEqual(
                action["eventTimeMs"] - refreshed_at, action["marchValue"],
            )

    def test_battle_records_carry_no_march_duration(self) -> None:
        """战斗中说明部队已抵达，不应残留行军时长被当成倒计时用。"""
        self.assertEqual(only_action(CAP_CRY, 41)["marchValue"], 0)
        self.assertEqual(only_action(CAP_MU, 100)["marchValue"], 0)

    def test_bandit_style_tags_are_recognised_as_combat(self) -> None:
        """刷黄的【消灭】与打矿的【攻占】同属战斗态（见 帝三辅助设计/军情.jpg）。"""
        for tag in ("消灭", "攻占", "夺取", "掠夺"):
            self.assertEqual(SERVER.MILITARY_ACTION_STATE_BY_TAG[tag], "战斗")

    def test_four_general_formation_from_pasture_capture(self) -> None:
        action = only_action(CAP_MU, 100)
        self.assertEqual(action["tag"], "攻占")
        self.assertEqual(action["targetName"], "牧场(1级)")
        # 口述真值：X=91，Y=28，四个将领
        self.assertEqual((action["x"], action["y"]), (91, 28))
        self.assertEqual(len(action["generalIds"]), 4)
        self.assertEqual(action["battleId"], 9381765)

    def test_general_names_are_resolved_from_session_generals(self) -> None:
        generals = [
            {"id": 0xFACF09, "name": "步1"},
            {"id": 0x14C1BE6, "name": "车1"},
        ]
        action = only_action(CAP_CRY, 41, generals)
        self.assertEqual(action["generalNames"], ["步1", "车1"])

    def test_unknown_general_id_stays_empty_instead_of_guessing(self) -> None:
        action = only_action(CAP_CRY, 41, [{"id": 0xFACF09, "name": "步1"}])
        self.assertEqual(action["generalNames"], ["步1", ""])

    def test_mine_capture_matches_spoken_coordinates(self) -> None:
        action = only_action(CAP_BIN, 308)
        self.assertEqual(action["tag"], "驻守")
        self.assertEqual(action["targetName"], "1级镔铁矿")
        # 口述真值：X=95，Y=30
        self.assertEqual((action["x"], action["y"]), (95, 30))
        self.assertEqual(len(action["generalIds"]), 2)

    def test_every_captured_sample_yields_exactly_one_action(self) -> None:
        """15 个真实样本必须条条解析出来，且不多不少。"""
        samples = [
            (CAP_MU, 100), (CAP_MU, 102), (CAP_MU, 107), (CAP_MU, 111),
            (CAP_BIN, 308), (CAP_BIN, 310), (CAP_BIN, 320),
            (CAP_CRY, 41), (CAP_CRY, 43), (CAP_CRY, 45), (CAP_CRY, 47),
            (CAP_CRY, 51), (CAP_CRY, 53), (CAP_CRY, 62), (CAP_CRY, 70),
        ]
        for capture, index in samples:
            with self.subTest(capture=capture, flow=index):
                action = only_action(capture, index)
                self.assertGreater(action["battleId"], 0)
                self.assertGreater(action["targetId"], 0)
                self.assertTrue(action["targetName"])
                self.assertIn(action["state"], {"战斗", "驻守", "返回"})

    def test_non_military_payload_produces_no_actions(self) -> None:
        """非军情包不能被锚点误命中而伪造出军情。"""
        self.assertEqual(SERVER.parse_8600_military_actions(b"", []), [])
        noise = "【活动时间】限时开启".encode("utf-8")
        payload = len(noise).to_bytes(2, "big") + noise + b"\x00" * 8
        self.assertEqual(SERVER.parse_8600_military_actions(payload, []), [])

    def test_incoming_raid_is_reconstructed_from_separate_fields(self) -> None:
        actions = SERVER.parse_8600_military_actions(incoming_raid_payload(), [])
        self.assertEqual(len(actions), 1)
        incoming = actions[0]
        self.assertTrue(incoming["incoming"])
        self.assertEqual(incoming["state"], "来袭")
        self.assertEqual(incoming["tag"], "掠夺")
        self.assertEqual(incoming["text"], "【掠夺】全益溪夺取宿代苑基地")
        self.assertEqual(incoming["recordId"], 10_564_231)
        self.assertEqual(incoming["attackerName"], "全益溪")
        self.assertEqual(incoming["actionType"], 1)
        self.assertEqual(incoming["actionTypeText"], "掠夺")
        self.assertEqual(incoming["targetName"], "宿代苑基地")
        self.assertEqual(incoming["targetId"], 176)
        self.assertEqual(incoming["marchValue"], 71_716_750)
        self.assertEqual(incoming["eventTimeMs"], 1_785_337_200_415)


class MilitaryIntel20260726Tests(unittest.TestCase):
    """军情专项抓包（20260726_173635）回归；断言对照口述时间线。

    - 17:40 出征副本宦官乱政 → 军情出现【副本】…战斗进行中
    - 17:46 出征 7 级山贼，先“还没到”再“战斗进行中”，17:48 变返回
    - 17:51 攻占牧场，先“还在行军中”，17:53“战斗进行中”，17:55 驻守
    """

    def test_dungeon_stage_battle_is_parsed_from_0x8600(self) -> None:
        """副本关卡战斗真实出现在军情列表里（targetType=0x0e，目标是关卡名）。"""
        action = only_action(CAP_JQ, 42)
        self.assertEqual(action["tag"], "副本")
        self.assertEqual(action["state"], "战斗")
        self.assertIn("参与副本关卡宦官乱政，战斗进行中", action["text"])
        self.assertEqual(action["targetName"], "宦官乱政")
        self.assertEqual(action["targetType"], 14)
        self.assertEqual(action["targetTypeText"], "副本关卡")
        self.assertEqual(len(action["generalIds"]), 5)
        # 0x17 副本尾部：无行军，剩余恒为 0，不能拿时间戳当倒计时。
        self.assertEqual(action["marchValue"], 0)

    def test_multiplayer_dungeon_team_without_battle_is_prep_state(self) -> None:
        """广宗决战（章末多人副本）建队后未开战：只算“备战”，不冒充战斗。"""
        action = only_action(CAP_JQ, 3)
        self.assertEqual(action["tag"], "副本")
        self.assertEqual(action["state"], "备战")
        self.assertNotIn("战斗进行中", action["text"])
        self.assertEqual(action["targetName"], "广宗决战")

    def test_bandit_march_uses_0x0b_tail_and_reports_marching(self) -> None:
        """打山贼去程尾部是 0x0b：没到目标前是“出征”，不是“战斗”。"""
        action = only_action(CAP_JQ, 81)
        self.assertEqual(action["tag"], "消灭")
        self.assertEqual(action["state"], "出征")
        self.assertNotIn("战斗进行中", action["text"])
        self.assertEqual(action["targetName"], "7级山贼(103,29)")
        self.assertEqual((action["x"], action["y"]), (103, 29))
        self.assertEqual(action["targetType"], 3)
        self.assertEqual(action["targetTypeText"], "山贼")
        self.assertEqual(action["marchKindText"], "去程")
        self.assertEqual(action["marchValue"], 32068)

    def test_bandit_battle_in_progress_has_zero_remaining(self) -> None:
        action = only_action(CAP_JQ, 84)
        self.assertEqual(action["state"], "战斗")
        self.assertIn("战斗进行中", action["text"])
        self.assertEqual(action["marchValue"], 0)

    def test_mine_outbound_march_is_reported_as_marching(self) -> None:
        """操作者口述“还在行军中”的攻占记录必须是“出征”态并带剩余时间。"""
        action = only_action(CAP_JQ, 128)
        self.assertEqual(action["tag"], "攻占")
        self.assertEqual(action["state"], "出征")
        self.assertEqual(action["targetName"], "牧场(1级)")
        self.assertEqual((action["x"], action["y"]), (92, 26))
        self.assertEqual(action["marchKindText"], "去程")
        self.assertEqual(action["marchValue"], 93949)
        self.assertEqual(action["eventTimeMs"], 1785059585543)

    def test_mine_battle_after_arrival_flips_to_fight_state(self) -> None:
        """同一 battleId 抵达后带“战斗进行中”后缀，状态推进为战斗。"""
        marching = only_action(CAP_JQ, 128)
        fighting = only_action(CAP_JQ, 137)
        self.assertEqual(fighting["battleId"], marching["battleId"])
        self.assertEqual(fighting["state"], "战斗")
        self.assertIn("战斗进行中", fighting["text"])
        self.assertEqual(fighting["marchValue"], 0)

    def test_outbound_march_value_decreases_with_fixed_eta(self) -> None:
        """去程连续刷新：marchValue 递减、eventTimeMs（预计到达）恒定。"""
        flows = [128, 131, 133, 134]
        actions = [only_action(CAP_JQ, flow) for flow in flows]
        values = [action["marchValue"] for action in actions]
        self.assertEqual(values, [93949, 57857, 41442, 22448])
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertEqual({action["eventTimeMs"] for action in actions}, {1785059585543})

    def test_return_march_value_decreases_with_fixed_eta(self) -> None:
        """回程连续刷新同样是“剩余递减 + 到家时刻恒定”。"""
        actions = [only_action(CAP_JQ, flow) for flow in (106, 107, 109)]
        self.assertEqual(
            [action["marchValue"] for action in actions],
            [38322, 24407, 13988],
        )
        self.assertEqual({action["eventTimeMs"] for action in actions}, {1785059338986})
        for action in actions:
            self.assertEqual(action["state"], "返回")
            self.assertEqual(action["marchKindText"], "回程")

    def test_garrison_record_still_parses_without_march_tail(self) -> None:
        action = only_action(CAP_JQ, 147)
        self.assertEqual(action["state"], "驻守")
        self.assertEqual(action["targetName"], "1级牧场")
        self.assertNotIn("eventTimeMs", action)

    def test_confirmed_empty_intel_yields_zero_actions(self) -> None:
        """口述“已经没有将领在出征或者战斗了”的 0x8600 必须解析出 0 条。"""
        packets = SERVER.parse_response(
            (CTF_OUT / CAP_JQ / "live_analyzed" / "050" / "resp.bin").read_bytes()
        )
        payload = next(
            packet["payload"] for packet in packets
            if packet.get("opcode") == 0x8600
        )
        self.assertEqual(SERVER.parse_8600_military_actions(payload, []), [])

    def test_tail_exposes_owned_captive_and_troop_state_without_unknown_bytes(self) -> None:
        parsed = SERVER.parse_8600_military_payload(
            payload_8600(CAP_JQ, 50),
            [],
        )
        self.assertTrue(parsed["trailingEvidenceParsed"])
        self.assertEqual(parsed["unparsedTailByteCount"], 0)
        self.assertEqual(len(parsed["generalStatusRecords"]), 14)
        self.assertEqual(len(parsed["captiveGeneralRecords"]), 19)
        self.assertEqual(parsed["troopAssignmentCount"], 6)
        attack_bow = next(
            row for row in parsed["generalStatusRecords"]
            if row.get("name") == "攻弓1"
        )
        self.assertEqual(attack_bow["status"], 0)
        self.assertEqual(attack_bow["currentSoldierCount"], 1121)
        captive = next(
            row for row in parsed["captiveGeneralRecords"]
            if row.get("name") == "樊星"
        )
        self.assertEqual(captive["status"], 3)
        self.assertEqual(captive["captureFiefId"], 205)
        self.assertEqual(captive["captureFiefName"], "利萍丰基地")

        active = SERVER.parse_8600_military_payload(
            payload_8600(CAP_JQ, 42),
            [],
        )
        self.assertEqual(
            active["activeBattleReferences"],
            [{"battleId": 9_005_825, "flag": 0}],
        )
        self.assertEqual(active["unparsedTailByteCount"], 0)


class DungeonMultiplayerFinalStageTests(unittest.TestCase):
    """章末关是多人副本：单人流程必须跳过/拒绝（抓包 20260726_173635）。"""

    def test_clear_mode_skips_chapter_final_stage(self) -> None:
        catalog = {
            "chapters": [
                {
                    "chapterId": 0,
                    "displayChapter": 1,
                    "detailFlag": 1,
                    "stages": [
                        {"displayStage": stage, "stageCode": stage + 9,
                         "available": True,
                         "resultCode": 1 if stage <= 11 else 255}
                        for stage in range(1, 13)
                    ],
                },
                {
                    "chapterId": 1,
                    "displayChapter": 2,
                    "detailFlag": 1,
                    "stages": [
                        {"displayStage": 1, "stageCode": 3,
                         "available": True, "resultCode": 255},
                    ],
                },
            ],
        }
        result = SERVER.first_uncompleted_dungeon_stage(catalog)
        # 第1章第12关（广宗决战，多人）未通关也要跳过，直接推进第2章第1关。
        self.assertEqual(result["chapter"], 1)
        self.assertEqual(result["stage"], 1)

    def test_all_solo_stages_cleared_reports_none(self) -> None:
        catalog = {
            "chapters": [{
                "chapterId": 0,
                "displayChapter": 1,
                "detailFlag": 1,
                "stages": [
                    {"displayStage": stage, "stageCode": stage + 9,
                     "available": True,
                     "resultCode": 1 if stage <= 11 else 255}
                    for stage in range(1, 13)
                ],
            }],
        }
        self.assertIsNone(SERVER.first_uncompleted_dungeon_stage(catalog))

    def test_execute_dungeon_refuses_chapter_final_stage(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            SERVER.execute_dungeon(
                {"sessionId": "x"},
                {"confirm": "dungeon", "generalIds": ["1"],
                 "chapter": "第一章", "stage": 12},
            )
        self.assertIn("多人副本", str(ctx.exception))


class MilitarySnapshotTests(unittest.TestCase):
    def test_incoming_raid_is_deduplicated_and_sorted_first(self) -> None:
        incoming = {"opcode": 0x8600, "payload": incoming_raid_payload()}
        fighting = {
            "opcode": 0x8600,
            "payload": payload_8600(CAP_CRY, 41),
        }
        snapshot = SERVER.parse_military_snapshot_from_packets(
            {}, [fighting, incoming, incoming], 200,
        )
        self.assertEqual(snapshot["actionCount"], 2)
        self.assertEqual(snapshot["incomingCount"], 1)
        self.assertEqual(
            [item["state"] for item in snapshot["actions"]],
            ["来袭", "战斗"],
        )

    def test_snapshot_marks_responded_and_sorts_by_state(self) -> None:
        sess: dict = {"generals": [{"id": 0xFACF09, "name": "步1"}]}
        packets = [
            {"opcode": 0x8600, "payload": payload_8600(CAP_CRY, 70)},   # 返回
            {"opcode": 0x8600, "payload": payload_8600(CAP_MU, 100)},   # 战斗
            {"opcode": 0x8600, "payload": payload_8600(CAP_BIN, 308)},  # 驻守
        ]
        snapshot = SERVER.parse_military_snapshot_from_packets(sess, packets, 200)
        self.assertTrue(snapshot["responded"])
        self.assertEqual(snapshot["sourceOpcode"], "0x1600/0x8600")
        self.assertEqual(snapshot["actionCount"], 3)
        self.assertEqual(
            [item["state"] for item in snapshot["actions"]],
            ["战斗", "驻守", "返回"],
        )
        self.assertIs(sess["militarySnapshot"], snapshot)

    def test_same_battle_is_not_listed_twice(self) -> None:
        sess: dict = {}
        packets = [
            {"opcode": 0x8600, "payload": payload_8600(CAP_CRY, 41)},
            {"opcode": 0x8600, "payload": payload_8600(CAP_CRY, 43)},
        ]
        snapshot = SERVER.parse_military_snapshot_from_packets(sess, packets, 200)
        self.assertEqual(snapshot["actionCount"], 1)

    def test_missing_8600_is_reported_as_not_responded(self) -> None:
        """没拿到 0x8600 时不能把空列表当成“确认无军情”。"""
        sess: dict = {}
        snapshot = SERVER.parse_military_snapshot_from_packets(sess, [], 200)
        self.assertFalse(snapshot["responded"])
        self.assertEqual(snapshot["actions"], [])

    def test_snapshot_is_never_persisted_across_restart(self) -> None:
        self.assertIn("militarySnapshot", SERVER.RUNTIME_TRANSIENT_SESSION_FIELDS)
        sess = {"sessionId": "x", "militarySnapshot": {"actions": [1]}}
        self.assertNotIn("militarySnapshot", SERVER.runtime_session_snapshot(sess))


class MilitaryIncomingUiTests(unittest.TestCase):
    def test_incoming_card_exposes_warning_and_arrival_fields(self) -> None:
        app_js = (ROOT / "电脑端辅助前端" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "电脑端辅助前端" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('"来袭": "junqing-state-incoming"', app_js)
        self.assertIn("来袭玩家：", app_js)
        self.assertIn("距来袭剩余", app_js)
        self.assertIn("预计到达：", app_js)
        self.assertIn("封地 ID", app_js)
        self.assertIn(".junqing-state-incoming", styles)
        self.assertIn(".junqing-incoming-card", styles)


if __name__ == "__main__":
    unittest.main()
