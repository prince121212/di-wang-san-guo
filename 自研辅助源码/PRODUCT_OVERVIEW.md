# 帝王三国手机端辅助 V1 产品说明

> 产品形态：Android 手机本地辅助
>
> 文档状态：与 2026-07-29 当前代码一致
>
> 版本标识：`V0.0.15`

## 1. 产品定义

手机端是独立执行核心，不是电脑端遥控器。电脑关机、电脑端辅助未启动、两台设备不在同一网络时，手机仍可独立完成本地账号登录、设置保存、任务调度、游戏请求、运行状态和地图管理。

正式运行链路只有一条：

```text
APK 内单容器页面
  → 本机异步 AssistantApi 桥
  → Kotlin 本地核心
  → AssistantForegroundService
  → 串行 TaskScheduler
  → 统一出征预检与事务账本
  → 手机直连游戏服务器
```

V1 不包含电脑 Mobile API、电脑地图同步、云协作地图、App 内代理、VPN、IP 检测或节点管理。

## 2. 设计原则

- 极简架构：一个正式 Activity、一个前台服务、一个调度所有者、一条协议出口。
- 单一职责：页面只展示和发命令；Repository 只负责本地事实；调度器只编排；协议层只负责游戏通信。
- 默认失败关闭：缺少真实 Session、协议 gate 或可核验响应时返回失败，不用 mock、dry-run 或推测结果冒充成功。
- 同步保护关键写入：凭据、Session 秘密、托管开关、运行截止时间和出征事务必须确认落盘。
- 低功耗：按最近任务期限唤醒；长等待释放 WakeLock，并交给系统可合并闹钟。
- 无重复事实源：账号、配置、运行状态、日志、完成锁和本地地图分别只有一个持久化所有者。

## 3. 模块职责

| 模块 | 唯一职责 |
|---|---|
| `AssistantWebActivity` | 加载 APK 内页面，限制导航和子资源来源 |
| `AssistantWebBridge` | 在单工作线程串行转发本机 API，结果回投页面线程 |
| `LocalAssistantApiController` | 本机 API 白名单、参数校验和用户命令入口 |
| `DebugCommandProvider` / `tools/mobile_debug.py` | Debug APK 的通用 ADB 转发、身份校验、日志、状态与快照；不实现业务逻辑 |
| `LocalAccountLoginService` | 真实登录与账号落库事务 |
| `AccountSessionRecovery` | 网络变化、Session 校验、退避和重新登录 |
| `AssistantForegroundService` | 唯一后台宿主、网络监听和按期限调度 |
| `TaskFactory` | 只从用户已保存配置创建正式任务 |
| `ExpeditionPreflight` | 所有出征共用的 Session、将领、体力、忠诚、兵种和兵力检查 |
| `ExpeditionTransactionRepository` | 发送前记录 `SENDING`，回执不明时阻止自动重发 |
| `SessionAwareGameProtocolClient` | 真实 Session 协议边界与失败关闭 |
| `LocalMapRepository` / `LocalTargetCache` | 本机山贼和资源点冷存储/热缓存 |

## 4. 当前能力

### 4.1 已完成的本地基础闭环

- 本地添加账号、真实登录、Session 保存、启停和删除。
- Session 失效自动重登；网络恢复后先刷新真实状态，再恢复任务。
- 每账号配置、最近请求健康、每日成功次数、完成锁和下一次运行时间持久化。
- 日志使用有界 JSONL 追加存储和单调游标；成功记录使用结构化事实字段，不再从日志文字猜测。
- Activity/WebView 与任务生命周期分离；用户启动后由前台服务持有调度。
- 手机本地山贼、资源点扫描结果缓存、失效清理和目标复核。
- 页面手动操作与后台调度共用账号锁；同账号不并发发包，不同账号可以独立执行，请求健康记录不串账。
- 停止、掉线或服务未接管时，持久化 Session 只用于重登，不向页面呈现为可执行 Session。
- 登录时缓存自有封地坐标；刷黄推荐中心按所选将领所在封地多数计算，缺坐标明确失败，不使用固定假坐标。

### 4.2 正式任务边界

任务工厂可按保存配置创建配兵、刷黄、打矿、副本、无损、掠夺、背包、军情、内政、金银花种植及七项日常任务。副本、刷黄、无损、掠夺和打矿统一经过出征预检与事务账本。

电脑端单账号逻辑已经落实到同一行为契约：竞技币以中国时区 22:00 为每日周期，其余日常以 00:00 为周期；服务器“已领取/重复领取”回执按完成处理；国民跳过俸禄、国家征收和名将拜访；内政一次尽量填满可用建筑/科技队列，成本来自实时封地状态；军情按活动状态和剩余时间排序，“仅日志”不会触发声音或振动。

协议代码和单元测试已覆盖上述任务的正式成功、失败、重试和停止路径，但“代码路径存在”不等于“每个功能都已有本轮真机动作证据”。真实响应缺少必要证据时，生产协议层必须返回错误。

当前范围只延期以下四项，界面置灰，API 也会失败关闭：

- 抢城。
- 押镖。
- 寻宝。
- 连体物品整理。

六部只发送已经确认的金银花种植；收菜、偷菜和礼部等未确认子动作不会发送。电脑版单账号界面中同样禁用的建筑加速、俘虏处理等控件保持禁用，不作为开放功能制造假成功。

除真机回归外，开放功能的代码、协议形状、调度、存储、页面语义和离线测试已对齐。刷黄已有历史真机闭环证据；其余开放任务仍需按功能逐一补齐当前版本的真机动作证据后，才能声明完成全部 V1 真机验收。

