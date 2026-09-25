"""云端共享地图 v2：本地副本 + 事件驱动上报。

规格见 docs/core_migration/cloud_event_sync_v2_spec.md。v1 是"状态镜像"：
每批扫描全量上报、每次找目标全图拉取。v2 改为客户端持有视野内目标的完整
副本（targets）+ 自己上传过的目标记忆（uploadMemory），找目标/筛选全部
本地完成；写入只发生在真实事件上——比对出新目标或字段变化发 upserts，
扫描覆盖到的格子里记忆的目标消失发 gone。核心不变量：新信息不延迟、不少
一条；重复信息不发送、不重写。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

#: 与服务端 TTL 对齐（规格：bandit 30 分钟 → 6 小时，mine 3 小时 → 24 小时）。
#: 本地过期只是垃圾回收；目标死亡以显式 gone 上报为准。
BANDIT_TARGET_TTL_MILLIS = 6 * 60 * 60 * 1000
MINE_TARGET_TTL_MILLIS = 24 * 60 * 60 * 1000

#: 变化订阅最小拉取间隔：规格约定客户端每分钟最多拉一次增量。
CHANGES_MIN_INTERVAL_MILLIS = 60_000

#: sync/changes 单页上限，与 Worker 端一致。
SYNC_PAGE_LIMIT = 500

#: v2 observations 单请求 upserts/gone 上限，与 Worker 端一致。
UPLOAD_BATCH_LIMIT = 200

#: 兼容已部署的旧 Worker：gone 的 UPDATE 有 4 个固定参数，D1 上限 100。
#: 即使新 Worker 已改为 json_each，旧端也必须能推进，不能等服务端升级。
UPLOAD_GONE_BATCH_LIMIT = 96

#: 上报失败只延后队列，不阻塞本地读/其他任务，也不在高频 tick 中重试风暴。
UPLOAD_RETRY_INTERVAL_MILLIS = 15_000

# A refused cached candidate is not supply. Keep its observation/outbox, but
# take it out of the hot pool while other targets can be discovered.
CANDIDATE_REFUSAL_RETRY_MILLIS = 60_000

#: 视野半径在配置距离外的冗余格数（规格：max(配置距离) + 20 格方形）。
VIEW_RADIUS_PADDING = 20

#: changes 一次 ensure_fresh 最多翻页数，防御服务端游标不前进造成的死循环。
_CHANGES_MAX_PAGES = 20


def shard_coordinates(
    actor_id: str,
    online_actor_ids: List[str],
    coordinates: List[Tuple[int, int]],
) -> Optional[List[Tuple[int, int]]]:
    """在线账号确定性分片：名单排序后取自己下标 i，坐标按 index % N == i 过滤。

    拿不到名单、或自己不在名单内（旧 Worker 的心跳没有 onlineActorIds）时
    返回 None，由调用方回退到 v1 的扫描租约（claim/release）逻辑。
    """

    ids = sorted({
        str(value).strip()
        for value in online_actor_ids or []
        if str(value or "").strip()
    })
    actor = str(actor_id or "").strip()
    if not ids or actor not in ids:
        return None
    index = ids.index(actor)
    count = len(ids)
    return [
        coordinate
        for position, coordinate in enumerate(coordinates)
        if position % count == index
    ]


class CloudMapReplicaStore:
    """每 账号×区服×地图类型 一份的云端目标本地副本。

    exchange 是宿主注入的云端请求原语（路径 + JSON body → 已校验 ok 的
    payload，失败抛异常）；clock 返回毫秒；data_directory 为空时副本只活
    在内存里（进程重启后全量重同步，语义不变）。
    """

    def __init__(
        self,
        *,
        server_key: str,
        map_kind: str,
        replica_id: str = "",
        data_directory: Optional[Path] = None,
        exchange: Callable[[str, Dict[str, Any]], Dict[str, Any]],
        clock: Callable[[], int],
        logger: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._server_key = str(server_key)
        self._map_kind = str(map_kind)
        self._replica_id = str(replica_id or "")
        self._exchange = exchange
        self._clock = clock
        self._logger = logger
        self._lock = threading.RLock()
        self._file_path: Optional[Path] = None
        if data_directory is not None:
            name_parts = ["cloud-map-replica"]
            if self._replica_id:
                name_parts.append(self._replica_id)
            name_parts.extend([self._server_key, self._map_kind])
            filename = "-".join(
                re.sub(r"[^0-9A-Za-z_.-]+", "_", part) for part in name_parts
            )
            self._file_path = Path(data_directory) / f"{filename}.json"
        self._reset_state()
        self._load()

    # ------------------------------------------------------------------
    # 状态与持久化
    # ------------------------------------------------------------------

    def _reset_state(self) -> None:
        # 副本行保持云端行形状（targetId/x/y/type/level/lastSeenAtMillis/
        # changedAtMillis/status/statusAtMillis/leaseUntilMillis/
        # retryAfterMillis/data）。观测库存不等于本轮派遣资格。
        self._targets: Dict[str, Dict[str, Any]] = {}
        # 自己上传过的目标记忆：{targetId: {"row": 观测行, "cells": [[x, y]...]}}
        self._upload_memory: Dict[str, Dict[str, Any]] = {}
        self._sync_cursor: Optional[Dict[str, Any]] = None
        self._changes_cursor: Dict[str, Any] = {"changedAt": 0, "targetId": ""}
        self._full_sync_done = False
        self._last_changes_fetch_at = 0
        # v2 端点确定不存在（4xx）时置位，停止每轮探测；瞬时报错只在当轮
        # 回退（ensure_fresh 返回 False），下一轮仍按规格重试。
        self._legacy = False
        self._view: Optional[Dict[str, int]] = None
        self._pending_upserts: Dict[str, Dict[str, Any]] = {}
        self._pending_gone: Dict[str, bool] = {}
        self._next_upload_retry_at = 0
        self._candidate_blocks: Dict[str, Dict[str, Any]] = {}
        # Preserve superseded availability uploads as held facts, not fake ACKs.
        self._local_consumed: Dict[str, Dict[str, int]] = {}
        self._next_refresh_retry_at = 0

    def _log(self, level: str, message: str) -> None:
        if self._logger is None:
            return
        try:
            self._logger(level, message)
        except Exception:
            pass

    def _load(self) -> None:
        if self._file_path is None or not self._file_path.exists():
            return
        try:
            raw = json.loads(self._file_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("副本文件根节点不是对象")
            targets = raw.get("targets")
            upload_memory = raw.get("uploadMemory")
            self._targets = {
                str(key): dict(value)
                for key, value in dict(targets or {}).items()
                if isinstance(value, dict)
            }
            self._upload_memory = {
                str(key): {
                    "row": dict(value.get("row") or {}),
                    "cells": [
                        [int(cell[0]), int(cell[1])]
                        for cell in value.get("cells") or []
                        if isinstance(cell, (list, tuple)) and len(cell) >= 2
                    ],
                }
                for key, value in dict(upload_memory or {}).items()
                if isinstance(value, dict)
            }
            sync_cursor = raw.get("syncCursor")
            self._sync_cursor = (
                dict(sync_cursor) if isinstance(sync_cursor, dict) else None
            )
            changes_cursor = raw.get("changesCursor")
            self._changes_cursor = (
                dict(changes_cursor)
                if isinstance(changes_cursor, dict)
                else {"changedAt": 0, "targetId": ""}
            )
            self._full_sync_done = raw.get("fullSyncDone") is True
            self._last_changes_fetch_at = int(
                raw.get("lastChangesFetchAt") or 0
            )
            self._legacy = raw.get("legacy") is True
            view = raw.get("view")
            self._view = dict(view) if isinstance(view, dict) else None
            self._pending_upserts = {
                str(key): dict(value)
                for key, value in dict(
                    raw.get("pendingUpserts") or {}
                ).items()
                if isinstance(value, dict)
            }
            self._pending_gone = {
                str(key): True for key in dict(raw.get("pendingGone") or {})
            }
            self._candidate_blocks = {
                str(key): dict(value)
                for key, value in dict(raw.get("candidateBlocks") or {}).items()
                if isinstance(value, dict)
            }
            self._local_consumed = {
                str(key): {str(k): int(v) for k, v in value.items()}
                for key, value in dict(raw.get("localConsumed") or {}).items()
                if isinstance(value, dict)
            }
        except Exception as error:
            # 损坏的副本不能带病使用：清空后下次 ensure_fresh 全量重同步。
            self._log("warn", f"云端地图副本文件损坏，已重建：{error}")
            self._reset_state()

    def _save(self) -> None:
        if self._file_path is None:
            return
        payload = {
            "targets": self._targets,
            "uploadMemory": self._upload_memory,
            "syncCursor": self._sync_cursor,
            "changesCursor": self._changes_cursor,
            "fullSyncDone": self._full_sync_done,
            "lastChangesFetchAt": self._last_changes_fetch_at,
            "legacy": self._legacy,
            "view": self._view,
            "pendingUpserts": self._pending_upserts,
            "pendingGone": self._pending_gone,
            "candidateBlocks": self._candidate_blocks,
            "localConsumed": self._local_consumed,
            "updatedAtMillis": int(self._clock()),
        }
        temporary_path = None
        try:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self._file_path.parent,
                prefix=self._file_path.name + ".", suffix=".tmp", delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(payload, temporary, ensure_ascii=False)
            os.replace(temporary_path, self._file_path)
        except Exception as error:
            # Dispatch safety still lives in the durable expedition ledger.
            self._log("warn", f"云端地图副本写入失败：{error}")
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # 只读属性
    # ------------------------------------------------------------------

    @property
    def legacy(self) -> bool:
        return self._legacy

    @property
    def full_sync_done(self) -> bool:
        return self._full_sync_done

    @property
    def ttl_millis(self) -> int:
        if self._map_kind == "bandit":
            return BANDIT_TARGET_TTL_MILLIS
        return MINE_TARGET_TTL_MILLIS

    @property
    def pending_upload_count(self) -> int:
        return len(self._pending_upserts) + len(self._pending_gone)

    def upload_pending(self, target_id: str) -> bool:
        with self._lock:
            return str(target_id).strip().lower() in self._pending_upserts

    def set_view(
        self,
        center_x: int,
        center_y: int,
        radius: int,
    ) -> None:
        """设置视野（主城为中心、radius 为半径的方形）；取不到时不调用。

        视野变化意味着当前副本可能缺新区域的行：保留已有行（对候选筛选
        无害），但重置全量游标让下一轮 ensure_fresh 重新分页补齐。
        """

        view = {
            "centerX": int(center_x),
            "centerY": int(center_y),
            "radius": max(0, int(radius)),
        }
        with self._lock:
            if view == self._view:
                return
            self._view = view
            self._full_sync_done = False
            self._sync_cursor = None
            self._changes_cursor = {"changedAt": 0, "targetId": ""}
            self._save()

    def _view_bounds(self) -> Dict[str, int]:
        if self._view is None:
            return {}
        radius = int(self._view["radius"])
        return {
            "minX": int(self._view["centerX"]) - radius,
            "maxX": int(self._view["centerX"]) + radius,
            "minY": int(self._view["centerY"]) - radius,
            "maxY": int(self._view["centerY"]) + radius,
        }

    # ------------------------------------------------------------------
    # 下行：全量同步 + 变化订阅
    # ------------------------------------------------------------------

    def _apply_row(
        self,
        targets: Dict[str, Dict[str, Any]],
        row: Dict[str, Any],
    ) -> None:
        target_id = str(row.get("targetId") or "").strip().lower()
        if not target_id:
            return
        block = self._candidate_blocks.get(target_id)
        if (
            block and block.get("reason") == "unknown-target"
            and int(row.get("changedAtMillis") or 0)
            > int(block.get("cloudRevision") or 0)
        ):
            # A newer cloud revision proves the row exists there. An old
            # available row replayed by sync is not such evidence.
            block["publicationConfirmed"] = True
        # status='missing' 的墓碑行是死亡传播的唯一通道：本地立即删除。
        if str(row.get("status") or "") == "missing":
            targets.pop(target_id, None)
            return
        data = row.get("data")
        targets[target_id] = {
            "targetId": target_id,
            "x": int(row.get("x") or 0),
            "y": int(row.get("y") or 0),
            "type": str(row.get("type") or ""),
            "level": row.get("level"),
            "lastSeenAtMillis": int(row.get("lastSeenAtMillis") or 0),
            "changedAtMillis": int(row.get("changedAtMillis") or 0),
            "status": str(row.get("status") or "available"),
            "statusAtMillis": int(row.get("statusAtMillis") or 0),
            "leaseUntilMillis": int(row.get("leaseUntilMillis") or 0),
            "retryAfterMillis": int(row.get("retryAfterMillis") or 0),
            "data": dict(data) if isinstance(data, dict) else {},
        }

    @staticmethod
    def _looks_like_missing_endpoint(error: Exception) -> bool:
        return re.search(r"HTTP 4\d\d", str(error)) is not None

    def _full_sync(self) -> None:
        max_changed_at = int(self._changes_cursor.get("changedAt") or 0)
        max_changed_id = str(self._changes_cursor.get("targetId") or "")
        while True:
            body: Dict[str, Any] = {
                "mapKind": self._map_kind,
                "limit": SYNC_PAGE_LIMIT,
                **self._view_bounds(),
            }
            if self._sync_cursor is not None:
                body["cursor"] = dict(self._sync_cursor)
            payload = self._exchange("/v1/maps/targets/sync", body)
            rows = [
                dict(row)
                for row in payload.get("targets") or []
                if isinstance(row, dict)
            ]
            for row in rows:
                changed_at = int(row.get("changedAtMillis") or 0)
                target_id = str(row.get("targetId") or "")
                if (changed_at, target_id) > (max_changed_at, max_changed_id):
                    max_changed_at, max_changed_id = changed_at, target_id
                self._apply_row(self._targets, row)
            next_cursor = payload.get("nextCursor")
            if not isinstance(next_cursor, dict):
                break
            self._sync_cursor = dict(next_cursor)
        self._full_sync_done = True
        self._sync_cursor = None
        # 全量已覆盖 changedAt <= 最大值的全部行，增量游标直接从这里起步，
        # 避免首轮 changes 把全图再拉一遍；同值更大 targetId 的行即使重发
        # 也是幂等应用。
        self._changes_cursor = {
            "changedAt": max_changed_at,
            "targetId": max_changed_id,
        }
        self._last_changes_fetch_at = int(self._clock())

    def _fetch_changes(self) -> None:
        for _ in range(_CHANGES_MAX_PAGES):
            payload = self._exchange(
                "/v1/maps/targets/changes",
                {
                    "mapKind": self._map_kind,
                    "since": dict(self._changes_cursor),
                    "limit": SYNC_PAGE_LIMIT,
                    **self._view_bounds(),
                },
            )
            rows = [
                dict(row)
                for row in payload.get("targets") or []
                if isinstance(row, dict)
            ]
            for row in rows:
                self._apply_row(self._targets, row)
            cursor = payload.get("cursor")
            if isinstance(cursor, dict):
                self._changes_cursor = dict(cursor)
            if len(rows) < SYNC_PAGE_LIMIT:
                break

    def _expire_stale(self, now: int) -> None:
        ttl = self.ttl_millis
        for target_id in list(self._targets):
            row = self._targets[target_id]
            last_seen = int(row.get("lastSeenAtMillis") or 0)
            if last_seen > 0 and now - last_seen > ttl:
                del self._targets[target_id]
        for target_id, block in list(self._candidate_blocks.items()):
            if now - int(block.get("blockedAtMillis") or 0) > ttl:
                del self._candidate_blocks[target_id]
        for target_id, fact in list(self._local_consumed.items()):
            if now - int(fact["atMillis"]) > ttl and target_id not in self._pending_upserts:
                del self._local_consumed[target_id]

    def ensure_fresh(self, now: Optional[int] = None) -> bool:
        """保证副本可用于本地筛选：未全量则分页拉全量，否则按节奏拉增量。

        返回 False 表示本轮不可用（旧 Worker 没有 v2 端点、或全量同步
        失败），调用方应回退 v1 全量查询；已完成全量的副本遇到增量拉取
        瞬时失败时仍返回 True（陈旧但可用，下轮再补）。
        """

        with self._lock:
            if self._legacy:
                return False
            now_millis = int(self._clock() if now is None else now)
            if not self._full_sync_done:
                if now_millis < self._next_refresh_retry_at:
                    return False
                try:
                    self._full_sync()
                    self._next_refresh_retry_at = 0
                except Exception as error:
                    self._next_refresh_retry_at = now_millis + UPLOAD_RETRY_INTERVAL_MILLIS
                    if self._looks_like_missing_endpoint(error):
                        self._legacy = True
                    self._log(
                        "warn",
                        f"云端地图 v2 全量同步失败，本轮回退 v1：{error}",
                    )
                    self._save()
                    return False
            elif (
                now_millis - self._last_changes_fetch_at
                > CHANGES_MIN_INTERVAL_MILLIS
                and now_millis >= self._next_refresh_retry_at
            ):
                try:
                    self._fetch_changes()
                    self._last_changes_fetch_at = now_millis
                    self._next_refresh_retry_at = 0
                except Exception as error:
                    self._next_refresh_retry_at = now_millis + UPLOAD_RETRY_INTERVAL_MILLIS
                    if self._looks_like_missing_endpoint(error):
                        self._legacy = True
                        self._log(
                            "warn",
                            f"云端地图 v2 变化订阅失败，回退 v1：{error}",
                        )
                        self._save()
                        return False
                    self._log(
                        "warn",
                        f"云端地图增量拉取失败，本轮沿用旧副本：{error}",
                    )
            # A local candidate can suppress further game scans even though
            # its upload never reached the cloud. Drain one bounded batch on
            # ordinary reads too; otherwise a failed scan upload can deadlock
            # every subsequent reservation indefinitely.
            self.flush_uploads()
            self._expire_stale(now_millis)
            self._save()
            return True

    # ------------------------------------------------------------------
    # 上行：扫描比对 + 事件上报
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_observation(
        target: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        target_id = str(target.get("targetId") or "").strip().lower()
        if not target_id:
            return None
        data = target.get("data")
        return {
            "targetId": target_id,
            "x": int(target.get("x") or 0),
            "y": int(target.get("y") or 0),
            "type": str(target.get("type") or ""),
            "level": target.get("level"),
            "data": dict(data) if isinstance(data, dict) else {},
        }

    def apply_scan_observation(
        self,
        region_x: int,
        region_y: int,
        seen_targets: List[Dict[str, Any]],
        now: Optional[int] = None,
        *,
        protected_target_ids: Optional[set[str]] = None,
    ) -> Dict[str, List[str]]:
        """把一次格子扫描与上传记忆比对，产出 upserts/gone 待发事件。

        新目标或字段变化进 upserts 队列并更新记忆；记忆里属于本格子的
        目标本次未见、且没有其他格子记录时进 gone 队列。副本 targets
        同步更新——本地真相立即生效，不等服务端回包。
        """

        with self._lock:
            now_millis = int(self._clock() if now is None else now)
            cell = [int(region_x), int(region_y)]
            seen_ids = set()
            upserted: List[str] = []
            for raw_target in seen_targets or []:
                if not isinstance(raw_target, dict):
                    continue
                observation = self._normalize_observation(raw_target)
                if observation is None:
                    continue
                target_id = observation["targetId"]
                seen_ids.add(target_id)
                consumed = self._local_consumed.get(target_id)
                revived_consumed = bool(
                    consumed
                    and now_millis > consumed["atMillis"]
                    and target_id not in (protected_target_ids or set())
                    and int(consumed.get("observedAfterMillis") or 0) <= consumed["atMillis"]
                )
                if revived_consumed:
                    consumed["observedAfterMillis"] = now_millis
                block = self._candidate_blocks.get(target_id)
                if (
                    block and block.get("reason") in {"dispatched", "missing"}
                    and now_millis > int(block.get("blockedAtMillis") or 0)
                    and target_id not in (protected_target_ids or set())
                ):
                    # Only a fresh game observation after ownership ended can
                    # revive a consumed target; cloud/cache replay cannot.
                    del self._candidate_blocks[target_id]
                # The newest sighting supersedes an unsent disappearance.
                # Sending both would upsert, then immediately tombstone it.
                self._pending_gone.pop(target_id, None)
                memory = self._upload_memory.get(target_id)
                if memory is None:
                    self._upload_memory[target_id] = {
                        "row": dict(observation),
                        "cells": [list(cell)],
                    }
                    self._pending_upserts[target_id] = dict(observation)
                    upserted.append(target_id)
                else:
                    if memory["row"] != observation or revived_consumed:
                        memory["row"] = dict(observation)
                        self._pending_upserts[target_id] = dict(observation)
                        upserted.append(target_id)
                    if cell not in memory["cells"]:
                        memory["cells"].append(list(cell))
                # A sighting is not a lease release. Match the server's upsert:
                # it preserves active reservations/dispatches/rejections.
                previous = self._targets.get(target_id) or {}
                previous_status = str(previous.get("status") or "available")
                revive = previous_status == "missing" or (
                    previous_status == "uncertain"
                    and int(previous.get("leaseUntilMillis") or 0) <= now_millis
                )
                status = "available" if revive else previous_status
                self._targets[target_id] = {
                    **observation,
                    "lastSeenAtMillis": now_millis,
                    # Keep the last *cloud* revision separate from local time.
                    "changedAtMillis": int(previous.get("changedAtMillis") or 0),
                    "status": status,
                    "statusAtMillis": int(previous.get("statusAtMillis") or now_millis),
                    "leaseUntilMillis": 0 if revive else int(previous.get("leaseUntilMillis") or 0),
                    "retryAfterMillis": 0 if revive else int(previous.get("retryAfterMillis") or 0),
                }
            gone: List[str] = []
            for target_id in list(self._upload_memory):
                memory = self._upload_memory[target_id]
                if cell not in memory["cells"] or target_id in seen_ids:
                    continue
                memory["cells"] = [
                    value for value in memory["cells"] if value != cell
                ]
                if memory["cells"]:
                    continue
                del self._upload_memory[target_id]
                self._pending_upserts.pop(target_id, None)
                self._pending_gone[target_id] = True
                self._targets.pop(target_id, None)
                gone.append(target_id)
            self._save()
            return {"upserts": upserted, "gone": gone}

    def record_consumed_targets(self, targets: Dict[str, int]) -> None:
        """Reconcile durable game receipts, including after a crash/restart.

        Dispatch accepted does not prove a target died. Hold its older upsert
        rather than inventing a gone event; only a new unowned game observation
        may supersede consumption. Cloud replay/healthy heartbeat cannot do so.
        """
        with self._lock:
            changed = False
            for target_id, at in targets.items():
                at = int(at)
                if int((self._local_consumed.get(target_id) or {}).get("atMillis") or 0) >= at:
                    continue
                self._local_consumed[target_id] = {"atMillis": at}
                row = self._targets.get(target_id) or {}
                self._candidate_blocks[target_id] = {
                    "reason": "dispatched", "blockedAtMillis": at,
                    "retryAtMillis": at + self.ttl_millis,
                    "cloudRevision": int(row.get("changedAtMillis") or 0),
                    "publicationConfirmed": False,
                }
                changed = True
            if changed:
                self._save()

    def requeue_upload(self, target_id: str) -> bool:
        """云端不认识这个目标时，把副本行重新排队上报。

        保留这条历史观测，不把补报排队误当作目标仍活着或云端已确认。
        派遣资格另由 candidate_blocks 控制。返回 False 表示副本也没有记录。
        """

        with self._lock:
            row = self._targets.get(str(target_id).strip().lower())
            if row is None:
                return False
            observation = self._normalize_observation(row)
            if observation is None:
                return False
            self._pending_upserts[observation["targetId"]] = observation
            self._save()
            return True

    def flush_uploads(self) -> bool:
        """最多发送一批 v2 事件；成功才清该批，积压留给后续读/扫描推进。

        失败保留队列并限频重试，返回 False、不抛异常。True 仅表示本批
        成功（或无待发事件），不能当作整个队列/某个指定目标已经上报。
        """

        with self._lock:
            if not self._pending_upserts and not self._pending_gone:
                return True
            now_millis = int(self._clock())
            if now_millis < self._next_upload_retry_at:
                return False
            upserts = [
                row for target_id, row in self._pending_upserts.items()
                if target_id not in self._local_consumed
                or int(self._local_consumed[target_id].get("observedAfterMillis") or 0)
                > self._local_consumed[target_id]["atMillis"]
            ][:UPLOAD_BATCH_LIMIT]
            gone = list(self._pending_gone)[:UPLOAD_GONE_BATCH_LIMIT]
            if not upserts and not gone:
                return False  # Held observations are neither sent nor acknowledged.
            pending_before = self.pending_upload_count
            body: Dict[str, Any] = {"mapKind": self._map_kind}
            if upserts:
                body["upserts"] = upserts
            if gone:
                body["gone"] = gone
            try:
                self._exchange("/v1/maps/observations", body)
            except Exception as error:
                self._next_upload_retry_at = (
                    now_millis + UPLOAD_RETRY_INTERVAL_MILLIS
                )
                self._log(
                    "warn",
                    "云端地图事件上报失败，队列保留并限频重试"
                    f"（目标{len(self._pending_upserts)}条、"
                    f"消失{len(self._pending_gone)}条）：{error}",
                )
                return False
            recovered = self._next_upload_retry_at > 0
            self._next_upload_retry_at = 0
            for observation in upserts:
                target_id = observation["targetId"]
                self._pending_upserts.pop(target_id, None)
                block = self._candidate_blocks.get(target_id)
                if block and block.get("reason") == "unknown-target":
                    # Only acknowledgement of THIS batch/target is evidence.
                    block["publicationConfirmed"] = True
            for target_id in gone:
                self._pending_gone.pop(target_id, None)
            self._save()
            if recovered or pending_before > len(upserts) + len(gone):
                self._log(
                    "info",
                    f"云端地图待发队列已推进：上报目标{len(upserts)}条、"
                    f"消失{len(gone)}条，剩余{self.pending_upload_count}条",
                )
            return True

    # ------------------------------------------------------------------
    # 本地候选筛选
    # ------------------------------------------------------------------

    def defer_candidate(
        self, target_id: str, reason: str, *, retry_at_millis: int = 0,
    ) -> None:
        """Durable eligibility overlay; never discard observations or events."""
        target_id = str(target_id).strip().lower()
        if not target_id:
            return
        with self._lock:
            now = int(self._clock())
            row = self._targets.get(target_id) or {}
            self._candidate_blocks[target_id] = {
                "reason": str(reason),
                "blockedAtMillis": now,
                "retryAtMillis": max(
                    now + CANDIDATE_REFUSAL_RETRY_MILLIS,
                    int(retry_at_millis),
                ),
                "cloudRevision": int(row.get("changedAtMillis") or 0),
                "publicationConfirmed": False,
            }
            self._save()

    def candidate_eligible(self, target_id: str, now: Optional[int] = None) -> bool:
        """Also gates legacy queries and raw scans, not just replica reads."""
        with self._lock:
            now_millis = int(self._clock() if now is None else now)
            block = self._candidate_blocks.get(str(target_id).strip().lower())
            if not block:
                return True
            if now_millis - int(block.get("blockedAtMillis") or 0) > self.ttl_millis:
                return True
            if block.get("reason") in {"dispatched", "missing"}:
                return False
            if now_millis < int(block.get("retryAtMillis") or 0):
                return False
            return (
                block.get("reason") != "unknown-target"
                or block.get("publicationConfirmed") is True
            )

    def offline_peer_blocks(self) -> set[str]:
        """Keep already-known peer leases even while new coordination is down."""
        with self._lock:
            now = int(self._clock())
            return {
                target_id for target_id, row in self._targets.items()
                if row.get("status") in {"reserved", "dispatching", "uncertain"}
                and int(row.get("leaseUntilMillis") or 0) > now
            } | {
                target_id for target_id, block in self._candidate_blocks.items()
                if block.get("reason") == "unavailable"
                and int(block.get("retryAtMillis") or 0) > now
            }

    def candidate_targets(
        self,
        now: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """副本内本地可用的目标行（保持云端行形状，由调用方转换/过滤）。

        可用 = status available、租约已过期的 reserved/dispatching/
        uncertain、已过 retryAfterMillis 的 rejected，且未过 TTL。
        """

        with self._lock:
            now_millis = int(self._clock() if now is None else now)
            ttl = self.ttl_millis
            result: List[Dict[str, Any]] = []
            for row in self._targets.values():
                if not self.candidate_eligible(str(row["targetId"]), now_millis):
                    continue
                last_seen = int(row.get("lastSeenAtMillis") or 0)
                if last_seen > 0 and now_millis - last_seen > ttl:
                    continue
                status = str(row.get("status") or "available")
                if status == "available":
                    pass
                elif status in {"reserved", "dispatching", "uncertain"}:
                    if int(row.get("leaseUntilMillis") or 0) > now_millis:
                        continue
                elif status == "rejected":
                    if int(row.get("retryAfterMillis") or 0) > now_millis:
                        continue
                else:
                    # missing 墓碑已在写入时删除，其余未知状态不可选。
                    continue
                result.append(dict(row))
            return result
