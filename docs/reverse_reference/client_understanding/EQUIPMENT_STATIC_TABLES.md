# 装备静态表来源与字段字典（第一版）

生成时间：2026-07-05  
目标：补齐 `scriptPages/data/d` 装备容器背后的静态模板、类型、强化材料、属性文案与联网 `bo` 配置来源；当前只做本地离线客户端理解，不重建服务端。

## 1. 产物

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/EQUIPMENT_STATIC_TABLES.md`
- 加载字段顺序：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_template_loader_fields.csv`
- 静态字段字典：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_static_field_dictionary.csv`
- helper/accessor 字典：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_helper_methods.csv`
- 模板实值表 scriptEquip.sc：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_template_static_values.csv`
- 类型/强化实值表 scriptEquipType.sc：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_type_static_values.csv`
- 属性文案实值表 scriptEquipEffect.sc：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_effect_text_values.csv`
- 特效图标实值表 scriptEquipIconEffect.sc：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_icon_effect_values.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_static_tables_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/equipment_static_extraction_summary.json`

## 2. 已验证加载链路

- `LscriptPages/data/g;->c3()V` 是 APK/RMS 脚本主加载器：`ue[index]` 文件名对应 RMS record `index+2`；当资源缓存过期时从 `/script/<name>` 加载。
- 装备核心静态表在 `c3()` 后半段按 record id 分支读取：
  - record `4` / `scriptEquip.sc`：模板主表，写入 `Lo/a.In/Jn/Kn/Ln/Mn/Nn/On/Pn`。
  - record `5` / `scriptEquipType.sc`：装备类型、强化倍率、强化材料，写入 `Lo/a.Wn/Xn/Yn/Zn/ao`。
  - record `6` / `scriptEquipEffect.sc`：属性文案模板，写入 `Lo/a.Qn/Rn/Sn`。
  - record `25` / `scriptEquipIconEffect.sc`：特殊装备效果图标映射，由 `LscriptPages/data/d;->H(String)` 写入 `Lo/a.Tn/Un/Vn`。
- `Lo/a.bo` 不在上述本地脚本中加载，而由 `0xe27f -> LscriptPages/data/g;->s4(String)` 从服务端响应写入；请求入口是 `LscriptPages/data/g;->b2(J,J)`，当 `bo == null` 时发送 `0x627f`，payload 为单字节 `0`。

## 3. `scriptEquip.sc` 模板主表

- 已解析模板数：`161`，template id 范围：`0..160`，唯一 id 数：`161`。
- `Nn` 属性类型分布：`0:58, 1:32, 2:35, 3:36`；结合 `scriptEquipType.sc` 与 `data.d.a[]`：`0=武器/攻击`、`1=头盔/生命`、`2=铠甲/防御`、`3=坐骑/统兵`。
- `Jn` 为 true 的行数：`24`；集中在倚天剑、青釭剑、青龙偃月刀、神兽装备、名马等，候选为“名品/稀有装备标记”。
- `On` 非空描述行数：`17`；`reserved_tail_byte` 分布：`0:161`。
- 关键字段顺序：`short In`、`UTF Mn`、`short Nn`、`byte Jn`、`UTF On`、`byte Kn`、`short Ln`、`short Pn`、`byte reserved`。
- `Kn` 已由 `gameHD/b.C` 的 `re_装备等级` / “等级”标签验证为装备等级；`Ln` 是基础属性；`Pn` 是图标资源 id。

模板样例：

