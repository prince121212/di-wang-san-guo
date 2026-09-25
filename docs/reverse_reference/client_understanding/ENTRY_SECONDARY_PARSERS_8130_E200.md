# 进服关键响应二级 Parser 合同：`0x8130` 与 `0xe200` 第一版

更新时间：2026-07-05

## 1. 已验证事实

- 抓包来源：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/captures/mitm/game_capture_20260705_020959/extracted/game_flows.json`
- 静态 DEX：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/recovered/original_classes_1.dex`
- 本轮解析 `0x8130` payload occurrence：`2` 个，唯一 payload：`1` 个。
- 本轮解析 `0xe200` payload occurrence：`4` 个，唯一 payload：`1` 个。
- `0x8130` 与 `0xe200` 当前样本均可按本报告 schema 消耗到 EOF：`True`。

## 2. `0x8130 -> m0.s -> m0.n` 任务列表结构

静态证据：`m0.s(String)` 清空 `q0` 任务展示缓存后调用 `m0.n(String)`；`m0.n` 在非 `A0` 分支固定读取 4 个顶层 group，每个 group 先读两个 byte 计数，再按 `long + UTF + boolean` 读取条目，最后读一个 trailing short。

```text
0x8130 payload:
  repeat group_index in 0..3:
      readByte primary_count      # primary 条目写 p0=1，并累加 m0.w0
      readByte secondary_count    # secondary 条目 p0 默认 0
      repeat primary_count:
          readLong task_id
          readUTF  task_name
          readBoolean flag_o0
      repeat secondary_count:
          readLong task_id
          readUTF  task_name
          readBoolean flag_o0
  readShort trailing_short        # 当前样本为 0，读取后未直接保存
```

| group | 标签候选 | primary | secondary | total | first id | first name |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 普通/成长任务候选 | 0 | 11 | 11 | 0x2714 | 种植技术 |
| 1 | 活动/运营任务候选 | 0 | 15 | 15 | 0x9b58ffba | 每日在线领好礼 |
| 2 | 国家/大型玩法入口候选 | 0 | 5 | 5 | 0x7919 | 百家争鸣 |
| 3 | 兑换/特殊入口候选 | 0 | 2 | 2 | 0x791a | 元宝换黄金 |

样本条目摘录：

| group | subgroup | id | name | flag_o0 |
| --- | --- | --- | --- | --- |
| 0 | secondary/p0=0 | 0x2714 | 种植技术 | True |
| 0 | secondary/p0=0 | 0x2716 | 建造弓兵营 | True |
| 0 | secondary/p0=0 | 0x2723 | 五谷丰登 | True |
| 0 | secondary/p0=0 | 0x273e | 威震四方6 | True |
| 0 | secondary/p0=0 | 0x2746 | 挑战山贼8 | True |
| 0 | secondary/p0=0 | 0x2757 | 使用鲁公手册 | True |
| 0 | secondary/p0=0 | 0x2764 | 剿匪英雄2 | True |
| 0 | secondary/p0=0 | 0x2774 | 开拓封地2 | True |
| 0 | secondary/p0=0 | 0x2786 | 招募将领12 | True |
| 0 | secondary/p0=0 | 0x27a9 | 升级将领4 | True |
| 0 | secondary/p0=0 | 0x27d8 | 修筑道路 | True |
| 1 | secondary/p0=0 | 0x9b58ffba | 每日在线领好礼 | True |

## 3. `0xe200 -> gameHD/a.h` 后页/活跃数据结构

`0xe200` 是 `0x6200 houyedu` 的响应；本样本 `status_s0=0`，进入完整数据分支。若 `status_s0==1`，客户端走“暂未开放/关闭提示”早退分支。

```text
0xe200 payload:
  readByte  s0_status
  if s0_status == 1: early return / not-open branch
  readLong  t0
  readShort u0
  readByte  v0, w0, x0, y0
  readByte  A0_count
  repeat A0_count: readByte -> B0[]
  readByte  C0_count
  repeat C0_count: readByte -> C0[]
  readByte  D_count
  repeat D_count:
      readByte marker -> D0[]
      readUTF  reward_text -> E0[]
      readByte status -> F0[]
  readUTF H0_text
  readLong ignored_or_activity_id
  readShort z0_active_score
  readShort I_count; repeat I_count: readUTF text, progress, reward
  readShort H_count; repeat H_count: readUTF text, progress, reward
  readByte L_count; repeat L_count: readShort threshold, readUTF reward, readShort aux
  readShort week_current; readShort week_target; readBoolean week_done; readUTF week_reward
  readShort month_current; readShort month_target; readBoolean month_done; readUTF month_reward
```

| s0 | t0 | date cand | x/y | B0 | D count | z0 | I | H | L | week | month |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 948001 | 2026-7-5 | 3/31 | 4 5 | 4 | 20 | 15 | 3 | 5 | 30/600 | 30/2800 |

奖励/签到相关摘录：

