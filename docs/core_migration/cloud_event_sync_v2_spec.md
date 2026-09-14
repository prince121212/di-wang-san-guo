# 云端共享地图事件驱动同步 v2 规格

## 背景与目标

现状（v1，"状态镜像"）：客户端每批扫描把所见目标全量上报、服务端全行重写；每次找目标全图拉取 ≤500 行本地过滤；心跳每 20 秒一次且每次顺带写 server_catalog/server_directory。实测 2-3 个号一天写入 12.6 万行（免费额度 10 万/天）。

v2 目标：稳态（地图无变化）云端读写趋近于零；写入只发生在真实事件上。免费额度容量目标 ≥100 个号。

核心不变量：**新信息不延迟、不少一条；重复信息不发送、不重写。**

## 关键设计决策

1. **取消逐目标存活确认（alive refresh）**。这是 v2 与初版方案的最大差异：算账后发现 alive 确认会成为新的写入大头（目标数 × 96 次/天）。改为：
   - 目标死亡靠**显式 gone 上报**（扫描覆盖到该格子而目标不在 → 立即上报）；
   - 击杀者客户端在战斗确认后立即上报 gone；
   - 长期 TTL 只做垃圾回收（被放弃的数据）：bandit 30 分钟 → **6 小时**，mine 3 小时 → **24 小时**。
   - 残存风险：某目标的所有观察者都下线且无人击杀上报时，目标最长滞留到新 TTL。可被 reserve 成功但行军扑空。可接受：活跃账号持续扫描自己分片，被杀目标分钟内被上报；无人覆盖的格子通常也无人查询。
2. **本地副本**：客户端持有订阅范围（视野）内目标的完整副本 + 自己上传过的目标记忆，找目标/筛选全部本地完成。
3. **变化订阅**：`changed_at` 游标驱动，客户端每分钟最多拉一次增量。
4. **扫描协调下云端**：删掉客户端对扫描租约的依赖，改为按在线账号列表确定性分片。服务端 claim/release 端点保留不动（旧 APK 兼容），新客户端不再调用。
5. **上传 = 我看到的全部（为团队）；下载 = 我视野范围内（为自己）**。

## Worker 端（cloud-shared-data）

### 迁移 0005_changed_at.sql

```sql
ALTER TABLE map_targets ADD COLUMN changed_at INTEGER NOT NULL DEFAULT 0;
UPDATE map_targets SET changed_at = MAX(last_seen_at, COALESCE(status_at, 0));
CREATE INDEX IF NOT EXISTS idx_map_targets_changed
    ON map_targets(server_key, map_kind, changed_at, target_id);
```

### changed_at 维护规则（所有写路径）

- observations upsert（v1 legacy 与 v2 upserts）：`changed_at = now`（仅在实际写入行时）。
- v2 gone：`status='missing', status_at=now, changed_at=now`（不再硬删除；保留 tombstone 让变化源传播）。
- reserveTarget / target status 更新 / cron 的 dispatching→uncertain：都加 `changed_at=now`。
- TTL 删除（cleanup）不变：物理删除 tombstone 与过期行。

### 新端点 1：`POST /v1/maps/targets/sync`（分页全量同步）

请求：common 字段 + `mapKind` + 可选 `minX,maxX,minY,maxY`（整数，视野过滤）+ 可选 `cursor: {lastSeenAt, targetId}` + 可选 `limit`（默认 500，上限 500）。
行为：
- `WHERE server_key=? AND map_kind=? AND last_seen_at>=now-TTL`；有视野参数时加 `x BETWEEN ? AND ? AND y BETWEEN ? AND ?`；有 cursor 时加 `(last_seen_at < ? OR (last_seen_at = ? AND target_id > ?))`。
- `ORDER BY last_seen_at DESC, target_id ASC LIMIT ?`。
响应：`{ok, mode...(requireSharedMode 展开), targets:[行], nextCursor:{lastSeenAt,targetId}|null, serverTimeMillis}`。返回行数 < limit 时 nextCursor=null。
行形状（sync/changes/query 共用）：
```json
{"targetId","x","y","type","level","lastSeenAtMillis","changedAtMillis",
 "status","statusAtMillis","leaseUntilMillis","retryAfterMillis","data":{}}
```

