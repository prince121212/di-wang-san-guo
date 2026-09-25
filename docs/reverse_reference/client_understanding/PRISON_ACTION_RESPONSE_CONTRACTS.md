# 监狱/俘虏动作响应合同（第一版）

生成时间：2026-07-05  
目标：深拆 `0x8233/0x8234/0x8236/0x8238/0x823b`，确认响应读流、状态同步块、错误码，以及请求中 `z.D` 的业务名。

## 1. 产物

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/PRISON_ACTION_RESPONSE_CONTRACTS.md`
- 响应 schema CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_action_response_schema.csv`
- 结果码 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_action_result_codes.csv`
- host id 语义 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_action_host_id_semantics.csv`
- 抓包 opcode 检查 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_action_capture_opcode_check.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_action_response_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_action_response_summary.json`

## 2. 响应读流与同步合同

| 响应 | 请求 | Handler | 语义 | 读流 schema | 同步合同 | UI/副作用 | 置信度 |
|---|---|---|---|---|---|---|---|
| `0x8233` | `0x1233` | `LscriptPages/game/q;->o1(Ljava/lang/String;)V` | prisoner control cost preflight | `readByte(ctrl_type); readByte(not_found_flag); if flag!=1 and ctrl_type in {0,1}: readLong(copper_cost); readLong(gold_cost)` | `none` | ctrl_type=0 弹“劝降俘虏”消耗确认并置 z.p0=4；ctrl_type=1 弹“营救被俘”消耗确认并置 z.p0=2；not_found_flag==1 直接提示“俘虏不在”。 | high |
| `0x8234` | `0x1234` | `LscriptPages/game/q;->b1(Ljava/lang/String;)V` | prisoner persuade/lure result | `readByte(result_code); readUTF(server_message)` | `if result_code in {0,1}: f6(0)+f6(1); else: f6(1); no V5/S5` | 按 result_code/server_message 显示劝降结果；成功类会刷新我方将领表与俘虏表，并记录“获得名将”事件。 | high |
| `0x8236` | `0x1236` | `LscriptPages/game/q;->c1(Ljava/lang/String;)V` | release prisoner result | `readByte(result_code)` | `if result_code==0: f6(1); no V5/S5` | result_code==0 提示释放成功，否则提示释放失败；重置弹窗/状态并调用 q.R0 刷新。 | high |
| `0x8238` | `0x1238` | `LscriptPages/game/q;->d1(Ljava/lang/String;)V` | rescue captured self general result | `readByte(result_code); readBoolean(full_sync_flag)` | `if full_sync_flag: f6(0); else: a6(0); no V5/S5` | 成功类提示/记录营救成功；-20 显示“已被劝降”；其他失败显示“营救失败”；随后刷新监狱页/HD 页。 | high |
| `0x823b` | `0x123b` | `LscriptPages/game/q;->a1(Ljava/lang/String;)V` | give up captured self general result | `readByte(result_code)` | `if result_code==0: f6(0); no V5/S5` | result_code==0 提示放弃成功，否则提示放弃失败；重置弹窗/监狱页并刷新 HD 页。 | high |

关键结论：这组监狱动作响应**不追加 `Lo/a.V5` 或 `Lo/a.S5`**。客户端只根据动作类型刷新 type0/type1 对象表：

- `0x8233` 只是前置消耗确认，不刷新对象表。
- `0x8234` 劝降结果会刷新 type1；结果码 `0/1` 时还刷新 type0。
- `0x8236` 释放成功刷新 type1。
- `0x8238` 营救响应按 boolean 选择 `f6(0)` 或 `a6(0)`。
- `0x823b` 放弃被俘将领成功刷新 type0。

## 3. 错误码/结果码

| 响应 | code | 含义 | 证据 | 置信度 |
|---|---|---|---|---|
| `0x8233` | `ctrl_type=0` | 劝降前置消耗提示 | q.o1 读取两项 long 成本后用 type1/z.n0 取将领名，弹 `re_提示劝降俘虏`，z.p0=4。 | high |
| `0x8233` | `ctrl_type=1` | 营救前置消耗提示 | q.o1 读取两项 long 成本后用 type0/z.n0 取将领名，弹 `re_提示营救被俘`，z.p0=2。 | high |
| `0x8233` | `not_found_flag=1` | 俘虏不在 | q.o1 第二个 byte 为 1 时直接显示 `di_提示俘虏不在`。 | high |
| `0x8234` | `0 or 1` | 劝降结果成功类/状态变更类，需同时刷新 type0 与 type1 对象表 | q.b1 对 0/1 调用 `Lo/a.f6(0)` 与 `Lo/a.f6(1)`，并记录“获得名将”。是否 0/1 细分仍需真实样本。 | medium-high |
| `0x8234` | `-1` | 俘虏不在 | `di_提示俘虏不在`。 | high |
| `0x8234` | `-2` | 武将上限 | `di_提示武将上限`。 | high |
| `0x8234` | `-3` | 劝降频率过快 | `di_提示劝降频率过快`。 | high |
| `0x8234` | `-4` | 营救频率过快 | `di_提示营救频率过快`。 | high |
| `0x8234` | `-5` | 铜钱不足 | `di_提示铜钱不足`。 | high |
| `0x8234` | `-6` | 黄金不足 | `di_黄金不足`。 | high |
| `0x8234` | `-7` | 劝降失败，将领没逃 | `di_提示劝降失败将领没逃`。 | high |
| `0x8234` | `-8` | 劝降失败，将领逃跑 | `di_提示劝降失败将领逃跑`。 | high |
| `0x8234` | `-9` | 营救失败，没有突围 | `di_提示营救失败没有突围`。 | high |
| `0x8234` | `-10` | 营救失败，突围失败 | `di_提示营救失败突围失败`。 | high |
| `0x8234` | `-11` | 劝降超时 | `di_提示劝降超时`。 | high |
| `0x8234` | `-20` | 已被劝降 | `di_提示已被劝降`。 | high |
| `0x8236` | `0` | 释放成功 | q.c1 成功分支 `f6(1)` 并显示 `di_提示释放成功`。 | high |
| `0x8236` | `non-zero` | 释放失败 | q.c1 非 0 显示 `di_提示释放失败`。 | high |
| `0x8238` | `0/1` | 营救成功类/状态变更类 | q.d1 将 0 显示为 `di_提示营救成功`；1 跳过失败文案但仍走刷新/成功记录路径，细分需真实样本。 | medium-high |
| `0x8238` | `-20` | 已被劝降 | q.d1 显示 `di_提示已被劝降`。 | high |
| `0x8238` | `other non-zero` | 营救失败 | q.d1 默认显示 `di_提示营救失败`。 | high |
| `0x823b` | `0` | 放弃成功 | q.a1 成功分支 `f6(0)` 并显示 `di_提示放弃成功`。 | high |
| `0x823b` | `non-zero` | 放弃失败 | q.a1 非 0 显示 `di_提示放弃失败`。 | high |

## 4. `z.D` / host id 语义

| 符号 | 建议命名 | 证据 | 监狱链路用法 | 置信度 |
|---|---|---|---|---|
| `LscriptPages/game/z;->D` | `current_fief_id_or_prison_host_fief_id` | `q.M1(J)` 同时写 `q.o=z.D=input` 与 `z.C=Lo/a.p3(input)`；`Lo/a.p3` 在封地 id 表 `Lo/a.ov` 中定位 index。 | `z.i0(0)` 用 `Lo/a.G2(z.D,0)` 列出 type0 被俘对象；`z.i0(2)` 用 `Lo/a.G2(z.D,1)` 列出 type1 俘虏对象；`z.d1` 把 `z.D` 作为 0x1234/0x1236/0x1238/0x123b 的第一个 long。 | medium-high |
| `Lo/a.Eo[type][idx]` | `object_owner_fief_id` | `Lo/a.Q3(type,idx)` 直接返回 `Eo[type][idx]`；`Lo/a.G2(host,0)` 用 `Eo[0][idx] == host` 过滤 type0 对象；`z.S` 对将领响应取 `Q3(0,idx)` 后调用 `q.M1(fief_id)`。 | type0 被俘列表按 `Eo[0]` 归属到当前封地/监狱宿主。 | medium-high |
| `Lo/a.Zo[idx]` | `type1_prison_host_fief_id` | `Lo/a.G2(host,1)` 不用 `Eo[1]`，而是用 type1 扩展 `Zo[idx] == host` 过滤俘虏列表。 | type1 “我方监狱中的俘虏/可劝降对象”所属监狱/封地 id。 | medium |

因此，`q.Z0(opcode, z.D, general_id, pay_mode)` 的第一个 long 在监狱动作中建议命名为 `host_fief_id` / `prison_host_fief_id`，不是将领 id，也不应优先命名为 city id。保守表述为“当前封地/监狱宿主 id”。

## 5. 服务端重建影响

- 前置接口 `0x1233/0x8233` 需要返回 `ctrl_type + not_found_flag + 两个 long 成本`；客户端把第一个成本与 `data.i.d` 铜钱比较，把第二个成本与 `data.g.F` 黄金比较。
- 劝降/营救/释放/放弃动作的资产扣减不通过本 handler 里的 `V5` 同步。若服务端需要扣铜钱/黄金，应通过对象刷新以外的其他同步链路或在动作语义中保证客户端余额状态一致；当前静态 handler 本身没有读 `V5`。
- `f6(type)` 是全量重建对象表；`a6(0)` 是单对象增量。服务端可按响应 schema 选择最小同步块，但字段顺序必须遵守既有 `a6/f6/b6` 合同。
- type0 被俘对象归属用 `Eo[0]` 过滤，type1 俘虏对象归属用 `Zo` 过滤；未来领域模型里应把“普通将领所属封地”和“监狱俘虏所属监狱/封地”分开建模。

## 6. 抓包覆盖说明

已做本地 flow JSON 的 opcode-sized naive scan，但该 scan 不能区分 envelope opcode 与大同步块内字段值。本轮报告以 DEX 静态证据为准；真实 `0x1233/0x1234/0x1236/0x1238/0x123b` 交易样本仍需后续触发后再验证 0/1 结果码细分。

## 7. 未解决问题

- `0x8234` 的 `result_code=0` 与 `1`、`0x8238` 的 `result_code=0` 与 `1` 细分语义需要真实响应样本确认；当前只能确定它们属于成功/状态变更类。
- `pay_mode=0/1` 由 `z.d1` 本地余额比较可高置信对应铜钱/黄金，但仍建议用真实样本确认服务端枚举名。
- `Lo/a.Wo/Yo/ap` 等 type1 扩展字段仍未命名，本轮只把与 host 过滤直接相关的 `Zo` 推进为监狱宿主封地 id 候选。
