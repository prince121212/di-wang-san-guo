# 六部任务列表字段深拆第一版

## 1. 结论摘要

本轮已把六部任务的“初始信息 / 列表刷新 / 委派 / 领奖”四条链路和任务列表主字段拆到第一版。核心结论：六部任务没有在客户端发现完整静态任务总表，任务条目由服务端通过 `0xE340/0xE341` 动态下发；客户端负责展示任务字段、计算/展示成功率候选、发起委派/领奖，并在领奖后走 `Lo/a.V5` 复合资产同步。

## 2. 协议闭环

|动作|请求|请求 opcode|响应 opcode|handler|请求体|响应要点|
|---|---|---:|---:|---|---|---|
|初始信息|`REQ_LIBUTASK_INFO`|`0x6340 / 25408`|`0xE340 / -7360`|`La0/a.E -> i(dis,0)`|空|`status/message + header + task list + Ng/Og 文官加成块`|
|列表刷新|`Req_libutaskList`|`0x6341 / 25409`|`0xE341 / -7359`|`La0/a.D -> i(dis,1)`|空|`status/message + header + task list`|
|委派任务|`Req_libutaskDispatch`|`0x6342 / 25410`|`0xE342 / -7358`|`La0/a.C`|`int task_id + byte count + long general_id[]`|刷新单任务字段并更新文官委派状态|
|领取奖励|`Req_libutaskAward`|`0x6343 / 25411`|`0xE343 / -7357`|`La0/a.B`|`int task_id`|刷新任务列表/文官，调用 `Lo/a.V5`，刷新 `Lo/a.m`|

关键证据：
- `a0_a__d____V__0xd0020.smali.txt`：`REQ_LIBUTASK_INFO` 与 `25408`。
- `a0_a__q____V__0xd07fc.smali.txt`：`Req_libutaskList` 与 `25409`。
- `a0_a__F____I__0xc14f0.smali.txt`：`Req_libutaskAward` 写 `int task_id`；`Req_libutaskDispatch` 写 `int task_id / byte count / long general_id[]`。
- dispatcher `o_a__A6__0x21f514.smali.txt`：`-7360/-7359/-7358/-7357 -> E/D/C/B`。

## 3. 列表响应结构

### 3.1 初始信息响应 `0xE340 -> E -> i(dis,0)`

```text
readByte status -> Xh
readUTF message -> Yh
if status == 0:
  i(dis, 0)
```

`i(dis, mode)` 共享 header：

```text
readInt   -> Lo/a.m        # 六部俸禄余额/株数，高置信
readByte  -> og            # 当前部门/列表状态候选
readLong  -> pg            # 时间字段候选
readShort -> qg            # 短整型状态候选
readShort -> rg            # 短整型状态候选
readLong  -> tg            # 时间字段候选
readByte  -> sg            # byte 状态候选
readInt   -> ug            # 服务器当前秒/时间基准候选
update Lo/a.g[current_city_index] = og
j(dis, mode)
```

当 `mode == 0`，`j()` 在任务列表后额外读取：

```text
readByte bonus_count
repeat bonus_count:
  readLong  general_id -> Ng[]
  readShort bonus      -> Og[]
```

`J0()` 中会把命中的 `Ng/Og` 加入成功率计算，因此 `Ng/Og` 是“文官个体任务加成/推荐加成”候选。

### 3.2 列表刷新响应 `0xE341 -> D -> i(dis,1)`

```text
readByte status -> ai
readUTF message -> bi
if status == 0:
  i(dis, 1)
```

`mode == 1` 只读取 header + task list，不读取 `Ng/Og` 附加块。

## 4. 单条任务字段结构 `j() -> h(task_id,index,dis)`

任务容器：

```text
readByte task_count
for each task:
  readInt task_id
  h(task_id, index, dis)
```

单任务字段顺序：

