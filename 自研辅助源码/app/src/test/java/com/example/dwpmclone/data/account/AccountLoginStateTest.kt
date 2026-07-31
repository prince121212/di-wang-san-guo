package com.example.dwpmclone.data.account

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AccountLoginStateTest {
    @Test
    fun `only invalid sessions require credential relogin`() {
        assertTrue(AccountLoginState.requiresRelogin(AccountLoginState.NEED_RELOGIN))
        assertTrue(AccountLoginState.requiresRelogin(AccountLoginState.OFFLINE))
        assertFalse(AccountLoginState.requiresRelogin(AccountLoginState.NETWORK_PAUSED))
        assertFalse(AccountLoginState.requiresRelogin(AccountLoginState.ONLINE))
        assertFalse(AccountLoginState.requiresRelogin(AccountLoginState.STOPPED))
    }

    @Test
    fun `online session is probed at desktop heartbeat cadence`() {
        assertFalse(
            AccountLoginState.shouldProbe(
                AccountLoginState.ONLINE,
                forceValidation = false,
                lastValidatedAtMillis = 1_000L,
                nowMillis = 20_999L,
                heartbeatIntervalMillis = 20_000L
            )
        )
        assertTrue(
            AccountLoginState.shouldProbe(
                AccountLoginState.ONLINE,
                forceValidation = false,
                lastValidatedAtMillis = 1_000L,
                nowMillis = 21_000L,
                heartbeatIntervalMillis = 20_000L
            )
        )
        assertTrue(
            AccountLoginState.shouldProbe(
                AccountLoginState.CHECKING,
                forceValidation = false,
                lastValidatedAtMillis = null,
                nowMillis = 0L,
                heartbeatIntervalMillis = 20_000L
            )
        )
    }
}
