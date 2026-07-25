#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("check_brush_yellow_prereq.py")
spec = importlib.util.spec_from_file_location("check_brush_yellow_prereq", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["check_brush_yellow_prereq"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


def make_hex_general(gid: int, name: str, status: int = 0, tili: int = 49) -> str:
    b = gid.to_bytes(8, "big") + len(name.encode()).to_bytes(2, "big") + name.encode() + bytes([status, tili])
    return b.hex()


class BrushYellowPrereqTest(unittest.TestCase):
    def test_reports_ready_when_live_formations_gates_and_generals_exist(self):
        extra = {
            "roleName": "君主",
            "state8004PayloadHex": make_hex_general(7_066_187, "何颜鸥"),
            "formationsJson": json.dumps([{"id": 3, "generalIds": [7066187], "status": "IDLE"}]),
            "realActionNetworkAllowed": "true",
            "realActionSendReady": "true",
            "realActionScope": "brush-yellow",
        }
        report = mod.build_report({"id": 1, "serverName": "区"}, {"sourceMode": 1}, extra, {"sessionFresh": True, "reason": "ok"})
        self.assertTrue(report["readyForRealBrushYellow"])
        self.assertEqual([], report["blockers"])
        self.assertEqual(1, report["generalCandidateCount"])
        self.assertEqual("formationsJson", report["formationSource"])
        self.assertEqual("READY_FOR_REAL_BRUSH_YELLOW", report["readinessStage"])
        self.assertFalse(report["configReadyExceptSession"])

    def test_reports_ready_with_explicit_recovered_general_fallback_formation(self):
        extra = {
            "roleName": "君主",
            "state8004PayloadHex": make_hex_general(7_066_187, "何颜鸥", status=0, tili=49),
            "allowRecoveredGeneralFallbackFormation": "true",
            "realActionNetworkAllowed": "true",
            "realActionSendReady": "true",
            "realActionScope": "brush-yellow",
        }
        report = mod.build_report({"id": 1, "serverName": "区"}, {"sourceMode": 1}, extra, {"sessionFresh": True, "reason": "ok"})
        self.assertTrue(report["readyForRealBrushYellow"])
        self.assertEqual([], report["blockers"])
        self.assertEqual(1, report["formationCount"])
        self.assertEqual(1, report["fallbackFormationCount"])
        self.assertEqual("recovered-state8004-general-fallback", report["formationSource"])
        self.assertEqual([7_066_187], report["formations"][0]["generalIds"])

    def test_fallback_allows_zero_tili_for_binary_name_candidate(self):
        extra = {
            "state8004PayloadHex": make_hex_general(7_066_187, "何颜鸥", status=0, tili=0),
            "allowRecoveredGeneralFallbackFormation": "true",
            "realActionNetworkAllowed": "true",
            "realActionSendReady": "true",
            "realActionScope": "brush-yellow",
        }
        report = mod.build_report({"id": 1}, {"sourceMode": 1}, extra, {"sessionFresh": True, "reason": "ok"})
        self.assertTrue(report["readyForRealBrushYellow"])
        self.assertEqual(1, report["fallbackFormationCount"])

    def test_does_not_use_recovered_general_fallback_without_explicit_flag(self):
        extra = {
            "state8004PayloadHex": make_hex_general(7_066_187, "何颜鸥", status=0, tili=49),
            "realActionNetworkAllowed": "true",
            "realActionSendReady": "true",
            "realActionScope": "brush-yellow",
        }
        report = mod.build_report({"id": 1, "serverName": "区"}, {"sourceMode": 1}, extra, {"sessionFresh": True, "reason": "ok"})
        self.assertFalse(report["readyForRealBrushYellow"])
        self.assertIn("no_formations_json_or_selected_formation", report["blockers"])
        self.assertEqual(0, report["formationCount"])
        self.assertEqual(0, report["fallbackFormationCount"])

    def test_blocks_when_session_is_expired_and_gate_missing(self):
        report = mod.build_report({"id": 1}, {"sourceMode": 1}, {}, {"sessionFresh": False, "reason": "expired"})
        self.assertFalse(report["readyForRealBrushYellow"])
        self.assertIn("session_not_fresh_live_1016", report["blockers"])
        self.assertIn("realActionScope_brush_yellow_not_confirmed", report["blockers"])
        self.assertEqual("WAITING_FOR_ACTION_GATE", report["readinessStage"])
        self.assertIn("刷新真实登录 session", report["recommendation"])

    def test_reports_session_only_wait_when_everything_else_is_ready(self):
        extra = {
            "state8004PayloadHex": make_hex_general(7_066_187, "何颜鸥"),
            "formationsJson": json.dumps([{"id": 3, "generalIds": [7066187], "status": "IDLE"}]),
            "realActionNetworkAllowed": "true",
            "realActionSendReady": "true",
            "realActionScope": "brush-yellow",
        }
        report = mod.build_report({"id": 1}, {"sourceMode": 1}, extra, {"sessionFresh": False, "reason": "expired"})
        self.assertFalse(report["readyForRealBrushYellow"])
        self.assertEqual(["session_not_fresh_live_1016"], report["blockers"])
        self.assertEqual([], report["nonSessionBlockers"])
        self.assertTrue(report["configReadyExceptSession"])
        self.assertEqual("WAITING_FOR_FRESH_SESSION_ONLY", report["readinessStage"])
        self.assertIn("仅需刷新真实登录 session", report["recommendation"])

    def test_markdown_contains_candidate_count(self):
        report = mod.build_report({"id": 1}, {"sourceMode": 1}, {}, None)
        md = mod.to_markdown(report)
        self.assertIn("generalCandidateCount", md)
        self.assertIn("readyForRealBrushYellow", md)


if __name__ == "__main__":
    unittest.main()
