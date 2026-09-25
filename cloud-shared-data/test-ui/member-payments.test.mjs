import assert from "node:assert/strict";
import test from "node:test";
import {harness,response,flush} from "./membership-harness.mjs";
const active={ok:true,authenticated:true,allowed:true,member:{email:"a@example.com",expiresAt:1792597714886}};
async function ui(){
  const result=harness("../../电脑端辅助前端/membership.js",{},r=>response(r.path.endsWith("payment-catalog")?
    {ok:true,enabled:true,mode:"sandbox",plans:[{plan:"month",days:30,totalAmount:"0.01"}]}:active));
  await flush();return result;
}
test("storefront can be opened before payment enablement without placing an order",async()=>{
  const page=harness("../../电脑端辅助前端/membership.js",{},()=>response({ok:true,enabled:false}));
  await flush();page.requests.length=0;
  await page.element("memberStoreOpen").onclick();
  assert.equal(page.requests.length,1);
  assert.equal(page.requests[0].path,"/api/member/payment-store-open");
  assert.deepEqual(page.requests[0].body,{});
});
test("purchase UI submits only a plan, then opens the native server-issued checkout",async()=>{
  const page=await ui();page.onFetch(r=>response(r.path.endsWith("payment-create")?{ok:true,order:{id:"order",totalAmount:"0.01"}}:{ok:true}));
  await page.element("memberPaymentPlans").children[0].onclick();
  assert.deepEqual(page.requests.find(r=>r.path.endsWith("payment-create")).body,{plan:"month"});
  assert.equal(page.requests.filter(r=>r.path.endsWith("payment-open")).length,1);
  assert.match(page.confirmations[0],/沙箱测试/);
});
test("sandbox payment success never invokes membership renewal",async()=>{
  const page=await ui();page.requests.length=0;
  page.onFetch(()=>response({ok:true,order:{status:"PAID",mode:"sandbox",membershipApplied:false}}));
  await page.element("memberPaymentQuery").onclick();
  assert.match(page.element("memberPaymentFeedback").textContent,/未增加真实会员/);
  assert.equal(page.requests.filter(r=>r.path.endsWith("/check")).length,0);
});
test("confirmed production entitlement refreshes the membership status",async()=>{
  const page=await ui();page.requests.length=0;
  page.onFetch(r=>response(r.path.endsWith("payment-status")?{ok:true,order:{status:"PAID",mode:"production",fulfilled:true,membershipApplied:true}}:active));
  await page.element("memberPaymentQuery").onclick();
  assert.equal(page.requests.filter(r=>r.path.endsWith("/check")).length,1);
});
test("pending payment does not become a successful membership",async()=>{
  const page=await ui();page.requests.length=0;
  page.onFetch(()=>response({ok:true,order:{status:"PENDING",mode:"production",fulfilled:false,membershipApplied:false}}));
  await page.element("memberPaymentQuery").onclick();
  assert.match(page.element("memberPaymentFeedback").textContent,/尚未确认/);
  assert.equal(page.requests.filter(r=>r.path.endsWith("/check")).length,0);
});
