import {execFileSync,spawnSync} from "node:child_process";
import {existsSync,statSync} from "node:fs";
import {dirname,resolve} from "node:path";
import {fileURLToPath} from "node:url";

// Android signing only. Never reads or configures an Alipay production private key.
const root=resolve(dirname(fileURLToPath(import.meta.url)),"..");
const args=process.argv.slice(2);
const keyPath=args[0]==="--keystore"&&args.length===2?resolve(args[1]):process.env.DWPM_RELEASE_KEYSTORE;
if(!keyPath||!existsSync(keyPath)||!statSync(keyPath).isFile()){
  console.error("请通过 --keystore 指定既有 Android 发布签名文件；不会生成新签名。");process.exit(1);
}
let password=process.env.DWPM_RELEASE_STORE_PASSWORD;
if(!password){
  try{password=execFileSync("/usr/bin/security",["find-generic-password","-s","dwpm-release-keystore-password","-w"],
    {encoding:"utf8",stdio:["ignore","pipe","pipe"]}).trim();}
  catch{console.error("无法读取既有 Android 发布签名凭据，请由所有者在本机配置。凭据不会输出。");process.exit(1);}
}
if(!password){console.error("Android 发布签名凭据为空，停止构建。");process.exit(1);}
const result=spawnSync(resolve(root,"gradlew"),[":app:assembleRelease","--console=plain"],{
  cwd:root,stdio:"inherit",env:{...process.env,DWPM_RELEASE_KEYSTORE:keyPath,DWPM_RELEASE_STORE_PASSWORD:password}
});
password=undefined;
if(result.error){console.error("无法启动构建，请检查本机 Java/Gradle 环境。");process.exit(1);}
process.exit(result.status??1);
