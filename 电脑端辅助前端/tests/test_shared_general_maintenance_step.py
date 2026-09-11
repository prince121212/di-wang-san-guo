from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core.facade import CoreFacade


class FakeExecution:
    operation_id = "shared-general-maintenance-fixture"

    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def raise_if_cancelled(self) -> None:
        return None

    def mark_request_sent(self, metadata) -> None:
        self.sent.append(dict(metadata))


class SharedGeneralMaintenanceStepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(
            (ROOT / "shared_core" / "protocol_parity_fixtures.json").read_text(
                encoding="utf-8"
            )
        )["fixtures"]["maintenanceProtocols"]

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.facade = CoreFacade(
            ROOT / "shared_core",
            str(Path(self.directory.name) / "operations.json"),
        )

    def tearDown(self) -> None:
        self.facade.close()
        self.directory.cleanup()

    def test_shared_step_reuses_exact_energy_and_loyalty_protocols(self) -> None:
        fixture = self.fixture
        commands: list[tuple[int, bytes, bool]] = []
        self.facade._fresh_inventory_state = types.MethodType(  # noqa: SLF001
            lambda _self, _account_ref, _context, *, phase: {
                "items": [{"itemId": 12, "name": "活血丹", "count": 5}],
                "phase": phase,
            },
            self.facade,
        )

        def command_fact(
            _self,
            _execution,
            _account_ref,
            opcode,
            payload,
            _phase,
            _context,
            *,
            mutation_sent,
        ):
            commands.append((int(opcode), bytes(payload), bool(mutation_sent)))
            if int(opcode) == 0x1218:
                response_opcode = 0x8218
                response = bytes.fromhex(fixture["generalItemResponseHex"])
            elif int(opcode) == 0x121F:
                response_opcode = 0x821F
                response = bytes.fromhex(fixture["addLoyaltyResponseHex"])
            else:
                raise AssertionError(f"unexpected opcode: {int(opcode):#x}")
            return {"packets": [{"opcode": response_opcode, "payload": response}]}

        self.facade._daily_command_fact = types.MethodType(  # noqa: SLF001
            command_fact,
            self.facade,
        )
        general = {
            "id": fixture["generalId"],
            "name": "共享维护将领",
            "energyReliable": True,
            "tili": 5,
            "loyalty": 59,
            "loyaltyLimit": 100,
        }
        execution = FakeExecution()

        result = self.facade._run_general_maintenance_step(  # noqa: SLF001
            execution,
            "202",
            general,
            {},
            auto_energy=True,
            energy_threshold=20,
            keep_full_loyalty=True,
            action_name="共享维护测试",
        )

        self.assertEqual(result["energy"]["after"], 55)
        self.assertEqual(result["loyalty"]["loyalty"], 100)
        self.assertEqual(general["tili"], 55)
        self.assertEqual(general["loyalty"], 100)
        self.assertEqual(
            [(opcode, payload.hex(), sent) for opcode, payload, sent in commands],
            [
                (0x1218, fixture["generalItemPayloadHex"], True),
                (0x121F, fixture["addLoyaltyPayloadHex"], True),
            ],
        )
        self.assertEqual(
            [row["feature"] for row in execution.sent],
            ["general-maintenance-energy", "general-maintenance-loyalty"],
        )

    def test_expedition_preflight_delegates_to_the_shared_step(self) -> None:
        general = {
            "id": 7,
            "name": "复用将领",
            "statusText": "闲",
            "displayStatus": "闲",
            "energyReliable": True,
            "tili": 80,
            "loyalty": 90,
            "loyaltyLimit": 100,
            "soldierCount": 120,
            "currentSoldierCount": 120,
        }
        self.facade._fresh_formation_state = types.MethodType(  # noqa: SLF001
            lambda _self, _account_ref, _context, read_only=False: (
                "",
                [dict(general)],
                [],
            ),
            self.facade,
        )
        calls: list[dict[str, object]] = []

        def maintenance(
            _self,
            _execution,
            _account_ref,
            selected,
            _context,
            **options,
        ):
            calls.append({"general": dict(selected), **dict(options)})
            return {
                "generalId": int(selected["id"]),
                "energy": {"reason": "energy-sufficient"},
                "loyalty": {"success": True},
            }

        self.facade._run_general_maintenance_step = types.MethodType(  # noqa: SLF001
            maintenance,
            self.facade,
        )
        selected, preflight = self.facade._run_expedition_preflight(  # noqa: SLF001
            FakeExecution(),
            "202",
            {
                "generalIds": [7],
                "hostSettings": {
                    "config": {
                        "healWounded": False,
                        "autoEnergy": True,
                        "energyThreshold": 35,
                    }
                },
            },
            {},
            action_name="复用验证",
            require_full_loyalty=True,
            restore_saved_formation=False,
        )

        self.assertEqual([row["id"] for row in selected], [7])
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["auto_energy"])
        self.assertEqual(calls[0]["energy_threshold"], 35)
        self.assertTrue(calls[0]["keep_full_loyalty"])
        self.assertEqual(preflight["maintenance"][0]["generalId"], 7)


