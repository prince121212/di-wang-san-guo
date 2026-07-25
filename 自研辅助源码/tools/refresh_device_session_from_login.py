#!/usr/bin/env python3
"""Refresh the installed self-app real session through the recovered login chain.

The UI login flow is convenient when the device is unlocked, but live regression
often needs a fresh dm/session while the app is stopped or the phone is locked.
This helper performs the same recovered passport -> enter area -> 0x1003 ->
0x1004 -> 0x1016 chain, then writes only refreshed session/channelExtra fields
back into the first saved account.  Existing regression gates and selected
formation metadata are preserved.

Password handling is intentionally non-echoing:
  - prefer DWPM_TEST_PASSWORD from the environment, or
  - prompt with getpass when running interactively.
The password is never written to reports or shared_prefs by this script.
"""
from __future__ import annotations

import argparse
import csv
import getpass
import html
import importlib.util
import json
import os
import re
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
ITEM_MAPPING_CANDIDATES = [
    PROJECT.parent / "reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/item_mapping/item_full_mapping.csv",
    PROJECT.parent / "ctf_out/apk/assets/script/scriptItem.sc",
]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


direct_probe = load_module("direct_binary_action_probe", ROOT / "direct_binary_action_probe.py")
device_extra = load_module("configure_device_session_extra", ROOT / "configure_device_session_extra.py")
prereq = load_module("check_brush_yellow_prereq", ROOT / "check_brush_yellow_prereq.py")


PACKAGE = "com.example.dwpmclone"


def parse_accounts_xml(raw_xml: str) -> tuple[str, dict[str, Any], str]:
    m = re.search(r'(<string name="accounts_json">)(.*?)(</string>)', raw_xml, re.S)
    if not m:
        raise ValueError("accounts_json not found")
    root = json.loads(html.unescape(m.group(2)))
    return raw_xml[:m.start(2)], root, raw_xml[m.end(2):]


def first_account(root: dict[str, Any]) -> dict[str, Any]:
    accounts = root.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("no accounts")
    account = accounts[0]
    if not isinstance(account, dict):
        raise ValueError("first account is not an object")
    account.setdefault("session", {}).setdefault("channelExtra", {})
    return account


def parse_8004_head(payload: bytes, source_opcode: str = "refresh/0x1016/0x8004") -> dict[str, Any]:
    p = 0

    def need(n: int) -> None:
        if p + n > len(payload):
            raise ValueError(f"0x8004 parse overflow pos={p} need={n} size={len(payload)}")

    def i8() -> int:
        nonlocal p
        need(1)
        v = struct.unpack(">b", payload[p:p + 1])[0]
        p += 1
        return v

    def u8() -> int:
        nonlocal p
        need(1)
        v = payload[p]
        p += 1
        return v

    def i16() -> int:
        nonlocal p
        need(2)
        v = struct.unpack(">h", payload[p:p + 2])[0]
        p += 2
        return v

    def i32() -> int:
        nonlocal p
        need(4)
        v = struct.unpack(">i", payload[p:p + 4])[0]
        p += 4
        return v

    def i64() -> int:
        nonlocal p
        need(8)
        v = struct.unpack(">q", payload[p:p + 8])[0]
        p += 8
        return v

    def utf() -> str:
        nonlocal p
        need(2)
        ln = struct.unpack(">H", payload[p:p + 2])[0]
        p += 2
        need(ln)
        s = payload[p:p + ln].decode("utf-8", errors="ignore")
        p += ln
        return s

    i8()  # status1
    i8()  # status2
    server_time = i64()
    role_id = i64()
    role_name = utf()
    i8()
    level = u8()
    copper = i64()
    food = i64()
    i64()
    i8()
    i16()
    i8()
    prestige = i64()
    prestige_prev = i64()
    prestige_next = i64()
    i64()
    i8()
    copper_per_hour = i32()
    food_per_hour = i32()
    i64()
    i64()
    population_current = i64()
    population_cap = i64()
    fief_limit = u8()
    general_limit = u8()
    resource_point_current = u8()
    resource_point_cap = u8()
    parsed_head = p
    tail = payload[parsed_head:]
    tail_preview = re.sub(r"\s+", " ", "".join(
        ch if (0x20 <= ord(ch) <= 0x7e or "\u4e00" <= ch <= "\u9fff") else " "
        for ch in tail.decode("utf-8", errors="ignore")
    )).strip()[:4096]
    return {
        "roleId": role_id,
        "roleName": role_name,
        "level": level,
        "copper": copper,
        "food": food,
        "prestige": prestige,
        "prestigePrevThreshold": prestige_prev,
        "prestigeNextThreshold": prestige_next,
        "copperPerHour": copper_per_hour,
        "foodPerHour": food_per_hour,
        "populationCurrent": population_current,
        "populationCap": population_cap,
        "fiefLimit": fief_limit,
        "generalLimit": general_limit,
        "resourcePointCurrent": resource_point_current,
        "resourcePointCap": resource_point_cap,
        "serverTimeMillis": server_time,
        "sourceOpcode": source_opcode,
        "payloadByteCount": len(payload),
        "parsedHeadByteCount": parsed_head,
        "tailByteCount": len(tail),
        "payloadHex": payload.hex(),
        "tailHex": tail.hex(),
        "tailUtf8Preview": tail_preview,
    }


