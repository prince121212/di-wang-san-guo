package com.example.dwpmclone.domain.config

import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.DungeonProtocolShapes

data class ConfigValidationIssue(
    val field: String,
    val message: String,
    val severity: ValidationSeverity = ValidationSeverity.ERROR
)

enum class ValidationSeverity { ERROR, WARNING }

object ConfigValidators {
    fun validateServerName(serverName: String): List<ConfigValidationIssue> = buildList {
        if (serverName.isBlank()) add(ConfigValidationIssue("serverName", "所在区服不能为空"))
        if (serverName.isNotBlank() && serverName.all { it.isDigit() }) {
            add(ConfigValidationIssue("serverName", "所在区服不能填纯数字，例如双线102区、H2、挑战、体验"))
        }
    }

    fun validateGuaji(config: GuajiConfig): List<ConfigValidationIssue> = buildList {
        if (config.reconnectDelaySeconds < 0) add(ConfigValidationIssue("reconnectDelaySeconds", "掉线重连秒数不能为负数"))
        if (config.requestDelayMillis !in 0..10_000) add(ConfigValidationIssue("requestDelayMillis", "延迟范围应为0-10000毫秒"))
        if (config.antiIpBanEnabled && config.requestDelayMillis !in 100..800) {
            add(ConfigValidationIssue("requestDelayMillis", "防封IP建议延迟100-800毫秒", ValidationSeverity.WARNING))
        }
        if (config.antiIpBanEnabled && !config.sameServerMutex) {
            add(ConfigValidationIssue("sameServerMutex", "防封IP要求同区只同时挂机一个号", ValidationSeverity.WARNING))
        }
    }

    fun validateShuaHuang(config: ShuaHuangConfig): List<ConfigValidationIssue> = buildList {
        if (config.dailyLimit !in 1..500) add(ConfigValidationIssue("dailyLimit", "每日刷黄次数应在1-500之间"))
        if (config.selectedFormationIds.isEmpty()) add(ConfigValidationIssue("selectedFormationIds", "需要至少选择一个出征编队", ValidationSeverity.WARNING))
        if (config.minCopperWan < 0) add(ConfigValidationIssue("minCopperWan", "铜钱保持阈值不能为负数"))
    }

    fun validateMine(config: MineConfig): List<ConfigValidationIssue> = buildList {
        if (config.resourcePointLimit < 0) add(ConfigValidationIssue("resourcePointLimit", "资源点上限不能为负数"))
        if (config.selectedMineTypes.isEmpty()) add(ConfigValidationIssue("selectedMineTypes", "至少选择一种矿", ValidationSeverity.WARNING))
        if (config.selectedFormationIds.isEmpty() && config.enabled) add(ConfigValidationIssue("selectedFormationIds", "刷矿需要选择出征编队", ValidationSeverity.WARNING))
        if (config.searchIntervalMinutes < 12) add(ConfigValidationIssue("searchIntervalMinutes", "后台搜索间隔至少12分钟", ValidationSeverity.WARNING))
        if (config.onlyEmptyMine && config.onlyDefendedMine) add(ConfigValidationIssue("mineFilter", "无人矿与专找有驻防矿不能同时作为唯一条件"))
    }

    fun validateGeneral(config: GeneralConfig): List<ConfigValidationIssue> = buildList {
        if (config.minEnergy < 0) add(ConfigValidationIssue("minEnergy", "体力阈值不能为负数"))
        if (!config.requireChineseNamePrefix) add(ConfigValidationIssue("requireChineseNamePrefix", "原界面要求将领名/封地名中文开头", ValidationSeverity.WARNING))
    }

    fun validateDungeon(config: DungeonConfig): List<ConfigValidationIssue> = buildList {
        if (config.dailyTimes <= 0) add(ConfigValidationIssue("dailyTimes", "每日刷副本次数必须为正数"))
        if (config.formationIds.isEmpty() && config.enabled) add(ConfigValidationIssue("formationIds", "自动副本需要选择出征编队", ValidationSeverity.WARNING))
        if (config.chapter !in 0..6) add(ConfigValidationIssue("chapter", "副本章节应为第1-7章"))
        val stageCount = DungeonProtocolShapes.stageCount(config.chapter)
        if (stageCount > 0 && config.stage !in 1..stageCount) {
            add(ConfigValidationIssue("stage", "第${config.chapter + 1}章关卡应为1-$stageCount"))
        }
        if (config.boxPosition !in 0..2) add(ConfigValidationIssue("boxPosition", "副本宝箱位置应为左、中、右"))
    }

    fun validateSurrenderRelease(config: SurrenderReleaseConfig): List<ConfigValidationIssue> = buildList {
        if (config.releaseGrowthBelow >= config.surrenderGrowthAbove) add(ConfigValidationIssue("growthThreshold", "自动释放阈值应低于自动劝降阈值"))
    }

    fun validateResourcePointSendGeneral(config: ResourcePointSendGeneralConfig): List<ConfigValidationIssue> = buildList {
        if (config.enabled && config.stopAfterMinutes <= 0) add(ConfigValidationIssue("stopAfterMinutes", "资源点送将需要设置几分钟后停止"))
        if (config.requiresKeepFullLoyaltyOff) add(ConfigValidationIssue("keepFullLoyalty", "开启前需关闭将领设置里的时刻保持满忠", ValidationSeverity.WARNING))
    }

    fun validateAutoLoot(config: AutoLootConfig): List<ConfigValidationIssue> = buildList {
        if (config.enabled && config.selectedFormationIds.isEmpty()) add(ConfigValidationIssue("selectedFormationIds", "自动掠夺需要选择编队", ValidationSeverity.WARNING))
        if (config.enabled && config.targetPlayerName.isBlank()) add(ConfigValidationIssue("targetPlayerName", "自动掠夺需要填写目标玩家"))
        if (config.enabled && config.targetFiefIndex <= 0) add(ConfigValidationIssue("targetFiefIndex", "目标封地序号必须大于0"))
    }

    fun validateAlarmWithdraw(config: AlarmWithdrawConfig): List<ConfigValidationIssue> = buildList {
        if (config.enabled && config.keywords.isEmpty()) add(ConfigValidationIssue("keywords", "警报扫描至少需要一个关键词"))
        if (config.mockOnlyProtection && config.withdrawDefense) add(ConfigValidationIssue("withdrawDefense", "当前本地调度只记录撤防计划，不执行真实撤防", ValidationSeverity.WARNING))
    }

    fun validateLicense(config: LicenseConfig, action: LicenseAction): List<ConfigValidationIssue> = buildList {
        if (!config.agreedToTerms) add(ConfigValidationIssue("agreedToTerms", "需要先同意协议"))
        if (action != LicenseAction.TRIAL && config.registrationCode.isBlank()) add(ConfigValidationIssue("registrationCode", "注册码不能为空"))
    }
}
