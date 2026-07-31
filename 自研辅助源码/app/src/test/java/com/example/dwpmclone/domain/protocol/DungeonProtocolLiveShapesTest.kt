package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DungeonProtocolLiveShapesTest {
    @Test
    fun stageMappingMatchesDesktopCatalogFallback() {
        assertEquals(12, DungeonProtocolShapes.stageCount(0))
        assertEquals(2, DungeonProtocolShapes.resolveStageCode(0, 3))
        assertEquals(4, DungeonProtocolShapes.resolveStageCode(0, 4))
        assertEquals(3, DungeonProtocolShapes.resolveStageCode(1, 1))
        assertEquals(85, DungeonProtocolShapes.resolveStageCode(6, 11))
    }

    @Test
    fun prepareExpeditionAndChestPayloadsMatchDesktopProtocol() {
        val prepare = byteArrayOf(
            0x0e, 0x01,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x12, 0x34,
            -1, -1, -1, -1,
            0x00, 0x04,
            0x00, 0x02
        )
        assertArrayEquals(
            prepare,
            DungeonProtocolShapes.buildPreparePayload(listOf(0x1234), stageCode = 2)
        )
        assertArrayEquals(
            prepare + byteArrayOf(-1, -1, -1, -1, -1, -1, -1, -1, 0, 0, 0),
            DungeonProtocolShapes.buildExpeditionPayload(listOf(0x1234), stageCode = 2)
        )
        assertArrayEquals(byteArrayOf(2), DungeonProtocolShapes.buildOpenChestPayload(2))
    }

    @Test
    fun captured8930CatalogResolvesServerStageIds() {
        val catalog = DungeonProtocolShapes.parseCatalog(CAPTURED_8930.hexBytes())

        assertEquals(7, catalog.chapters.size)
        assertEquals("山贼之乱", catalog.chapters[0].name)
        assertEquals(12, catalog.chapters[0].stages.size)
        assertEquals(0, catalog.chapters[0].stages[0].stageCode)
        assertEquals(2, catalog.chapters[0].stages[2].stageCode)
        assertEquals(4, catalog.chapters[0].stages[3].stageCode)
        assertFalse(catalog.chapters[0].stages[5].available)
        assertEquals(5, DungeonProtocolShapes.resolveStageCode(catalog, 0, 5))
        assertEquals(85, DungeonProtocolShapes.resolveStageCode(catalog, 6, 11))
        assertEquals(catalog.payloadBytes, catalog.parsedBytes)
    }

    @Test
    fun capturedDungeonStateRewardLaunchAndPollShapesParse() {
        assertEquals(
            DungeonBattlePhase.IDLE,
            DungeonProtocolShapes.parseBattleState("00".hexBytes()).phase
        )
        val active = DungeonProtocolShapes.parseBattleState(
            "010000000000038f4c00".hexBytes()
        )
        assertEquals(DungeonBattlePhase.FIGHTING, active.phase)
        assertEquals(0x38f4cL, active.battleId)
        assertEquals(0, active.tailCode)
        assertEquals(
            DungeonBattlePhase.PENDING_SETTLEMENT,
            DungeonProtocolShapes.parseBattleState("03".hexBytes()).phase
        )

        val reward = DungeonProtocolShapes.parseRewardState(
            "010000000000038f4c00000500000022".hexBytes()
        )
        assertEquals(1, reward.status)
        assertEquals(0x38f4cL, reward.battleId)

        val launch = DungeonProtocolShapes.parseLaunchResponse(
            "d8001be58d95e4babae589afe69cace590afe58aa8e68890e58a9fefbc81".hexBytes()
        )
        assertTrue(launch.success)
        assertTrue(launch.message.contains("副本启动成功"))
        assertArrayEquals(
            "020000000000038f4c".hexBytes(),
            DungeonProtocolShapes.buildBattlePollPayload(firstPoll = true, battleId = 0x38f4cL)
        )
        assertArrayEquals(
            "010000000000038f4c".hexBytes(),
            DungeonProtocolShapes.buildBattlePollPayload(firstPoll = false, battleId = 0x38f4cL)
        )
    }

    private fun String.hexBytes(): ByteArray {
        require(length % 2 == 0)
        return chunked(2).map { it.toInt(16).toByte() }.toByteArray()
    }

    companion object {
        private const val CAPTURED_8930 =
            "000700000f130f010f12000ce5b1b1e8b4bce4b98be4b9b1010c00000103000101010002010100040101000501ff000600ff000700ff000800ff000900ff000a00ff000b00ff000c00ff00010f150efc0ef70009e7acace4ba8ce7aba00000020f180efe0efb000ce995bfe5ae89e4b98be4b9b10000030f1a0f000ef9000ce5be90e5b79ee4b98be4ba8900000410b1106010b0000ce4bcaae5b89de8a281e69caf0000051aaa1a931a8f0015e5ae98e6b8a1e4b98be68898efbc88e4b88aefbc890000061aaa1a941a910015e5ae98e6b8a1e4b98be68898efbc88e4b88befbc8900"
    }
}
