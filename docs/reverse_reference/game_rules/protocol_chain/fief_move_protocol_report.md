# fiefMove / 迁封协议字段报告

生成时间：2026-07-05T07:18:38

## 1. 结论摘要

- `fiefMove` 是封地迁移/迁封请求。
- 请求 opcode：`0x1212`，十进制 `4626`。
- 响应 opcode：`0x8212`，由 `Lo/a;->A6` dispatch 到 `LscriptPages/game/q;->W(String)`。
- 请求体包含：源封地 ID、目标城池/槽位 short、目标标识方式，以及目标 ID 或目标名称二选一。
- 成功响应会同步封地新位置，并触发 `reqRoleInfo` 与 UI/列表刷新。
- 错误码 `-1..-9` 已恢复，覆盖“没有指定、迁封无效、没有空封、无可迁城、原封地城池、基地迁封、不属于您”等迁封规则。

## 2. 请求格式

| 顺序 | 字段 | 类型 | 证据 | 含义 |
|---:|---|---|---|---|
| 1 | `source_fief_id` | `long` | `q.T 00000a` | 待迁移封地 ID，调用点使用 `q.o` |
| 2 | `target_city_or_slot` | `short` | `q.T 000010-000012` | 目标城池/目标槽位；调用点来自 `o3[l3]` |
| 3 | `target_selector` | `byte` | `q.T 000018-000020` | `0=后续写 long`，非 0=后续写 UTF；同时写入 `q.e4` |
| 4a | `target_id` | `long` | `q.T 000024-000028` | selector==0 时写入；直接迁封分支传 `-1` |
| 4b | `target_name` | `UTF` | `q.T 00002e-000030` | selector!=0 时写入；调用点传 `W3[I2]` 或 `P3` |
| send | `opcode` | `short` | `q.T 000036-00003a` | `0x1212 / 4626` |

请求方法：`LscriptPages/game/q;->T(J I I J String)V`

调用来源：

- `q.H1()I 000560`：UI 文案 `di_联网封地迁封`，`selector=0,target_id=-1`。
- `q.H1()I 000b20`：`selector=1,target_name=W3[I2]`。
- `q.H1()I 000b4a`：`selector=1,target_name=P3`。

## 3. 响应格式

| 顺序 | 字段 | 类型 | 证据 | 含义 |
|---:|---|---|---|---|
| 1 | `status` | `byte` | `q.W 000000-000006` | `0=成功`，负数为错误码 |
| 2 | `moved_fief_id` | `long` | `q.W 00000c-000014` | 成功时返回迁移的封地 ID |
| 3 | `new_city_or_position` | `long` | `q.W 000018-00003e` | 成功时返回新城池/位置；低 16 位写入 `Lo/a.sv[p3(fief)]` |
| 4 | `extra_block_flag` | `byte` | `q.W 000042-00004e` | 非 0 时调用 `Lo/a.V5` 读取额外同步块 |
| 5 | `refresh_flag` | `boolean` | `q.W 000054-000060` | true 时调用 `data.b.L` 继续刷新数据 |

成功后：

- `q.W 000184-000190`：调用 `reqRoleInfo(-1, data.i.b)` 刷新角色详情。
- `q.W 000196-00019a`：调用 `q.g1(0, moved_fief_id)` 刷新迁封相关 UI/列表。

## 4. 错误码映射

| status | 含义 | 证据 |
|---:|---|---|
| -1 | 没有指定 | `q.W 000070-000084` |
| -2 | 迁封无效 | `q.W 00008e-0000a4` |
| -3 | 没有空封 | `q.W 0000ae-0000c4` |
| -4 | 无可迁城 | `q.W 0000ce-0000e4` |
| -5 | 原封地城池 | `q.W 0000ec-000102` |
| -6 | 其他错误 | `q.W 00010a-000120` |
| -7 | 基地迁封 | `q.W 000128-00013e` |
| -8 | 没有城池 | `q.W 000146-00015c` |
| -9 | 不属于您 | `q.W 000164-00017c` |

## 5. 服务端重建含义

重建服务端时，`fiefMove` 至少需要校验：

1. 源封地是否属于当前玩家。
2. 源封地是否允许迁封，基地封地应禁止迁封。
3. 目标城池/槽位是否有效。
4. 玩家是否有空封资格/目标城池是否可开封。
5. 成功后更新封地所在城池/位置，并返回新的封地位置同步块。

该接口是封地系统核心状态变更接口，必须以服务端为准。

## 6. 产物

- 请求字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fief_move_request_fields.csv`
- 响应字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fief_move_response_fields.csv`
- JSON 汇总：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fief_move_protocol_summary.json`
- 反汇编目录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_fief_move`
