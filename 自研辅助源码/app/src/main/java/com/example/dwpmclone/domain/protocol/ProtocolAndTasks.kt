// Protocol/task skeleton. RealGameProtocolClient must be implemented from recovered DEX/protocol evidence.
package com.example.dwpmclone.domain.protocol

import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.state.AutomationRuntimeStateStore
import com.example.dwpmclone.domain.cloud.CloudFirstMapCoordinator

sealed class ProtocolResult<out T> {
    data class Ok<T>(val value: T) : ProtocolResult<T>()
    data class Err(val code: String, val message: String, val retryable: Boolean = false) : ProtocolResult<Nothing>()
}

data class LoginState(val valid: Boolean, val reason: String? = null)
data class MonarchProfile(
    val level: Int,
    val nation: String?,
    val name: String,
    val roleId: Long? = null,
    val title: String? = null,
    val prestige: Long? = null,
    val populationCurrent: Long? = null,
    val populationCap: Long? = null,
    val resourcePointCurrent: Int? = null,
    val resourcePointCap: Int? = null,
    val raw: Map<String, String> = emptyMap()
)
data class MapArea(val start: MapCoordinate, val radius: Int)
data class MapSearchPolicy(val targetType: HuangTargetType? = null, val mineTypes: Set<MineType> = emptySet())
data class MapTarget(val id: Long, val coordinate: MapCoordinate, val type: String, val raw: Map<String, String> = emptyMap())
data class BattleResult(val success: Boolean, val consumedTimes: Int, val raw: Map<String, String> = emptyMap())
data class ResourceState(
    val copper: Long,
    val food: Long,
    val prestige: Long? = null,
    val copperPerHour: Int? = null,
    val foodPerHour: Int? = null,
    val populationCurrent: Long? = null,
    val populationCap: Long? = null,
    val resourcePointCurrent: Int? = null,
    val resourcePointCap: Int? = null,
    val raw: Map<String, String> = emptyMap()
)
data class MineSearchResult(
    val id: Long,
    val coordinate: MapCoordinate,
    val mineType: MineType,
    val level: Int?,
    val reserve: Long?,
    val isEmpty: Boolean,
    val defenseCount: Int?,
    val raw: Map<String, String> = emptyMap()
)
data class StepResult(val success: Boolean, val message: String, val raw: Map<String, String> = emptyMap())
data class General(
    val id: Long,
    val name: String,
    val growth: Int?,
    val loyalty: Int?,
    val energy: Int?,
    val rank: Int? = null,
    val kind: String? = null,
    val status: Int? = null,
    val placeId: Long? = null,
    val attack: Int? = null,
    val defense: Int? = null,
    val strength: Int? = null,
    val intelligence: Int? = null,
    val command: Int? = null,
    val energyLimit: Int? = null,
    val troopLimit: Int? = null,
    val exp: Long? = null,
    val expLimit: Long? = null,
    val isFulu: Boolean? = null,
    val isPeiBingFail: Boolean? = null,
    val raw: Map<String, String> = emptyMap()
)
data class InventoryItem(
    val id: Long,
    val name: String,
    val type: String,
    val quality: EquipmentQuality?,
    val level: Int?,
    val enhanced: Boolean,
    val equipped: Boolean,
    val count: Int = 1
)
data class LicenseStatus(val valid: Boolean, val expiresAtMillis: Long?, val message: String)
data class OpenServerResult(val serverName: String, val openTimeText: String?, val raw: Map<String, String> = emptyMap())
data class CitySearchResult(val name: String, val coordinate: MapCoordinate, val defenseCount: Int?, val raw: Map<String, String> = emptyMap())
data class TreasureSearchResult(val name: String, val kind: TreasureKind, val raw: Map<String, String> = emptyMap())
enum class ConvertMode { FOOD_TO_COPPER_HALF, FOOD_TO_COPPER_THRESHOLD }
enum class InventoryAction { OPEN, USE, DISCARD }

