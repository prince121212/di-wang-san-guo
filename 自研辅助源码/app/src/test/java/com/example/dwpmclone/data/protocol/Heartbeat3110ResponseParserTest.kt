package com.example.dwpmclone.data.protocol

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream

class Heartbeat3110ResponseParserTest {
    @Test
    fun parsesRealCapturedA110BroadcastPayload() {
        val captured = "0100000000000c319d000000000013aebc000003ee000002c300000000000003fc000000000000000000000002433fa00205000000000826554906000000000f446bb000010000000000064e780002006de5908de5b0862d2de5bca0e88b9ee8a2abe4bf98efbc8ce58d97e6a59a28e6a59a29e59bbde6b091e8b5b6e8b7afe4babaefbc9ce7a59ee5b7a5efbc9e28e794b73939e7baa729e59ca8e68898e69697e4b8ade4bf98e8998fe4ba86e5908de5b0862d2de5bca0e88b9ee3808200000000000000019f3d032314ffffffff0000010000000000000000000000000101ffffffffffffffffffffffffffffffff000100010200000000000007550000000000000000075d0000000000000000000400000000004964680000000000004a7d1f0000000000004ab9910000000000004ac947000000000000019f3d0365010000030000360f1300060001000003000300000200000100000000000000000000000001f4ff000000000000019f1da85c1c00"

        val parsed = Heartbeat3110ResponseParser.parse(captured)

        assertEquals(799_133L, parsed.copper)
        assertEquals(1_289_916L, parsed.food)
        assertEquals(1, parsed.broadcasts.size)
        assertTrue(parsed.broadcasts.single().contains("名将--张苞被俘"))
        assertTrue(parsed.broadcasts.single().contains("在战斗中俘虏了名将--张苞"))
    }

    @Test
    fun parsesConfirmedResourcesAndLengthPrefixedBroadcast() {
        val text = "名将--张苞被俘，南楚国民在战斗中俘虏了名将--张苞。"
        val payload = ByteArrayOutputStream().also { bos ->
            DataOutputStream(bos).use { out ->
                out.writeByte(1)
                out.writeLong(799_133L)
                out.writeLong(1_281_724L)
                out.write(ByteArray(62))
                val encoded = text.toByteArray(Charsets.UTF_8)
                out.writeShort(encoded.size)
                out.write(encoded)
            }
        }.toByteArray()

        val parsed = Heartbeat3110ResponseParser.parse(payload.toHex())

        assertEquals(799_133L, parsed.copper)
        assertEquals(1_281_724L, parsed.food)
        assertEquals(listOf(text), parsed.broadcasts)
        assertFalse(parsed.sessionInvalid)
    }

    @Test
    fun detectsCapturedSessionInvalidTailWithoutInventingResources() {
        val parsed = Heartbeat3110ResponseParser.parse("0101aabbccfffc0000")

        assertTrue(parsed.sessionInvalid)
        assertEquals(null, parsed.copper)
        assertEquals(null, parsed.food)
    }

    @Test
    fun mergesNewBroadcastsIntoDesktopMilitaryIntelShape() {
        val existing = """{"events":[{"timeText":"11:59:00","text":"赵云返回封地","state":"返回"}]}"""
        val snapshot = Heartbeat3110Snapshot(
            copper = 1,
            food = 2,
            broadcasts = listOf("蜀汉在县城陈仓击败南楚，国王刘备奋力守城。"),
            sessionInvalid = false,
            payloadHex = ""
        )

        val json = JSONObject(
            Heartbeat3110ResponseParser.mergeMilitaryIntel(existing, snapshot, 1_788_000_000_000L)
        )

        assertEquals("0x3110/0xa110", json.getString("sourceOpcode"))
        assertEquals(2, json.getJSONArray("events").length())
        assertTrue(json.getJSONArray("events").getJSONObject(1).getBoolean("national"))
    }

    private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it.toInt() and 0xff) }
}
