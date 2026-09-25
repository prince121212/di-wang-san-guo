"""Brush requests are serialized; independent formations' battles are not."""

from __future__ import annotations

import json
import struct
import sys
import tempfile
import types
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core/python"))

from dwpm_core import CoreFacade
from dwpm_core.automation import china_day_key
from dwpm_core.operations import OperationKnownFailureError, OperationUncertainError
from dwpm_core.ports import PlatformPorts
from dwpm_core.local_views import resident_success_records_from_public_state
from dwpm_core.features.brush_lanes import brush_record_key
from test_shared_resident_automation import FakeExecution, FixedClock


ACTIVE = "brushPendingRecoveryJson"
WAITING = "brushWaitingRecoveriesJson"


class BrushFormationLaneTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "operations.json")
        self.clock = FixedClock()
        self.facade = self.new_facade()
        self.generals = [
            {
                "id": i, "idHex": f"{i:016x}", "name": f"将领{i}",
                "status": 0, "statusText": "闲", "tili": 200,
                "soldierCount": 100, "soldierTypeCode": 3, "fiefId": 303,
            }
            for i in (7, 8, 9, 10)
        ]
        self.facade.account_record_upsert({
            "accountRef": "303", "id": 303, "enabled": True,
            "loginState": "ONLINE",
            "session": {
                "accountId": 303, "sourceMode": 1,
                "publicState": {
                    "roleId": "303", "lastValidatedAt": str(self.clock.value),
                    "savedTasksStarted": "true",
                    "activeResidentTaskKeys": "brushYellow",
                    "generalsJson": json.dumps(self.generals),
                },
            },
        })
        self.habits = {
            "formations": [
                {"enabled": True, "generalIds": [str(i)],
                 "soldierType": "轻骑兵", "soldierCount": 100}
                for i in (7, 8, 9, 10)
            ],
            "config": {
                "autoStart": True, "startHour": 0, "dailyLimit": 500,
                "healWounded": False, "autoEnergy": False, "dailyTasks": {},
                "brush": {
                    "startX": 10, "startY": 10, "scanLimit": 80,
                    "targetKind": "山贼",
                    "rows": [
                        {"enabled": True, "generalIds": [str(i)], "level": 7,
                         "drop": "宝物", "compositionCode": "5505"}
                        for i in (7, 8, 9, 10)
                    ],
                },
            },
        }
        self.facade.configure_resident_automation_from_habits("303", self.habits)
        self.facade.set_resident_automation_activation("303", True, ["brushYellow"])
        self.put(residentAutomationStateJson=json.dumps({
            "brush": {"cursor": 1, "dayKey": china_day_key(self.clock.value),
                      "usedCount": 1, "nextWakeAtMillis": self.clock.value},
        }))
        self.sent = []
        self.searched = 0
        self.install_game_boundaries()

    def new_facade(self):
        return CoreFacade(
            shared_root=ROOT / "shared_core", operation_store_path=self.path,
            ports=PlatformPorts(clock=self.clock),
        )

    def tearDown(self):
        self.facade.close()
        self.directory.cleanup()

    def put(self, **updates):
        self.facade._update_account_public_state("303", updates)

    def public(self):
        return self.facade._account_public_state("303")

    def pending(self):
        public = self.public()
        active = json.loads(public.get(ACTIVE) or "{}")
        return ([active] if active else []) + list(
            json.loads(public.get(WAITING) or "{}").values()
        )

    def old_pending(self, general_id=7, **updates):
        return {
            "generalIds": [general_id], "formationId": general_id,
            "targetId": 100 + general_id,
            "target": {"id": 100 + general_id, "kind": "山贼", "level": 7,
                       "x": 12, "y": 12},
            "createdAtMillis": self.clock.value - 30_000,
            "sendState": "accepted", "battleId": 1000 + general_id,
            "sawBusy": True, "healWounded": False,
            "nextPollAtMillis": self.clock.value + 30_000,
            "formations": [{"generalId": str(general_id), "soldierType": "轻骑兵",
                            "soldierCount": 100}],
            **updates,
        }

    def tick(self, **context):
        return self.facade._run_automation_recovery_tick(
            FakeExecution(), "303", {"allowedFeatures": ["brush"], **context}
        )

    def install_game_boundaries(self):
        """Keep scheduling, dispatch journal and return workflow real."""
        owner = self

        def search(_self, _execution, _body, _context):
            owner.searched += 1
            return {"targets": [{
                "id": 10000 + owner.searched, "idHex": f"{10000 + owner.searched:016x}",
                "kind": "山贼", "level": 7, "x": 10, "y": 10,
                "dropCategories": ["宝物"], "compositionCode": "1000",
            }]}

        def preflight(_self, _execution, _account, body, _context, **_kwargs):
            ids = {int(i) for i in body["generalIds"]}
            return [dict(g) for g in owner.generals if g["id"] in ids], {}

        def command(_self, _execution, _account, opcode, payload, *_args, **_kwargs):
            if opcode == 0x1522:
                owner.sent.append(bytes(payload))
                battle = 20000 + len(owner.sent)
                # Same 0x8522 layout as the protocol parity fixture.
                receipt = b"\x00\x00\x00" + struct.pack(">q", battle)
                return {"packets": [{"opcode": 0x8522, "payload": receipt}]}
            return {"packets": [{"opcode": 0x8520, "payload": b""}]}

        self.facade._run_brush_search_game_workflow = types.MethodType(search, self.facade)
        self.facade._run_expedition_preflight = types.MethodType(preflight, self.facade)
        self.facade._daily_command_fact = types.MethodType(command, self.facade)
        self.facade._fresh_formation_state = types.MethodType(
            lambda _self, *_a, **_kw: ("", deepcopy(owner.generals), []), self.facade
        )
        self.facade._run_troop_assign_game_workflow = types.MethodType(
            lambda *_a, **_kw: {"success": True, "message": "already exact"},
            self.facade,
        )

    def test_one_marching_formation_does_not_block_three_idle_formations(self):
        self.put(**{ACTIVE: json.dumps(self.old_pending())})
        result = self.tick()
        self.assertEqual(result["state"], "dispatched", result)
        self.assertEqual(result["formationNumber"], 2)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual({tuple(p["generalIds"]) for p in self.pending()}, {(7,), (8,)})
        self.assertNotIn("brush", result.get("isolatedPendingFeatures", []))

    def test_four_formations_can_be_in_flight_before_any_returns(self):
        self.put(**{ACTIVE: json.dumps(self.old_pending(nextPollAtMillis=self.clock.value + 120_000))})
        for _ in range(3):
            result = self.tick()
            self.assertEqual(result["state"], "dispatched", result)
            self.clock.value += 2_000
        self.assertEqual(len(self.pending()), 4)
        self.assertEqual(len(self.sent), 3)
        self.assertEqual(len({p["battleId"] for p in self.pending()}), 4)
        self.assertEqual(
            json.loads(self.public()["residentAutomationStateJson"])["brush"]["usedCount"], 4
        )
        # Even a stale "idle" snapshot cannot reuse generals with live ledgers.
        searched = self.searched
        result = self.tick()
        self.assertEqual(self.searched, searched)
        self.assertEqual(len(self.sent), 3)
        self.assertGreater(result["nextWakeAtMillis"], self.clock.value)
        self.assertEqual(
            result["nextWakeAtMillis"],
            min(p["nextPollAtMillis"] for p in self.pending()),
        )

    def test_return_clears_only_its_formation_and_does_not_rewind_cursor(self):
        self.put(**{ACTIVE: json.dumps(self.old_pending())})
        self.tick()
        self.clock.value += 31_000
        # Formation 7 is home; formation 8 remains away.
        self.generals[1].update(status=6, statusText="战")
        result = self.tick()
        self.assertEqual(result["state"], "completed", result)
        self.assertEqual([p["generalIds"] for p in self.pending()], [[8]])
        self.assertEqual(
            json.loads(self.public()["residentAutomationStateJson"])["brush"]["cursor"], 2
        )
        self.assertEqual(json.loads(self.public()["brushLastRecoveryJson"])["battleId"], 1007)

    def test_restart_keeps_all_battles_and_never_resends_an_occupied_formation(self):
        self.put(**{ACTIVE: json.dumps(self.old_pending())})
        self.tick()
        before = deepcopy(self.pending())
        self.facade.close()
        self.facade = self.new_facade()
        self.install_game_boundaries()
        self.assertEqual(self.pending(), before)
        self.clock.value += 2_000
        result = self.tick()
        self.assertEqual(result["formationNumber"], 3, result)
        self.assertEqual(len(self.pending()), 3)

    def test_uncertain_formation_reserves_its_generals_but_not_other_formations(self):
        pending = self.old_pending(
            sendState="uncertain", requiresAttention=True,
            preDispatchMutationState="accepted",
            sendingAtMillis=self.clock.value - 10_000,
        )
        self.put(**{ACTIVE: json.dumps(pending)})
        result = self.tick()
        self.assertEqual(result["state"], "dispatched", result)
        uncertain = next(p for p in self.pending() if p["generalIds"] == [7])
        self.assertEqual(uncertain["sendState"], "uncertain")
        self.assertTrue(uncertain["requiresAttention"])
        self.assertEqual(len(self.sent), 1)

    def test_overlapping_rules_are_skipped_before_target_search(self):
        self.habits["config"]["brush"]["rows"][1]["generalIds"] = ["7", "8"]
        self.facade.configure_resident_automation_from_habits("303", self.habits)
        self.put(**{ACTIVE: json.dumps(self.old_pending())})
        result = self.tick()
        self.assertEqual(result["formationNumber"], 3, result)
        self.assertEqual(self.searched, 1)

    def test_direct_dispatch_cannot_overwrite_a_live_ledger_for_same_generals(self):
        pending = self.old_pending()
        self.put(**{ACTIVE: json.dumps(pending)})
        body = {
            "accountRef": "303", "generalIds": ["7"],
            "target": {"id": 999, "kind": "山贼", "x": 11, "y": 11},
        }
        with self.assertRaises(OperationKnownFailureError):
            self.facade._run_brush_execute_game_workflow(FakeExecution(), body, {})
        self.assertEqual(json.loads(self.public()[ACTIVE]), pending)
        self.assertEqual(len(self.sent), 0)

    def test_recovery_only_context_cannot_dispatch_idle_siblings(self):
        self.put(**{ACTIVE: json.dumps(self.old_pending())})
        result = self.tick(configuredExecutionAllowed=False)
        self.assertNotEqual(result.get("state"), "dispatched")
        self.assertEqual(len(self.sent), 0)

    def test_a_later_team_can_return_first_without_erasing_an_earlier_battle(self):
        older = self.old_pending(nextPollAtMillis=self.clock.value + 300_000)
        later = self.old_pending(8, nextPollAtMillis=self.clock.value)
        self.put(**{
            ACTIVE: json.dumps(older),
            WAITING: json.dumps({brush_record_key(later): later}),
        })
        result = self.tick()
        self.assertEqual(result["state"], "completed", result)
        self.assertEqual([p["battleId"] for p in self.pending()], [1007])
        self.assertEqual(json.loads(self.public()["brushLastRecoveryJson"])["battleId"], 1008)
        self.assertEqual(len(self.sent), 0)

    def test_an_uncertain_new_send_cannot_overwrite_old_battles_or_pin_idle_siblings(self):
        self.put(**{ACTIVE: json.dumps(self.old_pending())})
        original = self.facade._daily_command_fact

        def missing(_self, execution, account, opcode, payload, *a, **kw):
            if opcode == 0x1522:
                self.sent.append(bytes(payload))
                return {"packets": []}
            return original(execution, account, opcode, payload, *a, **kw)

        self.facade._daily_command_fact = types.MethodType(missing, self.facade)
        with self.assertRaises(OperationUncertainError):
            self.tick()
        self.assertEqual(len(self.pending()), 2)
        self.assertEqual(
            next(p for p in self.pending() if p["generalIds"] == [8])["sendState"], "uncertain"
        )
        self.facade._daily_command_fact = original
        # One safe read-only observation of the uncertain lane may run first.
        self.clock.value += 2_000
        self.tick()
        self.clock.value += 2_000
        self.tick()
        self.assertEqual({tuple(p["generalIds"]) for p in self.pending()}, {(7,), (8,), (9,)})
        self.assertEqual(len(self.sent), 2)  # Never resent formation 8.
        self.assertEqual(
            json.loads(self.public()["residentAutomationStateJson"])["brush"]["usedCount"], 2
        )

    def test_repeated_blocked_recovery_yields_without_losing_its_step_journal(self):
        pending = self.old_pending(nextPollAtMillis=self.clock.value)
        self.put(**{ACTIVE: json.dumps(pending)})
        self.habits["config"]["brush"]["rows"] = self.habits["config"]["brush"]["rows"][:1]
        self.facade.configure_resident_automation_from_habits("303", self.habits)
        calls = []

        def stopped(_self, *_a, **_kw):
            calls.append(1)
            return {"feature": "brushYellow", "state": "blocked",
                    "requiresAttention": True, "nextWakeAtMillis": None,
                    "message": "uncertain formation step"}

        self.facade._run_brush_recovery_game_workflow = types.MethodType(stopped, self.facade)
        for _ in range(8):
            self.tick()
            self.clock.value += 2_000
        self.assertLessEqual(len(calls), 2)
        self.assertEqual(len(self.pending()), 1)
        self.assertTrue(self.pending()[0]["requiresAttention"])

    def test_same_target_is_not_dispatched_again_by_an_independent_team(self):
        pending = self.old_pending()
        self.put(**{ACTIVE: json.dumps(pending)})
        with self.assertRaises(OperationKnownFailureError) as caught:
            self.facade._run_brush_execute_game_workflow(
                FakeExecution(), {
                    "accountRef": "303", "generalIds": ["8"],
                    "target": pending["target"],
                }, {},
            )
        self.assertEqual(caught.exception.code, "BRUSH_TARGET_ALREADY_PENDING")
        self.assertEqual(json.loads(self.public()[ACTIVE]), pending)
        self.assertEqual(len(self.sent), 0)

    def test_stale_search_results_exclude_targets_owned_by_other_brush_teams(self):
        pending = self.old_pending()
        self.put(**{ACTIVE: json.dumps(pending)})
        self.facade._run_brush_search_game_workflow = types.MethodType(
            lambda *_a, **_kw: {"targets": [pending["target"]]}, self.facade
        )
        result = self.tick()
        self.assertEqual(result["state"], "no-targets", result)
        self.assertEqual(len(self.sent), 0)

    def test_other_expedition_features_cannot_use_a_brush_reserved_general(self):
        self.put(**{ACTIVE: json.dumps(self.old_pending())})
        with self.assertRaises(OperationKnownFailureError) as caught:
            CoreFacade._run_expedition_preflight(
                self.facade, FakeExecution(), "303", {"generalIds": ["7"]}, {},
                action_name="打矿",
            )
        self.assertEqual(caught.exception.code, "EXPEDITION_GENERALS_RESERVED")
        self.assertEqual(len(self.sent), 0)

    def test_waiting_history_recovers_every_accepted_battle_but_not_unknown_sends(self):
        old = self.old_pending(7, formationNumber=1)
        newer = self.old_pending(8, formationNumber=2)
        unknown = self.old_pending(9, formationNumber=3, sendState="uncertain")
        self.put(**{
            ACTIVE: json.dumps(newer),
            WAITING: json.dumps({
                brush_record_key(old): old, brush_record_key(unknown): unknown,
            }),
            "successRecordsJson": "[]",
        })
        records = resident_success_records_from_public_state(self.public(), account_ref="303")
        brushes = [r for r in records if r["category"] == "刷黄"]
        self.assertEqual({r["detail"]["battleId"] for r in brushes}, {1007, 1008})
        self.assertEqual({r["detail"]["formationNumber"] for r in brushes}, {1, 2})

    def test_skip_heal_marker_is_not_consumed_by_another_formation(self):
        self.habits["config"]["healWounded"] = True
        self.facade.configure_resident_automation_from_habits("303", self.habits)
        state = json.loads(self.public()["residentAutomationStateJson"])
        state["brush"].update({
            "cursor": 1, "skipHealOnce": True,
            "skipHealForGenerals": {"7": "uncertain-pre-dispatch-heal"},
        })
        self.put(residentAutomationStateJson=json.dumps(state))
        self.tick()
        self.assertTrue(self.pending()[0]["healWounded"])
        state = json.loads(self.public()["residentAutomationStateJson"])
        self.assertEqual(state["brush"]["skipHealForGenerals"], {"7": "uncertain-pre-dispatch-heal"})
        self.clock.value += 2_000
        state["brush"].update({"cursor": 0, "nextWakeAtMillis": self.clock.value})
        self.put(residentAutomationStateJson=json.dumps(state))
        self.tick()
        formation7 = next(p for p in self.pending() if p["generalIds"] == [7])
        self.assertFalse(formation7["healWounded"])
        self.assertNotIn("skipHealOnce", json.loads(self.public()["residentAutomationStateJson"])["brush"])

    def test_corrupt_waiting_ledger_fails_closed_without_overwriting_it(self):
        self.put(**{WAITING: '{"broken":"not a record"}'})
        with self.assertRaises(OperationKnownFailureError) as caught:
            self.facade._run_brush_execute_game_workflow(
                FakeExecution(), {"accountRef": "303", "generalIds": ["8"],
                                  "target": {"id": 999}}, {},
            )
        self.assertEqual(caught.exception.code, "BRUSH_LANE_LEDGER_INVALID")
        self.assertEqual(self.public()[WAITING], '{"broken":"not a record"}')
        self.assertEqual(len(self.sent), 0)

    def test_hitting_daily_limit_stops_new_dispatches_not_existing_recovery(self):
        self.habits["config"]["dailyLimit"] = 2
        self.facade.configure_resident_automation_from_habits("303", self.habits)
        self.put(**{ACTIVE: json.dumps(self.old_pending())})
        self.tick()
        self.clock.value += 2_000
        result = self.tick()
        self.assertNotEqual(result["state"], "dispatched")
        self.assertEqual(len(self.sent), 1)
        self.clock.value += 31_000
        result = self.tick()
        self.assertEqual(result["state"], "completed", result)
        self.assertEqual(
            json.loads(self.public()["residentAutomationStateJson"])["brush"]["usedCount"], 2
        )

    def test_known_busy_rule_is_skipped_in_favour_of_an_idle_rule(self):
        self.generals[1].update(status=6, statusText="战")
        self.put(generalsJson=json.dumps(self.generals))
        result = self.tick()
        self.assertEqual(result["formationNumber"], 3, result)
        self.assertEqual(len(self.sent), 1)

    def test_all_cached_busy_rules_are_refreshed_instead_of_stuck_forever(self):
        cached = [{**g, "status": 6, "statusText": "战"} for g in self.generals]
        self.put(generalsJson=json.dumps(cached))
        # The fresh read supplied by the fixture says all four are now idle.
        result = self.tick()
        self.assertEqual(result["state"], "dispatched", result)

    def test_one_new_stamina_pause_does_not_park_the_feature_for_half_an_hour(self):
        original = self.facade._run_expedition_preflight

        def shortage(_self, execution, account, body, context, **kwargs):
            if body["generalIds"] == ["8"]:
                self.facade._record_general_energy_cooldown(
                    "303", self.generals[1], action_name="刷黄",
                    message="体力不足", now_millis=self.clock.value,
                )
                raise OperationKnownFailureError(
                    "体力不足", code="EXPEDITION_ENERGY_ITEM_UNAVAILABLE",
                    details={"formationPaused": True, "retryAtMillis": self.clock.value + 1_800_000},
                )
            return original(execution, account, body, context, **kwargs)

        self.facade._run_expedition_preflight = types.MethodType(shortage, self.facade)
        first = self.tick()
        self.assertEqual(first["state"], "formation-paused", first)
        self.clock.value += 2_000
        second = self.tick()
        self.assertEqual(second["formationNumber"], 3, second)
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(self.facade._general_energy_cooldown_block("303", [8], self.clock.value))

    def test_unscoped_pause_cannot_borrow_another_teams_existing_cooldown(self):
        self.facade._record_general_energy_cooldown(
            "303", self.generals[0], action_name="刷黄",
            message="体力不足", now_millis=self.clock.value,
        )
        until = self.clock.value + 1_800_000

        def paused(_self, *_args, **_kwargs):
            raise OperationKnownFailureError(
                "等待体力恢复", code="EXPEDITION_ENERGY_ITEM_UNAVAILABLE",
                details={"formationPaused": True, "retryAtMillis": until},
            )

        self.facade._run_configured_brush_tick = types.MethodType(paused, self.facade)
        result = self.tick()
        self.assertEqual(result["nextWakeAtMillis"], until)
        self.assertEqual(len(self.sent), 0)

    def test_scoped_pause_requires_cooldown_for_the_affected_team(self):
        self.facade._record_general_energy_cooldown(
            "303", self.generals[0], action_name="刷黄",
            message="体力不足", now_millis=self.clock.value,
        )
        self.assertFalse(self.facade._brush_has_independent_rule(
            "303", paused_by={"sourceRowIndex": 1},
        ))
        self.assertTrue(self.facade._brush_has_independent_rule(
            "303", paused_by={"sourceRowIndex": 0},
        ))
        self.assertTrue(self.facade._brush_has_independent_rule(
            "303", paused_by={"generalIds": [7]},
        ))

    def test_isolated_team_notice_remains_visible_while_an_idle_sibling_dispatches(self):
        pending = self.old_pending(
            sendState="uncertain", requiresAttention=True,
            dispatchError="回执丢失，不能重发",
        )
        self.put(**{ACTIVE: json.dumps(pending)})
        self.tick()
        notices = self.facade.resident_resource_notices("303")["notices"]
        self.assertTrue(any(
            n["key"].startswith("brush-lane:") and "回执丢失" in n["message"]
            for n in notices
        ))


if __name__ == "__main__":
    unittest.main()
