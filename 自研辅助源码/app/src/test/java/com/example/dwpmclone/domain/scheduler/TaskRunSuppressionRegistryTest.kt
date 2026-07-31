package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.protocol.AssistantTask
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotEquals
import org.junit.Test

class TaskRunSuppressionRegistryTest {
    @Test
    fun localStopRemainsSuppressedUntilConfigurationChanges() {
        val registry = TaskRunSuppressionRegistry()
        val daily = StubTask(7L, TaskType.DAILY)
        val brush = StubTask(7L, TaskType.SHUA_HUANG)
        registry.onConfiguration("config-v1")
        registry.suppress(TaskLocalStopReport(7L, TaskType.DAILY, "done"))

        assertEquals(listOf(TaskType.SHUA_HUANG), registry.filter(7L, listOf(daily, brush)).map { it.type })
        registry.onConfiguration("config-v1")
        assertEquals(listOf(TaskType.SHUA_HUANG), registry.filter(7L, listOf(daily, brush)).map { it.type })
        registry.onConfiguration("config-v2")
        assertEquals(listOf(TaskType.DAILY, TaskType.SHUA_HUANG), registry.filter(7L, listOf(daily, brush)).map { it.type })
    }

    @Test
    fun sleepAndRetryDecisionsAreNotReexecutedBeforeDueTime() {
        val registry = TaskRunSuppressionRegistry()
        val brush = StubTask(7L, TaskType.SHUA_HUANG)
        registry.onConfiguration("config-v1")
        registry.record(
            TaskRunReport(
                7L,
                TaskType.SHUA_HUANG,
                listOf(TaskDecision.Continue, TaskDecision.Sleep(60_000))
            ),
            nowMillis = 1_000
        )

        assertEquals(61_000L, registry.nextRunAt(7L, TaskType.SHUA_HUANG))
        assertEquals(61_000L, registry.earliestNextRunAtMillis())
        assertEquals(emptyList<TaskType>(), registry.filter(7L, listOf(brush), 60_999).map { it.type })
        assertEquals(listOf(TaskType.SHUA_HUANG), registry.filter(7L, listOf(brush), 61_000).map { it.type })

        registry.record(
            TaskRunReport(7L, TaskType.SHUA_HUANG, listOf(TaskDecision.Continue)),
            nowMillis = 61_000
        )
        assertNull(registry.nextRunAt(7L, TaskType.SHUA_HUANG))
        assertNull(registry.earliestNextRunAtMillis())
    }

    @Test
    fun configurationChangeClearsBothStopAndDueState() {
        val registry = TaskRunSuppressionRegistry()
        val daily = StubTask(7L, TaskType.DAILY)
        registry.onConfiguration("config-v1")
        registry.record(
            TaskRunReport(7L, TaskType.DAILY, listOf(TaskDecision.RetryAfter(10_000))),
            nowMillis = 5_000
        )
        assertEquals(emptyList<TaskType>(), registry.filter(7L, listOf(daily), 5_001).map { it.type })

        registry.onConfiguration("config-v2")

        assertNull(registry.nextRunAt(7L, TaskType.DAILY))
        assertEquals(listOf(TaskType.DAILY), registry.filter(7L, listOf(daily), 5_001).map { it.type })
    }

    @Test
    fun persistedDeadlineAndStopRestoreOnlyForMatchingConfiguration() {
        val signature = TaskRunSuppressionRegistry.configurationSignature("config-v1")
        val statuses = listOf(
            TaskRuntimeStatus(
                7L,
                TaskType.SHUA_HUANG,
                TaskRuntimeState.SERVICE_STOPPED,
                "service recreated",
                updatedAtMillis = 1_000L,
                nextRunAtMillis = 61_000L
            ),
            TaskRuntimeStatus(
                7L,
                TaskType.DAILY,
                TaskRuntimeState.STOPPED,
                "completed",
                updatedAtMillis = 1_000L
            )
        )
        val tasks = listOf(
            StubTask(7L, TaskType.SHUA_HUANG),
            StubTask(7L, TaskType.DAILY)
        )

        val restored = TaskRunSuppressionRegistry().apply {
            restore(signature, signature, statuses, nowMillis = 2_000L)
        }
        assertEquals(emptyList<TaskType>(), restored.filter(7L, tasks, 2_000L).map { it.type })
        assertEquals(listOf(TaskType.SHUA_HUANG), restored.filter(7L, tasks, 61_000L).map { it.type })

        val changed = TaskRunSuppressionRegistry().apply {
            restore("other-signature", signature, statuses, nowMillis = 2_000L)
        }
        assertEquals(tasks.map { it.type }, changed.filter(7L, tasks, 2_000L).map { it.type })
        assertNotEquals(signature, TaskRunSuppressionRegistry.configurationSignature("config-v2"))
    }
}

private class StubTask(
    override val accountId: Long,
    override val type: TaskType
) : AssistantTask<Unit> {
    override val config: Unit = Unit
    override suspend fun prepare(ctx: TaskContext): TaskDecision = TaskDecision.Continue
    override suspend fun step(ctx: TaskContext): TaskDecision = TaskDecision.Continue
    override suspend fun recover(ctx: TaskContext, error: Throwable): TaskDecision = TaskDecision.Stop("error")
    override suspend fun stop(ctx: TaskContext, reason: String) = Unit
}
