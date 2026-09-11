package com.example.dwpmclone.ui.web

import java.time.ZoneId
import java.time.ZonedDateTime
import org.junit.Assert.assertEquals
import org.junit.Test

class SharedResidentDailyCountProjectionTest {
    @Test
    fun compactLocalLedgerProjectionWinsWithoutExposingFullResidentState() {
        val nowMillis = millis(2026, 8, 1, 12)
        val dayKey = (nowMillis + 8L * 60L * 60L * 1_000L) / (24L * 60L * 60L * 1_000L)

        val projected = SharedResidentDailyCountProjection.project(
            residentDailyCountsJson = """{"schemaVersion":1,"brush":{"dayKey":$dayKey,"usedCount":8},"dungeon":{"dayKey":$dayKey,"usedCount":2}}""",
            residentConfigJson = null,
            residentStateJson = null,
            fallbackBrushYellowCount = 0,
            fallbackDungeonCount = 0,
            nowMillis = nowMillis,
        )

        assertEquals(8, projected.brushYellowCount)
        assertEquals(2, projected.dungeonCount)
    }

    @Test
    fun schemaTwoUsesPythonResidentCountersAsTheOnlyDisplaySource() {
        val nowMillis = millis(2026, 8, 1, 12)
        val dayKey = (nowMillis + 8L * 60L * 60L * 1_000L) / (24L * 60L * 60L * 1_000L)

        val projected = SharedResidentDailyCountProjection.project(
            residentConfigJson = """{"schemaVersion":2}""",
            residentStateJson = """{"brush":{"dayKey":$dayKey,"usedCount":13},"dungeon":{"dayKey":$dayKey,"usedCount":4}}""",
            fallbackBrushYellowCount = 99,
            fallbackDungeonCount = 88,
            nowMillis = nowMillis,
        )

        assertEquals(13, projected.brushYellowCount)
        assertEquals(4, projected.dungeonCount)
    }

    @Test
    fun schemaTwoResetsStaleOrMissingPythonCountersInsteadOfShowingLegacyValues() {
        val nowMillis = millis(2026, 8, 1, 12)

        val projected = SharedResidentDailyCountProjection.project(
            residentConfigJson = """{"schemaVersion":2}""",
            residentStateJson = """{"dungeon":{"dayKey":1,"usedCount":7}}""",
            fallbackBrushYellowCount = 99,
            fallbackDungeonCount = 88,
            nowMillis = nowMillis,
        )

        assertEquals(0, projected.brushYellowCount)
        assertEquals(0, projected.dungeonCount)
    }

    @Test
    fun preMigrationAccountsKeepTheirLegacyDisplayCounters() {
        val projected = SharedResidentDailyCountProjection.project(
            residentConfigJson = """{"schemaVersion":1}""",
            residentStateJson = null,
            fallbackBrushYellowCount = 9,
            fallbackDungeonCount = 2,
            nowMillis = millis(2026, 8, 1, 12),
        )

        assertEquals(9, projected.brushYellowCount)
        assertEquals(2, projected.dungeonCount)
    }

    private fun millis(year: Int, month: Int, day: Int, hour: Int): Long =
        ZonedDateTime.of(year, month, day, hour, 0, 0, 0, ZoneId.of("Asia/Shanghai"))
            .toInstant()
            .toEpochMilli()
}
