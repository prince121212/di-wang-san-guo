import { env, runInDurableObject } from "cloudflare:test";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import worker from "../src/index";
import { emailProbeObjectName } from "../src/email-verification-probe";
import type { Env } from "../src/types";

const TOKEN = "test-email-probe-token-at-least-32-characters";
const EMAIL = "probe@example.com";
const calls: Array<{ text: string; to: string[]; from: string; subject: string }> = [];
const configured = env as unknown as Env;
let stub: DurableObjectStub;

async function api(action: string, input: Record<string, unknown>, token = TOKEN, workerEnv = configured) {
  const response = await worker.fetch(new Request(`https://worker.test/ops/email-verification/${action}`, {
    method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify({ email: EMAIL, ...input }),
  }), workerEnv);
  return { status: response.status, body: await response.json<Record<string, any>>() };
}
function send(requestId = crypto.randomUUID(), extra = {}) { return api("send", { requestId, ...extra }); }
function code() {
  const value = /验证码是：(\d{6})/.exec(calls.at(-1)!.text)?.[1];
  if (!value) throw new Error("test email did not contain a six-digit code");
  return value;
}
async function record() {
  return runInDurableObject(stub, (_instance, state) => state.storage.get<Record<string, any>>("emailChallenge"));
}
async function patchRecord(patch: Record<string, unknown>) {
  await runInDurableObject(stub, async (_instance, state) => {
    const current = await state.storage.get<Record<string, any>>("emailChallenge");
    await state.storage.put("emailChallenge", { ...current, ...patch });
  });
}

beforeEach(async () => {
  stub = env.RUNTIME_CONFIG.getByName(await emailProbeObjectName(EMAIL));
  await runInDurableObject(stub, async (_instance, state) => {
    await state.storage.deleteAll();
    await state.storage.deleteAlarm();
  });
  calls.length = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
    expect(String(url)).toBe("https://api.resend.com/emails");
    const headers = new Headers(init?.headers);
    expect(headers.get("Authorization")).toBe("Bearer re_test_email_probe_only");
    expect(headers.get("Idempotency-Key")).toMatch(/^dwpm-email-probe\//);
    calls.push(JSON.parse(String(init?.body)));
    return Response.json({ id: "test-resend-message-id" });
  });
});
afterEach(() => vi.restoreAllMocks());