```text
vg[index] = task_id
readShort -> wg[index]        # 类型映射原始 ID 候选
readUTF   -> zg[index]        # 任务标题/内容
readByte  -> xg[index]        # 等级
readByte  -> Bg[index]        # 品阶/品质

readByte target_tag_count
repeat:
  readShort -> Mg[index][]    # 状态/条件标签数组

readShort -> Kg[index]        # 地形 ID
readShort -> Lg[index]        # 目标 ID
readByte  -> Jg[index]        # 可委派文官上限/人数上限
readByte  -> dispatch_raw
readInt   -> Ig[index]        # 任务耗时/时间字段候选
readInt   -> Hg[index]        # 剩余秒/完成时间字段
readInt   -> Gg[index]        # 六部经验奖励

readByte reward_count
repeat:
  readShort -> Dg[index][]    # 道具/资源 ID
  readByte  -> Eg[index][]    # 数量

readInt  -> Fg[index]         # 六部俸禄奖励
readByte -> yg[index]         # 任务成功率 %
```

状态换算：

```text
if dispatch_raw == 1:
  Ag[index] = 0
  if Hg[index] == 0:
    Ag[index] = 1            # 可领奖/已完成候选
  else:
    Hg[index] = now_ms + Hg[index] * 1000
else:
  Ag[index] = -1             # 未委派/可查看候选
```

## 5. 字段语义第一版

|字段|语义第一版|证据|
|---|---|---|
|`vg[]`|任务 ID|`I0(task_id)` 按 `vg` 查索引；委派/领奖/详情都用它|
|`zg[]`|任务标题/内容|`readUTF` 后在列表和详情直接绘制|
|`xg[]`|任务等级|详情显示 `等级 N级`|
|`Bg[]`|任务品阶/品质|`Lo/a.K` 取颜色，`Lo/a.M` 取名称；详情标签为 `品阶`|
|`wg[] -> Cg[]`|任务类型 ID 与类型名候选|通过 `Lo/a.n0/p0/q0/r0` 映射；详情标签为 `类型`|
|`Kg[]`|地形 ID|通过 `Lo/a.u0/v0` 映射；详情标签为 `地形`|
|`Lg[]`|目标 ID/目标类型|通过 `Lo/a.w0/x0` 映射；详情标签为 `目标`|
|`Mg[][]`|状态/条件标签数组|通过 `Lo/a.s0/t0` 显示；也传入 `J0()` 参与成功率条件匹配|
|`Jg[] / Wf`|可委派文官上限/人数上限|详情显示 `文官 Wf`，委派页显示 `已选委派人数 x/Wf`；超过提示 `di_超过委派上限`|
|`Ag[]`|任务状态：`-1` 未委派、`0` 进行中、`1` 可领奖/已完成候选|`F()` 只有 `Ag==1` 才发 `Req_libutaskAward`|
|`Hg[] / Yf`|进行中任务剩余秒/绝对完成时间|`h()` 把剩余秒转 `now + sec*1000`；列表显示倒计时 `后完成`|
|`Ig[] / Xf`|任务耗时/时间字段候选|`q1()` 使用 `Ig-ug` 显示 `时间`；精确含义需动态确认|
|`Gg[]`|六部经验奖励|奖励文本 `六部经验 xN`|
|`Fg[]`|六部俸禄奖励|奖励文本 `六部俸禄 xN 株`|
|`Dg[][] / Eg[][]`|额外奖励 ID 与数量|显示时 `game/m.w(id,"x") + amount`|
|`yg[] / bg`|任务成功率百分比|列表/详情显示 `任务成功率 N%`|
|`Ng[] / Og[]`|文官个体任务加成候选|只在 `mode==0` 初始信息读；`J0()` 命中 general_id 后累加 bonus|

完整字段表见：`libu_task_field_mapping.csv`。

## 6. 委派与领奖响应

### 6.1 委派响应 `0xE342 -> C`

