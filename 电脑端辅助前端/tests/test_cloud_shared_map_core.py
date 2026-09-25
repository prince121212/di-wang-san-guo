from __future__ import annotations

import copy
import dataclasses
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core import CoreFacade  # noqa: E402
from dwpm_core.facade import (  # noqa: E402
    CLOUD_PRESENCE_GRACE_MILLIS,
    CLOUD_PRESENCE_RENEW_MILLIS,
)
from dwpm_core.operations import OperationKnownFailureError  # noqa: E402
from dwpm_core.ports import PlatformPorts  # noqa: E402


class FixedClock:
    def __init__(self, value: int = 80_000_000) -> None:
        self.value = value

    def now_millis(self) -> int:
        return self.value


class RecordingLogPort:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def write(self, event) -> None:
        self.events.append(dict(event))

    def user_messages(self) -> list[str]:
        return [
            str(event.get("message"))
            for event in self.events
            if str(event.get("audience") or "") == "user"
        ]


class FakeExecution:
    operation_id = "cloud-map-test"

    def mark_request_sent(self, _metadata=None) -> None:
        return None

    def publish_progress(self, _progress: int, _details=None) -> None:
        return None

    def raise_if_cancelled(self) -> None:
        return None

    def wait(self, _seconds: float) -> None:
        return None


class FakeCloudPort:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.calls: list[dict[str, object]] = []
        self.targets: list[dict[str, object]] = []
        self.fail = False
        self.reserved = True
        self.reserve_reason = ""
        # v2 endpoints: when present, the replica fills from these instead of
        # falling back to the v1 full query.
        self.v2 = False
        self.sync_targets: list[dict[str, object]] = []

    def configured(self) -> bool:
        return True

    def exchange(self, request):
        # Config traffic is separate from the map-coordination calls asserted
        # by these tests. Dedicated config tests record every request.
        if request["path"] == "/v1/client/config":
            return {"status": 200, "body": {"ok": True, "config": {
                "schemaVersion": 1, "cloudBrushMapEnabled": True, "revision": 0,
            }}}
        if self.fail:
            raise OSError("fixture cloud unavailable")
        value = copy.deepcopy(dict(request))
        self.calls.append(value)
        path = value["path"]
        if path == "/v1/presence/heartbeat":
            count = 2 if self.mode == "CLOUD_SHARED" else 1
            return {"status": 200, "body": {
                "ok": True,
                "mode": self.mode,
                "onlineAccountCount": count,
                "threshold": 2,
            }}
        if path == "/v1/servers/directory/sync":
            return {"status": 200, "body": {
                "ok": True,
                "platformKey": value["body"]["platformKey"],
                "count": len(value["body"]["areas"]),
            }}
        if path == "/v1/servers/directory/query":
            platform_key = value["body"]["platformKey"]
            return {"status": 200, "body": {
                "ok": True,
                "platformKey": platform_key,
                "updatedAt": 79_000_000,
                "areas": [{
                    "target": "1,3",
                    "areaId": "area-351",
                    "areaName": "周年服351区",
                    "serverUrl": "https://game.example/base",
                    "serverKey": "qzone_351",
                }],
            }}
        if path == "/v1/maps/targets/sync":
            if not self.v2:
                return {"status": 404, "body": {"ok": False, "error": "HTTP 404"}}
            return {"status": 200, "body": {
                "ok": True,
                "targets": copy.deepcopy(self.sync_targets),
                "nextCursor": None,
            }}
        if path == "/v1/maps/targets/changes":
            if not self.v2:
                return {"status": 404, "body": {"ok": False, "error": "HTTP 404"}}
            return {"status": 200, "body": {
                "ok": True,
                "targets": [],
                "cursor": dict(value["body"].get("since") or {}),
            }}
        if path == "/v1/maps/targets/query":
            return {"status": 200, "body": {
                "ok": True,
                "mode": "CLOUD_SHARED",
                "targets": copy.deepcopy(self.targets),
            }}
        if path == "/v1/maps/scans/claim":
            coordinates = value["body"]["coordinates"]
            scans = [
                {**coordinate, "leaseToken": f"lease-{index}"}
                for index, coordinate in enumerate(coordinates)
            ]
            return {"status": 200, "body": {"ok": True, "scans": scans}}
        if path == "/v1/maps/observations":
            return {"status": 200, "body": {"ok": True, "regionCount": 1}}
        if path == "/v1/maps/scans/release":
            return {"status": 200, "body": {"ok": True, "releasedCount": 1}}
        if path == "/v1/maps/targets/reserve":
            return {"status": 200, "body": {
                "ok": True,
                "reserved": self.reserved,
                "reservationToken": "reservation-1" if self.reserved else "",
                **(
                    {"reason": self.reserve_reason}
                    if not self.reserved and self.reserve_reason else {}
                ),
            }}
        if path == "/v1/maps/targets/status":
            return {"status": 200, "body": {"ok": True, "updated": True}}
        raise AssertionError(f"unexpected cloud path: {path}")


