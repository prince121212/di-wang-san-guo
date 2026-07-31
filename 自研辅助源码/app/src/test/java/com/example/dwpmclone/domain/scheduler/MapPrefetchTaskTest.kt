package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.data.protocol.MockGameProtocolClient
import com.example.dwpmclone.domain.config.ConfigDefaults
import com.example.dwpmclone.domain.localmap.BanditCacheKey
import com.example.dwpmclone.domain.localmap.LocalTargetCache
import com.example.dwpmclone.domain.localmap.MineCacheKey
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.HuangTargetType
import com.example.dwpmclone.domain.model.MapCoordinate
import com.example.dwpmclone.domain.model.MineConfig
import com.example.dwpmclone.domain.model.MineRule
import com.example.dwpmclone.domain.model.MineType
import com.example.dwpmclone.domain.protocol.GameProtocolClient
import com.example.dwpmclone.domain.protocol.MapSearchPolicy
import com.example.dwpmclone.domain.protocol.MapTarget
import com.example.dwpmclone.domain.protocol.MineSearchResult
import com.example.dwpmclone.domain.protocol.ProtocolResult
import com.example.dwpmclone.domain.protocol.TaskContext
import com.example.dwpmclone.domain.protocol.TaskDecision
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MapPrefetchTaskTest {
    @Test
    fun banditPreparationIssuesOneExactReadonlyRequestPerStepAndPoolsResults() {
        val protocol = RecordingPrefetchProtocol()
        val cache = LocalTargetCache()
        val config = ConfigDefaults.shuaHuang().copy(
            enabled = true,
            start = MapCoordinate(91, 26),
            targetType = HuangTargetType.SHAN_ZEI,
            selectedFormationIds = setOf(7L)
        )
        val task = BanditPrefetchTask(7L, config)

        SuspendRunner.run { task.step(context(protocol, cache, 1_000L)) }
        val second = SuspendRunner.run { task.step(context(protocol, cache, 3_000L)) }

        assertEquals(2, protocol.banditCalls.size)
        assertNotEquals(protocol.banditCalls[0].second, protocol.banditCalls[1].second)
        assertTrue(protocol.banditCalls.all { it.first.channelExtra["recoveredReadOnlyScanMode"] == "SINGLE" })
        assertTrue(protocol.banditCalls.all { it.first.channelExtra["recoveredReadOnlyScanLimit"] == "1" })
        assertEquals(TaskDecision.Sleep(2_000L), second)
        val key = BanditCacheKey.from(session(), config.start, config.targetType)
        assertEquals(2, cache.bandits(key, 3_000L)?.size)
    }

    @Test
    fun minePreparationScansOneCoordinateAndWritesTheOriginalRuleCache() {
        val protocol = RecordingPrefetchProtocol()
        val cache = LocalTargetCache()
        val rule = MineRule(
            enabled = true,
            generalIds = listOf(7L),
            mineType = MineType.GOLD,
            start = MapCoordinate(91, 26),
            scope = "附近",
            onlyEmpty = true,
            onlyDefended = false,
            level = 1
        )
        val config = ConfigDefaults.mine().copy(
            enabled = true,
            start = rule.start,
            selectedMineTypes = setOf(MineType.GOLD),
            selectedFormationIds = setOf(7L),
            rules = listOf(rule)
        )
        val task = MinePrefetchTask(7L, config)

        SuspendRunner.run { task.step(context(protocol, cache, 1_000L)) }
        val second = SuspendRunner.run { task.step(context(protocol, cache, 3_000L)) }

        assertEquals(2, protocol.mineCalls.size)
        assertTrue(protocol.mineCalls.all { it.searchScope == "定点" })
        assertNotEquals(protocol.mineCalls[0].start, protocol.mineCalls[1].start)
        assertEquals(TaskDecision.Sleep(2_000L), second)
        val originalRuleConfig = config.copy(
            start = rule.start,
            selectedMineTypes = setOf(rule.mineType),
            selectedFormationIds = rule.generalIds.toSet(),
            onlyEmptyMine = rule.onlyEmpty,
            onlyDefendedMine = rule.onlyDefended,
            searchScope = rule.scope,
            selectedLevels = setOf(1)
        )
        assertEquals(
            2,
            cache.mines(MineCacheKey.from(session(), originalRuleConfig), 3_000L)?.size
        )
    }

    private fun context(
        protocol: GameProtocolClient,
        cache: LocalTargetCache,
        nowMillis: Long
    ) = TaskContext(
        session = session(),
        protocol = protocol,
        nowMillis = nowMillis,
        localMap = cache
    )

    private fun session() = GameSession(
        accountId = 7L,
        tokenCiphertext = "token",
        expiresAtMillis = null,
        channelExtra = mapOf("serverKey" to "test-server"),
        sourceMode = 1
    )
}

private class RecordingPrefetchProtocol : GameProtocolClient by MockGameProtocolClient() {
    val banditCalls = mutableListOf<Pair<GameSession, MapCoordinate>>()
    val mineCalls = mutableListOf<MineConfig>()

    override suspend fun searchMap(
        session: GameSession,
        start: MapCoordinate,
        policy: MapSearchPolicy
    ): ProtocolResult<List<MapTarget>> {
        banditCalls += session to start
        return ProtocolResult.Ok(
            listOf(
                MapTarget(
                    id = 10_000L + banditCalls.size,
                    coordinate = start,
                    type = policy.targetType?.name ?: "山贼"
                )
            )
        )
    }

    override suspend fun searchMines(
        session: GameSession,
        config: MineConfig
    ): ProtocolResult<List<MineSearchResult>> {
        mineCalls += config
        return ProtocolResult.Ok(
            listOf(
                MineSearchResult(
                    id = 20_000L + mineCalls.size,
                    coordinate = config.start,
                    mineType = config.selectedMineTypes.first(),
                    level = config.selectedLevels.firstOrNull(),
                    reserve = 10_000L,
                    isEmpty = true,
                    defenseCount = 0
                )
            )
        )
    }
}
