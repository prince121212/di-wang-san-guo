import { env, SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import worker from "../src/index";
import type { Env } from "../src/types";

const clientHeaders = { authorization: "Bearer test-client-token" };
async function login() {
  const result = await SELF.fetch("https://worker.test/admin/api/login", {
    method: "POST", headers: { "content-type": "application/json", "cf-connecting-ip": "203.0.113.70" },
    body: JSON.stringify({ username: "test-admin", password: "test-password" }),
  });
  expect(result.status).toBe(200);
  return String(result.headers.get("set-cookie")).split(";", 1)[0];
}
async function current() {
  const result = await SELF.fetch("https://worker.test/v1/client/config", { method: "POST", headers: clientHeaders });
  expect(result.headers.get("cache-control")).toBe("no-store");
  return (await result.json<{ config: { revision: number; cloudBrushMapEnabled: boolean } }>()).config;
}
async function change(cookie: string, enabled: boolean, revision: number, extra: HeadersInit = {}) {
  return SELF.fetch("https://worker.test/admin/api/runtime-config", {
    method: "POST", headers: { cookie, "content-type": "application/json",
      origin: "https://worker.test", "x-admin-intent": "runtime-config", ...extra },
    body: JSON.stringify({ cloudBrushMapEnabled: enabled, expectedRevision: revision }),
  });
}

describe("cloud brush runtime control", () => {
  it("accepts additive runtime credentials without revoking legacy clients or granting admin writes", async () => {
    const configured = { ...env, CLIENT_API_TOKEN: "legacy-client", CLIENT_API_TOKEN_V2: "new-client" } as unknown as Env;
    for (const token of ["legacy-client", "new-client"]) {
      const result = await worker.fetch(new Request("https://worker.test/v1/servers/directory/query", {
        method: "POST", headers: { authorization: `Bearer ${token}` }, body:JSON.stringify({platformKey:"sglm"}),
      }), configured);
      expect(result.status).toBe(200);
      const admin = await worker.fetch(new Request("https://worker.test/admin/api/runtime-config", {
        method: "POST", headers: { authorization: `Bearer ${token}` },
      }), configured);
      expect(admin.status).toBe(401);
    }
    const denied = await worker.fetch(new Request("https://worker.test/v1/servers/directory/query", {
      method: "POST", headers: { authorization: "Bearer " },
    }), { ...configured, CLIENT_API_TOKEN: "", CLIENT_API_TOKEN_V2: "" });
    expect(denied.status).toBe(401);
  });
  it("keeps the global switch public-read-only and protects administrator writes", async () => {
    expect((await current()).cloudBrushMapEnabled).toBe(true);
    const response = await SELF.fetch("https://worker.test/v1/client/config", { method: "POST" });
    expect(response.status).toBe(200);
    expect((await change("", false, 0, clientHeaders)).status).toBe(401);
  });

  it("persists off/on and immediately returns the latest revision on startup reads", async () => {
    const cookie = await login();
    const before = await current();
    expect((await change(cookie, false, before.revision)).status).toBe(200);
    const disabled = await current();
    expect(disabled).toMatchObject({ cloudBrushMapEnabled: false, revision: before.revision + 1 });
    expect((await change(cookie, true, disabled.revision)).status).toBe(200);
    expect(await current()).toMatchObject({ cloudBrushMapEnabled: true, revision: before.revision + 2 });
  });

  it("rejects cross-origin requests, missing intent and string booleans", async () => {
    const cookie = await login();
    const before = await current();
    expect((await change(cookie, false, before.revision, { origin: "https://evil.test" })).status).toBe(403);
    expect((await change(cookie, false, before.revision, { "x-admin-intent": "" })).status).toBe(403);
    const invalid = await SELF.fetch("https://worker.test/admin/api/runtime-config", {
      method: "POST", headers: { cookie, origin: "https://worker.test",
        "x-admin-intent": "runtime-config", "content-type": "application/json" },
      body: JSON.stringify({ cloudBrushMapEnabled: "false", expectedRevision: before.revision }),
    });
    expect(invalid.status).toBe(400);
    expect(await current()).toEqual(before);
  });

  it("does not overwrite a newer administrator decision from a stale page", async () => {
    const cookie = await login();
    const before = await current();
    expect((await change(cookie, false, before.revision)).status).toBe(200);
    const stale = await change(cookie, true, before.revision);
    expect(stale.status).toBe(409);
    expect(await stale.json()).toMatchObject({ code: "CONFIG_REVISION_CONFLICT" });
    expect((await current()).cloudBrushMapEnabled).toBe(false);
  });

  it("keeps the control usable with D1 entirely unavailable and rejects old clients before D1", async () => {
    const cookie = await login();
    const before = await current();
    let dbCalls = 0;
    const broken = { ...env, CLIENT_API_TOKEN: "test-client-token", ADMIN_USERNAME: "test-admin",
      ADMIN_PASSWORD: "test-password",
      ADMIN_SESSION_SECRET: "test-session-secret-that-is-at-least-32-characters",
      DB: { prepare() { dbCalls++; throw new Error("D1 unavailable"); } } } as unknown as Env;
    const offlineLogin = await worker.fetch(new Request("https://worker.test/admin/api/login", {
      method: "POST", headers: { "content-type": "application/json", "cf-connecting-ip": "203.0.113.77" },
      body: JSON.stringify({ username: "test-admin", password: "test-password" }),
    }), broken);
    expect(offlineLogin.status).toBe(200);
    const changed = await worker.fetch(new Request("https://worker.test/admin/api/runtime-config", {
      method: "POST", headers: { cookie, origin: "https://worker.test", "x-admin-intent": "runtime-config",
        "content-type": "application/json" },
      body: JSON.stringify({ cloudBrushMapEnabled: false, expectedRevision: before.revision }),
    }), broken);
    expect(changed.status).toBe(200);
    const read = await worker.fetch(new Request("https://worker.test/v1/client/config", {
      method: "POST", headers: clientHeaders,
    }), broken);
    expect(await read.json()).toMatchObject({ config: { cloudBrushMapEnabled: false } });
    for (const path of ["/v1/maps/targets/reserve", "/v1/maps/observations", "/v1/maps/targets/sync"]) {
      const blocked = await worker.fetch(new Request(`https://worker.test${path}`, {
        method: "POST", headers: clientHeaders, body: JSON.stringify({ mapKind: "bandit" }),
      }), broken);
      expect(blocked.status).toBe(409);
      expect(await blocked.json()).toMatchObject({ code: "CLOUD_BRUSH_MAP_DISABLED" });
    }
    const heartbeat = await worker.fetch(new Request("https://worker.test/v1/presence/heartbeat", {
      method: "POST", headers: clientHeaders,
      body: JSON.stringify({ platformKey: "sglm", serverKey: "test", actorId: "a".repeat(64) }),
    }), broken);
    expect(await heartbeat.json()).toMatchObject({ mode: "LOCAL_ONLY" });
    expect(dbCalls).toBe(0);
  });

  it("exposes the accessible toggle in the administrator page", async () => {
    const page = await SELF.fetch("https://worker.test/admin/");
    const html = await page.text();
    expect(html).toContain('id="cloudBrushMapToggle"');
    expect(html).toContain('role="switch"');
  });
});
