# 将领培养 / 将神魂 / 成长值协议与字段（第一版）

生成时间：2026-07-05  
目标：拆清 `gameHD/h.f`、`gameHD/h.B`、`gameHD/g.k`、`gameHD/g.p` 与 `0x8275 -> gameHD/g.E`，固定将领培养 UI、请求、响应和 `Lo/a.b6` 相关字段语义。

## 1. 产物

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/GENERAL_CULTIVATION_GROWUP.md`
- 字段字典：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/general_cultivation_field_dictionary.csv`
- 请求合同表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/general_cultivation_requests.csv`
- 响应 schema 表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/general_cultivation_response_schema.csv`
- UI 证据表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/general_cultivation_ui_evidence.csv`
- 抓包 opcode 覆盖检查：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/general_cultivation_capture_opcode_check.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/general_cultivation_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/general_cultivation_summary.json`

## 2. 已验证事实

- 培养消耗道具是 `item_id=286`，客户端以 `Lo/a.p1(286)` 汇总 `Lo/a.bv/cv` 栈数量并显示在 `di_将神魂` 下。
- 培养请求 opcode 为 `0x1275`，两套 UI 分支都会发送同一种 payload：`writeLong(general_id); writeShort(cultivate_count)`。
- `general_id` 来自 `Lo/a.b4(0, idx)`，即 `Lo/a.co[0][idx]`；因此培养对象仍是 `b6 type0` 将领/宿主表。
- 请求前客户端检查 `Lo/a.G3(0,idx)`；若非 0，直接提示 `di_将领成长值已满`，不发送 `0x1275`。
- 响应 `0x8275` 由 `LscriptPages/gameHD/g;->E(String)` 处理；成功、失败和批量成功都会在响应中读取 `general_id` 并调用 `Lo/a.a6(0, stream)` 同步单个将领对象。
- 成功后提示中的最终成长值来自 `Lo/a.Q2(0,idx)`，即 `Lo/a.io`。
- `Lo/a.To` 在 `di_保底次数` 下显示，且失败响应仍同步 `a6`，因此高概率为当前保底/失败累计次数。
- `Lo/a.Uo` 通过 `G3` 读取，既参与 `di_保底次数` 展示，又作为“成长值已满”的本地预检查标志；最终字段名仍需真实样本确认。
- `Lo/a.So` 通过 `V2` 读取，只见用于将领名称颜色/成长档位着色，未见参与培养公式或请求。

## 3. 字段字典更新

| 字段 | Accessor | 建议命名 | 证据 | 置信度 |
|---|---|---|---|---|
| `Lo/a.io` | `Lo/a.Q2(II)` | `growth_value` | 培养成功/批量培养成功提示追加 Q2(0, idx)；将领详情也以“成长值”标签显示 Q2。 | high |
| `Lo/a.To` | `(direct read in gameHD/h.f and gameHD/g.k)` | `cultivation_guarantee_count_current` | 在“保底次数:”标签下作为第一个数值读取；培养失败分支仍 a6 同步，符合失败增加保底次数。 | medium-high |
| `Lo/a.Uo` | `Lo/a.G3(II)` | `cultivation_growth_full_or_cap_flag` | 在“保底次数:”标签下与 To 配对显示；发送 0x1275 前若 G3(0,idx)!=0，客户端直接提示“将领成长值已满”并不发请求。 | medium |
| `Lo/a.So` | `Lo/a.V2(II)` | `general_name_color_or_growth_tier` | V2 仅用于索引 gameHD/h.Q、gameHD/g.T1 等颜色数组并给将领名称着色；与成长页相邻同步，但未见客户端用它参与公式。 | medium-high |
| `Lo/a.bv/cv` | `Lo/a.p1(J)` | `item_count_by_item_id` | 培养页用 p1(286) 显示“将神魂”库存；p1 遍历 bv id 并累加 cv 数量。 | high |

## 4. 请求合同

```text
0x1275 reqGeneralCultivate / reqGeneralGrowUp:
  writeLong  general_id          # Lo/a.b4(0, idx) == Lo/a.co[0][idx]
  writeShort cultivate_count     # h.T 或 g.u1，客户端限制到 1..min(99, 将神魂库存)
```

| 调用点 | 预检查 | 请求体 | 计数限制 |
|---|---|---|---|
| `LscriptPages/gameHD/h;->B()I @ 0x0d8e-0x0dc8` | Lo/a.G3(0, current_idx) == 0；若非 0，提示 di_将领成长值已满，不发送。 | `writeLong(general_id = Lo/a.b4(0,current_idx)); writeShort(cultivate_count = h.T)` | h.T 由按钮/输入调整，客户端夹到 [1, min(99, max(1, Lo/a.p1(286)))]。 |
| `LscriptPages/gameHD/g;->p()V @ 0x09b6-0x09e4` | Lo/a.G3(0, current_idx) == 0；若非 0，提示 di_将领成长值已满，不发送。 | `writeLong(general_id = Lo/a.b4(0,current_idx)); writeShort(cultivate_count = g.u1)` | g.u1 由按钮/输入调整，客户端夹到 [1, min(99, max(1, Lo/a.p1(286)))]。 |

## 5. 响应合同

