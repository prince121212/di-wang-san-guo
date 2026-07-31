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
import com.example.dwpmclone.domain.protocol.NationalCitizenDailyPolicy
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.protocol.LootTargetFief
import com.example.dwpmclone.domain.protocol.StepResult

private const val MAX_NATIONAL_COLLECTION_ATTEMPTS: Int = 20

private val DAILY_FEATURE_TASK_TYPES = mapOf(
    DailyStep.SIGN_IN to TaskType.DAILY_SIGN_IN,
    DailyStep.ARENA_REWARD to TaskType.DAILY_ARENA_COINS
)

private val DAILY_FEATURE_KEYS = mapOf(
    DailyStep.SIGN_IN to "autoSignIn",
    DailyStep.ARENA_REWARD to "arenaCoins"
)

private val DAILY_FEATURE_LABELS = mapOf(
    DailyStep.SIGN_IN to "自动签到",
    DailyStep.ARENA_REWARD to "领竞技币"
)

private val DAILY_FEATURE_SUCCESS_CATEGORIES = mapOf(
    DailyStep.SIGN_IN to "签到",
    DailyStep.ARENA_REWARD to "领币"
)

/**
 * Daily features deliberately never return a business-error Stop decision.  Stop is
 * account/task lifecycle control in the existing scheduler; using it for a rejected
 * donation or an unavailable city would incorrectly affect sibling tasks.
 */
abstract class DailyFeatureTask<Cfg>(
    override val accountId: Long,
    override val type: TaskType,
    override val config: Cfg,
    private val completionKey: String? = null
) : AssistantTask<Cfg> {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        return when (val result = ctx.protocol.validateSession(ctx.session)) {
            is ProtocolResult.Ok -> {
                if (!result.value.valid) {
                    ctx.runtime.commandGate.markSessionExpired(ctx.session.accountId)
                    TaskDecision.NeedRelogin(result.value.reason ?: "会话已失效")
                } else {
                    val gateDecision = ctx.runtime.commandGate.beforeTask(ctx.session.accountId, type).asDailyDecision(ctx)
                    if (gateDecision != TaskDecision.Continue) {
                        gateDecision
                    } else if (completionKey != null &&
                        ctx.dailyCompletions.isCompleted(ctx.session.accountId, completionKey, ctx.nowMillis)
                    ) {
                        TaskDecision.Sleep(millisUntilNextChinaDay(ctx.nowMillis, ctx.behaviorContract.timezoneId))
                    } else {
                        TaskDecision.Continue
                    }
                }
            }
            is ProtocolResult.Err -> protocolErrorDecision(ctx, "会话检查", result)
        }
    }

    override suspend fun recover(ctx: TaskContext, error: Throwable): TaskDecision {
        val message = error.message ?: error::class.java.simpleName
        ctx.prompt(type, "任务异常：$message")
        return TaskDecision.Sleep(ctx.behaviorContract.dailySchedule.failedFeatureRetryMillis)
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
        return TaskDecision.Sleep(ctx.behaviorContract.dailySchedule.failedFeatureRetryMillis)
    }

    protected fun stepFailure(ctx: TaskContext, action: String, result: StepResult) {
        ctx.prompt(type, "${action}失败：${result.message.ifBlank { "服务器未确认成功" }}")
    }

    protected fun stepSuccess(ctx: TaskContext, action: String, result: StepResult) {
        if (result.message.isNotBlank()) {
            ctx.prompt(type, "$action：${result.message}")
        }
    }

    protected fun markDailyCompleted(ctx: TaskContext, key: String = requireNotNull(completionKey)) {
        ctx.dailyCompletions.markCompleted(ctx.session.accountId, key, ctx.nowMillis)
    }

    protected fun nextChinaDay(ctx: TaskContext): TaskDecision =
        TaskDecision.Sleep(millisUntilNextChinaDay(ctx.nowMillis, ctx.behaviorContract.timezoneId))

    protected fun retrySameDay(ctx: TaskContext): TaskDecision =
        TaskDecision.Sleep(ctx.behaviorContract.dailySchedule.failedFeatureRetryMillis)

    protected fun completeIfNationalCitizen(ctx: TaskContext): TaskDecision? {
        if (!NationalCitizenDailyPolicy.isNationalCitizen(ctx.session)) return null
        ctx.prompt(type, NationalCitizenDailyPolicy.COMPLETED_MESSAGE)
        markDailyCompleted(ctx)
        return nextChinaDay(ctx)
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

/**
 * One task per desktop daily feature.  The desktop scheduler owns a separate
 * lock, completion record and result log for sign-in and arena coins; keeping
 * the same boundary on Android prevents a rejected feature from hiding its
 * siblings or making the whole daily pipeline appear successful.
 */
class DailySingleStepTask(
    accountId: Long,
    private val dailyStep: DailyStep
) : DailyFeatureTask<DailyStep>(
    accountId,
    DAILY_FEATURE_TASK_TYPES[dailyStep]
        ?: error("unsupported independent daily step: $dailyStep"),
    dailyStep
) {
    private val completionKey: String = DAILY_FEATURE_KEYS.getValue(dailyStep)
    private val label: String = DAILY_FEATURE_LABELS.getValue(dailyStep)

    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        val base = super.prepare(ctx)
        if (base != TaskDecision.Continue) return base
        return if (ctx.dailyCompletions.isCompleted(ctx.session.accountId, completionKey, ctx.nowMillis)) {
            TaskDecision.Sleep(millisUntilNextDailyFeatureCycle(ctx.nowMillis, ctx.behaviorContract.timezoneId, completionKey))
        } else {
            base
        }
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        return when (val result = ctx.protocol.runDailyStep(ctx.session, dailyStep)) {
            is ProtocolResult.Ok -> {
                if (result.value.success) {
                    ctx.dailyCompletions.markCompleted(
                        ctx.session.accountId,
                        completionKey,
                        ctx.nowMillis
                    )
                    stepSuccess(ctx, label, result.value)
                    ctx.recordSuccess(
                        DAILY_FEATURE_SUCCESS_CATEGORIES.getValue(dailyStep),
                        result.value.message.ifBlank { "${label}成功" }
                    )
                    // A server-confirmed success (including a duplicate/already
                    // claimed receipt normalized by the protocol adapter) is the
                    // only case that may suppress this feature until the next
                    // China day.  A business rejection must remain retryable;
                    // otherwise one transient/unsupported response silently
                    // disables the feature for the rest of the day.
                    TaskDecision.Sleep(
                        millisUntilNextDailyFeatureCycle(
                            ctx.nowMillis,
                            ctx.behaviorContract.timezoneId,
                            completionKey
                        )
                    )
                } else {
                    stepFailure(ctx, label, result.value)
                    TaskDecision.Sleep(ctx.behaviorContract.dailySchedule.failedFeatureRetryMillis)
                }
            }
            is ProtocolResult.Err -> protocolErrorDecision(ctx, label, result)
        }
    }
}

