"""Verified Six Ministries settings and Hubu/Libu protocol rules.

Wire layouts come from the 2026-09-14 passive capture
(``passive_pcap_hotspot_20260914_111430``) and are documented in
``docs/reverse_reference/protocol/PROTOCOL_SPEC_户部礼部_20260914.md``.  Anything
the capture did not prove fails closed: unknown shapes raise instead of
being interpreted, and only the crop/delegation paths backed by capture
evidence may produce game writes.
"""

from __future__ import annotations

import re
import struct
from typing import Any, Optional

from ..contracts import load_behavior_contract
from ..protocol.wire import printable, read_utf


SIX_MINISTRIES_CONTRACT = load_behavior_contract()["sixMinistries"]
VERIFIED_MINISTRY_CROP = str(SIX_MINISTRIES_CONTRACT["verifiedCrop"])
MINISTRY_CROP_OPTIONS = ("金银花", "草药", "稻谷", "棉花")
HUBU_BATCH_PLANT_PAYLOAD = b"\x01\x00\x00\x00\x01"
VERIFIED_GARDEN_PLOT_COUNT = 10
OCCUPIED_GARDEN_RECORD_EXTRA_BYTES = 25

# 0xe320 layout (flows 049 = five occupied plots, 062 = all empty; device
# account 176 = named variant; account 202 = plot 1 empty between occupied
# plots 0 and 2): a fixed 24B header, then a u8-length UTF-8 fief name
# (empty for account 202, "乌吉" for 176), then a u8 plot count, then one
# entry per plot IN PLOT ORDER — a 32B record where the plot is occupied,
# a 7B zero-body entry where it is empty — then a 62B tail.  Flow 049's
# occupied plots happen to be 0-4 contiguous, which looks identical under
# an "occupied first, empties last" reading; account 202's gap at plot 1
# is what proved the entries are in place.
# Total = 26 + nameLen + 32×occupied + 7×(plots−occupied) + 62.
HUBU_GARDEN_FIXED_HEADER_BYTES = 24
HUBU_GARDEN_TAIL_BYTES = 62
HUBU_GARDEN_MIN_BYTES = (
    HUBU_GARDEN_FIXED_HEADER_BYTES + 1 + 1 + HUBU_GARDEN_TAIL_BYTES
)
HUBU_OCCUPIED_PLOT_BYTES = 32
HUBU_EMPTY_PLOT_BYTES = 7
HUBU_HARVEST_SUCCESS_MARKER = "采摘成功"
HUBU_HARVEST_GAIN_PATTERN = re.compile(r"俸禄\+(\d+)株")

# 礼部 task list (0xe340) and delegation (0xe342) layouts; only the state,
# duration and remaining-second fields of the 32B task tail are verified.
LIBU_TASK_TAIL_BYTES = 32
LIBU_TASK_STATES = (0, 1)
LIBU_DELEGATE_SUCCESS_MARKER = "操作成功"

# 吏部详情 (0xe301) incumbent records.  The delegation state is the u32 eight
# bytes before the end of the attribute block: 0 when the official is idle,
# otherwise the id of the 礼部 task they are running.  This is anchored by
# the invariant ten-byte attribute tail ``00 ?? busy(4) 00 salary(2) 00``
# seen on every incumbent record in flows 071/088/089/099/115, where the two
# delegated officials (束边→任务1, 柯温→任务5) show exactly their task ids and
# all nine never-delegated records show 0.
MINISTRY_OFFICIAL_MARKER = 0x30
MINISTRY_OFFICIAL_ATTRS_MIN_BYTES = 30
MINISTRY_OFFICIAL_ATTRS_MAX_BYTES = 40


def normalize_ministry_settings(body: dict[str, Any]) -> dict[str, Any]:
    settings = dict(body.get("settings") or body)
    crop = str(settings.get("crop") or VERIFIED_MINISTRY_CROP).strip()
    if crop not in MINISTRY_CROP_OPTIONS:
        crop = VERIFIED_MINISTRY_CROP
    return {
        "cropEnabled": bool(settings.get("cropEnabled", True)),
        "crop": crop,
        "highPriority": bool(settings.get("highPriority", True)),
        "stealEnabled": bool(settings.get("stealEnabled", True)),
        "courtesyEnabled": bool(settings.get("courtesyEnabled", True)),
        "salaryRefresh": bool(settings.get("salaryRefresh", True)),
    }


