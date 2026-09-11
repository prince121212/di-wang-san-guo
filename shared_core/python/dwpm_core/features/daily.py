"""Daily-task request builders and response parsers."""

from __future__ import annotations

import re
import struct
import time
from typing import Any

from ..contracts import load_behavior_contract
from ..protocol.wire import encode_utf, extract_utf_strings, printable, read_utf


DAILY_CONTRACT = load_behavior_contract()["daily"]
DAILY_ACTIONS_CONTRACT = DAILY_CONTRACT["actions"]
DAILY_SALARY_CONTRACT = DAILY_ACTIONS_CONTRACT["salary"]
DAILY_NATIONAL_CONTRACT = DAILY_ACTIONS_CONTRACT["nationalCollect"]
DAILY_GENERAL_VISIT_CONTRACT = DAILY_ACTIONS_CONTRACT["generalVisit"]
DAILY_DONATE_CONTRACT = DAILY_ACTIONS_CONTRACT["donate"]
DAILY_SIGN_IN_CONTRACT = DAILY_CONTRACT["signIn"]
DAILY_DIAMOND_BOX_CONTRACT = DAILY_SIGN_IN_CONTRACT["diamondBox"]
DAILY_SIGN_IN_ACTIVITY_OPCODE = int(
    str(DAILY_SIGN_IN_CONTRACT["activityResponseOpcode"]), 0
)
DAILY_SIGN_IN_LEGACY_OPCODE = int(
    str(DAILY_SIGN_IN_CONTRACT["legacyResponseOpcode"]), 0
)
DAILY_SIGN_IN_DUPLICATE_LOG = str(
    DAILY_SIGN_IN_CONTRACT["duplicateMessage"]
)
ARENA_COINS_DUPLICATE_LOG = "领竞技币重复，22点后再领取！"
utf = encode_utf


