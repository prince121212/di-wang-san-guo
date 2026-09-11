# 阶段 7：Android 宿主切换记录

> 状态：执行中
>
> 开始日期：2026-07-31

## 当前完成项

### 1. Bridge 分通道

`AssistantWebBridge` 不再使用一条全局单线程 executor。它从唯一的 `api_route_ownership.json` 读取响应类型，并分为：

- 两线程 `local-read`：账号、设置、日志、任务状态和缓存读取。
- 单线程 `local-write`：设置与其他本地原子写入，避免写入乱序。
- `network-operation(accountId)`：同账号串行、不同账号可并行。
- WebView UI 投递：按 request ID 返回短请求，并订阅共享核心结构化事件；不执行业务。

共享契约当前声明 56 条路由，其中 27 条本地路由、29 条网络 operation。JVM 并发测试证明：一个阻塞的网络请求不会延迟本地读取或写入；同账号网络任务严格串行，不同账号可以同时进展。

### 2. 账号列表切换到共享 Python

`GET /api/accounts` 已将 Android 当前所有者切换为 `shared-python`：

- Android 只读取账号、重连、配置、任务、日志摘要等平台事实。
- 共享 Python 统一计算生命周期状态、Session 是否可展示、重试倒计时、最后错误和账号卡 JSON。
- 删除了 Android 原有的 `accountArray()` 和账号卡生命周期拼装。
- 添加、启动、停止和设置页返回的单账号卡也复用同一共享投影。

真机结构验证：1 条账号的 24 个必需字段完整，敏感字段路径 0；热态 10 次样本 P50 约 39 ms、P95 约 46 ms。`nextRetryAtMillis=0` 已保持旧语义为 `reconnectAt=null`，不会显示伪 deadline。

电脑端与 Android 现在都以共享账号账本为公开事实源，账号列表、添加、启动、停止和删除路由均已切到 `shared-python`。

### 3. 军情作为首个网络异步样板

共享前端在军情页面使用 `GET /api/military/intel`：

- 电脑端仍可同步返回现有结果。
- Android Bridge 只提交请求，约 7–22 ms 返回 `202 + operationId`。
- 共享 Python operation 在后台按账号执行并持久化 `QUEUED / RUNNING / SUCCEEDED / FAILED / CANCELLED / UNCERTAIN`。
- Python 直接生成 `0x1600` 请求、通过 Android Raw HTTP 字节端口收取响应，并解析/聚合 `0x8600`；Android 不再拥有军情 opcode、解析或成功语义。
- 前端以原生 `__event` 完成事件为主，只保留 15 秒低频 `/api/core/operations/status` watchdog 恢复丢失事件；每次 Bridge 调用都保持短响应，不再用固定 30 秒判断游戏请求失败。
- `SUCCEEDED` 后仍返回原军情 JSON，因此共享页面业务代码不需要维护 Android 分支。
- 同账号、同参数且仍在途的重复查询返回同一 operation；完成后允许再次刷新。
- Android 为事件分配单调 `eventId`，页面忽略过期事件；事件携带 `progressDetails / requestSent / cancellationDenied`。
- 未完成 `operationId` 记录在 `localStorage`，页面重建后可恢复；临时状态读取失败不再产生未处理 Promise。
- 页面状态条只在 `requestSent=false` 时允许取消；已发包时明确禁用，`CANCELLED` 与 `UNCERTAIN` 分开展示。

共享 operation 在发送前仍会加入迁移期进程级账号锁，与旧后台调度器互斥。Python 回调 Kotlin 时只做一次非阻塞 `tryAcquire`；账号忙时 Python operation 在自己的网络通道内可取消地退避重试。取得锁后，Python 直接通过 Raw HTTP 发送自己生成的字节，不再进入 `SessionAwareGameProtocolClient`。

这里不能在 Python→Kotlin 同步回调中阻塞等锁：旧调度器持有账号锁期间，协议结果回写可能再次调用共享 Python；反向阻塞会形成“调度器持账号锁等 Python / Python operation 等账号锁”的锁反转。当前非阻塞握手与 Raw HTTP 直达路径消除了已迁移命令的这个重入环。`AndroidSharedCorePortBridge.accounts` 同时改为延迟初始化，避免 Bridge 构造时重入尚未发布的 `SharedPythonCoreHost`。

### 4. 本地设置写入切片

`POST /api/military/future/save` 已同时切换电脑端和 Android 的业务所有者为共享 Python：

- 押镖、寻宝、无损和副本的字段规范化、兼容别名、就绪状态和未抓包功能的失败关闭语义只保留在 `dwpm_core/settings.py`。
- 共享路由返回结构化本地写入计划，并显式标记 `networkRequired=false`。
- 电脑端只把计划写入现有 SQLite 账号习惯库；Android 只把计划写入 `LocalConfigRepository`。
- Android Kotlin 中原有的 `future()` 业务分支已删除，不再出现“电脑端可保存、Android 直接拒绝”的分叉。
- 该路由只完成本地校验和落盘，不启动 Service，不等待游戏服务器。

`POST /api/liubu/save` 也已切换为两端共享设置写入计划：

- 作物默认值、允许列表、“只有金银花种植可发送”门禁、未确认动作和用户提示均由共享 Python 生成。
- Kotlin 中原有的 `ministries()` 映射已删除。
- 设置缺少 `settings` 时在落盘前拒绝；未确认作物可保存但 `activationAllowed=false`。
- 电脑端不再在已落盘后因六部在线检查将保存报为失败。账号正在运行时只快速投递后台任务；未运行时返回“设置已保存，等待开始”。任务启动异常也不会反向覆盖本地保存成功。

`GET /api/accounts/settings` 已切换为共享本地读取路由：

- 电脑端只提供 SQLite 设置快照和公开账号卡；Android 只提供 `LocalConfigRepository` 快照和公开账号卡。
- 文件名、路径、`exists`、稳定排序的 JSON 内容和最终响应结构由共享 Python 统一生成。
- Android 已删除 `selected.toString(2)` 这一第二套返回拼装。
- 共享路由会在返回前拒绝设置快照中的密码、Token、Secret 或 Credential 字段。

真机连续 10 次热态读取结果：P50 38.3 ms，P95/P99 39.9 ms；返回 1 个可解析的 `account-config.json`，敏感路径 0。取样前后游戏请求历史哈希不变，`AssistantForegroundService` 未启动。

`POST /api/formations/save` 已切换为共享本地写入计划：

- 将领 ID 去重、每行上限、兵种与兵力校验、跨行重复检查、将领名快照和未同步 ID 判定均由共享 Python 生成。
- 未同步将领 ID 不会被删除；设置可正常落盘，但 `activationAllowed=false`，禁止发包。
- Kotlin 中原有的 `formation()` 业务映射已删除。
- 电脑端在账号运行时仍可在落盘后快速投递旧后台配兵任务，但任务启动异常不再覆盖本地保存成功。
- Android 在落盘后快速提交独立 `/api/formations/apply` mutation operation；保存响应不等待服务器。
- 停止账号仍可保存配兵，并明确返回“等待账号启动”，不进入网络适配器。

共享路由所有者契约当前声明 56 条路由，Android 和电脑端的 `shared-python` 所有权均为 56/56。新增收口包括区域/指南、账号添加/启动/停止/删除以及自动化启停。该数字是路由业务所有权契约，不代表路由之外的后台状态机已全部迁完，也不代替最终 APK 真机验收。

### 5. 其余本地设置与视图切换

- `POST /api/mine/save`、`POST /api/settings/save`、`POST /api/raid/execute`、`POST /api/lossless/execute` 和 `POST /api/dungeon/execute` 均使用共享 Python 写入计划。
- 上述混合接口已把本地落盘与后续网络执行分开；停止账号可保存，不会因游戏网络未就绪而反向报保存失败。
- 系统/账号日志、自动化状态、成功记录、日志写入/清空、提示关闭和山贼/矿点地图均由共享 Python 投影。
- Android 已删除 `TaskSuccessRecordPolicy.kt`、`LocalMapApiMapper.kt` 和对应重复业务测试；电脑端 SQLite 与 Android 本地记录只向共享核心提供原始事实。

### 6. 真实配兵持久化 operation

- `/api/formations/apply` 由共享 Python 负责规则拆分、最小持久化 payload、在途合并、状态和最终结果。
- mutation 采用两阶段账号锁：Python 先非阻塞取得 JVM 账号执行锁，然后持久化 `requestSent=true`，最后才调用 Android 字节 HTTP 传输。
- 服务器明确拒绝记为 `FAILED`；已越过发送边界后的断联或异常记为 `UNCERTAIN`，不会自动重放可能已成功的配兵。
- 批量配兵由共享 Python 拆成单将领执行行并逐条生成、解析 `0x1226/0x8226`；一键卸兵也由 Python 读取将领状态并对空闲带兵将领发送数量 0 的同一协议。
- Kotlin 中 `applyFormationsFromSharedCore`、`unassignAllTroops` 和专用网络适配白名单已删除；后续又删除了通用 `executeGameCommand`/Session 命令适配链，Android 只剩 `executeRawHttp`。
- 前端在保存返回后只在后台监听 operation，不用网络耗时阻塞“保存成功”反馈。

### 7. 状态、心跳与配兵原始命令

- `/api/state/refresh` 的全部 scope、`/api/heartbeat`、`/api/military/intel`、名将拜访候选、掠夺封地和一键卸兵已由共享 Python 拥有输入与结果语义。
- 状态刷新直接执行 `0x1016/0x8004`、可选 `0x1104/0x8104` 与 `0x1600/0x8600`；心跳直接执行 `0x3110/0xa110`。角色、资源、将领、军队、背包、军情及 A110 将领状态证据都由 Python 解析并写回同一公开账号账本。
- Android 已删除 `executeNetworkOperation`、`handleSharedCoreNetwork`、`stateRefresh`、`militaryIntel` 和 `heartbeat`；`LocalProtocolOperationService` 只剩本地 dashboard 投影。电脑端也删除三条 `_desktop_shared_*` 业务适配，改为调用相同 Python workflow，宿主只镜像规范化结果给迁移期旧后台线程。
- `/api/troops/assign`、`/api/troops/refill`和 `/api/troops/heal` 使用 Python `make_packet → RawHttpPort → parse_response`；Python 生成 payload、解析回执并决定 `SUCCEEDED / FAILED / UNCERTAIN`。
- 配兵先校验闲兵和统兵上限；补兵校验全部将领回执；治疗共用桌面端计划器，包含铜钱保底与最多一次固定 10 万粮食兑铜重试。

