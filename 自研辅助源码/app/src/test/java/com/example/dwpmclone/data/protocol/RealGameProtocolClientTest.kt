package com.example.dwpmclone.data.protocol

import com.example.dwpmclone.domain.protocol.GameHexAlignment
import com.example.dwpmclone.domain.protocol.GameHexCategory
import com.example.dwpmclone.domain.protocol.GameHexLengthRelation
import com.example.dwpmclone.domain.protocol.GameCoordinateCodec
import com.example.dwpmclone.domain.protocol.BatchRefillTroopsShape
import com.example.dwpmclone.domain.protocol.RankListShape
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream

class RealGameProtocolClientTest {
    private val client = RealGameProtocolClient()

    @Test
    fun parseAreaLineReadsPassportFields() {
        val line = "1`351`周年服351区(新服)`http://game.example`http://res.example`1660606`1660000`open`http://update`flag`client`qzone_351"

        val area = client.parseAreaLine(line)

        assertNotNull(area)
        assertEquals("周年服351区(新服)", area!!.areaName)
        assertEquals("qzone_351", area.serverKey)
        assertEquals("http://game.example", area.serverUrl)
    }

    @Test
    fun selectAreaSupportsNameAndServerKey() {
        val areas = listOf(
            client.parseAreaLine("1`350`周年服350区`http://g350`http://r`1`1`open`u`f`c`qzone_350")!!,
            client.parseAreaLine("1`351`周年服351区(新服)`http://g351`http://r`1`1`open`u`f`c`qzone_351")!!
        )

        assertEquals("qzone_351", client.selectArea(areas, "周年服351区").serverKey)
        assertEquals("周年服350区", client.selectArea(areas, "qzone_350").areaName)
    }

    @Test
    fun parse8004HeadReadsRoleStatePrefix() {
        val payload = packet8004Head()

        val state = client.parse8004Head(payload, "unit-test")

        assertEquals(10001L, state.roleId)
        assertEquals("测试君主", state.roleName)
        assertEquals(42, state.level)
        assertEquals(123456L, state.copper)
        assertEquals(654321L, state.food)
        assertEquals(88, state.copperPerHour)
        assertEquals(99, state.foodPerHour)
        assertEquals(5, state.resourcePointCurrent)
        assertEquals(8, state.resourcePointCap)
        assertEquals("unit-test", state.sourceOpcode)
        assertEquals(payload.size, state.payloadByteCount)
        assertEquals(state.payloadByteCount - state.parsedHeadByteCount, state.tailByteCount)
    }

