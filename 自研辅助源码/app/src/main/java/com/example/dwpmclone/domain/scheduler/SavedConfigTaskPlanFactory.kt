package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.config.ConfigDefaults
import com.example.dwpmclone.domain.model.*
import org.json.JSONObject

/**
 * Builds a local scheduling task plan from LocalConfigRepository export JSON.
 *
 * The original APK's proprietary config schema is still hidden in the packed DEX.
 * The rebuild skeleton therefore persists raw screen-form values keyed by recovered
 * resource IDs. This mapper is intentionally explicit and conservative: it translates
 * the recovered screen IDs into typed local configs without executing production game mutations.
 */
object SavedConfigTaskPlanFactory {
    private const val DEFAULT_ACCOUNT_ID: Long = MockTaskPlanFactory.MOCK_ACCOUNT_ID

    fun accountIds(exportJson: JSONObject): List<Long> {
        val configs = exportJson.optJSONObject("configs") ?: return listOf(DEFAULT_ACCOUNT_ID)
        val ids = linkedSetOf<Long>()
        configs.keys().forEach { key ->
            key.substringBefore("::").toLongOrNull()?.let(ids::add)
        }
        return ids.ifEmpty { linkedSetOf(DEFAULT_ACCOUNT_ID) }.toList()
    }

    fun plan(accountId: Long, exportJson: JSONObject, account: GameAccount? = null): SavedTaskPlan {
        val saved = SavedFeatureConfigs.fromExport(exportJson, accountId)
        if (!saved.hasAny()) {
            return SavedTaskPlan(
                session = account.realSchedulerSessionOrNull(
                    enableBrushYellowHints = false,
                    requireCollaborativeMap = false,
                    enableMilitaryIntelHints = false
                )
                    ?: MockTaskPlanFactory.session(),
                tasks = MockTaskPlanFactory.tasks(),
                sourceDescription = "synthetic-defaults:no-saved-config"
            )
        }
        val hasBrush = saved.values("shua_huang") != null
        val hasAlarm = saved.values("alarm_withdraw") != null
        val requireCollaborativeMap = hasBrush ||
            saved.values("auto_mining", "mine_search") != null
        val session = account.realSchedulerSessionOrNull(
            enableBrushYellowHints = hasBrush,
            requireCollaborativeMap = requireCollaborativeMap,
            enableMilitaryIntelHints = hasAlarm
        )
            ?: session(accountId)
        val bundle = configBundle(accountId, saved, session)
        return SavedTaskPlan(
            session = session,
            tasks = TaskFactory.buildBackgroundTaskSet(accountId, bundle),
            sourceDescription = if (session.sourceMode == 1) {
                "real-session+saved-screen-config:${saved.featureIds().joinToString(",")}"
            } else {
                "saved-screen-config:${saved.featureIds().joinToString(",")}"
            }
        )
    }

    fun session(accountId: Long): GameSession = GameSession(
        accountId = accountId,
        tokenCiphertext = "mock-token-from-saved-config",
        expiresAtMillis = null,
        channelExtra = mapOf("source" to "saved-screen-config"),
        sourceMode = 0
    )

