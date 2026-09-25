# 建筑产出/人口/队列公式与字段整理（第一版）

## 1. 结论摘要

本轮重点确认“建筑静态效果值”和“封地产出最终显示值”的关系：

- `scriptBuilding.sc` 尾部恢复出的 `En/Fn/Gn/Hn` 是建筑等级静态效果：
  - `En`：铜钱产量效果；访问器 `Lo/a.D1(building, level)`
  - `Fn`：粮食产量效果；访问器 `Lo/a.F1(building, level)`
  - `Gn`：人口上限/人口加成；访问器 `Lo/a.P1(building, level)`
  - `Hn`：征兵队列数量；访问器 `Lo/a.N1(building, level)`
- 但是封地概览界面最终展示的“产钱/产粮”不是在 UI 层重新按建筑逐个累加出来，而是直接使用服务器同步块 `Lo/a.Y5` 读入的 `tv/uv`：
  - `tv[fief] = readInt()`，UI 展示为“产钱：x / 小时”
  - `uv[fief] = readInt()`，UI 展示为“产粮：x / 小时”
- 临时增产/队列加成由 `Lo/a.k1` 读三组 buff：
  - `Bv/Cv/Dv`：铜钱增产
  - `Ev/Fv/Gv`：粮食增产
  - `Hv/Iv/Jv`：建筑队列/同时建设加成
- 因此，服务端重建时可以先采用：**服务器端计算最终 `tv/uv` 并下发，客户端只负责显示与倒计时提示**。

## 2. 关键证据

### 2.1 封地基础同步 `Lo/a.Y5(long,String)`

证据文件：`analysis/game_rules/protocol_chain/method_disasm_fief_sync/o_a__Y5__0x23fc94.smali.txt`

关键读流：

| offset | 字段 | 读法 | 当前命名 |
|---:|---|---|---|
| `0x4c-0x58` | `tv[fief]` | `readInt` | 铜钱产量/小时 |
| `0x5c-0x68` | `uv[fief]` | `readInt` | 粮食产量/小时 |
| `0x6c-0x78` | `vv[fief]` | `readShort` | 未完全命名 |
| `0x7c-0x88` | `wv[fief]` | `readShort` | 未完全命名 |
| `0x8c-0x98` | `xv[fief]` | `readByte` | 建筑队列基础上限/状态候选 |
| `0x9c-0xa8` | `yv[fief]` | `readShort` | 驻防当前值 |
| `0xac-0xb8` | `zv[fief]` | `readShort` | 驻防上限值 |
| `0xbc-0xc8` | `Av[fief]` | `readByte` | 征兵队列上限 |

### 2.2 封地概览 UI `scriptPages/game/q.L()`

证据文件：`analysis/game_rules/protocol_chain/method_disasm_fief_sync/scriptPages_game_q__L__0x320890.smali.txt`

关键 UI 字段对应：

| UI 文案 | 值来源 | 证据 offset | 结论 |
|---|---|---:|---|
| `di_标题产钱` | `Lo/a.tv[q.p] + di_小时` | `0x354-0x378` | `tv` 是铜钱/小时 |
| `di_标题产粮` | `Lo/a.uv[q.p] + di_小时` | `0x388-0x3a0` | `uv` 是粮食/小时 |
| `di_建筑队列` | `d2(fief) / U1(fief)` | `0x222-0x254` | 当前建设队列/队列上限 |
| `di_闲兵` | `o4(fief)` | `0x262-0x284` | `Lv` 总和为闲兵总数 |
| `di_标题征兵队列` | `R4(fief) / Av[fief]` | `0x292-0x2c6` | 当前征兵队列/征兵队列上限 |
| `di_驻防` | `yv[fief] / zv[fief]` | `0x312-0x346` | 驻防当前/上限 |

### 2.3 临时增产状态 `Lo/a.k1(int,String)`

证据文件：`analysis/game_rules/protocol_chain/method_disasm_fief_sync/o_a__k1__0x239d6c.smali.txt`

结构：

```text
coin_buff_count: byte
repeat coin_buff_count:
  Cv[fief][i]: byte      # 类型/目标
  Dv[fief][i]: long      # 当前时间 + readLong，作为结束时间
  Bv[i]: byte            # 增益值/状态值

food_buff_count: byte
repeat food_buff_count:
  Fv[fief][i]: byte
  Gv[fief][i]: long
  Ev[i]: byte

queue_buff_count: byte
repeat queue_buff_count:
  Iv[fief][i]: byte
  Jv[fief][i]: long
  Hv[i]: byte
```

辅助倒计时：

- `q2(fief,i)`：`Dv[fief][i] - now` 秒，铜钱增产剩余时间
- `J2(fief,i)`：`Gv[fief][i] - now` 秒，粮食增产剩余时间
- `V1(fief,i)`：`Jv[fief][i] - now` 秒，队列加成剩余时间

### 2.4 建筑效果表访问器

证据文件：`analysis/game_rules/protocol_chain/method_disasm_building_rules/o_a__D1__0x22229c.smali.txt` 等。

```text
D1(building, level) -> En[index][level-1]  # 铜钱产量效果
F1(building, level) -> Fn[index][level-1]  # 粮食产量效果
P1(building, level) -> Gn[index][level-1]  # 人口上限/人口加成
N1(building, level) -> Hn[index][level-1]  # 征兵队列数量
```

## 3. 服务端重建建议

第一版可采用如下可运行模型：

1. 按 `building_level_rules_server_ready.csv` 建立建筑等级表。
2. 服务端保存每个封地的建筑列表、资源、兵力、队列、buff。
3. 每次同步封地基础信息时，由服务端计算并下发：
   - `tv = final_coin_output_per_hour`
   - `uv = final_food_output_per_hour`
   - `xv/Av/yv/zv` 等队列与驻防上限字段
4. 客户端 `q.L` 直接显示 `tv/uv`；无需依赖客户端复算。
5. 对临时增产，服务端通过 `k1` 三组 buff 下发类型、剩余时间和值。是否把 buff 已合入 `tv/uv`，需要用一次有/无增产状态的抓包对比确认。

## 4. 尚未完全确认项

- `tv/uv` 是否已经包含 `Bv/Ev` 临时增产值，还是只显示基础产量、增产另以提示显示。
- `vv/wv` 的业务语义。
- `Mv/Nv` 第二组类型数量是伤兵、预备兵还是其他兵力池，需要继续追 UI 使用点。
- 资源上限、离线累计、科技/道具/称号加成是否全部由服务端计算后只同步结果；当前 UI 证据强烈倾向“服务端权威”。

## 5. 本轮新增文件

- `analysis/game_rules/protocol_chain/building_output_formula_fields.csv`
- `analysis/game_rules/protocol_chain/building_output_formula_refs.md`
- `analysis/game_rules/protocol_chain/building_output_formula_refs.json`
- `analysis/game_rules/protocol_chain/method_disasm_building_output/`
- `analysis/game_rules/protocol_chain/building_output_formula_summary.json`
