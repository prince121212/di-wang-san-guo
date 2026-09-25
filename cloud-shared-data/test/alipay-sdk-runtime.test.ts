import {env} from "cloudflare:test";
import {expect,it} from "vitest";
import {AlipaySdk} from "alipay-sdk";
import type {Env} from "../src/types";
import {request} from "../src/alipay-http";
import {vi} from "vitest";
import {debuglog} from "../src/payment-node-util";

it("official SDK signs a payment page in the real Worker runtime",()=>{
  const e=env as unknown as Env;
  const sdk=new AlipaySdk({appId:"test-app",privateKey:String(e.MEMBER_LEASE_PRIVATE_KEY),keyType:"PKCS8",
    alipayPublicKey:String(e.MEMBER_LEASE_PUBLIC_KEY),gateway:"https://openapi-sandbox.dl.alipaydev.com/gateway.do",signType:"RSA2"});
  const page=sdk.pageExec("alipay.trade.page.pay","POST",{bizContent:{out_trade_no:"test-order",total_amount:"0.01",subject:"测试",product_code:"FAST_INSTANT_TRADE_PAY"}});
  expect(page).toContain("<form");expect(page).toContain("openapi-sandbox.dl.alipaydev.com");
});

it("payment debug logging is disabled even when the runtime enables util.debuglog",()=>{
  const log=vi.spyOn(console,"debug");debuglog("alipay-sdk")("private signed request");
  expect(log).not.toHaveBeenCalled();log.mockRestore();
});

it("Worker transport rejects redirects without using unsupported redirect:error",async()=>{
  const f=vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(null,{status:302,headers:{location:"https://evil.invalid"}}));
  await expect(request("https://openapi-sandbox.dl.alipaydev.com/gateway.do",{method:"POST",data:{x:"y"},dataType:"text"})).rejects.toThrow("redirect rejected");
  expect(f.mock.calls[0][1]?.redirect).toBe("manual");f.mockRestore();
});
