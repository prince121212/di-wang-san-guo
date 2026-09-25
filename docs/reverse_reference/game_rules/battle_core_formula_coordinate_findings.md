# 战斗核心公式/蓄力/坐标阶段性逆向结论

## 1. 基础伤害/损兵

### 已确认
- 回放/战场表现层不重新计算基础伤害，而是消费战斗指令中的“前后兵数/剩余兵数/蓄力变动”。
- 普通攻击指令缓冲：`LscriptPages/game/s;->a([J [S [J [S [I)I`，执行入口在 `s->f0()` 的 command type 6。
- 战法指令缓冲：`LscriptPages/game/s;->l([J[S[S[J[S[S[I[I)I`，展示/结算入口在 `s->p0(I)Z` 的 command type 11。
- `s->p0()` 中 `re_损兵描述` 使用 `p2 - q2` 作为损兵数量：`000362 aget p2`、`000366 aget q2`、`00036a sub-int/2addr`。
- `s->f0()` 普攻损兵：目标 flag `8192` 时，`d2` 中带的是“新剩余兵数/城墙值”；客户端取旧值 `B0/N0` 与新值相减，仅做显示与状态同步。

### 证据路径
- `/analysis/game_rules/battle_dex/method_disasm/scriptPages_game_s__f0__0x33aa44.smali.txt`
  - `000c42-000cde`：普通攻击损兵同步，`B0`/`N0` 与 `d2` 比较/更新。
- `/analysis/game_rules/battle_dex/method_disasm/scriptPages_game_s__p0__0x32eb2c.smali.txt`
  - `00035a-0003ba`：战法损兵文本，`amount = p2 - q2`。
  - `000d4a-000d88`：战法效果结束后调用 `s->g(x,y,loss,1)` 漂字。

### 当前判断
- APK 客户端内已完整恢复“损兵如何在回放中落地”；但“基础伤害 = 攻防血兵数等如何算出”目前没有在 `s`/`data.g` 回放路径发现，倾向于服务端计算后下发。
- 若要继续追公式，应转向 `KING_BATTLE_SIMULATOR3.0` 相关路径和服务端模拟器数据构造函数，而不是 `s->f0/p0` 回放执行器。

## 2. 攻速/蓄力机制

### 已确认
- `C0[S]` 是单支部队当前攻击蓄力上限/攻击间隔，单位毫秒。
- `F0[J]` 是本轮攻击/蓄力开始时间戳。
- `E0[I]` 是暂停蓄力时记录的剩余时间。
- `D0[I]` 是蓄力增减偏移累计，回放中由 `16/32` flag 更新。
- 文本显示中蓄力值除以 `1000` 展示为秒。

### 证据路径
- `s->h(...)` 初始化部队：
  - `0002b4-0002be`：参数 v35 写入 `C0`。
  - `0002c2-0002d0`：`D0/E0` 初始化为 0。
- `s->p0(I)Z`：
  - `00041e`、`0004a4`：`delay / 1000`。
  - `000870-0008a6`：添加“混乱/固守”等暂停类 buff 时计算剩余蓄力 `E0 = C0 - (now - F0)`。
  - `000992-0009cc`：移除暂停类 buff 时恢复 `F0 = now - (C0 - E0)`。
  - `0008c2-0008d4`、`0009e8-0009fa`：部分攻速类效果直接写新 `C0 = p2`。
  - `000d90-000dde`：flag `16/32` 修改 `D0`，对应“蓄力减少/增加”的回放值。
- `sentence.txt`：
  - `re_攻击蓄力减少描述` / `re_攻击蓄力增加描述`。

### 当前判断
- “攻速换算为蓄力上限”的入口已经定位到 `C0`，但原始公式还需追 `s->h(...)` 调用源或模拟器路径中传入 v35 的生成逻辑。
- 战法表中“攻速提升/降低 # %”最终会表现为新 `C0` 或暂停/恢复逻辑。

## 3. 战场坐标/前后左右规则

### 已确认
- 客户端战场坐标是 2D 像素坐标，移动时每 tick 以 20 像素步进逼近目标。
- 战斗坑位分两方、若干列/排；X 坐标按阵营镜像，Y 坐标按排编号递增。
- 阵型有“正/斜”两种：`H[0] = {0,0,0,0,0}`，`H[1] = {-96,-48,0,48,96}`；当前阵型偏移写入 `G[S]`。

### 关键公式
- `C(row) = m * row + 558`，`J(row)` 相同。
- `B(camp, lane, col) = q + sideSign*(n+10) + sideSign*(col*l + optional_l) + G[lane]`
  - `camp==0` 时取负方向；`camp!=0` 时取正方向，且 `optional_l` 被置 0。
- `I(camp, lane, col) = q + sideSign*(3*l + 2*n) + sideSign*(col*l + optional_l) + G[lane]`
  - 用于从行军区进入战斗区时的目标位置。
- 常量来源：
  - 普通模式：`l=78`，`m=40 + screenH*15/1000`（低屏幕时 m=40），`n=10`。
  - HD/df==1：`l=128`，`m=64`，`n=20`；若屏幕高 <480，`m=40`。

