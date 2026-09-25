from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core import CoreFacade  # noqa: E402
from dwpm_core.features.expedition import (  # noqa: E402
    build_lossless_expedition_payload,
    build_lossless_prepare_payload,
)
from dwpm_core.features.lossless import (  # noqa: E402
    parse_lossless_catalog,
    parse_lossless_lineup,
    parse_lossless_settlement,
    parse_lossless_status,
)
from dwpm_core.operations import (  # noqa: E402
    OperationKnownFailureError,
    OperationUncertainError,
)
from dwpm_core.ports import PlatformPorts  # noqa: E402
from dwpm_core.protocol.wire import parse_response  # noqa: E402
from shared_raw_http_test_host import (  # noqa: E402
    _decode_request_commands,
    _encode_response,
)


CAPTURE_FLOWS = (
    ROOT
    / "电脑端辅助前端"
    / "tests"
    / "fixtures"
    / "game_packets"
    / "passive_pcap_hotspot_20260710_185601"
    / "live_analyzed"
)


def capture_payload(flow_index: int, opcode: int) -> bytes:
    packets = parse_response(
        (CAPTURE_FLOWS / f"{flow_index:03d}" / "resp.bin").read_bytes()
    )
    return next(
        packet["payload"]
        for packet in packets
        if packet.get("opcode") == opcode
    )


class FixedClock:
    def __init__(self, value: int = 30_000_000) -> None:
        self.value = value

    def now_millis(self) -> int:
        return self.value


class FakeExecution:
    operation_id = "op_lossless_fixture"

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


class StaticSecrets:
    def save(self, _account_ref: str, _values: Mapping[str, str]) -> None:
        return None

    def load(self, _account_ref: str) -> Mapping[str, str]:
        return {"dm": "202"}

    def delete(self, _account_ref: str) -> None:
        return None


class SettlementRawHttp:
    def __init__(self) -> None:
        self.commands: list[tuple[int, bytes]] = []

    def exchange(self, request: Mapping[str, object]) -> Mapping[str, object]:
        self.commands = _decode_request_commands(
            bytes(request.get("body") or b"")
        )
        return {
            "status": 200,
            "body": _encode_response([
                {
                    "opcode": 0x8902,
                    "payloadHex": capture_payload(17, 0x8902).hex(),
                },
                {
                    "opcode": 0x8904,
                    "payloadHex": capture_payload(85, 0x8904).hex(),
                },
            ]),
            "headers": {},
        }


