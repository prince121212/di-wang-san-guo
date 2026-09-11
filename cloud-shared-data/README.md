# 帝王三国共享云端数据

## 管理员后台

打开 `https://dwpm-data.292828.xyz/` 或 `/admin/` 即可进入只读管理后台。
后台使用独立的固定管理员账号密码登录，登录会话为 8 小时的签名
`HttpOnly/Secure/SameSite=Strict` Cookie；管理员密码和会话密钥只保存在
Cloudflare Worker Secret，不写入前端资源或仓库。

后台可视化展示：

- Passport 完整公共区服目录、匿名在线心跳、`LOCAL_ONLY/CLOUD_SHARED` 模式和共享门槛；
- 山贼/资源点数量、扫描分块、活动扫描租约及目标协调状态；
- 与电脑端山贼地图一致的 XY 坐标网格、洛阳标记、等级/掉落/步弓骑车筛选、
  缩放、点位详情和目标明细表；
- 资源点地图、资源类型和玩家占领筛选。

后台是只读投影，不提供释放租约、修改目标状态或删除地图数据的操作。
匿名角色 ID 只返回打码后的短标识，预占令牌永不返回。

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
`actorId` 是由平台键、区服键和角色 ID 在客户端生成的 SHA-256，90 秒无心跳
自动过期。

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
重新观察恢复和大批量观察固定 6 条 D1 写语句。

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

矿点出征成功后当前采用保守策略：在矿点 3 小时 TTL 内不自动重新开放，
防止同区服账号重复攻打。后续只在有可验证的回城/撤防事实时才可提前释放。
