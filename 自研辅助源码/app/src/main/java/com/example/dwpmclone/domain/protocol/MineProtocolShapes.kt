package com.example.dwpmclone.domain.protocol

import java.nio.ByteBuffer

data class MineExpeditionPreview(
    val marchSeconds: Int,
    val arrivalAt: Long,
    val secondTime: Long,
    val winRate: Int,
    val x: Int,
    val y: Int,
    val trailingBytes: Int
)

data class MineSpeedReceipt(
    val success: Boolean,
    val finished: Boolean,
    val status: Int,
    val message: String
)

data class MineWithdrawReceipt(
    val success: Boolean,
    val battleId: Long,
    val message: String
)

/** Pure protocol shapes shared by manual execution, the scheduler and parity fixtures. */
object MineProtocolShapes {
    fun buildPreparePayload(
        generalIds: List<Long>,
        targetId: Long,
        contract: MineBehaviorContract = MineBehaviorContract.defaults()
    ): ByteArray = dispatchPrefix(generalIds, targetId, contract)

    fun buildDispatchPayload(
        generalIds: List<Long>,
        targetId: Long,
        contract: MineBehaviorContract = MineBehaviorContract.defaults()
    ): ByteArray = dispatchPrefix(generalIds, targetId, contract) +
        ByteBuffer.allocate(11)
            .putLong(-1L)
            .put(byteArrayOf(0, 0, 0))
            .array()

    fun parsePreview(
        payload: ByteArray,
        contract: MineBehaviorContract = MineBehaviorContract.defaults()
    ): MineExpeditionPreview? {
        if (payload.size < contract.preview.minimumPayloadBytes) return null
        val buffer = ByteBuffer.wrap(payload)
        val marchSeconds = buffer.int
        if (marchSeconds < 0) return null
        return MineExpeditionPreview(
            marchSeconds = marchSeconds,
            arrivalAt = buffer.long,
            secondTime = buffer.long,
            winRate = buffer.get().toInt() and 0xff,
            x = buffer.short.toInt() and 0xffff,
            y = buffer.short.toInt() and 0xffff,
            trailingBytes = payload.size - contract.preview.minimumPayloadBytes
        )
    }

    fun buildSpeedPayload(battleId: Long, itemId: Int): ByteArray {
        require(battleId > 0L) { "行军加速缺少有效 battleId" }
        require(itemId in 0..0xffff) { "行军符编号超出协议范围" }
        return ByteBuffer.allocate(10).putLong(battleId).putShort(itemId.toShort()).array()
    }

    fun parseSpeedReceipt(payload: ByteArray): MineSpeedReceipt? {
        if (payload.isEmpty()) return null
        val status = payload[0].toInt()
        return MineSpeedReceipt(
            success = status == 0,
            finished = status == -2,
            status = status,
            message = when (status) {
                0 -> "行军加速成功"
                -1 -> "行军加速失败"
                -2 -> "行军已经结束"
                -3 -> "自动VIP状态下无法使用行军符"
                else -> "行军加速未知状态 $status"
            }
        )
    }

    fun chooseSpeedItems(
        remainingSeconds: Int,
        inventoryCounts: Map<Int, Int>,
        contract: MineSpeedBehaviorContract = MineSpeedBehaviorContract.defaults()
    ): List<Int> {
        val requiredSeconds = (remainingSeconds - contract.stopBelowSeconds).coerceAtLeast(0)
        if (requiredSeconds <= 0) return emptyList()
        val itemIds = contract.itemSeconds.keys.sorted()
        val counts = itemIds.associateWith { (inventoryCounts[it] ?: 0).coerceAtLeast(0) }
        val availableSeconds = itemIds.sumOf { itemId ->
            counts.getValue(itemId) * contract.itemSeconds.getValue(itemId)
        }
        if (availableSeconds < requiredSeconds) {
            return itemIds.sortedDescending().flatMap { itemId ->
                List(counts.getValue(itemId)) { itemId }
            }
        }

        val baseUnit = contract.itemSeconds.values.reduce(::gcd)
        val targetUnits = (requiredSeconds + baseUnit - 1) / baseUnit
        val maxUnits = targetUnits + 11
        val itemUnits = itemIds.associateWith { contract.itemSeconds.getValue(it) / baseUnit }
        val states = linkedMapOf(0 to List(itemIds.size) { 0 })
        itemIds.forEachIndexed { index, itemId ->
            val usable = minOf(
                counts.getValue(itemId),
                maxUnits / itemUnits.getValue(itemId) + 1
            )
            repeat(usable) {
                states.toList().forEach { (total, combo) ->
                    val nextTotal = total + itemUnits.getValue(itemId)
                    if (nextTotal > maxUnits) return@forEach
                    val candidate = combo.toMutableList().also { it[index] += 1 }.toList()
                    val current = states[nextTotal]
                    if (current == null || preferred(candidate, current)) {
                        states[nextTotal] = candidate
                    }
                }
            }
        }
        val winningTotal = states.keys.filter { it >= targetUnits }.minOrNull()
            ?: return emptyList()
        val winning = states.getValue(winningTotal)
        return itemIds.sortedDescending().flatMap { itemId ->
            List(winning[itemIds.indexOf(itemId)]) { itemId }
        }
    }

