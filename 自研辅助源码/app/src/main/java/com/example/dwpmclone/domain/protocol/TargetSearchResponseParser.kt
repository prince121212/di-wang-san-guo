package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.MapCoordinate

/**
 * Conservative parser for recovered 041540 target-search responses.
 *
 * Evidence:
 * - Landroid/o/ۦۤ۠;->ۦۖ۫(String,ZZZ)[Landroid/o/ۦۤ۠;
 * - id = record[0:12]
 * - kind is decoded from hex text markers such as 山贼/黄巾/渠帅/主将
 * - kv/kw are parsed from 4-hex-char coordinate fields adjacent to the kind marker
 *
 * This parser is intentionally tolerant because live response captures are still missing.
 * It is used as a response-shape bridge, not as proof that true network execution is done.
 */
object TargetSearchResponseParser {
    private val KIND_MARKERS = linkedMapOf(
        "E5B1B1E8B38A" to "山贼", // 山賊
        "E5B1B1E8B4BC" to "山贼",
        "E9BB83E5B7BE" to "黄巾", // 黃巾
        "E9BB84E5B7BE" to "黄巾",
        "E6B8A0E5B885" to "渠帅",
        "E6B8A0E5B8A5" to "渠帅", // 渠帥
        "E4B8BBE5B086" to "主将",
        "E4B8BBE5B087" to "主将", // 主將
        "E4B8BBE5B885" to "主帅",
        "E4B8BBE5B8A5" to "主帅" // 主帥
    )

    fun parse(responseHex: String): List<MapTarget> {
        val structured = parseStructured8540Targets(responseHex)
        if (structured.isNotEmpty()) return structured
        return parsePoints(responseHex).map { point ->
            MapTarget(
                id = point.id,
                coordinate = point.coordinate,
                type = point.kind,
                raw = mapOf(
                    "idHex" to point.idHex,
                    "kind" to point.kind,
                    "kindHex" to point.kindHex,
                    "rank" to point.rank.toString(),
                    "kv" to point.coordinate.x.toString(),
                    "kw" to point.coordinate.y.toString(),
                    "kz" to point.kz.toString(),
                    "source" to "041540-response-parser",
                    "rawRecord" to point.rawRecord
                )
            )
        }
    }

    private fun parseStructured8540Targets(responseHex: String): List<MapTarget> {
        val candidates = responseHex
            .replace("\\|", "|")
            .split('|', '\n', '\r', '\t', ' ')
            .map { it.filterHexUppercase() }
            .filter { it.length >= 20 && it.length % 2 == 0 }
        return candidates
            .flatMap { parseStructured8540Candidate(it) }
            .distinctBy { Triple(it.id, it.type, it.coordinate) }
    }

    private fun parseStructured8540Candidate(hex: String): List<MapTarget> {
        val payload = hex.hexToBytesOrNull() ?: return emptyList()
        if (payload.size < 5) return emptyList()
        return runCatching {
            val mapWidth = payload.u16(0)
            val mapHeight = payload.u16(2)
            val count = payload.u8(4).coerceIn(0, 80)
            var p = 5
            val targets = mutableListOf<MapTarget>()
            repeat(count) {
                if (p + 10 > payload.size) return@repeat
                val recordStart = p
                val id = payload.u64(p)
                p += 8
                if (id <= 0L) return@repeat
                val nameResult = payload.readUtfAt(p) ?: return@repeat
                val name = nameResult.first
                p = nameResult.second
                if (p + 7 > payload.size) return@repeat
                val metaA = payload.u8(p)
                val metaB = payload.u8(p + 1)
                val levelByte = payload.u8(p + 2)
                p += 3
                val metaD = payload.u16(p)
                p += 2
                val metaE = payload.u16(p)
                p += 2
                val resourceResult = payload.readUtfAt(p) ?: return@repeat
                val resource = resourceResult.first
                p = resourceResult.second
                if (p + 8 > payload.size) return@repeat
                val x = payload.i32(p)
                p += 4
                val y = payload.i32(p)
                p += 4

                val nextPos = payload.nextStructuredRecordOffset(p) ?: payload.size
                val tailHex = payload.copyOfRange(p, nextPos.coerceIn(p, payload.size)).toHexUpper().take(120)
                p = nextPos

                val level = Regex("""(\d+)级""").find(name)?.groupValues?.getOrNull(1)?.toIntOrNull()
                    ?: levelByte.takeIf { it in 1..99 }
                    ?: defaultRankForKind(name.normalizedKind()) ?: 0
                val kind = name.normalizedKind()
                val composition = inferCompositionFromLevel(level)
                val rawRecord = payload.copyOfRange(recordStart, (recordStart + 8 + 2 + name.toByteArray(Charsets.UTF_8).size).coerceAtMost(payload.size))
                    .toHexUpper()
                targets += MapTarget(
                    id = id,
                    coordinate = MapCoordinate(x, y),
                    type = kind,
                    raw = mapOf(
                        "idHex" to id.toString(16).padStart(12, '0'),
                        "targetIdHex" to id.toString(16).padStart(16, '0'),
                        "kind" to kind,
                        "name" to name,
                        "rank" to level.toString(),
                        "level" to level.toString(),
                        "kv" to x.toString(),
                        "kw" to y.toString(),
                        "x" to x.toString(),
                        "y" to y.toString(),
                        "resource" to resource,
                        "rawRecord" to rawRecord,
                        "mapWidth" to mapWidth.toString(),
                        "mapHeight" to mapHeight.toString(),
                        "metaA" to metaA.toString(),
                        "metaB" to metaB.toString(),
                        "levelByte" to levelByte.toString(),
                        "metaD" to metaD.toString(),
                        "metaE" to metaE.toString(),
                        "tailHex" to tailHex,
                        "foot" to composition[0].toString(),
                        "bow" to composition[1].toString(),
                        "cavalry" to composition[2].toString(),
                        "chariot" to composition[3].toString(),
                        "compositionCode" to composition.joinToString(""),
                        "compositionSource" to "level-template",
                        "source" to "8540-structured"
                    )
                )
            }
            targets
        }.getOrDefault(emptyList())
    }

