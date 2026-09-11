"""缺活血丹 is a timed pause of one formation, never a hold on the account lane.

Observed on a real phone: 将领维护 found 智步6 at 体力 22-29, below the top-up
threshold of 30, with no 活血丹 in the treasury.  The general could still march
(the dungeon using it completed 40 runs that day), yet the round aborted, its
pending record survived, and the pending lane re-entered the same check every
1.9 seconds for 561 seconds - starving 副本 and 刷黄.

Two rules replace that:

* short of the item but above the dispatch gate -> not a failure at all;
* short of the item *and* unable to march -> that general's formations pause
  for a fixed window while stamina regenerates; everything else continues.
"""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core import CoreFacade  # noqa: E402
from dwpm_core.features.maintenance import EXPEDITION_MIN_ENERGY  # noqa: E402
from dwpm_core.operations import OperationKnownFailureError  # noqa: E402
from dwpm_core.ports import PlatformPorts  # noqa: E402


PAUSE_MILLIS = 30 * 60 * 1000


class FixedClock:
    def __init__(self, value: int = 10_000_000) -> None:
        self.value = int(value)

    def now_millis(self) -> int:
        return self.value


class FakeExecution:
    operation_id = "op_energy_pause_fixture"

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


def _general(general_id: int, name: str, tili: int) -> dict:
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
        "tili": tili,
        "tiliLimit": 300,
        "loyalty": 100,
        "loyaltyLimit": 100,
        "soldierCount": 100,
        "currentSoldierCount": 100,
    }


class EnergyShortagePauseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FixedClock()
        self.directory = tempfile.TemporaryDirectory()
        self.facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(
                Path(self.directory.name) / "operations.json"
            ),
            ports=PlatformPorts(clock=self.clock),
        )
        self.facade.account_record_upsert({
            "accountRef": "202",
            "id": 202,
            "username": "energy-pause-fixture",
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
                    "activeResidentTaskKeys": "brushYellow,general",
                    "generalsJson": "[]",
                    "militarySnapshotJson": '{"actions":[]}',
                },
            },
        })
        self.inventory_reads = 0

        def empty_inventory(_self, _account_ref, _context, *, phase):
            self.inventory_reads += 1
            return {"items": [], "phase": phase}

        self.facade._fresh_inventory_state = types.MethodType(  # noqa: SLF001
            empty_inventory, self.facade
        )

    def tearDown(self) -> None:
        self.facade.close()
        self.directory.cleanup()

    def _public(self) -> dict:
        stored = json.loads(self.facade.account_record_json("202"))["account"]
        return stored["session"]["publicState"]

    def _cooldowns(self) -> dict:
        return json.loads(self._public().get("generalEnergyCooldownJson") or "{}")

    def _energy_step(self, general: dict, execution=None) -> dict:
        return self.facade._run_general_energy_maintenance_step(  # noqa: SLF001
            execution or FakeExecution(),
            "202",
            general,
            {},
            enabled=True,
            threshold=30,
            action_name="将领维护",
        )

    # -- the single origin --------------------------------------------------

    def test_short_of_item_but_able_to_march_is_not_a_failure(self) -> None:
        execution = FakeExecution()
        result = self._energy_step(_general(3758051, "智步6", 25), execution)

        self.assertTrue(result["ready"])
        self.assertFalse(result["actionRequired"])
        self.assertEqual(result["reason"], "energy-item-unavailable")
        self.assertIn("宝库没有活血丹", result["message"])
        self.assertIn(f"出征下限{EXPEDITION_MIN_ENERGY}", result["message"])
        self.assertEqual(execution.sent, [])
        self.assertEqual(self._cooldowns(), {})

    def test_unable_to_march_pauses_the_formation_for_thirty_minutes(self) -> None:
        with self.assertRaises(OperationKnownFailureError) as caught:
            self._energy_step(_general(3758051, "智步6", 15))
        error = caught.exception

        self.assertEqual(error.code, "EXPEDITION_ENERGY_ITEM_UNAVAILABLE")
        self.assertTrue(error.details["formationPaused"])
        self.assertEqual(
            error.details["retryAtMillis"], self.clock.value + PAUSE_MILLIS
        )
        self.assertIn("所在编队已暂停至", str(error))
        cooldowns = self._cooldowns()
        self.assertEqual(list(cooldowns), ["3758051"])
        self.assertEqual(
            cooldowns["3758051"]["untilMillis"], self.clock.value + PAUSE_MILLIS
        )
        self.assertEqual(cooldowns["3758051"]["source"], "将领维护")

    def test_the_pause_window_comes_from_the_behavior_contract(self) -> None:
        contract = json.loads(
            (ROOT / "shared_core" / "assistant_behavior_contract.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            contract["scheduler"]["energyShortageFormationPauseMillis"],
            PAUSE_MILLIS,
        )

    # -- expedition preflight ----------------------------------------------

    def test_preflight_skips_a_paused_formation_before_any_network_read(self) -> None:
        with self.assertRaises(OperationKnownFailureError):
            self._energy_step(_general(3758051, "智步6", 15))

        def must_not_read(_self, *_args, **_kwargs):
            raise AssertionError("a paused formation must not read game state")

        self.facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
            must_not_read, self.facade
        )
        with self.assertRaises(OperationKnownFailureError) as caught:
            self.facade._run_expedition_preflight(  # noqa: SLF001
                FakeExecution(),
                "202",
                {"generalIds": [3752041, 3758051]},
                {},
                action_name="副本",
                restore_saved_formation=False,
            )
        error = caught.exception
        self.assertEqual(error.code, "EXPEDITION_ENERGY_ITEM_UNAVAILABLE")
        self.assertEqual(error.details["generalIds"], [3758051])
        self.assertEqual(
            error.details["retryAtMillis"], self.clock.value + PAUSE_MILLIS
        )
        self.assertTrue(str(error).startswith("副本将领智步6"))

    def test_an_expired_pause_no_longer_blocks_the_formation(self) -> None:
        with self.assertRaises(OperationKnownFailureError):
            self._energy_step(_general(3758051, "智步6", 15))
        self.clock.value += PAUSE_MILLIS + 1

        reads = 0

        def formation_state(_self, *_args, **_kwargs):
            nonlocal reads
            reads += 1
            return "", [_general(3758051, "智步6", 80)], []

        self.facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
            formation_state, self.facade
        )
        selected, _preflight = self.facade._run_expedition_preflight(  # noqa: SLF001
            FakeExecution(),
            "202",
            {
                "generalIds": [3758051],
                "hostSettings": {"config": {"healWounded": False}},
            },
            {},
            action_name="副本",
            restore_saved_formation=False,
        )
        self.assertEqual([row["id"] for row in selected], [3758051])
        self.assertGreaterEqual(reads, 1)

    # -- 将领维护 round -----------------------------------------------------

    def _general_configs(self) -> dict:
        return {
            "general": {
                "enabled": True,
                "autoHeal": False,
                "autoEnergy": True,
                "minEnergy": 30,
                "keepFullLoyalty": False,
            },
        }

    def _install_two_generals(self, weak_tili: int) -> None:
        rows = [_general(3752041, "智步4", 300), _general(3758051, "智步6", weak_tili)]
        self.facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
            lambda _self, *_args, **_kwargs: ("", [dict(r) for r in rows], []),
            self.facade,
        )
        self.facade._persist_automation_general_snapshot = types.MethodType(  # noqa: SLF001
            lambda _self, *_args, **_kwargs: None, self.facade
        )

    def test_maintenance_round_completes_while_one_general_is_paused(self) -> None:
        self._install_two_generals(weak_tili=15)
        result = self.facade._run_configured_general_tick(  # noqa: SLF001
            FakeExecution(), "202", self._general_configs(), {}, {}
        )

        self.assertEqual(result["state"], "completed")
        self.assertTrue(result["success"])
        self.assertIsNotNone(result["nextWakeAtMillis"])
        self.assertEqual(
            [row["generalId"] for row in result["energyPaused"]], [3758051]
        )
        self.assertIn("智步6体力不足以出征且宝库没有活血丹", result["message"])
        self.assertIn("其余任务继续", result["message"])
        public = self._public()
        # The round is over: no pending record survives to claim the lane.
        self.assertEqual(public["generalMaintenancePendingJson"], "{}")
        self.assertIn("3758051", self._cooldowns())
        steps = {
            row["generalId"]: row["result"] for row in result["maintenance"]
        }
        self.assertEqual(steps[3752041]["reason"], "energy-sufficient")
        self.assertTrue(steps[3758051]["formationPaused"])

    def test_the_next_round_skips_the_paused_general_without_reading_inventory(self) -> None:
        self._install_two_generals(weak_tili=15)
        self.facade._run_configured_general_tick(  # noqa: SLF001
            FakeExecution(), "202", self._general_configs(), {}, {}
        )
        reads_after_first_round = self.inventory_reads
        self.assertEqual(reads_after_first_round, 1)

        self.clock.value += 10 * 60 * 1000
        second = self.facade._run_configured_general_tick(  # noqa: SLF001
            FakeExecution(), "202", self._general_configs(), {}, {}
        )
        self.assertEqual(second["state"], "completed")
        self.assertEqual(second["energyPaused"], [])
        steps = {
            row["generalId"]: row["result"] for row in second["maintenance"]
        }
        self.assertEqual(steps[3758051]["skipped"], "energy-cooldown")
        self.assertEqual(self.inventory_reads, reads_after_first_round)

    def test_a_manual_top_up_lifts_the_pause_at_the_next_round(self) -> None:
        # Round 1: 智步6 cannot march -> paused until now+30min; the dungeon
        # feature goes to sleep until exactly that deadline.
        self._install_two_generals(weak_tili=15)
        first = self.facade._run_configured_general_tick(  # noqa: SLF001
            FakeExecution(), "202", self._general_configs(), {}, {}
        )
        until = int(first["energyPaused"][0]["retryAtMillis"])
        self.assertIn("3758051", self._cooldowns())

        # The user hands the general a 活血丹; the next round reads 80.
        self.clock.value += 3 * 60 * 1000
        self._install_two_generals(weak_tili=80)
        state = {"dungeon": {"nextWakeAtMillis": until, "lastState": "waiting-resources"}}
        second = self.facade._run_configured_general_tick(  # noqa: SLF001
            FakeExecution(), "202", self._general_configs(), state, {}
        )

        self.assertEqual(
            [(row["generalId"], row["energy"]) for row in second["energyLifted"]],
            [(3758051, 80)],
        )
        self.assertIn("已提前解除所在编队暂停", second["message"])
        self.assertEqual(self._cooldowns(), {})
        saved = json.loads(self._public()["residentAutomationStateJson"])
        # Woken now rather than at the original 30-minute deadline.
        self.assertEqual(saved["dungeon"]["nextWakeAtMillis"], self.clock.value)
        # And the formation is dispatchable again without waiting.
        self.assertIsNone(
            self.facade._general_energy_cooldown_block(  # noqa: SLF001
                "202", [3758051], self.clock.value
            )
        )

    def test_a_still_exhausted_general_stays_paused(self) -> None:
        self._install_two_generals(weak_tili=15)
        self.facade._run_configured_general_tick(  # noqa: SLF001
            FakeExecution(), "202", self._general_configs(), {}, {}
        )
        self.clock.value += 3 * 60 * 1000
        second = self.facade._run_configured_general_tick(  # noqa: SLF001
            FakeExecution(), "202", self._general_configs(), {}, {}
        )
        self.assertEqual(second["energyLifted"], [])
        self.assertIn("3758051", self._cooldowns())

    def test_a_general_that_can_still_march_does_not_pause_anything(self) -> None:
        self._install_two_generals(weak_tili=25)
        result = self.facade._run_configured_general_tick(  # noqa: SLF001
            FakeExecution(), "202", self._general_configs(), {}, {}
        )
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["energyPaused"], [])
        self.assertEqual(self._cooldowns(), {})
        steps = {
            row["generalId"]: row["result"] for row in result["maintenance"]
        }
        self.assertEqual(steps[3758051]["reason"], "energy-item-unavailable")

    # -- 刷黄 rule selection ------------------------------------------------

    def _brush_configs(self) -> dict:
        def rule(index: int, general_id: int, level: int) -> dict:
            return {
                "enabled": True,
                "sourceRowIndex": index,
                "formationSourceRowIndex": index,
                "generalId": str(general_id),
                "generalIds": [str(general_id)],
                "levels": [level],
                "drops": ["宝物"],
                "compositionFilter": {},
                "formations": [{
                    "enabled": True,
                    "generalId": str(general_id),
                    "generalIds": [str(general_id)],
                    "soldierType": "近卫兵",
                    "soldierCount": 100,
                }],
            }

        return {
            "common": {
                "autoStart": True,
                "startHour": 0,
                "dailyLimit": 500,
                "brush": {
                    "startX": 10,
                    "startY": 10,
                    "scanLimit": 80,
                    "targetKind": "山贼",
                    "rules": [rule(0, 1826335, 8), rule(1, 3755035, 7)],
                },
            },
        }

    class _RuleProbe(Exception):
        def __init__(self, levels) -> None:
            super().__init__(str(levels))
            self.levels = list(levels)

    def _probe_rule_selection(self) -> None:
        facade = self.facade
        probe = self._RuleProbe

        def capture(_self, body, _context):
            raise probe(body.get("levels") or [])

        facade.brush_search_operation_payload = types.MethodType(  # noqa: SLF001
            capture, facade
        )

    def test_brush_skips_the_paused_rule_and_keeps_rotating(self) -> None:
        # Pause formation 1's general (rule index 0 carries level 8).
        with self.assertRaises(OperationKnownFailureError):
            self._energy_step(_general(1826335, "攻弓1", 15))
        self._probe_rule_selection()

        with self.assertRaises(self._RuleProbe) as caught:
            self.facade._run_configured_brush_tick(  # noqa: SLF001
                FakeExecution(), "202", self._brush_configs(),
                {"brush": {"cursor": 0}}, {},
            )
        self.assertEqual(caught.exception.levels, [7])

    def test_brush_sleeps_until_the_earliest_pause_when_every_rule_is_paused(self) -> None:
        with self.assertRaises(OperationKnownFailureError):
            self._energy_step(_general(1826335, "攻弓1", 15))
        self.clock.value += 5 * 60 * 1000
        with self.assertRaises(OperationKnownFailureError):
            self._energy_step(_general(3755035, "攻弓2", 15))
        self._probe_rule_selection()

        with self.assertRaises(OperationKnownFailureError) as caught:
            self.facade._run_configured_brush_tick(  # noqa: SLF001
                FakeExecution(), "202", self._brush_configs(),
                {"brush": {"cursor": 0}}, {},
            )
        error = caught.exception
        self.assertEqual(error.code, "EXPEDITION_ENERGY_ITEM_UNAVAILABLE")
        # The first general was paused five minutes earlier, so its window
        # ends first; that is when there is something new to look at.
        self.assertEqual(
            error.details["retryAtMillis"],
            self.clock.value - 5 * 60 * 1000 + PAUSE_MILLIS,
        )
        self.assertTrue(str(error).startswith("刷黄将领攻弓1"))

    # -- resident scheduler -------------------------------------------------

    def test_resident_retry_waits_for_the_pause_instead_of_polling(self) -> None:
        self.facade._update_account_public_state(  # noqa: SLF001
            "202",
            {
                "residentAutomationConfigJson": json.dumps(
                    self._brush_configs(), ensure_ascii=False
                ),
                "activeResidentTaskKeys": "brushYellow",
            },
        )
        until = self.clock.value + PAUSE_MILLIS

        def paused_brush(_self, *_args, **_kwargs):
            raise OperationKnownFailureError(
                "刷黄将领攻弓1体力不足以出征且宝库没有活血丹，所在编队已暂停",
                code="EXPEDITION_ENERGY_ITEM_UNAVAILABLE",
                details={"retryAtMillis": until, "formationPaused": True},
            )

        self.facade._run_configured_brush_tick = types.MethodType(  # noqa: SLF001
            paused_brush, self.facade
        )
        result = self.facade._run_configured_resident_tick(  # noqa: SLF001
            FakeExecution(), "202", {"allowedFeatures": ["brush"]}
        )

        self.assertEqual(result["feature"], "brush")
        self.assertEqual(result["state"], "retry")
        self.assertFalse(result["requiresAttention"])
        self.assertEqual(result["nextWakeAtMillis"], until)
        state = json.loads(self._public()["residentAutomationStateJson"])
        self.assertEqual(state["brush"]["nextWakeAtMillis"], until)

    # -- 副本 defer ---------------------------------------------------------

    def test_resource_shortage_retry_prefers_the_pause_deadline(self) -> None:
        pick = self.facade._resource_shortage_retry  # noqa: SLF001
        plain = OperationKnownFailureError("x", code="EXPEDITION_ENERGY_ITEM_UNAVAILABLE")
        retry_at, note = pick(self.clock.value, 300_000, plain)
        self.assertEqual(retry_at, self.clock.value + 300_000)
        self.assertEqual(note, "5分钟后重新检查")

        paused = OperationKnownFailureError(
            "x",
            code="EXPEDITION_ENERGY_ITEM_UNAVAILABLE",
            details={"retryAtMillis": self.clock.value + PAUSE_MILLIS},
        )
        retry_at, note = pick(self.clock.value, 300_000, paused)
        self.assertEqual(retry_at, self.clock.value + PAUSE_MILLIS)
        self.assertTrue(note.startswith("将于"))
        self.assertTrue(note.endswith("重新检查"))


