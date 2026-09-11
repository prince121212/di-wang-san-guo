package com.example.dwpmclone.host

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class ResidentLivenessWatchdogTest {
    private fun watchdog() = ResidentLivenessWatchdog(
        stallAfterMillis = 10_000L,
        repeatEveryMillis = 4_000L,
    )

    @Test
    fun aRunningLaneIsNeverReported() {
        val watchdog = watchdog()

        watchdog.recordTick(202, 1_000L)
        assertNull(watchdog.reportSilence(202, 5_000L))
        watchdog.recordTick(202, 6_000L)
        assertNull(watchdog.reportSilence(202, 15_000L))
    }

    @Test
    fun silenceIsReportedWithItsDurationOnceTheThresholdPasses() {
        // The invariant is stated without reference to any mechanism, so a
        // stall caused by a component nobody suspected still surfaces.
        val watchdog = watchdog()
        watchdog.recordTick(202, 1_000L)

        assertNull(watchdog.reportSilence(202, 10_999L))
        assertEquals(11_000L, watchdog.reportSilence(202, 12_000L))
    }

    @Test
    fun aContinuingStallHeartbeatsInsteadOfLoggingEveryWakeup() {
        val watchdog = watchdog()
        watchdog.recordTick(202, 0L)

        assertNotNull(watchdog.reportSilence(202, 10_000L))
        assertNull(watchdog.reportSilence(202, 11_000L))
        assertNull(watchdog.reportSilence(202, 13_999L))
        assertEquals(14_000L, watchdog.reportSilence(202, 14_000L))
    }

    @Test
    fun aRecoveredLaneReportsAgainFromScratch() {
        val watchdog = watchdog()
        watchdog.recordTick(202, 0L)
        assertNotNull(watchdog.reportSilence(202, 10_000L))

        watchdog.recordTick(202, 11_000L)

        assertNull(watchdog.reportSilence(202, 20_000L))
        assertEquals(10_000L, watchdog.reportSilence(202, 21_000L))
    }

    @Test
    fun anAccountSeenForTheFirstTimeStartsItsClockNow() {
        // Measuring from the epoch would report every fresh account as stalled.
        val watchdog = watchdog()

        assertNull(watchdog.reportSilence(202, 1_700_000_000_000L))
        assertNotNull(watchdog.reportSilence(202, 1_700_000_010_000L))
    }

    @Test
    fun accountsAreIndependentAndRemovedAccountsAreForgotten() {
        val watchdog = watchdog()
        watchdog.recordTick(202, 0L)
        watchdog.recordTick(303, 0L)

        assertNotNull(watchdog.reportSilence(202, 10_000L))
        assertNotNull(watchdog.reportSilence(303, 10_000L))

        watchdog.retainAccounts(setOf(202L))
        // 303 is gone, so it starts a fresh clock instead of reporting again.
        assertNull(watchdog.reportSilence(303, 11_000L))
    }
}
