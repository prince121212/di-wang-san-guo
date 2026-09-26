import assert from "node:assert/strict";
import test from "node:test";
import { flush, harness, response } from "./membership-harness.mjs";

const current = { ok: true, supported: true, currentVersionName: "V0.0.120", currentVersionCode: 120,
  officialSite: "https://dwsg.292828.xyz", latest: null, updateAvailable: false, checkedAt: 0 };
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

test("Home shows the official site and the QQ group, opened and copied through the phone", async () => {
  const ui = await phone(r => r.path.endsWith("/site-open") || r.path.endsWith("/copy-group-number") ? { ok: true } : current,
    { "app-update:auto-checked-at": String(Date.now()) });
  const community = ui.element("memberUpdateSlot").children[1];
  assert.match(community.innerHTML, /官网与交流群/);
  assert.match(community.innerHTML, /帝王三国攻略交流群<b id="appGroupNumber">879644685<\/b>/);
  assert.equal(ui.element("appOfficialSite").textContent, "dwsg.292828.xyz");
  await ui.element("appSiteOpen").onclick();
  assert.deepEqual([ui.requests.at(-1).path, ui.requests.at(-1).method], ["/api/app/site-open", "POST"]);
  assert.equal(ui.element("appCommunityFeedback").textContent, "已在浏览器打开官网。");
  await ui.element("appGroupCopy").onclick();
  assert.equal(ui.requests.at(-1).path, "/api/app/copy-group-number");
  assert.deepEqual(ui.requests.at(-1).body, { number: "879644685" });
  assert.match(ui.element("appCommunityFeedback").textContent, /^已复制群号 879644685。打开 QQ 搜索群号/);
});

test("the group card is shown on test builds too and reports the phone's failure reason", async () => {
  const ui = await phone(r => r.path.endsWith("/copy-group-number") ? { ok: false, error: "无法访问剪贴板，请手动记下群号" }
    : r.path.endsWith("/site-open") ? { ok: false, error: "手机上没有可用的浏览器，请手动访问 https://dwsg.292828.xyz/" }
    : { ...current, supported: false });
  assert.equal(ui.element("memberUpdateSlot").children.length, 2);
  await ui.element("appGroupCopy").onclick();
  assert.equal(ui.element("appCommunityFeedback").textContent, "无法访问剪贴板，请手动记下群号");
  await ui.element("appSiteOpen").onclick();
  assert.match(ui.element("appCommunityFeedback").textContent, /请手动访问 https:\/\/dwsg.292828.xyz\//);
  assert.equal(ui.element("appUpdateFeedback").textContent, "");
});
