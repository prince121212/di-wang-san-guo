# 电脑端与 Android 共享 Python 核心迁移规划

> 文档状态：执行中（阶段 0–6 已完成；阶段 7–10 执行中；阶段 11 未开始）
>
> 制定日期：2026-07-31
>
> 最近更新：2026-08-02（`V0.0.19` 已补齐 758 条共享道具名称并修复 0x8104 固定表误解析；内置“网络操作”状态托盘已隐藏但异步 operation 机制保留；829 项 Python、482 项 Android 回归、Debug/Release Kotlin 构建与 V1 静态审计通过，新 APK 已覆盖安装）
>
> 核心策略：保留已验证的电脑端行为，通过“抽离而非重写”形成唯一 Python 业务核心；电脑端和 Android 只保留各自的平台宿主层。

## 0.1 迁移口径（简化执行版）

本项目不是重新开发一套 Android 辅助，也不是把 Python 业务规则翻译成 Kotlin。核心工作只有四件事：

1. **同源打包**：把 `shared_core/python/dwpm_core` 作为唯一源码，在电脑端直接导入，在 APK 构建时自动打包；不再复制或改写业务函数。
2. **薄宿主接入**：Android 只提供 Raw HTTP、Keystore、本地文件、日志、通知和唤醒等平台能力；Python 决定 opcode、参数、流程和成功判定。
3. **逐路由切换**：把 Android 现有入口逐个改成调用 `CoreFacade`/operation。迁移顺序是“替换调用方”，不是“重新实现功能”。
4. **关闭旧发包权**：共享 Python 通过回归验证后，删除或禁用对应 Kotlin 的协议、成功判断和后台发包逻辑，避免两套代码同时执行。

文档后续阶段 0–11 只是风险控制和验收标签，不代表要重新写 11 次功能。已经完成的基础设施不重复做；剩余工作按“功能切换 → 回归 → 关闭旧实现”循环推进。

### 不属于本次工作的内容

- 不重新设计前端，不改变现有页面交互。
- 不把电脑端 Python 业务再翻译一份 Kotlin。
- 不为 Android 维护第二份可编辑 Python 核心。
- 不先做微服务、跨设备通信或复杂重构。

### 为什么仍需要少量宿主工作

这些工作不是业务重写，而是运行环境适配：Android 不能直接使用电脑端的进程、路径、代理和明文凭据；同时必须保证旧 Kotlin 不会和 Python 重复发包，并在进程重启或网络回执不明时避免重复动作。它们只解决“同一份代码能安全地在手机上运行”，不改变业务规则。

## 1. 最终目标

电脑端与 Android 对同一个功能、同一份配置、同一份服务器响应，必须经过同一份业务代码，并得到相同的：

- 请求 opcode 与 payload。
- 协议解析结果。
- 任务选择、优先级和下一步动作。
- 成功、失败、重试与停止判定。
- 持久化业务状态、日志事实和完成次数。

最终结构：

```text
共享前端（现有 index.html / app.js / styles.css / assistant-api.js）
                         │
              统一 Core API 请求模型
                         │
              shared_core/python/dwpm_core
     登录 / 协议 / 功能流程 / 状态机 / 调度 / 结果语义
                   ┌─────┴─────┐
                   │           │
             电脑端宿主     Android Kotlin 宿主
             HTTP/多容器     WebView/前台服务
             代理/起号       Keystore/通知/唤醒
```

## 2. 不可违反的原则

1. 业务源码只能有一份，禁止在 Android 目录手工复制一份可编辑的 Python 核心。
2. Android APK 可以包含构建时生成的核心副本，但来源必须固定为仓库中的唯一共享目录。
3. 不重新翻译已经有效的电脑端业务代码；优先机械抽离、导入和委托。
4. 同一真实账号、同一功能、同一时刻只能有一个执行核心拥有发包权。
5. 迁移期间允许两套实现做离线对比，不允许两套实现同时发送真实动作。
6. 每一步先保证电脑端不退化，再推进 Android。
7. 没有服务器明确成功证据时继续失败关闭，不为迁移方便制造假成功。
8. Android 密码和 Session 秘密继续使用 Keystore，不能沿用电脑端明文账号记录方式。
9. 先实现逻辑一致，再根据真实测量结果优化性能。
10. 用户点击、切页和打开弹窗必须立即得到界面反馈，不能等待核心或网络后才改变界面状态。
11. 本地设置、配置、日志和缓存状态的读写必须立即响应，不能排在游戏网络请求后面。
12. 只有确实依赖游戏服务器结果的操作允许等待；等待期间界面保持可操作并明确显示“请求中”。
13. 任一阶段未达到验收门槛，不进入下一阶段。

## 3. 目标目录

```text
帝王三国/
├── shared_core/
│   ├── assistant_behavior_contract.json
│   ├── feature_parity_matrix.json
│   ├── protocol_parity_fixtures.json
│   └── python/
│       ├── pyproject.toml
│       ├── dwpm_core/
│       │   ├── __init__.py
│       │   ├── version.py
│       │   ├── facade.py
│       │   ├── models.py
│       │   ├── ports.py
│       │   ├── account/
│       │   ├── protocol/
│       │   ├── features/
│       │   ├── scheduler/
│       │   ├── state/
│       │   └── persistence/
│       └── tests/
├── 电脑端辅助前端/
│   ├── server.py
│   └── desktop_adapter/
└── 自研辅助源码/
    └── app/src/main/
        ├── java/.../host/
        └── python/（仅构建生成，不手工编辑）
```

目录名称可以在落地时微调，但必须维持“共享核心不依赖任何宿主工程”的方向。

## 4. 代码边界

| 归属 | 包含内容 | 禁止包含 |
|---|---|---|
| 共享 Python 核心 | 登录流程、协议封包解析、功能流程、状态机、任务选择、重试和结果语义 | WebView、Activity、桌面窗口、Android 权限、Clash 进程 |
| 电脑端宿主 | HTTP Handler、多容器总控、起号工具、代理/IP、桌面路径、进程启动 | 复制一套刷黄/打矿等业务规则 |
| Android 宿主 | WebView 桥、前台服务、Keystore、通知、Alarm、WakeLock、网络变化、进程恢复 | opcode、协议解析器、任务业务规则、功能成功判定 |

共享核心通过少量平台接口使用宿主能力：

- `CredentialPort`：读取和删除凭据；Android 实现必须连接 Keystore。
- `DataDirectoryPort`：提供 App 私有数据目录或电脑数据目录。
- `ClockPort`：提供可测试的当前时间和时区。
- `NetworkStatePort`：报告网络是否可用，不参与业务决策翻译。
- `NotificationPort`：接收结构化通知事件，不决定何时算成功。
- `WakePort`：安排下一次系统唤醒，不保存第二套任务状态。
- `PlatformLogPort`：接收结构化日志事件并进行平台展示。

游戏协议、目标选择、重试原因、下一次业务执行时间都由共享核心决定。

## 5. 统一响应与异步任务模型

目标：界面立即反馈、本地操作立即完成、网络操作等待真实结果，但三者互不阻塞。

这里要区分两层“异步”：

- 所有核心调用都不得阻塞 WebView/UI 主线程。
- 只有依赖游戏服务器的操作才创建持久化异步任务；普通本地读写仍应快速返回最终结果，不能为了异步而排成长任务。

固定两种核心接口语义：

- 本地操作：完成真实读取或落盘后直接返回 `200 + 最终结果`，不创建 operation。
- 网络操作：校验并持久化任务后快速返回 `202 + operationId`，最终成败由游戏服务器结果决定。
- 任何既保存本地设置又可能触发网络的老接口，都必须拆成“本地保存”和“网络 operation”两个结果，不允许用一个请求串行等待。

### 5.1 三类响应

| 类型 | 示例 | 响应要求 |
|---|---|---|
| 界面交互 | 点击按钮、切页、展开、打开弹窗 | 前端立即改变视觉状态，不等待任何核心调用 |
| 本地操作 | 保存设置、读取配置、日志、任务状态、缓存快照 | 完成本地校验和持久化后立即返回，不发游戏请求 |
| 网络操作 | 登录、刷新军情、刷新真实状态、找黄、出征 | 立即进入“请求中”，由后台异步执行，等待游戏服务器真实完成或真实网络超时 |

三类结果的语义不能混用：

- 点击后可以立即显示按钮状态或“保存中”，但只有本地数据真实落盘后才能显示“已保存”。
- 网络操作创建成功只能显示“已受理/请求中”，不能提前显示“操作成功”。
- 游戏服务器返回明确结果后，才能显示网络操作成功或失败。

本地设置保存必须拆成两个结果：

```text
用户点击保存
  → 页面立即显示交互反馈，不冻结界面
  → local-write 立即校验并原子持久化本地配置
  → 页面显示“设置已保存”
  → 如配置需要启动或调整后台任务，再异步提交给任务引擎
  → 网络任务状态单独展示，不影响保存结果
```

禁止将“设置保存成功”与后续网络动作是否完成绑定在同一个阻塞请求中。

### 5.2 网络操作模型

网络操作使用持久化异步任务：

```text
页面提交网络操作
  → 页面立即显示“请求中”
  → CoreFacade 创建 operationId 并快速确认已受理
  → 每账号网络队列串行执行
  → 页面保持可操作，本地设置、日志和缓存照常使用
  → 游戏服务器返回后保存真实结果
  → 通过事件或 operation/status 更新页面
```

