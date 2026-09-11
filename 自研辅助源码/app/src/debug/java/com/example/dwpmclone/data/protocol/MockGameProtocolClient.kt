package com.example.dwpmclone.data.protocol

import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.*

/** Debug/test-only fake. Production source sets cannot reference this class. */
class MockGameProtocolClient : GameProtocolClient {
    override suspend fun login(account: GameAccount) = ProtocolResult.Ok(
        GameSession(account.id, tokenCiphertext = "mock-token", expiresAtMillis = null, channelExtra = emptyMap(), sourceMode = 0)
    )
    override suspend fun logout(session: GameSession) = ProtocolResult.Ok(StepResult(true, "mock logout"))
    override suspend fun validateSession(session: GameSession) = ProtocolResult.Ok(LoginState(valid = true))
    override suspend fun queryMonarch(session: GameSession) = ProtocolResult.Ok(MonarchProfile(level = 30, nation = "mock", name = "mock-monarch"))
    override suspend fun queryResourceState(session: GameSession) = ProtocolResult.Ok(ResourceState(copper = 1_000_000, food = 1_000_000))
    override suspend fun searchMap(session: GameSession, start: MapCoordinate, policy: MapSearchPolicy) = ProtocolResult.Ok(
        listOf(
            MapTarget(
                id = 1001L,
                coordinate = start,
                type = policy.targetType?.name ?: HuangTargetType.SHAN_ZEI.name,
                raw = mapOf("level" to "1", "mock" to "true")
            )
        )
    )
    override suspend fun dispatchFormation(session: GameSession, formationId: Long, target: MapTarget) = ProtocolResult.Ok(BattleResult(success = true, consumedTimes = 1))
    override suspend fun convertFoodToCopper(session: GameSession, mode: ConvertMode) = ProtocolResult.Ok(ResourceState(copper = 1_000_000, food = 1_000_000))
    override suspend fun searchMines(session: GameSession, config: MineConfig) = ProtocolResult.Ok(emptyList<MineSearchResult>())
    override suspend fun revalidateMineTarget(
        session: GameSession,
        mine: MineSearchResult,
        config: MineConfig
    ) = if (MineTargetFilterPolicy.matches(mine, config)) {
        ProtocolResult.Ok(mine)
    } else {
        ProtocolResult.Err("MINE_TARGET_STALE", "mock mine target stale", true)
    }
    override suspend fun occupyMine(session: GameSession, mine: MineSearchResult, formationId: Long) = ProtocolResult.Ok(StepResult(true, "mock occupy"))
    override suspend fun occupyMine(session: GameSession, mine: MineSearchResult, generalIds: List<Long>) =
        if (generalIds.isEmpty()) {
            ProtocolResult.Err("MINE_GENERALS_EMPTY", "打矿至少需要选择1名出征将领", false)
        } else {
            ProtocolResult.Ok(StepResult(true, "mock occupy ${generalIds.joinToString()}"))
        }
    override suspend fun withdrawMineDefense(session: GameSession, battleId: Long) = ProtocolResult.Ok(StepResult(true, "mock withdraw"))
    override suspend fun accelerateMineMarch(
        session: GameSession,
        battleId: Long,
        remainingSeconds: Int
    ) = ProtocolResult.Ok(StepResult(true, "mock mine speed"))
    override suspend fun runDailyStep(session: GameSession, step: DailyStep): ProtocolResult<StepResult> {
        val shape = DailyProtocolShapes.shapeFor(step)
        return ProtocolResult.Ok(
            StepResult(
                success = true,
                message = "mock daily $step",
                raw = mapOf(
                    "payloads" to shape.payloads.joinToString(separator = ","),
                    "successLog" to shape.successLog,
                    "evidence" to shape.evidence
                )
            )
        )
    }
    override suspend fun queryGenerals(session: GameSession) = ProtocolResult.Ok(
        listOf(General(id = 1L, name = "赵云", growth = 90, loyalty = 100, energy = 100))
    )
    override suspend fun queryFormations(session: GameSession) = ProtocolResult.Ok(
        listOf(
            FormationRuntime(
                id = 1L,
                name = "默认编队",
                generalIds = listOf(1L),
                status = FormationRuntimeStatus.IDLE,
                troopCount = 1999,
                raw = mapOf("mock" to "true")
            )
        )
    )
    override suspend fun healGeneral(session: GameSession, generalId: Long) = ProtocolResult.Ok(StepResult(true, "mock heal"))
    override suspend fun addEnergy(session: GameSession, generalId: Long) = ProtocolResult.Ok(StepResult(true, "mock energy"))
    override suspend fun addLoyalty(session: GameSession, generalId: Long, delta: Int) =
        ProtocolResult.Ok(StepResult(true, "mock loyalty +$delta"))
    override suspend fun updateFormation(session: GameSession, config: FormationConfig) = ProtocolResult.Ok(StepResult(true, "mock formation"))
    override suspend fun runInternalAffairs(session: GameSession, config: InternalAffairsConfig) = ProtocolResult.Ok(StepResult(true, "mock internal"))
    override suspend fun queryInventory(session: GameSession) = ProtocolResult.Ok(emptyList<InventoryItem>())
    override suspend fun useOrDiscardItem(session: GameSession, itemId: Long, action: InventoryAction, count: Int) =
        ProtocolResult.Ok(StepResult(true, "mock inventory"))
    override suspend fun setVipFeature(session: GameSession, config: VipFeatureConfig) = ProtocolResult.Ok(StepResult(true, "mock vip"))
    override suspend fun surrenderOrReleaseGenerals(session: GameSession, config: SurrenderReleaseConfig) = ProtocolResult.Ok(StepResult(true, "mock surrender/release"))
    override suspend fun sendGeneralToResourcePoint(session: GameSession, config: ResourcePointSendGeneralConfig) = ProtocolResult.Ok(StepResult(true, "mock send general"))
    override suspend fun scanAlarms(session: GameSession, config: AlarmConfig) = ProtocolResult.Ok(StepResult(true, "mock alarm scan"))
    override suspend fun runBulkToolAction(session: GameSession, action: BulkToolAction) = ProtocolResult.Ok(StepResult(true, "mock bulk $action"))
    override suspend fun queryOpenServer(query: OpenServerQuery) = ProtocolResult.Ok(OpenServerResult(query.serverName, "mock open time"))
    override suspend fun searchDefendedCities(session: GameSession, config: CityDefenseSearchConfig) = ProtocolResult.Ok(emptyList<CitySearchResult>())
    override suspend fun searchTreasures(session: GameSession, config: TreasureFilterConfig) = ProtocolResult.Ok(emptyList<TreasureSearchResult>())
    override suspend fun applyLicense(config: LicenseConfig, action: LicenseAction) = ProtocolResult.Ok(LicenseStatus(valid = true, expiresAtMillis = null, message = "mock license"))
}
