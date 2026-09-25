import type { Env, MapKind } from "./types";
import { policy, RequestError } from "./validation";
import { platformDisplayName } from "./platforms";
import { runtimeConfig, updateRuntimeConfig } from "./runtime-config";
import { handleMemberAdmin } from "./members";
import { handlePaymentAdmin } from "./payments";

const ADMIN_COOKIE = "__Host-dwpm_admin";
const SESSION_MAX_AGE_SECONDS = 8 * 60 * 60;
const BANDIT_TTL_MILLIS = 30 * 60 * 1000;
const MINE_TTL_MILLIS = 3 * 60 * 60 * 1000;

function json(body: unknown, status = 200, headers: HeadersInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      ...headers,
    },
  });
}

function redirect(location: string): Response {
  return new Response(null, {
    status: 302,
    headers: {
      location,
      "cache-control": "no-store",
    },
  });
}

function securityHeaders(headers: Headers): Headers {
  headers.set(
    "content-security-policy",
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
      + "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; "
      + "form-action 'self'",
  );
  headers.set("x-content-type-options", "nosniff");
  headers.set("x-frame-options", "DENY");
  headers.set("referrer-policy", "no-referrer");
  headers.set("permissions-policy", "camera=(), microphone=(), geolocation=()");
  return headers;
}

async function adminAsset(request: Request, env: Env): Promise<Response> {
  if (!env.ASSETS) return json({ ok: false, error: "管理员页面资源未配置" }, 503);
  const pathname = new URL(request.url).pathname;
  const assetPath = pathname === "/admin/"
    ? "/admin/index.html"
    : pathname;
  if (!["/admin/index.html", "/admin/admin.css", "/admin/admin.js", "/admin/members.js", "/admin/payments.js"].includes(assetPath)) {
    throw new RequestError("页面不存在", 404, "NOT_FOUND");
  }
  const url = new URL(request.url);
  url.pathname = assetPath;
  const upstream = await env.ASSETS.fetch(new Request(url.toString(), request));
  const headers = securityHeaders(new Headers(upstream.headers));
  headers.set("cache-control", assetPath.endsWith("index.html") ? "no-store" : "public, max-age=300");
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers,
  });
}

function bytesToBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64UrlToBytes(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/")
    + "=".repeat((4 - value.length % 4) % 4);
  const binary = atob(padded);
  return Uint8Array.from(
    binary,
    (character) => character.charCodeAt(0),
  ).buffer as ArrayBuffer;
}

async function hmacKey(env: Env): Promise<CryptoKey | null> {
  const secret = String(env.ADMIN_SESSION_SECRET ?? "").trim();
  if (secret.length < 32) return null;
  return crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

async function issueSession(username: string, env: Env, now: number): Promise<string> {
  const key = await hmacKey(env);
  if (!key) throw new RequestError("管理员会话密钥未配置", 503, "ADMIN_NOT_CONFIGURED");
  const payload = bytesToBase64Url(new TextEncoder().encode(JSON.stringify({
    username,
    issuedAt: now,
    expiresAt: now + SESSION_MAX_AGE_SECONDS * 1000,
  })));
  const signature = new Uint8Array(await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(payload),
  ));
  return `${payload}.${bytesToBase64Url(signature)}`;
}

function cookieValue(request: Request, name: string): string {
  for (const part of String(request.headers.get("cookie") ?? "").split(";")) {
    const index = part.indexOf("=");
    if (index < 0) continue;
    if (part.slice(0, index).trim() === name) return part.slice(index + 1).trim();
  }
  return "";
}

async function authenticatedUsername(request: Request, env: Env, now: number): Promise<string> {
  const token = cookieValue(request, ADMIN_COOKIE);
  const [payload, signature, extra] = token.split(".");
  if (!payload || !signature || extra) return "";
  const key = await hmacKey(env);
  if (!key) return "";
  let valid = false;
  try {
    valid = await crypto.subtle.verify(
      "HMAC",
      key,
      base64UrlToBytes(signature),
      new TextEncoder().encode(payload),
    );
  } catch {
    return "";
  }
  if (!valid) return "";
  try {
    const session = JSON.parse(new TextDecoder().decode(base64UrlToBytes(payload))) as {
      username?: unknown;
      issuedAt?: unknown;
      expiresAt?: unknown;
    };
    const username = String(session.username ?? "");
    const expected = String(env.ADMIN_USERNAME ?? "").trim();
    const issuedAt = Number(session.issuedAt ?? 0);
    const expiresAt = Number(session.expiresAt ?? 0);
    if (!username || username !== expected || issuedAt > now + 60_000 || expiresAt <= now) return "";
    if (expiresAt - issuedAt > SESSION_MAX_AGE_SECONDS * 1000 + 60_000) return "";
    return username;
  } catch {
    return "";
  }
}

