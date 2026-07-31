package com.example.dwpmclone.domain.protocol

import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MilitarySnapshotProtocolShapesTest {
    @Test
    fun parsesGarrisonActionWithBattleIdAndTarget() {
        val payload = formationPayload(
            text = "【驻守】步 | 驻守在水晶矿",
            battleId = 9_640_951L,
            generalIds = listOf(0xFACF09L, 0x14C1BEL),
            targetId = 1234L,
            targetType = 2,
            targetName = "水晶矿(1级)",
            x = 136,
            y = 20,
            sectionType = 3
        )

        val snapshot = MilitarySnapshotProtocolShapes.parse(
            payload,
            generalNamesById = mapOf(0xFACF09L to "步1", 0x14C1BEL to "车1")
        )

        assertTrue(snapshot.responded)
        val action = snapshot.actions.single()
        assertEquals("驻守", action.tag)
        assertEquals("驻守", action.state)
        assertEquals(9_640_951L, action.battleId)
        assertEquals(listOf(0xFACF09L, 0x14C1BEL), action.generalIds)
        assertEquals(listOf("步1", "车1"), action.generalNames)
        assertEquals(1234L, action.targetId)
        assertEquals("水晶矿(1级)", action.targetName)
        assertEquals(136, action.x)
        assertEquals(20, action.y)
        assertEquals(3, action.sourceSection)
    }

    @Test
    fun outboundMarchIsNotMistakenForBattle() {
        val payload = formationPayload(
            text = "【攻占】攻占牧场",
            battleId = 88L,
            generalIds = listOf(7L),
            targetId = 99L,
            targetType = 2,
            targetName = "牧场(1级)",
            x = 91,
            y = 28,
            sectionType = 1,
            marchKind = 0x09,
            marchValue = 12_345L,
            eventTimeMillis = 1_800_000_000_000L
        )

        val action = MilitarySnapshotProtocolShapes.parse(payload).actions.single()

        assertEquals("出征", action.state)
        assertEquals(0x09, action.marchKind)
        assertEquals(12_345L, action.marchValue)
        assertEquals("去程", action.toJson().getString("marchKindText"))
    }

    @Test
    fun incomingRaidIsReconstructedFromFieldsThatHaveNoBracketedText() {
        val snapshot = MilitarySnapshotProtocolShapes.parse(incomingRaidPayload())

        val incoming = snapshot.actions.single()
        assertTrue(incoming.incoming)
        assertEquals("来袭", incoming.state)
        assertEquals("掠夺", incoming.tag)
        assertEquals("【掠夺】全益溪夺取利萍丰基地", incoming.text)
        assertEquals(10_564_231L, incoming.recordId)
        assertEquals("全益溪", incoming.attackerName)
        assertEquals(1, incoming.actionType)
        assertEquals("掠夺", incoming.actionTypeText)
        assertEquals("利萍丰基地", incoming.targetName)
        assertEquals(176L, incoming.targetId)
        assertEquals(71_716_750L, incoming.marchValue)
        assertEquals(1_785_337_200_415L, incoming.eventTimeMillis)
        assertEquals(1, snapshot.toJson().getInt("incomingCount"))
        assertFalse(incoming.toJson().has("battleId"))
    }

    @Test
    fun actionsUseTheSameAttentionOrderAsTheDesktopMilitaryPage() {
        val returning = formationPayload(
            text = "【返回】返回基地",
            battleId = 30L,
            generalIds = listOf(3L),
            targetId = 103L,
            targetType = 1,
            targetName = "基地",
            x = 1,
            y = 1,
            sectionType = 1,
            marchKind = 0x0D
        )
        val fighting = formationPayload(
            text = "【消灭】7级山贼战斗进行中",
            battleId = 20L,
            generalIds = listOf(2L),
            targetId = 102L,
            targetType = 3,
            targetName = "7级山贼",
            x = 2,
            y = 2,
            sectionType = 1,
            marchKind = 0x0B
        )
        val garrison = formationPayload(
            text = "【驻守】驻守在牧场",
            battleId = 10L,
            generalIds = listOf(1L),
            targetId = 101L,
            targetType = 2,
            targetName = "牧场",
            x = 3,
            y = 3,
            sectionType = 3
        )

        assertEquals(
            listOf("来袭", "战斗", "驻守", "返回"),
            MilitarySnapshotProtocolShapes.parseAll(
                listOf(returning, garrison, incomingRaidPayload(), fighting)
            ).actions.map { it.state }
        )
    }

    @Test
    fun legacyUtfAnchorShapeIsRejectedInsteadOfProducingFalseMilitaryIntel() {
        val legacy = ByteArrayOutputStream().also { output ->
            DataOutputStream(output).use { data ->
                data.writeUTF("【驻守】驻守在水晶矿")
                data.writeShort(0)
                data.writeInt(0)
                data.writeLong(789L)
                data.writeByte(1)
                data.writeLong(7L)
                data.writeByte(0)
                data.writeLong(99L)
                data.writeByte(2)
                data.writeUTF("水晶矿(1级)")
                data.writeShort(18)
                data.writeShort(22)
            }
        }.toByteArray()

        assertTrue(MilitarySnapshotProtocolShapes.parse(legacy).actions.isEmpty())
    }

    @Test
    fun realCapturedDungeonBanditAndMinePayloadsMatchComputerParser() {
        val dungeon = parsedCapturePayload(42).single()
        assertEquals("副本", dungeon.tag)
        assertEquals("战斗", dungeon.state)
        assertEquals("宦官乱政", dungeon.targetName)
        assertEquals(14, dungeon.targetType)
        assertEquals(5, dungeon.generalIds.size)

        val bandit = parsedCapturePayload(81).single()
        assertEquals("消灭", bandit.tag)
        assertEquals("出征", bandit.state)
        assertEquals("7级山贼(103,29)", bandit.targetName)
        assertEquals(32_068L, bandit.marchValue)

        val mine = parsedCapturePayload(128).single()
        assertEquals("攻占", mine.tag)
        assertEquals("出征", mine.state)
        assertEquals("牧场(1级)", mine.targetName)
        assertEquals(92 to 26, mine.x to mine.y)
        assertEquals(93_949L, mine.marchValue)
        assertEquals(1_785_059_585_543L, mine.eventTimeMillis)
    }

    @Test
    fun realCapturedEmptyPayloadIsConfirmedEmptyRatherThanParseFailure() {
        val payload = capturePayload(50)
        assertEquals(5_172, payload.size)

        val snapshot = MilitarySnapshotProtocolShapes.parse(payload)

        assertTrue(snapshot.responded)
        assertTrue(snapshot.actions.isEmpty())
    }

    @Test
    fun realCapturedTailParsesOwnedCapturedAndTroopStateWithoutUnknownBytes() {
        val idle = MilitarySnapshotProtocolShapes.parse(capturePayload(50))

        assertTrue(idle.trailingEvidenceParsed)
        assertEquals(0, idle.unparsedTailByteCount)
        assertEquals(14, idle.generalStatusRecords.size)
        assertEquals(19, idle.captiveGeneralRecords.size)
        assertEquals(6, idle.troopAssignmentCount)
        val attackBowOne = idle.generalStatusRecords.first { it["name"] == "攻弓1" }
        assertEquals("0", attackBowOne["status"])
        assertEquals("空闲", attackBowOne["statusText"])
        assertEquals("1121", attackBowOne["currentSoldierCount"])
        assertEquals("强弩兵", attackBowOne["soldierType"])
        val captive = idle.captiveGeneralRecords.first { it["name"] == "樊星" }
        assertEquals(captive.toString(), "3", captive["status"])
        assertEquals("被俘", captive["statusText"])
        assertEquals("205", captive["captureFiefId"])
        assertEquals("利萍丰基地", captive["captureFiefName"])

        val dungeon = MilitarySnapshotProtocolShapes.parse(capturePayload(42))
        assertEquals(
            listOf(MilitaryBattleReference(9_005_825L, 0)),
            dungeon.activeBattleReferences
        )
        assertEquals(
            "6",
            dungeon.generalStatusRecords.first { it["name"] == "攻弓1" }["status"]
        )
        assertEquals(0, dungeon.unparsedTailByteCount)
    }

    private fun formationPayload(
        text: String,
        battleId: Long,
        generalIds: List<Long>,
        targetId: Long,
        targetType: Int,
        targetName: String,
        x: Int,
        y: Int,
        sectionType: Int,
        marchKind: Int = 0x17,
        marchValue: Long = 0L,
        eventTimeMillis: Long = 1_800_000_000_000L
    ): ByteArray = ByteArrayOutputStream().also { output ->
        DataOutputStream(output).use { data ->
            data.writeShort(0) // header pairs
            data.writeByte(1) // section count
            data.writeByte(sectionType)
            data.writeShort(1) // descriptor count
            data.writeUTF(text)
            data.writeShort(1) // descriptor value count
            data.writeShort(0) // descriptor -> record zero
            data.writeShort(1) // record count
            data.writeLong(battleId)
            data.writeByte(generalIds.size)
            generalIds.forEach {
                data.writeLong(it)
                data.writeByte(0)
            }
            data.writeLong(targetId)
            data.writeByte(targetType)
            data.writeUTF(targetName)
            data.writeShort(x)
            data.writeShort(y)
            if (sectionType == 1) {
                data.writeByte(marchKind)
                data.writeInt(marchValue.toInt())
                data.writeLong(eventTimeMillis)
            } else {
                data.writeLong(eventTimeMillis)
            }
        }
    }.toByteArray()

    private fun incomingRaidPayload(): ByteArray = ByteArrayOutputStream().also { output ->
        DataOutputStream(output).use { data ->
            data.writeShort(3)
            listOf(1 to 0, 1 to 1, 2 to 0).forEach { (kind, value) ->
                data.writeByte(kind)
                data.writeShort(value)
            }
            data.writeByte(3)

            data.writeByte(1)
            data.writeShort(0)
            data.writeShort(0)

            data.writeByte(2)
            data.writeShort(1)
            data.writeUTF("")
            data.writeShort(1)
            data.writeLong(0x18DC27L)
            data.writeShort(0)
            data.writeShort(50)
            data.writeShort(1)
            data.writeShort(0)
            data.writeShort(1)
            data.writeLong(10_564_231L)
            data.writeUTF("全益溪")
            data.writeByte(1)
            data.writeUTF("利萍丰基地")
            data.writeLong(176L)
            data.writeInt(71_716_750)
            data.writeLong(1_785_337_200_415L)

            data.writeByte(3)
            data.writeShort(0)
            data.writeShort(0)
        }
    }.toByteArray()

    private fun parsedCapturePayload(flow: Int): List<MilitarySnapshotAction> =
        MilitarySnapshotProtocolShapes.parse(capturePayload(flow)).actions

    private fun capturePayload(flow: Int): ByteArray {
        val root = listOf(
            File("../ctf_out/passive_pcap_hotspot_20260726_173635"),
            File("../../ctf_out/passive_pcap_hotspot_20260726_173635"),
            File("ctf_out/passive_pcap_hotspot_20260726_173635")
        ).firstOrNull(File::isDirectory)
            ?: error("军情真实抓包目录缺失")
        val response = File(root, "live_analyzed/${flow.toString().padStart(3, '0')}/resp.bin")
            .readBytes()
        DataInputStream(response.inputStream()).use { input ->
            val outer = input.readUnsignedByte()
            repeat(outer) {
                val inner = input.readUnsignedByte()
                repeat(inner) {
                    input.readLong()
                    input.readLong()
                    val obfuscated = input.readUnsignedByte()
                    val length = input.readInt()
                    val opcode = input.readUnsignedShort()
                    input.readUnsignedByte()
                    val payload = ByteArray(length).also(input::readFully)
                    check(obfuscated == 0) { "测试抓包 payload 使用了未支持的响应混淆" }
                    if (opcode == 0x8600) return payload
                }
            }
        }
        error("flow $flow 未找到 0x8600")
    }
}
