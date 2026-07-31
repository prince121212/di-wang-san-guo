# 帝王三国电脑端辅助前端 + 本地后端

入口目录：

```text
/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/电脑端辅助前端
```

## 启动

```bash
cd /Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/电脑端辅助前端
python3 server.py
```

浏览器打开：

```text
http://127.0.0.1:17351/index.html
```

## Android 本地 V1（共享前端，不依赖电脑）

`index.html`、`app.js`、`styles.css` 和 `assistant-api.js` 是电脑与 Android 共用的单容器 UI 源码，但两端拥有各自独立的执行核心：

```text
电脑浏览器：共享页面 → HTTP /api/* → server.py → 电脑端核心
Android：   APK 内共享页面 → 本机消息桥 → Kotlin 本地核心 → 游戏服务器
```

Android 构建只复制上述四个静态文件到 APK assets。手机页面里的 `/api/*` 由 `assistant-api.js` 交给 `window.DWPMNativeApi`，不请求本目录的 `server.py`，也不访问电脑地址、Mobile API、代理或云地图。

手机模式复用相同控件语义，但只显示一个容器，并移除电脑专属的总控、多容器、地图工具页、一键全启和 IP/代理区域。六部因缺少逐项真机动作证据而在手机模式禁用；打矿撤防历史配置在 Kotlin 任务入口强制关闭。

### Android 本机接口职责

| 路径组 | 本机职责 |
|---|---|
| `/api/accounts/*` | 真实登录、Keystore 凭据、账号启停与删除 |
| `/api/settings/*` 与各功能保存接口 | 每账号本地配置 |
| `/api/automation/*` | 启停唯一前台调度服务 |
| `/api/state/*`、`/api/logs/*` | 本地状态、完成次数和脱敏日志 |
| `/api/maps/bandits`、`/api/maps/mines` | 手机本地山贼与资源点地图 |

密码和 Session 认证字段使用 Android Keystore 管理的 AES-GCM 密钥分仓保存，不写入账号 JSON 或导出。用户添加手机托管账号时必须明确勾选凭据授权；启动托管还会检查可自动重登的密文是否存在。通知权限和电池优化豁免只在用户点击启动后请求。

完整 Android 架构、构建和验收边界见：

```text
/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/手机端辅助V1架构.md
/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/自研辅助源码/README.md
```

### 历史 Mobile API 边界

`server.py` 中保留的 `/api/v1/mobile/*`、Token 配对和旧兼容桥只属于电脑端历史兼容能力，不是 Android V1 的运行链路。不要通过启动局域网 Mobile API 来验收手机本地 V1；电脑服务关闭时，Android 本地登录、设置和调度仍应可用。

### 回归测试

```bash
python3 -m unittest discover -s tests -q
node --check app.js
```

当前共用前端全量测试为 470 项。真实账号验收遵循“先只读、再单账号单功能”的顺序；未经明确授权不启动批量托管。

## 同一账号跨区服运行规则

- 同一个游戏平台账号即使登录不同区服，也会互相顶掉游戏会话。
- 同一账号任意时刻只能运行一个区服；切换区服前，必须先停止旧区服的起号任务并关闭旧区服账号。
- 不允许依赖“区服不同”绕过重复登录保护，否则两个区服都可能反复掉线、无法正常运行。

## 已接入的真实链路

前端整体已按 `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/帝三辅助设计`
中的 21 张原型图还原为手机辅助样式的电脑端网页壳；真实操作链路通过底部
「保存设置」和添加账号弹窗接入本地后端 API：

1. `添加`
   - 打开添加账号弹窗；
   - 输入账号、密码、区服；
   - 后端真实登录 passport + 游戏服；
   - 读取角色、区服、将领数据。

2. `保存设置`
   - 读取「刷黄」页配置；
   - 后端发送 `041540`；
   - 解析真实 `0x8540` 目标列表；
   - 按前端控件筛选目标类型、山贼等级、步弓骑车条件。

3. 后台自动出征
   - 后端发送 `15200a0` prepare；
   - 后端发送 `15220a0` expedition；
   - 返回战报文本；
   - 证据报告保存到：

```text
/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/电脑端辅助前端/reports/
```

## 步弓骑车控件含义

前端视觉仍保留原型中的 `步弓骑车` 四位码输入，例如：

```text
5203 = 步≤5、弓≤2、骑≤0、车≤3
```

- `0525` = 步≤0、弓≤5、骑≤2、车≤5
- `5203` = 步≤5、弓≤2、骑≤0、车≤3
- `5000` = 必须含步 + 步≤5、弓≤0、骑≤0、车≤0，即只选“只含步兵类型”的山贼

