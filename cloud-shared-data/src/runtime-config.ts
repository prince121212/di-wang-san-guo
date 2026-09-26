import { DurableObject } from "cloudflare:workers";
import type { Env } from "./types";
import { RequestError } from "./validation";
import { handleEmailProbeStorage } from "./email-verification-probe";
import { handleMemberStorage } from "./members";
import { handlePaymentStorage } from "./payment-orders";

export interface RuntimeConfig {
  schemaVersion: 1;
  cloudBrushMapEnabled: boolean;
  revision: number;
  updatedAtMillis: number;
}

const DEFAULT_CONFIG: RuntimeConfig = {
  schemaVersion: 1, cloudBrushMapEnabled: true, revision: 0, updatedAtMillis: 0,
};

/** One tiny, strongly consistent control record, independent of D1 map quotas.
 * No public route reaches this object without Worker-side authentication.
 */
export class RuntimeConfigStore extends DurableObject<Env> {
  async fetch(request: Request): Promise<Response> {
    const path = new URL(request.url).pathname;
    if (path.startsWith("/payment/")) {
      return this.ctx.blockConcurrencyWhile(async () => {
        try { return await handlePaymentStorage(request, this.env, this.ctx.storage); }
        catch (e) { return Response.json({ ok:false, code:e instanceof RequestError?e.code:"PAYMENT_UNAVAILABLE",
          error:e instanceof RequestError?e.message:"订单服务暂不可用" },{status:e instanceof RequestError?e.status:503}); }
      });
    }
    if (path.startsWith("/member/") || path === "/member-directory" || path === "/member-limit" || path === "/member-trial") {
      return this.ctx.blockConcurrencyWhile(() => handleMemberStorage(request, this.env, this.ctx.storage));
    }
    if (new URL(request.url).pathname.startsWith("/email-probe/")) {
      return handleEmailProbeStorage(request, this.env, this.ctx.storage);
    }
    if (new URL(request.url).pathname === "/login-attempt" && request.method === "POST") {
      // Separate named object per hashed client IP; no credentials enter storage.
      const input = await request.json<{ valid: boolean }>();
      if (typeof input.valid !== "boolean") return new Response(null, { status: 400 });
      const now = Date.now();
      const result = await this.ctx.storage.transaction(async storage => {
        const previous = await storage.get<{ failures: number; firstAt: number; lockedUntil: number }>("attempt");
        if (previous && previous.lockedUntil > now) return { limited: true, retryAfterMillis: previous.lockedUntil - now };
        if (input.valid) {
          if (previous) await storage.delete("attempt");
        } else {
          const within = previous && now - previous.firstAt <= 15 * 60_000;
          const failures = within ? previous.failures + 1 : 1;
          await storage.put("attempt", { failures, firstAt: within ? previous.firstAt : now,
            lockedUntil: failures >= 5 ? now + 10 * 60_000 : 0 });
          await storage.setAlarm(now + 25 * 60_000);
        }
        return { limited: false, retryAfterMillis: 0 };
      });
      return Response.json(result);
    }
    if (request.method === "GET") {
      return Response.json(await this.ctx.storage.get<RuntimeConfig>("config") ?? DEFAULT_CONFIG);
    }
    if (request.method !== "PUT") return new Response(null, { status: 405 });
    const input = await request.json<{ cloudBrushMapEnabled: unknown; expectedRevision: unknown }>();
    if (typeof input.cloudBrushMapEnabled !== "boolean" || !Number.isSafeInteger(input.expectedRevision)) {
      return Response.json({ code: "INVALID_CONFIG", error: "配置格式无效" }, { status: 400 });
    }
    const result = await this.ctx.storage.transaction(async (storage) => {
      const current = await storage.get<RuntimeConfig>("config") ?? DEFAULT_CONFIG;
      if (input.expectedRevision !== current.revision) return null;
      if (input.cloudBrushMapEnabled === current.cloudBrushMapEnabled) return current;
      const next: RuntimeConfig = {
        schemaVersion: 1, cloudBrushMapEnabled: input.cloudBrushMapEnabled as boolean,
        revision: current.revision + 1, updatedAtMillis: Date.now(),
      };
      await storage.put("config", next);
      return next;
    });
    return result ? Response.json(result) : Response.json({
      code: "CONFIG_REVISION_CONFLICT", error: "配置已被其他管理页面修改，请刷新后重试",
    }, { status: 409 });
  }

  async alarm(): Promise<void> {
    await this.ctx.storage.deleteAll(); // Only isolated login/probe objects schedule alarms.
  }
}

export async function runtimeConfig(env: Env): Promise<RuntimeConfig> {
  const response = await env.RUNTIME_CONFIG.getByName("global").fetch("https://config.internal/");
  if (!response.ok) throw new RequestError("运行配置暂不可用", 503, "CONFIG_UNAVAILABLE");
  return response.json<RuntimeConfig>();
}

export async function updateRuntimeConfig(request: Request, env: Env): Promise<RuntimeConfig> {
  if (request.headers.get("origin") !== new URL(request.url).origin
    || request.headers.get("x-admin-intent") !== "runtime-config") {
    throw new RequestError("配置修改必须来自本后台页面", 403, "ADMIN_ORIGIN_REQUIRED");
  }
  if (!(request.headers.get("content-type") ?? "").startsWith("application/json")) {
    throw new RequestError("请使用 JSON 请求", 415, "INVALID_CONFIG");
  }
  if (Number(request.headers.get("content-length") ?? 0) > 4096) throw new RequestError("请求过大", 413);
  const raw = await request.text();
  if (raw.length > 4096) throw new RequestError("请求过大", 413);
  let input: Record<string, unknown>;
  try { input = JSON.parse(raw); } catch { throw new RequestError("配置格式无效"); }
  if (!input || typeof input !== "object" || Array.isArray(input)
    || Object.keys(input).some(key => !["cloudBrushMapEnabled", "expectedRevision"].includes(key))
    || typeof input.cloudBrushMapEnabled !== "boolean" || !Number.isSafeInteger(input.expectedRevision)
    || Number(input.expectedRevision) < 0) throw new RequestError("配置格式无效", 400, "INVALID_CONFIG");
  const response = await env.RUNTIME_CONFIG.getByName("global").fetch("https://config.internal/", {
    method: "PUT", body: JSON.stringify(input),
  });
  if (!response.ok) {
    const error = await response.json<{ error: string; code: string }>();
    throw new RequestError(error.error, response.status, error.code);
  }
  return response.json<RuntimeConfig>();
}
