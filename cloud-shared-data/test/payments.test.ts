import {env,runInDurableObject} from "cloudflare:test";
import {createPublicKey} from "node:crypto";
import {beforeAll,beforeEach,afterEach,expect,it,vi} from "vitest";
import worker from "../src/index";
import type {Env} from "../src/types";
import {b64,sha,sessionToken} from "../src/member-crypto";
import {cents,paymentConfig,verifyNotification,appPayEnabled} from "../src/alipay-payment";
import {orderStub,orderId,handlePaymentStorage} from "../src/payment-orders";
import {handleMemberStorage} from "../src/members";

const E=env as unknown as Env;const enc=new TextEncoder();
let device:CryptoKeyPair,platformKey:CryptoKey,memberId:string,token:string,deviceId:string,adminCookie:string;
async function request(path:string,value?:unknown,headers:Record<string,string>={}){
  const r=await worker.fetch(new Request("https://worker.test"+path,{method:value===undefined?"GET":"POST",
    headers:{"content-type":"application/json",...headers},...(value===undefined?{}:{body:JSON.stringify(value)})}),E);
  return {status:r.status,body:await r.json<any>()};
}
async function signed(action:string,data:Record<string,unknown>,keys=device){
  const payload=JSON.stringify({requestId:crypto.randomUUID(),timestamp:Date.now(),sessionToken:token,...data});
  return request("/v1/member/"+action,{payload,publicKey:b64(await crypto.subtle.exportKey("spki",keys.publicKey)),
    signature:b64(await crypto.subtle.sign("RSASSA-PKCS1-v1_5",keys.privateKey,enc.encode(`DWPM-MEMBER-V1\n/v1/member/${action}\n${payload}`)))});
}
async function create(plan="month",purchaseId=crypto.randomUUID()){
  const r=await signed("payment-create",{plan,purchaseId});expect(r.status).toBe(200);return r.body;
}
function fields(id:string){return {app_id:E.ALIPAY_APP_ID!,seller_id:E.ALIPAY_SELLER_ID!,out_trade_no:id,trade_no:"202609240000000000001",total_amount:"0.01",trade_status:"TRADE_SUCCESS",notify_id:crypto.randomUUID(),notify_type:"trade_status_sync",sign_type:"RSA2"};}
async function signNotification(fields:Record<string,string>):Promise<Record<string,string>>{
  const text=Object.keys(fields).filter(k=>!["sign","sign_type"].includes(k)&&fields[k]!=="").sort().map(k=>`${k}=${fields[k]}`).join("&");
  return {...fields,sign:b64(await crypto.subtle.sign("RSASSA-PKCS1-v1_5",platformKey,enc.encode(text)))};
}
async function notify(params:Record<string,string>){
  const response=await worker.fetch(new Request("https://worker.test/v1/payments/alipay/notify",{method:"POST",headers:{"content-type":"application/x-www-form-urlencoded"},body:new URLSearchParams(await signNotification(params)).toString()}),E);
  return {status:response.status,text:await response.text()};
}
async function getOrder(id:string){return runInDurableObject(orderStub(E,id),async(_i,s)=>s.storage.get<any>("order"));}
async function reply(method:string,data:Record<string,unknown>){
  const raw=JSON.stringify(data),sig=b64(await crypto.subtle.sign("RSASSA-PKCS1-v1_5",platformKey,enc.encode(raw)));
  return new Response(`{"${method.replaceAll(".","_")}_response":${raw},"sign":${JSON.stringify(sig)}}`,{headers:{"content-type":"application/json"}});
}
async function admin(action:string,body:Record<string,unknown>){return request("/admin/api/payments/"+action,body,{cookie:adminCookie,origin:"https://worker.test","x-admin-intent":"payment-manage"});}
beforeAll(async()=>{
  device=await crypto.subtle.generateKey({name:"RSASSA-PKCS1-v1_5",hash:"SHA-256",modulusLength:2048,publicExponent:new Uint8Array([1,0,1])},true,["sign","verify"]) as CryptoKeyPair;
  deviceId=await sha(new Uint8Array(await crypto.subtle.exportKey("spki",device.publicKey)));
  platformKey=await crypto.subtle.importKey("pkcs8",Uint8Array.from(atob(E.MEMBER_LEASE_PRIVATE_KEY!),x=>x.charCodeAt(0)),{name:"RSASSA-PKCS1-v1_5",hash:"SHA-256"},false,["sign"]);
  const r=await worker.fetch(new Request("https://worker.test/admin/api/login",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({username:"test-admin",password:"test-password"})}),E);
  adminCookie=r.headers.get("set-cookie")!.split(";",1)[0];await r.text();
});
beforeEach(async()=>{
  memberId=await sha(crypto.randomUUID());
  const sessionId=crypto.randomUUID();token=await sessionToken(E,{kind:"dwpm-member-session-v1",memberId,sessionId,deviceId,authVersion:1,issuedAt:Date.now(),expiresAt:Date.now()+3600000});
  await runInDurableObject(E.RUNTIME_CONFIG.getByName("member-v1:"+memberId),async(_i,s)=>s.storage.put("state",{
    member:{id:memberId,email:"payment-test@example.com",authVersion:1,sessionId,deviceId,disabled:false,expiresAt:0,plan:"",createdAt:Date.now()},
    nonces:[],failures:0,lockedUntil:0,sendDay:0,sends:0,audit:[],mutations:[]}));
  vi.spyOn(globalThis,"fetch").mockImplementation(async()=>{throw new Error("unexpected outbound request");});
});
afterEach(()=>vi.restoreAllMocks());

