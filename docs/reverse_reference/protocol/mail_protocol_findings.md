# 邮件/消息/客服补发相关协议离线逆向结果

## 结论摘要

从客户端 `original_classes_1.dex` 中离线搜索 `邮件/附件/领取/客服/系统邮件/消息` 相关字符串和引用方法后，当前没有发现明确的“邮件附件领取 / claim mail attachment / receive mail reward”专用协议。

已发现的邮件/消息相关协议主要是：消息/战报详情读取、删除/标记已读、发送玩家邮件、发送客服问题、客服 FAQ。

这与动态抓包观察一致：山贼/战报奖励是服务端结算时自动到账，客户端后续 `0x1114`/`0x111f` 只是读取详情。

## 已识别协议

| 命令 | 十进制 | 客户端方法 | 请求名 | 参数结构 | 用途判断 | 风险点 |
|---:|---:|---|---|---|---|---|
| `0x1114` | 4372 | `LscriptPages/game/h0;->Z(J)V` | `reqCheckMsg` | `long message/report id` | 消息/战报/战利品详情读取 | 已验证可重放但只读，不重复发奖 |
| `0x1116` | 4374 | `LscriptPages/game/h0;->b0(I I J)V` | `reqDelMsg` | `byte action + byte box/type + long id` | 删除/标记消息或邮件 | 状态变更，可重放但不涉及奖励发放 |
| `0x1118` | 4376 | `LscriptPages/game/h0;->g0(I,String,String,String)V` | `reqSendMsg` | `byte type + UTF receiver + UTF title + UTF content` | 玩家发邮件/消息 | 重放可能导致重复发送消息，不是奖励漏洞 |
| `0x111f` | 4383 | 动态抓包观察 | 未命名 | `long report id` | 战役结果详情读取 | 已自然重复出现两次，表现为只读 |
| `0x6232` | 25138 | `LscriptPages/game/h0;->h()V` 内 | `CSFAQLIST` | `long faq/customer id` | 客服 FAQ/客服问题列表 | 只读/客服相关 |
| `0x6234` | 25140 | `LscriptPages/game/h0;->b(B,J,String,String,String,String)V` | `CSSendNewMail` | `byte + long + UTF*4` | 发送客服问题/客服邮件 | 重放可能重复提交客服问题，不是领取奖励 |
| `0x180a` | 6154 | `LscriptPages/game/h0;->l()V` 内 | 未命名 | `byte[1]` | 可能是邮箱/发件箱初始化或列表请求 | 需要动态样本确认 |

## 关键证据

### 1. `0x1114 / reqCheckMsg`

文件：`method_disasm/scriptPages_game_h0__Z__0x3b057c.smali.txt`

```text
const-string v5, "reqCheckMsg"
const/16    v6, 4372
invoke-static ..., Lk/a;->r(..., J, ..., S)V
```

动态验证：

```text
1114000019f2e92b1ec0f868
```

返回战利品详情，但用户确认不会重复到账。

### 2. `0x1116 / reqDelMsg`

文件：`method_disasm/scriptPages_game_h0__b0__0x3b0be8.smali.txt`

```text
const-string v0, "reqDelMsg"
writeByte(action)
writeByte(box/type)
writeLong(id)
const/16 v2, 4374
Lo/a;->d0(S, [B)
```

调用点包含：

```text
di_联网删某消息
di_联网删某邮件
```

说明它是删除/标记类状态变更接口，不是领奖接口。

### 3. `0x1118 / reqSendMsg`

文件：`method_disasm/scriptPages_game_h0__g0__0x3b0e38.smali.txt`

```text
const-string v0, "reqSendMsg"
writeByte(type)
writeUTF(receiver)
writeUTF(title)
writeUTF(content)
const/16 v2, 4376
Lo/a;->d0(S, [B)
```

### 4. `0x6234 / CSSendNewMail`

文件：`method_disasm/scriptPages_game_h0__b__0x3a6080.smali.txt`

```text
const-string v0, "CSSendNewMail"
writeByte(...)
writeLong(...)
writeUTF(...)
writeUTF(...)
writeUTF(...)
writeUTF(...)
const/16 v2, 25140
Lo/a;->d0(S, [B)
```

字符串提示：

```text
di_发送客服问题中
```

判断为发送客服问题/客服邮件，不是客服补发奖励领取。

## 对“客服补发邮件”的判断

当前客户端证据更支持以下模型：

1. 客服补发如果发的是道具/资源，大概率由服务端直接写入宝库/资源；
2. 客户端收到的只是系统消息/邮件/战报详情；
3. 详情读取协议 `0x1114` 已实测只读，不会重复发奖；
4. 客户端未发现明确“附件领取”协议和“附件”UI 字符串。

因此，在无法触发真实客服补发邮件的前提下，暂时没有可验证的“客服补发奖励重放”入口。

## 仍需动态样本确认的情况

如果后续能拿到以下任一真实样本，需要重新验证：

- 未读系统补偿邮件；
- 充值到账邮件；
- 客服补发道具邮件；
- 带按钮的“领取附件/领取奖励”邮件。

如果这类邮件仍然只触发 `0x1114/0x111f` 详情读取，则基本可判定为只读；如果出现新的命令号，则需要单独审计。

## 产物

- 字符串引用：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/vuln_shop/mail_protocol_reverse/mail_string_refs.md`
- 方法摘要：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/vuln_shop/mail_protocol_reverse/mail_method_summary.md`
- 关键反汇编：`/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/vuln_shop/mail_protocol_reverse/method_disasm/`
