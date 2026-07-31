package com.example.dwpmclone.data.local

import com.example.dwpmclone.domain.state.DailyCompletionCycle
import com.example.dwpmclone.domain.state.InMemoryDailyCompletionStore
import java.time.ZoneId
import java.time.ZonedDateTime
import org.junit.Assert.assertEquals
import org.junit.Test

class DailyCompletionCycleTest {
    private val china = ZoneId.of("Asia/Shanghai")

    @Test
    fun arenaCycleChangesAtTwentyTwoWhileOtherTasksChangeAtMidnight() {
        val before = millis(2026, 7, 28, 21, 59, 59)
        val boundary = millis(2026, 7, 28, 22, 0, 0)

        assertEquals("20260727", DailyCompletionCycle.dateKey("arenaCoins", before))
        assertEquals("20260728", DailyCompletionCycle.dateKey("arenaCoins", boundary))
        assertEquals("20260728", DailyCompletionCycle.dateKey("autoSignIn", before))
        assertEquals("20260728", DailyCompletionCycle.dateKey("autoSignIn", boundary))
    }

    @Test
    fun inMemoryCompletionStoreUsesTheSameArenaCycleAsPersistentStorage() {
        val before = millis(2026, 7, 28, 21, 59, 59)
        val boundary = millis(2026, 7, 28, 22, 0, 0)
        val store = InMemoryDailyCompletionStore()

        store.markCompleted(1608603L, "arenaCoins", before)

        assertEquals(1, store.count(1608603L, "arenaCoins", before))
        assertEquals(0, store.count(1608603L, "arenaCoins", boundary))
    }

    private fun millis(year: Int, month: Int, day: Int, hour: Int, minute: Int, second: Int): Long =
        ZonedDateTime.of(year, month, day, hour, minute, second, 0, china).toInstant().toEpochMilli()
}
