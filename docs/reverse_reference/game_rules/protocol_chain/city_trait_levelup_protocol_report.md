# reqCityTraitLevelUp / 城池特性升级协议字段报告

生成时间：2026-07-05T07:40:50

## 1. 结论摘要

- `reqCityTraitLevelUp` 是“城池特性/天赋升级”接口，不是普通封地建筑建造/升级接口。
- 请求 opcode：`0x1324`，十进制 `4900`。
- 请求入口：`LscriptPages/game/k0;->c0()I`。
- 响应 opcode：`0x8324`，dispatcher 中以 signed short `-31964` 出现，由 `Lo/a;->A6` 分发到 `LscriptPages/game/k;->d1(String)`。
- 成功时 `k.d1` 调用 `LscriptPages/game/k;->m1(String)` 同步城池数据字段到 `data.b`。
- 请求只提交目标城池标识，不提交资源扣除数量或升级后数值；升级结果和资源/状态变化由服务端响应决定。

## 2. 请求格式

| 顺序 | 字段 | 类型 | 证据 | 含义 |
|---:|---|---|---|---|
| 1 | `target_selector` | `byte` | `k0.c0 000cc0-000cd8` | 城池名非空写 1，否则写 0 |
| 2a | `city_name` | `UTF` | `k0.c0 000cc4-000cca` | selector=1 时写入，来源 `k0.Y` 或 `k.i` |
| 2b | `city_id` | `long` | `k0.c0 000cd2-000cd8` | selector=0 时写入，来源 `k0.T` 或 `k.h` |
| send | `opcode` | `short` | `k0.c0 000cde-000ce2` | `0x1324 / 4900` |

请求前客户端 UI 会取 `data.b.A[city]` 与 `data.i.d` 做比较，不足时本地提示资源不足；但这只是前置提示，真正扣费/升级仍由服务端确认。

## 3. 响应格式：`0x8324 -> k.d1(String)`

| 顺序 | 字段 | 类型 | 证据 | 含义 |
|---:|---|---|---|---|
| 1 | `status_outer` | `byte` | `k.d1 000000-000008` | 外层状态；当前逻辑在非 0 时继续读取业务结果 |
| 2 | `result_code` | `byte` | `k.d1 000012-00001e` | 业务结果码；0 成功，负数为错误 |
| 3 | `success_sync` | nested | `k.d1 000022 -> k.m1(String)` | result_code==0 时读取城池特性同步块 |

### 3.1 成功同步块：`k.m1(String)`

| 顺序 | 字段 | 类型 | 写入缓存 | 证据 | 含义 |
|---:|---|---|---|---|---|
| 3.1 | `city_id` | `long` | lookup key | `k.m1 000000-000010` | 要更新的城池 ID |
| 3.2 | `trait_level_or_flag_z` | `byte` | `data.b.z[index]` | `k.m1 000008-000022` | 城池特性/天赋等级或状态候选 |
| 3.3 | `resource_or_cost_A` | `int` | `data.b.A[index]` | `k.m1 000026-00003e` | UI 请求前用其与玩家数值比较，疑似下级需求/当前特性数值 |
| 3.4 | `metric_B` | `int` | `data.b.B[index]` | `k.m1 000042-00005a` | 城池特性相关数值 |
| 3.5 | `metric_C` | `int` | `data.b.C[index]` | `k.m1 00005e-000076` | 城池特性相关数值 |
| 3.6 | `remaining_seconds_or_cooldown` | `int` | `data.b.D[index]=now+value` | `k.m1 00007a-00009e` | 剩余时间/冷却/到期时间偏移 |
| 3.7 | `state_k` | `byte` | `data.b.k[index]` | `k.m1 0000a2-0000ba` | 城池状态 byte |
| 3.8 | `short_m` | `int -> short` | `data.b.m[index]` | `k.m1 0000be-0000d8` | 读取 int 后转 short 保存 |

### 3.2 错误码

| result_code | 文案/含义 | 证据 |
|---:|---|---|
| 0 | 请求成功，并调用 `k.m1` 同步城池数据 | `k.d1 00001e-000038` |
| -4 | 铜钱不足 | `k.d1 00003e-000052` |
| -5 | 粮食不够 | `k.d1 000056-00006a` |
| -1 | 天赋升级相关错误/条件不满足候选 | `k.d1 00006e-000082` |
| -2 | 天赋已达最大值 | `k.d1 000086-00009a` |
| -3 | 其他错误 | `k.d1 00009e-0000b2` |

## 4. 与普通建筑升级的边界

本次确认的 `reqCityTraitLevelUp` 属于城池特性/天赋升级。DEX 字符串中没有直接发现 `reqBuildingLevelUp`、`reqBuildLevelUp` 这类直观请求名；普通封地建筑建造/升级可能：

1. 复用封地信息/城池封地列表类协议；
2. 由脚本动作或动态数据数组发送；
3. 使用非直观命名的 opcode。

因此普通建筑建造/升级仍需继续追 `reqFiefInfo / reqCityFiefList / reqApplyFief` 及封地 UI 控制流。

## 5. 服务端重建含义

- 服务端需要按目标城池 ID/名称校验归属、资源是否足够、特性是否可升级、是否已达最大值。
- 成功后返回 `k.m1` 同步块，更新城池特性等级/状态、下一级需求/数值和冷却时间。
- 客户端本地资源检查不能作为安全依据，服务端必须重新计算并扣费。

## 6. 产物

- 请求字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/city_trait_levelup_request_fields.csv`
- 响应字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/city_trait_levelup_response_fields.csv`
- JSON 汇总：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/city_trait_levelup_protocol_summary.json`
- 反汇编目录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_city_trait`
