"""Shared local reference projections used by both assistant hosts."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Mapping, Optional


GUIDE_ARTICLE_SPECS = (
    ("V6fzgl", "V6以上玩家前期发展攻略"),
    ("dwsgjingyan", "帝王三国升级经验"),
    ("pm80jigl", "15小时冲击80级攻略"),
    ("pmkssjgl", "快速升级攻略"),
    ("qzp", "强装/开箱经验"),
    ("rmb80jigl", "开区快速80级心得"),
    ("sfbgl", "副本刷将魂道具装备攻略"),
    ("shuashihuang", "刷黄攻略"),
    ("szsjgl", "神州升级攻略"),
    ("wuditcp", "无敌推城篇"),
)

GUIDE_OPEN_SERVER_VERSIONS = (
    {"index": 0, "label": "九游版", "summary": "30区=2012/11/29，每区间隔5天"},
    {"index": 1, "label": "腾讯版", "summary": "218区=2016/11/17；290区=2018/8/31；297区=2018/11/9"},
    {"index": 2, "label": "百度版", "summary": "30区=2012/11/29，每区间隔5天"},
    {"index": 3, "label": "热血帝王", "summary": "30区=2013/9/20，每区间隔7天"},
    {"index": 4, "label": "三国联盟", "summary": "102区=2016/10/12；112区=2017/4/26；113区=2017/5/17"},
    {"index": 5, "label": "新三国争霸", "summary": "30区=2012/7/13，每区间隔7天"},
    {"index": 6, "label": "繁体版", "summary": "30区=2015/3/20，每区间隔14天"},
)

_PLATFORM_PROFILES = {
    "sglm": {
        "name": "热血三国联盟",
        "aliases": ("热血三国联盟", "三国联盟", "sglm"),
    },
    "downjoy": {
        "name": "当乐帝王三国",
        "aliases": ("当乐帝王三国", "当乐", "dangley", "downjoy"),
    },
}


def project_area_catalog(source: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize host storage facts into the one public area-catalog shape."""

    platform_key = normalize_platform_key(
        source.get("platformKey") or source.get("platform")
    )
    raw_areas = source.get("areas") or []
    if not isinstance(raw_areas, list):
        raise ValueError("区服目录 areas 必须是数组")
    by_identity: Dict[tuple[str, str, str], Dict[str, str]] = {}
    for index, raw in enumerate(raw_areas):
        if not isinstance(raw, Mapping):
            raise ValueError(f"区服目录第 {index + 1} 项必须是对象")
        area_name = str(raw.get("areaName") or "").strip()
        if not area_name:
            continue
        item = {
            "target": str(raw.get("target") or "").strip(),
            "areaId": str(raw.get("areaId") or "").strip(),
            "areaName": area_name,
            "serverUrl": str(raw.get("serverUrl") or "").strip(),
            "serverKey": str(raw.get("serverKey") or "").strip(),
        }
        identity = (item["serverKey"], item["areaId"], item["areaName"])
        existing = by_identity.get(identity)
        if existing is None:
            by_identity[identity] = item
            continue
        targets = [value for value in existing["target"].split(",") if value]
        if item["target"] and item["target"] not in targets:
            existing["target"] = ",".join([*targets, item["target"]])
    areas = sorted(
        by_identity.values(),
        key=lambda item: (item["serverKey"], item["areaId"], item["areaName"]),
    )
    updated_at = _optional_positive_int(source.get("updatedAt"))
    return {
        "ok": True,
        "areas": areas,
        "updatedAt": updated_at,
        "count": len(areas),
        "platform": _PLATFORM_PROFILES[platform_key]["name"],
        "platformKey": platform_key,
    }


def guide_reference_payload(
    request: Mapping[str, Any],
    *,
    now_millis: Optional[int] = None,
) -> Dict[str, Any]:
    """Project one guide request; hosts supply bytes/text, never business rules."""

    resource = str(request.get("resource") or "").strip()
    if resource == "famous-generals":
        return _famous_generals_payload(request.get("sourceText"))
    if resource == "articles":
        items = [
            {"id": article_id, "title": title}
            for article_id, title in GUIDE_ARTICLE_SPECS
        ]
        return {"ok": True, "total": len(items), "items": items}
    if resource == "article":
        article_id = str(request.get("id") or "").strip()
        title = _guide_article_title(article_id)
        if title is None:
            return {"ok": False, "error": "未找到攻略内容"}
        body = request.get("sourceText")
        if not isinstance(body, str):
            raise ValueError("攻略原始文本缺失")
        return {
            "ok": True,
            "article": {"id": article_id, "title": title, "body": _strip_bom(body)},
        }
    if resource == "open-server-options":
        today = _requested_date(request.get("today")) or _beijing_date(now_millis)
        versions = []
        for option in GUIDE_OPEN_SERVER_VERSIONS:
            version_index = int(option["index"])
            rule = _latest_open_server_rule(version_index)
            base_date = date(rule["year"], rule["month"], rule["day"])
            diff_days = (today - base_date).days
            next_step = 0 if diff_days < 0 else diff_days // rule["intervalDays"] + 1
            upcoming_server = max(1, rule["baseServer"] + next_step)
            upcoming_date = base_date + timedelta(days=next_step * rule["intervalDays"])
            versions.append({
                **option,
                "upcomingServer": upcoming_server,
                "upcomingDate": _date_text(upcoming_date),
            })
        return {"ok": True, "versions": versions}
    if resource == "open-server-calculation":
        server = _required_positive_int(request.get("server"), "区服编号")
        version_index = _int(request.get("versionIndex"), 0)
        version = next(
            (
                option
                for option in GUIDE_OPEN_SERVER_VERSIONS
                if int(option["index"]) == version_index
            ),
            GUIDE_OPEN_SERVER_VERSIONS[0],
        )
        rule = _open_server_rule(int(version["index"]), server)
        days_offset = (server - rule["baseServer"]) * rule["intervalDays"]
        opened = date(rule["year"], rule["month"], rule["day"]) + timedelta(
            days=days_offset
        )
        return {
            "ok": True,
            "server": server,
            "versionIndex": int(version["index"]),
            "versionLabel": str(version["label"]),
            "dateText": _date_text(opened),
            "daysOffset": days_offset,
            "rule": rule,
        }
    return {"ok": False, "error": "未知的攻略资料类型"}


