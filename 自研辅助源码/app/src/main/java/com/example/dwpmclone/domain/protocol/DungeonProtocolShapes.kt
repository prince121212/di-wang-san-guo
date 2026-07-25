package com.example.dwpmclone.domain.protocol

import java.nio.ByteBuffer

/**
 * Local-only protocol shape helpers recovered from the auto fuben and auto chuangguan paths.
 *
 * These helpers intentionally model string-building and fixed-offset parsing only. They do
 * not include host URLs, session/key/passCode material, signatures, credentials, or
 * network execution.
 */
object DungeonProtocolShapes {
    private val staticStageCodes = mapOf(
        0 to listOf(0, 1, 2) + (4..12),
        1 to listOf(3) + (13..23),
        2 to (24..37).toList(),
        3 to (38..51).toList(),
        4 to (52..62).toList(),
        5 to (63..74).toList(),
        6 to (75..85).toList()
    )

    const val STATUS_QUERY: String = "00000000000000000001190000"
    const val STATE_STEP_902: String = "00000000000000000001190200"
    const val STATE_STEP_904: String = "00000000000000000001190400"
    const val STATE_STEP_906: String = "00000000000000000001190600"

    /** Recovered auto fuben queries used by ۦ۬ۧ(): 001930=list/target parser, 001938=status/result. */
    const val FUBEN_TARGET_QUERY: String = "000000000000000000001930"
    const val FUBEN_STATUS_QUERY: String = "000000000000000000001938"

    private const val PREFIX = "000000000000000000"
    private const val SECOND_TAIL = "ffffffffffffffff000000"
    private const val FUBEN_TRAILER = "ffffffff0004"

    fun stageCount(chapter: Int): Int = staticStageCodes[chapter]?.size ?: 0

    fun resolveStageCode(chapter: Int, displayStage: Int): Int {
        val stages = staticStageCodes[chapter]
            ?: throw IllegalArgumentException("unsupported dungeon chapter: ${chapter + 1}")
        require(displayStage in 1..stages.size) {
            "chapter ${chapter + 1} has ${stages.size} stages, requested $displayStage"
        }
        return stages[displayStage - 1]
    }

    fun resolveStageCode(
        catalog: DungeonCatalog,
        chapter: Int,
        displayStage: Int
    ): Int {
        val serverChapter = catalog.chapters.firstOrNull { it.chapterId == chapter }
        if (serverChapter != null && serverChapter.stages.isNotEmpty()) {
            require(displayStage in 1..serverChapter.stages.size) {
                "server chapter ${chapter + 1} has ${serverChapter.stages.size} stages, requested $displayStage"
            }
            return serverChapter.stages[displayStage - 1].stageCode
        }
        return resolveStageCode(chapter, displayStage)
    }

    /**
     * 0x8930 response. Captured chapter and stage ids are zero based. The UI stage is
     * one based and must select the corresponding entry instead of being sent directly.
     */
    fun parseCatalog(payload: ByteArray): DungeonCatalog {
        require(payload.size >= 2) { "0x8930 payload too short" }
        var p = 0
        fun u8(): Int {
            require(p < payload.size) { "0x8930 byte out of bounds at $p" }
            return payload[p++].toInt() and 0xff
        }
        fun u16(): Int {
            require(p + 2 <= payload.size) { "0x8930 short out of bounds at $p" }
            val value = ((payload[p].toInt() and 0xff) shl 8) or
                (payload[p + 1].toInt() and 0xff)
            p += 2
            return value
        }
        fun utf(): String {
            val length = u16()
            require(p + length <= payload.size) { "0x8930 utf out of bounds at $p length=$length" }
            return payload.copyOfRange(p, p + length)
                .toString(Charsets.UTF_8)
                .also { p += length }
        }

        val status = u8()
        require(status == 0) { "0x8930 returned status=$status" }
        val chapterCount = u8()
        require(chapterCount in 1..32) { "0x8930 invalid chapter count=$chapterCount" }
        val chapters = buildList {
            repeat(chapterCount) { displayIndex ->
                val chapterId = u16()
                val coords = listOf(u16(), u16(), u16())
                val name = utf()
                val detailFlag = u8()
                require(detailFlag in 0..1) {
                    "0x8930 invalid detail flag=$detailFlag chapter=$chapterId"
                }
                val stages = if (detailFlag == 1) {
                    val stageCount = u8()
                    require(stageCount <= 64) {
                        "0x8930 invalid stage count=$stageCount chapter=$chapterId"
                    }
                    buildList {
                        repeat(stageCount) { stageIndex ->
                            add(
                                DungeonCatalogStage(
                                    displayStage = stageIndex + 1,
                                    stageCode = u16(),
                                    availableCode = u8(),
                                    resultCode = u8()
                                )
                            )
                        }
                    }
                } else {
                    emptyList()
                }
                add(
                    DungeonCatalogChapter(
                        displayChapter = displayIndex + 1,
                        chapterId = chapterId,
                        name = name,
                        coords = coords,
                        stages = stages
                    )
                )
            }
        }
        return DungeonCatalog(status, chapters, p, payload.size)
    }

