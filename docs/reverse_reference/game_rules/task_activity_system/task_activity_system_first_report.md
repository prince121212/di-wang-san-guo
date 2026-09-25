# 任务/活动系统第一版

## 1. 结论摘要

1. 客户端没有发现完整的“所有任务 ID -> 完成条件 -> 奖励”静态总表；任务/活动更像由服务端动态下发，客户端负责展示、点击领取、委派和同步奖励。
2. 普通任务/活动入口主要集中在 `scriptPages/game/m0` 与 `scriptPages/game/q0`：列表 UI、任务详情、任务奖励、活动任务点击等。
3. 六部任务是一条相对清晰的任务子系统：有任务列表/刷新、委派、领取奖励三类协议；委派奖励成功后会调用 `Lo/a.V5` 同步资产。
4. 日历/签到/活跃度系统集中在 `scriptPages/gameHD/a`：包含补签、累计签到、活跃奖励、个人/周/月活跃分等字段。
5. `scriptFreshman.sc` 不是任务完成条件表，更像新手/玩法说明脚本；文件头显示 68 个条目候选，已抽出 59 条可读文本，包含“活动任务”提示和新手攻略标题。

## 2. 关键协议入口

| 模块 | 请求 | 请求 opcode | 响应 opcode | handler | 关键字段 |
|---|---|---:|---:|---|---|
| 活动任务点击/领取 | `reqActivityTask` | `0x1136 / 4406` | `0x8136 / -32458` | `m0.y(String)` | `writeLong task/activity id`；响应先读 `status` |
| 六部任务委派 | `Req_libutaskDispatch` | `0x6342 / 25410` | `0xE342 / -7358` | `a0/a.C(String)` | `writeInt task_id + writeByte general_count + general_id[]` |
| 六部任务奖励 | `Req_libutaskAward` | `0x6343 / 25411` | `0xE343 / -7357` | `a0/a.B(String)` | `writeInt task_id`；成功后 `Lo/a.V5` |
| 六部任务列表/刷新候选 | `Req_libutaskList` | `0x6341? / 25409?` | `0xE341 / -7359` | `a0/a.D(String)` | 成功后 `a0/a.i(dis,1)` 读取列表 |
| 签到补签 | `buqian` | `0x6204 / 25092` | `0xE204 / -7676` | `gameHD/a.j(String)` | `writeShort day + writeByte flag/payment`；本地检查黄金 `>=10` |
| 活跃/累计签到奖励 | `leijijiangli` | `0x6206 / 25094` | `0xE206 / -7674` | `gameHD/a.i(String)` | 发送奖励档位 byte；失败读服务端 message |
| 日历/活跃主数据 | `reqActivityHD` 相关 | `0x6200?` | `0xE200 / -7680` | `gameHD/a.h(String)` | 读取个人活跃度、周/月活跃分、累计签到、活跃奖励等大量字段 |

## 3. 六部任务读写流

### 3.1 委派请求 `Req_libutaskDispatch`

```text
openDos("Req_libutaskDispatch")
writeInt task_id
writeByte general_count
for each selected general:
    writeLong general_id
send opcode 0x6342 / 25410
```

响应 `a0/a.C`：

```text
readByte status -> a0/a.di
readUTF message -> a0/a.ei
if status == 0:
    readInt task_id
    a0/a.h(task_id, idx, dis) 更新任务信息
    readInt state_or_time
    readByte count
    for each:
        readLong general_id
        readByte short_status
        Lo/a.F[general_index] = state_or_time
        Lo/a.x[general_index] = short_status
        Lo/a.c7(general_index)
```

### 3.2 奖励请求 `Req_libutaskAward`

```text
openDos("Req_libutaskAward")
writeInt task_id
send opcode 0x6343 / 25411
```

响应 `a0/a.B`：