interface GameProtocolClient {
    suspend fun login(account: GameAccount): ProtocolResult<GameSession>
    suspend fun logout(session: GameSession): ProtocolResult<StepResult>
    suspend fun validateSession(session: GameSession): ProtocolResult<LoginState>
    suspend fun queryMonarch(session: GameSession): ProtocolResult<MonarchProfile>
    suspend fun queryResourceState(session: GameSession): ProtocolResult<ResourceState>
    suspend fun searchMap(session: GameSession, start: MapCoordinate, policy: MapSearchPolicy): ProtocolResult<List<MapTarget>>
    suspend fun dispatchFormation(session: GameSession, formationId: Long, target: MapTarget): ProtocolResult<BattleResult>
    suspend fun convertFoodToCopper(session: GameSession, mode: ConvertMode): ProtocolResult<ResourceState>
    suspend fun searchMines(session: GameSession, config: MineConfig): ProtocolResult<List<MineSearchResult>>
    suspend fun occupyMine(session: GameSession, mine: MineSearchResult, formationId: Long): ProtocolResult<StepResult>
    suspend fun occupyMine(
        session: GameSession,
        mine: MineSearchResult,
        generalIds: List<Long>
    ): ProtocolResult<StepResult> {
        val first = generalIds.firstOrNull()
            ?: return ProtocolResult.Err("MINE_GENERALS_EMPTY", "打矿至少需要选择1名出征将领", false)
        return occupyMine(session, mine, first)
    }
    suspend fun withdrawMineDefense(session: GameSession, mineId: Long): ProtocolResult<StepResult>
    suspend fun runDailyStep(session: GameSession, step: DailyStep): ProtocolResult<StepResult>
    suspend fun queryNationalCities(
        session: GameSession,
        kind: NationalCityKind
    ): ProtocolResult<List<NationalCity>> =
        ProtocolResult.Err(
            "NATIONAL_CITY_QUERY_NOT_IMPLEMENTED",
            "国家城池列表协议尚未实现",
            false
        )
    suspend fun queryNationalCollectStatus(
        session: GameSession,
        city: NationalCity
    ): ProtocolResult<NationalCollectStatus> =
        ProtocolResult.Err(
            "NATIONAL_COLLECT_STATUS_NOT_IMPLEMENTED",
            "国家征收状态协议尚未实现",
            false
        )
    suspend fun collectNationalCity(
        session: GameSession,
        city: NationalCity
    ): ProtocolResult<StepResult> =
        ProtocolResult.Err(
            "NATIONAL_COLLECT_NOT_IMPLEMENTED",
            "国家征收协议尚未实现",
            false
        )
    suspend fun queryOwnedFiefs(session: GameSession): ProtocolResult<List<LootTargetFief>> =
        ProtocolResult.Err(
            "OWNED_FIEF_QUERY_NOT_IMPLEMENTED",
            "自有城池列表协议尚未实现",
            false
        )
    suspend fun collectCityLord(
        session: GameSession,
        fief: LootTargetFief
    ): ProtocolResult<StepResult> =
        ProtocolResult.Err(
            "CITY_LORD_COLLECT_NOT_IMPLEMENTED",
            "城主征收协议尚未实现",
            false
        )
    suspend fun queryVisitGenerals(session: GameSession): ProtocolResult<List<GeneralVisitCandidate>> =
        ProtocolResult.Err(
            "GENERAL_VISIT_QUERY_NOT_IMPLEMENTED",
            "名将拜访列表协议尚未实现",
            false
        )
    suspend fun visitGeneral(
        session: GameSession,
        candidate: GeneralVisitCandidate
    ): ProtocolResult<StepResult> =
        ProtocolResult.Err(
            "GENERAL_VISIT_NOT_IMPLEMENTED",
            "名将拜访协议尚未实现",
            false
        )
    suspend fun queryGenerals(session: GameSession): ProtocolResult<List<General>>
    suspend fun queryFormations(session: GameSession): ProtocolResult<List<FormationRuntime>>
    suspend fun healGeneral(session: GameSession, generalId: Long): ProtocolResult<StepResult>
    suspend fun addEnergy(session: GameSession, generalId: Long): ProtocolResult<StepResult>
    suspend fun updateFormation(session: GameSession, config: FormationConfig): ProtocolResult<StepResult>
    suspend fun runInternalAffairs(session: GameSession, config: InternalAffairsConfig): ProtocolResult<StepResult>
    suspend fun runSixMinistries(
        session: GameSession,
        config: SixMinistriesConfig
    ): ProtocolResult<StepResult> =
        ProtocolResult.Err(
            "REAL_MINISTRY_NOT_IMPLEMENTED",
            "六部协议尚未由当前客户端实现",
            false
        )
    suspend fun runDungeon(session: GameSession, config: DungeonConfig): ProtocolResult<StepResult>
    suspend fun runLossless(session: GameSession, config: LosslessConfig): ProtocolResult<StepResult> =
        ProtocolResult.Err(
            code = "REAL_LOSSLESS_NOT_IMPLEMENTED",
            message = "无损真实协议尚未完整迁移，已禁止执行",
            retryable = false
        )
    suspend fun queryInventory(session: GameSession): ProtocolResult<List<InventoryItem>>
    suspend fun useOrDiscardItem(
        session: GameSession,
        itemId: Long,
        action: InventoryAction,
        count: Int = 1
    ): ProtocolResult<StepResult>
    suspend fun setVipFeature(session: GameSession, config: VipFeatureConfig): ProtocolResult<StepResult>
    suspend fun surrenderOrReleaseGenerals(session: GameSession, config: SurrenderReleaseConfig): ProtocolResult<StepResult>
    suspend fun sendGeneralToResourcePoint(session: GameSession, config: ResourcePointSendGeneralConfig): ProtocolResult<StepResult>
    suspend fun runAutoLoot(session: GameSession, config: AutoLootConfig): ProtocolResult<StepResult>
    suspend fun scanAlarmAndMaybeWithdraw(session: GameSession, config: AlarmWithdrawConfig): ProtocolResult<StepResult>
    suspend fun runBulkToolAction(session: GameSession, action: BulkToolAction): ProtocolResult<StepResult>
    suspend fun queryOpenServer(query: OpenServerQuery): ProtocolResult<OpenServerResult>
    suspend fun searchDefendedCities(session: GameSession, config: CityDefenseSearchConfig): ProtocolResult<List<CitySearchResult>>
    suspend fun searchTreasures(session: GameSession, config: TreasureFilterConfig): ProtocolResult<List<TreasureSearchResult>>
    suspend fun applyLicense(config: LicenseConfig, action: LicenseAction): ProtocolResult<LicenseStatus>
}

