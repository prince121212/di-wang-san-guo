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

## 离线同源验证

`CoreFacade.protocol_fixture_report()` 直接从共享 `protocol_parity_fixtures.json` 运行字节断言。Android Debug APK 通过进程内路由 `GET /api/core/verification/protocol` 执行了同一份 Python 代码：

```text
checkCount   = 44
passedCount  = 44
failureCount = 0
coreHash     = 9c409a1994dc2399b4f6823768f3c2f4274f060a5ee12526792a0597e76aa041
```

覆盖项包括：

- 普通/混淆响应 envelope。
- 配兵和补兵的请求字节与回执语义。
- 五种出征功能的预出征与正式出征字节。
- 出征、打矿预览、召回和行军加速回执。
- 0x8540/0x8542 目标解析、扫描顺序以及等级和归属筛选。
- 掠夺封地、无损状态/结算/阵容和副本目录/通关选择/战斗状态。

该路由只在 Debug 版开放，全程不登录账号、不读取 Session、不访问网络。

## 后续批次

- 军情回执解析。
- 角色、将领、军队、背包与日常纯解析。
- 全部协议 fixture 纳入 APK 内自检后，才结束阶段 4。
