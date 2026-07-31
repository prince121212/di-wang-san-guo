package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.DailyStep
import java.nio.ByteBuffer

/**
 * Local-only protocol shape helpers recovered from the "one-click daily" smali path.
 *
 * These helpers intentionally model string-building only. They do not include host URLs,
 * session/key/passCode material, signatures, credentials, or network execution.
 */
data class DailyProtocolStepShape(
    val step: DailyStep,
    val payloads: List<String>,
    val successLog: String,
    val delayAfterMillis: Long = 0L,
    val evidence: String
)

object DailyProtocolShapes {
    // Desktop parity: reading 0x6200 is a login/midnight concern, not part of sign-in.
    // Extra 0x6206 reward claims are separate operations and must not be hidden here.
    val signInSequence: List<String> = listOf(
        "000000000000000000006202"
    )

    /** Execution order recovered from Landroid/o/ۦ۠ۢ$ۦۖۨ;->ۦۦۥ()V. */
    val executionOrder: List<DailyStep> = listOf(
        DailyStep.SIGN_IN,
        DailyStep.SURPRISE_BOX,
        DailyStep.ADD_LOYALTY,
        DailyStep.COLLECT_TAX,
        DailyStep.ARENA_REWARD,
        DailyStep.SALARY,
        DailyStep.DELETE_MAIL,
        DailyStep.DONATE_COPPER,
        DailyStep.DONATE_FOOD,
        DailyStep.DONATE_TECH,
        DailyStep.CONVERT_HALF_FOOD_TO_COPPER
    )

    val recoveredSteps: Set<DailyStep> = executionOrder.toSet()

    const val SURPRISE_BOX: String = "00000000000000000009113400000000000de2b100"
    const val ADD_LOYALTY: String = "0000000000000000000c121f000000000000000002000000"
    const val COLLECT_TAX: String = "00000000000000000004133001000001"
    const val ARENA_REWARD: String = "000000000000000000006266"
    const val SALARY_REWARD: String = "00000000000000000001314b01"
    const val DELETE_MAIL: String = "0000000000000000000a11160001ffffffffffffffff"
    const val ARENA_DUPLICATE_MESSAGE: String = "领竞技币重复，22点后再领取！"

    fun buildDailyDiamondBoxPayload(): ByteArray =
        ByteBuffer.allocate(9)
            .putLong(0x0DE2B1L)
            .put(0)
            .array()

    /** Desktop build_delete_all_mail_payload: box=1, mailId=-1 means delete all. */
    fun buildDeleteAllMailPayload(): ByteArray =
        ByteBuffer.allocate(10)
            .put(0)
            .put(1)
            .putLong(-1L)
            .array()

    /** Desktop parse_delete_mail_response: action=0 and boxType=1 is authoritative success. */
    fun parseDeleteAllMailReceipt(payload: ByteArray): DeleteAllMailReceipt {
        require(payload.size >= 4) { "delete-mail response too short: ${payload.size}" }
        val action = payload[0].toInt() and 0xff
        val boxType = payload[1].toInt() and 0xff
        val remaining = ((payload[2].toInt() and 0xff) shl 8) or
            (payload[3].toInt() and 0xff)
        return DeleteAllMailReceipt(
            success = action == 0 && boxType == 1,
            action = action,
            boxType = boxType,
            remaining = remaining
        )
    }

    fun parseStatusMessage(payload: ByteArray): DailyStatusReceipt {
        require(payload.isNotEmpty()) { "daily response empty" }
        val status = payload[0].toInt()
        var message = ""
        var consumed = 1
        if (payload.size >= 3) {
            val length = ((payload[1].toInt() and 0xff) shl 8) or
                (payload[2].toInt() and 0xff)
            if (3 + length <= payload.size) {
                message = payload.copyOfRange(3, 3 + length).toString(Charsets.UTF_8)
                consumed = 3 + length
            }
        }
        return DailyStatusReceipt(
            success = status == 0,
            status = status,
            message = message,
            trailingBytes = payload.size - consumed
        )
    }

    /**
     * Normalizes the captured idempotent 0xe266 reply used after arena coins were
     * already claimed in the current 22:00 cycle. Opcode presence alone is not
     * enough: the duplicate shape is status -2, empty UTF, marker 1 and exactly
     * thirteen trailing reward-state bytes (16 bytes total).
     */
    fun parseArenaCoinClaimResponse(payload: ByteArray): ArenaCoinClaimReceipt {
        val parsed = parseStatusMessage(payload)
        val duplicate = parsed.status == -2 &&
            parsed.message.isBlank() &&
            payload.size == 16 &&
            payload[1] == 0.toByte() &&
            payload[2] == 0.toByte() &&
            payload[3] == 1.toByte()
        return ArenaCoinClaimReceipt(
            success = parsed.success || duplicate,
            status = parsed.status,
            message = if (duplicate) ARENA_DUPLICATE_MESSAGE else parsed.message,
            trailingBytes = parsed.trailingBytes,
            alreadyClaimed = duplicate,
            duplicateClaim = duplicate
        )
    }

