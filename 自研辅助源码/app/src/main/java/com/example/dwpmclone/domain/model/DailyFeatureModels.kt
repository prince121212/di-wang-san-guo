package com.example.dwpmclone.domain.model

/**
 * Independent daily feature configurations.  They intentionally do not share a
 * completion flag: a rejection in one feature must not suppress the others.
 */
data class DailyDonateConfig(
    val enabled: Boolean,
    /** Existing desktop rule: the amount is derived from the role-level factor. */
    val factorFz: Int = 1
)

data class DailySalaryConfig(
    val enabled: Boolean
)

data class DailyNationalCollectConfig(
    val enabled: Boolean,
    /**
     * Maximum number of national-collection actions in one run.  Zero means
     * use the server-reported daily quota (and stop when no eligible city or
     * quota remains).  This is an action cap, never a candidate-list cap: all
     * state/commandery/county cities must be inspected before choosing.
     */
    val maxAttempts: Int = 0
)

data class DailyCityLordCollectConfig(
    val enabled: Boolean
)

data class DailyGeneralVisitConfig(
    val enabled: Boolean,
    /** Ordered by the user's selection sequence. */
    val orderedGeneralIds: List<Long> = emptyList()
) {
    val selectedIds: List<Long>
        get() = orderedGeneralIds.filter { it > 0L }.distinct().take(MAX_SELECTED)

    companion object {
        const val MAX_SELECTED: Int = 4
    }
}
