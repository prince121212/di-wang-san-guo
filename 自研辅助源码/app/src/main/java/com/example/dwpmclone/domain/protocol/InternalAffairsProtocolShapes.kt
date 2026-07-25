package com.example.dwpmclone.domain.protocol

import java.nio.ByteBuffer

/**
 * Local-only protocol shape helpers recovered from the "auto internal affairs" path.
 *
 * These helpers intentionally model string-building, local selection mapping, and mock
 * planning only. They do not include host URLs, session/key/passCode material,
 * signatures, credentials, or network execution.
 */
object InternalAffairsProtocolShapes {
    private const val PREFIX = "0000000000000000000d12000"

    fun buildFiefQueryPayload(fiefId: Long, mode: Int = 0): ByteArray {
        require(fiefId > 0) { "fiefId must be positive" }
        require(mode in 0..0xff) { "mode must fit unsigned byte" }
        return ByteBuffer.allocate(9).put(mode.toByte()).putLong(fiefId).array()
    }

    fun buildBuildingActionPayload(
        fiefId: Long,
        slot: Int,
        buildingTypeId: Int,
        action: Int = 0
    ): ByteArray {
        require(fiefId > 0) { "fiefId must be positive" }
        require(action in 0..0xff) { "action must fit unsigned byte" }
        require(slot in 0..0xffff) { "slot must fit unsigned short" }
        require(buildingTypeId in 0..0xffff) { "building type must fit unsigned short" }
        return ByteBuffer.allocate(13)
            .put(action.toByte())
            .putLong(fiefId)
            .putShort(slot.toShort())
            .putShort(buildingTypeId.toShort())
            .array()
    }

    fun buildTechnologyUpgradePayload(
        fiefId: Long,
        academySlot: Int,
        technologyId: Int,
        targetLevel: Int,
        mode: Int = 0,
        useGold: Int = 0
    ): ByteArray {
        require(fiefId > 0) { "fiefId must be positive" }
        require(academySlot in 0..0xff) { "academy slot must fit unsigned byte" }
        require(technologyId in 0..21) { "technology id must be in 0..21" }
        require(targetLevel in 1..15) { "technology target level must be in 1..15" }
        require(mode in 0..0xff && useGold in 0..0xff) { "technology flags must fit unsigned byte" }
        return ByteBuffer.allocate(14)
            .putLong(fiefId)
            .put(academySlot.toByte())
            .putShort(technologyId.toShort())
            .put(targetLevel.toByte())
            .put(mode.toByte())
            .put(useGold.toByte())
            .array()
    }

    fun parseTechnologyStatesFrom8004(payload: ByteArray): List<InternalTechnologyState> {
        val recordSize = 27
        val count = 22
        val candidates = mutableListOf<List<InternalTechnologyState>>()
        for (offset in 0..(payload.size - recordSize * count).coerceAtLeast(-1)) {
            val rows = mutableListOf<InternalTechnologyState>()
            var plausible = true
            repeat(count) { index ->
                val p = offset + index * recordSize
                if (p + recordSize > payload.size ||
                    (payload[p].toInt() and 0xff) != index
                ) {
                    plausible = false
                    return@repeat
                }
                val level = payload[p + 1].toInt() and 0xff
                val state = payload[p + 2].toInt() and 0xff
                if (level > 15 || state > 10) {
                    plausible = false
                    return@repeat
                }
                val fiefId = ByteBuffer.wrap(payload, p + 3, 8).long
                val academyId = ByteBuffer.wrap(payload, p + 11, 8).long
                val deadline = ByteBuffer.wrap(payload, p + 19, 8).long
                rows += InternalTechnologyState(
                    technologyId = index,
                    level = level,
                    state = state,
                    researching = fiefId >= 0 && academyId >= 0 && deadline > 0,
                    fiefId = fiefId.takeIf { it >= 0 },
                    academyInstanceId = academyId.takeIf { it >= 0 },
                    deadlineMs = deadline
                )
            }
            if (plausible && rows.size == count) candidates += rows
        }
        require(candidates.size == 1) { "0x8004 technology table candidates=${candidates.size}" }
        return candidates.single()
    }

    fun parseFiefBuildings(payload: ByteArray, expectedFiefId: Long): List<InternalBuildingShape> {
        return parseFiefState(payload, expectedFiefId).buildings
    }

