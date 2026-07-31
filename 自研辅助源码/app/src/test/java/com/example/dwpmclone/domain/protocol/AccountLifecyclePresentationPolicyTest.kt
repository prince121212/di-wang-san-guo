package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AccountLifecyclePresentationPolicyTest {
    @Test
    fun enabledAccountIsOnlineOnlyWhileExecutionOwnerIsActive() {
        val online = AccountLifecyclePresentationPolicy.resolve(
            accountEnabled = true,
            executionOwnerActive = true,
            loginState = "REAL_PROTOCOL_ONLINE"
        )
        val orphaned = AccountLifecyclePresentationPolicy.resolve(
            accountEnabled = true,
            executionOwnerActive = false,
            loginState = "REAL_PROTOCOL_ONLINE"
        )

        assertEquals("online", online.status)
        assertEquals("开启", online.statusText)
        assertTrue(online.started)
        assertEquals("stopped", orphaned.status)
        assertEquals("未开启", orphaned.statusText)
        assertFalse(orphaned.started)
    }

    @Test
    fun liveOwnerPreservesCheckingAndOfflineSemantics() {
        val checking = AccountLifecyclePresentationPolicy.resolve(
            accountEnabled = true,
            executionOwnerActive = true,
            loginState = "REAL_PROTOCOL_CHECKING"
        )
        val relogin = AccountLifecyclePresentationPolicy.resolve(
            accountEnabled = true,
            executionOwnerActive = true,
            loginState = "REAL_PROTOCOL_NEED_RELOGIN"
        )

        assertEquals("checking", checking.status)
        assertTrue(checking.started)
        assertEquals("offline", relogin.status)
        assertTrue(relogin.started)
    }

    @Test
    fun explicitStopAlwaysPresentsStopped() {
        val stopped = AccountLifecyclePresentationPolicy.resolve(
            accountEnabled = false,
            executionOwnerActive = true,
            loginState = "REAL_PROTOCOL_STOPPED"
        )

        assertEquals("stopped", stopped.status)
        assertEquals("未开启", stopped.statusText)
        assertFalse(stopped.started)
    }

    @Test
    fun persistedRealSessionIsNotExposedOrUsableWhileAccountIsStoppedOrOffline() {
        assertFalse(AccountLifecyclePresentationPolicy.mayUseLiveSession(
            accountEnabled = false,
            executionOwnerActive = true,
            loginState = "REAL_PROTOCOL_STOPPED",
            sourceMode = 1
        ))
        assertFalse(AccountLifecyclePresentationPolicy.mayUseLiveSession(
            accountEnabled = true,
            executionOwnerActive = true,
            loginState = "REAL_PROTOCOL_NEED_RELOGIN",
            sourceMode = 1
        ))
        assertTrue(AccountLifecyclePresentationPolicy.mayUseLiveSession(
            accountEnabled = true,
            executionOwnerActive = true,
            loginState = "REAL_PROTOCOL_ONLINE",
            sourceMode = 1
        ))
    }
}
