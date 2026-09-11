package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.*

/** Task sequencing only; protocol encoding, transport and action safety stay behind GameProtocolClient. */
abstract class BaseAssistantTask<Cfg>(
    override val accountId: Long,
    override val type: TaskType,
    override val config: Cfg
) : AssistantTask<Cfg> {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        return when (val state = ctx.protocol.validateSession(ctx.session)) {
            is ProtocolResult.Ok -> {
                if (state.value.valid) {
                    ctx.runtime.commandGate.beforeTask(ctx.session.accountId, type).asDecision()
                } else {
                    ctx.runtime.commandGate.markSessionExpired(ctx.session.accountId)
                    TaskDecision.NeedRelogin(state.value.reason ?: "session invalid")
                }
            }
            is ProtocolResult.Err -> if (state.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(state.message)
        }
    }

    override suspend fun recover(ctx: TaskContext, error: Throwable): TaskDecision =
        TaskDecision.RetryAfter(DEFAULT_RETRY_MS)

    override suspend fun stop(ctx: TaskContext, reason: String) = Unit

    protected fun ProtocolResult<*>.asDecision(success: TaskDecision = TaskDecision.Continue): TaskDecision = when (this) {
        is ProtocolResult.Ok -> success
        is ProtocolResult.Err -> if (retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(message)
    }

    /**
     * Converts an action response only after the server has explicitly confirmed success.
     *
     * Do not use the generic [asDecision] converter for ProtocolResult<StepResult>: an Ok
     * transport envelope may still contain a rejected game action (`success=false`).
     */
    protected fun ProtocolResult<StepResult>.asConfirmedStepDecision(
        success: TaskDecision = TaskDecision.Continue,
        emptyFailureMessage: String = "服务器未确认动作成功"
    ): TaskDecision = when (this) {
        is ProtocolResult.Ok -> if (value.success) {
            success
        } else {
            TaskDecision.Stop(value.message.ifBlank { emptyFailureMessage })
        }
        is ProtocolResult.Err -> if (retryable) {
            TaskDecision.RetryAfter(DEFAULT_RETRY_MS)
        } else {
            TaskDecision.Stop(message)
        }
    }

    companion object {
        const val DEFAULT_RETRY_MS: Long = 10_000
    }
}

class DailyPipelineTask(accountId: Long, config: DailyConfig) :
    BaseAssistantTask<DailyConfig>(accountId, TaskType.DAILY, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision = sharedOwnerStop("日常")

    override suspend fun step(ctx: TaskContext): TaskDecision = sharedOwnerStop("日常")
}

/**
 * Configuration marker only. Shared Python owns validation, target search,
 * dispatch, recovery, counters and scheduling for production brush-yellow.
 */
class ShuaHuangTask(accountId: Long, config: ShuaHuangConfig) :
    BaseAssistantTask<ShuaHuangConfig>(accountId, TaskType.SHUA_HUANG, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision = sharedOwnerStop("刷黄")

    override suspend fun step(ctx: TaskContext): TaskDecision = sharedOwnerStop("刷黄")
}

/**
 * Configuration marker only. Shared Python owns read-only mine search,
 * dispatch, garrison recovery, withdrawal and scheduling.
 */
class MineTask(accountId: Long, config: MineConfig) :
    BaseAssistantTask<MineConfig>(
        accountId,
        if (config.backgroundSearch) TaskType.MINE_SEARCH else TaskType.AUTO_MINING,
        config,
    ) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision =
        sharedOwnerStop(if (config.backgroundSearch) "找矿" else "打矿")

    override suspend fun step(ctx: TaskContext): TaskDecision =
        sharedOwnerStop(if (config.backgroundSearch) "找矿" else "打矿")
}

class InventoryCleanupTask(accountId: Long, config: InventoryConfig) :
    BaseAssistantTask<InventoryConfig>(accountId, TaskType.INVENTORY, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision =
        sharedOwnerStop("背包整理")

    override suspend fun step(ctx: TaskContext): TaskDecision =
        sharedOwnerStop("背包整理")
}

