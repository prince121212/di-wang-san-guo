# 山贼系统规则第一版

- 日期：2026-07-05
- 输出目录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/bandit_system`

## 1. 结论摘要

- `reqThiefList / 0x1540 / 5440` 是山贼地图列表请求，请求体为 `x/writeShort`、`y/writeShort`。
- 单次请求不是返回全图，而是按当前坐标/区域返回一批山贼；全图数据需要多点枚举并按 `target_id` 去重。
- 现有全图扫描共去重 `5224` 伙山贼，等级范围 `1..10`，坐标范围 x=`0..184`，y=`0..55`。
- 后一次 corrected 扫描的元信息显示全图去重 `5424` 伙，但该目录只保留了修正后的 7 级明细；因此本报告的 7 级分析基于 corrected `596` 伙，且其中将领守军大类全为弓弩的只有 `4` 伙。

## 2. 协议入口

|协议|opcode|入口方法|请求体|
|---|---:|---|---|
|reqThiefList|0x1540 / 5440|`LscriptPages/game/p;->k1(I,I)V`|`x/writeShort; y/writeShort`|

证据文件：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_expedition/scriptPages_game_p__k1__0x30e790.smali.txt`。

样本 `bandit_0x1540_summary.csv` 显示：`query_x=91, query_y=26` 时返回 11 伙，覆盖 `x=91..93, y=26..31`；其他样本也呈现区域批量返回。

## 3. 各等级统计

|等级|数量|资源1范围/均值|资源2范围/均值|守军数|主要描述|兵种大类|
|---:|---:|---|---|---|---|---|
|1|501|40..60 / 49.84|100..150 / 124.0|1|一些资源,:466 | 一些资源,有装备,:35|步兵|
|2|493|80..100 / 90.46|200..300 / 249.82|1|许多资源,:462 | 许多资源,有装备,:31|步兵|
|3|510|140..160 / 150.48|300..400 / 353.05|1|很多资源,:255 | 许多资源,:222 | 很多资源,有装备,:20 | 许多资源,有装备,:13|步兵|
|4|576|150..180 / 165.21|400..500 / 449.54|2|很多资源,:469 | 很多资源,有宝箱,:41 | 很多资源,有装备,:40 | 很多资源,一些宝物,:21 | 很多资源,有宝箱,一些宝物,:2 | 很多资源,有装备,一些宝物,:2|步兵|
|5|544|250..300 / 276.41|600..800 / 700.73|2|很多资源,:303 | 大量资源,:91 | 很多资源,有装备,:47 | 很多资源,有宝箱,:35 | 很多资源,一些宝物,:21 | 大量资源,一些宝物,:12|弓弩;步兵;骑兵|
|6|526|300..400 / 352.61|800..1000 / 899.76|3|大量资源,:197 | 大量资源,有宝箱,:128 | 大量资源,一些宝物,:92 | 大量资源,有宝箱,一些宝物,:54 | 大量资源,有装备,:27 | 大量资源,有宝箱,有装备,:14|弓弩;步兵;骑兵|
|7|558|500..700 / 598.68|1400..1700 / 1551.13|2;3|大批资源,有宝箱,:260 | 大批资源,:194 | 大批资源,有宝箱,有装备,:33 | 大批资源,有装备,:27 | 大批资源,有宝箱,一些宝物,:21 | 大批资源,一些宝物,:15|弓弩;步兵;骑兵|
|8|501|900..1100 / 1000.13|2250..2750 / 2507.37|2;3;4|大批资源,:188 | 大批资源,有宝箱,:169 | 大批资源,有装备,:46 | 大批资源,有宝箱,有装备,:40 | 大批资源,一些宝物,:26 | 大批资源,有宝箱,一些宝物,:22|战车;骑兵|
|9|516|1400..1800 / 1595.02|3602..4400 / 3993.4|2;4|大批资源,有宝箱,:201 | 大批资源,:109 | 大批资源,有宝箱,一些宝物,:83 | 大批资源,一些宝物,:53 | 大批资源,有宝箱,有装备,:33 | 大批资源,有宝箱,有装备,一些宝物,:19|战车;骑兵|
|10|499|1801..2200 / 2005.78|4500..5486 / 5007.62|3;5|大批资源,有宝箱,一些宝物,:200 | 大批资源,有宝箱,:125 | 大批资源,有宝箱,有装备,一些宝物,:63 | 大批资源,有宝箱,有装备,:44 | 大批资源,一些宝物,:29 | 大批资源,有装备,一些宝物,:13|弓弩;战车;骑兵|

## 4. 7级纯弓弩山贼

|target_id|坐标|资源|掉落ID|守军|
|---:|---|---|---|---|
|2469146|(18,49)|699/1605||马卫芮:弓弩(raw=1,sub=1)x1112 | 浦蕴枫:弓弩(raw=1,sub=1)x1152 | 融恩瑞:弓弩(raw=1,sub=1)x1119|
|2472680|(34,4)|693/1674||容瑞:弓弩(raw=1,sub=1)x1146 | 谈冬:弓弩(raw=1,sub=1)x1283 | 柯寒瑾:弓弩(raw=1,sub=1)x1100|
|2468200|(103,7)|546/1481||仰红小:弓弩(raw=1,sub=1)x1237 | 濮熙:弓弩(raw=1,sub=1)x1102 | 满悌:弓弩(raw=1,sub=1)x1110|
|2467599|(181,8)|640/1699||花民:弓弩(raw=1,sub=1)x1117 | 王铃:弓弩(raw=1,sub=1)x1215 | 公羊修:弓弩(raw=1,sub=1)x1156|

## 5. 掉落 ID 映射

