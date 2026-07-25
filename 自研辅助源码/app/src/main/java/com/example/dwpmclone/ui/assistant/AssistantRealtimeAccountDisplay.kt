package com.example.dwpmclone.ui.assistant

import com.example.dwpmclone.data.local.LocalRoleState
import com.example.dwpmclone.domain.model.GameAccount
import org.json.JSONArray
import org.json.JSONObject

/**
 * Builds assistant-page account/role display data from real protocol sync results only.
 *
 * The UI must never invent account assets. A GameAccount is considered displayable only
 * when it owns a sourceMode=1 session, and role/resource fields are read from the latest
 * protocol-synced LocalRoleState or the real session channelExtra written by login sync.
 */
object AssistantRealtimeAccountDisplayMapper {
    const val EMPTY_ACCOUNT_LABEL = "暂无实时账号数据，请先登录/同步接口数据"
    const val EMPTY_ROLE_DETAIL = "暂无接口返回数据"
    // Lo/a.S5.Pm uses the zero-based row index in scriptSoldier.sc, not the soldier id.
    private val TROOP_TYPE_NAMES_BY_CODE = mapOf(
        0 to "民兵",
        1 to "弩兵",
        2 to "弓兵",
        3 to "轻骑兵",
        4 to "弩车",
        5 to "冲城车",
        6 to "轻步兵",
        7 to "近卫兵",
        8 to "重步兵",
        9 to "弩骑兵",
        10 to "重骑兵",
        11 to "铁骑兵",
        12 to "投石车",
        13 to "重弩车",
        14 to "强弩兵",
        15 to "骁骑兵"
    )
    private val ROLE_PROFESSION_NAMES_BY_CODE = mapOf(
        0 to "步将",
        1 to "弓将",
        2 to "骑将",
        4 to "勇士"
    )

    fun build(accounts: List<GameAccount>, localState: LocalRoleState?): AssistantRealtimeAccountDisplay {
        val realAccount = accounts.firstOrNull { it.session?.sourceMode == 1 }
        val state = localState.takeIf { candidate -> candidate != null && realAccount != null && candidate.matches(realAccount) }
        val extra = realAccount?.session?.channelExtra.orEmpty()
        val hasRealtimeAccount = realAccount != null
        // Session channelExtra is written by the latest protocol refresh.  LocalRoleState
        // may be older when refresh_device_session_from_login.py updates only accounts
        // shared_prefs, so prefer extra first and use LocalRoleState only as fallback.
        val roleName = firstText(extra["roleName"], state?.roleName, realAccount?.monarchName, realAccount?.displayName)
        val level = firstText(extra["level"], state?.level)
        val pickerLabel = when {
            !hasRealtimeAccount -> EMPTY_ACCOUNT_LABEL
            roleName != null && level != null -> "${realAccount!!.username}@${realAccount.serverName} · $roleName · Lv.$level"
            roleName != null -> "${realAccount!!.username}@${realAccount.serverName} · $roleName"
            else -> "${realAccount!!.username}@${realAccount.serverName} · 等待接口状态"
        }
        val roleRows = buildRoleRows(realAccount, state, extra)
        val generalsRaw = extra["generalsJson"] ?: extra["jiangLingData"]
        val heroRows = parseHeroRows(generalsRaw)
        val parsedFormationRows = parseFormationRows(extra["formationsJson"])
        val troopRowsDerivedFromGenerals = parsedFormationRows.isEmpty() && heroRows.isNotEmpty()
        val formationRows = parsedFormationRows.ifEmpty { parseGeneralTroopRows(generalsRaw) }
        val armyRows = parseArmyRows(
            extra["armyJson"] ?: extra["idleArmyJson"] ?: extra["troopsJson"]
        )
        val treasureRows = parseInventoryRows(
            extra["inventoryJson"] ?: extra["treasuresJson"] ?: extra["itemsJson"]
        )
        val statusRows = if (realAccount == null) {
            emptyList()
        } else {
            RoleStatusDisplayPolicy.rows(
                extra["roleStateJson"],
                extra["statusEffectsJson"],
                extra["effectsJson"],
                extra["buffsJson"],
                extra["statusJson"]
            )
        }
        return AssistantRealtimeAccountDisplay(
            realAccount = realAccount,
            roleState = state,
            hasRealtimeAccount = hasRealtimeAccount,
            pickerLabel = pickerLabel,
            accountSummary = buildAccountSummary(accounts),
            roleRows = roleRows,
            heroRows = heroRows,
            armyRows = armyRows,
            formationRows = formationRows,
            troopRowsDerivedFromGenerals = troopRowsDerivedFromGenerals,
            treasureRows = treasureRows,
            statusRows = statusRows,
            sourceSummary = firstText(extra["sourceOpcode"]?.let { "真实协议 $it" }, state?.source),
            syncedAt = firstText(extra["syncedAt"], state?.syncedAt)
        )
    }


