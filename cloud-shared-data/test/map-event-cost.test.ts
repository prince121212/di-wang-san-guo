import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { applyGone, applyMapEvents, applyUpserts } from "../src/database";
import worker from "../src/index";
import type { Env, TargetObservation } from "../src/types";
import { upsertObservations } from "../src/validation";

const SCOPE = JSON.stringify(["sanguo", "352"]);
const ACTOR_A = "a".repeat(64);
const ACTOR_B = "b".repeat(64);

// Execute the real D1 SQL, recording its row costs and enforcing production's
// parameter limit. Local SQLite otherwise accepts too many bound parameters.
function meteredDatabase() {
  const results: D1Result[] = [];
  const bindCounts: number[] = [];
  const native = new WeakMap<D1PreparedStatement, D1PreparedStatement>();
  const wrap = (statement: D1PreparedStatement): D1PreparedStatement => {
    const wrapped = {
      bind(...values: unknown[]) {
        bindCounts.push(values.length);
        if (values.length > 100) throw new Error("D1 parameter limit exceeded");
        return wrap(statement.bind(...values));
      },
      async run() {
        const result = await statement.run();
        results.push(result);
        return result;
      },
      async all() {
        const result = await statement.all();
        results.push(result);
        return result;
      },
      first: statement.first.bind(statement),
      raw: statement.raw.bind(statement),
    } as D1PreparedStatement;
    native.set(wrapped, statement);
    return wrapped;
  };
  return {
    db: {
      prepare: (sql: string) => wrap(env.DB.prepare(sql)),
      async batch(statements: D1PreparedStatement[]) {
        const batch = await env.DB.batch(statements.map((s) => native.get(s) ?? s));
        results.push(...batch);
        return batch;
      },
    } as D1Database,
    results,
    bindCounts,
    writes: () => results.reduce((sum, result) => sum + result.meta.rows_written, 0),
    reads: () => results.reduce((sum, result) => sum + result.meta.rows_read, 0),
  };
}

function target(targetId = "event-target"): TargetObservation {
  return {
    targetId, x: 10, y: 11, type: "山贼", level: 7,
    data: { name: "7级山贼" },
  };
}

async function row(targetId = "event-target") {
  return env.DB.prepare(
    "SELECT * FROM map_targets WHERE server_key=? AND map_kind='bandit' AND target_id=?",
  ).bind(SCOPE, targetId).first<Record<string, unknown>>();
}

async function sharedPresence() {
  await env.DB.prepare(
    "INSERT INTO presence(server_key,actor_id,last_seen_at) VALUES(?,?,?),(?,?,?)",
  ).bind(SCOPE, ACTOR_A, Date.now(), SCOPE, ACTOR_B, Date.now()).run();
}

async function post(db: D1Database, path: string, payload: Record<string, unknown>) {
  return worker.fetch(new Request(`https://worker.test${path}`, {
    method: "POST",
    headers: {
      authorization: "Bearer test-client-token",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      platformKey: "sanguo", serverKey: "352", actorId: ACTOR_A,
      mapKind: "bandit", ...payload,
    }),
  }), { ...env, DB: db } as unknown as Env);
}

