package com.example.dwpmclone.domain.protocol

/**
 * Local-only protocol shape helpers for the remaining automation paths recovered from smali:
 * persuade/release captive, plunder, resource-point send-general, warning/withdraw-defense.
 *
 * This file is documentation/mock logic only. It intentionally does not contain URLs, sessions,
 * native keys, credentials, live account state, or a network executor.
 */
object RemainingAutomationProtocolShapes {
    private const val PREFIX = "000000000000000000"
    private const val SECOND_TAIL = "ffffffffffffffff000000"

    const val CAPTIVE_PREPARE_PREFIX: String = "00000000000000000009123300"
    const val PERSUADE_CAPTIVE_PREFIX: String = "000000000000000000111234"
    const val RELEASE_CAPTIVE_PREFIX: String = "000000000000000000111236"

    const val WARNING_GENERAL_STATUS_QUERY: String =
        "0000000000000000000d160007000000000000000000000032"
    const val WARNING_LIST_QUERY: String = "000000000000000000001574"
    const val WITHDRAW_DEFENSE_PREFIX: String = "0000000000000000000a15260101"

    /** Recovered pre-step used by the auto-persuade path: 09123300 + fief/captive context id. */
    fun captivePrepareShape(contextId: String): String =
        CAPTIVE_PREPARE_PREFIX + contextId

    /** Recovered auto-persuade shape: 111234 + captive/general id + fief/context id + useGoldFlag. */
    fun persuadeCaptiveShape(captiveId: String, contextId: String, useGoldFlag: Int): String =
        PERSUADE_CAPTIVE_PREFIX + captiveId + contextId + useGoldFlag

    /** Recovered auto-release shape: 111236 + captive/general id + fief/context id. */
    fun releaseCaptiveShape(captiveId: String, contextId: String): String =
        RELEASE_CAPTIVE_PREFIX + captiveId + contextId

    /** Recovered warning withdrawal shape: 0a15260101 +驻防将领/驻防记录 id. */
    fun withdrawDefenseShape(defenseRecordId: String): String =
        WITHDRAW_DEFENSE_PREFIX + defenseRecordId

    /** Recovered resource-point search: 041542 + encoded coordinate. */
    fun resourcePointSearchShape(x: Int, y: Int): String =
        GameCoordinateCodec.buildResourcePointSearch(x, y)

    /** Recovered one-soldier resource-point send-general配兵: 0f1226 + generalId + 0000 + kind + countHex8. */
    fun resourceSendGeneralAssignOneSoldier(generalId: String, soldierKind: String): String =
        GeneralProtocolShapes.formationAssignShape(generalId, soldierKind, count = 1)

    /**
     * Generic first-stage expedition builder recovered from ۦۡۛ;->ۦۖۨ([String], String, int).
     *
     * Known modes:
     * - 1: resource-point send-general, opcode 1520010, no 0000 trailer before target.
     * - 2: auto fuben expedition, opcode 15200e0, inserts ffffffff0004 before fuben target id.
     * - 3: brush-yellow/target expedition, opcode 1520030, no trailer before target.
     * - 4: auto chuangguan expedition, opcode 15200b0, no trailer before owner/context id.
     */
    fun firstStageExpeditionShape(generalIds: List<String>, targetOrContextId: String, mode: ExpeditionMode): String {
        val idsBlob = generalIds.joinToString(separator = "")
        val lenHex = (generalIds.size * 8 + 0x0a).toString(radix = 16)
        return PREFIX + lenHex + mode.firstOpcode + generalIds.size + idsBlob + mode.firstTrailer + targetOrContextId
    }

    /**
     * Generic second-stage expedition builder recovered from ۦۡۛ;->ۦۖ۬([String], String, int).
     *
     * Shape mirrors first-stage but uses length n*8+0x15, 1522xxx opcode, and the common tail.
     */
    fun secondStageExpeditionShape(generalIds: List<String>, targetOrContextId: String, mode: ExpeditionMode): String {
        val idsBlob = generalIds.joinToString(separator = "")
        val lenHex = (generalIds.size * 8 + 0x15).toString(radix = 16)
        return PREFIX + lenHex + mode.secondOpcode + generalIds.size + idsBlob + mode.secondTrailer +
            targetOrContextId + mode.secondExtraBeforeCommonTail + SECOND_TAIL
    }

    fun resourceSendGeneralFirstStage(generalIds: List<String>, resourcePointId: String): String =
        firstStageExpeditionShape(generalIds, resourcePointId, ExpeditionMode.RESOURCE_POINT_SEND_GENERAL)

    fun resourceSendGeneralSecondStage(generalIds: List<String>, resourcePointId: String): String =
        secondStageExpeditionShape(generalIds, resourcePointId, ExpeditionMode.RESOURCE_POINT_SEND_GENERAL)

    fun brushYellowFirstStage(generalIds: List<String>, targetId: String): String =
        firstStageExpeditionShape(generalIds, targetId, ExpeditionMode.BRUSH_YELLOW)

    fun brushYellowSecondStage(generalIds: List<String>, targetId: String): String =
        secondStageExpeditionShape(generalIds, targetId, ExpeditionMode.BRUSH_YELLOW)

    fun autoFubenFirstStage(generalIds: List<String>, fubenTargetId: String): String =
        firstStageExpeditionShape(generalIds, fubenTargetId, ExpeditionMode.AUTO_FUBEN)

    fun autoFubenSecondStage(generalIds: List<String>, fubenTargetId: String): String =
        secondStageExpeditionShape(generalIds, fubenTargetId, ExpeditionMode.AUTO_FUBEN)
}

enum class ExpeditionMode(
    val firstOpcode: String,
    val secondOpcode: String,
    val firstTrailer: String = "",
    val secondTrailer: String = "",
    val secondExtraBeforeCommonTail: String = "",
) {
    PLUNDER_OR_FIEF(firstOpcode = "1520020", secondOpcode = "1522020", firstTrailer = "0000", secondTrailer = "0000"),
    RESOURCE_POINT_SEND_GENERAL(firstOpcode = "1520010", secondOpcode = "1522010"),
    AUTO_FUBEN(firstOpcode = "15200e0", secondOpcode = "15220e0", firstTrailer = "ffffffff0004", secondTrailer = "ffffffff0004"),
    BRUSH_YELLOW(firstOpcode = "1520030", secondOpcode = "1522030"),
    CHUANG_GUAN(firstOpcode = "15200b0", secondOpcode = "15220b0"),
}

sealed interface RemainingAutomationAction {
    data class Log(val message: String) : RemainingAutomationAction
    data class FixedPayload(val gameHex: String, val meaning: String) : RemainingAutomationAction
}