function constantTimeEqual(left: string, right: string): boolean {
  const a = new TextEncoder().encode(left);
  const b = new TextEncoder().encode(right);
  const length = Math.max(a.length, b.length);
  let difference = a.length ^ b.length;
  for (let index = 0; index < length; index += 1) {
    difference |= (a[index] ?? 0) ^ (b[index] ?? 0);
  }
  return difference === 0;
}

async function loginClientKey(request: Request): Promise<string> {
  const address = request.headers.get("cf-connecting-ip") ?? "unknown";
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(`dwpm-admin-login|${address}`),
  );
  return bytesToBase64Url(new Uint8Array(digest));
}

async function login(request: Request, env: Env, now: number): Promise<Response> {
  const configuredUsername = String(env.ADMIN_USERNAME ?? "").trim();
  const configuredPassword = String(env.ADMIN_PASSWORD ?? "");
  if (!configuredUsername || !configuredPassword || !(await hmacKey(env))) {
    return json({ ok: false, code: "ADMIN_NOT_CONFIGURED", error: "管理员登录尚未配置" }, 503);
  }
  const declaredLength = Number(request.headers.get("content-length") ?? 0);
  if (declaredLength > 4096) return json({ ok: false, error: "请求过大" }, 413);
  let input: Record<string, unknown>;
  try {
    input = await request.json<Record<string, unknown>>();
  } catch {
    return json({ ok: false, error: "请求格式无效" }, 400);
  }
  const username = String(input.username ?? "").trim().slice(0, 120);
  const password = String(input.password ?? "").slice(0, 240);
  const clientKey = await loginClientKey(request);
  const valid = constantTimeEqual(username, configuredUsername)
    && constantTimeEqual(password, configuredPassword);
  // The switch is an outage control: logging in must not spend depleted D1
  // map writes either. Preserve the same five-attempt/ten-minute lock policy.
  const limitResponse = await env.RUNTIME_CONFIG.getByName(`admin-login:${clientKey}`).fetch(
    "https://config.internal/login-attempt", { method: "POST", body: JSON.stringify({ valid }) },
  );
  if (!limitResponse.ok) throw new RequestError("登录保护暂不可用", 503, "ADMIN_UNAVAILABLE");
  const limit = await limitResponse.json<{ limited: boolean; retryAfterMillis: number }>();
  if (limit.limited) return json({ ok: false, code: "LOGIN_RATE_LIMITED",
    error: "登录失败次数过多，请10分钟后再试", retryAfterMillis: limit.retryAfterMillis }, 429);
  if (!valid) return json({ ok: false, code: "INVALID_CREDENTIALS", error: "账号或密码错误" }, 401);
  const session = await issueSession(configuredUsername, env, now);
  return json(
    { ok: true, username: configuredUsername, expiresInSeconds: SESSION_MAX_AGE_SECONDS },
    200,
    {
      "set-cookie": `${ADMIN_COOKIE}=${session}; Path=/; Max-Age=${SESSION_MAX_AGE_SECONDS}; HttpOnly; Secure; SameSite=Strict`,
    },
  );
}

function clearSession(): Response {
  return json({ ok: true }, 200, {
    "set-cookie": `${ADMIN_COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict`,
  });
}

function maskedActor(value: unknown): string {
  const actor = String(value ?? "");
  return actor.length >= 14 ? `${actor.slice(0, 6)}…${actor.slice(-4)}` : actor;
}

function scope(platformKey: string, serverKey: string): string {
  return JSON.stringify([platformKey, serverKey]);
}

interface MapSummary {
  targetCount: number;
  regionCount: number;
  activeLeaseCount: number;
  lastScannedAtMillis: number;
  statuses: Record<string, number>;
}

function emptyMapSummary(): MapSummary {
  return {
    targetCount: 0,
    regionCount: 0,
    activeLeaseCount: 0,
    lastScannedAtMillis: 0,
    statuses: {},
  };
}

