import assert from "node:assert/strict";
import test from "node:test";
import { deferred, flush, harness, response } from "./membership-harness.mjs";

const member = email => ({ id: email, email, expiresAt: 0, disabled: false });
const dashboard = storage => harness("../public/admin/members.js", storage);

test("a failed lookup clears the previous member so grant cannot target a hidden stale account", async () => {
  const ui = dashboard();
  ui.onFetch(r => r.body.email === "a@example.com" ? response({ ok: true, member: member(r.body.email) })
    : response({ ok: false, error: "会员账号不存在" }, 404));
  ui.search("a@example.com"); await flush();
  ui.search("missing@example.com"); await flush();
  assert.equal(ui.element("memberDetail").hidden, true);
  await ui.element("memberGrant").onclick();
  assert.equal(ui.requests.filter(r => r.path.endsWith("/update")).length, 0);
});

test("out-of-order member lookups only display the latest requested member", async () => {
  const ui = dashboard(), first = deferred();
  ui.onFetch(r => r.body.email === "a@example.com" ? first.promise
    : response({ ok: true, member: member(r.body.email) }));
  ui.search("a@example.com"); ui.search("b@example.com"); await flush();
  first.resolve(response({ ok: true, member: member("a@example.com") })); await flush();
  assert.equal(ui.element("memberSelectedEmail").textContent, "b@example.com");
});

test("uncertain grant retry reuses its id and does not silently change the plan or note", async () => {
  const ui = dashboard(); let updates = 0;
  ui.onFetch(r => {
    if (r.path.endsWith("/update")) { updates++; if (updates === 1) throw new Error("reply lost"); return response({ok:true}); }
    return response(r.body ? {ok:true,member:member(r.body.email),audit:[]} : {ok:true,members:[],nextCursor:null});
  });
  ui.search("a@example.com"); await flush();
  await ui.element("memberGrant").onclick();
  const first = ui.requests.find(r => r.path.endsWith("/update")).body;
  ui.element("memberPlan").value = "year";
  await ui.element("memberGrant").onclick();
  assert.equal(updates, 1);
  ui.element("memberPlan").value = "month";
  await ui.element("memberGrant").onclick();
  assert.deepEqual(ui.requests.filter(r => r.path.endsWith("/update")).map(r=>r.body.requestId), [first.requestId,first.requestId]);
});

test("detail audit resolves an uncertain mutation without sending another grant", async () => {
  const pending = { email: "a@example.com", action: "grant", plan: "month", note: "", requestId: "receipt" };
  const ui = dashboard({ "dwpm.admin.member.pending.v1": JSON.stringify(pending) });
  ui.onFetch(() => response({ok:true,member:member(pending.email),audit:[{requestId:"receipt",kind:"admin-grant"}]}));
  ui.search(pending.email); await flush();
  assert.equal(ui.storage.has("dwpm.admin.member.pending.v1"), false);
  assert.match(ui.element("memberFeedback").textContent, /不会重复开通/);
});

test("reload restores the exact pending plan and note before an idempotent retry", async () => {
  const pending = {email:"a@example.com",action:"grant",plan:"quarter",note:"original note",requestId:"original-id"};
  const ui = dashboard({"dwpm.admin.member.pending.v1":JSON.stringify(pending)});
  ui.onFetch(r=>response(r.path.endsWith("/update")?{ok:true}:r.body?{ok:true,member:member(pending.email),audit:[]}:{ok:true,members:[]}));
  ui.search(pending.email); await flush();
  assert.equal(ui.element("memberPlan").value,"quarter");
  assert.equal(ui.element("memberNote").value,"original note");
  await ui.element("memberGrant").onclick();
  assert.deepEqual(ui.requests.find(r=>r.path.endsWith("/update")).body,pending);
});

test("querying another member while a mutation is in flight cannot switch its target", async () => {
  const ui = dashboard(), saving = deferred();
  ui.onFetch(r=>r.path.endsWith("/update")?saving.promise:response(r.body?{ok:true,member:member(r.body.email),audit:[]}:{ok:true,members:[]}));
  ui.search("a@example.com"); await flush();
  const change=ui.element("memberGrant").onclick();
  ui.search("b@example.com"); await flush();
  assert.equal(ui.requests.filter(r=>r.body?.email==="b@example.com").length,0);
  saving.resolve(response({ok:true})); await change;
  assert.equal(ui.element("memberSelectedEmail").textContent,"a@example.com");
});

test("the list names the one-day trial and the audit shows why a new account got none", async () => {
  const ui = dashboard();
  const trial = { ...member("new@example.com"), plan: "trial", expiresAt: Date.now() + 3600000, deviceName: "测试手机" };
  ui.onFetch(r => response(r.body ? { ok: true, member: member(r.body.email), audit: [
    { at: 1790000000000, kind: "register", deviceName: "测试手机", note: "未赠送体验：同一台手机已由 first@example.com 于 2026-09-26 21:05 注册" },
  ] } : { ok: true, members: [trial], nextCursor: null }));
  ui.ready(); await flush();
  const row = ui.element("memberTableBody").children[0].children.map(cell => cell.textContent);
  assert.equal(row[1], "体验（1天）");
  assert.equal(row[3], "有效");
  ui.search("second@example.com"); await flush();
  assert.match(ui.element("memberAudit").children[0].textContent, /register · 测试手机 · 未赠送体验：同一台手机已由 first@example\.com/);
});
