package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.localmap.LocalTargetCache
import com.example.dwpmclone.domain.localmap.MemoryLocalMapStore
import com.example.dwpmclone.domain.model.FormationFilterMode
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.HuangTargetType
import com.example.dwpmclone.domain.model.MapCoordinate
import com.example.dwpmclone.domain.model.MineConfig
import com.example.dwpmclone.domain.model.MineType
import com.example.dwpmclone.domain.model.ShuaHuangConfig
import com.example.dwpmclone.domain.protocol.BattleResult
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.protocol.MapSearchPolicy
import com.example.dwpmclone.domain.protocol.MapTarget
import com.example.dwpmclone.domain.protocol.MineSearchResult
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.StepResult
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import org.junit.Assert.assertEquals
import org.junit.Test

class LocalMapTaskLifecycleTest {
    @Test
    fun reconstructedBrushTaskAndHotCacheConsumePersistedTargetWithoutRescanning() {
        val store = MemoryLocalMapStore()
        val protocol = RecordingLocalMapProtocol()
        val first = SuspendRunner.run {
            brushTask().step(context(protocol, LocalTargetCache(banditTtlMillis = 60_000L, store = store), 1_000L))
        }
        // Models a service/process reconstruction: both task and hot cache are new instances.
        val second = SuspendRunner.run {
            brushTask().step(context(protocol, LocalTargetCache(banditTtlMillis = 60_000L, store = store), 2_000L))
        }

        assertEquals(TaskDecision.Sleep(1_000L), first)
        assertEquals(TaskDecision.Sleep(1_000L), second)
        assertEquals(1, protocol.banditSearches)
        assertEquals(listOf(101L, 102L), protocol.dispatchedBandits)
    }

    @Test
    fun rejectedMineIsInvalidatedAndNextBatchRescansLocally() {
        val store = MemoryLocalMapStore()
        val protocol = RecordingLocalMapProtocol(mineOccupyResults = ArrayDeque(listOf(false, true)))

        val first = SuspendRunner.run {
            mineTask().step(context(protocol, LocalTargetCache(mineTtlMillis = 60_000L, store = store), 1_000L))
        }
        val second = SuspendRunner.run {
            mineTask().step(context(protocol, LocalTargetCache(mineTtlMillis = 60_000L, store = store), 2_000L))
        }

        assertEquals(TaskDecision.Sleep(10_000L), first)
        assertEquals(TaskDecision.Sleep(5_000L), second)
        assertEquals(2, protocol.mineSearches)
        assertEquals(listOf(201L, 202L), protocol.occupiedMines)
    }

    private fun context(
        protocol: GameProtocolClient,
        cache: LocalTargetCache,
        nowMillis: Long
    ) = TaskContext(
        session = GameSession(77L, "token", null, emptyMap(), sourceMode = 0),
        protocol = protocol,
        nowMillis = nowMillis,
        localMap = cache
    )

    private fun brushTask() = ShuaHuangTask(
        77L,
        ShuaHuangConfig(
            enabled = true,
            dailyLimit = 500,
            start = MapCoordinate(10, 20),
            targetType = HuangTargetType.SHAN_ZEI,
            selectedFormationIds = setOf(1L),
            formationFilterMode = FormationFilterMode.UNIFIED,
            deleteMailForSpeed = false,
            autoConvertFoodToCopper = false
        )
    )

    private fun mineTask() = MineTask(
        77L,
        MineConfig(
            enabled = true,
            start = MapCoordinate(10, 20),
            hitEmptyMine = true,
            withdrawDefense = false,
            resourcePointLimit = 2,
            selectedMineTypes = setOf(MineType.GOLD),
            acceleratedMineTypes = emptySet(),
            selectedFormationIds = setOf(1L),
            backgroundSearch = false,
            reloginOnDisconnect = true,
            stopOnDisconnect = false,
            vibrateOnEmptyGold = false,
            vibrateOnEmptyRare = false,
            onlyEmptyMine = true,
            onlyDefendedMine = false
        )
    )
}

private class RecordingLocalMapProtocol(
    private val mineOccupyResults: ArrayDeque<Boolean> = ArrayDeque()
) : GameProtocolClient by MockGameProtocolClient() {
    var banditSearches = 0
    var mineSearches = 0
    val dispatchedBandits = mutableListOf<Long>()
    val occupiedMines = mutableListOf<Long>()

    override suspend fun searchMap(
        session: GameSession,
        start: MapCoordinate,
        policy: MapSearchPolicy
    ): ProtocolResult<List<MapTarget>> {
        banditSearches += 1
        return ProtocolResult.Ok(listOf(
            MapTarget(101L, MapCoordinate(11, 20), HuangTargetType.SHAN_ZEI.name),
            MapTarget(102L, MapCoordinate(12, 20), HuangTargetType.SHAN_ZEI.name)
        ))
    }

    override suspend fun dispatchFormation(
        session: GameSession,
        formationId: Long,
        target: MapTarget
    ): ProtocolResult<BattleResult> {
        dispatchedBandits += target.id
        return ProtocolResult.Ok(BattleResult(true, 1))
    }

    override suspend fun dispatchFormation(
        session: GameSession,
        formation: com.example.dwpmclone.domain.model.FormationRuntime,
        target: MapTarget
    ): ProtocolResult<BattleResult> = dispatchFormation(session, formation.id, target)

    override suspend fun dispatchFormation(
        session: GameSession,
        formation: com.example.dwpmclone.domain.model.FormationRuntime,
        target: MapTarget,
        formationRules: List<com.example.dwpmclone.domain.model.FormationConfig>
    ): ProtocolResult<BattleResult> = dispatchFormation(session, formation.id, target)

    override suspend fun searchMines(
        session: GameSession,
        config: MineConfig
    ): ProtocolResult<List<MineSearchResult>> {
        mineSearches += 1
        return ProtocolResult.Ok(listOf(
            MineSearchResult(
                id = 200L + mineSearches,
                coordinate = config.start,
                mineType = MineType.GOLD,
                level = 5,
                reserve = 1_000L,
                isEmpty = true,
                defenseCount = 0
            )
        ))
    }

    override suspend fun occupyMine(
        session: GameSession,
        mine: MineSearchResult,
        formationId: Long
    ): ProtocolResult<StepResult> {
        occupiedMines += mine.id
        val success = mineOccupyResults.removeFirstOrNull() ?: true
        return ProtocolResult.Ok(
            StepResult(
                success,
                if (success) "occupied" else "target stale",
                if (success) mapOf("battleId" to (900_000L + mine.id).toString()) else emptyMap()
            )
        )
    }

    override suspend fun occupyMine(
        session: GameSession,
        mine: MineSearchResult,
        generalIds: List<Long>,
        maxMarchMinutes: Int,
        formationRules: List<com.example.dwpmclone.domain.model.FormationConfig>
    ): ProtocolResult<StepResult> = occupyMine(session, mine, generalIds.first())
}
