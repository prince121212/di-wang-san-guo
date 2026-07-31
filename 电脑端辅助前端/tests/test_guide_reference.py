from __future__ import annotations

import importlib.util
import json
import sys
import threading
import unittest
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "电脑端辅助前端"
SERVER_PATH = FRONTEND / "server.py"
SPEC = importlib.util.spec_from_file_location("dwpm_server_guide_reference_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class GuideReferenceTests(unittest.TestCase):
    def test_famous_general_table_is_available_to_desktop_containers(self) -> None:
        payload = SERVER.guide_famous_generals_payload()

        self.assertTrue(payload["ok"])
        self.assertEqual(399, payload["total"])
        zhuge = next(item for item in payload["items"] if item["name"] == "诸葛亮")
        self.assertEqual(99, zhuge["breakthrough"])
        self.assertEqual("智勇", zhuge["attribute"])
        self.assertEqual("蜀", zhuge["nation"])

    def test_guide_index_and_detail_keep_the_original_local_articles(self) -> None:
        index = SERVER.guide_articles_payload()
        detail = SERVER.guide_article_payload("shuashihuang")

        self.assertEqual(10, index["total"])
        self.assertTrue(detail["ok"])
        self.assertEqual("刷黄攻略", detail["article"]["title"])
        self.assertGreater(len(detail["article"]["body"]), 100)
        self.assertFalse(SERVER.guide_article_payload("../server.py")["ok"])

    def test_open_server_math_matches_the_recovered_android_rule(self) -> None:
        result = SERVER.guide_open_server_calculation_payload(version_index=4, server=114)
        options = SERVER.guide_open_server_options_payload(today=date(2026, 7, 27))

        self.assertEqual("三国联盟", result["versionLabel"])
        self.assertEqual("2017/5/31", result["dateText"])
        self.assertEqual(14, result["rule"]["intervalDays"])
        self.assertEqual(7, len(options["versions"]))
        alliance = options["versions"][4]
        self.assertGreater(alliance["upcomingServer"], 113)
        upcoming_parts = [int(part) for part in alliance["upcomingDate"].split("/")]
        self.assertGreater(
            date(*upcoming_parts),
            date(2026, 7, 27),
        )

    def test_shared_canvas_no_longer_contains_a_simulated_phone_status_bar(self) -> None:
        html = (FRONTEND / "index.html").read_text(encoding="utf-8")

        self.assertNotIn('class="status-bar"', html)
        self.assertNotIn('class="status-icons"', html)
        self.assertIn('class="app-title"', html)

    def test_read_only_reference_api_serves_a_desktop_container(self) -> None:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), SERVER.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = (
                f"http://127.0.0.1:{httpd.server_address[1]}"
                "/api/reference/guide?resource=famous-generals"
            )
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.loads(response.read())

            self.assertTrue(payload["ok"])
            self.assertEqual(399, payload["total"])
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
