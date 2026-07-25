package com.example.dwpmclone.domain.protocol

import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LosslessProtocolShapesTest {
    @Test
    fun parsesRealCooldownStatusCapture() {
        val status = LosslessProtocolShapes.parseStatus(
            "000000000005909e000203000000000000003f71b000000005".hex()
        )

        assertEquals(LosslessPhase.COOLDOWN, status.phase)
        assertEquals(2, status.remainingAttempts)
        assertEquals(364_702L, status.actionTimerMillis)
        assertEquals(4_157_872L, status.cooldownMillis)
        assertEquals(5, status.reopenCost)
    }

    @Test
    fun parsesRealFailedBattleSettlementWithoutTreatingTransportAsFailure() {
        val settlement = LosslessProtocolShapes.parseSettlement(
            (
                "000019f4bf4a7da082300024e6b688e781ad3130e7baa7e585b3e58da12de58dabe585b5efbc8c" +
                    "e5a4b1e8b4a5efbc81000ae5a3b0e69c9b2b33313700650a312ee4bba4e78b90e6828c2831e7baa7" +
                    "e5bc93e5b086290ae7bb8fe9aa8cefbc9a2b3336300a322ee588abe8b58b2831e7baa7e58b87e5a3ab" +
                    "290ae7bb8fe9aa8cefbc9a2b3930300a332ee69da8e8bf8ee5b3af2831e7baa7e6ada5e5b086290ae697a0"
                ).hex()
        )

        assertTrue(settlement.success)
        assertTrue(settlement.battleFailed)
        assertEquals("消灭10级关卡-卫兵，失败！", settlement.resultText)
        assertEquals("声望+317", settlement.generalText)
        assertEquals(0x19f4bf4a7da08230L, settlement.battleId)
    }

    @Test
    fun selectAndDispatchPayloadsMatchDesktopCapture() {
        assertArrayEquals(
            "0b050000000000f7f0bf0000000000e092780000000000f935510000000000f9354f0000000000df378100000000000003a0".hex(),
            LosslessProtocolShapes.buildPreparePayload(
                listOf(0xf7f0bf, 0xe09278, 0xf93551, 0xf9354f, 0xdf3781),
                roleId = 0x3a0
            )
        )
        assertArrayEquals(
            "0b050000000000f7f0bf0000000000e092780000000000f935510000000000f9354f0000000000df378100000000000003a0ffffffffffffffff000000".hex(),
            LosslessProtocolShapes.buildExpeditionPayload(
                listOf(0xf7f0bf, 0xe09278, 0xf93551, 0xf9354f, 0xdf3781),
                roleId = 0x3a0
            )
        )

        val selectPayload = ByteArrayOutputStream().also { bytes ->
            DataOutputStream(bytes).use { out ->
                out.writeInt(1)
                out.writeUTF("选择成功")
                out.writeLong(9)
                out.writeShort(0x3011)
            }
        }.toByteArray()
        val selected = LosslessProtocolShapes.parseSelect(selectPayload)
        assertTrue(selected.success)
        assertEquals(10, selected.selectedLevel)
        assertEquals(0x3011, selected.stageId)
    }

    @Test
    fun level10GuardRequiresCatapultAfterOtherChariots() {
        val qualified = lineup("弩车", "冲车", "弓兵", "投石车", "步兵")
        val rejected = lineup("投石车", "弩车", "冲车", "弓兵", "步兵")

        assertTrue(LosslessProtocolShapes.evaluateLevel10Guard(qualified).qualified)
        assertFalse(LosslessProtocolShapes.evaluateLevel10Guard(rejected).qualified)
    }

    @Test(expected = IllegalArgumentException::class)
    fun malformedStatusFailsClosed() {
        LosslessProtocolShapes.parseStatus(ByteArray(12))
    }

    private fun lineup(vararg types: String) = LosslessLineup(
        success = true,
        status = 0,
        stageId = 0x3011,
        levelName = "10级关卡",
        stageName = "卫兵",
        enemies = types.mapIndexed { index, type ->
            LosslessEnemy(index + 1, "敌将${index + 1}", type, 100)
        }
    )

    private fun String.hex(): ByteArray =
        chunked(2).map { it.toInt(16).toByte() }.toByteArray()
}
