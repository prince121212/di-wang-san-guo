import {
  cloudflareTest,
  readD1Migrations,
} from "@cloudflare/vitest-pool-workers";
import { defineConfig } from "vitest/config";
import { generateKeyPairSync } from "node:crypto";
import { Buffer } from "node:buffer";
import { builtinModules } from "node:module";

const memberTestKeys = generateKeyPairSync("rsa", { modulusLength: 2048,
  publicKeyEncoding: { type: "spki", format: "der" }, privateKeyEncoding: { type: "pkcs8", format: "der" } });
const paymentTestKeys=generateKeyPairSync("rsa",{modulusLength:2048,
  publicKeyEncoding:{type:"spki",format:"der"},privateKeyEncoding:{type:"pkcs1",format:"der"}});

const migrationsPath = decodeURIComponent(new URL("./migrations", import.meta.url).pathname);
const migrations = await readD1Migrations(migrationsPath);

export default defineConfig({
  resolve: { alias: {
    urllib: decodeURIComponent(new URL("./src/alipay-http.ts", import.meta.url).pathname),
    "node:util":decodeURIComponent(new URL("./src/payment-node-util.ts",import.meta.url).pathname),
  } },
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
          RESEND_API_KEY: "re_test_email_probe_only",
          RESEND_FROM_EMAIL: "noreply@example.com",
          EMAIL_PROBE_TOKEN: "test-email-probe-token-at-least-32-characters",
          EMAIL_PROBE_TO: "probe@example.com",
          EMAIL_PROBE_UNTIL: "4102444800000",
          MEMBER_AUTH_SECRET: "test-member-auth-secret-not-for-production-at-least-32-chars",
          MEMBER_LEASE_PRIVATE_KEY: Buffer.from(memberTestKeys.privateKey).toString("base64"),
          MEMBER_LEASE_PUBLIC_KEY: Buffer.from(memberTestKeys.publicKey).toString("base64"),
          ALIPAY_ENABLED: "true", ALIPAY_MODE: "sandbox", ALIPAY_APP_ID: "2026000000000001",
          ALIPAY_LIVE_APPROVED: "false", ALIPAY_APP_PAY_ENABLED: "false",
          ALIPAY_SELLER_ID: "2088000000000001", ALIPAY_ORIGIN: "https://worker.test",
          ALIPAY_PRIVATE_KEY: Buffer.from(paymentTestKeys.privateKey).toString("base64"),
          ALIPAY_PUBLIC_KEY: Buffer.from(memberTestKeys.publicKey).toString("base64"),
          ALIPAY_PLAN_PRICES: JSON.stringify({month:"0.01",quarter:"0.02",year:"0.03"}),
          TEST_MIGRATIONS: migrations,
        },
      },
    }),
  ],
  test: {
    deps: { optimizer: { ssr: { enabled: true, include: ["alipay-sdk"], exclude: [...builtinModules, ...builtinModules.map(n => "node:" + n), "node:sqlite"] } } },
    testTimeout: 60_000, // Six real scrypt checks can exceed 30s on a busy build host.
    include: ["test/**/*.test.ts"],
    setupFiles: ["./test/apply-migrations.ts"],
  },
});
