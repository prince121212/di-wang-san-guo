package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.MapCoordinate
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File

class TargetSearchResponseParserTest {
    @Test
    fun parsesPipeSeparated041540TargetRecords() {
        val response = listOf(
            "000000000065030005000b0016E9BB84E5B7BE",
            "0000000000660400060021002cE5B1B1E8B4BC"
        ).joinToString("|")

        val targets = TargetSearchResponseParser.parse(response)

        assertEquals(2, targets.size)
        assertEquals(101L, targets[0].id)
        assertEquals("黄巾", targets[0].type)
        assertEquals(MapCoordinate(11, 22), targets[0].coordinate)
        assertEquals("3", targets[0].raw["rank"])
        assertEquals("000000000065", targets[0].raw["idHex"])
        assertEquals(102L, targets[1].id)
        assertEquals("山贼", targets[1].type)
        assertEquals(MapCoordinate(33, 44), targets[1].coordinate)
        assertEquals("4", targets[1].raw["rank"])
    }

    @Test
    fun parsesCommanderRankNamesFromRecoveredMarkers() {
        val response = listOf(
            "00000000020100000000420042E6B8A0E5B885",
            "00000000020200000000480048E4B8BBE5B086"
        ).joinToString("|")

        val targets = TargetSearchResponseParser.parse(response)

        assertEquals("渠帅", targets[0].type)
        assertEquals("11", targets[0].raw["rank"])
        assertEquals("主将", targets[1].type)
        assertEquals("12", targets[1].raw["rank"])
    }

    @Test
    fun treatsUnrankedShanZeiAsLevelOneForBrushYellowFilter() {
        val response = "00000000020300000000480048E5B1B1E8B4BC"

        val target = TargetSearchResponseParser.parse(response).single()

        assertEquals("山贼", target.type)
        assertEquals("1", target.raw["rank"])
    }

    @Test
    fun parsesCompleteStructured8540WithDesktopFieldOrderAndRealUnits() {
        val fixture = sharedFixture()
        val response = fixture.getString("responseHex")
        val expected = fixture.getJSONObject("expected")

        val target = TargetSearchResponseParser.parse(response).single()

        assertEquals(expected.getLong("id"), target.id)
        assertEquals(expected.getString("kind"), target.type)
        assertEquals(MapCoordinate(expected.getInt("x"), expected.getInt("y")), target.coordinate)
        assertEquals(expected.getInt("level").toString(), target.raw["rank"])
        assertEquals(expected.getString("compositionCode"), target.raw["compositionCode"])
        assertEquals(expected.getString("compositionSource"), target.raw["compositionSource"])
        assertEquals(expected.getInt("resource1").toString(), target.raw["resource1"])
        assertEquals(expected.getInt("resource2").toString(), target.raw["resource2"])
        assertEquals("4,5", target.raw["lootIds"])
        assertEquals("10,11,12,13", target.raw["unitSoldierTypeCodes"])
        assertEquals("1200,900,800,700", target.raw["unitSoldierCounts"])
        assertEquals("8540-structured", target.raw["source"])
        assertEquals("0000000000464371000A31E7BAA7E5B1B1E8B4BC", target.raw["rawRecord"])
    }

    @Test
    fun partialStructured8540DoesNotInventCompositionFromLevel() {
        val response =
            "00bb003801" +
                "0000000000464371" + utfHex("1级山贼") +
                "033601009d002a" + utfHex("一些资源,") +
                "0000002f00000074"

        val target = TargetSearchResponseParser.parse(response).single()

        assertEquals(MapCoordinate(157, 42), target.coordinate)
        assertEquals("", target.raw["compositionCode"])
        assertEquals("unavailable", target.raw["compositionSource"])
        assertEquals("8540-structured-partial", target.raw["source"])
    }

    @Test
    fun parsesConcatenated041540TargetRecordsWithoutSeparators() {
        val response =
            "000000000301030005000b0016E9BB84E5B7BE" +
                "0000000003020400060021002cE5B1B1E8B4BC"

        val targets = TargetSearchResponseParser.parse(response)

        assertEquals(2, targets.size)
        assertEquals(0x301L, targets[0].id)
        assertEquals("黄巾", targets[0].type)
        assertEquals(MapCoordinate(11, 22), targets[0].coordinate)
        assertEquals(0x302L, targets[1].id)
        assertEquals("山贼", targets[1].type)
        assertEquals(MapCoordinate(33, 44), targets[1].coordinate)
    }

    @Test
    fun parsesRecoveredMainMarshalMarkersAsRank13Targets() {
        val response = listOf(
            "00000000040100000000500051E4B8BBE5B885",
            "00000000040200000000520053E4B8BBE5B8A5"
        ).joinToString("|")

        val targets = TargetSearchResponseParser.parse(response)

        assertEquals(2, targets.size)
        assertEquals("主帅", targets[0].type)
        assertEquals("13", targets[0].raw["rank"])
        assertEquals(MapCoordinate(80, 81), targets[0].coordinate)
        assertEquals("主帅", targets[1].type)
        assertEquals("13", targets[1].raw["rank"])
        assertEquals(MapCoordinate(82, 83), targets[1].coordinate)
    }

    private fun utfHex(text: String): String {
        val bytes = text.toByteArray(Charsets.UTF_8)
        return bytes.size.toString(16).padStart(4, '0') +
            bytes.joinToString(separator = "") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }
    }

    private fun sharedFixture(): JSONObject {
        val file = listOf(
            File("../shared_core/protocol_parity_fixtures.json"),
            File("../../shared_core/protocol_parity_fixtures.json"),
            File("shared_core/protocol_parity_fixtures.json")
        ).firstOrNull(File::exists)
            ?: error("shared_core/protocol_parity_fixtures.json is missing")
        return JSONObject(file.readText())
            .getJSONObject("fixtures")
            .getJSONObject("targetSearch8540Complete")
    }
}
