package com.example.dwpmclone.ui.web

import org.json.JSONObject

internal data class ResidentDailyCounts(
    val brushYellowCount: Int,
    val dungeonCount: Int,
)

/** Projects Python-owned resident counters without recreating scheduler rules in Kotlin. */
internal object SharedResidentDailyCountProjection {
    private const val SCHEMA_VERSION = 2
    private const val DAY_MILLIS = 24L * 60L * 60L * 1_000L
    private const val CHINA_OFFSET_MILLIS = 8L * 60L * 60L * 1_000L

    fun project(
        residentDailyCountsJson: String? = null,
        residentConfigJson: String?,
        residentStateJson: String?,
        fallbackBrushYellowCount: Int,
        fallbackDungeonCount: Int,
        nowMillis: Long,
    ): ResidentDailyCounts {
        val currentDay = (nowMillis + CHINA_OFFSET_MILLIS) / DAY_MILLIS
        val compact = jsonObject(residentDailyCountsJson)
        if (compact.optInt("schemaVersion", 0) >= 1) {
            return ResidentDailyCounts(
                brushYellowCount = count(compact, "brush", currentDay),
                dungeonCount = count(compact, "dungeon", currentDay),
            )
        }
        val config = jsonObject(residentConfigJson)
        if (config.optInt("schemaVersion", 0) < SCHEMA_VERSION) {
            return ResidentDailyCounts(
                brushYellowCount = fallbackBrushYellowCount.coerceAtLeast(0),
                dungeonCount = fallbackDungeonCount.coerceAtLeast(0),
            )
        }
        val state = jsonObject(residentStateJson)
        return ResidentDailyCounts(
            brushYellowCount = count(state, "brush", currentDay),
            dungeonCount = count(state, "dungeon", currentDay),
        )
    }

    private fun count(state: JSONObject, feature: String, currentDay: Long): Int {
        val featureState = state.optJSONObject(feature) ?: return 0
        if (featureState.optLong("dayKey", -1L) != currentDay) return 0
        return featureState.optInt("usedCount", 0).coerceAtLeast(0)
    }

    private fun jsonObject(raw: String?): JSONObject = raw
        ?.trim()
        ?.takeIf { it.startsWith("{") }
        ?.let { runCatching { JSONObject(it) }.getOrNull() }
        ?: JSONObject()
}
