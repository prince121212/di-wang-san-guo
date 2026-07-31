package com.example.dwpmclone.domain.protocol

import org.json.JSONArray
import org.json.JSONObject

/** Durable context for a launched dungeon battle that still needs polling or a chest. */
data class DungeonPendingRun(
    val generalIds: List<Long>,
    val chapter: Int,
    val stage: Int,
    val chestPosition: Int,
    val mode: String,
    val launchedAtMillis: Long,
    val battleId: Long? = null,
    /** Persisted before catalog confirmation so a restart never opens the same chest twice. */
    val chestOpened: Boolean = false,
    /** True when the durable expedition ledger reconstructed metadata lost by an old login flow. */
    val recoveredFromTransaction: Boolean = false
) {
    fun toJson(): JSONObject = JSONObject()
        .put("generalIds", JSONArray(generalIds))
        .put("chapter", chapter)
        .put("stage", stage)
        .put("chestPosition", chestPosition)
        .put("mode", mode)
        .put("launchedAtMillis", launchedAtMillis)
        .put("battleId", battleId ?: JSONObject.NULL)
        .put("chestOpened", chestOpened)
        .put("recoveredFromTransaction", recoveredFromTransaction)

    companion object {
        fun fromJson(raw: String?): DungeonPendingRun? {
            val json = raw?.trim()?.takeIf { it.startsWith("{") }
                ?.let { runCatching { JSONObject(it) }.getOrNull() }
                ?: return null
            val ids = json.optJSONArray("generalIds")?.let { array ->
                (0 until array.length())
                    .mapNotNull { array.optLong(it, 0L).takeIf { value -> value > 0L } }
            }.orEmpty().distinct()
            val chapter = json.optInt("chapter", -1)
            val stage = json.optInt("stage", 0)
            val chestPosition = json.optInt("chestPosition", -1)
            val mode = json.optString("mode").trim()
            val launchedAtMillis = json.optLong("launchedAtMillis", 0L)
            if (
                ids.isEmpty() || chapter < 0 || stage <= 0 || chestPosition !in 0..2 ||
                mode !in setOf("loop", "clear") || launchedAtMillis <= 0L
            ) {
                return null
            }
            return DungeonPendingRun(
                generalIds = ids,
                chapter = chapter,
                stage = stage,
                chestPosition = chestPosition,
                mode = mode,
                launchedAtMillis = launchedAtMillis,
                battleId = json.optLong("battleId", 0L).takeIf { it > 0L },
                chestOpened = json.optBoolean("chestOpened", false),
                recoveredFromTransaction = json.optBoolean("recoveredFromTransaction", false)
            )
        }
    }
}
