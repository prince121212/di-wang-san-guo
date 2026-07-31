package com.example.dwpmclone.domain.protocol

import org.json.JSONObject

/**
 * Cross-platform behavior rules loaded from shared_core/assistant_behavior_contract.json.
 *
 * Python and Android keep their platform-specific transport/lifecycle adapters, while
 * opcodes and server-result semantics come from this single contract.
 */
data class AssistantBehaviorContract(
    val timezoneId: String,
    val dailyFeaturesAreIndependent: Boolean,
    val oneDailyFailureMustNotBlockSiblings: Boolean,
    val scheduler: SchedulerBehaviorContract,
    val accountLifecycle: AccountLifecycleBehaviorContract,
    val dailySchedule: DailyScheduleBehaviorContract,
    val signIn: SignInBehaviorContract,
    val dailyActions: DailyActionsBehaviorContract,
    val expedition: ExpeditionBehaviorContract,
    val formation: FormationBehaviorContract,
    val mapSearch: MapSearchBehaviorContract,
    val brushYellow: BrushYellowBehaviorContract,
    val mine: MineBehaviorContract,
    val raid: RaidBehaviorContract,
    val lossless: LosslessBehaviorContract,
    val dungeon: DungeonBehaviorContract,
    val militarySnapshot: MilitarySnapshotBehaviorContract
) {
    companion object {
        fun defaults(): AssistantBehaviorContract = AssistantBehaviorContract(
            timezoneId = "Asia/Shanghai",
            dailyFeaturesAreIndependent = true,
            oneDailyFailureMustNotBlockSiblings = true,
            scheduler = SchedulerBehaviorContract.defaults(),
            accountLifecycle = AccountLifecycleBehaviorContract.defaults(),
            dailySchedule = DailyScheduleBehaviorContract.defaults(),
            signIn = SignInBehaviorContract.defaults(),
            dailyActions = DailyActionsBehaviorContract.defaults(),
            expedition = ExpeditionBehaviorContract.defaults(),
            formation = FormationBehaviorContract.defaults(),
            mapSearch = MapSearchBehaviorContract.defaults(),
            brushYellow = BrushYellowBehaviorContract.defaults(),
            mine = MineBehaviorContract.defaults(),
            raid = RaidBehaviorContract.defaults(),
            lossless = LosslessBehaviorContract.defaults(),
            dungeon = DungeonBehaviorContract.defaults(),
            militarySnapshot = MilitarySnapshotBehaviorContract.defaults()
        )

        fun fromJson(raw: String): AssistantBehaviorContract {
            val root = JSONObject(raw)
            require(root.optInt("schemaVersion") == 1) {
                "unsupported assistant behavior contract schemaVersion"
            }
            val semantics = root.getJSONObject("resultSemantics")
            val scheduler = root.getJSONObject("scheduler")
            val residentPriority = scheduler.getJSONObject("residentPriority")
            val accountLifecycle = root.getJSONObject("accountLifecycle")
            val accountStatusText = accountLifecycle.getJSONObject("statusText")
            val daily = root.getJSONObject("daily")
            val schedule = daily.getJSONObject("schedule")
            val signIn = daily.getJSONObject("signIn")
            val diamondBox = signIn.getJSONObject("diamondBox")
            val actions = daily.getJSONObject("actions")
            val arenaCoins = actions.getJSONObject("arenaCoins")
            val donate = actions.getJSONObject("donate")
            val salary = actions.getJSONObject("salary")
            val nationalCollect = actions.getJSONObject("nationalCollect")
            val cityLordCollect = actions.getJSONObject("cityLordCollect")
            val generalVisit = actions.getJSONObject("generalVisit")
            val expedition = root.getJSONObject("expedition")
            val formation = root.getJSONObject("formation")
            val mapSearch = root.getJSONObject("mapSearch")
            val mapWorld = mapSearch.getJSONObject("world")
            val brushYellow = root.getJSONObject("brushYellow")
            val brushSchedule = brushYellow.getJSONObject("schedule")
            val mine = root.getJSONObject("mine")
            val minePreview = mine.getJSONObject("preview")
            val mineSchedule = mine.getJSONObject("schedule")
            val mineSpeed = mine.getJSONObject("speed")
            val mineSpeedItems = mineSpeed.getJSONObject("itemSeconds")
            val withdraw = mine.getJSONObject("withdraw")
            val raid = root.getJSONObject("raid")
            val lossless = root.getJSONObject("lossless")
            val losslessModes = lossless.getJSONObject("modes")
            val losslessGuard = lossless.getJSONObject("level10Guard")
            val losslessSchedule = lossless.getJSONObject("schedule")
            val dungeon = root.getJSONObject("dungeon")
            val dungeonStages = dungeon.getJSONObject("staticStageCodes")
            val dungeonSchedule = dungeon.getJSONObject("schedule")
            val militarySnapshot = root.getJSONObject("militarySnapshot")
            return AssistantBehaviorContract(
                timezoneId = root.getString("timezone"),
                dailyFeaturesAreIndependent = semantics.getBoolean("dailyFeaturesAreIndependent"),
                oneDailyFailureMustNotBlockSiblings = semantics.getBoolean("oneDailyFailureMustNotBlockSiblings"),
                scheduler = SchedulerBehaviorContract(
                    residentPriority = residentPriority.keys().asSequence().associateWith(
                        residentPriority::getInt
                    ),
                    sameGeneralMutualExclusionRequired =
                        scheduler.getBoolean("sameGeneralMutualExclusionRequired"),
                    onlyRunnableResidentBlocksLowerPriority =
                        scheduler.getBoolean("onlyRunnableResidentBlocksLowerPriority"),
                    formationPrerequisiteRunsFirst =
                        scheduler.getBoolean("formationPrerequisiteRunsFirst"),
                    dailyFeaturesRunBeforeResidents =
                        scheduler.getBoolean("dailyFeaturesRunBeforeResidents"),
                    militaryLaneRunsBeforeIdleLane =
                        scheduler.getBoolean("militaryLaneRunsBeforeIdleLane"),
                    expeditionPreparationIsTaskScoped =
                        scheduler.getBoolean("expeditionPreparationIsTaskScoped"),
                    idleLaneMustYieldToDueMilitaryWork =
                        scheduler.getBoolean("idleLaneMustYieldToDueMilitaryWork"),
                    observationRefreshMayRunBetweenLanes =
                        scheduler.getBoolean("observationRefreshMayRunBetweenLanes"),
                    waitStatePersistsAcrossProcess =
                        scheduler.getBoolean("waitStatePersistsAcrossProcess"),
                    dayBoundaryUsesContractTimezone =
                        scheduler.getBoolean("dayBoundaryUsesContractTimezone"),
                    ministryPollMillis = scheduler.getLong("ministryPollMillis")
                ).also { it.validate() },
                accountLifecycle = AccountLifecycleBehaviorContract(
                    startedRequiresExecutionOwner = accountLifecycle.getBoolean("startedRequiresExecutionOwner"),
                    startRunsFreshLogin = accountLifecycle.getBoolean("startRunsFreshLogin"),
                    heartbeatIntervalMillis = accountLifecycle.getLong("heartbeatIntervalMillis"),
                    statusText = accountStatusText.keys().asSequence().associateWith(accountStatusText::getString)
                ).also { it.validate() },
                dailySchedule = DailyScheduleBehaviorContract(
                    failedFeatureRetryMillis = schedule.getLong("failedFeatureRetryMillis"),
                    completedFeatureSleep = schedule.getString("completedFeatureSleep")
                ).also {
                    require(it.failedFeatureRetryMillis > 0L) {
                        "daily failedFeatureRetryMillis must be positive"
                    }
                    require(it.completedFeatureSleep == "nextChinaDay") {
                        "unsupported daily completedFeatureSleep"
                    }
                },
                signIn = SignInBehaviorContract(
                    requestOpcode = signIn.getString("requestOpcode").parseOpcode(),
                    activityResponseOpcode = signIn.getString("activityResponseOpcode").parseOpcode(),
                    legacyResponseOpcode = signIn.getString("legacyResponseOpcode").parseOpcode(),
                    successMarkers = signIn.getJSONArray("successMarkers").stringList(),
                    duplicateMarkers = signIn.getJSONArray("duplicateMarkers").stringList(),
                    duplicateMessage = signIn.getString("duplicateMessage"),
                    confirmedMessage = signIn.getString("confirmedMessage"),
                    diamondBox = DiamondBoxBehaviorContract(
                        requestOpcode = diamondBox.getString("requestOpcode").parseOpcode(),
                        responseOpcode = diamondBox.getString("responseOpcode").parseOpcode(),
                        payload = diamondBox.getString("payloadHex").hexBytes(),
                        expiredMarkers = diamondBox.getJSONArray("expiredMarkers").stringList(),
                        duplicateMarkers = diamondBox.getJSONArray("duplicateMarkers").stringList(),
                        alreadyClaimedMessage = diamondBox.getString("alreadyClaimedMessage")
                    )
                ),
                dailyActions = DailyActionsBehaviorContract(
                    arenaCoins = ArenaCoinsBehaviorContract(
                        readRequestOpcode = arenaCoins.getString("readRequestOpcode").parseOpcode(),
                        claimRequestOpcode = arenaCoins.getString("claimRequestOpcode").parseOpcode(),
                        claimResponseOpcode = arenaCoins.getString("claimResponseOpcode").parseOpcode()
                    ),
                    donate = DonationBehaviorContract(
                        resourceRequestOpcode = donate.getString("resourceRequestOpcode").parseOpcode(),
                        resourceResponseOpcode = donate.getString("resourceResponseOpcode").parseOpcode(),
                        technologyRequestOpcode = donate.getString("technologyRequestOpcode").parseOpcode(),
                        technologyResponseOpcode = donate.getString("technologyResponseOpcode").parseOpcode(),
                        copperPerLevel = donate.getInt("copperPerLevel"),
                        foodPerLevel = donate.getInt("foodPerLevel"),
                        technologyPerLevel = donate.getInt("technologyPerLevel")
                    ),
                    salary = SalaryBehaviorContract(
                        requestOpcode = salary.getString("requestOpcode").parseOpcode(),
                        responseOpcode = salary.getString("responseOpcode").parseOpcode(),
                        payload = salary.getString("payloadHex").hexBytes(),
                        alreadyClaimedMarkers = salary.getJSONArray("alreadyClaimedMarkers").stringList(),
                        noOfficeMarkers = salary.getJSONArray("noOfficeMarkers").stringList(),
                        successMarkers = salary.getJSONArray("successMarkers").stringList()
                    ),
                    nationalCollect = NationalCollectBehaviorContract(
                        cityListRequestOpcode = nationalCollect.getString("cityListRequestOpcode").parseOpcode(),
                        cityListResponseOpcode = nationalCollect.getString("cityListResponseOpcode").parseOpcode(),
                        statusRequestOpcode = nationalCollect.getString("statusRequestOpcode").parseOpcode(),
                        statusResponseOpcode = nationalCollect.getString("statusResponseOpcode").parseOpcode(),
                        collectRequestOpcode = nationalCollect.getString("collectRequestOpcode").parseOpcode(),
                        collectResponseOpcode = nationalCollect.getString("collectResponseOpcode").parseOpcode(),
                        includedListCategories = nationalCollect.getJSONArray("includedListCategories").intList(),
                        responseHeaderBytes = nationalCollect.getInt("responseHeaderBytes"),
                        recordTailBytes = nationalCollect.getInt("recordTailBytes"),
                        pageSize = nationalCollect.getInt("pageSize"),
                        maxAttempts = nationalCollect.getInt("maxAttempts")
                    ),
                    cityLordCollect = CityLordCollectBehaviorContract(
                        ownedCityRequestOpcode = cityLordCollect.getString("ownedCityRequestOpcode").parseOpcode(),
                        ownedCityResponseOpcode = cityLordCollect.getString("ownedCityResponseOpcode").parseOpcode(),
                        ownedCityPayloadSuffix = cityLordCollect.getString("ownedCityPayloadSuffixHex").hexBytes(),
                        collectRequestOpcode = cityLordCollect.getString("collectRequestOpcode").parseOpcode(),
                        collectResponseOpcode = cityLordCollect.getString("collectResponseOpcode").parseOpcode(),
                        ineligibleMarkers = cityLordCollect.getJSONArray("ineligibleMarkers").stringList(),
                        alreadyCollectedMarkers = cityLordCollect.getJSONArray("alreadyCollectedMarkers").stringList()
                    ),
                    generalVisit = GeneralVisitBehaviorContract(
                        listRequestOpcode = generalVisit.getString("listRequestOpcode").parseOpcode(),
                        listResponseOpcode = generalVisit.getString("listResponseOpcode").parseOpcode(),
                        visitRequestOpcode = generalVisit.getString("visitRequestOpcode").parseOpcode(),
                        visitResponseOpcode = generalVisit.getString("visitResponseOpcode").parseOpcode(),
                        pageSize = generalVisit.getInt("pageSize"),
                        maxSelected = generalVisit.getInt("maxSelected"),
                        alreadyVisitedStatus = generalVisit.getInt("alreadyVisitedStatus"),
                        alreadyVisitedMarkers = generalVisit.getJSONArray("alreadyVisitedMarkers").stringList(),
                        invitationResolvedMarkers = generalVisit.getJSONArray("invitationResolvedMarkers").stringList()
                    )
                ).also { it.validate() },
                expedition = ExpeditionBehaviorContract(
                    prepareOpcode = expedition.getString("prepareOpcode").parseOpcode(),
                    prepareResponseOpcode = expedition.getString("prepareResponseOpcode").parseOpcode(),
                    dispatchOpcode = expedition.getString("dispatchOpcode").parseOpcode(),
                    dispatchResponseOpcode = expedition.getString("dispatchResponseOpcode").parseOpcode(),
                    serverConfirmedSuccessRequired = expedition.getBoolean("serverConfirmedSuccessRequired"),
                    dispatchSuccessRequiresPositiveBattleId =
                        expedition.getBoolean("dispatchSuccessRequiresPositiveBattleId"),
                    softRejectPayload = expedition.getString("softRejectPayloadHex").hexBytes()
                ).also { it.validate() },
                formation = FormationBehaviorContract(
                    assignRequestOpcode = formation.getString("assignRequestOpcode").parseOpcode(),
                    assignResponseOpcode = formation.getString("assignResponseOpcode").parseOpcode(),
                    refillRequestOpcode = formation.getString("refillRequestOpcode").parseOpcode(),
                    refillResponseOpcode = formation.getString("refillResponseOpcode").parseOpcode(),
                    idleGeneralStatus = formation.getInt("idleGeneralStatus"),
                    clampCountToTroopLimit = formation.getBoolean("clampCountToTroopLimit"),
                    precheckIdleSoldierInventory = formation.getBoolean("precheckIdleSoldierInventory"),
                    exactAssignedTypeAndCountRequired =
                        formation.getBoolean("exactAssignedTypeAndCountRequired"),
                    clearOtherGeneralsSkipsBusy = formation.getBoolean("clearOtherGeneralsSkipsBusy"),
                    assignmentDoesNotImplicitlyRefill =
                        formation.getBoolean("assignmentDoesNotImplicitlyRefill"),
                    completedSleepMillis = formation.getLong("completedSleepMillis")
                ).also { it.validate() },
                mapSearch = MapSearchBehaviorContract(
                    banditRequestOpcode = mapSearch.getString("banditRequestOpcode").parseOpcode(),
                    banditResponseOpcode = mapSearch.getString("banditResponseOpcode").parseOpcode(),
                    realEnemyUnitCompositionRequired =
                        mapSearch.getBoolean("realEnemyUnitCompositionRequired"),
                    world = MapWorldBehaviorContract(
                        xMin = mapWorld.getInt("xMin"),
                        xMax = mapWorld.getInt("xMax"),
                        yMin = mapWorld.getInt("yMin"),
                        yMax = mapWorld.getInt("yMax"),
                        step = mapWorld.getInt("step")
                    ),
                    nearbyRequestLimit = mapSearch.getInt("nearbyRequestLimit"),
                    fullRequestLimit = mapSearch.getInt("fullRequestLimit"),
                    preparationBatchSize = mapSearch.getInt("preparationBatchSize"),
                    idleScanBatchSize = mapSearch.getInt("idleScanBatchSize"),
                    scanCoordinateCacheTtlMillis = mapSearch.getLong("scanCoordinateCacheTtlMillis"),
                    targetCacheTtlMillis = mapSearch.getLong("targetCacheTtlMillis"),
                    filters = mapSearch.getJSONArray("filters").stringList()
                ).also { it.validate() },
                brushYellow = BrushYellowBehaviorContract(
                    minimumRoleLevel = brushYellow.getInt("minimumRoleLevel"),
                    maximumGeneralsPerFormation = brushYellow.getInt("maximumGeneralsPerFormation"),
                    actionType = brushYellow.getInt("actionType"),
                    exactSelectedLevelsRequired = brushYellow.getBoolean("exactSelectedLevelsRequired"),
                    schedule = BrushYellowScheduleBehaviorContract(
                        transientRetryMillis = brushSchedule.getLong("transientRetryMillis"),
                        targetUnavailableRetryMillis = brushSchedule.getLong("targetUnavailableRetryMillis"),
                        busyGeneralPollMillis = brushSchedule.getLong("busyGeneralPollMillis"),
                        postDispatchPollMillis = brushSchedule.getLong("postDispatchPollMillis"),
                        postReturnMaintenanceDelayMillis =
                            brushSchedule.getLong("postReturnMaintenanceDelayMillis"),
                        formationShortageRetryMillis =
                            brushSchedule.getLong("formationShortageRetryMillis"),
                        mapPreparationIdlePauseMillis =
                            brushSchedule.getLong("mapPreparationIdlePauseMillis"),
                        settlementFullRefreshMillis =
                            brushSchedule.getLong("settlementFullRefreshMillis"),
                        settlementRecheckGraceMillis =
                            brushSchedule.getLong("settlementRecheckGraceMillis")
                    )
                ).also { it.validate() },
                mine = MineBehaviorContract(
                    searchRequestOpcode = mine.getString("searchRequestOpcode").parseOpcode(),
                    searchResponseOpcode = mine.getString("searchResponseOpcode").parseOpcode(),
                    actionType = mine.getInt("actionType"),
                    maximumGeneralsPerFormation = mine.getInt("maximumGeneralsPerFormation"),
                    allowedSearchScopes = mine.getJSONArray("allowedSearchScopes").stringList(),
                    defaultSearchScope = mine.getString("defaultSearchScope"),
                    allowedMaxMarchMinutes = mine.getJSONArray("allowedMaxMarchMinutes").intList(),
                    defaultMaxMarchMinutes = mine.getInt("defaultMaxMarchMinutes"),
                    targetCacheTtlMillis = mine.getLong("targetCacheTtlMillis"),
                    playerOccupiedTargetsAllowed = mine.getBoolean("playerOccupiedTargetsAllowed"),
                    exactSelectedLevelRequired = mine.getBoolean("exactSelectedLevelRequired"),
                    resourceCapacityCheckRequired = mine.getBoolean("resourceCapacityCheckRequired"),
                    fullLoyaltyDefault = mine.getBoolean("fullLoyaltyDefault"),
                    replenishTroopsDefault = mine.getBoolean("replenishTroopsDefault"),
                    prepareOpcode = mine.getString("prepareOpcode").parseOpcode(),
                    prepareResponseOpcode = mine.getString("prepareResponseOpcode").parseOpcode(),
                    dispatchOpcode = mine.getString("dispatchOpcode").parseOpcode(),
                    dispatchResponseOpcode = mine.getString("dispatchResponseOpcode").parseOpcode(),
                    dispatchSuccessRequiresPositiveBattleId =
                        mine.getBoolean("dispatchSuccessRequiresPositiveBattleId"),
                    preview = MinePreviewBehaviorContract(
                        minimumPayloadBytes = minePreview.getInt("minimumPayloadBytes"),
                        requireTargetCoordinateMatch =
                            minePreview.getBoolean("requireTargetCoordinateMatch")
                    ),
                    schedule = MineScheduleBehaviorContract(
                        targetUnavailableRetryMillis =
                            mineSchedule.getLong("targetUnavailableRetryMillis"),
                        formationShortageRetryMillis =
                            mineSchedule.getLong("formationShortageRetryMillis"),
                        postDispatchPollMillis = mineSchedule.getLong("postDispatchPollMillis"),
                        garrisonPollMillis = mineSchedule.getLong("garrisonPollMillis"),
                        missingMilitaryGraceMillis =
                            mineSchedule.getLong("missingMilitaryGraceMillis"),
                        settlementTimeoutMillis = mineSchedule.getLong("settlementTimeoutMillis"),
                        postCycleSleepMillis = mineSchedule.getLong("postCycleSleepMillis")
                    ),
                    speed = MineSpeedBehaviorContract(
                        requestOpcode = mineSpeed.getString("requestOpcode").parseOpcode(),
                        responseOpcode = mineSpeed.getString("responseOpcode").parseOpcode(),
                        stopBelowSeconds = mineSpeed.getInt("stopBelowSeconds"),
                        itemSeconds = mineSpeedItems.keys().asSequence().associate { itemId ->
                            itemId.toInt() to mineSpeedItems.getInt(itemId)
                        }
                    ),
                    withdraw = MineWithdrawBehaviorContract(
                        afterGarrisonRequired = withdraw.getBoolean("afterGarrisonRequired"),
                        requestOpcode = withdraw.getString("requestOpcode").parseOpcode(),
                        responseOpcode = withdraw.getString("responseOpcode").parseOpcode(),
                        payloadPrefix = withdraw.getString("payloadPrefixHex").hexBytes(),
                        payloadSuffix = withdraw.getString("payloadSuffixHex").hexBytes(),
                        requireExactBattleIdMatch = withdraw.getBoolean("requireExactBattleIdMatch")
                    )
                ).also { it.validate() },
                raid = RaidBehaviorContract(
                    fiefQueryOpcode = raid.getString("fiefQueryOpcode").parseOpcode(),
                    fiefQueryResponseOpcode = raid.getString("fiefQueryResponseOpcode").parseOpcode(),
                    targetPayloadPrefix = raid.getString("targetPayloadPrefixHex").hexBytes(),
                    actionType = raid.getInt("actionType"),
                    maximumGeneralsPerFormation = raid.getInt("maximumGeneralsPerFormation"),
                    fiefIndexIsOneBased = raid.getBoolean("fiefIndexIsOneBased"),
                    fullTroopsDefault = raid.getBoolean("fullTroopsDefault"),
                    fullLoyaltyDefault = raid.getBoolean("fullLoyaltyDefault"),
                    prepareOpcode = raid.getString("prepareOpcode").parseOpcode(),
                    prepareResponseOpcode = raid.getString("prepareResponseOpcode").parseOpcode(),
                    dispatchOpcode = raid.getString("dispatchOpcode").parseOpcode(),
                    dispatchResponseOpcode = raid.getString("dispatchResponseOpcode").parseOpcode(),
                    dispatchSuccessRequiresPositiveBattleId =
                        raid.getBoolean("dispatchSuccessRequiresPositiveBattleId"),
                    immediateRelatedLong = raid.getLong("immediateRelatedLong"),
                    immediateFlags = raid.getString("immediateFlagsHex").hexBytes(),
                    busyGeneralPollMillis = raid.getLong("busyGeneralPollMillis"),
                    postDispatchPollMillis = raid.getLong("postDispatchPollMillis")
                ).also { it.validate() },
                lossless = LosslessBehaviorContract(
                    statusRequestOpcode = lossless.getString("statusRequestOpcode").parseOpcode(),
                    statusResponseOpcode = lossless.getString("statusResponseOpcode").parseOpcode(),
                    catalogRequestOpcode = lossless.getString("catalogRequestOpcode").parseOpcode(),
                    catalogResponseOpcode = lossless.getString("catalogResponseOpcode").parseOpcode(),
                    settlementRequestOpcode = lossless.getString("settlementRequestOpcode").parseOpcode(),
                    settlementResponseOpcode = lossless.getString("settlementResponseOpcode").parseOpcode(),
                    lineupRequestOpcode = lossless.getString("lineupRequestOpcode").parseOpcode(),
                    lineupResponseOpcode = lossless.getString("lineupResponseOpcode").parseOpcode(),
                    selectRequestOpcode = lossless.getString("selectRequestOpcode").parseOpcode(),
                    selectResponseOpcode = lossless.getString("selectResponseOpcode").parseOpcode(),
                    queryPayload = lossless.getString("queryPayloadHex").hexBytes(),
                    minimumLevel = lossless.getInt("minimumLevel"),
                    maximumLevel = lossless.getInt("maximumLevel"),
                    serverDailyLimit = lossless.getInt("serverDailyLimit"),
                    maximumGeneralsPerFormation = lossless.getInt("maximumGeneralsPerFormation"),
                    fullTroopsDefault = lossless.getBoolean("fullTroopsDefault"),
                    actionType = lossless.getInt("actionType"),
                    prepareOpcode = lossless.getString("prepareOpcode").parseOpcode(),
                    prepareResponseOpcode = lossless.getString("prepareResponseOpcode").parseOpcode(),
                    dispatchOpcode = lossless.getString("dispatchOpcode").parseOpcode(),
                    dispatchResponseOpcode = lossless.getString("dispatchResponseOpcode").parseOpcode(),
                    dispatchSuccessRequiresPositiveBattleId =
                        lossless.getBoolean("dispatchSuccessRequiresPositiveBattleId"),
                    immediateRelatedLong = lossless.getLong("immediateRelatedLong"),
                    immediateFlags = lossless.getString("immediateFlagsHex").hexBytes(),
                    modes = LosslessModeBehaviorContract(
                        cooldown = losslessModes.getInt("cooldown"),
                        ready = losslessModes.getJSONArray("ready").intList(),
                        fighting = losslessModes.getInt("fighting"),
                        dailyDone = losslessModes.getInt("dailyDone")
                    ),
                    stageNames = lossless.getJSONArray("stageNames").stringList(),
                    level10Guard = LosslessLevel10GuardBehaviorContract(
                        level = losslessGuard.getInt("level"),
                        stageId = losslessGuard.getInt("stageId"),
                        stageName = losslessGuard.getString("stageName"),
                        enemyCount = losslessGuard.getInt("enemyCount"),
                        chariotTokens = losslessGuard.getJSONArray("chariotTokens").stringList(),
                        catapultToken = losslessGuard.getString("catapultToken"),
                        minimumChariots = losslessGuard.getInt("minimumChariots"),
                        lastChariotMustBeCatapult =
                            losslessGuard.getBoolean("lastChariotMustBeCatapult"),
                        alternateLevel = losslessGuard.getInt("alternateLevel"),
                        defaultMaxRerolls = losslessGuard.getInt("defaultMaxRerolls"),
                        maximumMaxRerolls = losslessGuard.getInt("maximumMaxRerolls"),
                        rerollDelayMinMillis = losslessGuard.getLong("rerollDelayMinMillis"),
                        rerollDelayMaxMillis = losslessGuard.getLong("rerollDelayMaxMillis")
                    ),
                    schedule = LosslessScheduleBehaviorContract(
                        settlementRecheckMillis = losslessSchedule.getLong("settlementRecheckMillis"),
                        fightingPollMillis = losslessSchedule.getLong("fightingPollMillis"),
                        cooldownPollMinMillis = losslessSchedule.getLong("cooldownPollMinMillis"),
                        cooldownPollMaxMillis = losslessSchedule.getLong("cooldownPollMaxMillis"),
                        rerollNextCheckMillis = losslessSchedule.getLong("rerollNextCheckMillis"),
                        postDispatchPollMillis = losslessSchedule.getLong("postDispatchPollMillis"),
                        battleTimeoutMillis = losslessSchedule.getLong("battleTimeoutMillis")
                    )
                ).also { it.validate() },
                dungeon = DungeonBehaviorContract(
                    catalogRequestOpcode = dungeon.getString("catalogRequestOpcode").parseOpcode(),
                    catalogResponseOpcode = dungeon.getString("catalogResponseOpcode").parseOpcode(),
                    stateRequestOpcode = dungeon.getString("stateRequestOpcode").parseOpcode(),
                    stateResponseOpcode = dungeon.getString("stateResponseOpcode").parseOpcode(),
                    rewardRequestOpcode = dungeon.getString("rewardRequestOpcode").parseOpcode(),
                    rewardResponseOpcode = dungeon.getString("rewardResponseOpcode").parseOpcode(),
                    battlePollRequestOpcode = dungeon.getString("battlePollRequestOpcode").parseOpcode(),
                    battlePollResponseOpcode = dungeon.getString("battlePollResponseOpcode").parseOpcode(),
                    chestRequestOpcode = dungeon.getString("chestRequestOpcode").parseOpcode(),
                    chestResponseOpcode = dungeon.getString("chestResponseOpcode").parseOpcode(),
                    maximumGeneralsPerFormation = dungeon.getInt("maximumGeneralsPerFormation"),
                    actionType = dungeon.getInt("actionType"),
                    singlePlayerType = dungeon.getInt("singlePlayerType"),
                    prepareOpcode = dungeon.getString("prepareOpcode").parseOpcode(),
                    prepareResponseOpcode = dungeon.getString("prepareResponseOpcode").parseOpcode(),
                    dispatchOpcode = dungeon.getString("dispatchOpcode").parseOpcode(),
                    dispatchResponseOpcode = dungeon.getString("dispatchResponseOpcode").parseOpcode(),
                    immediateRelatedLong = dungeon.getLong("immediateRelatedLong"),
                    immediateFlags = dungeon.getString("immediateFlagsHex").hexBytes(),
                    allowedModes = dungeon.getJSONArray("allowedModes").stringList(),
                    defaultMode = dungeon.getString("defaultMode"),
                    chestNames = dungeon.getJSONArray("chestNames").stringList(),
                    uncompletedResultCode = dungeon.getInt("uncompletedResultCode"),
                    clearModeSkipsMultiplayerFinals =
                        dungeon.getBoolean("clearModeSkipsMultiplayerFinals"),
                    clearModeRequiresCatalogConfirmation =
                        dungeon.getBoolean("clearModeRequiresCatalogConfirmation"),
                    clearModePausesOnDefeat = dungeon.getBoolean("clearModePausesOnDefeat"),
                    defeatMarkers = dungeon.getJSONArray("defeatMarkers").stringList(),
                    launchSuccessMarkers = dungeon.getJSONArray("launchSuccessMarkers").stringList(),
                    staticStageCodes = dungeonStages.keys().asSequence().associate { chapter ->
                        chapter.toInt() to dungeonStages.getJSONArray(chapter).intList()
                    },
                    schedule = DungeonScheduleBehaviorContract(
                        postLaunchPollMillis = dungeonSchedule.getLong("postLaunchPollMillis"),
                        battlePollMillis = dungeonSchedule.getLong("battlePollMillis"),
                        battleTimeoutMillis = dungeonSchedule.getLong("battleTimeoutMillis"),
                        postCompletionMillis = dungeonSchedule.getLong("postCompletionMillis"),
                        waitingUnlockMillis = dungeonSchedule.getLong("waitingUnlockMillis"),
                        dailyDonePollMillis = dungeonSchedule.getLong("dailyDonePollMillis")
                    )
                ).also { it.validate() },
                militarySnapshot = MilitarySnapshotBehaviorContract(
                    requestOpcode = militarySnapshot.getString("requestOpcode").parseOpcode(),
                    responseOpcode = militarySnapshot.getString("responseOpcode").parseOpcode(),
                    requestPayload = militarySnapshot.getString("requestPayloadHex").hexBytes()
                )
            )
        }
    }
}

