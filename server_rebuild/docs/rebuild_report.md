# 三国·帝王联盟 服务端重建阶段报告

## 当前结论

仅凭 APK 可以重建一个“可迭代的兼容服务端骨架”，但不能一次性还原完整线上服务端逻辑。原因：客户端包含端点、资源、协议名和部分默认配置；完整战斗、经济、地图、状态推进逻辑原本在服务端，APK 内只能恢复接口调用方式和客户端期望的数据形状。

## 已恢复/可用资产

- APK 已脱壳，真实 DEX：`reverse_cases/apk-sanguo-diwanglianmeng-166/recovered/original_classes_1.dex`
- 客户端脚本/资源已提取到：`server_rebuild/public/game/`
- 本地 HTTP stub server：`server_rebuild/diwang_stub_server.py`
- TCP 协议探针：`server_rebuild/diwang_tcp_probe_server.py`
- 协议线索：`reverse_cases/apk-sanguo-diwanglianmeng-166/analysis/server_rebuild/protocol_clues.md`

## 关键端点线索

启动/区服：

- `/client.action?channel=`
- `/gateway/access-url.action?identity=`
- `/type/list.action?clientType=`
- `/area/list.action?`
- `/area/enter.action?session=`

账号/登录：

- `/user/register.action?`
- `/user/validate.action?session=`
- `/user/password.action?username=`
- `/user/reset-password.action?channelId=`
- `/system/user/loginCaptcha.action?email=`
- `/system/user/validateInfo.action?`

游戏进入：

- `/game/activate.action?channel=`
- `/game/loading.action?channel=`
- `/game/role.action?channel=`
- `/game/enter.action?channelCode=`

资源：

- `/game/res/`
- `/game/script/`
- `/game/dynamics/`

充值/商城 stub：

- `/charge/order.action?session=`
- `/asset/charge/dagedaChargeList.action?`
- `/mol/charge/purchase.action?`

## 重建策略

1. 先用 HTTP stub 让客户端通过启动、登录、区服列表、角色列表流程。
2. 用请求日志补齐每个接口的字段名和返回格式。
3. 若客户端进入游戏后连接 `:25511`，用 TCP 探针记录二进制包，再恢复包头、命令号、长度、加密/压缩。
4. 先实现“单机/沙盒服”：账号、角色、资源、背包、商城、地图静态数据。
5. 再逐步实现：建筑、出征、战斗、国家、军团、聊天、活动等服务端状态机。

## 本阶段可运行命令

```bash
cd /Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/server_rebuild
python3 diwang_stub_server.py --host 0.0.0.0 --port 8080
python3 diwang_tcp_probe_server.py --host 0.0.0.0 --port 25511
```

## APK 指向本地服务的方案

优先用测试环境 DNS/hosts/代理转发：

- `king9.cn -> 本机/局域网 IP`
- `resource.3gking.net -> 本机/局域网 IP`
- `139g.gameboxapi.net -> 本机/局域网 IP`
- `sglmpass.3gking.net -> 本机/局域网 IP`
- `dxt11v13g.3gking.net -> 本机/局域网 IP`

如果 HTTPS passport 证书阻碍，则制作本地测试版 APK，把 `assets/script/defautConfig.properties` 中 `channel.gw`、`channel.passport` 改到本地 HTTP 地址。
