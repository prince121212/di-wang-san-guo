package com.example.dwpmclone.host

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PendingOperationWakeLeaseTest {
    @Test
    fun repeatedPendingObservationNeverMovesTheHardDeadline() {
        val lease = PendingOperationWakeLease(maximumLeaseMillis = 120_000L)

        val first = lease.observe("op-1", pending = true, nowElapsedMillis = 1_000L)
        val repeated = lease.observe("op-1", pending = true, nowElapsedMillis = 60_000L)

        assertEquals(121_000L, first.deadlineElapsedMillis)
        assertEquals(121_000L, repeated.deadlineElapsedMillis)
        assertTrue(repeated.active)
        assertFalse(repeated.expired)
    }

    @Test
    fun pendingOperationExpiresAtTheHardLimit() {
        val lease = PendingOperationWakeLease(maximumLeaseMillis = 120_000L)
        lease.observe("op-1", pending = true, nowElapsedMillis = 1_000L)

        val expired = lease.snapshot(nowElapsedMillis = 121_000L)

        assertFalse(expired.active)
        assertTrue(expired.expired)
        assertEquals(setOf("op-1"), expired.pendingOperationIds)
    }

    @Test
    fun terminalObservationReleasesTheLeaseImmediately() {
        val lease = PendingOperationWakeLease(maximumLeaseMillis = 120_000L)
        lease.observe("op-1", pending = true, nowElapsedMillis = 1_000L)

        val terminal = lease.observe("op-1", pending = false, nowElapsedMillis = 2_000L)

        assertFalse(terminal.active)
        assertFalse(terminal.expired)
        assertTrue(terminal.pendingOperationIds.isEmpty())
        assertNull(terminal.deadlineElapsedMillis)
    }

    @Test
    fun accountsCanOverlapWithoutExtendingEachOthersDeadlines() {
        val lease = PendingOperationWakeLease(maximumLeaseMillis = 100L)
        lease.observe("op-old", pending = true, nowElapsedMillis = 1_000L)
        lease.observe("op-new", pending = true, nowElapsedMillis = 1_050L)

        val oneStillActive = lease.snapshot(nowElapsedMillis = 1_100L)

        assertTrue(oneStillActive.active)
        assertFalse(oneStillActive.expired)
        assertEquals(1_150L, oneStillActive.deadlineElapsedMillis)

        val allExpired = lease.snapshot(nowElapsedMillis = 1_150L)
        assertFalse(allExpired.active)
        assertTrue(allExpired.expired)
    }

    @Test
    fun clearRemovesEveryPendingOperation() {
        val lease = PendingOperationWakeLease(maximumLeaseMillis = 100L)
        lease.observe("op-1", pending = true, nowElapsedMillis = 1_000L)
        lease.observe("op-2", pending = true, nowElapsedMillis = 1_010L)

        val cleared = lease.clear()

        assertTrue(cleared.pendingOperationIds.isEmpty())
        assertFalse(cleared.active)
        assertFalse(cleared.expired)
        assertNull(cleared.deadlineElapsedMillis)
    }
}
