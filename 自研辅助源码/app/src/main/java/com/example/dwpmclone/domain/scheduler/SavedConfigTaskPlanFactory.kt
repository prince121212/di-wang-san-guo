package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.config.ConfigDefaults
import com.example.dwpmclone.domain.model.*
import com.example.dwpmclone.domain.protocol.AssistantBehaviorContract
import org.json.JSONObject

/** Explicit mapper from persisted page values to typed local task plans. */
object SavedConfigTaskPlanFactory {
    fun accountIds(exportJson: JSONObject): List<Long> {
        val configs = exportJson.optJSONObject("configs") ?: return emptyList()
        val ids = linkedSetOf<Long>()
        configs.keys().forEach { key ->
            key.substringBefore("::").toLongOrNull()?.let(ids::add)
        }
        return ids.toList()
    }

    fun plan(
        accountId: Long,
        exportJson: JSONObject,
        account: GameAccount? = null,
        behaviorContract: AssistantBehaviorContract = AssistantBehaviorContract.defaults()
    ): SavedTaskPlan {
        val saved = SavedFeatureConfigs.fromExport(exportJson, accountId)
        if (!saved.hasAny()) {
            return SavedTaskPlan(
                session = account.realSchedulerSessionOrNull(
                    enableMapReadHints = false,
                    enableMilitaryIntelHints = false,
                    enableInventoryHints = false
                )
                    ?: inertSession(accountId),
                tasks = emptyList(),
                sourceDescription = "no-saved-config"
            )
        }
        val hasBrush = saved.values("shua_huang") != null
        val hasMine = saved.values("auto_mining", "mine_search") != null
        val hasRaid = saved.values("auto_loot") != null
        val hasMinistry = saved.values("six_ministries") != null
        val hasAlarm = saved.values("alarm_withdraw") != null
        val hasInventory = saved.values("inventory") != null
        val session = account.realSchedulerSessionOrNull(
            enableMapReadHints = hasBrush || hasMine || hasMinistry,
            enableMilitaryIntelHints = hasAlarm || hasMine || hasRaid,
            enableInventoryHints = hasMine || hasInventory
        )
            ?: inertSession(accountId)
        val runtimeSession = session.withExpeditionPolicy(saved)
        val bundle = configBundle(accountId, saved, runtimeSession)
        return SavedTaskPlan(
            session = runtimeSession,
            tasks = TaskFactory.buildBackgroundTaskSet(
                accountId,
                bundle,
                behaviorContract.scheduler
            ),
            sourceDescription = if (session.sourceMode == 1) {
                "real-session+saved-screen-config:${saved.featureIds().joinToString(",")}"
            } else {
                "saved-screen-config:${saved.featureIds().joinToString(",")}"
            }
        )
    }

    /** Production entry point: a local service plan can never synthesize an account/session. */
    fun planForRealAccount(
        account: GameAccount,
        exportJson: JSONObject,
        behaviorContract: AssistantBehaviorContract = AssistantBehaviorContract.defaults()
    ): SavedTaskPlan? {
        val session = account.session ?: return null
        if (!account.enabled || session.sourceMode != 1) return null
        val savedPlan = plan(account.id, exportJson, account, behaviorContract)
        if (savedPlan.session.sourceMode != 1) return null
        return RealSessionTaskPlanAdapter.attachRealSession(savedPlan, session)
    }

    private fun inertSession(accountId: Long): GameSession = GameSession(
        accountId = accountId,
        tokenCiphertext = "",
        expiresAtMillis = null,
        channelExtra = mapOf("source" to "inert-saved-config-plan"),
        sourceMode = 0
    )

