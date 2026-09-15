from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

import dwpm_core.facade as facade_module
from dwpm_core import create_hosted_core
from dwpm_core.features.ministries import (
    build_hubu_harvest_payload,
    build_libu_delegate_payload,
    parse_hubu_garden_status,
    parse_hubu_harvest_response,
    parse_libu_delegate_response,
    parse_libu_task_list,
    parse_ministry_officials,
)
from shared_raw_http_test_host import (
    FIXTURE_GAME_HTTP,
    RawHttpGameCommandHostMixin,
)


FIXTURES = json.loads(
    (ROOT / "shared_core" / "protocol_parity_fixtures.json").read_text(
        encoding="utf-8"
    )
)["fixtures"]
GARDEN_049 = FIXTURES["ministryHubuGardenOccupied049"]["responseHex"]
GARDEN_062 = FIXTURES["ministryHubuVerifiedPlant"]["emptyGardenResponseHex"]
GARDEN_NAMED_176 = FIXTURES["ministryHubuGardenNamedFief176"]
PLANT_065 = FIXTURES["ministryHubuVerifiedPlant"]["plantResponseHex"]
HARVEST_FLOWS = FIXTURES["ministryHubuHarvestFlows"]
TASK_LIST_086 = FIXTURES["ministryLibuTaskList086"]["responseHex"]
TASK_LIST_096 = FIXTURES["ministryLibuTaskList096"]["responseHex"]
OFFICIALS_088 = FIXTURES["ministryOfficials088"]["responseHex"]
OFFICIALS_099 = FIXTURES["ministryOfficials099"]["responseHex"]
DELEGATE_091 = FIXTURES["ministryLibuDelegate091"]


def _game_response(request_opcode: int, response_opcode: int, payload_hex):
    packets = (
        []
        if payload_hex is None
        else [{"opcode": response_opcode, "payloadHex": payload_hex}]
    )
    return json.dumps({
        "status": 200,
        "body": {
            "ok": True,
            "gameCommandFact": {
                "requestOpcode": request_opcode,
                "httpCode": 200,
                "httpOk": True,
                "packets": packets,
            },
        },
    })


def _occupied_after_plant_hex(pool: int = 1213) -> str:
    """Flow-062 garden with plot 0 swapped for one occupied 32B record."""
    garden = bytearray.fromhex(GARDEN_062)
    garden[12:16] = int(pool).to_bytes(4, "big")
    record = (
        b"\x00\x00\x01"
        + (36000).to_bytes(4, "big")
        + (36000).to_bytes(4, "big")
        + b"\x00"
        + (100).to_bytes(2, "big")
        + b"\x00" * 18
    )
    assert len(record) == 32
    return (bytes(garden[:26]) + record + bytes(garden[33:96]) + bytes(garden[96:])).hex()


def _garden_with_pool(pool: int) -> str:
    garden = bytearray.fromhex(GARDEN_062)
    garden[12:16] = int(pool).to_bytes(4, "big")
    return bytes(garden).hex()


def _delegate_receipt_for(official_id: int) -> str:
    """Flow-091 receipt with the i64 official echo re-pointed."""
    payload = bytearray.fromhex(DELEGATE_091["responseHex"])
    payload[-9:-1] = int(official_id).to_bytes(8, "big")
    return bytes(payload).hex()


def _delegate_rejection_hex(message: str) -> str:
    """Non-zero status + UTF message: a definite server-side rejection."""
    encoded = message.encode("utf-8")
    return (b"\x01" + len(encoded).to_bytes(2, "big") + encoded).hex()


def _task_list_all_busy(response_hex: str) -> str:
    data = bytearray.fromhex(response_hex)
    position = 34
    for _ in range(data[33]):
        name_length = int.from_bytes(data[position + 6:position + 8], "big")
        tail = position + 8 + name_length
        data[tail + 10] = 1
        position = tail + 32
    return bytes(data).hex()


class FakeExecution:
    operation_id = "op_ministry_fixture"

    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def mark_request_sent(self, metadata=None) -> None:
        self.sent.append(dict(metadata or {}))

    def publish_progress(self, _progress: int, _details=None) -> None:
        return None

    def raise_if_cancelled(self) -> None:
        return None

    def wait(self, _seconds: float) -> None:
        return None


class _BridgeBase(RawHttpGameCommandHostMixin):
    def __init__(self) -> None:
        self.commands: list[dict] = []

    def executionOwnerActive(self):
        return True

    def tryAcquireNetworkOperation(self, account_ref):
        return account_ref == "202"

    def releaseNetworkOperation(self, account_ref):
        return None

    def executeNetworkOperation(self, *_args):
        raise AssertionError("六部路由必须走共享原始命令端口")

    @property
    def opcodes(self) -> list[int]:
        return [int(command["opcode"]) for command in self.commands]