    fun parseBattleState(payload: ByteArray): DungeonBattleStatus {
        require(payload.isNotEmpty()) { "0x8938 payload empty" }
        val status = payload[0].toInt() and 0xff
        return when (status) {
            0 -> {
                require(payload.size == 1) { "0x8938 idle payload has unexpected bytes" }
                DungeonBattleStatus(DungeonBattlePhase.IDLE)
            }
            1 -> {
                require(payload.size >= 10) { "0x8938 active payload too short" }
                DungeonBattleStatus(
                    phase = DungeonBattlePhase.FIGHTING,
                    battleId = ByteBuffer.wrap(payload, 1, 8).long,
                    tailCode = payload[9].toInt() and 0xff
                )
            }
            4 -> DungeonBattleStatus(DungeonBattlePhase.SETTLEMENT)
            else -> DungeonBattleStatus(DungeonBattlePhase.UNKNOWN, rawStatus = status)
        }
    }

    fun parseRewardState(payload: ByteArray): DungeonRewardStatus {
        require(payload.isNotEmpty()) { "0x893d payload empty" }
        val status = payload[0].toInt() and 0xff
        val battleId = if (status == 1) {
            require(payload.size >= 9) { "0x893d active payload too short" }
            ByteBuffer.wrap(payload, 1, 8).long
        } else {
            null
        }
        return DungeonRewardStatus(status, battleId)
    }

    fun buildBattlePollPayload(firstPoll: Boolean, battleId: Long): ByteArray =
        ByteBuffer.allocate(9)
            .put(if (firstPoll) 2 else 1)
            .putLong(battleId)
            .array()

    fun parseLaunchResponse(payload: ByteArray): DungeonActionReceipt {
        require(payload.isNotEmpty()) { "0x8522 payload empty" }
        val first = payload[0].toInt() and 0xff
        val text = payload.toString(Charsets.UTF_8)
        val success = first == 0 || text.contains("副本启动成功")
        return DungeonActionReceipt(success, first, text)
    }

    fun parseChestResponse(payload: ByteArray): DungeonActionReceipt {
        require(payload.isNotEmpty()) { "0x893e payload empty" }
        val first = payload[0].toInt() and 0xff
        return DungeonActionReceipt(
            success = first != 0xff,
            status = first,
            message = payload.toString(Charsets.UTF_8)
        )
    }

    fun buildPreparePayload(generalIds: List<Long>, stageCode: Int): ByteArray {
        require(generalIds.isNotEmpty()) { "at least one general is required" }
        require(generalIds.size <= 0xff) { "too many generals" }
        require(generalIds.all { it > 0 }) { "general ids must be positive" }
        require(stageCode in 0..0xffff) { "stage code must fit unsigned short" }
        return ByteBuffer.allocate(2 + generalIds.size * 8 + 8)
            .put(0x0e)
            .put(generalIds.size.toByte())
            .also { buffer -> generalIds.forEach(buffer::putLong) }
            .putInt(-1)
            .putShort(4)
            .putShort(stageCode.toShort())
            .array()
    }

    fun buildExpeditionPayload(generalIds: List<Long>, stageCode: Int): ByteArray =
        ByteBuffer.allocate(buildPreparePayload(generalIds, stageCode).size + 11)
            .put(buildPreparePayload(generalIds, stageCode))
            .putLong(-1L)
            .put(byteArrayOf(0, 0, 0))
            .array()

    fun buildOpenChestPayload(position: Int): ByteArray {
        require(position in 0..2) { "chest position must be 0, 1, or 2" }
        return byteArrayOf(position.toByte())
    }

    /**
     * Recovered p2=4 first expedition stage used by auto chuangguan.
     *
     * Shape:
     * 000... + hex(n*8+0x0a) + 15200b0 + n + concat(generalIds) + ownerId
     */
    fun buildDungeonFirstStage(generalIds: List<String>, ownerId: String): String {
        val idsBlob = generalIds.joinToString(separator = "")
        val lenHex = (generalIds.size * 8 + 0x0a).toString(radix = 16)
        return PREFIX + lenHex + "15200b0" + generalIds.size + idsBlob + ownerId
    }

