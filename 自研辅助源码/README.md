# 自研服务 Android 项目

这是一个原生 Kotlin + Gradle 的 Android 控制端。正式托管采用“电脑端统一核心 + 安卓远程控制面”：电脑端负责游戏协议、账号会话、任务调度、每日完成锁、代理和日志；安卓端负责连接、展示、配置更新和操作触发。

## 第一性原理架构

```text
电脑端 server.py
  ├─ 游戏协议 / 登录态 / 账号与代理
  ├─ 任务调度 / 每日独立锁 / 日志
  ├─ 脱敏 Mobile API
  └─ 完整电脑端 Web 控制台
          ▲
          │ HTTPS/HTTP + Bearer Token + Device ID + 幂等键
          ▼
安卓 RemoteCoreActivity（WebView）+ DesktopCoreApiClient（原生薄客户端）
```

- **唯一事实源**：安卓不再复制电脑端协议和任务生命周期；WebView 直接复用电脑端完整页面，电脑端修复一次即可同步到手机。
- **敏感信息隔离**：安卓只保存 Mobile API Token，不接收或写入游戏密码、session token、`gameHttp`、`dm`。
- **独立生效**：签到、竞技币、三项捐献、国家俸禄、国家征收、城主征收、名将拜访分别由电脑端独立开关、独立锁和独立完成状态管理。
- **兼容迁移**：原生 `AssistantForegroundService`、协议和资料页暂时保留，供离线资料与迁移期本地模式使用；启用电脑端统一核心后，正式任务优先走远程核心。

## 主要模块

- `MainActivity.kt`：主流程、页面路由、只读登录入口。
- `RemoteCoreActivity.kt`：安全配对并加载电脑端完整控制台，限制同源导航和文件访问。
- `data/remote/DesktopCoreApiClient.kt`：Mobile API 薄客户端，支持账号快照、配置 revision、任务启停、独立日常动作和兼容桥。
- `data/remote/DesktopCoreSettingsRepository.kt`：电脑地址、Mobile API Token、设备身份的私有设置。
- `BaseUiActivity.kt`：从主 Activity 拆出的通用原生 UI 组件与样式工具。
- `data/protocol/RealGameProtocolClient.kt`：生产环境只读协议链路：passport 登录/区服列表 → enter 区服 → 游戏服 `0x1003` → `0x1004` → `0x1016`。
- `data/local/*Repository.kt`：本地账号、角色状态、配置、资料和日志存储。
- `domain/protocol/*ProtocolShapes.kt`：协议形状与领域模型记录，用于只读解析和本地调度边界说明。
- `domain/scheduler/*`：迁移期本地任务计划、配置映射、调度状态机与日志输出。
- `ui/ScreenSpecRenderer.kt`：将 `screen_specs.json` 渲染为原生 Android 配置表单。
- `tools/verify_v1_coverage.py`：本地覆盖检查脚本。
- `tools/device_smoke_test.sh`：真机/模拟器安装启动烟测脚本。

## 构建

已验证配置：

- Gradle Wrapper：`8.10.2`
- Android Gradle Plugin：`8.7.3`
- Kotlin Android plugin：`1.9.24`
- JDK：17
- `versionName`：`1.0-v2-real-login`

推荐命令：

```bash
cd "/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/自研辅助源码"
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export PATH="$JAVA_HOME/bin:$PATH"
./gradlew :app:assembleDebug :app:testDebugUnitTest --no-daemon
```

产物：

```text
app/build/outputs/apk/debug/app-debug.apk
```

## 测试

当前已补充 JVM 单元测试：

- 协议解析：区服行解析、区服选择、`0x8004` 角色状态前缀解析。
- 配置映射：`LocalConfigRepository` 导出的页面配置键 → `SavedConfigTaskPlanFactory` 账号和任务计划。

运行：

```bash
./gradlew :app:testDebugUnitTest --no-daemon
```

## 说明

## 电脑端连接

在电脑端运行：

```text
/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/开启电脑端手机API.command
```

然后在安卓 Home →「电脑端统一核心」填写 `http://电脑局域网IP:17351` 和启动器显示的 Token，先测试连接，再打开完整控制台。电脑端 Mobile API 默认只允许回环访问；局域网模式必须显式设置 Token。启动器会把 Token/Secret 保存到电脑用户目录的私有配置文件，普通重启也会继续开放 API；建议固定 `DWPM_MOBILE_API_SECRET`，让不透明账号引用跨重启保持稳定。

## 测试与产物

```bash
cd "/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/自研辅助源码"
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export PATH="$JAVA_HOME/bin:$PATH"
./gradlew :app:testDebugUnitTest :app:assembleDebug
```

当前全量单元测试：368 项；Debug APK：

```text
/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/自研辅助源码/app/build/outputs/apk/debug/app-debug.apk
```

手机 WebView 顶部的“电脑端核心”工具栏还提供账号总控、山贼地图、资源地图和一键开始保存任务入口；电脑版的 `+容器` 属于多窗口排版能力，手机使用账号选择器和总控进入同一批账号。

真实账号验收顺序固定为：账号列表 → 脱敏快照 → 设置 revision → 任务/日志状态 → 名将候选查询；确认无误后只用一个测试账号执行一个动作，不批量启动全部账号。
