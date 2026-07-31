"""军情页“辅助此刻行动”（assistant_live_operations）回归。

军情页的 0x1600/0x8600 只反映野外军情，副本战斗和正在发起的出征看不到。
assistant_live_operations 从任务引擎真实运行时状态汇总“辅助此刻在做什么”。

下面用例的数据形态取自 2026-07-26 正在运行的辅助真实日志
（reports/assistant_state.sqlite3 account_logs / success_records）：

- 副本任务：攻弓2,智步4,智步5,智步6,骑1 → 第1章第12关，
  “指挥中心：已取得出征权，任务=dungeon” → “副本战斗轮询：状态=1 active=True”
- 刷黄任务：灰1(1883002)、车1(1883001)，目标 山贼 6、7级

断言遵循与军情页相同的底线：状态只来自将领真实忙闲（征/战/防/返），
将领全部回闲的在途记录不再展示，不把已结束的行动冒充“此刻”。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"

SPEC = importlib.util.spec_from_file_location("dwpm_server_assistant_ops_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


SID = "sess-assistant-ops-test"


def make_sess(statuses: dict[str, str]) -> dict:
    """statuses: 将领名 → displayStatus（闲/征/战/防/返）。"""
    generals = []
    by_name_id = {
        "灰1": 1883002, "车1": 1883001,
        "攻弓2": 3755035, "智步4": 3752041, "智步5": 3755036,
        "智步6": 3758051, "骑1": 172738,
    }
    for name, general_id in by_name_id.items():
        generals.append({
            "id": general_id,
            "idHex": f"{general_id:016x}",
            "name": name,
            "displayStatus": statuses.get(name, "闲"),
        })
    return {"sessionId": SID, "generals": generals}


def brush_task(*, general_ids: list[str], flight_extra: dict | None = None) -> dict:
    flight = {
        "cycleNo": 3,
        "ruleIndex": 0,
        "generalIds": list(general_ids),
        "target": {"name": "山贼", "level": 6, "kind": "山贼", "x": 92, "y": 25},
        "battleId": 555001,
        "dispatchedAt": 1_785_000_000_000,
    }
    flight.update(flight_extra or {})
    return {
        "taskId": "task-brush",
        "type": "auto-brush-yellow",
        "status": "running",
        "sessionId": SID,
        "schedulerState": "checking",
        "schedulerGeneralIds": list(general_ids),
        "schedulerUpdatedAt": 1_785_000_100_000,
        "brushInFlight": {"0": flight},
    }


def dungeon_task(*, state: str, with_battle: bool) -> dict:
    general_ids = ["3755035", "3752041", "3755036", "3758051", "172738"]
    task = {
        "taskId": "task-dungeon",
        "type": "dungeon",
        "status": "running",
        "sessionId": SID,
        "schedulerState": state,
        "schedulerGeneralIds": list(general_ids),
        "schedulerUpdatedAt": 1_785_000_200_000,
        "currentCycle": 9,
        "currentDungeonStage": {
            "chapter": 0, "chapterName": "第1章", "stage": 12, "stageCode": 12,
        },
    }
    if with_battle:
        task["currentDungeonBattle"] = {
            "chapterName": "第1章",
            "stage": 12,
            "generalIds": list(general_ids),
            "startedAt": 1_785_000_150_000,
            "battleId": 777001,
        }
    return task


def mine_task(*, state: str) -> dict:
    return {
        "taskId": "task-mine",
        "type": "auto-mine",
        "status": "running",
        "sessionId": SID,
        "schedulerState": state,
        "schedulerGeneralIds": ["1883001"],
        "schedulerUpdatedAt": 1_785_000_300_000,
        "cycle": 2,
        "lastTarget": {"name": "1级镔铁矿", "x": 95, "y": 30},
        "lastResult": {"success": True, "successBattleId": 888001},
    }


class AssistantLiveOperationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_tasks = dict(SERVER.AUTO_TASKS)
        SERVER.AUTO_TASKS.clear()

    def tearDown(self) -> None:
        SERVER.AUTO_TASKS.clear()
        SERVER.AUTO_TASKS.update(self._saved_tasks)

    def install(self, *tasks: dict) -> None:
        for task in tasks:
            SERVER.AUTO_TASKS[task["taskId"]] = task

    # --- 刷黄在途编队 -------------------------------------------------------

    def test_brush_flight_in_battle_reports_bandit_fight(self) -> None:
        self.install(brush_task(general_ids=["1883002", "1883001"]))
        sess = make_sess({"灰1": "战", "车1": "战"})
        ops = SERVER.assistant_live_operations(sess)
        self.assertEqual(len(ops), 1)
        op = ops[0]
        self.assertEqual(op["state"], "战斗")
        self.assertEqual(op["taskName"], "刷黄")
        self.assertEqual(op["targetText"], "6级山贼(92,25)")
        self.assertEqual(op["text"], "灰1、车1 正在与6级山贼(92,25)战斗")
        self.assertEqual(op["battleId"], 555001)
        self.assertEqual(op["cycleNo"], 3)
        self.assertEqual(op["startedAt"], 1_785_000_000_000)

    def test_brush_flight_marching_reports_expedition(self) -> None:
        self.install(brush_task(general_ids=["1883002", "1883001"]))
        sess = make_sess({"灰1": "征", "车1": "征"})
        ops = SERVER.assistant_live_operations(sess)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["state"], "出征")
        self.assertEqual(ops[0]["text"], "灰1、车1 正在出征6级山贼(92,25)")

    def test_brush_flight_returning_reports_return(self) -> None:
        self.install(brush_task(general_ids=["1883002", "1883001"]))
        sess = make_sess({"灰1": "返", "车1": "返"})
        ops = SERVER.assistant_live_operations(sess)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["state"], "返回")
        self.assertEqual(ops[0]["text"], "灰1、车1 正在从6级山贼(92,25)返回")

    def test_brush_flight_with_idle_generals_is_not_an_operation(self) -> None:
        """将领已全部回闲：只剩战后维护，不能冒充“此刻的军事行动”。"""
        self.install(brush_task(general_ids=["1883002", "1883001"]))
        sess = make_sess({})
        self.assertEqual(SERVER.assistant_live_operations(sess), [])

    # --- 副本战斗 -----------------------------------------------------------

    def test_dungeon_fighting_reports_stage_battle(self) -> None:
        self.install(dungeon_task(state="fighting", with_battle=True))
        sess = make_sess({name: "战" for name in ("攻弓2", "智步4", "智步5", "智步6", "骑1")})
        ops = SERVER.assistant_live_operations(sess)
        self.assertEqual(len(ops), 1)
        op = ops[0]
        self.assertEqual(op["state"], "战斗")
        self.assertEqual(op["taskName"], "副本")
        self.assertEqual(op["targetText"], "副本第1章第12关")
        self.assertEqual(
            op["text"],
            "攻弓2、智步4、智步5、智步6、骑1 正在与副本第1章第12关战斗",
        )
        self.assertEqual(op["battleId"], 777001)
        self.assertEqual(op["cycleNo"], 9)
        self.assertEqual(op["startedAt"], 1_785_000_150_000)

    def test_dungeon_fighting_without_marker_falls_back_to_stage(self) -> None:
        """战斗标记缺失时退回 currentDungeonStage，不因此丢掉副本军情。"""
        self.install(dungeon_task(state="fighting", with_battle=False))
        sess = make_sess({name: "战" for name in ("攻弓2", "智步4", "智步5", "智步6", "骑1")})
        ops = SERVER.assistant_live_operations(sess)
        self.assertEqual(len(ops), 1)
        self.assertIn("正在与副本第1章第12关战斗", ops[0]["text"])

    def test_dungeon_dispatching_reports_preparation(self) -> None:
        self.install(dungeon_task(state="dispatching", with_battle=False))
        sess = make_sess({})
        ops = SERVER.assistant_live_operations(sess)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["state"], "准备")
        self.assertIn("正在准备副本第1章第12关出征", ops[0]["text"])

    def test_dungeon_idle_scheduler_state_produces_no_operation(self) -> None:
        self.install(dungeon_task(state="checking", with_battle=False))
        sess = make_sess({})
        self.assertEqual(SERVER.assistant_live_operations(sess), [])

    # --- 打矿 --------------------------------------------------------------

    def test_mine_defending_reports_garrison_at_target(self) -> None:
        self.install(mine_task(state="fighting"))
        sess = make_sess({"车1": "防"})
        ops = SERVER.assistant_live_operations(sess)
        self.assertEqual(len(ops), 1)
        op = ops[0]
        self.assertEqual(op["state"], "驻守")
        self.assertEqual(op["taskName"], "打矿")
        self.assertEqual(op["text"], "车1 正在驻守1级镔铁矿(95,30)")
        self.assertEqual(op["battleId"], 888001)

    # --- 汇总行为 ----------------------------------------------------------

    def test_operations_sort_battle_first_preparation_last(self) -> None:
        self.install(
            dungeon_task(state="dispatching", with_battle=False),
            brush_task(general_ids=["1883002"]),
            mine_task(state="fighting"),
        )
        sess = make_sess({"灰1": "战", "车1": "防"})
        states = [op["state"] for op in SERVER.assistant_live_operations(sess)]
        self.assertEqual(states, ["战斗", "驻守", "准备"])

    def test_other_sessions_and_stopped_tasks_are_excluded(self) -> None:
        other = brush_task(general_ids=["1883002"])
        other["taskId"] = "task-other-session"
        other["sessionId"] = "some-other-session"
        stopped = brush_task(general_ids=["1883002"])
        stopped["taskId"] = "task-stopped"
        stopped["status"] = "stopped"
        self.install(other, stopped)
        sess = make_sess({"灰1": "战"})
        self.assertEqual(SERVER.assistant_live_operations(sess), [])

    def test_operations_are_json_serializable(self) -> None:
        self.install(
            dungeon_task(state="fighting", with_battle=True),
            brush_task(general_ids=["1883002", "1883001"]),
        )
        sess = make_sess({"灰1": "战", "车1": "战", "攻弓2": "战"})
        payload = json.dumps(SERVER.assistant_live_operations(sess), ensure_ascii=False)
        self.assertIn("正在与", payload)

    def test_empty_session_id_yields_no_operations(self) -> None:
        self.install(brush_task(general_ids=["1883002"]))
        self.assertEqual(SERVER.assistant_live_operations({"sessionId": ""}), [])


if __name__ == "__main__":
    unittest.main()
