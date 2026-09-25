# 0x800D / flushCitys 城池地图初始缓存协议字段报告

生成时间：2026-07-05T07:32:46

## 1. 结论摘要

- `0x800D` 是城池地图/战斗目标完整缓存的原始 byte[] 下发入口。
- dispatcher 中 `0x800D` 以 signed short `-32755` 出现，由 `Lo/a;->A6` 调用 `LscriptPages/game/s0;->b([B)V`。
- `s0.b([B)V` 只有两条有效逻辑：把 byte[] 存到 `s0.g2`，然后返回。
- 真正解析发生在 `LscriptPages/game/s0;->w()V`：它读取 `s0.g2`，调用 `BaseIO.openDis(g2, "flushCitys")`，按 `flushCitys` 流格式解析完整城市/战斗目标缓存。
- `flushCitys` 记录结构与上一轮整理的 `0x8012 -> s0.S(String)` 增量更新结构高度一致；关键差异是 `flushCitys` 能新增未知 ID、找空槽、必要时扩容缓存数组 100 个槽位，并明确写入 `s0.K[index]`。

## 2. 链路证据

| 节点 | 证据 | 结论 |
|---|---|---|
| dispatcher | `Lo/a.A6 0003c0-0003c8` | signed short `-32755` / unsigned `0x800D` 调用 `s0.b([B)` |
| raw sink | `s0.b 000000` | `sput-object v0, s0.g2`，保存原始 payload |
| parser entry | `s0.w 000000-0000c4` | 若 `s0.g2` 非空，使用流名 `flushCitys` 打开 byte[] |
| parser header | `s0.w 0000ca` | 先 `readShort` 得到记录数量 |
| parser record | `s0.w 0000e4-000268` | 逐条读取城市/目标记录 |
| cache write | `s0.w 00051e-0005ba` | 写入 `s0.r/s/t/u/v/w/x/y/z/A/B/C/D/E/F/G/K/I/J/L` |

## 3. payload 格式

### 3.1 顶层结构

| 顺序 | 字段 | 类型 | 证据 | 含义 |
|---:|---|---|---|---|
| 0 | `raw_payload` | `byte[]` | `s0.b 000000` | `0x800D` 响应原始字节，保存到 `s0.g2` |
| 1 | `record_count` | `short` | `s0.w 0000ca` | 本次下发的城市/战斗目标记录数 |
| 2 | `records[i]` | struct[] | `s0.w 0000dc-0005be` | 循环读取并写入/扩容本地地图缓存 |

### 3.2 单条记录结构

| 顺序 | 字段 | 类型 | 写入缓存 | 证据 | 含义 |
|---:|---|---|---|---|---|
| 2.1 | `city_id` | `long` | `s0.r[index]` | `s0.w 0000e4 / 00051e` | 城市/战斗目标 ID |
| 2.2 | `coord_x` | `short` | `s0.s[index][0]` | `s0.w 0000ec / 000526` | x 坐标 |
| 2.3 | `coord_y` | `short` | `s0.s[index][1]` | `s0.w 0000f8 / 000526` | y 坐标 |
| 2.4 | `packed_icon_or_type_bytes` | `byte[]` | `s0.t[index]` | `s0.w 000104-000146 / 00052e` | 压缩 byte 序列；首字节高 2 位决定总数量，高 2 位为 0 时按 4 个 byte 处理；每个值取低 6 位 |
| 2.5 | `name` | `UTF` | `s0.u[index]` | `s0.w 000148 / 000536` | 城市/目标名称 |
| 2.6-2.9 | `status_byte_v/w/x/y` | `byte*4` | `s0.v/w/x/y` | `s0.w 000150-000168 / 00053e-00055a` | 四个状态/类型 byte，业务语义待 UI 命名 |
| 2.10 | `text_z` | `UTF` | `s0.z[index]` | `s0.w 000170 / 00055e` | 文本字段；非空时后跟 A byte |
| 2.11 | `optional_byte_A` | `byte?` | `s0.A[index]` | `s0.w 000178-000192 / 000566` | `text_z` 非空时读取，否则置 0 |
| 2.12 | `text_B` | `UTF` | `s0.B[index]` | `s0.w 000194 / 00056e` | 文本字段 |
| 2.13 | `text_C` | `UTF` | `s0.C[index]` | `s0.w 00019c / 000576` | 文本字段 |
| 2.14-2.16 | `D[0..2]` | `int[3]` | `s0.D[index]` | `s0.w 0001a8-0001c4 / 00057e` | 三个 int；与 `0x8012` 增量结构一致 |
| 2.17-2.18 | `E[0..1]` | `short[2]` | `s0.E[index]` | `s0.w 0001d6-0001ea / 000586` | 两个 short |
| 2.19-2.20 | `F[0..1]` | `int[2]` | `s0.F[index]` | `s0.w 0001fa-00020a / 00058e` | 两个 int |
| 2.21-2.22 | `G[0..1]` | `int[2]` | `s0.G[index]` | `s0.w 00021e-00022a / 000596` | 两个 int |
| 2.23-2.24 | `K[0..1]` | `int[2]` | `s0.K[index]` | `s0.w 000236-000246 / 00059e` | 两个 int；这是 `flushCitys` 相比 `s0.S` 更明确写回的字段 |
| 2.25 | `I` | `short` | `s0.I[index]` | `s0.w 000252 / 0005a6` | short 状态/数值字段 |
| 2.26 | `J` | `long` | `s0.J[index]` | `s0.w 00025a / 0005ae` | long 状态/时间/归属类候选 |
| 2.27 | `L` | `byte` | `s0.L[index]` | `s0.w 000262 / 0005b6` | byte 状态字段 |

## 4. 缓存管理规则

1. 如果 `s0.s` 尚未初始化，`s0.w()` 按 `s0.q` 初始化 `s0.r..L` 全套数组。
2. 每条记录先按 `city_id` 在线性缓存 `s0.r` 中查找已有项。
3. 如果找到已有 ID，则覆盖原索引。
4. 如果找不到，则查找 `s0.s[index] == null` 的空槽。
5. 如果没有空槽，则把 `s0.r..L` 全套缓存数组扩容 `+100`，拷贝旧值后写入新记录。
6. 解析结束后 `closeDis("flushCitys")`。
7. 若 `s0.b2` 为 true，解析后按屏幕中心/可见范围重新选择当前坐标，写入 `s0.O` 与 `s0.P`。

## 5. 与 `reqFightingCity / 0x1012` 的关系

- `0x800D / flushCitys`：完整/批量地图缓存首包，能新增未知城市或目标。
- `0x8012 / s0.S`：已有城市/目标的状态增量刷新，只按已有 `city_id` 匹配更新。
- `0x1012 / reqFightingCity`：客户端请求刷新战斗城市状态；当前 APK 1.66 默认请求体基本为 `count=0`。

对服务端重建来说，进入地图的最小链路应是：

1. 服务端先给客户端下发 `0x800D` 原始 byte[]，建立 `s0.r..L` 地图缓存。
2. 客户端运行 `s0.w()` 解析 `flushCitys`。
3. 后续客户端发 `0x1012 / reqFightingCity`。
4. 服务端用 `0x8012` 返回已有目标的增量状态。

## 6. 产物

- 字段表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/flush_city_initial_cache_fields.csv`
- JSON 汇总：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/flush_city_initial_cache_summary.json`
- 反汇编证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_fighting_city/scriptPages_game_s0__b__0x40b000.smali.txt`、`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/protocol_chain/method_disasm_fighting_city/scriptPages_game_s0__w__0x40e4e0.smali.txt`
