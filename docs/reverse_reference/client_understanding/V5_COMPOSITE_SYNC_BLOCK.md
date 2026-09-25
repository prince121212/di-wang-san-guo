# `Lo/a.V5` 复合同步块深拆（第一版）
生成时间：2026-07-05  
目标：理解客户端通用同步块，不进入服务端实现。
## 1. 产物
- 字段读取序列：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/v5_read_sequence.csv`
- 子 parser / accessor 索引：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/v5_subblock_parsers.csv`
- V5 调用点：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/v5_callers.csv`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/v5_extraction_summary.json`

## 2. 已验证事实
- 方法：`Lo/a;->V5(Ljava/lang/String;)V`，code_off `0x23ee1c`。
- V5 方法内直接 `BaseIO.read*` 调用数：`22`。
- 全 DEX 静态发现 V5 调用方法数：`55`。
- `V5` 开头写入 `LscriptPages/data/g;->F/G` 两个 long。
- `V5` 重建 `Lo/a;->bv/cv/dv` 三组并行数组。
- `V5` 调用 `scriptPages/data/d.G()` 初始化装备数组，并全量重建 `scriptPages/data/d` 第 0 组 bank。
- `V5` 尾部写入 `Lo/a;->ev/fv`，消费一个未保存 short、一个未保存 byte，然后把 `Lo/a;->gv` 置为 `true`。

## 3. 归一化读取结构候选
```text
V5(dis):
  readLong -> data.g.F
  readLong -> data.g.G
  readShort stack_count
  repeat stack_count:
    readShort -> Lo/a.bv[i]      # 条目 id 候选
    readShort -> Lo/a.cv[i]      # 条目数量/值候选
    readLong  -> Lo/a.dv[i]      # 条目 long 参数候选
  data.d.G()                     # 初始化装备二维 bank
  readShort equipment_count
  repeat equipment_count:
    readLong  -> data.d.d[0][i]  # 装备实例 id
    readShort -> data.d.e[0][i]  # 装备模板/类型 id
    readByte  attr_len
    repeat attr_len:
      readByte -> data.d.f[0][i][j]
    readShort -> data.d.g[0][i]
    readByte  -> data.d.h[0][i][0]
    readByte  -> data.d.h[0][i][1]
    readShort -> data.d.j[0][i]
    readShort -> data.d.i[0][i][0]
    readShort -> data.d.i[0][i][1]
    readUTF   -> data.d.l[0][i]
    data.d.m[0][i] = 0
    if same id exists in data.d.d[1]: data.d.b(id)  # bank1 去重
  sort bank0 by data.d.f[0][i][0], data.d.f[0][i][1]
  readShort -> Lo/a.ev
  readShort -> Lo/a.fv
  readShort -> reserved/ignored
  readByte  -> reserved/ignored
  Lo/a.gv = true
```

## 4. 关键字段语义边界
- `Lo/a.bv/cv/dv` 更像“通用条目/物品/资源栈”而不是装备实例；证据是 `Lo/a.p1(J)` 对同 id 累加 `cv`，`Lo/a.g4/h4` 按 `scriptPages/data/g.T1(id)` 分类筛选。
- `scriptPages/data/d` 基本可以定为装备/宝物数据容器：静态字符串含“攻击、生命、防御、统兵”和“普通、良好、优秀、卓越”，并且大量 `game/k0`、`gameHD/c`、`game/z` UI 调用 `data.d` accessor。
- `data.d` 第一维有两个 bank：V5 全量重建 bank0；`Lo/a.c6(String)` 使用同一字段结构维护 bank1，并有 `data.d.k` 宿主 long 关系。
- `V5` 是大量响应后的“通用同步尾块/中块”，但它不是完整角色资产块：不少 caller 会在调用 V5 前后额外读取 `scriptPages/data/i.d/e/i`、封地、建筑、活动字段。