    private fun configBundle(accountId: Long, saved: SavedFeatureConfigs, session: GameSession): AssistantConfigBundle {
        val guaji = saved.values("guaji_start")
        val shua = saved.values("shua_huang")
        val autoMine = saved.values("auto_mining")
        val mineSearch = saved.values("mine_search")
        val daily = saved.values("daily_basic")
        val general = saved.values("general")
        val formation = saved.values("formation_troop")
        val internal = saved.values("internal_affairs")
        val dungeon = saved.values("dungeon")
        val lossless = saved.values("military_lossless")
        val inventory = saved.values("inventory")
        val autoLoot = saved.values("auto_loot")
        val ministries = saved.values("six_ministries")
        val alarm = saved.values("alarm_withdraw")

        val mineValues = autoMine ?: mineSearch
        val mineDefaults = ConfigDefaults.mine()
        val autoMiningEnabled = autoMine.bool(
            "enabled",
            autoMine.bool("APKTOOL_RENAMED_0x7f070075", false)
        )
        val configuredMineRows = autoMine.mineRows()
        val firstMineRow = configuredMineRows.firstOrNull { it.enabled } ?: configuredMineRows.firstOrNull()

        val configuredFormationId = firstConfiguredFormationId(shua, formation, session)
        val configuredGeneralId = firstConfiguredGeneralId(formation, session) ?: configuredFormationId
        val configuredFormations = formation.formationConfigs(configuredGeneralId)

        return AssistantConfigBundle(
            guaji = ConfigDefaults.guaji(accountId).copy(
                autoStart = true,
                reconnectDelaySeconds = guaji.int("APKTOOL_RENAMED_0x7f07008e", 10),
                requestDelayMillis = guaji.int("requestDelayMillis", 300),
                sameServerMutex = true,
                protectBackgroundHintAcknowledged = true
            ),
            shuaHuang = shua?.let {
                val brushRules = desktopBrushRules(it)
                val selectedIds = it.longSet("selectedFormationIds")
                    .ifEmpty { brushRules.flatMapTo(linkedSetOf()) { rule -> rule.generalIds } }
                    .ifEmpty { setOf(configuredFormationId) }
                ConfigDefaults.shuaHuang().copy(
                    enabled = it.bool("enabled", it.bool("APKTOOL_RENAMED_0x7f070073", false)),
                    dailyLimit = general.int(
                        "dailyLimit",
                        it.int("dailyLimit", it.int("APKTOOL_RENAMED_0x7f070163", 500))
                    ),
                    startHour = it.int("startHour", 0).coerceIn(0, 23),
                    start = MapCoordinate(
                        x = it.int("startX", it.int("APKTOOL_RENAMED_0x7f070165", 0)),
                        y = it.int("startY", it.int("APKTOOL_RENAMED_0x7f070166", 0))
                    ),
                    minCopperWan = it.int("APKTOOL_RENAMED_0x7f070164", 0),
                    targetType = if (
                        it.string("targetKind", "山贼") == "黄巾" ||
                        it.bool("APKTOOL_RENAMED_0x7f070188", false)
                    ) HuangTargetType.HUANG_JIN else HuangTargetType.SHAN_ZEI,
                    selectedFormationIds = selectedIds,
                    formationFilterMode = if (
                        brushRules.size > 1 || selectedIds.size > 1 ||
                        it.bool("APKTOOL_RENAMED_0x7f070184", false)
                    ) FormationFilterMode.PER_FORMATION else FormationFilterMode.UNIFIED,
                    replenishTroops = it.bool("replenishTroops", true),
                    deleteMailForSpeed = it.bool("cleanMail", it.bool("APKTOOL_RENAMED_0x7f070183", false)),
                    autoConvertFoodToCopper = it.bool("foodToCopper", it.bool("autoConvertFoodToCopper", true)),
                    targetFilter = targetFilter(it),
                    perFormationTargetFilters = perFormationTargetFilters(it) + desktopBrushTargetFilters(it),
                    rules = brushRules,
                    formationRules = configuredFormations.forGenerals(selectedIds)
                )
            },
            mine = mineValues?.let {
                val centerX = autoMine.int("centerX", firstMineRow?.x ?: 91).coerceIn(0, 186)
                val centerY = autoMine.int("centerY", firstMineRow?.y ?: 26).coerceIn(0, 66)
                val center = MapCoordinate(centerX, centerY)
                mineDefaults.copy(
                    enabled = autoMiningEnabled,
                    // 电脑端的中心坐标是附近/全国搜索的起点；只有定点规则
                    // 使用表格行自己的 x/y。
                    start = center,
                    hitEmptyMine = autoMine.bool("APKTOOL_RENAMED_0x7f070178", true),
                    // The desktop configuration owns this switch.  Keep it off when
                    // absent, but do not erase an explicitly enabled withdraw rule;
                    // the real 0x1526/0x8526 adapter now handles it in the same task.
                    withdrawDefense = autoMine.bool(
                        "withdrawDefense",
                        mineSearch.bool("withdrawDefense", false)
                    ),
                    selectedMineTypes = selectedMineTypes(autoMine, mineSearch),
                    acceleratedMineTypes = selectedAcceleratedMineTypes(autoMine),
                    selectedFormationIds = configuredMineRows
                        .filter { row -> row.enabled }
                        .flatMapTo(linkedSetOf()) { row -> row.generalIds }
                        .ifEmpty { setOf(1L) },
                    backgroundSearch = !autoMiningEnabled && mineSearch?.let {
                        it.bool("enabled", it.bool("APKTOOL_RENAMED_0x7f070075", true))
                    } == true,
                    searchIntervalMinutes = mineSearch.int("APKTOOL_RENAMED_0x7f07013f", 12),
                    reloginOnDisconnect = mineSearch.bool("APKTOOL_RENAMED_0x7f070141", true),
                    stopOnDisconnect = mineSearch.bool("APKTOOL_RENAMED_0x7f070140", false),
                    vibrateOnEmptyGold = mineSearch.bool("APKTOOL_RENAMED_0x7f0700eb", true),
                    vibrateOnEmptyRare = mineSearch.bool("APKTOOL_RENAMED_0x7f0700ec", true),
                    onlyEmptyMine = mineSearch.bool("APKTOOL_RENAMED_0x7f0700ee", false),
                    onlyDefendedMine = mineSearch.bool("APKTOOL_RENAMED_0x7f0700c8", false),
                    speed = if (autoMine.mineSpeedEnabled()) "加速" else "不加速",
                    fullLoyalty = autoMine.bool("fullLoyalty", true),
                    replenishTroops = autoMine.bool("replenishTroops", true),
                    maxMarchMinutes = autoMine.int("maxMarchMinutes", 45).let { value ->
                        if (value in setOf(45, 60, 90)) value else 45
                    },
                    // Desktop automatic mining never attacks a player-owned resource
                    // point; the retired target-player field must not alter this rule.
                    targetPlayerName = "",
                    searchScope = firstMineRow?.scope ?: autoMine.string("scope", "附近"),
                    rules = configuredMineRows.mapNotNull { row ->
                        val type = mineTypeFromDesktopLabel(row.resourceType)
                            ?: return@mapNotNull null
                        MineRule(
                            enabled = row.enabled,
                            generalIds = row.generalIds,
                            mineType = type,
                            start = if (row.scope == "定点") MapCoordinate(row.x, row.y) else center,
                            scope = row.scope,
                            onlyEmpty = row.onlyEmpty,
                            onlyDefended = row.onlyDefended,
                            level = row.level
                        )
                    },
                    formationRules = configuredFormations.forGenerals(
                        configuredMineRows.filter { row -> row.enabled }
                            .flatMapTo(linkedSetOf()) { row -> row.generalIds }
                    )
                )
            },
            daily = daily?.let {
                DailyConfig(
                    enabledSteps = selectedDailySteps(it),
                    vibrateOnAlarm = it.bool("APKTOOL_RENAMED_0x7f07009e", false),
                    stopOnStepFailure = false
                )
            },
            dailyDonate = daily?.let {
                DailyDonateConfig(
                    enabled = it.dailyFlag("autoDonate") || it.bool("dailyDonateEnabled", false) ||
                        it.bool("APKTOOL_RENAMED_0x7f0700a1", false) ||
                        it.bool("APKTOOL_RENAMED_0x7f0700a0", false),
                    factorFz = it.int("dailyDonationFactorFz", 1).coerceAtLeast(1)
                )
            },
            dailySalary = daily?.let {
                DailySalaryConfig(enabled = it.dailyFlag("salary") || it.bool("dailySalaryEnabled", false) ||
                    it.bool("APKTOOL_RENAMED_0x7f07009b", false))
            },
            dailyNationalCollect = daily?.let {
                DailyNationalCollectConfig(
                    enabled = it.dailyFlag("nationalCollect") || it.bool("nationalCollectEnabled", false),
                    maxAttempts = it.int("nationalCollectMaxCandidates", 0).coerceAtLeast(0)
                )
            },
            dailyCityLordCollect = daily?.let {
                DailyCityLordCollectConfig(
                    enabled = it.dailyFlag("cityLordCollect") || it.bool("cityLordCollectEnabled", false)
                )
            },
            dailyGeneralVisit = daily?.let {
                DailyGeneralVisitConfig(
                    enabled = it.dailyFlag("generalVisit") || it.bool("generalVisitEnabled", false),
                    orderedGeneralIds = it.orderedLongList(
                        "generalVisitGeneralIds",
                        "generalVisitIds",
                        "selectedGeneralIds"
                    ).take(DailyGeneralVisitConfig.MAX_SELECTED)
                )
            },
            general = general?.let {
                ConfigDefaults.general().copy(
                    autoHeal = it.bool(
                        "healWounded",
                        it.bool("autoHeal", it.bool("APKTOOL_RENAMED_0x7f070032", true))
                    ),
                    keepFullLoyalty = it.bool("APKTOOL_RENAMED_0x7f07002f", false),
                    autoEnergy = it.bool("autoEnergy", it.bool("APKTOOL_RENAMED_0x7f07002d", true)),
                    minEnergy = it.int(
                        "energyThreshold",
                        it.int("minEnergy", it.int("APKTOOL_RENAMED_0x7f070028", 20))
                    ).coerceIn(20, 100),
                    // 共享单账号界面尚未接入俘虏营救协议，不得由历史默认值暗中启动。
                    autoRescue = it.bool("autoRescue", it.bool("APKTOOL_RENAMED_0x7f070031", false)),
                    requireChineseNamePrefix = false
                )
            },
            foodToCopper = run {
                val enabled = general.bool(
                    "foodToCopper",
                    shua.bool("foodToCopper", false)
                )
                val requestedFloor = general.int(
                    "copperFloorWan",
                    shua.int("copperFloorWan", 1)
                )
                FoodToCopperConfig(
                    enabled = enabled,
                    copperFloorWan = requestedFloor.takeIf { it in setOf(1, 10, 20, 50) } ?: 1
                )
            },
            formations = configuredFormations,
            internalAffairs = internal?.let {
                ConfigDefaults.internalAffairs().copy(
                    enabled = it.bool("enabled", it.bool("APKTOOL_RENAMED_0x7f070070", false)),
                    upgradeLowestFirst = it.bool("upgradeLowestFirst", it.bool("APKTOOL_RENAMED_0x7f070065", true)),
                    buildWhenEmpty = it.desktopBuildingType(),
                    upgradeBuildings = it.bool("upgradeBuildings", true),
                    upgradeTechnology = it.bool("upgradeTechnology", false),
                    technologyIds = it.intSet("technologyIds").ifEmpty { setOf(5) }
                )
            },
            dungeon = dungeon?.let {
                val selectedGeneralIds = it.longSet("selectedGeneralIds")
                    .ifEmpty {
                        listOf(configuredGeneralId)
                            .filter { generalId -> generalId > 0L }
                            .toSet()
                    }
                    .toList()
                ConfigDefaults.dungeon().copy(
                    enabled = it.bool("enabled", it.bool("APKTOOL_RENAMED_0x7f07007a", false)),
                    dailyTimes = it.int("dailyTimes", it.int("APKTOOL_RENAMED_0x7f0700ca", 999)),
                    boxPosition = it.int("boxPosition", spinnerIndex(it.string("APKTOOL_RENAMED_0x7f070067", ""))),
                    chapter = it.int("chapter", spinnerIndex(it.string("APKTOOL_RENAMED_0x7f070068", ""))),
                    stage = it.int("stage", legacyDungeonStage(it.string("APKTOOL_RENAMED_0x7f070066", ""))),
                    formationIds = selectedGeneralIds,
                    mode = it.string(
                        "mode",
                        if (it.bool("autoUnlockUntilTarget", false)) "clear" else "loop"
                    ).takeIf { value -> value in setOf("loop", "clear") } ?: "loop",
                    formationRules = configuredFormations.filter { rule ->
                        val ruleIds = rule.generalIds.ifEmpty { listOf(rule.formationId) }
                        ruleIds.any(selectedGeneralIds::contains)
                    }
                )
            },
            lossless = lossless?.let {
                val rules = it.losslessRules()
                LosslessConfig(
                    enabled = it.bool("enabled", rules.any { rule -> rule.enabled }),
                    fullTroops = it.bool("fullTroops", false),
                    dailyLimit = it.int("dailyLimit", 5).coerceIn(1, 5),
                    rules = rules,
                    formationRules = configuredFormations.forGenerals(
                        rules.filter { rule -> rule.enabled }
                            .flatMapTo(linkedSetOf()) { rule -> rule.generalIds }
                    )
                )
            },
            inventory = inventory?.let {
                ConfigDefaults.inventory().copy(
                    enabled = it.bool("cleanInventory", false) ||
                        it.bool("autoOpenEnabled", false) || it.bool("APKTOOL_RENAMED_0x7f07006f", false),
                    openBoxes = it.bool("autoOpenEnabled", it.bool("APKTOOL_RENAMED_0x7f070047", false)),
                    openSilverTickets = it.bool("APKTOOL_RENAMED_0x7f070046", false),
                    autoOpenItemNames = it.stringSet("autoOpenItemNames", "auto_open_item_names"),
                    discardEquipmentQualities = selectedEquipmentQualities(it) + desktopEquipmentQualities(it),
                    discardBelowLevel = it.int("maxEquipmentLevel", it.int("APKTOOL_RENAMED_0x7f070039", 0)),
                    discardItems = selectedDiscardItems(it)
                )
            },
            autoLoot = autoLoot?.let {
                val selectedIds = it.longSet("selectedGeneralIds")
                val rules = it.autoLootRules()
                val firstRule = rules.firstOrNull { rule -> rule.enabled }
                ConfigDefaults.autoLoot().copy(
                    enabled = it.bool("auto_loot_enabled", rules.any { rule -> rule.enabled }),
                    selectedFormationIds = firstRule?.generalIds?.toSet() ?: selectedIds.ifEmpty {
                        if (it.bool("auto_loot_formation_1", false)) setOf(1L) else emptySet()
                    },
                    targetKeyword = it.string("auto_loot_target_keyword", "").ifBlank { null },
                    requireSecondConfirmForRealRun = false,
                    targetPlayerName = firstRule?.playerName ?: it.string("auto_loot_target_player", ""),
                    targetFiefIndex = firstRule?.fiefIndex
                        ?: it.int("auto_loot_fief_index", 1).coerceAtLeast(1),
                    fullTroops = it.bool("fullTroops", true),
                    fullLoyalty = it.bool("fullLoyalty", false),
                    rules = rules,
                    formationRules = configuredFormations.forGenerals(
                        rules.filter { rule -> rule.enabled }
                            .flatMapTo(linkedSetOf()) { rule -> rule.generalIds }
                    )
                )
            },
            sixMinistries = ministries?.let {
                SixMinistriesConfig(
                    cropEnabled = it.bool("cropEnabled", false),
                    crop = it.string("crop", MinistryProtocolCrop.VERIFIED_NAME),
                    highPriority = it.bool("highPriority", true),
                    stealEnabled = it.bool("stealEnabled", false),
                    courtesyEnabled = it.bool("courtesyEnabled", false),
                    salaryRefresh = it.bool("salaryRefresh", false)
                )
            },
            alarm = alarm?.let {
                val incomingMode = it.string("incomingMode", "声音+日志")
                    .takeIf { mode -> mode in setOf("声音+日志", "仅日志", "关闭") }
                    ?: "声音+日志"
                val militaryMode = it.string("militaryMode", "出征/返回")
                    .takeIf { mode -> mode in setOf("出征/返回", "仅来袭", "全部") }
                    ?: "出征/返回"
                val incomingEnabled = it.bool("incomingEnabled", true) && incomingMode != "关闭"
                val militaryEnabled = it.bool("militaryEnabled", true)
                val errorEnabled = it.bool("errorEnabled", true)
                ConfigDefaults.alarm().copy(
                    enabled = it.bool("alarm_withdraw_enabled", false) ||
                        incomingEnabled || militaryEnabled || errorEnabled,
                    keywords = it.string("alarm_keywords", "掠夺,夺取,攻城,敌军")
                        .split(',', '，', ' ')
                        .map { token -> token.trim() }
                        .filter { token -> token.isNotEmpty() }
                        .toSet(),
                    vibrateOnAlarm = it.bool("alarm_vibrate", true),
                    incomingEnabled = incomingEnabled,
                    incomingMode = incomingMode,
                    militaryEnabled = militaryEnabled,
                    militaryMode = militaryMode,
                    errorEnabled = errorEnabled
                )
            }
        )
    }

