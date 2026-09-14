"""云端共享地图 v2：本地副本 + 事件驱动上报的共享核心测试。

规格：docs/core_migration/cloud_event_sync_v2_spec.md。覆盖：全量同步分页
→ 增量订阅 → 本地筛选、扫描比对产生 upserts/gone、上传失败队列保留、
副本文件损坏重建、确定性分片下标、TTL 本地过期、旧 Worker 回退，以及
facade 接线后的 v2 全链路（副本供目标、分片替租约、事件上报替全量）。
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared_core" / "python"))

from dwpm_core import CoreFacade  # noqa: E402
from dwpm_core.features.cloud_map_replica import (  # noqa: E402
    BANDIT_TARGET_TTL_MILLIS,
    CHANGES_MIN_INTERVAL_MILLIS,
    MINE_TARGET_TTL_MILLIS,
    CloudMapReplicaStore,
    shard_coordinates,
)
from dwpm_core.features.targets import brush_scan_coordinates  # noqa: E402
from dwpm_core.ports import PlatformPorts  # noqa: E402


class MutableClock:
    def __init__(self, value: int = 1_700_000_000_000) -> None:
        self.value = value

    def now_millis(self) -> int:
        return self.value


def cloud_row(
    target_id: str,
    *,
    x: int = 10,
    y: int = 10,
    row_type: str = "山贼",
    level: int = 1,
    last_seen: int = 1_700_000_000_000,
    changed: int = 100,
    status: str = "available",
    lease_until: int = 0,
    retry_after: int = 0,
    data: dict | None = None,
) -> dict:
    return {
        "targetId": target_id,
        "x": x,
        "y": y,
        "type": row_type,
        "level": level,
        "lastSeenAtMillis": last_seen,
        "changedAtMillis": changed,
        "status": status,
        "statusAtMillis": last_seen,
        "leaseUntilMillis": lease_until,
        "retryAfterMillis": retry_after,
        "data": dict(data or {"name": f"{level}级{row_type}", "kind": row_type}),
    }


def observation(
    target_id: str,
    *,
    x: int = 10,
    y: int = 10,
    obs_type: str = "山贼",
    level: int = 1,
    data: dict | None = None,
) -> dict:
    return {
        "targetId": target_id,
        "x": x,
        "y": y,
        "type": obs_type,
        "level": level,
        "data": dict(data or {"name": "观测", "kind": obs_type}),
    }


class FakeExchange:
    """记录式的副本下行/上行传输；按路径弹出预置响应或抛错。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.sync_pages: list[dict] = []
        self.changes_pages: list[dict] = []
        self.fail_paths: set[str] = set()
        self.observation_bodies: list[dict] = []

    def __call__(self, path: str, body: dict) -> dict:
        self.calls.append((path, copy.deepcopy(body)))
        if path in self.fail_paths:
            raise OSError("fixture transport failure")
        if path == "/v1/maps/targets/sync":
            if self.sync_pages:
                return copy.deepcopy(self.sync_pages.pop(0))
            return {"ok": True, "targets": [], "nextCursor": None}
        if path == "/v1/maps/targets/changes":
            if self.changes_pages:
                return copy.deepcopy(self.changes_pages.pop(0))
            return {"ok": True, "targets": [], "cursor": dict(body["since"])}
        if path == "/v1/maps/observations":
            self.observation_bodies.append(copy.deepcopy(body))
            return {"ok": True}
        raise AssertionError(f"unexpected replica path: {path}")


