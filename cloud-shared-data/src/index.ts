import {
  applyMapEvents,
  cleanup,
  observeRegions,
  sharedMode,
  targetTtlMillis,
} from "./database";
import { handleAdminRequest } from "./admin";
import { runtimeConfig } from "./runtime-config";
import { handleEmailProbeRequest } from "./email-verification-probe";
import { handleMemberRequest } from "./members";
import { handlePaymentRequest } from "./payments";
import { validCloudToken } from "./member-crypto";
export { RuntimeConfigStore } from "./runtime-config";
import { platformDisplayName } from "./platforms";
import type { Env, RequestIdentity, SharedMode } from "./types";
import {
  anonymousIdValue,
  directoryAreas,
  goneTargetIds,
  integerValue,
  mapKindValue,
  objectValue,
  optionalText,
  policy,
  publicHttpUrl,
  regionObservations,
  RequestError,
  stringArray,
  textValue,
  upsertObservations,
} from "./validation";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

async function body(request: Request): Promise<Record<string, unknown>> {
  try {
    const declaredLength = Number(request.headers.get("content-length") ?? 0);
    if (declaredLength > 1_048_576) throw new RequestError("请求体不能超过1MB", 413);
    const raw = await request.text();
    if (raw.length > 1_048_576) throw new RequestError("请求体不能超过1MB", 413);
    return objectValue(JSON.parse(raw));
  } catch (error) {
    if (error instanceof RequestError) throw error;
    throw new RequestError("请求体不是有效 JSON");
  }
}

async function authorize(request: Request, env: Env): Promise<void> {
  const actual = request.headers.get("authorization") ?? "";
  // Additive client-key rotation: never invalidate existing installed apps
  // when provisioning a runtime-only key for a newly built APK.
  const accepted = [env.CLIENT_API_TOKEN, env.CLIENT_API_TOKEN_V2]
    .map(value => String(value ?? "").trim()).filter(Boolean);
  if (!accepted.some(token => actual === `Bearer ${token}`)
    && !(actual.startsWith("Bearer ") && await validCloudToken(env,actual.slice(7)))) {
    throw new RequestError("未授权", 401, "UNAUTHORIZED");
  }
}

function common(input: Record<string, unknown>): RequestIdentity {
  const platformKey = textValue(input.platformKey, "平台键", 80);
  const serverKey = textValue(input.serverKey, "区服键", 240);
  return {
    platformKey,
    serverKey,
    // JSON tuple encoding is collision-free even if either public key contains ':'
    // or other separators. Display names must never be used as serverKey.
    serverScope: JSON.stringify([platformKey, serverKey]),
    actorId: anonymousIdValue(input.actorId, "匿名角色 ID"),
  };
}

async function requireSharedMode(
  env: Env,
  serverScope: string,
  actorId: string,
  now: number,
): Promise<SharedMode> {
  const mode = await sharedMode(env.DB, serverScope, actorId, now, policy(env));
  if (!mode.requesterPresent) {
    throw new RequestError(
      "当前客户端没有有效在线心跳",
      409,
      "PRESENCE_REQUIRED",
    );
  }
  if (mode.mode !== "CLOUD_SHARED") {
    throw new RequestError(
      "当前区服在线账号不足2个，继续使用本地地图",
      409,
      "SHARED_MODE_INACTIVE",
    );
  }
  const { requesterPresent: _requesterPresent, ...publicMode } = mode;
  return publicMode;
}

