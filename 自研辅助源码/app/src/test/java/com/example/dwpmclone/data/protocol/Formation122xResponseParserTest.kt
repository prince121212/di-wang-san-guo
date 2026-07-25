package com.example.dwpmclone.data.protocol

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class Formation122xResponseParserTest {
    @Test
    fun captured8226UsesNewTypeAndCountRatherThanPreviousPair() {
        val capturedPayload = "0100000000006b4d9a0008007200080085010300000004"

        val result = Formation122xResponseParser.parse8226(capturedPayload)

        assertTrue(result.success)
        assertEquals(0x6b4d9aL, result.generalId)
        assertEquals(8, result.previousType)
        assertEquals(114, result.previousCount)
        assertEquals(8, result.assignedType)
        assertEquals(133, result.assignedCount)
    }

    @Test
    fun captured8229ParsesSuccessTextAndEveryRefilledGeneral() {
        val capturedPayload =
            "000012e689b9e9878fe8a1a5e6bba1e68890e58a9f" +
                "02" +
                "00000000006b4dae0100000096" +
                "00000000006b4d9a080000000a" +
                "00000000000007550103000000c0"

        val result = Formation122xResponseParser.parse8229(capturedPayload)

        assertTrue(result.success)
        assertEquals("批量补满成功", result.message)
        assertEquals(2, result.entries.size)
        assertEquals(FormationRefillEntry(0x6b4daeL, 1, 150), result.entries[0])
        assertEquals(FormationRefillEntry(0x6b4d9aL, 8, 10), result.entries[1])
    }

    @Test
    fun shortOrNonConfirming8229FailsClosed() {
        assertFalse(Formation122xResponseParser.parse8229("00").success)
        assertFalse(
            Formation122xResponseParser.parse8229(
                "00000ce689b9e9878fe5a4b1e8b4a500"
            ).success
        )
    }
}
