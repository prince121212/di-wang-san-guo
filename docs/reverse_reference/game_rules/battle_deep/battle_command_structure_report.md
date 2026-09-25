# 战斗指令流结构补充报告

生成时间：2026-07-05T06:49:46

## 1. 结论摘要

- `LscriptPages/game/s;->Z(String)` 是战斗/战报指令流解析入口。
- 指令流头部先 `readShort(commandCount)`，然后每条命令读取 `readByte(commandType)` 与 `readInt(timeOffsetMs)`。
- 当前确认 command type `1..11`，分别覆盖部队入场、进入战斗区、暂停/继续、离场、普通攻击、战斗结束、移动、提示文本、战法/技能攻击。
- 普通攻击与战法攻击均由指令流携带“攻击后剩余/前后数值”，客户端负责播放、同步与显示，不在该路径重新计算基础伤害。
- 攻击间隔 `C0` 的上游已明确：新协议 command type 1 直接 `readShort(attackIntervalMs)`，旧协议才有 4000/5000/7000ms 兼容推断。

## 2. 通用结构

- 方法：`LscriptPages/game/s;->Z(Ljava/lang/String;)V`，code_off `0x338bd8`
- 命令数量：`readShort at 000026`
- 每条命令头：`readByte(commandType) at 000040; readInt(timeOffsetMs) at 000048`
- 调度：每条命令写入 s.d1(type), s.e1(handlerIndex), s.f1(scheduledTimeMs)，并按 scheduledTimeMs/1000 分组写入 data.g.Qc/Rc
- 旧协议时间偏移：当 scriptPages/game/u.a == 0 时，末尾对 s.f1[3..22] 做 -7000/-17000/-16000/-19000/-22000/-23000/-25000/-26000/-28000/-29000/-31000 等兼容性偏移

## 3. command type 表

| type | 语义 | 读取结构 | handler | 与公式/机制关系 | 置信度 |
|---:|---|---|---|---|---|
| 1 | 进入行军区/创建战场部队 | `readLong(unitId); readByte(campOrSide); readUTF(name); [if new protocol readShort(extraA)]; readShort(soldierTypeOrIcon); [if new protocol readByte(extraB)]; readInt(extraC); readBoolean(flag); readInt(soldierCount); readShort(attackIntervalMs); [if HD/skin branch readShort(skinOrDisplay)]` | `s->j(I,J,I,String,S,I,B,I,I,S)` | attackIntervalMs 最终写入 C0；新协议直接下发，旧协议按兵数编码兼容为 4000/5000/7000ms | 高 |
| 2 | 加入布阵区/预备区候选 | `readLong(unitId); readByte(slotOrSide); readByte(extraA); readByte(extraB)` | `s->k(I,J)` | 战场位置/状态指令，不含伤害公式 | 中 |
| 3 | 加入到战斗区 | `readLong(unitId); readByte(actorOrSide); readByte(lane); readByte(col)` | `s->i(I,J,I,I)` | 使用 lane/col 进入战斗区，与 s->B/I/C/J 坐标函数相关 | 高 |
| 4 | 暂停行军区内行军 | `readByte(actorIndex)` | `s->e(I)` | 移动/演出控制，不含伤害公式 | 高 |
| 5 | 离开战斗 | `readLong(unitId); readByte(reasonOrSide)` | `s->c(J,I)` | 部队离场/撤退/死亡候选；伤兵资源仍来自指令结果 | 高 |
| 6 | 普通攻击指令 | `readByte(attackerCount); repeat readLong(attackerId), readShort(attackerArg); readByte(targetCount); repeat readLong(targetId), readShort(targetArg), readInt(oldOrFlagCandidate), readInt(newRemainOrWallValue)` | `s->a([J,[S,[J,[S,[I])` | 客户端不算基础伤害，只读取攻击后剩余值并做 old-new 显示/同步 | 高 |
| 7 | 战斗结束 | `readByte(resultOrFlag)` | `inline: h1=false; println("战场：战斗结束")` | 结束标记，不含胜负公式；胜负结果由指令流给出 | 高 |
| 8 | 使行军区内的部队继续行走 | `readByte(actorIndex)` | `s->f(I)` | 移动/演出控制，不含伤害公式 | 高 |
| 9 | 移动到战斗区指定位置 | `readLong(unitId); readByte(actorOrSide); readByte(lane); readByte(col)` | `s->d(I,J,I,I)` | 与前后/左右/坑位规则有关，使用 lane/col 坐标 | 高 |
| 10 | 战场文本/提示 | `readShort(textId); data.e$a->a(textId)` | `inline append to s.R2 string array` | 展示文本，不含公式 | 高 |
| 11 | 战法/技能攻击指令 | `readByte(sourceCount); repeat readLong(sourceId), readShort(skillOrBtId), readShort(sourceArg); readByte(targetCount); repeat readLong(targetId), readShort(targetArgA), readShort(targetArgB), readInt(beforeValue), readInt(afterValue)` | `s->l([J,[S,[S,[J,[S,[S,[I,[I]) and data.g->h(...)` | 客户端用 before-after 显示损兵/效果，不反推基础伤害 | 高 |

