(() => {
  "use strict";
  if (!window.DWPMNativeApi) return;
  const mount = document.getElementById("homeMembershipSlot");
  if (!mount) return;
  let mode = "login", busy = false, challenge = null, countdownUntil = 0, stateRevision = 0;
  const panel = document.createElement("section");
  panel.id = "membershipPanel";
  panel.innerHTML = `<header class="member-page-heading"><div><span class="member-eyebrow">帝王三国 · 会员服务</span><h2>会员中心</h2></div><span class="member-local-badge">本机运行</span></header>
    <section class="member-card member-hero"><div class="member-hero-top"><span id="memberPlanName">会员服务</span><span id="memberStatusBadge" role="status">正在检查</span></div>
      <p class="member-identity" id="memberIdentity">尚未登录</p><div class="member-validity"><span>会员有效期至</span><strong id="memberExpiryDate">—</strong></div>
      <p id="memberStatusText">正在读取会员状态…</p><div class="member-entitlements"><span>单手机授权</span><span>本机双账号</span><span>本地保存配置</span></div></section>
    <p id="memberNotice" class="member-warning" role="alert" hidden></p>
    <section id="memberSessionActions" class="member-card" hidden><div class="member-section-heading"><h3>本机授权</h3><span id="memberCheckHint"></span></div>
      <p class="member-copy">启动游戏账号时检查，运行期间每两小时复核。</p><button type="button" class="member-primary" id="memberRecheck">重新检查授权</button>
      <div class="member-account-actions"><button type="button" id="memberRelogin">重新登录此手机</button><button type="button" id="memberLogout">退出会员</button></div></section>
    <section id="memberTransfer" class="member-card" hidden><h3>换手机：导出 / 导入配置</h3>
      <p class="member-copy">导出会把本机的游戏账号、游戏密码和各功能设置保存到当前会员账号下；换手机后登录会员，点“导入配置”即可恢复。游戏密码用会员密码加密，服务器无法查看。</p>
      <label>会员密码<input id="memberTransferPassword" type="password" maxlength="128" autocomplete="current-password" placeholder="导出和导入时都需要输入"></label>
      <div class="member-transfer-actions"><button type="button" class="member-primary" id="memberConfigExport">导出配置</button><button type="button" id="memberConfigImport">导入配置</button></div>
      <p id="memberTransferFeedback" class="member-copy" role="status" hidden></p></section>
    <form id="memberForm" class="member-card"><h3 id="memberFormTitle">登录会员账号</h3><div class="member-modes"><button type="button" data-mode="login">登录</button>
      <button type="button" data-mode="register">邮箱注册</button><button type="button" data-mode="reset-password">忘记密码</button></div>
      <label>邮箱地址<input id="memberEmailInput" type="email" required autocomplete="username" maxlength="254" placeholder="请输入注册邮箱"></label>
      <label>登录密码<input id="memberPasswordInput" type="password" required minlength="10" maxlength="128" autocomplete="current-password" placeholder="请输入至少10个字符的密码"></label>
      <div id="memberCodeFields" hidden><label>邮箱验证码<input id="memberCodeInput" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" placeholder="6位数字验证码"></label>
        <button type="button" id="memberSendCode">获取验证码</button></div>
      <button id="memberSubmit" class="member-primary" type="submit">登录会员</button><p class="member-form-tip">新注册账号赠送 1 天体验会员<br>会员账号用于授权，与游戏账号分开管理。</p></form>
    <p id="memberFormFeedback" role="status" hidden></p>
    <section id="memberPayment" class="member-card" hidden><h3>支付宝开通</h3><p id="memberPaymentHint" class="member-copy"></p>
      <div id="memberPaymentPlans" class="member-plans"></div><button id="memberPaymentQuery" type="button">查询付款结果</button>
      <p id="memberPaymentFeedback" class="member-copy" role="status"></p></section>
    <section class="member-card member-support"><h3>开通与续期</h3><div class="member-plans"><span>月卡 <b>30天</b></span><span>季卡 <b>90天</b></span><span>年卡 <b>365天</b></span></div>
      <button id="memberStoreOpen" type="button" class="member-primary">查看会员套餐与支付宝付款</button>
      <p class="member-copy">月卡 ¥9.90 · 季卡 ¥25.90 · 年卡 ¥49.90。选择套餐后确认付款，不自动续费；也可联系管理员开通。</p></section>
    <div id="memberUpdateSlot"></div>
    <p class="member-footer">游戏账号与配置保存在本机<br>退出会员不会删除你的游戏数据</p>`;
  // Keep the form inside Home so other pages retain their original layout.
  mount.append(panel);
  const $ = id => document.getElementById(id);
  $("memberStoreOpen").onclick=async()=>{
    if(busy)return;busy=true;
    try{await call("payment-store-open",{});}catch(e){feedback(e.message);}finally{busy=false;}
  };
  const fmt = n => n ? new Date(n).toLocaleString("zh-CN",{hour12:false}) : "未开通";
  function feedback(message) { $("memberFormFeedback").textContent=message;$("memberFormFeedback").hidden=!message; }
  async function call(action, body) {
    const r=await fetch("/api/member/"+action, {method:body===undefined?"GET":"POST",
      headers:{"content-type":"application/json"},...(body===undefined?{}:{body:JSON.stringify(body)})});
    const data=await r.json();
    if (!r.ok || data.ok===false) throw new Error(data.error||data.message||"会员服务暂不可用");
    return data;
  }
  function render(state) {
    stateRevision++;
    window.DwpmMembershipState=state;
    const m=state.member||{};
    const view=window.DwpmMembershipPresentation.present(state);
    $("memberIdentity").textContent=m.email||"尚未登录";
    $("memberPlanName").textContent=view.plan;
    $("memberStatusBadge").textContent=view.label;
    $("memberStatusBadge").dataset.tone=view.tone;
    $("memberExpiryDate").textContent=view.expiry;
    $("memberStatusText").textContent=view.hint;
    $("memberCheckHint").textContent=state.allowed?"已验证":view.label;
    $("memberSessionActions").hidden=!state.authenticated;
    $("memberTransfer").hidden=!(state.authenticated&&state.configTransfer);
    if (!state.authenticated) $("memberForm").hidden=false;
    const notice=$("memberNotice");
    notice.hidden=!state.authenticated||state.allowed;
    if (!notice.hidden) {
      const details=state.details||{};
      notice.textContent=state.code==="MEMBER_SESSION_REPLACED"
        ? details.sameDevice ? "会员账号已在本机重新登录，当前旧会话已失效。请重新登录，游戏账号、设置和记录均已保留。"
          : `会员账号已于 ${fmt(details.otherLoginAtMillis)} 在另一台手机登录${details.otherDeviceName?"（"+details.otherDeviceName+"）":""}。本机授权已失效，自动任务已暂停。游戏账号、设置、记录和未结账本均已保留。如果是本人换手机，请在新手机继续；如非本人操作，建议重置会员密码。`
        : (state.message||"会员授权已暂停")+"。游戏账号、设置、记录和未结账本均已保留。";
      if (state.code==="MEMBER_SESSION_REPLACED") {
        const key=`member-notice:${m.id}:${details.otherLoginAtMillis}`;
        if(!localStorage.getItem(key)) {localStorage.setItem(key,"1");window.alert(notice.textContent);}
      }
    }
    window.dispatchEvent(new Event("dwpm-membership-updated"));
  }
  function switchMode(next) {
    mode=next;challenge=null;$("memberForm").hidden=false;
    $("memberCodeFields").hidden=mode==="login";$("memberCodeInput").required=mode!=="login";
    $("memberCodeInput").value="";$("memberSubmit").textContent=mode==="login"?"登录会员":mode==="register"?"验证邮箱并注册":"验证并重置密码";
    $("memberPasswordInput").autocomplete=mode==="login"?"current-password":"new-password";
    $("memberFormTitle").textContent=mode==="login"?"登录会员账号":mode==="register"?"创建会员账号":"重置登录密码";
    panel.querySelectorAll("[data-mode]").forEach(b=>b.classList.toggle("active",b.dataset.mode===mode));
    feedback("");
  }
  panel.querySelectorAll("[data-mode]").forEach(b=>b.onclick=()=>{if(!busy)switchMode(b.dataset.mode);});
  $("memberEmailInput").addEventListener("input",()=>{challenge=null;});
  $("memberSendCode").onclick=async()=>{
    if(busy||Date.now()<countdownUntil)return;
    const email=$("memberEmailInput").value.trim().toLowerCase();
    const purpose=mode;
    if(!$("memberEmailInput").checkValidity()) {$("memberEmailInput").reportValidity();return;}
    busy=true;$("memberSendCode").disabled=true;
    try {
      const result=await call("send-code",{email,purpose:purpose==="register"?"register":"reset-password",requestId:crypto.randomUUID()});
      countdownUntil=Date.now()+60000;
      if(mode!==purpose||$("memberEmailInput").value.trim().toLowerCase()!==email) {
        challenge=null;feedback("邮箱或操作已更改，请为当前邮箱重新获取验证码。");return;
      }
      challenge={id:result.challengeId,email,purpose};
      feedback(result.delivery==="accepted"?"验证码已发送，有效期15分钟，请查看邮箱或垃圾箱。":"发送结果尚未确认。如果已收到邮件，可以直接验证；未收到可60秒后重试。");
    } catch(e) {feedback(e.message);} finally {busy=false;}
  };
  $("memberForm").onsubmit=async event=>{
    event.preventDefault();if(busy)return;
    const email=$("memberEmailInput").value.trim().toLowerCase(),password=$("memberPasswordInput").value;
    if(mode!=="login"&&(!challenge||challenge.email!==email||challenge.purpose!==mode)) {feedback("请先获取本次操作的邮箱验证码");return;}
    if(mode==="login"&&window.DwpmMembershipState?.authenticated
      && !window.confirm("重新登录会让本机接管会员会话，另一台手机下次校验时将暂停。是否继续？"))return;
    busy=true;$("memberSubmit").disabled=true;
    try {
      const result=await call(mode,{email,password,challengeId:challenge?.id,code:$("memberCodeInput").value.trim()});
      $("memberPasswordInput").value="";$("memberCodeInput").value="";
      if(mode==="login") {render(result);$("memberForm").hidden=true;feedback(result.allowed?"登录成功，可以启动游戏账号。":"登录成功，请联系管理员开通或续期，再点击重新检查授权。");}
      else if(mode==="register"&&!window.DwpmMembershipState?.authenticated) await signInAfterRegister(result,email,password);
      else {switchMode("login");feedback(result.message||"操作成功，请登录");}
    } catch(e) {feedback(e.message);} finally {busy=false;$("memberSubmit").disabled=false;}
  };
  // A new account signs in right away, so the new-user trial works without a second form.
  async function signInAfterRegister(registered,email,password) {
    let state;
    try {state=await call("login",{email,password});}
    catch {switchMode("login");$("memberEmailInput").value=email;feedback(registered.message||"注册成功，请登录");return;}
    render(state);$("memberForm").hidden=true;
    const view=window.DwpmMembershipPresentation.present(state);
    feedback(registered.trial==="granted"&&state.allowed?`注册成功，已赠送 1 天体验会员，有效期至 ${view.dateTime}，现在就可以启动游戏账号。`
      :registered.trial==="unavailable"?"注册成功，已登录。体验会员暂时无法发放，请到 QQ 交流群联系管理员补发。"
      :registered.trial==="used"?"注册成功，已登录。体验会员每人限领一次，本账号未获赠送，可在下方开通会员。"
      :state.allowed?"注册成功，已登录，可以启动游戏账号。":"注册成功，已登录。可在下方开通会员后使用。");
  }
  $("memberRecheck").onclick=async()=>{
    if(busy)return;busy=true;$("memberRecheck").disabled=true;$("memberRecheck").textContent="正在验证…";
    try{const result=await call("check",{force:true});render(result);feedback(result.allowed?"授权已更新，可前往助手启动游戏账号。":result.message||"请根据提示处理会员授权。");}
    catch(e){feedback(e.message);}finally{busy=false;$("memberRecheck").disabled=false;$("memberRecheck").textContent="重新检查授权";}
  };
  $("memberRelogin").onclick=()=>{if(busy)return;switchMode("login");$("memberEmailInput").value=window.DwpmMembershipState?.member?.email||"";$("memberPasswordInput").focus();};
  $("memberLogout").onclick=async()=>{if(busy||!window.confirm("退出会员会暂停自动任务，游戏账号和数据会保留。继续？"))return;busy=true;try{render(await call("logout",{}));switchMode("login");}catch(e){feedback(e.message);}finally{busy=false;}};
  function transferFeedback(message) { $("memberTransferFeedback").textContent=message;$("memberTransferFeedback").hidden=!message; }
  function transferPassword(purpose) {
    const password=$("memberTransferPassword").value;
    if(!password) transferFeedback(`请输入会员密码，用来${purpose}游戏密码。`);
    return password;
  }
  async function transfer(button, pending, work) {
    busy=true;button.disabled=true;transferFeedback(pending);
    try{await work();}catch(e){transferFeedback(e.message);}finally{busy=false;button.disabled=false;}
  }
  $("memberConfigExport").onclick=async()=>{
    if(busy)return;
    const password=transferPassword("加密");if(!password)return;
    if(!window.confirm("导出会覆盖云端上一次导出的配置。确定导出本机全部游戏账号、游戏密码和各功能设置吗？"))return;
    await transfer($("memberConfigExport"),"正在加密并导出，请稍候…",async()=>{
      const r=await call("config-export",{password});
      $("memberTransferPassword").value="";
      transferFeedback(`已导出 ${r.accountCount} 个游戏账号（${r.passwordCount} 个游戏密码、${r.configCount} 项设置），导出时间 ${fmt(r.backupInfo?.exportedAt)}。\n换手机后登录本会员账号，在这里点“导入配置”即可。`);
    });
  };
  $("memberConfigImport").onclick=async()=>{
    if(busy)return;
    const password=transferPassword("解开导出时加密的");if(!password)return;
    await transfer($("memberConfigImport"),"正在读取云端配置…",async()=>{
      const preview=await call("config-import",{password,confirm:false});
      const list=preview.accounts.map(a=>`· ${a.label}${!a.supported?"（本机暂不支持该平台，将跳过）":a.existing?"（本机已有：合并设置，保留本机密码）":"（新增，默认不启动）"}`).join("\n");
      const locked=preview.passwordsReadable?"":"\n\n注意：这份配置是用旧的会员密码导出的，游戏密码无法解开。账号和设置照常导入，之后需要在助手页逐个点“修改”重新输入游戏密码。";
      if(!window.confirm(`云端配置导出于 ${fmt(preview.exportedAt)}${preview.deviceName?"（"+preview.deviceName+"）":""}，包含：\n${list}${locked}\n\n同一功能的设置以云端为准。确定导入吗？`)){transferFeedback("已取消导入。");return;}
      transferFeedback("正在导入…");
      const r=await call("config-import",{password,confirm:true,allowWithoutPasswords:!preview.passwordsReadable});
      $("memberTransferPassword").value="";
      const lines=[`导入完成：新增 ${r.added.length} 个、合并 ${r.merged.length} 个游戏账号，恢复 ${r.configsRestored} 项设置、${r.passwordsRestored} 个游戏密码。`];
      if(r.skipped.length)lines.push(`已跳过（本机暂不支持该平台）：${r.skipped.join("、")}。`);
      if(r.passwordsMissing.length)lines.push(`这些账号还没有游戏密码，请在助手页点“修改”输入：${r.passwordsMissing.join("、")}。`);
      lines.push("导入的账号默认不启动。确认旧手机不再运行这些账号后，再到助手页启动。");
      transferFeedback(lines.join("\n"));
    });
  };
  async function loadPaymentCatalog() {
    try {
      const catalog=await call("payment-catalog");
      if(!catalog.enabled)return;
      $("memberPayment").hidden=false;
      $("memberPaymentHint").textContent=catalog.mode==="sandbox"?"沙箱测试：不扣真实资金，不增加真实会员时长。":"付款后自动开通或续期；最终价格以支付宝收银台为准，不自动扣款。";
      const plans=$("memberPaymentPlans");plans.replaceChildren();
      for(const entry of catalog.plans||[]){
        if(!["month","quarter","year"].includes(entry.plan))continue;
        const button=document.createElement("button");button.type="button";
        button.textContent=`${{month:"月卡",quarter:"季卡",year:"年卡"}[entry.plan]} ¥${entry.totalAmount}`;
        button.onclick=async()=>{
          if(busy)return;
          if(!window.DwpmMembershipState?.authenticated){feedback("请先登录会员账号，再选择套餐。");return;}
          if(!window.confirm(`为当前会员购买${entry.days}天使用权，金额¥${entry.totalAmount}${catalog.mode==="sandbox"?"（沙箱测试，不开通真实会员）":""}？`))return;
          busy=true;button.disabled=true;
          try{const result=await call("payment-create",{plan:entry.plan});
            $("memberPaymentFeedback").textContent=`订单 ${result.order.id} · ¥${result.order.totalAmount}。付款后请返回查询，不要重复付款。`;
            await call("payment-open",{});
          }catch(e){$("memberPaymentFeedback").textContent=e.message;}finally{busy=false;button.disabled=false;}
        };
        plans.append(button);
      }
    }catch{/* Old/offline backends retain the manual activation path. */}
  }
  $("memberPaymentQuery").onclick=async()=>{
    if(busy)return;busy=true;$("memberPaymentQuery").disabled=true;
    try{const {order}=await call("payment-status",{});
      $("memberPaymentFeedback").textContent=order.status==="PAID"?
        order.mode==="sandbox"?"沙箱付款成功，未增加真实会员时长。":order.fulfilled?"付款成功，会员已开通或顺延。":"付款成功，会员同步中，请稍后查询。":
        ({PENDING:"尚未确认付款，请稍后查询。",CLOSED:"订单已关闭。",REFUND_PENDING:"退款处理中。",REFUNDED:"订单已退款。"})[order.status]||"订单状态待确认。";
      if(order.membershipApplied)render(await call("check",{force:true}));
    }catch(e){$("memberPaymentFeedback").textContent=e.message;}finally{busy=false;$("memberPaymentQuery").disabled=false;}
  };
  document.addEventListener("click",e=>{if(e.target.closest?.(".renew-btn")){
    document.querySelector('.bottom-item[data-page="Home"]')?.click();
    panel.scrollIntoView({behavior:"smooth",block:"start"});
    feedback("请向管理员提供会员邮箱开通或续期，完成后点击重新检查授权。");
  }});
  setInterval(()=>{
    const remaining=Math.ceil((countdownUntil-Date.now())/1000);
    $("memberSendCode").disabled=busy||remaining>0;$("memberSendCode").textContent=remaining>0?`${remaining}秒后重发`:"获取验证码";
  },1000);
  setInterval(async()=>{if(!document.hidden&&!busy){
    const revision=stateRevision;
    try{const state=await call("status");if(!busy&&revision===stateRevision)render(state);}catch{/* local UI polling only */}
  }},15000);
  switchMode("login");
  const initialRevision=stateRevision;
  call("check",{force:false}).then(state=>{if(!busy&&stateRevision===initialRevision){render(state);$("memberForm").hidden=state.authenticated;}}).catch(e=>feedback(e.message));
  loadPaymentCatalog();
})();
