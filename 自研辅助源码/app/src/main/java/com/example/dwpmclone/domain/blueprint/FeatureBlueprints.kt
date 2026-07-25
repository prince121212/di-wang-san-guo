package com.example.dwpmclone.domain.blueprint

/**
 * v1 product blueprint for the self-developed mock assistant APK.
 *
 * Scope guard:
 * - keeps UI/config/task scheduling/protocol-shape/logging reconstruction work;
 * - removes the standalone 找帅 product entry;
 * - removes original commercial license/purchase/trial/unbind flows;
 * - keeps real network execution blocked behind a lawful GameProtocolClient boundary.
 */
data class FeatureBlueprint(
    val id: String,
    val nameZh: String,
    val evidenceTier: EvidenceTier,
    val userVisibleFunctions: List<String>,
    val sourceEvidence: List<String>,
    val inferredMechanism: String,
    val kotlinModules: List<String>,
    val rebuildStatus: RebuildStatus,
    val blockersForRealGameParity: List<String>
)

enum class EvidenceTier {
    UI_AND_MANIFEST_VERIFIED,
    UI_VERIFIED_PROTOCOL_INFERRED,
    ASSETS_VERIFIED,
    V1_SUPPLEMENTAL_MOCK
}

enum class RebuildStatus {
    MOCK_OR_UI_CAN_BUILD,
    REAL_PROTOCOL_BLOCKED,
    LOCAL_ONLY_CAN_BUILD
}

