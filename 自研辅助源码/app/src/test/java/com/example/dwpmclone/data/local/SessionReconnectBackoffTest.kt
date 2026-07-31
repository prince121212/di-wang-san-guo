package com.example.dwpmclone.data.local

import org.junit.Assert.assertEquals
import org.junit.Test

class SessionReconnectBackoffTest {
    @Test
    fun growsAndCapsWithoutBusyLooping() {
        assertEquals(5_000L, SessionReconnectBackoff.delayMillis(1))
        assertEquals(15_000L, SessionReconnectBackoff.delayMillis(2))
        assertEquals(60_000L, SessionReconnectBackoff.delayMillis(4))
        assertEquals(300_000L, SessionReconnectBackoff.delayMillis(99))
    }
}
