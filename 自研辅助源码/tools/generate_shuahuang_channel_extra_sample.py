#!/usr/bin/env python3
"""Generate a safe brush-yellow channelExtra sample for offline replay and capture alignment.

The output is intentionally local/offline only: it contains no password/token and forces all
known network/action flags to false. It is useful as a golden fixture for:

- login/session metadata contract
- role/resource state
- general/formation state
- 041540 target import
- 1520030/1522030 dispatch result import
- stop/logout local lifecycle evidence
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

TOOL_DIR = Path(__file__).resolve().parent


def load_tool(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOL_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


verify_replay_contract = load_tool("verify_replay_contract")
replay_shuahuang_offline = load_tool("replay_shuahuang_offline")
replay_daily_offline = load_tool("replay_daily_offline")
replay_mine_offline = load_tool("replay_mine_offline")

SAFE_FALSE_FLAGS = {
    "networkSendAllowed": "false",
    "deviceRegressionNetworkSendAllowed": "false",
    "actionResponseCalibrationNetworkSendAllowed": "false",
    "nativeWrapperNetworkSendAllowed": "false",
    "realActionNetworkAllowed": "false",
    "sampleNetworkSendAllowed": "false",
}


def build_sample(
    role_name: str = "样本君主",
    target_type: str = "HUANG_JIN",
    target_alias_style: str = "captured",
    include_daily: bool = False,
    include_mine: bool = False,
) -> dict[str, str]:
    """Return channelExtra-style sample data that can pass offline brush-yellow replay."""
    target_type = target_type if target_type in {"HUANG_JIN", "SHAN_ZEI"} else "HUANG_JIN"
    huang_target = {
        "targetIdHex": "0000000000000065",
        "coordX": 11,
        "coordY": 22,
        "targetKind": "渠帅",
        "targetLevel": 11,
        "rawRecord": "sample-041540-huang-target",
    } if target_alias_style == "captured" else {
        "id": "101",
        "x": 11,
        "y": 22,
        "type": "黄巾",
        "rank": 11,
    }
    shan_target = {
        "targetID": "102",
        "kv": 33,
        "kw": 44,
        "kind": "山贼",
        "level": 4,
    } if target_alias_style == "captured" else {
        "id": "102",
        "x": 33,
        "y": 44,
        "type": "山贼",
        "rank": 4,
    }
    selected_target_id_hex = "0000000000000065" if target_type == "HUANG_JIN" else "0000000000000066"
    selected_target_id = "101" if target_type == "HUANG_JIN" else "102"
    selected_response = "刷黄出征成功！继续搜索... usedCount=1"

    extra: dict[str, str] = {
        "sourceMode": "1",
        "userId": "sample-user-10001",
        "serverUrl": "http://game.example",
        "dm": "999",
        "roleName": role_name,
        "level": "42",
        "nation": "蜀",
        "copper": "1234567",
        "food": "6543210",
        "prestige": "98765",
        "state8004TailUtf8Preview": (
            f"君主名={role_name}|君主等级=42|国家=蜀|铜钱=1234567|粮食=6543210|"
            "JiangLing{id=0000000000000007,name=赵云,status=0,tili=49,daiBingLimit=1999,isPeiBingFail=false}"
        ),
        "xiaohuangPrefsJson": json.dumps({
            "shuahuangChuzhengBiandui0": True,
            "bianduihao0": "0000000000000003",
            "bianduiDejiangling0": "0000000000000007",
            "bingli0": "1999",
        }, ensure_ascii=False, separators=(",", ":")),
        "mapTargetsJson": json.dumps([huang_target, shan_target], ensure_ascii=False, separators=(",", ":")),
        "dispatchResultsJson": json.dumps([{
            "bianduihao": "0000000000000003",
            "targetIdHex": selected_target_id_hex,
            "targetId": selected_target_id,
            "status": "成功",
            "usedCount": 1,
            "responseBody": selected_response,
            "generalIdHexChunks": ["0000000000000007"],
            "raw": {"source": "generate_shuahuang_channel_extra_sample.py"},
        }], ensure_ascii=False, separators=(",", ":")),
        "selectedFormationIds": "3",
        "shuaHuangTargetType": target_type,
        "shuahuangSampleGenerator": "tools/generate_shuahuang_channel_extra_sample.py",
    }
    if include_daily:
        extra.update(build_daily_fields())
    if include_mine:
        extra.update(build_mine_fields())
    extra.update(SAFE_FALSE_FLAGS)
    return extra


def build_daily_fields() -> dict[str, str]:
    steps = [
        "SIGN_IN",
        "SURPRISE_BOX",
        "ADD_LOYALTY",
        "COLLECT_TAX",
        "ARENA_REWARD",
        "SALARY",
        "DELETE_MAIL",
        "DONATE_COPPER",
        "DONATE_FOOD",
        "DONATE_TECH",
        "CONVERT_HALF_FOOD_TO_COPPER",
    ]
    success_logs = {
        "SIGN_IN": "已完成签到！",
        "SURPRISE_BOX": "已领取惊喜宝箱！",
        "ADD_LOYALTY": "已一键加忠！",
        "COLLECT_TAX": "已一键征收！",
        "ARENA_REWARD": "已领取竞技奖励！",
        "SALARY": "已领取俸禄！",
        "DELETE_MAIL": "已删除邮件！",
        "DONATE_COPPER": "已捐献铜钱！",
        "DONATE_FOOD": "已捐献粮食！",
        "DONATE_TECH": "已捐献科技！",
        "CONVERT_HALF_FOOD_TO_COPPER": "已转换一半粮食到铜钱！",
    }
    return {
        "dailyEnabledSteps": ",".join(steps),
        "dailyDonationFactorFz": "1",
        "dailyStepResultsJson": json.dumps(
            [{"step": step, "success": True, "message": success_logs[step]} for step in steps],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }


def build_mine_fields() -> dict[str, str]:
    return {
        "mineTargetsHex": "0000000001010101000b0016010002D00101000000270F00000000010202020021002c000002D0020200000022B8",
        "selectedMineTypes": "GOLD,SILVER",
        "onlyEmptyMine": "true",
        "hitEmptyMine": "true",
        "mineSelectedFormationIds": "3",
    }


def generate_report(extra: dict[str, str], target_type: str = "HUANG_JIN", start_x: int = 11, start_y: int = 22) -> dict[str, Any]:
    contract = verify_replay_contract.verify(extra)
    replay = replay_shuahuang_offline.replay(extra, target_type=target_type, start_x=start_x, start_y=start_y)
    target_selection = replay["summary"].get("targetSelectionEvidence", {})
    if not isinstance(target_selection, dict):
        target_selection = {}
    dispatch_payload = replay["summary"].get("dispatchPayloadEvidence", {})
    if not isinstance(dispatch_payload, dict):
        dispatch_payload = {}
    daily_replay = replay_daily_offline.replay(extra) if extra.get("dailyStepResultsJson") else None
    mine_replay = replay_mine_offline.replay(extra, start_x=11, start_y=22) if (extra.get("mineTargetsJson") or extra.get("mineTargetsHex") or extra.get("resourcePointSearchResponseHex")) else None
    return {
        "summary": {
            "shuaHuangOfflineReplayReady": bool(replay["summary"]["shuaHuangOfflineClosedLoopReplayReady"]),
            "dailyOfflineReplayReady": bool(daily_replay and daily_replay["summary"].get("dailyOfflineClosedLoopReplayReady")),
            "dailyProtocolEvidenceReady": bool(daily_replay and daily_replay["summary"].get("dailyProtocolEvidenceReady")),
            "dailyFullRecoveredOrderReady": bool(daily_replay and daily_replay["summary"].get("fullRecoveredOrder")),
            "mineOfflineReplayReady": bool(mine_replay and mine_replay["summary"].get("mineOfflineClosedLoopReplayReady")),
            "mineReadOnlyEvidenceReady": bool(mine_replay and mine_replay["summary"].get("mineReadOnlyEvidenceReady")),
            "mineSelectionEvidenceReady": bool(mine_replay and mine_replay["summary"].get("mineSelectionEvidenceReady")),
            "contractReady": bool(contract["summary"]["shuaHuangOfflineReplayReady"]),
            "dailyContractReady": bool(contract["summary"].get("dailyOfflineReplayReady")),
            "mineContractReady": bool(contract["summary"].get("mineOfflineReplayReady")),
            "targetType": target_type,
            "selectedFormationId": replay["summary"].get("selectedFormationId"),
            "selectedTargetId": replay["summary"].get("selectedTargetId"),
            "targetSelectionEvidenceReady": bool(target_selection.get("targetSelectionEvidenceReady")),
            "strictTargetTypeMatch": bool(target_selection.get("strictTargetTypeMatch")),
            "filterMatchedCount": int(target_selection.get("filterMatchedCount") or 0),
            "typeMatchedCount": int(target_selection.get("typeMatchedCount") or 0),
            "dispatchPayloadEvidenceReady": bool(dispatch_payload.get("dispatchPayloadEvidenceReady")),
            "preparePayload": dispatch_payload.get("preparePayload", ""),
            "expeditionPayload": dispatch_payload.get("expeditionPayload", ""),
            "dispatchMatched": replay["summary"].get("dispatchMatched"),
            "dispatchSuccess": replay["summary"].get("dispatchSuccess"),
            "realActionNetworkAllowed": False,
            "blocker": "sample/offline replay only; true 1520030/1522030/daily/mine action send remains disabled",
        },
        "channelExtra": extra,
        "replay": replay,
        "dailyReplay": daily_replay,
        "mineReplay": mine_replay,
        "replayContract": contract,
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 刷黄 ChannelExtra 样本生成报告",
        "",
        "## Summary",
        "",
        f"- shuaHuangOfflineReplayReady: {str(s['shuaHuangOfflineReplayReady']).lower()}",
        f"- contractReady: {str(s['contractReady']).lower()}",
        f"- dailyOfflineReplayReady: {str(s['dailyOfflineReplayReady']).lower()}",
        f"- dailyProtocolEvidenceReady: {str(s['dailyProtocolEvidenceReady']).lower()}",
        f"- dailyFullRecoveredOrderReady: {str(s['dailyFullRecoveredOrderReady']).lower()}",
        f"- dailyContractReady: {str(s['dailyContractReady']).lower()}",
        f"- mineOfflineReplayReady: {str(s['mineOfflineReplayReady']).lower()}",
        f"- mineReadOnlyEvidenceReady: {str(s['mineReadOnlyEvidenceReady']).lower()}",
        f"- mineSelectionEvidenceReady: {str(s['mineSelectionEvidenceReady']).lower()}",
        f"- mineContractReady: {str(s['mineContractReady']).lower()}",
        f"- targetType: {s['targetType']}",
        f"- selectedFormationId: {s['selectedFormationId']}",
        f"- selectedTargetId: {s['selectedTargetId']}",
        f"- targetSelectionEvidenceReady: {str(s['targetSelectionEvidenceReady']).lower()}",
        f"- strictTargetTypeMatch: {str(s['strictTargetTypeMatch']).lower()}",
        f"- filterMatchedCount: {s['filterMatchedCount']}",
        f"- typeMatchedCount: {s['typeMatchedCount']}",
        f"- dispatchPayloadEvidenceReady: {str(s['dispatchPayloadEvidenceReady']).lower()}",
        f"- dispatchMatched: {str(s['dispatchMatched']).lower()}",
        f"- dispatchSuccess: {str(s['dispatchSuccess']).lower()}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## Replay missing steps",
        "",
        "```json",
        json.dumps(report["replay"].get("missingSteps", []), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Contract missing",
        "",
        "```json",
        json.dumps(report["replayContract"].get("missing", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Safe flags",
        "",
        "```json",
        json.dumps({k: report["channelExtra"].get(k) for k in sorted(SAFE_FALSE_FLAGS)}, ensure_ascii=False, indent=2),
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role-name", default="样本君主")
    ap.add_argument("--target-type", choices=["HUANG_JIN", "SHAN_ZEI"], default="HUANG_JIN")
    ap.add_argument("--target-alias-style", choices=["captured", "canonical"], default="captured")
    ap.add_argument("--profile", choices=["shuahuang", "full"], default="shuahuang", help="full includes daily and mine replay fields")
    ap.add_argument("--include-daily", action="store_true", help="Include one-click daily replay fields")
    ap.add_argument("--include-mine", action="store_true", help="Include 041542 mine replay fields")
    ap.add_argument("--start-x", type=int, default=11)
    ap.add_argument("--start-y", type=int, default=22)
    ap.add_argument("--out", help="Write channelExtra JSON")
    ap.add_argument("--report-out", help="Write full JSON report")
    ap.add_argument("--markdown-out", help="Write Markdown report")
    ns = ap.parse_args()

    include_daily = ns.include_daily or ns.profile == "full"
    include_mine = ns.include_mine or ns.profile == "full"
    extra = build_sample(
        role_name=ns.role_name,
        target_type=ns.target_type,
        target_alias_style=ns.target_alias_style,
        include_daily=include_daily,
        include_mine=include_mine,
    )
    report = generate_report(extra, target_type=ns.target_type, start_x=ns.start_x, start_y=ns.start_y)
    if ns.out:
        Path(ns.out).write_text(json.dumps(extra, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if ns.report_out:
        Path(ns.report_out).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")
    if not ns.out and not ns.report_out and not ns.markdown_out:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
