package com.example.dwpmclone.data.account

import com.example.dwpmclone.data.local.LocalAccountRepository
import com.example.dwpmclone.data.local.SessionReconnectRepository
import com.example.dwpmclone.data.local.SessionReconnectState
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
}

data class AccountLifecycleDecision(
    val status: String,
    val statusText: String,
    val started: Boolean,
    val canonicalLoginState: String,
    val requiresRelogin: Boolean,
    val shouldProbe: Boolean,
    val mayUseLiveSession: Boolean,
    val runnable: Boolean,
    val heartbeatIntervalMillis: Long
)

fun interface AccountLifecycleDecisionSource {
    fun accountLifecycleDecision(
        accountEnabled: Boolean,
        executionOwnerActive: Boolean,
        loginState: String,
        sourceMode: Int,
        forceValidation: Boolean,
        lastValidatedAtMillis: Long?,
        nowMillis: Long
    ): AccountLifecycleDecision
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
    private val lifecycleDecisions: AccountLifecycleDecisionSource,
    private val stateTransitions: AccountStateTransitionSource,
    private val probe: SessionHealthProbe = RealSessionHealthProbe(),
) {
    fun reconcile(nowMillis: Long, forceValidation: Boolean): SessionRecoverySummary {
        var online = 0
        var paused = 0
        var waiting = 0
        var relogged = 0
        accounts.listAccounts().filter { it.enabled }.forEach { account ->
            val state = account.loginState.uppercase()
            val lifecycle = lifecycleDecisions.accountLifecycleDecision(
                accountEnabled = account.enabled,
                executionOwnerActive = true,
                loginState = state,
                sourceMode = account.session?.sourceMode ?: 0,
                forceValidation = forceValidation,
                lastValidatedAtMillis = account.session?.channelExtra
                    ?.get("lastValidatedAt")
                    ?.toLongOrNull(),
                nowMillis = nowMillis
            )
            if (lifecycle.requiresRelogin) {
                val retry = reconnects.state(account.id)
                if (retry.nextAttemptAtMillis > nowMillis) {
                    waiting += 1
                    return@forEach
                }
                runCatching { loginService.relogin(account, preserveTaskRuntime = true) }
                    .onSuccess { loggedIn ->
                        val transition = transition(
                            loggedIn,
                            AccountStateEvents.LOGIN_SUCCEEDED,
                            nowMillis,
                            validatedAtMillis = nowMillis
                        )
                        applyTransition(
                            loggedIn,
                            transition,
                            mapOf("lastReloginAt" to nowMillis.toString())
                        )
                        logs.append("账号 ${account.id} 自动重新登录成功", "session-recovery", account.id)
                        relogged += 1
                        online += 1
                    }
                    .onFailure { error ->
                        val transition = transition(
                            account,
                            AccountStateEvents.LOGIN_FAILED,
                            nowMillis,
                            message = error.message ?: "自动重登失败"
                        )
                        applyTransition(
                            account,
                            transition,
                            mapOf(
                                "nextReloginAt" to (transition.nextRetryAtMillis ?: 0L).toString(),
                                "lastReloginError" to transition.lastError
                            )
                        )
                        logs.append("账号 ${account.id} 自动重登失败，第${transition.failureCount}次；将在${transition.nextRetryAtMillis}后重试", "session-recovery", account.id)
                        waiting += 1
                    }
                return@forEach
            }
            val mustProbe = lifecycle.shouldProbe
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
                    val updated = account.copy(
                        displayName = result.updates["roleName"] ?: account.displayName,
                        monarchName = result.updates["roleName"] ?: account.monarchName,
                        session = session.copy(channelExtra = session.channelExtra + result.updates)
                    )
                    val transition = transition(
                        updated,
                        AccountStateEvents.PROBE_VALID,
                        nowMillis,
                        validatedAtMillis = result.updates["lastValidatedAt"]
                            ?.toLongOrNull()
                            ?: nowMillis
                    )
                    applyTransition(updated, transition, result.updates)
                    online += 1
                }
                is SessionProbeResult.Expired -> {
                    markNeedsRelogin(account.id, result.reason)
                    paused += 1
                }
                is SessionProbeResult.Unavailable -> {
                    val transition = transition(
                        account,
                        AccountStateEvents.PROBE_UNAVAILABLE,
                        nowMillis,
                        message = result.reason
                    )
                    applyTransition(
                        account,
                        transition,
                        mapOf(
                            "lastNetworkPauseReason" to transition.lastError,
                            "lastNetworkPauseAt" to nowMillis.toString(),
                            "nextSessionProbeAt" to (transition.nextRetryAtMillis ?: 0L).toString()
                        )
                    )
                    logs.append(
                        "账号 ${account.id} 状态同步暂停，第${transition.failureCount}次；将在${transition.nextRetryAtMillis}后重试",
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
        val account = accounts.get(accountId) ?: return
        val nowMillis = System.currentTimeMillis()
        val transition = transition(
            account,
            AccountStateEvents.SESSION_EXPIRED,
            nowMillis,
            message = reason,
            sessionInvalid = true
        )
        applyTransition(
            account,
            transition,
            mapOf(
                "lastOfflineReason" to transition.lastError,
                "lastOfflineAt" to nowMillis.toString()
            )
        )
        logs.append("账号 $accountId Session 已失效，已进入自动重登队列", "session-recovery", accountId)
    }

    fun markNetworkPaused(nowMillis: Long, reason: String) {
        accounts.listAccounts().filter { it.enabled && it.session?.sourceMode == 1 }.forEach { account ->
            val transition = transition(
                account,
                AccountStateEvents.NETWORK_UNAVAILABLE,
                nowMillis,
                message = reason
            )
            applyTransition(
                account,
                transition,
                mapOf(
                    "lastNetworkPauseAt" to nowMillis.toString(),
                    "lastNetworkPauseReason" to transition.lastError
                )
            )
        }
    }

    fun isRunnable(account: GameAccount): Boolean =
        lifecycleDecisions.accountLifecycleDecision(
            accountEnabled = account.enabled,
            executionOwnerActive = true,
            loginState = account.loginState,
            sourceMode = account.session?.sourceMode ?: 0,
            forceValidation = false,
            lastValidatedAtMillis = account.session?.channelExtra
                ?.get("lastValidatedAt")
                ?.toLongOrNull(),
            nowMillis = System.currentTimeMillis()
        ).runnable

    fun earliestRetryAtMillis(nowMillis: Long): Long? = accounts.listAccounts()
        .asSequence()
        .filter { it.enabled && it.session?.sourceMode == 1 }
        .map { reconnects.state(it.id).nextAttemptAtMillis }
        .filter { it > nowMillis }
        .minOrNull()

    fun earliestValidationAtMillis(nowMillis: Long): Long? = accounts.listAccounts()
        .asSequence()
        .filter { account ->
            lifecycleDecisions.accountLifecycleDecision(
                accountEnabled = account.enabled,
                executionOwnerActive = true,
                loginState = account.loginState,
                sourceMode = account.session?.sourceMode ?: 0,
                forceValidation = false,
                lastValidatedAtMillis = account.session?.channelExtra
                    ?.get("lastValidatedAt")
                    ?.toLongOrNull(),
                nowMillis = nowMillis
            ).mayUseLiveSession
        }
        .map { account ->
            val last = account.session?.channelExtra?.get("lastValidatedAt")?.toLongOrNull()
            val heartbeatIntervalMillis = lifecycleDecisions.accountLifecycleDecision(
                accountEnabled = account.enabled,
                executionOwnerActive = true,
                loginState = account.loginState,
                sourceMode = account.session?.sourceMode ?: 0,
                forceValidation = false,
                lastValidatedAtMillis = last,
                nowMillis = nowMillis
            ).heartbeatIntervalMillis
            last?.plus(heartbeatIntervalMillis) ?: nowMillis
        }
        .minOrNull()

    private fun transition(
        account: GameAccount,
        event: String,
        nowMillis: Long,
        message: String = "",
        sessionInvalid: Boolean = false,
        validatedAtMillis: Long? = null
    ): AccountStateTransition {
        val retry = reconnects.state(account.id)
        return stateTransitions.accountStateTransition(
            state = AccountTransitionInput(
                desiredStarted = account.enabled,
                loginState = account.loginState,
                sessionCredentialPresent = account.session?.sourceMode == 1,
                failureKind = retry.failureKind,
                failureCount = retry.failures,
                nextRetryAtMillis = retry.nextAttemptAtMillis.takeIf { it > 0L },
                lastError = retry.reason,
                lastValidatedAtMillis = account.session?.channelExtra
                    ?.get("lastValidatedAt")
                    ?.toLongOrNull()
            ),
            event = event,
            details = AccountTransitionDetails(
                message = message,
                sessionInvalid = sessionInvalid,
                validatedAtMillis = validatedAtMillis
            ),
            nowMillis = nowMillis
        )
    }

    private fun applyTransition(
        account: GameAccount,
        transition: AccountStateTransition,
        extraUpdates: Map<String, String> = emptyMap()
    ) {
        if (transition.sessionSecretAction == "delete") {
            accounts.deleteSessionSecrets(account.id)
        }
        val lifecycleUpdates = buildMap {
            transition.lastValidatedAtMillis?.let {
                put("lastValidatedAt", it.toString())
            }
            transition.nextRetryAtMillis?.let {
                put("nextReloginAt", it.toString())
            }
            put("lifecycleFailureKind", transition.failureKind)
            put("lifecycleFailureCount", transition.failureCount.toString())
            putAll(extraUpdates)
        }
        val session = account.session?.copy(
            tokenCiphertext = if (transition.sessionCredentialPresent) {
                LocalAccountRepository.SESSION_PRESENT_MARKER
            } else {
                ""
            },
            sourceMode = if (transition.sessionCredentialPresent) 1 else 0,
            channelExtra = account.session.channelExtra + lifecycleUpdates
        )
        accounts.upsert(
            account.copy(
                enabled = transition.desiredStarted,
                loginState = transition.loginState,
                session = session
            )
        )
        reconnects.replace(
            account.id,
            SessionReconnectState(
                failures = transition.failureCount,
                nextAttemptAtMillis = transition.nextRetryAtMillis ?: 0L,
                reason = transition.lastError,
                failureKind = transition.failureKind
            )
        )
    }
}
