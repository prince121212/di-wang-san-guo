# 帝王三国共享云端数据

## 管理员后台

打开 `https://dwpm-data.292828.xyz/` 或 `/admin/` 即可进入管理后台。
后台使用独立的固定管理员账号密码登录，登录会话为 8 小时的签名
`HttpOnly/Secure/SameSite=Strict` Cookie；管理员密码和会话密钥只保存在
Cloudflare Worker Secret，不写入前端资源或仓库。

后台可视化展示：

- Passport 完整公共区服目录、匿名在线心跳、`LOCAL_ONLY/CLOUD_SHARED` 模式和共享门槛；
- 山贼/资源点数量、扫描分块、活动扫描租约及目标协调状态；
- 与电脑端山贼地图一致的 XY 坐标网格、洛阳标记、等级/掉落/步弓骑车筛选、
  缩放、点位详情和目标明细表；
- 资源点地图、资源类型和玩家占领筛选。

### 会员管理（APP V0.0.109）

用户先在 APP 验证邮箱并注册，管理员在“会员管理”按完整邮箱查询，再手动
开通月卡30天、季卡90天或年卡365天；未到期的会员从原到期时间顺延。
第一版不接在线支付。支持停用、恢复、撤销会话以及最近操作记录。

查询失败立即清空操作对象，乱序返回不会覆盖最后一次查询，保存期间不切换
管理对象。网络中断造成结果不明时，保留原操作编号；重新查询能按审计记录
确认结果，否则恢复原套餐/备注供幂等重试，避免重复加时。

新用户注册成功即送 1 天体验（`plan: "trial"`）。每个注册按三把钥匙判断：APP 上传的
ANDROID_ID 哈希、设备签名密钥、`cf-connecting-ip`（IPv6 取 /64）；任一已被其他账号先注册
过就不送。每把钥匙是一个 `member-trial-v1:<HMAC>` Durable Object，只存首个注册者，永不过期、
不存原始 IP 或设备标识。未送原因写入该会员审计（管理员可见，APP 不可见），管理员可用
“体验 · 1天”补发，补发不会改掉正在生效的付费套餐名。

会员授权独立存储于 Durable Object，不依赖地图 D1 额度。新设备登录替换旧
会话，手机启动游戏账号时校验、运行期间最长两小时续验。详细设计见
`../自研辅助源码/docs/membership-v1-20260921.md`，操作与待办验收见
`../自研辅助源码/docs/membership-acceptance-guide.md`。

`npm test` 包含111项 Worker 测试和18项页面回归（含平台折叠、会员管理、
手机验证码交互及挤下线提示），页面测试不向生产服务发送邮件或开通权益。

平台标题可独立展开/收起所属全部区服，也允许所有平台同时收起。默认展开仅在
首次取得非空目录时执行一次，数据刷新不覆盖用户的折叠选择；从区服下拉框
主动选择区服时，仍会展开对应平台。`npm test` 包含此行为的 7 项页面交互回归。

地图数据仍是只读投影，不提供释放租约、修改目标状态或删除地图数据的操作。
匿名角色 ID 只返回打码后的短标识，预占令牌永不返回。

### 云端刷黄地图开关（APP V0.0.108 起）

后台顶部提供全局“云端刷黄地图”开关，首次部署保持开启，不自动改变现有用户策略。
开启：沿用云端优先、本地兜底。关闭：APP 只读写本机山贼地图，同机同平台同服
账号共享观测并原子避让目标；打矿仍始终本地化，不受开关影响。

- APP 每次显式启动/重登账号、进程恢复后首次调度账号，先读取
  `POST /v1/client/config`（Runtime Token 只读权限）。同一运行周期不按编队重复请求。
- 配置读取失败保留最后一次有效配置；首次无配置时默认本地。重新开启后在账号
  下次启动时读取，不要求正在本地运行的 APP 反复探测云端。
- 关闭时 Worker 在访问 D1 前拒绝山贼地图请求，返回明确的
  `CLOUD_BRUSH_MAP_DISABLED` 和配置版本；心跳返回本地模式，不写 D1。
  新版 APP 收到关闭通知后立即转本地，不清除或重发在途/未知出征。
- `GET/POST /admin/api/runtime-config` 仅允许管理员签名 Cookie；修改还校验
  同源 Origin、自定义意图头、严格布尔值及版本号，避免过期页面覆盖新的决定。
- 开关存在独立的 SQLite-backed Durable Object（`RUNTIME_CONFIG`），不使用
  地图 D1 的写入额度。管理员登录的限流也迁到独立命名的控制对象，仍保持
  15 分钟窗口内 5 次失败、锁定 10 分钟；不保存密码，只保存计数并自动清理。
  地图 D1 故障不妨碍登录、查看或修改开关。无需升级付费计划。
- 发布需执行 `wrangler deploy`，随部署应用 `runtime-config-v1` DO migration；
  不新增 D1 表、不清空已有地图或客户端上传队列。随后发布新版 APK。

本地开发时在 `.dev.vars` 配置 `ADMIN_USERNAME`、`ADMIN_PASSWORD` 和至少
32 个字符的 `ADMIN_SESSION_SECRET`，然后运行 `npm run dev`。

本目录只是跨设备公共数据服务。账号密码、游戏 Session/dm、代理、
用户设置、角色/将领/背包/封地、任务账本、记录、提示、日志和游戏原始
响应始终只保存在各自设备。

## 工作模式

- 同平台同区服只有 1 个在线角色：只发送匿名心跳，地图完整保持原本的
  本地搜索和本地存储，不读写云地图。
