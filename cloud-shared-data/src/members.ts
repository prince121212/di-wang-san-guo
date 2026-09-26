import type { Env } from "./types";
import { RequestError } from "./validation";
import { b64, cloudToken, emailValue, equal, LEASE_MILLIS, mac, MemberSession, passwordHash, passwordMatches,
  passwordValue, PasswordRecord, randomId, readSession, sessionToken, sha, signLease, unb64, verifyDeviceProof } from "./member-crypto";

const encoder = new TextEncoder();
const PLANS: Record<string, number> = { month: 30, quarter: 90, year: 365 };
const DAY = 86_400_000;
const CONFIG_BACKUP_ACTIONS = ["config-backup-put", "config-backup-get"];
const SESSION_ACTIONS = ["renew", "logout", ...CONFIG_BACKUP_ACTIONS];
const CONFIG_BACKUP_MAX_BYTES = 512 * 1024;
/** Latest manual export only. The client seals game passwords with the member password; the
 * whole document is additionally encrypted at rest with a per-member key derived from the
 * Worker secret, so a storage dump alone reveals neither accounts nor settings. */
interface StoredConfigBackup { exportedAt: number; deviceName: string; accountCount: number; bytes: number;
  iv: string; ciphertext: string }
interface Otp { id: string; purpose: string; digest: string; createdAt: number; expiresAt: number;
  attempts: number; used: boolean; delivery: string; requestId: string }
