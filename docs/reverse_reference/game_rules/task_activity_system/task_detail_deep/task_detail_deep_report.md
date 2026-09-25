# 普通任务详情/领取响应字段第一版

## 1. 结论摘要

本轮把普通任务列表、任务详情、领奖请求与领奖响应串成了第一版闭环：

```text
任务列表请求: m0.r -> opcode 0x1130 / 4400
任务列表响应: 0x8130 / -32464 -> m0.s -> m0.n
任务详情请求: m0.v -> reqTaskInfo opcode 0x1132 / 4402
任务详情响应: 0x8132 / -32462 -> m0.w
任务领奖请求: m0.t -> reqGainAward opcode 0x1134 / 4404
任务领奖响应: 0x8134 / -32460 -> m0.u
```

高置信结论：

- 任务列表按 **4 个大类 group** 下发；每个 group 又分两个数量桶。
- 列表基础字段是：`task_id / title / claimable_bool / list_status`。
- 详情字段是：`description / target_lines[] / guide_text / reward`。
- `group==0` 的奖励是结构化奖励数组 `reward_id + amount`。
- `group==1/2/3` 的奖励是服务端下发的文本奖励说明。
- 领奖成功后，服务端会先刷新任务列表，再同步等级/声望/铜钱/粮食/账号积分和 `Lo/a.V5` 复合资产块。

## 2. 任务列表协议

### 2.1 请求 `m0.r()`

```text
opcode = 4400 / 0x1130
body = one byte 0
```

证据：`m0.r` 中 `const/16 4400`，构造长度为 1 的 byte 数组并写入 0 后调用 `Lo/a.d0`。

### 2.2 响应 `0x8130 -> m0.s -> m0.n`

dispatcher：

```text
0x8130 / signed -32464 -> LscriptPages/game/m0;->s(String)
```

`m0.s` 会清空 `q0.S7/T7/U7/V7/W7/X7/Y7/Z7`，然后调用 `m0.n(dis)` 读取列表。

`m0.n` 常规读流：

```text
for group in 0..3:
    readByte primary_count
    readByte secondary_count
    total = primary_count + secondary_count

    for i in primary_count:
        readLong    -> m0.m0[group][i] 任务ID
        readUTF     -> m0.n0[group][i] 任务名/标题
        readBoolean -> m0.o0[group][i] 可领奖/旧弹窗按钮候选
        m0.p0[group][i] = 1

    for i in secondary_count:
        readLong    -> m0.m0[group][idx]
        readUTF     -> m0.n0[group][idx]
        readBoolean -> m0.o0[group][idx]
        m0.p0[group][idx] 默认 0

readShort 兼容/尾字段
```

同时，`m0.n` 会按 `task_id` 把旧的详情缓存迁移到新列表：

- `m0.q0`：目标文本数组
- `m0.r0`：描述文本
- `m0.s0`：指引文本
- `m0.t0`：结构化奖励数组
- `m0.u0`：文本奖励说明

如果当前页面是任务界面状态 80，`m0.n` 会复制到 `q0` 展示缓存：

```text
m0.m0 -> q0.S7  task_id
m0.n0 -> q0.T7  title
m0.p0 -> q0.U7  list_status
m0.q0 -> q0.V7  target_lines
m0.r0 -> q0.W7  description
m0.s0 -> q0.X7  guide_text
m0.t0 -> q0.Y7  structured_reward
m0.u0 -> q0.Z7  reward_text
```

## 3. 任务详情协议

### 3.1 请求 `m0.v(group, task_id)`

```text
openDos("reqTaskInfo")
writeByte group_index
writeLong task_id
send opcode 4402 / 0x1132
```

### 3.2 响应 `0x8132 -> m0.w`

dispatcher：

```text
0x8132 / signed -32462 -> LscriptPages/game/m0;->w(String)
```

成功读流：

```text
readByte status
if status == 0:
    readByte group_index
    readLong task_id
    idx = m0.i(group_index, task_id)

    readUTF -> m0.r0[group][idx] 任务描述

    readByte target_count
    for each target:
        readUTF -> m0.q0[group][idx][target_i] 任务目标/条件文本

    readUTF -> m0.s0[group][idx] 任务指引

    if group_index == 0:
        readByte reward_count
        for each reward:
            readShort -> reward_id
            if reward_id <= -1000:
                readShort -> amount
            elif reward_id < 0:
                readInt -> amount
            else:
                readShort -> amount
        写入 m0.t0[group][idx][reward_i] = [reward_id, amount]

    if group_index in {1,2,3}:
        readUTF -> m0.u0[group][idx] 文本奖励说明

    if group_index == 1:
        readUTF 额外兼容字段/丢弃字段
else:
    显示 di_内容取失败
```

