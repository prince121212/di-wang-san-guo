package com.example.dwpmclone.ui.web

import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.scheduler.TaskRuntimeState
import com.example.dwpmclone.domain.scheduler.TaskRuntimeStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalTaskPresentationTest {
    @Test
    fun exposesEveryDesktopResidentAndDailyRowEvenWithoutRuntimeStatus() {
        assertEquals(
            listOf("mine", "lossless", "brushYellow", "raid", "dungeon", "general", "ministry", "domestic", "inventory"),
            LocalTaskPresentation.residentSpecs.map { it.key }
        )
        assertEquals(
            listOf(
                "autoSignIn",
                "arenaCoins",
                "autoDonate",
                "salary",
                "nationalCollect",
                "cityLordCollect",
                "generalVisit"
            ),
            LocalTaskPresentation.dailySpecs.map { it.key }
        )
    }

    @Test
    fun mapsWaitReloginAndTerminalStatesWithoutPretendingTheyAreRunning() {
        val retry = status(TaskRuntimeState.RETRYING)
        val relogin = status(TaskRuntimeState.NEED_RELOGIN)
        val stopped = status(TaskRuntimeState.STOPPED)

        assertEquals("queued", LocalTaskPresentation.schedulerState(retry))
        assertEquals("waiting_account", LocalTaskPresentation.schedulerState(relogin))
        assertTrue(LocalTaskPresentation.isActive(relogin))
        assertEquals("stopped", LocalTaskPresentation.schedulerState(stopped))
        assertFalse(LocalTaskPresentation.isActive(stopped))
    }

    @Test
    fun inactiveSchedulerDowngradesPersistedRunningStateToStopped() {
        val running = status(TaskRuntimeState.RUNNING)

        assertEquals(
            "stopped",
            LocalTaskPresentation.schedulerState(running, schedulerActive = false)
        )
        assertFalse(LocalTaskPresentation.isActive(running, schedulerActive = false))
        assertTrue(LocalTaskPresentation.isActive(running, schedulerActive = true))
    }

    @Test
    fun schedulerRequiresAccountSavedTasksAndExecutionOwnerTogether() {
        assertTrue(LocalTaskPresentation.schedulerActive(true, true, true))
        assertFalse(LocalTaskPresentation.schedulerActive(false, true, true))
        assertFalse(LocalTaskPresentation.schedulerActive(true, false, true))
        assertFalse(LocalTaskPresentation.schedulerActive(true, true, false))
    }

    @Test
    fun retiredKotlinRuntimeRowsNeverEnterCurrentProjection() {
        val retired = listOf(
            TaskType.STATE_REFRESH,
            TaskType.BANDIT_PREFETCH,
            TaskType.MINE_PREFETCH,
            TaskType.FOOD_TO_COPPER,
            TaskType.FORMATION,
        ).map { status(TaskRuntimeState.RUNNING, it) }

        retired.forEach { status ->
            assertTrue(LocalTaskPresentation.isRetiredRuntimeType(status.type))
            assertFalse(LocalTaskPresentation.isActive(status))
            assertFalse(LocalTaskPresentation.isTaskStackVisible(status, completed = false))
            assertEquals("stopped", LocalTaskPresentation.schedulerState(status))
        }
        assertTrue(LocalTaskPresentation.latestByKey(retired).isEmpty())
    }

    @Test
    fun dailyCompletionTurnsItsPersistedSleepIntoDailyDone() {
        val sleeping = status(TaskRuntimeState.SLEEPING, TaskType.DAILY_SIGN_IN)
        assertEquals("daily_done", LocalTaskPresentation.schedulerState(sleeping, completed = true))
    }

    @Test
    fun dailyCitizenSkipIsTerminalAndNotQueued() {
        val skipped = status(TaskRuntimeState.SLEEPING, TaskType.DAILY_SALARY).copy(
            skipped = true,
            skipReason = "national-citizen",
            statusText = "已做（国民跳过）",
            message = "国民跳过",
        )

        assertEquals("daily_done", LocalTaskPresentation.schedulerState(skipped))
        assertFalse(LocalTaskPresentation.isTaskStackVisible(skipped, completed = false))
        assertEquals("已做（国民跳过）", skipped.displayText())
    }

    @Test
    fun taskStackExcludesCompletedDailyRowsAndKeepsActiveQueueOnly() {
        val completedDaily = status(TaskRuntimeState.SLEEPING, TaskType.DAILY_DONATE)
        val completedFormation = status(TaskRuntimeState.SLEEPING, TaskType.FORMATION)
        val futureCooldown = status(
            TaskRuntimeState.SLEEPING,
            nextRunAtMillis = 20_000L
        )
        val dueAfterCooldown = status(
            TaskRuntimeState.SLEEPING,
            nextRunAtMillis = 9_000L
        )
        val queued = status(TaskRuntimeState.WAITING)
        val running = status(TaskRuntimeState.RUNNING)
        val stopped = status(TaskRuntimeState.STOPPED)
        val banditPrefetch = status(TaskRuntimeState.RUNNING, TaskType.BANDIT_PREFETCH)
        val minePrefetch = status(TaskRuntimeState.WAITING, TaskType.MINE_PREFETCH)

        assertFalse(LocalTaskPresentation.isTaskStackVisible(completedDaily, completed = true))
        assertFalse(LocalTaskPresentation.isTaskStackVisible(completedFormation, completed = false))
        assertFalse(
            LocalTaskPresentation.isTaskStackVisible(
                futureCooldown,
                completed = false,
                nowMillis = 10_000L
            )
        )
        assertTrue(
            LocalTaskPresentation.isTaskStackVisible(
                dueAfterCooldown,
                completed = false,
                nowMillis = 10_000L
            )
        )
        assertEquals(
            "cooldown",
            LocalTaskPresentation.schedulerState(futureCooldown, nowMillis = 10_000L)
        )
        assertEquals(
            "queued",
            LocalTaskPresentation.schedulerState(dueAfterCooldown, nowMillis = 10_000L)
        )
        assertTrue(LocalTaskPresentation.isTaskStackVisible(queued, completed = false))
        assertTrue(LocalTaskPresentation.isTaskStackVisible(running, completed = false))
        assertFalse(LocalTaskPresentation.isTaskStackVisible(stopped, completed = false))
        assertFalse(LocalTaskPresentation.isTaskStackVisible(banditPrefetch, completed = false))
        assertFalse(LocalTaskPresentation.isTaskStackVisible(minePrefetch, completed = false))
        assertFalse(
            LocalTaskPresentation.isTaskStackVisible(
                queued,
                completed = false,
                schedulerActive = false
            )
        )
        assertEquals("queued", LocalTaskPresentation.taskStackStatus(queued))
        assertEquals("running", LocalTaskPresentation.taskStackStatus(running))
    }

    @Test
    fun currentExecutionGenerationRejectsOldSharedErrorFromEveryQueuedTask() {
        val generation = "service-generation-v20"
        val currentBrush = status(TaskRuntimeState.ERROR, TaskType.SHUA_HUANG).copy(
            message = "刷黄发送结果待核对，禁止自动重做",
            updatedAtMillis = 20_000L,
            executionGeneration = generation,
        )
        val legacyTypes = listOf(
            TaskType.DAILY_SIGN_IN,
            TaskType.DAILY_ARENA_COINS,
            TaskType.DAILY_DONATE,
            TaskType.DAILY_SALARY,
            TaskType.DAILY_GENERAL_VISIT,
            TaskType.DUNGEON,
            TaskType.SIX_MINISTRIES,
        )
        val legacyRows = legacyTypes.map { type ->
            status(TaskRuntimeState.RETRYING, type).copy(
                message = "刷黄恢复账本缺少保存配兵规则",
                updatedAtMillis = 10_000L,
                executionGeneration = "previous-kotlin-generation",
            )
        }

        val projected = LocalTaskPresentation.forExecutionGeneration(
            listOf(currentBrush) + legacyRows,
            generation,
        )

        assertEquals(listOf(TaskType.SHUA_HUANG), projected.map { it.type })
        assertFalse(projected.any { it.message.contains("缺少保存配兵规则") })
        assertTrue(
            LocalTaskPresentation.forExecutionGeneration(
                listOf(currentBrush) + legacyRows,
                null,
            ).containsAll(legacyRows)
        )
    }

    private fun status(
        state: TaskRuntimeState,
        type: TaskType = TaskType.SHUA_HUANG,
        nextRunAtMillis: Long? = null
    ) = TaskRuntimeStatus(7L, type, state, "test", 1_000L, nextRunAtMillis)
}