def fresh_login_state(username: str, password: str, server_query: str) -> dict[str, Any]:
    fresh = direct_probe.fresh_login(username, password, server_query)
    role = fresh["role"]
    code, data, packets = direct_probe.post_game(
        fresh["gameHttp"],
        [(0x1016, struct.pack(">q", int(role["roleId"])))],
        int(fresh["dm"]),
    )
    p8004 = next((p for p in packets if p.get("opcode") == 0x8004), None)
    if not p8004:
        opcodes = [f"0x{p.get('opcode', 0):04x}" for p in packets if "opcode" in p]
        raise RuntimeError(f"fresh login 0x1016 did not return 0x8004; opcodes={opcodes}")
    state = parse_8004_head(p8004["payload"])
    inventory_packets: list[dict[str, Any]] = []
    inventory_state: dict[str, Any] | None = None
    inventory_error = ""
    try:
        _, _, inventory_packets = direct_probe.post_game(
            fresh["gameHttp"],
            [(0x1104, b"\x00")],
            int(fresh["dm"]),
        )
        p8104 = next((p for p in inventory_packets if p.get("opcode") == 0x8104), None)
        if p8104:
            inventory_state = parse_8104_inventory(p8104["payload"])
        else:
            inventory_error = f"0x1104 did not return 0x8104; opcodes={[hex(p.get('opcode', 0)) for p in inventory_packets if 'opcode' in p]}"
    except Exception as exc:
        inventory_error = str(exc)
    return {
        "fresh": fresh,
        "http": code,
        "responseBytes": len(data),
        "opcodes": [f"0x{p.get('opcode', 0):04x}" for p in (packets + inventory_packets) if "opcode" in p],
        "state": state,
        "inventory": inventory_state,
        "inventoryError": inventory_error,
    }


def load_item_names() -> dict[int, dict[str, str]]:
    csv_path = next((p for p in ITEM_MAPPING_CANDIDATES if p.suffix == ".csv" and p.exists()), None)
    if not csv_path:
        return {}
    out: dict[int, dict[str, str]] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                item_id = int(row.get("item_id") or "")
            except ValueError:
                continue
            out[item_id] = {
                "name": row.get("name") or f"道具#{item_id}",
                "type": row.get("type_label") or "",
            }
    return out


