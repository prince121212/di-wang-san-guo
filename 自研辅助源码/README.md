# 帝王三国资料库

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
- `domain/scheduler/SchedulerTickPolicy.kt`：按任务期限自适应调度；空闲期间不持有 WakeLock，单次执行窗口使用有超时短锁，并由 Handler、系统截止时间闹钟和执行窗口恢复看门狗共同兜底。
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

V0.0.105 的刷黄优先使用云端共享协调；云端额度耗尽、网络或服务不可用时，
同轮改用本机山贼/黄巾快照，没有可用目标则按原筛选有界补扫。降级不暂停
空闲编队，也不清理旧出征账本。普通故障每分钟探测，额度故障每五分钟探测；
只有预占和出征占用都确认成功才恢复共享。降级仍保护本机同服账号的在途目标，
但无法保证与其他设备的账号完全避让。

V0.0.107 起打矿只使用本机地图，不调用云端查图、扫描租约、预占或状态上报。
同平台同区服账号共用核心持久化观测池，各自应用搜索条件；刷黄本地路径也使用
此共享池。出征前通过短锁原子检查并保存账号账本，停止账号及重启后的未决出征
仍参与避让。旧打矿云端额度等待自动解除，真实在途/未知出征不清除、不重发。
旧宿主快照保留作兼容展示；新池按真实游戏扫描逐步填充，每批最多 5 个坐标。

V0.0.108 起支持后台“云端刷黄地图”全局开关。每次启动/重登账号及进程恢复后
该账号首次调度时读取最新配置；失败保留上次配置，无历史配置则本地运行。
关闭后不请求云端刷黄地图、心跳或新增地图上传队列，同机共享与互斥不变；
开启后恢复云端优先、本地兜底。已有出征账本不清理、不重发，打矿始终本地化。

V0.0.109 增加邮箱会员账号、管理员手动开通月/季/年卡、单手机有效会话与最长
两小时运行许可。启动游戏账号必须联网检查，被挤下线后明确提示并保留本机数据。
第一版不接在线支付；功能与发行边界见 `docs/membership-v1-20260921.md`，
管理员操作和真机验收步骤见 `docs/membership-acceptance-guide.md`。

V0.0.110 将手机底部导航调整为“攻略｜助手｜Home”。会员登录/注册/找回密码、
会员状态只在Home展示，不再插入助手页面顶部；助手里的续期按钮跳到Home。
手机Home隐藏原始游戏设置查看器，电脑端仍保留；授权校验与后台任务机制不变。

V0.0.111 将会员状态和游戏账号状态分开：助手显示“会员有效/待检查授权”等
准确状态，无游戏账号时显示“游戏账号未添加”。Home和助手共用状态展示规则，
重新检查后立即同步，旧轮询不得覆盖新结果。Home改为会员卡、授权操作、开通说明
分区展示；升级不修改账号配置、存储结构或Keystore别名。

V0.0.119 在Home会员卡下增加“换手机：导出/导入配置”，只手动触发。导出把本机
全部游戏账号、各功能设置和游戏密码保存到当前会员账号下（只保留最近一次）；游戏
密码在手机上用会员密码派生的密钥加密（PBKDF2-HMAC-SHA256 60万次 + AES-256-GCM，
绑定会员ID），服务器只存密文，整份文档另用服务端密钥加密落盘。导入需新手机已登录
会员并再次输入会员密码，先预览再确认；账号按平台+游戏账号+区服对应，与游戏密码
无关，已有账号保留本机密码、只合并设置，新账号默认停止、不自动登录游戏。会员密码
重置过时游戏密码解不开，账号和设置照常导入，需逐个重新输入游戏密码。导入前需先停止
所有游戏账号。

V0.0.120 上线官网 https://dwsg.292828.xyz（`official-site/`）并增加“检查更新”。Home
会员页新增“版本与更新”卡片：显示当前版本，每天最多两次静默查询官网最新版本，也可手动
检查；有新版本时 Home 标签带提示，点“下载新版本”用系统浏览器打开官网安装包，覆盖安装
保留账号与设置。只有正式签名版参与官网更新，调试/验收/内部版不提示；更新信息必须属于
本应用包名，下载地址限定为官网 HTTPS 上的版本化安装包。发版用
`official-site/scripts/publish-release.mjs`（只接受正式证书签名、版本号递增的安装包）。

V0.0.121 Home 会员页新增“官网与交流群”卡片：显示官网地址（dwsg.292828.xyz），点“打开
官网”用系统浏览器打开；显示 QQ 群“帝王三国攻略交流群”（879644685），点“复制群号”由
App 写入系统剪贴板（只接受纯数字群号）。测试版和内部版也显示。官网同步增加“加入交流群”。

V0.0.122 新用户注册即送 1 天体验会员：注册成功后 App 自动登录，体验立即生效，会员页显示
“体验会员”和精确到分钟的到期时间。防止多邮箱反复领取：注册时 App 上传手机型号和
ANDROID_ID 的哈希（不需要权限，卸载重装不变，恢复出厂才会变），服务端再结合本机安装的
设备密钥和注册 IP（IPv6 按 /64）判断，任一已被其他账号注册过就不送；服务端只保存这些值的
密钥哈希，不存原始 ANDROID_ID 或 IP。未送的原因写在管理后台该会员的操作记录里（例如“同一台
手机已由 xx 注册”），管理员可用“体验 · 1天”补发。旧版 App 注册同样按安装与 IP 判断。

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

环境：Gradle 8.10.2、Android Gradle Plugin 8.7.3、Kotlin 1.9.24、JDK 17、targetSdk 36。当前版本标识为 `V0.0.111`。

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

代码、离线测试、静态审计和 APK 构建完成后，真机安装、逐功能动作、锁屏、网络切换、进程重建与重启恢复仍作为独立验收阶段。V0.0.103 的编队独立调度及后续吞吐诊断见 `docs/brush-formation-lanes-20260919.md`、`docs/brush-throughput-bottlenecks-20260919-1330.md`；V0.0.104 隔离不可领取目标、区分云端依赖等待与编队恢复，验证结果见 `docs/brush-dispatch-eligibility-20260919.md`。V0.0.105 按用户最新授权改为刷黄离线降级，见 `docs/brush-local-fallback-20260919.md`。本地继续执行不等于云端额度已经恢复，也不替代下述完整验收。

完整验收标准见工作区根目录的 `手机端辅助V1架构.md`。

自动审计通过不等于完整真机验收。逐功能真实动作、6 小时锁屏、网络切换与 Session 过期、关闭页面后的托管、重启首次解锁恢复和真实托管抓包，必须在用户明确授权测试账号与范围后执行。
