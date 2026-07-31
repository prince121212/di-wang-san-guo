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
- WebView UI 投递：只负责按 request ID 返回事件，不执行业务。

共享契约当前声明 55 条路由，其中 26 条本地路由、29 条网络 operation。JVM 并发测试证明：一个阻塞的网络请求不会延迟本地读取或写入；同账号网络任务严格串行，不同账号可以同时进展。

### 2. 账号列表切换到共享 Python

`GET /api/accounts` 已将 Android 当前所有者切换为 `shared-python`：

- Android 只读取账号、重连、配置、任务、日志摘要等平台事实。
- 共享 Python 统一计算生命周期状态、Session 是否可展示、重试倒计时、最后错误和账号卡 JSON。
- 删除了 Android 原有的 `accountArray()` 和账号卡生命周期拼装。
- 添加、启动、停止和设置页返回的单账号卡也复用同一共享投影。

真机结构验证：1 条账号的 24 个必需字段完整，敏感字段路径 0；热态 10 次样本 P50 约 39 ms、P95 约 46 ms。`nextRetryAtMillis=0` 已保持旧语义为 `reconnectAt=null`，不会显示伪 deadline。

电脑端当前仍使用旧 HTTP 账号入口；待同一共享投影接入电脑端事实适配并完成离线 JSON 对比后再切电脑端所有者。

### 3. 军情作为首个网络异步样板

共享前端在军情页面使用 `GET /api/military/intel`：

- 电脑端仍可同步返回现有结果。
- Android Bridge 只提交请求，约 7–22 ms 返回 `202 + operationId`。
- 共享 Python operation 在后台按账号执行并持久化 `QUEUED / RUNNING / SUCCEEDED / FAILED / CANCELLED / UNCERTAIN`。
- Android 网络适配器只提供旧网络传输和本地仓库能力；共享 Python 在适配器前重新校验账号状态与 Session 门禁。
- 前端只轮询本地 `/api/core/operations/status`；每次 Bridge 调用都保持短响应，不再用固定 30 秒判断游戏请求失败。
- `SUCCEEDED` 后仍返回原军情 JSON，因此共享页面业务代码不需要维护 Android 分支。
- 同账号、同参数且仍在途的重复查询返回同一 operation；完成后允许再次刷新。

共享 operation 进入旧 Android 传输前还会加入进程级账号锁，与后台调度器互斥。Python 回调 Kotlin 时只做一次非阻塞 `tryAcquire`；账号忙时 Kotlin 立即返回结构化 `LOCAL_ACCOUNT_BUSY`，Python operation 在自己的网络通道内可取消地退避重试。取得锁后会重新读取账号并再次检查平台所有者和 Session。

这里不能在 Python→Kotlin 同步回调中阻塞等锁：旧调度器持有账号锁期间，协议结果回写可能再次调用共享 Python；反向阻塞会形成“调度器持账号锁等 Python / Python operation 等账号锁”的锁反转。当前非阻塞握手消除了这个环。

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

最新 APK 在真机冷启动共享核心后，`GET /api/health` 返回 `migratedRouteCount=5`、`coreInitialized=true`；最新冷启动调用为 378 ms，调用前后 `AssistantForegroundService` 均未启动。

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

- 电脑端 Python：635 项测试通过。
- `app.js` 与 `assistant-api.js`：Node.js 语法检查通过。
- Native Bridge operation 行为测试：通过，覆盖 `202 → RUNNING → SUCCEEDED`。
- Android JVM：585 项测试、0 失败、0 错误；Release Kotlin 编译通过。
- 共享查询重复点击、完成后再次刷新、平台所有者门禁、共享 Session 门禁：全部通过。
- 账号通道连续两次返回 `LOCAL_ACCOUNT_BUSY` 后的退避恢复：operation 最终 `SUCCEEDED`，同步 Kotlin 回调路径不再阻塞等锁。

## 尚未完成

- `GET /api/accounts/settings` 与除 `POST /api/military/future/save`、`POST /api/liubu/save` 以外的设置保存路由仍由 Kotlin 负责映射；虽然已经进入独立 local-write 并使用同步 `commit()`，但尚未全部成为两端共享业务代码。
- 日志、任务状态、地图缓存等本地路由尚未逐条切换所有者。
- `/api/state/refresh` 的非军情 scope 及其他旧网络路由仍可能同步等待旧 Kotlin 网络实现。
- 军情真实成功路径尚未获得用户授权进行真机验证。
- operation 事件推送、页面重建后的统一加载态恢复和用户取消入口尚未全部接入页面。
- Python operation 与 Kotlin 调度器当前通过进程级账号锁互斥；阶段 9 仍需把调度本身迁入同一共享队列。

因此，阶段 7 仍为执行中，不能宣称 Android 所有“手机核心响应失败”路径已经消失。
