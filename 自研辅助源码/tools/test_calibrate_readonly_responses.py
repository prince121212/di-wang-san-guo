#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("calibrate_readonly_responses.py")
spec = importlib.util.spec_from_file_location("calibrate_readonly_responses", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["calibrate_readonly_responses"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class CalibrateReadOnlyResponsesTest(unittest.TestCase):
    def test_parse_json_and_kv_captures(self) -> None:
        target = "000000000065030005000b0016E9BB84E5B7BE"
        mine = "0000000001010105000B00160100"
        text = "\n".join([
            '[readonly-response-json] {"opcode":"041540","responseHex":"%s"}' % target,
            "[readonly-response] opcode=041542 responseHex=%s" % mine,
        ])

        report = mod.calibrate(text)

        self.assertEqual(2, report["summary"]["captureCount"])
        self.assertEqual(1, report["summary"]["targetParsedCount"])
        self.assertEqual(1, report["summary"]["mineParsedCount"])
        self.assertEqual(target.upper(), report["channelExtraCandidate"]["mapTargetsHex"])
        self.assertEqual(mine.upper(), report["channelExtraCandidate"]["mineTargetsHex"])
        self.assertEqual("黄巾", report["captures"][0]["parsed"][0]["type"])
        self.assertEqual(101, report["captures"][0]["parsed"][0]["id"])
        self.assertEqual("金矿", report["captures"][1]["parsed"][0]["kind"])

    def test_bare_hex_uses_default_opcode_and_markdown(self) -> None:
        target = "000000000065030005000b0016E9BB84E5B7BE"
        report = mod.calibrate(target, default_opcode="041540")
        markdown = mod.to_markdown(report)

        self.assertEqual(1, report["summary"]["captureCount"])
        self.assertIn("targetSearchResponseHex", report["channelExtraCandidate"])
        self.assertIn("041540 / 041542", markdown)
        self.assertIn("黄巾", markdown)

    def test_cli_writes_json_and_markdown(self) -> None:
        target = "000000000065030005000b0016E9BB84E5B7BE"
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "readonly.log"
            out = Path(td) / "out.json"
            md = Path(td) / "out.md"
            src.write_text('[readonly-response-json] {"opcode":"041540","responseHex":"%s"}\n' % target, encoding="utf-8")
            mod.main.__globals__["__name__"] if False else None
            import subprocess, sys
            subprocess.check_call([sys.executable, str(SCRIPT), str(src), "--out", str(out), "--markdown-out", str(md)])
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(1, data["summary"]["targetParsedCount"])
            self.assertIn("ChannelExtra Candidate", md.read_text(encoding="utf-8"))

    def test_parse_concatenated_041540_records_without_separators(self) -> None:
        target = (
            "000000000301030005000b0016E9BB84E5B7BE"
            "0000000003020400060021002cE5B1B1E8B4BC"
        )

        report = mod.calibrate(target, default_opcode="041540")

        parsed = report["captures"][0]["parsed"]
        self.assertEqual(2, report["summary"]["targetParsedCount"])
        self.assertEqual(0x301, parsed[0]["id"])
        self.assertEqual("黄巾", parsed[0]["type"])
        self.assertEqual((11, 22), (parsed[0]["x"], parsed[0]["y"]))
        self.assertEqual(0x302, parsed[1]["id"])
        self.assertEqual("山贼", parsed[1]["type"])
        self.assertEqual((33, 44), (parsed[1]["x"], parsed[1]["y"]))

    def test_parse_main_marshal_markers(self) -> None:
        target = (
            "00000000040100000000500051E4B8BBE5B885|"
            "00000000040200000000520053E4B8BBE5B8A5"
        )

        report = mod.calibrate(target, default_opcode="041540")

        parsed = report["captures"][0]["parsed"]
        self.assertEqual(2, report["summary"]["targetParsedCount"])
        self.assertEqual("主帅", parsed[0]["type"])
        self.assertEqual(13, parsed[0]["rank"])
        self.assertEqual((80, 81), (parsed[0]["x"], parsed[0]["y"]))
        self.assertEqual("主帅", parsed[1]["type"])
        self.assertEqual(13, parsed[1]["rank"])
        self.assertEqual((82, 83), (parsed[1]["x"], parsed[1]["y"]))


if __name__ == "__main__":
    unittest.main()
