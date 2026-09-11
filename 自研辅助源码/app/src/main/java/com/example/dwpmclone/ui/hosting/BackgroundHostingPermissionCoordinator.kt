package com.example.dwpmclone.ui.hosting

import android.Manifest
import android.app.Activity
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings

/** Starts only normal Android permission/settings flows after an explicit hosting action. */
class BackgroundHostingPermissionCoordinator(
    private val activity: Activity,
    /** Records which settings page opened, so a dead vendor deep link is visible. */
    private val outcomeSink: (String) -> Unit = {},
) {
    fun requestForStartedHosting() {
        activity.runOnUiThread {
            if (activity.isFinishing || activity.isDestroyed) return@runOnUiThread
            if (
                Build.VERSION.SDK_INT >= 33 &&
                activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
                PackageManager.PERMISSION_GRANTED
            ) {
                activity.requestPermissions(
                    arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                    REQUEST_NOTIFICATION_PERMISSION
                )
            } else {
                requestBatteryOptimizationExemption()
            }
        }
    }

    fun onRequestPermissionsResult(requestCode: Int): Boolean {
        if (requestCode != REQUEST_NOTIFICATION_PERMISSION) return false
        requestBatteryOptimizationExemption()
        return true
    }

    /** Opens only explicit, user-visible settings surfaces; no release build can self-grant them. */
    fun open(action: String): Boolean {
        val normalized = action.trim()
        if (normalized !in SUPPORTED_ACTIONS) return false
        activity.runOnUiThread {
            when (normalized) {
                "notification" -> openNotificationSettings()
                "battery-optimization" -> requestBatteryOptimizationExemption()
                "exact-alarm" -> openExactAlarmSettings()
                "vendor-battery" -> openVendorBatterySettings()
                "vendor-autostart" -> openVendorAutostartSettings()
                // Keep old action names accepted for already cached WebView pages.
                "xiaomi-battery" -> openVendorBatterySettings()
                "xiaomi-autostart" -> openVendorAutostartSettings()
                "app-details" -> openAppDetails()
                "wifi-settings" -> openWifiSettings()
            }
        }
        return true
    }

    private fun requestBatteryOptimizationExemption() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return
        val power = activity.getSystemService(PowerManager::class.java) ?: return
        if (power.isIgnoringBatteryOptimizations(activity.packageName)) return
        runCatching {
            activity.startActivity(
                Intent(
                    Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                    Uri.parse("package:${activity.packageName}")
                )
            )
        }
    }

    private fun openNotificationSettings() {
        if (
            Build.VERSION.SDK_INT >= 33 &&
            activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            activity.requestPermissions(
                arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                REQUEST_NOTIFICATION_PERMISSION,
            )
            return
        }
        launchFirst(
            Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                .putExtra(Settings.EXTRA_APP_PACKAGE, activity.packageName),
            appDetailsIntent(),
        )
    }

    private fun openExactAlarmSettings() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return
        launchFirst(
            Intent(
                Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                Uri.parse("package:${activity.packageName}"),
            ),
            appDetailsIntent(),
        )
    }

    private fun reportOutcome(action: String, opened: String?) {
        runCatching {
            outcomeSink(
                if (opened != null) {
                    "后台设置页已打开：$action → $opened"
                } else {
                    "后台设置页跳转失败：$action；本机系统未提供该入口，请按页面内的手动步骤设置"
                }
            )
        }
    }

    private fun openVendorBatterySettings() {
        val manufacturer = Build.MANUFACTURER.lowercase()
        val intents = mutableListOf<Intent>()
        when {
            manufacturer.contains("xiaomi") || manufacturer.contains("redmi") -> {
                intents += Intent().setComponent(ComponentName(
                    "com.miui.powerkeeper",
                    "com.miui.powerkeeper.ui.HiddenAppsConfigActivity",
                )).putExtra("package_name", activity.packageName)
                    .putExtra("package_label", activity.applicationInfo.loadLabel(activity.packageManager))
                intents += Intent("miui.intent.action.POWER_HIDE_MODE_APP_LIST")
                    .putExtra("package_name", activity.packageName)
            }
            manufacturer.contains("huawei") -> {
                intents += component("com.huawei.systemmanager", "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity")
                intents += component("com.huawei.systemmanager", "com.huawei.systemmanager.appcontrol.activity.StartupAppControlActivity")
            }
            manufacturer.contains("honor") -> {
                intents += component("com.hihonor.systemmanager", "com.hihonor.systemmanager.startupmgr.ui.StartupNormalAppListActivity")
                intents += component("com.hihonor.systemmanager", "com.hihonor.systemmanager.appcontrol.activity.StartupAppControlActivity")
            }
            manufacturer.contains("oppo") || manufacturer.contains("realme") || manufacturer.contains("oneplus") || manufacturer.contains("oplus") -> {
                intents += component("com.coloros.safecenter", "com.coloros.safecenter.startupapp.StartupAppListActivity")
                intents += component("com.oppo.safe", "com.oppo.safe.permission.startup.StartupAppListActivity")
            }
            manufacturer.contains("vivo") || manufacturer.contains("iqoo") -> {
                intents += component("com.vivo.permissionmanager", "com.vivo.permissionmanager.activity.BgStartUpManagerActivity")
                intents += component("com.vivo.permissionmanager", "com.vivo.permissionmanager.activity.PurviewTabActivity")
            }
            manufacturer.contains("meizu") -> {
                intents += component("com.meizu.safe", "com.meizu.safe.permission.SmartBGActivity")
            }
        }
        // The vendor page and the generic fallback are attempted separately so
        // the outcome distinguishes "opened the ROM's own switch" from "only
        // reached the AOSP page"; the latter still needs the manual steps.
        val opened = launchFirst(*intents.toTypedArray())
        reportOutcome("vendor-battery", opened)
        if (opened == null) {
            launchFirst(
                Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS),
                appDetailsIntent(),
            )
        }
    }

    /**
     * Where a timed Wi-Fi switch actually lives.
     *
     * On Xiaomi/Redmi, the sleep/timed-power-saving switch is exposed by the
     * powerkeeper scenario page.  It is tried before the generic Wi-Fi page so
     * the button lands on the setting named in the on-screen instructions.
     * Neither switch is readable by an app, so the written steps remain the
     * real guidance and the generic page is still the fallback.
     */
    private fun openWifiSettings() {
        val manufacturer = Build.MANUFACTURER.lowercase()
        val intents = mutableListOf<Intent>()
        if (manufacturer.contains("xiaomi") || manufacturer.contains("redmi")) {
            intents += component("com.miui.powerkeeper", "com.miui.powerkeeper.ui.ScenarioPowerSavingActivity")
            intents += component("com.miui.securitycenter", "com.miui.powercenter.PowerSettings")
        }
        intents += Intent(Settings.ACTION_WIFI_SETTINGS)
        intents += Intent(Settings.ACTION_WIRELESS_SETTINGS)
        val opened = launchFirst(*intents.toTypedArray())
        reportOutcome("wifi-settings", opened)
        if (opened == null) launchFirst(appDetailsIntent())
    }

    private fun openVendorAutostartSettings() {
        val manufacturer = Build.MANUFACTURER.lowercase()
        val intents = mutableListOf<Intent>()
        when {
            manufacturer.contains("xiaomi") || manufacturer.contains("redmi") ->
                intents += component("com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity")
            manufacturer.contains("huawei") -> {
                intents += component("com.huawei.systemmanager", "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity")
                intents += component("com.huawei.systemmanager", "com.huawei.systemmanager.appcontrol.activity.StartupAppControlActivity")
            }
            manufacturer.contains("honor") ->
                intents += component("com.hihonor.systemmanager", "com.hihonor.systemmanager.startupmgr.ui.StartupNormalAppListActivity")
            manufacturer.contains("oppo") || manufacturer.contains("realme") || manufacturer.contains("oneplus") || manufacturer.contains("oplus") -> {
                intents += component("com.coloros.safecenter", "com.coloros.safecenter.startupapp.StartupAppListActivity")
                intents += component("com.oppo.safe", "com.oppo.safe.permission.startup.StartupAppListActivity")
            }
            manufacturer.contains("vivo") || manufacturer.contains("iqoo") ->
                intents += component("com.vivo.permissionmanager", "com.vivo.permissionmanager.activity.BgStartUpManagerActivity")
            manufacturer.contains("meizu") ->
                intents += component("com.meizu.safe", "com.meizu.safe.permission.SmartBGActivity")
        }
        val opened = launchFirst(*intents.toTypedArray())
        reportOutcome("vendor-autostart", opened)
        if (opened == null) launchFirst(appDetailsIntent())
    }

    private fun component(packageName: String, className: String): Intent =
        Intent().setComponent(ComponentName(packageName, className))

    private fun openAppDetails() {
        launchFirst(appDetailsIntent())
    }

    private fun appDetailsIntent(): Intent = Intent(
        Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
        Uri.parse("package:${activity.packageName}"),
    )

    /**
     * Try each candidate page in order and report which one actually opened.
     *
     * Every deep link here is undocumented and may be renamed or hidden by
     * package visibility on any ROM update, so a total failure is an expected
     * outcome rather than a bug.  Returning it lets the caller record that the
     * user has to follow [VendorBackgroundGuidance] by hand instead of silently
     * leaving them on a page that never opened.
     */
    private fun launchFirst(vararg intents: Intent): String? {
        intents.forEach { intent ->
            val opened = runCatching {
                activity.startActivity(intent)
                true
            }.getOrDefault(false)
            if (opened) return intent.component?.flattenToShortString() ?: intent.action ?: "intent"
        }
        return null
    }

    private companion object {
        const val REQUEST_NOTIFICATION_PERMISSION = 7_301
        val SUPPORTED_ACTIONS = setOf(
            "notification",
            "battery-optimization",
            "exact-alarm",
            "vendor-battery",
            "vendor-autostart",
            "xiaomi-battery",
            "xiaomi-autostart",
            "app-details",
            "wifi-settings",
        )
    }
}
