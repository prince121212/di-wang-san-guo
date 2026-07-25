package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.model.DailyCityLordCollectConfig
import com.example.dwpmclone.domain.model.DailyDonateConfig
import com.example.dwpmclone.domain.model.DailyGeneralVisitConfig
import com.example.dwpmclone.domain.model.DailyNationalCollectConfig
import com.example.dwpmclone.domain.model.DailySalaryConfig
import com.example.dwpmclone.domain.model.DailyStep
import com.example.dwpmclone.domain.protocol.AssistantTask
import com.example.dwpmclone.domain.protocol.GeneralVisitCandidate
import com.example.dwpmclone.domain.protocol.NationalCity
import com.example.dwpmclone.domain.protocol.NationalCityKind
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.protocol.LootTargetFief
import com.example.dwpmclone.domain.protocol.StepResult

private const val DAILY_FEATURE_SLEEP_MS: Long = 24L * 60L * 60L * 1000L
private const val DAILY_FEATURE_ERROR_SLEEP_MS: Long = 60L * 1000L
private const val MAX_NATIONAL_COLLECTION_ATTEMPTS: Int = 20

/**
 * Daily features deliberately never return a business-error Stop decision.  Stop is
 * account/task lifecycle control in the existing scheduler; using it for a rejected
 * donation or an unavailable city would incorrectly affect sibling tasks.
 */
abstract class DailyFeatureTask<Cfg>(
    override val accountId: Long,
    override val type: TaskType,
    override val config: Cfg
) : AssistantTask<Cfg> {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        return when (val result = ctx.protocol.validateSession(ctx.session)) {
            is ProtocolResult.Ok -> {
                if (!result.value.valid) {
                    ctx.runtime.commandGate.markSessionExpired(ctx.session.accountId)
                    TaskDecision.NeedRelogin(result.value.reason ?: "会话已失效")
                } else {
                    ctx.runtime.commandGate.beforeTask(ctx.session.accountId, type).asDailyDecision(ctx)
                }
            }
            is ProtocolResult.Err -> protocolErrorDecision(ctx, "会话检查", result)
        }
    }

    override suspend fun recover(ctx: TaskContext, error: Throwable): TaskDecision {
        val message = error.message ?: error::class.java.simpleName
        ctx.prompt(type, "任务异常：$message")
        return TaskDecision.Sleep(DAILY_FEATURE_ERROR_SLEEP_MS)
    }

    override suspend fun stop(ctx: TaskContext, reason: String) = Unit

    protected fun protocolErrorDecision(
        ctx: TaskContext,
        action: String,
        error: ProtocolResult.Err
    ): TaskDecision {
        if (error.looksLikeSessionInvalid()) {
            ctx.runtime.commandGate.markSessionExpired(ctx.session.accountId)
            return TaskDecision.NeedRelogin("$action：${error.message}")
        }
        ctx.prompt(type, "${action}失败：${error.message}")
        return TaskDecision.Sleep(if (error.retryable) DAILY_FEATURE_ERROR_SLEEP_MS else DAILY_FEATURE_SLEEP_MS)
    }

    protected fun stepFailure(ctx: TaskContext, action: String, result: StepResult) {
        ctx.prompt(type, "${action}失败：${result.message.ifBlank { "服务器未确认成功" }}")
    }

    protected fun stepSuccess(ctx: TaskContext, action: String, result: StepResult) {
        if (result.message.isNotBlank()) {
            ctx.prompt(type, "$action：${result.message}")
        }
    }

    private fun ProtocolResult.Err.looksLikeSessionInvalid(): Boolean {
        val codeText = code.uppercase()
        val messageText = message.lowercase()
        return codeText.contains("SESSION") ||
            codeText.contains("LOGIN") ||
            codeText.contains("TOKEN") ||
            codeText.contains("AUTH") ||
            messageText.contains("会话失效") ||
            messageText.contains("登录过期") ||
            messageText.contains("token expired") ||
            messageText.contains("session expired")
    }

    private fun com.example.dwpmclone.domain.state.GateResult.asDailyDecision(ctx: TaskContext): TaskDecision = when (this) {
        is com.example.dwpmclone.domain.state.GateResult.Allowed -> TaskDecision.Continue
        is com.example.dwpmclone.domain.state.GateResult.Blocked -> {
            ctx.prompt(type, "任务暂不可执行：$reason")
            TaskDecision.Sleep(retryAfterMillis)
        }
    }
}

