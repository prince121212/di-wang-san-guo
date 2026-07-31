"""Pure login response parsers shared by desktop and Android hosts."""

from __future__ import annotations

import json
import re
import struct
from typing import Any


def parse_8003_login(payload: bytes) -> dict[str, Any]:
    position = 0

    def need(size: int, field: str) -> None:
        if position + size > len(payload):
            raise ValueError(
                f"0x8003 字段 {field} 不完整："
                f"pos={position}, need={size}, size={len(payload)}"
            )

    def i8(field: str) -> int:
        nonlocal position
        need(1, field)
        value = struct.unpack(">b", payload[position:position + 1])[0]
        position += 1
        return value

    def i16(field: str) -> int:
        nonlocal position
        need(2, field)
        value = struct.unpack(">h", payload[position:position + 2])[0]
        position += 2
        return value

    def i32(field: str) -> int:
        nonlocal position
        need(4, field)
        value = struct.unpack(">i", payload[position:position + 4])[0]
        position += 4
        return value

    def i64(field: str) -> int:
        nonlocal position
        need(8, field)
        value = struct.unpack(">q", payload[position:position + 8])[0]
        position += 8
        return value

    def text(field: str) -> str:
        nonlocal position
        need(2, f"{field}.length")
        length = int.from_bytes(payload[position:position + 2], "big")
        position += 2
        need(length, field)
        raw = payload[position:position + length]
        position += length
        return raw.decode("utf-8", errors="replace")

    status = i8("status")
    message = text("message")
    dm = i64("dm")
    selected = 0
    roles: list[dict[str, Any]] = []
    if status == 0:
        login_time = i64("loginTime")
        selected = i32("selectedRole")
        count = i32("roleCount")
        if count < 0 or count > 1000:
            raise ValueError(f"0x8003 角色数量异常：{count}")
        for index in range(count):
            role_id = i64(f"roles[{index}].roleId")
            server_code = i16(f"roles[{index}].serverCode")
            role_name = text(f"roles[{index}].roleName")
            level = i8(f"roles[{index}].level")
            country = text(f"roles[{index}].country")
            title = text(f"roles[{index}].title")
            roles.append(
                {
                    "roleId": role_id,
                    "serverCode": server_code,
                    "roleName": role_name,
                    "level": level,
                    "country": country,
                    "title": title,
                }
            )
    else:
        login_time = None
    return {
        "status": status,
        "message": message,
        "dm": dm,
        "loginTime": login_time,
        "selected": selected,
        "roles": roles,
        "parsedBytes": position,
        "trailingBytes": len(payload) - position,
    }


def parse_passport_area_list(
    text: str,
) -> tuple[str, str, list[dict[str, str]]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or "`" not in lines[0]:
        raise RuntimeError("账号登录失败或 passport 返回异常")
    head = lines[0].split("`")
    if len(head) < 2:
        raise RuntimeError("passport 区服列表响应缺少 session/userId")
    session, user_id = head[0], head[1]
    areas: list[dict[str, str]] = []
    for line in lines[1:]:
        parts = line.split("`")
        if len(parts) >= 12:
            areas.append(
                {
                    "target": parts[0],
                    "areaId": parts[1],
                    "areaName": parts[2],
                    "serverUrl": parts[3],
                    "serverKey": parts[11],
                }
            )
    if not areas:
        raise RuntimeError("passport 未返回任何区服")
    return session, user_id, areas


def find_login_area(
    areas: list[dict[str, str]],
    server_query: str,
) -> dict[str, str] | None:
    query = str(server_query or "").strip()
    if not query:
        return None
    exact = next(
        (
            area
            for area in areas
            if query
            in {
                area.get("areaName"),
                area.get("serverKey"),
                area.get("areaId"),
            }
        ),
        None,
    )
    if exact:
        return exact
    query_lower = query.lower()
    zone_match = (
        re.search(r"qzone[_-]?(\d+)", query_lower)
        or re.search(r"(\d+)\s*区", query_lower)
    )
    if zone_match:
        zone_number = zone_match.group(1)
        expected_key = f"qzone_{zone_number}"
        by_key = next(
            (
                area
                for area in areas
                if str(area.get("serverKey") or "").strip().lower()
                == expected_key
            ),
            None,
        )
        if by_key:
            return by_key
        by_zone = next(
            (
                area
                for area in areas
                if (
                    (
                        match := re.search(
                            r"(\d+)\s*区",
                            str(area.get("areaName") or ""),
                        )
                    )
                    and match.group(1) == zone_number
                )
            ),
            None,
        )
        if by_zone:
            return by_zone
    return next(
        (
            area
            for area in areas
            if (
                query_lower in str(area.get("areaName") or "").lower()
                or str(area.get("areaName") or "").lower() in query_lower
            )
        ),
        None,
    )


def area_catalog_signature(areas: list[dict[str, Any]]) -> str:
    normalized = sorted(
        [
            {
                "target": str(area.get("target") or ""),
                "areaId": str(area.get("areaId") or ""),
                "areaName": str(area.get("areaName") or ""),
                "serverUrl": str(area.get("serverUrl") or ""),
                "serverKey": str(area.get("serverKey") or ""),
            }
            for area in areas
        ],
        key=lambda area: (
            area["serverKey"],
            area["areaId"],
            area["areaName"],
        ),
    )
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
