package com.example.dwpmclone.data.local

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The operator's runtime panel and the developer's system log had one stream between
 * them, so a trace written for debugging appeared in the panel. These pin the rule that
 * separates them: audience is declared by the writer, and defaults to diagnostic.
 */
class LogAudienceSeparationTest {

    @Test
    fun anUndeclaredAudienceIsDiagnosticSoNothingLeaksIntoTheOperatorPanel() {
        assertEquals(LogAudience.DIAGNOSTIC, LogAudience.parse(null))
        assertEquals(LogAudience.DIAGNOSTIC, LogAudience.parse(""))
        assertEquals(LogAudience.DIAGNOSTIC, LogAudience.parse("  "))
        assertEquals(LogAudience.DIAGNOSTIC, LogAudience.parse("operator"))
        assertEquals(LogAudience.DIAGNOSTIC, LogAudience.parse("USERS"))
    }

    @Test
    fun aDeclaredUserAudienceIsHonouredRegardlessOfCasingOrPadding() {
        assertEquals(LogAudience.USER, LogAudience.parse("user"))
        assertEquals(LogAudience.USER, LogAudience.parse("USER"))
        assertEquals(LogAudience.USER, LogAudience.parse(" User "))
    }

    @Test
    fun rowsStoredBeforeTheFieldExistedOnlyCountAsUserWhenTheyAreSuccessRecords() {
        assertEquals(
            LogAudience.USER,
            LogAudiencePolicy.forStoredRow(storedAudience = null, hasSuccessCategory = true)
        )
        assertEquals(
            LogAudience.DIAGNOSTIC,
            LogAudiencePolicy.forStoredRow(storedAudience = null, hasSuccessCategory = false)
        )
    }

    @Test
    fun anExplicitStoredAudienceWinsOverTheSuccessRecordHeuristic() {
        assertEquals(
            LogAudience.DIAGNOSTIC,
            LogAudiencePolicy.forStoredRow(
                storedAudience = "DIAGNOSTIC",
                hasSuccessCategory = true
            )
        )
    }

    @Test
    fun aBurstOfDiagnosticsCannotEvictTheOperatorHistory() {
        val entries = mutableListOf<TaskLogEntry>()
        repeat(20) { index ->
            entries += entry(id = index.toLong(), audience = LogAudience.USER)
        }
        // The overnight sample ran roughly 80 diagnostics per user line; one shared ring
        // would have discarded every user line above long before the panel was opened.
        repeat(LogRetentionPolicy.MAX_DIAGNOSTIC_LOGS * 2) { index ->
            entries += entry(id = 1_000L + index, audience = LogAudience.DIAGNOSTIC)
        }

        LogRetentionPolicy.trim(entries)

        assertEquals(20, entries.count { it.audience == LogAudience.USER })
        assertEquals(
            LogRetentionPolicy.MAX_DIAGNOSTIC_LOGS,
            entries.count { it.audience == LogAudience.DIAGNOSTIC }
        )
    }

    @Test
    fun trimmingDropsTheOldestOfEachAudienceAndKeepsChronologicalOrder() {
        val entries = (0 until LogRetentionPolicy.MAX_USER_LOGS + 5)
            .map { entry(id = it.toLong(), audience = LogAudience.USER) }
            .toMutableList()

        LogRetentionPolicy.trim(entries)

        assertEquals(LogRetentionPolicy.MAX_USER_LOGS, entries.size)
        assertEquals(5L, entries.first().id)
        assertTrue(entries.zipWithNext().all { (a, b) -> a.id < b.id })
    }

    @Test
    fun aStructuredCoreEventWithNoSentenceStaysOutOfTheOperatorPanel() {
        // Shape taken verbatim from an overnight capture: this row, rendered as its own
        // JSON, is what the operator was being shown. 597 of 772 such rows were RUNNING
        // progress ticks that the UI already receives over the event channel.
        val recoveryTick = JSONObject()
            .put("accountRef", "176")
            .put("kind", "automation:recovery-tick:v1")
            .put("level", "info")
            .put("operationId", "op_cffdd03622884c99af4a54299e86f55c")
            .put("status", "RUNNING")
            .put("progress", 40)

        assertEquals(
            LogAudience.DIAGNOSTIC,
            LogAudiencePolicy.forCoreEvent(
                message = recoveryTick.optString("message"),
                declaredAudience = recoveryTick.optString("audience")
            )
        )
    }

    @Test
    fun aMessagelessEventCannotClaimTheOperatorPanelEvenIfItAsksTo() {
        assertEquals(
            LogAudience.DIAGNOSTIC,
            LogAudiencePolicy.forCoreEvent(message = "", declaredAudience = "user")
        )
    }

    @Test
    fun aCoreSentenceThatDeclaresItselfUserFacingReachesTheOperatorPanel() {
        assertEquals(
            LogAudience.USER,
            LogAudiencePolicy.forCoreEvent(
                message = "活血丹：统弓2 使用1枚活血丹，体力25→75",
                declaredAudience = "user"
            )
        )
    }

    @Test
    fun anInternalWarningStaysDiagnosticBecauseItNeverDeclaredAnAudience() {
        // e.g. "共享云端数据心跳失败：Connection reset" followed by a Java stack trace.
        assertEquals(
            LogAudience.DIAGNOSTIC,
            LogAudiencePolicy.forCoreEvent(
                message = "共享云端数据心跳失败：Connection reset\n\tat java.net.SocketInputStream.read",
                declaredAudience = ""
            )
        )
    }

    @Test
    fun aSuccessRecordCarriesNoWireIdentifiersIntoTheOperatorPanel() {
        // 出征/领取/使用道具 are the lines the panel exists to show, and they are already
        // written as finished Chinese sentences, so no rewriting pass is needed.
        val record = entry(id = 1L, audience = LogAudience.USER)
            .copy(message = "成功记录：活血丹：统弓2 使用1枚活血丹，体力25→75，来源将领维护")

        assertTrue(record.message.none { it == '{' || it == '}' })
        assertTrue(record.message.contains("活血丹"))
    }

    private fun entry(id: Long, audience: LogAudience) = TaskLogEntry(
        timeMillis = id,
        tag = "test",
        message = "line-$id",
        accountId = 176L,
        id = id,
        audience = audience
    )
}
