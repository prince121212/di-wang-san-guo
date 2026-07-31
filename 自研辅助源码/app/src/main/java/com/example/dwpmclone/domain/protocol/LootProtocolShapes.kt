package com.example.dwpmclone.domain.protocol

import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.nio.ByteBuffer

data class LootTargetFief(
    val index: Int,
    val targetId: Long,
    val name: String,
    val cityName: String,
    val serialByte: Int? = null,
    val mapFlag: Int? = null,
    val x: Int? = null,
    val y: Int? = null
)

data class RaidFiefList(
    val flag: Int,
    val playerName: String,
    val country: String,
    val fiefs: List<LootTargetFief>,
    val trailingBytes: Int
)

object LootProtocolShapes {
    fun buildFiefListPayload(playerName: String): ByteArray =
        buildRaidFiefListPayload(playerName)

    /** 0x1310 raid target query: the target selector is 0x0001 + UTF(playerName). */
    fun buildRaidFiefListPayload(
        playerName: String,
        contract: RaidBehaviorContract = RaidBehaviorContract.defaults()
    ): ByteArray {
        require(playerName.isNotBlank()) { "掠夺目标玩家名称不能为空" }
        return ByteArrayOutputStream().also { bytes ->
            DataOutputStream(bytes).use { out ->
                out.write(contract.targetPayloadPrefix)
                out.writeUTF(playerName.trim())
            }
        }.toByteArray()
    }

    fun parseFiefList(payload: ByteArray): List<LootTargetFief> =
        parseRaidFiefList(payload).fiefs

    fun parseRaidFiefList(payload: ByteArray): RaidFiefList {
        val buffer = ByteBuffer.wrap(payload)
        require(buffer.remaining() >= 2) { "0x8310响应过短" }
        val flag = buffer.short.toInt() and 0xffff
        val playerName = readUtf(buffer)
        val country = readUtf(buffer)
        require(buffer.hasRemaining()) { "0x8310缺少封地数量" }
        val count = buffer.get().toInt() and 0xff
        val fiefs = (1..count).map { index ->
            require(buffer.remaining() >= 8) { "第${index}条封地缺少targetId" }
            val targetId = buffer.long
            val name = readUtf(buffer)
            require(buffer.hasRemaining()) { "第${index}条封地缺少序号" }
            val serialByte = buffer.get().toInt() and 0xff
            val cityName = readUtf(buffer)
            require(buffer.remaining() >= 5) { "第${index}条封地尾部不完整" }
            val mapFlag = buffer.get().toInt() and 0xff
            val x = buffer.short.toInt() and 0xffff
            val y = buffer.short.toInt() and 0xffff
            LootTargetFief(index, targetId, name, cityName, serialByte, mapFlag, x, y)
        }
        return RaidFiefList(flag, playerName, country, fiefs, buffer.remaining())
    }

    fun buildPreparePayload(
        generalIds: List<Long>,
        targetId: Long,
        contract: RaidBehaviorContract = RaidBehaviorContract.defaults()
    ): ByteArray = dispatchPrefix(generalIds, targetId, contract)

    fun buildExpeditionPayload(
        generalIds: List<Long>,
        targetId: Long,
        contract: RaidBehaviorContract = RaidBehaviorContract.defaults()
    ): ByteArray = dispatchPrefix(generalIds, targetId, contract) + ByteBuffer.allocate(11)
            .putLong(contract.immediateRelatedLong)
            .put(contract.immediateFlags)
            .array()

    private fun dispatchPrefix(
        generalIds: List<Long>,
        targetId: Long,
        contract: RaidBehaviorContract
    ): ByteArray {
        val ids = generalIds.distinct()
        require(ids.isNotEmpty()) { "掠夺至少需要一个将领" }
        require(ids.size <= contract.maximumGeneralsPerFormation) {
            "掠夺一次最多选择${contract.maximumGeneralsPerFormation}名将领"
        }
        require(ids.all { it > 0L } && targetId > 0L) { "掠夺将领或目标 ID 无效" }
        return ByteBuffer.allocate(2 + ids.size * 8 + 8)
            .put(contract.actionType.toByte())
            .put(ids.size.toByte())
            .also { buffer -> ids.forEach(buffer::putLong) }
            .putLong(targetId)
            .array()
    }

    private fun readUtf(buffer: ByteBuffer): String {
        require(buffer.remaining() >= 2) { "UTF字段缺少长度" }
        val length = buffer.short.toInt() and 0xffff
        require(buffer.remaining() >= length) { "UTF字段长度越界" }
        return ByteArray(length).also(buffer::get).toString(Charsets.UTF_8)
    }
}
