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
}