class DailyDonateTask(
    accountId: Long,
    config: DailyDonateConfig
) : DailyFeatureTask<DailyDonateConfig>(accountId, TaskType.DAILY_DONATE, config) {
    override suspend fun step(ctx: TaskContext): TaskDecision {
        val steps = listOf(
            DailyStep.DONATE_COPPER to "铜钱捐献",
            DailyStep.DONATE_FOOD to "粮食捐献",
            DailyStep.DONATE_TECH to "科技积分捐献"
        )
        var failures = 0
        for ((dailyStep, label) in steps) {
            when (val result = ctx.protocol.runDailyStep(ctx.session, dailyStep)) {
                is ProtocolResult.Ok -> {
                    if (result.value.success) {
                        stepSuccess(ctx, label, result.value)
                    } else {
                        failures++
                        stepFailure(ctx, label, result.value)
                    }
                }
                is ProtocolResult.Err -> {
                    if (result.looksLikeSessionInvalid()) {
                        ctx.runtime.commandGate.markSessionExpired(ctx.session.accountId)
                        return TaskDecision.NeedRelogin("$label：${result.message}")
                    }
                    failures++
                    ctx.prompt(type, "${label}失败：${result.message}")
                }
            }
        }
        if (failures == steps.size) {
            ctx.prompt(type, "本次三项捐献均未完成")
        }
        return TaskDecision.Sleep(DAILY_FEATURE_SLEEP_MS)
    }
}

class DailySalaryTask(
    accountId: Long,
    config: DailySalaryConfig
) : DailyFeatureTask<DailySalaryConfig>(accountId, TaskType.DAILY_SALARY, config) {
    override suspend fun step(ctx: TaskContext): TaskDecision {
        return when (val result = ctx.protocol.runDailyStep(ctx.session, DailyStep.SALARY)) {
            is ProtocolResult.Ok -> {
                if (result.value.success) {
                    stepSuccess(ctx, "国家俸禄", result.value)
                } else {
                    stepFailure(ctx, "国家俸禄", result.value)
                }
                TaskDecision.Sleep(DAILY_FEATURE_SLEEP_MS)
            }
            is ProtocolResult.Err -> protocolErrorDecision(ctx, "国家俸禄", result)
        }
    }
}

