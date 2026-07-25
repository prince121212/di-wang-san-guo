package com.example.dwpmclone.domain.protocol

import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.nio.ByteBuffer

data class LootTargetFief(
    val index: Int,
    val targetId: Long,
    val name: String,
    val cityName: String
)

object LootProtocolShapes {
    fun buildFiefListPayload(playerName: String): ByteArray {
        require(playerName.isNotBlank()) { "玩家名称不能为空" }
        return ByteArrayOutputStream().also { bytes ->
            DataOutputStream(bytes).use { out ->
                out.writeShort(1)
                out.writeUTF(playerName.trim())
            }
        }.toByteArray()
    }

    fun parseFiefList(payload: ByteArray): List<LootTargetFief> {
        val buffer = ByteBuffer.wrap(payload)
        require(buffer.remaining() >= 2) { "0x8310响应过短" }
        buffer.short
        readUtf(buffer)
        readUtf(buffer)
        require(buffer.hasRemaining()) { "0x8310缺少封地数量" }
        val count = buffer.get().toInt() and 0xff
        return (1..count).map { index ->
            require(buffer.remaining() >= 8) { "第${index}条封地缺少targetId" }
            val targetId = buffer.long
            val name = readUtf(buffer)
            require(buffer.hasRemaining()) { "第${index}条封地缺少序号" }
            buffer.get()
            val cityName = readUtf(buffer)
            require(buffer.remaining() >= 5) { "第${index}条封地尾部不完整" }
            buffer.position(buffer.position() + 5)
            LootTargetFief(index, targetId, name, cityName)
        }
    }

    fun buildPreparePayload(generalIds: List<Long>, targetId: Long): ByteArray =
        dispatchPrefix(generalIds, targetId)

    fun buildExpeditionPayload(generalIds: List<Long>, targetId: Long): ByteArray =
        dispatchPrefix(generalIds, targetId) + ByteBuffer.allocate(11)
            .putLong(-1L)
            .put(byteArrayOf(0, 0, 0))
            .array()

    private fun dispatchPrefix(generalIds: List<Long>, targetId: Long): ByteArray {
        require(generalIds.isNotEmpty()) { "掠夺至少需要一个将领" }
        require(generalIds.size <= 255) { "掠夺将领数量超过255" }
        return ByteBuffer.allocate(2 + generalIds.size * 8 + 8)
            .put(1)
            .put(generalIds.size.toByte())
            .also { buffer -> generalIds.forEach(buffer::putLong) }
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