it("disabled production catalog stays publicly readable without weakening protected APIs",async()=>{
  const disabled={...E,ALIPAY_MODE:"production",ALIPAY_ENABLED:"false",ALIPAY_LIVE_APPROVED:"false"};
  const response=await worker.fetch(new Request("https://worker.test/v1/payments/catalog"),disabled);
  expect(response.status).toBe(200);
  const catalog=await response.json<any>();expect(catalog.enabled).toBe(false);expect(catalog.plans).toEqual([]);
  const protectedResponse=await worker.fetch(new Request("https://worker.test/admin/api/payments/query",{
    method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({orderId:"DWP"+"a".repeat(32)})}),disabled);
  expect(protectedResponse.status).toBe(401);await protectedResponse.text();
});

it("one-cent acceptance is limited to a single member/order and leaves public sales closed",async()=>{
  const purchaseId=crypto.randomUUID();
  const a={...E,ALIPAY_MODE:"production",ALIPAY_ENABLED:"false",ALIPAY_APP_PAY_ENABLED:"false",ALIPAY_LIVE_APPROVED:"false",
    ALIPAY_PLAN_PRICES:JSON.stringify({month:"9.90",quarter:"25.90",year:"49.90"}),
    ALIPAY_ACCEPTANCE_MEMBER_ID:memberId,ALIPAY_ACCEPTANCE_PURCHASE_ID:purchaseId,ALIPAY_ACCEPTANCE_UNTIL:String(Date.now()+600000)};
  expect(()=>paymentConfig(a)).toThrow();
  const config=paymentConfig(a,"settlement"),id=await orderId(config,memberId,purchaseId);
  const call=(action:string,data:Record<string,unknown>,runtime=a)=>runInDurableObject(orderStub(E,id),async(_i,s)=>{
    const r=await handlePaymentStorage(new Request("https://payment.internal/payment/"+action,{method:"POST",body:JSON.stringify(data)}),runtime,s.storage);
    return r.json<any>();
  });
  const created=await call("create",{id,memberId,plan:"month",channel:"app"});
  expect(created.order.totalAmount).toBe("0.01");expect(created.order.days).toBe(0);expect(created.order.acceptance).toBe(true);
  expect((await call("create",{id,memberId,plan:"month",channel:"app"})).order.id).toBe(id);
  await expect(call("create",{id,memberId,plan:"year",channel:"app"})).rejects.toThrow();
  await expect(call("create",{id,memberId,plan:"month",channel:"web"})).rejects.toThrow();
  await expect(call("create",{id,memberId:await sha("wrong"),plan:"month",channel:"app"})).rejects.toThrow();
  await expect(call("app",{memberId:"wrong"})).rejects.toThrow();
  const sdk=await call("app",{memberId}),params=new URLSearchParams(sdk.orderStr),biz=JSON.parse(params.get("biz_content")!);
  expect(biz.total_amount).toBe("0.01");expect(biz.product_code).toBe("QUICK_MSECURITY_PAY");
  expect(biz.subject).toContain("不开通会员");expect(params.get("notify_url")).toBe(a.ALIPAY_ORIGIN+"/v1/payments/alipay/notify");
  // Expiry stops new SDK invocations, but verified late settlement still works.
  const expired={...a,ALIPAY_ACCEPTANCE_UNTIL:String(Date.now()-1)};
  await expect(call("app",{memberId},expired)).rejects.toThrow();
  await expect(call("notify",{params:{...fields(id),total_amount:"9.90"}},expired)).rejects.toThrow();
  const notification=await signNotification(fields(id));
  expect(verifyNotification(config,notification)).toBe(true);
  await call("notify",{params:notification},expired);
  await call("notify",{params:notification},expired);
  const paid=await call("status",{memberId},expired);
  expect(paid.order.status).toBe("PAID");expect(paid.order.membershipApplied).toBe(false);
  const state=await runInDurableObject(E.RUNTIME_CONFIG.getByName("member-v1:"+memberId),async(_i,s)=>s.storage.get<any>("state"));
  expect(state.member.expiresAt).toBe(0);
  expect((await getOrder(id)).events.filter((e:any)=>e.notifyId===notification.notify_id)).toHaveLength(1);
  const catalog=await worker.fetch(new Request("https://worker.test/v1/payments/catalog"),a);
  expect((await catalog.json<any>()).enabled).toBe(false);
});

