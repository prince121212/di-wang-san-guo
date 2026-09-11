#!/usr/bin/env python3
"""Audit current progress against the user-requested migration objective.

This is an evidence dashboard, not a network/device test. It checks the current worktree
for source files, tools and reports that prove each planned milestone, and it keeps the
final objective incomplete until true action send and true device regression are proven.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STATUS_COMPLETE = "complete"
STATUS_OFFLINE_READY = "offline_ready"
STATUS_TOOLING_READY = "tooling_ready"
STATUS_DRY_RUN_ONLY = "dry_run_only"
STATUS_LIVE_SENDER_GATED = "live_sender_gated"
STATUS_CODE_ALIGNED_DEVICE_PENDING = "code_aligned_device_pending"
STATUS_PARTIAL = "partial"
STATUS_MISSING = "missing"


@dataclass
class Requirement:
    order: int
    name: str
    required: list[str]
    strong: list[str]
    status_if_present: str
    completion_requires_live: bool = False
    notes: str = ""


REQUIREMENTS = [
    Requirement(
        1,
        "整理迁移矩阵",
        ["reports/migration_matrix_shuahuang_first.md"],
        ["reverse_cases/apk/analysis/business/functional_requirement_matrix.json"],
        STATUS_COMPLETE,
        notes="刷黄优先迁移矩阵已落地，逆向证据路径在报告中引用。",
    ),
    Requirement(
        2,
        "补齐后台调度框架",
        [
            "app/src/main/java/com/example/dwpmclone/domain/scheduler/TaskScheduler.kt",
            "app/src/main/java/com/example/dwpmclone/domain/scheduler/LocalSchedulerLifecycleRunner.kt",
            "app/src/main/java/com/example/dwpmclone/domain/scheduler/HostingStartPolicy.kt",
            "app/src/main/java/com/example/dwpmclone/domain/scheduler/RealSessionTaskPlanAdapter.kt",
            "app/src/main/java/com/example/dwpmclone/domain/scheduler/AssistantTasks.kt",
            "app/src/main/java/com/example/dwpmclone/service/AssistantForegroundService.kt",
            "app/src/main/java/com/example/dwpmclone/host/SharedResidentAutomationAdapter.kt",
            "app/src/test/java/com/example/dwpmclone/domain/scheduler/TaskSchedulerCoreLifecycleTest.kt",
            "app/src/test/java/com/example/dwpmclone/domain/scheduler/SharedResidentLegacyTaskFailClosedTest.kt",
            "app/src/test/java/com/example/dwpmclone/host/SharedResidentAutomationAdapterTest.kt",
            "app/src/test/java/com/example/dwpmclone/domain/scheduler/HostingStartPolicyTest.kt",
            "app/src/test/java/com/example/dwpmclone/domain/scheduler/RealSessionTaskPlanAdapterTest.kt",
            "reports/service_lifecycle_entry_evidence.md",
            "reports/real_session_plan_alignment_evidence.md",
        ],
        [],
        STATUS_COMPLETE,
        notes="调度、停止和 logout 测试存在。",
    ),
    Requirement(
        3,
        "稳定真实登录 / Session 与账号启停",
        [
            "app/src/main/java/com/example/dwpmclone/data/protocol/RealGameProtocolClient.kt",
            "app/src/main/java/com/example/dwpmclone/data/protocol/SessionAwareGameProtocolClient.kt",
            "app/src/main/java/com/example/dwpmclone/data/local/LocalAccountRepository.kt",
            "app/src/main/java/com/example/dwpmclone/host/SharedPythonCoreHost.kt",
            "../shared_core/python/dwpm_core/account/lifecycle.py",
            "../shared_core/python/dwpm_core/account/state_machine.py",
            "app/src/test/java/com/example/dwpmclone/data/protocol/SessionAwareGameProtocolClientTest.kt",
            "app/src/test/java/com/example/dwpmclone/host/SharedPythonCoreHostContractTest.kt",
        ],
        [],
        STATUS_COMPLETE,
        notes="真实登录、持久化、启停呈现和停止账号禁止发包已完成；保留 Session 只用于重登。",
    ),
    Requirement(
        4,
        "优先实现刷黄闭环",
        [
            "tools/replay_shuahuang_offline.py",
            "tools/test_replay_shuahuang_offline.py",
            "tools/check_brush_yellow_prereq.py",
            "tools/test_check_brush_yellow_prereq.py",
            "../shared_core/python/dwpm_core/local_views.py",
            "../shared_core/python/dwpm_core/facade.py",
            "../shared_core/python/dwpm_core/automation.py",
            "../电脑端辅助前端/tests/test_shared_expedition_operations.py",
            "../电脑端辅助前端/tests/test_shared_automation_recovery.py",
            "../电脑端辅助前端/tests/test_shared_automation_recovery_workflows.py",
            "../电脑端辅助前端/tests/test_shared_resident_automation.py",
            "app/src/main/java/com/example/dwpmclone/host/SharedResidentAutomationAdapter.kt",
            "app/src/test/java/com/example/dwpmclone/domain/scheduler/SharedResidentLegacyTaskFailClosedTest.kt",
        ],
        [],
        STATUS_CODE_ALIGNED_DEVICE_PENDING,
        completion_requires_live=True,
        notes="登录封地中心→找黄→统一预检→0x1520/0x1522→回执/事务冻结→次数与恢复均由共享 Python 实现；Kotlin 仅保留失败关闭配置标记，待共享宿主真机回归。",
    ),
    Requirement(
        5,
        "实现一键日常流程模型",
        [
            "app/src/main/java/com/example/dwpmclone/domain/protocol/DailyProtocolShapes.kt",
            "app/src/test/java/com/example/dwpmclone/domain/protocol/DailyProtocolShapesTest.kt",
            "reports/daily_flow_model_evidence.md",
        ],
        [],
        STATUS_COMPLETE,
        notes="小黄点恢复顺序和 payload shape 已模型化。",
    ),
    Requirement(
        6,
        "接入一键日常协议",
        [
            "../shared_core/python/dwpm_core/automation.py",
            "../电脑端辅助前端/tests/test_shared_daily_operations.py",
            "../电脑端辅助前端/tests/test_shared_resident_automation.py",
            "app/src/main/java/com/example/dwpmclone/domain/scheduler/DailyFeatureTasks.kt",
            "app/src/main/java/com/example/dwpmclone/host/SharedResidentAutomationAdapter.kt",
            "app/src/test/java/com/example/dwpmclone/domain/scheduler/DailyFeatureParityTest.kt",
            "app/src/test/java/com/example/dwpmclone/host/SharedResidentAutomationAdapterTest.kt",
            "app/src/test/java/com/example/dwpmclone/data/local/DailyCompletionCycleTest.kt",
        ],
        [],
        STATUS_CODE_ALIGNED_DEVICE_PENDING,
        completion_requires_live=True,
        notes="七项日常的发送、完成锁、竞技币22:00周期和重复/不确定回执均由共享 Python 拥有；Kotlin 旧任务已缩为失败关闭的配置标记，仅待本轮真机回归。",
    ),
    Requirement(
        7,
        "补角色 / 资源 / 将领状态解析",
        [
            "app/src/main/java/com/example/dwpmclone/domain/protocol/State8004RoleResourceEvidenceParser.kt",
            "app/src/test/java/com/example/dwpmclone/domain/protocol/State8004RoleResourceEvidenceParserTest.kt",
            "app/src/main/java/com/example/dwpmclone/domain/protocol/State8004GeneralEvidenceParser.kt",
            "app/src/test/java/com/example/dwpmclone/domain/protocol/State8004GeneralEvidenceParserTest.kt",
            "app/src/main/java/com/example/dwpmclone/domain/protocol/State8004ArmyEvidenceParser.kt",
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt",
        ],
        [],
        STATUS_CODE_ALIGNED_DEVICE_PENDING,
        completion_requires_live=True,
        notes="角色、资源、完整将领列表、军队与背包刷新已接入真实状态并保留完整缓存，仅待设备回归确认账号样本。",
    ),
    Requirement(
        8,
        "做地图扫描 / 找矿只读能力",
        [
            "app/src/main/java/com/example/dwpmclone/domain/localmap/LocalTargetCache.kt",
            "app/src/main/java/com/example/dwpmclone/data/local/LocalMapRepository.kt",
            "../shared_core/python/dwpm_core/features/targets.py",
            "../电脑端辅助前端/tests/test_shared_expedition_operations.py",
            "../电脑端辅助前端/tests/test_shared_resident_automation.py",
            "app/src/test/java/com/example/dwpmclone/domain/scheduler/SharedResidentLegacyTaskFailClosedTest.kt",
            "app/src/test/java/com/example/dwpmclone/data/local/LocalMapPersistenceTest.kt",
        ],
        [],
        STATUS_CODE_ALIGNED_DEVICE_PENDING,
        completion_requires_live=True,
        notes="0x1540/0x1542 扫描、目标解析、游标与自动重扫由共享 Python 拥有；Android 本地地图仅保存投影，待设备回归。",
    ),
    Requirement(
        9,
        "再做出征 / 占矿等动作扩展",
        [
            "../shared_core/python/dwpm_core/automation.py",
            "../shared_core/python/dwpm_core/features/dungeon.py",
            "../电脑端辅助前端/tests/test_shared_dungeon_automation.py",
            "../shared_core/python/dwpm_core/features/lossless.py",
            "../电脑端辅助前端/tests/test_shared_lossless_automation.py",
            "../电脑端辅助前端/tests/test_shared_raid_automation.py",
            "../电脑端辅助前端/tests/test_shared_resident_automation.py",
            "app/src/main/java/com/example/dwpmclone/host/SharedResidentAutomationAdapter.kt",
            "app/src/test/java/com/example/dwpmclone/host/SharedResidentAutomationAdapterTest.kt",
            "app/src/test/java/com/example/dwpmclone/host/SharedPythonCoreHostContractTest.kt",
        ],
        [],
        STATUS_CODE_ALIGNED_DEVICE_PENDING,
        completion_requires_live=True,
        notes="打矿、掠夺、无损和副本均进入共享 tick；过渡 adapter 与 Kotlin 协议入口已删除，Android 只提交统一 resident operation；待逐功能真机回归。",
    ),
    Requirement(
        10,
        "清除 native 缺口并建立动作安全边界",
        [
            "app/src/main/java/com/example/dwpmclone/domain/protocol/ExpeditionTransaction.kt",
            "app/src/main/java/com/example/dwpmclone/data/local/ExpeditionTransactionRepository.kt",
            "app/src/main/java/com/example/dwpmclone/domain/state/AccountOperationLockRegistry.kt",
            "tools/verify_action_safety_invariants.py",
            "tools/test_verify_action_safety_invariants.py",
            "app/src/test/java/com/example/dwpmclone/domain/protocol/ExpeditionTransactionCoordinatorTest.kt",
            "app/src/test/java/com/example/dwpmclone/domain/state/AccountOperationLockRegistryTest.kt",
        ],
        [],
        STATUS_COMPLETE,
        notes="正式动作使用 direct-binary GameCommand，不依赖 lx/key/lb native wrapper；账号锁、发送前账本和未知回执冻结已完成。",
    ),
    Requirement(
        11,
        "收口剩余 Kotlin 后台业务所有者",
        [
            "app/src/main/java/com/example/dwpmclone/domain/scheduler/TaskFactory.kt",
            "app/src/main/java/com/example/dwpmclone/domain/scheduler/AssistantTasks.kt",
            "../shared_core/python/dwpm_core/automation.py",
            "../shared_core/python/dwpm_core/features/inventory.py",
            "../shared_core/python/dwpm_core/features/alarm.py",
            "../shared_core/python/dwpm_core/facade.py",
            "../共享Python核心迁移规划.md",
            "../电脑端辅助前端/tests/test_core_migration_route_ownership.py",
            "../电脑端辅助前端/tests/test_shared_inventory_automation.py",
            "../电脑端辅助前端/tests/test_shared_alarm_automation.py",
            "app/src/main/java/com/example/dwpmclone/host/SharedResidentAutomationAdapter.kt",
            "app/src/main/java/com/example/dwpmclone/service/AssistantForegroundService.kt",
            "app/src/test/java/com/example/dwpmclone/domain/scheduler/InventoryCleanupTaskTest.kt",
        ],
        [],
        STATUS_COMPLETE,
        notes="自动背包与军情警报已切入共享 Python，Kotlin 任务与旧扫描入口均失败关闭。",
    ),
    Requirement(
        12,
        "整体真机回归测试",
        [
            "tools/check_device_regression_preflight.py",
            "tools/check_live_1016_session.py",
            "tools/test_check_live_1016_session.py",
            "tools/refresh_device_session_from_login.py",
            "tools/test_refresh_device_session_from_login.py",
            "tools/configure_device_shuahuang_service_plan.py",
            "tools/test_configure_device_shuahuang_service_plan.py",
            "reports/no_ui_session_refresh_tool_evidence.md",
            "tools/inspect_apk_manifest.py",
            "tools/capture_device_protocol_regression.sh",
            "tools/device_regression_from_logs.py",
            "tools/replay_full_offline.py",
            "tools/test_replay_full_offline.py",
            "tools/verify_overall_regression_readiness.py",
            "tools/test_verify_overall_regression_readiness.py",
            "tools/verify_device_regression_artifacts.py",
            "tools/promote_device_regression_capture.py",
            "tools/test_promote_device_regression_capture.py",
            "tools/run_device_regression_pipeline.sh",
            "tools/test_run_device_regression_pipeline.py",
            "tools/wait_for_device_and_run_pipeline.sh",
            "tools/test_wait_for_device_and_run_pipeline.py",
            "tools/package_device_regression_evidence.py",
            "tools/test_package_device_regression_evidence.py",
            "reports/native_wrapper_positive_fixture_readiness_evidence.md",
            "reports/device_regression_checklist.md",
            "reports/full_offline_replay_report.md",
            "reports/overall_regression_readiness.md",
        ],
        [],
        STATUS_TOOLING_READY,
        completion_requires_live=True,
        notes="等待设备→账号基线准备/无 UI 刷新 session→采集→校准→回放→gate 审计→产物验收→canonical 晋级→overall 刷新→证据包归档一键管线齐全，preflight 已校验 base_channel_extra JSON/安全 flag/基线质量；当前未检测到 ADB 真机执行证据。",
    ),
]

KOTLIN_BACKGROUND_OWNER_SYMBOLS = {
    "GeneralMaintenanceTask": "将领维护",
    "InternalAffairsTask": "自动内政",
    "InventoryCleanupTask": "自动背包",
    "AlarmTask": "军情警报",
}


def remaining_kotlin_background_owners(root: Path) -> list[str]:
    factory = (
        root
        / "app/src/main/java/com/example/dwpmclone/domain/scheduler/TaskFactory.kt"
    )
    if not factory.exists():
        return sorted(KOTLIN_BACKGROUND_OWNER_SYMBOLS.values())
    source = factory.read_text(encoding="utf-8", errors="ignore")
    assistant_tasks = (
        root
        / "app/src/main/java/com/example/dwpmclone/domain/scheduler/AssistantTasks.kt"
    )
    service = (
        root
        / "app/src/main/java/com/example/dwpmclone/service/AssistantForegroundService.kt"
    )
    assistant_source = (
        assistant_tasks.read_text(encoding="utf-8", errors="ignore")
        if assistant_tasks.exists()
        else ""
    )
    service_source = (
        service.read_text(encoding="utf-8", errors="ignore")
        if service.exists()
        else ""
    )
    inventory_marker = (
        assistant_source.split("class InventoryCleanupTask", 1)[1].split(
            "class GeneralMaintenanceTask", 1
        )[0]
        if "class InventoryCleanupTask" in assistant_source
        and "class GeneralMaintenanceTask" in assistant_source
        else ""
    )
    inventory_fail_closed = (
        inventory_marker.count('sharedOwnerStop("背包整理")') >= 2
        and "TaskType.INVENTORY" in service_source.split(
            "private val SHARED_RESIDENT_TASK_TYPES", 1
        )[-1]
    )
    alarm_marker = (
        assistant_source.split("class AlarmTask", 1)[1]
        if "class AlarmTask" in assistant_source
        else ""
    )
    alarm_fail_closed = (
        alarm_marker[:800].count('sharedOwnerStop("军情警报")') >= 2
        and "TaskType.ALARM" in service_source.split(
            "private val SHARED_RESIDENT_TASK_TYPES", 1
        )[-1]
        and "SHARED_ALARM_OWNER" in (
            root
            / "app/src/main/java/com/example/dwpmclone/data/protocol/SessionAwareGameProtocolClient.kt"
        ).read_text(encoding="utf-8", errors="ignore")
    )
    return [
        label
        for symbol, label in KOTLIN_BACKGROUND_OWNER_SYMBOLS.items()
        if f"add({symbol}(" in source
        and not (symbol == "InventoryCleanupTask" and inventory_fail_closed)
        and not (symbol == "AlarmTask" and alarm_fail_closed)
    ]


def exists(root: Path, rel: str) -> bool:
    # reverse_cases lives next to the self-developed source directory.
    if rel.startswith("reverse_cases/"):
        return (root.parent / rel).exists()
    return (root / rel).exists()


def file_contains(root: Path, rel: str, needles: list[str]) -> bool:
    path = root.parent / rel if rel.startswith("reverse_cases/") else root / rel
    if not path.exists() or not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return all(needle in text for needle in needles)


def evaluate_requirement(root: Path, req: Requirement) -> dict[str, Any]:
    required = {path: exists(root, path) for path in req.required}
    strong = {path: exists(root, path) for path in req.strong}
    missing = [path for path, ok in required.items() if not ok]
    status = req.status_if_present if not missing else STATUS_MISSING
    # Live-dependent requirements cannot be considered final-complete without device/action evidence.
    final_complete = status == STATUS_COMPLETE and not req.completion_requires_live
    return {
        "order": req.order,
        "name": req.name,
        "status": status,
        "finalComplete": final_complete,
        "requiresLiveEvidence": req.completion_requires_live,
        "requiredEvidence": required,
        "supportingEvidence": strong,
        "missing": missing,
        "notes": req.notes,
    }


def load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def adb_warning_from_coverage(root: Path) -> bool:
    data = load_optional_json(root / "reports/v1_coverage_report.json")
    if not data:
        data = load_optional_json(root / "reports/v2_coverage_report.json")
    if not data:
        return True
    for check in data.get("checks", []):
        if isinstance(check, dict) and "ADB" in str(check.get("name", "")):
            return not bool(check.get("ok"))
    return True


def latest_brush_yellow_prereq(root: Path) -> dict[str, Any] | None:
    return load_optional_json(root / "reports/brush_yellow_live_prereq_current.json")


def brush_yellow_gate_summary(root: Path) -> dict[str, Any]:
    report = latest_brush_yellow_prereq(root) or {}
    gates = report.get("gates") if isinstance(report.get("gates"), dict) else {}
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    return {
        "realActionNetworkAllowed": bool(gates.get("realActionNetworkAllowed")),
        "realActionSendReady": bool(gates.get("realActionSendReady")),
        "realActionScopeBrushYellow": bool(gates.get("realActionScopeBrushYellow")),
        "allowRecoveredGeneralFallbackFormation": bool(gates.get("allowRecoveredGeneralFallbackFormation")),
        "formationCount": int(report.get("formationCount") or 0) if isinstance(report, dict) else 0,
        "generalCandidateCount": int(report.get("generalCandidateCount") or 0) if isinstance(report, dict) else 0,
        "liveSessionFresh": bool(report.get("liveSessionFresh")),
        "readyForRealBrushYellow": bool(report.get("readyForRealBrushYellow")),
        "blockers": blockers,
    }


def live_brush_yellow_success_summary(root: Path) -> dict[str, Any]:
    data = load_optional_json(root / "reports/live_brush_yellow_success_evidence_current.json") or {}
    return {
        "liveBrushYellowSuccess": bool(data.get("liveBrushYellowSuccess")),
        "actionReport": data.get("actionReport"),
        "generalName": (data.get("chosenGeneral") or {}).get("name") if isinstance(data.get("chosenGeneral"), dict) else None,
        "targetKind": (data.get("chosenTarget") or {}).get("kind") if isinstance(data.get("chosenTarget"), dict) else None,
        "targetHex": data.get("targetHex"),
        "prepareOpcodeOk": bool(data.get("prepareOpcodeOk")),
        "expeditionOpcodeOk": bool(data.get("expeditionOpcodeOk")),
        "successMarkers": data.get("successMarkers") or [],
    }


def service_brush_yellow_success_summary(root: Path) -> dict[str, Any]:
    data = load_optional_json(root / "reports/service_brush_yellow_evidence_current.json") or {}
    productized = load_optional_json(root / "reports/productized_brush_yellow_service_path_current.json") or {}
    markers = data.get("markers") if isinstance(data.get("markers"), dict) else {}
    return {
        "serviceBrushYellowClosedLoop": bool(data.get("serviceBrushYellowEvidenceReady"))
        and bool(productized.get("serviceBrushYellowClosedLoop")),
        "markers": markers,
        "latestRunLogCount": data.get("latestRunLogCount"),
        "candidateGeneral": productized.get("candidateGeneral"),
        "candidateTarget": productized.get("candidateTarget"),
        "targetHex": productized.get("targetHex"),
    }


def audit(root: Path) -> dict[str, Any]:
    items = [evaluate_requirement(root, req) for req in REQUIREMENTS]
    remaining_background_owners = remaining_kotlin_background_owners(root)
    for item in items:
        if item["order"] == 11 and item["status"] != STATUS_MISSING:
            if remaining_background_owners:
                item["status"] = STATUS_PARTIAL
                item["finalComplete"] = False
                item["notes"] = (
                    "仍由 Kotlin 拥有："
                    + "、".join(remaining_background_owners)
                    + "；已明确后置下一版本，不能用真机证据替代代码所有权迁移。"
                )
            else:
                item["status"] = STATUS_COMPLETE
                item["finalComplete"] = True
                item["notes"] = "路由之外的 Android 后台业务所有者已全部切入共享 Python。"
    shared_python_action_owner_present = file_contains(
        root,
        "../shared_core/python/dwpm_core/facade.py",
        [
            "def _run_brush_execute_game_workflow",
            "def _run_mine_execute_game_workflow",
            "brushPendingRecoveryJson",
            "minePendingGarrisonJson",
        ],
    )
    android_raw_http_host_present = file_contains(
        root,
        "app/src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt",
        [
            "fun executeRawHttp",
            "fun executionOwnerActive",
            "fun tryAcquireNetworkOperation",
        ],
    )
    kotlin_resident_fail_closed = file_contains(
        root,
        "app/src/main/java/com/example/dwpmclone/domain/scheduler/AssistantTasks.kt",
        [
            "class ShuaHuangTask",
            "class MineTask",
            "class InventoryCleanupTask",
            'sharedOwnerStop("背包整理")',
            "sharedOwnerStop",
        ],
    )
    if (
        shared_python_action_owner_present
        and android_raw_http_host_present
        and kotlin_resident_fail_closed
    ):
        for item in items:
            if item["order"] == 4 and item["status"] != STATUS_MISSING:
                item["status"] = STATUS_CODE_ALIGNED_DEVICE_PENDING
                item["notes"] = "刷黄组包、目标选择、事务防重和恢复均由共享 Python 执行，Android 只提供 Raw HTTP，Kotlin 旧任务失败关闭；待共享宿主真机回归。"
            elif item["order"] == 9 and item["status"] != STATUS_MISSING:
                item["status"] = STATUS_CODE_ALIGNED_DEVICE_PENDING
                item["notes"] = "占矿/加速/撤防、掠夺、无损和副本均已进入共享 Python operation 与严格回执账本；待逐功能真机回归。"
    adb_warning = adb_warning_from_coverage(root)
    brush_gate = brush_yellow_gate_summary(root)
    brush_success = live_brush_yellow_success_summary(root)
    service_brush_success = service_brush_yellow_success_summary(root)
    if brush_success["liveBrushYellowSuccess"]:
        for item in items:
            if item["order"] == 4 and item["status"] != STATUS_MISSING:
                item["notes"] = (
                    "登录→角色/资源→将领/编队→找黄→1520030/1522030 出征已获得真机成功战报；"
                    "仍需继续产品化 UI/service 闭环和全量回归。"
                )
    if service_brush_success["serviceBrushYellowClosedLoop"]:
        for item in items:
            if item["order"] == 4 and item["status"] != STATUS_MISSING:
                item["notes"] = (
                    "历史 Kotlin service 曾取得登录、找黄、出征和停止真机闭环；"
                    "该证据不能替代当前共享 Python 宿主回归，因此仍为 code_aligned_device_pending。"
                )
    incomplete = [item for item in items if not item["finalComplete"]]
    live_blockers = [item["name"] for item in items if item["requiresLiveEvidence"] and not item["finalComplete"]]
    objective_complete = not incomplete and not adb_warning
    return {
        "summary": {
            "objectiveComplete": objective_complete,
            "completedFinalCount": sum(1 for item in items if item["finalComplete"]),
            "totalRequirementCount": len(items),
            "adbDeviceWarning": adb_warning,
            "realActionNetworkAllowed": brush_gate["realActionNetworkAllowed"],
            "realActionSendReady": brush_gate["realActionSendReady"],
            "realActionScopeBrushYellow": brush_gate["realActionScopeBrushYellow"],
            "brushYellowPrereq": brush_gate,
            "liveBrushYellowSuccess": brush_success["liveBrushYellowSuccess"],
            "liveBrushYellowSuccessEvidence": brush_success,
            "serviceBrushYellowClosedLoop": service_brush_success["serviceBrushYellowClosedLoop"],
            "serviceBrushYellowEvidence": service_brush_success,
            "sharedPythonActionOwnerPresent": shared_python_action_owner_present,
            "androidRawHttpHostPresent": android_raw_http_host_present,
            "kotlinResidentFailClosed": kotlin_resident_fail_closed,
            "remainingKotlinBackgroundOwners": remaining_background_owners,
            "blocker": (
                "仍有 Kotlin 后台业务所有者待迁移，且共享核心仍待逐功能动作、"
                "锁屏、网络切换、进程重建、重启恢复和抓包等真机验收。"
                if remaining_background_owners
                else
                "代码与离线行为已对齐；剩余阻断为逐功能动作、锁屏、网络切换、"
                "进程重建、重启恢复和抓包等真机验收。"
            ),
        },
        "requirements": items,
        "incomplete": [{"order": item["order"], "name": item["name"], "status": item["status"], "requiresLiveEvidence": item["requiresLiveEvidence"], "missing": item["missing"]} for item in incomplete],
        "liveEvidenceBlockers": live_blockers,
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 迁移总目标状态审计",
        "",
        "## Summary",
        "",
        f"- objectiveComplete: {str(s['objectiveComplete']).lower()}",
        f"- completedFinalCount: {s['completedFinalCount']} / {s['totalRequirementCount']}",
        f"- adbDeviceWarning: {str(s['adbDeviceWarning']).lower()}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- realActionSendReady: {str(s.get('realActionSendReady', False)).lower()}",
        f"- realActionScopeBrushYellow: {str(s.get('realActionScopeBrushYellow', False)).lower()}",
        f"- liveBrushYellowSuccess: {str(s.get('liveBrushYellowSuccess', False)).lower()}",
        f"- serviceBrushYellowClosedLoop: {str(s.get('serviceBrushYellowClosedLoop', False)).lower()}",
        f"- sharedPythonActionOwnerPresent: {str(s.get('sharedPythonActionOwnerPresent', False)).lower()}",
        f"- androidRawHttpHostPresent: {str(s.get('androidRawHttpHostPresent', False)).lower()}",
        f"- kotlinResidentFailClosed: {str(s.get('kotlinResidentFailClosed', False)).lower()}",
        f"- remainingKotlinBackgroundOwners: {json.dumps(s.get('remainingKotlinBackgroundOwners', []), ensure_ascii=False)}",
        f"- blocker: {s['blocker']}",
        "",
        "## Requirements",
        "",
        "| 顺序 | 目标 | 状态 | Final Complete | 需要真机/动作证据 | 说明 |",
        "|---:|---|---|---:|---:|---|",
    ]
    for item in report["requirements"]:
        lines.append(
            f"| {item['order']} | {item['name']} | {item['status']} | "
            f"{str(item['finalComplete']).lower()} | {str(item['requiresLiveEvidence']).lower()} | {item['notes']} |"
        )
    lines += [
        "",
        "## Incomplete / 非最终完成项",
        "",
        "```json",
        json.dumps(report["incomplete"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Live evidence blockers",
        "",
        "```json",
        json.dumps(report["liveEvidenceBlockers"], ensure_ascii=False, indent=2),
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent), help="Self-developed source root")
    ap.add_argument("--out", help="Write JSON report; defaults to stdout")
    ap.add_argument("--markdown-out", help="Write Markdown report")
    ns = ap.parse_args()
    report = audit(Path(ns.root))
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
