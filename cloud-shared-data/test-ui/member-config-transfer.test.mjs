import assert from "node:assert/strict";
import test from "node:test";
import { flush, harness, response } from "./membership-harness.mjs";

const member = { ok: true, authenticated: true, allowed: true, code: "MEMBER_ACTIVE", configTransfer: true,
  member: { id: "member-a", email: "a@example.com", plan: "month", expiresAt: 1900000000000 } };
const preview = { ok: true, preview: true, exportedAt: 1790000000000, deviceName: "Xiaomi 22081212C", passwordsReadable: true,
  accounts: [{ label: "1608601@周年服351区", supported: true, existing: false, configCount: 5 },
    { label: "1608602@周年服352区", supported: true, existing: true, configCount: 3 }] };
const imported = { ok: true, added: ["1608601@周年服351区"], merged: ["1608602@周年服352区"], skipped: [],
  passwordsRestored: 1, passwordsMissing: [], configsRestored: 8 };

async function signedIn(route = {}) {
  const ui = harness("../../电脑端辅助前端/membership.js", {}, r => {
    const action = r.path.replace("/api/member/", "");
    if (route[action]) return response(route[action](r.body));
    return response(member);
  });
  await flush();
  return ui;
}
const transfers = ui => ui.requests.filter(r => /config-(export|import)$/.test(r.path));

test("the transfer card appears only for a signed-in member on a host that supports it", async () => {
  assert.equal((await signedIn()).element("memberTransfer").hidden, false);
  const unsupported = harness("../../电脑端辅助前端/membership.js", {}, () => response({ ...member, configTransfer: undefined }));
  await flush();
  assert.equal(unsupported.element("memberTransfer").hidden, true);
  const signedOut = harness("../../电脑端辅助前端/membership.js");
  await flush();
  assert.equal(signedOut.element("memberTransfer").hidden, true);
});

test("export and import never contact the phone without the member password", async () => {
  const ui = await signedIn();
  await ui.element("memberConfigExport").onclick();
  await ui.element("memberConfigImport").onclick();
  assert.equal(transfers(ui).length, 0);
  assert.match(ui.element("memberTransferFeedback").textContent, /会员密码/);
});

test("export sends the password once, clears the field and reports what was saved", async () => {
  const ui = await signedIn({ "config-export": () => ({ ok: true, accountCount: 2, passwordCount: 2, configCount: 8,
    backupInfo: { exportedAt: 1790000000000, accountCount: 2 } }) });
  ui.element("memberTransferPassword").value = "member-password-1";
  await ui.element("memberConfigExport").onclick();
  assert.deepEqual(transfers(ui).map(r => r.body), [{ password: "member-password-1" }]);
  assert.equal(ui.element("memberTransferPassword").value, "");
  assert.match(ui.confirmations.at(-1), /覆盖云端上一次导出/);
  assert.match(ui.element("memberTransferFeedback").textContent, /已导出 2 个游戏账号（2 个游戏密码、8 项设置）/);
});

test("import previews the cloud export and applies it only after confirmation", async () => {
  const ui = await signedIn({ "config-import": body => body.confirm ? imported : preview });
  ui.element("memberTransferPassword").value = "member-password-1";
  await ui.element("memberConfigImport").onclick();
  assert.deepEqual(transfers(ui).map(r => r.body.confirm), [false, true]);
  assert.equal(transfers(ui)[1].body.allowWithoutPasswords, false);
  const question = ui.confirmations.at(-1);
  assert.match(question, /1608601@周年服351区（新增，默认不启动）/);
  assert.match(question, /1608602@周年服352区（本机已有：合并设置，保留本机密码）/);
  const summary = ui.element("memberTransferFeedback").textContent;
  assert.match(summary, /新增 1 个、合并 1 个游戏账号，恢复 8 项设置、1 个游戏密码/);
  assert.match(summary, /默认不启动/);
  assert.equal(ui.element("memberTransferPassword").value, "");
});

test("declining the preview writes nothing", async () => {
  const ui = await signedIn({ "config-import": body => body.confirm ? imported : preview });
  ui.window.confirm = () => false;
  ui.element("memberTransferPassword").value = "member-password-1";
  await ui.element("memberConfigImport").onclick();
  assert.deepEqual(transfers(ui).map(r => r.body.confirm), [false]);
  assert.match(ui.element("memberTransferFeedback").textContent, /已取消导入/);
});

test("an export sealed with an older member password is imported only after explaining it", async () => {
  const ui = await signedIn({ "config-import": body => body.confirm
    ? { ...imported, passwordsRestored: 0, passwordsMissing: ["1608601@周年服351区"] }
    : { ...preview, passwordsReadable: false } });
  ui.element("memberTransferPassword").value = "member-password-new";
  await ui.element("memberConfigImport").onclick();
  assert.match(ui.confirmations.at(-1), /旧的会员密码导出的，游戏密码无法解开/);
  assert.equal(transfers(ui)[1].body.allowWithoutPasswords, true);
  assert.match(ui.element("memberTransferFeedback").textContent, /请在助手页点“修改”输入：1608601@周年服351区/);
});
