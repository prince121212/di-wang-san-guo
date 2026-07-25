package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.cloud.*
import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.*
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MineSearchTaskRulesTest {
    @Test
    fun enabledRulesRotateWithTheirOwnGeneralsTypeCoordinateAndScope() {
        val protocol = RecordingMineRulesProtocol()
        val cloud = RecordingMineRulesCloud(ownerName = "")
        val task = task(
            rules = listOf(
                MineRule(true, listOf(7001L), MineType.GOLD, MapCoordinate(18, 22), "附近"),
                MineRule(true, listOf(7002L, 7003L), MineType.BING_YU, MapCoordinate(33, 44), "全国")
            )
        )

        val first = SuspendRunner.run { task.step(context(protocol, cloud)) }
        val second = SuspendRunner.run { task.step(context(protocol, cloud)) }

        assertEquals(TaskDecision.Sleep(30_000), first)
        assertEquals(TaskDecision.Sleep(30_000), second)
        assertEquals(
            listOf(
                Triple(MapCoordinate(18, 22), setOf(MineType.GOLD), "附近"),
                Triple(MapCoordinate(33, 44), setOf(MineType.BING_YU), "全国")
            ),
            protocol.searchConfigs.map { Triple(it.start, it.selectedMineTypes, it.searchScope) }
        )
        assertEquals(listOf(listOf(7001L), listOf(7002L, 7003L)), protocol.occupyGeneralIds)
        assertEquals(listOf(setOf(MineType.GOLD.name), setOf(MineType.BING_YU.name)), cloud.allowedTypes)
    }

    @Test
    fun targetPlayerNameRequiresExplicitCloudOwnerEvidence() {
        val mismatchProtocol = RecordingMineRulesProtocol()
        val mismatchTask = task(
            targetPlayerName = "目标玩家",
            rules = listOf(MineRule(true, listOf(7001L), MineType.GOLD, MapCoordinate(18, 22), "定点"))
        )

        val mismatch = SuspendRunner.run {
            mismatchTask.step(context(mismatchProtocol, RecordingMineRulesCloud(ownerName = "其他玩家")))
        }

        assertEquals(TaskDecision.Sleep(30_000), mismatch)
        assertTrue(mismatchProtocol.occupyGeneralIds.isEmpty())

        val matchProtocol = RecordingMineRulesProtocol()
        val match = SuspendRunner.run {
            task(
                targetPlayerName = "目标玩家",
                rules = listOf(MineRule(true, listOf(7001L), MineType.GOLD, MapCoordinate(18, 22), "定点"))
            ).step(context(matchProtocol, RecordingMineRulesCloud(ownerName = "目标玩家")))
        }

        assertEquals(TaskDecision.Sleep(30_000), match)
        assertEquals(listOf(listOf(7001L)), matchProtocol.occupyGeneralIds)
    }

    @Test
    fun unsuccessfulOccupyNeverWithdrawsOrReportsSuccess() {
        val protocol = RecordingMineRulesProtocol(occupySuccess = false)
        val decision = SuspendRunner.run {
            task(
                withdrawDefense = true,
                rules = listOf(MineRule(true, listOf(7001L), MineType.GOLD, MapCoordinate(18, 22)))
            ).step(context(protocol, RecordingMineRulesCloud(ownerName = "")))
        }

        assertEquals(TaskDecision.Sleep(30_000), decision)
        assertEquals(0, protocol.withdrawCount)
        assertEquals(listOf(listOf(7001L)), protocol.occupyGeneralIds)
    }

    private fun task(
        targetPlayerName: String = "",
        withdrawDefense: Boolean = false,
        rules: List<MineRule>
    ) = MineSearchMockTask(
        77L,
        MineConfig(
            enabled = true,
            start = MapCoordinate(0, 0),
            hitEmptyMine = true,
            withdrawDefense = withdrawDefense,
            resourcePointLimit = 2,
            selectedMineTypes = setOf(MineType.GOLD),
            acceleratedMineTypes = emptySet(),
            selectedFormationIds = setOf(7001L),
            backgroundSearch = false,
            reloginOnDisconnect = true,
            stopOnDisconnect = false,
            vibrateOnEmptyGold = false,
            vibrateOnEmptyRare = false,
            onlyEmptyMine = false,
            onlyDefendedMine = false,
            targetPlayerName = targetPlayerName,
            rules = rules
        )
    )

    private fun context(protocol: GameProtocolClient, cloud: CollaborativeMapClient) = TaskContext(
        session = GameSession(
            accountId = 77L,
            tokenCiphertext = "token",
            expiresAtMillis = null,
            channelExtra = mapOf("collaborativeMapRequired" to "true", "serverKey" to "351"),
            sourceMode = 1
        ),
        protocol = protocol,
        nowMillis = 1_234L,
        cloudMap = CloudFirstMapCoordinator(cloud)
    )
}

