package com.example.dwpmclone.data.local

import android.content.Context
import com.example.dwpmclone.domain.protocol.TaskType
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

data class DailySuccessStats(
    val brushYellowCount: Int,
    val dungeonCount: Int
)

/**
 * Persists the same user-facing, successful-action-only daily counts used by the
 * computer role page. Keys include account, task and China-local calendar date.
 */
class LocalDailySuccessStatsRepository(context: Context) {
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
        val key = key(accountId, type, nowMillis)
        val next = prefs.getInt(key, 0).coerceAtLeast(0) + count
        prefs.edit().putInt(key, next).apply()
        return next
    }

    fun current(
        accountId: Long,
        type: TaskType,
        nowMillis: Long = System.currentTimeMillis()
    ): Int = prefs.getInt(key(accountId, type, nowMillis), 0).coerceAtLeast(0)

    fun stats(
        accountId: Long,
        nowMillis: Long = System.currentTimeMillis()
    ): DailySuccessStats = DailySuccessStats(
        brushYellowCount = current(accountId, TaskType.SHUA_HUANG, nowMillis),
        dungeonCount = current(accountId, TaskType.DUNGEON, nowMillis)
    )

    private fun key(accountId: Long, type: TaskType, nowMillis: Long): String =
        "${dayFormatter().format(Date(nowMillis))}:$accountId:${type.name}"

    private fun dayFormatter() = SimpleDateFormat("yyyyMMdd", Locale.ROOT).apply {
        timeZone = TimeZone.getTimeZone("Asia/Shanghai")
    }

    private companion object {
        val SUPPORTED_TYPES = setOf(TaskType.SHUA_HUANG, TaskType.DUNGEON)
    }
}
