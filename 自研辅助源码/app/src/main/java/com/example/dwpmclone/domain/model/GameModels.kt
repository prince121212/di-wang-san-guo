// Static-evidence Kotlin model skeleton for a DWPM-like assistant.
// Generated for planning only; protocol-backed behavior requires runtime DEX/protocol recovery.
package com.example.dwpmclone.domain.model

data class MapCoordinate(val x: Int, val y: Int)

enum class Channel { QQ, WECHAT, UC_9GAME, DANGLE, QIHOO_360, OFFICIAL, UNKNOWN }
enum class GameVersion { TENCENT_CLASSIC, OFFICIAL_CLASSIC, TRADITIONAL, OTHER }
enum class HuangTargetType { SHAN_ZEI, HUANG_JIN }
enum class FormationFilterMode { UNIFIED, PER_FORMATION }
enum class FormationRuntimeStatus { IDLE, BUSY, MARCHING, BATTLE, RETURNING, UNKNOWN }
enum class MineType { GOLD, SILVER, BING_YU, XIAN_ZHI, XUAN_TIE, YU_LU, PASTURE_LV1, PASTURE_LV2, PASTURE_LV3, CRYSTAL, LING_CAO, BIN_TIE, JIANG_GUO }
enum class EquipmentQuality { NORMAL, GOOD, EXCELLENT, SUPERB }
enum class BuildingType { UNKNOWN, FOOD, MONEY, ACADEMY, HOUSE, INFANTRY_CAMP, ARCHER_CAMP, CAVALRY_CAMP, CHARIOT_CAMP, WAREHOUSE }
enum class DailyStep { SIGN_IN, SURPRISE_BOX, SALARY, ARENA_REWARD, COLLECT_TAX, DONATE_TECH, DONATE_COPPER, DONATE_FOOD, ADD_LOYALTY, DELETE_MAIL, ACHIEVEMENT_REWARD, TASK_REWARD, LEVEL_GIFT, CONVERT_HALF_FOOD_TO_COPPER }
enum class LicenseAction { LOGIN, BUY, TRIAL, UNBIND, QUERY }
enum class BulkToolAction { GENERAL_TOKEN_ADD_COMMAND, USE_SMALL_DRUM_BAGUA, USE_BROKEN_TREASURE_MAP, CLAIM_TASK_ACHIEVEMENTS }
enum class TreasureKind { FOOD_STORAGE, MONEY_HOUSE, ARMORY, GOLD_SILVER_MOUNTAIN, TREASURE_HOUSE, JADE_MINE }

data class ShuaHuangTargetFilter(
    val minLevel: Int? = null,
    val maxLevel: Int? = null,
    val maxDistance: Int? = null,
    val maxFoot: Int? = null,
    val maxBow: Int? = null,
    val maxCavalry: Int? = null,
    val maxChariot: Int? = null,
    val dropKeywords: Set<String> = emptySet(),
    val requiredKeywords: Set<String> = emptySet(),
    val blockedKeywords: Set<String> = emptySet()
)

data class GameAccount(
    val id: Long,
    val displayName: String?,
    val username: String,
    val encryptedPassword: String?,
    val serverName: String,
    val gameVersion: GameVersion,
    val channel: Channel,
    val session: GameSession?,
    val enabled: Boolean,
    val serverId: String? = null,
    val monarchName: String? = null,
    val nation: String? = null,
    val loginState: String = "MOCK_NOT_LOGGED_IN",
    val gameAuthSignPlaceholder: String? = null,
    val antiBanIpEnabled: Boolean = false
)

data class GameSession(
    val accountId: Long,
    val tokenCiphertext: String,
    val expiresAtMillis: Long?,
    val channelExtra: Map<String, String>,
    val sourceMode: Int
)

data class FormationRuntime(
    val id: Long,
    val name: String?,
    val generalIds: List<Long>,
    val status: FormationRuntimeStatus,
    val troopCount: Int?,
    val raw: Map<String, String> = emptyMap()
) {
    val canDispatch: Boolean
        get() = status == FormationRuntimeStatus.IDLE
}