以“刷新军情”为例：页面立即显示“正在刷新军情”，实际数据可以等待游戏服务器返回；等待 40 秒不应被误报为“手机核心响应失败”。只有游戏网络层达到自己的真实超时或返回错误时，才显示“军情刷新失败”。

### 5.3 分通道执行

共享核心和宿主必须至少区分：

1. `local-read`：设置、日志、缓存快照和任务状态读取，可小并发，优先读内存快照。
2. `local-write`：设置与其他本地状态写入，单队列按提交顺序校验并原子落盘。
3. `network-lane(accountId)`：每个账号一条网络队列，手动操作和后台任务共用账号执行锁。
4. `event-lane`：推送操作进度、完成结果和通知，不参与业务决策。

`local-read` 和 `local-write` 只做本地工作，永远不等待网络、重试退避、账号网络锁或定时睡眠。

禁止使用一条全局单线程队列同时承载本地接口和长网络请求。不同账号可以独立等待网络，同一账号的真实动作必须串行。

### 5.4 超时、轮询和重复提交

1. 页面桥接超时只用于判断“请求是否成功提交给核心”，不能用来判断游戏动作失败。
2. 游戏请求超时由共享核心的网络策略决定，并返回明确的网络错误。
3. 页面关闭或重建后，未完成操作及其最终结果仍可通过 `operationId` 恢复。
4. 状态轮询必须合并；同一路由已有请求在途时不再排队。
5. 所有真实动作使用持久化幂等键；重复点击只返回同一个操作状态。
6. 动作尚未发送时可以取消；已经发送但回执不明时标记 `UNCERTAIN`，禁止自动重发。
7. 网络操作完成得再慢，也不能阻塞设置保存、日志、任务状态和其他纯本地接口。

### 5.5 可量化的响应目标

“立即响应”按用户感知和真实完成分别验收：

| 指标 | 目标 |
|---|---|
| 点击、切页、弹窗的视觉反馈 | 不等待桥接调用；目标 100ms 内可见 |
| 本地读取与本地设置保存 | 热态 P95 不超过 100ms、P99 不超过 200ms；保存成功表示已经真实落盘 |
| 网络操作受理 | P95 不超过 100ms，返回 `operationId` 后即释放桥接线程 |
| 网络操作完成 | 等待游戏服务器真实返回或共享核心的真实网络超时，不设置统一的 30 秒界面完成超时 |
| 隔离性 | 持续 90 秒的模拟网络任务期间，本地接口延迟目标不退化 |

冷启动时允许显示一次明确的“核心启动中”，但不得显示“手机核心响应失败”；核心就绪后必须达到上述热态指标。

## 6. 全程通用验收门槛

每一个迁移步骤都必须满足：

1. 电脑端 Python 测试全部通过。
2. `node --check app.js` 通过。
3. Android JVM 单元测试全部通过。
4. 共享协议 fixture 的请求字节与解析结果完全一致。
5. 电脑端已迁移接口的响应契约没有非预期变化。
6. 没有新增第二份可编辑业务源码。
7. 没有真实动作被两个核心重复发送。
8. 日志、配置和凭据中没有新增敏感明文。
9. 本地接口不排在网络任务后面，长网络任务不造成“核心响应失败”的假错误。
10. 本地设置保存与后续网络任务的结果已经分离。

阶段 0 原始基线（2026-07-31，保留作历史对照）：

- 电脑端：511 项测试通过，JavaScript 语法检查通过。
- Android：Gradle 测试报告 579 项，0 失败、0 错误。
- 当时的未提交改动已在阶段 0 中完成清点，并已建立迁移分支和可恢复检查点。

当前回归快照（阶段 7–10）：

- 电脑端 Python：本次全量复跑 829 项，全部通过。自动背包的安全边界与军情警报回归全部保留；新增宝物解析回归覆盖 APK 内置 758 条完整道具表、真实历史 0x8104 抓包、固定 12 字节对齐、未知道具占位和装备尾表继续解析。
- 电脑端日志根因已修复：游戏 `dm` 是有符号 64 位值，合法负数现在只按 `dm != 0` 判定；`dm=0` 仍失败关闭。Session 暂不可用统一使用 5 分钟退避；设置保存不再把 `accepted/queuedKeys` 当作日常失败结果，静态资源断开连接也不再打印无意义堆栈。当前在线服务未为此重启，避免修复生效后自动触发真实任务；需在账号安全停止后再做运行态复验。
- 十类常驻任务（刷黄、打矿、掠夺、无损、副本、将领维护、六部、自动内政、自动背包、军情警报）及七类日常任务已进入同一共享调度。自动背包保持单 tick 单 mutation；军情警报每 30 秒使用共享 `0x1600/0x8600` 快照，所有去重和通知决策持久化在 Python 账本。
- `app.js` 与 `assistant-api.js`：Node.js 语法检查通过。
- 共用 operation 前端 Bridge 行为测试通过。
- 动作安全不变量与 V1 静态覆盖门禁通过；迁移状态审计仍正确返回 `objectiveComplete=false`，但 `remainingKotlinBackgroundOwners=[]`，路由之外的 Kotlin 后台业务所有权已全部收口。剩余阻断是用户授权的真机功能、锁屏、网络切换、重启和抓包验收。
- Android JVM：482 项测试，0 失败、0 错误、0 跳过，Debug/Release Kotlin 编译通过。`TaskType.INVENTORY` 与 `TaskType.ALARM` 均由 Service 过滤到共享 resident tick；旧 `InventoryCleanupTask/AlarmTask` 失败关闭，`SessionAwareGameProtocolClient.scanAlarms` 仅返回 `SHARED_ALARM_OWNER`，不发包。
- Android `V0.0.17`（`versionCode=17`）Debug 与 Release APK 均构建成功；Release 产物为未签名 APK。构建机缺少 Python 3.10 只造成预编译提示，真机首次启动后已生成 CPython 3.10 `.pyc` 缓存，不影响功能。
- 上一轮已安装的 `V0.0.17` Debug APK 为 26,620,616 bytes，SHA-256 `4744e187d2750d8a3e75e64fb340cdde58d15092a425a2535a62b6690ce50ad2`；Release 未签名 APK 为 25,966,185 bytes，SHA-256 `1fb33aa075c8b82fb6f3032431070b0d5dc33d3663eaf14a8fd4afb310e8b247`。
- 自动内政迁移后曾重新构建本地 `V0.0.17` Debug APK：27,349,583 bytes，SHA-256 `c9575183bf892f051a186ad5f66d27cd1495457cb26ae5aa3432104c80aa82b7`。该阶段产物当时未安装；该条仅保留为历史构建记录，不能作为当前设备版本。
- 最后兼容补丁后已重新完成 `V0.0.18`（`versionCode=18`）Debug APK 干净构建：26,637,093 bytes，SHA-256 `d07bd04b1eeff547b3023fd922bef3b8a419789a1f16eadb2a4af6397286320b`。Manifest、内嵌 `alarm.py/facade.py/automation.py/settings.py` 与构建源哈希、旧 `currentFingerprints` 继承、`incomingKeywords/vibrateOnAlarm` 保留、警报调度契约、`alarmPendingEventsJson`、Android 稳定通知 ID 和前端 `V0.0.18` 缓存键均已核验；V1 静态构建审计通过。该 APK 已通过 `adb install -r` 覆盖安装到设备 `27a83c9c`，设备报告 `V0.0.18 / versionCode 18`，设备端 `base.apk` SHA-256 与构建产物完全一致；安装后未主动启动 APP，进程未运行，也未执行真实游戏动作。
- 宝物解析修复版 `V0.0.19`（`versionCode=19`）Debug APK 已干净构建：26,637,097 bytes，SHA-256 `d896a863d58aae33d5e4db5c5278b6bf14db1297a1713d3241945f2f3e964bf5`。APK 内已核验 `inventory.py/item_names.py`、758 条道具名称、未知 ID 安全占位、前端 `hidden + display:none!important` 网络操作托盘和 `V0.0.19` 静态资源缓存键；V1 静态构建审计通过。该 APK 已覆盖安装到设备 `27a83c9c`，设备版本与 `base.apk` SHA-256 均与构建产物一致；安装后未主动启动 APP，进程与前台 Service 均未运行。
- `V0.0.18` 真机日志另暴露刷黄 pending 等待态约 1.68–1.9 秒重复状态查询的问题：pending 自身的 30 秒 deadline 会被其他已到期功能的立即 deadline 覆盖。该调度缺陷不属于本次宝物解析/界面隐藏改动，`V0.0.19` 尚未修复；重新开启长期托管前应优先收口。
- 停止账号 `202` 的真实 WebView 状态投影已复验：`savedTasksStarted=false`、任务栈为空，六类常驻任务全部 `running=false` 并显示“未运行”；历史 `stateRefresh/banditPrefetch/minePrefetch/foodToCopper/formations` 不再进入当前任务接口。历史日志仍可查看，但不会再把旧 `RUNNING/WAITING` 状态冒充为当前任务。请求健康账本连续校验未变化。
- 本地写入验收首次暴露一个真实门禁缺口：账号卡虽然显示停止，但旧持久化 `enabled=true` 与 hosting 偏好仍可能使保存设置调用 `AssistantForegroundService.refresh()`。该次排查意外唤醒 Service 并产生 8 次游戏请求，其中 1 次为治疗 mutation；发现后立即停止账号和 Service，没有发生刷黄、打矿或出征。该事件不能作为授权真机验收，也不能从记录中省略。
- 缺口已修复：设置保存只有在“账号启用 + 登录态可执行 + 前台执行所有者已存活”时才报告任务启动；保存接口不再复活已停止 Service，也不再同步等待共享常驻配置写入。最新 APK 原样保存同一配置 3 次为 49.0–53.2 ms，均返回 `localWriteCommitted=true`，配置前后一致，账号仍停止，Service 未启动；修复后请求健康账本 SHA-256 始终为 `aaebaf690f33be59a808762571ddb63fd505229b54f0624052da5266447bf515`。
- 页面重建竞态已修复：任务托盘监听器注册后主动恢复 `localStorage` 中的 operation。真机模拟 operation 在页面重载后 1 秒内恢复“准备中/取消”，点击后得到持久化 `CANCELLED`，页面明确显示“未向游戏服务器发送请求”，跟踪项清空且请求健康账本不变。
- 真实 WebView 热态样本：健康接口 20 次 P95 4.4 ms，账号读取 20 次 P95 39.5 ms，合法设置读取基线 20 次 P95 53.6 ms，模拟网络 operation 受理 19.3 ms。90 秒模拟任务期间健康接口 P95 89.1 ms，均满足 100 ms 目标；但 operation 完成落盘附近出现 655.6 ms 单次尖峰，设置样本 P95 112.8 ms，故 G7 尾延迟仍未完全通过。
- 这只是当前已迁移范围的回归证据，不代表阶段 7 或最终发布验收已经完成。

