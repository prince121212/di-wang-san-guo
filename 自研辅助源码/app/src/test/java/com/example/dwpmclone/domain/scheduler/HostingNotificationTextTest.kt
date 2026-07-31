package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.protocol.TaskType
import org.junit.Assert.assertTrue
import org.junit.Test

class HostingNotificationTextTest {
    @Test
    fun `notification identifies accounts task and idle state`() {
        val active = HostingNotificationText.format(
            listOf("测试君主"),
            listOf(TaskType.SHUA_HUANG)
        )
        val idle = HostingNotificationText.format(listOf("测试君主"), emptyList())

        assertTrue(active.contains("账号：测试君主"))
        assertTrue(active.contains("当前：刷黄"))
        assertTrue(idle.contains("当前：等待调度"))
    }
}
