# `Lo/a.a6` / `Lo/a.f6` / `Lo/a.b6` 将领/对象同步链路深拆（第一版）

生成时间：2026-07-05  
目标：先理解客户端对象/将领同步合同，为未来服务端重建准备；当前不实现服务端。

## 1. 产物

- 字段读取序列：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/a6_f6_b6_read_sequences.csv`
- 调用点索引：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/a6_f6_callers.csv`
- 相关 parser / 字段索引：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/general_sync_related_parsers.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/a6_f6_b6_s5_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/a6_f6_extraction_summary.json`

## 2. 已验证事实

- `Lo/a;->a6(ILjava/lang/String;)V` code_off `0x23ffb4`，直接 `BaseIO.read*` 数 `1`。
- `Lo/a;->f6(ILjava/lang/String;)V` code_off `0x240b38`，直接 `BaseIO.read*` 数 `2`。
- `Lo/a;->b6(ILjava/lang/String;I)V` code_off `0x23ffe0`，直接 `BaseIO.read*` 数 `57`。
- `Lo/a;->S5(Ljava/lang/String;)V` code_off `0x23e4f0`，直接 `BaseIO.read*` 数 `5`。
- `0x8215` 响应分支首个 handler：`0a7c:Lo/a;->f6(I Ljava/lang/String;)V`。
- `0x8215` 分支内直接读取：`0a60:readByte(Ljava/lang/String;)B || 0a6c:readByte(Ljava/lang/String;)B`。
- `Lo/a.a8()` 发送 `reqLoadGenerals / 0x1215`，请求体为 `writeByte(0)`、`writeByte(0)`、`writeLong(scriptPages/data/i.a)`；发送前后使用 `Lo/a.np/op` 做节流。
- `Lo/a.f6(type, stream)` 开头把 `Lo/a.np=false`，可视为 `reqLoadGenerals`/列表同步完成标志。
- `Lo/a.c3(type, id)` 只是在 `Lo/a.co[type]` 中查找 long id；`a6` 未命中时不调用 `b6`。
- `Lo/a.f6` 与 `Lo/a.S5` 的主数组容量均为 `30`；`f6` 的二维字段第一维固定为 `2`。
- `f6(type0)` 会尝试按对象 id 保留旧 `jp/kp` 绑定表，说明它与 `c6` 的装备 bank1 宿主绑定存在耦合。

## 3. 归一化结构候选

### 3.1 `Lo/a.a6(type, stream)`：单对象更新 wrapper

```text
a6(type, dis):
  object_id = readLong(dis)
  idx = Lo/a.c3(type, object_id)        # 在 Lo/a.co[type] 中查找
  if idx >= 0:
    Lo/a.b6(type, dis, idx)             # 只更新已存在 slot
```

### 3.2 `Lo/a.f6(type, stream)`：批量列表重建

```text
f6(type, dis):
  Lo/a.np = false
  ensure all object arrays exist: co/do/eo/.../Uo, capacity [2][30]
  reset row arrays for this type; co[type][i] and Eo[type][i] are set to -1
  if type == 0:
    snapshot old co[0], old jp/kp bindings for later id-based remap
  count = readByte(dis)
  for i in 0 .. count-1:
    co[type][i] = readLong(dis)
    b6(type, dis, i)
  if type == 0:
    rebuild jp/kp by matching new co[0][i] against the old id snapshot
```

### 3.3 `Lo/a.b6(type, stream, idx)`：单对象字段合同

```text
common fields, always read:
  UTF do; short eo; byte fo; byte go; short ho; short io; byte jo;
  int ko; int lo;
  short mo/no/oo/po/qo/ro/so/to/uo;
  int vo; byte wo; byte xo;
  short zo/Ao; byte Bo; short Co/Do;
  long Eo/Fo; int Jo/Ko; short Lo/Mo;
  No = curTime + readLong; Oo = curTime;
  byte Vo; short Po/Qo; long Ro; byte So; short To/Uo;

