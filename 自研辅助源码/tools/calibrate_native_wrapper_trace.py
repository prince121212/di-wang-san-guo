#!/usr/bin/env python3
"""Generate a stability calibration report for 小黄点 native wrapper captures.

This consumes logs from frida_native_session_trace_v2.js and summarizes multiple
[native-wrapper-json] RequestBody captures to answer:
- are prefix/suffix lengths stable?
- can prefix be split as lx+key using imported native returns?
- does suffix behave like lb?

It is offline-only and never sends network requests.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

IMPORTER_PATH = Path(__file__).with_name("import_native_session_trace.py")
spec = importlib.util.spec_from_file_location("import_native_session_trace", IMPORTER_PATH)
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)  # type: ignore[union-attr]


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def opcode_markers(game_hex: str) -> list[str]:
    normalized = "".join(ch for ch in str(game_hex).lower() if ch in "0123456789abcdef")
    markers: list[str] = []
    marker_map = {
        "1520030": "brush_yellow_prepare_1520030",
        "1522030": "brush_yellow_dispatch_1522030",
        "1520010": "resource_point_prepare_1520010",
        "1522010": "resource_point_dispatch_1522010",
        "0a15260101": "withdraw_defense_0a15260101",
        "041540": "readonly_target_041540",
        "041542": "readonly_resource_041542",
    }
    for needle, marker in marker_map.items():
        if needle in normalized:
            markers.append(marker)
    if not markers:
        markers.append("unknown_or_unmapped")
    return markers


def wrapper_events(text: str, known: dict[str, str], include_values: bool = False) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        m = importer.WRAPPER_JSON.search(line)
        if not m:
            continue
        try:
            obj = json.loads(m.group("json"))
        except Exception:
            continue
        raw = obj.get("rawBody") or obj.get("body") or obj.get("requestBody")
        game_hex = str(obj.get("gameHex") or "")
        if not raw or not game_hex or game_hex not in str(raw):
            continue
        raw = str(raw)
        prefix, suffix = raw.split(game_hex, 1)
        event: dict[str, Any] = {
            "source": obj.get("source", ""),
            "threadId": obj.get("threadId", ""),
            "gameHex": game_hex,
            "gameHexLength": len(game_hex),
            "gameHexByteLength": len("".join(ch for ch in game_hex if ch in "0123456789abcdefABCDEF")) // 2,
            "gameHexSha256": sha(game_hex),
            "opcodeMarkers": opcode_markers(game_hex),
            "primaryOpcodeMarker": opcode_markers(game_hex)[0],
            "rawBodySha256": sha(raw),
            "rawBodyLength": len(raw),
            "prefixLength": len(prefix),
            "suffixLength": len(suffix),
            "prefixSha256": sha(prefix),
            "suffixSha256": sha(suffix),
        }
        lx = obj.get("lx") or known.get("nativeWrapperLx") or known.get("recoveredNativeLx") or known.get("derivedNativeWrapperLx")
        key = obj.get("key") or known.get("nativeWrapperKey") or known.get("recoveredNativeKey") or known.get("helpClassKey") or known.get("dbslGk") or known.get("derivedNativeWrapperKey")
        lb = obj.get("lb") or known.get("nativeWrapperLb") or known.get("recoveredNativeLb") or known.get("derivedNativeWrapperLb")
        statuses = []
        if lx and prefix.startswith(str(lx)):
            statuses.append("prefix_starts_with_lx")
            event["derivedKeySha256"] = sha(prefix[len(str(lx)):])
            if include_values:
                event["derivedKey"] = prefix[len(str(lx)):]
        if key and prefix.endswith(str(key)):
            statuses.append("prefix_ends_with_key")
            event["derivedLxSha256"] = sha(prefix[:-len(str(key))])
            if include_values:
                event["derivedLx"] = prefix[:-len(str(key))]
        if lx and key and prefix == str(lx) + str(key):
            statuses.append("prefix_equals_lx_plus_key")
        if lb and suffix == str(lb):
            statuses.append("suffix_equals_lb")
        elif suffix:
            statuses.append("suffix_assumed_lb")
            event["derivedLbSha256"] = sha(suffix)
            if include_values:
                event["derivedLb"] = suffix
        if not statuses:
            statuses.append("unsplit")
        event["splitStatus"] = statuses
        if include_values:
            event["prefix"] = prefix
            event["suffix"] = suffix
            event["rawBody"] = raw
        events.append(event)
    return events


def stability(values: list[Any]) -> dict[str, Any]:
    unique = []
    for v in values:
        if v not in unique:
            unique.append(v)
    return {"uniqueCount": len(unique), "stable": len(unique) <= 1, "values": unique}


def calibrate(text: str, include_values: bool = False) -> dict[str, Any]:
    extra = importer.parse(text, include_raw_body=include_values)
    events = wrapper_events(text, extra, include_values=include_values)
    split_statuses = sorted({s for e in events for s in e.get("splitStatus", [])})
    marker_counts = opcode_marker_counts(events)
    brush_yellow_details = brush_yellow_wrapper_details(events)
    remaining_action_details = remaining_action_wrapper_details(events)
    readiness = readiness_summary(events, split_statuses)
    summary = {
        "captureCount": len(events),
        "uniqueGameHexCount": len({e["gameHexSha256"] for e in events}),
        "nativeWrapperFieldAudit": parse_field_audit(extra),
        "opcodeMarkerCounts": marker_counts,
        "brushYellowWrapperCoverage": {
            "prepare1520030": marker_counts.get("brush_yellow_prepare_1520030", 0),
            "dispatch1522030": marker_counts.get("brush_yellow_dispatch_1522030", 0),
            "complete": marker_counts.get("brush_yellow_prepare_1520030", 0) > 0 and marker_counts.get("brush_yellow_dispatch_1522030", 0) > 0,
        },
        "brushYellowWrapperDetails": brush_yellow_details,
        "remainingActionWrapperDetails": remaining_action_details,
        "prefixLength": stability([e["prefixLength"] for e in events]),
        "suffixLength": stability([e["suffixLength"] for e in events]),
        "prefixHash": stability([e["prefixSha256"] for e in events]),
        "suffixHash": stability([e["suffixSha256"] for e in events]),
        "splitStatuses": split_statuses,
        "actionSendReady": readiness["actionSendReady"],
        "readinessLevel": readiness["readinessLevel"],
        "readinessReasons": readiness["reasons"],
        "networkSendAllowed": False,
        "blocker": "native wrapper calibration report only; true action send remains disabled until lx/key/lb semantics and response parser are verified",
    }
    return {
        "summary": summary,
        "channelExtraCandidate": extra,
        "captures": events,
    }


def readiness_summary(events: list[dict[str, Any]], split_statuses: list[str]) -> dict[str, Any]:
    reasons: list[str] = []
    if not events:
        reasons.append("no native-wrapper-json captures")
    if len({e.get("gameHexSha256") for e in events}) < 2:
        reasons.append("less than two unique gameHex captures")
    if "unsplit" in split_statuses or not split_statuses:
        reasons.append("wrapper prefix/suffix not fully split")
    if "prefix_equals_lx_plus_key" not in split_statuses and not ({"prefix_starts_with_lx", "prefix_ends_with_key"} <= set(split_statuses)):
        reasons.append("lx/key boundary not proven by captures")
    if "suffix_equals_lb" not in split_statuses and "suffix_assumed_lb" not in split_statuses:
        reasons.append("lb/suffix boundary not observed")
    # Even when all calibration evidence is present, the app must still keep real action
    # sends disabled until response semantics and user-controlled safety gate are added.
    reasons.append("real action network gate intentionally remains disabled in self-developed app")
    return {
        "actionSendReady": False,
        "readinessLevel": "dry_run_only",
        "reasons": reasons,
    }


def parse_field_audit(extra: dict[str, str]) -> dict[str, Any]:
    raw = extra.get("nativeWrapperFieldAuditJson", "")
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except Exception:
        return {"parseError": "nativeWrapperFieldAuditJson invalid"}
    return value if isinstance(value, dict) else {}


def opcode_marker_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        for marker in event.get("opcodeMarkers", []):
            counts[marker] = counts.get(marker, 0) + 1
    return counts


def event_split_proven(event: dict[str, Any]) -> bool:
    statuses = set(event.get("splitStatus", []))
    return (
        "prefix_equals_lx_plus_key" in statuses or
        {"prefix_starts_with_lx", "prefix_ends_with_key"}.issubset(statuses)
    ) and ("suffix_equals_lb" in statuses or "suffix_assumed_lb" in statuses) and "unsplit" not in statuses


def compact_hashes(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def marker_detail(events: list[dict[str, Any]], marker: str) -> dict[str, Any]:
    matched = [event for event in events if marker in event.get("opcodeMarkers", [])]
    return {
        "count": len(matched),
        "splitProven": bool(matched) and all(event_split_proven(event) for event in matched),
        "splitStatuses": sorted({status for event in matched for status in event.get("splitStatus", [])}),
        "gameHexLength": stability([event.get("gameHexLength") for event in matched]),
        "gameHexByteLength": stability([event.get("gameHexByteLength") for event in matched]),
        "rawBodyLength": stability([event.get("rawBodyLength") for event in matched]),
        "prefixLength": stability([event.get("prefixLength") for event in matched]),
        "suffixLength": stability([event.get("suffixLength") for event in matched]),
        "prefixHash": stability([event.get("prefixSha256") for event in matched]),
        "suffixHash": stability([event.get("suffixSha256") for event in matched]),
        "gameHexSha256": compact_hashes([str(event.get("gameHexSha256", "")) for event in matched]),
        "rawBodySha256": compact_hashes([str(event.get("rawBodySha256", "")) for event in matched]),
    }


def brush_yellow_wrapper_details(events: list[dict[str, Any]]) -> dict[str, Any]:
    prepare_marker = "brush_yellow_prepare_1520030"
    dispatch_marker = "brush_yellow_dispatch_1522030"
    prepare = marker_detail(events, prepare_marker)
    dispatch = marker_detail(events, dispatch_marker)
    return {
        "prepare1520030": prepare,
        "dispatch1522030": dispatch,
        "requiredMarkers": [prepare_marker, dispatch_marker],
        "complete": prepare["count"] > 0 and dispatch["count"] > 0,
        "splitProvenForBothStages": prepare["splitProven"] and dispatch["splitProven"],
    }


def remaining_action_wrapper_details(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize non-刷黄 action wrapper evidence for later action expansion.

    These are advisory/dry-run fields only. They help validate占矿/资源点送将和撤防
    captures without changing the hard brush-yellow gate or enabling sends.
    """
    resource_prepare_marker = "resource_point_prepare_1520010"
    resource_dispatch_marker = "resource_point_dispatch_1522010"
    withdraw_marker = "withdraw_defense_0a15260101"
    resource_prepare = marker_detail(events, resource_prepare_marker)
    resource_dispatch = marker_detail(events, resource_dispatch_marker)
    withdraw = marker_detail(events, withdraw_marker)
    return {
        "resourcePoint": {
            "prepare1520010": resource_prepare,
            "dispatch1522010": resource_dispatch,
            "requiredMarkers": [resource_prepare_marker, resource_dispatch_marker],
            "complete": resource_prepare["count"] > 0 and resource_dispatch["count"] > 0,
            "splitProvenForBothStages": resource_prepare["splitProven"] and resource_dispatch["splitProven"],
        },
        "withdrawDefense": {
            "withdraw0a15260101": withdraw,
            "requiredMarkers": [withdraw_marker],
            "complete": withdraw["count"] > 0,
            "splitProven": withdraw["splitProven"],
        },
        "networkSendAllowed": False,
    }