it("acceptance cannot be armed with invalid identity or unbounded expiry",async()=>{
  const base={...E,ALIPAY_MODE:"production",ALIPAY_ENABLED:"false",ALIPAY_LIVE_APPROVED:"false"};
  expect(()=>paymentConfig(base,"settlement")).toThrow();
  const a={...base,ALIPAY_ACCEPTANCE_MEMBER_ID:memberId,ALIPAY_ACCEPTANCE_PURCHASE_ID:crypto.randomUUID(),ALIPAY_ACCEPTANCE_UNTIL:String(Date.now()+7200000)};
  const id=await orderId(paymentConfig(a,"settlement"),memberId,a.ALIPAY_ACCEPTANCE_PURCHASE_ID);
  await expect(runInDurableObject(orderStub(E,id),async(_i,s)=>handlePaymentStorage(new Request("https://payment.internal/payment/create",{
    method:"POST",body:JSON.stringify({id,memberId,plan:"month",channel:"app"})}),a,s.storage))).rejects.toThrow();
});

it("normal-price production orders grant exact membership once after verified settlement",async()=>{
  const production={...E,ALIPAY_MODE:"production",ALIPAY_ENABLED:"true",ALIPAY_APP_PAY_ENABLED:"true",ALIPAY_LIVE_APPROVED:"true",
    ALIPAY_ACCEPTANCE_UNTIL:"1",ALIPAY_PLAN_PRICES:JSON.stringify({month:"9.90",quarter:"25.90",year:"49.90"})};
  // Run the actual member storage handler with the same production environment;
  // isolate storage in test DOs, never call any real payment gateway.
  const runtime={...production,RUNTIME_CONFIG:{getByName:(name:string)=>({fetch:async(url:string,init:RequestInit)=>
    runInDurableObject(E.RUNTIME_CONFIG.getByName(name),async(_i,s)=>handleMemberStorage(new Request(url,init),production,s.storage))})}} as unknown as Env;
  let expiry=0;
  for(const [plan,price,days] of [["month","9.90",30],["quarter","25.90",90],["year","49.90",365]] as const){
    const id=await orderId(paymentConfig(runtime),memberId,crypto.randomUUID());
    const call=(action:string,data:Record<string,unknown>)=>runInDurableObject(orderStub(E,id),async(_i,s)=>{
      const r=await handlePaymentStorage(new Request("https://payment.internal/payment/"+action,{method:"POST",body:JSON.stringify(data)}),runtime,s.storage);
      return r.json<any>();
    });
    const created=await call("create",{id,memberId,plan,channel:"app"});
    expect(created.order.totalAmount).toBe(price);expect(created.order.days).toBe(days);expect(created.order.acceptance).toBe(false);
    const before=Date.now();
    const params=await signNotification({...fields(id),total_amount:price});
    expect(verifyNotification(paymentConfig(runtime),params)).toBe(true);
    await call("notify",{params});
    const member=async()=>runInDurableObject(E.RUNTIME_CONFIG.getByName("member-v1:"+memberId),async(_i,s)=>(await s.storage.get<any>("state")).member);
    const granted=(await member()).expiresAt;
    expect(granted).toBeGreaterThanOrEqual(Math.max(expiry,before)+days*86400000);
    expect(granted).toBeLessThanOrEqual(Math.max(expiry,Date.now())+days*86400000);
    await call("notify",{params});expect((await member()).expiresAt).toBe(granted);
    const result=await call("status",{memberId});expect(result.order.membershipApplied).toBe(true);
    expiry=granted;
  }
  const r=await worker.fetch(new Request("https://worker.test/v1/payments/catalog"),runtime);
  const catalog=await r.json<any>();expect(catalog.enabled).toBe(true);
  expect(catalog.plans.map((p:any)=>p.totalAmount)).toEqual(["9.90","25.90","49.90"]);
});

