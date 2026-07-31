package com.example.dwpmclone.ui.web

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GeneralVisitConcurrencyContractTest {
    @Test
    fun candidateQueryIsImmediateWhileClaimRemainsExclusive() {
        val source = operationServiceSource()
        val candidates = source
            .substringAfter("private fun generalVisitCandidates")
            .substringBefore("private fun generalVisitClaim")
        val claim = source
            .substringAfter("private fun generalVisitClaim")
            .substringBefore("private fun completedDailyResponse")

        assertTrue(candidates.contains("runner.executeImmediateReadOnly("))
        assertFalse(candidates.contains("runner.execute(accountId"))
        assertTrue(claim.contains("runner.execute(accountId"))
        assertFalse(claim.contains("runner.executeImmediateReadOnly("))
    }

    private fun operationServiceSource(): String {
        val relative = "src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt"
        val candidates = listOf(File(relative), File("app/$relative"))
        val source = candidates.firstOrNull(File::isFile)
        checkNotNull(source) { "LocalProtocolOperationService.kt not found from ${File(".").absolutePath}" }
        return source.readText()
    }
}
