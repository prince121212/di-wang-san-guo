# `scriptPages/data/d` 装备容器字段与 accessor 字典（第一版）

生成时间：2026-07-05  
目标：把 `V5/c6` 写入的装备字段映射到客户端展示/计算 accessor；当前不实现服务端。

## 1. 产物

- accessor 字典：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/data_d_accessor_dictionary.csv`
- 字段字典：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/data_d_field_dictionary.csv`
- UI 语义证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/data_d_ui_evidence.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/data_d_equipment_accessors_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/data_d_accessor_summary.json`
- 自动化脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_data_d_equipment_accessors.py`

## 2. 已验证事实

- `scriptPages/data/d` 是二维装备容器，字段 `d/e/f/g/h/i/j/l/m` 第一维固定 2：bank0 由 `Lo/a.V5` 全量重建，bank1 由 `Lo/a.c6` 增量维护。
- `<clinit>` 明确初始化属性名：攻击、生命、防御、统兵；品质名：普通、良好、优秀、卓越。
- `y(J)` 是所有按装备实例 id 查询的定位器，命中后写入静态 `n=bank`、`o=slot`。
- `D/o/w/l/z/n/F` 等 accessor 均以 `e[bank][slot]` 装备模板 id 为入口，转到 `Lo/a.Mn/Pn/Kn/Nn` 等静态装备表。
- `d/E/j/i/c/h` 等 accessor 使用 `e`、`f[0]`、`f[1]` 推导基础属性、强化贡献和展示文案。
- `scriptPages/game/z.j()` 装备页给出关键 UI 证据：强化材料、强化效果、强化成功率、强化保底次数、失败掉级率/失败损毁率。

## 3. 字段字典