data class GuajiConfig(
    val accountId: Long,
    val autoStart: Boolean,
    val reconnectDelaySeconds: Int = 10,
    val antiIpBanEnabled: Boolean,
    val requestDelayMillis: Int = 100,
    val sameServerMutex: Boolean = true,
    val protectBackgroundHintAcknowledged: Boolean
)

data class ShuaHuangConfig(
    val enabled: Boolean,
    val dailyLimit: Int = 500,
    val startHour: Int = 0,
    val start: MapCoordinate,
    val minCopperWan: Int = 0,
    val targetType: HuangTargetType,
    val selectedFormationIds: Set<Long>,
    val formationFilterMode: FormationFilterMode,
    val replenishTroops: Boolean = false,
    val deleteMailForSpeed: Boolean,
    val autoConvertFoodToCopper: Boolean,
    val targetFilter: ShuaHuangTargetFilter = ShuaHuangTargetFilter(),
    val perFormationTargetFilters: Map<Long, ShuaHuangTargetFilter> = emptyMap()
)

data class MineConfig(
    val enabled: Boolean,
    val start: MapCoordinate,
    val hitEmptyMine: Boolean,
    val withdrawDefense: Boolean,
    val resourcePointLimit: Int,
    val selectedMineTypes: Set<MineType>,
    val acceleratedMineTypes: Set<MineType>,
    val selectedFormationIds: Set<Long>,
    val backgroundSearch: Boolean,
    val searchIntervalMinutes: Int = 12,
    val reloginOnDisconnect: Boolean,
    val stopOnDisconnect: Boolean,
    val vibrateOnEmptyGold: Boolean,
    val vibrateOnEmptyRare: Boolean,
    val onlyEmptyMine: Boolean,
    val onlyDefendedMine: Boolean,
    val speed: String = "不加速",
    val fullLoyalty: Boolean = true,
    val targetPlayerName: String = "",
    val searchScope: String = "附近",
    val rules: List<MineRule> = emptyList()
)

data class MineRule(
    val enabled: Boolean,
    val generalIds: List<Long>,
    val mineType: MineType,
    val start: MapCoordinate,
    val scope: String = "附近",
    val onlyEmpty: Boolean = false,
    val onlyDefended: Boolean = false
)

data class DailyConfig(
    val enabledSteps: Set<DailyStep>,
    val vibrateOnAlarm: Boolean,
    val stopOnStepFailure: Boolean = false
)

data class GeneralConfig(
    val autoHeal: Boolean,
    val keepFullLoyalty: Boolean,
    val autoEnergy: Boolean,
    val minEnergy: Int = 50,
    val autoRescue: Boolean,
    val requireChineseNamePrefix: Boolean = true
)

data class FormationConfig(
    val formationId: Long,
    val generalIds: List<Long>,
    val autoAssignTroops: Boolean,
    val troopType: String,
    val troopCount: Int = 1999,
    val fillToMaxWhenAutoAssignDisabled: Boolean
)

data class InternalAffairsConfig(
    val enabled: Boolean,
    val upgradeLowestFirst: Boolean,
    val buildingPriority: List<BuildingType>,
    val buildWhenEmpty: BuildingType?,
    val upgradeTechnology: Boolean = false,
    val technologyIds: Set<Int> = setOf(5)
)

data class SixMinistriesConfig(
    val cropEnabled: Boolean,
    val crop: String,
    val highPriority: Boolean,
    val stealEnabled: Boolean,
    val courtesyEnabled: Boolean,
    val salaryRefresh: Boolean
) {
    fun preparationError(): String? {
        if (!cropEnabled && !stealEnabled && !courtesyEnabled) return "six ministries disabled"
        if (cropEnabled && crop != MinistryProtocolCrop.VERIFIED_NAME) {
            return "unverified ministry crop selected: $crop"
        }
        if (!cropEnabled && !stealEnabled) {
            return "only verified planting and read-only steal scan are currently enabled"
        }
        return null
    }
}

object MinistryProtocolCrop {
    const val VERIFIED_NAME = "金银花"
    const val VERIFIED_ID = 1
}

data class DungeonConfig(
    val enabled: Boolean,
    val dailyTimes: Int = 999,
    val boxPosition: Int,
    val chapter: Int,
    val stage: Int,
    val formationIds: List<Long>,
    val autoUnlockUntilTarget: Boolean
)

