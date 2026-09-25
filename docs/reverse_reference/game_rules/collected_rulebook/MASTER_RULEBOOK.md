# 三国·帝王联盟 1.66 基础游戏规则与机制汇总（工作版）

- 生成时间：2026-07-05 06:42:20
- Case：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166`
- 目标：把 APK 离线表、客户端文本、已抓包协议中能确认的基础游戏规则统一收集，为后续服务端重建/规则复现提供索引。
- 置信度标记：`已确认`=有表/文本/抓包直接证据；`部分确认`=字段已定位但业务语义或公式未完全闭环；`待验证`=需要继续动态抓包或方法级反编译。

## 1. 规则资产总览

| 模块 | 当前状态 | 已收集证据 | 下一步缺口 |
|---|---|---|---|
| 基础玩法循环 | 已确认 | FAQ/引导/玩法文本：建设封地→产资源→招兵招将→战斗→奖励→扩张 | 补协议状态流转 |
| 玩家成长 | 部分确认 | 每5级增加将领数；每10级开新封地；35级建军团；30级国库捐献 | 玩家等级经验表/官职表未完整还原 |
| 称号/成就 | 部分确认 | 规则文本、帮助文本、称号宝箱47条、协议入口0x1180/0x1184/0x1186/0x1188/0x118a | 全量称号效果/成就条件数值表待动态响应或配置深解 |
| 资源经济 | 部分确认 | 铜钱、粮食、白银、黄金、声望、资源点/市场/商城文案与抓包 | 资源产量公式、仓储上限、离线结算未闭环 |
| 封地建筑 | 已确认表结构 | 建筑表9条，含大厅/房屋/农场/书院/四兵营/保留项 | 各级升级消耗/耗时字段需继续映射 |
| 科技 | 已确认表结构 | 科技22条，等级/成本/前置记录数已解析 | 部分效果文本 by 字段 与 by tech_id 存在错位，需要以客户端显示/实际效果复核 |
| 兵种 | 高置信 | 16个兵种，四大类、攻防血速、成本/时间/人口字段已提取 | 字段A/字段F语义、战斗公式映射待验证 |
| 将领 | 部分确认 | 招募、成长、忠诚、体力、经验、统帅、装备槽文案；技能表45条 | 将领属性表/名将表/成长公式未完整 |
| 装备 | 部分确认 | 4类装备，11条装备效果 | 装备实例/品质/强化/掉落表未完整 |
| 道具/背包 | 部分确认 | 48条道具效果，礼包/宝箱接口已动态验证 | item_id→道具名完整映射与礼包概率表需继续汇总 |
| 商城 | 已确认动态表 | 在线商城商品166条，购买接口与校验已审 | 活动/限购/充值商品未全审 |
| 副本 | 部分确认 | 副本启动/轮询/宝箱接口已抓；scriptFB 有关卡/奖励文本 | 副本关卡敌军配置表未结构化 |
| 山贼地图 | 较高 | 0x1540局部查询、全图扫描、7级山贼筛选 | 刷新周期/攻击结算/掉落概率未完整 |
| 战斗系统 | 部分确认 | 战法35+、BUFF25、技能45；回放损兵/蓄力/坐标逻辑已定位 | 基础伤害公式可能在服务端；需从更多战报样本拟合或追模拟器路径 |
| 协议接口 | 部分确认 | 商城0x1102、邮件0x1114、山贼0x1540、副本0x1522/0x1702/0x193e、道具0x3144 | 登录/建筑/招兵/出征/任务/联盟等协议待枚举 |

## 2. 已结构化数据表索引

- 数据清单 JSON：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/collected_rulebook/rule_data_inventory.json`
- 数据清单 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/collected_rulebook/rule_data_inventory.csv`

| 分类 | 表 | 记录数 | 字段 |
|---|---|---:|---|
| 战法/战斗 | `analysis/game_rules/battle_tables/bt_book_piece.csv` | 35 | id、名称、字段A、字段B、字段C、raw_tail、offset |
| 战法/战斗 | `analysis/game_rules/battle_tables/bt_book_pro_table.csv` | 4 | id、描述、raw_head、offset、记录长度 |
| 战法/战斗 | `analysis/game_rules/battle_tables/bt_effects.csv` | 25 | id、名称/短名、效果描述、raw_tail、offset |
| 战法/战斗 | `analysis/game_rules/battle_tables/bt_level_texts.csv` | 875 | bt_id、名称、序号、描述/公式 |
| 战法/战斗 | `analysis/game_rules/battle_tables/bt_list_summary.csv` | 35 | id、名称、记录长度、字符串数、核心描述/公式样例、全部文本样例、offset |
| 兵种 | `analysis/game_rules/soldier_table/soldier_values.csv` | 16 | id、名称、大类码、大类、阶位、字段A_疑似普通攻击/兵种等级、攻击、防御… |
| 建筑 | `analysis/game_rules/tables/parsed/buildings.csv` | 9 | id、名称、类型字段、最大等级、前置建筑ID、描述、资源/图片ID列表、tail_len… |
| 装备 | `analysis/game_rules/tables/parsed/equip_effects.csv` | 11 | id、flags、text、offset、note |
| 装备 | `analysis/game_rules/tables/parsed/equip_types.csv` | 4 | id、名称、子类型/槽位、属性ID列表、品质/效果项、offset |
| 道具 | `analysis/game_rules/tables/parsed/item_effects.csv` | 48 | id、flags、text、offset、note |
| 将领/技能 | `analysis/game_rules/tables/parsed/skill_effects.csv` | 22 | id、标题、字段raw、描述、offset |
| 将领/技能 | `analysis/game_rules/tables/parsed/skills.csv` | 45 | id、名称、技能族、等级、效果ID、效果标题、触发率/数值、效果描述… |
| 科技 | `analysis/game_rules/tables/parsed/tech_effects.csv` | 47 | id、flags、text、offset、note |
| 科技 | `analysis/game_rules/tables/parsed/tech_levels.csv` | 195 | tech_id、名称、等级、效果值、成本A、成本B、成本C、耗时秒… |
| 科技 | `analysis/game_rules/tables/parsed/tech_summary.csv` | 22 | id、名称、最大等级、图标ID、效果ID/字段、效果文本_by_字段、效果文本_by_tech_id、字段1… |
| 商城 | `analysis/vuln_shop/mall_goods/mall_goods_table.csv` | 166 | category、page、total_pages、row_index、good_id、item_id、item_name、item_type… |
| 山贼地图 | `analysis/vuln_shop/bandit_map_0x1540/bandit_0x1540_records.csv` | 66 | flow_idx、ts、target_id、name、level、x、y、desc… |
| 山贼地图 | `analysis/vuln_shop/bandit_map_0x1540/full_scan_7_archer_category_corrected_20260705_0415/level7_all_units_raw.csv` | 596 | target_id、x、y、desc、resource1、resource2、loot_ids、major_codes… |
| 称号/成就 | `analysis/game_rules/title_system/title_box_mapping.csv` | 47 | item_id、item_name、title_name、title_code_from_tail、desc… |
| 称号/成就 | `analysis/game_rules/title_system/title_protocol_methods.csv` | 12 | direction、opcode_dec、opcode_hex、method、logical_name、io_sequence… |
| 称号/成就 | `analysis/game_rules/title_system/title_sentence_hits.csv` | 44 | id、key、hit_terms、categories、text |

## 3. 兵种系统

- 已解析兵种：16 个。
- 大类统计：步兵 4个；弓弩 4个；骑兵 4个；战车/器械 4个
- 字段：名称、大类、阶位、攻击、防御、生命、速度、疑似射程/行动值、铜钱/粮食/材料成本、招募时间、人口占用。
- 证据表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/soldier_table/soldier_values.csv`

| id | 名称 | 大类 | 阶位 | 攻击 | 防御 | 生命 | 速度 | 人口 | 成本/时间 |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | 民兵 | 步兵 | 1 | 8 | 1 | 100 | 7 | 1 | 铜7/粮45/材0/时5 |
| 6 | 弩兵 | 弓弩 | 2 | 30 | 3 | 180 | 6 | 1 | 铜53/粮144/材0/时59 |
| 5 | 弓兵 | 弓弩 | 1 | 25 | 1 | 120 | 7 | 1 | 铜18/粮71/材0/时13 |
| 9 | 轻骑兵 | 骑兵 | 1 | 25 | 5 | 500 | 22 | 1 | 铜41/粮240/材0/时42 |
| 13 | 弩车 | 战车/器械 | 1 | 120 | 1 | 200 | 3 | 2 | 铜215/粮175/材0/时195 |
| 16 | 冲城车 | 战车/器械 | 3 | 3000 | 10 | 800 | 2 | 8 | 铜1862/粮1380/材0/时1621 |
| 2 | 轻步兵 | 步兵 | 2 | 20 | 8 | 450 | 7 | 1 | 铜33/粮96/材0/时16 |
| 4 | 近卫兵 | 步兵 | 4 | 50 | 18 | 1200 | 6 | 1 | 铜138/粮300/材0/时88 |
| 3 | 重步兵 | 步兵 | 3 | 45 | 22 | 850 | 4 | 1 | 铜92/粮158/材0/时37 |
| 8 | 弩骑兵 | 弓弩 | 4 | 55 | 8 | 600 | 14 | 1 | 铜213/粮650/材0/时432 |
| 10 | 重骑兵 | 骑兵 | 2 | 45 | 16 | 900 | 14 | 1 | 铜113/粮320/材0/时87 |
| 11 | 铁骑兵 | 骑兵 | 3 | 65 | 22 | 1300 | 12 | 1 | 铜242/粮570/材0/时244 |
| 15 | 投石车 | 战车/器械 | 4 | 500 | 1 | 250 | 3 | 5 | 铜3171/粮800/材0/时1986 |
| 14 | 重弩车 | 战车/器械 | 2 | 200 | 1 | 350 | 2 | 3 | 铜716/粮450/材0/时583 |
| 7 | 强弩兵 | 弓弩 | 3 | 60 | 5 | 250 | 5 | 1 | 铜153/粮260/材0/时207 |
| 12 | 骁骑兵 | 骑兵 | 4 | 60 | 18 | 1100 | 20 | 1 | 铜242/粮700/材0/时330 |

## 4. 建筑、科技、资源

- 建筑：9 条。核心建筑为大厅、房屋、农场、书院、步兵营、弓兵营、战车营、骑兵营；ID 7 为保留/空记录候选。
- 建筑规则高置信：大厅产铜钱且是其他建筑升级前提；房屋增人口；农场产粮；书院研究全封地共享科技；兵营按类型解锁兵种。
- 科技：22 条，名称：工程设计、征召技巧、种植技术、行军技巧、市场贸易、建筑学、铸铁技术、甲胄制造、药草研究、阵法技巧、抛射技巧、驾驭技巧、战车设计、统帅能力、信仰、仓储、安置、格斗、精准、驯马、精工、悬赏。
- 科技影响覆盖：建筑速度、招兵速度、粮食/铜钱产量、士兵攻防生命、行军速度、兵种专项加成、统兵、忠诚费用、仓储/撤退/战功/强化/聊天等。
- 资源经济已确认包含：铜钱、粮食、白银、黄金、声望、资源点收益、商城购买、礼包/宝箱/副本/战利品奖励。

## 5. 将领、技能、装备、道具

- 将领技能表：45 条，技能族：乱射、冲锋、奇袭、散射、散阵、斩将、暴击、枪阵、格档、溅射、盾阵、穿透、贯穿、践踏、连击。
- 技能效果表：22 条，包含暴击、连击、斩将、践踏、奇袭、散阵、穿透、乱射、散射、盾阵/格挡、冲锋、枪阵、溅射、贯穿等。
- 装备类型：4 类：武器、头盔、铠甲、坐骑。
- 道具效果：48 条，其中非空效果 44 条；覆盖建筑队列、产量加成、迁封、传音、体力/经验、将领刷新、保护、加速、出征、俘虏、战斗收益、统帅、攻速等。
- 动态验证：礼包/宝箱使用接口 `0x3144` 以服务器库存为准；有库存时重放等价于再次使用一个道具，无库存返回不足。

## 6. 商城、邮件、副本、山贼

- 商城在线商品表：166 条；商品 ID、item_id、名称、价格1/价格2、库存/限制已收集。
- 商城购买接口 `0x1102` 已审：改商品、改币种、异常数量均有服务端校验；原样重放会正常扣费，不是免费购买。
- 邮件/战利品 `0x1114`：详情可重放但不重复发奖，属于只读/展示类。
- 副本：启动 `0x1522`，战斗轮询 `0x1702`，宝箱/结果展示 `0x193e`；结果接口可重放但用户确认资源不重复到账。
- 山贼地图 `0x1540`：请求为局部坐标查询，不是一次全图；已做全图扫描，约 5424 伙山贼，7级约596。守军大类字段已校正为 0步兵/1弓弩/2骑兵/4战车。

## 7. 战斗机制当前结论

- 战法书/战法索引：35 条；战斗 BUFF/状态：25 条。
- 战斗不是简单回合制，更接近行动蓄力/行动条制；客户端回放使用 `C0` 作为攻击间隔/蓄力上限，单位毫秒。
- 普通攻击/战法损兵在客户端回放中以“旧兵数 - 新剩余兵数”展示；基础伤害公式目前倾向于由服务端计算后下发。
- 坐标/站位：客户端为 2D 像素坐标，分阵营镜像、行列坑位；已定位 `B/C/I/J` 等位置函数和正/斜阵型偏移。
- 目标策略文本已确认：最优攻击、最强攻击、剿灭攻击、要害攻击、城墙攻击。
- 待补：基础伤害公式、服务端战斗结果计算路径、技能/科技/装备叠加顺序、完整胜负/伤兵/自愈规则。

## 8. 下一步采集顺序

1. 深挖战斗：追 `KING_BATTLE_SIMULATOR3.0`、`fight.dat`、`scriptPages/game/s` 与战斗响应解析，判断基础伤害公式、攻速蓄力、伤兵/胜负是否能从客户端闭环。
2. 礼包/宝箱复杂掉落池：继续追 `0x3144` 使用/开箱响应函数，重点处理随机宝箱、装备箱、将领礼包的复杂结构。
3. 称号/成就数值表：实际打开“君主→成就/称号”后抓 `0x1180/0x1184/0x1186`，或继续反查称号配置加载格式。
4. 动态采集建筑升级、招兵、出征、战斗结算、任务领取接口，补协议状态机。
5. 若服务器恢复，优先抓一次完整“招兵→出征山贼→战斗→奖励”的链路。

## 9. 关键原始/中间证据路径

- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/game_rules_overview.md`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/soldier_table/soldier_values.md`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/tables/parsed/README.md`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_tables/README.md`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_system_mechanism.md`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_core_formula_coordinate_findings.md`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/title_system/title_system_report.md`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/vuln_shop/mall_goods/mall_goods_table.md`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/vuln_shop/bandit_map_0x1540/bandit_0x1540_records.md`

## 10. 副本/战役关卡表补充

- 已从 `scriptFB.sc` 初步结构化出 111 条副本/战役关卡展示记录。
- 输出：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/fb_tables/fb_stage_table.md`
- CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/fb_tables/fb_stage_table.csv`
- 当前字段：战役/关卡推断、名称、剧情、目标、敌军文本、敌军总兵力、随机奖励、地点、场景脚本。
- 待补：继续解析每个 `x-y-z.sc` 场景脚本，恢复实际站位/将领/兵种数量/战斗脚本细节。

## 11. 道具全映射补充

- 已从 `scriptItem.sc` 结构化出 758 条道具记录，覆盖名称、类型、描述、尾部原始参数、可直接解析的效果动作。
- 已合并 `scriptItemEffect.sc` 的 48 条效果文本，当前直接解析到效果动作的道具有 97 个。
- 已合并商城表，商城中出现的道具有 142 个。
- 已标记动态验证过的关键道具：兵书 item_id=16、钻石礼包 item_id=85、惊喜宝箱 item_id=99、50级高级兵甲箱 item_id=193。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/item_mapping/item_mapping_report.md`
- 全量 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/item_mapping/item_full_mapping.csv`
- 商城关联 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/item_mapping/item_mall_mapping.csv`
- 礼包/宝箱候选 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/item_mapping/item_package_box_candidates.csv`
- 待补：礼包/宝箱尾部掉落表目前只做候选标记，复杂概率/固定奖励结构还需继续反推。

## 12. 礼包/宝箱内容文本结构化补充

- 已从道具描述文本中结构化 407 个礼包/宝箱/资源包候选。
- 其中含概率文本 13 个，含钥匙需求 7 个，含固定/描述性奖励文本 287 个。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/item_mapping/package_reward_text_report.md`
- CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/item_mapping/package_reward_text_mapping.csv`
- 当前是文本层解析；复杂尾部二进制掉落池、概率权重和固定奖励记录仍需继续验证。

## 13. 礼包/宝箱 tail 二进制结构解析补充

- 已对 407 个礼包/宝箱/资源包候选尝试解析尾部二进制奖励结构。
- 当前确认通用固定奖励结构，可解析资源奖励和道具奖励；已成功解析 142 个。
- 资源类型当前确认：6=粮食、7=铜钱、8=白银、9=黄金。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/item_mapping/package_tail_binary_parse_report.md`
- 全量 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/item_mapping/package_tail_binary_parse.csv`
- 成功解析子集：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/item_mapping/package_tail_binary_parsed_ok.csv`
- 未解析项主要是随机宝箱、装备随机箱、将领礼包/复杂多段掉落池，需要继续追客户端 `0x3144` 使用/开箱解析函数。

## 14. 副本/战役场景脚本解析补充

- 已解析 `scriptFB.sc` 引用的 x-y-z 场景脚本与 APK 中实际存在的编号场景脚本。
- `scriptFB` 引用 227 个场景脚本；APK 中实际存在编号脚本 188 个；本轮覆盖 242 个脚本名，其中存在 188 个、缺失 54 个。
- 已识别 `.sc` 文件头：`version:u32 + declared_len:u32 + command_count:u32`，其中 `declared_len = 文件大小 - 8`。
- 已提取中文字符串 1239 条，并生成关卡→场景→演员候选/对白预览聚合表。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/fb_scene_scripts/fb_scene_script_report.md`
- 场景汇总 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/fb_scene_scripts/scene_script_summary.csv`
- 字符串 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/fb_scene_scripts/scene_script_strings.csv`
- 关卡聚合 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/fb_scene_scripts/stage_scene_aggregate.csv`
- 待补：继续反查 scene opcode，确认演员/单位创建、对白、动作、战斗触发的精确字段含义。

## 15. 副本场景 opcode 初步反推补充

- 已对 APK 内 188 个编号副本/战役场景脚本 `x-y-z.sc` 做 opcode 长度级解析，全部可解析到 EOF。
- 新增输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/fb_scene_scripts/scene_opcode_initial_findings.md`
- 命令明细 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/fb_scene_scripts/scene_opcode_observations.csv`
- 场景 opcode 汇总 CSV：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/fb_scene_scripts/scene_opcode_scene_summary.csv`
- 当前识别到 9 类 opcode：
  - `0x01`：场景/镜头初始化或切换，9字节/23字节两种形态。
  - `0x05`：定点效果/入场触发候选，11字节，含 id、duration、x/y。
  - `0x06`：对白/旁白文本显示，结构为固定头 + UTF 文本 + UI 尾字段。
  - `0x08`：脚本结束/返回，4字节，几乎每个脚本末尾出现。
  - `0x09`：演员/单位创建或摆放，含 actor_id/resource_id/name/坐标等候选字段。
  - `0x0A`：演员移动/动作/战斗区位移候选，固定18字节，含 actor_id、duration、x/y。
  - `0x0B`：演员状态/显隐切换候选，7字节，常成组出现。
  - `0x0C`：批量路径/镜头演出候选，18字节，常连续出现。
  - `0x0D`：延迟/镜头段落分隔，常见5字节，另有1例28字节长参数。
- 解析得到物理命令记录 4102 条，其中 `0x06` 对白/旁白 835 条，`0x09` 命名演员创建 408 条。
- 重要修正：`.sc` 头部第三字段可作为声明/逻辑计数字段，但 52 个脚本中它小于实际物理命令记录数；因此深解析不能只按该字段截断，应以 opcode 长度走到 EOF。
- 当前边界：这些 `.sc` 主要恢复副本剧情、演员、站位与演出流程；它不是服务端战斗结算公式本身。下一步若要恢复战斗结算，仍需追 `KING_BATTLE_SIMULATOR3.0`、`fight.dat` 与战斗协议。

## 16. 玩家成长/等级/官职/封地规则补充

- 已从 `sentence.txt`、`FAQ.txt`、`scriptFreshman.sc`、`scriptGuide.sc`、`scriptBanyou.sc`、`scriptMMhelp.sc`、`scriptRoleName.sc`、`scriptRoleProf.sc` 中整理玩家成长相关规则第一版。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/player_growth/player_growth_report.md`
- 结构化数据：
  - `growth_sentence_hits.csv`：sentence 成长相关命中 910 条。
  - `growth_faq_hits.csv`：FAQ 成长相关命中 24 条。
  - `freshman_entries.csv`：新手/成长引导记录 68 条。
  - `growth_binary_string_hits.csv`：二进制帮助/引导成长字符串 196 条。
  - `role_name_parts.csv`：将领姓名/名部件 1164 条。
  - `role_professions.csv`：将领职业 4 条。
- 当前确认的核心成长规则：
  - 君主存在等级/声望升级进度；部分功能按君主等级开放；国库捐献要求君主等级超过30级；竞技场等功能有等级门槛。
  - 封地数量受等级限制；帮助文本确认“每提升10级，可获得开启一片新封地资格”；封地隶属于城池，不能在已有封地的城池重复开辟，城池规模限制可开封地数。
  - 国家官职由战功/贡献影响，系统国家中丞相/大都督由贡献/战功最高者获取，每7日轮换；自建国家由国王任命或管理者调整。
  - 战功超过等级值10倍后衰减；贡献超过等级值100倍后衰减；基础衰减比例1%，连续未登录天数每+1天附加+1%。
  - 国库捐献/国库上限：每日可接受铜钱1.5亿、粮食3亿；国库总上限铜钱100亿、粮食300亿。
  - 军团创建：创建者等级35级以上、缴纳30万铜币、军团名不能重复。
  - 将领职业：步将、弓将、骑将、勇士；职业加成文本已确认（步将步兵防御+20%生命+15%，弓将弓兵攻击+30%，骑将骑兵攻防+15%，勇士全兵种生命+35%）。
  - 将领属性：武力加攻击、智力加防御、统帅提升带兵数；成长值决定升级属性增幅；成长60以上可培养，高成长星标 80~84/85~89/90~94。
  - 新手礼包伴随成长到60级，每10级可开启1次。
  - 称号规则：同一时间只能激活一个称号，每200秒可切换一次；“集”类称号无需激活即可加成，状态类称号条件不满足会失效。
- 待补：具体君主等级→声望阈值表、等级→封地数量最终公式、官职名额/排序表、称号奖励数值表仍需继续从 DEX/协议/动态样本反查。

## 17. 称号/成就系统规则与协议补充

- 已对称号/成就系统做一轮文本、道具、DEX 协议、抓包覆盖整合。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/title_system/title_system_report.md`
- 结构化数据：
  - `title_sentence_hits.csv`：称号/成就相关 sentence 文本命中 44 条。
  - `title_faq_hits.csv`：FAQ 称号/成就问答命中 1 条。
  - `title_help_hits.csv`：二进制帮助脚本称号/成就文本命中 80 条。
  - `title_box_mapping.csv`：称号相关道具/称号宝箱 47 条，其中 46 条称号宝箱 tail 解析出疑似称号编码。
  - `title_protocol_methods.csv`：DEX 反汇编确认的称号/成就请求与响应读写结构 12 条。
  - `title_capture_hits.csv`：抓包中称号/成就相关字符串命中 1621 条；直接 opcode 命中 0 条。
- 当前确认的核心规则：
  - 同一时间只能激活一个称号，每 200 秒可切换一次。
  - “集”类称号为特殊称号，达成条件后无需激活即可享有属性加成，且可与其他称号效果叠加。
  - 状态类称号在不满足条件时会自动失效，如神工、枭雄、无双、寨主。
  - 可隐藏/展示个人成就和称号详情；隐藏不应影响自身称号使用。
  - 寨主称号：灭敌时获得的战功 +10%，但只增加击败玩家兵力产生的战功，不增加攻打城池获得的固定战功。
  - 修筑城墙/道路每日贡献值有上限，但超过贡献上限后继续修筑仍统计 `铜墙铁壁` / `四通八达` 成就数值。
- 当前确认的关键协议入口：
  - `0x1180 reqAchievementList`：请求成就列表。
  - `0x1184 reqAchievementCont`：请求/领取成就内容或奖励候选。
  - `0x1186 reqNicknameList`：请求称号列表。
  - `0x1188 activationNickname`：激活称号。
  - `0x118a reqActivationUseGold`：用黄金立即激活/冷却称号。
- 称号宝箱 tail 模式：多数称号宝箱尾部存在 `01 10 00 <len> <ASCII数字...> 00 00 00`，中高置信为称号编码/称号ID。示例：`寨主称号宝箱` item_id=545 → tail code `1`；`无双称号宝箱` item_id=561 → tail code `18`；`神工称号宝箱` item_id=563 → tail code `20`。
- 当前边界：尚未完整恢复“每个称号/成就的属性效果数值表”。现有抓包未直接捕获 `0x1180/0x1184/0x1186/0x1188/0x118a`，需要用户实际打开成就/称号界面后再抓一次，或继续反查称号配置加载格式。

## 18. 战斗指令流/伤害公式边界补充

- 已对 `LscriptPages/game/s;->Z(String)` 战斗/战报指令流做结构化整理，确认 command type `1..11`。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_deep/battle_command_structure_report.md`
- 已同步补充到：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_core_formula_coordinate_findings.md`
- 结构化数据：
  - `battle_command_structure.csv`：11 类 command type 的读取结构、handler、状态缓冲、与公式关系。
  - `battle_command_baseio_reads.csv`：每类 command type 对应 BaseIO read 调用地址索引。
  - `battle_command_structure.json`：完整 JSON 汇总。
- 通用战斗指令格式：
  - `readShort(commandCount)`。
  - 每条命令读取 `readByte(commandType)` + `readInt(timeOffsetMs)`。
  - 每条命令进入 `s.d1(type)`、`s.e1(handlerIndex)`、`s.f1(scheduledTimeMs)`，并按 `scheduledTimeMs / 1000` 分组写入 `data.g.Qc/Rc` 供回放调度。
- 已确认 command type：
  - `1`：进入行军区/创建战场部队；读取 `attackIntervalMs`，最终写入 `C0`。
  - `2`：加入布阵区/预备区候选。
  - `3`：加入到战斗区；读取 lane/col，与坐标/坑位规则相关。
  - `4`：暂停行军区内行军。
  - `5`：离开战斗。
  - `6`：普通攻击指令；读取攻击后剩余值，客户端用 old-new 显示损兵/同步状态。
  - `7`：战斗结束。
  - `8`：使行军区部队继续行走。
  - `9`：移动到战斗区指定位置；读取 lane/col，与坐标/坑位规则相关。
  - `10`：战场文本/提示。
  - `11`：战法/技能攻击指令；读取 before/after，客户端显示损兵/效果。
- 关键结论：
  - 基础伤害公式仍未在客户端 `s->Z/f0/p0` 回放执行路径闭环。
  - 普通攻击与战法攻击均是“服务端/战斗结果生成侧给出结果，客户端回放表现”。
  - 攻速/蓄力 `C0` 的上游已确认：新协议 command type 1 直接携带毫秒值；旧协议才存在 `4000/5000/7000ms` 兼容推断。
  - 坐标/前后左右属于客户端表现层，已可通过 command type 3/9 与 `s->B/I/C/J` 继续精修。
- 当前边界：若要完全恢复服务端基础伤害公式，需要继续追 `KING_BATTLE_SIMULATOR3.0` 生成侧，或基于更多真实战报样本拟合。


## 19. KING_BATTLE_SIMULATOR3.0 本地模拟器路径补充

- 已继续追踪 `KING_BATTLE_SIMULATOR3.0` 相关路径，确认它首先是本地 RMS 阵容/模拟器配置存档名，而非基础伤害公式函数。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_deep/battle_simulator_path_report.md`
- 结构化数据：
  - `battle_simulator_rms_format.csv`：RMS record #1 中阵容槽字段读写镜像。
  - `battle_simulator_path_evidence.csv`：`F3/L4/G/gameHD.f` 等方法证据索引。
  - `battle_simulator_path_summary.json`：模拟器路径 JSON 汇总。
- 当前确认：
  - `data.g->F3()` 从 RMS record #1 读取最多 20 个阵容槽，填充 `m7..x7` 缓存。
  - `data.g->L4()` 处理模拟器 UI 输入、保存阵容，并将 `c6..n6` 当前配置序列化回 RMS record #1。
  - `data.g->G()` 与 `gameHD/f->r/k/b()` 主要是战斗模拟器界面绘制、士兵类型/数量配置、战法/称号选择、保存/选择/清空/开始战斗按钮。
  - 本路径未出现攻击、防御、生命、兵数闭环计算；它更像“本地阵容配置 UI + 阵容缓存”。