private class RecordingMineRulesProtocol(
    private val occupySuccess: Boolean = true
) : GameProtocolClient by MockGameProtocolClient() {
    val searchConfigs = mutableListOf<MineConfig>()
    val occupyGeneralIds = mutableListOf<List<Long>>()
    var withdrawCount = 0

    override suspend fun searchMines(
        session: GameSession,
        config: MineConfig
    ): ProtocolResult<List<MineSearchResult>> {
        searchConfigs += config
        return ProtocolResult.Ok(
            listOf(
                MineSearchResult(
                    id = 900L + searchConfigs.size,
                    coordinate = config.start,
                    mineType = config.selectedMineTypes.first(),
                    level = 5,
                    reserve = 1000L,
                    isEmpty = true,
                    defenseCount = 0
                )
            )
        )
    }

    override suspend fun occupyMine(
        session: GameSession,
        mine: MineSearchResult,
        generalIds: List<Long>
    ): ProtocolResult<StepResult> {
        occupyGeneralIds += generalIds
        return ProtocolResult.Ok(StepResult(occupySuccess, if (occupySuccess) "occupied" else "rejected"))
    }

    override suspend fun occupyMine(
        session: GameSession,
        mine: MineSearchResult,
        formationId: Long
    ): ProtocolResult<StepResult> = occupyMine(session, mine, listOf(formationId))

    override suspend fun withdrawMineDefense(
        session: GameSession,
        mineId: Long
    ): ProtocolResult<StepResult> {
        withdrawCount += 1
        return ProtocolResult.Ok(StepResult(true, "withdrawn"))
    }
}

private class RecordingMineRulesCloud(
    private val ownerName: String
) : CollaborativeMapClient {
    val allowedTypes = mutableListOf<Set<String>>()

    override suspend fun upload(request: ObservationUploadRequest): CloudMapResult<UploadReceipt> =
        CloudMapResult.Ok(UploadReceipt(request.observations.size, "revision-${allowedTypes.size}", request.clientBatchId))

    override suspend fun recommend(request: TargetRecommendationRequest): CloudMapResult<CloudTarget?> {
        allowedTypes += request.allowedMineTypes
        val type = request.allowedMineTypes.first()
        return CloudMapResult.Ok(
            CloudTarget(
                targetId = 1000L + allowedTypes.size,
                coordinate = request.start,
                targetType = type,
                level = 5,
                serverRevision = request.acceptedRevision,
                raw = mapOf(
                    "reserve" to "1000",
                    "isEmpty" to "true",
                    "defenseCount" to "0",
                    "ownerName" to ownerName
                )
            )
        )
    }

    override suspend fun reportExpedition(
        request: ExpeditionResultRequest
    ): CloudMapResult<ExpeditionResultReceipt> =
        CloudMapResult.Ok(
            ExpeditionResultReceipt(
                accepted = true,
                serverRevision = "${request.acceptedRevision}-result",
                targetId = request.targetId
            )
        )
}