    fun parseFiefState(payload: ByteArray, expectedFiefId: Long): InternalFiefState {
        require(payload.size >= 12) { "0x8246 response too short" }
        require(payload[0].toInt() == 0) { "0x8246 status=${payload[0].toInt()}" }
        require(ByteBuffer.wrap(payload, 1, 8).long == expectedFiefId) { "0x8246 fief mismatch" }
        val candidates = mutableListOf<Pair<Int, List<InternalBuildingShape>>>()
        for (offset in 9 until payload.size) {
            parseBuildingList(payload, offset)?.let { (buildings, end) ->
                val slots = buildings.map { it.slotOrIndex }
                if (end == payload.size && slots.distinct().size == slots.size &&
                    buildings.all { it.typeId in setOf(0, 1, 2, 3, 4, 5, 6, 8) }) {
                    candidates += offset to buildings
                }
            }
        }
        require(candidates.size == 1) { "0x8246 building list candidates=${candidates.size}" }
        val (buildingOffset, buildings) = candidates.single()
        val base = parseFiefBase(payload, 9, buildingOffset)
        return InternalFiefState(
            fiefId = expectedFiefId,
            name = base.name,
            buildQueueCapacity = base.buildQueueCapacity,
            buildQueueRemainingMs = base.buildQueueRemainingMs,
            buildings = buildings
        )
    }

    private fun parseBuildingList(
        payload: ByteArray,
        offset: Int
    ): Pair<List<InternalBuildingShape>, Int>? = runCatching {
        var p = offset
        fun u8(): Int = payload[p++].toInt() and 0xff
        fun i32(): Int = ByteBuffer.wrap(payload, p, 4).int.also { p += 4 }
        fun i64(): Long = ByteBuffer.wrap(payload, p, 8).long.also { p += 8 }
        val count = u8()
        require(count <= 32)
        val out = mutableListOf<InternalBuildingShape>()
        repeat(count) {
            require(p + 28 <= payload.size)
            val slot = u8()
            val instanceId = i64()
            val type = payload[p++].toInt()
            val level = u8()
            val timer = i32()
            i32() // progress
            i64() // state sign
            val nestedAction = u8()
            when (nestedAction) {
                0 -> i64()
                1 -> {
                    i64()
                    val taskCount = u8()
                    repeat(taskCount) {
                        require(p + 32 <= payload.size)
                        p += 32
                    }
                }
                else -> error("unknown nested action")
            }
            out += InternalBuildingShape(slot, type, level, timer.toLong(), instanceId)
        }
        out to p
    }.getOrNull()

    fun parseBuildingActionResponse(payload: ByteArray): InternalBuildingActionReceipt {
        require(payload.size >= 11) { "0x8200 response too short" }
        val status = payload[0].toInt()
        val substatus = payload[1].toInt()
        val fiefId = ByteBuffer.wrap(payload, 2, 8).long
        val parsed = parseBuildingList(payload, 10)
            ?: error("0x8200 building list invalid")
        require(parsed.second == payload.size) { "0x8200 trailing bytes=${payload.size - parsed.second}" }
        return InternalBuildingActionReceipt(
            success = status == 0 && substatus == 0,
            status = status,
            substatus = substatus,
            fiefId = fiefId,
            buildings = parsed.first
        )
    }

    fun actionWasApplied(
        receipt: InternalBuildingActionReceipt,
        expectedFiefId: Long,
        slot: Int,
        buildingTypeId: Int,
        previousLevel: Int?
    ): Boolean {
        if (!receipt.success || receipt.fiefId != expectedFiefId) return false
        val building = receipt.buildings.firstOrNull {
            it.slotOrIndex == slot && it.typeId == buildingTypeId
        } ?: return false
        return previousLevel == null || building.rank > previousLevel || building.busy
    }

    fun buildingLevelLimit(fief: InternalFiefState, buildingTypeId: Int): Int =
        if (buildingTypeId in setOf(4, 5, 6, 8)) 10
        else if ("基地" in fief.name) 15 else 10

    fun hallMustUpgradeFirst(fief: InternalFiefState): Boolean {
        val hall = fief.buildings.firstOrNull { it.typeId == 0 } ?: return false
        if (hall.busy) return false
        val otherLevels = fief.buildings.filter { it.typeId > 0 }.map { it.rank }
        return hall.rank < buildingLevelLimit(fief, 0) &&
            (otherLevels.isEmpty() || otherLevels.max() >= hall.rank)
    }

