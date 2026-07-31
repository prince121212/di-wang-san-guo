package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.protocol.TaskType
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
        val general = plan.tasks.single { it.type == TaskType.GENERAL } as GeneralMaintenanceTask
        val conversion = plan.tasks.single { it.type == TaskType.FOOD_TO_COPPER } as FoodToCopperTask

        assertFalse(general.config.autoHeal)
        assertEquals(35, general.config.minEnergy)
        assertEquals("false", plan.session.channelExtra["expeditionHealWounded"])
        assertEquals("35", plan.session.channelExtra["expeditionMinimumEnergy"])
        assertEquals(20, conversion.config.copperFloorWan)
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

        val tasks = SavedConfigTaskPlanFactory.plan(77L, export).tasks
        val general = tasks.single { it.type == TaskType.GENERAL } as GeneralMaintenanceTask

        assertTrue(general.config.autoHeal)
        assertTrue(general.config.autoEnergy)
        assertEquals(35, general.config.minEnergy)
    }

    @Test
    fun technologyOnlySelectionCreatesRunnableInternalTaskWithSelectedIds() {
        val configs = JSONObject().put(
            "77::internal_affairs",
            feature(
                JSONObject()
                    .put("enabled", false)
                    .put("upgradeTechnology", true)
                    .put("technologyIds", JSONArray().put(5).put(8).put(13))
            )
        )
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put("configs", configs)

        val tasks = SavedConfigTaskPlanFactory.plan(77L, export).tasks
        val internal = tasks.single { it.type == TaskType.INTERNAL } as InternalAffairsTask

        assertFalse(internal.config.enabled)
        assertTrue(internal.config.upgradeTechnology)
        assertEquals(setOf(5, 8, 13), internal.config.technologyIds)
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

        val internal = SavedConfigTaskPlanFactory.plan(77L, export).tasks
            .single { it.type == TaskType.INTERNAL } as InternalAffairsTask

        assertTrue(internal.config.enabled)
        assertFalse(internal.config.upgradeBuildings)
    }

    private fun feature(values: JSONObject): JSONObject =
        JSONObject().put("values", values)
}
