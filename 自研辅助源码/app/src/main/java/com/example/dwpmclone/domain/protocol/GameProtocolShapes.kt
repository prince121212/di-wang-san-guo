package com.example.dwpmclone.domain.protocol

import java.util.Locale

/**
 * Local-only protocol shape helpers recovered from static smali evidence.
 *
 * These helpers intentionally do not contain host URLs, session/key material, signatures,
 * credentials, or network execution. They are used by the clone skeleton to document and
 * unit-model the APK's local string-building logic.
 */
object GameCoordinateCodec {
    /** Equivalent to String.format("%4x%4x", x, y).replace(" ", "0") in the recovered APK. */
    fun encodeXY(x: Int, y: Int): String = String.format(Locale.ROOT, "%4x%4x", x, y).replace(" ", "0")

    fun buildResourcePointSearch(x: Int, y: Int): String =
        "000000000000000000041542" + encodeXY(x, y)

    fun buildTargetSearch(x: Int, y: Int): String =
        "000000000000000000041540" + encodeXY(x, y)
}

object BrushYellowExpeditionShape {
    private const val PREFIX = "000000000000000000"
    private const val SECOND_TAIL = "ffffffffffffffff000000"

    /** Desktop-captured canonical actionType=3 branch used before brush-yellow expedition. */
    fun buildFirstStage(
        generalIds: List<String>,
        targetId: String,
        actionType: Int = BrushYellowBehaviorContract.defaults().actionType
    ): String =
        build1520(generalIds, targetId, opcode = actionOpcode(0x1520, actionType), trailerBeforeTarget = "")

    /** Desktop-captured canonical actionType=3 branch used for the mutation request. */
    fun buildSecondStage(
        generalIds: List<String>,
        targetId: String,
        actionType: Int = BrushYellowBehaviorContract.defaults().actionType
    ): String =
        build1522(generalIds, targetId, opcode = actionOpcode(0x1522, actionType), trailerBeforeTarget = "")

    private fun actionOpcode(opcode: Int, actionType: Int): String {
        require(actionType in 0..255) { "actionType must fit one byte" }
        return opcode.toString(16).padStart(4, '0') + actionType.toString(16).padStart(2, '0') + "0"
    }

    fun build1520(generalIds: List<String>, targetId: String, opcode: String, trailerBeforeTarget: String = ""): String {
        val idsBlob = generalIds.joinToString(separator = "")
        val lenHex = (generalIds.size * 8 + 0x0a).toString(radix = 16)
        return PREFIX + lenHex + opcode + generalIds.size + idsBlob + trailerBeforeTarget + targetId
    }

    fun build1522(generalIds: List<String>, targetId: String, opcode: String, trailerBeforeTarget: String = ""): String {
        val idsBlob = generalIds.joinToString(separator = "")
        val lenHex = (generalIds.size * 8 + 0x15).toString(radix = 16)
        return PREFIX + lenHex + opcode + generalIds.size + idsBlob + trailerBeforeTarget + targetId + SECOND_TAIL
    }
}

/**
 * Passive-capture shape for opcode 1170.
 *
 * Evidence:
 * - 2026-07-08 bridge100 flow #008:
 *   wire tail 0000000000000000000311700000000001 -> response contains 仙女/赶路人/渣哥.
 * - 2026-07-08 bridge100 flow #010:
 *   wire tail 0000000000000000000311700000030001 -> another category contains 赶路人/赊刀人.
 *
 * `gameHex` intentionally excludes the envelope's empty signature UTF length (`0000`).
 * Captured binary tail is: PREFIX + len + opcode + 0000(empty signature) + payload.
 */
object RankListShape {
    private const val PREFIX = "000000000000000000"
    private const val OPCODE = "1170"

    fun buildCategory(category: Int): String {
        require(category in 0..0xff) { "rank category must fit one byte" }
        return PREFIX + "03" + OPCODE + category.toString(16).padStart(2, '0') + "0001"
    }

    fun buildRawParams(paramsHex: String): String {
        val params = paramsHex.filterNot { it.isWhitespace() }.lowercase(Locale.ROOT)
        require(params.length == 6) { "1170 observed payload params must be exactly 3 bytes / 6 hex chars" }
        require(params.all { it in '0'..'9' || it in 'a'..'f' }) { "params must be hex" }
        return PREFIX + "03" + OPCODE + params
    }

