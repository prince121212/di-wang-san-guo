# 客户端响应分发清洗表（Lo/a.A6）

生成来源：`Lo/a;->A6(S,[B,String)Z`，静态抽取 `if-ne pType,const` 顶层分支。

## 1. 产物

- 清洗分发表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/response_dispatch_clean.csv`
- handler 直接读字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/handler_direct_read_sequences.csv`
- opcode 合同表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/response_handler_contracts.csv`

## 2. 统计

- 响应 opcode 候选：458
- 唯一 handler 候选：497
- 具备首个业务 handler 的分支：452

## 3. 核心响应路由摘录

| response | signed | first handler | req-0x7000 | req-0x8000 | branch reads | handler direct reads |
|---:|---:|---|---|---|---|---|
| `0x8001` | -32767 | `Lo/a;->V8(J)V` | 0x1001 v1, ""@scriptPages/game/a0->U | 0x0001 | `028e:readByte(Ljava/lang/String;)B \|\| 0294:readLong(Ljava/lang/String;)J` | `` |
| `0x8002` | -32766 | `game/a0;->J([B)V` | 0x1002 | 0x0002 | `` | `000a:readByte(Ljava/lang/String;)B` |
| `0x8003` | -32765 | `game/b0;->i1(Ljava/lang/String;)V` | 0x1003 loginBaseinfo@scriptPages/game/b0->P0 | 0x0003 | `` | `0006:readByte(Ljava/lang/String;)B \|\| 000e:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0016:readLong(Ljava/lang/String;)J \|\| 0...` |
| `0x8004` | -32764 | `game/a0;->S([B)V` | 0x1004 gameLogin@scriptPages/game/a0->Q; accountLogin@scriptPages/game/b0->C0; (unnamed)@scriptPages/game/b0->D0 | 0x0004 | `` | `000a:readByte(Ljava/lang/String;)B \|\| 0016:readByte(Ljava/lang/String;)B \|\| 0062:readLong(Ljava/lang/String;)J \|\| 00aa:readInt(Ljav...` |
| `0x8005` | -32763 | `game/a0;->B0(Ljava/lang/String;)V` | 0x1005 data@scriptPages/game/a0->d0 | 0x0005 | `` | `0000:readByte(Ljava/lang/String;)B` |
| `0x8006` | -32762 | `data/g;->G0()B` | 0x1006 data@scriptPages/game/a0->Q0 | 0x0006 | `` | `` |
| `0x8007` | -32761 | `game/b0;->N0(Ljava/lang/String;)V` | 0x1007 data@scriptPages/game/b0->M0 | 0x0007 | `` | `0006:readByte(Ljava/lang/String;)B \|\| 000e:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x8008` | -32760 | `game/s0;->y([B)V` | 0x1008 cacheData@scriptPages/game/s0->d0 | 0x0008 | `` | `` |
| `0x800a` | -32758 | `data/c;->j(Ljava/lang/String;)V` | 0x100a | 0x000a | `0312:readByte(Ljava/lang/String;)B \|\| 031a:readByte(Ljava/lang/String;)B` | `0000:readLong(Ljava/lang/String;)J \|\| 000c:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0018:readInt(Ljava/lang/String;)I \|\| 00...` |
| `0x800b` | -32757 | `game/n;->M0(Ljava/lang/String;)V` | 0x100b data@scriptPages/game/a0->G0; di_提示没有黄金@scriptPages/game/n->C2; reqChooseCountry@scriptPages/game/n->L2 | 0x000b | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0010:readLong(Ljava/lang/String;)J` |
| `0x800c` | -32756 | `game/n;->u2(Ljava/lang/String;)V` | 0x100c | 0x000c | `` | `000c:readByte(Ljava/lang/String;)B \|\| 001c:readInt(Ljava/lang/String;)I \|\| 0022:readLong(Ljava/lang/String;)J \|\| 0028:readLong(Ljav...` |
| `0x800d` | -32755 | `game/s0;->b([B)V` | 0x100d | 0x000d | `` | `` |
| `0x8010` | -32752 | `game/s0;->R(Ljava/lang/String;)V` | 0x1010 | 0x0010 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readInt(Ljava/lang/String;)I \|\| 0010:readInt(Ljava/lang/String;)I` |
| `0x8012` | -32750 | `game/s0;->S(Ljava/lang/String;)V` | 0x1012 reqFightingCity@scriptPages/game/s0->Z | 0x0012 | `` | `0000:readShort(Ljava/lang/String;)S \|\| 0036:readShort(Ljava/lang/String;)S \|\| 003e:readShort(Ljava/lang/String;)S \|\| 008c:readShort...` |
| `0x8014` | -32748 | `game/a0;->a0(Ljava/lang/String;)V` | 0x1014 | 0x0014 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0012:readByte(Ljava/lang/String;)B \|\| 0054:readLong(Ljava/lang/String;)J \|\| 0064:readUTF(Ljav...` |
| `0x8016` | -32746 | `game/a0;->s0(Ljava/lang/String;)V` | 0x1016 | 0x0016 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x8018` | -32744 | `game/p0;->E(Ljava/lang/String;)V` | 0x1018 | 0x0018 | `` | `0012:readByte(Ljava/lang/String;)B \|\| 0034:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x8020` | -32736 | `data/i;->z(Ljava/lang/String;)V` | 0x1020 | 0x0020 | `` | `0000:readLong(Ljava/lang/String;)J \|\| 000c:readLong(Ljava/lang/String;)J \|\| 0018:readInt(Ljava/lang/String;)I \|\| 0024:readInt(Ljava...` |
| `0x8022` | -32734 | `data/g;->f4(Ljava/lang/String;)V` | 0x1022 di_联网数据请求@scriptPages/data/g->c2 | 0x0022 | `` | `0006:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0012:readByte(Ljava/lang/String;)B \|\| 002c:readShort(Ljava/lang/String;)S \|\| ...` |
| `0x8024` | -32732 | `game/a0;->g0(Ljava/lang/String;)V` | 0x1024 reqFCMVerify@scriptPages/game/a0->f0 | 0x0024 | `` | `0000:readByte(Ljava/lang/String;)B` |
| `0x8025` | -32731 | `game/b0;->O0(Ljava/lang/String;)V` | 0x1025 (unnamed)@scriptPages/PageMain->ExitGame | 0x0025 | `` | `0000:readByte(Ljava/lang/String;)B` |
| `0x8100` | -32512 | `game/q;->m1(Ljava/lang/String;)V` | 0x1100 propdec@scriptPages/game/q->B1; reqItemMallGoods@scriptPages/game/q->t0 | 0x0100 | `` | `0000:readShort(Ljava/lang/String;)S \|\| 0006:readByte(Ljava/lang/String;)B \|\| 003a:readLong(Ljava/lang/String;)J \|\| 004a:readInt(Lja...` |
| `0x8101` | -32511 | `game/f0;->k(Ljava/lang/String;)V` | 0x1101 | 0x0101 | `` | `003c:readByte(Ljava/lang/String;)B \|\| 0052:readShort(Ljava/lang/String;)S \|\| 005e:readShort(Ljava/lang/String;)S \|\| 0096:readByte(L...` |
| `0x8102` | -32510 | `game/q;->k(Ljava/lang/String;)V` | 0x1102 buyMallGood@scriptPages/game/q->B1 | 0x0102 | `` | `0006:readByte(Ljava/lang/String;)B \|\| 000e:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 001c:readLong(Ljava/lang/String;)J \|\| 0...` |
| `0x8103` | -32509 | `game/k0;->Y(Ljava/lang/String;)V` | 0x1103 reqUseItem@scriptPages/game/k0->X | 0x0103 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0006:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x8104` | -32508 | `Lo/a;->q7(Ljava/lang/String;)V` | 0x1104 (unnamed)@o/a->M6 | 0x0104 | `` | `` |
| `0x8110` | -32496 | `data/i;->b(Ljava/lang/String;)V` | 0x1110 | 0x0110 | `04a6:readByte(Ljava/lang/String;)B \|\| 04d0:readBoolean(Ljava/lang/String;)Z \|\| 04dc:readBoolean(Ljava/lang/String;)Z \|\| 04ee:readBoolean(Ljava/lang/String;)Z \|\| 04fa:readBoolean(Ljava/lang/String;)Z \|\| 0518:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0526:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0534:readBoolean(Ljava/lang/String;)Z \|\| 0554:readBoolean(Ljava/lang/String;)Z \|\| 0562:readLong(Ljava/lang/String;)J \|\| 0570:readBoolean(Ljava/lang/String;)Z \|\| 057a:readBoolean(Ljava/lang/String;)Z \|\| 0588:readByte(Ljava/lang/String;)B \|\| 0596:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 05a4:readByte(Ljava/lang/String;)B \|\| 05ae:readShort(Ljava/lang/String;)S \|\| 05bc:readShort(Ljava/lang/String;)S \|\| 05d0:readByte(Ljava/lang/String;)B \|\| 05de:readByte(Ljava/lang/String;)B \|\| 05f4:readByte(Ljava/lang/String;)B \|\| 060e:readInt(Ljava/lang/String;)I \|\| 0624:readLong(Ljava/lang/String;)J \|\| 0630:readInt(Ljava/lang/String;)I \|\| 064e:readBoolean(Ljava/lang/String;)Z` | `0000:readLong(Ljava/lang/String;)J \|\| 000c:readLong(Ljava/lang/String;)J \|\| 0018:readInt(Ljava/lang/String;)I \|\| 0024:readInt(Ljava...` |
| `0x8112` | -32494 | `game/i;->x(Ljava/lang/String;)V` | 0x1112 di_提示不能发言@scriptPages/game/i->H | 0x0112 | `` | `000e:readByte(Ljava/lang/String;)B \|\| 0016:readInt(Ljava/lang/String;)I \|\| 002a:readBoolean(Ljava/lang/String;)Z` |
| `0x8113` | -32493 | `` | 0x1113 | 0x0113 | `` | `` |
| `0x8114` | -32492 | `game/h0;->a0(Ljava/lang/String;)V` | 0x1114 | 0x0114 | `` | `0028:readByte(Ljava/lang/String;)B \|\| 002e:readLong(Ljava/lang/String;)J \|\| 0058:readByte(Ljava/lang/String;)B \|\| 0064:readUTF(Ljav...` |
| `0x8116` | -32490 | `game/h0;->c0(Ljava/lang/String;)V` | 0x1116 reqDelMsg@scriptPages/game/h0->b0 | 0x0116 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readByte(Ljava/lang/String;)B \|\| 0026:readByte(Ljava/lang/String;)B \|\| 0032:readInt(Ljav...` |
| `0x8118` | -32488 | `game/h0;->h0(Ljava/lang/String;)V` | 0x1118 reqSendMsg@scriptPages/game/h0->g0 | 0x0118 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x811a` | -32486 | `game/h0;->f0(Ljava/lang/String;)V` | 0x111a (unnamed)@scriptPages/game/h0->m0 | 0x011a | `` | `` |
| `0x811d` | -32483 | `game/h0;->Y(Ljava/lang/String;)V` | 0x111d | 0x011d | `` | `0006:readByte(Ljava/lang/String;)B \|\| 0012:readLong(Ljava/lang/String;)J \|\| 001a:readInt(Ljava/lang/String;)I \|\| 0050:readShort(Lja...` |
| `0x811f` | -32481 | `game/h0;->d0(Ljava/lang/String;)V` | 0x111f | 0x011f | `` | `0000:readByte(Ljava/lang/String;)B \|\| 000c:readLong(Ljava/lang/String;)J \|\| 0026:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x8120` | -32480 | `data/i;->x(Ljava/lang/String;)V` | 0x1120 reqRoleInfo@scriptPages/game/w->d0 | 0x0120 | `0d28:readByte(Ljava/lang/String;)B` | `0004:readLong(Ljava/lang/String;)J \|\| 0010:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 001c:readByte(Ljava/lang/String;)B \|\| 0...` |
| `0x8122` | -32478 | `game/w;->T(Ljava/lang/String;)V` | 0x1122 | 0x0122 | `` | `0006:readByte(Ljava/lang/String;)B \|\| 000e:readByte(Ljava/lang/String;)B \|\| 0016:readInt(Ljava/lang/String;)I` |
| `0x8124` | -32476 | `game/w;->R(Ljava/lang/String;)V` | 0x1124 | 0x0124 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readByte(Ljava/lang/String;)B \|\| 0016:readByte(Ljava/lang/String;)B` |
| `0x8126` | -32474 | `game/w;->b(Ljava/lang/String;)V` | 0x1126 | 0x0126 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readByte(Ljava/lang/String;)B \|\| 0010:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x8130` | -32464 | `game/m0;->s(Ljava/lang/String;)V` | 0x1130 (unnamed)@scriptPages/game/m0->r | 0x0130 | `` | `` |
| `0x8131` | -32463 | `Lo/a;->k7(Ljava/lang/String;)V` | 0x1131 | 0x0131 | `` | `000c:readInt(Ljava/lang/String;)I \|\| 0066:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0076:readLong(Ljava/lang/String;)J \|\| 00...` |
| `0x8132` | -32462 | `game/m0;->w(Ljava/lang/String;)V` | 0x1132 reqTaskInfo@scriptPages/game/m0->v | 0x0132 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0012:readByte(Ljava/lang/String;)B \|\| 001a:readLong(Ljava/lang/String;)J \|\| 003c:readUTF(Ljav...` |
| `0x8134` | -32460 | `game/m0;->u(Ljava/lang/String;)V` | 0x1134 reqGainAward@scriptPages/game/m0->t | 0x0134 | `` | `0006:readByte(Ljava/lang/String;)B \|\| 0020:readByte(Ljava/lang/String;)B \|\| 002e:readLong(Ljava/lang/String;)J \|\| 003a:readLong(Lja...` |
| `0x8136` | -32458 | `game/m0;->y(Ljava/lang/String;)V` | 0x1136 facebook@scriptPages/game/m0->B | 0x0136 | `` | `0006:readByte(Ljava/lang/String;)B` |
| `0x8137` | -32457 | `Lo/a;->n7(Ljava/lang/String;)V` | 0x1137 | 0x0137 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readLong(Ljava/lang/String;)J \|\| 0038:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0...` |
| `0x8138` | -32456 | `Lo/a;->N7(Ljava/lang/String;)V` | 0x1138 di_联网数据请求@o/a->e5 | 0x0138 | `` | `000c:readLong(Ljava/lang/String;)J \|\| 0012:readByte(Ljava/lang/String;)B \|\| 0048:readInt(Ljava/lang/String;)I \|\| 006c:readInt(Ljava...` |
| `0x8139` | -32455 | `Lo/a;->m7(Ljava/lang/String;)V` | 0x1139 | 0x0139 | `` | `000c:readInt(Ljava/lang/String;)I \|\| 0066:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0076:readLong(Ljava/lang/String;)J \|\| 00...` |
| `0x813a` | -32454 | `Lo/a;->o7(Ljava/lang/String;)V` | 0x113a | 0x013a | `` | `0004:readByte(Ljava/lang/String;)B \|\| 000c:readLong(Ljava/lang/String;)J \|\| 003c:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0...` |
| `0x8140` | -32448 | `game/k0;->U(Ljava/lang/String;)V` | 0x1140 (unnamed)@scriptPages/game/k0->b0; statereturn@scriptPages/game/k0->b0 | 0x0140 | `` | `` |
| `0x8142` | -32446 | `game/k0;->W(Ljava/lang/String;)V` | 0x1142 reqRoleStatusSet@scriptPages/game/k0->V | 0x0142 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x8144` | -32444 | `game/k0;->a0(Ljava/lang/String;)V` | 0x1144 reqUseItem@scriptPages/game/k0->Z | 0x0144 | `` | `0006:readByte(Ljava/lang/String;)B \|\| 0022:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0030:readLong(Ljava/lang/String;)J \|\| 0...` |
| `0x8146` | -32442 | `data/g;->a3(Ljava/lang/String;)V` | 0x1146 (unnamed)@scriptPages/game/q->S0; (unnamed)@scriptPages/game/z->U0 | 0x0146 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0024:readByte(Ljava/lang/String;)B \|\| 0030:readByte(Ljava/lang/String;)B \|\| 0052:readShort(Lj...` |
| `0x8147` | -32441 | `gameHD/i;->a(Ljava/lang/String;)V` | 0x1147 REQ_GOLD_INFO@scriptPages/gameHD/i->u | 0x0147 | `` | `000c:readLong(Ljava/lang/String;)J \|\| 0014:readLong(Ljava/lang/String;)J` |
| `0x8148` | -32440 | `game/k0;->T(Ljava/lang/String;)V` | 0x1148 di_提示君主改名@scriptPages/game/k0->l0 | 0x0148 | `` | `0006:readByte(Ljava/lang/String;)B \|\| 0012:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 001e:readUTF(Ljava/lang/String;)Ljava/lan...` |
| `0x8149` | -32439 | `gameHD/k;->I(Ljava/lang/String;)V` | 0x1149 | 0x0149 | `` | `0012:readByte(Ljava/lang/String;)B \|\| 001e:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 002a:readByte(Ljava/lang/String;)B \|\| 0...` |
| `0x814a` | -32438 | `Lo/a;->L7(Ljava/lang/String;)V` | 0x114a reqReplaceSkin@o/a->T7 | 0x014a | `` | `000c:readByte(Ljava/lang/String;)B \|\| 0014:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0020:readShort(Ljava/lang/String;)S \|\| ...` |
| `0x814b` | -32437 | `game/n;->l2(Ljava/lang/String;)V` | 0x114b tencentOpenPf@scriptPages/PageMain->runCountryExchangeTip; tencentOpenPf@scriptPages/game/n->M0 | 0x014b | `` | `` |
| `0x814c` | -32436 | `gameHD/k;->R(Ljava/lang/String;)V` | 0x114c chenhaozhuanhuan@scriptPages/gameHD/k->w | 0x014c | `` | `0000:readLong(Ljava/lang/String;)J \|\| 0008:readInt(Ljava/lang/String;)I` |
| `0x814d` | -32435 | `game/n;->m2(Ljava/lang/String;)V` | 0x114d | 0x014d | `` | `0000:readLong(Ljava/lang/String;)J \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x814e` | -32434 | `Lo/a;->P7(Ljava/lang/String;)V` | 0x114e reqUnlockSkin@o/a->T7 | 0x014e | `` | `000c:readByte(Ljava/lang/String;)B \|\| 0012:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x814f` | -32433 | `game/w;->j0(Ljava/lang/String;)V` | 0x114f reqRoleIconAndName@scriptPages/game/j->t | 0x014f | `` | `0000:readInt(Ljava/lang/String;)I \|\| 0024:readInt(Ljava/lang/String;)I \|\| 002c:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x8150` | -32432 | `game/g0;->f(Ljava/lang/String;)V` | 0x1150 di_联网数据请求@scriptPages/game/g0->d | 0x0150 | `` | `0000:readInt(Ljava/lang/String;)I \|\| 000c:readLong(Ljava/lang/String;)J \|\| 0018:readLong(Ljava/lang/String;)J \|\| 0024:readInt(Ljava...` |
| `0x8152` | -32430 | `game/g0;->h(Ljava/lang/String;)V` | 0x1152 reqExchange@scriptPages/game/g0->g | 0x0152 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readLong(Ljava/lang/String;)J \|\| 0014:readLong(Ljava/lang/String;)J \|\| 0020:readLong(Lja...` |
| `0x8160` | -32416 | `game/k0;->S(Ljava/lang/String;)V` | 0x1160 di_提示金不足扩容@scriptPages/game/k0->o0 | 0x0160 | `` | `0000:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x8170` | -32400 | `game/n0;->P(Ljava/lang/String;)V` | 0x1170 | 0x0170 | `` | `0032:readByte(Ljava/lang/String;)B \|\| 0044:readShort(Ljava/lang/String;)S \|\| 0052:readShort(Ljava/lang/String;)S \|\| 0064:readByte(L...` |
| `0x8172` | -32398 | `game/n0;->I(Ljava/lang/String;)V` | 0x1172 | 0x0172 | `` | `0072:readByte(Ljava/lang/String;)B \|\| 0082:readShort(Ljava/lang/String;)S \|\| 0090:readShort(Ljava/lang/String;)S \|\| 00a2:readByte(L...` |
| `0x8174` | -32396 | `game/n0;->H(Ljava/lang/String;)V` | 0x1174 | 0x0174 | `` | `0032:readByte(Ljava/lang/String;)B \|\| 0044:readShort(Ljava/lang/String;)S \|\| 0052:readShort(Ljava/lang/String;)S \|\| 0064:readByte(L...` |
| `0x8176` | -32394 | `game/n0;->F(Ljava/lang/String;)V` | 0x1176 | 0x0176 | `` | `002a:readByte(Ljava/lang/String;)B \|\| 003a:readShort(Ljava/lang/String;)S \|\| 0048:readShort(Ljava/lang/String;)S \|\| 005a:readByte(L...` |
| `0x8177` | -32393 | `game/n0;->L(Ljava/lang/String;)V` | 0x1177 | 0x0177 | `` | `002a:readByte(Ljava/lang/String;)B \|\| 0038:readShort(Ljava/lang/String;)S \|\| 0044:readShort(Ljava/lang/String;)S \|\| 0056:readByte(L...` |
| `0x8178` | -32392 | `game/n0;->Q(Ljava/lang/String;)V` | 0x1178 | 0x0178 | `` | `002a:readByte(Ljava/lang/String;)B \|\| 0038:readShort(Ljava/lang/String;)S \|\| 0044:readShort(Ljava/lang/String;)S \|\| 0056:readByte(L...` |
| `0x8179` | -32391 | `game/q0;->P1(Ljava/lang/String;)V` | 0x1179 di_请求中@scriptPages/game/q0->u0 | 0x0179 | `` | `0008:readLong(Ljava/lang/String;)J \|\| 0010:readInt(Ljava/lang/String;)I \|\| 0020:readInt(Ljava/lang/String;)I \|\| 004e:readLong(Ljava...` |
| `0x817a` | -32390 | `game/n0;->R(Ljava/lang/String;)V` | 0x117a reqRankList_military@scriptPages/game/n0->N | 0x017a | `` | `0022:readLong(Ljava/lang/String;)J \|\| 002e:readByte(Ljava/lang/String;)B \|\| 0034:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0...` |
| `0x8180` | -32384 | `game/i0;->v(Ljava/lang/String;)V` | 0x1180 reqAchievementList@scriptPages/game/i0->o | 0x0180 | `` | `0000:readBoolean(Ljava/lang/String;)Z \|\| 0008:readBoolean(Ljava/lang/String;)Z \|\| 0018:readShort(Ljava/lang/String;)S \|\| 0020:readS...` |
| `0x8182` | -32382 | `game/i0;->s(Ljava/lang/String;)V` | 0x1182 | 0x0182 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0038:readLong(Ljava/lang/String;)J \|\| 0048:readByte(Ljava/lang/String;)B \|\| 0058:readUTF(Ljav...` |
| `0x8184` | -32380 | `game/i0;->u(Ljava/lang/String;)V` | 0x1184 reqAchievementCont@scriptPages/game/i0->n | 0x0184 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readLong(Ljava/lang/String;)J \|\| 0010:readByte(Ljava/lang/String;)B \|\| 0022:readByte(Lja...` |
| `0x8186` | -32378 | `game/i0;->z(Ljava/lang/String;)V` | 0x1186 reqNicknameList@scriptPages/game/i0->r | 0x0186 | `` | `0000:readBoolean(Ljava/lang/String;)Z \|\| 0008:readShort(Ljava/lang/String;)S \|\| 0010:readLong(Ljava/lang/String;)J \|\| 0018:readUTF(...` |
| `0x8188` | -32376 | `game/i0;->w(Ljava/lang/String;)V` | 0x1188 | 0x0188 | `` | `000e:readByte(Ljava/lang/String;)B \|\| 0016:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 002e:readByte(Ljava/lang/String;)B \|\| 0...` |
| `0x818a` | -32374 | `game/i0;->x(Ljava/lang/String;)V` | 0x118a reqActivationUseGold@scriptPages/game/i0->q | 0x018a | `` | `0006:readByte(Ljava/lang/String;)B \|\| 000e:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x818b` | -32373 | `game/i0;->t(Ljava/lang/String;)V` | 0x118b di_提示改变成就隐藏状态@scriptPages/game/i0->A | 0x018b | `` | `0006:readByte(Ljava/lang/String;)B \|\| 000e:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0016:readBoolean(Ljava/lang/String;)Z` |
| `0x8190` | -32368 | `game/s0;->Y(Ljava/lang/String;)V` | 0x1190 di_提示国数据@scriptPages/game/s0->G | 0x0190 | `` | `0000:readShort(Ljava/lang/String;)S \|\| 0016:readShort(Ljava/lang/String;)S \|\| 002c:readShort(Ljava/lang/String;)S \|\| 0058:readLong(...` |
| `0x8192` | -32366 | `game/s0;->X(Ljava/lang/String;)V` | 0x1192 reqForceMapCity@scriptPages/game/s0->Y | 0x0192 | `` | `0006:readShort(Ljava/lang/String;)S \|\| 003a:readLong(Ljava/lang/String;)J \|\| 004a:readByte(Ljava/lang/String;)B \|\| 0056:readShort(L...` |
| `0x8200` | -32256 | `game/q;->i(Ljava/lang/String;)V` | 0x1200 | 0x0200 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readByte(Ljava/lang/String;)B \|\| 000e:readLong(Ljava/lang/String;)J` |
| `0x8201` | -32255 | `game/q;->j(Ljava/lang/String;)V` | 0x1201 | 0x0201 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0014:readLong(Ljava/lang/String;)J` |
| `0x8202` | -32254 | `game/q;->r(Ljava/lang/String;)V` | 0x1202 | 0x0202 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0026:readLong(Ljava/lang/String;)J \|\| 003a:readShort(Ljava/lang/String;)S` |
| `0x8204` | -32252 | `game/q;->b0(Ljava/lang/String;)V` | 0x1204 fiefItemUse@scriptPages/game/q->S | 0x0204 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0026:readLong(Ljava/lang/String;)J \|\| 003a:readShort(Ljava/lang/String;)S` |
| `0x8206` | -32250 | `game/q;->e(Ljava/lang/String;)V` | 0x1206 | 0x0206 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0026:readLong(Ljava/lang/String;)J \|\| 003a:readByte(Ljava/lang/String;)B` |
| `0x8208` | -32248 | `game/q;->f(Ljava/lang/String;)V` | 0x1208 | 0x0208 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0026:readLong(Ljava/lang/String;)J` |
| `0x820b` | -32245 | `game/q;->Z1(Ljava/lang/String;)V` | 0x120b | 0x020b | `` | `0000:readByte(Ljava/lang/String;)B \|\| 002a:readByte(Ljava/lang/String;)B \|\| 0036:readByte(Ljava/lang/String;)B \|\| 0044:readInt(Ljav...` |
| `0x820d` | -32243 | `game/q;->c(Ljava/lang/String;)V` | 0x120d buildQueueAdd@scriptPages/game/q->K1; buildQueueAdd@scriptPages/game/q->w1 | 0x020d | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0026:readLong(Ljava/lang/String;)J` |
| `0x820f` | -32241 | `game/q;->X(Ljava/lang/String;)V` | 0x120f | 0x020f | `` | `0000:readByte(Ljava/lang/String;)B \|\| 000c:readLong(Ljava/lang/String;)J \|\| 0014:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x8210` | -32240 | `game/q;->V(Ljava/lang/String;)V` | 0x1210 fiefMoveAbleCitys@scriptPages/game/q->U | 0x0210 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0012:readShort(Ljava/lang/String;)S \|\| 001e:readShort(Ljava/lang/String;)S \|\| 002a:readByte(L...` |
| `0x8212` | -32238 | `game/q;->W(Ljava/lang/String;)V` | 0x1212 fiefMove@scriptPages/game/q->T | 0x0212 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 000c:readLong(Ljava/lang/String;)J \|\| 0018:readLong(Ljava/lang/String;)J \|\| 0042:readByte(Lja...` |
| `0x8213` | -32237 | `game/q;->Y(Ljava/lang/String;)V` | 0x1213 | 0x0213 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 001a:readByte(Ljava/lang/String;)B` |
| `0x8214` | -32236 | `game/z;->O(Ljava/lang/String;)V` | 0x1214 di_将名字长@scriptPages/game/z->Z0 | 0x0214 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0014:readLong(Ljava/lang/String;)J \|\| 0...` |
| `0x8215` | -32235 | `Lo/a;->f6(I Ljava/lang/String;)V` | 0x1215 reqLoadGenerals@o/a->a8 | 0x0215 | `0a60:readByte(Ljava/lang/String;)B \|\| 0a6c:readByte(Ljava/lang/String;)B` | `07d8:readByte(Ljava/lang/String;)B \|\| 07fa:readLong(Ljava/lang/String;)J` |
| `0x8216` | -32234 | `game/z;->B(Ljava/lang/String;)V` | 0x1216 | 0x0216 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0016:readLong(Ljava/lang/String;)J` |
| `0x8218` | -32232 | `game/z;->C(Ljava/lang/String;)V` | 0x1218 | 0x0218 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0014:readLong(Ljava/lang/String;)J \|\| 0028:readShort(Ljava/lang/String;)S \|\| 003e:readShort(L...` |
| `0x821b` | -32229 | `game/z;->G(Ljava/lang/String;)V` | 0x121b | 0x021b | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0006:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 000c:readLong(Ljava/lang/String;)J \|\| 0...` |
| `0x821d` | -32227 | `game/z;->P(Ljava/lang/String;)V` | 0x121d | 0x021d | `` | `0012:readByte(Ljava/lang/String;)B \|\| 0026:readLong(Ljava/lang/String;)J \|\| 003e:readByte(Ljava/lang/String;)B \|\| 004c:readInt(Ljav...` |
| `0x821f` | -32225 | `game/z;->I(Ljava/lang/String;)V` | 0x121f | 0x021f | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readByte(Ljava/lang/String;)B \|\| 0010:readLong(Ljava/lang/String;)J \|\| 0018:readLong(Lja...` |
| `0x8220` | -32224 | `game/z;->E(Ljava/lang/String;)V` | 0x1220 | 0x0220 | `` | `0000:readByte(Ljava/lang/String;)B` |
| `0x8222` | -32222 | `game/z;->L(Ljava/lang/String;)V` | 0x1222 | 0x0222 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readByte(Ljava/lang/String;)B \|\| 0010:readLong(Ljava/lang/String;)J \|\| 0018:readInt(Ljav...` |
| `0x8223` | -32221 | `game/z;->L0(Ljava/lang/String;)V` | 0x1223 | 0x0223 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 000c:readLong(Ljava/lang/String;)J \|\| 0018:readLong(Ljava/lang/String;)J \|\| 0024:readInt(Ljav...` |
| `0x8224` | -32220 | `game/z;->Q(Ljava/lang/String;)V` | 0x1224 generalAddPoint@scriptPages/game/z->U0 | 0x0224 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0010:readLong(Ljava/lang/String;)J \|\| 0...` |
| `0x8225` | -32219 | `game/z;->K0(Ljava/lang/String;)V` | 0x1225 reqGeneralPracticeCancel@scriptPages/game/z->U0 | 0x0225 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0010:readByte(Ljava/lang/String;)B` |
| `0x8226` | -32218 | `game/z;->S(Ljava/lang/String;)V` | 0x1226 generalWithSoldier@scriptPages/game/z->R | 0x0226 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readLong(Ljava/lang/String;)J \|\| 0010:readShort(Ljava/lang/String;)S \|\| 0016:readShort(L...` |
| `0x8228` | -32216 | `game/z;->N(Ljava/lang/String;)V` | 0x1228 (unnamed)@scriptPages/game/z->U0 | 0x0228 | `` | `0000:readByte(Ljava/lang/String;)B` |
| `0x8229` | -32215 | `game/p;->M0(Ljava/lang/String;)V` | 0x1229 reqBathAddArmy@scriptPages/game/p->L0 | 0x0229 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 001a:readByte(Ljava/lang/String;)B \|\| 0...` |
| `0x822a` | -32214 | `game/z;->P0(Ljava/lang/String;)V` | 0x122a reqGeneralUseItem@scriptPages/game/z->O0 | 0x022a | `` | `0000:readByte(Ljava/lang/String;)B \|\| 000c:readByte(Ljava/lang/String;)B` |
| `0x822b` | -32213 | `game/q;->Q1(Ljava/lang/String;)V` | 0x122b generalWithSoldier@scriptPages/game/q->y1 | 0x022b | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readLong(Ljava/lang/String;)J \|\| 0018:readByte(Ljava/lang/String;)B \|\| 0030:readByte(Lja...` |
| `0x822c` | -32212 | `game/q;->j1(Ljava/lang/String;)V` | 0x122c | 0x022c | `` | `0000:readLong(Ljava/lang/String;)J \|\| 0006:readByte(Ljava/lang/String;)B` |
| `0x822d` | -32211 | `game/q;->R(Ljava/lang/String;)V` | 0x122d | 0x022d | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readLong(Ljava/lang/String;)J \|\| 000e:readByte(Ljava/lang/String;)B \|\| 001a:readByte(Lja...` |
| `0x822f` | -32209 | `game/q;->Q(Ljava/lang/String;)V` | 0x122f di_驱逐@scriptPages/game/q->E1 | 0x022f | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0006:readLong(Ljava/lang/String;)J \|\| 000c:readByte(Ljava/lang/String;)B \|\| 001a:readByte(Lja...` |
| `0x8230` | -32208 | `game/q;->e0(Ljava/lang/String;)V` | 0x1230 | 0x0230 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readLong(Ljava/lang/String;)J \|\| 000e:readLong(Ljava/lang/String;)J \|\| 0014:readByte(Lja...` |
| `0x8231` | -32207 | `game/q;->l1(Ljava/lang/String;)V` | 0x1231 reqHurtSoldierCurePreInfo@scriptPages/game/q->k1 | 0x0231 | `` | `0000:readLong(Ljava/lang/String;)J \|\| 0006:readShort(Ljava/lang/String;)S \|\| 000e:readLong(Ljava/lang/String;)J \|\| 001a:readLong(Lj...` |
| `0x8232` | -32206 | `game/q;->g0(Ljava/lang/String;)V` | 0x1232 | 0x0232 | `` | `0000:readByte(Ljava/lang/String;)B` |
| `0x8233` | -32205 | `game/q;->o1(Ljava/lang/String;)V` | 0x1233 reqPrisonerCtrlInfo@scriptPages/game/q->n1 | 0x0233 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readByte(Ljava/lang/String;)B \|\| 0050:readLong(Ljava/lang/String;)J \|\| 005c:readLong(Lja...` |
| `0x8234` | -32204 | `game/q;->b1(Ljava/lang/String;)V` | 0x1234 | 0x0234 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x8236` | -32202 | `game/q;->c1(Ljava/lang/String;)V` | 0x1236 | 0x0236 | `` | `0000:readByte(Ljava/lang/String;)B` |
| `0x8238` | -32200 | `game/q;->d1(Ljava/lang/String;)V` | 0x1238 | 0x0238 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readBoolean(Ljava/lang/String;)Z` |
| `0x823b` | -32197 | `game/q;->a1(Ljava/lang/String;)V` | 0x123b | 0x023b | `` | `0000:readByte(Ljava/lang/String;)B` |
| `0x823d` | -32195 | `game/q;->U1(Ljava/lang/String;)V` | 0x123d | 0x023d | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readLong(Ljava/lang/String;)J \|\| 000e:readInt(Ljava/lang/String;)I \|\| 002a:readLong(Ljav...` |
| `0x823f` | -32193 | `game/q;->Y1(Ljava/lang/String;)V` | 0x123f | 0x023f | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x8240` | -32192 | `game/q;->V1(Ljava/lang/String;)V` | 0x1240 | 0x0240 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0024:readLong(Ljava/lang/String;)J \|\| 0044:readByte(Ljava/lang/String;)B \|\| 005a:readByte(Lja...` |
| `0x8242` | -32190 | `game/q;->T1(Ljava/lang/String;)V` | 0x1242 soldierRecruitCancle@scriptPages/game/q->S1 | 0x0242 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0022:readLong(Ljava/lang/String;)J \|\| 003c:readLong(Ljava/lang/String;)J \|\| 0048:readLong(Lja...` |
| `0x8244` | -32188 | `game/q;->X1(Ljava/lang/String;)V` | 0x1244 | 0x0244 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0022:readLong(Ljava/lang/String;)J \|\| 003c:readLong(Ljava/lang/String;)J \|\| 0048:readLong(Lja...` |
| `0x8246` | -32186 | `game/q;->h1(Ljava/lang/String;)V` | 0x1246 reqFiefInfo@scriptPages/game/q->g1 | 0x0246 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 000c:readLong(Ljava/lang/String;)J` |
| `0x8248` | -32184 | `game/q;->P1(Ljava/lang/String;)V` | 0x1248 soldierAverageRecuit@scriptPages/game/q->O1 | 0x0248 | `` | `0000:readInt(Ljava/lang/String;)I \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x824a` | -32182 | `Lo/a;->O7(Ljava/lang/String;)V` | 0x124a | 0x024a | `` | `` |
| `0x824b` | -32181 | `Lo/a;->I6(Ljava/lang/String;)V` | 0x124b | 0x024b | `` | `0000:readLong(Ljava/lang/String;)J` |
| `0x824c` | -32180 | `game/z;->M(Ljava/lang/String;)V` | 0x124c generalAddPoint@scriptPages/game/z->U0 | 0x024c | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0010:readLong(Ljava/lang/String;)J \|\| 0...` |
| `0x8250` | -32176 | `game/z;->F0(Ljava/lang/String;)V` | 0x1250 | 0x0250 | `` | `0000:readByte(Ljava/lang/String;)B` |
| `0x8252` | -32174 | `game/z;->D0(Ljava/lang/String;)V` | 0x1252 | 0x0252 | `` | `0000:readBoolean(Ljava/lang/String;)Z \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0010:readByte(Ljava/lang/String;)B` |
| `0x8254` | -32172 | `game/z;->H0(Ljava/lang/String;)V` | 0x1254 | 0x0254 | `` | `0006:readBoolean(Ljava/lang/String;)Z \|\| 000e:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0016:readByte(Ljava/lang/String;)B` |
| `0x8260` | -32160 | `game/z;->N0(Ljava/lang/String;)V` | 0x1260 | 0x0260 | `` | `0000:readByte(Ljava/lang/String;)B` |
| `0x8262` | -32158 | `game/z;->M0(Ljava/lang/String;)V` | 0x1262 re_提示用技能书@scriptPages/game/z->e1 | 0x0262 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0006:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 000e:readByte(Ljava/lang/String;)B` |
| `0x8270` | -32144 | `game/z;->J0(Ljava/lang/String;)V` | 0x1270 | 0x0270 | `` | `0006:readByte(Ljava/lang/String;)B \|\| 0014:readShort(Ljava/lang/String;)S \|\| 0020:readShort(Ljava/lang/String;)S \|\| 002e:readByte(L...` |
| `0x8272` | -32142 | `game/z;->B0(Ljava/lang/String;)V` | 0x1272 reqFamousSearch@scriptPages/game/z->A0 | 0x0272 | `` | `0006:readByte(Ljava/lang/String;)B \|\| 0048:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0050:readShort(Ljava/lang/String;)S \|\| ...` |
| `0x8274` | -32140 | `game/z;->x0(Ljava/lang/String;)V` | 0x1274 | 0x0274 | `` | `0006:readByte(Ljava/lang/String;)B \|\| 000e:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x8275` | -32139 | `gameHD/g;->E(Ljava/lang/String;)V` | 0x1275 di_将领成长值已满@scriptPages/gameHD/g->p; di_将领成长值已满@scriptPages/gameHD/h->B | 0x0275 | `` | `0042:readByte(Ljava/lang/String;)B \|\| 004e:readLong(Ljava/lang/String;)J \|\| 007e:readLong(Ljava/lang/String;)J \|\| 00b2:readLong(Lja...` |
| `0x8276` | -32138 | `game/z;->z0(Ljava/lang/String;)V` | 0x1276 reqFamousDetail@scriptPages/game/z->y0 | 0x0276 | `` | `0006:readByte(Ljava/lang/String;)B \|\| 0030:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0038:readLong(Ljava/lang/String;)J \|\| 0...` |
| `0x8278` | -32136 | `game/z;->Q0(Ljava/lang/String;)V` | 0x1278 (unnamed)@scriptPages/game/z->R0 | 0x0278 | `` | `` |
| `0x8280` | -32128 | `Lo/a;->e6(Ljava/lang/String;)V` | 0x1280 ChangeTeamNEW@scriptPages/gameHD/g->q | 0x0280 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 005c:readByte(Ljava/lang/String;)B \|\| 0072:readByte(Ljava/lang/String;)B \|\| 0078:readUTF(Ljav...` |
| `0x8300` | -32000 | `game/k;->E0(Ljava/lang/String;)V` | 0x1300 reqCityFiefList@scriptPages/game/k->D0; reqCityFiefList@scriptPages/game/p->O0 | 0x0300 | `0d62:readByte(Ljava/lang/String;)B` | `0000:readByte(Ljava/lang/String;)B \|\| 000e:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 001a:readShort(Ljava/lang/String;)S \|\| ...` |
| `0x8301` | -31999 | `game/k;->p1(Ljava/lang/String;)V` | 0x1301 di_联网请求数据中@scriptPages/game/k->W | 0x0301 | `` | `` |
| `0x8302` | -31998 | `game/k;->J0(Ljava/lang/String;)V` | 0x1302 | 0x0302 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 000e:readLong(Ljava/lang/String;)J \|\| 0016:readByte(Ljava/lang/String;)B` |
| `0x8303` | -31997 | `game/k;->o1(Ljava/lang/String;)V` | 0x1303 di_联网请求数据中@scriptPages/game/k->w1 | 0x0303 | `` | `0008:readByte(Ljava/lang/String;)B \|\| 0010:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0020:readInt(Ljava/lang/String;)I \|\| 00...` |
| `0x8304` | -31996 | `game/k;->r0(Ljava/lang/String;)V` | 0x1304 reqCityGarrisonList@scriptPages/game/k->i1 | 0x0304 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0010:readByte(Ljava/lang/String;)B \|\| 0...` |
| `0x8305` | -31995 | `game/k;->s0(Ljava/lang/String;)V` | 0x1305 | 0x0305 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0010:readLong(Ljava/lang/String;)J \|\| 0018:readInt(Ljava/lang/String;)I` |
| `0x8306` | -31994 | `game/k;->q0(Ljava/lang/String;)V` | 0x1306 | 0x0306 | `` | `005a:readByte(Ljava/lang/String;)B \|\| 0066:readInt(Ljava/lang/String;)I \|\| 0076:readLong(Ljava/lang/String;)J \|\| 008a:readShort(Lja...` |
| `0x8308` | -31992 | `game/k;->h1(Ljava/lang/String;)V` | 0x1308 reqModifyNotice@scriptPages/game/k->g1 | 0x0308 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0012:readLong(Ljava/lang/String;)J \|\| 001a:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x830b` | -31989 | `game/k;->a(Ljava/lang/String;)V` | 0x130b reqApplyFief@scriptPages/game/k->r1 | 0x030b | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0012:readBoolean(Ljava/lang/String;)Z` |
| `0x830d` | -31987 | `game/k;->Y0(Ljava/lang/String;)V` | 0x130d | 0x030d | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0018:readInt(Ljava/lang/String;)I \|\| 0024:readInt(Ljava/lang/String;)I \|\| 0030:readByte(Ljava...` |
| `0x830f` | -31985 | `game/w;->b0(Ljava/lang/String;)V` | 0x130f | 0x030f | `` | `0000:readByte(Ljava/lang/String;)B \|\| 000c:readByte(Ljava/lang/String;)B \|\| 0022:readByte(Ljava/lang/String;)B \|\| 002e:readByte(Lja...` |
| `0x8310` | -31984 | `game/w;->c0(Ljava/lang/String;)V` | 0x1310 reqRoleFiefList@scriptPages/game/p->g0; di_联网城池列表@scriptPages/game/w->q0 | 0x0310 | `0de8:readByte(Ljava/lang/String;)B` | `0000:readByte(Ljava/lang/String;)B \|\| 000c:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0018:readUTF(Ljava/lang/String;)Ljava/lan...` |
| `0x8312` | -31982 | `game/k;->G0(Ljava/lang/String;)V` | 0x1312 reqCityForceExpel@scriptPages/game/k->F0 | 0x0312 | `` | `0000:readByte(Ljava/lang/String;)B` |
| `0x8314` | -31980 | `game/k;->H0(Ljava/lang/String;)V` | 0x1314 | 0x0314 | `` | `0000:readByte(Ljava/lang/String;)B` |
| `0x8316` | -31978 | `game/k;->K0(Ljava/lang/String;)V` | 0x1316 | 0x0316 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0018:readByte(Ljava/lang/String;)B \|\| 0026:readLong(Ljava/lang/String;)J \|\| 003a:readByte(Lja...` |
| `0x8318` | -31976 | `game/k;->M0(Ljava/lang/String;)V` | 0x1318 | 0x0318 | `` | `0010:readByte(Ljava/lang/String;)B \|\| 004c:readByte(Ljava/lang/String;)B \|\| 005c:readLong(Ljava/lang/String;)J \|\| 0076:readByte(Lja...` |
| `0x831b` | -31973 | `game/k;->x0(Ljava/lang/String;)V` | 0x131b reqCityConnectCities@scriptPages/game/k->w0 | 0x031b | `` | `0000:readByte(Ljava/lang/String;)B \|\| 000c:readByte(Ljava/lang/String;)B \|\| 00aa:readLong(Ljava/lang/String;)J \|\| 00b6:readByte(Lja...` |
| `0x831c` | -31972 | `game/p;->N0(Ljava/lang/String;)V` | 0x131c | 0x031c | `` | `0006:readInt(Ljava/lang/String;)I \|\| 0014:readByte(Ljava/lang/String;)B \|\| 0026:readShort(Ljava/lang/String;)S \|\| 0032:readShort(Lj...` |
| `0x8320` | -31968 | `game/k;->C0(Ljava/lang/String;)V` | 0x1320 reqCityFiefExpel@scriptPages/game/k->B0 | 0x0320 | `` | `000c:readByte(Ljava/lang/String;)B \|\| 0014:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x8322` | -31966 | `game/k;->c1(Ljava/lang/String;)V` | 0x1322 reqCityTraitInfo@scriptPages/game/k0->O | 0x0322 | `` | `0000:readByte(Ljava/lang/String;)B` |
| `0x8324` | -31964 | `game/k;->d1(Ljava/lang/String;)V` | 0x1324 reqCityTraitLevelUp@scriptPages/game/k0->c0 | 0x0324 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0012:readByte(Ljava/lang/String;)B` |
| `0x8326` | -31962 | `game/k;->W0(Ljava/lang/String;)V` | 0x1326 reqCityResetTax@scriptPages/game/k->V0 | 0x0326 | `` | `0006:readByte(Ljava/lang/String;)B \|\| 0016:readLong(Ljava/lang/String;)J \|\| 001e:readInt(Ljava/lang/String;)I` |
| `0x832b` | -31957 | `game/k;->t0(Ljava/lang/String;)V` | 0x132b | 0x032b | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0012:readLong(Ljava/lang/String;)J \|\| 001a:readByte(Ljava/lang/String;)B` |
| `0x832d` | -31955 | `game/k;->f1(Ljava/lang/String;)V` | 0x132d reqCityYield@scriptPages/game/k->e1 | 0x032d | `` | `0006:readByte(Ljava/lang/String;)B` |
| `0x8330` | -31952 | `game/k;->v0(Ljava/lang/String;)V` | 0x1330 | 0x0330 | `` | `0006:readBoolean(Ljava/lang/String;)Z \|\| 000e:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0016:readByte(Ljava/lang/String;)B \|\...` |
| `0x8332` | -31950 | `game/k;->z0(Ljava/lang/String;)V` | 0x1332 reqCityCountryCollectInfo@scriptPages/game/k->y0 | 0x0332 | `` | `0006:readByte(Ljava/lang/String;)B \|\| 001e:readByte(Ljava/lang/String;)B \|\| 0026:readByte(Ljava/lang/String;)B \|\| 002e:readByte(Lja...` |
| `0x8334` | -31948 | `game/k;->A0(Ljava/lang/String;)V` | 0x1334 reqCityCountryCollect@scriptPages/game/k->s1 | 0x0334 | `` | `0000:readBoolean(Ljava/lang/String;)Z \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0010:readByte(Ljava/lang/String;)B \|\...` |
| `0x8335` | -31947 | `game/k;->b1(Ljava/lang/String;)V` | 0x1335 REQ_CITY_TOTEM_CTRL@scriptPages/game/k->Z0 | 0x0335 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0010:readShort(Ljava/lang/String;)S \|\| 0018:readLong(Ljava/lang/String;)J` |
| `0x8336` | -31946 | `game/k;->a1(Ljava/lang/String;)V` | 0x1336 | 0x0336 | `` | `0000:readBoolean(Ljava/lang/String;)Z \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0010:readByte(Ljava/lang/String;)B \|\...` |
| `0x8340` | -31936 | `game/k;->Q0(Ljava/lang/String;)V` | 0x1340 reqCityOwnerCampaignInfo@scriptPages/game/k->P0 | 0x0340 | `` | `0000:readByte(Ljava/lang/String;)B` |
| `0x8342` | -31934 | `game/k;->U0(Ljava/lang/String;)V` | 0x1342 reqCityOwnerRoleCampaignInfo@scriptPages/game/k->T0 | 0x0342 | `` | `0006:readByte(Ljava/lang/String;)B \|\| 0016:readByte(Ljava/lang/String;)B` |
| `0x8344` | -31932 | `game/k;->S0(Ljava/lang/String;)V` | 0x1344 reqCityOwnerCampaignRoleList@scriptPages/game/k->R0 | 0x0344 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0020:readByte(Ljava/lang/String;)B \|\| 002e:readShort(Ljava/lang/String;)S \|\| 0060:readUTF(Lja...` |
| `0x8346` | -31930 | `game/k;->O0(Ljava/lang/String;)V` | 0x1346 | 0x0346 | `` | `0006:readByte(Ljava/lang/String;)B \|\| 001c:readBoolean(Ljava/lang/String;)Z \|\| 0022:readUTF(Ljava/lang/String;)Ljava/lang/String;` |
| `0x8400` | -31744 | `game/w;->Z(Ljava/lang/String;)V` | 0x1400 | 0x0400 | `` | `0000:readByte(Ljava/lang/String;)B` |
| `0x8404` | -31740 | `game/n;->O0(Ljava/lang/String;)V` | 0x1404 | 0x0404 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 000c:readByte(Ljava/lang/String;)B \|\| 00be:readShort(Ljava/lang/String;)S \|\| 00d4:readShort(L...` |
| `0x8406` | -31738 | `game/n;->o2(Ljava/lang/String;)V` | 0x1406 | 0x0406 | `` | `0000:readByte(Ljava/lang/String;)B` |
| `0x8408` | -31736 | `game/n;->k2(Ljava/lang/String;)V` | 0x1408 di_提示国王加点@scriptPages/game/n->U2 | 0x0408 | `` | `0000:readByte(Ljava/lang/String;)B \|\| 0008:readUTF(Ljava/lang/String;)Ljava/lang/String; \|\| 0016:readByte(Ljava/lang/String;)B` |

## 4. 解读边界

- 本表是静态清洗结果，复杂分支、内联读取、条件调用仍需结合目标 handler 反汇编人工确认。
- `req-0x7000` / `req-0x8000` 是启发式请求 opcode 对齐，不是最终命名。
- `handler_direct_read_sequence` 只统计 handler 方法内直接出现的 `BaseIO.read*`，不展开其二级 parser。
