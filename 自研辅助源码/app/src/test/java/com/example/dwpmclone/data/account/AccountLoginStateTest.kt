package com.example.dwpmclone.data.account

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class AccountLoginStateTest {
    @Test
    fun `android keeps only transport state names while Python owns decisions`() {
        assertEquals("REAL_PROTOCOL_ONLINE", AccountLoginState.ONLINE)
        assertEquals("REAL_PROTOCOL_CHECKING", AccountLoginState.CHECKING)
        assertEquals("REAL_PROTOCOL_NETWORK_PAUSED", AccountLoginState.NETWORK_PAUSED)
        assertEquals("REAL_PROTOCOL_NEED_RELOGIN", AccountLoginState.NEED_RELOGIN)
        assertEquals("REAL_PROTOCOL_OFFLINE", AccountLoginState.OFFLINE)
        assertEquals("REAL_PROTOCOL_STOPPED", AccountLoginState.STOPPED)

        val source = source(
            "app/src/main/java/com/example/dwpmclone/data/account/AccountSessionRecovery.kt",
            "src/main/java/com/example/dwpmclone/data/account/AccountSessionRecovery.kt"
        )
        assertFalse(source.contains("fun requiresRelogin("))
        assertFalse(source.contains("fun shouldProbe("))
        assertFalse(source.contains("object AccountLifecyclePresentationPolicy"))
    }

    @Test
    fun `production recovery receives the shared Python decision source`() {
        val service = source(
            "app/src/main/java/com/example/dwpmclone/service/AssistantForegroundService.kt",
            "src/main/java/com/example/dwpmclone/service/AssistantForegroundService.kt"
        )
        val host = source(
            "app/src/main/java/com/example/dwpmclone/host/SharedPythonCoreHost.kt",
            "src/main/java/com/example/dwpmclone/host/SharedPythonCoreHost.kt"
        )
        assertFalse(service.contains("heartbeatIntervalMillis = behaviorContract.accountLifecycle"))
        assertEquals(true, service.contains("lifecycleDecisions = SharedPythonCoreHost.get(this)"))
        assertEquals(true, host.contains("AccountLifecycleDecisionSource,"))
        assertEquals(true, host.contains("account_lifecycle_snapshot_json"))
    }

    private fun source(vararg candidates: String): String {
        val file = candidates.asSequence().map(::File).firstOrNull(File::isFile)
        checkNotNull(file) { "Source not found: ${candidates.joinToString()}" }
        return file.readText()
    }
}