class DailyDonateTask(
    accountId: Long,
    config: DailyDonateConfig
) : DailyFeatureTask<DailyDonateConfig>(accountId, TaskType.DAILY_DONATE, config, "autoDonate") {
    override suspend fun step(ctx: TaskContext): TaskDecision {
        val steps = listOf(
            DailyStep.DONATE_COPPER to "铜钱捐献",
            DailyStep.DONATE_FOOD to "粮食捐献",
            DailyStep.DONATE_TECH to "科技积分捐献"
        )
        var failures = 0
        var alreadyCompletedByQuota = 0
        for ((dailyStep, label) in steps) {
            when (val result = ctx.protocol.runDailyStep(ctx.session, dailyStep)) {
                is ProtocolResult.Ok -> {
                    if (result.value.success) {
                        if (result.value.raw["alreadyCompleted"] == "true") {
                            alreadyCompletedByQuota++
                        }
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
        return if (failures == 0) {
            markDailyCompleted(ctx)
            val completionMessage = when (alreadyCompletedByQuota) {
                steps.size -> "三项今日捐献额度均已用完，自动捐献按已做处理"
                0 -> "铜钱、粮食、科技积分三项捐献已由服务器确认"
                else -> "三项捐献均已成功或达到今日额度，自动捐献已做"
            }
            ctx.prompt(type, "自动捐献完成：$completionMessage")
            ctx.recordSuccess("捐献", completionMessage)
            nextChinaDay(ctx)
        } else {
            retrySameDay(ctx)
        }
    }
}

internal fun millisUntilNextChinaDay(nowMillis: Long, timezoneId: String): Long {
    val zone = java.util.TimeZone.getTimeZone(timezoneId)
    val calendar = java.util.Calendar.getInstance(zone).apply {
        timeInMillis = nowMillis
        add(java.util.Calendar.DAY_OF_YEAR, 1)
        set(java.util.Calendar.HOUR_OF_DAY, 0)
        set(java.util.Calendar.MINUTE, 0)
        set(java.util.Calendar.SECOND, 0)
        set(java.util.Calendar.MILLISECOND, 0)
    }
    return (calendar.timeInMillis - nowMillis).coerceAtLeast(1_000L)
}

internal fun millisUntilNextDailyFeatureCycle(
    nowMillis: Long,
    timezoneId: String,
    completionKey: String
): Long {
    if (completionKey != "arenaCoins") return millisUntilNextChinaDay(nowMillis, timezoneId)
    val calendar = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone(timezoneId)).apply {
        timeInMillis = nowMillis
        if (get(java.util.Calendar.HOUR_OF_DAY) >= 22) {
            add(java.util.Calendar.DAY_OF_YEAR, 1)
        }
        set(java.util.Calendar.HOUR_OF_DAY, 22)
        set(java.util.Calendar.MINUTE, 0)
        set(java.util.Calendar.SECOND, 0)
        set(java.util.Calendar.MILLISECOND, 0)
    }
    return (calendar.timeInMillis - nowMillis).coerceAtLeast(1_000L)
}

class DailySalaryTask(
    accountId: Long,
    config: DailySalaryConfig
) : DailyFeatureTask<DailySalaryConfig>(accountId, TaskType.DAILY_SALARY, config, "salary") {
    override suspend fun step(ctx: TaskContext): TaskDecision {
        completeIfNationalCitizen(ctx)?.let { return it }
        return when (val result = ctx.protocol.runDailyStep(ctx.session, DailyStep.SALARY)) {
            is ProtocolResult.Ok -> {
                if (result.value.success) {
                    stepSuccess(ctx, "国家俸禄", result.value)
                    markDailyCompleted(ctx)
                    ctx.recordSuccess("俸禄", result.value.message.ifBlank { "领取俸禄成功" })
                    return nextChinaDay(ctx)
                } else {
                    stepFailure(ctx, "国家俸禄", result.value)
                }
                retrySameDay(ctx)
            }
            is ProtocolResult.Err -> protocolErrorDecision(ctx, "国家俸禄", result)
        }
    }
}

class DailyNationalCollectTask(
    accountId: Long,
    config: DailyNationalCollectConfig
) : DailyFeatureTask<DailyNationalCollectConfig>(accountId, TaskType.DAILY_NATIONAL_COLLECT, config, "nationalCollect") {
    override suspend fun step(ctx: TaskContext): TaskDecision {
        completeIfNationalCitizen(ctx)?.let { return it }
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
        var statusFailureCount = 0
        for (kind in categories) {
            val cities = when (val result = ctx.protocol.queryNationalCities(ctx.session, kind)) {
                is ProtocolResult.Ok -> result.value
                is ProtocolResult.Err -> {
                    if (result.looksLikeSessionInvalid()) {
                        ctx.runtime.commandGate.markSessionExpired(ctx.session.accountId)
                        return TaskDecision.NeedRelogin("查询${kind.label()}失败：${result.message}")
                    }
                    ctx.prompt(type, "查询${kind.label()}失败：${result.message}")
                    statusFailureCount++
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
            if (statusFailureCount == 0) {
                ctx.prompt(type, "没有可执行的国家征收城池（已跳过小城）")
                markDailyCompleted(ctx)
                return nextChinaDay(ctx)
            }
            ctx.prompt(type, "国家征收城池列表读取失败，保留今日任务并稍后重试")
            return retrySameDay(ctx)
        }

        val ranked = mutableListOf<RankedNationalCity>()
        var inspectedStatusCount = 0
        var quotaLimit: Int? = null
        var quotaUsed = 0
        for (city in candidatesByName.values) {
            when (val result = ctx.protocol.queryNationalCollectStatus(ctx.session, city)) {
                is ProtocolResult.Ok -> {
                    inspectedStatusCount++
                    val status = result.value
                    if (status.limit > 0) {
                        quotaLimit = quotaLimit?.coerceAtMost(status.limit) ?: status.limit
                        quotaUsed = maxOf(quotaUsed, status.usedCount)
                    }
                    if (status.canCollect) {
                        ranked += RankedNationalCity(city, status.currentCopper)
                    }
                }
                is ProtocolResult.Err -> {
                    if (result.looksLikeSessionInvalid()) {
                        ctx.runtime.commandGate.markSessionExpired(ctx.session.accountId)
                        return TaskDecision.NeedRelogin("查询${city.name}征收金额失败：${result.message}")
                    }
                    statusFailureCount++
                    ctx.prompt(type, "查询${city.name}征收金额失败：${result.message}")
                }
            }
        }

        val quotaExhausted = quotaLimit?.let { quotaUsed >= it } ?: false
        ranked.sortWith(
            compareByDescending<RankedNationalCity> { it.copper }
                .thenBy { it.city.kind.priority }
                .thenBy { it.city.name }
        )
        val actionLimit = if (config.maxAttempts > 0) {
            config.maxAttempts.coerceAtMost(MAX_NATIONAL_COLLECTION_ATTEMPTS)
        } else {
            MAX_NATIONAL_COLLECTION_ATTEMPTS
        }
        var successfulCount = 0
        var actionFailureCount = 0
        var attemptedCount = 0
        if (!quotaExhausted) for (candidate in ranked.take(actionLimit)) {
            attemptedCount++
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
                        actionFailureCount++
                        stepFailure(ctx, "国家征收${candidate.city.name}", result.value)
                    }
                }
                is ProtocolResult.Err -> {
                    if (result.looksLikeSessionInvalid()) {
                        ctx.runtime.commandGate.markSessionExpired(ctx.session.accountId)
                        return TaskDecision.NeedRelogin("国家征收${candidate.city.name}：${result.message}")
                    }
                    actionFailureCount++
                    ctx.prompt(type, "国家征收${candidate.city.name}失败：${result.message}")
                }
            }
        }

        val noTarget = inspectedStatusCount > 0 && ranked.isEmpty() && statusFailureCount == 0
        val allRankedProcessed = attemptedCount >= ranked.size
        val completed = quotaExhausted || noTarget || (
            allRankedProcessed &&
                statusFailureCount == 0 &&
                actionFailureCount == 0 &&
                successfulCount == attemptedCount
            )
        ctx.prompt(
            type,
            if (successfulCount > 0) {
                "国家征收${if (actionFailureCount > 0) "部分" else ""}完成：成功${successfulCount}次，检查${inspectedStatusCount}座城池，跳过小城"
            } else if (quotaExhausted) {
                "国家征收次数已用尽"
            } else if (noTarget) {
                "当前州城、郡城、县城均没有可征收铜钱（已跳过小城）"
            } else {
                "国家征收未完成：失败${statusFailureCount + actionFailureCount}项"
            }
        )
        return if (completed) {
            markDailyCompleted(ctx)
            if (successfulCount > 0) {
                ctx.recordSuccess(
                    "国征",
                    "成功${successfulCount}次，检查${inspectedStatusCount}座城池，已跳过小城"
                )
            }
            nextChinaDay(ctx)
        } else {
            retrySameDay(ctx)
        }
    }

    private data class RankedNationalCity(val city: NationalCity, val copper: Long)
}

private fun NationalCity.normalizedKind(): NationalCityKind =
    kind.takeUnless { it == NationalCityKind.UNKNOWN }
        ?: NationalCityKind.fromListCategory(listCategory)

class DailyCityLordCollectTask(
    accountId: Long,
    config: DailyCityLordCollectConfig
) : DailyFeatureTask<DailyCityLordCollectConfig>(accountId, TaskType.DAILY_CITY_LORD_COLLECT, config, "cityLordCollect") {
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
            markDailyCompleted(ctx)
            return nextChinaDay(ctx)
        }
        val contract = ctx.behaviorContract.dailyActions.cityLordCollect
        var failures = 0
        var executed = 0
        var serverSuccesses = 0
        for (fief in cities) {
            when (val result = ctx.protocol.collectCityLord(ctx.session, fief)) {
                is ProtocolResult.Ok -> {
                    if (result.value.success) {
                        executed++
                        serverSuccesses++
                        stepSuccess(ctx, "城主征收${fief.cityName}", result.value)
                    } else {
                        val message = result.value.message
                        when {
                            contract.ineligibleMarkers.any(message::contains) -> {
                                executed++
                                ctx.prompt(type, "城主征收${fief.cityName}：当前城池不可征收，已完成今日尝试")
                            }
                            contract.alreadyCollectedMarkers.any(message::contains) -> {
                                executed++
                                ctx.prompt(type, "城主征收${fief.cityName}：今日已经征收，按完成处理")
                            }
                            else -> {
                                failures++
                                stepFailure(ctx, "城主征收${fief.cityName}", result.value)
                            }
                        }
                    }
                }
                is ProtocolResult.Err -> {
                    if (result.looksLikeSessionInvalid()) {
                        ctx.runtime.commandGate.markSessionExpired(ctx.session.accountId)
                        return TaskDecision.NeedRelogin("城主征收${fief.cityName}：${result.message}")
                    }
                    failures++
                    ctx.prompt(type, "城主征收${fief.cityName}失败：${result.message}")
                }
            }
        }
        return if (failures == 0 && executed >= cities.size) {
            markDailyCompleted(ctx)
            if (serverSuccesses > 0) {
                ctx.recordSuccess("城征", "成功${serverSuccesses}座，失败0座")
            }
            nextChinaDay(ctx)
        } else {
            retrySameDay(ctx)
        }
    }
}

