"""俘虏营 (prison) records, requests and the release/persuade policy.

Everything here was read off the 2026-09-14 hotspot capture, in which the
operator persuaded and released captives one at a time while narrating.

The wire facts, in the order a client meets them:

* Captives are **type-1 objects of the same table sync as generals**.  The
  login role state (0x8004) carries, right after the generals block, a
  ``u8 count`` and then one record per captive.  Each record is a general
  record - ``i64 id, UTF name, 114-byte common body`` (profession, growth,
  level, loyalty, ``heroStatus`` 3 = 俘, ``placeId`` -1; the last two body
  bytes, ``FF FF`` on a general, hold the rescue count) - followed by the
  prison extension: ``u16 reserved, i64 prisonFiefId, UTF prisonFiefName,
  u16 reserved, i64 persuadeCooldownBaseMillis``.  The ``u16`` at body
  offset ``0x57`` is the persuade attempt count.
* ``0x1233`` (``reqPrisonerCtrlInfo``): ``u8 0, i64 captiveId`` → ``0x8233``:
  ``u8, u8, i64 copperCost, i64 goldCost`` (125/150/175 铜 or 1 黄金).
* ``0x1234`` 劝降: ``i64 prisonFiefId, i64 captiveId, u8 payMode`` where
  ``payMode`` 0 spends copper.  ``0x8234`` answers ``u8 status, UTF
  message`` and then the rebuilt object tables: on success (status 0) the
  generals table *and* the captives table, on failure (status 249, "劝降失败，
  您需要等待下次劝降！") only the captives table.  A failed attempt raises
  ``persuadeCount`` by one, lowers loyalty by three and starts a one-hour
  cooldown, recorded as the attempt time in ``persuadeCooldownBaseMillis``.
* ``0x1236`` 释放: same body as 0x1234 → ``0x8236``: ``u8 status, u8 count``
  and the remaining captives.

The prison "host" in both requests is the *fief* holding the captive, not the
role: account 202's requests carried 205, its base fief id.
"""

from __future__ import annotations

import struct
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..protocol.wire import read_utf
from .generals import general_status_text_from_code


#: Wire value of 将领状态 "俘" - the one status a captive record carries.
CAPTIVE_STATUS_CODE = 3

#: How long a failed 劝降 locks the captive, as the client computes it:
#: ``max(cp + 3600000 - now, 0)``.
PERSUADE_COOLDOWN_MILLIS = 60 * 60 * 1000

#: Sizes of the pieces the client reads for one captive after its name.
_COMMON_BODY_BYTES = 114
_PRISON_FIXED_BEFORE_FIEF_NAME = 10   # u16 reserved, i64 prisonFiefId
_PRISON_FIXED_AFTER_FIEF_NAME = 10    # u16 reserved, i64 persuadeCooldownBaseMillis

#: 0x8234 status byte for "wait for the next attempt".
PERSUADE_STATUS_COOLDOWN = 249

PAY_MODE_COPPER = 0
PAY_MODE_GOLD = 1

_PROFESSION_LABELS = {0: "步将", 1: "弓将", 2: "骑将", 4: "勇士"}


def _u16(payload: bytes, offset: int) -> int:
    return int.from_bytes(payload[offset:offset + 2], "big")


def _i64(payload: bytes, offset: int) -> int:
    return int.from_bytes(payload[offset:offset + 8], "big", signed=True)


