package com.example.dwpmclone.ui.web

import com.example.dwpmclone.domain.localmap.LocalMapTargetRecord
import com.example.dwpmclone.domain.localmap.LocalTargetCache
import org.json.JSONArray
import org.json.JSONObject

/** Pure adapter from local protocol records to the shared map-page response contract. */
object LocalMapApiMapper {
    fun bandits(
        serverId: String,
        records: List<LocalMapTargetRecord>,
        nowMillis: Long,
        ttlMillis: Long = LocalTargetCache.DEFAULT_BANDIT_TTL_MILLIS
    ): JSONObject {
        val fresh = records.freshAt(nowMillis, ttlMillis)
        return JSONObject()
            .put("serverKey", serverId)
            .put("updatedAt", fresh.maxOfOrNull { it.lastValidatedAtMillis } ?: 0L)
            .put("ttlMs", ttlMillis)
            .put("points", JSONArray().apply {
                fresh.sortedWith(compareBy<LocalMapTargetRecord> { it.coordinate.y }.thenBy { it.coordinate.x })
                    .forEach { record -> put(record.toBanditJson()) }
            })
    }

    fun mines(
        serverId: String,
        records: List<LocalMapTargetRecord>,
        nowMillis: Long,
        ttlMillis: Long = LocalTargetCache.DEFAULT_MINE_TTL_MILLIS
    ): JSONObject {
        val fresh = records.freshAt(nowMillis, ttlMillis)
        return JSONObject()
            .put("serverKey", serverId)
            .put("updatedAt", fresh.maxOfOrNull { it.lastValidatedAtMillis } ?: 0L)
            .put("ttlMs", ttlMillis)
            .put("points", JSONArray().apply {
                fresh.sortedWith(compareBy<LocalMapTargetRecord> { it.coordinate.y }.thenBy { it.coordinate.x })
                    .forEach { record -> put(record.toMineJson(nowMillis, ttlMillis)) }
            })
    }

    private fun List<LocalMapTargetRecord>.freshAt(
        nowMillis: Long,
        ttlMillis: Long
    ): List<LocalMapTargetRecord> = filter { record ->
        val age = nowMillis - record.lastValidatedAtMillis
        record.active && record.lastValidatedAtMillis > 0L && age in 0L..ttlMillis
    }

    private fun LocalMapTargetRecord.toBanditJson(): JSONObject {
        val reward = fields("rewardDescription", "resource", "reward", "drop", "description")
        val composition = fields("compositionCode").ifBlank {
            listOf("foot", "bow", "cavalry", "chariot")
                .map { filterFields[it]?.toIntOrNull() }
                .takeIf { values -> values.all { it != null } }
                ?.joinToString("") { it.toString() }
                .orEmpty()
        }
        val categories = stringValues("dropCategories", "dropCategory")
            .ifEmpty { listOf("资源", "宝箱", "装备", "宝物").filter { it in reward } }
        val idHex = fields("idHex", "targetIdHex").ifBlank { targetId.toString(16).padStart(16, '0') }
        return JSONObject()
            .put("key", "id:$idHex")
            .put("id", targetId)
            .put("idHex", idHex)
            .put("name", fields("name", "kind").ifBlank { type })
            .put("level", level ?: fieldInt("level", "rank", "fz") ?: 0)
            .put("x", coordinate.x)
            .put("y", coordinate.y)
            .put("compositionCode", composition)
            .put("rewardDescription", reward)
            .put("dropCategories", JSONArray(categories))
            .put("lootIds", JSONArray(stringValues("lootIds", "lootId", "dropIds")))
            .put("firstDiscoveredAt", firstDiscoveredAtMillis)
            .put("updatedAt", lastValidatedAtMillis)
            .put("selectedForAttack", false)
            .put("status", "available")
    }

