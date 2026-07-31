package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.*
import com.example.dwpmclone.domain.localmap.BanditCacheKey
import com.example.dwpmclone.domain.localmap.MineCacheKey
import com.example.dwpmclone.domain.state.GateResult

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

private fun TaskContext.claimMilitaryGenerals(
    owner: TaskType,
    generalIds: Collection<Long>,
    label: String
): TaskDecision? = when (val gate = runtime.commandGate.tryClaimGenerals(
    accountId = session.accountId,
    owner = owner,
    taskKey = militaryTaskKey(owner),
    generalIds = generalIds,
    nowMillis = nowMillis,
    reason = "${label}检查及出征"
)) {
    GateResult.Allowed -> null
    is GateResult.Blocked -> TaskDecision.Sleep(
        gate.retryAfterMillis,
        reason = "${label}让行：${gate.reason}"
    )
}

private fun TaskContext.releaseMilitaryClaim(owner: TaskType) {
    runtime.commandGate.releaseReservation(session.accountId, owner, militaryTaskKey(owner))
}

private fun TaskContext.releaseMilitaryTask(owner: TaskType) {
    runtime.commandGate.releaseTask(session.accountId, owner)
}

private fun TaskContext.markMilitaryBusy(
    owner: TaskType,
    generalIds: Collection<Long>,
    reason: String
) {
    runtime.commandGate.markGeneralsBusy(
        session.accountId,
        owner,
        militaryTaskKey(owner),
        generalIds,
        nowMillis,
        reason
    )
}

private fun militaryTaskKey(owner: TaskType): String = "resident:${owner.name}"

private fun ProtocolResult.Err.isUncertainExpeditionSend(): Boolean =
    code.startsWith("REAL_ACTION_EXPEDITION_", ignoreCase = true) ||
        code.startsWith("REAL_MINE_DISPATCH_", ignoreCase = true) ||
        code.startsWith("REAL_DUNGEON_LAUNCH_", ignoreCase = true) ||
        code.startsWith("REAL_LOSSLESS_DISPATCH_", ignoreCase = true) ||
        code.startsWith("REAL_LOOT_DISPATCH_", ignoreCase = true)

private fun ProtocolResult.Err.keepsShortMilitaryClaim(): Boolean =
    code.endsWith("_APPLIED") ||
        code.contains("TRANSACTION_UNRESOLVED", ignoreCase = true) ||
        code.contains("REWARD_NOT_READY") ||
        code.contains("SETTLEMENT", ignoreCase = true)

private fun List<FormationConfig>.forGenerals(generalIds: Collection<Long>): List<FormationConfig> {
    val selected = generalIds.filter { it > 0L }.toSet()
    return filter { rule ->
        rule.generalIds.ifEmpty { listOf(rule.formationId) }.any(selected::contains)
    }
}

class DailyPipelineTask(accountId: Long, config: DailyConfig) :
    BaseAssistantTask<DailyConfig>(accountId, TaskType.DAILY, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (config.enabledSteps.isEmpty()) return TaskDecision.Stop("no daily step selected")
        val unrecovered = config.enabledSteps - DailyProtocolShapes.recoveredSteps
        if (unrecovered.isNotEmpty()) {
            return TaskDecision.Stop("unrecovered daily steps selected: ${unrecovered.joinToString(",")}")
        }
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        for (shape in DailyProtocolShapes.buildExecutionPlan(config.enabledSteps)) {
            val decision = if (shape.step == DailyStep.CONVERT_HALF_FOOD_TO_COPPER) {
                when (val result = ctx.protocol.convertFoodToCopper(ctx.session, ConvertMode.FOOD_TO_COPPER_HALF)) {
                    is ProtocolResult.Ok -> TaskDecision.Continue
                    is ProtocolResult.Err -> if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
                }
            } else {
                when (val result = ctx.protocol.runDailyStep(ctx.session, shape.step)) {
                    is ProtocolResult.Ok -> if (!result.value.success && config.stopOnStepFailure) TaskDecision.Stop(result.value.message) else TaskDecision.Continue
                    is ProtocolResult.Err -> if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
                }
            }
            if (decision is TaskDecision.Stop || decision is TaskDecision.RetryAfter) return decision
        }
        return TaskDecision.Sleep(24 * 60 * 60 * 1000L)
    }
}

/**
 * Low-priority, one-request-at-a-time bandit map preparation.
 *
 * The computer helper keeps this outside the expedition loop. Android does the same here:
 * every invocation scans exactly one canonical coordinate and yields, while ShuaHuangTask
 * still owns the final filter, reservation, revalidation and dispatch fallback.
 */
class BanditPrefetchTask(accountId: Long, config: ShuaHuangConfig) :
    BaseAssistantTask<ShuaHuangConfig>(accountId, TaskType.BANDIT_PREFETCH, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled) return TaskDecision.Stop("闲时找山贼对应的刷黄任务未启用")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        val contract = ctx.behaviorContract.mapSearch
        val coordinates = RecoveredMapScanPlanner.nearbyRequests(
            RecoveredSearchKind.TARGET_041540,
            config.start,
            contract.fullRequestLimit,
            contract
        ).map { it.coordinate }
        if (coordinates.isEmpty()) return TaskDecision.Sleep(PREFETCH_IDLE_MILLIS)
        val key = BanditCacheKey.from(ctx.session, config.start, config.targetType)
        val cursor = ctx.localMap.nextPreparationIndex(
            ctx.session.accountId,
            "bandit:${key.query().serverId}:${key.query().fingerprint}",
            coordinates.size
        )
        val coordinate = coordinates[cursor]
        val singleRequestSession = ctx.session.copy(
            channelExtra = ctx.session.channelExtra + mapOf(
                "recoveredReadOnlyScanMode" to "SINGLE",
                "recoveredReadOnlyScanLimit" to "1"
            )
        )
        return when (val result = ctx.protocol.searchMap(
            singleRequestSession,
            coordinate,
            MapSearchPolicy(targetType = config.targetType)
        )) {
            is ProtocolResult.Ok -> {
                val existing = ctx.localMap.bandits(key, ctx.nowMillis).orEmpty()
                ctx.localMap.saveBandits(
                    key,
                    (existing + result.value).distinctBy { it.id to it.coordinate },
                    ctx.nowMillis
                )
                ctx.runtime.emit(
                    "account=${ctx.session.accountId} idle-map bandit coord=${coordinate.x},${coordinate.y} " +
                        "found=${result.value.size} pooled=${(existing + result.value).distinctBy { it.id to it.coordinate }.size}"
                )
                TaskDecision.Sleep(ctx.behaviorContract.brushYellow.schedule.mapPreparationIdlePauseMillis)
            }
            is ProtocolResult.Err -> TaskDecision.RetryAfter(
                ctx.behaviorContract.brushYellow.schedule.transientRetryMillis,
                "闲时找山贼失败：${result.message}"
            )
        }
    }

    private companion object {
        const val PREFETCH_IDLE_MILLIS = 2_000L
    }
}

/** Low-priority resource-point pool preparation for enabled automatic-mining rows. */
class MinePrefetchTask(accountId: Long, config: MineConfig) :
    BaseAssistantTask<MineConfig>(accountId, TaskType.MINE_PREFETCH, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled) return TaskDecision.Stop("闲时找资源点对应的自动打矿任务未启用")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        val ruleConfigs = config.rules
            .filter { it.enabled && it.generalIds.isNotEmpty() }
            .map { rule ->
                config.copy(
                    start = rule.start,
                    selectedMineTypes = setOf(rule.mineType),
                    selectedFormationIds = rule.generalIds.toSet(),
                    onlyEmptyMine = rule.onlyEmpty,
                    onlyDefendedMine = rule.onlyDefended,
                    searchScope = rule.scope,
                    selectedLevels = rule.level?.let(::setOf) ?: emptySet(),
                    formationRules = config.formationRules.forGenerals(rule.generalIds)
                )
            }
            .ifEmpty { listOf(config) }
        val ruleIndex = ctx.localMap.nextPreparationIndex(
            ctx.session.accountId,
            "mine-rules",
            ruleConfigs.size
        )
        val activeConfig = ruleConfigs[ruleIndex]
        val cacheKey = MineCacheKey.from(ctx.session, activeConfig)
        val coordinates = RecoveredMapScanPlanner.mineScopeRequests(
            RecoveredSearchKind.RESOURCE_POINT_041542,
            activeConfig.start,
            activeConfig.searchScope,
            ctx.behaviorContract.mapSearch
        ).map { it.coordinate }
        if (coordinates.isEmpty()) return TaskDecision.Sleep(PREFETCH_IDLE_MILLIS)
        val coordinateIndex = ctx.localMap.nextPreparationIndex(
            ctx.session.accountId,
            "mine:${cacheKey.query().serverId}:${cacheKey.query().fingerprint}",
            coordinates.size
        )
        val coordinate = coordinates[coordinateIndex]
        val exactConfig = activeConfig.copy(start = coordinate, searchScope = "定点")
        return when (val result = ctx.protocol.searchMines(ctx.session, exactConfig)) {
            is ProtocolResult.Ok -> {
                val existing = ctx.localMap.mines(cacheKey, ctx.nowMillis).orEmpty()
                val pooled = (existing + result.value).distinctBy { it.id to it.coordinate }
                ctx.localMap.saveMines(cacheKey, pooled, ctx.nowMillis)
                ctx.runtime.emit(
                    "account=${ctx.session.accountId} idle-map mine coord=${coordinate.x},${coordinate.y} " +
                        "found=${result.value.size} pooled=${pooled.size}"
                )
                TaskDecision.Sleep(ctx.behaviorContract.brushYellow.schedule.mapPreparationIdlePauseMillis)
            }
            is ProtocolResult.Err -> TaskDecision.RetryAfter(
                ctx.behaviorContract.mine.schedule.targetUnavailableRetryMillis,
                "闲时找资源点失败：${result.message}"
            )
        }
    }

    private companion object {
        const val PREFETCH_IDLE_MILLIS = 2_000L
    }
}