    fun buildingCanFollowHall(fief: InternalFiefState, building: InternalBuildingShape): Boolean {
        val hall = fief.buildings.firstOrNull { it.typeId == 0 } ?: return false
        return building.typeId > 0 && !building.busy &&
            building.rank < hall.rank &&
            building.rank < buildingLevelLimit(fief, building.typeId)
    }

    fun nextCheckDelayMillis(fiefs: List<InternalFiefState>): Long {
        val halls = fiefs.map { fief -> fief.buildings.firstOrNull { it.typeId == 0 } }
        return if (halls.isNotEmpty() && halls.all { it != null && it.rank >= 7 }) {
            60L * 60L * 1_000L
        } else {
            10L * 60L * 1_000L
        }
    }

    private data class ParsedFiefBase(
        val name: String,
        val buildQueueCapacity: Int,
        val buildQueueRemainingMs: Long
    )

    private fun parseFiefBase(payload: ByteArray, start: Int, end: Int): ParsedFiefBase {
        var p = start
        fun take(size: Int): ByteArray {
            require(size >= 0 && p + size <= end) { "0x8246 fief base truncated" }
            return payload.copyOfRange(p, p + size).also { p += size }
        }
        fun u8(): Int = take(1)[0].toInt() and 0xff
        fun i16(): Int = ByteBuffer.wrap(take(2)).short.toInt()
        fun i32(): Int = ByteBuffer.wrap(take(4)).int
        fun i64(): Long = ByteBuffer.wrap(take(8)).long
        fun utf(): String {
            val length = (u8() shl 8) or u8()
            return take(length).toString(Charsets.UTF_8)
        }
        u8()
        u8()
        val name = utf()
        i64()
        i32()
        i32()
        i16()
        i16()
        val baseQueueCapacity = u8()
        i16()
        i16()
        u8()
        fun buffGroup(): List<Pair<Int, Long>> = List(u8()) {
            val value = u8()
            val remainingMs = i64()
            u8()
            value to remainingMs
        }
        buffGroup()
        buffGroup()
        val queueBoosts = buffGroup()
        repeat(2) {
            repeat(u8()) {
                u8()
                i32()
            }
        }
        require(p == end) { "0x8246 fief base trailing bytes=${end - p}" }
        val activeCapacity = queueBoosts.firstOrNull { (value, remaining) ->
            value > 0 && remaining > 0
        }?.first
        return ParsedFiefBase(
            name = name,
            buildQueueCapacity = activeCapacity ?: maxOf(1, baseQueueCapacity.takeIf { it > 0 } ?: 2),
            buildQueueRemainingMs = queueBoosts.maxOfOrNull { it.second } ?: 0L
        )
    }

    fun buildingTypeId(type: com.example.dwpmclone.domain.model.BuildingType): Int = when (type) {
        com.example.dwpmclone.domain.model.BuildingType.HOUSE,
        com.example.dwpmclone.domain.model.BuildingType.MONEY -> 1
        com.example.dwpmclone.domain.model.BuildingType.FOOD -> 2
        com.example.dwpmclone.domain.model.BuildingType.ACADEMY -> 3
        com.example.dwpmclone.domain.model.BuildingType.INFANTRY_CAMP -> 4
        com.example.dwpmclone.domain.model.BuildingType.ARCHER_CAMP -> 5
        com.example.dwpmclone.domain.model.BuildingType.CHARIOT_CAMP -> 6
        com.example.dwpmclone.domain.model.BuildingType.CAVALRY_CAMP -> 8
        else -> -1
    }

    fun buildOrUpgradePayload(
        fiefId: String,
        slotOrBuildingIndex: Int,
        buildingTypeId: Int,
        action: Int = 0,
    ): String {
        require(slotOrBuildingIndex in 0..0xff) { "slotOrBuildingIndex must fit one byte" }
        val slotHex = slotOrBuildingIndex.toString(radix = 16).padStart(2, '0')
        return PREFIX + action + fiefId + "00" + slotHex + "000" + buildingTypeId
    }

    fun selectionToBuildingTypeId(selection: Int): Int = when (selection) {
        0 -> -1
        1 -> 0 // 大厅
        2 -> 1 // 房屋
        3 -> 2 // 农田
        4 -> 3 // 书院
        5 -> 4 // 步兵营
        6 -> 5 // 弓兵营
        7 -> 6 // 战车营
        8 -> 8 // 骑兵营
        else -> 1
    }

