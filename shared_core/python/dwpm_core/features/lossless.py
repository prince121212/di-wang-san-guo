"""Lossless-battle status, catalog, lineup and receipt rules."""

from __future__ import annotations

import re
import struct
from typing import Any, Dict

from ..contracts import load_behavior_contract
from ..protocol.wire import printable, read_utf


LOSSLESS_CONTRACT = load_behavior_contract()["lossless"]
LOSSLESS_MODE_CONTRACT = LOSSLESS_CONTRACT["modes"]
LOSSLESS_GUARD_CONTRACT = LOSSLESS_CONTRACT["level10Guard"]
LOSSLESS_DAILY_LIMIT = int(LOSSLESS_CONTRACT["serverDailyLimit"])
LOSSLESS_MIN_LEVEL = int(LOSSLESS_CONTRACT["minimumLevel"])
LOSSLESS_MAX_LEVEL = int(LOSSLESS_CONTRACT["maximumLevel"])
LOSSLESS_MODE_NAMES = {
    int(LOSSLESS_MODE_CONTRACT["cooldown"]): "冷却中",
    **{
        int(value): "可出征"
        for value in LOSSLESS_MODE_CONTRACT["ready"]
    },
    int(LOSSLESS_MODE_CONTRACT["fighting"]): "战斗中",
    int(LOSSLESS_MODE_CONTRACT["dailyDone"]): "今日次数已用完",
}
LOSSLESS_STAGE_NAMES = list(LOSSLESS_CONTRACT["stageNames"])


