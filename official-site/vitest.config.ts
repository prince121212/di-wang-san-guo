import { cloudflareTest } from "@cloudflare/vitest-pool-workers";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [
    cloudflareTest({
      wrangler: { configPath: "./wrangler.jsonc" },
      miniflare: { compatibilityDate: "2026-07-30" },
    }),
  ],
  test: { include: ["test/**/*.test.ts"] },
});
