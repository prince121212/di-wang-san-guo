package com.example.dwpmclone.domain.protocol

import java.nio.ByteBuffer

/**
 * Local-only protocol shape helpers recovered from the "inventory / treasure vault" path.
 *
 * Request bodies below are verified against the desktop client's captured protocol.
 */
object InventoryProtocolShapes {
    const val INVENTORY_QUERY: String = "00000000000000000001110400"
    const val OPEN_ITEM_PREFIX: String = "000000000000000000043144"
    const val DISCARD_ITEM_PREFIX: String = "00000000000000000015110300000000000000"
    const val DISCARD_EQUIPMENT_PREFIX: String = "00000000000000000015110301"
    const val DISCARD_EQUIPMENT_TAIL: String = "ffffffffffffffff"
    const val BANDIT_HEADSCARF_TO_BRAVE_TOKEN: String = "000000000000000000091134000000000000791d00"

    const val TOKEN_KEEP_COUNT: Int = 999
    const val MAX_DISCARD_BATCH_LOOPS: Int = 30
    const val BANDIT_HEADSCARF_EXCHANGE_COST: Int = 1000
    const val BANDIT_HEADSCARF_MAX_EXCHANGES: Int = 3

    val openBoxItems: List<InventoryBatchRule> = listOf(
        InventoryBatchRule("精铁宝箱", 99, requiresPairedKey = "精铁钥匙"),
        InventoryBatchRule("青铜宝箱", 99, requiresPairedKey = "青铜钥匙"),
        InventoryBatchRule("实木宝箱", 99),
        InventoryBatchRule("惊喜宝箱", 9),
        InventoryBatchRule("资源辎重", 99),
        InventoryBatchRule("粮食辎重", 99),
        InventoryBatchRule("铜钱辎重", 99),
        InventoryBatchRule("镔铁小包", 9),
        InventoryBatchRule("水晶小包", 9),
        InventoryBatchRule("玄铁小包", 9),
        InventoryBatchRule("冰玉小包", 9),
        InventoryBatchRule("浆果小包", 9),
        InventoryBatchRule("灵草小包", 9),
        InventoryBatchRule("玉露小包", 9),
        InventoryBatchRule("仙芝小包", 9),
    )

    val openSilverTicketItems: List<InventoryBatchRule> = listOf(
        InventoryBatchRule("50两银票", 9),
    )

    val discardItemRules: List<InventoryBatchRule> = listOf(
        InventoryBatchRule("青铜宝箱", 99, configKey = "baokuQingtongbox"),
        InventoryBatchRule("精铁宝箱", 99, configKey = "baokuJingtiebox"),
        InventoryBatchRule("山贼头巾", 999, configKey = "baokutoujin"),
        InventoryBatchRule("火药桶", 99, configKey = "baokuHuoYaoTong"),
        InventoryBatchRule("传音符", 99, configKey = "baokuChuanYinfu"),
        InventoryBatchRule("青铜钥匙", 99, configKey = "baokuQingtongKey"),
        InventoryBatchRule("令牌", 999, configKey = "baokuLingpai", keepCount = TOKEN_KEEP_COUNT),
        InventoryBatchRule("屯田令", 99, configKey = "baokuTunTianLing"),
        InventoryBatchRule("通商令", 99, configKey = "baokuTongShangLing"),
        InventoryBatchRule("镔铁", 99, configKey = "baokuBintie"),
        InventoryBatchRule("浆果", 99, configKey = "baokuJiangguo"),
        InventoryBatchRule("水晶", 99, configKey = "baokuShuiJin"),
        InventoryBatchRule("灵草", 99, configKey = "baokuLincao"),
    )

    fun buildUsePayload(itemId: Long, count: Int): ByteArray {
        require(itemId in 0..0xffff) { "itemId must fit unsigned short" }
        require(count in 1..0xffff) { "count must fit unsigned short and be positive" }
        return ByteBuffer.allocate(4)
            .putShort(itemId.toShort())
            .putShort(count.toShort())
            .array()
    }

