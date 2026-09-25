# 出征/战斗结算协议第一版

- 日期：2026-07-05
- 位置：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain`
- 证据目录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_expedition`

## 1. 结论摘要

本轮已把出征链路拆成五个确定协议面：

| 协议名 | opcode | 入口方法 | 用途 |
|---|---:|---|---|
| `expeditionPreTipInfo` | `0x1520 / 5408` | `LscriptPages/game/p;->O(I,[J,J)V` | 正式出征前提示/预校验 |
| `expedition` | `0x1522 / 5410` | `LscriptPages/game/p;->N(I,[J,J,B,B,B,J)V` | 正式出征 |
| `reqThiefList` | `0x1540 / 5440` | `LscriptPages/game/p;->k1(I,I)V` | 按坐标/区域请求山贼列表 |
| `reqCheckMsg` | `0x1114 / 4372` | `LscriptPages/game/h0;->Z(J)V` | 战报/消息详情展示 |
| `REQ_FIGHTINFO` | `0x1702 / 5890` 或 `0x1707 / 5895` | `LscriptPages/game/s;->c0(J,I)V` | 战场初始化/回放指令流 |

核心结论：**出征成功不是只回一个 ID**。客户端在 `p.Q(String)` 读到 `result_code == 0` 后，会读取 `fight_or_expedition_id/readLong`，然后立即调用 `scriptPages/data/a.B(stream)` 消费完整状态快照。服务端重建时必须按这个复合读流返回地图/出征/封地状态，否则客户端后续字段会错位。

## 2. 正式出征请求 `0x1522`

证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_expedition/scriptPages_game_p__N__0x307b1c.smali.txt`

请求体顺序：

1. `expedition_type/writeByte`
2. `general_count/writeByte`
3. `general_id/writeLong * general_count`
4. `target_id/writeLong`
5. `related_long/writeLong`
6. `attack_strategy/writeByte`
7. `attack_mode/writeByte`
8. `unknown_flag/writeByte`

客户端随后通过 `Lo/a.d0(5410, body)` 发送。

## 3. 出征预提示 `0x1520`

证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_expedition/scriptPages_game_p__O__0x307b98.smali.txt`

请求体顺序：

1. `expedition_type/writeByte`
2. `general_count/writeByte`
3. `general_id/writeLong * general_count`
4. `target_id/writeLong`

同时客户端缓存：`p.k0=general_id[]`、`p.l0=expedition_type`、`p.m0=target_id`。

## 4. 出征响应 `p.Q(String)`

证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_expedition/scriptPages_game_p__Q__0x307cc8.smali.txt`

响应读流：

1. `result_code/readByte`
2. `message/readUTF`
3. 若 `result_code == 0`：
   - `fight_or_expedition_id/readLong -> p.n0`
   - `scriptPages/data/a.B(stream)`：继续读取完整状态快照

错误码分支：`-38`、`-40`、`-35`、`-32` 有专门处理，其他走 `p.M(result_code, message)`。

## 5. 状态快照 `scriptPages/data/a.B(String)`

证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_expedition/scriptPages_data_a__B__0x25fab8.smali.txt`

`a.B` 是当前出征链路最重要的服务端重建约束。它大体包含：

### 5.1 坐标/地图短整型矩阵

- `coord_pair_count/readShort`
- repeat：`readByte -> short`、`readShort`
- 写入 `scriptPages/data/a.c [[S]`

### 5.2 分段快照 `section_count/readByte`

随后循环读取 tag 分段：

#### tag=1：己方/拥有的出征队列候选

写入字段组：`g/h/i/j/k/l/m/n/o/p/q/s/t`。

单条记录近似读流：

```text
expedition_id/readLong
member_count/readByte
repeat member_count:
  member_or_general_id/readLong
  member_type/readByte
related_or_target_id/readLong
expedition_kind_or_status/readByte
target_name/readUTF
coord_x/readShort
coord_y/readShort
packed_byte/readByte  # k = packed >> 1; q = packed & 1
remain_seconds/readInt -> o = currentTime + remain_seconds
extra_long/readLong
```

#### tag=2：地图目标/点位列表候选

写入 `d[1] / e[1] / f[0]`，并调用 `C(0, stream)` 继续读取一类移动/队列状态。包含名称、目标 ID、短整型数组、坐标/尺寸字段。

