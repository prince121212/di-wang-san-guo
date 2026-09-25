# 人口/资源点/封地/将领上限字段第一版

- 样本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/三国·帝王联盟1.66.apk`
- Case：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166`
- 产出时间：2026-07-05
- 结论级别：字段同步与 UI 命名为高置信；上限生成公式仍待继续深追。

## 1. 总结

本轮把 `scriptPages/data/i` 中与人口、资源点、封地、将领容量相关的 6 个字段完成第一版命名：

| 字段 | 类型 | 命名 | 置信度 | 核心证据 |
|---|---:|---|---|---|
| `data.i.q` | long | 人口当前占用 | 高 | `i.x`/`i.b tag=6` 同步；`di_人口占用` 显示 `q/r`；征兵公式使用 `r-q` |
| `data.i.r` | long | 人口上限 | 高 | `i.x`/`i.b tag=7` 同步；`di_人口占用` 显示 `q/r`；征兵公式使用 `r-q` |
| `data.i.u` | int/readByte | 资源点当前占用/数量 | 高 | `i.x`/`i.b tag=13` 同步；首页 `di_标题资源点` 显示 `u/v` |
| `data.i.v` | byte | 资源点上限 | 高 | `i.x`/`i.b tag=14` 同步；首页 `di_标题资源点` 显示 `u/v` |
| `data.i.s` | int/readByte | 封地上限 | 高 | `i.x`/`i.b tag=8` 同步；首页 `di_标题封地` 显示 `Lo/a.s2().length / s`；`data.i.h()` 返回 `s` |
| `data.i.t` | int/readByte | 将领上限 | 高 | `i.x`/`i.b tag=9` 同步；`di_将领数` 显示 `Lo/a.M2(0).length / t`；`data.i.w()` 返回 `t` |

## 2. 协议同步链路

### 2.1 全量登录/角色同步：`LscriptPages/data/i;->x(String)V`

关键读流片段：

```text
0x0000e2 readLong -> data.i.q    # 人口当前占用
0x0000ee readLong -> data.i.r    # 人口上限
0x0000fa readByte -> data.i.s    # 封地上限
0x000106 readByte -> data.i.t    # 将领上限
0x000112 readByte -> data.i.u    # 资源点当前数量
0x00011e readByte -> data.i.v    # 资源点上限
```

证据文件：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/limits_deep/scriptPages_data_i__x__0x28bf60.smali.txt`

### 2.2 Tagged update：`LscriptPages/data/i;->b(String)V`

关键 tag：

| tag | 读类型 | 写入字段 | 语义 |
|---:|---|---|---|
| 6 | `readLong` | `data.i.q` | 人口当前占用 |
| 7 | `readLong` | `data.i.r` | 人口上限 |
| 8 | `readByte` | `data.i.s` | 封地上限 |
| 9 | `readByte` | `data.i.t` | 将领上限 |
| 13 | `readByte` | `data.i.u` | 资源点当前数量 |
| 14 | `readByte` | `data.i.v` | 资源点上限 |

证据文件：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/limits_deep/scriptPages_data_i__b__0x28bcfc.smali.txt`

### 2.3 资源/人口短同步：`LscriptPages/data/i;->z(String)V`

该方法同步：`data.i.d/e/m/n/q/r` 与 `data.g.F/G`，说明 `q/r` 不只在登录时出现，还会在资源类短响应中刷新。

```text
readLong -> data.i.d  # 铜钱
readLong -> data.i.e  # 粮食
readInt  -> data.i.m
readInt  -> data.i.n
readLong -> data.i.q  # 人口当前占用
readLong -> data.i.r  # 人口上限
readLong -> data.g.F  # 黄金
readLong -> data.g.G  # 白银
```

证据文件：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/limits_deep/scriptPages_data_i__z__0x28c230.smali.txt`

## 3. UI 证据

### 3.1 人口占用 `q/r`

`scriptPages/game/q.u()` 使用文案 `di_人口占用`，随后拼接 `data.i.q + "/" + data.i.r`。

证据文件：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/limits_deep/scriptPages_game_q__u__0x318484.smali.txt`

### 3.2 首页资源点 `u/v`

`scriptPages/game/k0.o()` 在 `di_标题资源点` 区域拼接 `data.i.u + "/" + data.i.v`。

证据文件：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/limits_deep/scriptPages_game_k0__o__0x3c7b14.smali.txt`

### 3.3 首页封地上限 `当前封地数/s`

`scriptPages/game/k0.o()` 在 `di_标题封地` 区域读取 `Lo/a.s2().length` 作为当前封地数量，并拼接 `data.i.s` 作为封地上限。

证据文件：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/limits_deep/scriptPages_game_k0__o__0x3c7b14.smali.txt`

### 3.4 将领数 `当前将领数/t`

`scriptPages/game/z.o()` 在 `di_将领数` 区域读取 `Lo/a.M2(0).length`，并拼接 `data.i.t`。
`scriptPages/game/k0.o()`、`gameHD/k.l` 等页面也引用 `data.i.t`。

证据文件：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/limits_deep/scriptPages_game_z__o__0x3618f8.smali.txt`

## 4. 已恢复公式：征兵可招数量

`scriptPages/data/g.z0(I,I)` 与征兵界面 `scriptPages/game/q.p0()` 均使用同一类约束：铜钱、粮食、剩余人口三者取最小值。

```text
coin_cap = floor(data.i.d / (g.Q1(soldierType) * multiplier))
food_cap = floor(data.i.e / (g.R1(soldierType) * multiplier))
pop_cap  = floor((data.i.r - data.i.q) / g.S1(soldierType))

可招数量 = max(0, min(coin_cap, food_cap, pop_cap))
```

其中：

```text
multiplier = 1  when mode/second_arg == 0
multiplier = 2  otherwise
```

含义：

- `g.Q1(soldierType)`：单兵铜钱成本候选。
- `g.R1(soldierType)`：单兵粮食成本候选。
- `g.S1(soldierType)`：单兵人口占用候选。
- `data.i.r - data.i.q`：剩余可用人口。

证据文件：

- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/limits_deep/scriptPages_data_g__z0__0x264cb4.smali.txt`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/limits_deep/scriptPages_game_q__p0__0x323e50.smali.txt`

## 5. 对重建服务端的影响

1. 服务端初版必须保存并同步角色级 `population_used/population_cap`，否则征兵界面的可招数量会异常。
2. `resource_point_used/resource_point_cap`、`fief_cap`、`general_cap` 是角色级容量字段，登录、升级、领取奖励、占领/放弃资源点、获得扩展道具后都应同步。
3. `data.i.s/t/u/v` 在客户端按 byte 读取或 byte 后存 int，服务端编码时要保持原协议宽度。
4. `Lo/a.P1(fief,0)` 是封地局部人口上限/房屋人口效果，不等于全局 `data.i.r`；重建时不要把单个封地人口容量直接当成账号总人口上限。

## 6. 当前边界与下一步

- 人口上限 `data.i.r` 的生成公式尚未闭环：建筑人口、科技、称号、官职/VIP/道具等叠加仍待继续。
- 封地上限 `data.i.s` 与君主等级/声望/官职的具体数值表仍待继续。
- 将领上限 `data.i.t` 的扩展空位、道具、官职/VIP 叠加仍待继续。
- 资源点上限 `data.i.v` 的生成公式和占领/放弃协议响应仍待动态样本验证。

结构化产物：

- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/limits_deep/limit_field_mapping.csv`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/limits_deep/limit_formula_summary.json`
