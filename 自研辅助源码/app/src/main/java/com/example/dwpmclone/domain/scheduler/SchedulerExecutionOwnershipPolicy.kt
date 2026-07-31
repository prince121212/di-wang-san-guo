package com.example.dwpmclone.domain.scheduler

/** Pure policy for the foreground host's global and per-account execution ownership. */
object SchedulerExecutionOwnershipPolicy {
    fun allowed(
        hostActive: Boolean,
        boundAccountId: Long?,
        accountEnabled: (Long) -> Boolean
    ): Boolean = hostActive && (boundAccountId == null || accountEnabled(boundAccountId))
}
