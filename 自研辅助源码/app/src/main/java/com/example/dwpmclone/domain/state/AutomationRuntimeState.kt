package com.example.dwpmclone.domain.state

import com.example.dwpmclone.domain.model.FormationRuntime
import com.example.dwpmclone.domain.model.FormationRuntimeStatus
import com.example.dwpmclone.domain.protocol.General
import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType

/**
 * Explicit runtime state for the assistant.
 *
 * Xiaohuang's original service effectively used an implicit Service/Runnable/if-else state
 * machine.  The clone keeps the same sequential business order, but stores runtime ownership
 * explicitly so action tasks cannot reuse the same general/formation while a previous command is
 * still in flight or marching.
 */
enum class AccountRunState {
    LOGGED_OUT,
    LOGGING_IN,
    SYNCING_STATE,
    READY,
    RUNNING,
    STOPPING,
    LOGGING_OUT,
    SESSION_EXPIRED,
    ERROR
}

enum class RuntimeGeneralState {
    UNKNOWN,
    IDLE,
    RESERVED,
    DISPATCHING,
    MARCHING,
    RETURNING,
    RESTING,
    UNAVAILABLE,
    ERROR
}

enum class RuntimeFormationState {
    UNKNOWN,
    IDLE,
    RESERVED,
    DISPATCHING,
    BUSY,
    RETURNING,
    UNAVAILABLE,
    ERROR
}

data class GeneralLease(
    val accountId: Long,
    val generalId: Long,
    val owner: TaskType,
    val taskKey: String,
    val state: RuntimeGeneralState,
    val acquiredAtMillis: Long,
    val expiresAtMillis: Long?,
    val reason: String
)

data class FormationLease(
    val accountId: Long,
    val formationId: Long,
    val owner: TaskType,
    val taskKey: String,
    val state: RuntimeFormationState,
    val acquiredAtMillis: Long,
    val expiresAtMillis: Long?,
    val reason: String,
    val generalIds: List<Long>
)

sealed class GateResult {
    data object Allowed : GateResult()
    data class Blocked(val reason: String, val retryAfterMillis: Long = DEFAULT_RETRY_MS) : GateResult()

    fun asDecision(): TaskDecision = when (this) {
        Allowed -> TaskDecision.Continue
        is Blocked -> TaskDecision.Sleep(retryAfterMillis, reason = reason)
    }

    companion object {
        const val DEFAULT_RETRY_MS: Long = 30_000L
    }
}