class CloudMapReplicaStoreTests(unittest.TestCase):
    def _store(
        self,
        exchange: FakeExchange,
        clock: MutableClock,
        directory=None,
        map_kind: str = "bandit",
    ) -> CloudMapReplicaStore:
        return CloudMapReplicaStore(
            server_key="server-352",
            map_kind=map_kind,
            replica_id="account-a",
            data_directory=directory,
            exchange=exchange,
            clock=clock.now_millis,
        )

    def test_full_sync_paginates_then_changes_then_local_filter(self) -> None:
        clock = MutableClock()
        exchange = FakeExchange()
        exchange.sync_pages = [
            {
                "ok": True,
                "targets": [
                    cloud_row("0000000000000001", changed=500),
                    cloud_row(
                        "0000000000000002",
                        changed=600,
                        status="reserved",
                        lease_until=clock.value + 3_600_000,
                    ),
                ],
                "nextCursor": {"lastSeenAt": 90, "targetId": "0000000000000002"},
            },
            {
                "ok": True,
                "targets": [
                    cloud_row("0000000000000003", changed=700),
                    cloud_row(
                        "0000000000000004",
                        changed=800,
                        status="rejected",
                        retry_after=clock.value - 1,
                    ),
                ],
                "nextCursor": None,
            },
        ]
        store = self._store(exchange, clock)
        self.assertTrue(store.ensure_fresh())
        sync_calls = [
            body for path, body in exchange.calls
            if path == "/v1/maps/targets/sync"
        ]
        self.assertEqual(len(sync_calls), 2, "必须翻页直到 nextCursor 为空")
        self.assertNotIn("cursor", sync_calls[0])
        self.assertEqual(
            sync_calls[1]["cursor"],
            {"lastSeenAt": 90, "targetId": "0000000000000002"},
        )
        # 本地可用性：available 与过 retry 的 rejected 可选，租约内的
        # reserved 不可选。
        candidates = {
            row["targetId"] for row in store.candidate_targets()
        }
        self.assertEqual(
            candidates, {"0000000000000001", "0000000000000003", "0000000000000004"}
        )

        # 60 秒节流内不拉增量。
        clock.value += CHANGES_MIN_INTERVAL_MILLIS - 1
        self.assertTrue(store.ensure_fresh())
        self.assertEqual(
            [path for path, _ in exchange.calls].count(
                "/v1/maps/targets/changes"
            ),
            0,
        )

        # 越过间隔：增量里的墓碑删除本地行，新行补齐；游标从全量最大值
        # （800）起步，不把全图再拉一遍。
        exchange.changes_pages = [{
            "ok": True,
            "targets": [
                cloud_row(
                    "0000000000000001", changed=900, status="missing"
                ),
                cloud_row("0000000000000005", changed=950),
            ],
            "cursor": {"changedAt": 950, "targetId": "0000000000000005"},
        }]
        clock.value += 2
        self.assertTrue(store.ensure_fresh())
        changes_calls = [
            body for path, body in exchange.calls
            if path == "/v1/maps/targets/changes"
        ]
        self.assertEqual(len(changes_calls), 1)
        self.assertEqual(
            changes_calls[0]["since"],
            {"changedAt": 800, "targetId": "0000000000000004"},
        )
        candidates = {
            row["targetId"] for row in store.candidate_targets()
        }
        self.assertEqual(
            candidates,
            {"0000000000000003", "0000000000000004", "0000000000000005"},
        )

    def test_scan_diff_produces_upserts_and_gone(self) -> None:
        clock = MutableClock()
        exchange = FakeExchange()
        store = self._store(exchange, clock)
        exchange.sync_pages = [{"ok": True, "targets": [], "nextCursor": None}]
        self.assertTrue(store.ensure_fresh())

        # 新目标 → upserts；本地副本立即可选（本地真相立即生效）。
        seen = [
            observation("00000000000000aa"),
            observation("00000000000000bb", x=11),
        ]
        diff = store.apply_scan_observation(1, 1, seen, clock.value)
        self.assertEqual(
            sorted(diff["upserts"]), ["00000000000000aa", "00000000000000bb"]
        )
        self.assertEqual(diff["gone"], [])
        self.assertEqual(
            {row["targetId"] for row in store.candidate_targets()},
            {"00000000000000aa", "00000000000000bb"},
        )
        self.assertTrue(store.flush_uploads())
        self.assertEqual(len(exchange.observation_bodies), 1)
        body = exchange.observation_bodies[0]
        self.assertNotIn("regions", body, "v2 上报不再走 legacy regions")
        self.assertEqual(
            sorted(t["targetId"] for t in body["upserts"]),
            ["00000000000000aa", "00000000000000bb"],
        )

        # 重复信息不发送：同样的观测不再产生事件。
        diff = store.apply_scan_observation(1, 1, seen, clock.value)
        self.assertEqual(diff, {"upserts": [], "gone": []})

        # 字段变化 → 重新 upsert。
        changed = observation("00000000000000aa", data={"name": "变了"})
        diff = store.apply_scan_observation(1, 1, [changed, seen[1]], clock.value)
        self.assertEqual(diff["upserts"], ["00000000000000aa"])

        # 记忆在本格子的目标本次未见 → gone；副本同步删除。
        diff = store.apply_scan_observation(1, 1, [changed], clock.value)
        self.assertEqual(diff["gone"], ["00000000000000bb"])
        self.assertEqual(
            {row["targetId"] for row in store.candidate_targets()},
            {"00000000000000aa"},
        )
        self.assertTrue(store.flush_uploads())
        self.assertEqual(
            exchange.observation_bodies[-1]["gone"], ["00000000000000bb"]
        )

        # 目标被另一个格子也覆盖时，单格未见不算 gone。
        store.apply_scan_observation(2, 2, [changed], clock.value)
        diff = store.apply_scan_observation(1, 1, [], clock.value)
        self.assertEqual(diff["gone"], [])
        diff = store.apply_scan_observation(2, 2, [], clock.value)
        self.assertEqual(diff["gone"], ["00000000000000aa"])

    def test_flush_failure_keeps_queue_for_retry(self) -> None:
        clock = MutableClock()
        exchange = FakeExchange()
        store = self._store(exchange, clock)
        exchange.sync_pages = [{"ok": True, "targets": [], "nextCursor": None}]
        self.assertTrue(store.ensure_fresh())
        store.apply_scan_observation(
            1, 1, [observation("00000000000000cc")], clock.value
        )
        self.assertEqual(store.pending_upload_count, 1)

        exchange.fail_paths.add("/v1/maps/observations")
        self.assertFalse(store.flush_uploads())
        self.assertEqual(
            store.pending_upload_count, 1, "失败必须保留队列下轮重试"
        )

        exchange.fail_paths.clear()
        self.assertTrue(store.flush_uploads())
        self.assertEqual(store.pending_upload_count, 0)
        self.assertEqual(
            exchange.observation_bodies[-1]["upserts"][0]["targetId"],
            "00000000000000cc",
        )

    def test_corrupted_replica_file_rebuilds_with_full_sync(self) -> None:
        clock = MutableClock()
        exchange = FakeExchange()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            exchange.sync_pages = [
                {
                    "ok": True,
                    "targets": [cloud_row("0000000000000001")],
                    "nextCursor": None,
                }
            ]
            store = self._store(exchange, clock, directory=path)
            self.assertTrue(store.ensure_fresh())
            files = list(path.glob("cloud-map-replica-*.json"))
            self.assertEqual(len(files), 1)
            files[0].write_text("{{{{ 损坏的副本", encoding="utf-8")

            # 损坏 → 视为没有副本：重新全量同步而不是带病使用。
            exchange.sync_pages = [
                {
                    "ok": True,
                    "targets": [cloud_row("0000000000000009")],
                    "nextCursor": None,
                }
            ]
            rebuilt = self._store(exchange, clock, directory=path)
            self.assertFalse(rebuilt.full_sync_done)
            self.assertTrue(rebuilt.ensure_fresh())
            self.assertEqual(
                [row["targetId"] for row in rebuilt.candidate_targets()],
                ["0000000000000009"],
            )

    def test_shard_index_is_deterministic_and_complete(self) -> None:
        coordinates = [(x, y) for x, y in zip(range(10), range(10))]
        actors = ["bbb", "aaa", "ccc"]
        shards = [
            shard_coordinates(actor, actors, coordinates)
            for actor in ("aaa", "bbb", "ccc")
        ]
        self.assertEqual(shards[0], [(0, 0), (3, 3), (6, 6), (9, 9)])
        self.assertEqual(shards[1], [(1, 1), (4, 4), (7, 7)])
        self.assertEqual(shards[2], [(2, 2), (5, 5), (8, 8)])
        merged = [c for shard in shards for c in shard or []]
        self.assertEqual(sorted(merged), coordinates, "分片必须不重不漏")
        # 乱序名单结果一致（排序后才取下标）。
        self.assertEqual(
            shard_coordinates("bbb", ["ccc", "bbb", "aaa"], coordinates),
            shards[1],
        )
        # 自己不在名单 / 名单为空 → None，调用方回退扫描租约。
        self.assertIsNone(shard_coordinates("ddd", actors, coordinates))
        self.assertIsNone(shard_coordinates("aaa", [], coordinates))

    def test_ttl_expires_rows_locally(self) -> None:
        clock = MutableClock()
        exchange = FakeExchange()
        exchange.sync_pages = [
            {
                "ok": True,
                "targets": [
                    cloud_row(
                        "0000000000000001",
                        last_seen=clock.value - BANDIT_TARGET_TTL_MILLIS - 1,
                    ),
                    cloud_row(
                        "0000000000000002",
                        last_seen=clock.value - BANDIT_TARGET_TTL_MILLIS + 1,
                    ),
                ],
                "nextCursor": None,
            }
        ]
        store = self._store(exchange, clock)
        self.assertTrue(store.ensure_fresh())
        self.assertEqual(
            [row["targetId"] for row in store.candidate_targets()],
            ["0000000000000002"],
            "bandit 超过 6 小时 TTL 的行必须本地过期",
        )

        mine_exchange = FakeExchange()
        mine_exchange.sync_pages = [
            {
                "ok": True,
                "targets": [
                    cloud_row(
                        "0000000000000003",
                        last_seen=clock.value - MINE_TARGET_TTL_MILLIS - 1,
                    ),
                    cloud_row(
                        "0000000000000004",
                        last_seen=clock.value - MINE_TARGET_TTL_MILLIS + 1,
                    ),
                ],
                "nextCursor": None,
            }
        ]
        mine_store = self._store(mine_exchange, clock, map_kind="mine")
        self.assertTrue(mine_store.ensure_fresh())
        self.assertEqual(
            [row["targetId"] for row in mine_store.candidate_targets()],
            ["0000000000000004"],
            "mine 超过 24 小时 TTL 的行必须本地过期",
        )

    def test_missing_v2_endpoint_falls_back_and_sticks(self) -> None:
        clock = MutableClock()

        class OldWorkerExchange:
            def __init__(self) -> None:
                self.sync_calls = 0

            def __call__(self, path: str, body: dict) -> dict:
                if path == "/v1/maps/targets/sync":
                    self.sync_calls += 1
                    raise RuntimeError("共享地图 HTTP 404")
                raise AssertionError(path)

        old_exchange = OldWorkerExchange()
        store = self._store(old_exchange, clock)  # type: ignore[arg-type]
        self.assertFalse(store.ensure_fresh(), "旧 Worker 没有 v2 端点")
        self.assertTrue(store.legacy)
        self.assertFalse(store.ensure_fresh())
        self.assertEqual(
            old_exchange.sync_calls, 1, "确认 404 后不再每轮重复探测"
        )

    def test_transient_sync_failure_falls_back_only_for_the_round(self) -> None:
        clock = MutableClock()
        exchange = FakeExchange()
        exchange.fail_paths.add("/v1/maps/targets/sync")
        store = self._store(exchange, clock)
        self.assertFalse(store.ensure_fresh())
        self.assertFalse(store.legacy, "瞬时报错不置 legacy，下轮仍重试 v2")
        exchange.fail_paths.clear()
        exchange.sync_pages = [
            {
                "ok": True,
                "targets": [cloud_row("0000000000000001")],
                "nextCursor": None,
            }
        ]
        self.assertTrue(store.ensure_fresh())
        self.assertEqual(len(store.candidate_targets()), 1)