async function overview(env: Env, now: number): Promise<Response> {
  const settings = policy(env);
  const [catalog, presences, targets, regions, leases] = await env.DB.batch([
    env.DB.prepare(
      `SELECT d.platform_key,d.server_key,d.area_id,d.area_name,d.game_http,
              d.first_seen_at,d.last_directory_sync_at,
              c.last_seen_at,c.observation_count
       FROM server_directory d
       LEFT JOIN server_catalog c
         ON c.platform_key=d.platform_key AND c.server_key=d.server_key
       ORDER BY COALESCE(c.last_seen_at,d.last_directory_sync_at) DESC LIMIT 1000`,
    ),
    env.DB.prepare(
      `SELECT server_key,COUNT(DISTINCT actor_id) AS online_count,MAX(last_seen_at) AS last_seen_at
       FROM presence WHERE last_seen_at>=? GROUP BY server_key`,
    ).bind(now - settings.presenceTtlMillis),
    env.DB.prepare(
      `SELECT server_key,map_kind,status,COUNT(*) AS count,MAX(last_seen_at) AS last_seen_at
       FROM map_targets
       WHERE (map_kind='bandit' AND last_seen_at>=?)
          OR (map_kind='mine' AND last_seen_at>=?)
       GROUP BY server_key,map_kind,status`,
    ).bind(now - BANDIT_TTL_MILLIS, now - MINE_TTL_MILLIS),
    env.DB.prepare(
      `SELECT server_key,map_kind,COUNT(*) AS count,MAX(scanned_at) AS last_scanned_at
       FROM map_regions
       WHERE (map_kind='bandit' AND scanned_at>=?)
          OR (map_kind='mine' AND scanned_at>=?)
       GROUP BY server_key,map_kind`,
    ).bind(now - BANDIT_TTL_MILLIS, now - MINE_TTL_MILLIS),
    env.DB.prepare(
      `SELECT server_key,map_kind,COUNT(*) AS count
       FROM map_scan_leases WHERE lease_until>? GROUP BY server_key,map_kind`,
    ).bind(now),
  ]);
  const presenceByScope = new Map<string, number>();
  for (const row of presences.results as Array<Record<string, unknown>>) {
    presenceByScope.set(String(row.server_key), Number(row.online_count ?? 0));
  }
  const summaries = new Map<string, { bandit: MapSummary; mine: MapSummary }>();
  const summaryFor = (serverScope: string) => {
    let value = summaries.get(serverScope);
    if (!value) {
      value = { bandit: emptyMapSummary(), mine: emptyMapSummary() };
      summaries.set(serverScope, value);
    }
    return value;
  };
  for (const row of targets.results as Array<Record<string, unknown>>) {
    const kind = String(row.map_kind) as MapKind;
    if (kind !== "bandit" && kind !== "mine") continue;
    const summary = summaryFor(String(row.server_key))[kind];
    const count = Number(row.count ?? 0);
    summary.targetCount += count;
    summary.statuses[String(row.status ?? "unknown")] = count;
  }
  for (const row of regions.results as Array<Record<string, unknown>>) {
    const kind = String(row.map_kind) as MapKind;
    if (kind !== "bandit" && kind !== "mine") continue;
    const summary = summaryFor(String(row.server_key))[kind];
    summary.regionCount = Number(row.count ?? 0);
    summary.lastScannedAtMillis = Number(row.last_scanned_at ?? 0);
  }
  for (const row of leases.results as Array<Record<string, unknown>>) {
    const kind = String(row.map_kind) as MapKind;
    if (kind !== "bandit" && kind !== "mine") continue;
    summaryFor(String(row.server_key))[kind].activeLeaseCount = Number(row.count ?? 0);
  }
  const servers = (catalog.results as Array<Record<string, unknown>>).map((row) => {
    const platformKey = String(row.platform_key);
    const serverKey = String(row.server_key);
    const serverScope = scope(platformKey, serverKey);
    const onlineAccountCount = presenceByScope.get(serverScope) ?? 0;
    return {
      platformKey,
      platformName: platformDisplayName(platformKey),
      serverKey,
      areaId: String(row.area_id ?? ""),
      areaName: String(row.area_name ?? ""),
      gameHttp: String(row.game_http ?? ""),
      firstSeenAtMillis: Number(row.first_seen_at ?? 0),
      lastSeenAtMillis: Number(row.last_seen_at ?? 0),
      observationCount: Number(row.observation_count ?? 0),
      lastDirectorySyncAtMillis: Number(row.last_directory_sync_at ?? 0),
      onlineAccountCount,
      threshold: settings.threshold,
      mode: onlineAccountCount >= settings.threshold ? "CLOUD_SHARED" : "LOCAL_ONLY",
      maps: summaries.get(serverScope) ?? { bandit: emptyMapSummary(), mine: emptyMapSummary() },
    };
  });
  return json({
    ok: true,
    generatedAtMillis: now,
    presenceTtlMillis: settings.presenceTtlMillis,
    threshold: settings.threshold,
    servers,
    totals: {
      serverCount: servers.length,
      onlineAccountCount: servers.reduce((total, row) => total + row.onlineAccountCount, 0),
      cloudSharedServerCount: servers.filter((row) => row.mode === "CLOUD_SHARED").length,
      banditTargetCount: servers.reduce((total, row) => total + row.maps.bandit.targetCount, 0),
      mineTargetCount: servers.reduce((total, row) => total + row.maps.mine.targetCount, 0),
      regionCount: servers.reduce(
        (total, row) => total + row.maps.bandit.regionCount + row.maps.mine.regionCount,
        0,
      ),
      activeLeaseCount: servers.reduce(
        (total, row) => total + row.maps.bandit.activeLeaseCount + row.maps.mine.activeLeaseCount,
        0,
      ),
    },
  });
}

