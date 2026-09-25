# reqRoleInfo / reqRoleFiefList 字段级协议初步报告

生成时间：2026-07-05T07:09:42

## 1. 结论摘要

- `reqRoleInfo` 已恢复请求体：可按 **角色ID** 或 **角色名** 查询角色/君主详情；请求 opcode 为 `0x1120`。
- `reqRoleInfo` 响应由 dispatcher `Lo/a;->A6` 在 `0x8120` 分支处理：先读一个状态 byte，成功时进入 `LscriptPages/game/w;->e0(String)` 读取角色详情字段。
- `reqRoleFiefList` 已恢复请求体：位于 `LscriptPages/game/p;->g0(I,I)` 的 `type=4` 分支；请求 opcode 为 `0x1310`。
- `reqRoleFiefList` 的列表响应当前关联到 `0x8510 -> p.a1(String) -> p.T(String)` 路径；`p.T` 会读取三大组列表数据，结构很大，疑似用于目标角色/势力相关的封地、城池/资源点、驻军或附属明细。
- 这两个协议是服务端重建“角色详情 → 封地/目标列表”闭环的第一批字段级成果。

## 2. reqRoleInfo 请求格式

| 顺序 | 字段 | 类型 | 证据 | 含义 |
|---:|---|---|---|---|
| 1 | `target_selector` | `byte` | `w.d0 000012-000026` | `1=按名称查询`，`0=按 roleId 查询` |
| 2a | `roleName` | `UTF` | `w.d0 000016-00001e` | 当 String 参数非空时写入 |
| 2b | `roleId` | `long` | `w.d0 000026-00002c` | 当 String 参数为空时写入 |
| send | `opcode` | `short` | `w.d0 000032-000036` | `0x1120 / 4384` |

## 3. reqRoleInfo 响应格式

- dispatcher 证据：`Lo/a;->A6` 中 `const/16 -32480`，即 `0x8120`。
- `A6` 对该分支先 `readByte(status)`：`status==0` 进入 `w.e0`，非 0 进入 `data.i.x` 错误/通用处理。
- `w.e0` 成功体已恢复 25 个读取字段，详见：
  `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/role_fief_response_fields.csv`

核心字段包括：`roleId/readLong`、`roleName/readUTF`、多个 `UTF` 文本字段、多个 byte/short/int/long 状态或数值字段。部分字段语义仍需结合 UI 文案或抓包样本命名。

## 4. reqRoleFiefList 请求格式

`LscriptPages/game/p;->g0(I,I)` 是一个列表请求选择器，其中 `type=4` 才是 `reqRoleFiefList`：

| 顺序 | 字段 | 类型 | 证据 | 含义 |
|---:|---|---|---|---|
| 1 | `mode_or_type` | `byte=1` | `p.g0 0000b6-0000c0` | 固定写 1，疑似查询类型 |
| 2 | `target_selector` | `byte` | `p.g0 0000c6-0000d8` | `1=按字符串查询`，`0=按 long 查询` |
| 3a | `targetName` | `UTF` | `p.g0 0000ca-0000d0` | `X6[u1]` 非空时写入 |
| 3b | `targetId` | `long` | `p.g0 0000d8-0000de` | 字符串为空时写入；当前分支常量为 0 |
| send | `opcode` | `short` | `p.g0 0000e4-0000e8` | `0x1310 / 4880` |

## 5. reqRoleFiefList / p.T 响应结构

`p.T(String)` 会按三大组读取：

1. **Group A**：先读 `count_A/readByte`，每条约包含 `id/name/short坐标或等级/多个 byte 状态/多个 int 数值/文本/子 long[3]`。
2. **Group B**：先读 `count_B/readByte`，每条约包含 `id/name/文本/状态 byte/两个 short`，并存在 `t4>=100` 的特殊编码拆分。
3. **Group C**：先读 `count_C/readByte`，每条含基础字段、可选扩展字段，以及两类嵌套子列表：`(byte,byte)*N` 与 `(UTF,short,byte,byte,byte,int)*N`。

完整字段顺序见：
`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/role_fief_response_fields.csv`

## 6. 对服务端重建的影响

- `reqRoleInfo` 可作为角色/君主详情 handler，实现成本较低：按 selector 返回目标角色基础详情即可让多个 UI 能展示基础信息。
- `reqRoleFiefList` 数据量大，是“查看目标封地/城池/资源点/驻军明细”的核心接口之一；重建初期可先返回空列表或最小字段，再逐步补齐三大组。
- 这两个接口都偏只读查询，适合优先实现为服务端重建的稳定基础。

## 7. 产物

- 请求字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/role_fief_request_fields.csv`
- 响应字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/role_fief_response_fields.csv`
- JSON 汇总：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/role_fief_protocol_summary.json`
- 反汇编目录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_role_fief`
