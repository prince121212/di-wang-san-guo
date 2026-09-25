# 协议 Envelope 与进服最小响应合同第一版

更新时间：2026-07-05

## 1. 已验证事实

- 抓包来源：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/captures/mitm/game_capture_20260705_020959/extracted/game_flows.json`
- 静态分发表：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/response_dispatch_clean.csv`
- 本轮成功解析 HTTP 游戏 flow：`20` 个。
- 成功解析请求 command：`27` 条；响应 packet：`33` 条。
- 所有已解析请求 header 均为：``1660606`7054`0000480502``。
- 所有请求 command 的 signature UTF 均为空串：`True`；对应 wire bytes 为 `00 00`。
- 所有响应 `obfuscation_flag`：`0`；所有 `fragment_or_cache_flag`：`0`。
- 每条 command 的第一个 long `dm` 在本抓包中固定为 `0x56ee99de606f4744`；响应 packet 的 long0 也固定为同值，说明它是连接/会话级 id 候选。

## 2. 请求 Envelope 线格式

真实抓包逐字段消耗到 EOF，和 `scriptPages/conn/a.a()` 静态写流顺序一致：

```text
request_packet:
  writeUTF(header)                       # 例：1660606`7054`0000480502
  writeLong(client_time)
  writeByte(command_count)
  repeat command_count:
      writeLong(dm/session_id_candidate) # 本样本固定 0x56ee99de606f4744
      writeLong(gm/command_unique_candidate) # 本样本均为 0
      writeShort(payload_length)
      writeShort(request_opcode)
      writeUTF(signature)                # 本样本均为空串，即 00 00
      writeByteArray(payload)            # 不额外写长度，长度来自 payload_length
```

## 3. 响应 Envelope 线格式

真实响应同样逐字段消耗到 EOF，和客户端 `readByte/readLong/readInt/readShort/readByteArray` 顺序一致：

```text
response_packet:
  readByte(outer_count)
  repeat outer_count:
      readByte(inner_count)
      repeat inner_count:
          readLong(long0/session_id_candidate)
          readLong(long1/server_time_or_sequence_candidate)
          readBoolean(obfuscation_flag)
          readInt(payload_length)
          readShort(response_opcode)
          readBoolean(fragment_or_cache_flag)
          readByteArray(payload)
          if obfuscation_flag:
              payload = Lo/a.P(Lo/a.o(), payload)
          Lo/a.A6(response_opcode, payload, "packetExe")
```

本次真实抓包中 `obfuscation_flag=0`，所以不需要解密即可对齐 response opcode 与 payload 长度。

## 4. 初始进服 #29~#35 摘要

| flow | req_len | resp_len | cmd_count | request opcodes | resp_packets | response opcodes | outer_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| #29 | 64 | 12375 | 1 | 0x1016 | 6 | 0x8001 0x800a 0x8146 0x8004 0xa129 0x8280 | 1 |
| #30 | 80 | 669 | 2 | 0x1104 0x1113 | 2 | 0x8104 0x8113 | 2 |
| #31 | 63 | 49870 | 1 | 0x1008 | 2 | 0x8008 0x800d | 1 |
| #33 | 126 | 7163 | 4 | 0x1800 0x1800 0x3110 0x6200 | 4 | 0x8800 0x8800 0xa110 0xe200 | 4 |
| #35 | 79 | 2379 | 2 | 0x1130 0x6200 | 2 | 0x8130 0xe200 | 2 |

## 5. 进服最小响应合同

这不是服务端实现，只是未来重建时必须优先满足的客户端入口响应序列基线。