interface Member {
  id: string; email: string; createdAt: number; password: PasswordRecord; authVersion: number;
  disabled: boolean; plan: string; expiresAt: number; sessionId: string; deviceId: string;
  deviceName: string; loginAt: number; lastCheckAt: number; sessionEndReason: string;
}
interface State {
  member?: Member; otp?: Otp; nonces: Array<{ id: string; at: number }>;
  failures: number; lockedUntil: number; sendDay: number; sends: number;
  audit: Array<Record<string, unknown>>; mutations: Array<{ id: string; fingerprint: string }>;
}
const EMPTY: State = { nonces: [], failures: 0, lockedUntil: 0, sendDay: 0, sends: 0, audit: [], mutations: [] };
function response(body: Record<string, unknown>, status = 200): Response {
  return Response.json({ serverTimeMillis: Date.now(), ...body }, { status, headers: { "cache-control": "no-store" } });
}
function error(code: string, message: string, status = 403, details = {}): Response {
  return response({ ok: false, code, error: message, ...details }, status);
}
function summary(member: Member) {
  return { id: member.id, email: member.email, createdAt: member.createdAt, disabled: member.disabled,
    plan: member.plan, expiresAt: member.expiresAt, active: !member.disabled && member.expiresAt > Date.now(),
    deviceName: member.deviceName, loginAt: member.loginAt, lastCheckAt: member.lastCheckAt,
    hasActiveSession: Boolean(member.sessionId), maxGameAccounts: 2 };
}
function audit(state: State, kind: string, details: Record<string, unknown> = {}) {
  state.audit.push({ id: crypto.randomUUID(), at: Date.now(), kind, ...details });
  state.audit = state.audit.slice(-200);
}
async function body(request: Request, max = 16000): Promise<Record<string, any>> {
  if (Number(request.headers.get("content-length") || 0) > max) throw new RequestError("请求过大", 413);
  const raw = await request.text();
  if (raw.length > max) throw new RequestError("请求过大", 413);
  try { const value = JSON.parse(raw); if (value && typeof value === "object" && !Array.isArray(value)) return value; }
  catch { /* generic error; never log input */ }
  throw new RequestError("请求格式无效");
}
/** The signed payload carries only the SHA-256; the document itself travels beside it. */
async function configBackupSummary(backup: unknown, digest: unknown): Promise<{ accountCount: number; bytes: number }> {
  if (typeof backup !== "string" || !backup) throw new RequestError("配置备份格式无效");
  const bytes = encoder.encode(backup).byteLength;
  if (bytes > CONFIG_BACKUP_MAX_BYTES) throw new RequestError("配置内容过大，无法导出", 413, "CONFIG_BACKUP_TOO_LARGE");
  if (typeof digest !== "string" || !equal(digest.toLowerCase(), await sha(backup))) {
    throw new RequestError("配置备份校验失败，请重新导出");
  }
  let value: any;
  try { value = JSON.parse(backup); } catch { throw new RequestError("配置备份格式无效"); }
  const accounts = value?.accounts;
  if (!value || typeof value !== "object" || value.format !== "dwpm-config-backup" || value.version !== 1
    || !Array.isArray(accounts) || accounts.length < 1 || accounts.length > 50
    || !value.secrets || typeof value.secrets !== "object") throw new RequestError("配置备份格式无效");
  return { accountCount: accounts.length, bytes };
}
async function configBackupKey(env: Env, memberId: string): Promise<CryptoKey> {
  const secret = await crypto.subtle.importKey("raw", encoder.encode(String(env.MEMBER_AUTH_SECRET)),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const raw = await crypto.subtle.sign("HMAC", secret, encoder.encode("config-backup-at-rest-v1\0" + memberId));
  return crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]);
}
async function sealConfigBackup(env: Env, memberId: string, backup: string) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData: encoder.encode(memberId) },
    await configBackupKey(env, memberId), encoder.encode(backup));
  return { iv: b64(iv), ciphertext: b64(ciphertext) };
}
async function openConfigBackup(env: Env, memberId: string, stored: StoredConfigBackup): Promise<string> {
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: unb64(stored.iv), additionalData: encoder.encode(memberId) },
    await configBackupKey(env, memberId), unb64(stored.ciphertext));
  return new TextDecoder().decode(plain);
}
function memberStub(env: Env, id: string) { return env.RUNTIME_CONFIG.getByName("member-v1:" + id); }
async function memberId(email: string) { return sha("dwpm-member-v1:" + email); }
async function limit(env: Env, name: string, max: number, window: number): Promise<boolean> {
  const stub = env.RUNTIME_CONFIG.getByName("member-limit:" + name);
  return (await stub.fetch("https://member.internal/member-limit", {
    method: "POST", body: JSON.stringify({ max, window }),
  })).ok;
}
async function indexMember(env: Env, member: Member) {
  // Projection only: authentication/entitlements never depend on this index.
  try {
    await env.RUNTIME_CONFIG.getByName("member-directory-v1").fetch("https://member.internal/member-directory", {
      method: "POST", body: JSON.stringify(summary(member)),
    });
  } catch { /* Admin can always look up an exact email directly. */ }
}
export async function handleMemberRequest(request: Request, env: Env): Promise<Response | null> {
  const path = new URL(request.url).pathname;
  if (!path.startsWith("/v1/member/")) return null;
  try {
    if (!env.MEMBER_AUTH_SECRET || !env.MEMBER_LEASE_PRIVATE_KEY || !env.MEMBER_LEASE_PUBLIC_KEY) {
      return error("MEMBER_NOT_CONFIGURED", "会员服务正在准备，请稍后再试", 503);
    }
    if (path === "/v1/member/info" && request.method === "GET") {
      return response({ ok: true, schemaVersion: 1, plans: PLANS, leaseMillis: LEASE_MILLIS,
        registrationEnabled: true, publicKey: env.MEMBER_LEASE_PUBLIC_KEY, maxGameAccounts: 2 });
    }
    const action = path.slice("/v1/member/".length);
    if (request.method !== "POST" || !["send-code", "register", "login", "reset-password", ...SESSION_ACTIONS].includes(action)) {
      return error("NOT_FOUND", "会员接口不存在", 404);
    }
    if (!SESSION_ACTIONS.includes(action)) {
      const ip = await sha(request.headers.get("cf-connecting-ip") || "unknown");
      if (!await limit(env, `${action}:${ip}`, action === "send-code" ? 10 : 60, 60 * 60_000)) {
        return error("MEMBER_RATE_LIMITED", "操作过于频繁，请稍后再试", 429);
      }
    }
    // JSON escaping can double the size of the embedded backup document.
    const input = await body(request, action === "config-backup-put" ? 2 * CONFIG_BACKUP_MAX_BYTES + 16000 : 16000);
    if (action === "send-code") {
      const email = emailValue(input.email);
      if (!["register", "reset-password"].includes(input.purpose) || typeof input.requestId !== "string"
        || !/^[a-f0-9-]{36}$/i.test(input.requestId)) throw new RequestError("验证码请求格式无效");
      return memberStub(env, await memberId(email)).fetch("https://member.internal/member/send-code", {
        method: "POST", body: JSON.stringify({ email, purpose: input.purpose, requestId: input.requestId }),
      });
    }
    const proof = await verifyDeviceProof(path, input);
    const data = proof.data;
    let claims: MemberSession | undefined;
    let id: string;
    let backup: Record<string, unknown> = {};
    if (SESSION_ACTIONS.includes(action)) {
      claims = await readSession(env, data.sessionToken);
      if (claims.deviceId !== proof.deviceId) return error("MEMBER_DEVICE_INVALID", "登录凭证不属于本机，请重新登录", 401);
      id = claims.memberId;
      if (CONFIG_BACKUP_ACTIONS.includes(action)) {
        data.password = passwordValue(data.password);
        if (action === "config-backup-put") {
          backup = { backup: input.backup, backupSummary: await configBackupSummary(input.backup, data.backupSha256) };
        }
        if (!await limit(env, `config-backup:${id}`, 30, 60 * 60_000)) {
          return error("MEMBER_RATE_LIMITED", "操作过于频繁，请稍后再试", 429);
        }
      }
    } else {
      data.email = emailValue(data.email);
      data.password = passwordValue(data.password);
      id = await memberId(data.email);
    }
    return memberStub(env, id).fetch(`https://member.internal/member/${action}`, {
      method: "POST", body: JSON.stringify({ data, claims, id, deviceId: proof.deviceId, ...backup }),
    });
  } catch (e) {
    if (e instanceof RequestError) return error(e.code, e.message, e.status);
    return error("MEMBER_SERVICE_UNAVAILABLE", "会员服务暂不可用，请稍后再试", 503);
  }
}

