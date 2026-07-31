package com.example.dwpmclone.data.account

data class AccountTransitionInput(
    val desiredStarted: Boolean,
    val loginState: String,
    val sessionCredentialPresent: Boolean,
    val failureKind: String = "",
    val failureCount: Int = 0,
    val nextRetryAtMillis: Long? = null,
    val lastError: String = "",
    val lastValidatedAtMillis: Long? = null
)

data class AccountTransitionDetails(
    val message: String = "",
    val sessionInvalid: Boolean = false,
    val validatedAtMillis: Long? = null
)

data class AccountStateTransition(
    val desiredStarted: Boolean,
    val loginState: String,
    val sessionCredentialPresent: Boolean,
    val liveSessionUsable: Boolean,
    val failureKind: String,
    val failureCount: Int,
    val nextRetryAtMillis: Long?,
    val lastError: String,
    val lastValidatedAtMillis: Long?,
    val nextOperation: String,
    val sessionSecretAction: String,
    val event: String,
    val updatedAtMillis: Long
)

fun interface AccountStateTransitionSource {
    fun accountStateTransition(
        state: AccountTransitionInput,
        event: String,
        details: AccountTransitionDetails,
        nowMillis: Long
    ): AccountStateTransition
}

object AccountStateEvents {
    const val USER_START = "USER_START"
    const val USER_STOP = "USER_STOP"
    const val LOGIN_SUCCEEDED = "LOGIN_SUCCEEDED"
    const val LOGIN_FAILED = "LOGIN_FAILED"
    const val PROBE_VALID = "PROBE_VALID"
    const val SESSION_EXPIRED = "SESSION_EXPIRED"
    const val PROBE_UNAVAILABLE = "PROBE_UNAVAILABLE"
    const val NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"
    const val PROCESS_RECOVERED = "PROCESS_RECOVERED"
}
