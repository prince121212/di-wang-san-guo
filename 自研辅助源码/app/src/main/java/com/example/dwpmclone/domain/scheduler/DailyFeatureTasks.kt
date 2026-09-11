package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.model.DailyCityLordCollectConfig
import com.example.dwpmclone.domain.model.DailyDonateConfig
import com.example.dwpmclone.domain.model.DailyGeneralVisitConfig
import com.example.dwpmclone.domain.model.DailyNationalCollectConfig
import com.example.dwpmclone.domain.model.DailySalaryConfig
import com.example.dwpmclone.domain.model.DailyStep
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType

private val DAILY_FEATURE_TASK_TYPES = mapOf(
    DailyStep.SIGN_IN to TaskType.DAILY_SIGN_IN,
    DailyStep.ARENA_REWARD to TaskType.DAILY_ARENA_COINS
)

/**
 * Configuration marker retained while SavedConfigTaskPlan exposes task-shaped metadata.
 * Production Service filters these task types and the shared Python resident tick owns
 * all daily selection, completion cycles, packets and receipts.
 */
abstract class SharedDailyTask<Cfg>(
    accountId: Long,
    type: TaskType,
    config: Cfg
) : BaseAssistantTask<Cfg>(accountId, type, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision = sharedDailyOwnerStop()

    override suspend fun step(ctx: TaskContext): TaskDecision = sharedDailyOwnerStop()

    private fun sharedDailyOwnerStop(): TaskDecision =
        TaskDecision.Stop("日常已由共享 Python 常驻核心执行，Kotlin 任务不得发包")
}

class DailySingleStepTask(
    accountId: Long,
    val dailyStep: DailyStep
) : SharedDailyTask<DailyStep>(
    accountId,
    DAILY_FEATURE_TASK_TYPES[dailyStep]
        ?: error("unsupported independent daily step: $dailyStep"),
    dailyStep
)

class DailyDonateTask(
    accountId: Long,
    config: DailyDonateConfig
) : SharedDailyTask<DailyDonateConfig>(accountId, TaskType.DAILY_DONATE, config)

class DailySalaryTask(
    accountId: Long,
    config: DailySalaryConfig
) : SharedDailyTask<DailySalaryConfig>(accountId, TaskType.DAILY_SALARY, config)

class DailyNationalCollectTask(
    accountId: Long,
    config: DailyNationalCollectConfig
) : SharedDailyTask<DailyNationalCollectConfig>(
    accountId,
    TaskType.DAILY_NATIONAL_COLLECT,
    config
)

class DailyCityLordCollectTask(
    accountId: Long,
    config: DailyCityLordCollectConfig
) : SharedDailyTask<DailyCityLordCollectConfig>(
    accountId,
    TaskType.DAILY_CITY_LORD_COLLECT,
    config
)

class DailyGeneralVisitTask(
    accountId: Long,
    config: DailyGeneralVisitConfig
) : SharedDailyTask<DailyGeneralVisitConfig>(
    accountId,
    TaskType.DAILY_GENERAL_VISIT,
    config
)
