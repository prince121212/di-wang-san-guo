package com.example.dwpmclone.domain.protocol

import org.junit.Assert.assertEquals
import org.junit.Test

class GameProtocolShapesTest {
    @Test
    fun encodeXYMatchesRecoveredSmaliExamples() {
        assertEquals("00000000", GameCoordinateCodec.encodeXY(0, 0))
        assertEquals("00000006", GameCoordinateCodec.encodeXY(0, 6))
        assertEquals("00060000", GameCoordinateCodec.encodeXY(6, 0))
        assertEquals("00060006", GameCoordinateCodec.encodeXY(6, 6))
        assertEquals("00420000", GameCoordinateCodec.encodeXY(66, 0))
        assertEquals("00ba0042", GameCoordinateCodec.encodeXY(186, 66))
        assertEquals("00ff00ff", GameCoordinateCodec.encodeXY(255, 255))
    }

    @Test
    fun buildTargetSearchUses041540PlusEncodedCoordinate() {
        assertEquals(
            "00000000000000000004154000060006",
            GameCoordinateCodec.buildTargetSearch(6, 6)
        )
    }

    @Test
    fun buildResourcePointSearchUses041542PlusEncodedCoordinate() {
        assertEquals(
            "00000000000000000004154200060006",
            GameCoordinateCodec.buildResourcePointSearch(6, 6)
        )
    }

    @Test
    fun buildRankListPreservesPassive1170Examples() {
        assertEquals(
            "000000000000000000031170000001",
            RankListShape.buildCategory(0)
        )
        assertEquals(
            "000000000000000000031170030001",
            RankListShape.buildCategory(3)
        )
        assertEquals(
            "000000000000000000031170030001",
            RankListShape.buildRawParams("030001")
        )
        assertEquals(
            "0000000000000000000311700000030001",
            RankListShape.buildCapturedWireTail(3)
        )
    }

    @Test
    fun describeRankList1170AsReadOnlyBinaryCandidateButStillRequiresAllowListAndParser() {
        val desc = GameHexDryRunParser.describe(RankListShape.buildCategory(3))

        assertEquals("1170", desc.opcodeHex)
        assertEquals(GameHexCategory.READ_ONLY_QUERY, desc.category)
        assertEquals(GameHexLengthRelation.DECLARED_EQUALS_PAYLOAD, desc.lengthRelation)
        assertEquals(true, desc.binaryCommandCandidate)
    }

    @Test
    fun buildBatchRefillTroopsPreservesPassive1229Examples() {
        assertEquals(
            "0000000000000000001112290200000000006b4dac0000000000686b99",
            BatchRefillTroopsShape.build(listOf("6b4dac", "686b99"))
        )
        assertEquals(
            "0000000000000000001112290200000000006b4dae00000000006b4d9a",
            BatchRefillTroopsShape.build(listOf("00000000006b4dae", "0x6b4d9a"))
        )
        assertEquals(
            "00000000000000000011122900000200000000006b4dac0000000000686b99",
            BatchRefillTroopsShape.buildCapturedWireTail(listOf("6b4dac", "686b99"))
        )
    }

    @Test
    fun describeBatchRefill1229AsStateChangingDryRunOnly() {
        val desc = GameHexDryRunParser.describe(BatchRefillTroopsShape.build(listOf("6b4dac", "686b99")))

        assertEquals("1229", desc.opcodeHex)
        assertEquals(0x11, desc.declaredLengthBytes)
        assertEquals(17, desc.payloadByteCount)
        assertEquals(GameHexLengthRelation.DECLARED_EQUALS_PAYLOAD, desc.lengthRelation)
        assertEquals(GameHexCategory.STATE_CHANGING_ACTION, desc.category)
        assertEquals(false, desc.binaryCommandCandidate)
    }

    @Test
    fun passiveWireDryRunPlannerBuildsObservedBatchRefillPrepareAndDispatchChain() {
        val plan = BrushYellowPassiveWireDryRunPlanner.plan(
            generalIds = listOf("6b4dac", "686b99"),
            targetWireId = "424de2"
        )

        assertEquals(listOf("00000000006b4dac", "0000000000686b99"), plan.generalIds)
        assertEquals("0000000000424de2", plan.targetWireId)
        assertEquals(
            "0000000000000000001112290200000000006b4dac0000000000686b99",
            plan.refillGameHex
        )
        assertEquals(
            "00000000000000000011122900000200000000006b4dac0000000000686b99",
            plan.refillCapturedWireTail
        )
        assertEquals(
            "0000000000000000001a15200a0200000000006b4dac0000000000686b990000000000424de2",
            plan.prepareGameHex
        )
        assertEquals(
            "0000000000000000001a152000000a0200000000006b4dac0000000000686b990000000000424de2",
            plan.prepareCapturedWireTail
        )
        assertEquals(
            "0000000000000000002515220a0200000000006b4dac0000000000686b990000000000424de2ffffffffffffffff000000",
            plan.dispatchGameHex
        )
        assertEquals(
            "00000000000000000025152200000a0200000000006b4dac0000000000686b990000000000424de2ffffffffffffffff000000",
            plan.dispatchCapturedWireTail
        )
        assertEquals(false, plan.networkSendAllowed)
        assertEquals(GameHexCategory.EXPEDITION_ACTION, GameHexDryRunParser.describe(plan.prepareGameHex).category)
        assertEquals(GameHexLengthRelation.DECLARED_EQUALS_PAYLOAD, GameHexDryRunParser.describe(plan.prepareGameHex).lengthRelation)
        assertEquals(GameHexCategory.EXPEDITION_ACTION, GameHexDryRunParser.describe(plan.dispatchGameHex).category)
        assertEquals(GameHexLengthRelation.DECLARED_EQUALS_PAYLOAD, GameHexDryRunParser.describe(plan.dispatchGameHex).lengthRelation)
    }
}
