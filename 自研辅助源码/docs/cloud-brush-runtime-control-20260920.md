# V108：云端刷黄地图控制

## 实现

- 后台顶部开关：`/admin/api/runtime-config`，管理员 Cookie、Origin、自定义意图头、
  严格布尔值、expectedRevision 防止过期页面覆盖；默认开启保持既有策略。
- 独立 SQLite-backed DO `RuntimeConfigStore`，随 `runtime-config-v1` migration
  创建，不新增 D1 表。管理员登录限流同样不使用地图 D1，原限流门槛及 Cookie
  签名机制保持；控制面在 D1 无法读写时仍可用。
- 客户端只读 `POST /v1/client/config`；每次启动/重登账号强制读取，进程重启后
  每账号首次调度读取一次，手动刷黄首次使用同样先读取。并发首次读取合并。
- 配置失败沿用最后有效值，无缓存默认本地；配置持久化在账号公开状态内，
  不上传游戏账号密码或 Session。Android 固定路径白名单加入配置接口。
- 关闭优先于共享模式及故障重试：本地地图、同服原子目标互斥照常，停止云端
  地图请求/在线心跳及新增上传队列；原上传队列、出征账本不清空、不重发。
- Worker 在 D1 访问前拦截关闭期间的山贼请求，明确返回
  `CLOUD_BRUSH_MAP_DISABLED`；新客户端发送前只允许一次切本地，越过游戏
  发送边界后不重试。启用后在下次启动账号读取，允许立即探测真实云端可用性。
- 仅移除旧刷黄 cloud-map 等待，不移除在途/未知账本或其他业务等待。打矿不变。

## 本地验证

- 全量 Python/前端 1361 项通过（新增配置专项 11 项）。
- Worker 79 项、TypeScript 检查通过，含关闭/开启、鉴权、同源、版本冲突、
  D1 全故障时登录/控制仍可用及旧客户端被拒绝。
- Android 583 项通过；`testDebugUnitTest assembleDebug compileReleaseKotlin` 成功。
- 已构建 `app/build/outputs/apk/debug/app-debug.apk`，版本 V0.0.108。

## 发布与真机验收完成（2026-09-20）

用户明确提供本机“认证相关”目录后，使用其中的账号级 API 凭据发布。
未将管理凭据复制进项目或 APK。最终 Worker 版本：
`5f03b8c6-7b92-4ddb-9cd2-19b8922d2dcb`，`wrangler versions deploy` 确认 100% 流量。

首次常规 deploy 已上传代码，但后续域名路由检查因凭据没有 zone route 权限失败。
改用 versions upload/deploy，仅更新 Worker 版本，保留既有自定义域名及
`*/30 * * * *` Cron；未要求额外权限，也未更改 DNS/路由。正式域名的页面和
配置接口均验证成功。

### 构建凭据检查

安装前发现新构建的 Runtime Token 为空。对用户自研、手机现有 V107 APK 的
`com.example.dwpmclone.BuildConfig` 用 SDK apkanalyzer 做只读检查，发现其字段
也为空；未读取游戏密码或 Session，未修改旧包。原包 SHA-256：
`114766cf627f72a1e1bae504f908c57f9327bcd42bdf9c090f8c1378603b8b1a`。

因此新增独立的 `CLIENT_API_TOKEN_V2`，保留云端原 `CLIENT_API_TOKEN`，保证
既有安装仍可访问。新令牌仅用于共享数据接口，不能修改管理员开关；测试覆盖
新旧凭据并存及两者均无管理员写权限。运行凭据保存到本机专用钥匙串项供构建使用，
没有写入源码或文档。配置接口实测返回 `ok=true`、`cloudBrushMapEnabled=true`、
`revision=0`；没有为了验收切换线上全局开关。

### 手机

已保留数据覆盖安装 V0.0.108/versionCode 108 到 ADB `27a83c9c`。
设备 APK 与构建件 SHA-256 一致：
`a716ecfb0ee05ebb4801329a3ac7b4d194857316ac15c9ede565c9fb216d705b`。
49 个 Python/契约文件一致，健康接口 coreHash：
`92ff06abde8aeea25317b41f974182dbcc3b97e90336626ddb91a3984c7324cc`。

- 202 于 20:35:02、176 于 20:35:03 启动读取成功，均为 `source=cloud`、开启、版本 0。
- 两个启用账号的配置哈希、启停及任务键与安装前一致；764 保持禁用且未拉取配置。
- 202 原打矿/刷黄账本继续恢复；20:35:30 副本完成，20:35:33 有新物品丢弃记录。
- 关闭/开启、断网、并发首次拉取、旧等待解除和出征不重发由回归测试验证；
  不将未切换线上全局策略的现场冒充生产关闭测试。

正式后台：`https://dwpm-data.292828.xyz/admin/`。已在 Chrome 新标签页导航，
确认窗口标题为“共享数据管理 · 帝王三国”；没有代用户输入线上管理员密码或切换全局策略。
未提交工作区的既有或本轮改动。