## 7. 分阶段执行计划

### 当前执行总览（2026-08-02）

完成口径：只有达到该阶段验收门槛才标记“已完成”。局部代码、过渡锁或局部性能数据只记录为前置成果，不提前算作后续阶段开工。

| 阶段 | 状态 | 已完成 | 尚未完成 |
|---|---|---|---|
| 阶段 0：保护当前版本 | 已完成 | 基线清点、迁移分支、可恢复检查点和测试基线 | 无 |
| 阶段 1：业务边界清单 | 已完成 | 路由所有者、响应类型和业务边界契约 | 无 |
| 阶段 2：共享 Python 包骨架 | 已完成 | 唯一共享包、`CoreFacade`、版本与哈希 | 无 |
| 阶段 3：Android 内嵌 Python | 已完成 | Android Python 运行时、进程内 Bridge、构建与隔离验证 | 无 |
| 阶段 4：纯协议与纯规则 | 已完成 | 共享协议、规则、fixture 和双端复用基础 | 无 |
| 阶段 5：统一 Core API | 已完成 | `dispatch`、平台适配、路由所有者契约和 operation 基础 | 其余路由的实际切换归阶段 7–8，不属于阶段 5 基础设施缺口 |
| 阶段 6：账号、Session、状态与存储 | 已完成 | 共享生命周期、状态机、非敏感账本、Keystore 凭据端口和双端主时间线 | 无 |
| 阶段 7：Android 宿主切换 | 进行中 | Bridge 分通道；契约声明的 56/56 条 Android 路由均由 `shared-python` 拥有；登录/区服/Session 建立和后台重登已统一到 Python；状态刷新、心跳、军情及全部已迁移游戏命令均为 Python 组包/解析 + Android Raw HTTP 字节传输；停止态投影、本地设置即时保存、页面重建恢复和安全取消已完成最终 APK 真机复验 | 其余本地路由 P95/P99、真实 `UNCERTAIN` 视觉、尾延迟专项及获得授权后的真实服务器成功路径 |
| 阶段 8：按功能纵向迁移 | 进行中 | 电脑端与 Android 路由所有权均为 56/56；配兵/补兵/治疗/开箱、户部/内政、手动日常、找黄/找矿、主要出征链和军情警报均共用 Python；十类常驻及后台日常的生产调度已切换到共享 tick | 仍服务新手/手动 starter 的桌面旧副本入口；故障回放与授权真机验收 |
| 阶段 9：统一调度 | 进行中（十类常驻+日常已切换） | `residentAutomationConfigJson/StateJson` 持久化配置、行游标、每日次数、警报指纹和 deadline；电脑端薄线程与 Android Service 均只提交同一个共享 tick；Android 已将 Python `nextWakeAtMillis` 接入 Handler/Alarm，并从 Kotlin 生产批次过滤十类常驻任务与七类日常任务 | 锁屏/Doze、设备重启和网络切换真机回放；最终合并桌面重复唤醒线程 |
| 阶段 10：删除 Kotlin 重复核心 | 进行中 | 已删除 Kotlin 完整登录实现、共享命令适配链、`RealSessionHealthProbe`、无损/副本/军情警报重复业务实现；桌面旧 worker 已删除或变为薄唤醒；Android 失败关闭标记和 Service 过滤保证旧入口不能发包 | 物理删除已无生产调用者的刷黄/打矿等旧协议副本、兼容性 `scanAlarms` 接口和自动背包死代码 |
| 阶段 11：性能、稳定性与发布 | 未开始 | 已取得局部真机本地读取和停止态军情受理数据 | 长稳、功耗、多账号、异常恢复和完整发布验收 |

当前契约声明的 56 条路由在 Android 和电脑端均由共享 Python 拥有（56/56）：

1. `GET /api/health`
2. `GET /api/accounts`
3. `GET /api/areas`
4. `GET /api/reference/guide`
5. `POST /api/accounts/stop`
6. `POST /api/accounts/delete`
7. `POST /api/accounts/add`
8. `POST /api/accounts/start`
9. `POST /api/automation/start-saved`
10. `POST /api/automation/stop`
11. `GET /api/military/intel`
12. `GET /api/state/refresh`
13. `GET /api/heartbeat`
14. `POST /api/brush/recommended-center`
15. `POST /api/daily/general-visit/candidates`
16. `POST /api/raid/fiefs`
17. `POST /api/formations/unassign-all`
18. `POST /api/troops/assign`
19. `POST /api/troops/refill`
20. `POST /api/troops/heal`
21. `POST /api/inventory/open-one`
22. `POST /api/brush/search`
23. `POST /api/brush/execute`
24. `POST /api/mine/search`
25. `POST /api/mine/execute`
26. `POST /api/liubu/hubu/query`
27. `POST /api/liubu/hubu/plant`
28. `POST /api/daily/sign-in/claim`
29. `POST /api/daily/arena-coins/claim`
30. `POST /api/daily/donate/claim`
31. `POST /api/daily/donate/custom`
32. `POST /api/daily/salary/claim`
33. `POST /api/daily/national-collect/claim`
34. `POST /api/daily/city-lord-collect/claim`
35. `POST /api/daily/general-visit/claim`
36. `POST /api/domestic/query`
37. `POST /api/domestic/action`
38. `POST /api/military/future/save`
39. `POST /api/liubu/save`
40. `GET /api/accounts/settings`
41. `POST /api/formations/save`
42. `POST /api/mine/save`
43. `POST /api/settings/save`
44. `POST /api/raid/execute`
45. `POST /api/lossless/execute`
46. `POST /api/dungeon/execute`
47. `GET /api/logs/system`
48. `GET /api/logs/account`
49. `GET /api/automation/status`
50. `GET /api/success-records`
51. `POST /api/logs/account`
52. `POST /api/logs/system/clear`
53. `POST /api/notices/dismiss`
54. `GET /api/maps/bandits`
55. `GET /api/maps/mines`
56. `POST /api/formations/apply`

### 阶段 0：保护当前可用版本

> 状态：已完成。

目标：确保任何迁移失败都能恢复到当前可用的电脑端。

任务：

1. 记录完整 `git status`、当前分支、版本号和测试结果。
2. 区分现有改动、删除文件和未跟踪文件，确认哪些属于当前有效实现。
3. 在用户确认后创建迁移专用分支和基线提交或等价的可恢复快照。
4. 构建一次电脑端便携版本和 Android Debug APK，保存 SHA-256。
5. 保存不含敏感信息的电脑端功能清单、路由清单和当前测试报告。
6. 迁移期间冻结无关的大规模重构。

交付物：

- 基线版本标识。
- 基线测试记录。
- 可恢复的 Git 检查点。
- 当前有效功能与接口清单。

验收门槛 G0：

- 可以从检查点恢复出当前可用的电脑端。
- 511 项电脑端测试、JavaScript 检查和 Android 测试均通过。

回退方式：恢复到基线检查点；不修改用户业务数据目录。

### 阶段 1：建立业务边界清单

> 状态：已完成。

目标：先弄清楚要共享什么，避免把桌面专属代码塞进 Android。

任务：

1. 将电脑端所有 `/api/*` 路由分成：共享单容器、电脑专属、历史兼容三类。
2. 为每个共享功能记录入口函数、调用链、状态读写、线程、定时器和协议 opcode。
3. 标记 `server.py` 中的桌面耦合：HTTP Handler、Clash、系统路径、起号、多容器和诊断。
4. 标记安全耦合：明文密码、Session、日志脱敏、SQLite 备份。
5. 建立“路由 → 功能 → 任务 → 协议 → 测试”追踪矩阵。
6. 明确抢城、押镖、寻宝、连体物品仍属于延期功能，不借迁移名义启用。

交付物：

- 单容器共享路由矩阵。
- Python 函数和全局状态依赖图。
- 桌面专属代码清单。
- Android Kotlin 重复业务实现清单。

验收门槛 G1：

- 每一个当前开放的单容器功能都有明确归属和测试入口。
- 没有“暂时不知道由谁负责”的真实动作接口。

### 阶段 2：创建共享 Python 包骨架

