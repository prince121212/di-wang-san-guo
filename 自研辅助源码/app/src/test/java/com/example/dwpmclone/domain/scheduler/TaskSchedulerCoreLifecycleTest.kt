package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.protocol.AssistantTask
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.StepResult
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TaskSchedulerCoreLifecycleTest {
    @Test
    fun duplicateTaskTypeForSameAccountRunsOnlyOncePerBatch() {
        val scheduler = TaskScheduler(MockGameProtocolClient())
        val session = session()
        val first = RecordingTask(session.accountId)
        val duplicate = RecordingTask(session.accountId)

        val reports = SuspendRunner.run {
            scheduler.runOnce(session, listOf(first, duplicate), nowMillis = 1_000L)
        }

        assertEquals(1, reports.size)
        assertEquals(1, first.prepareCount)
        assertEquals(1, first.stepCount)
        assertEquals(0, duplicate.prepareCount)
        assertEquals(0, duplicate.stepCount)
    }

    @Test
    fun stopAllStopsTasksAndLogsOutExactlyOnce() {
        val protocol = LogoutRecordingProtocol()
        val scheduler = TaskScheduler(protocol)
        val task = RecordingTask(accountId = 123L)

        val report = SuspendRunner.run {
            scheduler.stopAll(session(), listOf(task), "unit stop")
        }

        assertEquals(123L, report.accountId)
        assertEquals(listOf(TaskType.SHUA_HUANG), report.stoppedTaskTypes)
        assertTrue(report.logoutRequested)
        assertTrue(report.logoutSucceeded)
        assertEquals("unit stop", task.stoppedReason)
        assertEquals(1, protocol.logoutCount)
    }

    private fun session() = GameSession(
        accountId = 123L,
        tokenCiphertext = "unit-token",
        expiresAtMillis = null,
        channelExtra = emptyMap(),
        sourceMode = 0,
    )
}

private class RecordingTask(
    override val accountId: Long,
) : AssistantTask<Unit> {
    override val type: TaskType = TaskType.SHUA_HUANG
    override val config: Unit = Unit
    var stoppedReason: String? = null
    var prepareCount: Int = 0
    var stepCount: Int = 0

    override suspend fun prepare(ctx: TaskContext): TaskDecision {
        prepareCount += 1
        return TaskDecision.Continue
    }

    override suspend fun step(ctx: TaskContext): TaskDecision {
        stepCount += 1
        return TaskDecision.Continue
    }

    override suspend fun recover(ctx: TaskContext, error: Throwable): TaskDecision =
        TaskDecision.Stop(error.message ?: "error")

    override suspend fun stop(ctx: TaskContext, reason: String) {
        stoppedReason = reason
    }
}

private class LogoutRecordingProtocol(
    private val delegate: GameProtocolClient = MockGameProtocolClient(),
) : GameProtocolClient by delegate {
    var logoutCount = 0

    override suspend fun logout(session: GameSession): ProtocolResult<StepResult> {
        logoutCount += 1
        return delegate.logout(session)
    }
}
