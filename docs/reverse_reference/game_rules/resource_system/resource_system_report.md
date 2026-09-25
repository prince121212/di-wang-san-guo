# 资源系统第一版

生成时间：2026-07-05

## 1. 本轮结论摘要

已把客户端里“全局资源、封地资源、产出显示、奖励到账同步”的主链路串起来。当前高置信确认：

- `scriptPages/data/i.d` = 当前铜钱。
- `scriptPages/data/i.e` = 当前粮食。
- `scriptPages/data/g.F` = 黄金。
- `scriptPages/data/g.G` = 白银。
- `scriptPages/data/i.i` = 当前声望。
- `scriptPages/data/i.m` = 总产钱/小时。
- `scriptPages/data/i.n` = 总产粮/小时。
- `Lo/a.tv[fief]` = 单封地产钱/小时最终显示值。
- `Lo/a.uv[fief]` = 单封地产粮/小时最终显示值。

核心判断：客户端会用 `i.A()` 对铜钱/粮食做本地显示递增，但资产最终仍以服务端同步块为准；奖励、购买、战斗等导致的资源变化，都应由服务端完成后通过 `i.b/i.z/m0.u/Lo.a.*` 等同步下来。

## 2. 全局资源字段

| 字段 | 语义 | 证据 | 置信度 |
|---|---|---|---|
| `data.i.d` | 铜钱当前值 | `g0.e` 在 `di_标题铜钱` 下显示；`k0.o` 标签 `di_标题铜钱` 对应它；`data.g.w0(-1)` 返回它 | 高 |
| `data.i.e` | 粮食当前值 | `g0.e` 在 `di_标题粮食` 下显示；`data.g.w0(-2)` 返回它 | 高 |
| `data.g.F` | 黄金 | `g0.e` 在 `di_标题黄金` 下显示；`data.g.w0(-4)` 返回它 | 高 |
| `data.g.G` | 白银 | `g0.e` 在 `di_标题白银` 下显示；`data.g.w0(-3)` 返回它 | 高 |
| `data.i.i` | 当前声望 | `k0.o` 第一行 `di_标题声望` 使用；`q0.V` 声望升级提示使用 `i/j/k` | 高 |
| `data.i.j` | 当前等级声望下限/上一级阈值 | `q0.V` 用 `i-j` / `k-j` 计算声望升级进度 | 中高 |
| `data.i.k` | 下一级声望阈值 | 同上；`i.b type=2` 更新它并把旧值转入 `j` | 中高 |
| `data.i.m` | 总产钱/小时 | `q.u` 文案 `di_总产钱` 后显示；`i.A()` 用它按小时增加 `d` | 高 |
| `data.i.n` | 总产粮/小时 | `q.u` 文案 `di_标题总产粮` 后显示；`i.A()` 用它按小时增加 `e` | 高 |
| `data.g.H` | 账号积分 | `data.g.v0(-14)` 返回“账号积分”；`data.g.w0(-14)` 返回 `g.H`；`m0.u`、`a0/a.c2` 成功响应同步 | 高 |

完整字段表见：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/resource_field_mapping.csv`

## 3. 资源同步链路

### 3.1 登录/完整同步：`scriptPages/data/i.x(String)`

`i.x` 是角色全局状态完整同步入口，顺序读取角色 ID、名称、等级/身份、铜钱、粮食、声望、产量、人口、封地/资源点等字段，并在末尾设置 `G/H` 当前时间，用于后续本地显示递增。

关键读流片段：

```text
readLong -> data.i.a
readUTF  -> data.i.b
readByte -> data.i.B
readByte -> data.i.c
readLong -> data.i.d    # 铜钱
readLong -> data.i.e    # 粮食
...
readLong -> data.i.i    # 声望当前
readLong -> data.i.j
readLong -> data.i.k
...
readInt  -> data.i.m    # 总产钱/小时
readInt  -> data.i.n    # 总产粮/小时
readLong -> data.i.o
readLong -> data.i.p
readLong -> data.i.q
readLong -> data.i.r
readByte -> data.i.s
readByte -> data.i.t
readByte -> data.i.u
readByte -> data.i.v
```

### 3.2 增量同步：`scriptPages/data/i.b(String)`

`i.b` 开头直接同步资源核心值：

```text
readLong -> data.i.d
readLong -> data.i.e
readInt  -> data.i.m
readInt  -> data.i.n
readInt  -> data.g.F
readInt  -> data.g.G
readLong -> data.g.H
```

后续还有 tagged update：`type=1` 更新声望当前 `i.i`，`type=2` 更新下级声望阈值 `i.k`，`type=4..7` 更新 `o/p/q/r`，`type=8..15` 更新封地/将领/资源点等上限候选。

### 3.3 本地显示递增：`scriptPages/data/i.A()`

`i.A()` 不是权威结算，只是客户端显示层：

```text
d += floor((now - G) * m / 3600000)
e += floor((now - H) * n / 3600000)
```

也就是说即使客户端本地显示会增长，服务端重建时仍应以服务器数据库中的资源值为准，并在关键操作后重新同步。

### 3.4 奖励到账：`scriptPages/game/m0.u(String)`

奖励领取成功响应会同步：

```text
readByte result
m0.n(stream)       # 奖励列表/展示数据
if result == 0:
  readByte -> data.i.C(...)
  readLong -> data.i.i  # 声望
  readLong -> data.i.d  # 铜钱
  readLong -> data.i.e  # 粮食
  readLong -> data.g.H  # 账号积分
  Lo/a.V5(stream)       # 封地/状态补充同步
  readUTF -> message
