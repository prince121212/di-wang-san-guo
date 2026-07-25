package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.MinistryProtocolCrop
import java.nio.ByteBuffer

data class MinistryGardenStatus(
    val plotCount: Int,
    val occupiedCount: Int,
    val emptyCount: Int
)

data class MinistryPlantResponse(
    val success: Boolean,
    val status: Int,
    val message: String
)

data class MinistryStealTarget(
    val roleId: Long,
    val name: String,
    val marker: Int
)

/**
 * Shapes proven by the 2026-07-11 passive capture:
 * 0x6320 -> 0xe320 garden state and 0x6328 -> 0xe328 planting.
 *
 * Only crop id 1 (the captured/default 金银花 path) is exposed. Other crops,
 * harvesting, stealing and courtesy tasks remain closed until separately captured.
 */
object MinistryProtocolShapes {
    private const val VERIFIED_EMPTY_STATE_SIZE = 158
    private const val VERIFIED_PLOT_COUNT = 10
    private const val OCCUPIED_RECORD_EXTRA_BYTES = 25

    fun buildStatusQueryPayload(): ByteArray = ByteArray(0)

    fun buildStealTargetListPayload(): ByteArray = byteArrayOf(0)

    fun buildTargetGardenPayload(roleId: Long): ByteArray {
        require(roleId > 0L) { "target role id must be positive" }
        return ByteBuffer.allocate(8).putLong(roleId).array()
    }

    fun buildPlantPayload(cropName: String): ByteArray {
        require(cropName == MinistryProtocolCrop.VERIFIED_NAME) {
            "crop protocol not verified: $cropName"
        }
        return ByteBuffer.allocate(5)
            .put(1)
            .putInt(MinistryProtocolCrop.VERIFIED_ID)
            .array()
    }

    fun parseGardenStatus(payload: ByteArray): MinistryGardenStatus {
        require(payload.size >= VERIFIED_EMPTY_STATE_SIZE) { "0xe320 response too short" }
        val plotCount = payload[25].toInt() and 0xff
        require(plotCount == VERIFIED_PLOT_COUNT) {
            "0xe320 plot count changed: $plotCount"
        }
        val extra = payload.size - VERIFIED_EMPTY_STATE_SIZE
        require(extra >= 0 && extra % OCCUPIED_RECORD_EXTRA_BYTES == 0) {
            "0xe320 unsupported record shape: size=${payload.size}"
        }
        val occupied = extra / OCCUPIED_RECORD_EXTRA_BYTES
        require(occupied in 0..plotCount) {
            "0xe320 occupied count invalid: $occupied/$plotCount"
        }
        return MinistryGardenStatus(
            plotCount = plotCount,
            occupiedCount = occupied,
            emptyCount = plotCount - occupied
        )
    }

    fun parsePlantResponse(payload: ByteArray): MinistryPlantResponse {
        require(payload.size >= 3) { "0xe328 response too short" }
        val status = payload[0].toInt() and 0xff
        val messageLength = ByteBuffer.wrap(payload, 1, 2).short.toInt() and 0xffff
        require(messageLength <= payload.size - 3) { "0xe328 message length invalid" }
        val message = payload.copyOfRange(3, 3 + messageLength).toString(Charsets.UTF_8)
        return MinistryPlantResponse(
            success = status == 0 && message.contains("成功"),
            status = status,
            message = message.ifBlank { "六部种菜响应状态=$status" }
        )
    }

    fun parseStealTargets(payload: ByteArray): List<MinistryStealTarget> {
        var p = 0
        fun u8(): Int = payload[p++].toInt() and 0xff
        fun u16(): Int = ByteBuffer.wrap(payload, p, 2).short.toInt().and(0xffff).also { p += 2 }
        fun i64(): Long = ByteBuffer.wrap(payload, p, 8).long.also { p += 8 }
        fun utf(): String {
            val size = u16()
            require(size <= payload.size - p) { "0xe322 UTF length invalid" }
            return payload.copyOfRange(p, p + size).toString(Charsets.UTF_8).also { p += size }
        }
        require(payload.size >= 20) { "0xe322 response too short" }
        require(u8() == 0) { "0xe322 status is not success" }
        require(utf().contains("成功")) { "0xe322 success message missing" }
        u8() // captured page/mode = 0
        val count = u8()
        require(count in 0..20) { "0xe322 target count invalid: $count" }
        val targets = buildList {
            repeat(count) {
                val roleId = i64()
                val name = utf()
                val marker = u16()
                require(roleId > 0L && name.isNotBlank()) { "0xe322 target record invalid" }
                add(MinistryStealTarget(roleId, name, marker))
            }
        }
        // Captured response has one final list-state byte.
        require(p == payload.size - 1) { "0xe322 trailing shape changed: ${payload.size - p}" }
        u8()
        return targets
    }

    fun parseTargetGardenHeader(payload: ByteArray, expectedRoleId: Long) {
        require(payload.size >= 18) { "0xe323 response too short" }
        val status = payload[0].toInt() and 0xff
        val messageLength = ByteBuffer.wrap(payload, 1, 2).short.toInt() and 0xffff
        require(messageLength <= payload.size - 11) { "0xe323 message length invalid" }
        val messageEnd = 3 + messageLength
        val message = payload.copyOfRange(3, messageEnd).toString(Charsets.UTF_8)
        require(status == 0 && message == "success") { "0xe323 status/message invalid" }
        val roleId = ByteBuffer.wrap(payload, messageEnd, 8).long
        require(roleId == expectedRoleId) {
            "0xe323 target mismatch: $roleId != $expectedRoleId"
        }
    }
}
