# 《三国·帝王联盟 1.66》客户端理解工作台（服务端重建准备版）

更新时间：2026-07-05  
目标：先彻底理解客户端结构、资源、协议、状态同步和服务端依赖；当前 **不重建服务端**。

## 1. 已验证事实

- APK：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/三国·帝王联盟1.66.apk`
- SHA-256：`4571a166fd46c21edee1e2994d9e6e3bc905b41b049f80f89b7774f65cdc5fb8`
- 包名：`com.gamebox.king`
- 版本：`versionCode=182`，`versionName=1.66.0606`
- 壳入口：`com.xmxu.jiagu.StubApp`
- 真实 Application：`com.gamebox.king.GameboxApplication`
- 主 Activity：`com.gamebox.king.KingActivity`
- 真实 DEX：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/recovered/original_classes_1.dex`
  - SHA-256：`8df5340f841c7f73c1ff0287ce9b7baabb931cc0b4f86b1eccb55154a8991537`
  - Classes：`3047`
  - Methods：`32390`
  - Strings：`38118`

证据文件：

- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/reports/deep-reverse-report.md`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/AndroidManifest.parsed.xml`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/recovered_dex/original_classes_1_summary.md`

## 2. 客户端分层模型

### 2.1 Android 外壳层

客户端不是普通 Java 源码直出 APK，而是加固后 APK：

1. Manifest 指向 `com.xmxu.jiagu.StubApp`。
2. 壳 DEX 只有 8 个 class。
3. 壳从 `classes.dex` 尾部恢复真实 DEX。
4. 真实入口为 `com.gamebox.king.GameboxApplication` + `KingActivity`。

这层主要解决 APK 装载、Application 替换、Activity 启动，不承载核心游戏规则。

### 2.2 游戏运行时/引擎层

真实 DEX 显示客户端是一个“Java ME/MIDlet 风格迁移到 Android”的 2D 游戏客户端：

- `main.*`：Android Activity/Canvas/MIDlet 适配层。
- `engineBase.*`：图形、音频、资源、RMS、本地文件、HTTP/Socket 抽象。
- `scriptAPI.*`：脚本 API、BaseIO、BaseExt、BaseRes、支付/渠道/推送扩展。
- `scriptPages.*`：游戏 UI、业务页面、数据模型和协议处理。
- `o/a`：核心全局状态、网络分发、复合同步块和大量协议解析函数。

关键包数量证据见：`analysis/recovered_dex/original_classes_1_summary.md`。

### 2.3 资源/配置层

APK 内资源主要分为：

- `assets/script/*.sc|*.txt|*.properties`：可读/半可读脚本与规则文本，是规则恢复主来源。
- `assets/data/*.dat`：大量图片/地图/精灵/二进制资源，共约 9860 个 `.dat`。
- `assets/music/*.mp3`：音乐。
- `res/xml/network_security_config`：允许明文 HTTP。

启动配置：

```properties
channel.gw=http://king9.cn
channel.passport=https://sglmpass.3gking.net:12443/
version.fullnum=v1.66.0606
version.num=1660606
version.res=20260526
```

配置证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/all_scripts/assets/script/defautConfig.properties`

## 3. 网络与协议模型

### 3.1 已验证的真实业务通信形态

动态抓包显示，进入游戏后核心业务不是裸 TCP，而是明文 HTTP POST：

```text
http://118.89.111.11:25511/kingWapServer/HttpClient
```

请求体和响应体是二进制协议包；抓包证据见：

- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/captures/mitm/game_capture_20260705_020959/extracted/game_flows_summary.md`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/captures/mitm/game_capture_20260705_020959/http_flows.jsonl`

### 3.2 请求发送链路

静态证据：

- `LscriptPages/game/g;->y(String,String,S)`，code_off `0x2a1568`
  - `BaseIO.dos2DataArray(name)` 取出请求体。
  - `BaseIO.closeDos(name)` 关闭写流。
  - `Lo/a.d0(opcode, payload)` 入队。
- `Lo/a;->d0(S,[B)Z`，code_off `0x21eb40`
  - 将 opcode 存入 `Lo/a.Fm[]`。
  - 将 payload 存入 `Lo/a.Hm[][]`。
  - 将唯一/续包标记候选 `Lo/a.Gm[]` 清零。
  - `Lo/a.Em` 为待发送队列长度。
- `LscriptPages/conn/a;->a()V`，code_off `0x25edb0`
  - 周期性把 `Lo/a` 队列组装成 `packet`。
  - 写入版本/渠道字符串、客户端时间、命令数量、每条命令的 opcode、payload 长度、签名候选。
  - 调用 `BaseIO.openHttp(handle, Lo/a.vm, packetBytes, config)` 发送。
- `Lo/a;->J8(String,String)V`，code_off `0x24b908`
  - 构造 `/kingWapServer/HttpClient` URL。
- `engineBase/io/HttpConnection.httpConnectUrl()`，code_off `0x20e460`
  - 使用 Java `HttpURLConnection`。
  - POST 时直接写入 `reqData` 原始字节。
  - 只设置 `Connection: Close` 与 `accept: */*`。

### 3.3 请求包结构候选

根据 `scriptPages/conn/a.a()` 静态读写顺序，当前可建立如下候选结构：

```text
packet:
  writeUTF("<versionNum>`<server/channel?>`<channelNum>")
  writeLong(client_time)
  writeByte(command_count)
  repeat command_count:
    writeLong(Lo/a.Dm)              # 会话/账号/连接级 long 候选
    writeLong(Lo/a.Gm[i])           # 分片/重放/unique id 候选，普通请求多为 0
    writeShort(payload_length)
    writeShort(opcode)
    writeUTF(md5(opcode + client_time + Lo/a.Dm + "FIC1atsuf30"))
    writeByteArray(payload_or_obfuscated_payload)
```

注意：上面是客户端代码级候选结构，字段名仍需用更多抓包样本确认。

### 3.4 响应处理链路

`scriptPages/conn/a.a()` 对响应体执行：

```text
readByte(outer_count)
repeat outer_count:
  readByte(inner_count)
  repeat inner_count:
    readLong(...)                  # 时间/序列号候选
    readLong(unique_id)
    readBoolean(obfuscation_flag)
    readInt(payload_length)
    readShort(response_opcode)
    readBoolean(fragment_or_cache_flag)
    readByteArray(payload)
    if obfuscation_flag:
      payload = Lo/a.P(Lo/a.o(), payload)
    Lo/a.A6(response_opcode, payload, "packetExe")
