# 玉石消耗响应与背包同步第一版

- 案例目录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166`
- 主题：确认玉石消耗相关入口在响应阶段如何同步资源、背包/道具列表、复合同步块和错误状态。

## 1. 结论摘要

1. `玉石` 继续按 `item_id=399` 道具建模；`data.g.H/resource_id=-14` 是账号积分，不能混用。
2. 帅府帅位解锁 `0x6406 -> 0xE406 -> Lv/a.e` 是最清晰的道具扣减同步样本：响应读 `status/message/latest_gold` 后调用 `data.g.f(dis)` 同步完整道具列表。
3. 装备炼魂 `0x6280 -> 0xE280 -> data.g.r4` 和科技取消成功 `0x1244 -> 0x8244 -> q.X1` 会调用 `Lo/a.V5(dis)`；`Lo/a.V5` 起始同步黄金/白银，但它是装备/封地/建筑等复合同步块，不是单纯背包列表。
4. 科技升级 `0x123F -> 0x823F -> q.Y1` 本方法内只同步 `status/message + data.g.m0` 科技状态，未见玉石/背包同步。
5. 六部升级 `0x6302 -> 0xE302 -> a0/a.s` 只有特定部门分支调用 `Lo/a.V5`；错误状态主要保存服务端 `status/message`，本地无完整错误码表。

## 2. 请求/响应 dispatcher 映射

| 模块 | 请求 opcode | 响应 opcode | handler | 同步特征 |
|---|---:|---:|---|---|
| 科技升级 | `0x123F / 4671` | `0x823F / -32193` | `LscriptPages/game/q;->Y1(String)` | `data.g.m0` 科技状态；无明确背包同步 |
| 科技取消 | `0x1244 / 4676` | `0x8244 / -32188` | `LscriptPages/game/q;->X1(String)` | 成功分支 `Lo/a.V5` + 铜钱/粮食 + `data.g.m0` |
| 装备炼魂 | `0x6280 / 25216` | `0xE280 / -7552` | `LscriptPages/data/g;->r4(String)` | 固定 `Lo/a.V5`，末尾可选 `Lo/a.a6` |
| 六部/部门升级 | `0x6302 / 25346` | `0xE302 / -7422` | `La0/a;->s(String)` | 部门状态；特定分支 `Lo/a.V5` |
| 帅府帅位解锁 | `0x6406 / 25606` | `0xE406 / -7162` | `Lv/a;->e(String)` | `data.g.F` 黄金 + `data.g.f` 道具列表 |

## 3. 关键响应读流

### 3.1 科技升级 `q.Y1`

```text
readByte status
readUTF message
data.g.m0(dis)
if status == 0: r0.w = false
else: r0.a0(message, 1)
```

`data.g.m0` 读取科技单项状态：

```text
readByte tech_index/id
readByte -> g.f1[index]
readByte -> g.g1[index]
readLong -> g.h1[index]
readLong -> g.i1[index]
readLong -> g.j1[index]
```

边界：本响应内未见 `Lo/a.V5` 或 `data.g.f`，因此不能据此断言科技升级响应直接同步玉石扣减。

### 3.2 科技取消 `q.X1`

```text
readByte status
if status == -3:
    Lo/a.Z5(dis)
    data.b.L(dis)
elif status == -4:
    readLong
    Lo/a.j1(long, dis)
elif status == 0:
    Lo/a.V5(dis)
    readLong -> data.i.d 铜钱
    readLong -> data.i.e 粮食
if status != -5:
    data.g.m0(dis)
刷新 q.V0()
```

成功分支存在明确复合同步块，并追加铜钱/粮食。

### 3.3 装备炼魂 `data.g.r4`

```text
getCurTime -> data.g.d9
readInt
readUTF -> data.g.e9
readLong -> equip/general id 候选
readUTF -> text
data.d.y(id) 定位装备
更新 data.d.l[n][o] = text
Lo/a.V5(dis)
readLong
if readLong >= 0:
    Lo/a.a6(0, dis)
```

结论：炼魂响应会同步复合资产块；适合作为装备/资产变更后的服务端回包模板。

### 3.4 六部/部门升级 `a0/a.s`

```text
readByte status -> a0/a.Hh
readUTF message -> a0/a.Ih
if status == 0:
    readByte department_id
    Lo/a.t(department_id) -> idx
    readByte -> Lo/a.c[idx]  部门等级/状态
    readInt timer
    if timer > 0: Lo/a.h[idx] = now/1000 + timer
    else: Lo/a.h[idx] = 0
    if current department:
        readShort -> Lo/a.o
        根据部门类型刷新状态
        if department == Lo/a.k0: Lo/a.X8(dis)
        if department == Lo/a.m0:
            readByte -> Lo/a.T0
            Lo/a.V5(dis)
```

结论：部门升级响应不是固定资产同步；服务端要按部门类型决定附加块。

### 3.5 帅府帅位解锁 `v/a.e`

```text
readByte status
readUTF message
readLong -> data.g.F 黄金
Lv/a.K1 = status
Lv/a.J1 = 1
if status < 0:
    show message
    r0.w = false
data.g.f(dis)
```

`data.g.f` 是明确的道具/背包列表同步：

```text
readInt count
for each item:
    readLong  -> data.g.x[i]  道具实例/唯一 ID 候选
    readShort -> data.g.y[i]  item_id
    readBoolean -> data.g.z[i] 标记位
```

## 4. 通用同步块边界

### `Lo/a.V5(dis)`

开头字段：

```text
readLong -> data.g.F 黄金
readLong -> data.g.G 白银
readShort count
for each:
    readShort -> Lo/a.bv[i]
    readShort -> Lo/a.cv[i]
    readLong  -> Lo/a.dv[i]
...后续为装备/封地/建筑等复杂结构...
```

注意：`Lo/a.V5` 不是“背包同步”的同义词。它是复合同步块，后续仍要单独拆字段。

### `data.g.f(dis)`

这是当前最明确的道具/背包列表同步块，玉石 `item_id=399` 应从这个资产模型下发。

## 5. 服务端重建建议

1. 资产模型分开：
   - `account_points = data.g.H / resource_id=-14`
   - `jade = item_id=399` 道具/背包资产
2. 玉石消耗接口必须服务端权威校验：余额、支付模式、消耗数量、道具存在性、重放/幂等。
3. 回包要严格匹配客户端 handler：
   - 帅府解锁：`status/message/gold/data.g.f`
   - 装备炼魂：结果字段 + `Lo/a.V5` + 可选扩展
   - 科技取消：按 `status` 分支返回 `Lo/a.V5`/封地块/科技状态
   - 科技升级：至少返回 `data.g.m0` 科技状态；玉石扣减同步要通过后续刷新或补充兼容链路验证
   - 六部升级：按部门类型返回不同附加块，不要一律发送 `Lo/a.V5`

## 6. 仍需继续确认

- `payment_mode` 精确枚举：尤其六部、帅府中 `1/2` 对应玉石还是黄金。
- 科技升级成功后玉石数量如何刷新：本响应未见 `data.g.f/Lo/a.V5`。
- 文官刷新/恢复健康、战法残页兑换的最终请求入口和响应 handler。
- `Lo/a.V5` 复合同步块字段细命名。

## 7. 产物

- `jade_response_sync_mapping.csv`：响应 handler、读流、同步块、错误状态、重建建议表。
- `jade_response_sync_summary.json`：机器可读汇总。
- `method_disasm/`：关键 handler 反汇编证据。
