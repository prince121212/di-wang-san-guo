import { getBuiltinModule } from "node:process";
// Some Worker implementations enable util.debuglog independently of NODE_DEBUG.
// Preserve native utilities, but never let the SDK log signed requests/responses.
const native = getBuiltinModule("node:util") as typeof import("node:util");
export const {inherits,promisify,callbackify,inspect,format,formatWithOptions,types,TextDecoder,TextEncoder,parseArgs,isDeepStrictEqual}=native;
export function debuglog(section:string,callback?:unknown) {
  if(section.toLowerCase().startsWith("alipay-sdk"))return Object.assign(()=>{}, {enabled:false});
  return native.debuglog(section,callback as never);
}
export const debug=debuglog;
export default {...native,debuglog,debug};