    private fun LocalMapTargetRecord.toMineJson(nowMillis: Long, ttlMillis: Long): JSONObject {
        val kind = fields("kind", "name").ifBlank { mineLabel(type) }
        val ownerName = fields("ownerName", "playerName", "owner", "lordName")
        val playerOccupied = fieldBoolean("playerOccupied", "occupiedByPlayer") ?: ownerName.isNotBlank()
        val defenderCount = fieldInt("defenseCount", "defenders", "guardCount") ?: 0
        val idHex = fields("idHex", "targetIdHex", "resourcePointIdHex")
            .ifBlank { targetId.toString(16).padStart(16, '0') }
        val expiresAt = lastValidatedAtMillis + ttlMillis
        return JSONObject()
            .put("key", "id:$idHex")
            .put("id", targetId)
            .put("idHex", idHex)
            .put("name", fields("name").ifBlank { kind })
            .put("kind", kind)
            .put("protocolKind", type)
            .put("businessId", fieldLong("businessId", "resourceId") ?: JSONObject.NULL)
            .put("typeCode", fields("typeCode", "kindCode"))
            .put("level", level ?: fieldInt("level", "rank", "fz") ?: 0)
            .put("x", coordinate.x)
            .put("y", coordinate.y)
            .put("ownerName", ownerName)
            .put("ownerCountry", fields("ownerCountry", "country"))
            .put("playerOccupied", playerOccupied)
            .put("unoccupiedByPlayer", !playerOccupied)
            .put("amountA", fieldLong("amountA", "reserve", "amount") ?: JSONObject.NULL)
            .put("amountB", fieldLong("amountB") ?: JSONObject.NULL)
            .put("description", fields("description", "detail"))
            .put("defenderCount", defenderCount)
            .put("hasDefenders", defenderCount > 0)
            .put("firstDiscoveredAt", firstDiscoveredAtMillis)
            .put("updatedAt", lastValidatedAtMillis)
            .put("expiresAt", expiresAt)
            .put("remainingMs", (expiresAt - nowMillis).coerceAtLeast(0L))
            .put("selectedForAttack", false)
            .put("status", "available")
    }

    private fun LocalMapTargetRecord.fields(vararg keys: String): String {
        keys.forEach { key -> filterFields[key]?.takeIf { it.isNotBlank() }?.let { return it } }
        return ""
    }

    private fun LocalMapTargetRecord.fieldInt(vararg keys: String): Int? =
        keys.firstNotNullOfOrNull { filterFields[it]?.toIntOrNull() }

    private fun LocalMapTargetRecord.fieldLong(vararg keys: String): Long? =
        keys.firstNotNullOfOrNull { filterFields[it]?.toLongOrNull() }

    private fun LocalMapTargetRecord.fieldBoolean(vararg keys: String): Boolean? =
        keys.firstNotNullOfOrNull { key ->
            when (filterFields[key]?.trim()?.lowercase()) {
                "1", "true", "yes", "y" -> true
                "0", "false", "no", "n" -> false
                else -> null
            }
        }

    private fun LocalMapTargetRecord.stringValues(vararg keys: String): List<String> {
        val raw = fields(*keys)
        if (raw.isBlank()) return emptyList()
        runCatching {
            val array = JSONArray(raw)
            return (0 until array.length()).mapNotNull { index ->
                array.optString(index).trim().takeIf { it.isNotBlank() }
            }.distinct()
        }
        return raw.split(Regex("[,，、;；|/\\s]+"))
            .map(String::trim)
            .filter(String::isNotBlank)
            .distinct()
    }

    private fun mineLabel(type: String): String = when (type) {
        "GOLD" -> "金矿"
        "SILVER" -> "银矿"
        "BING_YU" -> "冰玉矿"
        "XIAN_ZHI" -> "仙芝园"
        "XUAN_TIE" -> "玄铁矿"
        "YU_LU" -> "玉露园"
        "PASTURE_LV1" -> "一级牧场"
        "PASTURE_LV2" -> "二级牧场"
        "PASTURE_LV3" -> "三级牧场"
        "CRYSTAL" -> "水晶矿"
        "LING_CAO" -> "灵草园"
        "BIN_TIE" -> "镌铁矿"
        "JIANG_GUO" -> "浆果园"
        else -> type
    }
}
