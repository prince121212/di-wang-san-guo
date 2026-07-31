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

from dwpm_core.features.expedition import (
    build_brush_payloads,
    build_dungeon_expedition_payload,
    build_dungeon_prepare_payload,
    build_lossless_expedition_payload,
    build_lossless_prepare_payload,
    build_mine_payloads,
    build_raid_expedition_payload,
    build_raid_prepare_payload,
)
from dwpm_core.hashing import source_manifest
from dwpm_core import CoreFacade


SPEC = importlib.util.spec_from_file_location("dwpm_server_expedition_parity", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class SharedExpeditionProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.fixtures = payload["fixtures"]

    def test_brush_payloads_run_directly_in_shared_core(self) -> None:
        fixture = self.fixtures["brushYellowActionType3"]
        expected = fixture["expected"]
        shared = build_brush_payloads(
            fixture["generalIdHexChunks"],
            fixture["targetIdHex"],
        )

        self.assertEqual(SERVER.build_brush_payloads(
            fixture["generalIdHexChunks"], fixture["targetIdHex"]
        ), shared)
        self.assertEqual(shared[0], expected["prepareGameHex"])
        self.assertEqual(shared[1], expected["dispatchGameHex"])

    def test_mine_payloads_run_directly_in_shared_core(self) -> None:
        fixture = self.fixtures["mineActionType2"]
        ids = [f"{value:016x}" for value in fixture["generalIds"]]
        shared = build_mine_payloads(ids, fixture["targetId"])

        self.assertEqual(SERVER.build_mine_payloads(ids, fixture["targetId"]), shared)
        self.assertEqual(shared[0].hex(), fixture["expected"]["preparePayloadHex"])
        self.assertEqual(shared[1].hex(), fixture["expected"]["dispatchPayloadHex"])

    def test_raid_payloads_run_directly_in_shared_core(self) -> None:
        fixture = self.fixtures["raidActionType1"]
        ids = [f"{value:016x}" for value in fixture["generalIds"]]
        prepare = build_raid_prepare_payload(ids, fixture["targetId"])
        dispatch = build_raid_expedition_payload(ids, fixture["targetId"])

        self.assertEqual(SERVER.build_raid_prepare_payload(ids, fixture["targetId"]), prepare)
        self.assertEqual(SERVER.build_raid_expedition_payload(ids, fixture["targetId"]), dispatch)
        self.assertEqual(prepare.hex(), fixture["expected"]["preparePayloadHex"])
        self.assertEqual(dispatch.hex(), fixture["expected"]["dispatchPayloadHex"])

    def test_lossless_payloads_run_directly_in_shared_core(self) -> None:
        fixture = self.fixtures["losslessActionType11"]
        ids = [f"{value:016x}" for value in fixture["generalIds"]]
        prepare = build_lossless_prepare_payload(ids, fixture["roleId"])
        dispatch = build_lossless_expedition_payload(ids, fixture["roleId"])

        self.assertEqual(SERVER.build_lossless_prepare_payload(ids, fixture["roleId"]), prepare)
        self.assertEqual(SERVER.build_lossless_expedition_payload(ids, fixture["roleId"]), dispatch)
        self.assertEqual(prepare.hex(), fixture["expected"]["preparePayloadHex"])
        self.assertEqual(dispatch.hex(), fixture["expected"]["dispatchPayloadHex"])

    def test_dungeon_payloads_run_directly_in_shared_core(self) -> None:
        fixture = self.fixtures["dungeonActionType14"]
        ids = [f"{value:016x}" for value in fixture["generalIds"]]
        prepare = build_dungeon_prepare_payload(ids, fixture["stageCode"])
        dispatch = build_dungeon_expedition_payload(ids, fixture["stageCode"])

        self.assertEqual(SERVER.build_dungeon_prepare_payload(ids, fixture["stageCode"]), prepare)
        self.assertEqual(SERVER.build_dungeon_expedition_payload(ids, fixture["stageCode"]), dispatch)
        self.assertEqual(prepare.hex(), fixture["expected"]["preparePayloadHex"])
        self.assertEqual(dispatch.hex(), fixture["expected"]["dispatchPayloadHex"])

    def test_shared_source_is_in_the_cross_platform_hash(self) -> None:
        manifest = source_manifest(ROOT / "shared_core")
        self.assertIn("python/dwpm_core/features/expedition.py", manifest["files"])

    def test_facade_runs_the_same_offline_fixture_suite_used_by_android(self) -> None:
        report = CoreFacade(ROOT / "shared_core").protocol_fixture_report()

        self.assertTrue(report["ok"])
        self.assertEqual(report["checkCount"], 33)
        self.assertEqual(report["passedCount"], 33)
        self.assertEqual(report["failureCount"], 0)


if __name__ == "__main__":
    unittest.main()
