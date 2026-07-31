package com.example.dwpmclone.data.account

import com.example.dwpmclone.data.local.CredentialVault
import com.example.dwpmclone.data.local.LocalAccountRepository
import com.example.dwpmclone.data.local.TaskLogRepository
import com.example.dwpmclone.data.protocol.RealGameProtocolClient
import com.example.dwpmclone.domain.model.Channel
import com.example.dwpmclone.domain.model.GameAccount
import com.example.dwpmclone.domain.model.GameSession
import com.example.dwpmclone.domain.model.GameVersion
import com.example.dwpmclone.domain.protocol.State8004ArmyEvidenceParser
import com.example.dwpmclone.domain.protocol.State8004GeneralEvidenceParser
import com.example.dwpmclone.domain.protocol.State8004StatusEvidenceParser
import org.json.JSONArray
import org.json.JSONObject

/** Owns the real login -> typed local state -> encrypted credential persistence transaction. */
class LocalAccountLoginService(
    private val accounts: LocalAccountRepository,
    private val credentials: CredentialVault,
    private val logs: TaskLogRepository,
    private val protocol: RealGameProtocolClient = RealGameProtocolClient()
) {
    fun loginAndPersist(username: String, password: String, serverQuery: String): GameAccount =
        loginAndPersist(username, password, serverQuery, expectedAccountId = null)

    private fun loginAndPersist(
        username: String,
        password: String,
        serverQuery: String,
        expectedAccountId: Long?
    ): GameAccount {
        require(username.isNotBlank()) { "账号不能为空" }
        require(password.isNotEmpty()) { "密码不能为空" }
        require(serverQuery.isNotBlank()) { "区服不能为空" }

        val result = protocol.loginAndFetchState(username.trim(), password, serverQuery.trim())
        val state = result.state
        require(expectedAccountId == null || state.roleId == expectedAccountId) {
            "自动重登返回了不同角色，已拒绝覆盖本地账号"
        }
        val role = result.selectedRole
        val existing = accounts.get(state.roleId) ?: accounts.listAccounts().firstOrNull {
            it.username == result.username &&
                (it.serverId == result.area.serverKey || it.serverName == result.area.areaName)
        }
        val generalRecords = State8004GeneralEvidenceParser.recoverBestAvailableRecords(
            state.tailHex,
            state.payloadHex
        )
        val statusRecords = State8004StatusEvidenceParser.recoverRecords(state.payloadHex)
        val armyRows = State8004ArmyEvidenceParser.recover(state.payloadHex)
        val inventory = result.inventoryState

        val sessionExtra = mutableMapOf(
            "userId" to result.userId,
            "dm" to result.dm.toString(),
            "serverUrl" to result.area.serverUrl,
            "serverKey" to result.area.serverKey,
            "gameHttp" to (result.area.serverUrl.trimEnd('/') + "/kingWapServer/HttpClient"),
            "accountWithSuffix" to result.accountWithSuffix.orEmpty(),
            "roleId" to state.roleId.toString(),
            "roleName" to state.roleName,
            "level" to state.level.toString(),
            "nation" to role.country,
            "title" to role.title,
            "copper" to state.copper.toString(),
            "food" to state.food.toString(),
            "prestige" to state.prestige.toString(),
            "copperPerHour" to state.copperPerHour.toString(),
            "foodPerHour" to state.foodPerHour.toString(),
            "populationCurrent" to state.populationCurrent.toString(),
            "populationCap" to state.populationCap.toString(),
            "fiefLimit" to state.fiefLimit.toString(),
            "generalLimit" to state.generalLimit.toString(),
            "resourcePointCurrent" to state.resourcePointCurrent.toString(),
            "resourcePointCap" to state.resourcePointCap.toString(),
            "officeFieldFlag" to (state.officeFieldFlag?.toString() ?: ""),
            "officeId" to (state.officeIdUnsigned?.toString() ?: ""),
            "officeIdRaw" to (state.officeIdRaw?.toString() ?: ""),
            "officeIdUnsigned" to (state.officeIdUnsigned?.toString() ?: ""),
            "officeName" to state.officeName,
            "officialTitle" to state.officeName,
            "state8004PayloadByteCount" to state.payloadByteCount.toString(),
            "state8004ParsedHeadByteCount" to state.parsedHeadByteCount.toString(),
            "state8004TailByteCount" to state.tailByteCount.toString(),
            "state8004PayloadHex" to state.payloadHex,
            "state8004TailHex" to state.tailHex,
            "state8004TailUtf8Preview" to state.tailUtf8Preview,
            "roleStateJson" to roleStateJson(result).toString(),
            "resourceStateJson" to resourceStateJson(result).toString(),
            "sourceOpcode" to state.sourceOpcode,
            "liveStateRefreshEnabled" to "true",
            "syncedAt" to result.syncedAt,
            "realActionNetworkAllowed" to "true",
            "realActionSendReady" to "true",
            "realActionScope" to "brush-yellow",
            "realActionScopes" to "brush-yellow,mine,daily,inventory,general-maintenance,dungeon,lossless,raid,resource-conversion,internal-affairs,ministry-plant",
            "realActionBrushYellowOnly" to "true",
            "recoveredReadOnlyLiveGate" to "true",
            "allowRecoveredGeneralFallbackFormation" to "true",
            "inventoryLiveRefreshAllowed" to "true",
            "militaryIntelLiveGate" to "true",
            "unifiedExpeditionPreflight" to "true",
            // 与电脑端一致：账号启动只恢复日常/内政等通用任务，
            // 刷黄、打矿等常驻任务由“开始执行任务”或在线保存规则显式开启。
            "savedTasksStarted" to "false",
            "activeResidentTaskKeys" to ""
        )
        if (generalRecords.isNotEmpty()) {
            sessionExtra["generalsJson"] = JSONArray().apply {
                generalRecords.forEach { put(JSONObject(it)) }
            }.toString()
            sessionExtra["state8004GeneralRecordCount"] = generalRecords.size.toString()
            sessionExtra["generalsParserVersion"] = State8004GeneralEvidenceParser.PARSER_VERSION
        }
        if (result.ownedFiefLocations.isNotEmpty()) {
            sessionExtra["ownedFiefLocationsJson"] = JSONArray().apply {
                result.ownedFiefLocations.forEach { fief ->
                    put(JSONObject()
                        .put("targetId", fief.targetId)
                        .put("fiefId", fief.targetId)
                        .put("name", fief.name)
                        .put("fiefName", fief.name)
                        .put("cityName", fief.cityName)
                        .put("serialByte", fief.serialByte ?: JSONObject.NULL)
                        .put("mapFlag", fief.mapFlag ?: JSONObject.NULL)
                        .put("x", fief.x ?: JSONObject.NULL)
                        .put("y", fief.y ?: JSONObject.NULL))
                }
            }.toString()
            sessionExtra["ownedFiefLocationsUpdatedAt"] = System.currentTimeMillis().toString()
        }
        result.ownedFiefLocationError?.let { error ->
            sessionExtra["ownedFiefLocationError"] = error
        }
        if (statusRecords.isNotEmpty()) {
            sessionExtra["statusJson"] = JSONArray().apply {
                statusRecords.forEach { put(JSONObject(it)) }
            }.toString()
            sessionExtra["state8004StatusRecordCount"] = statusRecords.size.toString()
        }
        if (armyRows.isNotEmpty()) {
            sessionExtra["armyJson"] = State8004ArmyEvidenceParser.toJson(armyRows)
            sessionExtra["armySource"] = "live/0x8004-compact-army"
            sessionExtra["armyRecordCount"] = armyRows.size.toString()
        }
        if (inventory != null) {
            sessionExtra["inventoryJson"] = JSONArray().apply {
                inventory.items.forEach { item ->
                    put(JSONObject()
                        .put("id", item.itemId)
                        .put("itemId", item.itemId)
                        .put("name", item.name)
                        .put("count", item.count)
                        .put("type", item.typeLabel.orEmpty())
                        .put("nameSource", item.nameSource)
                        .put("source", inventory.sourceOpcode)
                        .put("rawTailHex", item.rawTailHex))
                }
                inventory.equipment.forEach { item ->
                    put(JSONObject()
                        .put("id", item.instanceId)
                        .put("itemId", item.instanceId)
                        .put("templateId", item.templateId)
                        .put("name", item.name)
                        .put("count", 1)
                        .put("type", "equipment")
                        .put("quality", item.quality)
                        .put("level", item.level)
                        .put("strengthen", item.strengthen)
                        .put("enhanced", item.strengthen > 0)
                        .put("equipped", false)
                        .put("famous", item.famous)
                        .put("extraText", item.extraText)
                        .put(
                            "equipmentMetadataComplete",
                            item.instanceId > 0L && item.typeCode >= 0 &&
                                item.level > 0 && item.quality in 0..3
                        )
                        .put("source", inventory.sourceOpcode)
                        .put("rawHex", item.rawHex))
                }
            }.toString()
            sessionExtra["inventoryCapacity"] = inventory.capacity.toString()
            sessionExtra["inventoryItemCount"] = inventory.itemCount.toString()
            sessionExtra["inventoryEquipmentCount"] = inventory.equipment.size.toString()
            inventory.equipmentParseError?.let {
                sessionExtra["inventoryEquipmentParseError"] = it
            }
            sessionExtra["inventorySourceOpcode"] = inventory.sourceOpcode
            sessionExtra["inventoryPayloadByteCount"] = inventory.payloadByteCount.toString()
            sessionExtra["inventoryParsedItemByteCount"] = inventory.parsedItemByteCount.toString()
            sessionExtra["inventoryPayloadHex"] = inventory.payloadHex
            sessionExtra["inventoryTailHex"] = inventory.tailHex
        }
        result.dailyActivityState?.let { activity ->
            sessionExtra["dailyActivityJson"] = activity.toJson()
            sessionExtra["dailyActivitySourceOpcode"] = activity.sourceOpcode
            sessionExtra["dailyActivityPayloadByteCount"] = activity.payloadByteCount.toString()
        }

        val account = GameAccount(
            id = state.roleId,
            displayName = state.roleName,
            username = result.username,
            serverName = result.area.areaName,
            serverId = result.area.serverKey,
            gameVersion = GameVersion.TENCENT_CLASSIC,
            channel = Channel.QQ,
            session = GameSession(
                accountId = state.roleId,
                tokenCiphertext = LocalAccountRepository.SESSION_PRESENT_MARKER,
                expiresAtMillis = null,
                channelExtra = sessionExtra,
                sourceMode = 1
            ),
            enabled = existing?.enabled ?: false,
            monarchName = state.roleName,
            nation = role.country,
            loginState = if (existing?.enabled == true) AccountLoginState.ONLINE else AccountLoginState.STOPPED,
            gameAuthSignEvidence = "empty-signature-verified"
        )
        // Credential encryption is the commit gate: no account/session is persisted if it fails.
        credentials.savePassword(account.id, password)
        accounts.upsert(account)
        logs.append("真实协议登录成功：${state.roleName} Lv.${state.level} ${result.area.areaName}", "real-protocol", account.id)
        return account
    }

    fun relogin(account: GameAccount, preserveTaskRuntime: Boolean = true): GameAccount {
        val previousHealthAccountId = com.example.dwpmclone.data.protocol.GameRequestHealthSink.currentAccountId()
        com.example.dwpmclone.data.protocol.GameRequestHealthSink.bindAccount(account.id)
        return try {
            val password = credentials.loadPassword(account.id)
                ?: throw IllegalStateException("账号未保存无人值守登录凭据")
            val serverQuery = account.serverId?.takeIf { it.isNotBlank() } ?: account.serverName
            val loggedIn = loginAndPersist(account.username, password, serverQuery, expectedAccountId = account.id)
            if (!preserveTaskRuntime) return loggedIn
            val preserved = account.session?.channelExtra.orEmpty()
                .filterKeys { it in PRESERVED_RECONNECT_RUNTIME_KEYS }
            if (preserved.isEmpty()) return loggedIn
            val session = loggedIn.session ?: return loggedIn
            loggedIn.copy(session = session.copy(channelExtra = session.channelExtra + preserved)).also(accounts::upsert)
        } finally {
            if (previousHealthAccountId != null) {
                com.example.dwpmclone.data.protocol.GameRequestHealthSink.bindAccount(previousHealthAccountId)
            } else {
                com.example.dwpmclone.data.protocol.GameRequestHealthSink.clearAccount()
            }
        }
    }

    private fun roleStateJson(result: RealGameProtocolClient.LoginResult): JSONObject = result.state.let { state ->
        JSONObject()
            .put("roleId", state.roleId)
            .put("roleName", state.roleName)
            .put("level", state.level)
            .put("nation", result.selectedRole.country)
            .put("title", result.selectedRole.title)
            .put("prestige", state.prestige)
            .put("populationCurrent", state.populationCurrent)
            .put("populationCap", state.populationCap)
            .put("fiefLimit", state.fiefLimit)
            .put("generalLimit", state.generalLimit)
            .put("resourcePointCurrent", state.resourcePointCurrent)
            .put("resourcePointCap", state.resourcePointCap)
            .put("officeFieldFlag", state.officeFieldFlag ?: JSONObject.NULL)
            .put("officeId", state.officeIdUnsigned ?: JSONObject.NULL)
            .put("officeIdRaw", state.officeIdRaw ?: JSONObject.NULL)
            .put("officeIdUnsigned", state.officeIdUnsigned ?: JSONObject.NULL)
            .put("officeName", state.officeName)
            .put("sourceOpcode", state.sourceOpcode)
    }

    private fun resourceStateJson(result: RealGameProtocolClient.LoginResult): JSONObject = result.state.let { state ->
        JSONObject()
            .put("copper", state.copper)
            .put("food", state.food)
            .put("prestige", state.prestige)
            .put("copperPerHour", state.copperPerHour)
            .put("foodPerHour", state.foodPerHour)
            .put("populationCurrent", state.populationCurrent)
            .put("populationCap", state.populationCap)
            .put("resourcePointCurrent", state.resourcePointCurrent)
            .put("resourcePointCap", state.resourcePointCap)
    }

    private companion object {
        val PRESERVED_RECONNECT_RUNTIME_KEYS = setOf(
            "savedTasksStarted",
            "savedTasksStartedAt",
            "activeResidentTaskKeys",
            "minePendingGarrisonJson",
            "dungeonPendingRunJson",
            "brushPendingRecoveryJson"
        )
    }
}
