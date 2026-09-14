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
from dwpm_core.features.dungeon import (  # noqa: E402
    build_dungeon_battle_poll_payload,
    parse_dungeon_catalog,
    parse_dungeon_launch_response,
    parse_dungeon_reward_state,
    parse_dungeon_state,
)
from dwpm_core.features.expedition import (  # noqa: E402
    build_dungeon_expedition_payload,
    build_dungeon_prepare_payload,
)
from dwpm_core.operations import (  # noqa: E402
    OperationKnownFailureError,
    OperationUncertainError,
)
from dwpm_core.ports import PlatformPorts  # noqa: E402


FIXTURES = json.loads(
    (ROOT / "shared_core" / "protocol_parity_fixtures.json").read_text(
        encoding="utf-8"
    )
)["fixtures"]


class FixedClock:
    def __init__(self, value: int = 40_000_000) -> None:
        self.value = value

    def now_millis(self) -> int:
        return self.value


class FakeExecution:
    operation_id = "op_dungeon_fixture"

    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def mark_request_sent(self, metadata=None) -> None:
        self.sent.append(dict(metadata or {}))

    def publish_progress(self, _progress: int, _details=None) -> None:
        return None

    def raise_if_cancelled(self) -> None:
        return None

    def wait(self, _seconds: float) -> None:
        return None


def launch_marker_payload() -> bytes:
    encoded = "单人副本启动成功！".encode("utf-8")
    return len(encoded).to_bytes(2, "big") + encoded


