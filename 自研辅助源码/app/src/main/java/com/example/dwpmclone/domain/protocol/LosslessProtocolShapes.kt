package com.example.dwpmclone.domain.protocol

import java.nio.ByteBuffer

data class LosslessStatus(
    val mode: Int,
    val remainingAttempts: Int,
    val progressCode: Int,
    val statusFlag: Int,
    val settlementPending: Boolean,
    val actionTimerMillis: Long,
    val cooldownMillis: Long?,
    val reopenCost: Int?,
    val selectedLevel: Int?,
    val stageId: Int?,
) {
    val phase: LosslessPhase
        get() = when {
            settlementPending -> LosslessPhase.SETTLEMENT
            remainingAttempts <= 0 || mode == 4 -> LosslessPhase.DAILY_DONE
            mode == 0 -> LosslessPhase.COOLDOWN
            mode == 3 -> LosslessPhase.FIGHTING
            mode == 1 || mode == 2 -> LosslessPhase.READY
            else -> LosslessPhase.UNKNOWN
        }
}

enum class LosslessPhase {
    SETTLEMENT,
    DAILY_DONE,
    COOLDOWN,
    FIGHTING,
    READY,
    UNKNOWN,
}

data class LosslessSelectResult(
    val success: Boolean,
    val status: Int,
    val message: String,
    val selectedLevel: Int,
    val stageId: Int,
)

data class LosslessEnemy(
    val position: Int,
    val generalName: String,
    val soldierType: String,
    val soldierCount: Int,
)

data class LosslessLineup(
    val success: Boolean,
    val status: Int,
    val stageId: Int,
    val levelName: String,
    val stageName: String,
    val enemies: List<LosslessEnemy>,
)

data class LosslessSettlement(
    val success: Boolean,
    val status: Int,
    val modeAfterSettlement: Int?,
    val battleId: Long?,
    val resultText: String,
    val generalText: String,
    val extraText: String,
) {
    val message: String
        get() = resultText.ifBlank {
            if (status == -1) "没有待结算的无损战报" else "无损结算状态=$status"
        }

    val battleFailed: Boolean
        get() = listOf(resultText, generalText, extraText).any { "失败" in it }
}

data class LosslessLineupVerdict(
    val qualified: Boolean,
    val reason: String,
    val chariotPositions: List<Int>,
    val catapultPositions: List<Int>,
)

/**
 * Wire shapes recovered from the desktop implementation and its real 2026-07 captures.
 * Every parser is strict: a short, malformed or semantically inconsistent response throws
 * and callers must fail closed before sending a battle command.
 */
object LosslessProtocolShapes {
    val QUERY_PAYLOAD: ByteArray = byteArrayOf(0)

    fun parseStatus(payload: ByteArray): LosslessStatus {
        require(payload.size >= 13) { "0x8900公共字段不足：${payload.size}/13" }
        val buffer = ByteBuffer.wrap(payload)
        val timer = buffer.long.coerceAtLeast(0)
        val mode = buffer.get().toInt() and 0xff
        val remaining = buffer.get().toInt() and 0xff
        val progress = buffer.get().toInt() and 0xff
        val statusFlag = buffer.get().toInt() and 0xff
        val settlement = buffer.get().toInt() != 0
        var cooldown: Long? = null
        var reopenCost: Int? = null
        var selectedLevel: Int? = null
        var stageId: Int? = null
        if (mode == 0) {
            require(buffer.remaining() >= 12) { "0x8900冷却字段不足：${payload.size}/25" }
            cooldown = buffer.long.coerceAtLeast(0)
            reopenCost = buffer.int
        } else {
            require(buffer.remaining() >= 10) { "0x8900关卡字段不足：${payload.size}/23" }
            val levelIndex = buffer.long
            val rawStageId = buffer.short.toInt()
            selectedLevel = if (levelIndex < 0) null else (levelIndex + 1).toInt()
            stageId = if (rawStageId < 0) null else rawStageId
        }
        return LosslessStatus(
            mode = mode,
            remainingAttempts = remaining,
            progressCode = progress,
            statusFlag = statusFlag,
            settlementPending = settlement,
            actionTimerMillis = timer,
            cooldownMillis = cooldown,
            reopenCost = reopenCost,
            selectedLevel = selectedLevel,
            stageId = stageId,
        )
    }

    fun buildSelectLevelPayload(level: Int): ByteArray {
        require(level in 1..10) { "无损等级必须为1..10" }
        return ByteBuffer.allocate(4).putInt(level).array()
    }

    fun parseSelect(payload: ByteArray): LosslessSelectResult {
        val buffer = ByteBuffer.wrap(payload)
        require(buffer.remaining() >= 4) { "0x8908数据不足" }
        val status = buffer.int
        val message = buffer.readUtf("0x8908提示")
        require(buffer.remaining() >= 10) { "0x8908缺少等级或阶段字段" }
        val levelIndex = buffer.long
        val stageId = buffer.short.toInt() and 0xffff
        require(levelIndex in 0..9) { "0x8908等级索引异常：$levelIndex" }
        return LosslessSelectResult(
            success = status == 1,
            status = status,
            message = message,
            selectedLevel = (levelIndex + 1).toInt(),
            stageId = stageId,
        )
    }