    fun buildCapturedWireTail(category: Int): String {
        val gameHex = buildCategory(category)
        val body = gameHex.removePrefix(PREFIX)
        return PREFIX + body.take(6) + "0000" + body.drop(6)
    }
}

/**
 * Passive-capture shape for opcode 1229: 批量补兵/批量补满.
 *
 * Evidence:
 * - 2026-07-08 bridge100 flow #030:
 *   wire tail ...1112290000 + 02 + 00000000006b4dac + 0000000000686b99 -> “批量补满成功”.
 * - 2026-07-08 bridge100 flow #038:
 *   wire tail ...1112290000 + 02 + 00000000006b4dae + 00000000006b4d9a -> “批量补满成功”.
 *
 * This is a state-changing action. The helper intentionally only models the local bytes for
 * docs/tests/dry-run review and must not be used as a live-send allow-list entry.
 */
object BatchRefillTroopsShape {
    private const val PREFIX = "000000000000000000"
    private const val OPCODE = "1229"

    fun build(ids: List<String>): String {
        require(ids.isNotEmpty()) { "at least one general/formation id is required" }
        require(ids.size <= 0xff) { "id count must fit one byte" }
        val normalizedIds = ids.joinToString(separator = "") { normalizeEightByteId(it) }
        val declaredPayloadLength = 1 + ids.size * 8
        return PREFIX +
            declaredPayloadLength.toString(16).padStart(2, '0') +
            OPCODE +
            ids.size.toString(16).padStart(2, '0') +
            normalizedIds
    }

    fun buildCapturedWireTail(ids: List<String>): String {
        val gameHex = build(ids)
        val body = gameHex.removePrefix(PREFIX)
        return PREFIX + body.take(6) + "0000" + body.drop(6)
    }

    private fun normalizeEightByteId(idHex: String): String {
        val clean = idHex.removePrefix("0x").removePrefix("0X").filterNot { it.isWhitespace() }.lowercase(Locale.ROOT)
        require(clean.isNotEmpty()) { "id must not be blank" }
        require(clean.all { it in '0'..'9' || it in 'a'..'f' }) { "id must be hex: $idHex" }
        val significant = clean.trimStart('0').ifEmpty { "0" }
        require(significant.length <= 16) { "captured 1229 ids are 8-byte padded values; got too-wide id: $idHex" }
        return significant.padStart(16, '0')
    }
}

data class BrushYellowPassiveWireDryRunPlan(
    val generalIds: List<String>,
    val targetWireId: String,
    val refillGameHex: String?,
    val refillCapturedWireTail: String?,
    val prepareGameHex: String,
    val prepareCapturedWireTail: String,
    val dispatchGameHex: String,
    val dispatchCapturedWireTail: String,
    val networkSendAllowed: Boolean,
    val blocker: String,
    val evidence: String
)

/**
 * Passive bridge100 dry-run planner for the observed batch-refill + brush-yellow wire chain.
 *
 * This planner is deliberately build-only. It does not call SessionAwareGameProtocolClient and
 * does not change the existing live-action gates. Its purpose is to make the app display/audit
 * the exact bytes we expect before any future live calibration.
 */
object BrushYellowPassiveWireDryRunPlanner {
    fun plan(
        generalIds: List<String>,
        targetWireId: String,
        includeBatchRefill: Boolean = true,
        actionType: Int = BrushYellowBehaviorContract.defaults().actionType
    ): BrushYellowPassiveWireDryRunPlan {
        val normalizedGenerals = generalIds.map { normalizeEightByteHex(it, "generalId") }
        require(normalizedGenerals.isNotEmpty()) { "generalIds must not be empty" }
        require(normalizedGenerals.size <= 0xff) { "general count must fit one byte" }
        val target = normalizeEightByteHex(targetWireId, "targetWireId")
        val refill = if (includeBatchRefill) BatchRefillTroopsShape.build(normalizedGenerals) else null
        val prepare = buildExpeditionGameHex(
            opcode = "1520",
            generalIds = normalizedGenerals,
            targetWireId = target,
            extraTail = "",
            actionType = actionType
        )
        val dispatch = buildExpeditionGameHex(
            opcode = "1522",
            generalIds = normalizedGenerals,
            targetWireId = target,
            extraTail = SECOND_TAIL,
            actionType = actionType
        )
        return BrushYellowPassiveWireDryRunPlan(
            generalIds = normalizedGenerals,
            targetWireId = target,
            refillGameHex = refill,
            refillCapturedWireTail = refill?.let { BatchRefillTroopsShape.buildCapturedWireTail(normalizedGenerals) },
            prepareGameHex = prepare,
            prepareCapturedWireTail = toCapturedWireTail(prepare),
            dispatchGameHex = dispatch,
            dispatchCapturedWireTail = toCapturedWireTail(dispatch),
            networkSendAllowed = false,
            blocker = "passive wire 链路仅用于 dry-run/审计；1229/1520/1522 都是状态改变或出征动作，未进入真实发送 allowlist",
            evidence = "shared-contract canonical brush-yellow actionType=$actionType"
        )
    }