data class SchedulerBehaviorContract(
    val residentPriority: Map<String, Int>,
    val sameGeneralMutualExclusionRequired: Boolean,
    val onlyRunnableResidentBlocksLowerPriority: Boolean,
    val formationPrerequisiteRunsFirst: Boolean,
    val dailyFeaturesRunBeforeResidents: Boolean,
    val militaryLaneRunsBeforeIdleLane: Boolean,
    val expeditionPreparationIsTaskScoped: Boolean,
    val idleLaneMustYieldToDueMilitaryWork: Boolean,
    val observationRefreshMayRunBetweenLanes: Boolean,
    val waitStatePersistsAcrossProcess: Boolean,
    val dayBoundaryUsesContractTimezone: Boolean,
    val ministryPollMillis: Long
) {
    fun residentKey(type: TaskType): String? = when (type) {
        TaskType.AUTO_MINING, TaskType.MINE_SEARCH, TaskType.MINE_PREFETCH -> "mine"
        TaskType.LOSSLESS -> "lossless"
        TaskType.SHUA_HUANG, TaskType.BANDIT_PREFETCH -> "brushYellow"
        TaskType.AUTO_LOOT -> "raid"
        TaskType.DUNGEON -> "dungeon"
        TaskType.SIX_MINISTRIES -> "ministry"
        else -> null
    }

    fun residentPriority(type: TaskType): Int? = residentKey(type)?.let(residentPriority::get)

    fun validate() {
        require(residentPriority.keys == REQUIRED_RESIDENTS) {
            "scheduler residentPriority must contain $REQUIRED_RESIDENTS"
        }
        require(residentPriority.values.all { it > 0 } && residentPriority.values.toSet().size == residentPriority.size) {
            "scheduler resident priorities must be positive and unique"
        }
        require(sameGeneralMutualExclusionRequired) { "same-general mutual exclusion must stay enabled" }
        require(onlyRunnableResidentBlocksLowerPriority) { "only-runnable blocking invariant must stay enabled" }
        require(!formationPrerequisiteRunsFirst) {
            "global formation batch must stay disabled; expedition preparation is task-scoped"
        }
        require(!dailyFeaturesRunBeforeResidents) {
            "daily features must not delay due military work"
        }
        require(militaryLaneRunsBeforeIdleLane) { "military lane must run before idle lane" }
        require(expeditionPreparationIsTaskScoped) {
            "expedition healing, energy and formation repair must be task-scoped"
        }
        require(idleLaneMustYieldToDueMilitaryWork) {
            "idle lane must yield to due military work"
        }
        require(observationRefreshMayRunBetweenLanes) {
            "observation refresh must remain independent from idle mutations"
        }
        require(waitStatePersistsAcrossProcess) { "scheduler wait state must survive process restart" }
        require(dayBoundaryUsesContractTimezone) { "scheduler day boundary must use contract timezone" }
        require(ministryPollMillis > 0L) { "scheduler ministry poll interval must be positive" }
    }

    companion object {
        private val REQUIRED_RESIDENTS = setOf(
            "mine", "lossless", "brushYellow", "raid", "dungeon", "ministry"
        )

        fun defaults(): SchedulerBehaviorContract = SchedulerBehaviorContract(
            residentPriority = linkedMapOf(
                "mine" to 400,
                "lossless" to 300,
                "brushYellow" to 200,
                "raid" to 125,
                "dungeon" to 100,
                "ministry" to 50
            ),
            sameGeneralMutualExclusionRequired = true,
            onlyRunnableResidentBlocksLowerPriority = true,
            formationPrerequisiteRunsFirst = false,
            dailyFeaturesRunBeforeResidents = false,
            militaryLaneRunsBeforeIdleLane = true,
            expeditionPreparationIsTaskScoped = true,
            idleLaneMustYieldToDueMilitaryWork = true,
            observationRefreshMayRunBetweenLanes = true,
            waitStatePersistsAcrossProcess = true,
            dayBoundaryUsesContractTimezone = true,
            ministryPollMillis = 600_000L
        )
    }
}

