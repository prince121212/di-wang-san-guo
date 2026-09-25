# data.g.H 最终命名与玉石区分报告

- 日期：2026-07-05
- 目标：确认 `scriptPages/data/g.H` 到底是玉石、扩展货币，还是其他资源字段。

## 1. 结论摘要

`scriptPages/data/g.H` 可以从“玉石/扩展货币候选”修正为：**账号积分**。

关键证据链：

```text
g.<clinit> 初始化 f8 资源名表：第 14 项 = 账号积分
g.v0(I) 对负数资源 ID 返回 f8[abs(id)-1]
g.w0(I) 对 -14 返回 data.g.H
=> data.g.H = resource_id -14 = 账号积分数量
```

同时需要明确区分：

- `data.g.H`：账号积分，全局 long 字段，负数资源 ID `-14`。
- `玉石`：道具表中的普通/功能道具，`item_id=399`。

此前资源系统报告里把 `data.g.H` 标成“玉石/扩展货币候选”，现在应修正为“账号积分”。

## 2. 负数资源 ID 修正映射

| 资源 ID | 显示名 | 数量字段 |
|---:|---|---|
| -1 | 铜钱 | `data.i.d` |
| -2 | 粮食 | `data.i.e` |
| -3 | 白银 | `data.g.G` |
| -4 | 黄金 | `data.g.F` |
| -5 | 声望 | `data.i.i` |
| -6 | 战功 | `data.i.o` |
| -7 | 将领经验 | 保留/另追 |
| -8 | 基地预备兵 | 保留/另追 |
| -9 | 荣誉值 | 保留/另追 |
| -10 | 竞技币 | 保留/另追 |
| -11 | 俸禄 | 保留/另追 |
| -12 | 战法经验点 | 保留/另追 |
| -13 | 战法谋略值 | 保留/另追 |
| -14 | 账号积分 | `data.g.H` |

## 3. 关键反汇编证据

### 3.1 名称表 `g.f8`

`LscriptPages/data/g;-><clinit>` 初始化资源名：

```text
铜钱、粮食、白银、黄金、声望、战功、将领经验、基地预备兵、荣誉值、竞技币、俸禄、战法经验点、战法谋略值、账号积分
```

### 3.2 名称解析 `g.v0(I)`

`LscriptPages/data/g;->v0(I)`：

```text
if id < 0 and abs(id) <= 14:
    return f8[abs(id)-1]
```

所以：

```text
v0(-14) = f8[13] = 账号积分
```

### 3.3 数量解析 `g.w0(I)`

`LscriptPages/data/g;->w0(I)`：

```text
-1  -> data.i.d
-2  -> data.i.e
-3  -> data.g.G
-4  -> data.g.F
-5  -> data.i.i
-6  -> data.i.o
-14 -> data.g.H
```

所以：

```text
w0(-14) = data.g.H = 账号积分数量
```

## 4. 玉石不是 data.g.H

道具表中存在：

```text
item_id=399
name=玉石
type=普通/功能道具
desc=价值连城，用途广泛，可用于科技升级、将领空位激活、装备炼魂、六部系统使用和帅府系统使用等。
```

客户端也确实有大量玉石 UI：

- `di_玉石`
- `玉石或黄金`
- `使用玉石`
- `di_需要玉石`
- `di_玉石兑换`
- `res_解锁帅位玉石提示`

但这些字符串没有直接引用 `data.g.H`。因此不能把这些“玉石”文案作为 `H=玉石` 的证据。更准确的建模是：

- 玉石作为 `item_id=399` 道具保存/消耗。
- 账号积分作为 `resource_id=-14` / `data.g.H` 保存/同步。

## 5. 对服务端重建的影响

服务端资源模型建议修正为：

```text
coin        -> data.i.d / resource -1
food        -> data.i.e / resource -2
silver      -> data.g.G / resource -3
gold        -> data.g.F / resource -4
prestige    -> data.i.i / resource -5
war_merit   -> data.i.o / resource -6
account_pts -> data.g.H / resource -14
jade_item   -> item_id 399 inventory item
```

不要把 `data.g.H` 当成玉石余额；玉石应走背包道具/物品系统。

## 6. 当前边界

- 账号积分的具体获取、消耗、活动入口还没有完整恢复。
- 玉石 `item_id=399` 的具体消耗协议分布在科技升级、将领空位、装备炼魂、六部、帅府等模块，后续需要分模块继续整理。
