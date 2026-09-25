# 支付宝AI网页应用收款接入（待正式开通）

## 当前边界

按用户提供的`product=online`入口，采用Vibe Pay网页/H5收款，不是当面付、
自动续费或Agent代用户付款。月/季/年会员每次主动购买，不保存支付宝密码。
未执行正式签约、正式付款、生产部署或手机覆盖安装；人工开通和现有游戏任务不变。
套餐正式价格待用户确认，生产默认关闭，不能把沙箱0.01元当作正式售价。

官方Agent技能已通过安装器安装在`~/.codex/skills/alipay-aipay`，当前使用1.7.0。
官方匿名沙箱已创建，唯一配置文件`.alipay-sandbox.json`为0600且被Git忽略。
不要打印、复制或提交该文件。服务启动器从自身路径定位原文件，直接读取
`appIds[0].appPrivatePkcsKey`（Node.js PKCS1）及支付宝公钥；不转密钥格式。

## 实现

- `src/alipay-payment.ts`：支付宝官方SDK 4.14.0、公钥模式RSA2、定点金额、
  受控环境配置、完整表单通知验签。网页支付使用pageExec POST，而非exec。
- `src/alipay-http.ts`：仅适配SDK的HTTP传输到Worker原生fetch；固定支付宝网关，
  `redirect:manual`并拒绝3xx。Worker不支持Node的`redirect:error`，已真实定位修复。
  签名、验签和响应原文截取仍由SDK执行，不手写替代签名协议。
- `src/payment-node-util.ts`：保留原生util，只关闭alipay-sdk的debuglog，
  防止某些Worker运行时把完整签名请求/响应写入日志。
- `src/payment-orders.ts`：每笔订单独立命名DO；订单和固定套餐价格持久化，
  支付/查询/关单/整单退款/退款查询共用状态机，不使用内存订单。
- `src/payments.ts`：设备签名+当前会员会话校验下单/查单；会员未到期不影响购买，
  已到期会员也能续费。20次/小时下单限制，购买请求编号确定订单号，重试不新建订单。
- `src/members.ts`：会员权益与永久订单回执原子提交。重复通知不重复加时，
  退款回执阻止迟到的付款事件重新开通；不会解除管理员停用或替换登录会话。
- APK：原生层保存购买请求号、订单和短期收银台链接；WebView只传套餐，
  不接触会员登录令牌、私钥或支付宝凭证。仅允许打开云端同源`/pay/start`链接。
- Home：开通套餐、打开浏览器付款、查询付款结果；服务未配置时隐藏在线入口，
  保留联系管理员。管理员后台新增订单查询/关单/整单退款/退款查询。

## 接口

| 接口 | 权限/作用 |
|---|---|
| GET /v1/payments/catalog | 只读套餐与开关，无私密数据 |
| POST /v1/member/payment-create | 当前会员设备签名，仅plan+purchaseId |
| POST /v1/member/payment-status | 当前会员设备签名，校验订单归属 |
| GET /pay/start | 服务端签发的订单访问凭据，生成并提交官方支付表单 |
| GET /pay/return | 无参数中性页；有有效订单凭据才主动查单；不信任同步成功参数 |
| POST /v1/payments/alipay/notify | 支付宝表单通知，RSA2验签+金额/订单/应用/收款方核对 |
| POST /admin/api/payments/query,close,refund,refund-query | 管理员Cookie、Origin、意图头；退款/关单确认 |

支付成功仅TRADE_SUCCESS/TRADE_FINISHED，不把HTTP200、页面回跳或客户端提示当作已支付。
退/关单事件不发权益。退款默认只支持整单，金额从原单读取，结果不明保留原退款编号。
外部部分退款会冻结本订单履约并要求人工核对，不能再次自动整单退款。
全额退款扣回此单天数，不清游戏数据；用户当前已有运行许可仍可能存续最长两小时。

## 本地沙箱

```sh
npm run sandbox:check
npm run sandbox:pay
```

运行需Node22。启动入口`http://127.0.0.1:18789/sandbox`，回跳`/pay/return`。
`scripts/alipay-sandbox.mjs`只绑定127.0.0.1；18879不是本次使用端口。
数据存于`.wrangler/payment-sandbox-state`，使用当前Miniflare的resourcePersistencePath。
不要改回旧版durableObjectsPersist属性（当前版本忽略它）。
`wrangler.sandbox.jsonc`仅供本地构建，不可生产部署；它没有生产账号或会员私钥。
沙箱付款永不增加真实会员天数。localhost无法接收支付宝公网通知，以主动查单验收。
收银台CSP需允许支付宝网关至官方收银台子域的跳转，否则Chrome可能留在空白页。

浏览器已观察到支付宝官方沙箱收银台：商品“帝王三国月卡沙箱测试”、0.01元、
二维码和买家登录框。未输入买家凭据、未确认付款。付款体验需用户自行完成，
不能以收银台打开宣称已付款或沙箱支付完整通过。

## 生产配置与上线门槛

密钥由用户在Cloudflare Secrets自行配置，禁止发到聊天、写进APK或提交仓库：
`ALIPAY_PRIVATE_KEY`、`ALIPAY_PUBLIC_KEY`（支付宝验签公钥，不是应用公钥）。
其余配置：`ALIPAY_MODE=production`、`ALIPAY_APP_ID`、`ALIPAY_SELLER_ID`、
`ALIPAY_ORIGIN=https://dwpm-data.292828.xyz`、`ALIPAY_PLAN_PRICES`。
价格JSON必须包含month/quarter/year三项，两位以内小数金额字符串；不提供生产默认价。
最后才设置`ALIPAY_ENABLED=true`与`ALIPAY_LIVE_APPROVED=true`，两者均需具备。

上线前必须完成：

1. 如实说明游戏自动化功能并由支付宝确认准入、签约和应用权限。
2. 用户确定正式套餐价格、退款规则及客服方式。
3. 用户配置同一生产应用的APPID、PKCS1私钥、支付宝公钥、收款方ID。
4. 独立环境验证公网HTTPS异步通知、真实查单、退款/关单及网络丢回执恢复。
5. 支付权益审核及APK端到端验收完成，再开启正式入口；人工开通保留。

## 安全验证

ctf发布检查覆盖：客户端金额/时长注入、订单越权、通知伪造、重复字段、
应用/金额/收款方不匹配、重复通知、迟到通知、退款先到、退款幂等、
沙箱隔离、查单签名、关闭已付订单、Worker重定向及SDK日志抑制。
测试均使用独立随机测试密钥，不代表真实付款已经完成。
运行依赖npm audit --omit=dev结果为0漏洞，urllib/undici固定到已修复版本。

发布判断：**BLOCK正式收款**。代码与本地自动测试不替代签约、真实付款及公网通知验收。
