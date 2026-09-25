import {readFile,lstat} from "node:fs/promises";
import {fileURLToPath} from "node:url";
import {resolve,dirname} from "node:path";
import {execFileSync} from "node:child_process";
import {createHash} from "node:crypto";
import {Miniflare} from "miniflare";
import {AlipaySdk} from "alipay-sdk";

// Always resolve from this source file, never caller cwd. Credentials stay in
// the official skill-created file and process memory, not generated bundles.
const root=resolve(dirname(fileURLToPath(import.meta.url)),"..");
export async function loadSandbox() {
  const path=resolve(root,".alipay-sandbox.json"),stat=await lstat(path);
  if(!stat.isFile()||stat.isSymbolicLink()||(stat.mode&0o777)!==0o600)throw new Error("沙箱文件权限必须为0600且不是符号链接");
  const tracked=execFileSync("git",["ls-files","--",".alipay-sandbox.json"],{cwd:root,encoding:"utf8"});
  if(tracked.trim())throw new Error("沙箱配置不得被版本控制跟踪");
  const raw=JSON.parse(await readFile(path,"utf8"));const app=raw.appIds?.[0],seller=raw.sandboxAccounts?.partner?.userId;
  if(!app?.appId||!app.appPrivatePkcsKey||!app.alipayPublicKey||!seller)throw new Error("官方沙箱字段不完整");
  return {appId:app.appId,privateKey:app.appPrivatePkcsKey,alipayPublicKey:app.alipayPublicKey,
    sellerId:seller,keyType:"PKCS1",signType:"RSA2",camelcase:false,timeout:8000,
    gateway:"https://openapi-sandbox.dl.alipaydev.com/gateway.do"};
}
async function main(){
  const config=await loadSandbox();
  const sdk=new AlipaySdk({...config});
  if(process.argv.includes("--verify-config")){
    if(sdk.config.appId!==config.appId||sdk.config.gateway!==config.gateway||sdk.config.signType!=="RSA2"||sdk.config.keyType!=="PKCS1")throw new Error("SDK配置不匹配");
    // Signing only: no gateway request, no payment, no credentials in output.
    const signed=new URLSearchParams(sdk.sdkExecute("alipay.trade.app.pay",{bizContent:{
      out_trade_no:"sandbox-config-check",total_amount:"0.01",subject:"配置签名检查",product_code:"QUICK_MSECURITY_PAY"}}));
    if(signed.get("method")!=="alipay.trade.app.pay"||signed.get("app_id")!==config.appId||signed.get("sign_type")!=="RSA2"||!signed.get("sign"))throw new Error("APP签名配置不匹配");
    console.log("沙箱加载器：直接读取受保护原文件；Node.js PKCS1、RSA2、固定沙箱网关已核对。私钥未输出。");return;
  }
  execFileSync(process.execPath,[resolve(root,"node_modules/wrangler/bin/wrangler.js"),"deploy","--dry-run","--config","wrangler.sandbox.jsonc","--outdir",".wrangler/payment-sandbox-build"],{cwd:root,stdio:["ignore","pipe","pipe"]});
  const port=Number(process.env.DWPM_PAYMENT_SANDBOX_PORT||18789);
  if(!Number.isInteger(port)||port<1024||port>65535)throw new Error("Invalid local port");
  const origin=`http://127.0.0.1:${port}`;
  const mf=new Miniflare({host:"127.0.0.1",port,modules:true,scriptPath:resolve(root,".wrangler/payment-sandbox-build/sandbox-entry.js"),
    compatibilityDate:"2026-07-30",compatibilityFlags:["nodejs_compat"],
    outboundService: async request => {
      // Local workerd uses the host's HTTPS stack. Keep the same gateway-only
      // boundary as the deployed Worker transport; never forward to production.
      const target=new URL(request.url);
      if(target.origin!=="https://openapi-sandbox.dl.alipaydev.com"||target.pathname!=="/gateway.do")return new Response("Sandbox gateway only",{status:403});
      const headers={};request.headers.forEach((v,k)=>{if(!["host","content-length"].includes(k.toLowerCase()))headers[k]=v;});
      const response=await fetch(request.url,{method:request.method,headers,
        body:await request.arrayBuffer(),redirect:"error",signal:AbortSignal.timeout(10000)});
      return new Response(await response.arrayBuffer(),{status:response.status,headers:{"content-type":response.headers.get("content-type")||"application/json"}});
    },
    durableObjects:{RUNTIME_CONFIG:{className:"RuntimeConfigStore",useSQLite:true}},
    resourcePersistencePath:resolve(root,".wrangler/payment-sandbox-state"),
    bindings:{ALIPAY_MODE:"sandbox",ALIPAY_ENABLED:"true",ALIPAY_APP_ID:config.appId,ALIPAY_PRIVATE_KEY:config.privateKey,
      ALIPAY_PUBLIC_KEY:config.alipayPublicKey,ALIPAY_SELLER_ID:config.sellerId,ALIPAY_ORIGIN:origin,
      ALIPAY_PLAN_PRICES:JSON.stringify({month:"0.01",quarter:"0.01",year:"0.01"}),
      MEMBER_AUTH_SECRET:createHash("sha256").update("sandbox-local-only:"+config.privateKey).digest("hex")}});
  try {await mf.ready;}catch(error){await mf.dispose();throw error;}
  console.log(`本地沙箱付款入口：${origin}/sandbox`);
  console.log(`本地回跳页：${origin}/pay/return`);
  console.log("仅沙箱。无生产部署，无真实会员加时；公网通知待验证。");
  for(const signal of ["SIGINT","SIGTERM"])process.once(signal,async()=>{await mf.dispose();process.exit(0);});
}
if(process.argv[1]===fileURLToPath(import.meta.url))main().catch(()=>{console.error("沙箱启动或配置校验失败；敏感配置与SDK响应已隐藏，请检查本地环境和受保护文件。");process.exitCode=1;});
