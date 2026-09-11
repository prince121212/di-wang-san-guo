from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = ROOT / "shared_core" / "python"
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
FIXTURE_PATH = ROOT / "shared_core" / "protocol_parity_fixtures.json"
if str(CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CORE_SOURCE))

from dwpm_core.features.maintenance import (
    apply_full_loyalty_receipt,
    apply_general_energy_receipt,
    build_add_loyalty_payload,
    build_delete_all_mail_payload,
    build_discard_inventory_payload,
    build_resource_exchange_payload,
    build_use_general_item_payload,
    build_use_inventory_item_payload,
    equipment_is_safe_to_discard,
    parse_821f_loyalty_response,
    parse_delete_mail_response,
    parse_discard_inventory_response,
    parse_resource_exchange_response,
    parse_use_general_item_response,
    plan_general_energy_use,
    plan_generals_full_loyalty,
)
from dwpm_core.hashing import source_manifest


SPEC = importlib.util.spec_from_file_location(
    "dwpm_server_maintenance_shared_parity",
    SERVER_PATH,
)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class SharedMaintenanceProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.fixtures = payload["fixtures"]
        cls.fixture = cls.fixtures["maintenanceProtocols"]
        inventory = cls.fixtures["inventory8104Compact"]
        cls.item_names = {
            int(key): value for key, value in inventory["itemNames"].items()
        }
        cls.equipment_templates = {
            int(key): value
            for key, value in inventory["equipmentTemplates"].items()
        }

    def test_general_maintenance_payloads_and_loyalty_receipt_are_shared(self) -> None:
        fixture = self.fixture
        loyalty_payload = build_add_loyalty_payload(
            fixture["generalId"],
            fixture["loyaltyDelta"],
        )
        item_payload = build_use_general_item_payload(
            fixture["generalId"],
            fixture["generalItemId"],
            fixture["generalItemCount"],
        )
        self.assertEqual(loyalty_payload.hex(), fixture["addLoyaltyPayloadHex"])
        self.assertEqual(item_payload.hex(), fixture["generalItemPayloadHex"])
        self.assertEqual(
            SERVER.build_add_loyalty_payload(
                fixture["generalId"],
                fixture["loyaltyDelta"],
            ),
            loyalty_payload,
        )
        self.assertEqual(
            SERVER.build_use_general_item_payload(
                fixture["generalId"],
                fixture["generalItemId"],
                fixture["generalItemCount"],
            ),
            item_payload,
        )

        response = bytes.fromhex(fixture["addLoyaltyResponseHex"])
        parsed = parse_821f_loyalty_response(response)
        self.assertEqual(SERVER.parse_821f_loyalty_response(response), parsed)
        expected = fixture["expected"]
        self.assertTrue(parsed["success"])
        self.assertEqual(parsed["actualCost"], expected["loyaltyActualCost"])
        self.assertEqual(parsed["copper"], expected["loyaltyCopper"])
        self.assertEqual(parsed["generals"][0]["loyalty"], expected["loyalty"])
        self.assertEqual(
            parsed["generals"][0]["loyaltyLimit"],
            expected["loyaltyLimit"],
        )

    def test_energy_response_inventory_is_parsed_by_shared_core(self) -> None:
        parsed = parse_use_general_item_response(
            bytes.fromhex(self.fixture["generalItemResponseHex"]),
            item_names=self.item_names,
            equipment_templates=self.equipment_templates,
        )
        self.assertTrue(parsed["success"])
        self.assertEqual(parsed["message"], "活血丹使用成功")
        self.assertEqual(
            parsed["inventory"]["itemCount"],
            self.fixture["expected"]["energyInventoryItemCount"],
        )

    def test_energy_and_full_loyalty_business_plans_are_shared(self) -> None:
        energy = plan_general_energy_use(
            {
                "id": 101,
                "name": "统弓2",
                "tili": 5,
                "energyReliable": True,
            },
            {"items": [{"itemId": 12, "name": "活血丹", "count": 2}]},
            enabled=True,
            threshold=40,
            action_name="刷黄",
        )
        self.assertTrue(energy["actionRequired"])
        self.assertEqual(energy["payloadHex"], build_use_general_item_payload(101, 12, 1).hex())
        confirmed_energy = apply_general_energy_receipt(
            energy,
            {"success": True, "message": "活血丹使用成功"},
            action_name="刷黄",
        )
        self.assertEqual(confirmed_energy["after"], 55)
        self.assertIn("由5更新为55", confirmed_energy["message"])
        with self.assertRaisesRegex(ValueError, "宝库没有活血丹"):
            plan_general_energy_use(
                {
                    "id": 101,
                    "name": "统弓2",
                    "tili": 5,
                    "energyReliable": True,
                },
                {"items": []},
                enabled=True,
                threshold=40,
                action_name="刷黄",
            )

        plans = plan_generals_full_loyalty(
            [
                {"id": 1, "name": "满忠将", "loyalty": 100, "loyaltyLimit": 100},
                {"id": 2, "name": "低忠将", "loyalty": 59, "loyaltyLimit": 100},
            ],
            action_name="打矿",
        )
        self.assertTrue(plans[0]["skipped"])
        self.assertFalse(plans[1]["skipped"])
        self.assertEqual(plans[1]["delta"], 41)
        self.assertEqual(
            plans[1]["payloadHex"],
            build_add_loyalty_payload(2, 41).hex(),
        )
        loyalty_receipt = {
            "success": True,
            "actualCost": 5125,
            "copper": 94875,
            "generals": [
                {"generalId": 2, "loyalty": 100, "loyaltyLimit": 100},
            ],
        }
        confirmed_loyalty = apply_full_loyalty_receipt(
            plans[1],
            loyalty_receipt,
            action_name="打矿",
        )
        self.assertEqual(confirmed_loyalty["loyalty"], 100)
        self.assertEqual(confirmed_loyalty["copper"], 94875)
        with self.assertRaisesRegex(ValueError, "响应未包含该将领"):
            apply_full_loyalty_receipt(
                plans[1],
                {"success": True, "generals": []},
                action_name="打矿",
            )

    def test_resource_mail_and_discard_protocols_are_shared(self) -> None:
        fixture = self.fixture
        resource_payload = build_resource_exchange_payload(
            fixture["resourceDirection"],
            fixture["resourceAmount"],
        )
        self.assertEqual(resource_payload.hex(), fixture["resourcePayloadHex"])
        self.assertEqual(
            SERVER.build_resource_exchange_payload(
                fixture["resourceDirection"],
                fixture["resourceAmount"],
            ),
            resource_payload,
        )
        resource_response = bytes.fromhex(fixture["resourceResponseHex"])
        resource = parse_resource_exchange_response(resource_response)
        self.assertEqual(
            SERVER.parse_resource_exchange_response(resource_response),
            resource,
        )
        self.assertEqual(
            resource["copper"],
            fixture["expected"]["resourceCopper"],
        )
        self.assertEqual(resource["food"], fixture["expected"]["resourceFood"])

        mail_payload = build_delete_all_mail_payload()
        self.assertEqual(mail_payload.hex(), fixture["deleteMailPayloadHex"])
        self.assertEqual(SERVER.build_delete_all_mail_payload(), mail_payload)
        mail_response = bytes.fromhex(fixture["deleteMailResponseHex"])
        mail = parse_delete_mail_response(mail_response)
        self.assertEqual(SERVER.parse_delete_mail_response(mail_response), mail)
        self.assertEqual(mail["remaining"], fixture["expected"]["mailRemaining"])

        discard_payload = build_discard_inventory_payload(
            fixture["discardKind"],
            fixture["discardObjectId"],
            fixture["discardCount"],
        )
        self.assertEqual(discard_payload.hex(), fixture["discardPayloadHex"])
        self.assertEqual(
            SERVER.build_discard_inventory_payload(
                fixture["discardKind"],
                fixture["discardObjectId"],
                fixture["discardCount"],
            ),
            discard_payload,
        )
        discard_response = bytes.fromhex(fixture["discardResponseHex"])
        discard = parse_discard_inventory_response(
            discard_response,
            item_names=self.item_names,
            equipment_templates=self.equipment_templates,
        )
        desktop_parameterized = parse_discard_inventory_response(
            discard_response,
            item_names=SERVER.item_names_by_id(),
            equipment_templates=SERVER.equipment_templates_by_id(),
            quality_names=SERVER.EQUIPMENT_QUALITY_NAMES,
        )
        self.assertEqual(
            SERVER.parse_discard_inventory_response(discard_response),
            desktop_parameterized,
        )
        self.assertEqual(
            discard["message"],
            fixture["expected"]["discardMessage"],
        )
        self.assertEqual(
            discard["inventory"]["itemCount"],
            fixture["expected"]["discardInventoryItemCount"],
        )

    def test_inventory_item_use_payload_is_shared(self) -> None:
        payload = build_use_inventory_item_payload(
            self.fixture["inventoryItemId"],
            self.fixture["inventoryItemCount"],
        )
        self.assertEqual(payload.hex(), self.fixture["inventoryItemPayloadHex"])
        with self.assertRaises(RuntimeError):
            build_use_inventory_item_payload(70000, 1)

    def test_equipment_discard_guard_is_shared(self) -> None:
        safe = {
            "instanceId": 1,
            "equipmentMetadataComplete": True,
            "famous": False,
            "strengthen": 0,
            "extraText": "",
            "level": 10,
            "quality": 1,
        }
        strengthened = {**safe, "strengthen": 1}
        self.assertEqual(
            SERVER.equipment_is_safe_to_discard(
                safe,
                max_quality=1,
                max_level=60,
            ),
            equipment_is_safe_to_discard(
                safe,
                max_quality=1,
                max_level=60,
            ),
        )
        self.assertEqual(
            equipment_is_safe_to_discard(
                strengthened,
                max_quality=1,
                max_level=60,
            ),
            (False, "已经强化"),
        )

    def test_maintenance_source_is_in_cross_platform_hash(self) -> None:
        manifest = source_manifest(ROOT / "shared_core")
        self.assertIn(
            "python/dwpm_core/features/maintenance.py",
            manifest["files"],
        )


if __name__ == "__main__":
    unittest.main()
