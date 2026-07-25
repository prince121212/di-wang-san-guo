package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.MapCoordinate
import org.junit.Assert.assertEquals
import org.junit.Test

class RecoveredMapScanPlannerTest {
    @Test
    fun singleThreadScanMatchesRecoveredFullRangeAndStep() {
        val shard = RecoveredMapScanPlanner.shard(threadIndex = 0, threadCount = 1)
        val coordinates = shard.coordinates()

        assertEquals(0, shard.xStart)
        assertEquals(186, shard.xEnd)
        assertEquals(0, shard.yStart)
        assertEquals(66, shard.yEnd)
        assertEquals(6, shard.step)
        assertEquals(MapCoordinate(0, 0), coordinates.first())
        assertEquals(MapCoordinate(186, 66), coordinates.last())
        assertEquals(32 * 12, coordinates.size)
    }

    @Test
    fun shardedScanPreservesOriginalBoundaryOverlap() {
        val shards = RecoveredMapScanPlanner.shards(threadCount = 2)

        assertEquals(0, shards[0].xStart)
        assertEquals(90, shards[0].xEnd)
        assertEquals(90, shards[1].xStart)
        assertEquals(186, shards[1].xEnd)
        assertEquals(
            RecoveredMapScanPlanner.fullScanRequests(RecoveredSearchKind.TARGET_041540, 2).size - 12,
            RecoveredMapScanPlanner.fullScanRequestsDeduped(RecoveredSearchKind.TARGET_041540, 2).size
        )
    }

    @Test
    fun targetScanBuilds041540GameHex() {
        val request = RecoveredMapScanPlanner.singleRequest(
            RecoveredSearchKind.TARGET_041540,
            MapCoordinate(6, 6)
        )

        assertEquals("00000000000000000004154000060006", request.gameHex)
    }

    @Test
    fun resourcePointScanBuilds041542GameHex() {
        val request = RecoveredMapScanPlanner.singleRequest(
            RecoveredSearchKind.RESOURCE_POINT_041542,
            MapCoordinate(6, 6)
        )

        assertEquals("00000000000000000004154200060006", request.gameHex)
    }

    @Test
    fun fullScanRequestsCanBeFedIntoReadOnlyGameHexPlanner() {
        val first = RecoveredMapScanPlanner.fullScanRequests(RecoveredSearchKind.TARGET_041540).first()
        val realClient = com.example.dwpmclone.data.protocol.RealGameProtocolClient()

        val plan = realClient.planRecoveredReadOnlyGameHex(first.gameHex, dm = 1L)

        assertEquals(0x1540, plan.opcode)
        assertEquals(true, plan.canBuildCurrentBinaryRequest)
        assertEquals(false, plan.networkSendAllowed)
    }

    @Test
    fun mineScopesUseExactNearbyAndNationalDesktopLimits() {
        val center = MapCoordinate(18, 24)

        val exact = RecoveredMapScanPlanner.mineScopeRequests(
            RecoveredSearchKind.RESOURCE_POINT_041542,
            center,
            "定点"
        )
        val nearby = RecoveredMapScanPlanner.mineScopeRequests(
            RecoveredSearchKind.RESOURCE_POINT_041542,
            center,
            "附近"
        )
        val national = RecoveredMapScanPlanner.mineScopeRequests(
            RecoveredSearchKind.RESOURCE_POINT_041542,
            center,
            "全国"
        )

        assertEquals(listOf(center), exact.map { it.coordinate })
        assertEquals(80, nearby.size)
        assertEquals(center, nearby.first().coordinate)
        assertEquals(384, national.size)
        assertEquals(center, national.first().coordinate)
        assertEquals(national.map { it.coordinate }.distinct().size, national.size)
    }
}
