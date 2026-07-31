package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.AssistantTask
import com.example.dwpmclone.domain.protocol.SchedulerBehaviorContract

/** Builds one local task per explicitly saved configuration; protocol guards own mutation safety. */
object TaskFactory {
    fun buildBackgroundTaskSet(
        accountId: Long,
        configs: AssistantConfigBundle,
        schedulerContract: SchedulerBehaviorContract = SchedulerBehaviorContract.defaults()
    ): List<AssistantTask<*>> = SchedulerTaskOrdering.order(buildList {
        // 电脑端在每个出征任务内部按该编队执行治疗、加体和配兵。
        // 后台不再把全部配兵规则作为一个全局前置批次，避免一条规则失败阻断其他编队。
        configs.lossless?.takeIf { it.enabled && it.rules.any { rule -> rule.enabled } }
            ?.let { add(LosslessTask(accountId, it)) }
        configs.shuaHuang?.takeIf { it.enabled }?.let {
            add(ShuaHuangTask(accountId, it))
            add(BanditPrefetchTask(accountId, it))
        }
        configs.mine?.takeIf { it.enabled || it.backgroundSearch }?.let {
            add(MineTask(accountId, it))
            if (it.enabled) add(MinePrefetchTask(accountId, it))
        }
        configs.daily?.takeIf { it.enabledSteps.isNotEmpty() }?.let { daily ->
            // The desktop scheduler locks/completes sign-in and arena coins
            // independently.  Do not put them back into one aggregate task:
            // a rejected sign-in must remain visible without suppressing the
            // arena feature (and vice versa).
            daily.enabledSteps
                .filter { it == DailyStep.SIGN_IN || it == DailyStep.ARENA_REWARD }
                .forEach { add(DailySingleStepTask(accountId, it)) }
            val legacySteps = daily.enabledSteps - setOf(
                DailyStep.SIGN_IN,
                DailyStep.ARENA_REWARD
            )
            if (legacySteps.isNotEmpty()) {
                add(DailyPipelineTask(accountId, daily.copy(enabledSteps = legacySteps)))
            }
        }
        configs.dailyDonate?.takeIf { it.enabled }?.let { add(DailyDonateTask(accountId, it)) }
        configs.dailySalary?.takeIf { it.enabled }?.let { add(DailySalaryTask(accountId, it)) }
        configs.dailyNationalCollect?.takeIf { it.enabled }?.let { add(DailyNationalCollectTask(accountId, it)) }
        configs.dailyCityLordCollect?.takeIf { it.enabled }?.let { add(DailyCityLordCollectTask(accountId, it)) }
        configs.dailyGeneralVisit?.takeIf { it.enabled }?.let { add(DailyGeneralVisitTask(accountId, it)) }
        configs.general?.takeIf {
            it.autoHeal || it.keepFullLoyalty || it.autoEnergy || it.autoRescue
        }?.let { add(GeneralMaintenanceTask(accountId, it)) }
        configs.foodToCopper?.takeIf { it.enabled }
            ?.let { add(FoodToCopperTask(accountId, it)) }
        configs.internalAffairs?.takeIf { it.enabled || it.upgradeTechnology }
            ?.let { add(InternalAffairsTask(accountId, it)) }
        configs.dungeon?.takeIf { it.enabled }?.let { add(DungeonTask(accountId, it)) }
        configs.inventory?.takeIf { it.enabled }?.let { add(InventoryCleanupTask(accountId, it)) }
        configs.autoLoot?.takeIf { it.enabled }?.let { add(AutoLootTask(accountId, it)) }
        configs.sixMinistries
            ?.takeIf { it.cropEnabled && it.crop == MinistryProtocolCrop.VERIFIED_NAME }
            ?.let { add(SixMinistriesTask(accountId, it)) }
        // 心跳只证明会话在线；电脑端另有定时的角色/将领/军情刷新。
        // 手机端同样保留一条独立观察通道，它不与每日、内政或背包互相抑制。
        add(StateRefreshTask(accountId))
        configs.alarm?.takeIf {
            it.enabled && (it.incomingEnabled || it.militaryEnabled)
        }?.let { add(AlarmTask(accountId, it)) }
    }, schedulerContract)
}

data class AssistantConfigBundle(
    val guaji: GuajiConfig? = null,
    val shuaHuang: ShuaHuangConfig? = null,
    val mine: MineConfig? = null,
    val daily: DailyConfig? = null,
    val dailyDonate: DailyDonateConfig? = null,
    val dailySalary: DailySalaryConfig? = null,
    val dailyNationalCollect: DailyNationalCollectConfig? = null,
    val dailyCityLordCollect: DailyCityLordCollectConfig? = null,
    val dailyGeneralVisit: DailyGeneralVisitConfig? = null,
    val general: GeneralConfig? = null,
    val foodToCopper: FoodToCopperConfig? = null,
    val formations: List<FormationConfig> = emptyList(),
    val internalAffairs: InternalAffairsConfig? = null,
    val dungeon: DungeonConfig? = null,
    val lossless: LosslessConfig? = null,
    val inventory: InventoryConfig? = null,
    val autoLoot: AutoLootConfig? = null,
    val sixMinistries: SixMinistriesConfig? = null,
    val alarm: AlarmConfig? = null
)
