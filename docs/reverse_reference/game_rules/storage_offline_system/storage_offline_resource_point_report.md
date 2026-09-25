# 仓储 / 离线产出 / 资源点系统第一版报告

- 日期：2026-07-05
- 样本：三国·帝王联盟 1.66 APK
- 目录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/storage_offline_system`
- 本轮目标：在已确认资源字段基础上，继续追查“个人仓储上限、离线产出、资源点储量/产量”三类规则，并给服务端重建提供字段骨架。

## 1. 结论摘要

1. **个人铜钱/粮食仓储上限：客户端未恢复到明确闭环。** 当前扫描没有发现类似“铜钱上限/粮食上限/个人仓库容量”的稳定字段、同步块或本地 clamp 公式。`仓库`关键词仅命中 `LscriptPages/game/z;->j` 的 `di_仓库没装`，更像装备仓库。
2. **离线产出：客户端未发现权威公式。** `离线`关键词只命中腾讯 push SDK ReturnCode。已确认的 `scriptPages/data/i.A()` 是显示层按本地时间差递增铜钱/粮食，不是权威结算，也未见按仓储上限截断。
3. **“储量/产量”主要落在资源点系统。** `di_标题储量`、`di_产量` 等文本集中出现在 `scriptPages/data/g.F/V` 和 `scriptPages/game/p/q` 的资源点/目标列表 UI 链路，而不是玩家个人仓储。
4. **资源点列表请求已确认。** `LscriptPages/game/p;->h1(I,I)V` 发送 `reqResourceList`，opcode `0x1542 / 5442`，请求体为 `x/writeShort`、`y/writeShort`。
5. **资源点列表响应骨架已整理。** `p.f(String)` 读取 `q5/r5/s5...M5`；`p.c1(String)` 读取同构的 `T5/U5/V5...o6`。两者应分别服务资源点列表/攻占或目标视图。
6. **单资源点详情/驻军明细已定位。** `p.P0(String)` 成功时读取名称、坐标、描述、两个 int 数值与一组驻守/守军数组；`p.M0(String)` 更偏驻守/调兵后的将领和闲兵同步。

## 2. 关键证据

| 主题 | 证据 | 说明 |
|---|---|---|
| reqResourceList 请求 | `method_disasm_resource_point/scriptPages_game_p__h1__0x30e3a0.smali.txt` | `openDos("reqResourceList")`，连续写两个 short，调用 `data.f.u(..., 5442)`。 |
| 资源点列表响应 | `method_disasm_resource_point/scriptPages_game_p__f__0x2f75f4.smali.txt` | 先读状态/模式，再读区域 short、count，循环读取 `q5/r5/s5/t5/u5/.../L5`，末尾读取 `M5[]`。 |
| 同构目标列表响应 | `method_disasm_resource_point/scriptPages_game_p__c1__0x30d7c0.smali.txt` | 读流与 `p.f` 高度相似，字段名前缀换为 `T5/U5/V5...`。 |
| 单资源点详情 | `method_disasm_resource_point/scriptPages_game_p__P0__0x30cd34.smali.txt` | result=0 时读取 `K6/L6/M6/N6/x6/y6` 与 `O6..V6` 数组。 |
| 驻守/闲兵同步 | `method_disasm_resource_point/scriptPages_game_p__M0__0x30cad4.smali.txt` | 成功后读将领 ID、兵种、数量并调用 `Lo/a.T8/S8` 更新带兵/闲兵。 |
| 个人仓储缺口 | `storage_offline_string_field_hits.md` | “仓库”命中不像资源仓库；“离线”只在 push SDK；个人资源字段无上限闭环。 |
| 本地显示产出 | `resource_system_report.md` / `scriptPages/data/i.A()` | `d/e` 按 `m/n` 与时间差递增；无服务端权威属性，无上限截断。 |
| 征兵数量约束 | `method_disasm_storage/scriptPages_data_g__z0__0x264cb4.smali.txt` | 使用 `i.d/i.e/i.r-i.q` 取 min，说明 `i.q/r` 更像人口当前/上限，而不是仓储。 |
| 城池资源累积 | `method_disasm_storage/scriptPages_game_k__m__0x2bdbb4.smali.txt` | 出现 `di_资源累积`、`di_是否征收`，更偏城池/封地征收 UI。 |

## 3. 个人仓储上限判断

### 已确认事实

- 玩家资产字段已经在资源系统第一版确认：
  - `scriptPages/data/i.d` = 铜钱
  - `scriptPages/data/i.e` = 粮食
  - `scriptPages/data/g.F` = 黄金
  - `scriptPages/data/g.G` = 白银
  - `scriptPages/data/i.i` = 当前声望
- 本轮围绕 `仓库/上限/已满/超过/储量/离线/剩余/资源累积` 等关键词，以及 `data.i.d/e/q/r/u/v` 读写链进行扫描。
- 未发现对 `i.d/e` 做“超过个人仓库上限则截断”的本地代码。

### 推断

- **中置信度判断：客户端没有个人铜钱/粮食仓储上限闭环。**
- 如果游戏实际存在仓储上限，更可能由服务端在登录、征收、产出结算、资源同步时权威处理；客户端只显示最终资源值。
- 服务端重建时，初版可先不做个人仓储上限，或者做成可配置策略，不影响 APK 主要同步协议。

> 注意：这里不能表述为“游戏一定没有仓储上限”，只能表述为“当前 APK 客户端未恢复到个人仓储上限字段/公式闭环”。

## 4. 离线产出判断

### 已确认事实

- `离线`关键词未命中游戏规则代码，只命中腾讯推送 SDK：`返回标志，表示离线操作`。
- `scriptPages/data/i.A()` 会基于本地时间和总产量字段更新显示：
  - `d += floor((now - G) * m / 3600000)`
  - `e += floor((now - H) * n / 3600000)`
- 该函数没有发现资源上限截断逻辑，也不是关键操作成功后的权威到账链路。

### 推断

- **高置信度：客户端 i.A 是显示层递增。**
- **中置信度：离线产出/离线截断若存在，应在服务端完成。**
- 对重建服务端而言，登录时可根据上次结算时间和服务端产量计算离线产出，再下发最终 `i.d/e/m/n`；客户端会接受服务端同步覆盖。

## 5. 资源点系统协议骨架

### 5.1 `reqResourceList / 0x1542`

入口：`LscriptPages/game/p;->h1(I,I)V`

```text
openDos("reqResourceList")
writeShort(x)
writeShort(y)
data.f.u(..., opcode=5442 / 0x1542)
```

含义：按坐标/区域请求资源点列表。结合山贼 `reqThiefList` 的区域返回模式，资源点也更适合按局部地图返回，而不是一次全图返回。

### 5.2 `p.f(String)` 响应字段骨架

`p.f` 非快照分支读流：

```text
readByte status_or_mode
if status_or_mode == 1:
  Lo/a.Z5(stream)
