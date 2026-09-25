# 当乐帝王三国与三国联盟协议对比报告

## 当前阶段 / Current phase

离线抓包对比、当乐 APK 深度逆向与电脑端双平台适配。分析过程未修改原始 APK/PCAP，未使用真实账号向游戏或平台服务发送请求。

## 样本

| 平台 | PCAP | SHA-256 | 大小 |
|---|---|---|---:|
| 当乐帝王三国 | `ctf_out/passive_pcap_hotspot_20260719_034604/phone_tcp_all.pcap` | `a9cda93a405ea5abb2f4c65a4636ec3d604379361cd98fc6ee3daa055aef2609` | 864,846 B |
| 三国联盟/352区 | `ctf_out/passive_pcap_hotspot_20260719_025021/phone_tcp_all.pcap` | `44a7b1580bc0c4542425a010489b71f2beeaef225e9ae5a517e49f2e0994418b` | 4,510,376 B |
| 当乐客户端 APK | `当乐帝王三国.apk` | `2ce6abf6dff2d49f3543fdfc593452141040b0d5713180914c8a3f92c0c86aa6` | 101,946,166 B |
| 当乐恢复业务 DEX | `recovered/original_classes_1.dex` | `568d7136cb64564c65f33d30dcacd750f168394fa8a9a297351c4df7fa9825ab` | 7.3 MiB |

## 已验证事实 / Verified facts

### 1. 游戏业务承载层一致

当乐 1024 区游戏业务连接：

```text
115.159.51.193:8888
POST /kingWapServer/HttpClient HTTP/1.1
```

当乐还在选择 1024 区之前连接过：

```text
124.222.229.62:8888
POST /kingWapServer/HttpClient HTTP/1.1
```

三国联盟 352 区：

```text
115.159.92.72:25511
POST /kingWapServer/HttpClient HTTP/1.1
```

路径、HTTP 方法、Content-Length 消息承载方式一致；不同区服的 IP 和端口均可能不同。

### 2. 二进制请求封包结构一致

现有帝王三国请求解析器未经修改即可完整解析：

- 当乐 1024 区：54/54 个请求，全部无尾随字节；
- 当乐前一游戏节点：1/1 个请求，全部无尾随字节；
- 三国联盟 352 区：438/438 个请求，全部无尾随字节。

两端均使用：

```text
UTF header
i64 timestamp
u8 commandCount
repeat:
  i64 dm
  i64 related
  u16 payloadLength
  u16 opcode
  UTF label
  payload
```

### 3. 渠道号不同，并非只换游戏服地址

固定请求头：

```text
当乐：    1660606`7054`0000430000
三国联盟：1660606`7054`0000480502
```

首个 `0x1003` 游戏服登录 payload 都是三个 UTF 字段：

```text
userId UUID
session UUID
channelId
```

当乐实测第三字段为：

```text
0000430000
```

三国联盟实测第三字段为：

```text
0000480502
```

当乐 `0x1003` 中的前两个字段是平台登录后生成的 UUID，并不是用户输入的当乐账号 `222430291`。

### 4. 响应帧与业务 opcode 高度一致

当乐 54 组业务流中：

- 53 个响应可由现有响应帧解析器完整解析且无尾随字节；
- 1 个响应是单字节 `02`，对应一次双命令批量请求，是特殊空/状态响应，不是标准响应帧；
- 可解析响应共得到 67 个业务包。
- 本轮当乐响应帧的混淆标志均为 `0`，所以现有响应混淆密钥是否也完全相同，尚不能仅靠这轮 PCAP 证明。

当乐抓到 30 种请求 opcode，其中 27 种也出现在三国联盟 352 样本。共同项包含：

```text
0x1003 游戏服登录
0x1004 初始化角色
0x1007 角色创建
0x1104 宝库
0x1130/0x1132/0x1134 任务或奖励
0x1520 出征预览
0x1522 正式出征
0x1702 副本
0x1930/0x1938/0x193d 无损相关
0x3110 角色/将领状态
0x3940/0x3941 活动
0x6200/0x6202
0x6444
```

当乐样本独有的 `0x114c`、`0x3183`、`0x6400` 更可能来自本轮操作覆盖差异或新区/新角色流程，不能据此判断协议分叉。

本轮当乐样本没有抓到刷黄 `0x1540`、配兵 `0x1226`、治疗 `0x1230`、找矿 `0x1542` 等请求。因此这些功能可基于同一协议框架复用，但尚未由当乐样本逐项实证。

### 5. 平台登录链不同，现已从 APK 精确恢复

当乐登录阶段存在以下独立流量：

```text
ngsdk.d.cn:443
antiaddictionsdk.d.cn:443
118.89.109.107:11443（TLS SNI: 3gking.net）
```

随后才得到 UUID 形式的 `userId/session` 并向游戏服发送 `0x1003`。

APK 内置配置确认：

```text
channel.id=dangleY
channel.num=0000430000
channel.passport=https://3gking.net:11443/
MERCHANT_ID=31
APP_ID=89
APP_KEY=d0JG9Jn2
SERVER_SEQ_NUM=1
```

当乐 SDK 用户名密码登录端点：

```text
GET https://ngsdk.d.cn/api/user/login
passwordHash = SHA-256(password).upper()
```

`libdcn_dynamic.so` 中的 `sdkEncrypt` 已恢复为：

```python
key = b"bNA-!/Nf"
out[i] = (~(plain[i] ^ key[i % 8]) + i) & 0xff
encoded = base64.b64encode(out)
swap(encoded[0], encoded[len(encoded) // 2])
```

`signParam` 已恢复为：

```python
md5("shzy" + concat(params) + "gj88").hexdigest()
```

真实业务 DEX 中 `DangleYAPI$2.callback()` 明确执行：

