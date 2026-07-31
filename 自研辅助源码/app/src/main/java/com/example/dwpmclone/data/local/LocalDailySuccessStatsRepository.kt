package com.example.dwpmclone.data.local

import android.content.Context
import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.state.DailyCompletionCycle
import com.example.dwpmclone.domain.state.DailyCompletionStore

data class DailySuccessStats(
    val brushYellowCount: Int,
    val dungeonCount: Int
)

/**
 * Persists the same user-facing, successful-action-only daily counts used by the
 * computer role page. Keys include account, task and China-local calendar date.
 */
class LocalDailySuccessStatsRepository(context: Context) : DailyCompletionStore {
    private val prefs = context.getSharedPreferences(
        "dwpm_clone_daily_success_stats",
        Context.MODE_PRIVATE
    )

    fun add(
        accountId: Long,
        type: TaskType,
        count: Int = 1,
        nowMillis: Long = System.currentTimeMillis()
    ): Int {
        if (count <= 0 || type !in SUPPORTED_TYPES) return current(accountId, type, nowMillis)
        return add(accountId, type.name, count, nowMillis)
    }

    fun current(
        accountId: Long,
        type: TaskType,
        nowMillis: Long = System.currentTimeMillis()
    ): Int = count(accountId, type.name, nowMillis)

    override fun count(accountId: Long, key: String, nowMillis: Long): Int =
        prefs.getInt(key(accountId, normalizedKey(key), nowMillis), 0).coerceAtLeast(0)

    override fun add(accountId: Long, key: String, count: Int, nowMillis: Long): Int {
        if (count <= 0) return this.count(accountId, key, nowMillis)
        val storageKey = key(accountId, normalizedKey(key), nowMillis)
        val next = prefs.getInt(storageKey, 0).coerceAtLeast(0) + count
        check(prefs.edit().putInt(storageKey, next).commit()) { "无法持久化每日完成状态" }
        return next
    }

    fun stats(
        accountId: Long,
        nowMillis: Long = System.currentTimeMillis()
    ): DailySuccessStats = DailySuccessStats(
        brushYellowCount = current(accountId, TaskType.SHUA_HUANG, nowMillis),
        dungeonCount = current(accountId, TaskType.DUNGEON, nowMillis)
    )

    private fun key(accountId: Long, key: String, nowMillis: Long): String {
        val normalized = normalizedKey(key)
        return "${DailyCompletionCycle.dateKey(normalized, nowMillis)}:$accountId:$normalized"
    }

    private fun normalizedKey(value: String): String {
        val normalized = value.trim().replace(Regex("[^A-Za-z0-9._-]"), "_").take(80)
        require(normalized.isNotBlank()) { "每日完成状态 key 不能为空" }
        return normalized
    }

    private companion object {
        val SUPPORTED_TYPES = setOf(TaskType.SHUA_HUANG, TaskType.DUNGEON)
    }
}
