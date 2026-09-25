import type { Env } from "./types";
import { RequestError } from "./validation";

// Deliberately not a registration API: operator-only, one recipient, time-bounded.
const PREFIX = "/ops/email-verification/";
const TTL = 15 * 60_000;
const COOLDOWN = 60_000;
const MAX_ATTEMPTS = 5;
const MAX_SENDS_PER_DAY = 3;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const EMAIL = /^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/;

interface Challenge {
  id: string;
  requestId: string;
  codeMac: string;
  createdAtMillis: number;
  expiresAtMillis: number;
  attempts: number;
  usedAtMillis?: number;
  delivery: "pending" | "accepted" | "failed" | "unknown";
  messageId?: string;
  providerStatus?: number;
}
interface Budget { day: number; requestIds: string[] }

function json(value: unknown, status = 200): Response {
  return Response.json(value, { status, headers: { "cache-control": "no-store" } });
}
function failure(code: string, error: string, status: number): Response {
  return json({ ok: false, code, error }, status);
}
function normalizedEmail(raw: unknown): string {
  if (typeof raw !== "string") throw new RequestError("邮箱格式无效");
  const value = raw.trim().toLowerCase();
  if (value.length > 254 || !EMAIL.test(value)) throw new RequestError("邮箱格式无效");
  return value;
}
function hex(bytes: ArrayBuffer): string {
  return [...new Uint8Array(bytes)].map(n => n.toString(16).padStart(2, "0")).join("");
}
export async function emailProbeObjectName(email: string): Promise<string> {
  return "email-probe:" + hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(email)));
}
function generateCode(): string {
  const limit = Math.floor(2 ** 32 / 1_000_000) * 1_000_000;
  const bytes = new Uint32Array(1);
  do { crypto.getRandomValues(bytes); } while (bytes[0] >= limit);
  return (bytes[0] % 1_000_000).toString().padStart(6, "0");
}
async function codeMac(env: Env, email: string, id: string, code: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(env.EMAIL_PROBE_TOKEN),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return hex(await crypto.subtle.sign("HMAC", key,
    new TextEncoder().encode(`dwpm-email-probe-v1\0${email}\0${id}\0${code}`)));
}
function publicChallenge(record: Challenge) {
  return { challengeId: record.id, createdAtMillis: record.createdAtMillis,
    expiresAtMillis: record.expiresAtMillis, delivery: record.delivery,
    messageId: record.messageId ?? null, providerHttpStatus: record.providerStatus ?? null,
    attemptsRemaining: Math.max(0, MAX_ATTEMPTS - record.attempts),
    verified: Boolean(record.usedAtMillis) };
}
function sendResult(record: Challenge, replayed = false): Response {
  const accepted = record.delivery === "accepted";
  const pending = record.delivery === "pending";
  const failed = record.delivery === "failed";
  return json({ ok: accepted, ...publicChallenge(record), ...(replayed ? { replayed: true } : {}),
    ...(!accepted ? {
      code: pending ? "EMAIL_SEND_IN_PROGRESS" : failed ? "EMAIL_SEND_FAILED" : "EMAIL_SEND_UNCERTAIN",
      error: pending ? "邮件正在发送，请查询状态" : failed ? "邮件服务拒绝发送，可稍后重试"
        : "发送结果暂未确认，请先检查邮箱，重复本请求不会再次发信",
    } : {}),
  }, accepted ? 200 : pending ? 202 : failed ? 502 : 503);
}
async function readInput(request: Request): Promise<Record<string, unknown>> {
  if (Number(request.headers.get("content-length") ?? 0) > 2048) throw new RequestError("请求过大", 413);
  const raw = await request.text();
  if (raw.length > 2048) throw new RequestError("请求过大", 413);
  let input: unknown;
  try { input = JSON.parse(raw); } catch { throw new RequestError("请求格式无效"); }
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new RequestError("请求格式无效");
  return input as Record<string, unknown>;
}