class CloudSharedMapCoreTests(unittest.TestCase):
    def _facade(self, cloud: FakeCloudPort, logs=None):
        directory = tempfile.TemporaryDirectory()
        clock = FixedClock()
        facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(Path(directory.name) / "operations.json"),
            ports=PlatformPorts(
                clock=clock,
                cloud_shared_data=cloud,
                **({"logs": logs} if logs is not None else {}),
            ),
        )
        facade.account_record_upsert({
            "accountRef": "303",
            "id": 303,
            "enabled": True,
            "loginState": "ONLINE",
            "platformKey": "sglm",
            "serverId": "server-352",
            "serverName": "区352",
            "session": {
                "accountId": 303,
                "sourceMode": 1,
                "publicState": {
                    "roleId": "303",
                    "serverKey": "server-352",
                    "gameHttp": "https://game.example/kingWapServer/HttpClient?dm=private",
                    "lastValidatedAt": str(clock.value),
                    "savedTasksStarted": "true",
                    "activeResidentTaskKeys": "brushYellow",
                    "generalsJson": json.dumps([{
                        "id": 7,
                        "idHex": "0000000000000007",
                        "name": "赵云",
                    }]),
                },
            },
        })
        facade.configure_resident_automation_from_habits("303", {
            "formations": [{
                "enabled": True,
                "generalIds": ["7"],
                "soldierType": "轻骑兵",
                "soldierCount": 100,
            }],
            "config": {
                "autoStart": True,
                "startHour": 0,
                "dailyLimit": 3,
                "healWounded": False,
                "brush": {
                    "startX": 10,
                    "startY": 10,
                    "scanLimit": 1,
                    "targetKind": "山贼",
                    "rows": [{
                        "enabled": True,
                        "generalIds": ["7"],
                        "level": 1,
                    }],
                },
            },
            "mine": {"enabled": False, "rows": []},
        })
        record = json.loads(facade.account_record_json("303"))["account"]
        public = record["session"]["publicState"]
        config = json.loads(public["residentAutomationConfigJson"])
        state = json.loads(public["residentAutomationStateJson"])
        return facade, clock, directory, config, state

    def test_the_area_catalog_is_fetched_from_the_cloud_at_most_once(self) -> None:
        # The phone is where this list comes from: every login answers with the
        # game's complete area list, which is why login uploads it.  Android had
        # nowhere to keep a copy, so it passed an empty catalog in and every
        # /api/areas call went back out to read the whole platform directory -
        # for a list that changes about monthly - and then discarded it.
        cloud = FakeCloudPort("LOCAL_ONLY")
        facade, _clock, directory, _config, _state = self._facade(cloud)
        try:
            def area_queries() -> int:
                return sum(
                    1 for call in cloud.calls
                    if call["path"] == "/v1/servers/directory/query"
                )

            first = facade.dispatch("GET", "/api/areas", {"platform": "sglm"}, {})
            self.assertEqual(first.body["source"], "cloud-shared-data")
            self.assertEqual([a["serverKey"] for a in first.body["areas"]], ["qzone_351"])
            self.assertEqual(area_queries(), 1)

            for _ in range(5):
                again = facade.dispatch("GET", "/api/areas", {"platform": "sglm"}, {})
                self.assertEqual(again.body["source"], "local-cache")
                self.assertEqual(
                    [a["serverKey"] for a in again.body["areas"]], ["qzone_351"]
                )
            self.assertEqual(area_queries(), 1, "cloud must not be asked twice")

            # A host that keeps its own copy still wins outright.
            supplied = facade.dispatch("GET", "/api/areas", {
                "platform": "sglm",
                "areas": [{"areaName": "周年服999区", "serverKey": "qzone_999"}],
            }, {})
            self.assertEqual(supplied.body["source"], "local-cache")
            self.assertEqual(
                [a["serverKey"] for a in supplied.body["areas"]], ["qzone_999"]
            )
            self.assertEqual(area_queries(), 1)
        finally:
            facade.close()
            directory.cleanup()

    def test_a_login_refreshes_the_local_catalog_without_the_cloud(self) -> None:
        cloud = FakeCloudPort("LOCAL_ONLY")
        cloud.fail = True          # cloud down: the local copy must still update
        facade, _clock, directory, _config, _state = self._facade(cloud)
        try:
            facade._schedule_cloud_directory_sync("sglm", [{  # noqa: SLF001
                "serverKey": "qzone_352",
                "areaId": "area-352",
                "areaName": "周年服352区",
                "target": "2,4",
                "serverUrl": "https://game.example/base",
            }])
            served = facade.dispatch("GET", "/api/areas", {"platform": "sglm"}, {})
            self.assertEqual(served.body["source"], "local-cache")
            self.assertEqual(
                [a["serverKey"] for a in served.body["areas"]], ["qzone_352"]
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_complete_directory_sync_is_public_and_account_independent(self) -> None:
        cloud = FakeCloudPort("LOCAL_ONLY")
        facade, _clock, directory, _config, _state = self._facade(cloud)
        try:
            result = facade.cloud_directory_sync("sglm", [{
                "serverKey": "qzone_351",
                "areaId": "area-351",
                "areaName": "周年服351区",
                "target": "1,3",
                "serverUrl": (
                    "https://user:password@game.example/base"
                    "?session=private#fragment"
                ),
                "password": "must-not-cross-boundary",
            }])
            self.assertTrue(result["ok"])
            self.assertEqual(result["count"], 1)
            call = cloud.calls[-1]
            self.assertEqual(call["path"], "/v1/servers/directory/sync")
            self.assertEqual(call["body"]["platformKey"], "sglm")
            area = call["body"]["areas"][0]
            self.assertEqual(area["gameHttp"], "https://game.example/base")
            self.assertNotIn("actorId", call["body"])
            encoded = json.dumps(call, ensure_ascii=False)
            self.assertNotIn("password", encoded)
            self.assertNotIn("session=private", encoded)
        finally:
            facade.close()
            directory.cleanup()

    def test_empty_local_area_catalog_is_loaded_from_cloud_by_platform(self) -> None:
        cloud = FakeCloudPort("LOCAL_ONLY")
        facade, _clock, directory, _config, _state = self._facade(cloud)
        try:
            result = facade.dispatch(
                "GET",
                "/api/areas",
                {"platform": "热血三国联盟", "areas": []},
                {"requestId": "areas-from-cloud"},
            )
            self.assertEqual(result.status, 200)
            self.assertEqual(result.body["source"], "cloud-shared-data")
            self.assertEqual(result.body["platformKey"], "sglm")
            self.assertEqual(result.body["count"], 1)
            self.assertEqual(result.body["areas"][0]["serverKey"], "qzone_351")
            self.assertEqual(
                cloud.calls[-1]["body"],
                {"platformKey": "sglm"},
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_local_area_catalog_remains_authoritative_on_desktop(self) -> None:
        cloud = FakeCloudPort("LOCAL_ONLY")
        facade, _clock, directory, _config, _state = self._facade(cloud)
        try:
            before = len(cloud.calls)
            result = facade.dispatch(
                "GET",
                "/api/areas",
                {
                    "platform": "热血三国联盟",
                    "areas": [{
                        "areaName": "本地区服",
                        "serverKey": "local-server",
                    }],
                },
                {"requestId": "areas-local"},
            )
            self.assertEqual(result.body["source"], "local-cache")
            self.assertEqual(result.body["areas"][0]["serverKey"], "local-server")
            self.assertEqual(len(cloud.calls), before)
        finally:
            facade.close()
            directory.cleanup()

    """Entering shared mode must not take away what the account already knew.

    The two stores hold the same kind of evidence, so the tick unions them.
    Choosing exclusively made shared mode a *loss*: on a real device an account
    holding 215 usable cached bandits stopped reading them the moment a peer
    came online, the cloud answered with nothing, and it went back to sweeping
    five coordinates per tick.  Conflict avoidance is untouched - in shared mode
    every candidate still has to win a cloud reservation before any packet is
    sent - so a wider candidate set cannot make two accounts collide.
    """

    class _SnapshotPort:
        def __init__(self, targets) -> None:
            self._targets = list(targets)
            self.load_calls = 0

        def save(self, _snapshot) -> None:
            return None

        def invalidate(self, *_args, **_kwargs) -> None:
            return None

        def load(self, _account_ref, _kind, _fingerprint):
            self.load_calls += 1
            return {
                "scannedAtMillis": FixedClock().value,
                "targets": self._targets,
            }

    def _cached_bandit(self, target_id: int, x: int, y: int):
        return {
            "targetId": target_id,
            "x": x,
            "y": y,
            "type": "山贼",
            "level": 1,
            "filterFields": {
                # Mirrors the shape the working cloud fixture target uses, so
                # the cached path is compared against the same filters.
                "compositionCode": "0500",
                "dropCategories": '["资源"]',
                "kind": "山贼",
                "name": "1级山贼",
            },
        }

    def test_a_cache_only_target_never_consumes_a_shared_round(self) -> None:
        """Only the shared pool may supply candidates while a peer is online.

        A target that exists solely in this account's cache cannot be reserved
        - the Worker has never heard of it - so offering it as a shared
        candidate consumed the whole round on a reservation that could never
        succeed.  Both accounts stopped dispatching 刷黄 for 35 minutes.  With
        no shared candidate the tick must fall through to the ordinary scan.
        """

        cloud = FakeCloudPort("CLOUD_SHARED")
        cloud.targets = []
        facade, _clock, directory, config, state = self._facade(cloud)
        port = self._SnapshotPort([self._cached_bandit(0x5678, 10, 10)])
        facade._ports = dataclasses.replace(  # noqa: SLF001
            facade._ports, map_snapshots=port  # noqa: SLF001
        )
        scans: list[dict] = []

        def local_search(_self, _execution, body, _context):
            scans.append(dict(body))
            return self._empty_search(_self, _execution, body, _context)

        facade._run_brush_search_game_workflow = types.MethodType(  # noqa: SLF001
            local_search, facade
        )
        try:
            result = facade._run_configured_brush_tick(  # noqa: SLF001
                FakeExecution(), "303", config, state, {}
            )

            # The round was spent scanning, not thrown away on an
            # un-arbitrable reservation.
            self.assertEqual(len(scans), 1)
            self.assertNotEqual(
                result["message"], "匹配目标已由同区服其他账号领取，稍后重试"
            )
            self.assertNotIn(
                "/v1/maps/targets/reserve",
                [call["path"] for call in cloud.calls],
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_the_cache_is_read_even_when_no_peer_is_online(self) -> None:
        cloud = FakeCloudPort("LOCAL_ONLY")
        facade, _clock, directory, config, state = self._facade(cloud)
        port = self._SnapshotPort([self._cached_bandit(0x5678, 10, 10)])
        facade._ports = dataclasses.replace(  # noqa: SLF001
            facade._ports, map_snapshots=port  # noqa: SLF001
        )
        facade._observe_local_map("303", "bandit", (12, 12), [{
            "id": 0x5678, "kind": "山贼", "level": 1, "x": 10, "y": 10,
            "composition": {"foot": 0, "bow": 5, "cavalry": 0, "chariot": 0, "source": "8540-units"},
            "compositionCode": "0500", "dropCategories": ["资源"],
        }])
        def accepted(_self, _execution, body, _context):
            return {"result": {
                "success": True,
                "successBattleId": 9003,
                "battleText": "fixture accepted",
                "target": dict(body["target"]),
            }}

        facade._run_brush_search_game_workflow = types.MethodType(  # noqa: SLF001
            self._empty_search, facade
        )
        facade._run_brush_execute_game_workflow = types.MethodType(  # noqa: SLF001
            accepted, facade
        )
        try:
            result = facade._run_configured_brush_tick(  # noqa: SLF001
                FakeExecution(), "303", config, state, {}
            )
            self.assertEqual(result["target"]["id"], 0x5678)
            # No peer, so no reservation round trip is attempted.
            self.assertNotIn(
                "/v1/maps/targets/reserve",
                [call["path"] for call in cloud.calls],
            )
        finally:
            facade.close()
            directory.cleanup()

    @staticmethod
    def _configure_mine(facade: CoreFacade) -> tuple[dict, dict]:
        facade.configure_resident_automation_from_habits("303", {
            "formations": [{
                "enabled": True,
                "generalIds": ["7"],
                "soldierType": "轻骑兵",
                "soldierCount": 100,
            }],
            "config": {
                "autoStart": True,
                "startHour": 0,
                "dailyLimit": 3,
                "brush": {
                    "startX": 10,
                    "startY": 10,
                    "scanLimit": 1,
                    "targetKind": "山贼",
                    "rows": [{
                        "enabled": True,
                        "generalIds": ["7"],
                        "level": 1,
                    }],
                },
            },
            "mine": {
                "enabled": True,
                "centerX": 10,
                "centerY": 10,
                "rows": [{
                    "enabled": True,
                    "generalIds": ["7"],
                    "resourceType": "银矿",
                    "level": 1,
                    "x": 10,
                    "y": 10,
                    "scope": "定点",
                }],
            },
        })
        record = json.loads(facade.account_record_json("303"))["account"]
        public = record["session"]["publicState"]
        return (
            json.loads(public["residentAutomationConfigJson"]),
            json.loads(public["residentAutomationStateJson"]),
        )

    @staticmethod
    def _empty_search(_self, _execution, body, _context):
        return {
            "targets": [],
            "scanOffset": int(body["scanOffset"]),
            "scanLimit": int(body["scanLimit"]),
            "scanBatchSize": int(body["scanBatchSize"]),
            "scannedCount": 1,
            "nextScanOffset": 0,
            "scanWrapped": True,
            "scannedCoordinates": [[10, 10]],
            "scanResults": [{"scanCoord": [10, 10], "targets": []}],
        }

    def test_one_account_calls_only_presence_and_keeps_local_scan_path(self) -> None:
        cloud = FakeCloudPort("LOCAL_ONLY")
        facade, _clock, directory, config, state = self._facade(cloud)
        captured: list[dict[str, object]] = []

        def local_search(_self, _execution, body, _context):
            captured.append(dict(body))
            return self._empty_search(_self, _execution, body, _context)

        facade._run_brush_search_game_workflow = types.MethodType(  # noqa: SLF001
            local_search, facade
        )
        try:
            result = facade._run_configured_brush_tick(  # noqa: SLF001
                FakeExecution(), "303", config, state, {}
            )
            self.assertEqual(result["state"], "no-targets")
            self.assertEqual(
                [call["path"] for call in cloud.calls],
                ["/v1/presence/heartbeat"],
            )
            self.assertEqual(len(captured), 1)
            self.assertNotIn("_scanCoordinatesOverride", captured[0])
            self.assertNotIn("includeScanObservationTargets", captured[0])
            policy = facade.cloud_map_coordination_policy("303")
            self.assertEqual(policy["mode"], "LOCAL_ONLY")
            self.assertTrue(policy["legacyLocalMapPrefetchAllowed"])
        finally:
            facade.close()
            directory.cleanup()

    def test_a_filter_that_matches_nothing_all_round_advises_relaxing_it(self) -> None:
        """Fifteen empty batches say the filter, not the map, is the problem.

        "暂时没有目标" and "筛选条件在这个区里几乎选不出目标" both surface as a
        no-targets tick; only accumulated evidence tells them apart.  The core
        counts actually-scanned coordinates against the filter fingerprint and,
        at 75 (fifteen batches of five, just under one full 80-coordinate
        round), says so once.  A matched target ends the episode: the count
        clears and the panel hears the usual "已恢复运行".
        """
        logs = RecordingLogPort()
        cloud = FakeCloudPort("LOCAL_ONLY")
        facade, _clock, directory, _config, _state = self._facade(cloud, logs=logs)
        facade.configure_resident_automation_from_habits("303", {
            "formations": [{
                "enabled": True,
                "generalIds": ["7"],
                "soldierType": "轻骑兵",
                "soldierCount": 100,
            }],
            "config": {
                "autoStart": True,
                "startHour": 0,
                "dailyLimit": 3,
                "healWounded": False,
                "brush": {
                    "startX": 10,
                    "startY": 10,
                    "scanLimit": 80,
                    "targetKind": "山贼",
                    "rows": [{
                        "enabled": True,
                        "generalIds": ["7"],
                        "level": 1,
                    }],
                },
            },
            "mine": {"enabled": False, "rows": []},
        })

        def empty_batch(_self, _execution, body, _context):
            offset = int(body["scanOffset"])
            limit = int(body["scanLimit"])
            batch = int(body["scanBatchSize"])
            next_offset = offset + batch
            wrapped = next_offset >= limit
            return {
                "targets": [],
                "scanOffset": offset,
                "scanLimit": limit,
                "scanBatchSize": batch,
                "scannedCount": batch,
                "nextScanOffset": 0 if wrapped else next_offset,
                "scanWrapped": wrapped,
                "scannedCoordinates": [],
                "scanResults": [],
            }

        facade._run_brush_search_game_workflow = types.MethodType(  # noqa: SLF001
            empty_batch, facade
        )

        def stored_state() -> dict:
            public = json.loads(
                facade.account_record_json("303")
            )["account"]["session"]["publicState"]
            return json.loads(public["residentAutomationStateJson"])

        try:
            config = json.loads(json.loads(
                facade.account_record_json("303")
            )["account"]["session"]["publicState"]["residentAutomationConfigJson"])
            state = stored_state()
            for tick in range(1, 18):
                result = facade._run_configured_brush_tick(  # noqa: SLF001
                    FakeExecution(), "303", config, state, {}
                )
                state = stored_state()
                if tick < 15:
                    self.assertEqual(
                        result["state"], "no-targets", f"tick {tick}",
                    )
                else:
                    self.assertEqual(
                        result["state"], "filter-strict", f"tick {tick}",
                    )
                    self.assertIn("【建议】", result["message"])
                    self.assertIn("筛选条件可能过严", result["message"])

            advice_lines = [
                message for message in logs.user_messages()
                if "【建议】" in message
            ]
            self.assertEqual(
                1, len(advice_lines), "the conclusion is announced once",
            )
            brush = state["brush"]
            self.assertEqual(brush["noMatchScannedCoords"], 17 * 5)
            self.assertTrue(brush["filterAdviceActive"])

            def matched(_self, _execution, body, _context):
                found = {
                    "id": 0x1234,
                    "x": 10,
                    "y": 10,
                    "kind": "山贼",
                    "level": 1,
                }
                return {
                    **empty_batch(_self, _execution, body, _context),
                    "targets": [found],
                }

            def accepted(_self, _execution, body, _context):
                return {"result": {
                    "success": True,
                    "successBattleId": 9001,
                    "target": dict(body["target"]),
                }}

            facade._run_brush_search_game_workflow = types.MethodType(  # noqa: SLF001
                matched, facade
            )
            facade._run_brush_execute_game_workflow = types.MethodType(  # noqa: SLF001
                accepted, facade
            )
            result = facade._run_configured_brush_tick(  # noqa: SLF001
                FakeExecution(), "303", config, state, {}
            )

            self.assertEqual(result["state"], "dispatched")
            brush = stored_state()["brush"]
            self.assertEqual(brush["noMatchScannedCoords"], 0)
            self.assertFalse(brush["filterAdviceActive"])
            self.assertIn("刷黄已恢复运行", logs.user_messages())
        finally:
            facade.close()
            directory.cleanup()

    def test_a_changed_filter_restarts_the_advice_count(self) -> None:
        """The operator acting on the advice must not be advised again at once.

        The fingerprint covers the filter's meaning (centre, levels, drops,
        composition), so an edit zeroes the accumulated evidence and the next
        seventy-five coordinates decide afresh.
        """
        logs = RecordingLogPort()
        cloud = FakeCloudPort("LOCAL_ONLY")
        facade, _clock, directory, _config, _state = self._facade(cloud, logs=logs)

        habits = {
            "formations": [{
                "enabled": True,
                "generalIds": ["7"],
                "soldierType": "轻骑兵",
                "soldierCount": 100,
            }],
            "config": {
                "autoStart": True,
                "startHour": 0,
                "dailyLimit": 3,
                "healWounded": False,
                "brush": {
                    "startX": 10,
                    "startY": 10,
                    "scanLimit": 80,
                    "targetKind": "山贼",
                    "rows": [{
                        "enabled": True,
                        "generalIds": ["7"],
                        "level": 1,
                    }],
                },
            },
            "mine": {"enabled": False, "rows": []},
        }
        facade.configure_resident_automation_from_habits("303", habits)

        def empty_batch(_self, _execution, body, _context):
            offset = int(body["scanOffset"])
            limit = int(body["scanLimit"])
            batch = int(body["scanBatchSize"])
            next_offset = offset + batch
            wrapped = next_offset >= limit
            return {
                "targets": [],
                "scanOffset": offset,
                "scanLimit": limit,
                "scanBatchSize": batch,
                "scannedCount": batch,
                "nextScanOffset": 0 if wrapped else next_offset,
                "scanWrapped": wrapped,
                "scannedCoordinates": [],
                "scanResults": [],
            }

        facade._run_brush_search_game_workflow = types.MethodType(  # noqa: SLF001
            empty_batch, facade
        )

        def stored() -> tuple[dict, dict]:
            public = json.loads(
                facade.account_record_json("303")
            )["account"]["session"]["publicState"]
            return (
                json.loads(public["residentAutomationConfigJson"]),
                json.loads(public["residentAutomationStateJson"]),
            )

        try:
            config, state = stored()
            for _ in range(16):
                result = facade._run_configured_brush_tick(  # noqa: SLF001
                    FakeExecution(), "303", config, state, {}
                )
                _config, state = stored()
            self.assertEqual(result["state"], "filter-strict")

            # The operator widens the levels; the fingerprint changes.
            widened = copy.deepcopy(habits)
            widened["config"]["brush"]["rows"][0]["levels"] = [1, 2]
            del widened["config"]["brush"]["rows"][0]["level"]
            facade.configure_resident_automation_from_habits("303", widened)
            config, state = stored()
            result = facade._run_configured_brush_tick(  # noqa: SLF001
                FakeExecution(), "303", config, state, {}
            )

            self.assertEqual(result["state"], "no-targets")
            brush = stored()[1]["brush"]
            self.assertEqual(brush["noMatchScannedCoords"], 5)
            self.assertFalse(brush["filterAdviceActive"])
        finally:
            facade.close()
            directory.cleanup()

    def test_an_unknown_cloud_target_is_republished_from_the_replica(self) -> None:
        """A reserve refusal naming an unknown target re-publishes the truth.

        The legacy orphan sweep hard-deleted v2 uploads and left no tombstone
        for the changes feed, so replicas kept offering phantoms whose
        reservations could never succeed - and the account never rescanned,
        because candidates existed.  When the cloud answers unknown-target,
        the client re-queues the replica row as an upsert immediately, so the
        next round can actually reserve it.
        """
        cloud = FakeCloudPort("CLOUD_SHARED")
        cloud.v2 = True
        cloud.reserved = False
        cloud.reserve_reason = "unknown-target"
        cloud.sync_targets = [{
            "targetId": "0000000000001234",
            "x": 10,
            "y": 10,
            "type": "山贼",
            "level": 1,
            "lastSeenAtMillis": 80_000_000,
            "changedAtMillis": 80_000_000,
            "status": "available",
            "data": {
                "name": "1级山贼",
                "kind": "山贼",
                "composition": {
                    "foot": 0, "bow": 2, "cavalry": 0, "chariot": 0,
                    "source": "8540-units",
                },
            },
        }]
        facade, _clock, directory, config, state = self._facade(cloud)

        def forbidden_scan(*_args, **_kwargs):
            raise AssertionError("a cached candidate must skip the game-map scan")

        facade._run_brush_search_game_workflow = forbidden_scan  # noqa: SLF001
        try:
            result = facade._run_configured_brush_tick(  # noqa: SLF001
                FakeExecution(), "303", config, state, {}
            )

            self.assertEqual(result["state"], "no-targets")
            self.assertIn("云端记录同步中", result["message"])
            observations = [
                call for call in cloud.calls
                if call["path"] == "/v1/maps/observations"
            ]
            self.assertEqual(
                1, len(observations), "the phantom is re-published at once",
            )
            upserts = observations[0]["body"].get("upserts") or []
            self.assertEqual(
                [str(row.get("targetId")) for row in upserts],
                ["0000000000001234"],
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_cloud_target_is_used_without_rescanning_and_is_reserved(self) -> None:
        cloud = FakeCloudPort("CLOUD_SHARED")
        cloud.targets = [{
            "targetId": "0000000000001234",
            "x": 10,
            "y": 10,
            "type": "山贼",
            "level": 1,
            "data": {
                "name": "1级山贼",
                "kind": "山贼",
                "composition": {
                    "foot": 0, "bow": 5, "cavalry": 0, "chariot": 0,
                    "source": "8540-units",
                },
            },
        }]
        facade, _clock, directory, config, state = self._facade(cloud)

        def forbidden_scan(*_args, **_kwargs):
            raise AssertionError("cloud target should avoid a game-map scan")

        def accepted(_self, _execution, body, _context):
            return {"result": {
                "success": True,
                "successBattleId": 9001,
                "battleText": "fixture accepted",
                "target": dict(body["target"]),
            }}

        facade._run_brush_search_game_workflow = forbidden_scan  # noqa: SLF001
        facade._run_brush_execute_game_workflow = types.MethodType(  # noqa: SLF001
            accepted, facade
        )
        try:
            result = facade._run_configured_brush_tick(  # noqa: SLF001
                FakeExecution(), "303", config, state, {}
            )
            self.assertEqual(result["state"], "dispatched")
            paths = [call["path"] for call in cloud.calls]
            # v2 的目标来源是本地副本：首轮先探测 /v1/maps/targets/sync，
            # 本 fixture 扮演旧 Worker（无 v2 端点），本轮降级回 v1 全量
            # 查询，后续行为不变。
            self.assertEqual(paths, [
                "/v1/presence/heartbeat",
                "/v1/maps/targets/sync",
                "/v1/maps/targets/query",
                "/v1/maps/targets/reserve",
                "/v1/maps/targets/status",
                "/v1/maps/targets/status",
            ])
            statuses = [
                call["body"]["status"]
                for call in cloud.calls
                if call["path"] == "/v1/maps/targets/status"
            ]
            self.assertEqual(statuses, ["dispatching", "dispatched"])
            heartbeat = cloud.calls[0]["body"]
            self.assertEqual(len(heartbeat["actorId"]), 64)
            self.assertNotIn("roleId", heartbeat)
            self.assertNotIn("dm", json.dumps(heartbeat))
        finally:
            facade.close()
            directory.cleanup()

    def test_cloud_scan_claims_publish_normalized_observation_before_reserve(self) -> None:
        cloud = FakeCloudPort("CLOUD_SHARED")
        facade, _clock, directory, config, state = self._facade(cloud)

        def scanned(_self, _execution, body, _context):
            self.assertEqual(body["_scanCoordinatesOverride"], [[12, 12]])
            target = {
                "id": 0x1234,
                "idHex": "0000000000001234",
                "x": 10,
                "y": 10,
                "kind": "山贼",
                "level": 1,
                "composition": {
                    "foot": 0, "bow": 5, "cavalry": 0, "chariot": 0,
                    "source": "8540-units",
                },
                "password": "local-only",
                "rawPayload": "deadbeef",
            }
            return {
                "targets": [target],
                "scanOffset": 0,
                "scanLimit": 1,
                "scanBatchSize": 1,
                "scannedCount": 1,
                "nextScanOffset": 0,
                "scanWrapped": True,
                "scannedCoordinates": [[12, 12]],
                "scanResults": [{
                    "scanCoord": [12, 12],
                    "targets": [target],
                }],
            }

        def accepted(_self, _execution, body, _context):
            return {"result": {
                "success": True,
                "successBattleId": 9002,
                "target": dict(body["target"]),
            }}

        facade._run_brush_search_game_workflow = types.MethodType(  # noqa: SLF001
            scanned, facade
        )
        facade._run_brush_execute_game_workflow = types.MethodType(  # noqa: SLF001
            accepted, facade
        )
        try:
            result = facade._run_configured_brush_tick(  # noqa: SLF001
                FakeExecution(), "303", config, state, {}
            )
            self.assertEqual(result["state"], "dispatched")
            paths = [call["path"] for call in cloud.calls]
            self.assertLess(
                paths.index("/v1/maps/observations"),
                paths.index("/v1/maps/targets/reserve"),
            )
            observation_call = next(
                call for call in cloud.calls
                if call["path"] == "/v1/maps/observations"
            )
            encoded = json.dumps(observation_call["body"], ensure_ascii=False)
            self.assertNotIn("password", encoded)
            self.assertNotIn("rawPayload", encoded)
            region = observation_call["body"]["regions"][0]
            self.assertEqual(region["leaseToken"], "lease-0")
        finally:
            facade.close()
            directory.cleanup()

    def test_outage_falls_back_for_brush_but_keeps_mine_fail_closed(self) -> None:
        cloud = FakeCloudPort("CLOUD_SHARED")
        facade, clock, directory, config, state = self._facade(cloud)
        scans = 0

        def local_scan(*_args, **_kwargs):
            nonlocal scans
            scans += 1
            return {}

        facade._run_brush_search_game_workflow = local_scan  # noqa: SLF001
        try:
            shared_policy = facade.cloud_map_coordination_policy("303")
            self.assertEqual(shared_policy["mode"], "CLOUD_SHARED")
            self.assertFalse(
                shared_policy["legacyLocalMapPrefetchAllowed"]
            )
            clock.value += CLOUD_PRESENCE_RENEW_MILLIS + 1_000
            cloud.fail = True
            outage_policy = facade.cloud_map_coordination_policy("303")
            self.assertEqual(outage_policy["mode"], "CLOUD_UNAVAILABLE")
            self.assertFalse(
                outage_policy["legacyLocalMapPrefetchAllowed"]
            )
            self.assertTrue(outage_policy["legacyLocalBanditMapPrefetchAllowed"])
            result = facade._run_configured_brush_tick(
                FakeExecution(), "303", config, state, {}
            )
            self.assertEqual(result["mapMode"], "LOCAL_FALLBACK")
            self.assertEqual(scans, 1)
            self.assertEqual(facade._cloud_presence_mode("303")["mode"], "CLOUD_UNAVAILABLE")
            with self.assertRaises(OperationKnownFailureError):
                facade._cloud_map_action_mode("303", "找矿")
        finally:
            facade.close()
            directory.cleanup()

    def test_repeated_heartbeat_failures_cannot_forget_previously_shared_mode(self):
        cloud = FakeCloudPort("CLOUD_SHARED")
        facade, clock, directory, _config, _state = self._facade(cloud)
        try:
            self.assertEqual(facade.cloud_presence_heartbeat("303")["mode"], "CLOUD_SHARED")
            cloud.fail = True
            for _ in range(4):
                clock.value += CLOUD_PRESENCE_RENEW_MILLIS + 1
                result = facade.cloud_map_coordination_policy("303")
                self.assertEqual(result["mode"], "CLOUD_UNAVAILABLE")
                self.assertFalse(result["legacyLocalMapPrefetchAllowed"])
            # Reload the real account store with no in-memory mode history.
            path = str(Path(directory.name) / "operations.json")
            facade.close()
            facade = CoreFacade(
                shared_root=ROOT / "shared_core", operation_store_path=path,
                ports=PlatformPorts(clock=clock, cloud_shared_data=cloud),
            )
            clock.value += CLOUD_PRESENCE_RENEW_MILLIS + 1
            self.assertEqual(facade.cloud_presence_heartbeat("303")["mode"], "CLOUD_UNAVAILABLE")
            cloud.fail = False
            cloud.mode = "LOCAL_ONLY"
            clock.value += CLOUD_PRESENCE_GRACE_MILLIS + 1
            self.assertEqual(facade.cloud_presence_heartbeat("303")["mode"], "LOCAL_ONLY")
        finally:
            facade.close()
            directory.cleanup()

    def test_missing_own_presence_does_not_mean_peers_left(self):
        cloud = FakeCloudPort("CLOUD_SHARED")
        facade, _clock, directory, _config, _state = self._facade(cloud)
        try:
            self.assertEqual(facade.cloud_presence_heartbeat("303")["mode"], "CLOUD_SHARED")
            facade._cloud_shared_exchange = lambda *_a, **_kw: (
                409, {"ok": False, "code": "PRESENCE_REQUIRED"}
            )
            with self.assertRaises(OperationKnownFailureError) as raised:
                facade._cloud_map_exchange("303", "/v1/maps/targets/reserve", {})
            self.assertEqual(raised.exception.code, "CLOUD_SHARED_DATA_UNAVAILABLE")
            policy = facade.cloud_map_coordination_policy("303")
            self.assertEqual(policy["mode"], "CLOUD_SHARED")
            self.assertFalse(policy["legacyLocalMapPrefetchAllowed"])
        finally:
            facade.close()
            directory.cleanup()

    def test_one_account_mine_search_also_remains_local_only(self) -> None:
        cloud = FakeCloudPort("LOCAL_ONLY")
        facade, _clock, directory, _config, _state = self._facade(cloud)
        config, state = self._configure_mine(facade)
        calls = 0

        def local_mine(_self, _execution, _body, _context):
            nonlocal calls
            calls += 1
            return {"targets": [], "mines": [], "scanResults": []}

        facade._run_mine_search_game_workflow = types.MethodType(  # noqa: SLF001
            local_mine, facade
        )
        try:
            result = facade._run_configured_mine_tick(  # noqa: SLF001
                FakeExecution(), "303", config, state, {}
            )
            self.assertEqual(result["state"], "no-targets")
            self.assertEqual(calls, 1)
            self.assertEqual(
                [call["path"] for call in cloud.calls],
                [],
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_mine_ignores_cloud_targets_even_when_cloud_sharing_is_available(self) -> None:
        cloud = FakeCloudPort("CLOUD_SHARED")
        cloud.targets = [{"targetId": "0000000000005678", "x": 10, "y": 10,
                          "type": "银矿", "level": 1}]
        facade, _clock, directory, _config, _state = self._facade(cloud)
        config, state = self._configure_mine(facade)
        calls = []
        def local_scan(_execution, body, _context):
            calls.append(body)
            return {"targets": [{"id": 88, "kind": "银矿", "level": 1,
                                 "x": 10, "y": 10, "playerOccupied": False}]}
        facade._run_mine_search_game_workflow = local_scan
        facade._run_mine_execute_game_workflow = lambda _e, body, _c: {"result": {
            "success": True, "successBattleId": 9100, "target": body["target"]}}
        try:
            result = facade._run_configured_mine_tick(FakeExecution(), "303", config, state, {})
            self.assertEqual(result["state"], "dispatched")
            self.assertEqual(result["target"]["id"], 88)
            self.assertEqual(len(calls), 1)
            self.assertEqual(cloud.calls, [])
        finally:
            facade.close()
            directory.cleanup()

    def test_manual_brush_search_reuses_cloud_target_without_game_scan(self) -> None:
        cloud = FakeCloudPort("CLOUD_SHARED")
        cloud.targets = [{
            "targetId": "0000000000001234",
            "x": 10,
            "y": 10,
            "type": "山贼",
            "level": 1,
            "data": {"name": "1级山贼", "kind": "山贼"},
        }]
        facade, _clock, directory, _config, _state = self._facade(cloud)

        def forbidden(*_args, **_kwargs):
            raise AssertionError("manual cloud search must not rescan a known target")

        facade._run_brush_search_game_workflow = forbidden  # noqa: SLF001
        body = facade.brush_search_operation_payload({
            "accountRef": "303",
            "startX": 10,
            "startY": 10,
            "scanLimit": 20,
            "targetKind": "山贼",
            "levels": [1],
        }, {})
        try:
            result = facade._run_cloud_coordinated_brush_search_game_workflow(  # noqa: SLF001
                FakeExecution(), body, {}
            )
            self.assertTrue(result["cloudSharedMap"])
            self.assertEqual(result["count"], 1)
            # v2 副本探测 sync 失败（旧 Worker）后降级 v1 全量查询。
            self.assertEqual(
                [call["path"] for call in cloud.calls],
                [
                    "/v1/presence/heartbeat",
                    "/v1/maps/targets/sync",
                    "/v1/maps/targets/query",
                ],
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_manual_cloud_search_scans_only_claimed_batch_and_publishes(self) -> None:
        cloud = FakeCloudPort("CLOUD_SHARED")
        facade, _clock, directory, _config, _state = self._facade(cloud)
        captured: list[dict[str, object]] = []

        def scanned(_self, _execution, body, _context):
            captured.append(dict(body))
            coordinates = list(body["_scanCoordinatesOverride"])
            return {
                "targets": [],
                "scanResults": [
                    {"scanCoord": coordinate, "targets": []}
                    for coordinate in coordinates
                ],
                "scannedCoordinates": coordinates,
            }

        facade._run_brush_search_game_workflow = types.MethodType(  # noqa: SLF001
            scanned, facade
        )
        body = facade.brush_search_operation_payload({
            "accountRef": "303",
            "startX": 10,
            "startY": 10,
            "scanLimit": 40,
            "targetKind": "山贼",
        }, {})
        try:
            result = facade._run_cloud_coordinated_brush_search_game_workflow(  # noqa: SLF001
                FakeExecution(), body, {}
            )
            self.assertEqual(len(captured), 1)
            self.assertEqual(len(captured[0]["_scanCoordinatesOverride"]), 20)
            self.assertEqual(result["scannedCount"], 20)
            self.assertEqual(result["nextScanOffset"], 20)
            self.assertEqual(
                [call["path"] for call in cloud.calls],
                [
                    "/v1/presence/heartbeat",
                    # sync 瞬时失败后降级 v1 查询；退避到期才再探测，
                    # 不能在同一个手动扫描里重复打失败的端点。
                    "/v1/maps/targets/sync",
                    "/v1/maps/targets/query",
                    "/v1/maps/scans/claim",
                    "/v1/maps/observations",
                    "/v1/maps/targets/query",
                ],
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_manual_brush_execute_reserves_before_raw_dispatch(self) -> None:
        cloud = FakeCloudPort("CLOUD_SHARED")
        facade, _clock, directory, _config, _state = self._facade(cloud)
        target = {
            "id": 0x1234,
            "idHex": "0000000000001234",
            "x": 10,
            "y": 10,
            "kind": "山贼",
            "level": 1,
        }

        def accepted(_self, _execution, body, _context):
            self.assertEqual(body["target"]["id"], 0x1234)
            return {"ok": True, "result": {"success": True}}

        facade._run_brush_execute_game_workflow = types.MethodType(  # noqa: SLF001
            accepted, facade
        )
        try:
            result = facade._run_cloud_coordinated_brush_execute_game_workflow(  # noqa: SLF001
                FakeExecution(),
                {"accountRef": "303", "target": target, "generalIds": [7]},
                {},
            )
            self.assertTrue(result["cloudSharedMap"])
            self.assertEqual(
                [call["path"] for call in cloud.calls],
                [
                    "/v1/presence/heartbeat",
                    "/v1/maps/targets/reserve",
                    "/v1/maps/targets/status",
                    "/v1/maps/targets/status",
                ],
            )
            statuses = [
                call["body"]["status"]
                for call in cloud.calls
                if call["path"] == "/v1/maps/targets/status"
            ]
            self.assertEqual(statuses, ["dispatching", "dispatched"])
        finally:
            facade.close()
            directory.cleanup()

    def test_manual_execute_keeps_exact_local_path_for_one_account(self) -> None:
        cloud = FakeCloudPort("LOCAL_ONLY")
        facade, _clock, directory, _config, _state = self._facade(cloud)
        calls = 0

        def accepted(_self, _execution, _body, _context):
            nonlocal calls
            calls += 1
            return {"ok": True, "result": {"success": True}}

        facade._run_mine_execute_game_workflow = types.MethodType(  # noqa: SLF001
            accepted, facade
        )
        try:
            result = facade._run_cloud_coordinated_mine_execute_game_workflow(  # noqa: SLF001
                FakeExecution(),
                {
                    "accountRef": "303",
                    "target": {"id": 0x5678, "x": 10, "y": 10},
                    "generalIds": [7],
                },
                {},
            )
            self.assertTrue(result["ok"])
            self.assertEqual(calls, 1)
            self.assertEqual(
                [call["path"] for call in cloud.calls],
                [],
            )
        finally:
            facade.close()
            directory.cleanup()


class PresenceIsAboutRecencyTests(unittest.TestCase):
    """A lease must be renewed by a clock, not by unrelated business work.

    Renewal used to happen only inside a brush or mine round, and those run
    minutes apart while the generals are out, so the lease expired between
    renewals: two accounts that were both running watched each other appear and
    disappear every one to two minutes, deferring a brush round on each flip.
    """

    def _facade(self, cloud):
        directory = tempfile.TemporaryDirectory()
        clock = FixedClock()
        facade = CoreFacade(
            shared_root=ROOT / "shared_core",
            operation_store_path=str(Path(directory.name) / "operations.json"),
            ports=PlatformPorts(clock=clock, cloud_shared_data=cloud),
        )
        facade.account_record_upsert({
            "accountRef": "303",
            "id": 303,
            "enabled": True,
            "loginState": "ONLINE",
            "platformKey": "sglm",
            "serverId": "server-352",
            "serverName": "区352",
            "session": {
                "accountId": 303,
                "sourceMode": 1,
                "publicState": {"roleId": "303", "serverKey": "server-352"},
            },
        })
        return facade, clock, directory

    def test_one_late_renewal_does_not_drop_shared_mode(self) -> None:
        cloud = FakeCloudPort("CLOUD_SHARED")
        facade, clock, directory = self._facade(cloud)
        try:
            self.assertEqual(
                facade._cloud_presence_mode("303")["mode"],  # noqa: SLF001
                "CLOUD_SHARED",
            )

            # The peer is mid-battle and a moment late; the Worker reports one.
            cloud.mode = "LOCAL_ONLY"
            clock.value += CLOUD_PRESENCE_RENEW_MILLIS + 1_000
            held = facade._cloud_presence_mode("303")  # noqa: SLF001
            self.assertEqual(held["mode"], "CLOUD_SHARED")
            self.assertTrue(held["sharedHeldByGrace"])
        finally:
            facade.close()
            directory.cleanup()

    def test_a_peer_that_really_left_is_released_after_the_grace_window(self) -> None:
        cloud = FakeCloudPort("CLOUD_SHARED")
        facade, clock, directory = self._facade(cloud)
        try:
            facade._cloud_presence_mode("303")  # noqa: SLF001
            cloud.mode = "LOCAL_ONLY"
            clock.value += CLOUD_PRESENCE_GRACE_MILLIS + 1_000

            self.assertEqual(
                facade._cloud_presence_mode("303")["mode"],  # noqa: SLF001
                "LOCAL_ONLY",
            )
        finally:
            facade.close()
            directory.cleanup()

    def test_the_lease_is_renewed_well_inside_the_observed_expiry(self) -> None:
        """v2：扫描租约废弃后心跳只剩在线证明，但仍须明显快于宽限期。

        v1 要求 20 秒续期，因为扫描租约实测 60-90 秒过期、靠心跳续命。
        v2（cloud_event_sync_v2_spec）改用 onlineActorIds 确定性分片，
        服务端 PRESENCE_TTL 放宽到 300 秒，续期 120 秒即可；约束改为：
        宽限期必须盖住至少两个续期周期，模式才不会因一次迟到而抖动。
        """

        self.assertLessEqual(
            CLOUD_PRESENCE_RENEW_MILLIS * 2,
            CLOUD_PRESENCE_GRACE_MILLIS,
        )

    def test_a_never_shared_account_is_not_promoted_by_grace(self) -> None:
        cloud = FakeCloudPort("LOCAL_ONLY")
        facade, clock, directory = self._facade(cloud)
        try:
            for _ in range(3):
                self.assertEqual(
                    facade._cloud_presence_mode("303")["mode"],  # noqa: SLF001
                    "LOCAL_ONLY",
                )
                clock.value += CLOUD_PRESENCE_RENEW_MILLIS + 1_000
        finally:
            facade.close()
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
