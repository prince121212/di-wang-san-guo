package com.example.dwpmclone.ui.hosting

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings

/** Starts only normal Android permission/settings flows after an explicit hosting action. */
class BackgroundHostingPermissionCoordinator(private val activity: Activity) {
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

    private companion object {
        const val REQUEST_NOTIFICATION_PERMISSION = 7_301
    }
}
