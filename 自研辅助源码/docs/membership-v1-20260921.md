# V109 会员第一版：手动开通，无在线支付

## 已实现

- 邮箱验证码注册、邮箱密码登录、邮箱验证码重置密码。
- 月/季/年卡为30/90/365天，普通注册不赠送付费权益。管理员确认收款后手动开通，
  未到期从原到期日顺延；停用、恢复、撤销会话与最近操作记录独立。
- 每会员唯一当前会话，新设备主动登录替换旧会话；旧会话的 renew/logout 不能抢回
  或注销新设备。IP仅用于限流，不是设备身份。设备请求以 Android Keystore RSA 密钥签名。
- 会员运行许可为独立RSA签名，固定issuer/audience、绑定会员/会话/设备/本次请求nonce，
  最长两小时且不超过会员到期日。公钥固定在APK，签名私钥只在服务端和本机钥匙串。
- APP启动恢复需要联网，启动游戏账号强制检查；运行期间本地检查单调时钟截止时间，
  到期才续验，不按每个游戏动作联网。网络失败不延长原许可，被明确撤销立即停止放行。
- 核心入口、原始游戏命令与自动重登均检查会员授权。后台不能用保存的会员密码抢回会话。
  会员失效不清除配置/账本；已确认出征且按配置需要撤防的矿队，只允许军情/角色读取与
  对原battleId的撤防。未知结果账本不重放。跨游戏账号启动使用设备级准入锁，最多2个启用账号。
- 被挤下线：持久原因、前台弹窗、后台通知（权限允许时）、账号“会员暂停”标识；
  与到期、停用、管理员撤销、密码已修改、网络故障区分，不将网络失败误报为别人登录。
- 当前只提供管理员和普通会员，不包括在线支付、代理/多客服角色、会员间游戏数据云同步。
  游戏账号/密码/Session仍只保存在各自手机；会员退出不删除本机游戏数据。

## 云端存储与接口

为避免地图D1额度故障影响授权，会员权威状态使用独立命名的Durable Object，
不依赖地图D1。目录为可重建的后台查询投影，管理员始终可按完整邮箱直查权威记录。
验证码成功消费与用户建立/改密一起持久化，登录/管理员变更按会员串行。

- 公共信息：`GET /v1/member/info`
- 发验证码：`POST /v1/member/send-code`
- 设备签名请求：`POST /v1/member/register|login|reset-password|renew|logout`
- 管理员：`GET /admin/api/members`、`POST /admin/api/members/query|update`
- 所有管理写操作要求管理员Cookie、同源Origin和专用意图头；固定套餐天数由服务端决定。
  管理变更带幂等ID，界面保留结果不明的操作ID，避免网络重试重复加时。
- 密码：scrypt N=32768/r=8/p=3，随机盐加服务端pepper；每isolate最多2个密码计算任务，
  两小时续验不重新计算密码。验证码6位、15分钟、最多5次错误，60秒发送冷却。
- 默认每邮箱6封/UTC日、全站50封/窗口，IP另限流。推广前按真实用户规模调整
  `MEMBER_EMAIL_DAILY_LIMIT` 和服务预算；不是无限免费运行承诺。
- 旧邮箱联通测试入口已通过 `EMAIL_PROBE_UNTIL=0` 关闭。

服务端签名/认证密钥为Worker Secrets；本机钥匙串服务：
`dwpm-member-auth-secret`、`dwpm-member-lease-private-key`。
公钥可公开，文件为 `cloud-shared-data/member-lease-public-key.txt`。
不能随意替换认证pepper或签名私钥，否则旧密码/会话/已分发APK会失效。

## 构建与发行

- 版本：V0.0.109。
- `release`：正式签名、不可调试、R8开启，DebugCommandProvider不进入Manifest。
- `membertest`：包名 `com.example.dwpmclone.membertest`，名称“帝王三国·会员验收”，
  独立数据/设备密钥，与原APP并排验证，不覆盖正在运行的V108。
- Release签名：用户私有“认证相关/dwpm-release.jks”，0600权限；密码在钥匙串
  `dwpm-release-keystore-password`。请同时备份keystore和密码，丢失后无法签发兼容更新。
- Release包签名证书 SHA-256：
  `ad3448dc84ece6575c1e9c01119787664333117714d435db3818be9634627d19`。
- Release必须提供 `DWPM_RELEASE_KEYSTORE`、`DWPM_RELEASE_STORE_PASSWORD` 和会员验签公钥，
  缺少时packageRelease明确失败，不生成可误发的无签名商业包。
- Debug包和旧版无会员门禁的内部测试包不得对外分发。正式签名与旧Debug签名不同，
  不应卸载原测试APP来强行覆盖，避免丢失其Keystore和游戏数据。

## 验证与当前交接状态

[TARGET] 自研Android客户端与 dwpm-data.292828.xyz 会员服务。

[EVIDENCE]

- Worker版本 `bef1074c-51be-4332-a56a-4eb384b60f1f` 已100%部署（2026-09-21 23:12）。
- 线上info返回30/90/365天、两小时、2账号，公钥与APK信任锚一致。
- 未登录访问管理员会员接口实际返回401，后台页面已包含会员管理面板。
- Worker111项、页面18项；共享核心会员门禁9项。
  全量Python本轮1370项通过。Android591项结果无失败，Gradle本轮复用未变更的测试结果。
- Android591项通过（含8项签名/设备/nonce/期限校验专项），正式签名校验通过。
- APK内49个Python/契约文件和前端资源逐字节核验；未发现已知Cloudflare管理密钥、
  Resend密钥、会员签名私钥/认证secret、发布签名密码被打包。