```text
umid     = LoginInfo.getUmid()
userName = LoginInfo.getUserName()
token    = LoginInfo.getToken()
Lo/a.A1(1, umid, userName, token)
```

而当前 SDK 成功回调构造 `InnerLoginInfo(umid, "", "", accessToken, checkTokenUrl)`，因此游戏通行证换票参数精确为：

```text
session=<access_token>
username=<umid>
password=
channelId=0000430000
```

随后请求：

```text
https://3gking.net:11443/common/area/list.action
https://3gking.net:11443/common/area/enter.action
```

### 6. 电脑端已完成双平台业务路由改造，SDK 登录仍受阻

当前电脑端已经：

- 增加 `sglm/downjoy` 平台配置；
- 按账号平台选择 SDK 登录、passport、channel 和二进制 header；
- 将平台传入 `fresh_login()` 和首轮游戏服请求；
- 平台选择改为固定下拉框；
- 区服目录按平台持久化和查询；
- 账号稳定身份加入平台维度；
- 当乐账号配置、日志习惯键和共享地图键加入 `downjoy` 命名空间；
- 保留旧三国联盟账号、习惯和共享地图的原键，避免升级后历史数据失联。
- 当乐无缓存时的默认游戏区服已改为当前的 `1025区`，不再误用三国联盟
  的 351/352 区；APK 的 `SERVER_SEQ_NUM=1` 是 SDK 应用配置，不是游戏区号。

但是，真实账号在当乐 SDK 的 `api/user/login` 阶段返回：

```text
code=6007，参数错误
```

该失败发生在取得 SDK token 和请求游戏区服目录之前，因此与选择 351、1024
或 1025 区无关。当前电脑端只能认定为“游戏协议层和平台路由已适配”，不能
认定为“当乐真实登录已完成”；SDK 设备参数 `di/sinfo/udid` 仍需按 APK
运行环境继续校准。

本轮静态恢复进一步确认了设备字段算法：

```text
sinfo = sdkEncrypt("&&&" + Build.MODEL + "&" + Build.DISPLAY
                   + "&" + Build.VERSION.RELEASE + "&&")
di     = md5("shzy" + udid + android_id + "gj88")
old_di = md5("shzy" + udid + "gj88")
udid   = 持久化设备 UDID；优先 OAID，失败时为 md5(android_id)
         （android_id 无效时再退回安装时间）
```

电脑端已加入这套算法和可注入的 Android 设备字段。使用桌面占位设备字段
测试真实账号后，服务端错误由 `6007` 变为 `6010`，但仍为参数错误，说明
接口和部分参数路径已生效，剩余关键差异很可能是手机实际的
`OAID/udid、android_id、Build.MODEL/DISPLAY/RELEASE` 或 HTTPS 请求环境。

平台适配专项离线测试当前 7 项通过，覆盖当乐加密/签名固定向量、
token→passport 映射、请求 header、跨平台隔离以及平台默认区服隔离。

## 推断与置信度 / Inference and confidence

| 结论 | 置信度 |
|---|---|
| 游戏内 HTTP 承载和基础二进制封包可复用 | 高 |
| 已共同出现的 27 种请求 opcode 可复用现有构包和解析思路 | 高 |
| 出征、副本、状态读取等已抓到功能可复用 | 高 |
| 所有军事、内政功能无需任何平台差异处理 | 中；当乐样本尚未覆盖全部 opcode |
| 当乐只改一个服务器地址即可支持 | 否，高置信度 |
| 电脑端业务层可支持该平台 | 高 |
| 当前当乐 SDK 登录参数已可用于真实账号登录 | 否；已被 6007 实测否定 |

## 电脑端适配边界

建议拆成两层：

1. `PlatformAdapter`
   - 当乐 SDK/账号鉴权；
   - 获取游戏 passport session、userId；
   - 获取平台自己的区服目录；
   - 进入区服；
   - 提供 channelId、header、serverUrl。
2. `GameProtocolSession`
   - 继续复用现有 `post_game()`、opcode 构包、响应解析和军事/政事任务；
   - header、channel、响应配置改为会话级，不再使用单一全局常量。

同时必须把以下身份键加入 `platform`：

```text
账号唯一键 = platform + username + server
区服目录键 = platform + serverKey
共享山贼/矿图键 = platform + server identity
```

不能仅按“1024区”共享地图，否则不同平台的同名区服会串图。

## 最终判断

当乐与三国联盟不是两套完全不同的游戏业务协议；它们高度可能共用同一套帝王三国游戏内协议内核。现有电脑端的业务执行层可以大面积复用。

但它们也不是“只有一个 IP 不同”。目前至少已经实证存在：

- 游戏服 IP/端口不同；
- channelId 和请求 header 不同；
- 平台账号鉴权链不同；
- passport 入口/端口不同；
- 区服目录来源不同；
- 当乐额外 SDK 与防沉迷交互。

当前实现状态应表述为：

```text
游戏业务层已适配；
当乐 SDK 登录仍需修正设备参数；
当前 6007 阻断真实登录。
```

所以结论是：**电脑端的当乐登录适配器和会话级协议配置已经落地，现有游戏业务层继续复用。当前剩余工作是用用户自有当乐测试账号做首次只读在线验证，而不是继续猜地址或重复抓包。**

## 未决证据

要把“可大面积复用”提升为“完整支持”，还需：

1. 使用用户自有当乐测试账号完成一次电脑端只读登录，确认 SDK 服务当前仍接受恢复出的公共设备参数；
2. 若账号触发验证码、实名认证或设备保护，需要在界面增加对应的人工接管流程；
3. 当乐 30 级以上账号再分批验证找黄、配兵、治疗、找矿、召回、建筑和捐献等尚未出现在本轮 PCAP 的 opcode。
