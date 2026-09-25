import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source=readFileSync(new URL("../../电脑端辅助前端/app.js",import.meta.url),"utf8");
const header=source.slice(source.indexOf("function updateAccountHeader() {"),source.indexOf("function proxySelectValue("));
function page() {
  const nodes=new Map(),listeners=new Map();
  for(const key of [".open-count",".expire-label",".enabled-text",".renew-btn"])nodes.set(key,{textContent:"",dataset:{}});
  const window={DWPMNativeApi:{},addEventListener:(name,fn)=>listeners.set(name,fn)};
  const appState={accounts:[],sessionId:""};
  const context=vm.createContext({window,appState,
    document:{querySelector:q=>nodes.get(q)||null,getElementById:()=>null},
    liveRoleState:()=>({}),selectedAccount:()=>appState.accounts[0],accountProximityCompare:()=>0,
    accountTasksStarted:a=>a.tasksStarted,accountStatusText:s=>s==="online"?"游戏已登录":"游戏已停止",
    accountReconnectStatusText:()=>"",accountStatusClass:()=>"",renderRecentRequestDots(){},renderProxySelect(){}});
  vm.runInContext(readFileSync(new URL("../../电脑端辅助前端/membership-view.js",import.meta.url),"utf8"),context);
  vm.runInContext(header+";globalThis.refresh=updateAccountHeader;",context);
  return {window,appState,nodes,refresh:context.refresh,
    set:state=>{window.DwpmMembershipState=state;listeners.get("dwpm-membership-updated")();}};
}
const member={email:"a@example.com",plan:"month",expiresAt:1792597714886};
const active={required:true,authenticated:true,allowed:true,code:"MEMBER_ACTIVE",member};

test("a paid member without game accounts is not described as logged out or expired",()=>{
  const p=page();p.set(active);
  assert.equal(p.nodes.get(".expire-label").textContent,"会员有效");
  assert.match(p.nodes.get(".expire-label").title,/有效期至.*2026.*10.*21/);
  assert.equal(p.nodes.get(".open-count").textContent,"游戏账号未添加");
  assert.equal(p.nodes.get(".enabled-text").textContent,"未添加游戏账号");
});
test("authorization recovery clears the assistant's stale member pause immediately",()=>{
  const p=page();p.appState.accounts=[{status:"online",started:true,tasksStarted:true}];
  p.set({...active,allowed:false,code:"MEMBER_CHECK_REQUIRED"});
  assert.match(p.nodes.get(".enabled-text").textContent,/会员暂停/);
  p.set(active);
  assert.equal(p.nodes.get(".expire-label").textContent,"会员有效");
  assert.equal(p.nodes.get(".enabled-text").textContent,"游戏已登录");
  assert.equal(p.nodes.get(".open-count").textContent,"游戏 1 开");
});
test("network and recheck states are distinct from expired membership",()=>{
  const p=page();
  for(const [code,label] of [["MEMBER_NETWORK_UNAVAILABLE","暂无法验证"],["MEMBER_CHECK_REQUIRED","待检查授权"],["MEMBER_SESSION_REPLACED","本机已下线"],["MEMBER_DISABLED","账号已停用"]]){
    p.set({...active,allowed:false,code});assert.equal(p.nodes.get(".expire-label").textContent,label);
  }
});
test("only an explicit expired status says expired; a new member says not activated",()=>{
  const p=page();p.set({...active,allowed:false,code:"MEMBER_EXPIRED"});
  assert.equal(p.nodes.get(".expire-label").textContent,"会员已到期");
  p.set({...active,allowed:false,code:"MEMBER_EXPIRED",member:{...member,expiresAt:0}});
  assert.equal(p.nodes.get(".expire-label").textContent,"会员未开通");
});
test("header rerenders and tab switches do not invent a different membership status",()=>{
  const p=page();p.set(active);
  for(let i=0;i<5;i++)p.refresh();
  assert.equal(p.nodes.get(".expire-label").textContent,p.window.DwpmMembershipPresentation.present(active).label);
  delete p.window.DWPMNativeApi;p.refresh();assert.equal(p.nodes.get(".expire-label").textContent,"本地运行");
});