data class AccountLifecycleBehaviorContract(
    val startedRequiresExecutionOwner: Boolean,
    val startRunsFreshLogin: Boolean,
    val heartbeatIntervalMillis: Long,
    val statusText: Map<String, String>
) {
    fun validate() {
        require(heartbeatIntervalMillis > 0L) {
            "account lifecycle heartbeat interval must be positive"
        }
        require(statusText.keys.containsAll(REQUIRED_STATUSES)) {
            "account lifecycle statusText must define ${REQUIRED_STATUSES.joinToString()}"
        }
        require(statusText.values.none(String::isBlank)) {
            "account lifecycle statusText values must not be blank"
        }
    }

    companion object {
        private val REQUIRED_STATUSES = setOf("online", "checking", "offline", "stopped")

        fun defaults() = AccountLifecycleBehaviorContract(
            startedRequiresExecutionOwner = true,
            startRunsFreshLogin = true,
            heartbeatIntervalMillis = 20_000L,
            statusText = mapOf(
                "online" to "开启",
                "checking" to "检测中",
                "offline" to "掉线",
                "stopped" to "未开启"
            )
        )
    }
}

data class DailyActionsBehaviorContract(
    val arenaCoins: ArenaCoinsBehaviorContract,
    val donate: DonationBehaviorContract,
    val salary: SalaryBehaviorContract,
    val nationalCollect: NationalCollectBehaviorContract,
    val cityLordCollect: CityLordCollectBehaviorContract,
    val generalVisit: GeneralVisitBehaviorContract
) {
    fun validate() {
        require(donate.copperPerLevel > 0 && donate.foodPerLevel > 0 && donate.technologyPerLevel > 0) {
            "daily donation multipliers must be positive"
        }
        require(salary.payload.isNotEmpty()) { "daily salary payload must not be empty" }
        require(nationalCollect.includedListCategories == listOf(1, 2, 3)) {
            "national collection must query state/commandery/county only"
        }
        require(nationalCollect.responseHeaderBytes == 7) {
            "0x8404 response header must stay at the captured seven-byte shape"
        }
        require(nationalCollect.recordTailBytes > 0 && nationalCollect.pageSize > 0 && nationalCollect.maxAttempts > 0) {
            "national collection limits must be positive"
        }
        require(cityLordCollect.ownedCityPayloadSuffix.isNotEmpty()) {
            "owned-city query suffix must not be empty"
        }
        require(generalVisit.pageSize > 0 && generalVisit.maxSelected > 0) {
            "general visit limits must be positive"
        }
    }

    companion object {
        fun defaults(): DailyActionsBehaviorContract = DailyActionsBehaviorContract(
            arenaCoins = ArenaCoinsBehaviorContract.defaults(),
            donate = DonationBehaviorContract.defaults(),
            salary = SalaryBehaviorContract.defaults(),
            nationalCollect = NationalCollectBehaviorContract.defaults(),
            cityLordCollect = CityLordCollectBehaviorContract.defaults(),
            generalVisit = GeneralVisitBehaviorContract.defaults()
        )
    }
}

