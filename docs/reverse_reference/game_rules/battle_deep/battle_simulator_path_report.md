# KING_BATTLE_SIMULATOR3.0 路径反查报告

生成时间：2026-07-05T06:53:56

## 1. 结论摘要

- `KING_BATTLE_SIMULATOR3.0` 在当前 DEX 证据中是一个 **本地 RMS 阵容/模拟器配置存档名**。
- `data.g->F3()` 负责从 RMS record #1 读取最多 20 个阵容槽，解析为 `m7..x7` 一组整数/整数数组缓存。
- `data.g->L4()` 负责处理模拟器 UI 输入、保存阵容，并把 `c6..n6` 当前配置序列化回同一个 RMS record #1。
- `data.g->G()` 与 `gameHD/f->r/k/b()` 主要是“战斗模拟器”界面绘制、士兵类型/数量配置、战法/称号选择、保存/选择/清空/开始战斗按钮。
- 在这些方法中没有发现基础伤害公式形态；没有出现围绕攻击、防御、生命、兵数进行权威伤害结算的闭环。当前更像 **离线模拟器配置 UI + 本地阵容缓存**，不是服务端战斗公式本体。

## 2. 组件路径

| 组件 | 角色 | 证据 | 公式信号 |
|---|---|---|---|
| `data.g->F3()` | 读取 KING_BATTLE_SIMULATOR3.0 RMS | F3 000064-000094 openRms/getRecord/openDis; 00009a-00023a 解析整数数组 | 无伤害公式；只读 boolean/int/int[] 并填 m7..x7 缓存 |
| `data.g->L4()` | 战斗模拟器交互/保存/开始入口 | L4 00003e/0000ac/00088e/000ab0/000b8a 输入默认/单项上场兵数；000cb6-000e8c 保存 RMS | 主要是 UI 输入、阵容保存、开始战斗按钮处理 |
| `data.g->G()` | 模拟器配置界面绘制 | G 00039a/0007ae 战法；00095a/000a44 称号；000aa0 保存阵容；000b50 选择阵容；000c7c 开始战斗；000eea 默认上场兵数 | 配置/展示界面 |
| `gameHD/f->r()` | HD 模拟器布局/士兵类型配置 | f->r 00026c 士兵类型配置；0002de 默认上场兵数；设置 P6/N6 等点击区域 | 布局/选择控件，不含战斗公式 |
| `gameHD/f->k()/b()` | HD 标题/绘制 “战斗模拟器” | f->k 000e80 计算标题区域；f->b 00121e 绘制 “战斗模拟器” | UI 绘制 |

## 3. RMS 格式镜像

| order | 字段 | 写入证据 | 读取证据 | 含义 | 公式信号 |
|---:|---|---|---|---|---|
| 0 | `slot_count` | L4 000d26 writeInt(array_length(o7)) | F3 00009a readInt() | 阵容槽数量；F3 初始化为 20 槽 | 非公式，仅 RMS 记录数 |
| 1 | `slot_present` | L4 000d9c writeBoolean(v3!=null) | F3 0000a8 readBoolean() | 当前槽是否有保存的阵容 | 非公式，仅是否存在 |
| 2 | `m7 <= c6` | L4 000da6 writeInt(c6) | F3 0000b4 readInt -> m7[slot] | 第一组配置标量，疑似进攻方/当前选择类型 | 保存/载入 UI 配置，不见伤害运算 |
| 3 | `n7/o7/p7/q7 <= d6/e6/f6/g6` | L4 000dac-000de8 length + four int arrays | F3 0000bc-00010e length + four int arrays | 第一组四列数组，疑似一方士兵类型/兵种/数量/附加配置 | 逐项写入整数配置，无乘除公式 |
| 4 | `r7 <= h6` | L4 000dea-000e08 int array | F3 000110-000132 int array | 第一组附加数组，可能为战法/称号/阵容附加项 | 配置保存 |
| 5 | `s7 <= i6` | L4 000e0a writeInt(i6) | F3 000134 readInt -> s7[slot] | 第二组配置标量，疑似防守方/另一方选择类型 | 配置保存 |
| 6 | `t7/u7/v7/w7 <= j6/k6/l6/m6` | L4 000e10-000e4c length + four int arrays | F3 00013c-00018e length + four int arrays | 第二组四列数组，疑似另一方士兵类型/兵种/数量/附加配置 | 逐项写入整数配置，无伤害运算 |
| 7 | `x7 <= n6` | L4 000e4e-000e6c int array | F3 000190-0001b6 int array | 第二组附加数组 | 配置保存 |
| 8 | `RMS record #1` | L4 000e76-000e8c dos2DataArray + setRecord(1) | F3 000074-000094 openRms/getRecord(1)/openDis | KING_BATTLE_SIMULATOR3.0 只有本地 RMS 第 1 条记录读写证据 | 本地持久化，不是网络/战斗结算 |

## 4. 方法统计

| 方法/文件 | 字符串 | BaseIO操作 | 算术指令数 | 结论 |
|---|---|---|---:|---|
| `F3_load` | KING_BATTLE_SIMULATOR3.0 | isRmsExist<br>openRms<br>isRecordExist<br>getRecord<br>openDis<br>closeDis<br>closeRms | 5 | RMS读写/数组配置 |
| `L4_ui_save_start` | <br>INPUT_DEFAULT_SOLDIER_NUM_SET<br>INPUT_SOLDIER_NUM_SET<br>INPUT_DEFAULT_SOLDIER_NUM_SET<br>默认上场兵数<br>INPUT_SOLDIER_NUM_SET<br>设置上场兵数<br>INPUT_SOLDIER_NUM_SET | openDos<br>writeInt<br>writeBoolean<br>writeInt<br>writeInt<br>writeInt<br>writeInt<br>writeInt<br>writeInt<br>writeInt<br>writeInt<br>writeInt | 69 | RMS读写/数组配置 |
| `G_draw` | 车<br>骑<br>弓<br>步<br><br>士兵<br>战法<br>士兵 |  | 160 | UI/绘制/布局 |
| `HD_f_r_layout` | 字字字字<br>士兵类型配置<br>默认上场兵数：<br>（<br>）<br>【进攻方】 |  | 117 | UI/绘制/布局 |
| `HD_f_k_layout` | coco<br>wxmini<br>战斗模拟器 |  | 143 | UI/绘制/布局 |
| `HD_f_b_draw` | <br>防沉迷温馨提示<br>02000<br>..<br>分钟<br>1<br>re_分钟后开战<br>战斗模拟器 |  | 211 | UI/绘制/布局 |

## 5. 对战斗公式恢复的影响

- 这一路径能帮助恢复“模拟器配置结构”：两方兵种/数量/战法/称号等配置如何保存。
- 这一路径暂时不能证明客户端包含完整基础伤害公式。
- 结合 `s->Z/f0/p0` 指令流结论：真实战斗回放消费服务端/生成侧结果；本地模拟器路径目前只看到配置保存与 UI。

## 6. 下一步

1. 继续追 `data.g->j5()`、`data.g->p5()`、`L4()` 中“开始战斗”按钮后续路径，确认是否会生成本地 fight 指令流或发起请求。
2. 搜索 `m7..x7/c6..n6` 的调用点，看这些配置是否进入某个计算函数。
3. 若仍未发现计算函数，服务端重建时应把战斗基础公式作为“需拟合/重写模块”，以客户端战斗回放格式作为输出目标。
