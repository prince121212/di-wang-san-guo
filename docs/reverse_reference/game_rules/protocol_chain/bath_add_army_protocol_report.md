# reqBathAddArmy / 批量补兵协议字段报告

生成时间：2026-07-05T07:14:27

## 1. 结论摘要

- `reqBathAddArmy` 实际语义从 UI 文案看是 **批量补兵**，不是客户端提交任意兵种/数量。
- 请求 opcode：`0x1229`，十进制 `4649`。
- 响应 opcode：`0x8229`，由 `Lo/a;->A6` dispatch 到 `LscriptPages/game/p;->M0(String)`。
- 请求体只写入：选中的将领/角色 ID 数量 + ID 列表。
- 响应成功后，服务端回传补兵后的状态，客户端更新：
  1. 将领/角色当前带兵状态或数量缓存；
  2. 封地/上下文中的空闲兵库存数组。
- 这说明补兵的目标兵种、补多少兵、是否够兵等关键规则应由服务端决定；客户端只是选择将领并请求“自动补兵”。

## 2. 请求格式

| 顺序 | 字段 | 类型 | 证据 | 含义 |
|---:|---|---|---|---|
| 1 | `role_count` | `byte` | `p.L0 00000a-00000e` | 选中的将领/角色数量，即 long[] 长度 |
| 2..N | `role_ids[i]` | `long[]` | `p.L0 000014-000026` | 逐个写入选中的将领/角色 ID |
| send | `opcode` | `short` | `p.L0 00002c-000030` | `0x1229 / 4649` |

请求方法：`LscriptPages/game/p;->L0([J)V`

调用来源：

- `LscriptPages/game/p;->s1()I 000c70`：生成 `z0` 选中数组后请求，UI 文案 `di_联网批量补兵`。
- `LscriptPages/game/p;->y1()I 0000f8`：`p.a()` 从 `p.Z[5]` 中提取选中 ID 后请求。
- `LscriptPages/game/p;->y1()I 00080e`：`setSoliderCmd/adjust` 流程中同样调用。

## 3. 选中 ID 来源

- `p.b()` 统计 `p.Z[0..4]` 中大于 0 的 ID 数量。
- `p.a()` 生成 long[]：遍历 `p.Z[0..4]`，只保留大于 0 的 ID。
- 因此单次批量补兵最多与 UI 的 5 个将领槽相关；另一路 `s1()` 从 `v0` 过滤生成 `z0`。

## 4. 响应格式

| 顺序 | 字段 | 类型 | 证据 | 含义 |
|---:|---|---|---|---|
| 1 | `status` | `byte` | `p.M0 000000-000006` | `0=成功`，非 0 则显示 message |
| 2 | `message` | `UTF` | `p.M0 000008-00000e / 0000c6` | 服务端提示文案 |
| 3 | `role_update_count` | `byte` | `p.M0 00001a-000020` | 将领/角色更新条目数 |
| 4.1 | `role_id_or_key` | `long` | `p.M0 00002c-00003c` | 经 `Lo/a.q1(J)` 映射为本地实体 ID |
| 4.2 | `army_type_or_status` | `byte` | `p.M0 000044-00004c` | 映射成功后写入 `Lo/a.Pm` |
| 4.3 | `army_count_or_value` | `int` | `p.M0 00004c-000066` | 映射成功后写入 `Lo/a.Qm` |
| 5 | `fief_or_context_id` | `long` | `p.M0 000072-000080` | 经 `Lo/a.p3(J)` 映射为库存数组索引，疑似封地 ID |
| 6 | `soldier_type_count` | `byte` | `p.M0 000082-00008a` | 空闲兵/库存兵种数量 |
| 7.1 | `soldier_type[i]` | `byte[]` | `p.M0 000096-00009e` | 保存到 `Lo/a.Kv[index]` |
| 7.2 | `soldier_amount[i]` | `int[]` | `p.M0 0000a2-0000aa` | 保存到 `Lo/a.Lv[index]` |

## 5. 服务端重建含义

重建服务端时，`reqBathAddArmy` 可以按以下逻辑实现：

1. 读取客户端提交的将领 ID 列表。
2. 对每个将领，根据其所在封地、当前带兵、可带兵上限、空闲兵库存，计算补兵结果。
3. 返回每个将领的新带兵状态/数量。
4. 返回封地空闲兵库存数组，供客户端同步显示。

该接口不应信任客户端指定的补兵数量，因为客户端请求体里根本没有数量字段。

## 6. 产物

- 请求字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/bath_add_army_request_fields.csv`
- 响应字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/bath_add_army_response_fields.csv`
- JSON 汇总：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/bath_add_army_protocol_summary.json`
- 反汇编目录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_bath_add_army`