    fun buildWithdrawPayload(
        battleId: Long,
        contract: MineWithdrawBehaviorContract = MineWithdrawBehaviorContract.defaults()
    ): ByteArray {
        require(battleId > 0L) { "撤防缺少有效 battleId" }
        return contract.payloadPrefix +
            ByteBuffer.allocate(Long.SIZE_BYTES).putLong(battleId).array() +
            contract.payloadSuffix
    }

    fun parseWithdrawReceipt(
        payload: ByteArray,
        expectedBattleId: Long,
        contract: MineWithdrawBehaviorContract = MineWithdrawBehaviorContract.defaults()
    ): MineWithdrawReceipt {
        if (payload.size < 8) {
            return MineWithdrawReceipt(false, 0L, "撤防回执长度不足：${payload.size}/8")
        }
        val prefixId = ByteBuffer.wrap(payload, 0, 8).long
        if (prefixId > 0L &&
            (!contract.requireExactBattleIdMatch || prefixId == expectedBattleId)
        ) {
            return MineWithdrawReceipt(true, prefixId, "撤防请求已受理")
        }
        var offset = 0
        while (offset + 2 <= payload.size) {
            val length = ((payload[offset].toInt() and 0xff) shl 8) or
                (payload[offset + 1].toInt() and 0xff)
            val end = offset + 2 + length
            if (length in 1..600 && end <= payload.size) {
                val text = runCatching {
                    payload.copyOfRange(offset + 2, end).toString(Charsets.UTF_8)
                }.getOrDefault("")
                if (text.contains("【返回】") && end + 14 <= payload.size) {
                    val eventId = ByteBuffer.wrap(payload, end + 6, 8).long
                    if (eventId > 0L &&
                        (!contract.requireExactBattleIdMatch || eventId == expectedBattleId)
                    ) {
                        return MineWithdrawReceipt(true, eventId, "撤防请求已受理")
                    }
                }
                offset = end
            } else {
                offset += 1
            }
        }
        return MineWithdrawReceipt(
            false,
            prefixId,
            "撤防回执 battleId 不匹配：收到=$prefixId，期待=$expectedBattleId"
        )
    }

    private fun dispatchPrefix(
        generalIds: List<Long>,
        targetId: Long,
        contract: MineBehaviorContract
    ): ByteArray {
        val ids = generalIds.distinct()
        require(ids.isNotEmpty()) { "打矿至少需要一个将领" }
        require(ids.size <= contract.maximumGeneralsPerFormation) {
            "打矿一次最多选择${contract.maximumGeneralsPerFormation}名将领"
        }
        require(ids.all { it > 0L } && targetId > 0L) { "打矿将领或目标 ID 无效" }
        return ByteBuffer.allocate(2 + ids.size * 8 + 8)
            .put(contract.actionType.toByte())
            .put(ids.size.toByte())
            .also { buffer -> ids.forEach(buffer::putLong) }
            .putLong(targetId)
            .array()
    }

    private fun preferred(candidate: List<Int>, current: List<Int>): Boolean {
        val candidateKey = listOf(candidate.sum()) + candidate.asReversed().map { -it }
        val currentKey = listOf(current.sum()) + current.asReversed().map { -it }
        return candidateKey.indices.firstNotNullOfOrNull { index ->
            when {
                candidateKey[index] < currentKey[index] -> true
                candidateKey[index] > currentKey[index] -> false
                else -> null
            }
        } ?: false
    }

    private tailrec fun gcd(a: Int, b: Int): Int =
        if (b == 0) kotlin.math.abs(a) else gcd(b, a % b)
}
