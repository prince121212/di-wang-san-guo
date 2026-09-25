# 道路 / 城墙公式深追第一版

- 日期：2026-07-05
- 目标：恢复修墙/修路换算、道路值作用、城墙值作用，以及修筑请求协议。

## 1. 结论摘要

1. `road_value`：道路值。文本明确“道路值越高，军队行动速度越快”；另有提示“道路不通，无法阻击”。
2. `wall_value`：城墙/城防值。文本明确“城防越高，驻防部队战斗力越高”；攻城/城主竞选/抢城活动中，破坏城墙可获得积分。
3. 修墙换算已确认：
   - `60 粮食 = 1 点城墙`
   - `1 黄金 = 1000 点城墙`
4. 修路换算已确认：
   - `300 粮食 = 1 点道路`
   - `1 黄金 = 500 点道路`
5. 修筑确认文案中的贡献值显示公式已恢复：
   - 粮食修墙：`min(floor(输入粮食 / 3000), b1)`
   - 黄金修墙：`min(输入黄金 * 20, b1)`
   - 粮食修路：`min(floor(输入粮食 / 3000), d1)`
   - 黄金修路：`min(输入黄金 * 50, d1)`
   其中 `b1/d1` 是当日修墙/修路贡献剩余额度候选。
6. 修筑请求协议已定位：`LscriptPages/game/k;->i1(J,String,int,int,long)V` 复用请求名 `reqCityGarrisonList`，opcode `4868 / 0x1304`。

## 2. 文本规则证据

来自 `sentence_rule_hits.md`：

```text
#208 di_说明修墙
修筑城墙能提高城池的防御值;城池防御值越高,驻防在里面的部队战斗力越高.

#209 di_说明修路
修筑道路能提高城池道路值;道路值越高,军队行动速度越快.

#211 di_粮食修墙
使用粮食修筑城墙。60粮食可以修筑1点城墙

#213 di_粮食修路
使用粮食修筑道路。300粮食可以修筑1点道路

#216 di_黄金修墙
使用黄金修筑城墙。1点黄金可以修筑1000点城墙

#217 di_黄金修路
使用黄金修筑道路。1点黄金可以修筑500点道路

#683 di_提示道路阻击
您出征封地所在的城池与受攻击的城池道路不通,无法阻击
```

## 3. 修墙/修路输入上限逻辑

关键方法：`scriptPages/game/k;->d()V`

### 3.1 粮食修墙

客户端显示当前/上限来自 `k.Y0[0]/k.Y0[1]`。

```text
wall_gap = Y0[1] - Y0[0]
max_food_input = min(data.i.e, wall_gap * 60)
```

若 `wall_gap <= 0`，提示 `di_提示城墙最大`。

### 3.2 粮食修路

客户端显示当前/上限来自 `k.Z0[0]/k.Z0[1]`。

```text
road_gap = Z0[1] - Z0[0]
max_food_input = min(data.i.e, road_gap * 300)
```

若 `road_gap <= 0`，提示 `di_道路最大`。

### 3.3 黄金修墙

```text
wall_gap = Y0[1] - Y0[0]
max_gold_input = min(data.g.F, ceil(wall_gap / 1000))
```

客户端实现方式是 `gap / 1000`，如果结果为 0 且余数大于 0，则至少允许输入 1 黄金。

### 3.4 黄金修路

```text
road_gap = Z0[1] - Z0[0]
max_gold_input = min(data.g.F, ceil(road_gap / 500))
```

同样采用接近 `ceil` 的处理：不足 500 点道路缺口时也需要 1 黄金。

## 4. 确认文案中的实际换算和贡献显示

关键方法：`scriptPages/game/k;->D1()I`

`D1` 会在用户输入数量后，根据 `k.i1` 操作类型、`k.x1` 资源类型、`k.y1` 输入数量生成确认文案。

| 操作 | 资源 | 修筑值显示 | 贡献值显示 |
|---|---|---:|---:|
| 修墙 | 粮食 | `floor(y1 / 60)` 城墙 | `min(floor(y1 / 3000), b1)` |
| 修墙 | 黄金 | `y1 * 1000` 城墙 | `min(y1 * 20, b1)` |
| 修路 | 粮食 | `floor(y1 / 300)` 道路 | `min(floor(y1 / 3000), d1)` |
| 修路 | 黄金 | `y1 * 500` 道路 | `min(y1 * 50, d1)` |

说明：

- `y1` 是用户输入的资源数量，可能是粮食数量，也可能是黄金数量。
- `b1` 是修墙贡献剩余额度候选。
- `d1` 是修路贡献剩余额度候选。
- 这些是客户端确认文案显示公式，最终扣资源、加道路/城墙、加贡献仍应由服务端权威决定。

## 5. 修筑请求协议

关键方法：`scriptPages/game/k;->i1(J,String,int,int,long)V`

读流/写流：

```text
openDos("reqCityGarrisonList")
writeByte(0)
writeLong(city_id)
writeByte(repair_type)
writeByte(currency_type)
writeLong(amount)
Lo/a.d0(4868, data)
```

字段含义：

| 字段 | 类型 | 含义 |
|---|---|---|
| constant | byte | 固定 0 |
| city_id | long | 城池 ID，来自 `k.X0` |
| repair_type | byte | `1=修墙`、`2=修路`、`3=修塔候选` |
| currency_type | byte | `0=粮食`、`1=黄金` |
| amount | long | 输入资源数量，粮食数量或黄金数量 |
| opcode | short | `4868 / 0x1304` |

`D1` 确认后调用：

```text
k.i1(k.X0, null, repair_type, k.x1, k.y1)
```

其中：

```text
k.x1 = 0 -> 粮食
k.x1 = 1 -> 黄金
repair_type = 1 -> 修墙
repair_type = 2 -> 修路
repair_type = 3 -> 修塔候选
```

## 6. 对服务端重建的影响

服务端应实现：

1. 城池字段：
   - `road_value`
   - `road_max`
   - `wall_value`
   - `wall_max`
2. 修筑接口：
   - 接收 `city_id / repair_type / currency_type / amount`
   - 按服务端权威检查资源、上限、权限和贡献上限
   - 扣除资源
   - 增加道路/城墙值
   - 增加贡献
   - 下发新的城市状态、资源状态、贡献状态
3. 初版公式：
   - `food_wall_delta = floor(food_amount / 60)`
   - `gold_wall_delta = gold_amount * 1000`
   - `food_road_delta = floor(food_amount / 300)`
   - `gold_road_delta = gold_amount * 500`
   - 结果应截断到剩余上限。
4. 行军/战斗层：
   - 道路值影响军队行动速度，但精确公式未恢复。
   - 城防影响驻防部队战斗力，但精确加成未恢复。

## 7. 当前边界

- 道路值到行军时间/速度的精确公式仍未恢复。
- 城墙/城防值到驻防部队战斗力加成公式仍未恢复。
- 修筑成功响应如何同步资源、贡献、道路/城墙字段还需继续追响应读取器。
- 修塔规则本轮只作为同一 UI 分支识别，未完整整理。