```

关键结论：`Lo/a.A6(S,[B,String)Z` 是主响应分发器，code_off `0x21f514`。响应 opcode 多为 `0x8xxx`，即请求 opcode `0x1xxx` 的服务端响应形态。

早期已生成候选响应分发表：

- CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/response_dispatch_candidates.csv`
- Markdown：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/response_dispatch_candidates.md`

该表为早期粗抽取结果，已被下面的清洗版主索引取代；复杂分支仍需人工复核。

### 3.5 响应分发清洗结果（`Lo/a.A6`）

本轮已对 `Lo/a;->A6(S,[B,String)Z` 做第一轮清洗抽取，形成更适合后续协议恢复的主索引：

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/PROTOCOL_RESPONSE_DISPATCH_CLEAN.md`
- 清洗分发表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/response_dispatch_clean.csv`
- handler 直接读字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/handler_direct_read_sequences.csv`
- opcode 合同表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/response_handler_contracts.csv`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/protocol_dispatch_extraction_summary.json`

统计结果：

- 响应 opcode 候选：`458`
- 唯一 handler 候选：`497`
- 具备首个业务 handler 的分支：`452`

解读边界：

- `response_dispatch_clean.csv` 是当前 `Lo/a.A6` 分发恢复的主入口。
- `response_handler_contracts.csv` 更适合按“响应 opcode → handler → 读字段顺序 → 请求候选”查询。
- `handler_direct_read_sequences.csv` 只统计 handler 方法内直接出现的 `BaseIO.read*`；如果 handler 再调用二级 parser，该表不会自动展开。
- `request_candidate_minus_0x7000` / `request_candidate_minus_0x8000` 是启发式对齐字段，需结合请求生成函数、抓包和脚本文本命名确认。

### 3.6 已知关键响应合同摘录

| 响应 opcode | handler | 请求候选/语义 | 当前价值 |
|---:|---|---|---|
| `0x8003` | `LscriptPages/game/b0;->i1(String)` | `0x1003 loginBaseinfo` | 登录基础信息、账号/角色进入前状态。 |
| `0x8004` | `LscriptPages/game/a0;->S([B)` | `0x1004 gameLogin/accountLogin` | 游戏登录主响应；直接读字段多，且调用 `data/i.y`、`Lo/a.W`、`Lo/a.M6`。 |
| `0x8008` | `LscriptPages/game/s0;->y([B)` | `0x1008 cacheData` | 进服缓存/地图初始化相关，后续自动请求序列关键节点。 |
| `0x800d` | `LscriptPages/game/s0;->b([B)` | `0x100d` | 城池地图初始缓存候选。 |
| `0x8012` | `LscriptPages/game/s0;->S(String)` | `0x1012 reqFightingCity` | 攻城/战斗城市入口响应。 |
| `0x8114` | `LscriptPages/game/h0;->a0(String)` | `0x1114` | 邮件/战利品详情。 |
| `0x8120` | `LscriptPages/data/i;->x(String)` | `0x1120 reqRoleInfo` | 角色信息同步，是全局状态字典的重要入口。 |
| `0x8130` | `LscriptPages/game/m0;->s(String)` | `0x1130` | 任务列表。 |
| `0x8132` | `LscriptPages/game/m0;->w(String)` | `0x1132 reqTaskInfo` | 任务详情。 |
| `0x8134` | `LscriptPages/game/m0;->u(String)` | `0x1134 reqGainAward` | 领奖后的资产/任务状态同步。 |
| `0x8212` | `LscriptPages/game/q;->W(String)` | `0x1212 fiefMove` | 封地迁移响应。 |
| `0x8229` | `LscriptPages/game/p;->M0(String)` | `0x1229 reqBathAddArmy` | 批量补兵/兵力同步。 |
| `0x8310` | `LscriptPages/game/w;->c0(String)` | `0x1310 reqRoleFiefList` | 玩家封地列表，建筑/资源系统入口。 |
| `0x8324` | `LscriptPages/game/k;->d1(String)` | `0x1324 reqCityTraitLevelUp` | 城池特性升级响应。 |
| `0xe342` | `La0/a;->C(String)` | `0x6342 Req_libutaskDispatch`（按 `-0x8000`） | 六部/活动任务响应候选。 |

### 3.7 当前自动化脚本索引

本轮新增脚本：

- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_client_protocol_dispatch.py`

脚本职责：

1. 加载真实 DEX：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/recovered/original_classes_1.dex`
2. 定位 `Lo/a;->A6(S,[B,String)Z`。
3. 抽取顶层 `if-ne pType,const` 响应分支。
4. 识别每个分支中的首个业务 handler、所有业务调用、分支内直接 `BaseIO.read*`。
5. 对 handler 方法做直接 `BaseIO.read*` 序列统计。
6. 输出清洗表、合同表、读字段表和 Markdown 主报告。

复用方式：

```bash
python3 /Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_client_protocol_dispatch.py
```

### 3.8 `Lo/a.V5` 复合同步块第一版

已对 `Lo/a;->V5(Ljava/lang/String;)V` 做第一轮深拆，当前主索引：

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/V5_COMPOSITE_SYNC_BLOCK.md`
- 字段读取序列：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/v5_read_sequence.csv`
- 子 parser / accessor 索引：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/v5_subblock_parsers.csv`
- V5 调用点：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/v5_callers.csv`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/v5_extraction_summary.json`
- 自动化脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_v5_composite_sync.py`

核心结论：

```text
Lo/a.V5(dis):
  readLong -> scriptPages/data/g.F
  readLong -> scriptPages/data/g.G
  readShort stack_count
  repeat stack_count:
    readShort -> Lo/a.bv[i]   # 条目 id 候选
    readShort -> Lo/a.cv[i]   # 数量/值候选
    readLong  -> Lo/a.dv[i]   # long 参数候选
  readShort equipment_count
  repeat equipment_count:
    readLong/readShort/readByte... -> scriptPages/data/d bank0 装备记录
  readShort -> Lo/a.ev
  readShort -> Lo/a.fv
  readShort/readByte -> reserved/ignored
  Lo/a.gv = true
```

边界说明：

- `V5` 是大量业务响应共享的“通用同步块”，但不是完整角色资产块；许多响应会在调用 `V5` 前后额外同步 `scriptPages/data/i`、封地、建筑、活动或战斗字段。
- `Lo/a.bv/cv/dv` 更像通用条目/物品/资源栈；`scriptPages/data/d` 基本可定为装备/宝物容器。
- `scriptPages/data/d` 第一维有两个 bank：`V5` 全量重建 bank0，`Lo/a.c6(String)` 维护 bank1；`Lo/a.c6` 是下一轮装备系统深拆的优先目标。

### 3.9 `Lo/a.c6` 装备 bank1 同步 parser 第一版

已对 `Lo/a;->c6(Ljava/lang/String;)V` 做第一轮深拆，当前主索引：

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/C6_EQUIPMENT_BANK1_SYNC.md`
- 字段读取序列：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/c6_read_sequence.csv`
- c6 调用点：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/c6_callers.csv`
- bank1 相关 parser / 字段索引：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/c6_bank1_related_parsers.csv`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/c6_extraction_summary.json`
- 自动化脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_c6_equipment_bank1.py`

核心结论：

```text
Lo/a.c6(dis):
  readLong host_id
  host_index = Lo/a.c3(0, host_id)
  if host_index < 0: return
  清理 Lo/a.jp[host_index] 旧绑定装备
  data.d.a(host_id) 清理 data.d.k == host_id 的 bank1 记录
  readByte linked_id_count
  repeat linked_id_count:
    readLong -> Lo/a.jp[host_index][i]
  ensure data.d bank1 arrays capacity 120
  readByte update_count
  repeat update_count:
    readLong equipment_id
    if equipment_id != -1:
      readShort/readByte/readUTF... -> scriptPages/data/d bank1 装备记录
      data.d.k[slot] = host_id
      data.d.m[1][slot] = 0
  sort bank1 by data.d.f[1][slot][0], data.d.f[1][slot][1]
```

直接响应 handler 调用摘录：

| 响应 opcode | handler | 请求候选 | 当前价值 |
|---:|---|---|---|
| `0xa252` | `La0/a;->C1(String)` | `0x3252` | 活动/装备相关响应中同步 bank1、再同步 `a6/f6/V5/S5`。 |
| `0x8250` | `LscriptPages/game/z;->F0(String)` | `0x1250` | 将领/装备相关响应，只调用 `c6/f6` 后刷新装备 id 列表。 |
| `0x8252` | `LscriptPages/game/z;->D0(String)` | `0x1252` | 装备操作响应，调用 `c6/a6/f6/V5/S5`，字段组合较完整。 |
| `0x8254` | `LscriptPages/game/z;->H0(String)` | `0x1254` | 装备操作响应，调用 `c6/a6/f6/V5`。 |

间接调用：

- `LscriptPages/data/i;->y(String)` 会先调用 `data/i.x`、`data/g.y3`、`Lo/a.Z5`，再按 `readByte` 次数循环调用 `c6`；它出现在登录/角色资产初始化链路中。

边界说明：

- `c6` 维护的是与 `V5` 同构的 `scriptPages/data/d` 装备字段族，但写入 bank1。
- `data.d.k[slot] = host_id` 与 `Lo/a.jp[host_index]` 是 bank1 的宿主绑定关系，是 bank0 没有的关键字段。
- `host_id` 的业务对象类型仍需按 caller 分组确认；从调用场景看更接近将领装备/装备操作/活动奖励中的装备绑定对象。
- `equipment_id == -1` 分支只消费 long 后跳过剩余装备字段，可能是空槽、删除或占位记录。

### 3.10 `Lo/a.a6` / `Lo/a.f6` / `Lo/a.b6` 将领/对象同步链路第一版

已对 `Lo/a;->a6(I,String)`、`Lo/a;->f6(I,String)`、`Lo/a;->b6(I,String,I)` 与伴随状态块 `Lo/a;->S5(String)` 做第一轮深拆，当前主索引：

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/A6_F6_GENERAL_SYNC.md`
- 字段读取序列：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/a6_f6_b6_read_sequences.csv`
- 调用点索引：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/a6_f6_callers.csv`
- 相关 parser / 字段索引：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/general_sync_related_parsers.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/a6_f6_b6_s5_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/a6_f6_extraction_summary.json`
- 自动化脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_general_sync_a6_f6.py`

关键静态事实：

- `0x8215` 响应分支直接对应 `Lo/a.f6(I,String)`，请求候选为 `0x1215 reqLoadGenerals@o/a->a8`。
- `Lo/a.a8()` 发送 `reqLoadGenerals / 0x1215`，请求体为 `writeByte(0)`、`writeByte(0)`、`writeLong(scriptPages/data/i.a)`。
- `Lo/a.f6(type, stream)` 是批量列表重建 parser：初始化/重建 `co/do/eo/.../Uo` 等二维对象字段数组，容量固定 `[2][30]`；读取 `count/readByte` 后逐条读取 `co[type][i]/readLong`，再调用 `b6(type, stream, i)`。
- `Lo/a.a6(type, stream)` 是单对象更新 wrapper：先读 `object_id/readLong`，再用 `Lo/a.c3(type, object_id)` 在 `co[type]` 中定位，命中才调用 `b6` 更新该 slot。
- `Lo/a.b6(type, stream, idx)` 是单对象字段合同，当前确认直接 `BaseIO.read*` 数为 `57`：
  - common 字段包括：`do` 名称字符串、二十余个 short/byte/int、`Eo/Fo/Ro` long、`No=curTime+readLong`、`Vo` 状态 byte 等。
  - `type == 1` 额外读取 `Wo/Xo/Yo/Zo/ap/bp/cp`。
  - `type != 1` 额外读取 `yo/Ho/Io`；若 `Vo[type][idx] == 3`，继续读取 `dp/ep/fp/gp/hp/ip`。
- `Lo/a.S5(stream)` 是伴随 30 槽状态表：`Nm/Om/Pm/Qm`，每条读取 `long/long/byte/int`。

当前推断：

- `type 0` 高置信覆盖“将领/可装备宿主”主表。证据：`reqLoadGenerals`、大量 `scriptPages/game/z` 将领操作响应、`c6` 固定 `c3(0, host_id)` 绑定 bank1 装备。
- `type 1` 是同构的第二对象表，可能用于地图/驻防/对方或扩展角色对象；真实业务名仍需结合 UI 与抓包确认。
- `S5` 是和对象列表一起刷新的队列/状态/计时器类辅助表，常与 `f6(0/1)` 出现在出征快照、登录资产初始化、装备操作响应中。
- 对未来服务端重建最关键的影响：任何返回 `f6/a6/b6/S5` 的响应必须严格保持字段顺序，尤其 `b6` 的 `type` 分支与 `Vo==3` 条件分支会改变后续读取位置。

### 3.11 `scriptPages/data/d` 装备容器 accessor 字典第一版

已对 `scriptPages/data/d` 装备容器字段、accessor 与 UI 语义证据做第一轮深拆，当前主索引：

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/DATA_D_EQUIPMENT_ACCESSORS.md`
- accessor 字典：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/data_d_accessor_dictionary.csv`
- 字段字典：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/data_d_field_dictionary.csv`
- UI 语义证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/data_d_ui_evidence.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/data_d_equipment_accessors_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/data_d_accessor_summary.json`
- 自动化脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_data_d_equipment_accessors.py`

关键结论：

- `scriptPages/data/d` 是 V5/c6 共用的二维装备容器：
  - bank0：`Lo/a.V5` 全量重建。
  - bank1：`Lo/a.c6` 增量维护，并通过 `data.d.k[slot] = host_id` 绑定宿主。
- 静态文本已确认：
  - 属性名表 `data.d.a[]`：攻击、生命、防御、统兵。
  - 品质名表 `data.d.b[]`：普通、良好、优秀、卓越。
- 字段语义第一版：
  - `data.d.d[bank][slot]`：装备实例 id。
  - `data.d.e[bank][slot]`：装备模板 id。
  - `data.d.f[bank][slot][0]`：品质 index。
  - `data.d.f[bank][slot][1]`：强化等级/强化值候选。
  - `data.d.g[bank][slot]`：强化效果百分比候选，装备页以 `g/100.g%100%` 显示“强化效果”。
  - `data.d.h[bank][slot][0]`：强化失败风险百分比候选，装备页显示“失败掉级率/失败损毁率”；`h[][1]` 未命名。
  - `data.d.i[bank][slot][0/1]`：强化保底次数候选。
  - `data.d.j[bank][slot]`：协议 short 参数，暂未发现明确 UI 语义。
  - `data.d.k[slot]`：bank1 宿主 host_id 反链。
  - `data.d.l[bank][slot]`：装备额外文本/描述。
  - `data.d.m[bank][slot]`：内部标志/状态，暂未命名。
- 关键 accessor：
  - `D/o`：装备名称，来自 `Lo/a.Mn[g3(template_id)]`。
  - `w/l`：图标/资源类别候选，来自 `Lo/a.Pn[g3(template_id)]`。
  - `z/n`：装备部位/大类/颜色候选，来自 `Lo/a.Kn[g3(template_id)]`。
  - `d/E/j/i`：基础属性、强化贡献、总属性、格式化属性文案。
  - `t/u/v`：品质 index 与品质名称。
  - `q`：强化等级/强化值候选。
  - `k`：强化材料 `[item_id, amount]`。
  - `p`：强化失败风险。
  - `x`：装备特效资源编号，装备页拼接 `equipEffectN`。
  - `A/s`：原始/清洗后的额外描述。

面向服务端重建的紧凑装备记录候选：

```text
equipment_record_common:
  long  instance_id
  short template_id
  byte  vector_len
  byte[] f                 # f[0]=quality_index, f[1]=strength_level/value
  short strengthen_effect  # data.d.g
  byte  risk_or_flag_0     # data.d.h[][0]
  byte  risk_or_flag_1     # data.d.h[][1], 未命名
  short protocol_j         # data.d.j, 未命名
  short pity_current       # data.d.i[][0]
  short pity_target        # data.d.i[][1]
  UTF   extra_text         # data.d.l
  if bank1: host_id        # data.d.k，由 c6 写入
```

### 3.12 装备静态表来源与字段字典第一版

已对装备容器背后的本地静态表和联网 `bo` 配置入口做第一轮深拆，当前主索引：

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/EQUIPMENT_STATIC_TABLES.md`
- 加载字段顺序：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_template_loader_fields.csv`
- 静态字段字典：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_static_field_dictionary.csv`
- helper/accessor 字典：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_helper_methods.csv`
- 模板实值表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_template_static_values.csv`
- 类型/强化实值表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_type_static_values.csv`
- 属性文案实值表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_effect_text_values.csv`
- 特效图标实值表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_icon_effect_values.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_static_tables_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_static_extraction_summary.json`
- 自动化脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_equipment_static_tables.py`

关键静态事实：

- `LscriptPages/data/g;->c3()V` 是 APK/RMS 脚本主加载器；`ue[index]` 文件名对应 RMS record `index+2`，资源缓存过期时从 `/script/<name>` 加载。
- 装备本地静态表：
  - record `4` / `scriptEquip.sc`：模板主表，写入 `Lo/a.In/Jn/Kn/Ln/Mn/Nn/On/Pn`。
  - record `5` / `scriptEquipType.sc`：装备类型、强化倍率、强化材料，写入 `Lo/a.Wn/Xn/Yn/Zn/ao`。
  - record `6` / `scriptEquipEffect.sc`：属性文案模板，写入 `Lo/a.Qn/Rn/Sn`。
  - record `25` / `scriptEquipIconEffect.sc`：特殊装备效果图标映射，由 `scriptPages/data/d.H` 写入 `Lo/a.Tn/Un/Vn`。
- 已解析本地实值：
  - 装备模板：`161` 条，template id `0..160`，全部唯一。
  - 装备类型：`4` 条，`0=武器/攻击`、`1=头盔/生命`、`2=铠甲/防御`、`3=坐骑/统兵`。
  - 属性文案组：`11` 条。
  - 特效图标映射：`10` 条。
- `scriptEquip.sc` 字段顺序：

```text
short In(template_id)
UTF   Mn(name)
short Nn(type/stat_type)
byte  Jn(famous/rare flag candidate)
UTF   On(description)
byte  Kn(equipment_level)
short Ln(base_stat)
short Pn(icon_id)
byte  reserved_tail
```

- `Kn` 已由 `gameHD/b.C` 的 `re_装备等级` / “等级”标签验证为装备等级；`Ln` 是基础属性；`Pn` 是图标资源 id。
- `scriptEquipType.sc` 提供强化倍率和材料：

```text
data.d.E(equipment_id) = f[bank][slot][1] * Lo/a.Zn[l3(S4(template_id))][quality]
data.d.j(equipment_id) = Lo/a.Ln[g3(template_id)] + data.d.E(equipment_id)
data.d.k(equipment_id) = [
  ao[type][quality][0],
  max(1, ao[type][quality][1] * (strengthen_value + 1) / 100)
]
```

- `Lo/a.bo [[[S]]` 不在本地脚本中加载，而由 `0xe27f -> LscriptPages/data/g;->s4(String)` 从服务端响应写入；请求入口是 `LscriptPages/data/g;->b2(J,J)`，当 `bo == null` 时发送 `0x627f`，payload 为单字节 `0`。

当前边界：

- 高置信：装备模板、类型、强化倍率、强化材料、属性文案、特效图标映射的本地读取结构和实际值。
- 中置信：`Jn` 是名品/稀有装备标记；true 行集中在倚天剑、青釭剑、青龙偃月刀、神兽装备、名马等。
- 中低置信：`bo` 与 `data.g.v8/w8/x8/B8/C8/D8/y8/z8/A8` 的具体业务名；已知读取结构和 `data.d.B` 使用入口，但当前本地抓包未命中 `0xe27f`。

### 3.13 装备操作响应 `0x8250/0x8252/0x8254` 第一版

已对装备信息、装备穿戴/控制、装备强化/升级三个响应做第一轮合同整理，当前主索引：

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/EQUIPMENT_OPERATION_RESPONSES.md`
- 请求入口表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_operation_requests.csv`
- 响应 schema 表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_operation_response_schema.csv`
- 方法摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_operation_method_summary.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_operation_responses_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_operation_response_summary.json`
- 自动化脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_equipment_operation_responses.py`

请求入口：

| 请求 opcode | 请求方法 | 请求名 | 请求体 | 响应 |
|---:|---|---|---|---:|
| `0x1250` | `scriptPages/game/z.E0(J)` | `reqGeneralEquipInfo` | `writeLong(host_id)` | `0x8250 -> z.F0` |
| `0x1252` | `scriptPages/game/z.C0(J,J,I)` | `reqGeneralEquipCtrl` | `writeLong(host_id); writeLong(equipment_id); writeByte(action_type)` | `0x8252 -> z.D0` |
| `0x1254` | `scriptPages/game/z.G0(J,J,I)` | `reqGeneralEquipLevelup` | `writeLong(host_id); writeLong(equipment_id); writeByte(levelup_mode)` | `0x8254 -> z.H0` |

响应合同：

```text
0x8250 / z.F0:
  readByte sync_mode
  if sync_mode == 0: Lo/a.c6(stream)
  else:              Lo/a.f6(0, stream)
  z.z1 = Lo/a.z2(z.I1)
  # 无 success/message，无 V5/S5

0x8252 / z.D0:
  readBoolean success
  readUTF     message
  readByte    sync_mode
  if sync_mode == 0:
    Lo/a.c6(stream)
    Lo/a.a6(0, stream)
  else:
    Lo/a.f6(0, stream)
  Lo/a.V5(stream)
  Lo/a.S5(stream)
  z.z1 = Lo/a.z2(z.I1)

0x8254 / z.H0:
  z.D3 = 1
  readBoolean success
  readUTF     message
  readByte    sync_mode
  if sync_mode == 0:
    Lo/a.c6(stream)
    Lo/a.a6(0, stream)
  else if sync_mode == 1:
    Lo/a.f6(0, stream)
  Lo/a.V5(stream)
  z.z1 = Lo/a.z2(z.I1)
  if success: play DEPOT_LEVEL_UP_SUCCESS_EFFECT
```

关键边界：

- `0x8250` 更像打开/刷新指定宿主装备信息，只刷新 `c6/f6 + z2(I1)`。
- `0x8252` 是装备穿戴/卸下/控制类完整响应，带 `V5 + S5`。
- `0x8254` 是装备强化/升级响应，带 `V5` 但不带 `S5`；成功时播放强化成功特效，提示中包含 `强化等级→20` 时触发“强化”统计/埋点字符串。
- `z.C0/G0/E0` 请求参数已在 3.15 中由调用点复核固定为 `host_id/equipment_id/action_type|levelup_mode`。

### 3.14 装备强化 UI 与公式链路第一版

已对 `scriptPages/game/z.W0/a/j/e0/h1/u0/V` 串起装备强化页的状态机、材料/属性/成功率/保底/失败风险展示公式，以及普通强化、特殊强化、自动“强化20次”的请求模式。当前主索引：

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/EQUIPMENT_STRENGTHEN_UI_AND_FORMULAS.md`
- UI 状态/字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_strengthen_ui_schema.csv`
- 操作流程表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_strengthen_operation_flow.csv`
- 公式字典：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_strengthen_formula_dictionary.csv`
- 方法摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_strengthen_method_summary.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_strengthen_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_strengthen_extraction_summary.json`
- 自动化脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_equipment_strengthen_ui.py`

关键结论：

- `K1=2` 是强化弹窗；`I1` 是当前装备宿主 id 候选，`H1` 是当前装备实例 id。
- 普通强化：`z.G0(I1,H1,0)` -> `reqGeneralEquipLevelup / 0x1254`。
- 特殊强化：`z.G0(I1,H1,1)` -> `reqGeneralEquipLevelup / 0x1254`；具体消耗/规则仍需动态样本或服务端配置确认。
- 自动“强化20次”不是批量协议；客户端循环发送最多 20 次 `z.G0(I1,H1,0)`，由 `L1/M1/D3` 控制节奏，每轮仍期待 `0x8254`。
- 换装：`z.C0(I1,N1[index],0)` -> `reqGeneralEquipCtrl / 0x1252`；卸装：`z.C0(I1,H1,1)` -> `0x1252`。
- 强化材料展示公式：

```text
type = Lo/a.S4(template_id)
quality = data.d.f[bank][slot][0]
strengthen_value = data.d.f[bank][slot][1]
material_id = Lo/a.ao[Lo/a.l3(type)][quality][0]
base_amount_per_100 = Lo/a.ao[Lo/a.l3(type)][quality][1]
required_amount = max(1, base_amount_per_100 * (strengthen_value + 1) / 100)
```

- 强化属性展示公式：

```text
base = Lo/a.z1(template_id)
coeff = Lo/a.y2(type)[quality]
strengthen_contribution = strengthen_value * coeff
total_stat = base + strengthen_contribution
display_text = Lo/a.w2(type, total_stat)
```

- `data.d.g[bank][slot]` 被格式化为百分比显示在 `di_强化成功率` 后；`data.d.i[bank][slot][0/1]` 显示保底次数；`data.d.p(H1,false)` 在强化等级 `>=10` 时显示失败掉级率，`>=20` 时显示失败损毁率。
- 客户端只做库存/上限预检查和概率/风险展示；真正成功/失败、扣材料、掉级/损毁、保底推进必须由服务端通过 `0x8254 + c6/a6|f6 + V5` 权威同步。

### 3.15 装备请求参数命名 `z.E0/C0/G0` 第一版

已对所有 `z.E0(J)`、`z.C0(J,J,I)`、`z.G0(J,J,I)` 调用点做复核，并结合 `z.Y0()`、`z.b0(J,I,J,I)`、`z.X(I,J,B)`、`z.d()`、`z.W0()`、`gameHD/g.p()`、`gameHD/h.B()`、`gameHD/c.n()`、`game/k0.f0()` 固定请求参数命名。当前主索引：

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/EQUIPMENT_REQUEST_PARAMETER_NAMING.md`
- 调用点表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_request_call_sites.csv`
- 状态字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_request_state_fields.csv`
- 状态写入点表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_request_state_writes.csv`
- 参数结论表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_request_parameter_conclusions.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_request_parameter_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_request_parameter_summary.json`
- 自动化脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_equipment_request_parameters.py`

请求合同：

```text
0x1250 reqGeneralEquipInfo:
  writeLong host_id

0x1252 reqGeneralEquipCtrl:
  writeLong host_id
  writeLong equipment_id
  writeByte action_type      # 0=equip/change, 1=dropoff

0x1254 reqGeneralEquipLevelup:
  writeLong host_id
  writeLong equipment_id
  writeByte levelup_mode     # 0=normal, 1=special
```

关键证据：

- `z.I1` 写入点只有 `z.Y0` 和 `z.b0`：`Y0` 中 `I1=z.n[M]`，随后 `z.z1=Lo/a.z2(I1)` 与 `E0(I1)`；`b0` 第三个参数写入 `I1`，所有调用均传宿主 id 或 `data.d.r(equipment_id)`。
- `z.H1` 是当前装备实例 id：`z.b0` 第一个参数写入 `H1`，`z.d` 从 `z.z1` 选中装备写入 `H1`，后续所有 `data.d.*(H1)`、`C0(I1,H1,1)`、`G0(I1,H1,mode)` 都按装备实例使用。
- 卸装路径总是 `C0(data.d.r(equipment_id), equipment_id, 1)` 或等价的 `C0(I1,H1,1)`；换装路径总是 `C0(host_id, candidate_equipment_id, 0)`。
- `G0` 所有调用点都传 `z.I1,z.H1`；`mode=0` 普通强化/自动强化，`mode=1` 特殊强化。

置信度：

- 高置信：`E0(host_id)`、`C0(host_id,equipment_id,action_type)`、`G0(host_id,equipment_id,levelup_mode)`。
- 中高置信：`host_id` 的最终业务名大概率为 `general_id`；但为兼容 type0 宿主表/可装备对象，当前继续使用更稳妥的 `host_id/current_general_id candidate`。

### 3.16 将领培养 / 将神魂 / 成长值链路第一版

已对 `gameHD/h.f`、`gameHD/h.B`、`gameHD/g.k`、`gameHD/g.p` 与 `0x8275 -> gameHD/g.E` 做专项拆解，补齐 `Lo/a.b6` 中培养相关字段。当前主索引：

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/GENERAL_CULTIVATION_GROWUP.md`
- 字段字典：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/general_cultivation_field_dictionary.csv`
- 请求合同表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/general_cultivation_requests.csv`
- 响应 schema 表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/general_cultivation_response_schema.csv`
- UI 证据表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/general_cultivation_ui_evidence.csv`
- 抓包 opcode 覆盖检查：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/general_cultivation_capture_opcode_check.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/general_cultivation_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/general_cultivation_summary.json`
- 自动化脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_general_cultivation_growup.py`

请求合同：

```text
0x1275 reqGeneralCultivate / reqGeneralGrowUp:
  writeLong  general_id          # Lo/a.b4(0, idx) == Lo/a.co[0][idx]
  writeShort cultivate_count     # h.T 或 g.u1，客户端限制到 1..min(99, 将神魂库存)
```

响应合同：

```text
0x8275 gameHD/g.E(stream):
  readByte result_code
  if result_code in {0,1,2}:
      readLong general_id
      idx = Lo/a.c3(0, general_id)
      Lo/a.a6(0, stream)
      # 0=培养失败, 1=培养成功, 2=批量培养成功并显示 Q2 成长值
  else if -1/-2/-3/-4/-5:
      # 其他错误 / 缺将神魂并询问去商城 / 成长已满 / 非空闲 / 未开放
```

关键结论：

- 培养消耗道具为 `item_id=286`，客户端通过 `Lo/a.p1(286)` 汇总 `Lo/a.bv/cv` 数量并在 `di_将神魂` 下显示。
- `Lo/a.io` / `Q2(0,idx)` 是成长值；培养成功/批量成功提示会显示同步后的成长值。
- `Lo/a.To` 高概率是当前保底/失败累计次数；培养失败也会返回 `general_id + a6(0)`，用于刷新该字段。
- `Lo/a.Uo` / `G3(0,idx)` 是培养保底配对兼“成长值已满”预检查字段；若非 0，客户端直接提示“将领成长值已满”并不发送 `0x1275`。精确业务名仍需真实 `0x8275` 样本确认。
- `Lo/a.So` / `V2(0,idx)` 只见用于索引颜色数组给将领名称上色，可命名为 `general_name_color_or_growth_tier` 候选。
- 当前离线抓包已解析的请求/响应 opcode 中未命中真实 `0x1275/0x8275` 培养交易；本节为静态代码合同，动态取值仍待后续样本。

### 3.17 监狱/俘虏字段语义与动作入口第一版

已对 `scriptPages/game/z.n`、`z.p0`、`z.d1` 与 `game/q.n1/Z0` 做专项拆解，把 `Lo/a.b6` 中监狱/俘虏扩展字段对齐到 UI 标签与动作入口。当前主索引：

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/PRISON_CAPTURE_FIELD_DICTIONARY.md`
- 字段字典：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_capture_field_dictionary.csv`
- 页面模式表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_capture_page_modes.csv`
- 动作请求表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_capture_action_requests.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_capture_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_capture_summary.json`
- 自动化脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_prison_capture_fields.py`

关键字段：

| 字段 | type0 / 我方被俘视角 | type1 / 我方监狱俘虏视角 |
|---|---|---|
| `Po` / `F3` | `被劝次数` | `劝降次数` |
| `Qo` / `f4` | `营救次数` | `被救次数` |
| `dp` / `e4` | `营救剩余`结束时间 | 不使用 |
| `gp` | 所在城名称 | 不使用，type1 走城池表 |
| `hp[0/1]` / `A1` | 所在城坐标 `(x,y)` | 不使用 |
| `ip` | 封地名称 | 不使用 |
| `cp` / `E3` | 不使用 | `劝降剩余`冷却基准，`max(cp+3600000-now,0)` |

动作入口：

```text
0x1233 reqPrisonerCtrlInfo:
  writeByte ctrl_type      # 1=营救前置消耗提示, 0=劝降前置消耗提示候选
  writeLong general_id

0x1238 prisoner rescue:
  writeLong z.D
  writeLong general_id
  writeByte pay_mode

0x1234 prisoner persuade/lure:
  writeLong z.D
  writeLong general_id
  writeByte pay_mode

0x123b give up captured self general:
  writeLong z.D
  writeLong general_id
  writeByte 0

0x1236 release prisoner:
  writeLong z.D
  writeLong general_id
  writeByte 0
```

边界：

- `z.D` 在上述动作中作为第一个 long 传入；已在后续响应深拆中推进为“当前封地/监狱宿主 id”高置信候选，详见 3.18。
- `pay_mode 0/1` 由铜钱/黄金余额分支选择，当前只命名为支付模式候选。
- `Vo==3` 是触发 type0 `dp/gp/hp/ip` 扩展读取的关键状态；完整状态码枚举仍需继续补齐。

### 3.18 监狱/俘虏动作响应合同第一版

已对 `0x8233/0x8234/0x8236/0x8238/0x823b` 对应的 `scriptPages/game/q.o1/b1/c1/d1/a1` 做响应层深拆，补齐动作结果码、同步块边界，以及 `z.D` 的业务名。当前主索引：

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/PRISON_ACTION_RESPONSE_CONTRACTS.md`
- 响应 schema 表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_action_response_schema.csv`
- 结果码表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_action_result_codes.csv`
- host id 语义表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_action_host_id_semantics.csv`
- 抓包 opcode 检查：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_action_capture_opcode_check.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_action_response_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_action_response_summary.json`
- 自动化脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_prison_action_responses.py`

响应合同：

```text
0x8233 -> q.o1(stream)   # reqPrisonerCtrlInfo 前置消耗提示
  readByte  ctrl_type        # 0=劝降, 1=营救
  readByte  not_found_flag   # 1=俘虏不在
  if not_found_flag != 1 and ctrl_type in {0,1}:
      readLong copper_cost   # q.h4，本地与 data.i.d 比较
      readLong gold_cost     # q.i4，本地与 data.g.F 比较
  # 不调用 a6/f6/V5/S5

0x8234 -> q.b1(stream)   # 劝降/招降结果
  readByte result_code
  readUTF  server_message
  if result_code in {0,1}:
      Lo/a.f6(0, stream)
      Lo/a.f6(1, stream)
  else:
      Lo/a.f6(1, stream)
  # 不调用 V5/S5

0x8236 -> q.c1(stream)   # 释放俘虏
  readByte result_code
  if result_code == 0:
      Lo/a.f6(1, stream)
  # 不调用 V5/S5

0x8238 -> q.d1(stream)   # 营救我方被俘将领
  readByte    result_code
  readBoolean full_sync_flag
  if full_sync_flag:
      Lo/a.f6(0, stream)
  else:
      Lo/a.a6(0, stream)
  # 不调用 V5/S5

0x823b -> q.a1(stream)   # 放弃我方被俘将领
  readByte result_code
  if result_code == 0:
      Lo/a.f6(0, stream)
  # 不调用 V5/S5
```

`z.D` / host id 结论：

- `q.M1(J)` 会把输入 long 同时写入 `q.o` 与 `z.D`，并用 `Lo/a.p3(input)` 在封地 id 表 `Lo/a.ov` 中定位当前封地 index，因此 `z.D` 在监狱链路中应保守命名为 `current_fief_id_or_prison_host_fief_id`。
- `Lo/a.G2(z.D,0)` 使用 `Eo[0][idx] == z.D` 过滤 type0 对象；`Eo` 已同步推进为 `object_owner_fief_id`。
- `Lo/a.G2(z.D,1)` 使用 type1 扩展 `Zo[idx] == z.D` 过滤俘虏对象；`Zo` 已推进为 `type1_prison_host_fief_id` 候选。
- 因此 `q.Z0(opcode, z.D, general_id, pay_mode)` 的第一个 long 不是 `general_id`，也不应优先命名为 city id，而是“当前封地/监狱宿主 id”。

仍需动态验证：

- `0x8234 result_code=0/1` 与 `0x8238 result_code=0/1` 的精确细分仍缺真实响应样本。
- `pay_mode=0/1` 已由本地余额比较高置信对应铜钱/黄金，但最终枚举名仍建议用真实样本确认。

### 3.19 客户端全局状态字段索引第一版

已把前面分散在资源系统、V5、c6、a6/f6/b6、data.d 装备容器、监狱动作 host id 里的字段合并成一张全局状态索引。当前主索引：

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/GLOBAL_STATE_FIELD_INDEX.md`
- 字段索引 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/global_state_field_index.csv`
- 同步块地图 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/global_state_sync_blocks.csv`
- 负数资源 ID CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/global_state_negative_resource_ids.csv`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/global_state_field_index_summary.json`
- 自动化脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_global_state_field_index.py`

统计：

- 字段索引 95 行，high/high-* 置信 67 行。
- 覆盖域：`global/player`、`player_limits`、`item_stack`、`equipment_state`、`object_b6`、`object_sync`、`fief`、`fief_sync`、`prison_host_index`。

最关键结论：

| 状态域 | 关键容器/字段 | 当前结论 |
|---|---|---|
| 玩家资源 | `data.i.d/e/m/n/i/j/k/o/q/r/s/t/u/v`, `data.g.F/G/H` | 铜钱、粮食、产量、声望、人口、封地/将领/资源点上限、黄金、白银、账号积分已统一索引。 |
| 负数资源 ID | `data.g.w0/v0/f8` | `-1=铜钱, -2=粮食, -3=白银, -4=黄金, -5=声望, -6=战功, -14=账号积分`。 |
| 通用道具栈 | `Lo/a.bv/cv/dv` | `bv=item_id/stack_id`, `cv=数量`, `dv=long 参数候选`；将神魂=286，玉石=399。 |
| 装备状态 | `scriptPages/data/d.*` | bank0 由 V5 全量重建，bank1 由 c6 维护；`data.d.k` 是 bank1 宿主反链。 |
| 对象/将领 | `Lo/a.a6/f6/b6`, `Lo/a.co/do/...` | type0 为将领/可装备宿主，type1 为监狱俘虏/第二对象表；培养与监狱字段已并入索引。 |
| 封地/宿主 | `Lo/a.ov`, `Y5/Z5/k1`, `Eo/Zo`, `z.D` | `ov` 是封地 id 表；`z.D` 在监狱动作为当前封地/监狱宿主 id 候选。 |

服务端重建影响：

- 未来重建时可以重命名数据库字段，但必须能按这些客户端容器字段序列化回响应。
- `data.g.H` 继续固定为账号积分；玉石必须按 `item_id=399` 道具栈处理。
- `a6` 不负责新增对象，只更新已在 `co[type]` 里的 slot；需要新增/删除列表时走 `f6`。
- 装备系统必须同时处理 `data.d` 装备实例、`Lo/a.jp` 宿主绑定和宿主 `b6` 派生属性。

### 3.20 协议 envelope 与进服最小响应合同第一版

已把真实抓包 `game_flows.json` 中 20 个 HTTP 游戏 flow 按 `scriptPages/conn/a.a()` 的线格式逐字段解析，并与 `Lo/a.A6` 清洗分发表对齐，形成进服阶段最小响应合同。当前主索引：

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/PROTOCOL_ENVELOPE_AND_ENTRY_CONTRACT.md`
- flow 摘要 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/protocol_envelope_flow_summary.csv`
- request command 明细 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/protocol_envelope_request_commands.csv`
- response packet 明细 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/protocol_envelope_response_packets.csv`
- 进服最小合同 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/protocol_entry_minimal_contract.csv`
- 静态反汇编证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/protocol_envelope_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/protocol_envelope_summary.json`
- 自动化脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_protocol_envelope_contract.py`

统计与线格式结论：

- 20 个 HTTP 游戏 flow 全部解析到 EOF，无 parse error。
- 解析 request command 27 条、response packet 33 条。
- 请求 header 全部为 ``1660606`7054`0000480502``。
- 每条 command 的签名 UTF 均为空串，wire bytes 为 `00 00`；这与 `BaseUtil.md5(String)` 反汇编异常/空实现现象相符。
- request command 的 `dm` 全部为 `0x56ee99de606f4744`，`gm` 全部为 `0`；response packet 的 `long0` 也全部为同一 `dm`，高置信是连接/会话级 id 候选。
- 本抓包所有 response packet 的 `obfuscation_flag=0`、`fragment_or_cache_flag=0`，因此无需解密即可直接分发到 `Lo/a.A6`。

请求 envelope 已验证为：

```text
writeUTF(header)
writeLong(client_time)
writeByte(command_count)
repeat command_count:
    writeLong(dm/session_id_candidate)
    writeLong(gm/command_unique_candidate)
    writeShort(payload_length)
    writeShort(request_opcode)
    writeUTF(signature)       # 本样本为空串
    writeByteArray(payload)   # 不再额外写长度
```

响应 envelope 已验证为：

```text
readByte(outer_count)
repeat outer_count:
    readByte(inner_count)
    repeat inner_count:
        readLong(long0/session_id_candidate)
        readLong(long1/server_time_or_sequence_candidate)
        readBoolean(obfuscation_flag)
        readInt(payload_length)
        readShort(response_opcode)
        readBoolean(fragment_or_cache_flag)
        readByteArray(payload)
        if obfuscation_flag:
            payload = Lo/a.P(Lo/a.o(), payload)
        Lo/a.A6(response_opcode, payload, "packetExe")
```

进服阶段 #29~#35 的最小响应序列：

| flow | request command | response packet 序列 |
|---|---|---|
| `#29` | `0x1016` payload=`00000000000002fc` | `0x8001 -> 0x800a -> 0x8146 -> 0x8004 -> 0xa129 -> 0x8280` |
| `#30` | `0x1104 + 0x1113` | `0x8104 + 0x8113`；`0x8113` payload 长度为 0 且分发分支无直接 handler |
| `#31` | `0x1008 cacheData` | `0x8008 + 0x800d`，两个大 payload 是缓存/城池地图初始化关键入口 |
| `#33` | `0x1800 + 0x1800 + 0x3110 + 0x6200` | `0x8800 + 0x8800 + 0xa110 + 0xe200` |
| `#35` | `0x1130 + 0x6200` | `0x8130 + 0xe200` |

服务端重建准备价值：

- 未来最小联机框架必须先满足 envelope 层，否则所有业务 payload 都无法被客户端接受。
- 一个 HTTP request 可批量携带多个 command；一个 command 也可返回多个 response packet（例如 `#29/#31`）。
- `outer_count/inner_count` 不是业务字段，而是 response envelope 的批处理层；不可把它误并入 handler payload。
- `0x8130/0xe200` 二级 parser 字段语义已完成第一版；下一轮应优先展开更大的 `0x8004/0x8008/0x800d/0x8104` 字段语义。

### 3.21 `0x8130` / `0xe200` 进服二级 parser 合同第一版

已按交接手册优先级，把进服关键响应中的任务列表与后页/活跃数据做成第一版二级 parser 合同。当前主索引：

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/ENTRY_SECONDARY_PARSERS_8130_E200.md`
- schema CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_secondary_parser_schema.csv`
- occurrence CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_secondary_payload_occurrences.csv`
- `0x8130` group CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_8130_task_groups.csv`
- `0x8130` entry CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_8130_task_entries.csv`
- `0xe200` summary CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_e200_summary.csv`
- `0xe200` reward CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_e200_rewards.csv`
- `0xe200` active task CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_e200_active_tasks.csv`
- 静态反汇编证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_secondary_parser_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_secondary_parser_summary.json`
- 自动化脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_entry_secondary_parsers.py`

统计与验证：

- `0x8130` 样本出现 2 次，唯一 payload 1 个，长度 934，按 `m0.s -> m0.n` schema 解析到 EOF。
- `0xe200` 样本出现 4 次，唯一 payload 1 个，长度 1394，按 `gameHD/a.h` schema 解析到 EOF。
- 两类 payload 当前 parse error 为 0。

`0x8130` 任务列表结构：

```text
0x8130 payload:
  repeat 4 groups:
      readByte primary_count      # primary 条目写 p0=1，并累加 m0.w0
      readByte secondary_count    # secondary 条目 p0 默认 0
      repeat primary_count:
          readLong task_id
          readUTF  task_name
          readBoolean flag_o0
      repeat secondary_count:
          readLong task_id
          readUTF  task_name
          readBoolean flag_o0
  readShort trailing_short        # 当前样本为 0，读取后未直接保存
```

当前样本 4 个 group：

| group | 标签候选 | primary | secondary | first id/name |
|---|---|---:|---:|---|
| `0` | 普通/成长任务候选 | 0 | 11 | `0x2714` 种植技术 |
| `1` | 活动/运营任务候选 | 0 | 15 | `0x9b58ffba` 每日在线领好礼 |
| `2` | 国家/大型玩法入口候选 | 0 | 5 | `0x7919` 百家争鸣 |
| `3` | 兑换/特殊入口候选 | 0 | 2 | `0x791a` 元宝换黄金 |

边界：`boolean flag_o0` 只是静态字段写入名，暂不要过早命名为“已完成/可领取”；group 中文标签也仍是候选，需要 UI 页签/任务详情 `0x8132` 继续对齐。

`0xe200` 后页/活跃数据结构：

```text
0xe200 payload:
  readByte  s0_status
  if s0_status == 1: early return / not-open branch
  readLong  t0
  readShort u0
  readByte  v0, w0, x0, y0
  readByte  A0_count; repeat A0_count: readByte -> B0[]
  readByte  C0_count; repeat C0_count: readByte -> C0[]
  readByte  D_count; repeat D_count: readByte marker, readUTF reward_text, readByte status
  readUTF H0_text
  readLong ignored_or_activity_id
  readShort z0_active_score
  readShort I_count; repeat I_count: readUTF task, readUTF progress, readUTF reward
  readShort H_count; repeat H_count: readUTF task, readUTF progress, readUTF reward
  readByte L_count; repeat L_count: readShort threshold, readUTF reward, readShort aux
  readShort week_current; readShort week_target; readBoolean week_done; readUTF week_reward
  readShort month_current; readShort month_target; readBoolean month_done; readUTF month_reward
```

当前样本关键值：

- `s0_status=0`，进入完整数据分支；`s0_status=1` 为“暂未开放/关闭提示”早退分支。
- `u0/v0/w0 = 2026/7/5`，高置信是日期；`x0/y0=3/31` 仍保守候选。
- `z0_active_score=20`。
- 每日活跃任务 `I_count=15`，特殊活跃任务 `H_count=3`，活跃奖励档位 `L_count=5`。
- 周奖励进度 `30/600`，月奖励进度 `30/2800`。
- 奖励文本明确包含铜钱、粮食、白银、玉石、将神魂、图腾碎片、行军符、凝魂晶石等。

服务端重建准备价值：

- `0x8130` 不只是“任务列表文本”，还携带 4 组入口/任务状态数组，未来服务端需要按组序列化。
- `0xe200` 是后页/活跃度 UI 的完整数据块，活动奖励与活跃任务文本来自服务端 payload，不是纯本地静态表。
- 当前 `0xe200` 奖励文本中玉石仍按文本出现；资产同步层仍以 `item_id=399` 为准。

## 4. 当前模块地图

| 模块 | 客户端入口/证据 | 服务端重建价值 |
|---|---|---|
| 启动/配置 | `defautConfig.properties`，`resource/client.action?channel=`，`Lo/a.J8` | 还原登录前配置、资源服、游戏服地址。 |
| HTTP 游戏协议 | `BaseIO` + `Lo/a.d0` + `scriptPages/conn/a.a` + `Lo/a.A6` + `PROTOCOL_ENVELOPE_AND_ENTRY_CONTRACT.md` | 后续所有 handler 的基础包格式、批量 command/response envelope、进服最小响应序列。 |
| 商城 | `reqItemMallGoods/0x1100`，`buyMallGood/0x1102` | 商品列表、购买校验、货币扣减。 |
| 邮件/客服 | `reqCheckMsg/0x1114`，`reqSendMsg/0x1118` 等 | 邮件列表/详情/客服问答。 |
| 角色/将领 | `reqRoleInfo/0x1120`，`scriptPages/game/w`，`0x1275/0x8275` 培养，`0x1233/0x8233`、`0x1234/0x8234`、`0x1236/0x8236`、`0x1238/0x8238`、`0x123b/0x823b` 监狱 | 角色详情、将领展示、培养/成长值/保底次数、监狱/俘虏和单将领 `a6/b6/f6` 同步。 |
| 奖励/任务 | `reqGainAward/0x1134`，`0x1130/0x1132/0x1134`，`0x8130 -> m0.s/m0.n` | 任务列表 4 组结构、详情、领奖同步。 |
| 称号/成就 | `0x1180/0x1184/0x1186` | 称号、成就、效果数值。 |
| 封地/建筑 | `reqRoleFiefList/0x1310`，`fiefMove/0x1212`，建筑 `0x1200` 系列 | 封地列表、建筑同步、建造/升级/拆除。 |
| 城池/地图 | `0x800D -> s0.b([B)`，`reqFightingCity/0x1012` | 城池缓存、攻城入口、城市状态。 |
| 资源/资产同步 | `data.i.*`，`data.g.*`，`Lo/a.V5`，`Lo/a.c6`，`GLOBAL_STATE_FIELD_INDEX.md` | 铜钱、粮食、黄金、白银、账号积分、背包、装备 bank0/bank1、对象/封地状态索引。 |
| 装备/强化 | `scriptPages/game/z.W0/a/j`，`z.C0/G0`，`0x8252/0x8254`，`scriptPages/data/d` | 装备穿戴/卸装、强化材料/属性/成功率/保底/风险展示、服务端权威强化结果同步。 |
| 山贼/资源点 | `reqThiefList/0x1540`，`reqResourceList/0x1542` | 地图目标、守军、掉落/收益。 |
| 战斗/战报 | `0x1520/0x1522/0x1702/0x1707/0x640D`，`scriptPages/game/s` | 客户端回放结构；基础胜负/伤害多为服务端权威。 |
| 道具/礼包 | `reqUseItem/0x3144`，`scriptItem.sc` | 道具效果、礼包固定奖励、随机池待深拆。 |
| 六部/活动 | `0x6340~0x6343`，`a0/a`，`0x6200 -> 0xe200 -> gameHD/a.h` | 活动任务、六部任务、动态配置、后页/活跃度任务与奖励。 |

## 5. 客户端/服务端职责边界

当前高置信结论：

1. 客户端负责 UI、资源展示、请求组包、响应解析、战斗回放、本地预检查和部分静态表展示。
2. 服务端负责账号/会话、资产权威、库存扣减、时间推进、任务/活动动态配置、掉落、战斗结算、地图状态和绝大多数最终数值公式。
3. 客户端包含大量规则文本和展示表，但不等同于完整权威配置。
4. 未来重建服务端时，不能只按客户端显示公式实现；必须按协议响应字段和客户端状态同步块来满足客户端期望。

## 6. 为未来重建服务端最关键的客户端问题

当前建议优先理解，而不是实现：

1. **主协议包格式最终定名**：第一版已完成，主索引为 `PROTOCOL_ENVELOPE_AND_ENTRY_CONTRACT.md`；后续只需用更多重连/切区样本验证 `dm/gm/long1` 和 `obfuscation_flag=1` 解密分支。
2. **响应分发全表清洗**：第一轮已完成，当前主索引为 `PROTOCOL_RESPONSE_DISPATCH_CLEAN.md`；后续应按重点 handler 做人工复核和二级 parser 展开。
3. **`Lo/a.V5` / `Lo/a.c6` / `Lo/a.a6/f6/b6/S5` 复合同步块与装备、培养、监狱系统**：第一版均已完成并汇入 `GLOBAL_STATE_FIELD_INDEX.md`，当前主索引为 `V5_COMPOSITE_SYNC_BLOCK.md`、`C6_EQUIPMENT_BANK1_SYNC.md`、`A6_F6_GENERAL_SYNC.md`、`DATA_D_EQUIPMENT_ACCESSORS.md`、`EQUIPMENT_STATIC_TABLES.md`、`EQUIPMENT_OPERATION_RESPONSES.md`、`EQUIPMENT_STRENGTHEN_UI_AND_FORMULAS.md`、`EQUIPMENT_REQUEST_PARAMETER_NAMING.md`、`GENERAL_CULTIVATION_GROWUP.md`、`PRISON_CAPTURE_FIELD_DICTIONARY.md` 与 `PRISON_ACTION_RESPONSE_CONTRACTS.md`；后续重点是用真实样本验证候选字段取值和动态分支。
4. **初始登录后自动请求序列**：#29~#35 已完成 envelope/handler 对齐，`0x8130/0xe200` 二级 parser 第一版已完成；后续重点是展开更大的 `0x8004/0x8008/0x800d/0x8104` payload。
5. **全局数据字典**：第一版已完成，主索引为 `GLOBAL_STATE_FIELD_INDEX.md`；后续继续把低置信字段按 UI/样本转正。
6. **脚本/表资源格式索引**：区分展示表、可直接服务端复用表、仅文本说明、仍未知二进制表。
7. **战斗边界**：继续确认哪些只属于客户端回放，哪些必须由服务端返回。

## 7. 当前推荐下一步

不进入服务端重建时，下一步最值得做：

1. 继续展开 `0x8004` gameLogin 主响应，重点验证 `data/i.y -> f6/c6/S5` 的进服状态同步边界。
2. 展开 `0x8008/0x800d` 大 payload，补城池缓存、地图缓存字段命名。
3. 将 `0x8130` group 业务中文名与 UI 页签/任务详情 `0x8132` 做动态或静态对齐。
4. 用更多进服/切区/重连样本验证 `dm/gm/long1` 的最终命名；若出现 `obfuscation_flag=1`，验证 `Lo/a.o()` 与 `Lo/a.P()` 解密分支。
5. 若后续抓包能触发 `0x1275/0x8275`，验证 `To/Uo/So` 的动态取值、将神魂扣除同步块，以及服务端保底规则。
6. 若后续抓包能触发 `0x1233/0x8233`、`0x1234/0x8234` 或 `0x1238/0x8238`，验证监狱动作 `result_code=0/1` 细分与 `pay_mode=0/1`。
7. 若后续抓包能触发 `0x627f -> 0xe27f`，按 `data.g.s4` schema 解析 `Lo/a.bo` 与 `data.g.v8/w8/x8/B8/C8/D8/y8/z8/A8` 的真实值。
8. 继续把低置信字段（`Lo/a.dv`、`data.d.j/m`、type1 `Wo/Yo/ap`、部分 fief 隐藏字段）按 UI/样本逐步转入全局索引。
