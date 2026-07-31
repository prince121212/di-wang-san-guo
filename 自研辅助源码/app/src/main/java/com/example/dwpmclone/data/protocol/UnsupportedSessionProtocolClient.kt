package com.example.dwpmclone.data.protocol

import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.*

/** Production fallback that rejects sessions not created by the real login flow. */
class UnsupportedSessionProtocolClient : GameProtocolClient {
    private fun <T> rejected(): ProtocolResult<T> = ProtocolResult.Err(
        code = "NON_REAL_SESSION_REJECTED",
        message = "生产运行只接受手机本地真实登录 Session",
        retryable = false
    )

    override suspend fun login(account: GameAccount): ProtocolResult<GameSession> = rejected()
    override suspend fun logout(session: GameSession): ProtocolResult<StepResult> = rejected()
    override suspend fun validateSession(session: GameSession): ProtocolResult<LoginState> = rejected()
    override suspend fun queryMonarch(session: GameSession): ProtocolResult<MonarchProfile> = rejected()
    override suspend fun queryResourceState(session: GameSession): ProtocolResult<ResourceState> = rejected()
    override suspend fun searchMap(session: GameSession, start: MapCoordinate, policy: MapSearchPolicy): ProtocolResult<List<MapTarget>> = rejected()
    override suspend fun dispatchFormation(session: GameSession, formationId: Long, target: MapTarget): ProtocolResult<BattleResult> = rejected()
    override suspend fun convertFoodToCopper(session: GameSession, mode: ConvertMode): ProtocolResult<ResourceState> = rejected()
    override suspend fun searchMines(session: GameSession, config: MineConfig): ProtocolResult<List<MineSearchResult>> = rejected()
    override suspend fun occupyMine(session: GameSession, mine: MineSearchResult, formationId: Long): ProtocolResult<StepResult> = rejected()
    override suspend fun withdrawMineDefense(session: GameSession, battleId: Long): ProtocolResult<StepResult> = rejected()
    override suspend fun runDailyStep(session: GameSession, step: DailyStep): ProtocolResult<StepResult> = rejected()
    override suspend fun queryGenerals(session: GameSession): ProtocolResult<List<General>> = rejected()
    override suspend fun queryFormations(session: GameSession): ProtocolResult<List<FormationRuntime>> = rejected()
    override suspend fun healGeneral(session: GameSession, generalId: Long): ProtocolResult<StepResult> = rejected()
    override suspend fun addEnergy(session: GameSession, generalId: Long): ProtocolResult<StepResult> = rejected()
    override suspend fun updateFormation(session: GameSession, config: FormationConfig): ProtocolResult<StepResult> = rejected()
    override suspend fun runInternalAffairs(session: GameSession, config: InternalAffairsConfig): ProtocolResult<StepResult> = rejected()
    override suspend fun runDungeon(session: GameSession, config: DungeonConfig): ProtocolResult<StepResult> = rejected()
    override suspend fun queryInventory(session: GameSession): ProtocolResult<List<InventoryItem>> = rejected()
    override suspend fun useOrDiscardItem(session: GameSession, itemId: Long, action: InventoryAction, count: Int): ProtocolResult<StepResult> = rejected()
    override suspend fun setVipFeature(session: GameSession, config: VipFeatureConfig): ProtocolResult<StepResult> = rejected()
    override suspend fun surrenderOrReleaseGenerals(session: GameSession, config: SurrenderReleaseConfig): ProtocolResult<StepResult> = rejected()
    override suspend fun sendGeneralToResourcePoint(session: GameSession, config: ResourcePointSendGeneralConfig): ProtocolResult<StepResult> = rejected()
    override suspend fun runAutoLoot(session: GameSession, config: AutoLootConfig): ProtocolResult<StepResult> = rejected()
    override suspend fun scanAlarms(session: GameSession, config: AlarmConfig): ProtocolResult<StepResult> = rejected()
    override suspend fun runBulkToolAction(session: GameSession, action: BulkToolAction): ProtocolResult<StepResult> = rejected()
    override suspend fun queryOpenServer(query: OpenServerQuery): ProtocolResult<OpenServerResult> = rejected()
    override suspend fun searchDefendedCities(session: GameSession, config: CityDefenseSearchConfig): ProtocolResult<List<CitySearchResult>> = rejected()
    override suspend fun searchTreasures(session: GameSession, config: TreasureFilterConfig): ProtocolResult<List<TreasureSearchResult>> = rejected()
    override suspend fun applyLicense(config: LicenseConfig, action: LicenseAction): ProtocolResult<LicenseStatus> = rejected()
}
