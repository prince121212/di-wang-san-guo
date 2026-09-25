# 战斗核心公式/蓄力/坐标状态汇总

- 日期：2026-07-05

## 核心结论

客户端战斗模块主要是服务端指令流回放器；基础伤害/胜负/奖励公式未在回放路径闭环。攻速 C0、蓄力暂停/恢复、坐标坑位属于客户端表现层，已有高置信恢复。

## 状态表

|主题|状态|置信度|已确认|未确认|服务端重建建议|
|---|---|---|---|---|---|
|基础伤害公式|未在客户端回放路径恢复|高|普通攻击 command type 6 携带目标攻击后剩余值；战法 command type 11 携带 before/after；客户端用旧值-新值显示损兵。|攻击、防御、生命、兵数、科技、装备、称号等如何合成基础伤害。|服务端需要自建权威伤害公式或用大量样本拟合；客户端不能直接给出完整公式。|
|普通攻击损兵|回放落地机制已确认|高|type 6 读取 targetId、targetArg、old/flag、newRemainOrWallValue；f0 中用旧部队兵数/城墙值与新值差额表现损兵并更新状态。|服务端生成 newRemain 的公式。|服务端下发指令流时可直接提供攻击后剩余兵数，客户端即可正确回放。|
|战法/技能损兵|回放落地机制已确认|高|type 11 读取 source/target、skill/btId、beforeValue、afterValue；p0 用 before-after 显示损兵/效果。|战法附加伤害、BUFF 触发概率、目标筛选公式的服务端最终实现。|可先按战法文本表实现近似逻辑，再以 before/after 指令流驱动客户端。|
|攻速→蓄力上限 C0|回放侧已确认，属性换算公式未确认|高|C0[S] 是攻击间隔/蓄力上限，单位 ms；新协议 command type 1 直接 readShort(attackIntervalMs)，经 s.j -> s.f0 -> s.h 写入 C0。|兵种/武将攻速属性如何换算为 attackIntervalMs。旧协议仅有 4000/5000/7000ms 兼容规则。|服务端重建可以直接按兵种/武将给出 attackIntervalMs；若缺公式，先用兵种表/样本拟合。|
|蓄力暂停/恢复/增减|客户端表现机制已确认|高|F0 为蓄力开始时间，E0 为暂停时剩余时间，D0 为蓄力增减偏移累计；p0 中 buff 可暂停/恢复并直接修改 C0/D0。|所有战法 buff 对 C0/D0/E0 的完整映射仍需逐条对齐。|服务端可在指令流中下发 C0 或蓄力增减结果，客户端按结果播放。|
|战场坐标/坑位|表现层公式已确认|高|战场坐标为 2D 像素；B/I 计算 X，C/J 计算 Y；阵营镜像，lane/col 控制排/列，阵型偏移 G 来自 H[formation]。移动每 tick 以最多 20 像素逼近目标。|“目标身后/前后左右”在服务端目标选择中的逻辑仍需结合战法选择规则确认；客户端坐标只负责表现。|若下发 lane/col，客户端能自己算显示坐标；服务端目标选择需另实现。|
|战斗结束/胜负|结果由指令流/战报给出|高|command type 7 是战斗结束标记；战报 reqCheckMsg 展示胜负和奖励。|胜负判定和奖励生成公式。|服务端应权威结算胜负、损失和奖励，并写入战报/资源状态。|

## 关键文件

- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_core_formula_coordinate_findings.md`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_deep/battle_command_structure_report.md`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_deep/battle_command_structure.csv`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_dex/method_disasm/scriptPages_game_s__Z__0x338bd8.smali.txt`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_dex/method_disasm/scriptPages_game_s__f0__0x33aa44.smali.txt`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_dex/method_disasm/scriptPages_game_s__p0__0x32eb2c.smali.txt`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_dex/method_disasm/scriptPages_game_s__B__0x330c44.smali.txt`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/battle_dex/method_disasm/scriptPages_game_s__I__0x330de4.smali.txt`