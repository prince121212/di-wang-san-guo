package com.example.dwpmclone.ui.web

import com.example.dwpmclone.domain.model.MinistryProtocolCrop
import org.json.JSONArray
import org.json.JSONObject

data class LocalSettingsMapping(
    val configs: Map<String, JSONObject>,
    val disabled: Boolean
)

/** Pure adapter from the shared Web form contract to scheduler-owned feature configs. */
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
    const val LOSSLESS = "military_lossless"
    const val DUNGEON = "dungeon"

    private val troopTypes = setOf(
        "民兵", "弩兵", "弓兵", "轻骑兵", "弩车", "冲城车", "轻步兵", "近卫兵",
        "重步兵", "弩骑兵", "重骑兵", "铁骑兵", "投石车", "重弩车", "强弩兵", "骁骑兵"
    )
    private val mineTypes = setOf(
        "金矿", "银矿", "冰玉矿", "仙芝园", "玄铁矿", "玉露园", "水晶矿", "灵草园",
        "牧场", "一级牧场", "二级牧场", "三级牧场", "镔铁矿", "浆果园"
    )

    fun map(route: String, body: JSONObject): LocalSettingsMapping = when (route) {
        "/api/formations/save" -> formation(body)
        "/api/raid/execute" -> raid(body)
        "/api/mine/save" -> mine(body)
        "/api/liubu/save" -> ministries(body)
        "/api/lossless/execute" -> lossless(body)
        "/api/dungeon/execute" -> dungeon(body)
        "/api/military/future/save" -> future(body)
        "/api/settings/save" -> scoped(body)
        else -> throw IllegalArgumentException("不支持的设置接口：$route")
    }

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
                    .put("scanLimit", brush.optInt("scanLimit", 80))
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
                    .put("militaryEnabled", alarm.optBoolean("militaryEnabled", false))
                    .put("militaryMode", alarm.optString("militaryMode", "出征/返回"))
                    .put("errorEnabled", alarm.optBoolean("errorEnabled", false))
            )
        }
        if (config.length() > 0) habits.put("config", config)
        return habits
    }

    private fun formation(body: JSONObject): LocalSettingsMapping {
        val rows = normalizeGeneralRows(body.optJSONArray("formations") ?: JSONArray(), max = 5) { row, enabled ->
            val troopType = row.optString("soldierType", "轻骑兵").trim()
            val troopCount = row.optInt("soldierCount", 0)
            if (enabled) {
                require(troopType in troopTypes || troopType.toIntOrNull() in 0..15) { "配兵兵种无效：$troopType" }
                require(troopCount > 0) { "启用的配兵规则兵力必须大于0" }
            }
            row.put("soldierType", troopType).put("soldierCount", troopCount.coerceAtLeast(0))
        }
        val enabled = rows.anyEnabled()
        val clearOther = body.optJSONObject("formationOptions")?.optBoolean("clearOtherGenerals", false) == true
        return LocalSettingsMapping(
            mapOf(FORMATION to JSONObject()
                .put("enabled", enabled)
                .put("clearOtherGenerals", clearOther)
                .put("rows", rows)),
            disabled = !enabled
        )
    }

    private fun raid(body: JSONObject): LocalSettingsMapping {
        require(body.optString("confirm") == "raid") { "掠夺保存缺少 confirm=raid" }
        val rows = normalizeGeneralRows(body.optJSONArray("rows") ?: JSONArray(), max = 5) { row, enabled ->
            val player = row.optString("playerName").trim()
            val fief = row.optInt("fiefIndex", 0)
            if (enabled) {
                require(player.isNotBlank()) { "启用的掠夺规则缺少玩家名称" }
                require(fief > 0) { "启用的掠夺规则封地序号必须大于0" }
            }
            row.put("playerName", player).put("fiefIndex", fief)
        }
        val first = rows.firstEnabled()
        val enabled = first != null
        return LocalSettingsMapping(
            mapOf(RAID to JSONObject()
                .put("auto_loot_enabled", enabled)
                .put("fullTroops", first?.optBoolean("fullTroops", true) ?: true)
                .put("fullLoyalty", first?.optBoolean("fullLoyalty", false) ?: false)
                .put("rows", rows)),
            disabled = !enabled
        )
    }

    private fun mine(body: JSONObject): LocalSettingsMapping {
        val source = body.optJSONObject("settings")?.copy()
            ?: throw IllegalArgumentException("打矿保存缺少 settings")
        val rows = normalizeGeneralRows(source.optJSONArray("rows") ?: JSONArray(), max = 5) { row, enabled ->
            val type = row.optString("resourceType", "镔铁矿").trim()
            val scope = row.optString("scope", "附近").trim()
            require(scope in setOf("定点", "附近", "全国")) { "打矿范围无效：$scope" }
            if (enabled) require(type in mineTypes) { "打矿资源类型无效：$type" }
            row.put("resourceType", type)
                .put("scope", scope)
                .put("x", row.optInt("x", 0).coerceIn(0, 186))
                .put("y", row.optInt("y", 0).coerceIn(0, 66))
        }
        val enabled = rows.anyEnabled()
        source.put("enabled", enabled)
            .put("centerX", source.optInt("centerX", 91).coerceIn(0, 186))
            .put("centerY", source.optInt("centerY", 26).coerceIn(0, 66))
            .put("maxMarchMinutes", source.optInt("maxMarchMinutes", 45).takeIf { it in setOf(45, 60, 90) } ?: 45)
            .put("rows", rows)
        return LocalSettingsMapping(mapOf(MINE to source), disabled = !enabled)
    }

    private fun ministries(body: JSONObject): LocalSettingsMapping {
        val values = body.optJSONObject("settings")?.copy()
            ?: throw IllegalArgumentException("六部保存缺少 settings")
        val cropEnabled = values.optBoolean("cropEnabled", false)
        val stealEnabled = values.optBoolean("stealEnabled", false)
        val requested = cropEnabled || stealEnabled ||
            values.optBoolean("courtesyEnabled", false) ||
            values.optBoolean("salaryRefresh", false)
        val supported = cropEnabled &&
            values.optString("crop", MinistryProtocolCrop.VERIFIED_NAME) == MinistryProtocolCrop.VERIFIED_NAME
        values.put("enabled", supported)
            .put("supportedEnabled", supported)
            .put("requested", requested)
        return LocalSettingsMapping(mapOf(MINISTRIES to values), disabled = !requested)
    }

    private fun lossless(body: JSONObject): LocalSettingsMapping {
        require(body.optString("confirm") == "lossless") { "无损保存缺少 confirm=lossless" }
        val source = body.optJSONObject("settings")?.copy()
            ?: throw IllegalArgumentException("无损保存缺少 settings")
        val rows = normalizeGeneralRows(source.optJSONArray("rows") ?: JSONArray(), max = 5) { row, enabled ->
            val level = row.optString("level", "10").filter(Char::isDigit).toIntOrNull() ?: 10
            if (enabled) require(level in 1..10) { "无损等级必须为1..10" }
            row.put("level", "${level.coerceIn(1, 10)}级")
        }
        val enabled = rows.anyEnabled()
        source.put("enabled", enabled)
            .put("dailyLimit", source.optInt("dailyLimit", 5).coerceIn(1, 5))
            .put("rows", rows)
        return LocalSettingsMapping(mapOf(LOSSLESS to source), disabled = !enabled)
    }

    private fun dungeon(body: JSONObject): LocalSettingsMapping {
        require(body.optString("confirm") == "dungeon") { "副本保存缺少 confirm=dungeon" }
        val mode = body.optString("mode", "loop").takeIf { it in setOf("loop", "clear") } ?: "loop"
        val rows = normalizeGeneralRows(body.optJSONArray("rows") ?: JSONArray(), max = 5)
        require(rows.countEnabled() <= 1) { "副本同一时间只能启用一条规则" }
        val active = rows.firstEnabled()
        val values = JSONObject()
            .put("enabled", active != null)
            .put("mode", mode)
            .put("autoUnlockUntilTarget", mode == "clear")
            .put("dailyTimes", body.optInt("dailyTimes", 999).coerceAtLeast(1))
            .put("rows", rows)
        if (active != null) {
            values.put("selectedGeneralIds", active.copyArray("generalIds"))
                .put("chapter", chapterIndex(active.optString("chapter", "第一章")))
                .put("stage", active.optString("stage", "1").filter(Char::isDigit).toIntOrNull()?.coerceAtLeast(1) ?: 1)
                .put("boxPosition", chestIndex(active.optString("chest", "右")))
        }
        return LocalSettingsMapping(mapOf(DUNGEON to values), disabled = active == null)
    }

    private fun future(body: JSONObject): LocalSettingsMapping {
        val feature = body.optString("feature").trim()
        val label = when (feature) {
            "escort" -> "押镖"
            "treasure" -> "寻宝"
            else -> "军事预备功能"
        }
        throw IllegalArgumentException("${label}当前版本暂不实现，设置未保存")
    }

    private fun scoped(body: JSONObject): LocalSettingsMapping {
        val scope = body.optString("scope").trim()
        val patch = body.optJSONObject("patch")?.copy()
            ?: throw IllegalArgumentException("设置保存缺少 patch")
        return when (scope) {
            "brush" -> brush(patch)
            "common.frequent" -> frequent(patch)
            "common.daily" -> LocalSettingsMapping(
                mapOf(DAILY to JSONObject()
                    .put("dailyTasks", patch.optJSONObject("dailyTasks")?.copy() ?: JSONObject())
                    .put("generalVisitGeneralIds", normalizeIds(patch.optJSONArray("generalVisitGeneralIds"), 4))),
                disabled = false
            )
            "common.items" -> LocalSettingsMapping(mapOf(INVENTORY to patch), disabled = false)
            "common.chain" -> throw IllegalArgumentException("连体物品整理当前版本暂不实现，设置未保存")
            "common.alarm" -> {
                val alarm = patch.optJSONObject("alarm")?.copy() ?: JSONObject()
                val enabled = alarm.optBoolean("incomingEnabled", false) ||
                    alarm.optBoolean("militaryEnabled", false) || alarm.optBoolean("errorEnabled", false)
                alarm.put("alarm_withdraw_enabled", enabled)
                LocalSettingsMapping(mapOf(ALARM to alarm), disabled = !enabled)
            }
            else -> throw IllegalArgumentException("未知设置 scope：$scope")
        }
    }

    private fun brush(patch: JSONObject): LocalSettingsMapping {
        val brush = patch.optJSONObject("brush") ?: JSONObject()
        val rows = normalizeGeneralRows(brush.optJSONArray("rows") ?: JSONArray(), max = 5)
        val active = rows.firstEnabled()
        val rowIds = rows.enabledGeneralIds()
        val selectedIds = if (rowIds.length() > 0) rowIds else normalizeIds(
            JSONArray().put(brush.optString("generalId")), 5
        )
        val enabled = patch.optBoolean("autoStart", active != null) && selectedIds.length() > 0
        val filter = active?.optJSONObject("compositionFilter")?.copy()
            ?: brush.optJSONObject("compositionFilter")?.copy()
            ?: JSONObject()
        val values = JSONObject()
            .put("enabled", enabled)
            .put("startHour", patch.optInt("startHour", 0).coerceIn(0, 23))
            .put("dailyLimit", patch.optInt("dailyLimit", 500).coerceIn(1, 500))
            .put("replenishTroops", patch.optBoolean("replenishTroops", false))
            .put("foodToCopper", patch.optBoolean("foodToCopper", true))
            .put("copperFloorWan", patch.optInt("copperFloorWan", 1).takeIf { it in setOf(1, 10, 20, 50) } ?: 1)
            .put("cleanMail", patch.optBoolean("cleanMail", false))
            .put("startX", brush.optInt("startX", 0).coerceIn(0, 186))
            .put("startY", brush.optInt("startY", 0).coerceIn(0, 66))
            .put("scanLimit", brush.optInt("scanLimit", 80).coerceIn(1, 384))
            .put("targetKind", brush.optString("targetKind", "山贼"))
            .put("selectedFormationIds", selectedIds)
            .put("selectedFormationId", selectedIds.optString(0))
            .put("rows", rows)
            .put("levels", active?.copyArray("levels") ?: brush.copyArray("levels"))
            .put("drops", active?.copyArray("drops") ?: brush.copyArray("drops"))
            .put("compositionCode", active?.optString("compositionCode")?.ifBlank { null }
                ?: brush.optString("compositionCode"))
            .put("compositionFilter", filter)
        listOf("maxFoot", "maxBow", "maxCavalry", "maxChariot").forEach { key ->
            values.put(key, active?.optInt(key, filter.optInt(key, 0)) ?: filter.optInt(key, 0))
        }
        values.put(
            "requireFoot",
            active?.optBoolean("requireFoot", filter.optBoolean("requireFoot", false))
                ?: filter.optBoolean("requireFoot", false)
        )
        return LocalSettingsMapping(mapOf(BRUSH to values), disabled = !enabled)
    }

    private fun frequent(patch: JSONObject): LocalSettingsMapping {
        val energy = patch.optInt("energyThreshold", 20).coerceIn(20, 100)
        val general = JSONObject()
            .put("autoHeal", patch.optBoolean("healWounded", true))
            .put("autoEnergy", patch.optBoolean("autoEnergy", true))
            .put("minEnergy", energy)
            .put("foodToCopper", patch.optBoolean("foodToCopper", true))
            .put("copperFloorWan", patch.optInt("copperFloorWan", 1).takeIf { it in setOf(1, 10, 20, 50) } ?: 1)
            .put("dailyLimit", patch.optInt("dailyLimit", 500).coerceIn(1, 500))
        val domestic = patch.optJSONObject("domestic") ?: JSONObject()
        val internal = JSONObject()
            .put("enabled", domestic.optBoolean("enabled", false))
            .put("emptyBuildingType", domestic.optInt("emptyBuildingType", 1))
            .put("upgradeBuildings", domestic.optBoolean("upgradeBuildings", true))
            .put("upgradeTechnology", domestic.optBoolean("upgradeTechnology", false))
            .put("technologyIds", normalizePositiveInts(domestic.optJSONArray("technologyIds"), 20))
        return LocalSettingsMapping(mapOf(GENERAL to general, INTERNAL to internal), disabled = false)
    }

    private fun normalizeGeneralRows(
        input: JSONArray,
        max: Int,
        enrich: (JSONObject, Boolean) -> Unit = { _, _ -> }
    ): JSONArray = JSONArray().apply {
        for (index in 0 until input.length()) {
            val row = input.optJSONObject(index)?.copy() ?: continue
            val enabled = row.optBoolean("enabled", false)
            val ids = normalizeIds(row.optJSONArray("generalIds") ?: JSONArray().put(row.opt("generalId")), max)
            if (enabled) require(ids.length() > 0) { "第${index + 1}条启用规则未选择将领" }
            row.put("enabled", enabled)
                .put("generalIds", ids)
                .put("generalId", ids.optString(0))
            enrich(row, enabled)
            put(row)
        }
    }

    private fun normalizeIds(input: JSONArray?, max: Int): JSONArray {
        val seen = linkedSetOf<Long>()
        val array = input ?: JSONArray()
        for (index in 0 until array.length()) {
            array.optString(index).trim().toLongOrNull()?.takeIf { it > 0L }?.let(seen::add)
        }
        require(seen.size <= max) { "一次最多选择${max}名将领" }
        return JSONArray().apply { seen.forEach(::put) }
    }

    private fun normalizePositiveInts(input: JSONArray?, max: Int): JSONArray {
        val seen = linkedSetOf<Int>()
        val array = input ?: JSONArray()
        for (index in 0 until array.length()) array.optInt(index, -1).takeIf { it > 0 }?.let(seen::add)
        return JSONArray().apply { seen.take(max).forEach(::put) }
    }

    private fun JSONArray.anyEnabled(): Boolean = firstEnabled() != null
    private fun JSONArray.countEnabled(): Int = (0 until length()).count { optJSONObject(it)?.optBoolean("enabled", false) == true }
    private fun JSONArray.firstEnabled(): JSONObject? =
        (0 until length()).firstNotNullOfOrNull { index ->
            optJSONObject(index)?.takeIf { it.optBoolean("enabled", false) }
        }

    private fun JSONArray.enabledGeneralIds(): JSONArray {
        val ids = linkedSetOf<Long>()
        for (index in 0 until length()) {
            val row = optJSONObject(index)?.takeIf { it.optBoolean("enabled", false) } ?: continue
            row.optJSONArray("generalIds")?.let { selected ->
                for (itemIndex in 0 until selected.length()) {
                    selected.optLong(itemIndex).takeIf { it > 0L }?.let(ids::add)
                }
            }
        }
        return JSONArray().apply { ids.forEach(::put) }
    }

    private fun chapterIndex(value: String): Int {
        value.trim().toIntOrNull()?.let { return it.coerceAtLeast(0) }
        val chinese = mapOf('一' to 0, '二' to 1, '三' to 2, '四' to 3, '五' to 4, '六' to 5)
        return value.firstNotNullOfOrNull(chinese::get) ?: 0
    }

    private fun chestIndex(value: String): Int = when (value.trim()) {
        "左", "0" -> 0
        "中", "1" -> 1
        else -> 2
    }

    private fun copyPresent(source: JSONObject, target: JSONObject, vararg keys: String) {
        keys.forEach { key -> if (source.has(key) && !source.isNull(key)) target.put(key, source.opt(key)) }
    }

    private fun JSONObject.copy(): JSONObject = JSONObject(toString())
    private fun JSONObject.copyArray(key: String): JSONArray =
        optJSONArray(key)?.let { JSONArray(it.toString()) } ?: JSONArray()
}
