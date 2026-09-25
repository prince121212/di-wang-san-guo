# reqFightingCity / 城池战斗入口协议字段报告

生成时间：2026-07-05T07:27:30

## 1. 结论摘要

- `reqFightingCity` 是城池/战斗目标地图刷新相关请求，发送入口为 `LscriptPages/game/s0;->Z()V`。
- 请求 opcode：`0x1012`，十进制 `4114`。
- 响应 opcode：`0x8012`，dispatcher 中以 signed short `-32750` 出现，由 `Lo/a;->A6` 分发到 `LscriptPages/game/s0;->S(String)`。
- 请求最小体在 APK 1.66 静态字节码中表现为：`writeByte(0)` 后直接发送。也就是说，当前版本更像“请求服务端刷新/下发当前战斗城市状态”，而不是客户端主动提交完整筛选条件。
- `s0.Z` 中存在一个“按屏幕视野筛选城市并循环写入 city_id/name/D1/E1”的备用/遗留结构，但在 `000da6` 被清零后，按当前反汇编路径不可达或至少不是默认实际请求体。
- `0x8012 -> s0.S(String)` 响应结构分两组：先返回坐标标记列表，更新 `s0.H`；再返回城市/战斗目标记录，按现有 `s0.r` 中的 ID 匹配并更新 `s0.r/s/t/u/v/w/x/y/z/A/B/C/D/E/F/G/I/J/L` 等缓存。

## 2. 请求格式

| 顺序 | 字段 | 类型 | 证据 | 含义 |
|---:|---|---|---|---|
| 1 | `visible_city_count` | `byte` | `s0.Z 000da8-000db4`，且 `000da6 const/4 v3,0` | 实际发送的数量；当前静态路径写入 0 |
| 2.1 | `city_id[i]` | `long` | `s0.Z 000dba-000dda` | count>0 时写入，来源 `s0.r[i]`；当前像备用 delta 格式 |
| 2.2 | `city_name_or_label[i]` | `UTF` | `s0.Z 000de0-000de8` | count>0 时写入，来源 `s0.z[i]` |
| 2.3 | `city_metric_D1[i]` | `int` | `s0.Z 000dee-000dfa` | count>0 时写入，来源 `s0.D[i][1]` |
| 2.4 | `city_metric_E1[i]` | `short` | `s0.Z 000e00-000e0c` | count>0 时写入，来源 `s0.E[i][1]` |
| send | `opcode` | `short` | `s0.Z 000e18-000e1c` | `0x1012 / 4114` |

关键边界：`s0.Z 000d0c-000d9c` 确实会计算屏幕范围内城市数量 `v3` 与布尔数组 `v2`，但 `000da6` 立刻执行 `const/4 v3,0`，因此后续 `if-lez v3` 循环默认不执行。相邻 `reqXunyouCity / 0x6444` 分支也有类似清零形态，说明这可能是老版本增量请求机制被禁用后的残留。

## 3. 响应格式：`0x8012 -> s0.S(String)`

### 3.1 坐标标记组

| 顺序 | 字段 | 类型 | 证据 | 含义 |
|---:|---|---|---|---|
| 1 | `marker_count` | `short` | `s0.S 000000-00002a` | 标记坐标数量；进入时按当前城市缓存长度重建 `s0.H` |
| 2.1 | `marker_x[i]` | `short` | `s0.S 000036-00007a` | 标记坐标 x |
| 2.2 | `marker_y[i]` | `short` | `s0.S 00003e-00007a` | 标记坐标 y；客户端匹配 `s0.s[index]` 后置 `s0.H[index]=true` |

### 3.2 城市/战斗目标更新组