/** Brush task orchestration: validate -> refresh state -> choose local target -> preflight -> dispatch. */
class ShuaHuangTask(accountId: Long, config: ShuaHuangConfig) :
    BaseAssistantTask<ShuaHuangConfig>(accountId, TaskType.SHUA_HUANG, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled) return TaskDecision.Stop("auto shua huang disabled")
        if (config.dailyLimit <= 0) return TaskDecision.Stop("shua huang daily limit must be positive")
        if (config.selectedFormationIds.isEmpty()) return TaskDecision.Stop("no formation selected")
        val configuredRules = config.rules.filter { it.enabled }
        if (configuredRules.any { it.generalIds.isEmpty() }) {
            return TaskDecision.Stop("刷黄编队缺少出征将领")
        }
        if (configuredRules.any {
                it.generalIds.distinct().size >
                    ctx.behaviorContract.brushYellow.maximumGeneralsPerFormation
            }
        ) {
            return TaskDecision.Stop(
                "刷黄编队最多选择" +
                    "${ctx.behaviorContract.brushYellow.maximumGeneralsPerFormation}名出征将领"
            )
        }
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        BrushPendingRecovery.fromJson(
            ctx.session.channelExtra[BrushPendingRecovery.SESSION_KEY]
        )?.let { persisted ->
            ctx.runtime.addPendingBrushRecovery(
                ctx.session.accountId,
                type,
                persisted.generalIds
            )
            ctx.shuaLog(
                "restored-post-dispatch-recovery state=${persisted.sendState} " +
                    "generals=${persisted.generalIds.joinToString()} target=${persisted.targetId}"
            )
        }
        val rawPersistedUsedCount = ctx.session.channelExtra["shuaHuangUsedCount"]?.toIntOrNull()
            ?: ctx.session.channelExtra["usedAount"]?.toIntOrNull()
            ?: 0
        val persistedUsedCount = ctx.runtime.persistedBrushCountForDay(
            ctx.session.accountId,
            type,
            rawPersistedUsedCount,
            ctx.nowMillis
        )
        val realBrushGate = ctx.session.realBrushYellowGateReady()
        val pendingRecoveryGeneralIds = ctx.runtime.pendingBrushRecoveryGeneralIds(ctx.session.accountId, type)
        val usedCount = persistedUsedCount +
            ctx.runtime.brushConsumedCount(ctx.session.accountId, type, ctx.nowMillis)
        ctx.shuaLog("step-start used=$usedCount limit=${config.dailyLimit} selectedFormations=${config.selectedFormationIds.joinToString()}")
        if (usedCount >= config.dailyLimit && (!realBrushGate || pendingRecoveryGeneralIds.isEmpty())) {
            val wait = millisUntilNextDailyStart(
                ctx.nowMillis,
                config.startHour,
                ctx.behaviorContract.timezoneId
            )
            ctx.shuaLog("daily-limit reached used=$usedCount limit=${config.dailyLimit}; keep-resident waitMillis=$wait")
            return TaskDecision.Sleep(wait)
        }
        val waitForStart = millisUntilConfiguredStart(
            ctx.nowMillis,
            config.startHour,
            ctx.behaviorContract.timezoneId
        )
        if (waitForStart > 0L) {
            ctx.shuaLog("scheduled startHour=${config.startHour} waitMillis=$waitForStart")
            return TaskDecision.Sleep(waitForStart)
        }

        val brushContract = ctx.behaviorContract.brushYellow
        val brushSchedule = brushContract.schedule
        ctx.shuaLog("refresh-monarch")
        val monarch = when (val result = ctx.protocol.queryMonarch(ctx.session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return if (result.retryable) {
                TaskDecision.RetryAfter(brushSchedule.transientRetryMillis)
            } else {
                TaskDecision.Stop(result.message)
            }
        }
        if (monarch.level < brushContract.minimumRoleLevel) {
            return TaskDecision.Stop("请${brushContract.minimumRoleLevel}级之后再开启刷黄！")
        }

        ctx.shuaLog("refresh-resource")
        val resources = when (val result = ctx.protocol.queryResourceState(ctx.session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return if (result.retryable) TaskDecision.RetryAfter(brushSchedule.transientRetryMillis) else TaskDecision.Stop(result.message)
        }
        val minimumCopper = config.minCopperWan * 10_000L
        ctx.shuaLog("resource copper=${resources.copper} food=${resources.food} minCopper=$minimumCopper")
        if (minimumCopper > 0 && resources.copper < minimumCopper) {
            if (!config.autoConvertFoodToCopper) return TaskDecision.Stop("copper below configured reserve: ${resources.copper} < $minimumCopper")
            val convertedResources = when (val result = ctx.protocol.convertFoodToCopper(ctx.session, ConvertMode.FOOD_TO_COPPER_THRESHOLD)) {
                is ProtocolResult.Ok -> result.value
                is ProtocolResult.Err -> return if (result.retryable) TaskDecision.RetryAfter(brushSchedule.transientRetryMillis) else TaskDecision.Stop(result.message)
            }
            if (convertedResources.copper > resources.copper) {
                ctx.recordSuccess(
                    "转铜",
                    "${resources.food - convertedResources.food}粮换${convertedResources.copper - resources.copper}铜"
                )
            }
            if (convertedResources.copper < minimumCopper) {
                return TaskDecision.Stop("copper still below configured reserve after food conversion: ${convertedResources.copper} < $minimumCopper")
            }
        }

        ctx.shuaLog("query-generals")
        val generals = when (val result = ctx.protocol.queryGenerals(ctx.session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return if (result.retryable) TaskDecision.RetryAfter(brushSchedule.transientRetryMillis) else TaskDecision.Stop(result.message)
        }
        ctx.shuaLog("generals total=${generals.size} idle=${generals.count { it.status == null || it.status == 0 }}")
        if (generals.isEmpty()) return TaskDecision.Stop("no generals available for shua huang")

        ctx.shuaLog("query-formations")
        val formations = when (val result = ctx.protocol.queryFormations(ctx.session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return if (result.retryable) TaskDecision.RetryAfter(brushSchedule.transientRetryMillis) else TaskDecision.Stop(result.message)
        }
        ctx.shuaLog("formations total=${formations.size} selected=${formations.count { it.id in config.selectedFormationIds }}")
        formations.firstOrNull {
            it.id in config.selectedFormationIds &&
                it.generalIds.distinct().size > brushContract.maximumGeneralsPerFormation
        }?.let { oversized ->
            return TaskDecision.Stop(
                "刷黄编队${oversized.name ?: oversized.id}最多选择" +
                    "${brushContract.maximumGeneralsPerFormation}名出征将领"
            )
        }
        ctx.runtime.commandGate.reconcileServerState(ctx.session.accountId, generals, formations, ctx.nowMillis)
        if (realBrushGate) {
            runPendingRecoveryIfReturned(ctx, generals)?.let { return it }
        }
        if (usedCount >= config.dailyLimit) {
            val wait = millisUntilNextDailyStart(
                ctx.nowMillis,
                config.startHour,
                ctx.behaviorContract.timezoneId
            )
            ctx.shuaLog("daily-limit reached after-recovery used=$usedCount limit=${config.dailyLimit}; waitMillis=$wait")
            return TaskDecision.Sleep(wait)
        }
        val candidateFormations = chooseFormations(formations, generals)
        ctx.shuaLog("candidate-formations=${candidateFormations.joinToString { it.id.toString() }.ifBlank { "none" }}")
        if (candidateFormations.isEmpty()) return TaskDecision.Sleep(brushSchedule.busyGeneralPollMillis)

        val cacheKey = BanditCacheKey.from(ctx.session, config.start, config.targetType)
        val cachedTargets = ctx.localMap.bandits(cacheKey, ctx.nowMillis)
        val targets = if (cachedTargets != null) {
            ctx.shuaLog("targets-local-cache total=${cachedTargets.size}")
            cachedTargets
        } else {
            ctx.shuaLog("search-target-local start=${config.start.x},${config.start.y} type=${config.targetType}")
            when (val result = ctx.protocol.searchMap(
                ctx.session,
                config.start,
                MapSearchPolicy(targetType = config.targetType)
            )) {
                is ProtocolResult.Ok -> result.value.also {
                    ctx.localMap.saveBandits(cacheKey, it, ctx.nowMillis)
                }
                is ProtocolResult.Err -> return if (result.retryable) {
                    TaskDecision.RetryAfter(brushSchedule.transientRetryMillis)
                } else {
                    TaskDecision.Stop(result.message)
                }
            }
        }
        ctx.shuaLog("targets-local total=${targets.size} matched=${targets.count { it.matchesTargetType(config.targetType) }}")
        val matchingTargetAvailable = candidateFormations.any {
            chooseTargetForFormation(targets, it) != null
        }
        val (formation, target) = chooseReservableExpedition(ctx, candidateFormations, targets) ?: run {
            if (!matchingTargetAvailable) {
                // Desktop continues scanning when its filtered candidate pool is empty.
                // Expire this query rather than rereading a large but unusable snapshot forever.
                ctx.localMap.clearBandits(cacheKey)
                ctx.shuaLog("no-matching-targets cache-expired; scan-next-tick")
            }
            val wait = if (matchingTargetAvailable) {
                brushSchedule.busyGeneralPollMillis
            } else {
                brushSchedule.targetUnavailableRetryMillis
            }
            ctx.shuaLog("no-reservable-expedition wait=$wait")
            return TaskDecision.Sleep(wait)
        }
        ctx.shuaLog("selected formation=${formation.id} target=${target.id} coord=${target.coordinate.x},${target.coordinate.y} type=${target.type}")
        val refillDelegated = ctx.session.sourceMode == 1 &&
            ctx.session.channelExtra["unifiedExpeditionPreflight"].equals("true", ignoreCase = true)
        if (config.replenishTroops && !refillDelegated) {
            val generalIds = formation.generalIds.ifEmpty { listOf(formation.id) }
                .filter { it > 0L }
            if (generalIds.isEmpty()) {
                return TaskDecision.Stop("批量补满缺少出征将领，已阻止刷黄出征")
            }
            ctx.shuaLog("pre-dispatch-batch-refill generals=${generalIds.joinToString()}")
            when (val refill = ctx.protocol.updateFormation(
                ctx.session,
                FormationConfig(
                    formationId = formation.id,
                    generalIds = generalIds,
                    autoAssignTroops = false,
                    troopType = "",
                    troopCount = 0,
                    fillToMaxWhenAutoAssignDisabled = true
                )
            )) {
                is ProtocolResult.Err -> {
                    ctx.runtime.commandGate.releaseReservation(
                        ctx.session.accountId,
                        type,
                        runtimeTaskKey()
                    )
                    return if (refill.retryable) {
                        TaskDecision.RetryAfter(brushSchedule.transientRetryMillis)
                    } else {
                        TaskDecision.Stop("刷黄出征前批量补满失败：${refill.message}")
                    }
                }
                is ProtocolResult.Ok -> if (!refill.value.success) {
                    ctx.runtime.commandGate.releaseReservation(
                        ctx.session.accountId,
                        type,
                        runtimeTaskKey()
                    )
                    return TaskDecision.Stop("刷黄出征前批量补满失败：${refill.value.message}")
                }
            }
        } else if (config.replenishTroops) {
            ctx.shuaLog("pre-dispatch-batch-refill delegated to unified expedition preflight")
        }
        ctx.runtime.commandGate.markDispatchSending(ctx.session.accountId, type, runtimeTaskKey(), formation.id, ctx.nowMillis)
        return when (val dispatch = ctx.protocol.dispatchFormation(
            ctx.session,
            formation,
            target,
            config.formationRules
        )) {
            is ProtocolResult.Ok -> {
                if (!dispatch.value.success) {
                    val failureMessage = dispatch.value.failureMessage()
                    ctx.shuaLog("dispatch-failed formation=${formation.id} target=${target.id} message=$failureMessage")
                    ctx.shuaLogDispatchDryRun(dispatch.value)
                    // markDispatchSending already promoted the lease from RESERVED to
                    // DISPATCHING. Releasing only reservations is therefore a no-op and blocks
                    // both this task and dungeon until the 20-minute lease expires.
                    ctx.releaseMilitaryTask(type)
                    val softReject = dispatch.value.isSoftDispatchReject(ctx.behaviorContract.expedition)
                    val next = if (softReject) {
                        ctx.shuaLog(
                            "dispatch-rejected-soft target=${target.id} " +
                                "wait=${brushSchedule.targetUnavailableRetryMillis} continue-search-next-tick"
                        )
                        TaskDecision.Sleep(brushSchedule.targetUnavailableRetryMillis)
                    } else {
                        TaskDecision.Stop("shua huang dispatch failed: $failureMessage")
                    }
                    ctx.localMap.invalidateBandit(
                        cacheKey,
                        target.id,
                        ctx.nowMillis,
                        if (softReject) "dispatch-rejected" else "dispatch-failed"
                    )
                    next
                } else {
                    ctx.runtime.commandGate.markDispatchAccepted(ctx.session.accountId, type, runtimeTaskKey(), formation.id, ctx.nowMillis)
                    val consumed = dispatch.value.consumedTimes.coerceAtLeast(1)
                    val localConsumedTimes = ctx.runtime.addBrushConsumed(
                        ctx.session.accountId,
                        type,
                        consumed,
                        ctx.nowMillis
                    )
                    ctx.shuaLog("dispatch-success formation=${formation.id} target=${target.id} consumed=$consumed localConsumed=$localConsumedTimes")
                    ctx.recordSuccess(
                        "刷黄",
                        "编队${formation.id} > ${target.type}(${target.coordinate.x}，${target.coordinate.y})"
                    )
                    ctx.shuaLogDispatchDryRun(dispatch.value)
                    val pendingAfterDispatch = realBrushGate && formation.generalIds.isNotEmpty()
                    if (realBrushGate) {
                        ctx.runtime.addPendingBrushRecovery(ctx.session.accountId, type, formation.generalIds)
                        ctx.shuaLog("post-dispatch-recovery-pending generals=${formation.generalIds.joinToString()} wait-return-before-heal")
                    } else if (ctx.session.shouldHealWounded()) {
                        formation.generalIds.forEach { generalId ->
                            when (val heal = ctx.protocol.healGeneral(ctx.session, generalId)) {
                                is ProtocolResult.Ok -> ctx.shuaLog("post-dispatch-heal general=$generalId success=${heal.value.success} message=${heal.value.message}")
                                is ProtocolResult.Err -> ctx.shuaLog("post-dispatch-heal skipped/error general=$generalId code=${heal.code} message=${heal.message}")
                            }
                        }
                    } else {
                        ctx.shuaLog("post-dispatch-heal disabled-by-common-setting")
                    }
                    val totalUsedAfterDispatch = usedCount + consumed
                    val next = if (totalUsedAfterDispatch >= config.dailyLimit) {
                        if (pendingAfterDispatch) {
                            ctx.shuaLog("daily-limit reached after dispatch; wait-return-before-stop used=$totalUsedAfterDispatch limit=${config.dailyLimit}")
                            TaskDecision.Sleep(brushSchedule.postDispatchPollMillis)
                        } else {
                            val wait = millisUntilNextDailyStart(
                                ctx.nowMillis,
                                config.startHour,
                                ctx.behaviorContract.timezoneId
                            )
                            ctx.shuaLog(
                                "daily-limit reached after-dispatch used=$totalUsedAfterDispatch " +
                                    "limit=${config.dailyLimit}; keep-resident waitMillis=$wait"
                            )
                            TaskDecision.Sleep(wait)
                        }
                    } else {
                        TaskDecision.Sleep(
                            if (realBrushGate) brushSchedule.postDispatchPollMillis
                            else brushSchedule.postReturnMaintenanceDelayMillis
                        )
                    }
                    ctx.localMap.invalidateBandit(cacheKey, target.id, ctx.nowMillis, "dispatch-accepted")
                    next
                }
            }
            is ProtocolResult.Err -> {
                ctx.shuaLog("dispatch-error formation=${formation.id} target=${target.id} code=${dispatch.code} message=${dispatch.message}")
                if (!dispatch.isUncertainExpeditionSend()) {
                    // Preflight/two-phase correction failed before an expedition could be
                    // accepted. Release DISPATCHING as well as RESERVED state immediately.
                    ctx.releaseMilitaryTask(type)
                }
                // 可重试错误主要是治疗/加体/配兵的两阶段刷新，或网络结果待确认。
                // 这些都不是“目标已失效”证据，不能误删已搜到的山贼。
                if (dispatch.retryable) TaskDecision.RetryAfter(brushSchedule.transientRetryMillis)
                else TaskDecision.Stop(dispatch.message)
            }
        }
    }

    override suspend fun stop(ctx: TaskContext, reason: String) {
        // Task-specific cleanup hook only. Session logout is centralized in TaskScheduler.stopAll
        // so a brush-yellow stop maps to exactly one explicit logout request.
    }
    private fun TaskContext.shuaLog(message: String) {
        runtime.emit("account=${session.accountId} owner=$type brush-yellow $message")
    }

    private fun millisUntilConfiguredStart(
        nowMillis: Long,
        startHour: Int,
        timezoneId: String
    ): Long {
        val hour = startHour.coerceIn(0, 23)
        if (hour == 0) return 0L
        val now = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone(timezoneId)).apply {
            timeInMillis = nowMillis
        }
        if (now.get(java.util.Calendar.HOUR_OF_DAY) >= hour) return 0L
        val target = (now.clone() as java.util.Calendar).apply {
            set(java.util.Calendar.HOUR_OF_DAY, hour)
            set(java.util.Calendar.MINUTE, 0)
            set(java.util.Calendar.SECOND, 0)
            set(java.util.Calendar.MILLISECOND, 0)
        }
        return (target.timeInMillis - nowMillis).coerceAtLeast(0L)
    }

    private fun millisUntilNextDailyStart(
        nowMillis: Long,
        startHour: Int,
        timezoneId: String
    ): Long {
        val target = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone(timezoneId)).apply {
            timeInMillis = nowMillis
            add(java.util.Calendar.DAY_OF_YEAR, 1)
            set(java.util.Calendar.HOUR_OF_DAY, startHour.coerceIn(0, 23))
            set(java.util.Calendar.MINUTE, 0)
            set(java.util.Calendar.SECOND, 0)
            set(java.util.Calendar.MILLISECOND, 0)
        }
        return (target.timeInMillis - nowMillis).coerceAtLeast(60_000L)
    }

    private fun com.example.dwpmclone.domain.model.GameSession.realBrushYellowGateReady(): Boolean =
        channelExtra["realActionNetworkAllowed"].equals("true", ignoreCase = true) &&
            channelExtra["realActionSendReady"].equals("true", ignoreCase = true) &&
            (
                channelExtra["realActionScope"].equals("brush-yellow", ignoreCase = true) ||
                    channelExtra["realActionBrushYellowOnly"].equals("true", ignoreCase = true)
                )

    private fun com.example.dwpmclone.domain.model.GameSession.shouldHealWounded(): Boolean =
        !channelExtra["expeditionHealWounded"].equals("false", ignoreCase = true)

    private suspend fun runPendingRecoveryIfReturned(
        ctx: TaskContext,
        generals: List<General>
    ): TaskDecision? {
        val pendingRecoveryGeneralIds = ctx.runtime.pendingBrushRecoveryGeneralIds(ctx.session.accountId, type)
        if (pendingRecoveryGeneralIds.isEmpty()) return null
        val byId = generals.associateBy { it.id }
        val pending = pendingRecoveryGeneralIds.mapNotNull { generalId ->
            byId[generalId] ?: run {
                ctx.shuaLog("pending-recovery general=$generalId missing wait-next")
                return null
            }
        }
        pending.firstOrNull { it.status != 0 }?.let { general ->
            ctx.shuaLog("pending-recovery general=${general.id} status=${general.status} not-idle wait-next")
            return null
        }
        pending.firstOrNull {
            ctx.runtime.generalLease(ctx.session.accountId, it.id, ctx.nowMillis) != null
        }?.let { general ->
            ctx.shuaLog(
                "pending-recovery general=${general.id} still-has-dispatch-lease " +
                    "wait-fresh-server-idle"
            )
            return null
        }

        if (ctx.session.shouldHealWounded()) {
            // Healing is fief-scoped. A multi-general desktop brush row may place several
            // generals in the same fief, so issue exactly one heal-all request per fief.
            val representatives = pending.distinctBy { it.placeId ?: it.id }
            for (general in representatives) {
                when (val heal = ctx.protocol.healGeneral(ctx.session, general.id)) {
                    is ProtocolResult.Ok -> {
                        ctx.shuaLog(
                            "post-return-heal general=${general.id} success=${heal.value.success} " +
                                "message=${heal.value.message}"
                        )
                        if (!heal.value.success) {
                            return TaskDecision.Stop("刷黄战后治疗失败：${heal.value.message}")
                        }
                    }
                    is ProtocolResult.Err -> {
                        ctx.shuaLog(
                            "post-return-heal error general=${general.id} " +
                                "code=${heal.code} message=${heal.message}"
                        )
                        return if (heal.retryable) {
                            TaskDecision.RetryAfter(
                                ctx.behaviorContract.brushYellow.schedule.transientRetryMillis
                            )
                        } else {
                            TaskDecision.Stop("刷黄战后治疗失败：${heal.message}")
                        }
                    }
                }
            }
        } else {
            ctx.shuaLog("post-return-heal disabled-by-common-setting")
        }
        val pendingIdSet = pendingRecoveryGeneralIds.toSet()
        for (rule in config.formationRules.filter { formationRule ->
            formationRule.generalIds
                .ifEmpty { listOf(formationRule.formationId) }
                .any(pendingIdSet::contains)
        }) {
            when (val assigned = ctx.protocol.updateFormation(ctx.session, rule)) {
                is ProtocolResult.Ok -> if (!assigned.value.success) {
                    return TaskDecision.Stop(
                        "刷黄战后按保存规则配兵失败：${assigned.value.message}"
                    )
                }
                is ProtocolResult.Err -> return if (assigned.retryable) {
                    TaskDecision.RetryAfter(
                        ctx.behaviorContract.brushYellow.schedule.transientRetryMillis,
                        "刷黄战后配兵待重试：${assigned.message}"
                    )
                } else {
                    TaskDecision.Stop("刷黄战后配兵失败：${assigned.message}")
                }
            }
            ctx.shuaLog(
                "post-return-formation-restored generals=" +
                    rule.generalIds.ifEmpty { listOf(rule.formationId) }.joinToString()
            )
        }
        if (config.deleteMailForSpeed) {
            when (val result = ctx.protocol.runDailyStep(ctx.session, DailyStep.DELETE_MAIL)) {
                is ProtocolResult.Ok -> {
                    if (!result.value.success) {
                        return TaskDecision.Stop("刷黄战后清理邮件失败：${result.value.message}")
                    }
                    ctx.shuaLog("post-return-delete-mail success message=${result.value.message}")
                }
                is ProtocolResult.Err -> return if (result.retryable) {
                    TaskDecision.RetryAfter(
                        ctx.behaviorContract.brushYellow.schedule.transientRetryMillis
                    )
                } else {
                    TaskDecision.Stop("刷黄战后清理邮件失败：${result.message}")
                }
            }
        }
        when (val cleared = ctx.protocol.clearBrushPendingRecovery(ctx.session)) {
            is ProtocolResult.Ok -> if (!cleared.value.success) {
                return TaskDecision.RetryAfter(
                    ctx.behaviorContract.brushYellow.schedule.transientRetryMillis,
                    "刷黄战后维护状态清理失败：${cleared.value.message}"
                )
            }
            is ProtocolResult.Err -> return if (cleared.retryable) {
                TaskDecision.RetryAfter(
                    ctx.behaviorContract.brushYellow.schedule.transientRetryMillis,
                    "刷黄战后维护状态清理待重试：${cleared.message}"
                )
            } else {
                TaskDecision.Stop("刷黄战后维护状态清理失败：${cleared.message}")
            }
        }
        ctx.runtime.removePendingBrushRecovery(
            ctx.session.accountId,
            type,
            pendingRecoveryGeneralIds
        )
        ctx.shuaLog("post-return-recovery-done wait-next-tick-for-refill-before-dispatch")
        return TaskDecision.Sleep(
            ctx.behaviorContract.brushYellow.schedule.postReturnMaintenanceDelayMillis
        )
    }

    private fun TaskContext.shuaLogDispatchDryRun(result: BattleResult) {
        ProtocolDiagnosticsReportBuilder.brushYellowWireSummary(result.raw)?.let { shuaLog(it) }
    }

    private fun runtimeTaskKey(): String = "account-$accountId:${type.name}"

    private fun BattleResult.failureMessage(): String =
        raw["message"]
            ?: raw["responseText"]
            ?: raw["response"]
            ?: raw["rawResponse"]
            ?: raw["bodyText"]
            ?: raw["error"]
            ?: "unknown dispatch failure"

    private fun BattleResult.isSoftDispatchReject(contract: ExpeditionBehaviorContract): Boolean {
        val message = failureMessage()
        val hex = raw["responseHex"] ?: raw["expeditionResponseHex"] ?: ""
        val softRejectHex = contract.softRejectPayload.joinToString("") {
            (it.toInt() and 0xff).toString(16).padStart(2, '0')
        }
        return message.contains(
            "0x${contract.dispatchResponseOpcode.toString(16)}=$softRejectHex",
            ignoreCase = true
        ) ||
            isMissingTargetDispatchReject(message) ||
            message.contains("游戏服拒绝出征") ||
            hex.equals(softRejectHex, ignoreCase = true)
    }

    /** Desktop parity: a disappeared map target invalidates only that target, not the task. */
    private fun isMissingTargetDispatchReject(message: String): Boolean = listOf(
        "目标不存在",
        "目标已不存在",
        "不能到达",
        "无法到达",
        "目标已消失",
        "目标消失",
        "目标被消灭",
        "目标已被消灭"
    ).any { marker -> message.contains(marker) }

    private fun chooseFormations(formations: List<FormationRuntime>, generals: List<General>): List<FormationRuntime> {
        val generalById = generals.associateBy { it.id }
        val configuredRules = config.rules.filter { it.enabled && it.generalIds.isNotEmpty() }
        if (configuredRules.isNotEmpty()) {
            return configuredRules.mapNotNull { rule ->
                val ids = rule.generalIds.filter { it > 0L }.distinct()
                if (ids.size != rule.generalIds.distinct().size || ids.any { it !in generalById }) {
                    return@mapNotNull null
                }
                val exact = formations.firstOrNull { formation ->
                    formation.generalIds.filter { it > 0L }.distinct() == ids
                }
                val formation = exact ?: FormationRuntime(
                    id = ids.first(),
                    name = "刷黄编队-${ids.joinToString("-")}",
                    generalIds = ids,
                    status = FormationRuntimeStatus.IDLE,
                    troopCount = ids.sumOf { generalById[it]?.troopLimit?.coerceAtLeast(1) ?: 1 },
                    raw = mapOf(
                        "source" to "desktop-brush-rule",
                        "generalIds" to ids.joinToString(",")
                    )
                )
                formation.takeIf { it.isDispatchableWith(generalById) }
            }
        }

        val selectedOrder = config.selectedFormationIds.toList()
        val selectedByFormationId = formations
            .asSequence()
            .filter { it.id in config.selectedFormationIds }
            .sortedBy { selectedOrder.indexOf(it.id).let { index -> if (index < 0) Int.MAX_VALUE else index } }
            .filter { it.isDispatchableWith(generalById) }
            .toList()

        // 手机端刷黄页保存的是“出征将领”真实 ID；在 recovered formationsJson /
        // 小黄点 SharedPreferences 里可能只有旧 slot/编队号，导致 selected=0。
        // 这里把选中的真实将领 ID 补成单将领编队，保证保存设置后能继续进入
        // 041540 找黄、5203 筛选、出征链路。
        val selectedAsGeneralFallback = selectedOrder
            .asSequence()
            .filterNot { selectedId -> selectedByFormationId.any { it.id == selectedId } }
            .mapNotNull { selectedId ->
                val general = generalById[selectedId] ?: return@mapNotNull null
                FormationRuntime(
                    id = selectedId,
                    name = "候选刷黄编队-${general.name.ifBlank { selectedId.toString() }}",
                    generalIds = listOf(selectedId),
                    status = FormationRuntimeStatus.IDLE,
                    troopCount = general.troopLimit,
                    raw = mapOf(
                        "source" to "scheduler-selected-general-fallback",
                        "generalId" to selectedId.toString()
                    )
                ).takeIf { it.isDispatchableWith(generalById) }
            }
            .toList()

        return (selectedByFormationId + selectedAsGeneralFallback)
            .sortedBy { selectedOrder.indexOf(it.id).let { index -> if (index < 0) Int.MAX_VALUE else index } }
    }

    private fun FormationRuntime.isDispatchableWith(generalById: Map<Long, General>): Boolean =
        canDispatch &&
            (troopCount == null || troopCount > 0) &&
            generalIds.isNotEmpty() &&
            generalIds.any { it in generalById } &&
            generalIds.all { generalId ->
                val general = generalById[generalId]
                general == null || (
                    (general.status == null || general.status == 0) &&
                        (general.energy == null || general.energy > 0) &&
                        general.isPeiBingFail != true
                    )
            }

    private fun chooseReservableExpedition(
        ctx: TaskContext,
        formations: List<FormationRuntime>,
        targets: List<MapTarget>
    ): Pair<FormationRuntime, MapTarget>? {
        for (formation in formations) {
            val target = chooseTargetForFormation(targets, formation) ?: continue
            val gate = ctx.runtime.commandGate.tryReserveFormationForDispatch(
                accountId = ctx.session.accountId,
                owner = type,
                taskKey = runtimeTaskKey(),
                formation = formation,
                nowMillis = ctx.nowMillis,
                reason = "brush-yellow selected target=${target.id}"
            )
            if (gate is com.example.dwpmclone.domain.state.GateResult.Allowed) return formation to target
        }
        return null
    }

    private fun chooseTargetForFormation(targets: List<MapTarget>, formation: FormationRuntime): MapTarget? {
        val filter = config.filterForFormation(formation)
        return targets
            .asSequence()
            .filter { it.matchesTargetType(config.targetType) }
            .filter { it.matchesFilter(filter) }
            .sortedWith(targetComparator())
            .firstOrNull()
    }

    private fun targetComparator(): Comparator<MapTarget> =
        compareBy(
            { it.coordinate.distanceSquared(config.start) },
            { it.rankForSelection() ?: Int.MAX_VALUE },
            { it.id }
        )

    private fun ShuaHuangConfig.filterForFormation(formation: FormationRuntime): ShuaHuangTargetFilter =
        rules.firstOrNull { rule ->
            val ids = rule.generalIds.filter { it > 0L }.distinct()
            rule.enabled && ids.isNotEmpty() && (
                ids == formation.generalIds.filter { it > 0L }.distinct() ||
                    (formation.generalIds.size == 1 && ids.first() == formation.id)
                )
        }?.targetFilter ?: if (formationFilterMode == FormationFilterMode.PER_FORMATION) {
            perFormationTargetFilters[formation.id] ?: targetFilter
        } else {
            targetFilter
        }

    private fun MapTarget.matchesTargetType(expected: HuangTargetType): Boolean {
        val accepted = when (expected) {
            HuangTargetType.SHAN_ZEI -> setOf("SHAN_ZEI", "山贼", "山賊")
            HuangTargetType.HUANG_JIN -> setOf("HUANG_JIN", "黄巾", "黃巾", "渠帅", "渠帥", "主将", "主將", "主帅", "主帥")
        }
        val values = listOf(type, raw["targetType"].orEmpty(), raw["type"].orEmpty(), raw["kind"].orEmpty())
        return values.any { value -> accepted.any { it.equals(value, ignoreCase = true) || value.contains(it) } }
    }

    private fun MapTarget.rankForSelection(): Int? =
        raw["rank"]?.toIntOrNull()
            ?: raw["level"]?.toIntOrNull()
            ?: raw["targetLevel"]?.toIntOrNull()

    private fun MapTarget.matchesFilter(filter: ShuaHuangTargetFilter): Boolean {
        val level = rankForSelection()
        if (!ShuaHuangTargetFilterPolicy.matchesLevel(level, filter)) return false
        if (filter.maxDistance != null && coordinate.distanceSquared(config.start) > filter.maxDistance * filter.maxDistance) return false
        if (!matchesCompositionFilter(filter)) return false
        val haystack = buildString {
            append(type)
            raw.values.forEach { value ->
                append(' ')
                append(value)
            }
        }
        if (filter.dropKeywords.isNotEmpty() && filter.dropKeywords.none { keyword -> keyword.isNotBlank() && haystack.contains(keyword, ignoreCase = true) }) return false
        if (filter.requiredKeywords.any { keyword -> keyword.isNotBlank() && !haystack.contains(keyword, ignoreCase = true) }) return false
        if (filter.blockedKeywords.any { keyword -> keyword.isNotBlank() && haystack.contains(keyword, ignoreCase = true) }) return false
        return true
    }

    private fun MapTarget.matchesCompositionFilter(filter: ShuaHuangTargetFilter): Boolean {
        if (
            filter.maxFoot == null && filter.maxBow == null && filter.maxCavalry == null &&
            filter.maxChariot == null && !filter.requireFoot
        ) return true
        val code = raw["compositionCode"]
            ?: raw["enemyCompositionCode"]
            ?: raw["步弓骑车"]
            ?: raw["bgbqc"]
        val byCode = code?.filter { it.isDigit() }?.takeIf { it.length >= 4 }?.let {
            listOf(it[0] - '0', it[1] - '0', it[2] - '0', it[3] - '0')
        }
        val foot = rawInt("foot", "footCount", "步", "步军", "infantry", "defenderFoot") ?: byCode?.get(0)
        val bow = rawInt("bow", "bowCount", "弓", "弓军", "archer", "ranged", "defenderBow") ?: byCode?.get(1)
        val cavalry = rawInt("cavalry", "cavalryCount", "骑", "骑军", "rider", "defenderCavalry") ?: byCode?.get(2)
        val chariot = rawInt("chariot", "chariotCount", "车", "车军", "car", "defenderChariot") ?: byCode?.get(3)
        val source = raw["compositionSource"].orEmpty()
        if (source == "level-template" || source == "unavailable") return false
        // Desktop rejects a target when a composition filter is configured but 0x8540
        // did not provide all four real unit counters. Do the same on Android.
        if (listOf(foot, bow, cavalry, chariot).any { it == null }) return false
        val actualFoot = foot ?: return false
        val actualBow = bow ?: return false
        val actualCavalry = cavalry ?: return false
        val actualChariot = chariot ?: return false
        if (filter.requireFoot && actualFoot <= 0) return false
        if (filter.maxFoot != null && actualFoot > filter.maxFoot) return false
        if (filter.maxBow != null && actualBow > filter.maxBow) return false
        if (filter.maxCavalry != null && actualCavalry > filter.maxCavalry) return false
        if (filter.maxChariot != null && actualChariot > filter.maxChariot) return false
        return true
    }

    private fun MapTarget.rawInt(vararg keys: String): Int? {
        for (key in keys) {
            raw[key]?.filter { it.isDigit() }?.takeIf { it.isNotBlank() }?.toIntOrNull()?.let { return it }
        }
        return null
    }

    private fun MapCoordinate.distanceSquared(other: MapCoordinate): Int {
        val dx = x - other.x
        val dy = y - other.y
        return dx * dx + dy * dy
    }
}