| flow | request commands | response packets | 合同说明 |
| --- | --- | --- | --- |
| #29 | 0x1016(unknown,len=8,payload=00000000000002fc) | 0x8001(029c:Lo/a;->V8(J)V,len=19,outer=0) -> 0x800a(032a:LscriptPages/data/c;->j(Ljava/lang/String;)V,len=278,outer=0) -> 0x8146(0694:LscriptPages/data/g;->a3(Ljava/lang/String;)V,len=249,outer=0) -> 0x8004(02c6:LscriptPages/game/a0;->S([B)V,len=11397,outer=0) -> 0xa129(24be:La0/a;->I1(Ljava/lang/String;)V,len=4,outer=0) -> 0x8280(0c3e:Lo/a;->e6(Ljava/lang/String;)V,len=282,outer=0) | 进服/选择角色后主初始化批响应；单个 0x1016 触发 0x8001/0x800a/0x8146/0x8004/0xa129/0x8280，其中 0x8004 是 gameLogin 主响应。 |
| #30 | 0x1104(Lo/a;->M6,len=1,payload=00) -> 0x1113(unknown,len=1,payload=00) | 0x8104(0434:Lo/a;->q7(Ljava/lang/String;)V,len=618,outer=0) -> 0x8113(no-op/unknown,len=0,outer=1) | 进入后首批基础数据刷新；0x1104 有实体响应 0x8104，0x1113 对应空响应 0x8113。 |
| #31 | 0x1008(cacheData@game/s0->d0,len=7,payload=0b16c006800a0a) | 0x8008(0300:LscriptPages/game/s0;->y([B)V,len=25344,outer=0) -> 0x800d(03c8:LscriptPages/game/s0;->b([B)V,len=24476,outer=0) | cacheData/地图缓存初始化；0x1008 返回 0x8008 与 0x800d 两个大 payload。 |
| #33 | 0x1800(unknown,len=1,payload=00) -> 0x1800(unknown,len=1,payload=00) -> 0x3110(REQ_HD_LIVEPACKET@PageMain->runLivePacket,len=2,payload=0100) -> 0x6200(houyedu@gameHD/a->f,len=0,payload=<empty>) | 0x8800(1714:LscriptPages/game/w;->g0(Ljava/lang/String;)V,len=3,outer=0) -> 0x8800(1714:LscriptPages/game/w;->g0(Ljava/lang/String;)V,len=3,outer=1) -> 0xa110(24ac:La0/a;->D1(Ljava/lang/String;)V,len=5662,outer=2) -> 0xe200(1c34:LscriptPages/gameHD/a;->h(Ljava/lang/String;)V,len=1394,outer=3) | 进入后活动/在线/后页数据批量刷新；4 个请求与 4 个 outer group 一一对应。 |
| #35 | 0x1130(LscriptPages/game/m0;->r,len=1,payload=00) -> 0x6200(houyedu@gameHD/a->f,len=0,payload=<empty>) | 0x8130(1232:LscriptPages/game/m0;->s(Ljava/lang/String;)V,len=934,outer=0) -> 0xe200(1c34:LscriptPages/gameHD/a;->h(Ljava/lang/String;)V,len=1394,outer=1) | 普通任务列表与后页数据刷新；0x1130 返回任务列表 0x8130，0x6200 返回 0xe200。 |

## 6. 初始响应 packet → handler 对齐

