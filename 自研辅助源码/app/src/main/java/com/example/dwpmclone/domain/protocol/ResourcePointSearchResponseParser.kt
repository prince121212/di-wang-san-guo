package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.MapCoordinate
import com.example.dwpmclone.domain.model.MineType

/**
 * Parser for the real 0x8542 resource-point / mine-search response.
 *
 * Evidence:
 * - desktop `parse_8542_resources`, ported from scriptPages/game/p.i1(String)
 * - structured header: u16 centerX, u16 centerY, u8 recordCount
 * - structured records carry player owner/country only when detailFlag == 0
 * - Landroid/o/ۦۥۛ;->ۦۛۚ(String)[Landroid/o/ۦۥۛ;
 * - base record regex: 0000(?!0{8}).{8}0[0-9A|B]0[1-3](00[0-9A-C].){2}
 * - id=record[0:12], kindCode=record[12:14], rank=record[14:16], kv=record[16:20], kw=record[20:24]
 * - detail marker 02D and 0100 are used for status/defense detail extraction.
 *
 * The regex shape is retained only for older captures. Live structured replies are
 * parsed first so ownership is never inferred from the old `isEmpty` status bit.
 */
object ResourcePointSearchResponseParser {
    private val BASE_RECORD_REGEX = Regex("0000(?!00000000)[0-9A-Fa-f]{8}0[0-9AaBb]0[0-9A-Fa-f](00[0-9A-Ca-c][0-9A-Fa-f]){2}")
    private val DETAIL_REGEX = Regex("02D[0-9A-Fa-f]{3}0[0-4]0[0-9A-Fa-f]0000[0-9A-Fa-f]{4}(00[0-9A-Fa-f]{2})?")

    private val KIND_BY_CODE = mapOf(
        "01" to ResourceKind("金矿", MineType.GOLD),
        "02" to ResourceKind("银矿", MineType.SILVER),
        "03" to ResourceKind("冰玉矿", MineType.BING_YU),
        "04" to ResourceKind("仙芝", MineType.XIAN_ZHI),
        "05" to ResourceKind("玉露", MineType.YU_LU),
        "06" to ResourceKind("玄铁矿", MineType.XUAN_TIE),
        "07" to ResourceKind("水晶矿", MineType.CRYSTAL),
        "08" to ResourceKind("灵草", MineType.LING_CAO),
        "09" to ResourceKind("牧场", MineType.PASTURE_LV1),
        "0A" to ResourceKind("镔铁矿", MineType.BIN_TIE),
        "0B" to ResourceKind("浆果", MineType.JIANG_GUO)
    )

    fun parse(responseHex: String): List<MineSearchResult> {
        val normalized = responseHex.normalizedHex()
        val bytes = normalized.hexBytesOrNull()
        if (bytes != null && bytes.size >= 5) {
            parseStructured(bytes)?.let { return it }
        }
        return parseLegacy(normalized)
    }

    private fun parseLegacy(responseHex: String): List<MineSearchResult> = parsePoints(responseHex).map { point ->
        MineSearchResult(
            id = point.id,
            coordinate = point.coordinate,
            mineType = point.mineType,
            level = point.rank,
            reserve = point.kz?.toLong(),
            isEmpty = point.isEmpty,
            defenseCount = point.defenseCount,
            raw = mapOf(
                "idHex" to point.idHex,
                "kind" to point.kind,
                "kindCode" to point.kindCode,
                "rank" to point.rank.toString(),
                "kv" to point.coordinate.x.toString(),
                "kw" to point.coordinate.y.toString(),
                "kx" to point.isEmpty.toString(),
                "kz" to (point.kz?.toString() ?: ""),
                "statusHex" to point.statusHex,
                "detail" to point.detail,
                "playerOccupied" to "false",
                "source" to "041542-response-parser",
                "rawRecord" to point.rawRecord
            ),
            playerOccupied = false,
            ownerName = null
        )
    }

