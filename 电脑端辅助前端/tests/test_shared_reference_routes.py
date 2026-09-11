from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHARED_PYTHON = ROOT / "shared_core" / "python"
if str(SHARED_PYTHON) not in sys.path:
    sys.path.insert(0, str(SHARED_PYTHON))

from dwpm_core.facade import CoreFacade  # noqa: E402
from dwpm_core.reference import (  # noqa: E402
    guide_reference_payload,
    project_area_catalog,
)


class SharedReferenceRouteTests(unittest.TestCase):
    def test_area_catalog_normalizes_deduplicates_and_sorts_host_facts(self) -> None:
        result = project_area_catalog({
            "platform": "三国联盟",
            "updatedAt": 1234,
            "areas": [
                {
                    "target": "2",
                    "areaId": "352",
                    "areaName": "352区",
                    "serverUrl": "https://game-352",
                    "serverKey": "qzone_352",
                },
                {
                    "target": "1",
                    "areaId": "351",
                    "areaName": "351区",
                    "serverUrl": "https://game-351",
                    "serverKey": "qzone_351",
                },
                {
                    "target": "5",
                    "areaId": "351",
                    "areaName": "351区",
                    "serverUrl": "https://game-351",
                    "serverKey": "qzone_351",
                },
                {"areaName": ""},
            ],
        })

        self.assertTrue(result["ok"])
        self.assertEqual(result["platformKey"], "sglm")
        self.assertEqual(result["platform"], "热血三国联盟")
        self.assertEqual(result["count"], 2)
        self.assertEqual(
            [item["serverKey"] for item in result["areas"]],
            ["qzone_351", "qzone_352"],
        )
        self.assertEqual(result["areas"][0]["target"], "1,5")

    def test_guide_csv_article_catalog_and_article_are_shared(self) -> None:
        famous = guide_reference_payload({
            "resource": "famous-generals",
            "sourceText": "﻿姓名,突围,属性,国家\n诸葛亮,99,智勇,蜀\n未知将,, ,\n",
        })
        self.assertEqual(famous["total"], 2)
        self.assertEqual(famous["items"][0]["breakthrough"], 99)
        self.assertIsNone(famous["items"][1]["breakthrough"])

        catalog = guide_reference_payload({"resource": "articles"})
        self.assertEqual(catalog["total"], 10)
        article = guide_reference_payload({
            "resource": "article",
            "id": "shuashihuang",
            "sourceText": "﻿第一行\n第二行",
        })
        self.assertEqual(article["article"]["title"], "刷黄攻略")
        self.assertEqual(article["article"]["body"], "第一行\n第二行")

    def test_open_server_rules_have_one_python_owner(self) -> None:
        result = guide_reference_payload({
            "resource": "open-server-calculation",
            "versionIndex": 4,
            "server": 114,
        })
        self.assertEqual(result["dateText"], "2017/5/31")
        self.assertEqual(result["daysOffset"], 14)
        self.assertEqual(result["rule"]["baseServer"], 113)

        now = int(datetime(2026, 7, 6, tzinfo=timezone.utc).timestamp() * 1000)
        options = guide_reference_payload(
            {"resource": "open-server-options"},
            now_millis=now,
        )
        alliance = next(item for item in options["versions"] if item["index"] == 4)
        self.assertEqual(alliance["upcomingServer"], 352)
        self.assertEqual(alliance["upcomingDate"], "2026/7/15")

    def test_facade_registers_both_local_reference_routes(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        try:
            areas = facade.dispatch(
                "GET",
                "/api/areas",
                {"platform": "sglm", "areas": []},
                {"requestId": "areas-1"},
            )
            self.assertEqual(areas.status, 200)
            self.assertEqual(areas.body["count"], 0)

            missing = facade.dispatch(
                "GET",
                "/api/reference/guide",
                {"resource": "article", "id": "missing"},
                {"requestId": "guide-1"},
            )
            self.assertEqual(missing.status, 404)
            self.assertFalse(missing.body["ok"])
        finally:
            facade.close()


if __name__ == "__main__":
    unittest.main()
