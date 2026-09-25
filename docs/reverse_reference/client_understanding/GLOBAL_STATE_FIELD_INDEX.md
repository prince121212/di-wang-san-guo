# 客户端全局状态字段索引（第一版）

生成时间：2026-07-05  
目标：把 `scriptPages/data/i`、`scriptPages/data/g`、`Lo/a.bv/cv/dv`、`Lo/a.b6`、`scriptPages/data/d` 等已经拆出的客户端状态字段汇总成未来服务端重建可查的一张索引。

## 1. 产物

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/GLOBAL_STATE_FIELD_INDEX.md`
- 字段索引 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/global_state_field_index.csv`
- 同步块地图 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/global_state_sync_blocks.csv`
- 负数资源 ID CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/global_state_negative_resource_ids.csv`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/global_state_field_index_summary.json`

## 2. 汇总统计

- 字段索引行数：95；其中 high/high-* 置信行：67。
- 覆盖域：equipment_state=15、fief=8、fief_sync=1、global/player=18、item_stack=3、object_b6=38、object_sync=2、player_identity=1、player_limits=6、prison_host_index=3。
- 本文件是“客户端字段索引”，不是最终数据库 schema；字段名保留客户端容器和当前最佳业务名。

## 3. 最关键状态域

| 状态域 | 关键容器/字段 | 当前结论 | 服务端重建影响 |
|---|---|---|---|
| 玩家资源 | `data.i.d/e/m/n/i/j/k/o/q/r/s/t/u/v`, `data.g.F/G/H` | 铜钱/粮食/产量/声望/人口/上限/金银/账号积分已命名；`data.g.H` 是账号积分，不是玉石。 | 登录/奖励/购买/征兵等要权威同步；本地产出只是显示平滑。 |
| 负数资源 ID | `data.g.w0/v0/f8` | `-1..-6/-14` 已能解析到当前值；`-14=账号积分`。 | 奖励/成本表引用负数 ID 时按此映射处理。 |
| 通用道具栈 | `Lo/a.bv/cv/dv` | `bv=item_id/stack_id`, `cv=数量`, `dv=long 参数候选`；将神魂=286，玉石=399。 | V5 下发背包/道具栈；不要把玉石实现成 `data.g.H`。 |
| 装备状态 | `scriptPages/data/d.d/e/f/g/h/i/j/k/l/m` | bank0 由 V5 全量重建；bank1 由 c6 按 host 维护，`k=host_id` 反链。 | 装备穿戴/强化响应必须同时考虑装备实例和宿主 b6 属性。 |
| 对象/将领 | `Lo/a.co/do/.../b6` | type0 为将领/可装备宿主；type1 为俘虏/第二对象表；培养、监狱字段已部分命名。 | `a6` 只更新已有对象，`f6` 才重建列表；响应字段顺序必须严格一致。 |
| 封地/宿主 | `Lo/a.ov`, `Y5/Z5/k1`, `Eo/Zo`, `z.D` | `ov` 是封地 id 表；监狱动作 `z.D` 是当前封地/监狱宿主 id 候选。 | 封地 id 是将领归属、监狱 host、建筑/资源状态的连接键。 |

## 4. 同步块地图

| 同步块 | 类型 | schema 摘要 | 更新内容 | 服务端重建备注 | 置信度 |
|---|---|---|---|---|---|
| `scriptPages/data/i.x` | full role/player state | role_id, name, level/rank, d/e/f/vip, i/j/k, m/n/o/p/q/r/s/t/u/v/w/D/F, data.g.h3, y/z... | 玩家基础、资源、声望、人口、资源点/封地/将领上限等。 | 进服/登录后必须优先满足的全局状态块。 | high |
| `scriptPages/data/i.b` | incremental player resource/state | d,e,m,n,g.F,g.G,g.H,x then tagged updates 0..15/91 | 铜钱/粮食/产量/金银/账号积分及声望、人口、上限 tag 更新。 | 奖励、资源刷新、活动响应常用；需要保留 tag 语义。 | high |
| `scriptPages/data/i.z` | short player resource sync | d,e,m,n,q,r,g.F,g.G | 铜钱/粮食/产量/人口/黄金/白银短同步。 | 局部刷新可用；不包含账号积分 H。 | medium-high |
| `Lo/a.V5` | composite asset sync | data.g.F/G; stack_count + bv/cv/dv; data.d bank0 equipment; ev/fv/reserved/gv | 黄金/白银、通用道具栈、装备 bank0。 | 大量业务响应尾块/中块；不是完整背包唯一来源但必须严格按字段顺序。 | high |
| `Lo/a.c6` | equipment bank1 + host binding | host_id; linked equipment ids; update_count equipment records in data.d bank1; data.d.k host backref | 宿主已穿戴/绑定装备与 bank1 装备记录。 | 装备信息/穿戴/强化响应使用；host_id 必须能在 co[0] 找到，否则客户端不继续消费 c6。 | high |
| `Lo/a.a6/f6/b6` | object/general/prisoner sync | co[type] id table + b6 common fields + type1 extension + type0/status3 extension | 将领/宿主/type1 俘虏对象字段、培养字段、监狱字段。 | 培养、装备、监狱动作均依赖；a6 不新增 slot，f6 才重建列表。 | high |
| `Lo/a.Z5/Y5/k1` | fief state sync | Z5 count+fief ids; Y5 base fief fields; k1 temporary production/build-queue states | 封地 id 表、产钱/产粮、驻防、闲兵库存、建筑/增产临时状态。 | 角色/封地/建筑响应必须满足；ov 与 z.D/prison host id 共享封地 id 空间。 | high |
| `scriptPages/data/d` | equipment state container | d/e/f/g/h/i/j/k/l/m over two banks | 装备实例、模板、品质/强化、保底、风险、宿主反链、描述文本。 | 由 V5 重建 bank0，由 c6 维护 bank1；装备操作响应需同步相关宿主 b6。 | high |

## 5. 高价值字段摘录

| 域 | 容器 | 字段 | 命名 | 含义 | 置信度 |
|---|---|---|---|---|---|
| item_stack | `Lo/a` | `bv[]` | `item_or_stack_id` | 通用条目/道具栈 id；例如 item_id=286 将神魂、item_id=399 玉石。 | high |
| item_stack | `Lo/a` | `cv[]` | `item_or_stack_quantity` | 通用条目/道具栈数量/值；p1(id) 会按 id 累加该字段。 | high |
| item_stack | `Lo/a` | `dv[]` | `item_or_stack_long_param` | 通用条目/道具栈长整型参数；可能承载时效、绑定、实例参数或保留字段。 | medium |
| object_sync | `Lo/a` | `a6(type, stream)` | `single_object_incremental_sync` | 读取 object_id 后在 co[type] 中定位已有 slot，再调用 b6 更新单个对象。 | high |
| object_sync | `Lo/a` | `f6(type, stream)` | `object_table_full_sync` | 按 count 全量重建 co[type] 与 b6 字段表；type0 会按 id 保留装备绑定侧表。 | high |
| fief_sync | `Lo/a` | `ov[]` | `fief_id_table` | 封地 id 表；Lo/a.a3(index) 返回 ov[index]，Lo/a.p3(fief_id) 反查 index。 | high |
| global/player | `scriptPages/data/i` | `d` | `当前铜钱` | 当前铜钱 | high |
| global/player | `scriptPages/data/i` | `e` | `当前粮食` | 当前粮食 | high |
| global/player | `scriptPages/data/i` | `m` | `总产钱/小时` | 总产钱/小时 | high |
| global/player | `scriptPages/data/i` | `n` | `总产粮/小时` | 总产粮/小时 | high |
| global/player | `scriptPages/data/i` | `G/H` | `铜钱/粮食本地递增起算时间` | 铜钱/粮食本地递增起算时间 | high |
| global/player | `scriptPages/data/i` | `i` | `当前声望` | 当前声望 | high |
| global/player | `scriptPages/data/g` | `F` | `黄金` | 黄金 | high |
| global/player | `scriptPages/data/g` | `G` | `白银` | 白银 | high |
| global/player | `scriptPages/data/g` | `H` | `账号积分` | 账号积分 | high |
| fief | `Lo/a` | `tv[fief]` | `单封地产钱/小时最终显示值` | 单封地产钱/小时最终显示值 | high |
| fief | `Lo/a` | `uv[fief]` | `单封地产粮/小时最终显示值` | 单封地产粮/小时最终显示值 | high |
| fief | `Lo/a` | `yv/zv[fief]` | `驻防当前/上限` | 驻防当前/上限 | high |
| fief | `Lo/a` | `Kv/Lv[fief]` | `封地闲兵库存` | 封地闲兵库存 | high |
| fief | `Lo/a` | `Bv/Cv/Dv` | `铜钱增产状态` | 铜钱增产状态 | high |
| fief | `Lo/a` | `Ev/Fv/Gv` | `粮食增产状态` | 粮食增产状态 | high |
| fief | `Lo/a` | `Hv/Iv/Jv` | `建筑队列/同时建设加成状态` | 建筑队列/同时建设加成状态 | high |
| player_limits | `data.i` | `q` | `人口当前占用` | 人口当前占用 | high |
| player_limits | `data.i` | `r` | `人口上限` | 人口上限 | high |
| player_limits | `data.i` | `u` | `资源点当前占用/当前数量` | 资源点当前占用/当前数量 | high |
| player_limits | `data.i` | `v` | `资源点上限` | 资源点上限 | high |
| player_limits | `data.i` | `s` | `封地上限` | 封地上限 | high |
| player_limits | `data.i` | `t` | `将领上限` | 将领上限 | high |
| equipment_state | `LscriptPages/data/d;` | `a` | `静态属性名表` | 攻击/生命/防御/统兵；按 Lo/a.S4(e) 的属性类型索引。 | high |
| equipment_state | `LscriptPages/data/d;` | `b` | `静态品质名表` | 普通/良好/优秀/卓越；由 f[bank][slot][0] 索引。 | high |
| equipment_state | `LscriptPages/data/d;` | `d` | `装备实例 id` | bank0 由 V5 全量重建；bank1 由 c6 维护。 | high |
| equipment_state | `LscriptPages/data/d;` | `e` | `装备模板 id` | 用于 g3/S4/z1 等静态装备表映射名称、图标、属性类型、基础值。 | high |
| equipment_state | `LscriptPages/data/d;` | `f` | `品质与强化向量` | f[][0]=品质 index；f[][1]=强化等级/强化值。 | high |
| equipment_state | `LscriptPages/data/d;` | `g` | `强化效果百分比候选` | 装备页以 g/100 + "." + g%100 + "%" 形式显示“强化效果”。 | high |
| equipment_state | `LscriptPages/data/d;` | `h` | `强化失败风险向量` | p(J,false) 返回 h[][0]，装备页显示失败掉级率/失败损毁率百分比；h[][1] 未命名。 | high |
| equipment_state | `LscriptPages/data/d;` | `i` | `强化保底次数向量` | 装备页显示“强化保底次数”并读取 i[][0]/i[][1]。 | high |
| equipment_state | `LscriptPages/data/d;` | `k` | `bank1 宿主反链` | c6 写入 host_id；r(J) 对 bank1 返回该 host_id。 | high |
| equipment_state | `LscriptPages/data/d;` | `l` | `装备额外文本/描述` | A(J) 返回原文，s(J) 去掉 <#> 标签后显示。 | high |
| equipment_state | `LscriptPages/data/d;` | `n` | `locator bank` | y(J) 设置的当前命中 bank。 | high |
| equipment_state | `LscriptPages/data/d;` | `o` | `locator slot` | y(J) 设置的当前命中 slot。 | high |
| object_b6 | `Lo/a` | `do` | `name` | 对象/将领名称。 | high |
| object_b6 | `Lo/a` | `io` | `growth_value` | 成长值；将领详情/监狱 UI 在“成长值”标签下读取 `Q2`。 | high |
| object_b6 | `Lo/a` | `jo` | `level` | 等级；UI 以 `K3(name) + (A3 level) + 级` 显示。 | high |
| object_b6 | `Lo/a` | `ko` | `exp_current` | 经验当前值；监狱/将领详情 UI 以 `B2/C2` 显示经验进度。 | high |
| object_b6 | `Lo/a` | `lo` | `exp_next_or_cap` | 经验目标/上限值；与 `ko` 组成经验进度。 | high |
| object_b6 | `Lo/a` | `mo` | `force` | 武力；将领详情 UI 在“武力”标签下读取 `K2`。 | high |
| object_b6 | `Lo/a` | `no` | `intelligence` | 智力；将领详情 UI 在“智力”标签下读取 `H3`。 | high |
| object_b6 | `Lo/a` | `oo` | `command` | 统帅；将领详情 UI 在“统帅”标签下读取 `y3`。 | high |
| object_b6 | `Lo/a` | `po` | `attack` | 攻击；将领详情 UI 在“攻击”标签下读取 `t1`。 | high |
| object_b6 | `Lo/a` | `qo` | `defense` | 防御；将领详情 UI 在“防御”标签下读取 `v2`。 | high |
| object_b6 | `Lo/a` | `ro` | `energy_current` | 体力/行动力当前值；`a8` 本地每小时 +10 并受 `so` 上限限制，`z.C` 加体力响应更新 `ro/so`。 | high |
| object_b6 | `Lo/a` | `so` | `energy_max` | 体力/行动力上限；`a8` 作为 `ro` 上限，UI 以 `T2/U2` 显示。 | high |
| object_b6 | `Lo/a` | `vo` | `troop_capacity` | 配兵上限/统兵容量；将领详情 UI 在“配兵上限”标签下读取 `r1`。 | high |
| object_b6 | `Lo/a` | `wo` | `loyalty_current` | 忠诚度当前值；`z.I` 加忠诚响应更新 `wo/xo`，UI 显示忠诚度 `D2/E2`。 | high |
| object_b6 | `Lo/a` | `xo` | `loyalty_max` | 忠诚度上限/满值；`z.I` 提示“将领忠诚已全加满”并更新 `wo/xo`。 | high |
| object_b6 | `Lo/a` | `zo` | `salary_copper` | 俸禄铜钱；将领详情 UI 在“俸禄”标签下读取 `d4` 并追加“铜钱”。 | high |
| object_b6 | `Lo/a` | `Ao` | `breakout_ability` | 突围能力；将领详情 UI 在“突围能力”标签下读取 `A2`。 | high |
| object_b6 | `Lo/a` | `Eo` | `object_owner_fief_id` | 对象归属封地/宿主 id；`Q3(type,idx)` 直接返回该字段，`G2(host,0)` 用 `Eo[0][idx]==host` 过滤 type0 对象，`z.S` 会取 `Q3(0,idx)` 后调用 `q.M1(fief_id)`。 | medium-high |
| object_b6 | `Lo/a` | `No` | `state_end_time` | 状态倒计时结束时间；b6 读取相对 long 后存为 `curTime + delta`，`a8` 在状态 5 时用它清状态。 | high |
| object_b6 | `Lo/a` | `Vo` | `state_code` | 对象状态 byte；`v4` accessor 读取，`a8` 处理状态 5/9 倒计时，`b6` 在 type!=1 且状态 3 时读取额外字段。 | high |
| object_b6 | `Lo/a` | `Po` | `capture_persuade_count_by_view` | 监狱/俘虏次数字段；type0 在“被劝次数”下显示，type1 在“劝降次数”下显示。 | high |
| object_b6 | `Lo/a` | `Qo` | `capture_rescue_count_by_view` | 监狱/俘虏次数字段；type0 在“营救次数”下显示，type1 在“被救次数”下显示。 | high |
| object_b6 | `Lo/a` | `To` | `cultivation_guarantee_count_current` | 将领培养当前保底/失败累计次数候选；培养 UI 在“保底次数”标签下作为第一个数值读取，培养失败响应仍走 `a6` 同步。 | medium-high |
| object_b6 | `Lo/a` | `Uo` | `cultivation_growth_full_or_cap_flag` | 培养保底配对/成长已满标志候选；`G3` accessor 读取，培养 UI 与 `To` 配对显示，同时发送 `0x1275` 前若 `G3(0,idx)!=0` 会直接提示“将领成长值已满”。 | medium |
| object_b6 | `Lo/a` | `Xo` | `owner_lord_name_type1` | type==1 扩展字段；将领详情 UI 在“归属君主”标签下显示 `Xo[idx]`。 | high for type1 |
| object_b6 | `Lo/a` | `Zo` | `type1_prison_host_fief_id` | type==1 扩展 long；`G2(host,1)` 不走 `Eo[1]`，而是用 `Zo[idx]==host` 过滤我方监狱俘虏/可劝降对象。 | medium |
| object_b6 | `Lo/a` | `bp` | `country_name_type1` | type==1 扩展字段；将领详情 UI 在“所属国”标签下显示 `bp[idx]`。 | high for type1 |
| object_b6 | `Lo/a` | `cp` | `prisoner_persuade_cooldown_base_time_type1` | type==1 扩展 long；`E3(idx)=max(cp+3600000-now,0)`，监狱俘虏页显示“劝降剩余”，点击劝降前若剩余>0 提示“再次劝降”。 | high for type1 |
| object_b6 | `Lo/a` | `dp` | `captured_self_rescue_cooldown_end_time` | 仅 type!=1 且 `Vo==3` 读取的结束时间；`e4` 显示“营救剩余”，点击营救前若剩余>0 提示“再次营救”。 | high |
| object_b6 | `Lo/a` | `co` | `object_id_table` | 二维对象 id 表；type0 高置信为将领/可装备宿主主表，type1 为第二对象表。 | high |
| object_b6 | `Lo/a` | `Oo` | `last_energy_tick_time` | 体力本地恢复计时基准；b6 写为当前时间，`a8` 用它判断是否超过 1 小时并给 `ro` +10。 | high |
| object_b6 | `Lo/a` | `jp` | `host_equipment_id_bindings` | type0 宿主装备绑定侧表；`c6` 按 host_id 写入，`z2(host_id)` 返回宿主已穿戴装备 id 列表。 | high |

## 6. 负数资源 ID 映射

| resource_id | 显示名 | 当前值字段 | 置信度 | 备注 |
|---|---|---|---|---|
| `-1` | 铜钱 | `data.i.d` | 高 | g.w0 直接返回该字段 |
| `-2` | 粮食 | `data.i.e` | 高 | g.w0 直接返回该字段 |
| `-3` | 白银 | `data.g.G` | 高 | g.w0 直接返回该字段 |
| `-4` | 黄金 | `data.g.F` | 高 | g.w0 直接返回该字段 |
| `-5` | 声望 | `data.i.i` | 高 | g.w0 直接返回该字段 |
| `-6` | 战功 | `data.i.o` | 高 | g.w0 直接返回该字段 |
| `-7` | 将领经验 | `未在 w0 明确返回/保留` | 中 | g.v0 有名称；g.w0 当前分支返回 0/保留，具体数量来源需另追 |
| `-8` | 基地预备兵 | `未在 w0 明确返回/保留` | 中 | g.v0 有名称；g.w0 当前分支返回 0/保留，具体数量来源需另追 |
| `-9` | 荣誉值 | `未在 w0 明确返回/保留` | 中 | g.v0 有名称；g.w0 当前分支返回 0/保留，具体数量来源需另追 |
| `-10` | 竞技币 | `未在 w0 明确返回/保留` | 中 | g.v0 有名称；g.w0 当前分支返回 0/保留，具体数量来源需另追 |
| `-11` | 俸禄 | `未在 w0 明确返回/保留` | 中 | g.v0 有名称；g.w0 当前分支返回 0/保留，具体数量来源需另追 |
| `-12` | 战法经验点 | `未在 w0 明确返回/保留` | 中 | g.v0 有名称；g.w0 当前分支返回 0/保留，具体数量来源需另追 |
| `-13` | 战法谋略值 | `未在 w0 明确返回/保留` | 中 | g.v0 有名称；g.w0 当前分支返回 0/保留，具体数量来源需另追 |
| `-14` | 账号积分 | `data.g.H` | 高 | g.w0 直接返回该字段 |

## 7. 当前边界

- `data.g.H` 已确定为账号积分；玉石是 `item_id=399` 道具栈，走 `Lo/a.bv/cv/dv`/背包同步。
- `Lo/a.dv`、部分 `b6` 低置信字段、`data.d.j/m`、type1 `Wo/Yo/ap` 仍保留候选名，不应过度建模。
- 全局状态字段索引优先服务“读懂客户端”和未来响应合同；真正服务端数据库可以重命名，但必须能序列化回这些客户端字段。