当前 041540 可以稳定拿到目标等级、坐标、掉落等真实字段；敌方步/弓/骑/车精确明细仍需要继续用更多战报样本校准。现在后端已先接入可执行的等级模板筛选模型，控件会真实影响找黄结果和出征目标选择。


## 当前验证证据

最近一次 5000 筛选 + 真实出征成功证据：

```text
/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/电脑端辅助前端/reports/frontend_controls_5000_success_verification.json
```

该证据显示：

- 测试账号真实登录到 `董全 Lv.12`；
- 后端从真实登录数据读取到将领列表；
- `5000` 筛选命中 `compositionCode=1000` 的 1级山贼；
- 真实发送 `15200a0 + 15220a0` 后，战报包含 `消灭 步1消灭1级山贼`。

## 2026-07-26 军情解析升级（抓包 20260726_173635）

军情专项抓包（`ctf_out/passive_pcap_hotspot_20260726_173635`，带口述
时间线）带来四个新结论，全部已进 `parse_8600_military_actions`：

1. **副本关卡战斗真实出现在 0x8600 军情里**：`【副本】…参与副本关卡
   宦官乱政，战斗进行中`，`targetType=0x0e`，targetName 是关卡名。
   不带“战斗进行中”后缀的是已建队未开战的多人副本 → 状态“备战”。
2. **“出征”与“战斗”按尾部区分**：战斗类标签（攻占/消灭/夺取/掠夺）
   带去程尾部且剩余 > 0 → 状态“出征”（操作者口述“还在行军中”）；
   剩余为 0（此时文本带“战斗进行中”）→ “战斗”。
3. **新尾部/目标类型**：山贼去程尾部是 `0x0b`（结构与 0x09 相同），
   副本尾部是 `0x17`（无行军，剩余恒 0）；`targetType 0x03=山贼、
   0x0e=副本关卡`。
4. **marchValue 语义修正**：它是**剩余行军毫秒**（同一 battleId 连续
   刷新递减：93949→57857→41442→22448；回程 38322→24407→13988），
   不是旧注释写的“总时长”；eventTimeMs 是恒定的预计到达/到家时刻，
   战斗中则 ≈ 服务器当前时间（不能当倒计时）。军情页“剩余时长”
   倒计时锚定 `快照时刻 + marchValue`，每秒原地刷新。

状态排序变为：战斗 → 出征 → 驻守 → 返回 → 备战。

### 副本章末关（多人副本）

每章最后一关是多人副本，单人无法挑战：广宗决战建队后 0x8522 只回
“多人副本创建成功”，正是此前日志里副本任务卡死的原因。已做三层处理：

- 打通模式 `first_uncompleted_dungeon_stage` 自动跳过章末关
  （打通倒数第二关会同时解锁本章末关和下一章第一关，口述时间线确认）；
- `execute_dungeon` 对章末关直接拒绝并给出明确报错；
- 前端“副本”页关卡下拉不再提供各章最后一关。

顺带记录（**不主动调用**，抓包 flow 019）：解散组队接口为
`0x193a -> 0x893a`，多人副本误建队后可用它退出。

回归：`tests.test_military_intel` 新增 20260726 抓包样本 13 项断言
（副本记录、0x0b 尾部、剩余递减、空军情、章末关跳过/拒绝）。

## 2026-07-26 军情页并入“辅助此刻行动”（任务引擎实时）

0x1600/0x8600 只反映野外军情（攻占/驻守/返回）：副本战斗走 0x1938/0x8938
独立信道，正在配兵/发起中的出征也不会出现在军情列表里。军情页现在分两个
区块，来源分开、互不冒充：

```text
辅助此刻行动 · 实时          ← 任务引擎本地状态，纯本地组装，不发游戏请求
服务器军情 · 0x1600/0x8600   ← 原有军情快照，仍只在进入页面/手动刷新时拉
```

“辅助此刻行动”覆盖：

- 刷黄：`brushInFlight` 在途编队 → “灰1、车1 正在与6级山贼(92,25)战斗”，
  含 battleId、第几轮、出征时刻；
- 副本：`execute_dungeon` 启动成功落下的 `currentDungeonBattle` 战斗标记
  （循环模式现在也维护 `currentDungeonStage`）→
  “攻弓2、智步4、智步5、智步6、骑1 正在与副本第1章第12关战斗”；
- 打矿：`lastTarget` + 指挥中心 fighting → “车1 正在驻守1级镔铁矿(95,30)”；
- 其他常驻任务：`schedulerState=fighting/dispatching` 与 `schedulerMessage`。

行动“状态”（战斗/出征/驻守/返回）一律以心跳回来的将领真实忙闲
（征/战/防/返）定名；将领已全部回闲的在途记录不再展示——宁可少一条，
不把已结束的行动冒充“此刻”。

