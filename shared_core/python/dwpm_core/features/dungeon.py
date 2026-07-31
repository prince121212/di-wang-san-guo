"""Dungeon catalog, progression, selection and state rules."""

from __future__ import annotations

import re
import struct
from typing import Any, Dict, List, Optional

from ..contracts import load_behavior_contract
from ..protocol.wire import printable, read_utf


DUNGEON_CONTRACT = load_behavior_contract()["dungeon"]
DUNGEON_CHAPTER_MAP = {
    "第一章": 0,
    "第二章": 1,
    "第三章": 2,
    "第四章": 3,
    "第五章": 4,
    "第六章": 5,
    "第七章": 6,
    "山贼之乱": 0,
    "长安之乱": 2,
    "徐州之争": 3,
    "伪帝袁术": 4,
    "官渡之战（上）": 5,
    "官渡之战（下）": 6,
}
DUNGEON_CHEST_MAP = {
    **{
        str(name): index
        for index, name in enumerate(DUNGEON_CONTRACT["chestNames"])
    },
    "left": 0,
    "middle": 1,
    "right": 2,
}
DUNGEON_STATIC_STAGE_CODES = {
    int(chapter): [int(value) for value in values]
    for chapter, values in DUNGEON_CONTRACT["staticStageCodes"].items()
}
DUNGEON_CHAPTER_STAGE_COUNTS = {
    chapter_id: len(stage_codes)
    for chapter_id, stage_codes in DUNGEON_STATIC_STAGE_CODES.items()
}
DUNGEON_MODE_LOOP, DUNGEON_MODE_CLEAR = tuple(
    DUNGEON_CONTRACT["allowedModes"]
)


def normalize_dungeon_mode(value: Any) -> str:
    if isinstance(value, bool):
        return DUNGEON_MODE_CLEAR if value else DUNGEON_MODE_LOOP
    text = str(value or "").strip().lower()
    if text in {
        "clear",
        "progressive",
        "progress",
        "通关",
        "打通",
        "打通副本",
    }:
        return DUNGEON_MODE_CLEAR
    return str(DUNGEON_CONTRACT["defaultMode"])