data class ArenaCoinsBehaviorContract(
    val readRequestOpcode: Int,
    val claimRequestOpcode: Int,
    val claimResponseOpcode: Int
) {
    companion object {
        fun defaults() = ArenaCoinsBehaviorContract(0x6260, 0x6266, 0xE266)
    }
}

data class DonationBehaviorContract(
    val resourceRequestOpcode: Int,
    val resourceResponseOpcode: Int,
    val technologyRequestOpcode: Int,
    val technologyResponseOpcode: Int,
    val copperPerLevel: Int,
    val foodPerLevel: Int,
    val technologyPerLevel: Int
) {
    companion object {
        fun defaults() = DonationBehaviorContract(
            resourceRequestOpcode = 0x140C,
            resourceResponseOpcode = 0x840C,
            technologyRequestOpcode = 0x140A,
            technologyResponseOpcode = 0x840A,
            copperPerLevel = 1_000,
            foodPerLevel = 3_000,
            technologyPerLevel = 1_000
        )
    }
}

data class SalaryBehaviorContract(
    val requestOpcode: Int,
    val responseOpcode: Int,
    val payload: ByteArray,
    val alreadyClaimedMarkers: List<String>,
    val noOfficeMarkers: List<String>,
    val successMarkers: List<String>
) {
    companion object {
        fun defaults() = SalaryBehaviorContract(
            requestOpcode = 0x314B,
            responseOpcode = 0xA14B,
            payload = byteArrayOf(1),
            alreadyClaimedMarkers = listOf(
                "无法再次领取", "已经领取", "已领取", "今日已领取", "本日已领取", "今天已经领取"
            ),
            noOfficeMarkers = listOf(
                "无官职", "没有官职", "只有官员才能领取", "官员才能领取俸禄", "当前不能领取俸禄"
            ),
            successMarkers = listOf("成功", "获得铜钱")
        )
    }
}

data class NationalCollectBehaviorContract(
    val cityListRequestOpcode: Int,
    val cityListResponseOpcode: Int,
    val statusRequestOpcode: Int,
    val statusResponseOpcode: Int,
    val collectRequestOpcode: Int,
    val collectResponseOpcode: Int,
    val includedListCategories: List<Int>,
    val responseHeaderBytes: Int,
    val recordTailBytes: Int,
    val pageSize: Int,
    val maxAttempts: Int
) {
    companion object {
        fun defaults() = NationalCollectBehaviorContract(
            cityListRequestOpcode = 0x1404,
            cityListResponseOpcode = 0x8404,
            statusRequestOpcode = 0x1332,
            statusResponseOpcode = 0x8332,
            collectRequestOpcode = 0x1334,
            collectResponseOpcode = 0x8334,
            includedListCategories = listOf(1, 2, 3),
            responseHeaderBytes = 7,
            recordTailBytes = 34,
            pageSize = 10,
            maxAttempts = 20
        )
    }
}

data class CityLordCollectBehaviorContract(
    val ownedCityRequestOpcode: Int,
    val ownedCityResponseOpcode: Int,
    val ownedCityPayloadSuffix: ByteArray,
    val collectRequestOpcode: Int,
    val collectResponseOpcode: Int,
    val ineligibleMarkers: List<String>,
    val alreadyCollectedMarkers: List<String>
) {
    companion object {
        fun defaults() = CityLordCollectBehaviorContract(
            ownedCityRequestOpcode = 0x1318,
            ownedCityResponseOpcode = 0x8318,
            ownedCityPayloadSuffix = byteArrayOf(0, 0),
            collectRequestOpcode = 0x1330,
            collectResponseOpcode = 0x8330,
            ineligibleMarkers = listOf(
                "都城及其周边与之相联的门户城池不能进行征收",
                "只有城主可以使用城主征收功能",
                "您不是城主",
                "不是城主"
            ),
            alreadyCollectedMarkers = listOf(
                "已经征收", "本日已征收", "今日已征收", "今天已经征收", "已经进行过征收"
            )
        )
    }
}