## 4. BaseIO 读调用证据索引

| type | 语义 | read 调用地址 |
|---:|---|---|
| 1 | 进入行军区/创建战场部队 | `00005a:readLong | 000062:readByte | 00006a:readUTF | 000080:readShort | 000088:readShort | 00009e:readByte | 0000a6:readInt | 0000ae:readBoolean | 0000b4:readInt | 0000bc:readShort | 0000d6:readShort` |
| 2 | 加入布阵区/预备区候选 | `00041a:readLong | 000422:readByte | 00042a:readByte | 000430:readByte` |
| 3 | 加入到战斗区 | `000576:readLong | 00057e:readByte | 000586:readByte | 00058e:readByte` |
| 4 | 暂停行军区内行军 | `0006dc:readByte` |
| 5 | 离开战斗 | `0007ac:readLong | 0007b4:readByte` |
| 6 | 普通攻击指令 | `0008e8:readByte | 0008fe:readLong | 00090a:readShort | 00091c:readByte | 000936:readLong | 000942:readShort | 00094e:readInt | 000976:readInt` |
| 7 | 战斗结束 | `000c0e:readByte` |
| 8 | 使行军区内的部队继续行走 | `000c2c:readByte` |
| 9 | 移动到战斗区指定位置 | `000ca4:readLong | 000cac:readByte | 000cb4:readByte | 000cbc:readByte` |
| 10 | 战场文本/提示 | `000f06:readShort` |
| 11 | 战法/技能攻击指令 | `000fc6:readByte | 000fe0:readLong | 000fe8:readShort | 000ff0:readShort | 00100a:readByte | 00102c:readLong | 001034:readShort | 00103c:readShort | 001044:readInt | 00104c:readInt` |

## 5. 对战斗公式的影响

### 基础伤害公式

当前更强证据支持：客户端 `s->Z/f0/p0` 路径是**战斗回放/表现层执行器**，不是权威伤害计算器。

- 普通攻击 type 6：响应/战报中已经携带目标 `newRemainOrWallValue`，客户端在 `f0()` 中用旧值与新值差额显示损兵。
- 战法 type 11：响应/战报中携带 `beforeValue/afterValue`，客户端在 `p0()` 中用 `before-after` 显示损兵或效果。
- 因此 `攻击、防御、生命、兵数、科技、装备、称号` 等如何合成为伤害，目前没有在此执行器路径闭环。

### 攻速/蓄力

- `C0` 是攻击间隔/蓄力上限，单位毫秒。
- 新协议中 command type 1 直接读取 `attackIntervalMs` 并经 `s->j(...) -> s->f0() -> s->h(...)` 写入 `C0`。
- 战法/BUFF 可能在 `p0()` 中修改 `C0/D0/E0/F0`，但原始“属性攻速 → 毫秒 C0”的权威公式更可能在服务端或战斗模拟器生成侧。

### 坐标/前后左右

- type 3 和 type 9 都读取 `lane/col` 并调用 `s->i/d`，与 `s->B/I/C/J` 坐标函数闭环。
- 坐标规则属于客户端表现层可恢复内容；它不决定伤害，只决定入场、移动、目标显示和前后左右站位。

## 6. 未完成

1. 继续追 `KING_BATTLE_SIMULATOR3.0` 相关的 `data.g->F3/L4/G` 是否只是本地模拟 UI，还是包含离线战斗计算数据。
2. 继续追 `REQ_FIGHTINFO` 请求/响应和真实战斗包，尝试把 command type 6/11 的字段与战报样本对齐。
3. 若要恢复服务端战斗公式，需要更多真实战报样本做拟合，或拿到服务端配置/模拟器计算侧。
