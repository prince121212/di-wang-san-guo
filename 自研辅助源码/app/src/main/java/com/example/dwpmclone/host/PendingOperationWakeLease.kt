package com.example.dwpmclone.host

/**
 * A bounded execution lease for operations that are still queued or running.
 *
 * The lease is deliberately independent from the Android WakeLock itself.  It
 * records the first observed pending boundary and never extends that boundary
 * merely because status polling continues.  Once the deadline is reached the
 * host must fall back to AlarmManager plus the durable operation ledger.
 */
data class PendingOperationWakeLeaseSnapshot(
    val pendingOperationIds: Set<String>,
    val deadlineElapsedMillis: Long?,
    val active: Boolean,
    val expired: Boolean,
)

class PendingOperationWakeLease(
    private val maximumLeaseMillis: Long = DEFAULT_MAXIMUM_LEASE_MILLIS,
) {
    private val operationDeadlines = linkedMapOf<String, Long>()

    init {
        require(maximumLeaseMillis > 0L) {
            "maximumLeaseMillis must be positive"
        }
    }

    @Synchronized
    fun observe(
        operationId: String,
        pending: Boolean,
        nowElapsedMillis: Long,
    ): PendingOperationWakeLeaseSnapshot {
        val normalizedId = operationId.trim()
        if (normalizedId.isNotBlank()) {
            if (pending) {
                // The first observation starts this operation's lease.  A
                // later status poll never moves its deadline forward.
                operationDeadlines.putIfAbsent(
                    normalizedId,
                    safeAdd(nowElapsedMillis, maximumLeaseMillis),
                )
            } else {
                operationDeadlines.remove(normalizedId)
            }
        }
        return snapshotLocked(nowElapsedMillis)
    }

    @Synchronized
    fun clear(): PendingOperationWakeLeaseSnapshot {
        operationDeadlines.clear()
        return snapshotLocked(0L)
    }

    @Synchronized
    fun snapshot(nowElapsedMillis: Long): PendingOperationWakeLeaseSnapshot =
        snapshotLocked(nowElapsedMillis)

    private fun snapshotLocked(nowElapsedMillis: Long): PendingOperationWakeLeaseSnapshot {
        val pendingOperationIds = operationDeadlines.keys.toSet()
        val hasPending = pendingOperationIds.isNotEmpty()
        val activeDeadlines = operationDeadlines.values.filter { nowElapsedMillis < it }
        val active = activeDeadlines.isNotEmpty()
        // Expose the next live deadline while a lease is active.  Once all
        // entries expire, retain the oldest deadline for diagnostics.
        val deadline = activeDeadlines.minOrNull() ?: operationDeadlines.values.minOrNull()
        val expired = hasPending && !active
        return PendingOperationWakeLeaseSnapshot(
            pendingOperationIds = pendingOperationIds,
            deadlineElapsedMillis = deadline,
            active = active,
            expired = expired,
        )
    }

    private fun safeAdd(value: Long, delta: Long): Long =
        if (Long.MAX_VALUE - value < delta) Long.MAX_VALUE else value + delta

    companion object {
        const val DEFAULT_MAXIMUM_LEASE_MILLIS = 120_000L
    }
}