    private fun GameSession.withExpeditionPolicy(saved: SavedFeatureConfigs): GameSession {
        val general = saved.values("general")
        val brush = saved.values("shua_huang")
        val mine = saved.values("auto_mining", "mine_search")
        val autoEnergy = when {
            general?.has("autoEnergy") == true -> general.optBoolean("autoEnergy", false)
            general?.has("APKTOOL_RENAMED_0x7f07002d") == true ->
                general.optBoolean("APKTOOL_RENAMED_0x7f07002d", false)
            brush?.has("autoEnergy") == true -> brush.optBoolean("autoEnergy", false)
            else -> false
        }
        val minimumEnergy = when {
            general?.has("energyThreshold") == true -> general.int("energyThreshold", 20)
            general?.has("minEnergy") == true -> general.int("minEnergy", 20)
            general?.has("APKTOOL_RENAMED_0x7f070028") == true ->
                general.int("APKTOOL_RENAMED_0x7f070028", 20)
            brush?.has("energyThreshold") == true -> brush.int("energyThreshold", 20)
            else -> 20
        }.coerceIn(1, 100)
        val healWounded = when {
            general?.has("healWounded") == true -> general.optBoolean("healWounded", true)
            general?.has("autoHeal") == true -> general.optBoolean("autoHeal", true)
            general?.has("APKTOOL_RENAMED_0x7f070032") == true ->
                general.optBoolean("APKTOOL_RENAMED_0x7f070032", true)
            else -> true
        }
        return copy(
            channelExtra = channelExtra + mapOf(
                "expeditionAutoEnergy" to autoEnergy.toString(),
                "expeditionMinimumEnergy" to minimumEnergy.toString(),
                "expeditionHealWounded" to healWounded.toString(),
                "unifiedExpeditionPreflight" to "true",
                "brushReplenishTroops" to brush.bool("replenishTroops", false).toString(),
                "mineReplenishTroops" to mine.bool("replenishTroops", false).toString(),
                "mineRequireFullLoyalty" to mine.bool("fullLoyalty", false).toString(),
                "foodToCopperEnabled" to (
                    general.bool("foodToCopper", brush.bool("foodToCopper", false))
                    ).toString(),
                "copperFloorWan" to general.int("copperFloorWan", brush.int("copperFloorWan", 1))
                    .toString()
            )
        )
    }

