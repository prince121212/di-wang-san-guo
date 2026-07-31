package com.example.dwpmclone.data.local

import android.content.Context
import android.util.Log
import java.io.File
import org.json.JSONArray
import org.json.JSONObject

/**
 * Bounded append-only local log store.
 *
 * SharedPreferences required a full JSON-array read/write for every line and could lose
 * concurrent UI/service writes. JSONL makes the common append path O(1); one process-wide
 * lock/cache keeps all repository instances consistent and compacts only periodically.
 */
class TaskLogRepository(context: Context) {
    private val appContext = context.applicationContext
    private val file = File(appContext.filesDir, FILE_NAME)
    private val legacyPrefs = appContext.getSharedPreferences(
        LEGACY_PREFS_NAME,
        Context.MODE_PRIVATE
    )

    fun append(message: String, tag: String = "local-scheduler", accountId: Long? = null) {
        appendEntry(message, tag, accountId, successCategory = null, successMessage = null)
    }

    fun appendSuccess(accountId: Long, category: String, message: String, tag: String = "success-record") {
        require(accountId > 0L) { "成功记录缺少账号" }
        val safeCategory = SensitiveDataRedactor.redact(category).trim().take(MAX_SUCCESS_CATEGORY_LENGTH)
        val safeSuccessMessage = SensitiveDataRedactor.redact(message).trim().take(MAX_SUCCESS_MESSAGE_LENGTH)
        require(safeCategory.isNotBlank()) { "成功记录缺少分类" }
        require(safeSuccessMessage.isNotBlank()) { "成功记录缺少内容" }
        appendEntry(
            message = "成功记录：$safeCategory：$safeSuccessMessage",
            tag = tag,
            accountId = accountId,
            successCategory = safeCategory,
            successMessage = safeSuccessMessage
        )
    }

    private fun appendEntry(
        message: String,
        tag: String,
        accountId: Long?,
        successCategory: String?,
        successMessage: String?
    ) {
        val safeMessage = SensitiveDataRedactor.redact(message).take(MAX_MESSAGE_LENGTH)
        runCatching { Log.i(tag.take(23), safeMessage) }
        val resolvedAccountId = accountId ?: TaskLogAccountResolver.infer(safeMessage)
        synchronized(STORE_LOCK) {
            ensureLoaded()
            val now = System.currentTimeMillis()
            val entry = TaskLogEntry(
                timeMillis = now,
                tag = tag,
                message = safeMessage,
                accountId = resolvedAccountId,
                id = TaskLogCursorPolicy.nextId(now, cachedEntries.lastOrNull()?.id),
                successCategory = successCategory,
                successMessage = successMessage
            )
            cachedEntries += entry
            if (cachedEntries.size > MAX_LOGS) {
                cachedEntries.subList(0, cachedEntries.size - MAX_LOGS).clear()
            }
            runCatching {
                file.parentFile?.mkdirs()
                file.appendText(entry.toJson().toString() + "\n", Charsets.UTF_8)
                storedLineCount += 1
                if (storedLineCount > MAX_LOGS + COMPACTION_SLACK) rewriteFile()
            }.onFailure {
                Log.e(LOG_TAG, "persist task log failed", it)
            }
        }
    }

    fun recent(limit: Int = 20): List<TaskLogEntry> = synchronized(STORE_LOCK) {
        ensureLoaded()
        cachedEntries.takeLast(limit.coerceIn(0, MAX_LOGS)).asReversed()
    }

    fun clear() {
        synchronized(STORE_LOCK) {
            ensureLoaded()
            cachedEntries.clear()
            storedLineCount = 0
            runCatching { if (file.exists()) file.delete() }
            legacyPrefs.edit().remove(LEGACY_KEY_LOGS).commit()
        }
    }

    fun clearWhere(predicate: (TaskLogEntry) -> Boolean) {
        synchronized(STORE_LOCK) {
            ensureLoaded()
            cachedEntries.removeAll(predicate)
            rewriteFile()
        }
    }

