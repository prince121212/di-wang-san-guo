#!/usr/bin/env python3
"""Offline replay of the recovered one-click daily flow.

Consumes channelExtra JSON and verifies the recovered daily execution order against
`dailyStepResultsJson`. It does not contact devices or servers and does not enable real
daily action sends.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

TOOL_DIR = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("verify_replay_contract", TOOL_DIR / "verify_replay_contract.py")
verify_replay_contract = importlib.util.module_from_spec(spec)
sys.modules["verify_replay_contract"] = verify_replay_contract
spec.loader.exec_module(verify_replay_contract)  # type: ignore[union-attr]

EXECUTION_ORDER = [
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
SIGN_IN_SEQUENCE = [
    "000000000000000000006200",
    "000000000000000000006202",
    "00000000000000000001620603",
    "00000000000000000001620607",
    "0000000000000000000162060e",
    "0000000000000000000162061c",
]
FIXED_PAYLOADS = {
    "SURPRISE_BOX": ["00000000000000000009113400000000000de2b100"],
    "ADD_LOYALTY": ["0000000000000000000c121f000000000000000002000000"],
    "COLLECT_TAX": ["00000000000000000004133001000001"],
    "ARENA_REWARD": ["000000000000000000006266"],
    "SALARY": ["00000000000000000001314b01"],
    "DELETE_MAIL": ["0000000000000000000a11160001ffffffffffffffff"],
}
SUCCESS_LOGS = {
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
UNRECOVERED_STEPS = {"ACHIEVEMENT_REWARD", "TASK_REWARD", "LEVEL_GIFT"}


def load_json(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return {str(k): stringify(v) for k, v in data.items() if v is not None and stringify(v) != ""}


def stringify(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def merge_inputs(input_path: Path, base: str | None = None, merges: list[str] | None = None) -> dict[str, str]:
    out: dict[str, str] = {}
    if base:
        out.update(load_json(Path(base)))
    out.update(load_json(input_path))
    for item in merges or []:
        out.update(load_json(Path(item)))
    return out


def parse_json(raw: str) -> Any | None:
    try:
        return json.loads(raw)
    except Exception:
        return None


def parse_bool(value: Any) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on", "success"}:
        return True
    if text in {"false", "0", "no", "off", "fail", "failed"}:
        return False
    return None


def amount_hex16(amount: int) -> str:
    return f"{amount:016x}"


def donation_payload(step: str, fz: int) -> list[str]:
    if step == "DONATE_FOOD":
        return ["00000000000000000018140c0000000000000000" + amount_hex16(fz * 3000) + "0000000000000000"]
    if step == "DONATE_COPPER":
        return ["00000000000000000018140c" + amount_hex16(fz * 1000) + "00000000000000000000000000000000"]
    if step == "DONATE_TECH":
        return ["00000000000000000005140a" + amount_hex16(fz * 1000)[-10:]]
    return []


def payloads_for(step: str, fz: int) -> list[str]:
    if step == "SIGN_IN":
        return SIGN_IN_SEQUENCE
    if step in FIXED_PAYLOADS:
        return FIXED_PAYLOADS[step]
    if step.startswith("DONATE_"):
        return donation_payload(step, fz)
    return []


def payload_hex_from_result(item: dict[str, Any] | None) -> str:
    if not item:
        return ""
    raw = item.get("payloadHex") or item.get("payload") or item.get("gameHex") or ""
    return "".join(ch for ch in str(raw).lower() if ch in "0123456789abcdef")


def daily_step_protocol_evidence(step: str, item: dict[str, Any] | None, expected_payloads: list[str], ok: bool) -> dict[str, Any]:
    captured_payload = payload_hex_from_result(item)
    delegated = step == "CONVERT_HALF_FOOD_TO_COPPER"
    payload_shape_recovered = bool(expected_payloads) or delegated
    captured_payload_matches = None
    if captured_payload:
        normalized_expected = {"".join(ch for ch in p.lower() if ch in "0123456789abcdef") for p in expected_payloads}
        captured_payload_matches = captured_payload in normalized_expected
    return {
        "protocolEvidenceReady": bool(ok and payload_shape_recovered and (captured_payload_matches is not False)),
        "delegatedStep": delegated,
        "payloadShapeRecovered": payload_shape_recovered,
        "expectedPayloadCount": len(expected_payloads),
        "capturedPayloadHex": captured_payload,
        "capturedPayloadMatchesExpected": captured_payload_matches,
    }


def parse_daily_results(extra: dict[str, str]) -> dict[str, dict[str, Any]]:
    value = parse_json(extra.get("dailyStepResultsJson", ""))
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(value, list):
        return out
    for item in value:
        if not isinstance(item, dict):
            continue
        step = str(item.get("step") or item.get("dailyStep") or "").strip().upper()
        if not step:
            continue
        out[step] = item
    return out


def configured_steps(extra: dict[str, str], results: dict[str, dict[str, Any]]) -> list[str]:
    raw = extra.get("dailyEnabledSteps") or extra.get("enabledDailySteps") or extra.get("dailySteps") or ""
    if raw.strip():
        value = parse_json(raw)
        if isinstance(value, list):
            requested = [str(x).strip().upper() for x in value if str(x).strip()]
        else:
            requested = [part.strip().upper() for part in re.split(r"[,;|\s]+", raw) if part.strip()]
    else:
        requested = list(results.keys())
    order = {step: idx for idx, step in enumerate(EXECUTION_ORDER)}
    return sorted(dict.fromkeys(requested), key=lambda s: order.get(s, 10_000))


def result_success(item: dict[str, Any] | None, expected_log: str = "") -> bool | None:
    if item is None:
        return None
    explicit = parse_bool(item.get("success"))
    if explicit is not None:
        return explicit
    text = str(item.get("message") or item.get("responseText") or "")
    if expected_log and expected_log in text:
        return True
    if "失败" in text or "error" in text.lower() or "fail" in text.lower():
        return False
    if "成功" in text or "完成" in text or "领取" in text or "已捐献" in text:
        return True
    return None


def replay(extra: dict[str, str], stop_on_failure: bool | None = None) -> dict[str, Any]:
    contract = verify_replay_contract.verify(extra)
    fz = int(str(extra.get("dailyDonationFactorFz") or extra.get("donationFactorFz") or "1"))
    if stop_on_failure is None:
        stop_on_failure = str(extra.get("dailyStopOnStepFailure") or "false").lower() in {"true", "1", "yes", "on"}
    results = parse_daily_results(extra)
    steps_requested = configured_steps(extra, results)
    steps: list[dict[str, Any]] = []
    stopped_at: str | None = None
    unrecovered_requested: list[str] = []
    for step in steps_requested:
        expected_payloads = payloads_for(step, fz)
        expected_log = SUCCESS_LOGS.get(step, "")
        item = results.get(step)
        success = result_success(item, expected_log)
        recovered = step in EXECUTION_ORDER
        if not recovered:
            unrecovered_requested.append(step)
        ok = recovered and item is not None and success is True
        protocol_evidence = daily_step_protocol_evidence(step, item, expected_payloads, ok)
        steps.append({
            "step": step,
            "recovered": recovered,
            "payloadCount": len(expected_payloads),
            "payloads": expected_payloads,
            "expectedSuccessLog": expected_log,
            "resultPresent": item is not None,
            "success": success,
            "ok": ok,
            "protocolEvidence": protocol_evidence,
            "message": "" if item is None else str(item.get("message") or item.get("responseText") or ""),
        })
        if stop_on_failure and (not ok):
            stopped_at = step
            break
    missing = []
    if not (extra.get("userId") and extra.get("serverUrl")):
        missing.append("identity:userId/serverUrl")
    if not steps_requested:
        missing.append("dailySteps:configured-or-captured")
    missing.extend([f"dailyStep:{s['step']}" for s in steps if not s["ok"]])
    if unrecovered_requested:
        missing.append("unrecoveredSteps:" + ",".join(unrecovered_requested))
    if contract["summary"]["dailyOfflineReplayReady"] is False:
        missing.append("dailyReplayContract")
    order_index = {step: idx for idx, step in enumerate(EXECUTION_ORDER)}
    order_matches_recovered = steps_requested == sorted(steps_requested, key=lambda s: order_index.get(s, 10_000))
    protocol_missing = [
        s["step"]
        for s in steps
        if not (isinstance(s.get("protocolEvidence"), dict) and s["protocolEvidence"].get("protocolEvidenceReady"))
    ]
    daily_protocol_evidence_ready = not protocol_missing and order_matches_recovered and bool(steps)
    full_recovered_order = steps_requested == EXECUTION_ORDER
    ready = not missing and daily_protocol_evidence_ready
    return {
        "summary": {
            "dailyOfflineClosedLoopReplayReady": ready,
            "contractReady": contract["summary"]["dailyOfflineReplayReady"],
            "dailyProtocolEvidenceReady": daily_protocol_evidence_ready,
            "fullRecoveredOrder": full_recovered_order,
            "orderMatchesRecoveredSequence": order_matches_recovered,
            "requestedStepCount": len(steps_requested),
            "executedStepCount": len(steps),
            "successStepCount": sum(1 for s in steps if s["ok"]),
            "protocolEvidenceStepCount": sum(
                1 for s in steps
                if isinstance(s.get("protocolEvidence"), dict) and s["protocolEvidence"].get("protocolEvidenceReady")
            ),
            "stoppedAt": stopped_at,
            "stopOnFailure": stop_on_failure,
            "donationFactorFz": fz,
            "realActionNetworkAllowed": False,
            "blocker": "offline daily replay only; true daily action send remains disabled",
        },
        "missingSteps": missing,
        "protocolMissingSteps": protocol_missing,
        "requestedSteps": steps_requested,
        "expectedRecoveredOrder": EXECUTION_ORDER,
        "steps": steps,
        "dailyStepResults": results,
        "replayContract": contract,
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 一键日常离线回放报告",
        "",
        "## Summary",
        "",
        f"- dailyOfflineClosedLoopReplayReady: {str(s['dailyOfflineClosedLoopReplayReady']).lower()}",
        f"- contractReady: {str(s['contractReady']).lower()}",
        f"- dailyProtocolEvidenceReady: {str(s['dailyProtocolEvidenceReady']).lower()}",
        f"- fullRecoveredOrder: {str(s['fullRecoveredOrder']).lower()}",
        f"- orderMatchesRecoveredSequence: {str(s['orderMatchesRecoveredSequence']).lower()}",
        f"- requestedStepCount: {s['requestedStepCount']}",
        f"- executedStepCount: {s['executedStepCount']}",
        f"- successStepCount: {s['successStepCount']}",
        f"- protocolEvidenceStepCount: {s['protocolEvidenceStepCount']}",
        f"- stoppedAt: {s['stoppedAt']}",
        f"- stopOnFailure: {str(s['stopOnFailure']).lower()}",
        f"- donationFactorFz: {s['donationFactorFz']}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## Missing steps",
        "",
        "```json",
        json.dumps(report["missingSteps"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Protocol missing steps",
        "",
        "```json",
        json.dumps(report["protocolMissingSteps"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Expected recovered order",
        "",
        "```json",
        json.dumps(report["expectedRecoveredOrder"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Replayed steps",
        "",
        "```json",
        json.dumps(report["steps"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="channelExtra JSON containing dailyStepResultsJson")
    ap.add_argument("--base", help="Optional base channelExtra JSON merged before input")
    ap.add_argument("--merge-extra", action="append", default=[], help="Additional channelExtra JSON merged after input; can repeat")
    ap.add_argument("--stop-on-failure", action="store_true", help="Stop replay at first failed/missing daily step")
    ap.add_argument("--out", help="Write JSON report; defaults to stdout")
    ap.add_argument("--markdown-out", help="Write Markdown report")
    ns = ap.parse_args()
    extra = merge_inputs(Path(ns.input), base=ns.base, merges=ns.merge_extra)
    report = replay(extra, stop_on_failure=ns.stop_on_failure if ns.stop_on_failure else None)
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