| flow | outer.inner | resp opcode | payload_len | obf | frag | handler | request candidate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| #29 | 0.0 | 0x8001 | 19 | 0 | 0 | 029c:Lo/a;->V8(J)V | 0x1001 v1, ""@scriptPages/game/a0->U; 0x0001 |
| #29 | 0.1 | 0x800a | 278 | 0 | 0 | 032a:LscriptPages/data/c;->j(Ljava/lang/String;)V | 0x100a; 0x000a |
| #29 | 0.2 | 0x8146 | 249 | 0 | 0 | 0694:LscriptPages/data/g;->a3(Ljava/lang/String;)V | 0x1146 (unnamed)@scriptPages/game/q->S0; (unnamed)@scriptPages/game/z->U0; 0x0146 |
| #29 | 0.3 | 0x8004 | 11397 | 0 | 0 | 02c6:LscriptPages/game/a0;->S([B)V | 0x1004 gameLogin@scriptPages/game/a0->Q; accountLogin@scriptPages/game/b0->C0; (unnamed)@scriptPages/game/b0->D0; 0x0004 |
| #29 | 0.4 | 0xa129 | 4 | 0 | 0 | 24be:La0/a;->I1(Ljava/lang/String;)V | 0x3129 reqSetNewhandGuideInfo@scriptPages/gameHD/j->A; reqSetNewhandGuideInfo@scriptPages/gameHD/j->a; 0x2129 |
| #29 | 0.5 | 0x8280 | 282 | 0 | 0 | 0c3e:Lo/a;->e6(Ljava/lang/String;)V | 0x1280 ChangeTeamNEW@scriptPages/gameHD/g->q; 0x0280 |
| #30 | 0.0 | 0x8104 | 618 | 0 | 0 | 0434:Lo/a;->q7(Ljava/lang/String;)V | 0x1104 (unnamed)@o/a->M6; 0x0104 |
| #30 | 1.0 | 0x8113 | 0 | 0 | 0 | (no direct handler) | 0x1113; 0x0113 |
| #31 | 0.0 | 0x8008 | 25344 | 0 | 0 | 0300:LscriptPages/game/s0;->y([B)V | 0x1008 cacheData@scriptPages/game/s0->d0; 0x0008 |
| #31 | 0.1 | 0x800d | 24476 | 0 | 0 | 03c8:LscriptPages/game/s0;->b([B)V | 0x100d; 0x000d |
| #33 | 0.0 | 0x8800 | 3 | 0 | 0 | 1714:LscriptPages/game/w;->g0(Ljava/lang/String;)V | 0x1800; 0x0800 |
| #33 | 1.0 | 0x8800 | 3 | 0 | 0 | 1714:LscriptPages/game/w;->g0(Ljava/lang/String;)V | 0x1800; 0x0800 |
| #33 | 2.0 | 0xa110 | 5662 | 0 | 0 | 24ac:La0/a;->D1(Ljava/lang/String;)V | 0x3110 REQ_HD_LIVEPACKET@scriptPages/PageMain->runLivePacket; 0x2110 |
| #33 | 3.0 | 0xe200 | 1394 | 0 | 0 | 1c34:LscriptPages/gameHD/a;->h(Ljava/lang/String;)V | 0x7200; 0x6200 houyedu@scriptPages/gameHD/a->f |
| #35 | 0.0 | 0x8130 | 934 | 0 | 0 | 1232:LscriptPages/game/m0;->s(Ljava/lang/String;)V | 0x1130 (unnamed)@scriptPages/game/m0->r; 0x0130 |
| #35 | 1.0 | 0xe200 | 1394 | 0 | 0 | 1c34:LscriptPages/gameHD/a;->h(Ljava/lang/String;)V | 0x7200; 0x6200 houyedu@scriptPages/gameHD/a->f |

## 7. 关键推断与置信度

- `outer_count/inner_count` 是响应 envelope 的批处理层。`#33/#35/#30` 中 outer group 数与请求 command 数一致；`#29/#31` 显示一个请求也可返回多个 response packet。
- `response_long0` 与 request command 的 `dm` 完全一致，当前高置信命名为 `session_id/dm_candidate`；`response_long1` 随 packet 变化，像服务端时间或包序列。
- `0x1113 -> 0x8113` 在 `Lo/a.A6` 中存在分支但无直接 handler，且 payload 长度为 0；当前可视为进入阶段的空 ack/心跳式响应。
- `0x1008 -> 0x8008 + 0x800d` 是 cacheData/城池地图缓存初始化关键链路，后续若做二级 parser 应优先展开这两个大 payload。
- `0x6200 -> 0xe200` 多次与其他请求批量出现，对应 `gameHD/a.h`，属于进入后后页/联网数据刷新链路。

## 8. 输出文件

- flow 摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/protocol_envelope_flow_summary.csv`
- request command 明细：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/protocol_envelope_request_commands.csv`
- response packet 明细：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/protocol_envelope_response_packets.csv`
- 进服最小合同：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/protocol_entry_minimal_contract.csv`
- 静态反汇编证据：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/protocol_envelope_disasm.txt`
- 机器摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/client_understanding/protocol_envelope_summary.json`
- 自动化脚本：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/scripts/extract_protocol_envelope_contract.py`

## 9. 仍需继续

1. 展开 `0x8004`、`0x8008`、`0x800d`、`0x8104`、`0x8130`、`0xe200` 的二级 parser 字段语义。
2. 用更多进服/切区/重连样本验证 `dm/gm/long1` 的最终命名。
3. 若捕获到 `obfuscation_flag=1`，再用 `Lo/a.o()` key 与 `Lo/a.P()` 做 payload 解密验证。
