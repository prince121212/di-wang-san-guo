package com.example.dwpmclone.host

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SharedPythonCoreHostContractTest {
    @Test
    fun androidBuildPackagesTheRepositorySharedSourceInsteadOfACopy() {
        val rootBuild = source("../build.gradle.kts", "build.gradle.kts")
        val appBuild = source("app/build.gradle.kts", "build.gradle.kts")

        assertTrue(rootBuild.contains("id(\"com.chaquo.python\") version \"17.0.0\""))
        assertTrue(appBuild.contains("srcDir(sharedPythonSource.asFile)"))
        assertTrue(appBuild.contains("generateSharedPythonBundle"))
        assertTrue(appBuild.contains("minSdk = 24"))
        assertTrue(appBuild.contains("version = \"3.10\""))
        assertFalse(resolve("app/src/main/python/dwpm_core", "src/main/python/dwpm_core").exists())
    }

    @Test
    fun applicationWarmsTheInterpreterOffTheUiThread() {
        val application = source(
            "app/src/main/java/com/example/dwpmclone/SharedCoreApplication.kt",
            "src/main/java/com/example/dwpmclone/SharedCoreApplication.kt"
        )
        val host = source(
            "app/src/main/java/com/example/dwpmclone/host/SharedPythonCoreHost.kt",
            "src/main/java/com/example/dwpmclone/host/SharedPythonCoreHost.kt"
        )

        assertTrue(application.contains("warmUpAsync()"))
        assertTrue(host.contains("Thread(runnable, \"shared-python-warmup\")"))
        assertTrue(host.contains("Python.start(AndroidPlatform(appContext))"))
        assertTrue(host.contains("\"create_hosted_core\""))
        assertTrue(host.contains("platformPorts"))
        assertTrue(host.contains("operations-v2.json"))
        assertTrue(host.contains("\"dispatch_json\""))
        assertTrue(host.contains("\"account_lifecycle_snapshot_json\""))
        assertTrue(host.contains("\"account_transition_json\""))
        assertTrue(host.contains("AccountStateTransitionSource"))
        assertTrue(host.contains("\"account_records_snapshot_json\""))
        assertTrue(host.contains("\"account_record_presentation_json\""))
        assertTrue(host.contains("SharedAccountStateGateway"))
        assertTrue(host.contains("\"dispatch_json\""))
    }

    @Test
    fun pocOperationIsDurableImmediateAndCannotReachTheNetwork() {
        val controller = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt"
        )
        val operationCore = source(
            "../shared_core/python/dwpm_core/operations.py",
            "../../shared_core/python/dwpm_core/operations.py"
        )

        assertTrue(controller.contains("/api/core/operations/simulate"))
        assertTrue(controller.contains("/api/core/operations/status"))
        assertTrue(controller.contains("/api/core/verification/protocol"))
        assertTrue(controller.contains("ApplicationInfo.FLAG_DEBUGGABLE"))
        assertTrue(operationCore.contains("idempotencyKey"))
        assertTrue(operationCore.contains("temporary.replace(self._path)"))
        assertTrue(operationCore.contains("daemon=True"))
        assertFalse(operationCore.contains("import socket"))
        assertFalse(operationCore.contains("import requests"))
        assertFalse(operationCore.contains("import urllib"))
    }

    @Test
    fun phaseFiveHostPortsExposeCapabilitiesWithoutDuplicatingBusinessRules() {
        val ports = source(
            "app/src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt",
            "src/main/java/com/example/dwpmclone/host/AndroidSharedCorePortBridge.kt"
        )
        val facade = source(
            "../shared_core/python/dwpm_core/facade.py",
            "../../shared_core/python/dwpm_core/facade.py"
        )
        val operations = source(
            "../shared_core/python/dwpm_core/operations.py",
            "../../shared_core/python/dwpm_core/operations.py"
        )

        assertTrue(ports.contains("KeystoreCredentialVault"))
        assertTrue(ports.contains("KeystoreSessionSecretVault"))
        assertTrue(ports.contains("saveSessionSecrets"))
        assertTrue(ports.contains("loadSessionSecrets"))
        assertTrue(ports.contains("networkAvailable"))
        assertTrue(ports.contains("NotificationManager"))
        assertTrue(ports.contains("AlarmManager"))
        assertTrue(ports.contains("TaskLogRepository"))
        assertFalse(ports.contains("0x1522"))
        assertFalse(ports.contains("SessionAwareGameProtocolClient"))
        assertTrue(facade.contains("def dispatch("))
        assertTrue(facade.contains("sensitive field cannot enter operation ledger"))
        assertTrue(operations.contains("dwpm-network-"))
        assertTrue(operations.contains("UNCERTAIN"))
        assertTrue(operations.contains("request-already-sent"))
    }

    @Test
    fun accountMetadataUsesSharedPythonWhileSecretsRemainInKeystore() {
        val repository = source(
            "app/src/main/java/com/example/dwpmclone/data/local/LocalAccountRepository.kt",
            "src/main/java/com/example/dwpmclone/data/local/LocalAccountRepository.kt"
        )
        val store = source(
            "../shared_core/python/dwpm_core/account/store.py",
            "../../shared_core/python/dwpm_core/account/store.py"
        )

        assertTrue(repository.contains("SharedPythonCoreHost.get(context)"))
        assertTrue(repository.contains("accountRecordsImportIfEmpty"))
        assertTrue(repository.contains("listPublicAccounts"))
        assertTrue(repository.contains("SessionSecretPolicy.publicFields"))
        assertTrue(store.contains("secrets\": \"platform-ports-only"))
        assertTrue(store.contains("sensitive field cannot enter account store"))
        assertFalse(store.contains("load_password("))

        val controller = source(
            "app/src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt",
            "src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt"
        )
        assertTrue(controller.contains("GET\" to \"/api/accounts\" -> sharedCoreAccounts"))
        assertTrue(controller.contains("dispatchAccountProjection"))
        assertFalse(controller.contains("private fun accountArray()"))
    }

    private fun source(vararg candidates: String): String {
        val file = candidates.asSequence().map(::File).firstOrNull(File::isFile)
        checkNotNull(file) { "Source not found: ${candidates.joinToString()}" }
        return file.readText()
    }

    private fun resolve(vararg candidates: String): File =
        candidates.asSequence().map(::File).firstOrNull(File::exists) ?: File(candidates.first())
}