class FakeV2CloudPort:
    """v2 Worker 假实现：sync/changes/v2 observations + 带名单的心跳。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.sync_targets: list[dict] = []

    def configured(self) -> bool:
        return True

    def exchange(self, request):
        value = copy.deepcopy(dict(request))
        self.calls.append(value)
        path = value["path"]
        body = value["body"]
        if path == "/v1/presence/heartbeat":
            return {"status": 200, "body": {
                "ok": True,
                "mode": "CLOUD_SHARED",
                "onlineAccountCount": 2,
                "threshold": 2,
                # "peer-zzz" 字典序在任何 sha256 十六进制之后，所以自己
                # 恒为分片下标 0/2。
                "onlineActorIds": [body["actorId"], "peer-zzz"],
            }}
        if path == "/v1/maps/targets/sync":
            return {"status": 200, "body": {
                "ok": True,
                "targets": copy.deepcopy(self.sync_targets),
                "nextCursor": None,
            }}
        if path == "/v1/maps/targets/changes":
            return {"status": 200, "body": {
                "ok": True,
                "targets": [],
                "cursor": dict(body["since"]),
            }}
        if path == "/v1/maps/observations":
            return {"status": 200, "body": {"ok": True}}
        if path == "/v1/maps/targets/reserve":
            return {"status": 200, "body": {
                "ok": True,
                "reserved": True,
                "reservationToken": "reservation-1",
            }}
        if path == "/v1/maps/targets/status":
            return {"status": 200, "body": {"ok": True, "updated": True}}
        raise AssertionError(f"unexpected cloud path: {path}")


class FakeExecution:
    operation_id = "cloud-map-replica-test"

    def mark_request_sent(self, _metadata=None) -> None:
        return None

    def publish_progress(self, _progress: int, _details=None) -> None:
        return None

    def raise_if_cancelled(self) -> None:
        return None

    def wait(self, _seconds: float) -> None:
        return None


class CloudMapReplicaFacadeTests(unittest.TestCase):
    """facade 接线验证：v2 下目标来自副本、扫描走分片、上报走事件。"""

    def _facade(self, cloud: FakeV2CloudPort):
        directory = tempfile.TemporaryDirectory()
        clock = MutableClock(80_000_000)
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
                    "scanLimit": 6,
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
        return (
            facade,
            directory,
            json.loads(public["residentAutomationConfigJson"]),
            json.loads(public["residentAutomationStateJson"]),
        )

    def test_v2_tick_uses_replica_shard_and_event_upload(self) -> None:
        cloud = FakeV2CloudPort()
        facade, directory, config, state = self._facade(cloud)
        captured: list[dict] = []
        all_coordinates = brush_scan_coordinates(10, 10, 6)
        expected_shard = [list(value) for value in all_coordinates[::2]]

        def scanned(_self, _execution, body, _context):
            captured.append(dict(body))
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
            }
            coordinates = [tuple(value) for value in body["_scanCoordinatesOverride"]]
            return {
                "targets": [target],
                "scanOffset": 0,
                "scanLimit": 6,
                "scanBatchSize": len(coordinates),
                "scannedCount": len(coordinates),
                "nextScanOffset": 0,
                "scanWrapped": True,
                "scannedCoordinates": [list(value) for value in coordinates],
                "scanResults": [
                    {"scanCoord": list(value), "targets": [target]}
                    for value in coordinates
                ],
            }

        def accepted(_self, _execution, body, _context):
            return {"result": {
                "success": True,
                "successBattleId": 9201,
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
            self.assertIn("/v1/maps/targets/sync", paths)
            self.assertNotIn(
                "/v1/maps/targets/query", paths, "v2 不再全图拉取"
            )
            self.assertNotIn(
                "/v1/maps/scans/claim", paths, "v2 不再占用扫描租约"
            )
            # 确定性分片：2 个在线账号、自己是下标 0 → 偶数下标坐标。
            self.assertEqual(
                captured[0]["_scanCoordinatesOverride"], expected_shard
            )
            observations = [
                call["body"] for call in cloud.calls
                if call["path"] == "/v1/maps/observations"
            ]
            self.assertEqual(len(observations), 1)
            body = observations[0]
            self.assertNotIn("regions", body, "v2 上报不再全量 regions")
            self.assertEqual(
                [t["targetId"] for t in body["upserts"]],
                ["0000000000001234"],
            )
            encoded = json.dumps(body, ensure_ascii=False)
            self.assertNotIn("password", encoded)
        finally:
            facade.close()
            directory.cleanup()

    def test_v2_known_replica_target_skips_scan_entirely(self) -> None:
        cloud = FakeV2CloudPort()
        cloud.sync_targets = [{
            "targetId": "0000000000001234",
            "x": 10,
            "y": 10,
            "type": "山贼",
            "level": 1,
            "lastSeenAtMillis": 80_000_000,
            "changedAtMillis": 80_000_000,
            "status": "available",
            "statusAtMillis": 80_000_000,
            "leaseUntilMillis": 0,
            "retryAfterMillis": 0,
            "data": {
                "name": "1级山贼",
                "kind": "山贼",
                "composition": {
                    "foot": 0, "bow": 5, "cavalry": 0, "chariot": 0,
                    "source": "8540-units",
                },
            },
        }]
        facade, directory, config, state = self._facade(cloud)

        def forbidden_scan(*_args, **_kwargs):
            raise AssertionError("副本已有目标，本轮不应触发游戏地图扫描")

        def accepted(_self, _execution, body, _context):
            return {"result": {
                "success": True,
                "successBattleId": 9202,
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
            self.assertEqual(paths, [
                "/v1/presence/heartbeat",
                "/v1/maps/targets/sync",
                "/v1/maps/targets/reserve",
                "/v1/maps/targets/status",
                "/v1/maps/targets/status",
            ])
        finally:
            facade.close()
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