### 8. 单次开箱原始命令工作流

- `/api/inventory/open-one` 的确认词、允许物品、青铜/精铁钥匙前置检查和最小持久化 payload 已由共享 Python 拥有。
- Python 用 `0x1104/0x8104` 刷新并解析背包，仅在前置检查通过后持久化 `requestSent=true`，再发送 `0x3144`。
- `0xA144` 明确拒绝为 `FAILED`；缺回执或发送后断联为 `UNCERTAIN`；已获得成功回执后的背包刷新失败仅保留警告，不反向改成不确定态。
- Android 已删除 Kotlin `inventoryOpenOne` 路由，宿主仅执行 Python 提供的 URL、HTTP 字段和原始请求字节。电脑端手动开箱已共用同一输入计划、背包前置规则与奖励文本归一化。

### 9. 日常签到、竞技币与国家俸禄

- `/api/daily/sign-in/claim` 由 Python 发送 `0x6202`，解析 `0x8134/0xe202`，再执行可选的 `0x1134` 每日金钻宝箱。签到已确认后，可选宝箱失败只作警告，不覆盖签到成功。
- `/api/daily/arena-coins/claim` 由 Python 先用 `0x6260` 做可取消预检，再持久化 `requestSent` 并发送 `0x6266`；`0xe266` 重复领取按当日已完成处理。
- `/api/daily/salary/claim` 由 Python 生成 `0x314b` 请求并解析 `0xa14b`，包括铜钱、粮食与重复领取语义。
- 三条路由都使用同一账号锁、最小持久化 payload 和 `FAILED / UNCERTAIN` 发送边界；真实 fixture operation 测试已覆盖重复领取、成功俸禄、发送前失败与发送后缺回执。

### 10. 其余手动日常原始命令工作流

- 自动捐献由 Python 按当前等级生成铜钱、粮食、科技积分三条请求；自定义捐献在 Python 中按请求值、可用资源和等级上限取最小值。
- 国家征收由 Python 扫描州/郡/县城、查询状态，按铜钱倒序和城池层级并列规则选择，并维持账号级当日配额语义。
- 城主征收由 Python 解析 `0x8318` 自有城池，并将成功、已征、不可征与失败回执分类为确定的当日终态。
- 名将候选查询与拜访均已脱离 Kotlin 解析适配器；Python 拥有分页、候选顺延、俘虏跳过和“拒绝征召也算完成今日拜访”的语义。
- 所有只读预检在 `requestSent=false` 时可取消；第一条 mutation 前先持久化发送边界，缺回执为 `UNCERTAIN`。Kotlin 已移除这些手动路由和对应业务方法。
- 电脑端全部 9 条手动日常路由也已切换到同一工作流；旧 HTTP Handler 中的直接业务调用已删除。
- `DailyCompletionPort` 只让 Android/电脑宿主保存计数。Python 统一判定已完成时不发包、服务器确认/重复领取/明确跳过后写锁，失败、不确定和部分成功不写锁；自定义捐献不写自动捐献完成锁。竞技币端口使用显式时间并按中国时区 22:00 切换。

### 11. 刷黄与打矿正式出征共享工作流

- `/api/brush/execute` 与 `/api/mine/execute` 均由共享 Python 负责输入校验、正式出征前状态检查、必要的加体/加忠/治疗/配兵前置、payload 生成和回执判定。
- Android 只通过 Raw HTTP 发送 Python 生成的完整请求字节；旧 Kotlin 手动刷黄、打矿业务实现已从 `LocalProtocolOperationService` 删除。
- 电脑端两条手动路由也提交相同的持久化 operation，并通过 `DesktopRawHttpPort` 发送 Python 生成的完整请求字节；离线 fixture 已证明请求字节与 Android 相同。
- 正式 mutation 已发送但缺少对应回执时统一进入 `UNCERTAIN`，禁止自动重发；桌面前端收到 `202 + operationId` 后使用同一 operation 客户端等待终态，不再把网络等待误报为固定 30 秒超时。
- 正式出征之后的持久化恢复与撤防闭环已收入共享 Python，见下一节；双端生产常驻调度也已切换到同一共享 tick。

### 12. 共享登录核心与 Raw HTTP 收口

- `dwpm_core/account/login.py` 现在唯一拥有平台/passport 参数、区服选择、`0x1003/0x8003` 登录、`0x1004/0x1016/0x8004` 角色同步、背包/日常/自有封地初始化、当乐 SDK 加解密和 Session 事实生成。
- 共享核心直接写公开账号账本和 Session 密钥端口；Android 不再二次拼装登录结果，只在成功后启动前台服务。账号 operation 被受理为 `202` 时不会提前启动 Service。
- Android 后台自动重登调用 `SharedPythonCoreHost.reloginAccount`，与前台添加/启动复用同一登录实现。`LocalAccountLoginService.kt` 和 `RealGameProtocolClient` 中的完整 passport 登录/解析已删除。
- `RawHttpPort` 同时供登录和已迁移游戏命令使用。Android `executeRawHttp` 只处理 URL、query、headers、HTTP 方法和原始字节，并在游戏请求建连前再次检查前台执行所有权；不解析 opcode 或成功语义。
- Android `executeGameCommand`、`LocalProtocolOperationService.executeSharedCoreGameCommand`、`LocalProtocolOperationRunner.executeSharedCoreLockedGameCommand`和 `SessionAwareGameProtocolClient.executeSharedCoreGameCommand` 均已删除。

### 13. 刷黄战后恢复、打矿撤防与 recovery tick

- 刷黄出征前保存 `brushPendingRecoveryJson`；`CoreFacade` 每次使用新鲜 `0x1016/0x8004` 证据，只有观察到忙碌→回闲或经过完整刷新宽限期仍为空闲，才执行按封地治疗、恢复保存配兵和可选清理邮件。
- 打矿出征成功后保存 exact battleId、坐标和将领；`CoreFacade` 使用新鲜 `0x1600/0x8600 + 0x1016/0x8004`，只有三类证据匹配且状态为驻守时才生成 `0x1526`，并解析 `0x8526`。撤防成功后继续等待全部将领回闲才清账。
- 治疗、配兵、清邮件和撤防均有独立持久化子步骤。mutation 发包前保存 `sending`；发包后异常保存 `uncertain`，再次 tick 安全停止并禁止自动重放。
- 新增内部 `automation:recovery-tick:v1`，通过现有每账号 operation lane 快速受理、持久化运行并返回 `nextWakeAtMillis`。Android `SharedPythonCoreHost` 已暴露提交方法。
- Android Service 已在旧调度器前提交该入口，过滤刷黄/打矿旧任务，并把 Python 返回的 `nextWakeAtMillis` 纳入 Handler/Alarm；Kotlin 不再拥有这两类生产发包权。

### 14. 掠夺单次出征与回闲闭环

- 共享 Python 新增 `automation:raid-action:v1`，统一执行封地查询、将领前置检查、`0x1520/0x8520` 预出征门禁、`0x1522/0x8522` 正式出征和正 battleId 判定。
- 正式动作前持久化 `raidPendingReturnJson` 的 `sending` 边界；缺少 `0x8520` 时确定停止且不发送 `0x1522`，正式出征回执不明时保存 `uncertain` 并禁止自动重放。
- `automation:recovery-tick:v1` 已识别掠夺 pending，使用新鲜将领状态观察忙碌与回闲，全部回闲后才清除账本。
- 电脑端常驻 `execute_raid()` 已改为提交该共享 operation 并等待持久化终态；Android `SharedPythonCoreHost.submitRaidAction` 已提供相同入口。
- 掠夺规则游标、每日限制和下一业务时间已接入共享 tick；Android Service 过滤 `AUTO_LOOT`，旧 `AssistantTasks` 不再拥有生产触发或发包权。

### 15. 无损共享单次状态机与生产宿主切换

- 新增 `automation:lossless-action:v1`：Python 统一读取/解析 `0x1900/0x8900` 状态、`0x1904/0x8904` 目录、`0x1906/0x8906` 阵容和 `0x1908/0x8908` 选关，并保留电脑端 10 级卫兵筛阵与 7 级往返刷新规则。
- 出征前继续复用共享治疗、加体、保存配兵与可选补满兵；Python 生成 `0x1520/0x1522`，缺少 `0x8520` 时不发送正式出征，`0x8522` 回执不明进入 `UNCERTAIN`。
- 无损进入前置维护即保存 `losslessPendingBattleJson`；治疗、加体、配兵、补兵或选关每次 mutation 前更新子步骤 `sending`，中断后只读核对并禁止重放。出征成功后由 recovery tick 处理战斗、回闲和结算；结算保持电脑端原始的同一请求包 `0x1902 + 0x1904`，发包前持久化 settlement 边界。
- 电脑端 `lossless_worker` 已改成薄唤醒循环，只保留旧指挥中心互斥、停止等待当前 pending 和页面展示，所有无损业务决定由 `CoreFacade` 返回。
- Android Service 现在只提交统一 `SharedResidentAutomationAdapter`；旧 `LOSSLESS` 任务在进入 Scheduler 前被过滤。逐功能 `SharedLosslessActionAdapter` 及 `GameProtocolClient.runLossless` 过渡入口已删除，避免重新形成第二条调度链；`UNCERTAIN` 仍由共享 operation 明确冻结。
- Kotlin `LosslessProtocolShapes.kt`、`SessionAwareGameProtocolClient` 的旧无损发送 fallback 和 7 项重复协议测试已删除；新增静态门禁保证生产源码不再出现 `sendLosslessCommand` 或 `REAL_LOSSLESS_DISPATCH_*`。规则行游标和下一业务时间也已收回共享 tick，Android Service 过滤旧 `LOSSLESS` 生产任务。