class MineTask(accountId: Long, config: MineConfig) :
    BaseAssistantTask<MineConfig>(accountId, if (config.backgroundSearch) TaskType.MINE_SEARCH else TaskType.AUTO_MINING, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled && !config.backgroundSearch) return TaskDecision.Stop("mine task disabled")
        val contract = ctx.behaviorContract.mine
        if (config.searchScope !in contract.allowedSearchScopes) {
            return TaskDecision.Stop("打矿搜索范围无效：${config.searchScope}")
        }
        if (config.maxMarchMinutes !in contract.allowedMaxMarchMinutes) {
            return TaskDecision.Stop("打矿最大行军时间无效：${config.maxMarchMinutes}")
        }
        if (config.rules.filter { it.enabled }.any {
                it.generalIds.distinct().size > contract.maximumGeneralsPerFormation
            }
        ) {
            return TaskDecision.Stop(
                "打矿一次最多选择${contract.maximumGeneralsPerFormation}名将领"
            )
        }
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        val mineContract = ctx.behaviorContract.mine
        val schedule = mineContract.schedule
        val enabledRules = config.rules.filter {
            it.enabled && it.generalIds.isNotEmpty()
        }
        val rule = enabledRules.getOrNull(
            ctx.localMap.nextMineRuleIndex(ctx.session.accountId, enabledRules.size)
        )
        val activeConfig = if (rule != null) {
            config.copy(
                start = rule.start,
                selectedMineTypes = setOf(rule.mineType),
                selectedFormationIds = rule.generalIds.toSet(),
                onlyEmptyMine = rule.onlyEmpty,
                onlyDefendedMine = rule.onlyDefended,
                searchScope = rule.scope,
                selectedLevels = rule.level?.let(::setOf) ?: emptySet(),
                formationRules = config.formationRules.forGenerals(rule.generalIds)
            )
        } else {
            config
        }
        MinePendingGarrison.fromJson(ctx.session.channelExtra["minePendingGarrisonJson"])
            ?.let { pending ->
                ctx.markMilitaryBusy(
                    type,
                    pending.generalIds,
                    "打矿已出征，正在等待驻守、撤防和回闲"
                )
                return resumePendingMineGarrison(ctx, pending)
            }
        if (mineContract.resourceCapacityCheckRequired && type != TaskType.MINE_SEARCH) {
            val monarch = when (val result = ctx.protocol.queryMonarch(ctx.session)) {
                is ProtocolResult.Ok -> result.value
                is ProtocolResult.Err -> return if (result.retryable) {
                    TaskDecision.RetryAfter(schedule.targetUnavailableRetryMillis)
                } else {
                    TaskDecision.Stop(result.message)
                }
            }
            val current = monarch.resourcePointCurrent
            val cap = monarch.resourcePointCap
            if (current != null && cap != null && cap > 0 && current >= cap) {
                return TaskDecision.Sleep(schedule.targetUnavailableRetryMillis)
            }
        }
        val cacheKey = MineCacheKey.from(ctx.session, activeConfig)
        val cachedMines = ctx.localMap.mines(cacheKey, ctx.nowMillis)
        val mines = if (cachedMines != null) {
            cachedMines
        } else {
            when (val result = ctx.protocol.searchMines(ctx.session, activeConfig)) {
                is ProtocolResult.Ok -> result.value.also {
                    ctx.localMap.saveMines(cacheKey, it, ctx.nowMillis)
                }
                is ProtocolResult.Err -> return if (result.retryable) {
                    TaskDecision.RetryAfter(schedule.targetUnavailableRetryMillis)
                } else {
                    TaskDecision.Stop(result.message)
                }
            }
        }
        if (type == TaskType.MINE_SEARCH) return TaskDecision.Sleep(activeConfig.searchIntervalMinutes * 60_000L)
        val selectedMine = MineTargetFilterPolicy.ordered(
            mines.filter {
                MineTargetFilterPolicy.matches(it, activeConfig, mineContract)
            },
            activeConfig.start
        ).firstOrNull() ?: run {
            ctx.localMap.clearMines(cacheKey)
            return TaskDecision.Sleep(schedule.targetUnavailableRetryMillis)
        }
        val mine = when (val revalidated = ctx.protocol.revalidateMineTarget(
            ctx.session,
            selectedMine,
            activeConfig
        )) {
            is ProtocolResult.Ok -> revalidated.value
            is ProtocolResult.Err -> {
                ctx.localMap.invalidateMine(
                    cacheKey,
                    selectedMine.id,
                    ctx.nowMillis,
                    "revalidation:${revalidated.code}"
                )
                return if (revalidated.retryable) {
                    TaskDecision.RetryAfter(schedule.targetUnavailableRetryMillis)
                } else {
                    TaskDecision.Stop(revalidated.message)
                }
            }
        }
        val generalIds = activeConfig.selectedFormationIds.toList()
        if (generalIds.isEmpty()) return TaskDecision.Stop("no formation selected")
        if (generalIds.distinct().size > mineContract.maximumGeneralsPerFormation) {
            return TaskDecision.Stop(
                "打矿一次最多选择${mineContract.maximumGeneralsPerFormation}名将领"
            )
        }
        ctx.claimMilitaryGenerals(type, generalIds, "打矿")?.let { return it }
        val refillDelegated = ctx.session.sourceMode == 1 &&
            ctx.session.channelExtra["unifiedExpeditionPreflight"].equals("true", ignoreCase = true)
        if (activeConfig.replenishTroops && !refillDelegated) {
            val refill = ctx.protocol.updateFormation(
                ctx.session,
                FormationConfig(
                    formationId = generalIds.first(),
                    generalIds = generalIds,
                    autoAssignTroops = false,
                    troopType = "",
                    troopCount = 0,
                    fillToMaxWhenAutoAssignDisabled = true
                )
            )
            when (refill) {
                is ProtocolResult.Err -> {
                    if (!refill.keepsShortMilitaryClaim()) ctx.releaseMilitaryClaim(type)
                    return if (refill.retryable) {
                        TaskDecision.RetryAfter(schedule.formationShortageRetryMillis, refill.message)
                    } else {
                        TaskDecision.Stop("打矿出征前批量补满失败：${refill.message}")
                    }
                }
                is ProtocolResult.Ok -> if (!refill.value.success) {
                    ctx.releaseMilitaryClaim(type)
                    return TaskDecision.Stop("打矿出征前批量补满失败：${refill.value.message}")
                }
            }
        }
        // 统一入口同时携带行军上限和该编队的保存配兵规则；
        // 默认 45 分钟也不能绕过出征前按任务修复配兵。
        val occupyResult = ctx.protocol.occupyMine(
            ctx.session,
            mine,
            generalIds,
            activeConfig.maxMarchMinutes,
            activeConfig.formationRules
        )
        val occupyStep = when (val occupy = occupyResult) {
            is ProtocolResult.Err -> {
                when {
                    occupy.isUncertainExpeditionSend() -> ctx.markMilitaryBusy(
                        type,
                        generalIds,
                        "打矿出征结果待服务器状态确认"
                    )
                    occupy.keepsShortMilitaryClaim() -> Unit
                    else -> ctx.releaseMilitaryClaim(type)
                }
                return if (occupy.retryable) {
                    TaskDecision.RetryAfter(schedule.targetUnavailableRetryMillis, occupy.message)
                }
                else TaskDecision.Stop(occupy.message)
            }
            is ProtocolResult.Ok -> {
                if (!occupy.value.success) {
                    ctx.releaseMilitaryClaim(type)
                    ctx.localMap.invalidateMine(cacheKey, mine.id, ctx.nowMillis, "occupy-rejected")
                    return TaskDecision.Sleep(schedule.targetUnavailableRetryMillis)
                }
                ctx.localMap.invalidateMine(cacheKey, mine.id, ctx.nowMillis, "occupy-accepted")
                occupy.value
            }
        }
        val battleId = occupyStep.raw["battleId"]
            ?.toLongOrNull()
            ?.takeIf { it > 0L }
            ?: run {
                ctx.markMilitaryBusy(
                    type,
                    generalIds,
                    "打矿回执缺少 battleId，冻结将领等待状态确认"
                )
                return TaskDecision.Stop(
                    "打矿已受理，但0x8522回执缺少有效 battleId，为避免误撤防已停止后续动作"
                )
            }
        ctx.markMilitaryBusy(type, generalIds, "打矿已出征，等待驻守和撤防")
        ctx.recordSuccess(
            "打矿",
            "出征 > ${mine.mineType.name}(${mine.coordinate.x}，${mine.coordinate.y})"
        )
        if (activeConfig.speed.enabledFlag()) {
            when (val speed = ctx.protocol.accelerateMineMarch(
                ctx.session,
                battleId,
                occupyStep.raw["marchSeconds"]?.toIntOrNull() ?: 0
            )) {
                is ProtocolResult.Ok -> ctx.runtime.emit(
                    "account=${ctx.session.accountId} owner=$type mine-speed " +
                        "success=${speed.value.success} message=${speed.value.message}"
                )
                is ProtocolResult.Err -> ctx.runtime.emit(
                    "account=${ctx.session.accountId} owner=$type mine-speed " +
                        "code=${speed.code} message=${speed.message}"
                )
            }
        }
        // Desktop mining always completes the same closed loop: wait for this exact
        // battleId to become a confirmed garrison, recall it, then wait for idle.
        return TaskDecision.Sleep(
            if (mineContract.withdraw.afterGarrisonRequired) {
                schedule.postDispatchPollMillis
            } else {
                schedule.postCycleSleepMillis
            }
        )
    }

    private suspend fun resumePendingMineGarrison(
        ctx: TaskContext,
        pending: MinePendingGarrison
    ): TaskDecision {
        val schedule = ctx.behaviorContract.mine.schedule
        val age = (ctx.nowMillis - pending.dispatchAtMillis).coerceAtLeast(0L)
        if (age > schedule.settlementTimeoutMillis) {
            ctx.protocol.clearMinePendingGarrison(ctx.session, pending.battleId)
            return TaskDecision.Stop(
                "打矿 battleId=${pending.battleId} 驻守闭环超时" +
                "${schedule.settlementTimeoutMillis / 60_000}分钟，未自动撤防"
            )
        }
        // Once 0x8526 has been accepted, the desktop worker stops issuing recalls and
        // only refreshes the selected generals until all of them return idle.
        if (pending.recallRequestedAtMillis > 0L) {
            return waitMineGeneralsIdle(ctx, pending, clearWhenAllIdle = true)
        }
        val snapshot = when (val result = ctx.protocol.queryMilitarySnapshot(ctx.session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return if (result.retryable) {
                TaskDecision.RetryAfter(DEFAULT_RETRY_MS)
            } else {
                TaskDecision.Stop("刷新打矿军情失败：${result.message}")
            }
        }
        val action = snapshot.actions.firstOrNull { it.battleId == pending.battleId }
        if (action != null) {
            if (pending.x != 0 && pending.y != 0 &&
                (action.x != pending.x || action.y != pending.y)
            ) {
                return TaskDecision.Stop(
                    "打矿 battleId=${pending.battleId} 军情坐标不匹配：" +
                        "(${action.x},${action.y}) ≠ (${pending.x},${pending.y})"
                )
            }
            if (action.generalIds.intersect(pending.generalIds.toSet()).isEmpty()) {
                return TaskDecision.Stop("打矿 battleId=${pending.battleId} 军情将领不匹配，已禁止撤防")
            }
            when (action.state) {
                "驻守" -> return withdrawConfirmedMineGarrison(ctx, pending)
                "返回" -> return waitMineGeneralsIdle(ctx, pending, clearWhenAllIdle = true)
                else -> return TaskDecision.Sleep(schedule.garrisonPollMillis)
            }
        }

        // No 0x8600 record yet: distinguish a still-busy march from a failed/finished
        // action using the fresh 0x8004 general state.  Never guess a recall target.
        return waitMineGeneralsIdle(
            ctx,
            pending,
            clearWhenAllIdle = age >= schedule.missingMilitaryGraceMillis
        )
    }

    private suspend fun withdrawConfirmedMineGarrison(
        ctx: TaskContext,
        pending: MinePendingGarrison
    ): TaskDecision = when (val withdraw = ctx.protocol.withdrawMineDefense(ctx.session, pending.battleId)) {
        is ProtocolResult.Err -> if (withdraw.retryable) {
            TaskDecision.RetryAfter(DEFAULT_RETRY_MS)
        } else {
            TaskDecision.Stop(withdraw.message)
        }
        is ProtocolResult.Ok -> if (withdraw.value.success) {
            TaskDecision.Sleep(ctx.behaviorContract.mine.schedule.garrisonPollMillis)
        } else {
            TaskDecision.Stop(withdraw.value.message)
        }
    }

    private suspend fun waitMineGeneralsIdle(
        ctx: TaskContext,
        pending: MinePendingGarrison,
        clearWhenAllIdle: Boolean = false
    ): TaskDecision {
        val generals = when (val result = ctx.protocol.queryGenerals(ctx.session)) {
            is ProtocolResult.Ok -> result.value.filter { it.id in pending.generalIds }
            is ProtocolResult.Err -> return if (result.retryable) {
                TaskDecision.RetryAfter(DEFAULT_RETRY_MS)
            } else {
                TaskDecision.Stop("刷新打矿将领状态失败：${result.message}")
            }
        }
        if (generals.size == pending.generalIds.size && generals.all { it.status == 0 }) {
            if (clearWhenAllIdle) {
                ctx.protocol.clearMinePendingGarrison(ctx.session, pending.battleId)
                ctx.releaseMilitaryTask(type)
                return TaskDecision.Sleep(ctx.behaviorContract.mine.schedule.postCycleSleepMillis)
            }
        }
        return TaskDecision.Sleep(ctx.behaviorContract.mine.schedule.garrisonPollMillis)
    }

    private fun String.enabledFlag(): Boolean =
        trim().lowercase() !in setOf("", "不加速", "false", "0", "off")
}