describe("event delivery cost and atomicity", () => {
  it("writes zero rows for 20 replays of an acknowledged 200-target batch", async () => {
    const now = Date.now();
    const targets = Array.from({ length: 200 }, (_, i) => target(`replay-${i}`));
    await applyUpserts(env.DB, SCOPE, "bandit", targets, now);
    const meter = meteredDatabase();

    for (let i = 1; i <= 20; i++) {
      await applyMapEvents(meter.db, SCOPE, "bandit", targets, [], now + i * 60_000);
    }
    expect(meter.writes()).toBe(0);
    expect(Math.max(...meter.bindCounts)).toBeLessThanOrEqual(100);
    expect(await row("replay-0")).toMatchObject({
      last_seen_at: now, changed_at: now,
    });
  });

  it.each([
    { x: 12 }, { y: 13 }, { type: "黄巾" }, { level: null }, { level: 9 },
    { data: { name: "changed" } },
  ])("does not delay a real field change: %j", async (change) => {
    const now = Date.now();
    await applyUpserts(env.DB, SCOPE, "bandit", [target()], now);
    const meter = meteredDatabase();
    await applyUpserts(meter.db, SCOPE, "bandit", [{ ...target(), ...change }], now + 1);
    expect(meter.writes()).toBeGreaterThan(0);
    expect(await row()).toMatchObject({ last_seen_at: now + 1, changed_at: now + 1 });
    meter.results.length = 0;
    await applyUpserts(meter.db, SCOPE, "bandit", [{ ...target(), ...change }], now + 2);
    expect(meter.writes()).toBe(0);
  });

  it("compares normalized facts, not empty text or input key ordering", async () => {
    const now = Date.now();
    await applyUpserts(env.DB, SCOPE, "bandit", upsertObservations([target()], "bandit"), now);
    const meter = meteredDatabase();
    await applyUpserts(meter.db, SCOPE, "bandit", upsertObservations([{
      ...target(), data: { rewardDescription: "", name: "7级山贼" },
    }], "bandit"), now + 1);
    expect(meter.writes()).toBe(0);
  });

  it("can renew an equal but expired sighting once without changing its lease", async () => {
    const now = Date.now();
    const old = now - 6 * 60 * 60 * 1_000 - 1;
    await applyUpserts(env.DB, SCOPE, "bandit", [target()], old);
    await env.DB.prepare(
      `UPDATE map_targets SET status='reserved',reserved_by='owner',
       reservation_token='keep',lease_until=? WHERE target_id='event-target'`,
    ).bind(now + 60_000).run();
    const meter = meteredDatabase();
    await applyUpserts(meter.db, SCOPE, "bandit", [target()], now);
    expect(meter.writes()).toBeGreaterThan(0);
    expect(await row()).toMatchObject({
      last_seen_at: now, changed_at: now, status: "reserved",
      reserved_by: "owner", reservation_token: "keep", lease_until: now + 60_000,
    });
    meter.results.length = 0;
    await applyUpserts(meter.db, SCOPE, "bandit", [target()], now + 1);
    expect(meter.writes()).toBe(0);
  });

  it.each(["reserved", "dispatching", "uncertain", "dispatched", "rejected"])(
    "preserves %s ownership when observations replay or change",
    async (status) => {
      const now = Date.now();
      await applyUpserts(env.DB, SCOPE, "bandit", [target()], now);
      await env.DB.prepare(
        `UPDATE map_targets SET status=?,reserved_by='owner',reservation_token='keep',
         lease_until=?,retry_after=?,status_at=? WHERE target_id='event-target'`,
      ).bind(status, now + 60_000, now + 120_000, now).run();
      const meter = meteredDatabase();
      await applyUpserts(meter.db, SCOPE, "bandit", [target()], now + 1);
      expect(meter.writes()).toBe(0);
      await applyUpserts(meter.db, SCOPE, "bandit", [{ ...target(), level: 9 }], now + 2);
      expect(await row()).toMatchObject({
        status, reserved_by: "owner", reservation_token: "keep",
        lease_until: now + 60_000, retry_after: now + 120_000, status_at: now,
        level: 9,
      });
    },
  );

  it.each(["missing", "uncertain"])("revives %s after its protection has ended", async (status) => {
    const now = Date.now();
    await applyUpserts(env.DB, SCOPE, "bandit", [target()], now);
    await env.DB.prepare(
      `UPDATE map_targets SET status=?,reserved_by='owner',reservation_token='old',
       lease_until=? WHERE target_id='event-target'`,
    ).bind(status, now).run();
    await applyUpserts(env.DB, SCOPE, "bandit", [target()], now + 1);
    expect(await row()).toMatchObject({
      status: "available", reserved_by: "", reservation_token: "", lease_until: 0,
      changed_at: now + 1,
    });
  });

  it("leaves a repeated tombstone and its change-feed version untouched", async () => {
    const now = Date.now();
    await applyUpserts(env.DB, SCOPE, "bandit", [target()], now);
    expect(await applyGone(env.DB, SCOPE, "bandit", ["event-target"], now + 1)).toBe(1);
    const meter = meteredDatabase();
    expect(await applyGone(meter.db, SCOPE, "bandit", ["event-target"], now + 60_000)).toBe(0);
    expect(meter.writes()).toBe(0);
    expect(await row()).toMatchObject({
      status: "missing", status_at: now + 1, changed_at: now + 1,
    });
  });

  it("deduplicates upsert IDs with last observation winning", async () => {
    const now = Date.now();
    await applyUpserts(env.DB, SCOPE, "bandit", [target()], now);
    const meter = meteredDatabase();
    await applyMapEvents(meter.db, SCOPE, "bandit", [
      { ...target(), level: 9 }, target(), target(),
    ], [], now + 1);
    expect(meter.writes()).toBe(0);
    expect(await row()).toMatchObject({ level: 7, changed_at: now });
  });

  it("acknowledges 200 upserts plus 200 tombstones atomically below the parameter limit", async () => {
    await sharedPresence();
    const gone = Array.from({ length: 200 }, (_, i) => `gone-${i}`);
    await applyUpserts(env.DB, SCOPE, "bandit", gone.map((id) => target(id)), Date.now());
    const targets = Array.from({ length: 200 }, (_, i) => target(`new-${i}`));
    const meter = meteredDatabase();
    const first = await post(meter.db, "/v1/maps/observations", { upserts: targets, gone });
    expect(await first.json()).toMatchObject({ ok: true, upsertedCount: 200, goneCount: 200 });
    expect(Math.max(...meter.bindCounts)).toBeLessThanOrEqual(100);
    meter.results.length = 0;
    const replay = await post(meter.db, "/v1/maps/observations", { upserts: targets, gone });
    expect(await replay.json()).toMatchObject({ ok: true, upsertedCount: 200, goneCount: 0 });
    expect(meter.writes()).toBe(0);
  });

  it("rolls back both upserts and tombstones if the final link cleanup fails", async () => {
    const now = Date.now();
    await applyUpserts(env.DB, SCOPE, "bandit", [target("gone"), target("existing")], now);
    await env.DB.prepare(
      "INSERT INTO map_regions VALUES(?,'bandit',1,2,?,'observer')",
    ).bind(SCOPE, now).run();
    await env.DB.prepare(
      "INSERT INTO map_target_regions VALUES(?,'bandit','gone',1,2,?)",
    ).bind(SCOPE, now).run();
    await env.DB.prepare(
      `CREATE TRIGGER event_batch_test_failure BEFORE DELETE ON map_target_regions
       BEGIN SELECT RAISE(ABORT, 'injected link cleanup failure'); END`,
    ).run();
    try {
      await expect(applyMapEvents(env.DB, SCOPE, "bandit", [
        target("new"), { ...target("existing"), level: 9 },
      ], ["gone"], now + 1)).rejects.toThrow("injected link cleanup failure");
      expect(await row("new")).toBeNull();
      expect(await row("existing")).toMatchObject({ level: 7, changed_at: now });
      expect(await row("gone")).toMatchObject({ status: "available", changed_at: now });
      expect(await env.DB.prepare("SELECT COUNT(*) n FROM map_target_regions").first("n")).toBe(1);
    } finally {
      await env.DB.prepare("DROP TRIGGER event_batch_test_failure").run();
    }
    expect(await applyMapEvents(env.DB, SCOPE, "bandit", [
      target("new"), { ...target("existing"), level: 9 },
    ], ["gone"], now + 2)).toBe(1);
    expect(await row("new")).not.toBeNull();
    expect(await row("existing")).toMatchObject({ level: 9 });
  });

  it("does no database work for an empty event batch", async () => {
    const meter = meteredDatabase();
    expect(await applyMapEvents(meter.db, SCOPE, "bandit", [], [], Date.now())).toBe(0);
    expect(meter.results).toEqual([]);
    expect(meter.bindCounts).toEqual([]);
  });
});

