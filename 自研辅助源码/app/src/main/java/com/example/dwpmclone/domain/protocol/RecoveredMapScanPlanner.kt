package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.MapCoordinate

/**
 * Recovered 041540/041542 map scan planner.
 *
 * Static evidence from 小黄点:
 * - x range uses 186.0 split by thread count
 * - y range is 0..0x42 (66)
 * - both axes step by 6
 * - request = 041540/041542 + encodeXY(x,y)
 *
 * This object only builds offline/auditable request plans. It does not perform network I/O.
 */
object RecoveredMapScanPlanner {
    const val WORLD_X_MAX = 186
    const val WORLD_Y_MAX = 0x42
    const val STEP = 6

    fun shard(
        threadIndex: Int,
        threadCount: Int,
        contract: MapSearchBehaviorContract = MapSearchBehaviorContract.defaults()
    ): RecoveredScanShard {
        require(threadCount > 0) { "threadCount must be positive" }
        require(threadIndex in 0 until threadCount) { "threadIndex must be in 0 until threadCount" }
        val world = contract.world
        val slice = (world.xMax - world.xMin).toDouble() / threadCount.toDouble()
        val xStart = world.xMin + (((threadIndex * slice) / world.step).toInt()) * world.step
        val xEnd = world.xMin + ((((threadIndex + 1) * slice) / world.step).toInt()) * world.step
        return RecoveredScanShard(
            threadIndex = threadIndex,
            threadCount = threadCount,
            xStart = xStart,
            xEnd = xEnd,
            yStart = world.yMin,
            yEnd = world.yMax,
            step = world.step
        )
    }

    fun shards(
        threadCount: Int,
        contract: MapSearchBehaviorContract = MapSearchBehaviorContract.defaults()
    ): List<RecoveredScanShard> =
        (0 until threadCount).map { shard(it, threadCount, contract) }

    fun requests(
        kind: RecoveredSearchKind,
        shard: RecoveredScanShard,
        contract: MapSearchBehaviorContract = MapSearchBehaviorContract.defaults()
    ): List<RecoveredSearchRequest> =
        shard.coordinates().map { coordinate ->
            RecoveredSearchRequest(
                kind = kind,
                coordinate = coordinate,
                gameHex = buildGameHex(kind, coordinate.x, coordinate.y, contract)
            )
        }

    fun fullScanRequests(
        kind: RecoveredSearchKind,
        threadCount: Int = 1,
        contract: MapSearchBehaviorContract = MapSearchBehaviorContract.defaults()
    ): List<RecoveredSearchRequest> =
        shards(threadCount, contract).flatMap { requests(kind, it, contract) }

    fun fullScanRequestsDeduped(
        kind: RecoveredSearchKind,
        threadCount: Int,
        contract: MapSearchBehaviorContract = MapSearchBehaviorContract.defaults()
    ): List<RecoveredSearchRequest> =
        fullScanRequests(kind, threadCount, contract).distinctBy { it.coordinate }

    fun singleRequest(
        kind: RecoveredSearchKind,
        coordinate: MapCoordinate,
        contract: MapSearchBehaviorContract = MapSearchBehaviorContract.defaults()
    ): RecoveredSearchRequest =
        RecoveredSearchRequest(kind, coordinate, buildGameHex(kind, coordinate.x, coordinate.y, contract))

    /**
     * Mirrors the desktop helper's center-first scan order. Every account uses the same
     * world-origin six-tile lattice; the configured center affects ordering only.
     */
    fun nearbyRequests(
        kind: RecoveredSearchKind,
        center: MapCoordinate,
        limit: Int = MapSearchBehaviorContract.defaults().nearbyRequestLimit,
        contract: MapSearchBehaviorContract = MapSearchBehaviorContract.defaults()
    ): List<RecoveredSearchRequest> {
        val world = contract.world
        val cx = center.x.coerceIn(world.xMin, world.xMax)
        val cy = center.y.coerceIn(world.yMin, world.yMax)
        return buildList {
            for (x in world.xMin..world.xMax step world.step) {
                for (y in world.yMin..world.yMax step world.step) {
                    add(MapCoordinate(x, y))
                }
            }
        }
            .sortedWith(compareBy<MapCoordinate>(
                { (it.x - cx) * (it.x - cx) + (it.y - cy) * (it.y - cy) },
                { kotlin.math.abs(it.x - cx) + kotlin.math.abs(it.y - cy) },
                { it.x },
                { it.y }
            ))
            .take(limit.coerceIn(1, contract.fullRequestLimit))
            .map { singleRequest(kind, it, contract) }
    }

    fun mineScopeRequests(
        kind: RecoveredSearchKind,
        center: MapCoordinate,
        scope: String,
        contract: MapSearchBehaviorContract = MapSearchBehaviorContract.defaults()
    ): List<RecoveredSearchRequest> = when (scope) {
        "定点" -> listOf(singleRequest(kind, center, contract))
        "全国" -> nearbyRequests(kind, center, contract.fullRequestLimit, contract)
        else -> nearbyRequests(kind, center, contract.nearbyRequestLimit, contract)
    }

    fun buildGameHex(
        kind: RecoveredSearchKind,
        x: Int,
        y: Int,
        contract: MapSearchBehaviorContract = MapSearchBehaviorContract.defaults()
    ): String = when (kind) {
        RecoveredSearchKind.TARGET_041540 ->
            "00000000000000000004" + contract.banditRequestOpcode.toString(16).padStart(4, '0') +
                GameCoordinateCodec.encodeXY(x, y)
        RecoveredSearchKind.RESOURCE_POINT_041542 -> GameCoordinateCodec.buildResourcePointSearch(x, y)
    }
}

enum class RecoveredSearchKind { TARGET_041540, RESOURCE_POINT_041542 }

data class RecoveredScanShard(
    val threadIndex: Int,
    val threadCount: Int,
    val xStart: Int,
    val xEnd: Int,
    val yStart: Int,
    val yEnd: Int,
    val step: Int
) {
    fun coordinates(): List<MapCoordinate> {
        val out = mutableListOf<MapCoordinate>()
        var x = xStart
        while (x <= xEnd) {
            var y = yStart
            while (y <= yEnd) {
                out += MapCoordinate(x, y)
                y += step
            }
            x += step
        }
        return out
    }
}

data class RecoveredSearchRequest(
    val kind: RecoveredSearchKind,
    val coordinate: MapCoordinate,
    val gameHex: String
)
