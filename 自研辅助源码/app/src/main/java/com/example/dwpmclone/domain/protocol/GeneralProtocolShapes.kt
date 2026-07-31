package com.example.dwpmclone.domain.protocol

import java.nio.ByteBuffer

/**
 * Local-only protocol shape helpers recovered from the general / formation / healing paths.
 *
 * This file models string-building and task-planning evidence only. It intentionally does not
 * include host URLs, credentials, session/key/passCode material, signatures, native encoders,
 * or network execution. Use it as an offline documentation/mock layer for the skeleton app.
 */
object GeneralProtocolShapes {
    const val GENERAL_STATUS_QUERY: String = "0000000000000000000d160007000000000000000000000032"
    const val ADD_LOYALTY: String = "0000000000000000000c121f000000000000000002000000"

    private const val ADD_ENERGY_PREFIX = "0000000000000000000c1218"
    private const val ADD_ENERGY_MIDDLE = "000"
    private const val ADD_ENERGY_TAIL = "0001"

    private const val RESCUE_PREFIX = "000000000000000000111238"
    private const val RESCUE_FIEF_PREFIX = "00000000000000000009123301"

    private const val HEAL_COST_PREFIX = "0000000000000000000e1231"
    private const val HEAL_COST_TAIL = "ffffff"
    private const val HEAL_PREFIX = "000000000000000000101230"
    private const val HEAL_TAIL = "020000ffffffff00"
    private const val HEAL_ALL_COST_PREFIX = "0000000000000000000e1231"
    private const val HEAL_ALL_COST_TAIL = "ffffffffffff"
    private const val HEAL_ALL_PREFIX = "000000000000000000101230"
    private const val HEAL_ALL_TAIL = "020000ffffffff00"

    private const val RESOURCE_CONVERSION_PREFIX = "0000000000000000000911520"

    private const val FORMATION_ASSIGN_PREFIX = "0000000000000000000f1226"
    private const val FORMATION_ASSIGN_MIDDLE = "0000"

    private const val REFILL_PREFIX = "000000000000000000"
    const val REFILL_UNRESOLVED_SEGMENT: String = "<unresolved_fixed_segment>"

    /** Recovered add-energy shape: 0c1218 + generalId + 000 + drugNoHex + 0001. */
    fun addEnergyShape(generalId: String, drugNo: Int): String =
        ADD_ENERGY_PREFIX + generalId + ADD_ENERGY_MIDDLE + drugNo.toString(radix = 16) + ADD_ENERGY_TAIL

    fun buildAddEnergyPayload(generalId: Long, itemId: Int = 12, count: Int = 1): ByteArray {
        require(generalId > 0) { "generalId must be positive" }
        require(itemId in 0..0xffff) { "itemId must fit unsigned short" }
        require(count in 1..0xffff) { "count must fit unsigned short and be positive" }
        return ByteBuffer.allocate(12)
            .putLong(generalId)
            .putShort(itemId.toShort())
            .putShort(count.toShort())
            .array()
    }

    fun buildHealAllPreInfoPayload(fiefId: Long): ByteArray {
        require(fiefId > 0) { "fiefId must be positive" }
        return ByteBuffer.allocate(14)
            .putLong(fiefId)
            .putShort((-1).toShort())
            .putInt(-1)
            .array()
    }

    fun buildHealAllPayload(fiefId: Long): ByteArray {
        require(fiefId > 0) { "fiefId must be positive" }
        return ByteBuffer.allocate(16)
            .putLong(fiefId)
            .put(2)
            .putShort(0)
            .putInt(-1)
            .put(0)
            .array()
    }

    fun parseHealPreInfoResponse(
        payload: ByteArray,
        expectedFiefId: Long,
        expectedSoldierType: Int = -1
    ): HealPreInfoReceipt {
        require(payload.size >= 26) { "0x8231 response too short" }
        val buffer = ByteBuffer.wrap(payload)
        val fiefId = buffer.long
        val soldierType = buffer.short.toInt()
        val copperCost = buffer.long
        val goldCost = buffer.long
        require(fiefId == expectedFiefId) {
            "0x8231 fief mismatch: expected=$expectedFiefId actual=$fiefId"
        }
        require(soldierType == expectedSoldierType) {
            "0x8231 soldier type mismatch: expected=$expectedSoldierType actual=$soldierType"
        }
        require(copperCost >= 0 && goldCost >= 0) { "0x8231 returned negative cost" }
        return HealPreInfoReceipt(fiefId, soldierType, copperCost, goldCost)
    }

