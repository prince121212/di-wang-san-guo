package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MinistryProtocolShapesTest {
    @Test
    fun captured6320EmptyAndFiveOccupiedResponsesParseExactly() {
        val empty = MinistryProtocolShapes.parseGardenStatus(EMPTY_GARDEN.hexBytes())
        val fiveOccupied = MinistryProtocolShapes.parseGardenStatus(FIVE_OCCUPIED.hexBytes())

        assertEquals(10, empty.plotCount)
        assertEquals(0, empty.occupiedCount)
        assertEquals(10, empty.emptyCount)
        assertEquals(10, fiveOccupied.plotCount)
        assertEquals(5, fiveOccupied.occupiedCount)
        assertEquals(5, fiveOccupied.emptyCount)
    }

    @Test
    fun captured6328PayloadAndE328SuccessReceiptMatchEvidence() {
        assertArrayEquals(
            byteArrayOf(1, 0, 0, 0, 1),
            MinistryProtocolShapes.buildPlantPayload("金银花")
        )
        val receipt = MinistryProtocolShapes.parsePlantResponse(PLANT_SUCCESS.hexBytes())

        assertTrue(receipt.success)
        assertEquals(0, receipt.status)
        assertEquals("操作成功。", receipt.message)
    }

    @Test
    fun unknownCropAndUnconfirmedResponseShapesFailClosed() {
        val unknownCrop = runCatching { MinistryProtocolShapes.buildPlantPayload("草药") }
        val malformedState = runCatching {
            MinistryProtocolShapes.parseGardenStatus(ByteArray(159))
        }
        val failureReceipt = MinistryProtocolShapes.parsePlantResponse(
            "010006e5a4b1e8b4a5".hexBytes()
        )

        assertTrue(unknownCrop.isFailure)
        assertTrue(malformedState.isFailure)
        assertFalse(failureReceipt.success)
        assertEquals(1, failureReceipt.status)
        assertEquals("失败", failureReceipt.message)
    }

    @Test
    fun captured6322TargetsAnd6323GardenHeaderParseAsReadOnlyScan() {
        assertArrayEquals(byteArrayOf(0), MinistryProtocolShapes.buildStealTargetListPayload())
        val targets = MinistryProtocolShapes.parseStealTargets(STEAL_TARGETS.hexBytes())

        assertEquals(10, targets.size)
        assertEquals(0x95L, targets.first().roleId)
        assertEquals("薛忆笑", targets.first().name)
        assertEquals(0x9bL, targets[8].roleId)
        assertEquals("怪咖＜猛将＞", targets[8].name)
        assertArrayEquals(
            byteArrayOf(0, 0, 0, 0, 0, 0, 0, 0x35),
            MinistryProtocolShapes.buildTargetGardenPayload(0x35)
        )
        MinistryProtocolShapes.parseTargetGardenHeader(
            TARGET_GARDEN_35.hexBytes(),
            0x35L
        )
    }

    @Test
    fun targetGardenRoleMismatchFailsClosed() {
        val result = runCatching {
            MinistryProtocolShapes.parseTargetGardenHeader(
                TARGET_GARDEN_35.hexBytes(),
                0x95L
            )
        }
        assertTrue(result.isFailure)
    }

    private fun String.hexBytes(): ByteArray =
        chunked(2).map { it.toInt(16).toByte() }.toByteArray()

    companion object {
        private const val EMPTY_GARDEN =
            "000000010000000000000028000003e80032020005002800000a000000000000000100000000000002" +
                "000000000000030000000000000400000000000005000000000000060000000000000700000000000008" +
                "000000000000090000000000000200000007000100010d0001000000020000000300000004000000050000" +
                "00060000000700000008000000090000000a0000000b0000000c0000000d0000"

        private const val FIVE_OCCUPIED =
            "000000010000000000000028000001f40032020005002800000a00000100008ca000008bbf006400645a00" +
                "00000000000000000000000000003201000100008ca000008bcf006400645a000000000000000000000000" +
                "0000003202000100008ca000008bd2006400645a0000000000000000000000000000003203000100008ca0" +
                "00008bd5006400645a0000000000000000000000000000003204000100008ca000008bd7006400645a0000" +
                "00000000000000000000000000320500000000000006000000000000070000000000000800000000000009" +
                "0000000000000200000007000100010d000100000002000000030000000400000005000000060000000700" +
                "000008000000090000000a0000000b0000000c0000000d0000"

        private const val PLANT_SUCCESS =
            "00000fe6938de4bd9ce68890e58a9fe38082000003840100000100008ca000008ca0006400645a00000000" +
                "000000000000000000000032000100000000"

        private const val STEAL_TARGETS =
            "00000fe6938de4bd9ce68890e58a9fe38082000a00000000000000950009e8969be5bf86e7ac9100000000" +
                "0000000000350015e788b1e696b0e6b8b8efbc9ce5ada6e5a3abefbc9e000900000000000000bf0007e4b8" +
                "9ee79bb8340000000000000000039d0009e6b99be890b1e5a4a9000000000000000001000018e4b889e59b" +
                "bde4ba89e99cb8efbc9ce7a68fe6989fefbc9e0000000000000000028d0012e9babbe5ad90efbc9ce5ada6" +
                "e5a3abefbc9e000500000000000000d60009e58bbee696afe895be000000000000000002900013e4bb99e5" +
                "a5b32eefbc9ce5ada6e5a3abefbc9e0005000000000000009b0012e680aae59296efbc9ce78c9be5b086ef" +
                "bc9e000500000000000000fa0018e695ace7958fe887aae784b6efbc9ce7a68fe6989fefbc9e000000"

        private const val TARGET_GARDEN_35 =
            "00000773756363657373000000000000003505030a00000d00008c8000005ab2006400644500000000000000" +
                "00000000000000320001000d00008c8000005ab3006400644500000000000000000000000000000032000200" +
                "0d00008c8000005ab50064006445000000000000000000000000000000320003000500008c8000005ab90064" +
                "006445000000000000000000000000000000320004000500008c8000005ab900640064450000000000000000" +
                "0000000000320005000500008c8000005ab90064006445000000000000000000000000000032000600050000" +
                "8c8000005aba0064006445000000000000000000000000000000320007000500008c8000005aba0064006445" +
                "000000000000000000000000000000320008000500008c8000005abc00640064450000000000000000000000" +
                "000000003200090000"
    }
}