    private fun buildAccountSummary(accounts: List<GameAccount>): String {
        val realAccounts = accounts.filter { it.session?.sourceMode == 1 }
        if (realAccounts.isEmpty()) return "账号：暂无真实协议登录返回。"
        return realAccounts.joinToString(prefix = "账号：\n", separator = "\n") { account ->
            val extra = account.session?.channelExtra.orEmpty()
            val roleName = firstText(extra["roleName"], account.monarchName, account.displayName)
            val level = firstText(extra["level"])
            val suffix = listOfNotNull(roleName, level?.let { "Lv.$it" }).joinToString(" · ")
            val state = account.loginState.ifBlank { "REAL_PROTOCOL_LOGIN_OK" }
            "#${account.id} ${account.username}@${account.serverName}" +
                if (suffix.isBlank()) " · $state" else " · $suffix · $state"
        }
    }

    private fun buildRoleRows(
        account: GameAccount?,
        state: LocalRoleState?,
        extra: Map<String, String>
    ): List<Pair<String, String>> {
        if (account == null) return emptyList()
        return listOfNotNull(
            pair("君主", firstText(extra["roleName"], state?.roleName, account.monarchName, account.displayName)),
            pair("账号", firstText(account.username)),
            pair("服务器", firstText(extra["serverName"], account.serverName, state?.remark)),
            pair("等级", firstText(extra["level"], state?.level)),
            pair("国家", firstText(extra["nation"], account.nation, state?.nation, extra["title"])),
            pair("铜钱", firstText(formatWithRate(extra["copper"], extra["copperPerHour"]), state?.copper)),
            pair("粮食", firstText(formatWithRate(extra["food"], extra["foodPerHour"]), state?.food)),
            pair("声望", firstText(extra["prestige"], state?.exp)),
            pair("人口", firstText(formatCurrentCap(extra["populationCurrent"], extra["populationCap"]), state?.population)),
            pair("资源点", firstText(formatCurrentCap(extra["resourcePointCurrent"], extra["resourcePointCap"]), state?.resourcePoint)),
            pair("宝藏", firstText(
                extra["treasureProgress"],
                formatCurrentCap(extra["treasureOccupied"], extra["treasureLimit"])
            )),
            pair("刷黄次数", firstText(extra["shuaHuangUsedCount"], extra["usedAount"], extra["brushYellowCount"])),
            pair("副本次数", firstText(extra["dungeonCount"], extra["dungeonUsedCount"])),
            pair("封地上限", firstText(extra["fiefLimit"], extra["cityLimit"])),
            pair("将领上限", firstText(extra["generalLimit"], extra["heroLimit"])),
            pair("来源", firstText(extra["sourceOpcode"]?.let { "真实协议 $it" }, state?.source)),
            pair("同步时间", firstText(extra["syncedAt"], state?.syncedAt))
        )
    }

