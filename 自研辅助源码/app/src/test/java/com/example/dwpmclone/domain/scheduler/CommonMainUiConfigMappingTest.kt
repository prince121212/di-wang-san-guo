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
            .put("schema_version", "0.1-static-mock")
            .put("configs", configs)

        val tasks = SavedConfigTaskPlanFactory.plan(77L, export).tasks
        val general = tasks.single { it.type == TaskType.GENERAL } as GeneralMaintenanceMockTask

        assertTrue(general.config.autoHeal)
        assertTrue(general.config.autoEnergy)
        assertEquals(35, general.config.minEnergy)
        assertFalse(tasks.any { it.type == TaskType.SURRENDER_RELEASE })
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
            .put("schema_version", "0.1-static-mock")
            .put("configs", configs)

        val tasks = SavedConfigTaskPlanFactory.plan(77L, export).tasks
        val internal = tasks.single { it.type == TaskType.INTERNAL } as InternalAffairsMockTask

        assertFalse(internal.config.enabled)
        assertTrue(internal.config.upgradeTechnology)
        assertEquals(setOf(5, 8, 13), internal.config.technologyIds)
    }

    private fun feature(values: JSONObject): JSONObject =
        JSONObject().put("values", values)
}
