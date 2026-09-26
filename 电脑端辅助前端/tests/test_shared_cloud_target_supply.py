"""Target supply must progress despite legacy upload limits and idle peers."""

from __future__ import annotations

import copy
import dataclasses
import json
import tempfile
import types
import unittest
from pathlib import Path

import test_shared_cloud_map_replica as fixtures
from dwpm_core.features.cloud_map_replica import CloudMapReplicaStore
from dwpm_core.features.targets import brush_scan_coordinates


class LegacyD1Exchange(fixtures.FakeExchange):
    """The deployed gone query binds 4 fixed values plus one per target."""

    def __call__(self, path, body):
        if path == "/v1/maps/observations" and len(body.get("gone") or []) + 4 > 100:
            self.calls.append((path, copy.deepcopy(body)))
            raise OSError("D1 bound parameter limit exceeded")
        return super().__call__(path, body)


class CloudTargetUploadSupplyTests(unittest.TestCase):
    def store(self, exchange, clock, directory=None, logger=None):
        return CloudMapReplicaStore(
            server_key="server-352",
            map_kind="bandit",
            replica_id="account-a",
            data_directory=directory,
            exchange=exchange,
            clock=clock.now_millis,
            logger=logger,
        )

    def test_phone_sized_backlog_drains_without_another_scan_on_old_worker(self):
        clock = fixtures.MutableClock()
        exchange = LegacyD1Exchange()
        store = self.store(exchange, clock)
        self.assertTrue(store.ensure_fresh())
        old = [fixtures.observation(f"old-{i}") for i in range(404)]
        store.apply_scan_observation(1, 1, old)
        while store.pending_upload_count:
            self.assertTrue(store.flush_uploads())
        new = [fixtures.observation(f"new-{i}") for i in range(374)]
        store.apply_scan_observation(1, 1, new)
        self.assertEqual(store.pending_upload_count, 778)
        exchange.observation_bodies.clear()

        self.assertTrue(
            store.flush_uploads(),
            "a disappearance batch must not poison publication of new targets",
        )
        self.assertEqual(len(exchange.observation_bodies), 1, "one bounded request")
        self.assertLessEqual(len(exchange.observation_bodies[0]["gone"]), 96)
        # A matching but unpublished local candidate suppresses further scans.
        # Merely reading the replica must therefore drain the durable outbox.
        for _ in range(4):
            before = len(exchange.observation_bodies)
            self.assertTrue(store.ensure_fresh())
            self.assertLessEqual(len(exchange.observation_bodies) - before, 1)
        self.assertEqual(store.pending_upload_count, 0)
        uploaded = [
            row["targetId"] for b in exchange.observation_bodies
            for row in b.get("upserts", [])
        ]
        gone = [target_id for b in exchange.observation_bodies for target_id in b.get("gone", [])]
        self.assertEqual(uploaded, [row["targetId"] for row in new])
        self.assertEqual(gone, [row["targetId"] for row in old])

    def test_failed_queue_survives_restart_and_retries_without_new_observations(self):
        clock = fixtures.MutableClock()
        exchange = fixtures.FakeExchange()
        with tempfile.TemporaryDirectory() as directory:
            store = self.store(exchange, clock, Path(directory))
            self.assertTrue(store.ensure_fresh())
            store.apply_scan_observation(1, 1, [fixtures.observation("new-target")])
            exchange.fail_paths.add("/v1/maps/observations")
            self.assertFalse(store.flush_uploads())
            exchange.fail_paths.clear()
            restored = self.store(exchange, clock, Path(directory))
            self.assertEqual(restored.pending_upload_count, 1)
            self.assertTrue(restored.ensure_fresh())
            self.assertEqual(restored.pending_upload_count, 0)
            self.assertEqual(exchange.observation_bodies[-1]["upserts"][0]["targetId"], "new-target")

    def test_fresh_sighting_cancels_unsent_gone(self):
        clock = fixtures.MutableClock()
        exchange = fixtures.FakeExchange()
        store = self.store(exchange, clock)
        self.assertTrue(store.ensure_fresh())
        target = fixtures.observation("reappeared")
        store.apply_scan_observation(1, 1, [target])
        self.assertTrue(store.flush_uploads())
        store.apply_scan_observation(1, 1, [])
        store.apply_scan_observation(1, 1, [target])
        self.assertTrue(store.flush_uploads())
        latest = exchange.observation_bodies[-1]
        self.assertEqual(latest["upserts"], [target])
        self.assertNotIn("gone", latest, "an old disappearance must not delete a fresh sighting")

    def test_refresh_upload_failure_is_bounded_and_does_not_break_local_reads(self):
        clock = fixtures.MutableClock()
        exchange = fixtures.FakeExchange()
        store = self.store(exchange, clock)
        self.assertTrue(store.ensure_fresh())
        store.apply_scan_observation(1, 1, [fixtures.observation("still-local")])
        exchange.fail_paths.add("/v1/maps/observations")
        self.assertTrue(store.ensure_fresh())
        first_attempts = sum(path == "/v1/maps/observations" for path, _ in exchange.calls)
        self.assertEqual(first_attempts, 1)
        for _ in range(20):
            self.assertTrue(store.ensure_fresh())
        self.assertEqual(
            sum(path == "/v1/maps/observations" for path, _ in exchange.calls),
            first_attempts,
            "failed outbox retries must not flood the cloud in a hot scheduler loop",
        )
        self.assertEqual(store.pending_upload_count, 1)
        self.assertEqual(len(store.candidate_targets()), 1)
        clock.value += 60_000
        exchange.fail_paths.clear()
        self.assertTrue(store.ensure_fresh())
        self.assertEqual(store.pending_upload_count, 0)