    private fun LocalRoleState?.matches(account: GameAccount): Boolean {
        val state = this ?: return false
        if (!state.looksProtocolSynced()) return false
        val extra = account.session?.channelExtra.orEmpty()
        val accountRoleNames = listOfNotNull(extra["roleName"], account.monarchName, account.displayName)
            .filter { it.isNotBlank() }
            .toSet()
        return state.roleName.isBlank() || accountRoleNames.isEmpty() || state.roleName in accountRoleNames
    }

    private fun LocalRoleState.looksProtocolSynced(): Boolean {
        return source.contains("真实", ignoreCase = true) ||
            source.contains("协议", ignoreCase = true) ||
            source.contains("0x", ignoreCase = true) ||
            syncedAt.isNotBlank()
    }

    private fun parseHeroRows(raw: String?): List<List<String>> {
        val json = raw?.trim()?.takeIf { it.isNotEmpty() } ?: return emptyList()
        return runCatching {
            val arr = if (json.startsWith("[")) JSONArray(json) else JSONArray().put(JSONObject(json))
            (0 until arr.length()).mapNotNull { index ->
                val obj = arr.optJSONObject(index) ?: return@mapNotNull null
                val name = obj.firstString("name", "generalName", "姓名")
                val id = obj.firstString("id", "generalId", "将领ID")
                if (name == null && id == null) return@mapNotNull null
                listOf(
                    name ?: "#${id.orEmpty()}",
                    formatGeneralStatus(obj.firstString("status", "状态"), obj.firstString("statusText", "stateText", "状态文本")),
                    formatGeneralFief(obj),
                    formatGeneralCategory(obj),
                    formatGeneralLevel(obj),
                    formatCurrentCap(obj.firstString("tili", "energy", "体力"), obj.firstString("tiliLimit", "energyLimit", "体力上限")) ?: obj.firstString("energy") ?: "—",
                    formatGeneralLoyalty(obj),
                    formatGeneralTroops(obj),
                    formatTroopType(obj)
                )
            }
        }.getOrDefault(emptyList())
    }

    private fun parseFormationRows(raw: String?): List<List<String>> {
        val json = raw?.trim()?.takeIf { it.isNotEmpty() } ?: return emptyList()
        return runCatching {
            val arr = if (json.startsWith("[")) JSONArray(json) else JSONArray().put(JSONObject(json))
            (0 until arr.length()).mapNotNull { index ->
                val obj = arr.optJSONObject(index) ?: return@mapNotNull null
                val id = obj.firstString("id", "formationId", "编队ID")
                val name = obj.firstString("name", "formationName", "编队")
                if (id == null && name == null) return@mapNotNull null
                val generalIds = obj.optJSONArray("generalIds")?.let { arrIds ->
                    (0 until arrIds.length()).joinToString(",") { arrIds.optString(it) }
                }
                listOf(
                    name ?: "#${id.orEmpty()}",
                    generalIds ?: obj.firstString("generalId", "将领ID") ?: "—",
                    obj.firstString("status", "状态") ?: "—",
                    obj.firstString("troopCount", "soldiers", "兵力") ?: "—"
                )
            }
        }.getOrDefault(emptyList())
    }

    private fun parseGeneralTroopRows(raw: String?): List<List<String>> {
        val json = raw?.trim()?.takeIf { it.isNotEmpty() } ?: return emptyList()
        return runCatching {
            val arr = if (json.startsWith("[")) JSONArray(json) else JSONArray().put(JSONObject(json))
            (0 until arr.length()).mapNotNull { index ->
                val obj = arr.optJSONObject(index) ?: return@mapNotNull null
                val name = obj.firstString("name", "generalName", "姓名")
                val id = obj.firstString("id", "generalId", "将领ID")
                if (name == null && id == null) return@mapNotNull null
                listOf(
                    name ?: "#${id.orEmpty()}",
                    formatGeneralStatus(obj.firstString("status", "状态"), obj.firstString("statusText", "stateText", "状态文本")),
                    formatGeneralTroops(obj),
                    formatTroopType(obj)
                )
            }
        }.getOrDefault(emptyList())
    }