def parse_8104_inventory(payload: bytes, source_opcode: str = "0x1104/0x8104") -> dict[str, Any]:
    if len(payload) < 18:
        raise ValueError(f"0x8104 payload too short: {len(payload)}")
    capacity = int.from_bytes(payload[14:16], "big")
    item_count = int.from_bytes(payload[16:18], "big")
    if not (0 <= item_count <= 512):
        raise ValueError(f"0x8104 item_count out of range: {item_count}")
    items_end = 18 + item_count * 12
    if items_end > len(payload):
        raise ValueError(f"0x8104 item records overflow: end={items_end} size={len(payload)}")
    item_names = load_item_names()
    items: list[dict[str, Any]] = []
    for index in range(item_count):
        offset = 18 + index * 12
        item_id = int.from_bytes(payload[offset:offset + 2], "big")
        count = int.from_bytes(payload[offset + 2:offset + 4], "big")
        meta = item_names.get(item_id, {})
        name = meta.get("name") or f"道具#{item_id}"
        items.append({
            "id": item_id,
            "itemId": item_id,
            "name": name,
            "count": count,
            "type": meta.get("type") or "",
            "nameSource": "scriptItem.sc" if item_id in item_names else "raw-item-id",
            "source": source_opcode,
            "offset": offset,
            "rawTailHex": payload[offset + 4:offset + 12].hex(),
        })
    return {
        "capacity": capacity,
        "itemCount": item_count,
        "items": items,
        "sourceOpcode": source_opcode,
        "payloadByteCount": len(payload),
        "payloadHex": payload.hex(),
        "parsedItemByteCount": items_end,
        "tailHex": payload[items_end:].hex(),
    }


def recover_status_from_8004(hexstr: str) -> list[dict[str, Any]]:
    if not hexstr:
        return []
    try:
        bs = bytes.fromhex(hexstr)
    except ValueError:
        return []
    hits: list[dict[str, Any]] = []
    for pos in range(0, len(bs) - 2):
        ln = int.from_bytes(bs[pos:pos + 2], "big")
        if not (2 <= ln <= 160) or pos + 2 + ln > len(bs):
            continue
        raw = bs[pos + 2:pos + 2 + ln]
        try:
            text = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            continue
        if not looks_status_text(text):
            continue
        hits.append({"offset": pos, "length": ln, "value": text, "end": pos + 2 + ln})
    out: list[dict[str, Any]] = []
    seen_fiefs: set[str] = set()
    for hit in hits:
        value = str(hit["value"])
        if looks_fief_name(value) and value not in seen_fiefs:
            seen_fiefs.add(value)
            out.append({
                "name": "基地/封地",
                "detail": value,
                "status": "基地/封地",
                "remain": value,
                "kind": "fiefName",
                "source": "state8004-utf-evidence",
                "offset": hit["offset"],
            })
    by_end = {int(hit["end"]): hit for hit in hits}
    policies: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for effect in hits:
        effect_text = str(effect["value"])
        if not looks_policy_effect(effect_text):
            continue
        name = by_end.get(int(effect["offset"]))
        if not name or not looks_policy_name(str(name["value"])):
            continue
        key = (str(name["value"]), effect_text)
        if any((str(n["value"]), str(e["value"])) == key for n, e in policies):
            continue
        policies.append((name, effect))
    if policies:
        first = min(int(name["offset"]) for name, _ in policies)
        city = next((
            hit for hit in reversed(hits)
            if int(hit["offset"]) < first
            and 0 <= first - int(hit["end"]) <= 80
            and looks_short_place_name(str(hit["value"]))
        ), None)
        if city:
            out.append({
                "name": "城池",
                "detail": city["value"],
                "status": "城池",
                "remain": city["value"],
                "kind": "cityName",
                "source": "state8004-utf-evidence",
                "offset": city["offset"],
            })
    for name, effect in policies:
        name_offset = int(name["offset"])
        policy_index = int.from_bytes(bs[name_offset - 4:name_offset - 2], "big") if name_offset >= 4 else -1
        timer_raw = bs[name_offset - 2:name_offset].hex() if name_offset >= 2 else ""
        out.append({
            "name": name["value"],
            "detail": effect["value"],
            "effect": effect["value"],
            "remain": effect["value"],
            "kind": "policyBuff",
            "source": "state8004-policy-utf-pair",
            "nameOffset": name["offset"],
            "effectOffset": effect["offset"],
            "policyIndex": policy_index,
            "timerRawHex": timer_raw,
        })
    return out