/** In-memory state store scoped to one scheduler/service process. */
class AutomationRuntimeStateStore(
    private val defaultBusyLeaseMillis: Long = 20 * 60_000L,
    private val serverIdleConfirmMillis: Long = 10_000L,
    private val timezoneId: String = "Asia/Shanghai",
    val enforceCommandGate: Boolean = true,
    private val eventSink: (String) -> Unit = {},
    private val dailySuccessSink: (Long, TaskType, Int, Long) -> Unit = { _, _, _, _ -> },
    private val dailySuccessSource: (Long, TaskType, Long) -> Int = { _, _, _ -> 0 }
) {
    private val accountStates = mutableMapOf<Long, AccountRunState>()
    private val generalLeases = mutableMapOf<Pair<Long, Long>, GeneralLease>()
    private val formationLeases = mutableMapOf<Pair<Long, Long>, FormationLease>()
    private val brushPendingRecovery = mutableMapOf<Pair<Long, TaskType>, MutableSet<Long>>()
    private val brushLocalConsumed = mutableMapOf<Pair<Long, TaskType>, Int>()
    private val brushLocalConsumedDay = mutableMapOf<Pair<Long, TaskType>, Int>()
    private val brushPersistedBaseline = mutableMapOf<Pair<Long, TaskType>, Int>()
    private val brushPersistedBaselineDay = mutableMapOf<Pair<Long, TaskType>, Int>()
    private val residentRuleCursors = mutableMapOf<Pair<Long, TaskType>, Int>()

    val commandGate: CommandGate = CommandGate(this, defaultBusyLeaseMillis)

    internal fun emit(event: String) {
        runCatching { eventSink(event) }
    }

    @Synchronized
    fun accountState(accountId: Long): AccountRunState = accountStates[accountId] ?: AccountRunState.LOGGED_OUT

    @Synchronized
    fun setAccountState(accountId: Long, state: AccountRunState) {
        val previous = accountStates[accountId] ?: AccountRunState.LOGGED_OUT
        accountStates[accountId] = state
        if (previous != state) emit("account=$accountId state $previous -> $state")
    }

    @Synchronized
    fun generalLease(accountId: Long, generalId: Long, nowMillis: Long = System.currentTimeMillis()): GeneralLease? {
        pruneExpiredLocked(nowMillis)
        return generalLeases[accountId to generalId]
    }

    @Synchronized
    fun formationLease(accountId: Long, formationId: Long, nowMillis: Long = System.currentTimeMillis()): FormationLease? {
        pruneExpiredLocked(nowMillis)
        return formationLeases[accountId to formationId]
    }

    @Synchronized
    fun snapshotGeneralLeases(accountId: Long, nowMillis: Long = System.currentTimeMillis()): List<GeneralLease> {
        pruneExpiredLocked(nowMillis)
        return generalLeases.values.filter { it.accountId == accountId }.sortedBy { it.generalId }
    }

    @Synchronized
    fun brushConsumedCount(
        accountId: Long,
        owner: TaskType,
        nowMillis: Long = System.currentTimeMillis()
    ): Int {
        resetBrushCountIfDayChangedLocked(accountId to owner, nowMillis)
        return brushLocalConsumed[accountId to owner] ?: 0
    }

    @Synchronized
    fun persistedBrushCountForDay(
        accountId: Long,
        owner: TaskType,
        persistedCount: Int,
        nowMillis: Long = System.currentTimeMillis()
    ): Int {
        val key = accountId to owner
        val dayKey = localDayKey(nowMillis)
        if (brushPersistedBaselineDay[key] != dayKey) {
            val hadPreviousDay = brushPersistedBaselineDay.containsKey(key)
            brushPersistedBaselineDay[key] = dayKey
            val localPersisted = runCatching {
                dailySuccessSource(accountId, owner, nowMillis)
            }.getOrDefault(0).coerceAtLeast(0)
            brushPersistedBaseline[key] = if (hadPreviousDay) {
                localPersisted
            } else {
                maxOf(persistedCount.coerceAtLeast(0), localPersisted)
            }
        }
        return brushPersistedBaseline[key] ?: 0
    }

    fun persistedDailySuccessCount(
        accountId: Long,
        owner: TaskType,
        nowMillis: Long = System.currentTimeMillis()
    ): Int = runCatching { dailySuccessSource(accountId, owner, nowMillis) }
        .getOrDefault(0)
        .coerceAtLeast(0)

    @Synchronized
    fun addBrushConsumed(
        accountId: Long,
        owner: TaskType,
        consumed: Int,
        nowMillis: Long = System.currentTimeMillis()
    ): Int {
        if (consumed <= 0) return brushConsumedCount(accountId, owner, nowMillis)
        val key = accountId to owner
        resetBrushCountIfDayChangedLocked(key, nowMillis)
        val next = (brushLocalConsumed[key] ?: 0) + consumed
        brushLocalConsumed[key] = next
        runCatching { dailySuccessSink(accountId, owner, consumed, nowMillis) }
        emit("account=$accountId owner=$owner brush-consumed-local=$next")
        return next
    }

    fun recordDailySuccess(
        accountId: Long,
        owner: TaskType,
        count: Int = 1,
        nowMillis: Long = System.currentTimeMillis()
    ) {
        if (count <= 0) return
        runCatching { dailySuccessSink(accountId, owner, count, nowMillis) }
        emit("account=$accountId owner=$owner daily-success=+$count")
    }

    private fun resetBrushCountIfDayChangedLocked(
        key: Pair<Long, TaskType>,
        nowMillis: Long
    ) {
        val dayKey = localDayKey(nowMillis)
        val previousDay = brushLocalConsumedDay[key]
        if (previousDay != null && previousDay != dayKey) {
            brushLocalConsumed.remove(key)
            emit("account=${key.first} owner=${key.second} brush-consumed-local reset day=$dayKey")
        }
        brushLocalConsumedDay[key] = dayKey
    }

    private fun localDayKey(nowMillis: Long): Int {
        val calendar = java.util.Calendar.getInstance(
            java.util.TimeZone.getTimeZone(timezoneId)
        ).apply { timeInMillis = nowMillis }
        return calendar.get(java.util.Calendar.YEAR) * 1000 +
            calendar.get(java.util.Calendar.DAY_OF_YEAR)
    }

    @Synchronized
    fun pendingBrushRecoveryGeneralIds(accountId: Long, owner: TaskType): Set<Long> =
        brushPendingRecovery[accountId to owner]?.toSet().orEmpty()

    @Synchronized
    fun residentRuleIndex(accountId: Long, owner: TaskType, ruleCount: Int): Int {
        if (ruleCount <= 0) return 0
        return Math.floorMod(residentRuleCursors[accountId to owner] ?: 0, ruleCount)
    }

    @Synchronized
    fun advanceResidentRule(accountId: Long, owner: TaskType, ruleCount: Int) {
        if (ruleCount <= 0) return
        val key = accountId to owner
        residentRuleCursors[key] = Math.floorMod((residentRuleCursors[key] ?: 0) + 1, ruleCount)
    }

    @Synchronized
    fun addPendingBrushRecovery(accountId: Long, owner: TaskType, generalIds: Collection<Long>) {
        val ids = generalIds.filter { it > 0L }.toSet()
        if (ids.isEmpty()) return
        val key = accountId to owner
        val set = brushPendingRecovery.getOrPut(key) { linkedSetOf() }
        set += ids
        emit("account=$accountId owner=$owner brush-pending-recovery=${set.joinToString()}")
    }

    @Synchronized
    fun removePendingBrushRecovery(accountId: Long, owner: TaskType, generalIds: Collection<Long>) {
        val key = accountId to owner
        val set = brushPendingRecovery[key] ?: return
        set.removeAll(generalIds.toSet())
        if (set.isEmpty()) brushPendingRecovery.remove(key)
        emit("account=$accountId owner=$owner brush-pending-recovery=${set.joinToString().ifBlank { "none" }}")
    }


    @Synchronized
    internal fun reconcileServerState(accountId: Long, generals: List<General>, formations: List<FormationRuntime>, nowMillis: Long) {
        pruneExpiredLocked(nowMillis)
        val generalById = generals.associateBy { it.id }
        val formationById = formations.associateBy { it.id }
        val releasableFormationIds = formationLeases.values
            .filter { lease ->
                lease.accountId == accountId &&
                    lease.state in setOf(RuntimeFormationState.DISPATCHING, RuntimeFormationState.BUSY, RuntimeFormationState.RETURNING) &&
                    nowMillis - lease.acquiredAtMillis >= serverIdleConfirmMillis &&
                    formationById[lease.formationId]?.let { formation ->
                        formation.status == FormationRuntimeStatus.IDLE && isFreshEnoughForRelease(formation.raw, lease.acquiredAtMillis)
                    } == true &&
                    lease.generalIds.isNotEmpty() &&
                    lease.generalIds.all { generalId ->
                        val serverGeneral = generalById[generalId]
                        serverGeneral != null &&
                            serverGeneral.status == 0 &&
                            isFreshEnoughForRelease(serverGeneral.raw, lease.acquiredAtMillis)
                    }
            }
            .map { it.formationId }
            .toSet()
        if (releasableFormationIds.isNotEmpty()) {
            val releasedGeneralIds = formationLeases.values
                .filter { it.accountId == accountId && it.formationId in releasableFormationIds }
                .flatMapTo(linkedSetOf()) { it.generalIds }
            emit("account=$accountId server-idle-confirm release formations=${releasableFormationIds.joinToString()}")
            formationLeases.entries.removeIf { (_, lease) ->
                lease.accountId == accountId && lease.formationId in releasableFormationIds
            }
            generalLeases.entries.removeIf { (_, lease) ->
                lease.accountId == accountId && lease.generalId in releasedGeneralIds &&
                    formationLeases.values.none { remaining ->
                        remaining.accountId == accountId && lease.generalId in remaining.generalIds
                    }
            }
        }

        val formationOwnedGeneralIds = formationLeases.values
            .filter { it.accountId == accountId }
            .flatMapTo(hashSetOf()) { it.generalIds }
        val releasableGeneralIds = generalLeases.values
            .filter { lease ->
                lease.accountId == accountId &&
                    lease.generalId !in formationOwnedGeneralIds &&
                    lease.state in setOf(
                        RuntimeGeneralState.DISPATCHING,
                        RuntimeGeneralState.MARCHING,
                        RuntimeGeneralState.RETURNING
                    ) &&
                    nowMillis - lease.acquiredAtMillis >= serverIdleConfirmMillis &&
                    generalById[lease.generalId]?.let { general ->
                        general.status == 0 &&
                            isFreshEnoughForRelease(general.raw, lease.acquiredAtMillis)
                    } == true
            }
            .map { it.generalId }
            .toSet()
        if (releasableGeneralIds.isNotEmpty()) {
            emit("account=$accountId server-idle-confirm release generals=${releasableGeneralIds.joinToString()}")
            generalLeases.entries.removeIf { (_, lease) ->
                lease.accountId == accountId && lease.generalId in releasableGeneralIds
            }
        }
    }


    private fun isFreshEnoughForRelease(raw: Map<String, String>, leaseAcquiredAtMillis: Long): Boolean {
        val explicitMillis = raw.firstNotNullOfOrNull { (key, value) ->
            if (key.contains("syncedAtMillis", ignoreCase = true) || key.contains("liveStateMillis", ignoreCase = true)) {
                value.toLongOrNull()
            } else {
                null
            }
        }
        if (explicitMillis != null) return explicitMillis >= leaseAcquiredAtMillis

        // Unit/mock protocol objects often carry no raw source.  Recovered/static 0x8004 evidence
        // from login must not unlock a post-dispatch lease because it can predate the action.
        val source = raw["source"].orEmpty().lowercase()
        if (source.contains("recovered") || source.contains("state8004") || source.contains("shared-prefs")) return false
        return raw.isEmpty()
    }

    @Synchronized
    internal fun reserveFormation(
        accountId: Long,
        owner: TaskType,
        taskKey: String,
        formation: FormationRuntime,
        nowMillis: Long,
        expiresAtMillis: Long?,
        reason: String
    ): GateResult {
        pruneExpiredLocked(nowMillis)
        val formationKey = accountId to formation.id
        formationLeases[formationKey]?.let { lease ->
            if (lease.owner != owner || lease.taskKey != taskKey || lease.state != RuntimeFormationState.RESERVED) {
                val reasonText = "formation ${formation.id} locked by ${lease.owner}/${lease.taskKey} state=${lease.state}"
                emit("account=$accountId owner=$owner reserve blocked: $reasonText")
                return GateResult.Blocked(reasonText)
            }
        }
        for (generalId in formation.generalIds) {
            generalLeases[accountId to generalId]?.let { lease ->
                if (lease.owner != owner || lease.taskKey != taskKey || lease.state != RuntimeGeneralState.RESERVED) {
                    val reasonText = "general $generalId locked by ${lease.owner}/${lease.taskKey} state=${lease.state}"
                    emit("account=$accountId owner=$owner reserve blocked: $reasonText")
                    return GateResult.Blocked(reasonText)
                }
            }
        }
        formationLeases[formationKey] = FormationLease(
            accountId = accountId,
            formationId = formation.id,
            owner = owner,
            taskKey = taskKey,
            state = RuntimeFormationState.RESERVED,
            acquiredAtMillis = nowMillis,
            expiresAtMillis = expiresAtMillis,
            reason = reason,
            generalIds = formation.generalIds
        )
        emit("account=$accountId owner=$owner reserve formation=${formation.id} generals=${formation.generalIds.joinToString()} reason=$reason")
        formation.generalIds.forEach { generalId ->
            generalLeases[accountId to generalId] = GeneralLease(
                accountId = accountId,
                generalId = generalId,
                owner = owner,
                taskKey = taskKey,
                state = RuntimeGeneralState.RESERVED,
                acquiredAtMillis = nowMillis,
                expiresAtMillis = expiresAtMillis,
                reason = reason
            )
        }
        return GateResult.Allowed
    }

    /**
     * Short command-center claim used by expedition tasks before their protocol state machine.
     * The owning task may re-enter while its own expedition is in flight so it can poll and
     * settle; every other task sharing one of the generals must yield.
     */
    @Synchronized
    internal fun reserveGeneralsForTask(
        accountId: Long,
        owner: TaskType,
        taskKey: String,
        generalIds: Collection<Long>,
        nowMillis: Long,
        expiresAtMillis: Long,
        reason: String
    ): GateResult {
        pruneExpiredLocked(nowMillis)
        val ids = generalIds.filter { it > 0L }.distinct()
        if (ids.isEmpty()) return GateResult.Blocked("$owner has no selected generals")
        for (generalId in ids) {
            val lease = generalLeases[accountId to generalId] ?: continue
            if (lease.owner != owner || lease.taskKey != taskKey) {
                val blocked = "将领${generalId}正由${lease.owner}执行（${lease.state}）"
                emit("account=$accountId owner=$owner command-claim blocked: $blocked")
                return GateResult.Blocked(blocked, retryAfterMillis = 2_000L)
            }
        }
        ids.forEach { generalId ->
            val key = accountId to generalId
            if (generalLeases[key] == null) {
                generalLeases[key] = GeneralLease(
                    accountId = accountId,
                    generalId = generalId,
                    owner = owner,
                    taskKey = taskKey,
                    state = RuntimeGeneralState.RESERVED,
                    acquiredAtMillis = nowMillis,
                    expiresAtMillis = expiresAtMillis,
                    reason = reason
                )
            }
        }
        emit("account=$accountId owner=$owner command-claim generals=${ids.joinToString()} reason=$reason")
        return GateResult.Allowed
    }

    @Synchronized
    internal fun markGeneralsBusyAfterDispatch(
        accountId: Long,
        owner: TaskType,
        taskKey: String,
        generalIds: Collection<Long>,
        nowMillis: Long,
        expiresAtMillis: Long,
        reason: String
    ) {
        generalIds.filter { it > 0L }.distinct().forEach { generalId ->
            val key = accountId to generalId
            val current = generalLeases[key]
            if (current != null && (current.owner != owner || current.taskKey != taskKey)) {
                return@forEach
            }
            generalLeases[key] = GeneralLease(
                accountId = accountId,
                generalId = generalId,
                owner = owner,
                taskKey = taskKey,
                state = RuntimeGeneralState.MARCHING,
                acquiredAtMillis = nowMillis,
                expiresAtMillis = expiresAtMillis,
                reason = reason
            )
        }
        emit(
            "account=$accountId owner=$owner dispatch-busy generals=" +
                generalIds.filter { it > 0L }.distinct().joinToString()
        )
    }

    @Synchronized
    internal fun markFormationDispatching(
        accountId: Long,
        owner: TaskType,
        taskKey: String,
        formationId: Long,
        nowMillis: Long,
        expiresAtMillis: Long?
    ) {
        val formationKey = accountId to formationId
        val formationLease = formationLeases[formationKey] ?: return
        if (formationLease.owner != owner || formationLease.taskKey != taskKey) return
        emit("account=$accountId owner=$owner dispatch-sending formation=$formationId generals=${formationLease.generalIds.joinToString()}")
        formationLeases[formationKey] = formationLease.copy(
            state = RuntimeFormationState.DISPATCHING,
            acquiredAtMillis = nowMillis,
            expiresAtMillis = expiresAtMillis,
            reason = "dispatch command in flight"
        )
        formationLease.generalIds.forEach { generalId ->
            val key = accountId to generalId
            val lease = generalLeases[key] ?: return@forEach
            if (lease.owner == owner && lease.taskKey == taskKey) {
                generalLeases[key] = lease.copy(
                    state = RuntimeGeneralState.DISPATCHING,
                    acquiredAtMillis = nowMillis,
                    expiresAtMillis = expiresAtMillis,
                    reason = "dispatch command in flight"
                )
            }
        }
    }

    @Synchronized
    internal fun markFormationBusyAfterDispatch(
        accountId: Long,
        owner: TaskType,
        taskKey: String,
        formationId: Long,
        nowMillis: Long,
        expiresAtMillis: Long?
    ) {
        val formationKey = accountId to formationId
        val formationLease = formationLeases[formationKey] ?: return
        if (formationLease.owner != owner || formationLease.taskKey != taskKey) return
        emit("account=$accountId owner=$owner dispatch-accepted formation=$formationId generals=${formationLease.generalIds.joinToString()}")
        formationLeases[formationKey] = formationLease.copy(
            state = RuntimeFormationState.BUSY,
            acquiredAtMillis = nowMillis,
            expiresAtMillis = expiresAtMillis,
            reason = "server accepted dispatch; waiting for 0x8004 to confirm return"
        )
        formationLease.generalIds.forEach { generalId ->
            val key = accountId to generalId
            val lease = generalLeases[key] ?: return@forEach
            if (lease.owner == owner && lease.taskKey == taskKey) {
                generalLeases[key] = lease.copy(
                    state = RuntimeGeneralState.MARCHING,
                    acquiredAtMillis = nowMillis,
                    expiresAtMillis = expiresAtMillis,
                    reason = "server accepted dispatch; waiting for 0x8004 to confirm return"
                )
            }
        }
    }

    @Synchronized
    internal fun releaseTaskReservations(accountId: Long, owner: TaskType, taskKey: String) {
        val generalsBefore = generalLeases.size
        val formationsBefore = formationLeases.size
        generalLeases.entries.removeIf { (_, lease) ->
            lease.accountId == accountId && lease.owner == owner && lease.taskKey == taskKey && lease.state == RuntimeGeneralState.RESERVED
        }
        formationLeases.entries.removeIf { (_, lease) ->
            lease.accountId == accountId && lease.owner == owner && lease.taskKey == taskKey && lease.state == RuntimeFormationState.RESERVED
        }
        val releasedGenerals = generalsBefore - generalLeases.size
        val releasedFormations = formationsBefore - formationLeases.size
        if (releasedGenerals > 0 || releasedFormations > 0) {
            emit("account=$accountId owner=$owner release-reservation formations=$releasedFormations generals=$releasedGenerals")
        }
    }

    @Synchronized
    internal fun releaseTaskLeases(accountId: Long, owner: TaskType? = null) {
        val generalsBefore = generalLeases.size
        val formationsBefore = formationLeases.size
        generalLeases.entries.removeIf { (_, lease) -> lease.accountId == accountId && (owner == null || lease.owner == owner) }
        formationLeases.entries.removeIf { (_, lease) -> lease.accountId == accountId && (owner == null || lease.owner == owner) }
        val releasedGenerals = generalsBefore - generalLeases.size
        val releasedFormations = formationsBefore - formationLeases.size
        if (releasedGenerals > 0 || releasedFormations > 0) {
            emit("account=$accountId owner=${owner?.name ?: "ALL"} release-task formations=$releasedFormations generals=$releasedGenerals")
        }
    }

    @Synchronized
    private fun pruneExpiredLocked(nowMillis: Long) {
        generalLeases.entries.removeIf { (_, lease) -> lease.expiresAtMillis != null && lease.expiresAtMillis <= nowMillis }
        formationLeases.entries.removeIf { (_, lease) -> lease.expiresAtMillis != null && lease.expiresAtMillis <= nowMillis }
    }
}

