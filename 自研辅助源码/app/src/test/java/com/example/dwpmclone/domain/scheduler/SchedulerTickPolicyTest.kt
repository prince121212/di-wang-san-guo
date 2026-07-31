package com.example.dwpmclone.domain.scheduler

import org.junit.Assert.assertEquals
import org.junit.Test

class SchedulerTickPolicyTest {
    @Test
    fun sleepsUntilKnownDeadlineWithinBounds() {
        assertEquals(30_000L, SchedulerTickPolicy.nextDelayMillis(10_000L, 40_000L, ranWork = true))
        assertEquals(1_000L, SchedulerTickPolicy.nextDelayMillis(10_000L, 9_000L, ranWork = false))
        assertEquals(300_000L, SchedulerTickPolicy.nextDelayMillis(10_000L, 900_000L, ranWork = false))
    }

    @Test
    fun activeUnknownWorkRetriesQuicklyButIdleServiceStaysQuiet() {
        assertEquals(5_000L, SchedulerTickPolicy.nextDelayMillis(10_000L, null, ranWork = true))
        assertEquals(300_000L, SchedulerTickPolicy.nextDelayMillis(10_000L, null, ranWork = false))
        assertEquals(true, SchedulerTickPolicy.requiresContinuousWakeLock(60_000L))
        assertEquals(false, SchedulerTickPolicy.requiresContinuousWakeLock(60_001L))
    }
}
