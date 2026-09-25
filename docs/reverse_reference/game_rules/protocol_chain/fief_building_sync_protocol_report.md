# 封地建筑同步块协议字段初步

- 生成时间：`2026-07-05T08:03:08`
- 样本：`三国·帝王联盟1.66.apk`
- 范围：`Lo/a.Z5`、`Lo/a.Y5`、`Lo/a.k1`、`Lo/a.j1`、`Lo/a.T5`，即普通封地基础信息、建筑列表、建筑队列/增产状态和每建筑嵌套任务同步块。

## 1. 结论摘要

1. 完整封地缓存入口是 `Lo/a.Z5(String)`：先读 `Ov/readByte` 作为每封地建筑槽位容量，再读 `fief_count/readByte`，每个封地先 `readLong fief_id`，再调用 `Y5(fief_id, stream)` 和 `j1(fief_id, stream)`。
2. `Y5` 是封地基础信息块，内部调用 `k1` 读取封地级临时状态。
3. `j1` 是普通建筑列表块，每条建筑记录字段为：
   `slot_position_id/readByte`、`building_instance_id/readLong`、`building_type/readByte`、`building_level/readByte`、`build_timer/readInt`、`unused_progress_int/readInt`、`state_sign_long/readLong`、`T5 nested block`。
4. `k1` 已能命名三组状态：铜钱增产、粮食增产、同时建筑队列加成。
5. `T5` 是按建筑实例 ID 关联的嵌套任务块，UI 会用它展示兵种/产出类型、当前数量、上限、剩余时间等。

## 2. `Z5` 完整封地列表入口

| 顺序 | 字段 | IO | 缓存 | 说明 |
|---:|---|---|---|---|
| 1 | `building_slot_capacity` | `readByte` | `Lo/a.Ov` | 每封地普通建筑槽位容量。 |
| 2 | `fief_count` | `readByte` | loop count | 全量封地数量。 |
| 3 | `fief_id` | `readLong` | `Lo/a.ov[index]` | 封地 ID。 |
| 4 | `fief_base_block` | `Y5` | `pv/qv/rv/...` | 封地基础信息与状态。 |
| 5 | `building_list_block` | `j1` | `Pv/Qv/Rv/...` | 普通建筑列表。 |

证据：`Z5 000000-000182`。

## 3. `j1` 普通建筑列表字段

| 顺序 | 字段 | IO | 缓存 | 语义 |
|---:|---|---|---|---|
| 1 | `building_count` | `readByte` | loop count | 本封地下发建筑记录数。 |
| 2 | `slot_position_id` | `readByte` | `Lo/a.Vv[fief][i]` | 建筑槽位/位置编号；`Q1` 返回该值，建筑请求第 3 字段使用它。 |
| 3 | `building_instance_id` | `readLong` | `Lo/a.Pv[fief][i]` | 建筑实例/任务 ID；`H1` 返回该值。 |
| 4 | `building_type` | `readByte` | `Lo/a.Qv[fief][i]` | 建筑类型；`Z1` 返回该值，`-1` 为空槽。 |
| 5 | `building_level` | `readByte` | `Lo/a.Rv[fief][i]` | 建筑等级；`L1` 返回该值。 |
| 6 | `build_timer_ms_or_task_duration` | `readInt` | `Lo/a.Sv[fief][i]` | 建造/升级计时字段；UI 用 `W1()/1000` 展示剩余时间。 |
| 7 | `server_progress_int_unused` | `readInt` 后清零 | `Lo/a.Tv[fief][i]=0` | 客户端读取后立即覆盖为 0，疑似旧版进度字段。 |
| 8 | `build_state_sign_flag` | `readLong` 只取正负 | `Lo/a.Uv[fief][i]` | 负数缓存为 `-now`，非负缓存为 `now`，供 `Y1` 区分状态。 |
| 9 | `nested_building_task_block` | `T5` | `Xm/Ym/Zm/...` | 每建筑的嵌套生产/训练任务块。 |

## 4. `k1` 封地级临时状态

| 状态组 | 字段顺序 | UI 证据 |
|---|---|---|
| 铜钱增产 | `count/readByte`; 每条 `percent/readByte -> Cv`, `deadline_delta/readLong+now -> Dv`, `type/readByte -> Bv` | `q.K` 中 `di_提示铜钱增产` 使用 `Cv`，`q2` 使用 `Dv` 计算剩余时间。 |
| 粮食增产 | `count/readByte`; 每条 `percent/readByte -> Fv`, `deadline_delta/readLong+now -> Gv`, `type/readByte -> Ev` | `q.K` 中 `di_提示粮食增产` 使用 `Fv`，`J2` 使用 `Gv`。 |
| 同时建筑队列加成 | `count/readByte`; 每条 `capacity/readByte -> Iv`, `deadline_delta/readLong+now -> Jv`, `type/readByte -> Hv` | `U1` 若 `Jv[0]` 未过期，用 `Iv[0]` 覆盖默认 `xv`；UI 文案 `re_提示同时建筑`。 |

## 5. `T5` 每建筑嵌套任务块

`T5` 以建筑实例 ID 为 key 维护全局嵌套任务表：

| 顺序 | 字段 | IO/缓存 | 说明 |
|---:|---|---|---|
| 1 | `nested_action` | `readByte` | `0` 候选删除/清理，`1` 添加/更新。 |
| 2 | `nested_owner_building_id` | `readLong -> Xm` | 所属建筑实例 ID。 |
| 3 | `nested_task_count` | `readByte` | action=1 时的任务数量。 |
| 4 | `nested_task_id` | `readLong -> Ym` | 嵌套任务/产出条目 ID。 |
| 5 | `nested_task_state` | `readByte -> Zm` | UI 中值 `3` 会显示“人口达到”。 |
| 6 | `nested_target_type` | `readShort -> an` | 产出/士兵类型，UI 用 `data.g.u1(type)` 显示名称。 |
| 7 | `nested_current_amount` | `readInt -> bn` | 当前数量/已完成数量。 |
| 8 | `nested_target_or_capacity` | `readInt -> cn` | 目标数量/容量。 |
| 9 | `nested_remaining_or_total_ms` | `readLong -> dn` | UI 通过 `x1` 读取并展示剩余时间。 |
| 10 | `nested_flag_en` | `readByte -> en` | 状态标记。 |
| 11 | `nested_tick_interval` | `readInt -> fn` | 周期/间隔；客户端计算下一跳倒计时 `hn`。 |

## 6. 对重建服务端的影响

- 要让客户端进入封地并正确显示建筑，服务端至少要能构造：`Z5 -> Y5 -> k1 -> j1 -> T5` 的字段顺序。
- 普通建筑动作 `0x1200` 成功后，返回 `0x8200 -> q.i` 时要携带 `fief_id` 和 `j1` 建筑同步块，保证本地 `Pv/Qv/Rv/Sv/Uv/Vv` 更新。
- 若服务端暂不实现复杂产出/训练，`T5` 可先返回空/删除型块，但必须保持字段消费一致，否则客户端读流会错位。
- 建造队列上限既有默认 `xv`，也可能被 `k1` 的 `Iv/Jv` 临时状态覆盖；服务端应统一校验，不应信任客户端 UI 显示值。

## 7. 结构化产物

- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fief_building_sync_fields.csv`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fief_building_sync_summary.json`
- 反汇编证据目录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_fief_sync`
