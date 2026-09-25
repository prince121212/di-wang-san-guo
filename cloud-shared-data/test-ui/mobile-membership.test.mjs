import assert from "node:assert/strict";
import test from "node:test";
import { deferred, flush, harness, response } from "./membership-harness.mjs";

async function mobile() {
  const ui = harness("../../电脑端辅助前端/membership.js"); await flush();
  ui.element("memberEmailInput").value = "a@example.com";
  ui.element("memberPasswordInput").value = "test-only-password";
  return ui;
}
test("membership mounts exclusively in Home, never above the assistant container", async () => {
  const ui = await mobile();
  assert.deepEqual(ui.element("homeMembershipSlot").children.map(node=>node.id), ["membershipPanel"]);
  assert.equal(ui.element("body").children.length, 0);
  assert.equal(ui.element("assistantPage").children.length, 0);
});
test("renewal entry navigates to Home before presenting membership instructions", async () => {
  const ui = await mobile(); let opened = false;
  ui.element("homeTab").onclick=()=>{opened=true;};
  ui.renew();
  assert.equal(opened,true);
  assert.match(ui.element("memberFormFeedback").textContent,/开通或续期/);
});
test("switching forms while a code request is pending cannot repurpose that code", async () => {
  const ui = await mobile(), code = deferred();
  ui.onFetch(() => code.promise);
  ui.mode("register"); const sending = ui.element("memberSendCode").onclick();
  ui.mode("reset-password");
  code.resolve(response({ok:true,challengeId:"registration-only",delivery:"accepted"})); await sending;
  await ui.submit();
  assert.equal(ui.requests.filter(r=>r.path.endsWith("/reset-password")).length, 0);
});
test("changing email while sending never attaches an old challenge to the new address", async () => {
  const ui = await mobile(), code = deferred(); ui.onFetch(()=>code.promise);
  ui.mode("register"); const sending = ui.element("memberSendCode").onclick();
  ui.element("memberEmailInput").value = "b@example.com"; ui.element("memberEmailInput").emit("input");
  code.resolve(response({ok:true,challengeId:"a-only",delivery:"accepted"})); await sending;
  await ui.submit(); assert.equal(ui.requests.filter(r=>r.path.endsWith("/register")).length, 0);
});
test("uncertain email delivery keeps the usable challenge and explains the uncertainty", async () => {
  const ui = await mobile(); ui.mode("register");
  ui.onFetch(r => response(r.path.endsWith("/send-code") ? {ok:true,challengeId:"maybe-sent",delivery:"unknown"}
    : {ok:true,message:"注册成功，请登录"}));
  await ui.element("memberSendCode").onclick();
  assert.match(ui.element("memberFormFeedback").textContent, /尚未确认/);
  ui.element("memberCodeInput").value = "123456"; await ui.submit();
  assert.equal(ui.requests.find(r=>r.path.endsWith("/register")).body.challengeId, "maybe-sent");
  assert.equal(ui.element("memberPasswordInput").value, "");
});
test("session replacement shows a persistent reason and one alert without auto-login", async () => {
  const ui = await mobile();
  const state = {ok:true,authenticated:true,allowed:false,code:"MEMBER_SESSION_REPLACED",
    member:{id:"member-a",email:"a@example.com"},details:{otherLoginAtMillis:1700000000000,otherDeviceName:"手机B"}};
  ui.onFetch(()=>response(state));
  const poll = ui.intervals.find(x=>x.ms===15000).fn;
  await poll(); await poll();
  assert.equal(ui.alerts.length, 1); assert.equal(ui.element("memberNotice").hidden,false);
  assert.match(ui.element("memberNotice").textContent,/另一台手机登录.*手机B/);
  assert.match(ui.element("memberNotice").textContent,/均已保留/);
  assert.equal(ui.requests.filter(r=>r.path.endsWith("/login")).length,0);
});
test("network trouble is not reported as another phone logging in", async () => {
  const ui = await mobile();
  ui.onFetch(()=>response({ok:true,authenticated:true,allowed:false,code:"MEMBER_NETWORK_UNAVAILABLE",
    message:"暂时无法验证会员授权，请检查网络",member:{id:"a"}}));
  await ui.intervals.find(x=>x.ms===15000).fn();
  assert.match(ui.element("memberNotice").textContent,/检查网络/); assert.equal(ui.alerts.length,0);
});

const activeMember={ok:true,required:true,authenticated:true,allowed:true,code:"MEMBER_ACTIVE",
  member:{id:"a",email:"a@example.com",expiresAt:1792597714886,plan:"month"}};
test("authorization recheck updates shared state and immediately notifies the assistant header", async () => {
  const ui=await mobile();let notified=0;
  ui.window.addEventListener("dwpm-membership-updated",()=>notified++);
  ui.onFetch(()=>response(activeMember));await ui.element("memberRecheck").onclick();
  assert.equal(notified,1);assert.equal(ui.window.DwpmMembershipState.allowed,true);
  assert.equal(ui.element("memberStatusBadge").textContent,"会员有效");
  assert.match(ui.element("memberExpiryDate").textContent,/2026.*10.*21/);
  assert.match(ui.element("memberFormFeedback").textContent,/授权已更新/);
});

test("an older status poll cannot overwrite a successful authorization recheck", async () => {
  const ui=await mobile(),old=deferred();
  ui.onFetch(r=>r.path.endsWith("/status")?old.promise:response(activeMember));
  const poll=ui.intervals.find(x=>x.ms===15000).fn();
  await ui.element("memberRecheck").onclick();
  old.resolve(response({...activeMember,allowed:false,code:"MEMBER_EXPIRED"}));await poll;
  assert.equal(ui.window.DwpmMembershipState.allowed,true);
  assert.equal(ui.element("memberStatusBadge").textContent,"会员有效");
});

test("polls while a member form is being edited do not discard typed credentials", async () => {
  const ui=await mobile();ui.element("memberPasswordInput").value="unsent-local-password";
  ui.onFetch(()=>response(activeMember));await ui.intervals.find(x=>x.ms===15000).fn();
  assert.equal(ui.element("memberPasswordInput").value,"unsent-local-password");
  assert.equal(ui.requests.filter(r=>r.path.endsWith("/login")).length,0);
});
