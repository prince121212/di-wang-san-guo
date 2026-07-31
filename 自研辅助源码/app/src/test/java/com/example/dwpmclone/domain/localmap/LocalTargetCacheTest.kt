package com.example.dwpmclone.domain.localmap

import com.example.dwpmclone.domain.model.HuangTargetType
import com.example.dwpmclone.domain.model.MapCoordinate
import com.example.dwpmclone.domain.model.MineConfig
import com.example.dwpmclone.domain.model.MineType
import com.example.dwpmclone.domain.protocol.MapTarget
import com.example.dwpmclone.domain.protocol.MineSearchResult
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalTargetCacheTest {
    @Test
    fun consumedTargetsAreRemovedAndRemainingTargetsStayLocal() {
        val cache = LocalTargetCache(banditTtlMillis = 1_000L)
        val key = BanditCacheKey(7L, MapCoordinate(10, 20), HuangTargetType.SHAN_ZEI)
        cache.saveBandits(
            key,
            listOf(
                MapTarget(101L, MapCoordinate(11, 21), "山贼"),
                MapTarget(102L, MapCoordinate(12, 22), "山贼")
            ),
            observedAtMillis = 100L
        )

        cache.invalidateBandit(key, 101L)

        assertEquals(listOf(102L), cache.bandits(key, 200L)?.map { it.id })
        assertNull(cache.bandits(key, 1_101L))
    }

    @Test
    fun mineCacheIsScopedByLocalSearchPolicyAndExpires() {
        val cache = LocalTargetCache(mineTtlMillis = 500L)
        val gold = MineCacheKey.from(7L, mineConfig(setOf(MineType.GOLD)))
        val silver = MineCacheKey.from(7L, mineConfig(setOf(MineType.SILVER)))
        cache.saveMines(
            gold,
            listOf(MineSearchResult(9L, MapCoordinate(1, 2), MineType.GOLD, 5, 100, true, 0)),
            observedAtMillis = 1_000L
        )

        assertEquals(listOf(9L), cache.mines(gold, 1_400L)?.map { it.id })
        assertNull(cache.mines(silver, 1_400L))
        assertNull(cache.mines(gold, 1_501L))
    }

    @Test
    fun emptyScanIsFreshUntilTtlToAvoidTightRescanLoop() {
        val cache = LocalTargetCache(banditTtlMillis = 1_000L)
        val key = BanditCacheKey(7L, MapCoordinate(10, 20), HuangTargetType.SHAN_ZEI)

        cache.saveBandits(key, emptyList(), observedAtMillis = 100L)

        assertEquals(emptyList<MapTarget>(), cache.bandits(key, 1_000L))
        assertNull(cache.bandits(key, 1_101L))
    }

    @Test
    fun banditTargetsOutliveEmptyCoordinateScanLikeDesktopMapCache() {
        val cache = LocalTargetCache(
            banditTtlMillis = 30_000L,
            banditEmptyTtlMillis = 2_000L
        )
        val targetsKey = BanditCacheKey(7L, MapCoordinate(10, 20), HuangTargetType.SHAN_ZEI)
        val emptyKey = BanditCacheKey(7L, MapCoordinate(20, 30), HuangTargetType.SHAN_ZEI)
        cache.saveBandits(
            targetsKey,
            listOf(MapTarget(101L, MapCoordinate(12, 24), "山贼")),
            observedAtMillis = 1_000L
        )
        cache.saveBandits(emptyKey, emptyList(), observedAtMillis = 1_000L)

        assertEquals(listOf(101L), cache.bandits(targetsKey, 4_000L)?.map { it.id })
        assertNull(cache.bandits(emptyKey, 4_000L))
    }

    @Test
    fun persistedSnapshotRestoresIntoNewHotCacheAndRetainsSafeMetadata() {
        val store = MemoryLocalMapStore()
        val key = BanditCacheKey(
            accountId = 7L,
            start = MapCoordinate(10, 20),
            targetType = HuangTargetType.SHAN_ZEI,
            serverId = "qzone_351"
        )
        LocalTargetCache(banditTtlMillis = 10_000L, store = store).saveBandits(
            key,
            listOf(MapTarget(
                101L,
                MapCoordinate(11, 21),
                "山贼",
                raw = mapOf("level" to "3", "compositionCode" to "3210", "rawRecord" to "A".repeat(200))
            )),
            observedAtMillis = 1_000L
        )

        val restored = LocalTargetCache(banditTtlMillis = 10_000L, store = store)
            .bandits(key, 2_000L)
            .orEmpty()

        assertEquals(listOf(101L), restored.map { it.id })
        assertEquals("3210", restored.single().raw["compositionCode"])
        assertFalse(restored.single().raw.containsKey("rawRecord"))
        assertEquals("qzone_351", store.read(key.query())?.query?.serverId)

        LocalTargetCache(banditTtlMillis = 10_000L, store = store)
            .invalidateBandit(key, 101L, 2_100L, "dispatch-rejected")
        val invalid = store.read(key.query())!!.targets.single()
        assertEquals(2_100L, invalid.invalidatedAtMillis)
        assertEquals("dispatch-rejected", invalid.invalidReason)
        assertTrue(LocalTargetCache(banditTtlMillis = 10_000L, store = store).bandits(key, 2_200L) == null)
    }

    private fun mineConfig(types: Set<MineType>) = MineConfig(
        enabled = true,
        start = MapCoordinate(10, 20),
        hitEmptyMine = true,
        withdrawDefense = false,
        resourcePointLimit = 2,
        selectedMineTypes = types,
        acceleratedMineTypes = emptySet(),
        selectedFormationIds = setOf(1L),
        backgroundSearch = false,
        reloginOnDisconnect = true,
        stopOnDisconnect = false,
        vibrateOnEmptyGold = false,
        vibrateOnEmptyRare = false,
        onlyEmptyMine = true,
        onlyDefendedMine = false,
        searchScope = "附近"
    )
}