it("prices are fixed-point, server-selected and disabled when unconfigured",async()=>{
  expect(cents("0.01")).toBe(1);expect(cents("12.3")).toBe(1230);
  for(const value of ["0","-1","1e2","1.001","NaN",1])expect(()=>cents(value)).toThrow();
  expect(()=>paymentConfig({...E,ALIPAY_ENABLED:"false"})).toThrow();
  expect(()=>paymentConfig({...E,ALIPAY_MODE:"production"})).toThrow();
  expect((await signed("payment-create",{plan:"month",purchaseId:crypto.randomUUID(),total_amount:"0.001"})).status).toBe(400);
  expect((await signed("payment-create",{plan:"constructor",purchaseId:crypto.randomUUID()})).status).toBe(400);
});
it("renewal purchase works without active membership and retries reuse one durable order",async()=>{
  const id=crypto.randomUUID(),a=await create("month",id),b=await create("month",id);
  expect(a.order.id).toBe(b.order.id);expect(a.order.totalAmount).toBe("0.01");
  expect((await signed("payment-create",{plan:"year",purchaseId:id})).status).toBe(409);
  const page=await worker.fetch(new Request(a.checkoutUrl),E),html=await page.text();
  expect(html).toContain("<form");expect(html).toContain("openapi-sandbox.dl.alipaydev.com");expect(html).toContain("FAST_INSTANT_TRADE_PAY");
});
it("APP orders use a signed native SDK string, fixed amount, expiry and HTTPS notify",async()=>{
  const purchaseId=crypto.randomUUID();
  const a=await signed("payment-create",{plan:"month",purchaseId,channel:"app"});
  expect(a.status).toBe(200);expect(a.body.order.channel).toBe("app");expect(a.body.checkoutUrl).toBeUndefined();
  expect((await signed("payment-create",{plan:"month",purchaseId,channel:"app"})).body.order.id).toBe(a.body.order.id);
  const r=await signed("payment-app-order",{orderId:a.body.order.id});
  expect(r.status).toBe(200);expect(r.body.mode).toBe("sandbox");
  const params=new URLSearchParams(r.body.orderStr);
  expect(params.get("method")).toBe("alipay.trade.app.pay");expect(params.get("sign_type")).toBe("RSA2");
  expect(params.get("notify_url")).toBe(E.ALIPAY_ORIGIN+"/v1/payments/alipay/notify");
  const biz=JSON.parse(params.get("biz_content")!);
  expect(biz.product_code).toBe("QUICK_MSECURITY_PAY");expect(biz.total_amount).toBe("0.01");
  expect(biz.out_trade_no).toBe(a.body.order.id);expect(biz.time_expire).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);
  const signature=params.get("sign")!;params.delete("sign");params.sort();
  const plain=Array.from(params,([k,v])=>`${k}=${v}`).join("&");
  // Outgoing requests use the merchant test key, not Alipay's notification key.
  const merchantPublic=createPublicKey({key:Buffer.from(E.ALIPAY_PRIVATE_KEY!,"base64"),format:"der",type:"pkcs1"}).export({format:"der",type:"spki"});
  const key=await crypto.subtle.importKey("spki",new Uint8Array(merchantPublic),{name:"RSASSA-PKCS1-v1_5",hash:"SHA-256"},false,["verify"]);
  expect(await crypto.subtle.verify("RSASSA-PKCS1-v1_5",key,Uint8Array.from(atob(signature),x=>x.charCodeAt(0)),enc.encode(plain))).toBe(true);
  expect(fetch).not.toHaveBeenCalled(); // SDK signing itself does not create an Alipay trade.
});
it("one purchase cannot change payment channel and web orders cannot yield APP strings",async()=>{
  const purchaseId=crypto.randomUUID(),a=await create("month",purchaseId);
  expect((await signed("payment-create",{plan:"month",purchaseId,channel:"app"})).status).toBe(409);
  expect((await signed("payment-app-order",{orderId:a.order.id})).status).toBe(409);
  expect((await signed("payment-create",{plan:"month",purchaseId:crypto.randomUUID(),channel:"unknown"})).status).toBe(400);
});
it("APP signing rejects non-owners, extra fields, expired and paid orders",async()=>{
  const {body:a}=await signed("payment-create",{plan:"month",purchaseId:crypto.randomUUID(),channel:"app"});
  const r=await orderStub(E,a.order.id).fetch("https://payment.internal/payment/app",{method:"POST",body:JSON.stringify({memberId:await sha("other")})});
  expect(r.status).toBe(403);await r.text();
  expect((await signed("payment-app-order",{orderId:a.order.id,total_amount:"0.001"})).status).toBe(400);
  await runInDurableObject(orderStub(E,a.order.id),async(_i,s)=>{const x=await s.storage.get<any>("order");x.expiresAt=Date.now()-1000;await s.storage.put("order",x);});
  expect((await signed("payment-app-order",{orderId:a.order.id})).status).toBe(409);
  await notify(fields(a.order.id));
  expect((await signed("payment-app-order",{orderId:a.order.id})).status).toBe(409);
  expect((await signed("payment-status",{orderId:a.order.id})).body.order.status).toBe("PAID");
});
it("APP payment requires an explicit additional production enablement",()=>{
  expect(appPayEnabled({...E,ALIPAY_MODE:"production",ALIPAY_APP_PAY_ENABLED:undefined})).toBe(false);
  expect(appPayEnabled({...E,ALIPAY_MODE:"production",ALIPAY_APP_PAY_ENABLED:"true"})).toBe(true);
});
it("expired absent trades become closed only after a signed query and grace period",async()=>{
  const {order}=await create();
  await runInDurableObject(orderStub(E,order.id),async(_i,s)=>{const x=await s.storage.get<any>("order");x.expiresAt=Date.now()-61000;await s.storage.put("order",x);});
  vi.mocked(fetch).mockImplementation(()=>reply("alipay.trade.query",{code:"40004",sub_code:"ACQ.TRADE_NOT_EXIST"}));
  expect((await signed("payment-status",{orderId:order.id})).body.order.status).toBe("CLOSED");
  await notify(fields(order.id));expect((await getOrder(order.id)).status).toBe("PAID");
});
it("a second member cannot read or query another member's order",async()=>{
  const a=await create();memberId=await sha("different");
  const r=await orderStub(E,a.order.id).fetch("https://payment.internal/payment/query",{method:"POST",body:JSON.stringify({memberId})});
  expect(r.status).toBe(403);await r.text();
  const page=await worker.fetch(new Request(a.checkoutUrl.replace(/access=[^&]+/,"access=bad")),E);
  expect(await page.text()).not.toContain("<form");
});
it("forged or altered notifications and duplicate fields never mark an order paid",async()=>{
  const {order}=await create(),params=await signNotification(fields(order.id));
  params.total_amount="0.02";
  expect(verifyNotification(paymentConfig(E),params)).toBe(false);
  const raw=new URLSearchParams(params).toString()+"&total_amount=0.01";
  const r=await worker.fetch(new Request("https://worker.test/v1/payments/alipay/notify",{method:"POST",headers:{"content-type":"application/x-www-form-urlencoded"},body:raw}),E);
  expect(await r.text()).toBe("fail");expect((await getOrder(order.id)).status).toBe("PENDING");
});
it("correctly signed wrong amount, seller or app notifications fail business checks",async()=>{
  const {order}=await create();
  for(const patch of [{total_amount:"0.02"},{seller_id:"2088000000000002"},{app_id:"other"}])expect((await notify({...fields(order.id),...patch})).text).toBe("fail");
  expect((await getOrder(order.id)).status).toBe("PENDING");
});
it("duplicate paid notifications are idempotent and sandbox never adds real member time",async()=>{
  const {order}=await create(),p=fields(order.id);
  expect((await notify(p)).text).toBe("success");const a=await getOrder(order.id);
  expect((await notify(p)).text).toBe("success");const b=await getOrder(order.id);
  expect(b.status).toBe("PAID");expect(b.fulfilledAt).toBe(a.fulfilledAt);
  const state=await runInDurableObject(E.RUNTIME_CONFIG.getByName("member-v1:"+memberId),async(_i,s)=>s.storage.get<any>("state"));
  expect(state.member.expiresAt).toBe(0);
});
it("refund notifications and fake return parameters cannot grant membership",async()=>{
  const {order}=await create();expect((await notify({...fields(order.id),refund_fee:"0.01",gmt_refund:"2026-09-24 18:00:00",out_biz_no:"refund"})).text).toBe("success");
  expect((await getOrder(order.id)).status).toBe("REFUNDED");
  await notify(fields(order.id));expect((await getOrder(order.id)).status).toBe("REFUNDED");
  const r=await worker.fetch(new Request("https://worker.test/pay/return?out_trade_no="+order.id+"&trade_status=TRADE_SUCCESS"),E);
  expect(await r.text()).toContain("尚无可核验的订单");
});

