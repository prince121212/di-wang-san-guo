#!/usr/bin/env python3
"""Offline replay of the recovered brush-yellow minimum closed loop.

This verifier does not contact devices or servers. It consumes channelExtra/base JSON and
tries to execute the same high-level sequence as ShuaHuangTask:
validate session -> role/resource -> generals/formations -> 041540 target selection ->
dispatch result match -> stop/logout marker.
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

GENERAL_KEYS = verify_replay_contract.GENERAL_KEYS
FORMATION_KEYS = verify_replay_contract.FORMATION_KEYS
MAP_KEYS = verify_replay_contract.MAP_KEYS

JIANG_LING_BLOCK = re.compile(r"JiangLing\s*\{([^}]*)\}", re.I)
KV = re.compile(r"([A-Za-z0-9_]+)\s*=\s*([^,}\s]+)")


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


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def json_value(raw: str) -> Any | None:
    try:
        return json.loads(raw)
    except Exception:
        return None


def parse_generals(extra: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for key in GENERAL_KEYS:
        raw = extra.get(key, "").strip()
        if not raw:
            continue
        value = json_value(raw)
        if isinstance(value, list):
            for item in value:
                add_general(out, seen, item if isinstance(item, dict) else {"id": item})
        elif isinstance(value, dict):
            arrays = [v for v in value.values() if isinstance(v, list)]
            if arrays:
                for arr in arrays:
                    for item in arr:
                        add_general(out, seen, item if isinstance(item, dict) else {"id": item})
            else:
                add_general(out, seen, value)
        for block in JIANG_LING_BLOCK.findall(raw):
            fields = {m.group(1): m.group(2) for m in KV.finditer(block)}
            add_general(out, seen, fields)
        if key.lower().endswith("hex"):
            try:
                decoded = bytes.fromhex("".join(ch for ch in raw if ch in "0123456789abcdefABCDEF")).decode("utf-8", errors="ignore")
            except Exception:
                decoded = ""
            for block in JIANG_LING_BLOCK.findall(decoded):
                fields = {m.group(1): m.group(2) for m in KV.finditer(block)}
                add_general(out, seen, fields)
    return out


def add_general(out: list[dict[str, Any]], seen: set[int], item: dict[str, Any]) -> None:
    gid = parse_int(item.get("id") or item.get("generalId") or item.get("jiangLingId"))
    if gid is None or gid in seen:
        return
    seen.add(gid)
    out.append({
        "id": gid,
        "name": str(item.get("name") or item.get("mingzi") or item.get("generalName") or ""),
        "status": parse_int(item.get("status")),
        "energy": parse_int(item.get("tili") or item.get("energy")),
        "raw": {str(k): stringify(v) for k, v in item.items()},
    })


def recovered_pref_map(extra: dict[str, str]) -> dict[str, str]:
    prefs = dict(extra)
    for key in FORMATION_KEYS:
        raw = extra.get(key, "").strip()
        value = json_value(raw)
        if isinstance(value, dict):
            prefs.update({str(k): stringify(v) for k, v in value.items()})
    return prefs


def parse_formations(extra: dict[str, str], generals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    raw = extra.get("formationsJson", "").strip()
    value = json_value(raw)
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                fid = parse_int(item.get("id") or item.get("formationId"))
                if fid is None:
                    continue
                gids = item.get("generalIds") or item.get("generals") or []
                if not isinstance(gids, list):
                    gids = [gids]
                add_formation(out, seen, fid, [g for g in (parse_int(x) for x in gids) if g is not None], parse_bool(item.get("canDispatch", True)), item)
    prefs = recovered_pref_map(extra)
    general_by_id = {g["id"]: g for g in generals}
    for idx in range(0, 50):
        enabled = prefs.get(f"shuahuangChuzhengBiandui{idx}")
        fid = parse_int(prefs.get(f"bianduihao{idx}"))
        gid = parse_int(prefs.get(f"bianduiDejiangling{idx}"))
        if fid is None and gid is None:
            continue
        if enabled is not None and not parse_bool(enabled):
            continue
        gids = [gid] if gid is not None else []
        can = True
        if gid in general_by_id:
            g = general_by_id[gid]
            can = (g.get("status") in (None, 0)) and (g.get("energy") is None or g.get("energy") > 0)
        add_formation(out, seen, fid if fid is not None else idx, gids, can, {"sourceIndex": idx})
    return out


def add_formation(out: list[dict[str, Any]], seen: set[int], fid: int, gids: list[int], can: bool, raw: dict[str, Any]) -> None:
    if fid in seen:
        return
    seen.add(fid)
    out.append({"id": fid, "generalIds": gids, "canDispatch": can, "raw": {str(k): stringify(v) for k, v in raw.items()}})


def parse_targets(extra: dict[str, str]) -> list[dict[str, Any]]:
    raw_json = extra.get("mapTargetsJson", "").strip()
    value = json_value(raw_json)
    out: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            tid = parse_int(
                item.get("id")
                or item.get("targetId")
                or item.get("targetID")
                or item.get("idHex")
                or item.get("targetIdHex")
            )
            if tid is None:
                continue
            out.append({
                "id": tid,
                "type": str(item.get("type") or item.get("kind") or item.get("targetType") or item.get("targetKind") or item.get("name") or ""),
                "rank": parse_int(item.get("rank") or item.get("level") or item.get("targetLevel")) or 0,
                "x": parse_int(item.get("x") or item.get("kv") or item.get("coordX") or item.get("coordinateX") or item.get("kA")) or 0,
                "y": parse_int(item.get("y") or item.get("kw") or item.get("coordY") or item.get("coordinateY") or item.get("kB")) or 0,
                "raw": {str(k): stringify(v) for k, v in item.items()},
            })
    if out:
        return out
    for key in ("mapTargetsHex", "targetSearchResponseHex", "targetSearchResponse"):
        raw = extra.get(key, "").strip()
        if not raw:
            continue
        for item in readonly.parse_targets(raw):
            out.append({
                "id": int(item["id"]),
                "type": str(item.get("type") or ""),
                "rank": int(item.get("rank") or 0),
                "x": int(item.get("x") or 0),
                "y": int(item.get("y") or 0),
                "raw": {str(k): stringify(v) for k, v in item.items()},
            })
        if out:
            return out
    return out


def selected_formation_ids(extra: dict[str, str], formations: list[dict[str, Any]]) -> list[int]:
    raw = extra.get("selectedFormationIds") or extra.get("shuaHuangSelectedFormationIds") or ""
    ids = [parse_int(part) for part in re.split(r"[,;|\s]+", raw) if part.strip()] if raw else []
    ids = [x for x in ids if x is not None]
    if ids:
        return ids
    return [f["id"] for f in formations]


def target_matches(target: dict[str, Any], expected: str) -> bool:
    text = " ".join([str(target.get("type") or ""), json.dumps(target.get("raw") or {}, ensure_ascii=False)]).lower()
    if expected == "HUANG_JIN":
        return any(t.lower() in text for t in ["黄巾", "黃巾", "渠帅", "渠帥", "主将", "主將", "主帅", "主帥", "huang_jin"])
    if expected == "SHAN_ZEI":
        return any(t.lower() in text for t in ["山贼", "山賊", "shan_zei"])
    return True


def candidate_formations(formations: list[dict[str, Any]], generals: list[dict[str, Any]], selected_ids: list[int]) -> list[dict[str, Any]]:
    general_by_id = {g["id"]: g for g in generals}
    order = {fid: idx for idx, fid in enumerate(selected_ids)}
    out: list[dict[str, Any]] = []
    for formation in sorted(formations, key=lambda f: order.get(f["id"], 10_000)):
        if selected_ids and formation["id"] not in selected_ids:
            continue
        if not formation.get("canDispatch", False):
            continue
        gids = formation.get("generalIds") or []
        if not gids or not any(gid in general_by_id for gid in gids):
            continue
        blocked = False
        for gid in gids:
            g = general_by_id.get(gid)
            if not g:
                continue
            if g.get("status") not in (None, 0) or (g.get("energy") is not None and g.get("energy") <= 0):
                blocked = True
        if not blocked:
            out.append(formation)
    return out


def split_keywords(value: str | None) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in re.split(r"[,，;；|\s]+", value) if x.strip()]


def filter_for(extra: dict[str, str], formation_id: int | None) -> dict[str, Any]:
    prefixes = []
    mode = (extra.get("formationFilterMode") or extra.get("shuaHuangFormationFilterMode") or "").upper()
    if formation_id is not None and mode in {"PER_FORMATION", "PER", "FENKAI"}:
        prefixes.extend([f"shuaHuangFormation{formation_id}", f"formation{formation_id}"])
    prefixes.extend(["shuaHuang", "target", ""])

    def first_int(*suffixes: str) -> int | None:
        for prefix in prefixes:
            for suffix in suffixes:
                key = f"{prefix}{suffix}" if prefix else suffix[:1].lower() + suffix[1:]
                value = parse_int(extra.get(key))
                if value is not None:
                    return value
        return None

    def first_keywords(*suffixes: str) -> list[str]:
        for prefix in prefixes:
            for suffix in suffixes:
                key = f"{prefix}{suffix}" if prefix else suffix[:1].lower() + suffix[1:]
                values = split_keywords(extra.get(key))
                if values:
                    return values
        return []

    return {
        "minLevel": first_int("MinTargetLevel", "TargetLevelMin"),
        "maxLevel": first_int("MaxTargetLevel", "TargetLevelMax"),
        "maxDistance": first_int("MaxDistance", "TargetMaxDistance"),
        "requiredKeywords": first_keywords("RequiredKeywords", "TargetRequiredKeywords"),
        "blockedKeywords": first_keywords("BlockedKeywords", "TargetBlockedKeywords"),
    }


def target_matches_filter(target: dict[str, Any], flt: dict[str, Any], start_x: int, start_y: int) -> bool:
    level = parse_int(target.get("rank") or (target.get("raw") or {}).get("level") or (target.get("raw") or {}).get("targetLevel"))
    if flt.get("minLevel") is not None and (level is None or level < flt["minLevel"]):
        return False
    if flt.get("maxLevel") is not None and (level is None or level > flt["maxLevel"]):
        return False
    if flt.get("maxDistance") is not None:
        dist2 = (int(target.get("x") or 0) - start_x) ** 2 + (int(target.get("y") or 0) - start_y) ** 2
        if dist2 > int(flt["maxDistance"]) ** 2:
            return False
    haystack = (str(target.get("type") or "") + " " + json.dumps(target.get("raw") or {}, ensure_ascii=False)).lower()
    if any(k.lower() not in haystack for k in flt.get("requiredKeywords") or []):
        return False
    if any(k.lower() in haystack for k in flt.get("blockedKeywords") or []):
        return False
    return True


def choose_target(targets: list[dict[str, Any]], target_type: str, start_x: int, start_y: int, flt: dict[str, Any]) -> dict[str, Any] | None:
    filtered = [t for t in targets if target_matches_filter(t, flt, start_x, start_y)]
    matching = [t for t in filtered if target_matches(t, target_type)]
    if not matching:
        return None
    return sorted(matching, key=lambda t: ((int(t.get("x") or 0) - start_x) ** 2 + (int(t.get("y") or 0) - start_y) ** 2, int(t.get("rank") or 9999), int(t.get("id") or 0)))[0]


def filter_is_active(flt: dict[str, Any]) -> bool:
    return any(
        flt.get(key) not in (None, [], "")
        for key in ("minLevel", "maxLevel", "maxDistance", "requiredKeywords", "blockedKeywords")
    )


def choose_target_with_evidence(
    targets: list[dict[str, Any]],
    target_type: str,
    start_x: int,
    start_y: int,
    flt: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    filtered = [t for t in targets if target_matches_filter(t, flt, start_x, start_y)]
    matching = [t for t in filtered if target_matches(t, target_type)]
    target = None
    if matching:
        target = sorted(
            matching,
            key=lambda t: (
                (int(t.get("x") or 0) - start_x) ** 2 + (int(t.get("y") or 0) - start_y) ** 2,
                int(t.get("rank") or 9999),
                int(t.get("id") or 0),
            ),
        )[0]
    strict_match = bool(target is not None and target_matches(target, target_type))
    evidence = {
        "targetSelectionEvidenceReady": bool(target is not None and strict_match and targets and filtered and matching),
        "targetTypeConfigured": target_type,
        "strictTargetTypeMatch": strict_match,
        "filterActive": filter_is_active(flt),
        "appliedTargetFilter": flt,
        "startX": start_x,
        "startY": start_y,
        "inputTargetCount": len(targets),
        "filterMatchedCount": len(filtered),
        "typeMatchedCount": len(matching),
        "selectedTargetId": target.get("id") if target else None,
        "selectedTargetType": target.get("type") if target else None,
    }
    return target, evidence


def choose_expedition(extra: dict[str, str], formations: list[dict[str, Any]], targets: list[dict[str, Any]], target_type: str, start_x: int, start_y: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for formation in formations:
        flt = filter_for(extra, int(formation["id"]))
        target, evidence = choose_target_with_evidence(targets, target_type, start_x, start_y, flt)
        evidence["formationId"] = int(formation["id"])
        attempts.append(dict(evidence))
        if target is not None:
            evidence["attempts"] = attempts
            return formation, target, flt, evidence
    flt = filter_for(extra, None)
    target, evidence = choose_target_with_evidence(targets, target_type, start_x, start_y, flt)
    evidence["formationId"] = None
    evidence["attempts"] = attempts
    return None, None, flt, evidence


def dispatch_match(extra: dict[str, str], formation: dict[str, Any] | None, target: dict[str, Any] | None) -> dict[str, Any] | None:
    if not formation or not target:
        return None
    value = json_value(extra.get("dispatchResultsJson", ""))
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, dict):
            continue
        nested = item.get("raw") if isinstance(item.get("raw"), dict) else {}
        fid = parse_int(
            item.get("formationId")
            or item.get("formationID")
            or item.get("formation")
            or item.get("formationNo")
            or item.get("formationIdHex")
            or item.get("bianduihao")
            or item.get("biandui")
            or nested.get("formationId")
            or nested.get("bianduihao")
        )
        tid = parse_int(
            item.get("targetId")
            or item.get("targetID")
            or item.get("id")
            or item.get("target")
            or item.get("targetPointId")
            or item.get("enemyId")
            or item.get("targetIdHex")
            or item.get("idHex")
            or nested.get("targetId")
            or nested.get("targetIdHex")
            or nested.get("idHex")
        )
        if fid == formation["id"] and tid == target["id"]:
            return item
    return None


def fixed_width_hex(value: int | None, width: int = 16) -> str:
    if value is None:
        return ""
    return f"{int(value):0{width}x}"


def build_brush_yellow_payload_evidence(
    formation: dict[str, Any] | None,
    target: dict[str, Any] | None,
) -> dict[str, Any]:
    general_ids = []
    if formation:
        raw_ids = formation.get("generalIds") or []
        if isinstance(raw_ids, list):
            general_ids = [parsed for parsed in (parse_int(x) for x in raw_ids) if parsed is not None]
    target_id = parse_int(target.get("id")) if target else None
    general_chunks = [fixed_width_hex(gid) for gid in general_ids if fixed_width_hex(gid)]
    target_hex = fixed_width_hex(target_id)
    ready = bool(general_chunks and target_hex)
    prepare_payload = ""
    expedition_payload = ""
    prepare_length_hex = ""
    expedition_length_hex = ""
    if ready:
        count = str(len(general_chunks))
        ids_blob = "".join(general_chunks)
        prepare_length_hex = f"{len(general_chunks) * 8 + 0x0a:x}"
        expedition_length_hex = f"{len(general_chunks) * 8 + 0x15:x}"
        prepare_payload = "000000000000000000" + prepare_length_hex + "1520030" + count + ids_blob + "0000" + target_hex
        expedition_payload = "000000000000000000" + expedition_length_hex + "1522030" + count + ids_blob + "0000" + target_hex + "ffffffffffffffff000000"
    return {
        "dispatchPayloadEvidenceReady": ready,
        "formula": "p2=0 brush-yellow: prefix + len(ids*8+const) + opcode + count + concat(generalIds16) + 0000 + targetId16 (+ expedition tail)",
        "prepareOpcode": "1520030",
        "expeditionOpcode": "1522030",
        "generalIdHexChunks": general_chunks,
        "generalCount": len(general_chunks),
        "targetIdHex": target_hex,
        "prepareLengthHex": prepare_length_hex,
        "expeditionLengthHex": expedition_length_hex,
        "preparePayload": prepare_payload,
        "expeditionPayload": expedition_payload,
        "prepareContainsTarget": bool(prepare_payload and target_hex in prepare_payload),
        "expeditionContainsTarget": bool(expedition_payload and target_hex in expedition_payload),
        "prepareContainsAllGenerals": bool(prepare_payload and all(chunk in prepare_payload for chunk in general_chunks)),
        "expeditionContainsAllGenerals": bool(expedition_payload and all(chunk in expedition_payload for chunk in general_chunks)),
    }


def dispatch_response_text(dispatch: dict[str, Any]) -> str:
    nested = dispatch.get("raw") if isinstance(dispatch.get("raw"), dict) else {}
    for key in ("responseText", "response", "rawResponse", "bodyText", "body", "responseBody", "resultText", "rawText", "dispatchResponse"):
        value = dispatch.get(key)
        if value is None:
            value = nested.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def dispatch_success_value(dispatch: dict[str, Any]) -> bool:
    for key in ("success", "ok", "dispatchSuccess", "result", "status", "state"):
        if key not in dispatch:
            continue
        raw = dispatch.get(key)
        text = str(raw).strip().lower()
        if isinstance(raw, bool):
            return raw
        if text in {"true", "1", "yes", "y", "ok", "success", "succeeded", "done"}:
            return True
        if text in {"false", "0", "no", "n", "fail", "failed", "error"}:
            return False
        if "成功" in str(raw):
            return True
        if any(token in str(raw) for token in ("失败", "不可出征", "不能出征", "无法出征")):
            return False
    return False


def replay(extra: dict[str, str], target_type: str = "HUANG_JIN", start_x: int = 0, start_y: int = 0) -> dict[str, Any]:
    extra = verify_replay_contract.with_recovered_role_resource(extra)
    if target_type not in {"HUANG_JIN", "SHAN_ZEI"}:
        target_type = "SHAN_ZEI" if any(token in target_type for token in ("山", "賊", "贼")) else "HUANG_JIN"
    contract = verify_replay_contract.verify(extra)
    generals = parse_generals(extra)
    formations = parse_formations(extra, generals)
    targets = parse_targets(extra)
    selected_ids = selected_formation_ids(extra, formations)
    candidates = candidate_formations(formations, generals, selected_ids)
    formation, target, applied_filter, target_selection_evidence = choose_expedition(extra, candidates, targets, target_type, start_x, start_y)
    dispatch_payload_evidence = build_brush_yellow_payload_evidence(formation, target)
    dispatch = dispatch_match(extra, formation, target)
    dispatch_success = None if dispatch is None else dispatch_success_value(dispatch) or ("成功" in dispatch_response_text(dispatch))
    steps = [
        {"step": "login/session", "ok": bool(extra.get("userId") and extra.get("serverUrl")), "evidence": "userId/serverUrl"},
        {"step": "role/resource", "ok": bool(extra.get("roleName") and extra.get("level") and extra.get("copper") and extra.get("food")), "evidence": "roleName/level/copper/food"},
        {"step": "generals", "ok": len(generals) > 0, "count": len(generals)},
        {"step": "formations", "ok": len(formations) > 0, "count": len(formations)},
        {"step": "chooseFormation", "ok": formation is not None, "formationId": formation.get("id") if formation else None, "candidateCount": len(candidates)},
        {"step": "findYellow/041540", "ok": len(targets) > 0, "count": len(targets)},
        {
            "step": "chooseTarget",
            "ok": target is not None and bool(target_selection_evidence.get("targetSelectionEvidenceReady")),
            "targetId": target.get("id") if target else None,
            "targetType": target.get("type") if target else None,
            "targetTypeConfigured": target_selection_evidence.get("targetTypeConfigured"),
            "strictTargetTypeMatch": target_selection_evidence.get("strictTargetTypeMatch"),
            "filterMatchedCount": target_selection_evidence.get("filterMatchedCount"),
            "typeMatchedCount": target_selection_evidence.get("typeMatchedCount"),
        },
        {
            "step": "buildDispatchPayloads/1520030+1522030",
            "ok": bool(dispatch_payload_evidence.get("dispatchPayloadEvidenceReady")),
            "prepareOpcode": dispatch_payload_evidence.get("prepareOpcode"),
            "expeditionOpcode": dispatch_payload_evidence.get("expeditionOpcode"),
            "generalCount": dispatch_payload_evidence.get("generalCount"),
            "targetIdHex": dispatch_payload_evidence.get("targetIdHex"),
            "prepareLengthHex": dispatch_payload_evidence.get("prepareLengthHex"),
            "expeditionLengthHex": dispatch_payload_evidence.get("expeditionLengthHex"),
        },
        {"step": "dispatchResult/1522030", "ok": dispatch is not None and dispatch_success is True, "matched": dispatch is not None, "success": dispatch_success},
        {"step": "stop/logout", "ok": True, "evidence": "offline local logout marker; no network sent"},
    ]
    missing = [s["step"] for s in steps if not s.get("ok")]
    ready = not missing and contract["summary"]["shuaHuangOfflineReplayReady"]
    return {
        "summary": {
            "shuaHuangOfflineClosedLoopReplayReady": ready,
            "contractReady": contract["summary"]["shuaHuangOfflineReplayReady"],
            "generalCount": len(generals),
            "formationCount": len(formations),
            "targetCount": len(targets),
            "selectedFormationId": formation.get("id") if formation else None,
            "selectedTargetId": target.get("id") if target else None,
            "appliedTargetFilter": applied_filter,
            "targetSelectionEvidence": target_selection_evidence,
            "dispatchPayloadEvidence": dispatch_payload_evidence,
            "dispatchMatched": dispatch is not None,
            "dispatchSuccess": dispatch_success,
            "realActionNetworkAllowed": False,
            "blocker": "offline replay only; true brush-yellow action send remains disabled",
        },
        "missingSteps": missing,
        "steps": steps,
        "selected": {"formation": formation, "target": target, "dispatch": dispatch},
        "parsed": {"generals": generals, "formations": formations, "targets": targets},
        "replayContract": contract,
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 刷黄离线闭环回放报告",
        "",
        "## Summary",
        "",
        f"- shuaHuangOfflineClosedLoopReplayReady: {str(s['shuaHuangOfflineClosedLoopReplayReady']).lower()}",
        f"- contractReady: {str(s['contractReady']).lower()}",
        f"- generalCount: {s['generalCount']}",
        f"- formationCount: {s['formationCount']}",
        f"- targetCount: {s['targetCount']}",
        f"- selectedFormationId: {s['selectedFormationId']}",
        f"- selectedTargetId: {s['selectedTargetId']}",
        f"- dispatchMatched: {str(s['dispatchMatched']).lower()}",
        f"- dispatchSuccess: {str(s['dispatchSuccess']).lower() if s['dispatchSuccess'] is not None else 'null'}",
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
        "## Target selection evidence",
        "",
        "```json",
        json.dumps(s.get("targetSelectionEvidence", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Dispatch payload evidence",
        "",
        "```json",
        json.dumps(s.get("dispatchPayloadEvidence", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="channelExtra JSON such as base_channel_extra_merged.json or merged_channel_extra.json")
    ap.add_argument("--base", help="Optional base channelExtra JSON merged before input")
    ap.add_argument("--merge-extra", action="append", default=[], help="Additional channelExtra JSON merged after input; can repeat")
    ap.add_argument("--target-type", choices=["HUANG_JIN", "SHAN_ZEI"], default="HUANG_JIN")
    ap.add_argument("--start-x", type=int, default=0)
    ap.add_argument("--start-y", type=int, default=0)
    ap.add_argument("--out", help="Write JSON report; defaults to stdout")
    ap.add_argument("--markdown-out", help="Write Markdown report")
    ns = ap.parse_args()
    extra = merge_inputs(Path(ns.input), base=ns.base, merges=ns.merge_extra)
    report = replay(extra, target_type=ns.target_type, start_x=ns.start_x, start_y=ns.start_y)
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