class InventoryCleanupTask(accountId: Long, config: InventoryConfig) :
    BaseAssistantTask<InventoryConfig>(accountId, TaskType.INVENTORY, config) {
    private val keyRequirements = mapOf(
        "青铜宝箱" to "青铜钥匙",
        "精铁宝箱" to "精铁钥匙"
    )

    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled) return TaskDecision.Stop("inventory cleanup disabled")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        val items = when (val result = ctx.protocol.queryInventory(ctx.session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
        }
        val available = items.groupingBy { it.name }.fold(0) { total, item -> total + item.count }
            .toMutableMap()
        var opened = 0
        for (item in items) {
            val action = chooseInventoryAction(item) ?: continue
            if (action == InventoryAction.OPEN) {
                val keyName = keyRequirements[item.name]
                val usableCount = minOf(
                    item.count,
                    keyName?.let { available[it] ?: 0 } ?: item.count,
                    (50 - opened).coerceAtLeast(0)
                )
                if (usableCount <= 0) continue
                val actionResult = ctx.protocol.useOrDiscardItem(
                    ctx.session, item.id, InventoryAction.OPEN, count = usableCount
                )
                val decision = actionResult.asConfirmedStepDecision(
                    emptyFailureMessage = "服务器未确认背包动作成功"
                )
                if (decision is TaskDecision.Stop || decision is TaskDecision.RetryAfter) return decision
                val actualOpened = if (
                    ctx.session.channelExtra["inventoryLiveRefreshAllowed"]
                        .equals("true", ignoreCase = true)
                ) {
                    val refreshed = when (val result = ctx.protocol.queryInventory(ctx.session)) {
                        is ProtocolResult.Ok -> result.value
                        is ProtocolResult.Err -> return if (result.retryable) {
                            TaskDecision.RetryAfter(DEFAULT_RETRY_MS)
                        } else {
                            TaskDecision.Stop(result.message)
                        }
                    }
                    val latest = refreshed.groupingBy { it.name }
                        .fold(0) { total, current -> total + current.count }
                    val consumed = ((available[item.name] ?: item.count) - (latest[item.name] ?: 0))
                        .coerceIn(0, usableCount)
                    if (consumed <= 0) {
                        return TaskDecision.Stop("服务器回执成功，但背包数量未减少")
                    }
                    available.clear()
                    available.putAll(latest)
                    consumed
                } else {
                    usableCount.also {
                        available[item.name] = (available[item.name] ?: item.count) - it
                        if (keyName != null) available[keyName] = (available[keyName] ?: 0) - it
                    }
                }
                opened += actualOpened
                val message = (actionResult as? ProtocolResult.Ok)?.value?.message.orEmpty()
                ctx.recordSuccess(
                    "开箱",
                    "${item.name}${if (actualOpened > 1) " ×$actualOpened" else ""}" +
                        message.takeIf { it.isNotBlank() }?.let { " → $it" }.orEmpty()
                )
            } else {
                val actionResult = ctx.protocol.useOrDiscardItem(
                    ctx.session, item.id, action, count = item.count
                )
                val decision = actionResult.asConfirmedStepDecision(
                    emptyFailureMessage = "服务器未确认背包动作成功"
                )
                if (decision is TaskDecision.Stop || decision is TaskDecision.RetryAfter) return decision
                ctx.recordSuccess(
                    if (action == InventoryAction.DISCARD_EQUIPMENT) "丢弃装备" else "丢弃物品",
                    "${item.name} x${item.count}"
                )
            }
        }
        return TaskDecision.Sleep(60 * 60 * 1000L)
    }

    private fun chooseInventoryAction(item: InventoryItem): InventoryAction? {
        if (InventoryAutoOpenPolicy.shouldOpen(
                itemName = item.name,
                itemType = item.type,
                selectedNames = config.autoOpenItemNames,
                openBoxes = config.openBoxes,
                openSilverTickets = config.openSilverTickets
            )
        ) return InventoryAction.OPEN
        if (item.type == "equipment") {
            val maximumLevel = config.discardBelowLevel ?: return null
            if (config.discardEquipmentQualities.isEmpty()) return null
            if (!item.equipmentMetadataComplete || item.id <= 0L) return null
            if (item.famous || item.enhanced || item.equipped || item.extraText.isNotBlank()) return null
            val level = item.level ?: return null
            val quality = item.quality ?: return null
            if (level >= 80 || level >= maximumLevel) return null
            if (quality !in config.discardEquipmentQualities) return null
            return InventoryAction.DISCARD_EQUIPMENT
        }
        if (item.name in config.discardItems) return InventoryAction.DISCARD
        return null
    }
}