data class GeneralVisitBehaviorContract(
    val listRequestOpcode: Int,
    val listResponseOpcode: Int,
    val visitRequestOpcode: Int,
    val visitResponseOpcode: Int,
    val pageSize: Int,
    val maxSelected: Int,
    val alreadyVisitedStatus: Int,
    val alreadyVisitedMarkers: List<String>,
    val invitationResolvedMarkers: List<String>
) {
    companion object {
        fun defaults() = GeneralVisitBehaviorContract(
            listRequestOpcode = 0x3271,
            listResponseOpcode = 0xA271,
            visitRequestOpcode = 0x3273,
            visitResponseOpcode = 0xA273,
            pageSize = 4,
            maxSelected = 4,
            alreadyVisitedStatus = -2,
            alreadyVisitedMarkers = listOf("本日已拜访", "今日已拜访", "已经拜访"),
            invitationResolvedMarkers = listOf(
                "拒绝了阁下的邀请", "接受了阁下的邀请", "愿意追随", "纳入帐下"
            )
        )
    }
}

data class ExpeditionBehaviorContract(
    val prepareOpcode: Int,
    val prepareResponseOpcode: Int,
    val dispatchOpcode: Int,
    val dispatchResponseOpcode: Int,
    val serverConfirmedSuccessRequired: Boolean,
    val dispatchSuccessRequiresPositiveBattleId: Boolean,
    val softRejectPayload: ByteArray
) {
    fun validate() {
        require(prepareOpcode > 0 && prepareResponseOpcode > 0) {
            "expedition prepare opcodes must be positive"
        }
        require(dispatchOpcode > 0 && dispatchResponseOpcode > 0) {
            "expedition dispatch opcodes must be positive"
        }
        require(serverConfirmedSuccessRequired) {
            "expedition actions must require a server-confirmed result"
        }
        require(dispatchSuccessRequiresPositiveBattleId) {
            "expedition dispatch must require a positive battleId"
        }
        require(softRejectPayload.isNotEmpty()) {
            "expedition soft-reject payload must not be empty"
        }
    }

    fun isSoftReject(payload: ByteArray): Boolean = payload.contentEquals(softRejectPayload)

    companion object {
        fun defaults() = ExpeditionBehaviorContract(
            prepareOpcode = 0x1520,
            prepareResponseOpcode = 0x8520,
            dispatchOpcode = 0x1522,
            dispatchResponseOpcode = 0x8522,
            serverConfirmedSuccessRequired = true,
            dispatchSuccessRequiresPositiveBattleId = true,
            softRejectPayload = "ff0000".hexBytes()
        )
    }
}

data class FormationBehaviorContract(
    val assignRequestOpcode: Int,
    val assignResponseOpcode: Int,
    val refillRequestOpcode: Int,
    val refillResponseOpcode: Int,
    val idleGeneralStatus: Int,
    val clampCountToTroopLimit: Boolean,
    val precheckIdleSoldierInventory: Boolean,
    val exactAssignedTypeAndCountRequired: Boolean,
    val clearOtherGeneralsSkipsBusy: Boolean,
    val assignmentDoesNotImplicitlyRefill: Boolean,
    val completedSleepMillis: Long
) {
    fun validate() {
        require(assignRequestOpcode > 0 && assignResponseOpcode > 0) {
            "formation assignment opcodes must be positive"
        }
        require(refillRequestOpcode > 0 && refillResponseOpcode > 0) {
            "formation refill opcodes must be positive"
        }
        require(clampCountToTroopLimit) { "formation count must be clamped to troop limit" }
        require(precheckIdleSoldierInventory) { "formation assignment must precheck idle soldiers" }
        require(exactAssignedTypeAndCountRequired) { "formation receipt must exactly match the target" }
        require(clearOtherGeneralsSkipsBusy) { "formation cleanup must skip busy generals" }
        require(assignmentDoesNotImplicitlyRefill) { "formation assignment must not imply batch refill" }
        require(completedSleepMillis > 0L) { "formation completed sleep must be positive" }
    }

    companion object {
        fun defaults() = FormationBehaviorContract(
            assignRequestOpcode = 0x1226,
            assignResponseOpcode = 0x8226,
            refillRequestOpcode = 0x1229,
            refillResponseOpcode = 0x8229,
            idleGeneralStatus = 0,
            clampCountToTroopLimit = true,
            precheckIdleSoldierInventory = true,
            exactAssignedTypeAndCountRequired = true,
            clearOtherGeneralsSkipsBusy = true,
            assignmentDoesNotImplicitlyRefill = true,
            completedSleepMillis = 31_536_000_000L
        )
    }
}

data class MapWorldBehaviorContract(
    val xMin: Int,
    val xMax: Int,
    val yMin: Int,
    val yMax: Int,
    val step: Int
) {
    val coordinateCount: Int
        get() = ((xMax - xMin) / step + 1) * ((yMax - yMin) / step + 1)

    fun validate() {
        require(xMin >= 0 && yMin >= 0 && xMax >= xMin && yMax >= yMin) {
            "map-search world bounds are invalid"
        }
        require(step > 0) { "map-search world step must be positive" }
    }

    companion object {
        fun defaults() = MapWorldBehaviorContract(0, 186, 0, 66, 6)
    }
}

data class MapSearchBehaviorContract(
    val banditRequestOpcode: Int,
    val banditResponseOpcode: Int,
    val realEnemyUnitCompositionRequired: Boolean,
    val world: MapWorldBehaviorContract,
    val nearbyRequestLimit: Int,
    val fullRequestLimit: Int,
    val preparationBatchSize: Int,
    val idleScanBatchSize: Int,
    val scanCoordinateCacheTtlMillis: Long,
    val targetCacheTtlMillis: Long,
    val filters: List<String>
) {
    fun validate() {
        world.validate()
        require(banditRequestOpcode > 0 && banditResponseOpcode > 0) {
            "bandit-search opcodes must be positive"
        }
        require(realEnemyUnitCompositionRequired) {
            "bandit filtering must use real enemy composition"
        }
        require(nearbyRequestLimit in 1..world.coordinateCount) {
            "nearby map-search limit is outside the world lattice"
        }
        require(fullRequestLimit == world.coordinateCount) {
            "full map-search limit must cover the canonical world lattice exactly"
        }
        require(preparationBatchSize in 1..nearbyRequestLimit && idleScanBatchSize in 1..preparationBatchSize) {
            "map-search batch sizes are invalid"
        }
        require(scanCoordinateCacheTtlMillis > 0L && targetCacheTtlMillis >= scanCoordinateCacheTtlMillis) {
            "map-search cache TTL values are invalid"
        }
        require(filters.containsAll(REQUIRED_FILTERS)) {
            "map-search filters must include ${REQUIRED_FILTERS.joinToString()}"
        }
    }

    companion object {
        private val REQUIRED_FILTERS = setOf(
            "targetKind", "levels", "drops", "maxFoot", "maxBow",
            "maxCavalry", "maxChariot", "distance"
        )

        fun defaults() = MapSearchBehaviorContract(
            banditRequestOpcode = 0x1540,
            banditResponseOpcode = 0x8540,
            realEnemyUnitCompositionRequired = true,
            world = MapWorldBehaviorContract.defaults(),
            nearbyRequestLimit = 80,
            fullRequestLimit = 384,
            preparationBatchSize = 10,
            idleScanBatchSize = 1,
            scanCoordinateCacheTtlMillis = 120_000L,
            targetCacheTtlMillis = 1_800_000L,
            filters = REQUIRED_FILTERS.toList()
        )
    }
}

data class BrushYellowScheduleBehaviorContract(
    val transientRetryMillis: Long,
    val targetUnavailableRetryMillis: Long,
    val busyGeneralPollMillis: Long,
    val postDispatchPollMillis: Long,
    val postReturnMaintenanceDelayMillis: Long,
    val formationShortageRetryMillis: Long,
    val mapPreparationIdlePauseMillis: Long,
    val settlementFullRefreshMillis: Long,
    val settlementRecheckGraceMillis: Long
) {
    fun validate() {
        require(
            listOf(
                transientRetryMillis,
                targetUnavailableRetryMillis,
                busyGeneralPollMillis,
                postDispatchPollMillis,
                postReturnMaintenanceDelayMillis,
                formationShortageRetryMillis,
                mapPreparationIdlePauseMillis,
                settlementFullRefreshMillis,
                settlementRecheckGraceMillis
            ).all { it > 0L }
        ) { "brush-yellow schedule intervals must be positive" }
    }

    companion object {
        fun defaults() = BrushYellowScheduleBehaviorContract(
            transientRetryMillis = 10_000L,
            targetUnavailableRetryMillis = 10_000L,
            busyGeneralPollMillis = 30_000L,
            postDispatchPollMillis = 30_000L,
            postReturnMaintenanceDelayMillis = 1_000L,
            formationShortageRetryMillis = 60_000L,
            mapPreparationIdlePauseMillis = 2_000L,
            settlementFullRefreshMillis = 30_000L,
            settlementRecheckGraceMillis = 300_000L
        )
    }
}

data class BrushYellowBehaviorContract(
    val minimumRoleLevel: Int,
    val maximumGeneralsPerFormation: Int,
    val actionType: Int,
    val exactSelectedLevelsRequired: Boolean,
    val schedule: BrushYellowScheduleBehaviorContract
) {
    fun validate() {
        require(minimumRoleLevel > 0) { "brush-yellow minimum role level must be positive" }
        require(maximumGeneralsPerFormation in 1..255) {
            "brush-yellow maximum generals per formation is invalid"
        }
        require(actionType in 0..255) { "brush-yellow action type must fit one byte" }
        require(exactSelectedLevelsRequired) {
            "brush-yellow must match the exact selected target-level set"
        }
        schedule.validate()
    }

    companion object {
        fun defaults() = BrushYellowBehaviorContract(
            minimumRoleLevel = 30,
            maximumGeneralsPerFormation = 5,
            actionType = 3,
            exactSelectedLevelsRequired = true,
            schedule = BrushYellowScheduleBehaviorContract.defaults()
        )
    }
}

