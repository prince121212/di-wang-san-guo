import { env, runInDurableObject } from "cloudflare:test";
import { beforeAll, beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import worker from "../src/index";
import type { Env } from "../src/types";
import { b64, unb64, sha, LEASE_MILLIS, readSession, cloudToken, validCloudToken } from "../src/member-crypto";

const E = env as unknown as Env;
const encoder = new TextEncoder();
let deviceA: CryptoKeyPair, deviceB: CryptoKeyPair;
let email: string, adminCookie: string, mailCode: string, challengeId: string;
let ip: string;
async function request(path: string, value?: unknown, headers = {}) {
  const response = await worker.fetch(new Request("https://worker.test" + path, {
    method: value === undefined ? "GET" : "POST",
    headers: { "content-type": "application/json", "cf-connecting-ip": ip, ...headers },
    ...(value === undefined ? {} : { body: JSON.stringify(value) }),
  }), E);
  return { status: response.status, body: await response.json<Record<string, any>>() };
}
async function proof(action: string, data: Record<string, unknown>, keys = deviceA) {
  const payload = JSON.stringify({ requestId: crypto.randomUUID(), timestamp: Date.now(), ...data });
  const publicKey = b64(await crypto.subtle.exportKey("spki", keys.publicKey));
  const signature = b64(await crypto.subtle.sign("RSASSA-PKCS1-v1_5", keys.privateKey,
    encoder.encode(`DWPM-MEMBER-V1\n/v1/member/${action}\n${payload}`)));
  return { payload, publicKey, signature };
}
async function signed(action: string, data: Record<string, unknown>, keys = deviceA) {
  return request("/v1/member/" + action, await proof(action, data, keys));
}
async function sendCode(purpose = "register") {
  const result = await request("/v1/member/send-code", { email, purpose, requestId: crypto.randomUUID() });
  challengeId = result.body.challengeId;
  return result;
}
async function register() {
  expect((await sendCode()).status).toBe(200);
  const result = await signed("register", { email, password: "test-password-123", challengeId, code: mailCode });
  expect(result.status).toBe(200);
  return result.body.member;
}
async function login(keys = deviceA, password = "test-password-123") {
  return signed("login", { email, password, deviceName: keys === deviceA ? "手机A" : "手机B" }, keys);
}
async function admin(action = "grant", plan = "month", requestId = crypto.randomUUID()) {
  return request("/admin/api/members/update", { email, action, plan, requestId, note: "test only" }, {
    cookie: adminCookie, origin: "https://worker.test", "x-admin-intent": "member-update",
  });
}
async function memberState() {
  const id = await sha("dwpm-member-v1:" + email);
  return runInDurableObject(env.RUNTIME_CONFIG.getByName("member-v1:" + id), async (_instance, state) => state.storage.get<any>("state"));
}
beforeAll(async () => {
  const algorithm = { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1,0,1]), hash: "SHA-256" };
  deviceA = await crypto.subtle.generateKey(algorithm, true, ["sign","verify"]) as CryptoKeyPair;
  deviceB = await crypto.subtle.generateKey(algorithm, true, ["sign","verify"]) as CryptoKeyPair;
  const r = await worker.fetch(new Request("https://worker.test/admin/api/login", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "test-admin", password: "test-password" }),
  }), E);
  adminCookie = String(r.headers.get("set-cookie")).split(";",1)[0];
});
beforeEach(async () => {
  email = crypto.randomUUID() + "@example.com"; ip = crypto.randomUUID();
  await runInDurableObject(env.RUNTIME_CONFIG.getByName("member-limit:email-global"), async (_i,s) => {
    await s.storage.deleteAll(); await s.storage.deleteAlarm();
  });
  vi.spyOn(globalThis,"fetch").mockImplementation(async (url, init) => {
    expect(String(url)).toBe("https://api.resend.com/emails");
    const sent = JSON.parse(String(init?.body));
    mailCode = /验证码是：(\d{6})/.exec(sent.text)![1];
    return Response.json({id:crypto.randomUUID()});
  });
});
afterEach(() => vi.restoreAllMocks());