class GeneralMaintenanceTask(accountId: Long, config: GeneralConfig) :
    BaseAssistantTask<GeneralConfig>(accountId, TaskType.GENERAL, config) {
    override suspend fun step(ctx: TaskContext): TaskDecision {
        val generals = when (val result = ctx.protocol.queryGenerals(ctx.session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
        }
        if (config.autoHeal) {
            val representatives = generals
                .filter { it.placeId != null }
                .distinctBy { it.placeId }
                .ifEmpty { generals.firstOrNull()?.let(::listOf).orEmpty() }
            for (representative in representatives) {
                val actionResult = ctx.protocol.healGeneral(ctx.session, representative.id)
                val decision = actionResult.asConfirmedStepDecision(emptyFailureMessage = "服务器未确认治疗成功")
                if (decision is TaskDecision.Stop || decision is TaskDecision.RetryAfter) return decision
                val healStep = (actionResult as? ProtocolResult.Ok)?.value
                if (healStep?.raw?.containsKey("skipped") != true) {
                    ctx.recordSuccess(
                        "治疗",
                        "${representative.name.ifBlank { representative.id.toString() }} 全部伤兵"
                    )
                }
            }
        }
        for (general in generals) {
            // The game rejects ordinary expeditions at exactly 20 stamina (requires >20).
            // Preserve the configured "below threshold" rule above that hard boundary.
            if (config.autoEnergy && general.energy != null &&
                (general.energy <= 20 || general.energy < config.minEnergy)
            ) {
                val actionResult = ctx.protocol.addEnergy(ctx.session, general.id)
                val decision = actionResult.asConfirmedStepDecision(emptyFailureMessage = "服务器未确认加体成功")
                if (decision is TaskDecision.Stop || decision is TaskDecision.RetryAfter) return decision
                if ((actionResult as? ProtocolResult.Ok)?.value?.raw?.get("phase") != "waiting-general") {
                    ctx.recordSuccess("加体", "${general.name}使用1枚活血丹")
                }
            }
            if (config.keepFullLoyalty && general.loyalty != null && general.loyalty < 100) {
                val decision = ctx.protocol.addLoyalty(
                    ctx.session,
                    general.id,
                    100 - general.loyalty
                )
                    .asConfirmedStepDecision(emptyFailureMessage = "服务器未确认加忠成功")
                if (decision is TaskDecision.Stop || decision is TaskDecision.RetryAfter) return decision
            }
        }
        return TaskDecision.Sleep(10 * 60 * 1000L)
    }
}

class InternalAffairsTask(accountId: Long, config: InternalAffairsConfig) :
    BaseAssistantTask<InternalAffairsConfig>(accountId, TaskType.INTERNAL, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled && !config.upgradeTechnology) {
            return TaskDecision.Stop("internal affairs and technology upgrade disabled")
        }
        if (config.upgradeTechnology && config.technologyIds.isEmpty()) {
            return TaskDecision.Stop("technology upgrade enabled without selected technology")
        }
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision =
        when (val result = ctx.protocol.runInternalAffairs(ctx.session, config)) {
            is ProtocolResult.Ok -> {
                val actionKind = result.value.raw["actionKind"]
                val continueFillingQueues =
                    result.value.raw["actionSubmitted"].equals("true", ignoreCase = true) &&
                        (actionKind == "building" ||
                            (actionKind == "technology" && config.enabled))
                val nextDelay = if (continueFillingQueues) {
                    INTERNAL_QUEUE_FILL_DELAY_MS
                } else {
                    result.value.raw["nextDelayMillis"]?.toLongOrNull()
                        ?.coerceIn(10L * 60L * 1_000L, 60L * 60L * 1_000L)
                        ?: 10L * 60L * 1_000L
                }
                if (result.value.success) {
                    if (result.value.raw["actionSubmitted"].equals("true", ignoreCase = true)) {
                        ctx.recordSuccess(
                            if (actionKind == "technology") "科技" else "内政",
                            result.value.message
                        )
                    }
                    TaskDecision.Sleep(nextDelay)
                } else {
                    ctx.prompt(type, "内政本轮未完成：${result.value.message}")
                    TaskDecision.RetryAfter(nextDelay)
                }
            }
            is ProtocolResult.Err -> if (result.retryable) {
                TaskDecision.RetryAfter(DEFAULT_RETRY_MS)
            } else {
                TaskDecision.Stop(result.message)
            }
        }

    private companion object {
        const val INTERNAL_QUEUE_FILL_DELAY_MS: Long = 1_000L
    }
}

class DungeonTask(accountId: Long, config: DungeonConfig) :
    BaseAssistantTask<DungeonConfig>(accountId, TaskType.DUNGEON, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision = sharedOwnerStop("副本")

    override suspend fun step(ctx: TaskContext): TaskDecision = sharedOwnerStop("副本")
}

class LosslessTask(accountId: Long, config: LosslessConfig) :
    BaseAssistantTask<LosslessConfig>(accountId, TaskType.LOSSLESS, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision = sharedOwnerStop("无损")

    override suspend fun step(ctx: TaskContext): TaskDecision = sharedOwnerStop("无损")
}

class AutoLootTask(accountId: Long, config: AutoLootConfig) :
    BaseAssistantTask<AutoLootConfig>(accountId, TaskType.AUTO_LOOT, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision = sharedOwnerStop("掠夺")

    override suspend fun step(ctx: TaskContext): TaskDecision = sharedOwnerStop("掠夺")
}

class SixMinistriesTask(accountId: Long, config: SixMinistriesConfig) :
    BaseAssistantTask<SixMinistriesConfig>(accountId, TaskType.SIX_MINISTRIES, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision = sharedOwnerStop("六部")

    override suspend fun step(ctx: TaskContext): TaskDecision = sharedOwnerStop("六部")
}

private fun sharedOwnerStop(feature: String): TaskDecision =
    TaskDecision.Stop("$feature 已由共享 Python 常驻核心执行，Kotlin 任务不得发包")

class AlarmTask(accountId: Long, config: AlarmConfig) :
    BaseAssistantTask<AlarmConfig>(accountId, TaskType.ALARM, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision =
        sharedOwnerStop("军情警报")

    override suspend fun step(ctx: TaskContext): TaskDecision =
        sharedOwnerStop("军情警报")
}
