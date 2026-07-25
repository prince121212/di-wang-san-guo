package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.protocol.AssistantTask
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.state.AutomationRuntimeStateStore
import com.example.dwpmclone.domain.cloud.CloudFirstMapCoordinator

/**
 * Minimal sequential scheduler for the static-evidence rebuild skeleton.
 *
 * It models scheduling decisions locally and does not execute production game mutations:
 * - one account/session owns multiple tasks;
 * - each task has prepare -> step -> recover -> stop hooks;
 * - real anti-ban delays, same-server mutexes, reconnection and protocol calls belong
 *   behind lawful implementations of GameProtocolClient / production scheduler policies.
 */
class TaskScheduler(
    private val protocol: GameProtocolClient,
    val runtime: AutomationRuntimeStateStore = AutomationRuntimeStateStore(),
    private val cloudMap: CloudFirstMapCoordinator = CloudFirstMapCoordinator(),
    private val promptSink: ((Long, TaskType, String) -> Unit)? = null
) {
    suspend fun runOnce(
        session: GameSession,
        tasks: List<AssistantTask<*>>,
        nowMillis: Long = System.currentTimeMillis()
    ): List<TaskRunReport> {
        val ctx = TaskContext(
            session = session,
            protocol = protocol,
            nowMillis = nowMillis,
            runtime = runtime,
            cloudMap = cloudMap,
            promptSink = promptSink
        )
        val reports = mutableListOf<TaskRunReport>()
        var formationFailure: TaskDecision? = null
        uniqueTasksForAccount(session.accountId, tasks).forEach { task ->
            if (formationFailure != null && task.type in FORMATION_DEPENDENT_TASKS) {
                reports += TaskRunReport(
                    accountId = task.accountId,
                    type = task.type,
                    decisions = listOf(
                        TaskDecision.Stop(
                            "blocked before ${task.type.name}: formation prerequisite=$formationFailure"
                        )
                    )
                )
                return@forEach
            }
            val report = runTaskOnce(ctx, task)
            reports += report
            if (task.type == TaskType.FORMATION) {
                val decision = report.decisions.lastOrNull()
                if (decision is TaskDecision.Stop ||
                    decision is TaskDecision.RetryAfter ||
                    decision is TaskDecision.NeedRelogin
                ) {
                    formationFailure = decision
                }
            }
        }
        return reports
    }

    /**
     * Mirrors the desktop task registry invariant: one account may not execute two
     * instances of the same task type in one scheduler batch. Keep the first configured
     * instance so repeated imports or duplicated UI containers cannot duplicate actions.
     */
    internal fun uniqueTasksForAccount(
        accountId: Long,
        tasks: List<AssistantTask<*>>
    ): List<AssistantTask<*>> {
        val seen = linkedSetOf<com.example.dwpmclone.domain.protocol.TaskType>()
        return tasks.filter { task ->
            task.accountId == accountId && seen.add(task.type)
        }
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
        val runReports = runOnce(session, tasks, nowMillis)
        val localStops = TaskLifecycleInspector.localStopDecisions(runReports)
        val localStopReports = localStops.mapNotNull { terminal ->
            val task = tasks.firstOrNull { it.accountId == terminal.accountId && it.type == terminal.type }
                ?: return@mapNotNull null
            val reason = "task decision: ${terminal.decision}"
            task.stop(TaskContext(session, protocol, nowMillis, runtime, cloudMap, promptSink), reason)
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
        return TaskLifecycleReport(runReports, terminal, stopReport, localStopReports)
    }

    private suspend fun runTaskOnce(ctx: TaskContext, task: AssistantTask<*>): TaskRunReport {
        val decisions = mutableListOf<TaskDecision>()
        return try {
            val prepare = task.prepare(ctx)
            decisions += prepare
            if (prepare == TaskDecision.Continue) {
                decisions += task.step(ctx)
            }
            TaskRunReport(task.accountId, task.type, decisions)
        } catch (t: Throwable) {
            val recovered = task.recover(ctx, t)
            decisions += recovered
            TaskRunReport(task.accountId, task.type, decisions, error = t.message)
        }
    }

    suspend fun stopAll(
        session: GameSession,
        tasks: List<AssistantTask<*>>,
        reason: String
    ): TaskStopReport {
        runtime.commandGate.markStopping(session.accountId)
        tasks.forEach { task ->
            task.stop(TaskContext(session, protocol, System.currentTimeMillis(), runtime, cloudMap, promptSink), reason)
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

    companion object {
        private val FORMATION_DEPENDENT_TASKS = setOf(
            TaskType.LOSSLESS,
            TaskType.SHUA_HUANG,
            TaskType.AUTO_MINING,
            TaskType.DUNGEON,
            TaskType.AUTO_LOOT
        )
    }

}

data class TaskRunReport(
    val accountId: Long,
    val type: TaskType,
    val decisions: List<TaskDecision>,
    val error: String? = null
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
    val localStopReports: List<TaskLocalStopReport> = emptyList()
) {
    val logoutRequested: Boolean
        get() = stopReport?.logoutRequested == true
}

data class TaskLocalStopReport(
    val accountId: Long,
    val type: TaskType,
    val reason: String
)
