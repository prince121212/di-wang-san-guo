from __future__ import annotations

import importlib.util
import json
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = ROOT / "shared_core" / "python"
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
if str(CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CORE_SOURCE))

from dwpm_core import (
    CORE_ID,
    CORE_VERSION,
    CoreFacade,
    compute_core_hash,
    create_hosted_core,
)
from dwpm_core.hashing import hash_records, source_manifest
from dwpm_core.local_views import (
    project_success_records,
    resident_success_record,
    resident_success_records_from_operation_facts,
)
from dwpm_core.operations import OperationUncertainError
from dwpm_core.ports import PlatformPorts
from shared_raw_http_test_host import (
    FIXTURE_GAME_HTTP,
    RawHttpGameCommandHostMixin,
)


SPEC = importlib.util.spec_from_file_location("dwpm_server_shared_core_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class FixedClock:
    def __init__(self, now_millis: int) -> None:
        self.value = now_millis

    def now_millis(self) -> int:
        return self.value


class SharedPythonCoreTests(unittest.TestCase):
    def test_account_settings_projection_is_shared_deterministic_and_local(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        response = facade.dispatch(
            "GET",
            "/api/accounts/settings",
            {
                "account": {"sessionId": "202", "username": "fixture"},
                "configDir": "local://settings",
                "fileName": "account-config.json",
                "filePath": "local://settings/account-config.json",
                "exists": True,
                "settings": {"z": 1, "a": {"enabled": True}},
            },
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body["configDir"], "local://settings")
        self.assertEqual(len(response.body["files"]), 1)
        self.assertEqual(
            json.loads(response.body["files"][0]["content"]),
            {"a": {"enabled": True}, "z": 1},
        )
        self.assertLess(
            response.body["files"][0]["content"].index('"a"'),
            response.body["files"][0]["content"].index('"z"'),
        )
        self.assertEqual(facade.operations_snapshot()["count"], 0)
        facade.close()

    def test_account_settings_projection_rejects_sensitive_values(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        response = facade.dispatch(
            "GET",
            "/api/accounts/settings",
            {
                "account": {"sessionId": "202"},
                "settings": {"password": "must-not-leak"},
            },
        )

        self.assertEqual(response.status, 400)
        self.assertNotIn("must-not-leak", json.dumps(response.body))
        facade.close()

    def test_future_military_settings_write_plan_is_local_and_shared(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        plan = facade.settings_write_plan(
            "/api/military/future/save",
            {
                "feature": "escort",
                "settings": {
                    "enabled": True,
                    "rows": [
                        {
                            "enabled": True,
                            "generalIds": [7, "7", "", 8],
                        }
                    ],
                },
            },
        )

        self.assertFalse(plan["networkRequired"])
        self.assertTrue(plan["disabled"])
        self.assertEqual(
            plan["configs"]["military_future_escort"]["rows"][0]["generalIds"],
            ["7", "8"],
        )
        self.assertEqual(
            plan["response"]["readiness"]["status"],
            "capture_needed",
        )
        facade.close()

    def test_future_military_settings_plan_rejects_unknown_feature(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        result = facade.dispatch(
            "POST",
            "/api/military/future/save",
            {"feature": "unknown", "settings": {}},
        )

        self.assertEqual(result.status, 400)
        self.assertFalse(result.body["ok"])
        self.assertEqual(result.body["code"], "LOCAL_VALIDATION_FAILED")
        self.assertIn("未知军事功能", result.body["error"])
        facade.close()

    def test_ministry_settings_write_plan_separates_save_from_activation(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        unverified = facade.dispatch(
            "POST",
            "/api/liubu/save",
            {
                "settings": {
                    "cropEnabled": True,
                    "crop": "草药",
                    "stealEnabled": True,
                }
            },
        )
        verified = facade.dispatch(
            "POST",
            "/api/liubu/save",
            {
                "settings": {
                    "cropEnabled": True,
                    "crop": "金银花",
                    "stealEnabled": False,
                    "courtesyEnabled": False,
                    "salaryRefresh": False,
                }
            },
        )

        self.assertEqual(unverified.status, 200)
        unverified_plan = unverified.body["plan"]
        self.assertFalse(unverified_plan["networkRequired"])
        self.assertFalse(unverified_plan["activationAllowed"])
        self.assertTrue(unverified_plan["response"]["requested"])
        self.assertIn("配置已保存但不会发送", unverified_plan["response"]["reason"])

        verified_plan = verified.body["plan"]
        self.assertTrue(verified_plan["activationAllowed"])
        self.assertTrue(
            verified_plan["configs"]["six_ministries"]["supportedEnabled"]
        )
        missing = facade.dispatch(
            "POST",
            "/api/liubu/save",
            {"sessionId": "202"},
        )
        self.assertEqual(missing.status, 400)
        self.assertIn("缺少 settings", missing.body["error"])
        facade.close()

    def test_formation_settings_plan_preserves_unknown_ids_and_splits_execution(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        response = facade.dispatch(
            "POST",
            "/api/formations/save",
            {
                "formations": [
                    {
                        "enabled": True,
                        "generalIds": ["7", "8"],
                        "soldierType": "近卫兵",
                        "soldierCount": 1800,
                        "generalNameSnapshots": {"8": "旧名"},
                    },
                    {
                        "enabled": False,
                        "generalIds": [],
                        "soldierType": "民兵",
                        "soldierCount": 0,
                    },
                ],
                "formationOptions": {"clearOtherGenerals": False},
                "knownGenerals": [{"id": 7, "idHex": "07", "name": "关羽"}],
            },
        )

        self.assertEqual(response.status, 200)
        plan = response.body["plan"]
        self.assertFalse(plan["networkRequired"])
        self.assertFalse(plan["activationAllowed"])
        self.assertEqual(plan["response"]["unresolvedGeneralIds"], ["8"])
        self.assertEqual(
            plan["response"]["formations"][0]["generalNameSnapshots"],
            {"7": "关羽", "8": "旧名"},
        )
        self.assertEqual(len(plan["response"]["normalizedFormations"]), 2)
        self.assertEqual(facade.operations_snapshot()["count"], 0)
        facade.close()

    def test_formation_settings_plan_rejects_duplicates_and_invalid_enabled_rows(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        duplicate = facade.dispatch(
            "POST",
            "/api/formations/save",
            {
                "formations": [
                    {"enabled": True, "generalIds": ["7"], "soldierType": "近卫兵", "soldierCount": 1},
                    {"enabled": True, "generalIds": ["7"], "soldierType": "近卫兵", "soldierCount": 1},
                ]
            },
        )
        invalid = facade.dispatch(
            "POST",
            "/api/formations/save",
            {
                "formations": [
                    {"enabled": True, "generalIds": [], "soldierType": "未知兵种", "soldierCount": 0}
                ]
            },
        )

        self.assertEqual(duplicate.status, 400)
        self.assertIn("重复配置", duplicate.body["error"])
        self.assertEqual(invalid.status, 400)
        self.assertIn("未选择将领", invalid.body["error"])
        facade.close()

    def test_mine_settings_plan_is_local_normalized_and_shared(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        response = facade.dispatch(
            "POST",
            "/api/mine/save",
            {
                "settings": {
                    "speed": "中级行军符",
                    "fullLoyalty": True,
                    "replenishTroops": False,
                    "maxMarchMinutes": 75,
                    "centerX": 999,
                    "centerY": -4,
                    "targetPlayerName": "旧版玩家字段不得生效",
                    "rows": [
                        {
                            "enabled": True,
                            "generalIds": [7, "7", ""],
                            "resourceType": "镔铁矿",
                            "scope": "未知范围",
                            "x": 999,
                            "y": -1,
                        },
                        {
                            "enabled": False,
                            "generalIds": [],
                            "resourceType": "镔铁矿",
                            "scope": "附近",
                        },
                    ],
                },
                "knownGenerals": [{"id": 7, "idHex": "07", "name": "关羽"}],
            },
        )

        self.assertEqual(response.status, 200)
        plan = response.body["plan"]
        self.assertFalse(plan["networkRequired"])
        self.assertTrue(plan["activationAllowed"])
        self.assertFalse(plan["disabled"])
        saved = plan["configs"]["auto_mining"]
        self.assertTrue(saved["enabled"])
        self.assertTrue(saved["speed"])
        self.assertFalse(saved["replenishTroops"])
        self.assertEqual(saved["maxMarchMinutes"], 45)
        self.assertEqual((saved["centerX"], saved["centerY"]), (186, 0))
        self.assertEqual(saved["targetPlayerName"], "")
        self.assertEqual(len(saved["rows"]), 2)
        execution = plan["response"]["executionRows"]
        self.assertEqual(execution[0]["generalIds"], ["7"])
        self.assertEqual(execution[0]["scope"], "附近")
        self.assertEqual((execution[0]["x"], execution[0]["y"]), (186, 0))
        self.assertEqual(facade.operations_snapshot()["count"], 0)
        desktop = SERVER.normalize_mine_settings(
            {"generals": [{"id": 7, "idHex": "07"}]},
            plan["response"]["settings"],
        )
        self.assertEqual(desktop["rows"], execution)
        facade.close()

    def test_mine_settings_plan_rejects_missing_settings_and_foreign_general(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        missing = facade.dispatch("POST", "/api/mine/save", {"sessionId": "202"})
        foreign = facade.dispatch(
            "POST",
            "/api/mine/save",
            {
                "settings": {
                    "rows": [
                        {
                            "enabled": True,
                            "generalIds": [8],
                            "resourceType": "镔铁矿",
                        }
                    ]
                },
                "knownGenerals": [{"id": 7}],
            },
        )

        self.assertEqual(missing.status, 400)
        self.assertIn("缺少 settings", missing.body["error"])
        self.assertEqual(foreign.status, 400)
        self.assertIn("不属于当前账号", foreign.body["error"])
        facade.close()

    def test_raid_settings_plan_is_the_single_local_normalizer_for_both_hosts(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        body = {
            "confirm": "raid",
            "rows": [
                {
                    "enabled": True,
                    "generalIds": [7, "7", ""],
                    "playerName": "  目标甲  ",
                    "fiefIndex": "2",
                    "fullTroops": False,
                    "fullLoyalty": True,
                },
                {
                    "enabled": False,
                    "generalIds": [],
                    "playerName": "",
                    "fiefIndex": 0,
                },
            ],
            "knownGenerals": [{"id": 7, "idHex": "07"}],
        }
        response = facade.dispatch("POST", "/api/raid/execute", body)

        self.assertEqual(response.status, 200)
        plan = response.body["plan"]
        self.assertFalse(plan["networkRequired"])
        self.assertTrue(plan["activationAllowed"])
        self.assertEqual(plan["followUpOperation"]["kind"], "raid")
        saved = plan["configs"]["auto_loot"]
        self.assertTrue(saved["auto_loot_enabled"])
        self.assertFalse(saved["fullTroops"])
        self.assertTrue(saved["fullLoyalty"])
        self.assertEqual(len(saved["rows"]), 2)
        execution = plan["response"]["executionRows"]
        self.assertEqual(execution[0]["generalIds"], ["7"])
        self.assertEqual(execution[0]["playerName"], "目标甲")
        self.assertEqual(execution[0]["fiefIndex"], 2)
        self.assertEqual(
            SERVER.normalize_raid_rows(
                {"generals": [{"id": 7, "idHex": "07"}]},
                body,
            ),
            execution,
        )
        self.assertEqual(facade.operations_snapshot()["count"], 0)
        facade.close()

    def test_raid_settings_plan_rejects_missing_confirmation_and_foreign_general(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        missing_confirmation = facade.dispatch(
            "POST",
            "/api/raid/execute",
            {
                "rows": [{
                    "enabled": True,
                    "generalIds": [7],
                    "playerName": "目标甲",
                    "fiefIndex": 1,
                }]
            },
        )
        foreign = facade.dispatch(
            "POST",
            "/api/raid/execute",
            {
                "confirm": "raid",
                "rows": [{
                    "enabled": True,
                    "generalIds": [8],
                    "playerName": "目标甲",
                    "fiefIndex": 1,
                }],
                "knownGenerals": [{"id": 7}],
            },
        )

        self.assertEqual(missing_confirmation.status, 400)
        self.assertIn("confirm=raid", missing_confirmation.body["error"])
        self.assertEqual(foreign.status, 400)
        self.assertIn("不属于当前账号", foreign.body["error"])
        facade.close()

    def test_lossless_settings_plan_preserves_ui_rows_and_splits_execution_rows(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        response = facade.dispatch(
            "POST",
            "/api/lossless/execute",
            {
                "confirm": "lossless",
                "settings": {
                    "fullTroops": True,
                    "dailyLimit": 99,
                    "rows": [
                        {
                            "enabled": True,
                            "generalIds": [7, "7"],
                            "level": "9级",
                            "maxLineupRerolls": 999,
                        },
                        {
                            "enabled": False,
                            "generalIds": [],
                            "level": "旧占位值",
                        },
                    ],
                },
                "knownGenerals": [{"id": 7, "idHex": "07"}],
            },
        )

        self.assertEqual(response.status, 200)
        plan = response.body["plan"]
        self.assertFalse(plan["networkRequired"])
        self.assertFalse(plan["disabled"])
        saved = plan["configs"]["military_lossless"]
        self.assertTrue(saved["enabled"])
        self.assertEqual(saved["dailyLimit"], 5)
        self.assertEqual(len(saved["rows"]), 2)
        self.assertEqual(saved["rows"][1]["level"], "10级")
        execution = plan["response"]["executionRows"]
        self.assertEqual(execution[0]["generalIds"], ["7"])
        self.assertEqual(execution[0]["level"], 9)
        self.assertEqual(execution[0]["maxLineupRerolls"], 300)
        self.assertTrue(execution[0]["fullTroops"])
        self.assertEqual(
            SERVER.normalize_lossless_rows(
                {"generals": [{"id": 7, "idHex": "07"}]},
                saved,
            ),
            execution,
        )
        self.assertEqual(facade.operations_snapshot()["count"], 0)
        facade.close()

    def test_lossless_settings_plan_can_disable_without_network_or_enabled_rows(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        response = facade.dispatch(
            "POST",
            "/api/lossless/execute",
            {
                "confirm": "lossless",
                "settings": {
                    "rows": [{
                        "enabled": False,
                        "generalIds": [],
                        "level": "10级",
                    }]
                },
            },
        )

        self.assertEqual(response.status, 200)
        self.assertTrue(response.body["plan"]["disabled"])
        self.assertFalse(response.body["plan"]["activationAllowed"])
        self.assertEqual(response.body["plan"]["response"]["executionRows"], [])
        facade.close()

    def test_dungeon_settings_plan_normalizes_loop_and_clear_modes_once(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        loop = facade.dispatch(
            "POST",
            "/api/dungeon/execute",
            {
                "confirm": "dungeon",
                "mode": "loop",
                "rows": [
                    {
                        "enabled": True,
                        "generalIds": [7, "7"],
                        "chapter": "第四章",
                        "stage": "5",
                        "chest": "右",
                    },
                    {
                        "enabled": False,
                        "generalIds": [],
                        "chapter": "",
                        "stage": "",
                    },
                ],
                "knownGenerals": [{"id": 7, "idHex": "07"}],
            },
        )
        clear = facade.dispatch(
            "POST",
            "/api/dungeon/execute",
            {
                "confirm": "dungeon",
                "mode": "clear",
                "rows": [{
                    "enabled": True,
                    "generalIds": [7],
                    "chapter": "已删除章节",
                    "stage": "999",
                    "chest": "中",
                }],
                "knownGenerals": [{"id": 7}],
            },
        )

        self.assertEqual(loop.status, 200)
        loop_plan = loop.body["plan"]
        self.assertFalse(loop_plan["networkRequired"])
        self.assertTrue(loop_plan["acknowledgeDefeatOnSave"])
        self.assertEqual(len(loop_plan["response"]["rows"]), 2)
        loop_execution = loop_plan["response"]["executionRows"]
        self.assertEqual(loop_execution[0]["generalIds"], ["7"])
        self.assertEqual(loop_execution[0]["chapter"], 3)
        self.assertEqual(loop_execution[0]["stage"], 5)
        self.assertEqual(loop_execution[0]["chest"], 2)
        loop_config = loop_plan["configs"]["dungeon"]
        self.assertEqual(loop_config["selectedGeneralIds"], ["7"])
        self.assertEqual(loop_config["boxPosition"], 2)
        self.assertEqual(
            SERVER.normalize_dungeon_rows(
                {"generals": [{"id": 7, "idHex": "07"}]},
                {"rows": loop_plan["response"]["rows"]},
                mode="loop",
            ),
            loop_execution,
        )

        self.assertEqual(clear.status, 200)
        clear_execution = clear.body["plan"]["response"]["executionRows"]
        self.assertEqual(clear.body["plan"]["response"]["mode"], "clear")
        self.assertEqual(clear_execution[0]["chapter"], 0)
        self.assertEqual(clear_execution[0]["stage"], 1)
        self.assertEqual(clear_execution[0]["chest"], 1)
        facade.close()

    def test_dungeon_settings_plan_rejects_multiple_enabled_rows(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        response = facade.dispatch(
            "POST",
            "/api/dungeon/execute",
            {
                "confirm": "dungeon",
                "rows": [
                    {"enabled": True, "generalIds": [7], "chapter": "第一章", "stage": 1},
                    {"enabled": True, "generalIds": [8], "chapter": "第一章", "stage": 2},
                ],
            },
        )

        self.assertEqual(response.status, 400)
        self.assertIn("同一时间只能启用一条", response.body["error"])
        facade.close()

    def test_scoped_common_settings_preserve_other_pages_and_split_follow_up_work(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        response = facade.dispatch(
            "POST",
            "/api/settings/save",
            {
                "sessionId": "202",
                "scope": "common.daily",
                "patch": {
                    "healWounded": False,
                    "dailyTasks": {
                        "autoSignIn": True,
                        "salary": True,
                        "generalVisit": True,
                        "notARealTask": True,
                    },
                    "generalVisitGeneralIds": [],
                },
                "oldConfig": {
                    "autoStart": False,
                    "healWounded": True,
                    "brush": {"legacyMarker": "keep"},
                    "dailyTasks": {"autoSignIn": False, "salary": False},
                },
                "session": {
                    "sessionId": "202",
                    "role": {"level": 85, "officeName": "太守"},
                },
            },
        )

        self.assertEqual(response.status, 200)
        plan = response.body["plan"]
        self.assertFalse(plan["networkRequired"])
        config = plan["response"]["config"]
        self.assertTrue(config["healWounded"])
        self.assertEqual(config["brush"], {"legacyMarker": "keep"})
        self.assertTrue(config["dailyTasks"]["autoSignIn"])
        self.assertTrue(config["dailyTasks"]["salary"])
        self.assertFalse(config["dailyTasks"]["generalVisit"])
        self.assertNotIn("notARealTask", config["dailyTasks"])
        self.assertEqual(len(plan["response"]["settingsWarnings"]), 1)
        self.assertEqual(
            plan["configs"]["daily_basic"]["generalVisitGeneralIds"],
            [],
        )
        follow_up = plan["followUpOperations"][0]
        self.assertEqual(follow_up["kind"], "run-new-daily")
        self.assertEqual(follow_up["keys"], ["autoSignIn", "salary"])
        facade.close()

    def test_scoped_frequent_and_deferred_chain_settings_use_shared_normalization(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        frequent = facade.dispatch(
            "POST",
            "/api/settings/save",
            {
                "sessionId": "202",
                "scope": "common.frequent",
                "patch": {
                    "dailyLimit": 900,
                    "energyThreshold": 9,
                    "copperFloorWan": 3,
                    "domestic": {
                        "enabled": True,
                        "upgradeTechnology": True,
                        "technologyIds": [5, 999],
                    },
                },
                "oldConfig": {"autoStart": False},
                "session": {"role": {"level": 85}},
            },
        )
        chain = facade.dispatch(
            "POST",
            "/api/settings/save",
            {
                "sessionId": "202",
                "scope": "common.chain",
                "patch": {
                    "chainInventory": {
                        "enabled": True,
                        "keepItemName": "  青铜钥匙  ",
                        "keepCount": 20000,
                        "autoOpenEnabled": True,
                        "autoOpenItemNames": "50两银票",
                        "notAllowed": "drop",
                    }
                },
                "oldConfig": {"autoStart": False},
                "session": {"role": {"level": 85}},
            },
        )

        self.assertEqual(frequent.status, 200)
        frequent_plan = frequent.body["plan"]
        self.assertEqual(frequent_plan["configs"]["general"]["dailyLimit"], 500)
        self.assertEqual(frequent_plan["configs"]["general"]["minEnergy"], 20)
        self.assertEqual(frequent_plan["configs"]["general"]["copperFloorWan"], 1)
        self.assertEqual(
            frequent_plan["configs"]["internal_affairs"]["technologyIds"],
            [5],
        )
        self.assertEqual(
            {item["kind"] for item in frequent_plan["followUpOperations"]},
            {"auto-domestic", "auto-technology"},
        )
        chain_plan = chain.body["plan"]
        self.assertTrue(chain_plan["disabled"])
        self.assertFalse(chain_plan["activationAllowed"])
        self.assertEqual(
            chain_plan["configs"]["chain_inventory"],
            {
                "enabled": True,
                "keepItemName": "青铜钥匙",
                "keepCount": 9999,
                "autoOpenEnabled": True,
                "autoOpenItemNames": "50两银票",
            },
        )
        facade.close()

    def test_scoped_brush_settings_require_level_and_saved_formations(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        body = {
            "sessionId": "202",
            "scope": "brush",
            "patch": {
                "autoStart": True,
                "startHour": 18,
                "brush": {
                    "startX": 86,
                    "startY": 36,
                    "rows": [
                        {
                            "enabled": True,
                            "generalIds": [7, "7"],
                            "levels": [10],
                            "drops": ["资源"],
                            "compositionCode": "5203",
                        }
                    ],
                },
            },
            "oldConfig": {"autoStart": False},
            "knownGenerals": [{"id": 7}],
            "savedFormations": [
                {
                    "enabled": True,
                    "generalId": "7",
                    "soldierType": "近卫兵",
                    "soldierCount": 1800,
                }
            ],
            "session": {"role": {"level": 85}},
            "roleLevel": 85,
        }
        valid = facade.dispatch("POST", "/api/settings/save", body)
        low_level = facade.dispatch(
            "POST",
            "/api/settings/save",
            {**body, "roleLevel": 29},
        )
        no_formation = facade.dispatch(
            "POST",
            "/api/settings/save",
            {**body, "savedFormations": []},
        )

        self.assertEqual(valid.status, 200)
        plan = valid.body["plan"]
        self.assertTrue(plan["activationAllowed"])
        self.assertEqual(
            plan["configs"]["shua_huang"]["selectedFormationIds"],
            ["7"],
        )
        self.assertEqual(plan["configs"]["shua_huang"]["compositionCode"], "5203")
        self.assertEqual(low_level.status, 400)
        self.assertIn("30级", low_level.body["error"])
        self.assertEqual(no_formation.status, 400)
        self.assertIn("保存配兵规则", no_formation.body["error"])
        facade.close()

    def test_high_level_brush_save_requires_1000_troops_for_every_general(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        body = {
            "sessionId": "202",
            "scope": "brush",
            "patch": {
                "autoStart": True,
                "brush": {
                    "rows": [
                        {"enabled": False, "generalIds": [], "levels": [8]},
                        {"enabled": False, "generalIds": [], "levels": [8]},
                        {
                            "idx": 2,
                            "enabled": True,
                            "generalIds": [7, 8],
                            "levels": [9, 10],
                            "drops": ["资源"],
                            "compositionCode": "0500",
                        },
                    ],
                },
            },
            "oldConfig": {"autoStart": False},
            "knownGenerals": [
                {"id": 7, "name": "赵云"},
                {"id": 8, "name": "关羽"},
            ],
            "savedFormations": [
                {
                    "enabled": True,
                    "generalId": "7",
                    "soldierType": "近卫兵",
                    "soldierCount": 1000,
                },
                {
                    "enabled": True,
                    "generalId": "8",
                    "soldierType": "近卫兵",
                    "soldierCount": 999,
                },
            ],
            "session": {"role": {"level": 85}},
            "roleLevel": 85,
        }

        rejected = facade.dispatch("POST", "/api/settings/save", body)
        boundary = json.loads(json.dumps(body))
        boundary["savedFormations"][1]["soldierCount"] = 1000
        accepted = facade.dispatch("POST", "/api/settings/save", boundary)
        low_level = json.loads(json.dumps(body))
        low_level["patch"]["brush"]["rows"][2]["levels"] = [8]
        low_level_accepted = facade.dispatch(
            "POST", "/api/settings/save", low_level
        )

        self.assertEqual(rejected.status, 400)
        self.assertIn(
            "刷黄编队3未满足每个将领配兵达到1000",
            rejected.body["error"],
        )
        self.assertIn("关羽=999", rejected.body["error"])
        self.assertEqual(accepted.status, 200)
        self.assertEqual(
            accepted.body["plan"]["response"]["config"]["brush"]["rules"][0][
                "sourceRowIndex"
            ],
            2,
        )
        self.assertEqual(low_level_accepted.status, 200)
        facade.close()

    def test_desktop_shared_settings_validation_keeps_client_error_class(self) -> None:
        with self.assertRaises(SERVER.SharedSettingsValidationError) as rejected:
            SERVER.shared_settings_write_plan(
                "/api/settings/save",
                {
                    "sessionId": "202",
                    "scope": "brush",
                    "patch": {
                        "autoStart": True,
                        "brush": {
                            "rows": [{
                                "idx": 2,
                                "enabled": True,
                                "generalIds": [7],
                                "levels": [9],
                            }],
                        },
                    },
                    "oldConfig": {"autoStart": False},
                    "knownGenerals": [{"id": 7, "name": "赵云"}],
                    "savedFormations": [{
                        "enabled": True,
                        "generalId": "7",
                        "soldierType": "近卫兵",
                        "soldierCount": 999,
                    }],
                    "session": {"role": {"level": 85}},
                    "roleLevel": 85,
                },
            )

        self.assertIn(
            "刷黄编队3未满足每个将领配兵达到1000",
            str(rejected.exception),
        )

    def test_desktop_settings_http_returns_400_for_shared_validation(self) -> None:
        message = "刷黄编队3未满足每个将领配兵达到1000：赵云=999"
        session = {
            "sessionId": "validation-http",
            "role": {"level": 85},
            "roleState": {},
            "generals": [{"id": 7, "name": "赵云"}],
        }
        with (
            patch.object(SERVER, "get_session", return_value=session),
            patch.object(
                SERVER,
                "load_account_habits",
                return_value={"config": {}},
            ),
            patch.object(SERVER, "heal_saved_formation_rules", return_value=[]),
            patch.object(SERVER, "session_role_level", return_value=85),
            patch.object(
                SERVER,
                "shared_settings_write_plan",
                side_effect=SERVER.SharedSettingsValidationError(message),
            ),
        ):
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), SERVER.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            request = urllib.request.Request(
                f"http://127.0.0.1:{httpd.server_port}/api/settings/save",
                data=json.dumps({
                    "sessionId": "validation-http",
                    "scope": "brush",
                    "patch": {"autoStart": True, "brush": {"rows": []}},
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    urllib.request.urlopen(request, timeout=5)
                response_body = json.loads(
                    rejected.exception.read().decode("utf-8")
                )
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)

        self.assertEqual(rejected.exception.code, 400)
        self.assertEqual(response_body, {"ok": False, "error": message})

    def test_hosted_military_refresh_is_accepted_then_completed_by_shared_operation(self) -> None:
        class HostBridge:
            def __init__(self) -> None:
                self.calls = []

            def executeNetworkOperation(self, method, path, body_json, context_json):
                self.calls.append((method, path, json.loads(body_json)))
                return json.dumps(
                    {
                        "status": 200,
                        "body": {
                            "ok": True,
                            "militarySnapshot": {
                                "responded": True,
                                "actions": [],
                            },
                        },
                    },
                    ensure_ascii=False,
                )

            def executionOwnerActive(self):
                return True

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(
                str(Path(directory) / "operations-v2.json"),
                bridge,
            )
            try:
                facade.account_record_upsert(
                    {
                        "accountRef": "202",
                        "id": 202,
                        "username": "fixture",
                        "serverName": "fixture",
                        "enabled": True,
                        "loginState": "REAL_PROTOCOL_ONLINE",
                        "session": {
                            "accountId": 202,
                            "sourceMode": 1,
                            "publicState": {"lastValidatedAt": "1000"},
                        },
                    }
                )
                accepted = facade.dispatch(
                    "GET",
                    "/api/military/intel",
                    {"accountRef": "202", "sessionId": "202"},
                    {"requestId": "military-fixture-1", "platform": "android"},
                )

                self.assertEqual(accepted.status, 202)
                self.assertTrue(accepted.body["accepted"])
                operation = self.wait_for_operation(
                    facade,
                    accepted.body["operationId"],
                )
                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertTrue(operation["result"]["ok"])
                self.assertTrue(operation["result"]["militarySnapshot"]["responded"])
                self.assertEqual(len(bridge.calls), 1)
                self.assertEqual(bridge.calls[0][0:2], ("GET", "/api/military/intel"))
            finally:
                facade.close()

    def test_hosted_state_refresh_uses_shared_scope_plan_and_rejects_unknown_scope(self) -> None:
        class HostBridge:
            def __init__(self) -> None:
                self.calls = []

            def executeNetworkOperation(self, method, path, body_json, context_json):
                self.calls.append((method, path, json.loads(body_json)))
                return json.dumps(
                    {
                        "status": 200,
                        "body": {
                            "ok": True,
                            "role": {"roleId": 202, "roleName": "fixture"},
                            "roleState": {"copper": 1000},
                            "generals": [],
                        },
                    },
                    ensure_ascii=False,
                )

            def executionOwnerActive(self):
                return True

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(
                str(Path(directory) / "operations-v2.json"),
                bridge,
            )
            try:
                facade.account_record_upsert(
                    {
                        "accountRef": "202",
                        "id": 202,
                        "username": "fixture",
                        "serverName": "fixture",
                        "enabled": True,
                        "loginState": "REAL_PROTOCOL_ONLINE",
                        "session": {
                            "accountId": 202,
                            "sourceMode": 1,
                            "publicState": {"lastValidatedAt": "1000"},
                        },
                    }
                )
                accepted = facade.dispatch(
                    "GET",
                    "/api/state/refresh",
                    {
                        "accountRef": "202",
                        "sessionId": "must-not-be-persisted",
                        "scope": " ROLE ",
                    },
                    {"requestId": "state-role-1", "platform": "android"},
                )

                self.assertEqual(accepted.status, 202)
                operation = self.wait_for_operation(
                    facade,
                    accepted.body["operationId"],
                )
                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertEqual(len(bridge.calls), 1)
                self.assertEqual(bridge.calls[0][0:2], ("GET", "/api/state/refresh"))
                self.assertEqual(
                    bridge.calls[0][2],
                    {
                        "accountRef": "202",
                        "scope": "role",
                        "refreshParts": ["role", "resources", "generals"],
                    },
                )

                rejected = facade.dispatch(
                    "GET",
                    "/api/state/refresh",
                    {"accountRef": "202", "scope": "unsupported"},
                    {"requestId": "state-bad-scope-1", "platform": "android"},
                )
                self.assertEqual(rejected.status, 400)
                self.assertIn("scope", rejected.body["error"])
                self.assertEqual(len(bridge.calls), 1)
            finally:
                facade.close()

    def test_hosted_heartbeat_persists_no_session_and_projects_raw_host_fact(self) -> None:
        class HostBridge:
            def __init__(self) -> None:
                self.calls = []

            def executeNetworkOperation(self, method, path, body_json, context_json):
                self.calls.append((method, path, json.loads(body_json)))
                return json.dumps(
                    {
                        "status": 200,
                        "body": {
                            "ok": True,
                            "heartbeatFact": {
                                "valid": True,
                                "reason": "fixture session valid",
                                "checkedAtMillis": 123456,
                            },
                        },
                    }
                )

            def executionOwnerActive(self):
                return True

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(
                str(Path(directory) / "operations-v2.json"),
                bridge,
            )
            try:
                facade.account_record_upsert(
                    {
                        "accountRef": "202",
                        "id": 202,
                        "username": "fixture",
                        "serverName": "fixture",
                        "enabled": True,
                        "loginState": "REAL_PROTOCOL_ONLINE",
                        "session": {
                            "accountId": 202,
                            "sourceMode": 1,
                            "publicState": {"lastValidatedAt": "1000"},
                        },
                    }
                )
                accepted = facade.dispatch(
                    "GET",
                    "/api/heartbeat",
                    {
                        "accountRef": "202",
                        "sessionId": "must-not-be-persisted",
                    },
                    {"requestId": "heartbeat-1", "platform": "android"},
                )
                operation = self.wait_for_operation(
                    facade,
                    accepted.body["operationId"],
                )

                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertEqual(
                    operation["result"],
                    {
                        "ok": True,
                        "online": True,
                        "message": "fixture session valid",
                        "checkedAt": 123456,
                    },
                )
                self.assertEqual(
                    bridge.calls,
                    [("GET", "/api/heartbeat", {"accountRef": "202"})],
                )
                self.assertNotIn(
                    "must-not-be-persisted",
                    json.dumps(operation, ensure_ascii=False),
                )
            finally:
                facade.close()

    def test_hosted_visit_candidates_are_projected_by_shared_python(self) -> None:
        class HostBridge:
            def __init__(self) -> None:
                self.calls = []

            def executeNetworkOperation(self, method, path, body_json, context_json):
                self.calls.append((method, path, json.loads(body_json)))
                return json.dumps(
                    {
                        "status": 200,
                        "body": {
                            "ok": True,
                            "visitCandidatesFact": {
                                "candidates": [
                                    {
                                        "id": 7,
                                        "name": "赵云",
                                        "level": 30,
                                        "fiefName": "都城",
                                        "cityName": "洛阳",
                                        "captiveState": 0,
                                        "ownerName": "测试君主",
                                        "loyalty": 80,
                                        "growth": 95,
                                        "raw": {"sourceOpcode": "0xa271"},
                                    },
                                    {
                                        "id": 8,
                                        "name": "被俘候选",
                                        "level": 25,
                                        "captiveState": 1,
                                    },
                                ],
                                "completed": False,
                                "alreadyVisited": False,
                                "message": "请选择名将",
                                "checkedAtMillis": 654321,
                            },
                        },
                    },
                    ensure_ascii=False,
                )

            def executionOwnerActive(self):
                return True

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(
                str(Path(directory) / "operations-v2.json"),
                bridge,
            )
            try:
                facade.account_record_upsert(
                    {
                        "accountRef": "202",
                        "id": 202,
                        "username": "fixture",
                        "serverName": "fixture",
                        "enabled": True,
                        "loginState": "REAL_PROTOCOL_ONLINE",
                        "session": {
                            "accountId": 202,
                            "sourceMode": 1,
                            "publicState": {"lastValidatedAt": "1000"},
                        },
                    }
                )
                accepted = facade.dispatch(
                    "POST",
                    "/api/daily/general-visit/candidates",
                    {"accountRef": "202", "ignoredUiField": "drop-me"},
                    {"requestId": "visit-candidates-1", "platform": "android"},
                )
                operation = self.wait_for_operation(
                    facade,
                    accepted.body["operationId"],
                )

                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertEqual(operation["result"]["updatedAt"], 654321)
                self.assertTrue(operation["result"]["candidates"][0]["available"])
                self.assertFalse(operation["result"]["candidates"][1]["available"])
                self.assertEqual(
                    operation["result"]["generals"],
                    operation["result"]["candidates"],
                )
                self.assertEqual(
                    bridge.calls,
                    [(
                        "POST",
                        "/api/daily/general-visit/candidates",
                        {"accountRef": "202"},
                    )],
                )
            finally:
                facade.close()

    def test_hosted_raid_fiefs_validate_input_and_project_transport_facts(self) -> None:
        class HostBridge:
            def __init__(self) -> None:
                self.calls = []

            def executeNetworkOperation(self, method, path, body_json, context_json):
                self.calls.append((method, path, json.loads(body_json)))
                return json.dumps(
                    {
                        "status": 200,
                        "body": {
                            "ok": True,
                            "raidFiefsFact": {
                                "fiefs": [{
                                    "index": 2,
                                    "targetId": 1001,
                                    "name": "都城",
                                    "cityName": "洛阳",
                                    "serialByte": 3,
                                    "mapFlag": 1,
                                    "x": 91,
                                    "y": 26,
                                }],
                                "checkedAtMillis": 777000,
                            },
                        },
                    },
                    ensure_ascii=False,
                )

            def executionOwnerActive(self):
                return True

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(
                str(Path(directory) / "operations-v2.json"),
                bridge,
            )
            try:
                facade.account_record_upsert(
                    {
                        "accountRef": "202",
                        "id": 202,
                        "username": "fixture",
                        "serverName": "fixture",
                        "enabled": True,
                        "loginState": "REAL_PROTOCOL_ONLINE",
                        "session": {
                            "accountId": 202,
                            "sourceMode": 1,
                            "publicState": {"lastValidatedAt": "1000"},
                        },
                    }
                )
                rejected = facade.dispatch(
                    "POST",
                    "/api/raid/fiefs",
                    {"accountRef": "202", "playerName": "   "},
                    {"requestId": "raid-fiefs-empty-1"},
                )
                self.assertEqual(rejected.status, 400)
                self.assertEqual(bridge.calls, [])

                accepted = facade.dispatch(
                    "POST",
                    "/api/raid/fiefs",
                    {
                        "accountRef": "202",
                        "playerName": "  目标玩家  ",
                        "ignored": "drop-me",
                    },
                    {"requestId": "raid-fiefs-1", "platform": "android"},
                )
                operation = self.wait_for_operation(
                    facade,
                    accepted.body["operationId"],
                )

                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertEqual(operation["result"]["playerName"], "目标玩家")
                self.assertEqual(operation["result"]["fiefs"][0]["fiefName"], "都城")
                self.assertEqual(operation["result"]["updatedAt"], 777000)
                self.assertEqual(
                    bridge.calls,
                    [(
                        "POST",
                        "/api/raid/fiefs",
                        {"accountRef": "202", "playerName": "目标玩家"},
                    )],
                )
            finally:
                facade.close()

    def test_raw_host_raid_fiefs_uses_python_packet_and_parser(self) -> None:
        fixture = json.loads(
            (ROOT / "shared_core" / "protocol_parity_fixtures.json").read_text(
                encoding="utf-8"
            )
        )["fixtures"]["raidFief8310"]

        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self) -> None:
                self.commands = []

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                return account_ref == "202"

            def releaseNetworkOperation(self, _account_ref):
                return None

            def executeNetworkOperation(self, *_args):
                raise AssertionError("raw raid query must not use Kotlin route adapter")

            def executeGameCommand(self, account_ref, command_json, _context_json):
                command = json.loads(command_json)
                self.commands.append((str(account_ref), command))
                return json.dumps({
                    "status": 200,
                    "body": {
                        "ok": True,
                        "gameCommandFact": {
                            "requestOpcode": command["opcode"],
                            "httpCode": 200,
                            "httpOk": True,
                            "packets": [{
                                "opcode": 0x8310,
                                "payloadHex": fixture["responseHex"],
                            }],
                        },
                    },
                })

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(
                str(Path(directory) / "raid-fiefs-raw.json"), bridge
            )
            try:
                facade.account_record_upsert({
                    "accountRef": "202",
                    "id": 202,
                    "username": "fixture",
                    "serverName": "fixture",
                    "enabled": True,
                    "loginState": "REAL_PROTOCOL_ONLINE",
                    "session": {
                        "accountId": 202,
                        "sourceMode": 1,
                        "publicState": {
                            "gameHttp": FIXTURE_GAME_HTTP,
                            "lastValidatedAt": "1000",
                        },
                    },
                })
                accepted = facade.dispatch(
                    "POST",
                    "/api/raid/fiefs",
                    {
                        "accountRef": "202",
                        "playerName": fixture["playerName"],
                    },
                    {"requestId": "raid-fiefs-raw", "platform": "android"},
                )
                operation = self.wait_for_operation(
                    facade, accepted.body["operationId"]
                )

                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertFalse(operation["requestSent"])
                self.assertEqual(operation["result"]["fiefs"][0]["targetId"], fixture["expected"]["firstTargetId"])
                self.assertEqual(bridge.commands[0][0], "202")
                self.assertEqual(bridge.commands[0][1]["opcode"], 0x1310)
                self.assertEqual(
                    bridge.commands[0][1]["payloadHex"],
                    fixture["requestPayloadHex"],
                )
                self.assertTrue(bridge.commands[0][1]["readOnly"])
            finally:
                facade.close()

    def test_hosted_network_operation_rechecks_shared_session_gate_before_host_call(self) -> None:
        class HostBridge:
            calls = 0

            def executionOwnerActive(self):
                return True

            def executeNetworkOperation(self, *_args):
                self.calls += 1
                return json.dumps({"status": 200, "body": {"ok": True}})

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(
                str(Path(directory) / "operations-v2.json"),
                bridge,
            )
            try:
                facade.account_record_upsert(
                    {
                        "accountRef": "202",
                        "id": 202,
                        "username": "fixture",
                        "serverName": "fixture",
                        "enabled": False,
                        "loginState": "REAL_PROTOCOL_STOPPED",
                        "session": {
                            "accountId": 202,
                            "sourceMode": 1,
                            "publicState": {},
                        },
                    }
                )
                accepted = facade.dispatch(
                    "GET",
                    "/api/military/intel",
                    {"accountRef": "202"},
                    {"requestId": "military-stopped-1"},
                )
                operation = self.wait_for_operation(
                    facade,
                    accepted.body["operationId"],
                )

                self.assertEqual(operation["status"], "FAILED")
                self.assertIn("Session", operation["error"]["message"])
                self.assertEqual(bridge.calls, 0)
            finally:
                facade.close()

    def test_hosted_network_operation_requires_a_live_platform_owner(self) -> None:
        class HostBridge:
            calls = 0

            def executionOwnerActive(self):
                return False

            def executeNetworkOperation(self, *_args):
                self.calls += 1
                return json.dumps({"status": 200, "body": {"ok": True}})

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(
                str(Path(directory) / "operations-v2.json"),
                bridge,
            )
            try:
                facade.account_record_upsert(
                    {
                        "accountRef": "202",
                        "id": 202,
                        "username": "fixture",
                        "serverName": "fixture",
                        "enabled": True,
                        "loginState": "REAL_PROTOCOL_ONLINE",
                        "session": {
                            "accountId": 202,
                            "sourceMode": 1,
                            "publicState": {"lastValidatedAt": "1000"},
                        },
                    }
                )
                accepted = facade.dispatch(
                    "GET",
                    "/api/military/intel",
                    {"accountRef": "202"},
                    {"requestId": "military-owner-off-1"},
                )
                operation = self.wait_for_operation(
                    facade,
                    accepted.body["operationId"],
                )

                self.assertEqual(operation["status"], "FAILED")
                self.assertIn("执行所有者未激活", operation["error"]["message"])
                self.assertEqual(bridge.calls, 0)
            finally:
                facade.close()

    def test_hosted_network_operation_retries_busy_account_lane_without_blocking_host_call(self) -> None:
        class HostBridge:
            def __init__(self) -> None:
                self.calls = 0

            def executionOwnerActive(self):
                return True

            def executeNetworkOperation(self, *_args):
                self.calls += 1
                if self.calls < 3:
                    return json.dumps(
                        {
                            "status": 503,
                            "body": {
                                "ok": False,
                                "code": "LOCAL_ACCOUNT_BUSY",
                                "error": "account lane busy",
                            },
                        }
                    )
                return json.dumps(
                    {
                        "status": 200,
                        "body": {
                            "ok": True,
                            "militarySnapshot": {
                                "responded": True,
                                "actions": [],
                            },
                        },
                    }
                )

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(
                str(Path(directory) / "operations-v2.json"),
                bridge,
            )
            try:
                facade.account_record_upsert(
                    {
                        "accountRef": "202",
                        "id": 202,
                        "username": "fixture",
                        "serverName": "fixture",
                        "enabled": True,
                        "loginState": "REAL_PROTOCOL_ONLINE",
                        "session": {
                            "accountId": 202,
                            "sourceMode": 1,
                            "publicState": {"lastValidatedAt": "1000"},
                        },
                    }
                )
                accepted = facade.dispatch(
                    "GET",
                    "/api/military/intel",
                    {"accountRef": "202"},
                    {"requestId": "military-busy-1"},
                )
                operation = self.wait_for_operation(
                    facade,
                    accepted.body["operationId"],
                )

                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertEqual(bridge.calls, 3)
            finally:
                facade.close()

    def test_formation_apply_mutation_marks_send_boundary_and_distinguishes_outcomes(self) -> None:
        class HostBridge:
            def __init__(self, ledger: Path, outcome: str) -> None:
                self.ledger = ledger
                self.outcome = outcome
                self.acquired = 0
                self.released = 0
                self.calls = []

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                self.acquired += 1
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                self.released += 1
                self.assert_account = account_ref

            def executeNetworkOperation(self, method, path, body_json, context_json):
                body = json.loads(body_json)
                context = json.loads(context_json)
                ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
                record = next(
                    row for row in ledger["operations"]
                    if row["operationId"] == context["operationId"]
                )
                if not record["requestSent"]:
                    raise AssertionError("requestSent must be durable before host mutation")
                self.calls.append((method, path, body))
                if self.outcome == "crash":
                    raise RuntimeError("socket closed after send")
                if self.outcome == "rejected":
                    return json.dumps({
                        "status": 409,
                        "body": {
                            "ok": False,
                            "code": "FORMATION_REJECTED",
                            "error": "server rejected formation",
                        },
                    })
                return json.dumps({
                    "status": 200,
                    "body": {"ok": True, "success": True, "appliedCount": 2},
                })

        def live_account(facade: CoreFacade) -> None:
            facade.account_record_upsert({
                "accountRef": "202",
                "id": 202,
                "username": "fixture",
                "serverName": "fixture",
                "enabled": True,
                "loginState": "REAL_PROTOCOL_ONLINE",
                "session": {
                    "accountId": 202,
                    "sourceMode": 1,
                    "publicState": {"lastValidatedAt": "1000"},
                },
            })

        request = {
            "accountRef": "202",
            "confirm": "apply-formations",
            "formations": [{
                "enabled": True,
                "generalIds": [7, 8],
                "soldierType": "近卫兵",
                "soldierCount": 1800,
            }],
            "formationOptions": {"clearOtherGenerals": False},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for outcome, expected in (
                ("success", "SUCCEEDED"),
                ("rejected", "FAILED"),
                ("crash", "UNCERTAIN"),
            ):
                ledger = root / f"{outcome}.json"
                bridge = HostBridge(ledger, outcome)
                facade = create_hosted_core(str(ledger), bridge)
                try:
                    live_account(facade)
                    accepted = facade.dispatch(
                        "POST",
                        "/api/formations/apply",
                        request,
                        {"requestId": f"formation-{outcome}-1", "platform": "android"},
                    )
                    self.assertEqual(accepted.status, 202)
                    operation = self.wait_for_operation(
                        facade,
                        accepted.body["operationId"],
                    )
                    self.assertEqual(operation["status"], expected)
                    self.assertTrue(operation["requestSent"])
                    self.assertEqual(bridge.acquired, 1)
                    self.assertEqual(bridge.released, 1)
                    self.assertEqual(len(bridge.calls), 1)
                    sent = bridge.calls[0][2]
                    self.assertEqual(
                        [row["generalId"] for row in sent["formations"]],
                        ["7", "8"],
                    )
                    if outcome == "rejected":
                        self.assertEqual(operation["error"]["code"], "FORMATION_REJECTED")
                    if outcome == "crash":
                        self.assertIn("socket closed", operation["error"]["message"])
                finally:
                    facade.close()

    def test_unassign_all_mutation_owns_validation_send_boundary_and_projection(self) -> None:
        class HostBridge:
            def __init__(self, ledger: Path, outcome: str) -> None:
                self.ledger = ledger
                self.outcome = outcome
                self.acquired = 0
                self.released = 0
                self.calls = []

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                self.acquired += 1
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                self.released += 1
                self.released_account = account_ref

            def executeNetworkOperation(self, method, path, body_json, context_json):
                body = json.loads(body_json)
                context = json.loads(context_json)
                ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
                record = next(
                    row for row in ledger["operations"]
                    if row["operationId"] == context["operationId"]
                )
                if not record["requestSent"]:
                    raise AssertionError("requestSent must be durable before unassign mutation")
                self.calls.append((method, path, body))
                if self.outcome == "crash":
                    raise RuntimeError("connection lost after unassign send")
                if self.outcome == "host-rejected":
                    return json.dumps({
                        "status": 409,
                        "body": {
                            "ok": False,
                            "code": "UNASSIGN_SERVER_REJECTED",
                            "error": "server rejected unassign",
                        },
                    })
                warning = (
                    "卸兵已获得服务器回执，但刷新将领失败：断线"
                    if self.outcome == "refresh-warning"
                    else ""
                )
                receipt_success = self.outcome != "receipt-rejected"
                return json.dumps({
                    "status": 200,
                    "body": {
                        "ok": True,
                        "unassignAllFact": {
                            "receipt": {
                                "success": receipt_success,
                                "message": (
                                    "卸兵成功" if receipt_success else "服务器未确认卸兵"
                                ),
                                "raw": {
                                    "clear.clearedCount": "3",
                                    "clear.skippedCount": "1",
                                },
                            },
                            "generals": [{"id": 7, "name": "关羽"}],
                            "army": [{"generalId": 7, "soldierCount": 0}],
                            "roleState": {"roleId": 202},
                            "refreshWarning": warning,
                        },
                    },
                }, ensure_ascii=False)

        def live_account(facade: CoreFacade) -> None:
            facade.account_record_upsert({
                "accountRef": "202",
                "id": 202,
                "username": "fixture",
                "serverName": "fixture",
                "enabled": True,
                "loginState": "REAL_PROTOCOL_ONLINE",
                "session": {
                    "accountId": 202,
                    "sourceMode": 1,
                    "publicState": {"lastValidatedAt": "1000"},
                },
            })

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            validation_ledger = root / "validation.json"
            validation_bridge = HostBridge(validation_ledger, "success")
            validation_facade = create_hosted_core(
                str(validation_ledger),
                validation_bridge,
            )
            try:
                live_account(validation_facade)
                rejected = validation_facade.dispatch(
                    "POST",
                    "/api/formations/unassign-all",
                    {"accountRef": "202"},
                    {"requestId": "unassign-invalid-1", "platform": "android"},
                )
                self.assertEqual(rejected.status, 400)
                self.assertEqual(validation_bridge.acquired, 0)
                self.assertEqual(validation_bridge.calls, [])
                self.assertEqual(validation_facade.operations_snapshot()["count"], 0)
            finally:
                validation_facade.close()

            for outcome, expected in (
                ("success", "SUCCEEDED"),
                ("refresh-warning", "SUCCEEDED"),
                ("receipt-rejected", "FAILED"),
                ("host-rejected", "FAILED"),
                ("crash", "UNCERTAIN"),
            ):
                ledger = root / f"unassign-{outcome}.json"
                bridge = HostBridge(ledger, outcome)
                facade = create_hosted_core(str(ledger), bridge)
                try:
                    live_account(facade)
                    accepted = facade.dispatch(
                        "POST",
                        "/api/formations/unassign-all",
                        {
                            "accountRef": "202",
                            "confirm": "unassign-all-troops",
                            "ignored": "must-not-be-persisted",
                        },
                        {"requestId": f"unassign-{outcome}-1", "platform": "android"},
                    )
                    self.assertEqual(accepted.status, 202)
                    operation = self.wait_for_operation(
                        facade,
                        accepted.body["operationId"],
                    )

                    self.assertEqual(operation["status"], expected)
                    self.assertTrue(operation["requestSent"])
                    self.assertEqual(bridge.acquired, 1)
                    self.assertEqual(bridge.released, 1)
                    self.assertEqual(bridge.released_account, "202")
                    self.assertEqual(
                        bridge.calls,
                        [(
                            "POST",
                            "/api/formations/unassign-all",
                            {
                                "accountRef": "202",
                                "confirm": "unassign-all-troops",
                            },
                        )],
                    )
                    self.assertNotIn(
                        "must-not-be-persisted",
                        json.dumps(operation, ensure_ascii=False),
                    )
                    if outcome in {"success", "refresh-warning"}:
                        self.assertEqual(operation["result"]["clearedCount"], 3)
                        self.assertEqual(operation["result"]["skippedCount"], 1)
                        self.assertEqual(operation["result"]["generals"][0]["id"], 7)
                    if outcome == "refresh-warning":
                        self.assertIn("刷新将领失败", operation["result"]["refreshWarning"])
                    if outcome == "receipt-rejected":
                        self.assertEqual(operation["error"]["code"], "UNASSIGN_ALL_REJECTED")
                    if outcome == "host-rejected":
                        self.assertEqual(operation["error"]["code"], "UNASSIGN_SERVER_REJECTED")
                    if outcome == "crash":
                        self.assertIn("connection lost", operation["error"]["message"])
                finally:
                    facade.close()

    def test_shared_raw_command_assign_and_refill_workflows_own_business_semantics(self) -> None:
        fixtures = json.loads(
            (ROOT / "shared_core" / "protocol_parity_fixtures.json")
            .read_text(encoding="utf-8")
        )["fixtures"]
        general_id = int(fixtures["generalRecord8004"]["expected"]["id"])
        state_hex = (
            fixtures["generalRecord8004"]["responseHex"]
            + fixtures["idleArmy8004"]["responseHex"]
        )

        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self, ledger: Path, outcome: str) -> None:
                self.ledger = ledger
                self.outcome = outcome
                self.acquired = 0
                self.released = 0
                self.commands = []

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                self.acquired += 1
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                self.released += 1
                self.released_account = account_ref

            def executeNetworkOperation(self, *_args):
                raise AssertionError("troop workflow must use the raw command port")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                context = json.loads(context_json)
                opcode = int(command["opcode"])
                payload_hex = str(command["payloadHex"])
                self.commands.append((opcode, payload_hex, command["phase"]))
                if opcode != 0x1016:
                    ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
                    record = next(
                        row for row in ledger["operations"]
                        if row["operationId"] == context["operationId"]
                    )
                    if not record["requestSent"]:
                        raise AssertionError(
                            "requestSent must be durable before raw mutation command"
                        )
                if opcode == 0x1016:
                    packets = [{"opcode": 0x8004, "payloadHex": state_hex}]
                elif opcode == 0x1226:
                    if self.outcome == "assign-crash":
                        raise RuntimeError("socket closed after raw assign send")
                    if self.outcome == "assign-missing":
                        packets = [{"opcode": 0x880D, "payloadHex": "00"}]
                    else:
                        status = 0 if self.outcome == "assign-rejected" else 1
                        receipt = struct.pack(
                            ">bqhhhh",
                            status,
                            general_id,
                            -1,
                            0,
                            3,
                            100,
                        )
                        packets = [{"opcode": 0x8226, "payloadHex": receipt.hex()}]
                elif opcode == 0x1229:
                    message = "批量补满成功".encode("utf-8")
                    receipt = (
                        b"\x00"
                        + len(message).to_bytes(2, "big")
                        + message
                        + b"\x01"
                        + struct.pack(">qBi", general_id, 3, 100)
                    )
                    packets = [{"opcode": 0x8229, "payloadHex": receipt.hex()}]
                else:
                    raise AssertionError(f"unexpected raw opcode {opcode:#x}")
                return json.dumps({
                    "status": 200,
                    "body": {
                        "ok": True,
                        "gameCommandFact": {
                            "requestOpcode": opcode,
                            "httpCode": 200,
                            "httpOk": True,
                            "responseBytes": sum(
                                len(row["payloadHex"]) // 2 for row in packets
                            ),
                            "packets": packets,
                        },
                    },
                })

        def live_account(facade: CoreFacade) -> None:
            facade.account_record_upsert({
                "accountRef": "202",
                "id": 202,
                "username": "fixture",
                "serverName": "fixture",
                "enabled": True,
                "loginState": "REAL_PROTOCOL_ONLINE",
                "session": {
                    "accountId": 202,
                    "sourceMode": 1,
                    "publicState": {
                        "roleId": 202,
                        "gameHttp": FIXTURE_GAME_HTTP,
                        "lastValidatedAt": "1000",
                    },
                },
            })

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            validation_ledger = root / "raw-validation.json"
            validation_bridge = HostBridge(validation_ledger, "assign-success")
            validation_facade = create_hosted_core(
                str(validation_ledger),
                validation_bridge,
            )
            try:
                live_account(validation_facade)
                invalid = validation_facade.dispatch(
                    "POST",
                    "/api/troops/assign",
                    {
                        "accountRef": "202",
                        "generalId": general_id,
                        "soldierType": "轻骑兵",
                        "soldierCount": 100,
                    },
                    {"requestId": "assign-invalid-1", "platform": "android"},
                )
                self.assertEqual(invalid.status, 400)
                self.assertEqual(validation_bridge.acquired, 0)
                self.assertEqual(validation_bridge.commands, [])
            finally:
                validation_facade.close()

            for outcome, expected in (
                ("assign-success", "SUCCEEDED"),
                ("assign-rejected", "FAILED"),
                ("assign-missing", "UNCERTAIN"),
                ("assign-crash", "UNCERTAIN"),
            ):
                ledger = root / f"raw-{outcome}.json"
                bridge = HostBridge(ledger, outcome)
                facade = create_hosted_core(str(ledger), bridge)
                try:
                    live_account(facade)
                    accepted = facade.dispatch(
                        "POST",
                        "/api/troops/assign",
                        {
                            "accountRef": "202",
                            "confirm": "assign-troops",
                            "generalId": general_id,
                            "soldierType": "轻骑兵",
                            "soldierCount": 100,
                            "ignored": "do-not-persist",
                        },
                        {"requestId": f"{outcome}-1", "platform": "android"},
                    )
                    self.assertEqual(accepted.status, 202)
                    operation = self.wait_for_operation(
                        facade,
                        accepted.body["operationId"],
                    )

                    self.assertEqual(operation["status"], expected)
                    self.assertTrue(operation["requestSent"])
                    self.assertEqual(bridge.acquired, 1)
                    self.assertEqual(bridge.released, 1)
                    self.assertEqual(bridge.released_account, "202")
                    self.assertEqual(bridge.commands[0][0], 0x1016)
                    self.assertEqual(bridge.commands[1][0], 0x1226)
                    self.assertEqual(
                        bridge.commands[1][1],
                        struct.pack(">qbhi", general_id, 0, 3, 100).hex(),
                    )
                    self.assertNotIn(
                        "do-not-persist",
                        json.dumps(operation, ensure_ascii=False),
                    )
                    if outcome == "assign-success":
                        self.assertTrue(operation["result"]["result"]["success"])
                        self.assertEqual(
                            operation["result"]["result"]["raw"]["effectiveCount"],
                            100,
                        )
                    if outcome == "assign-rejected":
                        self.assertEqual(
                            operation["error"]["code"],
                            "TROOP_ASSIGN_REJECTED",
                        )
                finally:
                    facade.close()

            precheck_ledger = root / "raw-precheck.json"
            precheck_bridge = HostBridge(precheck_ledger, "assign-success")
            precheck_facade = create_hosted_core(
                str(precheck_ledger),
                precheck_bridge,
            )
            try:
                live_account(precheck_facade)
                accepted = precheck_facade.dispatch(
                    "POST",
                    "/api/troops/assign",
                    {
                        "accountRef": "202",
                        "confirm": "assign-troops",
                        "generalId": general_id,
                        "soldierType": "轻骑兵",
                        "soldierCount": 200,
                    },
                    {"requestId": "assign-precheck-1", "platform": "android"},
                )
                operation = self.wait_for_operation(
                    precheck_facade,
                    accepted.body["operationId"],
                )
                self.assertEqual(operation["status"], "FAILED")
                self.assertFalse(operation["requestSent"])
                self.assertEqual(
                    [row[0] for row in precheck_bridge.commands],
                    [0x1016],
                )
            finally:
                precheck_facade.close()

            refill_ledger = root / "raw-refill.json"
            refill_bridge = HostBridge(refill_ledger, "refill-success")
            refill_facade = create_hosted_core(str(refill_ledger), refill_bridge)
            try:
                live_account(refill_facade)
                accepted = refill_facade.dispatch(
                    "POST",
                    "/api/troops/refill",
                    {
                        "accountRef": "202",
                        "confirm": "batch-refill",
                        "generalIds": [str(general_id), str(general_id)],
                        "ignored": "drop-me",
                    },
                    {"requestId": "refill-success-1", "platform": "android"},
                )
                operation = self.wait_for_operation(
                    refill_facade,
                    accepted.body["operationId"],
                )
                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertTrue(operation["requestSent"])
                self.assertEqual(
                    [row[0] for row in refill_bridge.commands],
                    [0x1016, 0x1229],
                )
                self.assertEqual(
                    refill_bridge.commands[1][1],
                    (b"\x01" + struct.pack(">q", general_id)).hex(),
                )
                self.assertTrue(operation["result"]["result"]["success"])
                self.assertNotIn("drop-me", json.dumps(operation))
            finally:
                refill_facade.close()

    def test_shared_raw_command_heal_workflow_owns_plan_receipts_and_single_recovery(self) -> None:
        fixtures = json.loads(
            (ROOT / "shared_core" / "protocol_parity_fixtures.json")
            .read_text(encoding="utf-8")
        )["fixtures"]
        general_id = int(fixtures["generalRecord8004"]["expected"]["id"])
        state_hex = (
            fixtures["generalRecord8004"]["responseHex"]
            + fixtures["idleArmy8004"]["responseHex"]
        )
        fief_id = 555

        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self, ledger: Path, outcome: str) -> None:
                self.ledger = ledger
                self.outcome = outcome
                self.acquired = 0
                self.released = 0
                self.commands = []
                self.heal_calls = 0

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                self.acquired += 1
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                self.released += 1

            def executeNetworkOperation(self, *_args):
                raise AssertionError("heal workflow must use raw commands")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                context = json.loads(context_json)
                opcode = int(command["opcode"])
                payload_hex = str(command["payloadHex"])
                self.commands.append((opcode, payload_hex))
                if opcode in {0x1152, 0x1230}:
                    ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
                    record = next(
                        row for row in ledger["operations"]
                        if row["operationId"] == context["operationId"]
                    )
                    if not record["requestSent"]:
                        raise AssertionError(
                            "requestSent must be durable before heal mutation"
                        )
                if opcode == 0x1016:
                    packets = [{"opcode": 0x8004, "payloadHex": state_hex}]
                elif opcode == 0x1231:
                    if self.outcome == "pre-missing":
                        packets = [{"opcode": 0x880D, "payloadHex": "00"}]
                    else:
                        packets = [{
                            "opcode": 0x8231,
                            "payloadHex": struct.pack(
                                ">qhqq",
                                fief_id,
                                3,
                                100,
                                0,
                            ).hex(),
                        }]
                elif opcode == 0x1230:
                    self.heal_calls += 1
                    if self.outcome == "heal-crash":
                        raise RuntimeError("socket closed after heal send")
                    if self.outcome == "heal-missing":
                        packets = [{"opcode": 0x880D, "payloadHex": "00"}]
                    else:
                        status = (
                            -1
                            if self.outcome == "copper-recovery"
                            and self.heal_calls == 1
                            else -2
                            if self.outcome == "heal-rejected"
                            else 0
                        )
                        packets = [{
                            "opcode": 0x8230,
                            "payloadHex": struct.pack(">bqqB", status, 1, 2, 0).hex(),
                        }]
                elif opcode == 0x1152:
                    packets = [{
                        "opcode": 0x8152,
                        "payloadHex": (
                            b"\x00" + struct.pack(">qq", 30_000, 200_000)
                        ).hex(),
                    }]
                else:
                    raise AssertionError(f"unexpected heal opcode {opcode:#x}")
                return json.dumps({
                    "status": 200,
                    "body": {
                        "ok": True,
                        "gameCommandFact": {
                            "requestOpcode": opcode,
                            "httpCode": 200,
                            "httpOk": True,
                            "responseBytes": sum(
                                len(row["payloadHex"]) // 2 for row in packets
                            ),
                            "packets": packets,
                        },
                    },
                })

        def live_account(facade: CoreFacade) -> None:
            facade.account_record_upsert({
                "accountRef": "202",
                "id": 202,
                "username": "fixture",
                "serverName": "fixture",
                "enabled": True,
                "loginState": "REAL_PROTOCOL_ONLINE",
                "session": {
                    "accountId": 202,
                    "sourceMode": 1,
                    "publicState": {
                        "roleId": 202,
                        "gameHttp": FIXTURE_GAME_HTTP,
                        "lastValidatedAt": "1000",
                    },
                },
            })

        request = {
            "accountRef": "202",
            "confirm": "heal-wounded",
            "generalId": general_id,
            "fiefId": fief_id,
            "soldierType": "轻骑兵",
            "woundedCount": 7,
            "foodToCopper": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for outcome, expected in (
                ("heal-success", "SUCCEEDED"),
                ("heal-rejected", "FAILED"),
                ("pre-missing", "FAILED"),
                ("heal-missing", "UNCERTAIN"),
                ("heal-crash", "UNCERTAIN"),
                ("copper-recovery", "SUCCEEDED"),
            ):
                ledger = root / f"raw-heal-{outcome}.json"
                bridge = HostBridge(ledger, outcome)
                facade = create_hosted_core(str(ledger), bridge)
                try:
                    live_account(facade)
                    accepted = facade.dispatch(
                        "POST",
                        "/api/troops/heal",
                        {**request, "ignored": "drop-heal"},
                        {"requestId": f"{outcome}-1", "platform": "android"},
                    )
                    self.assertEqual(accepted.status, 202)
                    operation = self.wait_for_operation(
                        facade,
                        accepted.body["operationId"],
                    )
                    self.assertEqual(operation["status"], expected)
                    self.assertEqual(bridge.acquired, 1)
                    self.assertEqual(bridge.released, 1)
                    self.assertEqual(bridge.commands[0][0], 0x1016)
                    if outcome == "pre-missing":
                        self.assertFalse(operation["requestSent"])
                        self.assertEqual(
                            [row[0] for row in bridge.commands],
                            [0x1016, 0x1231],
                        )
                    else:
                        self.assertTrue(operation["requestSent"])
                    if outcome == "heal-success":
                        self.assertTrue(operation["result"]["result"]["success"])
                        self.assertEqual(
                            [row[0] for row in bridge.commands],
                            [0x1016, 0x1231, 0x1230],
                        )
                    if outcome == "heal-rejected":
                        self.assertEqual(
                            operation["error"]["code"],
                            "TROOP_HEAL_REJECTED",
                        )
                    if outcome == "copper-recovery":
                        self.assertEqual(
                            [row[0] for row in bridge.commands],
                            [0x1016, 0x1231, 0x1230, 0x1152, 0x1231, 0x1230],
                        )
                        self.assertTrue(
                            operation["result"]["result"]["raw"]["copperRecovery"]["attempted"]
                        )
                    self.assertNotIn(
                        "drop-heal",
                        json.dumps(operation, ensure_ascii=False),
                    )
                finally:
                    facade.close()

            no_wounded_ledger = root / "raw-heal-no-wounded.json"
            no_wounded_bridge = HostBridge(no_wounded_ledger, "heal-success")
            no_wounded_facade = create_hosted_core(
                str(no_wounded_ledger),
                no_wounded_bridge,
            )
            try:
                live_account(no_wounded_facade)
                accepted = no_wounded_facade.dispatch(
                    "POST",
                    "/api/troops/heal",
                    {**request, "woundedCount": 0},
                    {"requestId": "heal-no-wounded-1", "platform": "android"},
                )
                operation = self.wait_for_operation(
                    no_wounded_facade,
                    accepted.body["operationId"],
                )
                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertFalse(operation["requestSent"])
                self.assertEqual(
                    [row[0] for row in no_wounded_bridge.commands],
                    [0x1016],
                )
                self.assertEqual(
                    operation["result"]["result"]["raw"]["skipped"],
                    "no-wounded-soldiers",
                )
            finally:
                no_wounded_facade.close()

    def test_shared_log_routes_own_paging_localization_and_account_filtering(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        system = facade.dispatch(
            "GET",
            "/api/logs/system",
            {
                "limit": 2,
                "afterId": 10,
                "latestId": 13,
                "maxLines": 1_500,
                "storage": "fixture",
                "entries": [
                    {"id": 12, "time": 1200, "tag": "keepalive", "message": "wakelock released"},
                    {"id": 11, "time": 1100, "tag": "scheduler", "message": "LOSSLESS RUNNING"},
                    {"id": 9, "time": 900, "tag": "old", "message": "old"},
                ],
            },
        )
        initial = facade.dispatch(
            "GET",
            "/api/logs/system",
            {
                "limit": 2,
                "latestId": 4,
                "entries": [
                    {"id": 1, "time": 1, "message": "one"},
                    {"id": 2, "time": 2, "message": "two"},
                    {"id": 3, "time": 3, "message": "three"},
                    {"id": 4, "time": 4, "message": "four"},
                ],
            },
        )
        account = facade.dispatch(
            "GET",
            "/api/logs/account",
            {
                "accountRef": "7",
                "accountKey": "fixture-7",
                "limit": 2,
                "maxLines": 100,
                "entries": [
                    {"id": 1, "time": 1, "accountId": 8, "message": "other"},
                    {"id": 2, "time": 2, "accountId": 7, "message": "one"},
                    {"id": 3, "time": 3, "accountId": 7, "message": "two"},
                    {"id": 4, "time": 4, "accountId": 7, "message": "three"},
                    {"id": 5, "time": 5, "message": "unscoped"},
                ],
            },
        )

        self.assertEqual(system.status, 200)
        self.assertEqual([11, 12], [row["id"] for row in system.body["entries"]])
        self.assertEqual(system.body["entries"][0]["message"], "无损 运行中")
        self.assertEqual(system.body["entries"][1]["message"], "已释放后台保活锁")
        self.assertEqual(system.body["cursorId"], 12)
        self.assertEqual(system.body["latestId"], 13)
        self.assertTrue(system.body["hasMore"])
        self.assertEqual([3, 4], [row["id"] for row in initial.body["entries"]])

        self.assertEqual(account.status, 200)
        self.assertEqual(account.body["accountKey"], "fixture-7")
        self.assertEqual([3, 4], [row["id"] for row in account.body["entries"]])
        facade.close()

    def test_shared_success_route_accepts_structured_facts_and_exact_legacy_only(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        response = facade.dispatch(
            "GET",
            "/api/success-records",
            {
                "accountRef": "7",
                "accountKey": "fixture-7",
                "limit": 50,
                "records": [{
                    "id": 9,
                    "time": 900,
                    "category": "治疗",
                    "message": "兵种0 -1",
                }, {
                    "id": 8,
                    "time": 800,
                    "sessionId": "8",
                    "category": "其他账号",
                    "message": "不应该出现",
                }],
                "logEntries": [
                    {
                        "id": 10,
                        "time": 1000,
                        "accountId": 7,
                        "tag": "daily",
                        "message": "领竞技币完成：服务器确认成功",
                    },
                    {
                        "id": 11,
                        "time": 1100,
                        "accountId": 7,
                        "successCategory": "刷黄",
                        "successMessage": "击败10级山贼",
                        "message": "structured",
                    },
                    {
                        "id": 12,
                        "time": 1200,
                        "accountId": 7,
                        "message": "常规-日常保存成功：已开启自动签到",
                    },
                    {
                        "id": 13,
                        "time": 1300,
                        "accountId": 8,
                        "message": "领竞技币完成：其他账号",
                    },
                    {
                        "id": 14,
                        "time": 1400,
                        "message": "领竞技币完成：未归属日志",
                    },
                ],
            },
        )

        self.assertEqual(response.status, 200)
        entries = response.body["entries"]
        self.assertEqual(["刷黄", "领币", "治疗"], [row["category"] for row in entries])
        self.assertEqual(entries[-1]["message"], "全部伤兵")
        self.assertFalse(any("保存成功" in row["message"] for row in entries))
        facade.close()

    def test_shared_success_route_recovers_resident_battles_and_dedupes(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        facade.account_record_upsert({
            "accountRef": "7",
            "id": 7,
            "session": {
                "accountId": 7,
                "sourceMode": 1,
                "publicState": {
                    "brushPendingRecoveryJson": json.dumps({
                        "sendState": "accepted",
                        "battleId": 701,
                        "acceptedAtMillis": 7_010,
                        "target": {
                            "name": "7级山贼",
                            "x": 10,
                            "y": 11,
                        },
                    }),
                    "dungeonLastResultJson": json.dumps({
                        "state": "chest-opened",
                        "battleId": 702,
                        "completedAtMillis": 7_020,
                        "stage": {
                            "chapterName": "第四章",
                            "stage": 5,
                        },
                        "chestResult": {
                            "success": True,
                            "chestName": "右",
                        },
                    }),
                },
            },
        })
        response = facade.dispatch(
            "GET",
            "/api/success-records",
            {
                "accountRef": "7",
                "accountKey": "fixture-7",
                "limit": 50,
                "logEntries": [{
                    "id": 7_011,
                    "time": 7_011,
                    "accountId": 7,
                    "message": (
                        "共享常驻 tick=1 account=7 feature=brush "
                        "state=dispatched nextWakeAt=99 "
                        "message=刷黄出征已确认：battleId=701"
                    ),
                }],
            },
        )

        self.assertEqual(response.status, 200)
        entries = response.body["entries"]
        self.assertEqual(2, len(entries))
        self.assertEqual({"刷黄", "副本"}, {row["category"] for row in entries})
        self.assertEqual(
            1,
            sum("battleId=701" in row["message"] for row in entries),
        )
        brush = next(row for row in entries if row["category"] == "刷黄")
        self.assertIn("7级山贼(10，11)", brush["message"])
        self.assertEqual(701, brush["detail"]["battleId"])
        dungeon = next(row for row in entries if row["category"] == "副本")
        self.assertIn("第四章第5关", dungeon["message"])
        self.assertIn("battleId=702", dungeon["message"])
        facade.close()

    def test_resident_success_record_uses_brush_formation_and_lossless_stage(self) -> None:
        brush = resident_success_record(
            {
                "feature": "brush",
                "state": "dispatched",
                "success": True,
                "dispatchAccepted": True,
                "battleId": 19432238,
                "formationNumber": 3,
                "formationSourceRowIndex": 2,
                "sourceRowIndex": 0,
                "target": {
                    "name": "8级山贼",
                    "x": 86,
                    "y": 26,
                },
            },
            now_millis=7_000,
        )
        self.assertIsNotNone(brush)
        self.assertEqual(
            brush["message"],
            "编队1 > 8级山贼(86，26)（battleId=19432238）",
        )
        self.assertEqual(brush["detail"]["formationNumber"], 1)
        self.assertEqual(brush["detail"]["formationSourceRowIndex"], 2)
        self.assertEqual(brush["detail"]["ruleSourceRowIndex"], 0)

        for stage_name in ("卫兵", "小队长", "大队长", "头目", "首领"):
            with self.subTest(stage_name=stage_name):
                lossless = resident_success_record(
                    {
                        "feature": "lossless",
                        "state": "fighting",
                        "success": True,
                        "dispatchAccepted": True,
                        "battleId": 19428377,
                        "stage": {
                            "level": 9,
                            "levelName": "9级关卡",
                            "stageName": stage_name,
                        },
                    },
                    now_millis=7_100,
                )
                self.assertIsNotNone(lossless)
                self.assertEqual(lossless["message"], f"9级-{stage_name}")
                self.assertEqual(lossless["detail"]["stage"]["level"], 9)

    def test_every_confirmed_expedition_is_recorded_not_only_listed_ones(
        self,
    ) -> None:
        """Recognition follows the dispatch evidence, not a list of features.

        打矿 dispatched all day on a real account and appeared in no record the
        operator could see, because the projection enumerated features and its
        branch had never been written.  The evidence is identical for every
        expedition, so any feature carrying it must produce a line - otherwise
        the next feature added repeats this silently.
        """

        mine = resident_success_record(
            {
                "feature": "mine",
                "state": "dispatched",
                "success": True,
                "dispatchAccepted": True,
                "battleId": 41472667,
                "sourceRowIndex": 0,
                "target": {
                    "name": "1级镔铁矿",
                    "mineType": "BIN_TIE",
                    "x": 91,
                    "y": 26,
                },
            },
            now_millis=7_200,
        )
        self.assertIsNotNone(mine)
        self.assertEqual("打矿", mine["category"])
        self.assertEqual(
            "编队1 > 1级镔铁矿(91，26)（battleId=41472667）",
            mine["message"],
        )
        self.assertEqual("mine:battle:41472667", mine["dedupeKey"])

        raid = resident_success_record(
            {
                "feature": "raid",
                "state": "dispatched",
                "success": True,
                "dispatchAccepted": True,
                "battleId": 41472777,
                "sourceRowIndex": 1,
                "target": {"name": "张三", "x": 10, "y": 20},
            },
            now_millis=7_300,
        )
        self.assertIsNotNone(raid)
        self.assertEqual("掠夺", raid["category"])
        self.assertEqual(
            "编队2 > 张三(10，20)（battleId=41472777）",
            raid["message"],
        )

        # Every feature the scheduler can dispatch has to be nameable here.
        for feature in ("brush", "brushYellow", "mine", "raid", "lossless"):
            with self.subTest(feature=feature):
                self.assertIsNotNone(
                    resident_success_record(
                        {
                            "feature": feature,
                            "state": "dispatched",
                            "success": True,
                            "dispatchAccepted": True,
                            "battleId": 1234,
                        },
                        now_millis=7_400,
                    )
                )

    def test_mine_recall_is_its_own_record_beside_the_expedition(self) -> None:
        """Sending the generals out and getting them back are two facts.

        The round only frees the generals once they are home, but the whole
        驻守/撤防/回闲 half produced nothing the operator could see - the panel
        showed an expedition and then silence.  Both halves key off the same
        battle, so they must not share a dedupe key or only whichever was
        written first would survive.
        """

        dispatched = resident_success_record(
            {
                "feature": "mine",
                "state": "dispatched",
                "success": True,
                "dispatchAccepted": True,
                "battleId": 41511996,
                "sourceRowIndex": 0,
                "target": {"name": "1级镔铁矿", "x": 88, "y": 24},
            },
            now_millis=8_000,
        )
        recalled = resident_success_record(
            {
                "feature": "mine",
                "state": "completed",
                "success": True,
                "recallCompleted": True,
                "occupationOutcome": "recalled",
                "battleId": 41511996,
                "sourceRowIndex": 0,
                "target": {"name": "1级镔铁矿", "x": 88, "y": 24},
            },
            now_millis=9_000,
        )

        self.assertIsNotNone(recalled)
        self.assertEqual("打矿", recalled["category"])
        self.assertEqual(
            "编队1 已撤回 > 1级镔铁矿(88，24)（battleId=41511996）",
            recalled["message"],
        )
        self.assertNotEqual(dispatched["dedupeKey"], recalled["dedupeKey"])
        self.assertEqual("mine:recall:41511996", recalled["dedupeKey"])

        # A lost round never reaches the success list; it is narrated as a
        # failure instead, which is what raises the 提示 page entry.
        self.assertIsNone(
            resident_success_record(
                {
                    "feature": "mine",
                    "state": "completed",
                    "success": False,
                    "occupationFailed": True,
                    "occupationOutcome": "failed",
                    "battleId": 41511997,
                },
                now_millis=9_100,
            )
        )

    def test_operation_history_recovers_unrecorded_mine_expeditions(
        self,
    ) -> None:
        """The ledger kept the打矿 evidence the record page never read."""

        recovered = resident_success_records_from_operation_facts(
            [{
                "accountRef": "202",
                "status": "SUCCEEDED",
                "completedAtMillis": 7_500,
                "result": {
                    "feature": "mine",
                    "state": "dispatched",
                    "success": True,
                    "dispatchAccepted": True,
                    "battleId": 41472667,
                    "target": {"name": "1级镔铁矿", "x": 91, "y": 26},
                },
            }],
            account_ref="202",
        )

        self.assertEqual(1, len(recovered))
        self.assertEqual("打矿", recovered[0]["category"])
        self.assertEqual("mine:battle:41472667", recovered[0]["dedupeKey"])

    def test_operation_history_recovers_pre_upgrade_daily_success(self) -> None:
        recovered = resident_success_records_from_operation_facts(
            [{
                "accountRef": "202",
                "status": "SUCCEEDED",
                "completedAtMillis": 7_500,
                "result": {
                    "feature": "daily",
                    "dailyKey": "arenaCoins",
                    "cycleKey": 88,
                    "state": "completed",
                    "success": True,
                    "message": "铜钱:200000获得成功。竞技币:300获得成功。",
                },
            }],
            account_ref="202",
        )

        self.assertEqual(1, len(recovered))
        self.assertEqual("领币", recovered[0]["category"])
        self.assertEqual("daily:arenaCoins:88", recovered[0]["dedupeKey"])

    def test_operation_history_upgrades_old_vague_brush_and_lossless_records(self) -> None:
        public_state = {
            "residentAutomationConfigJson": json.dumps({
                "common": {
                    "brush": {
                        "rules": [{
                            "sourceRowIndex": 0,
                            "generalId": "1826335",
                            "generalIds": ["1826335", "1826336"],
                            "formations": [{
                                "generalId": "1826335",
                                "sourceRowIndex": 2,
                            }, {
                                "generalId": "1826336",
                                "sourceRowIndex": 1,
                            }],
                        }],
                    },
                },
            }, ensure_ascii=False),
        }
        facts = [{
            "accountRef": "202",
            "status": "SUCCEEDED",
            "completedAtMillis": 7_000,
            "result": {
                "feature": "brush",
                "state": "dispatched",
                "success": True,
                "dispatchAccepted": True,
                "battleId": 19432238,
                "sourceRowIndex": 0,
                "tickAtMillis": 7_000,
                "target": {
                    "name": "8级山贼",
                    "x": 86,
                    "y": 26,
                },
            },
        }, {
            "accountRef": "202",
            "status": "SUCCEEDED",
            "completedAtMillis": 7_100,
            "result": {
                "feature": "lossless",
                "state": "fighting",
                "success": True,
                "dispatchAccepted": True,
                "battleId": 19428377,
                "tickAtMillis": 7_100,
                "stage": {"level": 9, "stageName": "首领"},
            },
        }]
        recovered = resident_success_records_from_operation_facts(
            facts,
            account_ref="202",
            public_state=public_state,
        )
        projected = project_success_records({
            "accountRef": "202",
            "records": [{
                "id": 72,
                "time": 7_200,
                "category": "刷黄",
                "message": "共享核心出征 > 8级山贼",
                "detail": {
                    "feature": "brush",
                    "battleId": 19432238,
                    "target": {"name": "8级山贼"},
                },
            }, {
                "id": 73,
                "time": 7_300,
                "category": "无损",
                "message": "共享核心出征 > 目标",
                "detail": {
                    "feature": "lossless",
                    "battleId": 19428377,
                },
            }, *recovered],
        })
        by_category = {
            row["category"]: row for row in projected["entries"]
        }
        self.assertEqual(
            by_category["刷黄"]["message"],
            "编队1 > 8级山贼(86，26)（battleId=19432238）",
        )
        self.assertEqual(by_category["刷黄"]["time"], 7_200)
        self.assertEqual(by_category["无损"]["message"], "9级-首领")
        self.assertEqual(by_category["无损"]["time"], 7_300)
        self.assertEqual(len(projected["entries"]), 2)

    def test_success_record_projection_repairs_old_brush_display_number(self) -> None:
        projected = project_success_records({
            "accountRef": "202",
            "records": [{
                "id": 74,
                "time": 7_400,
                "sessionId": "202",
                "category": "刷黄",
                "message": "编队4 > 8级山贼(95，13)（battleId=20834092）",
                "detail": {
                    "feature": "brush",
                    "battleId": 20834092,
                    "formationNumber": 4,
                    "formationSourceRowIndex": 3,
                    "ruleSourceRowIndex": 1,
                    "target": {"name": "8级山贼", "x": 95, "y": 13},
                },
            }],
        })

        record = projected["entries"][0]
        self.assertEqual(
            record["message"],
            "编队2 > 8级山贼(95，13)（battleId=20834092）",
        )
        self.assertEqual(record["detail"]["formationNumber"], 2)
        self.assertEqual(record["detail"]["formationSourceRowIndex"], 3)

    def test_shared_local_write_plans_validate_without_touching_network(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        account_log = facade.dispatch(
            "POST",
            "/api/logs/account",
            {
                "sessionId": "7",
                "message": "  用户   点击保存  ",
                "level": "warning",
                "source": "web",
            },
        )
        clear = facade.dispatch("POST", "/api/logs/system/clear", {})
        dismiss = facade.dispatch(
            "POST",
            "/api/notices/dismiss",
            {"sessionId": "7", "noticeKey": "runtime:lossless:1"},
        )
        invalid = facade.dispatch(
            "POST",
            "/api/logs/account",
            {"sessionId": "7", "message": "   "},
        )

        self.assertEqual(account_log.status, 200)
        self.assertFalse(account_log.body["plan"]["networkRequired"])
        self.assertEqual(account_log.body["plan"]["write"]["message"], "用户 点击保存")
        self.assertEqual(account_log.body["plan"]["write"]["level"], "warn")
        self.assertTrue(clear.body["plan"]["clearSystemLogs"])
        self.assertEqual(dismiss.body["plan"]["write"]["noticeKey"], "runtime:lossless:1")
        self.assertEqual(invalid.status, 400)
        self.assertEqual(facade.operations_snapshot()["count"], 0)
        facade.close()

    def test_shared_automation_status_sorts_and_bounds_host_snapshots(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        response = facade.dispatch(
            "GET",
            "/api/automation/status",
            {
                "tasks": [
                    {"taskId": str(index), "createdAt": index}
                    for index in range(12)
                ],
                "assistantOperations": [{"id": "op-1"}],
                "taskOverview": {"savedTasksStarted": False},
            },
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(len(response.body["tasks"]), 10)
        self.assertEqual(response.body["tasks"][0]["taskId"], "11")
        self.assertEqual(response.body["assistantOperations"], [{"id": "op-1"}])
        facade.close()

    def test_shared_map_views_project_identical_desktop_and_android_facts(self) -> None:
        now = 20_000_000
        facade = CoreFacade(
            ROOT / "shared_core",
            ports=PlatformPorts(clock=FixedClock(now)),
        )
        common_bandit = {
            "targetId": 101,
            "x": 11,
            "y": 21,
            "type": "山贼",
            "level": 3,
            "firstDiscoveredAtMillis": now - 1_000,
            "lastValidatedAtMillis": now - 500,
            "active": True,
            "status": "reserved",
            "filterFields": {
                "name": "3级山贼",
                "compositionCode": "3210",
                "resource": "资源、装备",
                "dropCategories": '["资源", "装备"]',
                "lootIds": "[12, 13]",
            },
        }
        android_bandits = facade.dispatch(
            "GET",
            "/api/maps/bandits",
            {
                "serverKey": "qzone_351",
                "records": [
                    common_bandit,
                    {
                        **common_bandit,
                        "targetId": 102,
                        "lastValidatedAtMillis": now - 1_800_001,
                    },
                    {**common_bandit, "targetId": 103, "active": False},
                ],
            },
        )
        desktop_bandits = facade.dispatch(
            "GET",
            "/api/maps/bandits",
            {
                "serverKey": "qzone_351",
                "records": [{
                    "id": 101,
                    "idHex": "65",
                    "name": "3级山贼",
                    "level": 3,
                    "x": 11,
                    "y": 21,
                    "compositionCode": "3210",
                    "resource": "资源、装备",
                    "dropCategories": ["资源", "装备"],
                    "lootIds": [12, 13],
                    "firstDiscoveredAt": now - 1_000,
                    "updatedAt": now - 500,
                    "status": "reserved",
                }],
            },
        )

        common_mine = {
            "targetId": 201,
            "x": 12,
            "y": 22,
            "type": "CRYSTAL",
            "level": 5,
            "firstDiscoveredAtMillis": now - 1_000,
            "lastValidatedAtMillis": now - 500,
            "active": True,
            "status": "dispatched",
            "filterFields": {
                "name": "5级水晶矿",
                "kind": "水晶矿",
                "businessId": "2",
                "typeCode": "2",
                "reserve": "800",
                "playerOccupied": "false",
                "defenseCount": "2",
            },
        }
        android_mines = facade.dispatch(
            "GET",
            "/api/maps/mines",
            {"serverKey": "qzone_351", "records": [common_mine]},
        )
        desktop_mines = facade.dispatch(
            "GET",
            "/api/maps/mines",
            {
                "serverKey": "qzone_351",
                "records": [{
                    "id": 201,
                    "idHex": "c9",
                    "name": "5级水晶矿",
                    "kind": "水晶矿",
                    "protocolKind": "CRYSTAL",
                    "businessId": 2,
                    "typeCode": 2,
                    "level": 5,
                    "x": 12,
                    "y": 22,
                    "amountA": 800,
                    "playerOccupied": False,
                    "defenderCount": 2,
                    "firstDiscoveredAt": now - 1_000,
                    "updatedAt": now - 500,
                    "status": "dispatched",
                }],
            },
        )

        self.assertEqual(android_bandits.status, 200)
        self.assertEqual(android_bandits.body["points"], desktop_bandits.body["points"])
        self.assertEqual(len(android_bandits.body["points"]), 1)
        self.assertTrue(android_bandits.body["points"][0]["selectedForAttack"])
        self.assertEqual(android_bandits.body["ttlMs"], 1_800_000)
        self.assertEqual(android_mines.body["points"], desktop_mines.body["points"])
        self.assertEqual(android_mines.body["points"][0]["remainingMs"], 10_799_500)
        self.assertEqual(android_mines.body["ttlMs"], 10_800_000)
        facade.close()

    def test_brush_center_recommendation_is_shared_local_and_deterministic(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        response = facade.dispatch(
            "POST",
            "/api/brush/recommended-center",
            {
                "generalIds": ["11", "12", "13"],
                "roleLevel": 42,
                "enforceRoleLevel": True,
                "generals": [
                    {"id": 11, "name": "甲", "fiefId": 1001},
                    {"idHex": "0c", "name": "乙", "placeID": 1001},
                    {
                        "id": 13,
                        "name": "丙",
                        "placeId": 1002,
                        "raw": {"fiefX": 30, "fiefY": 40},
                    },
                ],
                "fiefs": [{
                    "targetId": 1001,
                    "fiefName": "都城",
                    "cityName": "洛阳",
                    "x": 190,
                    "y": 60,
                }],
            },
        )

        self.assertEqual(response.status, 200)
        self.assertEqual((response.body["x"], response.body["y"]), (186, 55))
        self.assertEqual(response.body["fiefId"], 1001)
        self.assertEqual(response.body["fiefCounts"], {"1001": 2, "1002": 1})
        self.assertEqual(
            [row["generalId"] for row in response.body["selectedGenerals"]],
            ["11", "12", "13"],
        )
        self.assertEqual(response.body["source"], "login-owned-fief-cache")
        self.assertEqual(facade.operations_snapshot()["count"], 0)

        low_level = facade.dispatch(
            "POST",
            "/api/brush/recommended-center",
            {
                "generalIds": ["11"],
                "roleLevel": 29,
                "enforceRoleLevel": True,
                "generals": [{"id": 11, "name": "甲", "fiefId": 1001}],
                "fiefs": [{"targetId": 1001, "x": 1, "y": 2}],
            },
        )
        self.assertEqual(low_level.status, 400)
        self.assertIn("30级", low_level.body["error"])
        facade.close()

    def test_core_health_reports_deterministic_source_identity(self) -> None:
        first = CoreFacade(ROOT / "shared_core").health()
        second = CoreFacade(ROOT / "shared_core").health()

        self.assertTrue(first["ok"])
        self.assertEqual(first["core"], CORE_ID)
        self.assertEqual(first["coreVersion"], CORE_VERSION)
        self.assertRegex(first["coreHash"], r"^[0-9a-f]{64}$")
        self.assertEqual(first["coreHash"], second["coreHash"])
        self.assertEqual(first["coreHash"], compute_core_hash(ROOT / "shared_core"))
        self.assertEqual(first["sharedRouteCount"], 56)
        self.assertEqual(first["localRouteCount"], 27)
        self.assertEqual(first["networkOperationRouteCount"], 29)
        self.assertEqual(first["operationModel"]["submission"], "immediate")

    def test_health_json_is_a_stable_android_bridge_contract(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")

        self.assertEqual(json.loads(facade.health_json()), facade.health())

    def test_hash_is_path_independent_and_content_sensitive(self) -> None:
        first = hash_records((("core/a.py", b"one"), ("contract.json", b"two")))
        reordered = hash_records((("contract.json", b"two"), ("core/a.py", b"one")))
        changed = hash_records((("core/a.py", b"ONE"), ("contract.json", b"two")))

        self.assertEqual(first, reordered)
        self.assertNotEqual(first, changed)

    def test_manifest_contains_only_relative_deterministic_sources(self) -> None:
        manifest = source_manifest(ROOT / "shared_core")

        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertRegex(manifest["coreHash"], r"^[0-9a-f]{64}$")
        self.assertIn("python/dwpm_core/facade.py", manifest["files"])
        self.assertIn("assistant_behavior_contract.json", manifest["files"])
        self.assertTrue(all(not path.startswith("/") for path in manifest["files"]))

    def test_dispatch_serves_migrated_routes_and_fails_closed_for_the_rest(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")

        health = facade.dispatch_local("GET", "/api/health?probe=1")
        accounts = facade.dispatch_local("GET", "/api/accounts")
        settings = facade.dispatch_local(
            "GET",
            "/api/accounts/settings",
            {
                "account": {"sessionId": "202"},
                "settings": {},
                "exists": True,
            },
        )
        unmigrated = facade.dispatch(
            "POST",
            "/api/accounts/add",
            {"accountRef": "pending-login"},
            {"requestId": "unmigrated-account-add"},
        )

        self.assertEqual(health.status, 200)
        self.assertTrue(health.body["ok"])
        self.assertEqual(accounts.status, 200)
        self.assertEqual(accounts.body, {"ok": True, "accounts": []})
        self.assertEqual(settings.status, 200)
        self.assertTrue(settings.body["ok"])
        self.assertEqual(unmigrated.status, 501)
        self.assertEqual(unmigrated.body["code"], "ROUTE_NOT_MIGRATED")
        self.assertIn("not migrated", unmigrated.body["error"])

    def test_account_stop_and_delete_are_shared_local_write_plans(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        try:
            missing = facade.dispatch("POST", "/api/accounts/stop", {})
            stopped = facade.dispatch(
                "POST",
                "/api/accounts/stop",
                {"sessionId": "202", "reason": "用户点击停止"},
            )
            deleted = facade.dispatch(
                "POST",
                "/api/accounts/delete",
                {"accountRef": "202"},
            )

            self.assertEqual(missing.status, 400)
            self.assertEqual(stopped.status, 200)
            stop_write = stopped.body["plan"]["write"]
            self.assertFalse(stopped.body["plan"]["networkRequired"])
            self.assertFalse(stop_write["enabled"])
            self.assertFalse(stop_write["savedTasksStarted"])
            self.assertEqual(stop_write["loginState"], "REAL_PROTOCOL_STOPPED")
            delete_write = deleted.body["plan"]["write"]
            self.assertTrue(delete_write["deleteCredentialFirst"])
            self.assertEqual(delete_write["deleteStores"][0], "account")
            self.assertIn("localMaps", delete_write["deleteStores"])
        finally:
            facade.close()

    def test_dispatch_json_is_the_same_host_neutral_entry_point(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")

        direct = facade.dispatch("GET", "/api/health")
        bridged = json.loads(
            facade.dispatch_json("GET", "/api/health", "{}", "{}")
        )

        self.assertEqual(bridged, direct.to_dict())
        self.assertEqual(direct.status, 200)
        self.assertEqual(
            direct.body["operationModel"]["networkLane"],
            "per-account",
        )
        self.assertEqual(
            direct.body["operationModel"]["localLane"],
            "direct",
        )
        facade.close()

    def test_long_network_operation_never_blocks_local_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            facade = CoreFacade(
                ROOT / "shared_core",
                str(Path(directory) / "operations.json"),
            )
            started = threading.Event()

            def slow_query(body, context, execution):
                started.set()
                execution.wait(0.25)
                return {"ok": True, "refreshed": True}

            facade.register_network_route(
                "GET",
                "/api/state/refresh",
                slow_query,
            )
            submitted_at = time.perf_counter()
            accepted = facade.dispatch(
                "GET",
                "/api/state/refresh",
                {"accountRef": "account-a"},
                {"requestId": "refresh-a-1"},
            )
            submit_millis = (time.perf_counter() - submitted_at) * 1000
            self.assertEqual(accepted.status, 202)
            self.assertLess(submit_millis, 100)
            self.assertTrue(started.wait(1))

            latencies = []
            for _ in range(20):
                local_started = time.perf_counter()
                local = facade.dispatch(
                    "GET",
                    "/api/accounts/settings",
                    {
                        "account": {"sessionId": "202"},
                        "settings": {"local": True},
                    },
                )
                latencies.append((time.perf_counter() - local_started) * 1000)
                self.assertEqual(local.status, 200)
            self.assertLess(max(latencies), 100)

            operation_id = accepted.body["operationId"]
            final = self.wait_for_operation(facade, operation_id)
            self.assertEqual(final["status"], "SUCCEEDED")
            facade.close()

    def test_network_lanes_serialize_one_account_and_parallelize_accounts(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        release = threading.Event()
        a1_started = threading.Event()
        a2_started = threading.Event()
        b1_started = threading.Event()
        events = []
        events_lock = threading.Lock()

        def lane_probe(body, context, execution):
            label = body["label"]
            with events_lock:
                events.append(("start", label, time.monotonic()))
            {"a1": a1_started, "a2": a2_started, "b1": b1_started}[label].set()
            if label in {"a1", "b1"}:
                while not release.wait(0.02):
                    execution.raise_if_cancelled()
            with events_lock:
                events.append(("end", label, time.monotonic()))
            return {"ok": True, "label": label}

        facade.register_network_route(
            "GET",
            "/api/state/refresh",
            lane_probe,
        )

        def submit(account: str, label: str):
            return facade.dispatch(
                "GET",
                "/api/state/refresh",
                {"accountRef": account, "label": label},
                {"requestId": f"lane-{label}"},
            )

        a1 = submit("account-a", "a1")
        self.assertTrue(a1_started.wait(1))
        a2 = submit("account-a", "a2")
        b1 = submit("account-b", "b1")
        self.assertTrue(b1_started.wait(1))
        self.assertFalse(a2_started.wait(0.05))
        release.set()
        for response in (a1, a2, b1):
            final = self.wait_for_operation(facade, response.body["operationId"])
            self.assertEqual(final["status"], "SUCCEEDED")
        self.assertTrue(a2_started.is_set())

        times = {(phase, label): stamp for phase, label, stamp in events}
        self.assertGreaterEqual(times[("start", "a2")], times[("end", "a1")])
        self.assertLess(times[("start", "b1")], times[("end", "a1")])
        facade.close()

    def test_active_query_clicks_coalesce_but_completed_refresh_can_run_again(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        started = threading.Event()
        release = threading.Event()
        executions = []

        def query(body, context, execution):
            executions.append(body["scope"])
            started.set()
            while not release.wait(0.01):
                execution.raise_if_cancelled()
            return {"ok": True, "scope": body["scope"]}

        facade.register_network_route("GET", "/api/state/refresh", query)
        first = facade.dispatch(
            "GET",
            "/api/state/refresh",
            {"accountRef": "account-a", "scope": "military"},
            {"requestId": "coalesce-1"},
        )
        self.assertTrue(started.wait(1))
        duplicate = facade.dispatch(
            "GET",
            "/api/state/refresh",
            {"accountRef": "account-a", "scope": "military"},
            {"requestId": "coalesce-2"},
        )

        self.assertEqual(first.body["operationId"], duplicate.body["operationId"])
        self.assertTrue(duplicate.body["deduplicated"])
        self.assertEqual(executions, ["military"])
        release.set()
        self.assertEqual(
            self.wait_for_operation(facade, first.body["operationId"])["status"],
            "SUCCEEDED",
        )

        repeated = facade.dispatch(
            "GET",
            "/api/state/refresh",
            {"accountRef": "account-a", "scope": "military"},
            {"requestId": "coalesce-3"},
        )
        self.assertNotEqual(first.body["operationId"], repeated.body["operationId"])
        self.assertFalse(repeated.body["deduplicated"])
        self.assertEqual(
            self.wait_for_operation(facade, repeated.body["operationId"])["status"],
            "SUCCEEDED",
        )
        self.assertEqual(executions, ["military", "military"])
        facade.close()

    def test_sent_mutation_timeout_becomes_uncertain_and_is_not_replayed(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        executions = []

        def uncertain_mutation(body, context, execution):
            executions.append(body["targetId"])
            execution.mark_request_sent({"opcode": "0x1522"})
            raise RuntimeError("game reply timed out")

        facade.register_network_route(
            "POST",
            "/api/brush/execute",
            uncertain_mutation,
        )
        first = facade.dispatch(
            "POST",
            "/api/brush/execute",
            {"accountRef": "account-a", "targetId": 123},
            {"requestId": "brush-uncertain-1"},
        )
        final = self.wait_for_operation(facade, first.body["operationId"])
        self.assertEqual(final["status"], "UNCERTAIN")
        self.assertTrue(final["requestSent"])

        duplicate = facade.dispatch(
            "POST",
            "/api/brush/execute",
            {"accountRef": "account-a", "targetId": 123},
            {"requestId": "brush-uncertain-1"},
        )
        self.assertEqual(duplicate.body["operationId"], first.body["operationId"])
        self.assertTrue(duplicate.body["deduplicated"])
        self.assertEqual(executions, [123])
        facade.close()

    def test_queued_operation_can_cancel_but_sent_mutation_cannot(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        first_started = threading.Event()
        sent_started = threading.Event()
        release = threading.Event()

        def controlled(body, context, execution):
            if body["label"] == "first":
                first_started.set()
            if body.get("sent"):
                execution.mark_request_sent({"opcode": "0x1522"})
                sent_started.set()
            while not release.wait(0.02):
                execution.raise_if_cancelled()
            return {"ok": True}

        facade.register_network_route(
            "POST",
            "/api/brush/execute",
            controlled,
        )
        first = facade.dispatch(
            "POST",
            "/api/brush/execute",
            {"accountRef": "account-a", "label": "first", "sent": True},
            {"requestId": "cancel-first"},
        )
        self.assertTrue(first_started.wait(1))
        self.assertTrue(sent_started.wait(1))
        queued = facade.dispatch(
            "POST",
            "/api/brush/execute",
            {"accountRef": "account-a", "label": "queued", "sent": False},
            {"requestId": "cancel-queued"},
        )

        queued_cancelled = facade.cancel_operation(queued.body["operationId"])
        sent_cancel = facade.cancel_operation(first.body["operationId"])
        self.assertEqual(
            queued_cancelled["operation"]["status"],
            "CANCELLED",
        )
        self.assertEqual(sent_cancel["operation"]["status"], "RUNNING")
        self.assertEqual(
            sent_cancel["operation"]["cancellationDenied"],
            "request-already-sent",
        )
        release.set()
        self.assertEqual(
            self.wait_for_operation(facade, first.body["operationId"])["status"],
            "SUCCEEDED",
        )
        facade.close()

    def test_recovery_marks_sent_running_mutation_uncertain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "operations.json"
            ledger.write_text(
                json.dumps(
                    {
                        "schemaVersion": 2,
                        "operations": [
                            {
                                "operationId": "op_recovery_sent",
                                "kind": "route:POST:/api/brush/execute",
                                "operationType": "mutation",
                                "accountRef": "account-a",
                                "idempotencyKey": "recovery-sent-1",
                                "status": "RUNNING",
                                "submittedAtMillis": 100,
                                "startedAtMillis": 110,
                                "updatedAtMillis": 120,
                                "completedAtMillis": None,
                                "payload": {"body": {"targetId": 1}},
                                "progress": 50,
                                "progressDetails": None,
                                "requestSent": True,
                                "requestSentAtMillis": 115,
                                "requestMetadata": {"opcode": "0x1522"},
                                "cancelRequested": False,
                                "result": None,
                                "error": None,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            facade = CoreFacade(ROOT / "shared_core", str(ledger))
            recovered = facade.operation_status("op_recovery_sent")["operation"]

            self.assertEqual(recovered["status"], "UNCERTAIN")
            self.assertEqual(
                recovered["error"]["code"],
                "RECOVERED_AFTER_REQUEST_SENT",
            )
            facade.close()

    def test_operation_ledger_rejects_sensitive_fields(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        facade.register_network_route(
            "POST",
            "/api/accounts/add",
            lambda body, context, execution: {"ok": True},
        )

        response = facade.dispatch(
            "POST",
            "/api/accounts/add",
            {
                "accountRef": "new-account",
                "username": "user",
                "password": "must-not-persist",
            },
            {"requestId": "add-sensitive-1"},
        )

        self.assertEqual(response.status, 400)
        self.assertIn("sensitive field", response.body["error"])
        self.assertEqual(facade.operations_snapshot()["count"], 0)
        facade.close()

    def test_explicit_uncertain_error_preserves_structured_evidence(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")

        def uncertain_query(body, context, execution):
            raise OperationUncertainError(
                "response frame incomplete",
                {"opcode": "0x8600"},
            )

        facade.register_network_route(
            "GET",
            "/api/military/intel",
            uncertain_query,
        )
        accepted = facade.dispatch(
            "GET",
            "/api/military/intel",
            {"accountRef": "account-a"},
            {"requestId": "intel-uncertain-1"},
        )
        final = self.wait_for_operation(facade, accepted.body["operationId"])
        self.assertEqual(final["status"], "UNCERTAIN")
        self.assertEqual(final["error"]["details"]["opcode"], "0x8600")
        facade.close()

    def test_operation_events_use_the_independent_platform_event_port(self) -> None:
        class CaptureEvents:
            def __init__(self):
                self.rows = []

            def publish(self, event):
                self.rows.append(dict(event))

        events = CaptureEvents()
        facade = CoreFacade(
            ROOT / "shared_core",
            ports=PlatformPorts(events=events),
        )
        facade.register_network_route(
            "GET",
            "/api/state/refresh",
            lambda body, context, execution: {"ok": True},
        )
        accepted = facade.dispatch(
            "GET",
            "/api/state/refresh",
            {"accountRef": "account-a"},
            {"requestId": "events-1"},
        )
        self.wait_for_operation(facade, accepted.body["operationId"])
        event_types = {row["type"] for row in events.rows}
        self.assertIn("operation.accepted", event_types)
        self.assertIn("operation.started", event_types)
        self.assertIn("operation.completed", event_types)
        facade.close()

    def test_operation_events_expose_progress_send_and_cancel_boundaries(self) -> None:
        class CaptureEvents:
            def __init__(self):
                self.rows = []

            def publish(self, event):
                self.rows.append(dict(event))

        events = CaptureEvents()
        request_sent = threading.Event()
        release = threading.Event()

        def mutation(body, context, execution):
            execution.publish_progress(37, {"phase": "preparing-command"})
            execution.mark_request_sent({"opcode": "0x1522"})
            request_sent.set()
            self.assertTrue(release.wait(1))
            return {"ok": True}

        facade = CoreFacade(
            ROOT / "shared_core",
            ports=PlatformPorts(events=events),
        )
        facade.register_network_route("POST", "/api/brush/execute", mutation)
        accepted = facade.dispatch(
            "POST",
            "/api/brush/execute",
            {"accountRef": "account-a", "targetId": 7},
            {"requestId": "event-boundaries-1"},
        )
        self.assertTrue(request_sent.wait(1))
        denied = facade.cancel_operation(accepted.body["operationId"])
        self.assertEqual(
            denied["operation"]["cancellationDenied"],
            "request-already-sent",
        )
        release.set()
        self.assertEqual(
            self.wait_for_operation(facade, accepted.body["operationId"])["status"],
            "SUCCEEDED",
        )

        progress = next(row for row in events.rows if row["type"] == "operation.progress")
        sent = next(row for row in events.rows if row["type"] == "operation.request-sent")
        cancel_denied = next(
            row for row in events.rows if row["type"] == "operation.cancel-denied"
        )
        self.assertEqual(progress["progress"], 37)
        self.assertEqual(progress["progressDetails"], {"phase": "preparing-command"})
        self.assertFalse(progress["requestSent"])
        self.assertTrue(sent["requestSent"])
        self.assertEqual(
            cancel_denied["cancellationDenied"],
            "request-already-sent",
        )
        facade.close()

    def test_simulated_network_operation_is_immediate_and_idempotent(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        started = time.perf_counter()

        submitted = facade.submit_simulated_network_operation(
            2_000,
            "shared-core-test-immediate",
            {"probe": "offline-only"},
        )
        elapsed_millis = (time.perf_counter() - started) * 1000
        duplicate = facade.submit_simulated_network_operation(
            2_000,
            "shared-core-test-immediate",
            {"probe": "offline-only"},
        )

        self.assertLess(elapsed_millis, 100)
        self.assertTrue(submitted["accepted"])
        self.assertFalse(submitted["deduplicated"])
        self.assertTrue(duplicate["deduplicated"])
        self.assertEqual(submitted["operationId"], duplicate["operationId"])
        with self.assertRaisesRegex(ValueError, "different input"):
            facade.submit_simulated_network_operation(
                2_000,
                "shared-core-test-immediate",
                {"probe": "different-input"},
            )
        self.assertTrue(facade.health()["ok"])
        self.assertEqual(
            facade.operation_status(submitted["operationId"])["operation"]["status"],
            "RUNNING",
        )
        cancelled = facade.cancel_operation(submitted["operationId"])
        self.assertEqual(cancelled["operation"]["status"], "CANCELLED")
        facade.close()

    def test_shared_raw_inventory_open_workflow_owns_precheck_and_terminal_semantics(self) -> None:
        def inventory_payload(*items: tuple[int, int]) -> bytes:
            return (
                b"\x00" * 14
                + struct.pack(">HH", 40, len(items))
                + b"".join(
                    struct.pack(">HH", item_id, count) + b"\x00" * 8
                    for item_id, count in items
                )
                + b"\x00\x00"
            )

        def status_payload(status: int, message: str) -> bytes:
            encoded = message.encode("utf-8")
            return struct.pack(">bH", status, len(encoded)) + encoded

        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self, ledger: Path, outcome: str) -> None:
                self.ledger = ledger
                self.outcome = outcome
                self.acquired = 0
                self.released = 0
                self.commands = []
                self.inventory_queries = 0

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                self.acquired += 1
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                self.released += 1
                self.released_account = account_ref

            def executeNetworkOperation(self, *_args):
                raise AssertionError("inventory workflow must use raw commands")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                context = json.loads(context_json)
                opcode = int(command["opcode"])
                payload_hex = str(command["payloadHex"])
                self.commands.append((opcode, payload_hex, command["phase"]))
                if opcode == 0x1104:
                    self.inventory_queries += 1
                    if self.outcome == "post-refresh-crash" and self.inventory_queries == 2:
                        raise RuntimeError("post-refresh disconnected")
                    if self.outcome == "missing-item":
                        packet_payload = inventory_payload()
                    elif self.outcome == "missing-key":
                        packet_payload = inventory_payload((58, 3))
                    else:
                        packet_payload = inventory_payload((58, 3), (59, 1))
                    packets = [{"opcode": 0x8104, "payloadHex": packet_payload.hex()}]
                elif opcode == 0x3144:
                    ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
                    record = next(
                        row for row in ledger["operations"]
                        if row["operationId"] == context["operationId"]
                    )
                    if not record["requestSent"]:
                        raise AssertionError(
                            "requestSent must be durable before inventory mutation"
                        )
                    if self.outcome == "send-crash":
                        raise RuntimeError("socket closed after inventory send")
                    if self.outcome == "missing-receipt":
                        packets = [{"opcode": 0x880D, "payloadHex": "00"}]
                    else:
                        rejected = self.outcome == "rejected"
                        packets = [{
                            "opcode": 0xA144,
                            "payloadHex": status_payload(
                                1 if rejected else 0,
                                "服务器拒绝" if rejected else "<br/>铜钱+1000;",
                            ).hex(),
                        }]
                else:
                    raise AssertionError(f"unexpected raw opcode {opcode:#x}")
                return json.dumps({
                    "status": 200,
                    "body": {
                        "ok": True,
                        "gameCommandFact": {
                            "requestOpcode": opcode,
                            "httpCode": 200,
                            "httpOk": True,
                            "responseBytes": sum(
                                len(row["payloadHex"]) // 2 for row in packets
                            ),
                            "packets": packets,
                        },
                    },
                }, ensure_ascii=False)

        def live_account(facade: CoreFacade) -> None:
            facade.account_record_upsert({
                "accountRef": "202",
                "id": 202,
                "username": "fixture",
                "serverName": "fixture",
                "enabled": True,
                "loginState": "REAL_PROTOCOL_ONLINE",
                "session": {
                    "accountId": 202,
                    "sourceMode": 1,
                    "publicState": {
                        "roleId": 202,
                        "gameHttp": FIXTURE_GAME_HTTP,
                        "lastValidatedAt": "1000",
                    },
                },
            })

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            validation_ledger = root / "inventory-validation.json"
            validation_bridge = HostBridge(validation_ledger, "success")
            validation_facade = create_hosted_core(
                str(validation_ledger),
                validation_bridge,
            )
            try:
                live_account(validation_facade)
                for body in (
                    {"accountRef": "202", "itemName": "青铜宝箱"},
                    {
                        "accountRef": "202",
                        "confirm": "open-one",
                        "itemName": "未授权道具",
                    },
                ):
                    rejected = validation_facade.dispatch(
                        "POST",
                        "/api/inventory/open-one",
                        body,
                        {"requestId": "inventory-invalid", "platform": "android"},
                    )
                    self.assertEqual(rejected.status, 400)
                self.assertEqual(validation_bridge.acquired, 0)
                self.assertEqual(validation_bridge.commands, [])
                self.assertEqual(validation_facade.operations_snapshot()["count"], 0)
            finally:
                validation_facade.close()

            for outcome, expected in (
                ("success", "SUCCEEDED"),
                ("post-refresh-crash", "SUCCEEDED"),
                ("missing-item", "FAILED"),
                ("missing-key", "FAILED"),
                ("rejected", "FAILED"),
                ("missing-receipt", "UNCERTAIN"),
                ("send-crash", "UNCERTAIN"),
            ):
                ledger = root / f"inventory-{outcome}.json"
                bridge = HostBridge(ledger, outcome)
                facade = create_hosted_core(str(ledger), bridge)
                try:
                    live_account(facade)
                    accepted = facade.dispatch(
                        "POST",
                        "/api/inventory/open-one",
                        {
                            "accountRef": "202",
                            "confirm": "open-one",
                            "itemName": "青铜宝箱",
                            "ignored": "do-not-persist",
                        },
                        {"requestId": f"inventory-{outcome}", "platform": "android"},
                    )
                    self.assertEqual(accepted.status, 202)
                    operation = self.wait_for_operation(
                        facade,
                        accepted.body["operationId"],
                    )
                    self.assertEqual(operation["status"], expected)
                    self.assertEqual(bridge.acquired, 1)
                    self.assertEqual(bridge.released, 1)
                    self.assertEqual(bridge.released_account, "202")
                    self.assertEqual(bridge.commands[0][0:2], (0x1104, "00"))
                    self.assertNotIn(
                        "do-not-persist",
                        json.dumps(operation, ensure_ascii=False),
                    )
                    if outcome in {"missing-item", "missing-key"}:
                        self.assertFalse(operation["requestSent"])
                        self.assertEqual(len(bridge.commands), 1)
                        self.assertEqual(
                            operation["error"]["code"],
                            "INVENTORY_OPEN_PRECHECK_FAILED",
                        )
                    else:
                        self.assertTrue(operation["requestSent"])
                        self.assertEqual(bridge.commands[1][0:2], (0x3144, "003a0001"))
                    if outcome == "success":
                        self.assertTrue(operation["result"]["result"]["success"])
                        self.assertEqual(
                            operation["result"]["result"]["raw"]["rewardText"],
                            "铜钱+1000",
                        )
                        self.assertEqual(
                            [row[0] for row in bridge.commands],
                            [0x1104, 0x3144, 0x1104],
                        )
                    if outcome == "post-refresh-crash":
                        self.assertIn("刷新背包失败", operation["result"]["refreshWarning"])
                    if outcome == "rejected":
                        self.assertEqual(
                            operation["error"]["code"],
                            "INVENTORY_OPEN_REJECTED",
                        )
                finally:
                    facade.close()

    def test_android_brush_search_uses_python_raw_commands_filters_and_map_port(self) -> None:
        fixture = json.loads(
            (ROOT / "shared_core" / "protocol_parity_fixtures.json").read_text(
                encoding="utf-8"
            )
        )["fixtures"]["targetSearch8540Complete"]

        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self, ledger: Path, missing_receipt: bool = False) -> None:
                self.ledger = ledger
                self.missing_receipt = missing_receipt
                self.acquired = 0
                self.released = 0
                self.commands = []
                self.snapshots = []

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                self.acquired += 1
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                self.released += 1

            def executeNetworkOperation(self, *_args):
                raise AssertionError("brush search must use Python raw commands")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                context = json.loads(context_json)
                opcode = int(command["opcode"])
                payload_hex = str(command["payloadHex"])
                self.commands.append((opcode, payload_hex, command["phase"]))
                ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
                record = next(
                    row for row in ledger["operations"]
                    if row["operationId"] == context["operationId"]
                )
                if record["requestSent"]:
                    raise AssertionError("read-only search must remain safely cancellable")
                if self.missing_receipt:
                    packets = [{"opcode": 0x880D, "payloadHex": "00"}]
                elif len(self.commands) == 1:
                    packets = [{"opcode": 0x8540, "payloadHex": fixture["responseHex"]}]
                else:
                    packets = [{"opcode": 0x8540, "payloadHex": "00bb003800"}]
                return json.dumps({
                    "status": 200,
                    "body": {
                        "ok": True,
                        "gameCommandFact": {
                            "requestOpcode": opcode,
                            "httpCode": 200,
                            "httpOk": True,
                            "responseBytes": sum(len(row["payloadHex"]) // 2 for row in packets),
                            "packets": packets,
                        },
                    },
                })

            def saveMapSnapshot(self, snapshot_json):
                self.snapshots.append(json.loads(snapshot_json))

            def invalidateMapTarget(self, *_args):
                raise AssertionError("search must not invalidate map targets")

        def live_account(facade: CoreFacade) -> None:
            facade.account_record_upsert({
                "accountRef": "202",
                "id": 202,
                "username": "fixture",
                "serverName": "fixture",
                "enabled": True,
                "loginState": "REAL_PROTOCOL_ONLINE",
                "session": {
                    "accountId": 202,
                    "sourceMode": 1,
                    "publicState": {
                        "gameHttp": FIXTURE_GAME_HTTP,
                        "lastValidatedAt": "1000",
                    },
                },
            })

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "brush-search.json"
            bridge = HostBridge(ledger)
            facade = create_hosted_core(str(ledger), bridge)
            try:
                live_account(facade)
                accepted = facade.dispatch(
                    "POST",
                    "/api/brush/search",
                    {
                        "accountRef": "202",
                        "startX": 90,
                        "startY": 24,
                        "targetKind": "山贼",
                        "levels": [1],
                        "drops": ["资源"],
                        "scanLimit": 2,
                        "ignored": "must-not-persist",
                    },
                    {"requestId": "brush-search-success", "platform": "android"},
                )
                self.assertEqual(accepted.status, 202)
                operation = self.wait_for_operation(facade, accepted.body["operationId"])
                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertFalse(operation["requestSent"])
                self.assertEqual(operation["result"]["count"], 1)
                target = operation["result"]["targets"][0]
                self.assertEqual(target["id"], fixture["expected"]["id"])
                self.assertEqual(target["compositionCode"], "1111")
                self.assertEqual([row[0] for row in bridge.commands], [0x1540, 0x1540])
                self.assertEqual(bridge.commands[0][1], "005a0018")
                self.assertEqual(bridge.acquired, 1)
                self.assertEqual(bridge.released, 1)
                self.assertEqual(len(bridge.snapshots), 1)
                snapshot = bridge.snapshots[0]
                self.assertEqual(snapshot["kind"], "BANDIT")
                self.assertEqual(snapshot["fingerprint"], "90,24|SHAN_ZEI")
                self.assertEqual(snapshot["targets"][0]["targetId"], fixture["expected"]["id"])
                self.assertNotIn("rawRecord", snapshot["targets"][0]["filterFields"])
                self.assertNotIn("must-not-persist", json.dumps(operation, ensure_ascii=False))
            finally:
                facade.close()

            missing_ledger = root / "brush-search-missing.json"
            missing_bridge = HostBridge(missing_ledger, missing_receipt=True)
            missing_facade = create_hosted_core(str(missing_ledger), missing_bridge)
            try:
                live_account(missing_facade)
                accepted = missing_facade.dispatch(
                    "POST",
                    "/api/brush/search",
                    {
                        "accountRef": "202",
                        "startX": 90,
                        "startY": 24,
                        "scanLimit": 1,
                    },
                    {"requestId": "brush-search-missing", "platform": "android"},
                )
                operation = self.wait_for_operation(
                    missing_facade,
                    accepted.body["operationId"],
                )
                self.assertEqual(operation["status"], "FAILED")
                self.assertFalse(operation["requestSent"])
                self.assertEqual(
                    operation["error"]["code"],
                    "BRUSH_SEARCH_RESPONSE_MISSING",
                )
                self.assertEqual(missing_bridge.snapshots, [])
            finally:
                missing_facade.close()

    def test_android_mine_search_uses_python_raw_commands_filters_and_map_port(self) -> None:
        fixture = json.loads(
            (ROOT / "shared_core" / "protocol_parity_fixtures.json").read_text(
                encoding="utf-8"
            )
        )["fixtures"]["mineSearch8542Structured"]

        class HostBridge(RawHttpGameCommandHostMixin):
            def __init__(self, ledger: Path, missing_receipt: bool = False) -> None:
                self.ledger = ledger
                self.missing_receipt = missing_receipt
                self.commands = []
                self.snapshots = []

            def executionOwnerActive(self):
                return True

            def tryAcquireNetworkOperation(self, account_ref):
                return account_ref == "202"

            def releaseNetworkOperation(self, account_ref):
                return None

            def executeNetworkOperation(self, *_args):
                raise AssertionError("mine search must use Python raw commands")

            def executeGameCommand(self, account_ref, command_json, context_json):
                command = json.loads(command_json)
                context = json.loads(context_json)
                self.commands.append(command)
                record = next(
                    row
                    for row in json.loads(self.ledger.read_text(encoding="utf-8"))["operations"]
                    if row["operationId"] == context["operationId"]
                )
                if record["requestSent"]:
                    raise AssertionError("read-only mine search must remain cancellable")
                packets = (
                    [{"opcode": 0x880D, "payloadHex": "00"}]
                    if self.missing_receipt
                    else [{"opcode": 0x8542, "payloadHex": fixture["responseHex"]}]
                )
                return json.dumps({
                    "status": 200,
                    "body": {
                        "ok": True,
                        "gameCommandFact": {
                            "requestOpcode": command["opcode"],
                            "httpCode": 200,
                            "httpOk": True,
                            "packets": packets,
                        },
                    },
                })

            def saveMapSnapshot(self, snapshot_json):
                self.snapshots.append(json.loads(snapshot_json))

            def invalidateMapTarget(self, *_args):
                raise AssertionError("search must not invalidate map targets")

        def live_account(facade: CoreFacade) -> None:
            facade.account_record_upsert({
                "accountRef": "202",
                "id": 202,
                "username": "fixture",
                "serverName": "fixture",
                "enabled": True,
                "loginState": "REAL_PROTOCOL_ONLINE",
                "session": {
                    "accountId": 202,
                    "sourceMode": 1,
                    "publicState": {
                        "gameHttp": FIXTURE_GAME_HTTP,
                        "lastValidatedAt": "1000",
                    },
                },
            })

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "mine-search.json"
            bridge = HostBridge(ledger)
            facade = create_hosted_core(str(ledger), bridge)
            try:
                live_account(facade)
                accepted = facade.dispatch(
                    "POST",
                    "/api/mine/search",
                    {
                        "accountRef": "202",
                        "centerX": 60,
                        "centerY": 24,
                        "scope": "附近",
                        "resourceTypes": ["PASTURE_LV2"],
                        "levels": [2],
                        "onlyEmpty": True,
                        "scanLimit": 1,
                    },
                    {"requestId": "mine-search-success", "platform": "android"},
                )
                self.assertEqual(accepted.status, 202)
                operation = self.wait_for_operation(facade, accepted.body["operationId"])
                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertFalse(operation["requestSent"])
                self.assertEqual(operation["result"]["count"], 1)
                target = operation["result"]["mines"][0]
                self.assertEqual(target["id"], fixture["expected"]["empty"]["id"])
                self.assertEqual(target["mineType"], "PASTURE_LV2")
                self.assertEqual([row["opcode"] for row in bridge.commands], [0x1542])
                self.assertEqual(bridge.commands[0]["payloadHex"], "003c0018")
                self.assertEqual(len(bridge.snapshots), 1)
                self.assertEqual(bridge.snapshots[0]["kind"], "MINE")
                self.assertEqual(
                    bridge.snapshots[0]["fingerprint"],
                    "60,24|PASTURE_LV2|2|附近|true|false",
                )
            finally:
                facade.close()

            missing_ledger = root / "mine-search-missing.json"
            missing_bridge = HostBridge(missing_ledger, missing_receipt=True)
            missing_facade = create_hosted_core(str(missing_ledger), missing_bridge)
            try:
                live_account(missing_facade)
                accepted = missing_facade.dispatch(
                    "POST",
                    "/api/mine/search",
                    {
                        "accountRef": "202",
                        "centerX": 60,
                        "centerY": 24,
                        "scope": "定点",
                        "scanLimit": 1,
                    },
                    {"requestId": "mine-search-missing", "platform": "android"},
                )
                operation = self.wait_for_operation(
                    missing_facade,
                    accepted.body["operationId"],
                )
                self.assertEqual(operation["status"], "FAILED")
                self.assertFalse(operation["requestSent"])
                self.assertEqual(
                    operation["error"]["code"],
                    "MINE_SEARCH_RESPONSE_MISSING",
                )
                self.assertEqual(missing_bridge.snapshots, [])
            finally:
                missing_facade.close()

    def test_simulated_operation_result_survives_facade_recreation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "operations.json"
            first = CoreFacade(ROOT / "shared_core", str(ledger))
            submitted = first.submit_simulated_network_operation(
                40,
                "shared-core-test-recovery",
                {"value": 7},
            )
            first.close()
            time.sleep(0.08)

            recovered = CoreFacade(ROOT / "shared_core", str(ledger))
            status = recovered.operation_status(submitted["operationId"])

            self.assertTrue(status["ok"])
            self.assertEqual(status["operation"]["status"], "SUCCEEDED")
            self.assertEqual(status["operation"]["result"]["echo"], {"value": 7})
            self.assertEqual(recovered.operations_snapshot()["count"], 1)
            recovered.close()

    def test_desktop_health_exposes_the_same_core_hash(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), SERVER.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/api/health",
                timeout=5,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        expected = SERVER.SHARED_PYTHON_CORE.health()
        self.assertEqual(payload["core"], CORE_ID)
        self.assertEqual(payload["coreVersion"], CORE_VERSION)
        self.assertEqual(payload["coreHash"], expected["coreHash"])
        self.assertEqual(payload["sharedRouteCount"], 56)
        self.assertEqual(payload["version"], SERVER.APP_VERSION)

    @staticmethod
    def wait_for_operation(
        facade: CoreFacade,
        operation_id: str,
        timeout: float = 2.0,
    ) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = facade.operation_status(operation_id)
            operation = status.get("operation") or {}
            if operation.get("status") in {
                "SUCCEEDED",
                "FAILED",
                "CANCELLED",
                "UNCERTAIN",
            }:
                return operation
            time.sleep(0.01)
        raise AssertionError(f"operation did not finish: {operation_id}")


if __name__ == "__main__":
    unittest.main()
