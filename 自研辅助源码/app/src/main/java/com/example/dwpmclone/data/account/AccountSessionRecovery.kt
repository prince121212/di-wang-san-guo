package com.example.dwpmclone.data.account

import com.example.dwpmclone.data.local.LocalAccountRepository
import com.example.dwpmclone.data.local.SessionReconnectRepository
import com.example.dwpmclone.data.local.SessionReconnectState
import com.example.dwpmclone.data.local.TaskLogRepository
import com.example.dwpmclone.domain.model.GameAccount

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
    val heartbeatIntervalMillis: Long,
    val sessionValidationIntervalMillis: Long
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

data class AccountReloginResult(
    val accountId: Long,
    val message: String
)

fun interface AccountReloginSource {
    fun reloginAccount(accountId: Long): AccountReloginResult
}

sealed interface SessionProbeResult {
    data class Valid(val updates: Map<String, String>) : SessionProbeResult
    data class Expired(val reason: String) : SessionProbeResult
    data class Unavailable(val reason: String) : SessionProbeResult
}

fun interface SessionHealthProbe {
    fun probe(account: GameAccount, fullStateRefresh: Boolean): SessionProbeResult
}

data class SessionRecoverySummary(
    val online: Int,
    val paused: Int,
    val waitingToRetry: Int,
    val relogged: Int,
    val degraded: Int = 0
)

/** Reconciles enabled accounts before the scheduler may issue any task action. */
class AccountSessionRecovery(
    private val accounts: LocalAccountRepository,
    private val reloginSource: AccountReloginSource,
    private val reconnects: SessionReconnectRepository,
    private val logs: TaskLogRepository,
    private val lifecycleDecisions: AccountLifecycleDecisionSource,
    private val stateTransitions: AccountStateTransitionSource,
    private val probe: SessionHealthProbe,
) {
    private val processRecovery = AccountProcessRecoveryCoordinator(stateTransitions)

    fun prepareProcessRecovery(nowMillis: Long) {
        processRecovery.prepare(
            store = object : AccountProcessRecoveryStore {
                override fun snapshots(): List<AccountProcessRecoverySnapshot> =
                    accounts.listAccounts().map { account ->
                        AccountProcessRecoverySnapshot(account, reconnects.state(account.id))
                    }

                override fun apply(account: GameAccount, transition: AccountStateTransition) {
                    applyTransition(account, transition)
                }
            },
            nowMillis = nowMillis
        )
    }

    fun reconcile(nowMillis: Long, forceValidation: Boolean): SessionRecoverySummary {
        var online = 0
        var paused = 0
        var waiting = 0
        var relogged = 0
        var degraded = 0
        accounts.listAccounts().filter { it.enabled }.forEach { account ->
            val state = account.loginState.uppercase()
            val retryState = reconnects.state(account.id)
            val lastValidatedAt = account.session?.channelExtra
                ?.get("lastValidatedAt")
                ?.toLongOrNull()
            val lastProbeFailureAt = account.session?.channelExtra
                ?.get("lastNetworkPauseAt")
                ?.toLongOrNull()
            if (
                state == AccountLoginState.ONLINE &&
                retryState.failures > 0 &&
                lastValidatedAt != null &&
                lastProbeFailureAt != null &&
                lastValidatedAt > lastProbeFailureAt
            ) {
                val confirmed = transition(
                    account,
                    AccountStateEvents.PROBE_VALID,
                    nowMillis,
                    validatedAtMillis = lastValidatedAt
                )
                applyTransition(account, confirmed)
                logs.append(
                    "账号 ${account.id} 已由后续游戏响应确认在线，已清除探活失败连续计数",
                    "session-recovery",
                    account.id
                )
                online += 1
                return@forEach
            }
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
                val retry = retryState
                if (retry.nextAttemptAtMillis > nowMillis) {
                    waiting += 1
                    return@forEach
                }
                runCatching {
                    val result = reloginSource.reloginAccount(account.id)
                    accounts.get(result.accountId)
                        ?: error("共享重登成功后未找到账号记录")
                }.onSuccess { loggedIn ->
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
            val retry = retryState
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
                    if (transition.liveSessionUsable) {
                        logs.append(
                            "账号 ${account.id} 探活暂未确认，连续第${transition.failureCount}次；" +
                                "Session保持可用，将在${transition.nextRetryAtMillis}快速复核",
                            "session-recovery",
                            account.id
                        )
                        degraded += 1
                        online += 1
                    } else if (transition.nextOperation == "login") {
                        logs.append(
                            "账号 ${account.id} 连续第${transition.failureCount}次无法从旧Session取得应用层响应；" +
                                "将在${transition.nextRetryAtMillis}自动重新登录",
                            "session-recovery",
                            account.id
                        )
                        paused += 1
                    } else {
                        logs.append(
                            "账号 ${account.id} 状态同步暂停，连续第${transition.failureCount}次；" +
                                "将在${transition.nextRetryAtMillis}后重试",
                            "session-recovery",
                            account.id
                        )
                        paused += 1
                    }
                }
            }
        }
        return SessionRecoverySummary(online, paused, waiting, relogged, degraded)
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
            val sessionValidationIntervalMillis = lifecycleDecisions.accountLifecycleDecision(
                accountEnabled = account.enabled,
                executionOwnerActive = true,
                loginState = account.loginState,
                sourceMode = account.session?.sourceMode ?: 0,
                forceValidation = false,
                lastValidatedAtMillis = last,
                nowMillis = nowMillis
            ).sessionValidationIntervalMillis
            last?.plus(sessionValidationIntervalMillis) ?: nowMillis
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