    fun parseHealResponse(payload: ByteArray): HealActionReceipt {
        require(payload.size >= 18) { "0x8230 response too short" }
        val buffer = ByteBuffer.wrap(payload)
        val status = buffer.get().toInt()
        val firstLong = buffer.long
        val secondLong = buffer.long
        val hasExtraState = buffer.get().toInt() != 0
        val message = when (status) {
            0 -> "治疗成功"
            -1 -> "铜钱不足"
            -2 -> "治疗失败"
            -3 -> "黄金不足"
            else -> "未知治疗状态 $status"
        }
        return HealActionReceipt(
            success = status == 0,
            status = status,
            message = message,
            firstLong = firstLong,
            secondLong = secondLong,
            hasExtraState = hasExtraState,
            trailingBytes = payload.size - 18
        )
    }

    fun parseAddEnergyResponse(payload: ByteArray): AddEnergyReceipt {
        require(payload.isNotEmpty()) { "0x8218 response empty" }
        val status = payload[0].toInt()
        val message = when (status) {
            0 -> "活血丹使用成功"
            else -> if (payload.size >= 3) {
                val length = ((payload[1].toInt() and 0xff) shl 8) or
                    (payload[2].toInt() and 0xff)
                require(3 + length <= payload.size) { "0x8218 error message exceeds payload" }
                payload.copyOfRange(3, 3 + length).toString(Charsets.UTF_8)
            } else {
                "活血丹使用失败，状态=$status"
            }
        }
        return AddEnergyReceipt(status == 0, status, message, payload.size - 1)
    }

    fun buildAddLoyaltyPayload(generalId: Long, delta: Int): ByteArray {
        require(generalId > 0L) { "generalId must be positive" }
        require(delta in 1..0xffff) { "loyalty delta must fit unsigned short" }
        return ByteBuffer.allocate(12)
            .putLong(generalId)
            .put(0)
            .putShort(delta.toShort())
            .put(0)
            .array()
    }

    fun parseAddLoyaltyResponse(payload: ByteArray): AddLoyaltyReceipt {
        require(payload.size >= 42) { "0x821f response too short: ${payload.size}/42" }
        val buffer = ByteBuffer.wrap(payload)
        val result = buffer.get().toInt()
        val mode = buffer.get().toInt() and 0xff
        val generalId = buffer.long
        val actualCost = buffer.long
        val copper = buffer.long
        val gold = buffer.long
        val resourceG = buffer.long
        val generals = if (mode == 2) {
            require(buffer.hasRemaining()) { "0x821f batch response lacks general count" }
            val count = buffer.get().toInt() and 0xff
            List(count) {
                require(buffer.remaining() >= 12) { "0x821f batch general record incomplete" }
                LoyaltyUpdate(
                    generalId = buffer.long,
                    loyalty = buffer.short.toInt() and 0xffff,
                    loyaltyLimit = buffer.short.toInt() and 0xffff
                )
            }
        } else {
            require(buffer.remaining() >= 4) { "0x821f response lacks loyalty result" }
            listOf(
                LoyaltyUpdate(
                    generalId = generalId,
                    loyalty = buffer.short.toInt() and 0xffff,
                    loyaltyLimit = buffer.short.toInt() and 0xffff
                )
            )
        }
        return AddLoyaltyReceipt(
            success = result == 0,
            result = result,
            mode = mode,
            generalId = generalId,
            actualCost = actualCost,
            copper = copper,
            gold = gold,
            resourceG = resourceG,
            generals = generals,
            trailingBytes = buffer.remaining(),
            message = if (result == 0) "忠诚度增加成功" else "忠诚度增加失败(result=$result)"
        )
    }

    fun buildFoodToCopperPayload(foodAmount: Long): ByteArray {
        require(foodAmount > 0) { "foodAmount must be positive" }
        return ByteBuffer.allocate(9)
            .put(1)
            .putLong(foodAmount)
            .array()
    }

    fun rescueShape(generalId: String, fiefId: String): String =
        RESCUE_PREFIX + generalId + fiefId

