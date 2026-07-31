package com.example.dwpmclone.domain.scheduler

import org.junit.Assert.assertEquals
import org.junit.Test

class ResidentTaskActivationPolicyTest {
    private val residents = setOf("mine", "lossless", "brushYellow", "raid", "dungeon", "ministry")

    @Test
    fun legacyStartedSessionWithoutExplicitFieldRestoresAllResidents() {
        assertEquals(
            residents,
            ResidentTaskActivationPolicy.activeKeys(
                mapOf("savedTasksStarted" to "true"),
                residents
            )
        )
    }

    @Test
    fun explicitEmptyFieldMeansNoResidentIsActive() {
        assertEquals(
            emptySet<String>(),
            ResidentTaskActivationPolicy.activeKeys(
                mapOf(
                    "savedTasksStarted" to "true",
                    "activeResidentTaskKeys" to ""
                ),
                residents
            )
        )
    }

    @Test
    fun disablingTheLastResidentDoesNotReenableAllResidents() {
        val keys = ResidentTaskActivationPolicy.afterToggle(
            channelExtra = mapOf(
                "savedTasksStarted" to "true",
                "activeResidentTaskKeys" to "brushYellow"
            ),
            allResidentKeys = residents,
            key = "brushYellow",
            active = false
        )
        val persisted = mapOf(
            "savedTasksStarted" to "true",
            "activeResidentTaskKeys" to ResidentTaskActivationPolicy.encode(keys)
        )

        assertEquals(emptySet<String>(), keys)
        assertEquals(
            emptySet<String>(),
            ResidentTaskActivationPolicy.activeKeys(persisted, residents)
        )
    }

    @Test
    fun savingOneEnabledRuleActivatesOnlyThatResident() {
        assertEquals(
            setOf("mine"),
            ResidentTaskActivationPolicy.afterToggle(
                channelExtra = mapOf(
                    "savedTasksStarted" to "false",
                    "activeResidentTaskKeys" to ""
                ),
                allResidentKeys = residents,
                key = "mine",
                active = true
            )
        )
    }

    @Test
    fun explicitAccountStopClearsBothTheStartedFlagAndResidentKeys() {
        val stopped = ResidentTaskActivationPolicy.stoppedUpdates()

        assertEquals("false", stopped["savedTasksStarted"])
        assertEquals("", stopped["activeResidentTaskKeys"])
        assertEquals(emptySet<String>(), ResidentTaskActivationPolicy.activeKeys(stopped, residents))
    }
}