function parsedTargetData(value: unknown): Record<string, unknown> {
  try {
    const parsed = JSON.parse(String(value ?? "{}"));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : {};
  } catch {
    return {};
  }
}

/** Re-project even legacy rows before returning them to an administrator. */
function adminTargetData(mapKind: MapKind, value: unknown): Record<string, unknown> {
  const source = parsedTargetData(value);
  const output: Record<string, unknown> = {};
  const copy = (keys: string[]) => {
    for (const key of keys) {
      if (source[key] !== undefined && source[key] !== null && source[key] !== "") {
        output[key] = source[key];
      }
    }
  };
  if (mapKind === "bandit") {
    copy(["name", "kind", "resource", "rewardDescription", "compositionCode", "dropCategories", "lootIds", "unitTypes", "composition"]);
  } else {
    copy([
      "name", "kind", "protocolKind", "ownerName", "ownerCountry", "description",
      "businessId", "typeCode", "rank", "detailFlag", "defenderCount", "amountA",
      "amountB", "storage", "productionPerHour", "valueJ", "valueK", "playerOccupied",
      "unoccupiedByPlayer", "isEmpty", "occupied", "hasDefenders",
    ]);
  }
  return output;
}

async function mapData(request: Request, env: Env, now: number): Promise<Response> {
  const url = new URL(request.url);
  const platformKey = String(url.searchParams.get("platformKey") ?? "").trim().slice(0, 80);
  const serverKey = String(url.searchParams.get("serverKey") ?? "").trim().slice(0, 240);
  const mapKind = String(url.searchParams.get("mapKind") ?? "bandit").trim() as MapKind;
  if (!platformKey || !serverKey) return json({ ok: false, error: "请选择区服" }, 400);
  if (mapKind !== "bandit" && mapKind !== "mine") {
    return json({ ok: false, error: "地图类型无效" }, 400);
  }
  const serverScope = scope(platformKey, serverKey);
  const settings = policy(env);
  const targetTtl = mapKind === "bandit" ? BANDIT_TTL_MILLIS : MINE_TTL_MILLIS;
  const [catalog, targets, regions, leases, presences] = await env.DB.batch([
    env.DB.prepare(
      `SELECT d.area_id,d.area_name,d.game_http,
              COALESCE(c.last_seen_at,0) AS last_seen_at,
              COALESCE(c.observation_count,0) AS observation_count,
              d.last_directory_sync_at
       FROM server_directory d
       LEFT JOIN server_catalog c
         ON c.platform_key=d.platform_key AND c.server_key=d.server_key
       WHERE d.platform_key=? AND d.server_key=?`,
    ).bind(platformKey, serverKey),
    env.DB.prepare(
      `SELECT target_id,x,y,target_type,level,data_json,last_seen_at,status,
              reserved_by,lease_until,retry_after,status_reason,status_at
       FROM map_targets
       WHERE server_key=? AND map_kind=? AND last_seen_at>=?
       ORDER BY last_seen_at DESC LIMIT 5000`,
    ).bind(serverScope, mapKind, now - targetTtl),
    env.DB.prepare(
      `SELECT scan_x,scan_y,scanned_at,observer_id
       FROM map_regions
       WHERE server_key=? AND map_kind=? AND scanned_at>=?
       ORDER BY scanned_at DESC LIMIT 5000`,
    ).bind(serverScope, mapKind, now - targetTtl),
    env.DB.prepare(
      `SELECT scan_x,scan_y,owner,lease_until
       FROM map_scan_leases
       WHERE server_key=? AND map_kind=? AND lease_until>?
       ORDER BY lease_until DESC LIMIT 1000`,
    ).bind(serverScope, mapKind, now),
    env.DB.prepare(
      `SELECT actor_id,last_seen_at FROM presence
       WHERE server_key=? AND last_seen_at>=?
       ORDER BY last_seen_at DESC LIMIT 1000`,
    ).bind(serverScope, now - settings.presenceTtlMillis),
  ]);
  const server = (catalog.results as Array<Record<string, unknown>>)[0];
  if (!server) return json({ ok: false, error: "区服不存在" }, 404);
  const online = presences.results as Array<Record<string, unknown>>;
  return json({
    ok: true,
    generatedAtMillis: now,
    mapKind,
    ttlMillis: targetTtl,
    bounds: { minX: 0, maxX: 186, minY: 0, maxY: mapKind === "bandit" ? 55 : 66 },
    server: {
      platformKey,
      serverKey,
      areaId: String(server.area_id ?? ""),
      areaName: String(server.area_name ?? ""),
      gameHttp: String(server.game_http ?? ""),
      lastSeenAtMillis: Number(server.last_seen_at ?? 0),
      observationCount: Number(server.observation_count ?? 0),
      onlineAccountCount: online.length,
      threshold: settings.threshold,
      mode: online.length >= settings.threshold ? "CLOUD_SHARED" : "LOCAL_ONLY",
    },
    onlineActors: online.map((row) => ({
      actor: maskedActor(row.actor_id),
      lastSeenAtMillis: Number(row.last_seen_at ?? 0),
    })),
    targets: (targets.results as Array<Record<string, unknown>>).map((row) => ({
      targetId: String(row.target_id),
      x: Number(row.x),
      y: Number(row.y),
      type: String(row.target_type ?? ""),
      level: row.level == null ? null : Number(row.level),
      data: adminTargetData(mapKind, row.data_json),
      lastSeenAtMillis: Number(row.last_seen_at ?? 0),
      remainingMillis: Math.max(0, Number(row.last_seen_at ?? 0) + targetTtl - now),
      status: String(row.status ?? "available"),
      reservedBy: maskedActor(row.reserved_by),
      leaseUntilMillis: Number(row.lease_until ?? 0),
      retryAfterMillis: Number(row.retry_after ?? 0),
      statusReason: String(row.status_reason ?? ""),
      statusAtMillis: Number(row.status_at ?? 0),
      selectedForAttack: ["reserved", "dispatching"].includes(String(row.status)),
    })),
    regions: (regions.results as Array<Record<string, unknown>>).map((row) => ({
      x: Number(row.scan_x),
      y: Number(row.scan_y),
      scannedAtMillis: Number(row.scanned_at ?? 0),
      observer: maskedActor(row.observer_id),
    })),
    scanLeases: (leases.results as Array<Record<string, unknown>>).map((row) => ({
      x: Number(row.scan_x),
      y: Number(row.scan_y),
      owner: maskedActor(row.owner),
      leaseUntilMillis: Number(row.lease_until ?? 0),
    })),
  });
}

