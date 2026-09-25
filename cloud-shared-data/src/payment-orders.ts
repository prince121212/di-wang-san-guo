import type {Env} from "./types";
import {RequestError} from "./validation";
import {amount,cents,paymentConfig,paymentSdk,PAYMENT_PLANS,PaymentConfig,PaymentPlan,alipayTime,tradeCall,refundEvent,appPayEnabled} from "./alipay-payment";
import {equal,mac,sha} from "./member-crypto";

export interface PaymentOrder {
  channel?:"web"|"app"; // Missing on pre-APP orders means web; never migrate a live order.
  id:string;memberId:string;plan:PaymentPlan;days:number;totalCents:number;mode:"sandbox"|"production";
  appId:string;sellerId:string;createdAt:number;expiresAt:number;access:string;
  status:"PENDING"|"PAID"|"CLOSED"|"REFUND_PENDING"|"REFUNDED";
  tradeNo?:string;paidAt?:number;fulfilledAt?:number;lastQueryAt?:number;
  externalRefund?:boolean;
  events?:Array<{at:number;kind:string;actor?:string;notifyId?:string}>;
  refund?:{id:string;amountCents:number;reason:string;requestedAt:number;actor:string};
}
const labels={month:"月卡",quarter:"季卡",year:"年卡"};
const orderPattern=/^DW[SP][a-f0-9]{32}$/;
export function validOrderId(value:unknown):value is string {return typeof value==="string" && orderPattern.test(value);}
export async function orderId(config:PaymentConfig,memberId:string,requestId:string) {
  return "DW"+(config.mode==="sandbox"?"S":"P")+(await sha(`${config.appId}\0${memberId}\0${requestId}`)).slice(0,32);
}
export function orderStub(env:Env,id:string) {
  if(!validOrderId(id))throw new RequestError("订单编号无效");
  return env.RUNTIME_CONFIG.getByName("payment-v1:"+id);
}
function json(body:unknown,status=200){return Response.json(body,{status,headers:{"cache-control":"no-store"}});}
function publicOrder(order:PaymentOrder) {
  return {id:order.id,plan:order.plan,days:order.days,totalAmount:amount(order.totalCents),mode:order.mode,
    channel:order.channel??"web",status:order.status,createdAt:order.createdAt,expiresAt:order.expiresAt,
    fulfilled:Boolean(order.fulfilledAt),membershipApplied:order.mode==="production"&&Boolean(order.fulfilledAt)&&order.status==="PAID"};
}
function sameConfig(config:PaymentConfig,order:PaymentOrder) {
  if(config.appId!==order.appId || config.sellerId!==order.sellerId || config.mode!==order.mode)throw new RequestError("订单所属支付应用已变更，请联系管理员",409);
}
function matchTrade(config:PaymentConfig,order:PaymentOrder,result:Record<string,any>,sellerRequired:boolean) {
  if(result.out_trade_no!==order.id || cents(result.total_amount)!==order.totalCents
    || (sellerRequired && result.seller_id!==config.sellerId)
    || (result.seller_id && result.seller_id!==config.sellerId)
    || (result.app_id && result.app_id!==config.appId)
    || typeof result.trade_no!=="string" || !/^\d{10,80}$/.test(result.trade_no)
    || (order.tradeNo && order.tradeNo!==result.trade_no)) throw new RequestError("支付订单核对失败",400,"PAYMENT_MISMATCH");
}
async function memberEntitlement(env:Env,order:PaymentOrder,action:"grant"|"refund") {
  // A sandbox transaction must NEVER change a real user's membership.
  if(order.mode==="sandbox")return;
  const response=await env.RUNTIME_CONFIG.getByName("member-v1:"+order.memberId).fetch("https://member.internal/member/payment-entitlement",{
    method:"POST",body:JSON.stringify({orderId:order.id,tradeNo:order.tradeNo,plan:order.plan,action,mode:order.mode})});
  if(!response.ok)throw new RequestError("款项已确认，会员权益同步待重试",503,"PAYMENT_FULFILLMENT_PENDING");
  await response.text();
}
export function resultPage(title:string,message:string):Response {
  const escape=(s:string)=>s.replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]!);
  return new Response(`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>帝王三国 · 支付结果</title><style>body{font:16px/1.8 system-ui;background:#f3f6fa;color:#24394f;margin:0;padding:48px 22px}main{max-width:520px;background:white;border:1px solid #dde5ef;border-radius:20px;padding:28px;margin:auto}h1{font-size:24px}small{color:#728297}</style><main><small>帝王三国 · 会员服务</small><h1>${escape(title)}</h1><p>${escape(message)}</p><p>请返回 APP 的 Home 页面，点击「查询付款结果」或「重新检查授权」。</p><small>页面跳转不代表支付成功，以服务端查询为准。</small></main></html>`,{
    headers:{"content-type":"text/html;charset=utf-8","cache-control":"no-store","referrer-policy":"no-referrer","x-content-type-options":"nosniff","content-security-policy":"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'"}});
}

