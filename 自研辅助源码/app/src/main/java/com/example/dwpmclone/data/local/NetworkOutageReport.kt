package com.example.dwpmclone.data.local

import org.json.JSONArray
import org.json.JSONObject

/**
 * One stretch during which hosting was running but had no usable network.
 *
 * Recorded by the foreground service, so the window itself already proves the
 * app was alive: a killed process records nothing.  The two observed flags say
 * whether *this* device saw each boundary happen, or only inherited the state
 * at process start - which is the difference between "the network went away at
 * 23:10" and "the network was already away when we looked".
 */
data class NetworkOutageWindow(
    val startAtMillis: Long,
    val endAtMillis: Long,
    val startObserved: Boolean = true,
    val endObserved: Boolean = true,
) {
    val durationMillis: Long get() = (endAtMillis - startAtMillis).coerceAtLeast(0L)

    fun toJson(): JSONObject = JSONObject()
        .put("startAtMillis", startAtMillis)
        .put("endAtMillis", endAtMillis)
        .put("startObserved", startObserved)
        .put("endObserved", endObserved)

    companion object {
        fun fromJson(value: JSONObject): NetworkOutageWindow? {
            val start = value.optLong("startAtMillis", 0L)
            val end = value.optLong("endAtMillis", 0L)
            if (start <= 0L || end < start) return null
            return NetworkOutageWindow(
                startAtMillis = start,
                endAtMillis = end,
                startObserved = value.optBoolean("startObserved", true),
                endObserved = value.optBoolean("endObserved", true),
            )
        }
    }
}

/**
 * A network blackout that repeats on the clock - i.e. somebody scheduled it.
 *
 * This is a *diagnosis*, not a measurement, so the bar for claiming it is
 * deliberately high (see [ScheduledNetworkOutageDetector]).  Telling a user to
 * go hunting through vendor settings when their router merely rebooted twice
 * would be worse than saying nothing.
 */
data class ScheduledNetworkOutage(
    val occurrences: Int,
    val observedDays: Int,
    val startMinuteOfDay: Int,
    val endMinuteOfDay: Int,
    val durationMinutes: Int,
    val lastStartAtMillis: Long,
    val lastEndAtMillis: Long,
) {
    val startClock: String get() = clockText(startMinuteOfDay)
    val endClock: String get() = clockText(endMinuteOfDay)

    /** The one sentence that has to make the cause obvious. */
    fun summaryLine(): String =
        "历史记录显示不同日期约 $startClock 断网、约 $endClock 恢复（${observedDays}个日期出现${occurrences}次，" +
            "每次约${durationText(durationMinutes)}）。这段时间托管仍在运行，" +
            "但手机没有可用网络，所以无法出征；这与睡眠模式或其他定时断网任务相符，不能单凭记录断定具体开关。"

    fun toJson(): JSONObject = JSONObject()
        .put("detected", true)
        .put("occurrences", occurrences)
        .put("observedDays", observedDays)
        .put("startMinuteOfDay", startMinuteOfDay)
        .put("endMinuteOfDay", endMinuteOfDay)
        .put("startClock", startClock)
        .put("endClock", endClock)
        .put("durationMinutes", durationMinutes)
        .put("durationText", durationText(durationMinutes))
        .put("lastStartAtMillis", lastStartAtMillis)
        .put("lastEndAtMillis", lastEndAtMillis)
        .put("summary", summaryLine())

    companion object {
        fun clockText(minuteOfDay: Int): String {
            val normalized = ((minuteOfDay % 1440) + 1440) % 1440
            return "%02d:%02d".format(normalized / 60, normalized % 60)
        }

        fun durationText(minutes: Int): String {
            if (minutes < 60) return "${minutes}分钟"
            val hours = minutes / 60.0
            return "%.1f小时".format(hours)
        }
    }
}

/**
 * Decides whether recorded outages form a schedule rather than bad luck.
 *
 * Vendor "sleep mode"/timed Wi-Fi switches are invisible to apps: there is no
 * API to read them, and the only public evidence is the shape of the outage
 * itself.  What separates a schedule from ordinary flakiness is that *both*
 * ends land at the same clock time on different days - a router reboot or a
 * roaming drop has neither a consistent start nor a consistent end.
 *
 * Pure by design: this is the claim the settings page makes to the user, so it
 * stays unit-testable with no Android runtime.
 */
object ScheduledNetworkOutageDetector {
    /** Shorter blackouts are ordinary connectivity noise, not a schedule. */
    const val LONG_OUTAGE_MINUTES = 45

    /** How far two occurrences may drift and still count as "the same time". */
    const val CLOCK_TOLERANCE_MINUTES = 75

    /** One long outage is an incident; a repeat on another day is a pattern. */
    const val MIN_OCCURRENCES = 2

    const val LOOKBACK_DAYS = 14

    fun needsReview(schedule: ScheduledNetworkOutage?, acknowledgedThroughMillis: Long): Boolean =
        schedule != null && schedule.lastEndAtMillis > acknowledgedThroughMillis

    private const val DAY_MILLIS = 86_400_000L
    private const val MINUTE_MILLIS = 60_000L

