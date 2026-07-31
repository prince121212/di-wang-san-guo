package com.example.dwpmclone.domain.scheduler

/** Pure timing policy: run near actual deadlines and stay quiet while no work is due. */
object SchedulerTickPolicy {
    const val MIN_DELAY_MILLIS = 1_000L
    const val ACTIVE_FALLBACK_MILLIS = 5_000L
    const val CONTINUOUS_WAKE_THRESHOLD_MILLIS = 60_000L
    const val MAX_IDLE_DELAY_MILLIS = 5L * 60L * 1_000L

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

    fun requiresContinuousWakeLock(delayMillis: Long): Boolean =
        delayMillis <= CONTINUOUS_WAKE_THRESHOLD_MILLIS
}
