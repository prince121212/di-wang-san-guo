import { createScheduledController, env, SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { observeRegions } from "../src/database";
import worker from "../src/index";
import type { Env as WorkerEnv } from "../src/types";

const TOKEN = "test-client-token";
const ACTOR_A = "a".repeat(64);
const ACTOR_B = "b".repeat(64);
const ACTOR_C = "c".repeat(64);

interface JsonResponse extends Record<string, unknown> {
  ok: boolean;
}

function identity(actorId = ACTOR_A, serverKey = "352") {
  return { platformKey: "sanguo", serverKey, actorId };
}

async function request(
  path: string,
  init: RequestInit = {},
): Promise<{ response: Response; json: JsonResponse }> {
  const response = await SELF.fetch(`https://worker.test${path}`, {
    ...init,
    headers: {
      authorization: `Bearer ${TOKEN}`,
      ...(init.body ? { "content-type": "application/json" } : {}),
      ...init.headers,
    },
  });
  return { response, json: await response.json<JsonResponse>() };
}

async function adminRequest(
  path: string,
  init: RequestInit = {},
): Promise<{ response: Response; json: JsonResponse }> {
  const response = await SELF.fetch(`https://worker.test${path}`, {
    ...init,
    headers: {
      ...(init.body ? { "content-type": "application/json" } : {}),
      ...init.headers,
    },
  });
  return { response, json: await response.json<JsonResponse>() };
}

async function adminLogin(
  username = "test-admin",
  password = "test-password",
  address = "203.0.113.10",
) {
  const result = await adminRequest("/admin/api/login", {
    method: "POST",
    headers: { "cf-connecting-ip": address },
    body: JSON.stringify({ username, password }),
  });
  return {
    ...result,
    cookie: String(result.response.headers.get("set-cookie") ?? "").split(";", 1)[0],
  };
}

function post(path: string, payload: Record<string, unknown>) {
  return request(path, { method: "POST", body: JSON.stringify(payload) });
}

async function heartbeat(actorId: string, serverKey = "352") {
  return post("/v1/presence/heartbeat", {
    ...identity(actorId, serverKey),
    server: {
      areaId: serverKey,
      areaName: `区${serverKey}`,
      gameHttp: "http://user:password@game.example/path?session=secret#fragment",
    },
  });
}

async function enableSharedMode(serverKey = "352") {
  await heartbeat(ACTOR_A, serverKey);
  return heartbeat(ACTOR_B, serverKey);
}

function observation(
  actorId: string,
  mapKind: "bandit" | "mine" = "bandit",
  targets: Array<Record<string, unknown>> = [],
  extra: Record<string, unknown> = {},
) {
  return post("/v1/maps/observations", {
    ...identity(actorId),
    mapKind,
    regions: [{ x: 84, y: 22, targets, ...extra }],
  });
}

describe("shared cloud data boundary", () => {
  it("keeps health public and every other route authenticated", async () => {
    const health = await SELF.fetch("https://worker.test/health");
    expect(health.status).toBe(200);
    expect(await health.json()).toMatchObject({ ok: true, schemaVersion: 1 });

    const unauthorized = await SELF.fetch("https://worker.test/v1/servers/catalog");
    expect(unauthorized.status).toBe(401);
    expect(await unauthorized.json()).toMatchObject({ code: "UNAUTHORIZED" });
  });

  it("counts distinct anonymous accounts, not repeated heartbeats", async () => {
    const first = await heartbeat(ACTOR_A);
    expect(first.json).toMatchObject({ mode: "LOCAL_ONLY", onlineAccountCount: 1 });

    const repeated = await heartbeat(ACTOR_A);
    expect(repeated.json).toMatchObject({ mode: "LOCAL_ONLY", onlineAccountCount: 1 });

    const second = await heartbeat(ACTOR_B);
    expect(second.json).toMatchObject({ mode: "CLOUD_SHARED", onlineAccountCount: 2 });
  });

  it("isolates presence thresholds by platform and server", async () => {
    await heartbeat(ACTOR_A, "352");
    await heartbeat(ACTOR_B, "353");
    const stillLocal = await heartbeat(ACTOR_C, "354");
    expect(stillLocal.json).toMatchObject({ mode: "LOCAL_ONLY", onlineAccountCount: 1 });

    const mapRequest = await post("/v1/maps/targets/query", {
      ...identity(ACTOR_A, "352"),
      mapKind: "bandit",
    });
    expect(mapRequest.json).toMatchObject({ code: "SHARED_MODE_INACTIVE" });
  });

  it("requires a SHA-256 actor id", async () => {
    const result = await post("/v1/presence/heartbeat", {
      ...identity("1608601"),
      server: {},
    });
    expect(result.response.status).toBe(400);
    expect(result.json.error).toContain("SHA-256");
  });

  it("stores only public server catalog fields and strips URL credentials/query", async () => {
    await heartbeat(ACTOR_A);
    const result = await request("/v1/servers/catalog?platformKey=sanguo");
    expect(result.response.status).toBe(200);
    expect(result.json.servers).toEqual([
      expect.objectContaining({
        platformKey: "sanguo",
        serverKey: "352",
        areaId: "352",
        areaName: "区352",
        gameHttp: "http://game.example/path",
      }),
    ]);
    expect(JSON.stringify(result.json)).not.toContain("password");
    expect(JSON.stringify(result.json)).not.toContain("session=secret");
  });

  it("syncs a complete public platform directory independently from heartbeats", async () => {
    const synced = await post("/v1/servers/directory/sync", {
      platformKey: "sanguo",
      areas: [
        {
          serverKey: "351",
          areaId: "area-351",
          areaName: "周年服351区",
          target: "1,3",
          gameHttp: "http://user:password@game351.example/base?session=secret#fragment",
          password: "must-not-persist",
        },
        {
          serverKey: "352",
          areaId: "area-352",
          areaName: "周年服352区",
          gameHttp: "http://game352.example/base",
        },
      ],
    });
    expect(synced.response.status).toBe(200);
    expect(synced.json).toMatchObject({ platformKey: "sanguo", count: 2 });

    const catalog = await request("/v1/servers/catalog?platformKey=sanguo");
    expect(catalog.json.servers).toEqual(expect.arrayContaining([
      expect.objectContaining({
        serverKey: "351",
        areaName: "周年服351区",
        gameHttp: "http://game351.example/base",
        lastSeenAtMillis: 0,
        observationCount: 0,
      }),
      expect.objectContaining({ serverKey: "352", areaName: "周年服352区" }),
    ]));
    expect(JSON.stringify(catalog.json)).not.toContain("password");
    expect(JSON.stringify(catalog.json)).not.toContain("session=secret");

    // A later complete snapshot removes stale rows for that platform only.
    await post("/v1/servers/directory/sync", {
      platformKey: "sanguo",
      areas: [{ serverKey: "352", areaName: "周年服352区", gameHttp: "" }],
    });
    const refreshed = await request("/v1/servers/catalog?platformKey=sanguo");
    expect((refreshed.json.servers as Array<Record<string, unknown>>).map(row => row.serverKey))
      .toEqual(["352"]);
  });

  it("returns the latest add-account directory for exactly one selected platform", async () => {
    await post("/v1/servers/directory/sync", {
      platformKey: "sanguo",
      areas: [{
        serverKey: "351",
        areaId: "area-351",
        areaName: "周年服351区",
        target: "1,3",
        gameHttp: "https://game351.example/base",
      }],
    });
    await post("/v1/servers/directory/sync", {
      platformKey: "downjoy",
      areas: [{
        serverKey: "1025",
        areaName: "双线1025区",
        gameHttp: "https://game1025.example/base",
      }],
    });

    const result = await post("/v1/servers/directory/query", {
      platformKey: "sanguo",
    });
    expect(result.response.status).toBe(200);
    expect(result.json).toMatchObject({
      ok: true,
      platformKey: "sanguo",
      platform: "sanguo",
      count: 1,
      areas: [{
        serverKey: "351",
        areaId: "area-351",
        areaName: "周年服351区",
        target: "1,3",
        serverUrl: "https://game351.example/base",
      }],
    });
    expect(JSON.stringify(result.json)).not.toContain("1025");
  });

  it("rejects empty or oversized directory snapshots without deleting existing data", async () => {
    await heartbeat(ACTOR_A);
    const invalid = await post("/v1/servers/directory/sync", {
      platformKey: "sanguo",
      areas: [],
    });
    expect(invalid.response.status).toBe(400);
    const catalog = await request("/v1/servers/catalog?platformKey=sanguo");
    expect(catalog.json.servers).toEqual([
      expect.objectContaining({ serverKey: "352" }),
    ]);
  });

  it("rejects every map read and mutation below two online accounts", async () => {
    await heartbeat(ACTOR_A);
    const scope = JSON.stringify(["sanguo", "352"]);
    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO map_regions(server_key,map_kind,scan_x,scan_y,scanned_at,observer_id)
         VALUES(?,?,?,?,?,?)`,
      ).bind(scope, "bandit", 1, 1, Date.now(), ACTOR_A),
      env.DB.prepare(
        `INSERT INTO map_scan_leases(
           server_key,map_kind,scan_x,scan_y,owner,lease_token,lease_until
         ) VALUES(?,?,?,?,?,?,?)`,
      ).bind(scope, "bandit", 2, 2, ACTOR_A, "existing-lease", Date.now() + 60_000),
    ]);

    const calls: Array<[string, Record<string, unknown>]> = [
      ["/v1/maps/targets/query", { mapKind: "bandit" }],
      ["/v1/maps/scans/claim", { mapKind: "bandit", coordinates: [{ x: 3, y: 3 }] }],
      ["/v1/maps/scans/release", { mapKind: "bandit", leaseTokens: ["existing-lease"] }],
      ["/v1/maps/observations", { mapKind: "bandit", regions: [{ x: 4, y: 4, targets: [] }] }],
      ["/v1/maps/targets/reserve", { mapKind: "bandit", targetId: "missing" }],
      ["/v1/maps/targets/status", {
        mapKind: "bandit", targetId: "missing", reservationToken: "token", status: "available",
      }],
    ];
    for (const [path, payload] of calls) {
      const result = await post(path, { ...identity(), ...payload });
      expect(result.response.status, path).toBe(409);
      expect(result.json, path).toMatchObject({ code: "SHARED_MODE_INACTIVE" });
    }

    const regions = await env.DB.prepare("SELECT COUNT(*) count FROM map_regions").first<{ count: number }>();
    const leases = await env.DB.prepare("SELECT lease_token FROM map_scan_leases").all();
    const targets = await env.DB.prepare("SELECT COUNT(*) count FROM map_targets").first<{ count: number }>();
    expect(Number(regions?.count)).toBe(1);
    expect(leases.results).toEqual([expect.objectContaining({ lease_token: "existing-lease" })]);
    expect(Number(targets?.count)).toBe(0);
  });

  it("requires the calling actor to have a fresh heartbeat", async () => {
    await enableSharedMode();
    const result = await post("/v1/maps/targets/query", {
      ...identity(ACTOR_C),
      mapKind: "bandit",
    });
    expect(result.response.status).toBe(409);
    expect(result.json).toMatchObject({ code: "PRESENCE_REQUIRED" });
  });

  it("projects bandit fields through a closed whitelist", async () => {
    await enableSharedMode();
    const uploaded = await observation(ACTOR_A, "bandit", [{
      targetId: "000000000001abcd",
      x: 86,
      y: 26,
      type: "山贼",
      level: 8,
      data: {
        name: "8级山贼",
        dropCategories: ["资源", "装备"],
        composition: { foot: 1, bow: 2, cavalry: 3, chariot: 4, raw: "secret" },
        password: "must-not-persist",
        session: "must-not-persist",
        rawPayload: "deadbeef",
      },
    }]);
    expect(uploaded.response.status).toBe(200);

    const queried = await post("/v1/maps/targets/query", {
      ...identity(ACTOR_B),
      mapKind: "bandit",
    });
    expect(queried.response.status).toBe(200);
    expect(queried.json.targets).toEqual([
      expect.objectContaining({
        targetId: "000000000001abcd",
        data: {
          name: "8级山贼",
          dropCategories: ["资源", "装备"],
          composition: { foot: 1, bow: 2, cavalry: 3, chariot: 4 },
        },
      }),
    ]);
    const stored = await env.DB.prepare("SELECT data_json FROM map_targets").first<{ data_json: string }>();
    expect(stored?.data_json).not.toContain("password");
    expect(stored?.data_json).not.toContain("session");
    expect(stored?.data_json).not.toContain("rawPayload");
  });

  it("supports normalized mine observations without accepting private fields", async () => {
    await enableSharedMode();
    await observation(ACTOR_A, "mine", [{
      targetId: "0000000000001234",
      x: 10,
      y: 11,
      type: "农场",
      level: 5,
      data: {
        businessId: 123,
        typeCode: 5,
        playerOccupied: false,
        defenderCount: 2,
        ownerName: "地图公开占领者",
        taskLedger: { local: true },
      },
    }]);
    const result = await post("/v1/maps/targets/query", {
      ...identity(ACTOR_B),
      mapKind: "mine",
    });
    expect(result.json.targets).toEqual([
      expect.objectContaining({
        type: "农场",
        data: {
          businessId: 123,
          typeCode: 5,
          playerOccupied: false,
          defenderCount: 2,
          ownerName: "地图公开占领者",
        },
      }),
    ]);
    expect(JSON.stringify(result.json)).not.toContain("taskLedger");
  });
});

describe("administrator dashboard", () => {
  it("redirects the root to the administrator page and serves secured assets", async () => {
    const root = await SELF.fetch("https://worker.test/", { redirect: "manual" });
    expect(root.status).toBe(302);
    expect(root.headers.get("location")).toBe("/admin/");

    const page = await SELF.fetch("https://worker.test/admin/");
    expect(page.status).toBe(200);
    expect(page.headers.get("content-security-policy")).toContain("frame-ancestors 'none'");
    expect(await page.text()).toContain("共享数据管理");
  });

  it("uses an HttpOnly signed session and keeps admin data unavailable before login", async () => {
    const blocked = await adminRequest("/admin/api/overview");
    expect(blocked.response.status).toBe(401);
    expect(blocked.json).toMatchObject({ code: "ADMIN_UNAUTHORIZED" });

    const invalid = await adminLogin("test-admin", "wrong-password", "203.0.113.11");
    expect(invalid.response.status).toBe(401);
    expect(invalid.response.headers.get("set-cookie")).toBeNull();

    const login = await adminLogin("test-admin", "test-password", "203.0.113.12");
    expect(login.response.status).toBe(200);
    const setCookie = String(login.response.headers.get("set-cookie"));
    expect(setCookie).toContain("__Host-dwpm_admin=");
    expect(setCookie).toContain("HttpOnly");
    expect(setCookie).toContain("Secure");
    expect(setCookie).toContain("SameSite=Strict");

    const session = await adminRequest("/admin/api/session", {
      headers: { cookie: login.cookie },
    });
    expect(session.json).toMatchObject({
      ok: true,
      authenticated: true,
      username: "test-admin",
    });
  });

  it("rate limits repeated bad passwords without exposing which credential failed", async () => {
    const address = "203.0.113.13";
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const result = await adminLogin("unknown", "wrong", address);
      expect(result.response.status).toBe(401);
      expect(result.json.error).toBe("账号或密码错误");
    }
    const limited = await adminLogin("test-admin", "test-password", address);
    expect(limited.response.status).toBe(429);
    expect(limited.json).toMatchObject({ code: "LOGIN_RATE_LIMITED" });
  });

  it("projects a read-only overview and masked map coordination data", async () => {
    await enableSharedMode();
    await observation(ACTOR_A, "bandit", [{
      targetId: "admin-target",
      x: 86,
      y: 26,
      type: "山贼",
      level: 8,
      data: {
        name: "8级山贼",
        dropCategories: ["资源", "装备"],
        compositionCode: "1200",
      },
    }]);
    const reserved = await post("/v1/maps/targets/reserve", {
      ...identity(ACTOR_A), mapKind: "bandit", targetId: "admin-target",
    });
    expect(reserved.json.reserved).toBe(true);
    const login = await adminLogin("test-admin", "test-password", "203.0.113.14");

    const overview = await adminRequest("/admin/api/overview", {
      headers: { cookie: login.cookie },
    });
    expect(overview.response.status).toBe(200);
    expect(overview.json.totals).toMatchObject({
      serverCount: 1,
      onlineAccountCount: 2,
      cloudSharedServerCount: 1,
      banditTargetCount: 1,
    });

    const map = await adminRequest(
      "/admin/api/map?platformKey=sanguo&serverKey=352&mapKind=bandit",
      { headers: { cookie: login.cookie } },
    );
    expect(map.response.status).toBe(200);
    expect(map.json.targets).toEqual([
      expect.objectContaining({
        targetId: "admin-target",
        status: "reserved",
        selectedForAttack: true,
        reservedBy: expect.stringContaining("…"),
        data: expect.objectContaining({ compositionCode: "1200" }),
      }),
    ]);
    const encoded = JSON.stringify(map.json);
    expect(encoded).not.toContain(ACTOR_A);
    expect(encoded).not.toContain(String(reserved.json.reservationToken));
  });

  it("lists offline directory servers with zero runtime state", async () => {
    await post("/v1/servers/directory/sync", {
      platformKey: "sanguo",
      areas: [
        { serverKey: "351", areaName: "周年服351区", gameHttp: "http://351.example" },
        { serverKey: "352", areaName: "周年服352区", gameHttp: "http://352.example" },
      ],
    });
    await heartbeat(ACTOR_A, "352");
    const login = await adminLogin("test-admin", "test-password", "203.0.113.15");
    const overview = await adminRequest("/admin/api/overview", {
      headers: { cookie: login.cookie },
    });
    expect(overview.json.totals).toMatchObject({ serverCount: 2, onlineAccountCount: 1 });
    expect(overview.json.servers).toEqual(expect.arrayContaining([
      expect.objectContaining({
        serverKey: "351",
        onlineAccountCount: 0,
        observationCount: 0,
        mode: "LOCAL_ONLY",
      }),
      expect.objectContaining({ serverKey: "352", onlineAccountCount: 1 }),
    ]));

    const map = await adminRequest(
      "/admin/api/map?platformKey=sanguo&serverKey=351&mapKind=bandit",
      { headers: { cookie: login.cookie } },
    );
    expect(map.response.status).toBe(200);
    expect(map.json).toMatchObject({ targets: [], regions: [], scanLeases: [] });
  });

  it("annotates overview rows with their game platform display name", async () => {
    await post("/v1/servers/directory/sync", {
      platformKey: "sglm",
      areas: [{ serverKey: "352", areaName: "周年服352区", gameHttp: "" }],
    });
    await post("/v1/servers/directory/sync", {
      platformKey: "downjoy",
      areas: [{ serverKey: "1025", areaName: "双线1025区", gameHttp: "" }],
    });
    const login = await adminLogin("test-admin", "test-password", "203.0.113.16");
    const overview = await adminRequest("/admin/api/overview", {
      headers: { cookie: login.cookie },
    });
    expect(overview.json.servers).toEqual(expect.arrayContaining([
      expect.objectContaining({ platformKey: "sglm", platformName: "热血三国联盟" }),
      expect.objectContaining({ platformKey: "downjoy", platformName: "当乐帝王三国" }),
    ]));
  });
});

describe("scan and target concurrency", () => {
  it("allows exactly one actor to claim the same scan coordinate", async () => {
    await enableSharedMode();
    const payload = { mapKind: "bandit", coordinates: [{ x: 84, y: 22 }] };
    const [left, right] = await Promise.all([
      post("/v1/maps/scans/claim", { ...identity(ACTOR_A), ...payload }),
      post("/v1/maps/scans/claim", { ...identity(ACTOR_B), ...payload }),
    ]);
    const winners = [left, right].filter((result) => (result.json.scans as unknown[]).length === 1);
    expect(winners).toHaveLength(1);
    const rows = await env.DB.prepare("SELECT * FROM map_scan_leases").all();
    expect(rows.results).toHaveLength(1);
  });

  it("consumes a matching scan lease and skips a fresh region", async () => {
    await enableSharedMode();
    const claimed = await post("/v1/maps/scans/claim", {
      ...identity(ACTOR_A), mapKind: "bandit", coordinates: [{ x: 84, y: 22 }],
    });
    const leaseToken = ((claimed.json.scans as Array<{ leaseToken: string }>)[0]).leaseToken;
    await observation(ACTOR_A, "bandit", [], { leaseToken });
    const second = await post("/v1/maps/scans/claim", {
      ...identity(ACTOR_B), mapKind: "bandit", coordinates: [{ x: 84, y: 22 }],
    });
    expect(second.json.scans).toEqual([]);
    const leaseCount = await env.DB.prepare("SELECT COUNT(*) count FROM map_scan_leases").first<{ count: number }>();
    expect(Number(leaseCount?.count)).toBe(0);
  });

  it("allows exactly one actor to reserve a target and enforces its token", async () => {
    await enableSharedMode();
    await observation(ACTOR_A, "bandit", [{
      targetId: "target-1", x: 1, y: 2, type: "山贼", level: 7, data: {},
    }]);
    const [left, right] = await Promise.all([
      post("/v1/maps/targets/reserve", {
        ...identity(ACTOR_A), mapKind: "bandit", targetId: "target-1",
      }),
      post("/v1/maps/targets/reserve", {
        ...identity(ACTOR_B), mapKind: "bandit", targetId: "target-1",
      }),
    ]);
    const winners = [left, right].filter((result) => result.json.reserved === true);
    expect(winners).toHaveLength(1);

    const wrong = await post("/v1/maps/targets/status", {
      ...identity(ACTOR_A),
      mapKind: "bandit",
      targetId: "target-1",
      reservationToken: "wrong-token",
      status: "dispatching",
    });
    expect(wrong.response.status).toBe(409);

    const token = String(winners[0].json.reservationToken);
    const winnerActor = winners[0] === left ? ACTOR_A : ACTOR_B;
    const dispatching = await post("/v1/maps/targets/status", {
      ...identity(winnerActor),
      mapKind: "bandit",
      targetId: "target-1",
      reservationToken: token,
      status: "dispatching",
    });
    expect(dispatching.json).toMatchObject({ ok: true, updated: true, status: "dispatching" });
    const dispatched = await post("/v1/maps/targets/status", {
      ...identity(winnerActor),
      mapKind: "bandit",
      targetId: "target-1",
      reservationToken: token,
      status: "dispatched",
    });
    expect(dispatched.json).toMatchObject({ ok: true, updated: true, status: "dispatched" });
  });

  it("falls back immediately when the second presence expires", async () => {
    await enableSharedMode();
    const scope = JSON.stringify(["sanguo", "352"]);
    await env.DB.prepare(
      "UPDATE presence SET last_seen_at=? WHERE server_key=? AND actor_id=?",
    ).bind(Date.now() - 100_000, scope, ACTOR_B).run();

    const result = await post("/v1/maps/targets/query", {
      ...identity(ACTOR_A), mapKind: "bandit",
    });
    expect(result.response.status).toBe(409);
    expect(result.json).toMatchObject({ code: "SHARED_MODE_INACTIVE" });
  });

  it("recovers expired scan and reservation leases for another actor", async () => {
    await enableSharedMode();
    const firstScan = await post("/v1/maps/scans/claim", {
      ...identity(ACTOR_A), mapKind: "bandit", coordinates: [{ x: 84, y: 22 }],
    });
    const firstScanToken = String(
      (firstScan.json.scans as Array<{ leaseToken: string }>)[0].leaseToken,
    );
    await env.DB.prepare(
      "UPDATE map_scan_leases SET lease_until=? WHERE lease_token=?",
    ).bind(Date.now() - 1, firstScanToken).run();
    const recoveredScan = await post("/v1/maps/scans/claim", {
      ...identity(ACTOR_B), mapKind: "bandit", coordinates: [{ x: 84, y: 22 }],
    });
    expect(recoveredScan.json.scans).toEqual([
      expect.objectContaining({ x: 84, y: 22 }),
    ]);
    expect(String((recoveredScan.json.scans as Array<{ leaseToken: string }>)[0].leaseToken))
      .not.toBe(firstScanToken);

    await observation(ACTOR_A, "bandit", [{
      targetId: "lease-target", x: 84, y: 22, type: "山贼", level: 7, data: {},
    }]);
    const firstReservation = await post("/v1/maps/targets/reserve", {
      ...identity(ACTOR_A), mapKind: "bandit", targetId: "lease-target",
    });
    const firstReservationToken = String(firstReservation.json.reservationToken);
    await env.DB.prepare(
      "UPDATE map_targets SET lease_until=? WHERE target_id=?",
    ).bind(Date.now() - 1, "lease-target").run();
    const recoveredReservation = await post("/v1/maps/targets/reserve", {
      ...identity(ACTOR_B), mapKind: "bandit", targetId: "lease-target",
    });
    expect(recoveredReservation.json.reserved).toBe(true);
    expect(String(recoveredReservation.json.reservationToken)).not.toBe(firstReservationToken);
  });

  it("accepts only legal target transitions", async () => {
    await enableSharedMode();
    await observation(ACTOR_A, "bandit", [{
      targetId: "transition-target", x: 1, y: 2, type: "山贼", level: 7, data: {},
    }]);
    const reserved = await post("/v1/maps/targets/reserve", {
      ...identity(ACTOR_A), mapKind: "bandit", targetId: "transition-target",
    });
    const token = String(reserved.json.reservationToken);
    const dispatching = await post("/v1/maps/targets/status", {
      ...identity(ACTOR_A), mapKind: "bandit", targetId: "transition-target",
      reservationToken: token, status: "dispatching",
    });
    expect(dispatching.response.status).toBe(200);

    const repeatedDispatching = await post("/v1/maps/targets/status", {
      ...identity(ACTOR_A), mapKind: "bandit", targetId: "transition-target",
      reservationToken: token, status: "dispatching",
    });
    expect(repeatedDispatching.response.status).toBe(409);
    expect(repeatedDispatching.json).toMatchObject({ ok: false, updated: false });

    const uncertain = await post("/v1/maps/targets/status", {
      ...identity(ACTOR_A), mapKind: "bandit", targetId: "transition-target",
      reservationToken: token, status: "uncertain",
    });
    expect(uncertain.response.status).toBe(200);
    const backwards = await post("/v1/maps/targets/status", {
      ...identity(ACTOR_A), mapKind: "bandit", targetId: "transition-target",
      reservationToken: token, status: "dispatching",
    });
    expect(backwards.response.status).toBe(409);
    const resolved = await post("/v1/maps/targets/status", {
      ...identity(ACTOR_A), mapKind: "bandit", targetId: "transition-target",
      reservationToken: token, status: "dispatched",
    });
    expect(resolved.json).toMatchObject({ ok: true, status: "dispatched" });

    const invalid = await post("/v1/maps/targets/status", {
      ...identity(ACTOR_A), mapKind: "bandit", targetId: "transition-target",
      reservationToken: token, status: "available-again",
    });
    expect(invalid.response.status).toBe(400);
    expect(invalid.json.error).toContain("目标状态无效");
  });

  it("cron cleans expired state and observations reopen an expired uncertain target", async () => {
    await enableSharedMode();
    await observation(ACTOR_A, "bandit", [{
      targetId: "uncertain-target", x: 84, y: 22, type: "山贼", level: 7, data: {},
    }]);
    const reserved = await post("/v1/maps/targets/reserve", {
      ...identity(ACTOR_A), mapKind: "bandit", targetId: "uncertain-target",
    });
    const token = String(reserved.json.reservationToken);
    await post("/v1/maps/targets/status", {
      ...identity(ACTOR_A), mapKind: "bandit", targetId: "uncertain-target",
      reservationToken: token, status: "dispatching",
    });

    const now = Date.now();
    const scope = JSON.stringify(["sanguo", "352"]);
    await env.DB.batch([
      env.DB.prepare(
        "UPDATE map_targets SET lease_until=? WHERE target_id='uncertain-target'",
      ).bind(now - 1),
      env.DB.prepare(
        `INSERT INTO map_scan_leases(
           server_key,map_kind,scan_x,scan_y,owner,lease_token,lease_until
         ) VALUES(?,?,?,?,?,?,?)`,
      ).bind(scope, "bandit", 8, 8, ACTOR_A, "cron-expired-scan", now - 1),
      env.DB.prepare(
        `INSERT INTO presence(server_key,actor_id,last_seen_at) VALUES(?,?,?)
         ON CONFLICT(server_key,actor_id) DO UPDATE SET last_seen_at=excluded.last_seen_at`,
      ).bind(scope, ACTOR_C, now - 100_000),
    ]);

    await worker.scheduled(createScheduledController({
      cron: "*/5 * * * *",
      scheduledTime: new Date(now),
    }), env as unknown as WorkerEnv);
    const afterCron = await env.DB.prepare(
      "SELECT status,status_reason FROM map_targets WHERE target_id=?",
    ).bind("uncertain-target").first<{ status: string; status_reason: string }>();
    expect(afterCron).toMatchObject({
      status: "uncertain",
      status_reason: "dispatch lease expired",
    });
    expect(Number((await env.DB.prepare(
      "SELECT COUNT(*) count FROM map_scan_leases WHERE lease_token=?",
    ).bind("cron-expired-scan").first<{ count: number }>())?.count)).toBe(0);
    expect(Number((await env.DB.prepare(
      "SELECT COUNT(*) count FROM presence WHERE actor_id=?",
    ).bind(ACTOR_C).first<{ count: number }>())?.count)).toBe(0);

    await observation(ACTOR_A, "bandit", [{
      targetId: "uncertain-target", x: 84, y: 22, type: "山贼", level: 7, data: {},
    }]);
    const reopened = await env.DB.prepare(
      `SELECT status,reserved_by,reservation_token,lease_until
       FROM map_targets WHERE target_id=?`,
    ).bind("uncertain-target").first<{
      status: string;
      reserved_by: string;
      reservation_token: string;
      lease_until: number;
    }>();
    expect(reopened).toMatchObject({
      status: "available",
      reserved_by: "",
      reservation_token: "",
      lease_until: 0,
    });
  });
});

describe("D1 write scaling", () => {
  it("uses a fixed six statements for observations regardless of target count", async () => {
    const statementCounts: number[] = [];

    async function run(targetCount: number) {
      let prepared = 0;
      let batchSize = 0;
      const fakeStatement = {
        bind() { return this; },
      };
      const fakeDb = {
        prepare() {
          prepared += 1;
          return fakeStatement;
        },
        async batch(statements: unknown[]) {
          batchSize = statements.length;
          return [];
        },
      } as unknown as D1Database;
      await observeRegions(
        fakeDb,
        "scope",
        "bandit",
        ACTOR_A,
        [{
          x: 1,
          y: 2,
          leaseToken: "lease",
          targets: Array.from({ length: targetCount }, (_, index) => ({
            targetId: `target-${index}`,
            x: index,
            y: 2,
            type: "山贼",
            level: 1,
            data: {},
          })),
        }],
        Date.now(),
      );
      expect(prepared).toBe(6);
      expect(batchSize).toBe(6);
      statementCounts.push(prepared);
    }

    await run(1);
    await run(500);
    expect(statementCounts).toEqual([6, 6]);
  });
});
