# 当乐 1025 区无痕抓包分析

- 样本：`ctf_out/passive_pcap_hotspot_20260719_134615/phone_tcp_all.pcap`
- 时间：2026-07-19 13:46:15—13:47:xx
- 方式：手机全量 TCP 被动抓包，未解密 TLS
- 解析结果：31 条 `/kingWapServer/HttpClient` HTTP 会话

## 关键结论

1. 当乐游戏业务层不是 TLS，而是明文 HTTP POST；业务接口结构与三国联盟一致。
2. 1025 区选服后实际游戏服确认是 `122.51.170.160:8888`，接口为 `http://122.51.170.160:8888/kingWapServer/HttpClient`。
3. 业务头始终为 `1660606\`7054\`0000430000`，当乐 channel 复用正确；`SERVER_SEQ_NUM=1` 不参与游戏区服选择。
4. 首次业务登录请求为 opcode `0x1003`，登录成功响应为 `0x8003`。响应中给出后续请求所需的 `dm`，后续请求使用该 dm。
5. 抓包包含完整的“进入游戏后”业务序列：角色信息、任务/活动、将领及地图/状态等请求；不是只有 SDK 登录。
6. 该轮抓包中没有足够证据恢复 SDK 的可重复登录接口：`ngsdk.d.cn` 的 SDK 登录仍是 TLS 加密；抓包只证明游戏层已经拿到了两枚会话 UUID/凭证并成功进入业务层。

## 登录序列

- 连接 `115.159.51.193:8888`：`0x1003 -> 0x8003`，响应文本显示“登录成功”，随后切换/确认区服流程。
- 连接 `122.51.170.160:8888`：`0x1003 -> 0x8003`，响应显示“没有角色信息”，随后出现角色创建请求并返回“角色创建成功”。这说明 122.51.170.160 是本轮选择的 1025 区游戏服。
- 后续请求均带有第二次 `0x8003` 返回的 dm，说明 dm 是会话级状态，不应写死。

## 解析产物

- `reverse_cases/downjoy-platform-capture-20260719/passive_1025_analyzed/game_http_flows.json`
- `reverse_cases/downjoy-platform-capture-20260719/passive_1025_analyzed/000/req.bin`
- `reverse_cases/downjoy-platform-capture-20260719/passive_1025_analyzed/000/resp.bin`
- `reverse_cases/downjoy-platform-capture-20260719/passive_1025_analyzed/001/req.bin`
- `reverse_cases/downjoy-platform-capture-20260719/passive_1025_analyzed/001/resp.bin`

## 当前适配判断

- 游戏业务层：可以复用，且已拿到 1025 区真实地址和登录包格式。
- 电脑端“凭抓包凭证直接登录”：只能做短时、一次性会话验证；凭证会过期/绑定设备或 SDK 会话，不能替代正常账号登录流程。
- 电脑端稳定自动登录：仍需完成当乐 SDK 登录 POST 的整体加密/响应解密，或由手机 SDK 登录后安全地把有效凭证交给电脑端；本轮无痕抓包没有解开 SDK TLS，因此尚未完成。