class SharedLosslessAutomationTests(unittest.TestCase):
    def _facade(self, *, raw_http=None):
        directory = tempfile.TemporaryDirectory()
        clock = FixedClock()
        facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(Path(directory.name) / "operations.json"),
            ports=PlatformPorts(
                clock=clock,
                raw_http=raw_http,
                session_secrets=(StaticSecrets() if raw_http else None),
            ),
        )
        facade.account_record_upsert({
            "accountRef": "202",
            "id": 202,
            "username": "lossless-fixture",
            "platform": "sglm",
            "platformKey": "sglm",
            "enabled": True,
            "loginState": "ONLINE",
            "session": {
                "accountId": 202,
                "sourceMode": 1,
                "publicState": {
                    "roleId": "202",
                    "gameHttp": (
                        "https://fixture.invalid/kingWapServer/HttpClient"
                    ),
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

    def _install_ready_fixtures(self, facade: CoreFacade) -> None:
        status = parse_lossless_status(capture_payload(84, 0x8900))
        catalog = parse_lossless_catalog(capture_payload(85, 0x8904))
        lineup = parse_lossless_lineup(capture_payload(86, 0x8906))
        facade._run_lossless_status_game_workflow = types.MethodType(  # noqa: SLF001
            lambda _self, *_args, **_kwargs: dict(status),
            facade,
        )
        facade._run_lossless_catalog_game_workflow = types.MethodType(  # noqa: SLF001
            lambda _self, *_args, **_kwargs: dict(catalog),
            facade,
        )
        facade._run_lossless_lineup_game_workflow = types.MethodType(  # noqa: SLF001
            lambda _self, *_args, **_kwargs: dict(lineup),
            facade,
        )
        selected = [self._general()]
        facade._run_expedition_preflight = types.MethodType(  # noqa: SLF001
            lambda _self, *_args, **_kwargs: (
                [dict(row) for row in selected],
                {"generalIds": [7]},
            ),
            facade,
        )

    @staticmethod
    def _body(facade: CoreFacade) -> dict[str, object]:
        return facade.lossless_action_operation_payload({
            "accountRef": "202",
            "confirm": "lossless",
            "generalIds": ["7"],
            "level": 10,
            "fullTroops": False,
            "maxLineupRerolls": 3,
        }, {})

    def test_ready_tick_uses_shared_payload_and_persists_battle(self) -> None:
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
                    "requestOpcode": int(opcode),
                    "httpCode": 200,
                    "httpOk": True,
                    "packets": [{
                        "opcode": 0x8520 if opcode == 0x1520 else 0x8522,
                        "payload": (
                            b""
                            if opcode == 0x1520
                            else bytes.fromhex("00000000000000006c42d1")
                        ),
                    }],
                }

            facade._execute_host_game_command = types.MethodType(  # noqa: SLF001
                command, facade
            )
            response = facade._run_lossless_action_game_workflow(  # noqa: SLF001
                FakeExecution(), self._body(facade), {}
            )
            result = response["result"]
            self.assertTrue(result["success"])
            self.assertEqual(result["successBattleId"], 7094993)
            self.assertEqual(commands, [
                (
                    0x1520,
                    build_lossless_prepare_payload(
                        ["0000000000000007"], 202
                    ),
                ),
                (
                    0x1522,
                    build_lossless_expedition_payload(
                        ["0000000000000007"], 202
                    ),
                ),
            ])
            stored = json.loads(facade.account_record_json("202"))["account"]
            pending = json.loads(
                stored["session"]["publicState"]["losslessPendingBattleJson"]
            )
            self.assertEqual(pending["dispatchSendState"], "accepted")
            self.assertEqual(pending["battleId"], 7094993)
            self.assertEqual(pending["generalIds"], [7])
        finally:
            facade.close()
            directory.cleanup()

    def test_configured_daily_limit_stops_new_dispatch_but_keeps_status_read(
        self,
    ) -> None:
        facade, clock, directory = self._facade()
        try:
            facade._run_lossless_status_game_workflow = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: {
                    "mode": 1,
                    "remainingAttempts": 2,
                    "usedAttempts": 3,
                    "settlementPending": False,
                },
                facade,
            )
            body = facade.lossless_action_operation_payload({
                "accountRef": "202",
                "confirm": "lossless",
                "generalIds": ["7"],
                "level": 10,
                "dailyLimit": 3,
            }, {})
            result = facade._run_lossless_action_game_workflow(  # noqa: SLF001
                FakeExecution(), body, {}
            )["result"]
            self.assertEqual(result["state"], "configured-daily-limit")
            self.assertEqual(
                result["nextWakeAtMillis"],
                facade._next_china_midnight_millis(clock.value),  # noqa: SLF001
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_missing_prepare_receipt_never_sends_dispatch(self) -> None:
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
                return {
                    "requestOpcode": int(opcode),
                    "httpCode": 200,
                    "httpOk": True,
                    "packets": [],
                }

            facade._execute_host_game_command = types.MethodType(  # noqa: SLF001
                command, facade
            )
            with self.assertRaisesRegex(
                OperationKnownFailureError,
                "已禁止发送正式出征",
            ):
                facade._run_lossless_action_game_workflow(  # noqa: SLF001
                    FakeExecution(), self._body(facade), {}
                )
            self.assertEqual(commands, [0x1520])
            stored = json.loads(facade.account_record_json("202"))["account"]
            self.assertEqual(
                stored["session"]["publicState"]["losslessPendingBattleJson"],
                "{}",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_pre_dispatch_network_ledger_is_archived_after_ready_recheck(
        self,
    ) -> None:
        facade, _clock, directory = self._facade()
        try:
            self._install_ready_fixtures(facade)

            def interrupted_preflight(
                _self,
                execution,
                *_args,
                **_kwargs,
            ):
                execution.mark_request_sent({
                    "feature": "troop-heal",
                    "opcode": "0x1230",
                })
                raise OperationUncertainError("治疗回执丢失")

            facade._run_expedition_preflight = types.MethodType(  # noqa: SLF001
                interrupted_preflight, facade
            )
            with self.assertRaisesRegex(
                OperationUncertainError,
                "治疗回执丢失",
            ):
                facade._run_lossless_action_game_workflow(  # noqa: SLF001
                    FakeExecution(), self._body(facade), {}
                )

            stored = json.loads(facade.account_record_json("202"))["account"]
            pending = json.loads(
                stored["session"]["publicState"]["losslessPendingBattleJson"]
            )
            self.assertEqual(
                pending["preDispatchMutationState"], "uncertain"
            )
            self.assertEqual(pending["preDispatchMutationCount"], 1)
            self.assertEqual(
                pending["preDispatchMutationMetadata"]["feature"],
                "troop-heal",
            )
            self.assertEqual(pending["dispatchSendState"], "not-sent")

            recovery_execution = FakeExecution()
            recovery = facade._run_lossless_recovery_game_workflow(  # noqa: SLF001
                recovery_execution, "202", pending, {}
            )
            self.assertEqual(recovery["state"], "recovered-ready")
            self.assertFalse(recovery["requiresAttention"])
            self.assertTrue(recovery["_pendingReleased"])
            self.assertEqual(recovery_execution.sent, [])
            self.assertIn("正式出征明确未发送", recovery["message"])
            stored = json.loads(facade.account_record_json("202"))["account"]
            public = stored["session"]["publicState"]
            self.assertEqual(public["losslessPendingBattleJson"], "{}")
            archived = json.loads(public["losslessLastRecoveryJson"])
            self.assertEqual(
                archived["recoveryResolution"],
                "latest-status-ready-formal-dispatch-not-sent",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_missing_energy_item_defers_five_minutes_without_stopping(self) -> None:
        facade, clock, directory = self._facade()
        try:
            self._install_ready_fixtures(facade)

            def resource_shortage(_self, execution, *_args, **_kwargs):
                execution.mark_request_sent({
                    "feature": "formation",
                    "opcode": "0x1226",
                })
                # Shaped like the real energy step: the defer is decided from
                # the ``retryableResourceShortage`` fact it attaches, not from
                # the code, so the fixture has to carry it too.
                raise OperationKnownFailureError(
                    "无损检查到赵云体力=31，低于自动加体阈值40，但宝库没有活血丹",
                    code="EXPEDITION_ENERGY_ITEM_UNAVAILABLE",
                    details={
                        "retryableResourceShortage": True,
                        "resource": "活血丹",
                    },
                )

            facade._run_expedition_preflight = types.MethodType(  # noqa: SLF001
                resource_shortage, facade
            )
            result = facade._run_lossless_action_game_workflow(  # noqa: SLF001
                FakeExecution(), self._body(facade), {}
            )["result"]

            self.assertEqual(result["state"], "waiting-resources")
            self.assertTrue(result["success"])
            self.assertFalse(result["requiresAttention"])
            self.assertEqual(result["nextWakeAtMillis"], clock.value + 300_000)
            stored = json.loads(facade.account_record_json("202"))["account"]
            public = stored["session"]["publicState"]
            self.assertEqual(public["losslessPendingBattleJson"], "{}")
            archived = json.loads(public["losslessLastDeferredJson"])
            self.assertEqual(
                archived["recoveryResolution"],
                "retryable-resource-shortage",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_legacy_resource_shortage_ledger_is_safely_deferred(self) -> None:
        facade, clock, directory = self._facade()
        try:
            self._install_ready_fixtures(facade)
            pending = {
                "generalIds": [7],
                "level": 10,
                "preDispatchMutationState": "failed",
                "preDispatchMutationError": (
                    "无损检查到赵云体力=31，低于自动加体阈值40，"
                    "但宝库没有活血丹"
                ),
                "prepareSendState": "not-sent",
                "dispatchSendState": "not-sent",
                "requiresAttention": True,
            }
            facade._save_automation_pending_record(  # noqa: SLF001
                "202", "losslessPendingBattleJson", pending
            )

            result = facade._run_lossless_recovery_game_workflow(  # noqa: SLF001
                FakeExecution(), "202", pending, {}
            )

            self.assertEqual(result["state"], "waiting-resources")
            self.assertTrue(result["_pendingReleased"])
            self.assertEqual(result["nextWakeAtMillis"], clock.value + 300_000)
            stored = json.loads(facade.account_record_json("202"))["account"]
            self.assertEqual(
                stored["session"]["publicState"]["losslessPendingBattleJson"],
                "{}",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_pre_dispatch_validation_failure_clears_empty_ledger(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            self._install_ready_fixtures(facade)

            def rejected_preflight(_self, *_args, **_kwargs):
                raise OperationKnownFailureError(
                    "缺少配兵规则",
                    code="EXPEDITION_FORMATION_RULE_MISSING",
                )

            facade._run_expedition_preflight = types.MethodType(  # noqa: SLF001
                rejected_preflight, facade
            )
            with self.assertRaisesRegex(
                OperationKnownFailureError,
                "缺少配兵规则",
            ):
                facade._run_lossless_action_game_workflow(  # noqa: SLF001
                    FakeExecution(), self._body(facade), {}
                )
            stored = json.loads(facade.account_record_json("202"))["account"]
            self.assertEqual(
                stored["session"]["publicState"]["losslessPendingBattleJson"],
                "{}",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_cooldown_tick_returns_next_wake_without_mutation(self) -> None:
        facade, clock, directory = self._facade()
        try:
            status = parse_lossless_status(
                bytes.fromhex(
                    "000000000005909e000203000000000000003f71b000000005"
                )
            )
            facade._run_lossless_status_game_workflow = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: dict(status),
                facade,
            )
            execution = FakeExecution()
            result = facade._run_lossless_action_game_workflow(  # noqa: SLF001
                execution, self._body(facade), {}
            )["result"]
            self.assertEqual(result["state"], "cooldown")
            self.assertEqual(result["nextWakeAtMillis"], clock.value + 60_000)
            self.assertEqual(execution.sent, [])
        finally:
            facade.close()
            directory.cleanup()

    def test_settlement_preserves_two_commands_in_one_raw_packet(self) -> None:
        raw_http = SettlementRawHttp()
        facade, _clock, directory = self._facade(raw_http=raw_http)
        try:
            execution = FakeExecution()
            settlement = facade._run_lossless_settlement_game_workflow(  # noqa: SLF001
                execution, "202", {}
            )
            self.assertTrue(settlement["success"])
            self.assertTrue(settlement["battleFailed"])
            self.assertNotIn("parseError", settlement["catalog"])
            self.assertEqual(raw_http.commands, [(0x1902, b"\x00"), (0x1904, b"\x00")])
            self.assertEqual(len(execution.sent), 1)
        finally:
            facade.close()
            directory.cleanup()

    def test_recovery_settles_before_judging_old_pre_dispatch_ledger(self) -> None:
        facade, clock, directory = self._facade()
        try:
            pending = {
                "generalIds": [7],
                "level": 10,
                "battleId": 7094993,
                "preDispatchMutationState": "uncertain",
                "preDispatchMutationCount": 2,
                "preDispatchMutationMetadata": {
                    "feature": "formation",
                    "opcode": "0x1226",
                },
                "preDispatchMutationError": "检查治疗费用时网络 HTTP 0",
                "prepareSendState": "not-sent",
                "dispatchSendState": "not-sent",
                "createdAtMillis": clock.value - 20_000,
            }
            facade._save_automation_pending_record(  # noqa: SLF001
                "202", "losslessPendingBattleJson", pending
            )
            settlement_status = parse_lossless_status(
                capture_payload(15, 0x8900)
            )
            settlement_result = parse_lossless_settlement(
                capture_payload(17, 0x8902)
            )
            facade._run_lossless_status_game_workflow = types.MethodType(  # noqa: SLF001
                lambda _self, *_args, **_kwargs: dict(settlement_status),
                facade,
            )

            def settle(_self, execution, *_args, **_kwargs):
                execution.mark_request_sent({"feature": "lossless-settlement"})
                return dict(settlement_result)

            facade._run_lossless_settlement_game_workflow = types.MethodType(  # noqa: SLF001
                settle, facade
            )
            execution = FakeExecution()
            result = facade._run_lossless_recovery_game_workflow(  # noqa: SLF001
                execution, "202", pending, {}
            )
            self.assertEqual(result["state"], "settled")
            stored = json.loads(facade.account_record_json("202"))["account"]
            public = stored["session"]["publicState"]
            self.assertEqual(public["losslessPendingBattleJson"], "{}")
            self.assertTrue(json.loads(public["losslessLastResultJson"])["settlement"])
            self.assertEqual(len(execution.sent), 1)
        finally:
            facade.close()
            directory.cleanup()

    def test_formal_dispatch_uncertain_still_blocks_automatic_resend(self) -> None:
        facade, _clock, directory = self._facade()
        try:
            self._install_ready_fixtures(facade)
            pending = {
                "generalIds": [7],
                "preDispatchMutationState": "accepted",
                "prepareSendState": "accepted",
                "dispatchSendState": "uncertain",
                "dispatchError": "正式出征 HTTP 0",
            }
            execution = FakeExecution()
            result = facade._run_lossless_recovery_game_workflow(  # noqa: SLF001
                execution, "202", pending, {}
            )

            self.assertEqual(result["state"], "blocked")
            self.assertTrue(result["requiresAttention"])
            self.assertIn("禁止自动重发", result["message"])
            self.assertEqual(execution.sent, [])
        finally:
            facade.close()
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