/** Internal DO calls only. Caller holds blockConcurrencyWhile, including async KDF/mail. */
export async function handleMemberStorage(request: Request, env: Env, storage: DurableObjectStorage): Promise<Response> {
  const path = new URL(request.url).pathname;
  const now = Date.now();
  if (path === "/member-limit") {
    const { max, window } = await request.json<{ max: number; window: number }>();
    const previous = await storage.get<{ count: number; until: number }>("limit");
    const value = previous && previous.until > now ? previous : { count: 0, until: now + window };
    if (value.count >= max) return response({ ok: false }, 429);
    value.count++;
    await storage.put("limit", value);
    await storage.setAlarm(value.until + 1000);
    return response({ ok: true });
  }
  if (path === "/member-directory") {
    if (request.method === "POST") {
      const row = await request.json<{ id: string }>();
      await storage.put("user:" + row.id, row);
      return response({ ok: true });
    }
    const startAfter = new URL(request.url).searchParams.get("after") || undefined;
    const records = await storage.list({ prefix: "user:", limit: 100, startAfter });
    return response({ ok: true, members: [...records.values()],
      nextCursor: records.size === 100 ? [...records.keys()].at(-1) : null });
  }
  const action = path.slice("/member/".length);
  const input = await request.json<Record<string, any>>();
  const state = await storage.get<State>("state") || structuredClone(EMPTY);
  const save = () => storage.put("state", state);
  if (action === "payment-entitlement") {
    // Internal DO call only. Persist entitlement and its permanent receipt
    // together, including refund-before-grant tombstones and retry recovery.
    const m=state.member;
    if(!m)return error("MEMBER_NOT_FOUND","会员不存在",404);
    if(input.mode!=="production"||env.ALIPAY_MODE!=="production"||env.ALIPAY_LIVE_APPROVED!=="true"
      ||!/^DWP[a-f0-9]{32}$/.test(input.orderId)||!Object.hasOwn(PLANS,input.plan)
      ||!["grant","refund"].includes(input.action)||!/^\d{10,80}$/.test(input.tradeNo))return error("PAYMENT_INVALID","付款权益参数无效",400);
    const key="payment-receipt:"+input.orderId;
    const previous=await storage.get<{tradeNo:string;plan:string;status:string}>(key);
    if(previous&&(previous.tradeNo!==input.tradeNo||previous.plan!==input.plan))return error("PAYMENT_CONFLICT","订单权益记录不一致",409);
    if(previous?.status==="refunded"||(previous&&input.action==="grant"))return response({ok:true,replayed:true});
    if(input.action==="grant"){
      m.expiresAt=Math.max(now,m.expiresAt)+PLANS[input.plan]*DAY;m.plan=input.plan;
      // Deliberately do not clear a suspension or replace a login session.
    }else if(previous?.status==="granted"){
      m.expiresAt=Math.max(now,m.expiresAt-PLANS[input.plan]*DAY);
    }
    audit(state,"payment-"+input.action,{orderId:input.orderId,plan:input.plan,expiresAt:m.expiresAt});
    await storage.transaction(async tx=>{
      await tx.put("state",state);
      await tx.put(key,{tradeNo:input.tradeNo,plan:input.plan,status:input.action==="grant"?"granted":"refunded"});
    });
    await indexMember(env,m);return response({ok:true});
  }
  if (action === "send-code") {
    const { email, purpose, requestId } = input;
    if (state.member?.disabled) return error("MEMBER_DISABLED", "账号已停用，请联系管理员");
    if (purpose === "register" && state.member) return error("MEMBER_EXISTS", "该邮箱已注册，请直接登录", 409);
    if (purpose === "reset-password" && !state.member) return response({ ok: true, message: "若邮箱已注册，将收到验证码" });
    if (state.otp && state.otp.requestId === requestId) return response({ ok: state.otp.delivery !== "failed",
      challengeId: state.otp.id, delivery: state.otp.delivery, replayed: true, expiresAt: state.otp.expiresAt });
    if (state.otp && now - state.otp.createdAt < 60_000) return error("EMAIL_COOLDOWN", "请60秒后重试", 429);
    const day = Math.floor(now / DAY);
    if (state.sendDay !== day) { state.sendDay = day; state.sends = 0; }
    if (state.sends >= 6 || !await limit(env, "email-global", Number(env.MEMBER_EMAIL_DAILY_LIMIT || 50), DAY)) {
      return error("EMAIL_LIMIT", "发信额度暂已用尽，请稍后再试", 429);
    }
    if (!env.RESEND_API_KEY || !env.RESEND_FROM_EMAIL) return error("EMAIL_UNAVAILABLE", "邮件服务尚未配置", 503);
    const bytes = new Uint32Array(1); const ceiling = Math.floor(2 ** 32 / 1_000_000) * 1_000_000;
    do { crypto.getRandomValues(bytes); } while (bytes[0] >= ceiling);
    const code = String(bytes[0] % 1_000_000).padStart(6, "0");
    const id = crypto.randomUUID();
    state.otp = { id, purpose, requestId, digest: await mac(env, `otp-v1\0${email}\0${purpose}\0${id}\0${code}`),
      createdAt: now, expiresAt: now + 15 * 60_000, attempts: 0, used: false, delivery: "pending" };
    state.sends++;
    await save();
    try {
      const result = await fetch("https://api.resend.com/emails", { method: "POST",
        headers: { authorization: `Bearer ${env.RESEND_API_KEY}`, "content-type": "application/json",
          "idempotency-key": "dwpm-member/" + id }, signal: AbortSignal.timeout(10_000),
        body: JSON.stringify({ from: `帝王三国资料库 <${env.RESEND_FROM_EMAIL}>`, to: [email],
          subject: `帝王三国资料库：${purpose === "register" ? "注册" : "重置密码"}验证码`,
          text: `你的验证码是：${code}\n15分钟内有效，只能使用一次。如非本人操作，请忽略。请勿向无关人员提供验证码。` }),
      });
      if (result.ok) {
        const receipt = await result.json<{id?: string}>();
        state.otp.delivery = typeof receipt.id === "string" && receipt.id.length > 0 ? "accepted" : "unknown";
      } else state.otp.delivery = result.status < 500 && ![408,409].includes(result.status) ? "failed" : "unknown";
    } catch { state.otp.delivery = "unknown"; }
    await save();
    return response({ ok: state.otp.delivery !== "failed", challengeId: id, expiresAt: state.otp.expiresAt,
      delivery: state.otp.delivery, message: state.otp.delivery === "accepted" ? "验证码已发送，请查收邮箱"
        : "邮件发送未确认，请先检查邮箱；如已收到可继续验证，未收到可60秒后重试", code: state.otp.delivery === "accepted" ? undefined : "EMAIL_UNAVAILABLE" },
    state.otp.delivery === "accepted" ? 200 : state.otp.delivery === "unknown" ? 202 : 503);
  }
  if (action === "admin-detail") return state.member ? response({ ok: true, member: summary(state.member), audit: state.audit })
    : error("MEMBER_NOT_FOUND", "会员账号不存在", 404);
  if (action === "admin-update") {
    const m = state.member;
    if (!m) return error("MEMBER_NOT_FOUND", "请用户先验证邮箱并注册", 404);
    const fingerprint = await sha(JSON.stringify([input.action, input.plan, input.note]));
    const prior = state.mutations.find(row => row.id === input.requestId);
    if (prior) return prior.fingerprint === fingerprint ? response({ ok: true, replayed: true, member: summary(m) })
      : error("IDEMPOTENCY_CONFLICT", "该操作编号已用于其他变更", 409);
    if (input.action === "grant") {
      const days = PLANS[input.plan]; if (!days) throw new RequestError("会员套餐无效");
      m.expiresAt = Math.max(now, m.expiresAt) + days * DAY;
      m.plan = input.plan;
    } else if (input.action === "disable") { m.disabled = true; m.sessionId = ""; m.sessionEndReason = "admin"; }
    else if (input.action === "enable") { m.disabled = false; }
    else if (input.action === "revoke") { m.sessionId = ""; m.sessionEndReason = "admin"; }
    else throw new RequestError("会员管理动作无效");
    audit(state, "admin-" + input.action, { actor: input.actor, plan: input.plan || "", note: input.note,
      expiresAt: m.expiresAt, requestId: input.requestId });
    state.mutations.push({ id: input.requestId, fingerprint }); state.mutations = state.mutations.slice(-500);
    await save(); await indexMember(env, m);
    return response({ ok: true, member: summary(m) });
  }
  const data = input.data || {};
  state.nonces = state.nonces.filter(n => now - n.at < 5 * 60_000);
  if (state.nonces.some(n => n.id === data.requestId)) return error("MEMBER_REPLAY", "该请求已经处理，请重新操作", 409);
  if (state.nonces.length >= 30) return error("MEMBER_RATE_LIMITED", "操作过于频繁，请稍后再试", 429);
  state.nonces.push({ id: data.requestId, at: now });
  if (action === "register" || action === "reset-password") {
    if (action === "register" && state.member) return error("MEMBER_EXISTS", "该邮箱已注册", 409);
    if (action === "reset-password" && !state.member) return error("CODE_INVALID", "验证码无效或已过期", 400);
    const otp = state.otp;
    const purpose = action === "register" ? "register" : "reset-password";
    if (!otp || otp.purpose !== purpose || otp.id !== data.challengeId || otp.used || otp.expiresAt <= now
      || otp.attempts >= 5 || otp.delivery === "failed") return error("CODE_INVALID", "验证码无效、已过期或错误次数过多", 400);
    if (typeof data.code !== "string" || !/^\d{6}$/.test(data.code)
      || !equal(otp.digest, await mac(env, `otp-v1\0${data.email}\0${purpose}\0${otp.id}\0${data.code}`))) {
      otp.attempts++; await save(); return error("CODE_INVALID", "验证码不正确", 400);
    }
    const password = await passwordHash(env, data.password);
    if (action === "register") state.member = { id: input.id, email: data.email, createdAt: now, password,
      authVersion: 1, disabled: false, plan: "", expiresAt: 0, sessionId: "", deviceId: "", deviceName: "",
      loginAt: 0, lastCheckAt: 0, sessionEndReason: "" };
    else { state.member!.password = password; state.member!.authVersion++; state.member!.sessionId = ""; }
    otp.used = true; otp.digest = ""; state.failures = 0; state.lockedUntil = 0;
    audit(state, action); await save(); await indexMember(env, state.member!);
    return response({ ok: true, member: summary(state.member!), message: action === "register"
      ? "注册成功，请登录；会员由管理员开通" : "密码已重置，旧登录已失效，请重新登录" });
  }
  const m = state.member;
  if (action === "login") {
    if (state.lockedUntil > now) return error("MEMBER_LOGIN_LOCKED", "尝试次数过多，请15分钟后重试", 429);
    if (!m || !await passwordMatches(env, data.password, m.password)) {
      state.failures++; if (state.failures >= 5) { state.lockedUntil = now + 15 * 60_000; state.failures = 0; }
      audit(state, "login-rejected"); await save(); return error("MEMBER_LOGIN_FAILED", "邮箱或密码不正确", 401);
    }
    if (m.disabled) return error("MEMBER_DISABLED", "会员账号已停用，请联系管理员");
    state.failures = 0; state.lockedUntil = 0;
    m.sessionId = randomId(); m.deviceId = input.deviceId;
    m.deviceName = String(data.deviceName || "Android手机").replace(/[\x00-\x1f]/g, "").slice(0,80);
    m.loginAt = now; m.lastCheckAt = now; m.sessionEndReason = "replaced";
    audit(state, "login", { deviceName: m.deviceName }); await save(); await indexMember(env, m);
    return authorized(env, m, data.requestId);
  }
  if (!m) return error("MEMBER_LOGIN_REQUIRED", "请登录会员账号", 401);
  const claims = input.claims as MemberSession;
  if (claims.authVersion !== m.authVersion) return error("MEMBER_PASSWORD_CHANGED", "会员密码已修改，请重新登录", 401);
  if (m.disabled) return error("MEMBER_DISABLED", "会员账号已停用，请联系管理员");
  if (!m.sessionId || claims.sessionId !== m.sessionId || input.deviceId !== m.deviceId) {
    return error(m.sessionEndReason === "admin" ? "MEMBER_SESSION_REVOKED" : "MEMBER_SESSION_REPLACED",
      m.sessionEndReason === "admin" ? "管理员已撤销本机登录，请重新登录" : input.deviceId === m.deviceId
        ? "会员账号已在本机重新登录，旧会话已失效，请重新登录" : "会员账号已在其他手机登录，本机自动任务已暂停",
      409, { otherLoginAtMillis: m.loginAt, otherDeviceName: m.deviceName, sameDevice: input.deviceId === m.deviceId });
  }
  if (CONFIG_BACKUP_ACTIONS.includes(action)) {
    // Holding a session is not enough: the export/import dialog re-proves the member password,
    // which also tells the phone that a failed unseal means an older password, not a typo.
    if (state.lockedUntil > now) return error("MEMBER_LOGIN_LOCKED", "尝试次数过多，请15分钟后重试", 429);
    if (!await passwordMatches(env, data.password, m.password)) {
      state.failures++; if (state.failures >= 5) { state.lockedUntil = now + 15 * 60_000; state.failures = 0; }
      audit(state, action + "-rejected"); await save();
      return error("MEMBER_PASSWORD_INVALID", "会员密码不正确", 401);
    }
    state.failures = 0; state.lockedUntil = 0;
    if (action === "config-backup-get") {
      const stored = await storage.get<StoredConfigBackup>("config-backup");
      audit(state, action, { found: Boolean(stored) }); await save();
      if (!stored) return error("CONFIG_BACKUP_NOT_FOUND", "云端还没有导出的配置，请先在原手机上点“导出配置”", 404);
      const { iv: _iv, ciphertext: _ciphertext, ...info } = stored;
      let backup: string;
      try { backup = await openConfigBackup(env, m.id, stored); }
      catch { return error("CONFIG_BACKUP_UNREADABLE", "云端配置无法读取，请在原手机上重新导出", 409); }
      return response({ ok: true, backup, backupInfo: info });
    }
    const info = { exportedAt: now, deviceName: m.deviceName, accountCount: input.backupSummary.accountCount,
      bytes: input.backupSummary.bytes };
    const sealed = await sealConfigBackup(env, m.id, input.backup);
    audit(state, action, { accountCount: info.accountCount, bytes: info.bytes });
    await storage.transaction(async tx => {
      await tx.put("state", state);
      await tx.put("config-backup", { ...info, ...sealed } satisfies StoredConfigBackup);
    });
    return response({ ok: true, backupInfo: info });
  }
  if (action === "logout") {
    m.sessionId = ""; m.sessionEndReason = "logout"; audit(state, "logout"); await save(); await indexMember(env, m);
    return response({ ok: true });
  }
  if (action === "payment-session") { await save(); return response({ok:true}); }
  if (action !== "renew") return error("NOT_FOUND", "接口不存在", 404);
  m.lastCheckAt = now; await save();
  return authorized(env, m, data.requestId);
}
async function authorized(env: Env, m: Member, requestId: string): Promise<Response> {
  const now = Date.now();
  const token = await sessionToken(env, { kind: "dwpm-member-session-v1", memberId: m.id, sessionId: m.sessionId,
    deviceId: m.deviceId, authVersion: m.authVersion, issuedAt: now, expiresAt: now + 30 * DAY });
  const lease = m.expiresAt > now ? await signLease(env, {
    kind: "dwpm-member-lease-v1", issuer: "dwpm", audience: "android", memberId: m.id,
    sessionId: m.sessionId, deviceId: m.deviceId, issuedAt: now, expiresAt: Math.min(now + LEASE_MILLIS, m.expiresAt),
    memberExpiresAt: m.expiresAt, maxGameAccounts: 2, requestId,
  }) : null;
  return response({ ok: true, member: summary(m), sessionToken: token, sessionId: m.sessionId, lease,
    cloudToken: lease ? await cloudToken(env,m.id,m.sessionId,Math.min(now+LEASE_MILLIS,m.expiresAt)) : null,
    code: lease ? "MEMBER_ACTIVE" : "MEMBER_EXPIRED",
    message: lease ? "会员授权有效" : "会员未开通或已到期，请联系管理员" });
}