## 4. 展示字段语义

`q0.t()` 和旧弹窗 `m0.h()` 明确使用这些字段绘制：

| 展示标题 | 字段 | 语义 |
|---|---|---|
| `di_标题任务描述` | `q0.W7 / m0.r0` | 任务描述 |
| `di_标题任务目标` | `q0.V7 / m0.q0` | 任务目标/条件文本数组 |
| `di_标题任务指引` | `q0.X7 / m0.s0` | 操作指引文本 |
| `di_标题任务奖励` | `q0.Y7 / m0.t0` 或 `q0.Z7 / m0.u0` | 结构化奖励或文本奖励 |
| 领奖按钮 `lingquAward/getAwordBtn` | `q0.U7 == 1` | 列表状态为可领奖/完成候选 |

## 5. 奖励结构

`group==0` 的奖励是结构化数组，每条是：

```text
reward_id, amount
```

客户端显示逻辑：

```text
if reward_id <= -1000 and reward_id >= -99999:
    item/equip_name = data.d.o(-reward_id - 1000)
    amount 是 short
    显示 re_获取道具
elif reward_id < 0:
    amount 是 int
    if reward_id == -8:
        显示 re_获得轻骑兵
    else:
        按本地负数资源显示名数组显示：白银/黄金/粮食/铜钱/声望/声望候选
else:
    amount 是 short
    item_name = data.g.s1(reward_id)
    item_icon = data.g.c1(reward_id)
    显示 re_获取道具
```

注意：这里的任务奖励负数 ID 显示表与前面全局 `resource_id=-1..-14` 映射不完全等价，不能直接混用；应以具体协议块为准。

## 6. 领奖协议

### 6.1 请求 `m0.t(task_id, input)`

```text
openDos("reqGainAward")
writeLong task_id
writeByte has_input   # input != null 为 1，否则 0
if input != null:
    writeUTF input
send opcode 4404 / 0x1134
```

这个请求与前面“奖励领取字段第一版”的 `reqGainAward` 是同一条主领奖链路；在任务系统中可携带激活码/输入文本。

### 6.2 响应 `0x8134 -> m0.u`

dispatcher：

```text
0x8134 / signed -32460 -> LscriptPages/game/m0;->u(String)
```

读流：

```text
readByte status
m0.n(dis)  # 先刷新任务列表
if status == 0:
    readByte -> data.i.C(byte) 等级/角色短状态更新候选
    readLong -> data.i.i 当前声望
    readLong -> data.i.d 铜钱
    readLong -> data.i.e 粮食
    readLong -> data.g.H 账号积分
    Lo/a.V5(dis) 复合同步资产块
readUTF -> message/reward_text
显示成功/失败提示
```

因此，任务领奖不是客户端本地发奖；成功到账由服务端回包同步。

## 7. 服务端重建建议

任务系统初版数据库建议：

```text
task_group       byte/int   0..3
task_id          long
title            string
list_status      byte       0/1，1 可显示领奖按钮
detail_loaded    bool
description      string
target_lines     string[]
guide_text       string
reward_mode      enum(structured/text)
structured_reward: [(reward_id, amount)]
reward_text      string
claimable        bool
optional_input   string/null
```

服务端协议建议：

1. `0x1130` 返回完整 4 组任务列表，保持两个桶顺序。
2. `0x1132` 返回指定任务详情，按 group 区分结构化奖励和文本奖励。
3. `0x1134` 领奖时做服务端权威校验：任务状态、是否已领、输入码、奖励发放、幂等/重放。
4. 领奖成功必须刷新任务列表，并同步资源与 `Lo/a.V5`，否则客户端 UI 和资产缓存会错位。

## 8. 当前边界

- 4 个 `group_index` 的中文业务名还未最终确认。
- `readShort` 尾字段语义未知，当前视为兼容/版本字段。
- `m0.o0` 与 `m0.p0/U7` 都参与可领取状态，但二者精确分工仍需动态样本确认。
- `reward_id <= -1000` 使用 `data.d.o()`，当前称为装备/道具名候选，需结合任务样本确认是否专指装备或特殊道具。
