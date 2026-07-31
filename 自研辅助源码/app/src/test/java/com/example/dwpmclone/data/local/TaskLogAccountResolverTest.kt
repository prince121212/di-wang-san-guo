package com.example.dwpmclone.data.local

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TaskLogAccountResolverTest {
    @Test
    fun infersSchedulerAndChineseAccountPrefixesWithoutGuessingUnscopedLogs() {
        assertEquals(351L, TaskLogAccountResolver.infer("account=351 owner=SHUA_HUANG step-start"))
        assertEquals(77L, TaskLogAccountResolver.infer("账号77出口IP检测成功"))
        assertEquals(88L, TaskLogAccountResolver.infer("账号 #88 网络路由已切换"))
        assertEquals(null, TaskLogAccountResolver.infer("云端连接成功"))
    }

    @Test
    fun selectedAccountFilterDoesNotLeakOtherOrUnscopedAccountLogs() {
        val selected = TaskLogEntry(1L, "task", "selected", 77L)
        val other = TaskLogEntry(2L, "task", "other", 88L)
        val unscoped = TaskLogEntry(3L, "task", "global", null)

        assertTrue(TaskLogAccountResolver.matches(selected, 77L))
        assertFalse(TaskLogAccountResolver.matches(other, 77L))
        assertFalse(TaskLogAccountResolver.matches(unscoped, 77L))
        assertTrue(TaskLogAccountResolver.matches(unscoped, null))
    }

    @Test
    fun cursorIdsRemainStrictlyIncreasingWithinSameMillisecondAndAcrossClockRollback() {
        val first = TaskLogCursorPolicy.nextId(nowMillis = 1_000L, previousId = null)
        val second = TaskLogCursorPolicy.nextId(nowMillis = 1_000L, previousId = first)
        val afterRollback = TaskLogCursorPolicy.nextId(nowMillis = 900L, previousId = second)

        assertEquals(1_000L, first)
        assertEquals(1_001L, second)
        assertEquals(1_002L, afterRollback)
    }

    @Test
    fun cursorFilteringDoesNotDropEntriesCreatedInTheSameMillisecond() {
        val entries = listOf(
            TaskLogEntry(1_000L, "task", "first", id = 1_000L),
            TaskLogEntry(1_000L, "task", "second", id = 1_001L),
            TaskLogEntry(1_000L, "task", "third", id = 1_002L)
        )

        assertEquals(listOf("second", "third"), entries.filter { it.id > 1_000L }.map { it.message })
    }

    @Test
    fun successRecordsPreferStructuredFactsAndNeverUseGenericSuccessWords() {
        val structured = TaskLogEntry(
            timeMillis = 1L,
            tag = "task",
            message = "任务内部记录",
            accountId = 77L,
            id = 1L,
            successCategory = "刷黄",
            successMessage = "编队1 > 10级山贼(91，26)"
        )

        assertEquals("刷黄", TaskSuccessRecordPolicy.resolve(structured)?.category)
        assertEquals(
            null,
            TaskSuccessRecordPolicy.fromLegacyMessage("常规-日常保存成功：已开启自动签到")
        )
        assertEquals(
            null,
            TaskSuccessRecordPolicy.fromLegacyMessage("自动捐献完成：铜钱成功、粮食失败、科技积分成功")
        )
        assertEquals(
            "领币",
            TaskSuccessRecordPolicy.fromLegacyMessage("领竞技币完成：服务器确认成功")?.category
        )
        assertEquals(
            "编队2 > 第四章第5关",
            TaskSuccessRecordPolicy.fromLegacyMessage(
                "副本第 1 轮第 2 条完成：将领甲 → 第四章第5关，开箱成功"
            )?.message
        )
    }
}
