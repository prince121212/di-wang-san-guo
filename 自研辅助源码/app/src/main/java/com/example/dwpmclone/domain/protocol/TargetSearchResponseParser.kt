package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.MapCoordinate

/**
 * Parser for the 0x8540 response returned by the recovered 0x1540 target search.
 *
 * Evidence:
 * - Landroid/o/ۦۤ۠;->ۦۖ۫(String,ZZZ)[Landroid/o/ۦۤ۠;
 * - structured records use the same field order as desktop `parse_8540_targets`
 * - the four composition counters come from the real unit rows, never from level templates
 * - marker scanning remains only as a compatibility fallback for incomplete captures
 *
 * A partial record is still surfaced for diagnostics, but it deliberately has no usable
 * composition. This prevents a configured 步/弓/骑/车 filter from accepting guessed data.
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
        return parseCompleteStructured8540(payload)
            ?: parsePartialStructured8540(payload)
    }

    /** Exact port of the desktop 0x8540 field order. */
    private fun parseCompleteStructured8540(payload: ByteArray): List<MapTarget>? = runCatching {
        val cursor = BinaryCursor(payload)
        val mapWidth = cursor.u16()
        val mapHeight = cursor.u16()
        val count = cursor.u8().also { require(it in 0..80) }
        val targets = mutableListOf<MapTarget>()
        repeat(count) { recordIndex ->
            val recordStart = cursor.position
            val id = cursor.u64().also { require(it > 0L) }
            val nameStart = cursor.position
            val name = cursor.utf()
            val nameEnd = cursor.position
            val metaA = cursor.u8()
            val metaB = cursor.u8()
            val levelByte = cursor.u8()
            val metaD = cursor.u16()
            val metaE = cursor.u16()
            val resource = cursor.utf()
            val resource1 = cursor.i32()
            val resource2 = cursor.i32()
            val lootCount = cursor.u8().also { require(it in 0..80) }
            val lootIds = List(lootCount) { cursor.i32().toLong() and 0xffff_ffffL }
            val unitCount = cursor.u8().also { require(it in 0..80) }
            val composition = linkedMapOf(
                "foot" to 0,
                "bow" to 0,
                "cavalry" to 0,
                "chariot" to 0
            )
            val units = mutableListOf<Structured8540Unit>()
            repeat(unitCount) {
                val generalName = cursor.utf()
                val unitA = cursor.u16()
                val unitUid = cursor.u16()
                val unitB = cursor.u8()
                val majorCode = cursor.u8()
                val soldierTypeCode = cursor.u8()
                val soldierCount = cursor.i32()
                val majorKey = when (majorCode) {
                    0 -> "foot"
                    1 -> "bow"
                    2 -> "cavalry"
                    4 -> "chariot"
                    else -> error("unknown 0x8540 major troop code=$majorCode")
                }
                composition[majorKey] = composition.getValue(majorKey) + 1
                units += Structured8540Unit(
                    generalName = generalName,
                    unitA = unitA,
                    unitUid = unitUid,
                    unitB = unitB,
                    majorCode = majorCode,
                    soldierTypeCode = soldierTypeCode,
                    soldierCount = soldierCount
                )
            }

            val kind = name.normalizedKind()
            val level = Regex("""(\d+)级""").find(name)?.groupValues?.getOrNull(1)?.toIntOrNull()
                ?: levelByte.takeIf { it in 1..99 }
                ?: fixedRankForKind(kind)
                ?: 0
            val rawRecord = payload.copyOfRange(recordStart, nameEnd).toHexUpper()
            val structuredRecord = payload.copyOfRange(recordStart, cursor.position).toHexUpper()
            val compositionCode = listOf("foot", "bow", "cavalry", "chariot")
                .joinToString("") { composition.getValue(it).toString() }
            targets += MapTarget(
                id = id,
                // Desktop uses metaD/metaE as the target coordinate. The two i32 values
                // after the reward text are resource metadata, not x/y.
                coordinate = MapCoordinate(metaD, metaE),
                type = kind,
                raw = linkedMapOf(
                    "idHex" to id.toString(16).padStart(12, '0'),
                    "targetIdHex" to id.toString(16).padStart(16, '0'),
                    "kind" to kind,
                    "name" to name,
                    "rank" to level.toString(),
                    "level" to level.toString(),
                    "kv" to metaD.toString(),
                    "kw" to metaE.toString(),
                    "x" to metaD.toString(),
                    "y" to metaE.toString(),
                    "resource" to resource,
                    "resource1" to resource1.toString(),
                    "resource2" to resource2.toString(),
                    "lootIds" to lootIds.joinToString(","),
                    "dropCategories" to resource.dropCategories().joinToString(","),
                    "unitGeneralNames" to units.joinToString("|") { it.generalName },
                    "unitMajorCodes" to units.joinToString(",") { it.majorCode.toString() },
                    "unitSoldierTypeCodes" to units.joinToString(",") { it.soldierTypeCode.toString() },
                    "unitSoldierCounts" to units.joinToString(",") { it.soldierCount.toString() },
                    "unitUids" to units.joinToString(",") { it.unitUid.toString() },
                    "unitMetaA" to units.joinToString(",") { it.unitA.toString() },
                    "unitMetaB" to units.joinToString(",") { it.unitB.toString() },
                    "unitCount" to unitCount.toString(),
                    "foot" to composition.getValue("foot").toString(),
                    "bow" to composition.getValue("bow").toString(),
                    "cavalry" to composition.getValue("cavalry").toString(),
                    "chariot" to composition.getValue("chariot").toString(),
                    "compositionCode" to compositionCode,
                    "compositionSource" to "8540-units",
                    "rawRecord" to rawRecord,
                    "structuredRecordHex" to structuredRecord,
                    "mapWidth" to mapWidth.toString(),
                    "mapHeight" to mapHeight.toString(),
                    "recordIndex" to recordIndex.toString(),
                    "nameStart" to nameStart.toString(),
                    "metaA" to metaA.toString(),
                    "metaB" to metaB.toString(),
                    "levelByte" to levelByte.toString(),
                    "metaD" to metaD.toString(),
                    "metaE" to metaE.toString(),
                    "source" to "8540-structured"
                )
            )
        }
        targets
    }.getOrNull()

    /**
     * Compatibility parser for old/truncated fixtures. It never invents composition.
     * Complete live payloads are consumed by [parseCompleteStructured8540] first.
     */
    private fun parsePartialStructured8540(payload: ByteArray): List<MapTarget> = runCatching {
        val mapWidth = payload.u16(0)
        val mapHeight = payload.u16(2)
        val count = payload.u8(4).coerceIn(0, 80)
        var p = 5
        val targets = mutableListOf<MapTarget>()
        repeat(count) { recordIndex ->
            if (p + 10 > payload.size) return@repeat
            val recordStart = p
            val id = payload.u64(p)
            p += 8
            if (id <= 0L) return@repeat
            val nameResult = payload.readUtfAt(p) ?: return@repeat
            val name = nameResult.first
            p = nameResult.second
            val nameEnd = p
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
            val resource1 = payload.i32(p)
            p += 4
            val resource2 = payload.i32(p)
            p += 4
            val nextPos = payload.nextStructuredRecordOffset(p) ?: payload.size
            val tailHex = payload.copyOfRange(p, nextPos.coerceIn(p, payload.size)).toHexUpper().take(120)
            p = nextPos

            val kind = name.normalizedKind()
            val level = Regex("""(\d+)级""").find(name)?.groupValues?.getOrNull(1)?.toIntOrNull()
                ?: levelByte.takeIf { it in 1..99 }
                ?: fixedRankForKind(kind)
                ?: 0
            targets += MapTarget(
                id = id,
                coordinate = MapCoordinate(metaD, metaE),
                type = kind,
                raw = linkedMapOf(
                    "idHex" to id.toString(16).padStart(12, '0'),
                    "targetIdHex" to id.toString(16).padStart(16, '0'),
                    "kind" to kind,
                    "name" to name,
                    "rank" to level.toString(),
                    "level" to level.toString(),
                    "kv" to metaD.toString(),
                    "kw" to metaE.toString(),
                    "x" to metaD.toString(),
                    "y" to metaE.toString(),
                    "resource" to resource,
                    "resource1" to resource1.toString(),
                    "resource2" to resource2.toString(),
                    "dropCategories" to resource.dropCategories().joinToString(","),
                    "compositionCode" to "",
                    "compositionSource" to "unavailable",
                    "rawRecord" to payload.copyOfRange(recordStart, nameEnd).toHexUpper(),
                    "mapWidth" to mapWidth.toString(),
                    "mapHeight" to mapHeight.toString(),
                    "recordIndex" to recordIndex.toString(),
                    "metaA" to metaA.toString(),
                    "metaB" to metaB.toString(),
                    "levelByte" to levelByte.toString(),
                    "metaD" to metaD.toString(),
                    "metaE" to metaE.toString(),
                    "tailHex" to tailHex,
                    "source" to "8540-structured-partial"
                )
            )
        }
        targets
    }.getOrDefault(emptyList())

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

    private fun String.normalizedKind(): String = when {
        contains("山贼") || contains("山賊") -> "山贼"
        contains("黄巾") || contains("黃巾") -> "黄巾"
        contains("渠帅") || contains("渠帥") -> "渠帅"
        contains("主将") || contains("主將") -> "主将"
        contains("主帅") || contains("主帥") -> "主帅"
        else -> this
    }

    private fun String.dropCategories(): List<String> =
        listOf("资源", "宝箱", "装备", "宝物").filter(::contains)

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

    private data class Structured8540Unit(
        val generalName: String,
        val unitA: Int,
        val unitUid: Int,
        val unitB: Int,
        val majorCode: Int,
        val soldierTypeCode: Int,
        val soldierCount: Int
    )

    private class BinaryCursor(private val bytes: ByteArray) {
        var position: Int = 0
            private set

        fun u8(): Int {
            need(1)
            return bytes[position++].toInt() and 0xff
        }

        fun u16(): Int = (u8() shl 8) or u8()

        fun u64(): Long {
            need(8)
            var value = 0L
            repeat(8) { value = (value shl 8) or u8().toLong() }
            return value
        }

        fun i32(): Int {
            need(4)
            return (u8() shl 24) or (u8() shl 16) or (u8() shl 8) or u8()
        }

        fun utf(): String {
            val length = u16()
            need(length)
            val start = position
            position += length
            return String(bytes, start, length, Charsets.UTF_8)
        }

        private fun need(count: Int) {
            require(count >= 0 && position + count <= bytes.size) {
                "truncated 0x8540 payload at offset=$position need=$count size=${bytes.size}"
            }
        }
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
