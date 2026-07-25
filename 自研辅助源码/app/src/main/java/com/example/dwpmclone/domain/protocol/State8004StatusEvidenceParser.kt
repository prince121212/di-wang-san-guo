package com.example.dwpmclone.domain.protocol

/**
 * Conservative text-evidence parser for the non-JiangLing part of 0x8004.
 *
 * Confirmed from live payloads: after the recovered JiangLing/S5 sections, 0x8004
 * contains length-prefixed UTF-8 strings for base/fief names, the current city, and
 * active policy/buff names with their effect text.  Numeric timer/cost fields around
 * those strings are still being calibrated; this parser therefore exposes only text
 * fields as displayable facts and keeps nearby numeric bytes as raw evidence.
 */
object State8004StatusEvidenceParser {
    private data class UtfHit(val offset: Int, val length: Int, val value: String) {
        val endOffset: Int get() = offset + 2 + length
    }

    fun recoverRecords(raw: String): List<Map<String, String>> {
        val bytes = raw.hexToBytesOrNull() ?: return emptyList()
        return recoverRecords(bytes)
    }

    fun recoverRecords(bytes: ByteArray): List<Map<String, String>> {
        val hits = scanUtfHits(bytes)
        if (hits.isEmpty()) return emptyList()
        val out = mutableListOf<Map<String, String>>()

        val fiefNames = hits
            .filter { it.value.looksLikeFiefName() }
            .distinctBy { it.value }
            .take(5)
        fiefNames.forEach { hit ->
            out += linkedMapOf(
                "name" to "基地/封地",
                "detail" to hit.value,
                "status" to "基地/封地",
                "remain" to hit.value,
                "kind" to "fiefName",
                "source" to "state8004-utf-evidence",
                "offset" to hit.offset.toString()
            )
        }

        val policies = recoverPolicyHits(bytes, hits)
        val firstPolicyNameOffset = policies.minOfOrNull { it.name.offset }
        val city = firstPolicyNameOffset?.let { first ->
            hits.lastOrNull { hit ->
                hit.offset < first && first - hit.endOffset in 0..80 && hit.value.looksLikeShortPlaceName()
            }
        }
        if (city != null) {
            out += linkedMapOf(
                "name" to "城池",
                "detail" to city.value,
                "status" to "城池",
                "remain" to city.value,
                "kind" to "cityName",
                "source" to "state8004-utf-evidence",
                "offset" to city.offset.toString()
            )
        }

        policies.forEach { policy ->
            out += linkedMapOf<String, String>().apply {
                put("name", policy.name.value)
                put("detail", policy.effect.value)
                put("effect", policy.effect.value)
                put("remain", policy.effect.value)
                put("kind", "policyBuff")
                put("source", "state8004-policy-utf-pair")
                put("nameOffset", policy.name.offset.toString())
                put("effectOffset", policy.effect.offset.toString())
                put("policyIndex", policy.policyIndex.toString())
                put("timerRawHex", policy.timerRawHex)
            }
        }
        return out
    }

    private data class PolicyHit(
        val name: UtfHit,
        val effect: UtfHit,
        val policyIndex: Int,
        val timerRawHex: String
    )

    private fun recoverPolicyHits(bytes: ByteArray, hits: List<UtfHit>): List<PolicyHit> {
        val policies = mutableListOf<PolicyHit>()
        val byEnd = hits.associateBy { it.endOffset }
        hits.filter { it.value.looksLikePolicyEffect() }.forEach { effect ->
            val name = byEnd[effect.offset] ?: return@forEach
            if (!name.value.looksLikePolicyName()) return@forEach
            val policyIndex = bytes.u16AtOrNull(name.offset - 4) ?: -1
            val timerRaw = bytes.copyOfRangeSafe(name.offset - 2, name.offset).toHex()
            policies += PolicyHit(name, effect, policyIndex, timerRaw)
        }
        return policies.distinctBy { it.name.value to it.effect.value }
    }

    private fun scanUtfHits(bytes: ByteArray): List<UtfHit> {
        val out = mutableListOf<UtfHit>()
        for (pos in 0 until bytes.size - 2) {
            val len = bytes.u16AtOrNull(pos) ?: continue
            if (len !in 2..160 || pos + 2 + len > bytes.size) continue
            val value = runCatching { String(bytes, pos + 2, len, Charsets.UTF_8) }.getOrNull()?.trim() ?: continue
            if (!value.looksLikeDisplayText()) continue
            out += UtfHit(pos, len, value)
        }
        return out.distinctBy { it.offset to it.value }
    }

    private fun String.looksLikeDisplayText(): Boolean {
        if (isBlank()) return false
        if (any { it.code < 0x20 }) return false
        val hasChinese = any { it in '\u4e00'..'\u9fff' }
        if (!hasChinese) return false
        return all { ch ->
            ch in '\u4e00'..'\u9fff' || ch.isLetterOrDigit() || ch in setOf(
                '·', '-', '_', ' ', '%', '/', '（', '）', '(', ')', '，', ',', '。', ':', '：', '！', '!', '*'
            )
        }
    }

    private fun String.looksLikeFiefName(): Boolean =
        (endsWith("基地") || endsWith("封地")) && length <= 12 && !contains("开启后")

    private fun String.looksLikeShortPlaceName(): Boolean =
        length in 2..6 && !contains("开启后") && !looksLikePolicyEffect() && !looksLikeFiefName()

    private fun String.looksLikePolicyName(): Boolean =
        length in 2..6 && !contains("开启") && !contains("提升") && !contains("降低") && !contains("费用")

    private fun String.looksLikePolicyEffect(): Boolean =
        contains("伤兵治疗费用") || contains("守军攻防") || contains("产能提升") || contains("铜钱粮食产能")

    private fun String.hexToBytesOrNull(): ByteArray? {
        val clean = trim().removePrefix("0x").removePrefix("0X")
            .filter { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }
        if (clean.length < 2 || clean.length % 2 != 0) return null
        return runCatching {
            ByteArray(clean.length / 2) { index -> clean.substring(index * 2, index * 2 + 2).toInt(16).toByte() }
        }.getOrNull()
    }

    private fun ByteArray.u16AtOrNull(index: Int): Int? =
        if (index >= 0 && index + 1 < size) ((this[index].toInt() and 0xff) shl 8) or (this[index + 1].toInt() and 0xff) else null

    private fun ByteArray.copyOfRangeSafe(from: Int, to: Int): ByteArray =
        if (from >= 0 && to >= from && to <= size) copyOfRange(from, to) else ByteArray(0)

    private fun ByteArray.toHex(): String = joinToString(separator = "") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }
}
