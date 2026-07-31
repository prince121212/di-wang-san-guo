package com.example.dwpmclone.ui.web

import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.domain.scheduler.AutoLootTask
import com.example.dwpmclone.domain.scheduler.DungeonTask
import com.example.dwpmclone.domain.scheduler.LosslessTask
import com.example.dwpmclone.domain.scheduler.MineTask
import com.example.dwpmclone.domain.scheduler.SavedConfigTaskPlanFactory
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalSettingsConfigMapperTest {
    @Test
    fun dedicatedSaveRoutesMapDirectlyIntoSchedulerFeatureConfigs() {
        val values = linkedMapOf<String, JSONObject>()
        merge(values, LocalSettingsConfigMapper.map("/api/formations/save", JSONObject()
            .put("formations", JSONArray().put(row(7L, 8L)
                .put("soldierType", "近卫兵")
                .put("soldierCount", 1800)))
            .put("formationOptions", JSONObject().put("clearOtherGenerals", false))))
        merge(values, LocalSettingsConfigMapper.map("/api/raid/execute", JSONObject()
            .put("confirm", "raid")
            .put("rows", JSONArray().put(row(7L, 8L)
                .put("playerName", "目标甲")
                .put("fiefIndex", 2)
                .put("fullTroops", false)
                .put("fullLoyalty", true)))))
        merge(values, LocalSettingsConfigMapper.map("/api/mine/save", JSONObject()
            .put("settings", JSONObject()
                .put("speed", true)
                .put("fullLoyalty", true)
                .put("replenishTroops", true)
                .put("maxMarchMinutes", 60)
                .put("centerX", 91)
                .put("centerY", 26)
                .put("rows", JSONArray().put(row(9L)
                    .put("resourceType", "镔铁矿")
                    .put("scope", "定点")
                    .put("x", 12)
                    .put("y", 8))))))
        merge(values, LocalSettingsConfigMapper.map("/api/liubu/save", JSONObject()
            .put("settings", JSONObject()
                .put("cropEnabled", true)
                .put("crop", "金银花")
                .put("highPriority", true)
                .put("stealEnabled", false)
                .put("courtesyEnabled", false)
                .put("salaryRefresh", false))))
        merge(values, LocalSettingsConfigMapper.map("/api/lossless/execute", JSONObject()
            .put("confirm", "lossless")
            .put("settings", JSONObject()
                .put("fullTroops", true)
                .put("rows", JSONArray().put(row(10L, 11L).put("level", "10级"))))))
        merge(values, LocalSettingsConfigMapper.map("/api/dungeon/execute", JSONObject()
            .put("confirm", "dungeon")
            .put("mode", "loop")
            .put("rows", JSONArray().put(row(12L)
                .put("chapter", "第四章")
                .put("stage", "5")
                .put("chest", "右")))))

        val plan = SavedConfigTaskPlanFactory.plan(123L, export(123L, values))

        assertTrue(plan.tasks.none { it.type == TaskType.FORMATION })

        val raid = plan.tasks.first { it.type == TaskType.AUTO_LOOT } as AutoLootTask
        assertEquals(listOf(7L, 8L), raid.config.rules.single().generalIds)
        assertEquals(listOf(7L, 8L), raid.config.formationRules.single().generalIds)
        assertEquals("近卫兵", raid.config.formationRules.single().troopType)
        assertEquals(1800, raid.config.formationRules.single().troopCount)
        assertFalse(raid.config.fullTroops)
        assertTrue(raid.config.fullLoyalty)

        val mine = plan.tasks.first { it.type == TaskType.AUTO_MINING } as MineTask
        assertEquals(listOf(9L), mine.config.rules.single().generalIds)
        assertEquals(12, mine.config.rules.single().start.x)
        assertEquals(60, mine.config.maxMarchMinutes)
        assertTrue(plan.tasks.any { it.type == TaskType.SIX_MINISTRIES })

        val lossless = plan.tasks.first { it.type == TaskType.LOSSLESS } as LosslessTask
        assertEquals(listOf(10L, 11L), lossless.config.rules.single().generalIds)
        assertEquals(10, lossless.config.rules.single().level)

        val dungeon = plan.tasks.first { it.type == TaskType.DUNGEON } as DungeonTask
        assertEquals(listOf(12L), dungeon.config.formationIds)
        assertEquals(3, dungeon.config.chapter)
        assertEquals(5, dungeon.config.stage)
        assertEquals(2, dungeon.config.boxPosition)
    }

    @Test
    fun scopedCommonAndBrushSavesRebuildTheFrontendHabitViewWithoutWebShadowKeys() {
        val values = linkedMapOf<String, JSONObject>()
        merge(values, LocalSettingsConfigMapper.map("/api/settings/save", JSONObject()
            .put("scope", "common.frequent")
            .put("patch", JSONObject()
                .put("dailyLimit", 320)
                .put("healWounded", true)
                .put("autoEnergy", true)
                .put("energyThreshold", 35)
                .put("foodToCopper", true)
                .put("copperFloorWan", 10)
                .put("domestic", JSONObject()
                    .put("enabled", true)
                    .put("emptyBuildingType", 3)
                    .put("upgradeTechnology", true)
                    .put("technologyIds", JSONArray().put(5).put(9))))))
        merge(values, LocalSettingsConfigMapper.map("/api/settings/save", JSONObject()
            .put("scope", "common.daily")
            .put("patch", JSONObject()
                .put("dailyTasks", JSONObject()
                    .put("autoSignIn", true)
                    .put("arenaCoins", true)
                    .put("salary", true)
                    .put("generalVisit", true))
                .put("generalVisitGeneralIds", JSONArray().put("7").put("8")))))
        merge(values, LocalSettingsConfigMapper.map("/api/settings/save", JSONObject()
            .put("scope", "common.alarm")
            .put("patch", JSONObject().put("alarm", JSONObject()
                .put("incomingEnabled", true)
                .put("incomingMode", "仅日志")
                .put("militaryEnabled", true)
                .put("militaryMode", "全部")
                .put("errorEnabled", false)))))
        merge(values, LocalSettingsConfigMapper.map("/api/settings/save", JSONObject()
            .put("scope", "brush")
            .put("patch", JSONObject()
                .put("autoStart", true)
                .put("startHour", 18)
                .put("dailyLimit", 320)
                .put("replenishTroops", true)
                .put("foodToCopper", true)
                .put("copperFloorWan", 10)
                .put("cleanMail", true)
                .put("brush", JSONObject()
                    .put("startX", 86)
                    .put("startY", 36)
                    .put("targetKind", "山贼")
                    .put("rows", JSONArray().put(row(7L, 8L)
                        .put("levels", JSONArray().put(10))
                        .put("drops", JSONArray().put("资源"))
                        .put("compositionCode", "5203")
                        .put("compositionFilter", JSONObject()
                            .put("maxFoot", 5)
                            .put("maxBow", 2)
                            .put("maxCavalry", 0)
                            .put("maxChariot", 3)
                            .put("requireFoot", true))))))))

        val habits = LocalSettingsConfigMapper.accountHabits(values::get)
        val config = habits.getJSONObject("config")
        val brush = config.getJSONObject("brush")

        assertEquals(35, config.getInt("energyThreshold"))
        assertEquals(3, config.getJSONObject("domestic").getInt("emptyBuildingType"))
        assertEquals(listOf("7", "8"), jsonStrings(config.getJSONArray("generalVisitGeneralIds")))
        assertEquals(86, brush.getInt("startX"))
        assertEquals(2, brush.getJSONArray("generalIds").length())
        assertTrue(brush.getJSONObject("compositionFilter").getBoolean("requireFoot"))
        assertTrue(values.getValue("shua_huang").getBoolean("requireFoot"))
        assertFalse(values.keys.any { it.startsWith("web_") })

        val plan = SavedConfigTaskPlanFactory.plan(123L, export(123L, values))
        assertEquals("true", plan.session.channelExtra["expeditionAutoEnergy"])
        assertEquals("35", plan.session.channelExtra["expeditionMinimumEnergy"])
        assertEquals("10", plan.session.channelExtra["copperFloorWan"])
        assertTrue(plan.tasks.any { it.type == TaskType.SHUA_HUANG })
        assertTrue(plan.tasks.any { it.type == TaskType.DAILY_SALARY })
        assertTrue(plan.tasks.any { it.type == TaskType.DAILY_GENERAL_VISIT })
        assertTrue(plan.tasks.any { it.type == TaskType.ALARM })
    }

    @Test
    fun invalidMutationPayloadsFailClosedBeforePersistence() {
        assertThrows(IllegalArgumentException::class.java) {
            LocalSettingsConfigMapper.map("/api/raid/execute", JSONObject()
                .put("confirm", "")
                .put("rows", JSONArray().put(row(7L).put("playerName", "目标").put("fiefIndex", 1))))
        }
        assertThrows(IllegalArgumentException::class.java) {
            LocalSettingsConfigMapper.map("/api/formations/save", JSONObject()
                .put("formations", JSONArray().put(row(1L, 2L, 3L, 4L, 5L, 6L)
                    .put("soldierType", "近卫兵")
                    .put("soldierCount", 100))))
        }
        val unverifiedCrop = LocalSettingsConfigMapper.map("/api/liubu/save", JSONObject()
            .put("settings", JSONObject().put("cropEnabled", true).put("crop", "草药")))
        assertFalse(unverifiedCrop.configs.getValue(LocalSettingsConfigMapper.MINISTRIES)
            .getBoolean("supportedEnabled"))

        assertThrows(IllegalArgumentException::class.java) {
            LocalSettingsConfigMapper.map("/api/military/future/save", JSONObject()
                .put("feature", "escort")
                .put("settings", JSONObject().put("enabled", true)))
        }
        assertThrows(IllegalArgumentException::class.java) {
            LocalSettingsConfigMapper.map("/api/settings/save", JSONObject()
                .put("scope", "common.chain")
                .put("patch", JSONObject().put("chainInventory", JSONObject().put("enabled", true))))
        }
    }

    private fun row(vararg ids: Long): JSONObject = JSONObject()
        .put("enabled", true)
        .put("generalIds", JSONArray().apply { ids.forEach(::put) })
        .put("generalId", ids.firstOrNull()?.toString().orEmpty())

    private fun merge(target: MutableMap<String, JSONObject>, mapping: LocalSettingsMapping) {
        target.putAll(mapping.configs)
    }

    private fun export(accountId: Long, values: Map<String, JSONObject>): JSONObject =
        JSONObject().put("configs", JSONObject().apply {
            values.forEach { (feature, json) ->
                put("$accountId::$feature", JSONObject().put("values", json))
            }
        })

    private fun jsonStrings(array: JSONArray): List<String> =
        (0 until array.length()).map(array::optString)
}