export async function handleEmailProbeRequest(request: Request, env: Env): Promise<Response | null> {
  const path = new URL(request.url).pathname;
  if (!path.startsWith(PREFIX)) return null;
  const until = Number(env.EMAIL_PROBE_UNTIL || 0);
  const token = String(env.EMAIL_PROBE_TOKEN || "");
  if (token.length < 32 || !Number.isFinite(until) || until <= Date.now() || !env.EMAIL_PROBE_TO) {
    return failure("EMAIL_PROBE_DISABLED", "验证码联通测试未启用或已结束", 404);
  }
  if (request.headers.get("authorization") !== `Bearer ${token}`) {
    return failure("UNAUTHORIZED", "测试入口未授权", 401);
  }
  const action = path.slice(PREFIX.length);
  if (request.method !== "POST" || !["send", "verify", "status"].includes(action)) {
    return failure("NOT_FOUND", "测试接口不存在", 404);
  }
  const input = await readInput(request);
  const email = normalizedEmail(input.email);
  if (email !== normalizedEmail(env.EMAIL_PROBE_TO)) return failure("RECIPIENT_NOT_ALLOWED", "只能使用指定的测试邮箱", 403);
  const allowed = action === "send" ? ["email", "requestId"] : action === "verify"
    ? ["email", "challengeId", "code"] : ["email", "challengeId"];
  if (Object.keys(input).some(key => !allowed.includes(key))) throw new RequestError("请求包含未知字段");
  const id = action === "send" ? input.requestId : input.challengeId;
  if (typeof id !== "string" || !UUID.test(id)) throw new RequestError("测试请求标识无效");
  if (action === "verify" && (typeof input.code !== "string" || !/^\d{6}$/.test(input.code))) {
    throw new RequestError("验证码必须为6位数字");
  }
  if (action === "send" && (!env.RESEND_API_KEY || !EMAIL.test(env.RESEND_FROM_EMAIL || ""))) {
    return failure("EMAIL_NOT_CONFIGURED", "测试发信服务未配置", 503);
  }
  const stub = env.RUNTIME_CONFIG.getByName(await emailProbeObjectName(email));
  return stub.fetch(`https://config.internal/email-probe/${action}`, {
    method: "POST", body: JSON.stringify({ ...input, email }),
  });
}

/** Separate named object in the existing namespace; never touches config or D1. */
export async function handleEmailProbeStorage(
  request: Request, env: Env, storage: DurableObjectStorage,
): Promise<Response> {
  const action = new URL(request.url).pathname.split("/").pop();
  const input = await request.json<{ email: string; requestId: string; challengeId: string; code: string }>();
  if (action === "send") return sendCode(env, storage, input.email, input.requestId);
  if (action === "status") {
    const current = await storage.get<Challenge>("emailChallenge");
    if (!current || current.id !== input.challengeId) return failure("CODE_NOT_FOUND", "测试验证码不存在", 404);
    return json({ ok: true, ...publicChallenge(current) });
  }
  if (action !== "verify") return failure("NOT_FOUND", "测试接口不存在", 404);
  const mac = await codeMac(env, input.email, input.challengeId, input.code);
  return storage.transaction(async transaction => {
    const current = await transaction.get<Challenge>("emailChallenge");
    if (!current || current.id !== input.challengeId) return failure("CODE_NOT_FOUND", "验证码无效", 400);
    if (current.usedAtMillis) return failure("CODE_ALREADY_USED", "验证码已使用", 409);
    if (Date.now() >= current.expiresAtMillis) return failure("CODE_EXPIRED", "验证码已过期", 410);
    if (current.delivery === "failed") return failure("EMAIL_SEND_FAILED", "该验证码邮件发送失败", 409);
    if (current.attempts >= MAX_ATTEMPTS) return failure("CODE_LOCKED", "验证码错误次数已达上限", 429);
    if (mac !== current.codeMac) {
      current.attempts += 1;
      await transaction.put("emailChallenge", current);
      return failure(current.attempts >= MAX_ATTEMPTS ? "CODE_LOCKED" : "CODE_INVALID",
        current.attempts >= MAX_ATTEMPTS ? "验证码错误次数已达上限" : "验证码不正确",
        current.attempts >= MAX_ATTEMPTS ? 429 : 400);
    }
    current.usedAtMillis = Date.now();
    current.codeMac = "";
    await transaction.put("emailChallenge", current);
    return json({ ok: true, verified: true, challengeId: current.id,
      verifiedAtMillis: current.usedAtMillis, message: "邮箱验证码联通测试成功；未创建会员账号" });
  });
}