def ministry_planting_allowed(settings: dict[str, Any]) -> bool:
    """Return true only for the one write path backed by capture evidence."""
    return bool(
        SIX_MINISTRIES_CONTRACT["onlyVerifiedPlantingMaySend"]
        and settings.get("cropEnabled")
        and str(settings.get("crop") or "") == VERIFIED_MINISTRY_CROP
    )


def ministry_courtesy_allowed(settings: dict[str, Any]) -> bool:
    """Return true when 礼部任务委派 may produce game writes."""
    return bool(
        SIX_MINISTRIES_CONTRACT.get("verifiedCourtesyDelegateMaySend")
        and settings.get("courtesyEnabled")
    )


def unconfirmed_ministry_actions(settings: dict[str, Any]) -> list[str]:
    """Describe saved controls which must never produce game writes yet."""
    actions = []
    if settings.get("stealEnabled"):
        actions.append("偷菜")
    if settings.get("salaryRefresh"):
        actions.append("俸禄刷新")
    return actions


def build_hubu_status_query_payload() -> bytes:
    return b""


def build_hubu_batch_plant_payload(
    crop_name: str = VERIFIED_MINISTRY_CROP,
) -> bytes:
    if (
        not SIX_MINISTRIES_CONTRACT["onlyVerifiedPlantingMaySend"]
        or str(crop_name or "").strip() != VERIFIED_MINISTRY_CROP
    ):
        raise RuntimeError(f"{crop_name}协议尚未确认；禁止发送批量种菜请求")
    return HUBU_BATCH_PLANT_PAYLOAD


def build_hubu_harvest_payload(plot_index: int, host_id: int) -> bytes:
    """0x6324: ``u8 plotIndex, i64 hostId`` (flows 052/054/056/058/059)."""
    plot_index = int(plot_index)
    host_id = int(host_id)
    if not 0 <= plot_index < VERIFIED_GARDEN_PLOT_COUNT:
        raise RuntimeError(f"采摘坑位异常：{plot_index}")
    if host_id <= 0:
        raise RuntimeError("采摘缺少角色 ID")
    return struct.pack(">Bq", plot_index, host_id)


def _parse_occupied_plot_record(record: bytes) -> dict[str, Any]:
    return {
        "plotIndex": record[0],
        "occupied": True,
        "cropId": int.from_bytes(record[1:3], "big"),
        "totalSeconds": int.from_bytes(record[3:7], "big"),
        "remainingSeconds": int.from_bytes(record[7:11], "big"),
        "percent": record[12],
        "plantCount": int.from_bytes(record[13:15], "big"),
    }


def parse_hubu_garden_status(payload: bytes) -> dict[str, Any]:
    """Parse 0xe320 per plot and fail closed on any unverified shape.

    Rejections carry a bounded fingerprint (length + full hex for payloads
    up to 512 bytes, otherwise the first 48 bytes) so a layout variant on
    some other account can be diagnosed from the ministry state message
    alone instead of a bare "菜地数量变化" with no evidence.
    """
    try:
        return _parse_hubu_garden_status(payload)
    except RuntimeError as error:
        detail = (
            payload.hex()
            if len(payload) <= 512
            else payload[:48].hex() + "…"
        )
        raise RuntimeError(
            f"{error} [0xe320 len={len(payload)} hex={detail}]"
        ) from error


