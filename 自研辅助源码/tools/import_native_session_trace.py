#!/usr/bin/env python3
"""Import Frida native/session trace logs into self-developed assistant channelExtra JSON.

Input is a log produced by reverse_cases/apk/scripts/frida_native_session_trace_v2.js.
The script extracts HelpClass/Dbsl returns and explicit lx/key/lb markers when present.
It does not contact devices or servers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

RET_PATTERNS = [
    re.compile(r"\[java-native-ret\]\s+(?P<class>[\w.$]+)\.(?P<method>\w+)\s+=>\s+(?P<value>.*)$"),
    re.compile(r"\[jni-ret\]\s+(?P<method>\w+)\([^)]*\).*?=>\s+(?P<value>.*)$"),
]
WRAPPER_JSON = re.compile(r"\[native-wrapper-json\]\s*(?P<json>\{.*\})")
GAME_WRAPPER_CALL = re.compile(r"\[game-wrapper-call\].*?gameHex=(?P<gameHex>[0-9a-fA-F]+)(?:.*?rawBody=(?P<rawBody>[^\s]+))?", re.I)
EXPLICIT_FIELD = re.compile(r"\b(?P<key>nativeWrapperLx|recoveredNativeLx|\blx\b|nativeWrapperKey|recoveredNativeKey|\bkey\b|nativeWrapperLb|recoveredNativeLb|\blb\b)\s*[:=]\s*(?P<value>[^\s,;]+)", re.I)

METHOD_TO_KEYS = {
    "getSession": ["recoveredNativeSession", "helpClassSession"],
    "getKey": ["recoveredNativeKey", "helpClassKey"],
    "getPassCode": ["recoveredNativePassCode", "helpClassPassCode"],
    "getMiMaCode": ["recoveredNativeMiMaCode", "helpClassMiMaCode"],
    "gK": ["dbslGk"],
    "gP": ["dbslGp"],
    "getInterfaceUrl": ["dbslInterfaceUrl"],
    "getInterfaceUrl2": ["dbslInterfaceUrl2"],
    "getHost": ["alwaysHopeHost"],
    "updateUrl": ["alwaysHopeUpdateUrl"],
    "getHostChild": ["helpClassHostChild"],
}
FIELD_ALIASES = {
    "nativewrapperlx": "nativeWrapperLx",
    "recoverednativelx": "recoveredNativeLx",
    "lx": "nativeWrapperLx",
    "nativewrapperkey": "nativeWrapperKey",
    "recoverednativekey": "recoveredNativeKey",
    "key": "nativeWrapperKey",
    "nativewrapperlb": "nativeWrapperLb",
    "recoverednativelb": "recoveredNativeLb",
    "lb": "nativeWrapperLb",
}

def is_masked(value: str) -> bool:
    return "…" in value or "(len=" in value or "****" in value

def clean(value: str) -> str:
    return value.strip().strip('"\'')

def parse(text: str, include_raw_body: bool = False) -> dict[str, str]:
    extra: dict[str, str] = {}
    masked = False
    seen_methods = []
    for line in text.splitlines():
        wrapper_json = WRAPPER_JSON.search(line)
        if wrapper_json:
            try:
                obj = json.loads(wrapper_json.group("json"))
                ingest_wrapper_object(extra, obj, include_raw_body)
            except Exception as exc:
                extra["nativeWrapperJsonImportError"] = str(exc)
        wrapper_call = GAME_WRAPPER_CALL.search(line)
        if wrapper_call:
            game_hex = clean(wrapper_call.group("gameHex") or "")
            raw_body = clean(wrapper_call.group("rawBody") or "")
            if game_hex:
                extra["nativeWrapperGameHex"] = game_hex
            if raw_body:
                ingest_wrapper_object(extra, {"gameHex": game_hex, "rawBody": raw_body}, include_raw_body)
        for m in RET_PATTERNS:
            mm = m.search(line)
            if not mm:
                continue
            method = mm.group("method")
            value = clean(mm.group("value"))
            if not value or value.startswith("<"):
                continue
            if is_masked(value):
                masked = True
            for key in METHOD_TO_KEYS.get(method, []):
                extra.setdefault(key, value)
            if method in METHOD_TO_KEYS:
                seen_methods.append(method)
        for mm in EXPLICIT_FIELD.finditer(line):
            key = FIELD_ALIASES[mm.group("key").lower()]
            value = clean(mm.group("value"))
            if is_masked(value):
                masked = True
            extra[key] = value
    if seen_methods:
        extra["nativeTraceMethods"] = ",".join(dict.fromkeys(seen_methods))
    extra["nativeTraceValuesMasked"] = str(masked).lower()
    extra["nativeTraceImporter"] = "tools/import_native_session_trace.py"
    enrich_wrapper_field_audit(extra)
    return extra

def wrapper_field_candidates(extra: dict[str, str]) -> dict[str, list[str]]:
    return {
        "lx": [key for key in ("nativeWrapperLx", "recoveredNativeLx", "derivedNativeWrapperLx") if extra.get(key)],
        "key": [key for key in ("nativeWrapperKey", "recoveredNativeKey", "helpClassKey", "dbslGk", "derivedNativeWrapperKey") if extra.get(key)],
        "lb": [key for key in ("nativeWrapperLb", "recoveredNativeLb", "derivedNativeWrapperLb") if extra.get(key)],
    }

def selected_candidate(extra: dict[str, str], candidates: list[str]) -> tuple[str, str]:
    for key in candidates:
        value = extra.get(key, "")
        if value:
            return key, value
    return "", ""

def hash_or_empty(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest() if value else ""

def enrich_wrapper_field_audit(extra: dict[str, str]) -> None:
    """Add a non-secret audit summary for lx/key/lb provenance.

    Values are intentionally not embedded in the JSON audit; only source keys, lengths
    and SHA-256 hashes are recorded. This lets device regression reports show whether
    wrapper fields came from explicit Frida JSON, native returns, or derived split data.
    """
    candidates = wrapper_field_candidates(extra)
    lx_source, lx_value = selected_candidate(extra, candidates["lx"])
    key_source, key_value = selected_candidate(extra, candidates["key"])
    lb_source, lb_value = selected_candidate(extra, candidates["lb"])
    split_statuses = [item for item in extra.get("nativeWrapperSplitStatus", "").split(",") if item]
    prefix_ok = (
        "prefix_equals_lx_plus_key" in split_statuses or
        "prefix_starts_with_lx" in split_statuses or
        "prefix_ends_with_key" in split_statuses
    )
    suffix_ok = "suffix_equals_lb" in split_statuses or "suffix_assumed_lb" in split_statuses
    values_masked = any(is_masked(value) for value in (lx_value, key_value, lb_value) if value)
    audit = {
        "lxPresent": bool(lx_value),
        "keyPresent": bool(key_value),
        "lbPresent": bool(lb_value),
        "selectedLxSource": lx_source,
        "selectedKeySource": key_source,
        "selectedLbSource": lb_source,
        "lxCandidateSources": candidates["lx"],
        "keyCandidateSources": candidates["key"],
        "lbCandidateSources": candidates["lb"],
        "selectedLxLength": len(lx_value) if lx_value else 0,
        "selectedKeyLength": len(key_value) if key_value else 0,
        "selectedLbLength": len(lb_value) if lb_value else 0,
        "selectedLxSha256": hash_or_empty(lx_value),
        "selectedKeySha256": hash_or_empty(key_value),
        "selectedLbSha256": hash_or_empty(lb_value),
        "splitStatuses": split_statuses,
        "prefixSplitProven": prefix_ok,
        "suffixObserved": suffix_ok,
        "rawBodyObserved": bool(extra.get("nativeWrapperRawBodySha256")),
        "rawBodyLength": int(extra.get("nativeWrapperRawBodyLength", "0") or 0),
        "prefixBeforeGameHexLength": int(extra.get("nativeWrapperPrefixBeforeGameHexLength", "0") or 0),
        "suffixAfterGameHexLength": int(extra.get("nativeWrapperSuffixAfterGameHexLength", "0") or 0),
        "valuesMasked": values_masked or extra.get("nativeTraceValuesMasked", "false").lower() == "true",
        "readyForDryRunWrapperPlan": bool(lx_value and key_value and lb_value and prefix_ok and suffix_ok and not values_masked),
        "networkSendAllowed": False,
    }
    extra["nativeWrapperFieldAuditJson"] = json.dumps(audit, ensure_ascii=False, sort_keys=True)
    extra["nativeWrapperFieldAuditReady"] = str(audit["readyForDryRunWrapperPlan"]).lower()
    extra["nativeWrapperFieldAuditNetworkSendAllowed"] = "false"

def ingest_wrapper_object(extra: dict[str, str], obj: dict, include_raw_body: bool) -> None:
    aliases = {
        "lx": "nativeWrapperLx",
        "key": "nativeWrapperKey",
        "lb": "nativeWrapperLb",
        "session": "recoveredNativeSession",
        "passCode": "recoveredNativePassCode",
        "gameHex": "nativeWrapperGameHex",
        "source": "nativeWrapperSource",
        "threadId": "nativeWrapperThreadId",
        "byteCount": "nativeWrapperByteCount",
        "offset": "nativeWrapperOffset",
    }
    for src, dst in aliases.items():
        value = obj.get(src)
        if value is not None and str(value).strip():
            extra[dst] = clean(str(value))
    raw_body = obj.get("rawBody") or obj.get("body") or obj.get("requestBody")
    game_hex = obj.get("gameHex") or extra.get("nativeWrapperGameHex")
    if raw_body is None:
        return
    raw_body = clean(str(raw_body))
    extra["nativeWrapperRawBodySha256"] = hashlib.sha256(raw_body.encode("utf-8", errors="replace")).hexdigest()
    extra["nativeWrapperRawBodyLength"] = str(len(raw_body))
    if include_raw_body:
        extra["nativeWrapperRawBody"] = raw_body
    if game_hex and str(game_hex) in raw_body:
        before, after = raw_body.split(str(game_hex), 1)
        extra["nativeWrapperPrefixBeforeGameHexLength"] = str(len(before))
        extra["nativeWrapperSuffixAfterGameHexLength"] = str(len(after))
        derive_wrapper_split(extra, before, after)
        if include_raw_body:
            extra["nativeWrapperPrefixBeforeGameHex"] = before
            extra["nativeWrapperSuffixAfterGameHex"] = after

def derive_wrapper_split(extra: dict[str, str], prefix: str, suffix: str) -> None:
    """Best-effort lx/key/lb derivation for the known lx+key+gameHex+lb shape.

    The function only derives fields from already captured evidence. It does not validate
    against a server and does not imply the wrapper can be sent.
    """
    known_lx = extra.get("nativeWrapperLx") or extra.get("recoveredNativeLx")
    known_key = extra.get("nativeWrapperKey") or extra.get("recoveredNativeKey") or extra.get("helpClassKey") or extra.get("dbslGk")
    known_lb = extra.get("nativeWrapperLb") or extra.get("recoveredNativeLb")
    status = []

    if known_lx and prefix.startswith(known_lx):
        extra.setdefault("derivedNativeWrapperLx", known_lx)
        rest = prefix[len(known_lx):]
        if rest:
            extra.setdefault("derivedNativeWrapperKey", rest)
            status.append("prefix_starts_with_lx")
    if known_key and prefix.endswith(known_key):
        extra.setdefault("derivedNativeWrapperKey", known_key)
        rest = prefix[:-len(known_key)] if known_key else prefix
        extra.setdefault("derivedNativeWrapperLx", rest)
        status.append("prefix_ends_with_key")
    if known_lx and known_key and prefix == known_lx + known_key:
        status.append("prefix_equals_lx_plus_key")
    if not known_lx and not known_key and prefix:
        extra.setdefault("nativeWrapperUnsplitPrefixSha256", hashlib.sha256(prefix.encode("utf-8", errors="replace")).hexdigest())
        status.append("prefix_unsplit")

    if known_lb and suffix == known_lb:
        extra.setdefault("derivedNativeWrapperLb", known_lb)
        status.append("suffix_equals_lb")
    elif suffix:
        extra.setdefault("derivedNativeWrapperLb", suffix)
        status.append("suffix_assumed_lb")
    elif not suffix:
        status.append("empty_suffix")

    if status:
        extra["nativeWrapperSplitStatus"] = ",".join(dict.fromkeys(status))

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="Frida native/session trace log")
    ap.add_argument("--out", help="Output JSON file; defaults to stdout")
    ap.add_argument("--include-raw-body", action="store_true", help="Persist raw wrapper body/prefix/suffix instead of only hashes and lengths")
    ns = ap.parse_args()
    text = Path(ns.input).read_text(encoding="utf-8", errors="replace")
    result = parse(text, include_raw_body=ns.include_raw_body)
    data = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)

if __name__ == "__main__":
    main()
