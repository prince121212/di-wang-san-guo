from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "电脑端辅助前端" / "app.js"
STYLES = ROOT / "电脑端辅助前端" / "styles.css"
MATRIX = ROOT / "shared_core" / "feature_parity_matrix.json"


class DeferredFeatureUiTests(unittest.TestCase):
    def test_deferred_features_are_disabled_in_shared_ui(self) -> None:
        app = APP_JS.read_text(encoding="utf-8")
        css = STYLES.read_text(encoding="utf-8")
        self.assertIn(
            'new Set(["抢城", "押镖", "寻宝", "连体物品"])',
            app,
        )
        self.assertIn('disabled aria-disabled=\\"true\\"', app)
        self.assertIn('if (btn.disabled || isDeferredFeatureSide(btn.dataset.side)) return;', app)
        self.assertIn('const militaryFutureFeatureMap = { "无损": "lossless", "副本": "dungeon" };', app)
        self.assertIn('.side-tab.feature-deferred:disabled', css)

    def test_parity_matrix_records_user_deferred_scope(self) -> None:
        matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
        self.assertEqual(
            matrix["deferred"],
            ["抢城", "押镖", "寻宝", "连体物品整理"],
        )
        statuses = {item["id"]: item["status"] for item in matrix["features"]}
        for feature in ("grabCity", "convoy", "treasure", "chainInventory"):
            self.assertEqual(statuses[feature], "deferred")


if __name__ == "__main__":
    unittest.main()