#### tag=3：敌方/其他出征队列候选

写入字段组：`D/E/F/G/H/I/J/K/L`。结构与 tag=1 类似，但字段略少；结束/基准时间为 `K = currentTime - readLong`。

### 5.3 快照尾部

- `a(stream)`：`readShort; repeat(readLong, readByte)`，按己方出征 ID 更新 `r[]` 状态位。
- `b(stream)`：`readShort; repeat(readLong, readByte)`，按另一类出征 ID 更新 `L[]` 状态位。
- `Lo/a.f6(0, stream)`、`Lo/a.f6(1, stream)`、`Lo/a.S5(stream)`：继续同步封地/资源/全局状态块。

## 6. 出征类型与状态文案

证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_expedition/scriptPages_data_a__clinit__0x25f81c.smali.txt`

`scriptPages/data/a.<clinit>` 初始化 17 个行动类型：

| index | 文案 |
|---:|---|
|0|派遣|
|1|掠夺|
|2|驻守|
|3|阻击|
|4|攻占|
|5|消灭|
|6|返回|
|7|侦查|
|8|闯关|
|9|抢城|
|10|城主竞选|
|11|出征副本|
|12|竞技场|
|13|押镖|
|14|寻宝|
|15|攻占|
|16|攻占|

出征状态文案 5 个：`行军中`、`战斗中`、`返回途中`、`等待中`、`已返回`。

## 7. 山贼列表 `reqThiefList 0x1540`

证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_expedition/scriptPages_game_p__k1__0x30e790.smali.txt`

请求体：

1. `x/writeShort`
2. `y/writeShort`

结合前序抓包，响应不是一次给全图所有山贼，而是按当前坐标/视野/区域返回一批山贼。要拿全图 7 级山贼，需要网格化枚举地图区域并合并去重。

## 8. 战报详情 `reqCheckMsg 0x1114`

证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_expedition/scriptPages_game_h0__Z__0x3b057c.smali.txt`、`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_expedition/scriptPages_game_h0__a0__0x3b05ac.smali.txt`

请求体：`message_or_report_id/writeLong`。

动态抓包已确认响应包含：山贼等级坐标、胜负文案、战利品、铜钱/粮食/声望、损失兵力等文本。该接口更像只读详情接口；前序重放测试显示它不会重复发放资源。

## 9. 战斗回放/指令流 `REQ_FIGHTINFO`

证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_expedition/scriptPages_game_s__c0__0x33a958.smali.txt`、`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_expedition/scriptPages_game_s__Y__0x3380fc.smali.txt`、`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_expedition/scriptPages_game_s__Z__0x338bd8.smali.txt`

请求体：

1. `fight_info_type/writeByte`
2. `fight_id/writeLong`
3. 若 `fight_info_type <= 3`：
   - `s.o1/writeLong`
   - `300000/writeLong`

opcode 选择：

- `fight_info_type <= 3`：`0x1702 / 5890`
- `fight_info_type > 3`：`0x1707 / 5895`

`scriptPages/game/s.Z` 中有明确指令流文案：`进入到行军区`、`加入到战斗区`、`暂停行军区内的行军`、`离开战斗`、`攻击指令`、`战斗结束`、`移动到战斗区指定位置`。这进一步支持：客户端主要是按服务端下发的战斗指令回放，而不是本地权威结算。

## 10. 对重建服务端的影响

1. 出征创建必须服务端权威校验：武将归属、状态、兵力、目标合法性、距离/行军时间、行动类型限制。
2. `0x1522` 成功响应必须构造：`0 + message + expedition_id + a.B 状态快照`。
3. 山贼奖励、战报、资源到账应在服务端结算时完成；`0x1114` 只负责展示详情。
4. 战斗过程若暂不实现完整模拟，可先生成服务端权威结算结果和最小可播放/可跳过指令流；但完整体验需要补 `s.Y/s.Z` 的战场初始化与指令格式。
5. 目前仍缺：基础伤害/伤兵/胜负/奖励掉落公式，`attack_strategy/attack_mode` 的 UI 语义，`a.B tag=1/2/3` 的动态样本字段命名。

## 11. 结构化输出

- 请求字段：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/expedition_request_fields.csv`
- 响应字段：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/expedition_response_fields.csv`
- JSON 摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/expedition_protocol_summary.json`
- 反汇编证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_expedition`
