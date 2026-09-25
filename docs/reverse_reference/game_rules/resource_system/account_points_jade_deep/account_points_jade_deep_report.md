# 账号积分与玉石入口深追第一版

- 样本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/三国·帝王联盟1.66.apk`
- Case：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166`
- 产出时间：2026-07-05

## 1. 总结

本轮继续区分两类容易混淆的资产：

```text
账号积分 = resource_id -14 = data.g.H = long 资源余额
玉石     = item_id 399 = 背包道具/功能道具
```

结论：两者不是同一个资产。服务端重建时必须拆成两套模型：

```text
account_points -> player/account resource balance -> data.g.H / resource_id=-14
jade_item      -> inventory item quantity          -> item_id=399
```

## 2. 账号积分：入口与边界

### 2.1 已确认身份

证据链仍然成立：

```text
g.<clinit>: f8[13] = 账号积分
g.v0(-14) = 账号积分
g.w0(-14) = data.g.H
```

### 2.2 已确认同步链

| 场景 | 方法 | 证据 | 置信度 |
|---|---|---|---|
| 登录/全量资源同步 | `scriptPages/data/i.b` | `readLong -> data.g.H` | 高 |
| 奖励领取成功 | `scriptPages/game/m0.u` | 成功后同步 `i.i/i.d/i.e/data.g.H/Lo.a.V5` | 中高 |
| 六部/部门响应 | `La0/a.c2` | 成功响应同步 `data.g.H` | 中 |

### 2.3 活动奖励候选：累计消费奖励列表

`Lo/a.w5()` 中出现：

```text
resource_id = -14
panel = "consumptionExpend_awardList"
```

它把某些活动奖励数量包装成 `resource_id=-14` 的奖励项，因此可解释为“累计消费/活动奖励可展示或发放账号积分”的候选。

证据文件：

- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/account_points_jade_deep/method_disasm/o_a__w5__0x23bac0.smali.txt`

当前边界：尚未发现“账号积分专用消耗请求”。它更多是走通用负数资源 ID 和奖励同步体系。

## 3. 玉石：来源与消耗入口

### 3.1 道具表身份

`item_full_mapping.csv` 已确认：

```text
item_id=399
name=玉石
type=普通/功能道具
desc=价值连城，用途广泛，可用于科技升级、将领空位激活、装备炼魂、六部系统使用和帅府系统使用等。
```

### 3.2 已确认礼包来源

固定礼包/宝箱奖励中已看到玉石：

| item_id | 礼包名 | 玉石奖励 |
|---:|---|---:|
| 442 | 年货 | 玉石 * 6 |
| 445 | 礼盒 | 玉石 * 66 |
| 739 | 糖果 | 玉石 * 10 |
| 740 | 粽子 | 玉石 * 10 |
| 741 | 西瓜 | 玉石 * 10 |
| 742 | 饺子 | 玉石 * 10 |

## 4. 玉石消耗/使用入口第一版

| 模块 | 方法 | 请求/opcode | 当前结论 | 置信度 |
|---|---|---|---|---|
| 科技升级 | `q.A/q.L1/q.W1` | `techResearch` `4671 / 0x123F` | UI 显示 `di_需要玉石`、`re_提示升级玉石消耗`；请求体含支付/模式 byte | 中高 |
| 六部/部门升级 | `La0/a.H` | `ReqInternalLevelUp` `25346 / 0x6302` | 可选择玉石或黄金，写入 `department_id byte + payment_mode byte` | 中高 |
| 装备炼魂 | `scriptPages/data/g.N4` | `REQ_GENERAL_EQUIP_LIANHUN` `25216 / 0x6280` | 高级炼魂/锁定属性场景；请求写 general/equip/mode/锁定 flags；消耗由服务端按模式判定 | 中 |
| 帅府帅位解锁 | `Lv/a.b1` | `REQ_SHUAIFU_ADD_SHUAI_MAX` `25606 / 0x6406` | 弹出“使用玉石/使用黄金”，发送支付模式 byte | 中高 |
| 文官刷新/恢复健康 | `gameHD/k.V`, `a0.t0` | 待追 | UI 读取 `item_id=399` 数量/价格，属于玉石消耗候选 | 中 |
| 战法残页兑换 | `q0.O` | 待追 | `di_玉石兑换`、`di_使用玉石兑换残页`，属于玉石兑换残页候选 | 中 |

### 4.1 科技升级请求

`q.W1(J,I,I,I,I,I)`：

```text
openDos("techResearch")
writeLong(...)
writeByte(...)
writeShort(...)
writeByte(...)
writeByte(...)
send opcode 4671 / 0x123F with final byte
```

证据：

- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/account_points_jade_deep/method_disasm/scriptPages_game_q__A__0x31b060.smali.txt`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/account_points_jade_deep/method_disasm/scriptPages_game_q__L1__0x314e60.smali.txt`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/account_points_jade_deep/method_disasm/scriptPages_game_q__W1__0x32ab30.smali.txt`

### 4.2 六部/部门升级请求

`La0/a.H()`：

```text
openDos("ReqInternalLevelUp")
writeByte(department_id)
writeByte(payment_mode)
send opcode 25346 / 0x6302
```

UI 文案明确：`di_玉石`、`di_黄金`、`玉石或黄金`、`re_是否消耗黄金或玉石升级部门`。

证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/account_points_jade_deep/method_disasm/a0_a__H__0xc2a10.smali.txt`

### 4.3 装备炼魂请求

`scriptPages/data/g.N4()`：

```text
openDos("REQ_GENERAL_EQUIP_LIANHUN")
writeLong(general_id)
writeLong(equip_id)
writeByte(mode)
writeByte(lock_count)
for each lock flag:
    writeBoolean(flag)
send opcode 25216 / 0x6280
```

证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/account_points_jade_deep/method_disasm/scriptPages_data_g__N4__0x2684cc.smali.txt`

### 4.4 帅府帅位解锁请求

`Lv/a.b1()`：

```text
buttons: unlockCommanderUseYushi / unlockCommanderUseGold / 返回
request: REQ_SHUAIFU_ADD_SHUAI_MAX
opcode: 25606 / 0x6406
payment_mode: byte 候选
```

证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/account_points_jade_deep/method_disasm/v_a__b1__0x4631a0.smali.txt`

## 5. 对服务端重建的影响

1. `data.g.H` 和 `item_id=399` 必须分开。账号积分走资源余额；玉石走背包道具数量。
2. 玉石扣减应发生在服务端，客户端只提交业务请求和支付模式，不可信任客户端本地数量判断。
3. 科技升级、部门升级、炼魂、帅府扩展、文官刷新/恢复健康、残页兑换都应检查玉石余额或对应背包数量。
4. 成功响应应同步背包/资源状态，否则客户端 UI 会显示旧数量。
5. `账号积分` 可作为奖励系统的 `resource_id=-14` 发放项；初版服务端奖励配置表应支持负数资源 ID 发放。

## 6. 当前边界

- 六部/部门升级 `payment_mode` 的 `1/2` 精确对应玉石或黄金，还需要动态样本验证。
- 科技升级 `q.W1` 后几个 byte 的业务名仍需结合响应和 UI 状态命名。
- 文官刷新/恢复健康、战法残页兑换的最终发送入口还需继续追状态机。
- 玉石扣减后的背包同步字段需要结合抓包响应样本确认。

## 7. 结构化产物

- `account_points_jade_entry_mapping.csv`
- `account_points_jade_summary.json`
- `account_points_jade_candidate_methods.csv/json`
- `account_points_jade_disasm_summary.json`
- `method_disasm/`
