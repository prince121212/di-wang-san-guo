"""Verified Six Ministries settings and Hubu planting protocol rules."""

from __future__ import annotations

import struct
from typing import Any

from ..contracts import load_behavior_contract
from ..protocol.wire import printable, read_utf


SIX_MINISTRIES_CONTRACT = load_behavior_contract()["sixMinistries"]
VERIFIED_MINISTRY_CROP = str(SIX_MINISTRIES_CONTRACT["verifiedCrop"])
MINISTRY_CROP_OPTIONS = ("金银花", "草药", "稻谷", "棉花")
HUBU_BATCH_PLANT_PAYLOAD = b"\x01\x00\x00\x00\x01"
VERIFIED_EMPTY_GARDEN_SIZE = 158
VERIFIED_GARDEN_PLOT_COUNT = 10
OCCUPIED_GARDEN_RECORD_EXTRA_BYTES = 25


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


def unconfirmed_ministry_actions(settings: dict[str, Any]) -> list[str]:
    """Describe saved controls which must never produce game writes yet."""
    actions = []
    if settings.get("stealEnabled"):
        actions.append("偷菜")
    if settings.get("courtesyEnabled"):
        actions.append("礼部任务")
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


def parse_hubu_garden_status(payload: bytes) -> dict[str, int]:
    """Parse the two captured 0xe320 garden shapes and fail closed otherwise."""
    if len(payload) < VERIFIED_EMPTY_GARDEN_SIZE:
        raise RuntimeError("0xe320 响应过短")
    plot_count = payload[25]
    if plot_count != VERIFIED_GARDEN_PLOT_COUNT:
        raise RuntimeError(f"0xe320 菜地数量变化：{plot_count}")
    extra = len(payload) - VERIFIED_EMPTY_GARDEN_SIZE
    if extra < 0 or extra % OCCUPIED_GARDEN_RECORD_EXTRA_BYTES != 0:
        raise RuntimeError(f"0xe320 尚未确认的记录结构：{len(payload)}B")
    occupied_count = extra // OCCUPIED_GARDEN_RECORD_EXTRA_BYTES
    if not 0 <= occupied_count <= plot_count:
        raise RuntimeError(
            f"0xe320 已占用菜地数量异常：{occupied_count}/{plot_count}"
        )
    return {
        "plotCount": plot_count,
        "occupiedCount": occupied_count,
        "emptyCount": plot_count - occupied_count,
    }


def parse_hubu_plant_response(payload: bytes) -> dict[str, Any]:
    """Parse the desktop-authoritative status + UTF reply used by 0xe328."""
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
