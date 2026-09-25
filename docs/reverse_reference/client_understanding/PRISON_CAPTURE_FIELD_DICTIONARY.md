# 监狱/俘虏字段语义与动作入口（第一版）

生成时间：2026-07-05  
目标：拆 `scriptPages/game/z.n` 与相关动作入口，把 `Po/Qo/dp/gp/hp/ip` 精确映射到被劝/营救/劝降/被救/剩余时间/地点字段。

## 1. 产物

- 主报告：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/PRISON_CAPTURE_FIELD_DICTIONARY.md`
- 字段字典：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_capture_field_dictionary.csv`
- 页面模式表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_capture_page_modes.csv`
- 动作请求表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_capture_action_requests.csv`
- 反汇编摘录：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_capture_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/prison_capture_summary.json`

## 2. 页面模式

| z.o0 / z.m | 列表来源 | 页面语义 | 按钮 | 标签字段 | 置信度 |
|---|---|---|---|---|---|
| `0` / `0` | `Lo/a.G2(z.D,0)` | 我方被俘/待营救将领详情候选 | GeneralPrison_rescue=营救; GeneralPrison_giveup=放弃; return | 被劝次数(Po[0]); 营救次数(Qo[0]); 营救剩余(dp/e4); 标题封地(ip); 所在城(gp+hp) | high |
| `1 or 2 path using m=1` / `1` | `Lo/a.G2(z.D,1)` | 我方监狱中的俘虏/可劝降将领详情候选 | GeneralPrison_purchase=劝降; GeneralPrison_rescue_relieve=释放; return | 劝降次数(Po[1]); 被救次数(Qo[1]); 劝降剩余(cp/E3); 将领君主(Xo); 所在城(sv/data.b) | high |

## 3. 字段字典

| 字段 | Accessor | type0 命名 | type0 证据 | type1 命名 | type1 证据 | 置信度 |
|---|---|---|---|---|---|---|
| `Lo/a.Po[type][idx]` | `Lo/a.F3(II)` | `captured_self_persuaded_count` | `z.n` o0==0 在 `di_被劝次数` 下读取 F3(0,idx)。 | `prisoner_persuade_count` | `z.n` o0!=0 在 `di_劝降次数` 下读取 F3(1,idx)。 | high |
| `Lo/a.Qo[type][idx]` | `Lo/a.f4(II)` | `captured_self_rescue_count` | `z.n` o0==0 在 `di_营救次数` 下读取 f4(0,idx)。 | `prisoner_rescued_count` | `z.n` o0!=0 在 `di_被救次数` 下读取 f4(1,idx)。 | high |
| `Lo/a.dp[idx]` | `Lo/a.e4(I)` | `captured_self_rescue_cooldown_end_time` | `z.n` o0==0 在 `di_营救剩余` 下显示 e4(idx) 剩余时间；`z.d1` 点击营救前若 e4(idx)>0 提示 `di_再次营救`。 | `` | 仅 b6 type!=1 且 Vo==3 扩展块读取；type1 分支用 cp/E3 做劝降剩余。 | high |
| `Lo/a.gp[idx]` | `(direct array)` | `captured_self_city_name` | `z.n` o0==0 在 `di_所在城` 下显示 gp[idx]，并与 hp 坐标拼接。 | `` | type1 当前用城池表 Lo/a.sv + data/b 取所在城。 | medium-high |
| `Lo/a.hp[idx][0/1]` | `Lo/a.A1(J)` | `captured_self_city_coord_pair` | `z.n` o0==0 拼接 `gp + (hp[0],hp[1])`；A1(host_id) 内部通过 c3(0,id) 返回 hp[idx]。 | `` | type1 当前用 data/b.g/h 从城池 id 计算坐标。 | medium-high |
| `Lo/a.ip[idx]` | `(direct array)` | `captured_self_fief_name` | `z.n` o0==0 在 `di_标题封地` 下显示 ip[idx]。 | `` | type1 当前显示 `di_将领君主`/`Xo` 等归属信息。 | medium-high |
| `Lo/a.cp[idx]` | `Lo/a.E3(I)` | `` |  | `prisoner_persuade_cooldown_base_time` | `E3(idx)=max(cp[idx]+3600000-now,0)`；`z.n` o0!=0 在 `di_劝降剩余` 下显示，`z.d1` 点击劝降前若 E3(idx)>0 提示 `di_再次劝降`。 | high for type1 |

## 4. 关键结论

- `Po/Qo` 是同一组 short 字段，但 type0 与 type1 页面标签不同：type0 为“被劝次数/营救次数”，type1 为“劝降次数/被救次数”。
- `dp` 只在 b6 `type!=1 && Vo==3` 扩展块中读取；`e4(idx)` 将其解释为结束时间并显示 `营救剩余`。
- `gp/ip/hp` 也是 type0 俘虏地点扩展：`ip=封地名`、`gp=所在城名`、`hp=[x,y]`。
- type1 的 `劝降剩余` 不走 `dp`，而是 `cp + 3600000 - now`，说明 `cp` 是劝降冷却基准时间/上次劝降时间候选。
- `z.p0(general_id, mode)` 的按钮布局进一步验证：o0==0 是“营救/放弃”，o0!=0 是“劝降/释放”。

## 5. 动作/请求入口

| opcode | 方法 | 请求名/语义 | payload | 调用点 | 响应 |
|---|---|---|---|---|---|
| `0x1233` | `scriptPages/game/q.n1(I,J)` | reqPrisonerCtrlInfo | `writeByte(ctrl_type); writeLong(general_id)` | z.d1 营救/劝降前置消耗提示：ctrl_type=1 营救，ctrl_type=0 劝降。 | 0x8233 -> q.o1 |
| `0x1238` | `scriptPages/game/q.Z0(0x1238,D,general_id,pay_mode)` | prisoner rescue | `writeLong(z.D); writeLong(general_id); writeByte(pay_mode)` | z.d1 联网营救俘虏；pay_mode 0/1 对应铜钱/黄金候选。 | 0x8238 -> q.d1 |
| `0x1234` | `scriptPages/game/q.Z0(0x1234,D,general_id,pay_mode)` | prisoner persuade/lure | `writeLong(z.D); writeLong(general_id); writeByte(pay_mode)` | z.d1 联网劝降俘虏；pay_mode 0/1 对应铜钱/黄金候选。 | 0x8234 -> q.b1 |
| `0x123b` | `scriptPages/game/q.Z0(0x123b,D,general_id,0)` | give up captured self general | `writeLong(z.D); writeLong(general_id); writeByte(0)` | z.d1 放弃被俘将领。 | 0x823b -> q.a1 |
| `0x1236` | `scriptPages/game/q.Z0(0x1236,D,general_id,0)` | release prisoner | `writeLong(z.D); writeLong(general_id); writeByte(0)` | z.d1 释放俘虏；成长值>=90 时会二次确认。 | 0x8236 -> q.c1 |

## 6. 服务端重建影响

- 返回 `a6/f6/b6` 将领对象时，若 `Vo==3` 且 type0 对象处于被俘/待营救状态，需要同时提供 `dp/gp/hp/ip` 扩展，否则监狱详情页地点与营救剩余时间无法正确显示。
- `Po/Qo` 的业务含义依赖对象表 type：服务端字段命名不能简单统一为同一中文名，应在领域模型中按“我方被俘视角”和“我方监狱俘虏视角”区分。
- 监狱动作请求走 `0x1233/0x1234/0x1236/0x1238/0x123b`，服务端响应需要继续按对应 handler 深拆；本轮重点是 UI 字段命名。

## 7. 未解决问题

- `z.D` 在监狱动作请求中作为第一个 long 传入，语义大概率是封地/城池/监狱宿主 id，仍需结合 `q.Z0` 响应与抓包确认。
- `pay_mode 0/1` 在营救/劝降中根据铜钱/黄金余额分支选择，当前命名为支付模式候选。
- `Vo==3` 与其他状态码的完整枚举仍需后续状态机样本补齐。