class MinistryParserCaptureTests(unittest.TestCase):
    def test_garden_status_parses_real_captures_per_plot(self) -> None:
        occupied = parse_hubu_garden_status(bytes.fromhex(GARDEN_049))
        self.assertEqual(
            occupied, FIXTURES["ministryHubuGardenOccupied049"]["expected"]
        )
        self.assertEqual(occupied["unlockedCount"], 5)
        self.assertEqual(occupied["occupiedCount"], 5)
        # 坑 5-9 未解锁但在报文里列为空坑条目；可种空坑必须是已解锁余量。
        self.assertEqual(occupied["emptyCount"], 0)
        self.assertEqual(
            occupied["plots"][0],
            {
                "plotIndex": 0,
                "occupied": True,
                "cropId": 1,
                "totalSeconds": 36000,
                "remainingSeconds": 0,
                "percent": 53,
                "plantCount": 100,
            },
        )
        self.assertEqual(occupied["plots"][9], {"plotIndex": 9, "occupied": False})

        empty = parse_hubu_garden_status(bytes.fromhex(GARDEN_062))
        self.assertEqual(
            empty, FIXTURES["ministryHubuVerifiedPlant"]["expected"]["garden"]
        )
        self.assertEqual(empty["emptyCount"], 5)
        self.assertEqual(empty["salaryPool"], 1313)

    def test_garden_status_parses_occupied_plots_with_a_gap(self) -> None:
        # 设备账号 202 的真实 0xe320：坑 1 空闲、坑 0/2/3/4 占用。
        # "占用记录集中在前"的旧读法在坑 1 的 7B 空条目上错位，随后读出的
        # 坑序号 0 触发"占用坑序号异常"，六部因此停摆数小时；真实布局是
        # 每个坑位按序号原地排列（占用 32B / 空闲 7B）。
        payload = bytes.fromhex(
            "00000001000000000000002800000a210032020005002800"
            "00" "0a"
            "00" "0001" + format(36000, "08x") + format(21693, "08x")
            + "0064006443" + "00" * 14 + "0032"
            + "01" + "00" * 6
            + "02" "0001" + format(36000, "08x") + format(0, "08x")
            + "004a00641e" + "00" * 14 + "0032"
            + "03" "0001" + format(36000, "08x") + format(9269, "08x")
            + "006400642e" + "00" * 14 + "0032"
            + "04" "0001" + format(36000, "08x") + format(17776, "08x")
            + "006400643c" + "00" * 14 + "0032"
            + ("05" + "00" * 6)
            + ("06" + "00" * 6)
            + ("07" + "00" * 6)
            + ("08" + "00" * 6)
            + ("09" + "00" * 6)
            + "0200000008000100000d0001000000020000000300000004"
            + "00000005000000060000000700000008000000090000000a"
            + "0000000b0000000c0000000d0000"
        )
        garden = parse_hubu_garden_status(payload)
        self.assertEqual(garden["occupiedCount"], 4)
        self.assertEqual(garden["emptyCount"], 1)
        self.assertEqual(
            [
                (plot["plotIndex"], plot["occupied"])
                for plot in garden["plots"]
            ],
            [
                (0, True), (1, False), (2, True), (3, True), (4, True),
                (5, False), (6, False), (7, False), (8, False), (9, False),
            ],
        )
        mature = garden["plots"][2]
        self.assertEqual(mature["remainingSeconds"], 0)
        self.assertEqual(mature["cropId"], 1)

    def test_harvest_requests_and_receipts_match_real_captures(self) -> None:
        pool = 500  # flow 049 菜地报文里的采摘前俸禄池
        for key in ("052", "054", "056", "058", "059"):
            fixture = HARVEST_FLOWS[key]
            expected = fixture["expected"]
            self.assertEqual(
                build_hubu_harvest_payload(
                    expected["plotIndex"], expected["hostId"]
                ).hex(),
                fixture["requestPayloadHex"],
            )
            receipt = parse_hubu_harvest_response(
                bytes.fromhex(fixture["responseHex"])
            )
            for field, value in expected.items():
                self.assertEqual(receipt[field], value, f"{key}.{field}")
            #  pool 链式吻合：每次回执的新池子 = 旧池子 + 本坑收益。
            pool += expected["gain"]
            self.assertEqual(receipt["newPool"], pool)

    def test_libu_task_lists_parse_real_captures(self) -> None:
        self.assertEqual(
            parse_libu_task_list(bytes.fromhex(TASK_LIST_086)),
            FIXTURES["ministryLibuTaskList086"]["expected"],
        )
        parsed = parse_libu_task_list(bytes.fromhex(TASK_LIST_096))
        self.assertEqual(parsed, FIXTURES["ministryLibuTaskList096"]["expected"])
        by_id = {task["taskId"]: task for task in parsed["tasks"]}
        self.assertEqual(by_id[1]["state"], 1)
        self.assertEqual(by_id[5]["state"], 1)
        self.assertEqual(by_id[3]["state"], 0)

    def test_delegate_requests_and_receipts_match_real_captures(self) -> None:
        for name in ("ministryLibuDelegate091", "ministryLibuDelegate094"):
            fixture = FIXTURES[name]
            self.assertEqual(
                build_libu_delegate_payload(
                    fixture["taskId"], fixture["officialId"]
                ).hex(),
                fixture["requestPayloadHex"],
            )
            receipt = parse_libu_delegate_response(
                bytes.fromhex(fixture["responseHex"]),
                task_id=fixture["taskId"],
                official_id=fixture["officialId"],
            )
            self.assertTrue(receipt["success"])
            self.assertEqual(receipt["taskId"], fixture["expected"]["taskId"])
            self.assertEqual(
                receipt["officialId"], fixture["expected"]["officialId"]
            )
            self.assertEqual(receipt["task"], fixture["expected"]["task"])

    def test_delegate_receipt_echo_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "回显与委派请求不一致"):
            parse_libu_delegate_response(
                bytes.fromhex(DELEGATE_091["responseHex"]),
                task_id=DELEGATE_091["taskId"],
                official_id=999,
            )

    def test_officials_parse_busy_state_from_real_captures(self) -> None:
        idle = parse_ministry_officials(bytes.fromhex(OFFICIALS_088))
        self.assertEqual(idle, FIXTURES["ministryOfficials088"]["expected"])
        self.assertTrue(all(row["idle"] for row in idle["officials"]))

        busy = parse_ministry_officials(bytes.fromhex(OFFICIALS_099))
        self.assertEqual(busy, FIXTURES["ministryOfficials099"]["expected"])
        by_name = {row["name"]: row for row in busy["officials"]}
        # 091 委派任务 1 给束边、094 委派任务 5 给柯温；其余在职文官为 0。
        self.assertEqual(by_name["束边"]["busyTaskId"], 1)
        self.assertFalse(by_name["束边"]["idle"])
        self.assertEqual(by_name["柯温"]["busyTaskId"], 5)
        self.assertFalse(by_name["柯温"]["idle"])
        self.assertTrue(by_name["殷懏"]["idle"])
        self.assertTrue(by_name["轩辕冉"]["idle"])

    def test_unverified_shapes_fail_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "尚未确认的记录结构"):
            parse_hubu_garden_status(bytes.fromhex(GARDEN_049) + b"\x00")
        with self.assertRaisesRegex(RuntimeError, "尾部含有未确认数据"):
            parse_libu_task_list(bytes.fromhex(TASK_LIST_086) + b"\x01")
        with self.assertRaisesRegex(RuntimeError, "响应过短"):
            parse_ministry_officials(bytes.fromhex(OFFICIALS_088)[:10])
        with self.assertRaisesRegex(RuntimeError, "成功回执结构异常"):
            parse_hubu_harvest_response(
                bytes.fromhex(HARVEST_FLOWS["052"]["responseHex"]) + b"\x00"
            )
        with self.assertRaisesRegex(RuntimeError, "采摘坑位异常"):
            build_hubu_harvest_payload(10, 202)
        with self.assertRaisesRegex(RuntimeError, "缺少角色 ID"):
            build_hubu_harvest_payload(0, 0)

    def test_garden_status_parses_named_fief_variant_from_device(self) -> None:
        parsed = parse_hubu_garden_status(
            bytes.fromhex(GARDEN_NAMED_176["responseHex"])
        )
        # 账号 176（户部 2 级、封地“乌吉”）的真机字节：u8 名长 + 名字 +
        # u8 总坑数。旧解析器把 [24:26] 当 u16 坑数读出 1764 而停摆。
        self.assertEqual(parsed, GARDEN_NAMED_176["expected"])
        self.assertEqual(parsed["gardenName"], "乌吉")
        self.assertEqual(parsed["emptyCount"], 5)

    def test_garden_status_named_variant_with_occupied_plots(self) -> None:
        base = bytes.fromhex(GARDEN_049)
        named = base[:24] + b"\x06" + "乌吉".encode() + base[25:]
        parsed = parse_hubu_garden_status(named)
        self.assertEqual(parsed["gardenName"], "乌吉")
        self.assertEqual(parsed["occupiedCount"], 5)
        self.assertEqual(parsed["plots"][0]["cropId"], 1)

    def test_garden_status_invalid_name_encoding_fails_closed(self) -> None:
        base = bytes.fromhex(GARDEN_062)
        mutated = base[:24] + b"\x02\xe4\xe4" + base[26:]
        with self.assertRaisesRegex(RuntimeError, "封地名不是 UTF-8"):
            parse_hubu_garden_status(mutated)

    def test_garden_status_rejection_carries_bounded_diagnostics(self) -> None:
        payload = bytearray.fromhex(GARDEN_062)
        payload[25] = 0x0B  # u8 总坑数 10 → 11
        mutated = bytes(payload)
        with self.assertRaises(RuntimeError) as raised:
            parse_hubu_garden_status(mutated)
        message = str(raised.exception)
        self.assertIn("菜地数量变化：11", message)
        self.assertIn(f"len={len(mutated)}", message)
        self.assertIn(mutated[:48].hex(), message)


