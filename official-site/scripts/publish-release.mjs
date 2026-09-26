#!/usr/bin/env node
// Publish a signed release APK to the official site's release channel (R2).
//
//   node scripts/publish-release.mjs --note "新增检查更新" [--note "..."] [--apk path] [--dry-run]
//
// Refuses anything that is not the official release build: wrong package, debuggable build,
// foreign signing certificate, or a version that is not newer than the current latest.
// Upload order is APK → history → latest, so a phone never sees a manifest whose APK is missing.
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SITE = "https://dwsg.292828.xyz";
const BUCKET = "dwpm-app-releases";
const PACKAGE = "com.example.dwpmclone";
// Release keystore certificate (docs/membership-v1-20260921.md); public, embedded in every release APK.
const RELEASE_CERT_SHA256 = "ad3448dc84ece6575c1e9c01119787664333117714d435db3818be9634627d19";

const siteRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const appRoot = resolve(siteRoot, "../自研辅助源码");

function fail(message) { console.error("发布中止：" + message); process.exit(1); }

function options(argv) {
  const parsed = { notes: [], apk: resolve(appRoot, "app/build/outputs/apk/release/app-release.apk"), dryRun: false };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--note" && argv[i + 1]) parsed.notes.push(argv[++i].trim());
    else if (argv[i] === "--apk" && argv[i + 1]) parsed.apk = resolve(argv[++i]);
    else if (argv[i] === "--dry-run") parsed.dryRun = true;
    else fail(`无法识别的参数 ${argv[i]}`);
  }
  if (!parsed.notes.filter(Boolean).length) fail("至少提供一条 --note 更新说明");
  if (!existsSync(parsed.apk)) fail(`找不到安装包 ${parsed.apk}，请先运行 自研辅助源码/tools/build-production.mjs`);
  return parsed;
}

function buildTool(name) {
  const props = readFileSync(resolve(appRoot, "local.properties"), "utf8");
  const sdk = process.env.ANDROID_HOME || /^sdk\.dir=(.+)$/m.exec(props)?.[1]?.trim();
  if (!sdk) fail("找不到 Android SDK（local.properties 的 sdk.dir 或 ANDROID_HOME）");
  const versions = readdirSync(join(sdk, "build-tools")).sort((a, b) => b.localeCompare(a, undefined, { numeric: true }));
  const found = versions.map(v => join(sdk, "build-tools", v, name)).find(existsSync);
  if (!found) fail(`Android build-tools 里没有 ${name}`);
  return found;
}

// apksigner is a Java tool; this Mac has no system Java, only the Homebrew JDK used for builds.
const HOMEBREW_JDK = "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home";
function tool(name, args) {
  const javaHome = process.env.JAVA_HOME || (existsSync(HOMEBREW_JDK) ? HOMEBREW_JDK : "");
  const env = { ...process.env, ...(javaHome ? { JAVA_HOME: javaHome, PATH: `${javaHome}/bin:${process.env.PATH}` } : {}) };
  try {
    return execFileSync(buildTool(name), args, { encoding: "utf8", env, stdio: ["ignore", "pipe", "pipe"] });
  } catch (error) {
    fail(`${name} 执行失败：${String(error.stderr || error.message).trim().split("\n")[0]}`);
  }
}

function inspect(apk) {
  const badging = tool("aapt2", ["dump", "badging", apk]);
  const pkg = /^package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'/m.exec(badging);
  if (!pkg) fail("无法读取安装包版本信息");
  const [, packageName, versionCode, versionName] = pkg;
  if (packageName !== PACKAGE) fail(`包名是 ${packageName}，只允许发布正式版 ${PACKAGE}`);
  if (/^application-debuggable/m.test(badging)) fail("这是可调试（debug）安装包，不能发布");
  if (!/^V\d{1,3}\.\d{1,3}\.\d{1,4}$/.test(versionName)) fail(`版本名 ${versionName} 不是正式版本格式`);
  const certs = tool("apksigner", ["verify", "--print-certs", apk]);
  const signers = [...certs.matchAll(/certificate SHA-256 digest: ([0-9a-f]{64})/g)].map(m => m[1]);
  if (signers.length !== 1 || signers[0] !== RELEASE_CERT_SHA256) fail("签名证书不是正式发布证书");
  const minSdk = Number(/^(?:minSdkVersion|sdkVersion):'(\d+)'/m.exec(badging)?.[1] || 0);
  const bytes = readFileSync(apk);
  return { packageName, versionCode: Number(versionCode), versionName, minSdk, sizeBytes: bytes.length,
    sha256: createHash("sha256").update(bytes).digest("hex"), certificateSha256: signers[0] };
}

