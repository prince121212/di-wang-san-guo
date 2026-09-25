# 治疗伤兵协议恢复进度（0x1231 / 0x1230）

更新时间：2026-07-08

## 已验证字段

### 0x1231 `reqHurtSoldierCurePreInfo`

来源：`LscriptPages/game/q;->k1(J I I)V`，code_off `0x328244`。

请求 payload：

| 顺序 | 写入方法 | 字段推断 |
|---:|---|---|
| 1 | `writeLong` | `fiefId/placeID` |
| 2 | `writeShort` | 伤兵兵种 row code，例如 `轻骑兵=3` |
| 3 | `writeInt` | 计划治疗数量 |

响应 handler：`LscriptPages/game/q;->l1(Ljava/lang/String;)V`，读取：

```text
readLong
readShort
readLong -> q.f4
readLong -> q.g4
```

推断为：封地/上下文 id、兵种、铜钱成本、黄金成本。

### 0x1230 治疗请求

来源：`LscriptPages/game/q;->d0(J I I I I)V`，code_off `0x3233b0`。

请求 payload：

| 顺序 | 写入方法 | 字段推断 |
|---:|---|---|
| 1 | `writeLong` | `fiefId/placeID` |
| 2 | `writeByte` | 伤兵分组/范围，历史 all-heal shape 中为 `2` |
| 3 | `writeShort` | 伤兵兵种 row code，例如 `轻骑兵=3` |
| 4 | `writeInt` | 治疗数量；历史 all-heal shape 中出现过 `-1` |
| 5 | `writeByte` | 是否黄金治疗，`0=铜钱/普通`、`1=黄金` |

响应 handler：`LscriptPages/game/q;->e0(Ljava/lang/String;)V`，读取：

```text
readByte status
readLong
readLong
readByte hasExtraState
```

错误码：

| status | 含义 |
|---:|---|
| `0` | 治疗成功 |
| `-1` | 铜钱不足 |
| `-2` | 治疗失败 |
| `-3` | 黄金不足 |

## 已接入电脑端代码

文件：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/电脑端辅助前端/server.py`

新增：

- `build_heal_preinfo_payload()`
- `build_heal_payload()`
- `parse_heal_preinfo_response()`
- `parse_heal_response()`
- `prepare_heal_wounded()`
- `recover_generals_from_8004()` 尝试带出将领 `placeID/fiefId`

当前自动刷黄循环会在恢复阶段生成治疗计划并记录日志；若缺少当前伤兵数量，则不会盲发 0x1230，避免误治疗/误扣资源。

## 仍需完成

要把“治疗伤兵”从安全 dry-run 变成真实发送，还需要稳定获得：

1. 当前封地/将领对应的 `fiefId/placeID`；
2. 当前伤兵兵种与数量，尤其是用户目标兵种（如轻骑兵）的伤兵数；
3. 至少一次实机抓包或客户端 UI 行为验证：`0x1231` 成本预估 -> 用户确认 -> `0x1230` 治疗。

在这三项全部验证前，电脑端自动任务会继续执行：找黄 -> 筛选 -> 出征 -> 等待 -> 治疗计划日志 -> 0x1229 补兵。

## 2026-07-08 追加：治疗全部语义接入

历史自研 shape 中：

```text
0x1230 payload tail = 02 0000 ffffffff 00
```

结合 `q.d0(J I I I I)` 字段顺序，解释为：

```text
group=2, soldierType=0, count=-1, useGold=0
```

同时 `q.l1()` 在解析 `0x8231` 时，若第二个字段 `readShort` 为负数，会走 `re_提示治疗全部` 文案分支。因此电脑端已接入：

```text
0x1231 治疗全部预估: fiefId + soldierType=-1 + count=-1
0x1230 治疗全部请求: fiefId + group=2 + soldierType=0 + count=-1 + useGold=0
```

电脑端后台循环现在会：

1. 若存在精确 `woundedCount`，按指定兵种/数量治疗；
2. 若缺少精确伤兵数但存在 `fiefId/placeID`，使用客户端“治疗全部”语义；
3. 若连 `fiefId/placeID` 都缺少，则跳过治疗，继续配兵/补兵，并在日志中说明。