    fun buildDiscardPayload(kind: Int, objectId: Long, count: Int): ByteArray {
        require(kind in 0..1) { "kind must be 0 (item) or 1 (equipment)" }
        require(objectId >= 0) { "objectId must be non-negative" }
        require(count > 0) { "count must be positive" }
        return ByteBuffer.allocate(21)
            .put(kind.toByte())
            .putLong(objectId)
            .putInt(count)
            .putLong(-1L)
            .array()
    }

    /**
     * Captured 0x8103 and 0xa144 both start with signed status byte followed by
     * DataInput UTF (u16 byte length + UTF-8 message). Inventory data may follow.
     */
    fun parseActionResponse(payload: ByteArray): InventoryActionReceipt {
        require(payload.size >= 3) { "inventory action response too short" }
        val status = payload[0].toInt()
        val messageLength = ((payload[1].toInt() and 0xff) shl 8) or
            (payload[2].toInt() and 0xff)
        require(3 + messageLength <= payload.size) {
            "inventory action message exceeds payload: length=$messageLength bytes=${payload.size}"
        }
        val message = payload.copyOfRange(3, 3 + messageLength).toString(Charsets.UTF_8)
        return InventoryActionReceipt(
            success = status == 0,
            status = status,
            message = message,
            trailingBytes = payload.size - 3 - messageLength
        )
    }

    fun openItemShape(itemName: String, count: Int): InventoryRequestShape = InventoryRequestShape(
        action = "open-item",
        fixedPrefix = OPEN_ITEM_PREFIX,
        logicalName = itemName,
        count = count,
        unresolvedEncoding = "itemName/count are further encoded by Landroid/o/ۦۡۦ;->ۦۖ۠ and wrapper Lcn/uc/gamesdk/c/c/b",
    )

    fun discardItemShape(itemName: String, count: Int): InventoryRequestShape = InventoryRequestShape(
        action = "discard-item",
        fixedPrefix = DISCARD_ITEM_PREFIX,
        logicalName = itemName,
        count = count,
        unresolvedEncoding = "itemName/count are further encoded by Landroid/o/ۦۡۦ;->ۦۖۡ and wrapper Lcn/uc/gamesdk/c/c/b",
    )

    fun discardEquipmentShape(equipmentId: String): EquipmentDiscardShape = EquipmentDiscardShape(
        fixedPrefix = DISCARD_EQUIPMENT_PREFIX,
        equipmentId = equipmentId,
        fixedTail = DISCARD_EQUIPMENT_TAIL,
        unresolvedEncoding = "equipment id middle fields are still unresolved in Landroid/o/ۦۥۖ;->ۦۜۧ",
    )

    /** Send the remainder first, then full batches; never emit a zero-count request. */
    fun planOpenBatches(itemName: String, total: Int, batchSize: Int): List<InventoryVaultAction> {
        require(total >= 0) { "total must be non-negative" }
        require(batchSize > 0) { "batchSize must be positive" }
        val remainder = total % batchSize
        val loops = total / batchSize
        return buildList {
            if (remainder > 0) {
                add(InventoryVaultAction.OpenItem(openItemShape(itemName, remainder)))
                add(InventoryVaultAction.Log("开启$itemName$remainder"))
            }
            repeat(loops) {
                add(InventoryVaultAction.OpenItem(openItemShape(itemName, batchSize)))
                add(InventoryVaultAction.Log("开启$itemName$batchSize"))
            }
        }
    }

    /** Send the remainder first, then at most 30 full batches; never discard zero items. */
    fun planDiscardBatches(itemName: String, total: Int, batchSize: Int): List<InventoryVaultAction> {
        require(total >= 0) { "total must be non-negative" }
        require(batchSize > 0) { "batchSize must be positive" }
        val remainder = total % batchSize
        val loops = minOf(total / batchSize, MAX_DISCARD_BATCH_LOOPS)
        return buildList {
            if (remainder > 0) {
                add(InventoryVaultAction.DiscardItem(discardItemShape(itemName, remainder)))
                add(InventoryVaultAction.Log("丢弃$itemName$remainder"))
            }
            repeat(loops) {
                add(InventoryVaultAction.DiscardItem(discardItemShape(itemName, batchSize)))
                add(InventoryVaultAction.Log("丢弃$itemName$batchSize"))
            }
        }
    }