    private fun selectedDailySteps(values: JSONObject): Set<DailyStep> = buildSet {
        if (values.optJSONObject("dailyTasks")?.has("autoSignIn") == true) {
            if (values.dailyFlag("autoSignIn")) add(DailyStep.SIGN_IN)
        } else if (values.bool("APKTOOL_RENAMED_0x7f0700a2", true)) {
            add(DailyStep.SIGN_IN)
        }
        if (values.dailyFlag("arenaCoins") || values.bool("APKTOOL_RENAMED_0x7f07009c", false)) {
            add(DailyStep.ARENA_REWARD)
        }
        // 捐献、俸禄、国家征收、城主征收、名将拜访均由独立任务负责，不能
        // 再混入旧 DAILY 管线，否则一个步骤失败会改变其他功能的生命周期。
        // 历史“每日兑换一半粮食”键与当前电脑端铜钱保底策略不同，禁止排入日常任务。
    }

    private fun GameAccount?.realSchedulerSessionOrNull(
        enableMapReadHints: Boolean,
        enableMilitaryIntelHints: Boolean,
        enableInventoryHints: Boolean
    ): GameSession? {
        val raw = this?.session?.takeIf { this.enabled && it.sourceMode == 1 } ?: return null
        if (!enableMapReadHints && !enableMilitaryIntelHints && !enableInventoryHints) return raw
        val additions = linkedMapOf<String, String>()
        if (enableMapReadHints) {
            additions += mapOf(
                // 刷黄和打矿都使用手机本地 0x1540/0x1542 只读扫描。
                "allowRecoveredGeneralFallbackFormation" to "true",
                "recoveredReadOnlyLiveGate" to "true"
            )
        }
        if (enableMilitaryIntelHints) {
            // 0x3110 payload 0100 is a captured, read-only heartbeat/status/system-message query.
            additions["militaryIntelLiveGate"] = "true"
        }
        if (enableInventoryHints) {
            additions["inventoryLiveRefreshAllowed"] = "true"
        }
        return raw.copy(
            channelExtra = raw.channelExtra + additions
        )
    }

    private fun firstConfiguredFormationId(
        shua: JSONObject?,
        formation: JSONObject?,
        session: GameSession
    ): Long =
        shua.longOrNull("selectedFormationId", "formationId", "generalId", "selectedGeneralId")
            ?: formation.longOrNull("selectedFormationId", "formationId", "generalId", "selectedGeneralId")
            ?: firstRealGeneralId(session)
            ?: 1L