### 16. 副本共享状态机与双端生产入口切换

- 新增 `automation:dungeon-action:v1`：Python 统一读取 `0x1938/0x8938` 状态和 `0x1930/0x8930` 目录，执行 loop/clear 选关、跳过每章多人末关、共享治疗/加体/保存配兵/补兵前置，并生成 `0x1520/0x1522`。
- `dungeonPendingRunJson` 在前置 mutation 前建立，分别记录前置、预出征、正式出征和开箱发送边界。缺少 `0x8520` 时不发送正式出征；`0x8522` 或 `0x893e` 回执不明进入 `UNCERTAIN`，恢复时禁止重放。
- 出征成功后共享状态机使用 `0x1938` 与 `0x1702/0x8702` 跟踪战斗，确认将领回闲后读取 `0x193d/0x893d`、开箱，并在 clear 模式通过实时目录确认通关；明确战败或连续无法确认通关时暂停，避免重复出征。
- 电脑端常驻 `dungeon_worker` 已变为薄唤醒循环；Android 通过统一 resident operation 执行副本，旧 `DUNGEON` 任务在进入 Scheduler 前被过滤。逐功能 `SharedDungeonActionAdapter` 与 `GameProtocolClient.runDungeon` 过渡入口已删除。共享 recovery tick 的 pending 优先级现为“打矿 > 无损 > 刷黄 > 掠夺 > 副本 > 将领维护 > 六部 > 自动内政”。
- Android `DungeonProtocolShapes.kt`、`DungeonPendingRun.kt` 和 `SessionAwareGameProtocolClient` 中约 700 行旧副本发送实现已删除，生产 `runDungeon` 缺少共享 gateway 时失败关闭。仍被桌面新手流程和手动 starter API 使用的旧 `execute_dungeon` 是独立入口，本版本不顺带改动新手引导，已列入后续迁移。

### 17. 主要常驻任务与日常共享调度生产切换

- `residentAutomationConfigJson` 由共享 Python 从双端现有账号习惯重新归一；`residentAutomationStateJson` schema 2 保存刷黄、打矿、掠夺、无损、副本、六部和日常的规则游标、每日次数、deadline 与最近结果。宿主不再计算下一条业务动作，副本/刷黄页面计数也直接投影该状态。
- `automation:recovery-tick:v1` 在没有 pending 时按共享优先级选择到期功能，并在高优先级任务进入等待后重新计算其他到期项，避免低优先级永久饥饿。找目标、正式动作、恢复、六部种菜和七类日常均直接复用现有共享 workflow。
- 刷黄/打矿在出征前治疗、加体、加忠或配兵之前建立 pending 账本；任何前置或正式出征 `sending/uncertain/failed` 都只允许后续只读核对，不会由新 tick 自动重做。
- Android `SharedResidentAutomationAdapter` 在 Service 的后台 scheduler 线程同步本地习惯、提交并等待持久化 operation。Service 在进入旧 `TaskScheduler` 前过滤刷黄/打矿、掠夺、无损、副本、六部及七类日常任务，Python 的 `nextWakeAtMillis` 与 Session/余下旧任务 deadline 一起交给现有 Handler/Alarm。
- 电脑端对应生产 worker 已改为薄唤醒入口；当前 `allowedFeatures=[mine,lossless,brush,raid,dungeon,general,ministry,domestic,inventory,alarm,daily]` 与 Android 过滤集合保持一致。旧 Python/Kotlin 实现仅作为待机械删除的非生产代码，不能重新进入调度批次。
- 副本明确战败增加同源人工确认：用户重新保存并启用副本配置时可归档明确战败；不明确 mutation 边界不能借保存配置清除。
- 六部种菜在发包前保存 `ministryPendingPlantJson`；回执不明时只查询菜地核对，禁止自动重种。七类日常复用共享 `DailyCompletionPort`，竞技币保持中国时区 22:00 周期，`UNCERTAIN` 或部分成功在当前周期禁止自动重放。

### 18. 首批旧所有者机械清理

- 桌面刷黄、打矿、掠夺、无损、副本和六部的六组 `_legacy_*_worker` 已全部删除；生产薄 worker 只唤醒共享 tick，静态测试要求旧名称不得重新出现。
- Android `AutoLootTask`、`LosslessTask`、`DungeonTask`、`SixMinistriesTask`、`DailyPipelineTask` 和七类日常任务仅保留配置载体；若过滤门禁回归失效，它们也只会返回“共享 Python 已接管”，不会调用协议或发包。
- `SessionAwareGameProtocolClient` 已删除 `runAutoLoot/runSixMinistries/runDungeon/runLossless`、国家/城主/名将日常扩展和掠夺封地的第二套协议入口；逐功能无损/副本 adapter 与测试一并删除，统一由 resident adapter 提交。
- 迁移状态与 V1 覆盖验证器已改用共享 Python workflow、resident adapter 和失败关闭门禁作为证据，不再要求已退役 Kotlin 文件存在。

### 19. 第二批旧任务机械清理与真实剩余边界

- Android `ShuaHuangTask/MineTask` 已从完整业务状态机缩为纯配置标记；即使 Service 过滤门禁失效，`prepare/step` 也只会返回“共享 Python 常驻核心执行”，不会验证 Session、搜索目标或发包。
- `BanditPrefetchTask/MinePrefetchTask` 已删除。找黄、找矿、规则游标、缓存投影和下一扫描时间全部由共享 Python tick 决定，不再先由 Kotlin 扫一遍地图。
- 无条件创建的 `StateRefreshTask` 已删除。状态、心跳和军情继续通过共享 Python 路由或实际业务 tick 按需刷新，Android 不再额外查询一轮将领、编队和军情。
- 独立 `FoodToCopperTask` 已删除：电脑端没有这种无业务前提的周期兑换任务；`foodToCopper/copperFloorWan` 配置仍保存，只有共享 Python 的刷黄、治疗、内政等真实前置条件需要时才兑换。
- 无生产创建入口的 `FormationUpdateTask` 已删除；手动/批量配兵继续只走共享 Python operation。
- `AssistantTasks.kt` 从 1746 行降到 362 行。Android `main` 静态门禁确认，除待物理删除的接口/协议实现文件外，没有生产调用者再使用 `dispatchFormation/searchMines/occupyMine/withdrawMineDefense` 等旧链路。
- 迁移状态审计已纠正证据口径：历史 Kotlin Service 的真机刷黄记录只能证明旧版本曾可用，不能将当前共享 Python 宿主标为真机完成。

### 20. 停止账号的当前任务状态收口

- `taskOverview` 的运行判定现在要求“账号启用、`savedTasksStarted=true`、`AssistantForegroundService` 持有执行权”同时成立。任一条件不成立，持久化的旧 `RUNNING/WAITING/SLEEPING` 只作为历史状态保留，当前概览统一降级为停止且 `running=false`。
- `stateRefresh`、`banditPrefetch`、`minePrefetch`、独立 `foodToCopper` 和旧 `formations` 调度类型已从当前任务栈、任务状态列表、概览映射和运行提示中过滤；历史日志不删除，仍可在记录区查看。
- 新增纯投影回归，覆盖停止态降级、三个执行条件缺一即停止、退役类型不进入当前投影；连同后续本地保存门禁回归，Android JVM 当前 484/484 通过。
- 新 Debug APK 已覆盖安装到设备 `27a83c9c`。账号 `202` 的真实 WebView 返回 `savedTasksStarted=false`、空任务栈，六类常驻任务全部 `running=false`；页面视觉显示“当前没有后台任务”和六项“未运行”，不再出现运行中/排队中的矛盾。整个检查期间前台执行 Service 未启动，请求健康账本哈希保持不变。

### 21. 本地设置执行门禁与页面重建恢复

本地写入真机验收首次暴露了第二个必须如实记录的门禁缺口：账号卡显示停止时，旧持久化数据仍可能保留 `enabled=true` 和 hosting 偏好。旧实现仅检查 `account.enabled`，保存刷黄设置后调用 `AssistantForegroundService.refresh()`，意外复活了已停止的 Service。

该次排查产生 8 次游戏请求：1 次 Session/状态探测、5 次配兵状态刷新、1 次治疗前查询和 1 次治疗 mutation。发现后立即调用账号停止并确认 Service 退出；没有刷黄、打矿或出征请求。一次治疗 mutation 已发生，无法伪装成“纯本地验收”，也不能删除这段审计记录。

修复内容：

- `LocalSettingsExecutionPolicy` 只有在“账号启用、登录态可执行、前台执行所有者已存活”同时成立时才允许设置保存后的任务立即启动。
- 设置保存只刷新已经存活的 Service，持久化 `enabled` 或 hosting 偏好不能再从页面写入路径复活 Service。
- 页面线程不再同步调用 `configureResidentAutomation`；配置先同步落盘，运行中的 Service 会异步刷新，停止账号则等下次显式启动时由 `SharedResidentAutomationAdapter` 在 tick 前同步。
- 响应新增 `localWriteCommitted=true`，并用 `waitingForAccountStart` 明确区分“本地已保存”和“后台已开始”。
- `app.js` 在注册 operation 托盘监听器后主动调用一次 `recoverTrackedOperations()`，消除首次恢复事件早于页面监听器的竞态；底层状态读取仍会合并，不会复制 operation。

最终 APK 真机证据：

- 停止账号原样保存同一配置 3 次分别为 53.2、49.0、52.0 ms；配置前后一致，账号始终为 stopped，Service 未启动。
- 页面重建前创建 300 秒 Debug 模拟 operation；重载后 1 秒内恢复“准备中/取消”，点击真实页面按钮后持久化终态为 `CANCELLED`，提示“未向游戏服务器发送请求”，`localStorage` 跟踪项清空。
- 修复后整个验证窗口请求健康账本 SHA-256 始终为 `aaebaf690f33be59a808762571ddb63fd505229b54f0624052da5266447bf515`，系统只存在 WebView 沙箱 Service。