data class MineBehaviorContract(
    val searchRequestOpcode: Int,
    val searchResponseOpcode: Int,
    val actionType: Int,
    val maximumGeneralsPerFormation: Int,
    val allowedSearchScopes: List<String>,
    val defaultSearchScope: String,
    val allowedMaxMarchMinutes: List<Int>,
    val defaultMaxMarchMinutes: Int,
    val targetCacheTtlMillis: Long,
    val playerOccupiedTargetsAllowed: Boolean,
    val exactSelectedLevelRequired: Boolean,
    val resourceCapacityCheckRequired: Boolean,
    val fullLoyaltyDefault: Boolean,
    val replenishTroopsDefault: Boolean,
    val prepareOpcode: Int,
    val prepareResponseOpcode: Int,
    val dispatchOpcode: Int,
    val dispatchResponseOpcode: Int,
    val dispatchSuccessRequiresPositiveBattleId: Boolean,
    val preview: MinePreviewBehaviorContract,
    val schedule: MineScheduleBehaviorContract,
    val speed: MineSpeedBehaviorContract,
    val withdraw: MineWithdrawBehaviorContract
) {
    fun validate() {
        require(searchRequestOpcode > 0 && searchResponseOpcode > 0) {
            "mine-search opcodes must be positive"
        }
        require(actionType in 0..255) { "mine action type must fit one byte" }
        require(maximumGeneralsPerFormation in 1..255) {
            "mine maximum generals per formation is invalid"
        }
        require(allowedSearchScopes.toSet() == setOf("\u5b9a\u70b9", "\u9644\u8fd1", "\u5168\u56fd")) {
            "mine search scopes must match the desktop options"
        }
        require(defaultSearchScope in allowedSearchScopes) { "mine default search scope is invalid" }
        require(allowedMaxMarchMinutes.distinct().sorted() == listOf(45, 60, 90)) {
            "mine march-minute options must match the desktop options"
        }
        require(defaultMaxMarchMinutes in allowedMaxMarchMinutes) {
            "mine default march-minute option is invalid"
        }
        require(targetCacheTtlMillis > 0L) { "mine target-cache TTL must be positive" }
        require(!playerOccupiedTargetsAllowed) { "automatic mine attacks must reject player targets" }
        require(exactSelectedLevelRequired) { "mine level filtering must be exact" }
        require(resourceCapacityCheckRequired) { "mine dispatch must check resource capacity" }
        require(prepareOpcode > 0 && prepareResponseOpcode > 0 &&
            dispatchOpcode > 0 && dispatchResponseOpcode > 0
        ) { "mine expedition opcodes must be positive" }
        require(dispatchSuccessRequiresPositiveBattleId) {
            "mine dispatch must require a positive battle id"
        }
        preview.validate()
        schedule.validate()
        speed.validate()
        withdraw.validate()
    }

    companion object {
        fun defaults(): MineBehaviorContract = MineBehaviorContract(
            searchRequestOpcode = 0x1542,
            searchResponseOpcode = 0x8542,
            actionType = 2,
            maximumGeneralsPerFormation = 5,
            allowedSearchScopes = listOf("\u5b9a\u70b9", "\u9644\u8fd1", "\u5168\u56fd"),
            defaultSearchScope = "\u9644\u8fd1",
            allowedMaxMarchMinutes = listOf(45, 60, 90),
            defaultMaxMarchMinutes = 45,
            targetCacheTtlMillis = 10_800_000L,
            playerOccupiedTargetsAllowed = false,
            exactSelectedLevelRequired = true,
            resourceCapacityCheckRequired = true,
            fullLoyaltyDefault = true,
            replenishTroopsDefault = true,
            prepareOpcode = 0x1520,
            prepareResponseOpcode = 0x8520,
            dispatchOpcode = 0x1522,
            dispatchResponseOpcode = 0x8522,
            dispatchSuccessRequiresPositiveBattleId = true,
            preview = MinePreviewBehaviorContract.defaults(),
            schedule = MineScheduleBehaviorContract.defaults(),
            speed = MineSpeedBehaviorContract.defaults(),
            withdraw = MineWithdrawBehaviorContract.defaults()
        )
    }
}

data class MinePreviewBehaviorContract(
    val minimumPayloadBytes: Int,
    val requireTargetCoordinateMatch: Boolean
) {
    fun validate() {
        require(minimumPayloadBytes == 25) { "mine 0x8520 preview must use the 25-byte prefix" }
        require(requireTargetCoordinateMatch) { "mine preview must match the selected target" }
    }

    companion object {
        fun defaults() = MinePreviewBehaviorContract(25, true)
    }
}

data class MineScheduleBehaviorContract(
    val targetUnavailableRetryMillis: Long,
    val formationShortageRetryMillis: Long,
    val postDispatchPollMillis: Long,
    val garrisonPollMillis: Long,
    val missingMilitaryGraceMillis: Long,
    val settlementTimeoutMillis: Long,
    val postCycleSleepMillis: Long
) {
    fun validate() {
        require(
            listOf(
                targetUnavailableRetryMillis,
                formationShortageRetryMillis,
                postDispatchPollMillis,
                garrisonPollMillis,
                missingMilitaryGraceMillis,
                settlementTimeoutMillis,
                postCycleSleepMillis
            ).all { it > 0L }
        ) { "mine schedule intervals must be positive" }
        require(settlementTimeoutMillis >= missingMilitaryGraceMillis) {
            "mine settlement timeout must cover the missing-military grace period"
        }
    }

    companion object {
        fun defaults() = MineScheduleBehaviorContract(
            targetUnavailableRetryMillis = 10_000L,
            formationShortageRetryMillis = 60_000L,
            postDispatchPollMillis = 5_000L,
            garrisonPollMillis = 10_000L,
            missingMilitaryGraceMillis = 120_000L,
            settlementTimeoutMillis = 14_400_000L,
            postCycleSleepMillis = 30_000L
        )
    }
}

data class MineSpeedBehaviorContract(
    val requestOpcode: Int,
    val responseOpcode: Int,
    val stopBelowSeconds: Int,
    val itemSeconds: Map<Int, Int>
) {
    fun validate() {
        require(requestOpcode > 0 && responseOpcode > 0) {
            "mine speed opcodes must be positive"
        }
        require(stopBelowSeconds > 0) { "mine speed stop threshold must be positive" }
        require(itemSeconds == mapOf(76 to 900, 77 to 1800, 78 to 3600, 79 to 10800)) {
            "mine speed item durations must match the desktop behavior"
        }
    }

    companion object {
        fun defaults() = MineSpeedBehaviorContract(
            requestOpcode = 0x1524,
            responseOpcode = 0x8524,
            stopBelowSeconds = 60,
            itemSeconds = mapOf(76 to 900, 77 to 1800, 78 to 3600, 79 to 10800)
        )
    }
}

data class MineWithdrawBehaviorContract(
    val afterGarrisonRequired: Boolean,
    val requestOpcode: Int,
    val responseOpcode: Int,
    val payloadPrefix: ByteArray,
    val payloadSuffix: ByteArray,
    val requireExactBattleIdMatch: Boolean
) {
    fun validate() {
        require(afterGarrisonRequired) { "mine must recall only after a confirmed garrison" }
        require(requestOpcode > 0 && responseOpcode > 0) {
            "mine withdraw opcodes must be positive"
        }
        require(payloadPrefix.isNotEmpty() && payloadSuffix.isNotEmpty()) {
            "mine withdraw payload framing must not be empty"
        }
        require(requireExactBattleIdMatch) { "mine withdraw must match the exact battle id" }
    }

    companion object {
        fun defaults(): MineWithdrawBehaviorContract = MineWithdrawBehaviorContract(
            afterGarrisonRequired = true,
            requestOpcode = 0x1526,
            responseOpcode = 0x8526,
            payloadPrefix = "0101".hexBytes(),
            payloadSuffix = "00".hexBytes(),
            requireExactBattleIdMatch = true
        )
    }
}

data class RaidBehaviorContract(
    val fiefQueryOpcode: Int,
    val fiefQueryResponseOpcode: Int,
    val targetPayloadPrefix: ByteArray,
    val actionType: Int,
    val maximumGeneralsPerFormation: Int,
    val fiefIndexIsOneBased: Boolean,
    val fullTroopsDefault: Boolean,
    val fullLoyaltyDefault: Boolean,
    val prepareOpcode: Int,
    val prepareResponseOpcode: Int,
    val dispatchOpcode: Int,
    val dispatchResponseOpcode: Int,
    val dispatchSuccessRequiresPositiveBattleId: Boolean,
    val immediateRelatedLong: Long,
    val immediateFlags: ByteArray,
    val busyGeneralPollMillis: Long,
    val postDispatchPollMillis: Long
) {
    fun validate() {
        require(fiefQueryOpcode > 0 && fiefQueryResponseOpcode > 0) {
            "raid fief-query opcodes must be positive"
        }
        require(targetPayloadPrefix.contentEquals("0001".hexBytes())) {
            "raid fief-query prefix must be 0001"
        }
        require(actionType in 0..255) { "raid action type must fit one byte" }
        require(maximumGeneralsPerFormation in 1..255) {
            "raid maximum generals per formation is invalid"
        }
        require(fiefIndexIsOneBased) { "raid fief index must be one-based" }
        require(prepareOpcode > 0 && prepareResponseOpcode > 0 &&
            dispatchOpcode > 0 && dispatchResponseOpcode > 0
        ) { "raid expedition opcodes must be positive" }
        require(dispatchSuccessRequiresPositiveBattleId) {
            "raid dispatch must require a positive battle id"
        }
        require(immediateRelatedLong == -1L && immediateFlags.contentEquals(byteArrayOf(0, 0, 0))) {
            "raid immediate-dispatch suffix is invalid"
        }
        require(busyGeneralPollMillis > 0L && postDispatchPollMillis > 0L) {
            "raid schedule intervals must be positive"
        }
    }

    companion object {
        fun defaults(): RaidBehaviorContract = RaidBehaviorContract(
            fiefQueryOpcode = 0x1310,
            fiefQueryResponseOpcode = 0x8310,
            targetPayloadPrefix = "0001".hexBytes(),
            actionType = 1,
            maximumGeneralsPerFormation = 5,
            fiefIndexIsOneBased = true,
            fullTroopsDefault = true,
            fullLoyaltyDefault = false,
            prepareOpcode = 0x1520,
            prepareResponseOpcode = 0x8520,
            dispatchOpcode = 0x1522,
            dispatchResponseOpcode = 0x8522,
            dispatchSuccessRequiresPositiveBattleId = true,
            immediateRelatedLong = -1L,
            immediateFlags = byteArrayOf(0, 0, 0),
            busyGeneralPollMillis = 10_000L,
            postDispatchPollMillis = 60_000L
        )
    }
}

