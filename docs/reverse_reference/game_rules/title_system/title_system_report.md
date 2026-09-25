# 称号/成就系统规则与协议线索报告

生成时间：2026-07-05T06:42:20

## 1. 本轮产物

- `title_sentence_hits.csv`：称号/成就相关 sentence 文本命中 44 条。
- `title_faq_hits.csv`：FAQ 称号/成就问答命中 1 条。
- `title_help_hits.csv`：二进制帮助脚本称号/成就文本命中 80 条。
- `title_box_mapping.csv`：称号相关道具/称号宝箱 47 条。
- `title_protocol_methods.csv`：DEX 反汇编确认的请求/响应读写结构 12 条。
- `title_capture_hits.csv`：抓包中称号/成就 opcode 或字符串命中 1621 条。

## 2. 已确认规则

- sentence#2057 `di_提示隐藏成就说明`：隐藏成就,能使自己在被其他玩家查看时,隐藏个人成就和称号的详细信息.您确定要隐藏吗?
- sentence#2058 `di_提示展示成就说明`：展示成就,能使自己在被其他玩家查看时,展示个人成就和称号的详细信息.您确定要展示吗?
- sentence#2061 `di_提示称号规则说明`：1.同一时间只能激活一个称号，每200秒可以切换一次称号； / 2.“集”类称号为特殊称号，达成成就条件即享有属性加成（无需激活），属性效果可与其他称号效果叠加； / 3.状态类称号在不满足成就条件时会自动失效，如神工、枭雄、无双、寨主等。
- sentence#3095 `di_无需激活称号提示`：当前称号无需激活即可获得称号效果
- sentence#3456 `re_修筑城墙贡献值上限提示`：修筑城墙每日获得贡献值有上限，超过上限后可继续修墙增加城墙值且不影响铜墙铁壁成就数值统计。 / 今日剩余可获得贡献值:${limitUp}
- sentence#3457 `re_修筑道路贡献值上限提示`：修筑道路每日获得贡献值有上限，超过上限后可继续修路增加道路值且不影响四通八达成就数值统计。 / 今日剩余可获得贡献值:${limitUp}

FAQ 补充：

- FAQ#50：使用寨主称号攻城不加战功？ → 寨主称号：灭敌时获得的战功增加10%，增加的是击败玩家兵力的获得的战功，并不增加攻打城池获得的固定战功.

帮助脚本补充：

