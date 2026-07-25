package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.MapCoordinate
import com.example.dwpmclone.domain.model.MineType
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ResourcePointSearchResponseParserTest {
    @Test
    fun parses041542ResourcePointBaseRecords() {
        val response = listOf(
            "0000000001010101000b0016010002D00101000000270F",
            "00000000010202020021002c000002D0020200000022B8"
        ).joinToString("")

        val mines = ResourcePointSearchResponseParser.parse(response)

        assertEquals(2, mines.size)
        assertEquals(0x101L, mines[0].id)
        assertEquals(MineType.GOLD, mines[0].mineType)
        assertEquals(1, mines[0].level)
        assertEquals(MapCoordinate(11, 22), mines[0].coordinate)
        assertTrue(mines[0].isEmpty)
        assertEquals(0, mines[0].defenseCount)
        assertEquals("01", mines[0].raw["kindCode"])
        assertEquals("0100", mines[0].raw["statusHex"])
        assertEquals("041542-response-parser", mines[0].raw["source"])

        assertEquals(0x102L, mines[1].id)
        assertEquals(MineType.SILVER, mines[1].mineType)
        assertEquals(2, mines[1].level)
        assertEquals(MapCoordinate(33, 44), mines[1].coordinate)
        assertEquals(false, mines[1].isEmpty)
        assertEquals("0000", mines[1].raw["statusHex"])
    }

    @Test
    fun parsePointsKeepsRawRecordAndDetail() {
        val response = "00000000010A0A0300420048010002D123030000000ABC"

        val point = ResourcePointSearchResponseParser.parsePoints(response).single()

        assertEquals("00000000010A", point.idHex)
        assertEquals("0A", point.kindCode)
        assertEquals("镔铁矿", point.kind)
        assertEquals(MineType.BIN_TIE, point.mineType)
        assertEquals(3, point.rank)
        assertEquals(MapCoordinate(66, 72), point.coordinate)
        assertEquals("02D123030000000ABC", point.detail)
        assertEquals("0100", point.statusHex)
    }

    @Test
    fun skipsUnknownMineKindCodeInsteadOfMisclassifyingAsGold() {
        val response = "0000000001FF0F01000b0016010002D00101000000270F"

        val mines = ResourcePointSearchResponseParser.parse(response)

        assertTrue(mines.isEmpty())
    }
}