/** Idle-lane copper-floor maintenance shared by building and military prerequisites. */
class FoodToCopperTask(accountId: Long, config: FoodToCopperConfig) :
    BaseAssistantTask<FoodToCopperConfig>(accountId, TaskType.FOOD_TO_COPPER, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled) return TaskDecision.Stop("粮食转铜未启用")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        val before = when (val result = ctx.protocol.queryResourceState(ctx.session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return if (result.retryable) {
                TaskDecision.RetryAfter(DEFAULT_RETRY_MS, "粮食转铜读取资源失败：${result.message}")
            } else {
                TaskDecision.Stop("粮食转铜读取资源失败：${result.message}")
            }
        }
        val floor = config.copperFloorWan * 10_000L
        if (before.copper >= floor) {
            return TaskDecision.Sleep(config.pollMillis, reason = "铜钱已达到保底${config.copperFloorWan}万")
        }
        return when (val result = ctx.protocol.convertFoodToCopper(
            ctx.session,
            ConvertMode.FOOD_TO_COPPER_THRESHOLD
        )) {
            is ProtocolResult.Ok -> {
                if (result.value.copper > before.copper) {
                    ctx.recordSuccess(
                        "粮食转铜",
                        "消耗${(before.food - result.value.food).coerceAtLeast(0L)}粮，" +
                            "增加${result.value.copper - before.copper}铜"
                    )
                }
                if (result.value.copper >= floor) {
                    TaskDecision.Sleep(config.pollMillis, reason = "粮食转铜已达到保底${config.copperFloorWan}万")
                } else {
                    TaskDecision.RetryAfter(config.pollMillis, "本次兑换后铜钱仍低于保底${config.copperFloorWan}万")
                }
            }
            is ProtocolResult.Err -> if (result.retryable) {
                TaskDecision.RetryAfter(DEFAULT_RETRY_MS, "粮食转铜失败：${result.message}")
            } else {
                TaskDecision.Stop("粮食转铜失败：${result.message}")
            }
        }
    }
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