def to_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    extra = report.get("channelExtraCandidate", {})
    captures = report.get("captures", [])
    lines = [
        "# Native Wrapper 校准报告",
        "",
        "## Summary",
        "",
        f"- captureCount: {summary['captureCount']}",
        f"- uniqueGameHexCount: {summary['uniqueGameHexCount']}",
        f"- nativeWrapperFieldAuditReady: {str(summary.get('nativeWrapperFieldAudit', {}).get('readyForDryRunWrapperPlan', False)).lower()}",
        f"- brushYellowWrapperCoverage: prepare1520030={summary['brushYellowWrapperCoverage']['prepare1520030']} dispatch1522030={summary['brushYellowWrapperCoverage']['dispatch1522030']} complete={str(summary['brushYellowWrapperCoverage']['complete']).lower()}",
        f"- brushYellowWrapperSplitProvenForBothStages: {str(summary['brushYellowWrapperDetails']['splitProvenForBothStages']).lower()}",
        f"- resourcePointWrapperCoverageComplete: {str(summary['remainingActionWrapperDetails']['resourcePoint']['complete']).lower()}",
        f"- withdrawDefenseWrapperCoverageComplete: {str(summary['remainingActionWrapperDetails']['withdrawDefense']['complete']).lower()}",
        f"- networkSendAllowed: {str(summary['networkSendAllowed']).lower()}",
        f"- actionSendReady: {str(summary['actionSendReady']).lower()}",
        f"- readinessLevel: {summary['readinessLevel']}",
        f"- splitStatuses: {', '.join(summary['splitStatuses']) if summary['splitStatuses'] else '(none)'}",
        f"- blocker: {summary['blocker']}",
        "",
        "## Readiness reasons",
        "",
    ]
    lines.extend(f"- {reason}" for reason in summary.get("readinessReasons", []))
    lines += [
        "",
        "## Stability",
        "",
        f"- prefixLength: stable={summary['prefixLength']['stable']} unique={summary['prefixLength']['uniqueCount']} values={summary['prefixLength']['values']}",
        f"- suffixLength: stable={summary['suffixLength']['stable']} unique={summary['suffixLength']['uniqueCount']} values={summary['suffixLength']['values']}",
        f"- prefixHash: stable={summary['prefixHash']['stable']} unique={summary['prefixHash']['uniqueCount']}",
        f"- suffixHash: stable={summary['suffixHash']['stable']} unique={summary['suffixHash']['uniqueCount']}",
        "",
        "## Native Wrapper Field Audit",
        "",
        "```json",
        json.dumps(summary.get("nativeWrapperFieldAudit", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Brush Yellow Wrapper Details",
        "",
        "```json",
        json.dumps(summary["brushYellowWrapperDetails"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Remaining Action Wrapper Details",
        "",
        "```json",
        json.dumps(summary["remainingActionWrapperDetails"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## ChannelExtra Candidate",
        "",
        "```json",
        json.dumps(extra, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Captures",
        "",
    ]
    for index, capture in enumerate(captures, start=1):
        lines += [
            f"### Capture {index}",
            "",
            f"- source: {capture.get('source', '')}",
            f"- threadId: {capture.get('threadId', '')}",
            f"- rawBodyLength: {capture.get('rawBodyLength')}",
            f"- prefixLength: {capture.get('prefixLength')}",
            f"- suffixLength: {capture.get('suffixLength')}",
            f"- splitStatus: {', '.join(capture.get('splitStatus', []))}",
            f"- opcodeMarkers: {', '.join(capture.get('opcodeMarkers', []))}",
            f"- gameHexSha256: `{capture.get('gameHexSha256')}`",
            f"- rawBodySha256: `{capture.get('rawBodySha256')}`",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="Frida native/session trace log")
    ap.add_argument("--out", help="Output calibration JSON; defaults to stdout")
    ap.add_argument("--markdown-out", help="Optional Markdown report path")
    ap.add_argument("--include-values", action="store_true", help="Include raw body/prefix/suffix values; default stores hashes/lengths only")
    ns = ap.parse_args()
    text = Path(ns.input).read_text(encoding="utf-8", errors="replace")
    report = calibrate(text, include_values=ns.include_values)
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
