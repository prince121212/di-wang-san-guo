package com.example.dwpmclone.host

/**
 * Reports an account whose resident lane has gone quiet, whatever the cause.
 *
 * This deliberately knows nothing about the wake gate, the pending ledger or
 * any other mechanism. Every stall so far was produced by a *different*
 * mechanism, and each one was invisible because the check for it lived inside
 * the mechanism that had failed. The only durable invariant is the one stated
 * without reference to any of them: an account with work configured should be
 * asked to do something regularly, and a long silence is a fault no matter
 * which component caused it.
 *
 * One real account was silent for three hours and twenty minutes. The
 * scheduler woke thirty-three times, declined on a single boolean, and wrote
 * nothing, so "stopped" and "idle" were indistinguishable in the logs.
 */
class ResidentLivenessWatchdog(
    private val stallAfterMillis: Long = STALL_AFTER_MILLIS,
    private val repeatEveryMillis: Long = REPEAT_EVERY_MILLIS,
) {
    private val lastTickAtMillis = mutableMapOf<Long, Long>()
    private val lastReportAtMillis = mutableMapOf<Long, Long>()

    init {
        require(stallAfterMillis > 0L) { "stallAfterMillis must be positive" }
        require(repeatEveryMillis > 0L) { "repeatEveryMillis must be positive" }
    }

    /** Records that the lane actually ran, which clears any standing report. */
    @Synchronized
    fun recordTick(accountId: Long, nowMillis: Long) {
        lastTickAtMillis[accountId] = nowMillis
        lastReportAtMillis.remove(accountId)
    }

    /**
     * How long this lane has been silent, when that is worth reporting.
     *
     * Returns null while the silence is still normal, and null again between
     * repeats so a stuck account produces a steady heartbeat rather than one
     * line per wakeup. An account seen for the first time starts its clock now:
     * the watchdog measures from when it began watching, never from the epoch.
     */
    @Synchronized
    fun reportSilence(accountId: Long, nowMillis: Long): Long? {
        val since = lastTickAtMillis.getOrPut(accountId) { nowMillis }
        val silentMillis = nowMillis - since
        if (silentMillis < stallAfterMillis) return null
        val reportedAt = lastReportAtMillis[accountId]
        if (reportedAt != null && nowMillis - reportedAt < repeatEveryMillis) {
            return null
        }
        lastReportAtMillis[accountId] = nowMillis
        return silentMillis
    }

    @Synchronized
    fun retainAccounts(activeAccountIds: Set<Long>) {
        lastTickAtMillis.keys.retainAll(activeAccountIds)
        lastReportAtMillis.keys.retainAll(activeAccountIds)
    }

    companion object {
        /** A lane quiet for this long is a fault, not a quiet period. */
        const val STALL_AFTER_MILLIS = 15L * 60L * 1_000L

        /** Heartbeat interval while the silence continues. */
        const val REPEAT_EVERY_MILLIS = 5L * 60L * 1_000L
    }
}