    internal fun parsePoints(responseHex: String): List<TargetSearchPoint> {
        val candidates = responseHex
            .replace("\\|", "|")
            .split('|', '\n', '\r', '\t', ' ')
            .map { it.filterHexUppercase() }
            .filter { it.length >= 20 }

        val normalized = responseHex.filterHexUppercase()
        return (candidates.mapNotNull { parseRecord(it) } + scanConcatenatedRecords(normalized))
            .distinctBy { Triple(it.id, it.kind, it.coordinate) }
    }

    private fun scanConcatenatedRecords(normalized: String): List<TargetSearchPoint> {
        if (normalized.length < 20) return emptyList()
        val out = mutableListOf<TargetSearchPoint>()
        for ((markerHex, _) in KIND_MARKERS) {
            var searchFrom = 0
            while (true) {
                val markerStart = normalized.indexOf(markerHex, startIndex = searchFrom)
                if (markerStart < 0) break
                for (prefixLength in listOf(26, 24, 22, 20, 18)) {
                    val start = markerStart - prefixLength
                    if (start < 0) continue
                    val end = markerStart + markerHex.length
                    val candidate = normalized.substring(start, end)
                    val parsed = parseRecord(candidate)
                    if (parsed != null && parsed.id > 0L && parsed.coordinate.x in 0..9999 && parsed.coordinate.y in 0..9999) {
                        out += parsed
                        break
                    }
                }
                searchFrom = markerStart + markerHex.length
            }
        }
        return out
    }

    private fun parseRecord(record: String): TargetSearchPoint? {
        val markerWithStart = KIND_MARKERS.entries
            .mapNotNull { entry ->
                val index = record.indexOf(entry.key)
                if (index >= 0) entry to index else null
            }
            .minByOrNull { it.second } ?: return null
        val marker = markerWithStart.first
        val markerStart = markerWithStart.second
        if (markerStart < 8 || record.length < 12) return null

        val idHex = record.take(12)
        val id = idHex.parseUnsignedHexLong() ?: return null
        val parsedRank = parseRank(record)
        val rank = fixedRankForKind(marker.value) ?: parsedRank.takeIf { it > 0 } ?: defaultRankForKind(marker.value) ?: 0
        val coordinate = parseCoordinate(record, markerStart)
        val kz = record.sliceOrNull(14, 18)?.toIntOrNull(16) ?: 0
        return TargetSearchPoint(
            idHex = idHex,
            id = id,
            kind = marker.value,
            kindHex = marker.key,
            rank = rank,
            coordinate = coordinate,
            kz = rank + kz,
            rawRecord = record
        )
    }

    private fun parseCoordinate(record: String, markerStart: Int): MapCoordinate {
        val ranges = listOf(
            markerStart - 8 to markerStart - 4,
            markerStart - 4 to markerStart,
            18 to 22,
            22 to 26,
            12 to 16,
            16 to 20
        )
        val pairs = ranges.chunked(2)
        for (pair in pairs) {
            if (pair.size != 2) continue
            val x = record.sliceOrNull(pair[0].first, pair[0].second)?.toIntOrNull(16)
            val y = record.sliceOrNull(pair[1].first, pair[1].second)?.toIntOrNull(16)
            if (x != null && y != null && x in 0..9999 && y in 0..9999) {
                return MapCoordinate(x, y)
            }
        }
        return MapCoordinate(0, 0)
    }