async function heartbeat(request: Request, env: Env, now: number): Promise<Response> {
  const input = await body(request);
  const { platformKey, serverKey, serverScope, actorId } = common(input);
  const server = objectValue(input.server ?? {}, "区服信息");
  const settings = policy(env);
  const config = await runtimeConfig(env);
  if (!config.cloudBrushMapEnabled) {
    return json({ ok: true, mode: "LOCAL_ONLY", onlineAccountCount: 0,
      threshold: settings.threshold, serverTimeMillis: now, onlineActorIds: [], config });
  }
  const areaId = optionalText(server.areaId, 80);
  const areaName = optionalText(server.areaName, 160);
  const gameHttp = publicHttpUrl(server.gameHttp);
  await env.DB.batch([
    env.DB.prepare(
      "DELETE FROM presence WHERE server_key=? AND last_seen_at<?",
    ).bind(serverScope, now - settings.presenceTtlMillis),
    // A heartbeat is only proof of being online, and every reader derives
    // online from last_seen_at against the TTL - so a row already inside the
    // threshold below carries no new information.  Skipping it is what turns
    // a 20-second heartbeat from a constant write stream into one write per
    // 90 seconds per actor.
    env.DB.prepare(
      `INSERT INTO presence(server_key,actor_id,last_seen_at)
       VALUES(?,?,?)
       ON CONFLICT(server_key,actor_id) DO UPDATE SET
         last_seen_at=excluded.last_seen_at
       WHERE presence.last_seen_at < ?`,
    ).bind(serverScope, actorId, now, now - 90_000),
    // Old APKs only ever write the directory from their heartbeat, so this
    // stays - but conditional.  An unchanged row is rewritten at most once an
    // hour instead of once per heartbeat; observation_count used to tick on
    // every heartbeat, which is exactly the write stream being removed.
    env.DB.prepare(
      `INSERT INTO server_catalog(
         platform_key,server_key,area_id,area_name,game_http,first_seen_at,last_seen_at
       ) VALUES(?,?,?,?,?,?,?)
       ON CONFLICT(platform_key,server_key) DO UPDATE SET
         area_id=CASE WHEN excluded.area_id<>'' THEN excluded.area_id ELSE server_catalog.area_id END,
         area_name=CASE WHEN excluded.area_name<>'' THEN excluded.area_name ELSE server_catalog.area_name END,
         game_http=CASE WHEN excluded.game_http<>'' THEN excluded.game_http ELSE server_catalog.game_http END,
         last_seen_at=excluded.last_seen_at,
         observation_count=server_catalog.observation_count+1
       WHERE server_catalog.last_seen_at < ?
          OR (server_catalog.area_id<>excluded.area_id AND excluded.area_id<>'')
          OR (server_catalog.area_name<>excluded.area_name AND excluded.area_name<>'')
          OR (server_catalog.game_http<>excluded.game_http AND excluded.game_http<>'')`,
    ).bind(platformKey, serverKey, areaId, areaName, gameHttp, now, now, now - 3_600_000),
    // Keep the public directory backwards compatible for older clients that
    // only know how to send a heartbeat.  Complete passport snapshots use the
    // dedicated sync endpoint below and are not inferred from presence.
    env.DB.prepare(
      `INSERT INTO server_directory(
         platform_key,server_key,area_id,area_name,game_http,
         first_seen_at,last_directory_sync_at
       ) VALUES(?,?,?,?,?,?,?)
       ON CONFLICT(platform_key,server_key) DO UPDATE SET
         area_id=CASE WHEN excluded.area_id<>'' THEN excluded.area_id ELSE server_directory.area_id END,
         area_name=CASE WHEN excluded.area_name<>'' THEN excluded.area_name ELSE server_directory.area_name END,
         game_http=CASE WHEN excluded.game_http<>'' THEN excluded.game_http ELSE server_directory.game_http END,
         last_directory_sync_at=excluded.last_directory_sync_at
       WHERE server_directory.last_directory_sync_at < ?
          OR (server_directory.area_id<>excluded.area_id AND excluded.area_id<>'')
          OR (server_directory.area_name<>excluded.area_name AND excluded.area_name<>'')
          OR (server_directory.game_http<>excluded.game_http AND excluded.game_http<>'')`,
    ).bind(platformKey, serverKey, areaId, areaName, gameHttp, now, now, now - 3_600_000),
  ]);
  const { requesterPresent: _requesterPresent, ...mode } = await sharedMode(
    env.DB,
    serverScope,
    actorId,
    now,
    settings,
  );
  // Sharding is computed from this list client-side, so it must come from the
  // same table and TTL sharedMode just used - and it must include the caller,
  // whose own presence row may legitimately have been skipped above.
  const online = await env.DB.prepare(
    `SELECT actor_id FROM presence
     WHERE server_key=? AND last_seen_at>=? ORDER BY actor_id`,
  ).bind(serverScope, now - settings.presenceTtlMillis).all<{ actor_id: string }>();
  return json({
    ok: true,
    ...mode,
    onlineActorIds: online.results.map((row) => String(row.actor_id)),
  });
}

