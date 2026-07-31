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
)
from .features.formation import (
    build_assign_troops_payload,
    build_refill_payload,
    parse_assign_troops_response,
    parse_refill_response,
)
from .protocol.wire import encode_utf, make_packet, parse_response


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
