import { AlipaySdk } from "alipay-sdk";
import type { Env } from "./types";
import { RequestError } from "./validation";

export const PAYMENT_PLANS = {month:30,quarter:90,year:365} as const;
export type PaymentPlan = keyof typeof PAYMENT_PLANS;
export function appPayEnabled(env:Env):boolean {
  return env.ALIPAY_MODE === "sandbox" || env.ALIPAY_APP_PAY_ENABLED === "true";
}
export interface PaymentConfig {
  mode:"sandbox"|"production"; appId:string; privateKey:string; publicKey:string;
  sellerId:string; origin:string; gateway:string; prices:Record<PaymentPlan,number>;
}
export function cents(value: unknown): number {
  if (typeof value !== "string" || !/^(?:0|[1-9]\d{0,8})(?:\.\d{1,2})?$/.test(value)) throw new RequestError("金额格式无效");
  const [whole,decimal=""] = value.split(".");
  const result = Number(whole)*100+Number(decimal.padEnd(2,"0"));
  if (!Number.isSafeInteger(result) || result<=0 || result>10_000_000_000) throw new RequestError("金额超出范围");
  return result;
}
export function amount(value:number):string { return `${Math.floor(value/100)}.${String(value%100).padStart(2,"0")}`; }
export function acceptanceConfigured(env:Env):boolean {
  return env.ALIPAY_MODE==="production" && /^[a-f0-9]{64}$/.test(env.ALIPAY_ACCEPTANCE_MEMBER_ID||"")
    && /^[a-f0-9-]{36}$/i.test(env.ALIPAY_ACCEPTANCE_PURCHASE_ID||"")
    && Number.isSafeInteger(Number(env.ALIPAY_ACCEPTANCE_UNTIL)) && Number(env.ALIPAY_ACCEPTANCE_UNTIL)>0;
}
export function acceptanceOpen(env:Env):boolean {
  const left=Number(env.ALIPAY_ACCEPTANCE_UNTIL)-Date.now();
  return acceptanceConfigured(env)&&left>0&&left<=3600000;
}
export function paymentConfig(env:Env,purpose:"public"|"settlement"="public"):PaymentConfig {
  // Settlement may process the ONE operator-configured acceptance order while
  // public sales remain disabled. This never skips signatures/business checks.
  const acceptance=purpose==="settlement"&&acceptanceConfigured(env);
  if ((!acceptance&&env.ALIPAY_ENABLED!=="true") || !["sandbox","production"].includes(env.ALIPAY_MODE||"")) throw new RequestError("在线支付暂未开放，请联系管理员开通",503,"PAYMENT_DISABLED");
  const mode=env.ALIPAY_MODE as PaymentConfig["mode"];
  if (!acceptance && mode==="production" && env.ALIPAY_LIVE_APPROVED!=="true") throw new RequestError("正式收款尚未验收",503,"PAYMENT_DISABLED");
  if (!env.ALIPAY_APP_ID || !env.ALIPAY_PRIVATE_KEY || !env.ALIPAY_PUBLIC_KEY || !env.ALIPAY_SELLER_ID || !env.ALIPAY_ORIGIN) throw new RequestError("支付配置不完整",503,"PAYMENT_NOT_CONFIGURED");
  const url=new URL(env.ALIPAY_ORIGIN);
  if (url.origin!==env.ALIPAY_ORIGIN || url.username || url.password || (url.protocol!=="https:" && !(mode==="sandbox" && url.protocol==="http:" && ["127.0.0.1","localhost"].includes(url.hostname)))) throw new RequestError("支付回跳地址无效",503);
  let raw:Record<string,unknown>;
  try {raw=JSON.parse(env.ALIPAY_PLAN_PRICES||"{}");}catch{throw new RequestError("套餐价格尚未配置",503);}
  const prices={} as Record<PaymentPlan,number>;
  for(const plan of Object.keys(PAYMENT_PLANS) as PaymentPlan[])prices[plan]=cents(raw[plan]);
  return {mode,appId:env.ALIPAY_APP_ID,privateKey:env.ALIPAY_PRIVATE_KEY,publicKey:env.ALIPAY_PUBLIC_KEY,
    sellerId:env.ALIPAY_SELLER_ID,origin:url.origin,prices,
    gateway:mode==="sandbox"?"https://openapi-sandbox.dl.alipaydev.com/gateway.do":"https://openapi.alipay.com/gateway.do"};
}
export function paymentSdk(config:PaymentConfig):AlipaySdk {
  return new AlipaySdk({appId:config.appId,privateKey:config.privateKey,keyType:"PKCS1",
    alipayPublicKey:config.publicKey,gateway:config.gateway,signType:"RSA2",camelcase:false,timeout:8000});
}
export function alipayTime(millis=Date.now()):string {return new Date(millis+8*3600000).toISOString().slice(0,19).replace("T"," ");}
export async function tradeCall(config:PaymentConfig,method:string,bizContent:Record<string,unknown>) {
  try {
    return await paymentSdk(config).exec(method,{timestamp:alipayTime(),bizContent},{validateSign:true});
  } catch (error) {
    const message=error instanceof Error?error.message:"";
    const category=message.includes("验签")?"signature":message.includes("HTTP 请求错误")?"http-status":message.includes("HttpClient")?"transport":message.includes("格式")?"format":"sdk";
    console.warn("payment gateway result unavailable",{category}); // Never log SDK error objects: they contain signatures.
    throw new RequestError("支付宝响应尚未确认，请稍后查询原订单，勿重复付款",503,"PAYMENT_RESULT_UNKNOWN");
  }
}
export async function notifyParams(request:Request):Promise<Record<string,string>> {
  if (!(request.headers.get("content-type")||"").startsWith("application/x-www-form-urlencoded")) throw new RequestError("通知格式无效");
  const raw=await request.text();if(raw.length>32768)throw new RequestError("通知过大",413);
  const result:Record<string,string>=Object.create(null);
  for(const [key,value] of new URLSearchParams(raw)) {
    if(Object.hasOwn(result,key))throw new RequestError("重复的通知字段");
    result[key]=value;
  }
  return result;
}
export function verifyNotification(config:PaymentConfig,params:Record<string,string>):boolean {
  // The SDK also supports obsolete RSA: pin RSA2 before invoking its verifier.
  return params.sign_type==="RSA2" && params.app_id===config.appId && paymentSdk(config).checkNotifySignV2(params);
}
export function refundEvent(params:Record<string,unknown>):boolean {
  return ["out_biz_no","gmt_refund","refund_fee"].some(k=>Object.hasOwn(params,k));
}
