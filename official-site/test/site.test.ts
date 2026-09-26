import { env } from "cloudflare:test";
import { beforeEach, describe, expect, it } from "vitest";
import worker, { type Env } from "../src/index";

const E = env as unknown as Env;
const apk = Uint8Array.from({ length: 1000 }, (_, i) => i % 251);
const release = { schemaVersion: 1, packageName: "com.example.dwpmclone", versionCode: 120, versionName: "V0.0.120",
  publishedAt: 1790420000000, sizeBytes: apk.length, sha256: "00".repeat(32), file: "dwsg-V0.0.120.apk",
  downloadUrl: "https://dwsg.292828.xyz/download/dwsg-V0.0.120.apk", notes: ["新增检查更新"] };

function get(path: string, init: RequestInit = {}) {
  return worker.fetch(new Request("https://dwsg.292828.xyz" + path, init), E);
}

beforeEach(async () => {
  await E.RELEASES.put("apk/dwsg-V0.0.120.apk", apk);
  await E.RELEASES.put("releases/latest.json", JSON.stringify(release));
  await E.RELEASES.put("releases/history.json", JSON.stringify({ schemaVersion: 1, releases: [release] }));
});

describe("release channel", () => {
  it("serves the latest manifest uncached for update checks, with ETag revalidation", async () => {
    const first = await get("/app/latest.json");
    expect(first.status).toBe(200);
    expect(first.headers.get("cache-control")).toBe("no-cache");
    expect(await first.json()).toMatchObject({ versionCode: 120, file: "dwsg-V0.0.120.apk" });
    const again = await get("/app/latest.json", { headers: { "if-none-match": first.headers.get("etag")! } });
    expect(again.status).toBe(304);
    expect((await get("/app/releases.json").then(r => r.json<any>())).releases[0].versionName).toBe("V0.0.120");
  });
  it("redirects the stable download link to the newest versioned package", async () => {
    const response = await get("/download/latest");
    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("/download/dwsg-V0.0.120.apk");
  });
  it("downloads the package as an attachment with a Chinese file name", async () => {
    const response = await get("/download/dwsg-V0.0.120.apk");
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/vnd.android.package-archive");
    expect(response.headers.get("content-disposition")).toContain(
      "filename*=UTF-8''" + encodeURIComponent("帝三资料库-V0.0.120.apk"));
    expect(response.headers.get("content-length")).toBe("1000");
    expect(new Uint8Array(await response.arrayBuffer())).toEqual(apk);
  });
  it("resumes interrupted downloads with byte ranges", async () => {
    const middle = await get("/download/dwsg-V0.0.120.apk", { headers: { range: "bytes=100-199" } });
    expect(middle.status).toBe(206);
    expect(middle.headers.get("content-range")).toBe("bytes 100-199/1000");
    expect(new Uint8Array(await middle.arrayBuffer())).toEqual(apk.slice(100, 200));
    const tail = await get("/download/dwsg-V0.0.120.apk", { headers: { range: "bytes=-10" } });
    expect(tail.headers.get("content-range")).toBe("bytes 990-999/1000");
    expect(new Uint8Array(await tail.arrayBuffer())).toEqual(apk.slice(990));
    const open = await get("/download/dwsg-V0.0.120.apk", { headers: { range: "bytes=900-" } });
    expect(open.headers.get("content-range")).toBe("bytes 900-999/1000");
  });
  it("rejects a range beyond the package", async () => {
    const response = await get("/download/dwsg-V0.0.120.apk", { headers: { range: "bytes=5000-6000" } });
    expect(response.status).toBe(416);
    expect(response.headers.get("content-range")).toBe("bytes */1000");
  });
  it("answers HEAD with the package size and no body", async () => {
    const response = await get("/download/dwsg-V0.0.120.apk", { method: "HEAD" });
    expect(response.status).toBe(200);
    expect(response.headers.get("content-length")).toBe("1000");
    expect(await response.text()).toBe("");
  });
  it("serves only versioned package names and read-only methods", async () => {
    for (const path of ["/download/dwsg-V0.0.999.apk", "/download/latest.json", "/download/dwsg-V0.0.120.apk.bak",
      "/download/%2e%2e%2freleases%2flatest.json"]) {
      expect((await get(path)).status).toBe(404);
    }
    expect((await get("/download/latest", { method: "POST" })).status).toBe(405);
    expect((await get("/app/latest.json", { method: "PUT", body: "{}" })).status).toBe(405);
  });
  it("reports that nothing is published yet instead of serving a stale link", async () => {
    await E.RELEASES.delete(["releases/latest.json", "releases/history.json"]);
    expect((await get("/app/latest.json")).status).toBe(404);
    expect((await get("/download/latest")).status).toBe(404);
  });
});