    /** Returns null when the payload is not the structured 0x8542 shape. */
    private fun parseStructured(payload: ByteArray): List<MineSearchResult>? = runCatching {
        val cursor = ResourceCursor(payload)
        val centerX = cursor.u16("centerX")
        val centerY = cursor.u16("centerY")
        val count = cursor.u8("resourceCount")
        require(centerX in 0..186 && centerY in 0..66 && count in 0..80) {
            "0x8542 structured header is invalid"
        }
        val resources = mutableListOf<MineSearchResult>()
        repeat(count) { recordIndex ->
            val recordStart = cursor.position
            val resourceId = cursor.i64("resource[$recordIndex].id")
            require(resourceId > 0L) { "0x8542 resource id must be positive" }
            val typeCode = cursor.u8("resource[$recordIndex].type")
            val level = cursor.u8("resource[$recordIndex].level")
            val x = cursor.u16("resource[$recordIndex].x")
            val y = cursor.u16("resource[$recordIndex].y")
            val detailFlag = cursor.u8("resource[$recordIndex].detailFlag")
            val ownerName = if (detailFlag == 0) {
                cursor.utf("resource[$recordIndex].ownerName")
            } else {
                ""
            }
            val ownerCountry = if (detailFlag == 0) {
                cursor.utf("resource[$recordIndex].ownerCountry")
            } else {
                ""
            }
            val amountA = cursor.i32("resource[$recordIndex].amountA")
            val amountB = cursor.i32("resource[$recordIndex].amountB")
            val description = cursor.utf("resource[$recordIndex].description")
            val valueJ = cursor.i32("resource[$recordIndex].valueJ")
            val valueK = cursor.i32("resource[$recordIndex].valueK")
            val troopGroups = List(cursor.u8("resource[$recordIndex].troopGroupCount")) { troopIndex ->
                StructuredTroopGroup(
                    typeCode = cursor.u8("resource[$recordIndex].troops[$troopIndex].type"),
                    count = cursor.u16("resource[$recordIndex].troops[$troopIndex].count"),
                    levelOrStatus = cursor.u8(
                        "resource[$recordIndex].troops[$troopIndex].levelOrStatus"
                    )
                )
            }
            val defenders = List(cursor.u8("resource[$recordIndex].defenderCount")) { defenderIndex ->
                StructuredDefender(
                    name = cursor.utf("resource[$recordIndex].defenders[$defenderIndex].name"),
                    fieldS = cursor.u16("resource[$recordIndex].defenders[$defenderIndex].fieldS"),
                    fieldR = cursor.u16("resource[$recordIndex].defenders[$defenderIndex].fieldR"),
                    fieldT = cursor.u8("resource[$recordIndex].defenders[$defenderIndex].fieldT"),
                    troopTypeCode = cursor.u8(
                        "resource[$recordIndex].defenders[$defenderIndex].troopType"
                    ),
                    generalLevelOrStatus = cursor.u8(
                        "resource[$recordIndex].defenders[$defenderIndex].generalLevelOrStatus"
                    ),
                    troopCount = cursor.i32(
                        "resource[$recordIndex].defenders[$defenderIndex].troopCount"
                    )
                )
            }
            val recordEnd = cursor.position
            val kind = structuredKind(typeCode, level)
            if (kind != null) {
                val playerOccupied = ownerName.isNotBlank() || ownerCountry.isNotBlank()
                resources += MineSearchResult(
                    id = resourceId,
                    coordinate = MapCoordinate(x, y),
                    mineType = kind.mineType,
                    level = level,
                    reserve = amountA.toLong(),
                    // Desktop business semantics: an "empty mine" means that no player
                    // owns it; NPC defenders are independent evidence.
                    isEmpty = !playerOccupied,
                    defenseCount = defenders.size,
                    raw = linkedMapOf(
                        "idHex" to resourceId.toString(16).padStart(16, '0'),
                        "kind" to kind.label,
                        "protocolKind" to kind.protocolLabel,
                        "kindCode" to typeCode.toString(16).padStart(2, '0').uppercase(),
                        "rank" to level.toString(),
                        "x" to x.toString(),
                        "y" to y.toString(),
                        "detailFlag" to detailFlag.toString(),
                        "ownerName" to ownerName,
                        "ownerCountry" to ownerCountry,
                        "playerOccupied" to playerOccupied.toString(),
                        "occupied" to playerOccupied.toString(),
                        "isEmpty" to (!playerOccupied).toString(),
                        "amountA" to amountA.toString(),
                        "amountB" to amountB.toString(),
                        "description" to description,
                        "valueJ" to valueJ.toString(),
                        "valueK" to valueK.toString(),
                        "troopGroups" to troopGroups.joinToString("|") { it.compact() },
                        "defenders" to defenders.joinToString("|") { it.compact() },
                        "defenderCount" to defenders.size.toString(),
                        "centerX" to centerX.toString(),
                        "centerY" to centerY.toString(),
                        "recordIndex" to recordIndex.toString(),
                        "source" to "8542-structured",
                        "rawRecord" to payload.copyOfRange(recordStart, recordEnd).toHex()
                    ),
                    playerOccupied = playerOccupied,
                    ownerName = ownerName.ifBlank { null }
                )
            }
        }
        if (cursor.position < payload.size) {
            val trailing = payload.copyOfRange(cursor.position, payload.size).toHex()
            resources.replaceAll { resource ->
                resource.copy(raw = resource.raw + ("trailingHex" to trailing))
            }
        }
        resources
    }.getOrNull()

    internal fun parsePoints(responseHex: String): List<ResourcePointSearchPoint> {
        val normalized = responseHex.normalizedHex().uppercase()
        val matches = BASE_RECORD_REGEX.findAll(normalized).toList()
        return matches.mapIndexedNotNull { index, match ->
            val nextStart = matches.getOrNull(index + 1)?.range?.first ?: normalized.length
            val tail = normalized.substring(match.range.last + 1, nextStart)
            val statusHex = tail.take(4).takeIf { it.length == 4 }
            val detail = DETAIL_REGEX.find(tail)?.value
            parseRecord(match.value, statusHex, detail)
        }
    }

