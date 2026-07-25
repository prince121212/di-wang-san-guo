package com.example.dwpmclone.ui.assistant

import org.json.JSONArray
import org.json.JSONObject

data class MilitaryIntelDisplay(
    val events: List<MilitaryIntelEvent>,
    val updatedAtMillis: Long?,
    val source: String
)

data class MilitaryIntelEvent(
    val timeText: String?,
    val text: String,
    val state: String?,
    val national: Boolean
)

enum class MilitaryIntelTab { MILITARY, NATION }

/**
 * The current computer UI calls the same renderJunqing() function for both side tabs.
 * Keep this policy explicit so the Android “国家” tab cannot silently become a narrower,
 * keyword-filtered feature that differs from the authoritative computer front end.
 */
object MilitaryIntelTabPolicy {
    fun visibleEvents(
        display: MilitaryIntelDisplay,
        @Suppress("UNUSED_PARAMETER") tab: MilitaryIntelTab
    ): List<MilitaryIntelEvent> = display.events
}

/**
 * Maps the same `militaryIntel` shape used by the computer front end. If no 0xa110 feed
 * has been persisted yet, busy general states are used as the same fallback as app.js.
 */
object MilitaryIntelDisplayMapper {
    fun map(channelExtra: Map<String, String>): MilitaryIntelDisplay {
        val intel = firstJson(
            channelExtra["militaryIntelJson"],
            channelExtra["militaryIntel"]
        )
        val explicitEvents = intel?.optJSONArray("events").toEvents()
        if (explicitEvents.isNotEmpty()) {
            return MilitaryIntelDisplay(
                events = explicitEvents,
                updatedAtMillis = intel?.optLong("updatedAt")?.takeIf { it > 0L },
                source = intel?.optString("sourceOpcode").orEmpty().ifBlank { "0x3110/0xa110" }
            )
        }

        val statusByName = intel?.optJSONObject("statusByName").toStringMap()
        val generals = firstArray(channelExtra["generalsJson"], channelExtra["jiangLingData"])
        val busy = buildList {
            if (generals != null) {
                for (index in 0 until generals.length()) {
                    val general = generals.optJSONObject(index) ?: continue
                    val name = general.optString("name").ifBlank {
                        general.optString("id").ifBlank { "未知将领" }
                    }
                    val state = normalizeStatus(
                        statusByName[name]
                            ?: general.optString("displayStatus")
                                .ifBlank { general.optString("statusText") }
                                .ifBlank { general.optString("status") }
                    )
                    if (state == "闲") continue
                    val troopType = general.optString("soldierType")
                        .ifBlank { general.optString("troopType") }
                    val troopCount = general.optString("soldierCount")
                        .ifBlank { general.optString("troopCount") }
                    add(
                        MilitaryIntelEvent(
                            timeText = null,
                            text = buildString {
                                append("【$state】$name")
                                if (troopType.isNotBlank()) append("，$troopType")
                                if (troopCount.isNotBlank()) append(" $troopCount")
                            },
                            state = state,
                            national = false
                        )
                    )
                }
            }
        }
        return MilitaryIntelDisplay(
            events = busy,
            updatedAtMillis = intel?.optLong("updatedAt")?.takeIf { it > 0L },
            source = if (intel == null) "将领实时状态" else intel.optString("sourceOpcode", "0x3110/0xa110")
        )
    }

    private fun JSONArray?.toEvents(): List<MilitaryIntelEvent> = buildList {
        val source = this@toEvents ?: return@buildList
        for (index in 0 until source.length()) {
            val event = source.optJSONObject(index) ?: continue
            val text = event.optString("text").trim()
            if (text.isBlank()) continue
            add(
                MilitaryIntelEvent(
                    timeText = event.optString("timeText")
                        .ifBlank { event.optString("time") }
                        .takeIf { it.isNotBlank() },
                    text = text,
                    state = event.optString("state").takeIf { it.isNotBlank() },
                    national = event.optBoolean("national", false) ||
                        text.contains("国家") ||
                        text.contains("国战") ||
                        text.contains("国都")
                )
            )
        }
    }

    private fun firstJson(vararg values: String?): JSONObject? =
        values.firstNotNullOfOrNull { value ->
            value?.trim()?.takeIf { it.startsWith("{") }?.let {
                runCatching { JSONObject(it) }.getOrNull()
            }
        }

    private fun firstArray(vararg values: String?): JSONArray? =
        values.firstNotNullOfOrNull { value ->
            value?.trim()?.let {
                runCatching {
                    when {
                        it.startsWith("[") -> JSONArray(it)
                        it.startsWith("{") -> JSONArray().put(JSONObject(it))
                        else -> null
                    }
                }.getOrNull()
            }
        }

    private fun JSONObject?.toStringMap(): Map<String, String> {
        if (this == null) return emptyMap()
        return keys().asSequence().associateWith { key -> optString(key) }
    }

    private fun normalizeStatus(raw: String?): String {
        val value = raw.orEmpty().trim()
        return when {
            value.isBlank() || value == "0" || value.contains("空闲") || value == "闲" -> "闲"
            value.contains("返回") || value == "返" -> "返回"
            value.contains("出征") || value.contains("行军") || value == "征" || value == "1" -> "征"
            else -> value
        }
    }
}
