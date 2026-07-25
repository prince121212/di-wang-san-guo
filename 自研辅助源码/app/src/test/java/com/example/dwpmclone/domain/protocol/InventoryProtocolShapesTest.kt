package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class InventoryProtocolShapesTest {
    @Test
    fun exactUseAndDiscardPayloadsMatchDesktopProtocol() {
        assertArrayEquals(
            byteArrayOf(0x00, 0x3a, 0x00, 0x02),
            InventoryProtocolShapes.buildUsePayload(itemId = 58, count = 2)
        )
        assertArrayEquals(
            byteArrayOf(
                0x00,
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x09,
                0x00, 0x00, 0x00, 0x1b,
                -1, -1, -1, -1, -1, -1, -1, -1
            ),
            InventoryProtocolShapes.buildDiscardPayload(kind = 0, objectId = 9, count = 27)
        )
    }

    @Test
    fun exactBatchMultiplesNeverCreateZeroCountActions() {
        val open = InventoryProtocolShapes.planOpenBatches("惊喜宝箱", total = 18, batchSize = 9)
        val discard = InventoryProtocolShapes.planDiscardBatches("传音符", total = 198, batchSize = 99)

        assertFalse(open.filterIsInstance<InventoryVaultAction.OpenItem>().any { it.request.count == 0 })
        assertFalse(discard.filterIsInstance<InventoryVaultAction.DiscardItem>().any { it.request.count == 0 })
        assertTrue(InventoryProtocolShapes.planOpenBatches("惊喜宝箱", 0, 9).isEmpty())
        assertTrue(InventoryProtocolShapes.planDiscardBatches("传音符", 0, 99).isEmpty())
    }

    @Test
    fun captured8103AndA144StatusUtfReceiptsParse() {
        val discard = InventoryProtocolShapes.parseActionResponse(
            "00000fe4b8a2e5bc83e68890e58a9fefbc81".hexBytes()
        )
        assertTrue(discard.success)
        assertEquals(0, discard.status)
        assertEquals("丢弃成功！", discard.message)

        val open = InventoryProtocolShapes.parseActionResponse(
            "000017e88eb7e5be97e9939ce992b13a333030303b3c62722f3e".hexBytes()
        )
        assertTrue(open.success)
        assertEquals("获得铜钱:3000;<br/>", open.message)
    }

    private fun String.hexBytes(): ByteArray =
        chunked(2).map { it.toInt(16).toByte() }.toByteArray()
}