def parse_captive_record(payload: bytes, offset: int) -> Tuple[Dict[str, Any], int]:
    """Read one captive record starting at ``offset``; return it and the end.

    Raises ``ValueError`` when the bytes cannot be a captive: the status is
    not 俘, the fief is not "none", or a field is out of its wire range.
    Callers scanning for the block rely on that to reject false starts.
    """

    if offset + 8 + 2 > len(payload):
        raise ValueError("俘虏记录不完整")
    captive_id = _i64(payload, offset)
    if captive_id <= 0:
        raise ValueError("俘虏 ID 无效")
    name, body = read_utf(payload, offset + 8)
    if not name or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in name):
        raise ValueError("俘虏名称无效")
    if body + _COMMON_BODY_BYTES + _PRISON_FIXED_BEFORE_FIEF_NAME + 2 > len(payload):
        raise ValueError("俘虏记录主体不完整")
    status = payload[body + 0x56]
    place_id = _i64(payload, body + 0x32)
    growth = _u16(payload, body + 0x06)
    level = payload[body + 0x08]
    loyalty = payload[body + 0x27]
    loyalty_limit = payload[body + 0x28]
    profession = payload[body + 0x03]
    if status != CAPTIVE_STATUS_CODE or place_id != -1:
        raise ValueError("不是俘虏记录")
    if not (1 <= growth <= 200 and 1 <= level <= 200 and 1 <= loyalty_limit <= 200):
        raise ValueError("俘虏记录字段越界")
    ext = body + _COMMON_BODY_BYTES
    rescue_count = _u16(payload, body + 0x70)
    prison_fief_id = _i64(payload, ext + 2)
    fief_name, after_fief = read_utf(payload, ext + _PRISON_FIXED_BEFORE_FIEF_NAME)
    if after_fief + _PRISON_FIXED_AFTER_FIEF_NAME > len(payload):
        raise ValueError("俘虏记录尾部不完整")
    cooldown_base = _i64(payload, after_fief + 2)
    end = after_fief + _PRISON_FIXED_AFTER_FIEF_NAME
    record = {
        "id": captive_id,
        "idHex": f"{captive_id:016x}",
        "name": name,
        "professionCode": profession,
        "kind": _PROFESSION_LABELS.get(profession, f"职业{profession}"),
        "growth": growth,
        "level": level,
        "loyalty": loyalty,
        "loyaltyLimit": loyalty_limit,
        "status": status,
        "statusText": general_status_text_from_code(status),
        "persuadeCount": _u16(payload, body + 0x57),
        "rescueCount": rescue_count,
        "prisonFiefId": prison_fief_id,
        "prisonFiefName": fief_name,
        "persuadeCooldownBaseMillis": cooldown_base,
        "persuadeAvailableAtMillis": (
            cooldown_base + PERSUADE_COOLDOWN_MILLIS if cooldown_base > 0 else 0
        ),
        # The five u16 attributes at body+0x11..0x19 as the wire carries them.
        # Their labels (武力/智力/统帅 and two derived values) are not pinned
        # by the capture, so they are exposed raw rather than misnamed.
        "attributes": [_u16(payload, body + o) for o in (0x11, 0x13, 0x15, 0x17, 0x19)],
        "offset": offset,
    }
    return record, end