审计后仍明确后置到下一版本的内容：

- 军情警报已在本阶段后续收口：事件指纹、持久化去重、通知/震动决策和进程重建恢复均已移入 Python，Kotlin 只保留系统通知展示端口。
- `SessionAwareGameProtocolClient` 内已无生产调用者的刷黄/打矿协议副本：当前已静态隔离；物理删除牵涉接口、解析器和历史协议测试，按“稍复杂后置”处理。
- 仍服务桌面新手/手动 starter 的旧副本入口：下一版本单独接入共享副本状态机，避免本版牵连新手流程。

### 22. 自动内政共享状态机与双端生产入口切换

- 共享 Python 新增稳定的内政规划器：按封地 ID 和配置顺序选择“最低大厅优先 → 空地建造 → 建筑升级/科技升级”，建筑与科技同时可用时按持久化轮次交替，避免任一队列长期饥饿。每个 tick 最多提交一个 mutation；确认成功后返回 1 秒 deadline 继续填队列，没有动作时使用 10 分钟或最早建筑完成时间。
- `domesticPendingActionJson` 保存整次候选、配置快照和 `resourceExchange/action` 两个子步骤。mutation 前先写 `sending`，明确成功写 `accepted/completed`，明确拒绝写 `rejected`，回执不明写 `uncertain`；pending 清理、`domesticLastActionJson` 和 `residentAutomationStateJson` deadline 由一次账号状态更新共同提交。
- 进程恢复先执行只读 `0x1016/0x8004 + 0x1246/0x8246`。候选已变化时归档旧计划并重新规划；候选未变化的 `sending/uncertain` 只展示阻断且禁止重发；持久化 `accepted` 只依据已经落盘的成功回执安全收尾，不重新发送动作。
- 资源门禁读取共享角色状态与同一成本表。粮食不足不发包；粮食转铜只执行一次，完成后观察铜钱仍不足则等待且不重复兑换；成本缺失或需要尚未接入余额的第三类资源时失败关闭。服务器明确拒绝后固定 10 分钟再读取，避免 1 秒紧密重试。
- 桌面 `auto-domestic` 与 `auto-technology` 均映射为同一个 `domestic` 常驻键，旧自动内政业务循环已删除；设置保存仍只做本地持久化和异步薄唤醒，停止账号不会被保存操作复活。Android `SharedResidentAutomationAdapter` 放行 `domestic`，Service 将结果投影为 `TaskType.INTERNAL`，`TaskFactory` 不再创建 `InternalAffairsTask`。
- 新增 16 项自动内政专项测试，覆盖大厅/空地/最低级/轮换、动态 deadline、粮转铜、进程重建、明确拒绝、候选变化、`sending/uncertain/accepted`、第三资源失败关闭、双端配置一致和 Android 旧生产入口归零。

### 23. 旧刷黄恢复账本兼容与 Android deadline 去重

- 真机日志定位到 `BRUSH_RECOVERY_FORMATION_MISSING`：旧 `V0.0.17` 在刷黄出征已确认成功后仅保存两名将领和目标，没有把恢复配兵规则冻结进 `brushPendingRecoveryJson`。治疗已完成，但恢复配兵时因账本缺字段失败。
- 共享 Python 新增只对旧账本生效的兼容回填：从当前已持久化 `residentAutomationConfigJson.formations` 中，为每个 pending `generalId` 要求恰好一条启用且兵种/数量有效的规则。在任何治疗或配兵 mutation 前将快照写回 pending，并保存来源、时间与 SHA-256；不完整或歧义配置继续发包前失败关闭。
- 已落盘为 `completed` 的按封地治疗子步骤保持幂等，只恢复两名将领的 exact 配兵，全部明确成功后才清理账本。
- Android 新增 `SharedResidentWakeGate`：每账号记住 Python 返回的 `nextWakeAtMillis`，旧任务的其他 tick 提前唤醒时不调用 adapter；截止时间最小间隔为 1 秒，多账号独立。`requiresAttention` 暂停自动重试，显式开始或配置刷新后解除；generation token 防止刷新前的在途结果把旧暂停重新写回。
- 该兼容修复完成时，真机仍运行旧 APK 和旧 Service；当时没有停止 Service、修改手机账本、安装 APK 或启动新游戏动作。后续安装状态以“当前回归证据”中的最新记录为准。

### 24. 自动背包共享状态机与双端生产入口切换

- 共享 Python 以一个确定性规划器统一自动开箱、指定物品丢弃和装备丢弃。每个 tick 只允许一个 mutation；开箱优先于丢弃，每轮最多处理 50 项动作和开启 50 个物品，缺少钥匙的已选宝箱保持不动。
- 共享核心内置 161 条装备模板。装备实例只有在元数据完整、非名将、未强化、无炼魂/额外描述、低于 80 级并同时低于用户设置的等级和品质阈值时才允许丢弃；任一装备元数据缺失会阻止自动装备清理。
- `inventoryPendingActionJson` 在动作前保存 `preparing`，越过发送边界前更新为 `sending`；服务器明确接受、拒绝或回执不明分别保存为 `accepted/rejected/uncertain`。成功回执后仍刷新 `0x1104/0x8104`，只有物品真实减少或装备实例消失才完成账本；部分减少按实际数量收尾。
- 进程恢复时，`preparing/failed-before-send` 可以安全释放并重新规划；`sending/uncertain/accepted` 只做只读刷新，禁止重发；60 秒内仍不能确认会保留账本、返回 `requiresAttention` 并暂停自动重试。
- 桌面新增 `auto-inventory` 薄唤醒任务并复用统一 resident worker。账号启动和“主号物品”保存会启动或刷新该任务，配置关闭会停止；旧 `auto_open_inventory_items` 函数只保留兼容定义，生产路径已无调用者。
- Android adapter 的 `allowedFeatures` 与 Service 的共享任务过滤均加入 `inventory`；`InventoryCleanupTask.prepare/step` 直接返回共享所有者失败关闭结果，回归证明不会触达 Kotlin 协议。
- 该自动背包切换节点当时新增 11 项 Python 专项测试，当时全量结果为 Python 822/822、Android 487/487；本文“当前回归证据”已更新为军情切换后的最新数字。

### 25. 军情警报共享状态机与最后一个 Kotlin 所有者收口

- 新增 `dwpm_core/features/alarm.py`，从共享 `0x1600/0x8600` 军情快照分类来袭与普通军情。指纹优先使用 `recordId/battleId/state/direction/targetId/generalIds`，剩余时间或展示文本变化不会制造新通知。
- `residentAutomationStateJson.alarm` 持久化配置哈希、首次基线、当前指纹和最近 200 个历史指纹。首次运行和配置变更只建基线，不重放当前已存在的军情。
- 新事件在任何宿主日志/通知调用前先保存到 `alarmPendingEventsJson`，分别记录 `logWritten/notificationDelivered`。进程恢复优先补投 pending，不重新请求军情或重做新事件判定；平台通知端口失败时 30 秒后再补投。
- “仅日志”事件仍进入结构化账号日志，但 Python 不调用 `NotificationPort`。Android 桥只使用 Python 给出的 `title/message/vibrate/fingerprint`；通知 ID 使用稳定指纹哈希，pending 重投会覆盖同一通知而不是新增重复通知。
- Android 宿主的调度异常不再用 Kotlin 读配置决定通知；`emit_host_alarm_error_json` 由 Python 判断 `errorEnabled`，对相同来源+消息持久化去重 5 分钟。
- 旧 schema 兼容已补齐：没有新字段时会从旧 `currentFingerprints` 平滑继承当前基线；共享设置计划与 Android mapper 同时保留 `incomingKeywords`、`vibrateOnAlarm`，用户保存其他配置不会丢失警报筛选或震动设置。
- 桌面新增 `auto-alarm` 薄唤醒任务和真实 `NotificationPort`；共享警报进入既有账号日志。Android adapter/Service 放行并过滤 `alarm/TaskType.ALARM`，`AlarmTask.prepare/step` 失败关闭。旧 `MilitaryAlarmEventDetector` 已删除，`SessionAwareGameProtocolClient.scanAlarms` 只返回 `SHARED_ALARM_OWNER`，不能发包。
- 迁移审计现返回 `remainingKotlinBackgroundOwners=[]`。代码所有权收口已完成，但总目标仍为 `objectiveComplete=false`，因为用户授权的真机功能、锁屏/Doze、网络切换、设备重启和抓包验收尚未完成。

### 26. 宝物固定表解析与内置 operation 托盘收口

- 真机 `V0.0.18` 的 0x8104 响应声明 45 个道具栈，但 Android 只携带 41 条默认名称，固定表遇到未知道具 ID 后被整体拒绝并进入逐字节兜底扫描。缓存结果中 45 条有 36 条误判为 `itemId=0`、40 条偏离真实 12 字节记录边界，装备数也被误报为 0；解析器把错误结果当作成功，因此日志中没有异常堆栈。
- 共享核心新增完整 758 条连续道具名称表，电脑端与 APK 直接导入同一 Python 数据。固定表的结构合法性不再依赖名称是否已知；超出名称表的新 ID 保留为 `道具#ID`，不会破坏整表。旧兜底扫描禁止接受错位的 ID 0，安全解析数与声明数不一致时显式返回 `parseError`。
- 新增回归覆盖真实历史 0x8104 抓包的 26 个道具栈和 7 件装备、真机形状中的将印/疾风符/凝魂晶石、未知道具占位及固定 12 字节对齐；自动背包 11 项安全边界和日常背包相关回归继续通过。
- `networkOperationTray` 保留在 DOM 中供 operation 事件、页面恢复和终态处理使用，但通过 HTML `hidden/aria-hidden` 与 CSS `display:none!important` 双重隐藏；网络请求仍按真实服务器完成时间返回结果，不恢复固定超时。
- `V0.0.18` 日志同时确认一项独立未完成问题：刷黄 pending 等待回闲时，其他已到期功能会把 30 秒恢复 deadline 覆盖成立即唤醒，造成约 1.68–1.9 秒一次的只读状态查询。该问题已在 `V0.0.34` 修复（息屏等待期 tick 间隔 13.9s → 31.0s，19 分钟深度 Doze 真机实测），并补了 deadline 回归。

