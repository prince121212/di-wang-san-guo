import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import assert from 'node:assert/strict';
const src=readFileSync(new URL('../../电脑端辅助前端/app.js',import.meta.url),'utf8');
const section=src.slice(src.indexOf('function accountStartNotice('),src.indexOf('async function startSelectedAccount()'));
function harness(mobile,ready,broken=false){
  const calls=[];
  const c=vm.createContext({isMobileLocal:mobile,fetch:async()=>{calls.push('check');if(broken)throw Error('unavailable');return {ok:true,json:async()=>({ok:true,reliableHostingReady:ready})}},
    openNativeGuideView:()=>calls.push('guide'),renderBackgroundPermissionGuide(){},appendLog(){},showToast:()=>calls.push('notice')});
  vm.runInContext(section,c);return {c,calls};
}
test('missing permissions warn without navigating away or blocking game login',async()=>{
  const {c,calls}=harness(true,false);await c.warnAboutMobileHostingPermissions();
  assert.deepEqual(calls,['check','notice']);
  const start=src.slice(src.indexOf('async function startSelectedAccount()'),src.indexOf('async function stopSelectedAccount()'));
  assert.match(start,/void warnAboutMobileHostingPermissions\(\)/);
  assert.doesNotMatch(start,/await (?:ensure|warnAbout)MobileHostingPermissions/);
  assert.match(start,/apiPost\("\/api\/accounts\/start"/);
});
test('ready mobile or desktop is not blocked by optional permissions',async()=>{
  const ready=harness(true,true);await ready.c.warnAboutMobileHostingPermissions();assert.deepEqual(ready.calls,['check']);
  const desktop=harness(false,false);await desktop.c.warnAboutMobileHostingPermissions();assert.deepEqual(desktop.calls,[]);
});
test('unavailable permission check is advisory rather than a rejected start',async()=>{
  const {c,calls}=harness(true,false,true);await assert.doesNotReject(c.warnAboutMobileHostingPermissions());assert.deepEqual(calls,['check']);
});
test('guide describes optional settings instead of a launch prerequisite',()=>{
  const html=readFileSync(new URL('../../电脑端辅助前端/index.html',import.meta.url),'utf8');
  const guide=html.slice(html.indexOf('<article id="backgroundSettingsGuide"'),html.indexOf('<article id="dungeonGuide"'));
  assert.match(guide,/为什么建议设置/);assert.match(guide,/不开启也可以启动账号和任务/);
  assert.doesNotMatch(guide,/为什么必须设置|必要权限通过后|连续请求游戏服的必要条件/);
});
test('stopped and unknown states do not claim a network disconnection',()=>{
  const {c}=harness(true,true);
  for(const status of ['stopped',undefined,'unknown'])assert.doesNotMatch(c.accountStartNotice(status).message,/掉线/);
  assert.match(c.accountStartNotice('offline').message,/掉线/);
});