def dungeon_chapter_number(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        if 0 <= value <= 20:
            return value
        raise RuntimeError(f"副本章节超出范围：{value}")
    text = str(value if value is not None else "").strip()
    if text in DUNGEON_CHAPTER_MAP:
        return int(DUNGEON_CHAPTER_MAP[text])
    display_match = re.fullmatch(r"第\s*(\d+)\s*章", text)
    if display_match:
        number = int(display_match.group(1))
        if 1 <= number <= 21:
            return number - 1
    match = re.search(r"(\d+)", text)
    if match:
        number = int(match.group(1))
        if 0 <= number <= 20:
            return number
    raise RuntimeError(f"副本章节无效：{value}")


def dungeon_stage_number(value: Any, chapter_id: Optional[int] = None) -> int:
    try:
        number = int(str(value or "").strip())
    except Exception:
        raise RuntimeError(f"副本关卡无效：{value}")
    if not 1 <= number <= 50:
        raise RuntimeError(f"副本关卡超出范围：{value}")
    chapter_stage_count = (
        DUNGEON_CHAPTER_STAGE_COUNTS.get(chapter_id)
        if chapter_id is not None
        else None
    )
    if chapter_stage_count is not None and number > chapter_stage_count:
        raise RuntimeError(
            f"副本第 {chapter_id + 1} 章只有 {chapter_stage_count} 关，"
            f"不能选择第 {number} 关"
        )
    return number


def dungeon_chapter_final_stage(
    chapter_id: int,
    stages: List[Dict[str, Any]],
) -> int:
    static_codes = DUNGEON_STATIC_STAGE_CODES.get(int(chapter_id)) or []
    max_display = max(
        (int(stage.get("displayStage") or 0) for stage in stages),
        default=0,
    )
    return max(len(static_codes), max_display)


def first_uncompleted_dungeon_stage(
    catalog: Dict[str, Any],
    *,
    skip_multiplayer_finals: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    if skip_multiplayer_finals is None:
        skip_multiplayer_finals = bool(
            DUNGEON_CONTRACT["clearModeSkipsMultiplayerFinals"]
        )
    chapters = [
        chapter
        for chapter in (catalog.get("chapters") or [])
        if isinstance(chapter, dict)
    ]
    chapters.sort(
        key=lambda item: (
            int(
                item.get("chapterId")
                if item.get("chapterId") is not None
                else item.get("displayChapter") or 0
            ),
            int(item.get("displayChapter") or 0),
        )
    )
    for chapter in chapters:
        stages = [
            row
            for row in (chapter.get("stages") or [])
            if isinstance(row, dict)
        ]
        stages.sort(key=lambda item: int(item.get("displayStage") or 0))
        chapter_id = int(
            chapter.get("chapterId")
            if chapter.get("chapterId") is not None
            else int(chapter.get("displayChapter") or 1) - 1
        )
        if not stages and int(chapter.get("detailFlag") or 0) == 0:
            static_codes = DUNGEON_STATIC_STAGE_CODES.get(chapter_id) or []
            return {
                "chapter": chapter_id,
                "chapterName": f"第{chapter_id + 1}章",
                "catalogChapterName": str(chapter.get("name") or ""),
                "stage": 1,
                "stageCode": int(static_codes[0]) if static_codes else None,
                "available": False,
                "resultCode": int(DUNGEON_CONTRACT["uncompletedResultCode"]),
                "lockedChapter": True,
                "catalog": catalog,
            }
        final_stage = dungeon_chapter_final_stage(chapter_id, stages)
        for stage in stages:
            if int(
                stage.get(
                    "resultCode",
                    DUNGEON_CONTRACT["uncompletedResultCode"],
                )
            ) != int(DUNGEON_CONTRACT["uncompletedResultCode"]):
                continue
            display_stage = int(stage.get("displayStage") or 0)
            if display_stage <= 0:
                continue
            if (
                skip_multiplayer_finals
                and final_stage > 0
                and display_stage >= final_stage
            ):
                continue
            if stage.get("stageCode") is None:
                raise RuntimeError(
                    f"副本第{chapter_id + 1}章第{display_stage}关"
                    "缺少服务器关卡编号"
                )
            return {
                "chapter": chapter_id,
                "chapterName": f"第{chapter_id + 1}章",
                "stage": display_stage,
                "stageCode": int(stage.get("stageCode")),
                "available": bool(stage.get("available", True)),
                "resultCode": int(DUNGEON_CONTRACT["uncompletedResultCode"]),
                "catalog": catalog,
            }
    return None


def dungeon_stage_completed_in_catalog(
    catalog: Dict[str, Any],
    stage_ref: Dict[str, Any],
) -> Optional[bool]:
    chapter_id = int(stage_ref.get("chapter") or 0)
    display_stage = int(stage_ref.get("stage") or 0)
    for chapter in catalog.get("chapters") or []:
        if int(chapter.get("chapterId", -1)) != chapter_id:
            continue
        for stage in chapter.get("stages") or []:
            if int(stage.get("displayStage") or 0) == display_stage:
                return int(
                    stage.get(
                        "resultCode",
                        DUNGEON_CONTRACT["uncompletedResultCode"],
                    )
                ) != int(DUNGEON_CONTRACT["uncompletedResultCode"])
    return None


def dungeon_battle_texts(result: Any) -> List[str]:
    if not isinstance(result, dict):
        return []
    texts = []

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text:
            texts.append(text)

    for source in (
        result,
        result.get("chestResult"),
        result.get("rewardState"),
        result.get("dungeonStateAfterLaunch"),
    ):
        if isinstance(source, dict):
            for key in (
                "textPreview",
                "message",
                "serverMessage",
                "launchText",
                "failureReason",
            ):
                add(source.get(key))
    for action in result.get("actionResults") or []:
        if not isinstance(action, dict):
            continue
        for packet in action.get("packets") or []:
            if isinstance(packet, dict):
                add(packet.get("textPreview"))
    for poll in (result.get("battlePoll") or {}).get("polls") or []:
        if not isinstance(poll, dict):
            continue
        for packet in poll.get("packets") or []:
            if isinstance(packet, dict):
                add(packet.get("textPreview"))
    return texts


def dungeon_battle_defeat_confirmed(result: Any) -> bool:
    if isinstance(result, dict) and result.get("defeatConfirmed") is True:
        return True
    return any(
        marker in text
        for text in dungeon_battle_texts(result)
        for marker in DUNGEON_CONTRACT["defeatMarkers"]
    )


def dungeon_chest_index(value: Any) -> int:
    text = str(value if value is not None else "").strip()
    if text in DUNGEON_CHEST_MAP:
        return int(DUNGEON_CHEST_MAP[text])
    try:
        number = int(text)
    except Exception:
        raise RuntimeError(f"副本开箱位置无效：{value}")
    if number in {0, 1, 2}:
        return number
    if number in {1, 2, 3}:
        return number - 1
    raise RuntimeError(f"副本开箱位置超出范围：{value}")


def is_dungeon_pending_chest_error(message: Any) -> bool:
    text = re.sub(r"[\s：:。.-]+", "", str(message or ""))
    return "副本个人状态异常" in text and "非空闲状态" in text


def parse_dungeon_catalog(payload: bytes) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "rawHex": payload.hex()[:4096],
        "chapters": [],
        "chapterNames": [],
        "textPreview": printable(payload, 1200),
    }
    if len(payload) < 2:
        result["parseError"] = "0x8930 数据不足"
        return result
    status = int(payload[0])
    result["status"] = status
    if status != 0:
        result["parseError"] = f"0x8930 返回状态={status}"
        return result
    position = 1
    try:
        chapter_count = int(payload[position])
        position += 1
        chapters = []
        for display_index in range(chapter_count):
            if position + 10 > len(payload):
                raise ValueError(
                    f"章节头越界：index={display_index} pos={position}"
                )
            chapter_id, coord_a, coord_b, coord_c = struct.unpack(
                ">HHHH",
                payload[position:position + 8],
            )
            position += 8
            name, position = read_utf(payload, position)
            if position >= len(payload):
                raise ValueError(
                    f"章节状态越界：index={display_index} pos={position}"
                )
            detail_flag = int(payload[position])
            position += 1
            stage_entries = []
            if detail_flag == 1:
                if position >= len(payload):
                    raise ValueError(
                        f"关卡数量越界：index={display_index} pos={position}"
                    )
                stage_count = int(payload[position])
                position += 1
                for stage_index in range(stage_count):
                    if position + 4 > len(payload):
                        raise ValueError(
                            f"关卡条目越界：chapter={chapter_id} "
                            f"index={stage_index} pos={position}"
                        )
                    stage_code = struct.unpack(
                        ">H",
                        payload[position:position + 2],
                    )[0]
                    available = int(payload[position + 2])
                    result_code = int(payload[position + 3])
                    position += 4
                    stage_entries.append(
                        {
                            "displayStage": stage_index + 1,
                            "stageCode": stage_code,
                            "available": bool(available),
                            "availableCode": available,
                            "resultCode": result_code,
                        }
                    )
            chapters.append(
                {
                    "displayChapter": display_index + 1,
                    "chapterId": chapter_id,
                    "name": name,
                    "detailFlag": detail_flag,
                    "coords": [coord_a, coord_b, coord_c],
                    "stages": stage_entries,
                }
            )
        result["chapters"] = chapters
        result["chapterNames"] = [
            str(chapter.get("name") or "")
            for chapter in chapters
            if chapter.get("name")
        ]
        result["parsedBytes"] = position
    except Exception as error:
        result["parseError"] = str(error)
    return result


def resolve_dungeon_stage_code(
    catalog: Dict[str, Any],
    chapter_id: int,
    display_stage: int,
) -> int:
    chapter = next(
        (
            item
            for item in (catalog.get("chapters") or [])
            if int(item.get("chapterId", -1)) == int(chapter_id)
        ),
        None,
    )
    stages = chapter.get("stages") if chapter else None
    if isinstance(stages, list) and stages:
        if not 1 <= display_stage <= len(stages):
            raise RuntimeError(
                f"副本第 {chapter_id + 1} 章当前只有 {len(stages)} 关，"
                f"不能选择第 {display_stage} 关"
            )
        stage_code = stages[display_stage - 1].get("stageCode")
        if stage_code is None:
            raise RuntimeError(
                f"副本第 {chapter_id + 1} 章第 {display_stage} 关"
                "缺少服务器关卡编号"
            )
        return int(stage_code)
    static_codes = DUNGEON_STATIC_STAGE_CODES.get(chapter_id) or []
    if not 1 <= display_stage <= len(static_codes):
        detail = (
            f"：{catalog.get('parseError')}"
            if catalog.get("parseError")
            else ""
        )
        raise RuntimeError(
            f"无法解析副本第 {chapter_id + 1} 章第 {display_stage} 关{detail}"
        )
    return int(static_codes[display_stage - 1])


def parse_dungeon_state(payload: bytes) -> Dict[str, Any]:
    output: Dict[str, Any] = {
        "rawHex": payload.hex(),
        "status": None,
        "active": False,
    }
    if not payload:
        return output
    status = payload[0]
    output["status"] = int(status)
    if status == 1 and len(payload) >= 10:
        battle_id = struct.unpack(">q", payload[1:9])[0]
        output.update(
            {
                "active": True,
                "battleId": battle_id,
                "battleIdHex": f"{battle_id:016x}",
                "tailByte": payload[9],
            }
        )
    elif status == 0:
        output["message"] = "无副本战斗"
    elif status == 4:
        output["message"] = "副本战斗已结束/可结算"
    else:
        output["message"] = f"副本状态={status}"
    return output
