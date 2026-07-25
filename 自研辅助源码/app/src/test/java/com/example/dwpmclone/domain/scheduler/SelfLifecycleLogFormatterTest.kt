package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.protocol.TaskType
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SelfLifecycleLogFormatterTest {
    @Test
    fun taskStopMarkerContainsStableEventSourceModeAndSafetyFlag() {
        val line = SelfLifecycleLogFormatter.taskStop(
            accountId = 7,
            sourceMode = 1,
            reason = "explicit stop action",
            stoppedTaskTypes = listOf(TaskType.SHUA_HUANG),
            logoutRequested = true,
            logoutSucceeded = true,
            logoutMessage = "real read-only session marked logged out locally"
        )

        assertTrue(line.startsWith("[self-lifecycle-json] "))
        val json = JSONObject(line.removePrefix("[self-lifecycle-json] "))
        assertEquals("task_stop", json.getString("event"))
        assertEquals(7L, json.getLong("accountId"))
        assertEquals(1, json.getInt("sourceMode"))
        assertEquals("SHUA_HUANG", json.getJSONArray("stoppedTaskTypes").getString(0))
        assertTrue(json.getBoolean("logoutRequested"))
        assertTrue(json.getBoolean("logoutSucceeded"))
        assertFalse(json.getBoolean("realActionNetworkAllowed"))
    }

    @Test
    fun sessionLogoutMarkerContainsLogoutOnceEvidence() {
        val line = SelfLifecycleLogFormatter.sessionLogout(
            accountId = 7,
            sourceMode = 1,
            reason = "terminal",
            logoutRequested = true,
            logoutSucceeded = true,
            logoutMessage = "logout ok"
        )

        val json = JSONObject(line.removePrefix("[self-lifecycle-json] "))
        assertEquals("session_logout", json.getString("event"))
        assertEquals(1, json.getInt("sourceMode"))
        assertTrue(json.getBoolean("logoutOnce"))
        assertFalse(json.getBoolean("realActionNetworkAllowed"))
    }
}
