# 共享核心实现边界清单

> 状态：阶段 1 初始清单
>
> 机器可读路由源：`shared_core/api_route_ownership.json`

## 结论

- 当前共享的只有前端和行为/协议 fixtures，游戏业务仍由 Python 与 Kotlin 分别实现。
- 目标范围是电脑端“单账号容器”的完整业务能力，不包括多账号总控、起号、代理、诊断和服务关闭。
- 当前共识别 55 个共享方法/路径，其中 26 个必须是纯本地即时响应，29 个必须是按账号异步执行的网络操作。
- 电脑宿主保留 32 个专属方法/路径；历史 Mobile API 与 `/api/login` 别名只保留兼容，不进入共享核心主接口。
- 阶段 3 另有 4 个 `android-debug-poc` 方法/路径，只验证离线异步 operation 模型，不属于正式业务接口，Release 版不开放。
- Android 当前明确缺少 4 个电脑单容器接口：六部查询、六部种植、内政查询、内政动作。
- Android 当前实现了桌面总控 `/api/dashboard`，它不属于手机目标范围，迁移后应从 Android 正式业务入口移除。

## 响应边界

### 纯本地即时响应

以下类型不能访问游戏服务器，也不能排在网络队列后面：

- 健康、账号列表、区服缓存、设置读取。
- 日志、成功记录、提示删除。
- 自动化状态、本地地图和缓存快照。
- 停止/删除本地账号。
- 保存通用设置、配兵规则、掠夺规则、打矿、六部、无损、副本和未来军情设置。
- 启停已经保存的后台任务；真正的网络动作由任务引擎异步执行。

### 按账号异步网络操作

以下类型立即创建 `operationId`，实际结果等待游戏服务器：

- 添加/启动账号及真实登录。
- 真实状态、心跳、军情刷新。
- 找黄、刷黄、找矿、打矿、查询掠夺封地。
- 配兵、补兵、治疗、卸兵和开箱。
- 日常领取/捐献/拜访。
- 六部查询/种植和内政查询/动作。

## 功能追踪矩阵

