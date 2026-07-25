package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType
import org.junit.Assert.assertEquals
import org.junit.Test

class TaskLifecycleInspectorTest {
    @Test
    fun accountTerminalOnlyIncludesNeedReloginAndStopRemainsTaskLocal() {
        val reports = listOf(
            TaskRunReport(1L, TaskType.SHUA_HUANG, listOf(TaskDecision.Continue, TaskDecision.Sleep(1_000))),
            TaskRunReport(2L, TaskType.DAILY, listOf(TaskDecision.Continue, TaskDecision.Stop("done"))),
            TaskRunReport(3L, TaskType.MINE_SEARCH, listOf(TaskDecision.NeedRelogin("expired"))),
            TaskRunReport(4L, TaskType.GENERAL, listOf(TaskDecision.RetryAfter(10_000)))
        )

        val terminal = TaskLifecycleInspector.terminalDecisions(reports)

        assertEquals(1, terminal.size)
        assertEquals(TaskType.MINE_SEARCH, terminal.single().type)
        assertEquals(TaskDecision.NeedRelogin("expired"), terminal.single().decision)
        val localStops = TaskLifecycleInspector.localStopDecisions(reports)
        assertEquals(1, localStops.size)
        assertEquals(TaskType.DAILY, localStops.single().type)
        assertEquals(TaskDecision.Stop("done"), localStops.single().decision)
    }

    @Test
    fun terminalSummaryAndLogLineAreStableForServiceAudit() {
        val terminal = listOf(
            TerminalTaskDecision(123L, TaskType.SHUA_HUANG, TaskDecision.Stop("daily limit"))
        )

        assertEquals(
            "SHUA_HUANG=Stop(daily limit)",
            TaskLifecycleInspector.terminalSummary(terminal)
        )
        assertEquals(
            "tick=7 TERMINAL account=123 type=SHUA_HUANG decision=Stop(daily limit) lifecycleRequiresStopLogout=true",
            TaskLifecycleInspector.terminalLogLine(7, terminal.single())
        )
    }
}