    private fun parseRecord(record: String, statusHex: String?, detail: String?): ResourcePointSearchPoint? {
        val idHex = record.substring(0, 12)
        val id = runCatching { java.lang.Long.parseUnsignedLong(idHex, 16) }.getOrNull() ?: return null
        val kindCode = record.substring(12, 14).uppercase()
        val kind = KIND_BY_CODE[kindCode] ?: return null
        val rank = record.substring(14, 16).toIntOrNull(16) ?: 0
        val x = record.substring(16, 20).toIntOrNull(16) ?: 0
        val y = record.substring(20, 24).toIntOrNull(16) ?: 0
        val isEmpty = statusHex?.equals("0100", ignoreCase = true) ?: true
        val kz = detail?.let { if (it.length >= 18) it.substring(14, 18).toIntOrNull(16) else null }
        val defenseCount = if (isEmpty) 0 else null
        return ResourcePointSearchPoint(
            idHex = idHex,
            id = id,
            kindCode = kindCode,
            kind = kind.label,
            mineType = kind.mineType,
            rank = rank,
            coordinate = MapCoordinate(x, y),
            isEmpty = isEmpty,
            defenseCount = defenseCount,
            kz = kz,
            detail = detail.orEmpty(),
            statusHex = statusHex.orEmpty(),
            rawRecord = record
        )
    }

    private fun structuredKind(typeCode: Int, level: Int): StructuredResourceKind? = when (typeCode) {
        0x01 -> StructuredResourceKind("镔铁矿", "镔铁矿", MineType.BIN_TIE)
        0x02 -> StructuredResourceKind("水晶矿", "水晶矿", MineType.CRYSTAL)
        0x03 -> StructuredResourceKind("玄铁矿", "玄铁矿", MineType.XUAN_TIE)
        0x05 -> when (level) {
            1 -> StructuredResourceKind("一级牧场", "牧场", MineType.PASTURE_LV1)
            2 -> StructuredResourceKind("二级牧场", "牧场", MineType.PASTURE_LV2)
            3 -> StructuredResourceKind("三级牧场", "牧场", MineType.PASTURE_LV3)
            else -> null
        }
        0x06 -> StructuredResourceKind("浆果园", "浆果园", MineType.JIANG_GUO)
        0x07 -> StructuredResourceKind("灵草园", "灵草园", MineType.LING_CAO)
        0x08 -> StructuredResourceKind("玉露园", "玉露园", MineType.YU_LU)
        0x0A -> StructuredResourceKind("银矿", "银矿", MineType.SILVER)
        else -> null
    }
}

data class ResourcePointSearchPoint(
    val idHex: String,
    val id: Long,
    val kindCode: String,
    val kind: String,
    val mineType: MineType,
    val rank: Int,
    val coordinate: MapCoordinate,
    val isEmpty: Boolean,
    val defenseCount: Int?,
    val kz: Int?,
    val detail: String,
    val statusHex: String,
    val rawRecord: String
)

private data class ResourceKind(val label: String, val mineType: MineType)

private data class StructuredResourceKind(
    val label: String,
    val protocolLabel: String,
    val mineType: MineType
)

private data class StructuredTroopGroup(
    val typeCode: Int,
    val count: Int,
    val levelOrStatus: Int
) {
    fun compact(): String = "$typeCode,$count,$levelOrStatus"
}

private data class StructuredDefender(
    val name: String,
    val fieldS: Int,
    val fieldR: Int,
    val fieldT: Int,
    val troopTypeCode: Int,
    val generalLevelOrStatus: Int,
    val troopCount: Int
) {
    fun compact(): String = listOf(
        name,
        fieldS,
        fieldR,
        fieldT,
        troopTypeCode,
        generalLevelOrStatus,
        troopCount
    ).joinToString(",")
}

private class ResourceCursor(private val payload: ByteArray) {
    var position: Int = 0
        private set

    fun u8(field: String): Int {
        need(1, field)
        return payload[position++].toInt() and 0xff
    }

    fun u16(field: String): Int {
        need(2, field)
        val value = ((payload[position].toInt() and 0xff) shl 8) or
            (payload[position + 1].toInt() and 0xff)
        position += 2
        return value
    }

    fun i32(field: String): Int {
        need(4, field)
        val value = java.nio.ByteBuffer.wrap(payload, position, 4).int
        position += 4
        return value
    }

    fun i64(field: String): Long {
        need(8, field)
        val value = java.nio.ByteBuffer.wrap(payload, position, 8).long
        position += 8
        return value
    }

    fun utf(field: String): String {
        val length = u16("$field.length")
        need(length, field)
        return payload.copyOfRange(position, position + length)
            .toString(Charsets.UTF_8)
            .also { position += length }
    }

    private fun need(size: Int, field: String) {
        require(size >= 0 && position + size <= payload.size) {
            "0x8542 truncated at $field: position=$position need=$size size=${payload.size}"
        }
    }
}

private fun String.normalizedHex(): String = filter {
    it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F'
}

private fun String.hexBytesOrNull(): ByteArray? {
    if (length % 2 != 0) return null
    return runCatching { chunked(2).map { it.toInt(16).toByte() }.toByteArray() }.getOrNull()
}

private fun ByteArray.toHex(): String = joinToString("") {
    "%02x".format(it.toInt() and 0xff)
}