> 状态：已完成。

目标：先建立唯一源码位置和稳定调用入口，不迁移真实功能。

任务：

1. 创建 `shared_core/python/dwpm_core`。
2. 创建统一入口 `CoreFacade`，初期只提供 `health()`、版本和核心哈希。
3. 定义平台接口 `ports.py`，暂不接入业务实现。
4. 电脑端通过仓库共享路径导入该包。
5. 建立 `coreVersion` 和 `coreHash`；哈希覆盖全部共享 Python 源码及行为契约。
6. 增加测试，保证桌面加载的核心目录就是唯一共享目录。

交付物：

- 可导入的共享 Python 包。
- 核心版本与哈希机制。
- 电脑端最小接入测试。

验收门槛 G2：

- 电脑端行为不变。
- 电脑端 `/api/health` 可以报告共享核心版本和哈希。
- 仓库中不存在第二个 `dwpm_core` 可编辑副本。

### 阶段 3：尽早验证 Android 内嵌 Python

> 状态：已完成。

目标：在大规模抽离前验证 Android 技术路线，避免迁移完成后才发现运行时不可用。

任务：

1. 先在 Debug 构建中接入 Chaquopy 或选定的 CPython 嵌入方案。
2. Gradle 从唯一共享目录打包 `dwpm_core`，不把源码提交到 Android 手工目录。
3. Kotlin 调用 Python `health()` 并取得相同的 `coreVersion/coreHash`。
4. 通过现有 `AssistantWebBridge` 完成一次进程内请求和响应。
5. 增加一个不访问真实网络的延迟任务，验证异步 `operationId`、进度和完成事件。
6. 延迟任务运行期间反复调用本地 `health/settings/status`，确认不会被阻塞。
7. 验证 Debug/Release 编译、目标 ABI、离线启动和进程重建。
8. 记录解释器冷启动、首次调用、连续调用、本地接口 P95、空闲内存、APK 增量和桥接延迟。
9. 本阶段禁止账号登录和任何真实游戏动作。

交付物：

- Android 内嵌 Python 最小样例。
- 性能与兼容性报告。
- 同源哈希验证。

验收门槛 G3：

- Android 能稳定加载共享核心并完成进程内调用。
- 电脑端和 APK 报告相同核心哈希。
- Debug 与 Release 均能构建。
- 模拟长任务不会阻塞本地接口，任务结果在页面重建后仍可读取。
- 性能数据已测量且没有阻断性问题。

失败分支：

- 如果 Chaquopy 不满足 ABI、构建或稳定性要求，先评估自嵌 CPython/JNI。
- 不允许在该结论出来前转而复制或重写业务逻辑。

### 阶段 4：抽离纯协议与纯规则

> 状态：已完成。

目标：从风险最低、最容易逐字节验证的代码开始。

迁移内容：

1. UTF、整数、坐标、十六进制和包结构编解码。
2. 游戏请求构造和响应拆包。
3. 各 opcode 的 payload builder 与 parser。
4. 目标筛选、等级、兵种、资源点和副本目录等纯规则。
5. 成功、重复领取、失败和未知回执的纯判定。

迁移方法：

1. 从 `server.py` 机械移动函数，尽量不修改函数体。
2. `server.py` 暂时保留兼容导入或薄包装，避免一次改动全部调用方。
3. 将现有协议 fixtures 直接用于共享核心测试。
4. Android 只运行相同测试，不增加 Kotlin 等价实现。

验收门槛 G4：

- 所有请求 payload 逐字节一致。
- 所有解析结构与电脑端基线一致。
- 电脑端仍使用这些共享函数正常运行。

### 阶段 5：建立统一 Core API 与平台适配层

> 状态：已完成统一入口、平台适配、路由所有者契约和 operation 基础设施。阶段 5 验收时首批 7 条路由使用共享 Python；后续阶段 7–8 已把双端契约路由扩展到 56/56。该阶段只代表基础设施完成，不代表路由之外的后台任务闭环已经迁完。

目标：让 HTTP 和 Android Bridge 调用同一个业务入口。

统一入口建议：

```text
CoreFacade.dispatch(method, path, body, request_context)
CoreFacade.submit_network_operation(account_ref, operation_type, payload, idempotency_key)
CoreFacade.operation_status(operation_id)
CoreFacade.cancel_operation(operation_id)
CoreFacade.start_account(account_ref)
CoreFacade.stop_account(account_ref)
CoreFacade.start_saved_tasks(account_ref)
CoreFacade.stop_saved_tasks(account_ref)
CoreFacade.snapshot(account_ref)
CoreFacade.shutdown()
```

任务：

1. 从 HTTP Handler 中抽出参数校验、业务调用和响应组装。
2. HTTP Handler 只负责 HTTP 读写、认证和状态码转发。
3. Android Bridge 直接调用同一 `dispatch()`，不启动本地 HTTP 服务。
4. 建立平台端口，实现数据目录、凭据、通知、网络状态和日志回调。
5. 共享核心拥有账号业务状态和任务状态；宿主不得维护影子业务状态。
6. 为每条路由标记当前执行所有者：`desktop-python`、`shared-python` 或 `android-kotlin`。
7. 为每条路由标记响应类型：`ui-only`、`local` 或 `network-operation`。
8. `local` 路由直接完成本地读写；`network-operation` 只在桥接线程创建任务，不在桥接线程等待游戏服务器。
9. 建立持久化 `operationId`、幂等键、进度、结果、错误和 `UNCERTAIN` 状态。
10. 网络结果通过统一事件或 `operation/status` 返回；页面重建后可继续读取。

验收门槛 G5：

- 已迁移路由在电脑 HTTP 和 Android 进程内桥上返回相同业务 JSON。
- Android 业务响应不经过第二套 Kotlin 判断。
- 路由所有者清单不存在双重真实发包权。
- 本地设置保存立即完成，任何后续网络动作均作为独立操作运行。
- 一个持续 90 秒的模拟网络任务不会阻塞设置、日志、任务状态和缓存快照。
- 网络任务完成后能够返回真实结果，不被固定 30 秒桥接超时丢弃。

### 阶段 6：迁移账号、Session、状态与存储

> 状态：已完成。共享生命周期、状态机、非敏感账号账本、Keystore 密码/Session 端口和双端主时间线均已接入。平台 passport、区服选择、`0x1003/0x8003`、`0x1004/0x1016/0x8004`、初始状态和当乐 SDK 加解密现由 `account/login.py` 唯一拥有，Android 后台重登也复用该流程；详细证据见 `docs/core_migration/account_state_stage6.md`。

目标：建立所有功能共同依赖的真实运行基础。

任务：

1. 抽离账号登录、区服选择、角色读取和 Session 生命周期。
2. 抽离心跳、Session 失效识别、退避和重新登录决策。
3. 抽离角色、资源、将领、军队、背包和军情状态刷新。
4. 共享核心继续使用统一的非敏感业务存储语义。
5. Android 密码通过 `CredentialPort` 从 Keystore 临时取得，禁止写入 Python SQLite、JSON 或日志。
6. Android 停止账号后，持久化 Session 只能用于重登，不能继续发动作。
7. 验证进程杀死、恢复和账号删除时的秘密清理。

验收门槛 G6：

- 电脑端账号行为没有退化。
- Android 离线回放中的账号状态转换与电脑端一致。
- Android 存储审计找不到密码、Token、`dm`、Cookie 等敏感明文。
- 未经用户授权仍不进行真机登录。

### 阶段 7：Android 宿主切换到共享核心

> 状态：执行中。契约声明的 Android 路由所有权已达 56/56；Bridge 分通道、共享登录/重登、本地设置/视图/地图投影、持久化 operation 和事件驱动页面链路已完成代码与离线门禁。状态刷新、心跳、军情及其他已迁移命令均由 Python 组包/解析并调用 Android `executeRawHttp`；Android 旧网络路由适配已经删除。剩余门槛是最终 WebView 验收和用户授权后的真实服务器成功路径。详细记录见 `docs/core_migration/android_host_stage7.md`。

目标：让 Android 成为共享核心的系统宿主，而不是第二个业务核心。

按响应风险从低到高执行：

1. 建立进程级核心单例，防止 WebView 和 Service 重复创建核心。
2. 先拆除 `AssistantWebBridge` 的全局单线程瓶颈，建立互不阻塞的 `local-lane`、`event-lane` 和 `network-lane(accountId)`。
3. 先切设置、日志、缓存和任务状态等本地路由；达到 5.5 的响应指标后再切网络路由。
4. `AssistantWebBridge` 将共享路由交给 Python `CoreFacade`；桥接线程只负责参数转换和快速受理。
5. 以“刷新军情”作为首个网络异步样板：立即返回 `operationId`，等待服务器后再更新结果。
6. 对每个账号建立唯一网络执行锁；UI 手动网络动作和后台任务进入同一把锁。
7. 保留一份结构化事件通道，将任务进度和结果交给前端；事件丢失时仍能通过 `operation/status` 恢复。
8. `AssistantForegroundService` 只管理进程存活、网络、通知和系统唤醒；Python 核心拥有任务状态、优先级和发包决策。
9. Kotlin 旧核心保留期间必须由总开关禁用真实动作，只允许离线对比。

验收门槛 G7：

