# 资源点 / 攻城目标字段语义深追第一版

- 日期：2026-07-05
- 样本：三国·帝王联盟 1.66 APK
- 目录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/storage_offline_system`

## 1. 本轮结论

上一版只恢复了 `reqResourceList / 0x1542` 与 `p.f / p.c1` 的读流骨架。本轮继续追 UI 显示函数 `LscriptPages/game/p;->s()V` 和 `p.t()`，把字段和显示标签对应起来。

核心结论：`p.f` 与 `p.c1` 这两套同构字段，在 UI 中不只是“储量/产量”列表，而是一个更完整的 **资源点 / 攻城目标 / 城池目标信息面板**。面板明确显示：

- 国家
- 天赋
- 封地
- 城主
- 驻防将领
- 道路
- 城墙
- 名将协防
- 协防几率
- 名将数量
- 攻克奖励
- 战功
- 国库铜钱
- 国库粮食

因此，之前标成“储量/产量候选”的部分字段可进一步命名：`y5/b6` 更像“道路”，`A5/d6` 更像“城墙”，`S5/t6` 是攻克奖励三元组。

## 2. 关键 UI 标签证据

`scriptPages/game/p;->s()V` 开头构造两组显示标签：

```text
主信息标签：
- ""                         # 首行名称/坐标
- di_国家                     # 国家
- di_天赋                     # 天赋
- di_标题封地                 # 封地
- di_城主                     # 城主

扩展信息标签：
- di_驻防将领                 # 驻防将领
- di_道路                     # 道路
- di_城墙                     # 城墙
```

后续又在协防和奖励区域出现：

```text
- di_名将协防
- di_协防几率
- di_名将数量
- di_攻克奖励
- di_标题战功
- di_国库铜钱
- di_国库粮食
```

这些标签直接把字段语义从“未知数值”推进到“城池/目标信息面板字段”。

## 3. `p.f` 字段语义映射

| 字段 | 读类型 | 当前语义 | 置信度 | 证据 |
|---|---|---|---|---|
| `q5` | long | 目标 ID | 高 | 列表首字段，后续 `M5[]` 与其比对。 |
| `r5` | byte | 类型码/图标类型 | 高 | `data.b.C(r5)` 取图标，`data.b.d[r5]` 取类型首字。 |
| `s5` | UTF | 名称 | 高 | 首行显示 `s5 (类型首字 x,y)`。 |
| `t5/u5` | short/short | 坐标 X/Y | 高 | 首行显示坐标。 |
| `J5` | UTF | 国家/势力 | 高 | 与 `di_国家` 标签对应。 |
| `w5/x5` | byte/byte | 天赋/加成，形如 `+N%` | 中高 | 与 `di_天赋` 标签对应。 |
| `D5/C5` | int/int | 封地当前/上限或规模/上限 | 高 | 与 `di_标题封地` 标签对应，显示 `D5/C5`，D5<=0 时显示 1。 |
| `G5/H5` | UTF/byte | 城主或守将名称/等级 | 高 | 与 `di_城主` 标签对应；空则显示“无”，非空显示 `名称(将领等级 H5)`。 |
| `F5/E5` | short/short | 驻防将领数量/上限 | 高 | 与 `di_驻防将领` 标签对应，显示 `F5/E5`。 |
| `y5` | int | 道路值/道路耐久/道路等级候选 | 中高 | 与 `di_道路` 标签对应。 |
| `A5` | int | 城墙值/城墙耐久/城墙等级候选 | 中高 | 与 `di_城墙` 标签对应。 |
| `Q5` | byte | 名将协防概率/开关 | 高 | `Q5>0` 时显示 `di_名将协防`，`di_协防几率` 值为 `Q5%`。 |
| `R5[2]` | byte x2 | 名将数量范围 | 高 | 与 `di_名将数量` 对应，显示 `R5[0]-R5[1]`。 |
| `S5[0]` | long | 攻克奖励：国库铜钱 | 高 | `di_国库铜钱 + S5[0]`。 |
| `S5[1]` | long | 攻克奖励：国库粮食 | 高 | `di_国库粮食 + S5[1]`。 |
| `S5[2]` | long | 攻克奖励：战功 | 高 | `di_标题战功 + S5[2]`。 |
| `K5/L5` | long/long | 时间/保护/刷新候选 | 低中 | 读流确认，主面板无直接标签。 |
| `z5/B5/O5/P5` | int x4 | 扩展/隐藏数值候选 | 低 | 读流确认，主面板未直接命名。 |
| `v5` | byte | 状态/归属/品质候选 | 低 | 读流确认，主面板未直接命名。 |

## 4. `p.c1` 同构字段语义映射

`p.c1` 与 `p.f` 的 UI 渲染分支几乎同构，可映射为：

| `p.f` | `p.c1` | 语义 |
|---|---|---|
| `q5` | `T5` | 目标 ID |
| `r5` | `U5` | 类型码/图标类型 |
| `s5` | `V5` | 名称 |
| `t5/u5` | `W5/X5` | 坐标 X/Y |
| `J5` | `m6` | 国家/势力 |
| `w5/x5` | `Z5/a6` | 天赋/加成百分比 |
| `D5/C5` | `g6/f6` | 封地当前/上限 |
| `G5/H5` | `j6/k6` | 城主/守将名称与等级 |
| `F5/E5` | `i6/h6` | 驻防将领数量/上限 |
| `y5` | `b6` | 道路值候选 |
| `A5` | `d6` | 城墙值候选 |
| `Q5` | `r6` | 名将协防概率/开关 |
| `R5[2]` | `s6[2]` | 名将数量范围 |
| `S5[0..2]` | `t6[0..2]` | 国库铜钱、国库粮食、战功奖励 |
| `K5/L5` | `n6/o6` | 时间/状态候选 |

## 5. 单点详情 `p.P0` 字段

`p.P0(String)` 成功分支读取：

```text
K6/readUTF       # 名称
L6/readShort     # 坐标 X
M6/readShort     # 坐标 Y
N6/readUTF       # 描述
x6/readInt       # 详情数值 1：产量/储量/状态候选
y6/readInt       # 详情数值 2：产量/储量/状态候选
count/readByte
repeat count:
  O6/readLong
  P6/readUTF
  S6/readByte
  Q6/readUTF
  R6/readByte
  T6/readByte
  V6/readByte
  if T6 >= 100: T6 -= 100; U6 = 1
