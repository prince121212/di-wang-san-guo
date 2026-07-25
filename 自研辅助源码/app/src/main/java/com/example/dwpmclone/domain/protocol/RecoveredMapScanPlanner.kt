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

    fun shard(threadIndex: Int, threadCount: Int): RecoveredScanShard {
        require(threadCount > 0) { "threadCount must be positive" }
        require(threadIndex in 0 until threadCount) { "threadIndex must be in 0 until threadCount" }
        val slice = WORLD_X_MAX.toDouble() / threadCount.toDouble()
        val xStart = (((threadIndex * slice) / STEP).toInt()) * STEP
        val xEnd = ((((threadIndex + 1) * slice) / STEP).toInt()) * STEP
        return RecoveredScanShard(
            threadIndex = threadIndex,
            threadCount = threadCount,
            xStart = xStart,
            xEnd = xEnd,
            yStart = 0,
            yEnd = WORLD_Y_MAX,
            step = STEP
        )
    }

    fun shards(threadCount: Int): List<RecoveredScanShard> =
        (0 until threadCount).map { shard(it, threadCount) }

    fun requests(kind: RecoveredSearchKind, shard: RecoveredScanShard): List<RecoveredSearchRequest> =
        shard.coordinates().map { coordinate ->
            RecoveredSearchRequest(
                kind = kind,
                coordinate = coordinate,
                gameHex = buildGameHex(kind, coordinate.x, coordinate.y)
            )
        }

    fun fullScanRequests(kind: RecoveredSearchKind, threadCount: Int = 1): List<RecoveredSearchRequest> =
        shards(threadCount).flatMap { requests(kind, it) }

    fun fullScanRequestsDeduped(kind: RecoveredSearchKind, threadCount: Int): List<RecoveredSearchRequest> =
        fullScanRequests(kind, threadCount).distinctBy { it.coordinate }

    fun singleRequest(kind: RecoveredSearchKind, coordinate: MapCoordinate): RecoveredSearchRequest =
        RecoveredSearchRequest(kind, coordinate, buildGameHex(kind, coordinate.x, coordinate.y))

    /**
     * Mirrors the desktop helper's center-first scan order. Coordinates remain on the
     * six-tile lattice relative to the configured center, then sort by distance.
     */
    fun nearbyRequests(
        kind: RecoveredSearchKind,
        center: MapCoordinate,
        limit: Int = 80
    ): List<RecoveredSearchRequest> {
        val cx = center.x.coerceIn(0, WORLD_X_MAX)
        val cy = center.y.coerceIn(0, WORLD_Y_MAX)
        return buildList {
            for (dx in -WORLD_X_MAX..WORLD_X_MAX step STEP) {
                for (dy in -WORLD_Y_MAX..WORLD_Y_MAX step STEP) {
                    val x = cx + dx
                    val y = cy + dy
                    if (x in 0..WORLD_X_MAX && y in 0..WORLD_Y_MAX) {
                        add(MapCoordinate(x, y))
                    }
                }
            }
        }
            .sortedWith(compareBy<MapCoordinate>(
                { (it.x - cx) * (it.x - cx) + (it.y - cy) * (it.y - cy) },
                { kotlin.math.abs(it.x - cx) + kotlin.math.abs(it.y - cy) },
                { it.x },
                { it.y }
            ))
            .take(limit.coerceIn(1, 384))
            .map { singleRequest(kind, it) }
    }

    fun mineScopeRequests(
        kind: RecoveredSearchKind,
        center: MapCoordinate,
        scope: String
    ): List<RecoveredSearchRequest> = when (scope) {
        "定点" -> listOf(singleRequest(kind, center))
        "全国" -> nearbyRequests(kind, center, 384)
        else -> nearbyRequests(kind, center, 80)
    }

    fun buildGameHex(kind: RecoveredSearchKind, x: Int, y: Int): String = when (kind) {
        RecoveredSearchKind.TARGET_041540 -> GameCoordinateCodec.buildTargetSearch(x, y)
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
