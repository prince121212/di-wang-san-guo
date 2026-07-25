package com.example.dwpmclone.data.protocol

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
    val variant: Int = 10,
    val prepareOpcode: String = "15200a0",
    val expeditionOpcode: String = "15220a0"
)

object BrushYellowDispatchPayloadBuilder {
    private const val PREFIX = "000000000000000000"
    private const val EXPEDITION_TAIL = "ffffffffffffffff000000"
    private data class VariantSpec(
        val variant: Int,
        val prepareOpcode: String,
        val prepareTrailerPrefix: String,
        val prepareExtra: Int,
        val expeditionOpcode: String,
        val expeditionTrailerPrefix: String,
        val expeditionExtra: Int
    )

    private val VARIANTS = listOf(
        // Live brush-yellow/剿灭山贼 shape.  2026-07-08 matrix testing showed
        // action type 10 is accepted for 山贼 dispatch, while type 3 returns
        // 0x8522=ff0000 in the saved-settings flow.
        VariantSpec(10, "15200a0", "", 0x0a, "15220a0", "", 0x15),
        // Historical canonical method shape kept as fallback.  Do not insert "0000" before target:
        // doing so shifts the target long and produces 0x8522=ff0000 from the game server.
        VariantSpec(0, "1520030", "", 0x0a, "1522030", "", 0x15),
        VariantSpec(1, "1520020", "0000", 0x0a, "1522020", "0000", 0x15),
        VariantSpec(2, "15200e0", "ffffffff0004", 0x0e, "15220e0", "ffffffff0004", 0x19),
        VariantSpec(3, "1520010", "", 0x08, "1522010", "", 0x13),
        VariantSpec(4, "15200b0", "", 0x08, "15220b0", "", 0x13),
    )

    fun buildBrushYellowPayloads(
        generalIdHexChunks: List<String>,
        targetIdHex: String
    ): BrushYellowDispatchPayloads =
        buildBrushYellowPayloads(generalIdHexChunks, targetIdHex, variant = 10)

    fun buildBrushYellowPayloads(
        generalIdHexChunks: List<String>,
        targetIdHex: String,
        variant: Int
    ): BrushYellowDispatchPayloads {
        require(generalIdHexChunks.isNotEmpty()) { "generalIdHexChunks must not be empty" }
        val ids = generalIdHexChunks.mapIndexed { index, value -> normalizeHex(value, "generalIdHexChunks[$index]") }
        val target = normalizeHex(targetIdHex, "targetIdHex")
        val spec = VARIANTS.firstOrNull { it.variant == variant } ?: error("unknown brush-yellow payload variant: $variant")
        val concatIds = ids.joinToString(separator = "")
        val count = ids.size.toString()
        val prepareLengthHex = (ids.size * 8 + spec.prepareExtra).toString(radix = 16)
        val expeditionLengthHex = (ids.size * 8 + spec.expeditionExtra).toString(radix = 16)

        return BrushYellowDispatchPayloads(
            preparePayload = PREFIX + prepareLengthHex + spec.prepareOpcode + count + concatIds + spec.prepareTrailerPrefix + target,
            expeditionPayload = PREFIX + expeditionLengthHex + spec.expeditionOpcode + count + concatIds + spec.expeditionTrailerPrefix + target + EXPEDITION_TAIL,
            variant = spec.variant,
            prepareOpcode = spec.prepareOpcode,
            expeditionOpcode = spec.expeditionOpcode
        )
    }

    fun buildAllBrushYellowPayloadVariants(
        generalIdHexChunks: List<String>,
        targetIdHex: String
    ): List<BrushYellowDispatchPayloads> =
        VARIANTS.map { buildBrushYellowPayloads(generalIdHexChunks, targetIdHex, it.variant) }

    private fun normalizeHex(value: String, fieldName: String): String {
        val normalized = value.trim().replace(" ", "").lowercase()
        require(normalized.isNotBlank()) { "$fieldName must not be blank" }
        require(normalized.all { it in '0'..'9' || it in 'a'..'f' }) { "$fieldName must be hex encoded: $value" }
        return normalized
    }
}
