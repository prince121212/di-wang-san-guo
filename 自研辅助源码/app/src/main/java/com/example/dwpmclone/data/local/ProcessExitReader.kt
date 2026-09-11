package com.example.dwpmclone.data.local

import android.app.ActivityManager
import android.content.Context
import android.os.Build

/**
 * Reads the platform's own record of why this app's processes died.
 *
 * Deliberately thin: every decision lives in [HostingInterruptionReport] so it
 * can be tested without an Android runtime.  Available from API 30; older
 * devices simply get no attribution and fall back to the heartbeat journal.
 */
object ProcessExitReader {
    /**
     * The limit is generous on purpose.  Records cover every process of the
     * package and the WebView sandbox renderer churns far faster than the host,
     * so a small window can contain no host record at all.
     */
    fun read(context: Context, limit: Int = DEFAULT_LIMIT): List<ProcessExitRecord> {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return emptyList()
        val manager = context.getSystemService(ActivityManager::class.java)
            ?: return emptyList()
        return runCatching {
            manager.getHistoricalProcessExitReasons(context.packageName, 0, limit)
                .map { info ->
                    ProcessExitRecord(
                        timestampMillis = info.timestamp,
                        reasonCode = info.reason,
                        description = info.description,
                        processName = info.processName,
                    )
                }
        }.getOrDefault(emptyList())
    }

    /** `PackageInfo.lastUpdateTime`, used to recognise our own installs. */
    fun lastUpdateTimeMillis(context: Context): Long? = runCatching {
        context.packageManager
            .getPackageInfo(context.packageName, 0)
            .lastUpdateTime
    }.getOrNull()

    private const val DEFAULT_LIMIT = 15
}