class FormationUpdateTask(accountId: Long, config: FormationConfig) :
    BaseAssistantTask<FormationConfig>(accountId, TaskType.FORMATION, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (config.generalIds.isEmpty()) return TaskDecision.Stop("no generals selected")
        if (config.autoAssignTroops && config.troopCount <= 0) return TaskDecision.Stop("troop count must be positive")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision =
        when (val result = ctx.protocol.updateFormation(ctx.session, config)) {
            is ProtocolResult.Ok -> {
                if (result.value.success) {
                    TaskDecision.Sleep(ctx.behaviorContract.formation.completedSleepMillis)
                } else {
                    ctx.runtime.emit(
                        "account=${ctx.session.accountId} owner=$type formation-update failed: ${result.value.message}; stop before brush-yellow dispatch"
                    )
                    TaskDecision.Stop(result.value.message)
                }
            }
            is ProtocolResult.Err -> {
                if (result.retryable) {
                    TaskDecision.RetryAfter(DEFAULT_RETRY_MS)
                } else {
                    // 配兵是刷黄/出征的安全前置条件。真实 0x1226/0x1229 未获得完整
                    // 0x8226/0x8229 确认时必须失败关闭，不能继续带着未知兵力出征。
                    TaskDecision.Stop(result.message)
                }
            }
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
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled) return TaskDecision.Stop("dungeon disabled")
        val contract = ctx.behaviorContract.dungeon
        if (config.dailyTimes <= 0) return TaskDecision.Stop("daily dungeon times must be positive")
        if (config.formationIds.isEmpty()) return TaskDecision.Stop("no dungeon formation selected")
        if (config.formationIds.distinct().size > contract.maximumGeneralsPerFormation) {
            return TaskDecision.Stop(
                "dungeon supports at most ${contract.maximumGeneralsPerFormation} generals"
            )
        }
        if (config.mode !in contract.allowedModes) {
            return TaskDecision.Stop("unsupported dungeon mode: ${config.mode}")
        }
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        val completedToday = ctx.runtime.persistedDailySuccessCount(
            ctx.session.accountId,
            type,
            ctx.nowMillis
        )
        if (completedToday >= config.dailyTimes) {
            ctx.releaseMilitaryTask(type)
            return TaskDecision.Sleep(
                millisUntilNextChinaDay(
                    ctx.nowMillis,
                    ctx.behaviorContract.timezoneId
                )
            )
        }
        val selectedGeneralIds = config.formationIds.filter { it > 0L }.distinct()
        ctx.claimMilitaryGenerals(type, selectedGeneralIds, "副本")?.let { return it }
        return when (val result = ctx.protocol.runDungeon(ctx.session, config)) {
            is ProtocolResult.Err -> {
                when {
                    result.isUncertainExpeditionSend() -> ctx.markMilitaryBusy(
                        type,
                        selectedGeneralIds,
                        "副本出征结果待服务器状态确认"
                    )
                    result.keepsShortMilitaryClaim() -> Unit
                    else -> ctx.releaseMilitaryClaim(type)
                }
                ctx.prompt(type, "副本执行失败：${result.message}")
                if (result.retryable) {
                    TaskDecision.RetryAfter(DEFAULT_RETRY_MS, result.message)
                } else {
                    TaskDecision.Stop(result.message)
                }
            }
            is ProtocolResult.Ok -> {
                if (!result.value.success) {
                    ctx.releaseMilitaryTask(type)
                    TaskDecision.Stop(result.value.message)
                } else {
                    val completed = result.value.raw["phase"] in setOf(
                        "chest-opened",
                        "settlement-recovered"
                    ) ||
                        (ctx.session.sourceMode != 1 && result.value.raw["phase"].isNullOrBlank())
                    if (completed) {
                        ctx.runtime.recordDailySuccess(
                            ctx.session.accountId,
                            type,
                            count = 1,
                            nowMillis = ctx.nowMillis
                        )
                        val chapter = result.value.raw["chapter"]?.toIntOrNull()?.plus(1)
                        val stage = result.value.raw["stage"]?.toIntOrNull()
                        ctx.recordSuccess(
                            "副本",
                            if (chapter != null && stage != null) {
                                "第${chapter}章第${stage}关 > ${result.value.message}"
                            } else {
                                result.value.message
                            }
                        )
                    }
                    val phase = result.value.raw["phase"]
                    when (phase) {
                        "fighting" -> ctx.markMilitaryBusy(
                            type,
                            selectedGeneralIds,
                            "副本已出征，等待战斗、回闲与开箱"
                        )
                        "chest-opened", "settlement-recovered", "all-clear",
                        "defeat-paused", "clear-unconfirmed", "clear-confirmation-missing" ->
                            ctx.releaseMilitaryTask(type)
                        else -> ctx.releaseMilitaryClaim(type)
                    }
                    TaskDecision.Sleep(
                        millis = result.value.raw["nextDelayMillis"]
                            ?.toLongOrNull()
                            ?.coerceIn(500L, 24 * 60 * 60 * 1000L)
                            ?: when (phase) {
                                "fighting" -> ctx.behaviorContract.dungeon.schedule.postLaunchPollMillis
                                else -> ctx.behaviorContract.dungeon.schedule.dailyDonePollMillis
                            },
                        keepRunning = phase == "fighting",
                        reason = result.value.message
                    )
                }
            }
        }
    }
}