    private fun firstConfiguredGeneralId(formation: JSONObject?, session: GameSession): Long? =
        formation.longOrNull("generalId", "selectedGeneralId", "formationGeneralId")
            ?: firstRealGeneralId(session)

    private fun firstRealGeneralId(session: GameSession): Long? {
        val raw = session.channelExtra["generalsJson"] ?: session.channelExtra["jiangLingData"] ?: return null
        return runCatching {
            val text = raw.trim()
            val arr = when {
                text.startsWith("[") -> org.json.JSONArray(text)
                text.startsWith("{") -> org.json.JSONArray().put(JSONObject(text))
                else -> return@runCatching null
            }
            for (i in 0 until arr.length()) {
                val obj = arr.optJSONObject(i) ?: continue
                val id = obj.longOrNull("id", "generalId", "jiangLingId")
                if (id != null && id > 0L) return@runCatching id
            }
            null
        }.getOrNull()
    }

    private fun targetFilter(values: JSONObject): ShuaHuangTargetFilter {
        val composition = values.optJSONObject("compositionFilter")
        return ShuaHuangTargetFilter(
            levels = values.brushLevels(),
            minLevel = values.intOrNull("shuaHuangMinTargetLevel", "targetLevelMin", "minTargetLevel"),
            maxLevel = values.intOrNull("shuaHuangMaxTargetLevel", "targetLevelMax", "maxTargetLevel"),
            maxDistance = values.intOrNull("shuaHuangMaxDistance", "targetMaxDistance", "maxDistance"),
            maxFoot = values.intOrNull("maxFoot", "shuaHuangMaxFoot")
                ?: composition.intOrNull("maxFoot"),
            maxBow = values.intOrNull("maxBow", "shuaHuangMaxBow")
                ?: composition.intOrNull("maxBow"),
            maxCavalry = values.intOrNull("maxCavalry", "shuaHuangMaxCavalry")
                ?: composition.intOrNull("maxCavalry"),
            maxChariot = values.intOrNull("maxChariot", "shuaHuangMaxChariot")
                ?: composition.intOrNull("maxChariot"),
            requireFoot = when {
                values.has("requireFoot") -> values.optBoolean("requireFoot", false)
                composition?.has("requireFoot") == true -> composition.optBoolean("requireFoot", false)
                else -> false
            },
            dropKeywords = values.dropKeywordSet(),
            requiredKeywords = values.stringSet("shuaHuangRequiredKeywords", "targetRequiredKeywords"),
            blockedKeywords = values.stringSet("shuaHuangBlockedKeywords", "targetBlockedKeywords")
        )
    }

    private fun desktopBrushTargetFilters(values: JSONObject): Map<Long, ShuaHuangTargetFilter> {
        val rows = values.optJSONArray("rows") ?: return emptyMap()
        val out = linkedMapOf<Long, ShuaHuangTargetFilter>()
        for (index in 0 until rows.length()) {
            val row = rows.optJSONObject(index)?.takeIf { it.optBoolean("enabled", false) } ?: continue
            val filter = targetFilter(row)
            row.optJSONArray("generalIds")?.let { ids ->
                for (idIndex in 0 until ids.length()) {
                    ids.optLong(idIndex).takeIf { it > 0L }?.let { out[it] = filter }
                }
            }
        }
        return out
    }

    private fun desktopBrushRules(values: JSONObject): List<ShuaHuangRule> {
        val rows = values.optJSONArray("rows") ?: return emptyList()
        return buildList {
            for (index in 0 until rows.length()) {
                val row = rows.optJSONObject(index)
                    ?.takeIf { it.optBoolean("enabled", false) }
                    ?: continue
                val generalIds = row.orderedLongList("generalIds")
                if (generalIds.isNotEmpty()) {
                    add(
                        ShuaHuangRule(
                            enabled = true,
                            generalIds = generalIds,
                            targetFilter = targetFilter(row)
                        )
                    )
                }
            }
        }
    }

    private fun perFormationTargetFilters(values: JSONObject): Map<Long, ShuaHuangTargetFilter> {
        val out = linkedMapOf<Long, ShuaHuangTargetFilter>()
        for (formationId in 0L..20L) {
            val filter = ShuaHuangTargetFilter(
                levels = values.intSet("shuaHuangFormation${formationId}Levels"),
                minLevel = values.intOrNull("shuaHuangFormation${formationId}MinTargetLevel", "formation${formationId}MinTargetLevel"),
                maxLevel = values.intOrNull("shuaHuangFormation${formationId}MaxTargetLevel", "formation${formationId}MaxTargetLevel"),
                maxDistance = values.intOrNull("shuaHuangFormation${formationId}MaxDistance", "formation${formationId}MaxDistance"),
                maxFoot = values.intOrNull("shuaHuangFormation${formationId}MaxFoot", "formation${formationId}MaxFoot", "maxFoot"),
                maxBow = values.intOrNull("shuaHuangFormation${formationId}MaxBow", "formation${formationId}MaxBow", "maxBow"),
                maxCavalry = values.intOrNull("shuaHuangFormation${formationId}MaxCavalry", "formation${formationId}MaxCavalry", "maxCavalry"),
                maxChariot = values.intOrNull("shuaHuangFormation${formationId}MaxChariot", "formation${formationId}MaxChariot", "maxChariot"),
                requireFoot = values.optBoolean("shuaHuangFormation${formationId}RequireFoot", values.optBoolean("requireFoot", false)),
                dropKeywords = values.dropKeywordSet(),
                requiredKeywords = values.stringSet("shuaHuangFormation${formationId}RequiredKeywords", "formation${formationId}RequiredKeywords"),
                blockedKeywords = values.stringSet("shuaHuangFormation${formationId}BlockedKeywords", "formation${formationId}BlockedKeywords")
            )
            if (filter != ShuaHuangTargetFilter()) out[formationId] = filter
        }
        return out
    }

