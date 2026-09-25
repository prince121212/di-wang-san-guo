"""Observations are not dispatch eligibility; a cloud outage is not a team."""

from __future__ import annotations

import copy
import dataclasses
import json
import tempfile
import types
import unittest
from pathlib import Path

import test_shared_cloud_map_replica as maps
import test_shared_brush_formation_lanes as lanes
from dwpm_core import CoreFacade
from dwpm_core.features.brush_lanes import brush_record_key, BRUSH_CONSUMED_FIELD
from dwpm_core.features.cloud_map_replica import CloudMapReplicaStore
from dwpm_core.operations import OperationKnownFailureError

ACTIVE, WAITING = lanes.ACTIVE, lanes.WAITING

class CandidateEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.clock = maps.MutableClock()
        self.exchange = maps.FakeExchange()
        self.row = maps.cloud_row("00000000000000aa", changed=100)
        self.exchange.sync_pages = [{"targets": [self.row]}]
        self.store = self.new_store()
        self.assertTrue(self.store.ensure_fresh())

    def new_store(self):
        return CloudMapReplicaStore(
            server_key="server", map_kind="bandit", replica_id="account",
            data_directory=Path(self.directory.name),
            clock=self.clock.now_millis, exchange=self.exchange,
        )

    def test_unknown_target_and_its_failed_outbox_survive_restart(self):
        target_id = self.row["targetId"]
        self.store.defer_candidate(target_id, "unknown-target")
        self.assertTrue(self.store.requeue_upload(target_id))
        self.exchange.fail_paths.add("/v1/maps/observations")
        self.assertFalse(self.store.flush_uploads())
        self.clock.value += 61_000
        restored = self.new_store()
        self.assertTrue(restored.ensure_fresh())
        self.assertEqual(restored.pending_upload_count, 1)
        self.assertTrue(restored.upload_pending(target_id))
        self.assertEqual(restored.candidate_targets(), [])
        self.exchange.fail_paths.clear()
        self.clock.value += 16_000
        self.assertTrue(restored.ensure_fresh())
        self.assertEqual(restored.pending_upload_count, 0)
        self.assertEqual(len(restored.candidate_targets()), 1)

    def test_a_different_upload_batch_is_not_acknowledgement_of_the_blocked_target(self):
        ids = [f"{i + 1000:016x}" for i in range(201)]
        self.store.apply_scan_observation(1, 1, [maps.observation(i) for i in ids])
        self.store.defer_candidate(ids[-1], "unknown-target")
        self.assertTrue(self.store.flush_uploads())
        self.clock.value += 61_000
        self.assertFalse(self.store.candidate_eligible(ids[-1]))
        self.assertTrue(self.store.upload_pending(ids[-1]))
        self.assertTrue(self.store.flush_uploads())
        self.assertTrue(self.store.candidate_eligible(ids[-1]))

    def test_sighting_or_stale_cloud_replay_cannot_unblock_an_unknown_cloud_row(self):
        target_id = self.row["targetId"]
        self.store.defer_candidate(target_id, "unknown-target")
        self.clock.value += 61_000
        self.store.apply_scan_observation(1, 1, [maps.observation(target_id)])
        self.store._apply_row(self.store._targets, self.row)
        self.assertFalse(self.store.candidate_eligible(target_id))
        self.store._apply_row(self.store._targets, {**self.row, "changedAtMillis": 101})
        self.assertTrue(self.store.candidate_eligible(target_id))
        self.assertTrue(self.store.upload_pending(target_id), "eligibility is not outbox deletion")

    def test_unavailable_candidate_waits_for_lease_and_sightings_do_not_reset_it(self):
        target_id = self.row["targetId"]
        until = self.clock.value + 120_000
        self.store.defer_candidate(target_id, "unavailable", retry_at_millis=until)
        self.clock.value += 61_000
        self.store.apply_scan_observation(1, 1, [maps.observation(target_id)])
        self.assertFalse(self.store.candidate_eligible(target_id))
        self.clock.value = until
        self.assertTrue(self.store.candidate_eligible(target_id))

    def test_consumed_target_needs_a_fresh_unowned_game_observation_not_cloud_replay(self):
        target_id = self.row["targetId"]
        for reason in ("dispatched", "missing"):
            with self.subTest(reason=reason):
                self.store.defer_candidate(target_id, reason)
                self.clock.value += 61_000
                self.store._apply_row(
                    self.store._targets, {**self.row, "changedAtMillis": 1000}
                )
                self.store.apply_scan_observation(
                    1, 1, [maps.observation(target_id)],
                    protected_target_ids={target_id},
                )
                self.assertFalse(self.new_store().candidate_eligible(target_id))
                self.clock.value += 1
                self.store.apply_scan_observation(1, 1, [maps.observation(target_id)])
                self.assertTrue(self.store.candidate_eligible(target_id))

    def test_sightings_never_clear_an_active_lease_or_rejection(self):
        for status in ("reserved", "dispatching", "uncertain", "rejected"):
            with self.subTest(status=status):
                row = {
                    **self.row, "status": status,
                    "leaseUntilMillis": self.clock.value + 120_000,
                    "retryAfterMillis": self.clock.value + 120_000,
                }
                self.store._apply_row(self.store._targets, row)
                self.store.apply_scan_observation(1, 1, [maps.observation(row["targetId"])])
                self.assertEqual(self.store.candidate_targets(), [])
                self.assertEqual(self.store._targets[row["targetId"]]["status"], status)

    def test_failed_changes_subscription_is_rate_limited_without_losing_local_reads(self):
        self.clock.value += 61_000
        self.exchange.fail_paths.add("/v1/maps/targets/changes")
        for _ in range(20):
            self.assertTrue(self.store.ensure_fresh())
        changes = lambda: [p for p, _ in self.exchange.calls if p.endswith("/changes")]
        self.assertEqual(len(changes()), 1)
        self.assertEqual(len(self.store.candidate_targets()), 1)
        self.clock.value += 15_000
        self.store.ensure_fresh()
        self.assertEqual(len(changes()), 2)


