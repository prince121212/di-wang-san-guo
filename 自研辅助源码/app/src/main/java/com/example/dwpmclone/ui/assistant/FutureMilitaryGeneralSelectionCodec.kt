package com.example.dwpmclone.ui.assistant

import org.json.JSONArray
import org.json.JSONObject

/**
 * Compatibility codec for the desktop military row shape.
 *
 * Current desktop rows store an ordered `generalIds` array and retain `generalId` as the first
 * selection for older consumers. Android historically loaded/saved only `generalId`, which
 * silently discarded every additional selected general.
 */
internal object FutureMilitaryGeneralSelectionCodec {
    fun read(row: JSONObject): List<Long> = buildList {
        row.optJSONArray("generalIds")?.let { ids ->
            for (index in 0 until ids.length()) {
                ids.optLong(index).takeIf { it > 0L }?.let(::add)
            }
        }
        if (isEmpty()) row.optLong("generalId").takeIf { it > 0L }?.let(::add)
    }.distinct()

    fun normalize(ids: Iterable<Long>): List<Long> =
        ids.filter { it > 0L }.distinct()

    fun write(ids: Iterable<Long>): JSONArray =
        JSONArray().apply { normalize(ids).forEach(::put) }
}