| section | idx | marker/threshold | text | status/aux |
| --- | --- | --- | --- | --- |
| cumulative_login_or_sign_reward_D0/E0/F0_candidate | 0 | 3 | 50000铜钱，150000粮食，20玉石 | 0 |
| cumulative_login_or_sign_reward_D0/E0/F0_candidate | 1 | 7 | 100000铜钱，300000粮食，100白银，1将神魂，30玉石 | 0 |
| cumulative_login_or_sign_reward_D0/E0/F0_candidate | 2 | 14 | 200000铜钱，600000粮食，200白银，2将神魂，50玉石 | 0 |
| cumulative_login_or_sign_reward_D0/E0/F0_candidate | 3 | 28 | 500000铜钱，1500000粮食，500白银，3将神魂，100玉石 | 0 |
| active_degree_reward_L/M/N_candidate | 0 | 20 | 10000铜钱，10白银，10玉石，随机道具 | 20 |
| active_degree_reward_L/M/N_candidate | 1 | 40 | 30000铜钱，20白银，10玉石，随机道具 | 0 |
| active_degree_reward_L/M/N_candidate | 2 | 60 | 50000铜钱，30白银，20玉石，随机道具 | 0 |
| active_degree_reward_L/M/N_candidate | 3 | 80 | 50白银，10图腾碎片，1中级行军符，60玉石，随机道具 | 0 |
| active_degree_reward_L/M/N_candidate | 4 | 100 | 100白银，1将神魂，1大福神符，100玉石，随机道具 | 0 |
| weekly_reward_f0/g0/h0/i0_candidate | 0 | 600 | 300白银，1鲁公古籍，1将神魂，1大练兵符，1中级行军符，随机道具 | False |
| monthly_reward_j0/k0/l0/m0_candidate | 0 | 2800 | 5神将碎片，5神装碎片，1000白银，500玉石，1凝魂晶石，1完整藏宝图，1紧急招募令，随机道具 | False |

活跃任务摘录：

| section | idx | task | progress | reward |
| --- | --- | --- | --- | --- |
| daily_active_task_I_candidate | 0 | 成功占领1个宝藏 | 0/1 | +10 |
| daily_active_task_I_candidate | 1 | 攻打1次流寇 | 0/1 | +10 |
| daily_active_task_I_candidate | 2 | 炼魂1次装备 | 0/1 | +10 |
| daily_active_task_I_candidate | 3 | 参与1次押镖系统 | 0/1 | +10 |
| daily_active_task_I_candidate | 4 | 世界频道发言1次 | 0/1 | +5 |
| daily_active_task_I_candidate | 5 | 获得一座城池 | 0/1 | +10 |
| daily_active_task_I_candidate | 6 | 参加5轮无损闯关 | 3/5 | +10 |
| daily_active_task_I_candidate | 7 | 剿灭山贼10次胜利 | 6/10 | +5 |
| daily_active_task_I_candidate | 8 | 参加1次抢城夺宝 | 0/1 | +5 |
| daily_active_task_I_candidate | 9 | 购买1件道具 | 0/1 | +10 |
| daily_active_task_I_candidate | 10 | 获得1点战功 | 0/1 | +5 |
| daily_active_task_I_candidate | 11 | 将领培养1次 | 0/1 | +5 |
| daily_active_task_I_candidate | 12 | 占领1个资源点 | 0/1 | +5 |
| daily_active_task_I_candidate | 13 | 获得1次夺取胜利 | 0/1 | +5 |
| daily_active_task_I_candidate | 14 | 军团频道发言1次 | 0/1 | +5 |
| special_active_task_H_candidate | 0 | 参加1次竞技场 | 1/1 | +5 |
| special_active_task_H_candidate | 1 | 成功强化1次装备 | 1/1 | +10 |
| special_active_task_H_candidate | 2 | 登入游戏 | 1/1 | +5 |

## 4. 关键推断与置信度

- `0x8130` 的 4 个 group 高置信是客户端任务/活动入口分组；group 业务中文名仍是候选，需要结合 UI 页签文字继续验证。
- `0x8130` 条目中的 boolean 写入 `m0.o0[group][idx]`，其最终语义暂命名为 `flag_o0`，不要过早命名为“已完成/可领取”。
- `0xe200` 的 `I[][]` 文本组直接显示每日活跃任务：任务文案、进度、奖励分值。
- `0xe200` 的 `L/M/N` 与 weekly/monthly 字段直接服务活跃度奖励 UI；奖励文本里包含铜钱、白银、玉石、将神魂等道具/资源。
- `0xe200` 里 `u0/v0/w0` 在样本中形如 `2026/7/5`，高置信是日期字段；`x0/y0` 仍保持候选命名。

## 5. 输出文件

- schema：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_secondary_parser_schema.csv`
- occurrence：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_secondary_payload_occurrences.csv`
- `0x8130` group：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_8130_task_groups.csv`
- `0x8130` entries：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_8130_task_entries.csv`
- `0xe200` summary：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_e200_summary.csv`
- `0xe200` reward rows：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_e200_rewards.csv`
- `0xe200` active tasks：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_e200_active_tasks.csv`
- static disasm：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_secondary_parser_disasm.txt`
- machine summary：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/entry_secondary_parser_summary.json`
- script：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_entry_secondary_parsers.py`

## 6. 下一步

1. 继续展开 `0x8004` gameLogin 主响应，重点验证 `data/i.y -> f6/c6/S5` 的进服状态同步边界。
2. 展开 `0x8008/0x800d` 大 payload，补城池缓存、地图缓存字段命名。
3. 将 `0x8130` group 业务中文名与 UI 页签/任务详情 `0x8132` 做动态或静态对齐。
