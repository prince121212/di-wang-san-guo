package com.example.dwpmclone.data.local

import com.example.dwpmclone.domain.localmap.LocalMapKind
import com.example.dwpmclone.domain.localmap.LocalMapQueryKey
import com.example.dwpmclone.domain.localmap.LocalMapSnapshot
import com.example.dwpmclone.domain.localmap.LocalMapTargetRecord
import com.example.dwpmclone.domain.model.MapCoordinate
import org.json.JSONArray
import org.json.JSONObject

internal object LocalMapJsonCodec {
    private const val VERSION = 1

    fun encode(snapshots: List<LocalMapSnapshot>): String = JSONObject()
        .put("version", VERSION)
        .put("snapshots", JSONArray().apply {
            snapshots.forEach { snapshot ->
                put(JSONObject()
                    .put("query", JSONObject()
                        .put("accountId", snapshot.query.accountId)
                        .put("serverId", snapshot.query.serverId)
                        .put("kind", snapshot.query.kind.name)
                        .put("fingerprint", snapshot.query.fingerprint))
                    .put("scannedAtMillis", snapshot.scannedAtMillis)
                    .put("targets", JSONArray().apply {
                        snapshot.targets.forEach { record -> put(record.toJson()) }
                    }))
            }
        })
        .toString()

    fun decode(raw: String?): List<LocalMapSnapshot> {
        if (raw.isNullOrBlank()) return emptyList()
        val root = runCatching { JSONObject(raw) }.getOrNull() ?: return emptyList()
        if (root.optInt("version") != VERSION) return emptyList()
        val snapshots = root.optJSONArray("snapshots") ?: return emptyList()
        return buildList {
            for (index in 0 until snapshots.length()) {
                val snapshot = snapshots.optJSONObject(index)?.toSnapshotOrNull() ?: continue
                add(snapshot)
            }
        }
    }

    private fun JSONObject.toSnapshotOrNull(): LocalMapSnapshot? = runCatching {
        val queryJson = getJSONObject("query")
        val query = LocalMapQueryKey(
            accountId = queryJson.getLong("accountId"),
            serverId = queryJson.getString("serverId"),
            kind = LocalMapKind.valueOf(queryJson.getString("kind")),
            fingerprint = queryJson.getString("fingerprint")
        )
        require(query.accountId > 0L && query.serverId.isNotBlank() && query.fingerprint.isNotBlank())
        val targetArray = optJSONArray("targets") ?: JSONArray()
        LocalMapSnapshot(
            query = query,
            scannedAtMillis = getLong("scannedAtMillis"),
            targets = buildList {
                for (index in 0 until targetArray.length()) {
                    targetArray.optJSONObject(index)?.toRecordOrNull()?.let(::add)
                }
            }
        )
    }.getOrNull()

    private fun LocalMapTargetRecord.toJson(): JSONObject = JSONObject()
        .put("targetId", targetId)
        .put("x", coordinate.x)
        .put("y", coordinate.y)
        .put("type", type)
        .put("level", level ?: JSONObject.NULL)
        .put("filterFields", JSONObject().apply {
            filterFields.toSortedMap().forEach { (key, value) -> put(key, value) }
        })
        .put("firstDiscoveredAtMillis", firstDiscoveredAtMillis)
        .put("lastValidatedAtMillis", lastValidatedAtMillis)
        .put("invalidatedAtMillis", invalidatedAtMillis ?: JSONObject.NULL)
        .put("invalidReason", invalidReason ?: JSONObject.NULL)

    private fun JSONObject.toRecordOrNull(): LocalMapTargetRecord? = runCatching {
        val fieldsJson = optJSONObject("filterFields") ?: JSONObject()
        val fields = linkedMapOf<String, String>()
        fieldsJson.keys().forEach { key -> fields[key] = fieldsJson.optString(key) }
        LocalMapTargetRecord(
            targetId = getLong("targetId"),
            coordinate = MapCoordinate(getInt("x"), getInt("y")),
            type = getString("type"),
            level = optInt("level").takeIf { has("level") && !isNull("level") },
            filterFields = fields,
            firstDiscoveredAtMillis = getLong("firstDiscoveredAtMillis"),
            lastValidatedAtMillis = getLong("lastValidatedAtMillis"),
            invalidatedAtMillis = optLong("invalidatedAtMillis").takeIf {
                has("invalidatedAtMillis") && !isNull("invalidatedAtMillis")
            },
            invalidReason = optString("invalidReason").takeIf {
                has("invalidReason") && !isNull("invalidReason") && it.isNotBlank()
            }
        ).also { require(it.targetId > 0L && it.firstDiscoveredAtMillis >= 0L) }
    }.getOrNull()
}