if type == 1:
  long Wo; UTF Xo; UTF Yo; long Zo; UTF ap; UTF bp; long cp;
else:
  int yo; Ho = curTime + readInt; short Io;
  if Vo[type][idx] == 3:
    dp = curTime + readInt; UTF ep; byte fp; UTF gp;
    short hp[0]; short hp[1]; UTF ip;
  if type == 0: mp = true
```

### 3.4 `Lo/a.S5(stream)`：伴随 30 槽状态表

```text
S5(dis):
  allocate Nm[30], Om[30], Pm[30], Qm[30]
  initialize Nm[i] = -1 and Pm[i] = -1
  count = readByte(dis)
  repeat count:
    readLong -> Nm[i]
    readLong -> Om[i]
    readByte -> Pm[i]
    readInt  -> Qm[i]
```

## 4. `b6` 字段读取表摘录

### 4.1 common 字段

| offset | read_call | target_or_field | note |
| --- | --- | --- | --- |
| 0x0010 | readUTF(Ljava/lang/String;)Ljava/lang/String; | Lo/a.do[type][idx] | 对象显示名/名称字符串候选；将领列表 UI 的核心字段。 |
| 0x0024 | readShort(Ljava/lang/String;)S | Lo/a.eo[type][idx] | 对象 short 参数 #1。 |
| 0x0038 | readByte(Ljava/lang/String;)B | Lo/a.fo[type][idx] | 对象 byte 参数 #1。 |
| 0x004c | readByte(Ljava/lang/String;)B | Lo/a.go[type][idx] | 对象 byte 参数 #2。 |
| 0x0060 | readShort(Ljava/lang/String;)S | Lo/a.ho[type][idx] | 对象 short 参数 #2。 |
| 0x0074 | readShort(Ljava/lang/String;)S | Lo/a.io[type][idx] | 对象 short 参数 #3。 |
| 0x0088 | readByte(Ljava/lang/String;)B | Lo/a.jo[type][idx] | 对象 byte 参数 #3。 |
| 0x009c | readInt(Ljava/lang/String;)I | Lo/a.ko[type][idx] | 对象 int 参数 #1。 |
| 0x00b0 | readInt(Ljava/lang/String;)I | Lo/a.lo[type][idx] | 对象 int 参数 #2。 |
| 0x00c4 | readShort(Ljava/lang/String;)S | Lo/a.mo[type][idx] | 对象 short 参数 #4。 |
| 0x00d8 | readShort(Ljava/lang/String;)S | Lo/a.no[type][idx] | 对象 short 参数 #5。 |
| 0x00ec | readShort(Ljava/lang/String;)S | Lo/a.oo[type][idx] | 对象 short 参数 #6。 |
| 0x0100 | readShort(Ljava/lang/String;)S | Lo/a.po[type][idx] | 对象 short 参数 #7。 |
| 0x0114 | readShort(Ljava/lang/String;)S | Lo/a.qo[type][idx] | 对象 short 参数 #8。 |
| 0x0128 | readShort(Ljava/lang/String;)S | Lo/a.ro[type][idx] | 对象 short 参数 #9；a8 会本地随时间递增并受 so 上限限制。 |
| 0x013c | readShort(Ljava/lang/String;)S | Lo/a.so[type][idx] | 对象 short 参数 #10；a8 中作为 ro 的上限。 |
| 0x0150 | readShort(Ljava/lang/String;)S | Lo/a.to[type][idx] | 对象 short 参数 #11。 |
| 0x0164 | readShort(Ljava/lang/String;)S | Lo/a.uo[type][idx] | 对象 short 参数 #12。 |
| 0x0178 | readInt(Ljava/lang/String;)I | Lo/a.vo[type][idx] | 对象 int 参数 #3。 |
| 0x018c | readByte(Ljava/lang/String;)B | Lo/a.wo[type][idx] | 对象 byte 参数 #4。 |
| 0x01a0 | readByte(Ljava/lang/String;)B | Lo/a.xo[type][idx] | 对象 byte 参数 #5。 |
| 0x01b4 | readShort(Ljava/lang/String;)S | Lo/a.zo[type][idx] | 对象 short 参数 #13。 |
| 0x01c8 | readShort(Ljava/lang/String;)S | Lo/a.Ao[type][idx] | 对象 short 参数 #14。 |
| 0x01dc | readByte(Ljava/lang/String;)B | Lo/a.Bo[type][idx] | 对象 byte 参数 #6。 |
| 0x01f0 | readShort(Ljava/lang/String;)S | Lo/a.Co[type][idx] | 对象 short 参数 #15。 |
| 0x0204 | readShort(Ljava/lang/String;)S | Lo/a.Do[type][idx] | 对象 short 参数 #16。 |
| 0x0218 | readLong(Ljava/lang/String;)J | Lo/a.Eo[type][idx] | 对象 long 参数 #1；f6 重载列表前把 Eo 初始化为 -1。 |
| 0x022c | readLong(Ljava/lang/String;)J | Lo/a.Fo[type][idx] | 对象 long 参数 #2。 |
| 0x0240 | readInt(Ljava/lang/String;)I | Lo/a.Jo[type][idx] | 对象 int 参数 #4。 |
| 0x0254 | readInt(Ljava/lang/String;)I | Lo/a.Ko[type][idx] | 对象 int 参数 #5。 |
| 0x0268 | readShort(Ljava/lang/String;)S | Lo/a.Lo[type][idx] | 对象 short 参数 #17。 |
| 0x027c | readShort(Ljava/lang/String;)S | Lo/a.Mo[type][idx] | 对象 short 参数 #18。 |
| 0x0288 | readLong(Ljava/lang/String;)J | Lo/a.No[type][idx]=curTime+readLong; Lo/a.Oo[type][idx]=curTime | 相对时间/倒计时字段；客户端转为绝对结束时间并记录同步时刻。 |
| 0x02b2 | readByte(Ljava/lang/String;)B | Lo/a.Vo[type][idx] | 对象状态 byte；a8 会检查状态 5/9 的倒计时，b6 type!=1 分支会检查状态 3。 |
| 0x02c6 | readShort(Ljava/lang/String;)S | Lo/a.Po[type][idx] | 对象 short 参数 #19。 |
| 0x02da | readShort(Ljava/lang/String;)S | Lo/a.Qo[type][idx] | 对象 short 参数 #20。 |
| 0x02ee | readLong(Ljava/lang/String;)J | Lo/a.Ro[type][idx] | 对象 long/时间参数 #3；a8 状态 9 会用它判断超时并清理装备绑定。 |
| 0x0302 | readByte(Ljava/lang/String;)B | Lo/a.So[type][idx] | 对象 byte 参数 #7。 |
| 0x0316 | readShort(Ljava/lang/String;)S | Lo/a.To[type][idx] | 对象 short 参数 #21。 |
| 0x032a | readShort(Ljava/lang/String;)S | Lo/a.Uo[type][idx] | 对象 short 参数 #22。 |

### 4.2 type==1 扩展字段

| offset | read_call | target_or_field | note |
| --- | --- | --- | --- |
| 0x0340 | readLong(Ljava/lang/String;)J | Lo/a.Wo[idx] | 仅 type==1 读取的 long 扩展字段 #1。 |
| 0x0350 | readUTF(Ljava/lang/String;)Ljava/lang/String; | Lo/a.Xo[idx] | 仅 type==1 读取的字符串扩展字段 #1。 |
| 0x0360 | readUTF(Ljava/lang/String;)Ljava/lang/String; | Lo/a.Yo[idx] | 仅 type==1 读取的字符串扩展字段 #2。 |
| 0x0370 | readLong(Ljava/lang/String;)J | Lo/a.Zo[idx] | 仅 type==1 读取的 long 扩展字段 #2。 |
| 0x0380 | readUTF(Ljava/lang/String;)Ljava/lang/String; | Lo/a.ap[idx] | 仅 type==1 读取的字符串扩展字段 #3。 |
| 0x0390 | readUTF(Ljava/lang/String;)Ljava/lang/String; | Lo/a.bp[idx] | 仅 type==1 读取的字符串扩展字段 #4。 |
| 0x03a0 | readLong(Ljava/lang/String;)J | Lo/a.cp[idx] | 仅 type==1 读取的 long 扩展字段 #3。 |

### 4.3 type!=1 / status==3 扩展字段

| offset | read_call | target_or_field | note |
| --- | --- | --- | --- |
| 0x03b6 | readInt(Ljava/lang/String;)I | Lo/a.yo[type][idx] | type!=1 扩展 int 字段；当前实际多见 type 0。 |
| 0x03c6 | readInt(Ljava/lang/String;)I | Lo/a.Ho[idx]=curTime+readInt | type!=1 扩展相对时间字段。 |
| 0x03da | readShort(Ljava/lang/String;)S | Lo/a.Io[idx] | type!=1 扩展 short 字段。 |
| 0x03fc | readInt(Ljava/lang/String;)I | Lo/a.dp[idx]=curTime+readInt | 仅 type!=1 且 Vo[type][idx]==3 时读取的相对时间字段。 |
| 0x0410 | readUTF(Ljava/lang/String;)Ljava/lang/String; | Lo/a.ep[idx] | 仅 type!=1 且 Vo==3 的字符串扩展字段 #1。 |
| 0x0420 | readByte(Ljava/lang/String;)B | Lo/a.fp[idx] | 仅 type!=1 且 Vo==3 的 byte 扩展字段。 |
| 0x0430 | readUTF(Ljava/lang/String;)Ljava/lang/String; | Lo/a.gp[idx] | 仅 type!=1 且 Vo==3 的字符串扩展字段 #2。 |
| 0x0446 | readShort(Ljava/lang/String;)S | Lo/a.hp[idx][0] | 仅 type!=1 且 Vo==3 的二元 short 参数 #0。 |
| 0x045a | readShort(Ljava/lang/String;)S | Lo/a.hp[idx][1] | 仅 type!=1 且 Vo==3 的二元 short 参数 #1。 |
| 0x046a | readUTF(Ljava/lang/String;)Ljava/lang/String; | Lo/a.ip[idx] | 仅 type!=1 且 Vo==3 的字符串扩展字段 #3。 |

## 5. 直接相关响应 handler

以下表只列直接响应 handler 或直接调用点，完整表见 CSV。

| target_method | caller | caller_code_off | invoke_offsets | response_opcodes_if_direct_handler | request_candidates_if_direct_handler |
| --- | --- | --- | --- | --- | --- |
| Lo/a;->S5(Ljava/lang/String;)V | La0/a;->C1(Ljava/lang/String;)V | 0xe4c8c | 0x0036 | 0xa252 | 0x3252 |
| Lo/a;->S5(Ljava/lang/String;)V | LscriptPages/game/z;->D0(Ljava/lang/String;)V | 0x36950c | 0x0038 | 0x8252 | 0x1252 |
| Lo/a;->a6(ILjava/lang/String;)V | La0/a;->C1(Ljava/lang/String;)V | 0xe4c8c | 0x0022 | 0xa252 | 0x3252 |
| Lo/a;->a6(ILjava/lang/String;)V | LscriptPages/data/g;->r4(Ljava/lang/String;)V | 0x288180 | 0x006e | 0xe280 | 0x6280 REQ_GENERAL_EQUIP_LIANHUN@scriptPages/data/g->N4 |
| Lo/a;->a6(ILjava/lang/String;)V | LscriptPages/game/k;->H0(Ljava/lang/String;)V | 0x2c9a08 | 0x0018 | 0x8314 | 0x1314 |
| Lo/a;->a6(ILjava/lang/String;)V | LscriptPages/game/q;->d1(Ljava/lang/String;)V | 0x327f7c | 0x001e | 0x8238 | 0x1238 |
| Lo/a;->a6(ILjava/lang/String;)V | LscriptPages/game/z;->B(Ljava/lang/String;)V | 0x365444 | 0x002a | 0x8216 | 0x1216 |
| Lo/a;->a6(ILjava/lang/String;)V | LscriptPages/game/z;->D0(Ljava/lang/String;)V | 0x36950c | 0x0024 | 0x8252 | 0x1252 |
| Lo/a;->a6(ILjava/lang/String;)V | LscriptPages/game/z;->E(Ljava/lang/String;)V | 0x3656b0 | 0x000e | 0x8220 | 0x1220 |
| Lo/a;->a6(ILjava/lang/String;)V | LscriptPages/game/z;->H0(Ljava/lang/String;)V | 0x3697e8 | 0x002a | 0x8254 | 0x1254 |
| Lo/a;->a6(ILjava/lang/String;)V | LscriptPages/game/z;->K0(Ljava/lang/String;)V | 0x369afc | 0x0020 | 0x8225 | 0x1225 reqGeneralPracticeCancel@scriptPages/game/z->U0 |
| Lo/a;->a6(ILjava/lang/String;)V | LscriptPages/game/z;->M0(Ljava/lang/String;)V | 0x369bb4 | 0x0026 | 0x8262 | 0x1262 re_提示用技能书@scriptPages/game/z->e1 |
| Lo/a;->a6(ILjava/lang/String;)V | LscriptPages/game/z;->P(Ljava/lang/String;)V | 0x365e2c | 0x0020 | 0x821d | 0x121d |
| Lo/a;->a6(ILjava/lang/String;)V | LscriptPages/game/z;->P0(Ljava/lang/String;)V | 0x369c94 | 0x001a | 0x822a | 0x122a reqGeneralUseItem@scriptPages/game/z->O0 |
| Lo/a;->a6(ILjava/lang/String;)V | LscriptPages/gameHD/g;->E(Ljava/lang/String;)V | 0x433b7c | 0x0062 \|\| 0x0092 \|\| 0x00c6 \|\| 0x020a \|\| 0x026e \|\| 0x02a2 | 0x8275 | 0x1275 di_将领成长值已满@scriptPages/gameHD/g->p; di_将领成长值已满@scriptPages/gameHD/h->B |
| Lo/a;->f6(ILjava/lang/String;)V | <direct response handler> |  |  | 0x8215 | 0x1215 reqLoadGenerals@o/a->a8 |
| Lo/a;->f6(ILjava/lang/String;)V | La0/a;->A1(Ljava/lang/String;)V | 0xe4c08 | 0x001e | 0xa273 | 0x3273 |
| Lo/a;->f6(ILjava/lang/String;)V | La0/a;->C1(Ljava/lang/String;)V | 0xe4c8c | 0x002a | 0xa252 | 0x3252 |
| Lo/a;->f6(ILjava/lang/String;)V | LscriptPages/game/k;->r0(Ljava/lang/String;)V | 0x2c8958 | 0x02f4 | 0x8304 | 0x1304 reqCityGarrisonList@scriptPages/game/k->i1 |
| Lo/a;->f6(ILjava/lang/String;)V | LscriptPages/game/q;->a1(Ljava/lang/String;)V | 0x327cb4 | 0x000e | 0x823b | 0x123b |
| Lo/a;->f6(ILjava/lang/String;)V | LscriptPages/game/q;->b1(Ljava/lang/String;)V | 0x327d50 | 0x001e \|\| 0x0026 \|\| 0x002c | 0x8234 | 0x1234 |
| Lo/a;->f6(ILjava/lang/String;)V | LscriptPages/game/q;->c1(Ljava/lang/String;)V | 0x327f0c | 0x000e | 0x8236 | 0x1236 |
| Lo/a;->f6(ILjava/lang/String;)V | LscriptPages/game/q;->d1(Ljava/lang/String;)V | 0x327f7c | 0x0016 | 0x8238 | 0x1238 |
| Lo/a;->f6(ILjava/lang/String;)V | LscriptPages/game/z;->D0(Ljava/lang/String;)V | 0x36950c | 0x002c | 0x8252 | 0x1252 |
| Lo/a;->f6(ILjava/lang/String;)V | LscriptPages/game/z;->F0(Ljava/lang/String;)V | 0x36976c | 0x0016 | 0x8250 | 0x1250 |
| Lo/a;->f6(ILjava/lang/String;)V | LscriptPages/game/z;->H0(Ljava/lang/String;)V | 0x3697e8 | 0x0036 | 0x8254 | 0x1254 |
| Lo/a;->f6(ILjava/lang/String;)V | LscriptPages/game/z;->M(Ljava/lang/String;)V | 0x365c3c | 0x0032 | 0x824c | 0x124c generalAddPoint@scriptPages/game/z->U0 |
| Lo/a;->f6(ILjava/lang/String;)V | LscriptPages/game/z;->M0(Ljava/lang/String;)V | 0x369bb4 | 0x001e | 0x8262 | 0x1262 re_提示用技能书@scriptPages/game/z->e1 |
| Lo/a;->f6(ILjava/lang/String;)V | LscriptPages/game/z;->N(Ljava/lang/String;)V | 0x365d38 | 0x000e | 0x8228 | 0x1228 (unnamed)@scriptPages/game/z->U0 |
| Lo/a;->f6(ILjava/lang/String;)V | LscriptPages/game/z;->N0(Ljava/lang/String;)V | 0x369c10 | 0x0010 | 0x8260 | 0x1260 |
| Lo/a;->f6(ILjava/lang/String;)V | LscriptPages/game/z;->P(Ljava/lang/String;)V | 0x365e2c | 0x0068 | 0x821d | 0x121d |
| Lo/a;->f6(ILjava/lang/String;)V | LscriptPages/game/z;->P0(Ljava/lang/String;)V | 0x369c94 | 0x0022 | 0x822a | 0x122a reqGeneralUseItem@scriptPages/game/z->O0 |
| Lo/a;->f6(ILjava/lang/String;)V | LscriptPages/game/z;->Q(Ljava/lang/String;)V | 0x365f0c | 0x0090 | 0x8224 | 0x1224 generalAddPoint@scriptPages/game/z->U0 |

## 6. 推断与置信度

- **高置信**：`f6` 是列表/批量对象同步；`a6` 是单对象增量更新；`b6` 是单对象字段 parser。
- **高置信**：`type 0` 至少覆盖“将领/可装备宿主”主表。证据：`0x8215 -> reqLoadGenerals`、大量 `scriptPages/game/z` 将领操作响应调用 `a6/f6`、`c6` 固定 `c3(0, host_id)` 绑定 bank1 装备。
- **中置信**：`type 1` 是与 type0 同构的第二对象表，用于地图/驻防/对方或扩展角色对象；它有 `Wo/Xo/Yo/Zo/ap/bp/cp` 额外身份/文本字段，但真实业务名仍需结合 UI 调用和抓包确认。
- **中置信**：`S5` 是和对象列表一起刷新的队列/状态/计时器类辅助表；它常与 `f6(0/1)` 同时出现在出征快照、登录资产初始化、装备操作响应中。
- **服务端重建影响**：任何返回 `f6/a6/b6/S5` 的响应必须严格保持字段顺序；尤其 `b6` 的 type 分支和 `Vo==3` 条件分支会改变后续读取位置。

## 7. 建议下一步

1. 沿 `scriptPages/game/z` 将领 UI 继续给 `b6` 字段命名：优先 `ro/so`、`Vo/No/Ro`、装备相关 id。
2. 深拆 `scriptPages/data/d` accessor 字典，把装备字段与 `c6/f6` 的宿主绑定串起来。
3. 展开 `0x8250/0x8252/0x8254`，确认装备操作响应中 `c6/a6/f6/V5/S5` 的组合顺序和业务状态码。
4. 回到进服链路 `0x8004/0x8008/0x8120/0x8310`，把登录后 `data/i.y -> f6/c6/S5/V5` 的最小响应合同补齐。
