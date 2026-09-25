# 普通封地建筑动作协议字段初步

- 生成时间：`2026-07-05T07:53:19`
- 样本：`三国·帝王联盟1.66.apk`
- 目标：区分普通封地建筑的建造、升级、拆除、取消、加速等请求动作，并补齐重建服务端所需字段顺序。

## 1. 结论摘要

1. 普通封地建筑不是 `reqCityTraitLevelUp / 0x1324`；城池特性升级与普通建筑升级是两套链路。
2. 普通建筑建造/升级/拆除/取消主要由 `LscriptPages/game/q;->h(int,long,int,int)` 构造，流名字符串为 `fiefMove`，但实际发送 opcode 是 `0x1200 / 4608`。
3. `q.h` 请求体固定为：
   - `action / writeByte`
   - `fief_id / writeLong`
   - `slot_or_building_slot_key / writeShort`
   - `building_type_or_current_building_type / writeShort`
4. `action` 第一版语义：
   - `0`：建造或升级共用。
   - `1`：尝试拆除单个建筑。
   - `2`：取消当前建造/升级操作候选。
5. `buildQueueAdd / 0x120D` 与 `buildItemUse / dynamic opcode` 是建筑 UI 的辅助链路，分别覆盖建筑队列/拆除全部候选与道具/加速使用。

## 2. `q.h` / `0x1200` 请求字段

| 顺序 | 字段 | IO | 证据 | 说明 |
|---:|---|---|---|---|
| 1 | `action` | `writeByte` | `q.h 00000a-00000c` | 动作码；由调用点决定。 |
| 2 | `fief_id` | `writeLong` | `q.h 000012` | 目标封地 ID。 |
| 3 | `slot_or_building_slot_key` | `writeShort` | `q.h 000018-00001a` | 建筑位置/格子键，多数来自 `Lo/a.Q1(p,a0)`。 |
| 4 | `building_type_or_current_building_type` | `writeShort` | `q.h 000020-000026`，`data.f.u` 追加 short 后 `d0(0x1200)` | 建造时为选择建筑类型；升级/拆除/取消时为当前位置建筑类型，多数来自 `Lo/a.Z1(p,a0)`。 |

## 3. 动作分工

| 动作 | 方法 | 实际参数 | 文案证据 | 置信度 |
|---|---|---|---|---|
| 建造 | `q.u1() -> q.h(...)` | `action=0, fief_id=q.o, slot=Q1(p,a0), building_type=g0[f0]` | `di_建造` | 高 |
| 升级 | `q.v1() -> q.h(...)` | `action=0, fief_id=q.o, slot=Q1(p,a0), building_type=Z1(p,a0)` | `di_升级` | 中高 |
| 尝试拆除 | `q.w1() -> q.h(...)` | `action=1, fief_id=q.o, slot=Q1(p,a0), building_type=Z1(p,a0)` | `di_联网尝试拆除` | 中高 |
| 取消操作 | `q.t1() -> q.h(...)` | `action=2, fief_id=q.o, slot=Q1(p,a0), building_type=Z1(p,a0)` | `cancelbuild`, `di_联网取消操作` | 中高 |

> 重要更正：`cancelbuild` 分支最终传给 `q.h` 的第一个参数是 `v6`，而方法开头 `v6=2`；附近出现的 `6` 是状态/按键判断，不是请求动作码。

## 4. `buildQueueAdd / 0x120D`

字段：

| 顺序 | 字段 | IO | 证据 | 说明 |
|---:|---|---|---|---|
| 1 | `fief_id` | `writeLong` | `q.K1 00032c`, `q.w1 000110` | 目标封地。 |
| 2 | `building_instance_or_slot_id` | `writeLong` | `q.K1 00031a -> H1(p,a0)`, `q.w1 0000fe -> H1(p,a0)` | 建筑实例/格子长整型键。 |

该请求在 UI 文案中出现 `di_联网拆除全部`，但响应 `q.e` 成功文案为 `di_增加建筑列队成功`。因此第一版将其命名为“建筑队列/拆除全部候选”，需要后续用动态包确认具体业务语义。

## 5. `buildItemUse` 动态 opcode

构造器：`LscriptPages/game/q;->d(int,long,int,long,short)`。

字段：

| 顺序 | 字段 | IO | 说明 |
|---:|---|---|---|
| 1 | `fief_id` | `writeLong` | 目标封地。 |
| 2 | `building_pos_or_type` | `writeShort` | 建筑位置/类型/对象类型。 |
| 3 | `item_or_task_id` | `writeLong` | 建筑任务、实例或道具目标 ID。 |
| 4 | `item_count_or_param` | `writeShort` | 使用数量或附加参数。 |

已确认的调用候选：

| opcode | 十进制 | 语义候选 | 证据 |
|---|---:|---|---|
| `0x1208` | 4616 | 建筑/建造任务加速候选 | `q.t1 buildPop_speed`, `q.K1 0002c0-0002fc` |
| `0x1240` | 4672 | 招募加速/招募令使用候选 | `di_联网加速招募` |
| `0x120B` | 4619 | 科技研究加速 | `di_联网科技加速` |

## 6. 响应处理器

| 协议 | opcode | handler | 字段/语义 |
|---|---|---|---|
| 建筑动作结果 | `0x8200 / signed -32256` | `q.i(String)` | `status/readByte; substatus/readByte; fief_id/readLong; Lo/a.j1 update block` |
| 建筑队列结果 | `0x8206 / signed -32250` | `q.e(String)` | `status/readByte`; `-1` 走全局同步，`0` 走成功同步并更新队列/剩余时间 |

`q.i` 已恢复主要错误码：封地不在、建筑不在、位置错误、条件不足、前提不足、君主不足、人口不足、铜钱不足、粮食不够、正在训练、书院只能一个、建造已满级、队列已满、5 个队列限制。

## 7. 对重建服务端的影响

- 服务端需要把 `0x1200` 当作普通建筑动作入口处理，即使客户端流名叫 `fiefMove`。
- `action=0` 需要根据当前封地格子状态与第 4 个 short 判断是“新建”还是“升级”。
- `action=1/2` 分别按拆除/取消处理，并统一返回 `0x8200` 建筑结果和封地建筑同步块。
- 道具/加速类请求不要直接信任客户端提交的数量/目标，需要由服务端校验背包、队列、剩余时间和目标归属。

## 8. 结构化产物

- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fief_building_action_fields.csv`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fief_building_action_summary.json`
