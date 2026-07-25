package com.example.dwpmclone.data.protocol

data class FormationAssign8226Result(
    val success: Boolean,
    val status: Int?,
    val generalId: Long?,
    val previousType: Int?,
    val previousCount: Int?,
    val assignedType: Int?,
    val assignedCount: Int?,
    val message: String
)

data class FormationRefillEntry(
    val generalId: Long,
    val soldierType: Int,
    val soldierCount: Int
)

data class FormationRefill8229Result(
    val success: Boolean,
    val status: Int?,
    val message: String,
    val entries: List<FormationRefillEntry>
)

/** Parsers for the captured 0x8226 assignment and 0x8229 batch-refill responses. */
object Formation122xResponseParser {
    fun parse8226(payloadHex: String): FormationAssign8226Result {
        val bytes = payloadHex.hexBytesOrNull()
            ?: return FormationAssign8226Result(false, null, null, null, null, null, null, "0x8226 响应 hex 无效")
        if (bytes.size < 17) {
            return FormationAssign8226Result(false, null, null, null, null, null, null, "0x8226 响应过短")
        }
        val status = bytes.u8(0)
        val generalId = bytes.i64(1)
        val previousType = bytes.u16(9)
        val previousCount = bytes.u16(11)
        val assignedType = bytes.u16(13)
        val assignedCount = bytes.u16(15)
        return FormationAssign8226Result(
            success = status == 1,
            status = status,
            generalId = generalId,
            previousType = previousType,
            previousCount = previousCount,
            assignedType = assignedType,
            assignedCount = assignedCount,
            message = if (status == 1) {
                "配兵成功：$previousCount→$assignedCount"
            } else {
                "配兵失败，状态=$status"
            }
        )
    }

    fun parse8229(payloadHex: String): FormationRefill8229Result {
        val bytes = payloadHex.hexBytesOrNull()
            ?: return FormationRefill8229Result(false, null, "0x8229 响应 hex 无效", emptyList())
        if (bytes.size < 4) {
            return FormationRefill8229Result(false, null, "0x8229 响应过短", emptyList())
        }
        val status = bytes.u8(0)
        val textLength = bytes.u16(1)
        if (textLength <= 0 || 3 + textLength >= bytes.size) {
            return FormationRefill8229Result(false, status, "0x8229 缺少确认文本", emptyList())
        }
        val message = runCatching {
            bytes.copyOfRange(3, 3 + textLength).toString(Charsets.UTF_8)
        }.getOrDefault("")
        var offset = 3 + textLength
        val count = bytes.u8(offset++)
        val entries = mutableListOf<FormationRefillEntry>()
        repeat(count) {
            if (offset + 13 > bytes.size) {
                return FormationRefill8229Result(false, status, "0x8229 编队结果数量不完整", entries)
            }
            entries += FormationRefillEntry(
                generalId = bytes.i64(offset),
                soldierType = bytes.u8(offset + 8),
                soldierCount = bytes.i32(offset + 9)
            )
            offset += 13
        }
        val success = status == 0 && message.contains("补满成功")
        return FormationRefill8229Result(
            success = success,
            status = status,
            message = message.ifBlank { "0x8229 未返回确认文本" },
            entries = entries
        )
    }

    private fun String.hexBytesOrNull(): ByteArray? {
        val normalized = filterNot(Char::isWhitespace)
        if (normalized.length % 2 != 0 || normalized.any { it.digitToIntOrNull(16) == null }) return null
        return ByteArray(normalized.length / 2) {
            normalized.substring(it * 2, it * 2 + 2).toInt(16).toByte()
        }
    }

    private fun ByteArray.u8(offset: Int): Int = this[offset].toInt() and 0xff

    private fun ByteArray.u16(offset: Int): Int =
        (u8(offset) shl 8) or u8(offset + 1)

    private fun ByteArray.i32(offset: Int): Int =
        (u8(offset) shl 24) or (u8(offset + 1) shl 16) or
            (u8(offset + 2) shl 8) or u8(offset + 3)

    private fun ByteArray.i64(offset: Int): Long {
        var value = 0L
        repeat(8) { value = (value shl 8) or u8(offset + it).toLong() }
        return value
    }
}
