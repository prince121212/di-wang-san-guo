package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class GeneralProtocolShapesTest {
    @Test
    fun addEnergyPayloadMatchesCapturedDesktopRequest() {
        assertArrayEquals(
            byteArrayOf(
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x12, 0x34,
                0x00, 0x0c,
                0x00, 0x01
            ),
            GeneralProtocolShapes.buildAddEnergyPayload(generalId = 0x1234)
        )
    }

    @Test
    fun foodToCopperPayloadMatchesCapturedDesktopRequest() {
        assertArrayEquals(
            byteArrayOf(0x01, 0, 0, 0, 0, 0, 0, 0x27, 0x10),
            GeneralProtocolShapes.buildFoodToCopperPayload(10_000)
        )
    }

    @Test
    fun capturedHealAllPayloadsAndResponsesMatchDesktopProtocol() {
        assertArrayEquals(
            "0000000000000755ffffffffffff".hexBytes(),
            GeneralProtocolShapes.buildHealAllPreInfoPayload(0x755)
        )
        assertArrayEquals(
            "0000000000000755020000ffffffff00".hexBytes(),
            GeneralProtocolShapes.buildHealAllPayload(0x755)
        )

        val pre = GeneralProtocolShapes.parseHealPreInfoResponse(
            "0000000000000755ffff00000000000000010000000000000079".hexBytes(),
            expectedFiefId = 0x755,
            expectedSoldierType = -1
        )
        assertEquals(1L, pre.copperCost)
        assertEquals(121L, pre.goldCost)

        val heal = GeneralProtocolShapes.parseHealResponse(
            "00000000000000007900000000000a8dc900000000000000075501030000000300".hexBytes()
        )
        assertTrue(heal.success)
        assertEquals(0, heal.status)
        assertEquals(121L, heal.firstLong)
        assertEquals(0x0a8dc9L, heal.secondLong)
    }

    @Test
    fun addEnergyResponseRequiresExplicitZeroStatus() {
        val success = GeneralProtocolShapes.parseAddEnergyResponse("00010203".hexBytes())
        assertTrue(success.success)
        assertEquals(3, success.trailingBytes)

        val message = "道具不足".toByteArray(Charsets.UTF_8)
        val rejected = GeneralProtocolShapes.parseAddEnergyResponse(
            byteArrayOf(
                -1,
                ((message.size ushr 8) and 0xff).toByte(),
                (message.size and 0xff).toByte()
            ) + message
        )
        assertEquals(false, rejected.success)
        assertEquals("道具不足", rejected.message)
    }

    private fun String.hexBytes(): ByteArray =
        chunked(2).map { it.toInt(16).toByte() }.toByteArray()
}
