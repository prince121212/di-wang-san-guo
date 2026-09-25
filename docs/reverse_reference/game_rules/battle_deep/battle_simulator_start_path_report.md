# 战斗模拟器开始战斗路径 / ReqChallengeTaskAward 反查报告

生成时间：2026-07-05T06:59:41

## 1. 结论摘要

- `KING_BATTLE_SIMULATOR3.0` 的保存槽已经确认是本地 RMS 阵容存档；继续追“开始战斗”后，确认它**仍不是本地基础伤害公式入口**。
- 用户点击开始后，客户端调用 `data.g->Q2()`，将当前两方配置 `c6..n6` 序列化到名为 `ReqChallengeTaskAward` 的请求体。
- 请求发送点为 `LscriptPages/game/g;->y(String,String,S)`，opcode 十进制 `25613`，十六进制 `0x640D`。
- 响应处理函数 `data.g->B4(String)` 只读取：`status/readByte`、`message/readUTF`，成功时再读取 `fightID/readLong`。
- `data.g->L4()` 等待响应，20 秒未回包显示 `di_联网超时`；若 `fightID > 0`，调用 `LscriptPages/game/c;->r(fightID, 1)` 进入战斗/战报回放。

## 2. 请求体字段顺序（Q2）

| 顺序 | 写入字段 | 写入类型 | 证据 | 含义候选 |
|---:|---|---|---|---|
| 1 | `array_length(h6)` | int | `Q2 000062-000064` | 第一方附加数组长度，可能为战法/称号/特殊配置 |
| 2 | `h6[i]` | int[] | `Q2 00006c-000080` | 第一方附加配置 |
| 3 | `c6` | int | `Q2 000082` | 第一方标量配置 |
| 4 | `array_length(e6)` | int | `Q2 000088-00008a` | 第一方单位槽数量 |
| 5 | `d6[i]` | int | `Q2 000098-00009c` | 第一方槽字段 A，疑似兵种/单位类型 |
| 6 | `e6[i]` | short | `Q2 0000a2-0000a8` | 第一方槽字段 B，疑似兵种/单位编号 |
| 7 | `f6[i]` | int | `Q2 0000ae-0000b2` | 第一方槽字段 C，疑似数量 |
| 8 | `g6[i]` | short | `Q2 0000b8-0000be` | 第一方槽字段 D，疑似战法/器械/附加 |
| 9 | `array_length(n6)` | int | `Q2 0000ca-0000cc` | 第二方附加数组长度 |
| 10 | `n6[i]` | int[] | `Q2 0000d2-0000e8` | 第二方附加配置 |
| 11 | `i6` | int | `Q2 0000ea` | 第二方标量配置 |
| 12 | `array_length(k6)` | int | `Q2 0000f0-0000f2` | 第二方单位槽数量 |
| 13 | `j6[i]` | int | `Q2 0000fe-000102` | 第二方槽字段 A |
| 14 | `k6[i]` | short | `Q2 000108-00010e` | 第二方槽字段 B |
| 15 | `l6[i]` | int | `Q2 000114-000118` | 第二方槽字段 C，疑似数量 |
| 16 | `m6[i]` | short | `Q2 00011e-000124` | 第二方槽字段 D |

## 3. 响应结构（B4）

| 字段 | 类型 | 证据 | 含义 |
|---|---|---|---|
| `c7` | 本地时间 | `B4 000000-000008` | 响应到达时间，用于 L4 判断已回包 |
| `d7` | byte | `B4 00000c-000014` | 状态码/成功标志；`d7 != 0` 时继续读取 fightID |
| `e7` | UTF string | `B4 000018-000020` | 服务端返回提示文案 |
| `f7` | long | `B4 00002c-000034` | fightID；若为 -1，客户端提示“载入战斗失败，fightID：-1” |

## 4. 对战斗公式恢复的影响

- 这条路径进一步证明：客户端的战斗模拟器不是完整本地结算器，而是**本地配置 UI + 服务端战斗生成请求**。
- 客户端可恢复的是：两方阵容/兵种/数量/战法/称号等输入格式，以及战斗回放指令流输出格式。
- 缺失的是：服务端如何从这些输入计算胜负、伤兵、战法效果、奖励与 fightID 对应战报。
- 因此服务端重建阶段，战斗公式应作为“拟合/重写模块”：用 APK 中的兵种、技能、科技、装备、称号表作为参数，用真实战报样本校准。

## 5. 关键证据文件

- 反汇编：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_dex/method_disasm_extra/scriptPages_data_g__Q2__0x281bb8.smali.txt`
- 反汇编：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_dex/method_disasm_extra/scriptPages_data_g__B4__0x288a80.smali.txt`
- 反汇编：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_dex/method_disasm_extra/scriptPages_data_g__L4__0x267264.smali.txt`
- 结构化表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_deep/battle_simulator_protocol_fields.csv`
- JSON 汇总：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_deep/battle_simulator_start_path_summary.json`
