package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream

class InternalAffairsLiveShapesTest {
    @Test
    fun fiefQueryAndBuildingActionMatchDesktopProtocol() {
        assertArrayEquals(
            byteArrayOf(0, 0, 0, 0, 0, 0, 0, 0x0a, 0x79),
            InternalAffairsProtocolShapes.buildFiefQueryPayload(0x0a79)
        )
        assertArrayEquals(
            byteArrayOf(
                0, 0, 0, 0, 0, 0, 0x09, 0xaf.toByte(),
                3,
                0, 5,
                2,
                0,
                0
            ),
            InternalAffairsProtocolShapes.buildTechnologyUpgradePayload(
                fiefId = 0x09af,
                academySlot = 3,
                technologyId = 5,
                targetLevel = 2
            )
        )
        assertArrayEquals(
            byteArrayOf(
                0,
                0, 0, 0, 0, 0, 0, 0x0a, 0x79,
                0, 3,
                0, 1
            ),
            InternalAffairsProtocolShapes.buildBuildingActionPayload(
                fiefId = 0x0a79,
                slot = 3,
                buildingTypeId = 1
            )
        )
    }

    @Test
    fun parsesVerified8246BuildingRecordShape() {
        val payload = CAPTURED_8246_SECONDARY.hexBytes()

        val state = InternalAffairsProtocolShapes.parseFiefState(payload, 0x0a79)
        val building = state.buildings.last()

        assertEquals("九业封地", state.name)
        assertEquals(2, state.buildQueueCapacity)
        assertEquals(4, state.buildings.size)
        assertEquals(10, building.slotOrIndex)
        assertEquals(1, building.typeId)
        assertEquals(1, building.rank)
        assertEquals(false, building.busy)
    }

    @Test
    fun parsesAndConfirmsCaptured8200BuildingSync() {
        val receipt = InternalAffairsProtocolShapes.parseBuildingActionResponse(
            CAPTURED_8200_BUILD.hexBytes()
        )

        assertTrue(receipt.success)
        assertEquals(0x0a79L, receipt.fiefId)
        assertEquals(4, receipt.buildings.size)
        assertTrue(
            InternalAffairsProtocolShapes.actionWasApplied(
                receipt,
                expectedFiefId = 0x0a79,
                slot = 10,
                buildingTypeId = 1,
                previousLevel = null
            )
        )
        assertFalse(
            InternalAffairsProtocolShapes.actionWasApplied(
                receipt,
                expectedFiefId = 0x0a78,
                slot = 10,
                buildingTypeId = 1,
                previousLevel = null
            )
        )
    }

    @Test
    fun desktopHallGatingAndDynamicScheduleArePreserved() {
        val base = InternalAffairsProtocolShapes.parseFiefState(
            CAPTURED_8246_BASE.hexBytes(),
            0x09af
        )
        val secondary = InternalAffairsProtocolShapes.parseFiefState(
            CAPTURED_8246_SECONDARY.hexBytes(),
            0x0a79
        )

        assertEquals("宫玉迎基地", base.name)
        assertEquals(13, base.buildings.size)
        assertEquals(3, base.buildings.first { it.typeId == 3 }.slotOrIndex)
        assertEquals(5, base.buildings.first { it.typeId == 3 }.rank)
        assertEquals(10, InternalAffairsProtocolShapes.buildingLevelLimit(base, 4))
        assertEquals(15, InternalAffairsProtocolShapes.buildingLevelLimit(base, 1))
        assertEquals(10 * 60 * 1_000L, InternalAffairsProtocolShapes.nextCheckDelayMillis(listOf(base, secondary)))
    }