class UnknownTargetCloud(maps.FakeV2CloudPort):
    fail_upload = True

    def exchange(self, request):
        if request["path"] == "/v1/maps/targets/reserve":
            self.calls.append(copy.deepcopy(request))
            return {"status": 200, "body": {
                "ok": True, "reserved": False, "reason": "unknown-target",
            }}
        if self.fail_upload and request["path"] == "/v1/maps/observations":
            self.calls.append(copy.deepcopy(request))
            raise OSError("fixture upload unavailable")
        return super().exchange(request)


class BrushDispatchSupplyTests(unittest.TestCase):
    def setUp(self):
        self.h = lanes.BrushFormationLaneTests()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.facade = self.h.facade
        self.clock = self.h.clock
        self.logs = []
        self.facade._ports = dataclasses.replace(
            self.facade._ports, logs=types.SimpleNamespace(write=self.logs.append)
        )

    def state(self):
        return json.loads(self.h.public()["residentAutomationStateJson"])["brush"]

    def install_unknown_cloud(self):
        cloud = UnknownTargetCloud()
        cloud.sync_targets = [maps.cloud_row(
            "000000000000abcd", level=7, last_seen=self.clock.value,
            data={
                "kind": "山贼", "resource": "宝物", "dropCategories": ["宝物"],
                "composition": {"foot": 1, "bow": 0, "cavalry": 0, "chariot": 0,
                                "source": "8540-units"},
                "unitTypes": [1],
            },
        )]
        self.facade._ports = dataclasses.replace(self.facade._ports, cloud_shared_data=cloud)
        account = json.loads(self.facade.account_record_json("303"))["account"]
        self.facade.account_record_upsert({
            **account, "platformKey": "sglm", "serverId": "server-352",
        })
        self.h.put(serverKey="server-352", gameHttp="https://game.example/HttpClient?dm=fixture")
        # Three busy teams, one idle. Use the real filter and real batch scan
        # reader, so a stub that ignores composition/windowing cannot green it.
        records = [self.h.old_pending(i, nextPollAtMillis=self.clock.value + 600_000)
                   for i in (7, 8, 10)]
        self.h.put(**{
            ACTIVE: json.dumps(records[0]),
            WAITING: json.dumps({brush_record_key(r): r for r in records[1:]}),
        })
        self.facade._run_brush_search_game_workflow = types.MethodType(
            CoreFacade._run_brush_search_game_workflow, self.facade
        )
        requests = maps.CloudMapReplicaFacadeTests()._record_map_requests(self.facade)
        return cloud, requests

    def test_one_unpublished_candidate_cannot_starve_the_only_idle_team(self):
        cloud, requests = self.install_unknown_cloud()
        config_before = self.h.public()["residentAutomationConfigJson"]
        results = []
        for _ in range(10):
            result = self.h.tick()
            results.append(result)
            self.clock.value = max(self.clock.value + 2_000, result["nextWakeAtMillis"])
        reserves = [c for c in cloud.calls if c["path"] == "/v1/maps/targets/reserve"]
        self.assertEqual(len(reserves), 1, results)
        self.assertTrue(all(r.get("formationNumber") == 3 for r in results), results)
        self.assertGreaterEqual(len(requests), 9, "the idle team must actually continue scanning")
        self.assertEqual(len(self.h.sent), 0)
        self.assertEqual(len(self.h.pending()), 3)
        self.assertEqual(self.h.public()["residentAutomationConfigJson"], config_before)
        self.assertTrue(self.facade._cloud_map_replica("303", "bandit").upload_pending(
            "000000000000abcd"
        ))

    def test_even_an_immediately_acknowledged_refusal_yields_one_new_scan(self):
        cloud, requests = self.install_unknown_cloud()
        cloud.fail_upload = False
        first = self.h.tick()
        self.assertEqual(len(requests), 0, first)
        self.clock.value += 61_000
        second = self.h.tick()
        self.assertGreater(len(requests), 0, second)
        self.assertEqual(
            len([c for c in cloud.calls if c["path"] == "/v1/maps/targets/reserve"]), 1
        )

    def test_a_large_refused_pool_has_a_bounded_arbitration_budget(self):
        cloud, requests = self.install_unknown_cloud()
        cloud.fail_upload = False  # Normal refusal, not the independent outage policy.
        row = cloud.sync_targets[0]
        cloud.sync_targets = [{**row, "targetId": f"{i + 1000:016x}"} for i in range(30)]
        first = self.h.tick()
        self.assertEqual(first["state"], "no-targets")
        self.assertEqual(len(requests), 0)
        self.assertEqual(
            len([c for c in cloud.calls if c["path"] == "/v1/maps/targets/reserve"]), 5
        )
        self.clock.value = first["nextWakeAtMillis"]
        self.h.tick()
        self.assertGreater(len(requests), 0)

    def test_idle_team_dispatches_a_new_target_after_the_old_one_was_refused(self):
        cloud, _requests = self.install_unknown_cloud()
        cloud.fail_upload = False
        first = self.h.tick()
        self.assertEqual(first["state"], "no-targets")
        self.clock.value = max(first["nextWakeAtMillis"], self.clock.value + 16_000)
        fresh = CoreFacade._cloud_target_from_row(
            "bandit", {**cloud.sync_targets[0], "targetId": "000000000000abce"}
        )
        for flag in ("fromCache", "fromSharedMap", "fromCloudSharedMap"):
            fresh.pop(flag, None)

        def scan(_self, _execution, body, _context):
            coordinate = body["_scanCoordinatesOverride"][0]
            return {
                "targets": [fresh], "scannedCount": 1,
                "scanResults": [{"scanCoord": coordinate, "targets": [fresh]}],
                "scannedCoordinates": [coordinate],
            }

        self.facade._run_brush_search_game_workflow = types.MethodType(scan, self.facade)
        exchange = cloud.exchange

        def new_target_reservable(request):
            if (
                request["path"] == "/v1/maps/targets/reserve"
                and request["body"]["targetId"] == fresh["idHex"]
            ):
                self.assertTrue(any(
                    row["targetId"] == fresh["idHex"]
                    for call in cloud.calls if call["path"] == "/v1/maps/observations"
                    for row in call["body"].get("upserts", [])
                ), "the new target must be published before reservation")
                return maps.FakeV2CloudPort.exchange(cloud, request)
            return exchange(request)

        cloud.exchange = new_target_reservable
        cloud.fail_upload = False
        result = self.h.tick()
        self.assertEqual(result["state"], "dispatched", result)
        self.assertEqual(result["formationNumber"], 3)
        self.assertEqual(result["target"]["id"], fresh["id"])
        self.assertEqual(len(self.h.sent), 1)
        self.assertEqual(len(self.h.pending()), 4, "all previous battles must survive")
        paths = [c["path"] for c in cloud.calls]
        self.assertIn("/v1/maps/targets/reserve", paths)
        states = [c["body"]["status"] for c in cloud.calls if c["path"].endswith("/status")]
        self.assertEqual(states, ["dispatching", "dispatched"])

    def outage(self, *, checked_at=0):
        self.h.put(cloudRuntimeConfigJson=json.dumps({
            "schemaVersion": 1, "cloudBrushMapEnabled": True, "revision": 0,
        }))
        self.facade._cloud_presence_mode = lambda *_a, **_kw: {
            "mode": "CLOUD_UNAVAILABLE", "checkedAtMillis": checked_at,
            "previouslyShared": True,
        }

    def seed_legacy_dependency_wait(self):
        state = json.loads(self.h.public()["residentAutomationStateJson"])
        state["brush"].update({
            "lastState": "waiting-dependency", "nextWakeAtMillis": self.clock.value + 60_000,
            "dependencyWait": {
                "path": "/v1/presence/heartbeat", "failureAtMillis": self.clock.value,
                "retryAtMillis": self.clock.value + 60_000,
                "errorCode": "CLOUD_SHARED_DATA_UNAVAILABLE", "message": "legacy cloud wait",
            },
        })
        self.h.put(residentAutomationStateJson=json.dumps(state))

    def test_cloud_error_cannot_borrow_a_sibling_accepted_ledger(self):
        self.h.put(**{ACTIVE: json.dumps(self.h.old_pending(
            nextPollAtMillis=self.clock.value + 600_000
        ))})
        before = copy.deepcopy(self.h.pending())
        self.outage()
        result = self.h.tick()
        self.assertEqual(result["state"], "dispatched", result)
        self.assertEqual(result["mapMode"], "LOCAL_FALLBACK")
        self.assertEqual(result["nextWakeAtMillis"], self.clock.value + 1_000)
        self.assertNotIn("dependencyWait", self.state())
        self.assertEqual(len(self.h.pending()), 2)
        old = next(p for p in self.h.pending() if p["battleId"] == before[0]["battleId"])
        self.assertEqual({key: old[key] for key in before[0]}, before[0])
        self.assertNotEqual(result["battleId"], old["battleId"])

    def test_http_500_is_a_dependency_failure_not_an_unrelated_team_failure(self):
        cloud, requests = self.install_unknown_cloud()
        exchange = cloud.exchange

        def fail_reservation(request):
            if request["path"] == "/v1/maps/targets/reserve":
                return {"status": 500, "body": {
                    "ok": False, "code": "INTERNAL_ERROR", "error": "fixture server error",
                }}
            return exchange(request)

        cloud.exchange = fail_reservation
        before = copy.deepcopy(self.h.pending())
        result = self.h.tick()
        self.assertEqual(result["state"], "no-targets", result)
        self.assertEqual(result["mapMode"], "LOCAL_FALLBACK")
        route = json.loads(self.h.public()["brushCloudFallbackJson"])
        self.assertEqual(route["failureCode"], "INTERNAL_ERROR")
        self.assertEqual(route["failurePath"], "/v1/maps/targets/reserve")
        self.assertEqual(result["nextWakeAtMillis"], self.clock.value + 2_000)
        self.assertEqual(len(requests), 5, "a real bounded local scan replaces cloud waiting")
        self.assertEqual(self.h.pending(), before)
        self.assertEqual(self.h.sent, [])

    def test_accepted_status_remains_excluded_even_if_its_cloud_write_fails(self):
        cloud, _requests = self.install_unknown_cloud()
        replica = self.facade._cloud_map_replica("303", "bandit")
        self.assertTrue(replica.ensure_fresh())
        target = CoreFacade._cloud_target_from_row("bandit", cloud.sync_targets[0])
        self.facade._cloud_shared_exchange = lambda *_a, **_kw: (
            500, {"ok": False, "code": "INTERNAL_ERROR"}
        )
        self.assertFalse(self.facade._cloud_update_map_target_status(
            "303", "bandit", target, "fixture-token", "dispatched", strict=False
        ))
        self.clock.value += 61_000
        replica._apply_row(replica._targets, cloud.sync_targets[0])
        self.assertEqual(replica.candidate_targets(), [])

    def test_sibling_recovery_preserves_cloud_deadline_and_does_not_narrate_resume(self):
        self.h.put(**{ACTIVE: json.dumps(self.h.old_pending(
            nextPollAtMillis=self.clock.value + 5_000
        ))})
        self.seed_legacy_dependency_wait()
        waiting = self.state()
        self.clock.value += 6_000
        result = self.h.tick()
        self.assertEqual(result["state"], "completed", result)
        self.assertEqual(self.state()["dependencyWait"], waiting["dependencyWait"])
        self.assertEqual(self.state()["nextWakeAtMillis"], waiting["nextWakeAtMillis"])
        self.assertEqual(self.state()["lastState"], "waiting-dependency")
        self.assertEqual(self.state()["cursor"], waiting["cursor"])
        self.assertFalse(any("已恢复运行" in e.get("message", "") for e in self.logs))

    def test_cloud_probe_backoff_does_not_delay_idle_local_teams(self):
        self.outage()
        presence = self.facade._cloud_presence_mode
        calls = []

        def heartbeat(*args, **kwargs):
            calls.append(self.clock.value)
            return presence(*args, **kwargs)

        self.facade._cloud_presence_mode = heartbeat
        for _ in range(4):
            result = self.h.tick()
            self.assertEqual(result["state"], "dispatched", result)
            self.assertEqual(result["mapMode"], "LOCAL_FALLBACK")
            self.clock.value = result["nextWakeAtMillis"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.h.sent), 4)

    def test_only_the_failed_cloud_endpoint_can_clear_its_wait(self):
        self.seed_legacy_dependency_wait()
        waiting = self.state()
        self.facade._cloud_shared_exchange = lambda *_a, **_kw: (200, {"ok": True})
        self.clock.value += 20_000
        success = {
            "feature": "brush", "state": "no-targets", "success": True,
            "nextWakeAtMillis": self.clock.value + 10_000,
        }
        self.facade._cloud_map_exchange("303", "/v1/maps/targets/sync", {})
        self.facade._apply_resident_result_state("303", success)
        self.assertEqual(self.state()["dependencyWait"], waiting["dependencyWait"])
        self.facade._cloud_map_exchange("303", "/v1/presence/heartbeat", {})
        self.facade._apply_resident_result_state("303", success)
        self.assertNotIn("dependencyWait", self.state())
        self.assertNotEqual(self.state()["lastState"], "waiting-dependency")

    def test_only_a_confirmed_new_local_verdict_can_remove_the_cloud_requirement(self):
        self.seed_legacy_dependency_wait()
        success = {"feature": "brush", "state": "no-targets", "success": True,
                   "nextWakeAtMillis": self.clock.value + 10_000}
        self.clock.value += 1
        self.facade._remember_cloud_mode("303", {
            "mode": "LOCAL_ONLY", "configured": True, "heartbeatUnavailable": True,
        })
        self.facade._apply_resident_result_state("303", success)
        self.assertIn("dependencyWait", self.state(), "failure is not a local-mode verdict")
        self.clock.value += 1
        self.facade._remember_cloud_mode("303", {"mode": "LOCAL_ONLY", "configured": True})
        self.facade._apply_resident_result_state("303", success)
        self.assertNotIn("dependencyWait", self.state())

    def test_an_unscoped_configuration_error_remains_blocked_despite_idle_siblings(self):
        self.h.put(**{ACTIVE: json.dumps(self.h.old_pending())})

        def invalid(*_args):
            raise OperationKnownFailureError("invalid config", code="SHARED_BRUSH_RULE_MISSING")

        self.facade._run_configured_brush_tick = invalid
        result = self.h.tick()
        self.assertTrue(result["requiresAttention"])
        self.assertEqual(self.state()["lastState"], "blocked")

    def test_local_mode_accepted_target_stays_out_of_old_caches_after_recovery_and_restart(self):
        first = self.h.tick()
        self.assertEqual(first["state"], "dispatched")
        target = copy.deepcopy(self.h.pending()[0]["target"])
        target.update({
            "resource": "宝物",
            "composition": {"foot": 1, "bow": 0, "cavalry": 0, "chariot": 0,
                            "source": "8540-units"},
        })
        self.h.generals[1].update(status=6, statusText="战")
        self.clock.value += 31_000
        self.assertEqual(self.h.tick()["state"], "waiting")
        self.h.generals[1].update(status=0, statusText="闲")
        self.clock.value += 31_000
        self.assertEqual(self.h.tick()["state"], "completed")
        self.facade.close()
        self.h.facade = self.h.new_facade()
        self.facade = self.h.facade
        self.h.install_game_boundaries()
        self.assertIn(str(target["id"]), json.loads(self.h.public()[BRUSH_CONSUMED_FIELD]))
        self.facade._load_map_snapshot_targets = lambda **_kw: [target]
        self.clock.value += 2_000
        result = self.h.tick()
        self.assertEqual(result["state"], "dispatched", result)
        self.assertNotEqual(result["target"]["id"], target["id"])
        self.assertEqual(self.h.searched, 2)


if __name__ == "__main__":
    unittest.main()
