from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = ROOT / "shared_core" / "python"
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
FIXTURE_PATH = ROOT / "shared_core" / "protocol_parity_fixtures.json"
CTF_OUT = ROOT / "ctf_out"
if str(CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CORE_SOURCE))

from dwpm_core.features.generals import (
    general_status_text_from_code,
    recover_generals_from_8004,
)
from dwpm_core.features.military import (
    MILITARY_ACTION_STATE_BY_TAG,
    MILITARY_INTEL_REQUEST_PAYLOAD,
    build_military_snapshot,
    military_action_state,
    military_action_tag,
    military_march_fields,
    parse_8600_military_actions,
    parse_8600_military_events,
    parse_8600_military_payload,
)
from dwpm_core.protocol.wire import parse_response


SPEC = importlib.util.spec_from_file_location(
    "dwpm_server_military_shared_parity",
    SERVER_PATH,
)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


def capture_payload(capture: str, flow_index: int) -> bytes:
    response_file = (
        CTF_OUT
        / capture
        / "live_analyzed"
        / f"{flow_index:03d}"
        / "resp.bin"
    )
    return next(
        packet["payload"]
        for packet in parse_response(response_file.read_bytes())
        if packet.get("opcode") == 0x8600
    )


class SharedMilitaryProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.fixtures = payload["fixtures"]

    def test_incoming_military_fixture_runs_in_shared_core(self) -> None:
        fixture = self.fixtures["militaryIncoming8600"]
        payload = bytes.fromhex(fixture["responseHex"])
        actions = parse_8600_military_actions(payload, [])

        self.assertEqual(
            MILITARY_INTEL_REQUEST_PAYLOAD.hex(),
            fixture["requestPayloadHex"],
        )
        self.assertEqual(
            SERVER.MILITARY_INTEL_REQUEST_PAYLOAD,
            MILITARY_INTEL_REQUEST_PAYLOAD,
        )
        self.assertEqual(SERVER.parse_8600_military_actions(payload, []), actions)
        self.assertEqual(len(actions), 1)
        for key, value in fixture["expected"].items():
            self.assertEqual(actions[0][key], value)

        snapshot = build_military_snapshot([payload, payload], [], 200)
        self.assertTrue(snapshot["responded"])
        self.assertEqual(snapshot["actionCount"], 1)
        self.assertEqual(snapshot["incomingCount"], 1)

    def test_garrison_event_fixture_runs_in_shared_core(self) -> None:
        fixture = self.fixtures["militaryGarrisonEvent8600"]
        payload = bytes.fromhex(fixture["responseHex"])
        events = parse_8600_military_events(payload)

        self.assertEqual(SERVER.parse_8600_military_events(payload), events)
        self.assertEqual(len(events), 1)
        for key, value in fixture["expected"].items():
            self.assertEqual(events[0][key], value)

    def test_general_8004_record_runs_in_shared_core(self) -> None:
        fixture = self.fixtures["generalRecord8004"]
        generals = recover_generals_from_8004(fixture["responseHex"])

        self.assertEqual(
            SERVER.recover_generals_from_8004(fixture["responseHex"]),
            generals,
        )
        self.assertEqual(len(generals), 1)
        for key, value in fixture["expected"].items():
            self.assertEqual(generals[0][key], value)
        for status in range(10):
            self.assertEqual(
                SERVER.general_status_text_from_code(status),
                general_status_text_from_code(status),
            )

    def test_real_outgoing_and_return_captures_run_in_shared_core(self) -> None:
        crystal_capture = "passive_pcap_hotspot_20260714_125113"
        fighting_payload = capture_payload(crystal_capture, 41)
        returning_payload = capture_payload(crystal_capture, 70)
        fighting = parse_8600_military_actions(fighting_payload, [])[0]
        returning = parse_8600_military_actions(returning_payload, [])[0]

        self.assertEqual(
            SERVER.parse_8600_military_payload(fighting_payload, []),
            parse_8600_military_payload(fighting_payload, []),
        )
        self.assertEqual(fighting["state"], "战斗")
        self.assertEqual(fighting["battleId"], 9649515)
        self.assertEqual(fighting["targetName"], "水晶矿(1级)")
        self.assertEqual((fighting["x"], fighting["y"]), (136, 20))
        self.assertEqual(returning["state"], "返回")
        self.assertEqual(returning["marchKindText"], "回程")
        self.assertGreater(returning["eventTimeMs"], 1_700_000_000_000)

    def test_real_tail_general_evidence_runs_in_shared_core(self) -> None:
        payload = capture_payload("passive_pcap_hotspot_20260726_173635", 50)
        parsed = parse_8600_military_payload(payload, [])

        self.assertEqual(SERVER.parse_8600_military_payload(payload, []), parsed)
        self.assertTrue(parsed["trailingEvidenceParsed"])
        self.assertEqual(parsed["unparsedTailByteCount"], 0)
        self.assertEqual(len(parsed["generalStatusRecords"]), 14)
        self.assertEqual(len(parsed["captiveGeneralRecords"]), 19)
        self.assertEqual(parsed["troopAssignmentCount"], 6)
        attack_bow = next(
            row
            for row in parsed["generalStatusRecords"]
            if row.get("name") == "攻弓1"
        )
        self.assertEqual(attack_bow["status"], 0)
        self.assertEqual(attack_bow["currentSoldierCount"], 1121)

    def test_military_state_helpers_run_in_shared_core(self) -> None:
        march = military_march_fields(0x0B, 32068, 1_785_059_585_543)
        cases = (
            (SERVER.military_action_tag("【消灭】7级山贼"), military_action_tag("【消灭】7级山贼")),
            (
                SERVER.military_march_fields(0x0B, 32068, 1_785_059_585_543),
                march,
            ),
            (
                SERVER.military_action_state("消灭", "【消灭】7级山贼", march),
                military_action_state("消灭", "【消灭】7级山贼", march),
            ),
        )
        for desktop, shared in cases:
            self.assertEqual(desktop, shared)
        self.assertEqual(MILITARY_ACTION_STATE_BY_TAG["消灭"], "战斗")
        self.assertEqual(
            military_action_state("消灭", "【消灭】7级山贼", march),
            "出征",
        )


if __name__ == "__main__":
    unittest.main()