| 顺序 | 字段 | 类型 | 写入缓存 | 证据 | 含义 |
|---:|---|---|---|---|---|
| 3 | `city_update_count` | `short` | loop count | `s0.S 00008c-000096` | 后续记录数量 |
| 4.1 | `city_id` | `long` | `s0.r[index]` | `s0.S 0000a0-0000a6 / 00021e-00022e` | 目标 ID；只匹配并更新已有 ID |
| 4.2 | `coord_x` | `short` | `s0.s[index][0]` | `s0.S 0000a8-0000b0 / 000232` | x 坐标 |
| 4.3 | `coord_y` | `short` | `s0.s[index][1]` | `s0.S 0000b4-0000bc / 000232` | y 坐标 |
| 4.4 | `packed_icon_or_type_bytes` | `byte[]` | `s0.t[index]` | `s0.S 0000c0-000100 / 00023a` | 压缩 byte 序列；首字节高 2 位决定数量，低 6 位为值 |
| 4.5 | `name` | `UTF` | `s0.u[index]` | `s0.S 000102-000108 / 000242` | 目标名称 |
| 4.6-4.9 | `status_byte_v/w/x/y` | `byte*4` | `s0.v/w/x/y` | `s0.S 00010a-000128 / 00024a-000262` | 四个状态/类型 byte，语义待 UI 反查 |
| 4.10 | `text_z` | `UTF` | `s0.z[index]` | `s0.S 00012a-000130 / 00026a` | 文本字段；非空时后跟 A byte |
| 4.11 | `optional_byte_A` | `byte?` | `s0.A[index]` | `s0.S 000136-00014c / 000272` | `text_z` 非空时读取，否则置 0 |
| 4.12 | `text_B` | `UTF` | `s0.B[index]` | `s0.S 00014e-000154 / 00027a` | 文本字段 |
| 4.13 | `text_C` | `UTF` | `s0.C[index]` | `s0.S 000156-00015c / 000282` | 文本字段 |
| 4.14-4.16 | `D[0..2]` | `int[3]` | `s0.D[index]` | `s0.S 00015e-000184 / 00028a` | 三个 int；`D0` 还会同步到 `data.b.n` |
| 4.17-4.18 | `E[0..1]` | `short[2]` | `s0.E[index]` | `s0.S 00018c-0001a8 / 000292` | 两个 short；`E0` 还会同步到 `data.b.q` |
| 4.19-4.20 | `F[0..1]` | `int[2]` | `s0.F[index]` | `s0.S 0001b0-0001c8 / 00029a` | 两个 int |
| 4.21-4.22 | `G[0..1]` | `int[2]` | `s0.G[index]` | `s0.S 0001cc-0001e4 / 0002a2` | 两个 int |
| 4.23-4.24 | `K_or_discarded[0..1]` | `int[2]` | `s0.K` in `flushCitys`; S 路径未明显写回 | `s0.S 0001e8-0001ee`; `s0.w 000236-00024e / 00059e-0005a2` | 与初始城市缓存结构对齐，增量路径可能只消费不更新 |
| 4.25 | `I` | `short` | `s0.I[index]` | `s0.S 0001f4-0001fa / 0002ae` | short 状态/数值字段 |
| 4.26 | `J` | `long` | `s0.J[index]` | `s0.S 0001fc-000202 / 0002b6` | long 状态/时间/归属类候选 |
| 4.27 | `L` | `byte` | `s0.L[index]` | `s0.S 000204-00020a / 0002be` | byte 状态字段 |

## 4. 与初始城市缓存 `flushCitys` 的关系

- `LscriptPages/game/s0;->w()V` 从本地 BaseIO 流名 `flushCitys` 读取完整城市缓存，并初始化/扩容 `s0.r..L`。
- `s0.w()` 的单条城市记录结构与 `s0.S(String)` 的更新记录几乎一致；差异是 `s0.w()` 会新增/扩容缓存并明确写入 `s0.K`，而 `s0.S()` 只遍历已有 `s0.r` 并按 ID 覆盖更新。
- 因此，对服务端重建来说，`0x8012` 更像“已有城市/战斗目标的状态刷新包”；完整首包/地图基础列表仍需继续追 `0x800D -> s0.b([B)` 与 `s0.g2 -> s0.w()` 的来源。

## 5. 服务端重建含义

1. 客户端当前可以接受 `reqFightingCity` 请求体只有一个 `count=0` 字节，因此服务端初版可先按该最小格式实现。
2. 返回 `0x8012` 时，需要保证客户端已经有对应 `city_id` 的基础缓存，否则 `s0.S()` 不会新增未知目标。
3. 如果后续需要模拟真实地图刷新，应先完成 `flushCitys` 初始缓存链路，再用 `0x8012` 做可见范围/状态增量更新。
4. 城市记录中大量字段仍需结合 UI 渲染函数或真实响应样本命名；当前已恢复二进制顺序，但业务语义置信度还不够高。

## 6. 产物

- 请求字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fighting_city_request_fields.csv`
- 响应字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fighting_city_response_fields.csv`
- JSON 汇总：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fighting_city_protocol_summary.json`
- 反汇编目录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_fighting_city`
