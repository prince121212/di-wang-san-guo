# 规则表解析输出

来源：APK assets/script/*.sc 二进制规则表。

已生成：

- buildings.md / .csv / .json
- tech_summary.md 与 tech_levels.md
- tech_effects.md
- skills.md 与 skill_effects.md
- item_effects.md
- equip_effects.md 与 equip_types.md

字段说明：
- `效果值`、`触发率/数值`、`成本A/B/C`、`耗时秒` 是按二进制结构直接读出的数值；具体业务含义仍需结合客户端代码或运行表现复核。
- 建筑表中的 ID 7 在 count=9 中存在，但未发现命名记录，暂标为保留/空地/废弃建筑候选。
- item_effects 的 ID 41 附近存在非标准占位/异常编码，脚本做了 resync 并保留 note。
