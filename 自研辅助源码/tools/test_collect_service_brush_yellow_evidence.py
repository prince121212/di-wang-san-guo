#!/usr/bin/env python3
from __future__ import annotations

import html
import importlib.util
import json
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("collect_service_brush_yellow_evidence.py")
spec = importlib.util.spec_from_file_location("collect_service_brush_yellow_evidence", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["collect_service_brush_yellow_evidence"] = mod
spec.loader.exec_module(mod)  # type: ignore[union-attr]


class CollectServiceBrushYellowEvidenceTest(unittest.TestCase):
    def test_parse_task_logs_xml(self):
        logs = [{"time": 1, "tag": "local-scheduler", "message": "local scheduling started"}]
        xml = '<map><string name="task_logs">' + html.escape(json.dumps(logs), quote=False) + "</string></map>"
        self.assertEqual(logs, mod.parse_task_logs_xml(xml))

    def test_collect_markers_from_mocked_logs(self):
        logs = [
            {"tag": "x", "message": "local scheduling started"},
            {"tag": "local-scheduler", "message": "real-session-from-account-repo tasks=1"},
            {"tag": "state-machine", "message": "brush-yellow selected formation=7066185"},
            {"tag": "real-action", "message": "真实刷黄二进制 sender 准备发送"},
            {"tag": "state-machine", "message": "brush-yellow dispatch-success formation=7066185 target=16304 consumed=1"},
            {"tag": "local-task-terminal", "message": "tick=1 terminal_decisions=1"},
        ]
        xml = '<map><string name="task_logs">' + html.escape(json.dumps(logs, ensure_ascii=False), quote=False) + "</string></map>"
        old = mod.adb_run_as_cat
        try:
            mod.adb_run_as_cat = lambda path, package=mod.PACKAGE: xml
            report = mod.collect()
        finally:
            mod.adb_run_as_cat = old
        self.assertTrue(report["serviceBrushYellowEvidenceReady"])
        self.assertTrue(report["markers"]["selectedFormation"])

    def test_latest_run_failure_is_not_ready_even_if_old_run_had_success(self):
        logs = [
            {"tag": "local-scheduler", "message": "service created"},
            {"tag": "x", "message": "local scheduling started"},
            {"tag": "local-scheduler", "message": "real-session-from-account-repo tasks=1"},
            {"tag": "state-machine", "message": "brush-yellow selected formation=7066185"},
            {"tag": "real-action", "message": "真实刷黄二进制 sender 准备发送"},
            {"tag": "state-machine", "message": "brush-yellow dispatch-success formation=7066185 target=16304 consumed=1"},
            {"tag": "local-task-terminal", "message": "tick=1 terminal_decisions=1"},
            {"tag": "local-scheduler", "message": "service created"},
            {"tag": "x", "message": "local scheduling started"},
            {"tag": "local-scheduler", "message": "real-session-from-account-repo tasks=1"},
            {"tag": "state-machine", "message": "brush-yellow selected formation=7066187"},
            {"tag": "real-action", "message": "真实刷黄二进制 sender 准备发送"},
            {"tag": "state-machine", "message": "brush-yellow dispatch-failed formation=7066187 target=16354"},
            {"tag": "local-task-terminal", "message": "tick=1 terminal_decisions=1"},
        ]
        xml = '<map><string name="task_logs">' + html.escape(json.dumps(logs, ensure_ascii=False), quote=False) + "</string></map>"
        old = mod.adb_run_as_cat
        try:
            mod.adb_run_as_cat = lambda path, package=mod.PACKAGE: xml
            report = mod.collect()
        finally:
            mod.adb_run_as_cat = old
        self.assertFalse(report["serviceBrushYellowEvidenceReady"])
        self.assertTrue(report["markers"]["dispatchFailed"])


if __name__ == "__main__":
    unittest.main()
