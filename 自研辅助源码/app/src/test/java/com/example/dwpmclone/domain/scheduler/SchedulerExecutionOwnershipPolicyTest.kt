package com.example.dwpmclone.domain.scheduler

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SchedulerExecutionOwnershipPolicyTest {
    @Test
    fun stoppedBoundAccountCannotUseAnotherAccountsLiveForegroundService() {
        val enabled = setOf(22L)

        assertFalse(
            SchedulerExecutionOwnershipPolicy.allowed(
                hostActive = true,
                boundAccountId = 11L,
                accountEnabled = enabled::contains
            )
        )
        assertTrue(
            SchedulerExecutionOwnershipPolicy.allowed(
                hostActive = true,
                boundAccountId = 22L,
                accountEnabled = enabled::contains
            )
        )
    }

    @Test
    fun globalStopAlwaysRevokesExecutionAndUnboundStartupMayProceedOnlyWhileActive() {
        assertFalse(
            SchedulerExecutionOwnershipPolicy.allowed(false, 22L) { true }
        )
        assertTrue(
            SchedulerExecutionOwnershipPolicy.allowed(true, null) { false }
        )
    }
}
