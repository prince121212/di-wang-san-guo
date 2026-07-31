package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.localmap.LocalTargetCache
import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.*
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MineSearchTaskRulesTest {
    @Test
    fun enabledRulesRotateWithTheirOwnGeneralsTypeCoordinateAndScope() {
        val protocol = RecordingMineRulesProtocol()
        val localMap = LocalTargetCache()
        val rules = listOf(
            MineRule(true, listOf(7001L), MineType.GOLD, MapCoordinate(18, 22), "附近"),
            MineRule(true, listOf(7002L, 7003L), MineType.BING_YU, MapCoordinate(33, 44), "全国")
        )

        val first = SuspendRunner.run { task(rules = rules).step(context(protocol, localMap = localMap)) }
        val second = SuspendRunner.run { task(rules = rules).step(context(protocol, localMap = localMap)) }

        assertEquals(TaskDecision.Sleep(5_000), first)
        assertEquals(TaskDecision.Sleep(5_000), second)
        assertEquals(
            listOf(
                Triple(MapCoordinate(18, 22), setOf(MineType.GOLD), "附近"),
                Triple(MapCoordinate(33, 44), setOf(MineType.BING_YU), "全国")
            ),
            protocol.searchConfigs.map { Triple(it.start, it.selectedMineTypes, it.searchScope) }
        )
        assertEquals(listOf(listOf(7001L), listOf(7002L, 7003L)), protocol.occupyGeneralIds)
    }

    @Test
    fun playerOwnedTargetsAreRejectedEvenWhenLegacyTargetPlayerNameMatches() {
        val mismatchProtocol = RecordingMineRulesProtocol(ownerName = "其他玩家")
        val mismatchTask = task(
            targetPlayerName = "目标玩家",
            rules = listOf(MineRule(true, listOf(7001L), MineType.GOLD, MapCoordinate(18, 22), "定点"))
        )

        val mismatch = SuspendRunner.run {
            mismatchTask.step(context(mismatchProtocol))
        }

        assertEquals(TaskDecision.Sleep(10_000), mismatch)
        assertTrue(mismatchProtocol.occupyGeneralIds.isEmpty())

        val matchProtocol = RecordingMineRulesProtocol(ownerName = "目标玩家")
        val match = SuspendRunner.run {
            task(
                targetPlayerName = "目标玩家",
                rules = listOf(MineRule(true, listOf(7001L), MineType.GOLD, MapCoordinate(18, 22), "定点"))
            ).step(context(matchProtocol))
        }

        assertEquals(TaskDecision.Sleep(10_000), match)
        assertTrue(matchProtocol.occupyGeneralIds.isEmpty())
    }

    @Test
    fun unsuccessfulOccupyNeverWithdrawsOrReportsSuccess() {
        val protocol = RecordingMineRulesProtocol(occupySuccess = false)
        val decision = SuspendRunner.run {
            task(
                withdrawDefense = true,
                rules = listOf(MineRule(true, listOf(7001L), MineType.GOLD, MapCoordinate(18, 22)))
            ).step(context(protocol))
        }

        assertEquals(TaskDecision.Sleep(10_000), decision)
        assertEquals(0, protocol.withdrawCount)
        assertEquals(listOf(listOf(7001L)), protocol.occupyGeneralIds)
    }

    @Test
    fun withdrawWaitsForMatchingGarrisonAndUsesTheAcceptedBattleId() {
        val protocol = RecordingMineRulesProtocol(occupyBattleId = 445566L)
        val firstDecision = SuspendRunner.run {
            task(
                withdrawDefense = true,
                rules = listOf(MineRule(true, listOf(7001L), MineType.GOLD, MapCoordinate(18, 22)))
            ).step(context(protocol))
        }

        assertEquals(TaskDecision.Sleep(5_000), firstDecision)
        assertTrue(protocol.withdrawBattleIds.isEmpty())

        protocol.snapshotAction = MilitarySnapshotAction(
            tag = "驻守",
            state = "驻守",
            text = "【驻守】驻守在金矿",
            battleId = 445566L,
            generalIds = listOf(7001L),
            targetId = 901L,
            targetType = 2,
            targetName = "金矿",
            x = 18,
            y = 22
        )
        val pending = MinePendingGarrison(
            battleId = 445566L,
            mineId = 901L,
            generalIds = listOf(7001L),
            x = 18,
            y = 22,
            targetName = "金矿",
            dispatchAtMillis = 0L,
            marchSeconds = 1
        )
        val secondDecision = SuspendRunner.run {
            task(
                withdrawDefense = true,
                rules = listOf(MineRule(true, listOf(7001L), MineType.GOLD, MapCoordinate(18, 22)))
            ).step(context(protocol, sessionExtras = mapOf("minePendingGarrisonJson" to pending.toJson().toString())))
        }

        assertEquals(TaskDecision.Sleep(10_000), secondDecision)
        assertEquals(listOf(445566L), protocol.withdrawBattleIds)
    }

    @Test
    fun acceptedRecallWaitsForEverySelectedGeneralToReturnIdleBeforeClearingPendingState() {
        val protocol = RecordingMineRulesProtocol(occupyBattleId = 445566L)
        protocol.generals = listOf(
            General(7001L, "甲", null, 100, 80, status = 0),
            General(7002L, "乙", null, 100, 80, status = 0)
        )
        val pending = MinePendingGarrison(
            battleId = 445566L,
            mineId = 901L,
            generalIds = listOf(7001L, 7002L),
            x = 18,
            y = 22,
            targetName = "金矿",
            dispatchAtMillis = 1_000L,
            marchSeconds = 1,
            recallRequestedAtMillis = 1_200L
        )

        val decision = SuspendRunner.run {
            task(
                rules = listOf(
                    MineRule(true, listOf(7001L, 7002L), MineType.GOLD, MapCoordinate(18, 22))
                )
            ).step(
                context(
                    protocol,
                    sessionExtras = mapOf("minePendingGarrisonJson" to pending.toJson().toString())
                )
            )
        }

        assertEquals(TaskDecision.Sleep(30_000), decision)
        assertEquals(listOf(445566L), protocol.clearedPendingBattleIds)
        assertTrue(protocol.withdrawBattleIds.isEmpty())
        assertTrue(protocol.occupyGeneralIds.isEmpty())
    }

    @Test
    fun enabledBatchRefillRunsForTheSelectedMineGeneralsBeforeDispatch() {
        val protocol = RecordingMineRulesProtocol()
        val decision = SuspendRunner.run {
            task(
                rules = listOf(
                    MineRule(true, listOf(7001L, 7002L), MineType.GOLD, MapCoordinate(18, 22))
                )
            ).step(context(protocol, mineGate = true))
        }

        assertEquals(TaskDecision.Sleep(5_000), decision)
        assertEquals(listOf(listOf(7001L, 7002L)), protocol.refillGeneralIds)
        assertEquals(listOf(listOf(7001L, 7002L)), protocol.occupyGeneralIds)
    }

    private fun task(
        targetPlayerName: String = "",
        withdrawDefense: Boolean = false,
        rules: List<MineRule>
    ) = MineTask(
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

    private fun context(
        protocol: GameProtocolClient,
        mineGate: Boolean = false,
        localMap: LocalTargetCache = LocalTargetCache(),
        sessionExtras: Map<String, String> = emptyMap()
    ) = TaskContext(
        session = GameSession(
            accountId = 77L,
            tokenCiphertext = "token",
            expiresAtMillis = null,
            channelExtra = buildMap {
                putAll(sessionExtras)
                if (mineGate) {
                    put("realActionNetworkAllowed", "true")
                    put("realActionSendReady", "true")
                    put("realActionScope", "mine")
                }
            },
            sourceMode = 1
        ),
        protocol = protocol,
        nowMillis = 1_234L,
        localMap = localMap
    )
}

private class RecordingMineRulesProtocol(
    private val occupySuccess: Boolean = true,
    private val ownerName: String = "",
    private val occupyBattleId: Long = 445566L,
    var snapshotAction: MilitarySnapshotAction? = null
) : GameProtocolClient by MockGameProtocolClient() {
    val searchConfigs = mutableListOf<MineConfig>()
    val occupyGeneralIds = mutableListOf<List<Long>>()
    val refillGeneralIds = mutableListOf<List<Long>>()
    var withdrawCount = 0
    val withdrawBattleIds = mutableListOf<Long>()
    val clearedPendingBattleIds = mutableListOf<Long>()
    var generals: List<General> = emptyList()

    override suspend fun queryMilitarySnapshot(session: GameSession): ProtocolResult<MilitarySnapshot> =
        ProtocolResult.Ok(MilitarySnapshot(snapshotAction?.let(::listOf).orEmpty(), true, ""))

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
                    defenseCount = 0,
                    raw = if (ownerName.isBlank()) emptyMap() else mapOf("ownerName" to ownerName)
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
        return ProtocolResult.Ok(
            StepResult(
                occupySuccess,
                if (occupySuccess) "occupied" else "rejected",
                if (occupySuccess) mapOf("battleId" to occupyBattleId.toString()) else emptyMap()
            )
        )
    }

    override suspend fun updateFormation(
        session: GameSession,
        config: FormationConfig
    ): ProtocolResult<StepResult> {
        if (config.fillToMaxWhenAutoAssignDisabled) refillGeneralIds += config.generalIds
        return ProtocolResult.Ok(StepResult(true, "refilled"))
    }

    override suspend fun occupyMine(
        session: GameSession,
        mine: MineSearchResult,
        formationId: Long
    ): ProtocolResult<StepResult> = occupyMine(session, mine, listOf(formationId))

    override suspend fun occupyMine(
        session: GameSession,
        mine: MineSearchResult,
        generalIds: List<Long>,
        maxMarchMinutes: Int,
        formationRules: List<FormationConfig>
    ): ProtocolResult<StepResult> = occupyMine(session, mine, generalIds)

    override suspend fun withdrawMineDefense(
        session: GameSession,
        battleId: Long
    ): ProtocolResult<StepResult> {
        withdrawCount += 1
        withdrawBattleIds += battleId
        return ProtocolResult.Ok(StepResult(true, "withdrawn"))
    }

    override suspend fun queryGenerals(session: GameSession): ProtocolResult<List<General>> =
        ProtocolResult.Ok(generals)

    override suspend fun clearMinePendingGarrison(
        session: GameSession,
        battleId: Long
    ): ProtocolResult<StepResult> {
        clearedPendingBattleIds += battleId
        return ProtocolResult.Ok(StepResult(true, "cleared"))
    }
}