def lossless_level_number(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        level = value
    else:
        match = re.search(r"(\d+)", str(value or "").strip())
        if not match:
            raise RuntimeError(f"无损等级无效：{value}")
        level = int(match.group(1))
    if not LOSSLESS_MIN_LEVEL <= level <= LOSSLESS_MAX_LEVEL:
        raise RuntimeError(f"无损等级超出范围：{value}")
    return level


def lossless_status_phase(status: Dict[str, Any]) -> str:
    if status.get("parseError"):
        return "error"
    if status.get("settlementPending"):
        return "settlement"
    mode = status.get("mode")
    remaining = int(status.get("remainingAttempts") or 0)
    if remaining <= 0 or mode == int(LOSSLESS_MODE_CONTRACT["dailyDone"]):
        return "daily_done"
    if mode == int(LOSSLESS_MODE_CONTRACT["cooldown"]):
        return "cooldown"
    if mode == int(LOSSLESS_MODE_CONTRACT["fighting"]):
        return "fighting"
    if mode in {int(value) for value in LOSSLESS_MODE_CONTRACT["ready"]}:
        return "ready"
    return "unknown"


def parse_lossless_status(payload: bytes) -> Dict[str, Any]:
    output: Dict[str, Any] = {
        "rawHex": payload.hex(),
        "state": None,
        "mode": None,
        "stateName": "未知",
        "dispatchable": False,
    }
    if len(payload) < 13:
        output["parseError"] = f"0x8900 公共字段不足：{len(payload)}/13"
        return output
    action_timer_ms = struct.unpack(">q", payload[0:8])[0]
    mode = int(payload[8])
    remaining_attempts = int(payload[9])
    progress_code = int(payload[10])
    status_flag = int(payload[11])
    settlement_pending = bool(payload[12])
    output.update(
        {
            "actionTimerMs": max(0, action_timer_ms),
            "actionTimerSec": max(0, action_timer_ms // 1000),
            "cooldownMs": 0,
            "cooldownSec": 0,
            "mode": mode,
            "remainingAttempts": remaining_attempts,
            "usedAttempts": max(0, LOSSLESS_DAILY_LIMIT - remaining_attempts),
            "state": mode,
            "progressCode": progress_code,
            "statusFlag": status_flag,
            "settlementPending": settlement_pending,
            "auxFlags": [progress_code, status_flag],
        }
    )

    if mode == 0:
        if len(payload) < 25:
            output["tailParseError"] = (
                f"0x8900 冷却字段不足：{len(payload)}/25"
            )
        else:
            cooldown_ms = struct.unpack(">q", payload[13:21])[0]
            output.update(
                {
                    "cooldownMs": max(0, cooldown_ms),
                    "cooldownSec": max(0, cooldown_ms // 1000),
                    "reopenCost": struct.unpack(">i", payload[21:25])[0],
                    "parsedBytes": 25,
                }
            )
            if len(payload) > 25:
                output["tailHex"] = payload[25:].hex()
    elif len(payload) < 23:
        output["tailParseError"] = f"0x8900 关卡字段不足：{len(payload)}/23"
    else:
        selected_level_index = struct.unpack(">q", payload[13:21])[0]
        stage_id = struct.unpack(">h", payload[21:23])[0]
        output.update(
            {
                "selectedLevelIndex": (
                    None if selected_level_index < 0 else selected_level_index
                ),
                "selectedLevel": (
                    None if selected_level_index < 0 else selected_level_index + 1
                ),
                "stageId": None if stage_id < 0 else stage_id,
                "stageIdHex": None if stage_id < 0 else f"{stage_id & 0xffff:04x}",
                "parsedBytes": 23,
            }
        )
    if mode == 3 and len(payload) > 23:
        position = 23
        try:
            output["activeLevel"] = int(payload[position])
            position += 1
            active_level_name, position = read_utf(payload, position)
            output["activeLevelName"] = active_level_name
            output["parsedBytes"] = position
            if position != len(payload):
                output["tailHex"] = payload[position:].hex()
        except Exception as error:
            output["tailParseError"] = str(error)

    phase = lossless_status_phase(output)
    output.update(
        {
            "phase": phase,
            "stateName": {
                "settlement": "待结算",
                "daily_done": "今日次数已用完",
            }.get(phase, LOSSLESS_MODE_NAMES.get(mode, f"未知状态({mode})")),
            "dispatchable": phase == "ready",
        }
    )
    return output


def parse_lossless_catalog(payload: bytes) -> Dict[str, Any]:
    output: Dict[str, Any] = {
        "rawHex": payload.hex()[:8192],
        "levels": [],
        "stageById": {},
        "textPreview": printable(payload, 1600),
    }
    if len(payload) < 4:
        output["parseError"] = "0x8904 数据不足"
        return output
    position = 0
    try:
        level_count = struct.unpack(">i", payload[position:position + 4])[0]
        position += 4
        if not 0 <= level_count <= 20:
            raise ValueError(f"等级数量异常：{level_count}")
        levels = []
        stage_by_id = {}
        for _ in range(level_count):
            if position + 9 > len(payload):
                raise ValueError(f"等级头越界：pos={position}")
            level_index = struct.unpack(">q", payload[position:position + 8])[0]
            position += 8
            level_number = int(payload[position])
            position += 1
            level_name, position = read_utf(payload, position)
            if position + 4 > len(payload):
                raise ValueError(
                    f"阶段数量越界：level={level_number} pos={position}"
                )
            stage_count = struct.unpack(">i", payload[position:position + 4])[0]
            position += 4
            if not 0 <= stage_count <= 20:
                raise ValueError(
                    f"阶段数量异常：level={level_number} count={stage_count}"
                )
            stages = []
            for stage_index in range(stage_count):
                if position + 2 > len(payload):
                    raise ValueError(
                        f"阶段编号越界：level={level_number} "
                        f"index={stage_index}"
                    )
                stage_id = struct.unpack(">H", payload[position:position + 2])[0]
                position += 2
                stage_name, position = read_utf(payload, position)
                stage = {
                    "stageIndex": stage_index,
                    "stageNumber": stage_index + 1,
                    "stageId": stage_id,
                    "stageIdHex": f"{stage_id:04x}",
                    "name": stage_name,
                }
                stages.append(stage)
                stage_by_id[str(stage_id)] = {
                    **stage,
                    "levelIndex": level_index,
                    "level": level_number,
                    "levelName": level_name,
                }
            levels.append(
                {
                    "levelIndex": level_index,
                    "level": level_number,
                    "name": level_name,
                    "stages": stages,
                }
            )
        output.update(
            {
                "levelCount": level_count,
                "levels": levels,
                "stageById": stage_by_id,
                "parsedBytes": position,
            }
        )
        if position != len(payload):
            output["tailHex"] = payload[position:].hex()
    except Exception as error:
        output["parseError"] = str(error)
    return output


def parse_lossless_lineup(payload: bytes) -> Dict[str, Any]:
    output: Dict[str, Any] = {
        "rawHex": payload.hex()[:8192],
        "enemies": [],
        "textPreview": printable(payload, 1600),
    }
    if len(payload) < 3:
        output["parseError"] = "0x8906 数据不足"
        return output
    position = 0
    try:
        status = int(payload[position])
        position += 1
        stage_id = struct.unpack(">H", payload[position:position + 2])[0]
        position += 2
        level_name, position = read_utf(payload, position)
        stage_name, position = read_utf(payload, position)
        if position + 4 > len(payload):
            raise ValueError("敌军数量越界")
        enemy_count = struct.unpack(">i", payload[position:position + 4])[0]
        position += 4
        if not 0 <= enemy_count <= 50:
            raise ValueError(f"敌军数量异常：{enemy_count}")
        enemies = []
        for index in range(enemy_count):
            general_name, position = read_utf(payload, position)
            if position + 10 > len(payload):
                raise ValueError(f"敌军字段越界：index={index} pos={position}")
            unknown_a = struct.unpack(">i", payload[position:position + 4])[0]
            position += 4
            unknown_b = struct.unpack(">H", payload[position:position + 2])[0]
            position += 2
            unknown_c = struct.unpack(">i", payload[position:position + 4])[0]
            position += 4
            soldier_type, position = read_utf(payload, position)
            if position + 4 > len(payload):
                raise ValueError(f"敌军兵力越界：index={index} pos={position}")
            soldier_count = struct.unpack(">i", payload[position:position + 4])[0]
            position += 4
            enemies.append(
                {
                    "index": index,
                    "position": index + 1,
                    "generalName": general_name,
                    "soldierType": soldier_type,
                    "soldierCount": soldier_count,
                    "unknownA": unknown_a,
                    "unknownB": unknown_b,
                    "unknownC": unknown_c,
                }
            )
        output.update(
            {
                "status": status,
                "success": status == 0,
                "stageId": stage_id,
                "stageIdHex": f"{stage_id:04x}",
                "levelName": level_name,
                "stageName": stage_name,
                "enemyCount": enemy_count,
                "enemies": enemies,
                "parsedBytes": position,
            }
        )
        if position != len(payload):
            output["tailHex"] = payload[position:].hex()
    except Exception as error:
        output["parseError"] = str(error)
    return output


def evaluate_level10_guard_lineup(lineup: Dict[str, Any]) -> Dict[str, Any]:
    enemies = list(lineup.get("enemies") or [])
    chariot_tokens = tuple(
        str(value) for value in LOSSLESS_GUARD_CONTRACT["chariotTokens"]
    )
    catapult_token = str(LOSSLESS_GUARD_CONTRACT["catapultToken"])
    chariot_indices = [
        index
        for index, enemy in enumerate(enemies)
        if any(
            token in str(enemy.get("soldierType") or "")
            for token in chariot_tokens
        )
    ]
    catapult_indices = [
        index
        for index, enemy in enumerate(enemies)
        if catapult_token in str(enemy.get("soldierType") or "")
    ]
    other_chariot_indices = [
        index for index in chariot_indices if index not in catapult_indices
    ]
    last_chariot_is_catapult = (
        bool(chariot_indices) and chariot_indices[-1] in catapult_indices
    )
    qualified = (
        len(enemies) == int(LOSSLESS_GUARD_CONTRACT["enemyCount"])
        and len(chariot_indices)
        >= int(LOSSLESS_GUARD_CONTRACT["minimumChariots"])
        and bool(catapult_indices)
        and last_chariot_is_catapult
    )
    if len(enemies) != int(LOSSLESS_GUARD_CONTRACT["enemyCount"]):
        reason = (
            f"敌军数量不是{LOSSLESS_GUARD_CONTRACT['enemyCount']}，"
            f"而是{len(enemies)}"
        )
    elif len(chariot_indices) < int(LOSSLESS_GUARD_CONTRACT["minimumChariots"]):
        reason = (
            f"战车类只有{len(chariot_indices)}名，少于"
            f"{LOSSLESS_GUARD_CONTRACT['minimumChariots']}名"
        )
    elif not catapult_indices:
        reason = "没有投石车"
    elif not last_chariot_is_catapult:
        reason = "所有战车兵种中的最后一个不是投石车"
    else:
        reason = "符合10级卫兵筛选条件"
    return {
        "qualified": qualified,
        "reason": reason,
        "chariotCount": len(chariot_indices),
        "chariotPositions": [index + 1 for index in chariot_indices],
        "catapultPositions": [index + 1 for index in catapult_indices],
        "otherChariotPositions": [
            index + 1 for index in other_chariot_indices
        ],
        "formation": [
            f"{enemy.get('soldierCount')}{enemy.get('soldierType')}"
            for enemy in enemies
        ],
    }


def parse_lossless_select_response(payload: bytes) -> Dict[str, Any]:
    output: Dict[str, Any] = {"rawHex": payload.hex(), "success": False}
    if len(payload) < 4:
        output["parseError"] = "0x8908 数据不足"
        return output
    position = 0
    try:
        status = struct.unpack(">i", payload[position:position + 4])[0]
        position += 4
        message, position = read_utf(payload, position)
        if position + 10 > len(payload):
            raise ValueError("0x8908 缺少等级或阶段字段")
        selected_level_index = struct.unpack(">q", payload[position:position + 8])[0]
        position += 8
        stage_id = struct.unpack(">H", payload[position:position + 2])[0]
        position += 2
        output.update(
            {
                "status": status,
                "success": status == 1,
                "message": message,
                "selectedLevelIndex": selected_level_index,
                "selectedLevel": selected_level_index + 1,
                "stageId": stage_id,
                "stageIdHex": f"{stage_id:04x}",
                "parsedBytes": position,
            }
        )
    except Exception as error:
        output["parseError"] = str(error)
    return output


def parse_lossless_settlement(payload: bytes) -> Dict[str, Any]:
    output: Dict[str, Any] = {
        "rawHex": payload.hex()[:8192],
        "success": False,
        "textPreview": printable(payload, 2000),
    }
    if not payload:
        output["parseError"] = "0x8902 空响应"
        return output
    position = 0
    try:
        status = struct.unpack(">b", payload[position:position + 1])[0]
        position += 1
        output["status"] = status
        if status != 0:
            output["message"] = (
                "没有待结算的无损战报"
                if status == -1
                else f"无损结算失败状态 {status}"
            )
            output["parsedBytes"] = position
            return output
        if position + 9 > len(payload):
            raise ValueError(f"0x8902 成功响应字段不足：{len(payload)}/10")
        mode_after = struct.unpack(">b", payload[position:position + 1])[0]
        position += 1
        battle_id = struct.unpack(">q", payload[position:position + 8])[0]
        position += 8
        output.update(
            {
                "modeAfterSettlement": mode_after,
                "battleId": battle_id,
                "battleIdHex": f"{battle_id:016x}",
            }
        )
        text_fields = []
        for key in ("resultText", "generalText", "extraText"):
            if position + 2 > len(payload):
                break
            value, position = read_utf(payload, position)
            output[key] = value
            text_fields.append(value)
        if position < len(payload):
            output["tailHex"] = payload[position:].hex()
        message = text_fields[0] if text_fields else ""
        combined_text = "\n".join(text_fields) or output["textPreview"]
        output.update(
            {
                "message": message,
                "success": True,
                "battleWon": (
                    any(
                        token in combined_text
                        for token in ("胜利", "成功", "通关")
                    )
                    and "失败" not in combined_text
                ),
                "battleFailed": "失败" in combined_text,
                "parsedBytes": position,
            }
        )
    except Exception as error:
        output["parseError"] = str(error)
    return output