## 5. 安全模型

- 用户添加账号后自动保存无人值守重登凭据，不增加额外确认步骤。
- 密码与 Session 认证字段分仓保存，使用 Android Keystore 管理的 AES-GCM 密钥。
- V2 Keystore 别名兼容旧密钥；旧密钥在设备解锁过渡期不可用时，安全降级为重新登录，不让 Activity 崩溃，也不保留明文。
- 账号 JSON 和导出只包含元数据、公开 Session 字段及 Keystore 占位标记，不包含密码、Token、`dm`、`userId`、Cookie 等认证秘密。
- 删除账号时先删除密码密文，再删除 Session 密文和账号元数据。
- 日志统一经过 `SensitiveDataRedactor`，屏蔽密码、Token、`dm`、`gameHttp`、Cookie 和 Bearer 值。
- `android:allowBackup=false`；WebView 禁用 Cookie、外部导航、外部子资源和混合内容。
- TLS 使用 Android 平台默认的证书链及主机名校验，不安装 trust-all TrustManager 或 HostnameVerifier。

## 6. 状态一致性与恢复

- 任务的 `Sleep`、`RetryAfter`、停止锁和服务停止状态保存绝对截止时间。
- 保存配置计算 SHA-256 签名；仅当签名一致时恢复旧截止时间，配置变化立即丢弃旧抑制状态。
- 每日任务次数和刷黄完成锁来自持久化仓库，不依赖每轮重建的 Task 对象。
- `activeResidentTaskKeys` 字段存在但为空时表示用户明确关闭全部常驻任务，不会被旧的“全部恢复”语义覆盖。
- 配置在线保存后立即更新相应常驻任务开关，页面返回的“已开始/等待账号启动”与调度状态一致。
- 出征先同步写入事务账本，再发送动作；超时或回执不明标记 `UNCERTAIN`，等待真实状态核对。
- 重启只恢复用户此前明确开启的托管，并等待设备首次解锁以使用 Keystore。

## 7. 性能与功耗

- APK 只打包共用前端的 `index.html`、`app.js`、`styles.css` 和 `assistant-api.js`，没有第二套手机页面。
- WebView 首屏读取本地 assets，不等待电脑、局域网服务或云端页面。
- 本机 API 使用单线程工作队列，避免阻塞页面主线程和并发写仓库。
- 调度按任务期限自适应；紧迫任务短间隔运行，长等待释放 WakeLock 并使用 `setAndAllowWhileIdle`。
- 本地地图使用有界热缓存和 TTL，空结果也短期缓存，避免无目标时密集扫描。

已有安全烟测记录的冷启动约 467 ms、完整绘制约 592 ms；该数字是特定设备上的一次证据，不作为所有设备的固定承诺。

## 8. UI 共享边界

电脑端与 Android 共用同一套容器前端：

- 电脑浏览器通过 HTTP 调用 `server.py`。
- Android 构建时把同一套静态文件复制进 APK，并由 `assistant-api.js` 将 `/api/*` 请求交给本机桥。
- 手机模式只保留单账号容器，移除电脑总控、多容器、地图工具页、一键全启和 IP/代理控件。

旧 `/api/v1/mobile/*` 仍可作为电脑端历史兼容接口存在，但不属于 Android V1 架构，也不是手机运行依赖。

## 9. 自动验证

Debug 构建还包含通用 ADB 调试入口：每次连接校验包名、版本、PID、UID 和 APK SHA-256，所有 API 请求直接进入现有 `LocalAssistantApiController`；Release 构建没有该 Provider。默认只允许 GET，POST 需要 CLI 与 Provider 双重显式确认。调试器可直接采集状态、中文日志和 JSON 快照，因此新增业务 API 后无需另写功能调试器。

2026-07-29 本轮自动验证结果：

- Android JVM 单测：567 项，0 失败、0 错误、0 跳过。
- 通用手机调试器 Python 单测：10 项，0 失败。
- 共用前端 Python 单测：511 项，0 失败。
- JavaScript 语法检查通过。
- Debug APK、Release Kotlin 编译通过。
- V1 `--skip-device` 离线静态/构建审计通过，覆盖本地架构、TLS、Keystore、脱敏、权限通知、状态恢复、账号互斥、结构化日志、延期动作和 APK Manifest；脚本未调用 ADB。

执行命令：

```bash
cd "/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/自研辅助源码"
export JAVA_HOME="$HOME/.cache/codex-jdks/zulu17/zulu-17.jdk/Contents/Home"
./gradlew testDebugUnitTest assembleDebug compileReleaseKotlin
python3 -m unittest tools.test_mobile_debug -v
python3 tools/verify_v1_coverage.py --skip-device

cd "../电脑端辅助前端"
python3 -m unittest discover -s tests -q
node --check app.js
```

审计报告：

```text
自研辅助源码/reports/v1_coverage_report.md
```

## 10. 尚需授权的真机验收

以下项目不能由静态检查或单元测试替代，未执行前不得把 15 条 V1 验收标准标记为全部完成：

1. 副本、刷黄、无损、掠夺和打矿逐功能真实动作证据。
2. 锁屏连续运行超过 6 小时。
3. Wi-Fi/移动数据切换、短时断网和真实 Session 过期恢复。
4. Activity/WebView 关闭后托管继续运行。
5. 手机重启并首次解锁后的托管恢复。
6. 真实托管期间抓包确认只访问游戏服务器。

这些测试可能发送游戏动作、消耗账号资源或改变设备网络/运行状态，必须在用户明确授权测试账号与范围后执行。