describe("indexed delta-feed cost", () => {
  async function seedLargeMap() {
    await sharedPresence();
    const now = Date.now();
    const ids = Array.from({ length: 5_000 }, (_, i) => `item-${String(i).padStart(5, "0")}`);
    await env.DB.prepare(
      `INSERT INTO map_targets(
         server_key,map_kind,target_id,x,y,data_json,last_seen_at,changed_at
       )
       SELECT ?,'bandit',CAST(value AS TEXT),1,2,'{}',?,? FROM json_each(?)`,
    ).bind(SCOPE, now, now, JSON.stringify(ids)).run();
    return now;
  }

  it("seeks past an exhausted cursor instead of reading the 5,000-row map", async () => {
    const now = await seedLargeMap();
    const meter = meteredDatabase();
    const response = await post(meter.db, "/v1/maps/targets/changes", {
      since: { changedAt: now, targetId: "item-04999" },
    });
    expect(await response.json()).toMatchObject({
      ok: true, targets: [], cursor: { changedAt: now, targetId: "item-04999" },
    });
    expect(meter.reads()).toBeLessThan(10);
  });

  it("seeks inside equal timestamps and still delivers every tombstone", async () => {
    const now = await seedLargeMap();
    await env.DB.prepare(
      "UPDATE map_targets SET status='missing' WHERE target_id='item-04999'",
    ).run();
    const meter = meteredDatabase();
    const first = await post(meter.db, "/v1/maps/targets/changes", {
      since: { changedAt: now, targetId: "item-04996" }, limit: 2,
    });
    const firstPage = await first.json<{
      targets: Array<{ targetId: string }>;
      cursor: { changedAt: number; targetId: string };
    }>();
    expect(firstPage.targets.map((r) => r.targetId)).toEqual(["item-04997", "item-04998"]);
    const second = await post(meter.db, "/v1/maps/targets/changes", {
      since: firstPage.cursor, limit: 2,
    });
    expect(await second.json()).toMatchObject({
      targets: [{ targetId: "item-04999", status: "missing" }],
      cursor: { changedAt: now, targetId: "item-04999" },
    });
    expect(meter.reads()).toBeLessThan(20);
  });
});