## `nextWakeAtMillis` 的两种含义（`V0.0.43`）

同一个字段同时被当作「这个功能下次何时需要处理」和「这个账号下次何时该被唤醒」，而 Kotlin 侧的 `SharedResidentWakeGate` 是**按账号**的。两条真机故障都源于此，且都表现为「结论过期后没有任何东西重新评估它」：

- 恢复探针原先按错误码白名单判定可恢复性，未列出的错误码就永久静默隔离。副本因一次 8 分 39 秒的人为中断超过 `battleTimeoutMillis` 而带上 `requiresAttention`，将领维护则卡在一条早已失效的「宝库没有活血丹」上——两者的发送边界都是 `accepted`，是**确定**结果，本可以自愈。判据改为只看在途 mutation 的结果是否未知：只有 `sending`/`uncertain` 才需要人工，见 `AMBIGUOUS_SEND_STATES`。
- 将领维护完成后返回自身 10 分钟节奏，账号级 wake gate 照单全收，把已经到期的副本和刷黄一起挂起 10 分钟。原先的 `_pendingReleased` 是个显式标志，只有 2 处工作流记得设置；改为从「pending 记录已清空」这一事实推导——车道已经交还，就不该再用它的 deadline 关住整个账号。

`V0.0.43` 真机验证：`isolated=` 消失；副本恢复连续执行（每轮约 1 分 45 秒）；战斗期间让位给刷黄扫描并完成出征（`battleId=31772342`）；将领维护完成后 14 秒即继续服务刷黄，不再出现 10 分钟停摆。

## 一次道具拒绝停掉整个账号 3 小时（`V0.0.47`）

08-28 15:36:16，将领 446076 的活血丹被服务器拒绝（`使用失败状态 -1`）。到 18:56 为止，该账号 3 小时 20 分钟内没有任何出征，`local-scheduler` 每 60 秒照常打点，但**一条 `shared-resident` 日志都没有**。三层缺陷叠加：

1. **已知结果被当成未知。** Kotlin `SharedResidentAutomationAdapter` 用 `attention = UNCERTAIN || requestSent` 判定。请求确实发出去了，但 operation 是 `FAILED`——服务器明确答复了。已发送 + 明确失败是**确定**结果。判据改为「结果确实未知」：`UNCERTAIN`，或越过发送边界后被取消。
2. **功能级事实被提升为账号级。** wake gate 是**按账号**的，却接受了一条只属于 `general` 的结论，于是 `pausedForAttention=true`、`nextWakeAtMillis=null`，**永久**暂停——`SharedResidentWakeGate` 原设计就是「等显式启动或配置刷新才解除」。副本和刷黄与活血丹毫无关系，且当时一个在战斗中、一个在等回闲，全部被一起冻住。现在：能归因到单个功能的失败不再暂停账号；真正的账号级不确定改为 5 分钟有界退避——重放安全本来就由核心的耐久发送边界账本负责，拦住每一个只读 tick 保护不了任何额外的东西。旧版写下的无限期暂停在读回时视为「立即到期」，账号因此能自行恢复。
3. **被门禁跳过的 tick 完全无声。** `permit()` 返回 null 时直接 `return@mapNotNull null`，所以「停止调度的账号」和「没事可做的账号」外观完全一致。现在会打日志说明退避到何时。

修完前两层后暴露出第三、第四层：

4. **`rejected` 被当作「越过发送边界未闭合」。** 服务器明确拒绝意味着什么都没生效，没有任何需要人工裁决的东西。把它算进阻塞集合，导致将领维护 pending 永远无法完成；而 pending 车道对所有 configured work 有绝对优先权，于是副本和刷黄再次一个都排不上（`via=general state=blocked` 每 tick 循环）。只有 `sending`/`uncertain`/裸 `accepted` 才是真正未闭合。
5. **失败路径回滚了发送边界账本。** `run_pending` 的异常处理用**工作流运行前**的快照重建记录，工作流在失败途中持久化的每一个步骤状态都被抹掉。这不只是收敛问题——它意味着一个已经 `accepted`（道具已扣）的步骤可能被抹成未发送，下一轮重复扣一次。改为先重读当前记录再合并错误字段。

`V0.0.47` 真机验证：账号自行恢复，19:05 补完 15:36 遗留的副本战斗，19:14 完成 3 小时来第一次刷黄出征（`battleId=31920227`）与副本开箱；`generalMaintenancePendingJson` 已清空，将领维护回到 10 分钟节奏，三个功能重新正常交替。

## 调度可观测性与活性看门狗（`V0.0.48`）

今天四次停摆的定位成本分别是 70 小时、4 天、10 分钟、3 小时 20 分钟，而**每一次都是人先发现记录不再出现**，再回头查证。共同原因不是缺少检查，而是：**每个检查都写在它所检查的那个机制内部**，机制一旦失效，检查随之失效。

因此这一步只做两件与任何机制无关的事。

### 1. 调度器必须说出它拒绝了什么

`_run_automation_recovery_tick` 里，「上报到期集合」和「合并唤醒时间」原本写在同一个 `if` 里。于是**由 pending 工作流拥有的 tick 完全不发布到期集合**——而那恰恰是饥饿功能唯一不可见的 tick。副本 70 小时零执行就发生在这个盲区里。

现在上报无条件执行，只有唤醒合并仍受条件约束。真机对照：`via=dungeon` 的 tick 从前没有 `cand=`，现在稳定带 `cand=brush|dungeon|general`。

同时新增 `stalledFeatures`：到期时间已过 `STALL_REPORT_MILLIS`（15 分钟）的候选，按逾期时长排序，日志里渲染为 `STALLED=副本(逾期23分)`。到期集合本就每 tick 计算，这项报告零额外成本。

### 2. 与机制无关的活性看门狗

`ResidentLivenessWatchdog` 不认识 wake gate、不认识 pending 账本、不认识任何调度组件。它只检验一条不引用任何机制的不变量：**配置了任务的账号应当被定期询问**。静默超过 15 分钟即上报，之后每 5 分钟心跳一次，直到恢复。

这正是 3 小时那次事故所缺的东西：调度器醒了 33 次，在一个布尔值上返回，什么都没写，于是"已停摆"和"空闲"在日志里完全同形。看门狗的价值不在于修复任何已知 bug，而在于**下一个我还没预料到形状的 bug**——不管是哪个组件失效，静默本身都会发声。

两个看门狗分处两层，这是必需的：核心侧的 `stalledFeatures` 抓「功能被饿死」（如副本 70 小时），宿主侧的静默检测抓「核心根本没被调用」（如账号级暂停 3 小时）——后者核心永远无法自行发现，因为它没有运行。

## 用观察结清不确定的前置账本（`V0.0.51`）

装包重启打断了副本的 `troop-heal`，账本停在 `preDispatchMutationState=sending`。此前的处理是把它当成"必须人工判断"，于是副本被无限期隔离，而刷黄和将领维护照常运行——又一次单功能永久停摆。

**第一性原理**：`sending` 表示**结果未知**，不表示**无法查明**。前置的每一步（治疗、加体、配兵）在发包前都会重新读取世界状态并据此决定是否要发：没有伤兵就不治疗，体力已达标就不用丹，配兵已匹配就不改。所以只要将领全部回闲、且预出征/正式出征/开箱**一个都没发过**，下一轮重跑不是"重放"，而是一次基于新观察的全新决策——它会自己得出"不需要做"的结论。

真正不可挽回的是正式发送：预出征、出征、开箱、结算、撤防。这些无论怎么读都无法撤销，必须停下等人。

因此把守卫分成两层：

- `FORMAL_SEND_STATE_KEYS`（模块常量）——只有这些的 `sending`/`uncertain` 会隔离功能。
- `preDispatchMutationState` **从探针中移除**。它原本挡在解析器前面，导致唯一有能力结清它的工作流永远进不去；**挡在解析器之前的守卫只能阻塞，不能解决**。

`ambiguous_preflight_reconciliation`（`automation.py`，纯函数）统一了这个判定：`isolate`（有正式发送）／`wait`（将领未回闲或不在新鲜状态里）／`reconcile`（归档，下轮重新推导）。刷黄早就有等价逻辑，副本没有——现在两者共用同一条规则，后续的出征类功能不会再各自漏一次。

真机验证（账号 176）：

```
20:58:20  副本旧账本自动归档   preDispatchMutationState=sending
                              feature=troop-heal
                              prepare/dispatch/chest 全部 not-sent
20:58:35  [活血丹] 统弓2 使用1枚活血丹，体力25→75，来源将领维护
20:59:08  单人副本启动成功
21:00:46  副本完成，右箱已开启（battleId=92260）
```

`isolated=` 与 `STALLED=` 均已消失；归档前 `STALLED=dungeon(逾期18分)` 在日志里持续可见，正是第 1 步建立的可观测性首次在真实故障上生效。

## 同区多账号的地图复用（`V0.0.57`）

两个测试账号同时在 `qzone_352` 运行时，其中一个近一小时只出征 1 次刷黄。查下来是四个独立缺陷叠加，全部与"地图知识如何被复用"有关。

### 1. 缓存是只写的

快照只存扁平的 `compositionCode`，而 `match_composition` 需要解析后的兵种字段、**看不到就一律拒绝**。真机数据：216 个缓存目标，通过筛选 **0** 个；放宽兵种筛选后 216 个全过。缓存写了一整晚，一个也没被用上。

修复：读回时从 4 位 `compositionCode` 还原 `{foot,bow,cavalry,chariot,source}`。位数不对或含非数字则**不还原**——瞎猜等于让编队去打一个没人测过防守的目标，宁可让它落选。