    private fun configBundle(accountId: Long, saved: SavedFeatureConfigs, session: GameSession): AssistantConfigBundle {
        val guaji = saved.values("guaji_start")
        val antiBan = saved.values("batch_guaji_antiban")
        val shua = saved.values("shua_huang")
        val autoMine = saved.values("auto_mining")
        val mineSearch = saved.values("mine_search")
        val daily = saved.values("daily_basic")
        val general = saved.values("general")
        val formation = saved.values("formation_troop")
        val internal = saved.values("internal_affairs")
        val sixMinistries = saved.values("six_ministries")
        val dungeon = saved.values("dungeon")
        val lossless = saved.values("military_lossless")
        val inventory = saved.values("inventory")
        val autoLoot = saved.values("auto_loot")
        val alarmWithdraw = saved.values("alarm_withdraw")

        val mineValues = autoMine ?: mineSearch
        val mineDefaults = ConfigDefaults.mine()
        val configuredMineRows = autoMine.mineRows()
        val firstMineRow = configuredMineRows.firstOrNull { it.enabled } ?: configuredMineRows.firstOrNull()

        val configuredFormationId = firstConfiguredFormationId(shua, formation, session)
        val configuredGeneralId = firstConfiguredGeneralId(formation, session) ?: configuredFormationId

        return AssistantConfigBundle(
            guaji = ConfigDefaults.guaji(accountId).copy(
                autoStart = true,
                reconnectDelaySeconds = guaji.int("APKTOOL_RENAMED_0x7f07008e", 10),
                antiIpBanEnabled = antiBan.bool("APKTOOL_RENAMED_0x7f0700fe", false),
                requestDelayMillis = antiBan.int("APKTOOL_RENAMED_0x7f0701d3", 100),
                sameServerMutex = true,
                protectBackgroundHintAcknowledged = true
            ),
            shuaHuang = shua?.let {
                ConfigDefaults.shuaHuang().copy(
                    enabled = it.bool("APKTOOL_RENAMED_0x7f070073", false),
                    dailyLimit = it.int("APKTOOL_RENAMED_0x7f070163", 500),
                    startHour = it.int("startHour", 0).coerceIn(0, 23),
                    start = MapCoordinate(
                        x = it.int("APKTOOL_RENAMED_0x7f070165", 0),
                        y = it.int("APKTOOL_RENAMED_0x7f070166", 0)
                    ),
                    minCopperWan = it.int("APKTOOL_RENAMED_0x7f070164", 0),
                    targetType = if (it.bool("APKTOOL_RENAMED_0x7f070188", false)) HuangTargetType.HUANG_JIN else HuangTargetType.SHAN_ZEI,
                    selectedFormationIds = setOf(configuredFormationId),
                    formationFilterMode = if (it.bool("APKTOOL_RENAMED_0x7f070184", false)) FormationFilterMode.PER_FORMATION else FormationFilterMode.UNIFIED,
                    replenishTroops = it.bool("replenishTroops", true),
                    deleteMailForSpeed = it.bool("APKTOOL_RENAMED_0x7f070183", false),
                    autoConvertFoodToCopper = it.bool("autoConvertFoodToCopper", true),
                    targetFilter = targetFilter(it),
                    perFormationTargetFilters = perFormationTargetFilters(it)
                )
            },
            mine = mineValues?.let {
                mineDefaults.copy(
                    enabled = autoMine.bool("enabled", autoMine.bool("APKTOOL_RENAMED_0x7f070075", false)),
                    start = MapCoordinate(
                        x = firstMineRow?.x ?: autoMine.int("APKTOOL_RENAMED_0x7f070174", 0),
                        y = firstMineRow?.y ?: autoMine.int("APKTOOL_RENAMED_0x7f070175", 0)
                    ),
                    hitEmptyMine = autoMine.bool("APKTOOL_RENAMED_0x7f070178", true),
                    // 当前电脑端打矿成功后保留占领/采集，不会立刻撤防。
                    withdrawDefense = if (autoMine != null) {
                        false
                    } else {
                        mineSearch.bool("APKTOOL_RENAMED_0x7f070172", false)
                    },
                    selectedMineTypes = selectedMineTypes(autoMine, mineSearch),
                    acceleratedMineTypes = selectedAcceleratedMineTypes(autoMine),
                    selectedFormationIds = configuredMineRows
                        .filter { row -> row.enabled }
                        .flatMapTo(linkedSetOf()) { row -> row.generalIds }
                        .ifEmpty { setOf(1L) },
                    backgroundSearch = mineSearch != null,
                    searchIntervalMinutes = mineSearch.int("APKTOOL_RENAMED_0x7f07013f", 12),
                    reloginOnDisconnect = mineSearch.bool("APKTOOL_RENAMED_0x7f070141", true),
                    stopOnDisconnect = mineSearch.bool("APKTOOL_RENAMED_0x7f070140", false),
                    vibrateOnEmptyGold = mineSearch.bool("APKTOOL_RENAMED_0x7f0700eb", true),
                    vibrateOnEmptyRare = mineSearch.bool("APKTOOL_RENAMED_0x7f0700ec", true),
                    onlyEmptyMine = mineSearch.bool("APKTOOL_RENAMED_0x7f0700ee", false),
                    onlyDefendedMine = mineSearch.bool("APKTOOL_RENAMED_0x7f0700c8", false),
                    speed = autoMine.string("speed", "不加速"),
                    fullLoyalty = autoMine.bool("fullLoyalty", true),
                    targetPlayerName = autoMine.string("targetPlayerName", "").trim(),
                    searchScope = firstMineRow?.scope ?: autoMine.string("scope", "附近"),
                    rules = configuredMineRows.mapNotNull { row ->
                        val type = mineTypeFromDesktopLabel(row.resourceType)
                            ?: return@mapNotNull null
                        MineRule(
                            enabled = row.enabled,
                            generalIds = row.generalIds,
                            mineType = type,
                            start = MapCoordinate(row.x, row.y),
                            scope = row.scope
                        )
                    }
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
                    enabled = it.bool("dailyDonateEnabled", false) ||
                        it.bool("APKTOOL_RENAMED_0x7f0700a1", false) ||
                        it.bool("APKTOOL_RENAMED_0x7f0700a0", false),
                    factorFz = it.int("dailyDonationFactorFz", 1).coerceAtLeast(1)
                )
            },
            dailySalary = daily?.let {
                DailySalaryConfig(enabled = it.bool("dailySalaryEnabled", false) ||
                    it.bool("APKTOOL_RENAMED_0x7f07009b", false))
            },
            dailyNationalCollect = daily?.let {
                DailyNationalCollectConfig(
                    enabled = it.bool("nationalCollectEnabled", false),
                    maxAttempts = it.int("nationalCollectMaxCandidates", 0).coerceAtLeast(0)
                )
            },
            dailyCityLordCollect = daily?.let {
                DailyCityLordCollectConfig(enabled = it.bool("cityLordCollectEnabled", false))
            },
            dailyGeneralVisit = daily?.let {
                DailyGeneralVisitConfig(
                    enabled = it.bool("generalVisitEnabled", false),
                    orderedGeneralIds = it.orderedLongList(
                        "generalVisitGeneralIds",
                        "generalVisitIds",
                        "selectedGeneralIds"
                    ).take(DailyGeneralVisitConfig.MAX_SELECTED)
                )
            },
            general = general?.let {
                ConfigDefaults.general().copy(
                    autoHeal = it.bool("APKTOOL_RENAMED_0x7f070032", true),
                    keepFullLoyalty = it.bool("APKTOOL_RENAMED_0x7f07002f", false),
                    autoEnergy = it.bool("APKTOOL_RENAMED_0x7f07002d", true),
                    minEnergy = it.int("APKTOOL_RENAMED_0x7f070028", 50),
                    autoRescue = it.bool("APKTOOL_RENAMED_0x7f070031", true)
                )
            },
            formations = formation?.let {
                listOf(
                    ConfigDefaults.formation(formationId = 1L).copy(
                        generalIds = listOf(configuredGeneralId).filter { it > 0L },
                        autoAssignTroops = it.bool("APKTOOL_RENAMED_0x7f070030", false),
                        troopType = it.string("APKTOOL_RENAMED_0x7f07007c", "mock-troop"),
                        troopCount = it.int("APKTOOL_RENAMED_0x7f07007b", 1999)
                    )
                )
            } ?: emptyList(),
            internalAffairs = internal?.let {
                ConfigDefaults.internalAffairs().copy(
                    enabled = it.bool("enabled", it.bool("APKTOOL_RENAMED_0x7f070070", false)),
                    upgradeLowestFirst = it.bool("upgradeLowestFirst", it.bool("APKTOOL_RENAMED_0x7f070065", true)),
                    buildWhenEmpty = it.string("buildWhenEmpty", "")
                        .let { value -> runCatching { BuildingType.valueOf(value) }.getOrNull() }
                        ?.takeUnless { type -> type == BuildingType.UNKNOWN },
                    upgradeTechnology = it.bool("upgradeTechnology", false),
                    technologyIds = it.intSet("technologyIds").ifEmpty { setOf(5) }
                )
            },
            sixMinistries = sixMinistries?.let {
                ConfigDefaults.sixMinistries().copy(
                    cropEnabled = it.bool("cropEnabled", false),
                    crop = it.string("crop", MinistryProtocolCrop.VERIFIED_NAME),
                    highPriority = it.bool("highPriority", true),
                    stealEnabled = it.bool("stealEnabled", false),
                    courtesyEnabled = it.bool("courtesyEnabled", false),
                    salaryRefresh = it.bool("salaryRefresh", false)
                )
            },
            dungeon = dungeon?.let {
                ConfigDefaults.dungeon().copy(
                    enabled = it.bool("enabled", it.bool("APKTOOL_RENAMED_0x7f07007a", false)),
                    dailyTimes = it.int("dailyTimes", it.int("APKTOOL_RENAMED_0x7f0700ca", 999)),
                    boxPosition = it.int("boxPosition", spinnerIndex(it.string("APKTOOL_RENAMED_0x7f070067", ""))),
                    chapter = it.int("chapter", spinnerIndex(it.string("APKTOOL_RENAMED_0x7f070068", ""))),
                    stage = it.int("stage", legacyDungeonStage(it.string("APKTOOL_RENAMED_0x7f070066", ""))),
                    formationIds = it.longSet("selectedGeneralIds")
                        .ifEmpty { listOf(configuredGeneralId).filter { generalId -> generalId > 0L }.toSet() }
                        .toList()
                )
            },
            lossless = lossless?.let {
                val rules = it.losslessRules()
                LosslessConfig(
                    enabled = it.bool("enabled", rules.any { rule -> rule.enabled }),
                    fullTroops = it.bool("fullTroops", true),
                    dailyLimit = it.int("dailyLimit", 5).coerceIn(1, 5),
                    rules = rules
                )
            },
            inventory = inventory?.let {
                ConfigDefaults.inventory().copy(
                    enabled = it.bool("APKTOOL_RENAMED_0x7f07006f", false),
                    openBoxes = it.bool("APKTOOL_RENAMED_0x7f070047", false),
                    openSilverTickets = it.bool("APKTOOL_RENAMED_0x7f070046", false),
                    autoOpenItemNames = it.stringSet("autoOpenItemNames", "auto_open_item_names"),
                    discardEquipmentQualities = selectedEquipmentQualities(it),
                    discardBelowLevel = it.int("APKTOOL_RENAMED_0x7f070039", 0),
                    discardItems = selectedDiscardItems(it)
                )
            },
            // 当前电脑端没有独立 VIP 配置页或执行链路。升级前保存的旧安卓 VIP
            // 键不得进入真实后台，否则只会命中 REAL_VIP_NOT_IMPLEMENTED。
            vip = null,
            // 当前电脑端俘虏两行没有保存/执行绑定；历史安卓键不得创建真实后台任务。
            surrenderRelease = null,
            // 当前电脑端“定点送将”属于打矿规则本身，由 MineConfig 的目标玩家校验和
            // 资源点出征闭环执行；旧安卓独立送将配置不得再创建第二个并行任务。
            resourcePointSendGeneral = null,
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
                    rules = rules
                )
            },
            alarmWithdraw = alarmWithdraw?.let {
                ConfigDefaults.alarmWithdraw().copy(
                    enabled = it.bool("alarm_withdraw_enabled", false),
                    keywords = it.string("alarm_keywords", "掠夺,夺取,攻城,敌军")
                        .split(',', '，', ' ')
                        .map { token -> token.trim() }
                        .filter { token -> token.isNotEmpty() }
                        .toSet(),
                    vibrateOnAlarm = it.bool("alarm_vibrate", true),
                    withdrawDefense = it.bool("alarm_withdraw_defense", false),
                    mockOnlyProtection = true,
                    incomingEnabled = it.bool("incomingEnabled", true),
                    incomingMode = it.string("incomingMode", "声音+日志"),
                    militaryEnabled = it.bool("militaryEnabled", true),
                    militaryMode = it.string("militaryMode", "出征/返回"),
                    errorEnabled = it.bool("errorEnabled", true)
                )
            },
            // 当前电脑端不存在旧安卓“令牌加统/小战鼓八卦/残缺宝藏图/一键领成就”
            // 批量工具页。保留模型供历史配置读取，但不排入当前桌面对齐计划。
            bulkTools = null
        )
    }

    private fun selectedDailySteps(values: JSONObject): Set<DailyStep> = buildSet {
        if (values.bool("APKTOOL_RENAMED_0x7f0700a2", true)) add(DailyStep.SIGN_IN)
        if (values.bool("APKTOOL_RENAMED_0x7f07009c", false)) add(DailyStep.ARENA_REWARD)
        // 捐献、俸禄、国家征收、城主征收、名将拜访均由独立任务负责，不能
        // 再混入旧 DAILY 管线，否则一个步骤失败会改变其他功能的生命周期。
        // 历史“每日兑换一半粮食”键与当前电脑端铜钱保底策略不同，禁止排入日常任务。
    }

    private fun GameAccount?.realSchedulerSessionOrNull(
        enableBrushYellowHints: Boolean,
        requireCollaborativeMap: Boolean,
        enableMilitaryIntelHints: Boolean
    ): GameSession? {
        val raw = this?.session?.takeIf { this.enabled && it.sourceMode == 1 } ?: return null
        if (!enableBrushYellowHints && !requireCollaborativeMap && !enableMilitaryIntelHints) return raw
        val additions = linkedMapOf(
            "collaborativeMapRequired" to requireCollaborativeMap.toString(),
            "collaborativeMapMode" to if (requireCollaborativeMap) {
                raw.channelExtra["collaborativeMapMode"] ?: "disabled-until-server-configured"
            } else {
                "off"
            }
        )
        if (enableBrushYellowHints) {
            additions += mapOf(
                // 保存刷黄配置后，允许调度器在没有原 APK 编队 SharedPreferences 的情况下，
                // 临时把 0x8004 解析出的真实将领视作“候选刷黄编队”。
                "allowRecoveredGeneralFallbackFormation" to "true",
                // 041540 是找黄/地图扫描查询，不是出征动作。
                "recoveredReadOnlyLiveGate" to "true"
            )
        }
        if (enableMilitaryIntelHints) {
            // 0x3110 payload 0100 is a captured, read-only heartbeat/status/system-message query.
            additions["militaryIntelLiveGate"] = "true"
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

    private fun targetFilter(values: JSONObject): ShuaHuangTargetFilter =
        ShuaHuangTargetFilter(
            minLevel = values.intOrNull("shuaHuangMinTargetLevel", "targetLevelMin", "minTargetLevel"),
            maxLevel = values.intOrNull("shuaHuangMaxTargetLevel", "targetLevelMax", "maxTargetLevel"),
            maxDistance = values.intOrNull("shuaHuangMaxDistance", "targetMaxDistance", "maxDistance"),
            maxFoot = values.intOrNull("maxFoot", "shuaHuangMaxFoot"),
            maxBow = values.intOrNull("maxBow", "shuaHuangMaxBow"),
            maxCavalry = values.intOrNull("maxCavalry", "shuaHuangMaxCavalry"),
            maxChariot = values.intOrNull("maxChariot", "shuaHuangMaxChariot"),
            dropKeywords = values.dropKeywordSet(),
            requiredKeywords = values.stringSet("shuaHuangRequiredKeywords", "targetRequiredKeywords"),
            blockedKeywords = values.stringSet("shuaHuangBlockedKeywords", "targetBlockedKeywords")
        )

    private fun perFormationTargetFilters(values: JSONObject): Map<Long, ShuaHuangTargetFilter> {
        val out = linkedMapOf<Long, ShuaHuangTargetFilter>()
        for (formationId in 0L..20L) {
            val filter = ShuaHuangTargetFilter(
                minLevel = values.intOrNull("shuaHuangFormation${formationId}MinTargetLevel", "formation${formationId}MinTargetLevel"),
                maxLevel = values.intOrNull("shuaHuangFormation${formationId}MaxTargetLevel", "formation${formationId}MaxTargetLevel"),
                maxDistance = values.intOrNull("shuaHuangFormation${formationId}MaxDistance", "formation${formationId}MaxDistance"),
                maxFoot = values.intOrNull("shuaHuangFormation${formationId}MaxFoot", "formation${formationId}MaxFoot", "maxFoot"),
                maxBow = values.intOrNull("shuaHuangFormation${formationId}MaxBow", "formation${formationId}MaxBow", "maxBow"),
                maxCavalry = values.intOrNull("shuaHuangFormation${formationId}MaxCavalry", "formation${formationId}MaxCavalry", "maxCavalry"),
                maxChariot = values.intOrNull("shuaHuangFormation${formationId}MaxChariot", "formation${formationId}MaxChariot", "maxChariot"),
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
        "牧场" -> MineType.PASTURE_LV1
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

private data class SavedMineRow(
    val enabled: Boolean,
    val generalIds: List<Long>,
    val resourceType: String,
    val x: Int,
    val y: Int,
    val scope: String
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
            level = level
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
    val array = this?.optJSONArray("mineRows") ?: return emptyList()
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
            resourceType = row.optString("resourceType", "金矿"),
            x = row.optInt("x", 0).coerceIn(0, 186),
            y = row.optInt("y", 0).coerceIn(0, 66),
            scope = row.optString("scope", "附近")
                .takeIf { it in setOf("定点", "附近", "全国") }
                ?: "附近"
        )
    }
}

private fun normalizeDropKeyword(raw: String): String? =
    when (raw.trim()) {
        "宝物", "资源", "装备", "宝箱" -> raw.trim()
        "铜钱", "粮食", "粮草", "资源类" -> "资源"
        else -> null
    }
