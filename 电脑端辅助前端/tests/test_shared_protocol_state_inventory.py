from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = ROOT / "shared_core" / "python"
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
FIXTURE_PATH = ROOT / "shared_core" / "protocol_parity_fixtures.json"
if str(CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CORE_SOURCE))

from dwpm_core.features.generals import (
    office_name_from_id,
    parse_8004_head,
    parse_a110_general_statuses,
    parse_idle_army_from_8004,
    parse_military_intel_from_a110,
)
from dwpm_core.features.inventory import (
    AUTO_OPEN_ITEM_NAMES,
    DEFAULT_ITEM_NAMES,
    inventory_reward_log_text,
    parse_8104_inventory,
    plan_open_one_inventory,
)
from dwpm_core.protocol.wire import parse_response


SPEC = importlib.util.spec_from_file_location(
    "dwpm_server_state_inventory_shared_parity",
    SERVER_PATH,
)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class SharedStateInventoryProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.fixtures = payload["fixtures"]

    def test_role_head_8004_runs_in_shared_core(self) -> None:
        fixture = self.fixtures["roleHead8004"]
        payload = bytes.fromhex(fixture["responseHex"])
        role = parse_8004_head(payload)

        self.assertEqual(SERVER.parse_8004_head(payload), role)
        for key, value in fixture["expected"].items():
            self.assertEqual(role[key], value)
        self.assertEqual(
            SERVER.office_name_from_id(role["officeIdUnsigned"]),
            office_name_from_id(role["officeIdUnsigned"]),
        )

    def test_idle_army_8004_runs_in_shared_core(self) -> None:
        fixture = self.fixtures["idleArmy8004"]
        rows = parse_idle_army_from_8004(fixture["responseHex"])

        self.assertEqual(
            SERVER.parse_idle_army_from_8004(fixture["responseHex"]),
            rows,
        )
        self.assertEqual(len(rows), len(fixture["expected"]))
        for actual, expected in zip(rows, fixture["expected"]):
            for key, value in expected.items():
                self.assertEqual(actual[key], value)

    def test_general_status_a110_runs_in_shared_core(self) -> None:
        fixture = self.fixtures["generalStatusA110"]
        payload = bytes.fromhex(fixture["responseHex"])
        generals = [fixture["general"]]
        result = parse_a110_general_statuses(payload, generals)

        self.assertEqual(
            SERVER.parse_a110_general_statuses(payload, generals),
            result,
        )
        record = result["records"][0]
        for key, value in fixture["expected"].items():
            self.assertEqual(record[key], value)

        with patch.object(SERVER, "now_ms", return_value=123456789):
            desktop_intel = SERVER.parse_military_intel_from_a110(
                payload,
                generals,
            )
        shared_intel = parse_military_intel_from_a110(
            payload,
            generals,
            updated_at=123456789,
        )
        self.assertEqual(desktop_intel, shared_intel)

    def test_compact_inventory_8104_runs_in_shared_core(self) -> None:
        fixture = self.fixtures["inventory8104Compact"]
        payload = bytes.fromhex(fixture["responseHex"])
        item_names = {
            int(key): value for key, value in fixture["itemNames"].items()
        }
        equipment_templates = {
            int(key): value
            for key, value in fixture["equipmentTemplates"].items()
        }
        inventory = parse_8104_inventory(
            payload,
            item_names=item_names,
            equipment_templates=equipment_templates,
        )
        expected = fixture["expected"]

        self.assertEqual(inventory["capacity"], expected["capacity"])
        self.assertEqual(inventory["itemCount"], expected["itemCount"])
        self.assertEqual(
            [row["itemId"] for row in inventory["items"]],
            expected["itemIds"],
        )
        self.assertEqual(
            [row["count"] for row in inventory["items"]],
            expected["itemCounts"],
        )
        self.assertEqual(
            inventory["equipmentCount"],
            expected["equipmentCount"],
        )
        equipment = inventory["equipment"][0]
        self.assertEqual(equipment["name"], expected["equipmentName"])
        self.assertEqual(
            equipment["qualityName"],
            expected["equipmentQuality"],
        )
        self.assertEqual(
            equipment["strengthen"],
            expected["equipmentStrengthen"],
        )
        # Weapon templates use typeCode=0; zero is valid metadata and must
        # not be mistaken for a missing value by the fail-closed cleaner.
        self.assertTrue(equipment["equipmentMetadataComplete"])

    def test_packaged_item_catalog_and_unknown_ids_keep_fixed_alignment(self) -> None:
        self.assertEqual(len(DEFAULT_ITEM_NAMES), 758)
        self.assertEqual(DEFAULT_ITEM_NAMES[432], "凝魂晶石")
        self.assertEqual(DEFAULT_ITEM_NAMES[575], "疾风符")
        self.assertEqual(DEFAULT_ITEM_NAMES[709], "将印")

        rows = [(709, 2), (1000, 3)]
        payload = (
            b"\x00" * 14
            + (1256).to_bytes(2, "big")
            + len(rows).to_bytes(2, "big")
            + b"".join(
                item_id.to_bytes(2, "big")
                + count.to_bytes(2, "big")
                + b"\x00" * 8
                for item_id, count in rows
            )
            + b"\x00\x00"
        )

        inventory = parse_8104_inventory(payload)

        self.assertNotIn("parseError", inventory)
        self.assertEqual(
            inventory["layout"],
            "u16-id-u16-count-reserved8-table",
        )
        self.assertEqual(
            [row["itemId"] for row in inventory["items"]],
            [709, 1000],
        )
        self.assertEqual(
            [row["name"] for row in inventory["items"]],
            ["将印", "道具#1000"],
        )
        self.assertEqual(inventory["unknownItemIds"], [1000])
        self.assertTrue(all(
            row["layout"] == "u16-id-u16-count-reserved8"
            for row in inventory["items"]
        ))

    def test_manual_open_plan_and_reward_text_are_shared(self) -> None:
        inventory = {
            "items": [
                {"itemId": 58, "name": "青铜宝箱", "count": 3},
                {"itemId": 59, "name": "青铜钥匙", "count": 1},
            ],
        }

        plan = plan_open_one_inventory(inventory, " 青铜宝箱 ")

        self.assertIn("青铜宝箱", AUTO_OPEN_ITEM_NAMES)
        self.assertEqual(plan["itemId"], 58)
        self.assertEqual(plan["openCount"], 1)
        self.assertEqual(plan["requiredKey"], "青铜钥匙")
        self.assertEqual(
            inventory_reward_log_text("<br/>铜钱+1000;<b>粮食+2</b>;"),
            "铜钱+1000；粮食+2",
        )
        with self.assertRaisesRegex(ValueError, "缺少青铜钥匙"):
            plan_open_one_inventory(
                {"items": [{"itemId": 58, "name": "青铜宝箱", "count": 3}]},
                "青铜宝箱",
            )
        with self.assertRaisesRegex(ValueError, "不在自动开箱允许范围"):
            plan_open_one_inventory(inventory, "未授权道具")

    def test_live_inventory_capture_matches_desktop_adapter(self) -> None:
        fixture = self.fixtures["inventory8104LiveCapture"]
        packets = parse_response((ROOT / fixture["sourceFile"]).read_bytes())
        payload = next(
            packet["payload"]
            for packet in packets
            if packet.get("opcode") == 0x8104
        )
        shared = parse_8104_inventory(
            payload,
            item_names=SERVER.item_names_by_id(),
            equipment_templates=SERVER.equipment_templates_by_id(),
            quality_names=SERVER.EQUIPMENT_QUALITY_NAMES,
        )
        desktop = SERVER.parse_8104_inventory(payload)
        packaged = parse_8104_inventory(payload)

        self.assertEqual(desktop, shared)
        self.assertEqual(
            len(shared["items"]),
            fixture["expected"]["itemStackCount"],
        )
        self.assertEqual(
            len(shared["equipment"]),
            fixture["expected"]["equipmentCount"],
        )
        self.assertNotIn("parseError", packaged)
        self.assertEqual(
            [
                (row["itemId"], row["name"], row["count"])
                for row in packaged["items"]
            ],
            [
                (row["itemId"], row["name"], row["count"])
                for row in desktop["items"]
            ],
        )
        self.assertEqual(
            [
                (row["instanceId"], row["templateId"], row["name"])
                for row in packaged["equipment"]
            ],
            [
                (row["instanceId"], row["templateId"], row["name"])
                for row in desktop["equipment"]
            ],
        )


if __name__ == "__main__":
    unittest.main()
