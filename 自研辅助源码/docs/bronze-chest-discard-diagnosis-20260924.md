# 1608601青铜宝箱未丢弃：只读诊断

## 当前阶段 / Current phase

2026-09-24约16:46，ADB设备27a83c9c、原包com.example.dwpmclone V0.0.111。
目标：解释16:43附近传音符和山贼头巾已丢弃、青铜宝箱却保留的原因。
未修改手机配置、未执行游戏请求或丢弃、未安装版本。

## 已验证事实 / Verified facts

- 游戏账号1608601对应本地sessionId=202，热血三国联盟周年服352区。
- /api/accounts/settings保存的config和residentAutomationConfigJson.inventory均确认：
  autoOpenEnabled=true，autoOpenItemNames包含青铜宝箱；cleanInventory=true，
  discardItemNames同样包含青铜宝箱、精铁宝箱、山贼头巾、传音符、屯田令。
- 日志：16:43:02开启铜钱辎重1个，丢弃传音符2个、山贼头巾431个。
  山贼头巾丢弃完成时间1790239382946，即本地16:43:02.946，与用户16:43:03描述吻合。
- 当次服务器丢弃回执中的背包与当前持久化背包均有青铜宝箱317个
  （99+99+99+20，itemId=58），青铜钥匙0个；并非物品名称未识别。
- inventoryPendingActionJson为空，没有青铜宝箱未知结果账本阻塞证据。

## 关键证据 / Key evidence

shared_core/python/dwpm_core/features/inventory.py，plan_next_automatic_inventory_action：
自动开启必须拥有对应钥匙；丢弃遍历遇到name in auto_names则无条件跳过。
因此同时设置开启和丢弃的宝箱，没有钥匙时既不会开启，也不会丢弃。
规划器最终仅返回“背包当前没有需要处理的物品”，未解释配置冲突。
现有test_shared_inventory_automation.py还明确测试并锁定了缺钥匙保留策略。

在内存中取实际青铜宝箱/钥匙快照及实际生效策略调用纯规划函数：
原策略返回action=None/no-action；只在内存副本去掉自动开启列表中的青铜宝箱后，
返回discard-item、itemId=58、requestedCount=317。没有把修改写回手机。

设备APK与本地debug APK SHA-256相同：
cbcaa1d74beb8a7322df4493b2b4fe18cec219089a468152b7c6ce38bed28f08。
分析时inventory.py SHA-256：
930c6afceb5bcb49411c51de2510562f1d9fd0c1cc6995c70550c0f2b00d3517。

## 推断与置信度 / Inference and confidence

高置信度：不是调度时间未到，不是丢弃任务未执行，而是自动开启的保留优先级
覆盖显式丢弃配置。规则与界面未提示冲突，造成用户预期与执行不一致。
精铁宝箱也同时勾选，未来有库存而没有钥匙时同样会保留；当前快照库存为0。

## 建议下一步 / Suggested next steps

1. 若目的为全部丢弃，用户可只取消自动开启列表中的青铜宝箱，保留丢弃配置。
2. 若目的为“能开先开、没钥匙的丢弃”，需用户确认后修改冲突策略并补回归。
   这属于真实物品销毁语义变化，不能在只读诊断中自行部署或改配置。
