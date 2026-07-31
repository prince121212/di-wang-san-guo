package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TaskRuntimeStatusTest {
    @Test
    fun sleepPersistsAnAbsoluteNextRunTimeAndCountdown() {
        val status = TaskRuntimeStatusMapper.fromReport(
            TaskRunReport(
                accountId = 7L,
                type = TaskType.DUNGEON,
                decisions = listOf(TaskDecision.Continue, TaskDecision.Sleep(60_000))
            ),
            nowMillis = 1_000,
            tick = 8
        )

        assertEquals(TaskRuntimeState.SLEEPING, status.state)
        assertEquals(61_000L, status.nextRunAtMillis)
        assertEquals(8, status.tick)
        assertEquals("等待 30秒", status.displayText(31_000))
    }

    @Test
    fun retryStopReloginAndErrorsRemainDistinguishable() {
        val retry = TaskRuntimeStatusMapper.fromReport(
            TaskRunReport(
                7L,
                TaskType.DUNGEON,
                listOf(TaskDecision.RetryAfter(10_000, "副本等待前序条件"))
            ),
            5_000
        )
        val stop = TaskRuntimeStatusMapper.fromReport(
            TaskRunReport(7L, TaskType.DAILY, listOf(TaskDecision.Stop("done"))),
            5_000
        )
        val relogin = TaskRuntimeStatusMapper.fromReport(
            TaskRunReport(7L, TaskType.DAILY, listOf(TaskDecision.NeedRelogin("expired"))),
            5_000
        )
        val error = TaskRuntimeStatusMapper.fromReport(
            TaskRunReport(7L, TaskType.DAILY, emptyList(), error = "boom"),
            5_000
        )

        assertEquals(TaskRuntimeState.RETRYING, retry.state)
        assertEquals(15_000L, retry.nextRunAtMillis)
        assertEquals("副本等待前序条件", retry.message)
        assertEquals(TaskRuntimeState.STOPPED, stop.state)
        assertNull(stop.nextRunAtMillis)
        assertEquals("done", stop.message)
        assertEquals(TaskRuntimeState.NEED_RELOGIN, relogin.state)
        assertEquals("expired", relogin.message)
        assertEquals(TaskRuntimeState.ERROR, error.state)
        assertEquals("boom", error.message)
    }

    @Test
    fun activeDungeonPollDelayRemainsRunning() {
        val status = TaskRuntimeStatusMapper.fromReport(
            TaskRunReport(
                accountId = 7L,
                type = TaskType.DUNGEON,
                decisions = listOf(
                    TaskDecision.Continue,
                    TaskDecision.Sleep(
                        millis = 10_000,
                        keepRunning = true,
                        reason = "副本第5章第6关战斗中"
                    )
                )
            ),
            nowMillis = 1_000
        )

        assertEquals(TaskRuntimeState.RUNNING, status.state)
        assertEquals(11_000L, status.nextRunAtMillis)
        assertEquals("副本第5章第6关战斗中", status.message)
    }

    @Test
    fun recoveredExceptionKeepsRetryDeadlineAcrossProcessRecreation() {
        val status = TaskRuntimeStatusMapper.fromReport(
            TaskRunReport(
                7L,
                TaskType.DAILY,
                listOf(TaskDecision.RetryAfter(10_000)),
                error = "temporary network error"
            ),
            nowMillis = 5_000
        )

        assertEquals(TaskRuntimeState.RETRYING, status.state)
        assertEquals(15_000L, status.nextRunAtMillis)
        assertEquals(true, status.message.contains("temporary network error"))
    }
}
