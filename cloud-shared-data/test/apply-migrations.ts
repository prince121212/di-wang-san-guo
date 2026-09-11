import { applyD1Migrations, env } from "cloudflare:test";
import type { D1Migration } from "@cloudflare/vitest-pool-workers";
import { beforeEach } from "vitest";

declare global {
  namespace Cloudflare {
    interface Env {
      DB: D1Database;
      TEST_MIGRATIONS: D1Migration[];
    }
  }
}

await applyD1Migrations(env.DB, env.TEST_MIGRATIONS);

beforeEach(async () => {
  await env.DB.batch([
    env.DB.prepare("DELETE FROM map_target_regions"),
    env.DB.prepare("DELETE FROM map_scan_leases"),
    env.DB.prepare("DELETE FROM map_targets"),
    env.DB.prepare("DELETE FROM map_regions"),
    env.DB.prepare("DELETE FROM presence"),
    env.DB.prepare("DELETE FROM server_catalog"),
    env.DB.prepare("DELETE FROM server_directory"),
  ]);
});