## 5. 与响应 opcode 的直接关系摘录
| response | caller | request candidate | V5 offset |
|---|---|---|---|
| `0xe307` | `La0/a;->A(Ljava/lang/String;)V` | `0x6307` | `0x0024` |
| `0xe343` | `La0/a;->B(Ljava/lang/String;)V` | `0x6343 Req_libutaskAward@a0/a->F` | `0x0090` |
| `0xa252` | `La0/a;->C1(Ljava/lang/String;)V` | `0x3252` | `0x0030` |
| `0xa131` | `La0/a;->H1(Ljava/lang/String;)V` | `0x3131` | `0x0016` |
| `0xa144` | `La0/a;->N1(Ljava/lang/String;)V` | `0x3144 reqUseItem@a0/a->M1` | `0x000e` |
| `0xe332` | `La0/a;->c2(Ljava/lang/String;)V` | `0x6332 ReqChallengeTaskAward@a0/a->J1` | `0x0072` |
| `0xe302` | `La0/a;->s(Ljava/lang/String;)V` | `0x6302` | `0x013e` |
| `0xe303` | `La0/a;->w(Ljava/lang/String;)V` | `0x6303` | `0x003a` |
| `0xe326` | `Lo/a;->E7(Ljava/lang/String;)V` | `0x6326` | `0x00ae` |
| `0x814e` | `Lo/a;->P7(Ljava/lang/String;)V` | `0x114e reqUnlockSkin@o/a->T7` | `0x0024` |
| `0x8104` | `Lo/a;->q7(Ljava/lang/String;)V` | `0x1104 (unnamed)@o/a->M6` | `0x000e` |
| `0xe288` | `LscriptPages/data/g;->m4(Ljava/lang/String;)V` | `0x6288` | `0x008e` |
| `0xe27b` | `LscriptPages/data/g;->q4(Ljava/lang/String;)V` | `0x627b di_寻宝中@scriptPages/data/g->a5` | `0x0098` |
| `0xe280` | `LscriptPages/data/g;->r4(Ljava/lang/String;)V` | `0x6280 REQ_GENERAL_EQUIP_LIANHUN@scriptPages/data/g->N4` | `0x0052` |
| `0x8114` | `LscriptPages/game/h0;->a0(Ljava/lang/String;)V` | `0x1114` | `0x028e` |
| `0x8112` | `LscriptPages/game/i;->x(Ljava/lang/String;)V` | `0x1112 di_提示不能发言@scriptPages/game/i->H` | `0x0036` |
| `0x8160` | `LscriptPages/game/k0;->S(Ljava/lang/String;)V` | `0x1160 di_提示金不足扩容@scriptPages/game/k0->o0` | `0x0008` |
| `0x8142` | `LscriptPages/game/k0;->W(Ljava/lang/String;)V` | `0x1142 reqRoleStatusSet@scriptPages/game/k0->V` | `0x0010` |
| `0x8103` | `LscriptPages/game/k0;->Y(Ljava/lang/String;)V` | `0x1103 reqUseItem@scriptPages/game/k0->X` | `0x000e` |
| `0x8144` | `LscriptPages/game/k0;->a0(Ljava/lang/String;)V` | `0x1144 reqUseItem@scriptPages/game/k0->Z` | `0x002a` |

## 6. 后续深拆建议
1. 深拆 `Lo/a.c6(String)`，补出 `data.d` bank1 的完整读取结构与宿主关系。
2. 对 `Lo/a.bv/cv/dv` 做字段字典：从 `Lo/a.g4/h4/p1/I8` 与 `game/k0` UI 反推条目 id、数量、时效 long 的语义。
3. 将 V5 caller 按 response opcode 分组，找出哪些业务响应只依赖 V5，哪些还需要额外资产/封地/建筑同步字段。
4. 用抓包样本中领取奖励、使用道具、装备操作响应对齐 V5 字段边界，验证 `stack_count/equipment_count` 的真实位置。
