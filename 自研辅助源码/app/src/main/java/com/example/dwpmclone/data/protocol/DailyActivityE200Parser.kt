package com.example.dwpmclone.data.protocol

import org.json.JSONArray
import org.json.JSONObject

data class DailyActivityTask(
    val text: String,
    val progress: String?,
    val current: Int?,
    val target: Int?,
    val reward: String?,
    val offset: Int
)

data class DailyActivityState(
    val tasks: List<DailyActivityTask>,
    val treasureOccupied: DailyActivityTask?,
    val sourceOpcode: String,
    val payloadByteCount: Int
) {
    fun toJson(): String = JSONObject()
        .put("sourceOpcode", sourceOpcode)
        .put("payloadByteCount", payloadByteCount)
        .put("tasks", JSONArray().apply {
            tasks.forEach { task ->
                put(JSONObject()
                    .put("text", task.text)
                    .put("offset", task.offset)
                    .apply {
                        task.progress?.let { put("progress", it) }
                        task.current?.let { put("current", it) }
                        task.target?.let { put("target", it) }
                        task.reward?.let { put("reward", it) }
                    }
                )
            }
        })
        .apply {
            treasureOccupied?.let { task ->
                put("treasureOccupied", JSONObject()
                    .put("text", task.text)
                    .put("progress", task.progress)
                    .put("current", task.current)
                    .put("target", task.target)
                )
            }
        }
        .toString()
}

/**
 * Parser ported from the current computer server's parse_e200_daily_activity().
 *
 * A task record normally exposes a Chinese task label followed by an n/m progress UTF
 * field and an optional signed reward UTF field. Unknown binary fields are ignored.
 */
object DailyActivityE200Parser {
    fun parse(
        payload: ByteArray,
        sourceOpcode: String = "0x6200/0xe200"
    ): DailyActivityState {
        val fields = extractUsefulUtfFields(payload)
        val tasks = fields.mapIndexedNotNull { index, field ->
            if (!field.text.hasChinese()) return@mapIndexedNotNull null
            val following = fields.drop(index + 1)
            val progressField = following.take(5).firstOrNull { PROGRESS.matches(it.text.trim()) }
            val rewardField = following.take(7).firstOrNull { REWARD.matches(it.text.trim()) }
            val match = progressField?.text?.trim()?.let(PROGRESS::matchEntire)
            DailyActivityTask(
                text = field.text,
                progress = progressField?.text?.trim(),
                current = match?.groupValues?.getOrNull(1)?.toIntOrNull(),
                target = match?.groupValues?.getOrNull(2)?.toIntOrNull(),
                reward = rewardField?.text?.trim(),
                offset = field.offset
            )
        }
        return DailyActivityState(
            tasks = tasks,
            treasureOccupied = tasks.firstOrNull {
                it.text.contains("宝藏") &&
                    (it.text.contains("占领") || it.text.contains("佔領"))
            },
            sourceOpcode = sourceOpcode,
            payloadByteCount = payload.size
        )
    }

    private fun extractUsefulUtfFields(payload: ByteArray): List<UtfField> {
        val found = mutableListOf<UtfField>()
        for (offset in 0 until (payload.size - 2).coerceAtLeast(0)) {
            val length = ((payload[offset].toInt() and 0xff) shl 8) or
                (payload[offset + 1].toInt() and 0xff)
            if (length !in 1..220 || offset + 2 + length > payload.size) continue
            val text = runCatching {
                payload.copyOfRange(offset + 2, offset + 2 + length).toString(Charsets.UTF_8)
            }.getOrNull().orEmpty()
            if (text.isBlank() || text.toByteArray(Charsets.UTF_8).size != length) continue
            if (text.any { it.isISOControl() && it !in listOf('\r', '\n', '\t') }) continue
            val trimmed = text.trim()
            val useful = text.hasChinese() ||
                PROGRESS.matches(trimmed) ||
                REWARD.matches(trimmed) ||
                (text.any(Char::isDigit) && text.length <= 80)
            if (useful) found += UtfField(offset, length, text)
        }
        val deduplicated = mutableListOf<UtfField>()
        var lastEnd = -1
        found.sortedBy(UtfField::offset).forEach { field ->
            if (field.offset < lastEnd && deduplicated.lastOrNull()?.text == field.text) {
                return@forEach
            }
            deduplicated += field
            lastEnd = maxOf(lastEnd, field.offset + 2 + field.length)
        }
        return deduplicated
    }

    private fun String.hasChinese(): Boolean = any { it in '\u4e00'..'\u9fff' }

    private data class UtfField(val offset: Int, val length: Int, val text: String)

    private val PROGRESS = Regex("""^\s*(\d+)\s*/\s*(\d+)\s*$""")
    private val REWARD = Regex("""^\s*[+-]\d+\s*$""")
}
