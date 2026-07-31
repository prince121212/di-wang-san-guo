#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("verify_migration_goal_status.py")
spec = importlib.util.spec_from_file_location("verify_migration_goal_status", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["verify_migration_goal_status"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]
ROOT = SCRIPT.parent.parent


class VerifyMigrationGoalStatusTest(unittest.TestCase):
    def test_current_worktree_reports_goal_not_final_complete(self):
        report = mod.audit(ROOT)
        self.assertFalse(report["summary"]["objectiveComplete"])
        self.assertEqual(11, report["summary"]["totalRequirementCount"])
        self.assertTrue(report["summary"]["realActionNetworkAllowed"])
        self.assertTrue(report["summary"]["realActionSendReady"])
        self.assertTrue(report["summary"]["realActionScopeBrushYellow"])
        self.assertIn("brushYellowPrereq", report["summary"])
        self.assertTrue(report["summary"]["liveBrushYellowSuccess"])
        self.assertIn("liveBrushYellowSuccessEvidence", report["summary"])
        self.assertTrue(report["summary"]["serviceBrushYellowClosedLoop"])
        self.assertIn("serviceBrushYellowEvidence", report["summary"])
        self.assertTrue(report["summary"]["directBinaryActionSenderPresent"])
        self.assertTrue(report["summary"]["brushYellowScopeGatePresent"])
        names = [item["name"] for item in report["requirements"]]
        self.assertIn("优先实现刷黄闭环", names)
        login_session = next(
            item for item in report["requirements"]
            if item["name"] == "稳定真实登录 / Session 与账号启停"
        )
        self.assertEqual("complete", login_session["status"])
        self.assertTrue(login_session["requiredEvidence"][
            "app/src/main/java/com/example/dwpmclone/domain/protocol/AccountLifecyclePresentation.kt"
        ])
        scheduler = next(item for item in report["requirements"] if item["name"] == "补齐后台调度框架")
        self.assertTrue(scheduler["requiredEvidence"]["app/src/main/java/com/example/dwpmclone/domain/scheduler/LocalSchedulerLifecycleRunner.kt"])
        self.assertTrue(scheduler["requiredEvidence"]["app/src/main/java/com/example/dwpmclone/domain/scheduler/HostingStartPolicy.kt"])
        self.assertTrue(scheduler["requiredEvidence"]["app/src/main/java/com/example/dwpmclone/domain/scheduler/RealSessionTaskPlanAdapter.kt"])
        self.assertTrue(scheduler["requiredEvidence"]["reports/service_lifecycle_entry_evidence.md"])
        self.assertTrue(scheduler["requiredEvidence"]["reports/real_session_plan_alignment_evidence.md"])
        shua_huang = next(item for item in report["requirements"] if item["name"] == "优先实现刷黄闭环")
        self.assertEqual("complete", shua_huang["status"])
        self.assertTrue(shua_huang["finalComplete"])
        self.assertTrue(shua_huang["requiredEvidence"]["tools/check_brush_yellow_prereq.py"])
        self.assertTrue(shua_huang["requiredEvidence"]["tools/test_check_brush_yellow_prereq.py"])
        self.assertTrue(shua_huang["requiredEvidence"][
            "app/src/main/java/com/example/dwpmclone/domain/protocol/BrushCenterRecommendationPolicy.kt"
        ])
        daily_protocol = next(item for item in report["requirements"] if item["name"] == "接入一键日常协议")
        self.assertEqual("code_aligned_device_pending", daily_protocol["status"])
        self.assertTrue(daily_protocol["requiredEvidence"][
            "app/src/test/java/com/example/dwpmclone/data/local/DailyCompletionCycleTest.kt"
        ])
        mine_search = next(item for item in report["requirements"] if item["name"] == "做地图扫描 / 找矿只读能力")
        self.assertEqual("code_aligned_device_pending", mine_search["status"])
        self.assertTrue(mine_search["requiredEvidence"][
            "app/src/test/java/com/example/dwpmclone/domain/scheduler/LocalMapTaskLifecycleTest.kt"
        ])
        action_ext = next(item for item in report["requirements"] if item["name"] == "再做出征 / 占矿等动作扩展")
        self.assertEqual("code_aligned_device_pending", action_ext["status"])
        self.assertTrue(action_ext["requiredEvidence"][
            "app/src/test/java/com/example/dwpmclone/domain/protocol/MineRaidProtocolParityFixtureTest.kt"
        ])
        device_regression = next(item for item in report["requirements"] if item["name"] == "整体真机回归测试")
        self.assertTrue(device_regression["requiredEvidence"]["tools/check_live_1016_session.py"])
        self.assertTrue(device_regression["requiredEvidence"]["tools/test_check_live_1016_session.py"])
        self.assertTrue(device_regression["requiredEvidence"]["tools/refresh_device_session_from_login.py"])
        self.assertTrue(device_regression["requiredEvidence"]["tools/test_refresh_device_session_from_login.py"])
        self.assertTrue(device_regression["requiredEvidence"]["tools/configure_device_shuahuang_service_plan.py"])
        self.assertTrue(device_regression["requiredEvidence"]["tools/test_configure_device_shuahuang_service_plan.py"])
        self.assertTrue(device_regression["requiredEvidence"]["reports/no_ui_session_refresh_tool_evidence.md"])
        self.assertTrue(device_regression["requiredEvidence"]["tools/replay_full_offline.py"])
        self.assertTrue(device_regression["requiredEvidence"]["tools/test_replay_full_offline.py"])
        self.assertTrue(device_regression["requiredEvidence"]["tools/verify_overall_regression_readiness.py"])
        self.assertTrue(device_regression["requiredEvidence"]["tools/test_verify_overall_regression_readiness.py"])
        self.assertTrue(device_regression["requiredEvidence"]["reports/full_offline_replay_report.md"])
        self.assertTrue(device_regression["requiredEvidence"]["reports/overall_regression_readiness.md"])
        native_gap = next(
            item for item in report["requirements"]
            if item["name"] == "清除 native 缺口并建立动作安全边界"
        )
        self.assertEqual("complete", native_gap["status"])
        self.assertTrue(native_gap["requiredEvidence"]["tools/verify_action_safety_invariants.py"])
        self.assertTrue(native_gap["requiredEvidence"]["tools/test_verify_action_safety_invariants.py"])
        self.assertTrue(native_gap["requiredEvidence"][
            "app/src/test/java/com/example/dwpmclone/domain/state/AccountOperationLockRegistryTest.kt"
        ])
        incomplete_names = [item["name"] for item in report["incomplete"]]
        self.assertNotIn("优先实现刷黄闭环", incomplete_names)
        self.assertIn("整体真机回归测试", incomplete_names)

    def test_markdown_contains_all_requirements(self):
        report = mod.audit(ROOT)
        md = mod.to_markdown(report)
        self.assertIn("迁移总目标状态审计", md)
        self.assertIn("directBinaryActionSenderPresent: true", md)
        self.assertIn("realActionSendReady: true", md)
        self.assertIn("liveBrushYellowSuccess: true", md)
        self.assertIn("serviceBrushYellowClosedLoop: true", md)
        self.assertIn("整理迁移矩阵", md)
        self.assertIn("整体真机回归测试", md)

    def test_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "goal_status.json"
            md = Path(td) / "goal_status.md"
            subprocess.check_call([sys.executable, str(SCRIPT), "--root", str(ROOT), "--out", str(out), "--markdown-out", str(md)])
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(report["summary"]["objectiveComplete"])
            self.assertIn("迁移总目标状态审计", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
