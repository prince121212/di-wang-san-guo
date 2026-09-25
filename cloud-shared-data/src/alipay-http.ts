/** Worker-only urllib transport for the official SDK. Signing, pageExec and
 * response/notification verification remain the SDK's unmodified implementation.
 * Only the form POST shape used by exec() is supported; no redirects or proxies. */
export class Agent { constructor(_options?: unknown) {} }
export class ProxyAgent { constructor() { throw new Error("Payment proxies are not supported"); } }
export async function request(url: string, options: {
  method: string; data: Record<string, unknown>; dataType: string;
  timeout?: number; headers?: Record<string, string>;
}) {
  const target = new URL(url);
  if (target.protocol !== "https:" || !["openapi.alipay.com", "openapi-sandbox.dl.alipaydev.com"].includes(target.hostname)
    || target.pathname !== "/gateway.do" || target.port || target.username || target.password
    || options.method !== "POST" || options.dataType !== "text") throw new Error("Unsupported payment transport");
  const body = new URLSearchParams();
  for (const [key,value] of Object.entries(options.data)) {
    if (typeof value !== "string" && typeof value !== "number") throw new Error("Invalid SDK form parameter");
    body.append(key,String(value));
  }
  const result = await fetch(target.toString(), { method:"POST", redirect:"manual",
    headers:{...options.headers,"content-type":"application/x-www-form-urlencoded;charset=UTF-8"},
    body:body.toString(),signal:AbortSignal.timeout(Math.min(options.timeout||8000,10000)) });
  if(result.status>=300&&result.status<400)throw new Error("Payment gateway redirect rejected");
  const data = await result.text();
  if (data.length > 131072) throw new Error("Payment response too large");
  const headers:Record<string,string>={};result.headers.forEach((value,key)=>{headers[key]=value;});
  return { status:result.status, headers, data };
}
export default { request };