    private fun selectedMineTypes(autoMine: JSONObject?, mineSearch: JSONObject?): Set<MineType> {
        val desktopRowTypes = autoMine.mineRows()
            .filter { it.enabled }
            .mapNotNullTo(linkedSetOf()) { row -> mineTypeFromDesktopLabel(row.resourceType) }
        if (desktopRowTypes.isNotEmpty()) return desktopRowTypes
        return buildSet {
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f070179", MineType.GOLD, true)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f070181", MineType.SILVER)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f070176", MineType.BING_YU)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f07017f", MineType.XIAN_ZHI)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f070180", MineType.XUAN_TIE)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f070182", MineType.YU_LU)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f07017d", MineType.PASTURE_LV1)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f07017b", MineType.PASTURE_LV2)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f07017c", MineType.PASTURE_LV3)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f07017e", MineType.CRYSTAL)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f07017a", MineType.LING_CAO)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f070171", MineType.BIN_TIE)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f070173", MineType.JIANG_GUO)
        addIfChecked(mineSearch, "APKTOOL_RENAMED_0x7f0700f4", MineType.GOLD, true)
        addIfChecked(mineSearch, "APKTOOL_RENAMED_0x7f0701d4", MineType.SILVER)
        addIfChecked(mineSearch, "APKTOOL_RENAMED_0x7f0700a7", MineType.BING_YU)
        addIfChecked(mineSearch, "APKTOOL_RENAMED_0x7f0701d1", MineType.XIAN_ZHI)
        addIfChecked(mineSearch, "APKTOOL_RENAMED_0x7f0701d2", MineType.XUAN_TIE)
        addIfChecked(mineSearch, "APKTOOL_RENAMED_0x7f0701d5", MineType.YU_LU)
        addIfChecked(mineSearch, "APKTOOL_RENAMED_0x7f07018a", MineType.CRYSTAL)
        addIfChecked(mineSearch, "APKTOOL_RENAMED_0x7f0700f7", MineType.LING_CAO)
        }.ifEmpty { setOf(MineType.GOLD) }
    }

    private fun mineTypeFromDesktopLabel(value: String): MineType? = when (value.trim()) {
        "金矿" -> MineType.GOLD
        "银矿" -> MineType.SILVER
        "冰玉矿" -> MineType.BING_YU
        "仙芝园" -> MineType.XIAN_ZHI
        "玄铁矿" -> MineType.XUAN_TIE
        "玉露园" -> MineType.YU_LU
        "水晶矿" -> MineType.CRYSTAL
        "灵草园" -> MineType.LING_CAO
        "牧场", "一级牧场" -> MineType.PASTURE_LV1
        "二级牧场" -> MineType.PASTURE_LV2
        "三级牧场" -> MineType.PASTURE_LV3
        "镔铁矿" -> MineType.BIN_TIE
        "浆果园" -> MineType.JIANG_GUO
        else -> runCatching { MineType.valueOf(value.trim()) }.getOrNull()
    }

    private fun selectedAcceleratedMineTypes(autoMine: JSONObject?): Set<MineType> = buildSet {
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f070168", MineType.GOLD, true)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f07016f", MineType.SILVER)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f070167", MineType.BING_YU)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f07016d", MineType.XIAN_ZHI)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f07016e", MineType.XUAN_TIE)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f070170", MineType.YU_LU)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f07016a", MineType.PASTURE_LV2)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f07016b", MineType.PASTURE_LV3)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f07016c", MineType.CRYSTAL)
        addIfChecked(autoMine, "APKTOOL_RENAMED_0x7f070169", MineType.LING_CAO)
    }

    private fun selectedEquipmentQualities(values: JSONObject): Set<EquipmentQuality> = buildSet {
        addIfChecked(values, "APKTOOL_RENAMED_0x7f070051", EquipmentQuality.NORMAL)
        addIfChecked(values, "APKTOOL_RENAMED_0x7f070050", EquipmentQuality.GOOD)
        addIfChecked(values, "APKTOOL_RENAMED_0x7f070053", EquipmentQuality.EXCELLENT)
        addIfChecked(values, "APKTOOL_RENAMED_0x7f070054", EquipmentQuality.SUPERB)
    }

    private fun selectedDiscardItems(values: JSONObject): Set<String> {
        val idToName = linkedMapOf(
            "APKTOOL_RENAMED_0x7f070049" to "青铜宝箱",
            "APKTOOL_RENAMED_0x7f070040" to "精铁宝箱",
            "APKTOOL_RENAMED_0x7f070038" to "传音符",
            "APKTOOL_RENAMED_0x7f070048" to "青铜钥匙",
            "APKTOOL_RENAMED_0x7f070052" to "山贼头巾",
            "APKTOOL_RENAMED_0x7f07003e" to "火药桶",
            "APKTOOL_RENAMED_0x7f07004d" to "屯田令",
            "APKTOOL_RENAMED_0x7f07004c" to "通商令",
            "APKTOOL_RENAMED_0x7f070045" to "令牌",
            "APKTOOL_RENAMED_0x7f070035" to "镔铁",
            "APKTOOL_RENAMED_0x7f07003f" to "浆果",
            "APKTOOL_RENAMED_0x7f07004b" to "水晶",
            "APKTOOL_RENAMED_0x7f070044" to "灵草",
            "APKTOOL_RENAMED_0x7f07003b" to "高级通商令",
            "APKTOOL_RENAMED_0x7f07003c" to "高级屯田令",
            "APKTOOL_RENAMED_0x7f07004f" to "战鼓",
            "APKTOOL_RENAMED_0x7f070034" to "八卦图",
            "APKTOOL_RENAMED_0x7f07004e" to "小还丹",
            "APKTOOL_RENAMED_0x7f07003d" to "活血丹",
            "APKTOOL_RENAMED_0x7f070037" to "重置丹",
            "APKTOOL_RENAMED_0x7f07004a" to "神农符",
            "APKTOOL_RENAMED_0x7f070036" to "财神符",
            "APKTOOL_RENAMED_0x7f070042" to "鲁公手册",
            "APKTOOL_RENAMED_0x7f070043" to "鲁公图册",
            "APKTOOL_RENAMED_0x7f070041" to "鲁公古籍"
        )
        return values.stringSet("discardItems", "discardItemNames").toMutableSet().apply {
            addAll(idToName.entries.filter { (id, _) -> values.bool(id, false) }.map { it.value })
        }
    }

    private fun <T> MutableSet<T>.addIfChecked(values: JSONObject?, id: String, value: T, default: Boolean = false) {
        if (values != null && values.bool(id, default)) add(value)
    }

    private fun spinnerIndex(value: String): Int = value.filter { it.isDigit() }.toIntOrNull() ?: 0

    private fun legacyDungeonStage(value: String): Int {
        val number = value.filter(Char::isDigit).toIntOrNull() ?: return 1
        return if (value.contains("关")) number.coerceAtLeast(1) else number + 1
    }
}

data class SavedTaskPlan(
    val session: GameSession,
    val tasks: List<com.example.dwpmclone.domain.protocol.AssistantTask<*>>,
    val sourceDescription: String
)

private class SavedFeatureConfigs(private val byFeature: Map<String, JSONObject>) {
    fun hasAny(): Boolean = byFeature.isNotEmpty()
    fun featureIds(): Set<String> = byFeature.keys

