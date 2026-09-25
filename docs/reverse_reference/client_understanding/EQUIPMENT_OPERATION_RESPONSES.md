# 装备操作响应合同：`0x8250/0x8252/0x8254`（第一版）

生成时间：2026-07-05  
目标：确认装备信息、穿戴/卸下、强化/升级响应如何组合 `c6/a6/f6/V5/S5`，为未来服务端响应合同做准备。

## 1. 产物

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/EQUIPMENT_OPERATION_RESPONSES.md`
- 请求入口表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_operation_requests.csv`
- 响应 schema 表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_operation_response_schema.csv`
- 方法读流/调用摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_operation_method_summary.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_operation_responses_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_operation_response_summary.json`

## 2. 请求入口与响应 handler

| 请求 opcode | 请求方法 | 请求名 | 请求体 | 响应 opcode | 响应 handler |
|---:|---|---|---|---:|---|
| 0x1250 | `LscriptPages/game/z;->E0(J)V` | `reqGeneralEquipInfo` | `writeLong(host_id)` | 0x8250 | `LscriptPages/game/z;->F0(Ljava/lang/String;)V` |
| 0x1252 | `LscriptPages/game/z;->C0(JJI)V` | `reqGeneralEquipCtrl` | `writeLong(host_id); writeLong(equipment_id); writeByte(action_type)` | 0x8252 | `LscriptPages/game/z;->D0(Ljava/lang/String;)V` |
| 0x1254 | `LscriptPages/game/z;->G0(JJI)V` | `reqGeneralEquipLevelup` | `writeLong(host_id); writeLong(equipment_id); writeByte(levelup_mode)` | 0x8254 | `LscriptPages/game/z;->H0(Ljava/lang/String;)V` |

关键请求事实：

- `z.E0(J)` / `reqGeneralEquipInfo` 使用 `Lk/a.r`，实际只写一个 `host_id` 后以 `0x1250` 发送。
- `z.C0(J,J,I)` / `reqGeneralEquipCtrl` 写 `host_id + equipment_id + byte action_type`，以 `0x1252` 发送。
- `z.G0(J,J,I)` / `reqGeneralEquipLevelup` 写 `host_id + equipment_id + byte levelup_mode`，以 `0x1254` 发送，并把 `z.D3` 置 0。
- 参数命名证据详见 `EQUIPMENT_REQUEST_PARAMETER_NAMING.md`：`action_type=0` 为装备/换装，`1` 为卸装；`levelup_mode=0` 为普通强化，`1` 为特殊强化。

## 3. 响应读流与同步组合

### 3.1 `0x8250 -> z.F0`：装备信息刷新

```text
readByte sync_mode
if sync_mode == 0:
  Lo/a.c6(stream)          # 更新 bank1 装备/宿主绑定
else:
  Lo/a.f6(0, stream)       # 全量刷新 type0 对象/将领表
z.z1 = Lo/a.z2(z.I1)       # 重算当前宿主装备 id 列表
```
边界：`0x8250` 不读取 success/message，不调用 `V5/S5`；它更像“打开/刷新某将领装备信息”的轻量同步。

### 3.2 `0x8252 -> z.D0`：装备穿戴/卸下/控制

```text
readBoolean success
readUTF     message
readByte    sync_mode
if sync_mode == 0:
  Lo/a.c6(stream)          # 装备 bank1 增量/宿主绑定
  Lo/a.a6(0, stream)       # 单个 type0 对象/将领增量
else:
  Lo/a.f6(0, stream)       # type0 对象/将领全量表
Lo/a.V5(stream)            # 复合资产块：资源/背包/bank0 装备等
Lo/a.S5(stream)            # 30 槽对象状态表
z.z1 = Lo/a.z2(z.I1)
```
结论：这是装备穿戴/卸下类服务端响应的完整同步形态；未来服务端返回时必须按 `success/message/sync_mode/(c6+a6|f6)/V5/S5` 顺序写流。

### 3.3 `0x8254 -> z.H0`：装备强化/升级

```text
z.D3 = 1
readBoolean success
readUTF     message
readByte    sync_mode
if sync_mode == 0:
  Lo/a.c6(stream)
  Lo/a.a6(0, stream)
else if sync_mode == 1:
  Lo/a.f6(0, stream)
Lo/a.V5(stream)
z.z1 = Lo/a.z2(z.I1)
if success:
  play DEPOT_LEVEL_UP_SUCCESS_EFFECT
if message contains "强化等级→20": analytics/log "强化"
```
边界：`0x8254` 调用 `V5`，但不调用 `S5`；这和 `0x8252` 不同。

## 4. 机器抽取的 schema 行

详见 `equipment_operation_response_schema.csv`；核心结论已经人工整理在第 3 节。

## 5. 面向服务端重建的最小合同

| 响应 | 最小写流顺序 |
|---:|---|
| `0x8250` | `byte sync_mode` + (`c6` if 0 else `f6(0)`) |
| `0x8252` | `boolean success` + `UTF message` + `byte sync_mode` + (`c6`+`a6(0)` if 0 else `f6(0)`) + `V5` + `S5` |
| `0x8254` | `boolean success` + `UTF message` + `byte sync_mode` + (`c6`+`a6(0)` if 0, `f6(0)` if 1, otherwise none) + `V5` |

## 6. 推断与置信度

- 高置信：请求 opcode、请求名、handler、直接读字段顺序、`c6/a6/f6/V5/S5` 组合关系。
- 高置信：`0x8252` 是装备控制/穿戴类完整响应，`0x8254` 是强化/升级响应。
- 中置信：`0x8250` 是指定宿主装备信息刷新；依据是请求名 `reqGeneralEquipInfo` 与只刷新 `c6/f6 + z2(I1)`。
- 高置信：请求参数已经由调用点复核固定为 `host_id/equipment_id/action_type|levelup_mode`；详见 `EQUIPMENT_REQUEST_PARAMETER_NAMING.md`。

## 7. 建议下一步

1. 沿 `scriptPages/game/z` 将领/装备详情 UI 继续给 `Lo/a.b6` 宿主对象字段命名。
2. 继续拆全局状态字段字典：`Lo/a.bv/cv/dv`、`scriptPages/data/i`、`scriptPages/data/g`。
3. 将 `0x8252/0x8254` 的合同合入未来服务端最小响应清单，但暂不实现服务端。
