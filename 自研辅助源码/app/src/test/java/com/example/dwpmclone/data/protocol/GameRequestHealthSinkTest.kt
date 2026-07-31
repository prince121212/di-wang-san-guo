package com.example.dwpmclone.data.protocol

import org.junit.Assert.assertEquals
import org.junit.Test

class GameRequestHealthSinkTest {
    @Test
    fun `thread local account binding attributes multi account requests independently`() {
        val records = mutableListOf<Pair<Long, String>>()
        try {
            GameRequestHealthSink.writer = { accountId, _, purpose, _ ->
                synchronized(records) { records += accountId to purpose }
            }
            GameRequestHealthSink.bindAccount(11L)
            assertEquals(11L, GameRequestHealthSink.currentAccountId())
            GameRequestHealthSink.record(true, "主线程")
            val worker = Thread {
                GameRequestHealthSink.bindAccount(22L)
                try {
                    GameRequestHealthSink.record(true, "工作线程")
                } finally {
                    GameRequestHealthSink.clearAccount()
                }
            }
            worker.start()
            worker.join()
            assertEquals(11L, GameRequestHealthSink.currentAccountId())
            GameRequestHealthSink.record(true, "主线程仍绑定")

            assertEquals(
                listOf(11L to "主线程", 22L to "工作线程", 11L to "主线程仍绑定"),
                records
            )
        } finally {
            GameRequestHealthSink.reset()
        }
    }
}
