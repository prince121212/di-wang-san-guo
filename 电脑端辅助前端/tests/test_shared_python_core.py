from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_SOURCE = ROOT / "shared_core" / "python"
SERVER_PATH = ROOT / "电脑端辅助前端" / "server.py"
if str(CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CORE_SOURCE))

from dwpm_core import (
    CORE_ID,
    CORE_VERSION,
    CoreFacade,
    compute_core_hash,
    create_hosted_core,
)
from dwpm_core.hashing import hash_records, source_manifest
from dwpm_core.operations import OperationUncertainError
from dwpm_core.ports import PlatformPorts


SPEC = importlib.util.spec_from_file_location("dwpm_server_shared_core_test", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


class SharedPythonCoreTests(unittest.TestCase):
    def test_future_military_settings_write_plan_is_local_and_shared(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        plan = facade.settings_write_plan(
            "/api/military/future/save",
            {
                "feature": "escort",
                "settings": {
                    "enabled": True,
                    "rows": [
                        {
                            "enabled": True,
                            "generalIds": [7, "7", "", 8],
                        }
                    ],
                },
            },
        )

        self.assertFalse(plan["networkRequired"])
        self.assertTrue(plan["disabled"])
        self.assertEqual(
            plan["configs"]["military_future_escort"]["rows"][0]["generalIds"],
            ["7", "8"],
        )
        self.assertEqual(
            plan["response"]["readiness"]["status"],
            "capture_needed",
        )
        facade.close()

    def test_future_military_settings_plan_rejects_unknown_feature(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        result = facade.dispatch(
            "POST",
            "/api/military/future/save",
            {"feature": "unknown", "settings": {}},
        )

        self.assertEqual(result.status, 400)
        self.assertFalse(result.body["ok"])
        self.assertEqual(result.body["code"], "LOCAL_VALIDATION_FAILED")
        self.assertIn("未知军事功能", result.body["error"])
        facade.close()

    def test_ministry_settings_write_plan_separates_save_from_activation(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        unverified = facade.dispatch(
            "POST",
            "/api/liubu/save",
            {
                "settings": {
                    "cropEnabled": True,
                    "crop": "草药",
                    "stealEnabled": True,
                }
            },
        )
        verified = facade.dispatch(
            "POST",
            "/api/liubu/save",
            {
                "settings": {
                    "cropEnabled": True,
                    "crop": "金银花",
                    "stealEnabled": False,
                    "courtesyEnabled": False,
                    "salaryRefresh": False,
                }
            },
        )

        self.assertEqual(unverified.status, 200)
        unverified_plan = unverified.body["plan"]
        self.assertFalse(unverified_plan["networkRequired"])
        self.assertFalse(unverified_plan["activationAllowed"])
        self.assertTrue(unverified_plan["response"]["requested"])
        self.assertIn("配置已保存但不会发送", unverified_plan["response"]["reason"])

        verified_plan = verified.body["plan"]
        self.assertTrue(verified_plan["activationAllowed"])
        self.assertTrue(
            verified_plan["configs"]["six_ministries"]["supportedEnabled"]
        )
        missing = facade.dispatch(
            "POST",
            "/api/liubu/save",
            {"sessionId": "202"},
        )
        self.assertEqual(missing.status, 400)
        self.assertIn("缺少 settings", missing.body["error"])
        facade.close()

    def test_hosted_military_refresh_is_accepted_then_completed_by_shared_operation(self) -> None:
        class HostBridge:
            def __init__(self) -> None:
                self.calls = []

            def executeNetworkOperation(self, method, path, body_json, context_json):
                self.calls.append((method, path, json.loads(body_json)))
                return json.dumps(
                    {
                        "status": 200,
                        "body": {
                            "ok": True,
                            "militarySnapshot": {
                                "responded": True,
                                "actions": [],
                            },
                        },
                    },
                    ensure_ascii=False,
                )

            def executionOwnerActive(self):
                return True

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(
                str(Path(directory) / "operations-v2.json"),
                bridge,
            )
            try:
                facade.account_record_upsert(
                    {
                        "accountRef": "202",
                        "id": 202,
                        "username": "fixture",
                        "serverName": "fixture",
                        "enabled": True,
                        "loginState": "REAL_PROTOCOL_ONLINE",
                        "session": {
                            "accountId": 202,
                            "sourceMode": 1,
                            "publicState": {"lastValidatedAt": "1000"},
                        },
                    }
                )
                accepted = facade.dispatch(
                    "GET",
                    "/api/military/intel",
                    {"accountRef": "202", "sessionId": "202"},
                    {"requestId": "military-fixture-1", "platform": "android"},
                )

                self.assertEqual(accepted.status, 202)
                self.assertTrue(accepted.body["accepted"])
                operation = self.wait_for_operation(
                    facade,
                    accepted.body["operationId"],
                )
                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertTrue(operation["result"]["ok"])
                self.assertTrue(operation["result"]["militarySnapshot"]["responded"])
                self.assertEqual(len(bridge.calls), 1)
                self.assertEqual(bridge.calls[0][0:2], ("GET", "/api/military/intel"))
            finally:
                facade.close()

    def test_hosted_network_operation_rechecks_shared_session_gate_before_host_call(self) -> None:
        class HostBridge:
            calls = 0

            def executionOwnerActive(self):
                return True

            def executeNetworkOperation(self, *_args):
                self.calls += 1
                return json.dumps({"status": 200, "body": {"ok": True}})

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(
                str(Path(directory) / "operations-v2.json"),
                bridge,
            )
            try:
                facade.account_record_upsert(
                    {
                        "accountRef": "202",
                        "id": 202,
                        "username": "fixture",
                        "serverName": "fixture",
                        "enabled": False,
                        "loginState": "REAL_PROTOCOL_STOPPED",
                        "session": {
                            "accountId": 202,
                            "sourceMode": 1,
                            "publicState": {},
                        },
                    }
                )
                accepted = facade.dispatch(
                    "GET",
                    "/api/military/intel",
                    {"accountRef": "202"},
                    {"requestId": "military-stopped-1"},
                )
                operation = self.wait_for_operation(
                    facade,
                    accepted.body["operationId"],
                )

                self.assertEqual(operation["status"], "FAILED")
                self.assertIn("Session", operation["error"]["message"])
                self.assertEqual(bridge.calls, 0)
            finally:
                facade.close()

    def test_hosted_network_operation_requires_a_live_platform_owner(self) -> None:
        class HostBridge:
            calls = 0

            def executionOwnerActive(self):
                return False

            def executeNetworkOperation(self, *_args):
                self.calls += 1
                return json.dumps({"status": 200, "body": {"ok": True}})

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(
                str(Path(directory) / "operations-v2.json"),
                bridge,
            )
            try:
                facade.account_record_upsert(
                    {
                        "accountRef": "202",
                        "id": 202,
                        "username": "fixture",
                        "serverName": "fixture",
                        "enabled": True,
                        "loginState": "REAL_PROTOCOL_ONLINE",
                        "session": {
                            "accountId": 202,
                            "sourceMode": 1,
                            "publicState": {"lastValidatedAt": "1000"},
                        },
                    }
                )
                accepted = facade.dispatch(
                    "GET",
                    "/api/military/intel",
                    {"accountRef": "202"},
                    {"requestId": "military-owner-off-1"},
                )
                operation = self.wait_for_operation(
                    facade,
                    accepted.body["operationId"],
                )

                self.assertEqual(operation["status"], "FAILED")
                self.assertIn("执行所有者未激活", operation["error"]["message"])
                self.assertEqual(bridge.calls, 0)
            finally:
                facade.close()

    def test_hosted_network_operation_retries_busy_account_lane_without_blocking_host_call(self) -> None:
        class HostBridge:
            def __init__(self) -> None:
                self.calls = 0

            def executionOwnerActive(self):
                return True

            def executeNetworkOperation(self, *_args):
                self.calls += 1
                if self.calls < 3:
                    return json.dumps(
                        {
                            "status": 503,
                            "body": {
                                "ok": False,
                                "code": "LOCAL_ACCOUNT_BUSY",
                                "error": "account lane busy",
                            },
                        }
                    )
                return json.dumps(
                    {
                        "status": 200,
                        "body": {
                            "ok": True,
                            "militarySnapshot": {
                                "responded": True,
                                "actions": [],
                            },
                        },
                    }
                )

        with tempfile.TemporaryDirectory() as directory:
            bridge = HostBridge()
            facade = create_hosted_core(
                str(Path(directory) / "operations-v2.json"),
                bridge,
            )
            try:
                facade.account_record_upsert(
                    {
                        "accountRef": "202",
                        "id": 202,
                        "username": "fixture",
                        "serverName": "fixture",
                        "enabled": True,
                        "loginState": "REAL_PROTOCOL_ONLINE",
                        "session": {
                            "accountId": 202,
                            "sourceMode": 1,
                            "publicState": {"lastValidatedAt": "1000"},
                        },
                    }
                )
                accepted = facade.dispatch(
                    "GET",
                    "/api/military/intel",
                    {"accountRef": "202"},
                    {"requestId": "military-busy-1"},
                )
                operation = self.wait_for_operation(
                    facade,
                    accepted.body["operationId"],
                )

                self.assertEqual(operation["status"], "SUCCEEDED")
                self.assertEqual(bridge.calls, 3)
            finally:
                facade.close()

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
        self.assertEqual(first["operationModel"]["submission"], "immediate")

    def test_health_json_is_a_stable_android_bridge_contract(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")

        self.assertEqual(json.loads(facade.health_json()), facade.health())

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

    def test_dispatch_serves_migrated_routes_and_fails_closed_for_the_rest(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")

        health = facade.dispatch_local("GET", "/api/health?probe=1")
        accounts = facade.dispatch_local("GET", "/api/accounts")
        unmigrated = facade.dispatch_local("GET", "/api/accounts/settings")

        self.assertEqual(health.status, 200)
        self.assertTrue(health.body["ok"])
        self.assertEqual(accounts.status, 200)
        self.assertEqual(accounts.body, {"ok": True, "accounts": []})
        self.assertEqual(unmigrated.status, 501)
        self.assertEqual(unmigrated.body["code"], "ROUTE_NOT_MIGRATED")
        self.assertIn("not migrated", unmigrated.body["error"])

    def test_dispatch_json_is_the_same_host_neutral_entry_point(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")

        direct = facade.dispatch("GET", "/api/health")
        bridged = json.loads(
            facade.dispatch_json("GET", "/api/health", "{}", "{}")
        )

        self.assertEqual(bridged, direct.to_dict())
        self.assertEqual(direct.status, 200)
        self.assertEqual(
            direct.body["operationModel"]["networkLane"],
            "per-account",
        )
        self.assertEqual(
            direct.body["operationModel"]["localLane"],
            "direct",
        )
        facade.close()

    def test_long_network_operation_never_blocks_local_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            facade = CoreFacade(
                ROOT / "shared_core",
                str(Path(directory) / "operations.json"),
            )
            started = threading.Event()

            facade.register_local_route(
                "GET",
                "/api/accounts/settings",
                lambda body, context: {"ok": True, "saved": True},
            )

            def slow_query(body, context, execution):
                started.set()
                execution.wait(0.25)
                return {"ok": True, "refreshed": True}

            facade.register_network_route(
                "GET",
                "/api/state/refresh",
                slow_query,
            )
            submitted_at = time.perf_counter()
            accepted = facade.dispatch(
                "GET",
                "/api/state/refresh",
                {"accountRef": "account-a"},
                {"requestId": "refresh-a-1"},
            )
            submit_millis = (time.perf_counter() - submitted_at) * 1000
            self.assertEqual(accepted.status, 202)
            self.assertLess(submit_millis, 100)
            self.assertTrue(started.wait(1))

            latencies = []
            for _ in range(20):
                local_started = time.perf_counter()
                local = facade.dispatch("GET", "/api/accounts/settings")
                latencies.append((time.perf_counter() - local_started) * 1000)
                self.assertEqual(local.status, 200)
            self.assertLess(max(latencies), 100)

            operation_id = accepted.body["operationId"]
            final = self.wait_for_operation(facade, operation_id)
            self.assertEqual(final["status"], "SUCCEEDED")
            facade.close()

    def test_network_lanes_serialize_one_account_and_parallelize_accounts(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        release = threading.Event()
        a1_started = threading.Event()
        a2_started = threading.Event()
        b1_started = threading.Event()
        events = []
        events_lock = threading.Lock()

        def lane_probe(body, context, execution):
            label = body["label"]
            with events_lock:
                events.append(("start", label, time.monotonic()))
            {"a1": a1_started, "a2": a2_started, "b1": b1_started}[label].set()
            if label in {"a1", "b1"}:
                while not release.wait(0.02):
                    execution.raise_if_cancelled()
            with events_lock:
                events.append(("end", label, time.monotonic()))
            return {"ok": True, "label": label}

        facade.register_network_route(
            "GET",
            "/api/state/refresh",
            lane_probe,
        )

        def submit(account: str, label: str):
            return facade.dispatch(
                "GET",
                "/api/state/refresh",
                {"accountRef": account, "label": label},
                {"requestId": f"lane-{label}"},
            )

        a1 = submit("account-a", "a1")
        self.assertTrue(a1_started.wait(1))
        a2 = submit("account-a", "a2")
        b1 = submit("account-b", "b1")
        self.assertTrue(b1_started.wait(1))
        self.assertFalse(a2_started.wait(0.05))
        release.set()
        for response in (a1, a2, b1):
            final = self.wait_for_operation(facade, response.body["operationId"])
            self.assertEqual(final["status"], "SUCCEEDED")
        self.assertTrue(a2_started.is_set())

        times = {(phase, label): stamp for phase, label, stamp in events}
        self.assertGreaterEqual(times[("start", "a2")], times[("end", "a1")])
        self.assertLess(times[("start", "b1")], times[("end", "a1")])
        facade.close()

    def test_active_query_clicks_coalesce_but_completed_refresh_can_run_again(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        started = threading.Event()
        release = threading.Event()
        executions = []

        def query(body, context, execution):
            executions.append(body["scope"])
            started.set()
            while not release.wait(0.01):
                execution.raise_if_cancelled()
            return {"ok": True, "scope": body["scope"]}

        facade.register_network_route("GET", "/api/state/refresh", query)
        first = facade.dispatch(
            "GET",
            "/api/state/refresh",
            {"accountRef": "account-a", "scope": "military"},
            {"requestId": "coalesce-1"},
        )
        self.assertTrue(started.wait(1))
        duplicate = facade.dispatch(
            "GET",
            "/api/state/refresh",
            {"accountRef": "account-a", "scope": "military"},
            {"requestId": "coalesce-2"},
        )

        self.assertEqual(first.body["operationId"], duplicate.body["operationId"])
        self.assertTrue(duplicate.body["deduplicated"])
        self.assertEqual(executions, ["military"])
        release.set()
        self.assertEqual(
            self.wait_for_operation(facade, first.body["operationId"])["status"],
            "SUCCEEDED",
        )

        repeated = facade.dispatch(
            "GET",
            "/api/state/refresh",
            {"accountRef": "account-a", "scope": "military"},
            {"requestId": "coalesce-3"},
        )
        self.assertNotEqual(first.body["operationId"], repeated.body["operationId"])
        self.assertFalse(repeated.body["deduplicated"])
        self.assertEqual(
            self.wait_for_operation(facade, repeated.body["operationId"])["status"],
            "SUCCEEDED",
        )
        self.assertEqual(executions, ["military", "military"])
        facade.close()

    def test_sent_mutation_timeout_becomes_uncertain_and_is_not_replayed(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        executions = []

        def uncertain_mutation(body, context, execution):
            executions.append(body["targetId"])
            execution.mark_request_sent({"opcode": "0x1522"})
            raise RuntimeError("game reply timed out")

        facade.register_network_route(
            "POST",
            "/api/brush/execute",
            uncertain_mutation,
        )
        first = facade.dispatch(
            "POST",
            "/api/brush/execute",
            {"accountRef": "account-a", "targetId": 123},
            {"requestId": "brush-uncertain-1"},
        )
        final = self.wait_for_operation(facade, first.body["operationId"])
        self.assertEqual(final["status"], "UNCERTAIN")
        self.assertTrue(final["requestSent"])

        duplicate = facade.dispatch(
            "POST",
            "/api/brush/execute",
            {"accountRef": "account-a", "targetId": 123},
            {"requestId": "brush-uncertain-1"},
        )
        self.assertEqual(duplicate.body["operationId"], first.body["operationId"])
        self.assertTrue(duplicate.body["deduplicated"])
        self.assertEqual(executions, [123])
        facade.close()

    def test_queued_operation_can_cancel_but_sent_mutation_cannot(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        first_started = threading.Event()
        sent_started = threading.Event()
        release = threading.Event()

        def controlled(body, context, execution):
            if body["label"] == "first":
                first_started.set()
            if body.get("sent"):
                execution.mark_request_sent({"opcode": "0x1522"})
                sent_started.set()
            while not release.wait(0.02):
                execution.raise_if_cancelled()
            return {"ok": True}

        facade.register_network_route(
            "POST",
            "/api/brush/execute",
            controlled,
        )
        first = facade.dispatch(
            "POST",
            "/api/brush/execute",
            {"accountRef": "account-a", "label": "first", "sent": True},
            {"requestId": "cancel-first"},
        )
        self.assertTrue(first_started.wait(1))
        self.assertTrue(sent_started.wait(1))
        queued = facade.dispatch(
            "POST",
            "/api/brush/execute",
            {"accountRef": "account-a", "label": "queued", "sent": False},
            {"requestId": "cancel-queued"},
        )

        queued_cancelled = facade.cancel_operation(queued.body["operationId"])
        sent_cancel = facade.cancel_operation(first.body["operationId"])
        self.assertEqual(
            queued_cancelled["operation"]["status"],
            "CANCELLED",
        )
        self.assertEqual(sent_cancel["operation"]["status"], "RUNNING")
        self.assertEqual(
            sent_cancel["operation"]["cancellationDenied"],
            "request-already-sent",
        )
        release.set()
        self.assertEqual(
            self.wait_for_operation(facade, first.body["operationId"])["status"],
            "SUCCEEDED",
        )
        facade.close()

    def test_recovery_marks_sent_running_mutation_uncertain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "operations.json"
            ledger.write_text(
                json.dumps(
                    {
                        "schemaVersion": 2,
                        "operations": [
                            {
                                "operationId": "op_recovery_sent",
                                "kind": "route:POST:/api/brush/execute",
                                "operationType": "mutation",
                                "accountRef": "account-a",
                                "idempotencyKey": "recovery-sent-1",
                                "status": "RUNNING",
                                "submittedAtMillis": 100,
                                "startedAtMillis": 110,
                                "updatedAtMillis": 120,
                                "completedAtMillis": None,
                                "payload": {"body": {"targetId": 1}},
                                "progress": 50,
                                "progressDetails": None,
                                "requestSent": True,
                                "requestSentAtMillis": 115,
                                "requestMetadata": {"opcode": "0x1522"},
                                "cancelRequested": False,
                                "result": None,
                                "error": None,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            facade = CoreFacade(ROOT / "shared_core", str(ledger))
            recovered = facade.operation_status("op_recovery_sent")["operation"]

            self.assertEqual(recovered["status"], "UNCERTAIN")
            self.assertEqual(
                recovered["error"]["code"],
                "RECOVERED_AFTER_REQUEST_SENT",
            )
            facade.close()

    def test_operation_ledger_rejects_sensitive_fields(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        facade.register_network_route(
            "POST",
            "/api/accounts/add",
            lambda body, context, execution: {"ok": True},
        )

        response = facade.dispatch(
            "POST",
            "/api/accounts/add",
            {
                "accountRef": "new-account",
                "username": "user",
                "password": "must-not-persist",
            },
            {"requestId": "add-sensitive-1"},
        )

        self.assertEqual(response.status, 400)
        self.assertIn("sensitive field", response.body["error"])
        self.assertEqual(facade.operations_snapshot()["count"], 0)
        facade.close()

    def test_explicit_uncertain_error_preserves_structured_evidence(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")

        def uncertain_query(body, context, execution):
            raise OperationUncertainError(
                "response frame incomplete",
                {"opcode": "0x8600"},
            )

        facade.register_network_route(
            "GET",
            "/api/military/intel",
            uncertain_query,
        )
        accepted = facade.dispatch(
            "GET",
            "/api/military/intel",
            {"accountRef": "account-a"},
            {"requestId": "intel-uncertain-1"},
        )
        final = self.wait_for_operation(facade, accepted.body["operationId"])
        self.assertEqual(final["status"], "UNCERTAIN")
        self.assertEqual(final["error"]["details"]["opcode"], "0x8600")
        facade.close()

    def test_operation_events_use_the_independent_platform_event_port(self) -> None:
        class CaptureEvents:
            def __init__(self):
                self.rows = []

            def publish(self, event):
                self.rows.append(dict(event))

        events = CaptureEvents()
        facade = CoreFacade(
            ROOT / "shared_core",
            ports=PlatformPorts(events=events),
        )
        facade.register_network_route(
            "GET",
            "/api/state/refresh",
            lambda body, context, execution: {"ok": True},
        )
        accepted = facade.dispatch(
            "GET",
            "/api/state/refresh",
            {"accountRef": "account-a"},
            {"requestId": "events-1"},
        )
        self.wait_for_operation(facade, accepted.body["operationId"])
        event_types = {row["type"] for row in events.rows}
        self.assertIn("operation.accepted", event_types)
        self.assertIn("operation.started", event_types)
        self.assertIn("operation.completed", event_types)
        facade.close()

    def test_simulated_network_operation_is_immediate_and_idempotent(self) -> None:
        facade = CoreFacade(ROOT / "shared_core")
        started = time.perf_counter()

        submitted = facade.submit_simulated_network_operation(
            2_000,
            "shared-core-test-immediate",
            {"probe": "offline-only"},
        )
        elapsed_millis = (time.perf_counter() - started) * 1000
        duplicate = facade.submit_simulated_network_operation(
            2_000,
            "shared-core-test-immediate",
            {"probe": "offline-only"},
        )

        self.assertLess(elapsed_millis, 100)
        self.assertTrue(submitted["accepted"])
        self.assertFalse(submitted["deduplicated"])
        self.assertTrue(duplicate["deduplicated"])
        self.assertEqual(submitted["operationId"], duplicate["operationId"])
        with self.assertRaisesRegex(ValueError, "different input"):
            facade.submit_simulated_network_operation(
                2_000,
                "shared-core-test-immediate",
                {"probe": "different-input"},
            )
        self.assertTrue(facade.health()["ok"])
        self.assertEqual(
            facade.operation_status(submitted["operationId"])["operation"]["status"],
            "RUNNING",
        )
        cancelled = facade.cancel_operation(submitted["operationId"])
        self.assertEqual(cancelled["operation"]["status"], "CANCELLED")
        facade.close()

    def test_simulated_operation_result_survives_facade_recreation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "operations.json"
            first = CoreFacade(ROOT / "shared_core", str(ledger))
            submitted = first.submit_simulated_network_operation(
                40,
                "shared-core-test-recovery",
                {"value": 7},
            )
            first.close()
            time.sleep(0.08)

            recovered = CoreFacade(ROOT / "shared_core", str(ledger))
            status = recovered.operation_status(submitted["operationId"])

            self.assertTrue(status["ok"])
            self.assertEqual(status["operation"]["status"], "SUCCEEDED")
            self.assertEqual(status["operation"]["result"]["echo"], {"value": 7})
            self.assertEqual(recovered.operations_snapshot()["count"], 1)
            recovered.close()

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

    @staticmethod
    def wait_for_operation(
        facade: CoreFacade,
        operation_id: str,
        timeout: float = 2.0,
    ) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = facade.operation_status(operation_id)
            operation = status.get("operation") or {}
            if operation.get("status") in {
                "SUCCEEDED",
                "FAILED",
                "CANCELLED",
                "UNCERTAIN",
            }:
                return operation
            time.sleep(0.01)
        raise AssertionError(f"operation did not finish: {operation_id}")


if __name__ == "__main__":
    unittest.main()