else:
  readShort -> p5[0]
  readShort -> p5[1]
  readByte  -> count
  repeat count:
    q5/readLong      # 资源点 id
    r5/readByte      # 类型/图标候选
    s5/readUTF       # 名称
    t5/readShort     # x
    u5/readShort     # y
    v5/readByte
    w5/readByte
    x5/readByte
    y5/readInt
    z5/readInt
    A5/readInt
    B5/readInt
    O5/readInt
    P5/readInt
    D5/readInt
    C5/readInt
    discard/readInt
    F5/readShort
    E5/readShort
    G5/readUTF
    H5/readByte
    I5/readUTF
    J5/readUTF
    discard/readShort
    discard/readLong
    Q5/readByte
    R5[2]/readByte,readByte
    S5[3]/readLong,readLong,readLong
    K5/readLong
    L5/readLong
  readLong -> M5_count
  M5/readLong * M5_count
```

初步语义：

- `q5`：资源点 ID。
- `s5`：资源点名称。
- `t5/u5`：坐标。
- `r5`：资源点类型或图标分类。
- `y5/z5/A5/B5/O5/P5/D5/C5`：产量、储量、等级、当前/上限等数值候选。
- `G5/I5/J5`：描述、所属、状态等文本字段候选。
- `S5[3]`：三项 long，高概率为驻守将领/关联队伍/占领相关 ID。
- `K5/L5`：时间戳/保护/占领结束时间候选。
- `M5[]`：与 `q5` 比对的资源点 ID 列表，可能是己方已占/已选/标记列表。

### 5.3 `p.c1(String)` 同构列表

`p.c1` 结构与 `p.f` 基本一致，字段换为：

```text
T5/U5/V5/W5/X5/Y5/Z5/a6/b6/c6/d6/e6/p6/q6/g6/f6/i6/h6/j6/k6/l6/m6/r6/s6/t6/n6/o6
```

推断：它是另一视图的资源点/目标列表，可能用于可攻击、已占领、派兵或特殊筛选页面。精确业务名需要结合 UI 调用路径 `p.s/p.t` 和真实响应样本继续命名。

### 5.4 `p.P0(String)` 单点详情

成功分支读流：

```text
readByte result
if result == 0:
  K6/readUTF      # 名称
  L6/readShort    # x
  M6/readShort    # y
  N6/readUTF      # 描述
  x6/readInt      # 数值1：产量/储量候选
  y6/readInt      # 数值2：产量/储量候选
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

