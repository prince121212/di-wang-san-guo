# 三国·帝王联盟 本地服务端重建骨架

这是基于 APK 离线逆向线索生成的 **本地协议兼容/恢复起点**，不是完整游戏服务器。

## 运行

```bash
cd /Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/server_rebuild
python3 diwang_stub_server.py --host 127.0.0.1 --port 8080
```

打开：`http://127.0.0.1:8080/`

## 已覆盖的端点类别

- 启动配置：`/client.action`、`/gateway/access-url.action`
- 区服列表：`/type/list.action`、`/area/list.action`、`/area/type.action`
- 账号：`/user/register.action`、`/user/validate.action`、`/user/password.action`、验证码类接口
- 游戏进入：`/game/activate.action`、`/game/role.action`、`/game/enter.action`、`/area/enter.action`
- 资源：`/game/script/`、`/game/data/`、`/game/music/`
- 公告、设备、实名、活动、充值 stub

## 请求日志

所有客户端请求会记录到：

```text
/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/server_rebuild/logs/requests.jsonl
```

后续可以根据日志逐个补齐字段格式。

## 让 APK 指向本地服务的思路

优先建议不改原 APK：在模拟器/测试机里通过 hosts/DNS/代理把以下域名指向本机或局域网机器：

- `king9.cn`
- `sglmpass.3gking.net`
- `139g.gameboxapi.net`
- `resource.3gking.net`
- 以及 DEX 字符串里的 `dxt11v13g.3gking.net`

如果 HTTPS 证书校验阻碍 `sglmpass.3gking.net:12443`，可在后续制作“本地测试版 APK”：只替换 `assets/script/defautConfig.properties` 里的 passport/gw/res URL 到 `http://127.0.0.1:8080/` 或局域网 IP。

## TCP 游戏服探针

APK 里出现过 `dxt11v13g.3gking.net:25511`，因此 HTTP 登录后可能会连接 TCP 游戏服。先启动探针记录二进制包：

```bash
cd /Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/server_rebuild
python3 diwang_tcp_probe_server.py --host 0.0.0.0 --port 25511
```

日志：

```text
/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/server_rebuild/logs/tcp_packets.jsonl
```
