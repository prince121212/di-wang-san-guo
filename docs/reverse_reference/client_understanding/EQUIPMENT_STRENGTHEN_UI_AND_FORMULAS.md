# 装备强化 UI 与公式链路（第一版）

生成时间：2026-07-05  
目标：从客户端离线恢复装备强化页的状态机、公式展示、请求模式和服务端同步边界，为未来重建服务端准备响应合同。

## 1. 产物

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/EQUIPMENT_STRENGTHEN_UI_AND_FORMULAS.md`
- UI 状态/字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_strengthen_ui_schema.csv`
- 操作流程表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_strengthen_operation_flow.csv`
- 公式字典：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_strengthen_formula_dictionary.csv`
- 方法摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_strengthen_method_summary.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_strengthen_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_strengthen_extraction_summary.json`

## 2. 方法入口

| 方法 | 角色 | 证据价值 |
|---|---|---|
| `LscriptPages/game/z;->W0()I` | 装备页输入/状态机：打开强化、换装/卸装、普通强化、特殊强化、自动强化 20 次。 | 所有强化操作按钮和 G0/C0 调用点集中在此方法。 |
| `LscriptPages/game/z;->a()V` | 材料不足/材料入口跳转：按当前装备材料 id 打开 q.T0(..., 4420)。 | W0 中库存不足或入口按钮会调用该方法。 |
| `LscriptPages/game/z;->j()V` | 装备弹窗/强化弹窗绘制：材料、属性、成功率、保底次数、失败风险、自动强化进度。 | 公式和字段语义的 UI 证据集中在此方法。 |
| `LscriptPages/game/z;->e0()V` | 创建强化弹窗/菜单，包含“强化20次/强化/说明/返回”等控件。 | W0 进入 K1=2 后调用。 |
| `LscriptPages/game/z;->h1()V` | 停止/重置自动强化：L1=-1、M1=0，并把按钮恢复为“强化20次”。 | 自动 20 次强化的停止条件和按钮状态由此方法复位。 |
| `LscriptPages/game/z;->u0(J)Z` | 判断当前装备 id 是否仍存在于 bank0/bank1/当前宿主列表中。 | W0 在 K1=2 处理输入前先用它校验 H1 是否仍有效。 |
| `LscriptPages/game/z;->V(I)[S` | 按材料 item_id 在 z.S1 中查找入口参数，供 q.T0([S, 4420) 使用。 | 材料不足入口和 z.a() 的关键 helper。 |
| `LscriptPages/game/z;->C0(JJI)V` | 发送 reqGeneralEquipCtrl / 0x1252：宿主 id 候选、装备 id、action_type。 | 换装/卸装请求入口。 |
| `LscriptPages/game/z;->G0(JJI)V` | 发送 reqGeneralEquipLevelup / 0x1254：宿主 id 候选、装备 id、levelup_mode。 | 普通强化/特殊强化/自动强化请求入口。 |
| `LscriptPages/game/z;->H0(Ljava/lang/String;)V` | 接收 0x8254 强化响应，设置 D3=1 并同步 c6/a6|f6 + V5。 | 自动强化节奏依赖 D3；响应合同由此确认。 |

## 3. 强化 UI 状态机

核心字段：`K1` 是装备页子状态机，`I1` 是当前装备宿主 id 候选，`H1` 是当前装备实例 id，`L1/M1/D3` 组成自动强化节奏控制。

| 状态/字段 | 客户端语义 | 证据 | 置信度 |
|---|---|---|---|
| `K1` | 装备页子状态机。0=装备弹窗主菜单；1=仓库装备列表/换装；2=强化弹窗；3/4/5/6/7/8=材料入口/说明/缺货提示/特殊强化等跳转态。 | z.W0 0x0000 起按 K1 分支；K1=2 区间处理 equipstronger 菜单；z.j 按 K1 绘制不同界面。 | high |
| `I1` | 当前装备宿主 id 候选，高概率为当前将领/可装备对象 id。 | 卸装 z.W0@0x0134 C0(I1,H1,1)；换装 @0x032a C0(I1,N1[selected],0)；强化 @0x065c/@0x0782 G0(I1,H1,mode)。 | medium-high |
| `H1` | 当前选中装备实例 id。 | 大量 data.d.*(H1) 访问；强化请求 G0(I1,H1,mode)；卸装 C0(I1,H1,1)。 | high |
| `N1` | 仓库/可换装装备实例 id 列表。 | K1=1 中由 data.d.f(1,J1) 填充，选中后 C0(I1,N1[selected],0)。 | high |
| `L1` | 自动强化剩余/状态计数。启动时置 20，绘制时显示 21-L1 / 20，停止时 h1 置 -1。 | z.W0@0x0682-0x069c 启动；@0x04c4 起循环；z.j@0x0ffa-0x1086 绘制 re_第N次强化。 | high |
| `M1` | 自动强化节流时间戳，约 800ms 间隔。 | z.W0@0x04cc-0x04f6 用 BaseUtil.getCurTime()-M1 > 800 控制下一次 G0。 | high |
| `D3` | 强化响应到达标志/节奏标志。G0 发送前置 0，H0 响应入口置 1，自动循环消费后再置 0。 | z.W0@0x052c 读取并清 0；z.G0 发送后置 0；z.H0 响应入口置 1。 | medium-high |
| `R1` | 强化弹窗菜单焦点/输入状态。 | K1=2 中围绕 q0.l0("equipstronger") 和输入键改变 R1。 | medium |
| `U1` | 强化 20 次按钮控件 id。自动强化开始时改图标和标题，h1 恢复。 | z.W0@0x06a0 调 Lo/a.g7(U1,12611,12611)、Y6(U1,"中止强化")；h1 复位。 | high |
| `data.d.q(H1)` | 当前装备强化等级/强化值；客户端上限检查为 <30。 | 进入强化前 z.W0@0x00f0；普通强化前 @0x0630；自动停止 @0x0508；失败风险门槛 z.j@0x0f54。 | high |
| `data.d.k(H1)` | 当前下一次强化所需材料 [item_id, required_amount]。 | z.W0@0x0538、0x05fc；z.a@0x0000；z.j@0x0b4c 显示材料名与库存/需求。 | high |

### 3.1 `K1` 主要状态

- `K1=0`：装备弹窗主菜单，处理 `equippop_equip/change/stronger/dropoff/return`。
- `K1=1`：仓库装备列表/换装，选中 `N1[index]` 后发 `C0(I1,N1[index],0)`。
- `K1=2`：强化弹窗，处理普通强化、强化 20 次、说明、材料入口、特殊强化跳转。
- `K1=3/4/5/6/7/8`：材料/道具入口、说明页、缺货提示、特殊强化相关跳转态；当前只按强化链路记录，不扩展这些子页面。

## 4. 操作流与请求

| 流程 | 用户动作/状态 | 客户端预检查 | 请求 | 响应/同步 | 服务端重建要点 |
|---|---|---|---|---|---|
| `open_strengthen_popup` | 装备弹窗主菜单选择 equippop_stronger | data.d.q(H1) < 30 | 无 | 无 | 打开强化弹窗本身不发包，只依赖客户端已持有的装备记录。 |
| `dropoff_equipment` | 装备弹窗主菜单选择 equippop_dropoff | 当前 H1 选中 | z.C0(I1,H1,1) -> reqGeneralEquipCtrl / 0x1252 | 0x8252: success,message,sync_mode,(c6+a6|f6),V5,S5 | 服务端决定是否允许卸装，并返回装备 bank1、宿主对象、资产/状态同步。 |
| `equip_from_store` | 仓库装备列表 K1=1 选择某装备 | N1=data.d.f(1,J1)，列表非空；用户选中 N1[index] | z.C0(I1,N1[index],0) -> reqGeneralEquipCtrl / 0x1252 | 0x8252: success,message,sync_mode,(c6+a6|f6),V5,S5 | 客户端只传目标装备实例 id 和 action_type=0；槽位、合法性、属性刷新由服务端裁定。 |
| `normal_strengthen` | 强化弹窗点击“强化” | material=data.d.k(H1); Lo/a.p1(item_id) >= required_amount 且库存非 0；data.d.q(H1)<30 | z.G0(I1,H1,0) -> reqGeneralEquipLevelup / 0x1254 | 0x8254: success,message,sync_mode,(c6+a6|f6),V5 | 客户端有库存/上限预检查，但成功率、扣材料、失败掉级/损毁、保底计数必须由服务端权威决定。 |
| `auto_strengthen_20_start` | 强化弹窗点击“强化20次” | 同普通强化材料/上限检查；若 L1<=0 则启动 | z.G0(I1,H1,0) -> 0x1254 | 0x8254 后由 D3/M1/L1 驱动下一次 | 这不是单包“强化20次”；客户端循环发送最多 20 个普通强化请求。 |
| `auto_strengthen_20_continue` | 自动强化进行中 | M1 间隔约 800ms；D3==1 表示上一轮响应已到；材料仍足；未到 30 级 | 循环 z.G0(I1,H1,0) | 每轮都是 0x8254 | 服务端无需识别 20 次批量模式；按单次 0x1254 响应即可驱动客户端。 |
| `special_strengthen` | 特殊强化入口/确认后执行 | 强化页跳转态返回后执行；仍以当前 I1/H1 为目标 | z.G0(I1,H1,1) -> reqGeneralEquipLevelup / 0x1254 | 0x8254 | levelup_mode=1 的具体消耗/成功规则客户端未闭环，需要服务端配置或动态样本确认。 |
| `material_shortage_entry` | 材料不足或材料入口按钮 | material_id=data.d.k(H1)[0] | 无 | 无 | 这是 UI 跳转/获取途径入口，不是强化结果包。 |

关键请求事实：

- 普通强化：`z.G0(I1,H1,0)` → `reqGeneralEquipLevelup / 0x1254`。
- 特殊强化：`z.G0(I1,H1,1)` → `reqGeneralEquipLevelup / 0x1254`。
- 自动“强化20次”不是批量协议，而是客户端循环发送最多 20 次 `z.G0(I1,H1,0)`，每轮等待 `0x8254` 响应后继续。
- 换装：`z.C0(I1,N1[index],0)` → `reqGeneralEquipCtrl / 0x1252`。
- 卸装：`z.C0(I1,H1,1)` → `reqGeneralEquipCtrl / 0x1252`。

## 5. 展示公式与字段

| 名称 | 客户端表达式 | 证据 | 服务端重建含义 | 置信度 |
|---|---|---|---|---|
| 强化等级/上限 | `level = data.d.q(equipment_id) = data.d.f[bank][slot][1]; client_max_check: level < 30` | z.W0@0x00f0、0x0630；data.d.q(J) 访问 f[][1]。 | 客户端会阻止已显示 >=30 的强化请求；服务端仍必须权威校验上限。 | high |
| 强化属性贡献 | `quality=data.d.f[bank][slot][0]; type=Lo/a.S4(template_id); base=Lo/a.z1(template_id); coeff=Lo/a.y2(type)[quality]; contribution=strengthen_value*coeff; total=base+contribution` | DATA_D_EQUIPMENT_ACCESSORS.md；EQUIPMENT_STATIC_TABLES.md；z.j@0x0d14-0x0e20 显示“强化效果”属性名和 coeff。 | 客户端展示属性可按本地静态表计算；服务端响应需同步装备 strengthen_value 和宿主属性，使 UI 与实际一致。 | high |
| 下一次强化材料 | `material=data.d.k(id); type=Lo/a.S4(template_id); quality=f[][0]; strengthen=f[][1]; material_id=ao[l3(type)][quality][0]; required=max(1, ao[l3(type)][quality][1]*(strengthen+1)/100)` | data.d.k(J) 公式；z.W0@0x05fc-0x0626 用 [0]/[1] 做库存判断；z.j@0x0b4c-0x0c6c 显示“库存/需求”。 | 可作为客户端预期材料显示；扣减数量最终以服务端响应 V5 背包同步为准。 | high |
| 材料库存预检查 | `inventory = Lo/a.p1(material_id); allow if inventory >= required_amount and inventory != 0` | z.W0@0x0608-0x062e；z.j@0x0b64-0x0b8c 用库存/需求决定颜色。 | 客户端预检查可被绕过，服务端必须再次检查库存。 | high |
| 成功率百分比显示 | `raw=data.d.g[bank][slot]; int=raw/100; frac=raw%100; show frac>0 ? f"{int}.{frac}%" : f"{int}%"; label=di_强化成功率` | z.j@0x0c80-0x0cf0 取 data.d.g 并格式化；@0x0e50-0x0e82 拼到 di_强化成功率。 | 服务端需在 0x8254 的 c6/V5 装备记录中同步新的 g 值；实际随机成功/失败仍由服务端权威。 | high |
| 保底次数显示 | `current=data.d.i[bank][slot][0]; target=data.d.i[bank][slot][1]; show "强化保底次数 current/target 次"` | z.j@0x0e88-0x0f28。 | 失败/成功后保底计数的增减必须由服务端通过装备同步字段写回。 | high |
| 失败掉级/损毁风险显示 | `risk=data.d.p(id,false)=data.d.h[bank][slot][0]; if risk>0 and level>=10: label = level<20 ? di_失败掉级率 : di_失败损毁率; show risk + "%"` | z.j@0x0f44-0x0fec。 | 客户端只显示风险；是否掉级/损毁和字段变化必须由服务端响应裁定。 | high |
| 自动强化 20 次进度 | `start: L1=20; progress_text uses 21-L1 + "/20"; interval gate: getCurTime()-M1 > 800ms` | z.W0@0x04cc-0x0502、0x0682-0x06b6；z.j@0x0ffa-0x1086。 | 客户端循环单次请求；服务端只需稳定处理连续 0x1254。 | high |

### 5.1 强化材料公式

`data.d.k(J)` 返回下一次强化材料 `[item_id, required_amount]`，其计算来自装备类型静态表 `scriptEquipType.sc` 的 `ao` 材料数组：

```text
type = Lo/a.S4(template_id)
quality = data.d.f[bank][slot][0]
strengthen_value = data.d.f[bank][slot][1]
material_id = Lo/a.ao[Lo/a.l3(type)][quality][0]
base_amount_per_100 = Lo/a.ao[Lo/a.l3(type)][quality][1]
required_amount = max(1, base_amount_per_100 * (strengthen_value + 1) / 100)
```

UI 用 `Lo/a.p1(material_id)` 显示库存并做本地预检查；未来服务端仍必须权威扣减和拒绝非法请求。

### 5.2 属性增长公式

```text
quality = data.d.f[bank][slot][0]
strengthen_value = data.d.f[bank][slot][1]
template_id = data.d.e[bank][slot]
type = Lo/a.S4(template_id)
base = Lo/a.z1(template_id) = Lo/a.Ln[Lo/a.g3(template_id)]
coeff = Lo/a.y2(type)[quality] = Lo/a.Zn[Lo/a.l3(type)][quality]
strengthen_contribution = strengthen_value * coeff
total_stat = base + strengthen_contribution
display_text = Lo/a.w2(type, total_stat)
```

`z.j()` 的“强化效果”区域显示属性名（攻击/生命/防御/统兵）和 `coeff`；装备总属性显示则走 `data.d.i/j/E`。

### 5.3 成功率、保底和风险

- `data.d.g[bank][slot]` 被格式化为百分比并显示在 `di_强化成功率` 后：`raw=1234` 显示为 `12.34%`，`raw=1200` 显示为 `12%`。
- `data.d.i[bank][slot][0/1]` 显示为“强化保底次数 current/target 次”。
- `data.d.p(H1,false)` 读取 `data.d.h[bank][slot][0]`；仅在 `risk>0 && level>=10` 时显示，`level<20` 是失败掉级率，`level>=20` 是失败损毁率。
- 客户端只展示这些概率/计数；随机成功、失败、掉级、损毁、保底计数变化和材料扣减都应由服务端响应 `0x8254` 决定。

## 6. `0x8254` 服务端最小响应边界

强化请求发送后，客户端期望 `0x8254 -> z.H0` 合同（详见装备操作响应报告）：

```text
boolean success
UTF     message
byte    sync_mode
if sync_mode == 0:
  Lo/a.c6(stream)      # 装备 bank1 / 宿主绑定增量
  Lo/a.a6(0, stream)   # 单个 type0 宿主对象增量
else if sync_mode == 1:
  Lo/a.f6(0, stream)   # type0 对象全量刷新
Lo/a.V5(stream)        # 资产/背包/bank0 装备等复合同步
```

成功时客户端播放 `DEPOT_LEVEL_UP_SUCCESS_EFFECT`；自动强化继续与否由 `D3/L1/M1` 和同步后的材料/等级共同决定。

## 7. 推断与置信度

- 高置信：`H1` 是当前装备实例 id；`G0(I1,H1,0/1)` 是普通/特殊强化；`C0(I1,equip_id,0/1)` 是换装/卸装。
- 中高置信：`I1` 是当前装备宿主 id，高概率为将领/可装备对象 id；需继续沿 `z.Y0()`、`gameHD/*` 调用点最终定名。
- 高置信：材料、属性、成功率、保底、失败风险的客户端展示字段和公式。
- 高置信：成功/失败判定、掉级/损毁、保底推进、扣材料必须由服务端权威处理；客户端只是预检查和展示。
- 中置信：`levelup_mode=1` 的特殊强化具体消耗/规则；当前只能确认请求 mode 值和 UI 提示，缺动态样本/服务端配置。

## 8. 建议下一步

1. 回看 `z.C0/G0/E0` 的所有调用点，把 `I1` 精确命名为 general_id/host_id，并确认 `N1[index]` 的来源筛选。
2. 沿 `scriptPages/game/z` 将领/装备详情 UI 继续给 `Lo/a.b6` 宿主对象字段命名，尤其是装备后的属性刷新字段。
3. 如果后续抓包出现 `0xe27f`，按 `data.g.s4` schema 解析动态 `bo` 表，补齐特殊强化/炼魂/附加效果相关材料或效果。