describe("isolated email verification probe", () => {
  it("requires the operator token, not the token shipped in the APK", async () => {
    expect((await api("send", { requestId: crypto.randomUUID() }, "test-client-token")).status).toBe(401);
    expect((await api("send", { requestId: crypto.randomUUID() }, "")).status).toBe(401);
    expect(calls).toHaveLength(0);
  });

  it("is disabled without a time-bounded configuration", async () => {
    expect((await api("send", { requestId: crypto.randomUUID() }, TOKEN,
      { ...configured, EMAIL_PROBE_UNTIL: "0" })).status).toBe(404);
    expect((await api("send", { requestId: crypto.randomUUID() }, TOKEN,
      { ...configured, EMAIL_PROBE_TOKEN: "" })).status).toBe(404);
    expect(calls).toHaveLength(0);
  });

  it("normalizes the allowed address and never sends to arbitrary recipients", async () => {
    expect((await send(crypto.randomUUID(), { email: "other@example.com" })).status).toBe(403);
    expect(calls).toHaveLength(0);
    expect((await send(crypto.randomUUID(), { email: " PROBE@EXAMPLE.COM " })).status).toBe(200);
    expect(calls[0].to).toEqual([EMAIL]);
  });

  it("stores only a keyed code digest and returns no plaintext code", async () => {
    const result = await send();
    expect(result.status).toBe(200);
    expect(result.body).toMatchObject({ delivery: "accepted", verified: false, attemptsRemaining: 5 });
    expect(result.body.code).toBeUndefined();
    const saved = await record();
    expect(saved!.codeMac).toMatch(/^[a-f0-9]{64}$/);
    expect(saved!.code).toBeUndefined();
    expect(saved!.expiresAtMillis - saved!.createdAtMillis).toBe(15 * 60_000);
    expect(calls[0].from).toBe("帝王三国资料库 <noreply@example.com>");
    expect(calls[0].text).toContain("不会创建会员账号");
  });

  it("coalesces simultaneous/replayed send requests without duplicate emails", async () => {
    const id = crypto.randomUUID();
    const [a, b] = await Promise.all([send(id), send(id)]);
    expect(a.body.challengeId).toBe(b.body.challengeId);
    expect(calls).toHaveLength(1);
    expect((await send(id)).body.replayed).toBe(true);
    expect(calls).toHaveLength(1);
  });

  it("consumes a correct code atomically; concurrent use succeeds exactly once", async () => {
    const sent = await send();
    const input = { challengeId: sent.body.challengeId, code: code() };
    const results = await Promise.all([api("verify", input), api("verify", input)]);
    expect(results.map(r => r.status).sort()).toEqual([200, 409]);
    expect((await record())!.codeMac).toBe("");
    expect((await api("verify", input)).body.code).toBe("CODE_ALREADY_USED");
    expect((await send()).body.code).toBe("PROBE_COMPLETED");
    expect(calls).toHaveLength(1);
  });

  it("counts wrong codes and locks the challenge at five failures", async () => {
    const sent = await send();
    const valid = code();
    const wrong = valid === "000000" ? "000001" : "000000";
    for (let i = 0; i < 5; i++) {
      expect((await api("verify", { challengeId: sent.body.challengeId, code: wrong })).status).toBe(i === 4 ? 429 : 400);
    }
    expect((await api("verify", { challengeId: sent.body.challengeId, code: valid })).body.code).toBe("CODE_LOCKED");
    expect((await record())!.attempts).toBe(5);
  });

  it("rejects expired and superseded codes", async () => {
    const sent = await send();
    const valid = code();
    await patchRecord({ expiresAtMillis: Date.now() - 1 });
    expect((await api("verify", { challengeId: sent.body.challengeId, code: valid })).body.code).toBe("CODE_EXPIRED");
    expect((await api("verify", { challengeId: crypto.randomUUID(), code: valid })).body.code).toBe("CODE_NOT_FOUND");
  });

  it("enforces the shared cooldown and daily send budget", async () => {
    const first = await send();
    expect((await send()).body.code).toBe("SEND_COOLDOWN");
    for (let i = 0; i < 2; i++) {
      await patchRecord({ createdAtMillis: Date.now() - 61_000 });
      expect((await send()).status).toBe(200);
    }
    await patchRecord({ createdAtMillis: Date.now() - 61_000 });
    expect((await send()).body.code).toBe("SEND_LIMIT");
    expect(calls).toHaveLength(3);
    expect((await api("verify", { challengeId: first.body.challengeId, code: code() })).body.code).toBe("CODE_NOT_FOUND");
  });

  it("does not recreate an old send request after a newer request", async () => {
    const id = crypto.randomUUID();
    await send(id);
    await patchRecord({ createdAtMillis: Date.now() - 61_000 });
    await send();
    await patchRecord({ createdAtMillis: Date.now() - 61_000 });
    expect((await send(id)).body.code).toBe("REQUEST_ALREADY_USED");
    expect(calls).toHaveLength(2);
  });

  it("keeps timeouts uncertain and never automatically replays a send", async () => {
    vi.mocked(fetch).mockRejectedValue(new Error("network timeout"));
    const id = crypto.randomUUID();
    const first = await send(id);
    expect(first.body.code).toBe("EMAIL_SEND_UNCERTAIN");
    expect((await send(id)).body).toMatchObject({ replayed: true, delivery: "unknown" });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("allows an explicit new request after a rejected send and cooldown", async () => {
    vi.mocked(fetch).mockImplementation(async () => Response.json({ message: "bad provider config" }, { status: 422 }));
    const id = crypto.randomUUID();
    const result = await send(id);
    expect(result.body.code).toBe("EMAIL_SEND_FAILED");
    expect((await send(id)).status).toBe(502);
    await patchRecord({ createdAtMillis: Date.now() - 61_000 });
    vi.mocked(fetch).mockImplementation(async () => Response.json({ id: "retried-message" }));
    expect((await send()).status).toBe(200);
  });

  it("does not require a JSON error body to recognize a provider rejection", async () => {
    vi.mocked(fetch).mockImplementation(async () => new Response("rejected", { status: 400 }));
    expect((await send()).body.code).toBe("EMAIL_SEND_FAILED");
  });

  it("treats provider timeouts and idempotency conflicts as uncertain", async () => {
    for (const status of [408, 409, 503]) {
      await runInDurableObject(stub, (_instance, state) => state.storage.deleteAll());
      vi.mocked(fetch).mockImplementation(async () => new Response("not confirmed", { status }));
      expect((await send()).body.code).toBe("EMAIL_SEND_UNCERTAIN");
    }
  });

  it("keeps OTP storage independent of the map D1 database", async () => {
    const withoutD1 = { ...configured, DB: { prepare() { throw new Error("D1 unavailable"); } } } as unknown as Env;
    const sent = await api("send", { requestId: crypto.randomUUID() }, TOKEN, withoutD1);
    expect(sent.status).toBe(200);
    const result = await api("verify", { challengeId: sent.body.challengeId, code: code() }, TOKEN, withoutD1);
    expect(result.body.verified).toBe(true);
  });

  it("reports metadata without exposing code or server credentials", async () => {
    const sent = await send();
    const result = await api("status", { challengeId: sent.body.challengeId });
    expect(result.body.delivery).toBe("accepted");
    expect(result.body).not.toHaveProperty("codeMac");
    expect(result.body).not.toHaveProperty("code");
    expect(result.body).not.toHaveProperty("email");
  });
});
