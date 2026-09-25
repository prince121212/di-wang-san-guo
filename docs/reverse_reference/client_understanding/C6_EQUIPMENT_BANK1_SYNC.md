# `Lo/a.c6` 装备 bank1 同步 parser 深拆（第一版）

生成时间：2026-07-05  
目标：补齐 `Lo/a.V5` 之后同一装备容器 `scriptPages/data/d` 的 bank1 同步逻辑；当前不做服务端实现。

## 1. 产物

- 字段读取序列：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/c6_read_sequence.csv`
- c6 调用点：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/c6_callers.csv`
- bank1 相关 parser / 字段索引：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/c6_bank1_related_parsers.csv`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/c6_extraction_summary.json`

## 2. 已验证事实

- 方法：`Lo/a;->c6(Ljava/lang/String;)V`，code_off `0x240470`。
- c6 方法内直接 `BaseIO.read*` 调用数：`15`。
- 全 DEX 静态发现 c6 调用方法数：`5`。
- c6 调用 `Lo/a.c3(0, host_id)` 定位宿主 index。
- 若 `Lo/a.c3(0, host_id)` 返回负数，c6 直接跳出，不继续消费后续字段。
- c6 使用 `Lo/a.jp[host_index]` 保存宿主绑定装备实例 id 列表。
- c6 使用与 V5 相同的 `scriptPages/data/d` 字段族，但写入第一维 `1`，即 bank1。
- c6 初始化 bank1 固定容量为 `120`，并把 `data.d.d[1]` 与 `data.d.k` 初始化为 `-1`。
- c6 upsert 装备记录时写入 `data.d.k[slot]=host_id`，形成 bank1 装备到宿主的反向关系。

## 3. 归一化读取结构候选

```text
c6(dis):
  readLong host_id
  host_index = Lo/a.c3(0, host_id)
  if host_index < 0:
    return                              # 不继续消费 c6 子包
  if Lo/a.jp[host_index] exists:
    for old_equipment_id in Lo/a.jp[host_index]:
      data.d.b(old_equipment_id)         # 从 bank1 删除旧装备
  data.d.a(host_id)                      # 清理 data.d.k == host_id 的 bank1 记录
  readByte linked_id_count
  Lo/a.jp[host_index] = new long[linked_id_count]
  repeat linked_id_count:
    readLong -> Lo/a.jp[host_index][i]
  ensure data.d bank1 arrays capacity 120
  readByte update_count
  repeat update_count:
    readLong equipment_id
    if equipment_id != -1:
      readShort -> data.d.e[1][slot]
      readByte attr_len
      repeat attr_len:
        readByte -> data.d.f[1][slot][j]
      readShort -> data.d.g[1][slot]
      readByte  -> data.d.h[1][slot][0]
      readByte  -> data.d.h[1][slot][1]
      readShort -> data.d.j[1][slot]
      readShort -> data.d.i[1][slot][0]
      readShort -> data.d.i[1][slot][1]
      readUTF   -> data.d.l[1][slot]
      data.d.d[1][slot] = equipment_id
      data.d.k[slot] = host_id
      data.d.m[1][slot] = 0
  sort bank1 by data.d.f[1][slot][0], data.d.f[1][slot][1]
```

## 4. 与 `Lo/a.V5` 的关系

- `V5` 全量重建 `scriptPages/data/d` bank0；`c6` 增量维护 bank1。
- 两者装备记录字段同构：`d/e/f/g/h/i/j/l/m`，其中 `d` 是装备实例 id，`e` 是模板/类型 short，`f` 是 byte 属性向量，`l` 是字符串字段。
- `c6` 额外维护 `data.d.k[slot] = host_id` 和 `Lo/a.jp[host_index]`，这是 bank1 相比 bank0 的宿主绑定关系。
- `c6` 常与 `V5`、`Lo/a.a6`、`Lo/a.f6` 同时出现在装备/道具/活动响应 handler 中，说明装备操作响应往往会同步 bank1、通用物品栈和其它装备派生状态。

## 5. 直接响应 handler 调用摘录

| response | caller | request candidate | c6 offset |
|---|---|---|---|
| `0xa252` | `La0/a;->C1(Ljava/lang/String;)V` | `0x3252` | `0x001c` |
| `0x8252` | `LscriptPages/game/z;->D0(Ljava/lang/String;)V` | `0x1252` | `0x001e` |
| `0x8250` | `LscriptPages/game/z;->F0(Ljava/lang/String;)V` | `0x1250` | `0x000c` |
| `0x8254` | `LscriptPages/game/z;->H0(Ljava/lang/String;)V` | `0x1254` | `0x0024` |

非直接 response handler 调用点（通常由登录/角色同步大 parser 间接调用）：

| caller | code_off | c6 offset | 说明 |
|---|---:|---:|---|
| `LscriptPages/data/i;->y(Ljava/lang/String;)V` | `0x28c188` | `0x005c` | `data/i.y` 会先调用 `data/i.x`、`data/g.y3`、`Lo/a.Z5`，再按 readByte 次数循环调用 c6；它出现在登录/角色资产初始化链路中。 |

## 6. 解读边界

- `host_id` 的真实业务对象仍需按 caller 分组确认；从调用场景看可能覆盖将领装备、活动任务奖励中的装备绑定、装备炼魂/强化等对象。
- `equipment_id == -1` 分支只消费 long 后跳过剩余装备字段，可能是空槽/删除/占位记录。
- bank1 排序复制了 `d/e/f/g/h/i/j/k/l`，没有明显复制 `m`；由于 c6 每次写入时把 `m[1][slot]` 置 0，该字段当前应视为低语义或待复核字段。
- 当前字段名仍是客户端结构名，不等同于最终服务端数据库字段名。

## 7. 后续深拆建议

1. 按 `c6_callers.csv` 把 `0xa252/0x8252/0x8254/0x8250` 等响应逐个展开，确认 host_id 的业务对象类型。
2. 深拆 `Lo/a.a6(I,String)` 与 `Lo/a.f6(I,String)`，它们经常跟 c6/V5 一起出现，可能负责装备槽位/将领派生状态。
3. 把 `data.d` accessor 的返回值映射成装备字段字典，尤其是 `D/w/z/t/q/u/j/i/E/k/B/A`。
4. 用实际装备操作抓包验证 `linked_id_count`、`update_count` 和 `equipment_id == -1` 的边界。
