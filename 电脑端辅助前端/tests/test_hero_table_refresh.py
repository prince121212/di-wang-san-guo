from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT / "shared_core" / "python"))

from dwpm_core import CoreFacade


class HeroTableRefreshUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = (ROOT / "app.js").read_text(encoding="utf-8")
        cls.styles = (ROOT / "styles.css").read_text(encoding="utf-8")

    def test_general_header_is_green_and_clickable(self) -> None:
        self.assertIn('id="refreshHeroTableBtn"', self.app)
        self.assertIn('class="hero-refresh-head"', self.app)
        self.assertIn(
            ".hero-table-scroll .hero-data-table th.hero-refresh-head",
            self.styles,
        )
        self.assertIn("background: #43aa43;", self.styles)

    def test_click_refreshes_fresh_general_and_fief_state(self) -> None:
        self.assertIn(
            'refreshHeroTableBtn.onclick = () => { void refreshHeroTable(); };',
            self.app,
        )
        self.assertIn('scope: "generals"', self.app)
        self.assertIn("const data = await apiGet(url);", self.app)
        self.assertIn("res.status === 202 && json.operationId", self.app)
        self.assertIn('apiPost("/api/raid/fiefs"', self.app)
        self.assertIn("mergeHeroFiefLocations(", self.app)
        self.assertIn("appState.generals = data.generals", self.app)
        self.assertIn("g.fiefName || g.cityName", self.app)

    def test_partial_failure_keeps_fresh_generals_and_reports_fief_error(self) -> None:
        self.assertIn(
            "将领请求已经成功，封地查询失败不能回滚为旧将领快照",
            self.app,
        )
        self.assertIn("英雄已刷新，封地名称刷新失败", self.app)


class HeroFiefProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.facade = CoreFacade(
            PROJECT_ROOT / "shared_core",
            str(Path(self.directory.name) / "operations.json"),
            account_store_path=str(Path(self.directory.name) / "accounts.json"),
        )
        self.facade.account_record_upsert({
            "accountRef": "176",
            "id": 176,
            "username": "1608600",
            "serverName": "fixture",
            "enabled": True,
            "loginState": "REAL_PROTOCOL_ONLINE",
            "session": {
                "accountId": 176,
                "sourceMode": 1,
                "publicState": {
                    "roleId": 176,
                    "roleName": "宿代苑",
                    "roleStateJson": json.dumps({"roleName": "宿代苑"}),
                    "generalsJson": json.dumps([
                        {"id": 1, "name": "将一", "fiefId": 176},
                        {"id": 2, "name": "将二", "fiefId": 999},
                    ], ensure_ascii=False),
                },
            },
        })

    def tearDown(self) -> None:
        self.facade.close()
        self.directory.cleanup()

    def test_self_fief_query_is_cached_and_projected_into_generals(self) -> None:
        cached = self.facade._remember_owned_fiefs_if_self(
            "176",
            "宿代苑",
            [{
                "targetId": 176,
                "fiefName": "测试封地",
                "cityName": "洛阳",
                "x": 12,
                "y": 34,
            }],
        )

        self.assertTrue(cached)
        projected = self.facade._project_account_public_state("176")
        self.assertEqual(projected["generals"][0]["fiefName"], "测试封地")
        self.assertEqual(projected["generals"][0]["cityName"], "洛阳")
        self.assertEqual(projected["generals"][0]["fiefX"], 12)
        self.assertNotIn("fiefName", projected["generals"][1])

    def test_enemy_fief_query_cannot_overwrite_owned_fief_cache(self) -> None:
        self.facade._remember_owned_fiefs_if_self(
            "176",
            "宿代苑",
            [{"targetId": 176, "fiefName": "本人封地"}],
        )

        cached = self.facade._remember_owned_fiefs_if_self(
            "176",
            "其他玩家",
            [{"targetId": 176, "fiefName": "敌方封地"}],
        )

        self.assertFalse(cached)
        projected = self.facade._project_account_public_state("176")
        self.assertEqual(projected["generals"][0]["fiefName"], "本人封地")


if __name__ == "__main__":
    unittest.main()
