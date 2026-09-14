package com.example.dwpmclone.domain.scheduler

/** Pure timing policy: run near actual deadlines and stay quiet while no work is due. */
object SchedulerTickPolicy {
    const val MIN_DELAY_MILLIS = 1_000L
    const val ACTIVE_FALLBACK_MILLIS = 5_000L
    const val MAX_IDLE_DELAY_MILLIS = 5L * 60L * 1_000L
    const val OVERDUE_LOG_THRESHOLD_MILLIS = 5_000L

    /** Slack after a deadline so the CPU lease outlives the tick it protects. */
    const val WAKE_HOLD_MARGIN_MILLIS = 90_000L

    /**
     * Longest CPU lease this policy will ever ask for: the whole planning
     * horizon plus the margin, so a hold across the longest named deadline is
     * never truncated by the lock's own timeout.
     */
    const val MAX_WAKE_HOLD_TIMEOUT_MILLIS = MAX_IDLE_DELAY_MILLIS + WAKE_HOLD_MARGIN_MILLIS

    fun nextDelayMillis(
        nowMillis: Long,
        earliestDeadlineMillis: Long?,
        ranWork: Boolean
    ): Long {
        if (earliestDeadlineMillis != null) {
            return (earliestDeadlineMillis - nowMillis)
                .coerceIn(MIN_DELAY_MILLIS, MAX_IDLE_DELAY_MILLIS)
        }
        return if (ranWork) ACTIVE_FALLBACK_MILLIS else MAX_IDLE_DELAY_MILLIS
    }

    /** Every scheduled deadline, including an immediate one, gets a system watchdog. */
    fun shouldArmAlarmWatchdog(delayMillis: Long): Boolean = delayMillis > 0L

    /**
     * Keep the CPU awake across every gap that ends at a deadline the
     * scheduler actually named.
     *
     * Timing correctness comes from the Handler, and the Handler only fires
     * while the CPU is awake.  The alarm behind it is a crash-recovery
     * watchdog, not a timer: in deep Doze the OS deferred it by 5s–195s on the
     * test device, so on the night of 2026-09-12 ticks arrived every 40s–5min
     * while the core asked for one every second.  A 13-minute mine cycle
     * tolerates that; a 2.5-minute dungeon cycle needing ~10 ticks and a brush
     * scan of 5 cells per tick do not.
     *
     * The rule is tied to the scheduler's own horizon rather than to a fixed
     * number of seconds: [nextDelayMillis] returns [MAX_IDLE_DELAY_MILLIS] only
     * when nothing is due within the horizon, so every shorter value is a
     * deadline someone is waiting on.  A fixed cutoff would silently depend on
     * whatever cadence happens to keep the delay below it today (the 60s
     * session probe) and would break the night that cadence changes.
     */
    fun shouldHoldWakeLockAcross(nextDelayMillis: Long): Boolean =
        nextDelayMillis in 0L until MAX_IDLE_DELAY_MILLIS

    /** Wake-lock timeout that covers the gap plus the tick that follows it. */
    fun wakeHoldTimeoutMillis(nextDelayMillis: Long): Long =
        (nextDelayMillis.coerceAtLeast(0L) + WAKE_HOLD_MARGIN_MILLIS)
            .coerceAtMost(MAX_WAKE_HOLD_TIMEOUT_MILLIS)
}
