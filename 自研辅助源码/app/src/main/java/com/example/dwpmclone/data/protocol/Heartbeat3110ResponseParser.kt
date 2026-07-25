package com.example.dwpmclone.data.protocol

import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

data class Heartbeat3110Snapshot(
    val copper: Long?,
    val food: Long?,
    val broadcasts: List<String>,
    val sessionInvalid: Boolean,
    val payloadHex: String
)

/**
 * Partial 0xa110 parser backed by live captures.
 *
 * Confirmed fields:
 * - payload[1..8]: current copper, big-endian uint64
 * - payload[9..16]: current food, big-endian uint64
 * - broadcasts: UTF-8 strings prefixed by an unsigned 16-bit byte length
 *
 * Unknown binary blocks remain untouched and are never guessed into UI fields.
 */
object Heartbeat3110ResponseParser {
    fun parse(payloadHex: String): Heartbeat3110Snapshot {
        val normalized = payloadHex.filterNot(Char::isWhitespace).lowercase()
        val bytes = normalized.hexToBytesOrEmpty()
        val sessionInvalid = normalized.endsWith("fffc0000") || normalized == "fffc0000"
        val copper = if (!sessionInvalid && bytes.size >= 17) bytes.unsignedLongAt(1) else null
        val food = if (!sessionInvalid && bytes.size >= 17) bytes.unsignedLongAt(9) else null
        return Heartbeat3110Snapshot(
            copper = copper,
            food = food,
            broadcasts = extractLengthPrefixedUtf8(bytes),
            sessionInvalid = sessionInvalid,
            payloadHex = normalized
        )
    }

    fun mergeMilitaryIntel(
        existingJson: String?,
        snapshot: Heartbeat3110Snapshot,
        updatedAtMillis: Long
    ): String {
        val existing = existingJson?.trim()
            ?.takeIf { it.startsWith("{") }
            ?.let { runCatching { JSONObject(it) }.getOrNull() }
            ?: JSONObject()
        val oldEvents = existing.optJSONArray("events") ?: JSONArray()
        val merged = mutableListOf<JSONObject>()
        for (index in 0 until oldEvents.length()) {
            oldEvents.optJSONObject(index)?.let { merged += JSONObject(it.toString()) }
        }
        val timeText = SimpleDateFormat("HH:mm:ss", Locale.CHINA).format(Date(updatedAtMillis))
        snapshot.broadcasts.forEach { text ->
            merged += JSONObject()
                .put("timeText", timeText)
                .put("text", text)
                .put("state", inferState(text))
                .put("national", isNational(text))
                .put("sourceOpcode", "0x3110/0xa110")
        }
        val deduplicated = linkedMapOf<String, JSONObject>()
        merged.forEach { event ->
            val key = listOf(
                event.optString("timeText"),
                event.optString("state"),
                event.optString("text")
            ).joinToString("|")
            deduplicated[key] = event
        }
        val retained = deduplicated.values.toList().takeLast(MAX_EVENTS)
        return JSONObject()
            .put("sourceOpcode", "0x3110/0xa110")
            .put("updatedAt", updatedAtMillis)
            .put("events", JSONArray().apply { retained.forEach { event -> put(event) } })
            .toString()
    }

    private fun extractLengthPrefixedUtf8(bytes: ByteArray): List<String> {
        val found = linkedSetOf<String>()
        for (offset in 0 until (bytes.size - 2).coerceAtLeast(0)) {
            val length = ((bytes[offset].toInt() and 0xff) shl 8) or
                (bytes[offset + 1].toInt() and 0xff)
            if (length !in MIN_TEXT_BYTES..MAX_TEXT_BYTES || offset + 2 + length > bytes.size) continue
            val text = runCatching {
                bytes.copyOfRange(offset + 2, offset + 2 + length).toString(Charsets.UTF_8)
            }.getOrNull()?.trim().orEmpty()
            if (text.isBlank() || text.toByteArray(Charsets.UTF_8).size != length) continue
            if (text.none { it.code > 127 } || text.any { it.isISOControl() }) continue
            found += text
        }
        return found.toList()
    }

    private fun inferState(text: String): String = when {
        text.contains("返回") -> "返回"
        text.contains("出征") || text.contains("行军") -> "征"
        else -> ""
    }

    private fun isNational(text: String): Boolean =
        listOf("国家", "国战", "国都", "县城", "守城", "国王").any(text::contains)

    private fun ByteArray.unsignedLongAt(offset: Int): Long? {
        if (offset < 0 || offset + 8 > size) return null
        var value = 0L
        repeat(8) { value = (value shl 8) or (this[offset + it].toLong() and 0xffL) }
        return value.takeIf { it >= 0L }
    }

    private fun String.hexToBytesOrEmpty(): ByteArray {
        if (length % 2 != 0 || any { it.digitToIntOrNull(16) == null }) return ByteArray(0)
        return ByteArray(length / 2) { index ->
            substring(index * 2, index * 2 + 2).toInt(16).toByte()
        }
    }

    private const val MIN_TEXT_BYTES = 6
    private const val MAX_TEXT_BYTES = 2_048
    private const val MAX_EVENTS = 100
}
