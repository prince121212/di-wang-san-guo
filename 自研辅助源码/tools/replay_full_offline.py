#!/usr/bin/env python3
"""Unified offline replay suite for migration regression artifacts.

This tool consumes channelExtra-style JSON and runs the recovered offline replay stack in
one place:

- brush-yellow minimum closed loop
- one-click daily flow
- 041542 mine/resource-point search
- replay contract audit
- action gate dry-run audit

It never contacts devices/servers and never enables real action sends.
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
verify_action_gate_readiness = load_tool("verify_action_gate_readiness")


def stringify(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def load_json(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    # Accept raw channelExtra and reports that contain channelExtra/baseChannelExtra.
    if isinstance(data.get("channelExtra"), dict):
        data = data["channelExtra"]
    elif isinstance(data.get("baseChannelExtra"), dict):
        data = data["baseChannelExtra"]
    return {str(k): stringify(v) for k, v in data.items() if v is not None and stringify(v) != ""}


def merge_inputs(input_path: Path, base: str | None = None, merges: list[str] | None = None) -> dict[str, str]:
    out: dict[str, str] = {}
    if base:
        out.update(load_json(Path(base)))
    out.update(load_json(input_path))
    for item in merges or []:
        out.update(load_json(Path(item)))
    return out


def json_array_len(raw: str | None) -> int:
    if not raw:
        return 0
    try:
        value = json.loads(raw)
    except Exception:
        return 0
    return len(value) if isinstance(value, list) else 0


def infer_target_type(extra: dict[str, str], explicit: str | None = None) -> str:
    if explicit in {"HUANG_JIN", "SHAN_ZEI"}:
        return explicit
    raw = (extra.get("shuaHuangTargetType") or extra.get("targetType") or "HUANG_JIN").upper()
    if raw in {"HUANG_JIN", "SHAN_ZEI"}:
        return raw
    return "SHAN_ZEI" if any(token in raw for token in ("山", "贼", "賊")) else "HUANG_JIN"


def build_action_gate_input(
    contract: dict[str, Any],
    shua: dict[str, Any],
    daily: dict[str, Any] | None,
    mine: dict[str, Any] | None,
) -> dict[str, Any]:
    parsed = shua.get("parsed", {}) if isinstance(shua.get("parsed"), dict) else {}
    return {
        "summary": {
            "shuaHuangOfflineClosedLoopReplayReady": bool(shua["summary"].get("shuaHuangOfflineClosedLoopReplayReady")),
            "dailyOfflineClosedLoopReplayReady": bool(daily and daily["summary"].get("dailyOfflineClosedLoopReplayReady")),
            "mineOfflineClosedLoopReplayReady": bool(mine and mine["summary"].get("mineOfflineClosedLoopReplayReady")),
            "targetParsedCount": len(parsed.get("targets", []) or []),
            "dispatchResultCount": 1 if shua["summary"].get("dispatchMatched") else 0,
            "dailyStepResultCount": 0 if not daily else int(daily["summary"].get("successStepCount", 0) or 0),
            "mineParsedCount": 0 if not mine else int(mine["summary"].get("mineCount", 0) or 0),
            "resourcePointActionPayloadEvidenceReady": bool(mine and mine["summary"].get("resourcePointActionPayloadEvidenceReady")),
            "withdrawPayloadEvidenceReady": bool(mine and mine["summary"].get("withdrawPayloadEvidenceReady")),
            "remainingActionDryRunEvidenceReady": bool(mine and mine["summary"].get("remainingActionDryRunEvidenceReady")),
            "realActionNetworkAllowed": False,
            "networkSendAllowed": False,
        },
        "replayContract": contract,
    }


def replay(
    extra: dict[str, str],
    target_type: str | None = None,
    start_x: int = 11,
    start_y: int = 22,
    require_daily: bool = True,
    require_mine: bool = True,
) -> dict[str, Any]:
    extra = verify_replay_contract.with_recovered_role_resource(extra)
    actual_target_type = infer_target_type(extra, target_type)
    contract = verify_replay_contract.verify(extra)
    shua = replay_shuahuang_offline.replay(extra, target_type=actual_target_type, start_x=start_x, start_y=start_y)
    daily = replay_daily_offline.replay(extra) if (require_daily or extra.get("dailyStepResultsJson")) else None
    mine = replay_mine_offline.replay(extra, start_x=11, start_y=22) if (require_mine or extra.get("mineTargetsJson") or extra.get("mineTargetsHex") or extra.get("resourcePointSearchResponseHex")) else None

    shua_ready = bool(shua["summary"].get("shuaHuangOfflineClosedLoopReplayReady"))
    daily_ready = bool(daily and daily["summary"].get("dailyOfflineClosedLoopReplayReady"))
    daily_protocol_ready = bool(daily and daily["summary"].get("dailyProtocolEvidenceReady"))
    daily_full_order_ready = bool(daily and daily["summary"].get("fullRecoveredOrder"))
    mine_ready = bool(mine and mine["summary"].get("mineOfflineClosedLoopReplayReady"))
    mine_readonly_ready = bool(mine and mine["summary"].get("mineReadOnlyEvidenceReady"))
    mine_selection_ready = bool(mine and mine["summary"].get("mineSelectionEvidenceReady"))
    resource_action_payload_ready = bool(mine and mine["summary"].get("resourcePointActionPayloadEvidenceReady"))
    withdraw_payload_ready = bool(mine and mine["summary"].get("withdrawPayloadEvidenceReady"))
    remaining_action_ready = bool(mine and mine["summary"].get("remainingActionDryRunEvidenceReady"))
    missing: list[str] = []
    if not shua_ready:
        missing.append("shuahuang")
    if require_daily and not daily_ready:
        missing.append("daily")
    if require_mine and not mine_ready:
        missing.append("mine")

    action_gate_input = build_action_gate_input(contract, shua, daily, mine)
    action_gate = verify_action_gate_readiness.audit(action_gate_input)
    full_ready = not missing
    parsed = shua.get("parsed", {}) if isinstance(shua.get("parsed"), dict) else {}
    return {
        "summary": {
            "fullOfflineReplayReady": full_ready,
            "shuaHuangOfflineClosedLoopReplayReady": shua_ready,
            "dailyOfflineClosedLoopReplayReady": daily_ready,
            "dailyProtocolEvidenceReady": daily_protocol_ready,
            "dailyFullRecoveredOrderReady": daily_full_order_ready,
            "mineOfflineClosedLoopReplayReady": mine_ready,
            "mineReadOnlyEvidenceReady": mine_readonly_ready,
            "mineSelectionEvidenceReady": mine_selection_ready,
            "resourcePointActionPayloadEvidenceReady": resource_action_payload_ready,
            "withdrawPayloadEvidenceReady": withdraw_payload_ready,
            "remainingActionDryRunEvidenceReady": remaining_action_ready,
            "shuaHuangContractReady": bool(contract["summary"].get("shuaHuangOfflineReplayReady")),
            "dailyContractReady": bool(contract["summary"].get("dailyOfflineReplayReady")),
            "mineContractReady": bool(contract["summary"].get("mineOfflineReplayReady")),
            "roleResourceParseReady": bool(contract["summary"].get("roleResourceParseReady")),
            "generalEvidenceParseReady": bool(contract["summary"].get("generalEvidenceParseReady")),
            "state8004GeneralEvidenceReady": bool(contract["summary"].get("state8004GeneralEvidenceReady")),
            "targetType": actual_target_type,
            "selectedFormationId": shua["summary"].get("selectedFormationId"),
            "selectedTargetId": shua["summary"].get("selectedTargetId"),
            "selectedMineId": None if mine is None else mine["summary"].get("selectedMineId"),
            "targetParsedCount": len(parsed.get("targets", []) or []),
            "dispatchResultCount": 1 if shua["summary"].get("dispatchMatched") else 0,
            "dailyStepResultCount": 0 if not daily else int(daily["summary"].get("successStepCount", 0) or 0),
            "mineParsedCount": 0 if not mine else int(mine["summary"].get("mineCount", 0) or 0),
            "dryRunActionEvidenceReady": bool(action_gate["summary"].get("dryRunActionEvidenceReady")),
            "realActionSendReady": False,
            "realActionNetworkAllowed": False,
            "blocker": "unified offline replay only; true live action send and device regression remain disabled/unproven",
        },
        "missingSuites": missing,
        "channelExtraPreview": {k: extra[k] for k in sorted(extra) if k not in {"tokenCiphertext", "password", "plainPassword"}},
        "replayContract": contract,
        "shuahuangReplay": shua,
        "dailyReplay": daily,
        "mineReplay": mine,
        "actionGateAudit": action_gate,
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# Full Offline Replay 统一验收报告",
        "",
        "## Summary",
        "",
        f"- fullOfflineReplayReady: {str(s['fullOfflineReplayReady']).lower()}",
        f"- shuaHuangOfflineClosedLoopReplayReady: {str(s['shuaHuangOfflineClosedLoopReplayReady']).lower()}",
        f"- dailyOfflineClosedLoopReplayReady: {str(s['dailyOfflineClosedLoopReplayReady']).lower()}",
        f"- dailyProtocolEvidenceReady: {str(s['dailyProtocolEvidenceReady']).lower()}",
        f"- dailyFullRecoveredOrderReady: {str(s['dailyFullRecoveredOrderReady']).lower()}",
        f"- mineOfflineClosedLoopReplayReady: {str(s['mineOfflineClosedLoopReplayReady']).lower()}",
        f"- mineReadOnlyEvidenceReady: {str(s['mineReadOnlyEvidenceReady']).lower()}",
        f"- mineSelectionEvidenceReady: {str(s['mineSelectionEvidenceReady']).lower()}",
        f"- resourcePointActionPayloadEvidenceReady: {str(s['resourcePointActionPayloadEvidenceReady']).lower()}",
        f"- withdrawPayloadEvidenceReady: {str(s['withdrawPayloadEvidenceReady']).lower()}",
        f"- remainingActionDryRunEvidenceReady: {str(s['remainingActionDryRunEvidenceReady']).lower()}",
        f"- shuaHuangContractReady: {str(s['shuaHuangContractReady']).lower()}",
        f"- dailyContractReady: {str(s['dailyContractReady']).lower()}",
        f"- mineContractReady: {str(s['mineContractReady']).lower()}",
        f"- roleResourceParseReady: {str(s['roleResourceParseReady']).lower()}",
        f"- generalEvidenceParseReady: {str(s['generalEvidenceParseReady']).lower()}",
        f"- state8004GeneralEvidenceReady: {str(s['state8004GeneralEvidenceReady']).lower()}",
        f"- targetType: {s['targetType']}",
        f"- selectedFormationId: {s['selectedFormationId']}",
        f"- selectedTargetId: {s['selectedTargetId']}",
        f"- selectedMineId: {s['selectedMineId']}",
        f"- targetParsedCount: {s['targetParsedCount']}",
        f"- dispatchResultCount: {s['dispatchResultCount']}",
        f"- dailyStepResultCount: {s['dailyStepResultCount']}",
        f"- mineParsedCount: {s['mineParsedCount']}",
        f"- dryRunActionEvidenceReady: {str(s['dryRunActionEvidenceReady']).lower()}",
        f"- realActionSendReady: {str(s['realActionSendReady']).lower()}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## Missing suites",
        "",
        "```json",
        json.dumps(report["missingSuites"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Action gate hard missing",
        "",
        "```json",
        json.dumps(report["actionGateAudit"].get("missing", []), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Replay contract missing",
        "",
        "```json",
        json.dumps(report["replayContract"].get("missing", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="channelExtra JSON, full sample, or report containing channelExtra/baseChannelExtra")
    ap.add_argument("--base", help="Optional base channelExtra JSON merged before input")
    ap.add_argument("--merge-extra", action="append", default=[], help="Additional channelExtra JSON merged after input; can repeat")
    ap.add_argument("--target-type", choices=["HUANG_JIN", "SHAN_ZEI"], help="Override brush-yellow target type")
    ap.add_argument("--start-x", type=int, default=11)
    ap.add_argument("--start-y", type=int, default=22)
    ap.add_argument("--no-require-daily", action="store_true")
    ap.add_argument("--no-require-mine", action="store_true")
    ap.add_argument("--out", help="Write JSON report; defaults to stdout")
    ap.add_argument("--markdown-out", help="Write Markdown report")
    ns = ap.parse_args()
    extra = merge_inputs(Path(ns.input), base=ns.base, merges=ns.merge_extra)
    report = replay(
        extra,
        target_type=ns.target_type,
        start_x=ns.start_x,
        start_y=ns.start_y,
        require_daily=not ns.no_require_daily,
        require_mine=not ns.no_require_mine,
    )
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