### 2. 缓存里绝大多数是尸体

215 个缓存目标里**只有 1 个仍有效**，其余 214 个早已被标记 invalidated，而读路径不过滤。结果是修好缺陷 1 之后，几乎每次派发都返回「目标不存在，不能到达」。

修复：宿主只序列化 `active` 记录，Python 侧再防御性跳过带 `invalidatedAtMillis` 的行。缺陷 1 和 2 必须一起修——只修任一个都会让情况更糟。

### 3. 进入云共享模式会**丢掉**本地缓存

原代码是 `if cloud_shared: 用云端 else: 用本地缓存`——二选一。于是一旦同区出现第二个账号，账号就不再读自己的缓存，而云端返回 0 个候选，只能退回每 tick 扫 5 个坐标。

修复：两个来源是**同一类证据**，求并集而不是二选一。这不影响冲突避免——共享模式下每个候选在派发前仍必须赢得云端 reservation，所以候选集变大不可能让两个账号撞车。

### 4. 本地缓存按账号分区，而地图是服务器的事实

同一服务器、同一扫描区域、同一目标类型下，两个账号看到的是同一张图。按账号分区让它们各自从零重新发现（一个 215 条、一个 5 条），也正是"同进程内两个账号共享地图却需要一次云端往返"的原因。

修复：写入仍按账号（"账号 176 在 22:09 看到过它"是真实陈述，provenance 保留），**读取**跨账号合并同 `(server, kind, fingerprint)` 的观测，取每个目标最新的记录——任一账号发现它消失，对所有账号都算消失。

`V0.0.57` 真机结果：「目标不存在」从 8 分钟 6 次降到 4.5 分钟 1 次；日志出现 `匹配目标已由同区服其他账号领取，稍后重试`，说明 reservation 正在按设计避免冲突。剩下的限制是真实的：该区域同时存活的 8 级山贼只有个位数，两个账号共享这一小群，扫描占多数 tick 属于内容供给问题，不是缺陷。

### 5. presence 抖动：租约由业务事件续期（`V0.0.58`）

真机每 1–2 分钟在"1 个在线"和"2 个在线"之间跳一次，每次翻转都让一轮刷黄延后。

根因不是 TTL 的取值，也不在 Worker：**presence 是一个带 TTL 的租约，而续期只作为刷黄/打矿轮次的副作用发生**。将领出征在外时这两个功能几分钟才跑一次，远超租约有效期，于是租约在两次续期之间过期——两个都在运行的账号互相看到对方时隐时现。

修复两条，对应两个不变量：

1. **租约必须由时钟续期，不能由节奏无关的业务活动顺带续期。** 心跳移到常驻 tick（每几秒一次），按 `CLOUD_PRESENCE_RENEW_MILLIS = 20s` 节流；实测过期窗口约 60–90 秒，留 3–4 倍余量。只有启用了刷黄或打矿的账号才付这个成本，且失败被吞掉——模式保持原值，绝不影响 tick。
2. **presence 说的是"最近见过"，不是"此刻为真"。** 单次读到"1 个在线"不能证明对端离开，它可能只是正在战斗、续期晚了一点。因此对上次正向观测保留 `CLOUD_PRESENCE_GRACE_MILLIS = 90s` 的粘滞窗口。真的离开了仍会被纠正：Worker 对地图查询回 409，模式立刻下降。

真机验证：`V0.0.58` 后 5 分钟内模式翻转 **0 次**（此前每 1–2 分钟一次），`在线人数发生变化，本轮已安全延后` **0 次**，同时 `匹配目标已由同区服其他账号领取` 出现 8 次——说明共享模式稳定生效，reservation 正在正常仲裁。

### 6. 两个后续缺陷（`V0.0.59` / `V0.0.60`）

**并集在共享模式下把整轮吃掉（我引入的回退，`V0.0.59` 修复）**

并集把只存在于本账号缓存里的目标也当作共享候选。这类目标**无法被 reservation 仲裁**——Worker 从来不知道它们存在——而 reservation 失败的分支会消耗整轮并退避。结果两个账号从 23:03（新代码生效）到 23:40 **一次刷黄都没有出征**。

正确的边界：**只有共享池能提供候选，因为只有共享池能仲裁它们。** 一个别人看不见的目标不是共享池目标；共享模式下没有共享候选时，落回普通扫描（与改动前一致）。回归测试断言的正是这一点：共享模式 + 云端 0 个 + 缓存非空 → 必须发生扫描，且不得调用 reserve。

顺带把那条误导性文案改掉：`匹配目标已由同区服其他账号领取` 读起来像正常的同伴竞争，而真实原因是所有候选都不可能被领取——正是它让 35 分钟零出征看起来毫无异常。现在会报出候选个数。

**`pending` 被当成可能已发送（`V0.0.60` 修复）**

真机账本：`preDispatchMutationState = pending`、`preDispatchMutationCount = 0`、三个发送状态全部 `not-sent`——**可证明什么都没发生**，却带着 `requiresAttention=True` 长期占住 pending 车道，导致刷黄饿了 20 分钟、将领维护饿了 16 分钟。

`pending` 是**初始**状态，意思是这个 mutation 从未开始。把它和 `sending`/`uncertain` 并列，是"已知结果被当成未知"的又一次重演。判据改为看**是否有发送证据**（`preDispatchMutationCount` 与三个发送状态），而不是看它恰好停在哪个非发送状态上；`failed` 分支的原条件保持不变，只做严格放宽。

这次是 `STALLED=brush(逾期20分),general(逾期16分)` 直接把它指出来的——第 1 步建立的可观测性第二次在真实故障上生效。

## 通宵 7 小时零出征：账本无上限增长（`V0.0.62`–`V0.0.64`）

08-29 00:51 两个账号同时停止产出，07:42 同时恢复，中间 **414 分钟**。两个账号相差不到 2 分钟同停同起，说明是进程级事件而不是业务逻辑。

### 证据

`dumpsys activity exit-info` 给出了直接死因：

```
03:45:50  com.example.dwpmclone  reason=13 (OTHER KILLS BY SYSTEM)
          description=ScreenOffCPUCheckKill   pss=513MB rss=624MB
09:55:02  com.example.dwpmclone  reason=13
          description=AutoPowerKill           pss=309MB rss=436MB
```

**`ScreenOffCPUCheckKill`**——厂商因"息屏期间持续占用 CPU"结束进程。而当时进程占用 **513MB**。

顺着内存查到根因：

```
operations-v2.json          52.7 MB
operation 条数              11,744（SUCCEEDED 11,697）
其中 automation:recovery-tick  11,610
单条最大                     172 KB
```

**耐久 operation 账本没有任何保留策略。** 常驻调度每几秒创建一条 operation，全部永久保留。而 `_persist_locked()` 每次都把**整个账本**重新序列化并落盘，且被约 20 处调用——包括每一次 `publish_progress`。于是每个 tick 要编码并写入数十 MB JSON，Native Heap 涨到 442 MB。

进程不是"被误杀"，它确实变成了一个失控进程。

### 三项修复

1. **保留上限**：只裁剪**确定已关闭**的 operation（`SUCCEEDED`/`CANCELLED`），保留最近 300 条。`UNCERTAIN` 永不裁剪——那正是这个账本存在的理由；`FAILED` 也保留，因为那是人排查时要看的东西。
2. **结果压缩**：`result` 占账本 96%，单条 tick 里 `scanResults` 一项就 109 KB——那是"结果怎么算出来的"的草稿，结果产生后没有任何消费方再读它。按**大小**而不是按字段名裁剪（保留名单会在有人加字段那天悄悄丢数据，排除名单会在有人加大字段那天悄悄漏掉），阈值 4 KB：实测消费方读取的最大字段是 `successRecord` 550 字节，被裁掉的是 5 KB–109 KB。裁掉什么会被记录，不静默丢弃。
3. **进度不落盘**：`publish_progress` 是系统里频率最高的写入，而进度只是 UI 提示，不是任何恢复路径读取的事实。

第 2 项第一次实现时在"关闭当刻"就压缩，桌面副本/无损 tick 立刻报 `未返回业务结果`——**结果要等消费方读过之后才是草稿**。改为保留最近 50 条完整，更旧的才压缩。这个错误是测试抓出来的。

### 实测

| | 修复前 | `V0.0.64` |
|---|---|---|
| 账本文件 | 52.7 MB | **1.55 MB**（−97%） |
| Native Heap | 442 MB | **43 MB**（−90%） |
| TOTAL PSS | 757 MB | **157 MB**（−79%） |

### 已排除：AOSP Doze 不是原因

`dumpsys deviceidle` 强制进入 deep IDLE 后观察 7 分钟：常驻 tick **77 次**，两个账号照常开箱、出征、维护。电池白名单（`user,com.example.dwpmclone`）确实生效。

结合"进程 00:51 停止产出但直到 03:45 才被杀"，那 3 小时是**被厂商冻结**而非 Doze——而冻结与击杀针对的都是高占用进程，所以上面的削减同时是这两者的缓解手段。

厂商行为无法在本地模拟，只能通宵实测验证。

### 仍未处理

- 打矿路径没有本地缓存读取，与刷黄修复前同形；这两个账号未启用打矿，缺少真机数据，未改。
- 桌面端 `DesktopMapSnapshotPort` 只注入了 `save` 与 `invalidate`，**没有 `load` 回调**，所以桌面端从未复用过自己的地图扫描——与 Android 修复前同类问题，且更基础。
- 云端 `/v1/maps/targets/query` 为何恒返回 0 个候选仍未查明。并集修复后同设备同区已不依赖它（本地跨账号合并即可），但跨设备共享仍无实际收益。

## 24 小时出征偏少：五个原因（09-08 真机复盘，`V0.0.65` 在装）

用户问题："记录页 24 小时只有很少几次出征——是没出征、没记录、被杀后台，还是 App 没执行？"结论：记录没有漏（每条成功记录都对应真实 `battleId`：176 刷黄 19、202 刷黄 11 + 副本 40）；进程曾被 `ScreenOffCPUCheckKill` 杀过 4 次但都在 2 分钟内拉起；真正的损失来自下面五项，按损失大小排序。

