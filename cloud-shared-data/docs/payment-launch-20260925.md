# 帝三资料库 APP 支付正式开放

用户已确认一分钱测试付款及商户到账，并明确授权正式开放收款。

## 价格和权益

月卡9.90元/30天，季卡25.90元/90天，年卡49.90元/365天；一次购买，不自动续费。
服务器固定价格和天数；验签通知或补偿查询确认后发放权益，重复支付事件不重复加时。

## 测试入口收口

已将线上 ALIPAY_ACCEPTANCE_UNTIL 设置为1，关闭新一分钱订单和SDK调起。
保留原验收订单及配置用于查单；订单的 acceptance 标记永久保留，不因正式上线发放会员。
真实订单 DWP62c8a2bcdf471fb171b98c7103d62dce 已由服务器返回 PAID/fulfilled=true/membershipApplied=false，用户确认商户到账。
不能据此声称普通会员价格订单的真机权益验收已完成，也不能仅凭当前订单公开状态推断是通知还是查询首先确认了付款。

## 发布包

正式包：自研辅助源码/app/build/outputs/apk/release/app-release.apk，V0.0.115，versionCode 115。
SHA-256：0dc091edfb04dc07b7a53d3a318c961eb81978c36dfddf720ee7ed5e0653f7e7。
Android 签名证书保持原正式签名；包名 com.example.dwpmclone。
不覆盖当前手机不同签名的内部调试包，不卸载/清数据强装。membertest 仅内部验收，不对客户分发。

## 运维

生产开关由 wrangler.jsonc 管理，ALIPAY_ENABLED/ALIPAY_APP_PAY_ENABLED/ALIPAY_LIVE_APPROVED 为true。
保留 Cloudflare 生产 Secrets、PID、现有会员及游戏数据；部署使用 keep-vars。
上线前版本（支付关闭、测试已过期）：924b0fcf-0495-42cd-8143-f43f00ddd656。
如发现付款后权益未到账，应先查原订单及服务端状态，不能让用户重复付款。
正式金额付款后会员到账及真实退款仍需后续验证，不能用自动化测试代替真实资金验收。

## 上线结果

- 已部署版本：6b3534e5-b59c-4fec-9c95-401269008d89。
- 实际生产套餐接口 HTTP200、enabled=true、mode=production、包含app渠道，价格9.90/25.90/49.90。
- health正常；未登录管理员支付接口401；无设备签名下单401；伪造通知400/fail。
- 全量139项Worker、42项UI、594项Android测试通过，TypeScript通过；正式release构建与签名校验通过，无调试Provider声明。
- 仅开放服务与生成本地正式APK，没有自动安装/卸载主应用，没有自动发起正常价扣款或退款。