data class LosslessBehaviorContract(
    val statusRequestOpcode: Int,
    val statusResponseOpcode: Int,
    val catalogRequestOpcode: Int,
    val catalogResponseOpcode: Int,
    val settlementRequestOpcode: Int,
    val settlementResponseOpcode: Int,
    val lineupRequestOpcode: Int,
    val lineupResponseOpcode: Int,
    val selectRequestOpcode: Int,
    val selectResponseOpcode: Int,
    val queryPayload: ByteArray,
    val minimumLevel: Int,
    val maximumLevel: Int,
    val serverDailyLimit: Int,
    val maximumGeneralsPerFormation: Int,
    val fullTroopsDefault: Boolean,
    val actionType: Int,
    val prepareOpcode: Int,
    val prepareResponseOpcode: Int,
    val dispatchOpcode: Int,
    val dispatchResponseOpcode: Int,
    val dispatchSuccessRequiresPositiveBattleId: Boolean,
    val immediateRelatedLong: Long,
    val immediateFlags: ByteArray,
    val modes: LosslessModeBehaviorContract,
    val stageNames: List<String>,
    val level10Guard: LosslessLevel10GuardBehaviorContract,
    val schedule: LosslessScheduleBehaviorContract
) {
    fun validate() {
        require(
            listOf(
                statusRequestOpcode, statusResponseOpcode,
                catalogRequestOpcode, catalogResponseOpcode,
                settlementRequestOpcode, settlementResponseOpcode,
                lineupRequestOpcode, lineupResponseOpcode,
                selectRequestOpcode, selectResponseOpcode,
                prepareOpcode, prepareResponseOpcode,
                dispatchOpcode, dispatchResponseOpcode
            ).all { it > 0 }
        ) { "lossless opcodes must be positive" }
        require(queryPayload.contentEquals(byteArrayOf(0))) { "lossless query payload must be 00" }
        require(minimumLevel == 1 && maximumLevel == 10) { "lossless level range must be 1..10" }
        require(serverDailyLimit == 5) { "lossless server daily limit must be five" }
        require(maximumGeneralsPerFormation == 5) { "lossless formation limit must be five" }
        require(!fullTroopsDefault) { "lossless full-troops desktop default must be false" }
        require(actionType == 0x0b) { "lossless action type must be 0x0b" }
        require(dispatchSuccessRequiresPositiveBattleId) {
            "lossless dispatch must require a positive battle id"
        }
        require(immediateRelatedLong == -1L && immediateFlags.contentEquals(byteArrayOf(0, 0, 0))) {
            "lossless immediate-dispatch suffix is invalid"
        }
        modes.validate()
        require(stageNames == listOf("卫兵", "小队长", "大队长", "头目", "首领")) {
            "lossless stage names are invalid"
        }
        level10Guard.validate(minimumLevel, maximumLevel)
        schedule.validate()
    }

    companion object {
        fun defaults() = LosslessBehaviorContract(
            statusRequestOpcode = 0x1900,
            statusResponseOpcode = 0x8900,
            catalogRequestOpcode = 0x1904,
            catalogResponseOpcode = 0x8904,
            settlementRequestOpcode = 0x1902,
            settlementResponseOpcode = 0x8902,
            lineupRequestOpcode = 0x1906,
            lineupResponseOpcode = 0x8906,
            selectRequestOpcode = 0x1908,
            selectResponseOpcode = 0x8908,
            queryPayload = byteArrayOf(0),
            minimumLevel = 1,
            maximumLevel = 10,
            serverDailyLimit = 5,
            maximumGeneralsPerFormation = 5,
            fullTroopsDefault = false,
            actionType = 0x0b,
            prepareOpcode = 0x1520,
            prepareResponseOpcode = 0x8520,
            dispatchOpcode = 0x1522,
            dispatchResponseOpcode = 0x8522,
            dispatchSuccessRequiresPositiveBattleId = true,
            immediateRelatedLong = -1L,
            immediateFlags = byteArrayOf(0, 0, 0),
            modes = LosslessModeBehaviorContract.defaults(),
            stageNames = listOf("卫兵", "小队长", "大队长", "头目", "首领"),
            level10Guard = LosslessLevel10GuardBehaviorContract.defaults(),
            schedule = LosslessScheduleBehaviorContract.defaults()
        )
    }
}

data class LosslessModeBehaviorContract(
    val cooldown: Int,
    val ready: List<Int>,
    val fighting: Int,
    val dailyDone: Int
) {
    fun validate() {
        require(cooldown == 0 && ready == listOf(1, 2) && fighting == 3 && dailyDone == 4) {
            "lossless mode mapping is invalid"
        }
    }

    companion object {
        fun defaults() = LosslessModeBehaviorContract(0, listOf(1, 2), 3, 4)
    }
}

data class LosslessLevel10GuardBehaviorContract(
    val level: Int,
    val stageId: Int,
    val stageName: String,
    val enemyCount: Int,
    val chariotTokens: List<String>,
    val catapultToken: String,
    val minimumChariots: Int,
    val lastChariotMustBeCatapult: Boolean,
    val alternateLevel: Int,
    val defaultMaxRerolls: Int,
    val maximumMaxRerolls: Int,
    val rerollDelayMinMillis: Long,
    val rerollDelayMaxMillis: Long
) {
    fun validate(minimumLevel: Int, maximumLevel: Int) {
        require(level == 10 && stageId == 0x3011 && stageName == "卫兵") {
            "lossless level-10 guard target is invalid"
        }
        require(enemyCount == 5 && minimumChariots == 3) {
            "lossless level-10 lineup thresholds are invalid"
        }
        require(chariotTokens == listOf("弩车", "投石车", "冲车") && catapultToken == "投石车") {
            "lossless chariot tokens are invalid"
        }
        require(lastChariotMustBeCatapult) { "lossless last chariot must be a catapult" }
        require(alternateLevel in minimumLevel..maximumLevel && alternateLevel != level) {
            "lossless alternate level is invalid"
        }
        require(defaultMaxRerolls in 1..maximumMaxRerolls && maximumMaxRerolls == 300) {
            "lossless reroll limits are invalid"
        }
        require(rerollDelayMinMillis > 0 && rerollDelayMaxMillis >= rerollDelayMinMillis) {
            "lossless reroll delay is invalid"
        }
    }

    companion object {
        fun defaults() = LosslessLevel10GuardBehaviorContract(
            level = 10,
            stageId = 0x3011,
            stageName = "卫兵",
            enemyCount = 5,
            chariotTokens = listOf("弩车", "投石车", "冲车"),
            catapultToken = "投石车",
            minimumChariots = 3,
            lastChariotMustBeCatapult = true,
            alternateLevel = 7,
            defaultMaxRerolls = 80,
            maximumMaxRerolls = 300,
            rerollDelayMinMillis = 1_000L,
            rerollDelayMaxMillis = 2_500L
        )
    }
}

data class LosslessScheduleBehaviorContract(
    val settlementRecheckMillis: Long,
    val fightingPollMillis: Long,
    val cooldownPollMinMillis: Long,
    val cooldownPollMaxMillis: Long,
    val rerollNextCheckMillis: Long,
    val postDispatchPollMillis: Long,
    val battleTimeoutMillis: Long
) {
    fun validate() {
        require(
            listOf(
                settlementRecheckMillis, fightingPollMillis, cooldownPollMinMillis,
                cooldownPollMaxMillis, rerollNextCheckMillis, postDispatchPollMillis,
                battleTimeoutMillis
            ).all { it > 0L }
        ) { "lossless schedule intervals must be positive" }
        require(cooldownPollMaxMillis >= cooldownPollMinMillis) {
            "lossless cooldown polling range is invalid"
        }
    }

    companion object {
        fun defaults() = LosslessScheduleBehaviorContract(
            settlementRecheckMillis = 500L,
            fightingPollMillis = 20_000L,
            cooldownPollMinMillis = 5_000L,
            cooldownPollMaxMillis = 60_000L,
            rerollNextCheckMillis = 4_000L,
            postDispatchPollMillis = 20_000L,
            battleTimeoutMillis = 900_000L
        )
    }
}

data class DungeonBehaviorContract(
    val catalogRequestOpcode: Int,
    val catalogResponseOpcode: Int,
    val stateRequestOpcode: Int,
    val stateResponseOpcode: Int,
    val rewardRequestOpcode: Int,
    val rewardResponseOpcode: Int,
    val battlePollRequestOpcode: Int,
    val battlePollResponseOpcode: Int,
    val chestRequestOpcode: Int,
    val chestResponseOpcode: Int,
    val maximumGeneralsPerFormation: Int,
    val actionType: Int,
    val singlePlayerType: Int,
    val prepareOpcode: Int,
    val prepareResponseOpcode: Int,
    val dispatchOpcode: Int,
    val dispatchResponseOpcode: Int,
    val immediateRelatedLong: Long,
    val immediateFlags: ByteArray,
    val allowedModes: List<String>,
    val defaultMode: String,
    val chestNames: List<String>,
    val uncompletedResultCode: Int,
    val clearModeSkipsMultiplayerFinals: Boolean,
    val clearModeRequiresCatalogConfirmation: Boolean,
    val clearModePausesOnDefeat: Boolean,
    val defeatMarkers: List<String>,
    val launchSuccessMarkers: List<String>,
    val staticStageCodes: Map<Int, List<Int>>,
    val schedule: DungeonScheduleBehaviorContract
) {
    fun validate() {
        require(
            listOf(
                catalogRequestOpcode, catalogResponseOpcode, stateRequestOpcode,
                stateResponseOpcode, rewardRequestOpcode, rewardResponseOpcode,
                battlePollRequestOpcode, battlePollResponseOpcode, chestRequestOpcode,
                chestResponseOpcode, prepareOpcode, prepareResponseOpcode,
                dispatchOpcode, dispatchResponseOpcode
            ).all { it > 0 }
        ) { "dungeon opcodes must be positive" }
        require(maximumGeneralsPerFormation == 5) { "dungeon formation limit must be five" }
        require(actionType == 0x0e && singlePlayerType == 4) {
            "dungeon expedition type is invalid"
        }
        require(immediateRelatedLong == -1L && immediateFlags.contentEquals(byteArrayOf(0, 0, 0))) {
            "dungeon immediate-dispatch suffix is invalid"
        }
        require(allowedModes == listOf("loop", "clear") && defaultMode in allowedModes) {
            "dungeon modes are invalid"
        }
        require(chestNames == listOf("左", "中", "右")) { "dungeon chest names are invalid" }
        require(uncompletedResultCode == 0xff) { "dungeon uncompleted result code must be 255" }
        require(
            clearModeSkipsMultiplayerFinals &&
                clearModeRequiresCatalogConfirmation &&
                clearModePausesOnDefeat
        ) { "dungeon clear-mode safety rules must remain enabled" }
        require(defeatMarkers.isNotEmpty() && launchSuccessMarkers.isNotEmpty()) {
            "dungeon result markers must not be empty"
        }
        require(staticStageCodes == defaultDungeonStageCodes()) {
            "dungeon static stage-code fallback differs from desktop"
        }
        schedule.validate()
    }

    companion object {
        fun defaults() = DungeonBehaviorContract(
            catalogRequestOpcode = 0x1930,
            catalogResponseOpcode = 0x8930,
            stateRequestOpcode = 0x1938,
            stateResponseOpcode = 0x8938,
            rewardRequestOpcode = 0x193d,
            rewardResponseOpcode = 0x893d,
            battlePollRequestOpcode = 0x1702,
            battlePollResponseOpcode = 0x8702,
            chestRequestOpcode = 0x193e,
            chestResponseOpcode = 0x893e,
            maximumGeneralsPerFormation = 5,
            actionType = 0x0e,
            singlePlayerType = 4,
            prepareOpcode = 0x1520,
            prepareResponseOpcode = 0x8520,
            dispatchOpcode = 0x1522,
            dispatchResponseOpcode = 0x8522,
            immediateRelatedLong = -1L,
            immediateFlags = byteArrayOf(0, 0, 0),
            allowedModes = listOf("loop", "clear"),
            defaultMode = "loop",
            chestNames = listOf("左", "中", "右"),
            uncompletedResultCode = 0xff,
            clearModeSkipsMultiplayerFinals = true,
            clearModeRequiresCatalogConfirmation = true,
            clearModePausesOnDefeat = true,
            defeatMarkers = listOf("战败", "挑战失败", "战斗失败", "副本失败"),
            launchSuccessMarkers = listOf("单人副本启动成功"),
            staticStageCodes = defaultDungeonStageCodes(),
            schedule = DungeonScheduleBehaviorContract.defaults()
        )
    }
}

