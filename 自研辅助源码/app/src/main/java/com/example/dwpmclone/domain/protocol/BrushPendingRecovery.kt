package com.example.dwpmclone.domain.protocol

import org.json.JSONArray
import org.json.JSONObject

/** Durable post-return maintenance marker written before a brush expedition is sent. */
data class BrushPendingRecovery(
    val generalIds: List<Long>,
    val formationId: Long,
    val targetId: Long,
    val targetX: Int,
    val targetY: Int,
    val createdAtMillis: Long,
    val sendState: String
) {
    fun toJson(): JSONObject = JSONObject()
        .put("generalIds", JSONArray(generalIds))
        .put("formationId", formationId)
        .put("targetId", targetId)
        .put("targetX", targetX)
        .put("targetY", targetY)
        .put("createdAtMillis", createdAtMillis)
        .put("sendState", sendState)

    companion object {
        const val SESSION_KEY = "brushPendingRecoveryJson"

        fun fromJson(raw: String?): BrushPendingRecovery? {
            val json = raw?.trim()?.takeIf { it.startsWith("{") }
                ?.let { runCatching { JSONObject(it) }.getOrNull() }
                ?: return null
            val generalIds = json.optJSONArray("generalIds")?.let { array ->
                (0 until array.length())
                    .mapNotNull { array.optLong(it, 0L).takeIf { id -> id > 0L } }
                    .distinct()
            }.orEmpty()
            val formationId = json.optLong("formationId", 0L)
            val targetId = json.optLong("targetId", 0L)
            val createdAtMillis = json.optLong("createdAtMillis", 0L)
            val sendState = json.optString("sendState").trim()
            if (
                generalIds.isEmpty() || formationId <= 0L || targetId <= 0L ||
                createdAtMillis <= 0L || sendState !in setOf("sending", "accepted", "uncertain")
            ) return null
            return BrushPendingRecovery(
                generalIds = generalIds,
                formationId = formationId,
                targetId = targetId,
                targetX = json.optInt("targetX"),
                targetY = json.optInt("targetY"),
                createdAtMillis = createdAtMillis,
                sendState = sendState
            )
        }
    }
}
