from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dataclasses import replace

from dwpm_core.automation import BLOCKED_STATES, FEATURE_LABELS
from dwpm_core.facade import CoreFacade
from dwpm_core.ports import PlatformPorts


class MovableClock:
    def __init__(self, value: int = 1_700_000_000_000) -> None:
        self.value = value

    def now_millis(self) -> int:
        return self.value

    def advance(self, millis: int) -> None:
        self.value += millis


class RecordingLogPort:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def write(self, event) -> None:
        self.events.append(dict(event))

    def user_messages(self) -> list[str]:
        return [
            str(event.get("message"))
            for event in self.events
            if str(event.get("audience") or "") == "user"
        ]


class SharedUserLogNarrationTests(unittest.TestCase):
    """The runtime panel is an operator surface; only deliberate lines may claim it.

    Every other log this core writes is a trace, and the Android host treats an
    unmarked line as one. These tests pin what does and does not get marked.
    """

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.logs = RecordingLogPort()
        self.clock = MovableClock()
        self.facade = CoreFacade(
            ROOT / "shared_core",
            str(Path(self.directory.name) / "operations.json"),
            ports=replace(PlatformPorts(), logs=self.logs, clock=self.clock),
        )
        self.facade.account_record_upsert({
            "accountRef": "176",
            "id": 176,
            "enabled": True,
            "loginState": "ONLINE",
            "platformKey": "sglm",
            "serverId": "server-352",
            "serverName": "区352",
            "session": {"accountId": 176, "sourceMode": 1, "publicState": {}},
        })
        self.logs.events.clear()

    def tearDown(self) -> None:
        self.facade.close()
        self.directory.cleanup()

    def test_a_success_record_is_narrated_as_one_finished_sentence(self) -> None:
        self.facade._append_success_record(  # noqa: SLF001
            "176",
            {
                "category": "活血丹",
                "message": "统弓2 使用1枚活血丹，体力25→75，来源将领维护",
                "dedupeKey": "general:energy:1:1",
            },
        )

        self.assertEqual(
            ["活血丹：统弓2 使用1枚活血丹，体力25→75，来源将领维护"],
            self.logs.user_messages(),
        )

    def test_a_deduplicated_record_is_not_narrated_twice(self) -> None:
        record = {
            "category": "刷黄",
            "message": "编队1 出征成功",
            "dedupeKey": "brush:battle:9001",
        }
        self.facade._append_success_record("176", dict(record))  # noqa: SLF001
        self.facade._append_success_record("176", dict(record))  # noqa: SLF001

        self.assertEqual(["刷黄：编队1 出征成功"], self.logs.user_messages())

    def test_a_blocked_feature_is_announced_once_and_its_recovery_once(self) -> None:
        for _ in range(3):
            self.facade._save_resident_automation_state(  # noqa: SLF001
                "176",
                {"brush": {"lastState": "blocked", "lastMessage": "体力不足"}},
            )
            self.clock.advance(30_000)
        for _ in range(3):
            self.facade._save_resident_automation_state(  # noqa: SLF001
                "176",
                {"brush": {"lastState": "running", "lastMessage": "出征中"}},
            )
            self.clock.advance(30_000)

        self.assertEqual(
            ["刷黄已暂停：体力不足", "刷黄已恢复运行"],
            self.logs.user_messages(),
        )

    def test_a_condition_that_flaps_faster_than_it_holds_is_never_announced(
        self,
    ) -> None:
        # 刷黄 re-samples for targets every few seconds; it flipped twelve times in
        # four minutes one morning. Every flip is a real state change and would
        # make a truthful line, and the whole burst carries no information: the
        # condition never changed, it was only looked at again.
        for _ in range(6):
            for state in ("no-targets", "running"):
                self.facade._save_resident_automation_state(  # noqa: SLF001
                    "176",
                    {"brush": {"lastState": state, "lastMessage": "本轮无目标"}},
                )
                self.clock.advance(13_000)

        self.assertEqual([], self.logs.user_messages())

    def test_a_condition_that_holds_still_reports_its_recovery(self) -> None:
        for _ in range(2):
            self.facade._save_resident_automation_state(  # noqa: SLF001
                "176",
                {"brush": {"lastState": "no-targets", "lastMessage": "本轮无目标"}},
            )
            self.clock.advance(10 * 60_000)
        self.facade._save_resident_automation_state(  # noqa: SLF001
            "176",
            {"brush": {"lastState": "running", "lastMessage": "出征中"}},
        )

        self.assertEqual(
            ["刷黄暂时没有可打的目标，稍后自动重试", "刷黄已恢复运行"],
            self.logs.user_messages(),
        )

    def test_states_that_mean_work_is_under_way_are_not_narrated(self) -> None:
        # The success record that follows is the news; announcing "running" first
        # would only say the same thing twice.
        for state in ("running", "fighting", "dispatched", "waiting", "idle"):
            self.facade._save_resident_automation_state(  # noqa: SLF001
                "176",
                {"brush": {"lastState": state, "lastMessage": f"内部状态 {state}"}},
            )

        self.assertEqual([], self.logs.user_messages())

    def test_an_idle_feature_explains_itself_rather_than_going_silent(self) -> None:
        # Ten of these appeared overnight. Without a line the operator sees an empty
        # panel and cannot tell "没有目标" apart from "助手挂了".
        for _ in range(4):
            self.facade._save_resident_automation_state(  # noqa: SLF001
                "176",
                {"brush": {"lastState": "no-targets", "lastMessage": "本轮无目标"}},
            )
            self.clock.advance(30_000)

        self.assertEqual(
            ["刷黄暂时没有可打的目标，稍后自动重试"],
            self.logs.user_messages(),
        )

    def test_a_pause_with_no_stated_reason_does_not_end_in_a_dangling_colon(
        self,
    ) -> None:
        self.facade._save_resident_automation_state(  # noqa: SLF001
            "176",
            {"brush": {"lastState": "blocked", "lastMessage": ""}},
        )

        self.assertEqual(["刷黄已暂停"], self.logs.user_messages())

    def test_an_unknown_feature_key_is_never_narrated_under_its_internal_name(
        self,
    ) -> None:
        self.facade._save_resident_automation_state(  # noqa: SLF001
            "176",
            {"someFutureFeature": {"lastState": "blocked", "lastMessage": "x"}},
        )

        self.assertEqual([], self.logs.user_messages())

    def test_every_blocked_state_has_a_label_for_the_features_it_can_block(
        self,
    ) -> None:
        # A narrated line names a feature from one table; a missing entry would
        # silently drop the announcement rather than print "domestic".
        for feature in ("brush", "dungeon", "lossless", "mine"):
            self.assertIn(feature, FEATURE_LABELS)
        self.assertEqual({"blocked", "defeat-paused"}, set(BLOCKED_STATES))

    def test_narration_never_fails_the_work_it_narrates(self) -> None:
        class BrokenLogPort:
            def write(self, event) -> None:
                raise RuntimeError("log sink unavailable")

        self.facade._ports = replace(  # noqa: SLF001
            self.facade._ports, logs=BrokenLogPort()  # noqa: SLF001
        )

        saved = self.facade._save_resident_automation_state(  # noqa: SLF001
            "176",
            {"brush": {"lastState": "blocked", "lastMessage": "体力不足"}},
        )

        self.assertEqual("blocked", saved["brush"]["lastState"])

    def test_a_daily_task_that_stops_itself_says_which_one_and_why(
        self,
    ) -> None:
        """日常 is seven tasks, and each has to be able to name itself.

        Their states live one level down, under their own keys, so the
        top-level narration loop found no ``lastState`` and no label for
        "daily" and said nothing.  A daily task that blocks itself for a whole
        cycle on an unreadable receipt is precisely what the operator needs
        told - 签到/领币/俸禄 just do not happen, for hours, silently.
        """

        self.facade._save_resident_automation_state(  # noqa: SLF001
            "176",
            {
                "daily": {
                    "autoSignIn": {
                        "lastState": "uncertain",
                        "lastMessage": (
                            "此前日常请求回执不明，当前周期禁止自动重放"
                        ),
                    },
                    "salary": {"lastState": "completed"},
                }
            },
        )

        self.assertEqual(
            ["签到已暂停：此前日常请求回执不明，当前周期禁止自动重放"],
            self.logs.user_messages(),
        )

        # And the recovery names the same task, not "日常".
        self.logs.events.clear()
        self.facade._save_resident_automation_state(  # noqa: SLF001
            "176",
            {"daily": {"autoSignIn": {"lastState": "completed"}}},
        )
        self.assertEqual(["签到已恢复运行"], self.logs.user_messages())

    def test_a_lost_mine_round_is_narrated_so_the_notice_page_raises_it(
        self,
    ) -> None:
        """Neither host has a "this feature failed" channel.

        The 角色-提示 page is derived from user log text: it matches the feature
        name against 失败/异常/中止/暂停/未完成 and clears the entry on 完成/
        成功.  So a lost 打矿 round becomes a notice by being narrated in those
        words, and the next round's 撤回 line clears it - no separate notice
        plumbing, and no divergence between the desktop and Android hosts.
        """

        self.facade._write_user_log(  # noqa: SLF001
            "176",
            self.facade._mine_occupation_failure_text(  # noqa: SLF001
                {"sourceRowIndex": 0},
                {"name": "1级镔铁矿", "x": 88, "y": 24},
                41511996,
            ),
        )

        self.assertEqual(
            [
                "打矿：编队1 占领失败，将领已自行返回 > "
                "1级镔铁矿(88，24)（battleId=41511996）"
            ],
            self.logs.user_messages(),
        )
        line = self.logs.user_messages()[0]
        self.assertIn("打矿", line, "the notice is matched by feature name")
        self.assertIn("失败", line, "and raised by this word")

    def test_a_machine_event_carries_no_user_audience(self) -> None:
        self.facade._publish_operation_event(  # noqa: SLF001
            {
                "kind": "automation:recovery-tick:v1",
                "status": "RUNNING",
                "progress": 40,
                "operationId": "op_fixture",
            }
        )

        self.assertEqual([], self.logs.user_messages())
        self.assertTrue(self.logs.events)


if __name__ == "__main__":
    unittest.main()