    fun parseLineup(payload: ByteArray): LosslessLineup {
        val buffer = ByteBuffer.wrap(payload)
        require(buffer.remaining() >= 3) { "0x8906数据不足" }
        val status = buffer.get().toInt() and 0xff
        val stageId = buffer.short.toInt() and 0xffff
        val levelName = buffer.readUtf("0x8906等级名")
        val stageName = buffer.readUtf("0x8906阶段名")
        require(buffer.remaining() >= 4) { "0x8906缺少敌军数量" }
        val count = buffer.int
        require(count in 0..50) { "0x8906敌军数量异常：$count" }
        val enemies = (0 until count).map { index ->
            val name = buffer.readUtf("0x8906第${index + 1}名敌将")
            require(buffer.remaining() >= 10) { "0x8906第${index + 1}名敌将字段不完整" }
            buffer.int
            buffer.short
            buffer.int
            val soldierType = buffer.readUtf("0x8906第${index + 1}名敌军兵种")
            require(buffer.remaining() >= 4) { "0x8906第${index + 1}名敌军缺少兵力" }
            LosslessEnemy(index + 1, name, soldierType, buffer.int)
        }
        return LosslessLineup(status == 0, status, stageId, levelName, stageName, enemies)
    }

    fun evaluateLevel10Guard(lineup: LosslessLineup): LosslessLineupVerdict {
        if (lineup.stageId != 0x3011 || lineup.stageName != "卫兵") {
            return LosslessLineupVerdict(true, "仅10级卫兵需要筛选阵容", emptyList(), emptyList())
        }
        val chariots = lineup.enemies.filter {
            listOf("弩车", "投石车", "冲车").any(it.soldierType::contains)
        }.map { it.position }
        val catapults = lineup.enemies.filter { "投石车" in it.soldierType }.map { it.position }
        val otherChariots = chariots - catapults.toSet()
        val qualified = lineup.enemies.size == 5 &&
            chariots.size >= 3 &&
            catapults.isNotEmpty() &&
            otherChariots.isNotEmpty() &&
            catapults.min() > otherChariots.max()
        val reason = when {
            lineup.enemies.size != 5 -> "敌军数量不是5"
            chariots.size < 3 -> "战车类少于3名"
            catapults.isEmpty() -> "没有投石车"
            otherChariots.isEmpty() -> "没有排在投石车之前的其他战车兵种"
            catapults.min() <= otherChariots.max() -> "投石车没有排在所有其他战车兵种之后"
            else -> "符合10级卫兵筛选条件"
        }
        return LosslessLineupVerdict(qualified, reason, chariots, catapults)
    }

    fun parseSettlement(payload: ByteArray): LosslessSettlement {
        require(payload.isNotEmpty()) { "0x8902空响应" }
        val buffer = ByteBuffer.wrap(payload)
        val status = buffer.get().toInt()
        if (status != 0) {
            return LosslessSettlement(false, status, null, null, "", "", "")
        }
        require(buffer.remaining() >= 9) { "0x8902成功响应字段不足" }
        val mode = buffer.get().toInt()
        val battleId = buffer.long
        val fields = ArrayList<String>(3)
        repeat(3) {
            if (buffer.remaining() >= 2) fields += buffer.readUtf("0x8902文本${it + 1}")
        }
        return LosslessSettlement(
            success = true,
            status = status,
            modeAfterSettlement = mode,
            battleId = battleId,
            resultText = fields.getOrElse(0) { "" },
            generalText = fields.getOrElse(1) { "" },
            extraText = fields.getOrElse(2) { "" },
        )
    }

    fun buildPreparePayload(generalIds: List<Long>, roleId: Long): ByteArray {
        require(generalIds.isNotEmpty()) { "无损至少需要选择1个出征将领" }
        require(generalIds.size <= 5) { "无损最多选择5个出征将领" }
        require(generalIds.all { it > 0 }) { "无损将领ID必须为正数" }
        require(roleId > 0) { "无损缺少角色ID" }
        return ByteBuffer.allocate(2 + generalIds.size * 8 + 8)
            .put(0x0b)
            .put(generalIds.size.toByte())
            .also { out -> generalIds.forEach(out::putLong) }
            .putLong(roleId)
            .array()
    }

    fun buildExpeditionPayload(generalIds: List<Long>, roleId: Long): ByteArray =
        ByteBuffer.allocate(buildPreparePayload(generalIds, roleId).size + 11)
            .put(buildPreparePayload(generalIds, roleId))
            .putLong(-1L)
            .put(byteArrayOf(0, 0, 0))
            .array()

    private fun ByteBuffer.readUtf(label: String): String {
        require(remaining() >= 2) { "$label 缺少长度" }
        val length = short.toInt() and 0xffff
        require(remaining() >= length) { "$label 长度越界：$length/${remaining()}" }
        return ByteArray(length).also(::get).toString(Charsets.UTF_8)
    }
}
