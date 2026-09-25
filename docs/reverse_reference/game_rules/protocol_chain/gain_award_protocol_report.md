# reqGainAward / 奖励领取协议字段报告

生成时间：2026-07-05T07:36:33

## 1. 结论摘要

- `reqGainAward` 是通用奖励领取请求，发送入口为 `LscriptPages/game/m0;->t(long,String)`。
- 请求 opcode：`0x1134`，十进制 `4404`。
- 响应 opcode：`0x8134`，dispatcher 中以 signed short `-32460` 出现，由 `Lo/a;->A6` 分发到 `LscriptPages/game/m0;->u(String)`。
- 请求体只包含奖励 ID、字符串存在标志、可选字符串上下文；客户端不提交奖励内容、资源数量或物品数量。
- 响应体先返回 `status`，随后调用 `m0.n(String)` 同步 4 类奖励列表；成功时再同步玩家/资源 long 字段和 `Lo/a.V5` 额外状态块，最后读取服务端提示文本。

## 2. 请求格式

| 顺序 | 字段 | 类型 | 证据 | 含义 |
|---:|---|---|---|---|
| 1 | `award_id` | `long` | `m0.t 00000a`; `000010 sput m0.C0` | 要领取的奖励/活动奖励 ID；保存到 `m0.C0` 用于响应后 UI 分支 |
| 2 | `name_selector` | `byte` | `m0.t 000014-000022` | 字符串参数非空写 1，否则写 0 |
| 3 | `award_name_or_context` | `UTF?` | `m0.t 000028-00002c` | 仅字符串参数非空时写入 |
| send | `opcode` | `short` | `m0.t 000032-000036` | `0x1134 / 4404` |

调用点覆盖多个奖励入口，包括 `Lo/a.e8`、`Lo/a.x8`、`game/i0.A`、`m0.B`、`m0.z`、`q0.V1/Y1/f2/n2`、`gameHD/a.j` 等，说明这是通用领奖接口。

## 3. 响应格式：`0x8134 -> m0.u(String)`

### 3.1 顶层字段

| 顺序 | 字段 | 类型 | 证据 | 含义 |
|---:|---|---|---|---|
| 1 | `status` | `byte` | `m0.u 000006-00000c` | `0=成功`，非 0=失败/错误 |
| 2 | `award_list_block` | complex | `m0.u 00000e -> m0.n(String)` | 4 类奖励列表同步块；成功失败都会先读取/消费 |
| 3 | `success_sync_block` | complex? | `m0.u 000020-00005e` | 仅 `status==0` 读取，包含玩家/资源数值与 `Lo/a.V5` 额外同步块 |
| 4 | `message` | `UTF` | `m0.u 0000d4-0000ec` | 服务端提示文本；为空则客户端显示“失败” |

### 3.2 `m0.n(String)` 奖励列表同步块

`m0.n` 固定处理 4 个奖励分类。每个分类先读两个 byte 计数，然后读两组记录：

| 字段 | 类型 | 证据 | 含义 |
|---|---|---|---|
| `available_count` | `byte` | `m0.n 0000c8-0000d0` | 第一组记录数，客户端将其标记为 `p0=1` 并累加 `w0` |
| `received_count` | `byte` | `m0.n 0000d0-0000d6` | 第二组记录数 |
| `available_record.id` | `long` | `m0.n 000166-000176` | 第一组奖励记录 ID |
| `available_record.name` | `UTF` | `m0.n 00017a-00018a` | 第一组奖励记录名称 |
| `available_record.flag` | `boolean` | `m0.n 00018e-00019e` | 第一组布尔标记 |
| `received_record.id` | `long` | `m0.n 0001c4-0001d8` | 第二组奖励记录 ID |
| `received_record.name` | `UTF` | `m0.n 0001dc-0001ec` | 第二组奖励记录名称 |
| `received_record.flag` | `boolean` | `m0.n 0001f0-000200` | 第二组布尔标记 |
| `list_trailer_or_version` | `short` | `m0.n 0002a6` | 4 类处理完后读取的 short，客户端当前不直接使用 |

`m0.n` 会写入/维护：`m0.m0/n0/o0/p0/q0/r0/s0/t0/u0/v0/w0`，并在当前页面状态为 `80` 时同步给 `q0.S7..Z7`。

### 3.3 成功同步块

仅当 `status == 0` 时读取：

| 顺序 | 字段 | 类型 | 证据 | 含义 |
|---:|---|---|---|---|
| 3.1 | `player_attr_byte` | `byte` | `m0.u 000020-000028` | 调用 `data.i.C(int)` 更新玩家/角色属性 |
| 3.2 | `player_i` | `long` | `m0.u 00002e-000036` | 写入 `data.i.i` |
| 3.3 | `player_d` | `long` | `m0.u 00003a-000042` | 写入 `data.i.d` |
| 3.4 | `player_e` | `long` | `m0.u 000046-00004e` | 写入 `data.i.e` |
| 3.5 | `global_H` | `long` | `m0.u 000052-00005a` | 写入 `data.g.H` |
| 3.6 | `extra_sync_block` | nested | `m0.u 00005e` | 调用 `Lo/a.V5(String)` 读取额外资源/背包/状态同步块 |

## 4. 服务端重建含义

1. 服务端应以 `award_id` 为唯一核心领奖目标，结合可选字符串上下文判断具体活动/奖励来源。
2. 领取是否成功、奖励内容、资源/物品到账都由服务端决定；客户端不会提交奖励明细。
3. 返回 `0x8134` 时，即便失败也应保持 `m0.n` 奖励列表同步块格式，否则客户端读流会错位。
4. 成功响应应同步玩家资源/状态字段，并通过 `Lo/a.V5` 或其他已知同步块更新背包/资源，最后返回提示文本。
5. 失败响应可通过非 0 `status` + `message UTF` 告知原因。

## 5. 产物

- 请求字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/gain_award_request_fields.csv`
- 响应字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/gain_award_response_fields.csv`
- JSON 汇总：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/gain_award_protocol_summary.json`
- 反汇编目录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_gain_award`
