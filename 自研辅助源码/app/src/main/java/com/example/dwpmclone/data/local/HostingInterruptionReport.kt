package com.example.dwpmclone.data.local

import org.json.JSONObject

/**
 * One process exit as the platform reported it, reduced to Android-free facts.
 *
 * [reasonCode] is an `android.app.ApplicationExitInfo.REASON_*` value.  Keeping
 * it an `Int` here is deliberate: attribution is the part that has to be right
 * on every vendor ROM, so it stays unit-testable without an Android runtime.
 */
data class ProcessExitRecord(
    val timestampMillis: Long,
    val reasonCode: Int,
    val description: String? = null,
    /**
     * Exit records cover every process of the package, including the WebView
     * sandbox renderer.  Those are reaped constantly and would otherwise
     * outrank the real hosting process and be misread as a vendor kill.
     */
    val processName: String? = null,
)

/**
 * Why on-device hosting stopped last time, and for how long.
 *
 * Cross-vendor distribution turns "it stopped working" into the only report a
 * user can give.  The durable heartbeat journal already knows *when* hosting
 * went quiet; [ProcessExitRecord] is the only public API that knows *why* the
 * process died.  Combining them is the difference between a bug report we can
 * act on and one we cannot.
 */
data class HostingInterruptionReport(
    val interrupted: Boolean,
    /** Wall-clock time hosting was down, when both ends of the gap are known. */
    val gapMillis: Long?,
    /** Stable key for logs and dashboards. */
    val attribution: String,
    val attributionText: String,
    /** True when the user can actually fix this in system settings. */
    val userActionable: Boolean,
    val exitReasonCode: Int?,
    val exitDescription: String?,
    val stopReason: String?,
) {
    fun summaryLine(): String {
        if (!interrupted) return "后台托管上次为正常停止或首次启动，无中断记录"
        val duration = gapMillis?.let { "中断约${formatDuration(it)}" } ?: "中断时长未知"
        val hint = if (userActionable) "；建议检查自启动与后台运行限制" else ""
        return "后台托管$duration：$attributionText$hint"
    }

    fun toJson(): JSONObject = JSONObject()
        .put("interrupted", interrupted)
        .put("gapMillis", gapMillis ?: JSONObject.NULL)
        .put("attribution", attribution)
        .put("attributionText", attributionText)
        .put("userActionable", userActionable)
        .put("exitReasonCode", exitReasonCode ?: JSONObject.NULL)
        .put("exitDescription", exitDescription ?: JSONObject.NULL)
        .put("stopReason", stopReason ?: JSONObject.NULL)
        .put("summary", summaryLine())

    companion object {
        // Verified against android-36 android.jar rather than transcribed from
        // documentation: a wrong code here would mis-blame the user's ROM.
        const val REASON_UNKNOWN = 0
        const val REASON_EXIT_SELF = 1
        const val REASON_SIGNALED = 2
        const val REASON_LOW_MEMORY = 3
        const val REASON_CRASH = 4
        const val REASON_CRASH_NATIVE = 5
        const val REASON_ANR = 6
        const val REASON_INITIALIZATION_FAILURE = 7
        const val REASON_PERMISSION_CHANGE = 8
        const val REASON_EXCESSIVE_RESOURCE_USAGE = 9
        const val REASON_USER_REQUESTED = 10
        const val REASON_USER_STOPPED = 11
        const val REASON_DEPENDENCY_DIED = 12
        const val REASON_OTHER = 13
        const val REASON_FREEZER = 14
        const val REASON_PACKAGE_STATE_CHANGE = 15
        const val REASON_PACKAGE_UPDATED = 16

        fun of(
            runtime: JSONObject,
            exits: List<ProcessExitRecord>,
            nowMillis: Long,
            /** Main process name; records for other processes are not evidence. */
            mainProcessName: String? = null,
            /** `PackageInfo.lastUpdateTime`, to recognise our own installs. */
            lastUpdateTimeMillis: Long? = null,
        ): HostingInterruptionReport {
            val interruptedAt = runtime.optLongOrNull("interruptedAtMillis")
            val previousHeartbeat = runtime.optLongOrNull("previousHeartbeatAtMillis")
            val stopReason = runtime.optStringOrNull("stopReason")
            if (interruptedAt == null) {
                return HostingInterruptionReport(
                    interrupted = false,
                    gapMillis = null,
                    attribution = "none",
                    attributionText = "无中断记录",
                    userActionable = false,
                    exitReasonCode = null,
                    exitDescription = null,
                    stopReason = stopReason,
                )
            }
            // Only an exit recorded after the last healthy heartbeat can explain
            // this interruption.  Without that guard a months-old force-stop
            // would be blamed for today's gap.
            val exit = exits
                .filter { it.timestampMillis <= nowMillis }
                .filter { previousHeartbeat == null || it.timestampMillis >= previousHeartbeat }
                // The WebView renderer dies far more often than the host, so an
                // unfiltered "newest record" reliably blames the wrong process.
                .filter {
                    mainProcessName == null || it.processName == null ||
                        it.processName == mainProcessName
                }
                .maxByOrNull { it.timestampMillis }
            val gap = if (previousHeartbeat != null && interruptedAt >= previousHeartbeat) {
                interruptedAt - previousHeartbeat
            } else {
                null
            }
            val attribution = when {
                // Our own install force-stops the app, which the platform reports
                // as USER_REQUESTED.  Blaming the ROM for it would train users to
                // hunt for a setting that was never the problem.
                exit != null && isOurOwnUpdate(exit, lastUpdateTimeMillis) ->
                    attribute(REASON_PACKAGE_UPDATED)
                exit != null -> attribute(exit.reasonCode)
                else -> fallbackAttribution(stopReason)
            }
            return HostingInterruptionReport(
                interrupted = true,
                gapMillis = gap,
                attribution = attribution.key,
                attributionText = attribution.text,
                userActionable = attribution.userActionable,
                exitReasonCode = exit?.reasonCode,
                exitDescription = exit?.description,
                stopReason = stopReason,
            )
        }

        /**
         * True when this exit is explained by our own install rather than by the
         * device.  Matched on the update timestamp instead of the description
         * text, which is free-form and vendor-specific.
         */
        private fun isOurOwnUpdate(
            exit: ProcessExitRecord,
            lastUpdateTimeMillis: Long?,
        ): Boolean {
            if (lastUpdateTimeMillis == null || lastUpdateTimeMillis <= 0L) return false
            return kotlin.math.abs(exit.timestampMillis - lastUpdateTimeMillis) <=
                UPDATE_MATCH_WINDOW_MILLIS
        }

        private const val UPDATE_MATCH_WINDOW_MILLIS = 60_000L

        private data class Attribution(
            val key: String,
            val text: String,
            val userActionable: Boolean,
        )

        private fun attribute(reasonCode: Int): Attribution = when (reasonCode) {
            REASON_SIGNALED -> Attribution(
                "system-killed",
                "进程被系统信号终止，常见于厂商后台清理",
                true,
            )
            REASON_OTHER -> Attribution(
                "system-killed",
                "被系统或厂商后台策略结束（Android 未给出细分原因）",
                true,
            )
            REASON_FREEZER -> Attribution("freezer", "进程被系统冻结后回收", true)
            REASON_LOW_MEMORY -> Attribution("low-memory", "系统内存不足回收了进程", true)
            REASON_EXCESSIVE_RESOURCE_USAGE -> Attribution(
                "resource-usage",
                "系统判定本应用后台资源占用过高",
                true,
            )
            REASON_PERMISSION_CHANGE -> Attribution(
                "permission-change",
                "权限变更导致进程重启",
                true,
            )
            REASON_USER_REQUESTED -> Attribution(
                "user",
                "用户主动结束（划掉任务卡或强行停止）",
                false,
            )
            REASON_USER_STOPPED -> Attribution("user", "用户在系统设置中停止了应用", false)
            REASON_EXIT_SELF -> Attribution("self", "应用自身正常退出", false)
            REASON_PACKAGE_UPDATED -> Attribution("package-updated", "应用更新后重启", false)
            REASON_PACKAGE_STATE_CHANGE -> Attribution(
                "package-updated",
                "应用安装状态变更后重启",
                false,
            )
            REASON_CRASH -> Attribution("crash", "应用崩溃（需要开发定位）", false)
            REASON_CRASH_NATIVE -> Attribution(
                "crash",
                "native 层崩溃（需要开发定位）",
                false,
            )
            REASON_ANR -> Attribution("anr", "应用无响应被系统终止（需要开发定位）", false)
            REASON_INITIALIZATION_FAILURE -> Attribution(
                "init-failure",
                "应用初始化失败（需要开发定位）",
                false,
            )
            REASON_DEPENDENCY_DIED -> Attribution("dependency", "依赖的进程退出", false)
            REASON_UNKNOWN -> Attribution("unknown", "系统未提供退出原因", false)
            else -> Attribution("unknown", "未识别的退出原因（code=$reasonCode）", false)
        }

        /**
         * No usable exit record.  A recorded stop reason still separates our own
         * orderly shutdown from a silent kill, so it must not be reported as an
         * unexplained system kill.
         */
        private fun fallbackAttribution(stopReason: String?): Attribution =
            if (stopReason.isNullOrBlank()) {
                Attribution("unknown", "系统未提供退出原因，且没有本地停止记录", false)
            } else {
                Attribution("recorded-stop", "本地记录的停止原因：$stopReason", false)
            }

        private fun formatDuration(millis: Long): String {
            val totalSeconds = millis / 1_000L
            val hours = totalSeconds / 3_600L
            val minutes = (totalSeconds % 3_600L) / 60L
            val seconds = totalSeconds % 60L
            return when {
                hours > 0 -> "${hours}小时${minutes}分"
                minutes > 0 -> "${minutes}分${seconds}秒"
                else -> "${seconds}秒"
            }
        }

        private fun JSONObject.optLongOrNull(key: String): Long? =
            if (has(key) && !isNull(key)) getLong(key) else null

        private fun JSONObject.optStringOrNull(key: String): String? =
            if (has(key) && !isNull(key)) getString(key).takeIf { it.isNotBlank() } else null
    }
}
