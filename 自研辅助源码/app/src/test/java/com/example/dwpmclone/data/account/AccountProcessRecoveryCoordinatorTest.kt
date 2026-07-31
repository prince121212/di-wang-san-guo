package com.example.dwpmclone.data.account

import com.example.dwpmclone.data.local.SessionReconnectState
import com.example.dwpmclone.domain.model.Channel
import com.example.dwpmclone.domain.model.GameAccount
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.GameVersion
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AccountProcessRecoveryCoordinatorTest {
    @Test
    fun `service process recovery reduces persisted state without a network capability`() {
        val nowMillis = 10_000L
        val retryAtMillis = 60_000L
        val account = account(
            enabled = true,
            loginState = AccountLoginState.ONLINE,
            lastValidatedAtMillis = 8_000L
        )
        var capturedInput: AccountTransitionInput? = null
        var capturedEvent = ""
        var capturedDetails: AccountTransitionDetails? = null
        var capturedNow = 0L
        val source = AccountStateTransitionSource { state, event, details, time ->
            capturedInput = state
            capturedEvent = event
            capturedDetails = details
            capturedNow = time
            AccountStateTransition(
                desiredStarted = state.desiredStarted,
                loginState = AccountLoginState.CHECKING,
                sessionCredentialPresent = state.sessionCredentialPresent,
                liveSessionUsable = false,
                failureKind = state.failureKind,
                failureCount = state.failureCount,
                nextRetryAtMillis = state.nextRetryAtMillis,
                lastError = state.lastError,
                lastValidatedAtMillis = state.lastValidatedAtMillis,
                nextOperation = "wait",
                sessionSecretAction = "keep",
                event = event,
                updatedAtMillis = time
            )
        }
        val applied = mutableListOf<Pair<GameAccount, AccountStateTransition>>()
        val store = object : AccountProcessRecoveryStore {
            override fun snapshots(): List<AccountProcessRecoverySnapshot> = listOf(
                AccountProcessRecoverySnapshot(
                    account = account,
                    reconnect = SessionReconnectState(
                        failures = 3,
                        nextAttemptAtMillis = retryAtMillis,
                        reason = "network unavailable",
                        failureKind = "network"
                    )
                )
            )

            override fun apply(account: GameAccount, transition: AccountStateTransition) {
                applied += account to transition
            }
        }

        val count = AccountProcessRecoveryCoordinator(source).prepare(store, nowMillis)

        assertEquals(1, count)
        assertEquals(AccountStateEvents.PROCESS_RECOVERED, capturedEvent)
        assertEquals(AccountTransitionDetails(), capturedDetails)
        assertEquals(nowMillis, capturedNow)
        assertTrue(capturedInput!!.desiredStarted)
        assertEquals(AccountLoginState.ONLINE, capturedInput!!.loginState)
        assertTrue(capturedInput!!.sessionCredentialPresent)
        assertEquals(3, capturedInput!!.failureCount)
        assertEquals("network", capturedInput!!.failureKind)
        assertEquals(retryAtMillis, capturedInput!!.nextRetryAtMillis)
        assertEquals(8_000L, capturedInput!!.lastValidatedAtMillis)
        assertEquals(1, applied.size)
        assertEquals(AccountLoginState.CHECKING, applied.single().second.loginState)
        assertFalse(applied.single().second.liveSessionUsable)
        assertEquals(retryAtMillis, applied.single().second.nextRetryAtMillis)
    }

    @Test
    fun `process recovery preserves stopped account intent without probing`() {
        val account = account(
            enabled = false,
            loginState = AccountLoginState.STOPPED,
            lastValidatedAtMillis = null
        )
        val source = AccountStateTransitionSource { state, event, _, time ->
            AccountStateTransition(
                desiredStarted = state.desiredStarted,
                loginState = AccountLoginState.STOPPED,
                sessionCredentialPresent = state.sessionCredentialPresent,
                liveSessionUsable = false,
                failureKind = state.failureKind,
                failureCount = state.failureCount,
                nextRetryAtMillis = state.nextRetryAtMillis,
                lastError = state.lastError,
                lastValidatedAtMillis = state.lastValidatedAtMillis,
                nextOperation = "none",
                sessionSecretAction = "keep",
                event = event,
                updatedAtMillis = time
            )
        }
        var applied: AccountStateTransition? = null
        val store = object : AccountProcessRecoveryStore {
            override fun snapshots(): List<AccountProcessRecoverySnapshot> =
                listOf(AccountProcessRecoverySnapshot(account, SessionReconnectState()))

            override fun apply(account: GameAccount, transition: AccountStateTransition) {
                applied = transition
            }
        }

        AccountProcessRecoveryCoordinator(source).prepare(store, nowMillis = 20_000L)

        assertFalse(applied!!.desiredStarted)
        assertEquals(AccountLoginState.STOPPED, applied!!.loginState)
        assertFalse(applied!!.liveSessionUsable)
        assertEquals("none", applied!!.nextOperation)
    }

    private fun account(
        enabled: Boolean,
        loginState: String,
        lastValidatedAtMillis: Long?
    ): GameAccount = GameAccount(
        id = 1001L,
        displayName = "offline fixture",
        username = "fixture",
        serverName = "fixture server",
        gameVersion = GameVersion.OTHER,
        channel = Channel.UNKNOWN,
        session = GameSession(
            accountId = 1001L,
            tokenCiphertext = "present",
            expiresAtMillis = null,
            channelExtra = buildMap {
                lastValidatedAtMillis?.let { put("lastValidatedAt", it.toString()) }
            },
            sourceMode = 1
        ),
        enabled = enabled,
        loginState = loginState
    )
}
