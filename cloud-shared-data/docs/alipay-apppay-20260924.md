# Android 原生支付宝会员支付

## 本轮范围

在既有网页收款上新增 APP 支付，不移除网页、管理员开通、查单、退款等功能。
生产收款仍未验收，不能仅凭本地测试或 APK 构建通过开通正式入口。

- Android 新购买请求固定 `channel=app`，服务端固定价格和会员天数。
- `POST /v1/member/payment-app-order`：设备签名及当前会员会话认证，检查订单归属、渠道、状态、有效期，返回 SDK `orderStr`。
- 服务端调用已安装的官方 Node SDK `sdkExecute("alipay.trade.app.pay", ...)`；`QUICK_MSECURITY_PAY`、RSA2、30 分钟有效期、HTTPS 异步通知。
- Android 使用官方 `com.alipay.sdk:alipaysdk-android:15.8.42`，非导出 `AlipayPaymentActivity` 在工作线程调用 `PayTask.payV2`。
- 订单串只在原生内存中使用，不存入 WebView、Intent 或日志。私钥只在服务端。
- SDK 返回任何状态都回查原订单。最多自动回查五次，每次间隔六秒；保留手动查询入口。服务端确认权益后刷新会员授权。
- 取消、未知结果不新建订单；重试保留购买编号。同一购买编号不能改变套餐或支付渠道。
- 沿用旧网页订单，避免更新 APK 后丢失待支付订单。已过期且支付宝验签查询确认不存在的订单，在一分钟宽限期后关闭本地状态；迟到的真实付款通知仍会确认付款。
- 正式 APK 拒绝沙箱；debug/membertest 可测试沙箱。沙箱永不增加真实会员天数。

## 配置和部署

沿用 `alipay-webpay-20260924.md` 的生产配置门槛；另外显式设置
`ALIPAY_APP_PAY_ENABLED=true` 才开放生产 APP 签名接口。
`ALIPAY_ENABLED=true`、`ALIPAY_LIVE_APPROVED=true` 仍必需。缺少配置时不开放收款。
正式应用必须具备 APP 支付权限；不能把网页支付签约视为 APP 支付已开通。
两种渠道当前共用同一服务端支付应用配置，配置切换前必须核对存量订单，不能混用两套应用密钥。

用户自行在 Cloudflare Secrets 配置生产私钥，不发送到聊天。Node SDK 使用 PKCS1 原始值。
APK 包名、正式签名及开放平台应用资料需要匹配并完成平台审核。
月、季、年正式价格、退款规则、客服联系方式和 SDK 隐私披露需要确认后再发布。

本轮只读检查线上 `/v1/payments/catalog` 返回 HTTP 401 / UNAUTHORIZED，未取得有效套餐目录。
这说明当前线上链路尚不能用于这次验收，不能据此推断商户签约状态。
未部署生产 Worker，未更改手机原安装包、未付款或退款。

## 验收

自动检查：TypeScript、Worker 支付测试（包括对输出订单串独立验签）、Android 单元测试与 membertest APK 构建。
本轮结果：`npm run check` 通过；`npm test` 的 135 项 Worker 测试、41 项 UI 测试全部通过；
`assembleMembertest`、`testMembertestUnitTest`、`compileReleaseKotlin` 通过。
APK：`自研辅助源码/app/build/outputs/apk/membertest/app-membertest.apk`（验收包，不是正式发布包）。
构建提示本机缺 Python 3.10，跳过 Python 字节码预编译，不影响本次构建成功。
`npm run sandbox:check` 仅校验受保护沙箱加载器和 APP 订单签名，不会创建支付宝交易，也不代表付款通过。

人工/实际环境仍须验证：

1. 配置已获 APP 支付权限的正式应用及已确认套餐价格，并部署服务端。
2. 手机安装同签名正式 APK；点击购买，普通支付宝出现正确商户、金额和商品。
3. 用户本人确认一笔付款；公网通知验签返回 success，会员只增加一次。
4. 验证取消、断网、进程退出重启后的原订单回查，以及管理员退款后的权益回收。

官方依据：
https://aipay.alipay.com/docs/vibe-pay/mobile-app-pay/app-pay-integration-guide-new.html
https://repo.maven.apache.org/maven2/com/alipay/sdk/alipaysdk-android/15.8.42/alipaysdk-android-15.8.42.pom