function wranglerEnv() {
  const env = { ...process.env };
  if (!env.CLOUDFLARE_API_TOKEN) {
    // Central local credential store; values are never printed.
    const file = join(homedir(), "Desktop/gitSpaceC/认证相关/cloudflare-account-d1.env");
    if (!existsSync(file)) fail("缺少 CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID");
    for (const line of readFileSync(file, "utf8").split("\n")) {
      const m = /^\s*(?:export\s+)?(CLOUDFLARE_[A-Z_]+)=(.*)$/.exec(line);
      if (m) env[m[1]] = m[2].trim().replace(/^["']|["']$/g, "");
    }
  }
  return env;
}

function wrangler(args, env, input) {
  return execFileSync(resolve(siteRoot, "node_modules/.bin/wrangler"), args,
    { cwd: siteRoot, env, encoding: "utf8", input, stdio: ["pipe", "pipe", "pipe"] });
}

function currentHistory(env) {
  try {
    const raw = wrangler(["r2", "object", "get", `${BUCKET}/releases/history.json`, "--remote", "--pipe"], env);
    const history = JSON.parse(raw);
    if (!Array.isArray(history.releases)) fail("线上更新记录格式异常，请人工检查");
    return history;
  } catch (error) {
    if (/not found|does not exist|NoSuchKey|404/i.test(String(error.stderr || error.message))) {
      return { schemaVersion: 1, releases: [] };
    }
    fail("读取线上更新记录失败：" + String(error.stderr || error.message).split("\n")[0]);
  }
}

const args = options(process.argv.slice(2));
const apk = inspect(args.apk);
const env = wranglerEnv();
const history = currentHistory(env);
const newest = history.releases[0];
if (newest && apk.versionCode <= newest.versionCode) {
  fail(`${apk.versionName}（${apk.versionCode}）不比线上最新 ${newest.versionName}（${newest.versionCode}）新`);
}
const file = `dwsg-${apk.versionName}.apk`;
const release = { schemaVersion: 1, ...apk, publishedAt: Date.now(), file,
  downloadUrl: `${SITE}/download/${file}`, notes: args.notes.filter(Boolean) };
const nextHistory = { schemaVersion: 1, releases: [release, ...history.releases] };

console.log(JSON.stringify(release, null, 2));
if (args.dryRun) { console.log("（--dry-run：只检查，未上传）"); process.exit(0); }

const work = mkdtempSync(join(tmpdir(), "dwsg-release-"));
try {
  writeFileSync(join(work, "history.json"), JSON.stringify(nextHistory));
  writeFileSync(join(work, "latest.json"), JSON.stringify(release));
  wrangler(["r2", "object", "put", `${BUCKET}/apk/${file}`, "--file", args.apk,
    "--content-type", "application/vnd.android.package-archive", "--remote"], env);
  wrangler(["r2", "object", "put", `${BUCKET}/releases/history.json`, "--file", join(work, "history.json"),
    "--content-type", "application/json; charset=utf-8", "--remote"], env);
  wrangler(["r2", "object", "put", `${BUCKET}/releases/latest.json`, "--file", join(work, "latest.json"),
    "--content-type", "application/json; charset=utf-8", "--remote"], env);
} finally {
  rmSync(work, { recursive: true, force: true });
}
console.log(`已发布 ${apk.versionName}：${SITE}/download/${file}`);