enum class TaskType {
    SHUA_HUANG,
    MINE_SEARCH,
    AUTO_MINING,
    DAILY,
    DAILY_DONATE,
    DAILY_SALARY,
    DAILY_NATIONAL_COLLECT,
    DAILY_CITY_LORD_COLLECT,
    DAILY_GENERAL_VISIT,
    GENERAL,
    FORMATION,
    INTERNAL,
    MINISTRY,
    DUNGEON,
    LOSSLESS,
    INVENTORY,
    VIP,
    RESOURCE_POINT_SEND_GENERAL,
    SURRENDER_RELEASE,
    AUTO_LOOT,
    ALARM_WITHDRAW,
    BULK_TOOLS,
    OPEN_SERVER_QUERY,
    CITY_SEARCH,
    TREASURE_SEARCH
}

data class TaskContext(
    val session: GameSession,
    val protocol: GameProtocolClient,
    val nowMillis: Long,
    val runtime: AutomationRuntimeStateStore = AutomationRuntimeStateStore(enforceCommandGate = false),
    val cloudMap: CloudFirstMapCoordinator = CloudFirstMapCoordinator(),
    val promptSink: ((Long, TaskType, String) -> Unit)? = null
) {
    fun prompt(type: TaskType, message: String) {
        promptSink?.invoke(session.accountId, type, message)
    }
}

sealed interface TaskDecision {
    data object Continue : TaskDecision
    data class Sleep(val millis: Long) : TaskDecision
    data class RetryAfter(val millis: Long) : TaskDecision
    data class NeedRelogin(val reason: String) : TaskDecision
    data class Stop(val reason: String) : TaskDecision
}

interface AssistantTask<Cfg> {
    val accountId: Long
    val type: TaskType
    val config: Cfg
    suspend fun prepare(ctx: TaskContext): TaskDecision
    suspend fun step(ctx: TaskContext): TaskDecision
    suspend fun recover(ctx: TaskContext, error: Throwable): TaskDecision
    suspend fun stop(ctx: TaskContext, reason: String)
}
