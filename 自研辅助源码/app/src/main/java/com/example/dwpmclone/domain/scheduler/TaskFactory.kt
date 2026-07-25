package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.AssistantTask

/** Builds local scheduling tasks from configuration models; tasks must not execute production mutations. */
object TaskFactory {
    fun buildBackgroundTaskSet(accountId: Long, configs: AssistantConfigBundle): List<AssistantTask<*>> = buildList {
        // 用户保存“将领A + 200轻骑兵 + 刷黄5203”后，首轮刷黄前必须先让配兵任务
        // 有机会执行；否则 ShuaHuangTask 会先搜索/出征，表现为“保存后没有按设定兵力执行”。
        configs.formations.forEach { add(FormationUpdateMockTask(accountId, it)) }
        // Desktop command-center priority: lossless > brush-yellow > dungeon.
        configs.lossless?.let { add(LosslessTask(accountId, it)) }
        configs.shuaHuang?.let { add(ShuaHuangTask(accountId, it)) }
        configs.mine?.let { add(MineSearchMockTask(accountId, it)) }
        configs.daily?.takeIf { it.enabledSteps.isNotEmpty() }?.let { add(DailyPipelineTask(accountId, it)) }
        configs.dailyDonate?.takeIf { it.enabled }?.let { add(DailyDonateTask(accountId, it)) }
        configs.dailySalary?.takeIf { it.enabled }?.let { add(DailySalaryTask(accountId, it)) }
        configs.dailyNationalCollect?.takeIf { it.enabled }?.let { add(DailyNationalCollectTask(accountId, it)) }
        configs.dailyCityLordCollect?.takeIf { it.enabled }?.let { add(DailyCityLordCollectTask(accountId, it)) }
        configs.dailyGeneralVisit?.takeIf { it.enabled }?.let { add(DailyGeneralVisitTask(accountId, it)) }
        configs.general?.let { add(GeneralMaintenanceMockTask(accountId, it)) }
        configs.internalAffairs?.let { add(InternalAffairsMockTask(accountId, it)) }
        configs.sixMinistries?.let { add(SixMinistriesTask(accountId, it)) }
        configs.dungeon?.let { add(DungeonMockTask(accountId, it)) }
        configs.inventory?.let { add(InventoryCleanupMockTask(accountId, it)) }
        configs.vip?.let { add(VipFeatureMockTask(accountId, it)) }
        configs.surrenderRelease?.let { add(SurrenderReleaseMockTask(accountId, it)) }
        configs.resourcePointSendGeneral?.let { add(ResourcePointSendGeneralMockTask(accountId, it)) }
        configs.autoLoot?.let { add(AutoLootMockTask(accountId, it)) }
        configs.alarmWithdraw?.let { add(AlarmWithdrawMockTask(accountId, it)) }
        configs.bulkTools?.let { add(BulkToolsMockTask(accountId, it)) }
    }
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
    val formations: List<FormationConfig> = emptyList(),
    val internalAffairs: InternalAffairsConfig? = null,
    val sixMinistries: SixMinistriesConfig? = null,
    val dungeon: DungeonConfig? = null,
    val lossless: LosslessConfig? = null,
    val inventory: InventoryConfig? = null,
    val vip: VipFeatureConfig? = null,
    val surrenderRelease: SurrenderReleaseConfig? = null,
    val resourcePointSendGeneral: ResourcePointSendGeneralConfig? = null,
    val autoLoot: AutoLootConfig? = null,
    val alarmWithdraw: AlarmWithdrawConfig? = null,
    val bulkTools: BulkToolConfig? = null
)