class DailyNationalCollectTask(
    accountId: Long,
    config: DailyNationalCollectConfig
) : DailyFeatureTask<DailyNationalCollectConfig>(accountId, TaskType.DAILY_NATIONAL_COLLECT, config) {
    override suspend fun step(ctx: TaskContext): TaskDecision {
        val categories = listOf(
            NationalCityKind.STATE,
            NationalCityKind.COMMANDERY,
            NationalCityKind.COUNTY
        )

        /*
         * Query every useful hierarchy in deterministic order.  The protocol
         * client itself refuses SMALL/UNKNOWN, and this second filter protects
         * the task from a malformed/broad response accidentally reintroducing
         * small cities into the action set.
         */
        val candidatesByName = linkedMapOf<String, NationalCity>()
        for (kind in categories) {
            val cities = when (val result = ctx.protocol.queryNationalCities(ctx.session, kind)) {
                is ProtocolResult.Ok -> result.value
                is ProtocolResult.Err -> {
                    if (result.looksLikeSessionInvalid()) {
                        ctx.runtime.commandGate.markSessionExpired(ctx.session.accountId)
                        return TaskDecision.NeedRelogin("查询${kind.label()}失败：${result.message}")
                    }
                    ctx.prompt(type, "查询${kind.label()}失败：${result.message}")
                    emptyList()
                }
            }
            for (city in cities) {
                val normalizedKind = city.normalizedKind()
                if (city.name.isBlank() || normalizedKind !in categories) continue
                candidatesByName.putIfAbsent(
                    city.name.trim(),
                    if (city.kind == normalizedKind) city else city.copy(kind = normalizedKind)
                )
            }
        }

        if (candidatesByName.isEmpty()) {
            ctx.prompt(type, "没有可执行的国家征收城池")
            return TaskDecision.Sleep(DAILY_FEATURE_SLEEP_MS)
        }

        val attemptedCities = linkedSetOf<String>()
        var successfulCount = 0
        var inspectedStatusCount = 0
        val actionLimit = if (config.maxAttempts > 0) {
            config.maxAttempts.coerceAtMost(MAX_NATIONAL_COLLECTION_ATTEMPTS)
        } else {
            MAX_NATIONAL_COLLECTION_ATTEMPTS
        }

        /*
         * A national officer may have several collection attempts per day.
         * Re-rank before every action so a successful collection (which resets
         * that city's accumulated resources) cannot make us spend a later
         * attempt on a stale value.  A city is attempted at most once in this
         * run; after collection its amount is expected to reset to zero.
         */
        while (successfulCount < actionLimit) {
            val ranked = mutableListOf<RankedNationalCity>()
            var sawQuotaExhausted = false
            for (city in candidatesByName.values) {
                if (city.name in attemptedCities) continue
                when (val result = ctx.protocol.queryNationalCollectStatus(ctx.session, city)) {
                    is ProtocolResult.Ok -> {
                        inspectedStatusCount++
                        if (result.value.quotaExhausted) sawQuotaExhausted = true
                        if (result.value.canCollect) {
                            ranked += RankedNationalCity(city, result.value.currentCopper)
                        }
                    }
                    is ProtocolResult.Err -> {
                        if (result.looksLikeSessionInvalid()) {
                            ctx.runtime.commandGate.markSessionExpired(ctx.session.accountId)
                            return TaskDecision.NeedRelogin("查询${city.name}征收金额失败：${result.message}")
                        }
                        // A city-specific query failure must not suppress the
                        // other candidates or sibling daily tasks.
                        ctx.prompt(type, "查询${city.name}征收金额失败：${result.message}")
                    }
                }
            }

            val candidate = ranked.maxWithOrNull(
                compareBy<RankedNationalCity> { it.copper }
                    .thenByDescending { it.city.kind.priority * -1 }
                    .thenByDescending { it.city.name }
            )
            if (candidate == null) {
                if (sawQuotaExhausted || attemptedCities.size >= candidatesByName.size) {
                    ctx.prompt(type, "国家征收次数已用尽或没有可征收城池")
                } else {
                    ctx.prompt(type, "没有可执行的国家征收城池")
                }
                break
            }

            attemptedCities += candidate.city.name
            when (val result = ctx.protocol.collectNationalCity(ctx.session, candidate.city)) {
                is ProtocolResult.Ok -> {
                    if (result.value.success) {
                        successfulCount++
                        stepSuccess(
                            ctx,
                            "国家征收${candidate.city.name}（可得${candidate.copper}铜钱，第${successfulCount}次）",
                            result.value
                        )
                    } else {
                        // Rejected business responses are safe to fall through
                        // to the next-ranked city.
                        stepFailure(ctx, "国家征收${candidate.city.name}", result.value)
                    }
                }
                is ProtocolResult.Err -> {
                    if (result.looksLikeSessionInvalid()) {
                        ctx.runtime.commandGate.markSessionExpired(ctx.session.accountId)
                        return TaskDecision.NeedRelogin("国家征收${candidate.city.name}：${result.message}")
                    }
                    // This action targets only the current city.  Report it and
                    // continue looking for another eligible city; no sibling
                    // task is stopped by the failure.
                    ctx.prompt(type, "国家征收${candidate.city.name}失败：${result.message}")
                }
            }
        }

        if (successfulCount > 0) {
            ctx.prompt(
                type,
                "国家征收完成：成功${successfulCount}次，检查${inspectedStatusCount}次城池状态，跳过小城"
            )
        }
        return TaskDecision.Sleep(DAILY_FEATURE_SLEEP_MS)
    }

    private data class RankedNationalCity(val city: NationalCity, val copper: Long)
}

private fun NationalCity.normalizedKind(): NationalCityKind =
    kind.takeUnless { it == NationalCityKind.UNKNOWN }
        ?: NationalCityKind.fromListCategory(listCategory)