    fun planTokenDiscard(totalTokens: Int): List<InventoryVaultAction> {
        val discardCount = (totalTokens - TOKEN_KEEP_COUNT).coerceAtLeast(0)
        return if (discardCount == 0) {
            listOf(InventoryVaultAction.Log("自动保留${TOKEN_KEEP_COUNT}个令牌"))
        } else {
            listOf(InventoryVaultAction.Log("自动保留${TOKEN_KEEP_COUNT}个令牌")) +
                planDiscardBatches("令牌", discardCount, 999)
        }
    }

    fun planBanditHeadscarf(
        totalHeadscarves: Int,
        alreadyExchangedCount: Int,
        discardEnabled: Boolean,
    ): List<InventoryVaultAction> {
        require(totalHeadscarves >= 0) { "totalHeadscarves must be non-negative" }
        require(alreadyExchangedCount >= 0) { "alreadyExchangedCount must be non-negative" }
        val remainingExchangeQuota = (BANDIT_HEADSCARF_MAX_EXCHANGES - alreadyExchangedCount).coerceAtLeast(0)
        val possibleExchanges = totalHeadscarves / BANDIT_HEADSCARF_EXCHANGE_COST
        val exchanges = minOf(remainingExchangeQuota, possibleExchanges)
        val afterExchange = totalHeadscarves - exchanges * BANDIT_HEADSCARF_EXCHANGE_COST
        return buildList {
            repeat(exchanges) {
                add(InventoryVaultAction.FixedPayload(BANDIT_HEADSCARF_TO_BRAVE_TOKEN, "领取勇士令+1"))
                add(InventoryVaultAction.Log("领取勇士令+1"))
            }
            if (discardEnabled && afterExchange > 0) {
                addAll(planDiscardBatches("山贼头巾", afterExchange, 999))
            }
        }
    }

    fun shouldDiscardEquipment(
        equipment: EquipmentShape,
        selectedQualities: Set<String>,
        lowLevelEnabled: Boolean,
        lowLevelThreshold: Int,
    ): Boolean {
        if (equipment.kf != 0) return false
        val qualityMatch = equipment.quality in selectedQualities
        val lowLevelMatch = lowLevelEnabled && equipment.level < lowLevelThreshold
        return qualityMatch || lowLevelMatch
    }
}

data class InventoryActionReceipt(
    val success: Boolean,
    val status: Int,
    val message: String,
    val trailingBytes: Int
)

data class InventoryBatchRule(
    val itemName: String,
    val batchSize: Int,
    val configKey: String? = null,
    val requiresPairedKey: String? = null,
    val keepCount: Int = 0,
)

data class InventoryRequestShape(
    val action: String,
    val fixedPrefix: String,
    val logicalName: String,
    val count: Int,
    val unresolvedEncoding: String,
)

data class EquipmentDiscardShape(
    val fixedPrefix: String,
    val equipmentId: String,
    val fixedTail: String,
    val unresolvedEncoding: String,
)

data class EquipmentShape(
    val id: String,
    val displayName: String,
    val quality: String,
    val level: Int,
    val kf: Int,
)

sealed interface InventoryVaultAction {
    data class Log(val message: String) : InventoryVaultAction
    data class OpenItem(val request: InventoryRequestShape) : InventoryVaultAction
    data class DiscardItem(val request: InventoryRequestShape) : InventoryVaultAction
    data class DiscardEquipment(val request: EquipmentDiscardShape) : InventoryVaultAction
    data class FixedPayload(val gameHex: String, val meaning: String) : InventoryVaultAction
}