- 关闭 Activity 后，共享 Python 核心仍由前台服务托管。
- 同一账号不存在 Python/Kotlin 并发发包。
- 页面显示的任务状态来自共享核心，不来自 Kotlin 推测。
- 军情刷新等网络操作可以等待真实完成，但等待期间本地操作保持即时响应。
- 页面重建后可以恢复未完成网络操作的加载状态和最终结果。
- 点击反馈、本地读写和网络受理达到 5.5 的量化指标。

### 阶段 8：按功能纵向迁移

> 状态：执行中。双端手动路由所有权均已达 56/56。刷黄、打矿、掠夺、无损、副本、将领维护、六部、自动内政、自动背包、军情警报与七类日常的生产调度均已接入同一个 `automation:recovery-tick:v1`；共享 Python 持久化宿主习惯、行游标、每日次数、优先级、发送账本和 deadline，桌面生产 worker 与 Android Service 只负责配置同步、提交、展示和唤醒。尚待收口的是仍被新手/手动 starter 使用的桌面旧副本入口，以及最终故障/真机验收。

按以下顺序推进，每次只迁移一个功能组：

| 批次 | 功能 | 原因 |
|---|---|---|
| A | 只读状态、心跳、军情、日志、成功记录 | 风险最低，可先验证完整数据链 |
| B | 配兵、补兵、治疗、加体、加忠 | 是全部出征功能的公共前置能力 |
| C | 刷黄 | 电脑端成熟，适合作为首个完整常驻任务闭环 |
| D | 打矿、掠夺 | 共用出征、目标搜索和军情确认能力 |
| E | 无损、副本 | 状态机复杂，需要建立在前面能力之上 |
| F | 背包、内政、日常、六部、警报 | 非出征任务与周期任务收尾 |

每个功能都执行同一份九步清单：

1. 锁定电脑端入口、配置和基线测试。
2. 把实现移动进共享核心，电脑端先改为调用共享核心。
3. 用真实历史响应和共享 fixtures 做离线回放。
4. 对比请求字节、状态变化、日志事实和下一次执行时间。
5. 明确该功能的本地步骤和网络步骤，禁止本地保存等待网络结果。
6. Android 路由切换为共享核心，Kotlin 对应功能关闭发包权。
7. 完成异步进度、离线、进程恢复、幂等和停止语义测试。
8. 获得用户明确授权后，进行单账号、单功能、低风险真机验证。
9. 真机通过后删除对应 Kotlin 业务实现和重复测试，更新所有者矩阵。

单功能验收门槛：

- 相同输入产生相同请求字节。
- 相同回执产生相同成功、失败、重试和停止结论。
- 相同状态产生相同下一任务和等待时间。
- 真实动作只有共享 Python 核心能够发送。
- Android 重启后不会重复发送回执不明的动作。
- 网络等待不会阻塞该功能的本地设置和其他本地接口。
- 操作实际完成后页面能收到结果，不出现固定时长造成的假失败。

### 阶段 9：统一调度与后台运行

> 状态：进行中（十类常驻与日常已切换）。`automation:recovery-tick:v1` 现在统一决定刷黄、打矿、掠夺、无损、副本、将领维护、六部、自动内政、自动背包、军情警报与七类日常的配置启停、优先级、规则行游标、每日边界、事件指纹和下一 deadline。Android Service 在旧 `TaskScheduler` 前提交共享 operation，并过滤这些功能的全部 Kotlin 生产任务；桌面对应 worker 也只是同一 tick 的薄唤醒入口。余下工作是旧入口/死代码物理清理和锁屏、Doze、重启、网络切换真机回放。

目标：在逻辑已经统一的前提下解决 Android 功耗和系统生命周期。

第一步采用兼容模式：

- 保留电脑端 Python 任务行为，Android 前台服务承载相同核心。
- 先证明功能一致，不同时重写调度器。

第二步根据测量结果优化为共享的 deadline/tick 模型：

```text
共享核心 tick(now)
  → 执行当前到期任务
  → 持久化状态
  → 返回 nextWakeAt
Android 宿主
  → 短等待保持前台调度
  → 长等待使用 Alarm/Doze 兼容唤醒
```

要求：

1. deadline/tick 仍在共享 Python 核心实现，不能只在 Kotlin 重写。
2. 电脑端也切换到同一调度语义。
3. 任务等待、完成锁、出征不确定账本和每日边界都必须持久化。
4. 优化前后运行同一组时间推进测试和故障恢复测试。
5. 调度器与页面手动网络操作共用每账号网络队列，不得绕过幂等和执行锁。
6. 调度器的长网络请求不得占用 `local-lane` 或延迟本地设置响应。

验收门槛 G9：

- 锁屏、Doze、网络切换和进程恢复不会改变业务决策。
- 任务不会因系统重复启动 Service 而重复执行。
- 调度优化前后的确定性回放结果一致。
- 后台任务持续运行时，本地设置、日志和任务状态仍保持即时响应。

### 阶段 10：删除 Android 重复业务核心

> 状态：进行中。迁移过程已删除 Kotlin 完整登录实现、共享 `executeGameCommand`/Session 适配链、无损/副本/军情警报重复业务实现和多个路由业务映射；十类常驻与日常的 Kotlin 生产所有权已全部关闭。桌面对应业务 worker 已删除或收缩为共享 tick 薄唤醒；Android 重复任务只保留配置/失败关闭标记，军情旧事件检测器已删除且 `scanAlarms` 只返回共享所有者错误。尚需物理删除兼容接口、已无调用者的刷黄/打矿旧协议副本与自动背包死代码。

目标：从代码结构上消除未来再次漂移的可能。

任务：

1. 删除或缩减 Kotlin 中的协议 builder/parser、任务类、功能状态机和成功判定。
2. 保留 Kotlin 平台宿主、数据安全、通知和生命周期代码。
3. 建立静态检查：Android `main` 源集不得重新出现游戏 opcode、任务优先级和功能回执规则。
4. Kotlin 测试转为宿主契约测试；业务测试全部落在共享核心。
5. 更新 README、产品说明和架构图。

验收门槛 G10：

- 任一开放功能在仓库中只能找到一个业务实现。
- Android 删除 Python 运行时或共享核心后无法执行游戏业务，证明不存在隐藏的 Kotlin 备用核心。
- 电脑端和 Android 报告同一核心版本与哈希。

### 阶段 11：性能、稳定性与发布验收

> 状态：未开始。已有局部真机性能样本，但尚未开展本阶段要求的完整长稳、功耗、多账号和发布验收。

目标：在一致性完成后优化真实性能并完成发布。

必须测量：

- Python 解释器冷启动和核心初始化时间。
- 首次与连续本地 API 调用延迟及 P50/P95/P99。
- 网络任务受理延迟、实际完成时间和结果通知延迟。
- 长网络任务运行期间本地 API 的延迟变化。
- 空闲与运行内存、线程数、CPU 和电量。
- APK 大小增量和各 ABI 安装结果。
- 6 小时以上锁屏托管。
- Wi-Fi/移动数据切换、断网、Session 过期。
- Activity 关闭、进程重建、设备重启首次解锁。
- 多账号串行公平性和同账号互斥。

优化原则：

1. 只优化实测热点。
2. 优先减少不必要轮询、线程和重复解析。
3. 如确有 CPU 热点，可将纯热点实现为两端共同调用的 Rust/C 扩展。
4. 禁止为了性能重新建立 Kotlin 业务分支。

最终验收：

- 电脑端原有功能保持有效。
- Android 开放功能完成逐项真机证据。
- 两端核心哈希一致。
- Android 不依赖电脑、局域网 Mobile API 或云地图即可运行。
- 不存在双核心、重复发包和敏感明文回归。
- 界面交互和本地设置即时响应，网络等待不会再被误报为核心失败。
- 5.5 的所有响应指标在目标真机上达标，并且在 90 秒长网络任务期间仍然达标。

## 8. 风险与控制措施

| 风险 | 控制措施 |
|---|---|
| 抽离导致电脑端退化 | 每次只迁移一个小模块，保留兼容导入，持续运行电脑端测试 |
| Android Python 运行时不兼容 | 在阶段 3 提前做最小 POC，未通过前不大规模迁移 |
| APK 内核心与电脑版本不同 | 构建时生成 `coreHash`，启动和 CI 都校验 |
| 两套核心重复发包 | 路由所有者矩阵、账号执行锁、旧 Kotlin 核心默认关闭真实动作 |
| Android 进程被系统杀死 | 共享核心持久化 deadline、完成锁和不确定事务；Service 恢复先核对状态 |
| Python 线程耗电 | 先测量，再将同一共享调度器改造成 deadline/tick；不在 Kotlin 另写规则 |
| 凭据安全回退 | Android 只通过 Keystore 端口提供凭据，自动扫描数据目录和日志中的敏感字段 |
| 当前工作区改动过多 | 阶段 0 建立明确基线和可恢复检查点后再开始结构调整 |
| 一次迁移范围过大 | 功能按批次和单功能验收门槛推进，任何失败只回退当前功能 |
| 长网络请求再次堵塞桥接线程 | 本地、网络和事件分通道；桥接线程只提交任务，不执行网络等待 |
| 页面超时后用户重复点击 | 持久化 operationId 和幂等键；重复请求返回已有任务状态 |
| 保存设置被网络副作用拖慢 | 本地持久化先独立完成，任务重建和网络动作随后异步执行 |

## 9. 完成定义

只有同时满足以下条件，迁移才算完成：

