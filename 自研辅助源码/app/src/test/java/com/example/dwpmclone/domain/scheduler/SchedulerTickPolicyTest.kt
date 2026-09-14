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
        assertEquals(false, SchedulerTickPolicy.shouldArmAlarmWatchdog(0L))
        assertEquals(true, SchedulerTickPolicy.shouldArmAlarmWatchdog(1_000L))
        assertEquals(true, SchedulerTickPolicy.shouldArmAlarmWatchdog(300_000L))
    }

    /**
     * Regression for the 02:00–09:42 starvation on the test device: every
     * tick declared an immediate follow-up, the host released the CPU anyway,
     * and deep Doze deferred the alarm watchdog by up to 195s. Dungeon/brush
     * need a tick every few seconds; any gap that ends at a deadline the
     * scheduler named must keep the CPU awake.
     */
    @Test
    fun everyNamedDeadlineKeepsCpuAwakeAndOnlyTheIdleCeilingReleasesIt() {
        assertEquals(true, SchedulerTickPolicy.shouldHoldWakeLockAcross(0L))
        assertEquals(true, SchedulerTickPolicy.shouldHoldWakeLockAcross(SchedulerTickPolicy.MIN_DELAY_MILLIS))
        assertEquals(true, SchedulerTickPolicy.shouldHoldWakeLockAcross(SchedulerTickPolicy.ACTIVE_FALLBACK_MILLIS))
        assertEquals(true, SchedulerTickPolicy.shouldHoldWakeLockAcross(SchedulerTickPolicy.MAX_IDLE_DELAY_MILLIS - 1L))
        assertEquals(false, SchedulerTickPolicy.shouldHoldWakeLockAcross(SchedulerTickPolicy.MAX_IDLE_DELAY_MILLIS))
        assertEquals(false, SchedulerTickPolicy.shouldHoldWakeLockAcross(-1L))
    }

    /**
     * The hold rule is derived from the horizon, not from a number of seconds.
     * Today the 60s session probe keeps every online gap short; the night that
     * cadence is raised, a fixed 60s cutoff would start releasing the CPU on
     * every quiet tick and the starvation would return with no test failing.
     * A deadline the scheduler itself computed is therefore always held, at
     * any distance inside the horizon.
     */
    @Test
    fun aDeadlineComputedByTheSchedulerIsHeldAtAnyDistanceInsideTheHorizon() {
        val now = 1_000_000L
        for (secondsAhead in listOf(30L, 61L, 120L, 240L, 299L)) {
            val delay = SchedulerTickPolicy.nextDelayMillis(
                nowMillis = now,
                earliestDeadlineMillis = now + secondsAhead * 1_000L,
                ranWork = false,
            )
            assertEquals("${secondsAhead}s ahead", true, SchedulerTickPolicy.shouldHoldWakeLockAcross(delay))
        }
        val idle = SchedulerTickPolicy.nextDelayMillis(now, earliestDeadlineMillis = null, ranWork = false)
        assertEquals(false, SchedulerTickPolicy.shouldHoldWakeLockAcross(idle))
        val farAway = SchedulerTickPolicy.nextDelayMillis(now, now + 60L * 60L * 1_000L, ranWork = false)
        assertEquals(false, SchedulerTickPolicy.shouldHoldWakeLockAcross(farAway))
    }

    @Test
    fun wakeHoldTimeoutOutlivesTheGapAndTheTickAfterItButNeverExceedsTheLeakGuard() {
        assertEquals(
            SchedulerTickPolicy.WAKE_HOLD_MARGIN_MILLIS,
            SchedulerTickPolicy.wakeHoldTimeoutMillis(0L),
        )
        assertEquals(
            10_000L + SchedulerTickPolicy.WAKE_HOLD_MARGIN_MILLIS,
            SchedulerTickPolicy.wakeHoldTimeoutMillis(10_000L),
        )
        assertEquals(
            SchedulerTickPolicy.WAKE_HOLD_MARGIN_MILLIS,
            SchedulerTickPolicy.wakeHoldTimeoutMillis(-5_000L),
        )
        // The longest legitimate hold fits under the cap exactly, so the lock
        // cannot expire before the Handler fires at the far edge of the horizon.
        assertEquals(
            SchedulerTickPolicy.MAX_WAKE_HOLD_TIMEOUT_MILLIS,
            SchedulerTickPolicy.wakeHoldTimeoutMillis(SchedulerTickPolicy.MAX_IDLE_DELAY_MILLIS - 1L) + 1L,
        )
        assertEquals(
            SchedulerTickPolicy.MAX_WAKE_HOLD_TIMEOUT_MILLIS,
            SchedulerTickPolicy.wakeHoldTimeoutMillis(Long.MAX_VALUE / 2),
        )
    }
}
