from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).with_name("assistant_api_bridge_operation.test.js")


class AssistantApiBridgeOperationTests(unittest.TestCase):
    def test_native_bridge_waits_on_local_operation_status(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("node is unavailable")
        completed = subprocess.run(
            [node, str(SCRIPT)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr or completed.stdout,
        )


if __name__ == "__main__":
    unittest.main()
