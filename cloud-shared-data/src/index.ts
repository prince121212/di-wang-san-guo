import { cleanup, observeRegions, sharedMode } from "./database";
import { handleAdminRequest } from "./admin";
import { platformDisplayName } from "./platforms";
import type { Env, RequestIdentity, SharedMode } from "./types";
import {
  anonymousIdValue,
  directoryAreas,
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

function authorize(request: Request, env: Env): void {
  const expected = String(env.CLIENT_API_TOKEN ?? "").trim();
  const actual = request.headers.get("authorization") ?? "";
  if (!expected || actual !== `Bearer ${expected}`) {
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
  await env.DB.batch([
    env.DB.prepare(
      "DELETE FROM presence WHERE server_key=? AND last_seen_at<?",
    ).bind(serverScope, now - settings.presenceTtlMillis),
    env.DB.prepare(
      `INSERT INTO presence(server_key,actor_id,last_seen_at)
       VALUES(?,?,?)
       ON CONFLICT(server_key,actor_id) DO UPDATE SET
         last_seen_at=excluded.last_seen_at`,
    ).bind(serverScope, actorId, now),
    env.DB.prepare(
      `INSERT INTO server_catalog(
         platform_key,server_key,area_id,area_name,game_http,first_seen_at,last_seen_at
       ) VALUES(?,?,?,?,?,?,?)
       ON CONFLICT(platform_key,server_key) DO UPDATE SET
         area_id=CASE WHEN excluded.area_id<>'' THEN excluded.area_id ELSE server_catalog.area_id END,
         area_name=CASE WHEN excluded.area_name<>'' THEN excluded.area_name ELSE server_catalog.area_name END,
         game_http=CASE WHEN excluded.game_http<>'' THEN excluded.game_http ELSE server_catalog.game_http END,
         last_seen_at=excluded.last_seen_at,
         observation_count=server_catalog.observation_count+1`,
    ).bind(
      platformKey, serverKey, optionalText(server.areaId, 80),
      optionalText(server.areaName, 160), publicHttpUrl(server.gameHttp), now, now,
    ),
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
         game_http=CASE WHEN excluded.game_http<>'' THEN excluded.game_http ELSE server_directory.game_http END`,
    ).bind(
      platformKey, serverKey, optionalText(server.areaId, 80),
      optionalText(server.areaName, 160), publicHttpUrl(server.gameHttp), now, now,
    ),
  ]);
  const { requesterPresent: _requesterPresent, ...mode } = await sharedMode(
    env.DB,
    serverScope,
    actorId,
    now,
    settings,
  );
  return json({ ok: true, ...mode });
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

async function queryTargets(request: Request, env: Env, now: number): Promise<Response> {
  const input = await body(request);
  const { serverScope, actorId } = common(input);
  const mapKind = mapKindValue(input.mapKind);
  const mode = await requireSharedMode(env, serverScope, actorId, now);
  const targetTtl = mapKind === "bandit" ? 30 * 60 * 1000 : 3 * 60 * 60 * 1000;
  const limit = integerValue(input.limit ?? 100, "返回数量", 1, 500);
  const rows = await env.DB.prepare(
    `SELECT target_id,x,y,target_type,level,data_json,last_seen_at,status
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
    targets: rows.results.map((row) => ({
      targetId: String(row.target_id),
      x: Number(row.x),
      y: Number(row.y),
      type: String(row.target_type ?? ""),
      level: row.level == null ? null : Number(row.level),
      lastSeenAtMillis: Number(row.last_seen_at),
      data: JSON.parse(String(row.data_json ?? "{}")),
    })),
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
  const regions = regionObservations(input.regions, mapKind);
  await observeRegions(env.DB, serverScope, mapKind, actorId, regions, now);
  return json({ ok: true, ...mode, regionCount: regions.length });
}

async function reserveTarget(request: Request, env: Env, now: number): Promise<Response> {
  const input = await body(request);
  const { serverScope, actorId } = common(input);
  const mapKind = mapKindValue(input.mapKind);
  const targetId = textValue(input.targetId, "目标 ID", 160);
  const mode = await requireSharedMode(env, serverScope, actorId, now);
  const token = crypto.randomUUID();
  const targetTtl = mapKind === "bandit" ? 30 * 60 * 1000 : 3 * 60 * 60 * 1000;
  const result = await env.DB.prepare(
    `UPDATE map_targets
     SET status='reserved', reserved_by=?, reservation_token=?, lease_until=?,
         retry_after=0, status_reason='', status_at=?
     WHERE server_key=? AND map_kind=? AND target_id=?
       AND (
         status='available'
         OR (status='reserved' AND lease_until<=?)
         OR (status='rejected' AND retry_after<=?)
       )
       AND last_seen_at>=?`,
  ).bind(
    actorId, token, now + policy(env).targetLeaseMillis, now,
    serverScope, mapKind, targetId, now, now, now - targetTtl,
  ).run();
  const reserved = Number(result.meta.changes ?? 0) === 1;
  return json({
    ok: true,
    ...mode,
    reserved,
    reservationToken: reserved ? token : "",
    leaseUntilMillis: reserved ? now + policy(env).targetLeaseMillis : 0,
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
         retry_after=?, status_reason=?, status_at=?
     WHERE server_key=? AND map_kind=? AND target_id=? AND reservation_token=?
       AND reserved_by=? AND status IN (${previousPlaceholders})`,
  ).bind(
    status, status, status, leaseUntil, retryAfter,
    optionalText(input.reason, 300), now, serverScope, mapKind, targetId, token,
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
  const admin = await handleAdminRequest(request, env);
  if (admin) return admin;
  if (request.method === "GET" && url.pathname === "/health") {
    return json({ ok: true, service: "dwpm-cloud-shared-data", schemaVersion: 1 });
  }
  authorize(request, env);
  const now = Date.now();
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
      return json({ ok: false, code: "INTERNAL_ERROR", error: "共享云端数据服务异常" }, 500);
    }
  },
  async scheduled(controller: ScheduledController, env: Env): Promise<void> {
    await cleanup(env.DB, Number(controller.scheduledTime || Date.now()), policy(env));
  },
};