async function syncDirectory(request: Request, env: Env, now: number): Promise<Response> {
  const input = await body(request);
  const platformKey = textValue(input.platformKey, "平台键", 80);
  const areas = directoryAreas(input.areas);
  const encoded = JSON.stringify(areas);
  // json_each keeps a complete snapshot at two D1 statements regardless of
  // whether a platform has 60 or 1,000 servers.  Validation happens before
  // either statement, and both operations share the same exact snapshot.
  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO server_directory(
         platform_key,server_key,area_id,area_name,target,game_http,
         first_seen_at,last_directory_sync_at,sync_count
       )
       SELECT ?,
              CAST(json_extract(area.value,'$.serverKey') AS TEXT),
              COALESCE(CAST(json_extract(area.value,'$.areaId') AS TEXT),''),
              CAST(json_extract(area.value,'$.areaName') AS TEXT),
              COALESCE(CAST(json_extract(area.value,'$.target') AS TEXT),''),
              COALESCE(CAST(json_extract(area.value,'$.gameHttp') AS TEXT),''),
              ?,?,1
       FROM json_each(?) AS area
       WHERE 1
       ON CONFLICT(platform_key,server_key) DO UPDATE SET
         area_id=excluded.area_id,
         area_name=excluded.area_name,
         target=excluded.target,
         game_http=excluded.game_http,
         last_directory_sync_at=excluded.last_directory_sync_at,
         sync_count=server_directory.sync_count+1`,
    ).bind(platformKey, now, now, encoded),
    env.DB.prepare(
      `DELETE FROM server_directory
       WHERE platform_key=? AND NOT EXISTS (
         SELECT 1 FROM json_each(?) AS area
         WHERE CAST(json_extract(area.value,'$.serverKey') AS TEXT)=server_directory.server_key
       )`,
    ).bind(platformKey, encoded),
  ]);
  return json({
    ok: true,
    platformKey,
    count: areas.length,
    syncedAtMillis: now,
  });
}

async function catalog(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const platformKey = optionalText(url.searchParams.get("platformKey"), 80);
  const result = platformKey
    ? await env.DB.prepare(
      `SELECT d.platform_key,d.server_key,d.area_id,d.area_name,d.game_http,
              d.target,d.last_directory_sync_at,d.first_seen_at,
              c.last_seen_at,c.observation_count
       FROM server_directory d
       LEFT JOIN server_catalog c
         ON c.platform_key=d.platform_key AND c.server_key=d.server_key
       WHERE d.platform_key=?
       ORDER BY COALESCE(c.last_seen_at,d.last_directory_sync_at) DESC LIMIT 1000`,
    ).bind(platformKey).all()
    : await env.DB.prepare(
      `SELECT d.platform_key,d.server_key,d.area_id,d.area_name,d.game_http,
              d.target,d.last_directory_sync_at,d.first_seen_at,
              c.last_seen_at,c.observation_count
       FROM server_directory d
       LEFT JOIN server_catalog c
         ON c.platform_key=d.platform_key AND c.server_key=d.server_key
       ORDER BY COALESCE(c.last_seen_at,d.last_directory_sync_at) DESC LIMIT 1000`,
    ).all();
  return json({
    ok: true,
    servers: result.results.map((row) => ({
      platformKey: String(row.platform_key),
      platformName: platformDisplayName(row.platform_key),
      serverKey: String(row.server_key),
      areaId: String(row.area_id ?? ""),
      areaName: String(row.area_name ?? ""),
      target: String(row.target ?? ""),
      gameHttp: String(row.game_http ?? ""),
      lastSeenAtMillis: Number(row.last_seen_at ?? 0),
      observationCount: Number(row.observation_count ?? 0),
      lastDirectorySyncAtMillis: Number(row.last_directory_sync_at ?? 0),
    })),
  });
}

async function queryDirectory(request: Request, env: Env): Promise<Response> {
  const input = await body(request);
  const platformKey = textValue(input.platformKey, "平台键", 80);
  const result = await env.DB.prepare(
    `SELECT server_key,area_id,area_name,target,game_http,last_directory_sync_at
     FROM server_directory
     WHERE platform_key=?
     ORDER BY server_key COLLATE NOCASE,area_name COLLATE NOCASE
     LIMIT 1000`,
  ).bind(platformKey).all<Record<string, unknown>>();
  const updatedAt = Math.max(
    0,
    ...result.results.map((row) => Number(row.last_directory_sync_at ?? 0)),
  );
  return json({
    ok: true,
    platformKey,
    platform: platformDisplayName(platformKey),
    updatedAt,
    count: result.results.length,
    areas: result.results.map((row) => ({
      target: String(row.target ?? ""),
      areaId: String(row.area_id ?? ""),
      areaName: String(row.area_name ?? ""),
      serverUrl: String(row.game_http ?? ""),
      serverKey: String(row.server_key),
    })),
  });
}

// One row shape for every map-target reader: sync pages, the change feed and
// the legacy query all serialize through this so a field added for one
// consumer (e.g. changed_at) can never drift between them.
const TARGET_ROW_COLUMNS =
  "target_id,x,y,target_type,level,data_json,last_seen_at,changed_at,status,status_at,lease_until,retry_after";

function targetRowJson(row: Record<string, unknown>): Record<string, unknown> {
  return {
    targetId: String(row.target_id),
    x: Number(row.x),
    y: Number(row.y),
    type: String(row.target_type ?? ""),
    level: row.level == null ? null : Number(row.level),
    lastSeenAtMillis: Number(row.last_seen_at),
    changedAtMillis: Number(row.changed_at ?? 0),
    status: String(row.status ?? "available"),
    statusAtMillis: Number(row.status_at ?? 0),
    leaseUntilMillis: Number(row.lease_until ?? 0),
    retryAfterMillis: Number(row.retry_after ?? 0),
    data: JSON.parse(String(row.data_json ?? "{}")),
  };
}

async function queryTargets(request: Request, env: Env, now: number): Promise<Response> {
  const input = await body(request);
  const { serverScope, actorId } = common(input);
  const mapKind = mapKindValue(input.mapKind);
  const mode = await requireSharedMode(env, serverScope, actorId, now);
  const targetTtl = targetTtlMillis(mapKind);
  const limit = integerValue(input.limit ?? 100, "返回数量", 1, 500);
  const rows = await env.DB.prepare(
    `SELECT ${TARGET_ROW_COLUMNS}
     FROM map_targets
     WHERE server_key=? AND map_kind=?
       AND (
         status='available'
         OR (status='reserved' AND lease_until<=?)
         OR (status='rejected' AND retry_after<=?)
       )
       AND last_seen_at>=?
     ORDER BY last_seen_at DESC LIMIT ?`,
  ).bind(
    serverScope, mapKind, now, now, now - targetTtl, limit,
  ).all<Record<string, unknown>>();
  return json({
    ok: true,
    ...mode,
    targets: rows.results.map(targetRowJson),
  });
}

interface Viewport {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

// All four bounds arrive or none do: a partially clamped square silently
// drops or admits whole bands of the map, which is worse than rejecting.
function viewport(input: Record<string, unknown>): Viewport | null {
  const keys = ["minX", "maxX", "minY", "maxY"] as const;
  const present = keys.filter((key) => input[key] != null);
  if (present.length === 0) return null;
  if (present.length !== keys.length) {
    throw new RequestError("视野过滤需要同时提供 minX/maxX/minY/maxY");
  }
  const bounds = Object.fromEntries(keys.map((key) => [
    key,
    integerValue(input[key], `视野 ${key}`, 0, 100_000),
  ])) as unknown as Viewport;
  if (bounds.minX > bounds.maxX || bounds.minY > bounds.maxY) {
    throw new RequestError("视野范围无效");
  }
  return bounds;
}

async function syncTargets(request: Request, env: Env, now: number): Promise<Response> {
  const input = await body(request);
  const { serverScope, actorId } = common(input);
  const mapKind = mapKindValue(input.mapKind);
  const mode = await requireSharedMode(env, serverScope, actorId, now);
  const limit = integerValue(input.limit ?? 500, "返回数量", 1, 500);
  const view = viewport(input);
  let cursor: { lastSeenAt: number; targetId: string } | null = null;
  if (input.cursor != null) {
    const raw = objectValue(input.cursor, "同步游标");
    cursor = {
      lastSeenAt: integerValue(raw.lastSeenAt, "同步游标时间", 0, Number.MAX_SAFE_INTEGER),
      targetId: textValue(raw.targetId, "同步游标目标 ID", 160),
    };
  }
  const conditions = [
    "server_key=?",
    "map_kind=?",
    // The sync feed mirrors what queryTargets would offer, so it applies the
    // same TTL: a row older than that is about to be swept and a fresh
    // replica gains nothing by copying it.
    "last_seen_at>=?",
  ];
  const bindings: unknown[] = [serverScope, mapKind, now - targetTtlMillis(mapKind)];
  if (view) {
    conditions.push("x BETWEEN ? AND ?", "y BETWEEN ? AND ?");
    bindings.push(view.minX, view.maxX, view.minY, view.maxY);
  }
  if (cursor) {
    conditions.push("(last_seen_at < ? OR (last_seen_at = ? AND target_id > ?))");
    bindings.push(cursor.lastSeenAt, cursor.lastSeenAt, cursor.targetId);
  }
  const rows = await env.DB.prepare(
    `SELECT ${TARGET_ROW_COLUMNS}
     FROM map_targets
     WHERE ${conditions.join(" AND ")}
     ORDER BY last_seen_at DESC, target_id ASC LIMIT ?`,
  ).bind(...bindings, limit).all<Record<string, unknown>>();
  // A short page means the feed is exhausted; handing back a cursor anyway
  // would make the client burn one more request to learn there is nothing.
  const last = rows.results[rows.results.length - 1];
  const nextCursor = rows.results.length === limit && last
    ? {
      lastSeenAt: Number(last.last_seen_at),
      targetId: String(last.target_id),
    }
    : null;
  return json({
    ok: true,
    ...mode,
    targets: rows.results.map(targetRowJson),
    nextCursor,
    serverTimeMillis: now,
  });
}

async function targetChanges(request: Request, env: Env, now: number): Promise<Response> {
  const input = await body(request);
  const { serverScope, actorId } = common(input);
  const mapKind = mapKindValue(input.mapKind);
  const mode = await requireSharedMode(env, serverScope, actorId, now);
  const limit = integerValue(input.limit ?? 500, "返回数量", 1, 500);
  const view = viewport(input);
  const rawSince = input.since == null ? {} : objectValue(input.since, "变化游标");
  const since = {
    changedAt: integerValue(rawSince.changedAt ?? 0, "变化游标时间", 0, Number.MAX_SAFE_INTEGER),
    targetId: optionalText(rawSince.targetId, 160),
  };
  const conditions = [
    "server_key=?",
    "map_kind=?",
    // Match the composite index's range, not just its server/map prefix.
    // The equivalent OR predicate made an empty poll scan the whole map.
    "(changed_at, target_id) > (?, ?)",
  ];
  const bindings: unknown[] = [serverScope, mapKind, since.changedAt, since.targetId];
  if (view) {
    conditions.push("x BETWEEN ? AND ?", "y BETWEEN ? AND ?");
    bindings.push(view.minX, view.maxX, view.minY, view.maxY);
  }
  // No TTL and no status filter here: a tombstone (status='missing') is the
  // only way a replica learns a target died, and filtering it out would leave
  // ghosts in every client that had already copied the row.
  const rows = await env.DB.prepare(
    `SELECT ${TARGET_ROW_COLUMNS}
     FROM map_targets
     WHERE ${conditions.join(" AND ")}
     ORDER BY changed_at ASC, target_id ASC LIMIT ?`,
  ).bind(...bindings, limit).all<Record<string, unknown>>();
  const last = rows.results[rows.results.length - 1];
  // With no changes the cursor echoes the input: the client stores it
  // opaquely and must not be nudged forward past changes it has not seen.
  const cursor = last
    ? { changedAt: Number(last.changed_at), targetId: String(last.target_id) }
    : since;
  return json({
    ok: true,
    ...mode,
    targets: rows.results.map(targetRowJson),
    cursor,
    serverTimeMillis: now,
  });
}

async function claimScans(request: Request, env: Env, now: number): Promise<Response> {
  const input = await body(request);
  const { serverScope, actorId } = common(input);
  const mapKind = mapKindValue(input.mapKind);
  const rawCoordinates = input.coordinates;
  if (!Array.isArray(rawCoordinates) || rawCoordinates.length < 1 || rawCoordinates.length > 20) {
    throw new RequestError("扫描坐标必须包含1到20项");
  }
  const coordinates = rawCoordinates.map((value) => {
    const row = objectValue(value, "扫描坐标");
    return {
      x: integerValue(row.x, "扫描 X 坐标", 0, 100_000),
      y: integerValue(row.y, "扫描 Y 坐标", 0, 100_000),
    };
  }).filter((coordinate, index, values) => values.findIndex(
    (candidate) => candidate.x === coordinate.x && candidate.y === coordinate.y,
  ) === index);
  const mode = await requireSharedMode(env, serverScope, actorId, now);
  const settings = policy(env);
  const claimed: Array<{ x: number; y: number; leaseToken: string }> = [];
  for (const coordinate of coordinates) {
    const leaseToken = crypto.randomUUID();
    const result = await env.DB.prepare(
      `INSERT INTO map_scan_leases(
         server_key,map_kind,scan_x,scan_y,owner,lease_token,lease_until
       ) SELECT ?,?,?,?,?,?,?
       WHERE NOT EXISTS (
         SELECT 1 FROM map_regions
         WHERE server_key=? AND map_kind=? AND scan_x=? AND scan_y=? AND scanned_at>=?
       )
       ON CONFLICT(server_key,map_kind,scan_x,scan_y) DO UPDATE SET
         owner=excluded.owner, lease_token=excluded.lease_token,
         lease_until=excluded.lease_until
       WHERE map_scan_leases.owner=excluded.owner OR map_scan_leases.lease_until<=?`,
    ).bind(
      serverScope, mapKind, coordinate.x, coordinate.y, actorId, leaseToken,
      now + settings.scanLeaseMillis,
      serverScope, mapKind, coordinate.x, coordinate.y, now - settings.scanFreshMillis,
      now,
    ).run();
    if (Number(result.meta.changes ?? 0) > 0) {
      claimed.push({ ...coordinate, leaseToken });
    }
  }
  return json({ ok: true, ...mode, scans: claimed });
}

async function releaseScans(request: Request, env: Env, now: number): Promise<Response> {
  const input = await body(request);
  const { serverScope, actorId } = common(input);
  const mapKind = mapKindValue(input.mapKind);
  const mode = await requireSharedMode(env, serverScope, actorId, now);
  const tokens = stringArray(input.leaseTokens, "扫描租约", 20);
  if (tokens.length === 0) return json({ ok: true, ...mode, releasedCount: 0 });
  const placeholders = tokens.map(() => "?").join(",");
  const result = await env.DB.prepare(
    `DELETE FROM map_scan_leases
     WHERE server_key=? AND map_kind=? AND lease_token IN (${placeholders})`,
  ).bind(serverScope, mapKind, ...tokens).run();
  return json({ ok: true, ...mode, releasedCount: Number(result.meta.changes ?? 0) });
}

async function observations(request: Request, env: Env, now: number): Promise<Response> {
  const input = await body(request);
  const { serverScope, actorId } = common(input);
  const mapKind = mapKindValue(input.mapKind);
  const mode = await requireSharedMode(env, serverScope, actorId, now);
  const hasUpserts = input.upserts != null;
  const hasGone = input.gone != null;
  if (hasUpserts || hasGone) {
    // v2: validate the whole batch before one atomic commit. Client-side
    // diffing does not imply exactly-once delivery, so the database also
    // suppresses identical replays without delaying real field changes.
    const upserts = hasUpserts ? upsertObservations(input.upserts, mapKind) : [];
    const gone = hasGone ? goneTargetIds(input.gone) : [];
    const goneCount = await applyMapEvents(
      env.DB, serverScope, mapKind, upserts, gone, now,
    );
    return json({
      ok: true,
      ...mode,
      upsertedCount: upserts.length,
      goneCount,
      serverTimeMillis: now,
    });
  }
  const regions = regionObservations(input.regions, mapKind);
  await observeRegions(
    env.DB, serverScope, mapKind, actorId, regions, now,
    policy(env).scanFreshMillis,
  );
  return json({ ok: true, ...mode, regionCount: regions.length });
}

async function reserveTarget(request: Request, env: Env, now: number): Promise<Response> {
  const input = await body(request);
  const { serverScope, actorId } = common(input);
  const mapKind = mapKindValue(input.mapKind);
  const targetId = textValue(input.targetId, "目标 ID", 160);
  const mode = await requireSharedMode(env, serverScope, actorId, now);
  const token = crypto.randomUUID();
  const targetTtl = targetTtlMillis(mapKind);
  const result = await env.DB.prepare(
    `UPDATE map_targets
     SET status='reserved', reserved_by=?, reservation_token=?, lease_until=?,
         retry_after=0, status_reason='', status_at=?, changed_at=?
     WHERE server_key=? AND map_kind=? AND target_id=?
       AND (
         status='available'
         OR (status='reserved' AND lease_until<=?)
         OR (status='rejected' AND retry_after<=?)
       )
       AND last_seen_at>=?`,
  ).bind(
    actorId, token, now + policy(env).targetLeaseMillis, now, now,
    serverScope, mapKind, targetId, now, now, now - targetTtl,
  ).run();
  const reserved = Number(result.meta.changes ?? 0) === 1;
  // A refusal is two different facts wearing one answer.  "A peer holds the
  // lease" tells the client to retry later; "this target is unknown here"
  // tells it the cloud lost (or never had) the row - the client's replica is
  // then the only copy of that truth and must re-publish it, or the target
  // stays unreservable until its local TTL.  The lookup costs one primary-key
  // read and only runs on failure, which a healthy fleet rarely sees.
  let reason = "";
  if (!reserved) {
    const existing = await env.DB.prepare(
      `SELECT 1 AS found FROM map_targets
       WHERE server_key=? AND map_kind=? AND target_id=?`,
    ).bind(serverScope, mapKind, targetId).first<{ found: number }>();
    reason = existing ? "unavailable" : "unknown-target";
  }
  return json({
    ok: true,
    ...mode,
    reserved,
    reservationToken: reserved ? token : "",
    leaseUntilMillis: reserved ? now + policy(env).targetLeaseMillis : 0,
    ...(reason ? { reason } : {}),
  });
}

async function targetStatus(request: Request, env: Env, now: number): Promise<Response> {
  const input = await body(request);
  const { serverScope, actorId } = common(input);
  const mapKind = mapKindValue(input.mapKind);
  const mode = await requireSharedMode(env, serverScope, actorId, now);
  const targetId = textValue(input.targetId, "目标 ID", 160);
  const token = textValue(input.reservationToken, "目标预占令牌", 160);
  const status = textValue(input.status, "目标状态", 40);
  if (!["available", "dispatching", "dispatched", "rejected", "missing", "uncertain"].includes(status)) {
    throw new RequestError("目标状态无效");
  }
  const settings = policy(env);
  const retryAfter = status === "rejected" ? now + settings.rejectRetryMillis : 0;
  const retainsReservation = status === "dispatching" || status === "uncertain";
  const leaseUntil = retainsReservation ? now + settings.targetLeaseMillis : 0;
  const allowedPrevious: Record<string, string[]> = {
    dispatching: ["reserved"],
    dispatched: ["reserved", "dispatching", "uncertain"],
    available: ["reserved", "dispatching", "uncertain"],
    rejected: ["reserved", "dispatching", "uncertain"],
    missing: ["reserved", "dispatching", "uncertain"],
    uncertain: ["reserved", "dispatching"],
  };
  const previous = allowedPrevious[status];
  const previousPlaceholders = previous.map(() => "?").join(",");
  const result = await env.DB.prepare(
    `UPDATE map_targets
     SET status=?, reserved_by=CASE WHEN ? IN ('dispatching','uncertain') THEN reserved_by ELSE '' END,
         reservation_token=CASE WHEN ? IN ('dispatching','uncertain') THEN reservation_token ELSE '' END,
         lease_until=?,
         retry_after=?, status_reason=?, status_at=?, changed_at=?
     WHERE server_key=? AND map_kind=? AND target_id=? AND reservation_token=?
       AND reserved_by=? AND status IN (${previousPlaceholders})`,
  ).bind(
    status, status, status, leaseUntil, retryAfter,
    optionalText(input.reason, 300), now, now, serverScope, mapKind, targetId, token,
    actorId, ...previous,
  ).run();
  const updated = Number(result.meta.changes ?? 0) === 1;
  return json(
    { ok: updated, ...mode, updated, status, serverTimeMillis: now },
    updated ? 200 : 409,
  );
}

async function route(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const payment = await handlePaymentRequest(request, env);
  if (payment) return payment;
  const member = await handleMemberRequest(request, env);
  if (member) return member;
  const emailProbe = await handleEmailProbeRequest(request, env);
  if (emailProbe) return emailProbe;
  const admin = await handleAdminRequest(request, env);
  if (admin) return admin;
  if (request.method === "GET" && url.pathname === "/health") {
    return json({ ok: true, service: "dwpm-cloud-shared-data", schemaVersion: 1 });
  }
  const now = Date.now();
  // This global, non-sensitive read-only switch grants no membership or admin authority.
  // New APKs do not need a long-lived shared credential just to read it.
  if (request.method === "POST" && url.pathname === "/v1/client/config") {
    return json({ ok: true, config: await runtimeConfig(env) });
  }
  await authorize(request, env);
  // Stop old clients as well, before any D1 read/write. A blocked mutation is
  // explicitly rejected, never acknowledged as an uploaded observation.
  if (request.method === "POST" && url.pathname.startsWith("/v1/maps/")) {
    const input = await body(request.clone() as Request);
    if (input.mapKind === "bandit") {
      const config = await runtimeConfig(env);
      if (!config.cloudBrushMapEnabled) return json({ ok: false, code: "CLOUD_BRUSH_MAP_DISABLED",
        error: "管理员已关闭云端刷黄地图，请使用手机本地地图", mode: "LOCAL_ONLY", config }, 409);
    }
  }
  if (request.method === "POST" && url.pathname === "/v1/presence/heartbeat") {
    return heartbeat(request, env, now);
  }
  if (request.method === "POST" && url.pathname === "/v1/servers/directory/sync") {
    return syncDirectory(request, env, now);
  }
  if (request.method === "POST" && url.pathname === "/v1/servers/directory/query") {
    return queryDirectory(request, env);
  }
  if (request.method === "GET" && url.pathname === "/v1/servers/catalog") {
    return catalog(request, env);
  }
  if (request.method === "POST" && url.pathname === "/v1/maps/targets/query") {
    return queryTargets(request, env, now);
  }
  if (request.method === "POST" && url.pathname === "/v1/maps/targets/sync") {
    return syncTargets(request, env, now);
  }
  if (request.method === "POST" && url.pathname === "/v1/maps/targets/changes") {
    return targetChanges(request, env, now);
  }
  if (request.method === "POST" && url.pathname === "/v1/maps/scans/claim") {
    return claimScans(request, env, now);
  }
  if (request.method === "POST" && url.pathname === "/v1/maps/scans/release") {
    return releaseScans(request, env, now);
  }
  if (request.method === "POST" && url.pathname === "/v1/maps/observations") {
    return observations(request, env, now);
  }
  if (request.method === "POST" && url.pathname === "/v1/maps/targets/reserve") {
    return reserveTarget(request, env, now);
  }
  if (request.method === "POST" && url.pathname === "/v1/maps/targets/status") {
    return targetStatus(request, env, now);
  }
  throw new RequestError("接口不存在", 404, "NOT_FOUND");
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      return await route(request, env);
    } catch (error) {
      if (error instanceof RequestError) {
        return json({ ok: false, code: error.code, error: error.message }, error.status);
      }
      console.error(error);
      const limit = d1DailyLimit(error);
      if (limit) {
        const now = Date.now();
        const resetAtMillis = (Math.floor(now / 86_400_000) + 1) * 86_400_000;
        const response = json({
          ok: false,
          code: "CLOUD_D1_DAILY_LIMIT",
          error: `共享地图数据库今日免费${limit === "write" ? "写入" : "读取"}额度已耗尽，`
            + "免费额度于 UTC 00:00（北京时间08:00）重置；共享派遣暂不可用",
          limit,
          retryAtMillis: resetAtMillis,
        }, 503);
        response.headers.set("retry-after", String(Math.ceil((resetAtMillis - now) / 1_000)));
        return response;
      }
      return json({ ok: false, code: "INTERNAL_ERROR", error: "共享云端数据服务异常" }, 500);
    }
  },
  async scheduled(controller: ScheduledController, env: Env): Promise<void> {
    await cleanup(env.DB, Number(controller.scheduledTime || Date.now()), policy(env));
  },
};

function d1DailyLimit(error: unknown): "read" | "write" | null {
  // D1 may wrap the useful message in Error.cause. Never classify unrelated
  // SQL failures as quota errors or expose raw SQL/credentials to clients.
  for (let depth = 0; depth < 5 && error instanceof Error; depth++) {
    const match = /exceeded D1's free tier daily row (read|write) limit/i.exec(error.message);
    if (match) return match[1].toLowerCase() as "read" | "write";
    error = error.cause;
  }
  return null;
}