    /**
     * Desktop “角色 → 军队” uses the idle/wounded army inventory rather than expedition
     * formations. Accept the field aliases seen in protocol evidence and imported fixtures while
     * keeping formation rows as a separate fallback in the UI.
     */
    private fun parseArmyRows(raw: String?): List<List<String>> {
        val json = raw?.trim()?.takeIf { it.isNotEmpty() } ?: return emptyList()
        return runCatching {
            val arr = if (json.startsWith("[")) JSONArray(json) else JSONArray().put(JSONObject(json))
            (0 until arr.length()).mapNotNull { index ->
                val obj = arr.optJSONObject(index) ?: return@mapNotNull null
                val type = obj.firstString(
                    "soldierType", "soldierTypeName", "troopType", "troopTypeName", "兵种"
                ) ?: obj.firstString("soldierTypeCode", "troopTypeCode")?.toIntOrNull()
                    ?.let { troopTypeName(it) ?: "未知兵种$it" }
                    ?: return@mapNotNull null
                val idle = obj.firstString(
                    "idleCount", "availableCount", "freeCount", "count", "amount", "闲兵数量", "闲兵"
                ) ?: "0"
                val wounded = obj.firstString(
                    "woundedCount", "hurtSoldierCount", "injuredCount", "伤兵数量", "伤兵"
                ) ?: "0"
                val fief = obj.firstString(
                    "fiefName", "cityName", "baseName", "封地", "封地名称"
                ) ?: obj.firstString("fiefId", "cityId")?.let { "封地$it" }
                    ?: "基地"
                listOf(type, idle, wounded, fief)
            }
        }.getOrDefault(emptyList())
    }

    private fun parseInventoryRows(raw: String?): List<List<String>> {
        val json = raw?.trim()?.takeIf { it.isNotEmpty() } ?: return emptyList()
        return runCatching {
            val arr = if (json.startsWith("[")) JSONArray(json) else JSONArray().put(JSONObject(json))
            (0 until arr.length()).mapNotNull { index ->
                val obj = arr.optJSONObject(index) ?: return@mapNotNull null
                val name = obj.firstString("name", "itemName", "treasureName", "名称") ?: return@mapNotNull null
                val count = obj.firstString("count", "num", "quantity", "数量") ?: "—"
                val id = obj.firstString("itemId", "id", "道具ID") ?: "—"
                listOf(name, count, id)
            }
        }.getOrDefault(emptyList())
    }

    private fun JSONObject.firstString(vararg keys: String): String? {
        keys.forEach { key ->
            if (has(key) && !isNull(key)) {
                val value = optString(key).trim()
                if (value.isNotBlank()) return value
            }
        }
        return null
    }

    private fun firstText(vararg values: String?): String? = values.firstOrNull { !it.isNullOrBlank() }?.trim()

    private fun pair(name: String, value: String?): Pair<String, String>? = value?.let { name to it }

    private fun formatGeneralStatus(status: String?, statusText: String?): String {
        compactGeneralStatusText(statusText)?.let { return it }
        return when (val raw = status?.trim()) {
            "0" -> "闲"
            "1" -> "征"
            "2" -> "防"
            "3" -> "俘"
            "4" -> "返"
            null, "" -> "—"
            else -> compactGeneralStatusText(raw) ?: raw
        }
    }

    private fun compactGeneralStatusText(value: String?): String? =
        value?.trim()?.takeIf { it.isNotBlank() }?.let { text ->
            when (text) {
                "空闲" -> "闲"
                "出征" -> "征"
                "防守", "驻防" -> "防"
                "被俘虏", "被俘" -> "俘"
                "死亡", "阵亡" -> "亡"
                "修炼", "修炼中" -> "修"
                "作战中" -> "战"
                "待招募" -> "招"
                "返回" -> "返"
                else -> text
            }
        }

    private fun formatGeneralFief(obj: JSONObject): String {
        obj.firstString("fiefName", "cityName", "baseName", "封地", "封地名称")
            ?.let { return it }
        return obj.firstString("fiefId", "placeId", "placeID", "cityId")
            ?.let { "封地#$it" }
            ?: "—"
    }

