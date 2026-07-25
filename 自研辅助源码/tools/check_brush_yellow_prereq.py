#!/usr/bin/env python3
"""Build a brush-yellow live regression prerequisite report from saved self-app evidence.

This script is deliberately non-mutating: it reads the installed app's shared_prefs via
`adb shell run-as`, optionally consumes the latest live 0x1016 freshness report, extracts
0x8004 general candidates, and reports whether the real brush-yellow action can be run.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

PACKAGE = "com.example.dwpmclone"
JIANG_BODY_LEN = 114
# Lo/a.S5.Pm is the zero-based row index in scriptSoldier.sc, not the soldier id.
SOLDIER_NAMES = {
    0: "民兵", 1: "弩兵", 2: "弓兵", 3: "轻骑兵",
    4: "弩车", 5: "冲城车", 6: "轻步兵", 7: "近卫兵",
    8: "重步兵", 9: "弩骑兵", 10: "重骑兵", 11: "铁骑兵",
    12: "投石车", 13: "重弩车", 14: "强弩兵", 15: "骁骑兵",
}
PROFESSION_NAMES = {0: "步将", 1: "弓将", 2: "骑将", 4: "勇士"}


def adb_run_as_cat(path: str, package: str = PACKAGE) -> str:
    return subprocess.check_output(["adb", "shell", "run-as", package, "cat", path], text=True, errors="ignore")


def load_saved_account(package: str = PACKAGE) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    raw = adb_run_as_cat("shared_prefs/dwpm_clone_accounts.xml", package=package)
    return parse_accounts_xml(raw)


def parse_accounts_xml(raw_xml: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    m = re.search(r'<string name="accounts_json">(.*?)</string>', raw_xml, re.S)
    if not m:
        raise ValueError("accounts_json not found")
    root = json.loads(html.unescape(m.group(1)))
    accounts = root.get("accounts") or []
    if not accounts:
        raise ValueError("no accounts")
    account = accounts[0]
    session = account.get("session") or {}
    extra = session.get("channelExtra") or {}
    return account, session, {str(k): str(v) for k, v in extra.items()}


def recover_generals_from_8004(hexstr: str) -> list[dict[str, Any]]:
    if not hexstr:
        return []
    try:
        bs = bytes.fromhex(hexstr)
    except ValueError:
        return []
    confirmed = recover_confirmed_jiangling_from_8004(bs)
    if confirmed:
        return confirmed
    res = []
    for pos in range(8, len(bs) - 2):
        ln = int.from_bytes(bs[pos:pos + 2], "big")
        if not (2 <= ln <= 24) or pos + 2 + ln > len(bs):
            continue
        name = bs[pos + 2:pos + 2 + ln].decode("utf-8", errors="ignore").strip()
        if not name or len(name) > 8:
            continue
        if sum("\u4e00" <= ch <= "\u9fff" for ch in name) < 1:
            continue
        if not all(("\u4e00" <= ch <= "\u9fff") or ch.isalnum() or ch == "·" for ch in name):
            continue
        gid = int.from_bytes(bs[pos - 8:pos], "big")
        if gid <= 0:
            continue
        status = bs[pos + 2 + ln] if pos + 2 + ln < len(bs) else None
        tili = bs[pos + 2 + ln + 1] if pos + 2 + ln + 1 < len(bs) else None
        res.append({
            "id": gid,
            "idHex": f"{gid:016x}",
            "name": name,
            "status": status,
            "tili": tili,
            "offset": pos,
            "source": "state8004-binary-name-candidate",
        })
    seen = set()
    out = []
    for g in res:
        if g["id"] in seen:
            continue
        seen.add(g["id"])
        out.append(g)
    return out


def recover_confirmed_jiangling_from_8004(bs: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for pos in range(8, len(bs) - 2):
        ln = int.from_bytes(bs[pos:pos + 2], "big")
        body_pos = pos + 2 + ln
        if not (2 <= ln <= 24) or body_pos + JIANG_BODY_LEN > len(bs):
            continue
        name = bs[pos + 2:body_pos].decode("utf-8", errors="ignore").strip()
        if not name or len(name) > 8:
            continue
        if sum("\u4e00" <= ch <= "\u9fff" for ch in name) < 1:
            continue
        if not all(("\u4e00" <= ch <= "\u9fff") or ch.isalnum() or ch == "·" for ch in name):
            continue
        gid = int.from_bytes(bs[pos - 8:pos], "big")
        if gid <= 0:
            continue
        body = bs[body_pos:body_pos + JIANG_BODY_LEN]
        if body[0x3a:0x42] != bs[pos - 8:pos] or body[0x70:0x72] != b"\xff\xff":
            continue
        profession = body[0x03]
        growth = int.from_bytes(body[0x06:0x08], "big")
        level = body[0x08]
        tili = int.from_bytes(body[0x1b:0x1d], "big")
        tili_limit = int.from_bytes(body[0x1d:0x1f], "big")
        troop_limit = int.from_bytes(body[0x23:0x27], "big")
        loyalty = body[0x27]
        loyalty_limit = body[0x28]
        status = body[0x58]
        if not (1 <= growth <= 200 and 1 <= level <= 200 and 0 <= profession <= 8):
            continue
        if not (0 <= tili <= 300 and 1 <= tili_limit <= 300 and 0 <= troop_limit <= 50000):
            continue
        if not (0 <= loyalty <= 200 and 1 <= loyalty_limit <= 200 and 0 <= status <= 16):
            continue
        records.append({
            "id": gid,
            "idHex": f"{gid:016x}",
            "name": name,
            "source": "state8004-binary-jiangling",
            "layout": "i64_id_u16_name_114_body_b6_common_v20260708b",
            "nameUtf8Offset": pos,
            "bodyOffset": body_pos,
            "professionCode": profession,
            "kindCode": profession,
            "categoryCode": profession,
            "kind": PROFESSION_NAMES.get(profession, f"职业{profession}"),
            "category": PROFESSION_NAMES.get(profession, f"职业{profession}"),
            "level": level,
            "rank": level,
            "growth": growth,
            "progression": growth,
            "jingyan": int.from_bytes(body[0x09:0x0d], "big"),
            "jingyanLimit": int.from_bytes(body[0x0d:0x11], "big"),
            "wuli": int.from_bytes(body[0x11:0x13], "big"),
            "zhili": int.from_bytes(body[0x13:0x15], "big"),
            "tongshuai": int.from_bytes(body[0x15:0x17], "big"),
            "gongji": int.from_bytes(body[0x17:0x19], "big"),
            "fangyu": int.from_bytes(body[0x19:0x1b], "big"),
            "tili": tili,
            "tiliLimit": tili_limit,
            "zhongChengdu": loyalty,
            "loyalty": loyalty,
            "loyaltyLimit": loyalty_limit,
            "daiBingLimit": troop_limit,
            "troopLimit": troop_limit,
            "maxTroopCount": troop_limit,
            "status": status,
            "statusText": "空闲" if status == 0 else f"状态{status}",
            "bodyHeadHex": body[:46].hex(),
        })
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for item in records:
        gid = int(item["id"])
        if gid in seen:
            continue
        seen.add(gid)
        out.append(item)
    if not out:
        return []
    s5 = recover_s5_assignments(bs, {int(item["id"]) for item in out}, max(int(item["bodyOffset"]) + JIANG_BODY_LEN for item in out))
    for item in out:
        assignment = s5.get(int(item["id"]))
        if not assignment:
            continue
        soldier_type, count, offset, s5_count = assignment
        item.update({
            "troopCount": count,
            "soldierCount": count,
            "currentTroopCount": count,
            "currentSoldierCount": count,
            "bingli": count,
            "troopTypeCode": soldier_type,
            "soldierTypeCode": soldier_type,
            "troopType": SOLDIER_NAMES.get(soldier_type, f"兵种code={soldier_type}"),
            "soldierType": SOLDIER_NAMES.get(soldier_type, f"兵种code={soldier_type}"),
            "troopTypeName": SOLDIER_NAMES.get(soldier_type, ""),
            "soldierTypeName": SOLDIER_NAMES.get(soldier_type, ""),
            "troopTypeSource": "Lo/a.S5.Pm",
            "troopCountSource": "Lo/a.S5.Qm",
            "s5Offset": offset,
            "s5Count": s5_count,
        })
    return out


def recover_s5_assignments(bs: bytes, ids: set[int], min_offset: int) -> dict[int, tuple[int, int, int, int]]:
    candidates: list[tuple[int, int, list[tuple[int, int, int, int]]]] = []
    for pos in range(min_offset, len(bs)):
        count = bs[pos]
        if not (1 <= count <= 30):
            continue
        end = pos + 1 + count * 21
        if end > len(bs):
            continue
        entries: list[tuple[int, int, int, int]] = []
        plausible = True
        for idx in range(count):
            off = pos + 1 + idx * 21
            nm = int.from_bytes(bs[off:off + 8], "big")
            om = int.from_bytes(bs[off + 8:off + 16], "big")
            pm = bs[off + 16]
            qm = int.from_bytes(bs[off + 17:off + 21], "big", signed=True)
            if not (0 <= pm <= 32 and 0 <= qm <= 500000):
                plausible = False
                break
            if nm == om and nm in ids:
                entries.append((nm, pm, qm, pos))
        if plausible and entries:
            candidates.append((len(entries), -pos, entries))
    if not candidates:
        return {}
    _, _, best_entries = max(candidates, key=lambda item: (item[0], item[1]))
    return {gid: (pm, qm, offset, len(best_entries)) for gid, pm, qm, offset in best_entries}


def plausible_generals(generals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bad_names = ("基地", "封地", "洛阳", "太祥")
    return [
        g for g in generals
        if 1_000_000 <= int(g.get("id", 0)) <= 200_000_000
        and not any(bad in str(g.get("name", "")) for bad in bad_names)
    ]


def parse_formations(extra: dict[str, str]) -> list[dict[str, Any]]:
    raw = extra.get("formationsJson")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, dict):
            out.append(item)
    return out


def fallback_formations_from_generals(extra: dict[str, str], generals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mirror the app-side recovered-state8004 fallback formation gate.

    The Kotlin sender can, only when explicitly enabled, treat an idle recovered
    0x8004 general as a single-general brush-yellow formation.  The preflight
    report must model that same behavior; otherwise a runnable live session is
    reported as blocked just because it does not yet have persisted
    ``formationsJson``.
    """
    if not bool_extra(extra, "allowRecoveredGeneralFallbackFormation"):
        return []
    out = []
    for g in generals:
        gid = int(g.get("id", 0) or 0)
        if gid <= 0:
            continue
        status = g.get("status")
        tili = g.get("tili")
        if status not in (None, 0):
            continue
        if (
            tili is not None and int(tili) <= 0
            and g.get("source") != "state8004-binary-name-candidate"
        ):
            continue
        out.append({
            "id": gid,
            "name": f"候选刷黄编队-{g.get('name') or gid}",
            "generalIds": [gid],
            "status": "IDLE",
            "troopCount": None,
            "raw": {
                "source": "recovered-state8004-general-fallback",
                "generalId": str(gid),
                "generalName": str(g.get("name") or ""),
                "requiresExplicitFlag": "allowRecoveredGeneralFallbackFormation",
            },
        })
    return out


