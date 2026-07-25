#!/usr/bin/env python3
"""Generate an operator checklist for one device protocol capture run.

The guide mirrors verify_device_capture_scenarios.py so the human/device-side actions match
what the later verifier requires. It is offline-only documentation generation; it does not use
ADB, Frida, network, or game APIs.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from verify_device_capture_scenarios import SCENARIOS, next_actions

CAPTURE_ORDER = [
    "loginState8004",
    "nativeWrapper",
    "generalFormationBaseline",
    "brushYellowSearch041540",
    "brushYellowNativeWrapper1520",
    "brushYellowDispatch1522030",
    "selfStopLogout",
    "daily",
    "mineSearch041542",
]

OPERATOR_STEPS = {
    "loginState8004": [
        "启动小黄点辅助和游戏本体，使用隔离测试账号完成登录/初始化。",
        "停留到角色/资源/将领状态同步完成；不要只采登录按钮点击，要等 0x8004 状态返回。",
    ],
    "nativeWrapper": [
        "执行任一会触发小黄点 native wrapper 的普通操作，确认 Frida 控制台持续输出 wrapper/json 标记。",
        "如果没有 [native-wrapper-json]，先检查 frida-server、脚本注入和小黄点包名。",
    ],
    "generalFormationBaseline": [
        "进入刷黄配置页或账号状态同步页，确认当前账号已有可用将领和刷黄出征编队。",
        "优先准备真实 `base_channel_extra.json`；采集日志或 merged channelExtra 中必须同时有将领基线和编队基线，避免后续 1522030 响应无法反推出 formationId。",
    ],
    "brushYellowSearch041540": [
        "进入刷黄功能，按目标条件执行一次找黄/搜索。",
        "等待搜索结果出现，确保日志包含 041540 readonly response 和黄巾/山贼目标片段。",
    ],
    "brushYellowNativeWrapper1520": [
        "在隔离测试账号中触发一次刷黄出征流程，重点保留 1520030 准备段和 1522030 出征段 native wrapper。",
        "这一步只采小黄点真实行为；自研辅助仍保持真实动作发送关闭。",
    ],
    "brushYellowDispatch1522030": [
        "同一次刷黄出征中等待服务端动作响应返回，确认日志包含 1522030 action-response-json。",
        "记录 formationId/targetId/usedAount 或成功文本，供离线 replay 校准。",
    ],
    "selfStopLogout": [
        "切到自研辅助，停止刷黄/本地调度任务并退出登录或让服务进入 terminal 停止流程。",
        "确认日志中同时出现任务停止和 logout/session 释放证据；这一步用于证明最小闭环的“停止任务/退出登录”，不代表允许真实动作发包。",
    ],
    "daily": [
        "执行一键日常至少一个步骤；推荐按签到、宝箱、加忠、征税、竞技奖励、俸禄、删信、三捐、粮转铜顺序完整采样。",
        "确认日志包含 daily-response-json 或 step/SIGN_IN 等日常步骤标记。",
    ],
    "mineSearch041542": [
        "执行找矿/资源点扫描，等待资源点列表返回。",
        "确认日志包含 041542 readonly response 和资源点/mineTargets/矿种坐标片段。",
    ],
}


def render_guide(package: str, mode: str, duration: str, base_channel_extra: str = "") -> str:
    lines: list[str] = [
        "# 设备协议采集操作指南",
        "",
        "## 本次采集参数",
        "",
        f"- package: {package or '<小黄点包名>'}",
        f"- mode: {mode}",
        f"- durationSeconds: {duration}",
        f"- baseChannelExtra: {base_channel_extra or '<未提供>'}",
        "- realActionNetworkAllowed: false",
        "- 说明：本指南只指导采集小黄点/游戏日志；自研辅助真实动作发送仍必须保持关闭。",
        "",
        "## 采集前 channelExtra 准备",
        "",
        "推荐在真机采集前准备真实账号的 `base_channel_extra.json`，用于把登录/session、角色/资源、将领/编队配置与本次日志采集合并回放：",
        "",
        "```bash",
        "python3 tools/prepare_base_channel_extra.py <LocalAccountRepository导出或账号JSON> \\",
        "  --out reports/base_channel_extra.json \\",
        "  --report-out reports/base_channel_extra_report.json \\",
        "  --markdown-out reports/base_channel_extra_report.md",
        "```",
        "",
        "如果只是验证工具链，可先生成离线 full 样本；真机验收时应优先使用真实账号/真实采集数据，不要把样本当作真实完成证据：",
        "",
        "```bash",
        "python3 tools/generate_shuahuang_channel_extra_sample.py --profile full \\",
        "  --out reports/full_replay_channel_extra_sample.json \\",
        "  --report-out reports/full_replay_channel_extra_sample_report.json \\",
        "  --markdown-out reports/full_replay_channel_extra_sample_report.md",
        "```",
        "",
        "## 推荐一键管线命令",
        "",
        "接上授权 ADB 设备后，优先使用等待设备管线。该命令会先等待 preflight 就绪，再可选执行自研 App smoke，随后采集小黄点/游戏日志、离线回放、gate 审计、产物验收和 canonical 导入：",
        "",
        "```bash",
        "bash tools/wait_for_device_and_run_pipeline.sh \\",
        f"  --package {package or 'com.ifengwoo.dwpm'} \\",
        "  --base-channel-extra reports/base_channel_extra.json \\",
        "  --timeout 600 \\",
        "  --interval 5 \\",
        f"  --duration {duration} \\",
        "  --run-self-smoke-first \\",
        "  --promote-canonical",
        "```",
        "",
        "如果尚未准备 `reports/base_channel_extra.json`，可以先去掉 `--base-channel-extra` 只跑 preflight/采集工具链；但最终验收必须补齐真实账号的 session、角色/资源、将领/编队基线。",
        "",
        "## 端到端验收链路映射",
        "",
        "| 目标链路 | 必需采集场景 | 通过信号 |",
        "|---|---|---|",
        "| 登录 | loginState8004 | 0x8004 + role/resource/session evidence |",
        "| 获取角色/资源状态 | loginState8004 | roleStateJson/resourceStateJson 或中文角色资源字段 |",
        "| 获取将领/编队信息 | generalFormationBaseline | generalsJson + formationsJson/bianduihao |",
        "| 找黄 | brushYellowSearch041540 | 041540 readonly-response-json |",
        "| 根据配置筛选目标 | brushYellowSearch041540 + base_channel_extra | offline replay 选择 targetId/targetType |",
        "| 出征刷黄 | brushYellowNativeWrapper1520 + brushYellowDispatch1522030 | 1520030 + 1522030 wrapper/action response；自研真实发包仍关闭 |",
        "| 停止任务 | selfStopLogout | [self-lifecycle-json] event=task_stop |",
        "| 退出登录 | selfStopLogout | [self-lifecycle-json] event=session_logout/logoutOnce |",
        "| 一键日常 | daily | daily-response-json 或 SIGN_IN 等步骤证据 |",
        "| 找矿只读 | mineSearch041542 | 041542 readonly-response-json |",
        "",
        "## 采集泳道顺序",
        "",
        "建议按三条泳道一次性完成，避免遗漏：",
        "",
        "1. **小黄点/游戏只读与动作样本泳道**：loginState8004 → nativeWrapper → generalFormationBaseline → brushYellowSearch041540 → brushYellowNativeWrapper1520 → brushYellowDispatch1522030 → daily → mineSearch041542。",
        "2. **自研辅助 lifecycle 泳道**：启动自研辅助真实只读 session → 启动后台托管/本地调度 → 停止后台托管/任务 → 退出登录，确保 logcat 有 `[self-lifecycle-json]`。",
        "3. **离线验收泳道**：采集结束后立即看 capture_scenario_check、self_lifecycle_logcat_check、shuahuang_minimum_goal_check、regression_artifact_check 和 full_offline_replay。",
        "",
        "## 必需场景顺序",
        "",
    ]
    for idx, name in enumerate(CAPTURE_ORDER, start=1):
        spec = SCENARIOS[name]
        lines.extend([
            f"### {idx}. {name}",
            "",
            f"- 目标：{spec['description']}",
            "- 操作：",
        ])
        lines.extend(f"  - {item}" for item in OPERATOR_STEPS[name])
        lines.extend([
            "- 必需证据正则：",
            "",
            "```text",
            *spec["required"],
            "```",
        ])
        if spec.get("recommended"):
            lines.extend([
                "- 推荐证据正则：",
                "",
                "```text",
                *spec["recommended"],
                "```",
            ])
        lines.append("")
    lines.extend([
        "## 漏采后的补采提示",
        "",
    ])
    lines.extend(f"- {item}" for item in next_actions(CAPTURE_ORDER))
    lines.extend([
        "",
        "## 验收口径",
        "",
        "采集完成后优先查看：",
        "",
        "```text",
        "capture_scenario_check.md",
        "self_lifecycle_logcat_check.md",
        "shuahuang_minimum_goal_check.md",
        "regression_artifact_check.md",
        "regression/summary.md",
        "regression/full_offline_replay.md",
        "regression/action_gate_readiness.md",
        "```",
        "",
        "必须看到：",
        "",
        "```text",
        "preflightReady=true",
        "captureScenarioRequiredReady=true",
        "selfLifecycleLogcatReady=true",
        "shuaHuangMinimumLiveEvidenceReady=true",
        "shuaHuangMinimumFinalReady=false  # 自研真实动作发送关闭时的预期值",
        "shuaHuangOfflineClosedLoopReplayReady=true",
        "dailyOfflineClosedLoopReplayReady=true",
        "mineOfflineClosedLoopReplayReady=true",
        "fullOfflineReplayReady=true",
        "dryRunActionEvidenceReady=true",
        "realActionNetworkAllowed=false",
        "realActionSendReady=false",
        "```",
        "",
        "如果 `fullOfflineReplayReady=false`，先查看 `regression/full_offline_replay.md` 中的 `Missing suites` 和各子回放报告；不要仅凭单个 parser 通过就判定真机回归完成。",
        "",
        "安全边界：本指南允许采集小黄点既有行为证据，不表示自研辅助可以发真实动作包。",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", default="")
    ap.add_argument("--mode", default="spawn")
    ap.add_argument("--duration", default="120")
    ap.add_argument("--base-channel-extra", default="")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    Path(ns.out).write_text(render_guide(ns.package, ns.mode, ns.duration, ns.base_channel_extra), encoding="utf-8")


if __name__ == "__main__":
    main()