    fun rescueFiefShape(fiefId: String): String =
        RESCUE_FIEF_PREFIX + fiefId

    fun healCostShape(itemDecoded: String): String =
        HEAL_COST_PREFIX + itemDecoded + HEAL_COST_TAIL

    fun healShape(itemDecoded: String): String =
        HEAL_PREFIX + itemDecoded + HEAL_TAIL

    /**
     * Recovered 2026-07-08 from q.k1/q.d0/q.l1:
     *   0x1231 all-heal pre-info = fiefId + soldierType=-1 + count=-1
     *   0x1230 all-heal request   = fiefId + group=2 + soldierType=0 + count=-1 + useGold=0
     */
    fun healAllCostShape(fiefId: String): String =
        HEAL_ALL_COST_PREFIX + normalizeEightByteHex(fiefId) + HEAL_ALL_COST_TAIL

    fun healAllShape(fiefId: String): String =
        HEAL_ALL_PREFIX + normalizeEightByteHex(fiefId) + HEAL_ALL_TAIL

    /** Recovered resource conversion shape used by healing when copper is insufficient. */
    fun resourceConversionShape(kind: Int, amount: Int): String =
        RESOURCE_CONVERSION_PREFIX + kind + amountHex16(amount)

    /** Recovered formation assignment order: prefix + generalId + 0000 + kind + countHex8. */
    fun formationAssignShape(generalId: String, kind: String, count: Int): String =
        FORMATION_ASSIGN_PREFIX + normalizeEightByteHex(generalId) + FORMATION_ASSIGN_MIDDLE + hexPad(kind.toInt(16), width = 2) + hexPad(count, width = 8)

    /**
     * Partially recovered refill shape. The recovered smali confirms prefix, lenByte, n, and ids;
     * one fixed segment is unresolved because its provider class is missing in the recovered smali set.
     */
    fun refillSoldierShape(generalIds: List<String>, unresolvedSegment: String = REFILL_UNRESOLVED_SEGMENT): String {
        val lenByte = hexPad(generalIds.size * 8 + 1, width = 2)
        return REFILL_PREFIX + lenByte + unresolvedSegment + generalIds.size + generalIds.joinToString(separator = "")
    }

    fun amountHex16(amount: Int): String = hexPad(amount, width = 16)

    fun hexPad(value: Int, width: Int): String {
        var hex = java.lang.Long.toHexString(value.toLong())
        while (hex.length < width) hex = "0$hex"
        return hex
    }

    private fun normalizeEightByteHex(value: String): String {
        val clean = value.removePrefix("0x").removePrefix("0X").filter { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }
        val significant = clean.trimStart('0').ifBlank { "0" }
        require(significant.length <= 16) { "id must fit in 8 bytes: $value" }
        return significant.padStart(16, '0').lowercase()
    }

    fun planAddEnergy(generals: List<GeneralShape>, threshold: Int): List<GeneralTaskAction> = buildList {
        add(GeneralTaskAction.Log("开始将领加体！"))
        add(GeneralTaskAction.FixedPayload(GENERAL_STATUS_QUERY, "查询将领体力/状态"))
        generals
            .filter { it.tili < threshold && it.isFulu && it.status == 0 }
            .forEach { general ->
                add(GeneralTaskAction.Log("${general.name}的体力为：${general.tili}，正在加体..."))
                for (drugNo in 0x0c..0x0f) {
                    add(GeneralTaskAction.FixedPayload(addEnergyShape(general.id, drugNo), "对${general.name}尝试体药${drugNo.toString(radix = 16)}"))
                }
            }
        add(GeneralTaskAction.Log("将领加体结束！"))
    }

    fun planAddLoyalty(enabled: Boolean): List<GeneralTaskAction> = if (enabled) {
        listOf(
            GeneralTaskAction.Log("开始加忠！"),
            GeneralTaskAction.FixedPayload(ADD_LOYALTY, "一键/全局加忠"),
            GeneralTaskAction.Log("将领加忠结束！"),
        )
    } else {
        emptyList()
    }