### 新端点 2：`POST /v1/maps/targets/changes`（变化订阅）

请求：common + `mapKind` + `since: {changedAt, targetId}`（游标，首参 `{changedAt:0,targetId:""}`）+ 可选视野参数 + `limit`（默认 500）。
行为：`WHERE server_key=? AND map_kind=? AND (changed_at > ? OR (changed_at = ? AND target_id > ?))` + 视野过滤，`ORDER BY changed_at ASC, target_id ASC LIMIT ?`。
响应：`{ok, targets:[行], cursor:{changedAt,targetId}, serverTimeMillis}`。无变化时 targets 为空、cursor 回显入参。客户端把整个 cursor 当不透明值存储。
注意：status='missing' 的行必须包含在结果里（这是死亡传播的唯一通道）。

### 端点 3 扩展：`POST /v1/maps/observations` 增加 v2 字段

请求在 legacy `regions` 之外允许：`upserts: [target]`（≤200）、`gone: [targetId]`（≤200）。两者都没有时走 legacy 路径（现有行为不动）。
- `upserts`：目标对象形状同 v1 regions 内嵌 target（targetId/x/y/type/level/data）。INSERT ... ON CONFLICT(server_key,map_kind,target_id) DO UPDATE 全字段 + `last_seen_at=now, changed_at=now` + status 恢复逻辑（同现有：missing→available、过期 uncertain→available、清租约）。**不做** 5 分钟节流——客户端保证只送真实变化。同时维护 map_target_regions 链接？不需要：v2 的链接只用于 legacy 孤儿清理；v2 gone 是显式的。若 upserts 附带 `{regionX, regionY}` 可选字段则写链接，否则不写。简化：v2 不写 map_target_regions。
- `gone`：`UPDATE map_targets SET status='missing', status_at=?, changed_at=? WHERE server_key=? AND map_kind=? AND target_id IN (...) AND status NOT IN ('reserved','dispatching')`；并 `DELETE FROM map_target_regions WHERE ... target_id IN (...)`。
- legacy 路径里的孤儿硬删除保留（旧客户端行为不变）。

### 心跳：`POST /v1/presence/heartbeat` 修改

- presence upsert 加条件：`WHERE presence.last_seen_at < ?`（阈值 now-90s）——20 秒一次的心跳不再每次都写。
- **server_catalog / server_directory 的 upsert 从心跳里移除**（每次心跳 3 行写入变 1 行且条件化）。区服目录改由客户端在"首次进入该区/目录信息变化"时调一个已有的或新的轻量端点上报（客户端已有目录同步逻辑 `cloud_directory_sync`，确认它走 `/v1/servers/...` 而非心跳；心跳里的目录写入本来就是冗余兜底）。
- 响应增加 `onlineActorIds: [actorId...]`（presence 表内 TTL 内的 actor_id 列表，含自己）——分片依据。匿名哈希，无隐私问题。
- `PRESENCE_TTL_MILLIS` 默认 90000 → 300000（wrangler.jsonc），因为写入间隔放松了。

### TTL 常量

`database.ts`：`BANDIT_TARGET_TTL_MILLIS = 6*60*60*1000`，`MINE_TARGET_TTL_MILLIS = 24*60*60*1000`。`index.ts` queryTargets 里的 `targetTtl` 同样更新（bandit 6h / mine 24h）。注意 map_regions 的清理也用这两个常量——region 行的 scanned_at 也按新 TTL 存活，可接受。

## 共享核心端（shared_core/python/dwpm_core）

### 新模块 `features/cloud_map_replica.py`