export async function handleAdminRequest(
  request: Request,
  env: Env,
): Promise<Response | null> {
  const url = new URL(request.url);
  const path = url.pathname;
  if (request.method === "GET" && path === "/") return redirect("/admin/");
  if (request.method === "GET" && path === "/admin") return redirect("/admin/");
  if (!path.startsWith("/admin/")) return null;

  const now = Date.now();
  if (request.method === "POST" && path === "/admin/api/login") {
    return login(request, env, now);
  }
  if (request.method === "GET" && path === "/admin/api/session") {
    const username = await authenticatedUsername(request, env, now);
    return json({ ok: true, authenticated: Boolean(username), username });
  }
  if (request.method === "POST" && path === "/admin/api/logout") return clearSession();
  if (path.startsWith("/admin/api/")) {
    const username = await authenticatedUsername(request, env, now);
    if (!username) return json({ ok: false, code: "ADMIN_UNAUTHORIZED", error: "请先登录" }, 401);
    const payment = await handlePaymentAdmin(request, env, username);
    if (payment) return payment;
    const member = await handleMemberAdmin(request, env, username);
    if (member) return member;
    if (request.method === "GET" && path === "/admin/api/runtime-config") {
      return json({ ok: true, config: await runtimeConfig(env) });
    }
    if (request.method === "POST" && path === "/admin/api/runtime-config") {
      return json({ ok: true, config: await updateRuntimeConfig(request, env) });
    }
    if (request.method === "GET" && path === "/admin/api/overview") return overview(env, now);
    if (request.method === "GET" && path === "/admin/api/map") return mapData(request, env, now);
    throw new RequestError("管理员接口不存在", 404, "NOT_FOUND");
  }
  if (request.method !== "GET" && request.method !== "HEAD") {
    throw new RequestError("请求方法无效", 405, "METHOD_NOT_ALLOWED");
  }
  return adminAsset(request, env);
}
