# 邮箱验证码联通测试（2026-09-21）

本次仅验证 Cloudflare 持久化 → Resend 发信 → 收件人提交验证码的闭环。
不创建用户、开通会员、收款，也不修改旧 wm985 项目或手机游戏账号。

## 保护措施

- 发件人：`帝王三国资料库 <noreply@292828.xyz>`。Resend 已核验域名为 verified，sending enabled。
- 收件人仅允许用户指定的 QQ 邮箱，通过 `EMAIL_PROBE_TO` Secret 配置，不写在公开路由源码中。
- `/ops/email-verification/send`、`verify`、`status` 均要求专用操作令牌；APK Runtime Token 无权调用。
- 入口通过 `EMAIL_PROBE_UNTIL` 设置六小时测试窗口，窗口结束后不再接受请求。
- 验证码六位，最长15分钟有效，只保存绑定邮箱/用途/挑战ID的 HMAC 摘要。
- 使用独立命名的 Cloudflare Durable Object，不读写地图 D1；验证码五次错误即锁定。
- 相同 requestId 不重复发信；60秒冷却，每个测试邮箱每日最多三封；通过验证后拒绝新发送。
- 校验与一次性消费为原子事务；不在返回值或日志中暴露验证码/邮件内容/密钥。
- Resend 超时或不确定回执保留 unknown 状态，不自动生成新验证码重发。

## 本次操作标识（发送前保存，避免中断后重复发信）

- Request ID：`dd832038-b35c-42bd-a95e-42cf1afc2c89`
- 操作令牌保存于本机钥匙串服务 `dwpm-email-probe-operator-token`，不记录明文。
- Resend 凭据来自用户指定的“认证相关/resend.env”，只配置为 Worker Secret。
- 已部署版本：`efaef4af-6052-4713-8c46-39b7b98d9111`，100%流量；没有修改域名路由、游戏任务或云端地图开关。
- 测试窗口截止毫秒：`1789944096151`（2026-09-21 06:41:36 +08:00）。
- 当前阶段：Cloudflare 已发出一次测试请求，Resend 返回 HTTP 200 受理；独立查询确认 `last_event=delivered`，待用户提交收到的验证码完成实际校验。
- Challenge ID：`f020b142-a06e-4b4f-b69a-ccc966e40c2f`。
- Resend Message ID：`01a0bfb3-2ea8-77a9-9236-e853ada321e7`。
- 创建时间：`1789922586122`；验证码到期：`1789923486122`（2026-09-21 00:58:06 +08:00）。
- 未授权调用实际返回 HTTP 401，未触发发信；授权发送返回 `delivery=accepted`、`verified=false`、剩余尝试次数5。
- 后续独立 `/status` 请求读取到相同 Challenge ID 和 Message ID，确认记录保存在 Cloudflare。
- Resend 查询只读取投递元数据，未读取或输出邮件正文和验证码；投递成功不等于用户已经看到收件箱邮件。

## 自动验证

`npm run check && npm test`：95项 Worker 测试及7项页面交互测试通过。
新增16项覆盖鉴权、邮箱归一化/白名单、摘要存储、并发发送幂等、单次校验、错误次数、
过期/旧验证码、冷却/日限额、超时不重发、发送失败可重试及 D1 故障隔离。

真实邮件的发送受理不等于收件人已看到；最终闭环需要用户收到邮件并提交本次测试验证码。
