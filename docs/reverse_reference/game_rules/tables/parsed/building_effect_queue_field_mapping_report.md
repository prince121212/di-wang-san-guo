# 建筑产出/征兵队列字段命名报告

- 来源：`Lo/a.U5` 建筑规则表读取器 + `D1/F1/P1/N1` 访问器 + UI 文案调用点。
- 新增产物：`building_level_effect_rules_named.csv`、`building_recruit_queue_rules_named.csv`、`building_level_rules_server_ready.csv`。

## 1. 字段命名结论

|访问器|缓存数组|UI/代码证据|命名|置信度|
|---|---|---|---|---|
|`D1(building,level)`|`En`|`q.u` 中 `di_标题铜钱` / `di_铜钱产量` 调用 D1|铜钱产量/铜钱加成|高|
|`F1(building,level)`|`Fn`|`q.u` 中 `di_产量` / `di_粮食产量` 调用 F1|粮食产量|高|
|`P1(building,level)`|`Gn`|`q.u` 中 `di_人口上限` / `di_人口加成` 调用 P1|人口上限/人口加成|高|
|`N1(building,level)`|`Hn`|`q.v` 中 `di_标题征兵队列` 后追加 N1|征兵队列数量|高|

## 2. 规则表格式修正

此前报告里把效果组第一个字节粗略称为 `tag=1`。按 `U5` 真实读流，更准确的结构是：

```text
成本组区域：
  group_count/readByte
  每组：group_type/readByte
    group_type=0 -> count/readByte; level + wn/xn/yn/zn 四个 int
    group_type=1 -> count/readByte; level + An/Bn/Cn/Dn 四个 int

产出效果区域：
  group_count/readByte
  每组：group_type/readByte
    group_type=0 -> count/readByte; level + En/Fn/Gn 三个 int

征兵队列区域：
  group_count/readByte
  每组：group_type/readByte
    group_type=0 -> count/readByte; level + Hn byte
```

## 3. 服务端可用含义

- `building_level_rules_server_ready.csv` 是目前最适合服务端重建使用的普通建筑每级规则合并表。
- 大厅主要填 `copper_output_D1_En`。
- 农场主要填 `food_output_F1_Fn`。
- 房屋主要填 `population_capacity_P1_Gn`。
- 兵营类主要填 `recruit_queue_count_N1_Hn`。

## 4. 样例

|建筑|等级|铜钱产量|粮食产量|人口上限|征兵队列|
|---|---:|---:|---:|---:|---:|
|大厅|1|15|0|0||
|大厅|15|1520|0|0||
|房屋|1|0|0|20||
|房屋|15|0|0|1140||
|农场|1|0|25|0||
|农场|15|0|1145|0||
|步兵营|1||||1|
|步兵营|10||||4|

## 5. 当前边界

- `upgrade_time_seconds_candidate` 仍保留 candidate：数值通过静态表稳定恢复，但单位还建议动态包验证。
- 成本字段 A/B/C 从错误码和数值看高度疑似铜钱/粮食/额外成本，其中 C 当前全为 0。
- 建筑产出最终到账仍可能叠加科技、道具 buff、离线时间、仓储上限；这些属于后续资源系统公式。
