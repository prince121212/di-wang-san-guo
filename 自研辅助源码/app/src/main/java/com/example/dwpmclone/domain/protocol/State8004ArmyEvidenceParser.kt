package com.example.dwpmclone.domain.protocol

import org.json.JSONArray
import org.json.JSONObject

data class State8004ArmyRow(
    val soldierTypeCode: Int,
    val soldierType: String,
    val idleCount: Int,
    val woundedCount: Int,
    val fiefName: String,
    val offset: Int
)

/**
 * Port of the current computer server's parse_idle_army_from_8004().
 *
 * Confirmed compact block:
 * 0x1d, idleTypeCount, repeated(byte type, int count),
 * woundedTypeCount, repeated(byte type, int count).
 */
object State8004ArmyEvidenceParser {
    fun recover(payloadHex: String): List<State8004ArmyRow> {
        val bytes = payloadHex.hexToBytesOrNull() ?: return emptyList()
        val candidates = mutableListOf<Candidate>()
        for (marker in 0 until (bytes.size - 3).coerceAtLeast(0)) {
            if ((bytes[marker].toInt() and 0xff) != 0x1d) continue
            var position = marker + 1
            val idleTypeCount = bytes.u8(position++)
            if (idleTypeCount !in 0..16) continue
            val idleRows = mutableListOf<Pair<Int, Int>>()
            var valid = true
            repeat(idleTypeCount) {
                if (position + 5 > bytes.size) {
                    valid = false
                    return@repeat
                }
                val type = bytes.u8(position)
                val count = bytes.signedInt(position + 1)
                position += 5
                if (type !in SOLDIER_NAMES || count !in 0..MAX_COUNT) {
                    valid = false
                } else {
                    idleRows += type to count
                }
            }
            if (!valid || position >= bytes.size) continue
            val woundedTypeCount = bytes.u8(position++)
            if (woundedTypeCount !in 0..16) continue
            val woundedRows = mutableListOf<Pair<Int, Int>>()
            repeat(woundedTypeCount) {
                if (position + 5 > bytes.size) {
                    valid = false
                    return@repeat
                }
                val type = bytes.u8(position)
                val count = bytes.signedInt(position + 1)
                position += 5
                if (type !in SOLDIER_NAMES || count !in 0..MAX_COUNT) {
                    valid = false
                } else {
                    woundedRows += type to count
                }
            }
            if (!valid || (idleRows + woundedRows).none { it.second > 0 }) continue
            val fiefName = previousFiefName(bytes, marker) ?: continue
            val order = linkedSetOf<Int>()
            idleRows.forEach { order += it.first }
            woundedRows.forEach { order += it.first }
            val rows = order.map { type ->
                State8004ArmyRow(
                    soldierTypeCode = type,
                    soldierType = SOLDIER_NAMES.getValue(type),
                    idleCount = idleRows.filter { it.first == type }.sumOf { it.second },
                    woundedCount = woundedRows.filter { it.first == type }.sumOf { it.second },
                    fiefName = fiefName,
                    offset = marker
                )
            }
            candidates += Candidate(marker, rows)
        }
        val merged = linkedMapOf<Pair<String, Int>, State8004ArmyRow>()
        candidates.sortedBy(Candidate::marker).flatMap(Candidate::rows).forEach { row ->
            val key = row.fiefName to row.soldierTypeCode
            val previous = merged[key]
            merged[key] = if (previous == null) row else previous.copy(
                idleCount = previous.idleCount + row.idleCount,
                woundedCount = previous.woundedCount + row.woundedCount
            )
        }
        return merged.values.toList()
    }

    fun toJson(rows: List<State8004ArmyRow>): String = JSONArray().apply {
        rows.forEach { row ->
            put(JSONObject()
                .put("soldierTypeCode", row.soldierTypeCode)
                .put("soldierType", row.soldierType)
                .put("idleCount", row.idleCount)
                .put("count", row.idleCount)
                .put("amount", row.idleCount)
                .put("woundedCount", row.woundedCount)
                .put("hurtSoldierCount", row.woundedCount)
                .put("fiefName", row.fiefName)
                .put("offset", row.offset)
                .put("source", "state8004-compact-army")
            )
        }
    }.toString()

    private fun previousFiefName(bytes: ByteArray, marker: Int): String? {
        val start = (marker - 700).coerceAtLeast(0)
        val region = bytes.copyOfRange(start, marker)
        val found = mutableListOf<String>()
        for (offset in 0 until (region.size - 2).coerceAtLeast(0)) {
            val length = (region.u8(offset) shl 8) or region.u8(offset + 1)
            if (length !in 2..40 || offset + 2 + length > region.size) continue
            val text = runCatching {
                region.copyOfRange(offset + 2, offset + 2 + length).toString(Charsets.UTF_8)
            }.getOrNull().orEmpty()
            if (text.toByteArray(Charsets.UTF_8).size != length) continue
            if (text.any { it.isISOControl() }) continue
            if (FIEF_MARKERS.any(text::contains)) found += text
        }
        return found.lastOrNull()
    }

    private fun String.hexToBytesOrNull(): ByteArray? {
        val clean = trim().removePrefix("0x").removePrefix("0X")
        if (clean.length < 8 || clean.length % 2 != 0 || clean.any { it.digitToIntOrNull(16) == null }) {
            return null
        }
        return ByteArray(clean.length / 2) { index ->
            clean.substring(index * 2, index * 2 + 2).toInt(16).toByte()
        }
    }

    private fun ByteArray.u8(offset: Int): Int = this[offset].toInt() and 0xff

    private fun ByteArray.signedInt(offset: Int): Int =
        (u8(offset) shl 24) or
            (u8(offset + 1) shl 16) or
            (u8(offset + 2) shl 8) or
            u8(offset + 3)

    private data class Candidate(val marker: Int, val rows: List<State8004ArmyRow>)

    private const val MAX_COUNT = 500_000
    private val FIEF_MARKERS = listOf("基地", "封地", "城", "县", "郡")
    private val SOLDIER_NAMES = mapOf(
        0 to "民兵", 1 to "弩兵", 2 to "弓兵", 3 to "轻骑兵",
        4 to "弩车", 5 to "冲城车", 6 to "轻步兵", 7 to "近卫兵",
        8 to "重步兵", 9 to "弩骑兵", 10 to "重骑兵", 11 to "铁骑兵",
        12 to "投石车", 13 to "重弩车", 14 to "强弩兵", 15 to "骁骑兵"
    )
}
