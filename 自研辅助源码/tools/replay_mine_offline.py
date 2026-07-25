#!/usr/bin/env python3
"""Offline replay of recovered 041542 mine/resource-point search and optional actions.

This verifier consumes channelExtra/base JSON, parses mine targets, applies local mine
filters, picks a mine, and optionally matches occupy/withdraw response metadata. It does
not contact devices or servers and does not enable real action sends.
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


def load_tool(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOL_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


verify_replay_contract = load_tool("verify_replay_contract")
readonly = load_tool("calibrate_readonly_responses")
replay_shuahuang_offline = load_tool("replay_shuahuang_offline")

MINE_KIND_ALIASES = {
    "GOLD": {"GOLD", "金", "金矿", "金礦", "01"},
    "SILVER": {"SILVER", "银", "銀", "银矿", "銀礦", "02"},
    "BING_YU": {"BING_YU", "冰玉", "冰玉矿", "03"},
    "XIAN_ZHI": {"XIAN_ZHI", "仙芝", "04"},
    "YU_LU": {"YU_LU", "玉露", "05"},
    "XUAN_TIE": {"XUAN_TIE", "玄铁", "玄鐵", "玄铁矿", "06"},
    "CRYSTAL": {"CRYSTAL", "水晶", "水晶矿", "07"},
    "LING_CAO": {"LING_CAO", "灵草", "靈草", "08"},
    "PASTURE_LV1": {"PASTURE_LV1", "牧场", "牧場", "09"},
    "BIN_TIE": {"BIN_TIE", "镔铁", "鑌鐵", "镔铁矿", "0A"},
    "JIANG_GUO": {"JIANG_GUO", "浆果", "漿果", "0B"},
}


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


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().strip('"\'')
    if not text:
        return None
    try:
        return int(text, 16) if re.fullmatch(r"[0-9a-fA-F]{8,}", text) else int(text, 10)
    except Exception:
        return None


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def normalize_mine_type(raw: Any, kind_code: Any = None) -> str:
    text = str(raw or "").strip()
    code = str(kind_code or "").strip().upper()
    candidates = {text, text.upper(), code}
    for name, aliases in MINE_KIND_ALIASES.items():
        if candidates & aliases or any(alias and alias in text for alias in aliases if not re.fullmatch(r"[0-9A-F]{2}", alias)):
            return name
    return text.upper() if text else "UNKNOWN"


def parse_mines(extra: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    value = parse_json(extra.get("mineTargetsJson", ""))
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            mine_id = parse_int(item.get("id") or item.get("mineId") or item.get("resourceId"))
            if mine_id is None:
                continue
            kind = normalize_mine_type(item.get("mineType") or item.get("type") or item.get("kind"), item.get("kindCode"))
            out.append({
                "id": mine_id,
                "mineType": kind,
                "kind": str(item.get("kind") or item.get("mineType") or kind),
                "kindCode": str(item.get("kindCode") or ""),
                "level": parse_int(item.get("level") or item.get("rank")) or 0,
                "x": parse_int(item.get("x") or item.get("kx") or item.get("kv")) or 0,
                "y": parse_int(item.get("y") or item.get("ky") or item.get("kw")) or 0,
                "isEmpty": parse_bool(item.get("isEmpty") if "isEmpty" in item else item.get("empty"), default=True),
                "defenseCount": parse_int(item.get("defenseCount") or item.get("defenders") or item.get("guardCount")),
                "raw": {str(k): stringify(v) for k, v in item.items()},
            })
    if out:
        return out
    for key in ("mineTargetsHex", "resourcePointSearchResponseHex", "resourcePointSearchResponse"):
        raw = extra.get(key, "").strip()
        if not raw:
            continue
        for item in readonly.parse_mines(raw):
            out.append({
                "id": int(item["id"]),
                "mineType": normalize_mine_type(item.get("kind"), item.get("kindCode")),
                "kind": str(item.get("kind") or ""),
                "kindCode": str(item.get("kindCode") or ""),
                "level": int(item.get("rank") or 0),
                "x": int(item.get("x") or 0),
                "y": int(item.get("y") or 0),
                "isEmpty": bool(item.get("isEmpty")),
                "defenseCount": parse_int(item.get("defenseCount")),
                "raw": {str(k): stringify(v) for k, v in item.items()},
            })
        if out:
            return out
    return out


def selected_types(extra: dict[str, str]) -> set[str]:
    raw = extra.get("selectedMineTypes") or extra.get("mineSelectedTypes") or extra.get("mineTypes") or ""
    if not raw.strip():
        return set()
    value = parse_json(raw)
    parts = value if isinstance(value, list) else re.split(r"[,;|\s]+", raw)
    return {normalize_mine_type(part) for part in parts if str(part).strip()}


def selected_formations(extra: dict[str, str]) -> list[int]:
    raw = extra.get("mineSelectedFormationIds") or extra.get("selectedFormationIds") or ""
    return [x for x in (parse_int(part) for part in re.split(r"[,;|\s]+", raw) if part.strip()) if x is not None]


def fixed_width_hex(value: int | None, width: int = 16) -> str:
    if value is None:
        return ""
    return f"{int(value):0{width}x}"


def explicit_general_ids(extra: dict[str, str]) -> list[int]:
    raw = (
        extra.get("mineGeneralIds")
        or extra.get("mineSelectedGeneralIds")
        or extra.get("selectedGeneralIds")
        or ""
    ).strip()
    if not raw:
        return []
    value = parse_json(raw)
    parts = value if isinstance(value, list) else re.split(r"[,;|\s]+", raw)
    return [x for x in (parse_int(part) for part in parts if str(part).strip()) if x is not None]


def general_ids_for_formation(extra: dict[str, str], formation_id: int | None) -> list[int]:
    explicit = explicit_general_ids(extra)
    if explicit:
        return explicit
    try:
        generals = replay_shuahuang_offline.parse_generals(extra)
        formations = replay_shuahuang_offline.parse_formations(extra, generals)
    except Exception:
        return []
    if formation_id is not None:
        for formation in formations:
            if parse_int(formation.get("id")) == formation_id:
                return [gid for gid in (parse_int(x) for x in (formation.get("generalIds") or [])) if gid is not None]
    if formations:
        return [gid for gid in (parse_int(x) for x in (formations[0].get("generalIds") or [])) if gid is not None]
    return []


def encode_xy(x: int, y: int) -> str:
    return f"{int(x):04x}{int(y):04x}"


def mine_filter_config(extra: dict[str, str]) -> dict[str, Any]:
    return {
        "selectedMineTypes": sorted(selected_types(extra)),
        "onlyEmptyMine": parse_bool(extra.get("onlyEmptyMine"), default=False),
        "onlyDefendedMine": parse_bool(extra.get("onlyDefendedMine"), default=False),
        "hitEmptyMine": parse_bool(extra.get("hitEmptyMine"), default=True),
    }


def filter_mines(extra: dict[str, str], mines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    config = mine_filter_config(extra)
    types = set(config["selectedMineTypes"])
    only_empty = bool(config["onlyEmptyMine"])
    only_defended = bool(config["onlyDefendedMine"])
    hit_empty = bool(config["hitEmptyMine"])
    out = []
    for mine in mines:
        if types and mine["mineType"] not in types:
            continue
        if only_empty and not mine.get("isEmpty"):
            continue
        if only_defended and mine.get("isEmpty") and not (mine.get("defenseCount") or 0) > 0:
            continue
        if not hit_empty and mine.get("isEmpty"):
            continue
        out.append(mine)
    return out


def choose_mine(mines: list[dict[str, Any]], start_x: int, start_y: int) -> dict[str, Any] | None:
    if not mines:
        return None
    return sorted(mines, key=lambda m: ((int(m.get("x") or 0) - start_x) ** 2 + (int(m.get("y") or 0) - start_y) ** 2, int(m.get("level") or 9999), int(m.get("id") or 0)))[0]


def mine_selection_evidence(
    mines: list[dict[str, Any]],
    filtered: list[dict[str, Any]],
    selected: dict[str, Any] | None,
    config: dict[str, Any],
    start_x: int,
    start_y: int,
    require_occupy: bool,
    require_withdraw: bool,
) -> dict[str, Any]:
    selected_type_match = False
    selected_empty_match = False
    if selected is not None:
        types = set(config.get("selectedMineTypes") or [])
        selected_type_match = (not types) or selected.get("mineType") in types
        selected_empty_match = (
            (not config.get("onlyEmptyMine") or bool(selected.get("isEmpty")))
            and (bool(config.get("hitEmptyMine", True)) or not bool(selected.get("isEmpty")))
        )
    search_payload = "000000000000000000041542" + encode_xy(start_x, start_y)
    read_only = not require_occupy and not require_withdraw
    return {
        "mineReadOnlyEvidenceReady": bool(read_only and selected is not None and len(mines) > 0 and len(filtered) > 0),
        "mineSelectionEvidenceReady": bool(selected is not None and selected_type_match and selected_empty_match and len(filtered) > 0),
        "searchOpcode": "041542",
        "searchPayload": search_payload,
        "startX": start_x,
        "startY": start_y,
        "inputMineCount": len(mines),
        "filterMatchedCount": len(filtered),
        "selectedMineId": selected.get("id") if selected else None,
        "selectedMineType": selected.get("mineType") if selected else None,
        "selectedMineIsEmpty": selected.get("isEmpty") if selected else None,
        "selectedTypeMatchesConfig": selected_type_match,
        "selectedEmptyMatchesConfig": selected_empty_match,
        "filterConfig": config,
        "occupyRequired": require_occupy,
        "withdrawRequired": require_withdraw,
        "realActionNetworkAllowed": False,
    }


def match_action(raw_json: str, mine_id: int, formation_id: int | None = None) -> dict[str, Any] | None:
    value = parse_json(raw_json)
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, dict):
            continue
        candidate_mine = parse_int(item.get("mineId") or item.get("resourceId") or item.get("id"))
        if candidate_mine != mine_id:
            continue
        if formation_id is not None:
            candidate_formation = parse_int(item.get("formationId") or item.get("bianduihao"))
            if candidate_formation != formation_id:
                continue
        return item
    return None


def action_success(item: dict[str, Any] | None) -> bool | None:
    if item is None:
        return None
    if "success" in item:
        return parse_bool(item.get("success"), default=False)
    text = str(item.get("message") or item.get("msg") or item.get("responseText") or "")
    if "失败" in text or "error" in text.lower() or "fail" in text.lower():
        return False
    if "成功" in text or "完成" in text:
        return True
    return None


def resource_point_action_payload_evidence(
    extra: dict[str, str],
    selected: dict[str, Any] | None,
    formation_id: int | None,
    required: bool,
) -> dict[str, Any]:
    general_ids = general_ids_for_formation(extra, formation_id) if selected is not None else []
    general_chunks = [fixed_width_hex(gid) for gid in general_ids if fixed_width_hex(gid)]
    resource_point_id = parse_int(selected.get("id")) if selected else None
    resource_point_hex = fixed_width_hex(resource_point_id)
    prepare_payload = ""
    dispatch_payload = ""
    prepare_length_hex = ""
    dispatch_length_hex = ""
    ready = bool(required and general_chunks and resource_point_hex)
    if general_chunks and resource_point_hex:
        count = str(len(general_chunks))
        ids_blob = "".join(general_chunks)
        prepare_length_hex = f"{len(general_chunks) * 8 + 0x0a:x}"
        dispatch_length_hex = f"{len(general_chunks) * 8 + 0x15:x}"
        # Resource-point send-general is the recovered mode=1 pair: unlike brush-yellow
        # it does not insert the 0000 trailer before the resource point id.
        prepare_payload = "000000000000000000" + prepare_length_hex + "1520010" + count + ids_blob + resource_point_hex
        dispatch_payload = "000000000000000000" + dispatch_length_hex + "1522010" + count + ids_blob + resource_point_hex + "ffffffffffffffff000000"
    return {
        "resourcePointActionPayloadEvidenceReady": ready,
        "required": required,
        "formula": "p2=0 resource-point: prefix + len(ids*8+const) + opcode + count + concat(generalIds16) + resourcePointId16 (+ expedition tail)",
        "prepareOpcode": "1520010",
        "dispatchOpcode": "1522010",
        "formationId": formation_id,
        "generalIdHexChunks": general_chunks,
        "generalCount": len(general_chunks),
        "resourcePointIdHex": resource_point_hex,
        "prepareLengthHex": prepare_length_hex,
        "dispatchLengthHex": dispatch_length_hex,
        "preparePayload": prepare_payload,
        "dispatchPayload": dispatch_payload,
        "prepareContainsResourcePoint": bool(prepare_payload and resource_point_hex in prepare_payload),
        "dispatchContainsResourcePoint": bool(dispatch_payload and resource_point_hex in dispatch_payload),
        "prepareContainsAllGenerals": bool(prepare_payload and all(chunk in prepare_payload for chunk in general_chunks)),
        "dispatchContainsAllGenerals": bool(dispatch_payload and all(chunk in dispatch_payload for chunk in general_chunks)),
        "networkSendAllowed": False,
        "realActionNetworkAllowed": False,
    }


def withdraw_record_id(extra: dict[str, str], selected: dict[str, Any] | None, withdraw: dict[str, Any] | None) -> tuple[int | None, str]:
    for source, value in [
        ("channelExtra.withdrawDefenseRecordId", extra.get("withdrawDefenseRecordId")),
        ("channelExtra.defenseRecordId", extra.get("defenseRecordId")),
        ("matchedAction.defenseRecordId", withdraw.get("defenseRecordId") if withdraw else None),
        ("matchedAction.guardRecordId", withdraw.get("guardRecordId") if withdraw else None),
        ("matchedAction.resourceId", withdraw.get("resourceId") if withdraw else None),
        ("matchedAction.mineId", withdraw.get("mineId") if withdraw else None),
        ("selectedMineIdFallback", selected.get("id") if selected else None),
    ]:
        parsed = parse_int(value)
        if parsed is not None:
            return parsed, source
    return None, "missing"


def withdraw_payload_evidence(
    extra: dict[str, str],
    selected: dict[str, Any] | None,
    withdraw: dict[str, Any] | None,
    required: bool,
) -> dict[str, Any]:
    record_id, source = withdraw_record_id(extra, selected, withdraw)
    record_hex = fixed_width_hex(record_id)
    payload = "0000000000000000000a15260101" + record_hex if record_hex else ""
    ready = bool(required and payload)
    return {
        "withdrawPayloadEvidenceReady": ready,
        "required": required,
        "formula": "withdraw-defense: prefix + 0a15260101 + defenseRecordId16",
        "withdrawOpcode": "0a15260101",
        "defenseRecordIdHex": record_hex,
        "defenseRecordIdSource": source,
        "withdrawPayload": payload,
        "payloadContainsRecordId": bool(payload and record_hex in payload),
        "networkSendAllowed": False,
        "realActionNetworkAllowed": False,
    }


def replay(extra: dict[str, str], start_x: int = 0, start_y: int = 0, require_occupy: bool | None = None, require_withdraw: bool | None = None) -> dict[str, Any]:
    contract = verify_replay_contract.verify(extra)
    mines = parse_mines(extra)
    filtered = filter_mines(extra, mines)
    selected = choose_mine(filtered, start_x, start_y)
    formation_ids = selected_formations(extra)
    formation_id = formation_ids[0] if formation_ids else parse_int(extra.get("mineFormationId"))
    if require_occupy is None:
        require_occupy = parse_bool(extra.get("mineRequireOccupyResult"), default=False) or bool(extra.get("occupyMineResultsJson"))
    if require_withdraw is None:
        require_withdraw = parse_bool(extra.get("withdrawDefense"), default=False) or parse_bool(extra.get("mineRequireWithdrawResult"), default=False) or bool(extra.get("withdrawMineResultsJson"))
    filter_config = mine_filter_config(extra)
    selection_evidence = mine_selection_evidence(mines, filtered, selected, filter_config, start_x, start_y, require_occupy, require_withdraw)
    occupy = match_action(extra.get("occupyMineResultsJson", ""), selected["id"], formation_id) if selected and require_occupy else None
    withdraw = match_action(extra.get("withdrawMineResultsJson", ""), selected["id"], None) if selected and require_withdraw else None
    occupy_ok = action_success(occupy)
    withdraw_ok = action_success(withdraw)
    resource_payload_evidence = resource_point_action_payload_evidence(extra, selected, formation_id, bool(require_occupy))
    withdraw_payload = withdraw_payload_evidence(extra, selected, withdraw, bool(require_withdraw))
    remaining_action_ready = bool(
        (not require_occupy or resource_payload_evidence["resourcePointActionPayloadEvidenceReady"])
        and (not require_withdraw or withdraw_payload["withdrawPayloadEvidenceReady"])
        and (require_occupy or require_withdraw)
    )
    steps = [
        {"step": "identity", "ok": bool(extra.get("userId") and extra.get("serverUrl")), "evidence": "userId/serverUrl"},
        {"step": "mineSearch/041542", "ok": len(mines) > 0, "count": len(mines), "searchPayload": selection_evidence["searchPayload"]},
        {"step": "filterMines", "ok": len(filtered) > 0, "count": len(filtered), "filterConfig": filter_config},
        {"step": "chooseMine", "ok": selected is not None, "mineId": selected.get("id") if selected else None, "mineType": selected.get("mineType") if selected else None},
    ]
    if require_occupy:
        steps.append({
            "step": "buildResourcePointPayloads/1520010+1522010",
            "ok": resource_payload_evidence["resourcePointActionPayloadEvidenceReady"],
            "prepareOpcode": resource_payload_evidence["prepareOpcode"],
            "dispatchOpcode": resource_payload_evidence["dispatchOpcode"],
            "generalCount": resource_payload_evidence["generalCount"],
            "resourcePointIdHex": resource_payload_evidence["resourcePointIdHex"],
        })
        steps.append({"step": "occupyMineResult", "ok": occupy is not None and occupy_ok is True, "matched": occupy is not None, "success": occupy_ok, "formationId": formation_id})
    if require_withdraw:
        steps.append({
            "step": "buildWithdrawPayload/0a15260101",
            "ok": withdraw_payload["withdrawPayloadEvidenceReady"],
            "withdrawOpcode": withdraw_payload["withdrawOpcode"],
            "defenseRecordIdHex": withdraw_payload["defenseRecordIdHex"],
            "defenseRecordIdSource": withdraw_payload["defenseRecordIdSource"],
        })
        steps.append({"step": "withdrawMineResult", "ok": withdraw is not None and withdraw_ok is True, "matched": withdraw is not None, "success": withdraw_ok})
    missing = [s["step"] for s in steps if not s.get("ok")]
    if not contract["summary"]["mineOfflineReplayReady"]:
        missing.append("mineReplayContract")
    ready = not missing
    return {
        "summary": {
            "mineOfflineClosedLoopReplayReady": ready,
            "contractReady": contract["summary"]["mineOfflineReplayReady"],
            "mineReadOnlyEvidenceReady": selection_evidence["mineReadOnlyEvidenceReady"],
            "mineSelectionEvidenceReady": selection_evidence["mineSelectionEvidenceReady"],
            "mineCount": len(mines),
            "filteredMineCount": len(filtered),
            "selectedMineId": selected.get("id") if selected else None,
            "selectedMineType": selected.get("mineType") if selected else None,
            "selectedFormationId": formation_id,
            "occupyRequired": require_occupy,
            "occupyMatched": occupy is not None,
            "occupySuccess": occupy_ok,
            "withdrawRequired": require_withdraw,
            "withdrawMatched": withdraw is not None,
            "withdrawSuccess": withdraw_ok,
            "mineSelectionEvidence": selection_evidence,
            "resourcePointActionPayloadEvidenceReady": resource_payload_evidence["resourcePointActionPayloadEvidenceReady"],
            "withdrawPayloadEvidenceReady": withdraw_payload["withdrawPayloadEvidenceReady"],
            "remainingActionDryRunEvidenceReady": remaining_action_ready,
            "realActionNetworkAllowed": False,
            "blocker": "offline mine replay only; true occupy/withdraw sends remain disabled",
        },
        "missingSteps": missing,
        "steps": steps,
        "selected": {"mine": selected, "occupy": occupy, "withdraw": withdraw},
        "resourcePointActionPayloadEvidence": resource_payload_evidence,
        "withdrawPayloadEvidence": withdraw_payload,
        "parsed": {"mines": mines, "filteredMines": filtered},
        "replayContract": contract,
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 找矿离线回放报告",
        "",
        "## Summary",
        "",
        f"- mineOfflineClosedLoopReplayReady: {str(s['mineOfflineClosedLoopReplayReady']).lower()}",
        f"- contractReady: {str(s['contractReady']).lower()}",
        f"- mineReadOnlyEvidenceReady: {str(s['mineReadOnlyEvidenceReady']).lower()}",
        f"- mineSelectionEvidenceReady: {str(s['mineSelectionEvidenceReady']).lower()}",
        f"- mineCount: {s['mineCount']}",
        f"- filteredMineCount: {s['filteredMineCount']}",
        f"- selectedMineId: {s['selectedMineId']}",
        f"- selectedMineType: {s['selectedMineType']}",
        f"- selectedFormationId: {s['selectedFormationId']}",
        f"- occupyRequired: {str(s['occupyRequired']).lower()}",
        f"- occupyMatched: {str(s['occupyMatched']).lower()}",
        f"- occupySuccess: {str(s['occupySuccess']).lower() if s['occupySuccess'] is not None else 'null'}",
        f"- withdrawRequired: {str(s['withdrawRequired']).lower()}",
        f"- withdrawMatched: {str(s['withdrawMatched']).lower()}",
        f"- withdrawSuccess: {str(s['withdrawSuccess']).lower() if s['withdrawSuccess'] is not None else 'null'}",
        f"- resourcePointActionPayloadEvidenceReady: {str(s['resourcePointActionPayloadEvidenceReady']).lower()}",
        f"- withdrawPayloadEvidenceReady: {str(s['withdrawPayloadEvidenceReady']).lower()}",
        f"- remainingActionDryRunEvidenceReady: {str(s['remainingActionDryRunEvidenceReady']).lower()}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## Missing steps",
        "",
        "```json",
        json.dumps(report["missingSteps"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Steps",
        "",
        "```json",
        json.dumps(report["steps"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Selected",
        "",
        "```json",
        json.dumps(report["selected"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Mine selection evidence",
        "",
        "```json",
        json.dumps(s.get("mineSelectionEvidence", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Resource-point action payload evidence",
        "",
        "```json",
        json.dumps(report.get("resourcePointActionPayloadEvidence", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Withdraw payload evidence",
        "",
        "```json",
        json.dumps(report.get("withdrawPayloadEvidence", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="channelExtra JSON containing mineTargetsJson/mineTargetsHex")
    ap.add_argument("--base", help="Optional base channelExtra JSON merged before input")
    ap.add_argument("--merge-extra", action="append", default=[], help="Additional channelExtra JSON merged after input; can repeat")
    ap.add_argument("--start-x", type=int, default=0)
    ap.add_argument("--start-y", type=int, default=0)
    ap.add_argument("--require-occupy", action="store_true")
    ap.add_argument("--require-withdraw", action="store_true")
    ap.add_argument("--out", help="Write JSON report; defaults to stdout")
    ap.add_argument("--markdown-out", help="Write Markdown report")
    ns = ap.parse_args()
    extra = merge_inputs(Path(ns.input), base=ns.base, merges=ns.merge_extra)
    report = replay(extra, start_x=ns.start_x, start_y=ns.start_y, require_occupy=ns.require_occupy or None, require_withdraw=ns.require_withdraw or None)
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
