import {
  cloudflareTest,
  readD1Migrations,
} from "@cloudflare/vitest-pool-workers";
import { defineConfig } from "vitest/config";

const migrationsPath = decodeURIComponent(new URL("./migrations", import.meta.url).pathname);
const migrations = await readD1Migrations(migrationsPath);

export default defineConfig({
  plugins: [
    cloudflareTest({
      wrangler: { configPath: "./wrangler.jsonc" },
      miniflare: {
        compatibilityDate: "2026-07-30",
        bindings: {
          CLIENT_API_TOKEN: "test-client-token",
          ADMIN_USERNAME: "test-admin",
          ADMIN_PASSWORD: "test-password",
          ADMIN_SESSION_SECRET: "test-session-secret-that-is-at-least-32-characters",
          TEST_MIGRATIONS: migrations,
        },
      },
    }),
  ],
  test: {
    setupFiles: ["./test/apply-migrations.ts"],
  },
});
