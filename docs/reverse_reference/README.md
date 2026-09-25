# 逆向参考资料

从原版 APK 逆向和抓包分析中保留下来的字典、数据表与协议参考，供以后查对照用。
2026-09-25 从本地 `reverse_cases/`、`ctf_out/` 整理而来；反汇编、字符串命中、
候选方法列表、原始抓包等中间产物已删除。原版 APK 仍在项目根目录（不入库）。

| 目录 | 内容 |
|---|---|
| `game_rules/` | 游戏数据字典与规则表：物品/礼包映射（`item_mapping/`）、建筑/科技/技能/装备表（`tables/parsed/`）、兵种（`soldier_table/`）、副本关卡（`fb_tables/`）、战斗表（`battle_tables/`）、商城商品（`mall_goods/`）、山贼、称号、任务活动、资源字段映射、协议字段（`protocol_chain/`）和总规则手册（`collected_rulebook/MASTER_RULEBOOK.md`） |
| `client_understanding/` | 客户端对象字段字典、全局状态字段索引、协议信封与响应分发、装备/牢房等协议契约 |
| `raw_scripts/` | 原版 1.66 APK 解出的全部 `.sc` 脚本表及游戏文本（`sentence.txt`、`FAQ.txt`），是上面各字典的原始数据 |
| `protocol/` | 协议参考：`protocol_clues`、操作码分发表 `opcode_dispatch.tsv`、户部礼部协议规范、邮件协议、当乐与三国联盟协议对比、打矿加速/满忠/出征协议报告 |
| `protocol/helper_payloads/` | 从参考辅助 APK 解出的刷黄出征、闯关副本、日常请求载荷构造 |
| `single_apk/` | 单机简化版解出的兵种数值表 |
| `deep-reverse-report.md` | 1.66 APK 离线逆向总报告 |

电脑端运行时使用的 4 张规则表（物品映射、装备模板、科技等级、建筑费用）另有一份在
`电脑端辅助前端/assets/`；测试用的真实抓包回包在 `电脑端辅助前端/tests/fixtures/game_packets/`。

## 旧路径对照

其他文档里引用的旧路径可按下表找到对应文件；表中未列出的旧文件已随中间产物删除。

| 旧路径 | 现路径 |
|---|---|
| `reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/` | `game_rules/` |
| `reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/` | `client_understanding/` |
| `reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/all_scripts/assets/script/` | `raw_scripts/` |
| `reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/server_rebuild/protocol_clues.*` | `protocol/protocol_clues.*` |
| `reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/vuln_shop/mall_goods/mall_goods_table.*` | `game_rules/mall_goods/` |
| `reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/vuln_shop/mail_protocol_reverse/mail_protocol_findings.md` | `protocol/mail_protocol_findings.md` |
| `reverse_cases/apk/analysis/*_decode_2026-07-06/*_payload*_summary.md` | `protocol/helper_payloads/` |
| `ctf_out/opcode_dispatch.tsv`、`ctf_out/PROTOCOL_SPEC_户部礼部_20260914.md` | `protocol/` |
| `ctf_out/single_apk/unit_table.*` | `single_apk/` |
| `ctf_out/passive_pcap_hotspot_*/live_analyzed/*/resp.bin`（测试用到的） | `电脑端辅助前端/tests/fixtures/game_packets/` |
