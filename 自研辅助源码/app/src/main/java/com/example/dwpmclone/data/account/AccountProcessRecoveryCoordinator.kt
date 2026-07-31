package com.example.dwpmclone.data.account

import com.example.dwpmclone.data.local.SessionReconnectState
import com.example.dwpmclone.domain.model.GameAccount

data class AccountProcessRecoverySnapshot(
    val account: GameAccount,
    val reconnect: SessionReconnectState
)

/**
 * Minimal persistence boundary used during process recreation.
 *
 * Deliberately exposes no login, protocol, probe or scheduler capability: process recovery may
 * reduce already-persisted state, but it must not send a game request from Service.onCreate().
 */
interface AccountProcessRecoveryStore {
    fun snapshots(): List<AccountProcessRecoverySnapshot>
    fun apply(account: GameAccount, transition: AccountStateTransition)
}

class AccountProcessRecoveryCoordinator(
    private val stateTransitions: AccountStateTransitionSource
) {
    fun prepare(store: AccountProcessRecoveryStore, nowMillis: Long): Int {
        val snapshots = store.snapshots()
        snapshots.forEach { snapshot ->
            val account = snapshot.account
            val retry = snapshot.reconnect
            val transition = stateTransitions.accountStateTransition(
                state = AccountTransitionInput(
                    desiredStarted = account.enabled,
                    loginState = account.loginState,
                    sessionCredentialPresent = account.session?.sourceMode == 1,
                    failureKind = retry.failureKind,
                    failureCount = retry.failures,
                    nextRetryAtMillis = retry.nextAttemptAtMillis.takeIf { it > 0L },
                    lastError = retry.reason,
                    lastValidatedAtMillis = account.session?.channelExtra
                        ?.get("lastValidatedAt")
                        ?.toLongOrNull()
                ),
                event = AccountStateEvents.PROCESS_RECOVERED,
                details = AccountTransitionDetails(),
                nowMillis = nowMillis
            )
            store.apply(account, transition)
        }
        return snapshots.size
    }
}