class DailyGeneralVisitTask(
    accountId: Long,
    config: DailyGeneralVisitConfig
) : DailyFeatureTask<DailyGeneralVisitConfig>(accountId, TaskType.DAILY_GENERAL_VISIT, config, "generalVisit") {
    override suspend fun step(ctx: TaskContext): TaskDecision {
        completeIfNationalCitizen(ctx)?.let { return it }
        val query = when (val result = ctx.protocol.queryVisitGenerals(ctx.session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return protocolErrorDecision(ctx, "查询可拜访名将", result)
        }
        if (query.completed) {
            ctx.prompt(type, query.message.ifBlank { "本日已经完成名将拜访" })
            markDailyCompleted(ctx)
            return nextChinaDay(ctx)
        }
        val configuredIds = config.selectedIds
            .take(ctx.behaviorContract.dailyActions.generalVisit.maxSelected)
        val orderedIds = configuredIds.ifEmpty {
            query.candidates
                .firstOrNull { it.captiveState == 0 }
                ?.let { candidate ->
                    ctx.prompt(type, "未指定名将，已自动选择可拜访列表首位：${candidate.name}")
                    listOf(candidate.id)
                }
                .orEmpty()
        }
        if (orderedIds.isEmpty()) {
            ctx.prompt(type, "当前没有可拜访名将，稍后重新查询")
            return retrySameDay(ctx)
        }
        val candidates = query.candidates.associateBy { it.id }
        var attempted = 0
        var failures = 0
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
                    val terminal = result.value.success ||
                        result.value.raw["alreadyVisited"].equals("true", ignoreCase = true) ||
                        result.value.raw["invitationResolved"].equals("true", ignoreCase = true)
                    if (terminal) {
                        stepSuccess(ctx, "名将拜访成功：${candidate.name}", result.value)
                        markDailyCompleted(ctx)
                        ctx.recordSuccess(
                            "拜访",
                            "${candidate.name}：${result.value.message.ifBlank { "名将拜访成功" }}"
                        )
                        return nextChinaDay(ctx)
                    }
                    failures++
                    stepFailure(ctx, "拜访${candidate.name}", result.value)
                }
                is ProtocolResult.Err -> {
                    if (result.looksLikeSessionInvalid()) {
                        ctx.runtime.commandGate.markSessionExpired(ctx.session.accountId)
                        return TaskDecision.NeedRelogin("拜访${candidate.name}：${result.message}")
                    }
                    failures++
                    ctx.prompt(type, "拜访${candidate.name}失败，顺延下一名：${result.message}")
                }
            }
        }
        ctx.prompt(type, if (attempted == 0) "没有可尝试拜访的已选名将" else "已按优先级尝试，未有名将拜访成功")
        return retrySameDay(ctx)
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