| id | 名称 | 类型 | 等级 | 基础值 | 图标 | Jn | 描述 |
|---:|---|---|---:|---:|---:|---:|---|
| 0 | 短剑 | 武器 | 1 | 10 | 797 | 0 |  |
| 1 | 板斧 | 武器 | 3 | 13 | 791 | 0 |  |
| 2 | 铜锤 | 武器 | 6 | 16 | 784 | 0 |  |
| 3 | 斩马刀 | 武器 | 9 | 19 | 787 | 0 |  |
| 4 | 铁胎弓 | 武器 | 12 | 22 | 813 | 0 |  |
| 5 | 亮银枪 | 武器 | 15 | 25 | 804 | 0 |  |
| 155 | 尊·天子剑 | 武器 | 99 | 200 | 12634 | 0 |  |
| 156 | 尊·帝王剑 | 武器 | 99 | 200 | 12635 | 0 |  |
| 157 | 尊·青龙偃月刀 | 武器 | 99 | 200 | 12636 | 0 |  |
| 158 | 尊·赤兔 | 坐骑 | 99 | 350 | 12637 | 0 |  |
| 159 | 尊·龙冠 | 头盔 | 99 | 200 | 12638 | 0 |  |
| 160 | 尊·皇袍 | 铠甲 | 99 | 150 | 12639 | 0 |  |

## 4. `scriptEquipType.sc` 类型/强化表

| type_id(Wn) | 名称(Xn) | 文案组(Yn) | 强化倍率 Zn[品质] | 强化材料 ao[品质] |
|---:|---|---:|---|---|
| 0 | 武器 | 0 | `[3, 5, 7, 10]` | `[{"quality_index": 0, "item_id": 3, "base_amount_per_100": 100}, {"quality_index": 1, "item_id": 34, "base_amount_per_100": 100}, {"quality_index": 2, "item_id": 35, "base_amount_per_100": 100}, {"quality_index": 3, "item_id": 119, "base_amount_per_100": 100}]` |
| 1 | 头盔 | 8 | `[3, 5, 7, 10]` | `[{"quality_index": 0, "item_id": 3, "base_amount_per_100": 50}, {"quality_index": 1, "item_id": 34, "base_amount_per_100": 50}, {"quality_index": 2, "item_id": 35, "base_amount_per_100": 50}, {"quality_index": 3, "item_id": 119, "base_amount_per_100": 50}]` |
| 2 | 铠甲 | 9 | `[1, 2, 3, 5]` | `[{"quality_index": 0, "item_id": 3, "base_amount_per_100": 50}, {"quality_index": 1, "item_id": 34, "base_amount_per_100": 50}, {"quality_index": 2, "item_id": 35, "base_amount_per_100": 50}, {"quality_index": 3, "item_id": 119, "base_amount_per_100": 50}]` |
| 3 | 坐骑 | 10 | `[3, 8, 12, 20]` | `[{"quality_index": 0, "item_id": 120, "base_amount_per_100": 100}, {"quality_index": 1, "item_id": 121, "base_amount_per_100": 100}, {"quality_index": 2, "item_id": 122, "base_amount_per_100": 100}, {"quality_index": 3, "item_id": 123, "base_amount_per_100": 100}]` |

客户端公式证据：

```text
data.d.E(equipment_id) = f[bank][slot][1] * Lo/a.Zn[l3(S4(template_id))][quality]
data.d.j(equipment_id) = Lo/a.Ln[g3(template_id)] + data.d.E(equipment_id)
data.d.k(equipment_id) = [ao[type][quality][0], max(1, ao[type][quality][1] * (strengthen_value + 1) / 100)]
```

## 5. `scriptEquipEffect.sc` 属性文案模板

`Lo/a.w2(type_id, value)` 的路径是：`type_id -> l3 -> Yn -> Qn -> Rn/Sn`，然后把 `Rn` 中的 `#` 替换为数值。当前表内 `Sn` 均为 `1`。

| Qn | flag | 文案模板 |
|---:|---:|---|
| 0 | 1 | 增加将领#点攻击力 |
| 1 | 1 | 增加将领#点统帅 |
| 2 | 1 | 增加将领#点统帅 |
| 3 | 1 | 增加将领#点统帅 |
| 4 | 1 | 增加将领#%统帅 |
| 5 | 1 | 增加将领#%统帅 |
| 6 | 1 | 增加将领#%统帅 |
| 7 | 1 | 增加将领#点突围能力 |
| 8 | 1 | 增加统帅部队#点生命值 |
| 9 | 1 | 增加将领#点防御力 |
| 10 | 1 | 增加将领#个统兵数. |

