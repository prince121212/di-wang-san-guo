# 普通封地建筑/建设协议入口第一版报告

生成时间：2026-07-05T07:44:29

## 1. 结论摘要

- 普通封地建筑链路不主要走 `LscriptPages/game/g;->y(String,String,S)`，而是大量走 `Lo/a;->d0(S,[B)`。
- 因此此前 `network_send_calls.csv` 的 40 个 `g.y` 发送点没有覆盖普通建筑建造/升级类请求。
- 本轮新增扫描产物 `network_d0_send_calls.csv/json`，共发现 251 个 `Lo/a.d0` 发送点。
- 与普通封地建筑/建设直接相关的第一批入口包括：
  - `reqFiefInfo / 0x1246`：请求封地详情。
  - `buildQueueAdd / 0x120D`：建筑队列/建筑相关操作。
  - `buildItemUse`：建筑/建造任务使用道具，opcode 由调用参数动态传入。
  - `q.i(String)`：封地建筑建造/升级结果候选响应，含完整错误码。
  - `q.e(String)`：建筑队列增加/建筑相关操作结果候选响应。

## 2. 新增路由表

- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/network_d0_send_calls.csv`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/network_d0_send_calls.json`

这张表与原 `network_send_calls.csv` 互补：

- `network_send_calls.csv`：扫描 `game.g->y(...)`。
- `network_d0_send_calls.csv`：扫描 `Lo/a->d0(S,[B)`。

## 3. 已确认/候选入口

| 类别 | 协议 | opcode | 方法 | 字段 | 结论 |
|---|---|---|---|---|---|
| 封地信息 | `reqFiefInfo` | `0x1246 / 4678` | `q.g1(int,long)` | `mode/writeByte; fief_id/writeLong` | 请求封地详情/刷新封地信息 |
| 建筑队列 | `buildQueueAdd` | `0x120D / 4621` | `q.K1(boolean)` / `q.w1()` | `fief_id/writeLong; building_or_slot_key/writeLong` | 建筑队列/建筑相关操作，需继续细分语义 |
| 建筑道具 | `buildItemUse` | 动态参数 | `q.d(int,long,int,long,short)` | `fief_id/writeLong; building_pos_or_type/writeShort; item_or_task_id/writeLong; item_count_or_param/writeShort` | 建筑/建造任务使用道具，常见于鲁公/加速/建筑道具 |
| 建筑结果 | `fief_building_result` | `0x8200 / signed -32256` | `q.i(String)` | `status; substatus; fief_id; Lo/a.j1 update block` | 建造/升级结果候选响应，含完整建筑错误码 |
| 队列结果 | `buildQueueAdd_result` | `0x8206 / signed -32250` | `q.e(String)` | `status; sync block; fief_id; queue update` | 建筑队列/建筑相关操作结果候选响应 |

## 4. `q.i(String)` 建筑错误码

`q.i` 的文案明确为封地/建筑建造类结果：

| status | 含义 |
|---:|---|
| 1 | 封地不在 |
| 2 | 建筑不在 |
| 3 | 位置错误 |
| 4 | 条件不足 |
| -1 | 前提不足 |
| -2 | 前提不足1 |
| -3 | 君主等级/君主条件不足 |
| -4 | 人口数量不足 |
| -5 | 前提不足2 |
| -6 | 铜钱不足 |
| -7 | 粮食不够 |
| -8 | 正在训练 |
| -9 | 书院只能一个 |
| -10 | 建造已满级 |
| 5 | 队列已满 |
| 7 | 5 个队列限制 |

成功/特殊状态时会调用 `Lo/a.j1(fief_id, stream)` 更新封地建筑数据。

## 5. 当前边界

- `buildQueueAdd` 的 UI 文案在不同分支出现“联网拆除全部”，说明它可能被多个建筑队列/拆除场景复用，不能简单命名为“增加队列”。
- 普通建筑“建造”“升级”“取消升级”“拆除”的精确 opcode 分工，还需要继续追 `q.K1/t1/u1/v1/L1` 与 `LscriptPages/data/f;->u(...)` 的封装发送逻辑。
- 已明确普通建筑链路与 `reqCityTraitLevelUp` 不同：后者是城池特性/天赋升级。

## 6. 产物

- 入口表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fief_building_protocol_entries.csv`
- JSON 汇总：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fief_building_protocol_entries_summary.json`
- d0 发送路由表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/network_d0_send_calls.csv`
- 反汇编目录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_fief_building`
