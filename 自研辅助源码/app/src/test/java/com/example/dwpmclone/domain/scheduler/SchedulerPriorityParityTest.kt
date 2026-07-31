package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.SessionAwareGameProtocolClient
import com.example.dwpmclone.domain.model.FormationConfig
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.protocol.AssistantBehaviorContract
import com.example.dwpmclone.domain.protocol.AssistantTask
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import com.example.dwpmclone.domain.protocol.TaskType
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SchedulerPriorityParityTest {
    private val scheduler = TaskScheduler(
        protocol = SessionAwareGameProtocolClient(offlineActionFixturesAllowed = true),
        behaviorContract = AssistantBehaviorContract.defaults()
    )

    @Test
    fun everyTaskTypeBelongsToTheDesktopEquivalentLane() {
        val contract = AssistantBehaviorContract.defaults().scheduler
        val byLane = TaskType.entries.groupBy { SchedulerTaskOrdering.lane(it, contract) }

        assertEquals(
            setOf(
                TaskType.FORMATION,
                TaskType.AUTO_MINING,
                TaskType.LOSSLESS,
                TaskType.SHUA_HUANG,
                TaskType.AUTO_LOOT,
                TaskType.DUNGEON
            ),
            byLane[SchedulerTaskLane.MILITARY].orEmpty().toSet()
        )
        assertEquals(
            setOf(TaskType.STATE_REFRESH, TaskType.ALARM),
            byLane[SchedulerTaskLane.OBSERVATION].orEmpty().toSet()
        )
        assertEquals(
            TaskType.entries.toSet() -
                byLane[SchedulerTaskLane.MILITARY].orEmpty().toSet() -
                byLane[SchedulerTaskLane.OBSERVATION].orEmpty().toSet(),
            byLane[SchedulerTaskLane.IDLE].orEmpty().toSet()
        )
    }

    @Test
    fun explicitFormationThenMilitaryResidentsRunBeforeIdleDailyWork() {
        val accountId = 77L
        val formationTwo = formationTask(accountId, 2L)
        val formationOne = formationTask(accountId, 1L)
        val tasks = listOf(
            PriorityStubTask(accountId, TaskType.DUNGEON),
            formationTwo,
            PriorityStubTask(accountId, TaskType.LOSSLESS),
            PriorityStubTask(accountId, TaskType.AUTO_LOOT),
            PriorityStubTask(accountId, TaskType.DAILY_SIGN_IN),
            PriorityStubTask(accountId, TaskType.BANDIT_PREFETCH),
            PriorityStubTask(accountId, TaskType.MINE_PREFETCH),
            PriorityStubTask(accountId, TaskType.STATE_REFRESH),
            PriorityStubTask(accountId, TaskType.SHUA_HUANG),
            PriorityStubTask(accountId, TaskType.AUTO_MINING),
            formationOne,
            PriorityStubTask(accountId, TaskType.SIX_MINISTRIES),
            PriorityStubTask(accountId, TaskType.DUNGEON)
        )

        val ordered = scheduler.uniqueTasksForAccount(accountId, tasks)

        assertEquals(
            listOf(
                TaskType.FORMATION,
                TaskType.FORMATION,
                TaskType.AUTO_MINING,
                TaskType.LOSSLESS,
                TaskType.SHUA_HUANG,
                TaskType.AUTO_LOOT,
                TaskType.DUNGEON,
                TaskType.STATE_REFRESH,
                TaskType.MINE_PREFETCH,
                TaskType.BANDIT_PREFETCH,
                TaskType.SIX_MINISTRIES,
                TaskType.DAILY_SIGN_IN
            ),
            ordered.map { it.type }
        )
        assertEquals(
            listOf(2L, 1L),
            ordered.filterIsInstance<FormationUpdateTask>().map { it.config.formationId }
        )
    }

    @Test
    fun sleepingHigherPriorityResidentDoesNotBlockLowerResident() {
        val calls = mutableListOf<TaskType>()
        val high = PriorityStubTask(77L, TaskType.AUTO_MINING, calls, TaskDecision.Sleep(60_000L))
        val low = PriorityStubTask(77L, TaskType.DUNGEON, calls, TaskDecision.Sleep(60_000L))
        val session = GameSession(77L, "token", null, emptyMap(), sourceMode = 1)

        val reports = SuspendRunner.run {
            scheduler.runOnce(session, listOf(low, high), nowMillis = 1_000L)
        }

        assertEquals(listOf(TaskType.AUTO_MINING, TaskType.DUNGEON), calls)
        assertEquals(2, reports.size)
        assertTrue(reports.all { it.decisions.last() is TaskDecision.Sleep })
    }

    @Test
    fun dueMilitaryBatchRunsObservationButDefersIdleLane() {
        val calls = mutableListOf<TaskType>()
        val session = GameSession(77L, "token", null, emptyMap(), sourceMode = 1)
        val tasks = listOf(
            PriorityStubTask(77L, TaskType.DAILY_DONATE, calls),
            PriorityStubTask(77L, TaskType.STATE_REFRESH, calls),
            PriorityStubTask(77L, TaskType.BANDIT_PREFETCH, calls),
            PriorityStubTask(77L, TaskType.DUNGEON, calls)
        )

        val reports = SuspendRunner.run {
            scheduler.runOnce(session, tasks, nowMillis = 1_000L)
        }

        assertEquals(
            listOf(TaskType.DUNGEON, TaskType.STATE_REFRESH),
            calls
        )
        assertEquals(
            listOf(TaskType.DUNGEON, TaskType.STATE_REFRESH),
            reports.map { it.type }
        )
    }

    @Test
    fun idleLaneRunsOneTaskPerBatchSoMilitaryDeadlinesAreRecheckedBetweenTasks() {
        val calls = mutableListOf<TaskType>()
        val session = GameSession(77L, "token", null, emptyMap(), sourceMode = 1)
        val tasks = listOf(
            PriorityStubTask(77L, TaskType.DAILY_DONATE, calls),
            PriorityStubTask(77L, TaskType.BANDIT_PREFETCH, calls)
        )

        val firstReports = SuspendRunner.run {
            scheduler.runOnce(session, tasks, nowMillis = 1_000L)
        }
        val secondReports = SuspendRunner.run {
            scheduler.runOnce(session, tasks, nowMillis = 2_000L)
        }

        assertEquals(
            listOf(TaskType.BANDIT_PREFETCH, TaskType.DAILY_DONATE),
            calls
        )
        assertEquals(listOf(TaskType.BANDIT_PREFETCH), firstReports.map { it.type })
        assertEquals(listOf(TaskType.DAILY_DONATE), secondReports.map { it.type })
    }

    @Test
    fun cooldownStartsWhenTheLongRunningTaskFinishesNotWhenTheTickStarted() {
        val accountId = 77L
        val task = PriorityStubTask(
            accountId,
            TaskType.DUNGEON,
            stepDecision = TaskDecision.Sleep(30_000L)
        )
        val scheduler = TaskScheduler(
            protocol = SessionAwareGameProtocolClient(offlineActionFixturesAllowed = true),
            behaviorContract = AssistantBehaviorContract.defaults(),
            clockMillis = { 100_000L }
        )
        val session = GameSession(accountId, "token", null, emptyMap(), sourceMode = 1)

        val report = SuspendRunner.run {
            scheduler.runOnce(session, listOf(task), nowMillis = 1_000L)
        }.single()
        val suppressions = TaskRunSuppressionRegistry()
        suppressions.record(report, requireNotNull(report.completedAtMillis))

        assertEquals(100_000L, report.completedAtMillis)
        assertTrue(suppressions.filter(accountId, listOf(task), 129_999L).isEmpty())
        assertEquals(listOf(task), suppressions.filter(accountId, listOf(task), 130_000L))
    }

    @Test
    fun revokedExecutionStopsTheBatchBeforeTheNextTaskAndDropsTheStaleReport() {
        var executionAllowed = true
        val calls = mutableListOf<TaskType>()
        val scheduler = TaskScheduler(
            protocol = SessionAwareGameProtocolClient(offlineActionFixturesAllowed = true),
            behaviorContract = AssistantBehaviorContract.defaults(),
            executionAllowed = { executionAllowed }
        )
        val session = GameSession(77L, "token", null, emptyMap(), sourceMode = 1)
        val tasks = listOf(
            PriorityStubTask(
                77L,
                TaskType.AUTO_MINING,
                calls,
                onStep = { executionAllowed = false }
            ),
            PriorityStubTask(77L, TaskType.DUNGEON, calls)
        )

        val reports = SuspendRunner.run {
            scheduler.runOnce(session, tasks, nowMillis = 1_000L)
        }

        assertEquals(listOf(TaskType.AUTO_MINING), calls)
        assertTrue(reports.isEmpty())
    }

    private fun formationTask(accountId: Long, formationId: Long) = FormationUpdateTask(
        accountId,
        FormationConfig(
            formationId = formationId,
            generalIds = listOf(formationId),
            autoAssignTroops = false,
            troopType = "轻骑兵",
            troopCount = 200,
            fillToMaxWhenAutoAssignDisabled = false
        )
    )
}

private class PriorityStubTask(
    override val accountId: Long,
    override val type: TaskType,
    private val calls: MutableList<TaskType>? = null,
    private val stepDecision: TaskDecision = TaskDecision.Sleep(1_000L),
    private val onStep: () -> Unit = {}
) : AssistantTask<Unit> {
    override val config: Unit = Unit

    override suspend fun prepare(ctx: TaskContext): TaskDecision = TaskDecision.Continue

    override suspend fun step(ctx: TaskContext): TaskDecision {
        calls?.add(type)
        onStep()
        return stepDecision
    }

    override suspend fun recover(ctx: TaskContext, error: Throwable): TaskDecision =
        TaskDecision.RetryAfter(1_000L)

    override suspend fun stop(ctx: TaskContext, reason: String) = Unit
}
