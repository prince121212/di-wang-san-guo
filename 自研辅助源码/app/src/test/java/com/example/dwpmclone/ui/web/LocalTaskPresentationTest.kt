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
            listOf("mine", "lossless", "brushYellow", "raid", "dungeon", "ministry"),
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
    fun dailyCompletionTurnsItsPersistedSleepIntoDailyDone() {
        val sleeping = status(TaskRuntimeState.SLEEPING, TaskType.DAILY_SIGN_IN)
        assertEquals("daily_done", LocalTaskPresentation.schedulerState(sleeping, completed = true))
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

    private fun status(
        state: TaskRuntimeState,
        type: TaskType = TaskType.SHUA_HUANG,
        nextRunAtMillis: Long? = null
    ) = TaskRuntimeStatus(7L, type, state, "test", 1_000L, nextRunAtMillis)
}
