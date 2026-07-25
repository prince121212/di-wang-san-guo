package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.*
import com.example.dwpmclone.domain.cloud.CloudMapResult
import com.example.dwpmclone.domain.cloud.CloudMapKind

private data class PendingCloudExpedition(
    val kind: CloudMapKind,
    val targetId: Long,
    val acceptedRevision: String,
    val success: Boolean,
    val message: String,
    val raw: Map<String, String>
)

/**
 * Mock task implementations derived from static UI evidence.
 *
 * These classes intentionally express task sequencing only. They do not embed original
 * game protocol endpoints, request parameters, token extraction, signing or encryption.
 */
abstract class BaseMockTask<Cfg>(
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
    BaseMockTask<DailyConfig>(accountId, TaskType.DAILY, config) {
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
 * First real-function migration skeleton: 登录/session 已由 scheduler 外部提供，
 * 单步闭环按“小黄点刷黄”目标收敛为：
 * validate session -> query role/resource -> query generals/formations -> find target -> dispatch.
 *
 * Concrete opcodes/payloads still belong behind GameProtocolClient implementations that are
 * restored from reverse evidence. This task only owns sequencing, guards and stop decisions.
 */
class ShuaHuangTask(accountId: Long, config: ShuaHuangConfig) :
    BaseMockTask<ShuaHuangConfig>(accountId, TaskType.SHUA_HUANG, config) {
    private var deleteMailCompletedDay: Int? = null
    private var pendingCloudExpedition: PendingCloudExpedition? = null
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled) return TaskDecision.Stop("auto shua huang disabled")
        if (config.dailyLimit <= 0) return TaskDecision.Stop("shua huang daily limit must be positive")
        if (config.selectedFormationIds.isEmpty()) return TaskDecision.Stop("no formation selected")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        flushPendingCloudExpedition(ctx)?.let { return it }
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
            val wait = millisUntilNextDailyStart(ctx.nowMillis, config.startHour)
            ctx.shuaLog("daily-limit reached used=$usedCount limit=${config.dailyLimit}; keep-resident waitMillis=$wait")
            return TaskDecision.Sleep(wait)
        }
        val waitForStart = millisUntilConfiguredStart(ctx.nowMillis, config.startHour)
        if (waitForStart > 0L) {
            ctx.shuaLog("scheduled startHour=${config.startHour} waitMillis=$waitForStart")
            return TaskDecision.Sleep(waitForStart)
        }

        ctx.shuaLog("refresh-monarch")
        val monarchDecision = ctx.protocol.queryMonarch(ctx.session).asDecision()
        if (monarchDecision is TaskDecision.Stop || monarchDecision is TaskDecision.RetryAfter) return monarchDecision

        ctx.shuaLog("refresh-resource")
        val resources = when (val result = ctx.protocol.queryResourceState(ctx.session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
        }
        val minimumCopper = config.minCopperWan * 10_000L
        ctx.shuaLog("resource copper=${resources.copper} food=${resources.food} minCopper=$minimumCopper")
        if (minimumCopper > 0 && resources.copper < minimumCopper) {
            if (!config.autoConvertFoodToCopper) return TaskDecision.Stop("copper below configured reserve: ${resources.copper} < $minimumCopper")
            val convertedResources = when (val result = ctx.protocol.convertFoodToCopper(ctx.session, ConvertMode.FOOD_TO_COPPER_THRESHOLD)) {
                is ProtocolResult.Ok -> result.value
                is ProtocolResult.Err -> return if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
            }
            if (convertedResources.copper < minimumCopper) {
                return TaskDecision.Stop("copper still below configured reserve after food conversion: ${convertedResources.copper} < $minimumCopper")
            }
        }

        val deleteMailDecision = runDeleteMailForSpeedIfNeeded(ctx)
        if (deleteMailDecision is TaskDecision.Stop || deleteMailDecision is TaskDecision.RetryAfter) return deleteMailDecision

        ctx.shuaLog("query-generals")
        val generals = when (val result = ctx.protocol.queryGenerals(ctx.session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
        }
        ctx.shuaLog("generals total=${generals.size} idle=${generals.count { it.status == null || it.status == 0 }}")
        if (generals.isEmpty()) return TaskDecision.Stop("no generals available for shua huang")

        ctx.shuaLog("query-formations")
        val formations = when (val result = ctx.protocol.queryFormations(ctx.session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
        }
        ctx.shuaLog("formations total=${formations.size} selected=${formations.count { it.id in config.selectedFormationIds }}")
        ctx.runtime.commandGate.reconcileServerState(ctx.session.accountId, generals, formations, ctx.nowMillis)
        if (realBrushGate && runPendingRecoveryIfReturned(ctx, generals)) {
            ctx.shuaLog("post-return-recovery-done wait-next-tick-for-refill-before-dispatch")
            return TaskDecision.Sleep(1_000)
        }
        if (usedCount >= config.dailyLimit) {
            val wait = millisUntilNextDailyStart(ctx.nowMillis, config.startHour)
            ctx.shuaLog("daily-limit reached after-recovery used=$usedCount limit=${config.dailyLimit}; waitMillis=$wait")
            return TaskDecision.Sleep(wait)
        }
        val candidateFormations = chooseFormations(formations, generals)
        ctx.shuaLog("candidate-formations=${candidateFormations.joinToString { it.id.toString() }.ifBlank { "none" }}")
        if (candidateFormations.isEmpty()) return TaskDecision.Sleep(30_000)

        ctx.shuaLog("search-target start=${config.start.x},${config.start.y} type=${config.targetType}")
        val targets = when (val result = ctx.protocol.searchMap(ctx.session, config.start, MapSearchPolicy(targetType = config.targetType))) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
        }
        ctx.shuaLog("targets-local total=${targets.size} matched=${targets.count { it.matchesTargetType(config.targetType) }}")
        val cloudTargets = when (val result = ctx.cloudMap.selectBanditTargets(
            session = ctx.session,
            observed = targets,
            start = config.start,
            targetType = config.targetType,
            nowMillis = ctx.nowMillis
        )) {
            is CloudMapResult.Ok -> result.value
            is CloudMapResult.Err -> {
                ctx.shuaLog("cloud-map blocked code=${result.code} message=${result.message}")
                return if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
            }
        }
        ctx.shuaLog("targets-cloud-recommended=${cloudTargets.size}")
        val (formation, target) = chooseReservableExpedition(ctx, candidateFormations, cloudTargets) ?: run {
            ctx.shuaLog("no-reservable-expedition wait=30000")
            return TaskDecision.Sleep(30_000)
        }
        ctx.shuaLog("selected formation=${formation.id} target=${target.id} coord=${target.coordinate.x},${target.coordinate.y} type=${target.type}")
        if (config.replenishTroops && (realBrushGate || ctx.session.sourceMode != 1)) {
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
                        TaskDecision.RetryAfter(DEFAULT_RETRY_MS)
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
            ctx.shuaLog("pre-dispatch-batch-refill skipped: real brush action gate not active")
        }
        ctx.runtime.commandGate.markDispatchSending(ctx.session.accountId, type, runtimeTaskKey(), formation.id, ctx.nowMillis)
        return when (val dispatch = ctx.protocol.dispatchFormation(ctx.session, formation.id, target)) {
            is ProtocolResult.Ok -> {
                if (!dispatch.value.success) {
                    val failureMessage = dispatch.value.failureMessage()
                    ctx.shuaLog("dispatch-failed formation=${formation.id} target=${target.id} message=$failureMessage")
                    ctx.shuaLogDispatchDryRun(dispatch.value)
                    ctx.runtime.commandGate.releaseReservation(ctx.session.accountId, type, runtimeTaskKey())
                    val next = if (dispatch.value.isSoftDispatchReject()) {
                        ctx.shuaLog("dispatch-rejected-soft target=${target.id} wait=30000 continue-search-next-tick")
                        TaskDecision.Sleep(30_000)
                    } else {
                        TaskDecision.Stop("shua huang dispatch failed: $failureMessage")
                    }
                    reportCloudExpedition(
                        ctx,
                        target,
                        success = false,
                        message = failureMessage,
                        raw = dispatch.value.raw,
                        next = next
                    )
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
                    ctx.shuaLogDispatchDryRun(dispatch.value)
                    val pendingAfterDispatch = realBrushGate && formation.generalIds.isNotEmpty()
                    if (realBrushGate) {
                        ctx.runtime.addPendingBrushRecovery(ctx.session.accountId, type, formation.generalIds)
                        ctx.shuaLog("post-dispatch-recovery-pending generals=${formation.generalIds.joinToString()} wait-return-before-heal")
                    } else {
                        formation.generalIds.forEach { generalId ->
                            when (val heal = ctx.protocol.healGeneral(ctx.session, generalId)) {
                                is ProtocolResult.Ok -> ctx.shuaLog("post-dispatch-heal general=$generalId success=${heal.value.success} message=${heal.value.message}")
                                is ProtocolResult.Err -> ctx.shuaLog("post-dispatch-heal skipped/error general=$generalId code=${heal.code} message=${heal.message}")
                            }
                        }
                    }
                    val totalUsedAfterDispatch = usedCount + consumed
                    val next = if (totalUsedAfterDispatch >= config.dailyLimit) {
                        if (pendingAfterDispatch) {
                            ctx.shuaLog("daily-limit reached after dispatch; wait-return-before-stop used=$totalUsedAfterDispatch limit=${config.dailyLimit}")
                            TaskDecision.Sleep(30_000)
                        } else {
                            val wait = millisUntilNextDailyStart(ctx.nowMillis, config.startHour)
                            ctx.shuaLog(
                                "daily-limit reached after-dispatch used=$totalUsedAfterDispatch " +
                                    "limit=${config.dailyLimit}; keep-resident waitMillis=$wait"
                            )
                            TaskDecision.Sleep(wait)
                        }
                    } else {
                        TaskDecision.Sleep(if (realBrushGate) 30_000 else 1_000)
                    }
                    reportCloudExpedition(
                        ctx,
                        target,
                        success = true,
                        message = dispatch.value.raw["message"] ?: "刷黄出征成功",
                        raw = dispatch.value.raw,
                        next = next
                    )
                }
            }
            is ProtocolResult.Err -> {
                ctx.shuaLog("dispatch-error formation=${formation.id} target=${target.id} code=${dispatch.code} message=${dispatch.message}")
                ctx.runtime.commandGate.releaseReservation(ctx.session.accountId, type, runtimeTaskKey())
                reportCloudExpedition(
                    ctx,
                    target,
                    success = false,
                    message = "${dispatch.code}: ${dispatch.message}",
                    raw = emptyMap(),
                    next = if (dispatch.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(dispatch.message)
                )
            }
        }
    }

    private suspend fun reportCloudExpedition(
        ctx: TaskContext,
        target: MapTarget,
        success: Boolean,
        message: String,
        raw: Map<String, String>,
        next: TaskDecision
    ): TaskDecision {
        pendingCloudExpedition = PendingCloudExpedition(
            kind = CloudMapKind.BANDIT,
            targetId = target.id,
            acceptedRevision = target.raw["cloudRevision"].orEmpty(),
            success = success,
            message = message,
            raw = raw
        )
        return flushPendingCloudExpedition(ctx) ?: next
    }

    private suspend fun flushPendingCloudExpedition(ctx: TaskContext): TaskDecision? {
        val pending = pendingCloudExpedition ?: return null
        return when (val report = ctx.cloudMap.reportExpedition(
            session = ctx.session,
            kind = pending.kind,
            targetId = pending.targetId,
            acceptedRevision = pending.acceptedRevision,
            success = pending.success,
            message = pending.message,
            nowMillis = ctx.nowMillis,
            raw = pending.raw
        )) {
            is CloudMapResult.Ok -> {
                pendingCloudExpedition = null
                ctx.shuaLog("cloud-result accepted target=${pending.targetId} revision=${report.value.serverRevision}")
                null
            }
            is CloudMapResult.Err -> {
                ctx.shuaLog("cloud-result pending target=${pending.targetId} code=${report.code} message=${report.message}")
                if (report.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS)
                else TaskDecision.Stop(report.message)
            }
        }
    }

    override suspend fun stop(ctx: TaskContext, reason: String) {
        // Task-specific cleanup hook only. Session logout is centralized in TaskScheduler.stopAll
        // so a brush-yellow stop maps to exactly one explicit logout request.
    }



    private suspend fun runDeleteMailForSpeedIfNeeded(ctx: TaskContext): TaskDecision {
        val day = localDayKey(ctx.nowMillis)
        if (!config.deleteMailForSpeed || deleteMailCompletedDay == day) {
            return TaskDecision.Continue
        }
        return when (val result = ctx.protocol.runDailyStep(ctx.session, DailyStep.DELETE_MAIL)) {
            is ProtocolResult.Ok -> {
                if (result.value.success) {
                    deleteMailCompletedDay = day
                    TaskDecision.Continue
                } else {
                    TaskDecision.Stop("delete mail before shua huang failed: ${result.value.message}")
                }
            }
            is ProtocolResult.Err -> if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
        }
    }

    private fun localDayKey(nowMillis: Long): Int {
        val calendar = java.util.Calendar.getInstance().apply { timeInMillis = nowMillis }
        return calendar.get(java.util.Calendar.YEAR) * 1000 +
            calendar.get(java.util.Calendar.DAY_OF_YEAR)
    }

    private fun TaskContext.shuaLog(message: String) {
        runtime.emit("account=${session.accountId} owner=$type brush-yellow $message")
    }

    private fun millisUntilConfiguredStart(nowMillis: Long, startHour: Int): Long {
        val hour = startHour.coerceIn(0, 23)
        if (hour == 0) return 0L
        val now = java.util.Calendar.getInstance().apply { timeInMillis = nowMillis }
        if (now.get(java.util.Calendar.HOUR_OF_DAY) >= hour) return 0L
        val target = (now.clone() as java.util.Calendar).apply {
            set(java.util.Calendar.HOUR_OF_DAY, hour)
            set(java.util.Calendar.MINUTE, 0)
            set(java.util.Calendar.SECOND, 0)
            set(java.util.Calendar.MILLISECOND, 0)
        }
        return (target.timeInMillis - nowMillis).coerceAtLeast(0L)
    }

    private fun millisUntilNextDailyStart(nowMillis: Long, startHour: Int): Long {
        val target = java.util.Calendar.getInstance().apply {
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

    private suspend fun runPendingRecoveryIfReturned(ctx: TaskContext, generals: List<General>): Boolean {
        val pendingRecoveryGeneralIds = ctx.runtime.pendingBrushRecoveryGeneralIds(ctx.session.accountId, type)
        if (pendingRecoveryGeneralIds.isEmpty()) return false
        val byId = generals.associateBy { it.id }
        val recovered = mutableListOf<Long>()
        pendingRecoveryGeneralIds.forEach { generalId ->
            val general = byId[generalId]
            if (general == null) {
                ctx.shuaLog("pending-recovery general=$generalId missing wait-next")
                return@forEach
            }
            if (general.status != null && general.status != 0) {
                ctx.shuaLog("pending-recovery general=$generalId status=${general.status} not-idle wait-next")
                return@forEach
            }
            when (val heal = ctx.protocol.healGeneral(ctx.session, generalId)) {
                is ProtocolResult.Ok -> ctx.shuaLog("post-return-heal general=$generalId success=${heal.value.success} message=${heal.value.message}")
                is ProtocolResult.Err -> ctx.shuaLog("post-return-heal skipped/error general=$generalId code=${heal.code} message=${heal.message}")
            }
            recovered += generalId
        }
        ctx.runtime.removePendingBrushRecovery(ctx.session.accountId, type, recovered)
        return recovered.isNotEmpty()
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

    private fun BattleResult.isSoftDispatchReject(): Boolean {
        val message = failureMessage()
        val hex = raw["responseHex"] ?: raw["expeditionResponseHex"] ?: ""
        return message.contains("0x8522=ff0000") ||
            message.contains("游戏服拒绝出征") ||
            hex.equals("ff0000", ignoreCase = true)
    }

    private fun chooseFormations(formations: List<FormationRuntime>, generals: List<General>): List<FormationRuntime> {
        val selectedOrder = config.selectedFormationIds.toList()
        val generalById = generals.associateBy { it.id }
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
        val filter = config.filterForFormation(formation.id)
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

    private fun ShuaHuangConfig.filterForFormation(formationId: Long): ShuaHuangTargetFilter =
        if (formationFilterMode == FormationFilterMode.PER_FORMATION) {
            perFormationTargetFilters[formationId] ?: targetFilter
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
        if (filter.minLevel != null && (level == null || level < filter.minLevel)) return false
        if (filter.maxLevel != null && (level == null || level > filter.maxLevel)) return false
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
        if (filter.maxFoot == null && filter.maxBow == null && filter.maxCavalry == null && filter.maxChariot == null) return true
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
        // 041540 解析暂未必能稳定恢复敌军四类统领数；没有字段时不误杀目标，字段存在时严格套用户条件。
        if (filter.maxFoot != null && foot != null && foot > filter.maxFoot) return false
        if (filter.maxBow != null && bow != null && bow > filter.maxBow) return false
        if (filter.maxCavalry != null && cavalry != null && cavalry > filter.maxCavalry) return false
        if (filter.maxChariot != null && chariot != null && chariot > filter.maxChariot) return false
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

class MineSearchMockTask(accountId: Long, config: MineConfig) :
    BaseMockTask<MineConfig>(accountId, if (config.backgroundSearch) TaskType.MINE_SEARCH else TaskType.AUTO_MINING, config) {
    private var ruleCursor: Int = 0
    private var pendingCloudExpedition: PendingCloudExpedition? = null

    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled && !config.backgroundSearch) return TaskDecision.Stop("mine task disabled")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        flushPendingCloudExpedition(ctx)?.let { return it }
        val enabledRules = config.rules.filter {
            it.enabled && it.generalIds.isNotEmpty()
        }
        val rule = enabledRules.getOrNull(
            if (enabledRules.isEmpty()) 0 else ruleCursor.mod(enabledRules.size)
        )
        if (enabledRules.isNotEmpty()) {
            ruleCursor = (ruleCursor + 1).mod(enabledRules.size)
        }
        val activeConfig = if (rule != null) {
            config.copy(
                start = rule.start,
                selectedMineTypes = setOf(rule.mineType),
                selectedFormationIds = rule.generalIds.toSet(),
                onlyEmptyMine = rule.onlyEmpty,
                onlyDefendedMine = rule.onlyDefended,
                searchScope = rule.scope
            )
        } else {
            config
        }
        val mines = when (val result = ctx.protocol.searchMines(ctx.session, activeConfig)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
        }
        if (type == TaskType.MINE_SEARCH) return TaskDecision.Sleep(activeConfig.searchIntervalMinutes * 60_000L)
        val cloudMines = when (val result = ctx.cloudMap.selectMineTargets(
            session = ctx.session,
            observed = mines,
            start = activeConfig.start,
            allowedMineTypes = activeConfig.selectedMineTypes.mapTo(linkedSetOf()) { it.name },
            nowMillis = ctx.nowMillis
        )) {
            is CloudMapResult.Ok -> result.value
            is CloudMapResult.Err ->
                return if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
        }
        val mine = cloudMines.firstOrNull {
            it.matchesTargetPlayer(config.targetPlayerName)
        } ?: return TaskDecision.Sleep(30_000)
        val generalIds = activeConfig.selectedFormationIds.toList()
        if (generalIds.isEmpty()) return TaskDecision.Stop("no formation selected")
        val occupyResult = if (generalIds.size == 1) {
            ctx.protocol.occupyMine(ctx.session, mine, generalIds.single())
        } else {
            ctx.protocol.occupyMine(ctx.session, mine, generalIds)
        }
        val occupyDecision = when (val occupy = occupyResult) {
            is ProtocolResult.Err -> {
                val next = if (occupy.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS)
                else TaskDecision.Stop(occupy.message)
                return reportCloudExpedition(
                    ctx,
                    mine,
                    false,
                    "${occupy.code}: ${occupy.message}",
                    emptyMap(),
                    next
                )
            }
            is ProtocolResult.Ok -> {
                if (!occupy.value.success) {
                    return reportCloudExpedition(
                        ctx,
                        mine,
                        false,
                        occupy.value.message,
                        occupy.value.raw,
                        TaskDecision.Sleep(30_000)
                    )
                }
                TaskDecision.Sleep(30_000)
            }
        }
        val next = if (activeConfig.withdrawDefense) {
            when (val withdraw = ctx.protocol.withdrawMineDefense(ctx.session, mine.id)) {
                is ProtocolResult.Err ->
                    if (withdraw.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS)
                    else TaskDecision.Stop(withdraw.message)
                is ProtocolResult.Ok ->
                    if (withdraw.value.success) TaskDecision.Sleep(30_000)
                    else TaskDecision.Stop(withdraw.value.message)
            }
        } else {
            occupyDecision
        }
        return reportCloudExpedition(
            ctx,
            mine,
            true,
            "打矿出征成功",
            emptyMap(),
            next
        )
    }

    private suspend fun reportCloudExpedition(
        ctx: TaskContext,
        mine: MineSearchResult,
        success: Boolean,
        message: String,
        raw: Map<String, String>,
        next: TaskDecision
    ): TaskDecision {
        pendingCloudExpedition = PendingCloudExpedition(
            kind = CloudMapKind.MINE,
            targetId = mine.id,
            acceptedRevision = mine.raw["cloudRevision"].orEmpty(),
            success = success,
            message = message,
            raw = raw
        )
        return flushPendingCloudExpedition(ctx) ?: next
    }

    private suspend fun flushPendingCloudExpedition(ctx: TaskContext): TaskDecision? {
        val pending = pendingCloudExpedition ?: return null
        return when (val report = ctx.cloudMap.reportExpedition(
            session = ctx.session,
            kind = pending.kind,
            targetId = pending.targetId,
            acceptedRevision = pending.acceptedRevision,
            success = pending.success,
            message = pending.message,
            nowMillis = ctx.nowMillis,
            raw = pending.raw
        )) {
            is CloudMapResult.Ok -> {
                pendingCloudExpedition = null
                null
            }
            is CloudMapResult.Err ->
                if (report.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS)
                else TaskDecision.Stop(report.message)
        }
    }

    private fun MineSearchResult.matchesTargetPlayer(expectedName: String): Boolean {
        val expected = expectedName.trim()
        if (expected.isEmpty()) return true
        val ownerText = raw.entries
            .filter { (key, _) ->
                key.contains("owner", true) ||
                    key.contains("player", true) ||
                    key.contains("name", true) ||
                    key.contains("text", true) ||
                    key.contains("description", true)
            }
            .joinToString(" ") { it.value }
        // 填写定点送将玩家名时必须有明确匹配证据；没有所有者字段也不能冒险出征。
        return ownerText.contains(expected, ignoreCase = true)
    }
}

class InventoryCleanupMockTask(accountId: Long, config: InventoryConfig) :
    BaseMockTask<InventoryConfig>(accountId, TaskType.INVENTORY, config) {
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
        val available = items.associate { it.name to it.count }.toMutableMap()
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
                repeat(usableCount) {
                    val decision = ctx.protocol.useOrDiscardItem(
                        ctx.session, item.id, InventoryAction.OPEN, count = 1
                    ).asConfirmedStepDecision(
                        emptyFailureMessage = "服务器未确认背包动作成功"
                    )
                    if (decision is TaskDecision.Stop || decision is TaskDecision.RetryAfter) return decision
                    opened++
                    if (keyName != null) available[keyName] = (available[keyName] ?: 0) - 1
                }
            } else {
                val decision = ctx.protocol.useOrDiscardItem(
                    ctx.session, item.id, action, count = item.count
                ).asConfirmedStepDecision(
                    emptyFailureMessage = "服务器未确认背包动作成功"
                )
                if (decision is TaskDecision.Stop || decision is TaskDecision.RetryAfter) return decision
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
        // Cached real inventory does not yet carry complete equipment-instance safety fields.
        if (item.type == "equipment") return null
        if (item.enhanced && config.neverDiscardEnhancedOrEquipped) return null
        if (item.equipped && config.neverDiscardEnhancedOrEquipped) return null
        if (item.quality != null && item.quality in config.discardEquipmentQualities) return InventoryAction.DISCARD
        if (config.discardBelowLevel != null && item.level != null && item.level < config.discardBelowLevel) return InventoryAction.DISCARD
        if (item.name in config.discardItems) return InventoryAction.DISCARD
        return null
    }
}

class GeneralMaintenanceMockTask(accountId: Long, config: GeneralConfig) :
    BaseMockTask<GeneralConfig>(accountId, TaskType.GENERAL, config) {
    override suspend fun step(ctx: TaskContext): TaskDecision {
        val generals = when (val result = ctx.protocol.queryGenerals(ctx.session)) {
            is ProtocolResult.Ok -> result.value
            is ProtocolResult.Err -> return if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
        }
        if (config.autoHeal) {
            val representative = generals.firstOrNull { it.placeId != null }
                ?: generals.firstOrNull()
                ?: return TaskDecision.Stop("no general available for wounded healing")
            val decision = ctx.protocol.healGeneral(ctx.session, representative.id)
                .asConfirmedStepDecision(emptyFailureMessage = "服务器未确认治疗成功")
            if (decision is TaskDecision.Stop || decision is TaskDecision.RetryAfter) return decision
        }
        for (general in generals) {
            if (config.requireChineseNamePrefix && general.name.firstOrNull()?.isChinese() == false) {
                return TaskDecision.Stop("general name must start with Chinese char: ${general.name}")
            }
            if (config.autoEnergy && general.energy != null && general.energy < config.minEnergy) {
                val decision = ctx.protocol.addEnergy(ctx.session, general.id)
                    .asConfirmedStepDecision(emptyFailureMessage = "服务器未确认加体成功")
                if (decision is TaskDecision.Stop || decision is TaskDecision.RetryAfter) return decision
            }
            if (config.keepFullLoyalty && general.loyalty != null && general.loyalty < 100) {
                val decision = ctx.protocol.runDailyStep(ctx.session, DailyStep.ADD_LOYALTY)
                    .asConfirmedStepDecision(emptyFailureMessage = "服务器未确认加忠成功")
                if (decision is TaskDecision.Stop || decision is TaskDecision.RetryAfter) return decision
            }
        }
        return TaskDecision.Sleep(10 * 60 * 1000L)
    }

    private fun Char.isChinese(): Boolean = this in '\u4e00'..'\u9fff'
}

class FormationUpdateMockTask(accountId: Long, config: FormationConfig) :
    BaseMockTask<FormationConfig>(accountId, TaskType.FORMATION, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (config.generalIds.isEmpty()) return TaskDecision.Stop("no generals selected")
        if (config.autoAssignTroops && config.troopCount <= 0) return TaskDecision.Stop("troop count must be positive")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision =
        when (val result = ctx.protocol.updateFormation(ctx.session, config)) {
            is ProtocolResult.Ok -> {
                if (result.value.success) {
                    TaskDecision.Sleep(5 * 60 * 1000L)
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

class InternalAffairsMockTask(accountId: Long, config: InternalAffairsConfig) :
    BaseMockTask<InternalAffairsConfig>(accountId, TaskType.INTERNAL, config) {
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
            is ProtocolResult.Ok -> TaskDecision.Sleep(
                result.value.raw["nextDelayMillis"]?.toLongOrNull()
                    ?.coerceIn(10L * 60L * 1_000L, 60L * 60L * 1_000L)
                    ?: 10L * 60L * 1_000L
            )
            is ProtocolResult.Err -> if (result.retryable) {
                TaskDecision.RetryAfter(DEFAULT_RETRY_MS)
            } else {
                TaskDecision.Stop(result.message)
            }
        }
}

class DungeonMockTask(accountId: Long, config: DungeonConfig) :
    BaseMockTask<DungeonConfig>(accountId, TaskType.DUNGEON, config) {
    private var completedDayKey: Long = Long.MIN_VALUE
    private var completedToday: Int = 0

    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled) return TaskDecision.Stop("dungeon disabled")
        if (config.dailyTimes <= 0) return TaskDecision.Stop("daily dungeon times must be positive")
        if (config.formationIds.isEmpty()) return TaskDecision.Stop("no dungeon formation selected")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        val dayKey = (ctx.nowMillis + 8 * 60 * 60 * 1000L) / (24 * 60 * 60 * 1000L)
        if (dayKey != completedDayKey) {
            completedDayKey = dayKey
            completedToday = 0
        }
        if (completedToday >= config.dailyTimes) {
            val nextMidnight = (dayKey + 1) * 24 * 60 * 60 * 1000L - 8 * 60 * 60 * 1000L
            return TaskDecision.Sleep((nextMidnight - ctx.nowMillis).coerceAtLeast(60_000L))
        }
        return when (val result = ctx.protocol.runDungeon(ctx.session, config)) {
            is ProtocolResult.Err ->
                if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
            is ProtocolResult.Ok -> {
                if (!result.value.success) {
                    TaskDecision.Stop(result.value.message)
                } else {
                    val completed = result.value.raw["phase"] == "chest-opened" ||
                        (ctx.session.sourceMode != 1 && result.value.raw["phase"].isNullOrBlank())
                    if (completed) {
                        completedToday++
                        ctx.runtime.recordDailySuccess(
                            ctx.session.accountId,
                            type,
                            count = 1,
                            nowMillis = ctx.nowMillis
                        )
                    }
                    when (result.value.raw["phase"]) {
                        "fighting" -> TaskDecision.Sleep(10_000L)
                        else -> TaskDecision.Sleep(60_000L)
                    }
                }
            }
        }
    }
}

class LosslessTask(accountId: Long, config: LosslessConfig) :
    BaseMockTask<LosslessConfig>(accountId, TaskType.LOSSLESS, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled) return TaskDecision.Stop("lossless disabled")
        if (config.dailyLimit <= 0) return TaskDecision.Stop("lossless daily limit must be positive")
        val enabledRules = config.rules.filter { it.enabled }
        if (enabledRules.isEmpty()) return TaskDecision.Stop("no lossless rule enabled")
        if (enabledRules.any { it.generalIds.isEmpty() }) return TaskDecision.Stop("lossless general missing")
        if (enabledRules.any { it.generalIds.size > 5 }) return TaskDecision.Stop("lossless rule supports at most 5 generals")
        if (enabledRules.any { it.level !in 1..10 }) return TaskDecision.Stop("lossless level must be 1..10")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        return when (val result = ctx.protocol.runLossless(ctx.session, config)) {
            is ProtocolResult.Err ->
                if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
            is ProtocolResult.Ok -> {
                // SessionAwareGameProtocolClient uses the server's remaining-attempt field
                // as the authoritative daily counter. Never suppress status/settlement
                // polling just because an earlier dispatch consumed the configured limit.
                if (result.value.success) {
                    TaskDecision.Sleep(
                        result.value.raw["nextDelayMillis"]
                            ?.toLongOrNull()
                            ?.coerceIn(1_000L, 24 * 60 * 60 * 1000L)
                            ?: 60_000L
                    )
                } else {
                    TaskDecision.Stop(result.value.message)
                }
            }
        }
    }
}

class VipFeatureMockTask(accountId: Long, config: VipFeatureConfig) :
    BaseMockTask<VipFeatureConfig>(accountId, TaskType.VIP, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled) return TaskDecision.Stop("vip feature disabled")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision =
        ctx.protocol.setVipFeature(ctx.session, config).asConfirmedStepDecision(
            success = TaskDecision.Sleep(60 * 60 * 1000L),
            emptyFailureMessage = "服务器未确认VIP动作成功"
        )
}

class SurrenderReleaseMockTask(accountId: Long, config: SurrenderReleaseConfig) :
    BaseMockTask<SurrenderReleaseConfig>(accountId, TaskType.SURRENDER_RELEASE, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.autoSurrender && !config.autoRelease) return TaskDecision.Stop("surrender/release disabled")
        if (config.releaseGrowthBelow >= config.surrenderGrowthAbove) return TaskDecision.Stop("release threshold must be below surrender threshold")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision =
        ctx.protocol.surrenderOrReleaseGenerals(ctx.session, config).asConfirmedStepDecision(
            success = TaskDecision.Sleep(10 * 60 * 1000L),
            emptyFailureMessage = "服务器未确认劝降或释放成功"
        )
}

class ResourcePointSendGeneralMockTask(accountId: Long, config: ResourcePointSendGeneralConfig) :
    BaseMockTask<ResourcePointSendGeneralConfig>(accountId, TaskType.RESOURCE_POINT_SEND_GENERAL, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled) return TaskDecision.Stop("resource point send general disabled")
        if (config.stopAfterMinutes <= 0) return TaskDecision.Stop("stopAfterMinutes must be positive")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision =
        ctx.protocol.sendGeneralToResourcePoint(ctx.session, config).asConfirmedStepDecision(
            success = TaskDecision.Sleep(config.stopAfterMinutes * 60_000L),
            emptyFailureMessage = "服务器未确认资源点送将成功"
        )
}

class AutoLootMockTask(accountId: Long, config: AutoLootConfig) :
    BaseMockTask<AutoLootConfig>(accountId, TaskType.AUTO_LOOT, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        config.preparationError()?.let { return TaskDecision.Stop(it) }
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision =
        when (val result = ctx.protocol.runAutoLoot(ctx.session, config)) {
            is ProtocolResult.Err ->
                if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS) else TaskDecision.Stop(result.message)
            is ProtocolResult.Ok -> {
                if (!result.value.success) {
                    TaskDecision.Stop(result.value.message)
                } else {
                    // Existing account refresh updates general state; once the selected
                    // generals return idle the next scheduler step launches another raid.
                    TaskDecision.Sleep(60_000L)
                }
            }
        }
}