class CloudTargetScanSupplyTests(unittest.TestCase):
    def fixture(self, cloud):
        helper = fixtures.CloudMapReplicaFacadeTests()
        facade, directory, config, state = helper._facade(cloud)
        config["common"]["brush"].update({
            "startX": 91, "startY": 26, "scanLimit": 80,
        })
        return helper, facade, directory, config, state

    def test_repair_log_never_calls_a_failed_or_still_queued_target_uploaded(self):
        class UnknownTargetCloud(fixtures.FakeV2CloudPort):
            fail_upload = False

            def exchange(self, request):
                if request["path"] == "/v1/maps/targets/reserve":
                    self.calls.append(copy.deepcopy(request))
                    return {"status": 200, "body": {
                        "ok": True, "reserved": False, "reason": "unknown-target",
                    }}
                if self.fail_upload and request["path"] == "/v1/maps/observations":
                    self.calls.append(copy.deepcopy(request))
                    raise OSError("fixture upload outage")
                return super().exchange(request)

        for failure, count in ((True, 1), (False, 201)):
            with self.subTest(failure=failure, count=count):
                cloud = UnknownTargetCloud()
                _, facade, directory, _config, _state = self.fixture(cloud)
                logs = []
                facade._ports = dataclasses.replace(
                    facade._ports, logs=types.SimpleNamespace(write=logs.append),
                )
                try:
                    replica = facade._cloud_map_replica("303", "bandit")
                    self.assertTrue(replica.ensure_fresh())
                    ids = [f"{i + 1:016x}" for i in range(count)]
                    replica.apply_scan_observation(
                        1, 1, [fixtures.observation(target_id) for target_id in ids],
                    )
                    cloud.fail_upload = failure
                    self.assertIsNone(facade._cloud_reserve_map_target(
                        "303", "bandit", {"idHex": ids[-1]},
                    ))
                    self.assertTrue(replica.upload_pending(ids[-1]))
                    self.assertIn("尚未上报成功", logs[-1]["message"])
                    self.assertNotIn("成功补报", logs[-1]["message"])
                    self.assertNotIn(
                        "/v1/maps/targets/status",
                        [call["path"] for call in cloud.calls],
                    )
                finally:
                    facade.close()
                    directory.cleanup()

    def test_online_but_nonscanning_peer_cannot_hide_half_the_search_area(self):
        for count, index in ((2, 0), (2, 1), (3, 2)):
            with self.subTest(count=count, index=index):
                cloud = fixtures.FakeV2CloudPort(count, index)
                helper, facade, directory, config, state = self.fixture(cloud)
                requests = helper._record_map_requests(facade)
                coordinates = brush_scan_coordinates(91, 26, 160)
                primary = coordinates[index::count]
                expected = primary + [c for c in coordinates if c not in set(primary)]
                try:
                    for tick in range(32):
                        before = len(requests)
                        result = facade._run_configured_brush_tick(
                            fixtures.FakeExecution(), "303", config, state, {}
                        )
                        self.assertEqual(requests[before:], expected[tick * 5:(tick + 1) * 5])
                        self.assertEqual(result["scannedCount"], 5)
                        self.assertEqual(result["scanLimit"], 160)
                        self.assertEqual(result["scanWrapped"], tick == 31)
                        public = json.loads(facade.account_record_json("303"))[
                            "account"
                        ]["session"]["publicState"]
                        state = json.loads(public["residentAutomationStateJson"])
                    self.assertEqual(requests, expected)
                    self.assertEqual(len(set(requests)), 160)
                    self.assertNotIn(
                        "/v1/maps/targets/reserve",
                        [call["path"] for call in cloud.calls],
                    )
                finally:
                    facade.close()
                    directory.cleanup()

    def test_peer_area_match_is_still_cloud_reserved_before_dispatch(self):
        cloud = fixtures.FakeV2CloudPort(actor_index=1)
        helper, facade, directory, config, state = self.fixture(cloud)
        config["common"]["brush"]["rules"][0]["compositionFilter"] = {
            "maxFoot": 5, "maxBow": 5, "maxCavalry": 5, "maxChariot": 5,
            "requireFoot": False,
        }
        requests = helper._record_map_requests(facade, target_at=82)
        dispatched = []

        def accept(_self, _execution, body, _context):
            self.assertEqual(cloud.calls[-1]["path"], "/v1/maps/targets/status")
            self.assertEqual(cloud.calls[-1]["body"]["status"], "dispatching")
            self.assertEqual(
                cloud.calls[-1]["body"]["reservationToken"], "reservation-1",
            )
            dispatched.append(copy.deepcopy(body))
            return {"result": {"success": True, "successBattleId": 9301}}

        facade._run_brush_execute_game_workflow = types.MethodType(accept, facade)
        try:
            for _ in range(17):
                result = facade._run_configured_brush_tick(
                    fixtures.FakeExecution(), "303", config, state, {}
                )
            coordinates = brush_scan_coordinates(91, 26, 160)
            self.assertEqual(requests, coordinates[1::2] + coordinates[::2][:2])
            self.assertEqual(result["state"], "dispatched")
            self.assertEqual(result["nextScanOffset"], 82)
            self.assertEqual(len(dispatched), 1)
            self.assertIn("/v1/maps/targets/reserve", [call["path"] for call in cloud.calls])
        finally:
            facade.close()
            directory.cleanup()

    def test_membership_change_resets_the_priority_order_not_just_its_length(self):
        cloud = fixtures.FakeV2CloudPort(actor_index=0)
        helper, facade, directory, config, state = self.fixture(cloud)
        requests = helper._record_map_requests(facade)
        try:
            first = facade._run_configured_brush_tick(
                fixtures.FakeExecution(), "303", config, state, {}
            )
            self.assertEqual(first["nextScanOffset"], 5)
            old_order = facade._cloud_shard_scan_space
            facade._cloud_shard_scan_space = lambda _ref, coords: coords[1::2]
            requests.clear()
            second = facade._run_configured_brush_tick(
                fixtures.FakeExecution(), "303", config, state, {}
            )
            self.assertEqual(second["scanOffset"], 0)
            self.assertEqual(requests, brush_scan_coordinates(91, 26, 80)[1::2][:5])
            facade._cloud_shard_scan_space = old_order
        finally:
            facade.close()
            directory.cleanup()

    def test_old_primary_cursor_resumes_into_catch_up_without_skipping(self):
        cloud = fixtures.FakeV2CloudPort(actor_index=1)
        helper, facade, directory, config, state = self.fixture(cloud)
        requests = helper._record_map_requests(facade)
        try:
            first = facade._run_configured_brush_tick(
                fixtures.FakeExecution(), "303", config, state, {}
            )
            cursor = state["brush"]["scanCursorsByRule"][first["scanRuleKey"]]
            cursor.pop("scanOrderKey")
            cursor["nextScanOffset"] = 79
            requests.clear()
            second = facade._run_configured_brush_tick(
                fixtures.FakeExecution(), "303", config, state, {}
            )
            coords = brush_scan_coordinates(91, 26, 160)
            self.assertEqual(requests, coords[1::2][-1:] + coords[::2][:4])
            self.assertEqual(second["scanOffset"], 79)
            self.assertEqual(second["nextScanOffset"], 84)
            self.assertEqual(second["catchUpScannedCount"], 4)
            self.assertFalse(second["scanWrapped"])
        finally:
            facade.close()
            directory.cleanup()