### 证据路径
- `s->B(I I I)I`：`/method_disasm/scriptPages_game_s__B__0x330c44.smali.txt`
- `s->C(I)I`：`/method_disasm/scriptPages_game_s__C__0x330c90.smali.txt`
- `s->I(I I I)I`：`/method_disasm/scriptPages_game_s__I__0x330de4.smali.txt`
- `s->N()V`：`/method_disasm/scriptPages_game_s__N__0x336cd0.smali.txt`，选择 `G = H[formation]`。
- `s->f0()`：`000454-0004ec`、`0011d2-001292`，每 tick X/Y 最多加减 20。

## 4. 仍需继续的点
- 继续从 `s->h(...)` 的调用源追 v35（攻击间隔/C0）的计算。
- 继续从 `data/g;->F3/L4/G` 与 `KING_BATTLE_SIMULATOR3.0` 相关函数追是否存在本地模拟基础伤害公式。
- 若本地模拟器只是组装请求/配置，则基础伤害公式只能从真实服务端行为样本拟合或重写。

## 5. 新增：C0/攻击间隔的上游来源

- `s->Z(String)` 解析 fight/battle 指令流，command type 1 进入行军区时读取部队初始信息并调用 `s->j(...)`。
- 新协议分支：直接 `readShort()` 得到攻击间隔，作为 `s->j` 最后一个参数，随后 `s->f0()` 中转给 `s->h(...)` 写入 `C0`。
- 旧协议兼容分支：如果未直接携带该 short，则按兵数编码推断：
  - `10000 < count < 20000`：兵数减 `7000`，攻击间隔置 `4000ms`。
  - `count > 20000`：兵数减 `17000`，攻击间隔普通为 `7000ms`，名字以“孟俊才”开头时为 `5000ms`。

### 证据路径
- `s->Z(String)`：`0000b4-0000c2` 读取兵数/攻击间隔，`0000e2-000124` 旧协议兼容换算，`000128-000150` 调用 `s->j(...)`。
- `s->j(...)`：最后参数写入 `C1[S]` 命令缓冲。
- `s->f0()`：`00005e-0000b2` 取 `C1` 并调用 `s->h(...)`。
- `s->h(...)`：`0002b4-0002be` 写 `C0`。

### 当前结论更新
- 客户端回放中的“攻击间隔/C0”不是由兵种表本地公式实时计算；新协议里是服务端/指令流直接下发毫秒值。
- 旧协议有一个非常粗的兼容规则（4000/5000/7000ms），这不是完整攻速公式，只是历史包格式兼容。

## 6. 新增：战斗指令流 command type 1..11 结构

- 已对 `LscriptPages/game/s;->Z(String)` 做战斗/战报指令流结构化整理。
- 新增报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_deep/battle_command_structure_report.md`
- 结构化数据：
  - `battle_command_structure.csv`：11 类 command type 的读取结构、handler、状态缓冲、与公式关系。
  - `battle_command_baseio_reads.csv`：每类 command type 对应 BaseIO read 调用地址索引。
  - `battle_command_structure.json`：完整 JSON 汇总。

### 通用战斗指令格式

- `s->Z(String)` 入口先 `readShort(commandCount)`。
- 每条命令先读取：`readByte(commandType)` + `readInt(timeOffsetMs)`。
- 每条命令进入 `s.d1(type)`、`s.e1(handlerIndex)`、`s.f1(scheduledTimeMs)`，并按 `scheduledTimeMs / 1000` 分组写入 `data.g.Qc/Rc` 供回放调度。

### 已确认 command type

|type|语义|与公式关系|
|---:|---|---|
|1|进入行军区/创建战场部队|读取 `attackIntervalMs`，最终写入 `C0`；新协议为服务端/指令流直接下发。|
|2|加入布阵区/预备区候选|位置/状态指令，不含伤害公式。|
|3|加入到战斗区|读取 lane/col，进入坐标/坑位规则。|
|4|暂停行军区内行军|移动控制。|
|5|离开战斗|部队离场/撤退/死亡候选。|
|6|普通攻击指令|读取攻击后剩余值；客户端做 old-new 损兵显示/状态同步。|
|7|战斗结束|结束标记，胜负结果由指令流给出。|
|8|使行军区部队继续行走|移动控制。|
|9|移动到战斗区指定位置|读取 lane/col，进入坐标/坑位规则。|
|10|战场文本/提示|展示文本。|
|11|战法/技能攻击指令|读取 before/after；客户端显示损兵/效果，不反推基础伤害。|

### 结论强化

- 基础伤害公式仍未在客户端 `s->Z/f0/p0` 回放执行路径闭环。
- 普通攻击与战法攻击均是“服务端/战斗结果生成侧给出结果，客户端回放表现”。
- 攻速/蓄力中的 `C0` 上游已经确认：新协议 command type 1 直接携带毫秒值；旧协议才存在 4000/5000/7000ms 兼容推断。
- 坐标/前后左右属于客户端表现层，已可通过 command type 3/9 与 `s->B/I/C/J` 继续精修。
