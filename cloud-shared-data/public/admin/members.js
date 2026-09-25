"use strict";
(() => {
  let rows = [], selected = null, saving = false, nextCursor = null, detailRequest = 0;
  const $ = id => document.getElementById(id);
  const labels = {month:"月卡（30天）",quarter:"季卡（90天）",year:"年卡（365天）"};
  const format = value => value ? new Date(value).toLocaleString("zh-CN",{hour12:false}) : "未开通";
  const text = (element,value) => { element.textContent = String(value ?? ""); return element; };
  const pendingKey = "dwpm.admin.member.pending.v1";
  const pending = () => { try {return JSON.parse(sessionStorage.getItem(pendingKey)||"null");} catch {return null;} };
  async function call(path, body, intent) {
    const result = await fetch(path, {method:body ? "POST":"GET",credentials:"same-origin",cache:"no-store",
      headers:body ? {"content-type":"application/json","x-admin-intent":intent}: {},
      ...(body ? {body:JSON.stringify(body)}:{}), signal:AbortSignal.timeout(15000)});
    const value = await result.json();
    if (!result.ok || !value.ok) {
      const e = new Error(value.error || "会员管理请求失败"); e.status=result.status; throw e;
    }
    return value;
  }
  function report(message, failed=false) {
    $("memberFeedback").textContent=message; $("memberFeedback").classList.toggle("form-error",failed);
  }
  function render() {
    const table=$("memberTableBody"); table.replaceChildren();
    for(const member of rows) {
      const tr=document.createElement("tr");
      for(const value of [member.email,labels[member.plan]||"无",format(member.expiresAt),
        member.disabled?"已停用":member.expiresAt>Date.now()?"有效":"未开通/已到期",member.deviceName||"尚未登录"]) {
        tr.append(text(document.createElement("td"),value));
      }
      const td=document.createElement("td"), button=text(document.createElement("button"),"管理");
      button.type="button";button.className="secondary-button";button.onclick=()=>detail(member.email);
      td.append(button);tr.append(td);table.append(tr);
    }
    $("memberMore").hidden=!nextCursor;
    $("memberEmpty").hidden=rows.length>0;
  }
  async function load(append=false) {
    try {
      const value=await call("/admin/api/members"+(append&&nextCursor?"?after="+encodeURIComponent(nextCursor):""));
      rows=append?[...rows,...value.members]:value.members;nextCursor=value.nextCursor;render();
      if(!rows.length) report("用户需先在新版APP验证邮箱并注册，再由管理员开通会员。");
    } catch(e) {report(e.message,true);}
  }
  async function detail(email, afterSave=false) {
    if (saving && !afterSave) return;
    const request = ++detailRequest;
    selected = null; $("memberDetail").hidden = true;
    try {
      const value=await call("/admin/api/members/query",{email},"member-query");
      if (request !== detailRequest) return;
      selected=value.member;$("memberDetail").hidden=false;
      $("memberSelectedEmail").textContent=selected.email;
      $("memberSelectedState").textContent=`${selected.disabled?"已停用":"可登录"} · 到期 ${format(selected.expiresAt)} · 最近登录 ${format(selected.loginAt)}`;
      $("memberDisable").textContent=selected.disabled?"解除停用":"停用账号";
      const list=$("memberAudit");list.replaceChildren();
      for(const event of (value.audit||[]).slice(-20).reverse()) {
        list.append(text(document.createElement("li"),`${format(event.at)} · ${event.kind} · ${event.actor||event.deviceName||"用户"}${event.note?" · "+event.note:""}`));
      }
      const prior=pending();
      if(prior?.email===selected.email && value.audit?.some(event=>event.requestId===prior.requestId)) {
        sessionStorage.removeItem(pendingKey);report("已核对：上次管理操作已成功，不会重复开通。");
      } else if(prior?.email===selected.email) {
        $("memberPlan").value=prior.plan;$("memberNote").value=prior.note;
        report("上次操作结果尚未确认，已恢复原套餐和备注；重试相同操作将复用原编号，不会重复加时。",true);
      }
    } catch(e) {if (request === detailRequest) report(e.message,true);}
  }
  async function change(action) {
    if(!selected||saving)return;
    const value={email:selected.email,action,plan:$("memberPlan").value,note:$("memberNote").value.trim()};
    if(!window.confirm(action==="grant"?`为 ${value.email} 开通/续期${labels[value.plan]}？未到期的从原到期时间顺延。`
      :action==="disable"?"停用该会员？客户端下次校验后将暂停新任务。"
      :action==="enable"?"解除账号停用？不会自动增加会员时长。":"撤销当前登录？客户端下次校验后需重新登录。"))return;
    const prior=pending();
    if(prior && ["email","action","plan","note"].some(k=>prior[k]!==value[k])) {
      report("上次操作结果尚未确认，请先查询原会员或重试相同操作。",true);return;
    }
    const request=prior||{...value,requestId:crypto.randomUUID()};
    sessionStorage.setItem(pendingKey,JSON.stringify(request));saving=true;
    $("memberDetail").querySelectorAll("button").forEach(b=>b.disabled=true);
    try {
      await call("/admin/api/members/update",request,"member-update");
      sessionStorage.removeItem(pendingKey);report("会员设置已保存；运行中的手机将在下次授权校验时同步。");
      await detail(value.email,true);await load();
    } catch(e) {
      if(e.status && e.status<500)sessionStorage.removeItem(pendingKey);
      report(e.message+(e.status?"":"。结果可能未确认，请查询后重试，不要重复开通。"),true);
    } finally {saving=false;$("memberDetail").querySelectorAll("button").forEach(b=>b.disabled=false);}
  }
  $("memberSearch").onsubmit=e=>{e.preventDefault();detail($("memberEmail").value.trim().toLowerCase());};
  $("memberRefresh").onclick=()=>load();$("memberMore").onclick=()=>load(true);
  $("memberGrant").onclick=()=>change("grant");
  $("memberDisable").onclick=()=>change(selected?.disabled?"enable":"disable");
  $("memberRevoke").onclick=()=>change("revoke");
  window.addEventListener("dwpm-admin-ready",()=>load());
})();