def normalize_general_visit_ids(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        raw_values = list(value)
    elif value in (None, ""):
        raw_values = []
    else:
        raw_values = re.split(r"[,，;；|\s]+", str(value))
    result: list[str] = []
    for raw in raw_values:
        text = str(raw or "").strip()
        if not text:
            continue
        if text.lower().startswith("0x"):
            try:
                text = str(int(text, 16))
            except ValueError:
                continue
        if not re.fullmatch(r"\d+", text):
            continue
        if text not in result:
            result.append(text)
        if len(result) >= 4:
            break
    return result


def role_is_national_citizen(session: dict[str, Any]) -> bool:
    """Return true only when live role data identifies the office as 国民."""
    role_state = (
        session.get("roleState")
        if isinstance(session.get("roleState"), dict)
        else {}
    )
    role = session.get("role") if isinstance(session.get("role"), dict) else {}
    for source in (role_state, role):
        office_name = str(source.get("officeName") or "").strip()
        has_office_data = bool(office_name)
        office_matches_citizen = office_name == "国民"
        for field in ("officeIdUnsigned", "officeId", "officeIdRaw"):
            value = source.get(field)
            if value in (None, ""):
                continue
            has_office_data = True
            try:
                if isinstance(value, str):
                    try:
                        parsed = int(value, 0)
                    except ValueError:
                        parsed = int(value)
                else:
                    parsed = int(value)
                normalized = parsed & 0xFFFF
            except (TypeError, ValueError):
                continue
            if normalized == 0x0100:
                office_matches_citizen = True
        if has_office_data:
            return office_matches_citizen
        if any(
            source.get(field) not in (None, "")
            for field in ("officeIdUnsigned", "officeId", "officeIdRaw")
        ):
            return office_matches_citizen
    return False


def national_citizen_daily_skip_result(
    session: dict[str, Any],
) -> dict[str, Any] | None:
    if not role_is_national_citizen(session):
        return None
    return {
        "success": True,
        "completed": True,
        "skipped": True,
        "skipReason": "national-citizen",
        "message": "国民跳过",
        "statusText": "已做（国民跳过）",
        "officeId": 0x0100,
        "officeName": "国民",
    }


def country_donation_limits(session: dict[str, Any]) -> dict[str, int]:
    level = int(
        (session.get("role") or {}).get("level")
        or (session.get("roleState") or {}).get("level")
        or 0
    )
    if level <= 0:
        raise RuntimeError("无法读取当前角色等级，不能计算最高捐献额")
    return {
        "level": level,
        "copper": level * int(DAILY_DONATE_CONTRACT["copperPerLevel"]),
        "food": level * int(DAILY_DONATE_CONTRACT["foodPerLevel"]),
    }


def parse_daily_donation_receipt(
    payload: bytes,
    resource: str,
    amount: int = 0,
) -> dict[str, Any]:
    """Normalize live donation receipts, including same-day idempotency.

    Confirmed Android/device responses use signed status bytes. Resource
    donation returns ``-3`` after today's quota has already been consumed;
    technology donation returns ``-4``. Both are terminal proof that the daily
    action is complete and must not remain in the retry queue.
    """

    key = str(resource or "")
    if key not in {"copper", "food", "technology"}:
        raise ValueError(f"未知捐献资源：{resource}")
    labels = {
        "copper": "铜钱",
        "food": "粮食",
        "technology": "科技积分",
    }
    label = labels[key]
    if not payload:
        return {
            "success": False,
            "completed": False,
            "alreadyCompleted": False,
            "resource": key,
            "amount": int(amount),
            "status": None,
            "statusUnsigned": None,
            "message": f"未确认{label}捐献成功（服务器回执为空）",
        }
    status = struct.unpack(">b", bytes(payload[:1]))[0]
    quota_status = -4 if key == "technology" else -3
    already_completed = status == quota_status
    success = status == 0 or already_completed
    if status == 0:
        message = f"已按最高额度捐献{label}{int(amount)}"
    elif already_completed:
        message = f"{label}今日捐献额度已用完，按已完成处理"
    else:
        message = f"未确认{label}捐献成功（响应状态={status}）"
    return {
        "success": success,
        "completed": success,
        "alreadyCompleted": already_completed,
        "completionReason": (
            "daily-donation-quota-used" if already_completed else ""
        ),
        "resource": key,
        "amount": int(amount),
        "status": int(status),
        "statusUnsigned": int(status) & 0xFF,
        "message": message,
    }


def now_ms() -> int:
    return int(time.time() * 1000)


def extract_utf_fields(payload: bytes, *, min_len: int = 1, max_len: int = 220) -> list[dict[str, Any]]:
    """Extract ordered modified-UTF-like fields, including ASCII progress values.

    0xe200 日常任务包里同一条任务通常是：
    任务文本 UTF、进度 UTF（如 0/1）、奖励 UTF（如 +10）。旧的
    extract_utf_strings 只保留中文字符串，无法拿到 0/1，所以这里保留
    ASCII 进度字段。
    """
    fields: list[dict[str, Any]] = []
    for pos in range(0, max(0, len(payload) - 2)):
        ln = int.from_bytes(payload[pos:pos + 2], "big")
        if not (min_len <= ln <= max_len) or pos + 2 + ln > len(payload):
            continue
        raw = payload[pos + 2:pos + 2 + ln]
        try:
            text = raw.decode("utf-8")
        except Exception:
            continue
        if not text:
            continue
        if any(ord(ch) < 0x20 and ch not in "\r\n\t" for ch in text):
            continue
        # Keep fields that are useful for UI/debug: Chinese labels, n/m progress,
        # signed rewards, or reward/resource text containing digits.
        useful = (
            any("\u4e00" <= ch <= "\u9fff" for ch in text)
            or re.fullmatch(r"\d+\s*/\s*\d+", text.strip())
            or re.fullmatch(r"[+-]\d+", text.strip())
            or bool(re.search(r"\d", text) and len(text) <= 80)
        )
        if useful:
            fields.append({"offset": pos, "length": ln, "text": text})
    fields.sort(key=lambda x: int(x.get("offset") or 0))
    # Remove overlapping duplicate hits caused by scanning every byte.
    deduped: list[dict[str, Any]] = []
    last_end = -1
    for item in fields:
        off = int(item["offset"])
        end = off + 2 + int(item["length"])
        if off < last_end and deduped and item["text"] == deduped[-1]["text"]:
            continue
        deduped.append(item)
        last_end = max(last_end, end)
    return deduped


def parse_e200_daily_activity(payload: bytes, source_opcode: str = "0x6200/0xe200") -> dict[str, Any]:
    fields = extract_utf_fields(payload, min_len=1, max_len=220)
    result: dict[str, Any] = {
        "sourceOpcode": source_opcode,
        "updatedAt": now_ms(),
        "payloadByteCount": len(payload),
        "treasureOccupied": {},
        "tasks": [],
    }
    progress_re = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
    for idx, item in enumerate(fields):
        text = str(item.get("text") or "")
        progress_item = next((x for x in fields[idx + 1:idx + 6] if progress_re.match(str(x.get("text") or ""))), None)
        reward_item = next((x for x in fields[idx + 1:idx + 8] if re.fullmatch(r"\s*[+-]\d+\s*", str(x.get("text") or ""))), None)
        if any("\u4e00" <= ch <= "\u9fff" for ch in text):
            task: dict[str, Any] = {"text": text, "offset": item.get("offset")}
            if progress_item:
                m = progress_re.match(str(progress_item.get("text") or ""))
                if m:
                    task.update({
                        "progress": progress_item.get("text"),
                        "current": int(m.group(1)),
                        "target": int(m.group(2)),
                    })
            if reward_item:
                task["reward"] = str(reward_item.get("text") or "").strip()
            result["tasks"].append(task)
            if "宝藏" in text and any(k in text for k in ["占领", "佔領"]):
                result["treasureOccupied"] = dict(task)
    if not result["treasureOccupied"]:
        text_preview = printable(payload, 2000)
        m = re.search(r"(?:成功)?占领\s*(\d+)个宝藏.*?(\d+)\s*/\s*(\d+)", text_preview)
        if m:
            result["treasureOccupied"] = {
                "text": f"成功占领{m.group(1)}个宝藏",
                "progress": f"{m.group(2)}/{m.group(3)}",
                "current": int(m.group(2)),
                "target": int(m.group(3)),
                "source": "textPreviewFallback",
            }
    return result


def parse_status_message_payload(payload: bytes) -> dict[str, Any]:
    """Parse the common byte-status + UTF message prefix used by action replies."""
    if not payload:
        return {"success": False, "status": None, "message": "响应为空"}
    status = struct.unpack(">b", payload[:1])[0]
    try:
        message, offset = read_utf(payload, 1)
    except Exception:
        message, offset = printable(payload, 300), 1
    return {
        "success": status == 0,
        "status": status,
        "message": message,
        "remainingHex": payload[offset:].hex()[:4096],
    }


# ---------------------------------------------------------------------------
# Daily country features (protocols recovered from the latest desktop capture)
# ---------------------------------------------------------------------------

DAILY_GENERAL_PAGE_SIZE = int(DAILY_GENERAL_VISIT_CONTRACT["pageSize"])
DAILY_NATIONAL_PAGE_SIZE = int(DAILY_NATIONAL_CONTRACT["pageSize"])
DAILY_NATIONAL_CATEGORIES = tuple(
    int(value)
    for value in DAILY_NATIONAL_CONTRACT["includedListCategories"]
)
DAILY_NATIONAL_MAX_PAGES = 100
DAILY_NATIONAL_MAX_ATTEMPTS = int(DAILY_NATIONAL_CONTRACT["maxAttempts"])


def _daily_read_utf(payload: bytes, offset: int) -> tuple[str, int]:
    if offset < 0 or offset + 2 > len(payload):
        raise ValueError(f"UTF长度字段越界 offset={offset} size={len(payload)}")
    length = struct.unpack_from(">H", payload, offset)[0]
    offset += 2
    if offset + length > len(payload):
        raise ValueError(
            f"UTF字段越界 length={length} offset={offset} size={len(payload)}"
        )
    return payload[offset:offset + length].decode("utf-8", errors="replace"), offset + length


def _daily_i16(payload: bytes, offset: int) -> tuple[int, int]:
    if offset + 2 > len(payload):
        raise ValueError(f"short字段越界 offset={offset}")
    return struct.unpack_from(">h", payload, offset)[0], offset + 2


def _daily_u16(payload: bytes, offset: int) -> tuple[int, int]:
    if offset + 2 > len(payload):
        raise ValueError(f"unsigned short字段越界 offset={offset}")
    return struct.unpack_from(">H", payload, offset)[0], offset + 2


def _daily_i32(payload: bytes, offset: int) -> tuple[int, int]:
    if offset + 4 > len(payload):
        raise ValueError(f"int字段越界 offset={offset}")
    return struct.unpack_from(">i", payload, offset)[0], offset + 4


def _daily_i64(payload: bytes, offset: int) -> tuple[int, int]:
    if offset + 8 > len(payload):
        raise ValueError(f"long字段越界 offset={offset}")
    return struct.unpack_from(">q", payload, offset)[0], offset + 8


def build_salary_payload() -> bytes:
    """0x314b claim request: one byte mode=1."""
    return b"\x01"


def build_national_city_list_payload(category: int, page: int) -> bytes:
    if int(category) not in DAILY_NATIONAL_CATEGORIES:
        raise ValueError("国家征收只允许查询州城、郡城、县城，禁止查询小城")
    if int(page) < 1 or int(page) > 0x7FFF:
        raise ValueError("国家城池列表页码无效")
    return struct.pack(">qBH", 1, int(category), int(page))


def build_national_city_status_payload(city_name: str) -> bytes:
    name = str(city_name or "").strip()
    if not name:
        raise ValueError("国家征收状态查询缺少城池名称")
    return b"\x01" + utf(name)


def build_national_collect_payload(city_name: str) -> bytes:
    return build_national_city_status_payload(city_name)


def build_owned_city_list_payload(role_id: int | str | None = None) -> bytes:
    """0x1318 查询自己作为城主拥有的城池。

    2026-07-25 抓包（passive_pcap_hotspot_20260725_010719 flow #131）：
      req payload = i64(roleId?) + u16(0)
      实测 roleId=2 时返回小城「南化」(104,20)。
    头像 → 城池信息 走的就是这个接口，不是 0x1310 封地列表。
    """
    rid = int(role_id or 0)
    if rid < 0:
        raise ValueError("自有城池查询 roleId 无效")
    return struct.pack(">qH", rid, 0)


def build_city_lord_collect_payload(city_name: str) -> bytes:
    name = str(city_name or "").strip()
    if not name:
        raise ValueError("城主征收缺少城池名称")
    # 2026-07-25 抓包 flow #133：01 + UTF(南化) + 00
    return b"\x01" + utf(name) + b"\x00"


def parse_owned_city_list(payload: bytes) -> dict[str, Any]:
    """Parse 0x8318 自有城池列表/详情。

    证据：
      - 操作口述：头像→城池信息只返回自己当城主的城（当时仅小城南化）
      - 抓包 flow #131 resp：可解析出 name=南化, x=104, y=20, owner=宿代苑
      - 客户端 k.M0 对 0x8318 的首段读取：
          status:u8, count:u8, 然后每条 city 记录以
          long + byte + UTF(name) + short x + short y 开头
    当前实现先稳定提取征收所需的 cityName/x/y/owner；其余字段保留 raw。
    """
    raw = payload or b""
    if len(raw) < 2:
        return {
            "success": False,
            "status": None,
            "count": 0,
            "cities": [],
            "message": f"0x8318响应过短：{len(raw)}",
            "rawHex": raw.hex()[:4096],
        }
    status = raw[0]
    count = raw[1]
    offset = 2
    cities: list[dict[str, Any]] = []
    message = ""

    # status==1：客户端提示“没有城池”
    if int(status) == 1:
        return {
            "success": True,
            "status": int(status),
            "count": 0,
            "cities": [],
            "noCity": True,
            "message": "没有城池",
            "rawHex": raw.hex()[:4096],
            "parsedBytes": offset,
        }

    def read_city_record(start: int, index: int) -> tuple[dict[str, Any] | None, int]:
        p = start
        if p + 9 > len(raw):
            return None, start
        city_id = struct.unpack_from(">q", raw, p)[0]
        p += 8
        kind_or_flag = raw[p]
        p += 1
        try:
            name, p2 = _daily_read_utf(raw, p)
        except Exception:
            return None, start
        p = p2
        if p + 4 > len(raw):
            return None, start
        x = struct.unpack_from(">H", raw, p)[0]
        y = struct.unpack_from(">H", raw, p + 2)[0]
        p += 4
        owner = ""
        owner_level = None
        # 尽量吸收 owner/level，失败也不影响 cityName
        try:
            if p + 2 <= len(raw):
                # 中间还有若干固定宽字段；用“下一个中文 UTF”扫描 owner。
                probe = p
                found_owner_at = None
                while probe + 2 <= len(raw) and probe < p + 64:
                    n = struct.unpack_from(">H", raw, probe)[0]
                    if 1 <= n <= 30 and probe + 2 + n <= len(raw):
                        chunk = raw[probe + 2:probe + 2 + n]
                        try:
                            text = chunk.decode("utf-8")
                        except Exception:
                            probe += 1
                            continue
                        if any("一" <= ch <= "鿿" for ch in text):
                            found_owner_at = probe
                            owner = text
                            after = probe + 2 + n
                            if after < len(raw):
                                owner_level = raw[after]
                            break
                    probe += 1
                if found_owner_at is not None:
                    # 不强制推进主游标到 owner 后，避免未识别字段错位；
                    # 主游标只保证消费到 x/y 后的最小记录，便于 count>1 时继续。
                    pass
        except Exception:
            pass
        # 主记录最小前进：long+byte+utf+x+y；若 count 指示多城，尝试按
        # 下一条 long+byte+utf 的起点启发式推进。
        next_p = p
        record = {
            "index": index,
            "cityId": int(city_id),
            "cityIdHex": f"{int(city_id) & 0xFFFFFFFFFFFFFFFF:016x}",
            "kindCode": int(kind_or_flag),
            "name": name,
            "cityName": name,
            "city": name,
            "x": int(x),
            "y": int(y),
            "ownerName": owner,
            "ownerLevel": owner_level,
        }
        return record, next_p

    if int(count) > 0:
        cursor = offset
        for index in range(1, int(count) + 1):
            city, cursor2 = read_city_record(cursor, index)
            if city is None:
                break
            cities.append(city)
            # 尝试定位下一条：从当前 utf/x/y 之后扫描下一个“long + byte + utf中文名”
            scan = cursor2
            next_start = None
            while scan + 11 <= len(raw) and index < int(count):
                n = struct.unpack_from(">H", raw, scan + 9)[0] if scan + 11 <= len(raw) else 0
                # long(8)+byte(1)+utfLen(2)
                if 1 <= n <= 30 and scan + 11 + n <= len(raw):
                    chunk = raw[scan + 11:scan + 11 + n]
                    try:
                        text = chunk.decode("utf-8")
                    except Exception:
                        scan += 1
                        continue
                    if any("一" <= ch <= "鿿" for ch in text):
                        next_start = scan
                        break
                scan += 1
            if next_start is None:
                cursor = cursor2
                break
            cursor = next_start
        offset = cursor
    else:
        # count==0 但 body 仍可能带单城详情（抓包 #131 即此形态）：
        # status,count 后直接 long+byte+UTF(name)+x+y...
        city, offset2 = read_city_record(offset, 1)
        if city is not None:
            cities.append(city)
            offset = offset2
            count = 1

    return {
        "success": True,
        "status": int(status),
        "count": len(cities),
        "declaredCount": int(count) if raw[1:2] else 0,
        "cities": cities,
        "message": message,
        "rawHex": raw.hex()[:4096],
        "parsedBytes": offset,
        "trailingHex": raw[offset:].hex()[:4096],
    }


def build_general_visit_list_payload(page: int, page_size: int = DAILY_GENERAL_PAGE_SIZE) -> bytes:
    if int(page) < 1 or int(page) > 0x7FFF:
        raise ValueError("名将列表页码无效")
    if int(page_size) < 1 or int(page_size) > 0x7FFF:
        raise ValueError("名将列表页大小无效")
    return struct.pack(">HH", int(page), int(page_size))


def build_general_visit_payload(general_id: int | str, page: int, page_size: int = DAILY_GENERAL_PAGE_SIZE) -> bytes:
    return struct.pack(">qHH", int(general_id), int(page), int(page_size))


def parse_daily_status_utf_receipt(payload: bytes, *, success_status: int = 1) -> dict[str, Any]:
    """Parse compact daily receipts such as 0x8330 city-lord collect.

    Layout observed for city-lord success:
      status:u8 + UTF(message) + trailing longs
    """
    if not payload:
        return {"success": False, "status": None, "message": "响应为空", "remainingHex": ""}
    status = struct.unpack_from(">b", payload, 0)[0]
    try:
        message, offset = _daily_read_utf(payload, 1)
    except Exception:
        message, offset = printable(payload, 500), 1
    return {
        "success": status == int(success_status),
        "status": status,
        "message": clean_activity_result_message(message),
        "remainingHex": payload[offset:].hex()[:4096],
    }


def parse_salary_receipt(payload: bytes) -> dict[str, Any]:
    """Parse 0xA14B 国家俸禄回执。

    2026-07-25 真实抓包 flow #021：
      01 00 + UTF("领取国家俸禄成功，获得铜钱642850，粮食1190689。") + longs...
    即 status:u8 + extra:u8 + UTF(message) + trailing values。
    旧实现少读了 extra 字节，会把文案解析成空，最终只剩“服务器确认成功”。
    """
    raw = payload or b""
    if not raw:
        return {
            "success": False,
            "completed": False,
            "status": None,
            "extra": None,
            "message": "响应为空",
            "copper": None,
            "food": None,
            "remainingHex": "",
        }
    status = struct.unpack_from(">b", raw, 0)[0]
    extra = raw[1] if len(raw) >= 2 else None
    message = ""
    offset = 1
    # 优先按 status + extra + UTF 解析；若 extra 位置其实已是 UTF 长度高字节，再回退。
    if len(raw) >= 2:
        try:
            message, offset = _daily_read_utf(raw, 2)
        except Exception:
            try:
                message, offset = _daily_read_utf(raw, 1)
                extra = None
            except Exception:
                message, offset = printable(raw[1:], 500), 1
                extra = None
    cleaned = clean_activity_result_message(message)
    copper = None
    food = None
    copper_match = re.search(r"铜钱\s*([0-9,，]+)", cleaned)
    food_match = re.search(r"粮食\s*([0-9,，]+)", cleaned)
    if copper_match:
        copper = int(re.sub(r"[,，]", "", copper_match.group(1)))
    if food_match:
        food = int(re.sub(r"[,，]", "", food_match.group(1)))

    already = any(
        marker in cleaned
        for marker in DAILY_SALARY_CONTRACT["alreadyClaimedMarkers"]
    )
    no_office = any(
        marker in cleaned
        for marker in DAILY_SALARY_CONTRACT["noOfficeMarkers"]
    )
    success_by_text = (
        any(marker in cleaned for marker in DAILY_SALARY_CONTRACT["successMarkers"])
        or (copper is not None or food is not None)
    )
    # 兼容两套回执：status==1 直接成功；或 status==0 且 extra==1/文案成功。
    success = (
        int(status) == 1
        or (int(status) == 0 and (extra == 1 or success_by_text) and not no_office)
        or already
    )
    if already:
        # 统一成用户可读短句
        summary = "无法再次领取"
    elif no_office:
        summary = "无官职无法领取"
        success = False
    elif success and (copper is not None or food is not None):
        copper_text = f"{copper}铜钱" if copper is not None else ""
        food_text = f"{food}粮食" if food is not None else ""
        joined = "、".join(part for part in (copper_text, food_text) if part)
        summary = f"领取成功{joined}" if joined else (cleaned or "领取俸禄成功")
    elif success:
        summary = cleaned or "领取俸禄成功"
    else:
        summary = cleaned or "领取俸禄失败"

    return {
        "success": bool(success),
        "completed": bool(success or already),
        "alreadyClaimed": bool(already),
        "noOffice": bool(no_office),
        "status": int(status),
        "extra": None if extra is None else int(extra),
        "message": summary,
        "rawMessage": cleaned,
        "copper": copper,
        "food": food,
        "remainingHex": raw[offset:].hex()[:4096],
    }


def parse_national_collect_status(payload: bytes) -> dict[str, Any]:
    if len(payload) < 36:
        raise ValueError(f"0x8332响应过短：{len(payload)}")
    status, availability, used_count, limit = payload[:4]
    current_copper = struct.unpack_from(">q", payload, 4)[0]
    copper_cap = struct.unpack_from(">q", payload, 12)[0]
    current_food = struct.unpack_from(">q", payload, 20)[0]
    food_cap = struct.unpack_from(">q", payload, 28)[0]
    return {
        "status": int(status),
        "availability": int(availability),
        "usedCount": int(used_count),
        "limit": int(limit),
        "currentCopper": int(current_copper),
        "copperCap": int(copper_cap),
        "currentFood": int(current_food),
        "foodCap": int(food_cap),
        "quotaExhausted": int(used_count) >= int(limit),
        "canCollect": (
            int(status) == 0
            and int(availability) == 0
            and int(used_count) < int(limit)
            and int(current_copper) > 0
        ),
    }


def _national_kind_from_wire(value: int) -> str:
    return {
        0: "state",
        1: "commandery",
        2: "county",
        3: "small",
    }.get(int(value), "unknown")


def _national_kind_from_category(value: int) -> str:
    return {
        1: "state",
        2: "commandery",
        3: "county",
        4: "small",
    }.get(int(value), "unknown")


def parse_national_city_page(payload: bytes, requested_category: int = 0) -> dict[str, Any]:
    # The captured 0x8404 body starts with a seven-byte header:
    #   status(1), response category(1), total pages(u16), page(u16), count(1)
    # Older code treated this as eight bytes and shifted every field by one,
    # which made real city pages look empty (and could turn a page count into
    # an enormous value).  Keep the offsets explicit because this parser is
    # also used by the national-collection selector.
    header_bytes = int(DAILY_NATIONAL_CONTRACT["responseHeaderBytes"])
    tail_bytes = int(DAILY_NATIONAL_CONTRACT["recordTailBytes"])
    if len(payload) < header_bytes:
        raise ValueError(f"0x8404响应过短：{len(payload)}")
    status = payload[0]
    response_category = payload[1]
    total_pages = struct.unpack_from(">H", payload, 2)[0]
    page = struct.unpack_from(">H", payload, 4)[0]
    count = payload[header_bytes - 1]
    category = (
        int(response_category)
        if response_category in range(1, 6)
        else int(requested_category)
    )
    offset = header_bytes
    cities: list[dict[str, Any]] = []
    for index in range(int(count)):
        name, offset = _daily_read_utf(payload, offset)
        if offset >= len(payload):
            raise ValueError(f"国家城池记录{index + 1}缺少类型")
        wire_kind = payload[offset]
        offset += 1
        x, offset = _daily_i16(payload, offset)
        y, offset = _daily_i16(payload, offset)
        owner, offset = _daily_read_utf(payload, offset)
        if offset + tail_bytes > len(payload):
            raise ValueError(f"国家城池记录{index + 1}尾部不完整")
        tail = payload[offset:offset + tail_bytes]
        offset += tail_bytes
        kind = _national_kind_from_wire(wire_kind)
        if kind == "unknown":
            kind = _national_kind_from_category(category)
        cities.append({
            "index": index + 1,
            "name": name,
            "cityName": name,
            "kind": kind,
            "kindCode": int(wire_kind),
            "x": int(x),
            "y": int(y),
            "ownerLabel": owner,
            "listCategory": int(category),
            "rawTailHex": tail.hex(),
        })
    return {
        "status": int(status),
        "category": int(category),
        "responseCategory": int(response_category),
        "totalPages": max(1, int(total_pages)),
        "page": max(1, int(page)),
        "count": int(count),
        "cities": cities,
        "parsedBytes": offset,
    }


def _parse_general_visit_candidate(payload: bytes, offset: int) -> tuple[dict[str, Any], int]:
    general_id, offset = _daily_i64(payload, offset)
    name, offset = _daily_read_utf(payload, offset)
    if offset + 4 > len(payload):
        raise ValueError("名将记录基础字段不完整")
    unknown_a, unknown_b = payload[offset], payload[offset + 1]
    level, job = payload[offset + 2], payload[offset + 3]
    offset += 4
    portrait, offset = _daily_i16(payload, offset)
    fief_name, offset = _daily_read_utf(payload, offset)
    city_name, offset = _daily_read_utf(payload, offset)
    if offset >= len(payload):
        raise ValueError("名将记录缺少俘虏状态")
    captive_state = payload[offset]
    offset += 1
    owner_name, offset = _daily_read_utf(payload, offset)
    salary_stars, offset = _daily_i16(payload, offset)
    if offset >= len(payload):
        raise ValueError("名将记录缺少忠诚度")
    loyalty = payload[offset]
    offset += 1
    exp, offset = _daily_i64(payload, offset)
    exp_limit, offset = _daily_i64(payload, offset)
    # Two protocol fields are currently unknown, followed by the displayed stats.
    _unknown_1, offset = _daily_i16(payload, offset)
    _unknown_2, offset = _daily_i16(payload, offset)
    growth, offset = _daily_i16(payload, offset)
    breakout, offset = _daily_i16(payload, offset)
    strength_base, offset = _daily_i16(payload, offset)
    strength_total, offset = _daily_i16(payload, offset)
    intelligence_base, offset = _daily_i16(payload, offset)
    intelligence_total, offset = _daily_i16(payload, offset)
    command, offset = _daily_i16(payload, offset)
    troop_limit, offset = _daily_i16(payload, offset)
    return {
        "id": str(general_id),
        "idInt": int(general_id),
        "name": name,
        "level": int(level),
        "job": int(job),
        "portrait": int(portrait),
        "fiefName": fief_name,
        "cityName": city_name,
        "captiveState": int(captive_state),
        "ownerName": owner_name,
        "salaryStars": int(salary_stars),
        "loyalty": int(loyalty),
        "exp": int(exp),
        "expLimit": int(exp_limit),
        "growth": int(growth),
        "breakout": int(breakout),
        "strengthBase": int(strength_base),
        "strengthTotal": int(strength_total),
        "intelligenceBase": int(intelligence_base),
        "intelligenceTotal": int(intelligence_total),
        "command": int(command),
        "troopLimit": int(troop_limit),
        "force": int(strength_total),
        "intelligence": int(intelligence_total),
        "available": int(captive_state) == 0,
        "rawUnknown": [int(unknown_a), int(unknown_b)],
        "_pageOffset": offset,
    }, offset


def parse_general_visit_page(payload: bytes) -> dict[str, Any]:
    if len(payload) < 6:
        # Business rejections may contain only status + UTF text.  Three
        # bytes is therefore the minimum useful frame even though a normal
        # paged response is longer.
        if len(payload) < 3:
            raise ValueError(f"0xA271响应过短：{len(payload)}")
    status = struct.unpack_from(">b", payload, 0)[0]
    message, offset = _daily_read_utf(payload, 1)
    if offset + 5 > len(payload):
        return {
            "status": int(status),
            "message": clean_activity_result_message(message),
            "pageSize": 0,
            "page": 0,
            "count": 0,
            "candidates": [],
            "parsedBytes": offset,
            "shortReceipt": True,
        }
    page_size, offset = _daily_u16(payload, offset)
    page, offset = _daily_u16(payload, offset)
    if offset >= len(payload):
        raise ValueError("名将列表缺少数量")
    count = payload[offset]
    offset += 1
    candidates = []
    for _ in range(int(count)):
        candidate, offset = _parse_general_visit_candidate(payload, offset)
        candidates.append(candidate)
    return {
        "status": int(status),
        "message": clean_activity_result_message(message),
        "pageSize": int(page_size),
        "page": int(page),
        "count": int(count),
        "candidates": candidates,
        "parsedBytes": offset,
    }


def general_visit_already_visited(status: Any, message: Any) -> bool:
    return int(status or 0) == int(DAILY_GENERAL_VISIT_CONTRACT["alreadyVisitedStatus"]) and any(
        marker in str(message or "")
        for marker in DAILY_GENERAL_VISIT_CONTRACT["alreadyVisitedMarkers"]
    )


def general_visit_has_no_candidates(status: Any, message: Any) -> bool:
    """Return whether the server explicitly says the king has no generals.

    This is a normal, actionable-empty result rather than a transport or
    protocol failure.  Keep the status check broad because the live server's
    business status may vary while the human-readable reason is stable.
    """

    return int(status or 0) != 0 and any(
        marker in str(message or "")
        for marker in DAILY_GENERAL_VISIT_CONTRACT.get(
            "noCandidateMarkers", ["国王麾下无名将"]
        )
    )


def parse_general_visit_receipt(payload: bytes) -> dict[str, Any]:
    if len(payload) < 4:
        raise ValueError(f"0xA273响应过短：{len(payload)}")
    status = struct.unpack_from(">i", payload, 0)[0]
    message, offset = _daily_read_utf(payload, 4)
    cleaned_message = clean_activity_result_message(message)
    already_visited = general_visit_already_visited(status, cleaned_message)
    # 拜访交互本身是否完成：接受征召、拒绝征召都算“今天已经拜访过了”。
    # “名将已被俘虏/已被结交”等表示拜访没真正发生，可顺延下一个候选。
    invitation_resolved = int(status) == 0 and any(
        marker in cleaned_message
        for marker in DAILY_GENERAL_VISIT_CONTRACT["invitationResolvedMarkers"]
    )
    visit_succeeded = int(status) == 1 or invitation_resolved
    return {
        "status": int(status),
        "message": cleaned_message,
        # 业务语义：只要成功完成一次拜访交互就算成功（含拒绝征召）。
        "success": visit_succeeded,
        "completed": visit_succeeded or already_visited,
        "recruited": int(status) == 1,
        "alreadyVisited": already_visited,
        "invitationResolved": invitation_resolved,
        "invitationRejected": invitation_resolved and "拒绝了阁下的邀请" in cleaned_message,
        "remainingHex": payload[offset:].hex()[:4096],
    }




def trailing_utf_message(payload: bytes) -> str:
    """Return a UTF field that exactly occupies the end of a packet payload."""
    raw = payload or b""
    for offset in range(len(raw) - 2, -1, -1):
        size = struct.unpack(">H", raw[offset:offset + 2])[0]
        if offset + 2 + size != len(raw):
            continue
        try:
            message = raw[offset + 2:].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if message.strip():
            return message.strip()
    return ""


def clean_activity_result_message(message: Any) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "；", str(message or ""))
    text = re.sub(r"<[^>]+>", "", text)
    return "；".join(
        part.strip()
        for part in re.split(r"[。；;]+", text)
        if part.strip()
    )


