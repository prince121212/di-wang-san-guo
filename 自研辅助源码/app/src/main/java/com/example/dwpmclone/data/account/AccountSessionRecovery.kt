package com.example.dwpmclone.data.account

import com.example.dwpmclone.data.local.LocalAccountRepository
import com.example.dwpmclone.data.local.SessionReconnectRepository
import com.example.dwpmclone.data.local.TaskLogRepository
import com.example.dwpmclone.data.protocol.RealGameProtocolClient
import com.example.dwpmclone.domain.model.GameAccount
import com.example.dwpmclone.domain.protocol.State8004ArmyEvidenceParser
import com.example.dwpmclone.domain.protocol.State8004GeneralEvidenceParser
import com.example.dwpmclone.domain.protocol.State8004StatusEvidenceParser
import org.json.JSONArray
import org.json.JSONObject

object AccountLoginState {
    const val ONLINE = "REAL_PROTOCOL_ONLINE"
    const val CHECKING = "REAL_PROTOCOL_CHECKING"
    const val NETWORK_PAUSED = "REAL_PROTOCOL_NETWORK_PAUSED"
    const val NEED_RELOGIN = "REAL_PROTOCOL_NEED_RELOGIN"
    const val OFFLINE = "REAL_PROTOCOL_OFFLINE"
    const val STOPPED = "REAL_PROTOCOL_STOPPED"

    fun requiresRelogin(value: String): Boolean = value == NEED_RELOGIN || value == OFFLINE

    fun shouldProbe(
        value: String,
        forceValidation: Boolean,
        lastValidatedAtMillis: Long?,
        nowMillis: Long,
        heartbeatIntervalMillis: Long
    ): Boolean {
        if (forceValidation || value == NETWORK_PAUSED || value == CHECKING) return true
        if (value != ONLINE) return false
        val last = lastValidatedAtMillis ?: return true
        return nowMillis - last >= heartbeatIntervalMillis
    }
}

sealed interface SessionProbeResult {
    data class Valid(val updates: Map<String, String>) : SessionProbeResult
    data class Expired(val reason: String) : SessionProbeResult
    data class Unavailable(val reason: String) : SessionProbeResult
}

fun interface SessionHealthProbe {
    fun probe(account: GameAccount, fullStateRefresh: Boolean): SessionProbeResult
}