    private fun formatGeneralCategory(obj: JSONObject): String {
        val source = obj.firstString("source").orEmpty()
        if (source == "state8004-binary-jiangling") {
            obj.byteFromBodyHeadHex(0x03)?.let { code ->
                ROLE_PROFESSION_NAMES_BY_CODE[code]?.let { return it }
            }
            obj.firstString("professionCode", "categoryCode", "kindCode")?.toIntOrNull()?.let { code ->
                ROLE_PROFESSION_NAMES_BY_CODE[code]?.let { return it }
            }
            obj.firstString("category", "分类", "kind", "type", "类")
                ?.takeUnless { it.startsWith("码") || Regex("""类\d+""").matches(it) }
                ?.let { return it }
            return "—"
        }
        obj.firstString("category", "分类")?.let { return it }
        obj.firstString("kind", "type", "类")?.let { return it }
        obj.firstString("kindCode")?.toIntOrNull()?.let { code -> ROLE_PROFESSION_NAMES_BY_CODE[code]?.let { return it } }
        obj.firstString("categoryCode")?.toIntOrNull()?.let { code -> ROLE_PROFESSION_NAMES_BY_CODE[code]?.let { return it } }
        obj.firstString("rankTier")?.let { return "阶$it" }
        return "—"
    }

    private fun formatGeneralLevel(obj: JSONObject): String {
        val source = obj.firstString("source").orEmpty()
        if (source == "state8004-binary-jiangling") {
            // Older cached parser output stored the real JiangLing rank/level in
            // rankTier while incorrectly putting growth in level/rank.  Prefer
            // rankTier/bodyHeadHex for those cached records so the UI fixes
            // itself even before the user logs in again.
            obj.firstString("rankTier")?.toIntOrNull()?.takeIf { it in 1..200 }?.let { return it.toString() }
            obj.firstString("bodyHeadHex")?.let { hex ->
                val clean = hex.filter { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }
                if (clean.length >= 18) {
                    clean.substring(16, 18).toIntOrNull(16)?.takeIf { it in 1..200 }?.let { return it.toString() }
                }
            }
        }
        return obj.firstString("level", "rank", "等级", "级") ?: "—"
    }

    private fun formatGeneralTroops(obj: JSONObject): String {
        val source = obj.firstString("source").orEmpty()
        if (source == "state8004-binary-jiangling") {
            val hasS5Assignment = obj.firstString("troopCountSource", "troopTypeSource", "s5Offset") != null
            val current = if (hasS5Assignment) {
                obj.firstString("troopCount", "soldierCount", "currentTroopCount", "currentSoldierCount", "bingli", "当前兵数", "兵数")
            } else {
                null
            }
            val cap = obj.firstString("daiBingLimit", "troopLimit", "maxTroopCount", "maxSoldierCount", "带兵上限", "统兵上限", "最大统兵数", "统兵数")
                ?: obj.u32FromBodyHeadHex(0x23)?.toString()
            return formatCurrentCapForTroops(current, cap) ?: "—"
        }
        return formatCurrentCapForTroops(
            obj.firstString("troopCount", "soldierCount", "currentTroopCount", "currentSoldierCount", "bingli", "当前兵数", "兵数"),
            obj.firstString("daiBingLimit", "troopLimit", "maxTroopCount", "maxSoldierCount", "带兵上限", "统兵上限", "最大统兵数", "统兵数")
        ) ?: "—"
    }

