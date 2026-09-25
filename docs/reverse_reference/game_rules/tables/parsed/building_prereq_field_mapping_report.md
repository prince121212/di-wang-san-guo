# 建筑前置条件字段命名报告

- 来源：`scriptBuilding.sc` -> `Lo/a.U5(String)` 真实读流。
- 产物：`building_level_prereq_rules_named.csv`、`building_prereq_field_mapping_summary.json`、`building_level_rules_combined_named.csv`。

## 1. 真实读流

`Lo/a.U5` 中前置条件组的每行 15 字节读法：

```text
level/readByte -> index = level - 1
pn/readShort -> cast byte
qn/readByte
rn/readByte
sn/readShort -> cast byte
tn/readByte
un/readShort -> cast byte
vn/readInt
trailing/readByte -> consumed but not stored
```

## 2. 已确认字段含义

|字段|缓存|访问器/证据|当前语义|置信度|
|---|---|---|---|---|
|`level`|-|`U5 0001fc`, `v7=level-1`|规则等级行|高|
|`qn`|`Lo/a.qn`|`R1(building,level)`；`q.l` 在前置检查中读取|当 `un != -1` 时，作为所需建筑等级|中高|
|`un`|`Lo/a.un`|`q.l 0000d4-00017e` 直接读取|建筑前置类型；`-1` 表示无该类前置|中高|
|`rn`|`Lo/a.rn`|`U5` 存储；本轮样本中 L11-L15 为 20|角色/君主等级或高等级门槛候选|中|
|`trailing`|-|`U5 00029a readByte` 但不缓存|行标记/高等级标志候选；L11-L15 多为 1|中|
|`pn/sn/tn/vn`|`pn/sn/tn/vn`|`S1` 访问 pn；其余暂未完全追完|前置参数/保留字段候选|低-中|

## 3. 样本统计

|字段|唯一值数量|主要值|非默认含义|
|---|---:|---|---|
|`pn_req_building_or_param`|1|0:100||
|`qn_req_level_for_un`|16|1:8, 2:8, 3:8, 4:8, 5:8, 6:8, 7:8, 8:8||
|`rn_req_role_or_gate_level`|2|0:85, 20:15|85 行为 0，15 行为 20，对应 15 级建筑的 L11-L15。|
|`sn_req_building_or_param2`|1|-1:100||
|`tn_req_level2_or_flag`|1|0:100||
|`un_required_building_type_for_q_l`|1|-1:100|本样本全为 -1，q.l 的建筑前置路径静态上存在但当前表未使用。|
|`vn_int_param`|1|0:100||
|`trailing_flag_byte`|2|0:80, 1:20|80 行为 0，20 行为 1，主要出现在超 10 级/部分高等级行。|

## 4. 对服务端重建的影响

- 服务端校验建筑升级时，不能只看成本表；还应读取 `building_level_prereq_rules_named.csv`。
- 当前客户端本地 `q.l` 明确校验的是 `un + qn` 这一组；但当前静态表中 `un` 全为 `-1`，说明实际关键前置可能由服务端权威校验，或由 `rn/trailing` 这类门槛字段体现。
- L11-L15 的 `rn=20` 与 `trailing=1` 很可能是“高等级门槛”，需要后续结合君主等级/大厅等级/都城类型动态验证。

## 5. 当前边界

- `pn/sn/tn/vn` 的精确业务名尚未完全确认；本轮已按 U5 真实字段顺序保留，不再使用旧偏移解释。
- 由于服务端权威，客户端前置校验只可作为 UI 参考；重建服务端必须按自身规则重复校验。
