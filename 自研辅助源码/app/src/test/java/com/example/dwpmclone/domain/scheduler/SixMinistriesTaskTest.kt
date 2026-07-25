package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.SixMinistriesConfig
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SixMinistriesTaskTest {
    private val context = TaskContext(
        session = GameSession(123L, "mock", null, emptyMap(), 0),
        protocol = MockGameProtocolClient(),
        nowMillis = 1L
    )

    @Test
    fun invalidCropStopsBeforeProtocolExecution() {
        val task = SixMinistriesTask(123L, config(crop = "草药"))

        val decision = SuspendRunner.run { task.prepare(context) }

        assertEquals(TaskDecision.Stop("unverified ministry crop selected: 草药"), decision)
    }

    @Test
    fun capturedCropPreparesAndSleepsAfterSuccessfulStep() {
        val task = SixMinistriesTask(123L, config(crop = "金银花"))

        assertEquals(TaskDecision.Continue, SuspendRunner.run { task.prepare(context) })
        val step = SuspendRunner.run { task.step(context) }
        assertTrue(step is TaskDecision.Sleep)
        assertEquals(60_000L, (step as TaskDecision.Sleep).millis)
    }

    @Test
    fun readOnlyStealScanSleepsTenMinutesWithoutPlanting() {
        val task = SixMinistriesTask(
            123L,
            config(crop = "金银花").copy(cropEnabled = false, stealEnabled = true)
        )

        assertEquals(TaskDecision.Continue, SuspendRunner.run { task.prepare(context) })
        assertEquals(
            TaskDecision.Sleep(10 * 60_000L),
            SuspendRunner.run { task.step(context) }
        )
    }

    private fun config(crop: String) = SixMinistriesConfig(
        cropEnabled = true,
        crop = crop,
        highPriority = true,
        stealEnabled = false,
        courtesyEnabled = false,
        salaryRefresh = false
    )
}
