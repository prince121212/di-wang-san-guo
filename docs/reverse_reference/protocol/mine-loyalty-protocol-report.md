# 打矿满忠抓包分析

## 当前阶段 / Current phase

- 已完成本轮抓包的离线协议还原。
- 原始 PCAP 未修改：`ctf_out/passive_pcap_hotspot_20260714_134721/game_traffic.pcap`
- PCAP SHA-256：`5d589d6c3f9e4ccd992235cdc704db15dd4057125ae52b90cbe8faa2cf4b6e50`
- 操作时间线：`ctf_out/passive_pcap_hotspot_20260714_134721/operator_timeline.md`

## 已验证事实 / Verified facts

1. 单个将领增加忠诚度使用 `0x121f -> 0x821f`。
2. 铜钱加忠请求体为 12 字节：

   ```text
   generalId/writeLong
   generalType/writeByte = 0（己方将领）
   addLoyalty/writeShort
   paymentType/writeByte = 0（铜钱）
   ```

3. 本轮两次请求：

   | 将领 | ID | 加忠前 | 增加值 | 请求 payload |
   |---|---:|---:|---:|---|
   | 车2后来 | `0x01531924` | 59 | 41 | `000000000153192400002900` |
   | 车1 | `0x014c1be6` | 0 | 100 | `00000000014c1be600006400` |

4. 两次 `0x821f` 均为单将领成功响应，更新后的当前忠诚度和上限均为 `100/100`。
5. 响应会携带服务器计算出的实际费用及更新后的资源余额，不应由辅助自行决定最终扣款。
6. 本轮实际费用：

   | 将领 | 等级 | 增加值 | 实际费用 | 单点费用 |
   |---|---:|---:|---:|---:|
   | 车2后来 | 10 | 41 | 5,125 铜钱 | 125 |
   | 车1 | 19 | 100 | 25,000 铜钱 | 250 |

7. 费用不是所有将领统一固定单价。客户端会读取所选将领的单点费用；服务器在请求后返回实际费用。
8. 当前电脑辅助已经能从 `0x8004` 将领结构稳定读取：
   - `loyalty`：当前忠诚度
   - `loyaltyLimit`：忠诚度上限

## 响应结构 / Response structure

客户端 `scriptPages/game/z.I(String)` 的读取顺序为：

```text
result/readByte
mode/readByte
generalId/readLong
actualCost/readLong
copper/readLong
gold/readLong
resourceG/readLong

若 mode != 2：
  loyalty/readShort
  loyaltyLimit/readShort

若 mode == 2：
  count/readByte
  重复 count 次：
    generalId/readLong
    loyalty/readShort
    loyaltyLimit/readShort
```

本轮是单将领模式 `mode=0`。客户端把 `result=2` 作为失败并显示“忠诚度增加失败”；其他成功状态的完整枚举仍缺少失败实抓。
本轮两个响应在上述字段后均还有一个值为 `0` 的保留尾字节，解析时应允许并忽略。

## 关键证据 / Key evidence

| Flow | 时间 | 请求 | 响应 | 证据 |
|---:|---|---|---|---|
| 19 | 13:50:32.867 | `0x121f` | `0x821f` | 车2后来，增加41，费用5125，结果100/100 |
| 24 | 13:51:59.814 | `0x121f` | `0x821f` | 车1，增加100，费用25000，结果100/100 |

客户端静态证据：

- `0x821f` 分发到 `scriptPages/game/z.I(String)`。
- `scriptPages/game/z.H(long,int,int,int)` 按
  `writeLong + writeByte + writeShort + writeByte` 写入请求，并以
  `4639 / 0x121f` 发送。
- 该处理器按将领 ID 更新当前忠诚度和忠诚度上限。
- 失败分支使用“忠诚度增加失败”提示。
- 全部将领批量模式存在，但本轮打矿应只处理所选编队，不应使用全体加忠。

## 打矿接入规则 / Mine integration

勾选“打矿满忠”后，每次正式出征前执行：

1. 等待本条编队全部将领处于可出征状态。
2. 刷新所选 `generalIds` 的实时将领数据。
3. 对每名将领比较 `loyalty` 和 `loyaltyLimit`，不要只写死为 100。
4. 若 `loyalty < loyaltyLimit`：
   - 计算 `delta = loyaltyLimit - loyalty`；
   - 发送一次 `0x121f` 铜钱加忠请求；
   - 解析 `0x821f`，确认该将领达到上限。
5. 全部所选将领都满忠后，才进入出征预览和正式出征。
6. 任一将领加忠失败、响应缺失、铜钱不足或结果仍未满：
   - 本轮不得出征；
   - 记录明确日志；
   - 保留打矿常驻任务，稍后重试，不应错误地带低忠将领出征。
7. 未勾选“打矿满忠”时完全跳过该流程。

推荐日志：

```text
打矿满忠检查：车2后来 59/100，需要补41点
打矿满忠成功：车2后来 100/100，消耗5125铜钱
打矿满忠完成：本编队2名将领均为100/100
打矿满忠失败：车1铜钱加忠失败，本轮暂不出征
```

## 推断与置信度 / Inference and confidence

- `generalId + generalType(byte) + addLoyalty(short) + paymentType(byte)`：
  高置信度，已由客户端写包方法和两个差分样本共同验证。
- `paymentType=0` 表示铜钱：高置信度，与本轮人工操作和客户端铜钱分支一致。
- `result=2` 表示失败：高置信度，客户端控制流直接确认。
- 费用按等级区间变化：中等置信度。本轮10级和19级样本显示125/250，但无需依赖该公式开发。

## 尚未覆盖 / Remaining gaps

- 未实抓铜钱不足响应。
- 未实抓已经满忠时仍发送请求的响应；正确实现应在本地实时数据检查后避免发送。
- 未实抓黄金加忠，打矿功能不需要该分支。
- 未实抓 `mode=2` 全体将领批量加忠，打矿只应补当前编队，因此不需要该分支。

## 结论

本轮抓包已经足够开发“打矿出征前，将当前编队所有未满忠将领逐个使用铜钱补满”的成功路径。请求格式、成功后的忠诚度确认、实际费用返回及客户端失败分支都已明确；铜钱不足的精细错误文案可后续补抓，不阻塞首版接入。
