package com.example.dwpmclone.ui.web

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MilitaryRefreshConcurrencyContractTest {
    @Test
    fun stateAndMilitaryRefreshBypassTheLongRunningSchedulerMutex() {
        val source = operationServiceSource()
        val stateRefresh = source
            .substringAfter("private fun stateRefresh")
            .substringBefore("private fun brushSearch")
        val militaryRefresh = source
            .substringAfter("private fun militaryIntel")
            .substringBefore("private fun heartbeat")

        assertTrue(stateRefresh.contains("runner.executeImmediateReadOnly("))
        assertFalse(stateRefresh.contains("runner.execute(accountId"))
        assertTrue(militaryRefresh.contains("runner.executeImmediateReadOnly("))
        assertFalse(militaryRefresh.contains("runner.execute(accountId"))
    }

    private fun operationServiceSource(): String {
        val relative = "src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt"
        val candidates = listOf(File(relative), File("app/$relative"))
        val source = candidates.firstOrNull(File::isFile)
        checkNotNull(source) { "LocalProtocolOperationService.kt not found from ${File(".").absolutePath}" }
        return source.readText()
    }
}