    private fun buildExpeditionGameHex(
        opcode: String,
        generalIds: List<String>,
        targetWireId: String,
        extraTail: String,
        actionType: Int
    ): String {
        require(actionType in 0..255) { "actionType must fit one byte" }
        val payload = actionType.toString(16).padStart(2, '0') +
            generalIds.size.toString(16).padStart(2, '0') +
            generalIds.joinToString(separator = "") +
            targetWireId +
            extraTail
        return PREFIX + (payload.length / 2).toString(16).padStart(2, '0') + opcode + payload
    }

    private fun toCapturedWireTail(gameHex: String): String {
        val body = gameHex.removePrefix(PREFIX)
        return PREFIX + body.take(6) + "0000" + body.drop(6)
    }

    private fun normalizeEightByteHex(value: String, fieldName: String): String {
        val clean = value.removePrefix("0x").removePrefix("0X").filterNot { it.isWhitespace() }.lowercase(Locale.ROOT)
        require(clean.isNotEmpty()) { "$fieldName must not be blank" }
        require(clean.all { it in '0'..'9' || it in 'a'..'f' }) { "$fieldName must be hex: $value" }
        val significant = clean.trimStart('0').ifEmpty { "0" }
        require(significant.length <= 16) { "$fieldName must fit 8 bytes: $value" }
        return significant.padStart(16, '0')
    }

    private const val PREFIX = "000000000000000000"
    private const val SECOND_TAIL = "ffffffffffffffff000000"
}

/**
 * Response/query shapes recovered only for local documentation and mock tests.
 *
 * They must not be wired to a real server client without lawful authorization and a separate
 * implementation of the original app's native/session/signing boundary.
 */
object ResponseStructureShapes {
    const val OWNED_RESOURCE_POINT_COUNT_PAYLOAD = "000000000000000000001574"
    const val OWNED_RESOURCE_POINT_ERROR_MARKER = "erro"
    const val OWNED_RESOURCE_POINT_MAX_COUNT_OBSERVED = 5
    val ownedResourcePointRecordRegex: Regex =
        Regex("""0{8}(?!0{8}).{8}0[0-9A|B](00[0-9A-C].){2}0[1-3]""")

    const val ALARM_SCAN_PAYLOAD = "0000000000000000000d160007000000000000000000000032"
    const val ALARM_SCAN_ERROR_MARKER = "error"
    val alarmKeywords: Set<String> = setOf("【掠夺】", "【夺取】", "【掠奪】", "【奪取】", "【攻佔】", "【攻占】", "【攻城】", "敵軍")

    val resourcePointRecordRegex: Regex =
        Regex("""0000(?!0{8}).{8}0[0-9A|B]0[1-3](00[0-9A-C].){2}""")
    val resourcePointDetailRegex: Regex =
        Regex("""02D...0[0-4]0.0000....(00..)?""")

    val targetPointBaseRecordRegex: Regex =
        Regex("""0000.{8}.{4}""")
    val targetPointDetailRegex: Regex =
        Regex("""02D...0[0-4]0.0000....(00..)?""")

    val lootableFiefRecordRegex: Regex =
        Regex("""(E59FBAE59CB0|E5B081E59CB0|.{12})0.00..((E.{5}){2}|(E.{5}){3})0.00..00..""")
    const val LOOTABLE_FIEF_QUERY_PREFIX = "000000000000000000"
    const val LOOTABLE_FIEF_QUERY_OPCODE = "1310000100"
}
