package com.example.dwpmclone.ui.web

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MilitaryRefreshConcurrencyContractTest {
    @Test
    fun stateAndMilitaryRefreshHaveNoKotlinNetworkAdapter() {
        val source = operationServiceSource()

        assertFalse(source.contains("private fun stateRefresh"))
        assertFalse(source.contains("private fun militaryIntel"))
        assertFalse(source.contains("private fun heartbeat"))
        assertFalse(source.contains("handleSharedCoreNetwork"))
        assertFalse(source.contains("SessionAwareGameProtocolClient"))
        assertTrue(source.contains("Local-only presentation adapter"))
    }

    private fun operationServiceSource(): String {
        val relative = "src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt"
        val candidates = listOf(File(relative), File("app/$relative"))
        val source = candidates.firstOrNull(File::isFile)
        checkNotNull(source) { "LocalProtocolOperationService.kt not found from ${File(".").absolutePath}" }
        return source.readText()
    }
}