```text
readByte status -> di
readUTF message -> ei
if status == 0:
  readInt task_id
  idx = I0(task_id)
  if idx >= 0:
    h(task_id, idx, dis)      # 刷新该任务完整字段

  readInt assignment_marker
  readByte general_count
  repeat:
    readLong general_id
    readByte general_state
    general_index = Lo/a.d3(general_id)
    if general_index >= 0:
      Lo/a.F[general_index] = assignment_marker
      Lo/a.x[general_index] = general_state
      Lo/a.c7(general_index)
```

`assignment_marker` 通常可按“文官当前任务/部门标记候选”建模，是否恒等于 task_id 需动态样本确认。

### 6.2 领奖响应 `0xE343 -> B`

```text
readByte status -> gi
readUTF message -> hi
if status >= 0:
  readInt task_id
  j(dis, 1)                  # 刷新任务列表
  readByte general_count
  repeat:
    readLong general_id
    Lo/a.a0(general_id, dis) # 刷新文官/将领详情

  clear Lo/a.F slots where value == task_id
  Lo/a.V5(dis)               # 复合资产同步
  readInt -> Lo/a.m          # 六部俸禄余额
```

服务端重建时，`Req_libutaskAward` 必须权威校验：任务是否完成、是否已领、成功/失败结果、奖励发放与幂等状态，并返回与客户端读流匹配的列表刷新、文官刷新、资产同步和俸禄余额。

## 7. 成功率计算边界

客户端存在 `La0/a.J0(...)` 用于 UI 层估算/展示成功率，输入包括：是否启用加成、候选文官 ID 数组、任务品阶/等级/地形/目标/状态标签等。它会读取：

- 文官等级、职位/属性、技能/状态数组等 `Lo/a` 数据；
- `Ng/Og` 个体 bonus；
- `Mg[]` 状态条件匹配；
- 若干 `Lo/a.A0/B0/C0/D0/E0/F0` 加成/上限常量。

但委派请求本身只上传 `task_id + general_id[]`，所以最终成功率、任务状态和奖励仍应以服务端为准。

## 8. 对重建服务端的影响

初版服务端数据模型建议：

```text
libu_task_instance:
  task_id int
  title string
  type_id short
  level byte
  quality byte
  terrain_id short
  target_id short
  state_tag_ids short[]
  max_general_count byte
  status enum {not_dispatched, in_progress, claimable_or_completed}
  duration_or_end int
  remaining_seconds int
  success_rate byte
  reward_libu_exp int
  reward_libu_salary int
  reward_items [{id: short, amount: byte}]
  assigned_general_ids long[]

libu_general_bonus:
  general_id long
  bonus short
```

关键实现点：

1. `0x6340` 初始信息返回 header、任务列表和 `Ng/Og` 加成块。
2. `0x6341` 列表刷新返回 header 和任务列表。
3. `0x6342` 委派只接受 `task_id/general_id[]`，服务端计算合法性、成功率、剩余时间和文官状态。
4. `0x6343` 领奖必须幂等，成功时刷新列表、文官状态、资产同步块和俸禄余额。

## 9. 当前边界

- `i()` header 中 `og/pg/qg/rg/tg/sg/ug` 的精确业务名仍需动态样本确认。
- `Ig` 与 `ug` 的绝对/相对时间语义仍需抓包样本确认。
- `wg/Kg/Lg/Mg` 所依赖的 `Lo/a.*` 静态表可继续单独导出成“任务类型/地形/目标/状态标签表”。
- `Ag==1` 当前按“可领奖/已完成候选”建模；若服务端存在成功/失败判定，需要动态样本确认 `yg` 与领奖结果的关系。

## 10. 产物

- `libu_task_report.md`
- `libu_task_field_mapping.csv`
- `libu_task_protocol_mapping.csv`
- `libu_task_summary.json`
- `libu_task_methods_summary.md/json`
- `method_disasm/`：`La0/a` 全方法反汇编，其中关键文件包括 `d/q/E/D/i/j/h/C/B/F/q1/i0/J0/a`。
