/**
 * 帝王三国资料库 official site: static pages plus the release channel the app checks for updates.
 *
 * R2 layout (written only by scripts/publish-release.mjs):
 *   releases/latest.json   newest release manifest, read by the app's update check
 *   releases/history.json  every published release, newest first, for the changelog
 *   apk/dwsg-V<x.y.z>.apk  immutable signed release packages
 */
export interface Env {
  ASSETS: Fetcher;
  RELEASES: R2Bucket;
}

const APK_FILE = /^dwsg-V\d{1,3}\.\d{1,3}\.\d{1,4}\.apk$/;
const APK_TYPE = "application/vnd.android.package-archive";
const MANIFESTS: Record<string, string> = {
  "/app/latest.json": "releases/latest.json",
  "/app/releases.json": "releases/history.json",
};

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: {
    "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });
}
function text(body: string, status: number, extra: HeadersInit = {}): Response {
  return new Response(body, { status, headers: { "content-type": "text/plain; charset=utf-8", ...extra } });
}

async function manifest(env: Env, key: string, request: Request): Promise<Response> {
  const object = await env.RELEASES.get(key, { onlyIf: request.headers });
  if (!object) return json({ ok: false, error: "暂无发布版本" }, 404);
  const headers = new Headers({
    "content-type": "application/json; charset=utf-8",
    // Phones must see a release as soon as it is published; revalidation stays cheap via ETag.
    "cache-control": "no-cache",
    "access-control-allow-origin": "*",
    etag: object.httpEtag,
  });
  if (!("body" in object)) return new Response(null, { status: 304, headers });
  return new Response(request.method === "HEAD" ? null : object.body, { headers });
}

async function latest(env: Env): Promise<Response> {
  const object = await env.RELEASES.get("releases/latest.json");
  const release = object ? await object.json<{ file?: unknown }>().catch(() => null) : null;
  if (!release || typeof release.file !== "string" || !APK_FILE.test(release.file)) {
    return json({ ok: false, error: "暂无发布版本" }, 404);
  }
  return new Response(null, { status: 302, headers: { location: "/download/" + release.file, "cache-control": "no-store" } });
}

/**
 * One byte range per RFC 9110, validated against the real size before touching R2 (so an
 * out-of-range request is a 416, never a silently truncated body). Multi-range and malformed
 * headers fall back to the whole file, which RFC 9110 permits.
 */
function byteRange(header: string | null, size: number): { offset: number; length: number } | "invalid" | null {
  const match = header ? /^bytes=(\d*)-(\d*)$/.exec(header.trim()) : null;
  if (!match || (match[1] === "" && match[2] === "")) return null;
  let start: number, end: number;
  if (match[1] === "") {
    const suffix = Number(match[2]);
    if (suffix === 0) return "invalid";
    start = Math.max(0, size - suffix); end = size - 1;
  } else {
    start = Number(match[1]); end = match[2] === "" ? size - 1 : Math.min(Number(match[2]), size - 1);
  }
  return start >= size || start > end ? "invalid" : { offset: start, length: end - start + 1 };
}

async function download(env: Env, file: string, request: Request): Promise<Response> {
  const key = "apk/" + file;
  const stored = await env.RELEASES.head(key);
  if (!stored) return text("安装包不存在", 404);
  const headers = new Headers({
    "content-type": APK_TYPE,
    "content-disposition": `attachment; filename="${file}"; filename*=UTF-8''${
      encodeURIComponent(file.replace(/^dwsg-/, "帝三资料库-"))}`,
    "accept-ranges": "bytes",
    // File names carry the version and are never overwritten.
    "cache-control": "public, max-age=31536000, immutable",
    "x-content-type-options": "nosniff",
    etag: stored.httpEtag,
  });
  if (request.method === "HEAD") {
    headers.set("content-length", String(stored.size));
    return new Response(null, { headers });
  }
  if (request.headers.get("if-none-match") === stored.httpEtag) return new Response(null, { status: 304, headers });
  const range = byteRange(request.headers.get("range"), stored.size);
  if (range === "invalid") return text("请求范围无效", 416, { "content-range": `bytes */${stored.size}` });
  const object = await env.RELEASES.get(key, range ? { range } : undefined);
  if (!object) return text("安装包不存在", 404);
  if (range) {
    headers.set("content-range", `bytes ${range.offset}-${range.offset + range.length - 1}/${stored.size}`);
    headers.set("content-length", String(range.length));
    return new Response(object.body, { status: 206, headers });
  }
  headers.set("content-length", String(stored.size));
  return new Response(object.body, { headers });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);
    const channel = pathname in MANIFESTS || pathname.startsWith("/download/");
    if (channel && request.method !== "GET" && request.method !== "HEAD") {
      return text("Method Not Allowed", 405, { allow: "GET, HEAD" });
    }
    if (pathname in MANIFESTS) return manifest(env, MANIFESTS[pathname], request);
    if (pathname === "/download/latest") return latest(env);
    if (pathname.startsWith("/download/")) {
      const file = pathname.slice("/download/".length);
      return APK_FILE.test(file) ? download(env, file, request) : text("安装包不存在", 404);
    }
    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;
