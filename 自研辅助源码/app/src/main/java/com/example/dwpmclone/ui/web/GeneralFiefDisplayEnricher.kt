package com.example.dwpmclone.ui.web

import org.json.JSONArray
import org.json.JSONObject

/** Adds the desktop-visible fief labels to general rows without inventing locations. */
internal object GeneralFiefDisplayEnricher {
    fun enrich(generals: JSONArray, ownedFiefs: JSONArray): JSONArray {
        if (generals.length() == 0 || ownedFiefs.length() == 0) return generals
        val fiefsById = (0 until ownedFiefs.length())
            .mapNotNull { ownedFiefs.optJSONObject(it) }
            .mapNotNull { fief -> fief.longAlias("fiefId", "targetId", "id")?.let { it to fief } }
            .toMap()
        if (fiefsById.isEmpty()) return generals

        return JSONArray().apply {
            for (index in 0 until generals.length()) {
                val source = generals.optJSONObject(index) ?: continue
                val general = JSONObject(source.toString())
                val fiefId = general.longAlias("fiefId", "placeID", "placeId", "cityId")
                val fief = fiefId?.let(fiefsById::get)
                if (fief != null) {
                    if (general.optString("fiefName").isBlank()) {
                        fief.stringAlias("fiefName", "name")?.let { general.put("fiefName", it) }
                    }
                    if (general.optString("cityName").isBlank()) {
                        fief.stringAlias("cityName", "city")?.let { general.put("cityName", it) }
                    }
                    if (!general.has("fiefId") || general.isNull("fiefId")) {
                        general.put("fiefId", fiefId)
                    }
                }
                put(general)
            }
        }
    }

    private fun JSONObject.longAlias(vararg keys: String): Long? = keys.firstNotNullOfOrNull { key ->
        if (!has(key) || isNull(key)) return@firstNotNullOfOrNull null
        val text = opt(key)?.toString()?.trim().orEmpty()
        when {
            text.startsWith("0x", ignoreCase = true) -> text.substring(2).toLongOrNull(16)
            else -> text.toLongOrNull()
        }?.takeIf { it > 0L }
    }

    private fun JSONObject.stringAlias(vararg keys: String): String? = keys.firstNotNullOfOrNull { key ->
        optString(key).trim().takeIf(String::isNotEmpty)
    }
}