    fun values(vararg featureIds: String): JSONObject? {
        for (featureId in featureIds) {
            val values = byFeature[featureId]?.optJSONObject("values")
            if (values != null) return values
        }
        return null
    }

    companion object {
        fun fromExport(exportJson: JSONObject, accountId: Long): SavedFeatureConfigs {
            val configs = exportJson.optJSONObject("configs") ?: return SavedFeatureConfigs(emptyMap())
            val map = linkedMapOf<String, JSONObject>()
            configs.keys().forEach { key ->
                val prefix = "$accountId::"
                if (key.startsWith(prefix)) {
                    val featureId = key.removePrefix(prefix)
                    map[featureId] = configs.optJSONObject(key) ?: JSONObject()
                }
            }
            return SavedFeatureConfigs(map)
        }
    }
}

private fun JSONObject?.bool(id: String, default: Boolean): Boolean =
    this?.takeIf { it.has(id) && !it.isNull(id) }?.optBoolean(id, default) ?: default

private fun JSONObject?.dailyFlag(id: String): Boolean =
    this?.optJSONObject("dailyTasks")?.optBoolean(id, false) == true

private fun JSONObject?.mineSpeedEnabled(): Boolean {
    val raw = this?.takeIf { it.has("speed") && !it.isNull("speed") }?.opt("speed")
        ?: return false
    return when (raw) {
        is Boolean -> raw
        is Number -> raw.toInt() != 0
        else -> raw.toString().trim() !in setOf("", "不加速", "false", "0")
    }
}

private fun JSONObject?.int(id: String, default: Int): Int =
    this?.takeIf { it.has(id) && !it.isNull(id) }?.optString(id)?.toIntOrNull() ?: default

private fun JSONObject?.longSet(id: String): Set<Long> {
    val array = this?.optJSONArray(id) ?: return emptySet()
    return buildSet {
        for (index in 0 until array.length()) {
            array.optLong(index).takeIf { it > 0L }?.let(::add)
        }
    }
}

/** Reads the first present JSON array without sorting; UI order is the visit priority. */
private fun JSONObject?.orderedLongList(vararg ids: String): List<Long> {
    val obj = this ?: return emptyList()
    for (id in ids) {
        val array = obj.optJSONArray(id) ?: continue
        return buildList {
            for (index in 0 until array.length()) {
                array.optLong(index).takeIf { it > 0L }?.let(::add)
            }
        }.distinct()
    }
    return emptyList()
}

private fun JSONObject?.intSet(id: String): Set<Int> {
    val array = this?.optJSONArray(id) ?: return emptySet()
    return buildSet {
        for (index in 0 until array.length()) {
            array.optInt(index, -1).takeIf { it >= 0 }?.let(::add)
        }
    }
}

/** Desktop accepts `levels` as an array/string and legacy `level` as one value. */
private fun JSONObject?.brushLevels(): Set<Int> {
    val obj = this ?: return emptySet()
    val raw = mutableListOf<String>()
    obj.optJSONArray("levels")?.let { array ->
        for (index in 0 until array.length()) raw += array.optString(index)
    }
    if (raw.isEmpty() && obj.has("levels") && !obj.isNull("levels")) {
        raw += obj.optString("levels").split(',', '，', ';', '；', '|', ' ')
    }
    if (raw.isEmpty() && obj.has("level") && !obj.isNull("level")) {
        raw += obj.optString("level")
    }
    return raw.asSequence()
        .mapNotNull { it.trim().toIntOrNull() }
        .filter { it in 1..10 }
        .toSortedSet()
}

private fun JSONObject?.intOrNull(vararg ids: String): Int? {
    val obj = this ?: return null
    for (id in ids) {
        if (obj.has(id) && !obj.isNull(id)) {
            obj.optString(id).toIntOrNull()?.let { return it }
        }
    }
    return null
}

private fun JSONObject?.longOrNull(vararg ids: String): Long? {
    val obj = this ?: return null
    for (id in ids) {
        if (obj.has(id) && !obj.isNull(id)) {
            obj.optString(id).toLongOrNull()?.let { return it }
        }
    }
    return null
}

private fun JSONObject?.string(id: String, default: String): String =
    this?.takeIf { it.has(id) && !it.isNull(id) }?.optString(id)?.takeIf { it.isNotBlank() } ?: default

private fun JSONObject?.stringSet(vararg ids: String): Set<String> {
    val obj = this ?: return emptySet()
    for (id in ids) {
        if (obj.has(id) && !obj.isNull(id)) {
            obj.optJSONArray(id)?.let { array ->
                return buildSet {
                    for (index in 0 until array.length()) {
                        array.optString(index).trim().takeIf { it.isNotEmpty() }?.let(::add)
                    }
                }
            }
            return obj.optString(id)
                .split(',', '，', ';', '；', '|', ' ')
                .map { it.trim() }
                .filter { it.isNotEmpty() }
                .toSet()
        }
    }
    return emptySet()
}

private fun JSONObject?.dropKeywordSet(): Set<String> {
    val obj = this ?: return emptySet()
    val rawValues = mutableListOf<String>()
    obj.optJSONArray("drops")?.let { arr ->
        for (i in 0 until arr.length()) rawValues += arr.optString(i)
        return rawValues.mapNotNull { normalizeDropKeyword(it) }.toSet()
    }
    rawValues += obj.optString("drop").orEmpty().split(',', '，', ';', '；', '|', ' ')
    if (rawValues.any { it.trim() == "不限" }) return setOf("宝物", "资源", "装备", "宝箱")
    return rawValues.mapNotNull { normalizeDropKeyword(it) }.toSet()
}

private fun List<FormationConfig>.forGenerals(generalIds: Collection<Long>): List<FormationConfig> {
    val selected = generalIds.filter { it > 0L }.toSet()
    if (selected.isEmpty()) return emptyList()
    return filter { rule ->
        rule.generalIds.ifEmpty { listOf(rule.formationId) }.any(selected::contains)
    }
}

