package com.example.dwpmclone.data.local

import android.content.Context
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject

/** Lightweight local log store for read-only sync and local scheduling. */
class TaskLogRepository(context: Context) {
    private val prefs = context.getSharedPreferences("dwpm_clone_task_logs", Context.MODE_PRIVATE)

    fun append(message: String, tag: String = "local-scheduler", accountId: Long? = null) {
        runCatching { Log.i(tag.take(23), message) }
        val resolvedAccountId = accountId ?: TaskLogAccountResolver.infer(message)
        val logs = readArray()
        logs.put(
            JSONObject()
                .put("time", System.currentTimeMillis())
                .put("tag", tag)
                .put("message", message)
                .put("accountId", resolvedAccountId)
        )
        val trimmed = JSONArray()
        val start = maxOf(0, logs.length() - MAX_LOGS)
        for (i in start until logs.length()) trimmed.put(logs.getJSONObject(i))
        prefs.edit().putString(KEY_LOGS, trimmed.toString()).apply()
    }

    fun recent(limit: Int = 20): List<TaskLogEntry> {
        val logs = readArray()
        val start = maxOf(0, logs.length() - limit)
        return (start until logs.length()).map { index ->
            val item = logs.getJSONObject(index)
            TaskLogEntry(
                timeMillis = item.optLong("time"),
                tag = item.optString("tag"),
                message = item.optString("message"),
                accountId = item.optLong("accountId").takeIf {
                    item.has("accountId") && !item.isNull("accountId") && it > 0L
                }
            )
        }.reversed()
    }

    fun clear() {
        prefs.edit().remove(KEY_LOGS).apply()
    }

    fun clearWhere(predicate: (TaskLogEntry) -> Boolean) {
        val source = readArray()
        val kept = JSONArray()
        for (index in 0 until source.length()) {
            val item = source.optJSONObject(index) ?: continue
            val entry = TaskLogEntry(
                timeMillis = item.optLong("time"),
                tag = item.optString("tag"),
                message = item.optString("message"),
                accountId = item.optLong("accountId").takeIf {
                    item.has("accountId") && !item.isNull("accountId") && it > 0L
                }
            )
            if (!predicate(entry)) kept.put(item)
        }
        prefs.edit().putString(KEY_LOGS, kept.toString()).apply()
    }

    private fun readArray(): JSONArray =
        runCatching { JSONArray(prefs.getString(KEY_LOGS, "[]") ?: "[]") }.getOrDefault(JSONArray())

    companion object {
        private const val KEY_LOGS = "task_logs"
        private const val MAX_LOGS = 200
    }
}

data class TaskLogEntry(
    val timeMillis: Long,
    val tag: String,
    val message: String,
    val accountId: Long? = null
)

internal object TaskLogAccountResolver {
    private val patterns = listOf(
        Regex("""\baccount=(\d+)\b""", RegexOption.IGNORE_CASE),
        Regex("""账号\s*#?(\d+)""")
    )

    fun infer(message: String): Long? =
        patterns.firstNotNullOfOrNull { pattern ->
            pattern.find(message)?.groupValues?.getOrNull(1)?.toLongOrNull()
        }

    fun matches(entry: TaskLogEntry, selectedAccountId: Long?): Boolean =
        selectedAccountId == null || entry.accountId == selectedAccountId
}
