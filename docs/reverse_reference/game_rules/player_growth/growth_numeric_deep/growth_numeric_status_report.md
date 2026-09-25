# 玩家成长数值深追状态：声望阈值与上限生成边界

- 样本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/三国·帝王联盟1.66.apk`
- Case：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166`
- 产出时间：2026-07-05

## 1. 本轮结论

这轮不是简单重复文本规则，而是从 DEX 静态链路确认：**君主等级、声望阈值、封地/将领/资源点上限的最终数值，大多由服务端同步给客户端；客户端主要负责显示和门槛判断。**

已确认：

| 字段 | 命名 | 证据 | 置信度 |
|---|---|---|---|
| `data.i.c` | 君主等级 | `q0.H` 直接绘制等级数字；`q0.V` 在 `c < 99` 时显示升级剩余声望，否则显示满级 | 高 |
| `data.i.i` | 当前声望 | `q0.H/q0.V` 用 `i-j` 作为当前等级内已获得声望 | 高 |
| `data.i.j` | 当前等级声望下限/上一级阈值 | 进度条起点；`i.b tag=12` 可刷新 | 中高 |
| `data.i.k` | 下一级声望阈值 | 进度条终点；`i.b tag=2` 可刷新 | 中高 |
| `data.i.s` | 封地上限 | `k.s1` 开辟封地前比较当前封地数与 `s`，满时显示 `re_开辟数量` | 高 |
| `data.i.t` | 将领上限 | `z.o/k0.o` 显示当前将领数/`t`；本轮未见生成公式 | 高 |
| `data.i.v` | 资源点上限 | `k0.o` 显示 `u/v`；本轮未见生成公式 | 高 |

## 2. 声望升级显示公式

证据方法：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/player_growth/growth_numeric_deep/method_disasm/scriptPages_game_q0__H__0x3f3c48.smali.txt`

`q0.H` 绘制君主信息面板中的声望进度条：

```text
cur_in_level = max(data.i.i - data.i.j, 0)
need_in_level = data.i.k - data.i.j
if need_in_level == 0:
    need_in_level = data.i.k   # 防止除 0 的兼容分支

progress_width = bar_width * cur_in_level / need_in_level
```

证据方法：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/player_growth/growth_numeric_deep/method_disasm/scriptPages_game_q0__V__0x3f87d4.smali.txt`

`q0.V` 在鼠标/触控提示中构造 `re_声望升级`：

```text
if data.i.c < 99:
    remaining = (data.i.k - data.i.j) - max(data.i.i - data.i.j, 0)
    # 正常阈值状态下等价于：remaining = data.i.k - data.i.i
    show "还需${声望数}声望升级"
else:
    show "满级"
```

## 3. 封地开辟门槛

证据方法：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/game_rules/player_growth/growth_numeric_deep/method_disasm/scriptPages_game_k__s1__0x2b52ac.smali.txt`

`k.s1` 中 `kinginfoopen`/开辟封地入口逻辑：

```text
current_fief_count = Lo/a.s2().length
if current_fief_count < data.i.s:
    进入开辟封地请求/选择流程
else:
    show re_开辟数量("您的等级只能开辟${数量}块封地", 数量=data.i.s)
```

这说明客户端没有在此处计算“等级能开几块封地”，而是直接消费服务端下发的 `data.i.s`。

## 4. 负向发现：尚未找到本地完整数值表

本轮扫描了候选字符串、字段引用和关键方法后，目前没有发现以下本地闭环：

1. 完整 `君主等级 -> 声望阈值` 表。客户端只显示 `data.i.j/k` 同步值。
2. 完整 `君主等级/声望/官职 -> 封地上限 data.i.s` 公式。客户端只判断当前封地数是否小于 `s`。
3. 完整 `将领上限 data.i.t` 生成公式。客户端主要显示/限制入口。
4. 完整 `资源点上限 data.i.v` 生成公式。客户端主要显示 `u/v`。
5. 官职自动轮选的服务端排序、名额和衰减公式。当前仍只有文本规则与 UI 字段证据。

## 5. 对重建服务端的影响

- 服务端要权威计算并同步 `level/current_prestige/level_prestige_floor/next_level_prestige/fief_cap/general_cap/resource_point_cap`。
- 初版服务端如果没有原始阈值表，可以先做配置表，并通过动态采样逐步拟合：每个等级采集一次 `data.i.c/i/j/k/s/t/u/v`。
- 客户端重建兼容重点不是在本地推导这些值，而是保证登录同步、资源/奖励同步、升级响应和 tagged update 能把这些字段及时下发。

## 6. 结构化产物

- `growth_numeric_field_status.csv`
- `growth_numeric_status_summary.json`
- `growth_numeric_candidate_methods.csv/json`
- `growth_numeric_candidate_disasm_summary.json`
- `method_disasm/`：候选方法反汇编证据
