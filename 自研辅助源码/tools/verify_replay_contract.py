#!/usr/bin/env python3
"""Verify whether channelExtra JSON is sufficient for offline replay contracts.

This is a local verifier for outputs such as device_regression_from_logs.py's
merged_channel_extra.json. It does not contact devices/servers and does not enable real
action sends.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROLE_KEYS = ["roleName", "level"]
RESOURCE_KEYS = ["copper", "food"]
ROLE_RESOURCE_EVIDENCE_KEYS = [
    "roleResourceStateText", "roleResourceStateRaw", "state8004HeadText",
    "state8004PayloadUtf8", "state8004PayloadText", "state8004TailUtf8",
    "state8004TailText", "state8004TailUtf8Preview", "state8004PayloadHex",
    "state8004TailHex",
]
IDENTITY_KEYS = ["userId", "serverUrl"]
DM_KEYS = ["dm"]
GENERAL_KEYS = [
    "generalsJson", "jiangLingJson", "jianglingsJson", "jiangLingData", "jiangLingRaw",
    "wuJiangData", "generalsRaw", "state8004TailUtf8", "state8004TailText",
    "state8004TailUtf8Preview", "state8004PayloadUtf8", "state8004PayloadText",
    "state8004TailHex", "state8004PayloadHex",
]
FORMATION_KEYS = ["formationsJson", "xiaohuangPrefsJson", "sharedPrefsJson", "guajiPrefsJson", "recoveredPrefsJson"]
MAP_KEYS = ["mapTargetsJson", "mapTargetsHex", "targetSearchResponseHex", "targetSearchResponse"]
DISPATCH_KEYS = ["dispatchResultsJson"]
MINE_KEYS = ["mineTargetsJson", "mineTargetsHex", "resourcePointSearchResponseHex", "resourcePointSearchResponse"]
DAILY_KEYS = ["dailyStepResultsJson"]
UNSAFE_TRUE_KEYS = [
    "deviceRegressionNetworkSendAllowed", "actionResponseCalibrationNetworkSendAllowed",
    "dailyResponseCalibrationNetworkSendAllowed", "readOnlyCalibrationNetworkSendAllowed",
    "nativeWrapperNetworkSendAllowed", "networkSendAllowed",
]
HEX_RE = re.compile(r"^[0-9a-fA-F\s|]+$")
JIANG_LING_RE = re.compile(r"JiangLing\s*\{|\b(?:id|name|status|tili)\s*=", re.I)
FORMATION_PREF_RE = re.compile(r"shuahuangChuzhengBiandui|bianduihao|bianduiDejiangling", re.I)
TARGET_TEXT_RE = re.compile(r"黄巾|山贼|渠帅|主将|主帅|HUANG_JIN|SHAN_ZEI", re.I)
ROLE_RESOURCE_KV_RE = re.compile(r"[\"']?([\u4e00-\u9fa5A-Za-z_][\u4e00-\u9fa5A-Za-z0-9_]*)[\"']?\s*[:=]\s*('[^']*'|\"[^\"]*\"|[^,;|\s{}]+)")


def normalize_role_resource_key(key: str) -> str | None:
    k = key.strip()
    lower = k.lower()
    if lower in {"roleid", "monarchid", "kingid"} or k in {"君主ID", "角色ID", "主公ID", "玩家ID"}:
        return "roleId"
    if lower in {"rolename", "monarchname", "kingname"} or k in {"君主", "君主名", "角色名", "主公", "主公名", "玩家名"}:
        return "roleName"
    if lower == "level" or k in {"等级", "等級", "君主等级", "君主等級", "角色等级", "角色等級", "主公等级"}:
        return "level"
    if lower in {"nation", "country"} or k in {"国家", "國家", "势力", "勢力", "阵营", "陣營"}:
        return "nation"
    if lower in {"title", "officialtitle"} or k in {"官职", "官職", "爵位", "称号", "稱號"}:
        return "title"
    if lower in {"prestige", "shengwang"} or k in {"声望", "聲望"}:
        return "prestige"
    if lower in {"copper", "money", "tongqian"} or k in {"铜钱", "銅錢", "铜币", "銅幣", "钱币", "錢幣"}:
        return "copper"
    if lower in {"food", "liangshi"} or k in {"粮食", "糧食", "粮草", "糧草"}:
        return "food"
    if lower in {"copperperhour", "moneyperhour"} or k in {"铜钱产量", "銅錢產量", "铜钱每小时", "銅錢每小時", "钱产量"}:
        return "copperPerHour"
    if lower == "foodperhour" or k in {"粮食产量", "糧食產量", "粮食每小时", "糧食每小時"}:
        return "foodPerHour"
    if lower in {"populationcurrent", "population", "renkou"} or k in {"人口", "当前人口", "當前人口"}:
        return "populationCurrent"
    if lower in {"populationcap", "populationlimit"} or k in {"人口上限", "人口容量"}:
        return "populationCap"
    if lower in {"resourcepointcurrent", "resourcepointused"} or k in {"资源点", "資源點", "资源点占用", "資源點占用", "已用资源点", "已用資源點"}:
        return "resourcePointCurrent"
    if lower in {"resourcepointcap", "resourcepointlimit"} or k in {"资源点上限", "資源點上限", "资源点容量", "資源點容量"}:
        return "resourcePointCap"
    return None


def normalize_role_resource_value(key: str, value: str) -> str:
    v = value.strip().strip("'\"")
    if key == "nation":
        if v.lower() == "wei" or v in {"魏国", "魏國"}:
            return "魏"
        if v.lower() == "shu" or v in {"蜀国", "蜀國"}:
            return "蜀"
        if v.lower() == "wu" or v in {"吴国", "吳國"}:
            return "吴"
    return v


def decode_hex_text(raw: str) -> str | None:
    cleaned = "".join(ch for ch in raw.strip().removeprefix("0x").removeprefix("0X") if ch in "0123456789abcdefABCDEF")
    if len(cleaned) < 2 or len(cleaned) % 2:
        return None
    try:
        return bytes.fromhex(cleaned).decode("utf-8", errors="ignore")
    except Exception:
        return None


def recover_role_resource_from_text(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    text = "".join(ch if (0x20 <= ord(ch) <= 0x7e or "\u4e00" <= ch <= "\u9fff") else "|" for ch in raw)
    for match in ROLE_RESOURCE_KV_RE.finditer(text):
        key = normalize_role_resource_key(match.group(1))
        if not key:
            continue
        value = normalize_role_resource_value(key, match.group(2))
        if value:
            out[key] = value
    has_role = bool(out.get("roleName") and out.get("level"))
    has_resource = bool(out.get("copper") and out.get("food"))
    return out if has_role or has_resource else {}


def recover_role_resource_evidence(extra: dict[str, str]) -> dict[str, str]:
    for key in ROLE_RESOURCE_EVIDENCE_KEYS:
        raw = extra.get(key, "").strip()
        if not raw:
            continue
        recovered = recover_role_resource_from_text(raw)
        if recovered:
            recovered.setdefault("roleResourceEvidenceSource", key)
            return recovered
        if key.lower().endswith("hex"):
            decoded = decode_hex_text(raw) or ""
            recovered = recover_role_resource_from_text(decoded)
            if recovered:
                recovered.setdefault("roleResourceEvidenceSource", key)
                return recovered
    return {}


def with_recovered_role_resource(extra: dict[str, str]) -> dict[str, str]:
    recovered = recover_role_resource_evidence(extra)
    if not recovered:
        return dict(extra)
    out = dict(extra)
    for key, value in recovered.items():
        out.setdefault(key, value)
    return out


def load_json(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return {str(k): str(v) for k, v in data.items() if v is not None}


def first_present(extra: dict[str, str], keys: list[str]) -> str | None:
    for key in keys:
        if extra.get(key, "").strip():
            return key
    return None


def all_present(extra: dict[str, str], keys: list[str]) -> list[str]:
    return [key for key in keys if extra.get(key, "").strip()]


def unsafe_flags(extra: dict[str, str]) -> list[str]:
    out = []
    for key in UNSAFE_TRUE_KEYS:
        value = extra.get(key)
        if value is not None and value.strip().lower() in {"true", "1", "yes", "on"}:
            out.append(key)
    return out


def check_json_array_field(extra: dict[str, str], key: str) -> bool:
    raw = extra.get(key, "").strip()
    if not raw:
        return False
    try:
        value = json.loads(raw)
    except Exception:
        return False
    return isinstance(value, list) and len(value) > 0


def parse_json(raw: str) -> Any | None:
    try:
        return json.loads(raw)
    except Exception:
        return None


def non_empty_jsonish(raw: str) -> bool:
    value = parse_json(raw)
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return len(value) > 0
    return False


def valid_hex_blob(raw: str, min_bytes: int = 6) -> bool:
    text = raw.strip()
    if not text or not HEX_RE.match(text):
        return False
    cleaned = "".join(ch for ch in text if ch in "0123456789abcdefABCDEF")
    return len(cleaned) >= min_bytes * 2 and len(cleaned) % 2 == 0


def first_valid_general_source(extra: dict[str, str]) -> str | None:
    for key in GENERAL_KEYS:
        raw = extra.get(key, "").strip()
        if not raw:
            continue
        if key.lower().endswith("json") and non_empty_jsonish(raw):
            return key
        if key.lower().endswith("hex") and valid_hex_blob(raw, min_bytes=12):
            return key
        if JIANG_LING_RE.search(raw):
            return key
        if "JiangLing" in key and raw:
            return key
    return None


def general_evidence_summary(extra: dict[str, str]) -> dict[str, Any]:
    source = first_valid_general_source(extra)
    raw = extra.get(source or "", "").strip() if source else ""
    count = 0
    source_kind = ""
    if source:
        value = parse_json(raw)
        if isinstance(value, list):
            count = len(value)
            source_kind = "json-list"
        elif isinstance(value, dict):
            arrays = [v for v in value.values() if isinstance(v, list)]
            count = max([len(v) for v in arrays] + ([1] if value else [0]))
            source_kind = "json-object"
        elif source.lower().endswith("hex"):
            decoded = decode_hex_text(raw) or ""
            count = max(len(re.findall(r"JiangLing\s*\{", decoded, re.I)), len(re.findall(r"\bid\s*=", decoded, re.I)))
            if count == 0 and valid_hex_blob(raw, min_bytes=12):
                count = 1
            source_kind = "state8004-hex"
        else:
            count = max(len(re.findall(r"JiangLing\s*\{", raw, re.I)), len(re.findall(r"\bid\s*=", raw, re.I)))
            if count == 0 and "JiangLing" in source and raw:
                count = 1
            source_kind = "state8004-text" if source.startswith("state8004") else "text"
    return {
        "generalEvidenceParseReady": bool(source and count > 0),
        "generalEvidenceSource": source or "",
        "generalEvidenceSourceKind": source_kind,
        "generalEvidenceCount": count,
        "fromState8004Evidence": bool(source and source.startswith("state8004")),
    }


def role_resource_parse_summary(extra: dict[str, str], recovered: dict[str, str]) -> dict[str, Any]:
    top_level_ready = all(extra.get(key, "").strip() for key in ROLE_KEYS + RESOURCE_KEYS)
    recovered_ready = bool(recovered and (recovered.get("roleName") or recovered.get("level")) and (recovered.get("copper") or recovered.get("food")))
    return {
        "roleResourceParseReady": bool(top_level_ready or recovered_ready),
        "topLevelRoleResourceReady": bool(top_level_ready),
        "recoveredRoleResourceReady": bool(recovered_ready),
        "roleResourceEvidenceSource": recovered.get("roleResourceEvidenceSource", "") if recovered else "",
        "roleName": extra.get("roleName") or recovered.get("roleName", ""),
        "level": extra.get("level") or recovered.get("level", ""),
        "copper": extra.get("copper") or recovered.get("copper", ""),
        "food": extra.get("food") or recovered.get("food", ""),
    }


def first_valid_formation_source(extra: dict[str, str]) -> str | None:
    for key in FORMATION_KEYS:
        raw = extra.get(key, "").strip()
        if not raw:
            continue
        value = parse_json(raw)
        if isinstance(value, list) and len(value) > 0:
            return key
        if isinstance(value, dict):
            keys = {str(k) for k in value.keys()}
            has_enabled = any(k.startswith("shuahuangChuzhengBiandui") and str(value.get(k)).lower() in {"true", "1", "yes", "on"} for k in keys)
            has_formation = any(k.startswith("bianduihao") for k in keys)
            has_general = any(k.startswith("bianduiDejiangling") for k in keys)
            if has_enabled or (has_formation and has_general) or ("formations" in key.lower() and len(value) > 0):
                return key
        if FORMATION_PREF_RE.search(raw):
            return key
    return None


def first_valid_map_source(extra: dict[str, str]) -> str | None:
    for key in MAP_KEYS:
        raw = extra.get(key, "").strip()
        if not raw:
            continue
        if key == "mapTargetsJson" and check_json_array_field(extra, key):
            return key
        if "Hex" in key and valid_hex_blob(raw, min_bytes=10):
            return key
        if key == "targetSearchResponse" and (valid_hex_blob(raw, min_bytes=10) or TARGET_TEXT_RE.search(raw)):
            return key
    return None


def first_valid_mine_source(extra: dict[str, str]) -> str | None:
    for key in MINE_KEYS:
        raw = extra.get(key, "").strip()
        if not raw:
            continue
        if key == "mineTargetsJson" and check_json_array_field(extra, key):
            return key
        if "Hex" in key and valid_hex_blob(raw, min_bytes=10):
            return key
        if key == "resourcePointSearchResponse" and valid_hex_blob(raw, min_bytes=10):
            return key
    return None


def usable_dispatch_results(extra: dict[str, str]) -> bool:
    raw = extra.get("dispatchResultsJson", "").strip()
    value = parse_json(raw)
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if not isinstance(item, dict):
            continue
        nested = item.get("raw") if isinstance(item.get("raw"), dict) else {}
        has_target = str(
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
            or ""
        ).strip() != ""
        has_formation = str(
            item.get("formationId")
            or item.get("formationID")
            or item.get("formation")
            or item.get("formationNo")
            or item.get("formationIdHex")
            or item.get("bianduihao")
            or item.get("biandui")
            or nested.get("formationId")
            or nested.get("bianduihao")
            or ""
        ).strip() != ""
        has_result = (
            any(key in item for key in ("success", "ok", "dispatchSuccess", "result", "status", "state")) or
            any(str(item.get(key) or nested.get(key) or "").strip() != "" for key in (
                "responseText", "response", "rawResponse", "bodyText", "body", "responseBody",
                "resultText", "rawText", "dispatchResponse", "responseHex", "rawResponseHex",
                "bodyHex", "responseBodyHex", "rawHex",
            ))
        )
        if has_target and has_formation and has_result:
            return True
    return False


def usable_daily_results(extra: dict[str, str]) -> bool:
    raw = extra.get("dailyStepResultsJson", "").strip()
    value = parse_json(raw)
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if isinstance(item, dict) and str(item.get("step") or item.get("dailyStep") or "").strip():
            return True
    return False


def verify(extra: dict[str, str]) -> dict[str, Any]:
    extra = with_recovered_role_resource(extra)
    role_resource_evidence = recover_role_resource_evidence(extra)
    general_evidence = general_evidence_summary(extra)
    role_resource_parse = role_resource_parse_summary(extra, role_resource_evidence)
    evidence: dict[str, Any] = {
        "identity": all_present(extra, IDENTITY_KEYS),
        "dm": all_present(extra, DM_KEYS),
        "role": all_present(extra, ROLE_KEYS),
        "resource": all_present(extra, RESOURCE_KEYS),
        "roleResourceEvidence": role_resource_evidence,
        "roleResourceParse": role_resource_parse,
        "generalEvidence": general_evidence,
        "generalSource": first_present(extra, GENERAL_KEYS),
        "formationSource": first_present(extra, FORMATION_KEYS),
        "mapSource": first_present(extra, MAP_KEYS),
        "dispatchSource": first_present(extra, DISPATCH_KEYS),
        "mineSource": first_present(extra, MINE_KEYS),
        "dailySource": first_present(extra, DAILY_KEYS),
        "dispatchResultsJsonValidArray": check_json_array_field(extra, "dispatchResultsJson"),
        "dailyStepResultsJsonValidArray": check_json_array_field(extra, "dailyStepResultsJson"),
        "generalParseReadySource": first_valid_general_source(extra),
        "formationParseReadySource": first_valid_formation_source(extra),
        "mapParseReadySource": first_valid_map_source(extra),
        "mineParseReadySource": first_valid_mine_source(extra),
        "dispatchResultsUsable": usable_dispatch_results(extra),
        "dailyStepResultsUsable": usable_daily_results(extra),
        "unsafeTrueFlags": unsafe_flags(extra),
    }
    missing_shua = []
    if len(evidence["identity"]) < len(IDENTITY_KEYS): missing_shua.append("identity:userId/serverUrl")
    if len(evidence["role"]) < len(ROLE_KEYS): missing_shua.append("role:roleName/level")
    if len(evidence["resource"]) < len(RESOURCE_KEYS): missing_shua.append("resource:copper/food")
    if not evidence["generalSource"] or not evidence["generalParseReadySource"]: missing_shua.append("generals:parseable")
    if not evidence["formationSource"] or not evidence["formationParseReadySource"]: missing_shua.append("formations:parseable")
    if not evidence["mapSource"] or not evidence["mapParseReadySource"]: missing_shua.append("mapTargets/041540:parseable")
    if not evidence["dispatchSource"] or not evidence["dispatchResultsJsonValidArray"] or not evidence["dispatchResultsUsable"]: missing_shua.append("dispatchResultsJson:usable")
    if evidence["unsafeTrueFlags"]: missing_shua.append("unsafe network flag must be false")

    missing_daily = []
    if len(evidence["identity"]) < len(IDENTITY_KEYS): missing_daily.append("identity:userId/serverUrl")
    if not evidence["dailySource"] or not evidence["dailyStepResultsJsonValidArray"] or not evidence["dailyStepResultsUsable"]: missing_daily.append("dailyStepResultsJson:usable")
    if evidence["unsafeTrueFlags"]: missing_daily.append("unsafe network flag must be false")

    missing_mine = []
    if len(evidence["identity"]) < len(IDENTITY_KEYS): missing_mine.append("identity:userId/serverUrl")
    if not evidence["mineSource"] or not evidence["mineParseReadySource"]: missing_mine.append("mineTargets/041542:parseable")
    if evidence["unsafeTrueFlags"]: missing_mine.append("unsafe network flag must be false")

    return {
        "summary": {
            "shuaHuangOfflineReplayReady": not missing_shua,
            "dailyOfflineReplayReady": not missing_daily,
            "mineOfflineReplayReady": not missing_mine,
            "roleResourceParseReady": role_resource_parse["roleResourceParseReady"],
            "generalEvidenceParseReady": general_evidence["generalEvidenceParseReady"],
            "state8004GeneralEvidenceReady": general_evidence["fromState8004Evidence"],
            "realActionNetworkAllowed": False,
            "blocker": "offline replay contract only; true action send remains disabled",
        },
        "missing": {
            "shuaHuang": missing_shua,
            "daily": missing_daily,
            "mine": missing_mine,
        },
        "evidence": evidence,
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# ChannelExtra 离线回放契约校验",
        "",
        "## Summary",
        "",
        f"- shuaHuangOfflineReplayReady: {str(s['shuaHuangOfflineReplayReady']).lower()}",
        f"- dailyOfflineReplayReady: {str(s['dailyOfflineReplayReady']).lower()}",
        f"- mineOfflineReplayReady: {str(s['mineOfflineReplayReady']).lower()}",
        f"- roleResourceParseReady: {str(s['roleResourceParseReady']).lower()}",
        f"- generalEvidenceParseReady: {str(s['generalEvidenceParseReady']).lower()}",
        f"- state8004GeneralEvidenceReady: {str(s['state8004GeneralEvidenceReady']).lower()}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## Missing",
        "",
        "```json",
        json.dumps(report["missing"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Evidence",
        "",
        "```json",
        json.dumps(report["evidence"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="channelExtra JSON file, e.g. merged_channel_extra.json")
    ap.add_argument("--base", help="Optional base channelExtra/session JSON merged before input")
    ap.add_argument("--out", help="Output JSON report; defaults to stdout")
    ap.add_argument("--markdown-out", help="Optional Markdown report path")
    ns = ap.parse_args()
    extra = {}
    if ns.base:
        extra.update(load_json(Path(ns.base)))
    extra.update(load_json(Path(ns.input)))
    report = verify(extra)
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