export async function handleMemberAdmin(request: Request, env: Env, actor: string): Promise<Response | null> {
  const url = new URL(request.url);
  if (!url.pathname.startsWith("/admin/api/members")) return null;
  if (request.method === "POST" && url.pathname === "/admin/api/members/query") {
    if (request.headers.get("origin") !== url.origin || request.headers.get("x-admin-intent") !== "member-query") {
      throw new RequestError("管理员查询必须来自本后台",403,"ADMIN_ORIGIN_REQUIRED");
    }
    const input = await body(request);
    return memberStub(env, await memberId(emailValue(input.email))).fetch("https://member.internal/member/admin-detail", {
      method: "POST", body: "{}",
    });
  }
  if (request.method === "GET" && url.pathname === "/admin/api/members") {
    const after = url.searchParams.get("after") || "";
    if (after && !/^user:[a-f0-9]{64}$/.test(after)) throw new RequestError("分页标识无效");
    return env.RUNTIME_CONFIG.getByName("member-directory-v1").fetch("https://member.internal/member-directory?after=" + after);
  }
  if (request.method !== "POST" || url.pathname !== "/admin/api/members/update") throw new RequestError("接口不存在",404);
  if (request.headers.get("origin") !== url.origin || request.headers.get("x-admin-intent") !== "member-update"
    || !(request.headers.get("content-type") || "").startsWith("application/json")) {
    throw new RequestError("管理员操作必须来自本后台",403,"ADMIN_ORIGIN_REQUIRED");
  }
  const input = await body(request);
  const email = emailValue(input.email);
  if (!/^[a-f0-9-]{36}$/i.test(String(input.requestId || "")) || !["grant","disable","enable","revoke"].includes(input.action)
    || (input.action === "grant" && !PLANS[input.plan]) || typeof input.note !== "string" || input.note.length > 200
    || Object.keys(input).some(key => !["email","requestId","action","plan","note"].includes(key))) throw new RequestError("会员管理参数无效");
  return memberStub(env, await memberId(email)).fetch("https://member.internal/member/admin-update", {
    method: "POST", body: JSON.stringify({ ...input, actor }),
  });
}
