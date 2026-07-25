package com.example.dwpmclone.data.protocol

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream

class DailyActivityE200ParserTest {
    @Test
    fun parsesTreasureProgressFromDesktopE200FieldOrder() {
        val payload = bytes(
            byteArrayOf(0x00, 0x02, 0x7f),
            utf("成功占领3个宝藏"),
            byteArrayOf(0x01, 0x02),
            utf("3/10"),
            utf("+10"),
            utf("参加竞技场"),
            utf("1/1")
        )

        val state = DailyActivityE200Parser.parse(payload)

        assertEquals("0x6200/0xe200", state.sourceOpcode)
        assertEquals(2, state.tasks.size)
        assertEquals("成功占领3个宝藏", state.treasureOccupied?.text)
        assertEquals("3/10", state.treasureOccupied?.progress)
        assertEquals(3, state.treasureOccupied?.current)
        assertEquals(10, state.treasureOccupied?.target)
        assertEquals("+10", state.treasureOccupied?.reward)
        assertTrue(JSONObject(state.toJson()).getJSONObject("treasureOccupied").getString("progress") == "3/10")
    }

    @Test
    fun doesNotInventTreasureProgressWhenTaskIsAbsent() {
        val state = DailyActivityE200Parser.parse(
            bytes(utf("参加竞技场"), utf("0/1"))
        )

        assertNull(state.treasureOccupied)
        assertEquals("0/1", state.tasks.single().progress)
    }

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
}