describe("member authority and account lifecycle", () => {
  it("short-lived cloud data credentials cannot become member or administrator authority", async () => {
    const token=await cloudToken(E,"a".repeat(64),"session-test",Date.now()+60000);
    expect(await validCloudToken(E,token)).toBe(true);
    const read=await request("/v1/servers/directory/query",{platformKey:"sglm"},{authorization:`Bearer ${token}`});
    expect(read.status).toBe(200);
    expect((await request("/admin/api/members",undefined,{authorization:`Bearer ${token}`})).status).toBe(401);
    await expect(readSession(E,token)).rejects.toThrow();
    const expired=await cloudToken(E,"a".repeat(64),"session-test",Date.now()-1);
    expect(await validCloudToken(E,expired)).toBe(false);
  });
  it("registers using email proof, hashes passwords, consumes code, and grants no membership", async () => {
    const member = await register();
    expect(member.expiresAt).toBe(0); expect(member.active).toBe(false);
    const state = await memberState();
    expect(state.member.password.algorithm).toBe("scrypt-v1");
    expect(JSON.stringify(state)).not.toContain("test-password-123");
    expect(state.otp.used).toBe(true); expect(state.otp.digest).toBe("");
    const result = await login();
    expect(result.body.lease).toBeNull(); expect(result.body.code).toBe("MEMBER_EXPIRED");
    expect(result.body.cloudToken).toBeNull();
  });
  it("rejects invalid device proof and cannot reuse a signed request on another action", async () => {
    await register();
    const payload = await proof("login", {email,password:"test-password-123"});
    expect((await request("/v1/member/login", {...payload,signature:b64(new Uint8Array(256))})).status).toBe(401);
    expect((await request("/v1/member/reset-password", payload)).status).toBe(401);
    expect((await request("/v1/member/login", payload)).status).toBe(200);
    expect((await request("/v1/member/login", payload)).body.code).toBe("MEMBER_REPLAY");
  });
  it("only administrators grant fixed-duration memberships and retrying a grant is idempotent", async () => {
    await register();
    const untrusted = await request("/admin/api/members/update", {email,action:"grant",plan:"year"}, {authorization:"Bearer test-client-token"});
    expect(untrusted.status).toBe(401);
    const id = crypto.randomUUID();
    const granted = await admin("grant","month",id);
    expect(granted.status).toBe(200);
    expect(granted.body.member.expiresAt - Date.now()).toBeGreaterThan(29 * 86400000);
    expect((await admin("grant","month",id)).body.member.expiresAt).toBe(granted.body.member.expiresAt);
    expect((await admin("grant","year",id)).status).toBe(409);
    expect((await admin("grant","quarter")).body.member.expiresAt).toBe(granted.body.member.expiresAt + 90 * 86400000);
  });
  it("enforces administrator origin and rejects client-selected durations", async () => {
    await register();
    const payload = {email,action:"grant",plan:"year",note:"test",requestId:crypto.randomUUID()};
    expect((await request("/admin/api/members/update",payload,{cookie:adminCookie})).status).toBe(403);
    expect((await request("/admin/api/members/update",{...payload,days:99999},{cookie:adminCookie,origin:"https://worker.test","x-admin-intent":"member-update"})).status).toBe(400);
  });
  it("new phone login revokes the old session; old refresh/logout cannot reclaim or evict the new one", async () => {
    await register(); await admin();
    const a = (await login()).body;
    const b = (await login(deviceB)).body;
    const old = await signed("renew",{sessionToken:a.sessionToken});
    expect(old.body.code).toBe("MEMBER_SESSION_REPLACED");
    expect(old.body.otherDeviceName).toBe("手机B");
    expect((await signed("logout",{sessionToken:a.sessionToken})).status).toBe(409);
    expect((await signed("renew",{sessionToken:b.sessionToken},deviceB)).body.code).toBe("MEMBER_ACTIVE");
  });
  it("a copied bearer token on another device cannot obtain authorization", async () => {
    await register(); await admin();
    const a = (await login()).body;
    expect((await signed("renew",{sessionToken:a.sessionToken},deviceB)).body.code).toBe("MEMBER_DEVICE_INVALID");
  });
  it("leases are independently signed, bound to the session/device and at most two hours", async () => {
    await register(); await admin();
    const signedLogin = await proof("login", {email,password:"test-password-123"});
    const result = (await request("/v1/member/login", signedLogin)).body;
    const [payload, signature] = result.lease.split('.');
    const decode = (s:string) => unb64(s.replace(/-/g,'+').replace(/_/g,'/'));
    const claims = JSON.parse(new TextDecoder().decode(decode(payload)));
    const key = await crypto.subtle.importKey("spki",unb64(E.MEMBER_LEASE_PUBLIC_KEY!),{name:"RSASSA-PKCS1-v1_5",hash:"SHA-256"},false,["verify"]);
    expect(await crypto.subtle.verify("RSASSA-PKCS1-v1_5",key,decode(signature),encoder.encode(payload))).toBe(true);
    expect(await crypto.subtle.verify("RSASSA-PKCS1-v1_5",key,decode(signature),encoder.encode(payload+'x'))).toBe(false);
    expect(claims.expiresAt - claims.issuedAt).toBe(LEASE_MILLIS);
    expect(claims.maxGameAccounts).toBe(2);
    expect(claims.requestId).toBe(JSON.parse(signedLogin.payload).requestId);
    expect(claims.deviceId).toBe((await readSession(E,result.sessionToken)).deviceId);
    expect(claims.expiresAt).toBeLessThanOrEqual(claims.memberExpiresAt);
  });
  it("suspension and explicit revocation deny renewal with distinct explanations", async () => {
    await register(); await admin(); const a = (await login()).body;
    await admin("disable"); expect((await signed("renew",{sessionToken:a.sessionToken})).body.code).toBe("MEMBER_DISABLED");
    await admin("enable"); expect((await signed("renew",{sessionToken:a.sessionToken})).body.code).toBe("MEMBER_SESSION_REVOKED");
  });
  it("wrong passwords are limited and return no account details", async () => {
    await register();
    for (let i=0;i<5;i++) expect((await login(deviceA,"incorrect-password")).body.code).toBe("MEMBER_LOGIN_FAILED");
    expect((await login()).body.code).toBe("MEMBER_LOGIN_LOCKED");
  });
  it("wrong verification codes are counted and cannot be replaced by a different purpose", async () => {
    await sendCode(); const correct=mailCode;
    for(let i=0;i<5;i++) expect((await signed("register",{email,password:"test-password-123",challengeId,code:correct==='000000'?'000001':'000000'})).status).toBe(400);
    expect((await signed("register",{email,password:"test-password-123",challengeId,code:correct})).status).toBe(400);
    expect((await memberState()).member).toBeUndefined();
  });
  it("password reset consumes its code and revokes all previous sessions", async () => {
    await register(); await admin(); const old=(await login()).body;
    const stub=env.RUNTIME_CONFIG.getByName("member-v1:"+await sha("dwpm-member-v1:"+email));
    await runInDurableObject(stub,async(_i,s)=>{const state=await s.storage.get<any>('state');state.otp.createdAt=0;await s.storage.put('state',state);});
    await sendCode("reset-password");
    const result=await signed("reset-password",{email,password:"a-new-password-123",challengeId,code:mailCode});
    expect(result.status).toBe(200);
    expect((await signed("renew",{sessionToken:old.sessionToken})).body.code).toBe("MEMBER_PASSWORD_CHANGED");
    expect((await login(deviceB,"a-new-password-123")).body.code).toBe("MEMBER_ACTIVE");
  });
  it("member operations do not depend on the map database", async () => {
    await register();
    const direct=await worker.fetch(new Request('https://worker.test/v1/member/login',{
      method:'POST',body:JSON.stringify(await proof('login',{email,password:'test-password-123'})),
    }),{...E,DB:{prepare(){throw new Error('D1 quota exhausted');}}} as unknown as Env);
    expect(direct.status).toBe(200);
  });
  it("client-supplied membership or role fields never grant paid authority", async () => {
    await register();
    const result=await signed("login",{email,password:"test-password-123",role:"admin",expiresAt:Date.now()+365*86400000,plan:"year",active:true});
    expect(result.body.lease).toBeNull();
    expect(result.body.member.expiresAt).toBe(0);
  });
  it("administrator detail and listing require an admin session", async () => {
    expect((await request("/admin/api/members")).status).toBe(401);
    await register();
    const detail=await request("/admin/api/members/query",{email},{cookie:adminCookie,origin:"https://worker.test","x-admin-intent":"member-query"});
    expect(detail.body.member.email).toBe(email);
    expect(detail.body.member).not.toHaveProperty("password");
    expect(detail.body.member).not.toHaveProperty("sessionToken");
  });
  it("uncertain email delivery still returns a challenge without falsely claiming delivery", async () => {
    vi.mocked(fetch).mockImplementation(async(_url,init)=>{
      mailCode=/验证码是：(\d{6})/.exec(JSON.parse(String(init?.body)).text)![1];
      throw new Error("reply lost after send");
    });
    const sent=await sendCode();
    expect(sent.status).toBe(202);expect(sent.body.delivery).toBe("unknown");
    const result=await signed("register",{email,password:"test-password-123",challengeId,code:mailCode});
    expect(result.status).toBe(200);
  });
});