    private fun ensureLoaded() {
        if (loadedPath == file.absolutePath) return
        cachedEntries.clear()
        loadedPath = file.absolutePath
        storedLineCount = 0
        if (file.exists()) {
            file.useLines(Charsets.UTF_8) { lines ->
                lines.forEach { line ->
                    storedLineCount += 1
                    line.toTaskLogEntryOrNull()?.let(cachedEntries::add)
                }
            }
        } else {
            migrateLegacyEntries()
        }
        cachedEntries.sortBy { it.id }
        if (cachedEntries.size > MAX_LOGS) {
            cachedEntries.subList(0, cachedEntries.size - MAX_LOGS).clear()
            rewriteFile()
        }
    }

    private fun migrateLegacyEntries() {
        val source = runCatching {
            JSONArray(legacyPrefs.getString(LEGACY_KEY_LOGS, "[]") ?: "[]")
        }.getOrDefault(JSONArray())
        var previousId: Long? = null
        for (index in 0 until source.length()) {
            val item = source.optJSONObject(index) ?: continue
            val time = item.optLong("time").takeIf { it > 0L } ?: continue
            val entry = item.toTaskLogEntry(
                fallbackId = TaskLogCursorPolicy.nextId(time, previousId)
            )
            cachedEntries += entry
            previousId = entry.id
        }
        if (cachedEntries.isNotEmpty()) rewriteFile()
        legacyPrefs.edit().remove(LEGACY_KEY_LOGS).commit()
    }

    private fun rewriteFile() {
        runCatching {
            file.parentFile?.mkdirs()
            val content = cachedEntries.joinToString(separator = "\n", postfix = if (cachedEntries.isEmpty()) "" else "\n") {
                it.toJson().toString()
            }
            file.writeText(content, Charsets.UTF_8)
            storedLineCount = cachedEntries.size
        }.onFailure {
            Log.e(LOG_TAG, "rewrite task logs failed", it)
        }
    }

    companion object {
        private val STORE_LOCK = Any()
        private val cachedEntries = mutableListOf<TaskLogEntry>()
        private var loadedPath: String? = null
        private var storedLineCount: Int = 0

        private const val FILE_NAME = "task_logs_v2.jsonl"
        private const val LEGACY_PREFS_NAME = "dwpm_clone_task_logs"
        private const val LEGACY_KEY_LOGS = "task_logs"
        private const val LOG_TAG = "TaskLogRepository"
        private const val MAX_LOGS = 1_500
        private const val COMPACTION_SLACK = 250
        private const val MAX_MESSAGE_LENGTH = 8_000
        private const val MAX_SUCCESS_CATEGORY_LENGTH = 30
        private const val MAX_SUCCESS_MESSAGE_LENGTH = 500
    }
}

data class TaskLogEntry(
    val timeMillis: Long,
    val tag: String,
    val message: String,
    val accountId: Long? = null,
    val id: Long = 0L,
    val successCategory: String? = null,
    val successMessage: String? = null
)

internal object TaskLogCursorPolicy {
    fun nextId(nowMillis: Long, previousId: Long?): Long =
        maxOf(nowMillis, (previousId ?: 0L) + 1L)
}

private fun TaskLogEntry.toJson(): JSONObject = JSONObject()
    .put("id", id)
    .put("time", timeMillis)
    .put("tag", tag)
    .put("message", message)
    .put("accountId", accountId ?: JSONObject.NULL)
    .put("successCategory", successCategory ?: JSONObject.NULL)
    .put("successMessage", successMessage ?: JSONObject.NULL)

private fun String.toTaskLogEntryOrNull(): TaskLogEntry? = runCatching {
    JSONObject(this).toTaskLogEntry()
}.getOrNull()

private fun JSONObject.toTaskLogEntry(fallbackId: Long = 0L): TaskLogEntry {
    val time = optLong("time")
    return TaskLogEntry(
        timeMillis = time,
        tag = optString("tag"),
        message = optString("message"),
        accountId = optLong("accountId").takeIf {
            has("accountId") && !isNull("accountId") && it > 0L
        },
        id = optLong("id").takeIf { it > 0L } ?: fallbackId.takeIf { it > 0L } ?: time,
        successCategory = optString("successCategory").trim().takeIf {
            has("successCategory") && !isNull("successCategory") && it.isNotBlank()
        },
        successMessage = optString("successMessage").trim().takeIf {
            has("successMessage") && !isNull("successMessage") && it.isNotBlank()
        }
    )
}

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