    private fun parseRank(record: String): Int {
        record.sliceOrNull(12, 14)?.toIntOrNull(16)?.takeIf { it in 1..99 }?.let { return it }
        record.sliceOrNull(12, 16)?.hexToText()?.toIntOrNull()?.takeIf { it in 1..99 }?.let { return it }
        return 0
    }

    private fun fixedRankForKind(kind: String): Int? = when (kind) {
        "渠帅" -> 11
        "主将" -> 12
        "主帅" -> 13
        else -> null
    }

    private fun defaultRankForKind(kind: String): Int? = when (kind) {
        // The game UI presents generic "山贼" entries as 1级山贼 in the brush-yellow
        // flow.  Some 041540 records do not carry an explicit rank byte, so keep the
        // level filter useful instead of producing rank=0 and rejecting every 山贼.
        "山贼" -> 1
        else -> null
    }

    private fun inferCompositionFromLevel(level: Int): List<Int> = when {
        level <= 1 -> listOf(1, 0, 0, 0)
        level == 2 -> listOf(1, 1, 0, 0)
        level == 3 -> listOf(1, 1, 1, 0)
        else -> listOf(1, 1, 1, 1)
    }

    private fun String.normalizedKind(): String = when {
        contains("山贼") || contains("山賊") -> "山贼"
        contains("黄巾") || contains("黃巾") -> "黄巾"
        contains("渠帅") || contains("渠帥") -> "渠帅"
        contains("主将") || contains("主將") -> "主将"
        contains("主帅") || contains("主帥") -> "主帅"
        else -> this
    }

    private fun String.filterHexUppercase(): String =
        filter { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }.uppercase()

    private fun String.sliceOrNull(start: Int, endExclusive: Int): String? =
        if (start >= 0 && endExclusive <= length && start < endExclusive) substring(start, endExclusive) else null

    private fun String.parseUnsignedHexLong(): Long? =
        runCatching { java.lang.Long.parseUnsignedLong(this, 16) }.getOrNull()

    private fun String.hexToBytesOrNull(): ByteArray? {
        if (length % 2 != 0) return null
        return runCatching {
            ByteArray(length / 2) { index -> substring(index * 2, index * 2 + 2).toInt(16).toByte() }
        }.getOrNull()
    }

    private fun ByteArray.u8(offset: Int): Int = this[offset].toInt() and 0xff
    private fun ByteArray.u16(offset: Int): Int = (u8(offset) shl 8) or u8(offset + 1)
    private fun ByteArray.u64(offset: Int): Long {
        var out = 0L
        for (i in 0 until 8) out = (out shl 8) or (u8(offset + i).toLong() and 0xff)
        return out
    }

    private fun ByteArray.i32(offset: Int): Int =
        (u8(offset) shl 24) or (u8(offset + 1) shl 16) or (u8(offset + 2) shl 8) or u8(offset + 3)

    private fun ByteArray.readUtfAt(offset: Int): Pair<String, Int>? {
        if (offset + 2 > size) return null
        val len = u16(offset)
        val start = offset + 2
        val end = start + len
        if (len < 0 || end > size) return null
        return String(copyOfRange(start, end), Charsets.UTF_8) to end
    }

    private fun ByteArray.nextStructuredRecordOffset(from: Int): Int? {
        for (q in from until (size - 10).coerceAtLeast(from)) {
            if (u8(q) == 0 && u8(q + 1) == 0 && u8(q + 2) == 0 && u8(q + 3) == 0 && u8(q + 4) == 0) {
                val id = u64(q)
                val possibleLen = u16(q + 8)
                if (id > 0L && possibleLen in 2..24 && q + 10 + possibleLen <= size) return q
            }
        }
        return null
    }

    private fun ByteArray.toHexUpper(): String =
        joinToString(separator = "") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }.uppercase()

    private fun String.hexToText(): String? {
        if (length % 2 != 0) return null
        return runCatching {
            val bytes = ByteArray(length / 2) { index ->
                substring(index * 2, index * 2 + 2).toInt(16).toByte()
            }
            String(bytes, Charsets.UTF_8)
        }.getOrNull()
    }
}

data class TargetSearchPoint(
    val idHex: String,
    val id: Long,
    val kind: String,
    val kindHex: String,
    val rank: Int,
    val coordinate: MapCoordinate,
    val kz: Int,
    val rawRecord: String
)