object FeatureBlueprints {
    val all: List<FeatureBlueprint> = listOf(
        bp(
            id = "account_processing",
            name = "账号管理与账号处理框架",
            functions = listOf("账号新增/编辑/删除", "区服、渠道、版本选择", "mock 登录态与 session/token 占位", "本地 VPN/代理接口占位"),
            modules = listOf("GameAccount", "GameSession", "LocalConfigRepository", "AccountProcessingScreen")
        ),
        bp(
            id = "background_hosting",
            name = "后台托管主控",
            functions = listOf("启动/停止后台挂机", "全部开始/停止", "同区互斥", "延迟、重连、日志、通知"),
            modules = listOf("AssistantForegroundService", "TaskScheduler", "TaskLogRepository")
        ),
        bp(
            id = "shua_huang",
            name = "自动刷黄 / 刷山贼",
            functions = listOf("每日次数", "起始坐标", "山贼/黄巾", "铜钱阈值", "编队选择", "删除邮件提速"),
            modules = listOf("ShuaHuangConfig", "GameProtocolShapes", "ShuaHuangTask")
        ),
        bp(
            id = "mine_search_and_mining",
            name = "找矿 / 刷矿",
            functions = listOf("前台/后台搜索", "资源点类型筛选", "无人/驻防筛选", "命中提醒/震动", "自动刷矿"),
            modules = listOf("MineConfig", "ResourcePointSnapshot", "MineSearchMockTask")
        ),
        bp(
            id = "daily_tasks",
            name = "一键日常",
            functions = listOf("签到", "惊喜宝箱", "加忠", "征收", "竞技/俸禄", "捐献", "删邮件", "领奖"),
            modules = listOf("DailyConfig", "DailyProtocolShapes", "DailyPipelineTask")
        ),
        bp(
            id = "general_maintenance",
            name = "将领维护",
            functions = listOf("自动加体", "保持满忠", "自动营救", "自动治疗", "资源转换占位"),
            modules = listOf("GeneralConfig", "GeneralProtocolShapes", "GeneralMaintenanceMockTask")
        ),
        bp(
            id = "formation_troop",
            name = "编队 / 配兵",
            functions = listOf("将领编队", "兵种兵数", "补满兵占位", "中文名规则提示"),
            modules = listOf("FormationConfig", "GeneralProtocolShapes", "FormationUpdateMockTask")
        ),
        bp(
            id = "internal_affairs",
            name = "自动内政",
            functions = listOf("空位建设", "建筑升级", "低级优先", "建筑优先级"),
            modules = listOf("InternalAffairsConfig", "InternalAffairsProtocolShapes", "InternalAffairsMockTask")
        ),
        bp(
            id = "dungeon",
            name = "自动副本 / 自动闯关",
            functions = listOf("副本次数", "章节/关卡", "宝箱位置", "闯关状态链", "冷却处理"),
            modules = listOf("DungeonConfig", "DungeonProtocolShapes", "DungeonMockTask")
        ),
        bp(
            id = "inventory",
            name = "宝库 / 背包整理",
            functions = listOf("库存查询", "开宝箱/银票", "丢弃物品/装备", "品质/等级筛选", "令牌保留"),
            modules = listOf("InventoryConfig", "InventoryProtocolShapes", "InventoryCleanupMockTask")
        ),
        bp(
            id = "surrender_release",
            name = "自动劝降 / 自动释放",
            functions = listOf("成长阈值", "金币劝降选项", "释放阈值", "动作日志"),
            modules = listOf("SurrenderReleaseConfig", "RemainingAutomationProtocolShapes", "SurrenderReleaseMockTask")
        ),
        bp(
            id = "resource_point_send_general",
            name = "资源点送将",
            functions = listOf("资源点坐标", "送出将领", "配 1 兵", "停止计时", "两段出征 shape"),
            modules = listOf("ResourcePointSendGeneralConfig", "RemainingAutomationProtocolShapes", "ResourcePointSendGeneralMockTask")
        ),
        bp(
            id = "alarm_withdraw",
            name = "警报扫描 / 撤防",
            tier = EvidenceTier.V1_SUPPLEMENTAL_MOCK,
            functions = listOf("关键词匹配", "震动/通知", "撤防动作生成", "mock 误报保护"),
            modules = listOf("AlarmWithdrawConfig", "ResponseStructureShapes", "AlarmWithdrawMockTask")
        ),
        bp(
            id = "auto_loot",
            name = "自动掠夺",
            tier = EvidenceTier.V1_SUPPLEMENTAL_MOCK,
            functions = listOf("目标列表 mock", "编队选择", "两段出征动作生成", "真实执行二次确认"),
            modules = listOf("AutoLootConfig", "RemainingAutomationProtocolShapes", "AutoLootMockTask")
        ),
        bp(
            id = "vip",
            name = "游戏内 VIP 功能开关",
            functions = listOf("VIP 开关页", "映射自动加体/捐献/内政/救兵/加忠/劝降", "不复刻原 APK 商业授权"),
            modules = listOf("VipFeatureConfig", "VipFeatureMockTask")
        ),
        bp(
            id = "bulk_tools",
            name = "批量工具",
            functions = listOf("令牌加统", "小战鼓八卦", "残缺宝藏图", "一键领任务成就"),
            modules = listOf("BulkToolConfig", "BulkToolsMockTask")
        ),
        bp(
            id = "guide_and_reference",
            name = "资料查询 / 攻略 / 名将",
            tier = EvidenceTier.ASSETS_VERIFIED,
            status = RebuildStatus.LOCAL_ONLY_CAN_BUILD,
            functions = listOf("名将速查", "攻略文本", "开区查询 mock", "城池搜索 mock", "宝藏筛选 mock"),
            modules = listOf("LocalGuideRepository", "OpenServerQueryMockTask", "CitySearchMockTask", "TreasureSearchMockTask")
        ),
        bp(
            id = "config_log_notify",
            name = "配置、日志、通知、震动、导入导出",
            tier = EvidenceTier.UI_AND_MANIFEST_VERIFIED,
            status = RebuildStatus.MOCK_OR_UI_CAN_BUILD,
            functions = listOf("配置 JSON 导入导出", "账号独立配置", "任务日志", "通知 channel", "震动提醒占位"),
            modules = listOf("LocalConfigRepository", "TaskLogRepository", "AssistantForegroundService")
        )
    )

    private fun bp(
        id: String,
        name: String,
        functions: List<String>,
        modules: List<String>,
        tier: EvidenceTier = EvidenceTier.UI_VERIFIED_PROTOCOL_INFERRED,
        status: RebuildStatus = RebuildStatus.REAL_PROTOCOL_BLOCKED
    ) = FeatureBlueprint(
        id = id,
        nameZh = name,
        evidenceTier = tier,
        userVisibleFunctions = functions,
        sourceEvidence = listOf("自研辅助apk交接文档.md", "recovered screen_specs.json where applicable"),
        inferredMechanism = "v1 复刻 UI、配置、任务状态机、协议 shape、日志和通知；默认 MockGameProtocolClient，不连接真实游戏服务器。",
        kotlinModules = modules,
        rebuildStatus = status,
        blockersForRealGameParity = listOf("真实 session/key", "请求外层包装", "脱敏响应样本", "合法授权的 RealGameProtocolClient")
    )
}