class RealSessionHealthProbe(
    private val protocol: RealGameProtocolClient = RealGameProtocolClient()
) : SessionHealthProbe {
    override fun probe(account: GameAccount, fullStateRefresh: Boolean): SessionProbeResult {
        val session = account.session ?: return SessionProbeResult.Expired("真实 Session 不存在")
        val extra = session.channelExtra
        val gameHttp = extra["gameHttp"]?.takeIf(String::isNotBlank)
            ?: extra["serverUrl"]?.takeIf(String::isNotBlank)?.trimEnd('/')?.plus("/kingWapServer/HttpClient")
            ?: return SessionProbeResult.Expired("游戏服务器地址不存在")
        val dm = extra["dm"]?.toLongOrNull()
            ?: return SessionProbeResult.Expired("角色会话 dm 不存在")
        val roleId = extra["roleId"]?.toLongOrNull() ?: account.id
        val previousHealthAccountId = com.example.dwpmclone.data.protocol.GameRequestHealthSink.currentAccountId()
        com.example.dwpmclone.data.protocol.GameRequestHealthSink.bindAccount(account.id)
        return try {
            runCatching {
            if (!fullStateRefresh) {
                val heartbeat = protocol.refreshHeartbeat3110(gameHttp, dm)
                return@runCatching SessionProbeResult.Valid(
                    mapOf(
                        "lastValidatedAt" to System.currentTimeMillis().toString(),
                        "lastHeartbeatAt" to System.currentTimeMillis().toString(),
                        "militaryIntelOpcodes" to heartbeat.responseOpcodes.joinToString(),
                        "militaryIntelPayloadHex" to heartbeat.responsePayloadHex
                    )
                )
            }
            val refreshed = protocol.refreshRoleState(gameHttp, dm, roleId)
            val state = refreshed.state
            val generalRecords = State8004GeneralEvidenceParser.recoverBestAvailableRecords(
                state.tailHex,
                state.payloadHex
            )
            val statusRecords = State8004StatusEvidenceParser.recoverRecords(state.payloadHex)
            val armyRows = State8004ArmyEvidenceParser.recover(state.payloadHex)
            val heartbeat = runCatching { protocol.refreshHeartbeat3110(gameHttp, dm) }.getOrNull()
            SessionProbeResult.Valid(
                buildMap {
                    putAll(mapOf(
                    "roleId" to state.roleId.toString(),
                    "roleName" to state.roleName,
                    "level" to state.level.toString(),
                    "copper" to state.copper.toString(),
                    "food" to state.food.toString(),
                    "prestige" to state.prestige.toString(),
                    "populationCurrent" to state.populationCurrent.toString(),
                    "populationCap" to state.populationCap.toString(),
                    "resourcePointCurrent" to state.resourcePointCurrent.toString(),
                    "resourcePointCap" to state.resourcePointCap.toString(),
                    "officeFieldFlag" to (state.officeFieldFlag?.toString() ?: ""),
                    "officeId" to (state.officeIdUnsigned?.toString() ?: ""),
                    "officeIdRaw" to (state.officeIdRaw?.toString() ?: ""),
                    "officeIdUnsigned" to (state.officeIdUnsigned?.toString() ?: ""),
                    "officeName" to state.officeName,
                    "officialTitle" to state.officeName,
                    "state8004PayloadHex" to state.payloadHex,
                    "state8004TailHex" to state.tailHex,
                    "roleStateJson" to JSONObject()
                        .put("roleId", state.roleId)
                        .put("roleName", state.roleName)
                        .put("level", state.level)
                        .put("prestige", state.prestige)
                        .put("populationCurrent", state.populationCurrent)
                        .put("populationCap", state.populationCap)
                        .put("resourcePointCurrent", state.resourcePointCurrent)
                        .put("resourcePointCap", state.resourcePointCap)
                        .put("officeFieldFlag", state.officeFieldFlag ?: JSONObject.NULL)
                        .put("officeId", state.officeIdUnsigned ?: JSONObject.NULL)
                        .put("officeIdRaw", state.officeIdRaw ?: JSONObject.NULL)
                        .put("officeIdUnsigned", state.officeIdUnsigned ?: JSONObject.NULL)
                        .put("officeName", state.officeName)
                        .put("sourceOpcode", state.sourceOpcode)
                        .toString(),
                    "resourceStateJson" to JSONObject()
                        .put("copper", state.copper)
                        .put("food", state.food)
                        .put("prestige", state.prestige)
                        .put("copperPerHour", state.copperPerHour)
                        .put("foodPerHour", state.foodPerHour)
                        .put("populationCurrent", state.populationCurrent)
                        .put("populationCap", state.populationCap)
                        .put("resourcePointCurrent", state.resourcePointCurrent)
                        .put("resourcePointCap", state.resourcePointCap)
                        .toString(),
                    "lastValidatedAt" to refreshed.refreshedAtMillis.toString()
                    ))
                    if (generalRecords.isNotEmpty()) {
                        put("generalsJson", JSONArray().apply {
                            generalRecords.forEach { put(JSONObject(it)) }
                        }.toString())
                        put("state8004GeneralRecordCount", generalRecords.size.toString())
                        put("generalsParserVersion", State8004GeneralEvidenceParser.PARSER_VERSION)
                    }
                    if (statusRecords.isNotEmpty()) {
                        put("statusJson", JSONArray().apply {
                            statusRecords.forEach { put(JSONObject(it)) }
                        }.toString())
                        put("state8004StatusRecordCount", statusRecords.size.toString())
                    }
                    if (armyRows.isNotEmpty()) {
                        put("armyJson", State8004ArmyEvidenceParser.toJson(armyRows))
                        put("armySource", "live/0x8004-compact-army")
                        put("armyRecordCount", armyRows.size.toString())
                    }
                    heartbeat?.let {
                        put("lastHeartbeatAt", refreshed.refreshedAtMillis.toString())
                        put("militaryIntelOpcodes", it.responseOpcodes.joinToString())
                        put("militaryIntelPayloadHex", it.responsePayloadHex)
                    }
                }
            )
            }.getOrElse { error ->
                val message = error.message ?: error::class.java.simpleName
                if (message.isSessionExpiredEvidence()) {
                    SessionProbeResult.Expired(message)
                } else {
                    SessionProbeResult.Unavailable(message)
                }
            }
        } finally {
            if (previousHealthAccountId != null) {
                com.example.dwpmclone.data.protocol.GameRequestHealthSink.bindAccount(previousHealthAccountId)
            } else {
                com.example.dwpmclone.data.protocol.GameRequestHealthSink.clearAccount()
            }
        }
    }

    private fun String.isSessionExpiredEvidence(): Boolean =
        contains("0x8016", ignoreCase = true) ||
            contains("没有角色信息") ||
            contains("沒有角色信息") ||
            contains("会话失效") ||
            contains("session invalid", ignoreCase = true)
}