async function sendCode(env: Env, storage: DurableObjectStorage, email: string, requestId: string): Promise<Response> {
  const now = Date.now();
  const code = generateCode();
  const id = crypto.randomUUID();
  const record: Challenge = { id, requestId, codeMac: await codeMac(env, email, id, code),
    createdAtMillis: now, expiresAtMillis: Math.min(now + TTL, Number(env.EMAIL_PROBE_UNTIL)),
    attempts: 0, delivery: "pending" };
  const existing = await storage.transaction(async transaction => {
    const previous = await transaction.get<Challenge>("emailChallenge");
    if (previous?.requestId === requestId) return sendResult(previous, true);
    if (previous?.usedAtMillis) return failure("PROBE_COMPLETED", "测试已完成，发送入口不再发信", 409);
    if (previous && now - previous.createdAtMillis < COOLDOWN) return failure("SEND_COOLDOWN", "请60秒后再试", 429);
    const day = Math.floor(now / 86_400_000);
    const stored = await transaction.get<Budget>("emailBudget");
    const budget = stored?.day === day ? stored : { day, requestIds: [] };
    if (budget.requestIds.includes(requestId)) return failure("REQUEST_ALREADY_USED", "旧发送请求已经处理", 409);
    if (budget.requestIds.length >= MAX_SENDS_PER_DAY) return failure("SEND_LIMIT", "今日测试发信次数已达上限", 429);
    budget.requestIds.push(requestId);
    await transaction.put({ emailChallenge: record, emailBudget: budget });
    await transaction.setAlarm(Number(env.EMAIL_PROBE_UNTIL) + 60_000);
    return null;
  });
  if (existing) return existing;

  let delivery: Challenge["delivery"] = "unknown";
  let messageId: string | undefined;
  let providerStatus: number | undefined;
  try {
    const response = await fetch("https://api.resend.com/emails", {
      method: "POST", headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`,
        "Content-Type": "application/json", "Idempotency-Key": `dwpm-email-probe/${id}` },
      body: JSON.stringify({ from: `帝王三国资料库 <${env.RESEND_FROM_EMAIL}>`, to: [email],
        subject: "帝王三国资料库：邮箱验证码联通测试",
        text: `你的测试验证码是：${code}\n\n有效期${Math.ceil((record.expiresAtMillis - now) / 60_000)}分钟，仅可使用一次。\n这是你申请的邮箱联通测试，不会创建会员账号、扣费或修改游戏数据。\n请勿将验证码提供给无关人员。`,
      }), signal: AbortSignal.timeout(10_000),
    });
    providerStatus = response.status;
    if (response.status >= 400 && response.status < 500 && ![408, 409].includes(response.status)) {
      delivery = "failed";
    } else if (response.ok) {
      const payload = await response.json<{ id?: string }>();
      if (typeof payload.id === "string" && /^[a-z0-9-]{1,100}$/i.test(payload.id)) {
        delivery = "accepted";
        messageId = payload.id;
      }
    }
  } catch {
    // A timeout is not proof no email was sent. Never replay with a new code.
  }
  const final = await storage.transaction(async transaction => {
    const current = await transaction.get<Challenge>("emailChallenge");
    if (!current || current.id !== id) return null;
    Object.assign(current, { delivery, messageId, providerStatus });
    await transaction.put("emailChallenge", current);
    return current;
  });
  if (!final) return failure("PROBE_STATE_CHANGED", "测试状态已变化，请查询状态", 409);
  return sendResult(final);
}