## 20. 战斗模拟器开始战斗请求补充

- 已继续追“开始战斗”按钮后续路径，确认模拟器会向服务端提交阵容请求，而不是在客户端本地结算基础伤害。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_deep/battle_simulator_start_path_report.md`
- 结构化数据：
  - `battle_simulator_protocol_fields.csv`：请求/响应字段顺序与证据偏移。
  - `battle_simulator_start_path_summary.json`：开始战斗链路 JSON 汇总。
  - `battle_start_field_refs.json`：`a6/b6/c7/d7/e7/f7/b7/c6..n6` 等关键字段引用扫描。
- 当前确认的请求链路：
  - `data.g->L4()` 点击开始后调用 `data.g->Q2()`。
  - `Q2()` 显示“进入战斗中...”，记录 `b7=curTime`，清空 `c7=0`。
  - `Q2()` 使用 `BaseIO.openDos("ReqChallengeTaskAward")`，按 `h6,c6,d6,e6,f6,g6,n6,i6,j6,k6,l6,m6` 顺序写入两方阵容/附加配置。
  - 发送点：`LscriptPages/game/g;->y("ReqChallengeTaskAward", "ReqChallengeTaskAward", 25613)`，opcode 十进制 `25613`，十六进制 `0x640D`。
  - 响应解析：`data.g->B4(String)` 读取 `d7=readByte()`、`e7=readUTF()`，若 `d7 != 0` 再读 `f7=readLong()` 作为 `fightID`。
  - `L4()` 等待响应；超过 20 秒显示 `di_联网超时`；若 `fightID > 0`，调用 `LscriptPages/game/c;->r(fightID, 1)` 进入战斗/战报。
- 对公式恢复的影响：客户端目前能恢复“战斗输入格式”和“战斗回放格式”，但真实胜负/伤害/伤兵生成仍在服务端或缺失模块中；服务端重建应将战斗基础公式列为拟合/重写模块。


## 21. 协议发送入口第一版

- 已对 `LscriptPages/game/g;->y(String,String,S)` 网络发送入口做第一轮静态扫描，提取 40 个发送调用点。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/protocol_send_entry_report.md`
- 结构化数据：
  - `network_send_calls.csv`：原始发送调用点、请求名、opcode、方法、偏移。
  - `network_send_calls_classified.csv`：按基础机制模块归类后的发送入口表。
  - `network_send_calls.json`：发送入口 JSON 汇总。
- 当前恢复的关键路由包括：
  - `0x1120 reqRoleInfo`：角色/将领信息。
  - `0x1310 reqRoleFiefList`：将领/角色封地列表。
  - `0x1229 reqBathAddArmy`：批量加兵/配兵。
  - `0x1212 fiefMove`：迁封/封地移动。
  - `0x1012 reqFightingCity`：城池战斗相关请求。
  - `0x640D ReqChallengeTaskAward`：战斗模拟器/挑战战斗请求。
  - `0x1134 reqGainAward`：奖励领取。
  - `0x3144/0x1144 reqUseItem`：道具使用。
  - `0x1180 reqAchievementList`、`0x1186 reqNicknameList`、`0x118A reqActivationUseGold`：成就/称号。
  - `0x131B/0x1320/0x1324/0x132D/0x1332/0x1334/0x1335/0x1340/0x1342/0x1344`：城池/城市相关。
  - `0x1418/0x1442/0x2001/0x2002/0x6282`：国家相关。
- 当前边界：这是“路由表第一版”，字段级协议还需按优先级逐个展开 `BaseIO.write*` 顺序；建议先按最小可玩闭环展开 `reqRoleInfo -> reqRoleFiefList -> reqBathAddArmy -> fiefMove/reqFightingCity -> 战斗结算/奖励`。


## 22. 角色详情/封地列表协议字段初步

- 已对服务端最小可玩闭环中的 `reqRoleInfo` 与 `reqRoleFiefList` 做第一轮字段级解析。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/role_fief_protocol_report.md`
- 结构化数据：
  - `role_fief_request_fields.csv`：`reqRoleInfo`、`reqRoleFiefList` 请求体字段顺序。
  - `role_fief_response_fields.csv`：`reqRoleInfo` 成功体与 `p.T` 三大列表组响应字段顺序。
  - `role_fief_protocol_summary.json`：协议解析 JSON 汇总。
  - `method_disasm_role_fief/`：相关方法反汇编与 dispatcher 证据。
- `reqRoleInfo`：
  - 请求 opcode：`0x1120`。
  - 请求方法：`LscriptPages/game/w;->d0(J,String)`。
  - 请求格式：`target_selector/writeByte`；若按名称查则写 `roleName/writeUTF`，否则写 `roleId/writeLong`。
  - 响应 dispatcher：`Lo/a;->A6` 中 `0x8120` 分支；先读状态 byte，成功时进入 `LscriptPages/game/w;->e0(String)`。
  - 成功体已恢复 25 个读取字段，包括 `roleId/readLong`、`roleName/readUTF`、多个文本字段和 byte/short/int/long 状态数值字段。
- `reqRoleFiefList`：
  - 请求 opcode：`0x1310`。
  - 请求方法：`LscriptPages/game/p;->g0(I,I)` 的 `type=4` 分支。
  - 请求格式：固定 `mode_or_type/writeByte(1)`，再写 `target_selector/writeByte`；字符串存在时写 `targetName/writeUTF`，否则写 `targetId/writeLong`。
  - 当前关联响应路径：`0x8510 -> LscriptPages/game/p;->a1(String) -> p.T(String)`。
  - `p.T` 响应读取三大组列表：Group A、Group B、Group C；包含 ID、名称、坐标/等级候选、资源/兵力/状态数值、文本字段、以及嵌套子列表。
- 当前边界：`reqRoleInfo` 语义较清晰；`reqRoleFiefList/p.T` 字段语义仍需结合实际抓包或 UI 渲染函数进一步命名。服务端重建初期可优先实现 `reqRoleInfo`，`reqRoleFiefList` 可先返回空三组列表作为最小兼容，再逐步补全。


## 23. 批量补兵 reqBathAddArmy 协议字段初步

- 已对服务端最小可玩闭环中的 `reqBathAddArmy` 做字段级解析。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/bath_add_army_protocol_report.md`
- 结构化数据：
  - `bath_add_army_request_fields.csv`：`reqBathAddArmy` 请求体字段顺序。
  - `bath_add_army_response_fields.csv`：`0x8229` 响应体字段顺序。
  - `bath_add_army_protocol_summary.json`：批量补兵协议 JSON 汇总。
  - `method_disasm_bath_add_army/`：`p.L0/p.M0/p.a/p.b/p.s1/p.y1` 与相关 `Lo/a` 更新函数反汇编。
- 当前确认：
  - 请求 opcode：`0x1229`，十进制 `4649`。
  - 请求方法：`LscriptPages/game/p;->L0([J)V`。
  - 响应 opcode：`0x8229`；dispatcher `Lo/a;->A6` 进入 `LscriptPages/game/p;->M0(String)`。
  - 请求体只包含 `role_count/writeByte` 和 `role_ids[i]/writeLong`，没有兵种/数量字段。
  - 选中 ID 来源包括 `p.a()` 从 `p.Z[0..4]` 过滤出的最多 5 个将领/角色 ID，以及 `p.s1()` 中从 `v0` 过滤生成的 `z0`。
  - UI 文案明确出现 `di_联网批量补兵`，因此该接口语义为“请求服务端对选中将领自动补兵”。
  - 成功响应先返回将领/角色更新组：`role_update_count`，每项含 `role_id_or_key/readLong`、`army_type_or_status/readByte`、`army_count_or_value/readInt`，客户端经 `Lo/a.q1` 映射后写入 `Lo/a.Pm/Qm`。
  - 随后返回封地/上下文兵种库存组：`fief_or_context_id/readLong`、`soldier_type_count/readByte`、`soldier_type[i]/readByte`、`soldier_amount[i]/readInt`，客户端写入 `Lo/a.Kv/Lv`。
- 对重建服务端的影响：补兵数量和目标兵种不是客户端提交的，应由服务端根据将领带兵上限、当前兵力、封地空闲兵库存等计算；该接口可作为“服务端权威资源/兵力同步”的证据。


## 24. 迁封 fiefMove 协议字段初步

- 已对服务端最小可玩闭环中的 `fiefMove` 做字段级解析。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fief_move_protocol_report.md`
- 结构化数据：
  - `fief_move_request_fields.csv`：`fiefMove` 请求体字段顺序。
  - `fief_move_response_fields.csv`：`0x8212` 响应体字段顺序与错误码映射。
  - `fief_move_protocol_summary.json`：迁封协议 JSON 汇总。
  - `method_disasm_fief_move/`：`q.T/q.W/q.H1` 与相关 `q` 响应候选函数反汇编。
- 当前确认：
  - 请求 opcode：`0x1212`，十进制 `4626`。
  - 请求方法：`LscriptPages/game/q;->T(J,I,I,J,String)`。
  - 响应 opcode：`0x8212`；dispatcher `Lo/a;->A6` 进入 `LscriptPages/game/q;->W(String)`。
  - 请求体包含 `source_fief_id/writeLong`、`target_city_or_slot/writeShort`、`target_selector/writeByte`，然后根据 selector 写 `target_id/writeLong` 或 `target_name/writeUTF`。
  - 调用点 `q.H1()` 的 UI 文案为 `di_联网封地迁封`，确认该接口为封地迁移/迁封请求。
  - 成功响应读取 `moved_fief_id/readLong`、`new_city_or_position/readLong`，并将新位置低 16 位写入 `Lo/a.sv[p3(fief)]`。
  - 成功后触发 `reqRoleInfo(-1,data.i.b)` 刷新角色详情，并调用 `q.g1(0,moved_fief_id)` 刷新迁封 UI/列表。
  - 错误码 `-1..-9` 已恢复：没有指定、迁封无效、没有空封、无可迁城、原封地城池、其他错误、基地迁封、没有城池、不属于您。
- 对重建服务端的影响：该接口是封地系统核心状态变更接口，服务端需要校验封地归属、基地禁止迁封、目标城池/槽位有效性、空封资格与目标城池可用性，并在成功后同步封地位置及相关角色/封地列表。

## 25. 城池战斗入口 reqFightingCity 协议字段初步

- 已对服务端最小可玩闭环中的 `reqFightingCity` 做字段级第一版解析。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fighting_city_protocol_report.md`
- 结构化数据：
  - `fighting_city_request_fields.csv`：`reqFightingCity / 0x1012` 请求体字段顺序。
  - `fighting_city_response_fields.csv`：`0x8012 -> s0.S(String)` 响应字段顺序。
  - `fighting_city_protocol_summary.json`：城池战斗入口协议 JSON 汇总。
  - `method_disasm_fighting_city/`：`s0.Z/s0.S/s0.w/s0.R/s0.U/s0.X/s0.Y` 相关方法反汇编。
- 当前确认：
  - 请求 opcode：`0x1012`，十进制 `4114`。
  - 请求方法：`LscriptPages/game/s0;->Z()V`。
  - 响应 opcode：`0x8012`；dispatcher `Lo/a;->A6` 中 signed short `-32750` 分支进入 `LscriptPages/game/s0;->S(String)`。
  - APK 1.66 静态路径中，`s0.Z` 在写入请求数量前执行 `const/4 v3,0`，因此实际最小请求体可视为 `visible_city_count/writeByte(0)` 后发送。
  - `s0.Z` 中仍保留一个 `count>0` 的备用/遗留循环：逐条写 `city_id/writeLong`、`city_name_or_label/writeUTF`、`D[i][1]/writeInt`、`E[i][1]/writeShort`，但默认路径不可达或至少不是当前版本常规请求体。
  - `s0.S` 响应先读坐标标记组：`marker_count/readShort`，随后每条 `(marker_x/readShort, marker_y/readShort)`，匹配现有 `s0.s` 后设置 `s0.H[index]=true`。
  - `s0.S` 再读城市/战斗目标更新组：`city_update_count/readShort`；每条记录包含 `city_id`、坐标、压缩外观/类型 byte 序列、名称、4 个状态 byte、3 个文本字段、`D[3]`、`E[2]`、`F[2]`、`G[2]`、疑似 `K[2]`、`I`、`J`、`L` 等字段。
  - `s0.S` 只按现有 `s0.r` 中的 ID 匹配并覆盖更新，不负责新增未知城市；完整初始城市/目标缓存来自 `s0.w()` 读取的 `flushCitys` 流，来源链路仍需继续追 `0x800D -> s0.b([B) -> s0.g2 -> s0.w()`。
- 对重建服务端的影响：服务端初版可先支持 `0x1012` 的 `count=0` 请求，并在客户端已有地图基础缓存后返回 `0x8012` 增量更新；若要从空客户端进入完整地图，需要继续恢复 `flushCitys` 初始缓存下发协议。

## 26. 城池地图初始缓存 0x800D / flushCitys 字段初步