/** Serial execution via the named order DO. No alarms: receipts are durable and
 * never removed by the generic limiter's expiry cleanup. */
export async function handlePaymentStorage(request:Request,env:Env,storage:DurableObjectStorage):Promise<Response> {
  const action=new URL(request.url).pathname.slice("/payment/".length);
  const input=await request.json<Record<string,any>>();
  const config=paymentConfig(env);let order=await storage.get<PaymentOrder>("order");
  const save=()=>storage.put("order",order!);
  if(action==="create") {
    const channel=input.channel??"web";
    if(!["web","app"].includes(channel))throw new RequestError("支付渠道无效");
    if(channel==="app"&&!appPayEnabled(env))throw new RequestError("APP支付尚未开放",503,"PAYMENT_APP_DISABLED");
    if(!validOrderId(input.id)||!Object.hasOwn(PAYMENT_PLANS,input.plan)||!/^[a-f0-9]{64}$/.test(input.memberId))throw new RequestError("订单参数无效");
    if(order) {
      sameConfig(config,order);
      if(order.memberId!==input.memberId||order.plan!==input.plan||(order.channel??"web")!==channel)throw new RequestError("该请求编号已用于另一套餐或支付渠道",409);
    }else{
      const now=Date.now(),plan=input.plan as PaymentPlan;
      order={id:input.id,memberId:input.memberId,plan,days:PAYMENT_PLANS[plan],totalCents:config.prices[plan],
        channel,mode:config.mode,appId:config.appId,sellerId:config.sellerId,createdAt:now,expiresAt:now+30*60000,
        access:await mac(env,"checkout-v1:"+input.id),status:"PENDING"};await save();
    }
    return json({ok:true,order:publicOrder(order),...((order.channel??"web")==="web"?{checkoutUrl:`${config.origin}/pay/start?order=${order.id}&access=${order.access}`}:{})});
  }
  if(!order)throw new RequestError("订单不存在",404,"PAYMENT_ORDER_NOT_FOUND");
  sameConfig(config,order);
  if(action==="app") {
    if(input.memberId!==order.memberId)throw new RequestError("无权支付该订单",403);
    if(order.channel!=="app")throw new RequestError("订单支付渠道不匹配",409);
    if(!appPayEnabled(env))throw new RequestError("APP支付尚未开放",503,"PAYMENT_APP_DISABLED");
    if(order.status!=="PENDING"||order.expiresAt<=Date.now())throw new RequestError("订单已结束或超时，请先查询原订单",409,"PAYMENT_ORDER_EXPIRED");
    const orderStr=paymentSdk(config).sdkExecute("alipay.trade.app.pay",{
      timestamp:alipayTime(),
      ...(config.origin.startsWith("https:")?{notifyUrl:`${config.origin}/v1/payments/alipay/notify`}:{}),
      bizContent:{out_trade_no:order.id,total_amount:amount(order.totalCents),subject:`帝三资料库${labels[order.plan]}${order.mode==="sandbox"?"沙箱测试":""}`,
        product_code:"QUICK_MSECURITY_PAY",seller_id:config.sellerId,time_expire:alipayTime(order.expiresAt)}});
    return json({ok:true,order:publicOrder(order),orderStr,mode:config.mode});
  }
  if(["status","query","page","return"].includes(action)) {
    const owner=input.memberId===order.memberId;
    const link=typeof input.access==="string"&&equal(input.access,order.access)&&Date.now()<order.createdAt+30*86400000;
    if(!owner&&!link)throw new RequestError("无权查看该订单",403);
  }
  if(action==="page") {
    if(order.channel==="app")throw new RequestError("请在APP内支付此订单",409);
    if(order.status!=="PENDING"||order.expiresAt<=Date.now())return resultPage("订单已结束或超时","请返回APP查询付款结果，需要再次购买时创建新订单。");
    const returnUrl=`${config.origin}/pay/return?order=${order.id}&access=${order.access}`;
    const html=paymentSdk(config).pageExec("alipay.trade.page.pay","POST",{
      timestamp:alipayTime(),returnUrl,
      ...(config.origin.startsWith("https:")?{notifyUrl:`${config.origin}/v1/payments/alipay/notify`}:{}),
      bizContent:{out_trade_no:order.id,total_amount:amount(order.totalCents),subject:`帝三资料库${labels[order.plan]}${order.mode==="sandbox"?"沙箱测试":""}`,
        product_code:"FAST_INSTANT_TRADE_PAY",seller_id:config.sellerId,time_expire:alipayTime(order.expiresAt)}});
    const page=`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>正在前往支付宝</title><style>body{font:16px/1.8 system-ui;padding:36px;color:#24394f}button{padding:12px 20px}small{color:#64748b}</style><h1>正在前往支付宝${order.mode==="sandbox"?"沙箱":""}收银台</h1><p>如果没有自动跳转，请点击下方按钮。请勿重复付款。</p>${html.replace("</form>","<button type=\"submit\">继续前往支付宝</button></form>")}<p><small>付款结果由服务器核实，关闭页面不会自动开通会员。</small></p></html>`;
    return new Response(page,{headers:{"content-type":"text/html;charset=utf-8","cache-control":"no-store","referrer-policy":"no-referrer",
      // Alipay's gateway redirects form submissions to its cashier subdomains.
      // Chrome checks that redirect chain against form-action as well.
      "content-security-policy":"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; form-action https://*.alipaydev.com https://*.alipay.com; base-uri 'none'; frame-ancestors 'none'"}});
  }
  const fulfill=async()=>{
    if(order!.status!=="PAID"||order!.fulfilledAt)return;
    await memberEntitlement(env,order!,"grant");order!.fulfilledAt=Date.now();await save();
  };
  const recordPaid=async(result:Record<string,any>,sellerRequired:boolean)=>{
    matchTrade(config,order!,result,sellerRequired);
    if(refundEvent(result)||["REFUNDED","REFUND_PENDING"].includes(order!.status))return;
    // Payment can race our close/query. Verified success wins over local CLOSED.
    if(["TRADE_SUCCESS","TRADE_FINISHED"].includes(result.trade_status)){
      order!.status="PAID";order!.tradeNo=result.trade_no;order!.paidAt ||=Date.now();await save();await fulfill();
    }else if(result.trade_status==="TRADE_CLOSED"&&order!.status==="PENDING"){
      order!.status="CLOSED";order!.tradeNo=result.trade_no;await save();
    }
  };
  const query=async()=>{
    if(order!.status==="PAID"){await fulfill();return;}
    if(order!.status!=="PENDING")return;
    if(Date.now()-(order!.lastQueryAt||0)<5000)return;
    order!.lastQueryAt=Date.now();await save();
    const result=await tradeCall(config,"alipay.trade.query",{out_trade_no:order!.id});
    if(result.code!=="10000"){
      if(result.sub_code==="ACQ.TRADE_NOT_EXIST"){
        // Do not strand a never-submitted expired SDK order forever. Keep a
        // clock-skew grace period; a verified late success still wins CLOSED.
        if(Date.now()>order!.expiresAt+60000){order!.status="CLOSED";await save();}
        return;
      }
      throw new RequestError("交易结果暂未确认，请稍后重试",503,"PAYMENT_RESULT_UNKNOWN");
    }
    await recordPaid(result,false);
  };
  if(action==="notify") {
    const params=input.params as Record<string,string>;
    if(params.app_id!==config.appId)throw new RequestError("支付应用不一致");
    matchTrade(config,order,params,true);
    if(refundEvent(params)){
      order.tradeNo=params.trade_no;
      order.externalRefund=true;
      if(params.refund_fee && cents(params.refund_fee)===order.totalCents){
        order.status="REFUNDED";await save();await memberEntitlement(env,order,"refund");
      }else if(order.status!=="REFUNDED"){
        // Partial/external refunds require reconciliation. Never re-grant on
        // a delayed payment notification and never issue a second full refund.
        order.status="REFUND_PENDING";await save();
      }
    }else{
    await recordPaid(params,true);
    }
    if(!order.events?.some(e=>e.notifyId===params.notify_id)){
      order.events=[...(order.events||[]),{at:Date.now(),kind:refundEvent(params)?"refund-notify":"payment-notify",notifyId:params.notify_id}].slice(-50);await save();
    }
    return json({ok:true});
  }
  if(action==="query"||action==="admin-query"||action==="return")await query();
  if(action==="return")return resultPage(order.mode==="sandbox"?"沙箱付款结果":"付款结果",
    order.status==="PAID"?(order.mode==="sandbox"?"已确认沙箱付款成功，未增加真实会员时长。":order.fulfilledAt?"付款成功，会员已开通或顺延。":"付款成功，会员同步中，请稍后查询。"):
    order.status==="PENDING"?"尚未确认付款，请勿重复支付，可稍后返回APP查询。":order.status==="REFUNDED"?"该订单已退款。":"该订单已关闭或正在处理退款。");
  if(action==="close") {
    await query();
    if(order.status==="PAID")throw new RequestError("订单已支付，不能关闭，请按退款流程处理",409);
    if(order.status==="PENDING"){
      const result=await tradeCall(config,"alipay.trade.close",{out_trade_no:order.id});
      if(result.code!=="10000")throw new RequestError("关单结果尚未确认，请查询原订单",503);
      if(result.out_trade_no!==order.id)throw new RequestError("关单订单不一致");
      order.status="CLOSED";await save();
      order.events=[...(order.events||[]),{at:Date.now(),kind:"admin-close",actor:input.actor}].slice(-50);await save();
    }
  }
  const confirmRefund=async(result:Record<string,any>)=>{
    if(result.out_trade_no!==order!.id||result.trade_no!==order!.tradeNo||cents(String(result.refund_amount??result.refund_fee))!==order!.totalCents)throw new RequestError("退款核对失败");
    // Persist a terminal payment state before reversing membership. Retries
    // still call the member's durable idempotent reversal after a lost reply.
    order!.status="REFUNDED";await save();await memberEntitlement(env,order!,"refund");
  };
  if(action==="refund") {
    if(order.externalRefund)throw new RequestError("该订单有外部退款记录，请先在支付宝核对，不可再次发起整单退款",409);
    if(order.status==="PENDING")await query();
    if(!["PAID","REFUND_PENDING","REFUNDED"].includes(order.status))throw new RequestError("只有已付款订单可退款",409);
    if(order.refund && (order.refund.id!==input.requestId||order.refund.reason!==input.reason))throw new RequestError("已有退款请求，请查询原请求，不要重复发起",409);
    if(!order.refund){
      if(typeof input.reason!=="string"||input.reason.length<1||input.reason.length>120||!/^[a-f0-9-]{36}$/i.test(input.requestId))throw new RequestError("退款参数无效");
      order.refund={id:input.requestId,reason:input.reason,amountCents:order.totalCents,requestedAt:Date.now(),actor:input.actor};
      order.status="REFUND_PENDING";await save();
      order.events=[...(order.events||[]),{at:Date.now(),kind:"admin-refund",actor:input.actor}].slice(-50);await save();
    }
    if(order.status==="REFUNDED")await memberEntitlement(env,order,"refund");
    else {
      const r=await tradeCall(config,"alipay.trade.refund",{out_trade_no:order.id,refund_amount:amount(order.totalCents),refund_reason:order.refund.reason,out_request_no:order.refund.id});
      if(r.code==="10000"&&r.fund_change==="Y")await confirmRefund(r);
      // Unknown/N response stays pending. The same request id is retained.
    }
  }
  if(action==="refund-query") {
    if(!order.refund)throw new RequestError("没有退款申请",409);
    if(order.status==="REFUNDED")await memberEntitlement(env,order,"refund");
    else if(Date.now()-order.refund.requestedAt>=10000){
      const r=await tradeCall(config,"alipay.trade.fastpay.refund.query",{out_trade_no:order.id,out_request_no:order.refund.id});
      if(r.code==="10000"&&r.refund_status==="REFUND_SUCCESS"){
        if(r.out_request_no!==order.refund.id)throw new RequestError("退款编号不一致");
        await confirmRefund(r);
      }
    }
  }
  if(!["status","query","admin-query","notify","close","refund","refund-query"].includes(action))throw new RequestError("支付操作不存在",404);
  return json({ok:true,order:publicOrder(order)});
}
