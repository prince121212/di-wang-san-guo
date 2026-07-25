package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.MapCoordinate
import com.example.dwpmclone.domain.model.MineType

/**
 * Conservative parser for recovered 041542 resource-point / mine-search responses.
 *
 * Evidence:
 * - Landroid/o/ۦۥۛ;->ۦۛۚ(String)[Landroid/o/ۦۥۛ;
 * - base record regex: 0000(?!0{8}).{8}0[0-9A|B]0[1-3](00[0-9A-C].){2}
 * - id=record[0:12], kindCode=record[12:14], rank=record[14:16], kv=record[16:20], kw=record[20:24]
 * - detail marker 02D and 0100 are used for status/defense detail extraction.
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

    fun parse(responseHex: String): List<MineSearchResult> = parsePoints(responseHex).map { point ->
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
                "source" to "041542-response-parser",
                "rawRecord" to point.rawRecord
            )
        )
    }

    internal fun parsePoints(responseHex: String): List<ResourcePointSearchPoint> {
        val normalized = responseHex.filter { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }.uppercase()
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
