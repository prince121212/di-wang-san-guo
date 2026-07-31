from __future__ import annotations

import importlib.util
import json
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = ROOT / "shared_core" / "python"
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
if str(CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CORE_SOURCE))

from dwpm_core import CORE_ID, CORE_VERSION, CoreFacade, compute_core_hash
from dwpm_core.hashing import hash_records, source_manifest


SPEC = importlib.util.spec_from_file_location("dwpm_server_shared_core_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class SharedPythonCoreTests(unittest.TestCase):
    def test_core_health_reports_deterministic_source_identity(self) -> None:
        first = CoreFacade(ROOT / "shared_core").health()
        second = CoreFacade(ROOT / "shared_core").health()

        self.assertTrue(first["ok"])
        self.assertEqual(first["core"], CORE_ID)
        self.assertEqual(first["coreVersion"], CORE_VERSION)
        self.assertRegex(first["coreHash"], r"^[0-9a-f]{64}$")
        self.assertEqual(first["coreHash"], second["coreHash"])
        self.assertEqual(first["coreHash"], compute_core_hash(ROOT / "shared_core"))
        self.assertEqual(first["sharedRouteCount"], 55)
        self.assertEqual(first["localRouteCount"], 26)
        self.assertEqual(first["networkOperationRouteCount"], 29)

    def test_hash_is_path_independent_and_content_sensitive(self) -> None:
        first = hash_records((("core/a.py", b"one"), ("contract.json", b"two")))
        reordered = hash_records((("contract.json", b"two"), ("core/a.py", b"one")))
        changed = hash_records((("core/a.py", b"ONE"), ("contract.json", b"two")))

        self.assertEqual(first, reordered)
        self.assertNotEqual(first, changed)

    def test_manifest_contains_only_relative_deterministic_sources(self) -> None:
        manifest = source_manifest(ROOT / "shared_core")

        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertRegex(manifest["coreHash"], r"^[0-9a-f]{64}$")
        self.assertIn("python/dwpm_core/facade.py", manifest["files"])
        self.assertIn("assistant_behavior_contract.json", manifest["files"])
        self.assertTrue(all(not path.startswith("/") for path in manifest["files"]))

    def test_phase_two_dispatch_only_owns_health(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")

        health = facade.dispatch_local("GET", "/api/health?probe=1")
        unmigrated = facade.dispatch_local("GET", "/api/accounts")

        self.assertEqual(health.status, 200)
        self.assertTrue(health.body["ok"])
        self.assertEqual(unmigrated.status, 404)
        self.assertIn("not migrated", unmigrated.body["error"])

    def test_desktop_health_exposes_the_same_core_hash(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), SERVER.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/api/health",
                timeout=5,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        expected = SERVER.SHARED_PYTHON_CORE.health()
        self.assertEqual(payload["core"], CORE_ID)
        self.assertEqual(payload["coreVersion"], CORE_VERSION)
        self.assertEqual(payload["coreHash"], expected["coreHash"])
        self.assertEqual(payload["sharedRouteCount"], 55)
        self.assertEqual(payload["version"], SERVER.APP_VERSION)


if __name__ == "__main__":
    unittest.main()
