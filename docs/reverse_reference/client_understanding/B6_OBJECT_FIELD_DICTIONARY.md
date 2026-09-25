# `Lo/a.b6` 宿主/将领对象字段字典（第一版）

生成时间：2026-07-05  
目标：在已恢复 `b6` 精确读流顺序的基础上，结合 UI 标签和 accessor 调用，把 type0 将领/装备宿主对象字段推进到可用于未来服务端同步合同的语义命名。

## 1. 产物

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/B6_OBJECT_FIELD_DICTIONARY.md`
- 字段字典：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/b6_object_field_dictionary.csv`
- Accessor 映射：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/b6_object_field_accessors.csv`
- UI 证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/b6_object_field_ui_evidence.csv`
- 字段引用摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/b6_object_field_references.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/b6_object_field_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/b6_object_field_summary.json`

## 2. 总体结论

- 本轮对 `b6` 字段形成 60 行字段字典，其中高置信/高置信 type1 字段 28 行。
- `type 0` 高置信是将领/可装备宿主对象表；装备 `host_id` 通过 `Lo/a.c3(0, host_id)` 定位到这张表。
- `b6` 字段里已经能明确覆盖：名称、等级、经验、忠诚、体力、成长值、武力、智力、统帅、攻击、防御、配兵上限、俸禄、状态/倒计时、装备绑定侧表。
- 本轮补强了培养/将神魂链路：`To` 高概率为当前保底/失败累计次数，`Uo/G3` 是保底配对兼成长已满预检查字段，`So/V2` 是名称颜色/成长档位候选。
- 仍需谨慎的字段主要集中在俘虏/监狱扩展、`Uo` 的精确业务名、type1 第二对象表文本/身份字段。

## 3. 高置信字段命名

| 字段 | 命名 | 语义 | 证据/来源 | 置信度 |
|---|---|---|---|---|
| `Lo/a.do` | `name` | 对象/将领名称。 | b6@0x0010 / refs=6 | high |
| `Lo/a.io` | `growth_value` | 成长值；将领详情/监狱 UI 在“成长值”标签下读取 `Q2`。 | b6@0x0074 / refs=5 | high |
| `Lo/a.jo` | `level` | 等级；UI 以 `K3(name) + (A3 level) + 级` 显示。 | b6@0x0088 / refs=7 | high |
| `Lo/a.ko` | `exp_current` | 经验当前值；监狱/将领详情 UI 以 `B2/C2` 显示经验进度。 | b6@0x009c / refs=7 | high |
| `Lo/a.lo` | `exp_next_or_cap` | 经验目标/上限值；与 `ko` 组成经验进度。 | b6@0x00b0 / refs=5 | high |
| `Lo/a.mo` | `force` | 武力；将领详情 UI 在“武力”标签下读取 `K2`。 | b6@0x00c4 / refs=5 | high |
| `Lo/a.no` | `intelligence` | 智力；将领详情 UI 在“智力”标签下读取 `H3`。 | b6@0x00d8 / refs=5 | high |
| `Lo/a.oo` | `command` | 统帅；将领详情 UI 在“统帅”标签下读取 `y3`。 | b6@0x00ec / refs=6 | high |
| `Lo/a.po` | `attack` | 攻击；将领详情 UI 在“攻击”标签下读取 `t1`。 | b6@0x0100 / refs=5 | high |
| `Lo/a.qo` | `defense` | 防御；将领详情 UI 在“防御”标签下读取 `v2`。 | b6@0x0114 / refs=5 | high |
| `Lo/a.ro` | `energy_current` | 体力/行动力当前值；`a8` 本地每小时 +10 并受 `so` 上限限制，`z.C` 加体力响应更新 `ro/so`。 | b6@0x0128 / refs=8 | high |
| `Lo/a.so` | `energy_max` | 体力/行动力上限；`a8` 作为 `ro` 上限，UI 以 `T2/U2` 显示。 | b6@0x013c / refs=7 | high |
| `Lo/a.vo` | `troop_capacity` | 配兵上限/统兵容量；将领详情 UI 在“配兵上限”标签下读取 `r1`。 | b6@0x0178 / refs=6 | high |
| `Lo/a.wo` | `loyalty_current` | 忠诚度当前值；`z.I` 加忠诚响应更新 `wo/xo`，UI 显示忠诚度 `D2/E2`。 | b6@0x018c / refs=7 | high |
| `Lo/a.xo` | `loyalty_max` | 忠诚度上限/满值；`z.I` 提示“将领忠诚已全加满”并更新 `wo/xo`。 | b6@0x01a0 / refs=7 | high |
| `Lo/a.zo` | `salary_copper` | 俸禄铜钱；将领详情 UI 在“俸禄”标签下读取 `d4` 并追加“铜钱”。 | b6@0x01b4 / refs=5 | high |
| `Lo/a.Ao` | `breakout_ability` | 突围能力；将领详情 UI 在“突围能力”标签下读取 `A2`。 | b6@0x01c8 / refs=5 | high |
| `Lo/a.No` | `state_end_time` | 状态倒计时结束时间；b6 读取相对 long 后存为 `curTime + delta`，`a8` 在状态 5 时用它清状态。 | b6@0x0288 / refs=8 | high |
| `Lo/a.Vo` | `state_code` | 对象状态 byte；`v4` accessor 读取，`a8` 处理状态 5/9 倒计时，`b6` 在 type!=1 且状态 3 时读取额外字段。 | b6@0x02b2 / refs=10 | high |
| `Lo/a.Po` | `capture_persuade_count_by_view` | 监狱/俘虏次数字段；type0 在“被劝次数”下显示，type1 在“劝降次数”下显示。 | b6@0x02c6 / refs=5 | high |
| `Lo/a.Qo` | `capture_rescue_count_by_view` | 监狱/俘虏次数字段；type0 在“营救次数”下显示，type1 在“被救次数”下显示。 | b6@0x02da / refs=5 | high |
| `Lo/a.Xo` | `owner_lord_name_type1` | type==1 扩展字段；将领详情 UI 在“归属君主”标签下显示 `Xo[idx]`。 | b6@0x0350 / refs=6 | high for type1 |
| `Lo/a.bp` | `country_name_type1` | type==1 扩展字段；将领详情 UI 在“所属国”标签下显示 `bp[idx]`。 | b6@0x0390 / refs=5 | high for type1 |
| `Lo/a.cp` | `prisoner_persuade_cooldown_base_time_type1` | type==1 扩展 long；`E3(idx)=max(cp+3600000-now,0)`，监狱俘虏页显示“劝降剩余”，点击劝降前若剩余>0 提示“再次劝降”。 | b6@0x03a0 / refs=5 | high for type1 |
| `Lo/a.dp` | `captured_self_rescue_cooldown_end_time` | 仅 type!=1 且 `Vo==3` 读取的结束时间；`e4` 显示“营救剩余”，点击营救前若剩余>0 提示“再次营救”。 | b6@0x03fc / refs=4 | high |
| `Lo/a.co` | `object_id_table` | 二维对象 id 表；type0 高置信为将领/可装备宿主主表，type1 为第二对象表。 | b6@side-table / refs=17 | high |
| `Lo/a.Oo` | `last_energy_tick_time` | 体力本地恢复计时基准；b6 写为当前时间，`a8` 用它判断是否超过 1 小时并给 `ro` +10。 | b6@side-table / refs=5 | high |
| `Lo/a.jp` | `host_equipment_id_bindings` | type0 宿主装备绑定侧表；`c6` 按 host_id 写入，`z2(host_id)` 返回宿主已穿戴装备 id 列表。 | b6@side-table / refs=11 | high |

## 4. 关键 UI 证据

| 方法 | 偏移 | UI/流程 | 证据 | 置信度 |
|---|---|---|---|---|
| `LscriptPages/game/z;->h()V` | 0x0562-0x084c | 将领详情属性表 | 标签“突围能力/成长值/武力/攻击/智力/防御/统帅/配兵上限/俸禄”依次调用 A2/Q2/K2/t1/H3/v2/y3/r1/d4。 | high |
| `LscriptPages/game/z;->h()V` | 0x085c-0x0878 | type1 归属信息 | 标签“归属君主/所属国”对应 `Xo[idx]` 和 `bp[idx]`。 | high |
| `LscriptPages/game/z;->n()V` | 0x013a-0x0182 & 0x0520-0x0572 | 监狱/俘虏经验忠诚 | 标签“经验/忠诚度”对应 `B2/C2` 与 `D2/E2` 进度对。 | high |
| `LscriptPages/game/z;->n()V` | 0x015a-0x01b6 & 0x0592-0x0630 | 监狱/俘虏基础属性 | 标签“成长值/武力/智力/统帅”对应 `Q2/K2/H3/y3`。 | high |
| `LscriptPages/game/z;->n()V` | 0x01b8-0x092c | 监狱/俘虏次数与剩余时间 | type0 标签“被劝次数/营救次数/营救剩余”对应 `Po/Qo/dp`；type1 标签“劝降次数/被救次数/劝降剩余”对应 `Po/Qo/cp`。 | high |
| `LscriptPages/game/z;->n()V` | 0x02da-0x043a | 我方被俘地点 | type0 在“封地/所在城”下显示 `ip/gp/hp`，其中 `hp` 以 `(x,y)` 拼接。 | medium-high |
| `LscriptPages/game/z;->e()V` | 0x0018-0x0244 | 加忠诚/加体力弹窗 | 字符串 `addLoyal/addEnergy`，忠诚显示 `D2/E2`，体力显示 `T2/U2`，并有“忠诚已满/体力已满”提示。 | high |
| `LscriptPages/game/z;->C(Ljava/lang/String;)V` | 0x0014-0x0046 | 加体力响应 | 响应按 object_id 定位后直接更新 `ro/so`。 | high |
| `LscriptPages/game/z;->I(Ljava/lang/String;)V` | 0x005e-0x00e8 | 加忠诚响应 | 响应按 object_id 定位后直接更新 `wo/xo`，失败提示“忠增失败”。 | high |
| `Lo/a;->a8()V` | 0x0050-0x00a8 | 体力本地恢复 | `ro` 每小时 +10，且不得超过 `so`，`Oo` 作为上次 tick 时间。 | high |
| `LscriptPages/gameHD/h;->m()V` | 0x0e66-0x0e8e | 统兵加成倒计时 | 若 `Io[idx] != -1` 且 `z3(Ho)>0`，显示“统兵加成剩余时间”。 | medium-high |
| `LscriptPages/gameHD/h;->f()V` | 0x078e-0x0dc8 | 培养/将神魂/保底次数 | HD 培养 UI 用 `p1(286)` 显示“将神魂”库存，读取 `To` 与 `G3(Uo)` 显示“保底次数”，确认时发送 `0x1275`。 | high |
| `LscriptPages/gameHD/g;->k()V / g;->p()V` | 0x00da-0x09e4 | 培养普通页/请求 | 普通培养页同样读取 `To/G3(Uo)`，并由 `g.p` 发送 `0x1275 writeLong(general_id)+writeShort(count)`。 | high |
| `LscriptPages/gameHD/h;->m()V / gameHD/g.f/u / La0/a.b0` | V2 callers | 将领名称颜色/成长档位 | `V2(0,idx)` 返回 `So`，只见用于索引颜色数组给将领名上色。 | medium-high |
| `Lo/a;->G2(JI)[J / LscriptPages/game/z;->i0(B)V` | G2 host filter | 监狱/将领列表宿主过滤 | `z.i0(0)` 使用 `G2(z.D,0)`，该分支按 `Eo[0]` 过滤；`z.i0(2)` 使用 `G2(z.D,1)`，该分支按 `Zo` 过滤。 | medium-high |
| `LscriptPages/game/q;->M1(J)V / Lo/a;->p3(J)I` | z.D host id | 当前封地/监狱宿主 id | `q.M1` 把输入 long 同时写入 `q.o` 与 `z.D`，并用 `Lo/a.p3` 在封地 id 表 `Lo/a.ov` 中定位 index。 | medium-high |
| `LscriptPages/gameHD/j;->E()V` | 0x014a-0x0172 & 0x05a4 | 配兵数量 | 配兵 UI 通过 `s1(II)`/`Fo` 与兵种表组合显示将领配兵。 | medium-high |

## 5. Accessor 到字段映射

| accessor | 字段 | 命名 | 说明 | 置信度 |
|---|---|---|---|---|
| `Lo/a.K3(II)` | `Lo/a.do` | `name` | 返回对象名称，空表/越界返回空串。 | high |
| `Lo/a.A3(II)` | `Lo/a.jo` | `level` | 返回等级。 | high |
| `Lo/a.B2(II)` | `Lo/a.ko` | `exp_current` | 返回经验当前值。 | high |
| `Lo/a.C2(II)` | `Lo/a.lo` | `exp_next_or_cap` | 返回经验目标/上限值。 | high |
| `Lo/a.D2(II)` | `Lo/a.wo` | `loyalty_current` | 返回忠诚当前值。 | high |
| `Lo/a.E2(II)` | `Lo/a.xo` | `loyalty_max` | 返回忠诚上限值。 | high |
| `Lo/a.T2(II)` | `Lo/a.ro` | `energy_current` | 返回体力当前值。 | high |
| `Lo/a.U2(II)` | `Lo/a.so` | `energy_max` | 返回体力上限值。 | high |
| `Lo/a.Q2(II)` | `Lo/a.io` | `growth_value` | 返回成长值。 | high |
| `Lo/a.A2(II)` | `Lo/a.Ao` | `breakout_ability` | 返回突围能力。 | high |
| `Lo/a.K2(II)` | `Lo/a.mo` | `force` | 返回武力。 | high |
| `Lo/a.H3(II)` | `Lo/a.no` | `intelligence` | 返回智力。 | high |
| `Lo/a.y3(II)` | `Lo/a.oo` | `command` | 返回统帅。 | high |
| `Lo/a.t1(II)` | `Lo/a.po` | `attack` | 返回攻击。 | high |
| `Lo/a.v2(II)` | `Lo/a.qo` | `defense` | 返回防御。 | high |
| `Lo/a.r1(II)` | `Lo/a.vo` | `troop_capacity` | 返回配兵上限。 | high |
| `Lo/a.d4(II)` | `Lo/a.zo` | `salary_copper` | 返回俸禄铜钱。 | high |
| `Lo/a.v4(II)` | `Lo/a.Vo` | `state_code` | 返回对象状态码。 | high |
| `Lo/a.z3(I)` | `Lo/a.Ho` | `command_bonus_remaining_seconds` | 返回 Ho 剩余时间。 | medium-high |
| `Lo/a.V2(II)` | `Lo/a.So` | `general_name_color_or_growth_tier` | 返回名称颜色/成长档位候选，多个将领列表用它索引颜色数组。 | medium-high |
| `Lo/a.Q3(II)` | `Lo/a.Eo` | `object_owner_fief_id` | 返回对象归属封地/宿主 id；`q.M1`/`z.D` 和 `Lo/a.p3` 会把它作为当前封地 id 使用。 | medium-high |
| `Lo/a.G3(II)` | `Lo/a.Uo` | `cultivation_growth_full_or_cap_flag` | 培养 UI 使用；请求 0x1275 前也用它做“成长值已满”预检查。 | medium |
| `Lo/a.s1(II)` | `Lo/a.Fo` | `soldier_count_or_assigned_troop_count` | 配兵 UI 使用。 | medium-high |
| `Lo/a.z2(J)` | `Lo/a.jp` | `host_equipment_id_bindings` | 按 host_id 返回已装备 id 列表。 | high |

## 6. 服务端重建影响

未来任何需要返回 `a6/f6/b6` 的服务端响应，至少要保证下列 type0 字段语义一致：

```text
co[type][slot] = object/host id
do = name
jo = level
ko/lo = exp_current / exp_next_or_cap
wo/xo = loyalty_current / loyalty_max
ro/so = energy_current / energy_max
io = growth_value
mo/no/oo = force / intelligence / command
po/qo = attack / defense
vo = troop_capacity
zo = salary_copper
Vo/No/Oo/Ro = state_code and timing fields
jp[type0][slot][] = equipped equipment ids for z2(host_id)
```

装备强化/穿戴响应更新 `c6/a6|f6/V5` 时，客户端会通过 `host_id -> c3(0, host_id) -> b6 fields` 刷新将领属性，再通过 `z2(host_id)` 刷新装备列表。因此服务端重建时不能只同步装备实例，还必须同步对应宿主对象的属性字段。

## 7. 未完全命名字段

- `eo/fo/ho/to/uo/Ao?` 之外的部分早期 short/byte 字段仍缺直接 UI 标签，需要继续从功能入口或抓包样本确认。
- `Po/Qo/dp/gp/hp/ip/cp` 已由 `PRISON_CAPTURE_FIELD_DICTIONARY.md` 精确对位：type0 为被劝/营救/营救剩余/地点，type1 为劝降/被救/劝降剩余；`Eo/Zo` 已由监狱动作响应深拆推进为封地/监狱宿主 id 过滤字段；`Ho/Io` 仍属统兵加成候选。
- `To/Uo/So` 已由 `GENERAL_CULTIVATION_GROWUP.md` 推进：`To` 可命名为当前保底次数候选，`Uo` 仍需真实 `0x8275` 样本确认是上限标志、保底目标还是复合字段；`So` 是名称颜色/成长档位候选。
- `type1` 的 `Xo/bp` 已能命名为归属君主/所属国文本，`Zo/cp` 已分别推进为监狱宿主封地 id 与劝降冷却基准；`Wo/Yo/ap` 仍需继续结合 UI。

## 8. 建议下一步

1. 继续深拆监狱动作响应 `0x8233/0x8234/0x8236/0x8238/0x823b`，确认响应内是否追加 `a6/f6/V5` 以及 `z.D` 的业务名。
2. 等后续真实培养样本出现时验证 `0x1275/0x8275` 中 `To/Uo/So` 动态取值和将神魂扣除同步块。
3. 把本字典并入未来全局状态字段字典，与 `scriptPages/data/i`、`scriptPages/data/g`、`Lo/a.bv/cv/dv` 统一索引。