class SixMinistriesTask(accountId: Long, config: SixMinistriesConfig) :
    BaseMockTask<SixMinistriesConfig>(accountId, TaskType.MINISTRY, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        config.preparationError()?.let { return TaskDecision.Stop(it) }
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision =
        when (val result = ctx.protocol.runSixMinistries(ctx.session, config)) {
            is ProtocolResult.Err ->
                if (result.retryable) TaskDecision.RetryAfter(DEFAULT_RETRY_MS)
                else TaskDecision.Stop(result.message)
            is ProtocolResult.Ok ->
                if (!result.value.success) TaskDecision.Stop(result.value.message)
                else {
                    when (result.value.raw["phase"]) {
                        "garden-full" -> TaskDecision.Sleep(10 * 60_000L)
                        "steal-scan" -> TaskDecision.Sleep(10 * 60_000L)
                        else -> TaskDecision.Sleep(60_000L)
                    }
                }
        }
}

class AlarmWithdrawMockTask(accountId: Long, config: AlarmWithdrawConfig) :
    BaseMockTask<AlarmWithdrawConfig>(accountId, TaskType.ALARM_WITHDRAW, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled) return TaskDecision.Stop("alarm scan disabled")
        if (config.keywords.isEmpty()) return TaskDecision.Stop("alarm keywords empty")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision =
        ctx.protocol.scanAlarmAndMaybeWithdraw(ctx.session, config).asConfirmedStepDecision(
            success = TaskDecision.Sleep(30_000),
            emptyFailureMessage = "服务器未确认警报扫描成功"
        )
}

