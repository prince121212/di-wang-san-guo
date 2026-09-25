(() => {
  "use strict";
  const $=id=>document.getElementById(id);let order=null,busy=false,queryRevision=0;
  const pendingKey="dwpm.admin.refund.pending.v1";
  const report=text=>{$("paymentFeedback").textContent=text;};
  const labels={PENDING:"待付款",PAID:"已付款",CLOSED:"已关闭",REFUND_PENDING:"退款待确认",REFUNDED:"已退款"};
  async function call(action,body){
    const r=await fetch("/admin/api/payments/"+action,{method:"POST",credentials:"same-origin",cache:"no-store",
      headers:{"content-type":"application/json","x-admin-intent":"payment-manage"},body:JSON.stringify(body),signal:AbortSignal.timeout(20000)});
    const value=await r.json();if(!r.ok||!value.ok)throw new Error(value.error||"订单操作未确认");return value.order;
  }
  function render(value){
    order=value;$("paymentDetail").hidden=false;
    $("paymentSummary").textContent=`${value.mode==="sandbox"?"沙箱":"正式"} · ${value.id} · ¥${value.totalAmount} · ${value.days}天 · ${labels[value.status]||"待确认"}`;
    $("paymentClose").disabled=value.status!=="PENDING";
    $("paymentRefund").disabled=!["PAID","REFUND_PENDING"].includes(value.status);
    $("paymentRefundQuery").disabled=!["REFUND_PENDING","REFUNDED"].includes(value.status);
    if(value.status==="REFUNDED"){
      const p=JSON.parse(sessionStorage.getItem(pendingKey)||"null");if(p?.orderId===value.id)sessionStorage.removeItem(pendingKey);
    }else{
      const p=JSON.parse(sessionStorage.getItem(pendingKey)||"null");if(p?.orderId===value.id)$("paymentRefundReason").value=p.reason;
    }
  }
  $("paymentSearch").onsubmit=async e=>{
    e.preventDefault();if(busy)return;const revision=++queryRevision;order=null;$("paymentDetail").hidden=true;
    try{const value=await call("query",{orderId:$("paymentOrderId").value.trim()});if(revision===queryRevision)render(value);}catch(e){if(revision===queryRevision)report(e.message);}
  };
  async function action(kind){
    if(busy||!order)return;
    let body={orderId:order.id};
    if(kind==="close"&&!window.confirm(`关闭未付款订单 ${order.id}？`))return;
    if(kind==="refund"){
      const reason=$("paymentRefundReason").value.trim();if(!reason){report("请填写退款原因");return;}
      if(!window.confirm(`对订单 ${order.id} 整单退款 ¥${order.totalAmount}，并扣回${order.days}天会员时长？`))return;
      const prior=JSON.parse(sessionStorage.getItem(pendingKey)||"null");
      if(prior&&(prior.orderId!==order.id||prior.reason!==reason)){report("还有结果未确认的退款，请先查询原订单或重试原申请。");return;}
      body=prior||{...body,reason,confirm:"refund",requestId:crypto.randomUUID()};
      sessionStorage.setItem(pendingKey,JSON.stringify(body));
    }
    if(kind==="close")body.confirm="close";
    busy=true;
    try{render(await call(kind,body));report(order.status==="REFUND_PENDING"?"退款结果尚未确认，至少10秒后查询退款结果。":"订单状态已更新。");}
    catch(e){report(e.message+"；结果不明时请查询原订单。");}finally{busy=false;}
  }
  $("paymentClose").onclick=()=>action("close");$("paymentRefund").onclick=()=>action("refund");$("paymentRefundQuery").onclick=()=>action("refund-query");
})();
