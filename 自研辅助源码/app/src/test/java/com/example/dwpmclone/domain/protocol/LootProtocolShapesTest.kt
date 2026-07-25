package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertEquals
import org.junit.Test

class LootProtocolShapesTest {
    @Test
    fun `query payload matches captured player lookup`() {
        assertEquals(
            "00010009e5a4a9e99b84e6989f",
            LootProtocolShapes.buildFiefListPayload("天雄星").toHex()
        )
    }

    @Test
    fun `dispatch payloads match immediate raid layout`() {
        val generals = listOf(0xc4a332L, 0xc4a331L)
        assertEquals(
            "01020000000000c4a3320000000000c4a3310000000000000959",
            LootProtocolShapes.buildPreparePayload(generals, 0x0959).toHex()
        )
        assertEquals(
            "01020000000000c4a3320000000000c4a3310000000000000959ffffffffffffffff000000",
            LootProtocolShapes.buildExpeditionPayload(generals, 0x0959).toHex()
        )
    }

    private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }
}