    fun planRescue(generals: List<GeneralShape>, fiefIdForGeneral: (GeneralShape) -> String?): List<GeneralTaskAction> = buildList {
        add(GeneralTaskAction.Log("开始营救将领..."))
        add(GeneralTaskAction.FixedPayload(GENERAL_STATUS_QUERY, "查询将领被俘/状态"))
        generals
            .filter { it.isFulu && it.isCapturedLike }
            .forEach { general ->
                val fiefId = fiefIdForGeneral(general) ?: return@forEach
                add(GeneralTaskAction.Log("${general.name}被敌军俘虏，正在营救..."))
                add(GeneralTaskAction.FixedPayload(rescueShape(general.id, fiefId), "营救${general.name}"))
                add(GeneralTaskAction.FixedPayload(rescueFiefShape(fiefId), "营救相关封地动作"))
            }
        add(GeneralTaskAction.Log("营救将领结束！"))
    }

    fun planHealing(items: List<HealingItemShape>, resource: GeneralResourceShape): List<GeneralTaskAction> = buildList {
        add(GeneralTaskAction.Log("开始治疗伤兵..."))
        items.forEachIndexed { index, item ->
            val percent = if (items.isEmpty()) 100 else index * 100 / items.size
            add(GeneralTaskAction.Log("治疗进度：$percent%"))
            add(GeneralTaskAction.FixedPayload(healCostShape(item.itemDecoded), "探测${item.displayName}治疗费用"))
            if (item.requiredCopper > resource.copper) {
                val convertAmount = (item.requiredCopper - resource.copper).coerceAtLeast(0)
                add(GeneralTaskAction.Log("铜钱不足${item.requiredCopper}，无法治疗，需要粮食转换！"))
                add(GeneralTaskAction.FixedPayload(resourceConversionShape(kind = 1, amount = convertAmount), "粮食转换为铜钱"))
            }
            add(GeneralTaskAction.FixedPayload(healShape(item.itemDecoded), "治疗${item.displayName}"))
        }
        add(GeneralTaskAction.Log("治疗伤兵结束！"))
    }

    fun planFormation(generals: List<GeneralShape>, kindByGeneralId: (String) -> String, countByGeneralId: (String) -> Int): List<GeneralTaskAction> = buildList {
        add(GeneralTaskAction.Log("开始配兵"))
        generals
            .filter { it.status == 0 && it.autoPeiBing }
            .forEach { general ->
                val kind = kindByGeneralId(general.id)
                val count = countByGeneralId(general.id)
                add(GeneralTaskAction.FixedPayload(formationAssignShape(general.id, kind, count), "${general.name}配兵"))
                add(GeneralTaskAction.FixedPayload(refillSoldierShape(listOf(general.id)), "${general.name}补满兵"))
            }
    }
}

data class HealPreInfoReceipt(
    val fiefId: Long,
    val soldierType: Int,
    val copperCost: Long,
    val goldCost: Long
)

data class HealActionReceipt(
    val success: Boolean,
    val status: Int,
    val message: String,
    val firstLong: Long,
    val secondLong: Long,
    val hasExtraState: Boolean,
    val trailingBytes: Int
)

data class AddEnergyReceipt(
    val success: Boolean,
    val status: Int,
    val message: String,
    val trailingBytes: Int
)

data class LoyaltyUpdate(
    val generalId: Long,
    val loyalty: Int,
    val loyaltyLimit: Int
)

data class AddLoyaltyReceipt(
    val success: Boolean,
    val result: Int,
    val mode: Int,
    val generalId: Long,
    val actualCost: Long,
    val copper: Long,
    val gold: Long,
    val resourceG: Long,
    val generals: List<LoyaltyUpdate>,
    val trailingBytes: Int,
    val message: String
)

data class GeneralShape(
    val id: String,
    val name: String,
    val tili: Int = 0,
    val isFulu: Boolean = false,
    val status: Int = 0,
    val isCapturedLike: Boolean = false,
    val autoPeiBing: Boolean = false,
    val isPeiBingFail: Boolean = false,
)

data class HealingItemShape(
    val itemDecoded: String,
    val displayName: String,
    val requiredCopper: Int,
)

data class GeneralResourceShape(
    val copper: Int,
    val food: Int,
)

sealed interface GeneralTaskAction {
    data class Log(val message: String) : GeneralTaskAction
    data class FixedPayload(val gameHex: String, val meaning: String) : GeneralTaskAction
}