    fun buildExecutionPlan(enabledSteps: Set<DailyStep>, donationFactorFz: Int = 1): List<DailyProtocolStepShape> =
        executionOrder.filter { it in enabledSteps }.map { shapeFor(it, donationFactorFz) }

    fun shapeFor(step: DailyStep, donationFactorFz: Int = 1): DailyProtocolStepShape = when (step) {
        DailyStep.SIGN_IN -> DailyProtocolStepShape(
            step = step,
            payloads = signInSequence,
            successLog = "已完成签到！",
            evidence = "ۦۦۥ lines 25286-26061"
        )
        DailyStep.SURPRISE_BOX -> fixed(step, SURPRISE_BOX, "已领取惊喜宝箱！", "26142-26353")
        DailyStep.ADD_LOYALTY -> fixed(step, ADD_LOYALTY, "已一键加忠！", "26434-26645")
        DailyStep.COLLECT_TAX -> fixed(step, COLLECT_TAX, "已一键征收！", "26726-26937")
        DailyStep.ARENA_REWARD -> fixed(step, ARENA_REWARD, "已领取竞技奖励！", "27018-27229")
        DailyStep.SALARY -> fixed(step, SALARY_REWARD, "已领取俸禄！", "27310-27521")
        DailyStep.DELETE_MAIL -> fixed(step, DELETE_MAIL, "已删除邮件！", "27609-27820")
        DailyStep.DONATE_COPPER -> DailyProtocolStepShape(
            step = step,
            payloads = listOf(donateCopper(donationFactorFz)),
            successLog = "已捐献铜钱！",
            delayAfterMillis = 1_000L,
            evidence = "27948-28096; donation builder p0=1 amount=fz*1000"
        )
        DailyStep.DONATE_FOOD -> DailyProtocolStepShape(
            step = step,
            payloads = listOf(donateFood(donationFactorFz)),
            successLog = "已捐献粮食！",
            delayAfterMillis = 1_000L,
            evidence = "28169-28364; donation builder p0=0 amount=fz*3000"
        )
        DailyStep.DONATE_TECH -> DailyProtocolStepShape(
            step = step,
            payloads = listOf(donateTech(donationFactorFz)),
            successLog = "已捐献科技！",
            evidence = "28436-28621; donation builder p0=2 amount=fz*1000"
        )
        DailyStep.CONVERT_HALF_FOOD_TO_COPPER -> DailyProtocolStepShape(
            step = step,
            payloads = emptyList(),
            successLog = "已转换一半粮食到铜钱！",
            evidence = "UI verified: 粮食转换一半到铜钱; routed via GameProtocolClient.convertFoodToCopper(FOOD_TO_COPPER_HALF) until original fixed payload is recovered"
        )
        else -> DailyProtocolStepShape(
            step = step,
            payloads = emptyList(),
            successLog = "未恢复的一键日常步骤：$step",
            evidence = "not recovered in richang-daily-execution-mechanism-2026-07-06"
        )
    }

    fun donateFood(fz: Int): String = donationPayload(type = 0, amount = fz * 3000)
    fun donateCopper(fz: Int): String = donationPayload(type = 1, amount = fz * 1000)
    fun donateTech(fz: Int): String = donationPayload(type = 2, amount = fz * 1000)

    fun donationPayload(type: Int, amount: Int): String {
        val amountHex16 = amountHex16(amount)
        return when (type) {
            0 -> "00000000000000000018140c0000000000000000" +
                amountHex16 +
                "0000000000000000"

            1 -> "00000000000000000018140c" +
                amountHex16 +
                "00000000000000000000000000000000"

            2 -> "00000000000000000005140a" +
                amountHex16.takeLast(10)

            else -> ""
        }
    }

    /**
     * Mirrors the recovered builder:
     * Long.toHexString((long) amount), then prepend "0" until the string has 16 chars.
     */
    fun amountHex16(amount: Int): String {
        var hex = java.lang.Long.toHexString(amount.toLong())
        while (hex.length < 16) {
            hex = "0$hex"
        }
        return hex
    }

    private fun fixed(step: DailyStep, payload: String, successLog: String, evidenceLines: String): DailyProtocolStepShape =
        DailyProtocolStepShape(
            step = step,
            payloads = listOf(payload),
            successLog = successLog,
            evidence = "ۦۦۥ lines $evidenceLines"
        )
}

data class DailyStatusReceipt(
    val success: Boolean,
    val status: Int,
    val message: String,
    val trailingBytes: Int
)

data class ArenaCoinClaimReceipt(
    val success: Boolean,
    val status: Int,
    val message: String,
    val trailingBytes: Int,
    val alreadyClaimed: Boolean,
    val duplicateClaim: Boolean
)

data class DeleteAllMailReceipt(
    val success: Boolean,
    val action: Int,
    val boxType: Int,
    val remaining: Int
)
