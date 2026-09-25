import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { applyGone } from "../src/database";

// Local SQLite can accept more variables than production D1. Enforce D1's
// documented 100-bound-parameters limit while still executing the real SQL.
function productionLimitDb(db: D1Database, bindCounts: number[]): D1Database {
  return {
    prepare(sql: string) {
      const statement = db.prepare(sql);
      return {
        bind(...values: unknown[]) {
          bindCounts.push(values.length);
          if (values.length > 100) {
            throw new Error(`D1 bound parameter limit: ${values.length} > 100`);
          }
          return statement.bind(...values);
        },
      };
    },
    batch: db.batch.bind(db),
  } as D1Database;
}

describe("gone event batches under production D1 limits", () => {
  it.each([96, 97, 200])(
    "tombstones %i IDs without a variable-count SQL query",
    async (count) => {
      const ids = Array.from({ length: count }, (_, index) => `gone-${index}`);
      const encoded = JSON.stringify(ids);
      const now = Date.now();
      for (const [scope, kind] of [
        ["scope-a", "bandit"],
        ["scope-b", "bandit"],
        ["scope-a", "mine"],
      ]) {
        await env.DB.prepare(
          `INSERT INTO map_regions(
             server_key,map_kind,scan_x,scan_y,scanned_at,observer_id
           ) VALUES(?,?,1,2,?,'test-actor')`,
        ).bind(scope, kind, now).run();
        await env.DB.prepare(
          `INSERT INTO map_targets(
             server_key,map_kind,target_id,x,y,target_type,level,data_json,
             last_seen_at,changed_at,status,reservation_token,lease_until
           )
           SELECT ?,?,CAST(value AS TEXT),1,2,'target',7,'{}',?,?,
             CASE key WHEN 0 THEN 'reserved' WHEN 1 THEN 'dispatching'
               ELSE 'available' END,
             'keep-token',?
           FROM json_each(?)`,
        ).bind(scope, kind, now - 1000, now - 1000, now + 60_000, encoded).run();
        await env.DB.prepare(
          `INSERT INTO map_target_regions(
             server_key,map_kind,target_id,scan_x,scan_y,last_seen_at
           )
           SELECT ?,?,CAST(value AS TEXT),1,2,? FROM json_each(?)`,
        ).bind(scope, kind, now, encoded).run();
      }

      const bindCounts: number[] = [];
      const changed = await applyGone(
        productionLimitDb(env.DB, bindCounts), "scope-a", "bandit", ids, now,
      );
      expect(changed).toBe(count - 2);
      expect(bindCounts).toHaveLength(2);
      expect(Math.max(...bindCounts)).toBeLessThanOrEqual(100);
      const rows = await env.DB.prepare(
        `SELECT target_id,status,changed_at,reservation_token,lease_until
         FROM map_targets WHERE server_key='scope-a' AND map_kind='bandit'`,
      ).all<{
        target_id: string;
        status: string;
        changed_at: number;
        reservation_token: string;
        lease_until: number;
      }>();
      for (const row of rows.results) {
        if (row.target_id === "gone-0" || row.target_id === "gone-1") {
          expect(row).toMatchObject({
            status: row.target_id === "gone-0" ? "reserved" : "dispatching",
            changed_at: now - 1000,
            reservation_token: "keep-token",
            lease_until: now + 60_000,
          });
        } else {
          expect(row.status).toBe("missing");
          expect(row.changed_at).toBe(now);
        }
      }
      expect((await env.DB.prepare(
        `SELECT COUNT(*) n FROM map_targets
         WHERE (server_key!='scope-a' OR map_kind!='bandit') AND status='missing'`,
      ).first<{ n: number }>())?.n).toBe(0);
      expect((await env.DB.prepare(
        `SELECT COUNT(*) n FROM map_target_regions
         WHERE server_key='scope-a' AND map_kind='bandit'`,
      ).first<{ n: number }>())?.n).toBe(0);
      expect((await env.DB.prepare(
        `SELECT COUNT(*) n FROM map_target_regions
         WHERE server_key!='scope-a' OR map_kind!='bandit'`,
      ).first<{ n: number }>())?.n).toBe(count * 2);
    },
  );

  it("does no SQL work for an empty event batch", async () => {
    const counts: number[] = [];
    expect(await applyGone(
      productionLimitDb(env.DB, counts), "scope-a", "bandit", [], Date.now(),
    )).toBe(0);
    expect(counts).toEqual([]);
  });
});
