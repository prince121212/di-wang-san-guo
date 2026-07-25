package com.example.dwpmclone.domain.protocol

/**
 * Conservative parser for passive-captured 1170 rank-list responses.
 *
 * Evidence from 2026-07-08 bridge100 flows #008/#010 shows rank rows as:
 *
 *   uint16 utf8NameLength + utf8Name + uint64 scoreOrCount
 *
 * after an opaque response header. The header/category/user-rank fields are still being
 * calibrated, so this parser only extracts stable row-level evidence and keeps raw hex snippets.
 */
object RankListResponseParser {
    fun parseHex(responseHex: String): RankListResponse {
        val bytes = responseHex.hexToBytesOrEmpty()
        return parseBytes(bytes, source = "1170-response-hex")
    }

    fun parseBytes(responseBytes: ByteArray, source: String = "1170-response-bytes"): RankListResponse {
        val entries = mutableListOf<RankListEntry>()
        var offset = 0
        while (offset + 2 <= responseBytes.size) {
            val nameLen = responseBytes.u16(offset)
            val nameStart = offset + 2
            val nameEnd = nameStart + nameLen
            val scoreEnd = nameEnd + SCORE_BYTES
            if (nameLen in 1..MAX_NAME_BYTES && scoreEnd <= responseBytes.size) {
                val nameBytes = responseBytes.copyOfRange(nameStart, nameEnd)
                val rawName = nameBytes.decodeUtf8OrNull()
                if (rawName != null && rawName.isLikelyRankName()) {
                    val scoreBytes = responseBytes.copyOfRange(nameEnd, scoreEnd)
                    entries += RankListEntry(
                        rank = entries.size + 1,
                        name = rawName.normalizedRankName(),
                        rawName = rawName,
                        scoreOrCount = scoreBytes.u64OrNull(),
                        scoreHex = scoreBytes.toHex(),
                        nameLengthBytes = nameLen,
                        offset = offset,
                        rawRecordHex = responseBytes.copyOfRange(offset, scoreEnd).toHex()
                    )
                    offset = scoreEnd
                    continue
                }
            }
            offset += 1
        }

        return RankListResponse(
            entries = entries.distinctBy { it.offset },
            rawTextPreview = responseBytes.toPrintableTextPreview(),
            evidence = "$source:lengthPrefixedUtf8NamePlusUint64"
        )
    }

    private fun ByteArray.u16(offset: Int): Int =
        ((this[offset].toInt() and 0xff) shl 8) or (this[offset + 1].toInt() and 0xff)

    private fun ByteArray.u64OrNull(): Long? {
        if (size != SCORE_BYTES) return null
        var value = 0L
        for (byte in this) {
            value = (value shl 8) or (byte.toLong() and 0xffL)
        }
        return value
    }

    private fun ByteArray.decodeUtf8OrNull(): String? =
        runCatching { String(this, Charsets.UTF_8) }.getOrNull()

    private fun String.isLikelyRankName(): Boolean {
        if (isBlank()) return false
        if (any { it == '\uFFFD' || it.code < 0x20 }) return false
        return any { it in '\u4e00'..'\u9fff' } && length <= MAX_NAME_CHARS
    }

    private fun String.normalizedRankName(): String = trim().trimEnd('.', '。')

    private fun String.hexToBytesOrEmpty(): ByteArray {
        val hex = filter { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }
        if (hex.length < 2 || hex.length % 2 != 0) return ByteArray(0)
        return runCatching {
            ByteArray(hex.length / 2) { index ->
                hex.substring(index * 2, index * 2 + 2).toInt(16).toByte()
            }
        }.getOrDefault(ByteArray(0))
    }

    private fun ByteArray.toHex(): String =
        joinToString(separator = "") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }

    private fun ByteArray.toPrintableTextPreview(maxChars: Int = 512): String =
        String(this, Charsets.UTF_8)
            .map { ch -> if (ch.code in 0x20..0x7e || ch in '\u4e00'..'\u9fff') ch else ' ' }
            .joinToString(separator = "")
            .replace(Regex("\\s+"), " ")
            .trim()
            .take(maxChars)

    private const val SCORE_BYTES = 8
    private const val MAX_NAME_BYTES = 32
    private const val MAX_NAME_CHARS = 12
}

data class RankListResponse(
    val entries: List<RankListEntry>,
    val rawTextPreview: String,
    val evidence: String
)

data class RankListEntry(
    val rank: Int,
    val name: String,
    val rawName: String,
    val scoreOrCount: Long?,
    val scoreHex: String,
    val nameLengthBytes: Int,
    val offset: Int,
    val rawRecordHex: String
)