def normalize_platform_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "sglm"
    lowered = text.lower()
    for key, profile in _PLATFORM_PROFILES.items():
        aliases: Iterable[str] = profile["aliases"]
        if lowered == key or any(lowered == alias.lower() for alias in aliases):
            return key
    raise ValueError(
        f"不支持的游戏平台：{text}；目前仅支持热血三国联盟、当乐帝王三国"
    )


def platform_display_name(value: Any) -> str:
    return str(_PLATFORM_PROFILES[normalize_platform_key(value)]["name"])


def _famous_generals_payload(source_text: Any) -> Dict[str, Any]:
    if not isinstance(source_text, str):
        raise ValueError("名将原始文本缺失")
    items = []
    rows = csv.reader(io.StringIO(_strip_bom(source_text)))
    next(rows, None)
    for row in rows:
        if len(row) < 4:
            continue
        name = str(row[0]).strip()
        if not name:
            continue
        breakthrough = str(row[1]).strip()
        items.append({
            "name": name,
            "breakthrough": int(breakthrough) if breakthrough.isdigit() else None,
            "attribute": str(row[2]).strip() or None,
            "nation": str(row[3]).strip() or None,
        })
    return {"ok": True, "total": len(items), "items": items}


def _guide_article_title(article_id: str) -> Optional[str]:
    return next(
        (title for candidate, title in GUIDE_ARTICLE_SPECS if candidate == article_id),
        None,
    )


def _open_server_rule(version_index: int, server: int) -> Dict[str, Any]:
    if version_index == 1:
        if server < 260:
            values = (218, 10, 2016, 11, 17, "原 APK pswitch_7：server < 260")
        elif server <= 290:
            values = (290, 7, 2018, 8, 31, "原 APK pswitch_7：260..290 分段")
        else:
            values = (297, 10, 2018, 11, 9, "原 APK pswitch_7：server > 290")
    elif version_index == 3:
        values = (30, 7, 2013, 9, 20, "原 APK pswitch_6")
    elif version_index == 4:
        if server < 111:
            values = (102, 21, 2016, 10, 12, "原 APK pswitch_2：server < 111")
        elif server <= 113:
            values = (112, 21, 2017, 4, 26, "原 APK pswitch_2：111..113 分段")
        else:
            values = (113, 14, 2017, 5, 17, "原 APK pswitch_2：server > 113")
    elif version_index == 5:
        values = (30, 7, 2012, 7, 13, "原 APK pswitch_1")
    elif version_index == 6:
        values = (30, 14, 2015, 3, 20, "原 APK pswitch_0")
    else:
        values = (30, 5, 2012, 11, 29, "原 APK pswitch_8 / 默认初始规则")
    base_server, interval_days, year, month, day, note = values
    return {
        "baseServer": base_server,
        "intervalDays": interval_days,
        "year": year,
        "month": month,
        "day": day,
        "note": note,
    }


def _latest_open_server_rule(version_index: int) -> Dict[str, Any]:
    if version_index == 1:
        return _open_server_rule(version_index, 291)
    if version_index == 4:
        return _open_server_rule(version_index, 114)
    return _open_server_rule(version_index, 2_147_483_647)


def _beijing_date(now_millis: Optional[int]) -> date:
    if now_millis is None:
        return datetime.now(timezone(timedelta(hours=8))).date()
    return datetime.fromtimestamp(
        int(now_millis) / 1000,
        timezone(timedelta(hours=8)),
    ).date()


def _requested_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError("today 必须是 YYYY-MM-DD") from error


def _date_text(value: date) -> str:
    return f"{value.year:04d}/{value.month}/{value.day}"


def _strip_bom(value: str) -> str:
    return str(value).removeprefix("\ufeff")


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _required_positive_int(value: Any, label: str) -> int:
    parsed = _int(value, 0)
    if parsed <= 0:
        raise ValueError(f"{label}必须大于 0")
    return parsed


def _optional_positive_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    parsed = _int(value, 0)
    return parsed if parsed > 0 else None