data class DungeonScheduleBehaviorContract(
    val postLaunchPollMillis: Long,
    val battlePollMillis: Long,
    val battleTimeoutMillis: Long,
    val postCompletionMillis: Long,
    val waitingUnlockMillis: Long,
    val dailyDonePollMillis: Long
) {
    fun validate() {
        require(
            listOf(
                postLaunchPollMillis, battlePollMillis, battleTimeoutMillis,
                postCompletionMillis, waitingUnlockMillis, dailyDonePollMillis
            ).all { it > 0L }
        ) { "dungeon schedule intervals must be positive" }
    }

    companion object {
        fun defaults() = DungeonScheduleBehaviorContract(
            postLaunchPollMillis = 10_000L,
            battlePollMillis = 2_000L,
            battleTimeoutMillis = 480_000L,
            postCompletionMillis = 500L,
            waitingUnlockMillis = 60_000L,
            dailyDonePollMillis = 60_000L
        )
    }
}

private fun defaultDungeonStageCodes(): Map<Int, List<Int>> = mapOf(
    0 to (listOf(0, 1, 2) + (4..12)),
    1 to (listOf(3) + (13..23)),
    2 to (24..37).toList(),
    3 to (38..51).toList(),
    4 to (52..62).toList(),
    5 to (63..74).toList(),
    6 to (75..85).toList()
)

data class MilitarySnapshotBehaviorContract(
    val requestOpcode: Int,
    val responseOpcode: Int,
    val requestPayload: ByteArray
) {
    companion object {
        fun defaults(): MilitarySnapshotBehaviorContract = MilitarySnapshotBehaviorContract(
            requestOpcode = 0x1600,
            responseOpcode = 0x8600,
            requestPayload = "07000000000000000000000014".hexBytes()
        )
    }
}

data class DailyScheduleBehaviorContract(
    val failedFeatureRetryMillis: Long,
    val completedFeatureSleep: String
) {
    companion object {
        fun defaults(): DailyScheduleBehaviorContract = DailyScheduleBehaviorContract(
            failedFeatureRetryMillis = 60_000L,
            completedFeatureSleep = "nextChinaDay"
        )
    }
}

data class SignInBehaviorContract(
    val requestOpcode: Int,
    val activityResponseOpcode: Int,
    val legacyResponseOpcode: Int,
    val successMarkers: List<String>,
    val duplicateMarkers: List<String>,
    val duplicateMessage: String,
    val confirmedMessage: String,
    val diamondBox: DiamondBoxBehaviorContract
) {
    val acceptedResponseOpcodes: Set<Int>
        get() = setOf(activityResponseOpcode, legacyResponseOpcode)

    companion object {
        fun defaults(): SignInBehaviorContract = SignInBehaviorContract(
            requestOpcode = 0x6202,
            activityResponseOpcode = 0x8134,
            legacyResponseOpcode = 0xE202,
            successMarkers = listOf("获得成功", "签到成功", "领取成功"),
            duplicateMarkers = listOf("本日已签到"),
            duplicateMessage = "自动签到重复，本日已签到，明日再签到！",
            confirmedMessage = "签到请求已由服务器确认",
            diamondBox = DiamondBoxBehaviorContract.defaults()
        )
    }
}

data class DiamondBoxBehaviorContract(
    val requestOpcode: Int,
    val responseOpcode: Int,
    val payload: ByteArray,
    val expiredMarkers: List<String>,
    val duplicateMarkers: List<String>,
    val alreadyClaimedMessage: String
) {
    companion object {
        fun defaults(): DiamondBoxBehaviorContract = DiamondBoxBehaviorContract(
            requestOpcode = 0x1134,
            responseOpcode = 0x8134,
            payload = "00000000000de2b100".hexBytes(),
            expiredMarkers = listOf("活动已过期"),
            duplicateMarkers = listOf("已经领取", "已领取", "重复领取"),
            alreadyClaimedMessage = "每日金钻宝箱已经领取过了！"
        )
    }
}

data class SignInReceipt(
    val success: Boolean,
    val message: String,
    val alreadyClaimed: Boolean,
    val duplicateClaim: Boolean,
    val responseOpcode: Int?,
    val serverMessage: String = ""
)

data class DiamondBoxReceipt(
    val success: Boolean,
    val message: String,
    val alreadyClaimed: Boolean,
    val serverMessage: String = ""
)

object DailySignInReceiptParser {
    fun parse(
        responseOpcodes: List<Int>,
        payload: ByteArray,
        contract: SignInBehaviorContract = SignInBehaviorContract.defaults()
    ): SignInReceipt {
        if (contract.activityResponseOpcode in responseOpcodes) {
            val rawText = payload.toString(Charsets.UTF_8)
            val trailing = payload.trailingUtf()
            val duplicate = contract.duplicateMarkers.firstOrNull { marker ->
                marker in rawText || marker in trailing
            }
            if (duplicate != null) {
                return SignInReceipt(
                    success = true,
                    message = contract.duplicateMessage,
                    alreadyClaimed = true,
                    duplicateClaim = true,
                    responseOpcode = contract.activityResponseOpcode,
                    serverMessage = duplicate
                )
            }
            if (trailing.isNotBlank() && contract.successMarkers.any { it in trailing }) {
                return SignInReceipt(
                    success = true,
                    message = trailing.cleanActivityMessage(),
                    alreadyClaimed = false,
                    duplicateClaim = false,
                    responseOpcode = contract.activityResponseOpcode,
                    serverMessage = trailing
                )
            }
            return SignInReceipt(
                success = false,
                message = if (trailing.isBlank()) {
                    "收到 0x${contract.activityResponseOpcode.toString(16)} 签到响应，但未找到成功或已签到标记"
                } else {
                    "签到响应未能识别：${trailing.cleanActivityMessage()}"
                },
                alreadyClaimed = false,
                duplicateClaim = false,
                responseOpcode = contract.activityResponseOpcode,
                serverMessage = trailing
            )
        }

        if (contract.legacyResponseOpcode in responseOpcodes) {
            if (payload.isEmpty()) {
                return SignInReceipt(
                    success = true,
                    message = contract.confirmedMessage,
                    alreadyClaimed = false,
                    duplicateClaim = false,
                    responseOpcode = contract.legacyResponseOpcode
                )
            }
            val receipt = runCatching { DailyProtocolShapes.parseStatusMessage(payload) }.getOrElse {
                return SignInReceipt(
                    success = false,
                    message = "签到回执解析失败：${it.message}",
                    alreadyClaimed = false,
                    duplicateClaim = false,
                    responseOpcode = contract.legacyResponseOpcode
                )
            }
            return SignInReceipt(
                success = receipt.success,
                message = receipt.message.ifBlank {
                    if (receipt.success) contract.confirmedMessage else "签到失败：状态=${receipt.status}"
                },
                alreadyClaimed = false,
                duplicateClaim = false,
                responseOpcode = contract.legacyResponseOpcode,
                serverMessage = receipt.message
            )
        }

        return SignInReceipt(
            success = false,
            message = "未收到可识别的签到响应（0x${contract.legacyResponseOpcode.toString(16)}/0x${contract.activityResponseOpcode.toString(16)}）",
            alreadyClaimed = false,
            duplicateClaim = false,
            responseOpcode = null
        )
    }

    fun parseDiamondBox(
        payload: ByteArray,
        contract: SignInBehaviorContract = SignInBehaviorContract.defaults()
    ): DiamondBoxReceipt {
        val box = contract.diamondBox
        val rawText = payload.toString(Charsets.UTF_8)
        val trailing = payload.trailingUtf()
        val combined = "$rawText\n$trailing"
        if (box.expiredMarkers.any { it in combined } ||
            box.duplicateMarkers.any { it in combined }
        ) {
            return DiamondBoxReceipt(
                success = true,
                message = box.alreadyClaimedMessage,
                alreadyClaimed = true,
                serverMessage = trailing.ifBlank { rawText.cleanActivityMessage() }
            )
        }
        if (trailing.isNotBlank() && contract.successMarkers.any { it in trailing }) {
            return DiamondBoxReceipt(
                success = true,
                message = trailing.cleanActivityMessage(),
                alreadyClaimed = false,
                serverMessage = trailing
            )
        }
        val status = runCatching { DailyProtocolShapes.parseStatusMessage(payload) }.getOrNull()
        return DiamondBoxReceipt(
            success = status?.success == true,
            // Keep the desktop's generic success wording when the server sends
            // a blank status message; the caller supplies the localized fallback.
            message = status?.message.orEmpty().ifBlank {
                if (status?.success == true) "" else "每日金钻宝箱回执无法确认"
            },
            alreadyClaimed = false,
            serverMessage = status?.message.orEmpty()
        )
    }
}

private fun String.parseOpcode(): Int = removePrefix("0x").removePrefix("0X").toInt(16)

private fun org.json.JSONArray.stringList(): List<String> =
    (0 until length()).map { getString(it) }

private fun org.json.JSONArray.intList(): List<Int> =
    (0 until length()).map { getInt(it) }

private fun String.hexBytes(): ByteArray {
    val normalized = filterNot(Char::isWhitespace)
    require(normalized.length % 2 == 0) { "hex length must be even" }
    return ByteArray(normalized.length / 2) { index ->
        normalized.substring(index * 2, index * 2 + 2).toInt(16).toByte()
    }
}

private fun ByteArray.trailingUtf(): String {
    for (offset in size - 2 downTo 0) {
        val length = ((this[offset].toInt() and 0xff) shl 8) or
            (this[offset + 1].toInt() and 0xff)
        if (offset + 2 + length != size) continue
        val message = runCatching {
            copyOfRange(offset + 2, size).toString(Charsets.UTF_8)
        }.getOrDefault("").trim()
        if (message.isNotBlank()) return message
    }
    return ""
}

private fun String.cleanActivityMessage(): String =
    replace(Regex("(?i)<br\\s*/?>"), "；")
        .replace(Regex("<[^>]+>"), "")
        .split(Regex("[。；;]+"))
        .map(String::trim)
        .filter(String::isNotBlank)
        .joinToString("；")