class LosslessTask(accountId: Long, config: LosslessConfig) :
    BaseAssistantTask<LosslessConfig>(accountId, TaskType.LOSSLESS, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled) return TaskDecision.Stop("lossless disabled")
        val contract = ctx.behaviorContract.lossless
        if (config.dailyLimit !in 1..contract.serverDailyLimit) {
            return TaskDecision.Stop("lossless daily limit must be 1..${contract.serverDailyLimit}")
        }
        val enabledRules = config.rules.filter { it.enabled }
        if (enabledRules.isEmpty()) return TaskDecision.Stop("no lossless rule enabled")
        if (enabledRules.any { it.generalIds.isEmpty() }) return TaskDecision.Stop("lossless general missing")
        if (enabledRules.any { it.generalIds.size > contract.maximumGeneralsPerFormation }) {
            return TaskDecision.Stop(
                "lossless rule supports at most ${contract.maximumGeneralsPerFormation} generals"
            )
        }
        if (enabledRules.any { it.level !in contract.minimumLevel..contract.maximumLevel }) {
            return TaskDecision.Stop(
                "lossless level must be ${contract.minimumLevel}..${contract.maximumLevel}"
            )
        }
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        val enabledRules = config.rules.filter { it.enabled }
        val ruleIndex = ctx.runtime.residentRuleIndex(ctx.session.accountId, type, enabledRules.size)
        val rule = enabledRules[ruleIndex]
        val activeConfig = config.copy(
            rules = listOf(rule),
            formationRules = config.formationRules.forGenerals(rule.generalIds)
        )
        ctx.claimMilitaryGenerals(type, rule.generalIds, "无损")?.let { return it }
        return when (val result = ctx.protocol.runLossless(ctx.session, activeConfig)) {
            is ProtocolResult.Err -> {
                when {
                    result.isUncertainExpeditionSend() -> ctx.markMilitaryBusy(
                        type,
                        rule.generalIds,
                        "无损出征结果待服务器状态确认"
                    )
                    result.keepsShortMilitaryClaim() -> Unit
                    else -> ctx.releaseMilitaryClaim(type)
                }
                if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS, result.message)
                else TaskDecision.Stop(result.message)
            }
            is ProtocolResult.Ok -> {
                // SessionAwareGameProtocolClient uses the server's remaining-attempt field
                // as the authoritative daily counter. Never suppress status/settlement
                // polling just because an earlier dispatch consumed the configured limit.
                if (result.value.success) {
                    val phase = result.value.raw["phase"]
                    if (result.value.raw["attemptConsumed"].equals("true", ignoreCase = true)) {
                        ctx.recordSuccess("无损", result.value.message)
                    }
                    when (phase) {
                        "fighting" -> ctx.markMilitaryBusy(
                            type,
                            rule.generalIds,
                            "无损战斗中，等待结算"
                        )
                        "settled" -> {
                            ctx.releaseMilitaryTask(type)
                            ctx.runtime.advanceResidentRule(
                                ctx.session.accountId,
                                type,
                                enabledRules.size
                            )
                        }
                        "cooldown", "daily-done", "configured-daily-limit" ->
                            ctx.releaseMilitaryTask(type)
                        else -> ctx.releaseMilitaryClaim(type)
                    }
                    TaskDecision.Sleep(
                        result.value.raw["nextDelayMillis"]
                            ?.toLongOrNull()
                            ?.coerceIn(1_000L, 24 * 60 * 60 * 1000L)
                            ?: 60_000L
                    )
                } else {
                    ctx.releaseMilitaryClaim(type)
                    TaskDecision.Stop(result.value.message)
                }
            }
        }
    }
}