```

当前判断：`O6..V6` 是详情页的驻守/守军条目数组，`T6>=100` 说明某个 byte 字段混入状态位。

## 6. 对服务端重建的影响

实现 `reqResourceList / 5442` 或同类目标列表时，服务端至少需要返回：

```text
id
type
name
x/y
country
bonus/talent pair
fief_current/fief_max
owner_name/owner_level
garrison_general_current/garrison_general_max
road_value
wall_value
famous_general_aid_chance
famous_general_count_min/max
reward_money
reward_food
reward_battle_credit
status/timers/extra fields
```

注意：`攻克奖励` 是预览显示；最终资源到账仍应由战斗/攻城结算接口服务端权威完成。

## 7. 当前边界

- `道路`、`城墙` 还需要动态样本确认它们究竟是等级、耐久、防御值还是别的积分值。
- `z5/B5/O5/P5`、`c6/e6/p6/q6` 仍未在主信息面板命名。
- `K5/L5`、`n6/o6` 的时间/状态语义仍需抓真实响应样本。
- `reqResourceList` 的中文业务名仍建议暂称“资源点/攻城目标/城池目标列表”，不要过早收窄成单一“资源点”。

## 8. 配套文件

- `resource_point_field_semantics.csv`：字段语义映射表。
- `resource_point_field_semantics_summary.json`：机器可读摘要。
- 证据方法：`method_disasm_storage/scriptPages_game_p__s__0x2fa374.smali.txt`、`method_disasm_storage/scriptPages_game_p__t__0x2fb3a8.smali.txt`、`method_disasm_resource_point/scriptPages_game_p__f__0x2f75f4.smali.txt`、`method_disasm_resource_point/scriptPages_game_p__c1__0x30d7c0.smali.txt`、`method_disasm_resource_point/scriptPages_game_p__P0__0x30cd34.smali.txt`。