it("a partial external refund blocks a late paid event and another full refund",async()=>{
  const {order}=await create("quarter");
  await notify({...fields(order.id),total_amount:"0.02",refund_fee:"0.01",out_biz_no:"partial"});
  await notify({...fields(order.id),total_amount:"0.02"});
  expect((await getOrder(order.id)).status).toBe("REFUND_PENDING");
  expect((await admin("refund",{orderId:order.id,requestId:crypto.randomUUID(),reason:"full",confirm:"refund"})).status).toBe(409);
});

it("confirmed refund reverses once and late paid notifications cannot revive the order",async()=>{
  const {order}=await create();await notify(fields(order.id));
  vi.mocked(fetch).mockImplementation(()=>reply("alipay.trade.refund",{code:"10000",out_trade_no:order.id,trade_no:fields(order.id).trade_no,refund_fee:"0.01",fund_change:"Y"}));
  const body={orderId:order.id,requestId:crypto.randomUUID(),reason:"test",confirm:"refund"};
  expect((await admin("refund",body)).body.order.status).toBe("REFUNDED");
  await notify(fields(order.id));expect((await getOrder(order.id)).status).toBe("REFUNDED");
});

it("closing queries first, requires admin intent, and will not close a paid order",async()=>{
  const {order}=await create();await notify(fields(order.id));
  expect((await admin("close",{orderId:order.id,confirm:"close"})).status).toBe(409);
  expect((await request("/admin/api/payments/close",{orderId:order.id,confirm:"close"},{cookie:adminCookie})).status).toBe(403);
});

