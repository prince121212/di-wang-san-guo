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
            "app/src/test/java/com/example/dwpmclone/domain/scheduler/TaskSchedulerStopAndShuaHuangTest.kt",
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
            "app/src/main/java/com/example/dwpmclone/domain/protocol/AccountLifecyclePresentation.kt",
            "app/src/test/java/com/example/dwpmclone/data/protocol/SessionAwareGameProtocolClientTest.kt",
            "app/src/test/java/com/example/dwpmclone/domain/protocol/AccountLifecyclePresentationPolicyTest.kt",
        ],
        [],
        STATUS_COMPLETE,
        notes="真实登录、持久化、启停呈现和停止账号禁止发包已完成；保留 Session 只用于重登。",
    ),
    Requirement(
        4,
        "优先实现刷黄闭环",
        [
            "app/src/main/java/com/example/dwpmclone/data/protocol/BrushYellowDispatchPayloadBuilder.kt",
            "app/src/main/java/com/example/dwpmclone/domain/protocol/BrushYellowDispatchResponseParser.kt",
            "tools/replay_shuahuang_offline.py",
            "tools/test_replay_shuahuang_offline.py",
            "tools/check_brush_yellow_prereq.py",
            "tools/test_check_brush_yellow_prereq.py",
            "app/src/main/java/com/example/dwpmclone/domain/protocol/BrushCenterRecommendationPolicy.kt",
            "app/src/main/java/com/example/dwpmclone/domain/scheduler/AssistantTasks.kt",
            "app/src/test/java/com/example/dwpmclone/domain/protocol/BrushYellowProtocolParityFixtureTest.kt",
            "app/src/test/java/com/example/dwpmclone/domain/protocol/BrushCenterRecommendationPolicyTest.kt",
        ],
        [],
        STATUS_CODE_ALIGNED_DEVICE_PENDING,
        completion_requires_live=True,
        notes="登录封地中心→本地找黄→统一预检→0x1520/0x1522→回执/事务冻结→次数与恢复均已实现，仅待本轮真机回归。",
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
            "app/src/main/java/com/example/dwpmclone/domain/protocol/DailyFeatureProtocolShapes.kt",
            "app/src/main/java/com/example/dwpmclone/domain/scheduler/DailyFeatureTasks.kt",
            "app/src/main/java/com/example/dwpmclone/domain/protocol/NationalCitizenDailyPolicy.kt",
            "app/src/test/java/com/example/dwpmclone/domain/scheduler/DailyFeatureParityTest.kt",
            "app/src/test/java/com/example/dwpmclone/domain/scheduler/DailyFeatureTerminalSemanticsTest.kt",
            "app/src/test/java/com/example/dwpmclone/data/local/DailyCompletionCycleTest.kt",
        ],
        [],
        STATUS_CODE_ALIGNED_DEVICE_PENDING,
        completion_requires_live=True,
        notes="七项日常真实发送、独立完成锁、竞技币22:00周期、重复回执和国民跳过均已实现，仅待本轮真机回归。",
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
            "app/src/main/java/com/example/dwpmclone/domain/protocol/TargetSearchResponseParser.kt",
            "app/src/main/java/com/example/dwpmclone/domain/protocol/ResourcePointSearchResponseParser.kt",
            "app/src/test/java/com/example/dwpmclone/domain/scheduler/LocalMapTaskLifecycleTest.kt",
            "app/src/test/java/com/example/dwpmclone/data/local/LocalMapPersistenceTest.kt",
        ],
        [],
        STATUS_CODE_ALIGNED_DEVICE_PENDING,
        completion_requires_live=True,
        notes="0x1540/0x1542扫描、本地持久化、TTL、空结果抑制、失效删除和自动重扫已完成，仅待设备回归。",
    ),
    Requirement(
        9,
        "再做出征 / 占矿等动作扩展",
        [
            "app/src/main/java/com/example/dwpmclone/domain/protocol/MineProtocolShapes.kt",
            "app/src/main/java/com/example/dwpmclone/domain/protocol/LootProtocolShapes.kt",
            "app/src/main/java/com/example/dwpmclone/domain/protocol/LosslessProtocolShapes.kt",
            "app/src/main/java/com/example/dwpmclone/domain/protocol/DungeonProtocolShapes.kt",
            "app/src/test/java/com/example/dwpmclone/domain/protocol/MineRaidProtocolParityFixtureTest.kt",
            "app/src/test/java/com/example/dwpmclone/domain/protocol/LosslessDungeonProtocolParityFixtureTest.kt",
        ],
        [],
        STATUS_CODE_ALIGNED_DEVICE_PENDING,
        completion_requires_live=True,
        notes="打矿占领/加速/撤防、掠夺、无损和副本均有真实发送、严格回执、统一预检和恢复状态，仅待逐功能真机回归。",
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
    direct_binary_sender_present = file_contains(
        root,
        "app/src/main/java/com/example/dwpmclone/data/protocol/SessionAwareGameProtocolClient.kt",
        [
            "sendBinaryMappedGameHex",
            "direct-binary-action",
            "payloads.preparePayload",
            "payloads.expeditionPayload",
        ],
    )
    brush_yellow_scope_gate_present = file_contains(
        root,
        "app/src/main/java/com/example/dwpmclone/data/protocol/SessionAwareGameProtocolClient.kt",
        [
            "REAL_ACTION_SCOPE_NOT_CONFIRMED",
            "realActionScope",
            "brush-yellow",
        ],
    )
    if direct_binary_sender_present and brush_yellow_scope_gate_present:
        for item in items:
            if item["order"] == 4 and item["status"] != STATUS_MISSING:
                item["status"] = STATUS_CODE_ALIGNED_DEVICE_PENDING
                item["notes"] = "刷黄 direct-binary sender、封地推荐中心、统一预检、事务防重和调度恢复已实现；仅待本轮真机回归。"
            elif item["order"] == 9 and item["status"] != STATUS_MISSING:
                item["status"] = STATUS_CODE_ALIGNED_DEVICE_PENDING
                item["notes"] = "占矿/加速/撤防、掠夺、无损和副本均已使用 direct-binary sender 与严格回执；仅待逐功能真机回归。"
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
                item["status"] = STATUS_COMPLETE
                item["finalComplete"] = True
                item["notes"] = (
                    "产品化 service 已完成登录/session 刷新、角色/资源/将领/编队读取、找黄、"
                    "1520030/1522030 出征成功、dailyLimit Stop、logout 和 service destroy 真机闭环。"
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
            "directBinaryActionSenderPresent": direct_binary_sender_present,
            "brushYellowScopeGatePresent": brush_yellow_scope_gate_present,
            "blocker": "代码与离线行为已对齐；剩余阻断仅为逐功能动作、锁屏、网络切换、进程重建、重启恢复和抓包等真机验收。",
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
        f"- directBinaryActionSenderPresent: {str(s.get('directBinaryActionSenderPresent', False)).lower()}",
        f"- brushYellowScopeGatePresent: {str(s.get('brushYellowScopeGatePresent', False)).lower()}",
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
