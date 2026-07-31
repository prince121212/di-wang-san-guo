# 阶段 6：账号、Session、状态与存储迁移记录

> 状态：已完成
>
> 开始日期：2026-07-31
>
> 完成日期：2026-07-31

## 本阶段边界

本阶段统一所有功能共同依赖的账号生命周期、Session 可用性门禁、失败分类、重试节奏和非敏感账号状态。验证仅使用单元测试、离线 fixture、Debug Provider 只读调用和不访问网络的模拟 operation。

本阶段没有登录账号、没有启动真实任务、没有访问游戏服务器，也没有发送任何真实游戏动作。

## 共享账号生命周期

唯一共享 Python 核心现已拥有：

- 用户启动、用户停止、登录成功和登录失败状态转换。
- Session 探测成功、过期、网络不可用和进程恢复状态转换。
- Session 是否允许发包的统一门禁。
- 网络、服务器、限流和未知失败的分类与分类退避。
- `desiredStarted`、失败次数、未来重试 deadline、最后错误和下一操作语义。

Android 通过类型化 `AccountStateTransitionSource` 和 `AccountLifecycleDecisionSource` 调用共享 reducer；账号卡展示、手动发包门禁和 Session 恢复器不再各自维护 Kotlin 判断表。电脑端启动、在线、停止的主时间线也调用同一 reducer。

未知历史登录状态按失败关闭处理为离线，不能因为迁移或恢复而默认在线。

## 非敏感账号账本与秘密端口

共享核心的 `accounts-v1.json` 是非敏感账号元数据和完整业务状态的唯一账本：

- Android 旧 SharedPreferences 账号记录只做一次性导入，并保留为已脱敏回退。
- 页面只读取轻量展示投影；恢复和任务逻辑仍可读取完整非敏感状态。
- 密码只能通过 `CredentialPort` 取得。
- Session 的 `dm`、Token、Cookie、用户标识和签名只能通过 `SessionSecretPort` 取得。
- Android 的两个秘密端口分别连接独立 Android Keystore AES-GCM 存储。
- 账号账本和 operation 账本均拒绝敏感字段进入。

当前真机账号账本约 2.32 MB，主要体积来自旧 `formationsJson` 等完整业务恢复数据。展示投影不会携带这些大字段，因此没有为追求页面速度而删除恢复所需事实。

## 进程恢复安全边界

`AssistantForegroundService.onCreate()` 会调用 `prepareProcessRecovery()`，将每个持久化账号作为 `PROCESS_RECOVERED` 事件交给共享状态机。该步骤只写入共享 reducer 返回的状态，不直接登录、探测 Session、启动调度器或发送游戏请求。

为此新增了纯离线 `AccountProcessRecoveryCoordinator`：它只依赖账号快照、重连快照和共享状态转换源，类型上不具备登录、协议、探测或调度能力。假仓库测试证明：

- 未来的 `nextRetryAtMillis` 在进程恢复后保持不变。
- `desiredStarted` 保持用户原意。
- 恢复后的 live Session 默认不可用，必须经过后续真实验证。
- 已停止账号仍保持停止，不会因进程重建自动启动。

## 真机只读与离线验证

设备 `27a83c9c` 安装了与本地 SHA-256 完全一致的最新 Debug APK。安装和校验没有打开 Activity，也没有启动 `AssistantForegroundService`。

只读结果：

- APK SHA-256：`2b2b55c1d16caf3f557b968799b7436b509d44ffe8e94e0e2c726852d0fa8877`
- 共享核心哈希：`043adaad937bfab79c6b57f6b4ea15b0be007b627f6d247eb5804405311bc025`
- 共享核心版本：`0.2.0`
- Android Python：`3.10.19`
- Python 启动：194 ms
- 核心初始化：172 ms
- 协议、规则、生命周期和类型化状态转换离线断言：110/110
- `USER_START` 类型化转换：`REAL_PROTOCOL_CHECKING`、`nextOperation=login`、`liveSessionUsable=false`

## 90 秒通道隔离复测

最新 APK 提交了一个明确不访问网络的 90 秒模拟 operation。在其处于 `RUNNING` 时，对六条本地路径各读取 8 次；测试结束后 operation 已取消为 `CANCELLED`，活动 operation 数为 0。

| 本地路径 | 控制器 P50 | 控制器 P95/P99 |
|---|---:|---:|
| 账号列表 | 14.78 ms | 17.88 ms |
| 设置读取 | 14.57 ms | 18.21 ms |
| 调度状态 | 20.20 ms | 27.73 ms |
| 账号日志 | 6.73 ms | 8.46 ms |
| 地图缓存 | 4.90 ms | 51.60 ms |
| operation 状态 | 2.70 ms | 6.21 ms |

所有本地控制器路径均低于规划的热态 P95 100 ms 目标，并且没有排在长任务之后。这里记录的是 App 进程内控制器耗时；ADB `content call` 自身约一秒的 shell 往返不代表 WebView Bridge 或用户界面耗时。阶段 7 仍需在真实 WebView 调用链上测量点击反馈、本地保存落盘和网络 operation 受理。

本轮没有用真实账号配置执行 `POST /api/settings/save`，避免为了测试改动用户设置。本地保存的最终响应指标将在阶段 7 切换设置路由时使用隔离测试数据正式验收。

## 真机存储安全审计

只读取文件结构和字段类别，不输出秘密值：

| 存储 | 结果 |
|---|---|
| `accounts-v1.json` | 1 条、2,319,796 字节、敏感字段 0 |
| `operations-v1.json` | 4 条、敏感字段 0 |
| `operations-v2.json` | 5 条、敏感字段 0 |
| 密码 Keystore SharedPreferences | 1 条，全部为 `v1:<12-byte-IV>:<ciphertext>` AES-GCM envelope |
| Session 秘密 SharedPreferences | 1 条，全部为 AES-GCM envelope |
| 9 个非秘密 SharedPreferences | 只有一个旧 `tokenCiphertext` 字段，值为 `keystore-managed-login` 标记；明文敏感值 0 |
| 任务日志 | 344,278 字节，敏感赋值与 Bearer 命中均为 0 |

`gameAuthSignEvidence` 只允许已知的非秘密验证标签；本轮未知证据值为 0。

## 回归结果

- 电脑端 Python：622 项测试全部通过。
- 电脑端 `app.js`：Node.js 语法检查通过。
- Android JVM：581 项测试、0 失败、0 错误、0 跳过；使用 `--rerun-tasks` 强制完整执行。
- Android `compileReleaseKotlin`：通过。
- 新增的进程恢复假仓库测试：2 项通过。
- 真机共享核心离线断言：110/110 通过。

## 阶段验收结论

阶段 6 的 G6 门槛已经满足：

- 电脑端账号行为回归通过。
- Android 离线账号状态转换由同一共享 Python 状态机决定。
- Android 密码与 Session 秘密继续留在 Keystore，非敏感账本和日志没有明文回归。
- 进程恢复只落状态且保留退避，不会从 `Service.onCreate()` 直接发包。
- 未经用户授权没有进行真机登录。

阶段 6 完成，可以进入阶段 7。

## 阶段 7 前仍存在的边界

当前正式共享路由所有者仍只有 `GET /api/health`。`AssistantWebBridge` 仍使用一条 Kotlin executor，其他本地和网络接口大多仍由旧 Kotlin Controller 执行。

因此不能宣称“手机核心响应失败”已经从所有路径彻底消失。阶段 7 必须先拆分本地、事件和按账号网络通道，先迁移并验收本地接口，再以军情刷新建立第一个真实网络异步样板。