class RecordingMapSnapshotPort:
    """Serves one cached bandit and records every invalidation."""

    def __init__(self, targets: list[dict]) -> None:
        self.targets = list(targets)
        self.invalidated: list[dict] = []

    def load(self, account_ref: str, kind: str, fingerprint: str):
        return {
            "scannedAtMillis": 10_000_000,
            "targets": [dict(row) for row in self.targets],
        }

    def save(self, *_args, **_kwargs) -> None:
        return None

    def invalidate(
        self,
        account_ref: str,
        kind: str,
        target_id: int,
        reason: str,
        invalidated_at_millis: int,
    ) -> None:
        self.invalidated.append({
            "accountRef": account_ref,
            "kind": kind,
            "targetId": target_id,
            "reason": reason,
            "invalidatedAtMillis": invalidated_at_millis,
        })


class StaleBrushTargetTests(unittest.TestCase):
    """A bandit the game says is gone must leave the local snapshot.

    Candidates are taken nearest-first from the cache.  Without writing the
    rejection back, the same dead target was re-selected every ten seconds on
    both live accounts once the shared pool became unavailable.
    """

    def setUp(self) -> None:
        self.clock = FixedClock()
        self.snapshots = RecordingMapSnapshotPort([{
            "targetId": 9901,
            "x": 12,
            "y": 11,
            "level": 8,
            "filterFields": {"kind": "山贼", "compositionCode": "5500"},
        }])
        self.directory = tempfile.TemporaryDirectory()
        self.facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(
                Path(self.directory.name) / "operations.json"
            ),
            ports=PlatformPorts(
                clock=self.clock, map_snapshots=self.snapshots
            ),
        )
        self.facade.account_record_upsert({
            "accountRef": "202",
            "id": 202,
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
                    "activeResidentTaskKeys": "brushYellow",
                    "generalsJson": "[]",
                },
            },
        })
        self.facade._cloud_presence_mode = types.MethodType(  # noqa: SLF001
            lambda _self, _account_ref, **_kw: {"mode": "LOCAL_ONLY"},
            self.facade,
        )
        self.facade._run_brush_search_game_workflow = types.MethodType(  # noqa: SLF001
            lambda _self, *_a, **_k: (_ for _ in ()).throw(
                AssertionError("cached target must be used, not a fresh scan")
            ),
            self.facade,
        )
        self.facade.brush_execute_operation_payload = types.MethodType(  # noqa: SLF001
            lambda _self, body, _context: dict(body), self.facade
        )

    def tearDown(self) -> None:
        self.facade.close()
        self.directory.cleanup()

    def _configs(self) -> dict:
        return {
            "formations": [],
            "common": {
                "autoStart": True,
                "startHour": 0,
                "dailyLimit": 500,
                "brush": {
                    "startX": 10,
                    "startY": 10,
                    "scanLimit": 80,
                    "targetKind": "山贼",
                    "rules": [{
                        "enabled": True,
                        "sourceRowIndex": 0,
                        "generalIds": ["1826335"],
                        "levels": [8],
                        "drops": [],
                        "compositionFilter": {},
                        "formations": [],
                    }],
                },
            },
        }

    def _run_with_rejection(self, message: str) -> OperationKnownFailureError:
        def rejected(_self, *_args, **_kwargs):
            raise OperationKnownFailureError(message, code="BRUSH_DISPATCH_REJECTED")

        self.facade._run_brush_execute_game_workflow = types.MethodType(  # noqa: SLF001
            rejected, self.facade
        )
        with self.assertRaises(OperationKnownFailureError) as caught:
            self.facade._run_configured_brush_tick(  # noqa: SLF001
                FakeExecution(), "202", self._configs(), {}, {}
            )
        return caught.exception

    def test_a_gone_target_is_invalidated_in_the_local_snapshot(self) -> None:
        error = self._run_with_rejection("目标不存在，不能到达。")
        self.assertEqual(error.code, "BRUSH_DISPATCH_REJECTED")
        self.assertEqual(
            [(row["kind"], row["targetId"]) for row in self.snapshots.invalidated],
            [("bandit", 9901)],
        )
        self.assertEqual(
            self.snapshots.invalidated[0]["invalidatedAtMillis"], self.clock.value
        )
        self.assertIn("目标不存在", self.snapshots.invalidated[0]["reason"])

    def test_a_formation_rejection_keeps_the_target(self) -> None:
        self._run_with_rejection("每个将领至少需配1000兵力")
        self.assertEqual(self.snapshots.invalidated, [])


if __name__ == "__main__":
    unittest.main()
