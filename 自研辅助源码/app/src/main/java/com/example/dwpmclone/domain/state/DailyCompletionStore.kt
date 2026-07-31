package com.example.dwpmclone.domain.state

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/** Process-independent daily counters/locks used by reconstructed task objects. */
interface DailyCompletionStore {
    fun count(accountId: Long, key: String, nowMillis: Long = System.currentTimeMillis()): Int
    fun add(
        accountId: Long,
        key: String,
        count: Int = 1,
        nowMillis: Long = System.currentTimeMillis()
    ): Int

    fun isCompleted(accountId: Long, key: String, nowMillis: Long = System.currentTimeMillis()): Boolean =
        count(accountId, key, nowMillis) > 0

    fun markCompleted(accountId: Long, key: String, nowMillis: Long = System.currentTimeMillis()) {
        if (!isCompleted(accountId, key, nowMillis)) add(accountId, key, 1, nowMillis)
    }
}

class InMemoryDailyCompletionStore : DailyCompletionStore {
    private val counts = linkedMapOf<Triple<Long, String, String>, Int>()

    @Synchronized
    override fun count(accountId: Long, key: String, nowMillis: Long): Int =
        counts[Triple(accountId, key, DailyCompletionCycle.dateKey(key, nowMillis))] ?: 0

    @Synchronized
    override fun add(accountId: Long, key: String, count: Int, nowMillis: Long): Int {
        if (count <= 0) return this.count(accountId, key, nowMillis)
        val storageKey = Triple(accountId, key, DailyCompletionCycle.dateKey(key, nowMillis))
        val next = (counts[storageKey] ?: 0) + count
        counts[storageKey] = next
        return next
    }
}

/** Desktop arena rewards reset at 22:00 China time; every other daily key resets at midnight. */
internal object DailyCompletionCycle {
    private const val ARENA_KEY = "arenaCoins"
    private const val ARENA_SHIFT_MILLIS = 22L * 60L * 60L * 1_000L

    fun dateKey(key: String, nowMillis: Long): String {
        val cycleMillis = if (key == ARENA_KEY) nowMillis - ARENA_SHIFT_MILLIS else nowMillis
        return SimpleDateFormat("yyyyMMdd", Locale.ROOT).apply {
            timeZone = TimeZone.getTimeZone("Asia/Shanghai")
        }.format(Date(cycleMillis))
    }
}
