import type {Env} from "./types";
import {RequestError} from "./validation";
import {readSession,verifyDeviceProof,sha} from "./member-crypto";
import {amount,PAYMENT_PLANS,paymentConfig,notifyParams,verifyNotification,appPayEnabled} from "./alipay-payment";
import {orderId,orderStub,resultPage,validOrderId} from "./payment-orders";

function json(value:unknown,status=200){return Response.json(value,{status,headers:{"cache-control":"no-store"}});}
async function input(request:Request):Promise<Record<string,any>>{
  const raw=await request.text();if(raw.length>16000)throw new RequestError("支付请求过大",413);
  try{const value=JSON.parse(raw);if(value&&typeof value==="object"&&!Array.isArray(value))return value;}catch{}
  throw new RequestError("支付请求格式无效");
}
async function internal(response:Response):Promise<Response>{
  if(response.ok)return response;
  let body:any;try{body=await response.json();}catch{throw new RequestError("订单服务暂不可用",503);}
  throw new RequestError(body.error||"订单请求失败",response.status,body.code||"PAYMENT_FAILED");
}
async function orderCall(env:Env,id:string,action:string,data:Record<string,unknown>){
  return internal(await orderStub(env,id).fetch("https://payment.internal/payment/"+action,{method:"POST",body:JSON.stringify(data)}));
}
export async function handlePaymentRequest(request:Request,env:Env):Promise<Response|null>{
  const url=new URL(request.url),path=url.pathname;
  if(path==="/v1/payments/catalog"&&request.method==="GET"){
    try{const c=paymentConfig(env);return json({ok:true,enabled:true,mode:c.mode,channels:appPayEnabled(env)?["web","app"]:["web"],
      plans:Object.entries(PAYMENT_PLANS).map(([plan,days])=>({plan,days,totalAmount:amount(c.prices[plan as keyof typeof PAYMENT_PLANS])}))});}
    catch{return json({ok:true,enabled:false,plans:[],message:"在线支付暂未开放，请联系管理员开通"});}
  }
  if(path==="/v1/payments/alipay/notify"){
    try{
      if(request.method!=="POST")return new Response("fail",{status:405});
      const c=paymentConfig(env),params=await notifyParams(request);
      if(!verifyNotification(c,params)||!validOrderId(params.out_trade_no)||!params.notify_id)throw new RequestError("无效通知");
      const r=await orderCall(env,params.out_trade_no,"notify",{params});await r.text();
      return new Response("success",{headers:{"content-type":"text/plain;charset=utf-8"}});
    }catch{return new Response("fail",{status:400,headers:{"content-type":"text/plain;charset=utf-8"}});}
  }
  if(path==="/pay/return"&&request.method==="GET"){
    if(!url.searchParams.has("order"))return resultPage("正在确认支付结果","尚无可核验的订单，请返回APP查询。此页面不会直接开通会员。");
    try{return await orderCall(env,url.searchParams.get("order")!,"return",{access:url.searchParams.get("access")});}
    catch(e){
      console.warn("payment return unavailable",{code:e instanceof RequestError?e.code:"PAYMENT_UNAVAILABLE",status:e instanceof RequestError?e.status:503});
      return resultPage("支付结果待确认","暂时无法核验订单，请返回APP查询原订单，勿重复付款。"+(env.ALIPAY_MODE==="sandbox"?`（${e instanceof RequestError?e.code:"PAYMENT_UNAVAILABLE"}）`:""));
    }
  }
  if(path==="/pay/start"&&request.method==="GET"){
    try{return await orderCall(env,url.searchParams.get("order")||"","page",{access:url.searchParams.get("access")});}
    catch{return resultPage("暂时无法打开收银台","订单不存在、已过期或当前支付不可用，请返回APP查询原订单。");}
  }
  if(!["/v1/member/payment-create","/v1/member/payment-status","/v1/member/payment-app-order"].includes(path))return null;
  if(request.method!=="POST")throw new RequestError("支付请求方法无效",405);
  const c=paymentConfig(env);
  const proof=await verifyDeviceProof(path,await input(request));
  const claims=await readSession(env,proof.data.sessionToken);
  if(claims.deviceId!==proof.deviceId)throw new RequestError("付款账号不属于本机",401);
  // Authentication is required even for expired memberships, but expiry itself
  // must not prevent buying a renewal. A replaced login cannot place orders.
  const authorized=await env.RUNTIME_CONFIG.getByName("member-v1:"+claims.memberId).fetch("https://member.internal/member/payment-session",{
    method:"POST",body:JSON.stringify({claims,deviceId:proof.deviceId,data:{requestId:proof.data.requestId}})});
  await internal(authorized);await authorized.text();
  const allowedKeys=path.endsWith("payment-create")?["sessionToken","requestId","timestamp","purchaseId","plan","channel"]:["sessionToken","requestId","timestamp","orderId"];
  if(Object.keys(proof.data).some(k=>!allowedKeys.includes(k)))throw new RequestError("不允许客户端指定支付金额或会员时长");
  if(path.endsWith("payment-create")){
    const channel=proof.data.channel??"web";
    if(!["web","app"].includes(channel))throw new RequestError("支付渠道无效");
    if(channel==="app"&&!appPayEnabled(env))throw new RequestError("APP支付尚未开放",503,"PAYMENT_APP_DISABLED");
    if(!Object.hasOwn(PAYMENT_PLANS,proof.data.plan)||!/^[a-f0-9-]{36}$/i.test(proof.data.purchaseId||""))throw new RequestError("购买请求无效");
    const limit=await env.RUNTIME_CONFIG.getByName("member-limit:payment-create:"+await sha(claims.memberId)).fetch("https://member.internal/member-limit",{
      method:"POST",body:JSON.stringify({max:20,window:3600000})});
    if(!limit.ok)throw new RequestError("下单过于频繁，请稍后再试",429);
    await limit.text();
    return orderCall(env,await orderId(c,claims.memberId,proof.data.purchaseId),"create",{memberId:claims.memberId,plan:proof.data.plan,channel,id:await orderId(c,claims.memberId,proof.data.purchaseId)});
  }
  if(path.endsWith("payment-app-order"))return orderCall(env,proof.data.orderId,"app",{memberId:claims.memberId});
  return orderCall(env,proof.data.orderId,"query",{memberId:claims.memberId});
}

export async function handlePaymentAdmin(request:Request,env:Env,actor:string):Promise<Response|null>{
  const url=new URL(request.url);
  if(!url.pathname.startsWith("/admin/api/payments/"))return null;
  const action=url.pathname.split("/").at(-1)!;
  if(request.method!=="POST"||!["query","close","refund","refund-query"].includes(action))throw new RequestError("支付管理操作无效",404);
  if(request.headers.get("origin")!==url.origin||request.headers.get("x-admin-intent")!=="payment-manage")throw new RequestError("支付管理必须来自本后台",403);
  const data=await input(request);
  if(Object.keys(data).some(k=>!["orderId","requestId","reason","confirm"].includes(k)))throw new RequestError("支付管理参数无效");
  if(["close","refund"].includes(action)&&data.confirm!==action)throw new RequestError("请确认此订单操作");
  // Only authenticated admin routes reach these internal actions; full refunds
  // use the stored order amount, never an administrator/browser-supplied amount.
  return orderCall(env,data.orderId,action==="query"?"admin-query":action,{...data,actor});
}
