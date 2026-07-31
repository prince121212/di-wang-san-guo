"""Offline cross-platform fixture verification executed by either host."""

from __future__ import annotations

from typing import Any, Dict, List

from .contracts import load_json_contract
from .features.expedition import (
    build_brush_payloads,
    build_dungeon_expedition_payload,
    build_dungeon_prepare_payload,
    build_lossless_expedition_payload,
    build_lossless_prepare_payload,
    build_mine_payloads,
    build_raid_expedition_payload,
    build_raid_prepare_payload,
    parse_dispatch_response,
)
from .features.formation import (
    build_assign_troops_payload,
    build_refill_payload,
    parse_assign_troops_response,
    parse_refill_response,
)
from .protocol.wire import encode_utf, make_packet, parse_response
from .features.mine import (
    build_march_speed_payload,
    build_recall_payload,
    choose_march_speed_items,
    parse_march_speed_response,
    parse_mine_preview,
    parse_recall_response,
)
from .features.targets import (
    brush_scan_coordinates,
    mine_target_matches,
    parse_bandit_targets,
    parse_mine_resources,
    target_matches_search_filter,
)
from .features.raid import (
    build_raid_fief_list_payload,
    parse_raid_fief_list,
)
from .features.lossless import (
    evaluate_level10_guard_lineup,
    parse_lossless_settlement,
    parse_lossless_status,
)
from .features.dungeon import (
    dungeon_chest_index,
    first_uncompleted_dungeon_stage,
    parse_dungeon_catalog,
    parse_dungeon_state,
    resolve_dungeon_stage_code,
)
from .features.generals import (
    parse_8004_head,
    parse_a110_general_statuses,
    parse_idle_army_from_8004,
    recover_generals_from_8004,
)
from .features.inventory import parse_8104_inventory
from .features.military import (
    MILITARY_INTEL_REQUEST_PAYLOAD,
    build_military_snapshot,
    parse_8600_military_actions,
    parse_8600_military_events,
)