- 已对城池地图/战斗目标完整缓存首包 `0x800D -> s0.b([B) -> s0.w()/flushCitys` 做字段级第一版解析。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/flush_city_initial_cache_report.md`
- 结构化数据：
  - `flush_city_initial_cache_fields.csv`：`0x800D` raw byte[] 与 `flushCitys` 单条城市/目标记录字段顺序。
  - `flush_city_initial_cache_summary.json`：初始地图缓存协议 JSON 汇总。
  - `method_disasm_fighting_city/scriptPages_game_s0__b__0x40b000.smali.txt`：`s0.b([B)` 只保存 payload 到 `s0.g2`。
  - `method_disasm_fighting_city/scriptPages_game_s0__w__0x40e4e0.smali.txt`：`flushCitys` 解析器。
- 当前确认：
  - 响应 opcode：`0x800D`，dispatcher 中以 signed short `-32755` 出现。
  - `Lo/a;->A6` 在 `0x800D` 分支把原始 byte[] 传给 `LscriptPages/game/s0;->b([B)V`。
  - `s0.b([B)` 不解析字段，只执行 `s0.g2 = payload`。
  - `s0.w()` 在 `s0.g2` 非空时 `BaseIO.openDis(g2, "flushCitys")`，先读 `record_count/readShort`，再循环读取城市/战斗目标记录。
  - 单条记录字段顺序包括：`city_id/long`、`coord_x/short`、`coord_y/short`、压缩外观/类型 byte 序列、`name/UTF`、4 个状态 byte、`text_z/UTF`、可选 `A/byte`、`text_B/UTF`、`text_C/UTF`、`D[3]/int`、`E[2]/short`、`F[2]/int`、`G[2]/int`、`K[2]/int`、`I/short`、`J/long`、`L/byte`。
  - 与 `0x8012 -> s0.S` 增量刷新相比，`flushCitys` 能新增未知 ID、找空槽、必要时将 `s0.r..L` 全套缓存数组扩容 100，并明确写入 `s0.K[index]`。
- 对重建服务端的影响：空客户端进入地图时应先下发 `0x800D/flushCitys` 建立地图缓存，再用 `0x1012/reqFightingCity` 与 `0x8012` 做后续状态刷新；否则单独返回 `0x8012` 无法让客户端新增未知城市/目标。

## 27. 奖励领取 reqGainAward 协议字段初步

- 已对通用奖励领取接口 `reqGainAward` 做字段级第一版解析。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/gain_award_protocol_report.md`
- 结构化数据：
  - `gain_award_request_fields.csv`：`reqGainAward / 0x1134` 请求体字段顺序。
  - `gain_award_response_fields.csv`：`0x8134 -> m0.u(String)` 与 `m0.n(String)` 奖励列表同步块字段顺序。
  - `gain_award_protocol_summary.json`：奖励领取协议 JSON 汇总。
  - `method_disasm_gain_award/`：`m0.t/m0.u/m0.n` 及相关响应候选方法反汇编。
- 当前确认：
  - 请求 opcode：`0x1134`，十进制 `4404`。
  - 请求方法：`LscriptPages/game/m0;->t(long,String)`。
  - 响应 opcode：`0x8134`；dispatcher `Lo/a;->A6` 中 signed short `-32460` 分支进入 `LscriptPages/game/m0;->u(String)`。
  - 请求体只包含 `award_id/writeLong`、`name_selector/writeByte`、可选 `award_name_or_context/writeUTF`；客户端不提交奖励物品/资源数量。
  - 响应先读 `status/readByte`，再固定调用 `m0.n(String)` 同步 4 类奖励列表；每类有两组记录计数和若干 `(id/long, name/UTF, flag/boolean)`。
  - `status==0` 时继续读取玩家/资源同步字段：`player_attr_byte/readByte`、`data.i.i/readLong`、`data.i.d/readLong`、`data.i.e/readLong`、`data.g.H/readLong`，随后调用 `Lo/a.V5(String)` 读取额外同步块。
  - 最后读取 `message/readUTF` 作为服务端提示；空字符串时客户端显示“失败”。
- 对重建服务端的影响：奖励发放完全应由服务端按 `award_id` 和上下文校验决定；响应必须保持奖励列表同步块格式，成功时同步资源/背包/玩家状态，失败时用非 0 status 与 message 返回原因。

## 28. 城池特性升级 reqCityTraitLevelUp 协议字段初步

- 已对城池特性/天赋升级接口 `reqCityTraitLevelUp` 做字段级第一版解析。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/city_trait_levelup_protocol_report.md`
- 结构化数据：
  - `city_trait_levelup_request_fields.csv`：`reqCityTraitLevelUp / 0x1324` 请求体字段顺序。
  - `city_trait_levelup_response_fields.csv`：`0x8324 -> k.d1(String) -> k.m1(String)` 响应与成功同步字段顺序。
  - `city_trait_levelup_protocol_summary.json`：城池特性升级协议 JSON 汇总。
  - `method_disasm_city_trait/`：`k0.c0`、`k.d1`、`k.m1` 等反汇编证据。
- 当前确认：
  - 请求 opcode：`0x1324`，十进制 `4900`。
  - 请求方法：`LscriptPages/game/k0;->c0()I`。
  - 响应 opcode：`0x8324`；dispatcher `Lo/a;->A6` 中 signed short `-31964` 分支进入 `LscriptPages/game/k;->d1(String)`。
  - 请求体只提交目标城池标识：`target_selector/writeByte` 后接 `city_name/writeUTF` 或 `city_id/writeLong`。
  - 成功时 `k.d1` 调用 `k.m1` 同步城池数据：`city_id/readLong`、`data.b.z/readByte`、`data.b.A/B/C/readInt`、`data.b.D=now+readInt`、`data.b.k/readByte`、`data.b.m/readInt->short`。
  - 错误码已恢复：`0` 成功，`-4` 铜钱不足，`-5` 粮食不够，`-1` 天赋升级相关错误/条件不满足候选，`-2` 天赋已达最大值，`-3` 其他错误。
- 当前边界：该接口是城池特性/天赋升级，不是普通封地建筑建造/升级。DEX 字符串未发现直观 `reqBuildingLevelUp`；普通建筑链路仍需继续追 `reqFiefInfo / reqCityFiefList / reqApplyFief` 与封地 UI 控制流。

## 29. 普通封地建筑/建设协议入口第一版

- 已确认普通封地建筑/建设链路大量走 `Lo/a;->d0(S,[B)`，不是此前 `game.g->y` 路由表能覆盖的发送方式。
- 新增 `Lo/a.d0` 发送入口扫描表：
  - `network_d0_send_calls.csv`：251 个 `Lo/a.d0(S,[B)` 发送点。
  - `network_d0_send_calls.json`：JSON 汇总。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fief_building_protocol_entries_report.md`
- 结构化数据：
  - `fief_building_protocol_entries.csv`：普通封地建筑/建设第一批入口与响应候选。
  - `fief_building_protocol_entries_summary.json`：封地建筑入口 JSON 汇总。
  - `method_disasm_fief_building/`：`q.K1/q.w1/q.d/q.g1/q.e/q.i` 等方法反汇编。
- 当前确认/候选入口：
  - `reqFiefInfo / 0x1246`：`q.g1(int,long)`，字段为 `mode/writeByte`、`fief_id/writeLong`。
  - `buildQueueAdd / 0x120D`：`q.K1(boolean)` 与 `q.w1()`，字段为 `fief_id/writeLong`、`building_or_slot_key/writeLong`。
  - `buildItemUse`：`q.d(int,long,int,long,short)`，opcode 由调用参数动态传入，字段为封地 ID、建筑位置/类型、道具/任务 ID、数量/参数 short。
  - `q.i(String)`：`0x8200 / signed -32256`，封地建筑建造/升级结果候选响应，含建筑错误码和 `Lo/a.j1` 封地建筑更新块。
  - `q.e(String)`：`0x8206 / signed -32250`，建筑队列/建筑相关操作结果候选响应。
- `q.i` 已恢复建筑错误码：封地不在、建筑不在、位置错误、条件不足、前提不足、君主不足、人口不足、铜钱不足、粮食不够、正在训练、书院只能一个、建造已满级、队列已满、5 个队列限制等。
- 当前边界：普通建筑“建造/升级/取消升级/拆除”的精确 opcode 分工仍需继续追 `q.K1/t1/u1/v1/L1` 与 `LscriptPages/data/f;->u(...)` 的封装发送逻辑。

## 30. 普通封地建筑动作协议字段初步

- 已完成普通封地建筑“建造/升级/拆除/取消/加速”动作协议第一版分工。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fief_building_action_protocol_report.md`
- 结构化数据：
  - `fief_building_action_fields.csv`：普通建筑动作请求字段、调用点语义、响应字段与证据。
  - `fief_building_action_summary.json`：普通建筑动作协议 JSON 汇总。
- 当前确认：
  - 普通建筑建造/升级/拆除/取消由 `LscriptPages/game/q;->h(int,long,int,int)` 构造，实际发送 opcode 为 `0x1200 / 4608`。
  - `q.h` 使用的流名字符串也是 `"fiefMove"`，但此处不是迁封 `0x1212`，而是普通建筑动作 `0x1200`。
  - `0x1200` 请求体字段顺序：`action/writeByte`、`fief_id/writeLong`、`slot_or_building_slot_key/writeShort`、`building_type_or_current_building_type/writeShort`。
  - 建造入口：`q.u1() -> q.h(0, q.o, Q1(p,a0), g0[f0])`，文案 `di_建造`。
  - 升级入口：`q.v1() -> q.h(0, q.o, Q1(p,a0), Z1(p,a0))`，文案 `di_升级`。建造和升级共用 `action=0`，由后两个 short 和当前格子状态区分。
  - 尝试拆除入口：`q.w1() -> q.h(1, q.o, Q1(p,a0), Z1(p,a0))`，文案 `di_联网尝试拆除`。
  - 取消操作入口：`q.t1()` 的 `cancelbuild` 分支最终调用 `q.h(2, q.o, Q1(p,a0), Z1(p,a0))`，文案 `di_联网取消操作`；此前候选的 `action=6` 已更正，附近的 `6` 是状态/按键判断，不是发送动作码。
  - `buildQueueAdd / 0x120D` 字段为 `fief_id/writeLong`、`building_instance_or_slot_id/writeLong`，用于建筑队列/拆除全部候选场景。
  - `buildItemUse` 为动态 opcode 通用封装，字段为 `fief_id/writeLong`、`building_pos_or_type/writeShort`、`item_or_task_id/writeLong`、`item_count_or_param/writeShort`；已确认候选调用包括 `4616/0x1208` 建筑加速、`4672/0x1240` 招募加速、`4619/0x120B` 科技加速。
  - 响应仍以 `q.i(String)` 的 `0x8200 / signed -32256` 作为建筑动作结果，`q.e(String)` 的 `0x8206 / signed -32250` 作为队列/相关操作结果。
- 对重建服务端的影响：服务端实现普通建筑时应把 `0x1200` 的 `action=0` 统一进入“建造或升级”判定，再根据目标格子是否已有建筑、目标/当前建筑类型 short 和服务端规则计算资源、前提、队列；不要信任客户端提交的道具数量、目标归属或剩余时间。
- 当前边界：`Lo/a.j1` 封地建筑同步块内部字段仍需单独深追；建筑产量、建筑升级消耗/时间、前置条件等数值表也仍需从配置/代码继续恢复。

## 31. 封地建筑同步块 `Z5/Y5/k1/j1/T5` 字段初步

- 已完成封地建筑同步块第一版深解析，覆盖完整封地列表、封地基础信息、普通建筑列表、封地级临时状态和每建筑嵌套任务。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/fief_building_sync_protocol_report.md`
- 结构化数据：
  - `fief_building_sync_fields.csv`：`Z5/Y5/k1/j1/T5` 字段顺序、缓存数组、证据与语义。
  - `fief_building_sync_summary.json`：封地建筑同步块 JSON 汇总。
  - `method_disasm_fief_sync/`：`Lo/a.j1`、`Lo/a.k1`、`Lo/a.Z5`、`Lo/a.Y5`、`Lo/a.T5`、访问器和 UI 证据方法反汇编。
- 当前确认：
  - 完整封地缓存入口为 `Lo/a.Z5(String)`：先读 `Lo/a.Ov/readByte` 作为每封地普通建筑槽位容量，再读 `fief_count/readByte`，每个封地依次 `readLong fief_id`、调用 `Y5(fief_id, stream)` 和 `j1(fief_id, stream)`。
  - `Y5` 是封地基础信息块，读取 `pv/qv/rv/sv/tv/uv/vv/wv/xv/yv/zv/Av` 等字段；其中 `xv` 是默认同时建筑队列容量，`U1` 会在 `k1` 队列加成未过期时用 `Iv[0]` 覆盖。
  - `k1` 三组状态已命名：铜钱增产 `Bv/Cv/Dv`、粮食增产 `Ev/Fv/Gv`、同时建筑队列加成 `Hv/Iv/Jv`。UI 证据分别来自 `di_提示铜钱增产`、`di_提示粮食增产`、`re_提示同时建筑`。
  - `j1` 普通建筑列表字段顺序：`building_count/readByte`，每条 `slot_position_id/readByte -> Vv`、`building_instance_id/readLong -> Pv`、`building_type/readByte -> Qv`、`building_level/readByte -> Rv`、`build_timer/readInt -> Sv`、`progress_or_unused/readInt -> Tv`、`state_sign/readLong -> Uv`，然后调用 `T5`。
  - `Vv` 是建筑槽位/位置编号，`Q1` 返回它并作为普通建筑动作 `0x1200` 请求第 3 字段；`Pv` 是建筑实例/任务 ID，`H1` 返回它并用于 `buildQueueAdd/buildItemUse`；`Qv` 是建筑类型，`Z1` 返回它；`Rv` 是建筑等级，`L1` 返回它。
  - `j1` 读取的 `Tv` int 字段会被客户端立即清零，服务端初版可发送 0。
  - `j1` 读取的 `Uv` long 只保留正负号：负数缓存为 `-当前时间`，非负缓存为 `当前时间`，供 `Y1` 区分建筑状态。
  - `T5` 是每建筑实例的嵌套生产/训练任务块，字段包括 `nested_action`、`nested_owner_building_id`、任务数量、任务 ID、状态 byte、目标类型 short、当前数量、目标/容量、剩余/总时间、状态标记、周期/间隔等。UI 通过 `an/bn/cn/dn/Zm` 展示产出/兵种、数量和剩余时间。
- 对重建服务端的影响：封地进入和建筑动作成功响应不能只同步资源，必须按 `Y5/k1/j1/T5` 的读流顺序构造字段；如果暂不实现复杂嵌套生产/训练，也要返回可被 `T5` 正确消费的空/删除型块，避免客户端读流错位。
- 当前边界：`Y5` 中若干封地基础字段 `pv/qv/sv/tv/uv/vv/wv/yv/zv/Av`、`Kv/Lv`、`Mv/Nv` 的精确业务名仍需结合 UI 渲染和动态样本继续命名；建筑升级消耗/时间/产量等规则数值另需解析配置表与公式。

## 32. 普通建筑规则数值表 `scriptBuilding.sc` 尾部解析初步

- 已从 `scriptBuilding.sc` 的建筑记录尾部恢复普通建筑每级规则数值第一版。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/tables/parsed/building_level_rules_report.md`
- 结构化数据：
  - `building_level_rules_combined.csv`：普通建筑每级成本、时间、效果/解锁、前置关键字段合并表。
  - `building_level_cost_rules.csv`：每级升级成本与耗时。
  - `building_level_effect_rules.csv`：大厅/房屋/农场的每级效果值。
  - `building_level_unlock_rules.csv`：步兵营/弓兵营/战车营/骑兵营的等级→解锁阶段。
  - `building_level_prereq_rules.csv`：15-byte 前置/门槛行结构化保留。
  - `building_tail_headers.csv`、`building_level_rules_summary.json`：解析头和 JSON 汇总。
- 当前确认：
  - 建筑尾部通用结构包含：表头 `header_flag/u8; label_a/u16le; label_b/u16le`，随后第一组 `prereq_count/u16be * 15-byte prereq rows`。
  - 升级成本组格式稳定：`tag/u8; count/u16be; count * (level/u8 + costA/u32be + costB/u32be + costC/u32be + time/u32be)`。
  - `costA/costB` 从错误码和数值规模看高度疑似铜钱/粮食；`costC` 当前样本全为 0；`time` 暂命名为 `build_time_seconds`，仍建议动态验证单位。
  - 大厅、房屋、农场存在产出/容量效果组：`tag=1; count; level + effect_a/effect_b/effect_c`。
    - 大厅 L1/L15 效果：`15 -> 1520`，对应铜钱产量候选。
    - 房屋 L1/L15 效果：`20 -> 1140`，对应人口上限候选。
    - 农场 L1/L15 效果：`25 -> 1145`，对应粮食产量候选。
  - 兵营类存在解锁组：`00 01; count; level + unlock_stage`，步兵营/弓兵营/战车营/骑兵营均大致为 L1-L3 阶段1、L4-L6 阶段2、L7-L9 阶段3、L10 阶段4。
  - 成本行数量显示：大厅/房屋/农场/书院为 15 级，兵营类为 10 级。旧 `buildings.json` 的“最大等级”字段对部分建筑不应直接作为升级上限，服务端重建应优先以尾部成本行数量作为等级上限候选。
- 当前边界：前置条件 15-byte 行已导出，但字段业务名仍需结合代码函数继续确认；建筑效果如何叠加科技/道具和离线产出仍需追资源系统。

## 33. 建筑前置条件 15-byte 行按 `Lo/a.U5` 真实读流命名第一版

- 已追到 `scriptBuilding.sc` 的真实读取器 `Lo/a;->U5(String)`，并据此修正普通建筑前置条件 15-byte 行字段解释。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/tables/parsed/building_prereq_field_mapping_report.md`
- 结构化数据：
  - `building_level_prereq_rules_named.csv`：按 `U5` 真实读流命名的前置条件行。
  - `building_prereq_field_mapping_summary.json`：字段映射、统计和证据汇总。
  - `building_level_rules_combined_named.csv`：成本/效果/解锁与命名版前置字段合并表。
  - `method_disasm_building_rules/o_a__U5__0x23e8d4.smali.txt`：真实表读取器反汇编。
- 当前确认：
  - `U5` 对前置条件行的读流为：`level/readByte -> index=level-1`、`pn/readShort -> cast byte`、`qn/readByte`、`rn/readByte`、`sn/readShort -> cast byte`、`tn/readByte`、`un/readShort -> cast byte`、`vn/readInt`、`trailing/readByte`。
  - `Lo/a.R1(building, level)` 返回 `qn[building][level-1]`。
  - `q.l(I,I)` 的本地建造/升级前置检查明确读取 `un[building][level-1]` 作为“所需建筑类型”，若 `un != -1`，再用 `R1` 取所需等级，并扫描当前封地 `Qv/Rv` 判断是否已有对应建筑且等级满足。
  - 当前静态表中 `un_required_building_type_for_q_l` 全部为 `-1`，说明该客户端本地前置路径存在，但这版表未使用它；前置/高等级门槛更可能由服务端权威校验，或由 `rn/trailing` 等字段体现。
  - `rn_req_role_or_gate_level` 在 100 行里只有 `0` 和 `20`：其中 15 行为 `20`，集中对应 15 级建筑的 L11-L15，疑似角色/君主等级或高等级门槛。
  - `trailing_flag_byte` 被 `U5` 消费但不缓存，主要在高等级行取 `1`，候选为行标记/高等级标志。
- 当前边界：`pn/sn/tn/vn` 的精确业务名仍未完全确认；本轮先纠正字段偏移和真实读流，避免沿用旧表中的错误偏移解释。服务端重建时应把这些字段保留为规则输入，并以服务端校验为准。

## 34. 建筑产出/人口/征兵队列字段命名第一版

- 已结合 `Lo/a.U5` 读表、`D1/F1/P1/N1` 访问器和 UI 文案，完成普通建筑效果字段高置信命名。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/tables/parsed/building_effect_queue_field_mapping_report.md`
- 结构化数据：
  - `building_level_effect_rules_named.csv`：大厅/房屋/农场每级效果的命名版，字段为铜钱产量、粮食产量、人口上限。
  - `building_recruit_queue_rules_named.csv`：兵营每级征兵队列数量，修正此前“解锁阶段”的宽泛命名。
  - `building_level_rules_server_ready.csv`：当前最适合服务端重建使用的普通建筑每级规则合并表。
  - `building_effect_queue_field_mapping_summary.json`：字段命名证据 JSON 汇总。
- 当前确认：
  - `Lo/a.D1(building, level)` 返回 `En`，UI 文案 `di_标题铜钱` / `di_铜钱产量` 调用它，命名为铜钱产量/铜钱加成。
  - `Lo/a.F1(building, level)` 返回 `Fn`，UI 文案 `di_产量` / `di_粮食产量` 调用它，命名为粮食产量。
  - `Lo/a.P1(building, level)` 返回 `Gn`，UI 文案 `di_人口上限` / `di_人口加成` 调用它，命名为人口上限/人口加成。
  - `Lo/a.N1(building, level)` 返回 `Hn`，UI 文案 `di_标题征兵队列` 后追加它，命名为征兵队列数量。
  - 对 `scriptBuilding.sc` 尾部格式作了修正：效果区域不是简单 `tag=1`，而是 `group_count/readByte` 后按 `group_type` 分组；产出效果区域的 `group_type=0` 对应 `En/Fn/Gn` 三个 int，征兵队列区域的 `group_type=0` 对应 `Hn` byte。
- 对重建服务端的影响：普通建筑每级规则可优先使用 `building_level_rules_server_ready.csv`；大厅填铜钱产量，农场填粮食产量，房屋填人口上限，兵营填征兵队列数量。最终资源到账仍需后续叠加科技、道具 buff、离线时间和仓储上限公式。
## 35. 建筑产出最终显示值与临时增产状态第一版

- 已完成建筑产出公式链路第一版整理：确认“建筑等级静态效果值”和“封地最终产量显示字段”不是同一层。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/building_output_formula_report.md`
- 结构化数据：
  - `building_output_formula_fields.csv`：`Y5/k1/q.L/D1/F1/P1/N1` 相关字段命名、读法、语义和服务端重建备注。
  - `building_output_formula_summary.json`：建筑产出链路第一版结论与未确认项。
  - `building_output_formula_refs.md/json`：全 DEX 范围内建筑产出相关方法/字段引用索引。
  - `method_disasm_building_output/`：`o4/r4/Y2/T7/X7/A0/O0/e8/k0.g/k0.h/k0.o` 等候选方法反汇编。
- 当前确认：
  - `Lo/a.Y5(long,String)` 直接从服务器同步 `tv/readInt` 和 `uv/readInt`；`scriptPages/game/q.L()` 在封地概览中把 `tv` 展示为“产钱/小时”，把 `uv` 展示为“产粮/小时”。
  - 因此 `tv/uv` 应命名为 `coin_output_per_hour`、`food_output_per_hour`，是封地最终显示产量，而不是 UI 层由建筑列表即时累加。
  - `Lo/a.k1(int,String)` 三组临时状态结构已复核：`Bv/Cv/Dv` 为铜钱增产，`Ev/Fv/Gv` 为粮食增产，`Hv/Iv/Jv` 为建筑队列/同时建设加成；`q2/J2/V1` 负责把结束时间换算成剩余秒。
  - `q.L()` 还确认了若干封地基础字段：`d2(fief)/U1(fief)` 为建筑队列当前/上限，`o4(fief)` 是 `Lv` 总和并显示为闲兵，`R4(fief)/Av[fief]` 为征兵队列当前/上限，`yv/zv` 显示为驻防当前/上限。
  - 建筑等级静态效果仍以 `building_level_rules_server_ready.csv` 为准：大厅给铜钱产量、农场给粮食产量、房屋给人口上限、兵营给征兵队列数量。服务端重建时应在服务端计算最终 `tv/uv` 后下发。
- 当前边界：`tv/uv` 是否已经合入临时增产 buff 仍需有/无增产状态动态对比；`vv/wv` 与 `Mv/Nv` 第二组类型数量仍未完全命名；资源上限、离线累计、科技/道具/称号加成公式还需继续追踪。

## 36. 出征/战斗结算协议第一版

- 已完成出征/战斗结算协议第一版整理，覆盖正式出征、预提示、山贼列表、战报详情和战斗回放/指令流。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/expedition_protocol_report.md`
- 结构化数据：
  - `expedition_request_fields.csv`：`expeditionPreTipInfo/0x1520`、`expedition/0x1522`、`reqThiefList/0x1540`、`reqCheckMsg/0x1114`、`REQ_FIGHTINFO/0x1702/0x1707` 请求字段顺序。
  - `expedition_response_fields.csv`：出征响应、`scriptPages/data/a.B` 状态快照、战报详情和战斗指令流字段骨架。
  - `expedition_protocol_summary.json`：协议链路、行动类型、状态文案和服务端重建影响 JSON 汇总。
  - `method_disasm_expedition/`：`p.N/O/Q/k1`、`data.a.B/C/a/b`、`h0.Z/a0`、`s.c0/Y/Z` 等反汇编证据。
- 当前确认：
  - `LscriptPages/game/p;->O(I,[J,J)V` 发送 `expeditionPreTipInfo`，opcode `0x1520 / 5408`，请求体为 `expedition_type`、`general_count`、`general_id[]`、`target_id`；同时缓存 `p.k0/p.l0/p.m0`。
  - `LscriptPages/game/p;->N(I,[J,J,B,B,B,J)V` 发送正式 `expedition`，opcode `0x1522 / 5410`，请求体为 `expedition_type`、`general_count`、`general_id[]`、`target_id`、`related_long`、`attack_strategy`、`attack_mode`、`unknown_flag`。
  - `LscriptPages/game/p;->Q(String)` 是正式出征响应读取器：先读 `result_code/readByte` 与 `message/readUTF`；成功时再读 `fight_or_expedition_id/readLong -> p.n0`，随后调用 `scriptPages/data/a.B(stream)` 消费完整状态快照。
  - `scriptPages/data/a.B(String)` 不是单一出征记录，而是一整个地图/出征/封地状态同步块：先读坐标短整型矩阵，再按 tag=1/2/3 读取己方出征队列、地图目标/点位、敌方或其他出征队列，末尾再读两组额外状态位并调用 `Lo/a.f6(0/1)`、`Lo/a.S5` 同步封地/全局状态。
  - `scriptPages/data/a.<clinit>` 确认 17 个行动类型文案：派遣、掠夺、驻守、阻击、攻占、消灭、返回、侦查、闯关、抢城、城主竞选、出征副本、竞技场、押镖、寻宝、攻占、攻占；状态文案为行军中、战斗中、返回途中、等待中、已返回。
  - `LscriptPages/game/p;->k1(I,I)V` 发送 `reqThiefList`，opcode `0x1540 / 5440`，请求体为 `x/writeShort`、`y/writeShort`；结合抓包，它按坐标/区域返回一批山贼，不是一次返回全图。
  - `LscriptPages/game/h0;->Z(J)V` 发送 `reqCheckMsg`，opcode `0x1114 / 4372`，请求体为 `message_or_report_id/writeLong`；前序动态重放验证表明该接口主要用于详情展示，不重复发放奖励。
  - `LscriptPages/game/s;->c0(J,I)V` 发送 `REQ_FIGHTINFO`：`fight_info_type <= 3` 使用 `0x1702 / 5890` 并额外写 `s.o1` 与常量 `300000`，`fight_info_type > 3` 使用 `0x1707 / 5895`；`s.Y/s.Z` 读取战场初始化与指令流。
- 对重建服务端的影响：正式出征成功响应必须返回 `0 + message + expedition_id + a.B状态快照`；战报详情接口只负责展示；战斗过程可先以服务端权威结算+最小指令流实现，完整体验再补 `s.Y/s.Z` 的战场初始化和指令格式。
- 当前边界：`attack_strategy/attack_mode/unknown_flag` 的 UI 精确语义仍需继续对应；`a.B tag=1/2/3` 的业务命名还需要更多动态样本；基础伤害、胜负、伤兵和山贼奖励掉落公式仍未完整恢复。

## 37. 战斗核心公式/蓄力/坐标状态汇总

- 已把当前战斗公式、攻速蓄力、坐标坑位的恢复状态整理为服务端重建可用摘要。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_deep/battle_formula_coordinate_status_report.md`
- 结构化数据：
  - `battle_formula_coordinate_status.csv`：基础伤害、普通攻击损兵、战法损兵、攻速/C0、蓄力状态、坐标坑位、战斗结束/胜负的确认状态。
  - `battle_formula_coordinate_status_summary.json`：核心结论、关键文件、服务端重建优先级。
- 当前确认：
  - 客户端 `scriptPages/game/s.Z/f0/p0` 路径是战斗回放/表现层执行器，不是完整权威伤害计算器。
  - 普通攻击 `command type 6` 携带目标攻击后剩余值；客户端用旧兵数/城墙值与新值差额显示损兵并同步状态。
  - 战法/技能攻击 `command type 11` 携带 `beforeValue/afterValue`；客户端用 `before-after` 显示损兵/效果。
  - `C0[S]` 是攻击间隔/蓄力上限，单位毫秒；新协议 `command type 1` 直接读取 `attackIntervalMs/readShort`，经 `s.j -> s.f0 -> s.h` 写入 `C0`。旧协议仅存在 `4000/5000/7000ms` 的兼容推断，不是完整攻速公式。
  - `F0` 是蓄力开始时间戳，`E0` 是暂停时剩余时间，`D0` 是蓄力增减偏移累计；`p0` 中 buff 可暂停/恢复蓄力并直接修改 `C0/D0/E0/F0`。
  - 战场坐标是 2D 像素表现层：`B/I` 计算 X，`C/J` 计算 Y；阵营左右镜像，`lane/col` 控制排/列，阵型偏移 `G` 来自 `H[formation]`，移动每 tick 最多 20 像素逼近目标。
  - `command type 7` 是战斗结束标记；胜负和奖励由服务端结果/战报详情给出。
- 对重建服务端的影响：服务端需要权威生成胜负、损兵、奖励与资源到账；客户端可通过最小战斗指令流回放。基础伤害公式若继续无法从客户端恢复，需要根据兵种/武将/战报样本拟合，或重新设计兼容公式。
- 当前边界：攻击/防御/生命/兵数/科技/装备/称号如何合成为基础伤害仍未在客户端闭环；目标选择中的“身后/前后左右”属于服务端战斗逻辑，还需结合战法目标规则和样本继续恢复。

## 38. 山贼系统规则第一版

- 已将山贼地图与全图扫描数据从临时漏洞验证目录正式沉淀到规则库。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/bandit_system/bandit_system_report.md`
- 结构化数据：
  - `bandit_all_unique_enriched.csv`：旧全量去重表 5224 伙山贼，补充掉落 ID 候选名称字段。
  - `bandit_level_stats.csv`：按等级统计数量、资源范围/均值、守军数量、描述和兵种大类。
  - `bandit_unit_category_combo_stats.csv`：按等级统计守军大类组合分布。
  - `bandit_loot_id_mapping.csv` / `bandit_loot_id_mapping_enriched.csv`：山贼地图 `loot_ids` 出现频次、等级分布和编码候选映射。
  - `level7_all_units_raw.csv`：修正后的 7 级山贼 596 伙守军大类明细。
  - `level7_pure_archer_major.csv`：7 级纯弓弩大类山贼 4 伙。
  - `bandit_system_summary.json`：山贼系统第一版 JSON 汇总。
- 当前确认：
  - `reqThiefList / 0x1540 / 5440` 是山贼地图列表请求，入口为 `LscriptPages/game/p;->k1(I,I)V`，请求体为 `x/writeShort`、`y/writeShort`。
  - 单次 `reqThiefList` 不是返回全图，而是按当前坐标/区域返回一批山贼；样本 `query_x=91, query_y=26` 返回 11 伙，覆盖 `x=91..93, y=26..31`。
  - 全等级统计当前基于旧全量去重表 `all_unique_bandits.csv`：5224 伙，等级 1..10，坐标约 x=0..184、y=0..55。后一次 corrected 扫描元信息显示全图去重 5424 伙，但该目录只保留了修正后的 7 级明细，因此报告中明确区分数据来源。
  - 各等级资源显示范围高度分层：1级约 40..60 / 100..150，5级约 250..300 / 600..800，7级约 500..700 / 1400..1700，10级约 1801..2200 / 4500..5486。`resource1/resource2` 从战报看分别高度疑似铜钱/粮食候选。
  - 守军槽数量随等级提升：1..3 级多为 1 槽，4..5 级多为 2 槽，6..7 级多为 3 槽，8..9 级多为 4 槽，10 级多为 5 槽；旧全量表存在少量 7/8/9/10 级 2/3 槽样本，需以后续动态样本复核。
  - 修正后的 7 级山贼中，将领守军大类全部为弓弩的只有 4 伙：`(18,49)`、`(34,4)`、`(103,7)`、`(181,8)`。
  - 山贼地图 `loot_ids` 多数不是直接 `item_id`，因为 `item_full_mapping.csv` 最大 item_id 为 757，而样本中常见 `1064/1793/13569/14849/29441` 等高值；已输出 low10/low12/minus1024/minus3072 等候选解码，但不把候选当作最终事实。
- 对重建服务端的影响：山贼列表接口应按区域/视野返回部分山贼；每伙山贼至少需要 `target_id/name/level/x/y/desc/resource1/resource2/loot_ids/unit_count/units`；最终战斗奖励还应由服务端结算生成，地图列表中的资源/掉落更像可见奖励/候选奖励字段。
- 当前边界：山贼刷新周期、`loot_ids` 真实编码函数、地图资源字段与战报铜钱/粮食/声望的最终结算公式、不同等级山贼守军模板生成规则仍需继续追踪。
## 39. 资源系统第一版

- 已完成全局资源、封地资源、产出显示和奖励到账同步链路第一版整理。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/resource_system_report.md`
- 结构化数据：
  - `resource_field_mapping.csv`：全局资源、封地资源、产出、人口/资源点候选字段命名表。
  - `resource_sync_chains.csv`：`i.x/i.b/i.z/i.A/m0.u/Lo.a.Y5/Lo.a.k1/data.g.w0` 等同步链路。
  - `resource_system_summary.json`：资源系统第一版 JSON 汇总。
  - `method_disasm_resource/` 与 `method_disasm_resource_extra/`：关键方法反汇编和引用证据。
- 当前确认：
  - `scriptPages/data/i.d` 为铜钱，`scriptPages/data/i.e` 为粮食；`scriptPages/data/g.F` 为黄金，`scriptPages/data/g.G` 为白银；`scriptPages/data/i.i` 为当前声望。
  - `scriptPages/data/i.m` 为总产钱/小时，`scriptPages/data/i.n` 为总产粮/小时；`scriptPages/data/i.A()` 会按 `m/n` 与本地时间差对 `d/e` 做显示层递增，公式为 `floor((now-last_time)*产量/3600000)`，但这不是权威结算。
  - `Lo/a.Y5` 下发的 `tv/uv` 是单封地产钱/产粮每小时最终显示值；`q.L/q.u` 直接展示 `tv/uv + 小时`，说明建筑静态表到最终封地产量之间的叠加应由服务端完成后同步。
  - `scriptPages/game/m0.u` 奖励领取成功后同步 `data.i.i`、`data.i.d`、`data.i.e`、`data.g.H` 和 `Lo/a.V5`，与前面动态验证“奖励实际到账在服务端结算/同步块完成”一致。
  - `scriptPages/data/g.w0(int)` 负数资源 ID 映射已确认：`-1=铜钱`、`-2=粮食`、`-3=白银`、`-4=黄金`、`-5=声望`、`-6=战功候选`、`-14=data.g.H`；后续第 46 节已把 `data.g.H` 修正命名为账号积分。
  - `data.g.H` 已不再按玉石候选处理；玉石是 `item_id=399` 的普通/功能道具。
  - 人口字段候选为 `data.i.q/r`，资源点候选为 `data.i.u/v`，封地上限候选为 `data.i.s`，将领上限候选为 `data.i.t`；其中人口、资源点、封地/将领上限仍需跨模块复核。
- 对重建服务端的影响：服务端需要权威保存并同步铜钱、粮食、黄金、白银、声望、声望阈值、总产量、封地产量、人口/资源点/封地/将领上限；客户端本地递增只用于展示，关键操作后必须用服务端同步覆盖。
- 当前边界：仓储上限、离线产出截断、掠夺损失、人口/资源点上限公式尚未完全恢复；`data.g.H` 最终命名见第 46 节。
## 40. 仓储/离线产出/资源点系统第一版

- 已把资源系统深追中的“个人仓储上限、离线产出、资源点储量/产量”整理成第一版报告。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/storage_offline_system/storage_offline_resource_point_report.md`
- 结构化数据：
  - `storage_offline_field_mapping.csv`：个人仓储、离线产出、显示递增、人口/资源点候选、征兵数量约束等字段映射。
  - `resource_point_protocol_fields.csv`：`reqResourceList/0x1542`、`p.f`、`p.c1`、`p.P0`、`p.M0` 的资源点协议字段骨架。
  - `storage_offline_summary.json`：仓储/离线/资源点第一版 JSON 汇总。
  - `storage_offline_string_field_hits.md/json`、`storage_more_terms_hits.json`：关键词与字段命中证据。
  - `method_disasm_storage/` 与 `method_disasm_resource_point/`：关键方法反汇编证据。
- 当前确认：
  - 客户端未找到个人铜钱/粮食仓储上限的明确字段、同步块或本地截断公式；`仓库`命中主要是装备仓库文案，不是资源仓库。
  - `离线`关键词只命中腾讯 push SDK；APK 内未发现离线产出权威公式。已确认的 `scriptPages/data/i.A()` 只是显示层按小时递增 `data.i.d/e`，且未见上限 clamp。
  - `di_标题储量`、`di_产量` 等命中主要属于资源点列表/详情 UI；当前更应解释为资源点储量/产量，而不是玩家个人仓储上限。
  - `LscriptPages/game/p;->h1(I,I)V` 发送 `reqResourceList`，opcode `0x1542 / 5442`，请求体为 `x/writeShort`、`y/writeShort`。
  - `LscriptPages/game/p;->f(String)` 是资源点列表响应候选：非快照分支读取区域坐标、记录数，然后循环读取 `q5/r5/s5/t5/u5/v5/w5/x5/y5/z5/A5/B5/O5/P5/D5/C5/F5/E5/G5/H5/I5/J5/Q5/R5/S5/K5/L5`，末尾再读 `M5[]` ID 列表。
  - `LscriptPages/game/p;->c1(String)` 与 `p.f` 基本同构，字段前缀为 `T5/U5/V5...o6`，推断是另一资源点/目标列表视图。
  - `LscriptPages/game/p;->P0(String)` 是单资源点详情/驻军明细候选，成功时读取名称、坐标、描述、两个 int 数值与 `O6..V6` 数组。
  - `scriptPages/data/g.z0(I,I)` 使用铜钱、粮食、剩余人口三者约束计算可征兵数量，进一步支持 `data.i.q/r` 为人口当前/上限候选，而非仓储上限。
- 对重建服务端的影响：初版可先不实现个人资源仓储上限，或做成服务端配置策略；登录/关键操作后由服务端权威同步资产。资源点系统需要按区域返回列表，并至少建模 `id/type/name/x/y/status/owner/level/production/storage/bonus/garrison/timers` 等字段。
- 当前边界：不能断言游戏一定没有仓储上限，只能说客户端未闭环；资源点大量数值字段仍需动态响应样本和 UI 截图进一步命名；资源点刷新、占领收益、掠夺损失、离线服务端结算仍待继续。
## 41. 资源点/攻城目标字段语义深追第一版

- 已基于 `p.s/p.t` UI 显示路径，把 `p.f` 与 `p.c1` 两套同构目标列表字段从“读流骨架”推进到标签级语义映射。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/storage_offline_system/resource_point_field_semantics_report.md`
- 结构化数据：
  - `resource_point_field_semantics.csv`：`p.f` 字段、`p.c1` 同构字段、显示标签、语义判定、置信度和服务端重建建议。
  - `resource_point_field_semantics_summary.json`：资源点/攻城目标字段语义深追 JSON 汇总。
- 当前确认：
  - `scriptPages/game/p.s()` 明确构造并显示 `di_国家`、`di_天赋`、`di_标题封地`、`di_城主`、`di_驻防将领`、`di_道路`、`di_城墙`、`di_名将协防`、`di_协防几率`、`di_名将数量`、`di_攻克奖励`、`di_标题战功`、`di_国库铜钱`、`di_国库粮食` 等标签。
  - `q5/T5` 为目标 ID，`r5/U5` 为类型码，`s5/V5` 为名称，`t5/u5` 与 `W5/X5` 为坐标。
  - `J5/m6` 对应国家/势力；`G5/H5` 与 `j6/k6` 对应城主或守将名称/等级。
  - `w5/x5` 与 `Z5/a6` 对应天赋/加成显示，形如 `+N%`。
  - `D5/C5` 与 `g6/f6` 显示在“封地”标签下，是当前/上限或规模/上限字段。
  - `F5/E5` 与 `i6/h6` 显示在“驻防将领”标签下，是驻防将领数量/上限。
  - `y5/b6` 显示在“道路”标签下；`A5/d6` 显示在“城墙”标签下。二者究竟是等级、耐久还是防御值仍需动态样本确认。
  - `Q5/r6` 为名将协防概率/开关：大于 0 时显示协防区块；`R5/s6` 两个 byte 显示名将数量范围。
  - `S5[0]/t6[0]`、`S5[1]/t6[1]`、`S5[2]/t6[2]` 分别显示攻克奖励的国库铜钱、国库粮食、战功。
- 对重建服务端的影响：`reqResourceList/5442` 类目标列表不能只返回资源点名称和坐标，还要返回国家、天赋、封地、城主、驻防将领、道路、城墙、协防概率、名将数量范围、攻克奖励三元组以及兼容扩展字段。
- 当前边界：`z5/B5/O5/P5` 与 `c6/e6/p6/q6` 仍未在主面板命名；`K5/L5` 与 `n6/o6` 的时间/状态语义仍需真实响应样本；`reqResourceList` 的中文业务名暂称“资源点/攻城目标/城池目标列表”，不要过早收窄。
## 42. 资源点/攻城目标剩余字段与道路城墙语义补充

- 已对 `v5/z5/B5/O5/P5/K5/L5/M5` 与同构 `Y5/c6/e6/p6/q6/n6/o6` 做全 DEX 静态引用扫描，并补充道路/城墙规则语义。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/storage_offline_system/resource_point_remaining_fields_report.md`
- 结构化数据：
  - `resource_point_remaining_fields.csv`：剩余字段引用情况、语义结论、证据和服务端重建建议。
  - `resource_point_remaining_fields_summary.json`：剩余字段与道路城墙语义补充 JSON 汇总。
  - `resource_point_remaining_refs/field_refs.md/json`：全 DEX 字段引用扫描结果。
- 当前确认：
  - `v5/z5/B5/O5/P5/K5/L5` 与 `Y5/c6/e6/p6/q6/n6/o6` 在静态 DEX 中除 `p.f/p.c1` 读取/存储外，未发现其他 UI 或逻辑方法使用；因此当前不能强行命名为产量/储量，只能保守标为隐藏状态、兼容字段或时间候选。
  - `M5[]` 读取后会与 `q5[]` 做 ID 匹配，命中后设置 `N5[index]=true`；因此 `M5[]` 是当前列表目标 ID 标记集合候选。
  - `y5/b6` 已确认是“道路”显示值；`A5/d6` 已确认是“城墙/城防”显示值。
  - 文本规则确认：修筑道路提高城池道路值，道路值越高军队行动速度越快；修筑城墙提高城池防御值，城防越高驻防部队战斗力越高。
  - 修墙换算文本高置信：`60 粮食 = 1 点城墙`，`1 黄金 = 1000 点城墙`；修路换算还需继续抽取 `scriptPages/game/k.D1` 完整分支。
- 对重建服务端的影响：`road_value` 和 `wall_value` 应作为城池/攻城目标核心字段；隐藏字段要按协议顺序保留，初版可返回 0；`M5[]` 不确定时可返回空数组；修墙公式可先按文本实现。
- 当前边界：`M5[]/N5[]` 标记业务名、`K5/L5/n6/o6` 时间含义、隐藏 int 字段真实含义、修路完整换算、道路到行军速度/城墙到战斗加成公式仍需继续。


## 43. 道路/城墙公式深追第一版

- 已把修墙/修路换算、贡献显示公式和修筑请求协议整理成第一版。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/storage_offline_system/road_wall_formula_report.md`
- 结构化数据：
  - `road_wall_formula_fields.csv`：道路/城墙/修筑请求字段与公式证据表。
  - `road_wall_formula_summary.json`：道路/城墙公式深追 JSON 汇总。
  - `road_wall_disasm/`：`k.D1`、`k.d`、`k.i1` 等关键方法反汇编证据。
- 当前确认：
  - `road_value` 为道路值；文本明确“道路值越高，军队行动速度越快”，且“道路不通，无法阻击”。
  - `wall_value` 为城墙/城防值；文本明确“城防越高，驻防部队战斗力越高”。
  - 修墙换算：`60 粮食 = 1 城墙`，`1 黄金 = 1000 城墙`。
  - 修路换算：`300 粮食 = 1 道路`，`1 黄金 = 500 道路`。
  - 客户端确认文案中的贡献显示公式：粮食修墙 `min(floor(输入粮食/3000), b1)`；黄金修墙 `min(输入黄金*20, b1)`；粮食修路 `min(floor(输入粮食/3000), d1)`；黄金修路 `min(输入黄金*50, d1)`。
  - 修筑请求方法为 `LscriptPages/game/k;->i1(J,String,int,int,long)V`，请求名复用 `reqCityGarrisonList`，opcode `4868 / 0x1304`，请求体为 `byte 0 + city_id/long + repair_type/byte + currency_type/byte + amount/long`。
  - `repair_type`：`1=修墙`、`2=修路`、`3=修塔候选`；`currency_type`：`0=粮食`、`1=黄金`；`amount` 是输入资源数量。
- 对重建服务端的影响：修筑接口应由服务端权威检查资源、权限、上限和贡献额度，然后同步最新资源、贡献、道路/城墙状态。
- 当前边界：道路值到行军速度的精确公式、城墙/城防到守军战斗力加成公式、修塔完整规则仍未恢复。

## 44. 修筑成功响应字段深追

- 已确认修墙/修路/修塔候选请求 `0x1304 / 4868` 的响应同步链路。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/storage_offline_system/repair_response_report.md`
- 结构化数据：
  - `repair_response_fields.csv`：`0x8304 -> k.r0(String)` 响应字段顺序、目标缓存和语义表。
  - `repair_response_summary.json`：修筑响应字段 JSON 汇总。
  - `repair_response_disasm/`：`k.r0/k.n1/k.s1/k.o1` 与 `i.p` 引用反汇编证据。
- 当前确认：
  - dispatcher `Lo/a;->A6` 在 `000d98-000da0` 将 signed short `-31996`，即 unsigned `0x8304`，分发到 `LscriptPages/game/k;->r0(String)`。
  - 响应头读取 `status/readByte` 与 `message/readUTF`；函数末尾统一显示服务端 message；`status=-8` 会额外调用 `Lo/a.f6(0,dis)` 读取通用同步块。
  - 响应直接同步 `data.g.F=黄金`、`data.i.e=粮食`、`data.i.p=贡献`。`data.i.p` 已通过君主/国家 UI 的 `di_贡献` 文案高置信确认。
  - 若 `city_id != -1`，响应继续读取并同步 `wall_current/wall_max`、`road_current/road_max`、`tower_current/tower_max` 候选，以及修墙/修路/修塔三组贡献额度二元组。
  - `k.n1` 写入 `Y0=wall[2]`、`Z0=road[2]`、`a1=tower[2]`、`b1/c1=修墙贡献对`、`d1/e1=修路贡献对`、`f1/g1=修塔贡献对`。其中 `b1/d1/f1` 已被 `k.D1` 用作确认文案贡献上限。
  - 城池状态会同步到 `data.b.v/w/x`、当前修筑面板缓存、邻近城池列表缓存、角色城池列表缓存，并调用 `s0.h0(...)` 更新地图城市摘要。
- 对重建服务端的影响：修筑响应不能只返回成功码；初版至少要返回最新黄金、粮食、贡献、城池 ID、城墙/道路 current/max、炮塔占位以及贡献额度字段，否则客户端 UI/缓存会错位或不刷新。
- 当前边界：响应头 3 个未保存字段仍是兼容字段候选；`c1/e1/g1` 的精确含义和修塔完整规则仍待动态样本。

## 45. 道路速度与城防战斗加成公式静态追踪状态

- 已对 `data.b.v/w/x` 与 `k.Y0/Z0/a1` 做全 DEX 引用扫描，确认道路/城墙数值在客户端的使用边界。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/storage_offline_system/road_wall_effect_formula_status_report.md`
- 结构化数据：
  - `road_wall_effect_formula_status.csv`：道路速度、城防加成、炮塔公式的恢复状态和服务端重建建议。
  - `road_wall_effect_formula_status_summary.json`：静态追踪状态 JSON 汇总。
  - `road_wall_usage_refs/road_wall_usage_refs.csv/json`：字段引用扫描证据。
- 当前确认：
  - `data.b.v / k.Y0` 是城墙/城防 current/max；`data.b.w / k.Z0` 是道路 current/max；`data.b.x / k.a1` 是炮塔 current/max 候选。
  - 这些字段的引用只集中在数据访问器、初始化、城池详情/修筑 UI、修筑输入上限、`0x8304 -> k.r0` 响应同步和地图/列表缓存刷新中。
  - 未发现道路值参与客户端本地行军时间/速度计算。
  - 未发现城墙/城防值参与客户端本地战斗伤害、攻防或损兵计算。
  - 结合战斗系统前序结论，客户端更像表现/回放层；道路速度和城防战斗加成大概率由服务端结算或下发结果决定。
- 对重建服务端的影响：道路/城墙字段必须权威保存并同步；道路速度和城防战斗加成初版可做配置化公式。若追求高还原，需要采集不同道路值行军耗时、不同城墙值攻城战报样本做拟合。
- 当前边界：静态结论只能说明客户端未见闭环公式；原服务端公式仍需动态样本或历史服务端资料恢复。炮塔攻击/伤害规则仍未展开。

## 46. data.g.H 最终命名与玉石区分

- 已把 `scriptPages/data/g.H` 从“玉石/扩展货币候选”修正为“账号积分”，并明确玉石应作为独立道具建模。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/gH_currency_deep/gH_identity_report.md`
- 结构化数据：
  - `gH_identity_evidence.csv`：`data.g.H` 命名证据链与玉石区分证据。
  - `negative_resource_id_mapping_corrected.csv`：负数资源 ID `-1..-14` 修正映射表。
  - `gH_identity_summary.json`：`data.g.H` 命名 JSON 汇总。
  - `gH_field_refs.csv/json`：`data.g.H` 精确字段引用扫描。
  - `jade_string_method_refs.csv/json`：玉石相关 UI/流程字符串引用扫描。
- 当前确认：
  - `LscriptPages/data/g;-><clinit>` 初始化 `f8` 资源名表，第 14 项是“账号积分”。
  - `LscriptPages/data/g;->v0(I)` 对负数资源 ID 返回 `f8[abs(id)-1]`，因此 `v0(-14)=账号积分`。
  - `LscriptPages/data/g;->w0(I)` 对 `-14` 返回 `data.g.H`，因此 `data.g.H=账号积分数量字段`。
  - 登录/全量同步 `data.i.b`、奖励领取 `m0.u`、六部/部门响应 `a0/a.c2` 都会同步 `data.g.H`。
  - `玉石` 是道具表中的 `item_id=399`，描述为“价值连城，用途广泛，可用于科技升级、将领空位激活、装备炼魂、六部系统使用和帅府系统使用等”。
  - 客户端存在大量玉石 UI 文案，如 `di_玉石`、`玉石或黄金`、`使用玉石`、`di_需要玉石`、`di_玉石兑换`，但这些字符串没有直接引用 `data.g.H`，不能作为 `H=玉石` 的证据。
- 对重建服务端的影响：资源模型应将 `account_points -> data.g.H/resource_id=-14` 与 `jade_item -> item_id=399` 分开保存和同步；不要把账号积分当作玉石余额。
- 当前边界：账号积分具体获取/消耗入口仍需继续追；玉石消耗协议分散在科技、将领空位、装备炼魂、六部、帅府等模块，需后续分模块整理。

## 47. 人口/资源点/封地/将领上限字段第一版

- 已完成 `scriptPages/data/i` 中人口、资源点、封地、将领容量字段的第一版命名。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/limits_deep/limit_fields_report.md`
- 结构化数据：
  - `limit_field_mapping.csv`：`data.i.q/r/u/v/s/t` 字段、类型、同步位置、UI 证据、逻辑证据和服务端重建建议。
  - `limit_formula_summary.json`：人口/资源点/封地/将领上限字段与征兵可招数量公式 JSON 汇总。
  - `limit_field_refs.csv/json`：相关字段全 DEX 引用扫描。
- 当前确认：
  - `data.i.q` = 人口当前占用；`data.i.r` = 人口上限。`q.u` 的 `di_人口占用` 与 `k0.o` 首页资源摘要均显示 `q/r`。
  - `data.i.u` = 资源点当前占用/当前数量；`data.i.v` = 资源点上限。`k0.o` 的 `di_标题资源点` 显示 `u/v`。
  - `data.i.s` = 封地上限。`k0.o` 的 `di_标题封地` 显示 `Lo/a.s2().length / s`，`data.i.h()` 直接返回 `s`。
  - `data.i.t` = 将领上限。`z.o` 的 `di_将领数` 显示 `Lo/a.M2(0).length / t`，`data.i.w()` 直接返回 `t`。
  - 全量同步 `LscriptPages/data/i;->x(String)` 依次读取 `q/r/s/t/u/v`。
  - tagged update `LscriptPages/data/i;->b(String)` 中 `tag=6/7/8/9/13/14` 分别同步 `q/r/s/t/u/v`。
  - 短同步 `LscriptPages/data/i;->z(String)` 会刷新铜钱、粮食、`q/r`、黄金、白银，说明人口字段会随资源类响应更新。
- 已恢复征兵可招数量公式：

```text
coin_cap = floor(data.i.d / (g.Q1(soldierType) * multiplier))
food_cap = floor(data.i.e / (g.R1(soldierType) * multiplier))
pop_cap  = floor((data.i.r - data.i.q) / g.S1(soldierType))
可招数量 = max(0, min(coin_cap, food_cap, pop_cap))
multiplier = 1 when mode/second_arg == 0, otherwise 2
```

- 对重建服务端的影响：角色基础状态需保存并同步 `population_used/population_cap/resource_point_used/resource_point_cap/fief_cap/general_cap`；`data.i.s/t/u/v` 按 byte 或 byte 后存 int 的协议宽度编码；征兵接口需以服务端权威资源和剩余人口为准。
- 当前边界：人口上限、封地上限、将领上限、资源点上限的“生成公式”仍未完全恢复；下一步应沿玩家成长数值、官职/VIP/道具扩展和资源点占领响应继续追。

## 48. 玩家成长数值深追：声望阈值与上限生成边界

- 已对玩家成长数值入口做第一轮 DEX 静态扫描，重点验证君主等级、声望阈值、封地/将领/资源点上限是否存在客户端本地完整公式。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/player_growth/growth_numeric_deep/growth_numeric_status_report.md`
- 结构化数据：
  - `growth_numeric_field_status.csv`：等级/声望阈值/封地/将领/资源点上限字段状态表。
  - `growth_numeric_status_summary.json`：玩家成长数值深追状态 JSON 汇总。
  - `growth_numeric_candidate_methods.csv/json`：候选字符串和字段引用方法扫描。
  - `growth_numeric_candidate_disasm_summary.json` 与 `method_disasm/`：关键候选方法反汇编证据。
- 当前确认：
  - `data.i.c` = 君主等级；`q0.H` 绘制等级数字，`q0.V` 在 `c < 99` 时显示升级剩余声望，否则显示“满级”。
  - `data.i.i` = 当前声望；`data.i.j` = 当前等级声望下限/上一级阈值；`data.i.k` = 下一级声望阈值。
  - `q0.H` 声望进度条公式：`progress_width = bar_width * max(i-j,0) / (k-j)`，若 `k-j==0` 则用 `k` 做兼容分母。
  - `q0.V` 的升级提示正常状态下等价于：`remaining = data.i.k - data.i.i`，显示文案 `还需${声望数}声望升级`。
  - `k.s1` 的开辟封地入口只判断 `Lo/a.s2().length < data.i.s`；达到上限时显示 `re_开辟数量`，数量直接来自 `data.i.s`。
- 负向发现：
  - 未在客户端静态扫描中发现完整 `君主等级 -> 声望阈值` 表，阈值由 `data.i.j/k` 从服务端同步。
  - 未发现 `等级/声望/官职 -> 封地上限 data.i.s` 的本地生成公式；客户端只消费服务端同步值。
  - 未发现 `将领上限 data.i.t`、`资源点上限 data.i.v` 的本地生成公式；当前主要是显示和门槛消费字段。
  - 官职自动轮选的服务端排序、名额和衰减公式仍未恢复，当前仍以文本规则和 UI 字段证据为主。
- 对重建服务端的影响：初版服务端应把 `level/current_prestige/level_prestige_floor/next_level_prestige/fief_cap/general_cap/resource_point_cap` 做成服务端权威配置/计算字段，并通过登录同步、资源同步、升级响应和 tagged update 下发；若追求高还原，需要动态采集不同等级账号的 `c/i/j/k/s/t/u/v` 样本拟合阈值表。

## 49. 账号积分与玉石入口深追第一版

- 已把 `data.g.H/resource_id=-14` 的账号积分入口与 `item_id=399` 玉石入口做第一版分流整理。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/account_points_jade_deep/account_points_jade_deep_report.md`
- 结构化数据：
  - `account_points_jade_entry_mapping.csv`：账号积分/玉石来源、消耗入口、协议、证据和服务端重建建议。
  - `account_points_jade_summary.json`：账号积分与玉石入口深追 JSON 汇总。
  - `account_points_jade_candidate_methods.csv/json`：`账号积分`、`玉石`、`item_id=399`、`resource_id=-14` 候选方法扫描。
  - `account_points_jade_disasm_summary.json` 与 `method_disasm/`：关键候选方法反汇编。
- 当前确认：
  - `账号积分 = resource_id -14 = data.g.H`，走资源余额模型；`玉石 = item_id 399`，走背包道具模型。二者不能混用。
  - 账号积分已确认同步链：`data.i.b` 登录/资源同步、`m0.u` 奖励领取成功同步、`a0.c2` 六部/部门响应同步。
  - `Lo/a.w5()` 的 `consumptionExpend_awardList` 会把活动奖励数量包装成 `resource_id=-14`，因此累计消费/活动奖励可配置账号积分奖励候选。
  - 玉石道具表确认：`item_id=399`，描述明确用于科技升级、将领空位激活、装备炼魂、六部系统、帅府系统等。
  - 玉石固定礼包来源已确认：年货 `442` 给玉石*6，礼盒 `445` 给玉石*66，糖果/粽子/西瓜/饺子 `739..742` 给玉石*10。
- 玉石消耗/使用入口第一版：
  - 科技升级：`q.A/q.L1/q.W1`，`techResearch`，opcode `4671 / 0x123F`；UI 显示 `di_需要玉石` 与 `re_提示升级玉石消耗`。
  - 六部/部门升级：`La0/a.H`，`ReqInternalLevelUp`，opcode `25346 / 0x6302`；请求写 `department_id byte + payment_mode byte`，UI 显示玉石/黄金二选一。
  - 装备炼魂：`scriptPages/data/g.N4`，`REQ_GENERAL_EQUIP_LIANHUN`，opcode `25216 / 0x6280`；请求写 `general_id/equip_id/mode/lock_count/lock_flags`，高级/锁定消耗由服务端判定。
  - 帅府帅位解锁：`Lv/a.b1`，`REQ_SHUAIFU_ADD_SHUAI_MAX`，opcode `25606 / 0x6406`；UI 按钮 `使用玉石/使用黄金`，发送支付模式 byte 候选。
  - 文官刷新/恢复健康：`gameHD/k.V`、`a0.t0` 读取或展示 `item_id=399` 数量/价格，是玉石消耗候选，最终发送入口待继续。
  - 战法残页兑换：`q0.O` 出现 `di_玉石兑换`、`di_使用玉石兑换残页`，最终发送入口待继续。
- 对重建服务端的影响：服务端需分开保存 `account_points` 与 `jade_item`；所有玉石消耗都应由服务端权威校验并同步背包/资源；奖励配置表应支持 `resource_id=-14` 发放账号积分和 `item_id=399` 发放玉石。
- 当前边界：部门升级 `payment_mode 1/2` 与玉石/黄金的精确映射、科技升级 `q.W1` 后几个 byte 语义、文官刷新/恢复健康和残页兑换发送入口、玉石扣减后的背包同步字段仍需动态样本或继续追状态机。

## 50. 玉石消耗响应与背包同步第一版

- 已把玉石消耗相关入口的响应 handler、资产同步方式和服务端回包边界整理成第一版。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/resource_system/jade_response_sync_deep/jade_response_sync_report.md`
- 结构化数据：
  - `jade_response_sync_mapping.csv`：请求 opcode、响应 opcode、handler、同步特征和服务端重建建议表。
  - `jade_response_sync_summary.json`：玉石响应同步 JSON 汇总。
  - `jade_response_candidate_methods.csv/json`、`jade_response_disasm_summary.json` 与 `method_disasm/`：候选方法和关键反汇编证据。
- 当前确认：
  - `玉石` 仍为 `item_id=399` 道具；`data.g.H/resource_id=-14` 是账号积分，二者必须分开建模。
  - 科技升级 `techResearch 0x123F -> 0x823F -> q.Y1` 读 `status/message` 后调用 `data.g.m0` 同步科技单项状态；本方法内未见 `Lo/a.V5` 或 `data.g.f`。
  - 科技取消 `0x1244 -> 0x8244 -> q.X1` 成功分支调用 `Lo/a.V5`，再同步 `data.i.d` 铜钱、`data.i.e` 粮食，并调用 `data.g.m0`。
  - 装备炼魂 `REQ_GENERAL_EQUIP_LIANHUN 0x6280 -> 0xE280 -> data.g.r4` 会更新装备/炼魂文本并调用 `Lo/a.V5`，末尾还有可选 `Lo/a.a6` 扩展同步。
  - 六部/部门升级 `ReqInternalLevelUp 0x6302 -> 0xE302 -> a0/a.s` 成功时同步部门等级/冷却；只有特定部门分支会调用 `Lo/a.V5`。
  - 帅府帅位解锁 `REQ_SHUAIFU_ADD_SHUAI_MAX 0x6406 -> 0xE406 -> v/a.e` 明确同步 `data.g.F` 黄金，并调用 `data.g.f` 完整道具/背包列表。
  - `Lo/a.V5` 是复合同步块，开头为 `data.g.F` 黄金、`data.g.G` 白银和若干资源/装备/封地结构；不能简单称为背包同步。
  - `data.g.f` 才是明确道具列表同步块：`readInt count` 后每项 `readLong unique_id + readShort item_id + readBoolean flag`。
- 对重建服务端的影响：所有玉石消耗接口都要服务端权威校验并按 handler 返回匹配的同步块；帅府类可直接刷新 `data.g.f`，炼魂/科技取消类要返回 `Lo/a.V5`，科技升级当前至少要返回科技状态，玉石扣减刷新链需动态样本进一步确认。
- 当前边界：`payment_mode` 精确枚举、科技升级成功后的玉石刷新方式、文官刷新/恢复健康和战法残页兑换最终入口、`Lo/a.V5` 复合同步块细字段仍需继续。

## 51. 任务/活动系统第一版

- 已对任务、活动、六部任务、签到/活跃度和新手玩法说明做第一版整理。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/task_activity_system/task_activity_system_first_report.md`
- 结构化数据：
  - `task_activity_protocol_mapping.csv`：任务/活动关键请求、响应、handler 与同步特征表。
  - `task_activity_string_refs.md/json`：任务/活动相关 DEX 字符串引用。
  - `task_activity_method_refs.md/json`：任务/活动候选方法引用汇总。
  - `task_activity_disasm_summary.md/json` 与 `method_disasm/`：关键方法反汇编证据。
  - `freshman_script_strings.md/csv/json`：`scriptFreshman.sc` 新手/玩法说明字符串抽取。
- 当前确认：
  - 未发现完整本地“任务 ID -> 完成条件 -> 奖励”总表；任务/活动大概率由服务端动态下发，客户端负责展示、点击领取、委派和同步奖励。
  - 普通活动任务点击/领取入口 `reqActivityTask` 请求 opcode `0x1136 / 4406`，请求体只写 `long task/activity id`；响应 `0x8136 / -32458 -> m0.y(String)` 先读 `status`，失败/非零进入 `m0.n` 子块处理。
  - 六部任务委派 `Req_libutaskDispatch` 请求 opcode `0x6342 / 25410`，请求体为 `int task_id + byte general_count + long general_id[]`；响应 `0xE342 / -7358 -> a0/a.C(String)` 更新任务/将领委派状态。
  - 六部任务领奖 `Req_libutaskAward` 请求 opcode `0x6343 / 25411`，请求体为 `int task_id`；响应 `0xE343 / -7357 -> a0/a.B(String)` 成功后调用 `Lo/a.V5` 复合同步资产。
  - 签到补签 `buqian` 请求 opcode `0x6204 / 25092`，请求体为 `short day + byte flag/payment`；响应 `0xE204 / -7676 -> gameHD/a.j(String)` 成功后刷新日历/活动数据。
  - 活跃/累计签到奖励 `leijijiangli` 请求 opcode `0x6206 / 25094`，响应 `0xE206 / -7674 -> gameHD/a.i(String)`；UI 字段包含个人活跃度、周活跃分、月活跃分、活跃奖励、累计签到。
  - `scriptFreshman.sc` 文件头 `0x0044` 为 68 个条目候选，已抽取 59 条可读字符串；它更像新手/玩法说明，不是任务奖励配置表。
- 对重建服务端的影响：任务系统初版应做成服务端动态配置模型；六部任务、签到/活跃度和普通活动任务应分模块实现，所有领奖都由服务端权威检查并按协议返回资产同步块。
- 当前边界：普通任务详情响应 `m0.n`、活动列表/主数据 `reqActivityHD`、六部任务列表 `a0/a.i/a0/a.j` 的具体字段仍需继续深拆；活动模板的完成条件/奖励多为服务端下发，客户端未见完整静态表。

## 52. 普通任务详情/领取响应字段第一版

- 已把普通任务列表、任务详情、领奖请求和领奖响应串成第一版字段闭环。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/task_activity_system/task_detail_deep/task_detail_deep_report.md`
- 结构化数据：
  - `task_detail_field_mapping.csv`：任务列表/详情/领奖字段映射表。
  - `task_detail_summary.json`：任务详情字段 JSON 汇总。
  - `task_detail_methods_summary.md/json` 与 `method_disasm/`：关键方法反汇编证据。
- 当前确认：
  - 任务列表请求 `m0.r()` 发送 opcode `0x1130 / 4400`，body 为单 byte `0`；响应 `0x8130 / -32464 -> m0.s -> m0.n`。
  - 单任务详情请求 `m0.v(group, task_id)` 使用 `reqTaskInfo`，opcode `0x1132 / 4402`，请求体为 `byte group_index + long task_id`；响应 `0x8132 / -32462 -> m0.w`。
  - 任务领奖请求 `m0.t(task_id,input)` 使用 `reqGainAward`，opcode `0x1134 / 4404`，请求体为 `long task_id + byte has_input + optional UTF input`；响应 `0x8134 / -32460 -> m0.u`。
  - 任务列表按 4 个 group 下发；每个 group 先读两个数量桶 `primary_count/secondary_count`。第一桶条目设置 `m0.p0/q0.U7=1`，第二桶默认为 0；`q0.U7==1` 时新 UI 显示 `lingquAward/getAwordBtn`。
  - 列表基础字段为：`m0.m0/q0.S7=task_id`、`m0.n0/q0.T7=任务标题`、`m0.o0=旧弹窗可领奖/按钮布尔候选`、`m0.p0/q0.U7=新列表状态`。
  - 详情字段为：`m0.r0/q0.W7=任务描述`、`m0.q0/q0.V7=任务目标/条件文本数组`、`m0.s0/q0.X7=任务指引`。
  - `group==0` 的奖励走结构化数组 `m0.t0/q0.Y7`，每条为 `reward_id + amount`；`group==1/2/3` 的奖励走文本字段 `m0.u0/q0.Z7`。
  - 结构化奖励的数量宽度由 `reward_id` 决定：`reward_id<=-1000` 读 `short amount`，`-999<reward_id<0` 读 `int amount`，`reward_id>=0` 读 `short amount`。
  - 领奖响应 `m0.u` 会先调用 `m0.n(dis)` 刷新任务列表；成功时继续同步 `data.i.C(byte)`、`data.i.i` 声望、`data.i.d` 铜钱、`data.i.e` 粮食、`data.g.H` 账号积分，并调用 `Lo/a.V5` 复合资产同步块。
- 对重建服务端的影响：普通任务系统初版可以做成服务端动态配置模型；必须实现 `0x1130` 列表、`0x1132` 详情、`0x1134` 领奖三条链。领奖必须服务端权威校验任务状态、已领状态、可选输入码、奖励发放和幂等/重放，并返回列表刷新和资产同步。
- 当前边界：4 个 group 的中文业务名、`m0.o0` 与 `m0.p0/U7` 精确分工、`readShort` 尾字段、`reward_id<=-1000` 是否专指装备仍需动态样本确认。

## 53. 六部任务列表字段深拆第一版

- 已把六部任务的初始信息、列表刷新、委派、领奖四条链路，以及任务列表内部字段拆成第一版。
- 输出报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/task_activity_system/libu_task_deep/libu_task_report.md`
- 结构化数据：
  - `libu_task_protocol_mapping.csv`：六部任务请求/响应 opcode、handler、请求体和同步特征。
  - `libu_task_field_mapping.csv`：列表 header、单任务字段、奖励字段、状态字段、委派/领奖响应字段映射。
  - `libu_task_summary.json`：六部任务字段 JSON 汇总。
  - `libu_task_methods_summary.md/json` 与 `method_disasm/`：`La0/a` 关键方法和全类反汇编证据。
- 当前确认：
  - 初始信息请求 `REQ_LIBUTASK_INFO` 使用 opcode `0x6340 / 25408`，响应 `0xE340 / -7360 -> La0/a.E -> i(dis,0)`；请求体为空。
  - 列表刷新请求 `Req_libutaskList` 使用 opcode `0x6341 / 25409`，响应 `0xE341 / -7359 -> La0/a.D -> i(dis,1)`；请求体为空。
  - 委派请求 `Req_libutaskDispatch` 使用 opcode `0x6342 / 25410`，请求体为 `writeInt task_id + writeByte general_count + repeat writeLong general_id`；响应 `0xE342 / -7358 -> La0/a.C`。
  - 领奖请求 `Req_libutaskAward` 使用 opcode `0x6343 / 25411`，请求体为 `writeInt task_id`；响应 `0xE343 / -7357 -> La0/a.B`。
  - `i(dis,mode)` 先读共享 header：`Lo/a.m` 六部俸禄余额、`og/pg/qg/rg/tg/sg/ug` 状态/时间字段候选，然后进入 `j(dis,mode)`。
  - `j(dis,mode)` 先读 `task_count`，每条读 `task_id` 后进入 `h(task_id,index,dis)`；`mode==0` 末尾额外读取 `Ng/Og = general_id/bonus` 文官个体任务加成候选。
  - 单任务字段已确认第一版：`vg=task_id`、`zg=标题`、`xg=等级`、`Bg=品阶`、`wg->Cg=类型候选`、`Kg=地形`、`Lg=目标`、`Mg[]=状态/条件标签`、`Jg/Wf=可委派文官上限`、`Ag=任务状态`、`Hg=剩余秒/完成时间`、`Ig-ug=任务耗时候选`、`Gg=六部经验奖励`、`Fg=六部俸禄奖励`、`Dg/Eg=额外奖励 ID/数量`、`yg=成功率百分比`。
  - `Ag` 状态第一版：`-1` 未委派/可查看，`0` 进行中，`1` 可领奖/已完成候选；`F()` 只有 `Ag==1` 分支会发送 `Req_libutaskAward`。
  - 领奖响应成功后会刷新任务列表和文官详情，清除 `Lo/a.F == task_id` 的委派标记，调用 `Lo/a.V5(dis)` 复合资产同步，并读 `Lo/a.m` 刷新六部俸禄余额。
- 对重建服务端的影响：六部任务应按服务端动态任务实例实现；`0x6340/0x6341` 下发完整任务字段，`0x6342` 由服务端校验文官、计算状态/倒计时/成功率，`0x6343` 由服务端权威校验完成/已领/奖励幂等并返回列表刷新、文官刷新、资产同步和俸禄余额。
- 当前边界：`og/pg/qg/rg/tg/sg/ug` 的精确业务名、`Ig` 与 `ug` 的绝对/相对时间语义、`wg/Kg/Lg/Mg` 对应标签表全集、`Ag==1` 与成功/失败结果关系仍需动态样本或继续追静态表。

