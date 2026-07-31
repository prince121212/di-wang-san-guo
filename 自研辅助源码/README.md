# 帝王三国手机端辅助 V1

这是一个可在 Android 手机上独立运行的本地辅助。电脑关机、电脑端辅助未启动或不存在时，手机仍能完成登录、保存设置、任务调度、游戏协议请求和本地地图管理。

设计以极简、单一职责和低功耗为原则：正式入口只有一个本地 WebView 容器，正式任务宿主只有一个前台服务，游戏动作只有一条真实协议通路。

## 架构

```text
本地 WebView 页面
  ↓ AssistantApi 异步消息桥
本地 Repository / 账号与配置
  ↓ 启用且拥有真实 Session 的账号
AssistantForegroundService
  ↓ 串行 TaskScheduler
统一出征前检查 + 出征事务账本
  ↓
SessionAwareGameProtocolClient
  ↓ 手机当前网络
游戏服务器
```

页面中的 `/api/*` 请求被 `assistant-api.js` 拦截后交给本机桥，不会访问电脑 Mobile API、代理服务或云地图。WebView 只允许载入 APK 内的 `assistant` 静态资源，外部导航和外部子资源会被拦截。

## 核心模块

- `AssistantWebActivity.kt`：唯一正式 Activity，加载 APK 内的共用前端。
- `ui/web/AssistantWebBridge.kt`：单线程异步桥，保证页面线程不读写仓库或发送协议。
- `ui/web/LocalAssistantApiController.kt`：本机 API 路由白名单。
- `data/account/*`：真实登录、Session 失效重登和网络切换恢复。
- `data/local/CredentialVault.kt`：Android Keystore + AES-GCM 凭据封装。
- `service/AssistantForegroundService.kt`：锁屏后继续运行的 `specialUse` 前台服务。
- `domain/scheduler/SchedulerTickPolicy.kt`：按任务期限自适应调度；60 秒内的紧迫任务保持 CPU，长等待改用系统合并唤醒并释放 WakeLock。
- `domain/protocol/ExpeditionPreflight.kt`：所有出征共用的 Session、将领、体力、忠诚、兵种和兵力检查。
- `data/local/ExpeditionTransactionRepository.kt`：出征发送前同步落盘的事务账本，防止回执不明时重发。
- `domain/localmap/LocalTargetCache.kt`：有界的内存热缓存。
- `data/local/LocalMapRepository.kt`：轻量 JSON 持久层，不初始化 Room，不进行网络同步。

## 本地地图

山贼和资源点的记录包含：

- 账号与区服标识。
- 目标 ID、X/Y、类型、等级和可解析筛选字段。
- 首次发现、最近验证、失效时间和失效原因。

山贼目标默认缓存 30 分钟，资源点默认缓存 3 小时；单个扫描坐标的空结果短期缓存 2 分钟，避免无目标时密集轮询。明确消耗或失效最后一个目标后，下一轮会立即重扫。

登录同时读取自有封地坐标。刷黄推荐中心按所选将领所在封地的数量决定，平票取最先选择的将领；坐标缺失时明确报错，不回退到固定假坐标。

## 安全边界

- 手机添加账号后自动保存无人值守重登凭据，不增加额外确认步骤。
- 密码和 Session 认证字段分别使用 Android Keystore + AES-GCM 密文保存，不写入账号 JSON、导出或日志。
- Keystore V2 别名兼容旧版本；旧密钥不可用时清理明文并要求重新登录，不阻断 Activity 启动。
- 日志统一经过敏感字段脱敏；TLS 使用 Android 默认的证书链和主机名校验，不安装 trust-all 实现。
- 只有用户明确保存的功能配置才能创建任务。
- 只有已启用且 `sourceMode == 1` 的真实 Session 才能进入正式调度。
- 正式源集不生成 mock Session 或 mock token。`MockGameProtocolClient` 仅存在 `app/src/debug` 中。
- `0x1522` 发送前必须持久化 `SENDING`；超时或回执不明时记录 `UNCERTAIN` 并禁止自动重发。
- 六部只开放已确认的金银花种植；未确认的收菜、偷菜和礼部动作不发送。打矿加速与撤防必须取得对应真实回执。没有确证的动作失败关闭，不显示为成功。
- 页面手动操作与后台调度共用账号锁；停止或掉线账号即使保留了重登 Session，也不能继续操作或显示为在线。
- 日志使用上限 1500 条的 JSONL 追加存储和单调 ID；成功记录来自结构化成功事实，不按“成功”文字模糊匹配。
- 不声明 VPN、Wi-Fi 修改、网络修改、文件共享或广播导出权限。
- 系统“强制停止”之后不尝试绕过 Android 规则自行恢复。

## 构建与测试

环境：Gradle 8.10.2、Android Gradle Plugin 8.7.3、Kotlin 1.9.24、JDK 17、targetSdk 36。当前版本标识为 `V0.0.15`。

```bash
cd "/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/自研辅助源码"
export JAVA_HOME="$HOME/.cache/codex-jdks/zulu17/zulu-17.jdk/Contents/Home"
./gradlew testDebugUnitTest assembleDebug compileReleaseKotlin
python3 -m unittest tools.test_mobile_debug -v
python3 tools/verify_v1_coverage.py --skip-device
```

共用前端测试：

```bash
cd "/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/电脑端辅助前端"
python3 -m unittest discover -s tests -q
```

Debug APK：

```text
/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/自研辅助源码/app/build/outputs/apk/debug/app-debug.apk
```

## 通用手机调试器

Debug APK 额外提供一条仅限 `adb shell/root/system/本应用 UID` 的命令通道，直接复用 WebView 的 `AssistantApiMessageCodec` 和 `LocalAssistantApiController`。它不复制副本、军情或任何其他业务逻辑；Release APK 不包含该入口。GET 默认允许，POST 必须显式传 `--allow-post`，电脑 CLI 与手机 Provider 会分别校验。

```bash
python3 tools/mobile_debug.py identity
python3 tools/mobile_debug.py call GET /api/health
python3 tools/mobile_debug.py status 1608600
python3 tools/mobile_debug.py logs 1608600 --limit 100
python3 tools/mobile_debug.py snapshot 1608600 --out before.json
python3 tools/mobile_debug.py diff before.json after.json --ignore-key capturedAt
```

快速迭代使用 `python3 tools/mobile_debug.py fast`：增量构建、`adb install -r`，然后核对包名、版本、PID 和设备/本地 APK SHA-256；默认不打开 Activity，也不自动启动账号任务。需要看页面时单独执行 `python3 tools/mobile_debug.py open-ui`。

## 当前验收边界

代码、离线测试、静态审计和 APK 构建完成后，真机安装、逐功能动作、锁屏、网络切换、进程重建与重启恢复仍作为独立验收阶段。本轮离线对齐不调用 ADB、不安装 APK，也不运行真机脚本。

完整验收标准见工作区根目录的 `手机端辅助V1架构.md`。

自动审计通过不等于完整真机验收。逐功能真实动作、6 小时锁屏、网络切换与 Session 过期、关闭页面后的托管、重启首次解锁恢复和真实托管抓包，必须在用户明确授权测试账号与范围后执行。
