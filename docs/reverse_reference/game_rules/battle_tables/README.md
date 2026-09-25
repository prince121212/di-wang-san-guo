# battle_tables 战斗/战法表解析

来源：assets/script/scriptBT*.sc、battle.rp。

- scriptBTBookPiece.sc: count=35，战法书残页/战法名称索引。
- scriptBTList.sc: header_count=35，本脚本按名称定位解析到 35 条战法/战斗技能记录。
- scriptBTEffect.sc: 解析到 25 条战斗 BUFF/状态效果。
- scriptBTBookProTable.sc: 解析到 4 条战法书残页概率说明。

说明：bt_list_summary 的“核心描述/公式样例”是从长记录中提取出的中文公式/说明文本；精确数值字段仍需继续对每条记录做结构反推。