def verify_protocol_fixtures() -> Dict[str, Any]:
    contract = load_json_contract("protocol_parity_fixtures.json")
    fixtures = contract["fixtures"]
    checks: List[Dict[str, Any]] = []

    def check(name: str, actual: Any, expected: Any) -> None:
        checks.append(
            {
                "name": name,
                "passed": actual == expected,
                "actual": actual,
                "expected": expected,
            }
        )

    wire = fixtures["wireEnvelopeV1"]
    check("wire.utf", encode_utf(wire["utfText"]).hex(), wire["utfHex"])
    request = wire["request"]
    commands = [
        (int(row["opcode"], 0), bytes.fromhex(row["payloadHex"]))
        for row in request["commands"]
    ]
    check(
        "wire.request",
        make_packet(
            commands,
            request["dm"],
            header=request["header"],
            timestamp_millis=request["timestampMillis"],
        ).hex(),
        request["expectedHex"],
    )
    for response_name, expected_payload_name in (
        ("plainResponseHex", "plainResponsePayloadHex"),
        ("obfuscatedResponseHex", "obfuscatedResponsePayloadHex"),
    ):
        packets = parse_response(bytes.fromhex(wire[response_name]))
        check(
            f"wire.{response_name}",
            packets[0]["payload"].hex() if packets else "",
            wire[expected_payload_name],
        )

    assignment = fixtures["formationAssign1226"]
    assignment_payload = build_assign_troops_payload(
        f"{assignment['generalId']:016x}",
        assignment["soldierTypeCode"],
        assignment["soldierCount"],
    )
    check(
        "formation.assign.request",
        assignment_payload.hex(),
        assignment["requestPayloadHex"],
    )
    assignment_receipt = parse_assign_troops_response(
        bytes.fromhex(assignment["successResponseHex"])
    )
    check(
        "formation.assign.receipt",
        {
            "success": assignment_receipt.get("success"),
            "oldType": assignment_receipt.get("oldSoldierTypeCode"),
            "oldCount": assignment_receipt.get("oldSoldierCount"),
            "newType": assignment_receipt.get("assignedSoldierTypeCode"),
            "newCount": assignment_receipt.get("assignedSoldierCount"),
        },
        {
            "success": assignment["expected"]["success"],
            "oldType": assignment["expected"]["previousType"],
            "oldCount": assignment["expected"]["previousCount"],
            "newType": assignment["expected"]["assignedType"],
            "newCount": assignment["expected"]["assignedCount"],
        },
    )

    refill = fixtures["formationRefill1229"]
    refill_payload = build_refill_payload(
        [f"{value:016x}" for value in refill["generalIds"]]
    )
    check("formation.refill.request", refill_payload.hex(), refill["requestPayloadHex"])
    refill_receipt = parse_refill_response(bytes.fromhex(refill["successResponseHex"]))
    check(
        "formation.refill.receipt",
        {
            "success": refill_receipt.get("success"),
            "message": refill_receipt.get("message"),
            "entryCount": len(refill_receipt.get("roleUpdates") or []),
        },
        {
            "success": refill["expected"]["success"],
            "message": refill["expected"]["message"],
            "entryCount": refill["expected"]["entryCount"],
        },
    )

    brush = fixtures["brushYellowActionType3"]
    brush_payloads = build_brush_payloads(
        brush["generalIdHexChunks"],
        brush["targetIdHex"],
    )
    check("expedition.brush.prepare", brush_payloads[0], brush["expected"]["prepareGameHex"])
    check("expedition.brush.dispatch", brush_payloads[1], brush["expected"]["dispatchGameHex"])

    mine = fixtures["mineActionType2"]
    mine_payloads = build_mine_payloads(
        [f"{value:016x}" for value in mine["generalIds"]],
        mine["targetId"],
    )
    check("expedition.mine.prepare", mine_payloads[0].hex(), mine["expected"]["preparePayloadHex"])
    check("expedition.mine.dispatch", mine_payloads[1].hex(), mine["expected"]["dispatchPayloadHex"])

    dispatch = fixtures["brushYellowDispatchReceipts"]
    dispatch_success = parse_dispatch_response(
        bytes.fromhex(dispatch["successResponseHex"])
    )
    dispatch_reject = parse_dispatch_response(
        bytes.fromhex(dispatch["softRejectResponseHex"])
    )
    check(
        "receipt.dispatch.success",
        {"success": dispatch_success.get("success"), "battleId": dispatch_success.get("battleId")},
        {"success": True, "battleId": dispatch["expectedBattleId"]},
    )
    check("receipt.dispatch.reject", dispatch_reject.get("success"), False)

    preview = fixtures["minePreview8520"]
    preview_result = parse_mine_preview(bytes.fromhex(preview["responseHex"]))
    check(
        "mine.preview",
        {key: preview_result.get(key) for key in ("marchSeconds", "winRate", "x", "y")},
        preview["expected"],
    )

    withdraw = fixtures["mineWithdraw8526"]
    check(
        "mine.recall.request",
        build_recall_payload(withdraw["battleId"]).hex(),
        withdraw["requestPayloadHex"],
    )
    check(
        "mine.recall.success",
        parse_recall_response(
            bytes.fromhex(withdraw["successResponseHex"]),
            withdraw["battleId"],
        ).get("success"),
        True,
    )
    check(
        "mine.recall.mismatch",
        parse_recall_response(
            bytes.fromhex(withdraw["mismatchedResponseHex"]),
            withdraw["battleId"],
        ).get("success"),
        False,
    )

    march_speed = fixtures["mineMarchSpeed8524"]
    check(
        "mine.speed.request",
        build_march_speed_payload(
            march_speed["battleId"],
            march_speed["itemId"],
        ).hex(),
        march_speed["requestPayloadHex"],
    )
    check(
        "mine.speed.success",
        parse_march_speed_response(
            bytes.fromhex(march_speed["successResponseHex"])
        ).get("success"),
        True,
    )
    check(
        "mine.speed.finished",
        parse_march_speed_response(
            bytes.fromhex(march_speed["finishedResponseHex"])
        ).get("finished"),
        True,
    )
    smart_speed = fixtures["mineSmartSpeed"]
    check(
        "mine.speed.selection",
        choose_march_speed_items(
            smart_speed["remainingSeconds"],
            smart_speed["inventory"],
        ),
        smart_speed["expectedItemIds"],
    )

    bandit_search = fixtures["targetSearch8540Complete"]
    bandit_expected = bandit_search["expected"]
    bandit_targets = parse_bandit_targets(
        bytes.fromhex(bandit_search["responseHex"])
    )
    bandit = bandit_targets[0] if bandit_targets else {}
    check(
        "targets.bandit.parse",
        {
            key: bandit.get(key)
            for key in (
                "id",
                "kind",
                "level",
                "x",
                "y",
                "resource1",
                "resource2",
                "lootIds",
                "compositionCode",
                "source",
            )
        },
        {
            key: bandit_expected[key]
            for key in (
                "id",
                "kind",
                "level",
                "x",
                "y",
                "resource1",
                "resource2",
                "lootIds",
                "compositionCode",
                "source",
            )
        },
    )

    mine_search = fixtures["mineSearch8542Structured"]
    mine_expected = mine_search["expected"]
    mine_targets = parse_mine_resources(bytes.fromhex(mine_search["responseHex"]))
    check(
        "targets.mine.parse",
        [
            {
                key: target.get(key)
                for key in (
                    "id",
                    "kind",
                    "level",
                    "x",
                    "y",
                    "ownerName",
                    "ownerCountry",
                    "playerOccupied",
                    "isEmpty",
                    "defenderCount",
                )
            }
            for target in mine_targets
        ],
        [
            {
                key: expected[key]
                for key in (
                    "id",
                    "kind",
                    "level",
                    "x",
                    "y",
                    "ownerName",
                    "ownerCountry",
                    "playerOccupied",
                    "isEmpty",
                    "defenderCount",
                )
            }
            for expected in (mine_expected["occupied"], mine_expected["empty"])
        ],
    )

    grid = fixtures["brushYellowCanonicalGridCenter100x30"]
    check(
        "targets.bandit.grid",
        brush_scan_coordinates(
            grid["center"]["x"],
            grid["center"]["y"],
            grid["limit"],
        ),
        [tuple(point) for point in grid["expectedCoordinates"]],
    )

    exact_levels = fixtures["brushYellowExactLevels"]
    check(
        "targets.bandit.levelFilter",
        [
            target_matches_search_filter(
                target,
                "山贼",
                exact_levels["selectedLevels"],
                [],
                {},
            )
            for target in exact_levels["targets"]
        ],
        [target["matches"] for target in exact_levels["targets"]],
    )

    mine_filter = fixtures["mineExactLevelAndOwnership"]
    check(
        "targets.mine.filter",
        [
            mine_target_matches(
                {
                    "id": target["id"],
                    "kind": target["mineType"],
                    "level": target["level"],
                    "isEmpty": target["isEmpty"],
                    "playerOccupied": target["playerOccupied"],
                },
                resource_types=mine_filter["selectedMineTypes"],
                levels=mine_filter["selectedLevels"],
                only_empty=mine_filter["onlyEmpty"],
            )
            for target in mine_filter["targets"]
        ],
        [target["matches"] for target in mine_filter["targets"]],
    )

    raid_fief = fixtures["raidFief8310"]
    raid_fief_expected = raid_fief["expected"]
    check(
        "raid.fief.request",
        build_raid_fief_list_payload(raid_fief["playerName"]).hex(),
        raid_fief["requestPayloadHex"],
    )
    raid_fief_result = parse_raid_fief_list(
        bytes.fromhex(raid_fief["responseHex"])
    )
    first_fief = (raid_fief_result.get("fiefs") or [{}])[0]
    check(
        "raid.fief.parse",
        {
            "playerName": raid_fief_result.get("playerName"),
            "country": raid_fief_result.get("country"),
            "count": raid_fief_result.get("count"),
            "firstTargetId": first_fief.get("targetId"),
            "firstName": first_fief.get("name"),
            "firstCityName": first_fief.get("cityName"),
            "firstX": first_fief.get("x"),
            "firstY": first_fief.get("y"),
        },
        raid_fief_expected,
    )
    raid_receipts = fixtures["raidDispatchReceipts"]
    check(
        "receipt.dispatch.missingBattleId",
        parse_dispatch_response(
            bytes.fromhex(raid_receipts["missingBattleIdResponseHex"])
        ).get("success"),
        False,
    )

    lossless_status_fixture = fixtures["losslessCooldown8900"]
    lossless_status_expected = lossless_status_fixture["expected"]
    lossless_status = parse_lossless_status(
        bytes.fromhex(lossless_status_fixture["responseHex"])
    )
    check(
        "lossless.status",
        {
            "phase": lossless_status.get("phase"),
            "mode": lossless_status.get("mode"),
            "remainingAttempts": lossless_status.get("remainingAttempts"),
            "actionTimerMillis": lossless_status.get("actionTimerMs"),
            "cooldownMillis": lossless_status.get("cooldownMs"),
            "reopenCost": lossless_status.get("reopenCost"),
        },
        lossless_status_expected,
    )
    lossless_settlement_fixture = fixtures["losslessSettlement8902Failed"]
    lossless_settlement_expected = lossless_settlement_fixture["expected"]
    lossless_settlement = parse_lossless_settlement(
        bytes.fromhex(lossless_settlement_fixture["responseHex"])
    )
    check(
        "lossless.settlement",
        {
            key: lossless_settlement.get(key)
            for key in (
                "success",
                "battleFailed",
                "battleId",
                "resultText",
                "generalText",
            )
        },
        lossless_settlement_expected,
    )
    guard_fixture = fixtures["losslessLevel10LastChariot"]
    guard_result = evaluate_level10_guard_lineup(
        {
            "stageId": guard_fixture["stageId"],
            "stageName": guard_fixture["stageName"],
            "enemies": [
                {
                    "position": index + 1,
                    "soldierType": soldier_type,
                    "soldierCount": 100,
                }
                for index, soldier_type in enumerate(
                    guard_fixture["soldierTypes"]
                )
            ],
        }
    )
    check(
        "lossless.guard",
        {
            key: guard_result.get(key)
            for key in ("qualified", "chariotPositions", "catapultPositions")
        },
        guard_fixture["expected"],
    )

    dungeon_catalog_fixture = fixtures["dungeonCatalog8930"]
    dungeon_catalog_expected = dungeon_catalog_fixture["expected"]
    dungeon_catalog = parse_dungeon_catalog(
        bytes.fromhex(dungeon_catalog_fixture["responseHex"])
    )
    first_chapter = (dungeon_catalog.get("chapters") or [{}])[0]
    first_stages = first_chapter.get("stages") or []
    check(
        "dungeon.catalog",
        {
            "chapterCount": len(dungeon_catalog.get("chapters") or []),
            "firstChapterName": first_chapter.get("name"),
            "firstChapterStageCount": len(first_stages),
            "displayStage3Code": first_stages[2].get("stageCode"),
            "displayStage4Code": first_stages[3].get("stageCode"),
        },
        {
            key: dungeon_catalog_expected[key]
            for key in (
                "chapterCount",
                "firstChapterName",
                "firstChapterStageCount",
                "displayStage3Code",
                "displayStage4Code",
            )
        },
    )
    first_uncompleted = first_uncompleted_dungeon_stage(dungeon_catalog) or {}
    check(
        "dungeon.progression",
        {
            "firstUncompletedChapter": first_uncompleted.get("chapter"),
            "firstUncompletedDisplayStage": first_uncompleted.get("stage"),
            "firstUncompletedStageCode": first_uncompleted.get("stageCode"),
            "firstUncompletedAvailable": first_uncompleted.get("available"),
            "chapter7DisplayStage11Code": resolve_dungeon_stage_code(
                dungeon_catalog,
                6,
                11,
            ),
        },
        {
            key: dungeon_catalog_expected[key]
            for key in (
                "firstUncompletedChapter",
                "firstUncompletedDisplayStage",
                "firstUncompletedStageCode",
                "firstUncompletedAvailable",
                "chapter7DisplayStage11Code",
            )
        },
    )
    dungeon_state_fixture = fixtures["dungeonStateAndPoll"]
    check(
        "dungeon.state.idle",
        parse_dungeon_state(
            bytes.fromhex(dungeon_state_fixture["idleResponseHex"])
        ).get("active"),
        False,
    )
    dungeon_active = parse_dungeon_state(
        bytes.fromhex(dungeon_state_fixture["fightingResponseHex"])
    )
    check(
        "dungeon.state.fighting",
        {
            "active": dungeon_active.get("active"),
            "battleId": dungeon_active.get("battleId"),
        },
        {
            "active": True,
            "battleId": dungeon_state_fixture["expected"]["battleId"],
        },
    )
    check("dungeon.chest", dungeon_chest_index("右"), 2)

    military_incoming_fixture = fixtures["militaryIncoming8600"]
    check(
        "military.request",
        MILITARY_INTEL_REQUEST_PAYLOAD.hex(),
        military_incoming_fixture["requestPayloadHex"],
    )
    military_actions = parse_8600_military_actions(
        bytes.fromhex(military_incoming_fixture["responseHex"]),
        [],
    )
    incoming = military_actions[0] if military_actions else {}
    check(
        "military.incoming",
        {
            key: incoming.get(key)
            for key in (
                "text",
                "state",
                "recordId",
                "attackerName",
                "actionType",
                "targetName",
                "targetId",
                "marchValue",
                "eventTimeMs",
            )
        },
        military_incoming_fixture["expected"],
    )
    garrison_fixture = fixtures["militaryGarrisonEvent8600"]
    garrison_events = parse_8600_military_events(
        bytes.fromhex(garrison_fixture["responseHex"])
    )
    garrison = garrison_events[0] if garrison_events else {}
    check(
        "military.garrisonEvent",
        {
            key: garrison.get(key)
            for key in (
                "battleId",
                "generalIds",
                "targetId",
                "targetName",
                "x",
                "y",
            )
        },
        garrison_fixture["expected"],
    )
    general_fixture = fixtures["generalRecord8004"]
    recovered_generals = recover_generals_from_8004(
        general_fixture["responseHex"]
    )
    recovered_general = recovered_generals[0] if recovered_generals else {}
    check(
        "generals.8004",
        {
            key: recovered_general.get(key)
            for key in (
                "id",
                "name",
                "status",
                "statusText",
                "level",
                "growth",
                "tili",
                "tiliLimit",
                "troopLimit",
            )
        },
        general_fixture["expected"],
    )
    role_head_fixture = fixtures["roleHead8004"]
    role_head = parse_8004_head(
        bytes.fromhex(role_head_fixture["responseHex"])
    )
    check(
        "role.8004",
        {
            key: role_head.get(key)
            for key in role_head_fixture["expected"]
        },
        role_head_fixture["expected"],
    )
    idle_army_fixture = fixtures["idleArmy8004"]
    idle_army = parse_idle_army_from_8004(
        idle_army_fixture["responseHex"]
    )
    check(
        "army.8004",
        [
            {
                key: row.get(key)
                for key in (
                    "soldierTypeCode",
                    "soldierType",
                    "idleCount",
                    "woundedCount",
                    "fiefName",
                )
            }
            for row in idle_army
        ],
        idle_army_fixture["expected"],
    )
    status_fixture = fixtures["generalStatusA110"]
    status_result = parse_a110_general_statuses(
        bytes.fromhex(status_fixture["responseHex"]),
        [status_fixture["general"]],
    )
    first_status = (status_result.get("records") or [{}])[0]
    check(
        "generals.a110",
        {
            key: first_status.get(key)
            for key in status_fixture["expected"]
        },
        status_fixture["expected"],
    )
    inventory_fixture = fixtures["inventory8104Compact"]
    inventory = parse_8104_inventory(
        bytes.fromhex(inventory_fixture["responseHex"]),
        item_names={
            int(key): value
            for key, value in inventory_fixture["itemNames"].items()
        },
        equipment_templates={
            int(key): value
            for key, value in inventory_fixture["equipmentTemplates"].items()
        },
    )
    first_equipment = (inventory.get("equipment") or [{}])[0]
    check(
        "inventory.8104",
        {
            "capacity": inventory.get("capacity"),
            "itemCount": inventory.get("itemCount"),
            "itemIds": [
                row.get("itemId")
                for row in inventory.get("items") or []
            ],
            "itemCounts": [
                row.get("count")
                for row in inventory.get("items") or []
            ],
            "equipmentCount": inventory.get("equipmentCount"),
            "equipmentName": first_equipment.get("name"),
            "equipmentQuality": first_equipment.get("qualityName"),
            "equipmentStrengthen": first_equipment.get("strengthen"),
        },
        inventory_fixture["expected"],
    )
    incoming_payload = bytes.fromhex(military_incoming_fixture["responseHex"])
    military_snapshot = build_military_snapshot(
        [incoming_payload, incoming_payload],
        [],
        200,
    )
    check(
        "military.snapshot",
        {
            "responded": military_snapshot.get("responded"),
            "actionCount": military_snapshot.get("actionCount"),
            "incomingCount": military_snapshot.get("incomingCount"),
        },
        {"responded": True, "actionCount": 1, "incomingCount": 1},
    )

    for feature, fixture_name, target_name, prepare_builder, dispatch_builder in (
        (
            "raid",
            "raidActionType1",
            "targetId",
            build_raid_prepare_payload,
            build_raid_expedition_payload,
        ),
        (
            "lossless",
            "losslessActionType11",
            "roleId",
            build_lossless_prepare_payload,
            build_lossless_expedition_payload,
        ),
        (
            "dungeon",
            "dungeonActionType14",
            "stageCode",
            build_dungeon_prepare_payload,
            build_dungeon_expedition_payload,
        ),
    ):
        fixture = fixtures[fixture_name]
        identifiers = [f"{value:016x}" for value in fixture["generalIds"]]
        prepare = prepare_builder(identifiers, fixture[target_name])
        dispatch = dispatch_builder(identifiers, fixture[target_name])
        check(
            f"expedition.{feature}.prepare",
            prepare.hex(),
            fixture["expected"]["preparePayloadHex"],
        )
        check(
            f"expedition.{feature}.dispatch",
            dispatch.hex(),
            fixture["expected"]["dispatchPayloadHex"],
        )

    failures = [row for row in checks if not row["passed"]]
    return {
        "ok": not failures,
        "schemaVersion": contract["schemaVersion"],
        "checkCount": len(checks),
        "passedCount": len(checks) - len(failures),
        "failureCount": len(failures),
        "checks": checks,
    }
