package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.data.protocol.BrushYellowDispatchPayloadBuilder
import com.example.dwpmclone.domain.model.MapCoordinate
import com.example.dwpmclone.domain.model.ShuaHuangTargetFilter
import com.example.dwpmclone.domain.model.ShuaHuangTargetFilterPolicy
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class BrushYellowProtocolParityFixtureTest {
    private val contract by lazy {
        AssistantBehaviorContract.fromJson(repositoryFile("assistant_behavior_contract.json").readText())
    }

    @Test
    fun actionTypeAndPayloadsMatchSharedFixture() {
        val fixture = fixture("brushYellowActionType3")
        val expected = fixture.getJSONObject("expected")
        val ids = fixture.getJSONArray("generalIdHexChunks").let { array ->
            (0 until array.length()).map(array::getString)
        }

        val payloads = BrushYellowDispatchPayloadBuilder.buildBrushYellowPayloads(
            ids,
            fixture.getString("targetIdHex"),
            contract.brushYellow.actionType
        )

        assertEquals(expected.getInt("actionType"), payloads.variant)
        assertEquals(expected.getString("prepareGameHex"), payloads.preparePayload)
        assertEquals(expected.getString("dispatchGameHex"), payloads.expeditionPayload)
    }

    @Test
    fun canonicalGridOrderMatchesSharedFixture() {
        val fixture = fixture("brushYellowCanonicalGridCenter100x30")
        val center = fixture.getJSONObject("center")
        val expected = fixture.getJSONArray("expectedCoordinates").let { rows ->
            (0 until rows.length()).map { index ->
                rows.getJSONArray(index).let { MapCoordinate(it.getInt(0), it.getInt(1)) }
            }
        }

        val actual = RecoveredMapScanPlanner.nearbyRequests(
            RecoveredSearchKind.TARGET_041540,
            MapCoordinate(center.getInt("x"), center.getInt("y")),
            fixture.getInt("limit"),
            contract.mapSearch
        ).map { it.coordinate }

        assertEquals(expected, actual)
        assertTrue(actual.all { it.x % contract.mapSearch.world.step == 0 })
        assertTrue(actual.all { it.y % contract.mapSearch.world.step == 0 })
    }

    @Test
    fun positiveBattleIdAndSoftRejectMatchSharedFixture() {
        val fixture = fixture("brushYellowDispatchReceipts")
        val success = BrushYellowDispatchResponseParser.parseHex(
            fixture.getString("successResponseHex"),
            contract.expedition
        )
        val rejected = BrushYellowDispatchResponseParser.parseHex(
            fixture.getString("softRejectResponseHex"),
            contract.expedition
        )

        assertTrue(success.success == true)
        assertEquals(fixture.getLong("expectedBattleId"), success.battleId)
        assertFalse(rejected.success == true)
    }

    @Test
    fun exactSelectedLevelsMatchSharedFixture() {
        val fixture = fixture("brushYellowExactLevels")
        val levels = fixture.getJSONArray("selectedLevels").let { array ->
            (0 until array.length()).map(array::getInt).toSet()
        }
        val filter = ShuaHuangTargetFilter(levels = levels)
        val targets = fixture.getJSONArray("targets")

        for (index in 0 until targets.length()) {
            val target = targets.getJSONObject(index)
            assertEquals(
                "target=${target.getLong("id")}",
                target.getBoolean("matches"),
                ShuaHuangTargetFilterPolicy.matchesLevel(target.getInt("level"), filter)
            )
        }
    }

    private fun fixture(name: String): JSONObject = JSONObject(
        repositoryFile("protocol_parity_fixtures.json").readText()
    ).getJSONObject("fixtures").getJSONObject(name)

    private fun repositoryFile(name: String): File = listOf(
        File("../shared_core/$name"),
        File("../../shared_core/$name"),
        File("shared_core/$name")
    ).firstOrNull(File::exists) ?: error("shared_core/$name is missing")
}