| field | type | name_candidate | role | confidence |
| --- | --- | --- | --- | --- |
| LscriptPages/data/d;->a | [String] | 静态属性名表 | 攻击/生命/防御/统兵；按 Lo/a.S4(e) 的属性类型索引。 | high |
| LscriptPages/data/d;->b | [String] | 静态品质名表 | 普通/良好/优秀/卓越；由 f[bank][slot][0] 索引。 | high |
| LscriptPages/data/d;->c | String | 空字符串/全局显示缓存候选 | 初始化为空；被少量 UI 读取，语义待复核。 | low |
| LscriptPages/data/d;->d | [[J] | 装备实例 id | bank0 由 V5 全量重建；bank1 由 c6 维护。 | high |
| LscriptPages/data/d;->e | [[S] | 装备模板 id | 用于 g3/S4/z1 等静态装备表映射名称、图标、属性类型、基础值。 | high |
| LscriptPages/data/d;->f | [[[B] | 品质与强化向量 | f[][0]=品质 index；f[][1]=强化等级/强化值。 | high |
| LscriptPages/data/d;->g | [[S] | 强化效果百分比候选 | 装备页以 g/100 + "." + g%100 + "%" 形式显示“强化效果”。 | high |
| LscriptPages/data/d;->h | [[[B] | 强化失败风险向量 | p(J,false) 返回 h[][0]，装备页显示失败掉级率/失败损毁率百分比；h[][1] 未命名。 | high |
| LscriptPages/data/d;->i | [[[I] | 强化保底次数向量 | 装备页显示“强化保底次数”并读取 i[][0]/i[][1]。 | high |
| LscriptPages/data/d;->j | [[S] | 协议 short 参数 | V5/c6 读取并重置；未发现 data.d accessor 使用，语义待复核。 | low |
| LscriptPages/data/d;->k | [J] | bank1 宿主反链 | c6 写入 host_id；r(J) 对 bank1 返回该 host_id。 | high |
| LscriptPages/data/d;->l | [[String] | 装备额外文本/描述 | A(J) 返回原文，s(J) 去掉 <#> 标签后显示。 | high |
| LscriptPages/data/d;->m | [[I] | 内部标志/状态 | V5/c6 初始化为 0；未发现 UI 语义，待复核。 | low |
| LscriptPages/data/d;->n | int | locator bank | y(J) 设置的当前命中 bank。 | high |
| LscriptPages/data/d;->o | int | locator slot | y(J) 设置的当前命中 slot。 | high |

## 4. Accessor 字典

| method | code_off | kind | role | confidence | external_call_count |
| --- | --- | --- | --- | --- | --- |
| LscriptPages/data/d;->g()I | 0x262004 | capacity accessor | 返回 bank0 数组长度。 | high | 6 |
| LscriptPages/data/d;->x(J)I | 0x262290 | effect accessor | 按 e 在 Un[] 中查找并返回 Vn[]；装备页拼接 equipEffectN 资源名。 | medium | 4 |
| LscriptPages/data/d;->B(J)[S | 0x262a88 | extra material/effect accessor | 返回 bo[S4(e)][quality] 的 [id,value]；被炼魂/装备效果相关入口调用，语义待复核。 | medium | 3 |
| LscriptPages/data/d;->f(II)[J | 0x2627a4 | filter accessor | 按装备属性/部位候选 S4(e)==arg0 过滤，并用 mask bit0/bit1 合并 bank0/bank1。 | high | 12 |
| LscriptPages/data/d;->r(J)J | 0x262740 | host accessor | 若装备在 bank1，返回 k[slot] host_id；否则返回 -1。 | high | 22 |
| LscriptPages/data/d;-><clinit>()V | 0x262b3c | initializer | 初始化属性名表 a=[攻击,生命,防御,统兵]、品质名表 b=[普通,良好,优秀,卓越]、空字符串 c。 | high | 0 |
| LscriptPages/data/d;->G()V | 0x262df4 | initializer | 初始化装备容器并行数组 d/e/f/g/h/i/j/l/m，第一维固定 2 个 bank。 | high | 2 |
| LscriptPages/data/d;->C()[J | 0x26292c | list accessor | 返回 bank1 中非负装备 id 列表；c6 维护 bank1。 | high | 17 |
| LscriptPages/data/d;->e()[J | 0x262774 | list accessor | 返回 bank0 装备 id 数组；V5 全量重建 bank0。 | high | 37 |
| LscriptPages/data/d;->y(J)V | 0x262d7c | locator | 按装备实例 id 在 bank0/bank1 中查找，命中后设置静态 n=bank、o=slot。 | high | 7 |
| LscriptPages/data/d;->a(J)V | 0x262c14 | mutator | 按 bank1 host backlink k==host_id 删除 bank1 装备记录。 | high | 4 |
| LscriptPages/data/d;->b(J)V | 0x262cc8 | mutator | 按 equipment_id 删除 bank1 装备记录。 | high | 2 |
| LscriptPages/data/d;->H(Ljava/lang/String;)V | 0x262e58 | parser | 读取 Lo/a.Tn/Un/Vn 三组 short 表；x(J) 用 Un->Vn 映射装备特效资源/效果 id。 | medium | 1 |
| LscriptPages/data/d;->t(J)I | 0x262204 | quality accessor | 返回 f[bank][slot][0]，品质 index；u(J) 用它映射普通/良好/优秀/卓越。 | high | 30 |
| LscriptPages/data/d;->u(J)Ljava/lang/String; | 0x262654 | quality accessor | 返回品质名称 b[t(id)]。 | high | 23 |
| LscriptPages/data/d;->v(I)Ljava/lang/String; | 0x262688 | quality helper | 按品质 index 返回 b[] 名称。 | high | 6 |
| LscriptPages/data/d;->m(J)I | 0x26211c | raw accessor | 返回装备模板/静态配置 id：e[bank][slot]。 | high | 2 |
| LscriptPages/data/d;->p(JZ)I | 0x262184 | risk accessor | 返回 h[bank][slot][index]；当前 UI 只用 index=false/0 显示失败掉级率/失败损毁率百分比。 | high | 2 |
| LscriptPages/data/d;->E(J)I | 0x26233c | stat accessor | 返回强化贡献：f[1] * y2(S4(e))[quality_index]。 | high | 3 |
| LscriptPages/data/d;->d(J)I | 0x261fc0 | stat accessor | 返回 Lo/a.z1(e)，即装备基础属性值。 | high | 3 |
| LscriptPages/data/d;->i(J)Ljava/lang/String; | 0x262500 | stat accessor | 返回格式化属性文案：w2(S4(e), 基础值+强化贡献)。 | high | 10 |
| LscriptPages/data/d;->j(J)I | 0x262034 | stat accessor | 返回总属性值：基础值 z1(e) + 强化贡献。 | high | 3 |
| LscriptPages/data/d;->c(SII)Ljava/lang/String; | 0x262418 | stat helper | 按模板 id、quality_index、强化值生成 “(基础值+强化值)” 说明。 | high | 8 |
| LscriptPages/data/d;->h(SII)Ljava/lang/String; | 0x262498 | stat helper | 按模板 id、quality_index、强化值生成格式化属性文案。 | high | 8 |
| LscriptPages/data/d;->q(J)I | 0x2621c4 | strength accessor | 返回 f[bank][slot][1]，强化等级/强化值候选；强化页用 >=10/>=20 控制失败掉级/损毁文案。 | high | 30 |
| LscriptPages/data/d;->k(J)[S | 0x2629c4 | strength material accessor | 返回强化材料 [item_id, amount]；装备页显示“强化材料”并检查 Lo/a.p1(item_id) 库存。 | high | 6 |
| LscriptPages/data/d;->D(J)Ljava/lang/String; | 0x2626f0 | template accessor | 返回装备名称：Mn[g3(e)]。 | high | 20 |
| LscriptPages/data/d;->F(J)I | 0x2623c8 | template accessor | 返回 Nn[g3(e)]；候选为装备等级/品质阶/限制字段，需结合调用点继续命名。 | medium | 15 |
| LscriptPages/data/d;->l(I)I | 0x2620f0 | template accessor | 按模板 id 返回 Pn[g3(template_id)]；与 w(J) 同源。 | medium | 5 |
| LscriptPages/data/d;->n(I)I | 0x262158 | template accessor | 按模板 id 返回 Kn[g3(template_id)]；与 z(J) 同源。 | medium | 5 |
| LscriptPages/data/d;->o(I)Ljava/lang/String; | 0x2625bc | template accessor | 按模板 id 返回装备名称：Mn[g3(template_id)]。 | high | 18 |
| LscriptPages/data/d;->w(J)I | 0x262244 | template accessor | 返回 Pn[g3(e)]；在装备页用于 r0.E(...) 绘制图标，候选为图标/资源类别 id。 | medium | 16 |
| LscriptPages/data/d;->z(J)I | 0x2622ec | template accessor | 返回 Kn[g3(e)]；多处用于装备展示/筛选，候选为装备部位/大类/颜色字段。 | medium | 18 |
| LscriptPages/data/d;->A(J)Ljava/lang/String; | 0x2626b0 | text accessor | 返回 l[bank][slot] 原始字符串，空时返回空串。 | high | 3 |
| LscriptPages/data/d;->s(J)Ljava/lang/String; | 0x2625e8 | text accessor | 把 A(J) 按换行与 <#> 拆分，返回清洗后的多行描述。 | high | 2 |

## 5. 关键 UI 语义证据

| evidence_method | offsets | strings_or_calls | interpretation |
| --- | --- | --- | --- |
| LscriptPages/data/d;-><clinit>() | 0x000a/0x0022/0x0038/0x004e | `di_攻击`、`di_生命`、`di_防御`、`di_统兵` | 属性名表 a[]。 |
| LscriptPages/data/d;-><clinit>() | 0x006c/0x0080/0x0094/0x00a8 | `di_普通`、`di_良好`、`di_优秀`、`di_卓越` | 品质名表 b[]。 |
| LscriptPages/game/z;->j()V | 0x0b50-0x0b9e | `di_强化材料` + data.d.k(J) | k(J) 返回强化材料 item_id/amount，并用 Lo/a.p1 检查库存。 |
| LscriptPages/game/z;->j()V | 0x0c9c-0x0d0c | `di_强化效果` + data.d.g | g[bank][slot] 按百分比显示。 |
| LscriptPages/game/z;->j()V | 0x0e50-0x0f1c | `di_强化成功率`、`di_强化保底次数` + data.d.i | i[bank][slot][0/1] 是强化保底次数候选。 |
| LscriptPages/game/z;->j()V | 0x0f48-0x0fbc | `di_失败掉级率` / `di_失败损毁率` + data.d.p(J,false) | h[bank][slot][0] 是失败风险百分比候选。 |
| LscriptPages/game/z;->j()V | 0x0922-0x0950 | `equipEffect` + data.d.x(J) | x(J) 返回装备特效资源编号。 |

## 6. 面向服务端重建的紧凑装备记录候选

```text
equipment_record_common (bank0 in V5, bank1 in c6):
  long  instance_id        -> data.d.d[bank][slot]
  short template_id        -> data.d.e[bank][slot]
  byte  vector_len
  byte[vector_len] f       -> f[0]=quality_index, f[1]=strength_level/value
  short strengthen_effect  -> data.d.g[bank][slot], UI 显示为百分比
  byte  risk_or_flag_0     -> data.d.h[bank][slot][0], UI 显示失败风险百分比
  byte  risk_or_flag_1     -> data.d.h[bank][slot][1], 未命名
  short protocol_j         -> data.d.j[bank][slot], 未命名
  short pity_current       -> data.d.i[bank][slot][0]
  short/int pity_target    -> data.d.i[bank][slot][1]
  UTF   extra_text         -> data.d.l[bank][slot]
  if bank1: long host_id   -> data.d.k[slot] (由 c6 写入，不在单条装备字段内)
```

注意：上面是客户端状态字段合同，不等于最终服务端权威字段名；强化材料表来自客户端静态表 `Lo/a.ao/bo/y2` 等，仍需继续拆 `Lo/a` 装备静态表加载来源。

## 7. 推断与置信度

- **高置信**：`f[0]` 是品质 index，`u/v` 映射到普通/良好/优秀/卓越。
- **高置信**：`f[1]` 是强化等级/强化值候选，参与强化贡献、强化材料数量和失败风险阈值。
- **高置信**：`g` 是强化效果百分比字段，客户端按 `g/100.g%100%` 显示。
- **高置信**：`i[0]/i[1]` 是强化保底次数相关字段。
- **中置信**：`z/n` 的 `Kn` 字段是装备部位/大类/颜色中的一种；调用场景多，需结合 UI 文本继续命名。
- **低置信**：`j` 与 `m` 当前仅见同步/重置，未发现明确展示语义。

## 8. 建议下一步

1. 继续拆 `Lo/a.g3/S4/z1/y2/w2/l3` 与 `Mn/Kn/Ln/Nn/Pn/ao/bo` 的加载来源，形成装备静态表字段字典。
2. 展开 `0x8250/0x8252/0x8254` 响应，确认装备强化/炼魂/穿戴操作的状态码和同步块顺序。
3. 用 `scriptPages/game/z.W0/a/j` 串起强化材料、成功率、失败率的完整客户端展示公式。
