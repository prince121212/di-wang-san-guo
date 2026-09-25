# 装备请求参数命名：`z.E0/C0/G0` 调用点复核（第一版）

生成时间：2026-07-05  
目标：把装备请求中的两个 long 参数从“宿主/装备候选”推进为可用于未来服务端响应/请求合同的明确命名。

## 1. 产物

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/EQUIPMENT_REQUEST_PARAMETER_NAMING.md`
- 调用点表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_request_call_sites.csv`
- 状态字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_request_state_fields.csv`
- 状态写入点表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_request_state_writes.csv`
- 参数结论表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_request_parameter_conclusions.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_request_parameter_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_request_parameter_summary.json`

## 2. 覆盖范围

- `z.E0(J)` 调用点：3 个。
- `z.C0(J,J,I)` 调用点：12 个。
- `z.G0(J,J,I)` 调用点：4 个。
- 关键状态设置方法：`z.Y0()`、`z.b0(J,I,J,I)`、`z.X(I,J,B)`、`z.d()`、`z.W0()`、`gameHD/g.p()`、`gameHD/h.B()`、`gameHD/c.n()`、`game/k0.f0()`。

## 3. 最终请求参数命名

| 方法 | opcode | 请求名 | 请求体命名 | 证据 | 置信度 |
|---|---:|---|---|---|---|
| `LscriptPages/game/z;->E0(J)V` | `0x1250` | `reqGeneralEquipInfo` | `writeLong(host_id)` | 见下方参数逐项证据 | high/见逐项 |
| `LscriptPages/game/z;->C0(JJI)V` | `0x1252` | `reqGeneralEquipCtrl` | `writeLong(host_id); writeLong(equipment_id); writeByte(action_type)` | 见下方参数逐项证据 | high/见逐项 |
| `LscriptPages/game/z;->G0(JJI)V` | `0x1254` | `reqGeneralEquipLevelup` | `writeLong(host_id); writeLong(equipment_id); writeByte(levelup_mode)` | 见下方参数逐项证据 | high/见逐项 |

逐项参数证据：

| 方法 | 参数旧名 | 参数新名 | 证据 | 置信度 |
|---|---|---|---|---|
| `LscriptPages/game/z;->E0(J)V` | `long_arg0` | `host_id` | 所有 E0 调用点先以同一 long 调 Lo/a.z2(host_id) 或来自 z.n/gameHD host arrays；响应 F0 后 z.z1=Lo/a.z2(z.I1)。 | high |
| `LscriptPages/game/z;->C0(JJI)V` | `long_arg0` | `host_id` | 卸装分支传 data.d.r(equipment_id)；换装分支传当前 z.I1/selected host；D0 后按 z.I1 重算装备列表。 | high |
| `LscriptPages/game/z;->C0(JJI)V` | `long_arg1` | `equipment_id` | 卸装分支传 H1/data.d.C()/z2(host)[idx]；换装分支传 N1/data.d.e()/k0.s2/u2；这些均是装备实例 id 列表。 | high |
| `LscriptPages/game/z;->C0(JJI)V` | `int_arg2` | `action_type` | 0 对应 di_联网换装/di_提示装备中；1 对应 di_联网卸载装备。 | high |
| `LscriptPages/game/z;->G0(JJI)V` | `long_arg0` | `host_id` | 所有 G0 调用点都传 z.I1；z.I1 已由 b0/Y0 证明为当前宿主 id。 | high |
| `LscriptPages/game/z;->G0(JJI)V` | `long_arg1` | `equipment_id` | 所有 G0 调用点都传 z.H1；H1 是当前装备实例 id，强化页大量 data.d.*(H1) 读取。 | high |
| `LscriptPages/game/z;->G0(JJI)V` | `int_arg2` | `levelup_mode` | 0 对应普通强化/自动20次；1 对应提示 di_提示特殊强化中。 | high for 0, medium-high for 1 |

因此，未来服务端侧可把三个请求合同写成：

```text
0x1250 reqGeneralEquipInfo:
  writeLong host_id

0x1252 reqGeneralEquipCtrl:
  writeLong host_id
  writeLong equipment_id
  writeByte action_type      # 0=equip/change, 1=dropoff

0x1254 reqGeneralEquipLevelup:
  writeLong host_id
  writeLong equipment_id
  writeByte levelup_mode     # 0=normal, 1=special
