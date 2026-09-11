package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.protocol.TaskType
import com.example.dwpmclone.ui.web.LocalSettingsConfigMapper
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CommonMainUiConfigMappingTest {
    @Test
    fun desktopFrequentFieldsControlMaintenanceAndExpeditionPolicy() {
        val configs = JSONObject().put(
            "77::general",
            feature(
                JSONObject()
                    .put("healWounded", false)
                    .put("autoEnergy", true)
                    .put("energyThreshold", 35)
                    .put("foodToCopper", true)
                    .put("copperFloorWan", 20)
            )
        )
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put("configs", configs)

        val plan = SavedConfigTaskPlanFactory.plan(77L, export)
        assertTrue(plan.tasks.none { it.type == TaskType.GENERAL })
        assertEquals("false", plan.session.channelExtra["expeditionHealWounded"])
        assertEquals("35", plan.session.channelExtra["expeditionMinimumEnergy"])
        assertTrue(plan.tasks.none { it.type == TaskType.FOOD_TO_COPPER })
        assertEquals("true", plan.session.channelExtra["foodToCopperEnabled"])
        assertEquals("20", plan.session.channelExtra["copperFloorWan"])
    }

    @Test
    fun commonMainGeneralMapsButHistoricalCaptiveFieldsAreIgnoredForDesktopParity() {
        val configs = JSONObject()
            .put(
                "77::general",
                feature(
                    JSONObject()
                        .put("APKTOOL_RENAMED_0x7f070032", true)
                        .put("APKTOOL_RENAMED_0x7f07002d", true)
                        .put("APKTOOL_RENAMED_0x7f070028", 35)
                        .put("APKTOOL_RENAMED_0x7f070031", true)
                )
            )
            .put(
                "77::surrender_release",
                feature(
                    JSONObject()
                        .put("APKTOOL_RENAMED_0x7f07006b", true)
                        .put("APKTOOL_RENAMED_0x7f07008b", 80)
                        .put("APKTOOL_RENAMED_0x7f07008d", false)
                        .put("APKTOOL_RENAMED_0x7f07006d", true)
                        .put("APKTOOL_RENAMED_0x7f07008c", 45)
                )
            )
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put("configs", configs)

        val plan = SavedConfigTaskPlanFactory.plan(77L, export)

        assertTrue(plan.tasks.none { it.type == TaskType.GENERAL })
        assertEquals("true", plan.session.channelExtra["expeditionHealWounded"])
        assertEquals("true", plan.session.channelExtra["expeditionAutoEnergy"])
        assertEquals("35", plan.session.channelExtra["expeditionMinimumEnergy"])
    }

    @Test
    fun technologyOnlySelectionFeedsSharedResidentWithoutKotlinTask() {
        val values = JSONObject()
            .put("enabled", false)
            .put("upgradeTechnology", true)
            .put("technologyIds", JSONArray().put(5).put(8).put(13))
        val configs = JSONObject().put(
            "77::internal_affairs",
            feature(values)
        )
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put("configs", configs)

        val tasks = SavedConfigTaskPlanFactory.plan(77L, export).tasks
        val domestic = LocalSettingsConfigMapper.accountHabits {
            if (it == LocalSettingsConfigMapper.INTERNAL) values else null
        }.getJSONObject("config").getJSONObject("domestic")

        assertTrue(tasks.none { it.type == TaskType.INTERNAL })
        assertFalse(domestic.getBoolean("enabled"))
        assertTrue(domestic.getBoolean("upgradeTechnology"))
        assertEquals(3, domestic.getJSONArray("technologyIds").length())
    }

    @Test
    fun desktopUpgradeBuildingsSwitchIsPreservedIndependentlyFromAutoDomestic() {
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put(
                "configs",
                JSONObject().put(
                    "77::internal_affairs",
                    feature(
                        JSONObject()
                            .put("enabled", true)
                            .put("upgradeBuildings", false)
                            .put("emptyBuildingType", 1)
                    )
                )
            )

        val tasks = SavedConfigTaskPlanFactory.plan(77L, export).tasks
        val values = export.getJSONObject("configs")
            .getJSONObject("77::internal_affairs")
            .getJSONObject("values")
        val domestic = LocalSettingsConfigMapper.accountHabits {
            if (it == LocalSettingsConfigMapper.INTERNAL) values else null
        }.getJSONObject("config").getJSONObject("domestic")

        assertTrue(tasks.none { it.type == TaskType.INTERNAL })
        assertTrue(domestic.getBoolean("enabled"))
        assertFalse(domestic.getBoolean("upgradeBuildings"))
    }

    private fun feature(values: JSONObject): JSONObject =
        JSONObject().put("values", values)
}
