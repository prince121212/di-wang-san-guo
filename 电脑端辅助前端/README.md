# 帝王三国电脑端辅助前端 + 本地后端

入口目录：

```text
/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/电脑端辅助前端
```

## 启动

```bash
cd /Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/电脑端辅助前端
python3 server.py
```

浏览器打开：

```text
http://127.0.0.1:17351/index.html
```

## 安卓端统一核心（Mobile API）

安卓端现在是电脑端的控制面，电脑端是唯一的游戏协议、账号会话、任务调度、每日完成锁、代理和日志核心。手机不再复制一套游戏协议，也不会接收游戏密码、`gameHttp`、`dm`、session token 等敏感字段；手机通过 Mobile API 读取脱敏快照、更新配置、启停任务，并在 WebView 中复用这套完整电脑端控制台。

默认服务只监听 `127.0.0.1`。需要让同一局域网的安卓手机访问时，建议在终端运行新增的启动器：

```text
/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/开启电脑端手机API.command
```

启动器会要求输入或生成 `DWPM_MOBILE_API_TOKEN`，再以局域网绑定方式重启服务，并在终端显示手机入口。Token 和用于生成 `accountRef` 的 Secret 会保存到用户目录下的私有文件（macOS 默认：`~/Library/Application Support/DWPMDesktop/mobile_api.env`，权限 600），不放在网页根目录；之后直接运行 `重启电脑端辅助.command` 也会保留手机 API。需要撤销手机访问时删除该文件并重启，或重新生成 Token。也可以手动启动：

```bash
cd "/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国"
export DWPM_DESKTOP_BIND_HOST=0.0.0.0
export DWPM_MOBILE_API_TOKEN="请替换为随机长 Token"
export DWPM_MOBILE_API_SECRET="建议固定保存的随机值"
"$PWD/重启电脑端辅助.command"
```

手机端在 Home →「电脑端统一核心」填写电脑地址和 Token，点击「测试电脑端连接」，再点击「保存并打开完整控制台」。入口地址为：

```text
http://电脑局域网IP:17351/api/v1/mobile/web?token=DWPM_MOBILE_API_TOKEN
```

配对请求只用一次 query token，服务端随后换成 `HttpOnly`、`SameSite=Strict` Cookie；普通 API 使用 `Authorization: Bearer`、`X-Device-Id` 和写操作 `Idempotency-Key`。局域网静态访问只开放 `index.html`、`app.js`、`styles.css`，数据库、日志、报告和源码即使持有 Token 也不能下载。`DWPM_MOBILE_API_SECRET` 用于稳定生成不透明 `accountRef`，建议跨重启保持不变。手机 WebView 顶部的“电脑端核心”工具栏还可以打开账号总控、山贼地图和资源地图；电脑版的 `+容器` 只是多窗口排版，不影响手机管理全部账号。

