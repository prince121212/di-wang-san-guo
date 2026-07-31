# 阶段 4：纯协议与纯规则抽离记录

> 状态：进行中
>
> 开始日期：2026-07-31

## 批次 1：字节基础、配兵与出征 payload

已将以下逻辑从电脑端 `server.py` 机械抽离到唯一共享 Python 核心：

- `dwpm_core.protocol.wire`：UTF 字段、请求包封装、响应包拆解、混淆解码、opcode/payload 取值、坐标和 gamehex 转换。
- `dwpm_core.features.formation`：兵种字典、配兵 0x1226/0x8226、批量补兵 0x1229/0x8229、治疗 0x1230/0x8230 与预估 0x1231/0x8231。
- `dwpm_core.features.expedition`：刷黄、打矿、掠夺、无损和副本的 0x1520/0x1522 出征 payload。
- `dwpm_core.contracts`：电脑端仓库文件与 Android APK 内嵌资源使用相同的契约加载入口。

`server.py` 的同名方法仍保留稳定 API，但函数体只委托给 `shared_*` 实现，不再保留第二份字节规则。

## 批次 2：目标、矿点与出征回执

继续把以下电脑端已验证逻辑机械抽离到共享核心：

- `dwpm_core.features.targets`：0x8540 山贼解析、0x8542 资源点解析、目标 ID 编码、掉落/兵种/等级/归属筛选、世界地图规范扫描网格、距离排序和目标去重。
- `dwpm_core.features.mine`：0x8520 预览、0x8526 召回、0x8524 行军加速、行军符选择和请求 payload。
- `dwpm_core.features.expedition.parse_dispatch_response`：0x8522 正式出征回执。
- `dwpm_core.protocol.wire.extract_utf_strings`：回执内 UTF 事件字段的共用提取。

电脑端保留原函数名兼容现有调用者，但实现均为共享函数的薄委托。抽离前后使用同一批抓包 fixture 做完整结果对比，0x8540 和 0x8542 的返回对象逐字段相等。

## 批次 3：掠夺、无损与副本

继续抽离三组纯业务规则：

- `dwpm_core.features.raid`：0x1310 查询 payload 与 0x8310 玩家封地列表解析。
- `dwpm_core.features.lossless`：等级规范化、0x8900 状态、0x8904 目录、0x8906 敌军阵容、0x8908 等级选择回执、0x8902 结算，以及 10 级卫兵阵容判定。
- `dwpm_core.features.dungeon`：副本输入规范化、0x8930 目录、首个未通关关卡选择、多人末关跳过、关卡编号解析、0x8938 战斗状态、开箱位置和明确战败识别。

迁移过程中全量测试捕获到一次私有战败文本收集函数遗漏；现已将该函数也纳入共享模块，并由桌面兼容包装调用。修正后电脑端 555 项测试全部通过。

## 批次 4：军情与将领底层记录

军情包尾依赖将领记录解析，因此先建立 `dwpm_core.features.generals`，再由 `dwpm_core.features.military` 单向依赖它：

- `generals`：0x8004/0x8600 共用的 114 字节将领体恢复、兵力表关联和将领状态短标签。
- `military`：0x1600 请求体、0x8600 三分区严格解析、来袭文案重建、行军/战斗/驻守/返回状态、包尾在外/俘虏将领证据，以及多包快照去重和排序。

共享实现已与 2026-07-14、2026-07-26 的多组真实军情抓包逐对象对比，包括完整包尾的 14 名自有将领、19 名俘虏和 6 条配兵记录。电脑端 561 项测试全部通过。

## 批次 5：角色、军队与背包

继续补全状态与资产解析：

- `generals`：0x8004 角色资源头、官职字典、各封地空闲/伤兵、0xa110 将领实时状态和军情文本。
- `inventory`：0x8104 固定道具表、旧版保守回退、V5 装备实例、品质/强化/保底字段。

电脑端本地物品和装备静态表作为只读数据参数传给共享解析器；字段读取、边界判定、回退规则和输出结构均只存在于共享 Python。真实 0x8104 抓包仍解析为 26 组道具、7 件装备，电脑端 566 项测试全部通过。

## 离线同源验证

`CoreFacade.protocol_fixture_report()` 直接从共享 `protocol_parity_fixtures.json` 运行字节断言。Android Debug APK 通过进程内路由 `GET /api/core/verification/protocol` 执行了同一份 Python 代码：

```text
checkCount   = 53
passedCount  = 53
failureCount = 0
coreHash     = b44c5f39092420325686689cf777e084d4b821aaf29f01d627b10def2bdb5ee0
```

覆盖项包括：

- 普通/混淆响应 envelope。
- 配兵和补兵的请求字节与回执语义。
- 五种出征功能的预出征与正式出征字节。
- 出征、打矿预览、召回和行军加速回执。
- 0x8540/0x8542 目标解析、扫描顺序以及等级和归属筛选。
- 掠夺封地、无损状态/结算/阵容和副本目录/通关选择/战斗状态。
- 0x8600 来袭/行军/战斗/驻守/返回、军情快照和将领底层记录。
- 0x8004 角色/将领/军队、0xa110 状态与 0x8104 道具/装备。

该路由只在 Debug 版开放，全程不登录账号、不读取 Session、不访问网络。

## 后续批次

- 日常、内政和六部纯解析与规则。
- 全部协议 fixture 纳入 APK 内自检后，才结束阶段 4。