def parse_captive_table(payload: bytes, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    """Read ``u8 count`` and that many captive records; return them and the end."""

    if offset >= len(payload):
        raise ValueError("俘虏表缺少数量")
    count = payload[offset]
    position = offset + 1
    records: List[Dict[str, Any]] = []
    for _ in range(count):
        record, position = parse_captive_record(payload, position)
        records.append(record)
    return records, position


def recover_captives_from_8004(hexstr: str) -> List[Dict[str, Any]]:
    """Return the captive table embedded in a 0x8004 role-state payload.

    The block sits after the generals; where exactly depends on what precedes
    it, so it is located by evidence rather than offset: the first position at
    which a byte can be read as a count followed by exactly that many valid
    captive records wins.  A role state with no captives yields ``[]``.
    """

    payload = bytes.fromhex(hexstr)
    best: List[Dict[str, Any]] = []
    for position in range(0, max(0, len(payload) - 40)):
        count = payload[position]
        if count == 0 or count > 60:
            continue
        # Cheap pre-check before attempting a full table parse: the first
        # record must open with a plausible id and name.
        try:
            first_id = _i64(payload, position + 1)
            if first_id <= 0:
                continue
            name_len = _u16(payload, position + 9)
            if not 1 <= name_len <= 64:
                continue
            records, _end = parse_captive_table(payload, position)
        except (ValueError, IndexError, struct.error):
            continue
        if len(records) == count and len(records) > len(best):
            best = records
            break
    return best


def build_prisoner_info_payload(captive_id: int) -> bytes:
    """``0x1233`` - ask the price of persuading one captive."""

    return b"\x00" + struct.pack(">q", int(captive_id))


def parse_prisoner_info_response(payload: bytes) -> Dict[str, Any]:
    """``0x8233`` - the copper and gold price of one 劝降."""

    if len(payload) < 18:
        return {"parseError": f"0x8233 过短：{len(payload)}"}
    return {
        "status": payload[0],
        "copperCost": _i64(payload, 2),
        "goldCost": _i64(payload, 10),
    }


def build_persuade_payload(
    prison_fief_id: int,
    captive_id: int,
    pay_mode: int = PAY_MODE_COPPER,
) -> bytes:
    """``0x1234`` - 劝降 one captive held in ``prison_fief_id``."""

    return struct.pack(">qqB", int(prison_fief_id), int(captive_id), int(pay_mode))


def build_release_payload(prison_fief_id: int, captive_id: int) -> bytes:
    """``0x1236`` - 释放 one captive held in ``prison_fief_id``."""

    return struct.pack(">qqB", int(prison_fief_id), int(captive_id), 0)


def _skip_general_table(payload: bytes, offset: int) -> int:
    """Step over ``u8 count`` general records (id, name, 114-byte body)."""

    count = payload[offset]
    position = offset + 1
    for _ in range(count):
        _name, body = read_utf(payload, position + 8)
        position = body + _COMMON_BODY_BYTES
        if position > len(payload):
            raise ValueError("将领表越界")
    return position


def parse_persuade_response(payload: bytes) -> Dict[str, Any]:
    """``0x8234`` - outcome of a 劝降 plus the rebuilt tables.

    Success rebuilds generals first (the captive just became one), so the
    captive table has to be found past a generals table whose records carry
    no captive marker; failure sends the captive table alone.
    """

    if not payload:
        return {"success": False, "status": None, "message": "响应为空", "captives": None}
    status = payload[0]
    try:
        message, position = read_utf(payload, 1)
    except Exception:
        return {"success": False, "status": status, "message": payload[1:].hex(), "captives": None}
    result: Dict[str, Any] = {
        "success": status == 0,
        "status": status,
        "cooldown": status == PERSUADE_STATUS_COOLDOWN,
        "message": message,
        "captives": None,
        "generalCount": None,
    }
    if position >= len(payload):
        return result
    try:
        if status == 0:
            result["generalCount"] = payload[position]
            position = _skip_general_table(payload, position)
        captives, _end = parse_captive_table(payload, position)
        result["captives"] = captives
    except (ValueError, IndexError, struct.error) as error:
        result["tableParseError"] = str(error)
    return result


def parse_release_response(payload: bytes) -> Dict[str, Any]:
    """``0x8236`` - ``u8 status`` and the captives that remain."""

    if not payload:
        return {"success": False, "status": None, "captives": None}
    status = payload[0]
    result: Dict[str, Any] = {"success": status == 0, "status": status, "captives": None}
    if len(payload) > 1:
        try:
            captives, _end = parse_captive_table(payload, 1)
            result["captives"] = captives
        except (ValueError, IndexError, struct.error) as error:
            result["tableParseError"] = str(error)
    return result


def normalize_captive_policy(settings: Dict[str, Any]) -> Dict[str, Any]:
    """The two 常规-常用 rows: 释放 below one growth, 劝降 at or above another."""

    def flag(name: str, default: bool = False) -> bool:
        raw = settings.get(name, default)
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return bool(raw)

    def bound(name: str, default: int) -> int:
        try:
            value = int(settings.get(name, default))
        except (TypeError, ValueError):
            value = default
        return max(1, min(200, value))

    return {
        "releaseEnabled": flag("captiveRelease", False),
        "releaseBelowGrowth": bound("captiveReleaseBelowGrowth", 70),
        "persuadeEnabled": flag("captivePersuade", False),
        "persuadeAtOrAboveGrowth": bound("captivePersuadeGrowth", 70),
        # Gold is never spent automatically; the operator's own words were
        # "所有的劝降都选择使用铜钱".
        "payMode": PAY_MODE_COPPER,
    }


def plan_captive_actions(
    captives: Sequence[Dict[str, Any]],
    policy: Dict[str, Any],
    *,
    now_millis: int,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Decide, per captive, whether to 释放, 劝降, wait or keep.

    Growth is the operator's only stated criterion ("成长值低于70的全部释放，
    高于70的全部劝降"), and it is the field the game itself shows first.
    A captive whose growth falls between the two thresholds is kept; one on
    cooldown is reported as waiting with the time it becomes eligible.
    """

    planned: List[Dict[str, Any]] = []
    actions = 0
    for captive in sorted(captives, key=lambda row: int(row.get("id") or 0)):
        growth = int(captive.get("growth") or 0)
        base = {
            "captiveId": int(captive.get("id") or 0),
            "name": str(captive.get("name") or ""),
            "growth": growth,
            "level": int(captive.get("level") or 0),
            "kind": str(captive.get("kind") or ""),
            "prisonFiefId": int(captive.get("prisonFiefId") or 0),
        }
        if policy.get("persuadeEnabled") and growth >= int(policy["persuadeAtOrAboveGrowth"]):
            available_at = int(captive.get("persuadeAvailableAtMillis") or 0)
            if available_at > int(now_millis):
                planned.append({**base, "action": "wait", "reason": "劝降冷却中",
                                "availableAtMillis": available_at})
                continue
            if actions < limit:
                planned.append({**base, "action": "persuade", "payMode": policy["payMode"]})
                actions += 1
            else:
                planned.append({**base, "action": "defer", "reason": "本轮动作已达上限"})
            continue
        if policy.get("releaseEnabled") and growth < int(policy["releaseBelowGrowth"]):
            if actions < limit:
                planned.append({**base, "action": "release"})
                actions += 1
            else:
                planned.append({**base, "action": "defer", "reason": "本轮动作已达上限"})
            continue
        planned.append({**base, "action": "keep", "reason": "成长值不在释放/劝降范围"})
    return planned
