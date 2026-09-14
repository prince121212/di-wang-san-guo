"""A troop shortfall is the account's state, not an unconfirmed operation.

Observed on a real phone: 打矿's preflight healed a general (one request,
receipt accepted) and then refused to march because 智步1 was twelve 近卫兵
short of its saved formation.  Nothing after the heal was sent.  The workflow
kept the pending record with ``requiresAttention`` because *something* had
been sent during preflight, the send-boundary probe isolated 打矿 on every
tick, and the 提示 page read "自动打矿存在未确认操作，已隔离并禁止自动重发，
请人工核对后处理" - for a condition the account holder could only end by
recruiting or lowering a number, and which the text never mentioned.

Three rules replace that:

* a preflight that ends in a *known* failure has nothing in flight, so its
  pending record is closed whether or not an earlier step was sent;
* a saved formation short of idle troops pauses that general's formations
  for a fixed window, exactly like stamina does, and says what ends it;
* a ledger a previous build left in that state is settled on first sight.
"""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core import CoreFacade  # noqa: E402
from dwpm_core.features.formation import (  # noqa: E402
    TroopShortageError,
    plan_troop_assignment,
)
from dwpm_core.operations import OperationKnownFailureError  # noqa: E402
from dwpm_core.ports import PlatformPorts  # noqa: E402


PAUSE_MILLIS = 30 * 60 * 1000
GENERAL_ID = 1826336
GENERAL_NAME = "智步1"


class FixedClock:
    def __init__(self, value: int = 10_000_000) -> None:
        self.value = int(value)

    def now_millis(self) -> int:
        return self.value


class RecordingLogPort:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event) -> None:
        self.events.append(dict(event))

    def user_messages(self) -> list[str]:
        return [
            str(event.get("message"))
            for event in self.events
            if str(event.get("audience") or "") == "user"
        ]


class FakeExecution:
    operation_id = "op_troop_pause_fixture"

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def mark_request_sent(self, metadata=None) -> None:
        self.sent.append(dict(metadata or {}))

    def publish_progress(self, progress: int, details=None) -> None:
        return None

    def raise_if_cancelled(self) -> None:
        return None

    def wait(self, _seconds: float) -> None:
        return None


def _general(general_id: int = GENERAL_ID, name: str = GENERAL_NAME) -> dict:
    return {
        "id": general_id,
        "idHex": f"{general_id:016x}",
        "name": name,
        "status": 0,
        "statusText": "闲",
        "displayStatus": "闲",
        "fiefId": 500,
        "placeID": 500,
        "energyReliable": True,
        "tili": 300,
        "tiliLimit": 300,
        "loyalty": 100,
        "loyaltyLimit": 100,
        "troopLimit": 699,
        # Carrying a different type, so none of it counts toward the target.
        "soldierTypeCode": 3,
        "soldierCount": 100,
        "currentSoldierCount": 100,
    }


#: 687 idle 近卫兵 against a saved formation of 699: twelve short.
ARMY = [{"soldierTypeCode": 7, "idleCount": 687}]
FORMATION_RULE = {
    "generalId": str(GENERAL_ID),
    "soldierType": "近卫兵",
    "soldierCount": 699,
}


class TroopShortagePauseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FixedClock()
        self.logs = RecordingLogPort()
        self.directory = tempfile.TemporaryDirectory()
        self.facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(
                Path(self.directory.name) / "operations.json"
            ),
            ports=replace(PlatformPorts(), clock=self.clock, logs=self.logs),
        )
        self.facade.account_record_upsert({
            "accountRef": "202",
            "id": 202,
            "username": "troop-pause-fixture",
            "serverName": "fixture",
            "enabled": True,
            "loginState": "ONLINE",
            "session": {
                "accountId": 202,
                "sourceMode": 1,
                "publicState": {
                    "roleId": "202",
                    "gameHttp": "https://fixture.invalid/game",
                    "lastValidatedAt": str(self.clock.value),
                    "savedTasksStarted": "true",
                    "activeResidentTaskKeys": "mine",
                    "generalsJson": "[]",
                    "militarySnapshotJson": '{"actions":[]}',
                },
            },
        })
        self.facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
            lambda _self, *_args, **_kwargs: ("", [_general()], list(ARMY)),
            self.facade,
        )
        self.logs.events.clear()

    def tearDown(self) -> None:
        self.facade.close()
        self.directory.cleanup()

    def _public(self) -> dict:
        stored = json.loads(self.facade.account_record_json("202"))["account"]
        return stored["session"]["publicState"]

    def _ledger(self) -> dict:
        return json.loads(self._public().get("generalEnergyCooldownJson") or "{}")

    def _preflight_body(self) -> dict:
        return {
            "accountRef": "202",
            "generalIds": [GENERAL_ID],
            "formationRules": [dict(FORMATION_RULE)],
            "hostSettings": {"config": {"healWounded": False}},
        }

    def _run_preflight(self, execution=None):
        return self.facade._run_expedition_preflight(  # noqa: SLF001
            execution or FakeExecution(),
            "202",
            self._preflight_body(),
            {},
            action_name="打矿",
            require_full_loyalty=False,
        )

    # -- the origin ---------------------------------------------------------

    def test_the_planner_names_the_shortfall_instead_of_only_describing_it(self) -> None:
        with self.assertRaises(TroopShortageError) as caught:
            plan_troop_assignment(
                [_general()],
                ARMY,
                {"generalId": GENERAL_ID, "soldierType": "近卫兵", "soldierCount": 699},
                self.facade._behavior_contract["formation"],  # noqa: SLF001
            )
        error = caught.exception
        self.assertEqual(error.details(), {
            "generalId": GENERAL_ID,
            "generalName": GENERAL_NAME,
            "soldierTypeCode": 7,
            "soldierType": "近卫兵",
            "targetCount": 699,
            "availableCount": 687,
            "shortage": 12,
        })
        # The sentence every existing caller already shows is unchanged.
        self.assertEqual(
            str(error), "智步1缺少12近卫兵；目标699，可用687，已保持原配兵不变"
        )
        self.assertIsInstance(error, ValueError)

    # -- expedition preflight ----------------------------------------------

    def test_a_shortfall_pauses_the_formation_and_says_what_ends_it(self) -> None:
        execution = FakeExecution()
        with self.assertRaises(OperationKnownFailureError) as caught:
            self._run_preflight(execution)
        error = caught.exception

        self.assertEqual(execution.sent, [], "a precheck refusal sends nothing")
        self.assertEqual(error.code, "EXPEDITION_TROOPS_UNAVAILABLE")
        self.assertTrue(error.details["retryableResourceShortage"])
        self.assertTrue(error.details["formationPaused"])
        self.assertEqual(error.details["resource"], "近卫兵")
        self.assertEqual(error.details["generalIds"], [GENERAL_ID])
        self.assertEqual(
            error.details["retryAtMillis"], self.clock.value + PAUSE_MILLIS
        )
        self.assertEqual(error.details["troopShortage"]["shortage"], 12)

        message = str(error)
        self.assertTrue(message.startswith("打矿出征前配兵未完成"), message)
        for fragment in (
            "智步1缺少12近卫兵",
            "保存的配兵为699",
            "当前空闲可用687",
            "招募近卫兵",
            "调低该将领的配兵数量",
            "所在编队已暂停至",
            "之后自动重试",
        ):
            self.assertIn(fragment, message)
        self.assertNotIn("活血丹", message)
        self.assertNotIn("人工", message)

        entry = self._ledger()[str(GENERAL_ID)]
        self.assertEqual(entry["cause"], "troops")
        self.assertEqual(entry["resource"], "近卫兵")
        self.assertEqual(entry["untilMillis"], self.clock.value + PAUSE_MILLIS)
        self.assertEqual(entry["troopShortage"]["availableCount"], 687)

    def test_the_pause_window_comes_from_the_behavior_contract(self) -> None:
        contract = json.loads(
            (ROOT / "shared_core" / "assistant_behavior_contract.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            contract["scheduler"]["troopShortageFormationPauseMillis"],
            PAUSE_MILLIS,
        )

    def test_a_paused_formation_is_refused_from_the_ledger_before_any_read(self) -> None:
        with self.assertRaises(OperationKnownFailureError):
            self._run_preflight()

        def must_not_read(_self, *_args, **_kwargs):
            raise AssertionError("a paused formation must not read game state")

        self.facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
            must_not_read, self.facade
        )
        self.clock.value += 5 * 60 * 1000
        with self.assertRaises(OperationKnownFailureError) as caught:
            self._run_preflight()
        error = caught.exception
        # The ledger remembers *why*: a troop pause must not come back out as
        # the stamina sentence, which would send the holder to the treasury.
        self.assertEqual(error.code, "EXPEDITION_TROOPS_UNAVAILABLE")
        self.assertEqual(error.details["resource"], "近卫兵")
        self.assertIn("智步1缺少12近卫兵", str(error))
        self.assertNotIn("活血丹", str(error))
        self.assertEqual(
            error.details["retryAtMillis"],
            self.clock.value - 5 * 60 * 1000 + PAUSE_MILLIS,
        )

    def test_an_expired_pause_lets_the_formation_be_checked_again(self) -> None:
        with self.assertRaises(OperationKnownFailureError):
            self._run_preflight()
        self.clock.value += PAUSE_MILLIS + 1
        # The barracks were refilled meanwhile: the saved count is reachable.
        self.facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
            lambda _self, *_args, **_kwargs: (
                "",
                [{**_general(), "soldierTypeCode": 7, "soldierCount": 699,
                  "currentSoldierCount": 699}],
                list(ARMY),
            ),
            self.facade,
        )
        selected, _preflight = self._run_preflight()
        self.assertEqual([row["id"] for row in selected], [GENERAL_ID])

    # -- the stamina machinery must not misread a troop pause ---------------

    def test_healthy_stamina_does_not_lift_a_troop_pause(self) -> None:
        with self.assertRaises(OperationKnownFailureError):
            self._run_preflight()
        lifted = self.facade._lift_recovered_energy_cooldowns(  # noqa: SLF001
            "202",
            {GENERAL_ID: _general()},
            {"mine": {"nextWakeAtMillis": self.clock.value + PAUSE_MILLIS}},
            self.clock.value,
        )
        self.assertEqual(lifted, [])
        self.assertIn(str(GENERAL_ID), self._ledger())
        # And the top-up skip that keys on a stamina pause does not see it.
        energy_only = self.facade._general_energy_cooldowns(  # noqa: SLF001
            "202", self.clock.value, cause="energy"
        )
        self.assertEqual(energy_only, {})

    # -- 打矿 execute: a known failure closes the ledger -----------------------

    def _mine_body(self) -> dict:
        return {
            "accountRef": "202",
            "generalIds": [GENERAL_ID],
            "target": {"id": 4242, "x": 88, "y": 24, "mineType": "1级镔铁矿"},
            "formationRules": [dict(FORMATION_RULE)],
            "hostSettings": {"config": {"healWounded": False}},
        }

    def test_a_known_failure_after_a_sent_heal_does_not_hold_the_lane(self) -> None:
        self.facade._mine_resource_capacity_state = types.MethodType(  # noqa: SLF001
            lambda _self, _account_ref: None, self.facade
        )
        real_preflight = self.facade._run_expedition_preflight  # noqa: SLF001

        def heal_then_short(_self, execution, *args, **kwargs):
            # The heal went out and was accepted - a settled fact.  Then the
            # assign precheck refuses without sending.
            execution.mark_request_sent({
                "feature": "troop-heal", "opcode": "0x1224",
            })
            return real_preflight(execution, *args, **kwargs)

        self.facade._run_expedition_preflight = types.MethodType(  # noqa: SLF001
            heal_then_short, self.facade
        )
        with self.assertRaises(OperationKnownFailureError) as caught:
            self.facade._run_mine_execute_game_workflow(  # noqa: SLF001
                FakeExecution(), self._mine_body(), {}
            )
        self.assertEqual(caught.exception.code, "EXPEDITION_TROOPS_UNAVAILABLE")

        public = self._public()
        self.assertEqual(public["minePendingGarrisonJson"], "{}")
        archived = json.loads(public["mineLastPreDispatchFailureJson"])
        self.assertEqual(archived["preDispatchMutationState"], "failed")
        self.assertFalse(archived["requiresAttention"])
        self.assertEqual(archived["preDispatchErrorCode"], "EXPEDITION_TROOPS_UNAVAILABLE")
        self.assertEqual(archived["dispatchSendState"], "not-started")

    # -- resident scheduler: the operator's words --------------------------

    def _mine_configs(self) -> dict:
        return {
            "mine": {
                "enabled": True,
                "settings": {},
                "rows": [{
                    "enabled": True,
                    "sourceRowIndex": 0,
                    "generalIds": [str(GENERAL_ID)],
                    "resourceType": "镔铁矿",
                }],
            },
        }

    def test_the_resident_tick_narrates_the_pause_in_the_holders_words(self) -> None:
        self.facade._update_account_public_state(  # noqa: SLF001
            "202",
            {
                "residentAutomationConfigJson": json.dumps(
                    self._mine_configs(), ensure_ascii=False
                ),
            },
        )
        until = self.clock.value + PAUSE_MILLIS

        def short_mine(_self, *_args, **_kwargs):
            raise OperationKnownFailureError(
                "打矿出征前配兵未完成：将领智步1缺少12近卫兵"
                "（保存的配兵为699，当前空闲可用687），"
                "请在游戏内招募近卫兵或调低该将领的配兵数量；"
                "所在编队已暂停至11:42，之后自动重试",
                code="EXPEDITION_TROOPS_UNAVAILABLE",
                details={
                    "retryableResourceShortage": True,
                    "resource": "近卫兵",
                    "retryAtMillis": until,
                    "formationPaused": True,
                },
            )

        self.facade._run_configured_mine_tick = types.MethodType(  # noqa: SLF001
            short_mine, self.facade
        )
        result = self.facade._run_configured_resident_tick(  # noqa: SLF001
            FakeExecution(), "202", {"allowedFeatures": ["mine"]}
        )

        self.assertEqual(result["feature"], "mine")
        self.assertEqual(result["state"], "formation-paused")
        self.assertFalse(result["requiresAttention"])
        self.assertEqual(result["nextWakeAtMillis"], until)
        state = json.loads(self._public()["residentAutomationStateJson"])
        self.assertEqual(state["mine"]["lastState"], "formation-paused")
        self.assertEqual(state["mine"]["nextWakeAtMillis"], until)

        lines = self.logs.user_messages()
        paused = [line for line in lines if line.startswith("打矿已暂停：")]
        self.assertEqual(len(paused), 1, lines)
        self.assertIn("智步1缺少12近卫兵", paused[0])
        self.assertIn("招募近卫兵或调低该将领的配兵数量", paused[0])
        self.assertNotIn("未确认操作", "".join(lines))
        self.assertNotIn("人工核对", "".join(lines))

        # Marching again is the edge the pause notice was waiting for.
        self.facade._run_configured_mine_tick = types.MethodType(  # noqa: SLF001
            lambda _self, _execution, account_ref, _configs, state, _context: (
                self.facade._save_resident_automation_state(  # noqa: SLF001
                    account_ref,
                    {**state, "mine": {**state.get("mine", {}),
                                       "lastState": "dispatched",
                                       "nextWakeAtMillis": self.clock.value + 60_000}},
                ) and {
                    "feature": "mine", "state": "dispatched", "success": True,
                    "nextWakeAtMillis": self.clock.value + 60_000,
                }
            ),
            self.facade,
        )
        self.clock.value = until + 1
        self.facade._run_configured_resident_tick(  # noqa: SLF001
            FakeExecution(), "202", {"allowedFeatures": ["mine"]}
        )
        self.assertIn("打矿已恢复运行", self.logs.user_messages())

    # -- a ledger an earlier build left behind -----------------------------

    def test_a_legacy_isolated_ledger_is_settled_without_a_human(self) -> None:
        # The exact shape found on the phone: heal sent, assign refused,
        # expedition never started, held "for a human".
        legacy = {
            "battleId": 0,
            "mineId": 4242,
            "generalIds": [GENERAL_ID, 1826335],
            "x": 88,
            "y": 24,
            "targetName": "1级镔铁矿",
            "createdAtMillis": self.clock.value - 3 * 3_600_000,
            "dispatchAtMillis": 0,
            "preDispatchMutationState": "failed",
            "preDispatchMutationAtMillis": self.clock.value - 3 * 3_600_000,
            "preDispatchRequestMetadata": {"feature": "troop-heal"},
            "preDispatchError": "智步1缺少12近卫兵；目标699，可用687，已保持原配兵不变",
            "dispatchSendState": "not-started",
            "recallRequestedAtMillis": 0,
            "requiresAttention": True,
            "blockedAtMillis": self.clock.value - 3 * 3_600_000,
        }
        self.facade._save_automation_pending_record(  # noqa: SLF001
            "202", "minePendingGarrisonJson", legacy
        )
        self.facade._refresh_military_snapshot_game = types.MethodType(  # noqa: SLF001
            lambda _self, *_args, **_kwargs: {"actions": []}, self.facade
        )
        self.facade._persist_automation_general_snapshot = (  # noqa: SLF001
            lambda *_args, **_kwargs: None
        )

        result = self.facade._run_mine_garrison_game_workflow(  # noqa: SLF001
            FakeExecution(), "202", legacy, {}
        )

        self.assertEqual(result["state"], "retry")
        self.assertFalse(result["requiresAttention"])
        self.assertTrue(result["_pendingReleased"])
        self.assertEqual(result["nextWakeAtMillis"], self.clock.value)
        public = self._public()
        self.assertEqual(public["minePendingGarrisonJson"], "{}")
        archived = json.loads(public["mineLastPreDispatchFailureJson"])
        self.assertEqual(
            archived["recoveryResolution"],
            "pre-dispatch-settled-nothing-formal-sent",
        )
        self.assertFalse(archived["requiresAttention"])
        settled = [
            line for line in self.logs.user_messages()
            if line.startswith("打矿此前的隔离已解除")
        ]
        self.assertEqual(len(settled), 1, self.logs.user_messages())
        self.assertIn("智步1缺少12近卫兵", settled[0])
        self.assertIn("正式出征从未发送", settled[0])

    def test_an_unsettled_preflight_send_is_still_held(self) -> None:
        # Fail-closed stays fail-closed: a heal whose receipt never came is an
        # unknown outcome, and this change must not loosen it.
        pending = {
            "battleId": 0,
            "mineId": 4242,
            "generalIds": [GENERAL_ID],
            "preDispatchMutationState": "uncertain",
            "preDispatchRequestMetadata": {"feature": "troop-heal"},
            "dispatchSendState": "not-started",
            "requiresAttention": True,
        }
        self.facade._save_automation_pending_record(  # noqa: SLF001
            "202", "minePendingGarrisonJson", pending
        )
        self.facade._refresh_military_snapshot_game = types.MethodType(  # noqa: SLF001
            lambda _self, *_args, **_kwargs: {"actions": []}, self.facade
        )
        self.facade._persist_automation_general_snapshot = (  # noqa: SLF001
            lambda *_args, **_kwargs: None
        )
        result = self.facade._run_mine_garrison_game_workflow(  # noqa: SLF001
            FakeExecution(), "202", pending, {}
        )
        self.assertEqual(result["state"], "blocked")
        self.assertTrue(result["requiresAttention"])
        self.assertNotEqual(self._public()["minePendingGarrisonJson"], "{}")


if __name__ == "__main__":
    unittest.main()