def bool_extra(extra: dict[str, str], key: str) -> bool:
    return str(extra.get(key, "")).strip().lower() in {"1", "true", "yes", "y", "on"}


def load_live_report(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def build_report(account: dict[str, Any], session: dict[str, Any], extra: dict[str, str], live_report: dict[str, Any] | None = None) -> dict[str, Any]:
    all_generals = recover_generals_from_8004(extra.get("state8004PayloadHex", ""))
    candidates = plausible_generals(all_generals)
    configured_formations = parse_formations(extra)
    fallback_formations = fallback_formations_from_generals(extra, candidates)
    formations = configured_formations or fallback_formations
    network_allowed = bool_extra(extra, "realActionNetworkAllowed")
    send_ready = bool_extra(extra, "realActionSendReady")
    scope_ok = extra.get("realActionScope", "").lower() == "brush-yellow" or bool_extra(extra, "realActionBrushYellowOnly")
    live_fresh = bool(live_report and live_report.get("sessionFresh"))
    blockers = []
    if not live_fresh:
        blockers.append("session_not_fresh_live_1016")
    if not candidates:
        blockers.append("no_general_candidates_from_8004")
    if not formations:
        blockers.append("no_formations_json_or_selected_formation")
    if not network_allowed:
        blockers.append("realActionNetworkAllowed_not_true")
    if not send_ready:
        blockers.append("realActionSendReady_not_true")
    if not scope_ok:
        blockers.append("realActionScope_brush_yellow_not_confirmed")
    ready = not blockers
    non_session_blockers = [b for b in blockers if b != "session_not_fresh_live_1016"]
    config_ready_except_session = (not live_fresh) and (not non_session_blockers)
    return {
        "checkedAtMillis": int(time.time() * 1000),
        "accountId": account.get("id"),
        "username": account.get("username"),
        "roleName": extra.get("roleName") or account.get("displayName"),
        "serverName": account.get("serverName"),
        "sourceMode": session.get("sourceMode"),
        "liveSessionFresh": live_fresh,
        "liveSessionReason": (live_report or {}).get("reason"),
        "state8004PayloadHexPresent": bool(extra.get("state8004PayloadHex")),
        "generalCandidateCount": len(candidates),
        "generalCandidates": candidates[:30],
        "formationCount": len(formations),
        "configuredFormationCount": len(configured_formations),
        "fallbackFormationCount": len(fallback_formations),
        "fallbackFormationEnabled": bool_extra(extra, "allowRecoveredGeneralFallbackFormation"),
        "formationSource": (
            "formationsJson" if configured_formations
            else "recovered-state8004-general-fallback" if fallback_formations
            else "none"
        ),
        "formations": formations[:20],
        "gates": {
            "realActionNetworkAllowed": network_allowed,
            "realActionSendReady": send_ready,
            "realActionScopeBrushYellow": scope_ok,
            "allowRecoveredGeneralFallbackFormation": bool_extra(extra, "allowRecoveredGeneralFallbackFormation"),
        },
        "readinessStage": readiness_stage(live_fresh, blockers),
        "configReadyExceptSession": config_ready_except_session,
        "nonSessionBlockers": non_session_blockers,
        "readyForRealBrushYellow": ready,
        "blockers": blockers,
        "recommendation": recommendation(blockers),
    }


def readiness_stage(live_fresh: bool, blockers: list[str]) -> str:
    if not blockers:
        return "READY_FOR_REAL_BRUSH_YELLOW"
    non_session = [b for b in blockers if b != "session_not_fresh_live_1016"]
    if not live_fresh and not non_session:
        return "WAITING_FOR_FRESH_SESSION_ONLY"
    if any(b.startswith("realAction") for b in blockers):
        return "WAITING_FOR_ACTION_GATE"
    if "no_formations_json_or_selected_formation" in blockers:
        return "WAITING_FOR_FORMATION"
    if "no_general_candidates_from_8004" in blockers:
        return "WAITING_FOR_STATE8004_GENERALS"
    return "BLOCKED_BY_PREREQUISITES"


def recommendation(blockers: list[str]) -> str:
    if not blockers:
        return "可进入受控刷黄真机回归。"
    non_session = [b for b in blockers if b != "session_not_fresh_live_1016"]
    if "session_not_fresh_live_1016" in blockers and not non_session:
        return "配置/gate/编队已就绪，仅需刷新真实登录 session：可解锁手机走 UI 登录同步，或运行 tools/refresh_device_session_from_login.py 隐藏输入密码刷新。"
    if "session_not_fresh_live_1016" in blockers:
        return "先刷新真实登录 session；同时继续处理其它 blockers。可解锁手机走 UI 登录同步，或运行 tools/refresh_device_session_from_login.py。"
    if "no_formations_json_or_selected_formation" in blockers:
        return "需要在 UI/配置中选择刷黄出征编队，或显式开启 allowRecoveredGeneralFallbackFormation=true 作为 0x8004 将领候选单将 fallback。"
    if any(b.startswith("realAction") for b in blockers):
        return "需要确认 realActionNetworkAllowed=true、realActionSendReady=true、realActionScope=brush-yellow。"
    return "按 blockers 逐项补齐。"


def to_markdown(report: dict[str, Any]) -> str:
    return "\n".join([
        "# Brush-yellow live prerequisite report",
        "",
        f"- checkedAtMillis: {report['checkedAtMillis']}",
        f"- accountId: {report['accountId']}",
        f"- roleName: {report['roleName']}",
        f"- serverName: {report['serverName']}",
        f"- liveSessionFresh: {str(report['liveSessionFresh']).lower()}",
        f"- liveSessionReason: {report['liveSessionReason']}",
        f"- generalCandidateCount: {report['generalCandidateCount']}",
        f"- formationCount: {report['formationCount']}",
        f"- configuredFormationCount: {report['configuredFormationCount']}",
        f"- fallbackFormationCount: {report['fallbackFormationCount']}",
        f"- formationSource: {report['formationSource']}",
        f"- readinessStage: {report['readinessStage']}",
        f"- configReadyExceptSession: {str(report['configReadyExceptSession']).lower()}",
        f"- readyForRealBrushYellow: {str(report['readyForRealBrushYellow']).lower()}",
        f"- blockers: {', '.join(report['blockers']) if report['blockers'] else 'none'}",
        f"- recommendation: {report['recommendation']}",
        "",
        "## Gates",
        "",
        "```json",
        json.dumps(report["gates"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## General candidates (first 30)",
        "",
        "```json",
        json.dumps(report["generalCandidates"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Formations",
        "",
        "```json",
        json.dumps(report["formations"], ensure_ascii=False, indent=2),
        "```",
    ])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", default=PACKAGE)
    ap.add_argument("--live-report", default="reports/live_1016_session_freshness_current.json")
    ap.add_argument("--out", default="reports/brush_yellow_live_prereq_current.json")
    ap.add_argument("--markdown-out", default="reports/brush_yellow_live_prereq_current.md")
    ns = ap.parse_args()
    account, session, extra = load_saved_account(package=ns.package)
    report = build_report(account, session, extra, load_live_report(Path(ns.live_report)))
    Path(ns.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")
    print(json.dumps({
        "readyForRealBrushYellow": report["readyForRealBrushYellow"],
        "blockers": report["blockers"],
        "generalCandidateCount": report["generalCandidateCount"],
        "formationCount": report["formationCount"],
        "out": ns.out,
    }, ensure_ascii=False, indent=2))
    return 0 if report["readyForRealBrushYellow"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