| 功能域 | 电脑端事实入口 | Android 重复实现 | 共享核心目标模块 | 主要现有测试 |
|---|---|---|---|---|
| 账号登录与 Session | `downjoy_sdk_login`、`login_game`、`start_account`、重连线程 | `LocalAccountLoginService`、`AccountSessionRecovery` | `dwpm_core.account` | `test_account_persistence.py`、`AccountLoginStateTest`、账号协议测试 |
| 网络与包协议 | `make_packet`、`parse_response`、`post_game` | `RealGameProtocolClient`、`SessionAwareGameProtocolClient` | `dwpm_core.protocol.transport` | `test_game_request_logging.py`、`RealGameProtocolClientTest` |
| 角色/资源/将领/军队 | `parse8003`、0x8004 系列解析与刷新函数 | `State8004*Parser`、协议客户端查询方法 | `dwpm_core.protocol.state` | `test_general_parser.py`、`State8004*Test` |
| 配兵与补兵 | 配兵 payload/回执、`execute_assign_troops`、`execute_refill_troops` | Formation shapes、调度任务和本机操作服务 | `dwpm_core.features.formation` | `test_shared_behavior_contract.py`、Formation/Task tests |
| 刷黄 | 0x1540/0x8540、`execute_brush`、`auto_brush_worker` | `ShuaHuangTask`、目标解析/筛选、出征客户端 | `dwpm_core.features.brush` | `test_brush.py`、Brush parity/dispatch tests |
| 打矿 | 0x1542/0x8542、`execute_mine`、`auto_mine_worker` | `MineTask`、Mine shapes/filter/pending | `dwpm_core.features.mine` | `test_mine_sqlite.py`、Mine scheduler/protocol tests |
| 掠夺 | `query_raid_fiefs`、`execute_raid`、`raid_worker` | `AutoLootTask`、Loot shapes | `dwpm_core.features.raid` | `test_raid_parity.py`、Loot protocol tests |
| 无损 | 无损 0x19xx 流程、`dispatch_lossless`、`lossless_worker` | `LosslessTask`、Lossless shapes | `dwpm_core.features.lossless` | `test_lossless.py`、Lossless parity/task tests |
| 副本 | 副本 0x193x/0x1702、`execute_dungeon`、`dungeon_worker` | `DungeonTask`、Dungeon shapes/pending | `dwpm_core.features.dungeon` | `test_dungeon_clear.py`、Dungeon protocol/task tests |
| 背包与维护 | 开箱、丢弃、治疗、加体、粮转铜等执行函数 | Inventory/General maintenance tasks 与协议 shapes | `dwpm_core.features.maintenance` | `test_auto_energy.py`、Inventory/General task tests |
| 内政 | 建筑/科技查询与动作、`auto_domestic_worker` | `InternalAffairsTask`、InternalAffairs shapes/costs | `dwpm_core.features.domestic` | `test_domestic.py`、InternalAffairs tests |
| 日常 | `execute_daily_once_tasks` 及各领取函数 | `DailyFeatureTasks`、Daily protocol shapes | `dwpm_core.features.daily` | `test_daily_country_features.py`、Daily parity/task tests |
| 六部 | 户部查询/种植、`auto_ministry_worker` | `SixMinistriesTask`、Ministry shapes | `dwpm_core.features.ministry` | `SixMinistriesConfigTest`、协议客户端测试 |
| 军情与警报 | 0x1600/0x8600 解析、军情快照和行动汇总 | `MilitarySnapshotProtocolShapes`、Alarm task/detector | `dwpm_core.features.military` | `test_military_intel.py`、Military/Alarm tests |
| 本地地图 | SQLite 山贼/资源点、协调扫描线程 | `LocalMapRepository`、`LocalTargetCache` | `dwpm_core.state.local_map` | `test_bandit_sqlite.py`、`test_mine_sqlite.py`、LocalMap tests |
| 调度与互斥 | `AUTO_TASKS`、各 worker、优先级/锁/持久化 | `TaskScheduler`、`AssistantTasks`、RuntimeState | `dwpm_core.scheduler` | `test_assistant_operations.py`、Scheduler/Runtime tests |
| 日志与完成事实 | SQLite 日志/成功记录/每日锁 | `TaskLogRepository`、Daily stats/status repositories | `dwpm_core.state.audit` | 日志、daily completion、success policy tests |

## 平台宿主保留内容

### 电脑端

- `ThreadingHTTPServer` 与静态文件服务。
- 多容器总控和一键启动全部账号。
- 起号工具及其数据库/工作线程。
- Clash/Mihomo、代理节点与出口 IP 管理。
- 诊断栈、服务关闭、便携版启动与桌面路径。

### Android

- `Activity`、`WebView` 和 JavaScript 消息桥。
- 前台服务、通知、Alarm、WakeLock、网络变化和系统启动恢复。
- Android Keystore 凭据与 Session 秘密端口。
- Python 运行时初始化、进程级核心单例以及本地/网络/事件三通道宿主。

Android 宿主不得保留 opcode、协议解析、目标选择、成功判定和任务优先级。

## 迁移时必须拆除的耦合

1. `server.py` 的业务函数直接访问模块级 `ACCOUNTS`、`SESSIONS`、`AUTO_TASKS` 和路径常量。
2. HTTP Handler 同时承担参数解析、业务执行、线程等待和响应组装。
3. 电脑端线程 worker 内含大量 `sleep/wait`，尚未形成可恢复的统一 operation 模型。
4. Android 旧 Kotlin 网络路由仍会在 `AssistantWebBridge` 全局单工作线程中等待；阶段 3 的共享核心 POC 已改为只提交 operation，后续阶段需逐路由切换。
5. Android 设置映射、任务工厂、协议客户端和任务类共同构成第二套业务事实源。
6. 电脑端账号记录含密码字段；Android 迁移只能通过 `CredentialPort` 临时取得 Keystore 凭据。

## 阶段 1 验收结论

- 所有电脑 Handler 静态 `/api/*` 路径均已归入共享、电脑宿主或历史兼容范围。
- 所有共享前端静态 `/api/*` 路径均已归类。
- 所有 Android 本地允许列表方法/路径均已归类。
- 路由矩阵由自动测试检查唯一性、源码覆盖、已知缺口和本地/网络响应类型。
- 后续新增路由如果未更新矩阵，测试必须失败。