data class SessionRecoverySummary(
    val online: Int,
    val paused: Int,
    val waitingToRetry: Int,
    val relogged: Int
)

/** Reconciles enabled accounts before the scheduler may issue any task action. */
class AccountSessionRecovery(
    private val accounts: LocalAccountRepository,
    private val loginService: LocalAccountLoginService,
    private val reconnects: SessionReconnectRepository,
    private val logs: TaskLogRepository,
    private val probe: SessionHealthProbe = RealSessionHealthProbe(),
    private val heartbeatIntervalMillis: Long = 20_000L
) {
    fun reconcile(nowMillis: Long, forceValidation: Boolean): SessionRecoverySummary {
        var online = 0
        var paused = 0
        var waiting = 0
        var relogged = 0
        accounts.listAccounts().filter { it.enabled && it.session?.sourceMode == 1 }.forEach { account ->
            val state = account.loginState.uppercase()
            if (AccountLoginState.requiresRelogin(state)) {
                val retry = reconnects.state(account.id)
                if (retry.nextAttemptAtMillis > nowMillis) {
                    waiting += 1
                    return@forEach
                }
                runCatching { loginService.relogin(account, preserveTaskRuntime = true) }
                    .onSuccess {
                        reconnects.reset(account.id)
                        accounts.updateLoginState(account.id, AccountLoginState.ONLINE, mapOf("lastReloginAt" to nowMillis.toString()))
                        logs.append("账号 ${account.id} 自动重新登录成功", "session-recovery", account.id)
                        relogged += 1
                        online += 1
                    }
                    .onFailure { error ->
                        val next = reconnects.recordFailure(account.id, nowMillis, error.message ?: "自动重登失败")
                        accounts.updateLoginState(
                            account.id,
                            AccountLoginState.OFFLINE,
                            mapOf(
                                "nextReloginAt" to next.nextAttemptAtMillis.toString(),
                                "lastReloginError" to next.reason
                            )
                        )
                        logs.append("账号 ${account.id} 自动重登失败，第${next.failures}次；将在${next.nextAttemptAtMillis}后重试", "session-recovery", account.id)
                        waiting += 1
                    }
                return@forEach
            }
            val mustProbe = AccountLoginState.shouldProbe(
                value = state,
                forceValidation = forceValidation,
                lastValidatedAtMillis = account.session?.channelExtra?.get("lastValidatedAt")?.toLongOrNull(),
                nowMillis = nowMillis,
                heartbeatIntervalMillis = heartbeatIntervalMillis
            )
            if (!mustProbe && state == AccountLoginState.ONLINE) {
                online += 1
                return@forEach
            }
            if (!mustProbe) {
                paused += 1
                return@forEach
            }
            val retry = reconnects.state(account.id)
            if (retry.nextAttemptAtMillis > nowMillis) {
                waiting += 1
                return@forEach
            }
            val fullStateRefresh = forceValidation ||
                state == AccountLoginState.NETWORK_PAUSED ||
                state == AccountLoginState.CHECKING
            when (val result = probe.probe(account, fullStateRefresh)) {
                is SessionProbeResult.Valid -> {
                    val session = account.session ?: return@forEach
                    accounts.upsert(
                        account.copy(
                            displayName = result.updates["roleName"] ?: account.displayName,
                            monarchName = result.updates["roleName"] ?: account.monarchName,
                            loginState = AccountLoginState.ONLINE,
                            session = session.copy(channelExtra = session.channelExtra + result.updates)
                        )
                    )
                    reconnects.reset(account.id)
                    online += 1
                }
                is SessionProbeResult.Expired -> {
                    markNeedsRelogin(account.id, result.reason)
                    paused += 1
                }
                is SessionProbeResult.Unavailable -> {
                    val next = reconnects.recordFailure(account.id, nowMillis, result.reason)
                    accounts.updateLoginState(
                        account.id,
                        AccountLoginState.NETWORK_PAUSED,
                        mapOf(
                            "lastNetworkPauseReason" to result.reason,
                            "lastNetworkPauseAt" to nowMillis.toString(),
                            "nextSessionProbeAt" to next.nextAttemptAtMillis.toString()
                        )
                    )
                    logs.append(
                        "账号 ${account.id} 状态同步暂停，第${next.failures}次；将在${next.nextAttemptAtMillis}后重试",
                        "session-recovery",
                        account.id
                    )
                    paused += 1
                }
            }
        }
        return SessionRecoverySummary(online, paused, waiting, relogged)
    }

    fun markNeedsRelogin(accountId: Long, reason: String) {
        accounts.updateLoginState(
            accountId,
            AccountLoginState.NEED_RELOGIN,
            mapOf("lastOfflineReason" to reason, "lastOfflineAt" to System.currentTimeMillis().toString())
        )
        reconnects.requestImmediate(accountId, reason)
        logs.append("账号 $accountId Session 已失效，已进入自动重登队列", "session-recovery", accountId)
    }

    fun markNetworkPaused(nowMillis: Long, reason: String) {
        accounts.listAccounts().filter { it.enabled && it.session?.sourceMode == 1 }.forEach { account ->
            accounts.updateLoginState(
                account.id,
                AccountLoginState.NETWORK_PAUSED,
                mapOf(
                    "lastNetworkPauseAt" to nowMillis.toString(),
                    "lastNetworkPauseReason" to reason
                )
            )
            reconnects.requestImmediate(account.id, reason)
        }
    }

    fun isRunnable(account: GameAccount): Boolean =
        account.enabled && account.session?.sourceMode == 1 && account.loginState == AccountLoginState.ONLINE

    fun earliestRetryAtMillis(nowMillis: Long): Long? = accounts.listAccounts()
        .asSequence()
        .filter { it.enabled && it.session?.sourceMode == 1 }
        .map { reconnects.state(it.id).nextAttemptAtMillis }
        .filter { it > nowMillis }
        .minOrNull()

    fun earliestValidationAtMillis(nowMillis: Long): Long? = accounts.listAccounts()
        .asSequence()
        .filter { it.enabled && it.session?.sourceMode == 1 && it.loginState == AccountLoginState.ONLINE }
        .map { account ->
            val last = account.session?.channelExtra?.get("lastValidatedAt")?.toLongOrNull()
            last?.plus(heartbeatIntervalMillis) ?: nowMillis
        }
        .minOrNull()
}