    /**
     * Recovered p2=4 second expedition stage used by auto chuangguan.
     *
     * Shape:
     * 000... + hex(n*8+0x15) + 15220b0 + n + concat(generalIds) + ownerId
     * + ffffffffffffffff000000
     */
    fun buildDungeonSecondStage(generalIds: List<String>, ownerId: String): String {
        val idsBlob = generalIds.joinToString(separator = "")
        val lenHex = (generalIds.size * 8 + 0x15).toString(radix = 16)
        return PREFIX + lenHex + "15220b0" + generalIds.size + idsBlob + ownerId + SECOND_TAIL
    }

    /**
     * Recovered p2=2 first expedition stage used by auto fuben.
     *
     * Shape:
     * 000... + hex(n*8+0x0a) + 15200e0 + n + concat(generalIds) + ffffffff0004 + fubenTargetId
     */
    fun buildAutoFubenFirstStage(generalIds: List<String>, fubenTargetId: String): String {
        val idsBlob = generalIds.joinToString(separator = "")
        val lenHex = (generalIds.size * 8 + 0x0a).toString(radix = 16)
        return PREFIX + lenHex + "15200e0" + generalIds.size + idsBlob + FUBEN_TRAILER + fubenTargetId
    }

    /**
     * Recovered p2=2 second expedition stage used by auto fuben.
     *
     * Shape:
     * 000... + hex(n*8+0x15) + 15220e0 + n + concat(generalIds) + ffffffff0004 + fubenTargetId
     * + ffffffffffffffff000000
     */
    fun buildAutoFubenSecondStage(generalIds: List<String>, fubenTargetId: String): String {
        val idsBlob = generalIds.joinToString(separator = "")
        val lenHex = (generalIds.size * 8 + 0x15).toString(radix = 16)
        return PREFIX + lenHex + "15220e0" + generalIds.size + idsBlob + FUBEN_TRAILER + fubenTargetId + SECOND_TAIL
    }

    /**
     * Local fixed-offset parser shape recovered from Landroid/o/ۦۡۧ;->ۦۚۛ(String): int[].
     *
     * The original code assumes a long enough response. This safe model returns null when
     * offsets are unavailable.
     */
    fun parseStatusShape(response: String): DungeonStatusShape? {
        if (response.length <= 0x5b) return null
        val raw = response.substring(0x3f, 0x40)
        val aux = response.substring(0x5b, 0x5c).toIntOrNull(radix = 16) ?: 0
        val state = when (raw) {
            "2" -> DungeonState.IDLE
            "1" -> DungeonState.STATE_ONE
            "0" -> DungeonState.COOLDOWN
            "3" -> DungeonState.FIGHTING
            else -> DungeonState.UNKNOWN
        }
        val cooldownSeconds = if (state == DungeonState.COOLDOWN && response.length >= 0x58) {
            response.substring(0x48, 0x58).toLongOrNull(radix = 16)?.div(1000)
        } else {
            null
        }
        return DungeonStatusShape(state = state, auxHexNibble = aux, cooldownSeconds = cooldownSeconds)
    }
}

data class DungeonCatalog(
    val status: Int,
    val chapters: List<DungeonCatalogChapter>,
    val parsedBytes: Int,
    val payloadBytes: Int
)

data class DungeonCatalogChapter(
    val displayChapter: Int,
    val chapterId: Int,
    val name: String,
    val coords: List<Int>,
    val stages: List<DungeonCatalogStage>
)

data class DungeonCatalogStage(
    val displayStage: Int,
    val stageCode: Int,
    val availableCode: Int,
    val resultCode: Int
) {
    val available: Boolean get() = availableCode != 0
}

data class DungeonBattleStatus(
    val phase: DungeonBattlePhase,
    val battleId: Long? = null,
    val tailCode: Int? = null,
    val rawStatus: Int = phase.protocolStatus
)

enum class DungeonBattlePhase(val protocolStatus: Int) {
    IDLE(0),
    FIGHTING(1),
    SETTLEMENT(4),
    UNKNOWN(-1)
}

data class DungeonRewardStatus(
    val status: Int,
    val battleId: Long?
)

data class DungeonActionReceipt(
    val success: Boolean,
    val status: Int,
    val message: String
)

data class DungeonStatusShape(
    val state: DungeonState,
    val auxHexNibble: Int,
    val cooldownSeconds: Long?,
)

enum class DungeonState(val originalIntValue: Int) {
    COOLDOWN(0),
    STATE_ONE(1),
    IDLE(2),
    FIGHTING(3),
    UNKNOWN(4),
}
