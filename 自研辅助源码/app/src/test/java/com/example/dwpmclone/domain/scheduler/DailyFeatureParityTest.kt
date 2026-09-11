package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.model.DailyCityLordCollectConfig
import com.example.dwpmclone.domain.model.DailyDonateConfig
import com.example.dwpmclone.domain.model.DailyGeneralVisitConfig
import com.example.dwpmclone.domain.model.DailyNationalCollectConfig
import com.example.dwpmclone.domain.model.DailySalaryConfig
import com.example.dwpmclone.domain.model.DailyStep
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.protocol.AssistantTask
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import org.junit.Assert.assertEquals
import org.junit.Test

class DailyFeatureParityTest {
    @Test
    fun retiredKotlinDailyTasksOnlyCarryConfigurationAndAlwaysFailClosed() {
        val tasks: List<AssistantTask<*>> = listOf(
            DailySingleStepTask(11L, DailyStep.SIGN_IN),
            DailySingleStepTask(11L, DailyStep.ARENA_REWARD),
            DailyDonateTask(11L, DailyDonateConfig(true)),
            DailySalaryTask(11L, DailySalaryConfig(true)),
            DailyNationalCollectTask(11L, DailyNationalCollectConfig(true)),
            DailyCityLordCollectTask(11L, DailyCityLordCollectConfig(true)),
            DailyGeneralVisitTask(11L, DailyGeneralVisitConfig(true, listOf(88L)))
        )
        val context = TaskContext(
            session = GameSession(11L, "real-token", null, emptyMap(), 1),
            protocol = MockGameProtocolClient(),
            nowMillis = 1_000L
        )
        val expected = TaskDecision.Stop(
            "日常已由共享 Python 常驻核心执行，Kotlin 任务不得发包"
        )

        tasks.forEach { task ->
            assertEquals(expected, SuspendRunner.run { task.prepare(context) })
            assertEquals(expected, SuspendRunner.run { task.step(context) })
        }
    }

    @Test
    fun markerTasksKeepSavedConfigurationForHostPresentation() {
        val visit = DailyGeneralVisitConfig(true, listOf(88L, 99L))
        val task = DailyGeneralVisitTask(11L, visit)

        assertEquals(visit, task.config)
        assertEquals(listOf(88L, 99L), task.config.selectedIds)
    }
}