class SharedMinistryGardenCourtesyTests(unittest.TestCase):
    def _make_facade(self, bridge):
        directory = tempfile.TemporaryDirectory()
        facade = create_hosted_core(
            str(Path(directory.name) / "operations.json"), bridge
        )
        facade.account_record_upsert({
            "accountRef": "202",
            "id": 202,
            "enabled": True,
            "loginState": "REAL_PROTOCOL_ONLINE",
            "session": {
                "accountId": 202,
                "sourceMode": 1,
                "publicState": {
                    "gameHttp": FIXTURE_GAME_HTTP,
                    "lastValidatedAt": "1000",
                    "savedTasksStarted": "true",
                },
            },
        })
        self.addCleanup(facade.close)
        self.addCleanup(directory.cleanup)
        return facade

    def _wait(self, facade, operation_id: str) -> dict:
        for _ in range(200):
            operation = facade.operation_status(operation_id)["operation"]
            if operation["status"] not in {"QUEUED", "RUNNING"}:
                return operation
            time.sleep(0.005)
        self.fail("operation did not finish")

    def _plant(self, facade, request_id: str) -> dict:
        response = facade.dispatch(
            "POST",
            "/api/liubu/hubu/plant",
            {
                "accountRef": "202",
                "confirm": "hubu-batch-plant",
                "crop": "稻谷",
            },
            {"requestId": request_id},
        )
        self.assertEqual(response.status, 202)
        return self._wait(facade, response.body["operationId"])

    def _configure_courtesy_tick(self, facade) -> None:
        facade.configure_resident_automation_from_habits("202", {
            "config": {"autoStart": True, "startHour": 0, "dailyLimit": 3},
            "ministry": {
                "cropEnabled": False,
                "stealEnabled": False,
                "courtesyEnabled": True,
                "salaryRefresh": False,
            },
        })
        facade.set_resident_automation_activation("202", True, ["ministry"])

    def _run_ministry_tick(self, facade) -> dict:
        return facade._run_automation_recovery_tick(  # noqa: SLF001
            FakeExecution(), "202", {"allowedFeatures": ["ministry"]}
        )

    def _pending(self, facade, field: str) -> dict:
        record = json.loads(facade.account_record_json("202"))["account"]
        return json.loads(record["session"]["publicState"].get(field) or "{}")

    def _success_records(self, facade) -> list:
        record = json.loads(facade.account_record_json("202"))["account"]
        return json.loads(
            record["session"]["publicState"].get("successRecordsJson") or "[]"
        )

    def test_harvests_every_mature_plot_then_plants(self) -> None:
        harvest_replies = {
            int(HARVEST_FLOWS[key]["expected"]["plotIndex"]): HARVEST_FLOWS[key][
                "responseHex"
            ]
            for key in ("052", "054", "056", "058", "059")
        }

        class Bridge(_BridgeBase):
            def __init__(self) -> None:
                super().__init__()
                self.status_calls = 0

            def executeGameCommand(self, _account_ref, command_json, _context):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode == 0x6320:
                    self.status_calls += 1
                    payload = (
                        GARDEN_049
                        if self.status_calls == 1
                        else _occupied_after_plant_hex()
                    )
                    return _game_response(opcode, 0xE320, payload)
                if opcode == 0x6324:
                    plot = int(command["payloadHex"][:2], 16)
                    return _game_response(
                        opcode, 0xE324, harvest_replies[plot]
                    )
                if opcode == 0x6328:
                    return _game_response(opcode, 0xE328, PLANT_065)
                raise AssertionError(f"unexpected opcode {opcode:#x}")

        facade = self._make_facade(Bridge())
        result = self._plant(facade, "hubu-harvest-plant")

        self.assertEqual(result["status"], "SUCCEEDED", result)
        raw = result["result"]["result"]["raw"]
        self.assertEqual(raw["phase"], "planted")
        self.assertEqual(len(raw["harvests"]), 5)
        self.assertEqual(
            sum(int(receipt["gain"]) for receipt in raw["harvests"]), 813
        )
        self.assertEqual(raw["occupiedAfter"], 1)
        self.assertEqual(raw["garden"]["salaryPool"], 1213)
        records = self._success_records(facade)
        actions = [
            (r["category"], (r.get("detail") or {}).get("action"))
            for r in records
        ]
        self.assertEqual(actions.count(("六部", "harvest")), 5)
        self.assertEqual(actions.count(("六部", "plant")), 1)
        harvest = next(
            r for r in records if (r.get("detail") or {}).get("action") == "harvest"
        )
        self.assertIn("采摘坑位1成功", harvest["message"])
        self.assertIn("俸禄+159株", harvest["message"])
        plant = next(
            r for r in records if (r.get("detail") or {}).get("action") == "plant"
        )
        self.assertIn("已种植稻谷", plant["message"])
        self.assertIn("坑位1", plant["message"])
        self.assertIn("俸禄池1213", plant["message"])

    def test_harvest_command_bytes_and_sequence_match_capture(self) -> None:
        harvest_replies = {
            int(HARVEST_FLOWS[key]["expected"]["plotIndex"]): HARVEST_FLOWS[key][
                "responseHex"
            ]
            for key in ("052", "054", "056", "058", "059")
        }

        class Bridge(_BridgeBase):
            def __init__(self) -> None:
                super().__init__()
                self.status_calls = 0

            def executeGameCommand(self, _account_ref, command_json, _context):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode == 0x6320:
                    self.status_calls += 1
                    payload = (
                        GARDEN_049
                        if self.status_calls == 1
                        else _occupied_after_plant_hex()
                    )
                    return _game_response(opcode, 0xE320, payload)
                if opcode == 0x6324:
                    plot = int(command["payloadHex"][:2], 16)
                    return _game_response(
                        opcode, 0xE324, harvest_replies[plot]
                    )
                if opcode == 0x6328:
                    return _game_response(opcode, 0xE328, PLANT_065)
                raise AssertionError(f"unexpected opcode {opcode:#x}")

        bridge = Bridge()
        facade = self._make_facade(bridge)
        result = self._plant(facade, "hubu-harvest-sequence")

        self.assertEqual(result["status"], "SUCCEEDED", result)
        self.assertEqual(
            bridge.opcodes,
            [0x6320, 0x6324, 0x6324, 0x6324, 0x6324, 0x6324, 0x6328, 0x6320],
        )
        harvest_commands = [
            command for command in bridge.commands if int(command["opcode"]) == 0x6324
        ]
        self.assertEqual(
            [command["payloadHex"] for command in harvest_commands],
            [HARVEST_FLOWS[key]["requestPayloadHex"] for key in (
                "052", "054", "056", "058", "059"
            )],
        )

    def test_lost_harvest_receipt_isolates_then_recovers_read_only(self) -> None:
        class Bridge(_BridgeBase):
            def __init__(self) -> None:
                super().__init__()
                self.status_calls = 0
                self.drop_first_harvest = True

            def executeGameCommand(self, _account_ref, command_json, _context):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode == 0x6320:
                    self.status_calls += 1
                    if self.status_calls == 1:
                        payload = GARDEN_049
                    elif self.status_calls in {2, 3}:
                        payload = GARDEN_062
                    else:
                        payload = _occupied_after_plant_hex()
                    return _game_response(opcode, 0xE320, payload)
                if opcode == 0x6324:
                    if self.drop_first_harvest:
                        self.drop_first_harvest = False
                        return _game_response(opcode, 0xE324, None)
                    raise AssertionError("采摘请求不得重发")
                if opcode == 0x6328:
                    return _game_response(opcode, 0xE328, PLANT_065)
                raise AssertionError(f"unexpected opcode {opcode:#x}")

        bridge = Bridge()
        facade = self._make_facade(bridge)

        first = self._plant(facade, "hubu-harvest-uncertain")
        self.assertEqual(first["status"], "UNCERTAIN", first)
        pending = self._pending(facade, "ministryPendingHarvestJson")
        self.assertEqual(pending["sendState"], "uncertain")
        self.assertEqual(pending["plotIndex"], 0)
        self.assertEqual(bridge.opcodes, [0x6320, 0x6324])

        bridge.commands.clear()
        recovered = self._plant(facade, "hubu-harvest-recover")
        self.assertEqual(recovered["status"], "SUCCEEDED", recovered)
        # 恢复只读核对（坑已空）→ 正常种菜；全程不得重发 0x6324。
        self.assertEqual(bridge.opcodes, [0x6320, 0x6320, 0x6328, 0x6320])
        self.assertEqual(self._pending(facade, "ministryPendingHarvestJson"), {})
        self.assertEqual(
            recovered["result"]["result"]["raw"]["phase"], "planted"
        )

    def test_unresolved_harvest_pending_never_replays(self) -> None:
        class Bridge(_BridgeBase):
            def executeGameCommand(self, _account_ref, command_json, _context):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode == 0x6320:
                    return _game_response(opcode, 0xE320, GARDEN_049)
                raise AssertionError("待决采摘未确认前禁止任何写请求")

        bridge = Bridge()
        facade = self._make_facade(bridge)
        facade._update_account_public_state(  # noqa: SLF001
            "202",
            {
                "ministryPendingHarvestJson": json.dumps({
                    "kind": "harvest",
                    "sendState": "sending",
                    "createdAtMillis": 1,
                    "plotIndex": 0,
                    "hostId": 202,
                    "cropId": 1,
                })
            },
        )

        result = self._plant(facade, "hubu-harvest-unresolved")
        self.assertEqual(result["status"], "FAILED", result)
        self.assertEqual(
            result["error"]["code"]
            if isinstance(result.get("error"), dict)
            else result.get("errorCode"),
            "MINISTRY_HARVEST_PENDING_UNRESOLVED",
        )
        self.assertEqual(bridge.opcodes, [0x6320])
        pending = self._pending(facade, "ministryPendingHarvestJson")
        self.assertEqual(pending["sendState"], "uncertain")

    def test_pool_insufficient_never_sends_plant(self) -> None:
        class Bridge(_BridgeBase):
            def executeGameCommand(self, _account_ref, command_json, _context):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode == 0x6320:
                    return _game_response(opcode, 0xE320, _garden_with_pool(50))
                raise AssertionError("俸禄池不足时禁止任何写请求")

        bridge = Bridge()
        facade = self._make_facade(bridge)
        result = self._plant(facade, "hubu-pool-insufficient")

        self.assertEqual(result["status"], "SUCCEEDED", result)
        raw = result["result"]["result"]["raw"]
        self.assertEqual(raw["phase"], "pool-insufficient")
        self.assertIn("只采不种", result["result"]["result"]["message"])
        self.assertEqual(bridge.opcodes, [0x6320])

    def test_courtesy_tick_delegates_first_idle_official(self) -> None:
        class Bridge(_BridgeBase):
            def executeGameCommand(self, _account_ref, command_json, _context):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode == 0x6340:
                    return _game_response(opcode, 0xE340, TASK_LIST_086)
                if opcode == 0x6301:
                    return _game_response(opcode, 0xE301, OFFICIALS_088)
                if opcode == 0x6342:
                    return _game_response(
                        opcode, 0xE342, _delegate_receipt_for(564)
                    )
                raise AssertionError(f"unexpected opcode {opcode:#x}")

        bridge = Bridge()
        facade = self._make_facade(bridge)
        self._configure_courtesy_tick(facade)

        result = self._run_ministry_tick(facade)
        self.assertEqual(result["feature"], "ministry")
        self.assertEqual(result["state"], "completed", result)
        self.assertIn("殷懏", result["message"])
        self.assertIn("征收[卓然]", result["message"])
        self.assertEqual(bridge.opcodes, [0x6340, 0x6301, 0x6342])
        # 工作流选第一个可委派任务（1）和第一个空闲文官（殷懏 564）。
        delegate_command = bridge.commands[-1]
        self.assertEqual(
            delegate_command["payloadHex"],
            build_libu_delegate_payload(1, 564).hex(),
        )
        self.assertEqual(self._pending(facade, "ministryPendingDelegateJson"), {})
        records = self._success_records(facade)
        delegates = [
            r for r in records
            if (r.get("detail") or {}).get("action") == "courtesy-delegate"
        ]
        self.assertEqual(len(delegates), 1)
        self.assertEqual(delegates[0]["category"], "六部")
        self.assertIn("已委派殷懏执行礼部任务「征收[卓然]」", delegates[0]["message"])

    def test_courtesy_tick_without_delegatable_task_sends_nothing(self) -> None:
        class Bridge(_BridgeBase):
            def executeGameCommand(self, _account_ref, command_json, _context):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode == 0x6340:
                    return _game_response(
                        opcode, 0xE340, _task_list_all_busy(TASK_LIST_086)
                    )
                raise AssertionError("没有可委派任务时不得查询文官或委派")

        bridge = Bridge()
        facade = self._make_facade(bridge)
        self._configure_courtesy_tick(facade)

        result = self._run_ministry_tick(facade)
        self.assertEqual(result["state"], "waiting", result)
        self.assertIn("没有可委派的任务", result["message"])
        self.assertEqual(bridge.opcodes, [0x6340])

    def test_courtesy_tick_without_idle_official_never_delegates(self) -> None:
        class Bridge(_BridgeBase):
            def executeGameCommand(self, _account_ref, command_json, _context):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode == 0x6340:
                    return _game_response(opcode, 0xE340, TASK_LIST_086)
                if opcode == 0x6301:
                    return _game_response(opcode, 0xE301, OFFICIALS_088)
                raise AssertionError("没有确认空闲的文官时禁止委派")

        bridge = Bridge()
        facade = self._make_facade(bridge)
        self._configure_courtesy_tick(facade)

        original = facade_module.parse_ministry_officials
        facade_module.parse_ministry_officials = lambda _payload: {
            "salaryPool": 1013,
            "officials": [
                {"officialId": 564, "name": "殷懏", "busyTaskId": 2, "idle": False},
                {"officialId": 563, "name": "轩辕冉", "busyTaskId": 4, "idle": False},
            ],
            "candidateCount": 0,
        }
        try:
            result = self._run_ministry_tick(facade)
        finally:
            facade_module.parse_ministry_officials = original

        self.assertEqual(result["state"], "waiting", result)
        self.assertIn("没有确认空闲的文官", result["message"])
        self.assertEqual(bridge.opcodes, [0x6340, 0x6301])

    def test_delegate_pending_recovers_from_task_list(self) -> None:
        class Bridge(_BridgeBase):
            def executeGameCommand(self, _account_ref, command_json, _context):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode == 0x6340:
                    return _game_response(opcode, 0xE340, TASK_LIST_096)
                raise AssertionError("待决委派未确认前禁止任何写请求")

        bridge = Bridge()
        facade = self._make_facade(bridge)
        self._configure_courtesy_tick(facade)
        facade._update_account_public_state(  # noqa: SLF001
            "202",
            {
                "ministryPendingDelegateJson": json.dumps({
                    "kind": "courtesy-delegate",
                    "sendState": "sending",
                    "createdAtMillis": 1,
                    "taskId": 1,
                    "taskName": "征收[卓然]",
                    "officialId": 6082,
                    "officialName": "束边",
                    "refreshAtMillis": 1789358400000,
                }, ensure_ascii=False)
            },
        )

        result = self._run_ministry_tick(facade)
        # flow 096 里任务 1 已是进行中 → 只读确认此前委派完成。
        self.assertEqual(result["state"], "completed", result)
        self.assertIn("束边", result["message"])
        self.assertEqual(bridge.opcodes, [0x6340])
        self.assertEqual(self._pending(facade, "ministryPendingDelegateJson"), {})

    def test_unresolved_delegate_pending_blocks_replay(self) -> None:
        class Bridge(_BridgeBase):
            def executeGameCommand(self, _account_ref, command_json, _context):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode == 0x6340:
                    return _game_response(opcode, 0xE340, TASK_LIST_096)
                raise AssertionError("待决委派未确认前禁止任何写请求")

        bridge = Bridge()
        facade = self._make_facade(bridge)
        self._configure_courtesy_tick(facade)
        facade._update_account_public_state(  # noqa: SLF001
            "202",
            {
                "ministryPendingDelegateJson": json.dumps({
                    "kind": "courtesy-delegate",
                    "sendState": "sending",
                    "createdAtMillis": 1,
                    "taskId": 2,
                    "taskName": "巡逻",
                    "officialId": 563,
                    "officialName": "轩辕冉",
                    "refreshAtMillis": 1789358400000,
                }, ensure_ascii=False)
            },
        )

        result = self._run_ministry_tick(facade)
        # flow 096 没有任务 2 的记录 → 无法确认，隔离等待，绝不重发。
        self.assertEqual(result["state"], "blocked", result)
        self.assertEqual(
            result["errorCode"], "MINISTRY_DELEGATE_PENDING_UNRESOLVED"
        )
        self.assertEqual(bridge.opcodes, [0x6340])
        pending = self._pending(facade, "ministryPendingDelegateJson")
        self.assertEqual(pending["sendState"], "uncertain")
        self.assertTrue(pending["requiresAttention"])

    def test_delegate_rejection_is_remembered_and_next_official_tried(
        self,
    ) -> None:
        delegate_targets: list[int] = []

        class Bridge(_BridgeBase):
            def executeGameCommand(self, _account_ref, command_json, _context):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode == 0x6340:
                    return _game_response(opcode, 0xE340, TASK_LIST_086)
                if opcode == 0x6301:
                    return _game_response(opcode, 0xE301, OFFICIALS_088)
                if opcode == 0x6342:
                    official_id = int.from_bytes(
                        bytes.fromhex(command["payloadHex"])[5:13], "big"
                    )
                    delegate_targets.append(official_id)
                    if official_id == 564:
                        return _game_response(
                            opcode,
                            0xE342,
                            _delegate_rejection_hex("在职郎中不能委派任务。"),
                        )
                    return _game_response(
                        opcode, 0xE342, _delegate_receipt_for(official_id)
                    )
                raise AssertionError(f"unexpected opcode {opcode:#x}")

        bridge = Bridge()
        facade = self._make_facade(bridge)
        self._configure_courtesy_tick(facade)
        original = facade_module.parse_ministry_officials
        facade_module.parse_ministry_officials = lambda _payload: {
            "salaryPool": 1013,
            "officials": [
                {"officialId": 564, "name": "殷懏", "busyTaskId": 0, "idle": True},
                {"officialId": 563, "name": "轩辕冉", "busyTaskId": 0, "idle": True},
            ],
            "candidateCount": 2,
        }
        try:
            first = self._run_ministry_tick(facade)
            # 被"不能委派"拒绝的文官已记住；同一 tick 内改派下一位成功。
            self.assertEqual(first["state"], "completed", first)
            self.assertIn("轩辕冉", first["message"])
            self.assertEqual(delegate_targets, [564, 563])
            self.assertEqual(
                self._pending(facade, "ministryDelegateIneligibleJson")[
                    "officialIds"
                ],
                [564],
            )

            # 第一轮圆满完成 → 六部唤醒时刻在 10 分钟后；拨回让它立即到期。
            record = json.loads(facade.account_record_json("202"))["account"]
            resident_state = json.loads(
                record["session"]["publicState"]["residentAutomationStateJson"]
            )
            resident_state["ministry"]["nextWakeAtMillis"] = 0
            facade._update_account_public_state(  # noqa: SLF001
                "202",
                {
                    "residentAutomationStateJson": json.dumps(
                        resident_state, ensure_ascii=False
                    )
                },
            )

            second = self._run_ministry_tick(facade)
            # 之后的轮次不再对已被拒绝的文官浪费正式写操作。
            self.assertEqual(second["state"], "completed", second)
            self.assertEqual(delegate_targets, [564, 563, 563])
        finally:
            facade_module.parse_ministry_officials = original

    def test_delegate_rejection_without_ineligibility_marker_is_not_remembered(
        self,
    ) -> None:
        class Bridge(_BridgeBase):
            def executeGameCommand(self, _account_ref, command_json, _context):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode == 0x6340:
                    return _game_response(opcode, 0xE340, TASK_LIST_086)
                if opcode == 0x6301:
                    return _game_response(opcode, 0xE301, OFFICIALS_088)
                if opcode == 0x6342:
                    return _game_response(
                        opcode,
                        0xE342,
                        _delegate_rejection_hex("俸禄池不足，稍后再试。"),
                    )
                raise AssertionError(f"unexpected opcode {opcode:#x}")

        bridge = Bridge()
        facade = self._make_facade(bridge)
        self._configure_courtesy_tick(facade)
        original = facade_module.parse_ministry_officials
        facade_module.parse_ministry_officials = lambda _payload: {
            "salaryPool": 1013,
            "officials": [
                {"officialId": 564, "name": "殷懏", "busyTaskId": 0, "idle": True},
            ],
            "candidateCount": 1,
        }
        try:
            result = self._run_ministry_tick(facade)
        finally:
            facade_module.parse_ministry_officials = original

        # 暂时性拒绝不记入名单（文官稍后可能仍可委派），按错误原样上报。
        self.assertEqual(result["errorCode"], "MINISTRY_DELEGATE_REJECTED")
        self.assertEqual(
            self._pending(facade, "ministryDelegateIneligibleJson"), {}
        )

    def test_all_idle_officials_ineligible_sends_no_delegate(self) -> None:
        class Bridge(_BridgeBase):
            def executeGameCommand(self, _account_ref, command_json, _context):
                command = json.loads(command_json)
                self.commands.append(command)
                opcode = int(command["opcode"])
                if opcode == 0x6340:
                    return _game_response(opcode, 0xE340, TASK_LIST_086)
                if opcode == 0x6301:
                    return _game_response(opcode, 0xE301, OFFICIALS_088)
                raise AssertionError("所有空闲文官均已被拒绝时禁止委派")

        bridge = Bridge()
        facade = self._make_facade(bridge)
        self._configure_courtesy_tick(facade)
        facade._update_account_public_state(  # noqa: SLF001
            "202",
            {
                "ministryDelegateIneligibleJson": json.dumps({
                    "officialIds": [564],
                })
            },
        )
        original = facade_module.parse_ministry_officials
        facade_module.parse_ministry_officials = lambda _payload: {
            "salaryPool": 1013,
            "officials": [
                {"officialId": 564, "name": "殷懏", "busyTaskId": 0, "idle": True},
            ],
            "candidateCount": 1,
        }
        try:
            result = self._run_ministry_tick(facade)
        finally:
            facade_module.parse_ministry_officials = original

        self.assertEqual(result["state"], "waiting", result)
        self.assertIn("均被服务器拒绝委派", result["message"])
        self.assertEqual(bridge.opcodes, [0x6340, 0x6301])


if __name__ == "__main__":
    unittest.main()
