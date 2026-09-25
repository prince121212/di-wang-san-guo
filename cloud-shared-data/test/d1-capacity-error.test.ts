import { env } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import worker from "../src/index";
import type { Env } from "../src/types";

afterEach(() => vi.restoreAllMocks());

async function failingRequest(error: Error) {
  vi.spyOn(console, "error").mockImplementation(() => {});
  return worker.fetch(new Request("https://worker.test/v1/presence/heartbeat", {
    method: "POST",
    headers: {
      authorization: "Bearer test-client-token",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      platformKey: "sanguo", serverKey: "352", actorId: "a".repeat(64),
    }),
  }), {
    ...env,
    DB: { prepare() { throw error; } },
  } as unknown as Env);
}

describe("D1 dependency capacity failures", () => {
  it.each(["read", "write"])("identifies daily row %s exhaustion without disclosing SQL", async (limit) => {
    vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-09-19T07:00:00Z"));
    const response = await failingRequest(new Error(
      `D1_ERROR: Your account has exceeded D1's free tier daily row ${limit} limit. private-sql-info`,
    ));
    const body = await response.json<Record<string, unknown>>();
    expect(response.status).toBe(503);
    expect(body).toMatchObject({
      ok: false, code: "CLOUD_D1_DAILY_LIMIT", limit,
      retryAtMillis: Date.parse("2026-09-20T00:00:00Z"),
    });
    expect(String(body.error)).toContain(limit === "write" ? "写入" : "读取");
    expect(JSON.stringify(body)).not.toContain("private-sql-info");
    expect(Number(response.headers.get("retry-after"))).toBe(17 * 60 * 60);
  });

  it("recognizes a wrapped D1 cause and rounds up the reset boundary", async () => {
    vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-09-19T23:59:59.500Z"));
    const response = await failingRequest(new Error("D1 batch failed", {
      cause: new Error("Your account has exceeded D1's free tier daily row write limit."),
    }));
    expect(response.status).toBe(503);
    expect(response.headers.get("retry-after")).toBe("1");
  });

  it("does not relabel arbitrary SQL errors as a recoverable quota condition", async () => {
    const response = await failingRequest(new Error("D1_ERROR: private SQL schema failure"));
    expect(response.status).toBe(500);
    expect(await response.json()).toEqual({
      ok: false, code: "INTERNAL_ERROR", error: "共享云端数据服务异常",
    });
    expect(response.headers.has("retry-after")).toBe(false);
  });

  it("bounds cause traversal even for a malformed cyclic error", async () => {
    const error = new Error("unknown database error");
    error.cause = error;
    const response = await failingRequest(error);
    expect(response.status).toBe(500);
  });
});
