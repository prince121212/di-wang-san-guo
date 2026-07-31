package com.example.dwpmclone.domain.protocol

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class LosslessDungeonProtocolParityFixtureTest {
    private val contract by lazy {
        AssistantBehaviorContract.fromJson(repositoryFile("assistant_behavior_contract.json").readText())
    }

    @Test
    fun losslessStatusSettlementAndPayloadsMatchSharedFixtures() {
        val statusFixture = fixture("losslessCooldown8900")
        val statusExpected = statusFixture.getJSONObject("expected")
        val status = LosslessProtocolShapes.parseStatus(
            statusFixture.getString("responseHex").hexBytes(),
            contract.lossless
        )
        assertEquals(statusExpected.getString("phase"), status.phase.name.lowercase())
        assertEquals(statusExpected.getInt("mode"), status.mode)
        assertEquals(statusExpected.getInt("remainingAttempts"), status.remainingAttempts)
        assertEquals(statusExpected.getLong("actionTimerMillis"), status.actionTimerMillis)
        assertEquals(statusExpected.getLong("cooldownMillis"), status.cooldownMillis)
        assertEquals(statusExpected.getInt("reopenCost"), status.reopenCost)

        val settlementFixture = fixture("losslessSettlement8902Failed")
        val settlementExpected = settlementFixture.getJSONObject("expected")
        val settlement = LosslessProtocolShapes.parseSettlement(
            settlementFixture.getString("responseHex").hexBytes()
        )
        assertEquals(settlementExpected.getBoolean("success"), settlement.success)
        assertEquals(settlementExpected.getBoolean("battleFailed"), settlement.battleFailed)
        assertEquals(settlementExpected.getLong("battleId"), settlement.battleId)
        assertEquals(settlementExpected.getString("resultText"), settlement.resultText)
        assertEquals(settlementExpected.getString("generalText"), settlement.generalText)

        val actionFixture = fixture("losslessActionType11")
        val actionExpected = actionFixture.getJSONObject("expected")
        val generalIds = actionFixture.longList("generalIds")
        val roleId = actionFixture.getLong("roleId")
        assertEquals(actionExpected.getInt("actionType"), contract.lossless.actionType)
        assertEquals(
            actionExpected.getString("preparePayloadHex"),
            LosslessProtocolShapes.buildPreparePayload(
                generalIds, roleId, contract.lossless
            ).toHex()
        )
        assertEquals(
            actionExpected.getString("dispatchPayloadHex"),
            LosslessProtocolShapes.buildExpeditionPayload(
                generalIds, roleId, contract.lossless
            ).toHex()
        )
    }

    @Test
    fun losslessLevel10GuardMatchesSharedFixture() {
        val fixture = fixture("losslessLevel10LastChariot")
        val types = fixture.stringList("soldierTypes")
        val lineup = LosslessLineup(
            success = true,
            status = 0,
            stageId = fixture.getInt("stageId"),
            levelName = "10级关卡",
            stageName = fixture.getString("stageName"),
            enemies = types.mapIndexed { index, type ->
                LosslessEnemy(index + 1, "敌将${index + 1}", type, 100)
            }
        )
        val verdict = LosslessProtocolShapes.evaluateLevel10Guard(lineup, contract.lossless)
        val expected = fixture.getJSONObject("expected")

        assertEquals(expected.getBoolean("qualified"), verdict.qualified)
        assertEquals(expected.intList("chariotPositions"), verdict.chariotPositions)
        assertEquals(expected.intList("catapultPositions"), verdict.catapultPositions)
    }

    @Test
    fun dungeonPayloadCatalogClearSelectionAndPollMatchSharedFixtures() {
        val actionFixture = fixture("dungeonActionType14")
        val actionExpected = actionFixture.getJSONObject("expected")
        val generalIds = actionFixture.longList("generalIds")
        val stageCode = actionFixture.getInt("stageCode")
        assertEquals(actionExpected.getInt("actionType"), contract.dungeon.actionType)
        assertEquals(
            actionExpected.getString("preparePayloadHex"),
            DungeonProtocolShapes.buildPreparePayload(
                generalIds, stageCode, contract.dungeon
            ).toHex()
        )
        assertEquals(
            actionExpected.getString("dispatchPayloadHex"),
            DungeonProtocolShapes.buildExpeditionPayload(
                generalIds, stageCode, contract.dungeon
            ).toHex()
        )
        assertEquals(
            actionExpected.getString("chestRightPayloadHex"),
            DungeonProtocolShapes.buildOpenChestPayload(2).toHex()
        )

        val catalogFixture = fixture("dungeonCatalog8930")
        val catalogExpected = catalogFixture.getJSONObject("expected")
        val catalog = DungeonProtocolShapes.parseCatalog(
            catalogFixture.getString("responseHex").hexBytes()
        )
        val first = catalog.chapters.first()
        assertEquals(catalogExpected.getInt("chapterCount"), catalog.chapters.size)
        assertEquals(catalogExpected.getString("firstChapterName"), first.name)
        assertEquals(catalogExpected.getInt("firstChapterStageCount"), first.stages.size)
        assertEquals(catalogExpected.getInt("displayStage3Code"), first.stages[2].stageCode)
        assertEquals(catalogExpected.getInt("displayStage4Code"), first.stages[3].stageCode)
        val selection = DungeonProtocolShapes.firstUncompletedStage(catalog, contract.dungeon)
        assertNotNull(selection)
        selection ?: error("shared catalog must expose an uncompleted stage")
        assertEquals(catalogExpected.getInt("firstUncompletedChapter"), selection.chapter)
        assertEquals(
            catalogExpected.getInt("firstUncompletedDisplayStage"), selection.displayStage
        )
        assertEquals(catalogExpected.getInt("firstUncompletedStageCode"), selection.stageCode)
        assertEquals(catalogExpected.getBoolean("firstUncompletedAvailable"), selection.available)
        assertEquals(
            catalogExpected.getInt("chapter7DisplayStage11Code"),
            DungeonProtocolShapes.resolveStageCode(catalog, 6, 11, contract.dungeon)
        )

        val stateFixture = fixture("dungeonStateAndPoll")
        val expected = stateFixture.getJSONObject("expected")
        assertEquals(
            DungeonBattlePhase.IDLE,
            DungeonProtocolShapes.parseBattleState(
                stateFixture.getString("idleResponseHex").hexBytes()
            ).phase
        )
        val active = DungeonProtocolShapes.parseBattleState(
            stateFixture.getString("fightingResponseHex").hexBytes()
        )
        assertEquals(DungeonBattlePhase.FIGHTING, active.phase)
        assertEquals(expected.getLong("battleId"), active.battleId)
        val reward = DungeonProtocolShapes.parseRewardState(
            stateFixture.getString("rewardResponseHex").hexBytes()
        )
        assertEquals(expected.getLong("battleId"), reward.battleId)
        assertEquals(
            expected.getString("firstPollPayloadHex"),
            DungeonProtocolShapes.buildBattlePollPayload(
                true, expected.getLong("battleId")
            ).toHex()
        )
        assertEquals(
            expected.getString("nextPollPayloadHex"),
            DungeonProtocolShapes.buildBattlePollPayload(
                false, expected.getLong("battleId")
            ).toHex()
        )
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
        require(length % 2 == 0)
        return chunked(2).map { it.toInt(16).toByte() }.toByteArray()
    }

    private fun ByteArray.toHex(): String =
        joinToString("") { "%02x".format(it.toInt() and 0xff) }
}
