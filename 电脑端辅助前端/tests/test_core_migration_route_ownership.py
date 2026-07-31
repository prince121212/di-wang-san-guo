from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "shared_core" / "api_route_ownership.json"
DESKTOP_SERVER = ROOT / "电脑端辅助前端" / "server.py"
FRONTEND_APP = ROOT / "电脑端辅助前端" / "app.js"
ANDROID_ROUTE_SOURCES = (
    ROOT
    / "自研辅助源码"
    / "app/src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt",
    ROOT
    / "自研辅助源码"
    / "app/src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt",
)


class CoreMigrationRouteOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        cls.shared = cls.matrix["routes"]
        cls.host_only = cls.matrix["hostOnlyRoutes"]
        cls.legacy = cls.matrix["legacyRoutes"]
        cls.exact_rows = [
            row for row in cls.shared + cls.host_only + cls.legacy
            if "*" not in row["path"] and row["method"] != "*"
        ]
        cls.exact_pairs = {
            (row["method"], row["path"]) for row in cls.exact_rows
        }
        cls.exact_paths = {row["path"] for row in cls.exact_rows}

    def test_matrix_has_unique_routes_and_valid_response_classes(self) -> None:
        keys = [(row["method"], row["path"]) for row in self.exact_rows]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(self.matrix["schemaVersion"], 1)
        for row in self.shared:
            self.assertEqual(self.matrix["targetOwner"], "shared-python")
            self.assertIn(row["responseClass"], {"local", "network-operation"})
            if row["responseClass"] == "network-operation":
                self.assertIn(row.get("operationKind"), {"query", "mutation"})
            else:
                self.assertNotIn("operationKind", row)

    def test_desktop_handler_paths_are_all_classified(self) -> None:
        source = DESKTOP_SERVER.read_text(encoding="utf-8")
        handler = source[source.index("class Handler("):source.index("def main()")]
        paths = set(re.findall(r'["\'](/api/[A-Za-z0-9_./-]+)', handler))
        missing = sorted(path for path in paths if not self._classified_path(path))
        self.assertEqual(missing, [])

    def test_shared_frontend_paths_are_all_classified(self) -> None:
        source = FRONTEND_APP.read_text(encoding="utf-8")
        paths = set(re.findall(r"/api/[A-Za-z0-9_./-]+", source))
        missing = sorted(path for path in paths if not self._classified_path(path))
        self.assertEqual(missing, [])

    def test_android_allow_list_is_covered_and_known_gaps_are_explicit(self) -> None:
        source = "\n".join(path.read_text(encoding="utf-8") for path in ANDROID_ROUTE_SOURCES)
        android_pairs = set(re.findall(r'"(GET|POST)"\s+to\s+"(/api/[^"]+)"', source))
        self.assertEqual(sorted(android_pairs - self.exact_pairs), [])

        expected_missing = {
            ("POST", "/api/liubu/hubu/query"),
            ("POST", "/api/liubu/hubu/plant"),
            ("POST", "/api/domestic/query"),
            ("POST", "/api/domestic/action"),
        }
        declared_missing = {
            (row["method"], row["path"])
            for row in self.shared
            if row["currentAndroid"] == "missing"
        }
        self.assertEqual(declared_missing, expected_missing)
        self.assertTrue(expected_missing.isdisjoint(android_pairs))

    def test_response_model_separates_local_saves_from_network_work(self) -> None:
        by_key = {(row["method"], row["path"]): row for row in self.shared}
        for path in (
            "/api/settings/save",
            "/api/formations/save",
            "/api/raid/execute",
            "/api/mine/save",
            "/api/liubu/save",
            "/api/lossless/execute",
            "/api/dungeon/execute",
            "/api/military/future/save",
        ):
            self.assertEqual(by_key[("POST", path)]["responseClass"], "local")

        for method, path in (
            ("GET", "/api/state/refresh"),
            ("GET", "/api/military/intel"),
            ("POST", "/api/brush/search"),
            ("POST", "/api/brush/execute"),
            ("POST", "/api/mine/search"),
            ("POST", "/api/mine/execute"),
        ):
            self.assertEqual(by_key[(method, path)]["responseClass"], "network-operation")

    def _classified_path(self, path: str) -> bool:
        return path in self.exact_paths or path.startswith("/api/v1/mobile")


if __name__ == "__main__":
    unittest.main()