    private fun formatTroopType(obj: JSONObject): String {
        val source = obj.firstString("source").orEmpty()
        val hasS5Assignment = obj.firstString("troopTypeSource", "troopCountSource", "s5Offset") != null
        obj.firstString("troopTypeName", "soldierTypeName")?.let { return it }
        obj.firstString("troopType", "soldierType", "兵种")?.let { type ->
            if (source == "state8004-binary-jiangling" && !hasS5Assignment && placeholderTroopCode(type) != null) {
                return "—"
            }
            placeholderTroopCode(type)?.let { code -> troopTypeName(code)?.let { return it } }
            return type
        }
        obj.firstString("troopTypeCode", "soldierTypeCode")?.toIntOrNull()?.let { code ->
            if (source == "state8004-binary-jiangling" && !hasS5Assignment) return "—"
            return troopTypeName(code) ?: "未知兵种$code"
        }
        return "—"
    }

    private fun formatGeneralLoyalty(obj: JSONObject): String {
        val source = obj.firstString("source").orEmpty()
        if (source == "state8004-binary-jiangling") {
            val current = obj.byteFromBodyHeadHex(0x27)?.toString()
                ?: obj.firstString("zhongChengdu", "loyalty", "忠诚")
            val limit = obj.byteFromBodyHeadHex(0x28)?.toString()
                ?: obj.firstString("loyaltyLimit", "忠诚上限")
            return formatCurrentCap(current, limit) ?: current ?: "—"
        }
        return formatCurrentCap(
            obj.firstString("zhongChengdu", "loyalty", "忠诚"),
            obj.firstString("loyaltyLimit", "忠诚上限")
        ) ?: obj.firstString("loyalty") ?: "—"
    }

    private fun JSONObject.byteFromBodyHeadHex(offset: Int): Int? {
        val clean = bodyHeadHexClean() ?: return null
        val start = offset * 2
        if (start < 0 || start + 2 > clean.length) return null
        return clean.substring(start, start + 2).toIntOrNull(16)
    }

    private fun JSONObject.u32FromBodyHeadHex(offset: Int): Long? {
        val clean = bodyHeadHexClean() ?: return null
        val start = offset * 2
        if (start < 0 || start + 8 > clean.length) return null
        return clean.substring(start, start + 8).toLongOrNull(16)
    }

    private fun JSONObject.bodyHeadHexClean(): String? {
        val clean = firstString("bodyHeadHex")
            ?.filter { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }
            ?: return null
        return clean
    }

    private fun placeholderTroopCode(value: String): Int? {
        val text = value.trim()
        return Regex("""^(?:兵种|未知兵种)(\d+)$""").matchEntire(text)?.groupValues?.getOrNull(1)?.toIntOrNull()
    }

    private fun troopTypeName(code: Int): String? =
        TROOP_TYPE_NAMES_BY_CODE[code]

    private fun formatWithRate(value: String?, perHour: String?): String? {
        val base = value?.trim()?.takeIf { it.isNotBlank() } ?: return null
        val rate = perHour?.trim()?.takeIf { it.isNotBlank() }
        return if (rate == null) base else "$base（+$rate/小时）"
    }

    private fun formatCurrentCap(current: String?, cap: String?): String? {
        val left = current?.trim()?.takeIf { it.isNotBlank() } ?: return null
        val right = cap?.trim()?.takeIf { it.isNotBlank() }
        return if (right == null) left else "$left / $right"
    }

    private fun formatCurrentCapForTroops(current: String?, cap: String?): String? {
        val left = current?.trim()?.takeIf { it.isNotBlank() }
        val right = cap?.trim()?.takeIf { it.isNotBlank() }
        return when {
            left != null && right != null -> "$left / $right"
            left != null -> left
            right != null -> "— / $right"
            else -> null
        }
    }
}

data class AssistantRealtimeAccountDisplay(
    val realAccount: GameAccount?,
    val roleState: LocalRoleState?,
    val hasRealtimeAccount: Boolean,
    val pickerLabel: String,
    val accountSummary: String,
    val roleRows: List<Pair<String, String>>,
    val heroRows: List<List<String>>,
    val armyRows: List<List<String>>,
    val formationRows: List<List<String>>,
    val troopRowsDerivedFromGenerals: Boolean,
    val treasureRows: List<List<String>>,
    val statusRows: List<List<String>>,
    val sourceSummary: String?,
    val syncedAt: String?
)
