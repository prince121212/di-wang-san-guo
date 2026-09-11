package com.example.dwpmclone.ui.web

internal data class LocalSettingsExecutionDecision(
    val executionActive: Boolean,
    val taskStarted: Boolean,
    val waitingForAccountStart: Boolean,
    val shouldRefreshExecutionOwner: Boolean,
)

/**
 * Keeps a local settings commit separate from foreground execution ownership.
 *
 * A persisted "account enabled" bit is only desired state. It must never revive
 * a stopped Service merely because the user saves a local setting.
 */
internal object LocalSettingsExecutionPolicy {
    fun decide(
        accountEnabled: Boolean,
        accountRunnable: Boolean,
        executionOwnerActive: Boolean,
        executionRequested: Boolean,
    ): LocalSettingsExecutionDecision {
        val executionActive = accountEnabled && accountRunnable && executionOwnerActive
        return LocalSettingsExecutionDecision(
            executionActive = executionActive,
            taskStarted = executionRequested && executionActive,
            waitingForAccountStart = executionRequested && !executionActive,
            shouldRefreshExecutionOwner = executionOwnerActive,
        )
    }
}
