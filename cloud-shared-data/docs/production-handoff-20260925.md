# 帝三资料库生产准备

## 已知事实

- APP 支付签约：本轮官方查询已生效；不要重新提交签约。
- 正式应用：2021007102687318，最新列表状态为 AUDIT（审核中）。
- 应用公钥已在开放平台短信校验后配置完成；官方 verify-key 已确认应用公钥生效，支付宝公钥已导出并写入 Cloudflare Secret ALIPAY_PUBLIC_KEY。
- 部署前线上 `/v1/payments/catalog` 返回 HTTP 401；部署后恢复 200/disabled。未放宽通用鉴权。
- 用户已完成 Cloudflare OAuth，线上原有 Secrets 均保留。仅核对名称，未读取秘密值；尚无 ALIPAY_PRIVATE_KEY 或 ALIPAY_SELLER_ID 配置。

## 本地已准备

`wrangler.jsonc` 中已填正式 APPID、production 模式、生产域名和三档价格。
ALIPAY_ENABLED、ALIPAY_APP_PAY_ENABLED、ALIPAY_LIVE_APPROVED 全部保持 false。
该配置已部署，仍不代表正式收款开通。

还需由所有者在 Cloudflare 中自行录入：ALIPAY_PRIVATE_KEY（PKCS1 原始值）、ALIPAY_SELLER_ID（实际收款方 PID）。ALIPAY_PUBLIC_KEY 已配置。
不要把私钥交给 Agent，不放进 APK，不提交仓库，不输出到终端或日志。
不要替换现有会员签名、会员认证秘密或客户端兼容凭据。

## 发布顺序

1. 在支付宝开放平台确认上述应用的公钥配置及应用状态；未知写入不得重复创建应用/公钥页。
2. 用户完成 Cloudflare OAuth，核对当前 Worker 的部署与 Secret 名称（不读取秘密值）。
3. 审查工作区中的支付、会员和其他共享服务改动，确认生产发布范围；跑 TypeScript、Worker 与 UI 回归、部署 dry-run。
4. 保持收款关闭发布服务端，确认公开套餐接口 200/disabled，管理与用户写接口仍鉴权。
5. 正式 APK 使用既有发布签名构建；不得覆盖手机原来不同签名的内部包，也不得卸载/清数据强行安装。
6. 完成产品权限、正式密钥、公网通知验收条件后，安排受控真实付款联调。不要用 ALIPAY_LIVE_APPROVED 的字面值替代验收证据。
7. 用户本人确认付款，核验签名通知/交易查询、会员幂等到账和异常恢复，再对用户开放。

Android 发布构建：在自研辅助源码目录运行 `node tools/build-production.mjs --keystore <既有发布签名文件路径>`。
需要可用 JAVA_HOME。脚本仅在内存中读取既有 Android 签名密码，不处理支付宝私钥，也不创建新密钥。

## 本轮实际验证

- release 构建成功，产物 `自研辅助源码/app/build/outputs/apk/release/app-release.apk`，版本 V0.0.114。
- APK 发布签名校验通过，证书与既有正式签名一致；包名 com.example.dwpmclone。未覆盖手机上的应用。
- APK SHA-256：0547e509e40001ddabd5e536567dbb18f303507ce3c2643eebef2b71a985d447。
- TypeScript 检查通过；全量 135 项 Worker 测试和42项 UI 测试通过；随后新增公开目录/鉴权回归，支付定向25项全部通过。
- Wrangler 生产构建 dry-run 通过，用户完成 OAuth 后以 keep-vars 部署成功。
- 当前版本 ffeb701c-3880-4ce1-b10d-562250e97259；前一版本 bef1074c-51be-4332-a56a-4eb384b60f1f。部署保留原 D1、DO、Secrets 和共享地图环境参数，无数据库迁移/数据清理操作。
- 部署后 GET /health、/v1/member/info、/v1/payments/catalog 均200；支付目录 enabled=false；未登录 GET /admin/api/payments/query 返回401。未发起交易、扣款、退款或会员权益写入。
- 应用资料已保存为“帝三资料库”并使用用户指定游戏图标；应用已提交审核，最新状态为 AUDIT。等待支付宝审核，不重复提审。