```

## 4. 状态字段来源

| 字段/方法 | 命名 | 证据 | 置信度 |
|---|---|---|---|
| `z.I1` | current_host_id / current_general_id candidate | 写入点只有 z.Y0 和 z.b0。Y0: I1=z.n[M]，随后 z.z1=Lo/a.z2(I1) 和 E0(I1)。b0: 第三个参数写入 I1，而所有调用均传宿主 id（z.n[index] 或 data.d.r(equipment_id)）。 | high |
| `z.H1` | current_equipment_id | z.b0 第一个参数写入 H1；z.d 从 z.z1 选中项写入 H1；后续所有 data.d.*(H1)、C0(I1,H1,1)、G0(I1,H1,mode) 都按装备实例使用。 | high |
| `z.J1` | current_equipment_type_or_slot_filter | z.b0 第二参数写入 J1；若 H1!=-1 则被 data.d.F(H1) 覆盖；data.d.f(1,J1) 用它筛选可换装备。 | medium-high |
| `z.N1` | candidate_equipment_id_list | 由 data.d.f(1,J1) 或同类 helper 生成；W0 选中后 C0(I1,N1[index],0)。 | high |
| `z.z1` | current_host_equipped_equipment_ids | 由 Lo/a.z2(I1/host_id) 返回；z.d 从 z.z1 选择 H1；F0/D0/H0 响应后重新 z.z1=Lo/a.z2(I1)。 | high |
| `scriptPages/data/d.r(equipment_id)` | equipment_host_id_backlink | bank1 装备反链 accessor；卸装路径总是 C0(data.d.r(equipment_id), equipment_id, 1)。 | high |
| `z.C3` | post-equipment-operation UI refresh context | 大量 C0 前设置为 0/1；不进入请求体，只影响 D0/H0 后续 UI 刷新/跳转。 | medium |

关键方法 `z.b0(J,I,J,I)` 的参数语义可按实际写字段反推为：

```text
z.b0(equipment_id, equipment_type_or_slot_filter, host_id, popup_state):
  z.H1 = equipment_id
  z.I1 = host_id
  z.J1 = equipment_type_or_slot_filter
  if equipment_id != -1: z.J1 = data.d.F(equipment_id)
  z.K1 = popup_state
