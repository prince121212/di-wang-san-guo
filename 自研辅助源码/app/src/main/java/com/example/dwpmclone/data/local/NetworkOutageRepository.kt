package com.example.dwpmclone.data.local

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * Durable journal of "hosting was up, the phone had no network".
 *
 * Kept separate from the task log because it must survive the log's rotation
 * and be answerable in one read: the diagnosis it feeds needs days of history,
 * while the log is a scrolling window the user also clears by hand.
 *
 * An open outage deliberately survives process death.  A vendor kill in the
 * middle of a nightly blackout is exactly the case worth reporting, and
 * re-opening the window on restart would cut it into unrecognisable pieces.
 */
class NetworkOutageRepository(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences(
        PREFS,
        Context.MODE_PRIVATE,
    )

    /**
     * Record that the network became unusable.
     *
     * @param transitionObserved true when this process saw the previous state;
     *   false when it only found the network already gone at start-up.
     */
    @Synchronized
    fun noteUnusable(nowMillis: Long, transitionObserved: Boolean) {
        if (preferences.getLong(KEY_OPEN_START, 0L) > 0L) return
        preferences.edit()
            .putLong(KEY_OPEN_START, nowMillis)
            .putBoolean(KEY_OPEN_START_OBSERVED, transitionObserved)
            .apply()
    }

    /** Close the open outage, dropping blips too short to mean anything. */
    @Synchronized
    fun noteUsable(nowMillis: Long, transitionObserved: Boolean): NetworkOutageWindow? {
        val start = preferences.getLong(KEY_OPEN_START, 0L)
        if (start <= 0L) return null
        val startObserved = preferences.getBoolean(KEY_OPEN_START_OBSERVED, true)
        val editor = preferences.edit()
            .remove(KEY_OPEN_START)
            .remove(KEY_OPEN_START_OBSERVED)
        if (nowMillis - start < MIN_RECORDED_MILLIS) {
            editor.apply()
            return null
        }
        val window = NetworkOutageWindow(
            startAtMillis = start,
            endAtMillis = nowMillis,
            startObserved = startObserved,
            endObserved = transitionObserved,
        )
        val windows = (readWindows() + window).takeLast(MAX_WINDOWS)
        editor
            .putString(KEY_WINDOWS, JSONArray().apply { windows.forEach { put(it.toJson()) } }.toString())
            .apply()
        return window
    }

    @Synchronized
    fun report(
        nowMillis: Long,
        zoneOffsetMillis: Long,
        currentNetworkUsable: Boolean? = null,
    ): NetworkAvailabilityReport {
        val windows = readWindows()
        val open = preferences.getLong(KEY_OPEN_START, 0L).takeIf { it > 0L }
        val acknowledgedThrough = preferences.getLong(KEY_ACKNOWLEDGED_THROUGH, 0L)
        val schedule = ScheduledNetworkOutageDetector.detect(windows, nowMillis, zoneOffsetMillis)
        return NetworkAvailabilityReport(
            schedule = schedule,
            recentWindows = windows,
            ongoingSinceMillis = open,
            currentNetworkUsable = currentNetworkUsable,
            scheduleNeedsReview = ScheduledNetworkOutageDetector.needsReview(
                schedule,
                acknowledgedThrough,
            ),
            scheduleAcknowledgedThroughMillis = acknowledgedThrough.takeIf { it > 0L },
        )
    }

    /**
     * A schedule is historical evidence, not a readable OEM switch state.
     * Persist the exact last completed window the user saw as handled; a later
     * matching blackout will then produce a new review prompt.
     */
    @Synchronized
    fun acknowledgeSchedule(
        evidenceThroughMillis: Long,
        nowMillis: Long,
        zoneOffsetMillis: Long,
    ): Boolean {
        if (evidenceThroughMillis <= 0L) return false
        val schedule = ScheduledNetworkOutageDetector.detect(
            readWindows(), nowMillis, zoneOffsetMillis,
        ) ?: return false
        if (schedule.lastEndAtMillis != evidenceThroughMillis) return false
        return preferences.edit()
            .putLong(KEY_ACKNOWLEDGED_THROUGH, evidenceThroughMillis)
            .putLong(KEY_ACKNOWLEDGED_AT, nowMillis)
            .commit()
    }

    private fun readWindows(): List<NetworkOutageWindow> {
        val raw = preferences.getString(KEY_WINDOWS, null) ?: return emptyList()
        val array = runCatching { JSONArray(raw) }.getOrNull() ?: return emptyList()
        return (0 until array.length()).mapNotNull { index ->
            array.optJSONObject(index)?.let { NetworkOutageWindow.fromJson(it) }
        }
    }

    private companion object {
        const val PREFS = "dwpm_network_outages"
        const val KEY_WINDOWS = "windows"
        const val KEY_OPEN_START = "open_start_at"
        const val KEY_OPEN_START_OBSERVED = "open_start_observed"
        const val KEY_ACKNOWLEDGED_THROUGH = "schedule_acknowledged_through"
        const val KEY_ACKNOWLEDGED_AT = "schedule_acknowledged_at"

        /** Roaming and cell/Wi-Fi handovers produce sub-minute gaps constantly. */
        const val MIN_RECORDED_MILLIS = 120_000L

        /** Two weeks of nightly windows plus room for daytime noise. */
        const val MAX_WINDOWS = 60
    }
}
