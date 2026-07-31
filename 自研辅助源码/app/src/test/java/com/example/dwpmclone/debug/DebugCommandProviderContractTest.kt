package com.example.dwpmclone.debug

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DebugCommandProviderContractTest {
    @Test
    fun providerExistsOnlyInDebugAndIsReachableByAdbShell() {
        val debugManifest = source("src/debug/AndroidManifest.xml")
        val mainManifest = source("src/main/AndroidManifest.xml")

        assertTrue(debugManifest.contains(".debug.DebugCommandProvider"))
        assertTrue(debugManifest.contains("android:authorities=\"\${applicationId}.debug\""))
        assertTrue(debugManifest.contains("android:exported=\"true\""))
        assertTrue(debugManifest.contains("android:grantUriPermissions=\"false\""))
        assertFalse(mainManifest.contains("DebugCommandProvider"))
    }

    @Test
    fun providerForwardsTheSharedMessageCodecToTheExistingController() {
        val provider = source(
            "src/debug/java/com/example/dwpmclone/debug/DebugCommandProvider.kt"
        )

        assertTrue(provider.contains("AssistantApiMessageCodec.decode(raw)"))
        assertTrue(provider.contains("controller.handle(request).toJson()"))
        assertTrue(provider.contains("controller = LocalAssistantApiController(appContext)"))
        assertFalse(provider.contains("\"/api/dungeon"))
        assertFalse(provider.contains("\"/api/military"))
        assertFalse(provider.contains("\"/api/raid"))
    }

    @Test
    fun providerIsUidRestrictedAndPostRequiresTwoIndependentSignals() {
        val provider = source(
            "src/debug/java/com/example/dwpmclone/debug/DebugCommandProvider.kt"
        )

        assertTrue(provider.contains("Binder.getCallingUid()"))
        assertTrue(provider.contains("Process.SHELL_UID"))
        assertTrue(provider.contains("Process.ROOT_UID"))
        assertTrue(provider.contains("Process.SYSTEM_UID"))
        assertTrue(provider.contains("extras?.getBoolean(EXTRA_ALLOW_POST, false) == true"))
        assertTrue(provider.contains("extras.getString(EXTRA_POST_CONFIRMATION) == POST_CONFIRMATION"))
        assertTrue(provider.contains("const val POST_CONFIRMATION = \"ALLOW_REAL_POST\""))
    }

    @Test
    fun providerEnablesWebviewInspectionAndDisablesCrud() {
        val provider = source(
            "src/debug/java/com/example/dwpmclone/debug/DebugCommandProvider.kt"
        )

        assertTrue(provider.contains("WebView.setWebContentsDebuggingEnabled(true)"))
        assertTrue(provider.contains("override fun query("))
        assertTrue(provider.contains("override fun insert("))
        assertTrue(provider.contains("override fun delete("))
        assertTrue(provider.contains("override fun update("))
        assertTrue(provider.contains("UnsupportedOperationException"))
    }

    private fun source(relative: String): String {
        val candidates = listOf(File(relative), File("app/$relative"))
        val file = candidates.firstOrNull(File::isFile)
        checkNotNull(file) { "$relative not found from ${File(".").absolutePath}" }
        return file.readText()
    }
}