```

## 5. 调用点分类摘要

| 请求 | 调用点 | 语义 | 参数来源 | 置信度 |
|---|---|---|---|---|
| `reqGeneralEquipCtrl` | `LscriptPages/game/k0;->f0()I@0x0a72` | 装备仓库/管理页卸下 bank1 已穿戴装备。 | host_id=data.d.r(data.d.C()[index]); equipment_id=data.d.C()[index]; action_type=1/dropoff=const 1 | high |
| `reqGeneralEquipCtrl` | `LscriptPages/game/k0;->f0()I@0x0acc` | 装备仓库/管理页卸下 u2 列表中的已穿戴装备。 | host_id=data.d.r(k0.u2[index]); equipment_id=k0.u2[index]; action_type=1/dropoff=const 1 | high |
| `reqGeneralEquipCtrl` | `LscriptPages/game/k0;->f0()I@0x0c2e` | 从仓库/装备列表给选定宿主装备当前装备。 | host_id=selected host id in local v4/v5; equipment_id=gameHD/c.a0[grid_index]; action_type=0/equip=const 0 | medium-high |
| `reqGeneralEquipCtrl` | `LscriptPages/game/k0;->f0()I@0x0c8c` | 从 data.d.e()/bank0 列表给选定宿主装备。 | host_id=selected host id in local v4/v5; equipment_id=data.d.e()[selected]; action_type=0/equip=const 0 | medium-high |
| `reqGeneralEquipCtrl` | `LscriptPages/game/k0;->f0()I@0x0cd0` | 从 data.d.e()/bank0 列表给选定宿主装备。 | host_id=selected host id in local v4/v5; equipment_id=data.d.e()[selected - len(data.d.e())]; action_type=0/equip=const 0 | medium-high |
| `reqGeneralEquipCtrl` | `LscriptPages/game/k0;->f0()I@0x0d0a` | 从 k0.s2 列表给选定宿主装备。 | host_id=selected host id in local v4/v5; equipment_id=k0.s2[k0.v2]; action_type=0/equip=const 0 | medium-high |
| `reqGeneralEquipCtrl` | `LscriptPages/game/k0;->f0()I@0x0d36` | 从 k0.u2 列表给选定宿主装备。 | host_id=selected host id in local v4/v5; equipment_id=k0.u2[index]; action_type=0/equip=const 0 | medium-high |
| `reqGeneralEquipCtrl` | `LscriptPages/game/z;->W0()I@0x013c` | 装备弹窗卸装。 | host_id=z.I1; equipment_id=z.H1; action_type=1/dropoff=const 1 | high |
| `reqGeneralEquipCtrl` | `LscriptPages/game/z;->W0()I@0x033e` | 装备弹窗从仓库列表换装。 | host_id=z.I1; equipment_id=z.N1[selected]; action_type=0/equip=const 0 | high |
| `reqGeneralEquipCtrl` | `LscriptPages/gameHD/c;->n()I@0x09a4` | HD 装备网格卸装。 | host_id=data.d.r(gameHD/c.a0[grid_index]); equipment_id=gameHD/c.a0[grid_index]; action_type=1/dropoff=const 1 | high |
| `reqGeneralEquipCtrl` | `LscriptPages/gameHD/g;->p()V@0x06ae` | 将领管理 HD 页卸下当前装备。 | host_id=data.d.r(equipment_id); equipment_id=equipment_id from Lo/a.z2(host)[selected]; action_type=1/dropoff=const 1 | high |
| `reqGeneralEquipCtrl` | `LscriptPages/gameHD/h;->B()I@0x07a4` | 另一 HD 将领装备页卸下当前装备。 | host_id=data.d.r(equipment_id); equipment_id=equipment_id from Lo/a.z2(host)[selected]; action_type=1/dropoff=const 1 | high |
| `reqGeneralEquipInfo` | `LscriptPages/game/z;->Y0()I@0x0db0` | 打开/刷新当前列表选中宿主的装备信息。 | host_id=z.n[z.M] | high |
| `reqGeneralEquipInfo` | `LscriptPages/gameHD/g;->p()V@0x051a` | 将领管理 HD 页按宿主 id 刷新装备信息。 | host_id=gameHD/g.a[selected] | high |
| `reqGeneralEquipInfo` | `LscriptPages/gameHD/h;->B()I@0x09da` | 另一将领/装备 HD 页按宿主 id 刷新装备信息。 | host_id=method-local selected host id v7/v8 | high |
| `reqGeneralEquipLevelup` | `LscriptPages/game/z;->W0()I@0x0502` | 自动强化 20 次循环中的下一次普通强化。 | host_id=z.I1; equipment_id=z.H1; levelup_mode=0/normal=const 0 | high |
| `reqGeneralEquipLevelup` | `LscriptPages/game/z;->W0()I@0x0664` | 强化弹窗普通强化按钮。 | host_id=z.I1; equipment_id=z.H1; levelup_mode=0/normal=const 0 | high |
| `reqGeneralEquipLevelup` | `LscriptPages/game/z;->W0()I@0x0692` | 启动自动“强化20次”时先发的一次普通强化。 | host_id=z.I1; equipment_id=z.H1; levelup_mode=0/normal=const 0 | high |
| `reqGeneralEquipLevelup` | `LscriptPages/game/z;->W0()I@0x078a` | 特殊强化确认后发起强化。 | host_id=z.I1; equipment_id=z.H1; levelup_mode=1/special=const 1 | medium-high |

## 6. 面向服务端重建的边界

- `host_id` 必须是装备所属/目标宿主对象 id，高概率就是将领/可装备对象 id；它用于服务端判断装备归属、目标槽位和属性刷新对象。
- `equipment_id` 是装备实例 id，不是模板 id；模板、品质、强化等级等由客户端本地/同步字段展示，但请求只传实例 id。
- `action_type=0` 是装备/换装；`action_type=1` 是卸装。客户端不会提交槽位，槽位应由服务端根据装备模板类型和宿主当前状态裁定。
- `levelup_mode=0` 是普通强化，自动“强化20次”仍是循环普通强化；`levelup_mode=1` 是特殊强化，具体消耗/成功规则仍待动态表或样本确认。
- `z.C3` 不是请求参数，只是操作后的 UI 刷新上下文。

## 7. 推断与置信度

- 高置信：`E0(J)` 的参数为 `host_id`。
- 高置信：`C0(J,J,I)` 的参数为 `host_id, equipment_id, action_type`。
- 高置信：`G0(J,J,I)` 的参数为 `host_id, equipment_id, levelup_mode`。
- 中高置信：`host_id` 的最终业务名大概率是 `general_id`，但为了兼容 type0 宿主表和可能的其他可装备对象，当前文档仍采用更稳妥的 `host_id/current_general_id candidate`。

## 8. 建议下一步

1. 沿 `scriptPages/game/z` 将领/装备详情 UI 继续给 `Lo/a.b6` 宿主对象字段命名，特别是装备后属性刷新字段。
2. 继续拆 `Lo/a.bv/cv/dv`、`scriptPages/data/i`、`scriptPages/data/g`，建立全局状态字段字典。
3. 后续若能获得 `0xe27f` 样本，再解析动态 `Lo/a.bo`，补齐特殊强化/炼魂/附加效果边界。
