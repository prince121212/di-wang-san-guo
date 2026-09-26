package com.example.dwpmclone.ui.web

import org.json.JSONArray
import org.json.JSONObject

data class LocalSettingsMapping(
    val configs: Map<String, JSONObject>,
    val disabled: Boolean
)

/** Host-only projection from shared-core configs back to the shared Web habit view. */
object LocalSettingsConfigMapper {
    const val FORMATION = "formation_troop"
    const val BRUSH = "shua_huang"
    const val GENERAL = "general"
    const val INTERNAL = "internal_affairs"
    const val DAILY = "daily_basic"
    const val INVENTORY = "inventory"
    const val CHAIN_INVENTORY = "chain_inventory"
    const val ALARM = "alarm_withdraw"
    const val RAID = "auto_loot"
    const val MINE = "auto_mining"
    const val MINISTRIES = "six_ministries"
    const val CAPTIVES = "captives"
    const val LOSSLESS = "military_lossless"
    const val DUNGEON = "dungeon"

    fun accountHabits(loadValues: (String) -> JSONObject?): JSONObject {
        val habits = JSONObject()
        loadValues(FORMATION)?.let { values ->
            habits.put("formations", values.copyArray("rows"))
            habits.put(
                "formationOptions",
                JSONObject().put("clearOtherGenerals", values.optBoolean("clearOtherGenerals", false))
            )
        }
        loadValues(RAID)?.let { habits.put("raid", it.copy()) }
        loadValues(MINE)?.let { habits.put("mine", it.copy()) }
        loadValues(MINISTRIES)?.let { habits.put("ministry", it.copy()) }
        loadValues(CAPTIVES)?.let { habits.put("captives", it.copy()) }

        val militaryFuture = JSONObject()
        loadValues(LOSSLESS)?.let { militaryFuture.put("lossless", it.copy()) }
        loadValues(DUNGEON)?.let { militaryFuture.put("dungeon", it.copy()) }
        listOf("escort", "treasure").forEach { feature ->
            loadValues("military_future_$feature")?.let { militaryFuture.put(feature, it.copy()) }
        }
        if (militaryFuture.length() > 0) habits.put("militaryFuture", militaryFuture)

        val config = JSONObject()
        loadValues(BRUSH)?.let { brush ->
            config.put("autoStart", brush.optBoolean("enabled", false))
            copyPresent(brush, config, "startHour", "dailyLimit", "replenishTroops", "foodToCopper", "copperFloorWan", "cleanMail")
            config.put(
                "brush",
                JSONObject()
                    .put("startX", brush.optInt("startX", 0))
                    .put("startY", brush.optInt("startY", 0))
                    .put("scanLimit", brush.optInt("scanLimit", 160).let { if (it == 80) 160 else it })
                    .put("targetKind", brush.optString("targetKind", "山贼"))
                    .put("rows", brush.copyArray("rows"))
                    .put("generalId", brush.optString("selectedFormationId"))
                    .put("generalIds", brush.copyArray("selectedFormationIds"))
                    .put("levels", brush.copyArray("levels"))
                    .put("drops", brush.copyArray("drops"))
                    .put("compositionCode", brush.optString("compositionCode"))
                    .put("compositionFilter", brush.optJSONObject("compositionFilter")?.copy() ?: JSONObject())
            )
        }
        loadValues(GENERAL)?.let { general ->
            habits.put(
                "general",
                JSONObject()
                    .put(
                        "autoHeal",
                        general.optBoolean(
                            "autoHeal",
                            general.optBoolean("healWounded", true)
                        )
                    )
                    .put("autoEnergy", general.optBoolean("autoEnergy", true))
                    .put(
                        "minEnergy",
                        general.optInt(
                            "minEnergy",
                            general.optInt("energyThreshold", 20)
                        )
                    )
                    .put(
                        "keepFullLoyalty",
                        general.optBoolean(
                            "keepFullLoyalty",
                            general.optBoolean("APKTOOL_RENAMED_0x7f07002f", false)
                        )
                    )
                    .put("autoRescue", general.optBoolean("autoRescue", false))
                    .put("foodToCopper", general.optBoolean("foodToCopper", false))
                    .put("copperFloorWan", general.optInt("copperFloorWan", 1))
            )
            config.put("healWounded", general.optBoolean("autoHeal", true))
            config.put("autoEnergy", general.optBoolean("autoEnergy", true))
            config.put("energyThreshold", general.optInt("minEnergy", 20))
            copyPresent(general, config, "foodToCopper", "copperFloorWan", "dailyLimit")
        }
        loadValues(INTERNAL)?.let { internal ->
            config.put(
                "domestic",
                JSONObject()
                    .put("enabled", internal.optBoolean("enabled", false))
                    .put("emptyBuildingType", internal.optInt("emptyBuildingType", 1))
                    .put("upgradeBuildings", internal.optBoolean("upgradeBuildings", true))
                    .put("upgradeLowestFirst", internal.optBoolean("upgradeLowestFirst", true))
                    .put("buildingPriority", internal.copyArray("buildingPriority"))
                    .put("upgradeTechnology", internal.optBoolean("upgradeTechnology", false))
                    .put("technologyIds", internal.copyArray("technologyIds"))
            )
        }
        loadValues(DAILY)?.let { daily ->
            config.put("dailyTasks", daily.optJSONObject("dailyTasks")?.copy() ?: JSONObject())
            config.put("generalVisitGeneralIds", daily.copyArray("generalVisitGeneralIds"))
        }
        loadValues(INVENTORY)?.let { inventory ->
            copyPresent(
                inventory,
                config,
                "cleanInventory",
                "discardItemNames",
                "discardEquipment",
                "maxEquipmentQuality",
                "discardEquipmentQualities",
                "maxEquipmentLevel",
                "autoOpenEnabled",
                "autoOpenItemNames"
            )
        }
        loadValues(CHAIN_INVENTORY)?.let { config.put("chainInventory", it.copy()) }
        loadValues(ALARM)?.let { alarm ->
            config.put(
                "alarm",
                JSONObject()
                    .put("incomingEnabled", alarm.optBoolean("incomingEnabled", false))
                    .put("incomingMode", alarm.optString("incomingMode", "声音+日志"))
                    .put(
                        "incomingKeywords",
                        if (alarm.has("incomingKeywords") && !alarm.isNull("incomingKeywords")) {
                            alarm.opt("incomingKeywords")
                        } else {
                            alarm.optString("alarm_keywords", "掠夺,夺取,攻城,敌军,来袭")
                        }
                    )
                    .put("militaryEnabled", alarm.optBoolean("militaryEnabled", false))
                    .put("militaryMode", alarm.optString("militaryMode", "出征/返回"))
                    .put("errorEnabled", alarm.optBoolean("errorEnabled", false))
                    .put("vibrateOnAlarm", alarm.optBoolean("vibrateOnAlarm", alarm.optBoolean("alarm_vibrate", true)))
            )
        }
        if (config.length() > 0) habits.put("config", config)
        return habits
    }

    private fun copyPresent(source: JSONObject, target: JSONObject, vararg keys: String) {
        keys.forEach { key -> if (source.has(key) && !source.isNull(key)) target.put(key, source.opt(key)) }
    }

    private fun JSONObject.copy(): JSONObject = JSONObject(toString())
    private fun JSONObject.copyArray(key: String): JSONArray =
        optJSONArray(key)?.let { JSONArray(it.toString()) } ?: JSONArray()
}