- 至少 2 个不同匿名角色心跳有效：进入 `CLOUD_SHARED`，启用云目标
  查询、每批最多 20 个坐标的扫描租约、标准化观察上传和目标原子预占。
- 账号曾进入共享模式后云端暂时故障：地图任务安全延后，不回退到
  本地抢同一目标。
- 从未进入共享模式且心跳失败：继续保持现有单账号本地机制。

区服作用域使用 `(platformKey, serverKey)` 无碰撞编码，不使用显示名称兜底。
`actorId` 是由平台键、区服键和角色 ID 在客户端生成的 SHA-256。心跳有效期
由 `PRESENCE_TTL_MILLIS` 决定（当前部署为5分钟）；同一角色的重复心跳
最多每90秒更新一次数据库，不是每次请求都写入。

## v2 事件交付与额度

- 一个 observations 请求的 upserts、gone 和旧链接清理在同一 D1 batch
  事务提交；任一步失败，不能先确认或留下半个成功批次。
- 客户端本地去重不等于网络恰好交付一次。有效期内的相同 upsert、已是
  missing 的 gone 不重复写行，也不推进 `changed_at`。真实字段变化、
  合法复活和过期记录续期仍立即处理，预占和在途状态不被观察覆盖。
- gone 最多200个 ID，使用 `json_each(?)`，不展开超过 D1 的100参数上限。
- 增量查询使用 `(changed_at,target_id) > (?,?)` 与复合索引匹配；
  没有变化时不从区服地图第一行重新扫描。
- D1 日免费读/写额度耗尽返回 HTTP503、`CLOUD_D1_DAILY_LIMIT` 及
  `retryAtMillis`/`Retry-After`，不伪装成业务成功。免费额度重置时间为
  UTC00:00（北京时间08:00）；代码修复不能追回当天已经用掉的额度。

2026-09-19的实际根因、部署及手机核验见
`../自研辅助源码/docs/cloud-d1-throughput-root-cause-20260919.md`。

## 云端数据白名单

允许保存：

- 公共区服目录；
- 山贼和资源点的标准化地图字段；
- 区域扫描新鲜度和扫描租约；
- 目标的 `available/reserved/dispatching/dispatched/rejected/missing/uncertain`
  协调状态；
- 匿名且自动过期的在线心跳。

Worker 对山贼/资源点扩展字段使用封闭白名单投影。未知字段会被丢弃，
`password`、`session`、`dm`、`rawPayload`、`taskLedger` 等内容不会入库。
游戏 URL 在客户端发送前移除用户名、密码、query 和 fragment，Worker 再次
清洗。

完整区服目录与运行观测分开保存：`server_directory` 是客户端从 Passport
取得的平台完整快照；`server_catalog` 只表示曾经有账号心跳的区服。客户端在
读取本地区服下拉框或成功获取 Passport 列表后，会后台调用
`POST /v1/servers/directory/sync`。因此未登录、未扫描的区服也会出现在管理员
目录中，但其在线账号和地图数量保持为 0。

## 本地验证

需要 Node.js 22：

```sh
nvm use
npm install
npm run check
npm test
```

测试使用真实本地 D1，覆盖单账号边界、区服隔离、扫描租约并发、目标
原子预占、合法/非法状态转换、租约过期恢复、Cron 清理、`uncertain`
重新观察恢复和 legacy 大批量观察固定6条 D1 语句，以及 v2 批次回滚、
重复交付零写入、生产参数上限和增量查询的实际读行成本。

## 客户端配置

电脑端从环境变量读取：

```sh
export DWPM_CLOUD_SHARED_DATA_URL="https://dwpm-data.292828.xyz"
export DWPM_CLOUD_SHARED_DATA_TOKEN="<runtime-client-token>"
```

Android 从未提交的 `自研辅助源码/local.properties` 或构建环境变量读取：

```properties
DWPM_CLOUD_SHARED_DATA_URL=https://dwpm-data.292828.xyz
DWPM_CLOUD_SHARED_DATA_TOKEN=<runtime-client-token>
```

Runtime Client Token 只用于调用这组固定数据接口，应可随时轮换。Cloudflare
管理 API Token 绝不得进入项目、电脑端客户端、`local.properties` 或 APK。
`CLIENT_API_TOKEN_V2` 是兼容式轮换槽：新增客户端凭据时保留原 `CLIENT_API_TOKEN`，
两者仅拥有相同的客户端接口权限，不能修改管理员开关。不要覆盖旧值使已安装用户失联。
当前开发 Mac 会从本机钥匙串项 `dwpm-cloud-shared-data-runtime-token`
读取 Runtime Client Token；其他电脑仍通过上述环境变量配置。Android 构建
在该 Mac 上也会使用同一钥匙串项，但只将 Runtime Token 写入本地构建产物。

## Cloudflare 部署顺序

1. 使用项目专用 D1，不复用其他项目数据库。
2. 将真实 D1 database ID 写入本机 `wrangler.jsonc`后应用远端迁移。
3. 生成独立的 Runtime Client Token，用 `wrangler secret put CLIENT_API_TOKEN`
   写入 Worker Secret，不提交实值。
4. 部署 Worker，先在线验证 health、单账号门槛、双账号租约和并发预占。
5. 再配置电脑端和 Android，重启/重新构建后用同区服两个真实账号验证。

矿点出征成功后当前采用保守策略：在矿点24小时 TTL 内不自动重新开放，
防止同区服账号重复攻打。后续只在有可验证的回城/撤防事实时才可提前释放。
