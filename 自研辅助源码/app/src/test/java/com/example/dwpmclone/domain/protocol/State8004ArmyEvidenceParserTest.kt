package com.example.dwpmclone.domain.protocol

import org.json.JSONArray
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream

class State8004ArmyEvidenceParserTest {
    @Test
    fun recoversCompactIdleAndWoundedArmyBlocksForEveryFief() {
        val payload = bytes(
            utf("董全基地"),
            byteArrayOf(0x01, 0x02),
            armyBlock(
                idle = listOf(10 to 735, 4 to 44),
                wounded = listOf(10 to 12, 4 to 3)
            ),
            utf("建业封地"),
            byteArrayOf(0x03),
            armyBlock(
                idle = listOf(1 to 99),
                wounded = emptyList()
            )
        )

        val rows = State8004ArmyEvidenceParser.recover(payload.toHex())

        assertEquals(3, rows.size)
        assertEquals(
            State8004ArmyRow(10, "重骑兵", 735, 12, "董全基地", 16),
            rows[0]
        )
        assertEquals("弩车", rows[1].soldierType)
        assertEquals(44, rows[1].idleCount)
        assertEquals(3, rows[1].woundedCount)
        assertEquals("建业封地", rows[2].fiefName)
        assertEquals(99, rows[2].idleCount)
        assertEquals(3, JSONArray(State8004ArmyEvidenceParser.toJson(rows)).length())
    }

    @Test
    fun rejectsCompactLookingBlockWithoutNearbyFiefEvidence() {
        val payload = armyBlock(
            idle = listOf(10 to 735),
            wounded = listOf(10 to 12)
        )

        assertTrue(State8004ArmyEvidenceParser.recover(payload.toHex()).isEmpty())
    }

    private fun armyBlock(
        idle: List<Pair<Int, Int>>,
        wounded: List<Pair<Int, Int>>
    ): ByteArray = ByteArrayOutputStream().also { output ->
        DataOutputStream(output).use {
            it.writeByte(0x1d)
            it.writeByte(idle.size)
            idle.forEach { (type, count) ->
                it.writeByte(type)
                it.writeInt(count)
            }
            it.writeByte(wounded.size)
            wounded.forEach { (type, count) ->
                it.writeByte(type)
                it.writeInt(count)
            }
        }
    }.toByteArray()

    private fun utf(value: String): ByteArray {
        val raw = value.toByteArray(Charsets.UTF_8)
        return ByteArrayOutputStream().also { output ->
            DataOutputStream(output).use {
                it.writeShort(raw.size)
                it.write(raw)
            }
        }.toByteArray()
    }

    private fun bytes(vararg values: ByteArray): ByteArray =
        ByteArrayOutputStream().also { output -> values.forEach(output::write) }.toByteArray()

    private fun ByteArray.toHex(): String =
        joinToString(separator = "") { "%02x".format(it.toInt() and 0xff) }
}
