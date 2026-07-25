package com.example.dwpmclone.domain.protocol

/**
 * Offline descriptor for recovered 小黄点 gameHex strings.
 *
 * This intentionally does not execute network requests. It explains whether a recovered
 * string looks byte-aligned enough to be mapped to the self-developed binary GameCommand
 * envelope, or whether it still depends on the original app's string/native wrapper.
 */
data class GameHexDryRunDescriptor(
    val originalHex: String,
    val normalizedHex: String,
    val prefixHex: String?,
    val declaredLengthHex: String?,
    val declaredLengthBytes: Int?,
    val opcodeHex: String?,
    val payloadHex: String,
    val payloadByteCount: Int?,
    val alignment: GameHexAlignment,
    val lengthRelation: GameHexLengthRelation,
    val category: GameHexCategory,
    val binaryCommandCandidate: Boolean,
    val blocker: String
)

enum class GameHexAlignment { VALID_HEX_BYTES, ODD_HEX_NIBBLES, NON_HEX }

enum class GameHexLengthRelation {
    DECLARED_EQUALS_PAYLOAD,
    DECLARED_EQUALS_OPCODE_PLUS_PAYLOAD,
    MISMATCH,
    UNPARSEABLE
}

enum class GameHexCategory { READ_ONLY_QUERY, STATE_CHANGING_ACTION, EXPEDITION_ACTION, UNKNOWN }

object GameHexDryRunParser {
    private const val KNOWN_PREFIX = "000000000000000000"

    fun describe(gameHex: String): GameHexDryRunDescriptor {
        val normalized = gameHex.filterNot { it.isWhitespace() }.lowercase()
        val isHex = normalized.all { it in '0'..'9' || it in 'a'..'f' }
        if (!isHex) {
            return GameHexDryRunDescriptor(
                originalHex = gameHex,
                normalizedHex = normalized,
                prefixHex = null,
                declaredLengthHex = null,
                declaredLengthBytes = null,
                opcodeHex = null,
                payloadHex = "",
                payloadByteCount = null,
                alignment = GameHexAlignment.NON_HEX,
                lengthRelation = GameHexLengthRelation.UNPARSEABLE,
                category = GameHexCategory.UNKNOWN,
                binaryCommandCandidate = false,
                blocker = "gameHex 包含非十六进制字符，不能进入二进制 GameCommand dry-run"
            )
        }
        val prefix = normalized.takeIf { it.startsWith(KNOWN_PREFIX) }?.take(KNOWN_PREFIX.length)
        val body = if (prefix != null) normalized.drop(KNOWN_PREFIX.length) else normalized
        val declaredHex = body.takeIf { it.length >= 2 }?.take(2)
        val opcode = body.takeIf { it.length >= 6 }?.substring(2, 6)
        val payload = body.takeIf { it.length >= 6 }?.drop(6).orEmpty()
        val declared = declaredHex?.toIntOrNull(radix = 16)
        val payloadBytes = if (payload.length % 2 == 0) payload.length / 2 else null
        val alignment = if (normalized.length % 2 == 0 && payloadBytes != null) {
            GameHexAlignment.VALID_HEX_BYTES
        } else {
            GameHexAlignment.ODD_HEX_NIBBLES
        }
        val relation = when {
            declared == null || opcode == null -> GameHexLengthRelation.UNPARSEABLE
            payloadBytes == null -> GameHexLengthRelation.MISMATCH
            declared == payloadBytes -> GameHexLengthRelation.DECLARED_EQUALS_PAYLOAD
            declared == payloadBytes + 2 -> GameHexLengthRelation.DECLARED_EQUALS_OPCODE_PLUS_PAYLOAD
            else -> GameHexLengthRelation.MISMATCH
        }
        val category = classify(opcode)
        val binaryCandidate = prefix == KNOWN_PREFIX &&
            alignment == GameHexAlignment.VALID_HEX_BYTES &&
            relation == GameHexLengthRelation.DECLARED_EQUALS_PAYLOAD &&
            category == GameHexCategory.READ_ONLY_QUERY
        val blocker = when {
            prefix != KNOWN_PREFIX -> "缺少已知 18 位 0 前缀，不能确认属于统一 gameHex 形状"
            alignment != GameHexAlignment.VALID_HEX_BYTES -> "gameHex 存在奇数 nibble；小黄点字符串 wrapper 可能不是直接二进制 payload，需继续恢复 native/string wrapper"
            relation != GameHexLengthRelation.DECLARED_EQUALS_PAYLOAD -> "长度字段与 payload 字节数不一致；不能直接映射为当前 RealGameProtocolClient.GameCommand"
            category == GameHexCategory.EXPEDITION_ACTION || category == GameHexCategory.STATE_CHANGING_ACTION -> "这是动作类请求；native/session/request wrapper 与安全门禁完成前仅允许 dry-run"
            category == GameHexCategory.READ_ONLY_QUERY -> "可作为只读二进制 GameCommand 候选；仍需对应响应 parser 才能真机启用"
            else -> "未知 opcode；需补证据后才能接入"
        }
        return GameHexDryRunDescriptor(
            originalHex = gameHex,
            normalizedHex = normalized,
            prefixHex = prefix,
            declaredLengthHex = declaredHex,
            declaredLengthBytes = declared,
            opcodeHex = opcode,
            payloadHex = payload,
            payloadByteCount = payloadBytes,
            alignment = alignment,
            lengthRelation = relation,
            category = category,
            binaryCommandCandidate = binaryCandidate,
            blocker = blocker
        )
    }

    private fun classify(opcodeHex: String?): GameHexCategory = when (opcodeHex) {
        "1110", "1016", "1170", "1540", "1542", "1600", "1930", "1938", "1104", "1574" -> GameHexCategory.READ_ONLY_QUERY
        "1520", "1522" -> GameHexCategory.EXPEDITION_ACTION
        "6200", "6202", "6206", "1134", "121f", "1330", "6266", "314b", "1116",
        "140c", "140a", "1218", "1229", "1230", "1231", "1226", "1233", "1234", "1236", "1526" -> GameHexCategory.STATE_CHANGING_ACTION
        else -> GameHexCategory.UNKNOWN
    }
}