data class LosslessConfig(
    val enabled: Boolean,
    val fullTroops: Boolean,
    val dailyLimit: Int = 5,
    val rules: List<LosslessRule>
)

data class LosslessRule(
    val enabled: Boolean,
    val generalIds: List<Long>,
    val level: Int
)

data class InventoryConfig(
    val enabled: Boolean,
    val openBoxes: Boolean,
    val openSilverTickets: Boolean,
    val autoOpenItemNames: Set<String> = emptySet(),
    val discardEquipmentQualities: Set<EquipmentQuality>,
    val discardBelowLevel: Int?,
    val neverDiscardEnhancedOrEquipped: Boolean = true,
    val discardItems: Set<String>
)

/**
 * Exact item allow-list exposed by the current desktop “主号物品 → 自动开箱” picker.
 *
 * A non-empty selection is authoritative: only explicitly selected names may be used. The
 * boolean box/ticket flags remain as a compatibility fallback for old persisted configurations
 * that predate `autoOpenItemNames`.
 */
object InventoryAutoOpenPolicy {
    val DESKTOP_ITEM_NAMES: List<String> = listOf(
        "50两银票", "100两银票", "300两银票", "1000两银票",
        "惊喜宝箱", "实木宝箱", "青铜宝箱", "精铁宝箱", "粮食辎重"
    )

    fun shouldOpen(
        itemName: String,
        itemType: String,
        selectedNames: Set<String>,
        openBoxes: Boolean,
        openSilverTickets: Boolean
    ): Boolean {
        if (itemName !in DESKTOP_ITEM_NAMES) return false
        if (selectedNames.isNotEmpty()) return itemName in selectedNames
        return (itemType == "box" && openBoxes) ||
            (itemName.contains("银票") && openSilverTickets)
    }
}

data class SurrenderReleaseConfig(
    val autoSurrender: Boolean,
    val surrenderGrowthAbove: Int = 80,
    val useGoldForSurrender: Boolean,
    val autoRelease: Boolean,
    val releaseGrowthBelow: Int = 45
)

data class VipFeatureConfig(
    val enabled: Boolean,
    val showVip: Boolean,
    val autoEnergy: Boolean,
    val autoDonate: Boolean,
    val autoInternalAffairs: Boolean,
    val autoTechnology: Boolean,
    val autoRescueSoldiers: Boolean,
    val timedAddLoyalty: Boolean,
    val autoSurrender: Boolean,
    val autoRescueGeneral: Boolean
)

data class ResourcePointSendGeneralConfig(
    val enabled: Boolean,
    val target: MapCoordinate,
    val generalId: Long,
    val troopType: String,
    val formationId: Long,
    val stopAfterMinutes: Int,
    val requiresKeepFullLoyaltyOff: Boolean = true
)

data class AutoLootConfig(
    val enabled: Boolean,
    val selectedFormationIds: Set<Long>,
    val targetKeyword: String? = null,
    val requireSecondConfirmForRealRun: Boolean = true,
    val targetPlayerName: String = "",
    val targetFiefIndex: Int = 1,
    val fullTroops: Boolean = true,
    val fullLoyalty: Boolean = false,
    val rules: List<AutoLootRule> = emptyList()
) {
    fun enabledRules(): List<AutoLootRule> {
        if (rules.isNotEmpty()) return rules.filter { it.enabled }
        return if (enabled && selectedFormationIds.isNotEmpty() && targetPlayerName.isNotBlank()) {
            listOf(
                AutoLootRule(
                    enabled = true,
                    generalIds = selectedFormationIds.toList(),
                    playerName = targetPlayerName,
                    fiefIndex = targetFiefIndex
                )
            )
        } else {
            emptyList()
        }
    }

    fun preparationError(): String? {
        if (!enabled) return "auto loot disabled"
        val enabledRules = enabledRules()
        if (enabledRules.isEmpty()) return "no loot rule enabled"
        if (enabledRules.any { it.generalIds.isEmpty() }) return "loot general missing"
        if (enabledRules.any { it.playerName.isBlank() || it.fiefIndex <= 0 }) {
            return "loot target player/fief invalid"
        }
        return null
    }

    fun selectEnabledRule(cursor: Int): Pair<Int, AutoLootRule>? {
        val enabledRules = enabledRules()
        if (enabledRules.isEmpty()) return null
        val index = Math.floorMod(cursor, enabledRules.size)
        return index to enabledRules[index]
    }
}

