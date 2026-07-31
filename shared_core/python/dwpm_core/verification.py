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