1. 前端源码只有一份。
2. 游戏业务源码只有一份。
3. 电脑端和 Android 使用相同核心版本与哈希。
4. Android Kotlin 中没有重复的游戏协议和任务业务实现。
5. 所有开放功能完成离线回放，关键功能完成用户授权的真机验证。
6. 电脑端现有可用能力没有退化。
7. Android 能在电脑关闭时独立运行。
8. 锁屏、断网、重启和 Session 失效恢复通过。
9. 安全审计确认凭据、Session 和日志没有明文回归。
10. 性能达到实测可接受标准，并且没有用第二套业务逻辑换取性能。
11. 用户操作立即得到界面反馈，本地设置保存不等待游戏服务器。
12. 网络操作可以等待真实结果，但不阻塞本地接口，也不会因固定桥接超时产生假失败。
13. 页面关闭、重建或重复点击不会丢失结果或重复执行真实动作。

## 10. 当前下一批工作项

### 工作项 T7.1：拆分 Android Bridge 执行通道

> 状态：已完成。

已完成：

- [x] 审计 `AssistantWebBridge` 的单 executor、Controller 和 Service 调用链。
- [x] 建立两线程 `local-read`、单线程 `local-write`、UI/event 投递和 `network-lane(accountId)`。
- [x] 验证长网络任务不阻塞本地读写、同账号网络任务串行、不同账号可并行。

### 工作项 T7.2：迁移本地快速路由

> 状态：功能迁移已完成，真实 WebView Bridge 的完整响应与长网络隔离验收仍待阶段 7 收口。

已完成：

- [x] `GET /api/accounts`：账号卡业务投影由共享 Python 生成。
- [x] `GET /api/accounts/settings`：两端复用共享设置快照和敏感字段门禁。
- [x] `POST /api/military/future/save`：本地保存与网络执行分离。
- [x] `POST /api/liubu/save`：本地落盘成功不再被后续任务结果覆盖。
- [x] `POST /api/formations/save`：本地配兵设置可真实保存，不再伪报网络配兵任务已启动。
- [x] `POST /api/mine/save`：本地保存与打矿网络执行分离。
- [x] `POST /api/settings/save`：各 scope 统一由共享 Python 校验和归并，网络后续任务不覆盖保存结果。
- [x] `POST /api/raid/execute`、`POST /api/lossless/execute`、`POST /api/dungeon/execute`：混合接口已拆为本地保存与独立执行状态。
- [x] 日志、任务状态、成功记录、提示关闭和山贼/矿点地图缓存均改由共享 Python 投影；对应 Kotlin 重复映射已删除。
- [x] 真机热态设置读取 10 次：P50 38.3 ms，P95/P99 39.9 ms；敏感路径 0，未启动 Service，游戏请求历史未变化。
- [x] 最新 Debug APK 真实 WebView 冷启动约 663 ms；原生 Bridge 正常，模拟 network operation 约 19.3 ms 返回 `202 + operationId`，90 秒运行期间健康读取 P95 89.1 ms，未启动 `AssistantForegroundService`。
- [x] 修复本地保存错误复活 Service：`LocalSettingsExecutionPolicy` 将“持久化启用意图”和“当前可执行状态”分开；保存只刷新已经存活的执行所有者，共享常驻配置改由 Service 在下一次显式启动/tick 前同步。
- [x] 最终 APK 对停止账号原样保存 3 次耗时 49.0–53.2 ms，配置前后一致，返回 `localWriteCommitted=true + waitingForAccountStart=true`；Service 未启动，请求健康账本未变化。

尚未完成：

- [ ] 对其余已迁移本地路由和真实本地写入完成 WebView P95/P99 验收。
- [ ] 共享 operation 完成时仍观察到一次 655.6 ms 健康读取尖峰；高频压力下设置读取 P95 186.1 ms、P99 1070.5 ms。正常点击频率不会触发“手机核心响应失败”，但严格 G7 尾延迟尚未达标。该优化涉及 operation 账本 `fsync`、CPython 单解释器竞争与持久化安全，列入下一版本专项，不能为降延迟削弱 mutation 发送账本。

### 工作项 T7.3：建立军情网络异步样板

> 状态：代码、离线门禁及最终 APK 的页面重建/安全取消真机验收已完成；真实军情成功路径和 `UNCERTAIN` 真机视觉仍待授权边界内验收。

已完成：

- [x] `GET /api/military/intel` 在 Android 快速返回 `202 + operationId`，不再用 Bridge 固定超时判断游戏结果。
- [x] 持久化 `QUEUED / RUNNING / SUCCEEDED / FAILED / CANCELLED / UNCERTAIN` 状态；原生事件为主，15 秒本地状态 watchdog 只用于丢事件恢复。
- [x] 同账号相同在途查询合并，避免重复点击重复发包。
- [x] Python 与 Kotlin 双重执行所有者/Session 门禁，以及与旧调度器互斥的非阻塞账号锁和退避重试。
- [x] 停止态真机负向验证：受理约 8.4 ms，最终明确失败为“Android 前台执行所有者未激活”；请求历史不变，Service 未启动。
- [x] 单调 `eventId` 事件将 `progressDetails / requestSent / cancellationDenied` 推送到页面，前端不再 250 ms 持续轮询。
- [x] `operationId` 保存在 `localStorage`，页面重建后重读持久化状态；临时读失败保持可恢复，不产生未处理 Promise。
- [x] 页面状态条在 `requestSent=false` 时提供取消；已发包时禁止取消，并分开展示 `CANCELLED / UNCERTAIN`。
- [x] 修复页面初始化竞态：托盘监听器注册后立即重读持久化 operation；最终 APK 页面重建后 1 秒内恢复取消入口，点击后显示 `CANCELLED` 并清理跟踪项，全程未启动 Service、未新增游戏请求。

尚未完成：

- [ ] 获得用户明确授权后验证一次 Service 托管下的真实军情成功路径。
- [ ] 仍需在用户授权的受控故障路径中验证真实 `UNCERTAIN` 视觉；页面重建、取消及 `CANCELLED` 的最终 WebView 验收已经完成，不能用 Debug 模拟结果冒充服务器回执不明。

### 工作项 T7.4：迁移真实配兵网络 operation

> 状态：代码与离线门禁已完成；真实账号成功路径必须等待用户明确授权。

- [x] 将真实配兵建立为独立持久化 mutation operation；保存设置立即返回，网络结果在后台完成。
- [x] 与后台调度共用账号执行锁、在途合并键和 `SUCCEEDED / FAILED / UNCERTAIN` 真实结果语义。
- [x] Python 在取得 JVM 账号锁后、进入字节 HTTP 传输前持久化 `requestSent`；明确拒绝为 `FAILED`，发送后断联为 `UNCERTAIN`，禁止静默重放。
- [x] 批量配兵和一键卸兵也已切换到 Python 逐将领 `0x1226/0x8226` 工作流；Android 的 `executeGameCommand`、`executeSharedCoreGameCommand`和 Session 协议适配链已删除，宿主只执行 Python 提供的 URL、HTTP 字段与原始字节。
- [x] 前端不等待 operation 才报告保存结果；只有 operation 真实终态成功后才提示“实际配兵完成”。
- [x] 停止账号仍可保存配兵，且不会调用配兵网络任务。
- [ ] 获得用户明确授权后完成一次真实配兵成功路径真机验证。

### 工作项 T7.5：迁移其余 Android 路由

> 状态：路由所有权切换已完成（56/56）；路由背后的旧宿主适配与后台任务收口继续归阶段 8–10。

