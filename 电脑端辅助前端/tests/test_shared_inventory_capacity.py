"""The 0x8104 bag limit lives in the trailer, and occupancy is a sum.

On three live accounts the shared parser reported bag capacities of 1863,
1386 and 1150.  The game shows 50 for all of them.  The reverse-engineered
client opens this packet with ``readLong, readLong, readShort`` - two asset
counters, then the stack count - so bytes 14..16 are the low half of the
second counter, not a limit.  The limit is the first short of the trailer the
client reads after the equipment bank, and the two captures below (inventory
syncs the server appended to 副本 chest replies) both end in
``0032 01f4 000a 05``.

The server never sends "slots used".  It sends the stack count and the
equipment count separately and the client adds them, which is what the 宝物
screen's "49/50" is; so does this parser, from the declared counts.

Each stack row also carries a per-stack long which the original client reads as
data.  It is usually zero, and this parser used to *require* zero as proof of
layout - so one time-limited item made a whole account fall back to a scan that
reports no equipment and no limit at all, showing "已占 43 格（上限未知）" and
silently blinding 背包整理 to every piece of equipment.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core.features.inventory import (  # noqa: E402
    parse_8104_footer,
    parse_8104_inventory,
)
from dwpm_core.verification import verify_protocol_fixtures  # noqa: E402
from dwpm_core import CoreFacade  # noqa: E402
from dwpm_core.ports import PlatformPorts  # noqa: E402


#: 0x8104 appended to a 副本 chest reply, account 176 (宿代苑): 37 stacks,
#: 12 pieces of equipment, limit 50 - the "49/50" the game showed that day.
CAPTURE_176 = bytes.fromhex(
    "000000000000004400000000000007470025000800020000000000000000006e000200000000"
    "00000000004000050000000000000000004200040000000000000000001d0003000000000000"
    "0000016600020000000000000000006c00010000000000000000006d00060000000000000000"
    "00c70004000000000000000000cb00040000000000000000000600050000000000000000001c"
    "00060000000000000000011e00070000000000000000004e00050000000000000000006b0002"
    "000000000000000001b000010000000000000000001400010000000000000000001800010000"
    "000000000000001b00040000000000000000004d000500000000000000000017000300000000"
    "00000000003b00220000000000000000004c000b000000000000000000200001000000000000"
    "0000002200200000000000000000001602a10000000000000000000c00110000000000000000"
    "0010001300000000000000000003006300000000000000000078001e00000000000000000003"
    "005000000000000000000072000b0000000000000000007300020000000000000000018f019a"
    "000000000000000000070048000000000000000000e700190000000000000000000400a40000"
    "000000000000000c00000000005198c600090200002710000000000000001400000000000000"
    "51dd4d0009020000271000000000000000140000000000000051dd4c00090201002710000000"
    "00000000140000000000000051ee26000a020000271000000000000000140000000000000052"
    "10a0000a020100271000000000000000140000000000000052cd300009020000271000000000"
    "000000140000000000000052cd310009020100271000000000000000140000000000000052d0"
    "c300090200002710000000000000001400000000000000531f73000902000027100000000000"
    "00001400000000000000531f72000a020000271000000000000000140000000000000053480f"
    "000902000027100000000000000014000000000000005358e700000200002710000000000000"
    "00140000003201f4000a05"
)

#: Same shape from account 202 (利萍丰): 34 stacks, 4 pieces, limit 50.
CAPTURE_202 = bytes.fromhex(
    "00000000000000b1000000000000056a0022000800020000000000000000006e000200000000"
    "00000000004000050000000000000000004200040000000000000000001d0003000000000000"
    "000002c500030000000000000000023f00020000000000000000006c00020000000000000000"
    "006d0005000000000000000000c70005000000000000000000cb000400000000000000000006"
    "00040000000000000000001500020000000000000000001c00060000000000000000011e0002"
    "0000000000000000004e00010000000000000000006b0005000000000000000001b000010000"
    "000000000000001b00080000000000000000004d00040000000000000000003b000a00000000"
    "00000000000d000100000000000000000000000900000000000000000023000a000000000000"
    "0000004c001700000000000000000020000200000000000000000079000d0000000000000000"
    "0022000a00000000000000000016014300000000000000000010018d00000000000000000078"
    "00100000000000000000000300040000000000000000007300010000000000000000018f0186"
    "000000000000000000040000000000063120000d020200271000000000000000140000000000"
    "000052a92d000a020013100c00000000000000640000000000000052cc430033020000271000"
    "000000000000140000000000000052dad60033020100271000000000000000140000003201f4"
    "000a05"
)


class Inventory8104CapacityTests(unittest.TestCase):
    def test_the_limit_is_read_from_the_trailer_not_the_header(self) -> None:
        for capture, header_low16, kinds, pieces in (
            (CAPTURE_176, 1863, 37, 12),
            (CAPTURE_202, 1386, 34, 4),
        ):
            with self.subTest(header_low16=header_low16):
                parsed = parse_8104_inventory(capture)
                self.assertEqual(parsed["layout"], "u16-id-u16-count-reserved8-table")
                self.assertIsNone(parsed.get("equipmentParseError"))
                # What the old parser called capacity is still visible, under
                # its real name, so nothing is lost - it just is not a limit.
                self.assertEqual(parsed["headerLong2"] & 0xFFFF, header_low16)
                self.assertEqual(parsed["capacity"], 50)
                self.assertEqual(parsed["itemCount"], kinds)
                self.assertEqual(parsed["declaredEquipmentCount"], pieces)
                self.assertEqual(parsed["equipmentCount"], pieces)
                self.assertEqual(parsed["slotsUsed"], kinds + pieces)
                self.assertEqual(parsed["slotsFree"], 50 - kinds - pieces)
                self.assertEqual(parsed["footer"]["values"], [50, 500, 10, 5])
                self.assertEqual(parsed["footer"]["rawHex"], "003201f4000a05")

    def test_occupancy_sums_the_declared_counts_not_the_decoded_rows(self) -> None:
        # A template table that knows none of these pieces makes every one an
        # unnamed "装备#N": still twelve slots, still 49/50.  (An empty
        # mapping would fall back to the built-in table, so use a foreign
        # one.)
        parsed = parse_8104_inventory(
            CAPTURE_176,
            equipment_templates={
                65535: {
                    "templateId": 65535, "name": "占位", "level": 1,
                    "typeCode": 0, "famous": False, "description": "",
                },
            },
        )
        self.assertTrue(all(row["name"].startswith("装备#") for row in parsed["equipment"]))
        self.assertEqual(parsed["slotsUsed"], 49)

    def test_a_missing_trailer_is_an_unknown_limit_not_a_guess(self) -> None:
        # The trailer starts right after the equipment bank; a packet cut
        # there says nothing about the limit and must not fall back to the
        # header bytes.
        end = parse_8104_inventory(CAPTURE_176)["v5EndOffset"]
        parsed = parse_8104_inventory(CAPTURE_176[:end])
        self.assertIsNone(parsed["capacity"])
        self.assertIsNone(parsed["slotsFree"])
        self.assertEqual(parsed["slotsUsed"], 49)
        self.assertEqual(parsed["footer"]["values"], [])

    def test_an_implausible_trailer_value_is_rejected(self) -> None:
        self.assertIsNone(parse_8104_footer(bytes.fromhex("0000"), 0)["capacity"])
        self.assertIsNone(parse_8104_footer(bytes.fromhex("ffff"), 0)["capacity"])
        self.assertEqual(parse_8104_footer(bytes.fromhex("0032"), 0)["capacity"], 50)

    def test_a_record_from_an_older_build_reports_an_unknown_limit(self) -> None:
        # Older builds stored the header counter under inventoryCapacity and
        # no version marker; showing it as "47/1863" would be worse than
        # showing no limit until the next refresh rewrites the record.
        import tempfile

        from dwpm_core import CoreFacade
        from dwpm_core.facade import INVENTORY_PARSER_VERSION
        from dwpm_core.ports import PlatformPorts

        directory = tempfile.TemporaryDirectory()
        facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(Path(directory.name) / "operations.json"),
            ports=PlatformPorts(),
        )
        try:
            rows = json.dumps([
                {"itemId": 12, "name": "活血丹", "count": 3},
                {"instanceId": 7, "type": "equipment", "name": "碧玉刀", "count": 1},
            ], ensure_ascii=False)
            legacy = facade._inventory_view_from_public_state({  # noqa: SLF001
                "inventoryJson": rows,
                "inventoryCapacity": "1863",
            })
            self.assertIsNone(legacy["capacity"])
            self.assertIsNone(legacy["slotsFree"])
            self.assertEqual(legacy["slotsUsed"], 2)
            # "还没读过" rather than "读不出来": the page says so, because the
            # account's next bag refresh resolves it with no user action.
            self.assertTrue(legacy["capacityPending"])

            fresh = facade._inventory_view_from_public_state({  # noqa: SLF001
                "inventoryJson": rows,
                "inventoryCapacity": "50",
                "inventorySlotsUsed": "49",
                "inventoryParserVersion": INVENTORY_PARSER_VERSION,
            })
            self.assertEqual(fresh["capacity"], 50)
            self.assertEqual(fresh["slotsUsed"], 49)
            self.assertEqual(fresh["slotsFree"], 1)
            self.assertFalse(fresh["capacityPending"])

            # And the writer stamps the marker the reader requires.
            written = facade._inventory_public_state_updates(  # noqa: SLF001
                parse_8104_inventory(CAPTURE_176)
            )
            self.assertEqual(written["inventoryParserVersion"], INVENTORY_PARSER_VERSION)
            self.assertEqual(written["inventoryCapacity"], "50")
            self.assertEqual(written["inventorySlotsUsed"], "49")
        finally:
            facade.close()
            directory.cleanup()

    def test_the_parity_fixture_agrees_with_the_captures(self) -> None:
        fixtures = json.loads(
            (ROOT / "shared_core" / "protocol_parity_fixtures.json").read_text(
                encoding="utf-8"
            )
        )["fixtures"]["inventory8104Compact"]
        payload = bytes.fromhex(fixtures["responseHex"])
        # The fixture header now carries 1863 where the old parser read the
        # limit, so a regression to that offset cannot pass as 50.
        self.assertEqual(int.from_bytes(payload[14:16], "big"), 1863)
        self.assertTrue(payload.hex().endswith("003201f4000a05"))
        report = verify_protocol_fixtures()
        inventory_check = next(
            row for row in report["checks"] if row["name"] == "inventory.8104"
        )
        self.assertTrue(inventory_check["passed"], inventory_check)


class Inventory8104LayoutGuardTests(unittest.TestCase):
    """A per-stack long is data, not proof of layout."""

    @staticmethod
    def _with_timed_long(capture: bytes, row: int) -> bytes:
        payload = bytearray(capture)
        offset = 18 + row * 12
        payload[offset + 4:offset + 12] = (1789000000000).to_bytes(8, "big")
        return bytes(payload)

    def test_a_time_limited_stack_no_longer_hides_the_whole_bag(self) -> None:
        baseline = parse_8104_inventory(CAPTURE_176)
        self.assertEqual(baseline["equipmentCount"], 12)
        last_row = baseline["itemCount"] - 1
        for row in (0, 3, last_row):
            with self.subTest(row=row):
                parsed = parse_8104_inventory(self._with_timed_long(CAPTURE_176, row))
                self.assertEqual(parsed["layout"], baseline["layout"])
                self.assertEqual(parsed["capacity"], 50)
                self.assertEqual(parsed["slotsUsed"], 49)
                # The equipment bank is what 背包整理 acts on; losing it made the
                # sweep decide there was nothing to discard.
                self.assertEqual(parsed["equipmentCount"], 12)
                self.assertEqual(
                    [row["instanceId"] for row in parsed["equipment"]],
                    [row["instanceId"] for row in baseline["equipment"]],
                )

    def test_the_long_is_preserved_as_row_evidence(self) -> None:
        parsed = parse_8104_inventory(self._with_timed_long(CAPTURE_202, 0))
        self.assertEqual(
            parsed["items"][0]["rawHex"],
            "00080002" + (1789000000000).to_bytes(8, "big").hex(),
        )

    def test_a_misaligned_table_is_still_rejected(self) -> None:
        # Claiming one stack too many walks the equipment bank off its start;
        # nothing downstream lines up, so the fixed layout must not be trusted.
        payload = bytearray(CAPTURE_202)
        payload[16:18] = (int.from_bytes(payload[16:18], "big") + 1).to_bytes(2, "big")
        parsed = parse_8104_inventory(bytes(payload))
        self.assertEqual(parsed["layout"], "legacy-scan-fallback")
        self.assertIsNone(parsed["capacity"])

    def test_a_trailing_equipment_error_still_surfaces_with_zero_longs(self) -> None:
        # Truncating mid-record leaves the equipment bank unparseable.  Every
        # per-stack long is zero here, which still corroborates the table, so
        # the items survive and the failure is reported rather than hidden.
        parsed = parse_8104_inventory(CAPTURE_202[:-40])
        self.assertEqual(parsed["layout"], "u16-id-u16-count-reserved8-table")
        self.assertEqual(parsed["itemCount"], 34)
        self.assertTrue(parsed.get("equipmentParseError"))
        self.assertIsNone(parsed["capacity"])


class FixedClock:
    def __init__(self, value: int = 1_789_300_000_000) -> None:
        self.value = int(value)

    def now_millis(self) -> int:
        return self.value


class FakeGameCommandPort:
    """Answers one command with the packets a real reply carried."""

    def __init__(self, packets: list[dict]) -> None:
        self.packets = packets
        self.calls = 0

    def execute(self, _account_ref, opcode, _payload, _phase, _context):
        self.calls += 1
        return {
            "requestOpcode": int(opcode),
            "httpCode": 200,
            "httpOk": True,
            "packets": [dict(packet) for packet in self.packets],
        }


class VolunteeredInventorySyncTests(unittest.TestCase):
    """A reply that carries a bag sync is a fresh bag, whoever asked for it.

    副本 opens a chest every few minutes and the server answers with a full
    0x8104.  That was dropped, so the 宝物 page showed an hour-old bag and -
    worse - 背包整理's "背包当前没有需要处理的物品" kept its hourly sleep even
    though the bag it described no longer existed.  A Lv.1 普通 短剑 that
    dropped a minute after the sweep sat in a 41/50 bag for the rest of the
    hour, though the saved policy selects exactly that piece.
    """

    def setUp(self) -> None:
        self.clock = FixedClock()
        self.directory = tempfile.TemporaryDirectory()
        self.facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(Path(self.directory.name) / "operations.json"),
            ports=PlatformPorts(clock=self.clock),
        )
        self.facade.account_record_upsert({
            "accountRef": "202",
            "id": 202,
            "username": "volunteered-inventory-fixture",
            "serverName": "fixture",
            "enabled": True,
            "loginState": "ONLINE",
            "session": {
                "accountId": 202,
                "sourceMode": 1,
                "publicState": {"roleId": "202", "lastValidatedAt": "1"},
            },
        })

    def tearDown(self) -> None:
        self.facade.close()
        self.directory.cleanup()

    def _public(self) -> dict:
        stored = json.loads(self.facade.account_record_json("202"))["account"]
        return stored["session"]["publicState"]

    def _chest_reply(self, capture: bytes = CAPTURE_202) -> None:
        # 0x8506 is the chest reply; the 0x8104 rides along with it.
        port = FakeGameCommandPort([
            {"opcode": 0x8506, "payloadHex": "0100"},
            {"opcode": 0x8104, "payloadHex": capture.hex()},
        ])
        self.facade._ports = self.facade._ports.__class__(  # noqa: SLF001
            **{**vars(self.facade._ports), "game_commands": port}  # noqa: SLF001
        )
        self.facade._execute_host_game_command(  # noqa: SLF001
            "202", 0x1506, b"\x00", "test/chest", {}, mutation_sent=True
        )

    def _set_inventory_state(self, slots_used: int, last_state: str) -> None:
        self.facade._update_account_public_state(  # noqa: SLF001
            "202",
            {
                "inventorySlotsUsed": str(slots_used),
                "residentAutomationStateJson": json.dumps({
                    "inventory": {
                        "lastState": last_state,
                        "lastMessage": "背包当前没有需要处理的物品",
                        "nextWakeAtMillis": self.clock.value + 3_600_000,
                    },
                }),
            },
        )

    def test_a_chest_reply_refreshes_the_bag_the_page_shows(self) -> None:
        self._chest_reply()
        public = self._public()
        self.assertEqual(public["inventoryCapacity"], "50")
        self.assertEqual(public["inventorySlotsUsed"], "38")
        self.assertEqual(public["inventoryEquipmentCount"], "4")
        view = self.facade._inventory_view_from_public_state(public)  # noqa: SLF001
        self.assertEqual(view["capacity"], 50)
        self.assertEqual(view["slotsUsed"], 38)
        self.assertEqual(view["slotsFree"], 12)
        self.assertEqual(len(view["equipment"]), 4)

    def test_a_fuller_bag_expires_the_sweeps_hourly_sleep(self) -> None:
        self._set_inventory_state(30, "waiting")
        self._chest_reply()
        state = json.loads(self._public()["residentAutomationStateJson"])
        self.assertEqual(state["inventory"]["nextWakeAtMillis"], self.clock.value)
        self.assertIn("背包又有新物品", state["inventory"]["lastMessage"])

    def test_a_bag_that_did_not_grow_keeps_the_sleep(self) -> None:
        # 38 -> 38 is the sweep seeing its own work; waking would spin.
        self._set_inventory_state(38, "waiting")
        self._chest_reply()
        state = json.loads(self._public()["residentAutomationStateJson"])
        self.assertEqual(
            state["inventory"]["nextWakeAtMillis"], self.clock.value + 3_600_000
        )

    def test_a_sweep_mid_cycle_is_not_interrupted(self) -> None:
        # Only the "nothing to do" conclusion expires; a running cycle already
        # re-reads the bag every second and owns its own deadline.
        self._set_inventory_state(30, "completed")
        self._chest_reply()
        state = json.loads(self._public()["residentAutomationStateJson"])
        self.assertEqual(
            state["inventory"]["nextWakeAtMillis"], self.clock.value + 3_600_000
        )

    def test_a_reply_without_a_bag_sync_changes_nothing(self) -> None:
        self._set_inventory_state(30, "waiting")
        port = FakeGameCommandPort([{"opcode": 0x8506, "payloadHex": "0100"}])
        self.facade._ports = self.facade._ports.__class__(  # noqa: SLF001
            **{**vars(self.facade._ports), "game_commands": port}  # noqa: SLF001
        )
        self.facade._execute_host_game_command(  # noqa: SLF001
            "202", 0x1506, b"\x00", "test/chest", {}, mutation_sent=True
        )
        public = self._public()
        self.assertEqual(public["inventorySlotsUsed"], "30")
        state = json.loads(public["residentAutomationStateJson"])
        self.assertEqual(
            state["inventory"]["nextWakeAtMillis"], self.clock.value + 3_600_000
        )

    def test_bookkeeping_never_fails_the_game_action(self) -> None:
        # A truncated sync must not turn an accepted chest open into an error.
        self._chest_reply(CAPTURE_202[:60])
        self.assertNotIn("inventoryCapacity", self._public())


if __name__ == "__main__":
    unittest.main()