it("refund pending query uses the original refund id and requires confirmed refund status",async()=>{
  const {order}=await create();await notify(fields(order.id));const requestId=crypto.randomUUID();
  vi.mocked(fetch).mockImplementation(()=>reply("alipay.trade.refund",{code:"10000",fund_change:"N"}));
  expect((await admin("refund",{orderId:order.id,requestId,reason:"test",confirm:"refund"})).body.order.status).toBe("REFUND_PENDING");
  await runInDurableObject(orderStub(E,order.id),async(_i,s)=>{const x=await s.storage.get<any>("order");x.refund.requestedAt=Date.now()-11000;await s.storage.put("order",x);});
  vi.mocked(fetch).mockImplementation(()=>reply("alipay.trade.fastpay.refund.query",{code:"10000",out_trade_no:order.id,trade_no:fields(order.id).trade_no,out_request_no:requestId,refund_amount:"0.01",refund_status:"REFUND_SUCCESS"}));
  expect((await admin("refund-query",{orderId:order.id})).body.order.status).toBe("REFUNDED");
});
it("compensation query uses the official SDK response signature and confirms payment",async()=>{
  const {order}=await create();vi.mocked(fetch).mockImplementation(async(url,init)=>{
    expect(new URL(String(url)).hostname).toBe("openapi-sandbox.dl.alipaydev.com");expect(init?.redirect).toBe("manual");
    return reply("alipay.trade.query",{...fields(order.id),code:"10000"});
  });
  const r=await signed("payment-status",{orderId:order.id});expect(r.status).toBe(200);expect(r.body.order.status).toBe("PAID");
});
it("a forged query response cannot upgrade payment state",async()=>{
  const {order}=await create();vi.mocked(fetch).mockResolvedValue(Response.json({alipay_trade_query_response:{...fields(order.id),code:"10000"},sign:"forged"}));
  expect((await signed("payment-status",{orderId:order.id})).status).toBe(503);expect((await getOrder(order.id)).status).toBe("PENDING");
});
it("unknown/waiting payment stays pending rather than being treated as paid",async()=>{
  const {order}=await create();vi.mocked(fetch).mockImplementation(()=>reply("alipay.trade.query",{...fields(order.id),code:"10000",trade_status:"WAIT_BUYER_PAY"}));
  const r=await signed("payment-status",{orderId:order.id});expect(r.status).toBe(200);expect(r.body.order.status).toBe("PENDING");
});
it("administrator refund retries reuse original parameters and are not public",async()=>{
  const {order}=await create();await notify(fields(order.id));const requestId=crypto.randomUUID();
  const body={orderId:order.id,requestId,reason:"验收退款",confirm:"refund"};
  expect((await request("/admin/api/payments/refund",body)).status).toBe(401);
  const sent:string[]=[];vi.mocked(fetch).mockImplementation(async(_url,init)=>{sent.push(String(init?.body));throw new Error("lost reply");});
  expect((await admin("refund",body)).status).toBe(503);expect((await getOrder(order.id)).status).toBe("REFUND_PENDING");
  expect((await admin("refund",{...body,requestId:crypto.randomUUID()})).status).toBe(409);
  expect((await admin("refund",body)).status).toBe(503);expect(sent.length).toBe(2);
  expect(new URLSearchParams(sent[0]).get("biz_content")).toBe(new URLSearchParams(sent[1]).get("biz_content"));
});
it("member entitlement receipts survive repeated grants and refunds",async()=>{
  const stub=E.RUNTIME_CONFIG.getByName("member-v1:"+memberId),orderId="DWP"+crypto.randomUUID().replaceAll("-","");
  const update=async(action:string)=>runInDurableObject(stub,async(_i,s)=>{
    const r=await handleMemberStorage(new Request("https://member.internal/member/payment-entitlement",{method:"POST",body:JSON.stringify({orderId,mode:"production",tradeNo:"202609240000000000001",plan:"month",action})}),{...E,ALIPAY_MODE:"production",ALIPAY_LIVE_APPROVED:"true"},s.storage);
    expect(r.status).toBe(200);await r.text();return (await s.storage.get<any>("state")).member.expiresAt;
  });
  const first=await update("grant");expect(first-Date.now()).toBeGreaterThan(29*86400000);
  expect(await update("grant")).toBe(first);const refunded=await update("refund");
  expect(refunded).toBeLessThanOrEqual(Date.now());expect(await update("grant")).toBe(refunded);
});