def _parse_hubu_garden_status(payload: bytes) -> dict[str, Any]:
    if len(payload) < HUBU_GARDEN_MIN_BYTES:
        raise RuntimeError("0xe320 响应过短")
    # 固定 24B 头之后是 u8 长度的 UTF-8 封地名，再是 u8 总坑数——把
    # plot_count 当 [24:26] u16 读，碰到带名字的账号（176="乌吉"）就会
    # 读出 0x06E4=1764 这样的假数量。
    name_length = payload[24]
    name_end = 25 + name_length
    if name_end + 1 > len(payload):
        raise RuntimeError("0xe320 封地名长度越界")
    try:
        garden_name = payload[25:name_end].decode("utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeError(f"0xe320 封地名不是 UTF-8：{error}") from error
    plot_count = payload[name_end]
    if plot_count != VERIFIED_GARDEN_PLOT_COUNT:
        raise RuntimeError(f"0xe320 菜地数量变化：{plot_count}")
    header_bytes = name_end + 1
    empty_garden_size = (
        header_bytes
        + plot_count * HUBU_EMPTY_PLOT_BYTES
        + HUBU_GARDEN_TAIL_BYTES
    )
    extra = len(payload) - empty_garden_size
    if extra < 0 or extra % OCCUPIED_GARDEN_RECORD_EXTRA_BYTES != 0:
        raise RuntimeError(f"0xe320 尚未确认的记录结构：{len(payload)}B")
    occupied_count = extra // OCCUPIED_GARDEN_RECORD_EXTRA_BYTES
    unlocked_count = int.from_bytes(payload[19:21], "big")
    if not 0 <= occupied_count <= unlocked_count <= plot_count:
        raise RuntimeError(
            f"0xe320 已占用菜地数量异常：{occupied_count}/{unlocked_count}"
        )
    plots: list[dict[str, Any]] = []
    position = header_bytes
    previous_index = -1
    remaining_occupied = occupied_count
    for _ in range(plot_count):
        plot_index = payload[position]
        if plot_index <= previous_index or plot_index >= plot_count:
            raise RuntimeError(f"0xe320 坑序号异常：{plot_index}")
        previous_index = plot_index
        empty_body = payload[position + 1:position + HUBU_EMPTY_PLOT_BYTES]
        if empty_body == b"\x00" * (HUBU_EMPTY_PLOT_BYTES - 1):
            plots.append({"plotIndex": plot_index, "occupied": False})
            position += HUBU_EMPTY_PLOT_BYTES
            continue
        # 占用记录的 cropId/totalSeconds 不会全为零（生长中的作物必有
        # 总时长），所以"索引后 6B 全零"只可能是空闲条目；占用额度耗尽
        # 或尾块对不齐时下面的计数与长度检查会失败关闭。
        if remaining_occupied <= 0:
            raise RuntimeError("0xe320 空闲坑条目含有未确认数据")
        record = payload[position:position + HUBU_OCCUPIED_PLOT_BYTES]
        plots.append(_parse_occupied_plot_record(record))
        remaining_occupied -= 1
        position += HUBU_OCCUPIED_PLOT_BYTES
    if remaining_occupied:
        raise RuntimeError(
            f"0xe320 占用坑数量与记录结构不符：剩余{remaining_occupied}"
        )
    if position + HUBU_GARDEN_TAIL_BYTES != len(payload):
        raise RuntimeError(
            f"0xe320 尾块长度异常：{len(payload) - position}B"
        )
    return {
        "plotCount": plot_count,
        "unlockedCount": unlocked_count,
        "occupiedCount": occupied_count,
        # Locked plots are listed as empty entries on the wire (flow 049
        # lists plots 5-9 while only five are unlocked), so the actionable
        # empty count is the unlocked remainder, not the listed one.
        "emptyCount": unlocked_count - occupied_count,
        "level": int.from_bytes(payload[0:4], "big"),
        "salaryPool": int.from_bytes(payload[12:16], "big"),
        "gardenName": garden_name,
        "plots": plots,
        "tailHex": payload[position:].hex(),
    }


def parse_hubu_harvest_response(payload: bytes) -> dict[str, Any]:
    """Parse 0xe324; offsets after the UTF message are derived, never fixed."""
    if not payload:
        return {"success": False, "status": None, "message": "响应为空"}
    status = struct.unpack(">b", payload[:1])[0]
    try:
        message, offset = read_utf(payload, 1)
    except Exception:
        message, offset = printable(payload, 300), 1
    result: dict[str, Any] = {
        "success": status == 0 and HUBU_HARVEST_SUCCESS_MARKER in message,
        "status": status,
        "message": message,
    }
    if status != 0:
        result["remainingHex"] = payload[offset:].hex()[:4096]
        return result
    # status + UTF + i64 hostId echo + u32 newPool + 32B cleared plot record.
    if len(payload) - offset != 8 + 4 + HUBU_OCCUPIED_PLOT_BYTES:
        raise RuntimeError(
            f"0xe324 成功回执结构异常：{len(payload) - offset}B"
        )
    host_id = struct.unpack(">q", payload[offset:offset + 8])[0]
    new_pool = int.from_bytes(payload[offset + 8:offset + 12], "big")
    record = payload[offset + 12:]
    gain_match = HUBU_HARVEST_GAIN_PATTERN.search(message)
    result.update({
        "hostId": host_id,
        "newPool": new_pool,
        "plotIndex": record[0],
        "gain": int(gain_match.group(1)) if gain_match else None,
    })
    return result


def parse_hubu_plant_response(payload: bytes) -> dict[str, Any]:
    """Parse 0xe328; offsets after the UTF message are derived, never fixed."""
    if not payload:
        return {"success": False, "status": None, "message": "响应为空"}
    status = struct.unpack(">b", payload[:1])[0]
    try:
        message, offset = read_utf(payload, 1)
    except Exception:
        message, offset = printable(payload, 300), 1
    result: dict[str, Any] = {
        "success": status == 0,
        "status": status,
        "message": message,
    }
    if status != 0:
        result["remainingHex"] = payload[offset:].hex()[:4096]
        return result
    # u32 newPool + u8 recordCount + N×32B new plot records + 6B tail
    # (flows 065/067/068 all carry exactly one record).
    remaining = len(payload) - offset
    if remaining < 5:
        raise RuntimeError("0xe328 成功回执过短")
    new_pool = int.from_bytes(payload[offset:offset + 4], "big")
    record_count = payload[offset + 4]
    if remaining != 5 + record_count * HUBU_OCCUPIED_PLOT_BYTES + 6:
        raise RuntimeError(f"0xe328 成功回执结构异常：{remaining}B")
    records = []
    position = offset + 5
    for _ in range(record_count):
        records.append(
            _parse_occupied_plot_record(
                payload[position:position + HUBU_OCCUPIED_PLOT_BYTES]
            )
        )
        position += HUBU_OCCUPIED_PLOT_BYTES
    result.update({"newPool": new_pool, "records": records})
    return result


def build_libu_task_list_payload() -> bytes:
    return b""


def _parse_libu_task_tail(tail: bytes) -> dict[str, Any]:
    state = tail[10]
    if state not in LIBU_TASK_STATES:
        raise RuntimeError(f"礼部任务状态尚未确认：{state}")
    return {
        "state": state,
        "durationSeconds": int.from_bytes(tail[11:15], "big"),
        "remainingSeconds": int.from_bytes(tail[15:19], "big"),
        "tailHex": tail.hex(),
    }


def parse_libu_task_list(payload: bytes) -> dict[str, Any]:
    """Parse 0xe340 (flows 086/090/096); unverified tail bytes stay opaque."""
    if len(payload) < 34:
        raise RuntimeError("0xe340 响应过短")
    task_count = payload[33]
    position = 34
    tasks: list[dict[str, Any]] = []
    for _ in range(task_count):
        if position + 8 > len(payload):
            raise RuntimeError("0xe340 任务记录截断")
        task_id = int.from_bytes(payload[position:position + 4], "big")
        template_id = int.from_bytes(payload[position + 4:position + 6], "big")
        try:
            name, offset = read_utf(payload, position + 6)
        except Exception as error:
            raise RuntimeError(f"0xe340 任务名解析失败：{error}") from error
        tail = payload[offset:offset + LIBU_TASK_TAIL_BYTES]
        if len(tail) != LIBU_TASK_TAIL_BYTES:
            raise RuntimeError("0xe340 任务记录尾部截断")
        tasks.append({
            "taskId": task_id,
            "templateId": template_id,
            "name": name,
            **_parse_libu_task_tail(tail),
        })
        position = offset + LIBU_TASK_TAIL_BYTES
    trailing = len(payload) - position
    if trailing > 1 or (trailing == 1 and payload[position] != 0):
        raise RuntimeError(f"0xe340 尾部含有未确认数据：{trailing}B")
    return {
        "salaryPool": int.from_bytes(payload[5:7], "big"),
        "refreshAtMillis": struct.unpack(">q", payload[8:16])[0],
        "resetAtMillis": struct.unpack(">q", payload[20:28])[0],
        "tasks": tasks,
    }


def build_libu_delegate_payload(task_id: int, official_id: int) -> bytes:
    """0x6342: ``u32 taskId, u8 01, i64 officialId`` (flows 091/094)."""
    task_id = int(task_id)
    official_id = int(official_id)
    if task_id <= 0:
        raise RuntimeError("礼部委派缺少任务 ID")
    if official_id <= 0:
        raise RuntimeError("礼部委派缺少文官 ID")
    return struct.pack(">IBq", task_id, 1, official_id)


def parse_libu_delegate_response(
    payload: bytes,
    *,
    task_id: int,
    official_id: int,
) -> dict[str, Any]:
    """Parse 0xe342; success requires status 0 and matching echoes."""
    if not payload:
        return {"success": False, "status": None, "message": "响应为空"}
    status = struct.unpack(">b", payload[:1])[0]
    try:
        message, offset = read_utf(payload, 1)
    except Exception:
        message, offset = printable(payload, 300), 1
    result: dict[str, Any] = {
        "success": False,
        "status": status,
        "message": message,
    }
    if status != 0:
        result["remainingHex"] = payload[offset:].hex()[:4096]
        return result
    # UTF + task record (u32 id, u16 template, UTF name, 32B tail)
    # + u32 taskId echo + u8 01 + i64 officialId echo + u8 (flows 091/094).
    if offset + 8 > len(payload):
        raise RuntimeError("0xe342 回执截断")
    record_task_id = int.from_bytes(payload[offset:offset + 4], "big")
    template_id = int.from_bytes(payload[offset + 4:offset + 6], "big")
    try:
        name, name_end = read_utf(payload, offset + 6)
    except Exception as error:
        raise RuntimeError(f"0xe342 任务名解析失败：{error}") from error
    tail = payload[name_end:name_end + LIBU_TASK_TAIL_BYTES]
    if len(tail) != LIBU_TASK_TAIL_BYTES:
        raise RuntimeError("0xe342 任务记录尾部截断")
    position = name_end + LIBU_TASK_TAIL_BYTES
    if len(payload) - position != 4 + 1 + 8 + 1:
        raise RuntimeError(
            f"0xe342 回执尾部结构异常：{len(payload) - position}B"
        )
    echo_task_id = int.from_bytes(payload[position:position + 4], "big")
    echo_official_id = struct.unpack(
        ">q", payload[position + 5:position + 13]
    )[0]
    if (
        record_task_id != int(task_id)
        or echo_task_id != int(task_id)
        or echo_official_id != int(official_id)
    ):
        raise RuntimeError("0xe342 回显与委派请求不一致")
    result.update({
        "success": LIBU_DELEGATE_SUCCESS_MARKER in message,
        "task": {
            "taskId": record_task_id,
            "templateId": template_id,
            "name": name,
            **_parse_libu_task_tail(tail),
        },
        "taskId": echo_task_id,
        "officialId": echo_official_id,
    })
    return result


def build_ministry_officials_payload() -> bytes:
    return b""


def _scan_official_record_start(payload: bytes, position: int) -> Optional[int]:
    """Next plausible ``i64 id + 0x30 + u8 + UTF name`` record start."""
    scan = position
    while scan + 12 <= len(payload):
        official_id = struct.unpack(">q", payload[scan:scan + 8])[0]
        if (
            payload[scan + 8] == MINISTRY_OFFICIAL_MARKER
            and 0 < official_id < 0x1_0000_0000
        ):
            name_length = int.from_bytes(payload[scan + 10:scan + 12], "big")
            if (
                2 <= name_length <= 30
                and scan + 12 + name_length <= len(payload)
            ):
                try:
                    name = payload[scan + 12:scan + 12 + name_length].decode(
                        "utf-8"
                    )
                except UnicodeDecodeError:
                    name = ""
                if name and all("一" <= char <= "鿿" for char in name):
                    return scan
        scan += 1
    return None


def _official_record_header(payload: bytes, position: int) -> tuple[int, str, int]:
    if position + 12 > len(payload):
        raise RuntimeError("0xe301 文官记录截断")
    official_id = struct.unpack(">q", payload[position:position + 8])[0]
    if official_id <= 0:
        raise RuntimeError("0xe301 文官 ID 异常")
    if payload[position + 8] != MINISTRY_OFFICIAL_MARKER:
        raise RuntimeError("0xe301 文官记录标记异常")
    try:
        name, attr_start = read_utf(payload, position + 10)
    except Exception as error:
        raise RuntimeError(f"0xe301 文官名解析失败：{error}") from error
    if not name:
        raise RuntimeError("0xe301 文官名为空")
    return official_id, name, attr_start


def _incumbent_busy_task_id(attrs: bytes, name: str) -> int:
    if not (
        MINISTRY_OFFICIAL_ATTRS_MIN_BYTES
        <= len(attrs)
        <= MINISTRY_OFFICIAL_ATTRS_MAX_BYTES
    ):
        raise RuntimeError(
            f"0xe301 文官{name}属性长度尚未确认：{len(attrs)}B"
        )
    # Ten-byte tail ``00 ?? busy(4) 00 salary(2) 00``; the anchors are what
    # make the busy read trustworthy, so any deviation fails closed.
    if attrs[-10] != 0 or attrs[-4] != 0 or attrs[-1] != 0:
        raise RuntimeError(f"0xe301 文官{name}属性尾块尚未确认")
    return int.from_bytes(attrs[-8:-4], "big")


def parse_ministry_officials(payload: bytes) -> dict[str, Any]:
    """Parse 0xe301 incumbent officials and their delegation state.

    Only the incumbent section is interpreted; the candidate section is
    walked solely to prove the frame was understood end to end.  Any
    unverified shape raises so the caller skips delegation for the tick
    instead of guessing whether an official is idle.
    """
    if len(payload) < 15:
        raise RuntimeError("0xe301 响应过短")
    incumbent_count = payload[14]
    starts: list[int] = []
    scan = 15
    while True:
        found = _scan_official_record_start(payload, scan)
        if found is None:
            break
        starts.append(found)
        scan = found + 12
    if len(starts) < incumbent_count:
        raise RuntimeError("0xe301 在职文官记录数量不足")
    incumbent_starts = starts[:incumbent_count]
    candidate_starts = starts[incumbent_count:]
    officials: list[dict[str, Any]] = []
    for index, start in enumerate(incumbent_starts):
        official_id, name, attr_start = _official_record_header(payload, start)
        if index + 1 < len(incumbent_starts):
            end = incumbent_starts[index + 1]
        elif candidate_starts:
            end = candidate_starts[0] - 1
        else:
            end = len(payload) - 1
        attrs = payload[attr_start:end]
        busy_task_id = _incumbent_busy_task_id(attrs, name)
        officials.append({
            "officialId": official_id,
            "name": name,
            "busyTaskId": busy_task_id,
            "idle": busy_task_id == 0,
        })
    count_byte_position = (
        candidate_starts[0] - 1 if candidate_starts else len(payload) - 1
    )
    if count_byte_position < 15:
        raise RuntimeError("0xe301 候选文官计数缺失")
    candidate_count = payload[count_byte_position]
    if candidate_count != len(candidate_starts):
        raise RuntimeError("0xe301 候选文官数量不符")
    for index, start in enumerate(candidate_starts):
        _official_record_header(payload, start)
        end = (
            candidate_starts[index + 1]
            if index + 1 < len(candidate_starts)
            else len(payload)
        )
        if end <= start:
            raise RuntimeError("0xe301 候选文官记录边界异常")
    return {
        "salaryPool": int.from_bytes(payload[10:14], "big"),
        "officials": officials,
        "candidateCount": candidate_count,
    }
