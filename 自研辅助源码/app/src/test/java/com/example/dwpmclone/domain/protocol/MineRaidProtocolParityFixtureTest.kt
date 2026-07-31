package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.MapCoordinate
import com.example.dwpmclone.domain.model.MineConfig
import com.example.dwpmclone.domain.model.MineType
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class MineRaidProtocolParityFixtureTest {
    private val contract by lazy {
        AssistantBehaviorContract.fromJson(repositoryFile("assistant_behavior_contract.json").readText())
    }

    @Test
    fun mineActionTypeAndPayloadsMatchSharedFixture() {
        val fixture = fixture("mineActionType2")
        val expected = fixture.getJSONObject("expected")
        val ids = fixture.longList("generalIds")
        val targetId = fixture.getLong("targetId")
        val prepare = MineProtocolShapes.buildPreparePayload(ids, targetId, contract.mine)
        val dispatch = MineProtocolShapes.buildDispatchPayload(ids, targetId, contract.mine)

        assertEquals(expected.getInt("actionType"), contract.mine.actionType)
        assertEquals(expected.getString("preparePayloadHex"), prepare.toHex())
        assertEquals(expected.getString("dispatchPayloadHex"), dispatch.toHex())
        assertEquals(
            expected.getString("prepareGameHex"),
            directGameHex(contract.mine.prepareOpcode, prepare)
        )
        assertEquals(
            expected.getString("dispatchGameHex"),
            directGameHex(contract.mine.dispatchOpcode, dispatch)
        )
    }

    @Test
    fun mineSearch8542OwnershipMatchesSharedFixture() {
        val fixture = fixture("mineSearch8542Structured")
        val expected = fixture.getJSONObject("expected")
        val resources = ResourcePointSearchResponseParser.parse(fixture.getString("responseHex"))

        assertEquals(expected.getInt("count"), resources.size)
        val occupied = resources[0]
        val occupiedExpected = expected.getJSONObject("occupied")
        assertEquals(occupiedExpected.getLong("id"), occupied.id)
        assertEquals(MineType.valueOf(occupiedExpected.getString("mineType")), occupied.mineType)
        assertEquals(occupiedExpected.getString("kind"), occupied.raw["kind"])
        assertEquals(occupiedExpected.getInt("level"), occupied.level)
        assertEquals(occupiedExpected.getInt("x"), occupied.coordinate.x)
        assertEquals(occupiedExpected.getInt("y"), occupied.coordinate.y)
        assertEquals(occupiedExpected.getLong("reserve"), occupied.reserve)
        assertEquals(occupiedExpected.getString("ownerName"), occupied.ownerName)
        assertEquals(occupiedExpected.getString("ownerCountry"), occupied.raw["ownerCountry"])
        assertEquals(occupiedExpected.getBoolean("playerOccupied"), occupied.playerOccupied)
        assertEquals(occupiedExpected.getBoolean("isEmpty"), occupied.isEmpty)
        assertEquals(occupiedExpected.getInt("defenderCount"), occupied.defenseCount)
        assertTrue(
            occupied.raw.getValue("defenders")
                .startsWith(occupiedExpected.getString("firstDefenderName") + ",")
        )
        assertEquals(expected.getInt("centerX").toString(), occupied.raw["centerX"])
        assertEquals(expected.getInt("centerY").toString(), occupied.raw["centerY"])

        val empty = resources[1]
        val emptyExpected = expected.getJSONObject("empty")
        assertEquals(emptyExpected.getLong("id"), empty.id)
        assertEquals(MineType.valueOf(emptyExpected.getString("mineType")), empty.mineType)
        assertEquals(emptyExpected.getString("kind"), empty.raw["kind"])
        assertEquals(emptyExpected.getInt("level"), empty.level)
        assertEquals(emptyExpected.getInt("x"), empty.coordinate.x)
        assertEquals(emptyExpected.getInt("y"), empty.coordinate.y)
        assertEquals(emptyExpected.getLong("reserve"), empty.reserve)
        assertEquals(null, empty.ownerName)
        assertEquals(emptyExpected.getString("ownerCountry"), empty.raw["ownerCountry"])
        assertEquals(emptyExpected.getBoolean("playerOccupied"), empty.playerOccupied)
        assertEquals(emptyExpected.getBoolean("isEmpty"), empty.isEmpty)
        assertEquals(emptyExpected.getInt("defenderCount"), empty.defenseCount)
    }

    @Test
    fun minePreviewAndWithdrawMatchSharedFixtures() {
        val previewFixture = fixture("minePreview8520")
        val expected = previewFixture.getJSONObject("expected")
        val preview = MineProtocolShapes.parsePreview(
            previewFixture.getString("responseHex").hexBytes(), contract.mine
        ) ?: error("shared 0x8520 preview fixture did not parse")

        assertEquals(expected.getInt("marchSeconds"), preview.marchSeconds)
        assertEquals(expected.getInt("winRate"), preview.winRate)
        assertEquals(expected.getInt("x"), preview.x)
        assertEquals(expected.getInt("y"), preview.y)

        val withdrawFixture = fixture("mineWithdraw8526")
        val battleId = withdrawFixture.getLong("battleId")
        assertEquals(
            withdrawFixture.getString("requestPayloadHex"),
            MineProtocolShapes.buildWithdrawPayload(battleId, contract.mine.withdraw).toHex()
        )
        val accepted = MineProtocolShapes.parseWithdrawReceipt(
            withdrawFixture.getString("successResponseHex").hexBytes(),
            battleId,
            contract.mine.withdraw
        )
        val mismatched = MineProtocolShapes.parseWithdrawReceipt(
            withdrawFixture.getString("mismatchedResponseHex").hexBytes(),
            battleId,
            contract.mine.withdraw
        )
        assertTrue(accepted.success)
        assertEquals(battleId, accepted.battleId)
        assertFalse(mismatched.success)
    }

    @Test
    fun mineExactLevelOwnershipAndSpeedMatchSharedFixtures() {
        val filterFixture = fixture("mineExactLevelAndOwnership")
        val selectedTypes = filterFixture.stringList("selectedMineTypes").map(MineType::valueOf).toSet()
        val selectedLevels = filterFixture.intList("selectedLevels").toSet()
        val config = MineConfig(
            enabled = true,
            start = MapCoordinate(0, 0),
            hitEmptyMine = true,
            withdrawDefense = true,
            resourcePointLimit = 1,
            selectedMineTypes = selectedTypes,
            acceleratedMineTypes = emptySet(),
            selectedFormationIds = setOf(1L),
            backgroundSearch = true,
            reloginOnDisconnect = true,
            stopOnDisconnect = false,
            vibrateOnEmptyGold = false,
            vibrateOnEmptyRare = false,
            onlyEmptyMine = filterFixture.getBoolean("onlyEmpty"),
            onlyDefendedMine = false,
            selectedLevels = selectedLevels
        )
        val targets = filterFixture.getJSONArray("targets")
        for (index in 0 until targets.length()) {
            val target = targets.getJSONObject(index)
            val occupied = target.getBoolean("playerOccupied")
            val result = MineSearchResult(
                id = target.getLong("id"),
                coordinate = MapCoordinate(index, index),
                mineType = MineType.valueOf(target.getString("mineType")),
                level = target.getInt("level"),
                reserve = null,
                isEmpty = target.getBoolean("isEmpty"),
                defenseCount = if (target.getBoolean("isEmpty")) 0 else 1,
                raw = mapOf("playerOccupied" to occupied.toString()),
                playerOccupied = occupied
            )
            assertEquals(
                "target=${target.getLong("id")}",
                target.getBoolean("matches"),
                MineTargetFilterPolicy.matches(result, config, contract.mine)
            )
        }

        val speedFixture = fixture("mineSmartSpeed")
        val inventory = speedFixture.getJSONArray("inventory").let { rows ->
            (0 until rows.length()).associate { index ->
                val row = rows.getJSONObject(index)
                row.getInt("itemId") to row.getInt("count")
            }
        }
        assertEquals(
            speedFixture.intList("expectedItemIds"),
            MineProtocolShapes.chooseSpeedItems(
                speedFixture.getInt("remainingSeconds"), inventory, contract.mine.speed
            )
        )
    }

    @Test
    fun raidActionTypeAndPayloadsMatchSharedFixture() {
        val fixture = fixture("raidActionType1")
        val expected = fixture.getJSONObject("expected")
        val ids = fixture.longList("generalIds")
        val targetId = fixture.getLong("targetId")
        val prepare = LootProtocolShapes.buildPreparePayload(ids, targetId, contract.raid)
        val dispatch = LootProtocolShapes.buildExpeditionPayload(ids, targetId, contract.raid)

        assertEquals(expected.getInt("actionType"), contract.raid.actionType)
        assertEquals(expected.getString("preparePayloadHex"), prepare.toHex())
        assertEquals(expected.getString("dispatchPayloadHex"), dispatch.toHex())
        assertEquals(
            expected.getString("prepareGameHex"),
            directGameHex(contract.raid.prepareOpcode, prepare)
        )
        assertEquals(
            expected.getString("dispatchGameHex"),
            directGameHex(contract.raid.dispatchOpcode, dispatch)
        )
    }

    @Test
    fun raidFiefAndDispatchReceiptsMatchSharedFixtures() {
        val fiefFixture = fixture("raidFief8310")
        val expected = fiefFixture.getJSONObject("expected")
        val parsed = LootProtocolShapes.parseRaidFiefList(
            fiefFixture.getString("responseHex").hexBytes()
        )
        val first = parsed.fiefs.first()

        assertEquals(
            fiefFixture.getString("requestPayloadHex"),
            LootProtocolShapes.buildRaidFiefListPayload(
                fiefFixture.getString("playerName"), contract.raid
            ).toHex()
        )
        assertEquals(expected.getString("playerName"), parsed.playerName)
        assertEquals(expected.getString("country"), parsed.country)
        assertEquals(expected.getInt("count"), parsed.fiefs.size)
        assertEquals(expected.getLong("firstTargetId"), first.targetId)
        assertEquals(expected.getString("firstName"), first.name)
        assertEquals(expected.getString("firstCityName"), first.cityName)
        assertEquals(expected.getInt("firstX"), first.x)
        assertEquals(expected.getInt("firstY"), first.y)

        val receiptFixture = fixture("raidDispatchReceipts")
        val success = BrushYellowDispatchResponseParser.parseHex(
            receiptFixture.getString("successResponseHex"), contract.expedition
        )
        val missing = BrushYellowDispatchResponseParser.parseHex(
            receiptFixture.getString("missingBattleIdResponseHex"), contract.expedition
        )
        val rejected = BrushYellowDispatchResponseParser.parseHex(
            receiptFixture.getString("softRejectResponseHex"), contract.expedition
        )
        assertTrue(success.success == true)
        assertEquals(receiptFixture.getLong("expectedBattleId"), success.battleId)
        assertFalse(missing.success == true)
        assertFalse(rejected.success == true)
    }

    private fun directGameHex(opcode: Int, payload: ByteArray): String {
        require(payload.size <= 0xff) { "direct gameHex length must fit one byte" }
        return "000000000000000000" +
            payload.size.toString(16).padStart(2, '0') +
            opcode.toString(16).padStart(4, '0') +
            payload.toHex()
    }

    private fun fixture(name: String): JSONObject = JSONObject(
        repositoryFile("protocol_parity_fixtures.json").readText()
    ).getJSONObject("fixtures").getJSONObject(name)

    private fun repositoryFile(name: String): File = listOf(
        File("../shared_core/$name"),
        File("../../shared_core/$name"),
        File("shared_core/$name")
    ).firstOrNull(File::exists) ?: error("shared_core/$name is missing")

    private fun JSONObject.longList(name: String): List<Long> = getJSONArray(name).let { array ->
        (0 until array.length()).map(array::getLong)
    }

    private fun JSONObject.intList(name: String): List<Int> = getJSONArray(name).let { array ->
        (0 until array.length()).map(array::getInt)
    }

    private fun JSONObject.stringList(name: String): List<String> = getJSONArray(name).let { array ->
        (0 until array.length()).map(array::getString)
    }

    private fun String.hexBytes(): ByteArray {
        require(length % 2 == 0) { "hex length must be even" }
        return chunked(2).map { it.toInt(16).toByte() }.toByteArray()
    }

    private fun ByteArray.toHex(): String =
        joinToString("") { "%02x".format(it.toInt() and 0xff) }
}