```

这与前面动态验证“邮件详情/战报详情只读，真正到账由结算/同步块完成”的结论一致。

## 4. 封地资源字段

`Lo/a.Y5(long,String)` 是单封地基础同步块。资源相关字段读流已经高置信命名：

| 字段 | 语义 | 证据 |
|---|---|---|
| `tv[fief]` | 单封地产钱/小时 | `q.L` 概览、`q.u` 建筑页都在 `di_标题产钱/di_封地产钱` 后显示，并追加“小时” |
| `uv[fief]` | 单封地产粮/小时 | 同上，文案为 `di_标题产粮/di_封地产粮` |
| `yv/zv` | 驻防当前/上限 | `q.L` 文案 `di_驻防` 显示为 `yv/zv` |
| `Av` | 征兵队列上限 | `q.L` 显示 `R4(fief)/Av[fief]` |
| `Kv/Lv` | 闲兵库存 | `q.L` 文案 `di_闲兵` 调用 `Lo/a.o4=sum(Lv)` |
| `Mv/Nv` | 第二组兵力池候选 | 结构与 `Kv/Lv` 类似，但业务名还未闭环，疑似伤兵/预备兵 |

因此服务端重建时，建筑静态表不是直接给客户端自己累加成最终产量；服务端应计算好每个封地最终 `tv/uv`，再通过封地同步块下发。

## 5. 负数资源 ID 映射

`scriptPages/data/g.w0(int)` 是一个很有用的资源数量解析器：

| 资源 ID | 返回字段 | 语义 |
|---:|---|---|
| `-1` | `data.i.d` | 铜钱 |
| `-2` | `data.i.e` | 粮食 |
| `-3` | `data.g.G` | 白银 |
| `-4` | `data.g.F` | 黄金 |
| `-5` | `data.i.i` | 声望 |
| `-6` | `data.i.o` | 战功候选 |
| `-14` | `data.g.H` | 账号积分 |

这个映射对后续解析奖励、消耗、礼包、商城、建筑成本里的“负数道具/资源 ID”很关键。

## 6. 服务端重建建议

1. 数据库至少先建：`coin/food/gold/silver/prestige/prestige_prev_threshold/prestige_next_threshold/coin_output_per_hour/food_output_per_hour/population_used/population_limit/resource_point_used/resource_point_limit/fief_limit/general_limit/extended_currency_H`。
2. 客户端登录后返回 `i.x + data.g.h3 + Lo/a.Z5` 等完整状态；普通操作后可用 `i.b/i.z` 做轻量同步。
3. 所有资源变动必须服务端权威计算，客户端本地 `i.A()` 仅用于显示平滑增长。
4. 封地最终产量 `tv/uv` 由服务端按建筑、科技、称号、道具 buff、临时增产状态计算后下发。
5. `data.g.H` 已修正为“账号积分”；玉石应作为 `item_id=399` 的背包道具建模，不要混入 `data.g.H`。

## 7. 未完成项

- 仓储上限字段和公式尚未闭环。
- 离线产出是否按仓储上限截断仍需追服务端同步样本。
- 掠夺损失/保护规则尚未恢复。
- 人口、资源点、封地、将领上限字段已找到候选，但还需跨模块验证。
- `data.g.H` 名称已由 `g.f8/g.v0/g.w0` 静态闭环确认为“账号积分”；账号积分的具体获取/消耗入口仍需继续追。

## 8. 产物索引

- `resource_field_mapping.csv`
- `resource_sync_chains.csv`
- `resource_system_summary.json`
- `method_disasm_resource/`
- `method_disasm_resource_extra/`