```text
server.py
- assistant_live_operations        汇总入口（public_session 与
                                   /api/automation/status 均返回 assistantOperations）
- _assistant_operation_state_from_generals / _assistant_target_display

app.js
- junqingLiveOpCardHtml / applyAssistantOperations
- refreshJunqingLiveOps            军情页打开时每 2 秒读 /api/automation/status
- updateJunqingTimeTexts           每秒原地更新“已进行/预计到达”文本

tests/test_assistant_operations.py  13 项，数据形态取自 2026-07-26 运行日志
```

刷新节奏：辅助行动随 2 秒任务轮询实时更新（本地数据，零游戏请求）；
0x1600 服务器军情仍只在进入军情页和点击「刷新军情」时发送，节奏不变。

## 2026-07-26 军情页改用真实军情接口（0x1600/0x8600）

军情页此前的数据来自 `0x3110 -> 0xa110` 心跳混合包，按关键词从文本里
捞“出征/返回/胜利”，所以既混进活动任务文本，又是历史事件流。本轮改为
真实军情列表：

```text
0x1600 -> 0x8600
```

请求体与真实客户端逐字节一致（`07000000000000000000000014`），常量为
`server.py: MILITARY_INTEL_REQUEST_PAYLOAD`，打矿召回复核也复用同一常量。

### 军情语义

军情展示的是**此刻正在进行的军事行动**，不是历史记录。同一次出征在
0x8600 里始终是同一个 `battleId`，随时间在三个状态之间流转：

```text
【攻占】…战斗进行中  →  【驻守】…驻守在X  →  【返回】…返回某某的封地
```

行动结束后该记录从军情里消失，页面就应该是空的。

### 已确认的记录结构

每条行动锚定在一个 `【…】` 事件文本上，文本之后的结构按抓包确认：

```text
u16 state16 | u32 state32 | u64 battleId | u8 generalCount
generalCount × (u64 generalId + u8 flag)
u64 targetId | u8 targetType | utf targetName | u16 x | u16 y
```

- `targetType`：`0x01` 封地/基地（无坐标），`0x02` 野外目标（有坐标）。
- 行军类尾部 `u8 marchKind(0x09 去程 / 0x0d 回程) + u32 + u64 毫秒时间戳`
  只在“去程/回程”记录里出现，驻守记录是另一种尾部形状，不解析。
- 回程时间戳已验证等于预计到家时间（抓包 13:02 召回 → 时间戳 13:35，
  与操作者口述“返回途中 30 多分钟”吻合）。**战斗态**的时间戳含义未确认，
  前端不拿它当倒计时展示。
- 其余尾部字节一律不解释、不猜测；结构自校验失败的候选直接丢弃。

### 关键函数与接口

```text
server.py
- MILITARY_INTEL_REQUEST_PAYLOAD
- parse_8600_military_actions       完整军情记录解析
- parse_8600_military_march_tail    行军尾部（含预计到达时间）
- parse_military_snapshot_from_packets
- refresh_military_snapshot         发送 0x1600 并写入 sess["militarySnapshot"]

app.js
- renderJunqing / junqingCardHtml / junqingEmptyHtml
```

- `GET /api/state/refresh?scope=military` 与 `GET /api/military/intel`
  都改为拉取真实军情快照。
- `public_session` 新增 `militarySnapshot`；原 `militaryIntel`（0xa110
  将领忙闲）保持不变，两者互不覆盖，打矿/刷黄状态机不受影响。
- `militarySnapshot` 列入 `RUNTIME_TRANSIENT_SESSION_FIELDS`，**不持久化**：
  军情是此刻状态，重启后必须重新向服务器确认，不允许旧军情冒充实时数据。

### 刷新节奏

只在**进入军情页**和**点击「刷新军情」**时发送 0x1600，与真实客户端一致；
不做常驻轮询，也不并进 20 秒心跳。

### 空态区分

页面把四种情况分开显示，空列表不会冒充“确认无军情”：

```text
账号未启动          → 提示先启动账号
从未拉取（updatedAt=0） → 提示点击刷新
拉取了但没收到 0x8600   → 明示未收到响应
收到 0x8600 且无行动    → 当前没有进行中的军情
```

### 回归

```bash
python3 -m unittest tests.test_military_intel   # 14 项，全部基于真实抓包
python3 -m unittest discover -s tests -p 'test*.py'
```

真值来自三份带 `operator_timeline.md` 口述记录的军情抓包：

```text
ctf_out/passive_pcap_hotspot_20260714_033644   牧场(91,28)，步2/步3/车2/车1
ctf_out/passive_pcap_hotspot_20260714_044023   镔铁矿(95,30)，步2/车2
ctf_out/passive_pcap_hotspot_20260714_125113   水晶矿(136,20)，步1/车1
```

单测断言的坐标和参战将领与玩家当时的口述完全一致，不是自证式断言。

