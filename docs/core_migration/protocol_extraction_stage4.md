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

## 离线同源验证

`CoreFacade.protocol_fixture_report()` 直接从共享 `protocol_parity_fixtures.json` 运行字节断言。Android Debug APK 通过进程内路由 `GET /api/core/verification/protocol` 执行了同一份 Python 代码：

```text
checkCount   = 18
passedCount  = 18
failureCount = 0
coreHash     = 9f9d3849e22f71017cb150451a9df25f59456eb10fbc9a7dd3140cfface1b2a8
```

覆盖项包括：

- 普通/混淆响应 envelope。
- 配兵和补兵的请求字节与回执语义。
- 五种出征功能的预出征与正式出征字节。

该路由只在 Debug 版开放，全程不登录账号、不读取 Session、不访问网络。

## 后续批次

- 目标搜索 0x8540/0x8542 解析与筛选。
- 掠夺、无损、副本和军情回执解析。
- 角色、将领、军队、背包与日常纯解析。
- 全部协议 fixture 纳入 APK 内自检后，才结束阶段 4。