`CloudMapReplicaStore`（每 account_ref + server_key + map_kind 一个副本）：
- 持久化：JSON 文件，经 ports 的 data_directory（安卓已提供 filesDir；桌面端同机制），文件名 `cloud-map-replica-{server_key}-{map_kind}.json`。内容：`{targets: {targetId: 行}, uploadMemory: {targetId: {行, cells: [[x,y]...]}}, syncCursor, changesCursor: {changedAt, targetId}, fullSyncDone, updatedAtMillis}`。读写要做容错（损坏 → 全量重同步）。
- 视野：以账号主城坐标为中心、`max(brushMaxDistance, mineMaxDistance) + 20 格` 为半径的方形（minX..maxX, minY..maxY）。主城坐标从账号状态取（刷黄/打矿流程已有 startX/startY）。
- `ensure_fresh(now)`：未全量 → 循环调 sync 直到 nextCursor=null；否则若 `now - lastChangesFetchAt > 60_000` → 调 changes 应用增量（upsert 行；status='missing' → 从副本删除；本地按 TTL 过期清理）。返回是否可用。
- `apply_scan_observation(region_x, region_y, seen_targets, now)` → 与 uploadMemory 比对：
  - 新目标或字段变化 → upserts 待发队列 + 更新 uploadMemory；
  - uploadMemory 记录在本格子的目标本次未见 → gone 待发队列 + 从 uploadMemory 移除（若该目标无其他格子记录）；
  - 同时在副本 targets 里更新（本地真相立即生效）。
- `flush_uploads()` → 组 v2 observations 请求发送；成功才清队列（失败保留下轮重试）。
- `candidate_targets()` → 副本内 status 可用（available / 租约过期 reserved / 过 retry rejected）、未过 TTL 的行，供本地筛选。
- 找目标处全部改走副本：刷黄 resident（facade.py:12373）、打矿 resident（facade.py:12875）、手动搜索（facade.py:25012, 25092, 25116）替换 `_cloud_query_map_targets`；`matches` 过滤逻辑不变，只是数据源换成本地。

### facade.py 接线

- `_cloud_publish_map_observations`（24718）：不再直接发 legacy regions 全量，改为逐 region 调 `replica.apply_scan_observation` 然后 `flush_uploads`。**保留 legacy 路径开关**：v2 失败/服务端不支持时回退 legacy 全量上报（保证旧 Worker 也能工作——部署顺序先 Worker 后 APK，正常不会用到）。
- 击杀/出征终态上报：`_cloud_update_map_target_status` 的状态为 "dispatched"（战斗确认胜利）或 "missing" 时，同步把目标加入 gone 队列（立即传播死亡）。看现有调用点确定胜利判定点；若"dispatched"只是已派出而非击杀，则以扫描侧 gone 为准即可，不强行加。
- 确定性分片：`_cloud_claim_map_scans` 调用点（12407 附近）改为：从 `_cloud_presence_mode` 拿 onlineActorIds（新增字段），排序后求自己下标 i/N，扫描坐标列表按 `index % N == i` 过滤；拿不到名单（旧 Worker）时退回现有 claim/release 逻辑。不再调用 claim/release。
- 心跳节奏：`CLOUD_PRESENCE_RENEW_MILLIS` 20_000 → 120_000；`CLOUD_PRESENCE_GRACE_MILLIS` 90_000 → 300_000。注释更新（为什么 20s 曾经必要：租约续期；现在扫描租约废弃，心跳只剩在线证明，2 分钟足够）。
- `_cloud_query_map_targets` 保留（旧 Worker 回退路径用）。

### 兼容与部署顺序

1. 先部署 Worker（新端点 + 心跳改动，legacy 全保留）→ 旧 APK 不受影响。
2. 再出 APK（共享核心内嵌，版本号 +1，RELEASES.md）。
3. 真机验证：176/202 刷黄、打矿行为不变；日志能看到 v2 同步/变化/增量上报。
4. 用量对账：次日对比 d1Analytics。

## 测试要求

- Worker vitest：sync 分页（含 >500 行跨页、视野过滤）、changes 游标（同 changed_at 多行分页不丢）、v2 observations（upserts 立即写、gone 变 missing+传播、reserved/dispatching 不被 gone）、心跳条件写（90s 内重复心跳 presence 行不变、onlineActorIds 正确）、legacy regions 路径回归。每个新测试做非空验证。
- 共享核心 unittest：副本全量同步→增量→本地筛选；扫描比对产生 upserts/gone；上传失败保留队列；副本文件损坏重建；分片下标计算；TTL 过期；旧 Worker（无 v2 端点）回退 legacy。沿用 `电脑端辅助前端/tests/` 现有 harness（端口 fake 模式参考 test_cloud_shared_map_core.py）。
- 全量回归：共享核心整套 + 安卓 `./gradlew testDebugUnitTest`。