data class AutoLootRule(
    val enabled: Boolean,
    val generalIds: List<Long>,
    val playerName: String,
    val fiefIndex: Int
)

data class AlarmWithdrawConfig(
    val enabled: Boolean,
    val keywords: Set<String> = setOf("掠夺", "夺取", "攻城", "敌军"),
    val vibrateOnAlarm: Boolean = true,
    val withdrawDefense: Boolean = false,
    val mockOnlyProtection: Boolean = true,
    val incomingEnabled: Boolean = true,
    val incomingMode: String = "声音+日志",
    val militaryEnabled: Boolean = true,
    val militaryMode: String = "出征/返回",
    val errorEnabled: Boolean = true
)

enum class AlarmNotificationKind { INCOMING, MILITARY, ERROR }

data class AlarmNotificationEvent(
    val accountId: Long,
    val kind: AlarmNotificationKind,
    val text: String,
    val vibrate: Boolean
)

/**
 * Static response-model snapshot recovered from smali field access.
 *
 * These classes intentionally model only local response structure semantics. They do not
 * provide a real parser, endpoint, session/key material, or network execution.
 */
data class ResourcePointSnapshot(
    val resourceId: String,
    val resourceKind: String,
    val level: Int,
    val coordinate: MapCoordinate,
    val occupiedOrGuardFlag: Boolean?,
    val detailText: String?,
    val totalDetailAmount: Int?,
    val detailCountA: Int?,
    val detailCountB: Int?,
    val chariotLikeCount: Int?,
    val rangedLikeCount: Int?,
    val evidenceClass: String = "Landroid/o/ۦۥۛ;"
)

data class TargetPointSnapshot(
    val targetId: String,
    val targetKind: String,
    val levelOrBossRank: Int,
    val coordinate: MapCoordinate,
    val totalDefenderAmount: Int?,
    val defenderCountA: Int?,
    val defenderCountB: Int?,
    val defenderCountC: Int?,
    val defenderCountD: Int?,
    val evidenceClass: String = "Landroid/o/ۦۤ۠;"
)

data class LootableFiefSnapshot(
    val fiefOrBaseTargetId: String,
    val sourceLordName: String?,
    val sourceIndex: Int?,
    val evidenceClass: String = "Landroid/o/ۥۡ۫ۜ;"
)

data class OwnedResourcePointCountSnapshot(
    val count: Int,
    val maxObservedByParser: Int = 5,
    val errorResponse: Boolean = false,
    val evidenceMethod: String = "Landroid/o/ۦ۠ۢ\$ۦۖۨ;->ۦۙ()I"
)

data class AlarmScanSnapshot(
    val hasAlarm: Boolean,
    val matchedKeyword: String?,
    val withdrawDefenseEnabled: Boolean,
    val evidenceMethod: String = "Landroid/o/ۦ۠ۢ\$ۦۖۨ;->ۦۤۖۨ()V"
)

data class GuideReferenceConfig(
    val generalCsvAsset: String = "dwsgmjb.TXT",
    val guideAssetsDir: String = "guidetxts",
    val enableLocalFts: Boolean,
    val openServerRemoteQueryEnabled: Boolean
)

data class LicenseConfig(
    val registrationCode: String,
    val autoLogin: Boolean,
    val agreedToTerms: Boolean,
    val lastAction: LicenseAction?
)

data class OpenServerQuery(
    val gameVersion: GameVersion,
    val serverName: String
)

data class FamousGeneral(
    val name: String,
    val breakthrough: Int?,
    val attribute: String?,
    val nation: String?
)

data class GuideArticle(
    val id: String,
    val title: String,
    val body: String,
    val sourceAsset: String
)

data class TreasureFilterConfig(
    val enabledKinds: Set<TreasureKind>,
    val nameKeyword: String?
)

data class CityDefenseSearchConfig(
    val enabled: Boolean,
    val minimumDefenseCount: Int? = null,
    val lastKnownStart: MapCoordinate? = null
)

data class BulkToolConfig(
    val enabledActions: Set<BulkToolAction>,
    val accountIds: Set<Long>
)