## 6. `scriptEquipIconEffect.sc` 特效图标映射

`data.d.x(equipment_id)` 用实例模板 id 在 `Lo/a.Un` 中查找，命中后返回 `Lo/a.Vn`；装备页会拼接 `equipEffectN` 资源名。

| row(Tn) | template_id(Un) | resource_id(Vn) |
|---:|---:|---:|
| 0 | 153 | 12546 |
| 1 | 137 | 12546 |
| 2 | 154 | 12546 |
| 3 | 152 | 12546 |
| 4 | 155 | 12546 |
| 5 | 156 | 12546 |
| 6 | 157 | 12546 |
| 7 | 158 | 12546 |
| 8 | 159 | 12546 |
| 9 | 160 | 12546 |

## 7. `Lo/a.bo` 与 `data.g.s4` 联网配置边界

- `Lo/a.bo [[[S]]` 由 `0xe27f` 响应写入，不是 APK 本地静态脚本的一部分。
- `data.d.B(equipment_id)` 使用 `S4(template_id) -> l3(type_id)` 与品质 index 读取 `bo[type][quality]` 的二元组；越界 quality 会钳到最后一档。
- `s4` 还读取 `data.g.v8/w8/x8/B8/C8/D8/y8/z8/A8`；这些字段大概率是装备强化/炼魂/联网活动配置，但当前本地抓包未命中 `0xe27f`，不能给最终业务名。
- 对未来自建服务端而言，只要客户端触发 `data.g.b2()` 且 `bo == null`，就需要提供 `0xe27f` 响应，否则相关装备入口会停留在“联网数据载入中”。

## 8. 面向服务端重建的装备静态/动态拼接模型

```text
equipment_instance (来自 V5/c6):
  instance_id      -> data.d.d[bank][slot]
  template_id      -> data.d.e[bank][slot]
  quality_index    -> data.d.f[bank][slot][0]
  strengthen_value -> data.d.f[bank][slot][1]
  strengthen_effect_pct / risk / pity / extra_text -> data.d.g/h/i/l

equipment_template (来自 scriptEquip.sc):
  name/level/base_stat/icon/type/description -> Mn/Kn/Ln/Pn/Nn/On

equipment_type (来自 scriptEquipType.sc):
  type_name/effect_group/strength_coeff/material -> Xn/Yn/Zn/ao

online_config (来自 0xe27f):
  bo[type][quality][2] + data.g.* 全局参数
```

## 9. 推断与置信度

- 高置信：`scriptEquip.sc`、`scriptEquipType.sc`、`scriptEquipEffect.sc`、`scriptEquipIconEffect.sc` 的字段顺序与数组写入关系；所有本地脚本已解析到 EOF。
- 高置信：`Nn/Wn` 是装备类型/属性类型，`Kn` 是装备等级，`Ln` 是基础属性，`Pn` 是图标资源 id，`Zn` 参与强化属性贡献，`ao` 参与强化材料数量计算。
- 中置信：`Jn` 是名品/稀有装备标记；依据是 true 行的内容分布，但当前没有发现直接 UI accessor。
- 中低置信：`bo` 与 `data.g.v8/w8/x8/B8/C8/D8/y8/z8/A8` 的具体业务名；已知读取结构和使用入口，但缺少 `0xe27f` 动态响应样本。

## 10. 建议下一步

1. 展开 `0x8250/0x8252/0x8254`，确认装备操作响应中的状态码、`c6/a6/f6/V5/S5` 顺序和刷新边界。
2. 继续串 `scriptPages/game/z.W0/a/j`，把强化成功率、失败掉级/损毁率、保底次数和材料展示公式闭环。
3. 若后续抓包能触发 `0x627f -> 0xe27f`，按 `data.g.s4` schema 解析 `bo` 与全局配置真实值。