    fun buildingName(typeId: Int): String = when (typeId) {
        0 -> "大厅"
        1 -> "房屋"
        2 -> "农田"
        3 -> "书院"
        4 -> "步兵营"
        5 -> "弓兵营"
        6 -> "战车营"
        7 -> "未知"
        8 -> "骑兵营"
        else -> "未知"
    }

    fun isUpgradeCandidate(fief: InternalFiefShape, building: InternalBuildingShape): Boolean {
        val maxRank = if (fief.name == "基地" || fief.name == "43C4836E2063E1BBA900") 15 else 10
        return building.rank < maxRank
    }

    fun sortCandidates(candidates: List<InternalBuildingShape>, lowRankFirst: Boolean): List<InternalBuildingShape> =
        if (lowRankFirst) candidates.sortedBy { it.rank } else candidates.sortedByDescending { it.rank }

    /**
     * Mirrors the recovered static control-flow shape, including the priority pass followed
     * by the rank-sorted pass. Runtime server responses may still reject duplicates or full
     * queues; this skeleton does not perform real network execution.
     */
    fun planUpgradePayloads(
        fief: InternalFiefShape,
        lowRankFirst: Boolean,
        prioritySelections: List<Int>,
        maxBusyQueues: Int = 5,
    ): List<InternalAffairsAction> {
        val candidates = fief.buildings.filter { isUpgradeCandidate(fief, it) }
        if (candidates.isEmpty()) {
            return listOf(InternalAffairsAction.Log(fief.name + "全部满级，无需升级"))
        }
        if (fief.buildings.count { it.busy } >= maxBusyQueues) {
            return listOf(InternalAffairsAction.Log(fief.name + "没有空闲建筑队列"))
        }

        val actions = mutableListOf<InternalAffairsAction>()
        val priorityTypes = prioritySelections.take(9).map { selectionToBuildingTypeId(it) }
        for (type in priorityTypes) {
            for (building in candidates) {
                if (building.typeId == type) {
                    actions += InternalAffairsAction.Payload(
                        buildOrUpgradePayload(fief.id, building.slotOrIndex, building.typeId),
                    )
                }
            }
        }

        for (building in sortCandidates(candidates, lowRankFirst)) {
            actions += InternalAffairsAction.Log(fief.name + "升级" + buildingName(building.typeId))
            actions += InternalAffairsAction.Payload(
                buildOrUpgradePayload(fief.id, building.slotOrIndex, building.typeId),
            )
        }
        return actions
    }

    fun planEmptySlotBuildPayloads(
        fief: InternalFiefShape,
        buildSelection: Int,
        slotCount: Int = 13,
    ): List<InternalAffairsAction> {
        val typeId = selectionToBuildingTypeId(buildSelection)
        if (typeId < 0) return emptyList()
        val occupiedSlots = fief.buildings.map { it.slotOrIndex }.toSet()
        return (0 until slotCount)
            .filter { it !in occupiedSlots }
            .flatMap { slot ->
                listOf(
                    InternalAffairsAction.Log("有空建筑，开始建设"),
                    InternalAffairsAction.Payload(buildOrUpgradePayload(fief.id, slot, typeId)),
                )
            }
    }
}

data class InternalFiefShape(
    val id: String,
    val name: String,
    val buildings: List<InternalBuildingShape>,
)

data class InternalBuildingShape(
    val slotOrIndex: Int,
    val typeId: Int,
    val rank: Int,
    val remainingTimeLikeValue: Long = 0L,
    val instanceId: Long = 0L
) {
    val busy: Boolean get() = remainingTimeLikeValue > 0L
}

data class InternalFiefState(
    val fiefId: Long,
    val name: String,
    val buildQueueCapacity: Int,
    val buildQueueRemainingMs: Long,
    val buildings: List<InternalBuildingShape>
)

data class InternalBuildingActionReceipt(
    val success: Boolean,
    val status: Int,
    val substatus: Int,
    val fiefId: Long,
    val buildings: List<InternalBuildingShape>
)

data class InternalTechnologyState(
    val technologyId: Int,
    val level: Int,
    val state: Int,
    val researching: Boolean,
    val fiefId: Long?,
    val academyInstanceId: Long?,
    val deadlineMs: Long
)

sealed interface InternalAffairsAction {
    data class Log(val message: String) : InternalAffairsAction
    data class Payload(val gameHex: String) : InternalAffairsAction
}