class EnergyItemSuccessRecordTests(unittest.TestCase):
    """A spent 活血丹 must leave a trace the user can actually find.

    Every feature tops generals up through the one shared step, but none of
    them reported it: 将领维护's tick message is only "将领维护完成", and an
    expedition reports its dispatch.  The item was consumed and nothing on the
    role page said so.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(
            (ROOT / "shared_core" / "protocol_parity_fixtures.json").read_text(
                encoding="utf-8"
            )
        )["fixtures"]["maintenanceProtocols"]

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.facade = CoreFacade(
            ROOT / "shared_core",
            str(Path(self.directory.name) / "operations.json"),
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
                },
            },
        })

    def tearDown(self) -> None:
        self.facade.close()
        self.directory.cleanup()

    def _records(self) -> list[dict[str, object]]:
        account = json.loads(self.facade.account_record_json("202"))["account"]
        raw = account["session"]["publicState"].get("successRecordsJson") or "[]"
        return [row for row in json.loads(raw) if isinstance(row, dict)]

    def _run_energy_step(self, *, tili: int) -> dict[str, object]:
        fixture = self.fixture
        self.facade._fresh_inventory_state = types.MethodType(  # noqa: SLF001
            lambda _self, _account_ref, _context, *, phase: {
                "items": [{"itemId": 12, "name": "活血丹", "count": 5}],
                "phase": phase,
            },
            self.facade,
        )
        self.facade._daily_command_fact = types.MethodType(  # noqa: SLF001
            lambda *_args, **_kwargs: {
                "packets": [{
                    "opcode": 0x8218,
                    "payload": bytes.fromhex(
                        fixture["generalItemResponseHex"]
                    ),
                }]
            },
            self.facade,
        )
        return self.facade._run_general_energy_maintenance_step(  # noqa: SLF001
            FakeExecution(),
            "202",
            {
                "id": fixture["generalId"],
                "name": "共享维护将领",
                "energyReliable": True,
                "tili": tili,
            },
            {},
            enabled=True,
            threshold=20,
            action_name="将领维护",
        )

    def test_an_accepted_receipt_is_recorded_for_the_role_page(self) -> None:
        applied = self._run_energy_step(tili=5)
        self.assertTrue(applied["success"])

        records = self._records()
        self.assertEqual(len(records), 1)
        record = records[0]
        # 政事 is everything the role page does not list as 军事, so the
        # category must stay outside that set.
        self.assertEqual(record["category"], "活血丹")
        self.assertIn("共享维护将领", record["message"])
        self.assertIn("体力5→55", record["message"])
        self.assertIn("将领维护", record["message"])
        self.assertEqual(record["detail"]["generalId"], self.fixture["generalId"])
        self.assertEqual(record["detail"]["itemCount"], 1)
        self.assertEqual(record["detail"]["remainingItemCount"], 4)
        self.assertEqual(record["sessionId"], "202")

    def test_the_record_reaches_the_role_page_projection(self) -> None:
        """The durable write is only useful if the page projection returns it.

        A record that is written but never read is exactly how earlier facts
        stayed invisible, so this asserts the whole path rather than the store.
        """

        self._run_energy_step(tili=5)
        projected = self.facade._success_records_route(  # noqa: SLF001
            {"accountRef": "202"}, {}
        )
        categories = [row["category"] for row in projected["entries"]]
        self.assertIn("活血丹", categories)
        military = {
            "刷黄", "副本", "掠夺", "无损", "打矿", "抢城", "押镖", "寻宝",
            "出征", "治疗", "加体",
        }
        self.assertNotIn("活血丹", military)

    def test_a_general_that_needed_nothing_records_nothing(self) -> None:
        applied = self._run_energy_step(tili=90)
        self.assertFalse(applied.get("actionRequired"))
        self.assertEqual(self._records(), [])


class EnergyRecordReducerTests(unittest.TestCase):
    def test_the_reducer_keeps_the_record_off_the_military_tab(self) -> None:
        from dwpm_core.local_views import general_energy_success_record

        record = general_energy_success_record(
            {
                "success": True,
                "actionRequired": True,
                "generalId": 7,
                "generalName": "赵云",
                "itemName": "活血丹",
                "itemCount": 1,
                "before": 12,
                "after": 32,
                "actionName": "副本",
                "availableItemCount": 3,
            },
            now_millis=1_700_000_123_456,
        )

        assert record is not None
        self.assertEqual(record["category"], "活血丹")
        self.assertEqual(
            record["message"], "赵云 使用1枚活血丹，体力12→32，来源副本"
        )
        self.assertEqual(record["detail"]["remainingItemCount"], 2)

    def test_two_uses_in_the_same_minute_are_one_event(self) -> None:
        """The item grants more energy than the lowest threshold that triggers it.

        So a second genuine top-up of the same general cannot happen within a
        minute, and a repeated report is a duplicate rather than a new fact.
        """

        from dwpm_core.local_views import general_energy_success_record

        base = {
            "success": True,
            "actionRequired": True,
            "generalId": 7,
            "generalName": "赵云",
            "before": 12,
            "after": 32,
        }
        first = general_energy_success_record(base, now_millis=1_700_000_000_000)
        second = general_energy_success_record(base, now_millis=1_700_000_030_000)
        assert first is not None and second is not None
        self.assertEqual(first["dedupeKey"], second["dedupeKey"])

    def test_zero_is_a_real_reading_on_both_counters(self) -> None:
        """体力0 is exactly who needs the item, and 0 left is what to warn about."""

        from dwpm_core.local_views import general_energy_success_record

        record = general_energy_success_record(
            {
                "success": True,
                "actionRequired": True,
                "generalId": 7,
                "generalName": "赵云",
                "before": 0,
                "after": 20,
                "availableItemCount": 1,
            },
            now_millis=1_700_000_000_000,
        )

        assert record is not None
        self.assertIn("体力0→20", record["message"])
        self.assertEqual(record["detail"]["remainingItemCount"], 0)

    def test_a_failed_or_skipped_step_is_not_a_record(self) -> None:
        from dwpm_core.local_views import general_energy_success_record

        self.assertIsNone(general_energy_success_record(None, now_millis=1))
        self.assertIsNone(
            general_energy_success_record(
                {"actionRequired": True, "success": False}, now_millis=1
            )
        )
        self.assertIsNone(
            general_energy_success_record(
                {"actionRequired": False, "reason": "energy-sufficient"},
                now_millis=1,
            )
        )


if __name__ == "__main__":
    unittest.main()