    @Test
    fun parse8004HeadPreservesRawPayloadAndTailEvidenceForLaterParserCalibration() {
        val tail = "id=0000000000000007|name=赵云|status=0|tili=49".toByteArray(Charsets.UTF_8)
        val payload = packet8004Head(tail)

        val state = client.parse8004Head(payload, "tail-test")

        assertEquals(payload.size, state.payloadByteCount)
        assertEquals(tail.size, state.tailByteCount)
        assertEquals(payload.joinToString(separator = "") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }, state.payloadHex)
        assertEquals(tail.joinToString(separator = "") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }, state.tailHex)
        assertEquals(true, state.tailUtf8Preview.contains("name"))
        assertEquals(true, state.tailUtf8Preview.contains("赵云"))
    }

    @Test
    fun persisted8004HexRecoversLimitsWithoutNetwork() {
        val payload = packet8004Head()
        val hex = payload.joinToString(separator = "") {
            (it.toInt() and 0xff).toString(16).padStart(2, '0')
        }

        val state = client.parsePersisted8004HeadHex(hex)

        assertEquals(7, state.fiefLimit)
        assertEquals(12, state.generalLimit)
        assertEquals(5, state.resourcePointCurrent)
        assertEquals(8, state.resourcePointCap)
        assertEquals("persisted/0x8004", state.sourceOpcode)
    }

    @Test
    fun parse8104InventoryReadsItemStacksAndResolvesScriptItemNames() {
        val payload = (
            "0000000000000000000000000000" + // 14-byte reserved head
                "0032" + // capacity 50
                "0002" + // two item stacks
                "000900050000000000000000" + // item 9 传音符 x5
                "001600010000000000000000" + // item 22 鲁公手册 x1
                "01f4000a05" // unparsed tail kept as evidence
            ).hexToBytesForTest()

        val state = client.parse8104Inventory(payload, "unit-0x8104")

        assertEquals(50, state.capacity)
        assertEquals(2, state.itemCount)
        assertEquals("unit-0x8104", state.sourceOpcode)
        assertEquals(42, state.parsedItemByteCount)
        assertEquals("01f4000a05", state.tailHex)
        assertEquals(9, state.items[0].itemId)
        assertEquals("传音符", state.items[0].name)
        assertEquals(5, state.items[0].count)
        assertEquals("scriptItem.sc", state.items[0].nameSource)
        assertEquals(22, state.items[1].itemId)
        assertEquals("鲁公手册", state.items[1].name)
    }


    @Test
    fun describeRecoveredGameHexMarksTargetSearchAsReadOnlyBinaryCandidate() {
        val desc = client.describeRecoveredGameHex("00000000000000000004154000060006")

        assertEquals("000000000000000000", desc.prefixHex)
        assertEquals("04", desc.declaredLengthHex)
        assertEquals(4, desc.declaredLengthBytes)
        assertEquals("1540", desc.opcodeHex)
        assertEquals("00060006", desc.payloadHex)
        assertEquals(4, desc.payloadByteCount)
        assertEquals(GameHexAlignment.VALID_HEX_BYTES, desc.alignment)
        assertEquals(GameHexLengthRelation.DECLARED_EQUALS_PAYLOAD, desc.lengthRelation)
        assertEquals(GameHexCategory.READ_ONLY_QUERY, desc.category)
        assertEquals(true, desc.binaryCommandCandidate)
    }

    @Test
    fun describeRecoveredGameHexKeepsStateChangingDailyActionDryRunOnly() {
        val desc = client.describeRecoveredGameHex("000000000000000000006200")

        assertEquals("6200", desc.opcodeHex)
        assertEquals(GameHexCategory.STATE_CHANGING_ACTION, desc.category)
        assertEquals(false, desc.binaryCommandCandidate)
        assertEquals(GameHexLengthRelation.DECLARED_EQUALS_PAYLOAD, desc.lengthRelation)
    }

    @Test
    fun describeRecoveredGameHexFlagsBrushYellowExpeditionAsNativeWrapperBlocked() {
        val desc = client.describeRecoveredGameHex(
            "0000000000000000001a15200a02000000000000000100000000000000020000000000000065"
        )

        assertEquals("1520", desc.opcodeHex)
        assertEquals(GameHexCategory.EXPEDITION_ACTION, desc.category)
        assertEquals(false, desc.binaryCommandCandidate)
        assertEquals(GameHexLengthRelation.DECLARED_EQUALS_PAYLOAD, desc.lengthRelation)
    }

    @Test
    fun describeRecoveredGameHexRejectsNonHexInput() {
        val desc = client.describeRecoveredGameHex("not-a-hex")

        assertEquals(GameHexAlignment.NON_HEX, desc.alignment)
        assertEquals(GameHexLengthRelation.UNPARSEABLE, desc.lengthRelation)
        assertEquals(false, desc.binaryCommandCandidate)
    }

    @Test
    fun planRecoveredReadOnlyGameHexBuildsTargetSearchBinaryRequestButKeepsNetworkClosed() {
        val plan = client.planRecoveredReadOnlyGameHex(GameCoordinateCodec.buildTargetSearch(6, 6), dm = 1883L)

        assertEquals(0x1540, plan.opcode)
        assertEquals("1540", plan.opcodeHex)
        assertEquals("00060006", plan.payloadHex)
        assertEquals(4, plan.payloadByteCount)
        assertEquals(true, plan.canBuildCurrentBinaryRequest)
        assertEquals(false, plan.networkSendAllowed)
        assertNotNull(plan.currentBinaryRequestHex)
        assertEquals(
            true,
            plan.currentBinaryRequestHex!!.endsWith(
                "000000000000075b" + // dm
                    "0000000000000000" + // gm
                    "0004" + // payload size
                    "1540" + // opcode
                    "0000" + // empty signature
                    "00060006" // recovered XY payload
            )
        )
    }

    @Test
    fun planRecoveredReadOnlyGameHexBuildsMineSearchBinaryRequestButKeepsNetworkClosed() {
        val plan = client.planRecoveredReadOnlyGameHex(GameCoordinateCodec.buildResourcePointSearch(6, 6), dm = 1L)

        assertEquals(0x1542, plan.opcode)
        assertEquals("1542", plan.opcodeHex)
        assertEquals(true, plan.canBuildCurrentBinaryRequest)
        assertEquals(false, plan.networkSendAllowed)
        assertEquals(
            true,
            plan.currentBinaryRequestHex!!.endsWith(
                "0000000000000001" +
                    "0000000000000000" +
                    "0004" +
                    "1542" +
                    "0000" +
                    "00060006"
            )
        )
    }

    @Test
    fun planRecoveredReadOnlyGameHexRejectsReadOnlyOpcodeOutsideAllowList() {
        val plan = client.planRecoveredReadOnlyGameHex("0000000000000000000810160000000000000001", dm = 1L)

        assertEquals(0x1016, plan.opcode)
        assertEquals(GameHexCategory.READ_ONLY_QUERY, plan.descriptor.category)
        assertEquals(true, plan.descriptor.binaryCommandCandidate)
        assertEquals(false, plan.canBuildCurrentBinaryRequest)
        assertEquals(null, plan.currentBinaryRequestHex)
        assertEquals(true, plan.blocker.contains("尚未进入真机候选白名单"))
    }

    @Test
    fun planRecoveredReadOnlyGameHexKeepsRank1170UnsentUntilAllowListAndParserAreCalibrated() {
        val plan = client.planRecoveredReadOnlyGameHex(RankListShape.buildCategory(3), dm = 1L)

        assertEquals(0x1170, plan.opcode)
        assertEquals(GameHexCategory.READ_ONLY_QUERY, plan.descriptor.category)
        assertEquals(GameHexLengthRelation.DECLARED_EQUALS_PAYLOAD, plan.descriptor.lengthRelation)
        assertEquals(true, plan.descriptor.binaryCommandCandidate)
        assertEquals(false, plan.canBuildCurrentBinaryRequest)
        assertEquals(null, plan.currentBinaryRequestHex)
        assertEquals(false, plan.networkSendAllowed)
        assertEquals(true, plan.blocker.contains("尚未进入真机候选白名单"))
    }

    @Test
    fun planRecoveredReadOnlyGameHexDoesNotBuildActionRequest() {
        val plan = client.planRecoveredReadOnlyGameHex("000000000000000000006200", dm = 1L)

        assertEquals(0x6200, plan.opcode)
        assertEquals(GameHexCategory.STATE_CHANGING_ACTION, plan.descriptor.category)
        assertEquals(false, plan.canBuildCurrentBinaryRequest)
        assertEquals(null, plan.currentBinaryRequestHex)
    }

    @Test
    fun planRecoveredReadOnlyGameHexRejectsBatchRefill1229AsStateChangingAction() {
        val plan = client.planRecoveredReadOnlyGameHex(
            BatchRefillTroopsShape.build(listOf("6b4dac", "686b99")),
            dm = 1L
        )

        assertEquals(0x1229, plan.opcode)
        assertEquals(GameHexCategory.STATE_CHANGING_ACTION, plan.descriptor.category)
        assertEquals(GameHexLengthRelation.DECLARED_EQUALS_PAYLOAD, plan.descriptor.lengthRelation)
        assertEquals(false, plan.canBuildCurrentBinaryRequest)
        assertEquals(null, plan.currentBinaryRequestHex)
        assertEquals(false, plan.networkSendAllowed)
    }

    @Test
    fun executeRecoveredReadOnlyGameHexKeepsLiveGateClosedByDefault() {
        val result = client.executeRecoveredReadOnlyGameHex(
            gameHttp = "http://127.0.0.1/should-not-be-called",
            dm = 1L,
            gameHex = GameCoordinateCodec.buildTargetSearch(6, 6)
        )

        assertEquals(false, result.networkSendAttempted)
        assertEquals(false, result.success)
        assertEquals("READ_ONLY_LIVE_GATE_DISABLED", result.code)
        assertEquals(0x1540, result.plan.opcode)
        assertEquals(true, result.plan.canBuildCurrentBinaryRequest)
    }

    @Test
    fun executeRecoveredReadOnlyGameHexRejectsStateChangingActionBeforeNetworkEvenWithGate() {
        val result = client.executeRecoveredReadOnlyGameHex(
            gameHttp = "http://127.0.0.1/should-not-be-called",
            dm = 1L,
            gameHex = "000000000000000000006200",
            liveGate = true
        )

        assertEquals(false, result.networkSendAttempted)
        assertEquals(false, result.success)
        assertEquals("READ_ONLY_GAME_HEX_NOT_ALLOWED", result.code)
        assertEquals(GameHexCategory.STATE_CHANGING_ACTION, result.plan.descriptor.category)
    }

    @Test
    fun executeRecoveredReadOnlyGameHexRequiresGameHttpWhenGateEnabled() {
        val result = client.executeRecoveredReadOnlyGameHex(
            gameHttp = "",
            dm = 1L,
            gameHex = GameCoordinateCodec.buildResourcePointSearch(6, 6),
            liveGate = true
        )

        assertEquals(false, result.networkSendAttempted)
        assertEquals(false, result.success)
        assertEquals("READ_ONLY_GAME_HTTP_MISSING", result.code)
        assertEquals(0x1542, result.plan.opcode)
    }

    private fun packet8004Head(tail: ByteArray = ByteArray(0)): ByteArray {
        val bos = ByteArrayOutputStream()
        val out = DataOutputStream(bos)
        fun utf(value: String) {
            val bytes = value.toByteArray(Charsets.UTF_8)
            out.writeShort(bytes.size)
            out.write(bytes)
        }
        out.writeByte(0) // status1
        out.writeByte(0) // status2
        out.writeLong(1_720_000_000_000L)
        out.writeLong(10001L)
        utf("测试君主")
        out.writeByte(0)
        out.writeByte(42)
        out.writeLong(123456L)
        out.writeLong(654321L)
        out.writeLong(0L)
        out.writeByte(0)
        out.writeShort(0)
        out.writeByte(0)
        out.writeLong(2000L)
        out.writeLong(1000L)
        out.writeLong(3000L)
        out.writeLong(0L)
        out.writeByte(0)
        out.writeInt(88)
        out.writeInt(99)
        out.writeLong(0L)
        out.writeLong(0L)
        out.writeLong(111L)
        out.writeLong(222L)
        out.writeByte(7)
        out.writeByte(12)
        out.writeByte(5)
        out.writeByte(8)
        out.write(tail)
        return bos.toByteArray()
    }

    private fun String.hexToBytesForTest(): ByteArray {
        val clean = filter { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }
        require(clean.length % 2 == 0)
        return ByteArray(clean.length / 2) { index ->
            clean.substring(index * 2, index * 2 + 2).toInt(16).toByte()
        }
    }
}