已将 `loot_ids` 与 `item_full_mapping.csv` 联动，生成 `bandit_loot_id_mapping.csv` 和带编码候选的 `bandit_loot_id_mapping_enriched.csv`。注意：山贼 `loot_ids` 多数不是直接 item_id，可能是带前缀/类型位的复合编码，因此解码候选只作为后续验证线索。Top 掉落如下：

|loot_id|出现次数|等级|直接道具名|解码候选|
|---:|---:|---|---|---|
|1793|300|8;9;10|||
|1064|254|7;8;9||low10:40:新手礼包4[礼包/宝箱/资源包] | minus1024:40:新手礼包4[礼包/宝箱/资源包]|
|1069|242|8;9||low10:45:新手礼包9[礼包/宝箱/资源包] | minus1024:45:新手礼包9[礼包/宝箱/资源包]|
|1084|239|10||low10:60:白银宝箱[礼包/宝箱/资源包] | minus1024:60:白银宝箱[礼包/宝箱/资源包]|
|1059|222|6;7;8||low10:35:玄铁[装备强化材料] | minus1024:35:玄铁[装备强化材料]|
|1074|217|9;10||low10:50:70级兵盔箱[礼包/宝箱/资源包] | minus1024:50:70级兵盔箱[礼包/宝箱/资源包]|
|13569|105|4;5;6;7||low10:257:活血丹包[礼包/宝箱/资源包]|
|1039|104|2;3;4||low10:15:九转金丹[普通/功能道具] | minus1024:15:九转金丹[普通/功能道具]|
|14849|92|6;7||low10:513:袁术碎片[任务物品]|
|1054|86|5;6;7||low10:30:火药桶[普通/功能道具] | minus1024:30:火药桶[普通/功能道具]|
|1044|84|3;4;5||low10:20:招贤令[普通/功能道具] | minus1024:20:招贤令[普通/功能道具]|
|4097|73|4;5;6||low10:1:屯田令[生产/内政增益] | low12:1:屯田令[生产/内政增益] | minus4096:1:屯田令[生产/内政增益]|
|29441|73|9;10|||
|1049|66|4;5;6||low10:25:鲁公宝典[增益/加速道具] | minus1024:25:鲁公宝典[增益/加速道具]|
|1034|61|1;2;3||low10:10:传音符小礼包[礼包/宝箱/资源包] | minus1024:10:传音符小礼包[礼包/宝箱/资源包]|
|3073|58|6;7;8;9;10||low10:1:屯田令[生产/内政增益] | minus3072:1:屯田令[生产/内政增益]|
|13570|32|6;7||low10:258:兵书包[礼包/宝箱/资源包]|
|3074|24|10||low10:2:高级屯田令[生产/内政增益] | minus3072:2:高级屯田令[生产/内政增益]|
|1083|19|10||low10:59:青铜钥匙[礼包/宝箱/资源包] | minus1024:59:青铜钥匙[礼包/宝箱/资源包]|
|1078|18|10||low10:54:高级粮食辎重[礼包/宝箱/资源包] | minus1024:54:高级粮食辎重[礼包/宝箱/资源包]|
|1081|18|10||low10:57:中级资源辎重[礼包/宝箱/资源包] | minus1024:57:中级资源辎重[礼包/宝箱/资源包]|
|16777217|17|1;2||low10:1:屯田令[生产/内政增益] | low12:1:屯田令[生产/内政增益]|
|1080|16|10||low10:56:中级粮食辎重[礼包/宝箱/资源包] | minus1024:56:中级粮食辎重[礼包/宝箱/资源包]|
|1068|15|8;9||low10:44:新手礼包8[礼包/宝箱/资源包] | minus1024:44:新手礼包8[礼包/宝箱/资源包]|
|1031|13|1;2||low10:7:精铁宝箱[礼包/宝箱/资源包] | minus1024:7:精铁宝箱[礼包/宝箱/资源包]|
|1065|12|8;9||low10:41:新手礼包5[礼包/宝箱/资源包] | minus1024:41:新手礼包5[礼包/宝箱/资源包]|
|1030|12|1;2||low10:6:迁封令[普通/功能道具] | minus1024:6:迁封令[普通/功能道具]|
|16779777|12|8;9;10||low10:513:袁术碎片[任务物品]|
|1077|12|10||low10:53:实木宝箱[礼包/宝箱/资源包] | minus1024:53:实木宝箱[礼包/宝箱/资源包]|
|1067|12|8;9||low10:43:新手礼包7[礼包/宝箱/资源包] | minus1024:43:新手礼包7[礼包/宝箱/资源包]|

## 6. 对服务端重建的影响

1. 山贼列表接口应按区域/视野返回部分山贼，而不是一次性返回全图。
2. 每伙山贼至少需要字段：`target_id/name/level/x/y/desc/resource1/resource2/loot_ids/unit_count/units`。
3. `resource1/resource2` 在地图列表中已经下发，具体名称从战报看对应铜钱/粮食候选；最终奖励还包括声望与任务物品，需要通过战报/结算继续补公式。
4. 守军大类可归并为步兵、弓弩、骑兵、战车；7级山贼固定 3 个将领/守军槽，10级样本为 5 个。
5. 掉落概率尚不能从单次地图列表直接确认；当前只能统计“可能掉落/展示掉落 ID”和全图样本出现频率。

## 7. 结构化输出

- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/bandit_system/bandit_all_unique_enriched.csv`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/bandit_system/bandit_level_stats.csv`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/bandit_system/bandit_unit_category_combo_stats.csv`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/bandit_system/bandit_loot_id_mapping.csv`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/bandit_system/bandit_loot_id_mapping_enriched.csv`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/bandit_system/level7_all_units_raw.csv`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/bandit_system/level7_pure_archer_major.csv`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/bandit_system/bandit_system_summary.json`