class DailyCityLordCollectTask(
    accountId: Long,
    config: DailyCityLordCollectConfig
) : DailyFeatureTask<DailyCityLordCollectConfig>(accountId, TaskType.DAILY_CITY_LORD_COLLECT, config) {
    override suspend fun step(ctx: TaskContext): TaskDecision {
        val fiefs = when (val result = ctx.protocol.queryOwnedFiefs(ctx.session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return protocolErrorDecision(ctx, "查询自有城池", result)
        }
        val cities = fiefs
            .filter { it.cityName.isNotBlank() }
            .distinctBy { it.cityName }
        if (cities.isEmpty()) {
            ctx.prompt(type, "没有查询到可执行城主征收的自有城池")
            return TaskDecision.Sleep(DAILY_FEATURE_SLEEP_MS)
        }
        for (fief in cities) {
            when (val result = ctx.protocol.collectCityLord(ctx.session, fief)) {
                is ProtocolResult.Ok -> {
                    if (result.value.success) {
                        stepSuccess(ctx, "城主征收${fief.cityName}", result.value)
                    } else {
                        stepFailure(ctx, "城主征收${fief.cityName}", result.value)
                    }
                }
                is ProtocolResult.Err -> {
                    if (result.looksLikeSessionInvalid()) {
                        ctx.runtime.commandGate.markSessionExpired(ctx.session.accountId)
                        return TaskDecision.NeedRelogin("城主征收${fief.cityName}：${result.message}")
                    }
                    ctx.prompt(type, "城主征收${fief.cityName}失败：${result.message}")
                }
            }
        }
        return TaskDecision.Sleep(DAILY_FEATURE_SLEEP_MS)
    }
}

class DailyGeneralVisitTask(
    accountId: Long,
    config: DailyGeneralVisitConfig
) : DailyFeatureTask<DailyGeneralVisitConfig>(accountId, TaskType.DAILY_GENERAL_VISIT, config) {
    override suspend fun step(ctx: TaskContext): TaskDecision {
        val orderedIds = config.selectedIds
        if (orderedIds.isEmpty()) {
            ctx.prompt(type, "名将拜访未选择将领")
            return TaskDecision.Sleep(DAILY_FEATURE_SLEEP_MS)
        }
        val candidates = when (val result = ctx.protocol.queryVisitGenerals(ctx.session)) {
            is ProtocolResult.Ok -> result.value.associateBy { it.id }
            is ProtocolResult.Err -> return protocolErrorDecision(ctx, "查询可拜访名将", result)
        }
        var attempted = 0
        for (id in orderedIds) {
            val candidate = candidates[id]
            if (candidate == null) {
                ctx.prompt(type, "名将ID=$id 已不在当前可拜访列表，顺延下一名")
                continue
            }
            if (candidate.captiveState != 0) {
                ctx.prompt(type, "名将${candidate.name}当前不可拜访，顺延下一名")
                continue
            }
            attempted++
            when (val result = ctx.protocol.visitGeneral(ctx.session, candidate)) {
                is ProtocolResult.Ok -> {
                    if (result.value.success) {
                        stepSuccess(ctx, "名将拜访成功：${candidate.name}", result.value)
                        return TaskDecision.Sleep(DAILY_FEATURE_SLEEP_MS)
                    }
                    stepFailure(ctx, "拜访${candidate.name}", result.value)
                }
                is ProtocolResult.Err -> {
                    if (result.looksLikeSessionInvalid()) {
                        ctx.runtime.commandGate.markSessionExpired(ctx.session.accountId)
                        return TaskDecision.NeedRelogin("拜访${candidate.name}：${result.message}")
                    }
                    ctx.prompt(type, "拜访${candidate.name}失败，顺延下一名：${result.message}")
                }
            }
        }
        ctx.prompt(type, if (attempted == 0) "没有可尝试拜访的已选名将" else "已按优先级尝试，未有名将拜访成功")
        return TaskDecision.Sleep(DAILY_FEATURE_SLEEP_MS)
    }
}

private fun NationalCityKind.label(): String = when (this) {
    NationalCityKind.STATE -> "州城"
    NationalCityKind.COMMANDERY -> "郡城"
    NationalCityKind.COUNTY -> "县城"
    NationalCityKind.SMALL -> "小城"
    NationalCityKind.UNKNOWN -> "未知城池"
}

private fun ProtocolResult.Err.looksLikeSessionInvalid(): Boolean {
    val codeText = code.uppercase()
    val messageText = message.lowercase()
    return codeText.contains("SESSION") ||
        codeText.contains("LOGIN") ||
        codeText.contains("TOKEN") ||
        codeText.contains("AUTH") ||
        messageText.contains("会话失效") ||
        messageText.contains("登录过期") ||
        messageText.contains("token expired") ||
        messageText.contains("session expired")
}
