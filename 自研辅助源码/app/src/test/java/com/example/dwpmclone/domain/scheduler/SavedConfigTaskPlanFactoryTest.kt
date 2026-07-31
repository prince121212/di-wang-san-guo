package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.model.Channel
import com.example.dwpmclone.domain.model.DailyStep
import com.example.dwpmclone.domain.model.GameAccount
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.GameVersion
import com.example.dwpmclone.domain.model.MineType
import com.example.dwpmclone.domain.protocol.TaskType
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SavedConfigTaskPlanFactoryTest {
    @Test
    fun formationRulesAreNotScheduledAsAGlobalPrerequisite() {
        val rows = org.json.JSONArray()
            .put(JSONObject().put("enabled", true).put("generalId", 7).put("soldierType", "轻骑兵").put("soldierCount", 100))
            .put(JSONObject().put("enabled", true).put("generalId", 8).put("soldierType", "弓兵").put("soldierCount", 200))
        val values = JSONObject()
            .put("clearOtherGenerals", true)
            .put("rows", rows)
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put("configs", JSONObject().put("123::formation_troop", JSONObject().put("values", values)))

        val plan = SavedConfigTaskPlanFactory.plan(123L, export)
        assertTrue(plan.tasks.none { it.type == TaskType.FORMATION })
        assertEquals(listOf(TaskType.STATE_REFRESH), plan.tasks.map { it.type })
    }

    @Test
    fun alarmPageFieldsMapToRuntimeAlertPolicy() {
        val values = JSONObject()
            .put("alarm_withdraw_enabled", true)
            .put("incomingEnabled", true)
            .put("incomingMode", "仅日志")
            .put("militaryEnabled", true)
            .put("militaryMode", "全部")
            .put("errorEnabled", false)
            .put("alarm_keywords", "掠夺,攻城")
            .put("alarm_vibrate", false)
            .put("alarm_withdraw_defense", false)
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put("configs", JSONObject()
                .put("123::alarm_withdraw", JSONObject().put("values", values))
            )
        val account = GameAccount(
            id = 123L,
            displayName = "测试君主",
            username = "u",
            serverName = "S1",
            serverId = "1",
            gameVersion = GameVersion.TENCENT_CLASSIC,
            channel = Channel.QQ,
            session = GameSession(
                accountId = 123L,
                tokenCiphertext = "real",
                expiresAtMillis = null,
                channelExtra = mapOf(
                    "userId" to "u",
                    "serverUrl" to "http://game.example",
                    "dm" to "1"
                ),
                sourceMode = 1
            ),
            enabled = true
        )

        val plan = SavedConfigTaskPlanFactory.plan(123L, export, account)
        val task = plan.tasks.first { it.type == TaskType.ALARM } as AlarmTask

        assertEquals("true", plan.session.channelExtra["militaryIntelLiveGate"])
        assertEquals(setOf("掠夺", "攻城"), task.config.keywords)
        assertEquals("仅日志", task.config.incomingMode)
        assertTrue(task.config.militaryEnabled)
        assertEquals("全部", task.config.militaryMode)
        assertEquals(false, task.config.errorEnabled)
    }

    @Test
    fun alarmSubSwitchesEnableRuntimeWithoutLegacyMasterFlag() {
        val values = JSONObject()
            .put("incomingEnabled", false)
            .put("militaryEnabled", true)
            .put("errorEnabled", false)
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put(
                "configs",
                JSONObject().put("123::alarm_withdraw", JSONObject().put("values", values))
            )

        val task = SavedConfigTaskPlanFactory.plan(123L, export)
            .tasks.single { it.type == TaskType.ALARM } as AlarmTask

        assertTrue(task.config.enabled)
        assertEquals(false, task.config.incomingEnabled)
        assertTrue(task.config.militaryEnabled)
    }

    @Test
    fun closedIncomingModeAndInvalidMilitaryModeUseDesktopNormalization() {
        val values = JSONObject()
            .put("incomingEnabled", true)
            .put("incomingMode", "关闭")
            .put("militaryEnabled", true)
            .put("militaryMode", "未知模式")
            .put("errorEnabled", false)
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put(
                "configs",
                JSONObject().put("123::alarm_withdraw", JSONObject().put("values", values))
            )

        val task = SavedConfigTaskPlanFactory.plan(123L, export)
            .tasks.single { it.type == TaskType.ALARM } as AlarmTask

        assertEquals(false, task.config.incomingEnabled)
        assertEquals("关闭", task.config.incomingMode)
        assertEquals("出征/返回", task.config.militaryMode)
    }

    @Test
    fun accountIdsAreReadFromSavedConfigKeys() {
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put("configs", JSONObject()
                .put("123::daily_basic", JSONObject().put("values", JSONObject()))
                .put("456::mine_search", JSONObject().put("values", JSONObject()))
            )

        assertEquals(setOf(123L, 456L), SavedConfigTaskPlanFactory.accountIds(export).toSet())
    }

    @Test
    fun legacyAndroidOnlyConfigsDoNotCreateDesktopAlignedBackgroundTasks() {
        val enabled = JSONObject()
            .put("APKTOOL_RENAMED_0x7f070077", true)
            .put("APKTOOL_RENAMED_0x7f070078", true)
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put("configs", JSONObject()
                .put("123::vip", JSONObject().put("values", enabled))
                .put("123::surrender_release", JSONObject().put("values", enabled))
                .put("123::resource_point_send_general", JSONObject().put("values", enabled))
                .put("123::bulk_tools", JSONObject().put("values", enabled))
            )

        val plan = SavedConfigTaskPlanFactory.plan(123L, export)

        assertEquals(listOf(TaskType.STATE_REFRESH), plan.tasks.map { it.type })
    }

    @Test
    fun dailyScreenConfigMapsToDailyTask() {
        val values = JSONObject()
            .put("APKTOOL_RENAMED_0x7f0700a2", true) // SIGN_IN
            .put("APKTOOL_RENAMED_0x7f07009a", false) // hidden desktop item remains disabled
            .put("APKTOOL_RENAMED_0x7f07009c", true) // ARENA_REWARD
            .put("APKTOOL_RENAMED_0x7f07009f", true) // 历史危险键应被当前计划忽略
            .put("APKTOOL_RENAMED_0x7f0700a1", true) // DONATE_COPPER
            .put("APKTOOL_RENAMED_0x7f0700a0", true) // DONATE_FOOD
            .put("APKTOOL_RENAMED_0x7f07009b", false) // SALARY remains pending
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put("configs", JSONObject()
                .put("123::daily_basic", JSONObject().put("values", values))
            )

        val plan = SavedConfigTaskPlanFactory.plan(123L, export)

        assertEquals(123L, plan.session.accountId)
        assertTrue(plan.sourceDescription.contains("daily_basic"))
        assertTrue(plan.tasks.any { it.type == TaskType.DAILY_SIGN_IN })
        assertTrue(plan.tasks.any { it.type == TaskType.DAILY_ARENA_COINS })
        assertTrue(plan.tasks.none { it.type == TaskType.DAILY })
        // Country donation is an independent daily feature.  Its three
        // endpoints must not be folded back into the legacy DAILY pipeline.
        assertTrue(plan.tasks.any { it.type == TaskType.DAILY_DONATE })
    }

    @Test
    fun shuaHuangSavedConfigUsesRealSessionAndFirstRealGeneralAsFallbackFormation() {
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put("configs", JSONObject()
                .put("6685254::shua_huang", JSONObject().put("values", JSONObject()
                    .put("APKTOOL_RENAMED_0x7f070073", true)
                    .put("startHour", 18)
                    .put("APKTOOL_RENAMED_0x7f070165", 86)
                    .put("APKTOOL_RENAMED_0x7f070166", 36)
                    .put("APKTOOL_RENAMED_0x7f070183", true)
                    .put("replenishTroops", true)
                    .put("levels", org.json.JSONArray().put(7).put(8))
                    .put(
                        "rows",
                        org.json.JSONArray().put(
                            JSONObject()
                                .put("enabled", true)
                                .put("generalIds", org.json.JSONArray().put(12886835L))
                                .put("levels", org.json.JSONArray().put(7).put(8))
                        )
                    )
                    .put("compositionCode", "5203")
                    .put("maxFoot", 5)
                    .put("maxBow", 2)
                    .put("maxCavalry", 0)
                    .put("maxChariot", 3)
                    .put("requireFoot", true)
                ))
            )
        val account = GameAccount(
            id = 6685254L,
            displayName = "东方美",
            username = "1608601",
            serverName = "周年服351区(新服)",
            serverId = "351",
            gameVersion = GameVersion.TENCENT_CLASSIC,
            channel = Channel.QQ,
            session = GameSession(
                accountId = 6685254L,
                tokenCiphertext = "real-session",
                expiresAtMillis = null,
                channelExtra = mapOf(
                    "userId" to "1608601",
                    "serverUrl" to "http://example.invalid",
                    "dm" to "1",
                    "generalsJson" to """[{"id":12886835,"name":"车1","status":0,"tili":46}]"""
                ),
                sourceMode = 1
            ),
            enabled = true
        )

        val plan = SavedConfigTaskPlanFactory.plan(6685254L, export, account)

        assertEquals(1, plan.session.sourceMode)
        assertEquals("true", plan.session.channelExtra["allowRecoveredGeneralFallbackFormation"])
        assertEquals("true", plan.session.channelExtra["recoveredReadOnlyLiveGate"])
        val shua = plan.tasks.first { it.type == TaskType.SHUA_HUANG } as ShuaHuangTask
        assertEquals(setOf(12886835L), shua.config.selectedFormationIds)
        assertEquals(18, shua.config.startHour)
        assertEquals(86, shua.config.start.x)
        assertEquals(36, shua.config.start.y)
        assertTrue(shua.config.replenishTroops)
        assertTrue(shua.config.deleteMailForSpeed)
        assertEquals(setOf(7, 8), shua.config.targetFilter.levels)
        assertEquals(listOf(12886835L), shua.config.rules.single().generalIds)
        assertEquals(setOf(7, 8), shua.config.rules.single().targetFilter.levels)
        assertEquals(5, shua.config.targetFilter.maxFoot)
        assertEquals(2, shua.config.targetFilter.maxBow)
        assertEquals(0, shua.config.targetFilter.maxCavalry)
        assertEquals(3, shua.config.targetFilter.maxChariot)
        assertTrue(shua.config.targetFilter.requireFoot)
    }

    @Test
    fun dungeonUsesSelectedRealGeneralAndConvertsStageIndexToDisplayNumber() {
        val values = JSONObject()
            .put("APKTOOL_RENAMED_0x7f07007a", true)
            .put("APKTOOL_RENAMED_0x7f070068", "0")
            .put("APKTOOL_RENAMED_0x7f070066", "2")
            .put("APKTOOL_RENAMED_0x7f070067", "2")
        val formationValues = JSONObject()
            .put("enabled", true)
            .put("rows", org.json.JSONArray().put(
                JSONObject()
                    .put("enabled", true)
                    .put("generalIds", org.json.JSONArray().put(12886835L))
                    .put("soldierType", "重步兵")
                    .put("soldierCount", 499)
            ))
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put("configs", JSONObject()
                .put("6685254::dungeon", JSONObject().put("values", values))
                .put("6685254::formation_troop", JSONObject().put("values", formationValues))
            )
        val account = GameAccount(
            id = 6685254L,
            displayName = "测试",
            username = "1608601",
            serverName = "351区",
            serverId = "351",
            gameVersion = GameVersion.TENCENT_CLASSIC,
            channel = Channel.QQ,
            session = GameSession(
                6685254L,
                "real-session",
                null,
                mapOf("generalsJson" to """[{"id":12886835,"name":"统步","status":0,"tili":46}]"""),
                1
            ),
            enabled = true
        )

        val plan = SavedConfigTaskPlanFactory.plan(6685254L, export, account)
        val dungeon = plan.tasks.first { it.type == TaskType.DUNGEON } as DungeonTask

        assertEquals(listOf(12886835L), dungeon.config.formationIds)
        assertEquals(3, dungeon.config.stage)
        assertEquals(2, dungeon.config.boxPosition)
        assertEquals(1, dungeon.config.formationRules.size)
        assertEquals("重步兵", dungeon.config.formationRules.single().troopType)
        assertEquals(499, dungeon.config.formationRules.single().troopCount)
    }

    @Test
    fun desktopMiningRowsMapToCoordinatesTypesAndRealGeneralIds() {
        val rows = org.json.JSONArray()
            .put(JSONObject()
                .put("enabled", true)
                .put("generalIds", org.json.JSONArray().put(7001L).put(7003L))
                .put("generalId", 7001)
                .put("resourceType", "冰玉矿")
                .put("x", 18)
                .put("y", 22)
                .put("scope", "定点")
            )
            .put(JSONObject()
                .put("enabled", true)
                .put("generalId", 7002)
                .put("resourceType", "银矿")
                .put("x", 19)
                .put("y", 23)
                .put("scope", "全国")
            )
        val values = JSONObject()
            .put("enabled", true)
            .put("speed", true)
            .put("fullLoyalty", false)
            .put("replenishTroops", false)
            .put("maxMarchMinutes", 60)
            .put("centerX", 91)
            .put("centerY", 26)
            .put("targetPlayerName", "")
            .put("rows", rows)
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put("configs", JSONObject()
                .put("123::auto_mining", JSONObject().put("values", values))
            )

        val plan = SavedConfigTaskPlanFactory.plan(123L, export)
        val task = plan.tasks.first { it.type == TaskType.AUTO_MINING } as MineTask

        assertTrue(task.config.enabled)
        assertEquals(91, task.config.start.x)
        assertEquals(26, task.config.start.y)
        assertEquals(setOf(7001L, 7003L, 7002L), task.config.selectedFormationIds)
        assertEquals(setOf(MineType.BING_YU, MineType.SILVER), task.config.selectedMineTypes)
        assertEquals("加速", task.config.speed)
        assertEquals(false, task.config.fullLoyalty)
        assertEquals(false, task.config.replenishTroops)
        assertEquals(60, task.config.maxMarchMinutes)
        assertEquals("", task.config.targetPlayerName)
        assertEquals("定点", task.config.searchScope)
        assertEquals(listOf(7001L, 7003L), task.config.rules[0].generalIds)
        assertEquals(18, task.config.rules[0].start.x)
        assertEquals(22, task.config.rules[0].start.y)
        assertEquals("全国", task.config.rules[1].scope)
        assertEquals(91, task.config.rules[1].start.x)
        assertEquals(26, task.config.rules[1].start.y)
        assertEquals(false, task.config.withdrawDefense)
    }

    @Test
    fun legacyAndroidMineRowsAndNamedSpeedRemainReadableAfterDesktopParityUpgrade() {
        val values = JSONObject()
            .put("enabled", true)
            .put("speed", "中级行军符")
            .put("mineRows", org.json.JSONArray().put(JSONObject()
                .put("enabled", true)
                .put("generalId", 7001L)
                .put("resourceType", "镔铁矿")
                .put("x", 12)
                .put("y", 8)
                .put("scope", "附近")
            ))
        val export = JSONObject().put(
            "configs",
            JSONObject().put("123::auto_mining", JSONObject().put("values", values))
        )

        val plan = SavedConfigTaskPlanFactory.plan(123L, export)
        val task = plan.tasks.first { it.type == TaskType.AUTO_MINING } as MineTask

        assertEquals("加速", task.config.speed)
        assertEquals(listOf(7001L), task.config.rules.single().generalIds)
        assertEquals(12, task.config.start.x)
        assertEquals(8, task.config.start.y)
    }

    @Test
    fun historicalMineSearchWithdrawFlagReachesTheProductionTaskWhenExplicitlyEnabled() {
        val values = JSONObject()
            .put("enabled", true)
            .put("withdrawDefense", true)
            .put("APKTOOL_RENAMED_0x7f070177", true)
        val export = JSONObject().put(
            "configs",
            JSONObject().put("123::mine_search", JSONObject().put("values", values))
        )

        val plan = SavedConfigTaskPlanFactory.plan(123L, export)
        val task = plan.tasks.first { it.type == TaskType.MINE_SEARCH } as MineTask

        assertEquals(true, task.config.withdrawDefense)
    }

    @Test
    fun lootRowsMapMultipleGeneralsTargetsAndFullTroopLoyaltyPolicies() {
        val rows = org.json.JSONArray()
            .put(JSONObject()
                .put("enabled", true)
                .put("generalIds", org.json.JSONArray().put(7001L).put(7002L))
                .put("playerName", "目标甲")
                .put("fiefIndex", 2)
            )
            .put(JSONObject()
                .put("enabled", true)
                .put("generalIds", org.json.JSONArray().put(8001L))
                .put("playerName", "目标乙")
                .put("fiefIndex", 3)
            )
            .put(JSONObject()
                .put("enabled", false)
                .put("generalIds", org.json.JSONArray().put(9001L))
                .put("playerName", "停用目标")
                .put("fiefIndex", 1)
            )
        val values = JSONObject()
            .put("auto_loot_enabled", true)
            .put("fullTroops", false)
            .put("fullLoyalty", true)
            .put("rows", rows)
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put("configs", JSONObject()
                .put("123::auto_loot", JSONObject().put("values", values))
            )

        val plan = SavedConfigTaskPlanFactory.plan(123L, export)
        val task = plan.tasks.first { it.type == TaskType.AUTO_LOOT } as AutoLootTask

        assertTrue(task.config.enabled)
        assertEquals(false, task.config.fullTroops)
        assertTrue(task.config.fullLoyalty)
        assertEquals(3, task.config.rules.size)
        assertEquals(listOf(7001L, 7002L), task.config.rules[0].generalIds)
        assertEquals("目标甲", task.config.rules[0].playerName)
        assertEquals(2, task.config.rules[0].fiefIndex)
        assertEquals(listOf(8001L), task.config.rules[1].generalIds)
        assertEquals(
            listOf("目标甲", "目标乙"),
            task.config.enabledRules().map { it.playerName }
        )
    }

    @Test
    fun savedSixMinistriesConfigCreatesVerifiedBackgroundTask() {
        val values = JSONObject()
            .put("cropEnabled", true)
            .put("crop", "金银花")
            .put("highPriority", false)
            .put("stealEnabled", true)
            .put("courtesyEnabled", false)
            .put("salaryRefresh", true)
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put("configs", JSONObject()
                .put("123::six_ministries", JSONObject().put("values", values))
            )

        val plan = SavedConfigTaskPlanFactory.plan(123L, export)

        assertEquals(
            listOf(TaskType.STATE_REFRESH, TaskType.SIX_MINISTRIES),
            plan.tasks.map { it.type }
        )
        val task = plan.tasks.single { it.type == TaskType.SIX_MINISTRIES } as SixMinistriesTask
        assertTrue(task.config.cropEnabled)
        assertTrue(task.config.stealEnabled)
    }
}