### 1. 手机 Wi-Fi 每晚定时关闭（约 35% 时间离线，非 App 问题）

三个夜晚两个账号都在 23:07–00:21 同时停产、07:24–07:36 同时恢复。`dumpsys wifi` 给出直接原因：`CMD_WIFI_TOGGLED → DisabledState` 于 **23:10:05**，`CMD_WIFI_TOGGLED → EnabledState` 于 **07:35:55**，切换时 `screen=off`（自动定时，不是人手）；`mobile_data=0`，所以整夜无网。App 全程存活（单一 `process_generation`），按 10–30 分钟重连退避重试，07:36:06 两账号在同一毫秒重登——比 Wi-Fi 恢复晚 8 秒。夜间既无 USER 事件也无 FAILED operation，因为账号不在线时常驻 tick 根本不会创建 operation。

这一项只能在手机上关掉“定时开关 WLAN/睡眠省电”。

### 2. 缺活血丹被当成需人工处理，将领维护每 1.9 秒空转

202 的智步6 体力 22–29，低于加体阈值 30 但**高于出征下限 20**（同一天副本用它打了 40 次）。`plan_general_energy_use` 抛 `宝库没有活血丹` → 整轮维护中止 → pending 账本留存 → `safe_read_only_recovery_probe` 判定"可复核"绕过了 `requiresAttention` 隔离 → 每 tick 重新进入，连续 561 秒 120 次，副本/刷黄被饿。

按用户定义的规则重做语义：

- 体力 **> 20** 且无活血丹：**不是错误**，返回 `reason=energy-item-unavailable` 继续；
- 体力 **≤ 20** 且无活血丹：记录该将领 30 分钟冷却（`generalEnergyCooldownJson`，契约 `scheduler.energyShortageFormationPauseMillis`），**只暂停包含该将领的编队**——刷黄换另一条规则，副本/无损延后到冷却到期；维护轮次跳过该将领继续完成，pending 不再挂起。所有消费方通过 `error.details["retryAtMillis"]` 得到统一的重试时刻。

### 3. 共享云端 Worker 500，刷黄全部"安全延后"

`dwpm-data.292828.xyz` 的 `/v1/presence/heartbeat`、`/v1/servers/catalog`、`/v1/servers/directory/query` 全部 `INTERNAL_ERROR`，而不碰 `server_directory` 表的 `/v1/maps/targets/query` 正常返回参数校验——与生产 D1 未应用 `0003_server_directory.sql` 一致。曾进入 `CLOUD_SHARED` 的账号按设计退化为 `CLOUD_UNAVAILABLE` 并延后刷黄，所以从 16:16 起两账号刷黄为零。本机未登录 Cloudflare，未能核实/修复；进程重启后账号回到 `LOCAL_ONLY` 可以刷黄，但失去了同区服的目标协调（19:29 两账号出征了同一个山贼）。

### 4. 四条"越过发送边界无回执"账本卡死 1–4 天

176：副本开箱 `sending`（09-06 11:10 起，副本 24 小时 0 次）、healByFief/539 `uncertain`（09-04 13:21 起，`STALLED=general(逾期8608分)`）、背包连接超时 `uncertain`（09-07 18:00 起）；202：背包连接超时 `uncertain`（09-04 11:03 起）。游戏只读状态早已空闲。经用户授权，停进程后把四个 pending 字段置空、原值归档到同名 `*OperatorClearedJson`，沙盒原文件备份在 Mac。重启后 176 的副本在 45 秒内完成了卡住的那一步开箱并继续出征。

### 5. `LOCAL_ONLY` 下被拒目标不从本地缓存剔除

候选始终取缓存中最近的一个；`目标不存在，不能到达` 被拒后只更新云端状态，本地快照不写 `invalidatedAtMillis`（端口两侧都有 `invalidate`，但 facade 从未调用）——于是同一具尸体每 10 秒重试一次直到 TTL 过期。现在 `BRUSH_DISPATCH_REJECTED` 且消息含"目标不存在/不能到达"时调用 `map_snapshots.invalidate`；配兵类拒绝不失效目标。真机上 176 最后一次被拒后的下一 tick 就重新扫描并出征。

### 云端 500 的真正根因：账号级 D1 免费读额度耗尽（09-08 20:10 定位）

Worker 代码与线上完全一致（拉取线上脚本比对，`server_directory` 相关标记数量一致），因此不需要重新部署，也不是迁移缺失。`wrangler d1 info` 给出真实原因：

| 数据库 | rows_read_24h |
|---|---|
| newsnow-db | **4,778,577** |
| dwpm-cloud-shared-data | 645,121 |

账号免费额度 500 万行/天，`newsnow-db` 一条查询就吃掉 83%：

```
SELECT source_id, MAX(fetched_at) FROM news_item WHERE source_id IN (?×25) GROUP BY source_id
avgRowsRead=159,286  numberOfTimesRun=26  queryEfficiency=0.00014
```

`news_item` 只有 `(source_id, pub_date DESC, fetched_at DESC)` 索引，`pub_date` 排在 `fetched_at` 前面，所以每个 source 都要全扫。已在 `newsnow/server/database/news.ts` 的 `doInit` 增加 `idx_news_item_source_fetched(source_id, fetched_at DESC)`，并直接对生产 D1 执行了该 DDL（DDL 不受读额度限制）。执行计划已确认改为：

```
SEARCH news_item USING COVERING INDEX idx_news_item_source_fetched (source_id=?)
```

单次读取从约 16 万行降到个位数。当天额度不会立即恢复（UTC 午夜 / 北京时间 08:00 重置），因此 dwpm 心跳在当晚仍为 500，账号按设计退回 `LOCAL_ONLY` 继续刷黄。

### 缺活血丹暂停的提前解除

30 分钟窗口只是对自然恢复速度的估计。用户手动补充活血丹后这个估计就是错的，而将领维护每轮本来就持有一份全部将领的最新读数——`_lift_recovered_energy_cooldowns` 因此在那里免费纠正：体力回到出征下限以上即删除该将领的冷却，并把"正好睡到该冷却到期"的功能唤醒到当前时刻，否则解除也要等到原定时刻才生效。

### 丢弃装备品质改为多选

原先是一个"上限"下拉框（选"良好"= 良好及以下）。现在是勾选集合，可以只丢普通+良好、也可以跳着选（普通+优秀）。兼容规则：

- 记录里存在 `discardEquipmentQualities` → 集合就是权威，**空集合表示什么都不丢**；
- 只有旧的 `maxEquipmentQuality` → 展开成"该品质及以下"，与它一直以来的含义完全一致；
- `maxEquipmentQuality` 继续写为所选集合中的最高品质，旧读者看到的上限不变。

判定条件不变且已在说明文字中写明：只处理宝库中（因此天然未穿戴）未强化、未炼魂、非名将、低于设定等级且 80 级以下的装备。真机验证：账号 202 由 UI 写入显式集合 `["普通","良好"]`，未触碰的账号 176 仍只有旧上限，两者经共享核心投影后都得到 `codes=[0,1]`。

### 回归与安装

新增 `tests/test_shared_energy_shortage_pause.py` 16 项、`test_shared_inventory_automation.py` 增补品质集合用例、Kotlin `InventoryUiConfigMappingTest` 增至 3 项；Python 全量 1069 项、前端 JS 2 项、Kotlin 3 项全部通过。多次 `adb install -r` 后用启动器 Activity 的 `onResume → refresh()` 恢复托管（直接 `am start-foreground-service` 被"未导出"拒绝，`USER_UNLOCKED` 广播受保护）。

## 真机门禁验证与发现的问题

首次负向验证时发现：共享 operation 把“自身正在运行”误当成 Android 前台 Service 仍持有执行权。账号元数据仍为启用状态，因此测试意外进入旧只读网络适配器并发送了一次 `0x1600` 军情查询；请求成功返回，但缺少 `0x8600`，operation 最终为 `FAILED`。

这次访问：

- 只有一次只读 `0x1600` 查询。
- 没有修改型 opcode、出征、登录或任务启动。
- 没有活动 operation 残留。

该行为不符合本阶段“未经授权不访问游戏服务器”的验证边界，不能忽略。现已增加两层实时门禁：

1. Python operation 调用 Android 适配器前，必须读取 `AssistantForegroundService.isExecutionOwnerActive()`。
2. Kotlin 临发包前再次检查 Service 所有权、账号启用状态和 Session 来源。

修复后的同一真机测试结果：

- 最新 APK 上 operation 受理：8.40 ms。
- 最终状态：`FAILED`，明确原因为“Android 前台执行所有者未激活”。
- 测试前后游戏请求记录都为 30 条，SHA-256 均为 `bd66eb4252488c26eae3c086850cece8f06b17155a5a166344e37220e7da16ef`。
- 活动 operation：0。
- `AssistantForegroundService` 测试前后均未启动。

未经用户明确授权，不继续执行 Service 启动后的真实军情成功路径。

## 当前回归证据

