# 修筑成功响应字段深追

- 日期：2026-07-05
- 目标：确认修墙/修路请求成功后，服务端通过哪个响应同步资源、贡献、道路、城墙字段。

## 1. 结论摘要

1. 修筑请求 `0x1304 / 4868` 的响应为 `0x8304`，在 Java/Dalvik signed short 中表现为 `-31996`。
2. dispatcher 证据：`Lo/a;->A6` 在 `000d98-000da0` 比较 `-31996` 并调用 `LscriptPages/game/k;->r0(String)`。
3. `k.r0(String)` 会直接同步：
   - 黄金：`scriptPages/data/g.F`
   - 粮食：`scriptPages/data/i.e`
   - 贡献：`scriptPages/data/i.p`
4. 若响应中的 `city_id != -1`，还会同步：
   - `wall_current / wall_max`：城墙/城防当前值与上限。
   - `road_current / road_max`：道路当前值与上限。
   - `tower_current / tower_max`：炮塔当前值与上限候选。
   - 修墙/修路/修塔三组贡献额度二元组。
5. 城池状态会写入多个缓存：`data.b.v/w/x`、`k.Y0/Z0/a1`、当前面板缓存、邻近城池列表缓存、角色城池列表缓存，并调用 `s0.h0(...)` 更新地图摘要。

## 2. 响应入口证据

来自 `Lo/a;->A6`：

```text
000d98: const/16 v2, -31996      ; unsigned 0x8304
000d9c: if-ne v9, v2, +007h
000da0: invoke-static v11, LscriptPages/game/k;->r0(Ljava/lang/String;)V
```

因此：

| 请求 | 请求 opcode | 响应 opcode | handler |
|---|---:|---:|---|
| 修墙/修路/修塔候选 | `0x1304 / 4868` | `0x8304 / signed -31996` | `k.r0(String)` |

## 3. 响应字段顺序

详表见：`analysis/game_rules/storage_offline_system/repair_response_fields.csv`。

核心顺序：

```text
status: readByte
message: readUTF
unknown_byte: readByte
unknown_int_1: readInt
unknown_int_2: readInt
gold: readLong -> data.g.F
food: readLong -> data.i.e
contribution: readLong -> data.i.p
city_id: readLong
if city_id != -1:
    wall_current: readInt
    wall_max: readInt
    road_current: readInt
    road_max: readInt
    tower_current_candidate: readInt
    tower_max_candidate: readInt
    contribution_limit_pair values: readInt x 6
```

## 4. 城墙、道路、炮塔三组状态

`k.r0` 读取三组 `int[2]` 后调用 `k.n1(...)`：

```text
k.n1(wall[2], road[2], tower[2], 0, wallContributionPair, roadContributionPair, towerContributionPair)
```

`k.n1` 明确写入：

```text
Y0 = wall[2]
Z0 = road[2]
a1 = tower[2]
b1/c1 = wall contribution pair
d1/e1 = road contribution pair
f1/g1 = tower contribution pair
```

其中 `Y0/Z0` 已在前一轮通过 `k.d()` 和文本规则确认：

- `Y0[1] - Y0[0]` 是城墙缺口。
- `Z0[1] - Z0[0]` 是道路缺口。

## 5. 对服务端重建的影响

修筑接口不能只返回“成功/失败”。为了让客户端状态一致，初版服务端应至少返回：

1. `status + message`。
2. 最新黄金、粮食、贡献。
3. 被修筑城池的 `city_id`。
4. 最新 `wall_current/wall_max`、`road_current/road_max`。
5. 若暂不实现炮塔，可仍按协议返回 `tower_current/tower_max=0` 或配置值。
6. 三组贡献额度字段，至少保证 `b1/d1/f1` 与客户端确认文案上限一致。

## 6. 当前边界

- 响应头 `unknown_byte/unknown_int_1/unknown_int_2` 读取但未保存，暂标为兼容字段。
- 贡献额度二元组中 `b1/d1/f1` 已参与确认文案上限；`c1/e1/g1` 的精确业务名仍待真实响应样本确认。
- 炮塔完整规则仍未展开，本轮只确认其与修墙/修路共用响应结构。
