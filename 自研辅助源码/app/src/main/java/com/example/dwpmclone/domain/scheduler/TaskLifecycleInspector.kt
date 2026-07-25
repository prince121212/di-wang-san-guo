package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.protocol.TaskDecision

/**
 * Pure lifecycle helpers shared by scheduler and service logging.
 *
 * A terminal task decision means the local automation run should not keep pretending the task is
 * active. The explicit `TaskScheduler.runOnceAndStopOnTerminal` entry performs stop/logout, while
 * foreground-service ticks can use this object to emit auditable terminal-decision logs without
 * unexpectedly logging out on every ordinary background tick.
 */
object TaskLifecycleInspector {
    /** Account-level terminal decisions. Only an invalid session requires stop-all/logout. */
    fun terminalDecisions(reports: List<TaskRunReport>): List<TerminalTaskDecision> =
        reports.mapNotNull { report ->
            val decision = report.decisions.lastOrNull()?.takeIf { it.isTerminalForLogout() }
            decision?.let { TerminalTaskDecision(report.accountId, report.type, it) }
        }

    /** Ordinary task completion/failure stops only that task and keeps the account online. */
    fun localStopDecisions(reports: List<TaskRunReport>): List<TerminalTaskDecision> =
        reports.mapNotNull { report ->
            val decision = report.decisions.lastOrNull()?.takeIf { it is TaskDecision.Stop }
            decision?.let { TerminalTaskDecision(report.accountId, report.type, it) }
        }

    fun terminalSummary(terminals: List<TerminalTaskDecision>): String =
        terminals.joinToString { "${it.type.name}=${it.decision.lifecycleSummary()}" }

    fun terminalLogLine(tick: Int, terminal: TerminalTaskDecision): String =
        "tick=$tick TERMINAL account=${terminal.accountId} type=${terminal.type.name} decision=${terminal.decision.lifecycleSummary()} lifecycleRequiresStopLogout=true"

    fun TaskDecision.isTerminalForLogout(): Boolean =
        this is TaskDecision.NeedRelogin

    fun TaskDecision.lifecycleSummary(): String = when (this) {
        TaskDecision.Continue -> "Continue"
        is TaskDecision.Sleep -> "Sleep(${millis}ms)"
        is TaskDecision.RetryAfter -> "RetryAfter(${millis}ms)"
        is TaskDecision.NeedRelogin -> "NeedRelogin($reason)"
        is TaskDecision.Stop -> "Stop($reason)"
    }
}