def parse_arena_coin_claim_response(payload: bytes) -> dict[str, Any]:
    """Normalize the observed 0xe266 duplicate-claim reply.

    Live evidence after a successful claim:
      fe 0000 01 00000000000325e4 0000012c
      ^^ ^^^^
      -2 empty UTF message

    The server uses status -2 with an empty UTF string and a fixed-size
    13-byte trailing reward-state block when the current arena reward has
    already been consumed. Treat this idempotently as today's task completed.
    """
    parsed = parse_status_message_payload(payload)
    duplicate = (
        parsed.get("status") == -2
        and not str(parsed.get("message") or "").strip()
        and len(payload or b"") == 16
        and (payload or b"")[1:3] == b"\x00\x00"
        and (payload or b"")[3:4] == b"\x01"
    )
    if duplicate:
        parsed.update({
            "success": True,
            "message": ARENA_COINS_DUPLICATE_LOG,
            "alreadyClaimed": True,
            "duplicateClaim": True,
            "serverStatus": -2,
        })
    return parsed

def parse_daily_sign_in_packets(packets: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse the known reply shapes for 0x6202 daily sign-in.

    Current live servers return a complete 0x8134 activity list for both
    branches. A fresh sign-in ends with a UTF reward message such as
    “铜钱:10000获得成功。粮食:30000获得成功。”; a duplicate ends with
    “本日已签到”. Older servers may still acknowledge a fresh sign-in with
    0xe202.
    """
    activity_response: dict[str, Any] | None = None
    for packet in packets:
        if packet.get("opcode") != DAILY_SIGN_IN_ACTIVITY_OPCODE:
            continue
        activity_response = packet
        payload = packet.get("payload") or b""
        server_message = trailing_utf_message(payload)
        raw_text = payload.decode("utf-8", errors="ignore")
        duplicate_marker = next((
            marker for marker in DAILY_SIGN_IN_CONTRACT["duplicateMarkers"]
            if marker in raw_text or marker in server_message
        ), "")
        if duplicate_marker:
            return {
                "success": True,
                "status": None,
                "message": DAILY_SIGN_IN_DUPLICATE_LOG,
                "alreadyClaimed": True,
                "duplicateClaim": True,
                "serverMessage": duplicate_marker,
                "responseOpcode": f"0x{DAILY_SIGN_IN_ACTIVITY_OPCODE:04x}",
                "payloadHex": payload.hex(),
                "remainingHex": "",
            }
        if server_message and any(
            marker in server_message
            for marker in DAILY_SIGN_IN_CONTRACT["successMarkers"]
        ):
            return {
                "success": True,
                "status": 0,
                "message": clean_activity_result_message(server_message),
                "serverMessage": server_message,
                "alreadyClaimed": False,
                "duplicateClaim": False,
                "responseOpcode": f"0x{DAILY_SIGN_IN_ACTIVITY_OPCODE:04x}",
                "payloadHex": payload.hex(),
                "remainingHex": "",
            }
    response = next((
        p for p in packets
        if p.get("opcode") == DAILY_SIGN_IN_LEGACY_OPCODE
    ), None)
    if response is None:
        if activity_response is not None:
            payload = activity_response.get("payload") or b""
            server_message = trailing_utf_message(payload)
            return {
                "success": False,
                "status": None,
                "message": (
                    f"签到响应未能识别：{clean_activity_result_message(server_message)}"
                    if server_message else
                    "收到 0x8134 签到响应，但未找到成功或已签到标记"
                ),
                "serverMessage": server_message,
                "responseOpcode": f"0x{DAILY_SIGN_IN_ACTIVITY_OPCODE:04x}",
                "payloadHex": payload.hex(),
                "remainingHex": "",
            }
        return {
            "success": False,
            "status": None,
            "message": (
                "未收到可识别的签到响应（"
                f"0x{DAILY_SIGN_IN_LEGACY_OPCODE:04x}/"
                f"0x{DAILY_SIGN_IN_ACTIVITY_OPCODE:04x}）"
            ),
            "responseOpcode": "",
            "payloadHex": "",
            "remainingHex": "",
        }
    payload = response.get("payload") or b""
    if not payload:
        return {
            "success": True,
            "status": 0,
            "message": str(DAILY_SIGN_IN_CONTRACT["confirmedMessage"]),
            "responseOpcode": f"0x{DAILY_SIGN_IN_LEGACY_OPCODE:04x}",
            "payloadHex": "",
            "remainingHex": "",
        }
    parsed = parse_status_message_payload(payload)
    return {
        **parsed,
        "responseOpcode": f"0x{DAILY_SIGN_IN_LEGACY_OPCODE:04x}",
        "payloadHex": payload.hex(),
    }


def parse_daily_diamond_box_response(payload: bytes) -> dict[str, Any]:
    """Normalize the expired-activity reply as today's box already claimed.

    The live 0x8134 reply can contain a complete activity list followed by
    “操作失败，活动已过期。”, rather than the common status+UTF layout.
    For this daily action the expired entry means there is nothing left to
    claim today, so treat it as an idempotent success.
    """
    raw_text = (payload or b"").decode("utf-8", errors="ignore")
    trailing_message = trailing_utf_message(payload)
    combined_message = f"{raw_text}\n{trailing_message}"
    if any(marker in raw_text for marker in DAILY_DIAMOND_BOX_CONTRACT["expiredMarkers"]):
        server_message = "操作失败，活动已过期。"
        return {
            "success": True,
            "status": struct.unpack(">b", payload[:1])[0] if payload else None,
            "message": str(DAILY_DIAMOND_BOX_CONTRACT["alreadyClaimedMessage"]),
            "alreadyClaimed": True,
            "serverMessage": server_message,
            "normalizedFromExpiredActivity": True,
            "remainingHex": "",
        }
    if any(text in combined_message for text in DAILY_DIAMOND_BOX_CONTRACT["duplicateMarkers"]):
        return {
            "success": True,
            "status": None,
            "message": str(DAILY_DIAMOND_BOX_CONTRACT["alreadyClaimedMessage"]),
            "alreadyClaimed": True,
            "serverMessage": trailing_message or clean_activity_result_message(raw_text),
            "remainingHex": "",
        }
    if trailing_message and any(
        marker in trailing_message
        for marker in DAILY_SIGN_IN_CONTRACT["successMarkers"]
    ):
        return {
            "success": True,
            "status": 0,
            "message": clean_activity_result_message(trailing_message),
            "alreadyClaimed": False,
            "serverMessage": trailing_message,
            "remainingHex": "",
        }
    common_status_utf = (
        len(payload or b"") >= 3
        and struct.unpack(">H", (payload or b"")[1:3])[0] == len(payload or b"") - 3
    )
    if not common_status_utf:
        return {
            "success": False,
            "status": None,
            "message": (
                f"每日金钻宝箱响应未能识别：{clean_activity_result_message(trailing_message)}"
                if trailing_message else
                "每日金钻宝箱响应未包含可识别的结果"
            ),
            "serverMessage": trailing_message,
            "remainingHex": "",
        }
    parsed = parse_status_message_payload(payload)
    message = str(parsed.get("message") or "")
    if any(text in message for text in DAILY_DIAMOND_BOX_CONTRACT["duplicateMarkers"]):
        parsed.update({
            "success": True,
            "message": str(DAILY_DIAMOND_BOX_CONTRACT["alreadyClaimedMessage"]),
            "alreadyClaimed": True,
            "serverMessage": message,
        })
    return parsed