class BulkToolsMockTask(accountId: Long, config: BulkToolConfig) :
    BaseMockTask<BulkToolConfig>(accountId, TaskType.BULK_TOOLS, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (config.enabledActions.isEmpty()) return TaskDecision.Stop("no bulk action selected")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        for (action in config.enabledActions) {
            val decision = ctx.protocol.runBulkToolAction(ctx.session, action)
                .asConfirmedStepDecision(emptyFailureMessage = "服务器未确认批量动作成功")
            if (decision is TaskDecision.Stop || decision is TaskDecision.RetryAfter) return decision
        }
        return TaskDecision.Sleep(60 * 60 * 1000L)
    }
}

class OpenServerQueryMockTask(accountId: Long, config: OpenServerQuery) :
    BaseMockTask<OpenServerQuery>(accountId, TaskType.OPEN_SERVER_QUERY, config) {
    override suspend fun step(ctx: TaskContext): TaskDecision =
        ctx.protocol.queryOpenServer(config).asDecision(TaskDecision.Stop("open server query completed"))
}

class CitySearchMockTask(accountId: Long, config: CityDefenseSearchConfig) :
    BaseMockTask<CityDefenseSearchConfig>(accountId, TaskType.CITY_SEARCH, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (!config.enabled) return TaskDecision.Stop("city search disabled")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision =
        ctx.protocol.searchDefendedCities(ctx.session, config).asDecision(TaskDecision.Stop("city search completed"))
}

class TreasureSearchMockTask(accountId: Long, config: TreasureFilterConfig) :
    BaseMockTask<TreasureFilterConfig>(accountId, TaskType.TREASURE_SEARCH, config) {
    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        if (config.enabledKinds.isEmpty() && config.nameKeyword.isNullOrBlank()) return TaskDecision.Stop("treasure filter empty")
        return super.prepare(ctx)
    }

    override suspend fun step(ctx: TaskContext): TaskDecision =
        ctx.protocol.searchTreasures(ctx.session, config).asDecision(TaskDecision.Stop("treasure search completed"))
}
