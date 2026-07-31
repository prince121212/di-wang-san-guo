package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.protocol.AssistantBehaviorContract
import com.example.dwpmclone.domain.protocol.AssistantTask
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.state.AutomationRuntimeStateStore
import com.example.dwpmclone.domain.localmap.LocalTargetCache
import com.example.dwpmclone.domain.state.DailyCompletionStore
import com.example.dwpmclone.domain.state.InMemoryDailyCompletionStore

/** Sequential per-account scheduler; task actions remain gated by GameProtocolClient and command leases. */
class TaskScheduler(
    private val protocol: GameProtocolClient,
    val runtime: AutomationRuntimeStateStore = AutomationRuntimeStateStore(),
    private val localMap: LocalTargetCache = LocalTargetCache(),
    private val promptSink: ((Long, TaskType, String) -> Unit)? = null,
    private val dailyCompletions: DailyCompletionStore = InMemoryDailyCompletionStore(),
    private val behaviorContract: AssistantBehaviorContract = AssistantBehaviorContract.defaults(),
    private val successSink: ((Long, String, String) -> Unit)? = null,
    private val clockMillis: () -> Long = System::currentTimeMillis,
    /** Foreground service ownership is checked between tasks; tests/manual callers default true. */
    private val executionAllowed: () -> Boolean = { true }
) {
    /**
     * Desktop tasks compete for the account command center between requests. Android cannot
     * preempt one in-flight request, so it runs at most one idle mutation per batch and then
     * rebuilds the due set. This prevents a military deadline that expires mid-batch from
     * waiting behind every daily/maintenance task.
     */
    private val idleLaneCursorByAccount = linkedMapOf<Long, Int>()

    suspend fun runOnce(
        session: GameSession,
        tasks: List<AssistantTask<*>>,
        nowMillis: Long = System.currentTimeMillis()
    ): List<TaskRunReport> = runBatch(session, tasks, nowMillis).reports

    private suspend fun runBatch(
        session: GameSession,
        tasks: List<AssistantTask<*>>,
        nowMillis: Long
    ): SchedulerRunBatch {
        val ctx = TaskContext(
            session = session,
            protocol = protocol,
            nowMillis = nowMillis,
            runtime = runtime,
            localMap = localMap,
            promptSink = promptSink,
            dailyCompletions = dailyCompletions,
            behaviorContract = behaviorContract,
            successSink = successSink
        )
        val ordered = uniqueTasksForAccount(session.accountId, tasks)
        val hasDueMilitaryWork = ordered.any {
            SchedulerTaskOrdering.lane(it.type, behaviorContract.scheduler) ==
                SchedulerTaskLane.MILITARY
        }
        val dueIdleTasks = ordered.filter {
            SchedulerTaskOrdering.lane(it.type, behaviorContract.scheduler) ==
                SchedulerTaskLane.IDLE
        }
        val selectedIdleTask = if (
            !hasDueMilitaryWork &&
            behaviorContract.scheduler.idleLaneMustYieldToDueMilitaryWork &&
            dueIdleTasks.isNotEmpty()
        ) {
            val cursor = Math.floorMod(
                idleLaneCursorByAccount[session.accountId] ?: 0,
                dueIdleTasks.size
            )
            idleLaneCursorByAccount[session.accountId] = cursor + 1
            dueIdleTasks[cursor]
        } else {
            null
        }
        val reports = mutableListOf<TaskRunReport>()
        var deferredIdleTaskCount = 0
        for (task in ordered) {
            if (!executionAllowed()) break
            val lane = SchedulerTaskOrdering.lane(task.type, behaviorContract.scheduler)
            if (lane == SchedulerTaskLane.IDLE &&
                behaviorContract.scheduler.idleLaneMustYieldToDueMilitaryWork &&
                (hasDueMilitaryWork || task !== selectedIdleTask)
            ) {
                deferredIdleTaskCount += 1
                continue
            }
            val report = runTaskOnce(ctx, task)
            // A stop that arrived during this task owns the final visible state. Do not return a
            // stale report that the service could write back over its "后台已停止" task stack.
            if (!executionAllowed()) break
            reports += report
        }
        return SchedulerRunBatch(reports, deferredIdleTaskCount)
    }

    /**
     * Mirrors the desktop registry and command-center order. Resident tasks are unique by
     * type, while every distinct saved formation must run because one account can own many
     * formation rows.
     */
    internal fun uniqueTasksForAccount(
        accountId: Long,
        tasks: List<AssistantTask<*>>
    ): List<AssistantTask<*>> {
        val seen = linkedSetOf<com.example.dwpmclone.domain.protocol.TaskType>()
        val seenFormationIds = linkedSetOf<Long>()
        val unique = tasks.filter { task ->
            if (task.accountId != accountId) return@filter false
            if (task.type == TaskType.FORMATION) {
                val formationId = (task.config as? com.example.dwpmclone.domain.model.FormationConfig)
                    ?.formationId
                formationId == null || seenFormationIds.add(formationId)
            } else {
                seen.add(task.type)
            }
        }
        return SchedulerTaskOrdering.order(unique, behaviorContract.scheduler)
    }

    /**
     * Explicit closed-loop entry for one-account automation runs.
     *
     * `runOnce` intentionally preserves service tick compatibility and only reports decisions.
     * This method is stricter: if any task reaches a terminal decision (`Stop` or `NeedRelogin`),
     * it invokes every task's stop hook and logs out the session before returning.
     */
    suspend fun runOnceAndStopOnTerminal(
        session: GameSession,
        tasks: List<AssistantTask<*>>,
        nowMillis: Long = System.currentTimeMillis(),
        reasonPrefix: String = "terminal task decision"
    ): TaskLifecycleReport {
        val batch = runBatch(session, tasks, nowMillis)
        val runReports = batch.reports
        val localStops = TaskLifecycleInspector.localStopDecisions(runReports)
        val localStopReports = localStops.mapNotNull { terminal ->
            val task = tasks.firstOrNull { it.accountId == terminal.accountId && it.type == terminal.type }
                ?: return@mapNotNull null
            val reason = "task decision: ${terminal.decision}"
            task.stop(
                TaskContext(
                    session,
                    protocol,
                    nowMillis,
                    runtime,
                    localMap,
                    promptSink,
                    dailyCompletions,
                    behaviorContract
                ),
                reason
            )
            runtime.commandGate.releaseTask(session.accountId, task.type)
            TaskLocalStopReport(session.accountId, task.type, reason)
        }
        val terminal = TaskLifecycleInspector.terminalDecisions(runReports)
        val stopReport = if (terminal.isNotEmpty()) {
            val reason = reasonPrefix + ": " + TaskLifecycleInspector.terminalSummary(terminal)
            stopAll(session, tasks, reason)
        } else {
            null
        }
        return TaskLifecycleReport(
            runReports,
            terminal,
            stopReport,
            localStopReports,
            deferredIdleTaskCount = batch.deferredIdleTaskCount
        )
    }

    private suspend fun runTaskOnce(ctx: TaskContext, task: AssistantTask<*>): TaskRunReport {
        val decisions = mutableListOf<TaskDecision>()
        return try {
            val prepare = task.prepare(ctx)
            decisions += prepare
            if (prepare == TaskDecision.Continue) {
                decisions += task.step(ctx)
            }
            TaskRunReport(
                task.accountId,
                task.type,
                decisions,
                completedAtMillis = clockMillis()
            )
        } catch (t: Throwable) {
            val recovered = task.recover(ctx, t)
            decisions += recovered
            TaskRunReport(
                task.accountId,
                task.type,
                decisions,
                error = t.message,
                completedAtMillis = clockMillis()
            )
        }
    }

    suspend fun stopAll(
        session: GameSession,
        tasks: List<AssistantTask<*>>,
        reason: String
    ): TaskStopReport {
        runtime.commandGate.markStopping(session.accountId)
        tasks.forEach { task ->
            task.stop(
                TaskContext(
                    session,
                    protocol,
                    System.currentTimeMillis(),
                    runtime,
                    localMap,
                    promptSink,
                    dailyCompletions,
                    behaviorContract
                ),
                reason
            )
            runtime.commandGate.releaseTask(session.accountId, task.type)
        }
        val logout = protocol.logout(session)
        runtime.commandGate.markLoggedOut(session.accountId)
        return TaskStopReport(
            accountId = session.accountId,
            stoppedTaskTypes = tasks.map { it.type },
            logoutRequested = true,
            logoutSucceeded = logout is com.example.dwpmclone.domain.protocol.ProtocolResult.Ok,
            logoutMessage = when (logout) {
                is com.example.dwpmclone.domain.protocol.ProtocolResult.Ok -> logout.value.message
                is com.example.dwpmclone.domain.protocol.ProtocolResult.Err -> logout.message
            }
        )
    }

}

private data class SchedulerRunBatch(
    val reports: List<TaskRunReport>,
    val deferredIdleTaskCount: Int
)

data class TaskRunReport(
    val accountId: Long,
    val type: TaskType,
    val decisions: List<TaskDecision>,
    val error: String? = null,
    /** Wall-clock time when this task produced its decision, not when the batch began. */
    val completedAtMillis: Long? = null
)

data class TaskStopReport(
    val accountId: Long,
    val stoppedTaskTypes: List<TaskType>,
    val logoutRequested: Boolean,
    val logoutSucceeded: Boolean,
    val logoutMessage: String
)

data class TerminalTaskDecision(
    val accountId: Long,
    val type: TaskType,
    val decision: TaskDecision
)

data class TaskLifecycleReport(
    val runReports: List<TaskRunReport>,
    val terminalDecisions: List<TerminalTaskDecision>,
    val stopReport: TaskStopReport?,
    val localStopReports: List<TaskLocalStopReport> = emptyList(),
    val deferredIdleTaskCount: Int = 0
) {
    val logoutRequested: Boolean
        get() = stopReport?.logoutRequested == true
}

data class TaskLocalStopReport(
    val accountId: Long,
    val type: TaskType,
    val reason: String
)
