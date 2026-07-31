# 阶段 5：统一 Core API 与平台适配层记录

> 状态：已完成
>
> 开始日期：2026-07-31
>
> 完成日期：2026-07-31

## 本阶段边界

本阶段建立双端共用的调用、异步 operation 和平台端口基础设施，但不在未经授权的情况下登录账号或发送真实游戏动作。

当前只有 `GET /api/health` 已在电脑端和 Android 同时切换为 `shared-python`。其他路由虽然已声明响应类型和最终归属，但仍由电脑端 Python 旧入口或 Android Kotlin 旧入口执行，将在阶段 6–8 逐条切换。

## 统一调用入口

`CoreFacade` 新增统一的：

```text
dispatch(method, path, body, request_context)
dispatch_json(method, path, body_json, request_context_json)
```

- 电脑 HTTP Handler 和 Android Chaquopy 均调用同一 `dispatch`。
- 本地路由直接执行本地处理器，不进入网络队列。
- 网络路由只校验请求并创建持久化 `operationId`，在调用线程返回 `202`，不等待游戏服务器。
- 已声明但未迁移的路由明确返回 `501 ROUTE_NOT_MIGRATED`，不会悄然走错误实现。
- 路由所有者矩阵会为每条路由生成 `currentDesktopOwner` 和 `currentAndroidOwner`，最终目标均为 `shared-python`。

## 持久化异步 operation

operation ledger 已升级为 schema 2，支持：

- `QUEUED / RUNNING / SUCCEEDED / FAILED / CANCELLED / UNCERTAIN` 六种状态。
- 同一账号串行，不同账号使用独立网络通道。
- 持久化幂等键；同键同输入返回原 operation，同键不同输入直接拒绝。
- 尚未发包的任务可取消；已发包的 mutation 不允许当成未执行任务重放。
- mutation 发包后异常或进程恢复时回执不明，进入 `UNCERTAIN`，禁止自动重发。
- 进度、结果、错误和事件全部持久化，页面或进程重建后可继续查询。
- JSON 写入使用临时文件、`fsync` 和原子替换。

operation ledger 不允许写入密码、Token、Cookie、Session、`dm` 等敏感字段。

## 平台端口

共享核心已定义凭据、数据目录、时钟、网络状态、通知、唤醒、日志和事件端口。

Android 宿主已接入：

- Keystore 凭据端口。
- App 私有数据目录。
- 当前网络状态。
- Android 日志和有界事件缓存。
- 系统通知和 Alarm 唤醒。

电脑端宿主已接入数据目录、结构化日志和事件 JSONL 端口。平台端口只提供系统能力，不包含 opcode、任务优先级或成功判定。

## 真机无网络验证

Android Debug APK 提交了 90 秒离线模拟网络任务。任务处于 `RUNNING` 时，仍可立即读取健康、设置、日志、任务状态、本地地图缓存和 operation 状态，没有出现“手机核心响应失败”。验证后所有模拟任务都已取消，设备上不存在 `QUEUED` 或 `RUNNING` 的调试任务。

8 轮反复读取的控制器耗时：

| 本地路由 | P50 | P95（8 样本下等于最大值） |
|---|---:|---:|
| 共享核心健康 | 0.70 ms | 0.77 ms |
| 账号日志 | 4.31 ms | 5.32 ms |
| operation 状态 | 2.75 ms | 5.18 ms |
| 本地地图缓存 | 65.37 ms | 92.46 ms |
| 旧 Kotlin 设置读取 | 200.70 ms | 245.38 ms |
| 旧 Kotlin 调度状态 | 201.72 ms | 240.17 ms |

这些数据证明长网络任务没有造成队头阻塞。同时，两条旧 Kotlin 本地路由仍略高于 200 ms 初始目标；其主要开销来自旧账号/调度快照组装与密钥存储读取，不是 operation 等待。阶段 6–7 迁移这些本地路由时必须消除不必要的秘密解密和重复快照构建，并重新做正式 P95 验收。

本轮只读设置与状态，没有修改账号配置、登录账号或访问游戏服务器。

## 验收结果

- 电脑端 603 项测试全部通过，`app.js` 语法检查通过。
- Android `testDebugUnitTest` 和 `compileReleaseKotlin` 通过。
- 真机 APK 内共享协议离线断言 101/101 通过。
- 本地源码和真机 APK 报告相同核心哈希：`7c8194665b3743cc4c17047eab2cc5b07752810c0150f4c71b765881585cd8c1`。
- Android 共享 Python 为 3.10.19，核心初始化 130 ms，连续健康调用约 0.4–0.8 ms。
- 已验证同账号串行、不同账号并行、幂等去重、取消、进程恢复和 `UNCERTAIN` 语义。

## 尚未解决的路径

`AssistantWebBridge` 当前仍使用一条 Kotlin executor。已进入共享 operation 的未来网络路由不会在该 executor 中等待；但尚未迁移的旧 Kotlin 网络接口仍可能阻塞它。

因此，本阶段的准确结论是“共享异步调度基础已建立，并通过离线长任务验证”，不是“手机所有核心响应失败都已消失”。要彻底消除旧阻塞路径，还需继续完成阶段 6 的账号/状态基础迁移和阶段 7–8 的路由切换。
