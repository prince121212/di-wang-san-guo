# 协议发送入口第一版梳理

生成时间：2026-07-05T07:04:02

## 1. 结论摘要

- 已对 DEX 中 `LscriptPages/game/g;->y(String,String,S)` 发送入口做一轮静态扫描，共提取到 **40** 个发送调用点。
- 可直接恢复常量请求名/opcode 的模块包括：称号/成就、城市/国家、封地、招兵/配兵、将领、道具、奖励、战斗/部队、聊天/邮件设置、寻宝/巡游等。
- 这张表是后续重建服务端路由表的第一版索引；字段级协议还需要逐个方法按 `BaseIO.write*` 顺序展开。

## 2. 分类统计

| 分类 | 数量 |
|---|---:|
| 其他/未知 | 7 |
| 国家 | 5 |
| 城池/城市 | 11 |
| 封地 | 2 |
| 将领/角色 | 1 |
| 战斗/部队 | 3 |
| 战法 | 1 |
| 招兵/配兵 | 1 |
| 探索/侦察 | 2 |
| 称号/成就 | 2 |
| 聊天设置 | 1 |
| 道具/奖励 | 3 |
| 邮件 | 1 |

## 3. 已恢复的关键发送入口

| 分类 | opcode | 请求名 | 方法 | 说明 |
|---|---:|---|---|---|
| 其他/未知 | `0x6221` | `(常量名未恢复)` | `LscriptPages/gameHD/m;->t(S)V` | code_off `0x45858c` invoke `000032` |
| 其他/未知 | `0x6222` | `(常量名未恢复)` | `LscriptPages/gameHD/m;->v(S I)V` | code_off `0x459518` invoke `00023e` |
| 其他/未知 | `0x6223` | `(常量名未恢复)` | `LscriptPages/gameHD/m;->x(S)V` | code_off `0x459844` invoke `000040` |
| 战斗/部队 | `0x1280` | `ChangeTeamNEW` | `LscriptPages/gameHD/g;->q()V` | code_off `0x430a14` invoke `000074` |
| 其他/未知 | `0x6421` | `REQ_CAPTUREFLAG_UPDATEINFO` | `Lv/a;->T0()I` | code_off `0x45e2bc` invoke `000558` |
| 城池/城市 | `0x1335` | `REQ_CITY_TOTEM_CTRL` | `LscriptPages/game/k;->Z0(J I S I)V` | code_off `0x2cadd8` invoke `00002c` |
| 国家 | `0x6282` | `REQ_COUNTRY_LIVELIHOOD_INFO` | `LscriptPages/game/n;->y0()V` | code_off `0x2e834c` invoke `0001f8` |
| 战法 | `0x640c` | `REQ_SHUAIFU_CONVERT_ZHANFA_BOOK` | `LscriptPages/game/q0;->m1(I [S)V` | code_off `0x400810` invoke `00004e` |
| 探索/侦察 | `0x627a` | `REQ_XUNBAO_INFO` | `LscriptPages/data/g;->J2(I I [S)V` | code_off `0x2812e8` invoke `000074` |
| 战斗/部队 | `0x640d` | `ReqChallengeTaskAward` | `LscriptPages/data/g;->Q2()V` | code_off `0x281bb8` invoke `000134` |
| 其他/未知 | `0x6342` | `Req_libutaskDispatch` | `La0/a;->F()I` | code_off `0xc14f0` invoke `000d62` |
| 其他/未知 | `0x1008` | `cacheData` | `LscriptPages/game/s0;->d0()V` | code_off `0x411a98` invoke `000f0e` |
| 封地 | `0x1212` | `fiefMove` | `LscriptPages/game/q;->T(J I I J Ljava/lang/String;)V` | code_off `0x322808` invoke `00003a` |
| 称号/成就 | `0x1180` | `reqAchievementList` | `LscriptPages/game/i0;->o(B J Ljava/lang/String;)V` | code_off `0x3b66f8` invoke `000046` |
| 其他/未知 | `0x118a` | `reqActivationUseGold` | `LscriptPages/game/i0;->q([J)V` | code_off `0x3b6780` invoke `000030` |
| 招兵/配兵 | `0x1229` | `reqBathAddArmy` | `LscriptPages/game/p;->L0([J)V` | code_off `0x30ca8c` invoke `000030` |
| 聊天设置 | `0x6287` | `reqChatSet` | `LscriptPages/game/i;->w(I [B I B)V` | code_off `0x2b4588` invoke `000058` |
| 城池/城市 | `0x131b` | `reqCityConnectCities` | `LscriptPages/game/k;->w0(J Ljava/lang/String;)V` | code_off `0x2c8de4` invoke `000030` |
| 城池/城市 | `0x1334` | `reqCityCountryCollect` | `LscriptPages/game/k;->s1()I` | code_off `0x2b52ac` invoke `000e7e` |
| 城池/城市 | `0x1332` | `reqCityCountryCollectInfo` | `LscriptPages/game/k;->y0(J Ljava/lang/String;)V` | code_off `0x2c9248` invoke `000030` |
| 城池/城市 | `0x1320` | `reqCityFiefExpel` | `LscriptPages/game/k;->B0(J Ljava/lang/String; [J)V` | code_off `0x2c9480` invoke `00004e` |
| 城池/城市 | `0x1340` | `reqCityOwnerCampaignInfo` | `LscriptPages/game/k;->P0(J Ljava/lang/String;)V` | code_off `0x2ca344` invoke `000030` |
| 城池/城市 | `0x1344` | `reqCityOwnerCampaignRoleList` | `LscriptPages/game/k;->R0(J Ljava/lang/String;)V` | code_off `0x2ca3bc` invoke `000030` |
| 城池/城市 | `0x1342` | `reqCityOwnerRoleCampaignInfo` | `LscriptPages/game/k;->T0(J Ljava/lang/String; J Ljava/lang/String;)V` | code_off `0x2ca92c` invoke `00004e` |
| 城池/城市 | `0x1324` | `reqCityTraitLevelUp` | `LscriptPages/game/k0;->c0()I` | code_off `0x3bdd2c` invoke `000ce2` |
| 城池/城市 | `0x132d` | `reqCityYield` | `LscriptPages/game/k;->e1(J Ljava/lang/String; J Ljava/lang/String;)V` | code_off `0x2cb168` invoke `00004e` |
| 国家 | `0x2001` | `reqCountryAssignResource` | `LscriptPages/game/n;->T0([Ljava/lang/String; I [J)V` | code_off `0x2ea0dc` invoke `00003e` |
| 国家 | `0x2002` | `reqCountryAssignResourceTip` | `LscriptPages/game/n;->V0(I [Ljava/lang/String;)V` | code_off `0x2ea22c` invoke `000030` |
| 国家 | `0x1418` | `reqCountryReqJoinCtrl` | `LscriptPages/game/n;->B1(I J Ljava/lang/String;)V` | code_off `0x2eb8e8` invoke `000038` |
| 国家 | `0x1442` | `reqCreateCountry` | `LscriptPages/game/n;->f2(J Ljava/lang/String;)V` | code_off `0x2ecde8` invoke `000030` |
| 探索/侦察 | `0x152d` | `reqDetectConsume` | `LscriptPages/game/p;->R0(J I J Ljava/lang/String;)V` | code_off `0x30cf98` invoke `00004e` |
| 战斗/部队 | `0x1012` | `reqFightingCity` | `LscriptPages/game/s0;->Z()V` | code_off `0x410988` invoke `000e1c` |
| 道具/奖励 | `0x1134` | `reqGainAward` | `LscriptPages/game/m0;->t(J Ljava/lang/String;)V` | code_off `0x3d263c` invoke `000036` |
| 邮件 | `0x6289` | `reqMailSet` | `LscriptPages/data/g;->O3(I I I)V` | code_off `0x28668c` invoke `00003a` |
| 称号/成就 | `0x1186` | `reqNicknameList` | `LscriptPages/game/i0;->r(J Ljava/lang/String;)V` | code_off `0x3b67c8` invoke `000040` |
| 封地 | `0x1310` | `reqRoleFiefList` | `LscriptPages/game/p;->g0(I I)V` | code_off `0x309800` invoke `0000e8` |
| 将领/角色 | `0x1120` | `reqRoleInfo` | `LscriptPages/game/w;->d0(J Ljava/lang/String;)V` | code_off `0x349ed0` invoke `000036` |
| 道具/奖励 | `0x3144` | `reqUseItem` | `La0/a;->M1(I I)V` | code_off `0xe5148` invoke `000030` |
| 道具/奖励 | `0x1144` | `reqUseItem` | `LscriptPages/game/k0;->Z(I S)V` | code_off `0x3ccfdc` invoke `00002e` |
| 城池/城市 | `0x6444` | `reqXunyouCity` | `LscriptPages/game/s0;->Z()V` | code_off `0x410988` invoke `001044` |

## 4. 对基础规则/服务端重建的价值

- 路由层：可以先按请求名/opcode 建立服务端 handler 表，优先支持登录后会被客户端主动调用的只读/同步接口。
- 字段层：每个发送方法的 descriptor 与 `BaseIO.write*` 顺序就是请求体格式入口。例如 `ReqChallengeTaskAward/0x640D` 已展开为两方阵容字段。
- 机制层：请求名显示基础机制模块至少包括：封地迁移、将领封地列表、批量加兵、城池民生/征收/驱逐/城主竞选、国家创建/加入/资源分配、道具使用、任务领奖、战斗/部队、称号/成就、邮件/聊天设置、探索/寻宝。

## 5. 边界与下一步

- 当前脚本只是一轮常量传播扫描，部分调用点请求名由参数传入，显示为空；这些需要针对方法参数继续追上游。
- 下一步建议按“服务端最小可玩闭环”优先展开字段：`reqRoleInfo` → `reqRoleFiefList` → 建筑/资源同步 → `reqBathAddArmy` → `fiefMove`/`reqFightingCity` → 战斗结算/奖励。

## 6. 产物

- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/network_send_calls.csv`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/network_send_calls_classified.csv`
- `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/network_send_calls.json`
