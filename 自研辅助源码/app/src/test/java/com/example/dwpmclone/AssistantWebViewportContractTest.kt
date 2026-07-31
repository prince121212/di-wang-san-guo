package com.example.dwpmclone

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AssistantWebViewportContractTest {
    @Test
    fun sharedPhoneCanvasFitsOnceAndCannotBePinchZoomed() {
        val source = activitySource()

        assertTrue(source.contains("useWideViewPort = true"))
        assertTrue(source.contains("loadWithOverviewMode = true"))
        assertTrue(source.contains("textZoom = 100"))
        assertTrue(source.contains("setSupportZoom(false)"))
        assertTrue(source.contains("builtInZoomControls = false"))
        assertTrue(source.contains("displayZoomControls = false"))
        assertFalse(source.contains("setInitialScale("))
    }

    @Test
    fun sharedPageConfirmDialogsReachTheLocalApiBridge() {
        val source = activitySource()

        assertTrue(source.contains("webView.webChromeClient = WebChromeClient()"))
    }

    private fun activitySource(): String {
        val relative = "src/main/java/com/example/dwpmclone/AssistantWebActivity.kt"
        val candidates = listOf(File(relative), File("app/$relative"))
        val source = candidates.firstOrNull(File::isFile)
        checkNotNull(source) { "AssistantWebActivity.kt not found from ${File(".").absolutePath}" }
        return source.readText()
    }
}