    @Test
    fun locatesVerifiedTwentyTwoEntryTechnologyTableIn8004() {
        val payload = ByteArrayOutputStream().also { bos ->
            DataOutputStream(bos).use { out ->
                out.write(ByteArray(19) { 0x66 })
                repeat(22) { technologyId ->
                    out.writeByte(technologyId)
                    out.writeByte(if (technologyId == 5) 2 else if (technologyId == 0) 1 else 0)
                    out.writeByte(if (technologyId == 5) 0 else 2)
                    if (technologyId == 5) {
                        out.writeLong(2438)
                        out.writeLong(21586)
                        out.writeLong(123456789)
                    } else {
                        out.writeLong(-1)
                        out.writeLong(-1)
                        out.writeLong(0)
                    }
                }
                out.writeByte(0x22)
            }
        }.toByteArray()

        val states = InternalAffairsProtocolShapes.parseTechnologyStatesFrom8004(payload)

        assertEquals(22, states.size)
        assertEquals(1, states[0].level)
        assertEquals(2, states[5].level)
        assertTrue(states[5].researching)
        assertEquals(2438L, states[5].fiefId)
        assertEquals(21586L, states[5].academyInstanceId)
    }

    @Test
    fun recoveredBuildingAndTechnologyCostsMatchDesktopRuleTables() {
        assertEquals(InternalResourceCost(164300L, 348192L), InternalAffairsCostTable.building(0, 15))
        assertEquals(InternalResourceCost(108L, 271L), InternalAffairsCostTable.building(6, 2))
        assertEquals(InternalResourceCost(476062L, 0L), InternalAffairsCostTable.technology(2, 10))
        assertEquals(InternalResourceCost(0L, 15000L), InternalAffairsCostTable.technology(15, 5))
        assertEquals(InternalResourceCost(0L, 0L), InternalAffairsCostTable.technology(16, 6))
        assertEquals(InternalResourceCost(0L, 0L), InternalAffairsCostTable.technology(0, 11))
    }

    private fun String.hexBytes(): ByteArray =
        chunked(2).map { it.toInt(16).toByte() }.toByteArray()

    companion object {
        private const val CAPTURED_8200_BUILD =
            "00000000000000000a79040000000000000055e00001000000000000000000000000000000000000000000000055e00100000000000055e10101000000000000000000000000000000000000000000000055e10400000000000055e20101000000000000000000000000000000000000000000000055e20a0000000000005750010000001387000000000000019f4ffd5a20000000000000005750"
        private const val CAPTURED_8246_SECONDARY =
            "000000000000000a790100000ce4b99de4b89ae5b081e59cb000000000000000570000001f000000000000003c02000000320003190000000000000000173200000000000000001864000000000000000019031900000000000000001a3200000000000000001b6400000000000000001c010500000000000000001d0000040000000000000055e00001000000000000000000000000000000000000000000000055e00100000000000055e10101000000000000000000000000000000000000000000000055e10400000000000055e20101000000000000000000000000000000000000000000000055e20a0000000000005750010100000000000000000000000000000000000000000000005750"
        private const val CAPTURED_8246_BASE =
            "0000000000000009af0a01000fe5aeabe78e89e8bf8ee59fbae59cb0000000000000007f0000052f0000045303b105ff02000000320103190000000000000000173200000000000000001864000000000000000019031900000000000000001a3200000000000000001b6400000000000000001c010500000000000000001d0403000000c8020000000100000000010800000004000d00000000000000529f000a0000000000000000000000000000000000000000000000529f0200000000000052a0020a000000000000000000000000000000000000000000000052a00100000000000052a1010a000000000000000000000000000000000000000000000052a10c00000000000052a40102000000000000000000000000000000000000000000000052a40a00000000000054340601000000000000000000000000000000000000000000000054340400000000000054350107000000000000000000000000000000000000000000000054350500000000000054360106000000000000000000000000000000000000000000000054360600000000000054370106000000000000000000000000000000000000000000000054370900000000000054380101000000000000000000000000000000000000000000000054380800000000000054390103000000000000000000000000000000000000000000000054390b000000000000543a01010000000000000000000000000000000000000000000000543a03000000000000543b03050000000000000000000000000000000000000000000000543b07000000000000543c01070000000000000000000000000000000000000000000000543c"
    }
}
