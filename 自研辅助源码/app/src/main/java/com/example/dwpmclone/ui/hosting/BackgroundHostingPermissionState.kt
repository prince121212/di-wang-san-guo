package com.example.dwpmclone.ui.hosting

import android.Manifest
import android.app.ActivityManager
import android.app.AlarmManager
import android.app.NotificationManager
import android.content.Context
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.os.Build
import android.os.PowerManager
import com.example.dwpmclone.service.AssistantForegroundService
import org.json.JSONArray
import org.json.JSONObject

/** Observable prerequisites for reliable user-started, screen-off hosting. */
data class BackgroundHostingPermissionState(
    val notificationGranted: Boolean,
    val batteryOptimizationExempt: Boolean,
    val exactAlarmGranted: Boolean,
    val xiaomiManualReviewRequired: Boolean,
    val debugBuild: Boolean,
    val sdkInt: Int,
    val manufacturer: String,
    val model: String,
    /** Public AOSP signal for the user-level restricted background mode. */
    val backgroundRestricted: Boolean = false,
    /** Permission is install-time on current Android, but exposing it makes
     *  readiness auditable instead of assuming every manifest merge succeeded. */
    val foregroundServiceGranted: Boolean = true,
    /** AOSP exposes no cross-OEM API for these switches.  UNKNOWN is deliberate. */
    val vendorManualReviewRequired: Boolean = false,
    val vendorFamily: String = "aosp",
) {
    /**
     * Standard prerequisites required to start hosting.  Exact alarms are a
     * punctuality enhancement, not a correctness prerequisite: the service has
     * a Handler path, an inexact allow-while-idle fallback and a durable
     * operation ledger when this special access is unavailable.
     */
    val reliableHostingReady: Boolean
        get() = notificationGranted && batteryOptimizationExempt &&
            foregroundServiceGranted && !backgroundRestricted

    /** Standard Android prerequisites are known; OEM policy remains a separate risk. */
    val reliabilityLevel: String
        get() = when {
            !reliableHostingReady -> "BLOCKED_STANDARD_PERMISSION"
            !exactAlarmGranted -> "STANDARD_READY_PUNCTUALITY_DEGRADED"
            vendorManualReviewRequired -> "STANDARD_READY_VENDOR_REVIEW"
            else -> "STANDARD_READY"
        }

    fun blockingIssueMessage(prefix: String = "后台托管未启动"): String? {
        val missing = buildList {
            if (!notificationGranted) add("通知权限")
            if (!batteryOptimizationExempt) add("忽略电池优化")
            if (!foregroundServiceGranted) add("前台服务权限")
            if (backgroundRestricted) add("解除系统后台运行限制")
        }
        if (missing.isEmpty()) return null
        return "$prefix：缺少${missing.joinToString("、")}；请在攻略-后台运行设置中完成授权后重试"
    }

    fun toJson(): JSONObject = JSONObject()
        .put("ok", true)
        .put("platform", "android")
        .put("debugBuild", debugBuild)
        .put("sdkInt", sdkInt)
        .put("manufacturer", manufacturer)
        .put("model", model)
        .put("serviceActive", AssistantForegroundService.isExecutionOwnerActive())
        .put("reliableHostingReady", reliableHostingReady)
        .put("reliabilityLevel", reliabilityLevel)
        .put("manualReviewRequired", vendorManualReviewRequired)
        .put("vendorFamily", vendorFamily)
        .put("backgroundRestricted", backgroundRestricted)
        .put("vendorPolicy", JSONObject()
            .put("state", if (vendorManualReviewRequired) "UNKNOWN_NEEDS_USER_CONFIRMATION" else "UNKNOWN")
            .put("queryable", false)
            .put("guarantee", "NO_PUBLIC_API_GUARANTEE"))
        // Always present, not only when a deep link fails: the vendor settings
        // components are undocumented and get renamed between ROM releases, so
        // written steps are the guidance that cannot break.
        .put("vendorGuidance", VendorBackgroundGuidance.forManufacturer(manufacturer).toJson())
        .put("blockingIssues", JSONArray().apply {
            if (!notificationGranted) put("notification")
            if (!batteryOptimizationExempt) put("battery-optimization")
            if (!foregroundServiceGranted) put("foreground-service")
            if (backgroundRestricted) put("background-restricted")
        })
        .put("items", JSONArray().apply {
            put(item(
                key = "notification",
                title = "通知权限",
                required = true,
                granted = notificationGranted,
                action = "notification",
                detail = "前台托管必须让用户持续看到运行状态和停止入口",
            ))
            put(item(
                key = "battery-optimization",
                title = "忽略电池优化",
                required = true,
                granted = batteryOptimizationExempt,
                action = "battery-optimization",
                detail = "保证息屏后 CPU 和游戏网络不被 Doze 长时间冻结",
            ))
            put(item(
                key = "exact-alarm",
                title = "精确闹钟",
                required = false,
                granted = exactAlarmGranted,
                action = "exact-alarm",
                detail = "作为 Handler 之外的截止时间看门狗；未授权时仍可用可延迟闹钟和持久化恢复，但触发时间可能延后",
            ))
            put(item(
                key = "sleep-mode",
                title = "省电模式 / 睡眠模式",
                required = false,
                granted = null,
                action = "wifi-settings",
                detail = "App 无法读取厂商开关状态；请手动确认已关闭睡眠模式、定时省电或定时关闭 WLAN，避免息屏后整夜断网",
            ))
            put(item(
                key = "background-restricted",
                title = "系统后台运行限制",
                required = true,
                granted = !backgroundRestricted,
                action = "app-details",
                detail = "Android 的系统级受限模式会阻止闹钟、网络和进程恢复；请将本应用设为不限制",
            ))
            if (vendorManualReviewRequired) {
                put(item(
                    key = "vendor-battery",
                    title = "$vendorFamily 后台策略",
                    required = false,
                    granted = null,
                    action = "vendor-battery",
                    detail = "厂商没有公开可靠查询接口；请在系统设置中将本应用设为允许后台运行/不限制",
                ))
                put(item(
                    key = "vendor-autostart",
                    title = "$vendorFamily 自启动/后台启动",
                    required = false,
                    granted = null,
                    action = "vendor-autostart",
                    detail = "厂商开关无法由普通 App 自动授予；请手动允许自启动，保证重启后能恢复托管",
                ))
            } else {
                put(item(
                    key = "vendor-review",
                    title = "厂商后台策略",
                    required = false,
                    granted = null,
                    action = "vendor-battery",
                    detail = "Android 无统一 API 可确认厂商清理策略；若系统提供后台限制/自启动开关，请按需允许",
                ))
            }
        })

    companion object {
        fun read(context: Context): BackgroundHostingPermissionState {
            val notificationManager = context.getSystemService(NotificationManager::class.java)
            val notificationGranted = (
                Build.VERSION.SDK_INT < 33 ||
                    context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) ==
                    PackageManager.PERMISSION_GRANTED
                ) && (notificationManager?.areNotificationsEnabled() != false)
            val powerManager = context.getSystemService(PowerManager::class.java)
            val batteryExempt = Build.VERSION.SDK_INT < Build.VERSION_CODES.M ||
                powerManager?.isIgnoringBatteryOptimizations(context.packageName) == true
            val alarmManager = context.getSystemService(AlarmManager::class.java)
            val exactAlarmGranted = Build.VERSION.SDK_INT < Build.VERSION_CODES.S ||
                alarmManager?.canScheduleExactAlarms() == true
            val manufacturer = Build.MANUFACTURER.orEmpty()
            val vendor = VendorBackgroundGuidance.forManufacturer(manufacturer)
            val foregroundServiceGranted = context.packageManager.checkPermission(
                Manifest.permission.FOREGROUND_SERVICE,
                context.packageName,
            ) == PackageManager.PERMISSION_GRANTED
            val backgroundRestricted = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                context.getSystemService(ActivityManager::class.java)
                    ?.isBackgroundRestricted == true
            } else {
                false
            }
            return BackgroundHostingPermissionState(
                notificationGranted = notificationGranted,
                batteryOptimizationExempt = batteryExempt,
                exactAlarmGranted = exactAlarmGranted,
                xiaomiManualReviewRequired = vendor.manualReviewRequired,
                debugBuild = context.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0,
                sdkInt = Build.VERSION.SDK_INT,
                manufacturer = manufacturer,
                model = Build.MODEL.orEmpty(),
                foregroundServiceGranted = foregroundServiceGranted,
                backgroundRestricted = backgroundRestricted,
                vendorManualReviewRequired = vendor.manualReviewRequired,
                vendorFamily = vendor.family,
            )
        }

        private fun item(
            key: String,
            title: String,
            required: Boolean,
            granted: Boolean?,
            action: String,
            detail: String,
        ): JSONObject = JSONObject()
            .put("key", key)
            .put("title", title)
            .put("required", required)
            .put("granted", granted ?: JSONObject.NULL)
            .put("action", action)
            .put("detail", detail)
    }
}
