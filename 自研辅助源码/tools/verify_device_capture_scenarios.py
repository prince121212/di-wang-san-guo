#!/usr/bin/env python3
"""Verify scenario coverage in raw Frida/logcat capture text.

This checks whether a device capture contains the marker families needed for the current
migration objective. It does not parse protocol deeply and does not send network traffic.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SCENARIOS = {
    "loginState8004": {
        "description": "登录/0x8004 角色资源与将领状态证据",
        "required": [
            r"0x8004|\"opcode\"\s*:\s*\"(?:0x)?8004\"|state8004PayloadHex|state8004TailHex|08101600000000|000000000000000000081016",
            r"roleName|君主名|角色名|copper|铜钱|銅錢|food|粮食|糧食|roleStateJson|resourceStateJson",
        ],
        "recommended": [r"JiangLing|state8004TailUtf8Preview|state8004TailHex|bF|将领|將領|武将|武將"],
    },
    "nativeWrapper": {
        "description": "native/session wrapper captures",
        "required": [r"\[native-wrapper-json\]", r"\[game-wrapper-call\]|\[java-native-ret\]"],
        "recommended": [r"HelpClass\.getKey|recoveredNativeKey|nativeWrapperKey"],
    },
    "generalFormationBaseline": {
        "description": "将领/编队基线证据，用于刷黄出征编队选择",
        "required": [
            r"JiangLing|generalsJson|generalStateJson|bianduiDejiangling|将领|將領|武将|武將",
            r"formationsJson|formationStateJson|shuahuangChuzhengBiandui|bianduihao|编队|編隊",
        ],
        "recommended": [
            r"canDispatch|status\s*[=:]\s*0|tili|energy|daiBingLimit|bingli|兵力",
            r"selectedFormationIds|shuaHuangSelectedFormationIds|shuahuangChuzhengBiandui",
        ],
    },
    "brushYellowNativeWrapper1520": {
        "description": "刷黄 1520030/1522030 两段 native wrapper 样本",
        "required": [
            r"\[native-wrapper-json\].*1520030|\"gameHex\"\s*:\s*\"[^\"]*1520030[^\"]*\"",
            r"\[native-wrapper-json\].*1522030|\"gameHex\"\s*:\s*\"[^\"]*1522030[^\"]*\"",
        ],
        "recommended": [r"lx|nativeWrapperLx|rawBody", r"lb|nativeWrapperLb|rawBody"],
    },
    "brushYellowSearch041540": {
        "description": "刷黄/找黄 041540 只读响应",
        "required": [r"\[readonly-response-json\].*041540|\"opcode\"\s*:\s*\"041540\""],
        "recommended": [r"黄巾|黃巾|山贼|山賊|E9BB84E5B7BE|E5B1B1E8B4BC"],
    },
    "brushYellowDispatch1522030": {
        "description": "刷黄出征 1522030 动作响应样本",
        "required": [r"\[action-response-json\].*1522030|\"opcode\"\s*:\s*\"1522030\""],
        "recommended": [r"刷黄出征成功|出征成功|usedAount|targetId|formationId"],
    },
    "selfStopLogout": {
        "description": "自研辅助停止任务与退出登录/释放 session 证据",
        "required": [
            r"\[self-lifecycle-json\].*\"event\"\s*:\s*\"(?:task_stop|scheduler_stop|service_stop|stop)\"|LocalSchedulerLifecycleRunner.*(?:stop|stopped)|TaskScheduler.*(?:stop|stopped)|停止任务|任务已停止",
            r"\[self-lifecycle-json\].*\"event\"\s*:\s*\"(?:logout|session_logout|service_logout)\"|logout(?:Once| exactly once| success| complete| completed)?|退出登录|已退出登录|释放session|释放 session",
        ],
        "recommended": [
            r"sourceMode\s*[=:]\s*1|\"sourceMode\"\s*:\s*1|realSession|真实只读",
            r"logoutOnce|logout exactly once|terminal|foreground service stopped|AssistantForegroundService",
        ],
    },
    "daily": {
        "description": "一键日常响应样本",
        "required": [r"\[daily-response-json\]|\"dailyStep\"\s*:|\"step\"\s*:\s*\"SIGN_IN\""],
        "recommended": [r"已完成签到|已领取惊喜宝箱|已一键加忠|已捐献"],
    },
    "mineSearch041542": {
        "description": "找矿/资源点 041542 只读响应",
        "required": [r"\[readonly-response-json\].*041542|\"opcode\"\s*:\s*\"041542\""],
        "recommended": [r"resourcePoint|mineTargets|041542|02D[0-9A-Fa-f]{3}"],
    },
}


def count_patterns(text: str, patterns: list[str]) -> dict[str, int]:
    return {pattern: len(re.findall(pattern, text, flags=re.I | re.S)) for pattern in patterns}


def verify_text(text: str) -> dict[str, Any]:
    scenarios: dict[str, Any] = {}
    missing_required: list[str] = []
    missing_recommended: list[str] = []
    for name, spec in SCENARIOS.items():
        required_counts = count_patterns(text, spec["required"])
        recommended_counts = count_patterns(text, spec["recommended"])
        required_ok = all(count > 0 for count in required_counts.values())
        recommended_ok = all(count > 0 for count in recommended_counts.values()) if spec["recommended"] else True
        if not required_ok:
            missing_required.append(name)
        if not recommended_ok:
            missing_recommended.append(name)
        scenarios[name] = {
            "description": spec["description"],
            "requiredOk": required_ok,
            "recommendedOk": recommended_ok,
            "requiredCounts": required_counts,
            "recommendedCounts": recommended_counts,
        }
    all_required = not missing_required
    return {
        "summary": {
            "captureScenarioRequiredReady": all_required,
            "captureScenarioRecommendedReady": all_required and not missing_recommended,
            "scenarioCount": len(SCENARIOS),
            "missingRequiredCount": len(missing_required),
            "missingRecommendedCount": len(missing_recommended),
            "realActionNetworkAllowed": False,
            "blocker": "capture scenario coverage only; true action send remains disabled",
        },
        "missingRequired": missing_required,
        "missingRecommended": missing_recommended,
        "scenarios": scenarios,
        "nextManualActions": next_actions(missing_required or missing_recommended),
    }


def next_actions(missing: list[str]) -> list[str]:
    hints = {
        "loginState8004": "完成一次自研只读登录或小黄点登录初始化采集，确认日志中包含 0x8004/state8004PayloadHex 以及 roleName/level/copper/food 或中文角色资源字段；推荐同时保留 JiangLing/将领证据。",
        "nativeWrapper": "启动小黄点并执行任一会触发请求的操作，确认 Frida 输出 [native-wrapper-json] 与 HelpClass/Dbsl 返回。",
        "generalFormationBaseline": "在刷黄出征前导出或采集将领与编队基线，确认日志/merged channelExtra 中同时包含 JiangLing/generalsJson 和 formationsJson 或 shuahuangChuzhengBiandui/bianduihao。",
        "brushYellowNativeWrapper1520": "在隔离账号中完整触发一次刷黄出征，确认 Frida 输出同时包含 1520030 与 1522030 的 [native-wrapper-json]；自研侧仍不发包。",
        "brushYellowSearch041540": "在小黄点中执行一次找黄/刷黄搜索，让日志出现 041540 readonly-response-json。",
        "brushYellowDispatch1522030": "在隔离账号中执行一次刷黄出征样本采集，让日志出现 1522030 action-response-json；自研侧仍不发包。",
        "selfStopLogout": "在自研辅助中停止本地调度/前台服务并退出登录，确认日志包含 task_stop/scheduler_stop 与 logout/session_logout；真实动作发送仍保持关闭。",
        "daily": "执行一键日常中的签到/宝箱/加忠/三捐任一或多项，让日志出现 daily-response-json。",
        "mineSearch041542": "执行找矿/资源点扫描，让日志出现 041542 readonly-response-json。",
    }
    return [hints[name] for name in missing if name in hints]


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 设备采集场景覆盖检查",
        "",
        "## Summary",
        "",
        f"- captureScenarioRequiredReady: {str(s['captureScenarioRequiredReady']).lower()}",
        f"- captureScenarioRecommendedReady: {str(s['captureScenarioRecommendedReady']).lower()}",
        f"- scenarioCount: {s['scenarioCount']}",
        f"- missingRequiredCount: {s['missingRequiredCount']}",
        f"- missingRecommendedCount: {s['missingRecommendedCount']}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## Missing required",
        "",
        "```json",
        json.dumps(report["missingRequired"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Missing recommended",
        "",
        "```json",
        json.dumps(report["missingRecommended"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Next manual actions",
        "",
    ]
    lines.extend(f"- {item}" for item in report["nextManualActions"])
    lines += [
        "",
        "## Scenario evidence",
        "",
        "```json",
        json.dumps(report["scenarios"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="device_combined.log, frida.log or any capture text")
    ap.add_argument("--out", help="Write JSON report; defaults to stdout")
    ap.add_argument("--markdown-out", help="Write Markdown report")
    ns = ap.parse_args()
    text = Path(ns.input).read_text(encoding="utf-8", errors="replace")
    report = verify_text(text)
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
