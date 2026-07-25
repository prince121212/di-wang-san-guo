package com.example.dwpmclone.domain.scheduler

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

class DailyActivityPolicyTest {
    private val zone = TimeZone.getTimeZone("Asia/Shanghai")
    private val policy = DailyActivityPolicy(zone)

    @Test
    fun readsOnLoginAndOnlyOnceAfterLocalDateChanges() {
        val beforeMidnight = millis("2026-07-11 23:59:59")
        val afterMidnight = millis("2026-07-12 00:00:01")

        assertTrue(policy.shouldReadAfterLogin())
        assertFalse(policy.shouldReadAfterMidnight("2026-07-11", beforeMidnight))
        assertTrue(policy.shouldReadAfterMidnight("2026-07-11", afterMidnight))
        assertFalse(policy.shouldReadAfterMidnight("2026-07-12", afterMidnight))
    }

    @Test
    fun emptyArenaFailureExplainsTimeOrAlreadyClaimedAndIsNotCompleted() {
        val result = ArenaRewardPolicy.interpret(status = 1, serverMessage = "")

        assertFalse(result.success)
        assertFalse(result.completed)
        assertEquals(ArenaRewardPolicy.UNAVAILABLE_MESSAGE, result.message)
    }

    @Test
    fun successfulArenaResponseKeepsServerRewardText() {
        val result = ArenaRewardPolicy.interpret(
            status = 0,
            serverMessage = "铜钱:25000获得成功。竞技币:50获得成功。"
        )

        assertTrue(result.success)
        assertTrue(result.completed)
        assertEquals("铜钱:25000获得成功。竞技币:50获得成功。", result.message)
    }

    private fun millis(value: String): Long =
        SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.ROOT).apply {
            timeZone = zone
        }.parse(value)!!.time
}