private fun JSONObject?.formationConfigs(fallbackGeneralId: Long): List<FormationConfig> {
    val values = this ?: return emptyList()
    val rows = values.optJSONArray("rows")
    if (rows != null) {
        val configs = (0 until rows.length()).mapNotNull { index ->
            val row = rows.optJSONObject(index)?.takeIf { it.optBoolean("enabled", false) }
                ?: return@mapNotNull null
            val generalIds = buildList {
                row.optJSONArray("generalIds")?.let { ids ->
                    for (itemIndex in 0 until ids.length()) {
                        ids.optLong(itemIndex).takeIf { it > 0L }?.let(::add)
                    }
                }
                if (isEmpty()) row.optLong("generalId").takeIf { it > 0L }?.let(::add)
            }.distinct().take(5)
            if (generalIds.isEmpty()) return@mapNotNull null
            ConfigDefaults.formation(formationId = generalIds.first()).copy(
                generalIds = generalIds,
                autoAssignTroops = true,
                troopType = row.optString("soldierType", "轻骑兵"),
                troopCount = row.optInt("soldierCount", 0).coerceAtLeast(1),
                fillToMaxWhenAutoAssignDisabled = false
            )
        }
        if (!values.optBoolean("clearOtherGenerals", false) || configs.isEmpty()) return configs
        val selectedIds = configs.flatMap(FormationConfig::generalIds).toSet()
        return configs.mapIndexed { index, config ->
            if (index == 0) config.copy(clearOtherGeneralIds = selectedIds) else config
        }
    }
    return listOf(
        ConfigDefaults.formation(formationId = 1L).copy(
            generalIds = listOf(fallbackGeneralId).filter { it > 0L },
            autoAssignTroops = values.bool("APKTOOL_RENAMED_0x7f070030", false),
            troopType = values.string("APKTOOL_RENAMED_0x7f07007c", ""),
            troopCount = values.int("APKTOOL_RENAMED_0x7f07007b", 1999)
        )
    )
}

private fun JSONObject.desktopBuildingType(): BuildingType? {
    string("buildWhenEmpty", "")
        .let { value -> runCatching { BuildingType.valueOf(value) }.getOrNull() }
        ?.takeUnless { it == BuildingType.UNKNOWN }
        ?.let { return it }
    return when (int("emptyBuildingType", -1)) {
        1 -> BuildingType.HOUSE
        2 -> BuildingType.FOOD
        3 -> BuildingType.ACADEMY
        4 -> BuildingType.INFANTRY_CAMP
        5 -> BuildingType.ARCHER_CAMP
        6 -> BuildingType.CHARIOT_CAMP
        8 -> BuildingType.CAVALRY_CAMP
        else -> null
    }
}

private fun desktopEquipmentQualities(values: JSONObject): Set<EquipmentQuality> {
    if (!values.optBoolean("discardEquipment", false)) return emptySet()
    return when (values.optString("maxEquipmentQuality", "良好")) {
        "普通" -> setOf(EquipmentQuality.NORMAL)
        "良好" -> setOf(EquipmentQuality.NORMAL, EquipmentQuality.GOOD)
        "优秀" -> setOf(EquipmentQuality.NORMAL, EquipmentQuality.GOOD, EquipmentQuality.EXCELLENT)
        "卓越", "极品" -> EquipmentQuality.entries.toSet()
        else -> emptySet()
    }
}

private data class SavedMineRow(
    val enabled: Boolean,
    val generalIds: List<Long>,
    val resourceType: String,
    val x: Int,
    val y: Int,
    val scope: String,
    val level: Int?,
    val onlyEmpty: Boolean,
    val onlyDefended: Boolean
)

private fun JSONObject?.losslessRules(): List<LosslessRule> {
    val array = this?.optJSONArray("rows") ?: return emptyList()
    return (0 until array.length()).mapNotNull { index ->
        val row = array.optJSONObject(index) ?: return@mapNotNull null
        val ids = buildList {
            row.optJSONArray("generalIds")?.let { generalIds ->
                for (itemIndex in 0 until generalIds.length()) {
                    generalIds.optLong(itemIndex).takeIf { it > 0L }?.let(::add)
                }
            }
            if (isEmpty()) row.optLong("generalId").takeIf { it > 0L }?.let(::add)
        }
        val level = row.optString("level")
            .ifBlank { row.optString("option") }
            .filter(Char::isDigit)
            .toIntOrNull()
            ?.coerceIn(1, 10)
            ?: 10
        LosslessRule(
            enabled = row.optBoolean("enabled", false),
            generalIds = ids,
            level = level,
            maxLineupRerolls = row.optInt("maxLineupRerolls", 80).coerceIn(1, 300)
        )
    }
}

private fun JSONObject?.autoLootRules(): List<AutoLootRule> {
    val array = this?.optJSONArray("rows") ?: return emptyList()
    return (0 until array.length()).mapNotNull { index ->
        val row = array.optJSONObject(index) ?: return@mapNotNull null
        val ids = buildList {
            row.optJSONArray("generalIds")?.let { generalIds ->
                for (itemIndex in 0 until generalIds.length()) {
                    generalIds.optLong(itemIndex).takeIf { it > 0L }?.let(::add)
                }
            }
            if (isEmpty()) row.optLong("generalId").takeIf { it > 0L }?.let(::add)
        }.distinct()
        AutoLootRule(
            enabled = row.optBoolean("enabled", false),
            generalIds = ids,
            playerName = row.optString("playerName").trim(),
            fiefIndex = row.optInt("fiefIndex", 1).coerceAtLeast(1)
        )
    }
}

private fun JSONObject?.mineRows(): List<SavedMineRow> {
    val array = this?.optJSONArray("rows") ?: this?.optJSONArray("mineRows") ?: return emptyList()
    return (0 until array.length()).mapNotNull { index ->
        val row = array.optJSONObject(index) ?: return@mapNotNull null
        val generalIds = buildList {
            row.optJSONArray("generalIds")?.let { ids ->
                for (itemIndex in 0 until ids.length()) {
                    ids.optLong(itemIndex).takeIf { it > 0L }?.let(::add)
                }
            }
            if (isEmpty()) {
                row.optString("generalId").toLongOrNull()
                    ?.takeIf { it > 0L }
                    ?.let(::add)
            }
        }.distinct()
        SavedMineRow(
            enabled = row.optBoolean("enabled", false),
            generalIds = generalIds,
            resourceType = row.optString("resourceType", "镔铁矿"),
            x = row.optInt("x", 0).coerceIn(0, 186),
            y = row.optInt("y", 0).coerceIn(0, 66),
            scope = row.optString("scope", "附近")
                .takeIf { it in setOf("定点", "附近", "全国") }
                ?: "附近",
            level = row.optInt("level", 0).takeIf { it > 0 },
            onlyEmpty = row.optBoolean("onlyEmpty", false),
            onlyDefended = row.optBoolean("onlyDefended", false)
        )
    }
}

private fun normalizeDropKeyword(raw: String): String? =
    when (raw.trim()) {
        "宝物", "资源", "装备", "宝箱" -> raw.trim()
        "铜钱", "粮食", "粮草", "资源类" -> "资源"
        else -> null
    }