```text
0x8275 gameHD/g.E(stream):
  readByte result_code
  if result_code in {0,1,2}:
      readLong general_id
      idx = Lo/a.c3(0, general_id)
      Lo/a.a6(0, stream)       # 单将领 b6 增量同步
      # 0=培养失败, 1=培养成功, 2=批量培养成功并显示 Q2 成长值
  else if -1/-2/-3/-4/-5:
      # 只读 result_code，显示错误/购买/已满/非空闲/未开放提示
```

| result_code | 服务端需返回 | 客户端效果 |
|---:|---|---|
| `0` | readByte result; readLong general_id; idx=Lo/a.c3(0,general_id); Lo/a.a6(0,stream) | 提示 di_培养失败；仍接受 a6 单将领同步，服务端可借此推进保底次数。 |
| `1` | readByte result; readLong general_id; idx=Lo/a.c3(0,general_id); Lo/a.a6(0,stream) | h.T=1；提示 di_培养成功。 |
| `2` | readByte result; readLong general_id; idx=Lo/a.c3(0,general_id); Lo/a.a6(0,stream) | h.T=1；提示“培养成功,成长值提升到” + Lo/a.Q2(0,idx)。 |
| `0/1/2` | 与 h.a==false 分支同构；结果写入 gameHD/g.d 和 g.u1。 | 提示失败/成功/批量成功；成功后 g.u1=1。 |
| `-1` | readByte result only | 提示 di_提示其他错误。 |
| `-2` | readByte result only | 提示 di_确认前往商城购买将神魂；设置 h.V 或 g.v1，供后续跳转商城/购买确认。 |
| `-3` | readByte result only | 提示 di_将领成长值已满。 |
| `-4` | readByte result only | 提示 di_将领非培养状态。 |
| `-5` | readByte result only | 提示 di_提示未开放。 |

## 6. UI 证据

| 方法 | 偏移 | 证据 | 置信度 |
|---|---|---|---|
| `LscriptPages/gameHD/h;->f()V` | 0x06d0-0x0cb0 | 培养页展示 di_培养成功功能、di_将神魂、di_保底次数、di_培养次数；p1(286) 显示将神魂库存；To/G3(Uo) 显示保底相关数值；h.T 显示本次培养次数。 | high |
| `LscriptPages/gameHD/g;->k()V` | 0x0074-0x05d4 | 另一套培养页同样展示将神魂库存、保底次数和培养次数；读取 To 与 G3(Uo)。 | high |
| `LscriptPages/gameHD/h;->B()I` | 0x0c94-0x0e92 | GrowUp_Cmd_BtnHD 控制减少/输入/增加/确认培养/说明；确认时写 0x1275 请求。 | high |
| `LscriptPages/gameHD/g;->p()V` | 0x08b4-0x0b10 | GrowUp_Cmd_Btn 控制普通培养页；确认时写 0x1275 请求。 | high |
| `LscriptPages/gameHD/h;->m()V / gameHD/g.f/u / La0/a.b0` | V2 callers | Lo/a.V2(0,idx) 返回 So，用作颜色数组索引为将领名称上色。 | medium-high |

## 7. 抓包覆盖情况

- 当前离线抓包目录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/captures/mitm/game_capture_20260705_020959/extracted`。
- 已解析请求 opcode：`0x1008, 0x1016, 0x1102, 0x1104, 0x1113, 0x1130, 0x1800, 0x3110, 0x3160, 0x6200`。
- 已解析响应 opcode：`0x8001, 0x8004, 0x8008, 0x800a, 0x800d, 0x8102, 0x8104, 0x8113, 0x8130, 0x8146, 0x8280, 0x8800, 0xa110, 0xa129, 0xa160, 0xe200`。
- 当前抓包未命中真实 `0x1275/0x8275` 培养交易；以上合同来自静态代码和响应分发表，需要后续实际培养样本验证 `To/Uo/So` 的动态取值。

## 8. 服务端重建影响

- 服务端未来实现培养时，不能只返回成功/失败码；`result_code in {0,1,2}` 必须追加 `general_id + a6(0)`，让客户端刷新 `io/To/Uo/So` 等 b6 字段。
- 培养失败也应同步 `a6`，否则客户端保底次数不会权威刷新。
- `0x1275` 请求中的 `cultivate_count` 是用户希望培养次数，不代表服务端必须全成功；服务端要按库存、将领状态、成长上限和概率/保底规则权威计算后同步最终 b6。
- `item_id=286` 的库存走 `V5 -> bv/cv` 或其他资产同步链；培养响应本身只见 `a6`，未见 `V5`，是否扣将神魂随本响应之外的同步块返回仍需真实样本验证。

## 9. 未解决问题

- `Lo/a.Uo` 的精确业务名：目前能确定它既用于保底展示又用于“成长值已满”预检查，但需要真实 `0x8275` 或 b6 样本确认它是上限标志、保底目标、还是二者复合状态。
- `Lo/a.So` 的最终业务名：当前高置信是名称颜色/成长档位 tier；是否完全由成长值区间派生，还是服务端直接下发的名将品质/颜色，需要更多样本。
- 培养概率、保底上限、扣道具数量是服务端权威；客户端只显示库存、次数和结果，不包含明确概率公式。