- [x] 迁移 `/api/state/refresh` 的全部 scope、`/api/heartbeat`、名将拜访候选查询和掠夺封地查询。
- [x] 迁移一键卸兵、批量/单将配兵、批量补兵和治疗 operation；现在全部使用 Python 原始命令工作流。
- [x] 迁移 `/api/inventory/open-one`：Python 拥有物品白名单、钥匙前置检查、`0x1104/0x8104` 背包解析、`0x3144/0xA144` 开箱及 `FAILED / UNCERTAIN` 终态；Kotlin 旧手动开箱路由已删除。
- [x] 迁移日常签到、竞技币和国家俸禄：Python 生成 `0x6202/0x1134`、`0x6260/0x6266`、`0x314b` 请求并解析真实 fixture 回执；重复领取归一为已完成，缺少 mutation 回执为 `UNCERTAIN`。
- [x] 迁移自动/自定义捐献、国家征收、城主征收和名将拜访：Python 拥有额度、候选、排序、配额、终态分类、封包和回执；对应 Kotlin 页面路由和业务方法已删除。
- [x] 手动日常的完成锁由 `DailyCompletionPort` 收口：Python 决定重复抑制与确定成功/跳过终态，宿主按账号、key 和显式时间保存计数；`FAILED / UNCERTAIN / partialSuccess` 不写完成，自定义捐献不写 `autoDonate` 完成锁。竞技币 22:00 周期已有双端显式时间契约，周期 key 的最终单一实现随阶段 9 调度存储一并收入 Python。电脑端旧 HTTP 手动日常分支已删除。
- [x] 电脑端找黄/找矿切换到 Android 相同的 Python 原始命令工作流；`DesktopMapSnapshotPort` 将 Python 筛选后的观测投影到现有 SQLite 地图，不会因为某个筛选视图未包含其他目标就误删全局地图记录。
- [x] 迁移刷黄和打矿正式出征：Python 负责出征前状态、加体/加忠/治疗/配兵前置、`0x1520/0x1522` payload、`0x8520/0x8522` 回执与 `UNCERTAIN` 边界；Android 只保留原始命令传输，电脑端手动路由调用同一 workflow。
- [x] 账号添加/启动、停止/删除、区域/指南、保存配置后自动化启停等剩余契约路由已切到共享 Python，双端所有权均为 56/56。
- [x] 共享登录核心直接写账号账本与 Session 密钥；Android 仅提供 Keystore、Raw HTTP 和成功后启动前台服务，后台自动重登复用同一 Python 流程。
- [x] 删除 Android 通用 Kotlin 游戏命令适配链；Python `make_packet → RawHttpPort → parse_response` 已成为已迁移命令的生产路径，并有原始字节回归覆盖。
- [x] 收口军情/状态/心跳：Python 直接生成 `0x1016/0x1104/0x1600/0x3110` 请求、解析 `0x8004/0x8104/0x8600/0xa110` 并更新统一公开账号状态；Android `executeNetworkOperation`、`handleSharedCoreNetwork` 和三条 Kotlin 业务适配已删除；电脑端也调用相同工作流。
- [x] 补强无损前置 mutation 账本：治疗、加体、配兵、补兵或选关前先写 `losslessPendingBattleJson`；进程恢复遇到 `sending/uncertain/failed` 只做只读状态核对并停止，禁止重放。正式预出征/出征异常也显式落成 `uncertain`。
- [x] 迁移副本常驻状态机：`automation:dungeon-action:v1` 统一目录/状态、loop/clear 选关、章末多人关跳过、前置维护、两阶段出征、战斗轮询、回闲、奖励、开箱、通关确认和战败暂停；`dungeonPendingRunJson` 覆盖前置、正式出征和开箱三个发送边界。
- [x] 电脑端 `dungeon_worker` 和 Android `runDungeon` 已改为薄提交/轮询入口；Android `DungeonProtocolShapes.kt`、`DungeonPendingRun.kt` 和旧 Kotlin 副本发送实现已删除。共享 recovery tick 的 pending 优先级现为打矿 > 无损 > 刷黄 > 掠夺 > 副本 > 将领维护 > 六部 > 自动内政。
- [x] 副本明确战败账本增加本地人工确认入口：只有用户重新保存并启用副本配置时才归档 `defeatConfirmed`；任一 `sending/uncertain` 边界仍拒绝清除，双端设置保存均调用同一 Python 判断。
- [x] 刷黄/打矿常驻配置与调度切入共享 Python：双端宿主习惯统一归一为 `residentAutomationConfigJson`，行游标、每日次数和 deadline 保存到 `residentAutomationStateJson`；Android Service 过滤旧 Kotlin 任务，桌面生产 worker 只唤醒共享 tick。
- [x] 掠夺、无损和副本的规则游标、每日限制、优先级和下一业务时间已接入同一 tick；双端旧调度不再拥有生产发包权。
- [x] 六部金银花种植已接入共享 tick；`ministryPendingPlantJson` 在发送前落账，回执不明时只查询菜地状态，禁止自动重种。
- [x] 七类日常后台调度已复用现有 Python workflow 和 `DailyCompletionPort`；竞技币保持中国时区 22:00 边界，`UNCERTAIN` 或部分成功在当周期禁止自动重放。
- [x] 副本/刷黄每日次数已从 `residentAutomationStateJson` 直接投影到双端页面；旧桌面/Android 计数只作 schema 2 之前的兼容回退。
- [x] 删除 Android 无条件状态刷新、独立粮食转铜轮询和无入口配兵任务；刷黄/打矿 Kotlin 任务缩为失败关闭配置标记，旧协议调用方静态归零。
- [x] 独立将领维护已进入共享 tick：双端配置归一为同一 `general` 计划，按封地治疗、逐将加体和逐将加忠使用 `generalMaintenancePendingJson` 子步骤账本；Android `TaskFactory` 不再创建旧 Kotlin 生产任务。
- [x] 自动内政已进入共享 tick：双端配置归一为同一 `domestic` 计划，`domesticPendingActionJson` 分别记录粮食转铜和建筑/科技动作；桌面两个入口均为薄唤醒，Android `TaskFactory` 不再创建旧 `InternalAffairsTask`。
- [x] 自动背包已进入共享 tick：双端配置归一为同一 `inventory` 计划；`inventoryPendingActionJson` 在每个物品/装备动作前保存发送边界，成功后只依据新鲜 `0x1104/0x8104` 数量减少或装备实例消失完成；桌面旧自动开箱线程已退出生产路径，Android `InventoryCleanupTask` 失败关闭。
- [x] 军情警报已收口：Python 持久化基线、指纹历史、pending 事件和异常去重；双端只保留日志/通知展示与唤醒能力。
- [x] 兼容旧警报账本与隐藏配置：新状态可从旧 `currentFingerprints` 继承当前基线；共享设置计划和 Android mapper 均保留 `incomingKeywords`、`vibrateOnAlarm`，保存其他设置不会静默清空警报筛选或震动选项。
- [ ] 按离线、失败门禁、最终 WebView、用户授权真机的顺序完成验收。

### 工作项 T8.1：完成主要常驻任务与日常共享闭环

> 状态：进行中。刷黄、打矿、掠夺、无损、副本、将领维护、六部、自动内政、自动背包、军情警报和七类日常的共享核心与双端生产所有权切换已完成；旧协议死代码物理删除和最终真机回放尚未完成，因此还不能宣称整个常驻体系已经完整可用。

已完成：

