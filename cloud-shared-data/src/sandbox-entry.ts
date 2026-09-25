/** Local-only acceptance entry; never imported by src/index.ts or deployed.
 * Uses real sandbox credentials and the exact production order/SDK code.
 * A sandbox order can exercise payment but cannot award real membership. */
import type {Env} from "./types";
import {handlePaymentRequest} from "./payments";
import {paymentConfig} from "./alipay-payment";
import {orderId,orderStub,resultPage} from "./payment-orders";
export {RuntimeConfigStore} from "./runtime-config";

export default {async fetch(request:Request,env:Env):Promise<Response>{
  const url=new URL(request.url);
  if(env.ALIPAY_MODE!=="sandbox"||url.protocol!=="http:"||!["127.0.0.1","localhost"].includes(url.hostname))return new Response("Local sandbox only",{status:403});
  try{
    if(url.pathname==="/sandbox"&&request.method==="GET")return new Response(`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>帝王三国 · 支付宝沙箱验收</title><style>body{font:16px/1.8 system-ui;background:#f3f6fa;padding:32px;color:#24394f}main{max-width:520px;margin:auto;padding:28px;background:white;border-radius:20px}button{padding:14px 24px;background:#255a8b;color:white;border:0;border-radius:12px;font-size:16px}</style><main><h1>支付宝沙箱验收</h1><p>这里使用支付宝官方沙箱，测试金额为0.01元沙箱余额，不扣真实资金。</p><p>测试商品：月卡（30天）。不会给真实会员增加时长，也不会更改手机账号。</p><form method="post" action="/sandbox/order"><input name="purchaseId" type="hidden" value="${crypto.randomUUID()}"><button>创建沙箱测试订单</button></form><p>页面跳转不算付款成功，以验签通知或主动查单为准。</p></main></html>`,{headers:{"content-type":"text/html;charset=utf-8","cache-control":"no-store","content-security-policy":"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"}});
    if(url.pathname==="/sandbox/order"&&request.method==="POST"){
      if(request.headers.get("origin")!==url.origin)return new Response("Origin required",{status:403});
      const body=await request.formData(),purchaseId=String(body.get("purchaseId")||"");
      if(!/^[a-f0-9-]{36}$/i.test(purchaseId))return new Response("Invalid purchase id",{status:400});
      const config=paymentConfig(env),memberId="a".repeat(64),id=await orderId(config,memberId,purchaseId);
      const r=await orderStub(env,id).fetch("https://payment.internal/payment/create",{method:"POST",body:JSON.stringify({id,memberId,plan:"month"})});
      const value=await r.json<{ok:boolean;checkoutUrl:string}>();if(!value.ok)throw new Error();
      return Response.redirect(value.checkoutUrl,303);
    }
    return await handlePaymentRequest(request,env)||new Response("Not found",{status:404});
  }catch{return resultPage("沙箱暂不可用","请检查本地沙箱服务配置。不会切换到正式支付。");}
}};
