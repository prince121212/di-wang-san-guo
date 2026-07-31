package com.example.dwpmclone.data.protocol

import com.example.dwpmclone.domain.protocol.BrushYellowBehaviorContract

/**
 * Evidence-backed payload builder for 小黄点刷黄出征.
 *
 * Source evidence:
 * - /Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk/analysis/shuahuang_expedition_decode_2026-07-06/shuahuang_expedition_payload_builder_summary.md
 * - 2026-07-08 unpacked game dex re-check:
 *   LscriptPages/game/p;->O(I [J J)V writes byte(type), byte(count), longs(generals), long(target)
 *   then sends 0x1520; LscriptPages/game/p;->N(I [J J B B B J)V writes the same prefix,
 *   long(-1), three zero bytes, then sends 0x1522.
 *
 * The recovered formula uses concat(ids), where every id is already a protocol-encoded
 * fixed-width hex chunk. Therefore this builder intentionally accepts encoded chunks
 * instead of guessing how a Long general id maps to wire bytes.
 */
data class BrushYellowDispatchPayloads(
    val preparePayload: String,
    val expeditionPayload: String,
    val variant: Int = 3,
    val prepareOpcode: String = "1520030",
    val expeditionOpcode: String = "1522030"
)

object BrushYellowDispatchPayloadBuilder {
    private const val PREFIX = "000000000000000000"
    private const val EXPEDITION_TAIL = "ffffffffffffffff000000"

    fun buildBrushYellowPayloads(
        generalIdHexChunks: List<String>,
        targetIdHex: String,
        actionType: Int = BrushYellowBehaviorContract.defaults().actionType
    ): BrushYellowDispatchPayloads {
        require(generalIdHexChunks.isNotEmpty()) { "generalIdHexChunks must not be empty" }
        require(actionType in 0..255) { "actionType must fit one byte" }
        val ids = generalIdHexChunks.mapIndexed { index, value -> normalizeHex(value, "generalIdHexChunks[$index]") }
        val target = normalizeHex(targetIdHex, "targetIdHex")
        val concatIds = ids.joinToString(separator = "")
        val count = ids.size.toString()
        val prepareLengthHex = (ids.size * 8 + 0x0a).toString(radix = 16)
        val expeditionLengthHex = (ids.size * 8 + 0x15).toString(radix = 16)
        val actionTypeHex = actionType.toString(16).padStart(2, '0')
        val prepareOpcode = "1520${actionTypeHex}0"
        val expeditionOpcode = "1522${actionTypeHex}0"

        return BrushYellowDispatchPayloads(
            preparePayload = PREFIX + prepareLengthHex + prepareOpcode + count + concatIds + target,
            expeditionPayload = PREFIX + expeditionLengthHex + expeditionOpcode + count + concatIds + target + EXPEDITION_TAIL,
            variant = actionType,
            prepareOpcode = prepareOpcode,
            expeditionOpcode = expeditionOpcode
        )
    }

    private fun normalizeHex(value: String, fieldName: String): String {
        val normalized = value.trim().replace(" ", "").lowercase()
        require(normalized.isNotBlank()) { "$fieldName must not be blank" }
        require(normalized.all { it in '0'..'9' || it in 'a'..'f' }) { "$fieldName must be hex encoded: $value" }
        return normalized
    }
}
