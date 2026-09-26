package com.example.dwpmclone.ui.hosting

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BackgroundHostingContractTest {
    @Test
    fun backgroundWarningNamesTheMissingSettingsWithoutBlockingStartup() {
        fun state(notification: Boolean, battery: Boolean) = BackgroundHostingPermissionState(
            notificationGranted = notification,
            batteryOptimizationExempt = battery,
            exactAlarmGranted = true,
            xiaomiManualReviewRequired = false,
            debugBuild = true,
            sdkInt = 36,
            manufacturer = "Xiaomi",
            model = "test",
        )

        assertEquals(
            "后台运行提醒：未开启通知权限，仍可启动账号和任务；切到后台或锁屏后，系统可能暂停网络或停止应用。可在攻略-后台运行设置中按需开启。",
            state(notification = false, battery = true).backgroundRiskMessage(),
        )
        assertEquals(
            "后台运行提醒：未开启忽略电池优化，仍可启动账号和任务；切到后台或锁屏后，系统可能暂停网络或停止应用。可在攻略-后台运行设置中按需开启。",
            state(notification = true, battery = false).backgroundRiskMessage(),
        )
        assertEquals(
            "后台运行提醒：未开启通知权限、忽略电池优化，仍可启动账号和任务；切到后台或锁屏后，系统可能暂停网络或停止应用。可在攻略-后台运行设置中按需开启。",
            state(notification = false, battery = false).backgroundRiskMessage(),
        )
        assertNull(state(notification = true, battery = true).backgroundRiskMessage())
        val denied = state(notification = false, battery = false).toJson()
        assertFalse(denied.getBoolean("startupBlockedByPermissions"))
        assertEquals(0, denied.getJSONArray("blockingIssues").length())
        assertEquals(2, denied.getJSONArray("warningIssues").length())
        val items=denied.getJSONArray("items")
        for(i in 0 until items.length()) assertFalse(items.getJSONObject(i).getBoolean("required"))
    }

    @Test
    fun systemBackgroundRestrictionIsReportedAsARiskNotAnAppGate() {
        val state = BackgroundHostingPermissionState(
            notificationGranted = true,
            batteryOptimizationExempt = true,
            exactAlarmGranted = true,
            xiaomiManualReviewRequired = false,
            debugBuild = true,
            sdkInt = 36,
            manufacturer = "AOSP",
            model = "test",
            backgroundRestricted = true,
        )
        assertFalse(state.reliableHostingReady)
        assertEquals(
            "后台运行提醒：未开启解除系统后台运行限制，仍可启动账号和任务；切到后台或锁屏后，系统可能暂停网络或停止应用。可在攻略-后台运行设置中按需开启。",
            state.backgroundRiskMessage(),
        )
        assertTrue(state.toJson().getJSONArray("items").toString().contains("background-restricted"))
    }

    @Test
    fun exactAlarmIsAnOptionalPunctualityEnhancement() {
        val state = BackgroundHostingPermissionState(
            notificationGranted = true,
            batteryOptimizationExempt = true,
            exactAlarmGranted = false,
            xiaomiManualReviewRequired = false,
            debugBuild = true,
            sdkInt = 36,
            manufacturer = "AOSP",
            model = "test",
        )
        assertTrue(state.reliableHostingReady)
        assertNull(state.backgroundRiskMessage())
        assertEquals(
            "STANDARD_READY_PUNCTUALITY_DEGRADED",
            state.reliabilityLevel,
        )
        val exactAlarm = state.toJson().getJSONArray("items").let { items ->
            (0 until items.length())
                .map(items::getJSONObject)
                .first { it.getString("key") == "exact-alarm" }
        }
        assertFalse(exactAlarm.getBoolean("required"))
    }

    @Test
    fun schedulerUsesTwoWakeChannelsAndUsesOnlyShortExecutionWakeLocks() {
        val service = source(
            "src/main/java/com/example/dwpmclone/service/AssistantForegroundService.kt"
        )
        val scheduling = service.substringAfter("private fun scheduleNextTick")
            .substringBefore("private fun scheduleWakeupAlarm")

        assertTrue(scheduling.contains("handler.postDelayed(tickRunnable, requestedDelay)"))
        assertTrue(scheduling.contains("scheduleWakeupAlarm(alarmAt)"))
        assertTrue(service.contains("ACTION_EXECUTION_WATCHDOG"))
        assertTrue(service.contains("armExecutionWatchdog()"))
        // Every tick starts by guaranteeing itself a full window; a renew never
        // shortens a longer lease already covering the CPU.
        assertTrue(service.contains("renewWakeLock(TICK_WAKELOCK_TIMEOUT_MILLIS)"))
        assertTrue(service.contains("releaseWakeLock()"))
        assertTrue(service.contains("TICK_WAKELOCK_TIMEOUT_MILLIS"))
        assertTrue(service.contains("PendingOperationWakeLease"))
        assertTrue(service.contains("PENDING_OPERATION_WAKE_LEASE_MILLIS"))
        assertTrue(service.contains("finishSchedulerWakeWindow"))
        assertFalse(scheduling.contains("acquireWakeLock()"))
        assertFalse(scheduling.contains("releaseWakeLock()"))
        // The CPU lease may outlive a tick only by a policy-bounded gap, and a
        // renew must re-arm the held lock rather than release-then-acquire:
        // deep Doze suspends the device in the gap between those two calls.
        assertTrue(service.contains("SchedulerTickPolicy.shouldHoldWakeLockAcross"))
        assertTrue(service.contains("SchedulerTickPolicy.wakeHoldTimeoutMillis"))
        val wakeWindow = service.substringAfter("private fun finishSchedulerWakeWindow")
            .substringBefore("private fun reportPreviousInterruption")
        assertFalse(wakeWindow.contains("releaseWakeLock(reason = \"renew"))
        assertTrue(wakeWindow.contains("renewWakeLock("))
        assertTrue(service.contains("setExactAndAllowWhileIdle"))
        assertTrue(service.contains("setAndAllowWhileIdle"))
        assertTrue(service.contains("consumeAndRunScheduledTick"))
        assertTrue(service.contains("tag = \"scheduler-health\""))
    }

    @Test
    fun releaseBuildHasOptionalGuideWithoutPermissionStartupGates() {
        val manifest = source("src/main/AndroidManifest.xml")
        val coordinator = source(
            "src/main/java/com/example/dwpmclone/ui/hosting/BackgroundHostingPermissionCoordinator.kt"
        )
        val state = source(
            "src/main/java/com/example/dwpmclone/ui/hosting/BackgroundHostingPermissionState.kt"
        )
        val controller = source(
            "src/main/java/com/example/dwpmclone/ui/web/LocalAssistantApiController.kt"
        )
        val frontend = source("../电脑端辅助前端/app.js")
        val index = source("../电脑端辅助前端/index.html")

        assertTrue(manifest.contains("android.permission.SCHEDULE_EXACT_ALARM"))
        assertTrue(state.contains("isIgnoringBatteryOptimizations"))
        assertTrue(state.contains("canScheduleExactAlarms"))
        assertTrue(coordinator.contains("ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS"))
        assertTrue(coordinator.contains("ACTION_REQUEST_SCHEDULE_EXACT_ALARM"))
        assertTrue(coordinator.contains("AutoStartManagementActivity"))
        assertTrue(coordinator.contains("ScenarioPowerSavingActivity"))
        assertTrue(
            coordinator.indexOf("ScenarioPowerSavingActivity") <
                coordinator.indexOf("Settings.ACTION_WIFI_SETTINGS"),
        )
        assertFalse(controller.contains("BACKGROUND_PERMISSION_REQUIRED"))
        assertFalse(controller.contains("!permissions.reliableHostingReady"))
        assertFalse(controller.contains("!backgroundPermissions.reliableHostingReady"))
        val service = source("src/main/java/com/example/dwpmclone/service/AssistantForegroundService.kt")
        assertFalse(service.contains("requiredBackgroundPermissionsReady"))
        assertFalse(service.contains("required background permission missing"))
        assertFalse(service.contains("required background permission revoked"))
        assertTrue(service.contains("reportBackgroundRisk()"))
        assertTrue(service.contains("startForeground(NOTIFICATION_ID"))
        assertFalse(coordinator.contains("reliableHostingReady) open(\"guide\")"))
        assertTrue(controller.contains("/api/background/permissions"))
        assertTrue(frontend.contains("renderBackgroundPermissionGuide"))
        assertTrue(index.contains("id=\"backgroundSettingsGuide\""))
        assertTrue(state.contains("key = \"sleep-mode\""))
        assertTrue(state.contains("action = \"wifi-settings\""))
        assertTrue(frontend.contains("item?.key === \"sleep-mode\" ? \"查看设置\""))
        assertFalse(index.contains("networkScheduleDiagnosis"))
        assertFalse(frontend.contains("历史断网已标记处理"))
    }

    private fun source(relative: String): String {
        val candidates = listOf(
            File(relative),
            File("app/$relative"),
            File("../$relative"),
        )
        val file = candidates.firstOrNull(File::isFile)
        checkNotNull(file) { "$relative not found from ${File(".").absolutePath}" }
        return file.readText()
    }
}