class AutoLootTask(accountId: Long, config: AutoLootConfig) :
    BaseAssistantTask<AutoLootConfig>(accountId, TaskType.AUTO_LOOT, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        config.preparationError()?.let { return TaskDecision.Stop(it) }
        if (config.enabledRules().any {
                it.generalIds.distinct().size > ctx.behaviorContract.raid.maximumGeneralsPerFormation
            }
        ) {
            return TaskDecision.Stop(
                "掠夺一次最多选择" +
                    "${ctx.behaviorContract.raid.maximumGeneralsPerFormation}名将领"
            )
        }
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        val enabledRules = config.enabledRules()
        val ruleIndex = ctx.runtime.residentRuleIndex(ctx.session.accountId, type, enabledRules.size)
        val rule = enabledRules[ruleIndex]
        val activeConfig = config.copy(
            selectedFormationIds = rule.generalIds.toSet(),
            targetPlayerName = rule.playerName,
            targetFiefIndex = rule.fiefIndex,
            rules = listOf(rule),
            formationRules = config.formationRules.forGenerals(rule.generalIds)
        )
        ctx.claimMilitaryGenerals(type, rule.generalIds, "掠夺")?.let { return it }
        return when (val result = ctx.protocol.runAutoLoot(ctx.session, activeConfig)) {
            is ProtocolResult.Err -> {
                when {
                    result.isUncertainExpeditionSend() -> ctx.markMilitaryBusy(
                        type,
                        rule.generalIds,
                        "掠夺出征结果待服务器状态确认"
                    )
                    result.keepsShortMilitaryClaim() -> Unit
                    else -> ctx.releaseMilitaryClaim(type)
                }
                if (result.retryable) {
                    TaskDecision.RetryAfter(
                        ctx.behaviorContract.raid.busyGeneralPollMillis,
                        result.message
                    )
                } else {
                    TaskDecision.Stop(result.message)
                }
            }
            is ProtocolResult.Ok -> {
                if (!result.value.success) {
                    ctx.releaseMilitaryClaim(type)
                    TaskDecision.Stop(result.value.message)
                } else {
                    // Existing account refresh updates general state; once the selected
                    // generals return idle the next scheduler step launches another raid.
                    if (result.value.raw["phase"] == "launched") {
                        ctx.recordSuccess("掠夺", result.value.message)
                        ctx.markMilitaryBusy(type, rule.generalIds, "掠夺已出征，等待将领回闲")
                        ctx.runtime.advanceResidentRule(
                            ctx.session.accountId,
                            type,
                            enabledRules.size
                        )
                    } else {
                        ctx.releaseMilitaryClaim(type)
                    }
                    TaskDecision.Sleep(ctx.behaviorContract.raid.postDispatchPollMillis)
                }
            }
        }
    }
}

class SixMinistriesTask(accountId: Long, config: SixMinistriesConfig) :
    BaseAssistantTask<SixMinistriesConfig>(accountId, TaskType.SIX_MINISTRIES, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        config.preparationError()?.let { return TaskDecision.Stop(it) }
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision =
        when (val result = ctx.protocol.runSixMinistries(ctx.session, config)) {
            is ProtocolResult.Ok -> {
                if (!result.value.success) {
                    ctx.prompt(type, "六部本轮未完成：${result.value.message}")
                } else if (result.value.raw["phase"] == "planted") {
                    ctx.recordSuccess("六部", "种菜 > ${result.value.message}")
                }
                TaskDecision.Sleep(ctx.behaviorContract.scheduler.ministryPollMillis)
            }
            is ProtocolResult.Err -> {
                ctx.prompt(type, "六部本轮失败：${result.message}")
                TaskDecision.RetryAfter(ctx.behaviorContract.scheduler.ministryPollMillis)
            }
        }
}

/** Independent desktop-style observation loop for role, generals, armies and military intel. */
class StateRefreshTask(accountId: Long) :
    BaseAssistantTask<Unit>(accountId, TaskType.STATE_REFRESH, Unit) {
    override suspend fun step(ctx: TaskContext): TaskDecision {
        val generals = when (val result = ctx.protocol.queryGenerals(ctx.session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return TaskDecision.RetryAfter(
                DEFAULT_RETRY_MS,
                "更新角色将领数据失败：${result.message}"
            )
        }
        val formations = when (val result = ctx.protocol.queryFormations(ctx.session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return TaskDecision.RetryAfter(
                DEFAULT_RETRY_MS,
                "更新编队状态失败：${result.message}"
            )
        }
        ctx.runtime.commandGate.reconcileServerState(
            ctx.session.accountId,
            generals,
            formations,
            ctx.nowMillis
        )
        when (val military = ctx.protocol.queryMilitarySnapshot(ctx.session)) {
            is ProtocolResult.Ok -> ctx.runtime.emit(
                "account=${ctx.session.accountId} observation-refresh " +
                    "generals=${generals.size} formations=${formations.size} " +
                    "militaryActions=${military.value.actions.size}"
            )
            is ProtocolResult.Err -> ctx.runtime.emit(
                "account=${ctx.session.accountId} observation-refresh military-intel " +
                    "code=${military.code} message=${military.message}"
            )
        }
        return TaskDecision.Sleep(ctx.behaviorContract.accountLifecycle.heartbeatIntervalMillis)
    }
}

class AlarmTask(accountId: Long, config: AlarmConfig) :
    BaseAssistantTask<AlarmConfig>(accountId, TaskType.ALARM, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled) return TaskDecision.Stop("alarm scan disabled")
        if (config.incomingEnabled && config.keywords.isEmpty()) {
            return TaskDecision.Stop("alarm keywords empty")
        }
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision =
        ctx.protocol.scanAlarms(ctx.session, config).asConfirmedStepDecision(
            success = TaskDecision.Sleep(30_000),
            emptyFailureMessage = "服务器未确认警报扫描成功"
        )
}