    fun detect(
        windows: List<NetworkOutageWindow>,
        nowMillis: Long,
        zoneOffsetMillis: Long,
    ): ScheduledNetworkOutage? {
        val since = nowMillis - LOOKBACK_DAYS * DAY_MILLIS
        val candidates = windows.filter {
            // Both boundaries must have been observed by a live process.  An
            // inferred boundary carries the process restart time, not the time
            // the network actually changed, and would invent a "schedule" out
            // of when the user happened to reopen the app.
            it.startObserved && it.endObserved &&
                it.startAtMillis >= since &&
                it.durationMillis >= LONG_OUTAGE_MINUTES * MINUTE_MILLIS
        }
        if (candidates.size < MIN_OCCURRENCES) return null

        var best: List<NetworkOutageWindow> = emptyList()
        var bestAnchor: NetworkOutageWindow? = null
        candidates.forEach { anchor ->
            val anchorStart = minuteOfDay(anchor.startAtMillis, zoneOffsetMillis)
            val anchorEnd = minuteOfDay(anchor.endAtMillis, zoneOffsetMillis)
            val group = candidates.filter {
                circularDistance(minuteOfDay(it.startAtMillis, zoneOffsetMillis), anchorStart) <=
                    CLOCK_TOLERANCE_MINUTES &&
                    circularDistance(minuteOfDay(it.endAtMillis, zoneOffsetMillis), anchorEnd) <=
                    CLOCK_TOLERANCE_MINUTES
            }
            if (group.size > best.size) {
                best = group
                bestAnchor = anchor
            }
        }
        val anchor = bestAnchor ?: return null
        if (best.size < MIN_OCCURRENCES) return null
        // Two blackouts inside one night are one incident, not a daily habit.
        val days = best.map { localDay(it.startAtMillis, zoneOffsetMillis) }.distinct()
        if (days.size < MIN_OCCURRENCES) return null

        val anchorStart = minuteOfDay(anchor.startAtMillis, zoneOffsetMillis)
        val anchorEnd = minuteOfDay(anchor.endAtMillis, zoneOffsetMillis)
        return ScheduledNetworkOutage(
            occurrences = best.size,
            observedDays = days.size,
            // Medians are taken relative to the anchor so a group straddling
            // midnight does not average to the middle of the afternoon.
            startMinuteOfDay = normalizeMinute(
                anchorStart + median(
                    best.map { signedOffset(minuteOfDay(it.startAtMillis, zoneOffsetMillis), anchorStart) }
                )
            ),
            endMinuteOfDay = normalizeMinute(
                anchorEnd + median(
                    best.map { signedOffset(minuteOfDay(it.endAtMillis, zoneOffsetMillis), anchorEnd) }
                )
            ),
            durationMinutes = median(best.map { (it.durationMillis / MINUTE_MILLIS).toInt() }),
            lastStartAtMillis = best.maxOf { it.startAtMillis },
            lastEndAtMillis = best.maxOf { it.endAtMillis },
        )
    }

    fun minuteOfDay(atMillis: Long, zoneOffsetMillis: Long): Int =
        (((atMillis + zoneOffsetMillis) % DAY_MILLIS + DAY_MILLIS) % DAY_MILLIS / MINUTE_MILLIS).toInt()

    private fun localDay(atMillis: Long, zoneOffsetMillis: Long): Long =
        Math.floorDiv(atMillis + zoneOffsetMillis, DAY_MILLIS)

    private fun circularDistance(a: Int, b: Int): Int {
        val raw = Math.abs(a - b)
        return minOf(raw, 1440 - raw)
    }

    private fun signedOffset(value: Int, anchor: Int): Int {
        var delta = value - anchor
        if (delta > 720) delta -= 1440
        if (delta < -720) delta += 1440
        return delta
    }

    private fun normalizeMinute(value: Int): Int = ((value % 1440) + 1440) % 1440

    private fun median(values: List<Int>): Int {
        if (values.isEmpty()) return 0
        val sorted = values.sorted()
        val middle = sorted.size / 2
        return if (sorted.size % 2 == 1) {
            sorted[middle]
        } else {
            (sorted[middle - 1] + sorted[middle]) / 2
        }
    }
}

/** What the settings page shows about network availability. */
data class NetworkAvailabilityReport(
    val schedule: ScheduledNetworkOutage?,
    val recentWindows: List<NetworkOutageWindow>,
    val ongoingSinceMillis: Long?,
    val currentNetworkUsable: Boolean? = null,
    val scheduleNeedsReview: Boolean = schedule != null,
    val scheduleAcknowledgedThroughMillis: Long? = null,
) {
    fun toJson(): JSONObject = JSONObject()
        .put(
            "scheduledOutage",
            schedule?.toJson() ?: JSONObject().put("detected", false),
        )
        .put("ongoingSinceMillis", ongoingSinceMillis ?: JSONObject.NULL)
        .put("currentNetworkUsable", currentNetworkUsable ?: JSONObject.NULL)
        .put("scheduleNeedsReview", scheduleNeedsReview)
        .put("scheduleReviewState", when {
            schedule == null -> "none"
            scheduleNeedsReview -> "needs-review"
            else -> "acknowledged"
        })
        .put("scheduleAcknowledgedThroughMillis", scheduleAcknowledgedThroughMillis ?: JSONObject.NULL)
        .put("recentWindows", JSONArray().apply {
            recentWindows.takeLast(12).forEach { put(it.toJson()) }
        })
}
