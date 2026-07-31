# Android 内嵌共享 Python 核心 POC 报告

> 验证日期：2026-07-31（Asia/Shanghai）
>
> 结论：阶段 3 通过，可以继续抽离真实业务逻辑。

## 结论

Android 已经在应用进程内加载仓库中唯一的 `shared_core/python/dwpm_core`，没有在 Android 目录中新建可手工编辑的第二份核心。电脑端与真机 APK 报告相同的：

```text
core        = dwpm-shared-python
coreVersion = 0.2.0
coreHash    = 7ff7ecacff94b341284b0648745e2075a4840e557fe824f8776f88e67170efa1
```

WebView 也已经通过现有 `AssistantWebBridge` 完成真实的进程内请求和回调。纯离线的 90 秒模拟任务运行时，页面本地 health 请求 P95 为 `1.8ms`，远低于初始 `200ms` 目标。

## 运行时选择

| 项目 | 选择 |
|---|---|
| Android Gradle Plugin | 8.7.3 |
| Chaquopy | 17.0.0 |
| Android 内 Python | 3.10.19 |
| compile/target SDK | 36 / 36 |
| min SDK | 24 |
| APK ABI | `armeabi-v7a`、`arm64-v8a` |

项目原来的 `minSdk` 是 23。官方版本表显示：

- Chaquopy 17 支持 AGP 7.3–9.2，但要求 API 24。
- Chaquopy 16.1 支持 AGP 7.0–8.13，也要求 API 24。
- 最后支持 API 21 的 Chaquopy 15 只支持到 AGP 8.5。

因此“AGP 8.7 + API 23”没有受官方支持的组合。本阶段选择将 `minSdk` 提高到 24，而不降级整个 Android 构建链。连接的小米 22081212C 是 Android 13 / API 33 / `arm64-v8a`，实机兼容。

官方版本表：https://chaquo.com/chaquopy/doc/current/versions.html

## 实现边界

1. Gradle 的 Python source set 直接指向仓库 `shared_core/python`。
2. 构建时在 `app/build/generated/sharedPythonBundle` 生成四份契约和 `source_manifest.json`，构建产物不提交、不手工编辑。
3. APK 内 `app.imy` 包含唯一核心的 8 个 Python 源文件、`pyproject.toml`、四份契约和构建哈希。
4. `SharedPythonCoreHost` 是进程级单例；`SharedCoreApplication` 在后台线程预热解释器，不占用 Android UI 线程。
5. 正式业务路由尚未切换所有者；`androidBusinessOwner=migration-poc-only` 明确防止将 POC 误当成迁移完成。

## 异步 operation 验证

Debug 版提供四条离线 POC 路由：

- `POST /api/core/operations/simulate`
- `GET /api/core/operations/status`
- `GET /api/core/operations`
- `POST /api/core/operations/cancel`

它们由 `ApplicationInfo.FLAG_DEBUGGABLE` 限制，Release 不开放。模拟任务只使用时钟、本地 JSON 账本和后台调度线程；源码不导入 `socket`、`requests` 或 `urllib`，不可能访问游戏服务器。

关键语义已验证：

- 提交立即返回 `202 + operationId`。
- 同一幂等键与相同输入只返回原 operation。
- 不同输入误用同一幂等键会失败关闭。
- 运行结果原子落盘到 App 私有目录。
- 调度线程在应用后台预热时创建，不将线程创建成本放到用户第一次点击上。
- 页面重建和应用进程重建后仍可通过原 `operationId` 读取最终结果。

## 性能数据

真机为小米 22081212C（Android 13 / API 33）。

| 指标 | 结果 |
|---|---:|
| Python 解释器启动 | 首次 341ms；后续进程 229–238ms |
| CoreFacade 初始化 | 首次 66ms；后续进程 35–46ms |
| 预热后 Python health 调用 | 约 0.55–0.60ms |
| WebView 完整桥接 health（100 次） | P50 1.5ms，P95 1.8ms，P99 2.1ms |
| 预热后模拟网络任务受理 | 5.9–12.2ms |
| 90 秒任务运行期间本地 health | P95 1.8ms，最大 2.1ms |
| Debug Provider 内 controller health（25 次） | P50 0.619ms，P95 0.842ms |
| 空闲页面 + WebView + Python 总 PSS/RSS | 194,535KB / 335,192KB |
| 空闲页面线程数 | 49 |

ADB `content call` 的端到端 P95 约 1.09 秒，其中绝大部分是每次创建 ADB shell 命令的调试开销；同一次请求在 App controller 内的 P95 只有 0.842ms，因此不将 ADB 数值当作产品延迟。

## 构建与体积

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| 迁移前 Debug APK | 2,378,937 字节 | `0d6d55155158a5b0da28947bf23fb5ed6615a8ce2f6e19bd0231134c8acb57a0` |
| 阶段 3 Debug APK | 27,064,798 字节 | `86bb59bdf98f431a85a327709d764bbc61d2b53339eac94751baa18de344f8ee` |
| 阶段 3 Release unsigned APK | 25,848,580 字节 | `c04fc61df384c206d8ee7a8ba9fd7ae903e157e5ee081372f42380dbf896353f` |

Debug APK 增加 24,685,861 字节（约 23.54MiB），主要是两套 ARM Python 运行时。这是当前最明显的代价，但不构成技术阻断；阶段 11 可评估 App Bundle/ABI split，不能为缩小 APK 恢复第二套 Kotlin 业务核心。

## 回归结果

- 电脑端 Python：524 项通过。
- 共享前端 JavaScript 语法：通过。
- Android JVM：582 项，0 失败、0 错误、0 跳过。
- Android Debug APK：构建、安装、身份与 SHA 校验通过。
- Android Release APK：`assembleRelease` 及 lint vital 通过。
- 手机通用调试器：10 项通过。

## 保留问题

1. 构建机没有 Python 3.10，Chaquopy 因此提示未预编译 `.pyc`。真机启动数据已证明不阻断，但 CI/发布环境后续应固定对应的 build Python。
2. PSS 中 WebView 图形内存占比很高；阶段 11 需分离测量“只有后台核心”与“打开 WebView”两种状态。
3. 现有 Kotlin 真实网络路由尚未切换到 operation 模型，它们仍可能触发原来的 30 秒假超时；阶段 3 证明了新路线可行，不代表旧路由已自动修复。
4. 本阶段没有登录任何账号，没有调用真实功能 POST，没有发送任何游戏请求。