class CommandGate internal constructor(
    private val store: AutomationRuntimeStateStore,
    private val defaultBusyLeaseMillis: Long
) {
    fun beforeTask(accountId: Long, taskType: TaskType): GateResult {
        if (!store.enforceCommandGate) return GateResult.Allowed
        val state = store.accountState(accountId)
        return when (state) {
            AccountRunState.LOGGED_OUT, AccountRunState.READY, AccountRunState.RUNNING, AccountRunState.SYNCING_STATE -> {
                store.setAccountState(accountId, AccountRunState.RUNNING)
                GateResult.Allowed
            }
            AccountRunState.LOGGING_IN, AccountRunState.STOPPING, AccountRunState.LOGGING_OUT -> {
                GateResult.Blocked("account $accountId not ready for $taskType: $state")
            }
            AccountRunState.SESSION_EXPIRED, AccountRunState.ERROR -> {
                GateResult.Blocked("account $accountId cannot run $taskType: $state")
            }
        }
    }

    fun reconcileServerState(
        accountId: Long,
        generals: List<General>,
        formations: List<FormationRuntime>,
        nowMillis: Long
    ) {
        if (!store.enforceCommandGate) return
        store.reconcileServerState(accountId, generals, formations, nowMillis)
        if (generals.isNotEmpty() || formations.isNotEmpty()) {
            store.setAccountState(accountId, AccountRunState.RUNNING)
        }
    }

    fun tryReserveFormationForDispatch(
        accountId: Long,
        owner: TaskType,
        taskKey: String,
        formation: FormationRuntime,
        nowMillis: Long,
        reason: String
    ): GateResult {
        if (!store.enforceCommandGate) return GateResult.Allowed
        if (!formation.canDispatch) return GateResult.Blocked("formation ${formation.id} server status is ${formation.status}")
        if (formation.generalIds.isEmpty()) return GateResult.Blocked("formation ${formation.id} has no generals")
        val expiresAt = nowMillis + defaultBusyLeaseMillis
        return store.reserveFormation(accountId, owner, taskKey, formation, nowMillis, expiresAt, reason)
    }

    fun tryClaimGenerals(
        accountId: Long,
        owner: TaskType,
        taskKey: String,
        generalIds: Collection<Long>,
        nowMillis: Long,
        reason: String
    ): GateResult {
        if (!store.enforceCommandGate) return GateResult.Allowed
        return store.reserveGeneralsForTask(
            accountId = accountId,
            owner = owner,
            taskKey = taskKey,
            generalIds = generalIds,
            nowMillis = nowMillis,
            expiresAtMillis = nowMillis + COMMAND_CLAIM_MILLIS,
            reason = reason
        )
    }

    fun markGeneralsBusy(
        accountId: Long,
        owner: TaskType,
        taskKey: String,
        generalIds: Collection<Long>,
        nowMillis: Long,
        reason: String
    ) {
        if (!store.enforceCommandGate) return
        store.markGeneralsBusyAfterDispatch(
            accountId,
            owner,
            taskKey,
            generalIds,
            nowMillis,
            nowMillis + defaultBusyLeaseMillis,
            reason
        )
    }

    fun markDispatchSending(accountId: Long, owner: TaskType, taskKey: String, formationId: Long, nowMillis: Long) {
        if (!store.enforceCommandGate) return
        store.markFormationDispatching(accountId, owner, taskKey, formationId, nowMillis, nowMillis + defaultBusyLeaseMillis)
    }

    fun markDispatchAccepted(accountId: Long, owner: TaskType, taskKey: String, formationId: Long, nowMillis: Long) {
        if (!store.enforceCommandGate) return
        store.markFormationBusyAfterDispatch(accountId, owner, taskKey, formationId, nowMillis, nowMillis + defaultBusyLeaseMillis)
    }

    fun releaseReservation(accountId: Long, owner: TaskType, taskKey: String) {
        if (!store.enforceCommandGate) return
        store.releaseTaskReservations(accountId, owner, taskKey)
    }

    fun releaseTask(accountId: Long, owner: TaskType) {
        if (!store.enforceCommandGate) return
        store.releaseTaskLeases(accountId, owner)
    }

    fun markStopping(accountId: Long) { if (store.enforceCommandGate) store.setAccountState(accountId, AccountRunState.STOPPING) }
    fun markLoggedOut(accountId: Long) { if (store.enforceCommandGate) store.setAccountState(accountId, AccountRunState.LOGGED_OUT) }
    fun markSessionExpired(accountId: Long) { if (store.enforceCommandGate) store.setAccountState(accountId, AccountRunState.SESSION_EXPIRED) }

    private companion object {
        const val COMMAND_CLAIM_MILLIS = 15_000L
    }
}
