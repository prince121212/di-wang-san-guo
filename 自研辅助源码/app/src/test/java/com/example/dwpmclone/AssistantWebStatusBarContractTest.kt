package com.example.dwpmclone

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

class AssistantWebStatusBarContractTest {
    @Test
    fun webViewFitsInsideSystemStatusAndNavigationBars() {
        val activity = sourceFile(
            "app/src/main/java/com/example/dwpmclone/AssistantWebActivity.kt",
            "src/main/java/com/example/dwpmclone/AssistantWebActivity.kt",
        ).readText()
        val style = sourceFile(
            "app/src/main/res/values/styles.xml",
            "src/main/res/values/styles.xml",
        ).readText()

        assertTrue(activity.contains("window.setDecorFitsSystemWindows(false)"))
        assertTrue(activity.contains("WindowInsets.Type.systemBars()"))
        assertTrue(activity.contains("WindowInsets.Type.displayCutout()"))
        assertTrue(activity.contains("bars.top"))
        assertTrue(activity.contains("content.requestApplyInsets()"))
        assertTrue(style.contains("android:windowOptOutEdgeToEdgeEnforcement"))
    }

    private fun sourceFile(vararg candidates: String): File = candidates
        .asSequence()
        .map(::File)
        .firstOrNull(File::isFile)
        ?: error("source file not found: ${candidates.joinToString()}")
}