- 安装会员验收包时，手机返回 `INSTALL_FAILED_USER_RESTRICTED: Install canceled by user`。
  没有绕过限制、没有覆盖原APP；手机仍只安装原 `com.example.dwpmclone` V0.0.108。

### 2026-09-21 23:15 续作

- 本轮 `adb devices -l` 无设备，未再次安装、不创建真实会员、不授予付费时长。
- 先用新增页面用例复现3个失败：查询失败保留旧会员、查询响应乱序覆盖、等待
  邮件期间切换用途导致验证码绑定错误。修复后18项页面用例通过；另验证
  开通请求丢失回执后的同编号重试、页面刷新后恢复原套餐/备注、保存期间
  不切换会员、挤下线单次弹窗与持久提示、网络故障不误报其他设备登录。
- 修改仅限会员页面与文档/测试，没有改动游戏请求、自动任务和地图策略。
- `testDebugUnitTest assembleMembertest assembleRelease` 成功；两个包的会员
  前端与源文件逐字节一致。正式包不可调试、禁止备份、无DebugCommandProvider，
  apksigner验签通过，证书与上次一致。展开两包后复查未发现已知部署/邮件/
  会员签名/发布密码实值。线上会员公钥仍与构建公钥一致。
- 部署CLI在上传Worker后检查域名路由权限返回错误；随后独立查询Cloudflare
  deployments确认新版本100%生效，并对线上 `members.js`、`index.html`
  与本地文件逐字节核验。未修改域名路由、原变量、密钥或云端刷黄开关。
- 已在Chrome切到 `https://dwpm-data.292828.xyz/admin/` 并观察到后台，
  之后窗口状态/截图不可用，未声称完成新版页面的浏览器交互验收。
- Release APK SHA-256：`4cbcc6b19f2a25ae705cd3d77423061f64ebae968c7725e5268c41d33259bfb6`。
- Membertest APK SHA-256：`c87a31564a5437605491c32eb676a97198549e175fe7f8e1e85efb575706b16e`。
- 下一步：按 `membership-acceptance-guide.md` 连接真机完成端到端验收。

### 手机重新连接后的安装复核

用户确认重新接手机后，ADB已识别 `22081212C`。再次执行
`adb install -r app/build/outputs/apk/membertest/app-membertest.apk`，仍返回
`INSTALL_FAILED_USER_RESTRICTED: Install canceled by user`。
包列表仅有原APP，版本V0.0.108、最后更新2026-09-20 20:34:47；前台仍是原APP。
主用户无标准设备策略安装限制，尚不能仅据此断定MIUI拦截的具体开关。
需用户在手机允许安装后再继续，未更改手机安全设置或绕过确认。

### 2026-09-21 23:21 独立验收包安装成功

用户允许后重新安装成功，包名 `com.example.dwpmclone.membertest`，
版本 `V0.0.109-membertest`，设备包SHA-256与本地
`c87a31564a5437605491c32eb676a97198549e175fe7f8e1e85efb575706b16e` 一致。
已启动独立Activity并检查手机截图，会员登录/邮箱注册/忘记密码入口可见。
本地会员状态为 `MEMBER_LOGIN_REQUIRED`、`allowed=false`、`authenticated=false`，
健康检查核心初始化无错误，coreHash为
`b918f34c9b782751e19fe7cfe6c2999622371cc87366a176d544d8df2079cccd`。
验收包游戏账号数为0，未复制原APP账号或启动游戏任务。
原APP仍为V0.0.108，未覆盖/卸载/清数据。未观察到本次启动的崩溃或JS错误。
下一步需用户自行在手机注册并登录会员，密码/验证码不进入聊天或调试命令。

### 2026-09-21 23:33 V110会员页面隔离

按用户要求改为底部“攻略｜助手｜Home”，会员面板挂载于 `homeMembershipSlot`，
不再向body前插；手机Home专门展示会员页面，电脑Home设置查看功能保留。
续期点击先切换Home；授权、签名、校验频率、游戏逻辑和云端服务均未修改。
真机截图确认助手顶部恢复，底部三个入口完整可见。Home与其他页面的显隐和
续期跳转通过自动化测试；本轮未完成手机上的逐项点击和真实登录。

- 页面25项、Python1370项、Android591项通过；两种APK构建成功。
- V110验收包已安装并核对设备SHA-256：
  `7cc1124b0fbcbf0fbc40a799f3596bf18565a37dd790b8eea9754bca48008df7`。
- V110正式候选包SHA-256：
  `8e3a2a76195c95387aaf632ac62b51b2e25b2b333598e938559e5eace31566d4`。
- 原APP仍V108，未覆盖/清数据；未开通或改动会员。
- 待跟进的既有显示问题：未登录时区服目录云端读取被授权层拒绝，用户日志显示
  Java调用栈（V109首次启动即已存在）。不是本次布局调整导致的崩溃，未在本次
  页面调整中扩展修改其云端/授权策略。

[PARITY VERIFIED] 无会员端口的既有核心行为通过全量回归；有会员门禁时测试确认
暂停新请求、保留账本、只允许限定的矿队收尾。未把测试通过冒充完整真机业务验证。

[RELEASE DECISION] 暂缓广泛分发：需要用户在手机允许安装验收包，然后自行完成
真实邮箱注册/登录，由管理员手动开通，再验证启动游戏账号及两台设备挤下线。
密码由用户自己在APP设置，不应发到聊天。当前没有创建真实会员或擅自授予付费时长。

客户端本地功能无法承诺绝对防修改APK；本版目标是普通账号共享控制，明确接受
最长两小时旧授权窗口。新设备登录不使另一设备正在执行的游戏服务器战斗瞬间消失。
