package com.example.dwpmclone.host

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * Durable hand-over record for a resident operation.
 *
 * The process can disappear between submit and the next status read.  Keeping
 * the idempotency key before submitting, and the operation id immediately
 * after submitting, makes that hand-over recoverable without replaying a
 * mutation whose send boundary is unknown.
 */
data class ResidentOperationRef(
    val operationId: String?,
    val tickKey: String,
)

interface ResidentOperationStore {
    fun get(accountId: Long): ResidentOperationRef?
    fun ensureTickKey(accountId: Long, suggestedKey: String): String
    fun putOperation(accountId: Long, operationId: String, tickKey: String)
    fun clear(accountId: Long)
    fun clearAll()
}

/** Small in-memory implementation used by JVM tests and non-Android callers. */
class InMemoryResidentOperationStore : ResidentOperationStore {
    private val values = linkedMapOf<Long, ResidentOperationRef>()

    @Synchronized
    override fun get(accountId: Long): ResidentOperationRef? = values[accountId]

    @Synchronized
    override fun ensureTickKey(accountId: Long, suggestedKey: String): String {
        val current = values[accountId]
        if (current != null) return current.tickKey
        val key = suggestedKey.trim().ifBlank { "resident-$accountId" }
        values[accountId] = ResidentOperationRef(operationId = null, tickKey = key)
        return key
    }

    @Synchronized
    override fun putOperation(accountId: Long, operationId: String, tickKey: String) {
        values[accountId] = ResidentOperationRef(
            operationId = operationId.trim().takeIf(String::isNotBlank),
            tickKey = tickKey.trim().ifBlank { "resident-$accountId" },
        )
    }

    @Synchronized
    override fun clear(accountId: Long) {
        values.remove(accountId)
    }

    @Synchronized
    override fun clearAll() {
        values.clear()
    }
}

/** SharedPreferences-backed implementation used by the Android service. */
class AndroidResidentOperationStore(context: Context) : ResidentOperationStore {
    private val preferences = context.applicationContext.getSharedPreferences(
        PREFS,
        Context.MODE_PRIVATE,
    )

    @Synchronized
    override fun get(accountId: Long): ResidentOperationRef? {
        val objectValue = read().optJSONObject(accountId.toString()) ?: return null
        val key = objectValue.optString("tickKey").trim()
        if (key.isBlank()) return null
        return ResidentOperationRef(
            operationId = objectValue.optString("operationId")
                .trim()
                .takeIf(String::isNotBlank),
            tickKey = key,
        )
    }

    @Synchronized
    override fun ensureTickKey(accountId: Long, suggestedKey: String): String {
        val all = read()
        val current = all.optJSONObject(accountId.toString())
        val existing = current?.optString("tickKey")?.trim().orEmpty()
        if (existing.isNotBlank()) return existing
        val key = suggestedKey.trim().ifBlank { "resident-$accountId" }
        all.put(
            accountId.toString(),
            JSONObject().put("tickKey", key),
        )
        write(all)
        return key
    }

    @Synchronized
    override fun putOperation(accountId: Long, operationId: String, tickKey: String) {
        val all = read()
        all.put(
            accountId.toString(),
            JSONObject()
                .put("operationId", operationId.trim())
                .put("tickKey", tickKey.trim().ifBlank { "resident-$accountId" }),
        )
        write(all)
    }

    @Synchronized
    override fun clear(accountId: Long) {
        val all = read()
        all.remove(accountId.toString())
        write(all)
    }

    @Synchronized
    override fun clearAll() {
        check(preferences.edit().remove(KEY).commit()) {
            "无法清理常驻 operation 恢复记录"
        }
    }

    private fun read(): JSONObject = runCatching {
        JSONObject(preferences.getString(KEY, "{}") ?: "{}")
    }.getOrDefault(JSONObject())

    private fun write(value: JSONObject) {
        check(preferences.edit().putString(KEY, value.toString()).commit()) {
            "无法持久化常驻 operation 恢复记录"
        }
    }

    private companion object {
        const val PREFS = "dwpm_resident_operations"
        const val KEY = "records"
    }
}