## 2026-07-14 打矿与资源地图

- `0x1542/0x8542` 按抓包确认结构解析，资源协议类型为
  镔铁、水晶、玄铁、牧场、浆果、灵草、玉露、银矿；牧场再按
  `level=1/2/3` 显示为一级、二级、三级牧场。
- 完整业务编号保留 1～13，其中已消失的金矿、冰玉矿、仙芝园
  不再出现在可选项中，实际可选 10 种。
- 资源点、扫描区域、区域关系、扫描租约和目标占用均写入
  `reports/shared_maps/shared_maps.sqlite3`，资源点有效期为 3 小时。
- 电脑版工具栏的“山贼地图”下方新增“资源地图”，可按资源类型和
  玩家归属筛选，并展示数量、守军、发现时间和剩余有效期。
- 打矿执行链路：

```text
容量/将领/配兵检查
→ 以中心坐标扫描资源点
→ 排除玩家占领点
→ 出征前按 resourceId 定点复核
→ 0x1520 预览并校验目标坐标
→ 0x1522 正式出征
→ 0xa110 确认将领状态“防”
→ 0x1600/0x8600 确认军情“驻守”
→ 0x1526/0x8526 召回
→ 确认将领回闲
→ 重新扫描并更新资源地图
```

## 2026-07-08 保存设置自动刷黄修复

本轮修复了「刷黄页面点击保存设置没有反应」的问题：

- 前端底部 `保存设置` 现在会收集：
  - 登录后的 session；
  - 「军事 → 配兵」里启用的出征将领、兵种、数量；
  - 「刷黄」页中心坐标、扫描格数、目标等级；
  - 步弓骑车四位码，例如 `5203` = 步≤5、弓≤2、骑≤0、车≤3；
  - 循环上限、循环间隔。
- 新增后端接口：
  - `POST /api/settings/save`：保存配置并启动后台自动刷黄任务；
  - `GET /api/automation/status?sessionId=...`：查看后台任务状态和日志；
  - `POST /api/automation/stop`：停止后台任务。
- 后台任务真实执行的链路：

```text
保存设置
→ 041540 找山贼
→ 按 5203 / 等级 / 类型筛选
→ 任选一个命中目标
→ 使用配兵页选中的将领发送 15200a0 + 15220a0 出征
→ 记录战报与 report 文件
→ 等待将领返回
→ 治疗伤兵节点
→ 0x1229 批量补兵/补满该将领
→ 进入下一轮并重复，直到达到循环上限或手动停止
```

当前边界：

- 补兵已接入已恢复的 `0x1229 reqBathAddArmy / 批量补兵`，请求格式为 `count + 8-byte general ids`，响应解析 `0x8229`。
- 治疗伤兵协议请求字段仍未完全确认，电脑端仍只保留“治疗伤兵”节点和日志，不发送未知治疗包，避免误操作。

## 2026-07-08 配兵到目标兵种数量接入

本轮进一步把“补兵至 200 轻骑兵”的语义向真实客户端靠拢：

- 新增 `0x1226 generalWithSoldier` 配兵请求：
  - payload = `writeLong(generalId) + writeByte(group=0) + writeShort(soldierTypeCode) + writeInt(count)`；
  - `轻骑兵` 的 row code 为 `3`；
  - 对“将领A 200 轻骑兵”会发送 payload：`generalId + 00 + 0003 + 000000c8`。
- 新增 `0x8226` 配兵响应解析；成功状态按客户端 handler `z.S()` 的 `status == 1` 判断。
- 后台循环恢复阶段现在顺序为：

```text
治疗伤兵节点
→ 0x1226 将领配兵到目标兵种/数量（例如 200 轻骑兵）
→ 0x1229 批量补兵/补满
→ 下一轮找黄
```

说明：治疗协议 `0x1231/0x1230` 字段已恢复并生成安全计划，但当前仍等待稳定“当前伤兵数量”来源；缺少数量时不会盲发治疗包。

## 2026-07-08 治疗伤兵真实请求接入

治疗协议已从“只记录节点”推进为可发送真实请求：

- `0x1231`：治疗费用预估；
- `0x1230`：治疗伤兵；
- 缺少精确伤兵数时，使用客户端历史 shape 对应的“治疗全部”语义：

```text
0x1231: fiefId + soldierType=-1 + count=-1
0x1230: fiefId + group=2 + soldierType=0 + count=-1 + useGold=0
```

后台循环目前恢复阶段为：

```text
治疗伤兵
→ 0x1226 配兵到目标兵种/数量
→ 0x1229 批量补兵/补满
→ 下一轮找黄
```

如果当前将领记录缺少 `fiefId/placeID`，治疗会安全跳过并继续后续配兵/补兵。
