package com.example.dwpmclone.ui.web

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GeneralVisitConcurrencyContractTest {
    @Test
    fun candidateQueryAndClaimUseOneSharedPythonWorkflowWithExplicitSendBoundary() {
        val service = source(
            "src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt",
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalProtocolOperationService.kt"
        )
        val hostedCore = source(
            "../shared_core/python/dwpm_core/__init__.py",
            "../../shared_core/python/dwpm_core/__init__.py"
        )
        val facade = source(
            "../shared_core/python/dwpm_core/facade.py",
            "../../shared_core/python/dwpm_core/facade.py"
        )
        val candidates = facade
            .substringAfter("def _daily_general_visit_candidates_raw(")
            .substringBefore("def _run_daily_general_visit_candidates_game_workflow(")
        val claim = facade
            .substringAfter("def _run_daily_general_visit_game_workflow(")
            .substringBefore("def _run_daily_sign_in_game_workflow(")

        assertFalse(service.contains("private fun generalVisitCandidates"))
        assertFalse(service.contains("private fun generalVisitClaim"))
        assertTrue(hostedCore.contains("facade._run_daily_general_visit_candidates_game_workflow"))
        assertTrue(hostedCore.contains("facade._run_daily_general_visit_game_workflow"))
        assertTrue(candidates.contains("\"readOnly\": True"))
        assertFalse(candidates.contains("mark_request_sent"))
        assertTrue(claim.contains("execution.mark_request_sent"))
        assertTrue(claim.contains("OperationUncertainError"))
    }

    private fun source(vararg paths: String): String {
        val file = paths.map(::File).firstOrNull(File::isFile)
        checkNotNull(file) { "source not found from ${File(".").absolutePath}: ${paths.toList()}" }
        return file.readText()
    }
}