class SharedDungeonAutomationTests(unittest.TestCase):
    def _facade(self):
        directory = tempfile.TemporaryDirectory()
        clock = FixedClock()
        facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(Path(directory.name) / "operations.json"),
            ports=PlatformPorts(clock=clock),
        )
        facade.account_record_upsert({
            "accountRef": "303",
            "id": 303,
            "enabled": True,
            "loginState": "ONLINE",
            "session": {
                "accountId": 303,
                "sourceMode": 1,
                "publicState": {
                    "roleId": "303",
                    "gameHttp": "https://fixture.invalid/game",
                    "lastValidatedAt": str(clock.value),
                    "generalsJson": "[]",
                },
            },
        })
        return facade, clock, directory

    @staticmethod
    def _general() -> dict[str, object]:
        return {
            "id": 7,
            "idHex": "0000000000000007",
            "name": "赵云",
            "status": 0,
            "statusText": "闲",
            "displayStatus": "闲",
            "energyReliable": True,
            "tili": 300,
            "loyalty": 100,
            "soldierTypeCode": 3,
            "soldierCount": 100,
            "currentSoldierCount": 100,
        }

    @staticmethod
    def _catalog() -> dict[str, object]:
        return parse_dungeon_catalog(
            bytes.fromhex(FIXTURES["dungeonCatalog8930"]["responseHex"])
        )

    def _body(self, facade: CoreFacade, *, mode: str = "loop") -> dict[str, object]:
        return facade.dungeon_action_operation_payload({
            "accountRef": "303",
            "confirm": "dungeon",
            "generalIds": ["7"],
            "mode": mode,
            "chapter": 0,
            "chapterName": "第一章",
            "stage": 3,
            "chest": 2,
            "fullTroops": False,
            "openChest": True,
        }, {})

    def _install_ready_fixtures(self, facade: CoreFacade) -> None:
        facade._run_dungeon_status_game_workflow = types.MethodType(  # noqa: SLF001
            lambda _self, *_args, **_kwargs: parse_dungeon_state(b"\x00"),
            facade,
        )
        facade._run_dungeon_catalog_game_workflow = types.MethodType(  # noqa: SLF001
            lambda _self, *_args, **_kwargs: self._catalog(),
            facade,
        )
        facade._run_expedition_preflight = types.MethodType(  # noqa: SLF001
            lambda _self, *_args, **_kwargs: (
                [self._general()],
                {"generalIds": [7]},
            ),
            facade,
        )

    def test_shared_shapes_preserve_captured_contract(self) -> None:
        fixture = FIXTURES["dungeonStateAndPoll"]
        state = parse_dungeon_state(bytes.fromhex(fixture["fightingResponseHex"]))
        reward = parse_dungeon_reward_state(
            bytes.fromhex(fixture["rewardResponseHex"])
        )
        launch = parse_dungeon_launch_response(launch_marker_payload())

        self.assertEqual(state["phase"], "fighting")
        self.assertEqual(state["battleId"], fixture["expected"]["battleId"])
        self.assertEqual(reward["battleId"], fixture["expected"]["battleId"])
        self.assertEqual(
            build_dungeon_battle_poll_payload(True, state["battleId"]).hex(),
            fixture["expected"]["firstPollPayloadHex"],
        )
        self.assertTrue(launch["success"])
        self.assertEqual(launch["successMarker"], "单人副本启动成功")

    def test_ready_tick_dispatches_exact_desktop_payload_and_persists(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            self._install_ready_fixtures(facade)
            commands: list[tuple[int, bytes]] = []

            def command(
                _self,
                _account,
                opcode,
                payload,
                _phase,
                _context,
                *,
                mutation_sent,
            ):
                self.assertTrue(mutation_sent)
                commands.append((int(opcode), bytes(payload)))
                return {
                    "httpCode": 200,
                    "packets": [{
                        "opcode": 0x8520 if opcode == 0x1520 else 0x8522,
                        "payload": b"" if opcode == 0x1520 else launch_marker_payload(),
                    }],
                }

            facade._execute_host_game_command = types.MethodType(  # noqa: SLF001
                command, facade
            )
            result = facade._run_dungeon_action_game_workflow(  # noqa: SLF001
                FakeExecution(), self._body(facade), {}
            )["result"]

            self.assertTrue(result["dispatchAccepted"])
            self.assertEqual(result["state"], "fighting")
            self.assertEqual(result["stage"]["stageCode"], 2)
            self.assertEqual(commands, [
                (
                    0x1520,
                    build_dungeon_prepare_payload(
                        ["0000000000000007"], 2
                    ),
                ),
                (
                    0x1522,
                    build_dungeon_expedition_payload(
                        ["0000000000000007"], 2
                    ),
                ),
            ])
            stored = json.loads(facade.account_record_json("303"))["account"]
            pending = json.loads(
                stored["session"]["publicState"]["dungeonPendingRunJson"]
            )
            self.assertEqual(pending["dispatchSendState"], "accepted")
            self.assertEqual(pending["stageCode"], 2)
            self.assertEqual(pending["generalIds"], [7])
        finally:
            facade.close()
            directory.cleanup()

    def test_missing_prepare_receipt_never_sends_formal_dispatch(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            self._install_ready_fixtures(facade)
            commands: list[int] = []

            def command(
                _self,
                _account,
                opcode,
                _payload,
                _phase,
                _context,
                *,
                mutation_sent,
            ):
                self.assertTrue(mutation_sent)
                commands.append(int(opcode))
                return {"httpCode": 200, "packets": []}

            facade._execute_host_game_command = types.MethodType(  # noqa: SLF001
                command, facade
            )
            with self.assertRaisesRegex(
                OperationKnownFailureError,
                "已禁止发送正式出征",
            ):
                facade._run_dungeon_action_game_workflow(  # noqa: SLF001
                    FakeExecution(), self._body(facade), {}
                )
            self.assertEqual(commands, [0x1520])
        finally:
            facade.close()
            directory.cleanup()

    def test_fighting_recovery_uses_first_then_followup_poll_shape(self) -> None:
        facade, clock, directory = self._facade()
        try:
            # The 0x1702 battle watch is off by default now: a real battle runs
            # ~105s, so polling it every couple of seconds spent about 24 round
            # trips per round learning nothing while holding the account lane.
            # Its two-phase payload shape stays pinned here so re-enabling the
            # evidence stream remains correct.
            schedule = facade._behavior_contract["dungeon"]["schedule"]  # noqa: SLF001
            schedule["battlePollEvidenceRequired"] = True
            # Zero both waits so the two ticks below stay back-to-back and keep
            # exercising the first/follow-up payload pair.
            schedule["battleQuietMillis"] = 0
            schedule["battlePollMillis"] = 0
            battle_id = FIXTURES["dungeonStateAndPoll"]["expected"]["battleId"]
            pending = {
                "generalIds": [7],
                "mode": "loop",
                "stageRef": {"chapter": 0, "stage": 3, "stageCode": 2},
                "chest": 2,
                "chestName": "右",
                "openChest": True,
                "createdAtMillis": clock.value - 20_000,
                "dispatchAcceptedAtMillis": clock.value - 20_000,
                "dispatchSendState": "accepted",
                "battleId": battle_id,
            }
            active = parse_dungeon_state(
                bytes.fromhex(
                    FIXTURES["dungeonStateAndPoll"]["fightingResponseHex"]
                )
            )
            facade._run_dungeon_status_game_workflow = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: dict(active),
                facade,
            )
            poll_payloads: list[bytes] = []

            def poll(
                _self,
                _account,
                opcode,
                payload,
                _phase,
                _context,
                *,
                mutation_sent,
            ):
                self.assertFalse(mutation_sent)
                self.assertEqual(opcode, 0x1702)
                poll_payloads.append(bytes(payload))
                return {"httpCode": 200, "packets": [{
                    "opcode": 0x8702,
                    "payload": b"battle-running",
                }]}

            facade._execute_host_game_command = types.MethodType(poll, facade)  # noqa: SLF001
            first = facade._run_dungeon_recovery_game_workflow(  # noqa: SLF001
                FakeExecution(), "303", pending, {}
            )
            second = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {}
            )

            self.assertEqual(first["state"], "fighting")
            self.assertEqual(second["state"], "fighting")
            self.assertEqual(second["feature"], "dungeon")
            self.assertEqual(
                [payload.hex() for payload in poll_payloads],
                [
                    FIXTURES["dungeonStateAndPoll"]["expected"][
                        "firstPollPayloadHex"
                    ],
                    FIXTURES["dungeonStateAndPoll"]["expected"][
                        "nextPollPayloadHex"
                    ],
                ],
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_clear_recovery_opens_chest_confirms_catalog_and_clears_ledger(
        self,
    ) -> None:
        facade, clock, directory = self._facade()
        try:
            pending = {
                "generalIds": [7],
                "mode": "clear",
                "stageRef": {
                    "chapter": 0,
                    "chapterName": "第一章",
                    "stage": 3,
                    "stageCode": 2,
                },
                "chest": 2,
                "chestName": "右",
                "openChest": True,
                "createdAtMillis": clock.value - 30_000,
                "dispatchAcceptedAtMillis": clock.value - 30_000,
                "dispatchSendState": "accepted",
                "battleId": 233292,
            }
            facade._run_dungeon_status_game_workflow = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: parse_dungeon_state(b"\x00"),
                facade,
            )
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: (
                    "",
                    [self._general()],
                    [],
                ),
                facade,
            )
            facade._run_dungeon_reward_game_workflow = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: parse_dungeon_reward_state(
                    bytes.fromhex(
                        FIXTURES["dungeonStateAndPoll"]["rewardResponseHex"]
                    )
                ),
                facade,
            )

            def open_chest(_self, execution, *_args, **_kwargs):
                execution.mark_request_sent({"feature": "dungeon-chest"})
                return {
                    "success": True,
                    "status": 0,
                    "chestIndex": 2,
                    "chestName": "右",
                    "textPreview": "获得奖励",
                }

            facade._run_dungeon_chest_game_workflow = types.MethodType(  # noqa: SLF001
                open_chest, facade
            )
            completed_catalog = self._catalog()
            completed_catalog["chapters"][0]["stages"][2]["resultCode"] = 1
            facade._run_dungeon_catalog_game_workflow = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: completed_catalog,
                facade,
            )

            execution = FakeExecution()
            result = facade._run_dungeon_recovery_game_workflow(  # noqa: SLF001
                execution, "303", pending, {}
            )
            self.assertEqual(result["state"], "chest-opened")
            self.assertTrue(result["stageCompleted"])
            self.assertTrue(result["chestResult"]["success"])
            self.assertEqual(len(execution.sent), 1)
            stored = json.loads(facade.account_record_json("303"))["account"]
            public = stored["session"]["publicState"]
            self.assertEqual(public["dungeonPendingRunJson"], "{}")
            self.assertEqual(
                json.loads(public["dungeonLastResultJson"])["state"],
                "chest-opened",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_pre_dispatch_mutation_is_never_auto_replayed(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            self._install_ready_fixtures(facade)

            def interrupted(_self, execution, *_args, **_kwargs):
                execution.mark_request_sent({"feature": "troop-heal"})
                raise OperationUncertainError("治疗回执不明")

            facade._run_expedition_preflight = types.MethodType(  # noqa: SLF001
                interrupted, facade
            )
            with self.assertRaises(OperationUncertainError):
                facade._run_dungeon_action_game_workflow(  # noqa: SLF001
                    FakeExecution(), self._body(facade), {}
                )
            stored = json.loads(facade.account_record_json("303"))["account"]
            pending = json.loads(
                stored["session"]["publicState"]["dungeonPendingRunJson"]
            )
            self.assertEqual(pending["preDispatchMutationState"], "uncertain")

            # Nothing formal was sent and the general is idle again, so the
            # world is back in a known state.  Every preflight step re-reads it
            # before acting, so the ledger is archived rather than replayed and
            # the next round simply re-derives what it needs.
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda _self, _account, _context, read_only=False: (
                    "", [self._general()], []
                ),
                facade,
            )
            recovery = facade._run_dungeon_recovery_game_workflow(  # noqa: SLF001
                FakeExecution(), "303", pending, {}
            )
            self.assertEqual(recovery["state"], "reconciled")
            self.assertFalse(recovery["requiresAttention"])
            self.assertIn("未重发", recovery["message"])
            stored = json.loads(facade.account_record_json("303"))["account"]
            public = stored["session"]["publicState"]
            self.assertEqual(public["dungeonPendingRunJson"], "{}")
            archived = json.loads(public["dungeonLastReconciliationJson"])
            self.assertEqual(
                archived["preDispatchMutationState"], "uncertain"
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_a_preflight_that_never_started_is_discarded_not_blocked(
        self,
    ) -> None:
        """Replays the exact record taken off a stalled account.

        ``preDispatchMutationState`` was ``pending`` - the *initial* state,
        meaning the mutation never began - with ``preDispatchMutationCount = 0``
        and every send state ``not-sent``.  Provably nothing had happened, yet
        the record carried ``requiresAttention`` and held the pending lane, so
        刷黄 went twenty minutes and 将领维护 sixteen without a turn.  "Nothing
        happened" must never require adjudication.
        """

        facade, clock, directory = self._facade()
        try:
            self._install_ready_fixtures(facade)
            facade._update_account_public_state(  # noqa: SLF001
                "303",
                {"dungeonPendingRunJson": json.dumps({
                    "generalIds": [7],
                    "chapter": 0,
                    "stage": 3,
                    "chest": 2,
                    "chestName": "右",
                    "openChest": True,
                    "preDispatchMutationState": "pending",
                    "preDispatchMutationCount": 0,
                    "prepareSendState": "not-sent",
                    "dispatchSendState": "not-sent",
                    "chestSendState": "not-sent",
                    "requiresAttention": True,
                    "createdAtMillis": clock.value - 20 * 60_000,
                })},
            )
            pending = json.loads(
                json.loads(facade.account_record_json("303"))["account"][
                    "session"
                ]["publicState"]["dungeonPendingRunJson"]
            )

            result = facade._run_dungeon_recovery_game_workflow(  # noqa: SLF001
                FakeExecution(), "303", pending, {}
            )

            self.assertFalse(result.get("requiresAttention"))
            self.assertIsNotNone(result.get("nextWakeAtMillis"))
            stored = json.loads(facade.account_record_json("303"))["account"]
            public = stored["session"]["publicState"]
            # The lane is released, so 刷黄 and 将领维护 can be scheduled again.
            self.assertEqual(public["dungeonPendingRunJson"], "{}")
            self.assertEqual(
                json.loads(public["dungeonLastDeferredJson"])[
                    "recoveryResolution"
                ],
                "pre-dispatch-failed-nothing-sent",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_an_uncertain_preflight_waits_while_the_general_is_still_out(
        self,
    ) -> None:
        """Idle is the evidence; without it nothing may be archived."""

        facade, _clock, directory = self._facade()
        try:
            self._install_ready_fixtures(facade)

            def interrupted(_self, execution, *_args, **_kwargs):
                execution.mark_request_sent({"feature": "troop-heal"})
                raise OperationUncertainError("治疗回执不明")

            facade._run_expedition_preflight = types.MethodType(  # noqa: SLF001
                interrupted, facade
            )
            with self.assertRaises(OperationUncertainError):
                facade._run_dungeon_action_game_workflow(  # noqa: SLF001
                    FakeExecution(), self._body(facade), {}
                )
            pending = json.loads(
                json.loads(facade.account_record_json("303"))["account"][
                    "session"
                ]["publicState"]["dungeonPendingRunJson"]
            )
            busy = {**self._general(), "statusText": "征", "displayStatus": "征"}
            facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
                lambda _self, _account, _context, read_only=False: (
                    "", [busy], []
                ),
                facade,
            )

            recovery = facade._run_dungeon_recovery_game_workflow(  # noqa: SLF001
                FakeExecution(), "303", pending, {}
            )

            self.assertEqual(recovery["state"], "waiting")
            self.assertFalse(recovery["requiresAttention"])
            stored = json.loads(facade.account_record_json("303"))["account"]
            self.assertNotEqual(
                stored["session"]["publicState"]["dungeonPendingRunJson"], "{}"
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_missing_energy_item_defers_five_minutes_without_stopping(self) -> None:
        facade, clock, directory = self._facade()
        try:
            self._install_ready_fixtures(facade)

            def resource_shortage(_self, execution, *_args, **_kwargs):
                # A preceding, confirmed formation mutation must not turn a
                # later deterministic resource check into an ambiguous launch.
                execution.mark_request_sent({
                    "feature": "formation",
                    "opcode": "0x1226",
                })
                # Shaped like the real energy step: the defer is decided from
                # the ``retryableResourceShortage`` fact it attaches, not from
                # the code, so the fixture has to carry it too.
                raise OperationKnownFailureError(
                    "副本检查到赵云体力=28，低于自动加体阈值40，但宝库没有活血丹",
                    code="EXPEDITION_ENERGY_ITEM_UNAVAILABLE",
                    details={
                        "retryableResourceShortage": True,
                        "resource": "活血丹",
                    },
                )

            facade._run_expedition_preflight = types.MethodType(  # noqa: SLF001
                resource_shortage, facade
            )
            result = facade._run_dungeon_action_game_workflow(  # noqa: SLF001
                FakeExecution(), self._body(facade), {}
            )["result"]

            self.assertEqual(result["state"], "waiting-resources")
            self.assertTrue(result["success"])
            self.assertFalse(result["requiresAttention"])
            self.assertEqual(result["nextWakeAtMillis"], clock.value + 300_000)
            stored = json.loads(facade.account_record_json("303"))["account"]
            public = stored["session"]["publicState"]
            self.assertEqual(public["dungeonPendingRunJson"], "{}")
            archived = json.loads(public["dungeonLastDeferredJson"])
            self.assertEqual(
                archived["recoveryResolution"],
                "retryable-resource-shortage",
            )
            self.assertFalse(archived["requiresAttention"])
        finally:
            facade.close()
            directory.cleanup()

    def test_legacy_resource_shortage_ledger_is_safely_deferred(self) -> None:
        facade, clock, directory = self._facade()
        try:
            self._install_ready_fixtures(facade)
            pending = {
                "generalIds": [7],
                "createdAtMillis": clock.value - 60_000,
                "preDispatchMutationState": "failed",
                "preDispatchMutationError": (
                    "副本检查到赵云体力=28，低于自动加体阈值40，"
                    "但宝库没有活血丹"
                ),
                "prepareSendState": "not-sent",
                "dispatchSendState": "not-sent",
                "chestSendState": "not-sent",
                "requiresAttention": True,
            }
            facade._save_automation_pending_record(  # noqa: SLF001
                "303", "dungeonPendingRunJson", pending
            )

            result = facade._run_dungeon_recovery_game_workflow(  # noqa: SLF001
                FakeExecution(), "303", pending, {}
            )

            self.assertEqual(result["state"], "waiting-resources")
            self.assertTrue(result["_pendingReleased"])
            self.assertEqual(result["nextWakeAtMillis"], clock.value + 300_000)
            stored = json.loads(facade.account_record_json("303"))["account"]
            self.assertEqual(
                stored["session"]["publicState"]["dungeonPendingRunJson"],
                "{}",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_resaving_config_only_archives_unambiguous_confirmed_defeat(
        self,
    ) -> None:
        facade, clock, directory = self._facade()
        try:
            confirmed = {
                "generalIds": [7],
                "stageRef": {"chapter": 0, "stage": 3},
                "battleId": 233292,
                "dispatchSendState": "accepted",
                "chestSendState": "rejected",
                "defeatConfirmed": True,
            }
            facade._save_automation_pending_record(  # noqa: SLF001
                "303", "dungeonPendingRunJson", confirmed
            )
            acknowledged = facade.acknowledge_dungeon_defeat("303")
            self.assertTrue(acknowledged["acknowledged"])
            stored = json.loads(facade.account_record_json("303"))["account"]
            public = stored["session"]["publicState"]
            self.assertEqual(public["dungeonPendingRunJson"], "{}")
            archived = json.loads(public["dungeonLastResultJson"])
            self.assertEqual(archived["state"], "defeat-acknowledged")
            self.assertEqual(archived["acknowledgedAtMillis"], clock.value)

            ambiguous = {
                **confirmed,
                "dispatchSendState": "uncertain",
            }
            facade._save_automation_pending_record(  # noqa: SLF001
                "303", "dungeonPendingRunJson", ambiguous
            )
            refused = facade.acknowledge_dungeon_defeat("303")
            self.assertFalse(refused["acknowledged"])
            self.assertEqual(
                refused["reason"], "ambiguous-mutation-boundary"
            )
            stored = json.loads(facade.account_record_json("303"))["account"]
            retained = json.loads(
                stored["session"]["publicState"]["dungeonPendingRunJson"]
            )
            self.assertEqual(retained["dispatchSendState"], "uncertain")
        finally:
            facade.close()
            directory.cleanup()

    def test_a_battle_in_progress_sends_nothing_and_yields_the_lane(self) -> None:
        """A battle nobody can hurry should not own the account lane.

        Measured on a real device: 副本 held 87% of all ticks purely polling a
        105s battle, and 刷黄 managed a single dispatch in 14.5 minutes.
        """

        facade, clock, directory = self._facade()
        try:
            battle_id = FIXTURES["dungeonStateAndPoll"]["expected"]["battleId"]
            launched_at = clock.value
            pending = {
                "generalIds": [7],
                "mode": "loop",
                "stageRef": {"chapter": 0, "stage": 3, "stageCode": 2},
                "chest": 2,
                "chestName": "右",
                "openChest": True,
                "createdAtMillis": launched_at,
                "dispatchAcceptedAtMillis": launched_at,
                "dispatchSendState": "accepted",
                "battleId": battle_id,
            }
            active = parse_dungeon_state(
                bytes.fromhex(
                    FIXTURES["dungeonStateAndPoll"]["fightingResponseHex"]
                )
            )
            facade._run_dungeon_status_game_workflow = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: dict(active),
                facade,
            )

            def refuse(*_args, **_kwargs):
                raise AssertionError("战斗期间不应发出任何游戏请求")

            facade._execute_host_game_command = types.MethodType(  # noqa: SLF001
                refuse, facade
            )
            first = facade._run_dungeon_recovery_game_workflow(  # noqa: SLF001
                FakeExecution(), "303", pending, {}
            )

            quiet = int(
                facade._behavior_contract["dungeon"]["schedule"][  # noqa: SLF001
                    "battleQuietMillis"
                ]
            )
            self.assertEqual(first["state"], "fighting")
            # No 0x1702 was sent, and the next look is deferred until the
            # battle can physically be over.
            self.assertEqual(first["nextWakeAtMillis"], launched_at + quiet)

            # The lane is free meanwhile: the pending is not "ready", so the
            # tick falls through to the configured features instead.
            follow_up = facade._run_automation_recovery_tick(  # noqa: SLF001
                FakeExecution(), "303", {}
            )
            self.assertNotEqual(follow_up.get("decidedVia"), "dungeon")

            stored = json.loads(facade.account_record_json("303"))["account"]
            retained = json.loads(
                stored["session"]["publicState"]["dungeonPendingRunJson"]
            )
            self.assertEqual(
                int(retained["nextPollAtMillis"]), launched_at + quiet
            )
        finally:
            facade.close()
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
