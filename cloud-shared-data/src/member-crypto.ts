import { scryptAsync } from "@noble/hashes/scrypt";
import type { Env } from "./types";
import { RequestError } from "./validation";

export const LEASE_MILLIS = 2 * 60 * 60_000;
export const SESSION_MILLIS = 30 * 24 * 60 * 60_000;
const encoder = new TextEncoder();
export function b64(bytes: ArrayBuffer | Uint8Array): string {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)));
}
export function unb64(value: string): Uint8Array<ArrayBuffer> {
  try { return Uint8Array.from(atob(value), c => c.charCodeAt(0)); }
  catch { throw new RequestError("凭证格式无效", 401, "MEMBER_SESSION_INVALID"); }
}
function url64(value: Uint8Array): string { return b64(value).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_"); }
function unurl64(value: string): Uint8Array {
  if (!/^[a-zA-Z0-9_-]+$/.test(value)) throw new RequestError("凭证格式无效", 401, "MEMBER_SESSION_INVALID");
  return unb64(value.replace(/-/g, "+").replace(/_/g, "/"));
}
export function randomId(): string { return url64(crypto.getRandomValues(new Uint8Array(32))); }
export async function sha(value: string | Uint8Array): Promise<string> {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", typeof value === "string" ? encoder.encode(value) : new Uint8Array(value)))]
    .map(n => n.toString(16).padStart(2, "0")).join("");
}
export function emailValue(raw: unknown): string {
  if (typeof raw !== "string") throw new RequestError("请输入邮箱");
  const email = raw.trim().toLowerCase();
  if (email.length > 254 || /[\x00-\x20\x7f<>]/.test(email)
    || !/^[^@]+@[^@]+\.[^@]+$/.test(email)) throw new RequestError("邮箱格式无效");
  return email;
}
export function passwordValue(raw: unknown): string {
  if (typeof raw !== "string" || raw.length < 10 || encoder.encode(raw).length > 128) {
    throw new RequestError("密码需至少10个字符，且不超过128字节");
  }
  return raw;
}
export async function mac(env: Env, context: string): Promise<string> {
  const secret = String(env.MEMBER_AUTH_SECRET || "");
  if (secret.length < 32) throw new RequestError("会员服务尚未配置", 503, "MEMBER_NOT_CONFIGURED");
  const key = await crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return url64(new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(context))));
}
export function equal(a: string, b: string): boolean {
  let difference = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) difference |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return difference === 0;
}
export interface PasswordRecord { algorithm: "scrypt-v1"; salt: string; hash: string }
let activePasswordJobs = 0;
export async function passwordHash(env: Env, password: string, salt = randomId()): Promise<PasswordRecord> {
  // Bound memory across DO instances sharing an isolate. Renewal never uses a KDF.
  if (activePasswordJobs >= 2) throw new RequestError("登录服务繁忙，请稍后重试", 503, "MEMBER_BUSY");
  activePasswordJobs++;
  try {
    const peppered = await mac(env, `password-v1\0${password}`);
    const hash = await scryptAsync(encoder.encode(peppered), encoder.encode(salt), {
      N: 32768, r: 8, p: 3, dkLen: 32, maxmem: 64 * 1024 * 1024,
    });
    return { algorithm: "scrypt-v1", salt, hash: b64(hash) };
  } finally { activePasswordJobs--; }
}
export async function passwordMatches(env: Env, password: string, stored: PasswordRecord): Promise<boolean> {
  return stored.algorithm === "scrypt-v1" && equal((await passwordHash(env, password, stored.salt)).hash, stored.hash);
}
export interface MemberSession {
  kind: "dwpm-member-session-v1"; memberId: string; sessionId: string; deviceId: string;
  authVersion: number; issuedAt: number; expiresAt: number;
}
export async function sessionToken(env: Env, value: MemberSession): Promise<string> {
  const payload = url64(encoder.encode(JSON.stringify(value)));
  return payload + "." + await mac(env, "session-v1:" + payload);
}
export async function cloudToken(env: Env, memberId: string, sessionId: string, expiresAt: number): Promise<string> {
  const payload = url64(encoder.encode(JSON.stringify({kind:"dwpm-member-map-v1",memberId,sessionId,issuedAt:Date.now(),expiresAt})));
  return payload + "." + await mac(env,"cloud-data-v1:"+payload);
}
export async function validCloudToken(env: Env, token: string): Promise<boolean> {
  if (!env.MEMBER_AUTH_SECRET || token.length > 4096) return false;
  const [payload, signature, extra] = token.split('.');
  if (!payload || !signature || extra || !equal(signature,await mac(env,"cloud-data-v1:"+payload))) return false;
  try {
    const value=JSON.parse(new TextDecoder().decode(unurl64(payload)));
    return value.kind==="dwpm-member-map-v1" && /^[a-f0-9]{64}$/.test(value.memberId)
      && typeof value.sessionId==="string" && Number.isSafeInteger(value.issuedAt) && Number.isSafeInteger(value.expiresAt)
      && value.issuedAt<=Date.now()+30_000 && value.expiresAt>Date.now()
      && value.expiresAt>value.issuedAt && value.expiresAt-value.issuedAt<=LEASE_MILLIS;
  } catch {return false;}
}
export async function readSession(env: Env, token: unknown): Promise<MemberSession> {
  if (typeof token !== "string" || token.length > 4096) throw new RequestError("请登录会员账号", 401, "MEMBER_LOGIN_REQUIRED");
  const [payload, signature, extra] = token.split(".");
  if (!payload || !signature || extra || !equal(signature, await mac(env, "session-v1:" + payload))) {
    throw new RequestError("登录凭证无效，请重新登录", 401, "MEMBER_SESSION_INVALID");
  }
  let value: MemberSession;
  try { value = JSON.parse(new TextDecoder().decode(unurl64(payload))); }
  catch { throw new RequestError("登录凭证无效", 401, "MEMBER_SESSION_INVALID"); }
  const now = Date.now();
  if (value.kind !== "dwpm-member-session-v1" || !/^[a-f0-9]{64}$/.test(value.memberId)
    || !/^[a-f0-9]{64}$/.test(value.deviceId) || !Number.isSafeInteger(value.authVersion)
    || !Number.isSafeInteger(value.issuedAt) || !Number.isSafeInteger(value.expiresAt)
    || value.issuedAt > now + 60_000 || value.expiresAt <= now
    || value.expiresAt - value.issuedAt > SESSION_MILLIS || typeof value.sessionId !== "string") {
    throw new RequestError("会员登录已过期，请重新登录", 401, "MEMBER_SESSION_EXPIRED");
  }
  return value;
}
export interface Proof { data: Record<string, any>; deviceId: string; publicKey: string }
export async function verifyDeviceProof(path: string, input: Record<string, unknown>): Promise<Proof> {
  if (typeof input.payload !== "string" || input.payload.length > 8192 || typeof input.publicKey !== "string"
    || input.publicKey.length > 1200 || typeof input.signature !== "string" || input.signature.length > 1024) {
    throw new RequestError("设备签名格式无效", 401, "MEMBER_DEVICE_INVALID");
  }
  let data: Record<string, any>;
  try { data = JSON.parse(input.payload); } catch { throw new RequestError("设备请求格式无效"); }
  if (!data || typeof data !== "object" || Array.isArray(data) || !Number.isSafeInteger(data.timestamp)
    || Math.abs(Date.now() - data.timestamp) > 5 * 60_000 || typeof data.requestId !== "string"
    || !/^[a-f0-9-]{36}$/i.test(data.requestId)) {
    throw new RequestError("请求已过期，请重新连接", 401, "MEMBER_REQUEST_EXPIRED");
  }
  try {
    const der = unb64(input.publicKey);
    const key = await crypto.subtle.importKey("spki", der, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
    if ((key.algorithm as KeyAlgorithm & {modulusLength: number}).modulusLength !== 2048 || !await crypto.subtle.verify(
      "RSASSA-PKCS1-v1_5", key, unb64(input.signature), encoder.encode(`DWPM-MEMBER-V1\n${path}\n${input.payload}`))) throw new Error();
    return { data, deviceId: await sha(der), publicKey: input.publicKey };
  } catch { throw new RequestError("设备签名不正确", 401, "MEMBER_DEVICE_INVALID"); }
}
export async function signLease(env: Env, claims: Record<string, unknown>): Promise<string> {
  if (!env.MEMBER_LEASE_PRIVATE_KEY) throw new RequestError("授权签名服务未配置", 503, "MEMBER_NOT_CONFIGURED");
  const payload = url64(encoder.encode(JSON.stringify(claims)));
  const key = await crypto.subtle.importKey("pkcs8", unb64(env.MEMBER_LEASE_PRIVATE_KEY),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["sign"]);
  return payload + "." + url64(new Uint8Array(await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, encoder.encode(payload))));
}
