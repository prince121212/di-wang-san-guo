package com.example.dwpmclone.domain.protocol

import org.json.JSONArray
import org.json.JSONObject

/** Durable hand-off between 0x8522 acceptance and the later 0x1600/0x8526 recall. */
data class MinePendingGarrison(
    val battleId: Long,
    val mineId: Long,
    val generalIds: List<Long>,
    val x: Int,
    val y: Int,
    val targetName: String,
    val dispatchAtMillis: Long,
    val marchSeconds: Int,
    val recallRequestedAtMillis: Long = 0L
) {
    fun toJson(): JSONObject = JSONObject()
        .put("battleId", battleId)
        .put("mineId", mineId)
        .put("generalIds", JSONArray(generalIds))
        .put("x", x)
        .put("y", y)
        .put("targetName", targetName)
        .put("dispatchAtMillis", dispatchAtMillis)
        .put("marchSeconds", marchSeconds)
        .put("recallRequestedAtMillis", recallRequestedAtMillis)

    companion object {
        fun fromJson(raw: String?): MinePendingGarrison? {
            val json = raw?.trim()?.takeIf { it.startsWith("{") }
                ?.let { runCatching { JSONObject(it) }.getOrNull() }
                ?: return null
            val battleId = json.optLong("battleId", 0L)
            val mineId = json.optLong("mineId", 0L)
            val ids = json.optJSONArray("generalIds")?.let { array ->
                (0 until array.length()).mapNotNull { array.optLong(it, 0L).takeIf { value -> value > 0L } }
            }.orEmpty().distinct()
            if (battleId <= 0L || mineId <= 0L || ids.isEmpty()) return null
            return MinePendingGarrison(
                battleId = battleId,
                mineId = mineId,
                generalIds = ids,
                x = json.optInt("x", 0),
                y = json.optInt("y", 0),
                targetName = json.optString("targetName"),
                dispatchAtMillis = json.optLong("dispatchAtMillis", 0L),
                marchSeconds = json.optInt("marchSeconds", 0),
                recallRequestedAtMillis = json.optLong("recallRequestedAtMillis", 0L)
            )
        }
    }
}
