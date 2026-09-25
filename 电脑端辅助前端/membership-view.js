// Presentation only: never grants authority or infers authorization from phone time.
(() => {
  "use strict";
  const dates = new Intl.DateTimeFormat("zh-CN", {year:"numeric",month:"2-digit",day:"2-digit"});
  const times = new Intl.DateTimeFormat("zh-CN", {year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false});
  function present(state) {
    const member=state?.member||{};
    const expires=Number(member.expiresAt);
    const hasExpiry=Number.isFinite(expires)&&expires>0;
    const date=hasExpiry?dates.format(expires):"尚未开通";
    const dateTime=hasExpiry?times.format(expires):"尚未开通";
    let label="正在检查",tone="pending",hint="正在读取本机会员授权，请稍候。";
    if(state?.allowed) {
      label="会员有效";tone="active";hint="本机已获授权，可前往助手启动游戏账号。";
    } else if(state && !state.authenticated) {
      label="会员未登录";tone="neutral";hint="登录会员后，即可查看权益与本机授权。";
    } else if(state) {
      const reasons={
        MEMBER_EXPIRED:[hasExpiry?"会员已到期":"会员未开通","expired",hasExpiry?"请联系管理员续期，再重新检查授权。":"账号已注册，请联系管理员开通会员。"],
        MEMBER_DISABLED:["账号已停用","paused","请联系管理员处理，游戏数据仍保留在本机。"],
        MEMBER_SESSION_REPLACED:["本机已下线","paused","会员已在另一会话登录，请查看下方说明。"],
        MEMBER_SESSION_REVOKED:["登录已撤销","paused","管理员已撤销本机登录，请重新登录。"],
        MEMBER_PASSWORD_CHANGED:["需重新登录","paused","会员密码已修改，请使用新密码登录。"],
        MEMBER_SESSION_INVALID:["需重新登录","paused","本机登录凭证已失效，请重新登录。"],
        MEMBER_SESSION_EXPIRED:["需重新登录","paused","本机登录已过期，请重新登录。"],
        MEMBER_NETWORK_UNAVAILABLE:["暂无法验证","pending","请检查网络后重试，这不代表会员已到期。"],
      };
      [label,tone,hint]=reasons[state.code]||["待检查授权","pending","请联网检查本机授权，会员有效期与运行许可分别显示。"];
    }
    return {label,tone,hint,date,dateTime,hasExpiry,
      deadline:hasExpiry?"有效期至 "+date:"尚未开通会员",
      plan:({month:"月卡会员",quarter:"季卡会员",year:"年卡会员"})[member.plan]||"会员服务"};
  }
  window.DwpmMembershipPresentation={present};
})();
