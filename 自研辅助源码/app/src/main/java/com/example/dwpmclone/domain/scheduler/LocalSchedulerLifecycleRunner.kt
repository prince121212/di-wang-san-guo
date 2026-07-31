package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.protocol.TaskType

/**
 * Service-facing lifecycle runner.
 *
 * The Android foreground service should not reimplement terminal-decision policy.  This
 * pure Kotlin helper gives the service a single explicit entry that mirrors the intended
 * brush-yellow lifecycle: run a tick, and if a task asks to Stop/NeedRelogin, stop all
 * tasks for that account and logout through TaskScheduler before returning.
 */
class LocalSchedulerLifecycleRunner(
    private val scheduler: TaskScheduler
) {
    suspend fun runPlansOnceAndStopOnTerminal(
        tick: Int,
        plans: List<SavedTaskPlan>,
        nowMillis: Long = System.currentTimeMillis(),
        reasonPrefix: String = "service lifecycle tick",
        beforeAccount: (Long) -> Unit = {},
        afterAccount: (Long) -> Unit = {}
    ): LocalSchedulerLifecycleBatchReport {
        val accountReports = plans.map { plan ->
            val accountId = plan.session.accountId
            beforeAccount(accountId)
            try {
                val lifecycle = scheduler.runOnceAndStopOnTerminal(
                    session = plan.session,
                    tasks = plan.tasks,
                    nowMillis = nowMillis,
                    reasonPrefix = "$reasonPrefix=$tick source=${plan.sourceDescription}"
                )
                LocalSchedulerAccountLifecycleReport(
                    accountId = accountId,
                    sourceMode = plan.session.sourceMode,
                    sourceDescription = plan.sourceDescription,
                    taskTypes = plan.tasks.map { it.type },
                    lifecycleReport = lifecycle
                )
            } finally {
                afterAccount(accountId)
            }
        }
        return LocalSchedulerLifecycleBatchReport(tick, accountReports)
    }
}

data class LocalSchedulerLifecycleBatchReport(
    val tick: Int,
    val accounts: List<LocalSchedulerAccountLifecycleReport>
) {
    val runReports: List<TaskRunReport>
        get() = accounts.flatMap { it.lifecycleReport.runReports }
    val terminalDecisions: List<TerminalTaskDecision>
        get() = accounts.flatMap { it.lifecycleReport.terminalDecisions }
    val stopReports: List<TaskStopReport>
        get() = accounts.mapNotNull { it.lifecycleReport.stopReport }
    val localStopReports: List<TaskLocalStopReport>
        get() = accounts.flatMap { it.lifecycleReport.localStopReports }
    val deferredIdleTaskCount: Int
        get() = accounts.sumOf { it.lifecycleReport.deferredIdleTaskCount }
}

data class LocalSchedulerAccountLifecycleReport(
    val accountId: Long,
    val sourceMode: Int,
    val sourceDescription: String,
    val taskTypes: List<TaskType>,
    val lifecycleReport: TaskLifecycleReport
)