- 电脑端日志根因已修复：游戏 `dm` 按有符号 64 位保存，合法负数现使用 `dm != 0` 判断，只有 0 才表示缺失；Session 暂不可用退避延长为 5 分钟。设置保存响应已把日常排队元数据和真实结果分开，静态资源断连不再打印无意义堆栈。在线旧进程尚未重启，需在账号安全停止后验证运行态。
- 电脑端 Python：829 项测试通过；共享业务、回执和恢复覆盖未删除，并新增完整道具表、固定对齐、未知道具和真实历史 0x8104 回归。
- `app.js` 与 `assistant-api.js`：Node.js 语法检查通过。
- 共用 operation 前端行为测试：通过，覆盖 Android 事件驱动 `202 → RUNNING → SUCCEEDED`、过期事件拒绝、页面恢复、临时读失败、取消和已发包取消拒绝，以及桌面端状态轮询和嵌套 workflow 结果展开。
- 动作安全不变量与 V1 静态覆盖门禁通过；迁移状态审计仍正确为未完成，但 Kotlin 后台生产所有者已为空集合。
- Android JVM：482 项测试全部通过，0 失败、0 错误、0 跳过；Debug/Release Kotlin 编译通过。自动背包与军情警报均进入共享任务过滤，旧 Kotlin 任务失败关闭。
- 自动内政迁移后曾重新构建 `V0.0.17`（`versionCode=17`）Debug APK：27,349,583 bytes，SHA-256 `c9575183bf892f051a186ad5f66d27cd1495457cb26ae5aa3432104c80aa82b7`。该阶段产物当时未安装；上一轮 Release 未签名 APK 为 25,966,185 bytes，SHA-256 `1fb33aa075c8b82fb6f3032431070b0d5dc33d3663eaf14a8fd4afb310e8b247`，均只作历史记录。
- 最后兼容补丁后已重新完成 `V0.0.18`（`versionCode=18`）Debug APK 干净构建：26,637,093 bytes，SHA-256 `d07bd04b1eeff547b3023fd922bef3b8a419789a1f16eadb2a4af6397286320b`。已核验 Manifest、内嵌 `alarm.py/facade.py/automation.py/settings.py` 与构建源哈希、旧 `currentFingerprints` 继承、`incomingKeywords/vibrateOnAlarm` 保留、警报调度契约、`alarmPendingEventsJson`、Android 通知桥和前端 `V0.0.18` 缓存键；V1 静态构建审计通过。该 APK 已通过 `adb install -r` 覆盖安装到设备 `27a83c9c`，设备报告 `V0.0.18 / versionCode 18`，设备端 `base.apk` SHA-256 与构建产物一致；安装后未主动启动 APP，进程未运行。
- 宝物解析修复版 `V0.0.19`（`versionCode=19`）Debug APK 已干净构建：26,637,097 bytes，SHA-256 `d896a863d58aae33d5e4db5c5278b6bf14db1297a1713d3241945f2f3e964bf5`。APK 内已核验完整道具表、严格固定表解析、隐藏 operation 托盘和 `V0.0.19` 缓存键；V1 静态审计与 482 项 Android 测试通过。该 APK 已覆盖安装到设备 `27a83c9c`，设备版本和 `base.apk` 哈希与本地一致；安装后进程与 `AssistantForegroundService` 均未运行。
- 升级前设备上的 `V0.0.17` Debug APK 为 26,620,616 bytes，设备端 SHA-256 `4744e187d2750d8a3e75e64fb340cdde58d15092a425a2535a62b6690ce50ad2`；其冷启动 Activity 603 ms、页面版本 `V0.0.17` 和停止态请求健康账本只保留为升级前基线，不代表当前 `V0.0.19` 的真机功能验收。
- 停止账号任务页、本地原样保存、页面重建和安全取消均已完成真实 WebView 复验；修复后的观察窗口内 `AssistantForegroundService` 未启动，请求健康账本 SHA-256 始终为 `aaebaf690f33be59a808762571ddb63fd505229b54f0624052da5266447bf515`。本节上方已单独保留修复前误唤醒 Service 和一次治疗 mutation 的审计，不能用修复后结果覆盖该事件。
- 真实 WebView 冷启动约 663 ms，页面完整加载且 `DWPMNativeApi` 可用。热态 20 次健康接口 P95 4.4 ms、账号读取 P95 39.5 ms；合法账号设置读取 20 次 P50 52.1 ms、P95 53.6 ms；模拟 operation 19.3 ms 返回 202。
- 90 秒无法访问网络的模拟 operation 期间，83 次健康读取 P50 7.8 ms、P95 89.1 ms，13 次设置读取 P50 55.6 ms；operation 正常完成。完成落盘附近出现一次健康 655.6 ms 与设置 112.8 ms 尖峰。另一次 200+200 次高频压力样本中健康 P99 153.3 ms，但设置 P95 186.1 ms、P99 1070.5 ms。正常用户交互不会再触发固定 30 秒假失败，但严格尾延迟门槛仍未全部满足。
- 共享查询重复点击、完成后再次刷新、平台所有者门禁、共享 Session 门禁：全部通过。
- 账号通道连续两次返回 `LOCAL_ACCOUNT_BUSY` 后的退避恢复：operation 最终 `SUCCEEDED`，同步 Kotlin 回调路径不再阻塞等锁。
- 配兵 mutation 覆盖成功、服务器明确拒绝和发送后 socket 异常；并证明进入字节 HTTP 传输前 `requestSent` 已持久化、账号锁只取得/释放各一次。
- 配兵/补兵/治疗和单次开箱的 Python 原始命令工作流均覆盖发包前失败、明确拒绝、缺失回执与发送后断联。
- 电脑端停止账号保存配兵的 HTTP 契约测试通过，并证明没有调用网络配兵任务。
- 电脑端单将配兵、补兵、治疗和单次开箱手动路由已提交同一份共享 Python 原始命令 workflow；离线开箱测试覆盖 `0x1104 → 0x3144 → 0x1104`、钥匙前置与成功回执解析。
- 电脑端户部查询/种植、内政查询/动作、全部手动日常及找黄/找矿也已提交 Android 相同的共享 workflow；批量配兵和一键卸兵的本地后续任务同样改为共享 operation。`DesktopMapSnapshotPort` 已将共享搜索观测投影到现有桌面 SQLite 地图。电脑端与 Android 的路由所有权当前均为 56/56 `shared-python`。
- 新增共享登录回归覆盖完整登录协议链、持久化 add/start、后台直接重登、密码/DM 不进入 operation/公开账本，以及 Python 原始报文经 `RawHttpPort` 发送。
- 已迁移游戏命令的测试宿主现会解码 Python 生成的真实请求包、返回原始字节响应，再由 Python `parse_response` 解析；不再依赖 Kotlin 式 `gameCommandFact` 测试替身。
- 状态/心跳/军情新增原始字节回归：状态全量刷新严格发送 `0x1016 → 0x1104 → 0x1600`，心跳发送 `0x3110`；测试宿主完全不提供 `executeNetworkOperation`，仍能完成解析、统一账本写回和最终响应。
- 刷黄/打矿恢复新增 6 项 workflow/tick/进程重开测试，覆盖正常战后维护、exact battleId 撤防、回闲清账、治疗回执不明确、撤防回执缺失和进程重开禁止重放。
- 掠夺共享 workflow 与桌面 Raw HTTP parity 测试通过：缺少 `0x8520` 时只发送 `0x1520`；收到确认后才发送 `0x1522`，并解析正 battleId。测试已不再 mock 被迁走的桌面业务函数。
- 无损共享测试覆盖冷却只读 tick、完整出征 payload、前置 mutation 账本、缺少预出征回执不发正式动作、同包结算和 pending 清账；桌面常驻入口通过原始字节端到端 fixture。
- 副本共享测试覆盖抓包目录/状态/poll shape、精确两阶段 payload、缺少预出征回执门禁、战斗轮询、回闲开箱、clear 目录确认和前置 mutation 中断；桌面 Raw HTTP 端到端与 Android 统一 resident adapter 门禁证明双端只调用同一 Python 状态机且 `UNCERTAIN` 不可重试。
- 独立将领维护测试覆盖多封地/多将领稳定顺序、每步只执行一次、已完成步骤跨进程续跑、未发包失败可重试、明确拒绝停止后续 mutation，以及 `sending/uncertain/accepted` 只读核对且禁止重放；俘虏营救仍固定失败关闭。
- 自动内政测试覆盖大厅/空地/最低级建筑与科技轮换、每 tick 单 mutation、1 秒连续填队列、动态建筑完成 deadline、粮食转铜一次性账本、进程重建、资源不足不重放、明确拒绝延迟、候选变化、`sending/uncertain/accepted` 恢复、第三资源失败关闭和双端配置一致。
- 自动背包测试覆盖白名单、钥匙、50 个上限、开箱优先、指定物品丢弃、装备保护与元数据缺失失败关闭、发包前 pending、单 tick 单 mutation、真实/部分消耗核对、`preparing/sending/uncertain/accepted/rejected` 恢复、超时要求人工处理和双端生产门禁。
- 刷黄/打矿故障回放覆盖配置与行游标的进程重建、只读断网有限重试、Session 失效发包前失败、停止单任务不影响另一任务、停止后不启动新动作、已接受动作继续安全恢复，以及 Android `UNCERTAIN`/超时不产生自动重放 deadline。

## 尚未完成

- 军情警报的共享代码与生产所有权已完成，但 Service 托管下的真实来袭/普通军情通知尚未获得用户授权做真机验收。
- 旧刷黄/打矿协议实现已无生产调用者并有静态门禁，但尚未物理删除；桌面新手/手动 starter 副本入口也留待下一版本逐项收口。
- 共享常驻的进程重建、断网、Session 失效、单任务停止/账号停止和 operation 不明确状态离线回放已完成；锁屏/Doze 已在 `V0.0.34` 完成 19 分钟深度 Doze 真机回放，设备重启和网络切换仍待真机回放。
- 军情真实成功路径尚未获得用户授权进行真机验证。
- 真实配兵成功路径尚未获得用户授权进行真机验证。
- operation 事件推送、页面重建恢复、用户取消入口和 `CANCELLED` 已完成最终 APK 的真实 WebView 视觉验收；真实 `UNCERTAIN` 视觉仍待用户授权的受控故障路径。
- 正常频率 WebView 本地读取和 90 秒隔离 P95 已基本达标；operation 完成落盘瞬间与高频压力下仍存在尾延迟。其根因涉及耐久 operation 账本 `fsync` 与单 CPython 解释器竞争，下一版本专项优化；本版本不以取消落盘或放宽 mutation 账本换取表面延迟。
- 十类常驻与七类日常已经进入同一共享队列；进程级账号锁只作为同账号网络互斥边界，不再保护任何 Kotlin 业务所有者。

因此，阶段 7 仍为执行中，不能宣称 Android 所有“手机核心响应失败”路径已经消失。