- [x] 刷黄在首个 mutation 发送边界前持久化 `brushPendingRecoveryJson`，记录 `sending`、将领、目标、恢复配兵规则和治疗设置；正式出征明确拒绝时清理，获得成功回执后更新为 `accepted` 并保存 `battleId`。
- [x] 打矿获得正式出征成功回执后持久化 `minePendingGarrisonJson`，保存 exact `battleId`、坐标、将领、行军时间、是否加速和是否撤防。
- [x] 共享 Python 已实现智能行军加速：刷新背包、选择行军符、生成 `0x1524`、解析 `0x8524`；加速失败或回执不明不会抹掉已经确认的打矿出征事实，也不会再次出征。
- [x] 刷黄纯 reducer 只有观察到“忙碌→回闲”，或经过完整状态刷新宽限期仍确认空闲，才允许进入战后维护。
- [x] 打矿纯 reducer 只接受 battleId、坐标和将领证据匹配的驻守记录；撤防发送边界为 `sending/uncertain` 时禁止自动重发，撤防后必须确认将领全部回闲才允许清账。
- [x] `CoreFacade` 刷黄恢复 workflow 已完成：新鲜 `0x1016/0x8004`、忙碌→回闲证据、按封地治疗、恢复保存配兵、可选 `0x1116/0x8116` 清理邮件，全部确定成功后才清账。
- [x] `CoreFacade` 打矿驻守 workflow 已完成：新鲜 `0x1600/0x8600 + 0x1016/0x8004`、exact battleId/坐标/将领门禁、`0x1526/0x8526` 撤防、回闲确认与安全清账。
- [x] 每个治疗、配兵、清邮件和撤防 mutation 都在发包前写入子步骤 `sending`；发送后断联写为 `uncertain`，再次 tick 会停止并禁止自动重放。
- [x] 补齐刷黄/打矿“出征前治疗、加体、加忠、配兵”最早发送边界：开始前即建立 pending；前置中断保存 `failed/uncertain`，恢复只允许只读核对，禁止重新执行前置或再次出征。
- [x] 建立内部持久化 `automation:recovery-tick:v1`：快速受理、每账号串行、在 operation 账本中恢复，并返回 `nextWakeAtMillis`；Android `SharedPythonCoreHost` 已提供宿主调用方法。
- [x] `resident_due_decision` 统一矿点优先级、刷黄每日边界、规则游标与 deadline；完成高优先级任务后会重新计算其他已到期任务，避免刷黄被持续打矿饿死。
- [x] 双端生产入口切换：桌面 `auto_brush_worker/auto_mine_worker` 只提交同一个共享 tick；Android Service 在旧 scheduler 前执行共享 tick，并过滤 `SHUA_HUANG/BANDIT_PREFETCH/AUTO_MINING/MINE_SEARCH/MINE_PREFETCH`，Python 返回 deadline 进入 Handler/Alarm。
- [x] `allowedFeatures=[mine,lossless,brush,raid,dungeon,general,ministry,domestic,inventory,alarm,daily]` 与 Android `SHARED_RESIDENT_TASK_TYPES` 保持一一对应；十类常驻的旧生产所有者均已关闭。
- [x] 自动背包的单动作计划和军情警报的持久化去重/pending 恢复已完成；当前电脑端 Python 全量 829/829、Android 482/482 均通过。旧核心测试不再作为迁移完成证据。
- [x] 补齐刷黄/打矿进程重建、断网、Session 失效、发送边界不明确、停止单任务与停止账号分离的离线回放；已接受动作即使任务停止仍会安全恢复，`UNCERTAIN`/超时不会生成自动重放 deadline。
- [x] 掠夺、无损、副本的规则游标、每日限制和下一业务时间已进入同一 tick；Android 不再调度对应 Kotlin 生产任务。
- [x] 六部种菜使用 `ministryPendingPlantJson` 发送账本；回执不明时只查询菜地核对，禁止再次种植。
- [x] 七类日常复用现有 Python workflow 与 `DailyCompletionPort`；竞技币保持中国时区 22:00 周期，`UNCERTAIN` 或部分成功在当周期禁止自动重放。
- [x] 副本/刷黄每日次数由 schema 2 `residentAutomationStateJson` 直接投影；旧双端计数仅作为迁移前兼容回退。
- [x] Android 角色记录已改为读取共享 Python 的结构化成功事实：刷黄在确认 `dispatched` 时按 `battleId` 持久化，副本在 `chest-opened/settlement-recovered` 时持久化；投影会恢复升级前最后一笔账本事实，并按 `battleId` 去重。`V0.0.23` 真机已同时返回刷黄目标/坐标和第四章第 5 关副本宝箱记录。
- [x] 首批阶段 10 机械清理完成：删除桌面 `_legacy_auto_brush_worker/_legacy_auto_mine_worker/_legacy_raid_worker/_legacy_lossless_worker/_legacy_dungeon_worker/_legacy_auto_ministry_worker`；Android 掠夺/无损/副本/六部/日常任务仅保留配置标记并失败关闭；删除 `runAutoLoot/runSixMinistries/runDungeon/runLossless`、旧日常扩展查询入口和逐功能过渡 adapter，静态门禁禁止恢复这些备用核心。
- [x] 第二批机械清理完成：`ShuaHuangTask/MineTask` 从完整 Kotlin 状态机缩为纯配置失败关闭标记，删除 `BanditPrefetchTask/MinePrefetchTask`；删除无条件 `StateRefreshTask`，避免共享状态刷新之外再发一次将领/编队/军情查询；删除电脑端不存在的独立 `FoodToCopperTask` 轮询，粮食转铜仍只由共享业务前置按需调用；删除无生产入口的 `FormationUpdateTask`。
- [x] Android `AssistantTasks.kt` 从 1746 行缩至 362 行；新增静态门禁确认 Android `main` 除待删除协议定义文件外不存在 `dispatchFormation/searchMines/occupyMine/withdrawMineDefense` 等旧调用者。迁移状态审计不再用历史 Kotlin 真机证据冒充当前共享 Python 真机验收。
- [x] 修正停止账号的当前任务投影：只有“账号启用 + 已启动保存任务 + 前台执行所有者存活”同时成立才允许展示运行态；否则历史运行状态统一降级为停止，退役的刷新/预取/独立粮转铜/旧配兵类型不进入当前任务列表。真机页面已确认任务栈为空、常驻任务均显示“未运行”，历史日志仍保留。
- [x] 修正本地保存的执行边界与页面恢复竞态：保存设置不再启动已停止 Service，真机写入 49.0–53.2 ms；页面重建后 operation 托盘和取消入口可立即恢复，Debug 模拟任务在发包前安全取消。
- [x] 独立将领维护完成共享化：首次 tick 先持久化稳定的封地/将领顺序与配置快照；每个治疗、加体、加忠步骤在 mutation 前写 `sending`，明确成功写 `accepted/completed`，明确拒绝写 `rejected`，回执不明写 `uncertain`。进程恢复只跳过已完成步骤或重试未发包步骤，任何越过发送边界但未安全收尾的步骤都只读核对并要求人工处理。
- [x] 将领维护双端所有权已切换：桌面 `auto-general` 只是共享 tick 薄唤醒线程；Android 配置映射保留完整 general 开关，Service 投影 `feature=general → TaskType.GENERAL`，旧 `GeneralMaintenanceTask` 已从生产 `TaskFactory` 移除。俘虏营救仍固定关闭，未确认协议不会发送。
- [x] 自动内政完成共享化：规划器稳定选择大厅、空地、最低级/配置优先建筑和已选科技，并在建筑/科技之间轮换；一次 tick 最多提交一个 mutation，确认成功后 1 秒继续填队列，无动作时按 10 分钟/建筑最早完成时间唤醒。
- [x] 自动内政恢复账本已完成：`resourceExchange/action` 在发包前写 `sending`，明确成功写 `accepted/completed`，明确拒绝写 `rejected`，回执不明写 `uncertain`。进程恢复会先只读刷新；候选已变化则归档重规划，候选未变化的 `sending/uncertain` 禁止重发，持久化 `accepted` 回执只做安全收尾。
- [x] 自动内政资源门禁已完成：粮食不足不发包；粮食转铜完成后若观察值仍不足，只等待且不重复兑换；成本表缺失或需要尚未接入余额的第三类资源时失败关闭。明确拒绝固定 10 分钟后重新读取，不进行 1 秒紧密重试。
- [x] 自动内政双端所有权已切换：桌面 `auto-domestic/auto-technology` 都映射同一 `domestic` 常驻键并只唤醒共享 tick；设置保存保持本地即时返回，停止账号不会被保存动作复活。Android Service 投影 `feature=domestic → TaskType.INTERNAL`，旧 `InternalAffairsTask` 已从生产 `TaskFactory` 移除。
- [x] 修复旧版 APK 遗留的已接受刷黄恢复账本：账本没有 `formations` 时，共享 Python 在任何治疗/配兵 mutation 前，从当前已持久化配置中为每个 exact `generalId` 要求唯一有效规则，回填并冻结到 pending；缺失、重复、兵种或数量无效时均在发包前失败关闭。已记录 `completed` 的治疗不会重复。
- [x] Android 新增纯 Kotlin 宿主级 `SharedResidentWakeGate`：每账号 deadline 互相独立，未到期时不调用 Python adapter；需人工关注时暂停自动重试；`ACTION_REFRESH`/显式重新开始可解除；刷新与在途旧 tick 竞态时，generation token 防止旧结果重新写回暂停。
- [x] 自动背包共享规划完成：每次 tick 最多选择一个动作；自动开箱只接受共享白名单并受钥匙、每轮 50 个和总动作 50 项上限约束，且优先于丢弃。配置为自动开启但缺钥匙的宝箱不会落入丢弃分支。
- [x] 自动背包装备保护完成：只有共享 161 条装备模板能够完整识别、实例 ID 有效、非名将、未强化、无炼魂/额外描述、低于 80 级且同时低于用户等级/品质阈值时才允许丢弃；任一装备元数据不完整会阻止自动装备清理并要求处理。
- [x] 自动背包恢复账本完成：动作发包前先保存 `preparing → sending`，明确成功保存 `accepted`，拒绝保存 `rejected`，回执不明保存 `uncertain`。`sending/uncertain/accepted` 在进程恢复后只刷新背包核对，不重发；真实数量部分减少也按实际消耗完成，60 秒始终无法确认则保留账本并暂停自动执行。
- [x] 自动背包双端所有权已切换：桌面 `auto-inventory` 只复用共享 tick 唤醒器，账号启动和“主号物品”保存会启动/刷新，关闭配置会停止；生产路径不再调用旧 `auto_open_inventory_items` 线程。Android adapter 放行 `inventory`，Service 过滤 `TaskType.INVENTORY`，旧 `InventoryCleanupTask` 无协议调用权。
- [x] 军情警报决策已收口到 `features/alarm.py`：使用 `recordId/battleId/state/direction/target/generalIds` 生成稳定指纹，倒计时变化不造成新事件；首次与配置变更只建基线，历史指纹持久化限长保留。
- [x] `alarmPendingEventsJson` 在任何平台日志/通知调用前落盘，并分别保存 `logWritten/notificationDelivered`；进程恢复先补投 pending，不重新请求军情或重做新事件判定。“仅日志”不调用 `NotificationPort`，异常提醒由 Python 判断 `errorEnabled` 并按 5 分钟去重。
- [x] 军情警报双端所有权已切换：桌面 `auto-alarm` 仅唤醒共享 tick，结构化警报进入账号日志；Android 桥只按 Python 给出的 `title/message/vibrate/fingerprint` 展示通知，稳定通知 ID 使 pending 重投覆盖旧通知。`AlarmTask` 失败关闭，旧 Kotlin 事件检测器已删除，`scanAlarms` 不再发包。

尚未完成：

- [x] 加体/加忠已收口为可复用的共享维护步骤；出征功能直接复用，不另写业务实现。
- [ ] `SessionAwareGameProtocolClient` 内旧刷黄/打矿协议实现已经没有生产调用者并被静态门禁隔离；物理删除牵涉接口、解析器和大量历史协议测试，按“稍复杂后置”留到下一版本，不影响当前发包所有权。
- [ ] 仍服务新手/手动 starter 的桌面旧副本入口留到下一版本单独改接共享状态机，避免牵连新手流程。
- [ ] 锁屏/Doze、设备重启和网络切换的真机回放；获得明确授权后再做单账号真实服务器成功路径。

### 下一步固定执行顺序

1. 自动背包与军情警报已按同一持久化安全门槛完成；下一步先保持离线审计和 APK 产物可重现，不在未授权时启动 Service 或发送真实游戏请求。
2. 停止态、代表性真实本地写入、页面重建和安全取消的最终 WebView 验收已完成；继续补其余本地路由 P95/P99 与授权边界内的真实 `UNCERTAIN` 视觉。operation 完成瞬间和高频压力的尾延迟专项列入下一版本，优化时不得削弱 mutation 持久化安全。
3. 按静态调用图继续物理删除旧刷黄/打矿协议副本、兼容性 `scanAlarms` 接口、自动背包死代码和桌面 starter 副本入口；每次删除后仍需全量回归，不影响已收口的生产所有权。
4. 执行锁屏/Doze、设备重启、网络切换、多账号、长稳和功耗验收；最后构建 APK，并仅在授权边界内做离线安全烟测和真实功能验证。

在上述项目完成并达到 G7 前，阶段 7 始终保持“进行中”；不得因为路由所有权已达 56/56 或取得局部性能数据而标记完成。详细证据持续记录在 `docs/core_migration/android_host_stage7.md`。