推断：这是单个资源点详情和驻守/守军明细读取器。`T6>=100` 的处理说明某个 byte 混入了状态位。

## 6. `data.g.z0(I,I)`：不是仓储，而是征兵约束

`scriptPages/data/g;->z0(I,I)I` 读流显示：

```text
money_limit = i.d / (Q1(type) * multiplier)
food_limit  = i.e / (R1(type) * multiplier)
limit = min(money_limit, food_limit)
pop_limit = (i.r - i.q) / S1(type)
limit = min(limit, pop_limit)
return max(limit, 0)
```

含义：这是“当前可招募数量”计算，受铜钱、粮食和剩余人口约束。它反向支持：

- `i.q/i.r` 更像人口当前/人口上限候选。
- 该路径不是玩家资源仓储上限。

## 7. 对服务端重建的直接建议

1. **资源资产仍以服务端为准。** 服务端保存并同步铜钱、粮食、黄金、白银、声望、总产量、封地产量等字段；客户端本地增长只是展示。
2. **个人仓储上限可先做配置项。** 由于客户端无明确上限字段，初版可以不截断；若后续动态样本证明有上限，再在服务端结算层添加。
3. **资源点列表按区域返回。** 实现 `reqResourceList/5442` 时按 `x/y` 返回附近资源点，字段顺序兼容 `p.f`。
4. **资源点模型建议字段：**
   - `resource_id`
   - `type`
   - `name`
   - `x/y`
   - `owner/status`
   - `level/current/max`
   - `production`
   - `storage/current_stock/capacity`
   - `bonus/percent`
   - `garrison_general_ids`
   - `protect_until/occupied_until/refresh_at`
   - `related_id_list`
5. **详情接口要支持驻守数组。** 单资源点详情至少要返回名称、坐标、描述、两项核心数值和驻守/守军列表。

## 8. 未完成项

- 资源点 `y5/z5/A5/B5/O5/P5/D5/C5` 的最终字段命名。
- 资源点刷新周期、占领收益、掠夺损失、驻守收益影响。
- 个人仓储上限是否由服务端静默实施，需要接近上限或超额资源样本验证。
- 离线产出如果有服务器侧结算，需要登录前后资源同步样本拟合。
- `data.g.H` 最终命名、人口/资源点/封地/将领上限公式仍待后续资源系统深追。

## 9. 配套结构化文件

- `analysis/game_rules/storage_offline_system/storage_offline_field_mapping.csv`：仓储/离线/资源点候选字段映射。
- `analysis/game_rules/storage_offline_system/resource_point_protocol_fields.csv`：资源点请求和响应字段骨架。
- `analysis/game_rules/storage_offline_system/storage_offline_summary.json`：机器可读摘要。
- `analysis/game_rules/storage_offline_system/storage_offline_string_field_hits.md`：关键词/字段命中原始摘要。
- `analysis/game_rules/storage_offline_system/method_disasm_resource_point`：资源点关键方法反汇编。
- `analysis/game_rules/storage_offline_system/method_disasm_storage`：仓储/离线候选关键方法反汇编。