### Mobile API 主要契约

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/mobile/health` | 健康检查与账号/会话数量 |
| GET | `/api/v1/mobile/capabilities` | 功能矩阵、日常独立开关、兼容桥白名单 |
| GET | `/api/v1/mobile/accounts` | 脱敏账号列表 |
| GET | `/api/v1/mobile/accounts/{accountRef}/snapshot` | 角色、资源、将领、军队、背包、科技、军情、任务和最近日志 |
| GET | `/api/v1/mobile/accounts/{accountRef}/settings` | 设置与配置 revision |
| POST/PATCH | `/api/v1/mobile/accounts/{accountRef}/settings` | 按 scope + revision 乐观锁更新配置 |
| GET | `/api/v1/mobile/accounts/{accountRef}/tasks` | 任务状态 |
| POST | `/api/v1/mobile/accounts/{accountRef}/account` | 启停账号 |
| POST | `/api/v1/mobile/accounts/{accountRef}/tasks` | 启停保存任务 |
| POST | `/api/v1/mobile/accounts/{accountRef}/daily` | 签到、竞技币、三项捐献、俸禄、国家征收、城主征收、名将候选/拜访 |
| GET | `/api/v1/mobile/accounts/{accountRef}/logs` | 增量账号日志 |
| POST | `/api/v1/mobile/legacy` | 严格白名单的旧电脑端接口兼容桥 |

其中「自动捐献」一次独立任务会依次尝试铜钱、粮食、科技积分三个接口；任一项失败不会跳过兄弟项，也不会改变签到、俸禄、征收或名将拜访的任务锁。名将拜访候选由电脑端实时查询，手机按用户勾选顺序最多提交 4 名，服务器按顺序失败顺延。

### 回归测试

```bash
python3 -m unittest discover -s tests -p 'test*.py'
node --check app.js
```

当前 Mobile API 加入后电脑端测试为 380 项；测试账号验收应遵循“先只读快照/设置/日志，再单账号单功能动作”的顺序，避免一次性启动全部账号。

## 同一账号跨区服运行规则

- 同一个游戏平台账号即使登录不同区服，也会互相顶掉游戏会话。
- 同一账号任意时刻只能运行一个区服；切换区服前，必须先停止旧区服的起号任务并关闭旧区服账号。
- 不允许依赖“区服不同”绕过重复登录保护，否则两个区服都可能反复掉线、无法正常运行。

## 已接入的真实链路

前端整体已按 `/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/帝三辅助设计`
中的 21 张原型图还原为手机辅助样式的电脑端网页壳；真实操作链路通过底部
「保存设置」和添加账号弹窗接入本地后端 API：

1. `添加`
   - 打开添加账号弹窗；
   - 输入账号、密码、区服；
   - 后端真实登录 passport + 游戏服；
   - 读取角色、区服、将领数据。

2. `保存设置`
   - 读取「刷黄」页配置；
   - 后端发送 `041540`；
   - 解析真实 `0x8540` 目标列表；
   - 按前端控件筛选目标类型、山贼等级、步弓骑车条件。

3. 后台自动出征
   - 后端发送 `15200a0` prepare；
   - 后端发送 `15220a0` expedition；
   - 返回战报文本；
   - 证据报告保存到：

```text
/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/电脑端辅助前端/reports/
```

## 步弓骑车控件含义

前端视觉仍保留原型中的 `步弓骑车` 四位码输入，例如：

```text
5203 = 步≤5、弓≤2、骑≤0、车≤3
```

- `0525` = 步≤0、弓≤5、骑≤2、车≤5
- `5203` = 步≤5、弓≤2、骑≤0、车≤3
- `5000` = 必须含步 + 步≤5、弓≤0、骑≤0、车≤0，即只选“只含步兵类型”的山贼

当前 041540 可以稳定拿到目标等级、坐标、掉落等真实字段；敌方步/弓/骑/车精确明细仍需要继续用更多战报样本校准。现在后端已先接入可执行的等级模板筛选模型，控件会真实影响找黄结果和出征目标选择。


## 当前验证证据

最近一次 5000 筛选 + 真实出征成功证据：

```text
/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/电脑端辅助前端/reports/frontend_controls_5000_success_verification.json
```

该证据显示：

- 测试账号真实登录到 `董全 Lv.12`；
- 后端从真实登录数据读取到将领列表；
- `5000` 筛选命中 `compositionCode=1000` 的 1级山贼；
- 真实发送 `15200a0 + 15220a0` 后，战报包含 `消灭 步1消灭1级山贼`。

## 2026-07-14 打矿与资源地图

- `0x1542/0x8542` 按抓包确认结构解析，资源协议类型为
  镔铁、水晶、玄铁、牧场、浆果、灵草、玉露、银矿；牧场再按
  `level=1/2/3` 显示为一级、二级、三级牧场。
- 完整业务编号保留 1～13，其中已消失的金矿、冰玉矿、仙芝园
  不再出现在可选项中，实际可选 10 种。
- 资源点、扫描区域、区域关系、扫描租约和目标占用均写入
  `reports/shared_maps/shared_maps.sqlite3`，资源点有效期为 3 小时。
- 电脑版工具栏的“山贼地图”下方新增“资源地图”，可按资源类型和
  玩家归属筛选，并展示数量、守军、发现时间和剩余有效期。
- 打矿执行链路：

```text
容量/将领/配兵检查
→ 以中心坐标扫描资源点
→ 排除玩家占领点
→ 出征前按 resourceId 定点复核
→ 0x1520 预览并校验目标坐标
→ 0x1522 正式出征
→ 0xa110 确认将领状态“防”
→ 0x1600/0x8600 确认军情“驻守”
→ 0x1526/0x8526 召回
→ 确认将领回闲
→ 重新扫描并更新资源地图
```

## 2026-07-08 保存设置自动刷黄修复

本轮修复了「刷黄页面点击保存设置没有反应」的问题：

- 前端底部 `保存设置` 现在会收集：
  - 登录后的 session；
  - 「军事 → 配兵」里启用的出征将领、兵种、数量；
  - 「刷黄」页中心坐标、扫描格数、目标等级；
  - 步弓骑车四位码，例如 `5203` = 步≤5、弓≤2、骑≤0、车≤3；
  - 循环上限、循环间隔。
- 新增后端接口：
  - `POST /api/settings/save`：保存配置并启动后台自动刷黄任务；
  - `GET /api/automation/status?sessionId=...`：查看后台任务状态和日志；
  - `POST /api/automation/stop`：停止后台任务。
- 后台任务真实执行的链路：

```text
保存设置
→ 041540 找山贼
→ 按 5203 / 等级 / 类型筛选
→ 任选一个命中目标
→ 使用配兵页选中的将领发送 15200a0 + 15220a0 出征
→ 记录战报与 report 文件
→ 等待将领返回
→ 治疗伤兵节点
→ 0x1229 批量补兵/补满该将领
→ 进入下一轮并重复，直到达到循环上限或手动停止
```

当前边界：

- 补兵已接入已恢复的 `0x1229 reqBathAddArmy / 批量补兵`，请求格式为 `count + 8-byte general ids`，响应解析 `0x8229`。
- 治疗伤兵协议请求字段仍未完全确认，电脑端仍只保留“治疗伤兵”节点和日志，不发送未知治疗包，避免误操作。

## 2026-07-08 配兵到目标兵种数量接入

本轮进一步把“补兵至 200 轻骑兵”的语义向真实客户端靠拢：

- 新增 `0x1226 generalWithSoldier` 配兵请求：
  - payload = `writeLong(generalId) + writeByte(group=0) + writeShort(soldierTypeCode) + writeInt(count)`；
  - `轻骑兵` 的 row code 为 `3`；
  - 对“将领A 200 轻骑兵”会发送 payload：`generalId + 00 + 0003 + 000000c8`。
- 新增 `0x8226` 配兵响应解析；成功状态按客户端 handler `z.S()` 的 `status == 1` 判断。
- 后台循环恢复阶段现在顺序为：

```text
治疗伤兵节点
→ 0x1226 将领配兵到目标兵种/数量（例如 200 轻骑兵）
→ 0x1229 批量补兵/补满
→ 下一轮找黄
```

说明：治疗协议 `0x1231/0x1230` 字段已恢复并生成安全计划，但当前仍等待稳定“当前伤兵数量”来源；缺少数量时不会盲发治疗包。

## 2026-07-08 治疗伤兵真实请求接入

治疗协议已从“只记录节点”推进为可发送真实请求：

- `0x1231`：治疗费用预估；
- `0x1230`：治疗伤兵；
- 缺少精确伤兵数时，使用客户端历史 shape 对应的“治疗全部”语义：

```text
0x1231: fiefId + soldierType=-1 + count=-1
0x1230: fiefId + group=2 + soldierType=0 + count=-1 + useGold=0
```

后台循环目前恢复阶段为：

```text
治疗伤兵
→ 0x1226 配兵到目标兵种/数量
→ 0x1229 批量补兵/补满
→ 下一轮找黄
```

如果当前将领记录缺少 `fiefId/placeID`，治疗会安全跳过并继续后续配兵/补兵。
