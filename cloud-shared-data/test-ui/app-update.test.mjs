import assert from "node:assert/strict";
import test from "node:test";
import { flush, harness, response } from "./membership-harness.mjs";

const current = { ok: true, supported: true, currentVersionName: "V0.0.120", currentVersionCode: 120,
  latest: null, updateAvailable: false, checkedAt: 0 };
const newer = { ...current, updateAvailable: true, message: "发现新版本 V0.0.121",
  latest: { versionCode: 121, versionName: "V0.0.121", publishedAt: 1790500000000, sizeBytes: 25219927,
    sha256: "ab".repeat(32), notes: ["新增检查更新", "修复若干问题"] } };

async function phone(route, storage = {}) {
  const ui = harness("../../电脑端辅助前端/app-update.js", storage, r => response(route(r)));
  await flush(); await flush();
  return ui;
}
const siteChecks = ui => ui.requests.filter(r => r.path.startsWith("/api/app/update?check=1"));

test("shows the installed version without asking the official site again within twelve hours", async () => {
  const ui = await phone(() => current, { "app-update:auto-checked-at": String(Date.now()) });
  assert.equal(ui.element("appUpdateCurrent").textContent, "当前版本：V0.0.120");
  assert.equal(siteChecks(ui).length, 0);
  assert.equal(ui.element("appUpdateLatest").hidden, true);
});

test("a silent daily check reveals a newer release with its size, date and notes", async () => {
  const ui = await phone(r => r.path.includes("check=1") ? newer : current);
  assert.equal(siteChecks(ui).length, 1);
  assert.equal(ui.element("appUpdateLatest").hidden, false);
  assert.equal(ui.element("appUpdateBadge").hidden, false);
  assert.match(ui.element("appUpdateSummary").textContent, /发现新版本 V0.0.121（24.1 MB，/);
  assert.deepEqual(ui.element("appUpdateNotes").children.map(n => n.textContent), ["新增检查更新", "修复若干问题"]);
  assert.ok(Number(ui.storage.get("app-update:auto-checked-at")) > 0);
});

test("the button forces a fresh check and the download opens through the phone", async () => {
  const ui = await phone(r => r.path.includes("check=1") ? newer : r.path.endsWith("/update-open") ? { ok: true } : current,
    { "app-update:auto-checked-at": String(Date.now()) });
  await ui.element("appUpdateCheck").onclick();
  assert.equal(ui.requests.at(-1).path, "/api/app/update?check=1&force=1");
  assert.match(ui.element("appUpdateFeedback").textContent, /发现新版本/);
  await ui.element("appUpdateDownload").onclick();
  assert.equal(ui.requests.at(-1).path, "/api/app/update-open");
  assert.match(ui.element("appUpdateFeedback").textContent, /覆盖安装/);
});

test("test and internal builds never offer an official-site update", async () => {
  const ui = await phone(() => ({ ...current, supported: false, currentVersionName: "V0.0.120-internal" }));
  assert.equal(siteChecks(ui).length, 0);
  assert.equal(ui.element("appUpdateCheck").hidden, true);
  assert.match(ui.element("appUpdateCurrent").textContent, /不通过官网更新/);
});

test("an unreachable site during the silent check leaves Home undisturbed", async () => {
  const ui = await phone(r => r.path.includes("check=1") ? { ok: false, error: "暂时无法连接官网" } : current);
  assert.equal(siteChecks(ui).length, 1);
  assert.equal(ui.element("appUpdateLatest").hidden, true);
  assert.equal(ui.element("appUpdateFeedback").textContent, "");
  assert.equal(ui.storage.get("app-update:auto-checked-at"), undefined);
});
