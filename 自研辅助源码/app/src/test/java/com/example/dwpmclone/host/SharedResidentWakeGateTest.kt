package com.example.dwpmclone.host

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SharedResidentWakeGateTest {
    private class MemoryWakeStore : ResidentWakeStateStore {
        val values = linkedMapOf<Long, ResidentWakeState>()
        override fun snapshot(): Map<Long, ResidentWakeState> = values.toMap()
        override fun put(accountId: Long, state: ResidentWakeState) { values[accountId] = state }
        override fun remove(accountId: Long) { values.remove(accountId) }
        override fun retainAccounts(activeAccountIds: Set<Long>) { values.keys.retainAll(activeAccountIds) }
        override fun clear() { values.clear() }
    }

    private fun result(
        accountId: Long,
        nextWakeAtMillis: Long?,
        requiresAttention: Boolean = false,
    ) = SharedResidentTickResult(
        accountId = accountId,
        operationId = "op-$accountId",
        feature = "brushYellow",
        dailyKey = null,
        state = if (requiresAttention) "blocked" else "waiting",
        message = "fixture",
        nextWakeAtMillis = nextWakeAtMillis,
        requiresAttention = requiresAttention,
        requestSent = false,
    )

    @Test
    fun deadlinePreventsOtherSchedulerTicksFromResubmitting() {
        val gate = SharedResidentWakeGate()

        assertTrue(gate.shouldRun(202, 1_000L))
        gate.record(result(202, 11_000L), completedAtMillis = 1_000L)

        assertFalse(gate.shouldRun(202, 2_500L))
        assertFalse(gate.shouldRun(202, 10_999L))
        assertTrue(gate.shouldRun(202, 11_000L))

        gate.record(result(202, 21_000L), completedAtMillis = 11_000L)
        assertFalse(gate.shouldRun(202, 11_000L))
        assertEquals(21_000L, gate.earliestDeadlineMillis(setOf(202L)))
    }

    @Test
    fun pastDeadlineIsClampedToMinimumInterval() {
        val gate = SharedResidentWakeGate(minimumIntervalMillis = 1_000L)

        gate.record(result(202, 900L), completedAtMillis = 1_000L)

        assertFalse(gate.shouldRun(202, 1_999L))
        assertTrue(gate.shouldRun(202, 2_000L))
    }

    @Test
    fun attentionBacksOffAndThenRetriesByItself() {
        // Replay safety belongs to the core's durable send-boundary ledger, so
        // holding every tick forever protected nothing and cost a real account
        // over three hours of complete inactivity after one item rejection.
        val gate = SharedResidentWakeGate(attentionRetryMillis = 5_000L)

        gate.record(
            result(202, nextWakeAtMillis = null, requiresAttention = true),
            completedAtMillis = 1_000L,
        )

        assertTrue(gate.awaitingAttention(202))
        assertFalse(gate.shouldRun(202, 5_999L))
        assertTrue(gate.shouldRun(202, 6_000L))
        assertEquals(6_000L, gate.earliestDeadlineMillis(setOf(202L)))
    }

    @Test
    fun anIndefiniteHoldWrittenByAnOlderBuildBecomesDueNow() {
        // The stuck account upgrades into a gate that can release it.
        val store = MemoryWakeStore()
        store.put(
            202,
            ResidentWakeState(nextWakeAtMillis = null, pausedForAttention = true),
        )

        val gate = SharedResidentWakeGate(store = store)

        assertTrue(gate.shouldRun(202, 1_000L))
        assertTrue(gate.awaitingAttention(202))
    }

    @Test
    fun resultStartedBeforeRefreshCannotRestoreOldPause() {
        val gate = SharedResidentWakeGate()
        val permit = gate.permit(202, 1_000L)!!

        gate.clear()
        gate.record(
            result(202, nextWakeAtMillis = null, requiresAttention = true),
            completedAtMillis = 2_000L,
            permitGeneration = permit,
        )

        assertTrue(gate.shouldRun(202, 2_000L))
    }

    @Test
    fun accountDeadlinesAreIndependentAndInactiveAccountsAreRemoved() {
        val gate = SharedResidentWakeGate()
        gate.record(result(202, 11_000L), completedAtMillis = 1_000L)
        gate.record(result(303, 6_000L), completedAtMillis = 1_000L)

        assertEquals(
            6_000L,
            gate.earliestDeadlineMillis(setOf(202L, 303L)),
        )
        assertFalse(gate.shouldRun(202, 6_000L))
        assertTrue(gate.shouldRun(303, 6_000L))

        gate.retainAccounts(setOf(202L))
        assertTrue(gate.shouldRun(303, 6_000L))
        assertEquals(11_000L, gate.earliestDeadlineMillis(setOf(202L)))
    }

    @Test
    fun deadlineAndAttentionBackoffSurviveGateRecreation() {
        val store = MemoryWakeStore()
        val first = SharedResidentWakeGate(store = store, attentionRetryMillis = 5_000L)
        first.record(result(202, 11_000L), completedAtMillis = 1_000L)
        first.record(
            result(303, nextWakeAtMillis = null, requiresAttention = true),
            completedAtMillis = 1_000L,
        )

        val restored = SharedResidentWakeGate(store = store, attentionRetryMillis = 5_000L)

        assertFalse(restored.shouldRun(202, 10_999L))
        assertTrue(restored.shouldRun(202, 11_000L))
        assertFalse(restored.shouldRun(303, 5_999L))
        assertTrue(restored.shouldRun(303, 6_000L))
        assertTrue(restored.awaitingAttention(303))
        assertEquals(6_000L, restored.earliestDeadlineMillis(setOf(202L, 303L)))
    }
}
