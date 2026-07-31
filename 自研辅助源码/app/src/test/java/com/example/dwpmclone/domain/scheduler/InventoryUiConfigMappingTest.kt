package com.example.dwpmclone.domain.scheduler

import com.example.dwpmclone.domain.model.EquipmentQuality
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class InventoryUiConfigMappingTest {
    @Test
    fun desktopAlignedMainInventoryFieldsMapToTypedTaskConfig() {
        val values = JSONObject()
            .put("enabled", true)
            .put("APKTOOL_RENAMED_0x7f07006f", true)
            .put("discardItems", JSONArray(listOf("传音符", "徭役令")))
            .put("discardEquipment", true)
            .put("APKTOOL_RENAMED_0x7f070051", true)
            .put("APKTOOL_RENAMED_0x7f070050", true)
            .put("APKTOOL_RENAMED_0x7f070039", 20)
            .put("APKTOOL_RENAMED_0x7f070047", true)
            .put("APKTOOL_RENAMED_0x7f070046", false)
            .put("autoOpenItemNames", JSONArray(listOf("青铜宝箱")))
        val export = JSONObject()
            .put("schema_version", "1.0-local")
            .put(
                "configs",
                JSONObject().put(
                    "77::inventory",
                    JSONObject()
                        .put("feature_id", "inventory")
                        .put("values", values)
                )
            )

        val task = SavedConfigTaskPlanFactory.plan(77L, export).tasks
            .single { it.type == com.example.dwpmclone.domain.protocol.TaskType.INVENTORY }
            as InventoryCleanupTask

        assertEquals(setOf("传音符", "徭役令"), task.config.discardItems)
        assertEquals(setOf("青铜宝箱"), task.config.autoOpenItemNames)
        assertEquals(setOf(EquipmentQuality.NORMAL, EquipmentQuality.GOOD), task.config.discardEquipmentQualities)
        assertEquals(20, task.config.discardBelowLevel)
        assertTrue(task.config.openBoxes)
    }
}
