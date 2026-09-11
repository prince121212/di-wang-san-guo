package com.example.dwpmclone.data.local

import android.content.Context
import android.util.Log
import java.io.File
import org.json.JSONArray
import org.json.JSONObject

/**
 * Who a log line was written for.
 *
 * Audience is knowable only at the write site: the caller knows whether it is narrating
 * what the assistant did for its operator, or recording a trace for whoever debugs this
 * build. It cannot be recovered downstream by inspecting the text -- the previous attempt
 * to do that ([UserFacingTextLocalizer]) had to guess from substrings and turned
 * "examine mineral vein" into "exa打矿 打矿ral vein".
 *
 * [DIAGNOSTIC] is the default on every path, so a line whose author never considered the
 * question cannot leak into the operator's panel.
 */
enum class LogAudience {
    /** A sentence the operator can act on, written in their language. */
    USER,

    /** Traces, tick counters, structured events, stack traces. */
    DIAGNOSTIC;

    companion object {
        fun parse(raw: String?): LogAudience =
            entries.firstOrNull { it.name.equals(raw?.trim(), ignoreCase = true) } ?: DIAGNOSTIC
    }
}

/**
 * Bounded append-only local log store.
 *
 * SharedPreferences required a full JSON-array read/write for every line and could lose
 * concurrent UI/service writes. JSONL makes the common append path O(1); one process-wide
 * lock/cache keeps all repository instances consistent and compacts only periodically.
 *
 * Retention is budgeted per [LogAudience] rather than over the file as a whole. A single
 * shared budget is not a fair one: diagnostics outnumbered user lines by roughly 80:1 in
 * an overnight sample, so any common ring evicts the operator's history almost as fast as
 * it is written.
 */
class TaskLogRepository(context: Context) {
    private val appContext = context.applicationContext
    private val file = File(appContext.filesDir, FILE_NAME)
    private val legacyPrefs = appContext.getSharedPreferences(
        LEGACY_PREFS_NAME,
        Context.MODE_PRIVATE
    )

    fun append(
        message: String,
        tag: String = "local-scheduler",
        accountId: Long? = null,
        audience: LogAudience = LogAudience.DIAGNOSTIC,
    ) {
        appendEntry(message, tag, accountId, successCategory = null, successMessage = null, audience = audience)
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
            successMessage = safeSuccessMessage,
            // A success record is already a finished sentence about something the operator
            // asked for; it is the one class of line that is user-facing by construction.
            audience = LogAudience.USER
        )
    }

    private fun appendEntry(
        message: String,
        tag: String,
        accountId: Long?,
        successCategory: String?,
        successMessage: String?,
        audience: LogAudience
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
                successMessage = successMessage,
                audience = audience
            )
            cachedEntries += entry
            trimToAudienceBudgets()
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

    /** Newest-first, restricted to one audience. */
    fun recent(limit: Int, audience: LogAudience): List<TaskLogEntry> = synchronized(STORE_LOCK) {
        ensureLoaded()
        cachedEntries.asReversed()
            .asSequence()
            .filter { it.audience == audience }
            .take(limit.coerceIn(0, MAX_LOGS))
            .toList()
    }

    private fun trimToAudienceBudgets() = LogRetentionPolicy.trim(cachedEntries)

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
        val before = cachedEntries.size
        trimToAudienceBudgets()
        if (cachedEntries.size != before) rewriteFile()
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
        private val MAX_LOGS = LogRetentionPolicy.totalBudget()
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
    val successMessage: String? = null,
    val audience: LogAudience = LogAudience.DIAGNOSTIC
)

/**
 * Retention budgeted per audience.
 *
 * Diagnostics outran user lines by roughly 80:1 in an overnight sample, so one
 * shared ring would let a noisy hour erase the operator's whole history. Each
 * audience is trimmed against its own budget instead.
 */
internal object LogRetentionPolicy {
    const val MAX_USER_LOGS = 600
    const val MAX_DIAGNOSTIC_LOGS = 1_500

    fun budgetFor(audience: LogAudience): Int = when (audience) {
        LogAudience.USER -> MAX_USER_LOGS
        LogAudience.DIAGNOSTIC -> MAX_DIAGNOSTIC_LOGS
    }

    fun totalBudget(): Int = LogAudience.entries.sumOf(::budgetFor)

    /** Drops the oldest entries of each audience past that audience's budget. */
    fun trim(entries: MutableList<TaskLogEntry>) {
        LogAudience.entries.forEach { audience ->
            var excess = entries.count { it.audience == audience } - budgetFor(audience)
            if (excess <= 0) return@forEach
            val iterator = entries.iterator()
            while (iterator.hasNext() && excess > 0) {
                if (iterator.next().audience == audience) {
                    iterator.remove()
                    excess -= 1
                }
            }
        }
    }
}

/**
 * How a stored row that predates the audience field is classified.
 *
 * Such a row records no author intent, so it cannot be asked. Only a success
 * record is provably a sentence written for the operator; everything else is
 * assumed to be a trace, which is the direction that cannot leak.
 */
internal object LogAudiencePolicy {
    fun forStoredRow(storedAudience: String?, hasSuccessCategory: Boolean): LogAudience = when {
        storedAudience != null -> LogAudience.parse(storedAudience)
        hasSuccessCategory -> LogAudience.USER
        else -> LogAudience.DIAGNOSTIC
    }

    /**
     * Audience of one log event arriving from the shared core.
     *
     * A structured event with no human sentence has nothing to show an operator, so
     * it cannot claim the panel no matter what it declares. Rendering such an event
     * as its own JSON was how route and progress telemetry got there: half the lines
     * and 76% of the characters in an overnight sample.
     */
    fun forCoreEvent(message: String, declaredAudience: String?): LogAudience =
        if (message.isBlank()) LogAudience.DIAGNOSTIC else LogAudience.parse(declaredAudience)
}

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
    .put("audience", audience.name)

private fun String.toTaskLogEntryOrNull(): TaskLogEntry? = runCatching {
    JSONObject(this).toTaskLogEntry()
}.getOrNull()

private fun JSONObject.toTaskLogEntry(fallbackId: Long = 0L): TaskLogEntry {
    val time = optLong("time")
    val storedAudience = optString("audience").takeIf { has("audience") && !isNull("audience") }
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
        },
        audience = LogAudiencePolicy.forStoredRow(
            storedAudience = storedAudience,
            hasSuccessCategory = !isNull("successCategory") &&
                optString("successCategory").isNotBlank()
        )
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