```text
readByte status -> a0/a.gi
readUTF message -> a0/a.hi
if status >= 0:
    readInt task_id
    a0/a.j(dis, 1) 读取奖励/任务块
    readByte count
    for each:
        readLong general_id
        Lo/a.a0(general_id, dis) 更新将领状态
    清理 Lo/a.F 中匹配 task_id 的将领任务状态
    Lo/a.V5(dis) 复合同步资产
    readInt -> Lo/a.m
```

结论：六部任务奖励是明确的“任务完成 -> 奖励到账 -> 资产同步”链路，服务端重建时必须返回 `Lo/a.V5`。

## 4. 签到/活跃度系统

`gameHD/a.k()` 中存在两个明确发送动作：

```text
补签 buqian:
writeShort gameHD/a.u0  日期/天索引候选
writeByte  gameHD/a.v0  补签标记/支付标记候选
send opcode 0x6204 / 25092
```

```text
活跃/累计签到奖励 leijijiangli:
send byte 奖励档位/活跃门槛候选
send opcode 0x6206 / 25094
```

UI 文案和字段显示该模块包含：

- `di_个人活跃度`
- `di_周活跃分`
- `di_月活跃分`
- `di_活跃奖励`
- `di_累计签到`
- `di_24时前领取奖励`
- 补签消耗、补签日期合法性、本地黄金不足提示

## 5. 活动任务类型/配置名称候选

DEX 字符串中出现了多类活动任务配置名，说明服务端可能按任务模板/活动类型下发：

- `OnlineAwardTaskV166`：累计在线奖励
- `ConsmeGoldOrSilverSingleTaskV164` / `ConsmeGoldOrSilverMultipleTaskV164`：消耗黄金/白银任务候选
- `DeterministicExchangeTaskV164` / `RandomExchangeTaskV164`：确定/随机兑换任务候选
- `EquipStrongTaskV164`：装备强化任务候选
- `JifenExchangeTaskV164`：积分兑换任务候选
- `JiBaoPenTaskV164`、`ChargeSectionAward`、`ChargeGainOnceAward`、`ChargeGainRandomAward`、`DailyContinuousChargeTask` 等充值/聚宝盆/活动奖励候选

这些更像活动模板名，不是本地固定任务表。

## 6. 新手/玩法说明脚本

`scriptFreshman.sc`：

- 文件头 `0x0044`，即 68 个条目候选。
- 已抽取 59 条可读字符串。
- 前 13 条为玩法标题，例如：
  - 工欲善其事 必先利其器
  - 即时战斗 百人攻城
  - 群雄并立 万人国战
  - 升官进爵 建国称帝
  - 战场活动 天天竞技
  - 副本故事 引人入胜
- 多条说明文本指向“游戏中查阅相关活动任务的具体说明”。

结论：该脚本可用于新手引导/玩法说明还原，但不能作为任务奖励配置表。

## 7. 服务端重建建议

1. 任务系统初版应服务端动态配置：`task_id / title / desc / target / progress / status / award_list / guide_action`。
2. 普通活动任务支持 `reqActivityTask(0x1136)`，请求只需任务/活动 ID，服务端返回状态和详情/奖励块。
3. 六部任务单独建模：任务列表、刷新、委派将领、完成时间/成功率、领奖，领奖后按 `Lo/a.V5` 同步资产。
4. 签到/活跃单独建模：每日签到状态、补签成本、个人/周/月活跃分、活跃奖励档位、累计签到奖励。
5. 奖励到账统一走服务端权威，避免客户端本地相信“领取成功”。

## 8. 当前边界

- 普通任务详情响应 `m0.n` 与活动列表响应尚未完全拆字段。
- `reqActivityHD` 主数据请求入口和 `0x6200` 请求体仍需继续确认。
- 六部任务列表 `a0/a.i`、`a0/a.j` 内部任务字段还未逐字段命名。
- 活动模板的具体完成条件和奖励多由服务端下发，客户端未见完整静态总表。