- `scriptBanyou.sc`@0x3ce：R您需要更深层的发展,才能使军队实力更上一层楼:<br/>调整兵种组合,让军队更好的发挥战斗力.<br/>获取更多更强的将领,以提升军队的战斗力.<br/>强化装备,以提升将领的能力.<br/>升级科技,提升各个兵种的战斗力.<br/>达成成就,获取高级称号,增强军队的战斗力.
- `scriptBanyou.sc`@0x550：(您现在的成就已经可以进行一些富有有挑战性的战争咯:抢占资源、夺取封地和攻占城池;只有经过这些战争的洗礼,才能成为真正的王者哦.<br/>小蝉要提醒您:这些战争是残酷的,胜败无常,损兵折将更是家常便饭,您做好准备了吗?
- `scriptBanyou.sc`@0x1830：,激活称号,能获得特殊的增益状态.
- `scriptBanyou.sc`@0x185f：您都拥有称号啦,快去激活他吧!<br/>称号带有一个特殊的状态,激活后您即可获取该状态;尤其是高级称号带来的状态能让您的实力大幅提升.
- `scriptFB.sc`@0x91ff：胜败乃兵家常事,请将军重整兵马再来挑战!<br/>获胜技巧:<br/>1.提升将领的等级,让将领的战斗力更强大<br/>2.招募能力更强大的将领<br/>3.取得成就,获得提升战斗能力的称号<br/>4.使用道具,提升军队的战斗能力
- `scriptFB.sc`@0x94a1：胜败乃兵家常事,请将军重整兵马再来挑战!<br/>获胜技巧:<br/>1.提升将领的等级,让将领的战斗力更强大<br/>2.招募能力更强大的将领<br/>3.取得成就,获得提升战斗能力的称号<br/>4.使用道具,提升军队的战斗能力
- `scriptFB.sc`@0x9721：胜败乃兵家常事,请将军重整兵马再来挑战!<br/>获胜技巧:<br/>1.提升将领的等级,让将领的战斗力更强大<br/>2.招募能力更强大的将领<br/>3.取得成就,获得提升战斗能力的称号<br/>4.使用道具,提升军队的战斗能力
- `scriptFB.sc`@0x99c6：胜败乃兵家常事,请将军重整兵马再来挑战!<br/>获胜技巧:<br/>1.提升将领的等级,让将领的战斗力更强大<br/>2.招募能力更强大的将领<br/>3.取得成就,获得提升战斗能力的称号<br/>4.使用道具,提升军队的战斗能力

## 3. 称号宝箱/道具映射

已从 `item_full_mapping.csv` 抽取称号相关道具 47 条。多数称号宝箱尾部存在 `01 10 00 <len> <ASCII数字...> 00 00 00` 模式，疑似“称号ID/称号编码”。

示例：

- item_id=544 `滑头称号宝箱` → title_name=`滑头`, tail_title_code=`0`
- item_id=545 `寨主称号宝箱` → title_name=`寨主`, tail_title_code=`1`
- item_id=546 `福星称号宝箱` → title_name=`福星`, tail_title_code=`2`
- item_id=547 `学士称号宝箱` → title_name=`学士`, tail_title_code=`3`
- item_id=548 `先锋称号宝箱` → title_name=`先锋`, tail_title_code=`5`
- item_id=549 `护军称号宝箱` → title_name=`护军`, tail_title_code=`6`
- item_id=550 `破军称号宝箱` → title_name=`破军`, tail_title_code=`7`
- item_id=551 `猛将称号宝箱` → title_name=`猛将`, tail_title_code=`8`
- item_id=552 `贪狼称号宝箱` → title_name=`贪狼`, tail_title_code=`9`
- item_id=553 `财主称号宝箱` → title_name=`财主`, tail_title_code=`10`
- item_id=554 `地主称号宝箱` → title_name=`地主`, tail_title_code=`11`
- item_id=555 `名士称号宝箱` → title_name=`名士`, tail_title_code=`12`
- item_id=556 `劳模称号宝箱` → title_name=`劳模`, tail_title_code=`13`
- item_id=557 `善人称号宝箱` → title_name=`善人`, tail_title_code=`14`
- item_id=558 `明君称号宝箱` → title_name=`明君`, tail_title_code=`15`
- item_id=559 `贤君称号宝箱` → title_name=`贤君`, tail_title_code=`16`
- item_id=560 `达人称号宝箱` → title_name=`达人`, tail_title_code=`17`
- item_id=561 `无双称号宝箱` → title_name=`无双`, tail_title_code=`18`
- item_id=562 `宗师称号宝箱` → title_name=`宗师`, tail_title_code=`19`
- item_id=563 `神工称号宝箱` → title_name=`神工`, tail_title_code=`20`

边界：这里能确认“道具打开后获得某称号”的客户端道具映射，但**不能单独证明称号的属性效果数值**；称号效果仍需从服务端称号配置响应或更深 DEX 数据结构获得。

## 4. 协议线索

关键请求方法：

- `0x1180 reqAchievementList`：LscriptPages/game/i0;->o(B,J,String)；writeByte(type); writeByte(hasName); writeLong(roleOrTargetId); writeUTF(nameOrEmpty)
- `0x1184 reqAchievementCont`：LscriptPages/game/i0;->n(B,J,S)；writeByte(type); writeLong(achievementId); writeShort(indexOrPage)
- `0x1186 reqNicknameList`：LscriptPages/game/i0;->r(J,String)；writeByte(hasName); writeLong(roleOrTargetId); writeUTF(nameOrEmpty)
- `0x1188 activationNickname`：LscriptPages/game/i0;->p(J)；helper Lk/a;->r(..., titleId, ..., 4488)
- `0x118a reqActivationUseGold`：LscriptPages/game/i0;->q([J)；writeByte(count); repeat writeLong(titleId)

关键响应解析：

- `i0.s(String)`：`count + (long id, byte type/status, UTF name) * count`
- `i0.t(String)`：`byte status + UTF message + boolean hiddenOrShown`
- `i0.u(String)`：成就/称号详情字段，读入多段 `long/UTF`，用于名称、描述、进度、奖励/效果候选。
- `i0.v(String)`：称号列表/拥有称号列表候选，多数组结构。
- `i0.w(String)`：激活/冷却结果；`status=-2` 时返回多个可用黄金立即激活/冷却项。
- `i0.y(String)`：`count + (long id, byte type/status, UTF name, short flag) * count`
- `i0.z(String)`：成就列表/详情配置：`boolean, short, long, UTF, short` 头部，随后每条 `long, byte, UTF, UTF, UTF, UTF, boolean, long, byte`。

## 5. 抓包覆盖情况

- 直接命中称号/成就 opcode：0 条。
- 仅字符串命中：1621 条。

解释：当前已有抓包主要覆盖商城、邮件、副本、礼包、山贼等流程，没有明确打开“君主→成就/称号”界面的操作，因此未捕获到 `0x1180/0x1184/0x1186/0x1188/0x118a` 这组称号协议的直接请求。字符串命中多来自任务/活动列表中的“国战无双、神工”等文本，不能当成称号协议响应。

## 6. 推断与置信度

- 高置信：称号同一时间只能激活一个；200 秒可切换；“集”类称号无需激活并可叠加；状态类称号不满足条件会失效。
- 高置信：寨主称号增加“击败玩家兵力产生的战功”10%，不增加攻城固定战功。
- 中高置信：称号宝箱 tail 中 ASCII 数字是称号编码/称号ID。
- 中置信：`i0.u/v/y/z` 响应结构中包含称号效果/成就奖励文本与进度字段，但字段语义还需要用真实称号响应动态校验。

## 7. 未完成

1. 具体每个称号的属性效果数值表尚未完整恢复。
2. 成就条件、成就点数、称号奖励与称号ID之间的全量服务端配置仍需动态抓 `0x1180/0x1184/0x1186` 响应或反查配置加载格式。
3. 称号激活/冷却的黄金消耗由服务端返回，客户端仅展示 `${数量}` 或解析 `i0.w` 中的 cost 字段。

## 8. sentence 示例命中

- sentence#448 `di_说明战功作用`：1、拥有战功就有机会获取国家官职，战功越高获取的职位越高。 / 2、战功是百团争霸、国战无双任务的排名标准之一。
- sentence#1090 `di_提示隐藏成就`：该玩家已隐藏其成就和称号的详细信息，无法查看。
- sentence#1779 `di_标题成就`：成就
- sentence#1780 `di_标题称号`：称号
- sentence#1922 `re_标题成就点数`：当前成就点数：${数值}点
- sentence#1929 `di_提示领取成就`：领取成就奖励中，请稍候…
- sentence#2024 `di_标题查看成就`：查看成就
- sentence#2026 `di_标题称号规则`：称号规则
- sentence#2027 `di_标题称号奖励`：称号奖励
- sentence#2029 `di_标题成就一览`：成就一览：
- sentence#2031 `di_标题当前称号`：当前称号:
- sentence#2032 `di_标题获得称号`：获得称号:
