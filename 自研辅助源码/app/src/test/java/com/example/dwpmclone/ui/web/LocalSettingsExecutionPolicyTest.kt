package com.example.dwpmclone.ui.web

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalSettingsExecutionPolicyTest {
    @Test
    fun persistedEnabledBitCannotReviveStoppedExecutionOwner() {
        val decision = LocalSettingsExecutionPolicy.decide(
            accountEnabled = true,
            accountRunnable = true,
            executionOwnerActive = false,
            executionRequested = true,
        )

        assertFalse(decision.executionActive)
        assertFalse(decision.taskStarted)
        assertTrue(decision.waitingForAccountStart)
        assertFalse(decision.shouldRefreshExecutionOwner)
    }

    @Test
    fun activeOwnerReceivesConfigurationRefreshAndMayStartRequestedTask() {
        val decision = LocalSettingsExecutionPolicy.decide(
            accountEnabled = true,
            accountRunnable = true,
            executionOwnerActive = true,
            executionRequested = true,
        )

        assertTrue(decision.executionActive)
        assertTrue(decision.taskStarted)
        assertFalse(decision.waitingForAccountStart)
        assertTrue(decision.shouldRefreshExecutionOwner)
    }

    @Test
    fun disabledFeatureStillRefreshesAnAlreadyRunningOwnerWithoutStartingTask() {
        val decision = LocalSettingsExecutionPolicy.decide(
            accountEnabled = true,
            accountRunnable = true,
            executionOwnerActive = true,
            executionRequested = false,
        )

        assertTrue(decision.executionActive)
        assertFalse(decision.taskStarted)
        assertFalse(decision.waitingForAccountStart)
        assertTrue(decision.shouldRefreshExecutionOwner)
    }

    @Test
    fun stoppedAccountCannotRunJustBecauseAnotherAccountOwnsTheService() {
        val decision = LocalSettingsExecutionPolicy.decide(
            accountEnabled = true,
            accountRunnable = false,
            executionOwnerActive = true,
            executionRequested = true,
        )

        assertFalse(decision.executionActive)
        assertFalse(decision.taskStarted)
        assertTrue(decision.waitingForAccountStart)
        assertTrue(decision.shouldRefreshExecutionOwner)
    }
}