def looks_status_text(text: str) -> bool:
    if not text or not any("\u4e00" <= ch <= "\u9fff" for ch in text):
        return False
    allowed = set("·-_ %/（）()，,。:：！!*")
    return all(("\u4e00" <= ch <= "\u9fff") or ch.isalnum() or ch in allowed for ch in text)


def looks_fief_name(text: str) -> bool:
    return (text.endswith("基地") or text.endswith("封地")) and len(text) <= 12 and "开启后" not in text


def looks_policy_effect(text: str) -> bool:
    return "伤兵治疗费用" in text or "守军攻防" in text or "产能提升" in text or "铜钱粮食产能" in text


def looks_policy_name(text: str) -> bool:
    return 2 <= len(text) <= 6 and "开启" not in text and "提升" not in text and "降低" not in text and "费用" not in text


def looks_short_place_name(text: str) -> bool:
    return 2 <= len(text) <= 6 and not looks_fief_name(text) and not looks_policy_effect(text)


def build_updates(result: dict[str, Any]) -> dict[str, str]:
    fresh = result["fresh"]
    state = result["state"]
    area = fresh["area"]
    role = fresh["role"]
    payload_hex = state["payloadHex"]
    generals = prereq.plausible_generals(prereq.recover_generals_from_8004(payload_hex))
    statuses = recover_status_from_8004(payload_hex)
    role_state_json = {
        "roleName": state["roleName"],
        "level": state["level"],
        "nation": role.get("country"),
        "title": role.get("title"),
        "roleId": state["roleId"],
        "serverName": area.get("areaName"),
        "syncedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    resource_state_json = {
        "copper": state["copper"],
        "food": state["food"],
        "prestige": state["prestige"],
        "copperPerHour": state["copperPerHour"],
        "foodPerHour": state["foodPerHour"],
        "populationCurrent": state["populationCurrent"],
        "populationCap": state["populationCap"],
        "resourcePointCurrent": state["resourcePointCurrent"],
        "resourcePointCap": state["resourcePointCap"],
    }
    updates = {
        "accountWithSuffix": str(fresh.get("accountWithSuffix") or ""),
        "userId": str(fresh.get("userId") or ""),
        "dm": str(fresh["dm"]),
        "gameHttp": str(fresh["gameHttp"]),
        "serverUrl": str(area["serverUrl"]).rstrip("/"),
        "roleId": str(state["roleId"]),
        "roleName": str(state["roleName"]),
        "level": str(state["level"]),
        "nation": str(role.get("country") or ""),
        "title": str(role.get("title") or ""),
        "copper": str(state["copper"]),
        "food": str(state["food"]),
        "prestige": str(state["prestige"]),
        "copperPerHour": str(state["copperPerHour"]),
        "foodPerHour": str(state["foodPerHour"]),
        "populationCurrent": str(state["populationCurrent"]),
        "populationCap": str(state["populationCap"]),
        "resourcePointCurrent": str(state["resourcePointCurrent"]),
        "resourcePointCap": str(state["resourcePointCap"]),
        "sourceOpcode": str(state["sourceOpcode"]),
        "state8004PayloadByteCount": str(state["payloadByteCount"]),
        "state8004ParsedHeadByteCount": str(state["parsedHeadByteCount"]),
        "state8004TailByteCount": str(state["tailByteCount"]),
        "state8004PayloadHex": str(state["payloadHex"]),
        "state8004TailHex": str(state["tailHex"]),
        "state8004TailUtf8Preview": str(state["tailUtf8Preview"]),
        "state8004GeneralRecordCount": str(len(generals)),
        "generalsJson": json.dumps(generals, ensure_ascii=False, separators=(",", ":")),
        "state8004StatusRecordCount": str(len(statuses)),
        "statusJson": json.dumps(statuses, ensure_ascii=False, separators=(",", ":")),
        "roleStateJson": json.dumps(role_state_json, ensure_ascii=False, separators=(",", ":")),
        "resourceStateJson": json.dumps(resource_state_json, ensure_ascii=False, separators=(",", ":")),
        "syncedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    inventory = result.get("inventory")
    if isinstance(inventory, dict):
        updates.update({
            "inventoryJson": json.dumps(inventory.get("items") or [], ensure_ascii=False, separators=(",", ":")),
            "inventoryCapacity": str(inventory.get("capacity") or ""),
            "inventoryItemCount": str(inventory.get("itemCount") or ""),
            "inventorySourceOpcode": str(inventory.get("sourceOpcode") or "0x1104/0x8104"),
            "inventoryPayloadByteCount": str(inventory.get("payloadByteCount") or ""),
            "inventoryParsedItemByteCount": str(inventory.get("parsedItemByteCount") or ""),
            "inventoryPayloadHex": str(inventory.get("payloadHex") or ""),
            "inventoryTailHex": str(inventory.get("tailHex") or ""),
        })
    elif result.get("inventoryError"):
        updates["inventoryError"] = str(result.get("inventoryError"))
    return updates


def apply_updates_to_root(root: dict[str, Any], updates: dict[str, str], result: dict[str, Any]) -> dict[str, Any]:
    account = first_account(root)
    fresh = result["fresh"]
    state = result["state"]
    area = fresh["area"]
    account["id"] = int(state["roleId"])
    account["displayName"] = state["roleName"]
    account["monarchName"] = state["roleName"]
    account["serverName"] = area["areaName"]
    account["serverId"] = area["serverKey"]
    account["loginState"] = "REAL_SYNCED"
    session = account.setdefault("session", {})
    session["accountId"] = int(state["roleId"])
    session["sourceMode"] = 1
    extra = session.setdefault("channelExtra", {})
    if not isinstance(extra, dict):
        raise ValueError("channelExtra is not an object")
    extra.update(updates)
    return account


def get_password(arg_password: str | None) -> str:
    if arg_password:
        return arg_password
    env_password = os.environ.get("DWPM_TEST_PASSWORD")
    if env_password:
        return env_password
    return getpass.getpass("Password (not echoed): ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", default=PACKAGE)
    ap.add_argument("--username", default=None)
    ap.add_argument("--password", default=None, help="Prefer DWPM_TEST_PASSWORD or interactive prompt to avoid shell history")
    ap.add_argument("--server", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-stop-first", action="store_true")
    ap.add_argument("--out", default="reports/device_session_refresh_current.json")
    ns = ap.parse_args()

    if ns.force_stop_first:
        subprocess.run(["adb", "shell", "am", "force-stop", ns.package], check=False)

    raw = device_extra.read_prefs(package=ns.package)
    prefix, root, suffix = parse_accounts_xml(raw)
    account = first_account(root)
    username = ns.username or str(account.get("username") or "")
    server = ns.server or str(account.get("serverName") or "周年服351区")
    password = get_password(ns.password)
    result = fresh_login_state(username, password, server)
    updates = build_updates(result)
    account = apply_updates_to_root(root, updates, result)
    rendered = device_extra.render_accounts_xml(prefix, root, suffix)
    if not ns.dry_run:
        device_extra.write_prefs(rendered, package=ns.package)

    report = {
        "checkedAtMillis": int(time.time() * 1000),
        "package": ns.package,
        "dryRun": ns.dry_run,
        "accountId": account.get("id"),
        "username": username,
        "roleName": result["state"]["roleName"],
        "serverName": account.get("serverName"),
        "http": result["http"],
        "responseBytes": result["responseBytes"],
        "opcodes": result["opcodes"],
        "dmPresent": bool(updates.get("dm")),
        "state8004PayloadHexPresent": bool(updates.get("state8004PayloadHex")),
        "generalCandidateCount": int(updates.get("state8004GeneralRecordCount") or 0),
        "inventoryItemCount": int(updates.get("inventoryItemCount") or 0),
        "inventoryCapacity": int(updates.get("inventoryCapacity") or 0),
        "inventoryError": updates.get("inventoryError", ""),
        "changedKeys": sorted(updates.keys()),
    }
    Path(ns.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
