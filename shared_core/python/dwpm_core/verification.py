"""Offline cross-platform fixture verification executed by either host."""

from __future__ import annotations

from typing import Any, Dict, List

from .contracts import load_json_contract
from .account import (
    AccountLifecyclePolicy,
    area_catalog_signature,
    classify_reconnect_failure,
    find_login_area,
    parse_8003_login,
    parse_passport_area_list,
    reconnect_delay_millis,
)
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
    parse_composition_code,
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
from .features.maintenance import (
    build_add_loyalty_payload,
    build_delete_all_mail_payload,
    build_discard_inventory_payload,
    build_resource_exchange_payload,
    build_use_general_item_payload,
    build_use_inventory_item_payload,
    equipment_is_safe_to_discard,
    parse_821f_loyalty_response,
    parse_delete_mail_response,
    parse_discard_inventory_response,
    parse_resource_exchange_response,
    parse_use_general_item_response,
)
from .features.daily import (
    build_owned_city_list_payload,
    build_salary_payload,
    country_donation_limits,
    general_visit_already_visited,
    national_citizen_daily_skip_result,
    normalize_general_visit_ids,
    parse_arena_coin_claim_response,
    parse_daily_diamond_box_response,
    parse_daily_sign_in_packets,
    parse_e200_daily_activity,
    parse_general_visit_page,
    parse_general_visit_receipt,
    parse_national_city_page,
    parse_owned_city_list,
    parse_salary_receipt,
)
from .features.internal_affairs import (
    build_building_action_payload,
    build_country_donation_payload,
    build_fief_query_payload,
    build_technology_donation_payload,
    build_technology_upgrade_payload,
    parse_8200_building_result,
    parse_8246_fief_result,
    parse_technology_states_from_8004,
)
from .features.ministries import (
    build_hubu_batch_plant_payload,
    build_hubu_status_query_payload,
    ministry_planting_allowed,
    normalize_ministry_settings,
    parse_hubu_garden_status,
    parse_hubu_plant_response,
    unconfirmed_ministry_actions,
)
from .features.military import (
    MILITARY_INTEL_REQUEST_PAYLOAD,
    build_military_snapshot,
    parse_8600_military_actions,
    parse_8600_military_events,
)
from .account.state_machine import (
    EVENT_LOGIN_FAILED,
    EVENT_LOGIN_SUCCEEDED,
    EVENT_PROCESS_RECOVERED,
    EVENT_SESSION_EXPIRED,
    EVENT_USER_START,
    reduce_account_event,
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

    login_fixture = fixtures["accountLogin8003"]
    login_result = parse_8003_login(
        bytes.fromhex(login_fixture["responseHex"])
    )
    first_role = (login_result.get("roles") or [{}])[0]
    check(
        "account.login.8003",
        {
            "status": login_result.get("status"),
            "message": login_result.get("message"),
            "dm": login_result.get("dm"),
            "loginTime": login_result.get("loginTime"),
            "selected": login_result.get("selected"),
            "roleCount": len(login_result.get("roles") or []),
            "firstRoleId": first_role.get("roleId"),
            "firstRoleName": first_role.get("roleName"),
            "firstRoleLevel": first_role.get("level"),
            "trailingBytes": login_result.get("trailingBytes"),
        },
        login_fixture["expected"],
    )
    passport_fixture = fixtures["accountPassportAreas"]
    passport_session, passport_user_id, passport_areas = (
        parse_passport_area_list(passport_fixture["responseText"])
    )
    passport_expected = passport_fixture["expected"]
    check(
        "account.passport.parse",
        {
            "session": passport_session,
            "userId": passport_user_id,
            "areaCount": len(passport_areas),
            "firstAreaId": passport_areas[0].get("areaId"),
            "firstAreaName": passport_areas[0].get("areaName"),
        },
        passport_expected,
    )
    check(
        "account.area.select",
        [
            (find_login_area(passport_areas, row["query"]) or {}).get(
                "serverKey"
            )
            for row in passport_fixture["queries"]
        ],
        [
            row["expectedServerKey"]
            for row in passport_fixture["queries"]
        ],
    )
    check(
        "account.area.signature",
        area_catalog_signature(passport_areas),
        area_catalog_signature(list(reversed(passport_areas))),
    )
    lifecycle = AccountLifecyclePolicy.from_behavior_contract(
        load_json_contract("assistant_behavior_contract.json")
    )
    online_lifecycle = lifecycle.snapshot(
        account_enabled=True,
        execution_owner_active=True,
        login_state="REAL_PROTOCOL_ONLINE",
        source_mode=1,
        last_validated_at_millis=1_000,
        now_millis=21_000,
    )
    check(
        "account.lifecycle.online",
        {
            key: online_lifecycle[key]
            for key in (
                "status",
                "statusText",
                "started",
                "shouldProbe",
                "mayUseLiveSession",
            )
        },
        {
            "status": "online",
            "statusText": "开启",
            "started": True,
            "shouldProbe": True,
            "mayUseLiveSession": True,
        },
    )
    stopped_lifecycle = lifecycle.snapshot(
        account_enabled=True,
        execution_owner_active=False,
        login_state="REAL_PROTOCOL_ONLINE",
        source_mode=1,
    )
    check(
        "account.lifecycle.ownerGate",
        {
            key: stopped_lifecycle[key]
            for key in ("status", "started", "mayUseLiveSession")
        },
        {
            "status": "stopped",
            "started": False,
            "mayUseLiveSession": False,
        },
    )
    check(
        "account.lifecycle.failureKinds",
        [
            classify_reconnect_failure("HTTP=0 bytes=0"),
            classify_reconnect_failure("HTTP 403 forbidden"),
            classify_reconnect_failure("HTTP 429"),
            classify_reconnect_failure("0x8152业务失败"),
        ],
        ["network", "server", "throttle", "unknown"],
    )
    check(
        "account.lifecycle.networkBackoff",
        [
            reconnect_delay_millis("network", count)
            for count in (1, 2, 3, 99)
        ],
        [180_000, 300_000, 600_000, 600_000],
    )
    check(
        "account.lifecycle.serverBackoff",
        [
            reconnect_delay_millis("server", count)
            for count in (1, 2, 3, 99)
        ],
        [600_000, 1_200_000, 1_800_000, 1_800_000],
    )
    transition_started = reduce_account_event(
        {
            "desiredStarted": False,
            "loginState": "REAL_PROTOCOL_STOPPED",
            "sessionCredentialPresent": False,
        },
        EVENT_USER_START,
        now_millis=1_000,
    )
    transition_online = reduce_account_event(
        transition_started,
        EVENT_LOGIN_SUCCEEDED,
        now_millis=2_000,
    )
    check(
        "account.stateMachine.startLogin",
        {
            "startedState": transition_started["loginState"],
            "startedOperation": transition_started["nextOperation"],
            "onlineState": transition_online["loginState"],
            "onlineUsable": transition_online["liveSessionUsable"],
        },
        {
            "startedState": "REAL_PROTOCOL_CHECKING",
            "startedOperation": "login",
            "onlineState": "REAL_PROTOCOL_ONLINE",
            "onlineUsable": True,
        },
    )
    transition_network_failure = reduce_account_event(
        transition_started,
        EVENT_LOGIN_FAILED,
        now_millis=3_000,
        details={"message": "HTTP=0 bytes=0"},
    )
    check(
        "account.stateMachine.failure",
        {
            key: transition_network_failure[key]
            for key in (
                "loginState",
                "failureKind",
                "failureCount",
                "nextRetryAtMillis",
                "liveSessionUsable",
                "sessionSecretAction",
            )
        },
        {
            "loginState": "REAL_PROTOCOL_OFFLINE",
            "failureKind": "network",
            "failureCount": 1,
            "nextRetryAtMillis": 183_000,
            "liveSessionUsable": False,
            "sessionSecretAction": "delete",
        },
    )
    transition_recovered = reduce_account_event(
        transition_online,
        EVENT_PROCESS_RECOVERED,
        now_millis=4_000,
    )
    check(
        "account.stateMachine.processRecovery",
        {
            "loginState": transition_recovered["loginState"],
            "nextOperation": transition_recovered["nextOperation"],
            "liveSessionUsable": transition_recovered["liveSessionUsable"],
        },
        {
            "loginState": "REAL_PROTOCOL_CHECKING",
            "nextOperation": "probe",
            "liveSessionUsable": False,
        },
    )
    transition_expired = reduce_account_event(
        transition_online,
        EVENT_SESSION_EXPIRED,
        now_millis=5_000,
        details={"message": "response-opcode-0x8016"},
    )
    check(
        "account.stateMachine.sessionExpired",
        {
            "loginState": transition_expired["loginState"],
            "nextOperation": transition_expired["nextOperation"],
            "sessionSecretAction": transition_expired["sessionSecretAction"],
            "liveSessionUsable": transition_expired["liveSessionUsable"],
        },
        {
            "loginState": "REAL_PROTOCOL_NEED_RELOGIN",
            "nextOperation": "login",
            "sessionSecretAction": "retain",
            "liveSessionUsable": False,
        },
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
    check(
        "targets.composition.parse",
        parse_composition_code("1步2弓3骑4车"),
        {
            "maxFoot": 1,
            "maxBow": 2,
            "maxCavalry": 3,
            "maxChariot": 4,
        },
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
    inventory_item_names = {
        int(key): value
        for key, value in inventory_fixture["itemNames"].items()
    }
    inventory_equipment_templates = {
        int(key): value
        for key, value in inventory_fixture["equipmentTemplates"].items()
    }
    inventory = parse_8104_inventory(
        bytes.fromhex(inventory_fixture["responseHex"]),
        item_names=inventory_item_names,
        equipment_templates=inventory_equipment_templates,
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
    maintenance_fixture = fixtures["maintenanceProtocols"]
    maintenance_expected = maintenance_fixture["expected"]
    check(
        "maintenance.loyalty.request",
        build_add_loyalty_payload(
            maintenance_fixture["generalId"],
            maintenance_fixture["loyaltyDelta"],
        ).hex(),
        maintenance_fixture["addLoyaltyPayloadHex"],
    )
    loyalty_result = parse_821f_loyalty_response(
        bytes.fromhex(maintenance_fixture["addLoyaltyResponseHex"])
    )
    loyalty_general = (loyalty_result.get("generals") or [{}])[0]
    check(
        "maintenance.loyalty.parse",
        {
            "actualCost": loyalty_result.get("actualCost"),
            "copper": loyalty_result.get("copper"),
            "loyalty": loyalty_general.get("loyalty"),
            "loyaltyLimit": loyalty_general.get("loyaltyLimit"),
        },
        {
            "actualCost": maintenance_expected["loyaltyActualCost"],
            "copper": maintenance_expected["loyaltyCopper"],
            "loyalty": maintenance_expected["loyalty"],
            "loyaltyLimit": maintenance_expected["loyaltyLimit"],
        },
    )
    check(
        "maintenance.energy.request",
        build_use_general_item_payload(
            maintenance_fixture["generalId"],
            maintenance_fixture["generalItemId"],
            maintenance_fixture["generalItemCount"],
        ).hex(),
        maintenance_fixture["generalItemPayloadHex"],
    )
    energy_result = parse_use_general_item_response(
        bytes.fromhex(maintenance_fixture["generalItemResponseHex"]),
        item_names=inventory_item_names,
        equipment_templates=inventory_equipment_templates,
    )
    check(
        "maintenance.energy.parse",
        {
            "success": energy_result.get("success"),
            "itemCount": (energy_result.get("inventory") or {}).get(
                "itemCount"
            ),
        },
        {
            "success": True,
            "itemCount": maintenance_expected["energyInventoryItemCount"],
        },
    )
    check(
        "maintenance.resource.request",
        build_resource_exchange_payload(
            maintenance_fixture["resourceDirection"],
            maintenance_fixture["resourceAmount"],
        ).hex(),
        maintenance_fixture["resourcePayloadHex"],
    )
    resource_result = parse_resource_exchange_response(
        bytes.fromhex(maintenance_fixture["resourceResponseHex"])
    )
    check(
        "maintenance.resource.parse",
        {
            "success": resource_result.get("success"),
            "copper": resource_result.get("copper"),
            "food": resource_result.get("food"),
        },
        {
            "success": True,
            "copper": maintenance_expected["resourceCopper"],
            "food": maintenance_expected["resourceFood"],
        },
    )
    check(
        "maintenance.mail.request",
        build_delete_all_mail_payload().hex(),
        maintenance_fixture["deleteMailPayloadHex"],
    )
    mail_result = parse_delete_mail_response(
        bytes.fromhex(maintenance_fixture["deleteMailResponseHex"])
    )
    check(
        "maintenance.mail.parse",
        {
            "success": mail_result.get("success"),
            "remaining": mail_result.get("remaining"),
        },
        {
            "success": True,
            "remaining": maintenance_expected["mailRemaining"],
        },
    )
    check(
        "maintenance.discard.request",
        build_discard_inventory_payload(
            maintenance_fixture["discardKind"],
            maintenance_fixture["discardObjectId"],
            maintenance_fixture["discardCount"],
        ).hex(),
        maintenance_fixture["discardPayloadHex"],
    )
    discard_result = parse_discard_inventory_response(
        bytes.fromhex(maintenance_fixture["discardResponseHex"]),
        item_names=inventory_item_names,
        equipment_templates=inventory_equipment_templates,
    )
    check(
        "maintenance.discard.parse",
        {
            "success": discard_result.get("success"),
            "message": discard_result.get("message"),
            "itemCount": (discard_result.get("inventory") or {}).get(
                "itemCount"
            ),
        },
        {
            "success": True,
            "message": maintenance_expected["discardMessage"],
            "itemCount": maintenance_expected[
                "discardInventoryItemCount"
            ],
        },
    )
    check(
        "maintenance.inventoryUse.request",
        build_use_inventory_item_payload(
            maintenance_fixture["inventoryItemId"],
            maintenance_fixture["inventoryItemCount"],
        ).hex(),
        maintenance_fixture["inventoryItemPayloadHex"],
    )
    check(
        "maintenance.equipment.safety",
        {
            "safe": equipment_is_safe_to_discard(
                {
                    "instanceId": 1,
                    "famous": False,
                    "strengthen": 0,
                    "extraText": "",
                    "level": 10,
                    "quality": 1,
                },
                max_quality=1,
                max_level=60,
            ),
            "strengthened": equipment_is_safe_to_discard(
                {
                    "instanceId": 1,
                    "famous": False,
                    "strengthen": 1,
                    "extraText": "",
                    "level": 10,
                    "quality": 1,
                },
                max_quality=1,
                max_level=60,
            ),
        },
        {
            "safe": (True, ""),
            "strengthened": (False, "已经强化"),
        },
    )
    for fixture_name in (
        "dailyNationalCity8404State",
        "dailyNationalCity8404Commandery",
        "dailyNationalCity8404County",
        "dailyNationalCity8404Small",
    ):
        national_fixture = fixtures[fixture_name]
        national_page = parse_national_city_page(
            bytes.fromhex(national_fixture["responseHex"]),
            national_fixture["requestedCategory"],
        )
        national_city = (national_page.get("cities") or [{}])[0]
        check(
            f"daily.national.{national_fixture['requestedCategory']}",
            {
                "category": national_page.get("category"),
                **{
                    key: national_city.get(key)
                    for key in ("name", "kind", "x", "y")
                },
            },
            national_fixture["expected"],
        )
    owned_city_fixture = fixtures["dailyOwnedCity8318Nanhua"]
    check(
        "daily.ownedCity.request",
        build_owned_city_list_payload(owned_city_fixture["roleId"]).hex(),
        owned_city_fixture["requestHex"],
    )
    owned_city_result = parse_owned_city_list(
        bytes.fromhex(owned_city_fixture["responseHex"])
    )
    owned_city = (owned_city_result.get("cities") or [{}])[0]
    check(
        "daily.ownedCity.parse",
        {
            "id": owned_city.get("cityId"),
            **{
                key: owned_city.get(key)
                for key in (
                    "kindCode",
                    "name",
                    "x",
                    "y",
                    "ownerName",
                    "ownerLevel",
                )
            },
        },
        owned_city_fixture["expected"],
    )
    salary_fixture = fixtures["dailySalaryA14bSuccess"]
    check(
        "daily.salary.request",
        build_salary_payload().hex(),
        salary_fixture["requestHex"],
    )
    salary_result = parse_salary_receipt(
        bytes.fromhex(salary_fixture["responseHex"])
    )
    check(
        "daily.salary.parse",
        {
            key: salary_result.get(key)
            for key in salary_fixture["expected"]
        },
        salary_fixture["expected"],
    )
    for fixture_name in (
        "dailyGeneralVisitA273Rejected",
        "dailyGeneralVisitA273AlreadyVisited",
    ):
        visit_fixture = fixtures[fixture_name]
        visit_result = parse_general_visit_receipt(
            bytes.fromhex(visit_fixture["responseHex"])
        )
        check(
            f"daily.visit.{fixture_name}",
            {
                key: visit_result.get(key)
                for key in visit_fixture["expected"]
            },
            visit_fixture["expected"],
        )
    visit_page_fixture = fixtures["dailyGeneralVisitA271AlreadyVisited"]
    visit_page = parse_general_visit_page(
        bytes.fromhex(visit_page_fixture["responseHex"])
    )
    visit_page_expected = visit_page_fixture["expected"]
    check(
        "daily.visit.page",
        {
            "status": visit_page.get("status"),
            "message": visit_page.get("message"),
            "completed": general_visit_already_visited(
                visit_page.get("status"),
                visit_page.get("message"),
            ),
            "alreadyVisited": general_visit_already_visited(
                visit_page.get("status"),
                visit_page.get("message"),
            ),
            "candidateCount": len(visit_page.get("candidates") or []),
        },
        visit_page_expected,
    )
    citizen_session = {
        "roleState": {"officeIdUnsigned": 0x0100, "level": 30}
    }
    check(
        "daily.identity.rules",
        {
            "skipMessage": (
                national_citizen_daily_skip_result(citizen_session) or {}
            ).get("message"),
            "donation": country_donation_limits(citizen_session),
            "visitIds": normalize_general_visit_ids(
                ["123", "0x7b", "bad", "456", "789", "1000", "2000"]
            ),
        },
        {
            "skipMessage": "国民跳过",
            "donation": {
                "level": 30,
                "copper": 30000,
                "food": 90000,
            },
            "visitIds": ["123", "456", "789", "1000"],
        },
    )
    activity_fixture = fixtures["dailyActivityE200"]
    activity = parse_e200_daily_activity(
        bytes.fromhex(activity_fixture["responseHex"])
    )
    check(
        "daily.activity.e200",
        {
            key: activity.get("treasureOccupied", {}).get(key)
            for key in activity_fixture["expected"]
        },
        activity_fixture["expected"],
    )
    arena_fixture = fixtures["dailyArenaDuplicateE266"]
    arena_result = parse_arena_coin_claim_response(
        bytes.fromhex(arena_fixture["responseHex"])
    )
    check(
        "daily.arena.duplicate",
        {
            key: arena_result.get(key)
            for key in arena_fixture["expected"]
        },
        arena_fixture["expected"],
    )
    sign_fixture = fixtures["dailySignIn8134Duplicate"]
    sign_result = parse_daily_sign_in_packets(
        [
            {
                "opcode": int(sign_fixture["responseOpcode"], 0),
                "payload": bytes.fromhex(sign_fixture["responseHex"]),
            }
        ]
    )
    check(
        "daily.signIn.duplicate",
        {
            key: sign_result.get(key)
            for key in sign_fixture["expected"]
        },
        sign_fixture["expected"],
    )
    diamond_fixture = fixtures["dailyDiamondExpired8134"]
    diamond_result = parse_daily_diamond_box_response(
        bytes.fromhex(diamond_fixture["responseHex"])
    )
    check(
        "daily.diamond.expired",
        {
            key: diamond_result.get(key)
            for key in diamond_fixture["expected"]
        },
        diamond_fixture["expected"],
    )
    internal_requests = fixtures["internalAffairsRequests"]
    internal_request_expected = internal_requests["expected"]
    check(
        "internal.fief.request",
        build_fief_query_payload(internal_requests["fiefId"]).hex(),
        internal_request_expected["fiefQueryPayloadHex"],
    )
    check(
        "internal.building.request",
        build_building_action_payload(
            internal_requests["fiefId"],
            internal_requests["buildingSlot"],
            internal_requests["buildingType"],
        ).hex(),
        internal_request_expected["buildingActionPayloadHex"],
    )
    check(
        "internal.technology.request",
        build_technology_upgrade_payload(
            internal_requests["academyFiefId"],
            internal_requests["academySlot"],
            internal_requests["technologyId"],
            internal_requests["technologyLevel"],
        ).hex(),
        internal_request_expected["technologyUpgradePayloadHex"],
    )
    check(
        "internal.countryDonation.request",
        build_country_donation_payload(
            copper=internal_requests["countryCopper"],
        ).hex(),
        internal_request_expected["countryDonationPayloadHex"],
    )
    check(
        "internal.technologyDonation.request",
        build_technology_donation_payload(
            internal_requests["technologyDonation"],
        ).hex(),
        internal_request_expected["technologyDonationPayloadHex"],
    )

    building_fixture = fixtures["internalAffairsBuilding8200"]
    building_result = parse_8200_building_result(
        bytes.fromhex(building_fixture["responseHex"])
    )
    last_building = (building_result.get("buildings") or [{}])[-1]
    check(
        "internal.building.parse",
        {
            "success": building_result.get("success"),
            "fiefId": building_result.get("fiefId"),
            "buildingCount": len(building_result.get("buildings") or []),
            "lastSlot": last_building.get("slot"),
            "lastType": last_building.get("type"),
            "lastName": last_building.get("name"),
        },
        building_fixture["expected"],
    )
    fief_fixture = fixtures["internalAffairsFief8246"]
    fief_result = parse_8246_fief_result(
        bytes.fromhex(fief_fixture["responseHex"]),
        fief_fixture["expectedFiefId"],
    )
    check(
        "internal.fief.parse",
        {
            "success": fief_result.get("success"),
            "fiefId": fief_result.get("fiefId"),
            "fiefName": fief_result.get("fiefName"),
            "buildQueueCapacity": fief_result.get("buildQueueCapacity"),
            "buildingCount": len(fief_result.get("buildings") or []),
        },
        fief_fixture["expected"],
    )
    technology_fixture = fixtures["internalAffairsTechnology8004"]
    technology_states = parse_technology_states_from_8004(
        bytes.fromhex(technology_fixture["responseHex"])
    )
    researching = next(
        (row for row in technology_states if row.get("researching")),
        {},
    )
    check(
        "internal.technology.parse",
        {
            "technologyCount": len(technology_states),
            "firstLevel": (
                technology_states[0].get("level")
                if technology_states else None
            ),
            "researchingTechnologyId": researching.get("technologyId"),
            "researchingName": researching.get("name"),
            "researchingLevel": researching.get("level"),
            "researchingFiefId": researching.get("fiefId"),
            "researchingAcademyInstanceId": researching.get(
                "academyInstanceId"
            ),
            "researchingDeadlineMs": researching.get("deadlineMs"),
        },
        technology_fixture["expected"],
    )

    ministry_fixture = fixtures["ministryHubuVerifiedPlant"]
    check(
        "ministry.status.request",
        build_hubu_status_query_payload().hex(),
        ministry_fixture["statusQueryPayloadHex"],
    )
    check(
        "ministry.plant.request",
        build_hubu_batch_plant_payload(ministry_fixture["crop"]).hex(),
        ministry_fixture["plantPayloadHex"],
    )
    check(
        "ministry.garden.parse",
        parse_hubu_garden_status(
            bytes.fromhex(ministry_fixture["emptyGardenResponseHex"])
        ),
        ministry_fixture["expected"]["garden"],
    )
    ministry_receipt = parse_hubu_plant_response(
        bytes.fromhex(ministry_fixture["plantResponseHex"])
    )
    check(
        "ministry.plant.parse",
        {
            key: ministry_receipt.get(key)
            for key in ministry_fixture["expected"]["receipt"]
        },
        ministry_fixture["expected"]["receipt"],
    )
    ministry_safety_fixture = fixtures["ministrySettingsSafety"]
    ministry_settings = normalize_ministry_settings(
        ministry_safety_fixture["input"]
    )
    ministry_safety_expected = ministry_safety_fixture["expected"]
    ministry_setting_keys = (
        "cropEnabled",
        "crop",
        "highPriority",
        "stealEnabled",
        "courtesyEnabled",
        "salaryRefresh",
    )
    check(
        "ministry.settings.normalize",
        {
            key: ministry_settings.get(key)
            for key in ministry_setting_keys
        },
        {
            key: ministry_safety_expected[key]
            for key in ministry_setting_keys
        },
    )
    check(
        "ministry.settings.safety",
        {
            "plantingAllowed": ministry_planting_allowed(ministry_settings),
            "unconfirmedActions": unconfirmed_ministry_actions(
                ministry_settings
            ),
        },
        {
            "plantingAllowed": ministry_safety_expected["plantingAllowed"],
            "unconfirmedActions": ministry_safety_expected[
                "unconfirmedActions"
            ],
        },
    )
    try:
        build_hubu_batch_plant_payload("草药")
        unverified_crop_rejected = False
    except RuntimeError:
        unverified_crop_rejected = True
    check(
        "ministry.unverified.failClosed",
        unverified_crop_rejected,
        True,
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
